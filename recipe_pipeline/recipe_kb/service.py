"""Offline semantic recall → hard filters → structured reranking service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from recipe_pipeline.evaluation.baseline import Preference, RecipeQueryParser
from recipe_pipeline.evaluation.baseline import ParsedQuery
from recipe_pipeline.evaluation.embedding import (
    EmbeddingKind,
    QueryEmbeddingTextBuilder,
)
from recipe_pipeline.evaluation.embedding_cache import CachedEmbeddingProvider
from recipe_pipeline.evaluation.embedding_providers import (
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from recipe_pipeline.normalization.ingredients import (
    IngredientCatalog,
    normalize_lookup_key,
)
from recipe_pipeline.recipe_kb.config import RecipeKBConfig
from recipe_pipeline.recipe_kb.repository import (
    PostgresRecipeRepository,
    RepositoryFilters,
)


DEFAULT_CACHE_DIR = Path("recipe_pipeline/output/embedding_benchmark/cache")


@dataclass(frozen=True, slots=True)
class RecipeRetrievalRequest:
    query: str
    available_ingredients: tuple[str, ...] = ()
    excluded_ingredients: tuple[str, ...] = ()
    excluded_allergens: tuple[str, ...] = ()
    dietary_constraints: tuple[str, ...] = ()
    taste_preferences: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    unavailable_equipment: tuple[str, ...] = ()
    scenario_tags: tuple[str, ...] = ()
    max_total_minutes: int | None = None
    max_difficulty: int | None = None
    servings: int | None = None
    limit: int = 5
    dataset_version: str = "golden_500_v1"


@dataclass(frozen=True, slots=True)
class RecipeSearchResult:
    recipe_id: UUID
    name: str
    matched_ingredients: list[str]
    missing_required_ingredients: list[str]
    total_minutes: int
    difficulty: int
    taste_tags: list[str]
    scenario_tags: list[str]
    quality_score: float
    why_matched: list[str]
    summary: str
    steps: list[dict]
    suggested_substitutions: list[dict]
    semantic_score: float = field(repr=False)
    score: float = field(repr=False)

    def compact_dict(self) -> dict:
        return {
            "recipeId": str(self.recipe_id), "name": self.name,
            "matchedIngredients": self.matched_ingredients,
            "missingRequiredIngredients": self.missing_required_ingredients,
            "totalMinutes": self.total_minutes, "difficulty": self.difficulty,
            "tasteTags": self.taste_tags, "scenarioTags": self.scenario_tags,
            "qualityScore": self.quality_score, "whyMatched": self.why_matched,
            "summary": self.summary, "steps": self.steps,
            "suggestedSubstitutions": self.suggested_substitutions,
        }


class RecipeRetrievalService:
    def __init__(
        self,
        config: RecipeKBConfig,
        *,
        repository: PostgresRecipeRepository | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        cache_dir: Path = DEFAULT_CACHE_DIR,
    ):
        self.config = config
        self.repository = repository or PostgresRecipeRepository(config)
        provider = embedding_provider or SentenceTransformerEmbeddingProvider(
            config.embedding_model,
            dimensions=config.embedding_dimension,
            batch_size=config.embedding_batch_size,
            device=config.embedding_device,
        )
        self._provider = CachedEmbeddingProvider(
            provider, cache_dir, batch_size=config.embedding_batch_size
        )
        self._parser = RecipeQueryParser()
        self._query_builder = QueryEmbeddingTextBuilder()
        self._catalog = IngredientCatalog()

    def search_recipes(self, request: RecipeRetrievalRequest) -> list[RecipeSearchResult]:
        if not (1 <= request.limit <= 50):
            raise ValueError("limit must be between 1 and 50")
        parsed = self._parser.parse(request.query)
        desired_ids, desired_names = self._resolve_ingredients(
            (*parsed.ingredient_names, *request.available_ingredients)
        )
        excluded_ids, _ = self._resolve_ingredients(request.excluded_ingredients)
        dietary = {
            value.upper() for value in request.dietary_constraints
        } | {
            item.value for item in parsed.preferences if item in {Preference.VEGETARIAN, Preference.VEGAN}
        }
        filters = RepositoryFilters(
            excluded_ingredient_ids=frozenset(
                set(parsed.excluded_ingredient_ids) | set(excluded_ids)
            ),
            excluded_allergens=frozenset(
                {item.value for item in parsed.excluded_allergens}
                | {value.upper() for value in request.excluded_allergens}
            ),
            required_dietary_tags=frozenset(dietary),
            unavailable_equipment=frozenset(
                {item.value for item in parsed.unavailable_equipment}
                | {value.upper() for value in request.unavailable_equipment}
            ),
            available_equipment=frozenset(value.upper() for value in request.equipment),
            exclude_spicy=parsed.exclude_spicy or any(
                value.casefold() in {"non_spicy", "non-spicy", "不辣"}
                for value in request.taste_preferences
            ),
            max_total_minutes=request.max_total_minutes or parsed.max_minutes,
            max_difficulty=request.max_difficulty or parsed.preferred_max_difficulty,
            servings=request.servings,
        )
        dataset_id = self.repository.dataset_id(request.dataset_version)
        eligible = self.repository.eligible_recipe_ids(dataset_id, filters)
        semantic_query = self._with_structured_semantics(
            parsed,
            desired_ids=desired_ids,
            desired_names=desired_names,
            request=request,
        )
        texts = self._query_builder.build(semantic_query)
        contexts = self._query_builder.contexts()
        vectors = self._provider.embed_queries(
            [texts[kind] for kind in EmbeddingKind],
            [contexts[kind] for kind in EmbeddingKind],
        )
        candidates = self.repository.exact_vector_candidates(
            dataset_version_id=dataset_id,
            query_vectors={kind: vector for kind, vector in zip(EmbeddingKind, vectors)},
            eligible_recipe_ids=eligible,
            candidate_k_per_lane=max(30, request.limit * 4),
        )
        details = self.repository.recipe_details(
            dataset_id, [item.recipe_id for item in candidates]
        )
        requested_scenarios = set(request.scenario_tags) | {
            item.value for item in parsed.scenario_tags
        }
        ranked = []
        for candidate in candidates:
            detail = details[candidate.recipe_id]
            ingredients = detail["ingredients"]
            ingredient_ids = {UUID(str(item["id"])) for item in ingredients}
            matched = [
                name for ingredient_id, name in zip(desired_ids, desired_names)
                if ingredient_id in ingredient_ids
            ]
            required = [
                item["name"] for item in ingredients if item["role"] == "REQUIRED"
            ]
            missing = [name for name in required if name not in set(desired_names)]
            coverage = len(set(desired_ids) & ingredient_ids) / len(desired_ids) if desired_ids else 0.0
            scenario_matches = requested_scenarios & set(detail["scenario_tags"])
            # The validated semantic score stays dominant. Structured signals only
            # resolve close candidates; hard constraints were already applied in SQL.
            rerank_score = (
                candidate.semantic_score
                + coverage * 0.02
                + len(scenario_matches) * 0.005
                + detail["quality_score"] * 0.0001
            )
            why = ["multilingual semantic match"]
            if matched:
                why.append("matched ingredients: " + ", ".join(matched))
            if scenario_matches:
                why.append("matched scenario: " + ", ".join(sorted(scenario_matches)))
            if filters.max_total_minutes is not None:
                why.append(f"within {filters.max_total_minutes} minute limit")
            if dietary:
                why.append(
                    "satisfies dietary constraints: "
                    + ", ".join(sorted(dietary))
                )
            if filters.exclude_spicy:
                why.append("non-spicy constraint satisfied")
            taste_tags = [
                f"{name}:{value}/5" for name, value in detail["taste"].items() if value
            ]
            ranked.append(
                RecipeSearchResult(
                    candidate.recipe_id, detail["name"], matched, missing,
                    detail["total_minutes"], detail["difficulty"], taste_tags,
                    detail["scenario_tags"], round(detail["quality_score"], 4),
                    why, detail["summary"], detail["steps"],
                    detail["substitutions"], candidate.semantic_score,
                    rerank_score,
                )
            )
        ranked.sort(key=lambda item: (-item.score, str(item.recipe_id)))
        return ranked[: request.limit]

    def vector_candidates(
        self,
        query: str,
        *,
        dataset_version: str = "golden_500_v1",
        limit: int = 5,
    ):
        """Exact vector-only lane used for Step 17H/17I parity evaluation."""
        parsed = self._parser.parse(query)
        dataset_id = self.repository.dataset_id(dataset_version)
        filters = RepositoryFilters(
            excluded_ingredient_ids=parsed.excluded_ingredient_ids,
            excluded_allergens=frozenset(item.value for item in parsed.excluded_allergens),
            required_dietary_tags=frozenset(
                item.value
                for item in parsed.preferences
                if item in {Preference.VEGETARIAN, Preference.VEGAN}
            ),
            unavailable_equipment=frozenset(item.value for item in parsed.unavailable_equipment),
            exclude_spicy=parsed.exclude_spicy,
            max_total_minutes=parsed.max_minutes,
            max_difficulty=parsed.preferred_max_difficulty,
        )
        eligible = self.repository.eligible_recipe_ids(dataset_id, filters)
        texts = self._query_builder.build(parsed)
        contexts = self._query_builder.contexts()
        vectors = self._provider.embed_queries(
            [texts[kind] for kind in EmbeddingKind],
            [contexts[kind] for kind in EmbeddingKind],
        )
        candidates = self.repository.exact_vector_candidates(
            dataset_version_id=dataset_id,
            query_vectors={kind: vector for kind, vector in zip(EmbeddingKind, vectors)},
            eligible_recipe_ids=eligible,
            candidate_k_per_lane=max(30, limit),
        )
        return candidates[:limit]

    @staticmethod
    def _with_structured_semantics(
        parsed: ParsedQuery,
        *,
        desired_ids: list[UUID],
        desired_names: list[str],
        request: RecipeRetrievalRequest,
    ) -> ParsedQuery:
        """Merge explicit tool fields into the immutable Step 17H query views."""

        # Importing the enums here keeps this service's public request fields
        # string-based while rejecting unknown structured tags deterministically.
        from recipe_pipeline.schemas.recipe import ScenarioTag

        scenario_values = {item.value: item for item in ScenarioTag}
        scenarios = set(parsed.scenario_tags)
        scenarios.update(
            scenario_values[value.upper()]
            for value in request.scenario_tags
            if value.upper() in scenario_values
        )
        preference_values = {item.value: item for item in Preference}
        preferences = set(parsed.preferences)
        preferences.update(
            preference_values[value.upper()]
            for value in (*request.dietary_constraints, *request.taste_preferences)
            if value.upper() in preference_values
        )
        semantic_parts = [parsed.original]
        if desired_names:
            semantic_parts.append("available ingredients: " + ", ".join(desired_names))
        if request.scenario_tags:
            semantic_parts.append("scenario: " + ", ".join(request.scenario_tags))
        if request.taste_preferences:
            semantic_parts.append(
                "taste preferences: " + ", ".join(request.taste_preferences)
            )
        if request.max_total_minutes is not None:
            semantic_parts.append(
                f"maximum {request.max_total_minutes} minutes"
            )
        return ParsedQuery(
            original="\n".join(semantic_parts),
            ingredient_ids=frozenset(desired_ids),
            ingredient_names=tuple(desired_names),
            scenario_tags=frozenset(scenarios),
            preferences=frozenset(preferences),
            max_minutes=request.max_total_minutes or parsed.max_minutes,
            exclude_spicy=parsed.exclude_spicy,
            preferred_max_difficulty=(
                request.max_difficulty or parsed.preferred_max_difficulty
            ),
            dish_terms=parsed.dish_terms,
            excluded_ingredient_ids=parsed.excluded_ingredient_ids,
            excluded_allergens=parsed.excluded_allergens,
            unavailable_equipment=parsed.unavailable_equipment,
        )

    def _resolve_ingredients(self, names) -> tuple[list[UUID], list[str]]:
        ids = []
        canonical = []
        by_alias = {
            normalize_lookup_key(alias): entry
            for entry in self._catalog.entries
            for alias in entry.aliases
        }
        by_name = {
            normalize_lookup_key(entry.normalized_name): entry
            for entry in self._catalog.entries
        }
        for name in names:
            lookup_key = normalize_lookup_key(name)
            entry = by_name.get(lookup_key) or by_alias.get(lookup_key)
            if entry and entry.ingredient_id not in ids:
                ids.append(entry.ingredient_id)
                canonical.append(entry.normalized_name)
        return ids, canonical
