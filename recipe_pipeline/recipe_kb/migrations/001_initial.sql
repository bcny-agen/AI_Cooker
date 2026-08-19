CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE recipe_dataset_status AS ENUM ('EXPERIMENTAL', 'VALIDATED', 'ACTIVE', 'INACTIVE');
CREATE TYPE recipe_ingestion_status AS ENUM ('RUNNING', 'SUCCEEDED', 'FAILED');
CREATE TYPE recipe_representation_type AS ENUM ('INGREDIENT', 'SCENARIO', 'FULL_SEMANTIC');

CREATE TABLE dataset_versions (
    dataset_version_id uuid PRIMARY KEY,
    version_key text NOT NULL UNIQUE,
    source_artifact_path text NOT NULL,
    source_artifact_sha256 char(64) NOT NULL,
    recipe_schema_version text NOT NULL,
    pipeline_version text NOT NULL,
    recipe_count integer NOT NULL CHECK (recipe_count >= 0),
    embedding_model text NOT NULL,
    embedding_dimension integer NOT NULL CHECK (embedding_dimension > 0),
    recipe_template_versions jsonb NOT NULL,
    query_template_versions jsonb NOT NULL,
    status recipe_dataset_status NOT NULL DEFAULT 'EXPERIMENTAL',
    ingested_at timestamptz,
    activated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (version_key, source_artifact_sha256)
);

CREATE UNIQUE INDEX one_active_recipe_dataset
    ON dataset_versions ((status)) WHERE status = 'ACTIVE';

