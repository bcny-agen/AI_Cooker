"""Agent-callable Step text-to-image tool for one selected dish."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from threading import Lock
import time
from typing import Callable, Protocol
from uuid import uuid4

from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.config.settings import Settings


class DishImageGenerationError(RuntimeError):
    """Raised when Step does not return one usable image."""


@dataclass(frozen=True, slots=True)
class GeneratedImagePayload:
    generation_id: str
    data: bytes
    content_type: str
    image_model: str
    prompt: str
    created_at: float


class GeneratedImageBuffer:
    """Small TTL buffer used only for the same-host Python-to-Java handoff."""

    def __init__(self, ttl_seconds: int = 600, max_items: int = 32) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_items = max_items
        self._items: dict[str, GeneratedImagePayload] = {}
        self._lock = Lock()

    def put(
        self,
        data: bytes,
        content_type: str,
        image_model: str,
        prompt: str,
    ) -> GeneratedImagePayload:
        now = time.monotonic()
        generation_id = str(uuid4())
        payload = GeneratedImagePayload(
            generation_id=generation_id,
            data=data,
            content_type=content_type,
            image_model=image_model,
            prompt=prompt,
            created_at=now,
        )
        with self._lock:
            self._remove_expired(now)
            if len(self._items) >= self._max_items:
                oldest = min(
                    self._items.values(),
                    key=lambda candidate: candidate.created_at,
                )
                self._items.pop(oldest.generation_id, None)
            self._items[generation_id] = payload
        return payload

    def get(self, generation_id: str) -> GeneratedImagePayload | None:
        now = time.monotonic()
        with self._lock:
            self._remove_expired(now)
            return self._items.get(generation_id)

    def _remove_expired(self, now: float) -> None:
        expired = [
            key
            for key, value in self._items.items()
            if now - value.created_at > self._ttl_seconds
        ]
        for key in expired:
            self._items.pop(key, None)


class DishImageGenerator(Protocol):
    model: str

    def generate(self, prompt: str) -> tuple[bytes, str]: ...


class StepDishImageGenerator:
    """OpenAI-compatible Step image generation adapter."""

    def __init__(self, settings: Settings) -> None:
        self.model = settings.image_model_name
        self._client = OpenAI(
            api_key=settings.model_api_key,
            base_url=settings.model_base_url,
        )

    def generate(self, prompt: str) -> tuple[bytes, str]:
        try:
            response = self._client.images.generate(
                model=self.model,
                prompt=prompt,
                size="1024x1024",
                response_format="b64_json",
                extra_body={
                    "cfg_scale": 1.0,
                    "steps": 8,
                    "text_mode": False,
                },
            )
        except OpenAIError as exc:
            raise DishImageGenerationError(
                "Step image generation failed."
            ) from exc

        if not response.data or not response.data[0].b64_json:
            raise DishImageGenerationError(
                "Step returned no generated image."
            )
        try:
            data = base64.b64decode(
                response.data[0].b64_json,
                validate=True,
            )
        except (ValueError, TypeError) as exc:
            raise DishImageGenerationError(
                "Step returned invalid image data."
            ) from exc
        if not data or len(data) > 20 * 1024 * 1024:
            raise DishImageGenerationError(
                "Step returned an invalid image size."
            )
        return data, _detect_content_type(data)


class DishImageInput(BaseModel):
    dish_description: str = Field(
        min_length=2,
        max_length=240,
        description=(
            "The selected dish name and only its known ingredients/cooking "
            "style. Do not pass the whole conversation."
        ),
    )


def build_culinary_image_prompt(dish_description: str) -> str:
    description = " ".join(dish_description.strip().split())
    if not description:
        raise DishImageGenerationError("Dish description is required.")
    prompt = (
        f"A realistic professional food photograph of {description}. "
        "Show only ingredients supported by that dish description. "
        "Natural appetizing texture, thoughtful restaurant plating, "
        "warm natural side lighting, high-detail editorial food photography, "
        "shallow depth of field, no people, no text, no watermark."
    )
    return prompt[:512]


def create_dish_image_tool(
    settings: Settings,
    buffer: GeneratedImageBuffer,
    *,
    generator: DishImageGenerator | None = None,
) -> StructuredTool:
    resolved_generator = generator or StepDishImageGenerator(settings)

    def generate_dish_image(dish_description: str) -> str:
        """Generate exactly one private preview image for a selected dish."""

        prompt = build_culinary_image_prompt(dish_description)
        _emit({
            "stage": "generating_image",
            "message": "Generating dish image...",
        })
        try:
            image_bytes, content_type = resolved_generator.generate(prompt)
            payload = buffer.put(
                image_bytes,
                content_type,
                resolved_generator.model,
                prompt,
            )
        except DishImageGenerationError:
            _emit({
                "stage": "image_generation_failed",
                "message": "Image generation failed.",
                "dish_description": dish_description,
            })
            return json.dumps({
                "status": "failed",
                "message": "The dish image could not be generated.",
            })

        transfer = {
            "generation_id": payload.generation_id,
            "image_model": payload.image_model,
            "prompt": payload.prompt,
        }
        _emit({"stage": "generated_image_ready", **transfer})
        return json.dumps({"status": "generated", **transfer})

    return StructuredTool.from_function(
        func=generate_dish_image,
        name="generate_dish_image",
        description=(
            "Generate one realistic food image only when the user explicitly "
            "asks to see or create an image of a specific dish. Never call it "
            "automatically for ordinary recipe recommendations or cooking questions."
        ),
        args_schema=DishImageInput,
    )


def _emit(event: dict[str, str]) -> None:
    try:
        get_stream_writer()(event)
    except (RuntimeError, KeyError):
        # Non-streaming invocation has no custom-event writer.
        return


def _detect_content_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise DishImageGenerationError("Step returned an unsupported image format.")
