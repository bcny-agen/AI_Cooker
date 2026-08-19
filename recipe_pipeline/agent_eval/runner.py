"""Live Agent runner that changes only an evaluation-only retrieval policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.context import AgentRunContext
from app.agent.constraints import DeterministicConstraintMiddleware
from app.agent.reliability import GroundedFailureRecoveryMiddleware
from app.config.settings import Settings
from app.memory.user_memory_context import UserMemoryContextMiddleware
from app.models.chat_model import create_chat_model_from_definition
from app.models.registry import ModelId, build_model_definitions
from app.services.cooker_agent import CookerAgentService
from app.tools.dish_image import GeneratedImageBuffer, create_dish_image_tool
from app.tools.recipe_search import RecipeKBRuntime, create_recipe_search_tool
from app.tools.web_search import create_web_search_tool
from recipe_pipeline.agent_eval.instrumentation import ToolRecorder, instrument_tool
from recipe_pipeline.agent_eval.models import EvaluationDataset, EvaluationScenario, EvaluationStrategy
from recipe_pipeline.agent_eval.scoring import score_turn
from recipe_pipeline.agent_eval.strategy import (
    prompt_for_strategy,
    tool_description_for_strategy,
)


@dataclass(slots=True)
class EvaluationAgent:
    service: CookerAgentService
    recorder: ToolRecorder
    graph: Any


def build_evaluation_agent(
    settings: Settings,
    runtime: RecipeKBRuntime,
    strategy: EvaluationStrategy,
    model_id: ModelId,
) -> EvaluationAgent:
    """Reuse production components; the system-prompt retrieval block alone differs."""

    definitions = build_model_definitions(settings)
    model = create_chat_model_from_definition(definitions[model_id])
    recorder = ToolRecorder()
    tools = [
        create_recipe_search_tool(runtime),
        create_web_search_tool(settings),
        create_dish_image_tool(settings, GeneratedImageBuffer()),
    ]
    for tool in tools:
        tool.description = tool_description_for_strategy(
            strategy,
            tool.name,
            tool.description,
        )
    agent = create_agent(
        model=model,
        tools=[instrument_tool(tool, recorder) for tool in tools],
        system_prompt=prompt_for_strategy(strategy),
        middleware=[
            UserMemoryContextMiddleware(),
            DeterministicConstraintMiddleware(
                force_recipe_search=(
                    strategy == EvaluationStrategy.RECIPE_RAG_FIRST
                    and model_id == ModelId.STEP_FLASH_3_7
                )
            ),
            GroundedFailureRecoveryMiddleware(),
        ],
        context_schema=AgentRunContext,
        checkpointer=InMemorySaver(),
    )
    return EvaluationAgent(
        service=CookerAgentService({model_id: agent}, definitions),
        recorder=recorder,
        graph=agent,
    )


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return str(value)


def _coverage(call: dict[str, Any]) -> tuple[bool | None, str | None]:
    if call.get("name") != "recipe_search":
        return None, None
    output = call.get("output")
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            return None, None
    if not isinstance(output, dict):
        return None, None
    return output.get("coverage_sufficient"), output.get("coverage_reason")


def _run_turn(
    evaluation_agent: EvaluationAgent,
    scenario: EvaluationScenario,
    turn_index: int,
    conversation_id: str,
    model_id: ModelId,
    strategy: EvaluationStrategy,
) -> dict[str, Any]:
    turn = scenario.turns[turn_index]
    evaluation_agent.recorder.begin_turn(turn_index)
    started = perf_counter()
    first_status_ms: float | None = None
    first_token_ms: float | None = None
    answer_parts: list[str] = []
    error_type: str | None = None
    error_message: str | None = None
    event_counts: dict[str, int] = {}
    try:
        if scenario.image_url and turn_index == 0:
            stream = evaluation_agent.service.stream_chat_with_image(
                conversation_id,
                turn.query,
                scenario.image_url,
                model_id=model_id,
                user_memories=scenario.user_memories,
                continuation_expected=False,
            )
        else:
            stream = evaluation_agent.service.stream_chat(
                conversation_id,
                turn.query,
                model_id=model_id,
                user_memories=scenario.user_memories,
                continuation_expected=turn_index > 0,
            )
        for event in stream:
            elapsed_ms = (perf_counter() - started) * 1000
            event_counts[event.type] = event_counts.get(event.type, 0) + 1
            if event.type == "status" and first_status_ms is None:
                first_status_ms = elapsed_ms
            elif event.type == "token":
                if first_token_ms is None:
                    first_token_ms = elapsed_ms
                if event.content:
                    answer_parts.append(event.content)
    except Exception as exc:
        error_type = type(exc).__name__
        error_message = str(exc)[:500]
    total_ms = (perf_counter() - started) * 1000
    calls = evaluation_agent.recorder.turn_records(turn_index)
    for call in calls:
        call["output"] = _json_safe(call.get("output"))
    answer = "".join(answer_parts)
    score = score_turn(answer, calls, turn.expected, strategy)
    if error_type:
        score["score"] = 0.0
        score["scenario_pass"] = False
    tool_latency = sum(float(call.get("latency_ms") or 0) for call in calls)
    coverage_values = [_coverage(call) for call in calls]
    return {
        "turn_index": turn_index,
        "query": turn.query,
        "expected": turn.expected.model_dump(mode="json"),
        "answer": answer,
        "tool_calls": calls,
        "coverage_events": [
            {"sufficient": sufficient, "reason": reason}
            for sufficient, reason in coverage_values
            if sufficient is not None or reason is not None
        ],
        "latency": {
            "time_to_first_status_ms": round(first_status_ms, 3) if first_status_ms is not None else None,
            "time_to_first_token_ms": round(first_token_ms, 3) if first_token_ms is not None else None,
            "total_completion_ms": round(total_ms, 3),
            "retrieval_tool_ms": round(tool_latency, 3),
            "model_and_orchestration_ms_estimate": round(max(0.0, total_ms - tool_latency), 3),
            "model_time_note": "end-to-end total minus synchronous tool wall time; includes Agent orchestration",
        },
        "event_counts": event_counts,
        "error": {"type": error_type, "message": error_message} if error_type else None,
        "score": score,
    }


def run_strategy(
    settings: Settings,
    runtime: RecipeKBRuntime,
    dataset: EvaluationDataset,
    scenario_ids: list[str],
    strategy: EvaluationStrategy,
    *,
    model_id: ModelId = ModelId.STEP_FLASH_3_7,
    progress_path: Path | None = None,
    resume: bool = False,
    agent: EvaluationAgent | None = None,
) -> dict[str, Any]:
    evaluation_agent = agent or build_evaluation_agent(
        settings, runtime, strategy, model_id
    )
    selected = [scenario for scenario in dataset.scenarios if scenario.scenario_id in set(scenario_ids)]
    results = []
    if resume and progress_path is not None and progress_path.exists():
        saved = json.loads(progress_path.read_text(encoding="utf-8"))
        metadata = saved.get("run_metadata") or {}
        if (
            metadata.get("strategy") != strategy.value
            or metadata.get("model_id") != model_id.value
            or metadata.get("dataset_version") != dataset.dataset_version
        ):
            raise ValueError("Saved evaluation progress does not match this run")
        results = [
            item for item in saved.get("scenarios", [])
            if item.get("scenario_id") in scenario_ids
        ]
    completed_ids = {item["scenario_id"] for item in results}
    run_started = datetime.now(timezone.utc)
    for scenario in selected:
        if scenario.scenario_id in completed_ids:
            continue
        evaluation_agent.recorder.begin_scenario()
        conversation_id = f"agent-eval-{strategy.value.lower()}-{scenario.scenario_id.lower()}-{uuid4().hex[:8]}"
        turns = [
            _run_turn(
                evaluation_agent,
                scenario,
                index,
                conversation_id,
                model_id,
                strategy,
            )
            for index in range(len(scenario.turns))
        ]
        critical = any(turn["score"]["critical_hard_constraint_violation"] for turn in turns)
        errors = [turn["error"] for turn in turns if turn["error"]]
        results.append({
            "scenario_id": scenario.scenario_id,
            "category": scenario.category,
            "split": scenario.split,
            "language": scenario.language,
            "conversation_id_fingerprint": conversation_id.rsplit("-", 1)[0],
            "same_thread_for_all_turns": True,
            "image_reference": scenario.image_reference,
            "user_memory_count": len(scenario.user_memories),
            "turns": turns,
            "score": 0.0 if critical else round(sum(turn["score"]["score"] for turn in turns) / len(turns), 2),
            "scenario_pass": not critical and not errors and all(turn["score"]["scenario_pass"] for turn in turns),
            "error_count": len(errors),
        })
        if progress_path is not None:
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(
                json.dumps(
                    _run_result(
                        dataset,
                        scenario_ids,
                        strategy,
                        model_id,
                        results,
                        run_started,
                    ),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ) + "\n",
                encoding="utf-8",
            )
    return _run_result(
        dataset,
        scenario_ids,
        strategy,
        model_id,
        results,
        run_started,
    )


def _run_result(
    dataset: EvaluationDataset,
    scenario_ids: list[str],
    strategy: EvaluationStrategy,
    model_id: ModelId,
    results: list[dict[str, Any]],
    run_started: datetime,
) -> dict[str, Any]:
    return {
        "run_metadata": {
            "strategy": strategy.value,
            "model_id": model_id.value,
            "dataset_version": dataset.dataset_version,
            "dataset_size": len(dataset.scenarios),
            "executed_scenario_count": len(results),
            "executed_turn_count": sum(len(item["turns"]) for item in results),
            "execution_scope": (
                "bounded_live_subset"
                if len(scenario_ids) < len(dataset.scenarios)
                else "full_live_suite"
            ),
            "selected_scenario_ids": scenario_ids,
            "started_at": run_started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "production_behavior_changed": False,
            "judge_kind": "deterministic_proxy",
        },
        "scenarios": results,
    }
