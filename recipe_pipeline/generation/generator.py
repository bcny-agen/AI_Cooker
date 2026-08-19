"""Bounded recipe generation contracts."""

from __future__ import annotations

import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from recipe_pipeline.generation.enhancer import AIOutputError, TextGenerationClient
from recipe_pipeline.schemas.recipe import RawRecipe, RecipeCategory


class RecipeBatchGenerator(Protocol):
    def generate_recipe_batch(
        self, category: RecipeCategory, count: int
    ) -> list[RawRecipe]: ...


class BatchPromptBuilder(Protocol):
    def build(self, category: RecipeCategory, count: int) -> str: ...


class GeneratedRecipeEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipes: list[RawRecipe]


class LLMRecipeBatchGenerator:
    """Future LLM generator boundary; caller supplies the provider client."""

    def __init__(
        self,
        client: TextGenerationClient,
        max_batch_size: int = 10,
        prompt_builder: BatchPromptBuilder | None = None,
    ):
        if not 1 <= max_batch_size <= 10:
            raise ValueError("max_batch_size must be between 1 and 10")
        self._client = client
        self._max_batch_size = max_batch_size
        self._prompt_builder = prompt_builder

    def generate_recipe_batch(
        self, category: RecipeCategory, count: int
    ) -> list[RawRecipe]:
        if not 1 <= count <= self._max_batch_size:
            raise ValueError(f"count must be between 1 and {self._max_batch_size}")
        prompt = (
            self._prompt_builder.build(category, count)
            if self._prompt_builder is not None
            else (
                f"Return a JSON array of exactly {count} RawRecipe objects for "
                f"category {category.value}. JSON only; no markdown."
            )
        )
        raw_output = self._client.complete(prompt)
        try:
            root = json.loads(raw_output)
            if isinstance(root, dict):
                recipes = GeneratedRecipeEnvelope.model_validate_json(raw_output).recipes
            elif isinstance(root, list):
                recipes = TypeAdapter(list[RawRecipe]).validate_json(raw_output)
            else:
                raise ValueError("generated JSON root must be an object or array")
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise AIOutputError("AI recipe batch failed RawRecipe validation") from exc
        if len(recipes) != count:
            raise AIOutputError("AI recipe batch returned an unexpected item count")
        return recipes
