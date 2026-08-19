"""Transparent deterministic scoring for final Agent answers and tool traces."""

from __future__ import annotations

from collections.abc import Iterable
import json
import re
from statistics import mean
from typing import Any

from recipe_pipeline.agent_eval.models import (
    EvaluationStrategy,
    ExpectedBehavior,
    SCORING_VERSION,
)


WEIGHTS = {
    "hard_constraint_compliance": 0.30,
    "ingredient_usefulness": 0.20,
    "recommendation_relevance": 0.20,
    "grounding": 0.15,
    "diversity": 0.05,
    "soft_preference_match": 0.05,
    "tool_efficiency": 0.05,
}

ALIASES: dict[str, tuple[str, ...]] = {
    "番茄": ("番茄", "西红柿", "tomato"),
    "鸡蛋": ("鸡蛋", "egg"),
    "青椒": ("青椒", "甜椒", "bell pepper", "pepper"),
    "豆腐": ("豆腐", "tofu"),
    "蘑菇": ("蘑菇", "香菇", "mushroom"),
    "土豆": ("土豆", "马铃薯", "potato"),
    "鸡胸肉": ("鸡胸肉", "chicken breast"),
    "鸡肉": ("鸡肉", "chicken"),
    "茄子": ("茄子", "eggplant", "aubergine"),
    "虾仁": ("虾仁", "虾", "shrimp", "prawn"),
    "西兰花": ("西兰花", "broccoli"),
    "米饭": ("米饭", "rice"),
    "葱": ("葱", "scallion", "green onion"),
    "eggplant": ("eggplant", "aubergine", "茄子"),
    "pork": ("pork", "猪肉"),
    "tofu": ("tofu", "豆腐"),
    "mushroom": ("mushroom", "蘑菇", "香菇"),
    "potato": ("potato", "土豆", "马铃薯"),
    "bell pepper": ("bell pepper", "pepper", "青椒", "甜椒"),
    "beef": ("beef", "牛肉"),
    "shrimp": ("shrimp", "prawn", "虾"),
    "broccoli": ("broccoli", "西兰花"),
    "zucchini": ("zucchini", "courgette", "西葫芦"),
    "egg": ("egg", "鸡蛋"),
    "rice": ("rice", "米饭"),
    "scallion": ("scallion", "green onion", "葱"),
}

ALLERGEN_TERMS = {
    "PEANUT": ("花生", "peanut"),
    "TREE_NUT": ("坚果", "核桃", "杏仁", "nut", "walnut", "almond"),
    "MILK": ("牛奶", "奶油", "黄油", "milk", "cream", "butter"),
    "EGG": ("鸡蛋", "蛋液", "egg"),
    "WHEAT": ("小麦", "面粉", "wheat", "flour"),
    "FISH": ("鱼", "三文鱼", "鳕鱼", "fish", "salmon", "cod"),
    "SHELLFISH": ("虾", "蟹", "贝", "shrimp", "prawn", "crab", "shellfish"),
    "SESAME": ("芝麻", "sesame"),
}

DIET_FORBIDDEN = {
    "VEGETARIAN": (
        "鸡肉", "鸡胸", "鸡翅", "牛肉", "猪肉", "排骨", "鱼", "虾", "蟹",
        "chicken", "beef", "pork", "fish", "shrimp", "prawn", "crab",
    ),
    "VEGAN": (
        "鸡肉", "牛肉", "猪肉", "鱼", "虾", "鸡蛋", "牛奶", "奶油", "黄油",
        "chicken", "beef", "pork", "fish", "shrimp", "egg", "milk", "cream", "butter",
    ),
}

EQUIPMENT_TERMS = {
    "OVEN": ("烤箱", "oven"),
    "STOVE": ("炉灶", "灶", "炉子", "stove"),
    "WOK": ("炒锅", "wok"),
}

PREFERENCE_TERMS = {
    "LOW_OIL": ("少油", "低油", "少放油", "less oil", "low-oil"),
    "NON_SPICY": ("不辣", "非辣", "不放辣", "non-spicy", "not spicy"),
    "LOW_SALT": ("少盐", "低盐", "less salt", "low-salt"),
    "HIGH_PROTEIN": ("高蛋白", "high protein"),
    "LIGHT": ("清淡", "light"),
    "HEALTHY": ("健康", "healthy"),
    "QUICK": ("快速", "快手", "quick"),
}

