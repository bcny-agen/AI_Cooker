"""Transactional, idempotent Golden Dataset importer with Step 17H cache reuse."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from recipe_pipeline.evaluation.embedding import (
    EmbeddingContext,
    EmbeddingKind,
    QUERY_TEMPLATE_VERSIONS,
    RECIPE_TEMPLATE_VERSIONS,
    RecipeEmbeddingTextBuilder,
)
from recipe_pipeline.evaluation.embedding_cache import (
    CachedEmbeddingProvider,
    source_text_hash,
)
from recipe_pipeline.evaluation.embedding_providers import (
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    validate_vector_dimensions,
)
from recipe_pipeline.normalization.ingredients import IngredientCatalog, normalize_lookup_key
from recipe_pipeline.recipe_kb.config import RecipeKBConfig
from recipe_pipeline.recipe_kb.database import connect
from recipe_pipeline.schemas.recipe import RecipeV1
from recipe_pipeline.sources import load_recipe_jsonl


DEFAULT_GOLDEN_DATASET = Path("recipe_pipeline/output/golden_500/recipes.jsonl")
DEFAULT_CACHE_DIR = Path("recipe_pipeline/output/embedding_benchmark/cache")
FROZEN_MODEL = "intfloat/multilingual-e5-small"
FROZEN_DIMENSION = 384
PIPELINE_VERSION = "recipe-kb-step17i-v1"


class RecipeImportError(RuntimeError):
    pass


class EmbeddingMissingError(RecipeImportError):
    pass


@dataclass(frozen=True, slots=True)
class ImportReport:
    ingestion_run_id: UUID
    dataset_version_id: UUID
    dataset_version: str
    source_sha256: str
    inserted: int
    updated: int
    unchanged: int
    rejected: int
    embedding_cache_hits: int
    new_embeddings: int
    duration_seconds: float
    status: str


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _vector_literal(vector) -> str:
    return "[" + ",".join(format(float(value), ".9g") for value in vector) + "]"


class GoldenDatasetImporter:
    def __init__(
        self,
        config: RecipeKBConfig,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        provider: EmbeddingProvider | None = None,
        allow_generation: bool = True,
    ):
        self.config = config
        self._cache_dir = cache_dir
        self._provider = provider
        self._allow_generation = allow_generation
        self._catalog = IngredientCatalog()
        self._builder = RecipeEmbeddingTextBuilder(self._catalog)

    def import_dataset(
        self,
        dataset_path: Path = DEFAULT_GOLDEN_DATASET,
        *,
        version_key: str = "golden_500_v1",
        fail_after_recipes: int | None = None,
    ) -> ImportReport:
        started = time.perf_counter()
        source_hash = _file_sha256(dataset_path)
        recipes = load_recipe_jsonl(dataset_path)  # strict RecipeV1 validation
        self._validate_source(recipes)
        documents = [
            document for recipe in recipes for document in self._builder.build(recipe)
        ]
        cached = self._cached_provider()
        vectors = []
        cache_hits = 0
        missing_documents = []
        missing_indexes = []
        for index, document in enumerate(documents):
            context = EmbeddingContext(document.kind.value, document.template_version)
            vector = cached.read_cached_document(document.text, context)
            if vector is None:
                missing_documents.append(document)
                missing_indexes.append(index)
                vectors.append(None)
            else:
                cache_hits += 1
                vectors.append(vector)
        if missing_documents:
            if not self._allow_generation:
                raise EmbeddingMissingError(
                    f"{len(missing_documents)} recipe embeddings are missing from the Step 17H cache"
                )
            generated = cached.embed_documents(
                [item.text for item in missing_documents],
                [
                    EmbeddingContext(item.kind.value, item.template_version)
                    for item in missing_documents
                ],
            )
            for index, vector in zip(missing_indexes, generated):
                vectors[index] = vector
        validate_vector_dimensions(vectors, self.config.embedding_dimension)
        vectors_by_recipe: dict[UUID, list[tuple]] = {}
        for document, vector in zip(documents, vectors):
            vectors_by_recipe.setdefault(document.recipe_id, []).append((document, vector))

        run_id = uuid4()
        dataset_id = uuid5(NAMESPACE_URL, f"ai-cooker:recipe-dataset:{version_key}:{source_hash}")
        inserted = updated = unchanged = rejected = new_embeddings = 0
        try:
            with connect(self.config) as connection:
                connection.execute(
                    """
                    INSERT INTO ingestion_runs(
                        ingestion_run_id, dataset_version_id, version_key,
                        source_artifact_sha256, status
                    ) VALUES (%s, NULL, %s, %s, 'RUNNING')
                    """,
                    (run_id, version_key, source_hash),
                )
                connection.execute(
                    """
                    INSERT INTO dataset_versions(
                        dataset_version_id, version_key, source_artifact_path,
                        source_artifact_sha256, recipe_schema_version, pipeline_version,
                        recipe_count, embedding_model, embedding_dimension,
                        recipe_template_versions, query_template_versions, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, 'EXPERIMENTAL')
                    ON CONFLICT (version_key) DO UPDATE SET
                        source_artifact_path = EXCLUDED.source_artifact_path
                    WHERE dataset_versions.source_artifact_sha256 = EXCLUDED.source_artifact_sha256
                    RETURNING dataset_version_id
                    """,
                    (
                        dataset_id,
                        version_key,
                        str(dataset_path),
                        source_hash,
                        recipes[0].schema_version,
                        PIPELINE_VERSION,
                        len(recipes),
                        self.config.embedding_model,
                        self.config.embedding_dimension,
                        json.dumps({kind.value: value for kind, value in RECIPE_TEMPLATE_VERSIONS.items()}),
                        json.dumps({kind.value: value for kind, value in QUERY_TEMPLATE_VERSIONS.items()}),
                    ),
                )
                existing_dataset = connection.execute(
                    "SELECT dataset_version_id, source_artifact_sha256 FROM dataset_versions WHERE version_key = %s",
                    (version_key,),
                ).fetchone()
                if not existing_dataset or existing_dataset[1] != source_hash:
                    raise RecipeImportError(
                        "dataset version key already exists for a different source artifact"
                    )
                dataset_id = existing_dataset[0]
                connection.execute(
                    "UPDATE ingestion_runs SET dataset_version_id = %s WHERE ingestion_run_id = %s",
                    (dataset_id, run_id),
                )
                self._upsert_vocabulary(connection)
                for position, recipe in enumerate(recipes, start=1):
                    state = self._recipe_state(connection, dataset_id, recipe)
                    if state == "inserted":
                        inserted += 1
                    elif state == "updated":
                        updated += 1
                    else:
                        unchanged += 1
                    self._replace_recipe_relations(connection, dataset_id, recipe)
                    new_embeddings += self._insert_embeddings(
                        connection, dataset_id, recipe, vectors_by_recipe[recipe.recipe_id]
                    )
                    if fail_after_recipes is not None and position >= fail_after_recipes:
                        raise RecipeImportError("intentional partial-import failure")
                connection.execute(
                    "UPDATE dataset_versions SET ingested_at = now() WHERE dataset_version_id = %s",
                    (dataset_id,),
                )
                connection.execute(
                    """
                    UPDATE ingestion_runs SET status = 'SUCCEEDED', inserted_count = %s,
                        updated_count = %s, unchanged_count = %s, rejected_count = %s,
                        embedding_cache_hits = %s, new_embeddings = %s,
                        completed_at = now()
                    WHERE ingestion_run_id = %s
                    """,
                    (inserted, updated, unchanged, rejected, cache_hits, new_embeddings, run_id),
                )
        except Exception as error:
            self._record_failure(run_id, version_key, source_hash, error)
            if isinstance(error, RecipeImportError):
                raise
            raise RecipeImportError("Golden Dataset import failed and was rolled back") from error
        return ImportReport(
            run_id,
            dataset_id,
            version_key,
            source_hash,
            inserted,
            updated,
            unchanged,
            rejected,
            cache_hits,
            new_embeddings,
            round(time.perf_counter() - started, 3),
            "SUCCEEDED",
        )

    def _record_failure(
        self, run_id: UUID, version_key: str, source_hash: str, error: Exception
    ) -> None:
        try:
            with connect(self.config) as connection:
                connection.execute(
                    """
                    INSERT INTO ingestion_runs(
                        ingestion_run_id, dataset_version_id, version_key,
                        source_artifact_sha256, status, rejected_count,
                        error_summary, completed_at
                    ) VALUES (%s, NULL, %s, %s, 'FAILED', 1, %s, now())
                    ON CONFLICT (ingestion_run_id) DO NOTHING
                    """,
                    (run_id, version_key, source_hash, type(error).__name__),
                )
        except Exception:
            # Preserve the original import failure if failure telemetry is unavailable.
            pass

    def _cached_provider(self) -> CachedEmbeddingProvider:
        provider = self._provider or SentenceTransformerEmbeddingProvider(
            self.config.embedding_model,
            dimensions=self.config.embedding_dimension,
            batch_size=self.config.embedding_batch_size,
            device=self.config.embedding_device,
        )
        return CachedEmbeddingProvider(
            provider, self._cache_dir, batch_size=self.config.embedding_batch_size
        )

    @staticmethod
    def _validate_source(recipes: list[RecipeV1]) -> None:
        if len(recipes) != 492:
            raise RecipeImportError(f"expected 492 Golden recipes, found {len(recipes)}")
        invalid = [
            str(recipe.recipe_id)
            for recipe in recipes
            if recipe.quality.human_reviewed
            or recipe.quality.status.value != "REVIEW"
            or recipe.source.source_type.value != "AI_SYNTHETIC"
        ]
        if invalid:
            raise RecipeImportError("Golden recipe provenance invariant failed")

    def _upsert_vocabulary(self, connection) -> None:
        for entry in self._catalog.entries:
            connection.execute(
                """
                INSERT INTO ingredients(ingredient_id, canonical_name) VALUES (%s, %s)
                ON CONFLICT (ingredient_id) DO UPDATE SET canonical_name = EXCLUDED.canonical_name
                """,
                (entry.ingredient_id, entry.normalized_name),
            )
            for alias in entry.aliases:
                connection.execute(
                    """
                    INSERT INTO ingredient_aliases(ingredient_id, alias, alias_key, language_hint)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (ingredient_id, alias_key) DO UPDATE SET alias = EXCLUDED.alias
                    """,
                    (
                        entry.ingredient_id,
                        alias,
                        normalize_lookup_key(alias),
                        "en" if alias.isascii() else "zh-CN",
                    ),
                )

    def _recipe_state(self, connection, dataset_id: UUID, recipe: RecipeV1) -> str:
        existing = connection.execute(
            "SELECT content_hash FROM recipes WHERE dataset_version_id = %s AND recipe_id = %s",
            (dataset_id, recipe.recipe_id),
        ).fetchone()
        state = "inserted" if not existing else (
            "unchanged" if existing[0] == recipe.quality.content_hash else "updated"
        )
        source = recipe.source
        connection.execute(
            """
            INSERT INTO recipes(
                dataset_version_id, recipe_id, name, aliases, language, cuisine, region,
                category, summary, min_servings, max_servings, prep_minutes, cook_minutes,
                inactive_minutes, total_minutes, difficulty, difficulty_reasons,
                required_equipment, optional_equipment, quality_status, confidence_score,
                human_reviewed, schema_version, source_dataset_version, content_hash, imported_at
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            ) ON CONFLICT (dataset_version_id, recipe_id) DO UPDATE SET
                name=EXCLUDED.name, aliases=EXCLUDED.aliases, language=EXCLUDED.language,
                cuisine=EXCLUDED.cuisine, region=EXCLUDED.region, category=EXCLUDED.category,
                summary=EXCLUDED.summary, min_servings=EXCLUDED.min_servings,
                max_servings=EXCLUDED.max_servings, prep_minutes=EXCLUDED.prep_minutes,
                cook_minutes=EXCLUDED.cook_minutes, inactive_minutes=EXCLUDED.inactive_minutes,
                total_minutes=EXCLUDED.total_minutes, difficulty=EXCLUDED.difficulty,
                difficulty_reasons=EXCLUDED.difficulty_reasons,
                required_equipment=EXCLUDED.required_equipment,
                optional_equipment=EXCLUDED.optional_equipment,
                quality_status=EXCLUDED.quality_status, confidence_score=EXCLUDED.confidence_score,
                human_reviewed=EXCLUDED.human_reviewed, schema_version=EXCLUDED.schema_version,
                source_dataset_version=EXCLUDED.source_dataset_version,
                content_hash=EXCLUDED.content_hash, imported_at=EXCLUDED.imported_at,
                updated_at=now()
            """,
            (
                dataset_id, recipe.recipe_id, recipe.identity.name, recipe.identity.aliases,
                recipe.identity.language, recipe.identity.cuisine.value, recipe.identity.region.value,
                recipe.identity.category.value, recipe.identity.summary, recipe.serving.min_servings,
                recipe.serving.max_servings, recipe.time.prep_minutes, recipe.time.cook_minutes,
                recipe.time.inactive_minutes, recipe.time.total_minutes, recipe.difficulty.level,
                recipe.difficulty.reasons, [item.value for item in recipe.equipment.required],
                [item.value for item in recipe.equipment.optional], recipe.quality.status.value,
                recipe.quality.confidence_score, recipe.quality.human_reviewed, recipe.schema_version,
                source.dataset_version, recipe.quality.content_hash, source.imported_at,
            ),
        )
        return state

    def _replace_recipe_relations(self, connection, dataset_id: UUID, recipe: RecipeV1) -> None:
        key = (dataset_id, recipe.recipe_id)
        for table in (
            "recipe_ingredient_substitutes", "recipe_steps", "recipe_taste_profiles",
            "recipe_nutrition", "recipe_tags", "recipe_sources", "recipe_ingredients",
        ):
            connection.execute(
                f"DELETE FROM {table} WHERE dataset_version_id = %s AND recipe_id = %s", key
            )
        for position, item in enumerate(recipe.ingredients, start=1):
            connection.execute(
                """
                INSERT INTO recipe_ingredients VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    *key, item.ingredient_id, item.display_name, item.role.value,
                    item.importance.value, item.requirement_group, item.quantity.minimum,
                    item.quantity.maximum, item.quantity.unit.value, item.preparation, position,
                ),
            )
        for item in recipe.substitutes:
            connection.execute(
                "INSERT INTO recipe_ingredient_substitutes VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (*key, item.recipe_ingredient_id, item.substitute_ingredient_id, item.ratio, item.penalty, item.note),
            )
        for step in recipe.steps:
            connection.execute(
                "INSERT INTO recipe_steps VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    *key, step.order, step.phase.value, step.instruction, step.duration_minutes,
                    step.method.value, step.heat_level.value, step.temperature_celsius,
                    step.ingredient_refs, [item.value for item in step.equipment_refs], step.safety_note,
                ),
            )
        taste = recipe.taste_profile
        connection.execute(
            "INSERT INTO recipe_taste_profiles VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (*key, taste.spicy, taste.sweet, taste.sour, taste.salty, taste.umami, taste.richness),
        )
        nutrition = recipe.nutrition
        connection.execute(
            "INSERT INTO recipe_nutrition VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (*key, nutrition.basis, nutrition.calories_kcal, nutrition.protein_g,
             nutrition.fat_g, nutrition.carbohydrate_g, nutrition.protein_level.value, nutrition.fat_level.value),
        )
        for tag_type, values in (
            ("DIETARY", recipe.tags.dietary), ("HEALTH", recipe.tags.health),
            ("SCENARIO", recipe.tags.scenario), ("TECHNIQUE", recipe.tags.technique),
            ("ALLERGEN", recipe.tags.allergens),
        ):
            for value in values:
                tag_id = connection.execute(
                    """
                    INSERT INTO tags(tag_type, tag_value) VALUES (%s,%s)
                    ON CONFLICT (tag_type, tag_value) DO UPDATE SET tag_value=EXCLUDED.tag_value
                    RETURNING tag_id
                    """, (tag_type, value.value)
                ).fetchone()[0]
                connection.execute("INSERT INTO recipe_tags VALUES (%s,%s,%s)", (*key, tag_id))
        source = recipe.source
        connection.execute(
            "INSERT INTO recipe_sources VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                *key, source.source_type.value, source.source_name, source.source_record_id,
                source.license, str(source.source_url) if source.source_url else None,
                source.reliability_score, source.generator_model, source.dataset_version, source.imported_at,
            ),
        )

    def _insert_embeddings(self, connection, dataset_id: UUID, recipe: RecipeV1, records) -> int:
        inserted = 0
        for document, vector in records:
            representation = "FULL_SEMANTIC" if document.kind == EmbeddingKind.FULL_RECIPE else document.kind.value
            row = connection.execute(
                """
                INSERT INTO recipe_embeddings(
                    dataset_version_id, recipe_id, representation_type, embedding_model,
                    embedding_dimension, template_version, source_text_hash, embedding
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)
                ON CONFLICT DO NOTHING RETURNING embedding_id
                """,
                (
                    dataset_id, recipe.recipe_id, representation, self.config.embedding_model,
                    self.config.embedding_dimension, document.template_version,
                    source_text_hash(document.text), _vector_literal(vector),
                ),
            ).fetchone()
            inserted += int(row is not None)
        return inserted

    def activate_dataset(self, version_key: str) -> None:
        with connect(self.config) as connection:
            target = connection.execute(
                "SELECT dataset_version_id FROM dataset_versions WHERE version_key=%s AND status='VALIDATED'",
                (version_key,),
            ).fetchone()
            if not target:
                raise RecipeImportError("only an explicitly validated dataset can be activated")
            connection.execute("UPDATE dataset_versions SET status='INACTIVE' WHERE status='ACTIVE'")
            connection.execute(
                "UPDATE dataset_versions SET status='ACTIVE', activated_at=now() WHERE dataset_version_id=%s",
                (target[0],),
            )

    def validate_dataset(
        self,
        version_key: str,
        dataset_path: Path = DEFAULT_GOLDEN_DATASET,
    ) -> None:
        recipes = load_recipe_jsonl(dataset_path)
        expected_hashes = {
            (
                recipe.recipe_id,
                "FULL_SEMANTIC" if document.kind == EmbeddingKind.FULL_RECIPE else document.kind.value,
                document.template_version,
                source_text_hash(document.text),
            )
            for recipe in recipes
            for document in self._builder.build(recipe)
        }
        with connect(self.config) as connection:
            row = connection.execute(
                """
                SELECT dv.recipe_count, count(DISTINCT r.recipe_id), count(re.embedding_id),
                       count(*) FILTER (WHERE re.embedding_dimension <> vector_dims(re.embedding)),
                       count(*) FILTER (WHERE r.human_reviewed OR r.quality_status <> 'REVIEW')
                FROM dataset_versions dv
                JOIN recipes r USING (dataset_version_id)
                JOIN recipe_embeddings re USING (dataset_version_id, recipe_id)
                WHERE dv.version_key=%s
                GROUP BY dv.recipe_count
                """, (version_key,)
            ).fetchone()
            if not row or row[0] != row[1] or row[2] != row[1] * 3 or row[3] or row[4]:
                raise RecipeImportError("dataset integrity validation failed")
            stored_hashes = {
                (item[0], item[1], item[2], item[3])
                for item in connection.execute(
                    """
                    SELECT re.recipe_id, re.representation_type::text,
                           re.template_version, re.source_text_hash
                    FROM recipe_embeddings re
                    JOIN dataset_versions dv USING(dataset_version_id)
                    WHERE dv.version_key=%s
                    """,
                    (version_key,),
                ).fetchall()
            }
            if stored_hashes != expected_hashes:
                raise RecipeImportError("stored embedding source hashes do not match Step 17H representations")
            connection.execute(
                "UPDATE dataset_versions SET status='VALIDATED' WHERE version_key=%s",
                (version_key,),
            )

    @staticmethod
    def report_dict(report: ImportReport) -> dict:
        return asdict(report)
