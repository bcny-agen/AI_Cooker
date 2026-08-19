"""End-to-end offline Golden Dataset v1 builder and artifact exporter."""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from recipe_pipeline.export.writer import DatasetExporter
from recipe_pipeline.golden.audit import CodexSemanticRecipeAuditor, SEMANTIC_AUDITOR_PROMPT
from recipe_pipeline.golden.catalog import get_golden_blueprints
from recipe_pipeline.golden.duplicates import SemanticDuplicateReviewer
from recipe_pipeline.golden.generation import (
    CANONICAL_GENERATOR_PROMPT,
    BoundedCanonicalGenerationCoordinator,
    CodexCanonicalRecipeGenerator,
    DeterministicRecipeEnricher,
)
from recipe_pipeline.golden.models import (
    AuditDecision,
    CANONICAL_GENERATOR_PROMPT_VERSION,
    GOLDEN_DATASET_VERSION,
    GOLDEN_GENERATOR_MODEL,
    SEMANTIC_AUDITOR_PROMPT_VERSION,
)
from recipe_pipeline.golden.reports import build_diversity_report, build_human_review_sample
from recipe_pipeline.golden.retrieval import run_golden_retrieval_evaluation
from recipe_pipeline.golden.vocabulary import build_vocabulary_report
from recipe_pipeline.pipeline import PipelineResult, RecipeDatasetPipeline
from recipe_pipeline.sources.manual import ManualRecipeSource


