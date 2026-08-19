"""Aggregate paired results and export the required Step 17K artifacts."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean, median
from typing import Any

from app.models.registry import ModelId, build_model_definitions
from app.config.settings import Settings
from recipe_pipeline.agent_eval.models import EvaluationDataset, JUDGE_VERSION, SCORING_VERSION


ARTIFACT_NAMES = (
    "evaluation_dataset.json",
    "legacy_results.json",
    "rag_results.json",
    "comparison_metrics.json",
    "failure_analysis.json",
    "tool_usage_report.json",
    "latency_report.json",
    "human_agent_eval_sample.json",
    "model_comparison.json",
    "final_recommendation.json",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _turns(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [turn for scenario in run.get("scenarios", []) for turn in scenario.get("turns", [])]


def _scenario_map(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["scenario_id"]: item for item in run.get("scenarios", [])}


def _mean(values: list[float | int | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return round(mean(valid), 3) if valid else None


def _median(values: list[float | int | None]) -> float | None:
    valid = [float(value) for value in values if value is not None]
    return round(median(valid), 3) if valid else None


def _strategy_metrics(run: dict[str, Any]) -> dict[str, Any]:
    scenarios = run.get("scenarios", [])
    turns = _turns(run)
    calls = [call for turn in turns for call in turn.get("tool_calls", [])]
    recipe_calls = [call for call in calls if call.get("name") == "recipe_search"]
    web_calls = [call for call in calls if call.get("name") == "web_search"]
    both_turns = sum(
        1 for turn in turns
        if {call.get("name") for call in turn.get("tool_calls", [])} >= {"recipe_search", "web_search"}
    )
    ordinary_sufficient = []
    unnecessary_web = 0
    expected_web_turns = []
    correct_web = 0
    explicit_web_turns = []
    explicit_web_correct = 0
    gap_turns = []
    gap_fallback_correct = 0
    for turn in turns:
        names = {call.get("name") for call in turn.get("tool_calls", [])}
        expected = turn["expected"]
        if expected.get("web_should_be_used"):
            expected_web_turns.append(turn)
            correct_web += int("web_search" in names)
        if expected.get("explicit_current_web"):
            explicit_web_turns.append(turn)
            explicit_web_correct += int("web_search" in names)
        if expected.get("web_should_be_used") and expected.get("recipe_kb_should_be_used"):
            gap_turns.append(turn)
            gap_fallback_correct += int(
                {"recipe_search", "web_search"}.issubset(names)
            )
        coverage = turn.get("coverage_events", [])
        sufficient = any(event.get("sufficient") is True for event in coverage)
        if sufficient and not expected.get("web_should_be_used"):
            ordinary_sufficient.append(turn)
            unnecessary_web += int("web_search" in names)
    components = defaultdict(list)
    for turn in turns:
        for key, value in turn["score"]["components"].items():
            components[key].append(value)
    missing = [turn["score"].get("missing_ingredient_burden") for turn in turns]
    tool_failures = Counter(
        call.get("error_type") for call in calls if call.get("error_type")
    )
    errors = Counter(
        turn["error"]["type"] for turn in turns if turn.get("error")
    )
    return {
        "executed_scenarios": len(scenarios),
        "executed_turns": len(turns),
        "overall_score": _mean([item.get("score") for item in scenarios]),
        "scenario_pass_rate": round(sum(item.get("scenario_pass", False) for item in scenarios) / len(scenarios), 4) if scenarios else None,
        "hard_constraint_pass_rate": round(sum(not turn["score"]["critical_hard_constraint_violation"] for turn in turns) / len(turns), 4) if turns else None,
        "critical_violation_count": sum(turn["score"]["critical_hard_constraint_violation"] for turn in turns),
        "ingredient_usefulness": _mean(components["ingredient_usefulness"]),
        "recommendation_relevance": _mean(components["recommendation_relevance"]),
        "grounding": _mean(components["grounding"]),
        "diversity": _mean(components["diversity"]),
        "soft_preference_match": _mean(components["soft_preference_match"]),
        "missing_ingredient_burden": _mean(missing),
        "recipe_kb_calls": len(recipe_calls),
        "tavily_calls": len(web_calls),
        "recipe_kb_call_rate_per_turn": round(len(recipe_calls) / len(turns), 4) if turns else None,
        "tavily_call_rate_per_turn": round(len(web_calls) / len(turns), 4) if turns else None,
        "both_source_turns": both_turns,
        "unnecessary_tavily_calls": unnecessary_web,
        "tavily_avoidance_rate_on_observed_sufficient_kb": round(1 - unnecessary_web / len(ordinary_sufficient), 4) if ordinary_sufficient else None,
        "observed_sufficient_kb_ordinary_turns": len(ordinary_sufficient),
        "expected_web_use_correct_rate": round(correct_web / len(expected_web_turns), 4) if expected_web_turns else None,
        "explicit_current_web_correct_rate": round(explicit_web_correct / len(explicit_web_turns), 4) if explicit_web_turns else None,
        "kb_gap_both_source_fallback_rate": round(gap_fallback_correct / len(gap_turns), 4) if gap_turns else None,
        "coverage_insufficient_rate_per_recipe_call": round(sum(any(event.get("sufficient") is False for event in turn.get("coverage_events", [])) for turn in turns) / len(recipe_calls), 4) if recipe_calls else None,
        "time_to_first_status_ms_mean": _mean([turn["latency"].get("time_to_first_status_ms") for turn in turns]),
        "time_to_first_token_ms_mean": _mean([turn["latency"].get("time_to_first_token_ms") for turn in turns]),
        "time_to_first_token_ms_median": _median([turn["latency"].get("time_to_first_token_ms") for turn in turns]),
        "total_completion_ms_mean": _mean([turn["latency"].get("total_completion_ms") for turn in turns]),
        "total_completion_ms_median": _median([turn["latency"].get("total_completion_ms") for turn in turns]),
        "recipe_kb_latency_ms_mean": _mean([call.get("latency_ms") for call in recipe_calls]),
        "tavily_latency_ms_mean": _mean([call.get("latency_ms") for call in web_calls]),
        "model_and_orchestration_ms_estimate_mean": _mean([turn["latency"].get("model_and_orchestration_ms_estimate") for turn in turns]),
        "agent_failure_rate": round(sum(item.get("error_count", 0) > 0 for item in scenarios) / len(scenarios), 4) if scenarios else None,
        "agent_errors": dict(errors),
        "tool_failures": dict(tool_failures),
    }


def _category_metrics(run: dict[str, Any]) -> dict[str, Any]:
    groups = defaultdict(list)
    for scenario in run.get("scenarios", []):
        groups[scenario["category"]].append(scenario)
    return {
        category: {
            "count": len(items),
            "overall_score": _mean([item["score"] for item in items]),
            "pass_rate": round(sum(item["scenario_pass"] for item in items) / len(items), 4),
            "hard_constraint_pass_rate": round(
                sum(not turn["score"]["critical_hard_constraint_violation"] for item in items for turn in item["turns"])
                / sum(len(item["turns"]) for item in items), 4
            ),
        }
        for category, items in sorted(groups.items())
    }


def build_reports(dataset: EvaluationDataset, legacy: dict[str, Any], rag: dict[str, Any], settings: Settings) -> dict[str, Any]:
    legacy_metrics = _strategy_metrics(legacy)
    rag_metrics = _strategy_metrics(rag)
    paired_ids = sorted(set(_scenario_map(legacy)) & set(_scenario_map(rag)))
    legacy_map, rag_map = _scenario_map(legacy), _scenario_map(rag)
    holdout_ids = {item.scenario_id for item in dataset.scenarios if item.split == "holdout"}
    complete_holdout = set(paired_ids) == holdout_ids
    deltas = [
        {
            "scenario_id": scenario_id,
            "category": rag_map[scenario_id]["category"],
            "legacy_score": legacy_map[scenario_id]["score"],
            "rag_score": rag_map[scenario_id]["score"],
            "delta": round(rag_map[scenario_id]["score"] - legacy_map[scenario_id]["score"], 2),
        }
        for scenario_id in paired_ids
    ]
    comparison = {
        "report_version": "agent-rag-comparison-v1",
        "scoring_version": SCORING_VERSION,
        "judge_version": JUDGE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_size": len(dataset.scenarios),
        "paired_live_scenario_count": len(paired_ids),
        "execution_scope": rag["run_metadata"]["execution_scope"],
        "interpretation_limit": (
            "All 80 frozen holdout scenarios were executed as paired Legacy-vs-RAG comparisons."
            if complete_holdout
            else "Only executed paired scenarios support measured Legacy-vs-RAG claims."
        ),
        "legacy": legacy_metrics,
        "recipe_rag": rag_metrics,
        "delta_recipe_rag_minus_legacy": {
            key: round(rag_metrics[key] - legacy_metrics[key], 4)
            for key in (
                "overall_score", "scenario_pass_rate", "hard_constraint_pass_rate",
                "ingredient_usefulness", "recommendation_relevance", "grounding", "diversity",
                "tavily_call_rate_per_turn", "time_to_first_token_ms_mean", "total_completion_ms_mean", "agent_failure_rate",
            )
            if rag_metrics.get(key) is not None and legacy_metrics.get(key) is not None
        },
        "by_category": {"legacy": _category_metrics(legacy), "recipe_rag": _category_metrics(rag)},
        "paired_scenario_deltas": deltas,
    }
    failures = {
        "report_version": "agent-rag-failure-analysis-v1",
        "legacy": [
            {"scenario_id": item["scenario_id"], "category": item["category"], "score": item["score"], "errors": [turn["error"] for turn in item["turns"] if turn["error"]], "violations": [violation for turn in item["turns"] for violation in turn["score"]["violations"]]}
            for item in legacy.get("scenarios", []) if not item["scenario_pass"]
        ],
        "recipe_rag": [
            {"scenario_id": item["scenario_id"], "category": item["category"], "score": item["score"], "errors": [turn["error"] for turn in item["turns"] if turn["error"]], "violations": [violation for turn in item["turns"] for violation in turn["score"]["violations"]]}
            for item in rag.get("scenarios", []) if not item["scenario_pass"]
        ],
        "taxonomy": ["hard_constraint", "vision_extraction", "recipe_retrieval", "tavily_provider", "model", "tool_call", "checkpoint_context", "deterministic_judge_uncertainty"],
    }
    def specialized(run: dict[str, Any]) -> dict[str, Any]:
        images = [item for item in run.get("scenarios", []) if item["category"] == "image_ingredient_query"]
        followups = [item for item in run.get("scenarios", []) if item["category"] == "follow_up_context"]
        memories = [item for item in run.get("scenarios", []) if item["category"] == "long_term_memory"]
        return {
            "image": {
                "scenario_count": len(images),
                "vision_extraction_usefulness": _mean([
                    turn["score"]["components"]["ingredient_usefulness"]
                    for item in images for turn in item["turns"]
                ]),
                "recipe_retrieval_coverage_sufficient_rate": _mean([
                    float(any(event.get("sufficient") is True for event in turn.get("coverage_events", [])))
                    for item in images for turn in item["turns"]
                ]),
                "stream_or_agent_error_rate": _mean([
                    float(any(turn.get("error") for turn in item["turns"]))
                    for item in images
                ]),
                "failure_attribution": "Vision extraction is scored separately from Recipe KB coverage and stream completion.",
            },
            "follow_up": {
                "scenario_count": len(followups),
                "same_thread_rate": _mean([float(item.get("same_thread_for_all_turns", False)) for item in followups]),
                "scenario_pass_rate": _mean([float(item["scenario_pass"]) for item in followups]),
                "repeated_web_on_follow_up_turns": sum(
                    call.get("name") == "web_search"
                    for item in followups for turn in item["turns"][1:] for call in turn["tool_calls"]
                ),
            },
            "memory": {
                "scenario_count": len(memories),
                "scenario_pass_rate": _mean([float(item["scenario_pass"]) for item in memories]),
                "hard_constraint_pass_rate": _mean([
                    float(not turn["score"]["critical_hard_constraint_violation"])
                    for item in memories for turn in item["turns"]
                ]),
            },
        }
    specialized_metrics = {
        "legacy": specialized(legacy),
        "recipe_rag": specialized(rag),
    }
    failures["specialized_evaluation"] = specialized_metrics
    tool_report = {
        "report_version": "agent-rag-tool-usage-v1",
        "legacy": {key: legacy_metrics[key] for key in legacy_metrics if any(term in key for term in ("calls", "call_rate", "both_source", "avoidance", "coverage", "expected_web", "explicit_current", "kb_gap", "tool_failures"))},
        "recipe_rag": {key: rag_metrics[key] for key in rag_metrics if any(term in key for term in ("calls", "call_rate", "both_source", "avoidance", "coverage", "expected_web", "explicit_current", "kb_gap", "tool_failures"))},
        "definitions": {
            "unnecessary_tavily": "web_search on an ordinary turn after observed Recipe KB coverage_sufficient=true",
            "fallback": "a turn using both recipe_search and web_search",
            "tavily_avoidance_rate": "1 - unnecessary Tavily calls / observed sufficient-KB ordinary turns",
        },
    }
    latency = {
        "report_version": "agent-rag-latency-v1",
        "legacy": {key: value for key, value in legacy_metrics.items() if "_ms_" in key},
        "recipe_rag": {key: value for key, value in rag_metrics.items() if "_ms_" in key},
        "measurement": "wall-clock around the existing CookerAgentService streaming iterator",
        "model_generation_caveat": "Provider streams do not expose isolated generation wall time; reported model_and_orchestration is total minus synchronous tool time.",
    }
    # Reliability cases outrank score deltas so former/current stream failures are
    # guaranteed to reach human review when they belong to the executed split.
    reliability_priority = ["ARAG-003", "ARAG-073", "ARAG-095", "ARAG-097", "ARAG-099"]
    reliability_priority.extend(
        item["scenario_id"]
        for item in (*legacy.get("scenarios", []), *rag.get("scenarios", []))
        if item.get("error_count", 0) > 0
    )
    sample_ids = []
    for scenario_id in reliability_priority:
        if scenario_id in paired_ids and scenario_id not in sample_ids:
            sample_ids.append(scenario_id)
    for item in sorted(deltas, key=lambda item: -abs(item["delta"])):
        if item["scenario_id"] not in sample_ids:
            sample_ids.append(item["scenario_id"])
        if len(sample_ids) >= 24:
            break
    for scenario_id in paired_ids:
        item = rag_map[scenario_id]
        priority = item["category"] in {"dietary_restrictions", "combination_constraints", "image_ingredient_query", "explicit_current_web", "kb_coverage_gap", "follow_up_context", "long_term_memory"}
        low_confidence = any(turn["score"]["judge"]["confidence"] == "low" for turn in item["turns"])
        if (priority or low_confidence) and scenario_id not in sample_ids:
            sample_ids.append(scenario_id)
    sample_ids = sample_ids[:min(30, len(paired_ids))]
    human = {
        "sample_version": "human-agent-eval-v2-reliability-priority",
        "target_size": "20-30 when at least 20 paired scenarios are executed",
        "actual_size": len(sample_ids),
        "selection": "former/current stream failures, then absolute score delta, then hard/image/web/gap/follow-up/memory and low-confidence deterministic judgments",
        "review_status": "awaiting_human_review",
        "items": [
            {"scenario_id": sid, "category": rag_map[sid]["category"], "legacy": legacy_map[sid], "recipe_rag": rag_map[sid], "human_rating": None, "human_notes": None}
            for sid in sample_ids
        ],
    }
    definitions = build_model_definitions(settings)
    deepseek_available = definitions[ModelId.DEEPSEEK_V4_PRO].available
    model_comparison = {
        "report_version": "agent-rag-model-comparison-v1",
        "step_flash_3_7": {"status": "executed", "paired_scenarios": len(paired_ids), "recipe_rag_metrics": rag_metrics},
        "deepseek_v4_pro": {
            "status": "not_executed" if deepseek_available else "configuration_missing",
            "reason": "Representative run was not requested by CLI." if deepseek_available else "DEEPSEEK_API_KEY was not configured; no synthetic results were substituted.",
            "paired_scenarios": 0,
        },
        "behavior_differences": None,
        "comparison_conclusion": "Unavailable: both models must have real paired executions before behavior differences can be claimed.",
    }
    tavily_reduction = None
    if legacy_metrics["tavily_call_rate_per_turn"] is not None and rag_metrics["tavily_call_rate_per_turn"] is not None:
        tavily_reduction = round(legacy_metrics["tavily_call_rate_per_turn"] - rag_metrics["tavily_call_rate_per_turn"], 4)
    value_demonstrated = bool(
        rag_metrics["hard_constraint_pass_rate"] is not None
        and legacy_metrics["hard_constraint_pass_rate"] is not None
        and rag_metrics["hard_constraint_pass_rate"] >= legacy_metrics["hard_constraint_pass_rate"]
        and rag_metrics["grounding"] >= legacy_metrics["grounding"]
        and (tavily_reduction or 0) > 0
        and rag_metrics["overall_score"] > legacy_metrics["overall_score"]
    )
    reliability_blocker = rag_metrics["agent_failure_rate"] > legacy_metrics["agent_failure_rate"]
    promotion_ready = value_demonstrated and not reliability_blocker
    recommendation = {
        "report_version": "agent-rag-final-recommendation-v3-constraint-boundary",
        "decision": (
            "NOT_PROMOTION_READY"
            if complete_holdout and not promotion_ready
            else "PROMOTION_READY_FOR_STEP_FLASH_3_7"
            if complete_holdout and promotion_ready
            else "KEEP_RECIPE_RAG_AS_DEVELOPMENT_DEFAULT"
            if promotion_ready
            else "INSUFFICIENT_EVIDENCE_FOR_DEFAULT_DECISION"
        ),
        "evaluation_scope": (
            "FULL_FROZEN_HOLDOUT" if complete_holdout else "BOUNDED_PAIRED_SUBSET"
        ),
        "measured_paired_scenarios": len(paired_ids),
        "full_dataset_size": len(dataset.scenarios),
        "frozen_holdout_size": len(holdout_ids),
        "criteria": {
            "hard_constraint_not_worse": rag_metrics["hard_constraint_pass_rate"] >= legacy_metrics["hard_constraint_pass_rate"],
            "ingredient_relevance_not_worse": rag_metrics["ingredient_usefulness"] >= legacy_metrics["ingredient_usefulness"],
            "grounding_not_worse": rag_metrics["grounding"] >= legacy_metrics["grounding"],
            "tavily_call_rate_reduced": (tavily_reduction or 0) > 0,
            "explicit_web_still_used": rag_metrics["expected_web_use_correct_rate"],
            "reliability_not_worse": rag_metrics["agent_failure_rate"] <= legacy_metrics["agent_failure_rate"],
        },
        "specialized_evaluation": specialized_metrics,
        "promotion_gate": "OPEN" if promotion_ready else "BLOCKED",
        "next_steps": (
            [
                "Review remaining safe-negative-clause false positives separately from genuinely unsafe answers; keep fail-closed behavior in production.",
                "Validate constraint-only follow-up tool forcing with a provider that exposes forced-tool support through LangChain streaming.",
                "Complete blinded review of human_agent_eval_sample.json; deterministic scoring is not human judgment.",
            ]
            if promotion_ready
            else [
                "Resolve the measured reliability or hard-constraint regression on a new development set before another frozen holdout run.",
                "Complete blinded review of human_agent_eval_sample.json; deterministic scoring is not human judgment.",
            ]
        ),
        "caveat": "No Recipe KB data, ranker, retrieval weight, coverage threshold, or frozen annotation was tuned from holdout results.",
    }
    return {
        "comparison_metrics.json": comparison,
        "failure_analysis.json": failures,
        "tool_usage_report.json": tool_report,
        "latency_report.json": latency,
        "human_agent_eval_sample.json": human,
        "model_comparison.json": model_comparison,
        "final_recommendation.json": recommendation,
    }


def export_all(output_dir: Path, dataset: EvaluationDataset, legacy: dict[str, Any], rag: dict[str, Any], settings: Settings) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "evaluation_dataset.json", dataset.model_dump(mode="json"))
    write_json(output_dir / "legacy_results.json", legacy)
    write_json(output_dir / "rag_results.json", rag)
    for name, report in build_reports(dataset, legacy, rag, settings).items():
        write_json(output_dir / name, report)
