"""Privacy-bounded raw LangGraph tracing for Step 17K.1 reliability failures."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from typing import Any
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)

from app.agent.context import AgentRunContext
from app.config.settings import Settings
from app.models.registry import ModelId
from app.tools.recipe_search import RecipeKBRuntime
from recipe_pipeline.agent_eval.models import EvaluationScenario, EvaluationStrategy
from recipe_pipeline.agent_eval.runner import build_evaluation_agent


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _message_summary(message: BaseMessage) -> dict[str, Any]:
    text = message.text if hasattr(message, "text") else ""
    result: dict[str, Any] = {
        "type": type(message).__name__,
        "id": getattr(message, "id", None),
        "text_characters": len(text or ""),
        "text_fingerprint": _fingerprint(text) if text else None,
    }
    if isinstance(message, (AIMessage, AIMessageChunk)):
        result.update({
            "tool_call_count": len(message.tool_calls or []),
            "tool_call_chunk_count": len(
                getattr(message, "tool_call_chunks", None) or []
            ),
            "invalid_tool_call_count": len(message.invalid_tool_calls or []),
            "chunk_position": getattr(message, "chunk_position", None),
            "finish_reason": message.response_metadata.get("finish_reason"),
            "additional_kwargs_keys": sorted(message.additional_kwargs),
            "response_metadata_keys": sorted(message.response_metadata),
        })
    if isinstance(message, ToolMessage):
        result["tool_name"] = message.name
        result["tool_call_id"] = message.tool_call_id
    return result


def _update_messages(update: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for node, node_update in update.items():
        if not isinstance(node_update, dict):
            continue
        raw = node_update.get("messages")
        messages = raw if isinstance(raw, list) else [raw]
        for message in messages:
            if isinstance(message, BaseMessage):
                result.append({"node": node, **_message_summary(message)})
    return result


def trace_scenario(
    settings: Settings,
    runtime: RecipeKBRuntime,
    scenario: EvaluationScenario,
    *,
    model_id: ModelId = ModelId.STEP_FLASH_3_7,
) -> dict[str, Any]:
    """Trace one scenario without storing user or assistant message content."""

    evaluation_agent = build_evaluation_agent(
        settings,
        runtime,
        EvaluationStrategy.RECIPE_RAG_FIRST,
        model_id,
    )
    evaluation_agent.recorder.begin_scenario()
    conversation_id = (
        f"agent-reliability-{scenario.scenario_id.lower()}-{uuid4().hex[:8]}"
    )
    turns = []
    for turn_index, turn in enumerate(scenario.turns):
        evaluation_agent.recorder.begin_turn(turn_index)
        if scenario.image_url and turn_index == 0:
            human = HumanMessage(content=[
                {"type": "text", "text": turn.query},
                {"type": "image", "url": scenario.image_url},
            ])
        else:
            human = HumanMessage(content=turn.query)
        config = {"configurable": {"thread_id": conversation_id}}
        events: list[dict[str, Any]] = []
        per_message_chunks: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "chunk_count": 0,
                "text_characters": 0,
                "tool_call_chunk_count": 0,
                "saw_last_position": False,
            }
        )
        error = None
        try:
            for mode, data in evaluation_agent.graph.stream(
                {"messages": [human]},
                config,
                stream_mode=["messages", "updates", "custom"],
                context=AgentRunContext(user_memories=scenario.user_memories),
            ):
                if mode == "messages" and isinstance(data, tuple) and len(data) == 2:
                    message, metadata = data
                    if not isinstance(message, BaseMessage):
                        continue
                    summary = _message_summary(message)
                    metadata = metadata if isinstance(metadata, dict) else {}
                    events.append({
                        "sequence": len(events),
                        "mode": mode,
                        "metadata": {
                            key: metadata.get(key)
                            for key in (
                                "langgraph_node", "langgraph_step",
                                "langgraph_checkpoint_ns", "ls_model_name",
                            )
                            if metadata.get(key) is not None
                        },
                        "message": summary,
                    })
                    if isinstance(message, AIMessageChunk):
                        key = message.id or (
                            f"step:{metadata.get('langgraph_step')}:"
                            f"node:{metadata.get('langgraph_node')}"
                        )
                        aggregate = per_message_chunks[key]
                        aggregate["chunk_count"] += 1
                        aggregate["text_characters"] += len(message.text or "")
                        aggregate["tool_call_chunk_count"] += len(
                            message.tool_call_chunks or []
                        )
                        aggregate["saw_last_position"] |= (
                            message.chunk_position == "last"
                        )
                elif mode == "updates" and isinstance(data, dict):
                    events.append({
                        "sequence": len(events),
                        "mode": mode,
                        "nodes": sorted(data),
                        "messages": _update_messages(data),
                    })
                elif mode == "custom":
                    events.append({
                        "sequence": len(events),
                        "mode": mode,
                        "stage": data.get("stage") if isinstance(data, dict) else None,
                    })
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)[:300]}

        snapshot = evaluation_agent.graph.get_state(config)
        values = getattr(snapshot, "values", None)
        messages = values.get("messages") if isinstance(values, dict) else []
        summaries = [
            _message_summary(message)
            for message in messages
            if isinstance(message, BaseMessage)
        ]
        assistant_after_user = []
        last_human = max(
            (index for index, message in enumerate(messages) if isinstance(message, HumanMessage)),
            default=-1,
        )
        for message in messages[last_human + 1:]:
            if isinstance(message, AIMessage):
                assistant_after_user.append(_message_summary(message))
        valid_final = [
            item for item in assistant_after_user
            if item["text_characters"] > 0 and item["tool_call_count"] == 0
        ]
        turns.append({
            "turn_index": turn_index,
            "query_fingerprint": _fingerprint(turn.query),
            "query_characters": len(turn.query),
            "events": events,
            "chunk_aggregates": dict(per_message_chunks),
            "tool_calls": [
                {
                    "name": call["name"],
                    "argument_keys": sorted(call["arguments"]),
                    "error_type": call["error_type"],
                }
                for call in evaluation_agent.recorder.turn_records(turn_index)
            ],
            "checkpoint_tail": summaries[-10:],
            "assistant_messages_after_user": assistant_after_user,
            "valid_canonical_final_count": len(valid_final),
            "canonical_final": valid_final[-1] if valid_final else None,
            "raw_stream_error": error,
        })
    return {
        "report_version": "agent-stream-diagnostic-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_id": scenario.scenario_id,
        "category": scenario.category,
        "model": model_id.value,
        "image_input": bool(scenario.image_url),
        "private_content_recorded": False,
        "turns": turns,
    }