class GoldenDatasetBuilder:
    def build(self, output_dir: Path, requested_count: int = 500) -> dict:
        if requested_count != 500:
            raise ValueError("Golden Dataset v1 has a reviewed 500-blueprint plan")
        started = time.monotonic()
        imported_at = datetime.now(timezone.utc)
        blueprints = get_golden_blueprints()
        vocabulary = build_vocabulary_report({name for item in blueprints for name in item.ingredients})
        if vocabulary["unresolved_count"]:
            raise ValueError("blueprint contains unresolved controlled ingredients")

        canonical, generation_rejected, retry_count = BoundedCanonicalGenerationCoordinator(
            CodexCanonicalRecipeGenerator()
        ).run(blueprints)
        enricher = DeterministicRecipeEnricher()
        raw_recipes = [enricher.enrich(item, imported_at=imported_at) for item in canonical]
        pipeline_result = RecipeDatasetPipeline().run(ManualRecipeSource(raw_recipes))

        collection_by_id = {}
        canonical_by_record = {item.record_id: item for item in canonical}
        for recipe in pipeline_result.recipes:
            source_item = canonical_by_record[recipe.source.source_record_id]
            collection_by_id[str(recipe.recipe_id)] = source_item.collection.value

        audits = CodexSemanticRecipeAuditor().audit_all(pipeline_result.recipes)
        audit_pass_ids = {item.recipe_id for item in audits if item.decision == AuditDecision.PASS}
        audit_pass_recipes = [recipe for recipe in pipeline_result.recipes if str(recipe.recipe_id) in audit_pass_ids]
        duplicate_items = SemanticDuplicateReviewer().review(audit_pass_recipes)
        duplicate_rejected = SemanticDuplicateReviewer.rejected_ids(duplicate_items)
        final_recipes = [recipe for recipe in audit_pass_recipes if str(recipe.recipe_id) not in duplicate_rejected]

        final_result = PipelineResult(
            processed_count=requested_count,
            recipes=final_recipes,
            validation_reports=pipeline_result.validation_reports,
            quality_reports=pipeline_result.quality_reports,
        )
        generation_report = self._generation_report(
            requested_count=requested_count, generated=len(canonical), pipeline=pipeline_result,
            audits=audits, duplicate_rejected=duplicate_rejected,
            final_count=len(final_recipes), retry_count=retry_count,
            generation_rejected=generation_rejected,
            duration=time.monotonic() - started, blueprints=blueprints,
        )
        DatasetExporter().export(final_result, output_dir, generation_report=generation_report)
        self._write_json(output_dir / "semantic_audit_report.json", {
            "prompt_version": SEMANTIC_AUDITOR_PROMPT_VERSION,
            "prompt_policy": SEMANTIC_AUDITOR_PROMPT.strip(),
            "summary": dict(Counter(item.decision.value for item in audits)),
            "human_reviewed": False,
            "items": [item.model_dump(mode="json") for item in audits],
        })
        self._write_json(output_dir / "duplicate_report.json", {
            "layers": ["normalized_name", "core_ingredient_jaccard", "cooking_method_and_step_similarity", "semantic_identity_review"],
            "review_pair_count": len(duplicate_items),
            "rejected_recipe_count": len(duplicate_rejected),
            "ambiguous_human_review_count": sum(item.decision == "HUMAN_REVIEW" for item in duplicate_items),
            "items": [item.model_dump(mode="json") for item in duplicate_items],
        })
        self._write_json(output_dir / "ingredient_vocabulary_report.json", vocabulary)
        diversity = build_diversity_report(final_recipes, collection_by_id, duplicate_items)
        self._write_json(output_dir / "diversity_report.json", diversity)
        human_sample = build_human_review_sample(final_recipes, collection_by_id, audits, duplicate_items)
        self._write_json(output_dir / "human_review_sample.json", human_sample)
        retrieval = run_golden_retrieval_evaluation(final_recipes)
        self._write_json(output_dir / "retrieval_evaluation_report.json", retrieval)
        rejected_records = list(generation_rejected)
        rejected_records.extend(
            {"source_record_id": report.source_record_id, "stage": "DETERMINISTIC_VALIDATION", "reasons": [issue.model_dump(mode="json") for issue in report.issues]}
            for report in pipeline_result.validation_reports if not report.is_valid
        )
        rejected_records.extend(
            {"recipe_id": item.recipe_id, "name": item.recipe_name, "stage": "SEMANTIC_AUDIT", "reasons": item.reasons}
            for item in audits if item.decision != AuditDecision.PASS
        )
        rejected_records.extend(
            {"recipe_id": item.right_recipe_id, "name": item.right_name, "stage": "DUPLICATE_GATE", "reason": item.reason}
            for item in duplicate_items if item.decision == "REJECT_RIGHT"
        )
        self._write_json(output_dir / "rejected_records.json", {"count": len(rejected_records), "items": rejected_records})
        generation_report["total_duration_seconds"] = round(time.monotonic() - started, 3)
        self._write_json(output_dir / "generation_report.json", generation_report)
        return {"generation": generation_report, "diversity": diversity, "retrieval": retrieval, "output_dir": str(output_dir.resolve())}

    @staticmethod
    def _generation_report(*, requested_count, generated, pipeline, audits, duplicate_rejected, final_count, retry_count, generation_rejected, duration, blueprints) -> dict:
        validation_pass = sum(report.is_valid for report in pipeline.validation_reports)
        audit_counts = Counter(item.decision.value for item in audits)
        method_families = Counter(item.method.value for item in blueprints)
        return {
            "dataset_version": GOLDEN_DATASET_VERSION,
            "requested": requested_count, "generated": generated,
            "schema_pass_count": generated, "schema_pass_rate": round(generated / requested_count, 4),
            "deterministic_validation_pass_count": validation_pass,
            "deterministic_validation_pass_rate": round(validation_pass / requested_count, 4),
            "semantic_audit": dict(audit_counts),
            "semantic_audit_pass_rate": round(audit_counts[AuditDecision.PASS.value] / max(1, pipeline.accepted_count), 4),
            "duplicate_gate_rejected_count": len(duplicate_rejected), "final_golden_count": final_count,
            "retry_count": retry_count, "generation_rejected_count": len(generation_rejected),
            "pipeline_rejected_count": pipeline.rejected_count,
            "quality_status_distribution": dict(Counter(report.status.value for report in pipeline.quality_reports)),
            "average_quality_score": round(
                sum(report.score for report in pipeline.quality_reports)
                / max(1, len(pipeline.quality_reports)),
                4,
            ),
            "human_reviewed_count": 0,
            "lifecycle_counts": {
                "GENERATED": generated,
                "VALIDATED": validation_pass,
                "AUDIT_PASSED": audit_counts[AuditDecision.PASS.value],
                "GOLDEN_ACCEPTED": final_count,
                "HUMAN_REVIEWED": 0,
                "PUBLISHED": 0,
            },
            "primary_collection_plan": dict(Counter(item.collection.value for item in blueprints)),
            "batch_size": CodexCanonicalRecipeGenerator.batch_size,
            "batch_count": (requested_count + CodexCanonicalRecipeGenerator.batch_size - 1) // CodexCanonicalRecipeGenerator.batch_size,
            "batch_quality": {
                "malformed_batch_count": len(generation_rejected),
                "retry_count": retry_count,
                "observed_batch_size_quality_drop": False,
            },
            "template_repetition": {
                "method_template_family_count": len(method_families),
                "largest_method_family": method_families.most_common(1)[0][0],
                "largest_method_family_ratio": round(method_families.most_common(1)[0][1] / requested_count, 4),
                "note": "method-specific structure is intentionally consistent; human sample must assess whether instructions need more dish-specific detail",
            },
            "canonical_generator": {"model": GOLDEN_GENERATOR_MODEL, "prompt_version": CANONICAL_GENERATOR_PROMPT_VERSION, "prompt_policy": CANONICAL_GENERATOR_PROMPT.strip()},
            "semantic_auditor": {"model": GOLDEN_GENERATOR_MODEL, "prompt_version": SEMANTIC_AUDITOR_PROMPT_VERSION},
            "nutrition_policy": "all synthetic values null; protein/fat levels UNKNOWN",
            "provenance_policy": "AI_SYNTHETIC; semantic audit never sets human_reviewed",
            "total_duration_seconds": round(duration, 3),
        }

    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        temporary.replace(path)
