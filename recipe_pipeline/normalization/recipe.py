"""Convert source records into strict Recipe Schema v1 objects."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from recipe_pipeline.normalization.ingredients import IngredientCatalog
from recipe_pipeline.schemas.recipe import (
    Difficulty,
    Equipment,
    Identity,
    QualityMetadata,
    Quantity,
    RawRecipe,
    RecipeIngredient,
    RecipeStep,
    RecipeTime,
    RecipeV1,
    Serving,
)


class StepIngredientReferenceError(ValueError):
    """Raised when a step refers to an ingredient absent from its recipe."""


class RecipeNormalizer:
    def __init__(self, catalog: IngredientCatalog | None = None):
        self.catalog = catalog or IngredientCatalog()

    def normalize(self, raw: RawRecipe) -> RecipeV1:
        ingredient_rows: list[RecipeIngredient] = []
        source_alias_to_id = {}
        included_ids = set()

        for raw_ingredient in raw.ingredients:
            canonical = self.catalog.resolve(raw_ingredient.name)
            included_ids.add(canonical.ingredient_id)
            source_alias_to_id[raw_ingredient.name.strip().casefold()] = canonical.ingredient_id
            ingredient_rows.append(
                RecipeIngredient(
                    ingredient_id=canonical.ingredient_id,
                    display_name=raw_ingredient.display_name or raw_ingredient.name,
                    normalized_name=canonical.normalized_name,
                    role=raw_ingredient.role,
                    importance=raw_ingredient.importance,
                    requirement_group=raw_ingredient.requirement_group,
                    quantity=Quantity(
                        minimum=raw_ingredient.quantity_min,
                        maximum=raw_ingredient.quantity_max,
                        unit=raw_ingredient.unit,
                    ),
                    preparation=raw_ingredient.preparation,
                )
            )

        steps: list[RecipeStep] = []
        for raw_step in raw.steps:
            refs = []
            for name in raw_step.ingredient_names:
                canonical = self.catalog.resolve(name)
                if canonical.ingredient_id not in included_ids:
                    raise StepIngredientReferenceError(
                        f"step {raw_step.order} refers to ingredient not in recipe: {name!r}"
                    )
                refs.append(canonical.ingredient_id)
            steps.append(
                RecipeStep(
                    order=raw_step.order,
                    phase=raw_step.phase,
                    instruction=raw_step.instruction,
                    duration_minutes=raw_step.duration_minutes,
                    method=raw_step.method,
                    heat_level=raw_step.heat_level,
                    temperature_celsius=raw_step.temperature_celsius,
                    ingredient_refs=list(dict.fromkeys(refs)),
                    equipment_refs=raw_step.equipment_refs,
                    safety_note=raw_step.safety_note,
                )
            )

        recipe_id = raw.recipe_id or uuid5(
            NAMESPACE_URL,
            f"ai-cooker:recipe:{raw.source.source_name}:{raw.source.source_record_id}",
        )
        return RecipeV1(
            recipe_id=recipe_id,
            identity=Identity(
                name=raw.name,
                aliases=raw.aliases,
                language=raw.language,
                region=raw.region,
                cuisine=raw.cuisine,
                category=raw.category,
                summary=raw.summary,
            ),
            serving=Serving(
                min_servings=raw.min_servings,
                max_servings=raw.max_servings,
            ),
            time=RecipeTime(
                prep_minutes=raw.prep_minutes,
                cook_minutes=raw.cook_minutes,
                inactive_minutes=raw.inactive_minutes,
                total_minutes=raw.total_minutes,
            ),
            difficulty=Difficulty(
                level=raw.difficulty_level,
                reasons=raw.difficulty_reasons,
            ),
            ingredients=ingredient_rows,
            substitutes=[],
            steps=steps,
            equipment=Equipment(
                required=raw.equipment_required,
                optional=raw.equipment_optional,
            ),
            taste_profile=raw.taste_profile,
            nutrition=raw.nutrition,
            tags=raw.tags,
            source=raw.source,
            quality=QualityMetadata(),
        )
