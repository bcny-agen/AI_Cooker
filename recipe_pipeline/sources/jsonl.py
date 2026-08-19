"""Load already validated Recipe Schema v1 JSONL as a duplicate baseline."""

from __future__ import annotations

from pathlib import Path

from recipe_pipeline.schemas.recipe import RecipeV1


def load_recipe_jsonl(path: Path) -> list[RecipeV1]:
    recipes = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            recipes.append(RecipeV1.model_validate_json(line))
        except Exception as exc:
            raise ValueError(
                f"invalid Recipe Schema v1 JSONL at line {line_number}"
            ) from exc
    return recipes
