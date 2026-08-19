from __future__ import annotations

import argparse
import json
from pathlib import Path

from recipe_pipeline.recipe_kb.benchmark import run_postgres_benchmark
from recipe_pipeline.recipe_kb.config import RecipeKBConfig
from recipe_pipeline.recipe_kb.database import apply_migrations, readiness
from recipe_pipeline.recipe_kb.importer import GoldenDatasetImporter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recipe PostgreSQL + pgvector KB")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    sub.add_parser("ready")
    importer = sub.add_parser("import")
    importer.add_argument("--dataset", type=Path, default=Path("recipe_pipeline/output/golden_500/recipes.jsonl"))
    importer.add_argument("--version", default="golden_500_v1")
    validate = sub.add_parser("validate")
    validate.add_argument("--version", default="golden_500_v1")
    activate = sub.add_parser("activate")
    activate.add_argument("--version", default="golden_500_v1")
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--output", type=Path, default=Path("recipe_pipeline/output/recipe_kb"))
    args = parser.parse_args(argv)
    config = RecipeKBConfig.from_env()
    if args.command == "migrate":
        result = apply_migrations(config)
    elif args.command == "ready":
        result = readiness(config)
    elif args.command == "import":
        result = GoldenDatasetImporter.report_dict(
            GoldenDatasetImporter(config).import_dataset(args.dataset, version_key=args.version)
        )
    elif args.command == "validate":
        GoldenDatasetImporter(config).validate_dataset(args.version)
        result = {"validated": args.version, "activated": False}
    elif args.command == "activate":
        GoldenDatasetImporter(config).activate_dataset(args.version)
        result = {"activated": args.version}
    else:
        result = run_postgres_benchmark(config, output_dir=args.output)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
