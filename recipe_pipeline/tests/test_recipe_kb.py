from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from recipe_pipeline.evaluation.embedding import EmbeddingKind, RecipeEmbeddingTextBuilder
from recipe_pipeline.evaluation.embedding_providers import EmbeddingResponseError, validate_vector_dimensions
from recipe_pipeline.normalization.ingredients import IngredientCatalog
from recipe_pipeline.recipe_kb.config import (
    RecipeKBConfig,
    RecipeKBConfigurationError,
)
from recipe_pipeline.recipe_kb.importer import GoldenDatasetImporter
from recipe_pipeline.recipe_kb.repository import REPRESENTATION_DB_NAMES
from recipe_pipeline.recipe_kb.service import RecipeRetrievalService


class RecipeKBUnitTests(unittest.TestCase):
    def test_configuration_is_isolated_from_mysql_and_redacts_password(self) -> None:
        environment = {
            "RECIPE_DB_HOST": "localhost",
            "RECIPE_DB_PORT": "55432",
            "RECIPE_DB_NAME": "recipe_test",
            "RECIPE_DB_USER": "recipe_user",
            "RECIPE_DB_PASSWORD": "recipe-secret",
            "MYSQL_PASSWORD": "must-not-be-used",
            "RECIPE_EMBEDDING_MODEL": "intfloat/multilingual-e5-small",
            "RECIPE_EMBEDDING_DIMENSION": "384",
        }
        with patch.dict(os.environ, environment, clear=True):
            config = RecipeKBConfig.from_env()
        self.assertEqual(config.password, "recipe-secret")
        self.assertNotIn("recipe-secret", repr(config))
        self.assertNotIn("must-not-be-used", repr(config))

    def test_configuration_requires_dedicated_password(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RecipeKBConfigurationError):
                RecipeKBConfig.from_env()

    def test_frozen_e5_dimension_is_validated(self) -> None:
        with self.assertRaises(RecipeKBConfigurationError):
            RecipeKBConfig(
                password="secret",
                embedding_model="intfloat/multilingual-e5-small",
                embedding_dimension=768,
            ).validate()
        with self.assertRaises(EmbeddingResponseError):
            validate_vector_dimensions([(1.0, 0.0)], 384)

    def test_migration_has_required_relational_tables_and_no_ann_index(self) -> None:
        migration = Path(
            "recipe_pipeline/recipe_kb/migrations/001_initial.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", migration)
        for table in (
            "recipes", "ingredients", "ingredient_aliases", "recipe_ingredients",
            "recipe_steps", "recipe_taste_profiles", "recipe_nutrition", "tags",
            "recipe_tags", "recipe_sources", "recipe_embeddings", "dataset_versions",
            "ingestion_runs",
        ):
            self.assertIn(f"CREATE TABLE {table}", migration)
        lowered = migration.casefold()
        self.assertNotIn("using hnsw", lowered)
        self.assertNotIn("using ivfflat", lowered)

    def test_vector_metadata_maps_step17h_views_without_template_changes(self) -> None:
        self.assertEqual(REPRESENTATION_DB_NAMES[EmbeddingKind.FULL_RECIPE], "FULL_SEMANTIC")
        self.assertEqual(RecipeEmbeddingTextBuilder.__module__, "recipe_pipeline.evaluation.embedding")

    def test_golden_source_invariants_are_enforced(self) -> None:
        from recipe_pipeline.sources import load_recipe_jsonl

        recipes = load_recipe_jsonl(
            Path("recipe_pipeline/output/golden_500/recipes.jsonl")
        )
        GoldenDatasetImporter._validate_source(recipes)
        self.assertEqual(len(recipes), 492)
        self.assertFalse(any(recipe.quality.human_reviewed for recipe in recipes))

    def test_structured_ingredient_aliases_use_catalog_normalization(self) -> None:
        service = RecipeRetrievalService.__new__(RecipeRetrievalService)
        service._catalog = IngredientCatalog()

        _ids, names = service._resolve_ingredients(
            ["  tomato ", "西 红 柿", "eggs"]
        )

        self.assertEqual(names, ["番茄", "鸡蛋"])


if __name__ == "__main__":
    unittest.main()
