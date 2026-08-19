"""Explainable quality scoring for Recipe Schema v1 records."""

from __future__ import annotations

import hashlib
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from recipe_pipeline.schemas.recipe import QualityMetadata, RecipeStatus, RecipeV1
from recipe_pipeline.validation.models import IssueSeverity, ValidationIssue


class QualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_id: UUID
    score: float = Field(ge=0, le=1)
    status: RecipeStatus
    components: dict[str, float]


class RecipeQualityScorer:
    """Weighted, deterministic gate: <.70 reject, <.85 review, otherwise publish."""

    WEIGHTS = {
        "source_reliability": 0.30,
        "schema_completeness": 0.15,
        "ingredient_consistency": 0.20,
        "step_consistency": 0.20,
        "safety": 0.15,
    }

    def score(
        self, recipe: RecipeV1, issues: list[ValidationIssue]
    ) -> tuple[RecipeV1, QualityReport]:
        has_error = any(issue.severity == IssueSeverity.ERROR for issue in issues)
        components = {
            "source_reliability": recipe.source.reliability_score,
            "schema_completeness": self._completeness(recipe),
            "ingredient_consistency": self._component_score(
                issues, ("INGREDIENT_", "REQUIRED_", "UNKNOWN_STEP_INGREDIENT")
            ),
            "step_consistency": self._component_score(
                issues, ("STEP_",)
            ),
            "safety": self._component_score(
                issues,
                (
                    "UNSAFE_",
                    "UNSUPPORTED_MEDICAL_",
                    "IMPLAUSIBLE_",
                    "NUTRITION_",
                ),
            ),
        }
        score = round(
            sum(components[name] * weight for name, weight in self.WEIGHTS.items()),
            4,
        )
        if has_error or score < 0.70:
            status = RecipeStatus.REJECTED
        elif score < 0.85:
            status = RecipeStatus.REVIEW
        else:
            status = RecipeStatus.PUBLISHED

        content_hash = hashlib.sha256(
            recipe.model_dump_json(
                exclude={"quality": True, "source": {"imported_at"}}
            ).encode("utf-8")
        ).hexdigest()
        updated = recipe.model_copy(
            update={
                "quality": QualityMetadata(
                    status=status,
                    confidence_score=score,
                    human_reviewed=recipe.quality.human_reviewed,
                    content_hash=content_hash,
                )
            }
        )
        report = QualityReport(
            recipe_id=recipe.recipe_id,
            score=score,
            status=status,
            components={key: round(value, 4) for key, value in components.items()},
        )
        return updated, report

    @staticmethod
    def _completeness(recipe: RecipeV1) -> float:
        optional_signals = (
            bool(recipe.identity.aliases),
            recipe.nutrition.calories_kcal is not None,
            recipe.nutrition.protein_g is not None,
            recipe.nutrition.fat_g is not None,
            recipe.nutrition.carbohydrate_g is not None,
            bool(recipe.tags.scenario),
            bool(recipe.source.license),
        )
        return 0.8 + 0.2 * (sum(optional_signals) / len(optional_signals))

    @staticmethod
    def _component_score(
        issues: list[ValidationIssue], prefixes: tuple[str, ...]
    ) -> float:
        relevant = [
            issue
            for issue in issues
            if any(issue.code.startswith(prefix) for prefix in prefixes)
        ]
        errors = sum(issue.severity == IssueSeverity.ERROR for issue in relevant)
        warnings = sum(issue.severity == IssueSeverity.WARNING for issue in relevant)
        return max(0.0, 1.0 - errors * 0.5 - warnings * 0.15)
