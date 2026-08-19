"""Tool instrumentation that preserves schemas, descriptions, and outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool


@dataclass(slots=True)
class ToolCallRecord:
    turn_index: int
    name: str
    arguments: dict[str, Any]
    output: Any
    latency_ms: float
    error_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ToolRecorder:
    def __init__(self) -> None:
        self.turn_index = 0
        self.records: list[ToolCallRecord] = []

    def begin_scenario(self) -> None:
        self.turn_index = 0
        self.records.clear()

    def begin_turn(self, turn_index: int) -> None:
        self.turn_index = turn_index

    def turn_records(self, turn_index: int) -> list[dict[str, Any]]:
        return [
            record.as_dict()
            for record in self.records
            if record.turn_index == turn_index
        ]


def instrument_tool(tool: BaseTool, recorder: ToolRecorder) -> StructuredTool:
    """Wrap one synchronous Agent tool without changing its model contract."""

    def invoke_instrumented(**kwargs: Any) -> Any:
        started = perf_counter()
        output: Any = None
        error_type: str | None = None
        try:
            output = tool.invoke(kwargs)
            rendered = str(output)
            if tool.name == "web_search" and (
                "temporarily unavailable" in rendered
                or "web_search_unavailable" in rendered
                or "WebSearchError" in rendered
            ):
                error_type = "TavilyUnavailable"
            elif tool.name == "recipe_search" and (
                '"available":false' in rendered.replace(" ", "").casefold()
                or "recipe_kb_query_failed" in rendered
            ):
                error_type = "RecipeKBUnavailable"
            return output
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            recorder.records.append(ToolCallRecord(
                turn_index=recorder.turn_index,
                name=tool.name,
                arguments=dict(kwargs),
                output=output,
                latency_ms=round((perf_counter() - started) * 1000, 3),
                error_type=error_type,
            ))

    return StructuredTool.from_function(
        func=invoke_instrumented,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        handle_tool_error=getattr(tool, "handle_tool_error", False),
    )
