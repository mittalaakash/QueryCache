# Adding LLM observability with Langfuse

Langfuse is the single tracing path in this app (see `OBSERVABILITY.md`).
Langfuse ships its own LangChain callback handler: no changes to the RAG
pipeline's logic, just a callback wired into the `config` dict passed to the
`ChatOllama.astream(...)` call in `app/rag/generation.py`, built once in
`app/observability/tracing.py` and passed through `app/api/routes.py` →
`stream_query(...)`.

## 1. What you get

One trace per `POST /query` call that
misses the semantic cache, containing a single span for the `llama3.2`
chat completion, showing the exact RAG prompt (question + retrieved chunks)
sent to Ollama, the completion, latency, and token usage. There's no
node-by-node waterfall — this app has one LLM call per cache-miss query, not
a multi-step agent graph. Cache hits (`app/rag/cache.py`'s `lookup()` finds
a match) skip the `ChatOllama` call entirely and so produce **no span and
no trace** — you'll only see cache-miss queries show up in Langfuse. The
query embedding call (`OllamaEmbeddings.embed_query`) also isn't wired to
the callback handler, so it never appears as a span either way.

## 2. Sign up and get keys

1. Easiest start: create a free account at https://cloud.langfuse.com
   (EU region; US/Japan/HIPAA regions also exist — see step 4).
   Self-hosting (Docker Compose, Kubernetes, AWS/Azure/GCP) is documented at
   https://langfuse.com/self-hosting if you want traces to stay on your own
   infra instead.
2. Create a project (e.g. `rag-app`).
3. Grab the public key (`pk-lf-...`) and secret key (`sk-lf-...`) from
   Project Settings → API Keys.

## 3. Install the library

Already added to `requirements.txt` — `langfuse` (the SDK), which uses the
`langchain-core` this repo already depends on for its callback integration
(plain `langchain` is not a dependency):

```bash
pip install -r requirements.txt
```

## 4. Turn tracing on — just environment variables

```bash
cp .env.example .env
# edit .env, set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to your real keys
```

`LANGFUSE_BASE_URL` defaults to `https://cloud.langfuse.com` (EU). Other
regions: `https://us.cloud.langfuse.com`, `https://jp.cloud.langfuse.com`,
`https://hipaa.cloud.langfuse.com` — or your own self-hosted URL.

`app/config.py` calls `load_dotenv()` at import time, which exports `.env`
into `os.environ` (this is required — `pydantic-settings` reads `.env` into
`app.config.settings` but does not export it to `os.environ`, and the
Langfuse `CallbackHandler()` reads its credentials from `os.environ`
directly). `app/api/routes.py` then builds a
`langfuse_handler = get_langfuse_handler()` at import time
(`app/observability/tracing.py`) and passes it as `callbacks=[langfuse_handler]`
into `stream_query(...)` on every `POST /query` call. If the keys aren't
set, the client just logs a warning and sends nothing — the app still runs
fine, tracing is simply off.

Then run the app as usual:

```bash
uvicorn app.main:app --reload
```

## 5. Look at a trace

1. Ask a question from the UI (`static/index.html`) or `POST /query` — one
   that hasn't been asked before, or that hit an invalidated cache entry, so
   it actually misses the semantic cache.
2. Open your Langfuse project → **Tracing**.
3. Click the newest trace to see the single `llama3.2` LLM call, with its
   prompt (question + retrieved chunks), completion, and latency.
4. Ask the same question again — it's served from the cache, so no new
   trace appears in Langfuse.

## 6. Turning it off

Unset `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` (or remove the
`callbacks=[langfuse_handler]` argument in `app/api/routes.py`'s `query()`)
— nothing else changes.
