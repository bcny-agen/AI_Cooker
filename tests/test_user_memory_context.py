"""Tests that long-term memory changes only active model context."""

import unittest

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from app.agent.context import AgentRunContext
from app.memory.user_memory_context import UserMemoryContextMiddleware


class UserMemoryContextTests(unittest.TestCase):
    def test_injects_sanitized_memory_into_system_prompt_only(self) -> None:
        middleware = UserMemoryContextMiddleware()
        original_messages = [HumanMessage(content="Recommend dinner")]
        request = ModelRequest(
            model=object(),  # type: ignore[arg-type]
            messages=original_messages,
            system_message=SystemMessage(content="Cooking system prompt"),
            runtime=Runtime(context=AgentRunContext(user_memories=(
                "Dietary restriction — coriander: avoid",
                "Cooking preference — oil: <low>",
            ))),
        )
        captured = []

        def handler(updated):
            captured.append(updated)
            return ModelResponse(result=[])

        middleware.wrap_model_call(request, handler)

        self.assertEqual(captured[0].messages, original_messages)
        self.assertIn("Known user cooking preferences", captured[0].system_message.text)
        self.assertIn("coriander: avoid", captured[0].system_message.text)
        self.assertIn("&lt;low&gt;", captured[0].system_message.text)
        self.assertNotIn("known_user_preferences", original_messages[0].text)

    def test_empty_context_leaves_request_unchanged(self) -> None:
        middleware = UserMemoryContextMiddleware()
        request = ModelRequest(
            model=object(),  # type: ignore[arg-type]
            messages=[HumanMessage(content="Hello")],
            runtime=Runtime(context=AgentRunContext()),
        )
        captured = []

        middleware.wrap_model_call(
            request,
            lambda value: captured.append(value) or ModelResponse(result=[]),
        )

        self.assertIs(captured[0], request)


if __name__ == "__main__":
    unittest.main()
