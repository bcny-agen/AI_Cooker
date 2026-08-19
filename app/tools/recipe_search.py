"""Managed LangGraph tool for the validated PostgreSQL Recipe Knowledge Base."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import Settings
from recipe_pipeline.evaluation.embedding_providers import (
    SentenceTransformerEmbeddingProvider,
)
from recipe_pipeline.recipe_kb.config import RecipeKBConfig
from recipe_pipeline.recipe_kb.repository import PostgresRecipeRepository
from recipe_pipeline.recipe_kb.service import (
    RecipeRetrievalRequest,
    RecipeRetrievalService,
    RecipeSearchResult,
)


logger = logging.getLogger(__name__)
DEFAULT_AGENT_CACHE_DIR = Path("recipe_pipeline/output/recipe_kb/agent_cache")
EXPLICIT_WEB_TERMS = (
    "latest",
    "current trend",
    "trending",
    "viral",
    "internet",
    "online source",
    "web source",
    "最新",
    "当下流行",
    "热门趋势",
    "网红",
    "爆款",
    "网上",
    "网页来源",
)


class RecipeSearchConfigurationError(RuntimeError):
    """Raised only when the Recipe KB tool schema cannot be constructed."""


class RecipeKBPool(Protocol):
    def connection(self): ...
    def close(self, timeout: float = 5.0) -> None: ...


class RecipeSearchInput(BaseModel):
    """Bounded schema shown to both Step and DeepSeek tool-calling models."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=1000,
        description="The user's recipe or cooking request in its original language.",
    )
    available_ingredients: list[str] = Field(
        default_factory=list,
        max_length=30,
        description=(
            "Ingredients the user has, including ingredients identified from an "
            "uploaded image. Use short ingredient names."
        ),
    )
    excluded_ingredients: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Ingredients that must not appear in any returned recipe.",
    )
    excluded_allergens: list[str] = Field(
        default_factory=list,
        max_length=15,
        description=(
            "Allergens to exclude, such as EGG, MILK, PEANUT, TREE_NUT, SOY, "
            "WHEAT, FISH, SHELLFISH, or SESAME."
        ),
    )
    dietary_constraints: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Hard dietary constraints, especially VEGETARIAN or VEGAN.",
    )
    taste_preferences: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Preferences such as LOW_OIL, NON_SPICY, or HIGH_PROTEIN. Include "
            "relevant stable preferences from trusted known-user-preference "
            "context, not only preferences stated in the latest message."
        ),
    )
    equipment: list[str] = Field(
        default_factory=list,
        max_length=15,
        description="Available equipment only when the user clearly specifies it.",
    )
    unavailable_equipment: list[str] = Field(
        default_factory=list,
        max_length=15,
        description="Equipment the recipe must not require.",
    )
    scenario_tags: list[str] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Scenario tags such as QUICK_MEAL, BEGINNER_FRIENDLY, FAMILY_MEAL, "
            "STUDENT_COOKING, AIR_FRYER, ONE_POT, or HEALTHY_MEAL."
        ),
    )
    max_total_minutes: int | None = Field(default=None, ge=1, le=1440)
    max_difficulty: int | None = Field(default=None, ge=1, le=5)
    servings: int | None = Field(default=None, ge=1, le=50)
    limit: int = Field(default=5, ge=1, le=5)
    include_steps: bool = Field(
        default=False,
        description=(
            "Set true only for detailed cooking instructions or a named recipe; "
            "leave false for recommendation lists to keep context compact."
        ),
    )


