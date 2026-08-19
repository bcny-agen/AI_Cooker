"""Expected-vs-actual Recipe tool argument audit for Step 17K.1."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
from typing import Any

from recipe_pipeline.agent_eval.models import EvaluationDataset
from recipe_pipeline.agent_eval.scoring import ALIASES


EQUIPMENT_ALIASES = {
    "AIR_FRYER": {"air_fryer", "空气炸锅"},
    "RICE_COOKER": {"rice_cooker", "电饭锅"},
    "MICROWAVE": {"microwave", "微波炉"},
    "STEAMER": {"steamer", "蒸锅"},
    "PAN": {"pan", "平底锅"},
    "OVEN": {"oven", "烤箱"},
    "WOK": {"wok", "炒锅"},
    "STOVE": {"stove", "炉灶", "灶", "炉子"},
}

PREFERENCE_TOOL_VALUES = {
    "LOW_OIL": {"low_oil", "low-oil", "少油", "低油"},
    "NON_SPICY": {"non_spicy", "non-spicy", "不辣"},
    "HIGH_PROTEIN": {"high_protein", "high-protein", "高蛋白"},
    "LOW_SALT": {"low_salt", "low-salt", "少盐", "低盐"},
}

ALLERGEN_EQUIVALENTS = {
    "花生": "PEANUT",
    "坚果": "TREE_NUT",
    "牛奶": "MILK",
    "鸡蛋": "EGG",
    "芝麻": "SESAME",
}


def _folded(values: list[Any] | tuple[Any, ...]) -> set[str]:
    return {str(value).strip().casefold() for value in values if str(value).strip()}


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _ingredient_present(expected: str, actual: set[str]) -> bool:
    aliases = ALIASES.get(expected, (expected,))
    return bool({value.casefold() for value in aliases} & actual)


def _equipment_present(expected: str, actual: set[str]) -> bool:
    aliases = EQUIPMENT_ALIASES.get(expected.upper(), {expected.casefold()})
    return bool({value.casefold() for value in aliases} & actual)


def _preference_present(expected: str, actual: set[str]) -> bool | None:
    aliases = PREFERENCE_TOOL_VALUES.get(expected.upper())
    if aliases is None:
        return None
    return bool({value.casefold() for value in aliases} & actual)


def build_constraint_forwarding_audit(
    dataset: EvaluationDataset,
    run: dict[str, Any],
) -> dict[str, Any]:
    """Audit only annotated fields; never infer missing expected labels."""

    definitions = {item.scenario_id: item for item in dataset.scenarios}
    items = []
    counts: Counter[str] = Counter()
    for scenario_result in run.get("scenarios", []):
        scenario = definitions[scenario_result["scenario_id"]]
        for turn_index, turn_result in enumerate(scenario_result["turns"]):
            expected = scenario.turns[turn_index].expected
            calls = [
                call for call in turn_result.get("tool_calls", [])
                if call.get("name") == "recipe_search"
            ]
            actual = [call.get("arguments") or {} for call in calls]
            union = {
                field: _folded([
                    value
                    for arguments in actual
                    for value in arguments.get(field, [])
                ])
                for field in (
                    "available_ingredients", "excluded_ingredients",
                    "excluded_allergens", "dietary_constraints",
                    "taste_preferences", "equipment", "unavailable_equipment",
                    "scenario_tags",
                )
            }
            checks: list[dict[str, Any]] = []

            def add(field: str, value: str, passed: bool | None, note: str = "") -> None:
                status = "not_machine_checkable" if passed is None else "passed" if passed else "failed"
                counts[f"{field}:{status}"] += 1
                checks.append({
                    "field": field,
                    "expected": value,
                    "status": status,
                    "note": note or None,
                })

            for ingredient in expected.required_ingredients or expected.visible_ingredients:
                add("available_ingredients", ingredient, _ingredient_present(
                    ingredient, union["available_ingredients"]
                ))
            for ingredient in expected.forbidden_ingredients:
                passed = _ingredient_present(
                    ingredient, union["excluded_ingredients"]
                ) or ALLERGEN_EQUIVALENTS.get(ingredient, "").casefold() in union[
                    "excluded_allergens"
                ]
                add("excluded_ingredients", ingredient, passed)
            for allergen in expected.excluded_allergens:
                add(
                    "excluded_allergens", allergen,
                    allergen.casefold() in union["excluded_allergens"],
                )
            for diet in expected.dietary_constraints:
                add(
                    "dietary_constraints", diet,
                    diet.casefold() in union["dietary_constraints"],
                )
            for preference in expected.soft_preferences:
                add(
                    "taste_preferences", preference,
                    _preference_present(preference, union["taste_preferences"]),
                    "The current RecipeSearchInput vocabulary has no deterministic value for this preference."
                    if preference.upper() not in PREFERENCE_TOOL_VALUES else "",
                )
            for equipment in expected.available_equipment:
                add(
                    "equipment", equipment,
                    _equipment_present(equipment, union["equipment"]),
                )
            for equipment in expected.unavailable_equipment:
                add(
                    "unavailable_equipment", equipment,
                    _equipment_present(equipment, union["unavailable_equipment"]),
                )
            if expected.max_time_minutes is not None:
                values = {
                    arguments.get("max_total_minutes") for arguments in actual
                }
                add(
                    "max_total_minutes", str(expected.max_time_minutes),
                    expected.max_time_minutes in values,
                )

            item_status = (
                "not_applicable"
                if not checks and not calls
                else "no_recipe_call"
                if checks and not calls
                else "failed"
                if any(check["status"] == "failed" for check in checks)
                else "passed"
            )
            counts[f"turn:{item_status}"] += 1
            items.append({
                "scenario_id": scenario.scenario_id,
                "category": scenario.category,
                "turn_index": turn_index,
                "query_fingerprint": _fingerprint(turn_result.get("query", "")),
                "recipe_call_count": len(calls),
                "actual_argument_keys": sorted({
                    key for arguments in actual for key in arguments
                }),
                "checks": checks,
                "status": item_status,
                "memory_context_present": bool(scenario.user_memories),
                "expected_unannotated_fields": {
                    "max_difficulty": "not annotated",
                    "servings": "not annotated except natural-language follow-ups",
                    "scenario_tags": "not frozen as exact expected values",
                },
            })
    # v1 accidentally counted aggregate turn statuses alongside individual
    # field expectations. Keep a compatibility figure, but make the primary
    # forwarding rate a field-only metric.
    machine_checks_v1_compatible = sum(
        value for key, value in counts.items()
        if key.endswith(":passed") or key.endswith(":failed")
    )
    passed_v1_compatible = sum(
        value for key, value in counts.items() if key.endswith(":passed")
    )
    failed_v1_compatible = sum(
        value for key, value in counts.items() if key.endswith(":failed")
    )
    passed = sum(
        value for key, value in counts.items()
        if not key.startswith("turn:") and key.endswith(":passed")
    )
    failed = sum(
        value for key, value in counts.items()
        if not key.startswith("turn:") and key.endswith(":failed")
    )
    machine_checks = passed + failed
    return {
        "report_version": "constraint-forwarding-audit-v2-field-only-rate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset.dataset_version,
        "model": run.get("run_metadata", {}).get("model_id"),
        "strategy": run.get("run_metadata", {}).get("strategy"),
        "executed_scenarios": len(run.get("scenarios", [])),
        "machine_checkable_expectations": machine_checks,
        "passed_expectations": passed,
        "failed_expectations": failed,
        "forwarding_rate": round(passed / machine_checks, 4) if machine_checks else None,
        "v1_compatible_counts_including_turn_status": {
            "machine_checkable_expectations": machine_checks_v1_compatible,
            "passed_expectations": passed_v1_compatible,
            "failed_expectations": failed_v1_compatible,
            "forwarding_rate": round(
                passed_v1_compatible / machine_checks_v1_compatible, 4
            ) if machine_checks_v1_compatible else None,
        },
        "counts": dict(sorted(counts.items())),
        "items": items,
        "limitations": [
            "Only frozen annotated expectations are audited.",
            "Difficulty, servings, and exact scenario tags are reported as unannotated rather than silently scored.",
            "A sensible clarification without recipe_search is not automatically a retrieval failure.",
        ],
    }
