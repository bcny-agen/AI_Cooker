from __future__ import annotations

import json

from langchain_core.tools import StructuredTool

from app.agent.prompts import COOKER_SYSTEM_PROMPT
from recipe_pipeline.agent_eval.dataset import build_evaluation_dataset
from recipe_pipeline.agent_eval.constraint_audit import (
    build_constraint_forwarding_audit,
)
from recipe_pipeline.agent_eval.instrumentation import ToolRecorder, instrument_tool
from recipe_pipeline.agent_eval.main import stratified_ids
from recipe_pipeline.agent_eval.models import EvaluationStrategy, ExpectedBehavior
from recipe_pipeline.agent_eval.reporting import ARTIFACT_NAMES
from recipe_pipeline.agent_eval.scoring import WEIGHTS, score_turn
from recipe_pipeline.agent_eval.strategy import (
    prompt_for_strategy,
    tool_description_for_strategy,
)


def test_dataset_is_frozen_100_with_dev_holdout_and_required_categories():
    dataset = build_evaluation_dataset()
    assert dataset.frozen is True
    assert len(dataset.scenarios) == 100
    assert sum(item.split == "development" for item in dataset.scenarios) == 20
    assert sum(item.split == "holdout" for item in dataset.scenarios) == 80
    assert len({item.scenario_id for item in dataset.scenarios}) == 100
    assert {
        "ingredient_recommendation", "partial_ingredient_coverage",
        "synonym_multilingual", "preference_constraints",
        "dietary_restrictions", "time_constraints", "equipment_constraints",
        "combination_constraints", "follow_up_context", "explicit_current_web",
        "kb_coverage_gap", "image_ingredient_query", "long_term_memory",
    } == {item.category for item in dataset.scenarios}
    assert sum(len(item.turns) for item in dataset.scenarios) == 112


def test_stratified_selection_is_stable_and_category_complete():
    dataset = build_evaluation_dataset()
    first = stratified_ids(dataset, 24)
    assert first == stratified_ids(dataset, 24)
    selected = [item for item in dataset.scenarios if item.scenario_id in first]
    assert len(selected) == 24
    assert len({item.category for item in selected}) == 13


def test_legacy_policy_is_eval_only_and_production_prompt_is_unchanged():
    original = COOKER_SYSTEM_PROMPT
    rag = prompt_for_strategy(EvaluationStrategy.RECIPE_RAG_FIRST)
    legacy = prompt_for_strategy(EvaluationStrategy.LEGACY_WEB_FIRST)
    assert rag is COOKER_SYSTEM_PROMPT
    assert "优先调用 web_search" in legacy
    assert "优先调用 recipe_search" in original
    assert COOKER_SYSTEM_PROMPT == original
    production_description = "first use recipe_search"
    assert tool_description_for_strategy(
        EvaluationStrategy.RECIPE_RAG_FIRST,
        "web_search",
        production_description,
    ) == production_description
    assert "primary retrieval" in tool_description_for_strategy(
        EvaluationStrategy.LEGACY_WEB_FIRST,
        "web_search",
        production_description,
    )
    assert "流式工具调用纪律" in legacy


def test_weights_are_transparent_and_sum_to_one():
    assert sum(WEIGHTS.values()) == 1.0
    assert WEIGHTS["hard_constraint_compliance"] == 0.30


def test_critical_hard_violation_forces_zero_score():
    expected = ExpectedBehavior(
        recipe_kb_should_be_used=False,
        web_should_be_used=False,
        forbidden_ingredients=("花生",),
    )
    result = score_turn("推荐花生拌菜，这道菜很适合晚饭。" * 4, [], expected)
    assert result["critical_hard_constraint_violation"] is True
    assert result["score"] == 0
    assert result["scenario_pass"] is False


def test_legacy_tool_efficiency_uses_legacy_policy_not_rag_target():
    expected = ExpectedBehavior(
        recipe_kb_should_be_used=True,
        web_should_be_used=False,
    )
    calls = [{"name": "web_search", "arguments": {}, "output": {"results": []}, "error_type": None}]
    result = score_turn(
        "Web-grounded cooking recommendation with enough useful detail for dinner preparation.",
        calls,
        expected,
        EvaluationStrategy.LEGACY_WEB_FIRST,
    )
    assert result["components"]["tool_efficiency"] == 1.0


