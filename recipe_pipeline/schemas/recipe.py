"""Strict Recipe Schema v1 and the normalized raw-input contract."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)


NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Region(str, Enum):
    CHINESE_HOME = "CHINESE_HOME"
    SICHUAN = "SICHUAN"
    CANTONESE = "CANTONESE"
    OTHER_CHINESE = "OTHER_CHINESE"
    GLOBAL_HOME = "GLOBAL_HOME"
    UNSPECIFIED = "UNSPECIFIED"


class Cuisine(str, Enum):
    CHINESE = "CHINESE"
    OTHER_ASIAN = "OTHER_ASIAN"
    WESTERN = "WESTERN"
    FUSION = "FUSION"
    UNSPECIFIED = "UNSPECIFIED"


class RecipeCategory(str, Enum):
    MAIN_DISH = "MAIN_DISH"
    SIDE_DISH = "SIDE_DISH"
    SOUP = "SOUP"
    STAPLE = "STAPLE"
    BREAKFAST = "BREAKFAST"
    SNACK = "SNACK"
    DESSERT = "DESSERT"


class IngredientRole(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    GARNISH = "GARNISH"


class IngredientImportance(str, Enum):
    CORE = "CORE"
    SUPPORTING = "SUPPORTING"
    PANTRY = "PANTRY"


class Unit(str, Enum):
    GRAM = "g"
    KILOGRAM = "kg"
    MILLILITER = "ml"
    LITER = "l"
    PIECE = "piece"
    TABLESPOON = "tbsp"
    TEASPOON = "tsp"
    CUP = "cup"
    PINCH = "pinch"
    TO_TASTE = "to_taste"


class StepPhase(str, Enum):
    PREP = "PREP"
    COOK = "COOK"
    FINISH = "FINISH"


class CookingMethod(str, Enum):
    PREPARE = "PREPARE"
    MIX = "MIX"
    STIR_FRY = "STIR_FRY"
    PAN_FRY = "PAN_FRY"
    BOIL = "BOIL"
    SIMMER = "SIMMER"
    STEAM = "STEAM"
    BAKE = "BAKE"
    ROAST = "ROAST"
    AIR_FRY = "AIR_FRY"


class HeatLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EquipmentName(str, Enum):
    KNIFE = "KNIFE"
    CUTTING_BOARD = "CUTTING_BOARD"
    BOWL = "BOWL"
    WOK = "WOK"
    PAN = "PAN"
    POT = "POT"
    STEAMER = "STEAMER"
    OVEN = "OVEN"
    AIR_FRYER = "AIR_FRYER"
    RICE_COOKER = "RICE_COOKER"


class NutritionLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class DietaryTag(str, Enum):
    VEGETARIAN = "VEGETARIAN"
    VEGAN = "VEGAN"
    GLUTEN_FREE = "GLUTEN_FREE"
    DAIRY_FREE = "DAIRY_FREE"


class HealthTag(str, Enum):
    BALANCED = "BALANCED"
    HIGH_PROTEIN = "HIGH_PROTEIN"
    LOW_FAT = "LOW_FAT"
    HIGH_FIBER = "HIGH_FIBER"


class ScenarioTag(str, Enum):
    QUICK_MEAL = "QUICK_MEAL"
    FAMILY_MEAL = "FAMILY_MEAL"
    STUDENT_COOKING = "STUDENT_COOKING"
    AIR_FRYER = "AIR_FRYER"
    ONE_POT = "ONE_POT"
    BEGINNER_FRIENDLY = "BEGINNER_FRIENDLY"
    HEALTHY_MEAL = "HEALTHY_MEAL"


class AllergenTag(str, Enum):
    EGG = "EGG"
    MILK = "MILK"
    PEANUT = "PEANUT"
    TREE_NUT = "TREE_NUT"
    SOY = "SOY"
    WHEAT = "WHEAT"
    FISH = "FISH"
    SHELLFISH = "SHELLFISH"
    SESAME = "SESAME"


class SourceType(str, Enum):
    PUBLIC_DATASET = "PUBLIC_DATASET"
    MANUAL = "MANUAL"
    AI_SYNTHETIC = "AI_SYNTHETIC"


class RecipeStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"


class Identity(StrictModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]
    aliases: list[ShortText] = Field(default_factory=list, max_length=20)
    language: Literal["zh-CN", "en"] = "zh-CN"
    region: Region
    cuisine: Cuisine
    category: RecipeCategory
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=600)]

    @field_validator("aliases")
    @classmethod
    def unique_aliases(cls, aliases: list[str]) -> list[str]:
        keys = [alias.casefold() for alias in aliases]
        if len(keys) != len(set(keys)):
            raise ValueError("aliases must be unique")
        return aliases


class Serving(StrictModel):
    min_servings: int = Field(ge=1, le=100)
    max_servings: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def validate_range(self) -> "Serving":
        if self.max_servings < self.min_servings:
            raise ValueError("max_servings must be at least min_servings")
        return self


class RecipeTime(StrictModel):
    prep_minutes: int = Field(ge=0, le=1_440)
    cook_minutes: int = Field(ge=0, le=1_440)
    inactive_minutes: int = Field(default=0, ge=0, le=10_080)
    total_minutes: int = Field(ge=1, le=10_080)

    @model_validator(mode="after")
    def validate_total(self) -> "RecipeTime":
        if self.total_minutes < self.prep_minutes + self.cook_minutes:
            raise ValueError("total_minutes cannot be less than prep + cook")
        return self


class Difficulty(StrictModel):
    level: int = Field(ge=1, le=5)
    reasons: list[ShortText] = Field(default_factory=list, max_length=10)


class Quantity(StrictModel):
    minimum: float | None = Field(default=None, ge=0, le=100_000)
    maximum: float | None = Field(default=None, ge=0, le=100_000)
    unit: Unit

    @model_validator(mode="after")
    def validate_range(self) -> "Quantity":
        if self.minimum is not None and self.maximum is not None:
            if self.maximum < self.minimum:
                raise ValueError("quantity maximum must be at least minimum")
        if self.unit != Unit.TO_TASTE and self.minimum is None:
            raise ValueError("a numeric minimum is required unless unit is to_taste")
        return self


class RecipeIngredient(StrictModel):
    ingredient_id: UUID
    display_name: ShortText
    normalized_name: ShortText
    role: IngredientRole
    importance: IngredientImportance
    requirement_group: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    ]
    quantity: Quantity
    preparation: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=200),
    ] = ""


class IngredientSubstitute(StrictModel):
    recipe_ingredient_id: UUID
    substitute_ingredient_id: UUID
    ratio: float = Field(default=1.0, gt=0, le=20)
    penalty: float = Field(default=0.1, ge=0, le=1)
    note: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    ]


class RecipeStep(StrictModel):
    order: int = Field(ge=1, le=200)
    phase: StepPhase
    instruction: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=5, max_length=1_500),
    ]
    duration_minutes: int = Field(ge=0, le=1_440)
    method: CookingMethod
    heat_level: HeatLevel
    temperature_celsius: float | None = Field(default=None, ge=0, le=500)
    ingredient_refs: list[UUID] = Field(default_factory=list, max_length=100)
    equipment_refs: list[EquipmentName] = Field(default_factory=list, max_length=30)
    safety_note: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=500),
    ] | None = None


class Equipment(StrictModel):
    required: list[EquipmentName] = Field(default_factory=list, max_length=30)
    optional: list[EquipmentName] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def disjoint_sets(self) -> "Equipment":
        if set(self.required) & set(self.optional):
            raise ValueError("equipment cannot be both required and optional")
        return self


class TasteProfile(StrictModel):
    spicy: int = Field(ge=0, le=5)
    sweet: int = Field(ge=0, le=5)
    sour: int = Field(ge=0, le=5)
    salty: int = Field(ge=0, le=5)
    umami: int = Field(ge=0, le=5)
    richness: int = Field(ge=0, le=5)


class Nutrition(StrictModel):
    basis: Literal["PER_SERVING"] = "PER_SERVING"
    calories_kcal: float | None = Field(default=None, ge=0, le=3_000)
    protein_g: float | None = Field(default=None, ge=0, le=500)
    fat_g: float | None = Field(default=None, ge=0, le=500)
    carbohydrate_g: float | None = Field(default=None, ge=0, le=1_000)
    protein_level: NutritionLevel
    fat_level: NutritionLevel


class RecipeTags(StrictModel):
    dietary: list[DietaryTag] = Field(default_factory=list, max_length=30)
    health: list[HealthTag] = Field(default_factory=list, max_length=30)
    scenario: list[ScenarioTag] = Field(default_factory=list, max_length=30)
    technique: list[CookingMethod] = Field(default_factory=list, max_length=30)
    allergens: list[AllergenTag] = Field(default_factory=list, max_length=30)


class SourceMetadata(StrictModel):
    source_type: SourceType
    source_name: ShortText
    source_record_id: ShortText
    license: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
    ] | None = None
    source_url: HttpUrl | None = None
    reliability_score: float = Field(ge=0, le=1)
    generator_model: ShortText | None = None
    dataset_version: ShortText | None = None
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QualityMetadata(StrictModel):
    status: RecipeStatus = RecipeStatus.DRAFT
    confidence_score: float = Field(default=0, ge=0, le=1)
    human_reviewed: bool = False
    content_hash: Annotated[
        str,
        StringConstraints(pattern=r"^[0-9a-f]{64}$"),
    ] | None = None


class RecipeV1(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    recipe_id: UUID
    identity: Identity
    serving: Serving
    time: RecipeTime
    difficulty: Difficulty
    ingredients: list[RecipeIngredient] = Field(min_length=1, max_length=200)
    substitutes: list[IngredientSubstitute] = Field(default_factory=list, max_length=100)
    steps: list[RecipeStep] = Field(min_length=1, max_length=200)
    equipment: Equipment
    taste_profile: TasteProfile
    nutrition: Nutrition
    tags: RecipeTags
    source: SourceMetadata
    quality: QualityMetadata = Field(default_factory=QualityMetadata)

    @model_validator(mode="after")
    def validate_core_structure(self) -> "RecipeV1":
        if not any(item.role == IngredientRole.REQUIRED for item in self.ingredients):
            raise ValueError("at least one required ingredient is needed")
        ingredient_ids = [item.ingredient_id for item in self.ingredients]
        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise ValueError("ingredients must use unique canonical IDs")
        return self


class RawIngredient(InputModel):
    name: ShortText
    display_name: ShortText | None = None
    role: IngredientRole = IngredientRole.REQUIRED
    importance: IngredientImportance = IngredientImportance.SUPPORTING
    requirement_group: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    ] = "default"
    quantity_min: float | None = Field(default=None, ge=0, le=100_000)
    quantity_max: float | None = Field(default=None, ge=0, le=100_000)
    unit: Unit
    preparation: Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=200),
    ] = ""


class RawStep(InputModel):
    order: int = Field(ge=1, le=200)
    phase: StepPhase
    instruction: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=5, max_length=1_500),
    ]
    duration_minutes: int = Field(ge=0, le=1_440)
    method: CookingMethod
    heat_level: HeatLevel = HeatLevel.NONE
    temperature_celsius: float | None = Field(default=None, ge=0, le=500)
    ingredient_names: list[ShortText] = Field(default_factory=list, max_length=100)
    equipment_refs: list[EquipmentName] = Field(default_factory=list, max_length=30)
    safety_note: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=500),
    ] | None = None


class RawRecipe(InputModel):
    recipe_id: UUID | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=160)]
    aliases: list[ShortText] = Field(default_factory=list, max_length=20)
    language: Literal["zh-CN", "en"] = "zh-CN"
    region: Region
    cuisine: Cuisine
    category: RecipeCategory
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=600)]
    min_servings: int = Field(ge=1, le=100)
    max_servings: int = Field(ge=1, le=100)
    prep_minutes: int = Field(ge=0, le=1_440)
    cook_minutes: int = Field(ge=0, le=1_440)
    inactive_minutes: int = Field(default=0, ge=0, le=10_080)
    total_minutes: int = Field(ge=1, le=10_080)
    difficulty_level: int = Field(ge=1, le=5)
    difficulty_reasons: list[ShortText] = Field(default_factory=list, max_length=10)
    ingredients: list[RawIngredient] = Field(min_length=1, max_length=200)
    steps: list[RawStep] = Field(min_length=1, max_length=200)
    equipment_required: list[EquipmentName] = Field(default_factory=list, max_length=30)
    equipment_optional: list[EquipmentName] = Field(default_factory=list, max_length=30)
    taste_profile: TasteProfile
    nutrition: Nutrition
    tags: RecipeTags
    source: SourceMetadata
