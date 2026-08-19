"""Offline recipe ingestion, normalization, validation and quality orchestration."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, ValidationError

from recipe_pipeline.generation.enhancer import AIOutputError, NoOpRecipeEnhancer, RecipeEnhancer
from recipe_pipeline.normalization.ingredients import UnknownIngredientError
from recipe_pipeline.normalization.recipe import RecipeNormalizer, StepIngredientReferenceError
from recipe_pipeline.quality.scoring import QualityReport, RecipeQualityScorer
from recipe_pipeline.schemas.recipe import RecipeStatus, RecipeV1
from recipe_pipeline.sources.base import InvalidSourceRecord, RecipeSource
from recipe_pipeline.validation.duplicate import DuplicateDetector
from recipe_pipeline.validation.models import IssueSeverity, ValidationIssue, ValidationReport
from recipe_pipeline.validation.validators import RecipeValidator


class PipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processed_count: int
    recipes: list[RecipeV1]
    validation_reports: list[ValidationReport]
    quality_reports: list[QualityReport]

    @property
    def accepted_count(self) -> int:
        return len(self.recipes)

    @property
    def rejected_count(self) -> int:
        return self.processed_count - self.accepted_count

    def summary(self) -> dict[str, int]:
        return {
            "processed": self.processed_count,
            "accepted": self.accepted_count,
            "rejected": self.rejected_count,
            "published": sum(recipe.quality.status == RecipeStatus.PUBLISHED for recipe in self.recipes),
            "needs_review": sum(recipe.quality.status == RecipeStatus.REVIEW for recipe in self.recipes),
        }


class RecipeDatasetPipeline:
    """Synchronous offline pipeline; intentionally independent of FastAPI and MySQL."""

    def __init__(
        self,
        normalizer: RecipeNormalizer | None = None,
        enhancer: RecipeEnhancer | None = None,
        validator: RecipeValidator | None = None,
        duplicate_detector: DuplicateDetector | None = None,
        quality_scorer: RecipeQualityScorer | None = None,
    ):
        self._normalizer = normalizer or RecipeNormalizer()
        self._enhancer = enhancer or NoOpRecipeEnhancer()
        self._validator = validator or RecipeValidator(self._normalizer.catalog)
        self._duplicate_detector = duplicate_detector or DuplicateDetector()
        self._quality_scorer = quality_scorer or RecipeQualityScorer()

    def run(
        self,
        source: RecipeSource,
        *,
        baseline_recipes: Iterable[RecipeV1] = (),
    ) -> PipelineResult:
        recipes: list[RecipeV1] = []
        validation_reports: list[ValidationReport] = []
        quality_reports: list[QualityReport] = []
        processed_count = 0
        self._duplicate_detector.reset()
        for baseline_recipe in baseline_recipes:
            self._duplicate_detector.register(baseline_recipe)

        for raw in source.load():
            processed_count += 1
            if isinstance(raw, InvalidSourceRecord):
                validation_reports.append(
                    ValidationReport(
                        source_record_id=raw.source_record_id,
                        is_valid=False,
                        issues=[
                            ValidationIssue(
                                code="SOURCE_PARSE_FAILED",
                                message=raw.error,
                                path="",
                                severity=IssueSeverity.ERROR,
                            )
                        ],
                    )
                )
                continue
            source_record_id = raw.source.source_record_id
            try:
                recipe = self._enhancer.enhance(self._normalizer.normalize(raw))
                issues = self._validator.validate(recipe)
                duplicate = self._duplicate_detector.find(recipe)
                if duplicate is not None:
                    issues.append(
                        ValidationIssue(
                            code="DUPLICATE_RECIPE",
                            message=(
                                f"duplicate of {duplicate.recipe_id}: {duplicate.reason}; "
                                f"ingredient_similarity={duplicate.ingredient_similarity:.3f}, "
                                f"step_similarity={duplicate.step_similarity:.3f}"
                            ),
                            path="recipe_id",
                            severity=IssueSeverity.ERROR,
                        )
                    )
                recipe, quality_report = self._quality_scorer.score(recipe, issues)
                is_valid = not any(issue.severity == IssueSeverity.ERROR for issue in issues)
                validation_reports.append(
                    ValidationReport(
                        source_record_id=source_record_id,
                        recipe_id=recipe.recipe_id,
                        is_valid=is_valid,
                        issues=issues,
                    )
                )
                quality_reports.append(quality_report)
                if recipe.quality.status != RecipeStatus.REJECTED:
                    recipes.append(recipe)
                    self._duplicate_detector.register(recipe)
            except (
                AIOutputError,
                UnknownIngredientError,
                StepIngredientReferenceError,
                ValidationError,
                ValueError,
            ) as exc:
                validation_reports.append(
                    ValidationReport(
                        source_record_id=source_record_id,
                        is_valid=False,
                        issues=[
                            ValidationIssue(
                                code="RECIPE_TRANSFORM_FAILED",
                                message=str(exc),
                                path="",
                                severity=IssueSeverity.ERROR,
                            )
                        ],
                    )
                )

        return PipelineResult(
            processed_count=processed_count,
            recipes=recipes,
            validation_reports=validation_reports,
            quality_reports=quality_reports,
        )
