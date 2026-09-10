"""All Postgres/pgvector I/O: documents, chunks, and the semantic query cache."""

import psycopg
from psycopg.types.json import Jsonb


# --- documents & chunks -----------------------------------------------------

def get_document(conn: psycopg.Connection, path: str) -> dict | None:
    row = conn.execute(
        "SELECT id, content_hash FROM documents WHERE path = %s", (path,)
    ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "content_hash": row[1]}


def upsert_document(conn: psycopg.Connection, path: str, title: str, content_hash: str) -> int:
    row = conn.execute(
        """
        INSERT INTO documents (path, title, content_hash)
        VALUES (%s, %s, %s)
        ON CONFLICT (path) DO UPDATE
            SET title = EXCLUDED.title,
                content_hash = EXCLUDED.content_hash,
                updated_at = now()
        RETURNING id
        """,
        (path, title, content_hash),
    ).fetchone()
    return row[0]


def replace_chunks(
    conn: psycopg.Connection, document_id: int, chunks: list[str], embeddings: list[list[float]]
) -> None:
    with conn.transaction():
        conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunks (document_id, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                [(document_id, i, c, e) for i, (c, e) in enumerate(zip(chunks, embeddings))],
            )


def find_documents_not_in(conn: psycopg.Connection, existing_paths: set[str]) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM documents WHERE path != ALL(%s)", (list(existing_paths),)
    ).fetchall()
    return [r[0] for r in rows]


def delete_documents(conn: psycopg.Connection, document_ids: list[int]) -> int:
    if not document_ids:
        return 0
    rows = conn.execute(
        "DELETE FROM documents WHERE id = ANY(%s) RETURNING id", (document_ids,)
    ).fetchall()
    return len(rows)


def list_documents(conn: psycopg.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT title, path, updated_at FROM documents ORDER BY updated_at DESC"
    ).fetchall()
    return [{"title": r[0], "path": r[1], "updated_at": r[2].isoformat()} for r in rows]


def search_chunks(conn: psycopg.Connection, query_embedding: list[float], k: int = 4) -> list[dict]:
    rows = conn.execute(
        """
        SELECT d.id, d.title, d.path, c.content, c.embedding <=> %s::vector AS distance
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        ORDER BY distance ASC
        LIMIT %s
        """,
        (query_embedding, k),
    ).fetchall()
    return [
        {"document_id": r[0], "title": r[1], "path": r[2], "content": r[3], "distance": r[4]}
        for r in rows
    ]


# --- semantic query cache ----------------------------------------------------

def find_cache_candidates(
    conn: psycopg.Connection, query_embedding: list[float], limit: int, ttl_seconds: int
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, answer, sources, slots, question_embedding <=> %s::vector AS distance
        FROM query_cache
        WHERE created_at > now() - (%s || ' seconds')::interval
        ORDER BY distance ASC
        LIMIT %s
        """,
        (query_embedding, ttl_seconds, limit),
    ).fetchall()
    return [
        {"id": r[0], "answer": r[1], "sources": r[2], "slots": set(r[3]), "distance": r[4]}
        for r in rows
    ]


def store_cache_entry(
    conn: psycopg.Connection,
    question: str,
    question_embedding: list[float],
    slots: set[str],
    answer: str,
    sources: list[dict],
    document_ids: list[int],
) -> int:
    with conn.transaction():
        row = conn.execute(
            """
            INSERT INTO query_cache (question, question_embedding, slots, answer, sources)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (question, question_embedding, sorted(slots), answer, Jsonb(sources)),
        ).fetchone()
        cache_id = row[0]
        if document_ids:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO query_cache_documents (cache_id, document_id)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """,
                    [(cache_id, doc_id) for doc_id in document_ids],
                )
    return cache_id


def invalidate_cache_for_documents(conn: psycopg.Connection, document_ids: list[int]) -> int:
    if not document_ids:
        return 0
    rows = conn.execute(
        """
        DELETE FROM query_cache
        WHERE id IN (
            SELECT cache_id FROM query_cache_documents WHERE document_id = ANY(%s)
        )
        RETURNING id
        """,
        (document_ids,),
    ).fetchall()
    return len(rows)
