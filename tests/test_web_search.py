"""Tests for the independently degrading Tavily boundary."""

import unittest

from app.config.settings import Settings
from app.tools.web_search import (
    WebSearchError,
    WebSearchTool,
    create_web_search_tool,
)


class WebSearchToolTests(unittest.TestCase):
    def test_converts_returned_tavily_error_to_safe_tool_exception(self) -> None:
        source_error = RuntimeError("provider failed")

        with self.assertRaises(WebSearchError) as raised:
            WebSearchTool._raise_for_error({"error": source_error})

        self.assertIs(raised.exception.__cause__, source_error)

    def test_preserves_successful_result(self) -> None:
        result = {"results": [{"title": "Recipe"}]}
        self.assertIs(WebSearchTool._raise_for_error(result), result)

    def test_missing_key_returns_safe_unavailable_tool(self) -> None:
        settings = Settings(
            "step-3.7-flash",
            "model-key",
            "https://model.example/v1",
            "localhost",
            3306,
            "user",
            "password",
            "agent_web",
        )

        tool = create_web_search_tool(settings)

        self.assertEqual(tool.name, "web_search")
        self.assertIn("web_search_unavailable", tool.invoke({"query": "latest"}))


if __name__ == "__main__":
    unittest.main()
