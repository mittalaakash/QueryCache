# Adding LLM observability with LangSmith — from scratch

This app is built on LangChain (`ChatOllama`) and LangGraph. Both are made by
the LangChain team and report every run to **LangSmith** automatically once
it's turned on — no manual instrumentation code needed. That's the appeal
over a generic tracer: you get prompt/completion text, token counts, latency,
and the full graph-node waterfall for free, specifically because your stack
already speaks LangChain's tracing protocol.

## 1. What you get

- One **trace per top-level call** (`graph.astream(...)` in `main.py`),
  containing a **child run per LangGraph node** (`planner`, `budget_agent`,
  `itinerary_agent`, `human_review`, `booking`) automatically, because
  LangGraph reports each node execution as a run.
- Inside each node's LLM call, a further child run with the exact prompt sent
  to Ollama, the completion returned, latency, and token usage.
- A pause/resume on `human_review` (via `interrupt`) shows up as two separate
  runs against the same thread — you can see the state right before the
  interrupt and the state the resume produced.

## 2. Sign up and get an API key

1. Create an account at https://smith.langchain.com (free tier is enough for
   this).
2. Create a project (e.g. `trip-planner`) — or just let LangSmith create one
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

`main.py` calls `load_dotenv()` on startup (via `python-dotenv`), so
`.env` is picked up automatically — no manual `export` needed. `.env` is
gitignored; only `.env.example` (with a placeholder key) is meant to be
committed.

(The older var names `LANGCHAIN_TRACING_V2` / `LANGCHAIN_API_KEY` /
`LANGCHAIN_PROJECT` still work — LangSmith reads either set.)

Then run the app as usual:

```bash
uvicorn main:app --reload
```

Every graph run now ships to your LangSmith project automatically.

## 5. Look at a trace

1. Trigger a run from the UI (`static/index.html` — hit **Start**).
2. Open https://smith.langchain.com, select your project.
3. Click the newest trace — you'll see the node waterfall
   (`planner → budget_agent → itinerary_agent → human_review → booking`),
   each with its LLM call, the exact prompt/completion, and latency per step.
4. Approve/reject/edit in the UI — the resume shows up as a continuation of
   the same run.

## 6. Optional: name/tag runs for easier filtering

If you want to search traces by `thread_id` later (e.g. to find "the trace
for this specific user's trip"), pass it through as run metadata — LangGraph
already threads `config["configurable"]["thread_id"]` into every run, so it's
searchable in LangSmith without extra code. No changes needed here since
`main.py` already builds `config` with `thread_id`.

## 7. Turning it off

Unset `LANGSMITH_TRACING` (or set it to `false`) — nothing else changes,
since tracing here is purely environment-driven, not baked into the code.

## 8. When to reach for something else

- **Non-LLM parts of a larger system** (plain HTTP handlers, DB calls, queues
  unrelated to LangChain) aren't covered by LangSmith — it only sees
  LangChain/LangGraph runs. For full-service tracing you'd add a
  general-purpose tracer (OpenTelemetry) alongside it.
- **Self-hosting / data locality** — LangSmith is a hosted SaaS; your
  prompts/completions leave the machine. If that's a blocker, **Langfuse**
  (self-hostable, open source) has the same LangChain/LangGraph callback
  integration and keeps traces on your own infra. It's already wired up here
  too — see `LANGFUSE.md`.
