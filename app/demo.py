"""Command-line demonstration of the reusable AI_Cooker Agent core."""

from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage

from app.agent.factory import create_cooker_agent
from app.config.settings import Settings, SettingsError
from app.memory.checkpointer import CheckpointerError, CheckpointerManager
from app.models.chat_model import ModelConfigurationError
from app.services.cooker_agent import CookerAgentError, CookerAgentService
from app.tools.recipe_search import RecipeSearchConfigurationError
from app.tools.web_search import WebSearchConfigurationError


def _print_response(label: str, response: AIMessage) -> None:
    print(f"\n{label}")
    print(response.text)


def main() -> int:
    """Run two conversations and close the checkpointer cleanly."""

    try:
        settings = Settings.from_env()
        if not settings.demo_image_url:
            raise SettingsError(
                "DEMO_IMAGE_URL is required to run the multimodal demonstration."
            )

        checkpointer_manager = CheckpointerManager(settings)
        with checkpointer_manager:
            agent = create_cooker_agent(
                settings=settings,
                checkpointer=checkpointer_manager.checkpointer,
            )
            service = CookerAgentService(agent)

            conversation_a = str(uuid.uuid4())
            print(f"Conversation A ID: {conversation_a}")

            image_response = service.chat_with_image(
                conversation_id=conversation_a,
                message="帮我看看这些食材能做什么。",
                image_url=settings.demo_image_url,
            )
            _print_response("Conversation A — image question", image_response)

            follow_up_response = service.chat(
                conversation_id=conversation_a,
                message="我喜欢第三道菜，你能详细讲一讲它的做法吗？",
            )
            _print_response(
                "Conversation A — follow-up with the same ID",
                follow_up_response,
            )

            conversation_b = str(uuid.uuid4())
            print(f"\nConversation B ID: {conversation_b}")
            second_conversation_response = service.chat(
                conversation_id=conversation_b,
                message="我有鸡蛋和西红柿，请推荐适合的菜谱。",
            )
            _print_response(
                "Conversation B — independent conversation",
                second_conversation_response,
            )

    except (
        SettingsError,
        CheckpointerError,
        ModelConfigurationError,
        RecipeSearchConfigurationError,
        WebSearchConfigurationError,
        CookerAgentError,
    ) as exc:
        print(f"AI_Cooker could not complete the demo: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
