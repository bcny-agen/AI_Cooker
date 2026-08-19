"""Step 17K.1 before/after reliability and promotion-gate report."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


def _errors(run: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for scenario in run.get("scenarios", []):
        for turn in scenario.get("turns", []):
            error = turn.get("error")
            if error:
                result.append({
                    "scenario_id": scenario["scenario_id"],
                    "category": scenario["category"],
                    "turn_index": turn["turn_index"],
                    "error_type": error["type"],
                    "error_message": error["message"],
                    "tool_order": [
                        call["name"] for call in turn.get("tool_calls", [])
                    ],
                    "tokens_emitted": bool(
                        turn.get("event_counts", {}).get("token")
                    ),
                    "done_emitted": bool(
                        turn.get("event_counts", {}).get("done")
                    ),
                })
    return result


def build_reliability_report(
    *,
    step17k_rag: dict[str, Any],
    pre_retry_legacy: dict[str, Any],
    pre_retry_rag: dict[str, Any],
    final_legacy: dict[str, Any],
    final_rag: dict[str, Any],
    final_comparison: dict[str, Any],
    development_comparison: dict[str, Any],
    constraint_audit: dict[str, Any],
) -> dict[str, Any]:
    phases = {}
    for name, run in (
        ("step17k_bounded_rag", step17k_rag),
        ("full_holdout_before_empty_retry_legacy", pre_retry_legacy),
        ("full_holdout_before_empty_retry_rag", pre_retry_rag),
        ("full_holdout_final_legacy", final_legacy),
        ("full_holdout_final_rag", final_rag),
    ):
        errors = _errors(run)
        scenario_count = len(run.get("scenarios", []))
        failed_scenarios = len({item["scenario_id"] for item in errors})
        phases[name] = {
            "scenario_count": scenario_count,
            "failed_scenarios": failed_scenarios,
            "failure_rate": round(failed_scenarios / scenario_count, 4)
            if scenario_count else None,
            "error_types": dict(Counter(item["error_type"] for item in errors)),
            "errors": errors,
        }
    legacy = final_comparison["legacy"]
    rag = final_comparison["recipe_rag"]
    return {
        "report_version": "agent-rag-reliability-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical_completion_rule": [
            "Stream real AIMessageChunk text immediately, grouped by message ID.",
            "Reject a message that emits user-visible text and later becomes a tool request.",
            "After graph completion, select the last non-empty, tool-call-free AIMessage after the latest HumanMessage from checkpoint state.",
            "Require streamed text and message ID to match that canonical final AIMessage.",
            "Emit done exactly once only after canonical validation; tool messages are never user-visible.",
        ],
        "root_causes": {
            "image_mismatch": (
                "The former adapter concatenated chunks across model message IDs, "
                "so pre-tool/intermediate model text could be compared with a different "
                "final AIMessage. Vision extraction and Recipe KB execution both completed."
            ),
            "empty_final": (
                "Step intermittently returned an empty, tool-call-free model response "
                "after completed tools. A one-time model-node retry reduced but did not "
                "eliminate this provider/model behavior."
            ),
            "upstream_model": (
                "One final holdout request failed with an upstream APIStatusError, "
                "mapped to ModelInvocationError."
            ),
        },
        "phases": phases,
        "development_gate": {
            "legacy_failure_rate": development_comparison["legacy"]["agent_failure_rate"],
            "rag_failure_rate": development_comparison["recipe_rag"]["agent_failure_rate"],
            "rag_hard_constraint_pass_rate": development_comparison["recipe_rag"]["hard_constraint_pass_rate"],
            "rag_grounding": development_comparison["recipe_rag"]["grounding"],
            "rag_tavily_call_rate": development_comparison["recipe_rag"]["tavily_call_rate_per_turn"],
            "status": "PASSED_FOR_HOLDOUT",
        },
        "final_holdout": {
            "legacy_failure_rate": legacy["agent_failure_rate"],
            "rag_failure_rate": rag["agent_failure_rate"],
            "legacy_ingredient_usefulness": legacy["ingredient_usefulness"],
            "rag_ingredient_usefulness": rag["ingredient_usefulness"],
            "legacy_grounding": legacy["grounding"],
            "rag_grounding": rag["grounding"],
            "legacy_tavily_call_rate": legacy["tavily_call_rate_per_turn"],
            "rag_tavily_call_rate": rag["tavily_call_rate_per_turn"],
            "legacy_time_to_first_token_ms": legacy["time_to_first_token_ms_mean"],
            "rag_time_to_first_token_ms": rag["time_to_first_token_ms_mean"],
            "legacy_total_completion_ms": legacy["total_completion_ms_mean"],
            "rag_total_completion_ms": rag["total_completion_ms_mean"],
            "legacy_hard_constraint_pass_rate": legacy["hard_constraint_pass_rate"],
            "rag_hard_constraint_pass_rate": rag["hard_constraint_pass_rate"],
            "rag_explicit_web_correct_rate": rag["explicit_current_web_correct_rate"],
            "rag_kb_gap_fallback_rate": rag["kb_gap_both_source_fallback_rate"],
        },
        "constraint_forwarding": {
            "machine_checkable_expectations": constraint_audit["machine_checkable_expectations"],
            "passed": constraint_audit["passed_expectations"],
            "failed": constraint_audit["failed_expectations"],
            "forwarding_rate": constraint_audit["forwarding_rate"],
            "conclusion": (
                "Memory and several explicit constraint fields are still not "
                "forwarded consistently; no post-holdout prompt tuning was performed."
            ),
        },
        "deepseek": {
            "status": "BLOCKED_BY_CONFIGURATION",
            "simulated": False,
        },
        "promotion_ready": False,
        "promotion_blockers": [
            "Recipe RAG final holdout failure rate exceeded Legacy.",
            "Recipe RAG hard-constraint pass rate was below Legacy in the deterministic rubric.",
            "Constraint forwarding remained incomplete on the frozen holdout.",
        ],
    }
