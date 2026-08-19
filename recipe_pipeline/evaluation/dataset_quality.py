"""Offline Step 17F dataset quality, diversity, and retrieval comparison."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from recipe_pipeline.evaluation.models import RetrieverMetrics
from recipe_pipeline.evaluation.runner import RecipeRetrievalEvaluationRunner
from recipe_pipeline.schemas.recipe import CookingMethod, RecipeStatus, RecipeV1
from recipe_pipeline.sources import load_recipe_jsonl


class FailureExample(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: str
    source_record_id: str
    code: str
    detail: str


class DatasetQualitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    requested_count: int
    generated_count: int
    accepted_count: int
    schema_pass_rate: float
    validation_pass_rate: float
    duplicate_rate: float
    suspected_near_duplicate_rate: float
    suspected_near_duplicate_pairs: list[list[str]]
    average_quality_score: float | None
    rejected_rate: float
    review_rate: float
    published_rate: float
    unique_ingredient_count: int
    cuisine_distribution: dict[str, int]
    category_distribution: dict[str, int]
    issue_counts: dict[str, int]
    failure_classification_counts: dict[str, int]
    failure_examples: list[FailureExample]
    culinary_audit_pass_rate: float | None
    culinary_audit_concerns: dict[str, int]
    generator_metadata_preserved_count: int


class RetrievalComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_100_recipe_count: int
    combined_recipe_count: int
    current_100: RetrieverMetrics
    combined: RetrieverMetrics
    average_new_recipe_top_5_share: float
    queries_with_new_recipe_in_top_5: int
    queries_with_three_or_more_new_recipes_in_top_5: int
    combined_failed_queries: list[str]
    qrel_warning: str


class StepFlashEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment: str = "step17f_step_flash_batch_200"
    codex_dataset: DatasetQualitySnapshot
    step_flash_dataset: DatasetQualitySnapshot
    retrieval: RetrievalComparison
    recommendation_basis: list[str] = Field(default_factory=list)
    observed_generation_failure_examples: list[str] = Field(default_factory=list)
    prompt_improvements: list[str] = Field(default_factory=list)


class StepFlashExperimentEvaluator:
    def evaluate(
        self,
        *,
        codex_dir: Path,
        step_flash_dir: Path,
        output_path: Path,
    ) -> StepFlashEvaluationReport:
        codex_recipes = load_recipe_jsonl(codex_dir / "recipes.jsonl")
        step_recipes = load_recipe_jsonl(step_flash_dir / "recipes.jsonl")
        codex_snapshot = self._snapshot("codex_first_100", codex_dir, codex_recipes)
        step_snapshot = self._snapshot(
            "step_flash_batch_200", step_flash_dir, step_recipes
        )
        retrieval = self._retrieval_comparison(
            codex_recipes, step_recipes, output_path.parent
        )
        report = StepFlashEvaluationReport(
            codex_dataset=codex_snapshot,
            step_flash_dataset=step_snapshot,
            retrieval=retrieval,
            recommendation_basis=self._recommendation_basis(
                codex_snapshot, step_snapshot, retrieval
            ),
            observed_generation_failure_examples=[
                "source.imported_at was emitted as null instead of omitted",
                "a five-recipe response was truncated before the JSON string closed",
                "HEALTHY_MEAL was placed in tags.health instead of tags.scenario",
                "steps referenced water even when water was absent from ingredients",
            ],
            prompt_improvements=[
                "Reduce Step generation to one or two recipes per request, or use provider-supported strict structured output.",
                "Require all numeric nutrition fields to be null and nutrition levels UNKNOWN unless externally calculated.",
                "Ban health-targeting and unverified audience claims such as weight control, easy digestion, and fitness food.",
                "Require water to appear in ingredients whenever a step references it.",
                "Require explicit safe doneness cues for poultry and fish.",
                "Add a second-stage semantic near-duplicate gate before dataset acceptance.",
            ],
        )
        self._atomic_json(output_path, report.model_dump(mode="json"))
        return report

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _snapshot(
        self,
        dataset_name: str,
        directory: Path,
        recipes: list[RecipeV1],
    ) -> DatasetQualitySnapshot:
        generation = self._load_json(directory / "generation_report.json")
        validation = self._load_json(directory / "validation_report.json")
        quality = self._load_json(directory / "quality_report.json")
        validation_items = validation.get("items", [])
        quality_items = quality.get("items", [])
        requested = int(generation.get("total_requested", len(recipes)))
        generated = int(generation.get("generated_successfully", len(validation_items)))
        valid_count = sum(bool(item.get("is_valid")) for item in validation_items)
        issue_counts: Counter[str] = Counter()
        classifications: Counter[str] = Counter()
        examples: list[FailureExample] = []
        for item in validation_items:
            for issue in item.get("issues", []):
                code = str(issue.get("code", "UNKNOWN"))
                issue_counts[code] += 1
                classification = self._classify_issue(code, str(issue.get("message", "")))
                classifications[classification] += 1
                if len(examples) < 10:
                    examples.append(
                        FailureExample(
                            classification=classification,
                            source_record_id=str(item.get("source_record_id", "unknown")),
                            code=code,
                            detail=str(issue.get("message", ""))[:300],
                        )
                    )
        generation_failures = generation.get("generation_failures", [])
        for failure in generation_failures:
            count = int(failure.get("requested_count", 0))
            classifications["generation_problem"] += count
            if len(examples) < 10:
                examples.append(
                    FailureExample(
                        classification="generation_problem",
                        source_record_id=f"batch-{failure.get('batch_index', 'unknown')}",
                        code=str(failure.get("error_type", "GENERATION_FAILED")),
                        detail=(
                            f"batch exhausted {failure.get('attempts', 0)} attempts; "
                            f"{count} requested records were not produced"
                        ),
                    )
                )
        quality_scores = [float(item["score"]) for item in quality_items]
        status_counts = Counter(str(item["status"]) for item in quality_items)
        duplicate_count = issue_counts.get("DUPLICATE_RECIPE", 0)
        concerns = Counter(
            concern
            for recipe in recipes
            for concern in self._culinary_concerns(recipe)
        )
        passed_culinary = sum(not self._culinary_concerns(recipe) for recipe in recipes)
        near_duplicate_pairs = self._suspected_near_duplicates(recipes)
        return DatasetQualitySnapshot(
            dataset_name=dataset_name,
            requested_count=requested,
            generated_count=generated,
            accepted_count=len(recipes),
            schema_pass_rate=self._rate(generated, requested),
            validation_pass_rate=self._rate(valid_count, generated),
            duplicate_rate=self._rate(duplicate_count, generated),
            suspected_near_duplicate_rate=self._rate(
                len({name for pair in near_duplicate_pairs for name in pair}),
                len(recipes),
            ),
            suspected_near_duplicate_pairs=near_duplicate_pairs,
            average_quality_score=(round(mean(quality_scores), 4) if quality_scores else None),
            rejected_rate=self._rate(requested - len(recipes), requested),
            review_rate=self._rate(status_counts[RecipeStatus.REVIEW.value], requested),
            published_rate=self._rate(status_counts[RecipeStatus.PUBLISHED.value], requested),
            unique_ingredient_count=len(
                {item.ingredient_id for recipe in recipes for item in recipe.ingredients}
            ),
            cuisine_distribution=dict(Counter(recipe.identity.cuisine.value for recipe in recipes)),
            category_distribution=dict(Counter(recipe.identity.category.value for recipe in recipes)),
            issue_counts=dict(issue_counts),
            failure_classification_counts=dict(classifications),
            failure_examples=examples,
            culinary_audit_pass_rate=(
                self._rate(passed_culinary, len(recipes)) if recipes else None
            ),
            culinary_audit_concerns=dict(concerns),
            generator_metadata_preserved_count=sum(
                bool(recipe.source.generator_model and recipe.source.dataset_version)
                for recipe in recipes
            ),
        )

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    @staticmethod
    def _classify_issue(code: str, message: str) -> str:
        if code == "DUPLICATE_RECIPE":
            return "duplicate_problem"
        if code == "SOURCE_PARSE_FAILED":
            return "schema_problem"
        if code == "RECIPE_TRANSFORM_FAILED":
            lowered = message.casefold()
            if "ingredient" in lowered or "食材" in lowered:
                return "normalization_problem"
            return "schema_problem"
        return "validation_problem"

    @staticmethod
    def _culinary_concerns(recipe: RecipeV1) -> list[str]:
        concerns = []
        if len(recipe.ingredients) < 2:
            concerns.append("TOO_FEW_INGREDIENTS")
        if len(recipe.ingredients) > 15:
            concerns.append("TOO_MANY_HOUSEHOLD_INGREDIENTS")
        if len(recipe.steps) < 2:
            concerns.append("TOO_FEW_EXECUTABLE_STEPS")
        if recipe.time.total_minutes > 180:
            concerns.append("HOUSEHOLD_TIME_OVER_180_MINUTES")
        if all(step.method == CookingMethod.PREPARE for step in recipe.steps):
            concerns.append("NO_COOKING_METHOD")
        numeric_nutrition = (
            recipe.nutrition.calories_kcal,
            recipe.nutrition.protein_g,
            recipe.nutrition.fat_g,
            recipe.nutrition.carbohydrate_g,
        )
        if any(value is not None for value in numeric_nutrition):
            concerns.append("UNVERIFIED_SYNTHETIC_NUTRITION")
        summary = recipe.identity.summary
        if any(
            term in summary
            for term in ("控脂", "减肥", "健身", "老人", "小孩", "易消化", "零失败")
        ):
            concerns.append("HEALTH_OR_AUDIENCE_CLAIM_REQUIRES_REVIEW")
        ingredient_names = {item.normalized_name for item in recipe.ingredients}
        instructions = "".join(step.instruction for step in recipe.steps)
        if ingredient_names & {"鸡肉", "鸡腿", "鸡翅"} and not any(
            cue in instructions for cue in ("74", "熟透", "无血水", "完全变白")
        ):
            concerns.append("POULTRY_DONENESS_UNCLEAR")
        if any("鱼" in name for name in ingredient_names) and not any(
            cue in instructions for cue in ("63", "熟透", "鱼肉变白", "轻易剥离")
        ):
            concerns.append("FISH_DONENESS_UNCLEAR")
        return concerns

    @staticmethod
    def _suspected_near_duplicates(recipes: list[RecipeV1]) -> list[list[str]]:
        pairs = []
        for index, left in enumerate(recipes):
            left_ingredients = {item.ingredient_id for item in left.ingredients}
            for right in recipes[index + 1 :]:
                if left.identity.category != right.identity.category:
                    continue
                right_ingredients = {item.ingredient_id for item in right.ingredients}
                union = left_ingredients | right_ingredients
                ingredient_similarity = (
                    len(left_ingredients & right_ingredients) / len(union)
                    if union
                    else 1.0
                )
                name_similarity = SequenceMatcher(
                    None, left.identity.name, right.identity.name
                ).ratio()
                if ingredient_similarity >= 0.65 and name_similarity >= 0.6:
                    pairs.append([left.identity.name, right.identity.name])
        return pairs[:20]

    @staticmethod
    def _retrieval_comparison(
        codex_recipes: list[RecipeV1],
        step_recipes: list[RecipeV1],
        work_parent: Path,
    ) -> RetrievalComparison:
        runner = RecipeRetrievalEvaluationRunner()
        root = work_parent / f"_retrieval_work_{uuid4().hex}"
        root.mkdir(parents=True, exist_ok=False)
        try:
            current_path = root / "current.jsonl"
            combined_path = root / "combined.jsonl"
            current_path.write_text(
                "".join(recipe.model_dump_json() + "\n" for recipe in codex_recipes),
                encoding="utf-8",
            )
            combined = [*codex_recipes, *step_recipes]
            combined_path.write_text(
                "".join(recipe.model_dump_json() + "\n" for recipe in combined),
                encoding="utf-8",
            )
            current_run = runner.run(current_path, root / "current-output")
            combined_run = runner.run(combined_path, root / "combined-output")
        finally:
            shutil.rmtree(root, ignore_errors=True)
        step_recipe_ids = {recipe.recipe_id for recipe in step_recipes}
        return RetrievalComparison(
            current_100_recipe_count=len(codex_recipes),
            combined_recipe_count=len(combined),
            current_100=current_run.metrics.hybrid,
            combined=combined_run.metrics.hybrid,
            average_new_recipe_top_5_share=round(
                mean(
                    sum(
                        hit.recipe_id in step_recipe_ids
                        for hit in result.hybrid_top_k
                    )
                    / 5
                    for result in combined_run.results
                ),
                4,
            ),
            queries_with_new_recipe_in_top_5=sum(
                any(
                    hit.recipe_id in step_recipe_ids
                    for hit in result.hybrid_top_k
                )
                for result in combined_run.results
            ),
            queries_with_three_or_more_new_recipes_in_top_5=sum(
                sum(
                    hit.recipe_id in step_recipe_ids
                    for hit in result.hybrid_top_k
                )
                >= 3
                for result in combined_run.results
            ),
            combined_failed_queries=[
                result.query_id
                for result in combined_run.results
                if result.hybrid_reciprocal_rank == 0
            ],
            qrel_warning=(
                "The fixed relevance labels contain only first-batch recipe IDs. "
                "New Step recipes in top-k are unjudged, so metric decreases mix "
                "real ranking displacement with incomplete relevance judgments."
            ),
        )

    @staticmethod
    def _recommendation_basis(
        codex: DatasetQualitySnapshot,
        step: DatasetQualitySnapshot,
        retrieval: RetrievalComparison,
    ) -> list[str]:
        return [
            f"Step schema pass rate: {step.schema_pass_rate:.4f}",
            f"Step validation pass rate: {step.validation_pass_rate:.4f}",
            f"Step culinary audit pass rate: {(step.culinary_audit_pass_rate or 0):.4f}",
            (
                "Combined retrieval MRR delta: "
                f"{retrieval.combined.mrr - retrieval.current_100.mrr:+.4f}"
            ),
            (
                "Average quality delta vs Codex: "
                f"{(step.average_quality_score or 0) - (codex.average_quality_score or 0):+.4f}"
            ),
        ]

    @staticmethod
    def _atomic_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
