"""Small deterministic demo generator used by tests and the 10-record sample run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from recipe_pipeline.schemas.recipe import (
    AllergenTag,
    CookingMethod,
    Cuisine,
    DietaryTag,
    EquipmentName,
    HealthTag,
    HeatLevel,
    IngredientImportance,
    IngredientRole,
    Nutrition,
    NutritionLevel,
    RawIngredient,
    RawRecipe,
    RawStep,
    RecipeCategory,
    RecipeTags,
    Region,
    ScenarioTag,
    SourceMetadata,
    SourceType,
    StepPhase,
    TasteProfile,
    Unit,
)


@dataclass(frozen=True, slots=True)
class _FixtureSpec:
    slug: str
    name: str
    first: str
    second: str
    summary: str
    cook_instruction: str
    protein_level: NutritionLevel = NutritionLevel.MEDIUM
    allergen: AllergenTag | None = None


_SPECS = (
    _FixtureSpec(
        "tomato-egg",
        "离线测试·番茄炒鸡蛋",
        "番茄",
        "鸡蛋",
        "用于验证管线的家常番茄炒鸡蛋测试记录，并非正式发布食谱。",
        "锅中放油，中火先炒熟鸡蛋，再加入番茄翻炒至出汁并用盐调味。",
        NutritionLevel.HIGH,
        AllergenTag.EGG,
    ),
    _FixtureSpec(
        "chicken-potato",
        "离线测试·鸡肉烧土豆",
        "鸡肉",
        "土豆",
        "用于验证管线的鸡肉土豆家庭餐测试记录，并非正式发布食谱。",
        "锅中放油，中火将鸡肉完全炒至变色，加入土豆和水煮至鸡肉熟透。",
        NutritionLevel.HIGH,
    ),
    _FixtureSpec(
        "tofu-spinach",
        "离线测试·菠菜烧豆腐",
        "豆腐",
        "菠菜",
        "用于验证管线的清淡豆腐菠菜测试记录，并非正式发布食谱。",
        "锅中放油，中火加入豆腐和菠菜轻轻翻炒，加入盐并烧至菠菜熟软。",
        NutritionLevel.MEDIUM,
        AllergenTag.SOY,
    ),
    _FixtureSpec(
        "carrot-egg",
        "离线测试·胡萝卜炒蛋",
        "胡萝卜",
        "鸡蛋",
        "用于验证管线的胡萝卜鸡蛋快手菜测试记录，并非正式发布食谱。",
        "锅中放油，中火炒软胡萝卜，再加入鸡蛋翻炒至完全凝固并用盐调味。",
        NutritionLevel.HIGH,
        AllergenTag.EGG,
    ),
    _FixtureSpec(
        "broccoli-chicken",
        "离线测试·西兰花炒鸡肉",
        "西兰花",
        "鸡肉",
        "用于验证管线的西兰花鸡肉健康餐测试记录，并非正式发布食谱。",
        "锅中放油，中火将鸡肉炒至完全熟透，加入西兰花翻炒至断生并用盐调味。",
        NutritionLevel.HIGH,
    ),
    _FixtureSpec(
        "onion-egg",
        "离线测试·洋葱炒鸡蛋",
        "洋葱",
        "鸡蛋",
        "用于验证管线的洋葱鸡蛋学生餐测试记录，并非正式发布食谱。",
        "锅中放油，中火炒软洋葱，加入鸡蛋翻炒至完全凝固并用盐调味。",
        NutritionLevel.HIGH,
        AllergenTag.EGG,
    ),
    _FixtureSpec(
        "tomato-tofu",
        "离线测试·番茄烧豆腐",
        "番茄",
        "豆腐",
        "用于验证管线的番茄豆腐一锅菜测试记录，并非正式发布食谱。",
        "锅中放油，中火炒出番茄汁，加入豆腐和水煮透并用盐调味。",
        NutritionLevel.MEDIUM,
        AllergenTag.SOY,
    ),
    _FixtureSpec(
        "potato-carrot",
        "离线测试·土豆胡萝卜煮",
        "土豆",
        "胡萝卜",
        "用于验证管线的土豆胡萝卜家庭餐测试记录，并非正式发布食谱。",
        "锅中放油略炒土豆和胡萝卜，加入水用中火煮至软熟并用盐调味。",
        NutritionLevel.LOW,
    ),
    _FixtureSpec(
        "spinach-egg",
        "离线测试·菠菜炒鸡蛋",
        "菠菜",
        "鸡蛋",
        "用于验证管线的菠菜鸡蛋早餐菜测试记录，并非正式发布食谱。",
        "锅中放油，中火炒软菠菜，加入鸡蛋翻炒至完全凝固并用盐调味。",
        NutritionLevel.HIGH,
        AllergenTag.EGG,
    ),
    _FixtureSpec(
        "broccoli-tofu",
        "离线测试·西兰花烧豆腐",
        "西兰花",
        "豆腐",
        "用于验证管线的西兰花豆腐清淡餐测试记录，并非正式发布食谱。",
        "锅中放油，中火加入西兰花和豆腐翻炒，加少量水烧透并用盐调味。",
        NutritionLevel.MEDIUM,
        AllergenTag.SOY,
    ),
)


class FixtureRecipeGenerator:
    """Produces at most ten records marked as low-reliability synthetic test data."""

    def generate_recipe_batch(
        self, category: RecipeCategory, count: int
    ) -> list[RawRecipe]:
        if not 1 <= count <= 10:
            raise ValueError("fixture count must be between 1 and 10")
        return [self._build(spec, category) for spec in _SPECS[:count]]

    @staticmethod
    def _build(spec: _FixtureSpec, category: RecipeCategory) -> RawRecipe:
        allergens = [spec.allergen] if spec.allergen else []
        dietary = []
        if spec.first not in {"鸡肉"} and spec.second not in {"鸡肉"}:
            dietary.append(DietaryTag.VEGETARIAN)
        return RawRecipe(
            name=spec.name,
            aliases=[],
            region=Region.CHINESE_HOME,
            cuisine=Cuisine.CHINESE,
            category=category,
            summary=spec.summary,
            min_servings=2,
            max_servings=2,
            prep_minutes=8,
            cook_minutes=12,
            total_minutes=20,
            difficulty_level=1,
            difficulty_reasons=["步骤少且只使用常见锅具"],
            ingredients=[
                RawIngredient(
                    name=spec.first,
                    role=IngredientRole.REQUIRED,
                    importance=IngredientImportance.CORE,
                    quantity_min=200,
                    unit=Unit.GRAM,
                ),
                RawIngredient(
                    name=spec.second,
                    role=IngredientRole.REQUIRED,
                    importance=IngredientImportance.CORE,
                    quantity_min=150,
                    unit=Unit.GRAM,
                ),
                RawIngredient(
                    name="食用油",
                    role=IngredientRole.OPTIONAL,
                    importance=IngredientImportance.PANTRY,
                    quantity_min=1,
                    unit=Unit.TABLESPOON,
                ),
                RawIngredient(
                    name="盐",
                    role=IngredientRole.OPTIONAL,
                    importance=IngredientImportance.PANTRY,
                    unit=Unit.TO_TASTE,
                ),
            ],
            steps=[
                RawStep(
                    order=1,
                    phase=StepPhase.PREP,
                    instruction=f"将{spec.first}和{spec.second}清洗处理好，分别放置备用。",
                    duration_minutes=8,
                    method=CookingMethod.PREPARE,
                    ingredient_names=[spec.first, spec.second],
                    equipment_refs=[EquipmentName.KNIFE, EquipmentName.CUTTING_BOARD],
                ),
                RawStep(
                    order=2,
                    phase=StepPhase.COOK,
                    instruction=spec.cook_instruction,
                    duration_minutes=12,
                    method=CookingMethod.STIR_FRY,
                    heat_level=HeatLevel.MEDIUM,
                    ingredient_names=[spec.first, spec.second, "食用油", "盐"],
                    equipment_refs=[EquipmentName.WOK],
                    safety_note="肉类和蛋类必须充分加热至熟透后再食用。"
                    if spec.first in {"鸡肉", "鸡蛋"} or spec.second in {"鸡肉", "鸡蛋"}
                    else "烹饪时注意热油和蒸汽，避免烫伤。",
                ),
            ],
            equipment_required=[
                EquipmentName.KNIFE,
                EquipmentName.CUTTING_BOARD,
                EquipmentName.WOK,
            ],
            taste_profile=TasteProfile(
                spicy=0,
                sweet=1,
                sour=1 if "番茄" in {spec.first, spec.second} else 0,
                salty=2,
                umami=2,
                richness=1,
            ),
            nutrition=Nutrition(
                calories_kcal=320,
                protein_g=24 if spec.protein_level == NutritionLevel.HIGH else 14,
                fat_g=12,
                carbohydrate_g=28,
                protein_level=spec.protein_level,
                fat_level=NutritionLevel.MEDIUM,
            ),
            tags=RecipeTags(
                dietary=dietary,
                health=[HealthTag.BALANCED],
                scenario=[
                    ScenarioTag.QUICK_MEAL,
                    ScenarioTag.BEGINNER_FRIENDLY,
                ],
                technique=[CookingMethod.STIR_FRY],
                allergens=allergens,
            ),
            source=SourceMetadata(
                source_type=SourceType.AI_SYNTHETIC,
                source_name="offline_demo_fixture",
                source_record_id=spec.slug,
                license="TEST-ONLY-NOT-FOR-PRODUCTION",
                reliability_score=0.4,
                imported_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        )
