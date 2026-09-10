# QueryCache

A local RAG (retrieval-augmented generation) application: FastAPI + pgvector + Ollama, with a semantic query cache that's gated on both embedding similarity *and* a deterministic slot match — so it never confuses "Q1 2025" with "Q1 2026" just because the questions look similar.

## Features

- **Incremental ingestion** — a synthetic 100-document corpus (revenue reports, stories, FAQs, meeting notes, how-tos) is hashed per file; re-running ingestion skips unchanged documents, re-embeds changed ones, and removes deleted ones.
- **Semantic query cache** — a repeated or paraphrased question skips generation entirely. A hit requires both a cosine-similarity threshold *and* an identical set of extracted "slots" (years, quarters, and other numbers, with relative phrases like "this year" resolved against today's date), so semantically-close-but-factually-different questions are never confused.
- **Document-scoped cache invalidation** — editing a document invalidates only the cached answers that used it as a source, not the whole cache.
- **Query + document UI** — ask questions, see cited sources and a "cached" badge, add or edit documents in place.
- **Observability** — Langfuse tracing, structured logging, Prometheus metrics at `/metrics`.

## Architecture

```
app/
  main.py              FastAPI app factory (lifespan-managed DB connection)
  config.py            Typed settings (pydantic-settings)
  api/routes.py        HTTP routes
  core/                Chunking, shared Ollama embedder
  db/                  Connection, schema, all SQL (documents/chunks/query_cache)
  ingestion/           Incremental ingestion pipeline
  rag/                 Retrieval, generation, semantic cache
  observability/       Logging, metrics, Langfuse tracing
scripts/
  generate_docs.py     Seeded synthetic corpus generator
  ingest.py             Ingestion CLI
static/index.html       Query + document UI
documents/               Generated markdown corpus
tests/                   Unit tests
```

Design docs, the implementation plan, and the full task-by-task build/review trail are in `docs/superpowers/`.

## Prerequisites

- Python 3.12+
- [Docker](https://www.docker.com/) (for the pgvector Postgres container)
- [Ollama](https://ollama.com/) running locally

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Pull the models
ollama pull nomic-embed-text
ollama pull llama3.2

# 3. Start the isolated pgvector Postgres container
docker compose up -d

# 4. Configure environment
cp .env.example .env
# edit .env if you want Langfuse tracing (optional — the app works without it)

# 5. Generate the synthetic document corpus (~100 files)
python -m scripts.generate_docs

# 6. Run initial ingestion
python -m scripts.ingest

# 7. Start the app
uvicorn app.main:app --reload
```

Open **http://localhost:8000** to ask questions and manage documents.

## Re-ingesting after edits

Editing a document through the UI ingests just that one file. To re-sync the whole `documents/` folder from disk (e.g. after editing files directly):

```bash
python -m scripts.ingest
```

Unchanged files are skipped; only new/changed/deleted files are processed.

## Testing

```bash
python -m pytest tests/ -v
```

## Observability

- **Tracing**: set `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` in `.env` — see `LANGFUSE.md`. Traces one call per cache-miss `/query` (embedding + generation); cache hits produce no LLM trace.
- **Metrics**: `GET /metrics` (Prometheus text format) — query count/latency, cache hit/miss counts, retrieved-chunk counts, ingested-document counts.
- **Logging**: structured logs via Python's stdlib `logging`, configured in `app/observability/logging_config.py`.

See `OBSERVABILITY.md` for details.