CREATE TABLE ingestion_runs (
    ingestion_run_id uuid PRIMARY KEY,
    dataset_version_id uuid REFERENCES dataset_versions(dataset_version_id),
    version_key text NOT NULL,
    source_artifact_sha256 char(64) NOT NULL,
    status recipe_ingestion_status NOT NULL,
    inserted_count integer NOT NULL DEFAULT 0,
    updated_count integer NOT NULL DEFAULT 0,
    unchanged_count integer NOT NULL DEFAULT 0,
    rejected_count integer NOT NULL DEFAULT 0,
    embedding_cache_hits integer NOT NULL DEFAULT 0,
    new_embeddings integer NOT NULL DEFAULT 0,
    error_summary text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE ingredients (
    ingredient_id uuid PRIMARY KEY,
    canonical_name text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ingredient_aliases (
    ingredient_id uuid NOT NULL REFERENCES ingredients(ingredient_id) ON DELETE CASCADE,
    alias text NOT NULL,
    alias_key text NOT NULL,
    language_hint text,
    PRIMARY KEY (ingredient_id, alias_key),
    UNIQUE (alias_key)
);

CREATE TABLE recipes (
    dataset_version_id uuid NOT NULL REFERENCES dataset_versions(dataset_version_id) ON DELETE CASCADE,
    recipe_id uuid NOT NULL,
    name text NOT NULL,
    aliases text[] NOT NULL DEFAULT '{}',
    language text NOT NULL,
    cuisine text NOT NULL,
    region text NOT NULL,
    category text NOT NULL,
    summary text NOT NULL,
    min_servings integer NOT NULL,
    max_servings integer NOT NULL,
    prep_minutes integer NOT NULL,
    cook_minutes integer NOT NULL,
    inactive_minutes integer NOT NULL,
    total_minutes integer NOT NULL,
    difficulty integer NOT NULL,
    difficulty_reasons text[] NOT NULL DEFAULT '{}',
    required_equipment text[] NOT NULL DEFAULT '{}',
    optional_equipment text[] NOT NULL DEFAULT '{}',
    quality_status text NOT NULL CHECK (quality_status = 'REVIEW'),
    confidence_score real NOT NULL,
    human_reviewed boolean NOT NULL DEFAULT false CHECK (human_reviewed = false),
    schema_version text NOT NULL,
    source_dataset_version text,
    content_hash char(64) NOT NULL,
    imported_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version_id, recipe_id)
);

CREATE TABLE recipe_ingredients (
    dataset_version_id uuid NOT NULL,
    recipe_id uuid NOT NULL,
    ingredient_id uuid NOT NULL REFERENCES ingredients(ingredient_id),
    display_name text NOT NULL,
    role text NOT NULL,
    importance text NOT NULL,
    requirement_group text NOT NULL,
    quantity_min double precision,
    quantity_max double precision,
    unit text NOT NULL,
    preparation text NOT NULL,
    position integer NOT NULL,
    PRIMARY KEY (dataset_version_id, recipe_id, ingredient_id),
    FOREIGN KEY (dataset_version_id, recipe_id)
        REFERENCES recipes(dataset_version_id, recipe_id) ON DELETE CASCADE
);

CREATE TABLE recipe_ingredient_substitutes (
    dataset_version_id uuid NOT NULL,
    recipe_id uuid NOT NULL,
    recipe_ingredient_id uuid NOT NULL,
    substitute_ingredient_id uuid NOT NULL REFERENCES ingredients(ingredient_id),
    ratio double precision NOT NULL,
    penalty double precision NOT NULL,
    note text NOT NULL,
    PRIMARY KEY (dataset_version_id, recipe_id, recipe_ingredient_id, substitute_ingredient_id),
    FOREIGN KEY (dataset_version_id, recipe_id, recipe_ingredient_id)
        REFERENCES recipe_ingredients(dataset_version_id, recipe_id, ingredient_id) ON DELETE CASCADE
);

CREATE TABLE recipe_steps (
    dataset_version_id uuid NOT NULL,
    recipe_id uuid NOT NULL,
    step_order integer NOT NULL,
    phase text NOT NULL,
    instruction text NOT NULL,
    duration_minutes integer NOT NULL,
    method text NOT NULL,
    heat_level text NOT NULL,
    temperature_celsius double precision,
    ingredient_refs uuid[] NOT NULL DEFAULT '{}',
    equipment_refs text[] NOT NULL DEFAULT '{}',
    safety_note text,
    PRIMARY KEY (dataset_version_id, recipe_id, step_order),
    FOREIGN KEY (dataset_version_id, recipe_id)
        REFERENCES recipes(dataset_version_id, recipe_id) ON DELETE CASCADE
);

CREATE TABLE recipe_taste_profiles (
    dataset_version_id uuid NOT NULL,
    recipe_id uuid NOT NULL,
    spicy smallint NOT NULL,
    sweet smallint NOT NULL,
    sour smallint NOT NULL,
    salty smallint NOT NULL,
    umami smallint NOT NULL,
    richness smallint NOT NULL,
    PRIMARY KEY (dataset_version_id, recipe_id),
    FOREIGN KEY (dataset_version_id, recipe_id)
        REFERENCES recipes(dataset_version_id, recipe_id) ON DELETE CASCADE
);

CREATE TABLE recipe_nutrition (
    dataset_version_id uuid NOT NULL,
    recipe_id uuid NOT NULL,
    basis text NOT NULL,
    calories_kcal double precision,
    protein_g double precision,
    fat_g double precision,
    carbohydrate_g double precision,
    protein_level text NOT NULL,
    fat_level text NOT NULL,
    PRIMARY KEY (dataset_version_id, recipe_id),
    FOREIGN KEY (dataset_version_id, recipe_id)
        REFERENCES recipes(dataset_version_id, recipe_id) ON DELETE CASCADE
);

CREATE TABLE tags (
    tag_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tag_type text NOT NULL,
    tag_value text NOT NULL,
    UNIQUE (tag_type, tag_value)
);

CREATE TABLE recipe_tags (
    dataset_version_id uuid NOT NULL,
    recipe_id uuid NOT NULL,
    tag_id bigint NOT NULL REFERENCES tags(tag_id),
    PRIMARY KEY (dataset_version_id, recipe_id, tag_id),
    FOREIGN KEY (dataset_version_id, recipe_id)
        REFERENCES recipes(dataset_version_id, recipe_id) ON DELETE CASCADE
);

CREATE TABLE recipe_sources (
    dataset_version_id uuid NOT NULL,
    recipe_id uuid NOT NULL,
    source_type text NOT NULL CHECK (source_type = 'AI_SYNTHETIC'),
    source_name text NOT NULL,
    source_record_id text NOT NULL,
    license text,
    source_url text,
    reliability_score real NOT NULL,
    generator_model text,
    source_dataset_version text,
    imported_at timestamptz NOT NULL,
    PRIMARY KEY (dataset_version_id, recipe_id),
    FOREIGN KEY (dataset_version_id, recipe_id)
        REFERENCES recipes(dataset_version_id, recipe_id) ON DELETE CASCADE
);

CREATE TABLE recipe_embeddings (
    embedding_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_version_id uuid NOT NULL,
    recipe_id uuid NOT NULL,
    representation_type recipe_representation_type NOT NULL,
    embedding_model text NOT NULL,
    embedding_dimension integer NOT NULL CHECK (embedding_dimension > 0),
    template_version text NOT NULL,
    source_text_hash char(64) NOT NULL,
    embedding vector NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (dataset_version_id, recipe_id)
        REFERENCES recipes(dataset_version_id, recipe_id) ON DELETE CASCADE,
    CHECK (vector_dims(embedding) = embedding_dimension),
    UNIQUE (
        dataset_version_id, recipe_id, representation_type,
        embedding_model, template_version, source_text_hash
    )
);

CREATE INDEX recipe_ingredients_lookup ON recipe_ingredients(ingredient_id, dataset_version_id);
CREATE INDEX recipe_tags_lookup ON recipe_tags(tag_id, dataset_version_id);
CREATE INDEX recipe_embeddings_exact_scope ON recipe_embeddings(
    dataset_version_id, embedding_model, embedding_dimension, representation_type
);

-- Deliberately no HNSW or IVFFlat index: 1,476 vectors use exact cosine search.
