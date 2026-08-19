"""Schemas for conservative long-term user-memory extraction."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.registry import DEFAULT_MODEL_ID, ModelId


MemoryType = Literal[
    "DIETARY_RESTRICTION",
    "FOOD_PREFERENCE",
    "CUISINE_PREFERENCE",
    "COOKING_PREFERENCE",
    "HOUSEHOLD_CONTEXT",
    "NUTRITION_GOAL",
]
MemoryAction = Literal["UPSERT", "DELETE"]


class MemoryContextMessage(BaseModel):
    role: Literal["USER", "ASSISTANT"]
    content: Annotated[str, Field(min_length=1, max_length=10_000)]


class MemoryExtractionRequest(BaseModel):
    current_user_message: Annotated[str, Field(min_length=1, max_length=10_000)]
    context: Annotated[
        list[MemoryContextMessage],
        Field(default_factory=list, max_length=8),
    ]
    model_id: ModelId = DEFAULT_MODEL_ID


class ExtractedMemory(BaseModel):
    action: MemoryAction
    memory_type: MemoryType
    key: Annotated[str, Field(min_length=1, max_length=80)]
    value: Annotated[str, Field(min_length=1, max_length=255)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    source_text: Annotated[str, Field(min_length=1, max_length=500)]

    @field_validator("key", "value", "source_text")
    @classmethod
    def require_trimmed_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Memory fields must not be blank.")
        return normalized


class MemoryExtractionResponse(BaseModel):
    memories: Annotated[list[ExtractedMemory], Field(max_length=12)]
