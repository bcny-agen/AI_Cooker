"""Transport schemas for checkpoint-free forum draft generation."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.registry import ModelId


class ForumDraftHistoryMessage(BaseModel):
    role: Literal["USER", "ASSISTANT"]
    content: Annotated[str, Field(min_length=1, max_length=20_000)]

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("History content must not be blank.")
        return value


class ForumDraftRequest(BaseModel):
    messages: Annotated[list[ForumDraftHistoryMessage], Field(min_length=1, max_length=500)]
    model_id: ModelId
    conversation_id: Annotated[str, Field(min_length=1, max_length=150)] | None = None


class ForumDraftResponse(BaseModel):
    title: str
    content: str
    dish_name: str
