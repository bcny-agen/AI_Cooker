# Recipe Knowledge Base (Step 17I)

This subsystem persists only the immutable Golden Recipe Dataset in a dedicated
PostgreSQL database with pgvector. It does not connect to FastAPI, LangGraph,
Java, Vue, MySQL, forum, or memory code.

## Local database

Preferred cross-platform setup (verified official image tag):

```powershell
$env:RECIPE_DB_PASSWORD = "choose-a-local-password"
docker compose -f recipe_pipeline/recipe_kb/docker-compose.yml up -d
```

Windows without Docker can use the project-local Pixi environment. The checked
configuration pins PostgreSQL 16.14 and pgvector 0.8.3 because those exact
conda-forge win-64 builds share a compatible `libpq` ABI:

```powershell
cd recipe_pipeline/recipe_kb
pixi install
```

The schema migration applies `CREATE EXTENSION vector` and readiness verifies
both PostgreSQL and extension versions. Database credentials come exclusively
from `RECIPE_DB_*`; application MySQL settings are never consulted.

## Import and validation

```powershell
python -m recipe_pipeline.recipe_kb.main migrate
python -m recipe_pipeline.recipe_kb.main import
python -m recipe_pipeline.recipe_kb.main validate
python -m recipe_pipeline.recipe_kb.main benchmark
```

Validation changes the dataset from `EXPERIMENTAL` to `VALIDATED`. Activation is
a separate explicit command and is not part of the Step 17I import.

The importer validates each JSONL row as `RecipeV1`, preserves `REVIEW`,
`human_reviewed=false`, and `AI_SYNTHETIC`, reuses the exact Step 17H recipe
templates/cache, and inserts each recipe plus three independently versioned
vectors in one transaction.

## Retrieval order

1. Embed the exact Step 17H structured ingredient/scenario/full query views.
2. Run exact cosine search independently for the matching representation type.
3. Union candidate recipe IDs (no ANN, RRF, or unrelated-lane score averaging).
4. Apply deterministic relational hard filters before candidates are returned.
5. Use the validated weighted semantic score as dominant ranking signal, with
   small explainable ingredient/scenario/quality tie-breakers in the service.

The `vector` column is dimension-flexible for future model migrations, but every
row stores and enforces its own dimension. Queries always scope model, dimension,
representation, and immutable template version.

## Production Agent integration

FastAPI owns one `RecipeKBRuntime` for its application lifespan. The runtime
uses a dedicated psycopg connection pool and loads the configured E5 model once
during startup; both Step and DeepSeek Agents share the resulting
`recipe_search` tool. `RECIPE_DATASET_VERSION` explicitly authorizes a
`VALIDATED` or `ACTIVE` version and never selects the newest dataset implicitly.

If configuration, PostgreSQL, pgvector, dataset metadata, or embeddings are
unavailable, the tool returns a safe unavailable contract. This is isolated
from the MySQL LangGraph checkpointer, and the Agent can independently use the
retained Tavily `web_search` fallback.
