from datetime import datetime, timezone
from types import SimpleNamespace

from recipe_pipeline.agent_eval.dataset import build_evaluation_dataset
from recipe_pipeline.agent_eval.models import EvaluationStrategy
from recipe_pipeline.agent_eval.runner import _run_result, run_strategy
from app.models.registry import ModelId


def test_progress_result_uses_selected_scope_without_hidden_runner_state():
    dataset = build_evaluation_dataset()
    result = _run_result(
        dataset,
        ["ARAG-001"],
        EvaluationStrategy.RECIPE_RAG_FIRST,
        ModelId.STEP_FLASH_3_7,
        [],
        datetime.now(timezone.utc),
    )
    assert result["run_metadata"]["execution_scope"] == "bounded_live_subset"


def test_run_strategy_can_reuse_prebuilt_agent(monkeypatch, tmp_path):
    dataset = build_evaluation_dataset()
    selected = [dataset.scenarios[0].scenario_id]
    sentinel = SimpleNamespace(
        recorder=SimpleNamespace(begin_scenario=lambda: None)
    )
    called = []

    monkeypatch.setattr(
        "recipe_pipeline.agent_eval.runner._run_turn",
        lambda evaluation_agent, scenario, turn_index, conversation_id,
        model_id, strategy: called.append(evaluation_agent) or {
            "score": {
                "critical_hard_constraint_violation": False,
                "score": 100.0,
                "scenario_pass": True,
            },
            "error": None,
        },
    )
    result = run_strategy(
        settings=object(),  # type: ignore[arg-type]
        runtime=object(),  # type: ignore[arg-type]
        dataset=dataset,
        scenario_ids=selected,
        strategy=EvaluationStrategy.RECIPE_RAG_FIRST,
        agent=sentinel,  # type: ignore[arg-type]
        progress_path=tmp_path / "progress.json",
    )

    assert called == [sentinel]
    assert result["run_metadata"]["executed_scenario_count"] == 1