def test_negated_exclusion_is_not_treated_as_positive_use():
    expected = ExpectedBehavior(
        recipe_kb_should_be_used=False,
        web_should_be_used=False,
        forbidden_ingredients=("花生",),
    )
    result = score_turn("这道菜不要花生，并且避免任何花生制品。可以用豆腐和青菜完成晚饭。", [], expected)
    assert result["critical_hard_constraint_violation"] is False
    heading_result = score_turn("**花生限制**：本方案不含花生，也无需花生油。可以用豆腐和青菜完成晚饭。", [], expected)
    assert heading_result["critical_hard_constraint_violation"] is False
    replacement_result = score_turn(
        "可以用椰奶替代牛奶；成品口感类似奶油浓汤，但方案全程无乳制品。",
        [],
        ExpectedBehavior(
            recipe_kb_should_be_used=False,
            web_should_be_used=False,
            forbidden_ingredients=("牛奶", "奶油"),
        ),
    )
    assert replacement_result["critical_hard_constraint_violation"] is False


def test_available_equipment_is_forwarded_separately_from_unavailable():
    expected = ExpectedBehavior(
        recipe_kb_should_be_used=True,
        web_should_be_used=False,
        available_equipment=("AIR_FRYER",),
    )
    call = {
        "name": "recipe_search",
        "arguments": {"equipment": ["空气炸锅"]},
        "output": '{"available":true,"recipes":[]}',
        "error_type": None,
    }
    result = score_turn("用空气炸锅烹饪鸡翅，按照推荐温度完成即可。" * 3, [call], expected)
    assert not result["critical_hard_constraint_violation"]


def test_instrumentation_preserves_schema_and_records_output():
    def search(query: str) -> str:
        return json.dumps({"query": query, "ok": True})

    original = StructuredTool.from_function(search, name="recipe_search", description="d")
    recorder = ToolRecorder()
    wrapped = instrument_tool(original, recorder)
    assert wrapped.args_schema == original.args_schema
    assert wrapped.invoke({"query": "egg"}) == '{"query": "egg", "ok": true}'
    assert recorder.records[0].name == "recipe_search"
    assert recorder.records[0].arguments == {"query": "egg"}


def test_required_artifact_contract_is_complete():
    assert len(ARTIFACT_NAMES) == 10
    assert set(ARTIFACT_NAMES) == {
        "evaluation_dataset.json", "legacy_results.json", "rag_results.json",
        "comparison_metrics.json", "failure_analysis.json",
        "tool_usage_report.json", "latency_report.json",
        "human_agent_eval_sample.json", "model_comparison.json",
        "final_recommendation.json",
    }


def test_constraint_audit_covers_ingredients_exclusions_time_equipment_memory():
    dataset = build_evaluation_dataset()
    selected_ids = {"ARAG-057", "ARAG-065", "ARAG-098"}
    scenarios = []
    for scenario in dataset.scenarios:
        if scenario.scenario_id not in selected_ids:
            continue
        expected = scenario.turns[0].expected
        arguments = {
            "available_ingredients": list(expected.required_ingredients),
            "excluded_ingredients": list(expected.forbidden_ingredients),
            "excluded_allergens": list(expected.excluded_allergens),
            "dietary_constraints": list(expected.dietary_constraints),
            "taste_preferences": list(expected.soft_preferences),
            "equipment": list(expected.available_equipment),
            "unavailable_equipment": list(expected.unavailable_equipment),
            "scenario_tags": [],
            "max_total_minutes": expected.max_time_minutes,
        }
        scenarios.append({
            "scenario_id": scenario.scenario_id,
            "turns": [{
                "query": scenario.turns[0].query,
                "tool_calls": [{"name": "recipe_search", "arguments": arguments}],
            }],
        })
    report = build_constraint_forwarding_audit(
        dataset,
        {
            "run_metadata": {
                "model_id": "STEP_FLASH_3_7",
                "strategy": "RECIPE_RAG_FIRST",
            },
            "scenarios": scenarios,
        },
    )
    checked_fields = {
        check["field"]
        for item in report["items"]
        for check in item["checks"]
    }
    assert {
        "available_ingredients", "excluded_ingredients",
        "taste_preferences", "equipment", "max_total_minutes",
    }.issubset(checked_fields)
    assert report["failed_expectations"] == 0
    assert report["machine_checkable_expectations"] == (
        report["passed_expectations"] + report["failed_expectations"]
    )
    assert report["v1_compatible_counts_including_turn_status"]
    assert any(item["memory_context_present"] for item in report["items"])
