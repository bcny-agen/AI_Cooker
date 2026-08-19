"""Recipe KB tool tests without a model, network, or PostgreSQL dependency."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from app.config.settings import Settings
from app.tools.recipe_search import (
    RecipeKBRuntime,
    RecipeSearchInput,
    create_recipe_search_tool,
)
from recipe_pipeline.recipe_kb.service import RecipeSearchResult


def settings(**overrides) -> Settings:
    values = {
        "model_name": "step-3.7-flash",
        "model_api_key": "model-key",
        "model_base_url": "https://model.example/v1",
        "mysql_host": "localhost",
        "mysql_port": 3306,
        "mysql_user": "user",
        "mysql_password": "password",
        "mysql_database": "agent_web",
        "tavily_api_key": "tavily-key",
    }
    values.update(overrides)
    return Settings(**values)


def result(
    *,
    semantic_score: float = 0.91,
    matched: list[str] | None = None,
    missing: list[str] | None = None,
) -> RecipeSearchResult:
    return RecipeSearchResult(
        recipe_id=uuid4(),
        name="番茄炒蛋",
        matched_ingredients=matched or ["番茄", "鸡蛋"],
        missing_required_ingredients=missing or [],
        total_minutes=15,
        difficulty=1,
        taste_tags=["umami:2/5"],
        scenario_tags=["QUICK_MEAL", "BEGINNER_FRIENDLY"],
        quality_score=0.82,
        why_matched=["matched ingredients: 番茄, 鸡蛋"],
        summary="番茄和鸡蛋制作的家常菜。",
        steps=[{
            "order": 1,
            "instruction": "炒熟鸡蛋后加入番茄。",
            "duration_minutes": 10,
            "safety_note": "鸡蛋应彻底熟透。",
        }],
        suggested_substitutions=[],
        semantic_score=semantic_score,
        score=semantic_score + 0.02,
    )


class FakeRetrievalService:
    def __init__(self, results=None, error: Exception | None = None) -> None:
        self.results = list(results or [])
        self.error = error
        self.requests = []

    def search_recipes(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return list(self.results)


class RecipeSearchToolTests(unittest.TestCase):
    def test_kb_success_alias_contract_is_compact_and_coverage_is_true(self) -> None:
        retrieval = FakeRetrievalService([result()])
        runtime = RecipeKBRuntime(settings(), retrieval_service=retrieval)
        tool = create_recipe_search_tool(runtime)

        payload = json.loads(tool.invoke({
            "query": "西红柿鸡蛋怎么做",
            "available_ingredients": ["西红柿", "eggs"],
            "limit": 3,
        }))

        self.assertTrue(payload["available"])
        self.assertTrue(payload["coverage_sufficient"])
        self.assertEqual(payload["coverage_policy_version"], "recipe-coverage-v1")
        self.assertEqual(payload["recipes"][0]["matched_ingredients"], ["番茄", "鸡蛋"])
        self.assertEqual(payload["recipes"][0]["steps"], [])
        serialized = json.dumps(payload)
        self.assertNotIn("semantic_score", serialized.casefold())
        self.assertNotIn("embedding", serialized.casefold())
        self.assertNotIn("sql", serialized.casefold())
        self.assertNotIn("score", payload["recipes"][0])
        self.assertEqual(retrieval.requests[0].dataset_version, "golden_500_v1")

    def test_hard_constraints_are_forwarded_and_steps_are_opt_in(self) -> None:
        retrieval = FakeRetrievalService([result()])
        runtime = RecipeKBRuntime(settings(), retrieval_service=retrieval)

        payload = runtime.search(RecipeSearchInput(
            query="做一道不含花生的纯素菜",
            excluded_ingredients=["花生"],
            excluded_allergens=["PEANUT"],
            dietary_constraints=["VEGAN"],
            unavailable_equipment=["OVEN"],
            max_total_minutes=20,
            max_difficulty=1,
            servings=2,
            include_steps=True,
        ))

        request = retrieval.requests[0]
        self.assertEqual(request.excluded_ingredients, ("花生",))
        self.assertEqual(request.excluded_allergens, ("PEANUT",))
        self.assertEqual(request.dietary_constraints, ("VEGAN",))
        self.assertEqual(request.unavailable_equipment, ("OVEN",))
        self.assertEqual(request.max_total_minutes, 20)
        self.assertEqual(request.max_difficulty, 1)
        self.assertEqual(request.servings, 2)
        self.assertEqual(payload["recipes"][0]["steps"][0]["order"], 1)

    def test_coverage_is_false_for_weak_result_and_explicit_current_intent(self) -> None:
        weak = RecipeKBRuntime(
            settings(),
            retrieval_service=FakeRetrievalService([
                result(semantic_score=0.50, matched=["鸡蛋"], missing=["番茄", "洋葱", "青椒", "豆腐"]),
            ]),
        )
        weak_payload = weak.search(RecipeSearchInput(
            query="鸡蛋和番茄能做什么",
            available_ingredients=["鸡蛋", "番茄"],
        ))
        self.assertFalse(weak_payload["coverage_sufficient"])
        self.assertEqual(weak_payload["coverage_reason"], "weak_or_impractical_matches")

        current = RecipeKBRuntime(
            settings(),
            retrieval_service=FakeRetrievalService([result()]),
        )
        current_payload = current.search(RecipeSearchInput(
            query="最新 viral 番茄鸡蛋趋势",
            available_ingredients=["番茄", "鸡蛋"],
        ))
        self.assertFalse(current_payload["coverage_sufficient"])
        self.assertEqual(current_payload["coverage_reason"], "current_or_web_intent")

    def test_database_unavailable_is_distinct_from_insufficient_coverage(self) -> None:
        runtime = RecipeKBRuntime(settings())

        payload = runtime.search(RecipeSearchInput(query="番茄炒蛋"))

        self.assertFalse(payload["available"])
        self.assertFalse(payload["coverage_sufficient"])
        self.assertEqual(payload["coverage_reason"], "recipe_kb_unavailable")

    def test_high_semantic_score_alone_does_not_cover_unrelated_intent(self) -> None:
        runtime = RecipeKBRuntime(
            settings(),
            retrieval_service=FakeRetrievalService([result()]),
        )

        payload = runtime.search(RecipeSearchInput(
            query="I want an obscure regional moon-shaped pastry",
        ))

        self.assertFalse(payload["coverage_sufficient"])
        self.assertEqual(payload["coverage_reason"], "query_intent_not_covered")

    def test_query_failure_is_safe_and_does_not_escape_tool(self) -> None:
        runtime = RecipeKBRuntime(
            settings(),
            retrieval_service=FakeRetrievalService(error=RuntimeError("db down")),
        )

        payload = runtime.search(RecipeSearchInput(query="番茄炒蛋"))

        self.assertFalse(payload["available"])
        self.assertEqual(payload["coverage_reason"], "recipe_kb_query_failed")

    def test_unknown_hard_constraint_is_never_silently_ignored(self) -> None:
        retrieval = FakeRetrievalService([result()])
        runtime = RecipeKBRuntime(settings(), retrieval_service=retrieval)

        payload = runtime.search(RecipeSearchInput(
            query="Recommend dinner",
            dietary_constraints=["HALAL"],
        ))

        self.assertTrue(payload["available"])
        self.assertFalse(payload["coverage_sufficient"])
        self.assertEqual(
            payload["coverage_reason"],
            "unsupported_hard_constraints",
        )
        self.assertEqual(payload["recipes"], [])
        self.assertEqual(retrieval.requests, [])

    def test_close_owns_only_recipe_pool(self) -> None:
        pool = MagicMock()
        runtime = RecipeKBRuntime(
            settings(),
            retrieval_service=FakeRetrievalService(),
            pool=pool,
        )

        runtime.close()

        pool.close.assert_called_once_with(timeout=5.0)


if __name__ == "__main__":
    unittest.main()
