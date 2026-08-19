"""Construction of the OpenAI-compatible chat model used by AI_Cooker."""

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from app.config.settings import Settings
from app.models.registry import ModelDefinition, ModelId, build_model_definitions


class ModelConfigurationError(RuntimeError):
    """Raised when the configured chat model cannot be constructed."""


def create_chat_model(
    settings: Settings,
    model_id: ModelId = ModelId.STEP_FLASH_3_7,
) -> BaseChatModel:
    """Create one configured model through LangChain's OpenAI adapter."""

    definition = build_model_definitions(settings)[model_id]
    return create_chat_model_from_definition(definition)


def create_chat_model_from_definition(
    definition: ModelDefinition,
) -> BaseChatModel:
    if not definition.available:
        raise ModelConfigurationError(
            f"Model {definition.id.value} is not configured."
        )

    try:
        return init_chat_model(
            model=definition.provider_model_name,
            model_provider="openai",
            api_key=definition.api_key,
            base_url=definition.base_url,
        )
    except Exception as exc:
        raise ModelConfigurationError(
            "Unable to configure the OpenAI-compatible chat model."
        ) from exc


def create_chat_models(
    definitions: dict[ModelId, ModelDefinition],
) -> dict[ModelId, BaseChatModel]:
    """Create each configured provider model once for reuse by all services."""

    return {
        model_id: create_chat_model_from_definition(definition)
        for model_id, definition in definitions.items()
        if definition.available
    }
