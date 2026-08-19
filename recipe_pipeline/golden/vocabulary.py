"""Controlled ingredient-vocabulary review for Golden Dataset v1."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from recipe_pipeline.normalization.ingredients import (
    GOLDEN_INGREDIENT_ENTRIES,
    IngredientCatalog,
    UnknownIngredientError,
)


class VocabularyDecision(str, Enum):
    APPROVE = "APPROVE"
    MAP = "MAP"
    REVIEW = "REVIEW"


class VocabularyReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submitted_name: str
    decision: VocabularyDecision
    canonical_name: str | None
    ingredient_id: UUID | None
    reason: str


class IngredientVocabularyReviewQueue:
    """Never creates a canonical concept from an unreviewed model string."""

    def __init__(self, catalog: IngredientCatalog | None = None):
        self.catalog = catalog or IngredientCatalog()

    def review(self, submitted_name: str) -> VocabularyReviewItem:
        try:
            entry = self.catalog.resolve(submitted_name)
        except UnknownIngredientError:
            return VocabularyReviewItem(
                submitted_name=submitted_name,
                decision=VocabularyDecision.REVIEW,
                canonical_name=None,
                ingredient_id=None,
                reason="unknown concept requires explicit vocabulary-owner review",
            )
        decision = (
            VocabularyDecision.APPROVE
            if submitted_name == entry.normalized_name
            else VocabularyDecision.MAP
        )
        return VocabularyReviewItem(
            submitted_name=submitted_name,
            decision=decision,
            canonical_name=entry.normalized_name,
            ingredient_id=entry.ingredient_id,
            reason=(
                "reviewed canonical concept"
                if decision == VocabularyDecision.APPROVE
                else "mapped through a reviewed alias"
            ),
        )


def build_vocabulary_report(blueprint_ingredient_names: set[str]) -> dict:
    queue = IngredientVocabularyReviewQueue()
    used_items = [queue.review(name) for name in sorted(blueprint_ingredient_names)]
    additions = [
        {
            "canonical_name": item.normalized_name,
            "ingredient_id": str(item.ingredient_id),
            "aliases": list(item.aliases),
            "decision": "APPROVE",
        }
        for item in GOLDEN_INGREDIENT_ENTRIES
    ]
    unresolved = [item for item in used_items if item.decision == VocabularyDecision.REVIEW]
    return {
        "workflow": ["REVIEW", "APPROVE_OR_MAP", "DETERMINISTIC_ID", "USE"],
        "golden_vocabulary_addition_count": len(additions),
        "golden_vocabulary_additions": additions,
        "blueprint_unique_ingredient_count": len(blueprint_ingredient_names),
        "blueprint_resolution": [item.model_dump(mode="json") for item in used_items],
        "unresolved_count": len(unresolved),
        "unresolved": [item.model_dump(mode="json") for item in unresolved],
        "id_policy": "uuid5(NAMESPACE_URL, 'ai-cooker:ingredient:<canonical-name>')",
    }
