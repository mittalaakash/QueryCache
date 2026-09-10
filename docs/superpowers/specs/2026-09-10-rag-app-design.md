# RAG application — design

Replaces the LangGraph trip-planner demo in this repo with a production-shaped
RAG app: a synthetic document corpus, an incremental ingestion pipeline into
pgvector, retrieval + generation over Ollama, a semantic answer cache, a query
UI, and observability (Langfuse tracing, logging, Prometheus metrics). Built
as a proper `app/` package since the user intends to keep extending it.

## Why

User wants a self-contained local RAG demo — own documents, own vector store
(pgvector, Docker, local), own ingestion pipeline (incremental re-ingestion on
document change), a query interface, observability, and a semantic cache —
structured so it's a reasonable base to build further features on, not a
throwaway script.

## Package layout

```
app/
  main.py                FastAPI app factory (lifespan-managed DB connection)
  config.py               pydantic-settings — typed, validated env config
  api/
    routes.py              /, /query, /documents, /metrics, /health
  core/
    embeddings.py           shared OllamaEmbeddings instance
    chunking.py              pure text splitter
  db/
    connection.py            psycopg connection + pgvector registration
    schema.py                 documents / chunks / query_cache / query_cache_documents
    repository.py             all SQL: document+chunk CRUD, vector search, cache CRUD
  ingestion/
    pipeline.py               decide_action, ingest_file, sync_documents
  rag/
    retrieval.py               vector search + prompt building
    generation.py               orchestrates cache -> retrieval -> LLM -> cache write
    cache.py                    semantic cache lookup/store + slot extraction
  observability/
    logging_config.py           central logging setup
    metrics.py                   Prometheus counters/histograms
    tracing.py                    Langfuse handler factory
scripts/
  generate_docs.py              seeded corpus generator
  ingest.py                      CLI: run sync_documents against documents/
static/
  index.html                    query + document UI
documents/                      generated markdown corpus (~100 files)
tests/
  test_chunking.py
  test_ingestion.py
  test_semantic_cache.py
docker-compose.yml
requirements.txt
.env.example
```

## Vector store

New, isolated Postgres container — **not** the existing `postgres` container
on :5432, which belongs to a different project (`llmgateway`, 67 tables of
real data). Isolation avoids any risk to that data.

- Image: `pgvector/pgvector:pg17`
- Port: `5433` (host) -> `5432` (container)
- Named volume for persistence, via `docker-compose.yml`
- DB name `ragdb`, credentials in `.env` (`DATABASE_URL`)

Schema:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(768) NOT NULL
);
CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops);

