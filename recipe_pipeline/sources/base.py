"""Source adapter contract."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from recipe_pipeline.schemas.recipe import RawRecipe


@dataclass(frozen=True, slots=True)
class InvalidSourceRecord:
    source_record_id: str
    error: str


class RecipeSource(Protocol):
    def load(self) -> Iterable[RawRecipe | InvalidSourceRecord]: ...
