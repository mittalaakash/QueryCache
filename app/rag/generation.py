"""Ties the semantic cache, retrieval, and the Ollama chat model together
into the streamed-events pipeline the API layer consumes."""

from typing import AsyncIterator

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

from app.config import settings
from app.observability import metrics
from app.rag import cache as semantic_cache
from app.rag.retrieval import build_prompt, search

_llm = ChatOllama(model=settings.ollama_chat_model, temperature=0.2)


async def stream_query(conn, question: str, callbacks: list | None = None, k: int = 4) -> AsyncIterator[dict]:
    cached, query_embedding, slots = semantic_cache.lookup(conn, question)
    if cached is not None:
        metrics.CACHE_HITS.inc()
        yield {"type": "sources", "data": cached["sources"], "cached": True}
        yield {"type": "token", "data": cached["answer"]}
        yield {"type": "done"}
        return

    metrics.CACHE_MISSES.inc()
    chunks = search(conn, query_embedding, k=k)
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
    semantic_cache.store(conn, question, query_embedding, slots, "".join(answer_parts), sources, document_ids)
    yield {"type": "done"}
