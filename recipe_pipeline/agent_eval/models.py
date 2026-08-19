"""Versioned contracts for the Step 17K Agent-level evaluation."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


DATASET_VERSION = "agent-rag-eval-v1"
SCORING_VERSION = "agent-rag-scoring-v2-negative-context"
JUDGE_VERSION = "deterministic-agent-judge-v1"


class EvaluationStrategy(str, Enum):
    LEGACY_WEB_FIRST = "LEGACY_WEB_FIRST"
    RECIPE_RAG_FIRST = "RECIPE_RAG_FIRST"


class ExpectedBehavior(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipe_kb_should_be_used: bool
    recipe_kb_may_be_used: bool = False
    web_should_be_used: bool
    required_ingredients: tuple[str, ...] = ()
    forbidden_ingredients: tuple[str, ...] = ()
    excluded_allergens: tuple[str, ...] = ()
    dietary_constraints: tuple[str, ...] = ()
    soft_preferences: tuple[str, ...] = ()
    max_time_minutes: int | None = None
    available_equipment: tuple[str, ...] = ()
    unavailable_equipment: tuple[str, ...] = ()
    visible_ingredients: tuple[str, ...] = ()
    request_multiple: bool = False
    explicit_current_web: bool = False


class EvaluationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=1000)
    expected: ExpectedBehavior


class EvaluationScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    category: str
    split: str
    language: str
    turns: tuple[EvaluationTurn, ...]
    user_memories: tuple[str, ...] = ()
    image_url: str | None = None
    image_reference: str | None = None


class EvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_version: str = DATASET_VERSION
    frozen: bool = True
    scenarios: tuple[EvaluationScenario, ...]
