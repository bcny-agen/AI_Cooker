"""Adapter for already curated/manual records."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence

from pydantic import ValidationError

from recipe_pipeline.schemas.recipe import RawRecipe
from recipe_pipeline.sources.base import InvalidSourceRecord


class ManualRecipeSource:
    def __init__(self, records: Sequence[RawRecipe | dict]):
        self._records = records

    def load(self) -> Iterable[RawRecipe | InvalidSourceRecord]:
        for index, record in enumerate(self._records):
            try:
                yield (
                    record
                    if isinstance(record, RawRecipe)
                    else RawRecipe.model_validate_json(
                        json.dumps(record, ensure_ascii=False, default=str)
                    )
                )
            except (ValidationError, ValueError, TypeError) as exc:
                yield InvalidSourceRecord(
                    source_record_id=_source_record_id(record, index),
                    error=str(exc),
                )


def _source_record_id(record: RawRecipe | dict, index: int) -> str:
    if isinstance(record, dict):
        source = record.get("source")
        if isinstance(source, dict) and source.get("source_record_id"):
            return str(source["source_record_id"])
    return f"manual-record-{index + 1}"
