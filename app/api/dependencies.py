"""Runtime dependencies shared by the API routes."""

from __future__ import annotations

import asyncio
import ipaddress
import threading
from collections.abc import AsyncIterator, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TypeVar

from fastapi import HTTPException, Request, status
from langchain_core.messages import AIMessage

from app.models.registry import ModelId, PublicModelInfo
from app.api.schemas.memory import ExtractedMemory, MemoryContextMessage
from app.services.cooker_agent import AgentStreamEvent, CookerAgentService
from app.services.cooker_agent import ConversationHistoryMessage
from app.services.forum_draft import (
    DraftHistoryMessage,
    ForumDraftService,
    GeneratedForumDraft,
)
from app.services.user_memory_extraction import UserMemoryExtractionService
from app.memory.conversation_state import ConversationStateCleaner
from app.tools.dish_image import GeneratedImageBuffer, GeneratedImagePayload

ResultT = TypeVar("ResultT")


class AgentRuntime:
    """Run the synchronous Agent on its single, dedicated worker thread."""

    def __init__(
        self,
        service: CookerAgentService,
        executor: ThreadPoolExecutor,
        forum_draft_service: ForumDraftService | None = None,
        memory_extraction_service: UserMemoryExtractionService | None = None,
        conversation_state_cleaner: ConversationStateCleaner | None = None,
        generated_image_buffer: GeneratedImageBuffer | None = None,
    ) -> None:
        self._service = service
        self._executor = executor
        self._forum_draft_service = forum_draft_service
        self._memory_extraction_service = memory_extraction_service
        self._conversation_state_cleaner = conversation_state_cleaner
        self._generated_image_buffer = generated_image_buffer

    async def run(self, operation: Callable[[], ResultT]) -> ResultT:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, operation)

    async def chat(
        self,
        conversation_id: str,
        message: str,
        image_url: str | None,
        model_id: ModelId,
        user_memories: Sequence[str] = (),
        continuation_expected: bool = False,
    ) -> AIMessage:
        if image_url is not None:
            operation = partial(
                self._service.chat_with_image,
                conversation_id,
                message,
                image_url,
                model_id,
                user_memories,
                continuation_expected,
            )
        else:
            operation = partial(
                self._service.chat,
                conversation_id,
                message,
                model_id,
                user_memories,
                continuation_expected,
            )

        return await self.run(operation)

    async def stream_chat(
        self,
        conversation_id: str,
        message: str,
        image_url: str | None,
        model_id: ModelId,
        user_memories: Sequence[str] = (),
        continuation_expected: bool = False,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Bridge the synchronous Agent iterator to an async response safely."""

        loop = asyncio.get_running_loop()
        events: asyncio.Queue[AgentStreamEvent | BaseException | object] = (
            asyncio.Queue()
        )
        finished = object()
        stop_requested = threading.Event()

        def publish(item: AgentStreamEvent | BaseException | object) -> None:
            loop.call_soon_threadsafe(events.put_nowait, item)

        def produce() -> None:
            try:
                if image_url is not None:
                    stream = self._service.stream_chat_with_image(
                        conversation_id,
                        message,
                        image_url,
                        model_id,
                        user_memories,
                        continuation_expected,
                    )
                else:
                    stream = self._service.stream_chat(
                        conversation_id,
                        message,
                        model_id,
                        user_memories,
                        continuation_expected,
                    )

                for event in stream:
                    if stop_requested.is_set():
                        break
                    publish(event)
            except BaseException as exc:
                publish(exc)
            finally:
                publish(finished)

        producer = loop.run_in_executor(self._executor, produce)
        try:
            while True:
                item = await events.get()
                if item is finished:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            stop_requested.set()
            if producer.done():
                await producer

    async def ensure_continuation_ready(
        self,
        conversation_id: str,
        model_id: ModelId,
    ) -> None:
        await self.run(partial(
            self._service.ensure_continuation_ready,
            conversation_id,
            model_id,
        ))

    async def recover_thread(
        self,
        conversation_id: str,
        history: Sequence[ConversationHistoryMessage],
        model_id: ModelId,
    ) -> None:
        await self.run(partial(
            self._service.recover_thread,
            conversation_id,
            history,
            model_id,
        ))

    async def delete_conversation_state(self, conversation_id: str) -> None:
        if self._conversation_state_cleaner is None:
            raise RuntimeError("Conversation state cleanup is unavailable.")
        await self.run(partial(
            self._conversation_state_cleaner.delete,
            conversation_id,
        ))

    def available_models(self) -> list[PublicModelInfo]:
        return self._service.available_models()

    def get_generated_image(
        self,
        generation_id: str,
    ) -> GeneratedImagePayload | None:
        if self._generated_image_buffer is None:
            return None
        return self._generated_image_buffer.get(generation_id)

    async def extract_user_memories(
        self,
        *,
        current_user_message: str,
        context: Sequence[MemoryContextMessage],
        model_id: ModelId,
    ) -> list[ExtractedMemory]:
        if self._memory_extraction_service is None:
            raise RuntimeError("User-memory extraction is unavailable.")
        return await self.run(partial(
            self._memory_extraction_service.extract,
            current_user_message=current_user_message,
            context=context,
            model_id=model_id,
        ))

    async def generate_forum_draft(
        self,
        history: Sequence[DraftHistoryMessage],
        model_id: ModelId,
        conversation_id: str | None = None,
    ) -> GeneratedForumDraft:
        if self._forum_draft_service is None:
            raise RuntimeError("Forum draft generation is unavailable.")
        return await self.run(partial(
            self._forum_draft_service.generate,
            history,
            model_id,
            conversation_id,
        ))


def get_agent_runtime(request: Request) -> AgentRuntime:
    """Return the initialized Agent runtime or report temporary unavailability."""

    runtime = getattr(request.app.state, "agent_runtime", None)
    if not isinstance(runtime, AgentRuntime):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI Agent service is unavailable.",
        )
    return runtime


def require_internal_caller(request: Request) -> None:
    """Restrict Java-owned recovery history to same-host service calls."""

    client = request.client
    try:
        address = ipaddress.ip_address(client.host if client else "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc
    if not address.is_loopback:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
