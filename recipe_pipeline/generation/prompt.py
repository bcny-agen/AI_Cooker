"""Versioned prompt construction; validation rules remain in validation/."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from recipe_pipeline.normalization import IngredientCatalog
from recipe_pipeline.schemas.recipe import RawRecipe, RecipeCategory


RECIPE_GENERATION_PROMPT_VERSION = "recipe_generation_prompt_v1"


class DatasetSegment(str, Enum):
    CHINESE_HOME = "CHINESE_HOME"
    QUICK_MEALS = "QUICK_MEALS"
    HEALTHY_MEALS = "HEALTHY_MEALS"
    BEGINNER_COOKING = "BEGINNER_COOKING"
    AIR_FRYER_SIMPLE_TOOLS = "AIR_FRYER_SIMPLE_TOOLS"


_SEGMENT_RULES: dict[DatasetSegment, str] = {
    DatasetSegment.CHINESE_HOME: (
        "Create practical Chinese household dishes. Use region CHINESE_HOME and "
        "cuisine CHINESE. Prefer ordinary family meals over restaurant showpieces."
    ),
    DatasetSegment.QUICK_MEALS: (
        "Every recipe must have total_minutes <= 30 and include QUICK_MEAL. "
        "Use few ingredients and normal household equipment."
    ),
    DatasetSegment.HEALTHY_MEALS: (
        "Every recipe must include HEALTHY_MEAL. Prefer vegetables and balanced "
        "protein, but make no medical or weight-loss claims. Use null numeric "
        "nutrition values and UNKNOWN levels whenever uncertain."
    ),
    DatasetSegment.BEGINNER_COOKING: (
        "Every recipe must include BEGINNER_FRIENDLY, use difficulty level 1 or 2, "
        "and provide explicit, safe, easy-to-follow steps."
    ),
    DatasetSegment.AIR_FRYER_SIMPLE_TOOLS: (
        "Every recipe must include AIR_FRYER, declare AIR_FRYER as required "
        "equipment, and include at least one AIR_FRY step. Use realistic household "
        "temperatures from 120 to 220 Celsius."
    ),
}


@dataclass(frozen=True, slots=True)
class RecipeGenerationPrompt:
    segment: DatasetSegment
    batch_index: int
    attempt: int
    source_record_prefix: str
    avoid_names: tuple[str, ...] = ()
    catalog: IngredientCatalog | None = None

    @property
    def version(self) -> str:
        return RECIPE_GENERATION_PROMPT_VERSION

    def build(self, category: RecipeCategory, count: int) -> str:
        catalog = self.catalog or IngredientCatalog()
        canonical_names = json.dumps(
            list(catalog.canonical_names), ensure_ascii=False
        )
        avoid_names = json.dumps(list(self.avoid_names), ensure_ascii=False)
        schema = json.dumps(
            RawRecipe.model_json_schema(), ensure_ascii=False, separators=(",", ":")
        )
        retry_note = (
            "This is the single correction attempt. Check every required field, "
            "enum, ingredient name, step reference and item count carefully."
            if self.attempt > 1
            else "This is the initial generation attempt."
        )
        return f"""PROMPT_VERSION: {self.version}

You generate trustworthy structured data for an AI household cooking assistant.
Return exactly one JSON object with exactly one key named \"recipes\". Its value
must be an array containing exactly {count} recipes. Do not use Markdown, comments,
code fences, prose outside JSON, or additional object fields.

DATASET SEGMENT: {self.segment.value}
RECIPE CATEGORY: {category.value}
SEGMENT RULES: {_SEGMENT_RULES[self.segment]}
{retry_note}

CONTENT RULES:
1. Produce distinct, realistic recipes that a normal household can cook.
2. Do not invent historical, regional, medical, detox, disease-treatment, or
   guaranteed nutrition claims.
3. Use only canonical ingredient names from CONTROLLED_INGREDIENT_NAMES below.
   RawIngredient.name and every RawStep.ingredient_names entry must match exactly.
4. Every non-to_taste quantity needs quantity_min. Required ingredients must be
   referenced by at least one step. Step orders start at 1 and are continuous.
5. total_minutes must be at least prep_minutes + cook_minutes. Step durations,
   heat, temperature, method, and required equipment must be realistic.
6. Equipment and every tag/method/unit must use only enum values allowed by schema.
7. If nutrition is uncertain, use null for numeric nutrition fields and UNKNOWN
   for protein_level/fat_level. Never fabricate precision.
8. Set aliases to an empty array unless a genuine common dish alias is certain.
9. Avoid all recipe names in AVOID_RECIPE_NAMES and avoid near-identical ingredient
   sets and cooking steps within this batch.
10. Each source object must use source_type AI_SYNTHETIC, source_name
    {self.version}, license AI-GENERATED-REVIEW-REQUIRED, source_url null,
    reliability_score 0.5, and a unique source_record_id beginning with
    {self.source_record_prefix}. Omit source.imported_at, source.generator_model,
    and source.dataset_version entirely; the trusted pipeline writes those fields.
    Never emit null for imported_at. Human review is performed later by the pipeline.
11. Keep output compact but complete: use 3-8 ingredients, 3-5 executable steps,
    and concise instructions. Keep substitutes empty unless genuinely useful,
    aliases empty unless certain, optional equipment minimal, and JSON whitespace
    minimal. Do not add narrative detail merely to make the output longer.
12. Put QUICK_MEAL, HEALTHY_MEAL, BEGINNER_FRIENDLY, and AIR_FRYER only in
    tags.scenario. Never put scenario values in tags.health; tags.health permits
    only BALANCED, HIGH_PROTEIN, LOW_FAT, and HIGH_FIBER.

CONTROLLED_INGREDIENT_NAMES:
{canonical_names}

AVOID_RECIPE_NAMES:
{avoid_names}

RAW RECIPE INGESTION JSON SCHEMA:
{schema}
"""
