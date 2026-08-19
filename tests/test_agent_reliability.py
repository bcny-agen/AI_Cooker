import json

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

from app.agent.reliability import (
    EmptyFinalModelResponseRetryMiddleware,
    GroundedFailureRecoveryMiddleware,
)


def test_retries_one_empty_final_model_response_without_fabricating_text():
    middleware = EmptyFinalModelResponseRetryMiddleware()
    outputs = [
        ModelResponse(result=[AIMessage(content="")]),
        ModelResponse(result=[AIMessage(content="real answer")]),
    ]
    calls = []

    result = middleware.wrap_model_call(
        object(),
        lambda request: calls.append(request) or outputs.pop(0),
    )

    assert len(calls) == 2
    assert result.result[0].text == "real answer"


def test_does_not_retry_tool_call_or_nonempty_text():
    middleware = EmptyFinalModelResponseRetryMiddleware()
    for message in (
        AIMessage(content="answer"),
        AIMessage(content="", tool_calls=[{
            "name": "recipe_search", "args": {},
            "id": "call", "type": "tool_call",
        }]),
    ):
        calls = []
        result = middleware.wrap_model_call(
            object(),
            lambda request: calls.append(request) or ModelResponse(result=[message]),
        )
        assert len(calls) == 1
        assert result.result[0] == message


def test_one_retry_remains_empty_and_is_not_retried_indefinitely():
    middleware = EmptyFinalModelResponseRetryMiddleware()
    calls = []
    result = middleware.wrap_model_call(
        object(),
        lambda request: calls.append(request) or ModelResponse(
            result=[AIMessage(content="")]
        ),
    )
    assert len(calls) == 2
    assert result.result[0].text == ""


def _recovery_request(messages):
    return ModelRequest(
        model=object(),  # type: ignore[arg-type]
        messages=messages,
        runtime=Runtime(),
    )


def test_empty_response_recovers_only_from_existing_recipe_evidence():
    middleware = GroundedFailureRecoveryMiddleware()
    payload = {
        "recipes": [{
            "name": "番茄炒蛋",
            "summary": "以番茄和鸡蛋完成的家庭食谱。",
            "total_minutes": 15,
            "difficulty": 1,
            "missing_required_ingredients": [],
        }]
    }
    request = _recovery_request([
        HumanMessage(content="番茄鸡蛋怎么做？"),
        ToolMessage(
            content=json.dumps(payload, ensure_ascii=False),
            name="recipe_search",
            tool_call_id="call-1",
        ),
    ])
    calls = []

    result = middleware.wrap_model_call(
        request,
        lambda _: calls.append(1) or ModelResponse(result=[AIMessage(content="")]),
    )

    assert len(calls) == 2
    assert "番茄炒蛋" in result.result[0].text
    assert result.result[0].additional_kwargs["ai_cooker_recovery_policy"]


def test_upstream_error_recovers_from_completed_web_evidence_without_replaying_tool():
    middleware = GroundedFailureRecoveryMiddleware()
    request = _recovery_request([
        HumanMessage(content="最近流行什么？"),
        ToolMessage(
            content=json.dumps({"results": [{
                "title": "Current egg trend",
                "url": "https://example.com/egg",
                "content": "A current source summary.",
            }]}),
            name="web_search",
            tool_call_id="call-web",
        ),
    ])
    calls = []

    result = middleware.wrap_model_call(
        request,
        lambda _: calls.append(1) or ModelResponse(result=[AIMessage(content="")]),
    )

    assert len(calls) == 2
    assert "https://example.com/egg" in result.result[0].text


def test_no_tool_evidence_keeps_empty_response_incomplete():
    middleware = GroundedFailureRecoveryMiddleware()
    request = _recovery_request([HumanMessage(content="hello")])
    calls = []

    result = middleware.wrap_model_call(
        request,
        lambda _: calls.append(1) or ModelResponse(result=[AIMessage(content="")]),
    )

    assert len(calls) == 2
    assert result.result[0].text == ""
