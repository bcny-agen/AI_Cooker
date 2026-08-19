"""End-to-end offline evaluation and artifact export."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from recipe_pipeline.evaluation.baseline import (
    BaselineCandidate,
    BaselineRecipeRetriever,
)
from recipe_pipeline.evaluation.metrics import (
    build_metrics,
    classify_failure,
    classify_hybrid_failure,
    recall_at_k,
    reciprocal_rank,
)
from recipe_pipeline.evaluation.models import (
    EvaluationMetrics,
    EvaluationQuery,
    QueryRetrievalResult,
    QueryUnderstandingResult,
    ResolvedEvaluationQuery,
    RetrievalHit,
)
from recipe_pipeline.evaluation.query_set import get_evaluation_queries
from recipe_pipeline.evaluation.vector_store import LocalVectorRecipeRetriever
from recipe_pipeline.evaluation.hybrid import HybridCandidate, HybridRecipeRetriever
from recipe_pipeline.schemas.recipe import RecipeV1
from recipe_pipeline.sources import load_recipe_jsonl


@dataclass(frozen=True, slots=True)
class EvaluationArtifacts:
    queries: Path
    retrieval_results: Path
    metrics: Path


@dataclass(frozen=True, slots=True)
class EvaluationRun:
    queries: list[ResolvedEvaluationQuery]
    results: list[QueryRetrievalResult]
    metrics: EvaluationMetrics
    artifacts: EvaluationArtifacts


class RecipeRetrievalEvaluationRunner:
    def run(
        self,
        dataset_path: Path,
        output_dir: Path,
        *,
        top_k: int = 5,
        queries: list[EvaluationQuery] | None = None,
    ) -> EvaluationRun:
        if top_k != 5:
            raise ValueError("Step 17D reports Recall@5 and requires top_k=5")
        started = time.monotonic()
        recipes = load_recipe_jsonl(dataset_path)
        if not recipes:
            raise ValueError("evaluation dataset is empty")
        resolved_queries = self._resolve_queries(
            queries or get_evaluation_queries(), recipes
        )
        baseline = BaselineRecipeRetriever(recipes)
        vector = LocalVectorRecipeRetriever(recipes, baseline)
        hybrid = HybridRecipeRetriever(recipes)
        recipes_by_id = {recipe.recipe_id: recipe for recipe in recipes}
        results = []

        for query in resolved_queries:
            baseline_candidates = baseline.retrieve(query.query, top_k)
            vector_candidates = vector.retrieve(query.query, top_k)
            hybrid_result = hybrid.retrieve(query.query, top_k)
            baseline_ids = [candidate.recipe.recipe_id for candidate in baseline_candidates]
            vector_ids = [candidate.recipe.recipe_id for candidate in vector_candidates]
            hybrid_ids = [candidate.recipe.recipe_id for candidate in hybrid_result.top_k]
            baseline_recall = recall_at_k(baseline_ids, query.expected_recipe_ids)
            baseline_rr = reciprocal_rank(baseline_ids, query.expected_recipe_ids)
            vector_recall = recall_at_k(vector_ids, query.expected_recipe_ids)
            vector_rr = reciprocal_rank(vector_ids, query.expected_recipe_ids)
            hybrid_recall = recall_at_k(hybrid_ids, query.expected_recipe_ids)
            hybrid_rr = reciprocal_rank(hybrid_ids, query.expected_recipe_ids)
            failure = (
                classify_failure(query, baseline, recipes_by_id)
                if baseline_rr == 0
                else None
            )
            rule_candidate_ids = [
                candidate.recipe.recipe_id
                for candidate in hybrid_result.rule_candidates
            ]
            vector_candidate_ids = [
                candidate.recipe.recipe_id
                for candidate in hybrid_result.vector_candidates
            ]
            hybrid_failure = (
                classify_hybrid_failure(
                    query,
                    hybrid_result.parsed_query,
                    rule_candidate_ids,
                    vector_candidate_ids,
                    hybrid_ids,
                )
                if hybrid_rr == 0
                else None
            )
            parsed = hybrid_result.parsed_query
            results.append(
                QueryRetrievalResult(
                    query_id=query.query_id,
                    query=query.query,
                    kind=query.kind,
                    expected_recipe_ids=query.expected_recipe_ids,
                    query_understanding=QueryUnderstandingResult(
                        ingredients=list(parsed.ingredient_names),
                        max_time_minutes=parsed.max_minutes,
                        preferences=sorted(
                            preference.value for preference in parsed.preferences
                        ),
                        exclude_spicy=parsed.exclude_spicy,
                        preferred_max_difficulty=parsed.preferred_max_difficulty,
                        scenarios=sorted(tag.value for tag in parsed.scenario_tags),
                        dish_terms=list(parsed.dish_terms),
                    ),
                    baseline_top_k=self._hits(baseline_candidates),
                    vector_top_k=self._hits(vector_candidates),
                    hybrid_top_k=self._hybrid_hits(hybrid_result.top_k),
                    hybrid_rule_candidate_ids=rule_candidate_ids,
                    hybrid_vector_candidate_ids=vector_candidate_ids,
                    baseline_recall_at_k=round(baseline_recall, 6),
                    baseline_reciprocal_rank=round(baseline_rr, 6),
                    vector_recall_at_k=round(vector_recall, 6),
                    vector_reciprocal_rank=round(vector_rr, 6),
                    hybrid_recall_at_k=round(hybrid_recall, 6),
                    hybrid_reciprocal_rank=round(hybrid_rr, 6),
                    failure=failure,
                    hybrid_failure=hybrid_failure,
                )
            )

        metrics = build_metrics(
            results,
            baseline,
            dataset_recipe_count=len(recipes),
            top_k=top_k,
            duration_seconds=time.monotonic() - started,
        )
        artifacts = self._export(output_dir, resolved_queries, results, metrics)
        return EvaluationRun(resolved_queries, results, metrics, artifacts)

    @staticmethod
    def _resolve_queries(
        queries: list[EvaluationQuery], recipes: list[RecipeV1]
    ) -> list[ResolvedEvaluationQuery]:
        ids_by_name = {recipe.identity.name: recipe.recipe_id for recipe in recipes}
        resolved = []
        for query in queries:
            missing = [
                name for name in query.expected_recipe_names if name not in ids_by_name
            ]
            resolved.append(
                ResolvedEvaluationQuery(
                    query_id=query.query_id,
                    query=query.query,
                    kind=query.kind,
                    expected_recipe_names=query.expected_recipe_names,
                    expected_recipe_ids=[
                        ids_by_name[name]
                        for name in query.expected_recipe_names
                        if name in ids_by_name
                    ],
                    missing_expected_names=missing,
                )
            )
        return resolved

    @staticmethod
    def _hits(candidates: list[BaselineCandidate]) -> list[RetrievalHit]:
        return [
            RetrievalHit(
                rank=rank,
                recipe_id=candidate.recipe.recipe_id,
                recipe_name=candidate.recipe.identity.name,
                score=candidate.score,
                ingredient_coverage=candidate.ingredient_coverage,
                preference_match=candidate.preference_match,
            )
            for rank, candidate in enumerate(candidates, start=1)
        ]

    @staticmethod
    def _hybrid_hits(candidates: list[HybridCandidate]) -> list[RetrievalHit]:
        return [
            RetrievalHit(
                rank=candidate.rank,
                recipe_id=candidate.recipe.recipe_id,
                recipe_name=candidate.recipe.identity.name,
                score=candidate.final_score,
                ingredient_coverage=candidate.ingredient_coverage,
                preference_match=candidate.preference_match,
                rerank_breakdown={
                    key: round(value, 6)
                    for key, value in asdict(candidate.breakdown).items()
                },
            )
            for candidate in candidates
        ]

    @staticmethod
    def _export(
        output_dir: Path,
        queries: list[ResolvedEvaluationQuery],
        results: list[QueryRetrievalResult],
        metrics: EvaluationMetrics,
    ) -> EvaluationArtifacts:
        output_dir.mkdir(parents=True, exist_ok=True)
        query_path = output_dir / "queries.json"
        result_path = output_dir / "retrieval_results.json"
        metrics_path = output_dir / "metrics.json"
        RecipeRetrievalEvaluationRunner._atomic_json(
            query_path,
            [query.model_dump(mode="json") for query in queries],
        )
        RecipeRetrievalEvaluationRunner._atomic_json(
            result_path,
            [result.model_dump(mode="json") for result in results],
        )
        RecipeRetrievalEvaluationRunner._atomic_json(
            metrics_path,
            metrics.model_dump(mode="json"),
        )
        return EvaluationArtifacts(query_path, result_path, metrics_path)

    @staticmethod
    def _atomic_json(path: Path, payload: object) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
