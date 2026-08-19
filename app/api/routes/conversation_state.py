"""Same-host Java-to-Python conversation state cleanup endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import (
    AgentRuntime,
    get_agent_runtime,
    require_internal_caller,
)
from app.memory.conversation_state import ConversationStateCleanupError


router = APIRouter(prefix="/api/v1", tags=["internal"])


@router.delete(
    "/internal/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def delete_conversation_state(
    thread_id: str,
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
    _internal: Annotated[None, Depends(require_internal_caller)],
) -> Response:
    try:
        await runtime.delete_conversation_state(thread_id)
    except ConversationStateCleanupError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation persistence is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The AI Agent state could not be deleted.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
