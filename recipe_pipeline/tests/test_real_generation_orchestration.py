from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from recipe_pipeline.generation import (
    AIOutputError,
    CodexAuthoredGenerationJobRunner,
    DatasetSegment,
    GenerationJob,
    LLMRecipeBatchGenerator,
    ParallelRetryingGenerationCoordinator,
    PromptedLLMGenerationJobRunner,
    RECIPE_GENERATION_PROMPT_VERSION,
    RecipeGenerationPrompt,
    RetryingGenerationCoordinator,
    STEP_FLASH_DATASET_VERSION,
    STEP_FLASH_GENERATOR_MODEL,
    StepFlashGenerationJobRunner,
    build_generation_report,
    create_first_100_plan,
    create_step_flash_200_plan,
)
from recipe_pipeline.evaluation.dataset_quality import StepFlashExperimentEvaluator
from recipe_pipeline.export import DatasetExporter
from recipe_pipeline.pipeline import RecipeDatasetPipeline
from recipe_pipeline.schemas.recipe import RecipeCategory, SourceType
from recipe_pipeline.sources import ManualRecipeSource
from recipe_pipeline.tests.helpers import normalized_recipe, raw_recipe


class _StaticClient:
    def __init__(self, output: str):
        self.output = output

    def complete(self, prompt: str) -> str:
        return self.output


class _FailOnceRunner:
    def __init__(self):
        self.calls = 0

    def generate_job(self, job, attempt, avoid_names):
        self.calls += 1
        if self.calls == 1:
            raise AIOutputError("malformed fixture")
        return [raw_recipe()]


