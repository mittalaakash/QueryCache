"""Incremental ingestion: walk documents/*.md, hash each file, and only
re-chunk/re-embed files whose content changed since the last run. Updating
or deleting a document invalidates any semantic-cache answers that used it
as a source, so stale answers are never served after content changes."""

import hashlib
import logging
from pathlib import Path
from typing import Callable, Literal

from app.core.chunking import split_into_chunks
from app.db import repository

EmbedFn = Callable[[list[str]], list[list[float]]]
Action = Literal["insert", "update", "skip"]

logger = logging.getLogger("ingestion")


def decide_action(existing_hash: str | None, new_hash: str) -> Action:
    if existing_hash is None:
        return "insert"
    if existing_hash == new_hash:
        return "skip"
    return "update"


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def ingest_file(conn, embed_fn: EmbedFn, path: Path) -> Action:
    content = path.read_text()
    new_hash = hashlib.sha256(content.encode()).hexdigest()

    existing = repository.get_document(conn, str(path))
    action = decide_action(existing["content_hash"] if existing else None, new_hash)
    if action == "skip":
        return action

    title = _extract_title(content, fallback=path.stem)
    chunks = split_into_chunks(content)
    chunk_embeddings = embed_fn(chunks)

    doc_id = repository.upsert_document(conn, str(path), title, new_hash)
    repository.replace_chunks(conn, doc_id, chunks, chunk_embeddings)

    if action == "update":
        invalidated = repository.invalidate_cache_for_documents(conn, [doc_id])
        if invalidated:
            logger.info("invalidated %d cached answer(s) referencing %s", invalidated, path)

    return action


def sync_documents(conn, embed_fn: EmbedFn, documents_dir: Path) -> dict:
    paths = sorted(documents_dir.glob("*.md"))
    disk_paths = {str(p) for p in paths}

    counts = {"insert": 0, "update": 0, "skip": 0}
    for path in paths:
        action = ingest_file(conn, embed_fn, path)
        counts[action] += 1

    # Invalidate cache entries for documents about to be deleted BEFORE
    # deleting them: the delete cascades away query_cache_documents rows
    # first, which would make invalidation a no-op if done afterward.
    deleted_ids = repository.find_documents_not_in(conn, disk_paths)
    repository.invalidate_cache_for_documents(conn, deleted_ids)
    repository.delete_documents(conn, deleted_ids)
    counts["delete"] = len(deleted_ids)

    return counts
