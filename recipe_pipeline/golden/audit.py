"""Semantic cooking audit kept separate from deterministic schema validation."""

from __future__ import annotations

from recipe_pipeline.golden.models import AuditDecision, SemanticAuditItem
from recipe_pipeline.schemas.recipe import NutritionLevel, RecipeV1


SEMANTIC_AUDITOR_PROMPT = """recipe_semantic_auditor_v1
Audit culinary coherence, executable sequence, ingredient/step and time/equipment
consistency, food safety, and unsupported claims. Do not repair or enrich recipes.
Do not invent temperatures. PASS, FLAG, or REJECT with explicit issue codes.
"""

_BANNED_CLAIMS = (
    "燃脂", "排毒", "易消化", "适合老年人", "适合儿童", "保证健康", "零失败",
    "治疗", "治愈", "降血糖", "降血压", "fat-burning", "detox", "guaranteed healthy",
)
_SAFETY_NAMES = {
    "鸡肉", "鸡腿", "鸡翅", "整鸡", "鸭肉", "鸭腿", "鸡胗", "鸡爪", "猪肉", "五花肉",
    "猪排骨", "猪蹄", "猪肝", "猪肚", "肉馅", "牛肉", "羊肉", "羊排", "鱼", "鲈鱼",
    "草鱼", "鲫鱼", "鳕鱼", "带鱼", "金枪鱼", "三文鱼", "虾", "鱿鱼", "蛤蜊", "扇贝",
    "螃蟹", "鸡蛋",
}


class CodexSemanticRecipeAuditor:
    """Deterministic executable form of the independently versioned audit policy."""

    def audit(self, recipe: RecipeV1) -> SemanticAuditItem:
        issues: list[str] = []
        reasons: list[str] = []
        searchable = " ".join(
            [recipe.identity.name, recipe.identity.summary]
            + [step.instruction for step in recipe.steps]
            + [step.safety_note or "" for step in recipe.steps]
        ).casefold()
        for claim in _BANNED_CLAIMS:
            if claim.casefold() in searchable:
                issues.append("UNSUPPORTED_CLAIM")
                reasons.append(f"unsupported claim detected: {claim}")
                break
        nutrition = recipe.nutrition
        if any(value is not None for value in (nutrition.calories_kcal, nutrition.protein_g, nutrition.fat_g, nutrition.carbohydrate_g)) or nutrition.protein_level != NutritionLevel.UNKNOWN or nutrition.fat_level != NutritionLevel.UNKNOWN:
            issues.append("UNVERIFIED_SYNTHETIC_NUTRITION")
            reasons.append("synthetic nutrition must remain null/UNKNOWN")
        ingredient_ids = {item.ingredient_id for item in recipe.ingredients}
        referenced = {ref for step in recipe.steps for ref in step.ingredient_refs}
        if not ingredient_ids.issubset(referenced):
            issues.append("INGREDIENT_STEP_INCONSISTENCY")
            reasons.append("one or more declared ingredients are unused")
        declared_equipment = set(recipe.equipment.required) | set(recipe.equipment.optional)
        step_equipment = {item for step in recipe.steps for item in step.equipment_refs}
        if not step_equipment.issubset(declared_equipment):
            issues.append("EQUIPMENT_INCONSISTENCY")
            reasons.append("a step requires undeclared equipment")
        duration = sum(step.duration_minutes for step in recipe.steps)
        if duration > recipe.time.total_minutes * 1.5 or recipe.time.total_minutes < 5:
            issues.append("TIME_UNREALISTIC")
            reasons.append("step and total times are not mutually plausible")
        names = {item.normalized_name for item in recipe.ingredients}
        safety_sensitive = bool(names & _SAFETY_NAMES)
        if safety_sensitive and not any(step.safety_note for step in recipe.steps):
            issues.append("FOOD_SAFETY_CUE_MISSING")
            reasons.append("animal protein or egg has no explicit doneness/safety cue")
        if not any(step.phase.value == "COOK" for step in recipe.steps) and names & (_SAFETY_NAMES - {"金枪鱼"}):
            issues.append("COOKING_STAGE_MISSING")
            reasons.append("raw-sensitive ingredient lacks a cooking stage")
        reject_codes = {
            "UNSUPPORTED_CLAIM", "UNVERIFIED_SYNTHETIC_NUTRITION",
            "INGREDIENT_STEP_INCONSISTENCY", "EQUIPMENT_INCONSISTENCY",
            "FOOD_SAFETY_CUE_MISSING", "COOKING_STAGE_MISSING",
        }
        decision = AuditDecision.REJECT if set(issues) & reject_codes else (AuditDecision.FLAG if issues else AuditDecision.PASS)
        score = max(0.0, round(1.0 - 0.18 * len(issues), 3))
        return SemanticAuditItem(
            recipe_id=str(recipe.recipe_id), recipe_name=recipe.identity.name,
            decision=decision, score=score, issue_codes=issues,
            reasons=reasons or ["culinary, consistency, safety, claims, and time checks passed"],
            safety_sensitive=safety_sensitive,
        )

    def audit_all(self, recipes: list[RecipeV1]) -> list[SemanticAuditItem]:
        return [self.audit(recipe) for recipe in recipes]
