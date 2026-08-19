"""Internal Java-to-Python endpoint for memory candidate extraction."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from openai import OpenAIError

from app.api.dependencies import AgentRuntime, get_agent_runtime
from app.api.schemas.memory import MemoryExtractionRequest, MemoryExtractionResponse
from app.services.user_memory_extraction import MemoryExtractionError


router = APIRouter(prefix="/api/v1/memories", tags=["memory"])


@router.post("/extract", response_model=MemoryExtractionResponse)
async def extract_memories(
    request: MemoryExtractionRequest,
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
) -> MemoryExtractionResponse:
    try:
        memories = await runtime.extract_user_memories(
            current_user_message=request.current_user_message,
            context=request.context,
            model_id=request.model_id,
        )
    except (OpenAIError, MemoryExtractionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="User-memory extraction failed.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User-memory extraction failed.",
        ) from exc
    return MemoryExtractionResponse(memories=memories)
