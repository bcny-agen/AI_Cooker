"""Adapter around a bounded AI or fixture recipe generator."""

from __future__ import annotations

from collections.abc import Iterable

from recipe_pipeline.generation.generator import RecipeBatchGenerator
from recipe_pipeline.schemas.recipe import RawRecipe, RecipeCategory


class SyntheticRecipeSource:
    def __init__(
        self,
        generator: RecipeBatchGenerator,
        category: RecipeCategory,
        count: int,
    ):
        if not 1 <= count <= 10:
            raise ValueError("synthetic source count must be between 1 and 10")
        self._generator = generator
        self._category = category
        self._count = count

    def load(self) -> Iterable[RawRecipe]:
        return iter(self._generator.generate_recipe_batch(self._category, self._count))