@dataclass(frozen=True, slots=True)
class RecipeCoveragePolicy:
    version: str
    min_semantic_score: float
    min_ingredient_ratio: float
    max_missing_required: int

    def evaluate(
        self,
        *,
        query: str,
        requested_ingredient_count: int,
        results: list[RecipeSearchResult],
    ) -> tuple[bool, str]:
        normalized_query = query.casefold()
        if any(term in normalized_query for term in EXPLICIT_WEB_TERMS):
            return False, "current_or_web_intent"
        if not results:
            return False, "no_constraint_satisfying_recipes"

        non_ingredient_evidence = any(
            self._has_non_ingredient_evidence(query, result)
            for result in results
        )
        if requested_ingredient_count == 0 and not non_ingredient_evidence:
            return False, "query_intent_not_covered"

        for result in results:
            ingredient_ratio = (
                len(result.matched_ingredients) / requested_ingredient_count
                if requested_ingredient_count
                else 1.0
            )
            if (
                result.semantic_score >= self.min_semantic_score
                and ingredient_ratio >= self.min_ingredient_ratio
                and len(result.missing_required_ingredients)
                <= self.max_missing_required
            ):
                return True, "qualified_recipe_match"
        return False, "weak_or_impractical_matches"

    @staticmethod
    def _has_non_ingredient_evidence(
        query: str,
        result: RecipeSearchResult,
    ) -> bool:
        compact_query = "".join(query.casefold().split())
        compact_name = "".join(result.name.casefold().split())
        if compact_name and compact_name in compact_query:
            return True
        return any(
            reason.startswith((
                "matched scenario:",
                "satisfies dietary constraints:",
                "non-spicy constraint satisfied",
                "within ",
            ))
            for reason in result.why_matched
        )


