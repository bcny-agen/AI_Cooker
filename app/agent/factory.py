"""Factory for assembling the reusable AI_Cooker LangGraph Agent."""

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.agent.prompts import COOKER_SYSTEM_PROMPT
from app.agent.context import AgentRunContext
from app.agent.constraints import DeterministicConstraintMiddleware
from app.agent.reliability import GroundedFailureRecoveryMiddleware
from app.config.settings import Settings
from app.memory.context_compression import ConversationContextMiddleware
from app.memory.user_memory_context import UserMemoryContextMiddleware
from app.memory.conversation_summary import ConversationSummaryStore
from app.models.chat_model import create_chat_model_from_definition
from app.models.registry import ModelId, build_model_definitions
from app.tools.recipe_search import create_recipe_search_tool
from app.tools.recipe_search import RecipeKBRuntime
from app.tools.web_search import create_web_search_tool
from app.tools.dish_image import GeneratedImageBuffer, create_dish_image_tool


def create_cooker_agent(
    settings: Settings,
    checkpointer: BaseCheckpointSaver,
    image_buffer: GeneratedImageBuffer | None = None,
    recipe_kb_runtime: RecipeKBRuntime | None = None,
) -> CompiledStateGraph:
    """Create the Agent explicitly; importing this module performs no I/O."""

    model = create_chat_model_from_definition(
        build_model_definitions(settings)[ModelId.STEP_FLASH_3_7]
    )
    recipe_runtime = recipe_kb_runtime or RecipeKBRuntime(settings).start()
    recipe_search = create_recipe_search_tool(recipe_runtime)
    web_search = create_web_search_tool(settings)
    dish_image = create_dish_image_tool(
        settings,
        image_buffer or GeneratedImageBuffer(),
    )

    return create_agent(
        model=model,
        tools=[recipe_search, web_search, dish_image],
        system_prompt=COOKER_SYSTEM_PROMPT,
        middleware=[
            DeterministicConstraintMiddleware(),
            GroundedFailureRecoveryMiddleware(),
        ],
        checkpointer=checkpointer,
    )


def create_cooker_agents(
    settings: Settings,
    checkpointer: BaseCheckpointSaver,
    *,
    models: dict[ModelId, BaseChatModel] | None = None,
    summary_store: ConversationSummaryStore | None = None,
    image_buffer: GeneratedImageBuffer | None = None,
    recipe_kb_runtime: RecipeKBRuntime | None = None,
) -> dict[ModelId, CompiledStateGraph]:
    """Build each configured Agent once while sharing prompt, tool, and saver."""

    definitions = build_model_definitions(settings)
    recipe_runtime = recipe_kb_runtime or RecipeKBRuntime(settings).start()
    recipe_search = create_recipe_search_tool(recipe_runtime)
    web_search = create_web_search_tool(settings)
    dish_image = create_dish_image_tool(
        settings,
        image_buffer or GeneratedImageBuffer(),
    )
    resolved_models = models or {
        model_id: create_chat_model_from_definition(definition)
        for model_id, definition in definitions.items()
        if definition.available
    }
    agents: dict[ModelId, CompiledStateGraph] = {}
    for model_id, model in resolved_models.items():
        middleware = [
            UserMemoryContextMiddleware(),
            DeterministicConstraintMiddleware(
                # DeepSeek thinking mode rejects named tool_choice with HTTP
                # 400; it still receives the same constraint prompt/schema and
                # all recipe_search arguments remain deterministically merged.
                force_recipe_search=(model_id == ModelId.STEP_FLASH_3_7),
            ),
            GroundedFailureRecoveryMiddleware(),
        ]
        if summary_store is not None:
            middleware.append(ConversationContextMiddleware(
                model_id=model_id,
                summary_model=model,
                store=summary_store,
                policy=definitions[model_id].context_policy,
                max_summary_characters=settings.summary_max_characters,
            ))
        agents[model_id] = create_agent(
            model=model,
            tools=[recipe_search, web_search, dish_image],
            system_prompt=COOKER_SYSTEM_PROMPT,
            middleware=middleware,
            context_schema=AgentRunContext,
            checkpointer=checkpointer,
        )
    return agents
