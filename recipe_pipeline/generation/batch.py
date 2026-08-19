"""Controlled first-batch planning, retry orchestration and statistics."""

from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from recipe_pipeline.generation.enhancer import AIOutputError, TextGenerationClient
from recipe_pipeline.generation.generator import LLMRecipeBatchGenerator
from recipe_pipeline.generation.prompt import (
    DatasetSegment,
    RECIPE_GENERATION_PROMPT_VERSION,
    RecipeGenerationPrompt,
)
from recipe_pipeline.schemas.recipe import (
    RawRecipe,
    RecipeCategory,
    RecipeStatus,
    SourceMetadata,
    SourceType,
)

if TYPE_CHECKING:
    from recipe_pipeline.pipeline import PipelineResult


STEP_FLASH_GENERATOR_MODEL = "STEP_3_7_FLASH"
STEP_FLASH_DATASET_VERSION = "step17f_step_flash_batch_200"


class GenerationJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_index: int = Field(ge=1)
    segment: DatasetSegment
    category: RecipeCategory
    count: int = Field(ge=1, le=10)


class GenerationFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    batch_index: int
    segment: DatasetSegment
    requested_count: int
    attempts: int
    error_type: str


class GenerationRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_count: int
    raw_recipes: list[RawRecipe]
    record_segments: dict[str, DatasetSegment]
    requested_distribution: dict[str, int]
    generated_distribution: dict[str, int]
    retry_count: int
    failures: list[GenerationFailure]
    generation_duration_seconds: float


class GenerationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_version: str
    provider: str
    model_name: str
    generator_model: str | None = None
    dataset_version: str | None = None
    generated_at: datetime
    duration_seconds: float
    total_requested: int
    generated_successfully: int
    accepted_count: int
    schema_generation_failures: int
    pipeline_validation_failures: int
    validation_failures: int
    rejected_count: int
    retry_count: int
    duplicate_count: int
    baseline_recipe_count: int
    average_quality_score: float | None
    quality_distribution: dict[str, int]
    requested_category_distribution: dict[str, int]
    generated_category_distribution: dict[str, int]
    accepted_category_distribution: dict[str, int]
    source_type_distribution: dict[str, int]
    human_reviewed_count: int
    generation_failures: list[GenerationFailure]


class GenerationJobRunner(Protocol):
    def generate_job(
        self,
        job: GenerationJob,
        attempt: int,
        avoid_names: tuple[str, ...],
    ) -> list[RawRecipe]: ...


class PromptedLLMGenerationJobRunner:
    """Runs one planned job through the existing LLMRecipeBatchGenerator."""

    def __init__(
        self,
        client: TextGenerationClient,
        *,
        run_id: str,
        generator_model: str | None = None,
        dataset_version: str | None = None,
        imported_at: datetime | None = None,
    ):
        self._client = client
        self._run_id = run_id
        self._generator_model = generator_model
        self._dataset_version = dataset_version
        self._imported_at = imported_at or datetime.now(timezone.utc)

    def generate_job(
        self,
        job: GenerationJob,
        attempt: int,
        avoid_names: tuple[str, ...],
    ) -> list[RawRecipe]:
        prefix = (
            f"{self._run_id}-{job.segment.value.lower()}-{job.batch_index:02d}"
        )
        prompt = RecipeGenerationPrompt(
            segment=job.segment,
            batch_index=job.batch_index,
            attempt=attempt,
            source_record_prefix=prefix,
            avoid_names=avoid_names,
        )
        generator = LLMRecipeBatchGenerator(
            self._client,
            max_batch_size=10,
            prompt_builder=prompt,
        )
        recipes = generator.generate_recipe_batch(job.category, job.count)
        trusted_recipes = []
        for index, recipe in enumerate(recipes, start=1):
            trusted_source = SourceMetadata(
                source_type=SourceType.AI_SYNTHETIC,
                source_name=RECIPE_GENERATION_PROMPT_VERSION,
                source_record_id=f"{prefix}-{index:02d}",
                license="AI-GENERATED-REVIEW-REQUIRED",
                source_url=None,
                reliability_score=0.5,
                generator_model=self._generator_model,
                dataset_version=self._dataset_version,
                imported_at=self._imported_at,
            )
            trusted_recipes.append(
                recipe.model_copy(update={"source": trusted_source})
            )
        return trusted_recipes


class StepFlashGenerationJobRunner(PromptedLLMGenerationJobRunner):
    """Step 17F adapter that owns trusted model and dataset provenance."""

    def __init__(
        self,
        client: TextGenerationClient,
        *,
        run_id: str,
        imported_at: datetime | None = None,
    ):
        super().__init__(
            client,
            run_id=run_id,
            generator_model=STEP_FLASH_GENERATOR_MODEL,
            dataset_version=STEP_FLASH_DATASET_VERSION,
            imported_at=imported_at,
        )