class RecipeKBRuntime:
    """Own one pool and one E5 model for the entire FastAPI lifespan."""

    def __init__(
        self,
        settings: Settings,
        *,
        retrieval_service: RecipeRetrievalService | None = None,
        pool: RecipeKBPool | None = None,
    ) -> None:
        self.settings = settings
        self._service = retrieval_service
        self._pool = pool
        self._available = retrieval_service is not None
        self._unavailable_reason = (
            None if retrieval_service is not None else "not_started"
        )
        self._policy = RecipeCoveragePolicy(
            version=settings.recipe_coverage_policy_version,
            min_semantic_score=settings.recipe_coverage_min_semantic_score,
            min_ingredient_ratio=settings.recipe_coverage_min_ingredient_ratio,
            max_missing_required=settings.recipe_coverage_max_missing_required,
        )

    @property
    def available(self) -> bool:
        return self._available

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    def start(self) -> "RecipeKBRuntime":
        """Open the pool and eagerly load E5 without making app startup fatal."""

        if self._service is not None:
            self._available = True
            self._unavailable_reason = None
            return self
        if not self.settings.recipe_db_password:
            self._mark_unavailable("configuration_missing")
            return self

        config = RecipeKBConfig(
            host=self.settings.recipe_db_host,
            port=self.settings.recipe_db_port,
            database=self.settings.recipe_db_name,
            user=self.settings.recipe_db_user,
            password=self.settings.recipe_db_password,
            connect_timeout_seconds=(
                self.settings.recipe_db_connect_timeout_seconds
            ),
            embedding_model=self.settings.recipe_embedding_model,
            embedding_dimension=self.settings.recipe_embedding_dimension,
            embedding_batch_size=self.settings.recipe_embedding_batch_size,
            embedding_device=self.settings.recipe_embedding_device,
        )
        try:
            config.validate()
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                kwargs=config.connection_kwargs,
                min_size=self.settings.recipe_db_pool_min_size,
                max_size=self.settings.recipe_db_pool_max_size,
                timeout=float(config.connect_timeout_seconds),
                check=ConnectionPool.check_connection,
                name="ai-cooker-recipe-kb",
                open=False,
            )
            pool.open(
                wait=True,
                timeout=float(config.connect_timeout_seconds),
            )
            self._pool = pool
            repository = PostgresRecipeRepository(
                config,
                connection_provider=pool.connection,
            )
            # This checks both explicit dataset status and frozen embedding metadata.
            repository.dataset_id(self.settings.recipe_dataset_version)
            provider = SentenceTransformerEmbeddingProvider(
                config.embedding_model,
                dimensions=config.embedding_dimension,
                batch_size=config.embedding_batch_size,
                device=config.embedding_device,
            )
            provider.load_model()
            self._service = RecipeRetrievalService(
                config,
                repository=repository,
                embedding_provider=provider,
                cache_dir=DEFAULT_AGENT_CACHE_DIR,
            )
        except Exception as exc:
            self._mark_unavailable(type(exc).__name__)
            self.close()
            return self

        self._available = True
        self._unavailable_reason = None
        logger.info(
            "recipe_kb_started dataset_version=%s embedding_model=%s "
            "embedding_dimension=%s pool_min=%s pool_max=%s",
            self.settings.recipe_dataset_version,
            self.settings.recipe_embedding_model,
            self.settings.recipe_embedding_dimension,
            self.settings.recipe_db_pool_min_size,
            self.settings.recipe_db_pool_max_size,
        )
        return self

    def close(self) -> None:
        pool, self._pool = self._pool, None
        if pool is not None:
            try:
                pool.close(timeout=5.0)
            except Exception as exc:
                logger.warning(
                    "recipe_kb_pool_close_failed error_type=%s",
                    type(exc).__name__,
                )

    def search(self, request: RecipeSearchInput) -> dict[str, Any]:
        started = perf_counter()
        query_fingerprint = hashlib.sha256(
            request.query.encode("utf-8")
        ).hexdigest()[:12]
        if not self._available or self._service is None:
            self._log_search(
                query_fingerprint=query_fingerprint,
                latency_ms=(perf_counter() - started) * 1000,
                candidate_count=0,
                coverage_sufficient=False,
                selected_ids=[],
                failure=self._unavailable_reason or "unavailable",
            )
            return {
                "available": False,
                "coverage_sufficient": False,
                "coverage_reason": "recipe_kb_unavailable",
                "recipes": [],
            }

        if self._has_unsupported_hard_constraints(request):
            self._log_search(
                query_fingerprint=query_fingerprint,
                latency_ms=(perf_counter() - started) * 1000,
                candidate_count=0,
                coverage_sufficient=False,
                selected_ids=[],
                failure="unsupported_hard_constraints",
            )
            return {
                "available": True,
                "coverage_sufficient": False,
                "coverage_reason": "unsupported_hard_constraints",
                "recipes": [],
            }

        retrieval_request = RecipeRetrievalRequest(
            query=request.query,
            available_ingredients=tuple(request.available_ingredients),
            excluded_ingredients=tuple(request.excluded_ingredients),
            excluded_allergens=tuple(request.excluded_allergens),
            dietary_constraints=tuple(request.dietary_constraints),
            taste_preferences=tuple(request.taste_preferences),
            equipment=tuple(request.equipment),
            unavailable_equipment=tuple(request.unavailable_equipment),
            scenario_tags=tuple(request.scenario_tags),
            max_total_minutes=request.max_total_minutes,
            max_difficulty=request.max_difficulty,
            servings=request.servings,
            limit=request.limit,
            dataset_version=self.settings.recipe_dataset_version,
        )
        try:
            results = self._service.search_recipes(retrieval_request)
        except Exception as exc:
            self._log_search(
                query_fingerprint=query_fingerprint,
                latency_ms=(perf_counter() - started) * 1000,
                candidate_count=0,
                coverage_sufficient=False,
                selected_ids=[],
                failure=type(exc).__name__,
            )
            return {
                "available": False,
                "coverage_sufficient": False,
                "coverage_reason": "recipe_kb_query_failed",
                "recipes": [],
            }

        requested_ingredients = self._requested_ingredient_count(
            request,
            results,
        )
        sufficient, reason = self._policy.evaluate(
            query=request.query,
            requested_ingredient_count=requested_ingredients,
            results=results,
        )
        recipes = [
            self._tool_recipe(result, include_steps=request.include_steps)
            for result in results
        ]
        selected_ids = [str(result.recipe_id) for result in results]
        self._log_search(
            query_fingerprint=query_fingerprint,
            latency_ms=(perf_counter() - started) * 1000,
            candidate_count=len(results),
            coverage_sufficient=sufficient,
            selected_ids=selected_ids,
            failure=None,
        )
        return {
            "available": True,
            "coverage_sufficient": sufficient,
            "coverage_reason": reason,
            "coverage_policy_version": self._policy.version,
            "recipes": recipes,
        }

    def _mark_unavailable(self, reason: str) -> None:
        self._available = False
        self._unavailable_reason = reason
        logger.warning("recipe_kb_unavailable reason=%s", reason)

    @staticmethod
    def _requested_ingredient_count(
        request: RecipeSearchInput,
        results: list[RecipeSearchResult],
    ) -> int:
        if request.available_ingredients:
            from recipe_pipeline.normalization.ingredients import (
                IngredientCatalog,
                UnknownIngredientError,
                normalize_lookup_key,
            )

            catalog = IngredientCatalog()
            identities: set[str] = set()
            for value in request.available_ingredients:
                try:
                    identities.add(str(catalog.resolve(value).ingredient_id))
                except UnknownIngredientError:
                    identities.add("unknown:" + normalize_lookup_key(value))
            return len(identities)
        from recipe_pipeline.evaluation.baseline import RecipeQueryParser

        return len(RecipeQueryParser().parse(request.query).ingredient_ids)

    @staticmethod
    def _has_unsupported_hard_constraints(request: RecipeSearchInput) -> bool:
        from recipe_pipeline.normalization.ingredients import (
            IngredientCatalog,
            UnknownIngredientError,
        )
        from recipe_pipeline.schemas.recipe import (
            AllergenTag,
            DietaryTag,
            EquipmentName,
        )

        catalog = IngredientCatalog()
        for value in request.excluded_ingredients:
            try:
                catalog.resolve(value)
            except UnknownIngredientError:
                return True
        allowed_allergens = {item.value for item in AllergenTag}
        allowed_diets = {item.value for item in DietaryTag}
        allowed_equipment = {item.value for item in EquipmentName}
        return bool(
            {value.upper() for value in request.excluded_allergens}
            - allowed_allergens
            or {value.upper() for value in request.dietary_constraints}
            - allowed_diets
            or {
                value.upper()
                for value in (*request.equipment, *request.unavailable_equipment)
            }
            - allowed_equipment
        )

    @staticmethod
    def _tool_recipe(
        result: RecipeSearchResult,
        *,
        include_steps: bool,
    ) -> dict[str, Any]:
        steps = []
        if include_steps:
            steps = [
                {
                    "order": item["order"],
                    "instruction": item["instruction"],
                    "duration_minutes": item["duration_minutes"],
                    **(
                        {"safety_note": item["safety_note"]}
                        if item.get("safety_note")
                        else {}
                    ),
                }
                for item in result.steps[:12]
            ]
        return {
            "recipe_id": str(result.recipe_id),
            "name": result.name,
            "summary": result.summary,
            "matched_ingredients": result.matched_ingredients,
            "missing_required_ingredients": (
                result.missing_required_ingredients
            ),
            "suggested_substitutions": result.suggested_substitutions[:5],
            "total_minutes": result.total_minutes,
            "difficulty": result.difficulty,
            "taste_tags": result.taste_tags,
            "scenario_tags": result.scenario_tags,
            "quality_score": result.quality_score,
            "why_matched": result.why_matched,
            "steps": steps,
        }

    @staticmethod
    def _log_search(
        *,
        query_fingerprint: str,
        latency_ms: float,
        candidate_count: int,
        coverage_sufficient: bool,
        selected_ids: list[str],
        failure: str | None,
    ) -> None:
        logger.info(
            "recipe_kb_query query_fingerprint=%s latency_ms=%.3f "
            "candidates=%s coverage_sufficient=%s selected_recipe_ids=%s "
            "failure=%s",
            query_fingerprint,
            latency_ms,
            candidate_count,
            coverage_sufficient,
            ",".join(selected_ids),
            failure or "none",
        )


def create_recipe_search_tool(runtime: RecipeKBRuntime) -> StructuredTool:
    """Expose Recipe KB as a compact model-driven tool."""

    def recipe_search(**kwargs: Any) -> str:
        request = RecipeSearchInput.model_validate(kwargs)
        return json.dumps(
            runtime.search(request),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    try:
        return StructuredTool.from_function(
            func=recipe_search,
            name="recipe_search",
            description=(
                "Search AI_Cooker's explicitly pinned, curated internal Recipe "
                "Knowledge Base. Use this first for ordinary recipe recommendations, "
                "ingredient-based cooking ideas, substitutions, and canonical cooking "
                "instructions. Pass ingredients identified from images in "
                "available_ingredients and always pass known allergies, exclusions, "
                "dietary constraints, and equipment constraints. Read "
                "coverage_sufficient: when true, answer from these recipes without "
                "automatically calling web_search; when false or available is false, "
                "web_search may supplement. The recipes are curated AI-synthetic "
                "REVIEW records, not an authoritative food source."
            ),
            args_schema=RecipeSearchInput,
        )
    except Exception as exc:
        raise RecipeSearchConfigurationError(
            "Unable to configure the Recipe KB search tool."
        ) from exc
