"""Bounded Codex-authored canonical generation and isolated enrichment."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from recipe_pipeline.golden.catalog import cuisine_for_style, region_for_style
from recipe_pipeline.golden.models import (
    CANONICAL_GENERATOR_PROMPT_VERSION,
    GOLDEN_DATASET_VERSION,
    GOLDEN_GENERATOR_MODEL,
    CanonicalRecipeContent,
    GoldenBlueprint,
    PrimaryCollection,
)
from recipe_pipeline.schemas.recipe import (
    AllergenTag,
    CookingMethod,
    DietaryTag,
    EquipmentName,
    HeatLevel,
    IngredientImportance,
    IngredientRole,
    Nutrition,
    NutritionLevel,
    RawIngredient,
    RawRecipe,
    RawStep,
    RecipeTags,
    ScenarioTag,
    SourceMetadata,
    SourceType,
    StepPhase,
    TasteProfile,
    Unit,
)


CANONICAL_GENERATOR_PROMPT = """canonical_recipe_generator_v1
Return only reliable canonical cooking content: identity, cuisine/category, servings,
ingredients and reasonable quantities, preparation/cooking steps, time, and equipment.
Do not generate nutrition numbers, health claims, confidence, review state, or fake sources.
Use realistic household cooking and the supplied controlled ingredient names only.
"""

_EQUIPMENT = {
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
_POULTRY = {"鸡肉", "鸡腿", "鸡翅", "整鸡", "鸭肉", "鸭腿", "鸡胗", "鸡爪"}
_MEAT = {"猪肉", "五花肉", "猪排骨", "猪蹄", "猪肝", "猪肚", "肉馅", "牛肉", "羊肉", "羊排"}
_FISH = {"鱼", "鲈鱼", "草鱼", "鲫鱼", "鳕鱼", "带鱼", "金枪鱼", "三文鱼"}
_SHELLFISH = {"虾", "鱿鱼", "蛤蜊", "扇贝", "螃蟹"}
_ANIMAL = _POULTRY | _MEAT | _FISH | _SHELLFISH
_SWEET = {"苹果", "香蕉", "梨", "橙子", "草莓", "蓝莓", "菠萝", "蜂蜜", "红枣", "酸奶", "牛奶"}
_LIQUIDS = {"水", "牛奶", "酸奶", "椰奶", "淡奶油"}
_CONDIMENTS = {
    "盐", "生抽", "老抽", "醋", "白糖", "冰糖", "黑胡椒", "白胡椒", "淀粉",
    "料酒", "芝麻油", "蚝油", "豆瓣酱", "辣椒", "花椒", "咖喱粉", "番茄酱",
    "蜂蜜", "豆豉", "黄豆酱", "甜面酱", "芝麻酱", "花生酱", "沙茶酱", "鱼露",
    "辣椒酱", "五香粉", "孜然", "八角", "桂皮", "香叶", "米酒", "柠檬汁",
    "泡打粉",
}


def _safety_note(names: set[str]) -> str | None:
    if names & _POULTRY:
        return "禽肉中心应完全熟透且无粉红生肉；生熟刀板分开。"
    if names & _FISH:
        return "鱼肉应加热至不透明并可轻易剥离。"
    if names & _SHELLFISH:
        return "水产应加热至完全熟透，并避免生熟器具交叉接触。"
    if names & _MEAT:
        return "肉类中心应充分熟透，并注意生熟器具分开。"
    if "鸡蛋" in names:
        return "蛋液应加热至完全凝固。"
    return None


def _quantity(name: str, index: int) -> tuple[float | None, Unit]:
    if name == "盐":
        return None, Unit.TO_TASTE
    if name == "水":
        return 500.0, Unit.MILLILITER
    if name in {"鸡蛋", "鸡腿", "鸡翅", "整鸡", "鸭腿", "苹果", "香蕉", "梨", "橙子", "柠檬", "馒头"}:
        return (2.0 if name != "整鸡" else 1.0), Unit.PIECE
    if name in _LIQUIDS:
        return 200.0, Unit.MILLILITER
    if name in _CONDIMENTS:
        return (1.0 if index else 2.0), Unit.TABLESPOON
    return (250.0 if index == 0 else 150.0), Unit.GRAM


def _preparation(name: str, method: CookingMethod) -> str:
    if method == CookingMethod.MIX and name in {"红豆", "绿豆", "鹰嘴豆", "鸡肉", "虾", "鸡蛋"}:
        return "提前煮熟并放凉"
    if name in _POULTRY | _MEAT | _FISH | _SHELLFISH:
        return "清理后切成适合入口且厚薄均匀的块或片"
    if name in {"大蒜", "姜", "小葱", "香菜"}:
        return "洗净后切碎"
    if name in {"大米", "小米", "糯米", "红豆", "绿豆", "黄豆", "莲子"}:
        return "淘洗干净"
    if name in _CONDIMENTS | _LIQUIDS | {"水"}:
        return ""
    return "洗净后按菜品需要切成均匀大小"


class CodexCanonicalRecipeGenerator:
    """The authored blueprint is the model output; this adapter enforces the contract."""

    batch_size = 8

    def generate_batch(self, blueprints: list[GoldenBlueprint]) -> list[CanonicalRecipeContent]:
        if not 1 <= len(blueprints) <= 10:
            raise ValueError("canonical batches must contain 1-10 recipes")
        return [self.generate(item) for item in blueprints]

    def generate(self, blueprint: GoldenBlueprint) -> CanonicalRecipeContent:
        core = list(blueprint.ingredients)
        names = list(core)
        is_sweet = blueprint.category.value in {"DESSERT"} or (
            bool(set(core) & _SWEET) and not bool(set(core) & _ANIMAL)
        )
        if blueprint.method in {CookingMethod.BOIL, CookingMethod.SIMMER, CookingMethod.STEAM} and "水" not in names:
            names.append("水")
        if blueprint.method in {CookingMethod.STIR_FRY, CookingMethod.PAN_FRY} and "食用油" not in names:
            names.append("食用油")
        if not is_sweet and "盐" not in names:
            names.append("盐")
        ingredients = []
        for index, name in enumerate(names):
            amount, unit = _quantity(name, index)
            ingredients.append(
                RawIngredient(
                    name=name,
                    display_name=name,
                    role=IngredientRole.REQUIRED if name in core else IngredientRole.OPTIONAL,
                    importance=(
                        IngredientImportance.CORE
                        if name in core and name not in _CONDIMENTS and name != "水"
                        else IngredientImportance.PANTRY
                    ),
                    quantity_min=amount,
                    unit=unit,
                    preparation=_preparation(name, blueprint.method),
                )
            )
        prep = min(12, max(4, blueprint.total_minutes // 4))
        cook = blueprint.total_minutes - prep
        equipment = [EquipmentName.KNIFE, EquipmentName.CUTTING_BOARD, _EQUIPMENT[blueprint.method]]
        mixed_protein = blueprint.method == CookingMethod.MIX and bool(set(core) & (_POULTRY | _MEAT | _SHELLFISH | {"鸡蛋"}))
        if mixed_protein:
            equipment.append(EquipmentName.POT)
        equipment = list(dict.fromkeys(equipment))
        steps = [
            RawStep(
                order=1, phase=StepPhase.PREP,
                instruction=f"准备{'、'.join(core)}；需清洗的食材洗净，按后续成熟速度处理并分别放置。",
                duration_minutes=prep, method=CookingMethod.PREPARE, heat_level=HeatLevel.NONE,
                ingredient_names=core, equipment_refs=[EquipmentName.KNIFE, EquipmentName.CUTTING_BOARD],
            )
        ]
        if mixed_protein:
            protein = [name for name in core if name in (_POULTRY | _MEAT | _SHELLFISH | {"鸡蛋"})]
            steps.append(RawStep(
                order=2, phase=StepPhase.COOK,
                instruction=f"锅中加水，将{'、'.join(protein)}煮至完全熟透，取出放凉。",
                duration_minutes=max(5, cook // 2), method=CookingMethod.BOIL, heat_level=HeatLevel.MEDIUM,
                ingredient_names=protein, equipment_refs=[EquipmentName.POT], safety_note=_safety_note(set(protein)),
            ))
            final_minutes = max(2, cook - steps[-1].duration_minutes)
            steps.append(RawStep(
                order=3, phase=StepPhase.FINISH,
                instruction=f"将处理好的{'、'.join(core)}放入碗中拌匀，按口味调味后立即食用。",
                duration_minutes=final_minutes, method=CookingMethod.MIX, heat_level=HeatLevel.NONE,
                ingredient_names=names, equipment_refs=[EquipmentName.BOWL],
            ))
        else:
            steps.append(self._cook_step(blueprint, names, cook))
        record_id = f"golden-v1-{uuid5(NAMESPACE_URL, 'ai-cooker:golden:' + blueprint.name).hex[:16]}"
        return CanonicalRecipeContent(
            record_id=record_id,
            collection=blueprint.collection,
            style=blueprint.style,
            name=blueprint.name,
            region=region_for_style(blueprint.style),
            cuisine=cuisine_for_style(blueprint.style),
            category=blueprint.category,
            min_servings=2,
            max_servings=3 if blueprint.collection == PrimaryCollection.FAMILY_ONE_POT else 2,
            prep_minutes=prep,
            cook_minutes=cook,
            total_minutes=blueprint.total_minutes,
            ingredients=ingredients,
            steps=steps,
            equipment_required=equipment,
        )

    @staticmethod
    def _cook_step(blueprint: GoldenBlueprint, names: list[str], duration: int) -> RawStep:
        label = "、".join(blueprint.ingredients)
        method = blueprint.method
        instructions = {
            CookingMethod.STIR_FRY: f"锅烧热后加少量油，按成熟速度依次加入{label}翻炒，调味后炒至全部熟透。",
            CookingMethod.PAN_FRY: f"平底锅加入少量油，将处理好的{label}摊匀，以中火煎至两面定型并完全熟透。",
            CookingMethod.BOIL: f"锅中水沸后依次加入{label}，保持适度沸腾，煮至食材成熟且口感合适。",
            CookingMethod.SIMMER: f"将{label}放入锅中煮沸，转小火加盖炖至主要食材熟软，中途检查水量。",
            CookingMethod.STEAM: f"蒸锅上汽后放入处理好的{label}，加盖蒸至中心完全熟透。",
            CookingMethod.BAKE: f"将{label}混合后放入烤盘，烤箱预热至180°C，烤至中心熟透、表面定型。",
            CookingMethod.ROAST: f"将{label}均匀铺入烤盘，烤箱预热至190°C，烤至食材熟透并适度上色。",
            CookingMethod.AIR_FRY: f"将{label}均匀放入空气炸锅，180°C烹调，中途翻动一次，直至完全熟透。",
            CookingMethod.MIX: f"将处理好的{label}放入碗中拌匀，按口味调味后立即食用。",
        }
        heat = HeatLevel.NONE if method == CookingMethod.MIX else (HeatLevel.LOW if method == CookingMethod.SIMMER else HeatLevel.MEDIUM)
        temperature = 180.0 if method in {CookingMethod.BAKE, CookingMethod.AIR_FRY} else (190.0 if method == CookingMethod.ROAST else None)
        return RawStep(
            order=2, phase=StepPhase.FINISH if method == CookingMethod.MIX else StepPhase.COOK,
            instruction=instructions[method], duration_minutes=duration, method=method,
            heat_level=heat, temperature_celsius=temperature,
            ingredient_names=names, equipment_refs=[_EQUIPMENT[method]], safety_note=_safety_note(set(names)),
        )


class BoundedCanonicalGenerationCoordinator:
    def __init__(self, generator: CodexCanonicalRecipeGenerator, max_attempts: int = 2):
        if max_attempts != 2:
            raise ValueError("Golden v1 permits exactly one retry")
        self.generator = generator
        self.max_attempts = max_attempts

    def run(self, blueprints: list[GoldenBlueprint]) -> tuple[list[CanonicalRecipeContent], list[dict], int]:
        generated: list[CanonicalRecipeContent] = []
        rejected: list[dict] = []
        retry_count = 0
        for offset in range(0, len(blueprints), self.generator.batch_size):
            batch = blueprints[offset : offset + self.generator.batch_size]
            for attempt in range(1, self.max_attempts + 1):
                try:
                    generated.extend(self.generator.generate_batch(batch))
                    break
                except Exception as exc:  # bounded adapter boundary, reported verbatim offline
                    if attempt == 1:
                        retry_count += 1
                        continue
                    rejected.extend({"name": item.name, "stage": "GENERATION", "reason": str(exc)} for item in batch)
        return generated, rejected, retry_count


class DeterministicRecipeEnricher:
    def enrich(self, canonical: CanonicalRecipeContent, *, imported_at: datetime | None = None) -> RawRecipe:
        names = {item.name for item in canonical.ingredients}
        animal = bool(names & _ANIMAL)
        egg = "鸡蛋" in names
        dairy = bool(names & {"牛奶", "酸奶", "奶酪", "黄油", "淡奶油"})
        wheat = bool(names & {"面粉", "面条", "面包", "馒头", "意大利面", "饺子皮", "馄饨皮"})
        soy = bool(names & {"豆腐", "豆皮", "腐竹", "豆豉", "黄豆", "黄豆酱", "生抽", "老抽"})
        dietary = []
        if not animal:
            dietary.append(DietaryTag.VEGETARIAN)
            if not egg and not dairy:
                dietary.append(DietaryTag.VEGAN)
        if not wheat:
            dietary.append(DietaryTag.GLUTEN_FREE)
        if not dairy:
            dietary.append(DietaryTag.DAIRY_FREE)
        allergens = []
        for present, tag in ((egg, AllergenTag.EGG), (dairy, AllergenTag.MILK), ("花生" in names or "花生酱" in names, AllergenTag.PEANUT), (bool(names & {"核桃", "腰果"}), AllergenTag.TREE_NUT), (soy, AllergenTag.SOY), (wheat, AllergenTag.WHEAT), (bool(names & _FISH), AllergenTag.FISH), (bool(names & _SHELLFISH), AllergenTag.SHELLFISH), (bool(names & {"芝麻", "芝麻酱", "芝麻油"}), AllergenTag.SESAME)):
            if present:
                allergens.append(tag)
        scenario = []
        if canonical.total_minutes <= 25:
            scenario.append(ScenarioTag.QUICK_MEAL)
        if canonical.collection == PrimaryCollection.BEGINNER_FRIENDLY:
            scenario.append(ScenarioTag.BEGINNER_FRIENDLY)
        if canonical.collection == PrimaryCollection.FAMILY_ONE_POT:
            scenario.extend([ScenarioTag.FAMILY_MEAL, ScenarioTag.ONE_POT])
        if canonical.collection == PrimaryCollection.HEALTHY_LIGHT:
            scenario.append(ScenarioTag.HEALTHY_MEAL)
        if canonical.collection == PrimaryCollection.AIR_FRYER_APPLIANCE:
            scenario.append(ScenarioTag.AIR_FRYER)
        method = canonical.steps[-1].method
        spicy = 3 if names & {"辣椒", "花椒", "豆瓣酱", "辣椒酱"} else 0
        sweet = 2 if names & {"白糖", "冰糖", "蜂蜜", "红枣"} else 0
        sour = 2 if names & {"醋", "柠檬", "柠檬汁", "酸菜", "酸豆角"} else 0
        level = 1 if canonical.collection == PrimaryCollection.BEGINNER_FRIENDLY else (3 if method in {CookingMethod.STEAM, CookingMethod.ROAST} and animal else 2)
        return RawRecipe(
            recipe_id=uuid5(NAMESPACE_URL, "ai-cooker:golden-recipe:" + canonical.name),
            name=canonical.name, aliases=canonical.aliases, language=canonical.language,
            region=canonical.region, cuisine=canonical.cuisine, category=canonical.category,
            summary=f"以{'、'.join(item.name for item in canonical.ingredients[:4])}为主要食材，采用{method.value}完成的家庭食谱。",
            min_servings=canonical.min_servings, max_servings=canonical.max_servings,
            prep_minutes=canonical.prep_minutes, cook_minutes=canonical.cook_minutes,
            total_minutes=canonical.total_minutes, difficulty_level=level,
            difficulty_reasons=["步骤和火候复杂度由确定性规则评估"],
            ingredients=[item.model_copy(deep=True) for item in canonical.ingredients],
            steps=[item.model_copy(deep=True) for item in canonical.steps],
            equipment_required=list(canonical.equipment_required), equipment_optional=list(canonical.equipment_optional),
            taste_profile=TasteProfile(spicy=spicy, sweet=sweet, sour=sour, salty=2 if "盐" in names else 1, umami=2 if animal or soy else 1, richness=2 if names & {"五花肉", "黄油", "淡奶油"} else 1),
            nutrition=Nutrition(calories_kcal=None, protein_g=None, fat_g=None, carbohydrate_g=None, protein_level=NutritionLevel.UNKNOWN, fat_level=NutritionLevel.UNKNOWN),
            tags=RecipeTags(dietary=dietary, health=[], scenario=list(dict.fromkeys(scenario)), technique=[method], allergens=allergens),
            source=SourceMetadata(source_type=SourceType.AI_SYNTHETIC, source_name=CANONICAL_GENERATOR_PROMPT_VERSION, source_record_id=canonical.record_id, license="AI-GENERATED-REVIEW-REQUIRED", reliability_score=0.5, generator_model=GOLDEN_GENERATOR_MODEL, dataset_version=GOLDEN_DATASET_VERSION, imported_at=imported_at or datetime.now(timezone.utc)),
        )
