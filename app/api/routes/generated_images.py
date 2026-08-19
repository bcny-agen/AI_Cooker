"""Loopback-only transfer of generated image bytes to the Java service."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import (
    AgentRuntime,
    get_agent_runtime,
    require_internal_caller,
)


router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


@router.get(
    "/generated-images/{generation_id}",
    response_class=Response,
    include_in_schema=False,
)
async def get_generated_image(
    generation_id: UUID,
    runtime: Annotated[AgentRuntime, Depends(get_agent_runtime)],
    _internal: Annotated[None, Depends(require_internal_caller)],
) -> Response:
    """Return one short-lived generated image to a same-host Java caller."""

    payload = runtime.get_generated_image(str(generation_id))
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated image is unavailable or expired.",
        )
    return Response(
        content=payload.data,
        media_type=payload.content_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
