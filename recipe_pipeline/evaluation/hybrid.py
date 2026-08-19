"""Offline hybrid candidate generation, RRF fusion, and structured reranking."""

from __future__ import annotations

from dataclasses import astuple, dataclass
from typing import Protocol
from uuid import UUID

from recipe_pipeline.evaluation.baseline import (
    BaselineRecipeRetriever,
    ParsedQuery,
)
from recipe_pipeline.evaluation.embedding import (
    EmbeddingContext,
    EmbeddingKind,
    QueryEmbeddingTextBuilder,
    RecipeEmbeddingTextBuilder,
)
from recipe_pipeline.evaluation.embedding_providers import (
    EmbeddingProvider,
    TfidfEmbeddingProvider,
    sparse_dot,
)
from recipe_pipeline.schemas.recipe import IngredientImportance, RecipeV1


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    recipe: RecipeV1
    rank: int
    score: float
    source: str


class CandidateRetriever(Protocol):
    def retrieve_candidates(
        self,
        query: str,
        filters: ParsedQuery,
        top_k: int,
    ) -> list[RetrievalCandidate]: ...


class RuleCandidateRetriever:
    def __init__(
        self,
        recipes: list[RecipeV1],
        baseline: BaselineRecipeRetriever,
    ):
        self._recipes = recipes
        self._baseline = baseline

    def retrieve_candidates(
        self,
        query: str,
        filters: ParsedQuery,
        top_k: int,
    ) -> list[RetrievalCandidate]:
        scored = [
            self._baseline.score_recipe(recipe, filters)
            for recipe in self._recipes
            if self._baseline.satisfies_hard_constraints(recipe, filters)
        ]
        scored.sort(key=lambda candidate: candidate.score, reverse=True)
        return [
            RetrievalCandidate(
                recipe=candidate.recipe,
                rank=rank,
                score=candidate.score,
                source="RULE",
            )
            for rank, candidate in enumerate(scored[:top_k], start=1)
        ]


