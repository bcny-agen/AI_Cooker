"""Zero-dependency local vector prototype for evaluation, not production use."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from uuid import UUID

from recipe_pipeline.evaluation.baseline import (
    BaselineCandidate,
    BaselineRecipeRetriever,
)
from recipe_pipeline.evaluation.embedding import (
    EmbeddingDocument,
    EmbeddingKind,
    RecipeEmbeddingTextBuilder,
)
from recipe_pipeline.schemas.recipe import RecipeV1


class HashingTextEmbedder:
    """Deterministic token hashing; replaceable by a real embedding model later."""

    def __init__(self, dimensions: int = 512):
        if dimensions < 64:
            raise ValueError("dimensions must be at least 64")
        self.dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        for token in self._tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return tuple(vector)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        lowered = text.casefold()
        tokens = re.findall(r"[a-z0-9_]+", lowered)
        for sequence in re.findall(r"[\u4e00-\u9fff]+", lowered):
            tokens.extend(sequence[index : index + 2] for index in range(max(0, len(sequence) - 1)))
            tokens.extend(sequence[index : index + 3] for index in range(max(0, len(sequence) - 2)))
        return tokens


@dataclass(frozen=True, slots=True)
class _VectorRecord:
    document: EmbeddingDocument
    vector: tuple[float, ...]


class InMemoryVectorStore:
    def __init__(self):
        self._records: list[_VectorRecord] = []

    def add(self, document: EmbeddingDocument, vector: tuple[float, ...]) -> None:
        self._records.append(_VectorRecord(document, vector))

    def search(
        self, query_vector: tuple[float, ...]
    ) -> list[tuple[EmbeddingDocument, float]]:
        scored = [
            (
                record.document,
                sum(left * right for left, right in zip(record.vector, query_vector)),
            )
            for record in self._records
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored


_KIND_WEIGHTS = {
    EmbeddingKind.INGREDIENT: 0.45,
    EmbeddingKind.SCENARIO: 0.25,
    EmbeddingKind.FULL_RECIPE: 0.30,
}


class LocalVectorRecipeRetriever:
    def __init__(
        self,
        recipes: list[RecipeV1],
        baseline: BaselineRecipeRetriever,
        text_builder: RecipeEmbeddingTextBuilder | None = None,
        embedder: HashingTextEmbedder | None = None,
    ):
        self._recipes_by_id = {recipe.recipe_id: recipe for recipe in recipes}
        self._baseline = baseline
        self._embedder = embedder or HashingTextEmbedder()
        self._store = InMemoryVectorStore()
        builder = text_builder or RecipeEmbeddingTextBuilder()
        for recipe in recipes:
            for document in builder.build(recipe):
                self._store.add(document, self._embedder.embed(document.text))

    def retrieve(self, query: str, top_k: int = 5) -> list[BaselineCandidate]:
        parsed = self._baseline.parser.parse(query)
        query_vector = self._embedder.embed(parsed.expanded_text())
        aggregate_scores: dict[UUID, float] = {}
        for document, similarity in self._store.search(query_vector):
            aggregate_scores[document.recipe_id] = (
                aggregate_scores.get(document.recipe_id, 0.0)
                + similarity * _KIND_WEIGHTS[document.kind]
            )
        ordered = sorted(
            aggregate_scores.items(), key=lambda item: item[1], reverse=True
        )[:top_k]
        hits = []
        for recipe_id, score in ordered:
            recipe = self._recipes_by_id[recipe_id]
            baseline_metadata = self._baseline.score_recipe(recipe, parsed)
            hits.append(
                BaselineCandidate(
                    recipe=recipe,
                    score=round(score, 6),
                    ingredient_coverage=baseline_metadata.ingredient_coverage,
                    preference_match=baseline_metadata.preference_match,
                )
            )
        return hits
