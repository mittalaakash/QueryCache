"""HTTP routes: query (SSE), document list/add, health, metrics."""

import json
import logging
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, StreamingResponse

from app.core.embeddings import embedder
from app.db import repository
from app.ingestion.pipeline import ingest_file
from app.observability import metrics
from app.observability.tracing import get_langfuse_handler
from app.rag.generation import stream_query

logger = logging.getLogger("rag_app")
router = APIRouter()

DOCUMENTS_DIR = Path("documents")
langfuse_handler = get_langfuse_handler()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _safe_filename(title: str) -> str:
    # Strip to a safe slug so a title can't be used for path traversal.
    slug = re.sub(r"[^a-z0-9_-]", "", title.strip().lower().replace(" ", "_"))
    return f"{slug or uuid.uuid4().hex}.md"


@router.get("/")
def index():
    return FileResponse("static/index.html")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/query")
async def query(req: Request):
    conn = req.app.state.db_conn
    body = await req.json()
    question = body["question"]

    async def stream():
        start = time.perf_counter()
        async for event in stream_query(conn, question, callbacks=[langfuse_handler]):
            yield _sse(event)
        metrics.QUERY_COUNT.inc()
        metrics.QUERY_LATENCY.observe(time.perf_counter() - start)
        logger.info("query answered question=%r", question)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/documents")
def list_documents(req: Request):
    return repository.list_documents(req.app.state.db_conn)


@router.get("/documents/content")
def get_document_content(path: str):
    file_path = Path(path)
    resolved = file_path.resolve()
    if not resolved.is_relative_to(DOCUMENTS_DIR.resolve()) or not resolved.is_file():
        return Response(status_code=404, content="not found")
    return {"path": path, "content": file_path.read_text()}


@router.post("/documents")
async def upsert_document(req: Request):
    conn = req.app.state.db_conn
    body = await req.json()
    title, content = body["title"], body["content"]
    existing_path = body.get("path")

    if existing_path:
        path = Path(existing_path)
        resolved = path.resolve()
        if not resolved.is_relative_to(DOCUMENTS_DIR.resolve()) or not resolved.is_file():
            return Response(status_code=400, content="invalid path")
    else:
        path = DOCUMENTS_DIR / _safe_filename(title)

    path.write_text(content)

    action = ingest_file(conn, embedder.embed_documents, path)
    metrics.INGESTED_DOCUMENTS.labels(action=action).inc()
    logger.info("document %s via UI path=%s", action, path)

    return {"action": action, "documents": repository.list_documents(conn)}


@router.get("/metrics")
def get_metrics():
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type)
