"""Diversity metrics and stratified human-review sampling."""

from __future__ import annotations

from collections import Counter, defaultdict

from recipe_pipeline.golden.models import DuplicateReviewItem, PrimaryCollection, SemanticAuditItem
from recipe_pipeline.schemas.recipe import IngredientImportance, RecipeV1


def build_diversity_report(recipes: list[RecipeV1], collections: dict[str, str], duplicates: list[DuplicateReviewItem]) -> dict:
    ingredient_counts = Counter(item.normalized_name for recipe in recipes for item in recipe.ingredients if item.importance == IngredientImportance.CORE)
    cuisine = Counter(recipe.identity.cuisine.value for recipe in recipes)
    regions = Counter(recipe.identity.region.value for recipe in recipes)
    methods = Counter(tag.value for recipe in recipes for tag in recipe.tags.technique)
    difficulty = Counter(str(recipe.difficulty.level) for recipe in recipes)
    scenarios = Counter(tag.value for recipe in recipes for tag in recipe.tags.scenario)
    equipment = Counter(item.value for recipe in recipes for item in recipe.equipment.required)
    collection_counts = Counter(collections.get(str(recipe.recipe_id), "UNKNOWN") for recipe in recipes)
    total = max(1, len(recipes))
    warnings = []
    for name, count in ingredient_counts.items():
        if count / total > 0.2:
            warnings.append({"type": "INGREDIENT_CONCENTRATION", "name": name, "ratio": round(count / total, 4)})
    for name, count in methods.items():
        if count / total > 0.35:
            warnings.append({"type": "METHOD_CONCENTRATION", "name": name, "ratio": round(count / total, 4)})
    adjacency: dict[str, set[str]] = defaultdict(set)
    for item in duplicates:
        adjacency[item.left_recipe_id].add(item.right_recipe_id)
        adjacency[item.right_recipe_id].add(item.left_recipe_id)
    seen: set[str] = set()
    duplicate_cluster_count = 0
    for node in adjacency:
        if node in seen:
            continue
        duplicate_cluster_count += 1
        stack = [node]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adjacency[current] - seen)
    return {
        "unique_recipes": len({recipe.identity.name.casefold() for recipe in recipes}),
        "unique_normalized_ingredients": len(ingredient_counts),
        "ingredient_frequency": dict(ingredient_counts.most_common()),
        "top_overrepresented_ingredients": [{"ingredient": name, "count": count, "ratio": round(count / total, 4)} for name, count in ingredient_counts.most_common(20)],
        "primary_collection_distribution": dict(collection_counts),
        "cuisine_distribution": dict(cuisine), "region_distribution": dict(regions),
        "cooking_method_distribution": dict(methods), "difficulty_distribution": dict(difficulty),
        "scenario_distribution": dict(scenarios), "equipment_distribution": dict(equipment),
        "duplicate_review_pairs": len(duplicates),
        "duplicate_clusters": duplicate_cluster_count,
        "concentration_warnings": warnings,
    }


def build_human_review_sample(recipes: list[RecipeV1], collections: dict[str, str], audits: list[SemanticAuditItem], duplicates: list[DuplicateReviewItem], size: int = 50) -> dict:
    audit_by_id = {item.recipe_id: item for item in audits}
    duplicate_ids = {item.left_recipe_id for item in duplicates} | {item.right_recipe_id for item in duplicates}
    groups: dict[str, list[RecipeV1]] = defaultdict(list)
    for recipe in recipes:
        groups[collections.get(str(recipe.recipe_id), "UNKNOWN")].append(recipe)
    selected: list[RecipeV1] = []
    for collection in PrimaryCollection:
        rows = sorted(groups.get(collection.value, []), key=lambda item: (item.quality.confidence_score, item.identity.name))
        if rows:
            picks = [rows[0], rows[-1]] + [row for row in rows if audit_by_id.get(str(row.recipe_id)) and audit_by_id[str(row.recipe_id)].safety_sensitive][:3]
            for row in picks:
                if row not in selected:
                    selected.append(row)
    priority = sorted(recipes, key=lambda item: (
        str(item.recipe_id) not in duplicate_ids,
        not (audit_by_id.get(str(item.recipe_id)) and audit_by_id[str(item.recipe_id)].safety_sensitive),
        item.quality.confidence_score,
        item.identity.name,
    ))
    for recipe in priority:
        if len(selected) >= size:
            break
        if recipe not in selected:
            selected.append(recipe)
    selected = selected[:size]
    return {
        "sample_size": len(selected),
        "human_review_completed": False,
        "selection_policy": ["each primary collection", "lowest and highest accepted quality", "food-safety-sensitive", "possible near-duplicates", "deterministic fill"],
        "items": [
            {
                "recipe": recipe.model_dump(mode="json"),
                "primary_collection": collections.get(str(recipe.recipe_id)),
                "review_reasons": [
                    reason for condition, reason in (
                        (audit_by_id.get(str(recipe.recipe_id)) and audit_by_id[str(recipe.recipe_id)].safety_sensitive, "FOOD_SAFETY_SENSITIVE"),
                        (str(recipe.recipe_id) in duplicate_ids, "POSSIBLE_NEAR_DUPLICATE"),
                    ) if condition
                ] or ["STRATIFIED_QUALITY_SAMPLE"],
            }
            for recipe in selected
        ],
    }
