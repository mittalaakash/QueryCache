# RAG application — design

Replaces the LangGraph trip-planner demo in this repo with a full
retrieval-augmented-generation app: a synthetic document corpus, an
incremental ingestion pipeline into pgvector, retrieval + generation over
Ollama, a query UI, and observability (Langfuse tracing, logging, Prometheus
metrics).

## Why

User wants a self-contained local RAG demo: own documents, own vector store
(pgvector, Docker, local), own ingestion pipeline (with incremental
re-ingestion when documents change), a query interface, and observability
(traces/logs/metrics).

## Vector store

New, isolated Postgres container — **not** the existing `postgres` container
on :5432, which belongs to a different project (`llmgateway`, 67 tables of
real data). Isolation avoids any risk to that data.

- Image: `pgvector/pgvector:pg17`
- Port: `5433` (host) -> `5432` (container)
- Named volume for persistence
- Defined in `docker-compose.yml`, `docker compose up -d` to start
- DB name `ragdb`, user/password in `.env` (`DATABASE_URL`)

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
```

768 dims matches `nomic-embed-text` (the local Ollama embedding model).

## Document corpus

`generate_docs.py`: a seeded generator that writes ~100 synthetic markdown
files into `documents/`, across templates that give the corpus numeric and
narrative variety:

- Quarterly revenue reports (tables, $ figures, growth %)
- Short fictional stories
- Product FAQs
- Meeting notes
- Technical how-tos

Deterministic (fixed seed) so re-running it doesn't silently drift the
corpus. Run once at setup; files are then editable by hand or via the app's
document UI.

## Ingestion pipeline (`ingest.py`)

Walks `documents/*.md`. For each file:

1. Compute `sha256` of file content.
2. Look up `documents` row by `path`.
   - Missing -> new document: insert row, chunk + embed + insert chunks.
   - Present, hash unchanged -> skip entirely (the incremental part).
   - Present, hash changed -> delete old chunks, re-chunk + re-embed + insert,
     update stored hash.
3. After the walk, any `documents` row whose `path` no longer exists on disk
   is deleted (cascades to its chunks) — keeps the store in sync with
   deletions.

Chunking: simple character-based splitter, ~800 chars per chunk, 100 char
overlap — no need for a heavier splitter library at this corpus size/shape.

Embeddings: `OllamaEmbeddings(model="nomic-embed-text")`.

Runs as a CLI (`python ingest.py`) for bulk/initial ingestion, and is called
directly (single-document path) by the FastAPI app when a document is
added/edited through the UI — this is the "incremental ingestion" the user
asked for: editing a document and getting just that document re-embedded,
not the whole corpus.

## Retrieval + generation (`rag.py`)

1. Embed the incoming query with the same Ollama embedding model.
2. `SELECT ... ORDER BY embedding <=> $1 LIMIT k` against `chunks` (cosine
   distance) joined to `documents` for title/path — top-k (k=4).
3. Build a prompt: retrieved chunks as context (with source labels) + the
   question, instructing the model to cite sources and say when the context
   doesn't answer the question.
4. Stream the answer from `ChatOllama(model="llama3.2")` token-by-token.

## FastAPI app (`main.py`)

Reuses the existing SSE streaming pattern from the trip-planner.

- `GET /` — serves the query UI (`static/index.html`, rewritten)
- `POST /query` — body `{"question": str}`, SSE stream: a `sources` event
  (retrieved chunks/doc titles) then `token` events for the streamed answer,
  then `done`
- `GET /documents` — list ingested documents (title, path, updated_at)
- `POST /documents` — body `{"title": str, "content": str}`, writes/overwrites
  a file under `documents/`, incrementally ingests just that file, returns
  the updated document list
- `GET /metrics` — Prometheus text format via `prometheus-client`

## Observability

- **Tracing**: Langfuse `CallbackHandler` (already configured via env vars in
  `.env`) passed to both the embedding calls and the generation `ChatOllama`
  call. `langgraph`/`langsmith` are dropped from `requirements.txt` — they
  were only used by the trip-planner graph being removed; Langfuse becomes
  the single tracing path.
- **Logging**: stdlib `logging`, structured messages for ingestion runs
  (documents added/updated/skipped/deleted, chunk counts) and per-query
  retrieval latency.
- **Metrics**: `prometheus-client` counters/histograms — query count, query
  latency histogram, retrieved-chunk count, ingested document/chunk counts —
  exposed at `/metrics`.

## Removed

`graph.py`, `test_graph.py`, the trip-planner UI markup in
`static/index.html` (file rewritten, not deleted).

## Dependencies

Add: `psycopg[binary]`, `pgvector`, `prometheus-client`.
Remove: `langgraph`, `langsmith`, `openai` (unused).
Keep: `fastapi`, `uvicorn[standard]`, `langchain-ollama`, `langchain-core`,
`langfuse`, `python-dotenv`.

## Testing

One assert-based `test_ingest.py` covering the non-trivial branchy logic:
chunking boundaries and the hash-based skip/reinsert/delete decision, run
against a stubbed embedder (no real Ollama/DB needed for the unit test).

## Env vars (new)

```
DATABASE_URL=postgresql://raguser:ragpass@localhost:5433/ragdb
OLLAMA_EMBED_MODEL=nomic-embed-text
```
