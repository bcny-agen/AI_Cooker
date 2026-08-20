"""Production embedding adapters plus deterministic offline test doubles."""

from __future__ import annotations

import math
import random
import re
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeAlias

import httpx

from recipe_pipeline.evaluation.embedding import EmbeddingContext


SparseVector: TypeAlias = dict[int, float]
DenseVector: TypeAlias = tuple[float, ...]
EmbeddingVector: TypeAlias = SparseVector | DenseVector


class EmbeddingProviderError(RuntimeError):
    """A provider request failed without exposing request credentials."""


class EmbeddingResponseError(EmbeddingProviderError):
    """A provider returned malformed vectors or an unexpected dimension."""


@dataclass(frozen=True, slots=True)
class EmbeddingProviderInfo:
    provider: str
    model: str
    dimensions: int | None
    execution_mode: str


class EmbeddingProvider(Protocol):
    @property
    def info(self) -> EmbeddingProviderInfo: ...

    def embed_documents(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]: ...

    def embed_queries(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]: ...

    def embed_query(
        self, text: str, context: EmbeddingContext | None = None
    ) -> EmbeddingVector: ...


def _normalise_dense(values: Sequence[float]) -> DenseVector:
    vector = tuple(float(value) for value in values)
    if not vector or any(not math.isfinite(value) for value in vector):
        raise EmbeddingResponseError("embedding vector is empty or non-finite")
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        raise EmbeddingResponseError("embedding vector has zero norm")
    return tuple(value / norm for value in vector)


def validate_vector_dimensions(
    vectors: Sequence[EmbeddingVector], expected: int | None = None
) -> int:
    if not vectors:
        raise EmbeddingResponseError("provider returned no vectors")
    dimensions = []
    for vector in vectors:
        if isinstance(vector, dict):
            dimensions.append(max(vector, default=-1) + 1)
        else:
            dimensions.append(len(vector))
    observed = dimensions[0]
    if observed <= 0 or any(value != observed for value in dimensions):
        raise EmbeddingResponseError("provider returned inconsistent vector dimensions")
    if expected is not None and observed != expected:
        raise EmbeddingResponseError(
            f"embedding dimension mismatch: expected {expected}, observed {observed}"
        )
    return observed


class TfidfEmbeddingProvider:
    """Character n-gram lexical comparison baseline, not a semantic model."""

    def __init__(self):
        self._vocabulary: dict[str, int] = {}
        self._idf: dict[int, float] = {}
        self._fitted = False

    @property
    def info(self) -> EmbeddingProviderInfo:
        return EmbeddingProviderInfo(
            "local", "character-ngram-tfidf", len(self._vocabulary) or None, "offline"
        )

    def embed_documents(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]:
        del contexts
        tokenized = [self._tokens(text) for text in texts]
        terms = sorted({term for tokens in tokenized for term in tokens})
        self._vocabulary = {term: index for index, term in enumerate(terms)}
        document_frequency = Counter(
            term for tokens in tokenized for term in set(tokens)
        )
        count = max(1, len(texts))
        self._idf = {
            self._vocabulary[term]: math.log((1 + count) / (1 + frequency)) + 1
            for term, frequency in document_frequency.items()
        }
        self._fitted = True
        return [self._vector(tokens) for tokens in tokenized]

    def embed_queries(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]:
        del contexts
        if not self._fitted:
            raise RuntimeError("embed_documents must be called before embed_queries")
        return [self._vector(self._tokens(text)) for text in texts]

    def embed_query(
        self, text: str, context: EmbeddingContext | None = None
    ) -> EmbeddingVector:
        return self.embed_queries([text], [context] if context else None)[0]

    def _vector(self, tokens: list[str]) -> SparseVector:
        counts = Counter(tokens)
        vector = {
            self._vocabulary[term]: frequency * self._idf[self._vocabulary[term]]
            for term, frequency in counts.items()
            if term in self._vocabulary
        }
        norm = math.sqrt(sum(value * value for value in vector.values()))
        return {index: value / norm for index, value in vector.items()} if norm else {}

    @staticmethod
    def _tokens(text: str) -> list[str]:
        lowered = text.casefold()
        tokens = re.findall(r"[a-z0-9_]+", lowered)
        for sequence in re.findall(r"[\u4e00-\u9fff]+", lowered):
            tokens.extend(
                sequence[index : index + 2]
                for index in range(max(0, len(sequence) - 1))
            )
            tokens.extend(
                sequence[index : index + 3]
                for index in range(max(0, len(sequence) - 2))
            )
        return tokens


