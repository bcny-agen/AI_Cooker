"""Tests for environment-backed application settings."""

import os
import unittest
from unittest.mock import patch

from app.config.settings import Settings, SettingsError
from app.models.registry import ModelId, build_model_definitions


VALID_ENV = {
    "MODEL_NAME": "step-3.7-flash",
    "MODEL_API_KEY": "test-model-key",
    "MODEL_BASE_URL": "https://model.example/v1",
    "MYSQL_HOST": "localhost",
    "MYSQL_PORT": "3306",
    "MYSQL_USER": "cook user",
    "MYSQL_PASSWORD": "p@ss:/?",
    "MYSQL_DATABASE": "agent web",
    "TAVILY_API_KEY": "test-tavily-key",
}


class SettingsTests(unittest.TestCase):
    def test_loads_typed_settings_and_builds_encoded_mysql_uri(self) -> None:
        with patch.dict(os.environ, VALID_ENV, clear=True):
            settings = Settings.from_env(env_file=None)

        self.assertEqual(settings.mysql_port, 3306)
        self.assertEqual(
            settings.mysql_uri,
            "mysql://cook%20user:p%40ss%3A%2F%3F@localhost:3306/agent%20web",
        )
        definitions = build_model_definitions(settings)
        self.assertTrue(definitions[ModelId.STEP_FLASH_3_7].available)
        self.assertFalse(definitions[ModelId.DEEPSEEK_V4_PRO].available)
        self.assertEqual(
            definitions[ModelId.STEP_FLASH_3_7]
            .context_policy.context_window_tokens,
            256_000,
        )
        self.assertEqual(
            definitions[ModelId.DEEPSEEK_V4_PRO]
            .context_policy.context_window_tokens,
            1_000_000,
        )
        self.assertEqual(settings.recipe_dataset_version, "golden_500_v1")
        self.assertEqual(
            settings.recipe_embedding_model,
            "intfloat/multilingual-e5-small",
        )
        self.assertEqual(settings.recipe_embedding_dimension, 384)
        self.assertIsNone(settings.recipe_db_password)

    def test_loads_optional_deepseek_configuration(self) -> None:
        environment = dict(
            VALID_ENV,
            DEEPSEEK_API_KEY="deepseek-test-key",
            DEEPSEEK_BASE_URL="https://api.deepseek.com",
            DEEPSEEK_MODEL_NAME="deepseek-v4-pro",
        )
        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_env(env_file=None)

        definition = build_model_definitions(settings)[ModelId.DEEPSEEK_V4_PRO]
        self.assertTrue(definition.available)
        self.assertFalse(definition.capabilities.supports_images)

    def test_reports_missing_required_values(self) -> None:
        incomplete = dict(VALID_ENV)
        del incomplete["MODEL_API_KEY"]

        with patch.dict(os.environ, incomplete, clear=True):
            with self.assertRaisesRegex(SettingsError, "MODEL_API_KEY"):
                Settings.from_env(env_file=None)

    def test_tavily_key_is_optional_for_independent_kb_operation(self) -> None:
        environment = dict(VALID_ENV)
        del environment["TAVILY_API_KEY"]

        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_env(env_file=None)

        self.assertEqual(settings.tavily_api_key, "")

    def test_rejects_invalid_mysql_port(self) -> None:
        invalid = dict(VALID_ENV, MYSQL_PORT="not-a-number")

        with patch.dict(os.environ, invalid, clear=True):
            with self.assertRaisesRegex(SettingsError, "must be an integer"):
                Settings.from_env(env_file=None)

    def test_rejects_summary_trigger_at_or_above_model_context(self) -> None:
        invalid = dict(
            VALID_ENV,
            STEP_CONTEXT_WINDOW_TOKENS="1000",
            STEP_SUMMARY_TRIGGER_TOKENS="1000",
        )

        with patch.dict(os.environ, invalid, clear=True):
            with self.assertRaisesRegex(
                SettingsError,
                "STEP_SUMMARY_TRIGGER_TOKENS",
            ):
                Settings.from_env(env_file=None)

    def test_rejects_unsupported_step_image_model(self) -> None:
        invalid = dict(VALID_ENV, STEP_IMAGE_MODEL="step-image-v1")

        with patch.dict(os.environ, invalid, clear=True):
            with self.assertRaisesRegex(
                SettingsError,
                "supports only step-image-edit-2",
            ):
                Settings.from_env(env_file=None)

    def test_recipe_dataset_and_coverage_policy_are_explicitly_configurable(self) -> None:
        environment = dict(
            VALID_ENV,
            RECIPE_DB_PASSWORD="recipe-secret",
            RECIPE_DATASET_VERSION="golden_500_v1",
            RECIPE_COVERAGE_MIN_SEMANTIC_SCORE="0.81",
            RECIPE_COVERAGE_MIN_INGREDIENT_RATIO="0.60",
            RECIPE_COVERAGE_MAX_MISSING_REQUIRED="2",
        )
        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_env(env_file=None)

        self.assertEqual(settings.recipe_db_password, "recipe-secret")
        self.assertEqual(settings.recipe_dataset_version, "golden_500_v1")
        self.assertEqual(settings.recipe_coverage_min_semantic_score, 0.81)
        self.assertEqual(settings.recipe_coverage_min_ingredient_ratio, 0.60)
        self.assertEqual(settings.recipe_coverage_max_missing_required, 2)


if __name__ == "__main__":
    unittest.main()
