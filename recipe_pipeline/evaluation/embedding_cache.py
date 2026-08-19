"""Atomic, resumable embedding cache keyed by model, view, text, and template."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from recipe_pipeline.evaluation.embedding import EmbeddingContext
from recipe_pipeline.evaluation.embedding_providers import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingResponseError,
    EmbeddingVector,
    validate_vector_dimensions,
)


def source_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class EmbeddingCacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0
    provider_requests: int = 0
    failures: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class EmbeddingGenerationError(EmbeddingProviderError):
    def __init__(self, failures: list[dict[str, str]]):
        super().__init__(f"{len(failures)} embedding item(s) failed")
        self.failures = failures


class CachedEmbeddingProvider:
    def __init__(
        self,
        provider: EmbeddingProvider,
        cache_dir: Path,
        *,
        batch_size: int = 16,
    ):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._provider = provider
        self._cache_dir = cache_dir
        self._batch_size = batch_size
        self.stats = EmbeddingCacheStats()

    @property
    def info(self):
        return self._provider.info

    def embed_documents(self, texts, contexts=None):
        return self._embed(texts, contexts, "document")

    def embed_queries(self, texts, contexts=None):
        return self._embed(texts, contexts, "query")

    def embed_query(self, text, context=None):
        return self.embed_queries([text], [context] if context else None)[0]

    def read_cached_document(
        self, text: str, context: EmbeddingContext
    ) -> EmbeddingVector | None:
        """Read one validated document vector without generating a replacement."""
        return self._read(self._entry_path("document", context, text), context, text)

    def _embed(
        self,
        texts: list[str] | tuple[str, ...],
        contexts: list[EmbeddingContext] | tuple[EmbeddingContext, ...] | None,
        lane: Literal["document", "query"],
    ) -> list[EmbeddingVector]:
        values = list(texts)
        if contexts is None:
            contexts = [EmbeddingContext("DEFAULT", "unversioned-v1") for _ in values]
        contexts = list(contexts)
        if len(contexts) != len(values):
            raise ValueError("one embedding context is required per source text")
        results: list[EmbeddingVector | None] = [None] * len(values)
        pending: list[tuple[int, str, EmbeddingContext, Path]] = []
        for index, (text, context) in enumerate(zip(values, contexts)):
            path = self._entry_path(lane, context, text)
            cached = self._read(path, context, text)
            if cached is not None:
                self.stats.hits += 1
                results[index] = cached
            else:
                self.stats.misses += 1
                pending.append((index, text, context, path))
        failures: list[dict[str, str]] = []
        for offset in range(0, len(pending), self._batch_size):
            self._process_batch(pending[offset : offset + self._batch_size], lane, results, failures)
        if failures:
            raise EmbeddingGenerationError(failures)
        return [vector for vector in results if vector is not None]

    def _process_batch(self, batch, lane, results, failures) -> None:
        if not batch:
            return
        try:
            self.stats.provider_requests += 1
            texts = [item[1] for item in batch]
            contexts = [item[2] for item in batch]
            if lane == "document":
                vectors = self._provider.embed_documents(texts, contexts)
            else:
                vectors = self._provider.embed_queries(texts, contexts)
            if len(vectors) != len(batch):
                raise EmbeddingResponseError("provider returned the wrong vector count")
            expected = self._expected_dimension()
            observed = validate_vector_dimensions(vectors, expected)
            self._write_dimension(observed)
            for item, vector in zip(batch, vectors):
                index, text, context, path = item
                results[index] = vector
                self._write(path, context, text, vector, observed)
                self.stats.writes += 1
        except EmbeddingProviderError as error:
            if len(batch) > 1:
                midpoint = len(batch) // 2
                self._process_batch(batch[:midpoint], lane, results, failures)
                self._process_batch(batch[midpoint:], lane, results, failures)
                return
            self.stats.failures += 1
            _, text, context, _ = batch[0]
            failures.append(
                {
                    "source_text_hash": source_text_hash(text),
                    "representation_type": context.representation_type,
                    "error": type(error).__name__,
                }
            )

    def _namespace(self) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{self.info.provider}__{self.info.model}")
        return self._cache_dir / safe

    def _entry_path(self, lane: str, context: EmbeddingContext, text: str) -> Path:
        safe_type = re.sub(r"[^a-zA-Z0-9._-]+", "_", context.representation_type)
        safe_template = re.sub(r"[^a-zA-Z0-9._-]+", "_", context.template_version)
        return self._namespace() / lane / safe_type / safe_template / f"{source_text_hash(text)}.json"

    def _dimension_path(self) -> Path:
        return self._namespace() / "metadata.json"

    def _expected_dimension(self) -> int | None:
        configured = self.info.dimensions
        path = self._dimension_path()
        if not path.exists():
            return configured
        try:
            cached = int(json.loads(path.read_text(encoding="utf-8"))["dimensions"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise EmbeddingResponseError("embedding cache metadata is malformed") from error
        if configured is not None and configured != cached:
            raise EmbeddingResponseError(
                f"cached dimension {cached} does not match configured dimension {configured}"
            )
        return cached

    def _write_dimension(self, observed: int) -> None:
        expected = self._expected_dimension()
        if expected is not None and expected != observed:
            raise EmbeddingResponseError(
                f"embedding dimension mismatch: expected {expected}, observed {observed}"
            )
        path = self._dimension_path()
        if not path.exists():
            self._atomic_json(path, {"dimensions": observed})

    def _read(self, path: Path, context: EmbeddingContext, text: str) -> EmbeddingVector | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["source_text_hash"] != source_text_hash(text):
                return None
            if payload["template_version"] != context.template_version:
                return None
            values = tuple(float(value) for value in payload["vector"])
            validate_vector_dimensions([values], self._expected_dimension())
            return values
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _write(self, path: Path, context: EmbeddingContext, text: str, vector: EmbeddingVector, dimensions: int) -> None:
        dense = [0.0] * dimensions if isinstance(vector, dict) else list(vector)
        if isinstance(vector, dict):
            for index, value in vector.items():
                dense[index] = value
        self._atomic_json(
            path,
            {
                "provider": self.info.provider,
                "model": self.info.model,
                "representation_type": context.representation_type,
                "template_version": context.template_version,
                "source_text_hash": source_text_hash(text),
                "dimensions": dimensions,
                "vector": dense,
            },
        )

    @staticmethod
    def _atomic_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.replace(path)
