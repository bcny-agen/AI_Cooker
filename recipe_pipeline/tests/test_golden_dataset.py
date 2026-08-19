from __future__ import annotations

import unittest

from recipe_pipeline.golden.audit import CodexSemanticRecipeAuditor
from recipe_pipeline.golden.catalog import get_golden_blueprints
from recipe_pipeline.golden.duplicates import SemanticDuplicateReviewer
from recipe_pipeline.golden.generation import (
    CANONICAL_GENERATOR_PROMPT,
    BoundedCanonicalGenerationCoordinator,
    CodexCanonicalRecipeGenerator,
    DeterministicRecipeEnricher,
)
from recipe_pipeline.golden.models import AuditDecision
from recipe_pipeline.golden.reports import build_diversity_report, build_human_review_sample
from recipe_pipeline.golden.retrieval import build_golden_query_splits
from recipe_pipeline.golden.vocabulary import IngredientVocabularyReviewQueue, VocabularyDecision
from recipe_pipeline.normalization.recipe import RecipeNormalizer
from recipe_pipeline.schemas.recipe import NutritionLevel


def _normalized(count: int):
    generator = CodexCanonicalRecipeGenerator()
    enricher = DeterministicRecipeEnricher()
    normalizer = RecipeNormalizer()
    return [
        normalizer.normalize(enricher.enrich(generator.generate(item)))
        for item in get_golden_blueprints()[:count]
    ]


def test_canonical_generation_has_only_reliable_core_contract():
    content = CodexCanonicalRecipeGenerator().generate(get_golden_blueprints()[0])
    assert content.name == "麻婆豆腐"
    assert content.ingredients
    assert content.steps
    assert "nutrition" not in type(content).model_fields
    assert "Do not generate nutrition numbers" in CANONICAL_GENERATOR_PROMPT


def test_enrichment_does_not_rewrite_canonical_content_and_nutrition_is_unknown():
    content = CodexCanonicalRecipeGenerator().generate(get_golden_blueprints()[0])
    ingredients = [item.model_dump() for item in content.ingredients]
    steps = [item.model_dump() for item in content.steps]
    raw = DeterministicRecipeEnricher().enrich(content)
    assert [item.model_dump() for item in raw.ingredients] == ingredients
    assert [item.model_dump() for item in raw.steps] == steps
    assert raw.nutrition.calories_kcal is None
    assert raw.nutrition.protein_level == NutritionLevel.UNKNOWN
    assert raw.source.generator_model == "gpt-5.6-sol"


def test_semantic_audit_rejects_claims_and_missing_safety():
    recipe = _normalized(1)[0]
    claimed = recipe.model_copy(update={
        "identity": recipe.identity.model_copy(update={"summary": "这是一道保证健康并可以排毒的家常料理。"})
    })
    assert CodexSemanticRecipeAuditor().audit(claimed).decision == AuditDecision.REJECT
    unsafe = recipe.model_copy(update={
        "steps": [step.model_copy(update={"safety_note": None}) for step in recipe.steps]
    })
    result = CodexSemanticRecipeAuditor().audit(unsafe)
    assert result.decision == AuditDecision.REJECT
    assert "FOOD_SAFETY_CUE_MISSING" in result.issue_codes


def test_unknown_ingredient_enters_review_queue_and_alias_maps():
    queue = IngredientVocabularyReviewQueue()
    assert queue.review("西红柿").decision == VocabularyDecision.MAP
    assert queue.review("想象中的星云菜").decision == VocabularyDecision.REVIEW
    assert queue.review("想象中的星云菜").ingredient_id is None


def test_generation_retry_is_bounded_to_one_retry():
    class FailOnce(CodexCanonicalRecipeGenerator):
        def __init__(self):
            self.calls = 0

        def generate_batch(self, blueprints):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("malformed batch")
            return super().generate_batch(blueprints)

    generator = FailOnce()
    generated, rejected, retries = BoundedCanonicalGenerationCoordinator(generator).run(get_golden_blueprints()[:3])
    assert len(generated) == 3
    assert rejected == []
    assert retries == 1
    assert generator.calls == 2


def test_semantic_duplicate_detection_uses_identity_ingredients_and_method():
    first = CodexCanonicalRecipeGenerator().generate(get_golden_blueprints()[0])
    renamed = first.model_copy(update={"record_id": "duplicate-record", "name": "家常麻婆豆腐"})
    enricher = DeterministicRecipeEnricher()
    normalizer = RecipeNormalizer()
    recipes = [normalizer.normalize(enricher.enrich(first)), normalizer.normalize(enricher.enrich(renamed))]
    matches = SemanticDuplicateReviewer().review(recipes)
    assert matches
    assert matches[0].decision in {"REJECT_RIGHT", "HUMAN_REVIEW"}
    assert matches[0].core_ingredient_jaccard == 1.0


def test_diversity_report_and_human_sample_are_review_friendly():
    recipes = _normalized(60)
    collections = {
        str(recipe.recipe_id): get_golden_blueprints()[index].collection.value
        for index, recipe in enumerate(recipes)
    }
    audits = CodexSemanticRecipeAuditor().audit_all(recipes)
    diversity = build_diversity_report(recipes, collections, [])
    sample = build_human_review_sample(recipes, collections, audits, [], size=50)
    assert diversity["unique_recipes"] == 60
    assert diversity["unique_normalized_ingredients"] > 10
    assert sample["sample_size"] == 50
    assert sample["human_review_completed"] is False
    assert all(item["recipe"]["quality"]["human_reviewed"] is False for item in sample["items"])


def test_development_and_holdout_queries_and_targets_are_disjoint():
    recipes = _normalized(150)
    development, holdout = build_golden_query_splits(recipes)
    assert len(development) == 50
    assert len(holdout) == 75
    assert not ({item["query"] for item in development} & {item["query"] for item in holdout})
    assert not ({item["expected_recipe_ids"][0] for item in development} & {item["expected_recipe_ids"][0] for item in holdout})
    assert all(item["expected_recipe_ids"] for item in development + holdout)


class GoldenDatasetTests(unittest.TestCase):
    """Expose the same pure tests to the repository's unittest runner."""

    def test_canonical_generation(self):
        test_canonical_generation_has_only_reliable_core_contract()

    def test_enrichment_isolation_and_unknown_nutrition(self):
        test_enrichment_does_not_rewrite_canonical_content_and_nutrition_is_unknown()

    def test_claim_and_food_safety_audit(self):
        test_semantic_audit_rejects_claims_and_missing_safety()

    def test_unknown_ingredient_review_queue(self):
        test_unknown_ingredient_enters_review_queue_and_alias_maps()

    def test_bounded_retry(self):
        test_generation_retry_is_bounded_to_one_retry()

    def test_semantic_duplicate_detection(self):
        test_semantic_duplicate_detection_uses_identity_ingredients_and_method()

    def test_diversity_and_human_sample(self):
        test_diversity_report_and_human_sample_are_review_friendly()

    def test_development_holdout_separation(self):
        test_development_and_holdout_queries_and_targets_are_disjoint()
