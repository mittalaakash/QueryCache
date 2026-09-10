# Observability

This app has three observability paths, all already wired up:

1. **Langfuse** — LLM tracing (prompts, completions, latency, token usage).
   See `LANGFUSE.md` for setup.
2. **Structured logging** — via `app/observability/logging_config.py`.
3. **Prometheus metrics** — exposed at `GET /metrics`, via
   `app/observability/metrics.py`.

`langgraph`/`langsmith` are not part of this app — Langfuse is the single
tracing path (see `requirements.txt`; neither package is listed there).

## 1. Langfuse tracing

`app/api/routes.py` builds a `langfuse_handler = get_langfuse_handler()` at
import time (`app/observability/tracing.py`) and passes it as
`callbacks=[langfuse_handler]` into `stream_query(...)` on every
`POST /query` call.

**Trace shape:** one trace per `POST /query` call that misses the semantic
cache, containing a single span for the `llama3.2` chat completion
(`ChatOllama.astream(...)` in `app/rag/generation.py`), showing the exact RAG
prompt (question + retrieved chunks) sent to Ollama, the completion, latency,
and token usage. Cache hits (`app/rag/cache.py`'s `lookup()` finds a match)
skip the `ChatOllama` call entirely and so produce **no span and no
trace** — you'll only see cache-miss queries show up in Langfuse. The query
embedding call (`OllamaEmbeddings.embed_query`) also isn't wired to the
callback handler, so it never appears as a span either way.

See `LANGFUSE.md` for how to sign up, get keys, and turn it on.

## 2. Structured logging

`app/observability/logging_config.py`'s `configure_logging()` sets up
`logging.basicConfig` once at process start (`%(asctime)s %(levelname)s
%(name)s: %(message)s`), used consistently by both the FastAPI app and the
CLI ingestion scripts. Look for logs from the `rag_app` and `ingestion`
loggers.

## 3. Prometheus metrics

`GET /metrics` (`app/observability/metrics.py`) exposes:

- `rag_queries_total` — total `POST /query` calls answered.
- `rag_query_latency_seconds` — end-to-end query latency histogram.
- `rag_retrieved_chunks` — chunks retrieved per query.
- `rag_ingested_documents_total{action}` — documents processed via the UI
  ingestion path (`POST /documents`), labeled by `insert`/`update`/`skip`.
- `rag_cache_hits_total` / `rag_cache_misses_total` — semantic cache
  hit/miss counts.

Point a local Prometheus (or `curl`) at `http://localhost:8000/metrics` to
see current values.
