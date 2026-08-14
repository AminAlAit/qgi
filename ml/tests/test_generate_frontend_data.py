"""Unit tests for generate_frontend_data.py pure functions.

Deferred: generate_frontend_data.py has NO extractable pure functions at
module scope. Every function (generate_partners_index, generate_pattern_density,
generate_structural_twins, generate_pair_windows, generate_analogues,
generate_indicator_trajectories) takes a live `athena` boto3 client as its
first argument and immediately calls run_athena_query().

The only pure-ish logic (name_to_slug, partner sorting, structural-twins
top-5 selection, density accumulation) is embedded inside those Athena-bound
functions with no separate callsite.

Recommendation for integration follow-up:
  - Extract name_to_slug() to module level (it is duplicated vs
    generate_country_risks.py's equivalent transform).
  - Extract _build_partners_index_from_rows(rows, id_to_name, id_to_alpha2)
    as a pure helper so it can be unit-tested with hand-crafted row lists.
  - Extract _top_n_twins(pairs_dict, n=5) as a pure helper.

Until those extractions happen, meaningful tests require mocking boto3 at the
client level — which is integration-level, not unit-level.

#373 test coverage audit — deferred: integration-level test harness needed.

Source-text sentinels (#521): cheap regression guards that don't need a
boto3 mock — they just `read_text()` the script and assert SQL shape.
Defends specific properties we've explicitly chosen and could regress on.
"""
from pathlib import Path

import pytest


_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "generate_frontend_data.py"
)


def test_deferred_integration_level():
    """Placeholder — pure functions not yet extracted from Athena-bound functions.

    See module docstring above for the specific extractions needed.
    Tracked under #373.
    """
    pytest.skip(
        "generate_frontend_data.py: all business logic is embedded inside "
        "Athena-calling functions. Pure helpers must be extracted before "
        "unit tests can be written. See module docstring."
    )


# ─── #521 source-text sentinels ──────────────────────────────────────────────


def test_analogues_query_reads_recipes_deduped_not_raw_recipes():
    """#521 (Fork B follow-up): the analogues query must source from
    `qgi_data.recipes_deduped` (the bullet-6 dedup view, #458), NOT
    `qgi_data.recipes` directly. Reading the raw table re-introduces the
    nested-length-pattern inflation that #458 was designed to fix.

    Defends against an accidental revert in a refactor or merge resolution.
    """
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "FROM qgi_data.recipes_deduped" in text, (
        "analogues query must read from `qgi_data.recipes_deduped` (#458 dedup "
        "view), per #521 fix"
    )
    # Also pin the regression: the un-dedup'd `FROM qgi_data.recipes` SHOULD
    # NOT appear AS A LIVE QUERY anywhere in this script. Comments referencing
    # the old name are fine — they describe history. The grep below catches
    # the live form by requiring whitespace + the bare table name without the
    # `_deduped` suffix.
    import re
    live_raw_reads = re.findall(
        r"FROM\s+qgi_data\.recipes(?!\w)",
        text,
    )
    # Each match should be `FROM qgi_data.recipes_deduped` (the regex above
    # already excludes `_deduped` via `(?!\w)`, so any matches here are bare).
    assert not live_raw_reads, (
        f"Unexpected live read of `qgi_data.recipes` (Level-3) in "
        f"generate_frontend_data.py — must use `recipes_deduped` (#521). "
        f"Found {len(live_raw_reads)} such reference(s)."
    )
