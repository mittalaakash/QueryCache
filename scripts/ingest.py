"""CLI: run the incremental ingestion pipeline against documents/."""

import logging
from pathlib import Path

from app.core.embeddings import embedder
from app.db.connection import get_connection
from app.db.schema import init_schema
from app.ingestion.pipeline import sync_documents
from app.observability.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("ingestion.cli")

if __name__ == "__main__":
    conn = get_connection()
    init_schema(conn)
    result = sync_documents(conn, embedder.embed_documents, Path("documents"))
    logger.info("ingestion complete: %s", result)
