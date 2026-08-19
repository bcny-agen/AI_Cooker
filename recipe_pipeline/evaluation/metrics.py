"""Recall, MRR, coverage, preference metrics, and failure classification."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from recipe_pipeline.evaluation.baseline import BaselineRecipeRetriever, ParsedQuery
from recipe_pipeline.evaluation.models import (
    EvaluationMetrics,
    FailureAnalysis,
    FailureClass,
    HybridFailureAnalysis,
    HybridFailureClass,
    QueryRetrievalResult,
    ResolvedEvaluationQuery,
    RetrieverMetrics,
)
from recipe_pipeline.schemas.recipe import RecipeV1


def recall_at_k(retrieved: list[UUID], expected: list[UUID]) -> float:
    if not expected:
        return 0.0
    return len(set(retrieved) & set(expected)) / len(set(expected))


def reciprocal_rank(retrieved: list[UUID], expected: list[UUID]) -> float:
    expected_set = set(expected)
    for rank, recipe_id in enumerate(retrieved, start=1):
        if recipe_id in expected_set:
            return 1.0 / rank
    return 0.0


def classify_failure(
    query: ResolvedEvaluationQuery,
    baseline: BaselineRecipeRetriever,
    recipes_by_id: dict[UUID, RecipeV1],
) -> FailureAnalysis:
    if query.missing_expected_names or not query.expected_recipe_ids:
        return FailureAnalysis(
            classification=FailureClass.DATA_PROBLEM,
            reason="one or more expected recipes are absent from the evaluated dataset",
        )
    parsed = baseline.parser.parse(query.query)
    if parsed.ingredient_ids:
        expected_ingredients = [
            {item.ingredient_id for item in recipes_by_id[recipe_id].ingredients}
            for recipe_id in query.expected_recipe_ids
            if recipe_id in recipes_by_id
        ]
        if expected_ingredients and not any(
            ingredients & parsed.ingredient_ids for ingredients in expected_ingredients
        ):
            return FailureAnalysis(
                classification=FailureClass.SCHEMA_PROBLEM,
                reason="normalized query ingredients do not overlap expected recipe ingredients",
            )
    if not (
        parsed.ingredient_ids
        or parsed.scenario_tags
        or parsed.preferences
        or parsed.max_minutes is not None
        or parsed.dish_terms
    ):
        return FailureAnalysis(
            classification=FailureClass.QUERY_UNDERSTANDING_PROBLEM,
            reason="baseline parser extracted no ingredient, scenario, time, preference, or dish intent",
        )
    if (
        parsed.preferences
        and not parsed.ingredient_ids
        and not parsed.scenario_tags
        and parsed.max_minutes is None
        and not parsed.dish_terms
    ):
        return FailureAnalysis(
            classification=FailureClass.QUERY_UNDERSTANDING_PROBLEM,
            reason="preference-only query is under-specified and leaves many tied candidates",
        )
    return FailureAnalysis(
        classification=FailureClass.RETRIEVAL_PROBLEM,
        reason="expected recipe exists and query intent was parsed, but ranking placed it below top-k",
    )


def build_metrics(
    results: list[QueryRetrievalResult],
    baseline: BaselineRecipeRetriever,
    *,
    dataset_recipe_count: int,
    top_k: int,
    duration_seconds: float,
) -> EvaluationMetrics:
    baseline_metrics = _retriever_metrics(results, baseline, lane="baseline")
    vector_metrics = _retriever_metrics(results, baseline, lane="vector")
    hybrid_metrics = _retriever_metrics(results, baseline, lane="hybrid")
    failed = [result.query_id for result in results if result.failure is not None]
    vector_failed = [
        result.query_id
        for result in results
        if result.vector_reciprocal_rank == 0
    ]
    hybrid_failed = [
        result.query_id
        for result in results
        if result.hybrid_reciprocal_rank == 0
    ]
    failure_counts = Counter(
        result.failure.classification.value
        for result in results
        if result.failure is not None
    )
    hybrid_failure_counts = Counter(
        result.hybrid_failure.classification.value
        for result in results
        if result.hybrid_failure is not None
    )
    return EvaluationMetrics(
        dataset_recipe_count=dataset_recipe_count,
        query_count=len(results),
        top_k=top_k,
        generated_at=datetime.now(timezone.utc),
        evaluation_duration_seconds=round(duration_seconds, 3),
        baseline=baseline_metrics,
        local_vector_prototype=vector_metrics,
        hybrid=hybrid_metrics,
        failed_queries=failed,
        local_vector_failed_queries=vector_failed,
        hybrid_failed_queries=hybrid_failed,
        failure_classification_counts=dict(failure_counts),
        hybrid_failure_classification_counts=dict(hybrid_failure_counts),
    )


def _retriever_metrics(
    results: list[QueryRetrievalResult],
    baseline: BaselineRecipeRetriever,
    *,
    lane: str,
) -> RetrieverMetrics:
    if lane == "baseline":
        recalls = [result.baseline_recall_at_k for result in results]
        reciprocal_ranks = [result.baseline_reciprocal_rank for result in results]
        hit_lists = [result.baseline_top_k for result in results]
    elif lane == "vector":
        recalls = [result.vector_recall_at_k for result in results]
        reciprocal_ranks = [result.vector_reciprocal_rank for result in results]
        hit_lists = [result.vector_top_k for result in results]
    elif lane == "hybrid":
        recalls = [result.hybrid_recall_at_k for result in results]
        reciprocal_ranks = [result.hybrid_reciprocal_rank for result in results]
        hit_lists = [result.hybrid_top_k for result in results]
    else:
        raise ValueError(f"unknown metrics lane: {lane}")
    coverage_values = []
    preference_values = []
    for result, hits in zip(results, hit_lists):
        if not hits:
            continue
        parsed = baseline.parser.parse(result.query)
        if parsed.ingredient_ids:
            coverage_values.append(hits[0].ingredient_coverage)
        if parsed.preferences and hits[0].preference_match is not None:
            preference_values.append(hits[0].preference_match)
    return RetrieverMetrics(
        query_count=len(results),
        recall_at_5=round(sum(recalls) / len(recalls), 4) if recalls else 0.0,
        hit_rate_at_5=round(
            sum(value > 0 for value in reciprocal_ranks) / len(reciprocal_ranks), 4
        )
        if reciprocal_ranks
        else 0.0,
        mrr=round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4)
        if reciprocal_ranks
        else 0.0,
        average_ingredient_coverage=(
            round(sum(coverage_values) / len(coverage_values), 4)
            if coverage_values
            else None
        ),
        average_preference_match=(
            round(sum(preference_values) / len(preference_values), 4)
            if preference_values
            else None
        ),
        failed_query_count=sum(value == 0 for value in reciprocal_ranks),
    )


def classify_hybrid_failure(
    query: ResolvedEvaluationQuery,
    parsed: ParsedQuery,
    rule_candidate_ids: list[UUID],
    vector_candidate_ids: list[UUID],
    hybrid_top_ids: list[UUID],
) -> HybridFailureAnalysis:
    expected = set(query.expected_recipe_ids)
    if query.missing_expected_names or not expected:
        return HybridFailureAnalysis(
            classification=HybridFailureClass.MISSING_RECIPE_DATA,
            reason="expected recipe is absent from the evaluated dataset",
        )
    if not (
        parsed.ingredient_ids
        or parsed.scenario_tags
        or parsed.preferences
        or parsed.max_minutes is not None
        or parsed.dish_terms
    ) or (
        parsed.preferences
        and not parsed.ingredient_ids
        and not parsed.scenario_tags
        and parsed.max_minutes is None
        and not parsed.dish_terms
    ):
        return HybridFailureAnalysis(
            classification=HybridFailureClass.QUERY_PARSING_FAILURE,
            reason="deterministic parsing produced insufficient constraints for a stable top-k",
        )
    if expected & set(hybrid_top_ids):
        raise ValueError("hybrid failure classification called for a successful query")
    rule_has_expected = bool(expected & set(rule_candidate_ids))
    vector_has_expected = bool(expected & set(vector_candidate_ids))
    if not rule_has_expected and not vector_has_expected:
        semantic_only = bool(parsed.scenario_tags or parsed.preferences) and not parsed.ingredient_ids
        return HybridFailureAnalysis(
            classification=(
                HybridFailureClass.VECTOR_RETRIEVAL_FAILURE
                if semantic_only
                else HybridFailureClass.RULE_RANKING_FAILURE
            ),
            reason="expected recipe did not enter the fused candidate pool",
        )
    return HybridFailureAnalysis(
        classification=HybridFailureClass.RERANKING_FAILURE,
        reason="expected recipe entered the candidate pool but final reranking placed it below top-k",
    )
