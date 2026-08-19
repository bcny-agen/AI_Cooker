"""Four-layer duplicate review for canonical Golden recipes."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from recipe_pipeline.golden.models import DuplicateReviewItem
from recipe_pipeline.schemas.recipe import IngredientImportance, RecipeV1


def _normalized_name(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value.casefold())


def _ngrams(value: str, size: int = 3) -> set[str]:
    compact = _normalized_name(value)
    return {compact[i : i + size] for i in range(max(0, len(compact) - size + 1))}


def _jaccard(left: set, right: set) -> float:
    return len(left & right) / len(left | right) if left | right else 1.0


class SemanticDuplicateReviewer:
    def review(self, recipes: list[RecipeV1]) -> list[DuplicateReviewItem]:
        results: list[DuplicateReviewItem] = []
        for left_index, left in enumerate(recipes):
            left_name = _normalized_name(left.identity.name)
            left_core = {item.ingredient_id for item in left.ingredients if item.importance == IngredientImportance.CORE}
            left_methods = {step.method for step in left.steps if step.method.value != "PREPARE"}
            left_steps = _ngrams(" ".join(step.instruction for step in left.steps))
            for right in recipes[left_index + 1 :]:
                right_name = _normalized_name(right.identity.name)
                name_similarity = SequenceMatcher(None, left_name, right_name).ratio()
                right_core = {item.ingredient_id for item in right.ingredients if item.importance == IngredientImportance.CORE}
                ingredient_similarity = _jaccard(left_core, right_core)
                if name_similarity < 0.45 and ingredient_similarity < 0.5:
                    continue
                right_methods = {step.method for step in right.steps if step.method.value != "PREPARE"}
                method_similarity = _jaccard(left_methods, right_methods)
                step_similarity = _jaccard(left_steps, _ngrams(" ".join(step.instruction for step in right.steps)))
                if left_name == right_name:
                    decision, reason = "REJECT_RIGHT", "identical normalized recipe name"
                elif ingredient_similarity >= 0.8 and method_similarity >= 0.99 and name_similarity >= 0.55:
                    decision, reason = "REJECT_RIGHT", "same core ingredients and method with highly similar identity"
                elif (ingredient_similarity >= 0.65 and method_similarity >= 0.99) or name_similarity >= 0.78:
                    decision, reason = "HUMAN_REVIEW", "plausible canonical distinction requires human review"
                else:
                    continue
                results.append(DuplicateReviewItem(
                    left_recipe_id=str(left.recipe_id), right_recipe_id=str(right.recipe_id),
                    left_name=left.identity.name, right_name=right.identity.name,
                    name_similarity=round(name_similarity, 4),
                    core_ingredient_jaccard=round(ingredient_similarity, 4),
                    method_similarity=round(method_similarity, 4),
                    step_similarity=round(step_similarity, 4), decision=decision, reason=reason,
                ))
        return results

    @staticmethod
    def rejected_ids(items: list[DuplicateReviewItem]) -> set[str]:
        return {item.right_recipe_id for item in items if item.decision == "REJECT_RIGHT"}
