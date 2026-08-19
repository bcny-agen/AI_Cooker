"""Unit tests for the Agent-callable Step dish image tool."""

import json
import unittest

from app.config.settings import Settings
from app.tools.dish_image import (
    GeneratedImageBuffer,
    build_culinary_image_prompt,
    create_dish_image_tool,
)


class FakeImageGenerator:
    model = "step-image-edit-2"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> tuple[bytes, str]:
        self.prompts.append(prompt)
        return b"\x89PNG\r\n\x1a\nprivate-image", "image/png"


def settings() -> Settings:
    return Settings(
        model_name="step-3.7-flash",
        model_api_key="test-key",
        model_base_url="https://api.stepfun.com/step_plan/v1",
        mysql_host="localhost",
        mysql_port=3306,
        mysql_user="test",
        mysql_password="test",
        mysql_database="test",
        tavily_api_key="test",
    )


class DishImageToolTests(unittest.TestCase):
    def test_selected_dish_description_becomes_grounded_culinary_prompt(self) -> None:
        generator = FakeImageGenerator()
        buffer = GeneratedImageBuffer()
        tool = create_dish_image_tool(
            settings(),
            buffer,
            generator=generator,
        )

        result = json.loads(tool.invoke({
            "dish_description": (
                "Kung Pao chicken with chicken, peanuts and dried chilies"
            ),
        }))

        self.assertEqual(result["status"], "generated")
        self.assertEqual(result["image_model"], "step-image-edit-2")
        self.assertEqual(len(generator.prompts), 1)
        self.assertIn("Kung Pao chicken", generator.prompts[0])
        self.assertIn("only ingredients supported", generator.prompts[0])
        self.assertNotIn("Generate the second dish", generator.prompts[0])
        self.assertIsNotNone(buffer.get(result["generation_id"]))

    def test_prompt_is_bounded_and_does_not_add_named_ingredients(self) -> None:
        prompt = build_culinary_image_prompt("Tomato scrambled eggs")

        self.assertLessEqual(len(prompt), 512)
        self.assertIn("Tomato scrambled eggs", prompt)
        self.assertNotIn("peanuts", prompt.lower())


if __name__ == "__main__":
    unittest.main()
