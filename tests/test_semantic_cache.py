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


def test_extract_cache_slots_fiscal_year_different_years_different_slots():
    """FY2025 and FY2026 must produce different slots (critical bug fix).
    Ensures fiscal years like FY2025 are correctly parsed even when
    letter-adjacent to digits (no word boundary between Y and 2)."""
    slots_fy2025 = extract_cache_slots("Apple revenue in FY2025", TODAY)
    slots_fy2026 = extract_cache_slots("Apple revenue in FY2026", TODAY)
    assert slots_fy2025 != slots_fy2026
    # Verify both correctly extracted the 4-digit years
    assert "2025" in slots_fy2025
    assert "2026" in slots_fy2026


def test_extract_cache_slots_fiscal_year_short_form():
    """Short fiscal year form FY25 (2025) must be distinguishable from FY26."""
    slots_fy25 = extract_cache_slots("What was FY25 revenue?", TODAY)
    slots_fy26 = extract_cache_slots("What was FY26 revenue?", TODAY)
    assert slots_fy25 != slots_fy26
    assert "2025" in slots_fy25
    assert "2026" in slots_fy26


def test_extract_cache_slots_bare_quarter_gets_implicit_year():
    """Bare quarter 'Q1 revenue' without explicit year must include today's year.
    Ensures 'Q1 revenue' asked in 2025 ≠ 'Q1 revenue' asked in 2026."""
    slots = extract_cache_slots("What was Q1 revenue?", TODAY)
    assert "Q1" in slots
    assert str(TODAY.year) in slots
    assert slots == frozenset({"Q1", "2026"})


def test_extract_cache_slots_unrelated_number_not_excluded_by_quarter_digit():
    """Regression test: ensure numbers sharing a digit value with a quarter
    (e.g., '3' in 'top 3' and '3' in 'Q3') are not confused.
    The number '3' at position of 'top 3' and quarter digit '3' at position of 'Q3'
    are different tokens at different spans and must both be tracked."""
    with_number = extract_cache_slots("What were the top 3 customers in Q3?", TODAY)
    without_number = extract_cache_slots("What was the revenue in Q3?", TODAY)

    # With unrelated number: should have both "3" and "Q3"
    assert "3" in with_number
    assert "Q3" in with_number

    # Without unrelated number: should have only "Q3", no "3"
    assert "3" not in without_number
    assert "Q3" in without_number

    # They must be different (to prevent wrong cache hits)
    assert with_number != without_number
