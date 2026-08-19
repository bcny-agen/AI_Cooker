# AI_Cooker Recipe Dataset Pipeline

This package is an **offline data-engineering tool**, not part of the FastAPI
request path. It does not call the live Agent, Tavily, MySQL, Java backend, or a
vector database.

## Flow

```text
source adapter -> RawRecipe -> controlled normalization -> optional AI enhancement
-> Recipe Schema v1 -> deterministic validation -> duplicate detection
-> quality gate -> JSONL + reports
```

Unknown ingredient names are rejected instead of being guessed. AI output is
untrusted and must validate as a complete `RecipeV1` object. The quality gate is:

- score below `0.70`, or any deterministic error: `REJECTED`
- `0.70 <= score < 0.85`: `REVIEW`
- score at least `0.85`: `PUBLISHED`

The demo records are fixed, synthetic, test-only data with low source
reliability. They are intentionally marked `REVIEW`, not production knowledge.

## Commands

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m recipe_pipeline.main demo --count 10 --output recipe_pipeline/output
.\.venv\Scripts\python.exe -m recipe_pipeline.main generate-first-batch --count 100 --generator codex-direct --output recipe_pipeline/output/first_batch_100
.\.venv\Scripts\python.exe -m recipe_pipeline.main generate-step-flash-batch --count 200 --output recipe_pipeline/output/step_flash_batch_200 --baseline recipe_pipeline/output/first_batch_100/recipes.jsonl
.\.venv\Scripts\python.exe -m recipe_pipeline.main export-schema --output recipe_pipeline/output/recipe_schema_v1.json
.\.venv\Scripts\python.exe -m recipe_pipeline.evaluation.main --dataset recipe_pipeline/output/first_batch_100/recipes.jsonl --output recipe_pipeline/evaluation/output --top-k 5
.\.venv\Scripts\python.exe -m unittest discover -s recipe_pipeline/tests -v
```

Artifacts:

- `recipes.jsonl`: one accepted Recipe Schema v1 object per line
- `validation_report.json`: deterministic validation results
- `quality_report.json`: component scores and gate decisions
- `recipe_schema_v1.json`: machine-readable JSON Schema
- `generation_report.json`: requested/generated/rejected counts, retries, duration,
  quality distribution, duplicate count, and requested/accepted segment distribution
- `evaluation_report.json` (Step 17F): Codex/Step quality and diversity comparison,
  culinary audit concerns, and current-100 versus combined retrieval metrics

`LLM_PROVIDER`, `MODEL_NAME`, `API_KEY`, and `LLM_BASE_URL` configure the optional
OpenAI-compatible remote client; credentials are never written to reports.
The Step 17C command defaults to the checked-in Codex-authored 100-recipe seed
batch and still routes every record through `RecipeBatchGenerator` and the full
pipeline. `--generator configured-llm` remains available for an explicitly
configured OpenAI-compatible provider and uses JSON Mode plus schema validation.

The Step 17F command is an isolated experiment. It requires
`MODEL_NAME=step-3.7-flash`, uses four bounded generation workers, retries each
five-recipe job at most once, checks duplicates against `first_batch_100`, and
never writes Step records into the Codex dataset. A valid schema or deterministic
quality score is not human verification; synthetic nutrition values, safety cues,
and near duplicates remain explicit review concerns.
