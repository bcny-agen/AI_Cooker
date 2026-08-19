from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from recipe_pipeline.export import DatasetExporter
from recipe_pipeline.generation import AIOutputError, FixtureRecipeGenerator
from recipe_pipeline.pipeline import RecipeDatasetPipeline
from recipe_pipeline.quality import RecipeQualityScorer
from recipe_pipeline.schemas.recipe import RecipeCategory, RecipeStatus
from recipe_pipeline.sources import ManualRecipeSource, PublicDatasetSource, SyntheticRecipeSource
from recipe_pipeline.tests.helpers import normalized_recipe, raw_recipe
from recipe_pipeline.validation import DuplicateDetector, IssueSeverity, RecipeValidator, ValidationIssue


class ValidationQualityPipelineTests(unittest.TestCase):
    def test_valid_recipe_passes_deterministic_validation(self) -> None:
        self.assertEqual(RecipeValidator().validate(normalized_recipe()), [])

    def test_non_consecutive_steps_are_rejected(self) -> None:
        recipe = normalized_recipe()
        second = recipe.steps[1].model_copy(update={"order": 3})
        recipe = recipe.model_copy(update={"steps": [recipe.steps[0], second]})
        codes = {issue.code for issue in RecipeValidator().validate(recipe)}
        self.assertIn("STEP_ORDER_INVALID", codes)

    def test_unsafe_instruction_is_rejected(self) -> None:
        recipe = normalized_recipe(1)
        unsafe = recipe.steps[1].model_copy(
            update={"instruction": "将鸡肉保持生的状态并生吃鸡肉完成测试。"}
        )
        recipe = recipe.model_copy(update={"steps": [recipe.steps[0], unsafe]})
        issues = RecipeValidator().validate(recipe)
        self.assertTrue(any(issue.code == "UNSAFE_COOKING_INSTRUCTION" for issue in issues))

    def test_duplicate_name_is_detected(self) -> None:
        detector = DuplicateDetector()
        first = normalized_recipe()
        detector.register(first)
        duplicate = first.model_copy(update={"recipe_id": normalized_recipe(1).recipe_id})
        self.assertIsNotNone(detector.find(duplicate))

    def test_quality_thresholds_publish_review_and_reject(self) -> None:
        scorer = RecipeQualityScorer()
        recipe = normalized_recipe()
        high_source = recipe.source.model_copy(update={"reliability_score": 1.0})
        published, _ = scorer.score(recipe.model_copy(update={"source": high_source}), [])
        self.assertEqual(published.quality.status, RecipeStatus.PUBLISHED)

        review_source = recipe.source.model_copy(update={"reliability_score": 0.4})
        review, _ = scorer.score(recipe.model_copy(update={"source": review_source}), [])
        self.assertEqual(review.quality.status, RecipeStatus.REVIEW)

        error = ValidationIssue(
            code="UNSAFE_COOKING_INSTRUCTION",
            message="unsafe",
            severity=IssueSeverity.ERROR,
        )
        rejected, _ = scorer.score(recipe.model_copy(update={"source": high_source}), [error])
        self.assertEqual(rejected.quality.status, RecipeStatus.REJECTED)

    def test_pipeline_rejects_second_duplicate_and_keeps_first(self) -> None:
        first = raw_recipe()
        second_source = first.source.model_copy(update={"source_record_id": "duplicate-record"})
        second = first.model_copy(update={"source": second_source})
        result = RecipeDatasetPipeline().run(ManualRecipeSource([first, second]))
        self.assertEqual(result.processed_count, 2)
        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.rejected_count, 1)
        self.assertTrue(
            any(
                issue.code == "DUPLICATE_RECIPE"
                for issue in result.validation_reports[1].issues
            )
        )

    def test_pipeline_catches_invalid_ai_output(self) -> None:
        class _FailingEnhancer:
            def enhance(self, recipe):
                raise AIOutputError("invalid test output")

        result = RecipeDatasetPipeline(enhancer=_FailingEnhancer()).run(
            ManualRecipeSource([raw_recipe()])
        )
        self.assertEqual(result.accepted_count, 0)
        self.assertEqual(result.validation_reports[0].issues[0].code, "RECIPE_TRANSFORM_FAILED")

    def test_invalid_source_record_is_reported_without_stopping_batch(self) -> None:
        invalid = raw_recipe().model_dump(mode="json")
        del invalid["name"]
        valid = raw_recipe(1).model_dump(mode="json")
        result = RecipeDatasetPipeline().run(PublicDatasetSource([invalid, valid]))
        self.assertEqual(result.processed_count, 2)
        self.assertEqual(result.accepted_count, 1)
        self.assertEqual(result.validation_reports[0].issues[0].code, "SOURCE_PARSE_FAILED")

    def test_export_writes_parseable_jsonl_and_reports(self) -> None:
        source = SyntheticRecipeSource(
            FixtureRecipeGenerator(), RecipeCategory.MAIN_DISH, 3
        )
        result = RecipeDatasetPipeline().run(source)
        output_dir = Path(__file__).parent / "_test_output"
        self.addCleanup(shutil.rmtree, output_dir, True)
        artifacts = DatasetExporter().export(
            result,
            output_dir,
            generation_report={"total_requested": 3},
        )
        lines = artifacts.recipes_jsonl.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(json.loads(line)["schema_version"] == "1.0" for line in lines))
        validation = json.loads(artifacts.validation_report.read_text(encoding="utf-8"))
        quality = json.loads(artifacts.quality_report.read_text(encoding="utf-8"))
        self.assertEqual(validation["summary"]["accepted"], 3)
        self.assertEqual(len(quality["items"]), 3)
        self.assertIn("$defs", json.loads(artifacts.recipe_schema.read_text(encoding="utf-8")))
        self.assertEqual(
            json.loads(artifacts.generation_report.read_text(encoding="utf-8"))[
                "total_requested"
            ],
            3,
        )


if __name__ == "__main__":
    unittest.main()
