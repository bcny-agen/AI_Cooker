from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from recipe_pipeline.evaluation.baseline import (
    BaselineRecipeRetriever,
    Preference,
    RecipeQueryParser,
)
from recipe_pipeline.evaluation.embedding import (
    EmbeddingKind,
    RecipeEmbeddingTextBuilder,
)
from recipe_pipeline.evaluation.metrics import recall_at_k, reciprocal_rank
from recipe_pipeline.evaluation.embedding_providers import FakeEmbeddingProvider
from recipe_pipeline.evaluation.hybrid import (
    HybridRecipeRetriever,
    HybridReranker,
    RuleCandidateRetriever,
    VectorCandidateRetriever,
    reciprocal_rank_fusion,
)
from recipe_pipeline.evaluation.models import EvaluationQuery, QueryKind
from recipe_pipeline.evaluation.query_set import get_evaluation_queries
from recipe_pipeline.evaluation.runner import RecipeRetrievalEvaluationRunner
from recipe_pipeline.generation import (
    CodexAuthoredGenerationJobRunner,
    RetryingGenerationCoordinator,
    create_first_100_plan,
)
from recipe_pipeline.pipeline import RecipeDatasetPipeline
from recipe_pipeline.sources import ManualRecipeSource


class RetrievalEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        generation = RetryingGenerationCoordinator(
            CodexAuthoredGenerationJobRunner(run_id="evaluation-unit")
        ).run(create_first_100_plan())
        cls.recipes = RecipeDatasetPipeline().run(
            ManualRecipeSource(generation.raw_recipes)
        ).recipes
        cls.retriever = BaselineRecipeRetriever(cls.recipes)

    def test_query_set_contains_sixty_unique_user_queries(self) -> None:
        queries = get_evaluation_queries()
        self.assertEqual(len(queries), 60)
        self.assertEqual(len({query.query_id for query in queries}), 60)

    def test_ingredient_normalization_and_synonym_matching(self) -> None:
        parser = RecipeQueryParser()
        chinese = parser.parse("西红柿炒蛋")
        english = parser.parse("tomato egg dish")
        self.assertEqual(set(chinese.ingredient_names), {"番茄", "鸡蛋"})
        self.assertEqual(set(english.ingredient_names), {"番茄", "鸡蛋"})
        self.assertEqual(chinese.ingredient_ids, english.ingredient_ids)

    def test_normalized_ingredient_query_ranks_matching_recipe_first(self) -> None:
        results = self.retriever.retrieve("aubergine tofu", top_k=5)
        self.assertEqual(results[0].recipe.identity.name, "茄子番茄烧豆腐")
        self.assertEqual(results[0].ingredient_coverage, 1.0)

    def test_english_ingredient_query_retrieval_ranking(self) -> None:
        results = self.retriever.retrieve("chicken and potato recipes", top_k=5)
        names = [result.recipe.identity.name for result in results]
        self.assertIn("豆角土豆炖鸡肉", names[:3])

    def test_embedding_text_builder_creates_three_modular_views(self) -> None:
        documents = RecipeEmbeddingTextBuilder().build(self.recipes[0])
        self.assertEqual({document.kind for document in documents}, set(EmbeddingKind))
        ingredient_document = next(
            document for document in documents if document.kind == EmbeddingKind.INGREDIENT
        )
        self.assertIn("食材:", ingredient_document.text)
        self.assertIn(self.recipes[0].ingredients[0].normalized_name, ingredient_document.text)

    def test_metric_calculation(self) -> None:
        expected = [uuid4(), uuid4()]
        retrieved = [uuid4(), expected[0], uuid4(), expected[1]]
        self.assertEqual(recall_at_k(retrieved, expected), 1.0)
        self.assertEqual(reciprocal_rank(retrieved, expected), 0.5)
        self.assertEqual(recall_at_k([], expected), 0.0)

    def test_query_parser_extracts_ingredients_and_constraints(self) -> None:
        parsed = RecipeQueryParser().parse(
            "我有西红柿和鸡蛋，10分钟，少油，不辣，适合新手"
        )
        self.assertEqual(set(parsed.ingredient_names), {"番茄", "鸡蛋"})
        self.assertEqual(parsed.max_minutes, 10)
        self.assertIn(Preference.LOW_OIL, parsed.preferences)
        self.assertIn(Preference.NON_SPICY, parsed.preferences)
        self.assertTrue(parsed.exclude_spicy)
        self.assertEqual(parsed.preferred_max_difficulty, 2)

    def test_rule_candidate_retriever_uses_common_interface(self) -> None:
        parsed = self.retriever.parser.parse("chicken and potato recipes")
        candidates = RuleCandidateRetriever(
            self.recipes, self.retriever
        ).retrieve_candidates(parsed.original, parsed, top_k=5)
        self.assertEqual(len(candidates), 5)
        self.assertTrue(all(candidate.source == "RULE" for candidate in candidates))
        self.assertIn(
            "豆角土豆炖鸡肉",
            [candidate.recipe.identity.name for candidate in candidates[:3]],
        )

    def test_vector_candidate_retriever_accepts_fake_provider(self) -> None:
        recipes = self.recipes[:2]
        builder = RecipeEmbeddingTextBuilder()
        texts = [
            "\n".join(document.text for document in builder.build(recipe))
            for recipe in recipes
        ]
        parsed = self.retriever.parser.parse("semantic test query")
        provider = FakeEmbeddingProvider(
            {
                texts[0]: {0: 1.0},
                texts[1]: {1: 1.0},
                parsed.expanded_text(): {1: 1.0},
            }
        )
        candidates = VectorCandidateRetriever(
            recipes, provider=provider
        ).retrieve_candidates(parsed.original, parsed, top_k=2)
        self.assertEqual(candidates[0].recipe.recipe_id, recipes[1].recipe_id)
        self.assertEqual(candidates[0].source, "VECTOR")

    def test_rrf_fusion_rewards_recipe_present_in_both_rankings(self) -> None:
        first, shared, last = uuid4(), uuid4(), uuid4()
        scores = reciprocal_rank_fusion(
            [[first, shared], [shared, last]], rank_constant=60
        )
        self.assertGreater(scores[shared], scores[first])
        self.assertGreater(scores[shared], scores[last])

    def test_reranker_applies_large_non_spicy_penalty(self) -> None:
        base = self.recipes[0]
        mild = base.model_copy(
            update={"taste_profile": base.taste_profile.model_copy(update={"spicy": 0})}
        )
        spicy = base.model_copy(
            update={
                "recipe_id": uuid4(),
                "taste_profile": base.taste_profile.model_copy(update={"spicy": 5}),
            }
        )
        baseline = BaselineRecipeRetriever([mild, spicy])
        parsed = baseline.parser.parse("不辣")
        reranker = HybridReranker(baseline)
        mild_score = reranker.score(mild, parsed, 0.03)[0]
        spicy_score = reranker.score(spicy, parsed, 0.03)[0]
        self.assertGreaterEqual(mild_score - spicy_score, 10.0)

    def test_hybrid_retrieval_ranks_combined_ingredient_recipe(self) -> None:
        result = HybridRecipeRetriever(self.recipes).retrieve(
            "chicken and potato recipes", top_k=5
        )
        self.assertIn(
            "豆角土豆炖鸡肉",
            [candidate.recipe.identity.name for candidate in result.top_k],
        )
        self.assertEqual(len(result.rule_candidates), 30)
        self.assertEqual(len(result.vector_candidates), 30)

    def test_evaluation_report_generation(self) -> None:
        output_dir = Path(__file__).parent / "_evaluation_output"
        self.addCleanup(shutil.rmtree, output_dir, True)
        output_dir.mkdir(parents=True, exist_ok=True)
        dataset_path = output_dir / "recipes.jsonl"
        dataset_path.write_text(
            "".join(recipe.model_dump_json() + "\n" for recipe in self.recipes),
            encoding="utf-8",
        )
        query = EvaluationQuery(
            query_id="report-test",
            query="西红柿鸡蛋",
            kind=QueryKind.SYNONYM,
            expected_recipe_names=["番茄洋葱炒鸡蛋"],
        )
        run = RecipeRetrievalEvaluationRunner().run(
            dataset_path,
            output_dir / "reports",
            queries=[query],
        )
        self.assertEqual(run.metrics.query_count, 1)
        self.assertEqual(run.metrics.baseline.hit_rate_at_5, 1.0)
        self.assertEqual(run.metrics.hybrid.hit_rate_at_5, 1.0)
        for artifact in (
            run.artifacts.queries,
            run.artifacts.retrieval_results,
            run.artifacts.metrics,
        ):
            self.assertTrue(artifact.is_file())
            json.loads(artifact.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
