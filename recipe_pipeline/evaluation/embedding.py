"""Versioned recipe and structured-query representations for retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from recipe_pipeline.evaluation.baseline import ParsedQuery, Preference
from recipe_pipeline.normalization.ingredients import IngredientCatalog
from recipe_pipeline.schemas.recipe import RecipeV1


class EmbeddingKind(str, Enum):
    INGREDIENT = "INGREDIENT"
    SCENARIO = "SCENARIO"
    FULL_RECIPE = "FULL_RECIPE"


RECIPE_TEMPLATE_VERSIONS = {
    EmbeddingKind.INGREDIENT: "recipe-ingredient-v2",
    EmbeddingKind.SCENARIO: "recipe-scenario-v2",
    EmbeddingKind.FULL_RECIPE: "recipe-full-v2",
}
QUERY_TEMPLATE_VERSIONS = {
    EmbeddingKind.INGREDIENT: "query-ingredient-v1",
    EmbeddingKind.SCENARIO: "query-scenario-v1",
    EmbeddingKind.FULL_RECIPE: "query-full-v1",
}


class EmbeddingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recipe_id: UUID
    kind: EmbeddingKind
    text: str
    template_version: str


@dataclass(frozen=True, slots=True)
class EmbeddingContext:
    representation_type: str
    template_version: str


_SCENARIO_LABELS = {
    "QUICK_MEAL": "快手菜 quick meal 快速晚餐",
    "FAMILY_MEAL": "家常菜 family meal 家庭晚餐",
    "STUDENT_COOKING": "学生做饭 student cooking 简单设备",
    "AIR_FRYER": "空气炸锅 air fryer",
    "ONE_POT": "一锅菜 one pot",
    "BEGINNER_FRIENDLY": "新手友好 beginner friendly 简单做法",
    "HEALTHY_MEAL": "健康餐 healthy meal 清淡搭配",
}
_PREFERENCE_LABELS = {
    Preference.LOW_OIL: "少油 low oil 清淡",
    Preference.NON_SPICY: "不辣 non spicy",
    Preference.HIGH_PROTEIN: "高蛋白 high protein",
    Preference.VEGETARIAN: "素食 vegetarian",
    Preference.VEGAN: "纯素 vegan",
}
_METHOD_LABELS = {
    "PREPARE": "准备 prepare",
    "MIX": "拌 mix",
    "STIR_FRY": "炒 stir fry",
    "PAN_FRY": "煎 pan fry",
    "BOIL": "煮 boil",
    "SIMMER": "炖 simmer stew",
    "STEAM": "蒸 steam",
    "BAKE": "烘烤 bake",
    "ROAST": "烤 roast",
    "AIR_FRY": "空气炸 air fry",
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class RecipeEmbeddingTextBuilder:
    """Build the three stable views without IDs, source, or quality internals."""

    def __init__(self, catalog: IngredientCatalog | None = None):
        self._catalog = catalog or IngredientCatalog()
        self._ingredients_by_id = {
            entry.ingredient_id: entry for entry in self._catalog.entries
        }

    def build(self, recipe: RecipeV1) -> list[EmbeddingDocument]:
        canonical = [item.normalized_name for item in recipe.ingredients]
        aliases = sorted(
            {
                alias
                for item in recipe.ingredients
                for alias in self._aliases(item.ingredient_id)
                if alias.casefold() != item.normalized_name.casefold()
            }
        )
        substitutes = sorted(
            {
                name
                for substitute in recipe.substitutes
                for name in self._canonical_and_aliases(
                    substitute.substitute_ingredient_id
                )
            }
        )
        core = [
            item.normalized_name
            for item in recipe.ingredients
            if item.importance.value == "CORE"
        ]
        scenarios = [
            _SCENARIO_LABELS.get(tag.value, tag.value)
            for tag in recipe.tags.scenario
        ]
        methods = sorted(
            {
                _METHOD_LABELS.get(step.method.value, step.method.value)
                for step in recipe.steps
            }
        )
        dietary = [tag.value for tag in recipe.tags.dietary]
        taste = recipe.taste_profile

        ingredient_text = "\n".join(
            (
                f"食材: {'; '.join(canonical)} (canonical ingredients)",
                f"食材别名 ingredient aliases: {'; '.join(aliases) or '无'}",
                f"有效替代食材 valid substitutes: {'; '.join(substitutes) or '无'}",
                f"核心食材组合 core ingredient combination: {' + '.join(core)}",
            )
        )
        scenario_text = "\n".join(
            (
                f"总时间 total time: {recipe.time.total_minutes} 分钟 minutes",
                f"难度 difficulty: {recipe.difficulty.level}/5",
                "所需设备 required equipment: "
                + "; ".join(item.value for item in recipe.equipment.required),
                f"烹饪方式 cooking methods: {'; '.join(methods)}",
                f"场景 scenario: {'; '.join(scenarios) or '通用 general'}",
                (
                    "口味 taste: "
                    f"辣 spicy {taste.spicy}/5, 甜 sweet {taste.sweet}/5, "
                    f"酸 sour {taste.sour}/5, 鲜 umami {taste.umami}/5, "
                    f"浓郁 richness {taste.richness}/5"
                ),
                f"客观饮食标签 objective dietary tags: {'; '.join(dietary) or '无 none'}",
            )
        )
        full_text = "\n".join(
            (
                f"菜名 dish name: {recipe.identity.name}",
                f"菜名别名 aliases: {'; '.join(recipe.identity.aliases) or '无'}",
                f"摘要 summary: {_clean(recipe.identity.summary)}",
                (
                    "菜系与分类 cuisine and category: "
                    f"{recipe.identity.cuisine.value}; {recipe.identity.region.value}; "
                    f"{recipe.identity.category.value}"
                ),
                f"核心食材 core ingredients: {'; '.join(core)}",
                f"主要做法 main cooking methods: {'; '.join(methods)}",
                f"场景 scenario: {'; '.join(scenarios) or '通用 general'}",
                (
                    "口味与饮食 taste and dietary: "
                    f"spicy {taste.spicy}/5, sweet {taste.sweet}/5, "
                    f"sour {taste.sour}/5, umami {taste.umami}/5; "
                    f"{' '.join(dietary)}"
                ),
            )
        )
        texts = {
            EmbeddingKind.INGREDIENT: ingredient_text,
            EmbeddingKind.SCENARIO: scenario_text,
            EmbeddingKind.FULL_RECIPE: full_text,
        }
        return [
            EmbeddingDocument(
                recipe_id=recipe.recipe_id,
                kind=kind,
                text=texts[kind],
                template_version=RECIPE_TEMPLATE_VERSIONS[kind],
            )
            for kind in EmbeddingKind
        ]

    def _aliases(self, ingredient_id: UUID) -> tuple[str, ...]:
        entry = self._ingredients_by_id.get(ingredient_id)
        return entry.aliases if entry else ()

    def _canonical_and_aliases(self, ingredient_id: UUID) -> tuple[str, ...]:
        entry = self._ingredients_by_id.get(ingredient_id)
        return entry.aliases if entry else ()


class QueryEmbeddingTextBuilder:
    """Preserve raw semantics while adding the parser's deterministic structure."""

    def __init__(self, catalog: IngredientCatalog | None = None):
        catalog = catalog or IngredientCatalog()
        self._ingredients_by_id = {
            entry.ingredient_id: entry for entry in catalog.entries
        }

    def build(self, parsed: ParsedQuery) -> dict[EmbeddingKind, str]:
        normalized_raw = _clean(parsed.original.casefold())
        ingredient_terms = []
        entries_by_name = {
            entry.normalized_name: entry for entry in self._ingredients_by_id.values()
        }
        for canonical in parsed.ingredient_names:
            entry = entries_by_name.get(canonical)
            ingredient_terms.append(
                " / ".join(entry.aliases if entry else (canonical,))
            )
        scenarios = [
            _SCENARIO_LABELS.get(tag.value, tag.value)
            for tag in sorted(parsed.scenario_tags, key=lambda item: item.value)
        ]
        preferences = [
            _PREFERENCE_LABELS[item]
            for item in sorted(parsed.preferences, key=lambda item: item.value)
        ]
        constraints = [
            f"最多 {parsed.max_minutes} 分钟 maximum {parsed.max_minutes} minutes"
            if parsed.max_minutes is not None
            else "",
            "必须不辣 must be non spicy" if parsed.exclude_spicy else "",
            (
                f"难度不高于 {parsed.preferred_max_difficulty} beginner"
                if parsed.preferred_max_difficulty is not None
                else ""
            ),
            (
                "排除食材 excluded ingredient IDs resolved deterministically"
                if parsed.excluded_ingredient_ids
                else ""
            ),
            (
                "过敏原排除 allergens excluded: "
                + ", ".join(item.value for item in parsed.excluded_allergens)
                if parsed.excluded_allergens
                else ""
            ),
            (
                "不可用设备 unavailable equipment: "
                + ", ".join(item.value for item in parsed.unavailable_equipment)
                if parsed.unavailable_equipment
                else ""
            ),
        ]
        structured = [
            *ingredient_terms,
            *scenarios,
            *preferences,
            *parsed.dish_terms,
            *(value for value in constraints if value),
        ]
        return {
            EmbeddingKind.INGREDIENT: "\n".join(
                (
                    f"原始查询 raw query: {normalized_raw}",
                    "目标食材 desired ingredients: "
                    + ("; ".join(ingredient_terms) or "未指定 unspecified"),
                    f"菜品类型 dish form: {'; '.join(parsed.dish_terms) or '未指定'}",
                )
            ),
            EmbeddingKind.SCENARIO: "\n".join(
                (
                    f"原始查询 raw query: {normalized_raw}",
                    f"场景 scenario: {'; '.join(scenarios) or '未指定'}",
                    f"偏好 preferences: {'; '.join(preferences) or '未指定'}",
                    f"确定性约束 deterministic constraints: {'; '.join(value for value in constraints if value) or '无'}",
                )
            ),
            EmbeddingKind.FULL_RECIPE: "\n".join(
                (
                    f"食谱检索查询 recipe search query: {normalized_raw}",
                    f"解析后的语义 parsed semantics: {'; '.join(structured) or normalized_raw}",
                )
            ),
        }

    @staticmethod
    def contexts() -> dict[EmbeddingKind, EmbeddingContext]:
        return {
            kind: EmbeddingContext(kind.value, QUERY_TEMPLATE_VERSIONS[kind])
            for kind in EmbeddingKind
        }
