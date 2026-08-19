"""Independent development/holdout retrieval evaluation for Golden Dataset v1."""

from __future__ import annotations

import time
from collections import defaultdict

from recipe_pipeline.evaluation.hybrid import HybridRecipeRetriever
from recipe_pipeline.evaluation.metrics import recall_at_k, reciprocal_rank
from recipe_pipeline.evaluation.models import QueryKind
from recipe_pipeline.normalization.ingredients import IngredientCatalog
from recipe_pipeline.schemas.recipe import IngredientImportance, RecipeV1, ScenarioTag


_KIND_ORDER = [
    QueryKind.INGREDIENT, QueryKind.SYNONYM, QueryKind.SCENARIO,
    QueryKind.PREFERENCE, QueryKind.COMBINED,
]


def _core_names(recipe: RecipeV1) -> list[str]:
    names = [item.normalized_name for item in recipe.ingredients if item.importance == IngredientImportance.CORE]
    return names[:2] or [recipe.ingredients[0].normalized_name]


def _query_text(recipe: RecipeV1, kind: QueryKind, catalog: IngredientCatalog) -> str:
    names = _core_names(recipe)
    joined = "和".join(names)
    if kind == QueryKind.INGREDIENT:
        return f"我有{joined}，可以做什么？"
    if kind == QueryKind.SYNONYM:
        first = next(item for item in recipe.ingredients if item.normalized_name == names[0])
        entry = catalog.get(first.ingredient_id)
        alias = next((item for item in entry.aliases if item != entry.normalized_name), entry.normalized_name)
        return " ".join([alias, *names[1:]])
    if kind == QueryKind.SCENARIO:
        if ScenarioTag.AIR_FRYER in recipe.tags.scenario:
            prefix = "空气炸锅"
        elif ScenarioTag.BEGINNER_FRIENDLY in recipe.tags.scenario:
            prefix = "适合新手"
        elif ScenarioTag.QUICK_MEAL in recipe.tags.scenario:
            prefix = "快手晚饭"
        else:
            prefix = "家庭家常菜"
        return f"{prefix} {joined}"
    if kind == QueryKind.PREFERENCE:
        preference = "不辣" if recipe.taste_profile.spicy == 0 else "高蛋白"
        return f"{preference} {joined}"
    return f"{recipe.time.total_minutes}分钟内 {joined} {recipe.identity.name[-1]}"


def build_golden_query_splits(recipes: list[RecipeV1], development_count: int = 50, holdout_count: int = 75) -> tuple[list[dict], list[dict]]:
    required = development_count + holdout_count
    if len(recipes) < required:
        raise ValueError(f"at least {required} recipes are required for disjoint evaluation targets")
    catalog = IngredientCatalog()
    ordered = sorted(recipes, key=lambda item: str(item.recipe_id))
    # A fixed stride spreads collections/names while keeping the split deterministic.
    stride_order = ordered[::2] + ordered[1::2]
    rows = []
    seen_query_text: set[str] = set()
    for recipe in stride_order:
        index = len(rows)
        kind = _KIND_ORDER[index % len(_KIND_ORDER)]
        query_text = _query_text(recipe, kind, catalog)
        if query_text in seen_query_text:
            continue
        seen_query_text.add(query_text)
        split = "development" if index < development_count else "holdout"
        rows.append({
            "query_id": f"golden-{split[:3]}-{index + 1:03d}",
            "query": query_text,
            "kind": kind.value,
            "expected_recipe_ids": [str(recipe.recipe_id)],
            "expected_recipe_names": [recipe.identity.name],
        })
        if len(rows) == required:
            break
    if len(rows) != required:
        raise ValueError("not enough unique user-style queries for requested split sizes")
    development = rows[:development_count]
    holdout = rows[development_count:]
    if {item["query"] for item in development} & {item["query"] for item in holdout}:
        raise ValueError("development and holdout query text must be disjoint")
    if {item["expected_recipe_ids"][0] for item in development} & {item["expected_recipe_ids"][0] for item in holdout}:
        raise ValueError("development and holdout relevance targets must be disjoint")
    return development, holdout


def _evaluate_split(retriever: HybridRecipeRetriever, rows: list[dict]) -> dict:
    started = time.monotonic()
    results = []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        response = retriever.retrieve(row["query"], top_k=5)
        ids = [str(item.recipe.recipe_id) for item in response.top_k]
        expected = row["expected_recipe_ids"]
        recall = recall_at_k(ids, expected)
        rr = reciprocal_rank(ids, expected)
        item = {
            **row,
            "top_k": [
                {
                    "rank": hit.rank, "recipe_id": str(hit.recipe.recipe_id),
                    "recipe_name": hit.recipe.identity.name,
                    "score": hit.final_score,
                    "ingredient_coverage": hit.ingredient_coverage,
                    "preference_match": hit.preference_match,
                }
                for hit in response.top_k
            ],
            "recall_at_5": recall, "reciprocal_rank": rr,
            "failure_class": None if rr else (
                "QUERY_PARSING_FAILURE" if not response.parsed_query.ingredient_ids else
                "CANDIDATE_OR_RERANKING_FAILURE"
            ),
        }
        results.append(item)
        grouped[row["kind"]].append(item)

    def metrics(items: list[dict]) -> dict:
        coverages = [item["top_k"][0]["ingredient_coverage"] for item in items if item["top_k"]]
        preferences = [item["top_k"][0]["preference_match"] for item in items if item["top_k"] and item["top_k"][0]["preference_match"] is not None]
        return {
            "query_count": len(items),
            "recall_at_5": round(sum(item["recall_at_5"] for item in items) / len(items), 4) if items else 0.0,
            "hit_rate_at_5": round(sum(item["reciprocal_rank"] > 0 for item in items) / len(items), 4) if items else 0.0,
            "mrr": round(sum(item["reciprocal_rank"] for item in items) / len(items), 4) if items else 0.0,
            "average_ingredient_coverage": round(sum(coverages) / len(coverages), 4) if coverages else None,
            "average_preference_match": round(sum(preferences) / len(preferences), 4) if preferences else None,
            "failed_query_count": sum(item["reciprocal_rank"] == 0 for item in items),
        }
    return {
        "metrics": metrics(results),
        "metrics_by_query_kind": {kind: metrics(items) for kind, items in grouped.items()},
        "results": results,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def run_golden_retrieval_evaluation(recipes: list[RecipeV1]) -> dict:
    development, holdout = build_golden_query_splits(recipes)
    # Fixed Step 17E weights: no tuning is performed against holdout.
    retriever = HybridRecipeRetriever(recipes)
    return {
        "dataset_recipe_count": len(recipes),
        "retriever": "Step17E HybridRecipeRetriever",
        "embedding_provider": "TfidfEmbeddingProvider (offline lexical prototype)",
        "ranking_configuration": {"candidate_k": 30, "rrf_constant": 60, "rule_weight": 10.0, "vector_weight": 1.0, "tuned_in_step17g": False},
        "split_policy": {"development_queries": len(development), "holdout_queries": len(holdout), "query_text_disjoint": True, "target_recipe_ids_disjoint": True},
        "development": _evaluate_split(retriever, development),
        "holdout": _evaluate_split(retriever, holdout),
    }
