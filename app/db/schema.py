"""Schema for documents, their chunks, and the semantic query cache."""

import psycopg


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id SERIAL PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding vector(768) NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS chunks_embedding_idx
        ON chunks USING hnsw (embedding vector_cosine_ops)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_cache (
            id SERIAL PRIMARY KEY,
            question TEXT NOT NULL,
            question_embedding vector(768) NOT NULL,
            slots TEXT[] NOT NULL DEFAULT '{}',
            answer TEXT NOT NULL,
            sources JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS query_cache_embedding_idx
        ON query_cache USING hnsw (question_embedding vector_cosine_ops)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_cache_documents (
            cache_id INTEGER NOT NULL REFERENCES query_cache(id) ON DELETE CASCADE,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            PRIMARY KEY (cache_id, document_id)
        )
    """)
