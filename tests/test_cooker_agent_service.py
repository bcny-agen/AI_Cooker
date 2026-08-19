"""Tests for the service boundary without network or database access."""

import unittest
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)

from app.services.cooker_agent import (
    AgentResponseError,
    CookerAgentService,
    ConversationHistoryMessage,
    InvalidAgentInputError,
    ThreadRecoveryRequiredError,
    UnsupportedModelCapabilityError,
)
from app.memory.conversation_summary import (
    ConversationSummary,
    RECOVERED_SUMMARY_REFERENCE,
)
from app.models.registry import ModelId


class FakeAgent:
    def __init__(
        self,
        *,
        emit_summary_status: bool = False,
        state_messages=None,
        emit_image_events: bool = False,
        tool_names: tuple[str, ...] = ("recipe_search",),
    ) -> None:
        self.calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.emit_summary_status = emit_summary_status
        self.state_messages = list(state_messages or [
            HumanMessage(content="existing question", id="existing-user"),
            AIMessage(content="existing answer", id="existing-assistant"),
        ])
        self.state_updates = []
        self.emit_image_events = emit_image_events
        self.tool_names = tool_names

    def invoke(
        self,
        input: dict[str, Any],
        config: dict[str, Any],
        *,
        context=None,
    ) -> dict[str, Any]:
        self.calls.append((input, config))
        self.last_context = context
        return {
            "messages": [
                *input["messages"],
                AIMessage(content="final cooking response"),
            ]
        }

    def stream(
        self,
        input: dict[str, Any],
        config: dict[str, Any],
        *,
        stream_mode: list[str],
        context=None,
    ):
        self.calls.append((input, config))
        self.last_context = context
        if self.emit_summary_status:
            yield (
                "messages",
                (
                    AIMessageChunk(content="private summary text"),
                    {
                        "langgraph_node": "model",
                        "tags": ["ai_cooker_context_summary"],
                    },
                ),
            )
            yield (
                "custom",
                {
                    "type": "context_compression",
                    "stage": "summarizing_context",
                },
            )
        for index, tool_name in enumerate(self.tool_names):
            message_id = f"tool-request-message-{index}"
            yield (
                "messages",
                (
                    AIMessageChunk(
                        id=message_id,
                        content="",
                        tool_call_chunks=[{
                            "name": tool_name,
                            "args": "{}",
                            "id": f"call-{index}",
                            "index": index,
                            "type": "tool_call_chunk",
                        }],
                    ),
                    {"langgraph_node": "model"},
                ),
            )
            yield (
                "updates",
                {
                    "model": {
                        "messages": [AIMessage(
                            id=message_id,
                            content="",
                            tool_calls=[{
                                "name": tool_name,
                                "args": {},
                                "id": f"call-{index}",
                                "type": "tool_call",
                            }],
                        )]
                    }
                },
            )
            yield (
                "updates",
                {
                    "tools": {
                        "messages": [ToolMessage(
                            content="tool result",
                            name=tool_name,
                            tool_call_id=f"call-{index}",
                        )]
                    }
                },
            )
        if self.emit_image_events:
            yield (
                "custom",
                {
                    "stage": "generating_image",
                    "message": "Generating dish image...",
                },
            )
            yield (
                "custom",
                {
                    "stage": "generated_image_ready",
                    "generation_id": "26806f88-d8fe-4de2-972a-c4482458f134",
                    "image_model": "step-image-edit-2",
                    "prompt": "A realistic food photo of tomato eggs",
                },
            )
        yield (
            "messages",
            (
                AIMessageChunk(id="final-message", content="Cook "),
                {"langgraph_node": "model"},
            ),
        )
        yield (
            "messages",
            (
                AIMessageChunk(
                    id="final-message",
                    content="soup.",
                    chunk_position="last",
                ),
                {"langgraph_node": "model"},
            ),
        )
        yield (
            "updates",
            {"model": {"messages": [AIMessage(
                id="final-message",
                content="Cook soup.",
            )]}} ,
        )
        self.state_messages.extend([
            input["messages"][0],
            AIMessage(id="final-message", content="Cook soup."),
        ])

    def get_state(self, config):
        return SimpleNamespace(values={"messages": list(self.state_messages)})

    def update_state(self, config, values, as_node=None):
        self.state_updates.append((config, values, as_node))
        messages = list(values.get("messages", []))
        if messages and isinstance(messages[0], RemoveMessage):
            self.state_messages = messages[1:]
        else:
            by_id = {message.id: message for message in self.state_messages}
            for message in messages:
                by_id[message.id] = message
            self.state_messages = list(by_id.values())
        return config