NEGATIONS = (
    "不要", "不放", "不含", "未含", "未发现", "未列出", "没有", "无",
    "不用", "避免", "回避", "排除", "去掉", "无需", "不能", "过敏",
    "替代", "代替", "取代", "接近", "类似", "效果", "do not", "don't",
    "avoid", "without", "no ", "instead of", "alternative to", "similar to",
)

EQUIPMENT_ALIASES = {
    "AIR_FRYER": ("AIR_FRYER", "空气炸锅"),
    "RICE_COOKER": ("RICE_COOKER", "电饭锅"),
    "MICROWAVE": ("MICROWAVE", "微波炉"),
    "STEAMER": ("STEAMER", "蒸锅"),
    "PAN": ("PAN", "平底锅"),
    "OVEN": ("OVEN", "烤箱"),
    "STOVE": ("STOVE", "炉灶", "灶", "炉子"),
    "WOK": ("WOK", "炒锅"),
}

FORBIDDEN_ALLERGEN_EQUIVALENTS = {
    "花生": "PEANUT",
    "坚果": "TREE_NUT",
    "牛奶": "MILK",
    "鸡蛋": "EGG",
    "芝麻": "SESAME",
}


def _contains_alias(text: str, ingredient: str) -> bool:
    folded = text.casefold()
    aliases = ALIASES.get(ingredient, (ingredient,))
    return any(alias.casefold() in folded for alias in aliases)


def _unsafe_positive_mention(text: str, term: str) -> bool:
    folded = text.casefold()
    needle = term.casefold()
    start = 0
    while True:
        position = folded.find(needle, start)
        if position < 0:
            return False
        left = max(folded.rfind(boundary, 0, position) for boundary in ("。", "！", "？", ".", "!", "?", "\n", ";", "；"))
        right_candidates = [folded.find(boundary, position + len(needle)) for boundary in ("。", "！", "？", ".", "!", "?", "\n", ";", "；")]
        right = min((value for value in right_candidates if value >= 0), default=len(folded))
        clause = folded[left + 1:right]
        if not any(negation in clause for negation in NEGATIONS):
            return True
        start = position + len(needle)


def _decode_output(output: Any) -> Any:
    if not isinstance(output, str):
        return output
    try:
        return json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return output


