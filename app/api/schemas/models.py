"""Public model capability schemas."""

from pydantic import BaseModel, ConfigDict

from app.models.registry import ModelId


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ModelId
    display_name: str
    supports_text: bool
    supports_tools: bool
    supports_streaming: bool
    supports_images: bool
    available: bool
