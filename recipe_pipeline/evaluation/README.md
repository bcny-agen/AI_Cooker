# Recipe Retrieval Evaluation

This package evaluates Recipe Schema v1 JSONL entirely offline. It is not used by
FastAPI, LangGraph, Java, or the production Agent.

## Evaluation lanes

1. `BaselineRecipeRetriever` scans the controlled ingredient catalog (including
   Chinese/English aliases), then ranks with ingredient coverage, recipe-name and
   dish keywords, scenario tags, time constraints, and preference heuristics.
2. `RecipeEmbeddingTextBuilder` produces independent ingredient, scenario, and
   full-recipe representations.
3. `LocalVectorRecipeRetriever` uses deterministic token hashing and an in-memory
   vector store. This is only a plumbing prototype; it is not a semantic model and
   is not a substitute for future PostgreSQL + pgvector embeddings.
4. `HybridRecipeRetriever` parses ingredients and constraints once, obtains a
   30-recipe pool from both the rule and vector retrievers, combines ranks with
   weighted Reciprocal Rank Fusion, and applies an explainable structured reranker.

The hybrid vector lane uses character n-gram TF-IDF. It is a real lexical vector
calculation rather than fake/hash embeddings, but it is still not a multilingual
semantic embedding model. `EmbeddingProvider` keeps this replaceable;
`FakeEmbeddingProvider` is restricted to tests and `RealEmbeddingProvider` is the
future adapter boundary.

The current dataset showed that the vector lane is weaker than normalized rules,
so RRF uses evidence-based weights of `rule=10` and `vector=1`. Scores are never
averaged directly. Final ranking is:

```text
weighted RRF
+ ingredient coverage / complete-match bonus
- missing and excess core ingredient penalties
+ preference and scenario match
- spicy, time, and difficulty constraint violations
+ dish-name keyword match
+ recipe quality confidence
```

The fixed test set has 60 user-style queries: 25 ingredient, 10 synonym, 10
scenario, 10 preference, and 5 combined queries. Expected recipe names are
resolved to the IDs in the evaluated artifact at runtime, so rerunning dataset
generation does not leave stale IDs in the evaluation output.

## Run

```powershell
.\.venv\Scripts\python.exe -m recipe_pipeline.evaluation.main `
  --dataset recipe_pipeline\output\first_batch_100\recipes.jsonl `
  --output recipe_pipeline\evaluation\output `
  --top-k 5
```

Outputs:

- `queries.json`
- `retrieval_results.json`
- `metrics.json`

`Recall@5` is mean set recall, not only a binary hit rate. The report also includes
HitRate@5, MRR, top-result ingredient coverage, preference match, and failed-query
classification.

## Real multilingual benchmark (Step 17H)

`embedding_benchmark_main` reuses the same parser, rule retriever, RRF fusion, and
structured reranker while evaluating the fixed 50-query development and 75-query
holdout splits. It writes the five-lane matrix (rule-only, TF-IDF vector/hybrid,
and real vector/hybrid) under `recipe_pipeline/output/embedding_benchmark/`.

The default local model is `intfloat/multilingual-e5-small` (384 dimensions) and
uses its documented `query:` / `passage:` prefixes. A configurable
OpenAI-compatible `/embeddings` adapter is also available. API keys are read only
from `RECIPE_EMBEDDING_API_KEY`; they are never written to reports.

```powershell
uv run --python 3.13 --no-project `
  --with pydantic==2.13.4 --with httpx==0.28.1 --with openai==2.47.0 `
  --with "sentence-transformers>=5.1,<6" `
  python -m recipe_pipeline.evaluation.embedding_benchmark_main
```

Recipe and query views have independent template versions. The offline cache key
contains provider/model namespace, representation type, SHA-256 source-text hash,
and template version; dimensions are checked and files are replaced atomically.
Cached vector payloads are local generated data and are gitignored.
