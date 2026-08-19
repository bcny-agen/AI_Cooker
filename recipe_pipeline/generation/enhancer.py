"""Optional AI enhancement with strict output parsing and no provider coupling."""

from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from recipe_pipeline.schemas.recipe import RecipeV1


class AIOutputError(ValueError):
    """The provider returned malformed or schema-invalid output."""


class TextGenerationClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class RecipeEnhancer(Protocol):
    def enhance(self, recipe: RecipeV1) -> RecipeV1: ...


class NoOpRecipeEnhancer:
    def enhance(self, recipe: RecipeV1) -> RecipeV1:
        return recipe


class LLMRecipeEnhancer:
    """Provider-neutral enhancer. AI output is untrusted until RecipeV1 validates."""

    def __init__(self, client: TextGenerationClient):
        self._client = client

    def enhance(self, recipe: RecipeV1) -> RecipeV1:
        prompt = (
            "Return one complete Recipe Schema v1 object as JSON only. "
            "Preserve recipe_id, source provenance, factual quantities and safety.\n"
            + recipe.model_dump_json()
        )
        raw_output = self._client.complete(prompt)
        try:
            enhanced = RecipeV1.model_validate_json(raw_output)
            if enhanced.recipe_id != recipe.recipe_id or enhanced.source != recipe.source:
                raise ValueError("AI enhancement must preserve recipe identity and provenance")
            return enhanced
        except (ValidationError, ValueError, TypeError) as exc:
            raise AIOutputError("AI enhancement output failed Recipe Schema v1 validation") from exc
