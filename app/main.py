"""FastAPI application and lifecycle for the AI_Cooker service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import partial
from typing import TypeVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent.factory import create_cooker_agents
from app.api.dependencies import AgentRuntime
from app.api.routes.chat import router as chat_router
from app.api.routes.health import router as health_router
from app.api.routes.models import router as models_router
from app.api.routes.forum import router as forum_router
from app.api.routes.memory import router as memory_router
from app.config.settings import Settings
from app.memory.checkpointer import CheckpointerManager
from app.memory.conversation_summary import MySQLConversationSummaryStore
from app.services.cooker_agent import CookerAgentService
from app.models.registry import build_model_definitions
from app.models.chat_model import create_chat_models
from app.services.forum_draft import ForumDraftService
from app.services.user_memory_extraction import UserMemoryExtractionService
from app.memory.conversation_state import ConversationStateCleaner
from app.api.routes.conversation_state import router as conversation_state_router
from app.api.routes.generated_images import router as generated_images_router
from app.tools.dish_image import GeneratedImageBuffer
from app.tools.recipe_search import RecipeKBRuntime

LifespanContext = Callable[[FastAPI], AbstractAsyncContextManager[None]]
ResultT = TypeVar("ResultT")


async def _run_on_agent_thread(
    executor: ThreadPoolExecutor,
    operation: Callable[[], ResultT],
) -> ResultT:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, operation)


def _start_agent_service(
    settings: Settings,
    checkpointer_manager: CheckpointerManager,
    summary_store: MySQLConversationSummaryStore,
    recipe_kb_runtime: RecipeKBRuntime,
) -> tuple[
    CookerAgentService,
    ForumDraftService,
    UserMemoryExtractionService,
    GeneratedImageBuffer,
]:
    """Create every blocking Agent resource on the dedicated Agent thread."""

    checkpointer = checkpointer_manager.start()
    summary_store.start()
    recipe_kb_runtime.start()
    definitions = build_model_definitions(settings)
    models = create_chat_models(definitions)
    generated_image_buffer = GeneratedImageBuffer()
    agents = create_cooker_agents(
        settings=settings,
        checkpointer=checkpointer,
        models=models,
        summary_store=summary_store,
        image_buffer=generated_image_buffer,
        recipe_kb_runtime=recipe_kb_runtime,
    )
    return (
        CookerAgentService(
            agents,
            definitions,
            summary_store=summary_store,
            recovery_recent_messages=settings.forum_draft_recent_messages,
        ),
        ForumDraftService(
            models,
            summary_store=summary_store,
            max_history_characters=(
                settings.forum_draft_max_history_characters
            ),
            recent_messages=settings.forum_draft_recent_messages,
        ),
        UserMemoryExtractionService(models),
        generated_image_buffer,
    )


@asynccontextmanager
async def application_lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Start and stop the singleton Agent resources with the ASGI process."""

    settings = Settings.from_env()
    checkpointer_manager = CheckpointerManager(settings)
    summary_store = MySQLConversationSummaryStore(settings)
    recipe_kb_runtime = RecipeKBRuntime(settings)
    executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="ai-cooker-agent",
    )

    try:
        (
            service,
            forum_draft_service,
            memory_extraction_service,
            generated_image_buffer,
        ) = await _run_on_agent_thread(
            executor,
            partial(
                _start_agent_service,
                settings,
                checkpointer_manager,
                summary_store,
                recipe_kb_runtime,
            ),
        )
        application.state.agent_runtime = AgentRuntime(
            service,
            executor,
            forum_draft_service,
            memory_extraction_service,
            ConversationStateCleaner(checkpointer_manager.checkpointer, summary_store),
            generated_image_buffer,
        )
        yield
    finally:
        application.state.agent_runtime = None
        try:
            await _run_on_agent_thread(executor, recipe_kb_runtime.close)
        finally:
            try:
                await _run_on_agent_thread(executor, summary_store.close)
            finally:
                try:
                    await _run_on_agent_thread(
                        executor,
                        checkpointer_manager.close,
                    )
                finally:
                    executor.shutdown(wait=True, cancel_futures=True)


def create_app(
    *,
    lifespan_context: LifespanContext = application_lifespan,
) -> FastAPI:
    """Build the lightweight ASGI app without opening external resources."""

    application = FastAPI(
        title="AI_Cooker AI Service",
        version="0.1.0",
        lifespan=lifespan_context,
    )
    application.include_router(health_router)
    application.include_router(models_router)
    application.include_router(chat_router)
    application.include_router(forum_router)
    application.include_router(memory_router)
    application.include_router(conversation_state_router)
    application.include_router(generated_images_router)

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request,
        _exception: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "Request validation failed."},
        )

    return application


app = create_app()
