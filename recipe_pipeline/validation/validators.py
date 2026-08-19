"""Deterministic ingredient, step, nutrition and cooking-safety checks."""

from __future__ import annotations

import math

from recipe_pipeline.normalization.ingredients import IngredientCatalog
from recipe_pipeline.schemas.recipe import IngredientRole, RecipeV1
from recipe_pipeline.validation.models import IssueSeverity, ValidationIssue


def _issue(
    code: str,
    message: str,
    path: str,
    severity: IssueSeverity = IssueSeverity.ERROR,
) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, path=path, severity=severity)


class RecipeValidator:
    """Pure local checks. No model, network, search or database calls."""

    _UNSAFE_PHRASES = (
        "生吃鸡肉",
        "生食鸡肉",
        "raw chicken",
        "drink bleach",
        "食用漂白剂",
    )
    _MEDICAL_CLAIMS = (
        "治疗癌症",
        "治愈癌症",
        "包治百病",
        "cure cancer",
        "cures disease",
    )

    def __init__(self, catalog: IngredientCatalog | None = None):
        self._catalog = catalog or IngredientCatalog()

    def validate(self, recipe: RecipeV1) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        issues.extend(self._validate_ingredients(recipe))
        issues.extend(self._validate_steps(recipe))
        issues.extend(self._validate_safety(recipe))
        issues.extend(self._validate_nutrition(recipe))
        return issues

    def _validate_ingredients(self, recipe: RecipeV1) -> list[ValidationIssue]:
        issues = []
        referenced = {ref for step in recipe.steps for ref in step.ingredient_refs}
        ingredient_ids = {item.ingredient_id for item in recipe.ingredients}
        for index, item in enumerate(recipe.ingredients):
            catalog_item = self._catalog.get(item.ingredient_id)
            if catalog_item is None or catalog_item.normalized_name != item.normalized_name:
                issues.append(
                    _issue(
                        "INGREDIENT_CATALOG_MISMATCH",
                        "ingredient ID and normalized name do not match the controlled catalog",
                        f"ingredients[{index}]",
                    )
                )
            if item.role == IngredientRole.REQUIRED and item.ingredient_id not in referenced:
                issues.append(
                    _issue(
                        "REQUIRED_INGREDIENT_UNUSED",
                        "required ingredient is not referenced by any cooking step",
                        f"ingredients[{index}]",
                    )
                )
        for step_index, step in enumerate(recipe.steps):
            for ref in step.ingredient_refs:
                if ref not in ingredient_ids:
                    issues.append(
                        _issue(
                            "UNKNOWN_STEP_INGREDIENT",
                            "step references an ingredient absent from the recipe",
                            f"steps[{step_index}].ingredient_refs",
                        )
                    )
        return issues

    @staticmethod
    def _validate_steps(recipe: RecipeV1) -> list[ValidationIssue]:
        issues = []
        orders = [step.order for step in recipe.steps]
        if orders != list(range(1, len(recipe.steps) + 1)):
            issues.append(
                _issue(
                    "STEP_ORDER_INVALID",
                    "step order must be consecutive and start at one",
                    "steps",
                )
            )
        declared_equipment = set(recipe.equipment.required) | set(recipe.equipment.optional)
        for index, step in enumerate(recipe.steps):
            missing = set(step.equipment_refs) - declared_equipment
            if missing:
                issues.append(
                    _issue(
                        "STEP_EQUIPMENT_UNDECLARED",
                        "step references equipment absent from recipe equipment",
                        f"steps[{index}].equipment_refs",
                    )
                )
        active_minutes = sum(step.duration_minutes for step in recipe.steps)
        if active_minutes > recipe.time.total_minutes * 1.5:
            issues.append(
                _issue(
                    "STEP_TIME_MISMATCH",
                    "sum of step durations is much larger than declared total time",
                    "time.total_minutes",
                    IssueSeverity.WARNING,
                )
            )
        return issues

    def _validate_safety(self, recipe: RecipeV1) -> list[ValidationIssue]:
        issues = []
        searchable = " ".join(
            [recipe.identity.name, recipe.identity.summary]
            + [step.instruction for step in recipe.steps]
            + [step.safety_note or "" for step in recipe.steps]
        ).casefold()
        for phrase in self._UNSAFE_PHRASES:
            if phrase.casefold() in searchable:
                issues.append(
                    _issue(
                        "UNSAFE_COOKING_INSTRUCTION",
                        "recipe contains a known unsafe cooking instruction",
                        "steps",
                    )
                )
                break
        for phrase in self._MEDICAL_CLAIMS:
            if phrase.casefold() in searchable:
                issues.append(
                    _issue(
                        "UNSUPPORTED_MEDICAL_CLAIM",
                        "recipe contains an unsupported medical claim",
                        "identity.summary",
                    )
                )
                break
        for index, step in enumerate(recipe.steps):
            if step.temperature_celsius is not None and step.temperature_celsius > 350:
                issues.append(
                    _issue(
                        "IMPLAUSIBLE_TEMPERATURE",
                        "declared cooking temperature exceeds the supported household range",
                        f"steps[{index}].temperature_celsius",
                    )
                )
        return issues

    @staticmethod
    def _validate_nutrition(recipe: RecipeV1) -> list[ValidationIssue]:
        issues = []
        nutrition = recipe.nutrition
        if nutrition.calories_kcal is not None and nutrition.calories_kcal > 2_000:
            issues.append(
                _issue(
                    "IMPLAUSIBLE_CALORIES",
                    "per-serving calories exceed the pipeline plausibility limit",
                    "nutrition.calories_kcal",
                )
            )
        macros = (nutrition.protein_g, nutrition.fat_g, nutrition.carbohydrate_g)
        if any(value is not None and value > 250 for value in macros):
            issues.append(
                _issue(
                    "IMPLAUSIBLE_MACRONUTRIENT",
                    "a per-serving macronutrient value exceeds the plausibility limit",
                    "nutrition",
                )
            )
        if nutrition.calories_kcal is not None and all(value is not None for value in macros):
            protein, fat, carbohydrate = macros
            estimated = protein * 4 + fat * 9 + carbohydrate * 4
            denominator = max(nutrition.calories_kcal, 1)
            if not math.isclose(estimated, nutrition.calories_kcal, rel_tol=0.6):
                issues.append(
                    _issue(
                        "NUTRITION_CALORIE_MISMATCH",
                        "calories and declared macronutrients differ substantially",
                        "nutrition",
                        IssueSeverity.WARNING,
                    )
                )
        return issues
