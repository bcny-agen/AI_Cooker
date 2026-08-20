"""Simple application service for text and image conversations."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
import json
import logging
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

import pymysql
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from openai import OpenAIError

from app.agent.context import AgentRunContext
from app.agent.constraints import (
    extract_constraints_for_answer,
    unsafe_constraint_mentions,
)
from app.memory.conversation_summary import (
    ConversationSummaryStore,
    ConversationSummaryStoreError,
    RECOVERED_SUMMARY_REFERENCE,
)
from app.models.registry import (
    DEFAULT_MODEL_ID,
    MODEL_CAPABILITIES,
    ModelDefinition,
    ModelId,
    PublicModelInfo,
    public_model_info,
)


logger = logging.getLogger(__name__)


class AgentInvoker(Protocol):
    """The small part of a compiled LangGraph Agent used by this service."""

    def invoke(
        self,
        input: dict[str, Any],
        config: dict[str, Any],
        *,
        context: AgentRunContext | None = None,
    ) -> dict[str, Any]: ...

    def stream(
        self,
        input: dict[str, Any],
        config: dict[str, Any],
        *,
        stream_mode: list[str],
        context: AgentRunContext | None = None,
    ) -> Iterator[tuple[str, Any]]: ...

    def get_state(self, config: dict[str, Any]) -> Any: ...

    def update_state(
        self,
        config: dict[str, Any],
        values: dict[str, Any],
        as_node: str | None = None,
    ) -> dict[str, Any]: ...


StreamEventType = Literal[
    "status",
    "token",
    "generated_image",
    "image_error",
    "done",
]


@dataclass(frozen=True, slots=True)
class GeneratedImageTransfer:
    generation_id: str
    image_model: str
    prompt: str

    def as_dict(self) -> dict[str, str]:
        return {
            "generation_id": self.generation_id,
            "image_model": self.image_model,
            "prompt": self.prompt,
        }


@dataclass(frozen=True, slots=True)
class AgentStreamEvent:
    """Small, transport-neutral event emitted by a streaming Agent run."""

    type: StreamEventType
    stage: str | None = None
    message: str | None = None
    content: str | None = None
    generation_id: str | None = None
    image_model: str | None = None
    prompt: str | None = None

    @classmethod
    def status(cls, stage: str, message: str) -> "AgentStreamEvent":
        return cls(type="status", stage=stage, message=message)

    @classmethod
    def token(cls, content: str) -> "AgentStreamEvent":
        return cls(type="token", content=content)

    @classmethod
    def done(cls) -> "AgentStreamEvent":
        return cls(type="done")

    @classmethod
    def generated_image(
        cls,
        generation_id: str,
        image_model: str,
        prompt: str,
    ) -> "AgentStreamEvent":
        return cls(
            type="generated_image",
            generation_id=generation_id,
            image_model=image_model,
            prompt=prompt,
        )

    @classmethod
    def image_error(cls, message: str) -> "AgentStreamEvent":
        return cls(type="image_error", message=message)

    def as_dict(self) -> dict[str, str]:
        result = {"type": self.type}
        if self.stage is not None:
            result["stage"] = self.stage
        if self.message is not None:
            result["message"] = self.message
        if self.content is not None:
            result["content"] = self.content
        if self.generation_id is not None:
            result["generation_id"] = self.generation_id
        if self.image_model is not None:
            result["image_model"] = self.image_model
        if self.prompt is not None:
            result["prompt"] = self.prompt
        return result


class CookerAgentError(RuntimeError):
    """Base class for errors exposed by CookerAgentService."""


class InvalidAgentInputError(CookerAgentError, ValueError):
    """Raised when conversation, text, or image input is invalid."""


class UnsupportedModelError(InvalidAgentInputError):
    """Raised when a public model ID is unavailable or unknown."""


class UnsupportedModelCapabilityError(InvalidAgentInputError):
    """Raised when a request uses a capability the model does not have."""


class ModelInvocationError(CookerAgentError):
    """Raised when the OpenAI-compatible model request fails."""


class SearchInvocationError(CookerAgentError):
    """Raised when the Tavily search tool fails."""


class CheckpointerInvocationError(CookerAgentError):
    """Raised when checkpoint loading or persistence fails."""


class AgentResponseError(CookerAgentError):
    """Raised when a completed Agent run has no final AI message."""


class AgentExecutionError(CookerAgentError):
    """Raised for an unexpected Agent execution failure."""


class ThreadRecoveryRequiredError(CookerAgentError):
    """Raised before inference when a legacy thread must be rebuilt."""

    def __init__(self, reason: str) -> None:
        super().__init__("Conversation Agent state requires recovery.")
        self.reason = reason


HistoryRole = Literal["USER", "ASSISTANT"]


@dataclass(frozen=True, slots=True)
class ConversationHistoryMessage:
    """Authorized, user-visible business history supplied by Java."""

    message_id: int
    role: HistoryRole
    content: str


class CookerAgentService:
    """Application-facing operations for one compiled cooking Agent."""

    def __init__(
        self,
        agents: AgentInvoker | Mapping[ModelId, AgentInvoker],
        model_definitions: Mapping[ModelId, ModelDefinition] | None = None,
        summary_store: ConversationSummaryStore | None = None,
        recovery_recent_messages: int = 12,
    ) -> None:
        self._agents = (
            dict(agents)
            if isinstance(agents, Mapping)
            else {DEFAULT_MODEL_ID: agents}
        )
        self._model_definitions = dict(model_definitions or {})
        self._summary_store = summary_store
        self._recovery_recent_messages = recovery_recent_messages

    def available_models(self) -> list[PublicModelInfo]:
        if self._model_definitions:
            return [
                public_model_info(self._model_definitions[model_id])
                for model_id in ModelId
            ]
        capabilities = MODEL_CAPABILITIES[DEFAULT_MODEL_ID]
        return [
            PublicModelInfo(
                id=DEFAULT_MODEL_ID,
                display_name="Step 3.7 Flash",
                supports_text=capabilities.supports_text,
                supports_tools=capabilities.supports_tools,
                supports_streaming=capabilities.supports_streaming,
                supports_images=capabilities.supports_images,
                available=True,
            )
        ]

    def chat(
        self,
        conversation_id: str,
        message: str,
        model_id: ModelId = DEFAULT_MODEL_ID,
        user_memories: Sequence[str] = (),
        continuation_expected: bool = False,
    ) -> AIMessage:
        """Send a text message and return only the final AI response."""

        self._validate_conversation_id(conversation_id)
        self._validate_message(message)
        human_message = HumanMessage(content=message)
        return self._invoke(
            conversation_id,
            human_message,
            model_id,
            user_memories,
            continuation_expected=continuation_expected,
            sanitize_images_after=False,
        )

    def chat_with_image(
        self,
        conversation_id: str,
        message: str,
        image_url: str,
        model_id: ModelId = DEFAULT_MODEL_ID,
        user_memories: Sequence[str] = (),
        continuation_expected: bool = False,
    ) -> AIMessage:
        """Send text plus an already-hosted HTTPS image to the same Agent."""

        self._validate_conversation_id(conversation_id)
        self._validate_message(message)
        self._validate_image_url(image_url)
        self._require_image_support(model_id)

        human_message = HumanMessage(
            content=[
                {"type": "text", "text": message},
                {"type": "image", "url": image_url},
            ]
        )
        return self._invoke(
            conversation_id,
            human_message,
            model_id,
            user_memories,
            continuation_expected=continuation_expected,
            sanitize_images_after=True,
        )

    def stream_chat(
        self,
        conversation_id: str,
        message: str,
        model_id: ModelId = DEFAULT_MODEL_ID,
        user_memories: Sequence[str] = (),
        continuation_expected: bool = False,
    ) -> Iterator[AgentStreamEvent]:
        """Stream a text Agent run using LangGraph's native stream API."""

        self._validate_conversation_id(conversation_id)
        self._validate_message(message)
        return self._stream(
            conversation_id,
            HumanMessage(content=message),
            has_image=False,
            model_id=model_id,
            user_memories=user_memories,
            continuation_expected=continuation_expected,
        )

    def stream_chat_with_image(
        self,
        conversation_id: str,
        message: str,
        image_url: str,
        model_id: ModelId = DEFAULT_MODEL_ID,
        user_memories: Sequence[str] = (),
        continuation_expected: bool = False,
    ) -> Iterator[AgentStreamEvent]:
        """Stream a multimodal Agent run for an existing HTTPS image."""

        self._validate_conversation_id(conversation_id)
        self._validate_message(message)
        self._validate_image_url(image_url)
        self._require_image_support(model_id)
        return self._stream(
            conversation_id,
            HumanMessage(
                content=[
                    {"type": "text", "text": message},
                    {"type": "image", "url": image_url},
                ]
            ),
            has_image=True,
            model_id=model_id,
            user_memories=user_memories,
            continuation_expected=continuation_expected,
        )

    def ensure_continuation_ready(
        self,
        conversation_id: str,
        model_id: ModelId = DEFAULT_MODEL_ID,
    ) -> None:
        """Fail before inference if an existing thread needs one-time recovery."""

        self._validate_conversation_id(conversation_id)
        agent = self._agent_for(model_id)
        reason = self._recovery_reason(agent, conversation_id)
        if reason is not None:
            raise ThreadRecoveryRequiredError(reason)

    def recover_thread(
        self,
        conversation_id: str,
        history: Sequence[ConversationHistoryMessage],
        model_id: ModelId = DEFAULT_MODEL_ID,
    ) -> None:
        """Rebuild one unusable checkpoint from Java-authorized visible history."""

        self._validate_conversation_id(conversation_id)
        self._validate_recovery_history(history)
        agent = self._agent_for(model_id)
        reason = self._recovery_reason(agent, conversation_id)
        if reason is None:
            raise InvalidAgentInputError(
                "Conversation Agent state does not require recovery."
            )

        try:
            summary = (
                self._summary_store.load(conversation_id)
                if self._summary_store is not None
                else None
            )
        except (ConversationSummaryStoreError, pymysql.MySQLError) as exc:
            raise CheckpointerInvocationError(
                "Conversation summary loading failed during recovery."
            ) from exc
        selected_history = list(history)
        if summary is not None:
            selected_history = selected_history[-self._recovery_recent_messages:]

        recovered_messages: list[AnyMessage] = [
            self._history_message_to_langchain(message)
            for message in selected_history
        ]
        config = self._thread_config(conversation_id)
        try:
            agent.update_state(
                config,
                {
                    "messages": [
                        RemoveMessage(id=REMOVE_ALL_MESSAGES),
                        *recovered_messages,
                    ]
                },
                as_node="__start__",
            )
            if summary is not None and self._summary_store is not None:
                self._summary_store.save(replace(
                    summary,
                    summarized_through_message_id=(
                        RECOVERED_SUMMARY_REFERENCE
                    ),
                    summarized_message_count=0,
                ))
        except (ConversationSummaryStoreError, pymysql.MySQLError) as exc:
            raise CheckpointerInvocationError(
                "Conversation checkpoint recovery failed."
            ) from exc
        except CookerAgentError:
            raise
        except Exception as exc:
            raise AgentExecutionError(
                "Conversation Agent state recovery failed."
            ) from exc

    def _invoke(
        self,
        conversation_id: str,
        human_message: HumanMessage,
        model_id: ModelId,
        user_memories: Sequence[str],
        *,
        continuation_expected: bool,
        sanitize_images_after: bool,
    ) -> AIMessage:
        config = self._thread_config(conversation_id)
        agent = self._agent_for(model_id)

        try:
            if continuation_expected:
                self._ensure_agent_ready(agent, conversation_id)
            result = agent.invoke(
                {"messages": [human_message]},
                config,
                context=self._run_context(user_memories),
            )
        except OpenAIError as exc:
            logger.warning(
                "cooking_model_invocation_failed provider_error=%s",
                type(exc).__name__,
            )
            raise ModelInvocationError("The cooking model request failed.") from exc
        except pymysql.MySQLError as exc:
            raise CheckpointerInvocationError(
                "Conversation checkpoint loading or persistence failed."
            ) from exc
        except CookerAgentError:
            raise
        except Exception as exc:
            raise AgentExecutionError("The cooking Agent failed unexpectedly.") from exc

        response = self._extract_final_ai_message(result)
        self._log_tool_sources(result.get("messages"))
        transfers = self._extract_generated_image_transfers(
            result.get("messages")
        )
        if transfers:
            response.additional_kwargs["generated_images"] = [
                transfer.as_dict() for transfer in transfers[:1]
            ]
        if sanitize_images_after:
            self._sanitize_historical_images(agent, config)
        return response

    def _stream(
        self,
        conversation_id: str,
        human_message: HumanMessage,
        *,
        has_image: bool,
        model_id: ModelId,
        user_memories: Sequence[str],
        continuation_expected: bool,
    ) -> Iterator[AgentStreamEvent]:
        """Map real LangGraph model/tool events to the public stream contract."""

        initial_stage = "analyzing_image" if has_image else "thinking"
        initial_message = (
            "Analyzing the ingredient image..."
            if has_image
            else "Thinking about your ingredients..."
        )
        yield AgentStreamEvent.status(initial_stage, initial_message)

        config = self._thread_config(conversation_id)
        agent = self._agent_for(model_id)
        tool_statuses_emitted: set[str] = set()
        tool_sources_used: set[str] = set()
        generating_emitted = False
        streamed_parts: list[str] = []
        streamed_by_message_id: dict[str, list[str]] = {}
        tool_request_message_ids: set[str] = set()
        update_final_message: AIMessage | None = None

        try:
            if continuation_expected:
                self._ensure_agent_ready(agent, conversation_id)
            for mode, data in agent.stream(
                {"messages": [human_message]},
                config,
                stream_mode=["messages", "updates", "custom"],
                context=self._run_context(user_memories),
            ):
                if mode == "custom" and isinstance(data, dict):
                    if data.get("stage") == "summarizing_context":
                        yield AgentStreamEvent.status(
                            "summarizing_context",
                            "Compressing older conversation context...",
                        )
                    elif data.get("stage") == "generating_image":
                        yield AgentStreamEvent.status(
                            "generating_image",
                            "Generating dish image...",
                        )
                    elif data.get("stage") == "generated_image_ready":
                        transfer = self._transfer_from_mapping(data)
                        if transfer is not None:
                            yield AgentStreamEvent.generated_image(
                                transfer.generation_id,
                                transfer.image_model,
                                transfer.prompt,
                            )
                    elif data.get("stage") == "image_generation_failed":
                        yield AgentStreamEvent.image_error(
                            "Image generation failed."
                        )
                    continue

                if mode == "messages":
                    if not isinstance(data, tuple) or len(data) != 2:
                        continue
                    chunk, metadata = data
                    if not isinstance(chunk, AIMessageChunk):
                        continue
                    if (
                        isinstance(metadata, dict)
                        and "ai_cooker_context_summary"
                        in metadata.get("tags", [])
                    ):
                        continue

                    chunk_key = self._stream_message_key(chunk, metadata)
                    if self._has_tool_calls(chunk):
                        tool_request_message_ids.add(chunk_key)
                        if streamed_by_message_id.get(chunk_key):
                            raise AgentResponseError(
                                "A tool-request message emitted user-visible text."
                            )
                        tool_names = self._tool_call_names(chunk)
                        tool_sources_used.update(
                            tool_names & {"recipe_search", "web_search"}
                        )
                        for event in self._tool_status_events(
                            tool_names,
                            tool_statuses_emitted,
                        ):
                            yield event
                        continue

                    text = chunk.text
                    if not text:
                        continue
                    if chunk_key in tool_request_message_ids:
                        raise AgentResponseError(
                            "A tool-request message emitted user-visible text."
                        )
                    if not generating_emitted:
                        generating_emitted = True
                        yield AgentStreamEvent.status(
                            "generating_answer",
                            "Generating your recommendation...",
                        )
                    streamed_by_message_id.setdefault(chunk_key, []).append(text)
                    streamed_parts.append(text)
                    yield AgentStreamEvent.token(text)
                    continue

                if mode != "updates" or not isinstance(data, dict):
                    continue

                if "tools" in data:
                    update_tool_names = self._tool_names_from_update(data)
                    tool_sources_used.update(
                        update_tool_names & {"recipe_search", "web_search"}
                    )
                    for event in self._tool_status_events(
                        update_tool_names,
                        tool_statuses_emitted,
                    ):
                        yield event

                candidate = self._extract_ai_message_from_update(data)
                if (
                    candidate is not None
                    and not candidate.tool_calls
                    and candidate.text
                ):
                    update_final_message = candidate
        except OpenAIError as exc:
            logger.warning(
                "cooking_model_stream_failed provider_error=%s",
                type(exc).__name__,
            )
            raise ModelInvocationError("The cooking model request failed.") from exc
        except pymysql.MySQLError as exc:
            raise CheckpointerInvocationError(
                "Conversation checkpoint loading or persistence failed."
            ) from exc
        except CookerAgentError:
            raise
        except Exception as exc:
            raise AgentExecutionError("The cooking Agent failed unexpectedly.") from exc

        final_message, final_state_messages = self._canonical_final_from_state(
            agent, config
        )
        final_text = final_message.text
        final_constraints = extract_constraints_for_answer(
            final_state_messages, user_memories
        )
        unsafe_terms = (
            unsafe_constraint_mentions(final_text, final_constraints)
            if final_constraints.should_search_recipe
            else ()
        )
        if unsafe_terms:
            logger.warning(
                "cooking_agent_constraint_violation term_count=%s",
                len(unsafe_terms),
            )
            raise AgentResponseError(
                "The final Agent response violated an active cooking constraint."
            )

        streamed_text = "".join(streamed_parts)
        if not streamed_text:
            if not generating_emitted:
                yield AgentStreamEvent.status(
                    "generating_answer",
                    "Generating your recommendation...",
                )
            yield AgentStreamEvent.token(final_text)
        elif streamed_text != final_text:
            raise AgentResponseError(
                "Streamed content did not match the final Agent response."
            )
        streamed_message_ids = {
            message_id
            for message_id, parts in streamed_by_message_id.items()
            if parts
        }
        if final_message.id is not None and streamed_message_ids not in (
            set(),
            {final_message.id},
        ):
            raise AgentResponseError(
                "Streamed content came from a non-final Agent message."
            )
        if (
            update_final_message is not None
            and update_final_message.id == final_message.id
            and update_final_message.text != final_text
        ):
            raise AgentResponseError(
                "The final Agent update did not match checkpoint state."
            )

        if has_image:
            self._sanitize_historical_images(agent, config)

        logger.info(
            "cooking_agent_tool_sources recipe_kb=%s tavily=%s both=%s "
            "tavily_fallback_triggered=%s",
            "recipe_search" in tool_sources_used,
            "web_search" in tool_sources_used,
            {"recipe_search", "web_search"}.issubset(tool_sources_used),
            {"recipe_search", "web_search"}.issubset(tool_sources_used),
        )

        yield AgentStreamEvent.status("completed", "Recommendation complete.")
        yield AgentStreamEvent.done()

    def _agent_for(self, model_id: ModelId) -> AgentInvoker:
        try:
            normalized = ModelId(model_id)
        except ValueError as exc:
            raise UnsupportedModelError("The requested model is not supported.") from exc
        agent = self._agents.get(normalized)
        if agent is None:
            raise UnsupportedModelError(
                "The requested model is not configured on this service."
            )
        return agent

    def _ensure_agent_ready(
        self,
        agent: AgentInvoker,
        conversation_id: str,
    ) -> None:
        reason = self._recovery_reason(agent, conversation_id)
        if reason is not None:
            raise ThreadRecoveryRequiredError(reason)

    def _recovery_reason(
        self,
        agent: AgentInvoker,
        conversation_id: str,
    ) -> str | None:
        try:
            snapshot = agent.get_state(self._thread_config(conversation_id))
        except pymysql.MySQLError as exc:
            raise CheckpointerInvocationError(
                "Conversation checkpoint loading failed."
            ) from exc
        except Exception as exc:
            raise AgentExecutionError(
                "Conversation checkpoint inspection failed."
            ) from exc

        values = getattr(snapshot, "values", None)
        messages = values.get("messages") if isinstance(values, dict) else None
        if not isinstance(messages, list) or not messages:
            return "missing_checkpoint"
        if any(self._contains_image(message) for message in messages):
            return "historical_image"
        return None

    @staticmethod
    def _stream_message_key(
        message: AIMessageChunk,
        metadata: Any,
    ) -> str:
        if message.id:
            return message.id
        if not isinstance(metadata, dict):
            return "unidentified-model-message"
        return (
            f"step:{metadata.get('langgraph_step')}:"
            f"node:{metadata.get('langgraph_node')}"
        )

    @classmethod
    def _canonical_final_from_state(
        cls,
        agent: AgentInvoker,
        config: dict[str, Any],
    ) -> tuple[AIMessage, list[AnyMessage]]:
        """Return the final visible answer and its full checkpoint context."""

        try:
            snapshot = agent.get_state(config)
        except pymysql.MySQLError as exc:
            raise CheckpointerInvocationError(
                "Conversation checkpoint loading failed after streaming."
            ) from exc
        except Exception as exc:
            raise AgentExecutionError(
                "Conversation checkpoint inspection failed after streaming."
            ) from exc
        values = getattr(snapshot, "values", None)
        messages = values.get("messages") if isinstance(values, dict) else None
        if not isinstance(messages, list) or not messages:
            raise AgentResponseError("The Agent returned no final state.")
        last_human_index = max(
            (
                index
                for index, message in enumerate(messages)
                if isinstance(message, HumanMessage)
            ),
            default=-1,
        )
        for message in reversed(messages[last_human_index + 1:]):
            if (
                isinstance(message, AIMessage)
                and not message.tool_calls
                and bool(message.text)
            ):
                return message, messages
        raise AgentResponseError("The Agent returned no final AI response.")

    @staticmethod
    def _contains_image(message: AnyMessage) -> bool:
        if not isinstance(message.content, list):
            return False
        return any(
            isinstance(part, dict)
            and part.get("type") in {"image", "image_url"}
            for part in message.content
        )

    def _sanitize_historical_images(
        self,
        agent: AgentInvoker,
        config: dict[str, Any],
    ) -> None:
        try:
            snapshot = agent.get_state(config)
            values = getattr(snapshot, "values", None)
            messages = values.get("messages") if isinstance(values, dict) else None
            if not isinstance(messages, list):
                return
            replacements: list[HumanMessage] = []
            for message in messages:
                if not isinstance(message, HumanMessage):
                    continue
                if not self._contains_image(message):
                    continue
                text = message.text.strip() or "An ingredient image was provided."
                replacements.append(HumanMessage(
                    content=text,
                    id=message.id,
                    name=message.name,
                    additional_kwargs=message.additional_kwargs,
                    response_metadata=message.response_metadata,
                ))
            if replacements:
                agent.update_state(config, {"messages": replacements})
        except pymysql.MySQLError as exc:
            raise CheckpointerInvocationError(
                "Conversation checkpoint image sanitization failed."
            ) from exc
        except Exception as exc:
            raise AgentExecutionError(
                "Conversation checkpoint image sanitization failed."
            ) from exc

    @staticmethod
    def _history_message_to_langchain(
        message: ConversationHistoryMessage,
    ) -> AnyMessage:
        message_id = f"business-message-{message.message_id}"
        if message.role == "USER":
            return HumanMessage(content=message.content, id=message_id)
        return AIMessage(content=message.content, id=message_id)

    @staticmethod
    def _validate_recovery_history(
        history: Sequence[ConversationHistoryMessage],
    ) -> None:
        if len(history) > 500:
            raise InvalidAgentInputError(
                "recovery history must contain at most 500 messages."
            )
        total_characters = 0
        previous_id = -1
        for message in history:
            if message.message_id <= previous_id:
                raise InvalidAgentInputError(
                    "recovery history message IDs must be strictly increasing."
                )
            previous_id = message.message_id
            if message.role not in {"USER", "ASSISTANT"}:
                raise InvalidAgentInputError(
                    "recovery history contains an unsupported role."
                )
            if not message.content.strip():
                raise InvalidAgentInputError(
                    "recovery history must not contain blank content."
                )
            total_characters += len(message.content)
        if total_characters > 500_000:
            raise InvalidAgentInputError(
                "recovery history is too large."
            )

    @staticmethod
    def _thread_config(conversation_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": conversation_id}}

    @staticmethod
    def _require_image_support(model_id: ModelId) -> None:
        try:
            capabilities = MODEL_CAPABILITIES[ModelId(model_id)]
        except (KeyError, ValueError) as exc:
            raise UnsupportedModelError("The requested model is not supported.") from exc
        if not capabilities.supports_images:
            raise UnsupportedModelCapabilityError(
                "The selected model does not support image input."
            )

    @staticmethod
    def _has_tool_calls(message: AIMessage | AIMessageChunk) -> bool:
        return bool(
            message.tool_calls
            or getattr(message, "tool_call_chunks", None)
        )

    @staticmethod
    def _tool_call_names(
        message: AIMessage | AIMessageChunk,
    ) -> set[str]:
        names = {
            str(call.get("name"))
            for call in message.tool_calls
            if isinstance(call, dict) and call.get("name")
        }
        for call in getattr(message, "tool_call_chunks", None) or []:
            name = call.get("name") if isinstance(call, dict) else None
            if name:
                names.add(str(name))
        return names

    @classmethod
    def _tool_names_from_update(cls, update: dict[str, Any]) -> set[str]:
        tool_update = update.get("tools")
        if not isinstance(tool_update, dict):
            return set()
        messages = tool_update.get("messages")
        candidates = messages if isinstance(messages, list) else [messages]
        return {
            message.name
            for message in candidates
            if isinstance(message, ToolMessage) and message.name
        }

    @classmethod
    def _update_has_non_image_tool(cls, update: dict[str, Any]) -> bool:
        return bool(
            cls._tool_names_from_update(update) - {"generate_dish_image"}
        )

    @staticmethod
    def _tool_status_events(
        tool_names: set[str],
        emitted: set[str],
    ) -> list[AgentStreamEvent]:
        events: list[AgentStreamEvent] = []
        statuses = {
            "recipe_search": (
                "searching_recipe_kb",
                "Searching the recipe knowledge base...",
            ),
            "web_search": (
                "searching_web",
                "Searching the web for additional recipes...",
            ),
        }
        for name in ("recipe_search", "web_search"):
            if name not in tool_names or name in emitted:
                continue
            emitted.add(name)
            stage, message = statuses[name]
            events.append(AgentStreamEvent.status(stage, message))
        other_names = tool_names - {
            "recipe_search",
            "web_search",
            "generate_dish_image",
        }
        if other_names and "other_search" not in emitted:
            emitted.add("other_search")
            events.append(AgentStreamEvent.status(
                "using_tool",
                "Checking additional cooking information...",
            ))
        return events

    @staticmethod
    def _log_tool_sources(messages: Any) -> None:
        if not isinstance(messages, list):
            return
        names = {
            message.name
            for message in messages
            if isinstance(message, ToolMessage) and message.name
        }
        logger.info(
            "cooking_agent_tool_sources recipe_kb=%s tavily=%s both=%s "
            "tavily_fallback_triggered=%s",
            "recipe_search" in names,
            "web_search" in names,
            {"recipe_search", "web_search"}.issubset(names),
            {"recipe_search", "web_search"}.issubset(names),
        )

    @classmethod
    def _extract_generated_image_transfers(
        cls,
        messages: Any,
    ) -> list[GeneratedImageTransfer]:
        if not isinstance(messages, list):
            return []
        transfers: list[GeneratedImageTransfer] = []
        for message in messages:
            if not isinstance(message, ToolMessage):
                continue
            if message.name != "generate_dish_image":
                continue
            if not isinstance(message.content, str):
                continue
            try:
                data = json.loads(message.content)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or data.get("status") != "generated":
                continue
            transfer = cls._transfer_from_mapping(data)
            if transfer is not None:
                transfers.append(transfer)
        return transfers

    @staticmethod
    def _transfer_from_mapping(
        data: Mapping[str, Any],
    ) -> GeneratedImageTransfer | None:
        generation_id = data.get("generation_id")
        image_model = data.get("image_model")
        prompt = data.get("prompt")
        if not all(isinstance(value, str) and value for value in (
            generation_id,
            image_model,
            prompt,
        )):
            return None
        return GeneratedImageTransfer(
            generation_id=generation_id,
            image_model=image_model,
            prompt=prompt,
        )

    @staticmethod
    def _extract_ai_message_from_update(
        update: dict[str, Any],
    ) -> AIMessage | None:
        for node_update in update.values():
            if not isinstance(node_update, dict):
                continue
            messages = node_update.get("messages")
            if isinstance(messages, AIMessage):
                return messages
            if not isinstance(messages, list):
                continue
            for message in reversed(messages):
                if isinstance(message, AIMessage):
                    return message
        return None

    @staticmethod
    def _extract_final_ai_message(result: dict[str, Any]) -> AIMessage:
        messages = result.get("messages")
        if not isinstance(messages, list) or not messages:
            raise AgentResponseError("The Agent returned no message history.")

        final_message = messages[-1]
        if not isinstance(final_message, AIMessage) or final_message.tool_calls:
            raise AgentResponseError("The Agent returned no final AI response.")
        return final_message

    @staticmethod
    def _validate_conversation_id(conversation_id: str) -> None:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise InvalidAgentInputError("conversation_id must be a non-empty string.")
        if conversation_id != conversation_id.strip():
            raise InvalidAgentInputError(
                "conversation_id must not start or end with whitespace."
            )
        if len(conversation_id) > 150:
            raise InvalidAgentInputError(
                "conversation_id must contain at most 150 characters."
            )

    @staticmethod
    def _validate_message(message: str) -> None:
        if not isinstance(message, str) or not message.strip():
            raise InvalidAgentInputError("message must be a non-empty string.")

    @staticmethod
    def _validate_image_url(image_url: str) -> None:
        if not isinstance(image_url, str) or not image_url.strip():
            raise InvalidAgentInputError("image_url must be a non-empty string.")
        if len(image_url) > 2048 or any(ord(char) < 32 for char in image_url):
            raise InvalidAgentInputError("image_url is not a valid URL.")

        try:
            parsed = urlsplit(image_url)
        except ValueError as exc:
            raise InvalidAgentInputError("image_url is not a valid URL.") from exc

        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise InvalidAgentInputError(
                "image_url must be an absolute HTTPS URL."
            )
        if parsed.username is not None or parsed.password is not None:
            raise InvalidAgentInputError(
                "image_url must not contain embedded credentials."
            )

    @staticmethod
    def _run_context(user_memories: Sequence[str]) -> AgentRunContext:
        normalized = tuple(item.strip() for item in user_memories if item.strip())
        if len(normalized) > 24 or sum(len(item) for item in normalized) > 5_000:
            raise InvalidAgentInputError("user memory context is too large.")
        return AgentRunContext(user_memories=normalized)
