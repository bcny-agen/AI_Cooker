"""Exact and near-duplicate detection with a replaceable step similarity strategy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from recipe_pipeline.schemas.recipe import RecipeV1


class StepSimilarityStrategy(Protocol):
    def similarity(self, left: RecipeV1, right: RecipeV1) -> float: ...


def _compact(value: str) -> str:
    return re.sub(r"\W+", "", value.casefold(), flags=re.UNICODE)


def _ngrams(value: str, size: int = 3) -> set[str]:
    compact = _compact(value)
    if len(compact) <= size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


class CharacterNgramStepSimilarity:
    def similarity(self, left: RecipeV1, right: RecipeV1) -> float:
        left_grams = _ngrams(" ".join(step.instruction for step in left.steps))
        right_grams = _ngrams(" ".join(step.instruction for step in right.steps))
        union = left_grams | right_grams
        return len(left_grams & right_grams) / len(union) if union else 1.0


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    recipe_id: UUID
    reason: str
    ingredient_similarity: float
    step_similarity: float


class DuplicateDetector:
    def __init__(
        self,
        step_strategy: StepSimilarityStrategy | None = None,
        ingredient_threshold: float = 0.9,
        step_threshold: float = 0.8,
    ):
        self._step_strategy = step_strategy or CharacterNgramStepSimilarity()
        self._ingredient_threshold = ingredient_threshold
        self._step_threshold = step_threshold
        self._known: list[RecipeV1] = []

    def reset(self) -> None:
        self._known.clear()

    def register(self, recipe: RecipeV1) -> None:
        self._known.append(recipe)

    def find(self, candidate: RecipeV1) -> DuplicateMatch | None:
        candidate_name = _compact(candidate.identity.name)
        candidate_ingredients = {item.ingredient_id for item in candidate.ingredients}
        for existing in self._known:
            existing_name = _compact(existing.identity.name)
            ingredient_score = self._set_similarity(
                candidate_ingredients,
                {item.ingredient_id for item in existing.ingredients},
            )
            step_score = self._step_strategy.similarity(candidate, existing)
            if candidate_name == existing_name:
                return DuplicateMatch(
                    existing.recipe_id,
                    "normalized recipe name matches an earlier record",
                    ingredient_score,
                    step_score,
                )
            if (
                ingredient_score >= self._ingredient_threshold
                and step_score >= self._step_threshold
            ):
                return DuplicateMatch(
                    existing.recipe_id,
                    "ingredient and cooking-step similarity exceed thresholds",
                    ingredient_score,
                    step_score,
                )
        return None

    @staticmethod
    def _set_similarity(left: set[UUID], right: set[UUID]) -> float:
        union = left | right
        return len(left & right) / len(union) if union else 1.0