class RetryingGenerationCoordinator:
    """At most two attempts per job; no unbounded retries."""

    def __init__(self, runner: GenerationJobRunner, max_attempts: int = 2):
        if max_attempts != 2:
            raise ValueError("Step 17C requires exactly two maximum attempts")
        self._runner = runner
        self._max_attempts = max_attempts

    def run(
        self,
        jobs: list[GenerationJob],
        *,
        initial_avoid_names: tuple[str, ...] = (),
    ) -> GenerationRunResult:
        started = time.monotonic()
        raw_recipes: list[RawRecipe] = []
        record_segments: dict[str, DatasetSegment] = {}
        retries = 0
        failures: list[GenerationFailure] = []
        avoid_names = list(initial_avoid_names)
        requested_distribution = Counter()
        generated_distribution = Counter()

        for job in jobs:
            requested_distribution[job.segment.value] += job.count
            last_error: Exception | None = None
            for attempt in range(1, self._max_attempts + 1):
                if attempt > 1:
                    retries += 1
                try:
                    generated = self._runner.generate_job(
                        job, attempt, tuple(avoid_names)
                    )
                    if len(generated) != job.count:
                        raise AIOutputError(
                            "generated batch returned an unexpected item count"
                        )
                    raw_recipes.extend(generated)
                    generated_distribution[job.segment.value] += len(generated)
                    for recipe in generated:
                        source_record_id = recipe.source.source_record_id
                        record_segments[source_record_id] = job.segment
                        avoid_names.append(recipe.name)
                    last_error = None
                    break
                except (AIOutputError, ValidationError, ValueError) as exc:
                    last_error = exc
            if last_error is not None:
                failures.append(
                    GenerationFailure(
                        batch_index=job.batch_index,
                        segment=job.segment,
                        requested_count=job.count,
                        attempts=self._max_attempts,
                        error_type=type(last_error).__name__,
                    )
                )

        return GenerationRunResult(
            requested_count=sum(job.count for job in jobs),
            raw_recipes=raw_recipes,
            record_segments=record_segments,
            requested_distribution=dict(requested_distribution),
            generated_distribution=dict(generated_distribution),
            retry_count=retries,
            failures=failures,
            generation_duration_seconds=round(time.monotonic() - started, 3),
        )


class ParallelRetryingGenerationCoordinator:
    """Bounded offline API fan-out; each job still retries at most once."""

    def __init__(
        self,
        runner: GenerationJobRunner,
        *,
        max_workers: int = 4,
        max_attempts: int = 2,
    ):
        if not 1 <= max_workers <= 8:
            raise ValueError("max_workers must be between 1 and 8")
        if max_attempts != 2:
            raise ValueError("Step 17F requires exactly two maximum attempts")
        self._runner = runner
        self._max_workers = max_workers
        self._max_attempts = max_attempts

    def run(
        self,
        jobs: list[GenerationJob],
        *,
        initial_avoid_names: tuple[str, ...] = (),
    ) -> GenerationRunResult:
        started = time.monotonic()
        requested_distribution = Counter()
        for job in jobs:
            requested_distribution[job.segment.value] += job.count

        def execute(job: GenerationJob):
            last_error: Exception | None = None
            retries = 0
            for attempt in range(1, self._max_attempts + 1):
                if attempt > 1:
                    retries += 1
                try:
                    generated = self._runner.generate_job(
                        job, attempt, initial_avoid_names
                    )
                    if len(generated) != job.count:
                        raise AIOutputError(
                            "generated batch returned an unexpected item count"
                        )
                    return job, generated, retries, None
                except (AIOutputError, ValidationError, ValueError) as exc:
                    last_error = exc
            return job, [], retries, last_error

        completed = []
        with ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="step-flash-generation",
        ) as executor:
            futures = {executor.submit(execute, job): job for job in jobs}
            for future in as_completed(futures):
                completed.append(future.result())

        completed.sort(key=lambda item: item[0].batch_index)
        raw_recipes: list[RawRecipe] = []
        record_segments: dict[str, DatasetSegment] = {}
        generated_distribution = Counter()
        failures = []
        retry_count = 0
        for job, generated, retries, error in completed:
            retry_count += retries
            if error is not None:
                failures.append(
                    GenerationFailure(
                        batch_index=job.batch_index,
                        segment=job.segment,
                        requested_count=job.count,
                        attempts=self._max_attempts,
                        error_type=type(error).__name__,
                    )
                )
                continue
            raw_recipes.extend(generated)
            generated_distribution[job.segment.value] += len(generated)
            for recipe in generated:
                record_segments[recipe.source.source_record_id] = job.segment

        return GenerationRunResult(
            requested_count=sum(job.count for job in jobs),
            raw_recipes=raw_recipes,
            record_segments=record_segments,
            requested_distribution=dict(requested_distribution),
            generated_distribution=dict(generated_distribution),
            retry_count=retry_count,
            failures=failures,
            generation_duration_seconds=round(time.monotonic() - started, 3),
        )