class FakeSummaryStore:
    def __init__(self, summary=None) -> None:
        self.summary = summary
        self.saved = []

    def load(self, conversation_id):
        return self.summary

    def save(self, summary):
        self.summary = summary
        self.saved.append(summary)


class ScriptedStreamingAgent(FakeAgent):
    def __init__(self, events, final_messages):
        super().__init__(state_messages=[])
        self.events = list(events)
        self.final_messages = list(final_messages)

    def stream(self, input, config, *, stream_mode, context=None):
        self.calls.append((input, config))
        self.last_context = context
        self.state_messages = [*input["messages"], *self.final_messages]
        yield from self.events


class CookerAgentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = FakeAgent()
        self.service = CookerAgentService(self.agent)

    def test_chat_uses_conversation_id_as_thread_id(self) -> None:
        response = self.service.chat("conversation-a", "我有鸡蛋。")

        self.assertEqual(response.content, "final cooking response")
        input, config = self.agent.calls[0]
        self.assertEqual(
            config,
            {"configurable": {"thread_id": "conversation-a"}},
        )
        self.assertIsInstance(input["messages"][0], HumanMessage)

    def test_chat_with_image_builds_multimodal_human_message(self) -> None:
        self.service.chat_with_image(
            "conversation-a",
            "这些食材能做什么？",
            "https://images.example/ingredients.jpg",
        )

        human_message = self.agent.calls[0][0]["messages"][0]
        self.assertEqual(
            human_message.content,
            [
                {"type": "text", "text": "这些食材能做什么？"},
                {
                    "type": "image",
                    "url": "https://images.example/ingredients.jpg",
                },
            ],
        )

    def test_user_memory_is_run_scoped_context_not_checkpoint_input(self) -> None:
        self.service.chat(
            "conversation-memory",
            "Recommend dinner",
            user_memories=["Dietary restriction — coriander: avoid"],
        )

        input, _config = self.agent.calls[0]
        self.assertEqual(len(input["messages"]), 1)
        self.assertEqual(
            self.agent.last_context.user_memories,
            ("Dietary restriction — coriander: avoid",),
        )

    def test_different_conversation_ids_remain_distinct(self) -> None:
        self.service.chat("conversation-a", "第一条消息")
        self.service.chat("conversation-b", "另一条消息")

        thread_ids = [
            config["configurable"]["thread_id"]
            for _, config in self.agent.calls
        ]
        self.assertEqual(thread_ids, ["conversation-a", "conversation-b"])

    def test_rejects_non_https_image_url(self) -> None:
        with self.assertRaisesRegex(InvalidAgentInputError, "HTTPS"):
            self.service.chat_with_image(
                "conversation-a",
                "看图",
                "http://images.example/ingredients.jpg",
            )

    def test_stream_uses_real_tool_and_model_events(self) -> None:
        events = list(self.service.stream_chat(
            "conversation-stream",
            "Find a soup recipe",
        ))

        self.assertEqual(
            [event.type for event in events],
            ["status", "status", "status", "token", "token", "status", "done"],
        )
        self.assertEqual(
            [event.stage for event in events if event.type == "status"],
            [
                "thinking",
                "searching_recipe_kb",
                "generating_answer",
                "completed",
            ],
        )
        self.assertEqual(
            "".join(event.content or "" for event in events),
            "Cook soup.",
        )
        _input, config = self.agent.calls[0]
        self.assertEqual(
            config,
            {"configurable": {"thread_id": "conversation-stream"}},
        )

    def test_intermediate_text_from_tool_request_fails_without_done(self) -> None:
        request = AIMessage(
            id="request",
            content="I will search first.",
            tool_calls=[{
                "name": "recipe_search", "args": {},
                "id": "call-1", "type": "tool_call",
            }],
        )
        final = AIMessage(id="final", content="Grounded final answer.")
        agent = ScriptedStreamingAgent([
            ("messages", (AIMessageChunk(id="request", content="I will search first."), {"langgraph_node": "model"})),
            ("messages", (AIMessageChunk(id="request", content="", tool_call_chunks=[{"name": "recipe_search", "args": "{}", "id": "call-1", "index": 0, "type": "tool_call_chunk"}]), {"langgraph_node": "model"})),
            ("updates", {"model": {"messages": [request]}}),
            ("updates", {"tools": {"messages": [ToolMessage(content="result", name="recipe_search", tool_call_id="call-1")]}}),
            ("messages", (AIMessageChunk(id="final", content="Grounded "), {"langgraph_node": "model"})),
            ("messages", (AIMessageChunk(id="final", content="final answer.", chunk_position="last"), {"langgraph_node": "model"})),
            ("updates", {"model": {"messages": [final]}}),
        ], [request, ToolMessage(content="result", name="recipe_search", tool_call_id="call-1"), final])

        events = []
        with self.assertRaises(AgentResponseError):
            for event in CookerAgentService(agent).stream_chat("tool-chain", "cook"):
                events.append(event)

        self.assertNotIn("done", [event.type for event in events])

    def test_real_tokens_arrive_before_the_final_update(self) -> None:
        final = AIMessage(id="final", content="Real streamed answer.")
        agent = ScriptedStreamingAgent([
            ("messages", (AIMessageChunk(id="final", content="Real "), {"langgraph_node": "model"})),
            ("messages", (AIMessageChunk(id="final", content="streamed answer.", chunk_position="last"), {"langgraph_node": "model"})),
            ("updates", {"model": {"messages": [final]}}),
        ], [final])
        stream = CookerAgentService(agent).stream_chat("real-stream", "cook")

        self.assertEqual(next(stream).type, "status")
        self.assertEqual(next(stream).stage, "generating_answer")
        self.assertEqual(next(stream).content, "Real ")
        remaining = list(stream)
        self.assertEqual("".join(event.content or "" for event in remaining), "streamed answer.")
        self.assertEqual(remaining[-1].type, "done")

    def test_recipe_to_tavily_multi_tool_chain_has_one_canonical_answer(self) -> None:
        final = AIMessage(id="final", content="Fallback-grounded final answer.")
        events = []
        state = []
        for index, name in enumerate(("recipe_search", "web_search")):
            request = AIMessage(id=f"request-{index}", content="", tool_calls=[{"name": name, "args": {}, "id": f"call-{index}", "type": "tool_call"}])
            events.extend([
                ("messages", (AIMessageChunk(id=request.id, content="", tool_call_chunks=[{"name": name, "args": "{}", "id": f"call-{index}", "index": 0, "type": "tool_call_chunk"}]), {"langgraph_node": "model"})),
                ("updates", {"model": {"messages": [request]}}),
                ("updates", {"tools": {"messages": [ToolMessage(content="result", name=name, tool_call_id=f"call-{index}")]}}),
            ])
            state.extend([request, ToolMessage(content="result", name=name, tool_call_id=f"call-{index}")])
        events.extend([
            ("messages", (AIMessageChunk(id="final", content=final.text, chunk_position="last"), {"langgraph_node": "model"})),
            ("updates", {"model": {"messages": [final]}}),
        ])
        agent = ScriptedStreamingAgent(events, [*state, final])

        output = list(CookerAgentService(agent).stream_chat("fallback-chain", "uncommon dish"))

        stages = [event.stage for event in output if event.type == "status"]
        self.assertLess(stages.index("searching_recipe_kb"), stages.index("searching_web"))
        self.assertEqual("".join(event.content or "" for event in output), final.text)
        self.assertEqual(sum(event.type == "done" for event in output), 1)

    def test_partial_stream_mismatch_never_emits_done(self) -> None:
        final = AIMessage(id="final", content="Canonical answer.")
        agent = ScriptedStreamingAgent([
            ("messages", (AIMessageChunk(id="final", content="Different answer.", chunk_position="last"), {"langgraph_node": "model"})),
            ("updates", {"model": {"messages": [final]}}),
        ], [final])
        emitted = []

        with self.assertRaises(AgentResponseError):
            for event in CookerAgentService(agent).stream_chat("mismatch", "cook"):
                emitted.append(event)

        self.assertNotIn("done", [event.type for event in emitted])

    def test_image_recipe_rag_stream_uses_final_text_not_tool_messages(self) -> None:
        final = AIMessage(id="final", content="The image-grounded recipe answer.")
        request = AIMessage(id="request", content="", tool_calls=[{"name": "recipe_search", "args": {}, "id": "call-image", "type": "tool_call"}])
        agent = ScriptedStreamingAgent([
            ("messages", (AIMessageChunk(id="request", content="", tool_call_chunks=[{"name": "recipe_search", "args": "{}", "id": "call-image", "index": 0, "type": "tool_call_chunk"}]), {"langgraph_node": "model"})),
            ("updates", {"model": {"messages": [request]}}),
            ("updates", {"tools": {"messages": [ToolMessage(content="private recipe tool result", name="recipe_search", tool_call_id="call-image")]}}),
            ("messages", (AIMessageChunk(id="final", content=final.text, chunk_position="last"), {"langgraph_node": "model"})),
            ("updates", {"model": {"messages": [final]}}),
        ], [request, ToolMessage(content="private recipe tool result", name="recipe_search", tool_call_id="call-image"), final])

        output = list(CookerAgentService(agent).stream_chat_with_image("image-rag", "what can I cook", "https://images.example/ingredients.jpg"))

        self.assertEqual("".join(event.content or "" for event in output), final.text)
        self.assertEqual(output[-1].type, "done")

    def test_image_recipe_then_generation_keeps_tools_out_of_final_text(self) -> None:
        final = AIMessage(id="final", content="Your grounded dish image is ready.")
        events = []
        state = []
        for index, name in enumerate(("recipe_search", "generate_dish_image")):
            request = AIMessage(
                id=f"request-{index}",
                content="",
                tool_calls=[{
                    "name": name, "args": {},
                    "id": f"call-{index}", "type": "tool_call",
                }],
            )
            tool = ToolMessage(
                content="private tool result",
                name=name,
                tool_call_id=f"call-{index}",
            )
            events.extend([
                ("messages", (AIMessageChunk(
                    id=request.id,
                    content="",
                    tool_call_chunks=[{
                        "name": name, "args": "{}",
                        "id": f"call-{index}", "index": 0,
                        "type": "tool_call_chunk",
                    }],
                ), {"langgraph_node": "model"})),
                ("updates", {"model": {"messages": [request]}}),
                ("updates", {"tools": {"messages": [tool]}}),
            ])
            state.extend([request, tool])
        events.extend([
            ("custom", {
                "stage": "generated_image_ready",
                "generation_id": "26806f88-d8fe-4de2-972a-c4482458f134",
                "image_model": "step-image-edit-2",
                "prompt": "A grounded dish photo",
            }),
            ("messages", (AIMessageChunk(
                id="final",
                content=final.text,
                chunk_position="last",
            ), {"langgraph_node": "model"})),
            ("updates", {"model": {"messages": [final]}}),
        ])
        agent = ScriptedStreamingAgent(events, [*state, final])

        output = list(CookerAgentService(agent).stream_chat_with_image(
            "image-generation-rag",
            "make a dish and image",
            "https://images.example/ingredients.jpg",
        ))

        self.assertEqual("".join(event.content or "" for event in output), final.text)
        self.assertEqual(sum(event.type == "generated_image" for event in output), 1)
        self.assertEqual(sum(event.type == "done" for event in output), 1)

    def test_streaming_emits_only_statuses_for_tools_that_run(self) -> None:
        recipe_events = list(CookerAgentService(
            FakeAgent(tool_names=("recipe_search",)),
        ).stream_chat("recipe-only", "recommend dinner"))
        recipe_stages = [
            event.stage for event in recipe_events if event.type == "status"
        ]
        self.assertIn("searching_recipe_kb", recipe_stages)
        self.assertNotIn("searching_web", recipe_stages)

        fallback_events = list(CookerAgentService(
            FakeAgent(tool_names=("recipe_search", "web_search")),
        ).stream_chat("fallback", "find a current viral recipe"))
        fallback_stages = [
            event.stage for event in fallback_events if event.type == "status"
        ]
        self.assertLess(
            fallback_stages.index("searching_recipe_kb"),
            fallback_stages.index("searching_web"),
        )

    def test_image_generation_tool_does_not_emit_search_status(self) -> None:
        events = list(CookerAgentService(
            FakeAgent(
                tool_names=("generate_dish_image",),
                emit_image_events=True,
            ),
        ).stream_chat("image-tool-only", "generate an image of the second dish"))
        stages = [event.stage for event in events if event.type == "status"]
        self.assertNotIn("searching_recipe_kb", stages)
        self.assertNotIn("searching_web", stages)
        self.assertIn("generating_image", stages)

    def test_image_stream_begins_with_real_image_analysis_state(self) -> None:
        first_event = next(self.service.stream_chat_with_image(
            "conversation-image-stream",
            "What is in this image?",
            "https://images.example/ingredients.jpg",
        ))

        self.assertEqual(first_event.type, "status")
        self.assertEqual(first_event.stage, "analyzing_image")

    def test_stream_emits_summarization_status_only_for_real_custom_event(self) -> None:
        service = CookerAgentService(FakeAgent(emit_summary_status=True))

        events = list(service.stream_chat(
            "conversation-summary",
            "Continue the recipe",
        ))

        statuses = [event.stage for event in events if event.type == "status"]
        self.assertIn("summarizing_context", statuses)
        self.assertEqual(statuses.count("summarizing_context"), 1)
        self.assertNotIn(
            "private summary text",
            "".join(event.content or "" for event in events),
        )

    def test_explicit_image_tool_events_are_forwarded_without_affecting_text(self) -> None:
        service = CookerAgentService(FakeAgent(emit_image_events=True))

        events = list(service.stream_chat(
            "image-generation-thread",
            "Generate an image of the tomato eggs dish",
        ))

        self.assertIn(
            "generating_image",
            [event.stage for event in events if event.type == "status"],
        )
        image_event = next(
            event for event in events if event.type == "generated_image"
        )
        self.assertEqual(image_event.image_model, "step-image-edit-2")
        self.assertEqual(
            "".join(event.content or "" for event in events),
            "Cook soup.",
        )

    def test_non_image_question_emits_no_image_generation_event(self) -> None:
        events = list(self.service.stream_chat(
            "normal-cooking-thread",
            "How much salt should I add?",
        ))

        self.assertNotIn(
            "generated_image",
            [event.type for event in events],
        )
        self.assertNotIn(
            "generating_image",
            [event.stage for event in events if event.type == "status"],
        )

    def test_deepseek_uses_its_agent_with_same_thread_id(self) -> None:
        step_agent = FakeAgent()
        deepseek_agent = FakeAgent()
        service = CookerAgentService({
            ModelId.STEP_FLASH_3_7: step_agent,
            ModelId.DEEPSEEK_V4_PRO: deepseek_agent,
        })

        events = list(service.stream_chat(
            "shared-conversation",
            "I have tofu.",
            ModelId.DEEPSEEK_V4_PRO,
        ))

        self.assertEqual(events[-1].type, "done")
        self.assertEqual(step_agent.calls, [])
        self.assertEqual(
            deepseek_agent.calls[0][1]["configurable"]["thread_id"],
            "shared-conversation",
        )

    def test_deepseek_rejects_image_before_agent_execution(self) -> None:
        deepseek_agent = FakeAgent()
        service = CookerAgentService({ModelId.DEEPSEEK_V4_PRO: deepseek_agent})

        with self.assertRaises(UnsupportedModelCapabilityError):
            service.chat_with_image(
                "conversation-image",
                "What is this?",
                "https://images.example/food.jpg",
                ModelId.DEEPSEEK_V4_PRO,
            )

        self.assertEqual(deepseek_agent.calls, [])

    def test_healthy_checkpoint_uses_normal_continuation(self) -> None:
        response = self.service.chat(
            "healthy-thread",
            "Continue please",
            continuation_expected=True,
        )

        self.assertEqual(response.text, "final cooking response")
        self.assertEqual(len(self.agent.calls), 1)
        self.assertEqual(self.agent.state_updates, [])

    def test_missing_checkpoint_requires_recovery_before_model_call(self) -> None:
        agent = FakeAgent(state_messages=[])
        agent.state_messages = []
        service = CookerAgentService(agent)

        with self.assertRaises(ThreadRecoveryRequiredError) as raised:
            service.chat(
                "legacy-thread",
                "Continue please",
                continuation_expected=True,
            )

        self.assertEqual(raised.exception.reason, "missing_checkpoint")
        self.assertEqual(agent.calls, [])

    def test_historical_image_checkpoint_requires_text_recovery(self) -> None:
        agent = FakeAgent(state_messages=[HumanMessage(
            id="old-image",
            content=[
                {"type": "text", "text": "What can I cook?"},
                {"type": "image", "url": "https://example/expired.jpg"},
            ],
        )])
        service = CookerAgentService(agent)

        with self.assertRaises(ThreadRecoveryRequiredError) as raised:
            service.ensure_continuation_ready(
                "image-thread",
                ModelId.STEP_FLASH_3_7,
            )

        self.assertEqual(raised.exception.reason, "historical_image")

    def test_recovery_replaces_state_without_duplicating_business_history(self) -> None:
        agent = FakeAgent(state_messages=[])
        agent.state_messages = []
        service = CookerAgentService(agent)
        history = [
            ConversationHistoryMessage(11, "USER", "I have tomatoes."),
            ConversationHistoryMessage(12, "ASSISTANT", "Make tomato eggs."),
        ]

        service.recover_thread("legacy-thread", history)

        _config, update, as_node = agent.state_updates[0]
        self.assertIsInstance(update["messages"][0], RemoveMessage)
        self.assertEqual(as_node, "__start__")
        self.assertEqual(
            [message.id for message in agent.state_messages],
            ["business-message-11", "business-message-12"],
        )
        service.chat(
            "legacy-thread",
            "How long should it cook?",
            continuation_expected=True,
        )
        self.assertEqual(len(agent.calls), 1)

    def test_recovery_rebases_summary_and_keeps_only_recent_messages(self) -> None:
        summary = ConversationSummary(
            conversation_id="summarized-thread",
            summary="User has eggs and chose tomato stir-fry.",
            summarized_through_message_id="old-checkpoint-message",
            summarized_message_count=18,
            approximate_tokens_before=1000,
            approximate_tokens_after=200,
        )
        store = FakeSummaryStore(summary)
        agent = FakeAgent(state_messages=[])
        agent.state_messages = []
        service = CookerAgentService(
            agent,
            summary_store=store,
            recovery_recent_messages=4,
        )
        history = [
            ConversationHistoryMessage(
                index,
                "USER" if index % 2 else "ASSISTANT",
                f"message {index}",
            )
            for index in range(1, 9)
        ]

        service.recover_thread("summarized-thread", history)

        self.assertEqual(len(agent.state_messages), 4)
        self.assertEqual(agent.state_messages[0].id, "business-message-5")
        self.assertEqual(store.saved[-1].summarized_message_count, 0)
        self.assertEqual(
            store.saved[-1].summarized_through_message_id,
            RECOVERED_SUMMARY_REFERENCE,
        )


if __name__ == "__main__":
    unittest.main()
