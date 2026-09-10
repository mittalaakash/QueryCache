"""Semantic cache: lookup/store, gated by both embedding similarity and a
deterministic 'slots' match.

Embedding similarity alone can't tell 'Q1 2025' from 'Q1 2026' apart — they
are semantically close but factually different questions. extract_cache_slots
pulls out every year/quarter/number a question mentions or implies (resolving
relative phrases like 'this year' against today's date) so a cache hit is
only allowed when both the embedding distance is small AND the slot sets are
identical. This also lets paraphrases of the same period ('the first three
months of this year' vs 'Q1 2026') collide onto the same cache entry.

ponytail: phrase/month-group tables cover common phrasings only, not full
date-language understanding — extend the tables (or swap in a real
date-parsing library) if a phrasing shows up that isn't recognized.
"""

import re
from datetime import date

from app.config import settings
from app.core.embeddings import embedder
from app.db import repository

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_EXPLICIT_QUARTER_RE = re.compile(r"\bq([1-4])\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")

_QUARTER_WORDS = {
    "first quarter": "Q1", "quarter one": "Q1",
    "second quarter": "Q2", "quarter two": "Q2",
    "third quarter": "Q3", "quarter three": "Q3",
    "fourth quarter": "Q4", "quarter four": "Q4",
}
_RELATIVE_YEAR_WORDS = {
    "this year": 0, "current year": 0,
    "last year": -1, "previous year": -1,
    "next year": 1,
}
_RELATIVE_QUARTER_WORDS = {"this quarter", "current quarter"}

_MONTH_NAME_TO_ABBR = {
    "january": "jan", "february": "feb", "march": "mar", "april": "apr",
    "may": "may", "june": "jun", "july": "jul", "august": "aug",
    "september": "sep", "october": "oct", "november": "nov", "december": "dec",
    "jan": "jan", "feb": "feb", "mar": "mar", "apr": "apr", "jun": "jun",
    "jul": "jul", "aug": "aug", "sep": "sep", "sept": "sep", "oct": "oct",
    "nov": "nov", "dec": "dec",
}
_MONTHS_TO_QUARTER = {
    frozenset({"jan", "feb", "mar"}): "Q1",
    frozenset({"apr", "may", "jun"}): "Q2",
    frozenset({"jul", "aug", "sep"}): "Q3",
    frozenset({"oct", "nov", "dec"}): "Q4",
}
_QUARTER_PHRASES = {
    "first three months": "Q1", "first 3 months": "Q1",
}


def extract_cache_slots(query: str, today: date) -> frozenset[str]:
    lowered = query.lower()
    slots: set[str] = set()

    explicit_years = {m.group(0) for m in _YEAR_RE.finditer(query)}
    slots |= explicit_years

    for phrase, offset in _RELATIVE_YEAR_WORDS.items():
        if phrase in lowered:
            slots.add(str(today.year + offset))

    for m in _EXPLICIT_QUARTER_RE.finditer(query):
        slots.add(f"Q{m.group(1)}")
    for phrase, quarter in _QUARTER_WORDS.items():
        if phrase in lowered:
            slots.add(quarter)

    if any(phrase in lowered for phrase in _RELATIVE_QUARTER_WORDS):
        slots.add(f"Q{(today.month - 1) // 3 + 1}")

    months_found = {
        _MONTH_NAME_TO_ABBR[w]
        for w in re.findall(r"[a-zA-Z]+", lowered)
        if w in _MONTH_NAME_TO_ABBR
    }
    for month_set, quarter in _MONTHS_TO_QUARTER.items():
        if month_set <= months_found:
            slots.add(quarter)

    for phrase, quarter in _QUARTER_PHRASES.items():
        if phrase in lowered:
            slots.add(quarter)

    for m in _NUMBER_RE.finditer(query):
        token = m.group(0).replace(",", "")
        if token not in explicit_years:
            slots.add(token)

    return frozenset(slots)


def lookup(conn, question: str) -> tuple[dict | None, list[float], frozenset[str]]:
    """Returns (cached_result_or_None, question_embedding, slots). The caller
    passes the embedding/slots through to store() on a miss so the question
    is only embedded once per query."""
    query_embedding = embedder.embed_query(question)
    query_slots = extract_cache_slots(question, date.today())

    candidates = repository.find_cache_candidates(
        conn,
        query_embedding,
        limit=settings.semantic_cache_candidates,
        ttl_seconds=settings.semantic_cache_ttl_seconds,
    )
    for candidate in candidates:
        if candidate["distance"] <= settings.semantic_cache_threshold and candidate["slots"] == query_slots:
            return {"answer": candidate["answer"], "sources": candidate["sources"]}, query_embedding, query_slots

    return None, query_embedding, query_slots


def store(
    conn,
    question: str,
    question_embedding: list[float],
    slots: frozenset[str],
    answer: str,
    sources: list[dict],
    document_ids: list[int],
) -> None:
    repository.store_cache_entry(conn, question, question_embedding, set(slots), answer, sources, document_ids)
