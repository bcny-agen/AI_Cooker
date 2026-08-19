"""Schemas for the chat endpoint."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.models.registry import DEFAULT_MODEL_ID, ModelId


class ChatRequest(BaseModel):
    conversation_id: Annotated[str, Field(min_length=1, max_length=150)]
    message: Annotated[str, Field(min_length=1)]
    image_url: HttpUrl | None = None
    model_id: ModelId = DEFAULT_MODEL_ID
    continuation_expected: bool = False
    user_memories: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=300)]],
        Field(default_factory=list, max_length=24),
    ]

    @field_validator("user_memories")
    @classmethod
    def validate_user_memories(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("user_memories must not contain blank entries.")
        if sum(len(value) for value in normalized) > 5_000:
            raise ValueError("user_memories is too large.")
        return normalized

    @field_validator("image_url")
    @classmethod
    def require_https(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and value.scheme != "https":
            raise ValueError("image_url must use HTTPS.")
        return value


class RecoveryHistoryMessage(BaseModel):
    message_id: Annotated[int, Field(gt=0)]
    role: Literal["USER", "ASSISTANT"]
    content: Annotated[str, Field(min_length=1, max_length=20_000)]


class ChatRecoveryRequest(ChatRequest):
    recovery_history: Annotated[
        list[RecoveryHistoryMessage],
        Field(max_length=500),
    ]


class GeneratedImageTransfer(BaseModel):
    generation_id: str
    image_model: str
    prompt: str


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    generated_images: list[GeneratedImageTransfer] = Field(default_factory=list)
