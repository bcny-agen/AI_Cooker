from __future__ import annotations

import argparse
import json
from pathlib import Path

from recipe_pipeline.evaluation.embedding_benchmark import (
    DEFAULT_DATASET,
    DEFAULT_OUTPUT,
    run_embedding_benchmark,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Step 17H embedding benchmark")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = run_embedding_benchmark(args.dataset, args.output)
    print(json.dumps(result["recommendation"], ensure_ascii=False))
    print(f"output={result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
