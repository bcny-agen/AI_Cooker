"""Fixed Step 17I PostgreSQL holdout benchmark and integrity artifact export."""

from __future__ import annotations

import json
import statistics
import time
from collections import defaultdict
from pathlib import Path
from uuid import UUID

from recipe_pipeline.evaluation.metrics import recall_at_k, reciprocal_rank
from recipe_pipeline.golden.retrieval import build_golden_query_splits
from recipe_pipeline.evaluation.embedding import EmbeddingKind, RecipeEmbeddingTextBuilder
from recipe_pipeline.evaluation.embedding_cache import source_text_hash
from recipe_pipeline.recipe_kb.database import connect
from recipe_pipeline.recipe_kb.config import RecipeKBConfig
from recipe_pipeline.recipe_kb.repository import PostgresRecipeRepository
from recipe_pipeline.recipe_kb.service import RecipeRetrievalService
from recipe_pipeline.sources import load_recipe_jsonl


DEFAULT_OUTPUT = Path("recipe_pipeline/output/recipe_kb")


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _metric(rows: list[dict]) -> dict:
    count = len(rows)
    latencies = sorted(row["latency_ms"] for row in rows)
    return {
        "query_count": count,
        "recall_at_5": round(sum(row["recall_at_5"] for row in rows) / count, 4),
        "hit_rate_at_5": round(sum(row["reciprocal_rank"] > 0 for row in rows) / count, 4),
        "mrr": round(sum(row["reciprocal_rank"] for row in rows) / count, 4),
        "average_latency_ms": round(statistics.fmean(latencies), 3),
        "p50_latency_ms": round(statistics.median(latencies), 3),
        "p95_latency_ms": round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))], 3),
    }


def run_postgres_benchmark(
    config: RecipeKBConfig,
    *,
    output_dir: Path = DEFAULT_OUTPUT,
    dataset_path: Path = Path("recipe_pipeline/output/golden_500/recipes.jsonl"),
) -> dict:
    recipes = load_recipe_jsonl(dataset_path)
    _, holdout = build_golden_query_splits(recipes)
    service = RecipeRetrievalService(config)
    rows = []
    for query in holdout:
        started = time.perf_counter()
        candidates = service.vector_candidates(query["query"], limit=5)
        latency = (time.perf_counter() - started) * 1000
        retrieved = [item.recipe_id for item in candidates]
        expected = [UUID(value) for value in query["expected_recipe_ids"]]
        rows.append(
            {
                **query,
                "top_k": [
                    {
                        "rank": rank,
                        "recipe_id": str(item.recipe_id),
                        "score": round(item.semantic_score, 8),
                        "lane_ranks": item.lane_ranks,
                    }
                    for rank, item in enumerate(candidates, start=1)
                ],
                "recall_at_5": recall_at_k(retrieved, expected),
                "reciprocal_rank": reciprocal_rank(retrieved, expected),
                "latency_ms": round(latency, 3),
            }
        )
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["kind"]].append(row)
    repository = PostgresRecipeRepository(config)
    metrics = {
        "system": "PostgreSQL pgvector exact cosine",
        "overall": _metric(rows),
        "by_query_category": {kind: _metric(items) for kind, items in sorted(grouped.items())},
        "step17h_in_memory_reference": {"recall_at_5": 1.0, "mrr": 0.8558},
    }
    integrity = repository.integrity_report("golden_500_v1")
    expected_hashes = {
        (
            str(recipe.recipe_id),
            "FULL_SEMANTIC" if document.kind == EmbeddingKind.FULL_RECIPE else document.kind.value,
            document.template_version,
            source_text_hash(document.text),
        )
        for recipe in recipes
        for document in RecipeEmbeddingTextBuilder().build(recipe)
    }
    with connect(config) as connection:
        stored_hashes = {
            (str(row[0]), row[1], row[2], row[3])
            for row in connection.execute(
                """
                SELECT re.recipe_id, re.representation_type::text,
                       re.template_version, re.source_text_hash
                FROM recipe_embeddings re JOIN dataset_versions dv USING(dataset_version_id)
                WHERE dv.version_key='golden_500_v1'
                """
            ).fetchall()
        }
    integrity["source_text_hash_mismatches"] = len(expected_hashes ^ stored_hashes)
    _atomic_json(output_dir / "postgres_retrieval_results.json", rows)
    _atomic_json(output_dir / "postgres_retrieval_metrics.json", metrics)
    _atomic_json(output_dir / "data_integrity_report.json", integrity)
    return {"metrics": metrics, "integrity": integrity}
