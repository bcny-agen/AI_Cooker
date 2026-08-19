"""API tests that never contact the real model, Tavily, or MySQL."""

from __future__ import annotations

import unittest
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.api.dependencies import (
    AgentRuntime,
    get_agent_runtime,
    require_internal_caller,
)
from app.main import create_app
from app.models.registry import ModelId, PublicModelInfo
from app.services.cooker_agent import (
    AgentStreamEvent,
    AgentExecutionError,
    CheckpointerInvocationError,
    InvalidAgentInputError,
    ModelInvocationError,
    SearchInvocationError,
    ConversationHistoryMessage,
    ThreadRecoveryRequiredError,
)
from app.services.forum_draft import GeneratedForumDraft
from app.api.schemas.memory import ExtractedMemory
from app.tools.dish_image import GeneratedImageBuffer


@asynccontextmanager
async def empty_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    yield


class FakeCookerAgentService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.text_calls: list[tuple[str, str]] = []
        self.image_calls: list[tuple[str, str, str]] = []
        self.model_calls: list[ModelId] = []
        self.user_memory_calls: list[tuple[str, ...]] = []

    def chat(
        self,
        conversation_id: str,
        message: str,
        model_id: ModelId,
        user_memories=(),
        continuation_expected=False,
    ) -> AIMessage:
        self.text_calls.append((conversation_id, message))
        self.model_calls.append(model_id)
        self.user_memory_calls.append(tuple(user_memories))
        if self.error is not None:
            raise self.error
        return AIMessage(content="text cooking answer")

    def chat_with_image(
        self,
        conversation_id: str,
        message: str,
        image_url: str,
        model_id: ModelId,
        user_memories=(),
        continuation_expected=False,
    ) -> AIMessage:
        self.image_calls.append((conversation_id, message, image_url))
        self.model_calls.append(model_id)
        self.user_memory_calls.append(tuple(user_memories))
        if self.error is not None:
            raise self.error
        return AIMessage(content="image cooking answer")

    def stream_chat(
        self,
        conversation_id: str,
        message: str,
        model_id: ModelId,
        user_memories=(),
        continuation_expected=False,
    ):
        self.text_calls.append((conversation_id, message))
        self.model_calls.append(model_id)
        self.user_memory_calls.append(tuple(user_memories))
        if self.error is not None:
            raise self.error
        yield AgentStreamEvent.status("thinking", "Thinking...")
        yield AgentStreamEvent.token("streamed ")
        yield AgentStreamEvent.token("answer")
        yield AgentStreamEvent.status("completed", "Complete.")
        yield AgentStreamEvent.done()

    def stream_chat_with_image(
        self,
        conversation_id: str,
        message: str,
        image_url: str,
        model_id: ModelId,
        user_memories=(),
        continuation_expected=False,
    ):
        self.image_calls.append((conversation_id, message, image_url))
        self.model_calls.append(model_id)
        self.user_memory_calls.append(tuple(user_memories))
        if self.error is not None:
            raise self.error
        yield AgentStreamEvent.status("analyzing_image", "Analyzing...")
        yield AgentStreamEvent.token("image answer")
        yield AgentStreamEvent.status("completed", "Complete.")
        yield AgentStreamEvent.done()

    def ensure_continuation_ready(self, conversation_id, model_id):
        if isinstance(self.error, ThreadRecoveryRequiredError):
            raise self.error

    def recover_thread(
        self,
        conversation_id: str,
        history: list[ConversationHistoryMessage],
        model_id: ModelId,
    ) -> None:
        self.recovery_call = (conversation_id, history, model_id)

    def available_models(self) -> list[PublicModelInfo]:
        return [
            PublicModelInfo(
                id=ModelId.STEP_FLASH_3_7,
                display_name="Step 3.7 Flash",
                supports_text=True,
                supports_tools=True,
                supports_streaming=True,
                supports_images=True,
                available=True,
            ),
            PublicModelInfo(
                id=ModelId.DEEPSEEK_V4_PRO,
                display_name="DeepSeek V4 Pro",
                supports_text=True,
                supports_tools=True,
                supports_streaming=True,
                supports_images=False,
                available=True,
            ),
        ]


class FakeForumDraftService:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    def generate(self, history, model_id, conversation_id=None):
        self.calls.append((history, model_id, conversation_id))
        if self.error is not None:
            raise self.error
        return GeneratedForumDraft(
            title="Tomato and Egg Stir-Fry",
            content="A grounded recipe recommendation.",
            dish_name="Tomato and Egg Stir-Fry",
        )


