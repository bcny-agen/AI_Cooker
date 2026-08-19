"""Contracts that keep canonical content separate from enrichment and audit."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from recipe_pipeline.schemas.recipe import (
    CookingMethod,
    Cuisine,
    EquipmentName,
    RawIngredient,
    RawStep,
    RecipeCategory,
    Region,
)


CANONICAL_GENERATOR_PROMPT_VERSION = "canonical_recipe_generator_v1"
SEMANTIC_AUDITOR_PROMPT_VERSION = "recipe_semantic_auditor_v1"
GOLDEN_DATASET_VERSION = "golden_recipe_dataset_v1"
GOLDEN_GENERATOR_MODEL = "gpt-5.6-sol"


class PrimaryCollection(str, Enum):
    CHINESE_HOME = "CHINESE_HOME"
    QUICK_EVERYDAY = "QUICK_EVERYDAY"
    BEGINNER_FRIENDLY = "BEGINNER_FRIENDLY"
    FAMILY_ONE_POT = "FAMILY_ONE_POT"
    HEALTHY_LIGHT = "HEALTHY_LIGHT"
    AIR_FRYER_APPLIANCE = "AIR_FRYER_APPLIANCE"
    OTHER_HOUSEHOLD = "OTHER_HOUSEHOLD"


class AuditDecision(str, Enum):
    PASS = "AUDIT_PASSED"
    FLAG = "FLAGGED"
    REJECT = "REJECTED"


class CanonicalRecipeContent(BaseModel):
    """Reliable cooking content only; no taste, claims, nutrition, or quality."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    collection: PrimaryCollection
    style: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    language: str = "zh-CN"
    region: Region
    cuisine: Cuisine
    category: RecipeCategory
    min_servings: int
    max_servings: int
    prep_minutes: int
    cook_minutes: int
    total_minutes: int
    ingredients: list[RawIngredient]
    steps: list[RawStep]
    equipment_required: list[EquipmentName]
    equipment_optional: list[EquipmentName] = Field(default_factory=list)


class GoldenBlueprint(BaseModel):
    """Codex-authored canonical recipe plan consumed in bounded batches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    collection: PrimaryCollection
    style: str
    ingredients: tuple[str, ...]
    method: CookingMethod
    category: RecipeCategory
    total_minutes: int = Field(ge=5, le=240)


class SemanticAuditItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe_id: str
    recipe_name: str
    decision: AuditDecision
    score: float = Field(ge=0, le=1)
    issue_codes: list[str]
    reasons: list[str]
    safety_sensitive: bool
    prompt_version: str = SEMANTIC_AUDITOR_PROMPT_VERSION


class DuplicateReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_recipe_id: str
    right_recipe_id: str
    left_name: str
    right_name: str
    name_similarity: float
    core_ingredient_jaccard: float
    method_similarity: float
    step_similarity: float
    decision: str
    reason: str