CREATE TABLE query_cache (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    question_embedding vector(768) NOT NULL,
    slots TEXT[] NOT NULL DEFAULT '{}',
    answer TEXT NOT NULL,
    sources JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON query_cache USING ivfflat (question_embedding vector_cosine_ops);

CREATE TABLE query_cache_documents (
    cache_id INTEGER NOT NULL REFERENCES query_cache(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY (cache_id, document_id)
);
```

768 dims matches `nomic-embed-text` (the local Ollama embedding model).

## Document corpus

`scripts/generate_docs.py`: a seeded generator writing ~100 synthetic
markdown files into `documents/`, across templates chosen for numeric and
narrative variety: quarterly revenue reports (tables, $ figures, growth %),
short fictional stories, product FAQs, meeting notes, technical how-tos.
Deterministic (fixed seed). Run once at setup; files are then editable by
hand or via the app's document UI.

## Ingestion pipeline (`app/ingestion/pipeline.py`)

Walks `documents/*.md`. For each file:

1. Compute `sha256` of file content.
2. Look up the `documents` row by `path`.
   - Missing -> **insert**: chunk + embed + insert chunks.
   - Present, hash unchanged -> **skip**.
   - Present, hash changed -> **update**: delete old chunks, re-chunk +
     re-embed + insert, update stored hash, **invalidate any cached answers
     that used this document** (see Semantic cache below).
3. After the walk, any `documents` row whose `path` no longer exists on disk
   is **deleted** (cascades to its chunks) — its cache entries are
   invalidated first, then it's removed.

Chunking: character-based splitter, ~800 chars per chunk, 100 char overlap.

Embeddings: `OllamaEmbeddings(model="nomic-embed-text")`, via the shared
`app/core/embeddings.py` instance.

Runs as a CLI (`python -m scripts.ingest`) for bulk/initial ingestion, and is
called directly (single-document path) by the FastAPI app when a document is
added/edited through the UI — the incremental-ingestion requirement.

## Retrieval + generation (`app/rag/retrieval.py`, `app/rag/generation.py`)

1. Check the semantic cache first (below). On a qualifying hit, return the
   cached answer/sources without touching retrieval or the LLM.
2. On a miss: embed the query, `SELECT ... ORDER BY embedding <=> $1 LIMIT k`
   against `chunks` joined to `documents` (cosine distance, k=4).
3. Build a prompt: retrieved chunks as context (source-labeled) + the
   question, instructing the model to cite sources and say when the context
   doesn't answer the question.
4. Stream the answer from `ChatOllama(model="llama3.2")` token-by-token.
5. Store the finished answer, its sources, and the source documents' ids in
   the semantic cache for next time.

## Semantic cache (`app/rag/cache.py`)

Goal: skip the (expensive) generation call for questions that are
semantically the same as one already answered — without serving a *wrong*
cached answer for questions that only *look* similar.

**Storage:** `query_cache` holds the raw question, its embedding, the
answer, its sources, and a `slots` array (below). `query_cache_documents`
links each cache row to the document ids that backed its answer.

**Lookup (`cache.lookup`):**
1. Embed the question; extract its `slots` (below).
2. Fetch the nearest `semantic_cache_candidates` (default 5) rows from
   `query_cache` by cosine distance, restricted to entries younger than
   `semantic_cache_ttl_seconds` (default 3600 — a staleness backstop on top
   of explicit invalidation).
3. Walk candidates in distance order; the first one where
   `distance <= semantic_cache_threshold` (default 0.05) **and**
   `candidate.slots == query.slots` is the hit. Both conditions must hold —
   similarity alone is not sufficient.
4. Return `(hit_or_None, question_embedding, slots)` — the embedding and
   slots are reused by `cache.store` on a miss so the question is only
   embedded once per query.

**Slot extraction (`extract_cache_slots`)** is the guard against false
positives: it pulls out every year, quarter, and standalone number
mentioned or implied by the question, resolving relative time phrases
against today's date:

- Explicit years (`2025`, `2026`, ...) and explicit quarters (`Q1`..`Q4`,
  "first quarter", "quarter one").
- Relative years ("this year" -> current year, "last year" -> current
  year - 1) and relative quarters ("this quarter" -> computed from today's
  month).
- Month groups that exactly cover a quarter ("January, February, March" or
  "the first three months of this year" -> `Q1`), so a paraphrase and its
  literal quarter form collide onto the same slot set.
- Any other standalone number in the question (so "top 5 customers" and
  "top 10 customers" get different slot sets even though nothing else
  differs).

Two questions only share a cache entry if their slot sets are **identical**
(both empty counts as identical — most questions have no date/number
specifics, and for those, similarity alone gates the hit). This is
regex/dictionary based, not an LLM call, so it stays fast — deliberately
covers common phrasings only, not full date-language understanding.
`ponytail: extend the phrase tables (or swap in a real date-parsing library)
if a phrasing shows up that isn't recognized.`

**Invalidation (`repository.invalidate_cache_for_documents`):** ingestion
calls this whenever a document is updated or deleted, passing that
document's id. It deletes exactly the `query_cache` rows linked to that
document via `query_cache_documents` — not the whole cache. Order matters
for deletions: the linked cache rows must be invalidated *before* the
document row is deleted (deleting the document cascades away the join rows
first, which would make them unfindable), so `sync_documents` looks up
documents-to-delete, invalidates their cache, and only then deletes them.

**Metrics:** `rag_cache_hits_total` / `rag_cache_misses_total` counters.

## FastAPI app (`app/main.py`, `app/api/routes.py`)

Reuses the SSE streaming pattern from the original trip-planner. The DB
connection is created once in a FastAPI `lifespan` context and stored on
`app.state.db_conn` (no module-level global connection).

- `GET /` — serves the query UI (`static/index.html`)
- `GET /health` — liveness check
- `POST /query` — body `{"question": str}`, SSE stream: a `sources` event
  (retrieved/cached chunks or doc titles, with a `cached: bool` flag) then
  `token` events for the answer, then `done`
- `GET /documents` — list ingested documents (title, path, updated_at)
- `POST /documents` — body `{"title": str, "content": str}`, writes/overwrites
  a file under `documents/` (title sanitized to a safe filename — no path
  traversal), incrementally ingests just that file, returns the updated
  document list
- `GET /metrics` — Prometheus text format via `prometheus-client`

## Observability

- **Tracing**: Langfuse `CallbackHandler` (`app/observability/tracing.py`,
  configured via env vars in `.env`) passed to the generation `ChatOllama`
  call. `langgraph`/`langsmith` are dropped — Langfuse is the single tracing
  path.
- **Logging**: stdlib `logging`, centrally configured
  (`app/observability/logging_config.py`), used for ingestion runs
  (documents added/updated/skipped/deleted, cache invalidation counts) and
  per-query logging.
- **Metrics**: `prometheus-client` (`app/observability/metrics.py`) — query
  count/latency, retrieved-chunk count, cache hit/miss counts, ingested
  document counts by action — exposed at `/metrics`.

## Removed

`graph.py`, `test_graph.py`, the flat-file `main.py`/`db.py`/etc. from the
first draft of this design (superseded by the `app/` package layout), the
trip-planner UI markup in `static/index.html` (file rewritten).

## Dependencies

Add: `psycopg[binary]`, `pgvector`, `prometheus-client`, `pydantic-settings`.
Remove: `langgraph`, `langsmith`, `openai` (unused).
Keep: `fastapi`, `uvicorn[standard]`, `langchain-ollama`, `langchain-core`,
`langfuse`, `python-dotenv`.

## Testing

- `tests/test_chunking.py` — chunk boundaries and overlap.
- `tests/test_ingestion.py` — `decide_action`'s insert/update/skip branches.
- `tests/test_semantic_cache.py` — `extract_cache_slots`: explicit
  year+quarter extraction, different years producing different slot sets,
  relative-phrase canonicalization landing on the same slot set as the
  literal phrasing, no-date/number questions producing an empty set, and
  non-date numeric mismatches (e.g. "top 5" vs "top 10") producing different
  sets.

Run via `python -m pytest tests/ -v` from the repo root (the `-m` form
ensures the repo root — and therefore the `app` package — is on
`sys.path`, without needing an editable install).

## Env vars (new)

```
DATABASE_URL=postgresql://raguser:ragpass@localhost:5433/ragdb
OLLAMA_EMBED_MODEL=nomic-embed-text
```

(`OLLAMA_CHAT_MODEL`, `SEMANTIC_CACHE_THRESHOLD`,
`SEMANTIC_CACHE_TTL_SECONDS`, `SEMANTIC_CACHE_CANDIDATES` are all
`pydantic-settings` fields with sensible defaults — only set them in `.env`
to override.)
