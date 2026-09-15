"""Postgres/pgvector connection helper."""

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from app.config import settings


def get_connection() -> psycopg.Connection:
    conn = psycopg.connect(settings.database_url, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def get_pool() -> ConnectionPool:
    # One shared connection can't serve concurrent requests safely — pool so
    # each request gets its own connection, checked out per request.
    with psycopg.connect(settings.database_url, autocommit=True) as bootstrap:
        bootstrap.execute("CREATE EXTENSION IF NOT EXISTS vector")

    return ConnectionPool(
        settings.database_url,
        kwargs={"autocommit": True},
        configure=register_vector,
        open=True,
    )
