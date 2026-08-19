"""Codex-authored first-batch seeds exposed through RecipeBatchGenerator."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from recipe_pipeline.generation.batch import GenerationJob
from recipe_pipeline.generation.prompt import (
    DatasetSegment,
    RECIPE_GENERATION_PROMPT_VERSION,
)
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


CODEX_GENERATION_PROVIDER = "codex-direct"
CODEX_GENERATION_MODEL = "gpt-5.6-sol"


@dataclass(frozen=True, slots=True)
class _RecipeSeed:
    name: str
    ingredients: tuple[str, ...]
    method: CookingMethod
    total_minutes: int = 30


def _seed(
    name: str,
    ingredients: tuple[str, ...],
    method: CookingMethod = CookingMethod.STIR_FRY,
    total_minutes: int = 30,
) -> _RecipeSeed:
    return _RecipeSeed(name, ingredients, method, total_minutes)


_SEEDS: dict[DatasetSegment, tuple[_RecipeSeed, ...]] = {
    DatasetSegment.CHINESE_HOME: (
        _seed("青椒炒猪肉", ("猪肉", "青椒", "小葱", "生抽")),
        _seed("芹菜炒牛肉", ("牛肉", "芹菜", "姜", "生抽")),
        _seed("番茄鸡蛋豆腐煲", ("番茄", "鸡蛋", "豆腐", "水"), CookingMethod.SIMMER, 35),
        _seed("土豆烧鸡腿", ("土豆", "鸡腿", "姜", "生抽", "水"), CookingMethod.SIMMER, 40),
        _seed("香菇蒸鸡肉", ("香菇", "鸡肉", "姜", "生抽"), CookingMethod.STEAM, 35),
        _seed("莲藕炒猪肉", ("莲藕", "猪肉", "青椒")),
        _seed("白菜炖豆腐", ("白菜", "豆腐", "水"), CookingMethod.SIMMER, 35),
        _seed("西葫芦炒鸡蛋", ("西葫芦", "鸡蛋"), total_minutes=20),
        _seed("茄子烧豆角", ("茄子", "豆角", "生抽", "水"), CookingMethod.SIMMER, 35),
        _seed("冬瓜虾仁汤", ("冬瓜", "虾", "水", "姜"), CookingMethod.BOIL, 30),
        _seed("胡萝卜土豆炖牛肉", ("胡萝卜", "土豆", "牛肉", "水"), CookingMethod.SIMMER, 50),
        _seed("菠菜豆腐汤", ("菠菜", "豆腐", "水"), CookingMethod.BOIL, 25),
        _seed("菜花炒猪肉", ("菜花", "猪肉", "小葱")),
        _seed("香菇白菜炒豆腐", ("香菇", "白菜", "豆腐")),
        _seed("白萝卜炖鸡肉", ("白萝卜", "鸡肉", "姜", "水"), CookingMethod.SIMMER, 45),
        _seed("南瓜蒸鸡蛋", ("南瓜", "鸡蛋", "水"), CookingMethod.STEAM, 30),
        _seed("青椒土豆丝", ("青椒", "土豆", "醋"), total_minutes=25),
        _seed("洋葱炒牛肉", ("洋葱", "牛肉", "黑胡椒")),
        _seed("西兰花炒虾仁", ("西兰花", "虾", "大蒜")),
        _seed("芹菜香菇炒豆腐", ("芹菜", "香菇", "豆腐")),
        _seed("番茄土豆炖牛肉", ("番茄", "土豆", "牛肉", "水"), CookingMethod.SIMMER, 50),
        _seed("黄瓜炒鸡蛋", ("黄瓜", "鸡蛋"), total_minutes=20),
        _seed("韭菜炒鸡蛋", ("韭菜", "鸡蛋"), total_minutes=20),
        _seed("豆芽炒猪肉", ("豆芽", "猪肉", "小葱"), total_minutes=25),
        _seed("山药胡萝卜鸡汤", ("山药", "胡萝卜", "鸡肉", "水"), CookingMethod.SIMMER, 50),
        _seed("白菜猪肉炖豆腐", ("白菜", "猪肉", "豆腐", "水"), CookingMethod.SIMMER, 40),
        _seed("莲藕胡萝卜炖猪肉", ("莲藕", "胡萝卜", "猪肉", "水"), CookingMethod.SIMMER, 50),
        _seed("茄子番茄烧豆腐", ("茄子", "番茄", "豆腐", "水"), CookingMethod.SIMMER, 35),
        _seed("豌豆胡萝卜炒鸡肉", ("豌豆", "胡萝卜", "鸡肉")),
        _seed("玉米胡萝卜鸡肉汤", ("玉米", "胡萝卜", "鸡肉", "水"), CookingMethod.BOIL, 40),
        _seed("紫菜鸡蛋汤", ("紫菜", "鸡蛋", "水"), CookingMethod.BOIL, 20),
        _seed("海带豆腐汤", ("海带", "豆腐", "水"), CookingMethod.BOIL, 30),
        _seed("菜花番茄炒鸡蛋", ("菜花", "番茄", "鸡蛋")),
        _seed("豆角土豆炖鸡肉", ("豆角", "土豆", "鸡肉", "水"), CookingMethod.SIMMER, 45),
        _seed("香菇洋葱炒猪肉", ("香菇", "洋葱", "猪肉")),
        _seed("西兰花胡萝卜炒牛肉", ("西兰花", "胡萝卜", "牛肉")),
        _seed("白萝卜香菇炖鸡肉", ("白萝卜", "香菇", "鸡肉", "水"), CookingMethod.SIMMER, 45),
        _seed("菠菜香菇炒鸡蛋", ("菠菜", "香菇", "鸡蛋")),
        _seed("毛豆炒鸡肉", ("毛豆", "鸡肉", "彩椒")),
        _seed("南瓜烧豆腐", ("南瓜", "豆腐", "水"), CookingMethod.SIMMER, 35),
    ),
    DatasetSegment.QUICK_MEALS: (
        _seed("番茄鸡蛋面", ("番茄", "鸡蛋", "面条", "水"), CookingMethod.BOIL, 20),
        _seed("菠菜鸡蛋面", ("菠菜", "鸡蛋", "面条", "水"), CookingMethod.BOIL, 20),
        _seed("洋葱鸡蛋炒饭", ("洋葱", "鸡蛋", "米饭"), total_minutes=20),
        _seed("胡萝卜鸡肉炒饭", ("胡萝卜", "鸡肉", "米饭"), total_minutes=25),
        _seed("豌豆虾仁炒饭", ("豌豆", "虾", "米饭"), total_minutes=20),
        _seed("青椒鸡肉快炒", ("青椒", "鸡肉", "生抽"), total_minutes=20),
        _seed("豆芽鸡蛋快炒", ("豆芽", "鸡蛋", "小葱"), total_minutes=15),
        _seed("西兰花鸡蛋快炒", ("西兰花", "鸡蛋", "大蒜"), total_minutes=20),
        _seed("毛豆胡萝卜炒饭", ("毛豆", "胡萝卜", "米饭"), total_minutes=20),
        _seed("黄瓜鸡蛋炒饭", ("黄瓜", "鸡蛋", "米饭"), total_minutes=20),
        _seed("番茄豆腐快煮汤", ("番茄", "豆腐", "水"), CookingMethod.BOIL, 20),
        _seed("紫菜鸡蛋面", ("紫菜", "鸡蛋", "面条", "水"), CookingMethod.BOIL, 20),
        _seed("番茄虾仁面", ("番茄", "虾", "面条", "水"), CookingMethod.BOIL, 25),
        _seed("香菇豆腐盖饭", ("香菇", "豆腐", "米饭", "生抽"), CookingMethod.SIMMER, 25),
        _seed("黄瓜豆腐拌饭", ("黄瓜", "豆腐", "米饭", "芝麻油"), CookingMethod.MIX, 15),
        _seed("香蕉燕麦酸奶杯", ("香蕉", "燕麦", "酸奶"), CookingMethod.MIX, 10),
        _seed("苹果燕麦粥", ("苹果", "燕麦", "水"), CookingMethod.BOIL, 20),
        _seed("土豆洋葱鸡蛋饼", ("土豆", "洋葱", "鸡蛋", "面粉"), CookingMethod.PAN_FRY, 25),
        _seed("玉米鸡蛋早餐饼", ("玉米", "鸡蛋", "面粉"), CookingMethod.PAN_FRY, 20),
        _seed("牛奶香蕉燕麦粥", ("牛奶", "香蕉", "燕麦"), CookingMethod.BOIL, 15),
    ),
    DatasetSegment.HEALTHY_MEALS: (
        _seed("西兰花清炒鸡肉", ("西兰花", "鸡肉", "大蒜"), total_minutes=25),
        _seed("三文鱼南瓜烤盘", ("三文鱼", "南瓜", "柠檬"), CookingMethod.ROAST, 35),
        _seed("鹰嘴豆黄瓜番茄沙拉", ("鹰嘴豆", "黄瓜", "番茄", "柠檬"), CookingMethod.MIX, 15),
        _seed("菠菜毛豆豆腐煮", ("菠菜", "毛豆", "豆腐", "水"), CookingMethod.BOIL, 25),
        _seed("冬瓜鸡肉清汤", ("冬瓜", "鸡肉", "水", "姜"), CookingMethod.BOIL, 35),
        _seed("白萝卜鱼汤", ("白萝卜", "鱼", "水", "姜"), CookingMethod.BOIL, 35),
        _seed("香菇西兰花蒸豆腐", ("香菇", "西兰花", "豆腐", "水"), CookingMethod.STEAM, 30),
        _seed("山药玉米鸡肉汤", ("山药", "玉米", "鸡肉", "水"), CookingMethod.SIMMER, 45),
        _seed("芹菜胡萝卜炒牛肉", ("芹菜", "胡萝卜", "牛肉"), total_minutes=25),
        _seed("西葫芦虾仁快炒", ("西葫芦", "虾", "大蒜"), total_minutes=20),
        _seed("南瓜燕麦粥", ("南瓜", "燕麦", "水"), CookingMethod.BOIL, 25),
        _seed("苹果酸奶燕麦杯", ("苹果", "酸奶", "燕麦"), CookingMethod.MIX, 10),
        _seed("莲藕毛豆拌菜", ("莲藕", "毛豆", "醋", "芝麻油"), CookingMethod.MIX, 25),
        _seed("白菜香菇豆腐汤", ("白菜", "香菇", "豆腐", "水"), CookingMethod.BOIL, 30),
        _seed("菜花鹰嘴豆煮", ("菜花", "鹰嘴豆", "番茄", "水"), CookingMethod.SIMMER, 30),
    ),
    DatasetSegment.BEGINNER_COOKING: (
        _seed("番茄洋葱炒鸡蛋", ("番茄", "洋葱", "鸡蛋"), total_minutes=20),
        _seed("土豆胡萝卜焖饭", ("土豆", "胡萝卜", "米饭", "水"), CookingMethod.SIMMER, 30),
        _seed("鸡蛋蒸豆腐", ("鸡蛋", "豆腐", "水"), CookingMethod.STEAM, 25),
        _seed("黄瓜鸡蛋汤", ("黄瓜", "鸡蛋", "水"), CookingMethod.BOIL, 20),
        _seed("白菜豆腐家常煮", ("白菜", "豆腐", "胡萝卜", "水"), CookingMethod.BOIL, 25),
        _seed("玉米胡萝卜炒鸡蛋", ("玉米", "胡萝卜", "鸡蛋"), total_minutes=20),
        _seed("南瓜牛奶燕麦粥", ("南瓜", "牛奶", "燕麦"), CookingMethod.BOIL, 20),
        _seed("洋葱土豆煎饼", ("洋葱", "土豆", "面粉"), CookingMethod.PAN_FRY, 25),
        _seed("菠菜鸡蛋汤", ("菠菜", "鸡蛋", "水"), CookingMethod.BOIL, 20),
        _seed("西兰花胡萝卜炒豆腐", ("西兰花", "胡萝卜", "豆腐"), total_minutes=25),
        _seed("香蕉鸡蛋燕麦饼", ("香蕉", "鸡蛋", "燕麦"), CookingMethod.PAN_FRY, 20),
        _seed("苹果牛奶燕麦粥", ("苹果", "牛奶", "燕麦"), CookingMethod.BOIL, 20),
        _seed("玉米鸡蛋早餐杯", ("玉米", "鸡蛋", "奶酪"), CookingMethod.STEAM, 20),
        _seed("菠菜奶酪煎蛋", ("菠菜", "奶酪", "鸡蛋"), CookingMethod.PAN_FRY, 20),
        _seed("红薯酸奶燕麦碗", ("红薯", "酸奶", "燕麦"), CookingMethod.MIX, 25),
    ),
    DatasetSegment.AIR_FRYER_SIMPLE_TOOLS: (
        _seed("空气炸锅蜜汁鸡翅", ("鸡翅", "蜂蜜", "生抽"), CookingMethod.AIR_FRY, 30),
        _seed("空气炸锅黑椒土豆角", ("土豆", "黑胡椒"), CookingMethod.AIR_FRY, 25),
        _seed("空气炸锅柠檬三文鱼", ("三文鱼", "柠檬", "黑胡椒"), CookingMethod.AIR_FRY, 25),
        _seed("空气炸锅蒜香西兰花", ("西兰花", "大蒜", "黑胡椒"), CookingMethod.AIR_FRY, 20),
        _seed("空气炸锅椒盐南瓜", ("南瓜", "黑胡椒"), CookingMethod.AIR_FRY, 25),
        _seed("空气炸锅芝麻豆腐", ("豆腐", "生抽", "芝麻"), CookingMethod.AIR_FRY, 25),
        _seed("空气炸锅姜香鸡腿", ("鸡腿", "姜", "生抽"), CookingMethod.AIR_FRY, 35),
        _seed("空气炸锅红薯条", ("红薯", "黑胡椒"), CookingMethod.AIR_FRY, 25),
        _seed("空气炸锅咖喱菜花", ("菜花", "咖喱粉"), CookingMethod.AIR_FRY, 20),
        _seed("空气炸锅苹果燕麦杯", ("苹果", "燕麦", "蜂蜜"), CookingMethod.AIR_FRY, 20),
    ),
}


_COOKING_EQUIPMENT = {
    CookingMethod.MIX: EquipmentName.BOWL,
    CookingMethod.STIR_FRY: EquipmentName.WOK,
    CookingMethod.PAN_FRY: EquipmentName.PAN,
    CookingMethod.BOIL: EquipmentName.POT,
    CookingMethod.SIMMER: EquipmentName.POT,
    CookingMethod.STEAM: EquipmentName.STEAMER,
    CookingMethod.BAKE: EquipmentName.OVEN,
    CookingMethod.ROAST: EquipmentName.OVEN,
    CookingMethod.AIR_FRY: EquipmentName.AIR_FRYER,
}

_ANIMAL_PROTEINS = {"猪肉", "牛肉", "鸡肉", "鸡腿", "鸡翅", "虾", "鱼", "三文鱼"}
_EGG_DAIRY = {"鸡蛋", "牛奶", "酸奶", "奶酪"}
_SWEET_INGREDIENTS = {"苹果", "香蕉", "蜂蜜", "酸奶", "牛奶"}


class CodexSegmentRecipeBatchGenerator:
    """Implements RecipeBatchGenerator over the current session's authored seeds."""

    def __init__(
        self,
        *,
        segment: DatasetSegment,
        offset: int,
        run_id: str,
        imported_at: datetime,
    ):
        self._segment = segment
        self._offset = offset
        self._run_id = run_id
        self._imported_at = imported_at

    def generate_recipe_batch(
        self, category: RecipeCategory, count: int
    ) -> list[RawRecipe]:
        if not 1 <= count <= 10:
            raise ValueError("Codex batch count must be between 1 and 10")
        selected = _SEEDS[self._segment][self._offset : self._offset + count]
        if len(selected) != count:
            raise ValueError("Codex seed plan does not contain the requested batch")
        return [
            self._build_recipe(seed, category, self._offset + index)
            for index, seed in enumerate(selected, start=1)
        ]

    def _build_recipe(
        self,
        seed: _RecipeSeed,
        category: RecipeCategory,
        item_number: int,
    ) -> RawRecipe:
        ingredient_names = list(seed.ingredients)
        is_sweet = bool(set(ingredient_names) & _SWEET_INGREDIENTS) and not (
            set(ingredient_names) & _ANIMAL_PROTEINS
        )
        if seed.method in {CookingMethod.BOIL, CookingMethod.SIMMER, CookingMethod.STEAM}:
            if "水" not in ingredient_names:
                ingredient_names.append("水")
        if seed.method not in {CookingMethod.MIX, CookingMethod.BOIL} and not is_sweet:
            if "食用油" not in ingredient_names:
                ingredient_names.append("食用油")
        if not is_sweet and "盐" not in ingredient_names:
            ingredient_names.append("盐")

        equipment = _COOKING_EQUIPMENT[seed.method]
        prep_minutes = min(8, max(3, seed.total_minutes // 3))
        cook_minutes = seed.total_minutes - prep_minutes
        ingredient_models = [
            self._ingredient(name, required=index < len(seed.ingredients))
            for index, name in enumerate(ingredient_names)
        ]
        scenario = self._scenario_tags()
        dietary, allergens = self._dietary_and_allergens(set(ingredient_names))
        cooking_instruction, heat, temperature = self._cooking_instruction(
            seed, ingredient_names
        )
        safety_note = (
            "肉类、蛋类和水产食材应充分加热至熟透，并注意生熟器具分开。"
            if set(ingredient_names) & (_ANIMAL_PROTEINS | {"鸡蛋"})
            else "操作热锅、热水或热蒸汽时注意防烫，并保持器具清洁。"
        )
        record_id = (
            f"{self._run_id}-{self._segment.value.lower()}-{item_number:03d}"
        )
        return RawRecipe(
            name=seed.name,
            aliases=[],
            language="zh-CN",
            region=(
                Region.GLOBAL_HOME
                if self._segment == DatasetSegment.AIR_FRYER_SIMPLE_TOOLS
                else Region.CHINESE_HOME
            ),
            cuisine=(
                Cuisine.FUSION
                if self._segment == DatasetSegment.AIR_FRYER_SIMPLE_TOOLS
                else Cuisine.CHINESE
            ),
            category=category,
            summary=(
                f"一道以{'、'.join(seed.ingredients)}为主的实用家庭食谱，"
                f"采用{self._method_label(seed.method)}完成，步骤清楚且适合日常操作。"
            ),
            min_servings=2,
            max_servings=2,
            prep_minutes=prep_minutes,
            cook_minutes=cook_minutes,
            inactive_minutes=0,
            total_minutes=seed.total_minutes,
            difficulty_level=(
                1
                if self._segment
                in {
                    DatasetSegment.BEGINNER_COOKING,
                    DatasetSegment.AIR_FRYER_SIMPLE_TOOLS,
                }
                else 2
            ),
            difficulty_reasons=["使用常见食材和家庭厨具，步骤数量较少"],
            ingredients=ingredient_models,
            steps=[
                RawStep(
                    order=1,
                    phase=StepPhase.PREP,
                    instruction=(
                        f"准备{'、'.join(seed.ingredients)}，需要清洗的食材洗净，"
                        "按易熟程度切成大小均匀的块或片并分别放置。"
                    ),
                    duration_minutes=prep_minutes,
                    method=CookingMethod.PREPARE,
                    heat_level=HeatLevel.NONE,
                    ingredient_names=list(seed.ingredients),
                    equipment_refs=[
                        EquipmentName.KNIFE,
                        EquipmentName.CUTTING_BOARD,
                    ],
                ),
                RawStep(
                    order=2,
                    phase=(StepPhase.FINISH if seed.method == CookingMethod.MIX else StepPhase.COOK),
                    instruction=cooking_instruction,
                    duration_minutes=cook_minutes,
                    method=seed.method,
                    heat_level=heat,
                    temperature_celsius=temperature,
                    ingredient_names=ingredient_names,
                    equipment_refs=[equipment],
                    safety_note=safety_note,
                ),
            ],
            equipment_required=[
                EquipmentName.KNIFE,
                EquipmentName.CUTTING_BOARD,
                equipment,
            ],
            equipment_optional=[],
            taste_profile=self._taste_profile(set(ingredient_names)),
            nutrition=Nutrition(
                calories_kcal=None,
                protein_g=None,
                fat_g=None,
                carbohydrate_g=None,
                protein_level=NutritionLevel.UNKNOWN,
                fat_level=NutritionLevel.UNKNOWN,
            ),
            tags=RecipeTags(
                dietary=dietary,
                health=(
                    [HealthTag.BALANCED]
                    if self._segment == DatasetSegment.HEALTHY_MEALS
                    else []
                ),
                scenario=scenario,
                technique=[seed.method],
                allergens=allergens,
            ),
            source=SourceMetadata(
                source_type=SourceType.AI_SYNTHETIC,
                source_name=RECIPE_GENERATION_PROMPT_VERSION,
                source_record_id=record_id,
                license="AI-GENERATED-REVIEW-REQUIRED",
                source_url=None,
                reliability_score=0.5,
                imported_at=self._imported_at,
            ),
        )

    @staticmethod
    def _ingredient(name: str, *, required: bool) -> RawIngredient:
        if name == "盐":
            quantity_min, unit = None, Unit.TO_TASTE
        elif name == "水":
            quantity_min, unit = 600, Unit.MILLILITER
        elif name == "鸡蛋":
            quantity_min, unit = 2, Unit.PIECE
        elif name in {"鸡腿", "鸡翅", "苹果", "香蕉", "柠檬"}:
            quantity_min, unit = 2, Unit.PIECE
        elif name in {
            "食用油",
            "生抽",
            "老抽",
            "醋",
            "料酒",
            "芝麻油",
            "蚝油",
            "蜂蜜",
        }:
            quantity_min, unit = 1, Unit.TABLESPOON
        elif name in {
            "白糖",
            "黑胡椒",
            "淀粉",
            "豆瓣酱",
            "辣椒",
            "花椒",
            "咖喱粉",
            "番茄酱",
            "芝麻",
        }:
            quantity_min, unit = 1, Unit.TEASPOON
        elif name in {"牛奶", "酸奶"}:
            quantity_min, unit = 200, Unit.MILLILITER
        else:
            quantity_min, unit = 200, Unit.GRAM
        return RawIngredient(
            name=name,
            role=(IngredientRole.REQUIRED if required else IngredientRole.OPTIONAL),
            importance=(
                IngredientImportance.CORE
                if required
                else IngredientImportance.PANTRY
            ),
            requirement_group="default",
            quantity_min=quantity_min,
            unit=unit,
        )

    def _scenario_tags(self) -> list[ScenarioTag]:
        return {
            DatasetSegment.CHINESE_HOME: [ScenarioTag.FAMILY_MEAL],
            DatasetSegment.QUICK_MEALS: [
                ScenarioTag.QUICK_MEAL,
                ScenarioTag.STUDENT_COOKING,
            ],
            DatasetSegment.HEALTHY_MEALS: [ScenarioTag.HEALTHY_MEAL],
            DatasetSegment.BEGINNER_COOKING: [ScenarioTag.BEGINNER_FRIENDLY],
            DatasetSegment.AIR_FRYER_SIMPLE_TOOLS: [
                ScenarioTag.AIR_FRYER,
                ScenarioTag.BEGINNER_FRIENDLY,
            ],
        }[self._segment]

    @staticmethod
    def _dietary_and_allergens(
        ingredients: set[str],
    ) -> tuple[list[DietaryTag], list[AllergenTag]]:
        dietary = []
        if not ingredients & _ANIMAL_PROTEINS:
            dietary.append(DietaryTag.VEGETARIAN)
            if not ingredients & _EGG_DAIRY:
                dietary.append(DietaryTag.VEGAN)
        allergens = []
        allergen_rules = (
            (AllergenTag.EGG, {"鸡蛋"}),
            (AllergenTag.MILK, {"牛奶", "酸奶", "奶酪"}),
            (AllergenTag.SOY, {"豆腐", "生抽", "老抽", "豆瓣酱"}),
            (AllergenTag.WHEAT, {"面条", "面粉", "面包糠"}),
            (AllergenTag.FISH, {"鱼", "三文鱼"}),
            (AllergenTag.SHELLFISH, {"虾", "蚝油"}),
            (AllergenTag.SESAME, {"芝麻", "芝麻油"}),
        )
        for allergen, triggers in allergen_rules:
            if ingredients & triggers:
                allergens.append(allergen)
        return dietary, allergens

    @staticmethod
    def _taste_profile(ingredients: set[str]) -> TasteProfile:
        return TasteProfile(
            spicy=3 if ingredients & {"辣椒", "花椒", "豆瓣酱"} else 0,
            sweet=2 if ingredients & _SWEET_INGREDIENTS else 1,
            sour=2 if ingredients & {"醋", "柠檬", "番茄"} else 0,
            salty=1 if "盐" in ingredients else 0,
            umami=2 if ingredients & (_ANIMAL_PROTEINS | {"香菇", "豆腐"}) else 1,
            richness=2 if ingredients & (_ANIMAL_PROTEINS | _EGG_DAIRY) else 1,
        )

    @staticmethod
    def _method_label(method: CookingMethod) -> str:
        return {
            CookingMethod.MIX: "拌制",
            CookingMethod.STIR_FRY: "翻炒",
            CookingMethod.PAN_FRY: "煎制",
            CookingMethod.BOIL: "煮制",
            CookingMethod.SIMMER: "炖煮",
            CookingMethod.STEAM: "蒸制",
            CookingMethod.BAKE: "烘烤",
            CookingMethod.ROAST: "烤制",
            CookingMethod.AIR_FRY: "空气炸制",
        }[method]

    @staticmethod
    def _cooking_instruction(
        seed: _RecipeSeed, ingredient_names: list[str]
    ) -> tuple[str, HeatLevel, float | None]:
        names = "、".join(ingredient_names)
        if seed.method == CookingMethod.MIX:
            return (
                f"将{names}放入干净大碗，轻柔翻拌均匀，调味后立即食用。",
                HeatLevel.NONE,
                None,
            )
        if seed.method == CookingMethod.STIR_FRY:
            return (
                f"锅中加入食用油，以中火按成熟所需时间依次加入{names}，翻炒至全部熟透后调味。",
                HeatLevel.MEDIUM,
                None,
            )
        if seed.method == CookingMethod.PAN_FRY:
            return (
                f"平底锅薄薄刷油，以中小火放入混合好的{names}，两面煎至定型并完全熟透。",
                HeatLevel.MEDIUM,
                None,
            )
        if seed.method == CookingMethod.BOIL:
            return (
                f"锅中加入水烧开，按易熟程度依次放入{names}，保持中火煮至全部熟透并调味。",
                HeatLevel.MEDIUM,
                None,
            )
        if seed.method == CookingMethod.SIMMER:
            return (
                f"锅中加入{names}并补足水，煮开后转小火加盖炖至食材熟软，最后调味。",
                HeatLevel.LOW,
                None,
            )
        if seed.method == CookingMethod.STEAM:
            return (
                f"将{names}装入耐热盘，蒸锅水开后放入，以中火蒸至中心完全熟透。",
                HeatLevel.MEDIUM,
                100,
            )
        if seed.method in {CookingMethod.BAKE, CookingMethod.ROAST}:
            return (
                f"将{names}均匀铺在烤盘，放入预热至180摄氏度的烤箱，烤至中心熟透。",
                HeatLevel.MEDIUM,
                180,
            )
        return (
            f"将{names}拌匀后平铺在空气炸锅篮中，180摄氏度加热，中途翻面并炸至熟透。",
            HeatLevel.MEDIUM,
            180,
        )


class CodexAuthoredGenerationJobRunner:
    """Adapts Codex-authored seeds to the same job/retry orchestration contract."""

    def __init__(
        self,
        *,
        run_id: str,
        imported_at: datetime | None = None,
    ):
        self._run_id = run_id
        self._imported_at = imported_at or datetime.now(timezone.utc)
        self._offsets: dict[DatasetSegment, int] = defaultdict(int)

    def generate_job(
        self,
        job: GenerationJob,
        attempt: int,
        avoid_names: tuple[str, ...],
    ) -> list[RawRecipe]:
        offset = self._offsets[job.segment]
        generator = CodexSegmentRecipeBatchGenerator(
            segment=job.segment,
            offset=offset,
            run_id=self._run_id,
            imported_at=self._imported_at,
        )
        recipes = generator.generate_recipe_batch(job.category, job.count)
        self._offsets[job.segment] += len(recipes)
        return recipes
