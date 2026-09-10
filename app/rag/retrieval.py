"""Vector search + prompt construction over the ingested document chunks."""

from app.db import repository

PROMPT_TEMPLATE = """Answer the question using ONLY the context below. Cite \
sources by title in brackets, e.g. [Q3 2024 Revenue Report]. If the context \
doesn't contain the answer, say so plainly instead of guessing.

Context:
{context}

Question: {question}
Answer:"""


def search(conn, query_embedding: list[float], k: int = 4) -> list[dict]:
    return repository.search_chunks(conn, query_embedding, k=k)


def build_prompt(question: str, chunks: list[dict]) -> str:
    context = "\n\n".join(f"[{c['title']}]\n{c['content']}" for c in chunks)
    return PROMPT_TEMPLATE.format(context=context, question=question)
