# Adding LLM observability with Langfuse

This is the self-hostable alternative to the LangSmith setup in
`OBSERVABILITY.md`. Langfuse ships its own LangChain/LangGraph callback
handler, so it works the same way: no changes to `graph.py`'s node logic,
just a callback wired into the `config` dict already passed to
`graph.astream(...)`.

Both integrations can run at once — LangSmith traces via env vars
automatically, Langfuse traces via the explicit `langfuse_handler` in
`main.py`. Nothing here disables the other.

## 1. What you get

Same shape as the LangSmith trace: one trace per `/run/start` or
`/run/.../resume` call, with a child span per LangGraph node
(`planner`, `budget_agent`, `itinerary_agent`, `human_review`, `booking`),
each showing the exact prompt sent to Ollama, the completion, latency, and
token usage. The `human_review` interrupt/resume shows up as two spans tied
to the same `thread_id`.

## 2. Sign up and get keys

1. Easiest start: create a free account at https://cloud.langfuse.com
   (EU region; US/Japan/HIPAA regions also exist — see step 4).
   Self-hosting (Docker Compose, Kubernetes, AWS/Azure/GCP) is documented at
   https://langfuse.com/self-hosting if you want traces to stay on your own
   infra instead — that's the actual reason to pick Langfuse over LangSmith.
2. Create a project (e.g. `trip-planner`).
3. Grab the public key (`pk-lf-...`) and secret key (`sk-lf-...`) from
   Project Settings → API Keys.

## 3. Install the library

Already added to `requirements.txt` — `langfuse` (the SDK) plus `langchain`
(the LangChain callback integration imports the full `langchain` package,
not just `langchain-core`, which this repo already depended on):

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

`main.py` already builds a `CallbackHandler()` at startup and passes it via
`config["callbacks"]` on both `/run/start` and `/run/{thread_id}/resume`. If
the keys aren't set, the client just logs a warning and sends nothing — the
app still runs fine (same "off by default" behavior as the LangSmith setup).

Then run the app as usual:

```bash
uvicorn main:app --reload
```

## 5. Look at a trace

1. Trigger a run from the UI (`static/index.html` — hit **Start**).
2. Open your Langfuse project → **Tracing**.
3. Click the newest trace to see the node waterfall, each with its LLM
   call, prompt/completion, and latency.
4. Approve/reject/edit in the UI — the resume appears as a continuation of
   the same trace (grouped by `thread_id`).

## 6. Turning it off

Unset `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` (or remove the
`langfuse_handler` from `config["callbacks"]` in `main.py`) — nothing else
changes.
