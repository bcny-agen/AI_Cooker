import json

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime

from app.agent.constraints import (
    DeterministicConstraintMiddleware,
    extract_recipe_constraints,
    merge_recipe_search_arguments,
    unsafe_constraint_mentions,
)
from app.agent.context import AgentRunContext


def test_extracts_explicit_query_constraints_deterministically():
    constraints = extract_recipe_constraints([HumanMessage(
        content="只有电饭锅，鸡肉和米饭，30分钟，少油。"
    )])

    assert constraints.available_ingredients == ("鸡肉", "米饭")
    assert constraints.taste_preferences == ("LOW_OIL",)
    assert constraints.equipment == ("RICE_COOKER",)
    assert "OVEN" in constraints.unavailable_equipment
    assert constraints.max_total_minutes == 30


def test_extracts_allergens_and_supported_diet_contract_values():
    constraints = extract_recipe_constraints([
        HumanMessage(content="不要坚果，无麸质燕麦早餐。")
    ])

    assert set(constraints.excluded_allergens) == {"TREE_NUT", "PEANUT", "WHEAT"}
    assert "GLUTEN_FREE" in constraints.dietary_constraints
    assert "坚果" in constraints.excluded_ingredients


def test_memory_exclusions_and_taste_are_not_available_ingredients():
    constraints = extract_recipe_constraints(
        [HumanMessage(content="给我推荐晚饭。")],
        ("avoid coriander", "prefer low oil"),
    )

    assert constraints.available_ingredients == ()
    assert set(constraints.excluded_ingredients) == {"coriander", "香菜"}
    assert constraints.taste_preferences == ("LOW_OIL",)


def test_merge_canonicalizes_aliases_and_never_weakens_constraints():
    constraints = extract_recipe_constraints(
        [HumanMessage(content="今天吃什么？")],
        ("do not eat pork", "prefer non-spicy food"),
    )
    merged = merge_recipe_search_arguments(
        {
            "query": "dinner",
            "available_ingredients": ["tomatoes", "prawns"],
            "excluded_ingredients": ["pork"],
            "taste_preferences": ["not spicy"],
        },
        constraints,
    )

    assert merged["available_ingredients"] == [
        "tomatoes", "prawns", "番茄", "虾",
    ]
    assert {"pork", "猪肉", "猪排骨"}.issubset(
        set(merged["excluded_ingredients"])
    )
    assert set(merged["taste_preferences"]) == {"NOT SPICY", "NON_SPICY"}


def test_recipe_tool_call_is_enforced_before_execution():
    middleware = DeterministicConstraintMiddleware()
    state = {"messages": [HumanMessage(content="没有炒锅，用蒸锅做鱼。")]}
    request = ToolCallRequest(
        tool_call={
            "name": "recipe_search",
            "args": {"query": "蒸鱼", "unavailable_equipment": ["wok"]},
            "id": "call-1",
            "type": "tool_call",
        },
        tool=None,
        state=state,
        runtime=Runtime(context=AgentRunContext()),
    )
    captured = []

    result = middleware.wrap_tool_call(
        request,
        lambda updated: captured.append(updated) or ToolMessage(
            content=json.dumps({"recipes": []}),
            name="recipe_search",
            tool_call_id="call-1",
        ),
    )

    assert isinstance(result, ToolMessage)
    arguments = captured[0].tool_call["args"]
    assert arguments["available_ingredients"] == ["鱼"]
    assert arguments["equipment"] == ["STEAMER"]
    assert arguments["unavailable_equipment"] == ["WOK"]


def test_final_answer_validator_allows_negative_clause_but_rejects_positive_use():
    constraints = extract_recipe_constraints(
        [HumanMessage(content="不吃猪肉，推荐牛肉菜。")]
    )

    assert unsafe_constraint_mentions("推荐牛肉炖土豆，不含猪肉。", constraints) == ()
    assert unsafe_constraint_mentions("也可用豆腐替代猪肉。", constraints) == ()
    assert unsafe_constraint_mentions("也可以加猪肉末增香。", constraints) == ("猪肉",)


def test_under_specified_meal_request_forces_recipe_tool_not_arbitrary_text():
    middleware = DeterministicConstraintMiddleware()
    request = ModelRequest(
        model=object(),  # type: ignore[arg-type]
        messages=[HumanMessage(content="给我推荐晚饭。")],
        system_message=SystemMessage(content="cook"),
        tools=[{"type": "function", "function": {"name": "recipe_search"}}],
        runtime=Runtime(context=AgentRunContext(user_memories=(
            "avoid coriander", "prefer low oil",
        ))),
    )
    captured = []

    middleware.wrap_model_call(
        request,
        lambda updated: captured.append(updated) or ModelResponse(
            result=[AIMessage(content="", tool_calls=[{
                "name": "recipe_search", "args": {}, "id": "call-1",
                "type": "tool_call",
            }])]
        ),
    )

    assert captured[0].tool_choice == {
        "type": "function", "function": {"name": "recipe_search"}
    }


def test_constraint_only_first_turn_remains_a_clarification_case():
    constraints = extract_recipe_constraints([
        HumanMessage(content="我不吃辣。"),
    ])

    assert constraints.taste_preferences == ("NON_SPICY",)
    assert constraints.should_search_recipe is False


def test_force_recipe_search_can_be_disabled_for_incompatible_model():
    middleware = DeterministicConstraintMiddleware(force_recipe_search=False)
    request = ModelRequest(
        model=object(),  # type: ignore[arg-type]
        messages=[HumanMessage(content="鸡蛋晚饭怎么做？")],
        tools=[{"type": "function", "function": {"name": "recipe_search"}}],
        runtime=Runtime(context=AgentRunContext()),
    )
    captured = []

    middleware.wrap_model_call(
        request,
        lambda updated: captured.append(updated) or ModelResponse(
            result=[AIMessage(content="clarify")]
        ),
    )

    assert captured[0].tool_choice is None
