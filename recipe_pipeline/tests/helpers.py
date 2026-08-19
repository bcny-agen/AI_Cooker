"""Shared deterministic test fixtures."""

from recipe_pipeline.generation import FixtureRecipeGenerator
from recipe_pipeline.normalization import RecipeNormalizer
from recipe_pipeline.schemas.recipe import RawRecipe, RecipeCategory, RecipeV1


def raw_recipe(index: int = 0) -> RawRecipe:
    return FixtureRecipeGenerator().generate_recipe_batch(
        RecipeCategory.MAIN_DISH, index + 1
    )[index]


def normalized_recipe(index: int = 0) -> RecipeV1:
    return RecipeNormalizer().normalize(raw_recipe(index))
