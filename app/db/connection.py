"""Postgres/pgvector connection helper."""

import psycopg
from pgvector.psycopg import register_vector

from app.config import settings


def get_connection() -> psycopg.Connection:
    conn = psycopg.connect(settings.database_url, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn
