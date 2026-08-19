from __future__ import annotations

import os
import unittest
from pathlib import Path
from uuid import uuid4

from recipe_pipeline.evaluation.embedding import EmbeddingKind
from recipe_pipeline.evaluation.embedding_providers import FakeEmbeddingProvider
from recipe_pipeline.recipe_kb.config import RecipeKBConfig
from recipe_pipeline.recipe_kb.database import apply_migrations, connect, readiness
from recipe_pipeline.recipe_kb.importer import GoldenDatasetImporter, RecipeImportError
from recipe_pipeline.recipe_kb.repository import PostgresRecipeRepository, RepositoryFilters
from recipe_pipeline.recipe_kb.service import RecipeRetrievalRequest, RecipeRetrievalService


@unittest.skipUnless(
    os.getenv("RECIPE_KB_INTEGRATION") == "1",
    "set RECIPE_KB_INTEGRATION=1 for a real PostgreSQL + pgvector instance",
)
class RecipeKBIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = RecipeKBConfig.from_env()
        apply_migrations(cls.config)
        cls.importer = GoldenDatasetImporter(cls.config, allow_generation=False)
        cls.first = cls.importer.import_dataset()
        cls.second = cls.importer.import_dataset()
        cls.repository = PostgresRecipeRepository(cls.config)

    def test_vector_extension_and_migrations(self) -> None:
        state = readiness(self.config)
        self.assertTrue(state["ready"])
        self.assertTrue(state["pgvector_version"])

    def test_recipe_import_aliases_and_vector_metadata(self) -> None:
        report = self.repository.integrity_report("golden_500_v1")
        self.assertEqual(report["recipes"], 492)
        self.assertEqual(report["embeddings"], 1476)
        self.assertEqual(report["dimension_mismatches"], 0)
        self.assertEqual(self.repository.alias_resolution("西红柿")[1], "番茄")
        self.assertEqual(self.repository.alias_resolution("tomato")[1], "番茄")
        with connect(self.config) as connection:
            metadata = connection.execute(
                """
                SELECT embedding_model, embedding_dimension,
                       count(DISTINCT representation_type), count(*)
                FROM recipe_embeddings GROUP BY embedding_model, embedding_dimension
                """
            ).fetchone()
        self.assertEqual(metadata, ("intfloat/multilingual-e5-small", 384, 3, 1476))

    def test_second_import_is_idempotent_and_uses_cache(self) -> None:
        self.assertEqual(self.first.embedding_cache_hits, 1476)
        self.assertEqual(self.first.inserted + self.first.unchanged, 492)
        self.assertEqual(self.second.inserted, 0)
        self.assertEqual(self.second.updated, 0)
        self.assertEqual(self.second.unchanged, 492)
        self.assertEqual(self.second.new_embeddings, 0)

    def test_dataset_is_not_implicitly_active(self) -> None:
        report = self.repository.integrity_report("golden_500_v1")
        self.assertEqual(report["active_dataset_count"], 0)

    def test_exact_vector_search_and_hard_filtering(self) -> None:
        service = RecipeRetrievalService(self.config)
        ids = service.vector_candidates("tomato egg dish", limit=5)
        self.assertEqual(len(ids), 5)
        results = service.search_recipes(
            RecipeRetrievalRequest(query="我不吃辣的20分钟晚餐", limit=5)
        )
        self.assertTrue(results)
        self.assertTrue(all(item.total_minutes <= 20 for item in results))
        self.assertTrue(
            all(
                not any(tag.startswith("spicy:") for tag in item.taste_tags)
                for item in results
            )
        )
        self.assertNotIn("embedding", results[0].compact_dict())

    def test_partial_import_rolls_back(self) -> None:
        failed_version = f"rollback-{uuid4()}"
        with self.assertRaises(RecipeImportError):
            self.importer.import_dataset(version_key=failed_version, fail_after_recipes=2)
        with connect(self.config) as connection:
            count = connection.execute(
                "SELECT count(*) FROM dataset_versions WHERE version_key=%s",
                (failed_version,),
            ).fetchone()[0]
        self.assertEqual(count, 0)
        with connect(self.config) as connection:
            failed = connection.execute(
                "SELECT count(*) FROM ingestion_runs WHERE version_key=%s AND status='FAILED'",
                (failed_version,),
            ).fetchone()[0]
        self.assertEqual(failed, 1)

    def test_database_rejects_dimension_mismatch(self) -> None:
        import psycopg

        with self.assertRaises(psycopg.errors.CheckViolation):
            with connect(self.config) as connection:
                connection.execute(
                    """
                    INSERT INTO recipe_embeddings(
                        dataset_version_id, recipe_id, representation_type,
                        embedding_model, embedding_dimension, template_version,
                        source_text_hash, embedding
                    ) SELECT dataset_version_id, recipe_id, 'INGREDIENT',
                        'dimension-test', 384, 'dimension-test-v1',
                        repeat('a', 64), '[1,2]'::vector
                    FROM recipes LIMIT 1
                    """
                )


if __name__ == "__main__":
    unittest.main()
