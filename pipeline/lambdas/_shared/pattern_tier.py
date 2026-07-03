"""Single source of truth for the pattern_tier S/M/L/XL bucketing (#128, #558).

The pattern_tier label is derived from a pattern's length-in-years and was
previously defined as an inline `CASE WHEN length BETWEEN N AND M THEN ...`
SQL block in 7 places across 4 Lambda functions (pipeline-c-worker,
pipeline-recipe-engine, pipeline-recipe-engine-finalize,
pipeline-recipe-engine-list-formatter). Drifting boundaries would silently
produce inconsistent recipe data; #558 consolidated all 7 to import from
this module.

## Schema

Tiers are exhaustive over length in [3, +infinity):

    length 3 to 8   -> "S"
    length 9 to 20  -> "M"
    length 21 to 40 -> "L"
    length 41+      -> "XL"

The lower floor of 3 matches the SCDI minimum window. There is no upper
cap; XL is open-ended.

## Python + SQL parity

Both `length_to_pattern_tier()` (Python) and `pattern_tier_case_sql()`
(SQL template) MUST emit the same label for every integer length. The
parity is regression-tested via `test_pattern_tier_python_matches_sql`
in the pipeline-recipe-engine-list-formatter test suite (mirrors the
same parity guard used for the 12-bucket length axis in #534).

## How this module ships with each Lambda

The deploy workflow at `.github/workflows/deploy-lambdas.yml` copies
`lambdas/_shared/*.py` into each Lambda's bundle before zipping, so
each runtime gets its own copy. Lambdas import via
`from _shared.pattern_tier import PATTERN_TIERS, length_to_pattern_tier,
pattern_tier_case_sql`. The module itself has no runtime dependencies
beyond the Python stdlib.
"""

from __future__ import annotations

# Tuple in length-order. Used by external code that needs to enumerate
# the tier vocabulary (e.g. validation against an enum column).
PATTERN_TIERS: tuple[str, ...] = ("S", "M", "L", "XL")

# Inclusive (min_length, max_length_inclusive_or_None) per tier. XL has
# `max=None` to signal open-ended upper bound; do not substitute a
# sentinel like 999999 because some SQL dialects coerce that into a
# narrow integer and corrupt the BETWEEN clause.
PATTERN_TIER_RANGES: dict[str, tuple[int, int | None]] = {
    "S": (3, 8),
    "M": (9, 20),
    "L": (21, 40),
    "XL": (41, None),
}


def length_to_pattern_tier(length: int) -> str:
    """Python port of the SQL CASE expression. Used by any pipeline code
    that needs to compute a pattern_tier from a length without round-
    tripping through Athena.

    Mirrors `pattern_tier_case_sql()` exactly — any change in one MUST
    be reflected in the other (regression-tested).

    Returns "S" for length < 3 (defensive — SCDI floor is 3, but a
    smaller value would otherwise return None and propagate into NULL
    pattern_tier columns).
    """
    if length < 3:
        return "S"
    if length <= 8:
        return "S"
    if length <= 20:
        return "M"
    if length <= 40:
        return "L"
    return "XL"


# Template for the SQL CASE expression. Call sites substitute the length
# column prefix via `.format(length="p.length")` or `.format(length=
# "length")` depending on whether they alias the patterns table.
#
# Keep this in sync with length_to_pattern_tier() above — the parity
# test in pipeline-recipe-engine-list-formatter pins every integer in
# [0, 200] across both implementations.
PATTERN_TIER_CASE_SQL_TEMPLATE: str = """CASE
                WHEN {length} BETWEEN 3 AND 8  THEN 'S'
                WHEN {length} BETWEEN 9 AND 20 THEN 'M'
                WHEN {length} BETWEEN 21 AND 40 THEN 'L'
                ELSE 'XL'
            END"""


def pattern_tier_case_sql(length_column: str = "length") -> str:
    """Render the SQL CASE expression with the given length column
    reference substituted in. Use the no-prefix form for INSERT...SELECT
    contexts (`length`) and the aliased form for SELECT FROM patterns
    queries (`p.length`).

    Example:
        >>> pattern_tier_case_sql("p.length")
        "CASE\\n                WHEN p.length BETWEEN 3 AND 8  THEN 'S'\\n..."

    The template's whitespace is calibrated to be drop-in for the
    existing SQL strings — call sites need no extra indentation
    adjustment when replacing inline CASE blocks.
    """
    return PATTERN_TIER_CASE_SQL_TEMPLATE.format(length=length_column)
