"""Agent-level Legacy-web-first versus Recipe-RAG-first evaluation."""

from recipe_pipeline.agent_eval.dataset import build_evaluation_dataset
from recipe_pipeline.agent_eval.models import EvaluationStrategy

__all__ = ["EvaluationStrategy", "build_evaluation_dataset"]