class SentenceTransformerEmbeddingProvider:
    """CPU/GPU local adapter; model loading is lazy so unit tests stay offline."""

    def __init__(
        self,
        model: str,
        *,
        dimensions: int | None = None,
        batch_size: int = 16,
        device: str = "cpu",
        query_prefix: str | None = None,
        document_prefix: str | None = None,
    ):
        self._info = EmbeddingProviderInfo("sentence-transformers", model, dimensions, "local")
        self._batch_size = batch_size
        self._device = device
        default_query, default_document = self._default_prefixes(model)
        self._query_prefix = default_query if query_prefix is None else query_prefix
        self._document_prefix = (
            default_document if document_prefix is None else document_prefix
        )
        self._model_instance = None

    @staticmethod
    def _default_prefixes(model: str) -> tuple[str, str]:
        folded = model.casefold()
        if "bge-" in folded and "-zh" in folded:
            return "为这个句子生成表示以用于检索相关文章：", ""
        if "bge-" in folded:
            return "Represent this sentence for searching relevant passages: ", ""
        # Preserve the existing E5 contract for the frozen production model
        # and custom providers that previously relied on these defaults.
        return "query: ", "passage: "

    @property
    def info(self) -> EmbeddingProviderInfo:
        return self._info

    def _model(self):
        if self._model_instance is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise EmbeddingProviderError(
                    "sentence-transformers is required for the local provider"
                ) from error
            self._model_instance = SentenceTransformer(
                self._info.model, device=self._device
            )
        return self._model_instance

    def load_model(self) -> None:
        """Eagerly initialize the otherwise-lazy model during app startup."""

        self._model()

    def _embed(self, texts: Sequence[str], prefix: str) -> list[EmbeddingVector]:
        if not texts:
            return []
        prepared = [prefix + text for text in texts]
        try:
            encoded = self._model().encode(
                prepared,
                batch_size=self._batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except Exception as error:
            raise EmbeddingProviderError(
                f"local embedding failed for model {self._info.model}: {type(error).__name__}"
            ) from error
        vectors = [_normalise_dense(vector.tolist()) for vector in encoded]
        observed = validate_vector_dimensions(vectors, self._info.dimensions)
        if self._info.dimensions is None:
            self._info = EmbeddingProviderInfo(
                self._info.provider, self._info.model, observed, self._info.execution_mode
            )
        return vectors

    def embed_documents(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]:
        del contexts
        return self._embed(texts, self._document_prefix)

    def embed_queries(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]:
        del contexts
        return self._embed(texts, self._query_prefix)

    def embed_query(
        self, text: str, context: EmbeddingContext | None = None
    ) -> EmbeddingVector:
        return self.embed_queries([text], [context] if context else None)[0]


class OpenAICompatibleEmbeddingProvider:
    """Batched /embeddings HTTP adapter with bounded retry and validation."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        dimensions: int | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        query_prefix: str = "",
        document_prefix: str = "",
        client: httpx.Client | None = None,
    ):
        if not api_key:
            raise ValueError("embedding API key is required")
        if max_retries < 0 or max_retries > 10:
            raise ValueError("max_retries must be between 0 and 10")
        self._info = EmbeddingProviderInfo("openai-compatible", model, dimensions, "remote")
        self._endpoint = base_url.rstrip("/") + "/embeddings"
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self._query_prefix = query_prefix
        self._document_prefix = document_prefix
        self._client = client or httpx.Client()

    @property
    def info(self) -> EmbeddingProviderInfo:
        return self._info

    def _request(self, texts: Sequence[str], prefix: str) -> list[EmbeddingVector]:
        if not texts:
            return []
        payload = {"model": self._info.model, "input": [prefix + text for text in texts]}
        if self._info.dimensions is not None:
            payload["dimensions"] = self._info.dimensions
        response = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(
                    self._endpoint,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                    timeout=self._timeout,
                )
                if response.status_code < 400:
                    break
                if response.status_code not in {408, 409, 429} and response.status_code < 500:
                    raise EmbeddingProviderError(
                        f"embedding request rejected with HTTP {response.status_code}"
                    )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt == self._max_retries:
                    raise EmbeddingProviderError(
                        f"embedding request failed after {attempt + 1} attempts"
                    ) from error
            if attempt == self._max_retries:
                status = response.status_code if response is not None else "transport"
                raise EmbeddingProviderError(
                    f"embedding request failed after {attempt + 1} attempts (HTTP {status})"
                )
            retry_after = response.headers.get("Retry-After") if response is not None else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else self._backoff * (2**attempt)
            time.sleep(delay + random.random() * min(0.1, delay))
        try:
            data = response.json()["data"]
            ordered = sorted(data, key=lambda item: item["index"])
            if len(ordered) != len(texts):
                raise ValueError("wrong number of embeddings")
            vectors = [_normalise_dense(item["embedding"]) for item in ordered]
        except (KeyError, TypeError, ValueError) as error:
            raise EmbeddingResponseError("embedding response was malformed") from error
        observed = validate_vector_dimensions(vectors, self._info.dimensions)
        if self._info.dimensions is None:
            self._info = EmbeddingProviderInfo(
                self._info.provider, self._info.model, observed, self._info.execution_mode
            )
        return vectors

    def embed_documents(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]:
        del contexts
        return self._request(texts, self._document_prefix)

    def embed_queries(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]:
        del contexts
        return self._request(texts, self._query_prefix)

    def embed_query(
        self, text: str, context: EmbeddingContext | None = None
    ) -> EmbeddingVector:
        return self.embed_queries([text], [context] if context else None)[0]


class FakeEmbeddingProvider:
    """Deterministic test double; never selected by the benchmark CLI."""

    def __init__(
        self,
        vectors_by_text: dict[str, EmbeddingVector],
        *,
        model: str = "fake-v1",
        dimensions: int | None = None,
        fail_texts: set[str] | None = None,
    ):
        self._vectors = vectors_by_text
        self._fail_texts = fail_texts or set()
        inferred = dimensions
        if inferred is None and vectors_by_text:
            first = next(iter(vectors_by_text.values()))
            inferred = max(first, default=-1) + 1 if isinstance(first, dict) else len(first)
        self._info = EmbeddingProviderInfo("fake", model, inferred, "test")
        self.document_calls: list[list[str]] = []
        self.query_calls: list[list[str]] = []

    @property
    def info(self) -> EmbeddingProviderInfo:
        return self._info

    def _vectors_for(self, texts: Sequence[str]) -> list[EmbeddingVector]:
        failed = [text for text in texts if text in self._fail_texts]
        if failed:
            raise EmbeddingProviderError("deterministic fake failure")
        output = []
        for text in texts:
            vector = self._vectors.get(text)
            if vector is None:
                vector = next(
                    (
                        candidate
                        for known_text, candidate in self._vectors.items()
                        if text in known_text or known_text.strip() in text
                    ),
                    {},
                )
            output.append(self._copy(vector))
        return output

    @staticmethod
    def _copy(vector: EmbeddingVector) -> EmbeddingVector:
        return dict(vector) if isinstance(vector, dict) else tuple(vector)

    def embed_documents(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]:
        del contexts
        self.document_calls.append(list(texts))
        return self._vectors_for(texts)

    def embed_queries(
        self,
        texts: Sequence[str],
        contexts: Sequence[EmbeddingContext] | None = None,
    ) -> list[EmbeddingVector]:
        del contexts
        self.query_calls.append(list(texts))
        return self._vectors_for(texts)

    def embed_query(
        self, text: str, context: EmbeddingContext | None = None
    ) -> EmbeddingVector:
        return self.embed_queries([text], [context] if context else None)[0]


def sparse_dot(left: EmbeddingVector, right: EmbeddingVector) -> float:
    if isinstance(left, dict) and isinstance(right, dict):
        if len(left) > len(right):
            left, right = right, left
        return sum(value * right.get(index, 0.0) for index, value in left.items())
    if isinstance(left, dict) or isinstance(right, dict):
        sparse, dense = (left, right) if isinstance(left, dict) else (right, left)
        return sum(value * dense[index] for index, value in sparse.items() if index < len(dense))
    if len(left) != len(right):
        raise EmbeddingResponseError(
            f"cannot compare vectors with dimensions {len(left)} and {len(right)}"
        )
    return sum(a * b for a, b in zip(left, right))
