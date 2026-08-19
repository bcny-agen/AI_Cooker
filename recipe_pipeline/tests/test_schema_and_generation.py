from __future__ import annotations

import unittest

from pydantic import ValidationError

from recipe_pipeline.generation import (
    AIOutputError,
    FixtureRecipeGenerator,
    LLMRecipeBatchGenerator,
    LLMRecipeEnhancer,
)
from recipe_pipeline.normalization import IngredientCatalog, RecipeNormalizer, UnknownIngredientError
from recipe_pipeline.schemas.recipe import RawRecipe, RecipeCategory, RecipeV1
from recipe_pipeline.tests.helpers import normalized_recipe, raw_recipe


class _FakeTextClient:
    def __init__(self, output: str):
        self.output = output
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return self.output


class SchemaAndGenerationTests(unittest.TestCase):
    def test_recipe_schema_has_versioned_core_sections(self) -> None:
        schema = RecipeV1.model_json_schema()
        self.assertIn("recipe_id", schema["properties"])
        self.assertIn("ingredients", schema["properties"])
        self.assertIn("steps", schema["properties"])
        self.assertEqual(schema["properties"]["schema_version"]["default"], "1.0")

    def test_invalid_raw_schema_is_rejected(self) -> None:
        payload = raw_recipe().model_dump(mode="python")
        del payload["name"]
        with self.assertRaises(ValidationError):
            RawRecipe.model_validate(payload)

    def test_aliases_resolve_to_one_canonical_ingredient_id(self) -> None:
        catalog = IngredientCatalog()
        self.assertEqual(catalog.resolve("番茄").ingredient_id, catalog.resolve("西红柿").ingredient_id)
        self.assertEqual(catalog.resolve("tomatoes").ingredient_id, catalog.resolve("番茄").ingredient_id)

    def test_unknown_ingredient_is_rejected_instead_of_guessed(self) -> None:
        raw = raw_recipe()
        unknown = raw.ingredients[0].model_copy(update={"name": "虚构月球蔬菜"})
        raw = raw.model_copy(update={"ingredients": [unknown, *raw.ingredients[1:]]})
        with self.assertRaises(UnknownIngredientError):
            RecipeNormalizer().normalize(raw)

    def test_malformed_ai_enhancement_json_is_rejected(self) -> None:
        enhancer = LLMRecipeEnhancer(_FakeTextClient("not-json"))
        with self.assertRaises(AIOutputError):
            enhancer.enhance(normalized_recipe())

    def test_valid_ai_enhancement_json_is_revalidated(self) -> None:
        recipe = normalized_recipe()
        client = _FakeTextClient(recipe.model_dump_json())
        enhanced = LLMRecipeEnhancer(client).enhance(recipe)
        self.assertEqual(enhanced, recipe)
        self.assertEqual(client.calls, 1)

    def test_llm_batch_enforces_maximum_ten_without_calling_client(self) -> None:
        client = _FakeTextClient("[]")
        generator = LLMRecipeBatchGenerator(client)
        with self.assertRaises(ValueError):
            generator.generate_recipe_batch(RecipeCategory.MAIN_DISH, 11)
        self.assertEqual(client.calls, 0)

    def test_fixture_batch_is_bounded_and_marked_test_only(self) -> None:
        recipes = FixtureRecipeGenerator().generate_recipe_batch(
            RecipeCategory.MAIN_DISH, 10
        )
        self.assertEqual(len(recipes), 10)
        self.assertTrue(all(item.source.source_name == "offline_demo_fixture" for item in recipes))
        with self.assertRaises(ValueError):
            FixtureRecipeGenerator().generate_recipe_batch(RecipeCategory.MAIN_DISH, 11)


if __name__ == "__main__":
    unittest.main()
