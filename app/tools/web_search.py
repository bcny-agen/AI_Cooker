"""Tavily web-search tool retained as an independent Recipe KB fallback."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from langchain_tavily import TavilySearch

from app.config.settings import Settings


class WebSearchConfigurationError(RuntimeError):
    """Raised when the Tavily tool cannot be configured."""


class WebSearchError(ToolException):
    """A Tavily failure visible to the model without terminating the Agent."""


class WebSearchTool(TavilySearch):
    """TavilySearch whose provider errors remain inside the tool boundary."""

    @staticmethod
    def _raise_for_error(result: Any) -> Any:
        if not isinstance(result, dict) or not result.get("error"):
            return result

        error = result["error"]
        failure = WebSearchError(
            "Web search is temporarily unavailable. Continue from Recipe KB "
            "results when they are sufficient; otherwise explain the limitation."
        )
        if isinstance(error, BaseException):
            raise failure from error
        raise failure

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        try:
            result = super()._run(*args, **kwargs)
        except WebSearchError:
            raise
        except Exception as error:
            raise self._unavailable_failure() from error
        return self._raise_for_error(result)

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        try:
            result = await super()._arun(*args, **kwargs)
        except WebSearchError:
            raise
        except Exception as error:
            raise self._unavailable_failure() from error
        return self._raise_for_error(result)

    @staticmethod
    def _unavailable_failure() -> WebSearchError:
        return WebSearchError(
            "Web search is temporarily unavailable. Continue from Recipe KB "
            "results when they are sufficient; otherwise explain the limitation."
        )


def create_web_search_tool(settings: Settings) -> BaseTool:
    """Create Tavily with an explicit name and a narrow fallback policy."""

    description = (
        "Search the current web. For recipe recommendations, first use "
        "recipe_search and call web_search only when its "
        "coverage_sufficient field is false, it is unavailable, or the "
        "user explicitly asks for current trends, web sources, or online "
        "references. Do not call this automatically after sufficient "
        "Recipe KB results."
    )
    if not settings.tavily_api_key:
        def unavailable_web_search(query: str) -> str:
            del query
            return (
                '{"available":false,"error":"web_search_unavailable",'
                '"results":[]}'
            )

        return StructuredTool.from_function(
            func=unavailable_web_search,
            name="web_search",
            description=description,
        )
    try:
        return WebSearchTool(
            name="web_search",
            description=description,
            max_results=5,
            topic="general",
            tavily_api_key=settings.tavily_api_key,
            handle_tool_error=True,
        )
    except Exception as exc:
        raise WebSearchConfigurationError(
            "Unable to configure the Tavily web-search tool."
        ) from exc
