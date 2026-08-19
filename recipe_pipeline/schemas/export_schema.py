"""JSON Schema export for downstream contracts."""

import json
from pathlib import Path

from recipe_pipeline.schemas.recipe import RecipeV1


def export_recipe_json_schema(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(RecipeV1.model_json_schema(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
