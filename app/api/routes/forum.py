"""Internal Java-facing API for checkpoint-free forum draft generation."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import AgentRuntime, get_agent_runtime
from app.api.schemas.forum import ForumDraftRequest, ForumDraftResponse
from app.services.forum_draft import (
    DraftHistoryMessage,
    ForumDraftModelError,
    ForumDraftOutputError,
    InvalidForumDraftInputError,
)

router = APIRouter(prefix="/api/v1/forum", tags=["forum-drafts"])


@router.post("/drafts", response_model=ForumDraftResponse)
async def generate_forum_draft(
    request: ForumDraftRequest,
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
) -> ForumDraftResponse:
    history = [
        DraftHistoryMessage(message.role, message.content)
        for message in request.messages
    ]
    try:
        draft = await runtime.generate_forum_draft(
            history,
            request.model_id,
            request.conversation_id,
        )
    except InvalidForumDraftInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (ForumDraftModelError, ForumDraftOutputError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI service could not generate a valid forum draft.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred.",
        ) from exc

    return ForumDraftResponse(
        title=draft.title,
        content=draft.content,
        dish_name=draft.dish_name,
    )
