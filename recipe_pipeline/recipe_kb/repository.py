"""Exact pgvector retrieval repository with relational deterministic filters."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import UUID

from recipe_pipeline.evaluation.embedding import EmbeddingKind, RECIPE_TEMPLATE_VERSIONS
from recipe_pipeline.evaluation.embedding_providers import validate_vector_dimensions
from recipe_pipeline.recipe_kb.config import RecipeKBConfig
from recipe_pipeline.recipe_kb.database import connect


REPRESENTATION_DB_NAMES = {
    EmbeddingKind.INGREDIENT: "INGREDIENT",
    EmbeddingKind.SCENARIO: "SCENARIO",
    EmbeddingKind.FULL_RECIPE: "FULL_SEMANTIC",
}
REPRESENTATION_WEIGHTS = {
    EmbeddingKind.INGREDIENT: 0.45,
    EmbeddingKind.SCENARIO: 0.25,
    EmbeddingKind.FULL_RECIPE: 0.30,
}


def vector_literal(vector) -> str:
    return "[" + ",".join(format(float(value), ".9g") for value in vector) + "]"


@dataclass(frozen=True, slots=True)
class RepositoryFilters:
    excluded_ingredient_ids: frozenset[UUID] = frozenset()
    excluded_allergens: frozenset[str] = frozenset()
    required_dietary_tags: frozenset[str] = frozenset()
    unavailable_equipment: frozenset[str] = frozenset()
    available_equipment: frozenset[str] = frozenset()
    exclude_spicy: bool = False
    max_total_minutes: int | None = None
    max_difficulty: int | None = None
    servings: int | None = None


@dataclass(frozen=True, slots=True)
class ExactVectorCandidate:
    recipe_id: UUID
    lane_ranks: dict[str, int]
    lane_similarities: dict[str, float]
    semantic_score: float


class PostgresRecipeRepository:
    def __init__(
        self,
        config: RecipeKBConfig,
        *,
        connection_provider: Callable[[], AbstractContextManager[Any]] | None = None,
    ):
        self.config = config
        self._connection_provider = connection_provider

    def _connection(self) -> AbstractContextManager[Any]:
        if self._connection_provider is not None:
            return self._connection_provider()
        return connect(self.config)

    def dataset_id(self, version_key: str, *, allow_experimental: bool = False) -> UUID:
        allowed = (
            ("EXPERIMENTAL", "VALIDATED", "ACTIVE")
            if allow_experimental
            else ("VALIDATED", "ACTIVE")
        )
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT dataset_version_id, embedding_model, embedding_dimension
                FROM dataset_versions
                WHERE version_key=%s AND status=ANY(%s)
                """,
                (version_key, list(allowed)),
            ).fetchone()
        if not row:
            raise LookupError(f"Recipe dataset {version_key!r} is unavailable")
        if row[1] != self.config.embedding_model or row[2] != self.config.embedding_dimension:
            raise LookupError(
                f"Recipe dataset {version_key!r} embedding metadata does not "
                "match the configured Agent embedding model"
            )
        return row[0]

    def eligible_recipe_ids(
        self, dataset_version_id: UUID, filters: RepositoryFilters
    ) -> list[UUID]:
        clauses = ["r.dataset_version_id = %s"]
        parameters: list[Any] = [dataset_version_id]
        if filters.exclude_spicy:
            clauses.append("tp.spicy = 0")
        if filters.max_total_minutes is not None:
            clauses.append("r.total_minutes <= %s")
            parameters.append(filters.max_total_minutes)
        if filters.max_difficulty is not None:
            clauses.append("r.difficulty <= %s")
            parameters.append(filters.max_difficulty)
        if filters.servings is not None:
            clauses.append("r.min_servings <= %s AND r.max_servings >= %s")
            parameters.extend((filters.servings, filters.servings))
        if filters.unavailable_equipment:
            clauses.append("NOT (r.required_equipment && %s::text[])")
            parameters.append(sorted(filters.unavailable_equipment))
        if filters.available_equipment:
            clauses.append("r.required_equipment <@ %s::text[]")
            parameters.append(sorted(filters.available_equipment))
        if filters.excluded_ingredient_ids:
            clauses.append(
                """NOT EXISTS (
                    SELECT 1 FROM recipe_ingredients ri
                    WHERE ri.dataset_version_id=r.dataset_version_id
                      AND ri.recipe_id=r.recipe_id
                      AND ri.ingredient_id=ANY(%s::uuid[])
                )"""
            )
            parameters.append(list(filters.excluded_ingredient_ids))
        if filters.excluded_allergens:
            clauses.append(
                """NOT EXISTS (
                    SELECT 1 FROM recipe_tags rt JOIN tags t USING(tag_id)
                    WHERE rt.dataset_version_id=r.dataset_version_id
                      AND rt.recipe_id=r.recipe_id AND t.tag_type='ALLERGEN'
                      AND t.tag_value=ANY(%s::text[])
                )"""
            )
            parameters.append(sorted(filters.excluded_allergens))
        for dietary in sorted(filters.required_dietary_tags):
            acceptable = [dietary]
            if dietary == "VEGETARIAN":
                acceptable.append("VEGAN")
            clauses.append(
                """EXISTS (
                    SELECT 1 FROM recipe_tags rt JOIN tags t USING(tag_id)
                    WHERE rt.dataset_version_id=r.dataset_version_id
                      AND rt.recipe_id=r.recipe_id AND t.tag_type='DIETARY'
                      AND t.tag_value=ANY(%s::text[])
                )"""
            )
            parameters.append(acceptable)
        sql = (
            "SELECT r.recipe_id FROM recipes r "
            "JOIN recipe_taste_profiles tp USING(dataset_version_id, recipe_id) WHERE "
            + " AND ".join(clauses)
        )
        with self._connection() as connection:
            return [row[0] for row in connection.execute(sql, parameters).fetchall()]

    def exact_vector_candidates(
        self,
        *,
        dataset_version_id: UUID,
        query_vectors: dict[EmbeddingKind, tuple[float, ...]],
        eligible_recipe_ids: list[UUID],
        candidate_k_per_lane: int = 30,
    ) -> list[ExactVectorCandidate]:
        if not eligible_recipe_ids:
            return []
        validate_vector_dimensions(
            list(query_vectors.values()), self.config.embedding_dimension
        )
        lane_rows: dict[EmbeddingKind, list[tuple[UUID, float]]] = {}
        with self._connection() as connection:
            for kind in EmbeddingKind:
                rows = connection.execute(
                    """
                    SELECT recipe_id, 1 - (embedding <=> %s::vector) AS similarity
                    FROM recipe_embeddings
                    WHERE dataset_version_id=%s
                      AND recipe_id=ANY(%s::uuid[])
                      AND representation_type=%s
                      AND embedding_model=%s
                      AND embedding_dimension=%s
                      AND template_version=%s
                    ORDER BY embedding <=> %s::vector, recipe_id
                    LIMIT %s
                    """,
                    (
                        vector_literal(query_vectors[kind]), dataset_version_id,
                        eligible_recipe_ids, REPRESENTATION_DB_NAMES[kind],
                        self.config.embedding_model, self.config.embedding_dimension,
                        RECIPE_TEMPLATE_VERSIONS[kind], vector_literal(query_vectors[kind]),
                        candidate_k_per_lane,
                    ),
                ).fetchall()
                lane_rows[kind] = [(row[0], float(row[1])) for row in rows]
            union_ids = sorted(
                {recipe_id for rows in lane_rows.values() for recipe_id, _ in rows},
                key=str,
            )
            if not union_ids:
                return []
            all_scores: dict[UUID, dict[EmbeddingKind, float]] = {
                recipe_id: {} for recipe_id in union_ids
            }
            for kind in EmbeddingKind:
                rows = connection.execute(
                    """
                    SELECT recipe_id, 1 - (embedding <=> %s::vector) AS similarity
                    FROM recipe_embeddings
                    WHERE dataset_version_id=%s AND recipe_id=ANY(%s::uuid[])
                      AND representation_type=%s AND embedding_model=%s
                      AND embedding_dimension=%s AND template_version=%s
                    """,
                    (
                        vector_literal(query_vectors[kind]), dataset_version_id, union_ids,
                        REPRESENTATION_DB_NAMES[kind], self.config.embedding_model,
                        self.config.embedding_dimension, RECIPE_TEMPLATE_VERSIONS[kind],
                    ),
                ).fetchall()
                for recipe_id, score in rows:
                    all_scores[recipe_id][kind] = float(score)
        ranks = {
            kind: {recipe_id: rank for rank, (recipe_id, _) in enumerate(rows, start=1)}
            for kind, rows in lane_rows.items()
        }
        candidates = []
        for recipe_id, scores in all_scores.items():
            if set(scores) != set(EmbeddingKind):
                continue
            candidates.append(
                ExactVectorCandidate(
                    recipe_id=recipe_id,
                    lane_ranks={kind.value: ranks[kind].get(recipe_id, candidate_k_per_lane + 1) for kind in EmbeddingKind},
                    lane_similarities={kind.value: round(scores[kind], 8) for kind in EmbeddingKind},
                    semantic_score=sum(
                        scores[kind] * REPRESENTATION_WEIGHTS[kind]
                        for kind in EmbeddingKind
                    ),
                )
            )
        candidates.sort(key=lambda item: (-item.semantic_score, str(item.recipe_id)))
        return candidates

    def recipe_details(
        self, dataset_version_id: UUID, recipe_ids: list[UUID]
    ) -> dict[UUID, dict[str, Any]]:
        if not recipe_ids:
            return {}
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT r.recipe_id, r.name, r.summary, r.total_minutes, r.difficulty,
                       r.confidence_score, r.required_equipment,
                       tp.spicy, tp.sweet, tp.sour, tp.salty, tp.umami, tp.richness,
                       COALESCE((SELECT jsonb_agg(jsonb_build_object(
                           'id', ri.ingredient_id, 'name', i.canonical_name,
                           'role', ri.role, 'importance', ri.importance
                       ) ORDER BY ri.position)
                       FROM recipe_ingredients ri JOIN ingredients i USING(ingredient_id)
                       WHERE ri.dataset_version_id=r.dataset_version_id AND ri.recipe_id=r.recipe_id), '[]'),
                       COALESCE((SELECT array_agg(t.tag_value ORDER BY t.tag_value)
                       FROM recipe_tags rt JOIN tags t USING(tag_id)
                       WHERE rt.dataset_version_id=r.dataset_version_id AND rt.recipe_id=r.recipe_id
                         AND t.tag_type='SCENARIO'), '{}'),
                       COALESCE((SELECT array_agg(t.tag_value ORDER BY t.tag_value)
                       FROM recipe_tags rt JOIN tags t USING(tag_id)
                       WHERE rt.dataset_version_id=r.dataset_version_id AND rt.recipe_id=r.recipe_id
                         AND t.tag_type='DIETARY'), '{}'),
                       COALESCE((SELECT jsonb_agg(jsonb_build_object(
                           'order', rs.step_order,
                           'instruction', rs.instruction,
                           'duration_minutes', rs.duration_minutes,
                           'safety_note', rs.safety_note
                       ) ORDER BY rs.step_order)
                       FROM recipe_steps rs
                       WHERE rs.dataset_version_id=r.dataset_version_id
                         AND rs.recipe_id=r.recipe_id), '[]'),
                       COALESCE((SELECT jsonb_agg(jsonb_build_object(
                           'ingredient', source_i.canonical_name,
                           'substitute', substitute_i.canonical_name,
                           'note', ris.note
                       ) ORDER BY source_i.canonical_name, substitute_i.canonical_name)
                       FROM recipe_ingredient_substitutes ris
                       JOIN ingredients source_i
                         ON source_i.ingredient_id=ris.recipe_ingredient_id
                       JOIN ingredients substitute_i
                         ON substitute_i.ingredient_id=ris.substitute_ingredient_id
                       WHERE ris.dataset_version_id=r.dataset_version_id
                         AND ris.recipe_id=r.recipe_id), '[]')
                FROM recipes r
                JOIN recipe_taste_profiles tp USING(dataset_version_id, recipe_id)
                WHERE r.dataset_version_id=%s AND r.recipe_id=ANY(%s::uuid[])
                """,
                (dataset_version_id, recipe_ids),
            ).fetchall()
        return {
            row[0]: {
                "recipe_id": row[0], "name": row[1], "summary": row[2],
                "total_minutes": row[3], "difficulty": row[4],
                "quality_score": float(row[5]), "required_equipment": list(row[6]),
                "taste": {
                    "spicy": row[7], "sweet": row[8], "sour": row[9],
                    "salty": row[10], "umami": row[11], "richness": row[12],
                },
                "ingredients": row[13], "scenario_tags": list(row[14]),
                "dietary_tags": list(row[15]), "steps": row[16],
                "substitutions": row[17],
            }
            for row in rows
        }

    def alias_resolution(self, alias: str) -> tuple[UUID, str] | None:
        from recipe_pipeline.normalization.ingredients import normalize_lookup_key

        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT i.ingredient_id, i.canonical_name
                FROM ingredient_aliases ia JOIN ingredients i USING(ingredient_id)
                WHERE ia.alias_key=%s
                """,
                (normalize_lookup_key(alias),),
            ).fetchone()
        return (row[0], row[1]) if row else None

    def integrity_report(self, version_key: str) -> dict[str, Any]:
        with self._connection() as connection:
            dataset = connection.execute(
                "SELECT dataset_version_id FROM dataset_versions WHERE version_key=%s",
                (version_key,),
            ).fetchone()
            if not dataset:
                raise LookupError(version_key)
            dataset_id = dataset[0]
            counts = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM recipes WHERE dataset_version_id=%s),
                  (SELECT count(*) FROM ingredients),
                  (SELECT count(*) FROM ingredient_aliases),
                  (SELECT count(*) FROM recipe_ingredients WHERE dataset_version_id=%s),
                  (SELECT count(*) FROM recipe_embeddings WHERE dataset_version_id=%s),
                  (SELECT count(*) FROM recipe_embeddings WHERE dataset_version_id=%s AND vector_dims(embedding)<>embedding_dimension),
                  (SELECT count(*) FROM recipes r WHERE r.dataset_version_id=%s AND
                     (SELECT count(*) FROM recipe_embeddings e WHERE e.dataset_version_id=r.dataset_version_id AND e.recipe_id=r.recipe_id)<>3),
                  (SELECT count(*) FROM recipes WHERE dataset_version_id=%s AND (human_reviewed OR quality_status<>'REVIEW')),
                  (SELECT count(*) FROM recipe_sources WHERE dataset_version_id=%s AND source_type<>'AI_SYNTHETIC'),
                  (SELECT count(*) FROM dataset_versions WHERE status='ACTIVE'),
                  (SELECT count(*) FROM recipe_ingredients ri LEFT JOIN recipes r
                     ON r.dataset_version_id=ri.dataset_version_id AND r.recipe_id=ri.recipe_id
                     WHERE ri.dataset_version_id=%s AND r.recipe_id IS NULL),
                  (SELECT count(*) FROM recipe_embeddings re LEFT JOIN recipes r
                     ON r.dataset_version_id=re.dataset_version_id AND r.recipe_id=re.recipe_id
                     WHERE re.dataset_version_id=%s AND r.recipe_id IS NULL)
                """,
                (
                    dataset_id, dataset_id, dataset_id, dataset_id, dataset_id,
                    dataset_id, dataset_id, dataset_id, dataset_id,
                ),
            ).fetchone()
            extension = connection.execute(
                "SELECT current_setting('server_version'), extversion FROM pg_extension WHERE extname='vector'"
            ).fetchone()
        return {
            "postgresql_version": extension[0], "pgvector_version": extension[1],
            "recipes": counts[0], "ingredients": counts[1], "aliases": counts[2],
            "recipe_ingredients": counts[3], "embeddings": counts[4],
            "dimension_mismatches": counts[5], "recipes_missing_representations": counts[6],
            "provenance_violations": counts[7] + counts[8], "active_dataset_count": counts[9],
            "orphan_recipe_ingredients": counts[10], "orphan_embeddings": counts[11],
        }