class VectorCandidateRetriever:
    def __init__(
        self,
        recipes: list[RecipeV1],
        provider: EmbeddingProvider | None = None,
        text_builder: RecipeEmbeddingTextBuilder | None = None,
    ):
        self._recipes = recipes
        self._baseline = BaselineRecipeRetriever(recipes)
        builder = text_builder or RecipeEmbeddingTextBuilder()
        self._documents = [
            document for recipe in recipes for document in builder.build(recipe)
        ]
        self._provider = provider or TfidfEmbeddingProvider()
        self._vectors = self._provider.embed_documents(
            [document.text for document in self._documents],
            [
                EmbeddingContext(document.kind.value, document.template_version)
                for document in self._documents
            ],
        )
        self._query_builder = QueryEmbeddingTextBuilder()

    def retrieve_candidates(
        self,
        query: str,
        filters: ParsedQuery,
        top_k: int,
    ) -> list[RetrievalCandidate]:
        query_texts = self._query_builder.build(filters)
        query_contexts = self._query_builder.contexts()
        query_vectors = self._provider.embed_queries(
            [query_texts[kind] for kind in EmbeddingKind],
            [query_contexts[kind] for kind in EmbeddingKind],
        )
        vectors_by_kind = dict(zip(EmbeddingKind, query_vectors))
        aggregate = {recipe.recipe_id: 0.0 for recipe in self._recipes}
        weights = {
            EmbeddingKind.INGREDIENT: 0.45,
            EmbeddingKind.SCENARIO: 0.25,
            EmbeddingKind.FULL_RECIPE: 0.30,
        }
        for document, vector in zip(self._documents, self._vectors):
            aggregate[document.recipe_id] += (
                sparse_dot(vector, vectors_by_kind[document.kind])
                * weights[document.kind]
            )
        scored = [
            (recipe, aggregate[recipe.recipe_id])
            for recipe in self._recipes
            if self._baseline.satisfies_hard_constraints(recipe, filters)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [
            RetrievalCandidate(recipe=recipe, rank=rank, score=round(score, 6), source="VECTOR")
            for rank, (recipe, score) in enumerate(scored[:top_k], start=1)
        ]


def reciprocal_rank_fusion(
    rankings: list[list[UUID]],
    *,
    rank_constant: int = 60,
    weights: list[float] | None = None,
) -> dict[UUID, float]:
    if rank_constant <= 0:
        raise ValueError("rank_constant must be positive")
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("weights must contain one value per ranking")
    fused: dict[UUID, float] = {}
    for ranking_index, ranking in enumerate(rankings):
        weight = weights[ranking_index] if weights is not None else 1.0
        if weight < 0:
            raise ValueError("RRF weights cannot be negative")
        for rank, recipe_id in enumerate(ranking, start=1):
            fused[recipe_id] = fused.get(recipe_id, 0.0) + weight / (
                rank_constant + rank
            )
    return fused


@dataclass(frozen=True, slots=True)
class RerankBreakdown:
    rrf: float
    ingredient: float
    missing_ingredient_penalty: float
    extra_core_penalty: float
    preference: float
    spicy_penalty: float
    scenario: float
    time: float
    difficulty: float
    dish_keyword: float
    quality: float


@dataclass(frozen=True, slots=True)
class HybridCandidate:
    recipe: RecipeV1
    rank: int
    final_score: float
    ingredient_coverage: float
    preference_match: float | None
    breakdown: RerankBreakdown


class HybridReranker:
    """Structured scoring applied after RRF candidate fusion."""

    def __init__(self, baseline: BaselineRecipeRetriever):
        self._baseline = baseline

    def score(
        self,
        recipe: RecipeV1,
        parsed: ParsedQuery,
        fused_score: float,
    ) -> tuple[float, float, float | None, RerankBreakdown]:
        baseline_metadata = self._baseline.score_recipe(recipe, parsed)
        recipe_ingredients = {item.ingredient_id for item in recipe.ingredients}
        ingredient_coverage = baseline_metadata.ingredient_coverage
        missing_count = len(parsed.ingredient_ids - recipe_ingredients)
        extra_core = {
            item.ingredient_id
            for item in recipe.ingredients
            if item.importance == IngredientImportance.CORE
        } - parsed.ingredient_ids

        rrf_component = fused_score * 60.0
        ingredient_component = ingredient_coverage * 6.0
        if parsed.ingredient_ids and ingredient_coverage == 1.0:
            ingredient_component += 2.0
        missing_penalty = -4.0 * missing_count
        extra_penalty = (
            -0.15 * max(0, len(extra_core) - 1)
            if parsed.ingredient_ids
            else 0.0
        )
        preference_component = (
            (baseline_metadata.preference_match or 0.0) * 2.0
            if parsed.preferences
            else 0.0
        )
        spicy_penalty = (
            -10.0
            if parsed.exclude_spicy and recipe.taste_profile.spicy > 0
            else 0.0
        )
        scenario_component = 2.0 * len(
            set(recipe.tags.scenario) & parsed.scenario_tags
        )
        time_component = 0.0
        if parsed.max_minutes is not None:
            if recipe.time.total_minutes <= parsed.max_minutes:
                time_component = 2.0 + max(
                    0.0,
                    (parsed.max_minutes - recipe.time.total_minutes) / 30,
                )
            else:
                time_component = -min(
                    8.0,
                    ((recipe.time.total_minutes - parsed.max_minutes) / 5) * 2,
                )
        difficulty_component = 0.0
        if parsed.preferred_max_difficulty is not None:
            if recipe.difficulty.level <= parsed.preferred_max_difficulty:
                difficulty_component = 2.0
            else:
                difficulty_component = -4.0 * (
                    recipe.difficulty.level - parsed.preferred_max_difficulty
                )
        dish_component = 1.5 * sum(
            term in recipe.identity.name for term in parsed.dish_terms
        )
        quality_component = recipe.quality.confidence_score * 0.5
        breakdown = RerankBreakdown(
            rrf=rrf_component,
            ingredient=ingredient_component,
            missing_ingredient_penalty=missing_penalty,
            extra_core_penalty=extra_penalty,
            preference=preference_component,
            spicy_penalty=spicy_penalty,
            scenario=scenario_component,
            time=time_component,
            difficulty=difficulty_component,
            dish_keyword=dish_component,
            quality=quality_component,
        )
        total = sum(astuple(breakdown))
        return (
            round(total, 6),
            ingredient_coverage,
            baseline_metadata.preference_match,
            breakdown,
        )


@dataclass(frozen=True, slots=True)
class HybridRetrievalResult:
    parsed_query: ParsedQuery
    rule_candidates: list[RetrievalCandidate]
    vector_candidates: list[RetrievalCandidate]
    top_k: list[HybridCandidate]


class HybridRecipeRetriever:
    def __init__(
        self,
        recipes: list[RecipeV1],
        *,
        embedding_provider: EmbeddingProvider | None = None,
        candidate_k: int = 30,
        rrf_constant: int = 60,
        rule_weight: float = 10.0,
        vector_weight: float = 1.0,
    ):
        self._recipes_by_id = {recipe.recipe_id: recipe for recipe in recipes}
        self._baseline = BaselineRecipeRetriever(recipes)
        self._rule = RuleCandidateRetriever(recipes, self._baseline)
        self._vector = VectorCandidateRetriever(recipes, embedding_provider)
        self._reranker = HybridReranker(self._baseline)
        self._candidate_k = candidate_k
        self._rrf_constant = rrf_constant
        self._rule_weight = rule_weight
        self._vector_weight = vector_weight

    @property
    def parser(self):
        return self._baseline.parser

    def retrieve(self, query: str, top_k: int = 5) -> HybridRetrievalResult:
        parsed = self.parser.parse(query)
        rule_candidates = self._rule.retrieve_candidates(
            query, parsed, self._candidate_k
        )
        vector_candidates = self._vector.retrieve_candidates(
            query, parsed, self._candidate_k
        )
        fused = reciprocal_rank_fusion(
            [
                [candidate.recipe.recipe_id for candidate in rule_candidates],
                [candidate.recipe.recipe_id for candidate in vector_candidates],
            ],
            rank_constant=self._rrf_constant,
            weights=[self._rule_weight, self._vector_weight],
        )
        reranked = []
        for recipe_id, fused_score in fused.items():
            recipe = self._recipes_by_id[recipe_id]
            if not self._baseline.satisfies_hard_constraints(recipe, parsed):
                continue
            final_score, coverage, preference, breakdown = self._reranker.score(
                recipe, parsed, fused_score
            )
            reranked.append((recipe, final_score, coverage, preference, breakdown))
        reranked.sort(key=lambda item: item[1], reverse=True)
        hits = [
            HybridCandidate(
                recipe=recipe,
                rank=rank,
                final_score=score,
                ingredient_coverage=coverage,
                preference_match=preference,
                breakdown=breakdown,
            )
            for rank, (recipe, score, coverage, preference, breakdown) in enumerate(
                reranked[:top_k], start=1
            )
        ]
        return HybridRetrievalResult(parsed, rule_candidates, vector_candidates, hits)
