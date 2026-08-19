"""Command-line entry point for controlled, reproducible Agent evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from app.config.settings import Settings
from app.models.registry import ModelId
from app.tools.recipe_search import RecipeKBRuntime
from recipe_pipeline.agent_eval.dataset import build_evaluation_dataset
from recipe_pipeline.agent_eval.models import EvaluationStrategy
from recipe_pipeline.agent_eval.reporting import export_all, write_json
from recipe_pipeline.agent_eval.runner import run_strategy
from recipe_pipeline.agent_eval.scoring import score_turn


DEFAULT_OUTPUT = Path("recipe_pipeline/output/agent_rag_evaluation")


def stratified_ids(dataset, count: int) -> list[str]:
    """Round-robin over categories, holdout first, without random sampling."""

    if not 1 <= count <= len(dataset.scenarios):
        raise ValueError("live pair count must be between 1 and dataset size")
    categories = sorted({scenario.category for scenario in dataset.scenarios})
    buckets = {
        category: [
            scenario.scenario_id
            for scenario in dataset.scenarios
            if scenario.category == category and scenario.split == "holdout"
        ] + [
            scenario.scenario_id
            for scenario in dataset.scenarios
            if scenario.category == category and scenario.split == "development"
        ]
        for category in categories
    }
    selected: list[str] = []
    offset = 0
    while len(selected) < count:
        progressed = False
        for category in categories:
            if offset < len(buckets[category]) and len(selected) < count:
                selected.append(buckets[category][offset])
                progressed = True
        if not progressed:
            break
        offset += 1
    return selected


def _unexecuted_run(dataset, strategy: EvaluationStrategy, ids: list[str], reason: str) -> dict:
    return {
        "run_metadata": {
            "strategy": strategy.value,
            "model_id": ModelId.STEP_FLASH_3_7.value,
            "dataset_version": dataset.dataset_version,
            "dataset_size": len(dataset.scenarios),
            "executed_scenario_count": 0,
            "executed_turn_count": 0,
            "execution_scope": "not_executed",
            "selected_scenario_ids": ids,
            "reason": reason,
            "production_behavior_changed": False,
            "judge_kind": "deterministic_proxy",
        },
        "scenarios": [],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--live-pairs", type=int, default=24)
    parser.add_argument("--dataset-only", action="store_true")
    parser.add_argument(
        "--rescore-existing",
        action="store_true",
        help="Reapply the current deterministic rubric to saved raw traces only.",
    )
    parser.add_argument(
        "--strategy",
        choices=("both", "legacy", "rag"),
        default="both",
        help="Resume one missing strategy without overwriting the other result.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset = build_evaluation_dataset()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "evaluation_dataset.json", dataset.model_dump(mode="json"))
    if args.dataset_only:
        print(json.dumps({"dataset_size": len(dataset.scenarios), "output": str(args.output_dir)}, ensure_ascii=False))
        return 0

    settings = Settings.from_env()
    selected_ids = stratified_ids(dataset, args.live_pairs)
    legacy_path = args.output_dir / "legacy_results.json"
    rag_path = args.output_dir / "rag_results.json"
    if args.rescore_existing:
        if not legacy_path.exists() or not rag_path.exists():
            raise FileNotFoundError("Both saved strategy result files are required")
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        rag = json.loads(rag_path.read_text(encoding="utf-8"))
        for run, strategy in (
            (legacy, EvaluationStrategy.LEGACY_WEB_FIRST),
            (rag, EvaluationStrategy.RECIPE_RAG_FIRST),
        ):
            for scenario in run["scenarios"]:
                scenario_definition = next(
                    item for item in dataset.scenarios
                    if item.scenario_id == scenario["scenario_id"]
                )
                turn_scores = []
                for index, turn in enumerate(scenario["turns"]):
                    expected = scenario_definition.turns[index].expected
                    turn["expected"] = expected.model_dump(mode="json")
                    turn["score"] = score_turn(
                        turn["answer"],
                        turn["tool_calls"],
                        expected,
                        strategy,
                    )
                    if turn.get("error"):
                        turn["score"]["score"] = 0.0
                        turn["score"]["scenario_pass"] = False
                    turn_scores.append(turn["score"])
                critical = any(score["critical_hard_constraint_violation"] for score in turn_scores)
                scenario["score"] = 0.0 if critical else round(
                    sum(score["score"] for score in turn_scores) / len(turn_scores),
                    2,
                )
                scenario["scenario_pass"] = (
                    not critical
                    and scenario.get("error_count", 0) == 0
                    and all(score["scenario_pass"] for score in turn_scores)
                )
        export_all(args.output_dir, dataset, legacy, rag, settings)
        print(json.dumps({
            "dataset_size": len(dataset.scenarios),
            "rescored_existing": True,
            "output": str(args.output_dir),
        }, ensure_ascii=False))
        return 0
    legacy = _unexecuted_run(dataset, EvaluationStrategy.LEGACY_WEB_FIRST, selected_ids, "strategy not selected")
    rag = _unexecuted_run(dataset, EvaluationStrategy.RECIPE_RAG_FIRST, selected_ids, "strategy not selected")
    if legacy_path.exists() and args.strategy == "rag":
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    if rag_path.exists() and args.strategy == "legacy":
        rag = json.loads(rag_path.read_text(encoding="utf-8"))

    runtime = RecipeKBRuntime(settings).start()
    try:
        if args.strategy in {"both", "legacy"}:
            legacy = run_strategy(settings, runtime, dataset, selected_ids, EvaluationStrategy.LEGACY_WEB_FIRST)
            write_json(legacy_path, legacy)
        if args.strategy in {"both", "rag"}:
            rag = run_strategy(settings, runtime, dataset, selected_ids, EvaluationStrategy.RECIPE_RAG_FIRST)
            write_json(rag_path, rag)
    finally:
        runtime.close()
    export_all(args.output_dir, dataset, legacy, rag, settings)
    print(json.dumps({
        "dataset_size": len(dataset.scenarios),
        "live_paired_scenarios": min(legacy["run_metadata"]["executed_scenario_count"], rag["run_metadata"]["executed_scenario_count"]),
        "output": str(args.output_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
