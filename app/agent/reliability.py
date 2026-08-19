"""Narrow model-response reliability middleware for real Agent streaming."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage
from langchain_core.messages import HumanMessage, ToolMessage
from openai import OpenAIError


GROUNDED_RECOVERY_POLICY_VERSION = "grounded-model-failure-recovery-v1"


class EmptyFinalModelResponseRetryMiddleware(AgentMiddleware):
    """Retry once when a model call returns neither text nor a tool request.

    This wraps only the current model node. It does not replay completed tools,
    fabricate assistant text, or retry a response that has already emitted text.
    """

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        response = handler(request)
        if not self._is_empty_ai_response(response):
            return response
        return handler(request)

    @staticmethod
    def _is_empty_ai_response(response: ModelCallResult) -> bool:
        if isinstance(response, AIMessage):
            messages = [response]
        elif isinstance(response, ModelResponse):
            messages = response.result
        else:
            return False
        ai_messages = [
            message for message in messages if isinstance(message, AIMessage)
        ]
        return bool(ai_messages) and all(
            not message.text
            and not message.tool_calls
            and not message.invalid_tool_calls
            for message in ai_messages
        )


class GroundedFailureRecoveryMiddleware(EmptyFinalModelResponseRetryMiddleware):
    """Retry one model node, then recover only from completed tool evidence.

    Tools are never replayed. A deterministic response is created only when a
    Recipe KB or Tavily ToolMessage exists after the latest user message. With
    no such evidence, the original exception/empty response remains visible to
    the service-level failure handling.
    """

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        first_error: OpenAIError | None = None
        first_response: ModelCallResult | None = None
        try:
            first_response = handler(request)
            if not self._is_empty_ai_response(first_response):
                return first_response
        except OpenAIError as exc:
            first_error = exc

        try:
            second = handler(request)
            if not self._is_empty_ai_response(second):
                return second
            recovery = self._grounded_recovery(request)
            return recovery if recovery is not None else second
        except OpenAIError:
            recovery = self._grounded_recovery(request)
            if recovery is not None:
                return recovery
            if first_error is not None:
                raise first_error
            raise

    @classmethod
    def _grounded_recovery(cls, request: ModelRequest) -> ModelResponse | None:
        evidence = cls._tool_evidence_after_latest_user(request.messages)
        if not evidence:
            return None
        sections = [
            cls._render_recipe_evidence(value)
            if name == "recipe_search"
            else cls._render_web_evidence(value)
            for name, value in evidence
        ]
        rendered = [section for section in sections if section]
        if not rendered:
            return None
        text = (
            "The final model response was unavailable, so this conservative "
            "answer contains only evidence already returned by the completed "
            "cooking tools.\n\n" + "\n\n".join(rendered)
        )
        return ModelResponse(result=[AIMessage(
            content=text,
            additional_kwargs={
                "ai_cooker_recovery_policy": GROUNDED_RECOVERY_POLICY_VERSION,
            },
        )])

    @staticmethod
    def _tool_evidence_after_latest_user(
        messages: list[Any],
    ) -> list[tuple[str, Any]]:
        last_human = max(
            (
                index for index, message in enumerate(messages)
                if isinstance(message, HumanMessage)
            ),
            default=-1,
        )
        evidence: list[tuple[str, Any]] = []
        for message in messages[last_human + 1:]:
            if not isinstance(message, ToolMessage):
                continue
            name = message.name or ""
            if name not in {"recipe_search", "web_search"}:
                continue
            value = message.content
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    continue
            if isinstance(value, dict):
                evidence.append((name, value))
        return evidence

    @staticmethod
    def _render_recipe_evidence(value: dict[str, Any]) -> str:
        recipes = value.get("recipes")
        if not isinstance(recipes, list) or not recipes:
            reason = str(value.get("coverage_reason") or "no qualified Recipe KB result")
            return f"Recipe KB returned no recipe candidates ({reason})."
        lines = ["Recipe KB results:"]
        for item in recipes[:5]:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            details = [str(item["name"])]
            if isinstance(item.get("total_minutes"), (int, float)):
                details.append(f"{item['total_minutes']} minutes")
            if item.get("difficulty") is not None:
                details.append(f"difficulty {item['difficulty']}/5")
            summary = str(item.get("summary") or "").strip()
            missing = item.get("missing_required_ingredients")
            suffix = "; ".join(details)
            if summary:
                suffix += f" — {summary}"
            if isinstance(missing, list) and missing:
                suffix += "; additional ingredients needed: " + ", ".join(
                    str(part) for part in missing[:8]
                )
            lines.append(f"- {suffix}")
        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _render_web_evidence(value: dict[str, Any]) -> str:
        results = value.get("results")
        if not isinstance(results, list) or not results:
            return "Web search completed but returned no usable sources."
        lines = ["Current web sources:"]
        for item in results[:5]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "Untitled source").strip()
            url = str(item.get("url") or "").strip()
            content = " ".join(str(item.get("content") or "").split())[:240]
            line = f"- {title}"
            if url:
                line += f": {url}"
            if content:
                line += f" — {content}"
            lines.append(line)
        return "\n".join(lines) if len(lines) > 1 else ""
