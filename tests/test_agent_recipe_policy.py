"""Static Agent-policy regressions for tool routing and multimodal continuity."""

import unittest

from app.agent.prompts import COOKER_SYSTEM_PROMPT


class AgentRecipePolicyTests(unittest.TestCase):
    def test_recipe_kb_is_primary_and_tavily_is_conditional(self) -> None:
        self.assertIn("优先调用 recipe_search", COOKER_SYSTEM_PROMPT)
        self.assertIn("coverage_sufficient=true", COOKER_SYSTEM_PROMPT)
        self.assertIn("不要自动继续网页搜索", COOKER_SYSTEM_PROMPT)
        self.assertIn("coverage_sufficient=false", COOKER_SYSTEM_PROMPT)
        self.assertIn("web_search", COOKER_SYSTEM_PROMPT)

    def test_image_ingredients_followup_and_image_tool_policies_are_preserved(self) -> None:
        self.assertIn("available_ingredients", COOKER_SYSTEM_PROMPT)
        self.assertIn("不要无意义地重复检索", COOKER_SYSTEM_PROMPT)
        self.assertIn("include_steps=true", COOKER_SYSTEM_PROMPT)
        self.assertIn("Call generate_dish_image only", COOKER_SYSTEM_PROMPT)
        self.assertIn("the second dish", COOKER_SYSTEM_PROMPT)

    def test_synthetic_dataset_is_not_presented_as_authoritative(self) -> None:
        self.assertIn("human_reviewed=false", COOKER_SYSTEM_PROMPT)
        self.assertIn("不得称其为权威", COOKER_SYSTEM_PROMPT)
        self.assertIn("必须来自该工具本次返回的字段", COOKER_SYSTEM_PROMPT)
        self.assertIn("不得把模型自行想到的候选混入", COOKER_SYSTEM_PROMPT)
        self.assertIn("过敏", COOKER_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
