"""Checkpoint-free forum draft generation from supplied visible history."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.agent.forum_draft_prompt import FORUM_DRAFT_SYSTEM_PROMPT
from app.memory.conversation_summary import ConversationSummaryStore
from app.models.registry import ModelId


class ForumDraftError(RuntimeError):
    """Base error for the dedicated draft generator."""


class InvalidForumDraftInputError(ForumDraftError, ValueError):
    """Raised when no useful visible conversation history was supplied."""


class ForumDraftModelError(ForumDraftError):
    """Raised when the configured provider cannot generate a draft."""


class ForumDraftOutputError(ForumDraftError):
    """Raised when structured and validated fallback output are both invalid."""


@dataclass(frozen=True, slots=True)
class DraftHistoryMessage:
    role: Literal["USER", "ASSISTANT"]
    content: str


class GeneratedForumDraft(BaseModel):
    """Provider-neutral validated draft returned to Java."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=20_000)
    dish_name: str = Field(min_length=1, max_length=160)

    @field_validator("title", "content", "dish_name")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Draft text must not be blank.")
        return normalized


class StructuredDraftRunnable(Protocol):
    def invoke(self, input: Any) -> Any: ...


RELEVANT_HISTORY_PATTERN = re.compile(
    r"\b(recipe|dish|ingredient|cook|step|prepare|stir|bake|boil|fry|tip)\b"
    r"|食谱|菜|食材|烹饪|步骤|做法|炒|煮|烤|建议",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


class ForumDraftService:
    """Use provider models directly, never a checkpointed LangGraph Agent."""

    def __init__(
        self,
        models: Mapping[ModelId, BaseChatModel],
        *,
        summary_store: ConversationSummaryStore | None = None,
        max_history_characters: int = 24_000,
        recent_messages: int = 12,
    ) -> None:
        self._models = dict(models)
        self._summary_store = summary_store
        self._max_history_characters = max_history_characters
        self._recent_messages = recent_messages
        self._structured: dict[ModelId, StructuredDraftRunnable] = {
            model_id: model.with_structured_output(
                GeneratedForumDraft,
                method="function_calling",
                include_raw=True,
            )
            for model_id, model in self._models.items()
        }

    def generate(
        self,
        history: Sequence[DraftHistoryMessage],
        model_id: ModelId,
        conversation_id: str | None = None,
    ) -> GeneratedForumDraft:
        normalized_total = sum(
            len(message.content.strip())
            for message in history
            if message.role in ("USER", "ASSISTANT")
        )
        persisted_summary = None
        if (
            conversation_id
            and self._summary_store is not None
            and normalized_total > self._max_history_characters
        ):
            try:
                persisted_summary = self._summary_store.load(conversation_id)
            except Exception as exc:
                logger.warning(
                    "forum_draft_summary_load_failed error=%s",
                    type(exc).__name__,
                )

        summary_text = persisted_summary.summary if persisted_summary else ""
        history_budget = max(
            1_000,
            self._max_history_characters - len(summary_text),
        )
        selected = select_history(
            history,
            max_characters=history_budget,
            recent_messages=self._recent_messages,
        )
        model = self._models.get(model_id)
        structured = self._structured.get(model_id)
        if model is None or structured is None:
            raise InvalidForumDraftInputError(
                "The selected model is not configured."
            )

        transcript = format_history(selected)
        summary_block = (
            "\n\n<conversation_summary>\n"
            f"{summary_text}\n"
            "</conversation_summary>"
            if summary_text
            else ""
        )
        messages = [
            SystemMessage(content=FORUM_DRAFT_SYSTEM_PROMPT),
            HumanMessage(content=(
                "Create one forum draft from this private conversation transcript. "
                "Return title, content, and dish_name.\n\n"
                f"<conversation>\n{transcript}\n</conversation>"
                f"{summary_block}"
            )),
        ]

        try:
            result = structured.invoke(messages)
            parsed = result.get("parsed") if isinstance(result, dict) else result
            if parsed is not None:
                return GeneratedForumDraft.model_validate(parsed)
        except Exception:
            # Providers differ in native structured-output behavior. A second,
            # JSON-only call is safe because draft generation has no side effect.
            pass

        fallback_messages = [
            messages[0],
            HumanMessage(content=(
                messages[1].content
                + "\n\nReturn only one JSON object with exactly these string keys: "
                + '"title", "content", "dish_name".'
            )),
        ]
        try:
            raw = model.invoke(fallback_messages)
        except Exception as exc:
            raise ForumDraftModelError(
                "The forum draft model request failed."
            ) from exc

        try:
            return GeneratedForumDraft.model_validate_json(
                _extract_json_text(raw)
            )
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ForumDraftOutputError(
                "The model returned an invalid forum draft."
            ) from exc


def select_history(
    history: Sequence[DraftHistoryMessage],
    *,
    max_characters: int,
    recent_messages: int,
) -> list[DraftHistoryMessage]:
    """Deterministically keep the first user request and useful recent turns."""

    normalized = [
        DraftHistoryMessage(message.role, message.content.strip())
        for message in history
        if message.role in ("USER", "ASSISTANT") and message.content.strip()
    ]
    if not normalized:
        raise InvalidForumDraftInputError(
            "Conversation history does not contain usable messages."
        )

    total = sum(len(item.content) for item in normalized)
    if total <= max_characters:
        return normalized

    first_user_index = next(
        (index for index, item in enumerate(normalized) if item.role == "USER"),
        0,
    )
    recent_indices = list(range(
        max(0, len(normalized) - recent_messages),
        len(normalized),
    ))
    relevant_indices = [
        index
        for index, item in enumerate(normalized)
        if RELEVANT_HISTORY_PATTERN.search(item.content)
    ]
    priority = [
        first_user_index,
        *reversed(recent_indices),
        *reversed(relevant_indices),
    ]

    selected: dict[int, DraftHistoryMessage] = {}
    remaining = max_characters
    for index in priority:
        if index in selected or remaining <= 0:
            continue
        item = normalized[index]
        content = item.content[:remaining]
        if content:
            selected[index] = DraftHistoryMessage(item.role, content)
            remaining -= len(content)

    return [selected[index] for index in sorted(selected)]


def format_history(history: Sequence[DraftHistoryMessage]) -> str:
    return "\n\n".join(
        f"[{message.role}]\n{message.content}"
        for message in history
    )


def _extract_json_text(message: Any) -> str:
    if isinstance(message, AIMessage):
        text = message.text
    else:
        text = getattr(message, "text", None)
        if not isinstance(text, str):
            content = getattr(message, "content", None)
            text = content if isinstance(content, str) else ""
    stripped = text.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        stripped = stripped[7:-3].strip()
    elif stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3].strip()
    return stripped
