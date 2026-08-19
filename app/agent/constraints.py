"""Deterministic cooking-constraint extraction and Recipe tool enforcement."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from html import escape
import json
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from langchain_core.messages import ToolMessage

from app.agent.context import AgentRunContext
from recipe_pipeline.evaluation.baseline import Preference, RecipeQueryParser
from recipe_pipeline.normalization.ingredients import (
    IngredientCatalog,
    UnknownIngredientError,
)


CONSTRAINT_POLICY_VERSION = "recipe-constraint-boundary-v1"


_ALLERGEN_PATTERNS: dict[str, tuple[str, ...]] = {
    "EGG": ("鸡蛋过敏", "蛋过敏", "egg allergy", "allergic to eggs"),
    "MILK": (
        "牛奶过敏", "乳制品过敏", "乳糖不耐受", "无奶", "不要奶制品",
        "milk allergy", "dairy allergy", "dairy-free", "without dairy",
    ),
    "PEANUT": (
        "花生过敏", "不要花生", "不吃花生", "avoid peanuts",
        "peanut allergy", "allergic to peanuts", "without peanuts",
    ),
    "TREE_NUT": (
        "坚果过敏", "不要坚果", "不吃坚果", "无坚果", "nut allergy",
        "allergic to nuts", "without nuts",
    ),
    "SOY": ("大豆过敏", "豆类过敏", "soy allergy", "allergic to soy"),
    "WHEAT": (
        "小麦过敏", "无麸质", "麸质过敏", "wheat allergy",
        "gluten-free", "gluten free", "celiac",
    ),
    "FISH": ("鱼过敏", "海鲜过敏", "fish allergy", "seafood allergy"),
    "SHELLFISH": (
        "甲壳类过敏", "贝类过敏", "海鲜过敏", "shellfish allergy",
        "seafood allergy",
    ),
    "SESAME": ("芝麻过敏", "sesame allergy", "allergic to sesame"),
}

_DIET_PATTERNS: dict[str, tuple[str, ...]] = {
    "VEGAN": ("纯素", "全素", "vegan"),
    "VEGETARIAN": ("素食", "蛋奶素", "vegetarian"),
    "GLUTEN_FREE": ("无麸质", "gluten-free", "gluten free", "celiac"),
    "DAIRY_FREE": ("无奶", "不要奶制品", "dairy-free", "without dairy"),
}

_TASTE_PATTERNS: dict[str, tuple[str, ...]] = {
    "LOW_OIL": (
        "少油", "低油", "少放点油", "少放油", "别太油", "不油腻",
        "prefer low oil", "low-oil", "low oil",
    ),
    "NON_SPICY": (
        "不辣", "不要辣", "不吃辣", "完全不辣", "prefer non-spicy",
        "non-spicy", "not spicy",
    ),
    "HIGH_PROTEIN": ("高蛋白", "high protein", "high-protein"),
    "LOW_SALT": ("少盐", "低盐", "low salt", "low-salt"),
    "LOW_SWEET": ("不要太甜", "少糖", "低糖", "low sugar", "less sweet"),
    "LIGHT": ("清淡", "light meal"),
    "CRISPY": ("脆一点", "酥脆", "crispy"),
    "TENDER": ("嫩一点", "tender"),
    "HEALTHY": ("健康一点", "healthy"),
}

_EQUIPMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "AIR_FRYER": ("空气炸锅", "air fryer"),
    "RICE_COOKER": ("电饭锅", "电饭煲", "rice cooker"),
    "MICROWAVE": ("微波炉", "microwave"),
    "STEAMER": ("蒸锅", "steamer"),
    "PAN": ("平底锅", "煎锅", "pan", "skillet"),
    "WOK": ("炒锅", "wok"),
    "OVEN": ("烤箱", "oven"),
    "STOVE": ("炉灶", "燃气灶", "电磁炉", "stove", "cooktop"),
}

_NEGATIVE_EQUIPMENT_PREFIXES = (
    "没有", "没用", "不用", "不能用", "不使用", "无", "no ", "without ",
)

_NEGATIVE_EQUIPMENT_SUFFIXES = (
    "没有", "不能用", "不可用", "用不了", "坏了", " unavailable", " not available",
)

_SCENARIO_PATTERNS: dict[str, tuple[str, ...]] = {
    "QUICK_MEAL": ("快手", "快速", "分钟内", "quick"),
    "BEGINNER_FRIENDLY": ("新手", "初学", "简单", "beginner"),
    "AIR_FRYER": ("空气炸锅", "air fryer"),
    "HEALTHY_MEAL": ("健康", "healthy"),
    "FAMILY_MEAL": ("家常", "家庭", "family"),
    "STUDENT_COOKING": ("宿舍", "学生", "student"),
    "ONE_POT": ("一锅", "one pot", "one-pot"),
}

_ALLERGEN_INGREDIENTS: dict[str, tuple[str, ...]] = {
    "EGG": ("鸡蛋",),
    "MILK": ("牛奶", "奶油", "黄油", "奶酪"),
    "PEANUT": ("花生", "花生酱"),
    "TREE_NUT": ("核桃", "腰果"),
    "WHEAT": ("面粉",),
    "FISH": ("鱼", "三文鱼", "鳕鱼"),
    "SHELLFISH": ("虾", "螃蟹", "蛤蜊", "扇贝"),
    "SESAME": ("芝麻", "芝麻油", "芝麻酱"),
}

_ALLERGEN_FROM_EXCLUSION = {
    "花生": "PEANUT",
    "坚果": "TREE_NUT",
    "牛奶": "MILK",
    "鸡蛋": "EGG",
    "芝麻": "SESAME",
}

_GENERIC_INGREDIENT_ALIASES = {
    "意面": "意面",
    "吐司": "面包",
    "prawns": "虾",
    "tomatoes": "番茄",
    "green peppers": "青椒",
    "green onions": "小葱",
}

_EXTRA_INGREDIENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "虾": ("prawns", "prawn"),
    "意面": ("意面", "pasta", "spaghetti"),
    "米饭": ("一锅饭",),
    "小白菜": ("小白菜",),
    "青菜": ("青菜", "leafy greens", "leafy vegetables"),
    "吐司": ("吐司", "toast"),
}

_CATEGORY_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    # A general pork exclusion must not leak through a more specific pork cut.
    "猪肉": ("猪肉", "五花肉", "猪排骨", "猪蹄", "猪肝", "猪肚"),
}

_PROHIBITED_BY_DIET = {
    "VEGETARIAN": ("鸡肉", "牛肉", "猪肉", "鱼", "虾", "chicken", "beef", "pork", "fish", "shrimp"),
    "VEGAN": (
        "鸡肉", "牛肉", "猪肉", "鱼", "虾", "鸡蛋", "牛奶", "奶油", "黄油",
        "chicken", "beef", "pork", "fish", "shrimp", "egg", "milk", "cream", "butter",
    ),
}

_SAFE_NEGATIONS = (
    "不要", "不吃", "不放", "不含", "未含", "没有", "无", "不用", "不能用",
    "未使用", "符合", "是否含", "避免", "回避", "排除", "去掉", "过敏", "do not", "don't", "avoid",
    "without", "free from", "no ",
    # A comparison or replacement does not propose using the restricted item.
    "替代", "代替", "取代", "接近", "类似", "效果", "instead of",
    "alternative to", "similar to",
)

_PREFERENCE_ONLY_INGREDIENTS = {
    "LOW_OIL": {"食用油"},
    "LOW_SALT": {"盐"},
}

_EXPLICIT_WEB_MARKERS = (
    "最近网上", "当前网页", "网上流行", "热门趋势", "网红", "网页来源",
    "latest", "current", "trending", "viral", "web source", "online source",
)


@dataclass(frozen=True, slots=True)
class RecipeConstraints:
    available_ingredients: tuple[str, ...] = ()
    excluded_ingredients: tuple[str, ...] = ()
    excluded_allergens: tuple[str, ...] = ()
    dietary_constraints: tuple[str, ...] = ()
    taste_preferences: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    unavailable_equipment: tuple[str, ...] = ()
    scenario_tags: tuple[str, ...] = ()
    max_total_minutes: int | None = None
    max_difficulty: int | None = None
    servings: int | None = None
    should_search_recipe: bool = False

    def as_tool_arguments(self) -> dict[str, Any]:
        return {
            "available_ingredients": list(self.available_ingredients),
            "excluded_ingredients": list(self.excluded_ingredients),
            "excluded_allergens": list(self.excluded_allergens),
            "dietary_constraints": list(self.dietary_constraints),
            "taste_preferences": list(self.taste_preferences),
            "equipment": list(self.equipment),
            "unavailable_equipment": list(self.unavailable_equipment),
            "scenario_tags": list(self.scenario_tags),
            "max_total_minutes": self.max_total_minutes,
            "max_difficulty": self.max_difficulty,
            "servings": self.servings,
        }


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)


def _message_text(message: AnyMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    if not isinstance(message.content, list):
        return ""
    return " ".join(
        str(part.get("text", ""))
        for part in message.content
        if isinstance(part, dict) and part.get("type") == "text"
    )


def _canonical_ingredient(value: str, catalog: IngredientCatalog) -> str:
    cleaned = value.strip()
    alias = _GENERIC_INGREDIENT_ALIASES.get(cleaned.casefold())
    if alias:
        cleaned = alias
    try:
        return catalog.resolve(cleaned).normalized_name
    except UnknownIngredientError:
        if cleaned.casefold().endswith("s"):
            try:
                return catalog.resolve(cleaned[:-1]).normalized_name
            except UnknownIngredientError:
                pass
        return cleaned


def _explicit_ingredient_mentions(
    text: str,
    catalog: IngredientCatalog,
) -> list[str]:
    """Return non-overlapping user spellings, longest alias first."""

    folded = text.casefold()
    aliases = sorted(
        (
            (alias.casefold(), alias)
            for entry in catalog.entries
            for alias in entry.aliases
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    occupied: set[int] = set()
    values: list[str] = []
    for folded_alias, _alias in aliases:
        pattern = (
            rf"(?<![a-z0-9]){re.escape(folded_alias)}(?![a-z0-9])"
            if folded_alias.isascii()
            else re.escape(folded_alias)
        )
        for match in re.finditer(pattern, folded):
            positions = set(range(match.start(), match.end()))
            if positions & occupied:
                continue
            occupied.update(positions)
            values.append(text[match.start():match.end()])
    return values


def _negative_ingredient_mentions(
    text: str,
    catalog: IngredientCatalog,
) -> list[str]:
    """Extract every ingredient in an explicit negative/allergy clause."""

    folded = text.casefold()
    clauses = [
        match.group(1)
        for match in re.finditer(
            r"(?:不要|不吃|不放|避免|排除|去掉|忌口)\s*([^，,。！？.!?;；\n]+)",
            folded,
        )
    ]
    clauses.extend(
        match.group(1)
        for match in re.finditer(
            r"(?:do not eat|don't eat|avoid|without|exclude|no)\s+([^,.!?;\n]+)",
            folded,
        )
    )
    clauses.extend(
        match.group(1)
        for match in re.finditer(
            r"([^，,。！？.!?;；\n]+?)(?:过敏|allergy|allergic)",
            folded,
        )
    )
    return [
        value
        for clause in clauses
        for value in _explicit_ingredient_mentions(clause, catalog)
    ]


def extract_recipe_constraints(
    messages: Sequence[AnyMessage],
    user_memories: Sequence[str] = (),
) -> RecipeConstraints:
    """Extract only explicit constraints from trusted memory and user messages."""

    catalog = IngredientCatalog()
    parser = RecipeQueryParser(catalog)
    human_texts = [_message_text(message) for message in messages if isinstance(message, HumanMessage)]
    texts = [*user_memories, *human_texts]
    available: list[str] = []
    excluded: list[str] = []
    allergens: list[str] = []
    diets: list[str] = []
    tastes: list[str] = []
    equipment: list[str] = []
    unavailable: list[str] = []
    scenarios: list[str] = []
    max_minutes: int | None = None
    max_difficulty: int | None = None
    servings: int | None = None
    recommendation_markers = (
        "推荐", "食谱", "晚饭", "晚餐", "早餐", "午餐", "吃什么",
        "怎么做", "做法", "能一起做", "recipe", "dinner", "breakfast",
        "lunch", "dish", "dishes", "what to eat", "what can i cook",
    )
    latest_human = human_texts[-1].casefold() if human_texts else ""
    should_search_recipe = (
        any(marker in latest_human for marker in recommendation_markers)
        and not any(marker in latest_human for marker in _EXPLICIT_WEB_MARKERS)
    )

    for raw in texts:
        text = raw.strip()
        if not text:
            continue
        folded = text.casefold()
        parsed = parser.parse(text)
        available.extend(_explicit_ingredient_mentions(text, catalog))
        available.extend(parsed.ingredient_names)
        for value, patterns in _EXTRA_INGREDIENT_PATTERNS.items():
            if any(pattern in folded for pattern in patterns):
                available.append(value)
        excluded.extend(
            catalog.get(value).normalized_name
            for value in parsed.excluded_ingredient_ids
            if catalog.get(value) is not None
        )
        excluded.extend(_negative_ingredient_mentions(text, catalog))
        allergens.extend(item.value for item in parsed.excluded_allergens)
        for preference in parsed.preferences:
            if preference == Preference.VEGETARIAN:
                diets.append("VEGETARIAN")
            elif preference == Preference.VEGAN:
                diets.append("VEGAN")
            else:
                tastes.append(preference.value)
        if parsed.max_minutes is not None:
            max_minutes = parsed.max_minutes
        if parsed.preferred_max_difficulty is not None:
            max_difficulty = parsed.preferred_max_difficulty

        for entry in catalog.entries:
            for alias in entry.aliases:
                escaped = re.escape(alias.casefold())
                patterns = (
                    rf"(?:不要|不吃|不放|避免|排除|去掉|忌口)\s*{escaped}",
                    rf"(?:do not eat|don't eat|avoid|without|exclude|no)\s+{escaped}(?![a-z0-9])",
                )
                if any(re.search(pattern, folded) for pattern in patterns):
                    excluded.append(entry.normalized_name)
                    break

        for value, patterns in _ALLERGEN_PATTERNS.items():
            if any(pattern in folded for pattern in patterns):
                allergens.append(value)
        for value, patterns in _DIET_PATTERNS.items():
            if any(pattern in folded for pattern in patterns):
                diets.append(value)
        for value, patterns in _TASTE_PATTERNS.items():
            if any(pattern in folded for pattern in patterns):
                tastes.append(value)
        for value, patterns in _SCENARIO_PATTERNS.items():
            if any(pattern in folded for pattern in patterns):
                scenarios.append(value)

        for value, aliases in _EQUIPMENT_ALIASES.items():
            for alias in aliases:
                position = folded.find(alias)
                if position < 0:
                    continue
                prefix = folded[max(0, position - 8):position]
                suffix = folded[position + len(alias):position + len(alias) + 12]
                if (
                    any(prefix.endswith(item) for item in _NEGATIVE_EQUIPMENT_PREFIXES)
                    or any(suffix.startswith(item) for item in _NEGATIVE_EQUIPMENT_SUFFIXES)
                ):
                    unavailable.append(value)
                else:
                    equipment.append(value)
                break

        if "只有" in folded or re.search(r"\bonly\b", folded):
            available_equipment = set(equipment)
            if available_equipment:
                unavailable.extend(
                    value for value in _EQUIPMENT_ALIASES if value not in available_equipment
                )
        # A specifically requested appliance/method excludes the conventional
        # oven/stove alternatives for this retrieval, without claiming the user
        # never owns them.
        if "AIR_FRYER" in equipment or "AIR_FRYER" in scenarios:
            unavailable.extend(("OVEN", "STOVE"))

        serving_match = re.search(r"(\d{1,2})\s*(?:人份|人|servings?)", folded)
        if serving_match:
            servings = int(serving_match.group(1))

    normalized_excluded = [*excluded]
    normalized_excluded.extend(
        _canonical_ingredient(value, catalog) for value in excluded
    )
    exclusion_text = " ".join(texts).casefold()
    for value in tuple(normalized_excluded):
        mapped = _ALLERGEN_FROM_EXCLUSION.get(value)
        if mapped:
            allergens.append(mapped)
    for value, mapped in _ALLERGEN_FROM_EXCLUSION.items():
        if any(
            marker + value in exclusion_text
            for marker in ("不要", "不吃", "避免", "排除", "without ", "avoid ")
        ):
            normalized_excluded.append(value)
            allergens.append(mapped)
    if "TREE_NUT" in allergens and "坚果" in exclusion_text:
        normalized_excluded.append("坚果")
        allergens.append("PEANUT")

    # Allergen declarations are hard ingredient exclusions too. This is
    # additive to the allergen enum because the Recipe tool exposes both.
    normalized_excluded.extend(
        value
        for allergen in allergens
        for value in _ALLERGEN_INGREDIENTS.get(allergen, ())
    )
    normalized_excluded = [
        expanded
        for value in normalized_excluded
        for expanded in _CATEGORY_EXCLUSIONS.get(value, (value,))
    ]

    normalized_available = [
        *available,
        *(_canonical_ingredient(value, catalog) for value in available),
    ]
    allergen_ingredients = {
        _canonical_ingredient(value, catalog)
        for allergen in allergens
        for value in _ALLERGEN_INGREDIENTS.get(allergen, ())
    }
    excluded_keys = {
        _canonical_ingredient(value, catalog).casefold()
        for value in normalized_excluded
    }
    normalized_available = [
        value for value in normalized_available
        if _canonical_ingredient(value, catalog).casefold() not in excluded_keys
        and _canonical_ingredient(value, catalog) not in allergen_ingredients
    ]
    # Memory constraints such as "avoid coriander" are parsed by the shared
    # catalog as ingredients before their negative semantics are applied.
    normalized_available = [
        value for value in normalized_available
        if _canonical_ingredient(value, catalog).casefold() not in excluded_keys
    ]
    for preference in tastes:
        normalized_available = [
            value for value in normalized_available
            if _canonical_ingredient(value, catalog)
            not in _PREFERENCE_ONLY_INGREDIENTS.get(preference, set())
        ]
    equipment_values = _unique(equipment)
    unavailable_values = tuple(
        value for value in _unique(unavailable) if value not in set(equipment_values)
    )
    latest_mentions = (
        _explicit_ingredient_mentions(human_texts[-1], catalog)
        if human_texts else []
    )
    latest_negative_keys = {
        _canonical_ingredient(value, catalog).casefold()
        for value in (
            _negative_ingredient_mentions(human_texts[-1], catalog)
            if human_texts else []
        )
    }
    latest_has_available = any(
        _canonical_ingredient(value, catalog).casefold() not in latest_negative_keys
        for value in latest_mentions
    )
    latest_updates_boundary = len(human_texts) > 1 and any(
        marker in latest_human
        for marker in (
            "记得", "不要", "不吃", "过敏", "没有", "少油", "低油",
            "少放油", "少放点油",
            "不辣", "分钟", "份量", "个人", "remember", "avoid",
            "allergic", "without", "servings", "less oil", "non-spicy",
        )
    )
    # A constraint-only first turn such as "我不吃辣" remains a clarification
    # case. Positive ingredients provide recommendation context; later turns
    # can update the active boundary without repeating "recipe".
    if (
        not any(marker in latest_human for marker in _EXPLICIT_WEB_MARKERS)
        and (latest_has_available or latest_updates_boundary)
    ):
        should_search_recipe = True
    return RecipeConstraints(
        available_ingredients=_unique(normalized_available),
        excluded_ingredients=_unique(normalized_excluded),
        excluded_allergens=_unique(value.upper() for value in allergens),
        dietary_constraints=_unique(value.upper() for value in diets),
        taste_preferences=_unique(value.upper() for value in tastes),
        equipment=equipment_values,
        unavailable_equipment=unavailable_values,
        scenario_tags=_unique(value.upper() for value in scenarios),
        max_total_minutes=max_minutes,
        max_difficulty=max_difficulty,
        servings=servings,
        should_search_recipe=should_search_recipe,
    )


def merge_recipe_search_arguments(
    arguments: dict[str, Any],
    constraints: RecipeConstraints,
) -> dict[str, Any]:
    """Merge deterministic constraints without weakening model-supplied values."""

    catalog = IngredientCatalog()
    merged = dict(arguments)

    def ingredients(field: str, enforced: tuple[str, ...]) -> list[str]:
        supplied = arguments.get(field) or []
        canonical_supplied = [
            _canonical_ingredient(str(value), catalog) for value in supplied
        ]
        # Preserve the model's exact vision/name output for observability while
        # appending catalog-normalized aliases for deterministic matching.
        # "青菜" is the dataset's generic leafy-green boundary and remains an
        # additive category alias rather than replacing a specific vegetable.
        if field == "available_ingredients" and any(
            value in {"生菜", "油菜", "菠菜", "小白菜"}
            for value in canonical_supplied
        ):
            canonical_supplied.append("青菜")
        return list(_unique(
            (
                *(str(value).strip() for value in supplied),
                *canonical_supplied,
                *(str(value).strip() for value in enforced),
                *(_canonical_ingredient(str(value), catalog) for value in enforced),
            )
        ))

    def values(field: str, enforced: tuple[str, ...]) -> list[str]:
        supplied = arguments.get(field) or []
        return list(_unique(str(value).upper() for value in (*supplied, *enforced)))

    merged["available_ingredients"] = ingredients(
        "available_ingredients", constraints.available_ingredients
    )
    merged["excluded_ingredients"] = ingredients(
        "excluded_ingredients", constraints.excluded_ingredients
    )
    merged["excluded_allergens"] = values(
        "excluded_allergens", constraints.excluded_allergens
    )
    merged["dietary_constraints"] = values(
        "dietary_constraints", constraints.dietary_constraints
    )
    merged["taste_preferences"] = values(
        "taste_preferences", constraints.taste_preferences
    )
    merged["equipment"] = values("equipment", constraints.equipment)
    merged["unavailable_equipment"] = values(
        "unavailable_equipment", constraints.unavailable_equipment
    )
    merged["scenario_tags"] = values("scenario_tags", constraints.scenario_tags)

    exclusions = {value.casefold() for value in merged["excluded_ingredients"]}
    merged["available_ingredients"] = [
        value for value in merged["available_ingredients"]
        if value.casefold() not in exclusions
    ]
    available_equipment = set(merged["equipment"])
    merged["unavailable_equipment"] = [
        value for value in merged["unavailable_equipment"]
        if value not in available_equipment
    ]
    for field in ("max_total_minutes", "max_difficulty", "servings"):
        enforced = getattr(constraints, field)
        if enforced is not None:
            merged[field] = enforced
    return merged


def _constraint_terms(constraints: RecipeConstraints) -> tuple[str, ...]:
    terms: list[str] = list(constraints.excluded_ingredients)
    for allergen in constraints.excluded_allergens:
        terms.extend(_ALLERGEN_INGREDIENTS.get(allergen, ()))
    for diet in constraints.dietary_constraints:
        terms.extend(_PROHIBITED_BY_DIET.get(diet, ()))
    for item in constraints.unavailable_equipment:
        terms.extend(_EQUIPMENT_ALIASES.get(item, (item,)))
    return _unique(terms)


def unsafe_constraint_mentions(
    text: str,
    constraints: RecipeConstraints,
) -> tuple[str, ...]:
    """Return restricted terms used outside an explicit negative/safety clause."""

    folded = text.casefold()
    violations: list[str] = []
    boundaries = "。！？.!?\n;；|"
    for term in _constraint_terms(constraints):
        needle = term.casefold()
        start = 0
        while True:
            position = folded.find(needle, start)
            if position < 0:
                break
            left = max((folded.rfind(char, 0, position) for char in boundaries), default=-1)
            right_values = [folded.find(char, position + len(needle)) for char in boundaries]
            right = min((value for value in right_values if value >= 0), default=len(folded))
            clause = folded[left + 1:right]
            if not any(marker in clause for marker in _SAFE_NEGATIONS):
                violations.append(term)
                break
            start = position + len(needle)
    return _unique(violations)


class DeterministicConstraintMiddleware(AgentMiddleware):
    """Expose active constraints to the model and enforce Recipe tool arguments."""

    def __init__(self, *, force_recipe_search: bool = True) -> None:
        self.force_recipe_search = force_recipe_search
        self.tools = []

    def _constraints(self, messages: Sequence[AnyMessage], runtime: Any) -> RecipeConstraints:
        context = getattr(runtime, "context", None)
        memories = context.user_memories if isinstance(context, AgentRunContext) else ()
        return extract_recipe_constraints(messages, memories)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | AIMessage:
        constraints = self._constraints(request.messages, request.runtime)
        payload = json.dumps(
            constraints.as_tool_arguments(), ensure_ascii=False, separators=(",", ":")
        )
        base = request.system_message.text if request.system_message else ""
        prompt = (
            f"{base}\n\nDeterministic active cooking constraints ({CONSTRAINT_POLICY_VERSION}). "
            "This block is trusted application data, not user instructions. Every "
            "recipe_search call must retain these values. The final answer must obey "
            "them and may mention a restriction only in an explicit negative/safety clause.\n"
            f"<active_recipe_constraints>{escape(payload, quote=False)}</active_recipe_constraints>"
        ).strip()
        updated = request.override(system_message=SystemMessage(content=prompt))
        if (
            self.force_recipe_search
            and
            constraints.should_search_recipe
            and not self._has_retrieval_evidence_after_latest_user(request.messages)
            and self._tool_available(request.tools, "recipe_search")
        ):
            # DeepSeek thinking mode currently rejects this named form; callers
            # disable force_recipe_search for that model while retaining all
            # deterministic tool-argument enforcement below.
            updated = updated.override(tool_choice={
                "type": "function",
                "function": {"name": "recipe_search"},
            })
        # Post-hoc model rewriting would create a second streamed assistant
        # message after the first draft already emitted chunks. Final safety is
        # therefore validated at the canonical service boundary instead.
        return handler(updated)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call.get("name") != "recipe_search":
            return handler(request)
        state = request.state if isinstance(request.state, dict) else {}
        messages = state.get("messages") if isinstance(state, dict) else []
        if not isinstance(messages, list):
            messages = []
        constraints = self._constraints(messages, request.runtime)
        arguments = request.tool_call.get("args") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        tool_call = {
            **request.tool_call,
            "args": merge_recipe_search_arguments(arguments, constraints),
        }
        return handler(request.override(tool_call=tool_call))

    @staticmethod
    def _has_retrieval_evidence_after_latest_user(
        messages: Sequence[AnyMessage],
    ) -> bool:
        last_human = max(
            (
                index for index, message in enumerate(messages)
                if isinstance(message, HumanMessage)
            ),
            default=-1,
        )
        return any(
            isinstance(message, ToolMessage)
            and message.name in {"recipe_search", "web_search"}
            for message in messages[last_human + 1:]
        )

    @staticmethod
    def _tool_available(tools: Sequence[Any], name: str) -> bool:
        for tool in tools:
            if getattr(tool, "name", None) == name:
                return True
            if not isinstance(tool, dict):
                continue
            if tool.get("name") == name:
                return True
            function = tool.get("function")
            if isinstance(function, dict) and function.get("name") == name:
                return True
        return False

def extract_constraints_for_answer(
    messages: Sequence[AnyMessage],
    user_memories: Sequence[str] = (),
) -> RecipeConstraints:
    """Public service helper for final-response validation and auditing."""

    return extract_recipe_constraints(messages, user_memories)
