"""Validation report models kept separate from the recipe data contract."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IssueSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    path: str = Field(default="", max_length=300)
    severity: IssueSeverity


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_record_id: str
    recipe_id: UUID | None = None
    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