class RealGenerationOrchestrationTests(unittest.TestCase):
    def test_prompt_is_versioned_strict_and_segment_specific(self) -> None:
        prompt = RecipeGenerationPrompt(
            segment=DatasetSegment.QUICK_MEALS,
            batch_index=1,
            attempt=1,
            source_record_prefix="test-quick-01",
            avoid_names=("番茄炒鸡蛋",),
        ).build(RecipeCategory.MAIN_DISH, 5)
        self.assertIn(RECIPE_GENERATION_PROMPT_VERSION, prompt)
        self.assertIn('"recipes"', prompt)
        self.assertIn("exactly 5 recipes", prompt)
        self.assertIn("total_minutes <= 30", prompt)
        self.assertIn("CONTROLLED_INGREDIENT_NAMES", prompt)
        self.assertIn("番茄", prompt)
        self.assertIn("additional object fields", prompt)
        self.assertIn("Omit source.imported_at", prompt)
        self.assertIn("Never emit null for imported_at", prompt)
        self.assertNotIn("API_KEY", prompt)

    def test_schema_invalid_ai_json_is_rejected(self) -> None:
        invalid = {"recipes": [{"name": "缺少绝大多数字段"}]}
        generator = LLMRecipeBatchGenerator(
            _StaticClient(json.dumps(invalid, ensure_ascii=False))
        )
        with self.assertRaises(AIOutputError):
            generator.generate_recipe_batch(RecipeCategory.MAIN_DISH, 1)

    def test_failed_generation_is_regenerated_once(self) -> None:
        runner = _FailOnceRunner()
        job = GenerationJob(
            batch_index=1,
            segment=DatasetSegment.CHINESE_HOME,
            category=RecipeCategory.MAIN_DISH,
            count=1,
        )
        result = RetryingGenerationCoordinator(runner).run([job])
        self.assertEqual(runner.calls, 2)
        self.assertEqual(result.retry_count, 1)
        self.assertEqual(len(result.raw_recipes), 1)
        self.assertEqual(result.failures, [])

    def test_prompted_runner_replaces_ai_provenance(self) -> None:
        payload = {"recipes": [raw_recipe().model_dump(mode="json")]}
        runner = PromptedLLMGenerationJobRunner(
            _StaticClient(json.dumps(payload, ensure_ascii=False)),
            run_id="unit-test",
        )
        job = GenerationJob(
            batch_index=1,
            segment=DatasetSegment.CHINESE_HOME,
            category=RecipeCategory.MAIN_DISH,
            count=1,
        )
        generated = runner.generate_job(job, 1, ())
        self.assertEqual(generated[0].source.source_type, SourceType.AI_SYNTHETIC)
        self.assertEqual(generated[0].source.source_name, RECIPE_GENERATION_PROMPT_VERSION)
        self.assertTrue(generated[0].source.source_record_id.startswith("unit-test-"))
        self.assertFalse(hasattr(generated[0], "quality"))

    def test_first_batch_plan_has_exact_distribution(self) -> None:
        plan = create_first_100_plan()
        distribution = {}
        for job in plan:
            distribution[job.segment.value] = distribution.get(job.segment.value, 0) + job.count
        self.assertEqual(
            distribution,
            {
                "CHINESE_HOME": 40,
                "QUICK_MEALS": 20,
                "HEALTHY_MEALS": 15,
                "BEGINNER_COOKING": 15,
                "AIR_FRYER_SIMPLE_TOOLS": 10,
            },
        )

    def test_step_flash_plan_has_exact_distribution(self) -> None:
        plan = create_step_flash_200_plan()
        distribution = {}
        for job in plan:
            distribution[job.segment.value] = distribution.get(job.segment.value, 0) + job.count
        self.assertEqual(len(plan), 40)
        self.assertEqual(
            distribution,
            {
                "CHINESE_HOME": 80,
                "QUICK_MEALS": 40,
                "HEALTHY_MEALS": 30,
                "BEGINNER_COOKING": 30,
                "AIR_FRYER_SIMPLE_TOOLS": 20,
            },
        )

    def test_step_flash_adapter_preserves_trusted_metadata(self) -> None:
        payload = {"recipes": [raw_recipe().model_dump(mode="json")]}
        runner = StepFlashGenerationJobRunner(
            _StaticClient(json.dumps(payload, ensure_ascii=False)),
            run_id="step-flash-unit",
        )
        job = GenerationJob(
            batch_index=1,
            segment=DatasetSegment.CHINESE_HOME,
            category=RecipeCategory.MAIN_DISH,
            count=1,
        )
        recipe = runner.generate_job(job, 1, ())[0]
        self.assertEqual(recipe.source.generator_model, STEP_FLASH_GENERATOR_MODEL)
        self.assertEqual(recipe.source.dataset_version, STEP_FLASH_DATASET_VERSION)
        self.assertEqual(recipe.source.source_type, SourceType.AI_SYNTHETIC)

    def test_step_flash_malformed_output_retries_once_then_reports_failure(self) -> None:
        runner = StepFlashGenerationJobRunner(
            _StaticClient("not-json"), run_id="step-flash-malformed"
        )
        job = GenerationJob(
            batch_index=1,
            segment=DatasetSegment.CHINESE_HOME,
            category=RecipeCategory.MAIN_DISH,
            count=1,
        )
        generation = RetryingGenerationCoordinator(runner).run([job])
        self.assertEqual(generation.retry_count, 1)
        self.assertEqual(generation.raw_recipes, [])
        self.assertEqual(generation.failures[0].requested_count, 1)

    def test_step_flash_parallel_batch_statistics(self) -> None:
        payload = {"recipes": [raw_recipe().model_dump(mode="json")]}
        runner = StepFlashGenerationJobRunner(
            _StaticClient(json.dumps(payload, ensure_ascii=False)),
            run_id="step-flash-parallel",
        )
        jobs = [
            GenerationJob(
                batch_index=index,
                segment=segment,
                category=RecipeCategory.MAIN_DISH,
                count=1,
            )
            for index, segment in enumerate(
                (DatasetSegment.CHINESE_HOME, DatasetSegment.QUICK_MEALS), start=1
            )
        ]
        generation = ParallelRetryingGenerationCoordinator(
            runner, max_workers=2
        ).run(jobs)
        self.assertEqual(generation.requested_count, 2)
        self.assertEqual(len(generation.raw_recipes), 2)
        self.assertEqual(generation.retry_count, 0)
        self.assertEqual(
            generation.generated_distribution,
            {"CHINESE_HOME": 1, "QUICK_MEALS": 1},
        )

    def test_codex_first_batch_all_records_pass_pipeline(self) -> None:
        generation = RetryingGenerationCoordinator(
            CodexAuthoredGenerationJobRunner(run_id="unit-codex-batch")
        ).run(create_first_100_plan())
        result = RecipeDatasetPipeline().run(
            ManualRecipeSource(generation.raw_recipes),
            baseline_recipes=[normalized_recipe()],
        )
        self.assertEqual(generation.requested_count, 100)
        self.assertEqual(len(generation.raw_recipes), 100)
        self.assertEqual(result.accepted_count, 100)
        self.assertEqual(len({recipe.identity.name for recipe in result.recipes}), 100)
        self.assertTrue(
            all(recipe.source.source_type == SourceType.AI_SYNTHETIC for recipe in result.recipes)
        )
        self.assertTrue(all(not recipe.quality.human_reviewed for recipe in result.recipes))

    def test_baseline_duplicate_is_reported_and_rejected(self) -> None:
        candidate = raw_recipe()
        new_source = candidate.source.model_copy(update={"source_record_id": "new-copy"})
        candidate = candidate.model_copy(update={"source": new_source})
        result = RecipeDatasetPipeline().run(
            ManualRecipeSource([candidate]),
            baseline_recipes=[normalized_recipe()],
        )
        self.assertEqual(result.accepted_count, 0)
        self.assertTrue(
            any(
                issue.code == "DUPLICATE_RECIPE"
                for issue in result.validation_reports[0].issues
            )
        )

    def test_generation_report_contains_quality_and_batch_statistics(self) -> None:
        runner = _FailOnceRunner()
        job = GenerationJob(
            batch_index=1,
            segment=DatasetSegment.CHINESE_HOME,
            category=RecipeCategory.MAIN_DISH,
            count=1,
        )
        generation = RetryingGenerationCoordinator(runner).run([job])
        pipeline = RecipeDatasetPipeline().run(
            ManualRecipeSource(generation.raw_recipes)
        )
        report = build_generation_report(
            generation,
            pipeline,
            provider="test-provider",
            model_name="test-model",
            baseline_recipe_count=10,
            duration_seconds=1.25,
        )
        self.assertEqual(report.total_requested, 1)
        self.assertEqual(report.generated_successfully, 1)
        self.assertEqual(report.accepted_count, 1)
        self.assertEqual(report.retry_count, 1)
        self.assertIsNotNone(report.average_quality_score)
        self.assertEqual(sum(report.quality_distribution.values()), 1)

    def test_step_flash_comparison_report_is_exported(self) -> None:
        raw = raw_recipe()
        codex_pipeline = RecipeDatasetPipeline().run(ManualRecipeSource([raw]))
        step_source = raw.source.model_copy(
            update={
                "source_record_id": "step-record",
                "generator_model": STEP_FLASH_GENERATOR_MODEL,
                "dataset_version": STEP_FLASH_DATASET_VERSION,
            }
        )
        step_pipeline = RecipeDatasetPipeline().run(
            ManualRecipeSource([raw.model_copy(update={"source": step_source})])
        )
        root = Path(__file__).parent / "_step17f_comparison_output"
        self.addCleanup(shutil.rmtree, root, True)
        root.mkdir(parents=True, exist_ok=True)
        codex_dir = root / "codex"
        step_dir = root / "step"
        codex_generation = RetryingGenerationCoordinator(_FailOnceRunner()).run(
            [
                GenerationJob(
                    batch_index=1,
                    segment=DatasetSegment.CHINESE_HOME,
                    category=RecipeCategory.MAIN_DISH,
                    count=1,
                )
            ]
        )
        codex_report = build_generation_report(
            codex_generation,
            codex_pipeline,
            provider="codex-test",
            model_name="codex-test",
            baseline_recipe_count=0,
            duration_seconds=0.1,
        )
        step_report = build_generation_report(
            codex_generation,
            step_pipeline,
            provider="step-test",
            model_name="step-3.7-flash",
            baseline_recipe_count=1,
            duration_seconds=0.1,
            generator_model=STEP_FLASH_GENERATOR_MODEL,
            dataset_version=STEP_FLASH_DATASET_VERSION,
        )
        DatasetExporter().export(
            codex_pipeline,
            codex_dir,
            generation_report=codex_report.model_dump(mode="json"),
        )
        DatasetExporter().export(
            step_pipeline,
            step_dir,
            generation_report=step_report.model_dump(mode="json"),
        )
        output = step_dir / "evaluation_report.json"
        report = StepFlashExperimentEvaluator().evaluate(
            codex_dir=codex_dir,
            step_flash_dir=step_dir,
            output_path=output,
        )
        self.assertTrue(output.is_file())
        self.assertEqual(report.step_flash_dataset.accepted_count, 1)
        self.assertEqual(
            report.step_flash_dataset.generator_metadata_preserved_count, 1
        )


if __name__ == "__main__":
    unittest.main()
