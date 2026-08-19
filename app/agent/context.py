"""Run-scoped context supplied by the trusted Java business service."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentRunContext:
    """Sanitized user preferences for one Agent invocation only."""

    user_memories: tuple[str, ...] = ()
