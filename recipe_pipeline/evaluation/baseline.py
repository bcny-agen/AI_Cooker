"""Explainable offline baseline: normalized ingredients plus keyword rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from recipe_pipeline.normalization import IngredientCatalog
from recipe_pipeline.schemas.recipe import (
    AllergenTag,
    CookingMethod,
    DietaryTag,
    EquipmentName,
    RecipeV1,
    ScenarioTag,
)


class Preference(str, Enum):
    LOW_OIL = "LOW_OIL"
    NON_SPICY = "NON_SPICY"
    HIGH_PROTEIN = "HIGH_PROTEIN"
    VEGETARIAN = "VEGETARIAN"
    VEGAN = "VEGAN"


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    original: str
    ingredient_ids: frozenset[UUID]
    ingredient_names: tuple[str, ...]
    scenario_tags: frozenset[ScenarioTag]
    preferences: frozenset[Preference]
    max_minutes: int | None
    exclude_spicy: bool
    preferred_max_difficulty: int | None
    dish_terms: tuple[str, ...]
    excluded_ingredient_ids: frozenset[UUID] = frozenset()
    excluded_allergens: frozenset[AllergenTag] = frozenset()
    unavailable_equipment: frozenset[EquipmentName] = frozenset()

    def expanded_text(self) -> str:
        return " ".join(
            (
                self.original,
                *self.ingredient_names,
                *(tag.value for tag in self.scenario_tags),
                *(preference.value for preference in self.preferences),
                *self.dish_terms,
                f"{self.max_minutes}分钟" if self.max_minutes is not None else "",
                "排除辣味" if self.exclude_spicy else "",
                (
                    f"难度不高于{self.preferred_max_difficulty}"
                    if self.preferred_max_difficulty is not None
                    else ""
                ),
            )
        )


@dataclass(frozen=True, slots=True)
class BaselineCandidate:
    recipe: RecipeV1
    score: float
    ingredient_coverage: float
    preference_match: float | None


_SCENARIO_KEYWORDS = {
    ScenarioTag.QUICK_MEAL: ("快手", "快速", "quick", "分钟能做", "分钟以内"),
    ScenarioTag.BEGINNER_FRIENDLY: ("新手", "初学", "beginner", "简单"),
    ScenarioTag.AIR_FRYER: ("空气炸锅", "air fryer"),
    ScenarioTag.HEALTHY_MEAL: ("健康", "healthy"),
    ScenarioTag.FAMILY_MEAL: ("一家人", "家庭", "家常", "family"),
    ScenarioTag.STUDENT_COOKING: ("学生", "宿舍", "student"),
}

_PREFERENCE_KEYWORDS = {
    Preference.LOW_OIL: ("少油", "低油", "清淡", "low oil"),
    Preference.NON_SPICY: ("不辣", "不吃辣", "不要辣", "non-spicy", "not spicy"),
    Preference.HIGH_PROTEIN: ("高蛋白", "high protein"),
    Preference.VEGETARIAN: ("素食", "vegetarian"),
    Preference.VEGAN: ("纯素", "vegan"),
}

_DISH_TERM_KEYWORDS = {
    "汤": ("汤", "soup"),
    "面": ("面", "noodle", "noodles"),
    "饭": ("饭", "rice meal"),
    "粥": ("粥", "porridge"),
    "饼": ("饼", "pancake"),
    "沙拉": ("沙拉", "salad"),
    "炒": ("炒", "stir fry", "stir-fry"),
    "蒸": ("蒸", "steam", "steamed"),
    "炖": ("炖", "stew", "simmer"),
}

_ALLERGEN_KEYWORDS = {
    AllergenTag.EGG: ("鸡蛋过敏", "蛋过敏", "egg allergy"),
    AllergenTag.MILK: ("牛奶过敏", "乳制品过敏", "milk allergy", "dairy allergy"),
    AllergenTag.PEANUT: ("花生过敏", "peanut allergy"),
    AllergenTag.TREE_NUT: ("坚果过敏", "nut allergy"),
    AllergenTag.SOY: ("大豆过敏", "soy allergy"),
    AllergenTag.WHEAT: ("小麦过敏", "wheat allergy"),
    AllergenTag.FISH: ("鱼过敏", "fish allergy"),
    AllergenTag.SHELLFISH: ("甲壳类过敏", "海鲜过敏", "shellfish allergy"),
    AllergenTag.SESAME: ("芝麻过敏", "sesame allergy"),
}
_EQUIPMENT_KEYWORDS = {
    EquipmentName.AIR_FRYER: ("没有空气炸锅", "不用空气炸锅", "no air fryer"),
    EquipmentName.OVEN: ("没有烤箱", "不用烤箱", "no oven"),
    EquipmentName.STEAMER: ("没有蒸锅", "不用蒸锅", "no steamer"),
    EquipmentName.WOK: ("没有炒锅", "不用炒锅", "no wok"),
    EquipmentName.POT: ("没有锅", "no pot"),
}

_HIGH_PROTEIN_INGREDIENTS = {
    "猪肉",
    "牛肉",
    "鸡肉",
    "鸡腿",
    "鸡翅",
    "虾",
    "鱼",
    "三文鱼",
    "鸡蛋",
    "豆腐",
}

_LOW_OIL_METHOD_SCORES = {
    CookingMethod.MIX: 1.0,
    CookingMethod.BOIL: 1.0,
    CookingMethod.STEAM: 1.0,
    CookingMethod.SIMMER: 0.85,
    CookingMethod.AIR_FRY: 0.8,
    CookingMethod.BAKE: 0.75,
    CookingMethod.ROAST: 0.75,
    CookingMethod.PAN_FRY: 0.35,
    CookingMethod.STIR_FRY: 0.25,
    CookingMethod.PREPARE: 0.5,
}


class RecipeQueryParser:
    def __init__(self, catalog: IngredientCatalog | None = None):
        self._catalog = catalog or IngredientCatalog()

    def parse(self, query: str) -> ParsedQuery:
        normalized_query = query.casefold().replace("炒蛋", "鸡蛋").replace("煎蛋", "鸡蛋")
        ingredient_ids, ingredient_names = self._match_ingredients(normalized_query)
        excluded_ids = self._match_excluded_ingredients(normalized_query)
        if excluded_ids:
            ingredient_ids -= excluded_ids
            excluded_names = {
                entry.normalized_name
                for entry in self._catalog.entries
                if entry.ingredient_id in excluded_ids
            }
            ingredient_names = [
                name for name in ingredient_names if name not in excluded_names
            ]
        scenario_tags = frozenset(
            tag
            for tag, keywords in _SCENARIO_KEYWORDS.items()
            if any(keyword.casefold() in normalized_query for keyword in keywords)
        )
        preferences = frozenset(
            preference
            for preference, keywords in _PREFERENCE_KEYWORDS.items()
            if any(keyword.casefold() in normalized_query for keyword in keywords)
        )
        time_match = re.search(r"(\d{1,3})\s*分钟", normalized_query)
        max_minutes = int(time_match.group(1)) if time_match else None
        dish_terms = tuple(
            term
            for term, keywords in _DISH_TERM_KEYWORDS.items()
            if any(keyword.casefold() in normalized_query for keyword in keywords)
        )
        excluded_allergens = frozenset(
            allergen
            for allergen, keywords in _ALLERGEN_KEYWORDS.items()
            if any(keyword.casefold() in normalized_query for keyword in keywords)
        )
        unavailable_equipment = frozenset(
            equipment
            for equipment, keywords in _EQUIPMENT_KEYWORDS.items()
            if any(keyword.casefold() in normalized_query for keyword in keywords)
        )
        return ParsedQuery(
            original=query,
            ingredient_ids=frozenset(ingredient_ids),
            ingredient_names=tuple(ingredient_names),
            scenario_tags=scenario_tags,
            preferences=preferences,
            max_minutes=max_minutes,
            exclude_spicy=Preference.NON_SPICY in preferences,
            preferred_max_difficulty=(
                2
                if ScenarioTag.BEGINNER_FRIENDLY in scenario_tags
                else None
            ),
            dish_terms=dish_terms,
            excluded_ingredient_ids=frozenset(excluded_ids),
            excluded_allergens=excluded_allergens,
            unavailable_equipment=unavailable_equipment,
        )

    def _match_ingredients(self, query: str) -> tuple[set[UUID], list[str]]:
        aliases = sorted(
            (
                (alias.casefold(), entry)
                for entry in self._catalog.entries
                for alias in entry.aliases
                if len(alias.strip()) >= 2
                or (
                    alias == entry.normalized_name
                    and entry.normalized_name in {"鱼", "虾"}
                )
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        occupied: set[int] = set()
        matched_ids: set[UUID] = set()
        matched_names: list[str] = []
        for alias, entry in aliases:
            pattern = (
                rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
                if alias.isascii()
                else re.escape(alias)
            )
            for match in re.finditer(pattern, query):
                positions = set(range(match.start(), match.end()))
                if positions & occupied:
                    continue
                occupied.update(positions)
                if entry.ingredient_id not in matched_ids:
                    matched_ids.add(entry.ingredient_id)
                    matched_names.append(entry.normalized_name)
        return matched_ids, matched_names

    def _match_excluded_ingredients(self, query: str) -> set[UUID]:
        excluded: set[UUID] = set()
        for entry in self._catalog.entries:
            for alias in entry.aliases:
                escaped = re.escape(alias.casefold())
                patterns = (
                    rf"(?:不吃|不要|排除|忌口)\s*{escaped}",
                    rf"(?:without|exclude|no)\s+{escaped}(?![a-z0-9])",
                )
                if any(re.search(pattern, query) for pattern in patterns):
                    excluded.add(entry.ingredient_id)
                    break
        return excluded


class BaselineRecipeRetriever:
    def __init__(
        self,
        recipes: list[RecipeV1],
        parser: RecipeQueryParser | None = None,
    ):
        self._recipes = recipes
        self.parser = parser or RecipeQueryParser()

    def retrieve(self, query: str, top_k: int = 5) -> list[BaselineCandidate]:
        parsed = self.parser.parse(query)
        candidates = [
            self.score_recipe(recipe, parsed)
            for recipe in self._recipes
            if self.satisfies_hard_constraints(recipe, parsed)
        ]
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return candidates[:top_k]

    @staticmethod
    def satisfies_hard_constraints(recipe: RecipeV1, parsed: ParsedQuery) -> bool:
        ingredient_ids = {item.ingredient_id for item in recipe.ingredients}
        if ingredient_ids & parsed.excluded_ingredient_ids:
            return False
        if set(recipe.tags.allergens) & parsed.excluded_allergens:
            return False
        if set(recipe.equipment.required) & parsed.unavailable_equipment:
            return False
        if parsed.exclude_spicy and recipe.taste_profile.spicy > 0:
            return False
        if parsed.max_minutes is not None and recipe.time.total_minutes > parsed.max_minutes:
            return False
        if Preference.VEGAN in parsed.preferences and DietaryTag.VEGAN not in recipe.tags.dietary:
            return False
        if (
            Preference.VEGETARIAN in parsed.preferences
            and not ({DietaryTag.VEGETARIAN, DietaryTag.VEGAN} & set(recipe.tags.dietary))
        ):
            return False
        return True

    def score_recipe(self, recipe: RecipeV1, parsed: ParsedQuery) -> BaselineCandidate:
        recipe_ingredient_ids = {item.ingredient_id for item in recipe.ingredients}
        if parsed.ingredient_ids:
            ingredient_coverage = len(
                recipe_ingredient_ids & parsed.ingredient_ids
            ) / len(parsed.ingredient_ids)
        else:
            ingredient_coverage = 0.0

        score = ingredient_coverage * 8.0
        if parsed.ingredient_ids and ingredient_coverage == 1.0:
            score += 3.0
        recipe_name = recipe.identity.name.casefold()
        compact_query = re.sub(r"\W+", "", parsed.original.casefold())
        compact_name = re.sub(r"\W+", "", recipe_name)
        if compact_name and compact_name in compact_query:
            score += 5.0
        score += sum(2.0 for term in parsed.dish_terms if term in recipe_name)

        recipe_scenarios = set(recipe.tags.scenario)
        score += 3.0 * len(recipe_scenarios & parsed.scenario_tags)
        if parsed.max_minutes is not None:
            if recipe.time.total_minutes <= parsed.max_minutes:
                score += 3.0
                score += max(0.0, (parsed.max_minutes - recipe.time.total_minutes) / 30)
            else:
                score -= min(3.0, (recipe.time.total_minutes - parsed.max_minutes) / 10)

        preference_match = self._preference_match(recipe, parsed.preferences)
        if preference_match is not None:
            score += preference_match * 3.0

        query_terms = self._simple_terms(parsed.original)
        recipe_terms = self._simple_terms(
            " ".join((recipe.identity.name, recipe.identity.summary))
        )
        if query_terms:
            score += len(query_terms & recipe_terms) / len(query_terms)
        score += recipe.quality.confidence_score * 0.01
        return BaselineCandidate(
            recipe=recipe,
            score=round(score, 6),
            ingredient_coverage=round(ingredient_coverage, 6),
            preference_match=(
                round(preference_match, 6)
                if preference_match is not None
                else None
            ),
        )

    @staticmethod
    def _preference_match(
        recipe: RecipeV1, preferences: frozenset[Preference]
    ) -> float | None:
        if not preferences:
            return None
        ingredient_names = {item.normalized_name for item in recipe.ingredients}
        methods = {step.method for step in recipe.steps}
        scores = []
        for preference in preferences:
            if preference == Preference.LOW_OIL:
                cooking_methods = methods - {CookingMethod.PREPARE}
                scores.append(
                    max(
                        _LOW_OIL_METHOD_SCORES[method]
                        for method in (cooking_methods or methods)
                    )
                )
            elif preference == Preference.NON_SPICY:
                scores.append(1.0 if recipe.taste_profile.spicy == 0 else 0.0)
            elif preference == Preference.HIGH_PROTEIN:
                scores.append(1.0 if ingredient_names & _HIGH_PROTEIN_INGREDIENTS else 0.0)
            elif preference == Preference.VEGETARIAN:
                scores.append(1.0 if DietaryTag.VEGETARIAN in recipe.tags.dietary else 0.0)
            elif preference == Preference.VEGAN:
                scores.append(1.0 if DietaryTag.VEGAN in recipe.tags.dietary else 0.0)
        return sum(scores) / len(scores)

    @staticmethod
    def _simple_terms(text: str) -> set[str]:
        lowered = text.casefold()
        latin = set(re.findall(r"[a-z0-9]+", lowered))
        cjk_sequences = re.findall(r"[\u4e00-\u9fff]+", lowered)
        cjk_bigrams = {
            sequence[index : index + 2]
            for sequence in cjk_sequences
            for index in range(max(0, len(sequence) - 1))
        }
        return latin | cjk_bigrams
