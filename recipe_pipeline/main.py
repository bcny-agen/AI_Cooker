"""Command-line entry point for offline pipeline development."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

from recipe_pipeline.config import PipelineSettings
from recipe_pipeline.export import DatasetExporter
from recipe_pipeline.generation import (
    CODEX_GENERATION_MODEL,
    CODEX_GENERATION_PROVIDER,
    CodexAuthoredGenerationJobRunner,
    FixtureRecipeGenerator,
    OpenAICompatibleTextClient,
    ParallelRetryingGenerationCoordinator,
    PromptedLLMGenerationJobRunner,
    STEP_FLASH_DATASET_VERSION,
    STEP_FLASH_GENERATOR_MODEL,
    StepFlashGenerationJobRunner,
    RetryingGenerationCoordinator,
    build_generation_report,
    create_first_100_plan,
    create_step_flash_200_plan,
)
from recipe_pipeline.pipeline import RecipeDatasetPipeline
from recipe_pipeline.schemas.recipe import RecipeCategory
from recipe_pipeline.sources import ManualRecipeSource, SyntheticRecipeSource, load_recipe_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI_Cooker offline recipe pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo", help="generate up to ten local test records")
    demo.add_argument("--count", type=int, default=10)
    demo.add_argument("--output", type=Path)
    schema = subparsers.add_parser("export-schema", help="export Recipe Schema v1")
    schema.add_argument("--output", type=Path)
    generate = subparsers.add_parser(
        "generate-first-batch",
        help="generate the controlled first 100-recipe AI batch",
    )
    generate.add_argument("--count", type=int, default=100)
    generate.add_argument(
        "--output",
        type=Path,
        default=Path("recipe_pipeline/output/first_batch_100"),
    )
    step_flash = subparsers.add_parser(
        "generate-step-flash-batch",
        help="generate the isolated Step 3.7 Flash 200-recipe experiment",
    )
    step_flash.add_argument("--count", type=int, default=200)
    step_flash.add_argument(
        "--output",
        type=Path,
        default=Path("recipe_pipeline/output/step_flash_batch_200"),
    )
    step_flash.add_argument(
        "--baseline",
        type=Path,
        default=Path("recipe_pipeline/output/first_batch_100/recipes.jsonl"),
    )
    golden = subparsers.add_parser(
        "build-golden-dataset",
        help="build the reviewed offline Golden Recipe Dataset v1",
    )
    golden.add_argument("--count", type=int, default=500)
    golden.add_argument(
        "--output",
        type=Path,
        default=Path("recipe_pipeline/output/golden_500"),
    )
    generate.add_argument(
        "--generator",
        choices=("codex-direct", "configured-llm"),
        default="codex-direct",
    )
    generate.add_argument(
        "--baseline",
        type=Path,
        default=Path("recipe_pipeline/output/recipes.jsonl"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = PipelineSettings.from_environment()
    output_dir = args.output or settings.output_dir

    if args.command == "demo":
        if not 1 <= args.count <= settings.max_batch_size:
            raise SystemExit(f"--count must be between 1 and {settings.max_batch_size}")
        source = SyntheticRecipeSource(
            FixtureRecipeGenerator(), RecipeCategory.MAIN_DISH, args.count
        )
        result = RecipeDatasetPipeline().run(source)
        artifacts = DatasetExporter().export(result, output_dir)
        print(
            f"processed={result.processed_count} accepted={result.accepted_count} "
            f"rejected={result.rejected_count}"
        )
        print(f"output={artifacts.recipes_jsonl.parent.resolve()}")
        return 0 if result.rejected_count == 0 else 1

    if args.command == "build-golden-dataset":
        from recipe_pipeline.golden import GoldenDatasetBuilder

        report = GoldenDatasetBuilder().build(args.output, requested_count=args.count)
        generation = report["generation"]
        holdout = report["retrieval"]["holdout"]["metrics"]
        print(
            f"requested={generation['requested']} generated={generation['generated']} "
            f"golden={generation['final_golden_count']} "
            f"holdout_recall_at_5={holdout['recall_at_5']}"
        )
        print(f"output={Path(report['output_dir'])}")
        return 0

    if args.command in {"generate-first-batch", "generate-step-flash-batch"}:
        is_step_flash = args.command == "generate-step-flash-batch"
        if is_step_flash and args.count != 200:
            raise SystemExit("Step 17F supports exactly --count 200")
        if args.count != 100:
            if not is_step_flash:
                raise SystemExit("Step 17C supports exactly --count 100")
        if not args.baseline.is_file():
            raise SystemExit(f"duplicate baseline not found: {args.baseline}")

        started = time.monotonic()
        baseline = load_recipe_jsonl(args.baseline)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if is_step_flash:
            if not settings.llm_available:
                raise SystemExit(
                    "Step Flash generation requires MODEL_NAME/API_KEY/LLM_BASE_URL"
                )
            if settings.model_name != "step-3.7-flash":
                raise SystemExit("MODEL_NAME must be step-3.7-flash for Step 17F")
            client = OpenAICompatibleTextClient(
                api_key=settings.api_key or "",
                base_url=settings.base_url or "",
                model_name=settings.model_name,
                timeout_seconds=settings.request_timeout_seconds,
                max_output_tokens=settings.max_output_tokens,
                temperature=settings.temperature,
            )
            runner = StepFlashGenerationJobRunner(client, run_id=run_id)
            report_provider = settings.llm_provider or "openai-compatible"
            report_model = settings.model_name
            plan = create_step_flash_200_plan()
        elif args.generator == "codex-direct":
            runner = CodexAuthoredGenerationJobRunner(run_id=run_id)
            report_provider = CODEX_GENERATION_PROVIDER
            report_model = CODEX_GENERATION_MODEL
            plan = create_first_100_plan()
        else:
            if not settings.llm_available:
                raise SystemExit(
                    "LLM generation is not configured; set MODEL_NAME/API_KEY/LLM_BASE_URL "
                    "or the compatible MODEL_* variables."
                )
            client = OpenAICompatibleTextClient(
                api_key=settings.api_key or "",
                base_url=settings.base_url or "",
                model_name=settings.model_name or "",
                timeout_seconds=settings.request_timeout_seconds,
                max_output_tokens=settings.max_output_tokens,
                temperature=settings.temperature,
            )
            runner = PromptedLLMGenerationJobRunner(client, run_id=run_id)
            report_provider = settings.llm_provider or "openai-compatible"
            report_model = settings.model_name or "unconfigured"
            plan = create_first_100_plan()
        coordinator = (
            ParallelRetryingGenerationCoordinator(runner, max_workers=4)
            if is_step_flash
            else RetryingGenerationCoordinator(runner)
        )
        generation = coordinator.run(
            plan,
            initial_avoid_names=tuple(recipe.identity.name for recipe in baseline),
        )
        result = RecipeDatasetPipeline().run(
            ManualRecipeSource(generation.raw_recipes),
            baseline_recipes=baseline,
        )
        report = build_generation_report(
            generation,
            result,
            provider=report_provider,
            model_name=report_model,
            baseline_recipe_count=len(baseline),
            duration_seconds=time.monotonic() - started,
            generator_model=(STEP_FLASH_GENERATOR_MODEL if is_step_flash else None),
            dataset_version=(
                STEP_FLASH_DATASET_VERSION if is_step_flash else None
            ),
        )
        artifacts = DatasetExporter().export(
            result,
            args.output,
            generation_report=report.model_dump(mode="json"),
        )
        if is_step_flash:
            from recipe_pipeline.evaluation.dataset_quality import (
                StepFlashExperimentEvaluator,
            )

            StepFlashExperimentEvaluator().evaluate(
                codex_dir=args.baseline.parent,
                step_flash_dir=args.output,
                output_path=args.output / "evaluation_report.json",
            )
        print(
            f"requested={report.total_requested} generated={report.generated_successfully} "
            f"accepted={report.accepted_count} rejected={report.rejected_count} "
            f"retries={report.retry_count}"
        )
        print(f"output={artifacts.recipes_jsonl.parent.resolve()}")
        return 0

    from recipe_pipeline.schemas.export_schema import export_recipe_json_schema

    schema_path = args.output or output_dir / "recipe_schema_v1.json"
    written = export_recipe_json_schema(schema_path)
    print(f"schema={written.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
