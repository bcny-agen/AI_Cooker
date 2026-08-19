from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import httpx

from recipe_pipeline.evaluation.baseline import BaselineRecipeRetriever
from recipe_pipeline.evaluation.embedding import (
    EmbeddingContext,
    EmbeddingKind,
    QueryEmbeddingTextBuilder,
    RecipeEmbeddingTextBuilder,
)
from recipe_pipeline.evaluation.embedding_benchmark import (
    EVALUATION_MATRIX,
    validate_holdout_isolation,
)
from recipe_pipeline.evaluation.embedding_cache import (
    CachedEmbeddingProvider,
    EmbeddingGenerationError,
    source_text_hash,
)
from recipe_pipeline.evaluation.embedding_providers import (
    EmbeddingResponseError,
    FakeEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    validate_vector_dimensions,
)
from recipe_pipeline.evaluation.hybrid import VectorCandidateRetriever
from recipe_pipeline.generation import (
    CodexAuthoredGenerationJobRunner,
    RetryingGenerationCoordinator,
    create_first_100_plan,
)
from recipe_pipeline.pipeline import RecipeDatasetPipeline
from recipe_pipeline.sources import ManualRecipeSource


class EmbeddingBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        generated = RetryingGenerationCoordinator(
            CodexAuthoredGenerationJobRunner(run_id="embedding-unit")
        ).run(create_first_100_plan())
        cls.recipes = RecipeDatasetPipeline().run(
            ManualRecipeSource(generated.raw_recipes)
        ).recipes

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="recipe-embedding-test-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_provider_batches_and_cache_hits_without_regeneration(self) -> None:
        texts = ["one", "two", "three"]
        contexts = [EmbeddingContext("INGREDIENT", "v1") for _ in texts]
        fake = FakeEmbeddingProvider(
            {text: (float(index + 1), 1.0) for index, text in enumerate(texts)},
            dimensions=2,
        )
        cached = CachedEmbeddingProvider(fake, self.temp_dir, batch_size=2)
        first = cached.embed_documents(texts, contexts)
        second = cached.embed_documents(texts, contexts)
        self.assertEqual(first, second)
        self.assertEqual([len(call) for call in fake.document_calls], [2, 1])
        self.assertEqual(cached.stats.hits, 3)
        self.assertEqual(cached.stats.misses, 3)

    def test_cache_invalidates_on_model_template_and_source_text(self) -> None:
        context_v1 = EmbeddingContext("FULL_RECIPE", "v1")
        context_v2 = EmbeddingContext("FULL_RECIPE", "v2")
        fake = FakeEmbeddingProvider({"text": (1.0, 0.0), "changed": (0.0, 1.0)}, dimensions=2)
        cache = CachedEmbeddingProvider(fake, self.temp_dir, batch_size=4)
        cache.embed_documents(["text"], [context_v1])
        cache.embed_documents(["text"], [context_v2])
        cache.embed_documents(["changed"], [context_v2])
        other_model = CachedEmbeddingProvider(
            FakeEmbeddingProvider({"text": (1.0, 0.0)}, model="fake-v2", dimensions=2),
            self.temp_dir,
        )
        other_model.embed_documents(["text"], [context_v1])
        self.assertEqual(cache.stats.misses, 3)
        self.assertEqual(other_model.stats.misses, 1)

    def test_source_text_hash_is_utf8_deterministic(self) -> None:
        self.assertEqual(source_text_hash("番茄 egg"), source_text_hash("番茄 egg"))
        self.assertNotEqual(source_text_hash("番茄 egg"), source_text_hash("番茄 eggs"))
        self.assertEqual(len(source_text_hash("番茄 egg")), 64)

    def test_dimension_validation_rejects_mismatch(self) -> None:
        self.assertEqual(validate_vector_dimensions([(1.0, 0.0)], 2), 2)
        with self.assertRaises(EmbeddingResponseError):
            validate_vector_dimensions([(1.0, 0.0), (1.0, 0.0, 0.0)])
        with self.assertRaises(EmbeddingResponseError):
            validate_vector_dimensions([(1.0, 0.0)], 3)

    def test_partial_failure_writes_successes_and_resumes(self) -> None:
        contexts = [EmbeddingContext("SCENARIO", "v1")] * 3
        failing = FakeEmbeddingProvider(
            {"ok-1": (1.0, 0.0), "bad": (0.5, 0.5), "ok-2": (0.0, 1.0)},
            dimensions=2,
            fail_texts={"bad"},
        )
        cache = CachedEmbeddingProvider(failing, self.temp_dir, batch_size=3)
        with self.assertRaises(EmbeddingGenerationError):
            cache.embed_documents(["ok-1", "bad", "ok-2"], contexts)
        recovered = CachedEmbeddingProvider(
            FakeEmbeddingProvider({"bad": (0.5, 0.5)}, dimensions=2),
            self.temp_dir,
            batch_size=3,
        )
        recovered.embed_documents(["ok-1", "bad", "ok-2"], contexts)
        self.assertEqual(recovered.stats.hits, 2)
        self.assertEqual(recovered.stats.misses, 1)

    def test_query_representation_uses_raw_and_parsed_structure(self) -> None:
        parsed = BaselineRecipeRetriever(self.recipes).parser.parse(
            "我想要适合新手的少油鸡肉晚餐，20分钟以内"
        )
        texts = QueryEmbeddingTextBuilder().build(parsed)
        self.assertEqual(set(texts), set(EmbeddingKind))
        self.assertIn("鸡肉", texts[EmbeddingKind.INGREDIENT])
        self.assertIn("少油", texts[EmbeddingKind.SCENARIO])
        self.assertIn("20", texts[EmbeddingKind.FULL_RECIPE])

    def test_real_vector_retriever_integration_uses_three_views(self) -> None:
        recipes = self.recipes[:2]
        documents = [
            document
            for recipe in recipes
            for document in RecipeEmbeddingTextBuilder().build(recipe)
        ]
        parsed = BaselineRecipeRetriever(recipes).parser.parse("semantic query")
        query_texts = QueryEmbeddingTextBuilder().build(parsed)
        vectors = {document.text: (1.0, 0.0) for document in documents[:3]}
        vectors.update({document.text: (0.0, 1.0) for document in documents[3:]})
        vectors.update({text: (0.0, 1.0) for text in query_texts.values()})
        retriever = VectorCandidateRetriever(
            recipes,
            provider=FakeEmbeddingProvider(vectors, dimensions=2),
        )
        hits = retriever.retrieve_candidates(parsed.original, parsed, 2)
        self.assertEqual(hits[0].recipe.recipe_id, recipes[1].recipe_id)

    def test_openai_compatible_adapter_sends_one_batch_and_sorts_indices(self) -> None:
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": [0.0, 2.0]},
                        {"index": 0, "embedding": [2.0, 0.0]},
                    ]
                },
            )

        provider = OpenAICompatibleEmbeddingProvider(
            model="verified-model",
            base_url="https://example.invalid/v1",
            api_key="secret-not-logged",
            dimensions=2,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        vectors = provider.embed_documents(["a", "b"])
        self.assertEqual(vectors, [(1.0, 0.0), (0.0, 1.0)])
        self.assertEqual(requests[0]["input"], ["a", "b"])

    def test_evaluation_matrix_and_holdout_isolation(self) -> None:
        self.assertEqual(
            EVALUATION_MATRIX,
            (
                "rule_only",
                "tfidf_vector_only",
                "tfidf_hybrid",
                "real_embedding_vector_only",
                "real_embedding_hybrid",
            ),
        )
        development = [{"query": "dev", "expected_recipe_ids": ["one"]}]
        holdout = [{"query": "hold", "expected_recipe_ids": ["two"]}]
        validate_holdout_isolation(development, holdout)
        with self.assertRaises(ValueError):
            validate_holdout_isolation(development, development)


if __name__ == "__main__":
    unittest.main()
