"""Contracts for evaluation queries, retrieval hits, metrics, and failures."""

from __future__ import annotations

from enum import Enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QueryKind(str, Enum):
    INGREDIENT = "INGREDIENT"
    SYNONYM = "SYNONYM"
    SCENARIO = "SCENARIO"
    PREFERENCE = "PREFERENCE"
    COMBINED = "COMBINED"


class FailureClass(str, Enum):
    DATA_PROBLEM = "DATA_PROBLEM"
    SCHEMA_PROBLEM = "SCHEMA_PROBLEM"
    RETRIEVAL_PROBLEM = "RETRIEVAL_PROBLEM"
    QUERY_UNDERSTANDING_PROBLEM = "QUERY_UNDERSTANDING_PROBLEM"


class HybridFailureClass(str, Enum):
    QUERY_PARSING_FAILURE = "QUERY_PARSING_FAILURE"
    MISSING_RECIPE_DATA = "MISSING_RECIPE_DATA"
    RULE_RANKING_FAILURE = "RULE_RANKING_FAILURE"
    VECTOR_RETRIEVAL_FAILURE = "VECTOR_RETRIEVAL_FAILURE"
    RERANKING_FAILURE = "RERANKING_FAILURE"


class EvaluationQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=500)
    kind: QueryKind
    expected_recipe_names: list[str] = Field(min_length=1)


class ResolvedEvaluationQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str
    query: str
    kind: QueryKind
    expected_recipe_names: list[str]
    expected_recipe_ids: list[UUID]
    missing_expected_names: list[str] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    recipe_id: UUID
    recipe_name: str
    score: float
    ingredient_coverage: float = Field(ge=0, le=1)
    preference_match: float | None = Field(default=None, ge=0, le=1)
    rerank_breakdown: dict[str, float] | None = None


class QueryUnderstandingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ingredients: list[str]
    max_time_minutes: int | None
    preferences: list[str]
    exclude_spicy: bool
    preferred_max_difficulty: int | None
    scenarios: list[str]
    dish_terms: list[str]


class FailureAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: FailureClass
    reason: str


class HybridFailureAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: HybridFailureClass
    reason: str


class QueryRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str
    query: str
    kind: QueryKind
    expected_recipe_ids: list[UUID]
    query_understanding: QueryUnderstandingResult
    baseline_top_k: list[RetrievalHit]
    vector_top_k: list[RetrievalHit]
    hybrid_top_k: list[RetrievalHit]
    hybrid_rule_candidate_ids: list[UUID]
    hybrid_vector_candidate_ids: list[UUID]
    baseline_recall_at_k: float
    baseline_reciprocal_rank: float
    vector_recall_at_k: float
    vector_reciprocal_rank: float
    hybrid_recall_at_k: float
    hybrid_reciprocal_rank: float
    failure: FailureAnalysis | None = None
    hybrid_failure: HybridFailureAnalysis | None = None


class RetrieverMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_count: int
    recall_at_5: float
    hit_rate_at_5: float
    mrr: float
    average_ingredient_coverage: float | None
    average_preference_match: float | None
    failed_query_count: int


class EvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_recipe_count: int
    query_count: int
    top_k: int
    generated_at: datetime
    evaluation_duration_seconds: float
    baseline: RetrieverMetrics
    local_vector_prototype: RetrieverMetrics
    hybrid: RetrieverMetrics
    failed_queries: list[str]
    local_vector_failed_queries: list[str]
    hybrid_failed_queries: list[str]
    failure_classification_counts: dict[str, int]
    hybrid_failure_classification_counts: dict[str, int]
