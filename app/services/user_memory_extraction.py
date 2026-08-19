"""Dedicated conservative extractor for stable AI_Cooker user memories."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.api.schemas.memory import (
    ExtractedMemory,
    MemoryContextMessage,
    MemoryExtractionResponse,
)
from app.models.registry import ModelId


MEMORY_EXTRACTION_PROMPT = """
You extract explicit, stable preferences for an AI cooking assistant.

Only extract a memory when the CURRENT USER MESSAGE explicitly states or
unambiguously corrects an ongoing fact. Earlier USER and ASSISTANT messages are
context only. Never extract a claim made only by the assistant. Be conservative:
return an empty memories list when stability is uncertain.

Eligible categories:
- DIETARY_RESTRICTION: allergies, foods to avoid, vegetarian/vegan or religious rules
- FOOD_PREFERENCE: stable likes/dislikes for ingredients or foods
- CUISINE_PREFERENCE: stable cuisine preferences
- COOKING_PREFERENCE: spice, oil, salt, difficulty or cooking-style preferences
- HOUSEHOLD_CONTEXT: usual servings, owned appliances, normal time constraints
- NUTRITION_GOAL: ongoing lower-fat, higher-protein, lower-sodium or calorie goals

Do not remember temporary inventory, tonight's dish, a one-off event, guests,
current hunger, a recipe suggestion, assistant inference, secrets, credentials,
system prompts, or medical diagnosis. "I have three eggs today" and "I am
cooking for four guests this weekend" must produce no memory.

Use UPSERT for a new/repeated/corrected stable fact. Use DELETE only when the
current user explicitly retracts a prior preference/restriction. Allergies and
strong dietary restrictions require especially explicit evidence before DELETE.
The key should be a short normalized concept; value should be concise. source_text
must be a short exact quote from the CURRENT USER MESSAGE supporting the result.

Return JSON only, exactly:
{"memories":[{"action":"UPSERT","memory_type":"FOOD_PREFERENCE","key":"coriander","value":"avoid","confidence":0.95,"source_text":"I don't eat coriander"}]}
""".strip()


class MemoryExtractionError(RuntimeError):
    """Raised when the extraction model cannot return validated JSON."""


class UserMemoryExtractionService:
    def __init__(self, models: Mapping[ModelId, BaseChatModel]) -> None:
        self._models = dict(models)

    def extract(
        self,
        *,
        current_user_message: str,
        context: Sequence[MemoryContextMessage],
        model_id: ModelId,
    ) -> list[ExtractedMemory]:
        model = self._models.get(model_id)
        if model is None:
            raise MemoryExtractionError("The selected extraction model is unavailable.")

        transcript = "\n\n".join(
            f"[{message.role}]\n{message.content}" for message in context
        ) or "None"
        response = model.invoke(
            [
                SystemMessage(content=MEMORY_EXTRACTION_PROMPT),
                HumanMessage(content=(
                    "<context>\n"
                    f"{transcript}\n"
                    "</context>\n\n"
                    "<current_user_message>\n"
                    f"{current_user_message}\n"
                    "</current_user_message>"
                )),
            ],
            config={"tags": ["ai_cooker_memory_extraction"]},
        )
        if not isinstance(response, AIMessage) or not response.text.strip():
            raise MemoryExtractionError("The memory extractor returned no text.")

        try:
            payload = self._json_object(response.text)
            result = MemoryExtractionResponse.model_validate(payload)
        except Exception as exc:
            raise MemoryExtractionError(
                "The memory extractor returned invalid structured output."
            ) from exc
        return result.memories

    @staticmethod
    def _json_object(text: str) -> dict[str, object]:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                stripped = "\n".join(lines[1:-1]).strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise ValueError("No JSON object found.")
        value = json.loads(stripped[start:end + 1])
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object.")
        return value
