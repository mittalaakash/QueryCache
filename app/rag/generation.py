"""Ties the semantic cache, retrieval, and the Ollama chat model together
into the streamed-events pipeline the API layer consumes."""

import asyncio
from typing import AsyncIterator

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama
from langfuse import get_client
from psycopg_pool import ConnectionPool

from app.config import settings
from app.observability import metrics
from app.rag import cache as semantic_cache
from app.rag.retrieval import build_prompt, search

_llm = ChatOllama(model=settings.ollama_chat_model, temperature=0.2)
_langfuse = get_client()


async def stream_query(
    pool: ConnectionPool, question: str, callbacks: list | None = None, k: int = 4
) -> AsyncIterator[dict]:
    # repository/cache functions are plain blocking psycopg calls, so each one
    # runs in a worker thread (via asyncio.to_thread) against its own pooled
    # connection — otherwise a slow query would stall the whole event loop.
    def _lookup():
        with pool.connection() as conn:
            return semantic_cache.lookup(conn, question)

    cached, query_embedding, slots = await asyncio.to_thread(_lookup)
    if cached is not None:
        metrics.CACHE_HITS.inc()
        yield {"type": "sources", "data": cached["sources"], "cached": True}
        yield {"type": "token", "data": cached["answer"]}
        yield {"type": "done"}
        return

    metrics.CACHE_MISSES.inc()
    with _langfuse.start_as_current_observation(as_type="span", name="rag-query", input=question):
        def _search():
            with pool.connection() as conn:
                return search(conn, query_embedding, k=k)

        with _langfuse.start_as_current_observation(as_type="retriever", name="vector-search", input=question) as retriever:
            chunks = await asyncio.to_thread(_search)
            retriever.update(output=[{"title": c["title"], "path": c["path"]} for c in chunks])
        metrics.RETRIEVED_CHUNKS.observe(len(chunks))
        sources = [{"title": c["title"], "path": c["path"]} for c in chunks]
        yield {"type": "sources", "data": sources, "cached": False}

        prompt = build_prompt(question, chunks)
        config = {"callbacks": callbacks} if callbacks else {}
        answer_parts: list[str] = []
        async for chunk in _llm.astream([HumanMessage(content=prompt)], config=config):
            if chunk.content:
                answer_parts.append(chunk.content)
                yield {"type": "token", "data": chunk.content}

    document_ids = [c["document_id"] for c in chunks]
    answer = "".join(answer_parts)

    def _store():
        with pool.connection() as conn:
            semantic_cache.store(conn, question, query_embedding, slots, answer, sources, document_ids)

    await asyncio.to_thread(_store)
    yield {"type": "done"}
