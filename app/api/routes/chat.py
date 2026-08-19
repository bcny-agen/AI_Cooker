"""Text and multimodal chat endpoints, including SSE streaming."""

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    AgentRuntime,
    get_agent_runtime,
    require_internal_caller,
)
from app.api.schemas.chat import (
    ChatRecoveryRequest,
    ChatRequest,
    ChatResponse,
    GeneratedImageTransfer,
)
from app.services.cooker_agent import (
    AgentExecutionError,
    AgentResponseError,
    CheckpointerInvocationError,
    CookerAgentError,
    InvalidAgentInputError,
    ModelInvocationError,
    SearchInvocationError,
    ThreadRecoveryRequiredError,
    ConversationHistoryMessage,
)

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _generated_images(response: object) -> list[GeneratedImageTransfer]:
    additional_kwargs = getattr(response, "additional_kwargs", None)
    if not isinstance(additional_kwargs, dict):
        return []
    raw_items = additional_kwargs.get("generated_images")
    if not isinstance(raw_items, list):
        return []
    result: list[GeneratedImageTransfer] = []
    for item in raw_items[:1]:
        try:
            result.append(GeneratedImageTransfer.model_validate(item))
        except (TypeError, ValueError):
            continue
    return result


def _sse(event_type: str, data: dict[str, str]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {payload}\n\n"


def _public_stream_error(error: BaseException) -> str:
    if isinstance(error, (ModelInvocationError, SearchInvocationError)):
        return "An upstream AI service failed."
    if isinstance(error, CheckpointerInvocationError):
        return "Conversation persistence is temporarily unavailable."
    return "The AI Agent could not complete the request."


def _recovery_conflict(error: ThreadRecoveryRequiredError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "thread_recovery_required",
            "reason": error.reason,
        },
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
) -> ChatResponse:
    image_url = str(request.image_url) if request.image_url is not None else None

    try:
        response = await runtime.chat(
            conversation_id=request.conversation_id,
            message=request.message,
            image_url=image_url,
            model_id=request.model_id,
            user_memories=request.user_memories,
            continuation_expected=request.continuation_expected,
        )
    except ThreadRecoveryRequiredError as exc:
        raise _recovery_conflict(exc) from exc
    except InvalidAgentInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (ModelInvocationError, SearchInvocationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="An upstream AI service failed.",
        ) from exc
    except CheckpointerInvocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation persistence is temporarily unavailable.",
        ) from exc
    except (AgentResponseError, AgentExecutionError, CookerAgentError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The AI Agent could not complete the request.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred.",
        ) from exc

    return ChatResponse(
        conversation_id=request.conversation_id,
        answer=response.text,
        generated_images=_generated_images(response),
    )


@router.post("/chat/stream", response_class=StreamingResponse)
async def stream_chat(
    request: ChatRequest,
    http_request: Request,
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
) -> StreamingResponse:
    """Stream genuine LangGraph status and model-content events over SSE."""

    image_url = str(request.image_url) if request.image_url is not None else None

    if request.continuation_expected:
        try:
            await runtime.ensure_continuation_ready(
                request.conversation_id,
                request.model_id,
            )
        except ThreadRecoveryRequiredError as exc:
            raise _recovery_conflict(exc) from exc
        except InvalidAgentInputError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CheckpointerInvocationError as exc:
            raise HTTPException(
                status_code=503,
                detail="Conversation persistence is temporarily unavailable.",
            ) from exc
        except CookerAgentError as exc:
            raise HTTPException(
                status_code=500,
                detail="The AI Agent could not inspect the conversation.",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail="An unexpected internal error occurred.",
            ) from exc

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in runtime.stream_chat(
                conversation_id=request.conversation_id,
                message=request.message,
                image_url=image_url,
                model_id=request.model_id,
                user_memories=request.user_memories,
                continuation_expected=False,
            ):
                if await http_request.is_disconnected():
                    break
                yield _sse(event.type, event.as_dict())
        except Exception as exc:
            if await http_request.is_disconnected():
                return
            yield _sse(
                "error",
                {
                    "type": "error",
                    "message": _public_stream_error(exc),
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/internal/chat/recover",
    response_model=ChatResponse,
    include_in_schema=False,
)
async def recover_chat(
    request: ChatRecoveryRequest,
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
    _internal: Annotated[None, Depends(require_internal_caller)],
) -> ChatResponse:
    """Internal Java-to-Python recovery path; never exposed by Java's API."""

    history = [
        ConversationHistoryMessage(
            message_id=item.message_id,
            role=item.role,
            content=item.content,
        )
        for item in request.recovery_history
    ]
    image_url = str(request.image_url) if request.image_url is not None else None
    try:
        await runtime.recover_thread(
            request.conversation_id,
            history,
            request.model_id,
        )
        response = await runtime.chat(
            conversation_id=request.conversation_id,
            message=request.message,
            image_url=image_url,
            model_id=request.model_id,
            user_memories=request.user_memories,
            continuation_expected=False,
        )
    except InvalidAgentInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ModelInvocationError, SearchInvocationError) as exc:
        raise HTTPException(
            status_code=502,
            detail="An upstream AI service failed.",
        ) from exc
    except CheckpointerInvocationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Conversation persistence is temporarily unavailable.",
        ) from exc
    except CookerAgentError as exc:
        raise HTTPException(
            status_code=500,
            detail="The AI Agent could not complete the request.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal error occurred.",
        ) from exc
    return ChatResponse(
        conversation_id=request.conversation_id,
        answer=response.text,
        generated_images=_generated_images(response),
    )


@router.post(
    "/internal/chat/stream/recover",
    response_class=StreamingResponse,
    include_in_schema=False,
)
async def recover_stream_chat(
    request: ChatRecoveryRequest,
    http_request: Request,
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
    _internal: Annotated[None, Depends(require_internal_caller)],
) -> StreamingResponse:
    """Recover state before returning SSE, so failures remain HTTP errors."""

    history = [
        ConversationHistoryMessage(
            message_id=item.message_id,
            role=item.role,
            content=item.content,
        )
        for item in request.recovery_history
    ]
    try:
        await runtime.recover_thread(
            request.conversation_id,
            history,
            request.model_id,
        )
    except InvalidAgentInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CheckpointerInvocationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Conversation persistence is temporarily unavailable.",
        ) from exc
    except CookerAgentError as exc:
        raise HTTPException(
            status_code=500,
            detail="The AI Agent could not recover the conversation.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="An unexpected internal error occurred.",
        ) from exc

    image_url = str(request.image_url) if request.image_url is not None else None

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in runtime.stream_chat(
                conversation_id=request.conversation_id,
                message=request.message,
                image_url=image_url,
                model_id=request.model_id,
                user_memories=request.user_memories,
                continuation_expected=False,
            ):
                if await http_request.is_disconnected():
                    break
                yield _sse(event.type, event.as_dict())
        except Exception as exc:
            if not await http_request.is_disconnected():
                yield _sse("error", {
                    "type": "error",
                    "message": _public_stream_error(exc),
                })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
