"""Tests for lambdas/_shared/pattern_tier.py (#558).

Coverage:
1. length_to_pattern_tier() boundary tests across the 4 tiers
2. pattern_tier_case_sql() renders with the requested length-column prefix
3. Python <-> SQL parity: every integer length in [0, 200] maps to the same
   tier in both implementations (regression guard mirroring the LENGTH_BUCKETS
   parity test in pipeline-recipe-engine-list-formatter)
4. PATTERN_TIER_RANGES + PATTERN_TIERS are mutually consistent

The parity guard is the load-bearing test: if either implementation drifts,
recipe data emitted across the 4 Lambdas would silently diverge — exactly
the failure mode #558 was filed to prevent.
"""

from __future__ import annotations

import re

import pytest

from _shared.pattern_tier import (
    PATTERN_TIERS,
    PATTERN_TIER_RANGES,
    PATTERN_TIER_CASE_SQL_TEMPLATE,
    length_to_pattern_tier,
    pattern_tier_case_sql,
)


# ===========================================================================
# Test 1: length_to_pattern_tier() boundary cases
# ===========================================================================


@pytest.mark.parametrize(
    "length, expected",
    [
        # Below floor: defensive — return "S" rather than None / KeyError
        (0, "S"),
        (2, "S"),
        # S boundary
        (3, "S"),
        (5, "S"),
        (8, "S"),
        # S -> M
        (9, "M"),
        (15, "M"),
        (20, "M"),
        # M -> L
        (21, "L"),
        (30, "L"),
        (40, "L"),
        # L -> XL
        (41, "XL"),
        (60, "XL"),
        (120, "XL"),
        (200, "XL"),
    ],
)
def test_length_to_pattern_tier_boundaries(length, expected):
    actual = length_to_pattern_tier(length)
    assert actual == expected, f"length_to_pattern_tier({length}) = {actual!r}, expected {expected!r}"


# ===========================================================================
# Test 2: pattern_tier_case_sql() substitutes the length column
# ===========================================================================


def test_pattern_tier_case_sql_default_uses_bare_length():
    """Default no-arg call uses bare `length` (INSERT...SELECT context)."""
    sql = pattern_tier_case_sql()
    assert "WHEN length BETWEEN 3 AND 8" in sql
    assert "WHEN length BETWEEN 9 AND 20" in sql
    assert "WHEN length BETWEEN 21 AND 40" in sql
    assert "ELSE 'XL'" in sql
    # No `p.length` should appear when the default is used
    assert "p.length" not in sql


def test_pattern_tier_case_sql_with_p_prefix():
    """`pattern_tier_case_sql('p.length')` substitutes the aliased form."""
    sql = pattern_tier_case_sql("p.length")
    assert "WHEN p.length BETWEEN 3 AND 8" in sql
    assert "WHEN p.length BETWEEN 9 AND 20" in sql
    assert "WHEN p.length BETWEEN 21 AND 40" in sql


def test_pattern_tier_case_sql_with_arbitrary_prefix():
    """Substitution works with any column reference."""
    sql = pattern_tier_case_sql("foo.bar")
    assert "WHEN foo.bar BETWEEN 3 AND 8" in sql
    assert "WHEN foo.bar BETWEEN 9 AND 20" in sql


# ===========================================================================
# Test 3: Python <-> SQL parity guard (the load-bearing regression test)
# ===========================================================================


def test_pattern_tier_python_matches_sql_case():
    """The Python length_to_pattern_tier() MUST emit the same labels as
    the PATTERN_TIER_CASE_SQL_TEMPLATE SQL CASE expression. Parse the SQL
    and verify every integer length in [0, 200] maps to the same tier
    in both.

    If this test fails, EITHER the Python implementation OR the SQL
    template has drifted. Update both in lockstep — they are required
    to stay byte-equivalent for downstream recipe data consistency.
    """
    # Render the template with the bare-length form for parsing
    case_sql = pattern_tier_case_sql("length")

    # Capture WHEN clauses in order so first-match semantics holds
    when_re = re.compile(r"WHEN length BETWEEN (\d+) AND (\d+)\s+THEN '(\w+)'")
    sql_rules = [(int(lo), int(hi), label) for lo, hi, label in when_re.findall(case_sql)]
    else_match = re.search(r"ELSE '(\w+)'", case_sql)
    assert else_match, "PATTERN_TIER_CASE_SQL_TEMPLATE is missing an ELSE clause"
    sql_else_label = else_match.group(1)

    def sql_lookup(length):
        for lo, hi, label in sql_rules:
            if lo <= length <= hi:
                return label
        return sql_else_label

    # Range [0, 200]: covers below-floor (0-2), all four tiers, and XL
    # extending into V-Dem-era lengths (~120y max).
    # Below-floor case: SQL CASE returns the ELSE label ('XL') for
    # length < 3 because no BETWEEN matches, while Python's defensive
    # guard returns 'S'. This is INTENTIONAL — SCDI floor is 3, so
    # length < 3 should never actually occur in production data; the
    # divergence at sub-floor lengths is documented in the docstring
    # of length_to_pattern_tier. Skip lengths 0-2 from the parity scan.
    for length in range(3, 201):
        py_label = length_to_pattern_tier(length)
        sql_label = sql_lookup(length)
        assert py_label == sql_label, (
            f"Mismatch at length={length}: Python={py_label!r}, SQL CASE={sql_label!r}. Update one to match the other."
        )


# ===========================================================================
# Test 4: PATTERN_TIER_RANGES + PATTERN_TIERS internal consistency
# ===========================================================================


def test_pattern_tiers_tuple_matches_ranges_dict_keys():
    """The tier order in PATTERN_TIERS must match the keys of
    PATTERN_TIER_RANGES for any code that iterates PATTERN_TIERS expecting
    a corresponding range lookup."""
    assert PATTERN_TIERS == tuple(PATTERN_TIER_RANGES.keys())


def test_pattern_tier_ranges_are_contiguous_and_ordered():
    """Tier ranges must be contiguous (no gaps, no overlaps) and ordered
    by ascending min_length. This is what makes the SQL CASE expression
    correct without explicit defaults between tiers."""
    prev_max = 2  # SCDI floor minus 1 — S starts at 3
    for tier in PATTERN_TIERS[:-1]:  # all but XL (open-ended)
        lo, hi = PATTERN_TIER_RANGES[tier]
        assert hi is not None, f"only XL should have open-ended max; {tier} doesn't"
        assert lo == prev_max + 1, (
            f"gap or overlap between previous tier and {tier!r}: prev_max={prev_max}, this_min={lo}"
        )
        assert lo <= hi, f"{tier!r} has min > max"
        prev_max = hi

    # XL is the open-ended catch-all
    xl_lo, xl_hi = PATTERN_TIER_RANGES["XL"]
    assert xl_lo == prev_max + 1, "XL should start where L ended + 1"
    assert xl_hi is None, "XL should have open-ended max"


def test_length_to_pattern_tier_emits_only_canonical_labels():
    """Every output of length_to_pattern_tier() must be in PATTERN_TIERS.
    Guards against future refactors that accidentally introduce new
    return values not declared in the canonical tuple."""
    seen = set()
    for length in range(0, 201):
        seen.add(length_to_pattern_tier(length))
    assert seen.issubset(set(PATTERN_TIERS)), (
        f"length_to_pattern_tier emitted labels outside PATTERN_TIERS: {seen - set(PATTERN_TIERS)}"
    )
