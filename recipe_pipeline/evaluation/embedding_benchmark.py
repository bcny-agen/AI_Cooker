"""Step 17H fixed-split multilingual embedding benchmark and artifact export."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from uuid import UUID

from recipe_pipeline.evaluation.baseline import BaselineRecipeRetriever, ParsedQuery
from recipe_pipeline.evaluation.embedding_cache import CachedEmbeddingProvider
from recipe_pipeline.evaluation.embedding_providers import (
    OpenAICompatibleEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    TfidfEmbeddingProvider,
)
from recipe_pipeline.evaluation.hybrid import (
    HybridCandidate,
    HybridRecipeRetriever,
    RetrievalCandidate,
    VectorCandidateRetriever,
)
from recipe_pipeline.evaluation.metrics import recall_at_k, reciprocal_rank
from recipe_pipeline.golden.retrieval import build_golden_query_splits
from recipe_pipeline.schemas.recipe import RecipeV1
from recipe_pipeline.sources import load_recipe_jsonl


DEFAULT_DATASET = Path("recipe_pipeline/output/golden_500/recipes.jsonl")
DEFAULT_OUTPUT = Path("recipe_pipeline/output/embedding_benchmark")
DEFAULT_LOCAL_MODEL = "intfloat/multilingual-e5-small"
MODEL_DOCUMENTATION_URL = "https://huggingface.co/intfloat/multilingual-e5-small"
EVALUATION_MATRIX = (
    "rule_only",
    "tfidf_vector_only",
    "tfidf_hybrid",
    "real_embedding_vector_only",
    "real_embedding_hybrid",
)


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_holdout_isolation(
    development: list[dict[str, Any]], holdout: list[dict[str, Any]]
) -> None:
    if {row["query"] for row in development} & {row["query"] for row in holdout}:
        raise ValueError("development and holdout query leakage detected")
    if {row["expected_recipe_ids"][0] for row in development} & {
        row["expected_recipe_ids"][0] for row in holdout
    }:
        raise ValueError("development and holdout relevance-target leakage detected")


def _hits(candidates: list[RetrievalCandidate] | list[HybridCandidate], baseline, parsed) -> list[dict[str, Any]]:
    output = []
    for fallback_rank, candidate in enumerate(candidates, start=1):
        recipe = candidate.recipe
        metadata = baseline.score_recipe(recipe, parsed)
        score = candidate.final_score if isinstance(candidate, HybridCandidate) else candidate.score
        output.append(
            {
                "rank": getattr(candidate, "rank", fallback_rank),
                "recipe_id": str(recipe.recipe_id),
                "recipe_name": recipe.identity.name,
                "score": round(float(score), 6),
                "ingredient_coverage": metadata.ingredient_coverage,
                "preference_match": metadata.preference_match,
            }
        )
    return output


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    coverages = [row["top_k"][0]["ingredient_coverage"] for row in rows if row["top_k"]]
    preferences = [
        row["top_k"][0]["preference_match"]
        for row in rows
        if row["top_k"] and row["top_k"][0]["preference_match"] is not None
    ]
    count = len(rows)
    return {
        "query_count": count,
        "recall_at_5": round(sum(row["recall_at_5"] for row in rows) / count, 4) if count else 0.0,
        "hit_rate_at_5": round(sum(row["reciprocal_rank"] > 0 for row in rows) / count, 4) if count else 0.0,
        "mrr": round(sum(row["reciprocal_rank"] for row in rows) / count, 4) if count else 0.0,
        "average_ingredient_coverage": round(sum(coverages) / len(coverages), 4) if coverages else None,
        "average_preference_match": round(sum(preferences) / len(preferences), 4) if preferences else None,
        "average_latency_ms": round(sum(row["latency_ms"] for row in rows) / count, 3) if count else 0.0,
        "failed_query_count": sum(row["reciprocal_rank"] == 0 for row in rows),
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["kind"]].append(row)
    return {
        "overall": _metric_summary(rows),
        "by_query_category": {
            kind: _metric_summary(group) for kind, group in sorted(grouped.items())
        },
    }


def _failure_class(
    row: dict[str, Any],
    parsed: ParsedQuery,
    recipes_by_id: dict[UUID, RecipeV1],
    lane: str,
) -> tuple[str, str]:
    expected = [UUID(value) for value in row["expected_recipe_ids"]]
    if not expected or any(recipe_id not in recipes_by_id for recipe_id in expected):
        return "MISSING_RECIPE_COVERAGE", "expected recipe is absent from the immutable dataset"
    if not (
        parsed.ingredient_ids
        or parsed.scenario_tags
        or parsed.preferences
        or parsed.max_minutes is not None
        or parsed.dish_terms
    ):
        return "QUERY_PARSING_FAILURE", "parser extracted no actionable structure"
    if parsed.preferences and not (
        parsed.ingredient_ids or parsed.scenario_tags or parsed.max_minutes is not None or parsed.dish_terms
    ):
        return "UNDER_SPECIFIED_USER_QUERY", "preference-only intent has many valid recipes"
    if row.get("candidate_contains_expected") and row["reciprocal_rank"] == 0:
        return "RERANKING_FAILURE", "expected recipe entered candidates but ranked below top five"
    if lane.endswith("hybrid") and not row.get("candidate_contains_expected"):
        return "CANDIDATE_FUSION_FAILURE", "expected recipe did not enter the fused candidate set"
    if lane.startswith("real_embedding"):
        return "EMBEDDING_SEMANTIC_FAILURE", "semantic vector ranking omitted the fixed relevance target"
    if parsed.ingredient_ids:
        expected_names = {
            item.normalized_name
            for recipe_id in expected
            for item in recipes_by_id[recipe_id].ingredients
        }
        if not expected_names & set(parsed.ingredient_names):
            return "MISSING_ALIAS", "query ingredient normalization does not overlap the expected recipe"
    return "RERANKING_FAILURE", "structured scoring placed the fixed relevance target below top five"


def _evaluate_lane(
    name: str,
    rows: list[dict[str, Any]],
    recipes: list[RecipeV1],
    retriever: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baseline = BaselineRecipeRetriever(recipes)
    evaluated = []
    for row in rows:
        parsed = baseline.parser.parse(row["query"])
        started = time.perf_counter()
        candidate_contains_expected = False
        if name == "rule_only":
            candidates = retriever.retrieve(row["query"], top_k=5)
            hits = [
                {
                    "rank": rank,
                    "recipe_id": str(item.recipe.recipe_id),
                    "recipe_name": item.recipe.identity.name,
                    "score": item.score,
                    "ingredient_coverage": item.ingredient_coverage,
                    "preference_match": item.preference_match,
                }
                for rank, item in enumerate(candidates, start=1)
            ]
        elif name.endswith("hybrid"):
            result = retriever.retrieve(row["query"], top_k=5)
            candidates = result.top_k
            hits = _hits(candidates, baseline, parsed)
            pool = result.rule_candidates + result.vector_candidates
            candidate_contains_expected = bool(
                set(row["expected_recipe_ids"])
                & {str(item.recipe.recipe_id) for item in pool}
            )
        else:
            candidates = retriever.retrieve_candidates(row["query"], parsed, top_k=5)
            hits = _hits(candidates, baseline, parsed)
        latency_ms = (time.perf_counter() - started) * 1000
        retrieved = [UUID(item["recipe_id"]) for item in hits]
        expected = [UUID(value) for value in row["expected_recipe_ids"]]
        evaluated.append(
            {
                **row,
                "system": name,
                "top_k": hits,
                "recall_at_5": recall_at_k(retrieved, expected),
                "reciprocal_rank": reciprocal_rank(retrieved, expected),
                "latency_ms": round(latency_ms, 3),
                "candidate_contains_expected": candidate_contains_expected,
            }
        )
    return evaluated, _metrics(evaluated)


def _build_provider(output_dir: Path):
    provider_name = os.getenv("RECIPE_EMBEDDING_PROVIDER", "sentence-transformers").strip()
    model = os.getenv("RECIPE_EMBEDDING_MODEL", DEFAULT_LOCAL_MODEL).strip()
    batch_size = int(os.getenv("RECIPE_EMBEDDING_BATCH_SIZE", "16"))
    dimensions_value = os.getenv("RECIPE_EMBEDDING_DIMENSIONS", "384").strip()
    dimensions = int(dimensions_value) if dimensions_value else None
    if provider_name == "sentence-transformers":
        provider = SentenceTransformerEmbeddingProvider(
            model,
            dimensions=dimensions,
            batch_size=batch_size,
            device=os.getenv("RECIPE_EMBEDDING_DEVICE", "cpu"),
        )
    elif provider_name == "openai-compatible":
        provider = OpenAICompatibleEmbeddingProvider(
            model=model,
            base_url=os.getenv("RECIPE_EMBEDDING_BASE_URL", ""),
            api_key=os.getenv("RECIPE_EMBEDDING_API_KEY", ""),
            dimensions=dimensions,
            timeout_seconds=float(os.getenv("RECIPE_EMBEDDING_TIMEOUT_SECONDS", "30")),
        )
    else:
        raise ValueError(f"unsupported RECIPE_EMBEDDING_PROVIDER: {provider_name}")
    return CachedEmbeddingProvider(provider, output_dir / "cache", batch_size=batch_size)


def run_embedding_benchmark(
    dataset_path: Path = DEFAULT_DATASET,
    output_dir: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    previous_generation_report: dict[str, Any] = {}
    previous_report_path = output_dir / "embedding_generation_report.json"
    if previous_report_path.exists():
        try:
            previous_generation_report = json.loads(
                previous_report_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            previous_generation_report = {}
    dataset_hash_before = _sha256(dataset_path)
    recipes = load_recipe_jsonl(dataset_path)
    if len(recipes) != 492:
        raise ValueError(f"Step 17H requires exactly 492 recipes, found {len(recipes)}")
    if any(recipe.quality.human_reviewed for recipe in recipes):
        raise ValueError("Golden Dataset contains an unexpected human_reviewed=true record")
    development, holdout = build_golden_query_splits(recipes)
    validate_holdout_isolation(development, holdout)

    provider = _build_provider(output_dir)
    generation_started = time.perf_counter()
    real_vector = VectorCandidateRetriever(recipes, provider=provider)
    embedding_generation_seconds = time.perf_counter() - generation_started
    tfidf_vector = VectorCandidateRetriever(recipes, provider=TfidfEmbeddingProvider())
    rule = BaselineRecipeRetriever(recipes)
    tfidf_hybrid = HybridRecipeRetriever(recipes, embedding_provider=TfidfEmbeddingProvider())

    # Only development queries participate in the real-hybrid vector-weight choice.
    tuning_results = []
    for vector_weight in (0.5, 1.0, 2.0, 5.0, 10.0, 20.0):
        candidate = HybridRecipeRetriever(
            recipes, embedding_provider=provider, rule_weight=10.0, vector_weight=vector_weight
        )
        candidate._vector = real_vector
        rows, metrics = _evaluate_lane("real_embedding_hybrid", development, recipes, candidate)
        tuning_results.append(
            {
                "rule_weight": 10.0,
                "vector_weight": vector_weight,
                **metrics["overall"],
            }
        )
    selected = max(
        tuning_results,
        key=lambda item: (item["recall_at_5"], item["mrr"], -item["vector_weight"]),
    )
    # Reuse the already-built real vector index; only fusion weights vary.
    real_hybrid = HybridRecipeRetriever(
        recipes,
        embedding_provider=provider,
        rule_weight=10.0,
        vector_weight=selected["vector_weight"],
    )
    real_hybrid._vector = real_vector

    systems = {
        "rule_only": rule,
        "tfidf_vector_only": tfidf_vector,
        "tfidf_hybrid": tfidf_hybrid,
        "real_embedding_vector_only": real_vector,
        "real_embedding_hybrid": real_hybrid,
    }
    if tuple(systems) != EVALUATION_MATRIX:
        raise RuntimeError("evaluation matrix is incomplete or reordered")
    all_results: dict[str, dict[str, list[dict[str, Any]]]] = {}
    all_metrics: dict[str, dict[str, dict[str, Any]]] = {}
    for system_name, retriever in systems.items():
        all_results[system_name] = {}
        all_metrics[system_name] = {}
        for split_name, split_rows in (("development", development), ("holdout", holdout)):
            rows, metrics = _evaluate_lane(system_name, split_rows, recipes, retriever)
            all_results[system_name][split_name] = rows
            all_metrics[system_name][split_name] = metrics

    recipes_by_id = {recipe.recipe_id: recipe for recipe in recipes}
    failure_rows = []
    adjudication = []
    for system_name, splits in all_results.items():
        for split_name, rows in splits.items():
            for row in rows:
                if row["reciprocal_rank"] > 0:
                    continue
                parsed = rule.parser.parse(row["query"])
                classification, reason = _failure_class(
                    row, parsed, recipes_by_id, system_name
                )
                failure_rows.append(
                    {
                        "system": system_name,
                        "split": split_name,
                        "query_id": row["query_id"],
                        "query": row["query"],
                        "kind": row["kind"],
                        "classification": classification,
                        "reason": reason,
                    }
                )
                if row["top_k"]:
                    candidate = row["top_k"][0]
                    adjudication.append(
                        {
                            "system": system_name,
                            "split": split_name,
                            "query_id": row["query_id"],
                            "query": row["query"],
                            "fixed_expected_recipe_ids": row["expected_recipe_ids"],
                            "candidate_recipe_id": candidate["recipe_id"],
                            "candidate_recipe_name": candidate["recipe_name"],
                            "reason_for_review": (
                                "top-ranked recipe satisfies parsed deterministic constraints "
                                "but is absent from this run's fixed relevance target"
                            ),
                            "counted_as_correct": False,
                        }
                    )

    real_holdout = all_metrics["real_embedding_hybrid"]["holdout"]["overall"]
    tfidf_holdout = all_metrics["tfidf_hybrid"]["holdout"]["overall"]
    value_over_tfidf = (
        real_holdout["recall_at_5"] > tfidf_holdout["recall_at_5"]
        or (
            real_holdout["recall_at_5"] == tfidf_holdout["recall_at_5"]
            and real_holdout["mrr"] > tfidf_holdout["mrr"]
        )
    )
    real_dimensions = provider.info.dimensions
    recommendation = {
        "recommended_model": provider.info.model if value_over_tfidf else "structured retrieval remains dominant",
        "recommended_provider": provider.info.provider if value_over_tfidf else None,
        "embedding_dimensions": real_dimensions,
        "measurable_value_over_tfidf_hybrid": value_over_tfidf,
        "freeze_vector_dimension": value_over_tfidf,
        "ready_for_postgresql_pgvector": value_over_tfidf,
        "reason": (
            "real multilingual hybrid improved fixed-holdout recall/MRR over TF-IDF hybrid"
            if value_over_tfidf
            else "real multilingual hybrid did not beat the structured TF-IDF hybrid on fixed holdout"
        ),
    }
    config = {
        "dataset": str(dataset_path),
        "dataset_sha256": dataset_hash_before,
        "dataset_recipe_count": len(recipes),
        "top_k": 5,
        "candidate_k": 30,
        "development_queries": len(development),
        "holdout_queries": len(holdout),
        "holdout_isolation": True,
        "real_hybrid_tuning": {
            "split": "development",
            "candidates": tuning_results,
            "selected_rule_weight": 10.0,
            "selected_vector_weight": selected["vector_weight"],
        },
        "representation_template_versions": {
            "recipe": {
                "INGREDIENT": "recipe-ingredient-v2",
                "SCENARIO": "recipe-scenario-v2",
                "FULL_RECIPE": "recipe-full-v2",
            },
            "query": {
                "INGREDIENT": "query-ingredient-v1",
                "SCENARIO": "query-scenario-v1",
                "FULL_RECIPE": "query-full-v1",
            },
        },
    }
    model_info = {
        "models": [
            {
                "role": "lexical_baseline",
                "provider": "local",
                "model": "character-ngram-tfidf",
                "dimensions": tfidf_vector._provider.info.dimensions,
            },
            {
                "role": "real_multilingual_embedding",
                "provider": provider.info.provider,
                "model": provider.info.model,
                "dimensions": real_dimensions,
                "execution_mode": provider.info.execution_mode,
                "documentation": MODEL_DOCUMENTATION_URL if provider.info.model == DEFAULT_LOCAL_MODEL else None,
            },
        ]
    }
    cold_duration = (
        round(embedding_generation_seconds, 3)
        if provider.stats.misses
        else previous_generation_report.get(
            "cold_embedding_generation_duration_seconds"
        )
    )
    cached_duration = (
        round(embedding_generation_seconds, 3)
        if not provider.stats.misses
        else previous_generation_report.get(
            "cached_corpus_initialization_duration_seconds"
        )
    )
    generation_report = {
        "status": "completed",
        "provider": provider.info.provider,
        "model": provider.info.model,
        "dimensions": real_dimensions,
        "recipes_embedded": len(recipes),
        "recipe_representations": len(recipes) * 3,
        "evaluation_queries": len(development) + len(holdout),
        "query_representations_per_query": 3,
        "current_run_corpus_initialization_seconds": round(embedding_generation_seconds, 3),
        "cold_embedding_generation_duration_seconds": cold_duration,
        "cached_corpus_initialization_duration_seconds": cached_duration,
        "current_run_cache_hits": provider.stats.hits,
        "current_run_cache_misses": provider.stats.misses,
        "failures": provider.stats.failures,
    }
    cache_report = {
        "namespace": f"{provider.info.provider}__{provider.info.model}",
        "key_fields": ["embedding_model", "representation_type", "source_text_hash", "template_version"],
        "hits": provider.stats.hits,
        "misses": provider.stats.misses,
        "writes": provider.stats.writes,
        "provider_requests": provider.stats.provider_requests,
        "failures": provider.stats.failures,
        "hit_rate": round(provider.stats.hit_rate, 6),
        "atomic_writes": True,
    }
    failure_report = {
        "counts": dict(Counter(row["classification"] for row in failure_rows)),
        "items": failure_rows,
    }
    _atomic_json(output_dir / "benchmark_config.json", config)
    _atomic_json(output_dir / "embedding_models.json", model_info)
    _atomic_json(output_dir / "embedding_generation_report.json", generation_report)
    _atomic_json(output_dir / "retrieval_metrics.json", all_metrics)
    _atomic_json(output_dir / "retrieval_results.json", all_results)
    _atomic_json(output_dir / "failure_analysis.json", failure_report)
    _atomic_json(output_dir / "relevance_adjudication_candidates.json", adjudication)
    _atomic_json(output_dir / "cache_report.json", cache_report)
    _atomic_json(output_dir / "model_recommendation.json", recommendation)

    dataset_hash_after = _sha256(dataset_path)
    if dataset_hash_after != dataset_hash_before:
        raise RuntimeError("Golden Dataset changed during the benchmark")
    reloaded = load_recipe_jsonl(dataset_path)
    if any(recipe.quality.human_reviewed for recipe in reloaded):
        raise RuntimeError("Golden Dataset human-review flags changed during the benchmark")
    return {
        "metrics": all_metrics,
        "generation_report": generation_report,
        "cache_report": cache_report,
        "recommendation": recommendation,
        "output_dir": str(output_dir.resolve()),
    }
