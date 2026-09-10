# Adding LLM observability with LangSmith — from scratch

This app is built on LangChain (`ChatOllama` for generation, `OllamaEmbeddings`
for embeddings). LangChain runs report to **LangSmith** automatically once
it's turned on — no manual instrumentation code needed. That's the appeal
over a generic tracer: you get prompt/completion text, token counts, and
latency for free, specifically because the generation call already speaks
LangChain's tracing protocol.

## 1. What you get

- One **trace per `POST /query` call that misses the semantic cache**,
  containing a single child run: the `llama3.2` chat completion
  (`ChatOllama.astream(...)` in `app/rag/generation.py`) with the exact
  RAG prompt (retrieved chunks + question) sent to Ollama, the streamed
  completion, latency, and token usage. The query embedding
  (`OllamaEmbeddings.embed_query` in `app/rag/cache.py`) is called directly,
  not through a traced `Runnable.invoke`, so it does **not** appear as a
  child run — only the generation call does.
- **Cache hits produce no trace at all.** When `app/rag/cache.py`'s
  `lookup()` finds a matching cached answer, `stream_query()` in
  `app/rag/generation.py` returns the cached answer immediately and never
  calls `ChatOllama`, so there's nothing for LangSmith to report — this is
  the whole point of the cache (skip generation, not just skip work after
  the fact).
- There's no multi-node waterfall or human-in-the-loop pause/resume here —
  this app doesn't use LangGraph. Each cache-miss query is a single flat
  LLM call.

## 2. Sign up and get an API key

1. Create an account at https://smith.langchain.com (free tier is enough for
   this).
2. Create a project (e.g. `rag-app`) — or just let LangSmith create one
   from the env var below on first run.
3. Grab an API key from Settings → API Keys.

## 3. Install the library

Already covered — `langsmith` ships as a dependency of `langchain-core`,
which this repo already depends on. It's pinned explicitly in
`requirements.txt` since it's now a deliberate integration point, not just
incidental:

```
pip install -r requirements.txt
```

## 4. Turn tracing on — just environment variables

No code changes needed in the graph/app logic. Copy the template and fill in
your key:

```bash
cp .env.example .env
# edit .env, set LANGSMITH_API_KEY to your real key
```

`app/config.py` (via `pydantic-settings`, `env_file=".env"`) picks up `.env`
automatically on startup — no manual `export` needed. `.env` is gitignored;
only `.env.example` (with a placeholder key) is meant to be committed.

(The older var names `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` /
`LANGCHAIN_PROJECT` still work — LangSmith reads either set.)

Then run the app as usual:

```bash
uvicorn app.main:app --reload
```

Every cache-miss query now ships a trace to your LangSmith project
automatically.

## 5. Look at a trace

1. Ask a question from the UI (`static/index.html`) or `POST /query`.
2. Open https://smith.langchain.com, select your project.
3. Click the newest trace — you'll see the single `llama3.2` LLM call, with
   the exact prompt (question + retrieved chunks), completion, and latency.
4. Ask the *same* question again — it's served from the semantic cache, so
   no new trace appears. Only genuinely new (or invalidated) questions
   produce a trace.

## 6. Turning it off

Unset `LANGSMITH_TRACING` (or set it to `false`) — nothing else changes,
since tracing here is purely environment-driven, not baked into the code.

## 7. When to reach for something else

- **Non-LLM parts of a larger system** (retrieval/pgvector search, the
  semantic cache lookup, plain HTTP handlers) aren't covered by LangSmith —
  it only sees LangChain runs, i.e. the `ChatOllama` generation call. For
  full-service tracing (including retrieval latency or cache hit/miss) you'd
  add a general-purpose tracer (OpenTelemetry) or rely on the Prometheus
  metrics at `GET /metrics` (`rag_cache_hits_total`, `rag_retrieved_chunks`,
  etc.) alongside it.
- **Self-hosting / data locality** — LangSmith is a hosted SaaS; your
  prompts/completions leave the machine. If that's a blocker, **Langfuse**
  (self-hostable, open source) has the same LangChain callback integration
  and keeps traces on your own infra. It's already wired up here too — see
  `LANGFUSE.md`.
