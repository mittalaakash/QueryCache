"""Langfuse tracing handler factory — the single place that builds the
callback handler passed into LLM calls."""

from langfuse.langchain import CallbackHandler


def get_langfuse_handler() -> CallbackHandler:
    # No-ops (logs a warning, sends nothing) if LANGFUSE_PUBLIC_KEY/SECRET_KEY aren't set.
    return CallbackHandler()
