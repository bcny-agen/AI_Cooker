"""Tests for checkpoint-free, structured forum draft generation."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from app.models.registry import ModelId
from app.memory.conversation_summary import ConversationSummary
from app.services.forum_draft import (
    DraftHistoryMessage,
    ForumDraftOutputError,
    ForumDraftService,
    GeneratedForumDraft,
    InvalidForumDraftInputError,
    select_history,
)


class FakeStructuredRunnable:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[object] = []

    def invoke(self, input):
        self.calls.append(input)
        if self.error is not None:
            raise self.error
        return self.result


class FakeDraftModel:
    def __init__(self, structured_result, fallback_text: str = "") -> None:
        self.structured = FakeStructuredRunnable(structured_result)
        self.fallback_text = fallback_text
        self.fallback_calls: list[object] = []

    def with_structured_output(self, *_args, **_kwargs):
        return self.structured

    def invoke(self, input):
        self.fallback_calls.append(input)
        return AIMessage(content=self.fallback_text)


class FakeSummaryStore:
    def __init__(self, summary: ConversationSummary | None) -> None:
        self.summary = summary
        self.calls: list[str] = []

    def load(self, conversation_id: str) -> ConversationSummary | None:
        self.calls.append(conversation_id)
        return self.summary

    def save(self, summary: ConversationSummary) -> None:
        self.summary = summary


class ForumDraftServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.history = [
            DraftHistoryMessage("USER", "I have eggs and tomatoes."),
            DraftHistoryMessage(
                "ASSISTANT",
                "Try tomato and egg stir-fry with scallions.",
            ),
        ]

    def test_step_and_deepseek_use_their_registered_model(self) -> None:
        step = FakeDraftModel({
            "parsed": {
                "title": "Tomato and Egg Stir-Fry",
                "content": "A quick dish recommended for eggs and tomatoes.",
                "dish_name": "Tomato and Egg Stir-Fry",
            }
        })
        deepseek = FakeDraftModel({
            "parsed": {
                "title": "DeepSeek Tomato Dish",
                "content": "A practical tomato and egg recommendation.",
                "dish_name": "Tomato and Egg Stir-Fry",
            }
        })
        service = ForumDraftService({
            ModelId.STEP_FLASH_3_7: step,  # type: ignore[dict-item]
            ModelId.DEEPSEEK_V4_PRO: deepseek,  # type: ignore[dict-item]
        })

        step_result = service.generate(self.history, ModelId.STEP_FLASH_3_7)
        deepseek_result = service.generate(
            self.history,
            ModelId.DEEPSEEK_V4_PRO,
        )

        self.assertEqual(step_result.title, "Tomato and Egg Stir-Fry")
        self.assertEqual(deepseek_result.title, "DeepSeek Tomato Dish")
        self.assertEqual(len(step.structured.calls), 1)
        self.assertEqual(len(deepseek.structured.calls), 1)
        self.assertEqual(step.fallback_calls, [])

    def test_validated_json_fallback_handles_incompatible_native_output(self) -> None:
        model = FakeDraftModel(
            {"parsed": None, "parsing_error": ValueError("bad tool output")},
            """```json
            {"title":"Soup","content":"A grounded soup recommendation.","dish_name":"Soup"}
            ```""",
        )
        service = ForumDraftService({
            ModelId.STEP_FLASH_3_7: model,  # type: ignore[dict-item]
        })

        result = service.generate(self.history, ModelId.STEP_FLASH_3_7)

        self.assertEqual(result, GeneratedForumDraft(
            title="Soup",
            content="A grounded soup recommendation.",
            dish_name="Soup",
        ))
        self.assertEqual(len(model.fallback_calls), 1)

    def test_rejects_malformed_structured_and_fallback_output(self) -> None:
        model = FakeDraftModel({"parsed": None}, '{"title":"missing fields"}')
        service = ForumDraftService({
            ModelId.STEP_FLASH_3_7: model,  # type: ignore[dict-item]
        })

        with self.assertRaises(ForumDraftOutputError):
            service.generate(self.history, ModelId.STEP_FLASH_3_7)

    def test_rejects_empty_or_invalid_history(self) -> None:
        model = FakeDraftModel({"parsed": None})
        service = ForumDraftService({
            ModelId.STEP_FLASH_3_7: model,  # type: ignore[dict-item]
        })

        with self.assertRaises(InvalidForumDraftInputError):
            service.generate([], ModelId.STEP_FLASH_3_7)
        with self.assertRaises(InvalidForumDraftInputError):
            service.generate(
                [DraftHistoryMessage("USER", "   ")],
                ModelId.STEP_FLASH_3_7,
            )

    def test_history_boundary_preserves_first_user_request_and_recent_turns(self) -> None:
        history = [
            DraftHistoryMessage("USER", "First request: make a tomato dish."),
            *[
                DraftHistoryMessage(
                    "ASSISTANT" if index % 2 else "USER",
                    f"Middle message {index} " + ("x" * 80),
                )
                for index in range(10)
            ],
            DraftHistoryMessage("ASSISTANT", "Recent cooking tip."),
        ]

        selected = select_history(
            history,
            max_characters=240,
            recent_messages=2,
        )

        self.assertEqual(selected[0].content, history[0].content)
        self.assertIn("Recent cooking tip.", [item.content for item in selected])
        self.assertLessEqual(sum(len(item.content) for item in selected), 240)

    def test_history_boundary_recognizes_older_chinese_recipe_context(self) -> None:
        history = [
            DraftHistoryMessage("USER", "最初的问题"),
            DraftHistoryMessage("ASSISTANT", "关键菜谱步骤：先炒鸡蛋，再加入番茄。"),
            DraftHistoryMessage("USER", "无关内容" + ("甲" * 120)),
            DraftHistoryMessage("ASSISTANT", "最近回复"),
        ]

        selected = select_history(
            history,
            max_characters=50,
            recent_messages=1,
        )

        self.assertIn(history[1].content, [item.content for item in selected])

    def test_long_forum_draft_uses_summary_plus_selected_business_history(self) -> None:
        model = FakeDraftModel({
            "parsed": {
                "title": "Low-oil Tomato Eggs",
                "content": "A grounded draft.",
                "dish_name": "Tomato Eggs",
            }
        })
        summary_store = FakeSummaryStore(ConversationSummary(
            conversation_id="conversation-long",
            summary="The user selected tomato eggs and requested less oil.",
            summarized_through_message_id="message-10",
            summarized_message_count=10,
            approximate_tokens_before=500,
            approximate_tokens_after=100,
        ))
        service = ForumDraftService(
            {ModelId.STEP_FLASH_3_7: model},  # type: ignore[dict-item]
            summary_store=summary_store,
            max_history_characters=1_000,
            recent_messages=2,
        )
        long_history = [
            DraftHistoryMessage("USER", "eggs and tomatoes " + ("x" * 600)),
            DraftHistoryMessage("ASSISTANT", "recipe steps " + ("y" * 600)),
            DraftHistoryMessage("USER", "Please use less oil."),
        ]

        service.generate(
            long_history,
            ModelId.STEP_FLASH_3_7,
            "conversation-long",
        )

        prompt = model.structured.calls[0][1].text
        self.assertIn("<conversation_summary>", prompt)
        self.assertIn("requested less oil", prompt)
        self.assertIn("Please use less oil.", prompt)
        self.assertEqual(summary_store.calls, ["conversation-long"])

    def test_short_forum_draft_behavior_does_not_require_summary(self) -> None:
        model = FakeDraftModel({
            "parsed": {
                "title": "Dish",
                "content": "Grounded content.",
                "dish_name": "Dish",
            }
        })
        summary_store = FakeSummaryStore(None)
        service = ForumDraftService(
            {ModelId.STEP_FLASH_3_7: model},  # type: ignore[dict-item]
            summary_store=summary_store,
        )

        service.generate(
            self.history,
            ModelId.STEP_FLASH_3_7,
            "conversation-short",
        )

        self.assertEqual(summary_store.calls, [])
        self.assertNotIn(
            "<conversation_summary>",
            model.structured.calls[0][1].text,
        )

    def test_generation_never_touches_agent_or_checkpointer_objects(self) -> None:
        model = FakeDraftModel({
            "parsed": {
                "title": "Dish",
                "content": "Grounded content.",
                "dish_name": "Dish",
            }
        })
        agent = MagicMock()
        checkpointer = MagicMock()
        service = ForumDraftService({
            ModelId.STEP_FLASH_3_7: model,  # type: ignore[dict-item]
        })

        service.generate(self.history, ModelId.STEP_FLASH_3_7)

        agent.assert_not_called()
        checkpointer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
