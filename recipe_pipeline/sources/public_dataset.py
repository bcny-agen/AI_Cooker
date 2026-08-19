"""Generic adapter boundary for future public-dataset importers."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from pydantic import ValidationError

from recipe_pipeline.schemas.recipe import RawRecipe
from recipe_pipeline.sources.base import InvalidSourceRecord


PublicRecordParser = Callable[[dict[str, Any]], RawRecipe]


class PublicDatasetSource:
    def __init__(
        self,
        records: Sequence[dict[str, Any]],
        parser: PublicRecordParser | None = None,
    ):
        self._records = records
        self._parser = parser or _parse_recipe_record

    def load(self) -> Iterable[RawRecipe | InvalidSourceRecord]:
        for index, record in enumerate(self._records):
            try:
                yield self._parser(record)
            except (ValidationError, ValueError, TypeError) as exc:
                source = record.get("source")
                source_record_id = (
                    str(source.get("source_record_id"))
                    if isinstance(source, dict) and source.get("source_record_id")
                    else f"public-record-{index + 1}"
                )
                yield InvalidSourceRecord(source_record_id, str(exc))


def _parse_recipe_record(record: dict[str, Any]) -> RawRecipe:
    return RawRecipe.model_validate_json(
        json.dumps(record, ensure_ascii=False, default=str)
    )