class FakeMemoryExtractionService:
    def __init__(self) -> None:
        self.calls = []

    def extract(self, *, current_user_message, context, model_id):
        self.calls.append((current_user_message, context, model_id))
        return [ExtractedMemory(
            action="UPSERT",
            memory_type="COOKING_PREFERENCE",
            key="oil",
            value="low",
            confidence=0.96,
            source_text="I prefer less oil",
        )]


class FakeConversationStateCleaner:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.error: Exception | None = None

    def delete(self, conversation_id: str) -> None:
        if self.error is not None:
            raise self.error
        self.deleted.append(conversation_id)


class ApiRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.service = FakeCookerAgentService()
        self.draft_service = FakeForumDraftService()
        self.memory_service = FakeMemoryExtractionService()
        self.state_cleaner = FakeConversationStateCleaner()
        self.generated_image_buffer = GeneratedImageBuffer()
        self.runtime = AgentRuntime(
            self.service,  # type: ignore[arg-type]
            self.executor,
            self.draft_service,  # type: ignore[arg-type]
            self.memory_service,  # type: ignore[arg-type]
            self.state_cleaner,  # type: ignore[arg-type]
            self.generated_image_buffer,
        )
        self.application = create_app(lifespan_context=empty_lifespan)
        self.application.dependency_overrides[get_agent_runtime] = (
            lambda: self.runtime
        )
        self.application.dependency_overrides[require_internal_caller] = (
            lambda: None
        )
        self.client_context = TestClient(self.application)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.executor.shutdown(wait=True, cancel_futures=True)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_model_list_endpoint_exposes_capabilities(self) -> None:
        response = self.client.get("/api/v1/models")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[1]["id"], "DEEPSEEK_V4_PRO")
        self.assertFalse(response.json()[1]["supports_images"])
        self.assertNotIn("base_url", response.text)

    def test_forum_draft_endpoint_uses_visible_history_and_selected_model(self) -> None:
        response = self.client.post(
            "/api/v1/forum/drafts",
            json={
                "messages": [
                    {"role": "USER", "content": "I have eggs."},
                    {"role": "ASSISTANT", "content": "Make an omelette."},
                ],
                "model_id": "DEEPSEEK_V4_PRO",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dish_name"], "Tomato and Egg Stir-Fry")
        history, model_id, conversation_id = self.draft_service.calls[0]
        self.assertEqual([item.role for item in history], ["USER", "ASSISTANT"])
        self.assertEqual(model_id, ModelId.DEEPSEEK_V4_PRO)
        self.assertIsNone(conversation_id)

    def test_forum_draft_endpoint_rejects_empty_history(self) -> None:
        response = self.client.post(
            "/api/v1/forum/drafts",
            json={"messages": [], "model_id": "STEP_FLASH_3_7"},
        )

        self.assertEqual(response.status_code, 400)

    def test_text_chat_endpoint(self) -> None:
        response = self.client.post(
            "/api/v1/chat",
            json={
                "conversation_id": "conversation-a",
                "message": "I have eggs.",
                "image_url": None,
                "user_memories": ["Cooking preference — oil: low"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "conversation_id": "conversation-a",
                "answer": "text cooking answer",
                "generated_images": [],
            },
        )
        self.assertEqual(
            self.service.text_calls,
            [("conversation-a", "I have eggs.")],
        )
        self.assertEqual(self.service.image_calls, [])
        self.assertEqual(self.service.model_calls, [ModelId.STEP_FLASH_3_7])
        self.assertEqual(
            self.service.user_memory_calls,
            [("Cooking preference — oil: low",)],
        )

    def test_internal_memory_extraction_endpoint_returns_structured_candidates(self) -> None:
        response = self.client.post(
            "/api/v1/memories/extract",
            json={
                "current_user_message": "I prefer less oil.",
                "context": [
                    {"role": "USER", "content": "I prefer less oil."},
                    {"role": "ASSISTANT", "content": "Understood."},
                ],
                "model_id": "STEP_FLASH_3_7",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["memories"][0]["key"], "oil")
        self.assertEqual(
            self.memory_service.calls[0][0],
            "I prefer less oil.",
        )

    def test_deepseek_streaming_path_uses_public_model_id(self) -> None:
        response = self.client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": "conversation-deepseek",
                "message": "I have tofu.",
                "image_url": None,
                "model_id": "DEEPSEEK_V4_PRO",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: done", response.text)
        self.assertEqual(self.service.model_calls, [ModelId.DEEPSEEK_V4_PRO])

    def test_image_chat_endpoint(self) -> None:
        response = self.client.post(
            "/api/v1/chat",
            json={
                "conversation_id": "conversation-image",
                "message": "What can I cook with these?",
                "image_url": "https://images.example/ingredients.jpg",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "conversation_id": "conversation-image",
                "answer": "image cooking answer",
                "generated_images": [],
            },
        )
        self.assertEqual(
            self.service.image_calls,
            [
                (
                    "conversation-image",
                    "What can I cook with these?",
                    "https://images.example/ingredients.jpg",
                )
            ],
        )
        self.assertEqual(self.service.text_calls, [])

    def test_streaming_endpoint_emits_structured_sse_events(self) -> None:
        response = self.client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": "conversation-stream",
                "message": "I have eggs.",
                "image_url": None,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"].split(";")[0],
            "text/event-stream",
        )
        self.assertIn("event: status", response.text)
        self.assertIn('"stage":"thinking"', response.text)
        self.assertIn('"type":"token","content":"streamed "', response.text)
        self.assertIn("event: done", response.text)
        self.assertEqual(
            self.service.text_calls,
            [("conversation-stream", "I have eggs.")],
        )

    def test_streaming_failure_is_a_safe_error_event(self) -> None:
        self.service.error = ModelInvocationError("secret upstream detail")

        response = self.client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": "conversation-stream-error",
                "message": "I have eggs.",
                "image_url": None,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: error", response.text)
        self.assertIn("An upstream AI service failed.", response.text)
        self.assertNotIn("secret upstream detail", response.text)

    def test_invalid_input_returns_400(self) -> None:
        invalid_requests = [
            {
                "conversation_id": "",
                "message": "hello",
                "image_url": None,
            },
            {
                "conversation_id": "conversation-a",
                "message": "",
                "image_url": None,
            },
            {
                "conversation_id": "conversation-a",
                "message": "hello",
                "image_url": "http://images.example/ingredients.jpg",
            },
        ]

        for request_body in invalid_requests:
            with self.subTest(request_body=request_body):
                response = self.client.post("/api/v1/chat", json=request_body)
                self.assertEqual(response.status_code, 400)

    def test_service_exceptions_are_mapped_to_http_statuses(self) -> None:
        cases = [
            (InvalidAgentInputError("invalid"), 400),
            (ModelInvocationError("model failed"), 502),
            (SearchInvocationError("search failed"), 502),
            (CheckpointerInvocationError("database failed"), 503),
            (AgentExecutionError("agent failed"), 500),
            (RuntimeError("unexpected"), 500),
        ]

        for error, expected_status in cases:
            with self.subTest(error=type(error).__name__):
                self.service.error = error
                response = self.client.post(
                    "/api/v1/chat",
                    json={
                        "conversation_id": "conversation-a",
                        "message": "hello",
                        "image_url": None,
                    },
                )
                self.assertEqual(response.status_code, expected_status)

    def test_existing_thread_recovery_is_requested_before_inference(self) -> None:
        self.service.error = ThreadRecoveryRequiredError("historical_image")

        response = self.client.post(
            "/api/v1/chat",
            json={
                "conversation_id": "legacy-conversation",
                "message": "continue",
                "continuation_expected": True,
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"],
            {
                "code": "thread_recovery_required",
                "reason": "historical_image",
            },
        )

    def test_stream_recovery_conflict_is_http_error_not_sse_error(self) -> None:
        self.service.error = ThreadRecoveryRequiredError("missing_checkpoint")

        response = self.client.post(
            "/api/v1/chat/stream",
            json={
                "conversation_id": "legacy-stream",
                "message": "continue",
                "continuation_expected": True,
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertNotIn("event: error", response.text)

    def test_internal_recovery_seeds_authorized_history_and_keeps_thread_id(self) -> None:
        response = self.client.post(
            "/api/v1/internal/chat/recover",
            json={
                "conversation_id": "legacy-conversation",
                "message": "continue",
                "model_id": "STEP_FLASH_3_7",
                "recovery_history": [
                    {
                        "message_id": 10,
                        "role": "USER",
                        "content": "I have eggs.",
                    },
                    {
                        "message_id": 11,
                        "role": "ASSISTANT",
                        "content": "Make an omelette.",
                    },
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["conversation_id"],
            "legacy-conversation",
        )
        conversation_id, history, model_id = self.service.recovery_call
        self.assertEqual(conversation_id, "legacy-conversation")
        self.assertEqual([item.message_id for item in history], [10, 11])
        self.assertEqual(model_id, ModelId.STEP_FLASH_3_7)

    def test_internal_recovery_rejects_non_loopback_clients(self) -> None:
        application = create_app(lifespan_context=empty_lifespan)
        application.dependency_overrides[get_agent_runtime] = lambda: self.runtime
        with TestClient(
            application,
            client=("192.0.2.10", 50000),
        ) as external_client:
            response = external_client.post(
                "/api/v1/internal/chat/recover",
                json={
                    "conversation_id": "legacy-conversation",
                    "message": "continue",
                    "recovery_history": [],
                },
            )

        self.assertEqual(response.status_code, 404)

    def test_internal_thread_deletion_is_scoped_and_returns_no_content(self) -> None:
        response = self.client.delete(
            "/api/v1/internal/threads/conversation-to-delete"
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(
            self.state_cleaner.deleted,
            ["conversation-to-delete"],
        )

    def test_internal_generated_image_transfer_is_loopback_scoped(self) -> None:
        payload = self.generated_image_buffer.put(
            b"\x89PNG\r\n\x1a\nimage-bytes",
            "image/png",
            "step-image-edit-2",
            "A food photo",
        )

        response = self.client.get(
            f"/api/v1/internal/generated-images/{payload.generation_id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, payload.data)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.headers["cache-control"], "no-store")


class ApiLifecycleTests(unittest.TestCase):
    def test_lifespan_starts_and_closes_agent_resources(self) -> None:
        settings = MagicMock(name="settings")
        checkpointer = MagicMock(name="checkpointer")
        agent = MagicMock(name="agent")
        service = MagicMock(name="service")
        draft_service = MagicMock(name="draft_service")
        models = {ModelId.STEP_FLASH_3_7: MagicMock(name="model")}

        with (
            patch("app.main.Settings.from_env", return_value=settings) as load_settings,
            patch("app.main.CheckpointerManager") as manager_class,
            patch("app.main.MySQLConversationSummaryStore") as summary_class,
            patch("app.main.create_chat_models", return_value=models) as create_models,
            patch("app.main.create_cooker_agents", return_value={ModelId.STEP_FLASH_3_7: agent}) as create_agents,
            patch("app.main.build_model_definitions", return_value={}) as definitions,
            patch("app.main.CookerAgentService", return_value=service) as service_class,
            patch("app.main.ForumDraftService", return_value=draft_service) as draft_service_class,
            patch("app.main.RecipeKBRuntime") as recipe_runtime_class,
        ):
            manager = manager_class.return_value
            summary_store = summary_class.return_value
            recipe_runtime = recipe_runtime_class.return_value
            manager.start.return_value = checkpointer
            application = create_app()

            with TestClient(application) as client:
                response = client.get("/api/v1/health")
                self.assertEqual(response.status_code, 200)

            load_settings.assert_called_once_with()
            manager_class.assert_called_once_with(settings)
            summary_class.assert_called_once_with(settings)
            manager.start.assert_called_once_with()
            summary_store.start.assert_called_once_with()
            create_agents.assert_called_once()
            create_agent_kwargs = create_agents.call_args.kwargs
            self.assertEqual(create_agent_kwargs["settings"], settings)
            self.assertEqual(create_agent_kwargs["checkpointer"], checkpointer)
            self.assertEqual(create_agent_kwargs["models"], models)
            self.assertEqual(create_agent_kwargs["summary_store"], summary_store)
            self.assertIsInstance(
                create_agent_kwargs["image_buffer"],
                GeneratedImageBuffer,
            )
            self.assertIs(
                create_agent_kwargs["recipe_kb_runtime"],
                recipe_runtime,
            )
            definitions.assert_called_once_with(settings)
            create_models.assert_called_once_with({})
            service_class.assert_called_once_with(
                {ModelId.STEP_FLASH_3_7: agent},
                {},
                summary_store=summary_store,
                recovery_recent_messages=(
                    settings.forum_draft_recent_messages
                ),
            )
            draft_service_class.assert_called_once_with(
                models,
                summary_store=summary_store,
                max_history_characters=(
                    settings.forum_draft_max_history_characters
                ),
                recent_messages=settings.forum_draft_recent_messages,
            )
            summary_store.close.assert_called_once_with()
            recipe_runtime.start.assert_called_once_with()
            recipe_runtime.close.assert_called_once_with()
            manager.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
