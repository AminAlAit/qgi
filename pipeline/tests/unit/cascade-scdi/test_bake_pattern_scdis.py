"""Unit tests for the cascade SCDI baker (§H) — bake_pattern_scdis.

All I/O is injected, so the end-to-end bake runs with an in-memory panel accessor
(no pandas, no parquet, no S3). Covers: reference loaders, candidate flatten + `ind`
carry-through, per-pair de-dup, balanced greedy-fill to the cap, slug orientation
(alphabetical iso2 + offset), aligned-series gap handling, and the full bake map.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "batch" / "cascade-scdi"))
import bake_pattern_scdis as bp  # noqa: E402


# ---- reference loaders ------------------------------------------------------


def test_load_indexes_maps_numeric_id_to_code_name_sector():
    idx = bp.load_indexes(
        [
            {"id": "NY.GDP.MKTP.KD.ZG", "numeric_id": 1, "name": "GDP growth", "sector": "Economic"},
            {"id": "PV.EST", "numeric_id": 3, "name": "Political Stability", "sector": "Governance"},
            {"id": "NO_ID"},  # skipped — no numeric_id
        ]
    )
    assert idx[1] == {"code": "NY.GDP.MKTP.KD.ZG", "name": "GDP growth", "sector": "Economic"}
    assert idx[3]["sector"] == "Governance"
    assert len(idx) == 2


def test_load_partner_meta_collects_a2_and_name_for_both_directions():
    pm = bp.load_partner_meta(
        {
            "10": [{"p": 20, "a2": "ZZ", "n": "Zedland"}],
            "20": [{"p": 10, "a2": "AA", "n": "Aaland"}],
        }
    )
    assert pm[10] == {"a2": "AA", "name": "Aaland"}
    assert pm[20] == {"a2": "ZZ", "name": "Zedland"}


# ---- candidate flatten ------------------------------------------------------


def test_candidate_windows_flattens_and_carries_ind():
    pw = {
        "10": {"20": {"top": [{"l": 5, "sa": 2000, "sb": 2000, "ic": 2, "ac": 0.9, "pps": 9.0, "ind": [1, 2]}]}},
    }
    cands = bp.candidate_windows(pw)
    assert len(cands) == 1
    c = cands[0]
    assert (c["a_id"], c["b_id"], c["l"], c["sa"], c["sb"]) == (10, 20, 5, 2000, 2000)
    assert c["ind"] == [1, 2]


def test_candidate_windows_empty_ind_when_absent():
    pw = {"10": {"20": {"top": [{"l": 5, "sa": 2000, "sb": 2000, "ic": 2, "ac": 0.9, "pps": 9.0}]}}}
    assert bp.candidate_windows(pw)[0]["ind"] == []


# ---- per-pair de-dup --------------------------------------------------------


def test_representative_per_pair_dedups_direction_and_keeps_richest():
    cands = [
        {"a_id": 10, "b_id": 20, "l": 5, "sa": 2000, "sb": 2000, "ic": 2, "ac": 0.9, "pps": 1, "ind": [1]},
        # same canonical pair, reversed direction, MORE indicators -> wins
        {"a_id": 20, "b_id": 10, "l": 8, "sa": 1990, "sb": 1990, "ic": 4, "ac": 0.8, "pps": 1, "ind": [1, 2, 3, 4]},
    ]
    reps = bp.representative_per_pair(cands)
    assert len(reps) == 1
    assert reps[0]["ic"] == 4  # richest window kept


# ---- balanced greedy-fill ---------------------------------------------------


def test_select_patterns_balanced_rank_and_cap():
    # three distinct pairs; B has weak corr but is long+rich (PPS would over-rank it).
    cands = [
        {
            "a_id": 1,
            "b_id": 2,
            "l": 10,
            "sa": 2000,
            "sb": 2000,
            "ic": 5,
            "ac": 0.95,
            "pps": 47.5,
            "ind": [1, 2, 3, 4, 5],
        },
        {"a_id": 3, "b_id": 4, "l": 60, "sa": 1960, "sb": 1960, "ic": 2, "ac": 0.50, "pps": 60.0, "ind": [1, 2]},
        {"a_id": 5, "b_id": 6, "l": 5, "sa": 2010, "sb": 2010, "ic": 1, "ac": 0.60, "pps": 3.0, "ind": [1]},
    ]
    selected, total = bp.select_patterns(cands, size_cap_bytes=10_000)
    pairs = [(min(c["a_id"], c["b_id"]), max(c["a_id"], c["b_id"])) for c in selected]
    assert pairs[0] == (1, 2)  # strong+rich pattern ranks first (PPS would pick (3,4))
    assert len(selected) == 3 and total > 0


def test_select_patterns_respects_cap():
    cands = [
        {"a_id": 1, "b_id": 2, "l": 10, "sa": 2000, "sb": 2000, "ic": 5, "ac": 0.9, "pps": 1, "ind": [1, 2, 3, 4, 5]},
        {"a_id": 3, "b_id": 4, "l": 10, "sa": 2000, "sb": 2000, "ic": 5, "ac": 0.8, "pps": 1, "ind": [1, 2, 3, 4, 5]},
    ]
    # cap fits only one 5-indicator pattern (5*260+120 = 1420)
    selected, total = bp.select_patterns(cands, size_cap_bytes=1500)
    assert len(selected) == 1 and total <= 1500


def test_select_patterns_ranks_on_actual_ind_count_not_stale_ic():
    # `ic` is recorded at generation; `len(ind)` is the truth after enrichment. Equal
    # corr + length, so #indicators is the only differentiator. Pair Y has MORE actual
    # ids; it must rank first even though pair X claims a far larger (stale) `ic`.
    # Ranking on `ic` would wrongly pick X — this guards the B2/F2 fix.
    cands = [
        {"a_id": 1, "b_id": 2, "l": 10, "sa": 2000, "sb": 2000, "ic": 99, "ac": 0.9, "pps": 1, "ind": [1, 2]},
        {"a_id": 3, "b_id": 4, "l": 10, "sa": 2000, "sb": 2000, "ic": 3, "ac": 0.9, "pps": 1, "ind": [1, 2, 3, 4]},
    ]
    selected, _ = bp.select_patterns(cands, size_cap_bytes=100_000)
    first = (min(selected[0]["a_id"], selected[0]["b_id"]), max(selected[0]["a_id"], selected[0]["b_id"]))
    assert first == (3, 4)  # more ACTUAL indicators wins; the stale ic=99 is ignored


# ---- slug orientation -------------------------------------------------------


def test_slug_aligned_alphabetical_and_series_order():
    pm = {10: {"a2": "AA", "name": "Aaland"}, 20: {"a2": "ZZ", "name": "Zedland"}}
    window = {"a_id": 10, "b_id": 20, "sa": 2000, "sb": 2000, "l": 5}
    slug, first, second = bp.slug_and_orientation(window, pm)
    assert slug == "aa-zz-2000-2004"
    assert first["name"] == "Aaland" and second["name"] == "Zedland"


def test_slug_orientation_flips_to_alphabetical_when_file_country_is_later():
    # file-side country (a_id) is ZZ, partner is AA -> slug + series must flip to AA-first.
    pm = {10: {"a2": "ZZ", "name": "Zedland"}, 20: {"a2": "AA", "name": "Aaland"}}
    window = {"a_id": 10, "b_id": 20, "sa": 2000, "sb": 1995, "l": 6}
    slug, first, second = bp.slug_and_orientation(window, pm)
    assert first["a2"] == "AA" and first["start"] == 1995  # AA's own start year travels with it
    assert second["a2"] == "ZZ" and second["start"] == 2000
    assert slug == "aa-zz-1995-2000-6"  # 5-seg offset (different start years)


# ---- aligned series ---------------------------------------------------------


def test_aligned_series_offset_and_gap_drop():
    panel = {
        ("A", 2000): 1.0,
        ("A", 2001): 2.0,
        ("A", 2002): 3.0,
        ("B", 2005): 9.0,
        ("B", 2007): 11.0,
    }  # B missing 2006
    value_at = lambda c, y: panel.get((c, y))
    raw_a, raw_b = bp.aligned_series(value_at, "A", 2000, "B", 2005, 3)
    # position 0: A2000/B2005 ok; position 1: A2001/B2006 -> B missing, dropped;
    # position 2: A2002/B2007 ok
    assert raw_a == [1.0, 3.0]
    assert raw_b == [9.0, 11.0]


# ---- end-to-end bake --------------------------------------------------------


def _panel_value_at_factory(panels):
    def factory(code):
        d = panels.get(code, {})
        return lambda country, year: d.get((country, year))

    return factory


def test_bake_end_to_end_produces_contract():
    pw = {"10": {"20": {"top": [{"l": 5, "sa": 2000, "sb": 2000, "ic": 2, "ac": 0.9, "pps": 9.0, "ind": [1, 2]}]}}}
    indexes = [
        {"id": "GDP", "numeric_id": 1, "name": "GDP growth", "sector": "Economic"},
        {"id": "INF", "numeric_id": 2, "name": "Inflation", "sector": "Economic"},
    ]
    partners = {"10": [{"p": 20, "a2": "ZZ", "n": "Zedland"}], "20": [{"p": 10, "a2": "AA", "n": "Aaland"}]}
    panels = {
        # Aaland is country 10 (AA -> first/series_a); Zedland is 20 (ZZ -> series_b)
        "GDP": {("Aaland", y): float(v) for y, v in zip(range(2000, 2005), [1, 2, 3, 4, 5])}
        | {("Zedland", y): float(v) for y, v in zip(range(2000, 2005), [2, 4, 6, 8, 10])},
        "INF": {("Aaland", y): float(v) for y, v in zip(range(2000, 2005), [5, 4, 3, 2, 1])}
        | {("Zedland", y): float(v) for y, v in zip(range(2000, 2005), [1, 2, 3, 4, 5])},
    }
    out = bp.bake(pw, indexes, partners, _panel_value_at_factory(panels), size_cap_bytes=10_000, epochs=12)

    assert list(out.keys()) == ["aa-zz-2000-2004"]
    inds = out["aa-zz-2000-2004"]
    assert len(inds) == 2
    gdp = next(i for i in inds if i["code"] == "GDP")
    assert gdp["pearson_r"] == 1.0 and gdp["direction"] == "same"
    assert len(gdp["series_a"]) == 12 and len(gdp["series_b"]) == 12
    inf = next(i for i in inds if i["code"] == "INF")
    assert inf["pearson_r"] == -1.0 and inf["direction"] == "opposite"


def test_bake_empty_when_no_ind_enrichment():
    pw = {"10": {"20": {"top": [{"l": 5, "sa": 2000, "sb": 2000, "ic": 2, "ac": 0.9, "pps": 9.0}]}}}  # no ind
    out = bp.bake(pw, [], {}, _panel_value_at_factory({}), size_cap_bytes=10_000)
    assert out == {}


def test_bake_drops_pattern_with_no_panel_data():
    pw = {"10": {"20": {"top": [{"l": 5, "sa": 2000, "sb": 2000, "ic": 1, "ac": 0.9, "pps": 9.0, "ind": [1]}]}}}
    indexes = [{"id": "GDP", "numeric_id": 1, "name": "GDP", "sector": "Economic"}]
    partners = {"10": [{"p": 20, "a2": "ZZ", "n": "Zedland"}], "20": [{"p": 10, "a2": "AA", "n": "Aaland"}]}
    out = bp.bake(pw, indexes, partners, _panel_value_at_factory({}), size_cap_bytes=10_000)  # empty panels
    assert out == {}  # the one indicator has no data -> pattern omitted, not shipped empty
