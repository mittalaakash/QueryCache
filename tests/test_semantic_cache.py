from datetime import date

from app.rag.cache import extract_cache_slots

TODAY = date(2026, 6, 1)  # so "this year" -> 2026, "this quarter" -> Q2


def test_extract_cache_slots_explicit_quarter_and_year():
    slots = extract_cache_slots("What was Apple's revenue in Q1 2025?", TODAY)
    assert slots == frozenset({"2025", "Q1"})


def test_extract_cache_slots_different_year_gives_different_slots():
    slots_2025 = extract_cache_slots("Apple revenue in Q1 2025", TODAY)
    slots_2026 = extract_cache_slots("Apple revenue in Q1 2026", TODAY)
    assert slots_2025 != slots_2026


def test_extract_cache_slots_canonicalizes_relative_phrasing_to_same_quarter():
    explicit = extract_cache_slots("Apple revenue in Q1 2026", TODAY)
    relative = extract_cache_slots(
        "Apple revenue in the first three months of this year", TODAY
    )
    assert explicit == relative == frozenset({"2026", "Q1"})


def test_extract_cache_slots_no_dates_or_numbers_is_empty():
    slots = extract_cache_slots("What does the billing FAQ say about rate limits?", TODAY)
    assert slots == frozenset()


def test_extract_cache_slots_catches_non_date_numeric_mismatch():
    top5 = extract_cache_slots("Who are the top 5 customers?", TODAY)
    top10 = extract_cache_slots("Who are the top 10 customers?", TODAY)
    assert top5 != top10
