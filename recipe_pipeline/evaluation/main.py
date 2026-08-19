"""CLI for the Step 17E offline baseline/vector/hybrid evaluation."""

from __future__ import annotations

import argparse
from pathlib import Path

from recipe_pipeline.evaluation.runner import RecipeRetrievalEvaluationRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate recipe retrieval offline")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("recipe_pipeline/output/first_batch_100/recipes.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("recipe_pipeline/evaluation/output"),
    )
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)
    run = RecipeRetrievalEvaluationRunner().run(
        args.dataset, args.output, top_k=args.top_k
    )
    print(
        f"queries={run.metrics.query_count} "
        f"baseline_recall_at_5={run.metrics.baseline.recall_at_5:.4f} "
        f"baseline_mrr={run.metrics.baseline.mrr:.4f} "
        f"hybrid_recall_at_5={run.metrics.hybrid.recall_at_5:.4f} "
        f"hybrid_mrr={run.metrics.hybrid.mrr:.4f} "
        f"hybrid_failed={run.metrics.hybrid.failed_query_count}"
    )
    print(f"output={run.artifacts.metrics.parent.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
