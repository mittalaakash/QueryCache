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
_FY_RE = re.compile(r"\bfy\s?(\d{2})\b", re.IGNORECASE)
_EXPLICIT_QUARTER_RE = re.compile(r"\bq\s?([1-4])\b", re.IGNORECASE)
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


def _space_letter_digit_boundaries(text: str) -> str:
    """Insert spaces at letter↔digit boundaries to help word-boundary regexes.
    Transforms "FY2025" → "FY 2025" and "Q1FY25" → "Q1 FY 25" so that
    \b-anchored patterns can correctly identify years/quarters."""
    text = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", text)
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)
    return text


def extract_cache_slots(query: str, today: date) -> frozenset[str]:
    # Insert spaces at letter↔digit boundaries so \b-anchored regexes work correctly.
    spaced_query = _space_letter_digit_boundaries(query)
    lowered = spaced_query.lower()
    slots: set[str] = set()

    explicit_years = {m.group(0) for m in _YEAR_RE.finditer(spaced_query)}
    slots |= explicit_years

    for phrase, offset in _RELATIVE_YEAR_WORDS.items():
        if phrase in lowered:
            slots.add(str(today.year + offset))

    # Handle fiscal years like "FY2025" or "FY25" (after spacing: "FY 2025" or "FY 25")
    for m in _FY_RE.finditer(lowered):
        fy_year = int(m.group(1))
        # Convert 2-digit year to 4-digit (assumes 2000-2099)
        full_year = 2000 + fy_year
        slots.add(str(full_year))

    # Track which quarter digits we've extracted to avoid double-counting with _NUMBER_RE
    quarter_digits = set()
    for m in _EXPLICIT_QUARTER_RE.finditer(spaced_query):
        quarter_num = m.group(1)
        slots.add(f"Q{quarter_num}")
        quarter_digits.add(quarter_num)

    for phrase, quarter in _QUARTER_WORDS.items():
        if phrase in lowered:
            slots.add(quarter)
            # Extract quarter digit from string like "Q1"
            quarter_digits.add(quarter[1])

    if any(phrase in lowered for phrase in _RELATIVE_QUARTER_WORDS):
        q_num = str((today.month - 1) // 3 + 1)
        slots.add(f"Q{q_num}")
        quarter_digits.add(q_num)

    months_found = {
        _MONTH_NAME_TO_ABBR[w]
        for w in re.findall(r"[a-zA-Z]+", lowered)
        if w in _MONTH_NAME_TO_ABBR
    }
    for month_set, quarter in _MONTHS_TO_QUARTER.items():
        if month_set <= months_found:
            slots.add(quarter)
            quarter_digits.add(quarter[1])

    for phrase, quarter in _QUARTER_PHRASES.items():
        if phrase in lowered:
            slots.add(quarter)
            quarter_digits.add(quarter[1])

    for m in _NUMBER_RE.finditer(spaced_query):
        token = m.group(0).replace(",", "")
        if token not in explicit_years and token not in quarter_digits:
            slots.add(token)

    # If any quarter was found but no explicit year, add today's year for consistency.
    has_quarter = any(s.startswith("Q") and len(s) == 2 for s in slots)
    has_year = any(len(s) == 4 and s.isdigit() for s in slots)
    if has_quarter and not has_year:
        slots.add(str(today.year))

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
