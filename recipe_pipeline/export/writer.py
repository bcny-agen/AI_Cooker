"""UTF-8 JSONL and report export with same-filesystem atomic replacement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from recipe_pipeline.pipeline import PipelineResult
from recipe_pipeline.schemas.recipe import RecipeV1


@dataclass(frozen=True, slots=True)
class ExportedArtifacts:
    recipes_jsonl: Path
    validation_report: Path
    quality_report: Path
    recipe_schema: Path
    generation_report: Path | None = None


class DatasetExporter:
    def export(
        self,
        result: PipelineResult,
        output_dir: Path,
        *,
        generation_report: dict[str, object] | None = None,
    ) -> ExportedArtifacts:
        output_dir.mkdir(parents=True, exist_ok=True)
        recipes_path = output_dir / "recipes.jsonl"
        validation_path = output_dir / "validation_report.json"
        quality_path = output_dir / "quality_report.json"
        schema_path = output_dir / "recipe_schema_v1.json"
        generation_path = (
            output_dir / "generation_report.json"
            if generation_report is not None
            else None
        )

        self._atomic_write(
            recipes_path,
            "".join(recipe.model_dump_json() + "\n" for recipe in result.recipes),
        )
        self._atomic_write_json(
            validation_path,
            {
                "summary": result.summary(),
                "items": [report.model_dump(mode="json") for report in result.validation_reports],
            },
        )
        self._atomic_write_json(
            quality_path,
            {
                "summary": result.summary(),
                "thresholds": {"reject_below": 0.70, "publish_at_or_above": 0.85},
                "items": [report.model_dump(mode="json") for report in result.quality_reports],
            },
        )
        self._atomic_write_json(schema_path, RecipeV1.model_json_schema())
        if generation_path is not None:
            self._atomic_write_json(generation_path, generation_report)
        return ExportedArtifacts(
            recipes_path,
            validation_path,
            quality_path,
            schema_path,
            generation_path,
        )

    @staticmethod
    def _atomic_write_json(path: Path, payload: object) -> None:
        DatasetExporter._atomic_write(
            path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(path)
