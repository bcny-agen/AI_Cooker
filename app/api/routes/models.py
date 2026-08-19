"""Model discovery endpoint consumed by the Java backend."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import AgentRuntime, get_agent_runtime
from app.api.schemas.models import ModelResponse

router = APIRouter(prefix="/api/v1", tags=["models"])


@router.get("/models", response_model=list[ModelResponse])
async def list_models(
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
) -> list[ModelResponse]:
    return [
        ModelResponse(
            id=item.id,
            display_name=item.display_name,
            supports_text=item.supports_text,
            supports_tools=item.supports_tools,
            supports_streaming=item.supports_streaming,
            supports_images=item.supports_images,
            available=item.available,
        )
        for item in runtime.available_models()
    ]
