"""Stable public model identifiers and provider-owned configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.config.settings import Settings


class ModelId(str, Enum):
    """Identifiers shared with Java and Vue; provider names stay internal."""

    STEP_FLASH_3_7 = "STEP_FLASH_3_7"
    DEEPSEEK_V4_PRO = "DEEPSEEK_V4_PRO"


DEFAULT_MODEL_ID = ModelId.STEP_FLASH_3_7


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    supports_text: bool
    supports_tools: bool
    supports_streaming: bool
    supports_images: bool


@dataclass(frozen=True, slots=True)
class ModelContextPolicy:
    """Configured inference limits; token counts are conservative estimates."""

    context_window_tokens: int
    summary_trigger_tokens: int
    keep_recent_tokens: int

    @property
    def safe_input_tokens(self) -> int:
        """Reserve twenty percent for output, tool calls, and count variance."""

        return int(self.context_window_tokens * 0.8)


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    id: ModelId
    display_name: str
    provider_model_name: str
    base_url: str
    api_key: str | None
    capabilities: ModelCapabilities
    context_policy: ModelContextPolicy

    @property
    def available(self) -> bool:
        return bool(
            self.provider_model_name.strip()
            and self.base_url.strip()
            and self.api_key
            and self.api_key.strip()
        )


@dataclass(frozen=True, slots=True)
class PublicModelInfo:
    id: ModelId
    display_name: str
    supports_text: bool
    supports_tools: bool
    supports_streaming: bool
    supports_images: bool
    available: bool


MODEL_CAPABILITIES: dict[ModelId, ModelCapabilities] = {
    ModelId.STEP_FLASH_3_7: ModelCapabilities(
        supports_text=True,
        supports_tools=True,
        supports_streaming=True,
        supports_images=True,
    ),
    ModelId.DEEPSEEK_V4_PRO: ModelCapabilities(
        supports_text=True,
        supports_tools=True,
        supports_streaming=True,
        supports_images=False,
    ),
}


def build_model_definitions(
    settings: Settings,
) -> dict[ModelId, ModelDefinition]:
    """Resolve provider details once without exposing them through the API."""

    return {
        ModelId.STEP_FLASH_3_7: ModelDefinition(
            id=ModelId.STEP_FLASH_3_7,
            display_name="Step 3.7 Flash",
            provider_model_name=settings.model_name,
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            capabilities=MODEL_CAPABILITIES[ModelId.STEP_FLASH_3_7],
            context_policy=ModelContextPolicy(
                context_window_tokens=settings.step_context_window_tokens,
                summary_trigger_tokens=settings.step_summary_trigger_tokens,
                keep_recent_tokens=settings.step_summary_keep_recent_tokens,
            ),
        ),
        ModelId.DEEPSEEK_V4_PRO: ModelDefinition(
            id=ModelId.DEEPSEEK_V4_PRO,
            display_name="DeepSeek V4 Pro",
            provider_model_name=settings.deepseek_model_name,
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key,
            capabilities=MODEL_CAPABILITIES[ModelId.DEEPSEEK_V4_PRO],
            context_policy=ModelContextPolicy(
                context_window_tokens=settings.deepseek_context_window_tokens,
                summary_trigger_tokens=settings.deepseek_summary_trigger_tokens,
                keep_recent_tokens=(
                    settings.deepseek_summary_keep_recent_tokens
                ),
            ),
        ),
    }


def public_model_info(definition: ModelDefinition) -> PublicModelInfo:
    capabilities = definition.capabilities
    return PublicModelInfo(
        id=definition.id,
        display_name=definition.display_name,
        supports_text=capabilities.supports_text,
        supports_tools=capabilities.supports_tools,
        supports_streaming=capabilities.supports_streaming,
        supports_images=capabilities.supports_images,
        available=definition.available,
    )