def _walk_mappings(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_mappings(child)


def _recipe_outputs(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recipes: list[dict[str, Any]] = []
    for call in tool_calls:
        if call.get("name") != "recipe_search":
            continue
        data = _decode_output(call.get("output"))
        if not isinstance(data, dict):
            continue
        candidates = data.get("recipes")
        if isinstance(candidates, list):
            recipes.extend(item for item in candidates if isinstance(item, dict))
    return recipes


def _evidence_text(tool_calls: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for call in tool_calls:
        value = _decode_output(call.get("output"))
        if isinstance(value, str):
            chunks.append(value)
            continue
        for mapping in _walk_mappings(value):
            for key in ("name", "title", "summary", "content", "why_matched"):
                item = mapping.get(key)
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, list):
                    chunks.extend(str(part) for part in item)
    return " ".join(chunks)


def _normalized_tokens(text: str) -> set[str]:
    english = re.findall(r"[a-z][a-z-]{2,}", text.casefold())
    chinese = [
        text[index:index + 2]
        for index in range(max(0, len(text) - 1))
        if all("\u4e00" <= char <= "\u9fff" for char in text[index:index + 2])
    ]
    stop = {"可以", "推荐", "做法", "一道", "这个", "然后", "加入", "使用", "with", "recipe", "recipes", "this", "that"}
    return {item for item in (*english, *chinese) if item not in stop}


def _grounding(answer: str, tool_calls: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    evidence = _evidence_text(tool_calls)
    if not tool_calls:
        return 0.0, {"reason": "no_retrieval_evidence", "overlap": 0.0}
    if not evidence.strip():
        return 0.0, {"reason": "empty_or_failed_retrieval", "overlap": 0.0}
    answer_tokens = _normalized_tokens(answer)
    evidence_tokens = _normalized_tokens(evidence)
    overlap = (
        len(answer_tokens & evidence_tokens) / len(answer_tokens)
        if answer_tokens else 0.0
    )
    score = min(1.0, overlap / 0.35)
    recipes = _recipe_outputs(tool_calls)
    named = [str(item.get("name", "")) for item in recipes if item.get("name")]
    mentioned_names = [name for name in named if name.casefold() in answer.casefold()]
    if named and mentioned_names:
        score = max(score, min(1.0, 0.65 + 0.1 * len(mentioned_names)))
    return round(score, 4), {
        "reason": "deterministic lexical evidence proxy",
        "answer_evidence_overlap": round(overlap, 4),
        "retrieved_recipe_names_mentioned": mentioned_names,
    }


def _diversity(answer: str, tool_calls: list[dict[str, Any]], requested: bool) -> tuple[float, dict[str, Any]]:
    if not requested:
        return 1.0, {"reason": "multiple recommendations not requested"}
    recipes = _recipe_outputs(tool_calls)
    names = [str(item.get("name", "")).strip() for item in recipes if item.get("name")]
    mentioned = [name for name in names if name.casefold() in answer.casefold()]
    candidates = mentioned or names[:3]
    normalized = {
        re.sub(r"(?:低油|少油|家常|简单|快手|经典|健康)", "", name).strip().casefold()
        for name in candidates
        if name.strip()
    }
    if len(candidates) < 2:
        return 0.4, {"reason": "fewer than two grounded candidates", "candidates": candidates}
    ratio = len(normalized) / len(candidates)
    return round(ratio, 4), {"reason": "normalized grounded recipe-name uniqueness", "candidates": candidates}


def _hard_constraints(answer: str, tool_calls: list[dict[str, Any]], expected: ExpectedBehavior) -> tuple[float, bool, list[str]]:
    checks: list[bool] = []
    violations: list[str] = []
    calls = [call for call in tool_calls if call.get("name") == "recipe_search"]
    arguments = [call.get("arguments") or {} for call in calls]

    forbidden_terms = list(expected.forbidden_ingredients)
    for allergen in expected.excluded_allergens:
        forbidden_terms.extend(ALLERGEN_TERMS.get(allergen.upper(), ()))
    for diet in expected.dietary_constraints:
        forbidden_terms.extend(DIET_FORBIDDEN.get(diet.upper(), ()))
    for equipment in expected.unavailable_equipment:
        forbidden_terms.extend(EQUIPMENT_TERMS.get(equipment.upper(), ()))

    for term in dict.fromkeys(forbidden_terms):
        safe = not _unsafe_positive_mention(answer, term)
        checks.append(safe)
        if not safe:
            violations.append(f"answer_positive_mention:{term}")

    if calls:
        for forbidden in expected.forbidden_ingredients:
            passed = any(
                _contains_alias(" ".join(map(str, args.get("excluded_ingredients", []))), forbidden)
                or FORBIDDEN_ALLERGEN_EQUIVALENTS.get(forbidden) in {
                    str(x).upper() for x in args.get("excluded_allergens", [])
                }
                for args in arguments
            )
            checks.append(passed)
            if not passed:
                violations.append(f"recipe_tool_omitted_exclusion:{forbidden}")
        for allergen in expected.excluded_allergens:
            passed = any(allergen.upper() in {str(x).upper() for x in args.get("excluded_allergens", [])} for args in arguments)
            checks.append(passed)
            if not passed:
                violations.append(f"recipe_tool_omitted_allergen:{allergen}")
        for diet in expected.dietary_constraints:
            passed = any(diet.upper() in {str(x).upper() for x in args.get("dietary_constraints", [])} for args in arguments)
            checks.append(passed)
            if not passed:
                violations.append(f"recipe_tool_omitted_diet:{diet}")
        if expected.max_time_minutes is not None:
            passed = any(args.get("max_total_minutes") == expected.max_time_minutes for args in arguments)
            checks.append(passed)
            if not passed:
                violations.append("recipe_tool_omitted_or_changed_time_limit")
        for equipment in expected.available_equipment:
            allowed = {value.casefold() for value in EQUIPMENT_ALIASES.get(equipment.upper(), (equipment,))}
            passed = any(
                bool(allowed & {str(x).casefold() for x in args.get("equipment", [])})
                for args in arguments
            )
            checks.append(passed)
            if not passed:
                violations.append(f"recipe_tool_omitted_available_equipment:{equipment}")
        for equipment in expected.unavailable_equipment:
            allowed = {value.casefold() for value in EQUIPMENT_ALIASES.get(equipment.upper(), (equipment,))}
            passed = any(
                bool(allowed & {str(x).casefold() for x in args.get("unavailable_equipment", [])})
                for args in arguments
            )
            checks.append(passed)
            if not passed:
                violations.append(f"recipe_tool_omitted_unavailable_equipment:{equipment}")

    if expected.max_time_minutes is not None:
        recipes = _recipe_outputs(tool_calls)
        stated = [item.get("total_minutes") for item in recipes if isinstance(item.get("total_minutes"), (int, float))]
        safe = not stated or all(value <= expected.max_time_minutes for value in stated)
        checks.append(safe)
        if not safe:
            violations.append("retrieved_recipe_exceeds_time_limit")

    score = mean(checks) if checks else 1.0
    critical = bool(violations)
    return round(score, 4), critical, violations


def score_turn(
    answer: str,
    tool_calls: list[dict[str, Any]],
    expected: ExpectedBehavior,
    strategy: EvaluationStrategy = EvaluationStrategy.RECIPE_RAG_FIRST,
) -> dict[str, Any]:
    """Score one completed user turn; a critical violation forces failure."""

    answer = answer or ""
    required = expected.visible_ingredients or expected.required_ingredients
    matched = [ingredient for ingredient in required if _contains_alias(answer, ingredient)]
    ingredient_score = len(matched) / len(required) if required else 1.0

    relevance_parts = [len(answer.strip()) >= 60]
    relevance_parts.append(not required or bool(matched))
    relevance_parts.append(any(term in answer.casefold() for term in ("做", "菜", "步骤", "分钟", "recipe", "cook", "dish", "source", "来源")))
    relevance_score = sum(relevance_parts) / len(relevance_parts)

    grounding_score, grounding_detail = _grounding(answer, tool_calls)
    diversity_score, diversity_detail = _diversity(answer, tool_calls, expected.request_multiple)
    hard_score, critical, violations = _hard_constraints(answer, tool_calls, expected)

    preference_checks = []
    for preference in expected.soft_preferences:
        terms = PREFERENCE_TERMS.get(preference.upper(), (preference,))
        preference_checks.append(any(term.casefold() in answer.casefold() for term in terms))
    soft_score = mean(preference_checks) if preference_checks else 1.0

    names = [call.get("name") for call in tool_calls]
    used_recipe = "recipe_search" in names
    used_web = "web_search" in names
    if strategy == EvaluationStrategy.LEGACY_WEB_FIRST and not expected.recipe_kb_may_be_used:
        tavily_failed = any(
            call.get("name") == "web_search" and call.get("error_type")
            for call in tool_calls
        )
        recipe_ok = not used_recipe or tavily_failed
        web_ok = used_web
    else:
        recipe_ok = (
            used_recipe if expected.recipe_kb_should_be_used
            else (True if expected.recipe_kb_may_be_used else not used_recipe)
        )
        web_ok = used_web == expected.web_should_be_used
    tool_score = (float(recipe_ok) + float(web_ok)) / 2

    components = {
        "hard_constraint_compliance": hard_score,
        "ingredient_usefulness": round(ingredient_score, 4),
        "recommendation_relevance": round(relevance_score, 4),
        "grounding": grounding_score,
        "diversity": diversity_score,
        "soft_preference_match": round(soft_score, 4),
        "tool_efficiency": round(tool_score, 4),
    }
    weighted = sum(components[name] * WEIGHTS[name] for name in WEIGHTS) * 100
    score = 0.0 if critical else round(weighted, 2)
    recipes = _recipe_outputs(tool_calls)
    missing_counts = [len(item.get("missing_required_ingredients") or []) for item in recipes]
    return {
        "scoring_version": SCORING_VERSION,
        "strategy_scored": strategy.value,
        "score": score,
        "scenario_pass": not critical and score >= 70,
        "critical_hard_constraint_violation": critical,
        "violations": violations,
        "components": components,
        "ingredient_matches": matched,
        "missing_ingredient_burden": round(mean(missing_counts), 3) if missing_counts else None,
        "grounding_detail": grounding_detail,
        "diversity_detail": diversity_detail,
        "judge": {
            "kind": "deterministic_proxy",
            "version": "deterministic-agent-judge-v1",
            "confidence": "low" if grounding_score < 0.4 or relevance_score < 0.67 else "medium",
            "limitations": [
                "relevance is a rubric proxy, not a blinded human rating",
                "grounding is lexical evidence overlap plus exact Recipe KB names",
                "negative-context detection is heuristic",
            ],
        },
    }
