"""Unit tests for conservative structured user-memory extraction."""

import unittest

from langchain_core.messages import AIMessage

from app.api.schemas.memory import MemoryContextMessage
from app.models.registry import ModelId
from app.services.user_memory_extraction import (
    MemoryExtractionError,
    UserMemoryExtractionService,
)


class FakeExtractionModel:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = []

    def invoke(self, messages, config=None):
        self.calls.append((messages, config))
        return AIMessage(content=self.response)


class UserMemoryExtractionTests(unittest.TestCase):
    def service(self, response: str):
        model = FakeExtractionModel(response)
        return UserMemoryExtractionService({
            ModelId.STEP_FLASH_3_7: model,  # type: ignore[dict-item]
        }), model

    def test_extracts_stable_food_preference_with_grounding_quote(self) -> None:
        service, model = self.service("""
            {"memories":[{
              "action":"UPSERT",
              "memory_type":"FOOD_PREFERENCE",
              "key":"coriander",
              "value":"avoid",
              "confidence":0.96,
              "source_text":"I don't eat coriander"
            }]}
        """)

        result = service.extract(
            current_user_message="I don't eat coriander.",
            context=[],
            model_id=ModelId.STEP_FLASH_3_7,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].key, "coriander")
        self.assertEqual(result[0].memory_type, "FOOD_PREFERENCE")
        self.assertIn(
            "<current_user_message>\nI don't eat coriander.",
            model.calls[0][0][1].text,
        )
        self.assertEqual(
            model.calls[0][1]["tags"],
            ["ai_cooker_memory_extraction"],
        )

    def test_extracts_allergy_as_safety_restriction(self) -> None:
        service, _model = self.service("""
            {"memories":[{
              "action":"UPSERT",
              "memory_type":"DIETARY_RESTRICTION",
              "key":"peanut",
              "value":"allergy",
              "confidence":0.99,
              "source_text":"I have a peanut allergy"
            }]}
        """)

        result = service.extract(
            current_user_message="I have a peanut allergy.",
            context=[],
            model_id=ModelId.STEP_FLASH_3_7,
        )

        self.assertEqual(result[0].memory_type, "DIETARY_RESTRICTION")
        self.assertEqual(result[0].value, "allergy")

    def test_temporary_inventory_correctly_allows_empty_result(self) -> None:
        service, model = self.service('{"memories":[]}')

        result = service.extract(
            current_user_message="I have three eggs today.",
            context=[],
            model_id=ModelId.STEP_FLASH_3_7,
        )

        self.assertEqual(result, [])
        self.assertIn("temporary inventory", model.calls[0][0][0].text)

    def test_no_forced_memory_and_assistant_context_is_context_only(self) -> None:
        service, model = self.service('{"memories":[]}')

        result = service.extract(
            current_user_message="Thanks!",
            context=[MemoryContextMessage(
                role="ASSISTANT",
                content="You probably prefer low-oil recipes.",
            )],
            model_id=ModelId.STEP_FLASH_3_7,
        )

        self.assertEqual(result, [])
        self.assertIn("Earlier USER and ASSISTANT messages are", model.calls[0][0][0].text)

    def test_invalid_structured_output_is_rejected(self) -> None:
        service, _model = self.service("not json")

        with self.assertRaises(MemoryExtractionError):
            service.extract(
                current_user_message="I prefer mild food.",
                context=[],
                model_id=ModelId.STEP_FLASH_3_7,
            )


if __name__ == "__main__":
    unittest.main()
