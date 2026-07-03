"""
Source-text sentinel tests for the #519 OECD-share computation in
`write_recipes_aggregated_table()`.

Background — see [qgi-aws-tf #519](https://github.com/AminAlAit/qgi-aws-tf/issues/519):

`recipes_aggregated.coverage_bias_diagnostic.oecd_share` was a hardcoded
`0.0` placeholder. The frontend `/signals/{country}/{slug}` page renders it
as "0%" via `(coverage_bias_diagnostic.oecd_share * 100).toFixed(0)%`. #519
ships a real computation: each recipe instance's (country_a_id, country_b_id)
is JOIN'd against `qgi_data.countries → alpha_3 → OECD members VALUES`.

These tests are hermetic source-text checks (no AWS, no Athena). They
defend the most regress-prone properties of the change:

  - The `0.0` literal must not return as the oecd_share value
  - The OECD VALUES list must contain canonical members (38 countries
    as of 2026-04, post-Costa Rica accession)
  - The CTE chain must reach the final SELECT via `LEFT JOIN oecd_shares`
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "lambdas"
    / "pipeline-recipe-engine-finalize"
    / "lambda_function.py"
)


def _read_source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


# ─── canonical OECD membership ───────────────────────────────────────────────


CANONICAL_OECD_ALPHA3 = {
    "AUS",
    "AUT",
    "BEL",
    "CAN",
    "CHL",
    "COL",
    "CRI",
    "CZE",
    "DNK",
    "EST",
    "FIN",
    "FRA",
    "DEU",
    "GRC",
    "HUN",
    "ISL",
    "IRL",
    "ISR",
    "ITA",
    "JPN",
    "KOR",
    "LVA",
    "LTU",
    "LUX",
    "MEX",
    "NLD",
    "NZL",
    "NOR",
    "POL",
    "PRT",
    "SVK",
    "SVN",
    "ESP",
    "SWE",
    "CHE",
    "TUR",
    "GBR",
    "USA",
}
# 38 countries as of 2026-04. Costa Rica joined 2021, Colombia 2020,
# Lithuania 2018. If a future accession adds a member, both this set AND
# the VALUES list in the Lambda must be updated together.


# ─── tests ───────────────────────────────────────────────────────────────────


def test_oecd_members_values_clause_present():
    """The Lambda must declare the OECD members VALUES clause as a CTE.

    Defends against accidental deletion in a refactor that moves the
    oecd-share logic elsewhere.
    """
    text = _read_source()
    assert "oecd_members(alpha_3) AS (VALUES" in text, (
        "Expected `oecd_members(alpha_3) AS (VALUES (...)...)` CTE in finalize Lambda for #519 OECD-share computation."
    )


def test_oecd_members_list_matches_canonical_38():
    """The 38-country canonical OECD list must be present in the VALUES.

    A regression where someone trims the list silently (e.g., mistakenly
    drops a recently-acceded member like Costa Rica) under-counts that
    country's OECD membership and miscomputes oecd_share. This test pins
    the list against the canonical reference.

    To add a new OECD member: update both this set AND the VALUES clause
    in the Lambda. The test deliberately fails on a unilateral edit so
    the asymmetry surfaces in CI.
    """
    text = _read_source()
    # Isolate the OECD VALUES body: from `oecd_members(alpha_3) AS (VALUES`
    # forward to the start of the next CTE (`recipe_country_with_oecd AS`).
    # Anchoring on the next CTE name avoids the nested-paren matching
    # problem that regex doesn't handle natively.
    m = re.search(
        r"oecd_members\(alpha_3\)\s+AS\s+\(VALUES(?P<body>.+?)recipe_country_with_oecd\s+AS",
        text,
        flags=re.S | re.IGNORECASE,
    )
    assert m, "could not locate OECD VALUES clause"
    body = m.group("body")
    found = set(re.findall(r"'([A-Z]{3})'", body))
    missing = CANONICAL_OECD_ALPHA3 - found
    extra = found - CANONICAL_OECD_ALPHA3
    assert not missing, (
        f"OECD VALUES list is missing canonical members: {sorted(missing)}. "
        "Either the list was trimmed in error or a new OECD member needs "
        "adding to BOTH this test set and the Lambda VALUES clause."
    )
    assert not extra, (
        f"OECD VALUES list has unexpected entries: {sorted(extra)}. "
        "These alpha_3 codes are not OECD members per the 2026-04 reference; "
        "remove them or update the canonical set."
    )
    assert len(found) == 38, f"OECD member count drift: expected 38, found {len(found)}."


def test_oecd_share_is_not_zero_placeholder():
    """The Lambda must not regress to the `cast(0.0 as real)` placeholder
    for oecd_share — the entire point of #519 is to replace that with a
    real computation. The test searches for the specific placeholder
    pattern in the coverage_bias_diagnostic block.
    """
    text = _read_source()
    # The pre-#519 code had `cast(0.0 as real)` as the second positional
    # field in coverage_bias_diagnostic's row(). After the fix, this should
    # be `cast(coalesce(os.oecd_share, 0.0) as real)`. We assert the latter
    # is present and not the bare placeholder form.
    assert "coalesce(os.oecd_share, 0.0)" in text, (
        "Expected oecd_share to be wired via `coalesce(os.oecd_share, 0.0)` in the final SELECT, per #519 fix."
    )
    # Make sure the bare `cast(0.0 as real),` line that was the historic
    # placeholder isn't sitting in the same block. We allow `0.0` to appear
    # elsewhere (e.g., greatest(0.0, ...) for Wilson CI) but not as the
    # second positional field of coverage_bias_diagnostic. The simplest
    # invariant: between `cb.n_distinct_country_pairs as int)` and
    # `oecd_share real`, the value used must reference `os.oecd_share`.
    cbd_block = re.search(
        r"cb\.n_distinct_country_pairs as int\),(?P<inner>.+?)\) as row\(\s*n_pairs",
        text,
        flags=re.S,
    )
    assert cbd_block, "could not isolate coverage_bias_diagnostic row() block"
    inner = cbd_block.group("inner")
    assert "os.oecd_share" in inner, (
        "coverage_bias_diagnostic.oecd_share must be wired from os.oecd_share, not a bare 0.0 literal. #519 regression."
    )


def test_oecd_shares_cte_joined_in_final_select():
    """The `oecd_shares` CTE must be LEFT JOIN'd to category_basics in the
    final SELECT. Without this JOIN, `os.oecd_share` is unbound and Athena
    fails the query — but a regression that drops the JOIN AND falls back
    to a literal would silently return the wrong value.
    """
    text = _read_source()
    assert "LEFT JOIN oecd_shares os" in text, (
        "Final SELECT must include `LEFT JOIN oecd_shares os ON os.event_category = "
        "cb.event_category` to bind os.oecd_share. #519 regression."
    )


def test_recipe_country_pair_unnest_uses_union_all():
    """Both country_a_id and country_b_id contribute to oecd_share.

    Pinning UNION ALL (not UNION) so duplicates aren't deduped — a recipe
    with country_a_id == country_b_id (rare but possible if data is dirty)
    should still count both legs as 1 each, not collapse to 1.
    """
    text = _read_source()
    # Find the recipe_country_unnested CTE
    m = re.search(
        r"recipe_country_unnested AS \((?P<body>.+?)\),",
        text,
        flags=re.S,
    )
    assert m, "recipe_country_unnested CTE missing"
    body = m.group("body")
    assert "country_a_id AS country_id" in body
    assert "country_b_id AS country_id" in body
    assert "UNION ALL" in body, (
        "recipe_country_unnested must UNION ALL country_a_id and country_b_id "
        "so each leg of the pair contributes to OECD share."
    )


def test_countries_join_present():
    """A regression that drops the JOIN to `qgi_data.countries` (e.g., a
    refactor that tries to derive OECD membership from a different source)
    breaks the alpha_3 lookup silently. Pin the JOIN explicitly. The pattern
    matches the explicit-cast convention used elsewhere in the codebase
    (cast(c.id as integer)).
    """
    text = _read_source()
    assert "LEFT JOIN qgi_data.countries c ON cast(c.id as integer) = rcu.country_id" in text, (
        "Expected `LEFT JOIN qgi_data.countries c ON cast(c.id as integer) = rcu.country_id` "
        "in the recipe_country_with_oecd CTE. Without this JOIN, alpha_3 is unbound "
        "and the OECD VALUES JOIN matches nothing → all is_oecd = 0."
    )


def test_oecd_share_division_handles_empty_categories():
    """The OECD-share formula must be `sum(is_oecd) / nullif(count(*), 0)` —
    `nullif` guards against divide-by-zero on event_categories with no
    recipe instances (defensive, since category_basics already filters
    to non-empty categories, but pinning the division pattern catches
    a future refactor that loosens that filter).
    """
    text = _read_source()
    # The exact division form, allowing whitespace flexibility
    pat = re.compile(
        r"cast\(sum\(is_oecd\)\s+as\s+double\)\s*/\s*"
        r"nullif\(\s*cast\(count\(\*\)\s+as\s+double\)\s*,\s*0\s*\)",
        re.IGNORECASE,
    )
    assert pat.search(text), (
        "Expected `cast(sum(is_oecd) as double) / nullif(cast(count(*) as double), 0)`. "
        "If you changed the formula, update this test too."
    )
