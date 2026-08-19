"""Tests for incremental, checkpoint-preserving active context compression."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.runtime import ExecutionInfo, Runtime

from app.memory.context_compression import (
    ContextCompressionError,
    ConversationContextMiddleware,
)
from app.memory.conversation_summary import (
    ConversationSummary,
    RECOVERED_SUMMARY_REFERENCE,
)
from app.models.registry import ModelContextPolicy, ModelId


class MemorySummaryStore:
    def __init__(self) -> None:
        self.items: dict[str, ConversationSummary] = {}
        self.saved: list[ConversationSummary] = []

    def load(self, conversation_id: str) -> ConversationSummary | None:
        return self.items.get(conversation_id)

    def save(self, summary: ConversationSummary) -> None:
        self.items[summary.conversation_id] = summary
        self.saved.append(summary)


class FakeSummaryModel:
    def __init__(self, outputs: list[str] | None = None) -> None:
        self.outputs = list(outputs or ["Grounded cooking summary."])
        self.calls: list[object] = []
        self.error: Exception | None = None

    def invoke(self, messages, config=None):
        self.calls.append(messages)
        self.last_config = config
        if self.error is not None:
            raise self.error
        return AIMessage(content=self.outputs.pop(0))


def count_test_tokens(messages) -> int:
    return sum(
        int(message.additional_kwargs.get("test_tokens", 1))
        for message in messages
    )


def human(index: int, text: str | None = None) -> HumanMessage:
    return HumanMessage(
        id=f"human-{index}",
        content=text or f"user detail {index}",
        additional_kwargs={"test_tokens": 10},
    )


def assistant(index: int, text: str | None = None) -> AIMessage:
    return AIMessage(
        id=f"assistant-{index}",
        content=text or f"assistant recipe {index}",
        additional_kwargs={"test_tokens": 10},
    )


class ContextCompressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemorySummaryStore()
        self.summary_model = FakeSummaryModel([
            "Summary v1: eggs, tomato, no coriander.",
            "Summary v2: eggs, tomato, no coriander; selected stir-fry.",
        ])
        self.events: list[dict[str, str]] = []
        self.handled_requests: list[ModelRequest] = []

    def middleware(
        self,
        model_id: ModelId = ModelId.STEP_FLASH_3_7,
        *,
        trigger: int = 50,
    ) -> ConversationContextMiddleware:
        return ConversationContextMiddleware(
            model_id=model_id,
            summary_model=self.summary_model,  # type: ignore[arg-type]
            store=self.store,
            policy=ModelContextPolicy(
                context_window_tokens=200,
                summary_trigger_tokens=trigger,
                keep_recent_tokens=25,
            ),
            max_summary_characters=1_000,
            token_counter=count_test_tokens,
        )

    def request(self, conversation_id: str, messages) -> ModelRequest:
        return ModelRequest(
            model=MagicMock(),
            messages=list(messages),
            system_message=SystemMessage(content="Cook safely."),
            runtime=Runtime(
                stream_writer=self.events.append,
                execution_info=ExecutionInfo(
                    checkpoint_id="checkpoint",
                    checkpoint_ns="",
                    task_id="task",
                    thread_id=conversation_id,
                ),
            ),
        )

    def handler(self, request: ModelRequest) -> ModelResponse:
        self.handled_requests.append(request)
        return ModelResponse(result=[AIMessage(content="answer")])

    def test_short_conversation_does_not_summarize_or_emit_status(self) -> None:
        messages = [human(1), assistant(1)]

        self.middleware().wrap_model_call(
            self.request("short", messages),
            self.handler,
        )

        self.assertEqual(self.summary_model.calls, [])
        self.assertEqual(self.store.saved, [])
        self.assertEqual(self.events, [])
        self.assertEqual(self.handled_requests[0].messages, messages)

    def test_threshold_summarizes_old_messages_and_retains_recent_turns(self) -> None:
        messages = [
            human(1, "eggs and tomatoes"),
            assistant(1, "recommend stir-fry"),
            human(2, "no coriander"),
            assistant(2, "adjusted recipe"),
            human(3, "less oil"),
            assistant(3, "use one teaspoon"),
            human(4, "what is the next step?"),
        ]

        self.middleware().wrap_model_call(
            self.request("long", messages),
            self.handler,
        )

        saved = self.store.items["long"]
        self.assertEqual(saved.summarized_message_count, 4)
        self.assertEqual(saved.summarized_through_message_id, "assistant-2")
        self.assertEqual(
            self.handled_requests[0].messages,
            messages[4:],
        )
        self.assertIn(
            "Summary v1",
            self.handled_requests[0].system_message.text,
        )
        self.assertEqual(
            [event["stage"] for event in self.events],
            ["summarizing_context"],
        )
        self.assertEqual(
            self.summary_model.last_config,
            {"tags": ["ai_cooker_context_summary"]},
        )

    def test_incremental_summary_does_not_resummarize_same_messages(self) -> None:
        initial = [
            human(1), assistant(1), human(2), assistant(2),
            human(3), assistant(3), human(4),
        ]
        middleware = self.middleware()
        middleware.wrap_model_call(self.request("incremental", initial), self.handler)
        first_count = self.store.items["incremental"].summarized_message_count

        expanded = [*initial, assistant(4), human(5)]
        middleware.wrap_model_call(self.request("incremental", expanded), self.handler)

        second = self.store.items["incremental"]
        self.assertGreater(second.summarized_message_count, first_count)
        second_prompt = self.summary_model.calls[1][1].text
        self.assertIn("Summary v1", second_prompt)
        self.assertNotIn("user detail 1", second_prompt)
        self.assertIn("user detail 3", second_prompt)

    def test_summary_failure_preserves_previous_summary_and_safely_falls_back(self) -> None:
        messages = [
            human(1), assistant(1), human(2), assistant(2),
            human(3), assistant(3), human(4),
        ]
        middleware = self.middleware()
        middleware.wrap_model_call(self.request("failure", messages), self.handler)
        previous = self.store.items["failure"]
        self.summary_model.error = RuntimeError("provider failed")

        expanded = [*messages, assistant(4), human(5)]
        middleware.wrap_model_call(self.request("failure", expanded), self.handler)

        self.assertEqual(self.store.items["failure"], previous)
        fallback = self.handled_requests[-1]
        self.assertIn(previous.summary, fallback.system_message.text)
        self.assertEqual(
            fallback.messages,
            expanded[previous.summarized_message_count:],
        )

    def test_step_and_deepseek_thresholds_are_independent(self) -> None:
        messages = [human(1), assistant(1), human(2), assistant(2), human(3)]
        step = self.middleware(ModelId.STEP_FLASH_3_7, trigger=40)
        deep = self.middleware(ModelId.DEEPSEEK_V4_PRO, trigger=100)

        step.wrap_model_call(self.request("step", messages), self.handler)
        deep.wrap_model_call(self.request("deep", messages), self.handler)

        self.assertIn("step", self.store.items)
        self.assertNotIn("deep", self.store.items)

    def test_model_switch_reuses_existing_conversation_summary(self) -> None:
        messages = [
            human(1), assistant(1), human(2), assistant(2),
            human(3), assistant(3), human(4),
        ]
        self.middleware().wrap_model_call(
            self.request("switch", messages),
            self.handler,
        )
        stored = self.store.items["switch"]
        deep = self.middleware(ModelId.DEEPSEEK_V4_PRO, trigger=100)

        deep.wrap_model_call(self.request("switch", messages), self.handler)

        self.assertEqual(self.store.items["switch"], stored)
        self.assertIn(stored.summary, self.handled_requests[-1].system_message.text)

    def test_recovered_summary_is_reused_with_only_reseeded_recent_messages(self) -> None:
        self.store.items["recovered"] = ConversationSummary(
            conversation_id="recovered",
            summary="Earlier context: eggs, tomato, and no coriander.",
            summarized_through_message_id=RECOVERED_SUMMARY_REFERENCE,
            summarized_message_count=0,
            approximate_tokens_before=1_000,
            approximate_tokens_after=120,
        )
        recent = [human(8), assistant(8), human(9)]

        self.middleware(trigger=100).wrap_model_call(
            self.request("recovered", recent),
            self.handler,
        )

        handled = self.handled_requests[-1]
        self.assertEqual(handled.messages, recent)
        self.assertIn("Earlier context", handled.system_message.text)
        self.assertEqual(self.summary_model.calls, [])

    def test_separate_conversations_never_share_summaries(self) -> None:
        messages = [
            human(1), assistant(1), human(2), assistant(2),
            human(3), assistant(3), human(4),
        ]
        middleware = self.middleware()
        middleware.wrap_model_call(self.request("one", messages), self.handler)
        middleware.wrap_model_call(self.request("two", messages), self.handler)

        self.assertEqual(set(self.store.items), {"one", "two"})
        self.assertNotEqual(
            self.store.items["one"].conversation_id,
            self.store.items["two"].conversation_id,
        )

    def test_never_sends_context_known_to_exceed_safe_input_limit(self) -> None:
        middleware = ConversationContextMiddleware(
            model_id=ModelId.STEP_FLASH_3_7,
            summary_model=self.summary_model,  # type: ignore[arg-type]
            store=self.store,
            policy=ModelContextPolicy(
                context_window_tokens=200,
                summary_trigger_tokens=180,
                keep_recent_tokens=25,
            ),
            max_summary_characters=1_000,
            token_counter=count_test_tokens,
        )
        messages = [human(index) for index in range(17)]

        with self.assertRaises(ContextCompressionError):
            middleware.wrap_model_call(
                self.request("unsafe", messages),
                self.handler,
            )

        self.assertEqual(self.handled_requests, [])


if __name__ == "__main__":
    unittest.main()