def create_first_100_plan() -> list[GenerationJob]:
    """Exact 40/20/15/15/10 distribution in five-recipe jobs."""
    specs = [
        *[(DatasetSegment.CHINESE_HOME, RecipeCategory.MAIN_DISH)] * 8,
        *[(DatasetSegment.QUICK_MEALS, RecipeCategory.MAIN_DISH)] * 2,
        (DatasetSegment.QUICK_MEALS, RecipeCategory.STAPLE),
        (DatasetSegment.QUICK_MEALS, RecipeCategory.BREAKFAST),
        *[(DatasetSegment.HEALTHY_MEALS, RecipeCategory.MAIN_DISH)] * 2,
        (DatasetSegment.HEALTHY_MEALS, RecipeCategory.SIDE_DISH),
        *[(DatasetSegment.BEGINNER_COOKING, RecipeCategory.MAIN_DISH)] * 2,
        (DatasetSegment.BEGINNER_COOKING, RecipeCategory.BREAKFAST),
        (DatasetSegment.AIR_FRYER_SIMPLE_TOOLS, RecipeCategory.MAIN_DISH),
        (DatasetSegment.AIR_FRYER_SIMPLE_TOOLS, RecipeCategory.SNACK),
    ]
    return [
        GenerationJob(
            batch_index=index,
            segment=segment,
            category=category,
            count=5,
        )
        for index, (segment, category) in enumerate(specs, start=1)
    ]


def create_step_flash_200_plan() -> list[GenerationJob]:
    """Exact Step 17F 80/40/30/30/20 distribution in five-recipe jobs."""
    specs = [
        *[(DatasetSegment.CHINESE_HOME, RecipeCategory.MAIN_DISH)] * 16,
        *[(DatasetSegment.QUICK_MEALS, RecipeCategory.MAIN_DISH)] * 4,
        *[(DatasetSegment.QUICK_MEALS, RecipeCategory.STAPLE)] * 2,
        *[(DatasetSegment.QUICK_MEALS, RecipeCategory.BREAKFAST)] * 2,
        *[(DatasetSegment.HEALTHY_MEALS, RecipeCategory.MAIN_DISH)] * 4,
        *[(DatasetSegment.HEALTHY_MEALS, RecipeCategory.SIDE_DISH)] * 2,
        *[(DatasetSegment.BEGINNER_COOKING, RecipeCategory.MAIN_DISH)] * 4,
        *[(DatasetSegment.BEGINNER_COOKING, RecipeCategory.BREAKFAST)] * 2,
        *[(DatasetSegment.AIR_FRYER_SIMPLE_TOOLS, RecipeCategory.MAIN_DISH)] * 2,
        *[(DatasetSegment.AIR_FRYER_SIMPLE_TOOLS, RecipeCategory.SNACK)] * 2,
    ]
    return [
        GenerationJob(
            batch_index=index,
            segment=segment,
            category=category,
            count=5,
        )
        for index, (segment, category) in enumerate(specs, start=1)
    ]


def build_generation_report(
    generation: GenerationRunResult,
    pipeline: "PipelineResult",
    *,
    provider: str,
    model_name: str,
    baseline_recipe_count: int,
    duration_seconds: float,
    generator_model: str | None = None,
    dataset_version: str | None = None,
) -> GenerationReport:
    quality_distribution = Counter(
        report.status.value for report in pipeline.quality_reports
    )
    scores = [report.score for report in pipeline.quality_reports]
    accepted_distribution = Counter()
    for recipe in pipeline.recipes:
        segment = generation.record_segments.get(recipe.source.source_record_id)
        if segment is not None:
            accepted_distribution[segment.value] += 1
    pipeline_validation_failures = sum(
        not report.is_valid for report in pipeline.validation_reports
    )
    schema_generation_failures = sum(
        failure.requested_count for failure in generation.failures
    )
    duplicate_count = sum(
        issue.code == "DUPLICATE_RECIPE"
        for report in pipeline.validation_reports
        for issue in report.issues
    )
    return GenerationReport(
        prompt_version=RECIPE_GENERATION_PROMPT_VERSION,
        provider=provider,
        model_name=model_name,
        generator_model=generator_model,
        dataset_version=dataset_version,
        generated_at=datetime.now(timezone.utc),
        duration_seconds=round(duration_seconds, 3),
        total_requested=generation.requested_count,
        generated_successfully=len(generation.raw_recipes),
        accepted_count=pipeline.accepted_count,
        schema_generation_failures=schema_generation_failures,
        pipeline_validation_failures=pipeline_validation_failures,
        validation_failures=schema_generation_failures + pipeline_validation_failures,
        rejected_count=generation.requested_count - pipeline.accepted_count,
        retry_count=generation.retry_count,
        duplicate_count=duplicate_count,
        baseline_recipe_count=baseline_recipe_count,
        average_quality_score=(round(sum(scores) / len(scores), 4) if scores else None),
        quality_distribution=dict(quality_distribution),
        requested_category_distribution=generation.requested_distribution,
        generated_category_distribution=generation.generated_distribution,
        accepted_category_distribution=dict(accepted_distribution),
        source_type_distribution={
            SourceType.AI_SYNTHETIC.value: pipeline.accepted_count
        },
        human_reviewed_count=sum(
            recipe.quality.human_reviewed for recipe in pipeline.recipes
        ),
        generation_failures=generation.failures,
    )
