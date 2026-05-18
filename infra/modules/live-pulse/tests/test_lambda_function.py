"""Unit tests for the live-pulse poller's pure logic — no AWS, no network.

Run: python -m pytest modules/live-pulse/tests/ -v
"""
import json
import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

import lambda_function as lf  # noqa: E402


# --- z_to_100 mapping (must match build_pressure.py) -----------------------
def test_z_to_100_centre():
    assert lf.z_to_100(0) == 50


def test_z_to_100_one_sigma():
    assert lf.z_to_100(1) == 70
    assert lf.z_to_100(-1) == 30


def test_z_to_100_clamps():
    assert lf.z_to_100(100) == 100  # upper clamp
    assert lf.z_to_100(-100) == 2   # lower clamp (floor is 2, not 0)


# --- window stamp generation ----------------------------------------------
def test_window_stamps_count_and_order():
    from datetime import datetime

    t0 = datetime(2026, 6, 12, 3, 0, 0)
    stamps = lf._window_stamps(t0, 24)
    assert len(stamps) == 24 * 4          # 96 fifteen-minute slots
    assert stamps[0] == "20260612030000"  # newest first
    assert stamps[1] == "20260612024500"  # 15 min earlier
    assert all(len(s) == 14 for s in stamps)


# --- incremental fetch selection ------------------------------------------
def test_select_fetch_skips_cached_outside_recent_window():
    wanted = ["20260612030000", "20260612024500", "20260612020000", "20260611120000"]
    buckets = {"20260612024500": {}, "20260611120000": {}}  # two already cached
    recent_cut = "20260612023000"  # last 30 min are re-fetched
    to_fetch, skipped = lf.select_fetch(wanted, buckets, recent_cut, max_fetch=100)
    # 0300 is uncached; 0245 is cached but >= recent_cut so re-fetched;
    # 0200 uncached; 1120(prev day) is cached AND below the cut -> skipped.
    assert set(to_fetch) == {"20260612030000", "20260612024500", "20260612020000"}
    assert "20260611120000" not in to_fetch
    assert skipped == 0


def test_select_fetch_newest_first_and_cap():
    wanted = [f"202606120{h}0000" for h in (9, 8, 7, 6, 5)]  # 5 uncached slots
    to_fetch, skipped = lf.select_fetch(wanted, {}, recent_cut="0", max_fetch=3)
    assert to_fetch == ["20260612090000", "20260612080000", "20260612070000"]
    assert skipped == 2  # the two oldest deferred, reported (never silent)


# --- window rollup ---------------------------------------------------------
def test_roll_window_sums_only_in_window_and_known_countries():
    win = {"20260612030000", "20260612024500"}
    buckets = {
        "20260612030000": {"LBN": [100, 1, 2, 3, 4, 5, 6]},
        "20260612024500": {"LBN": [50, 0, 1, 0, 1, 0, 1]},
        "20260612010000": {"LBN": [999, 9, 9, 9, 9, 9, 9]},  # out of window
        "20260612030000_x": {},
        "20260612030000z": {"ZZZ": [10, 1, 1, 1, 1, 1, 1]},  # unknown iso3, out of win anyway
    }
    agg = lf.roll_window(buckets, win)
    assert agg["LBN"] == [150, 1, 3, 3, 5, 5, 7]
    # An unknown country in the window must be ignored, not crash.
    buckets2 = {"20260612030000": {"ZZZ": [10, 1, 1, 1, 1, 1, 1]}}
    agg2 = lf.roll_window(buckets2, win)
    assert agg2["LBN"] == [0, 0, 0, 0, 0, 0, 0]


# --- cell computation + sparsity suppression -------------------------------
def test_compute_cells_valid_zscore():
    # share = 20/1000 = 0.02; mu=0.01, sigma=0.005 -> z = 2.0 -> pulse 90.
    agg = {"LBN": [1000, 20, 0, 0, 0, 0, 0]}
    stats = {"LBN|T01": {"mu": 0.01, "sigma": 0.005}}
    cells = lf.compute_cells(agg, stats)
    assert cells["LBN|T01"]["pulse"] == 90
    assert cells["LBN|T01"]["z"] == 2.0


def test_compute_cells_sparsity_low_total_is_null_not_zero():
    agg = {"LBN": [50, 20, 0, 0, 0, 0, 0]}  # total below MIN_COUNTRY_DOCS(200)
    stats = {"LBN|T01": {"mu": 0.01, "sigma": 0.005}}
    cells = lf.compute_cells(agg, stats)
    assert cells["LBN|T01"]["pulse"] is None  # never 0 — absence != calm
    assert cells["LBN|T01"]["total"] == 50


def test_compute_cells_sparsity_low_topic_is_null():
    agg = {"LBN": [1000, 2, 0, 0, 0, 0, 0]}  # topic docs below MIN_TOPIC_DOCS(5)
    stats = {"LBN|T01": {"mu": 0.01, "sigma": 0.005}}
    cells = lf.compute_cells(agg, stats)
    assert cells["LBN|T01"]["pulse"] is None


def test_compute_cells_missing_baseline_is_null():
    agg = {"LBN": [1000, 20, 0, 0, 0, 0, 0]}
    cells = lf.compute_cells(agg, stats={})  # no stat for this cell
    assert cells["LBN|T01"]["pulse"] is None


def test_compute_cells_zero_sigma_does_not_divide_by_zero():
    agg = {"LBN": [1000, 20, 0, 0, 0, 0, 0]}
    stats = {"LBN|T01": {"mu": 0.01, "sigma": 0.0}}  # degenerate baseline
    cells = lf.compute_cells(agg, stats)
    # share(0.02) > mu(0.01) and sigma floored to 1e-9 -> huge z -> clamps 100.
    assert cells["LBN|T01"]["pulse"] == 100


# --- board topics stay in sync with the validated pattern file -------------
def test_board_patterns_match_topic_theme_patterns_json():
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..",
                     "qgi-gdelt-poc", "topic_theme_patterns.json"),
        os.path.expanduser("~/qgi-gdelt-poc/topic_theme_patterns.json"),
    ]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if path is None:
        pytest.skip("topic_theme_patterns.json not reachable in this checkout")
    patterns = json.load(open(path, encoding="utf-8"))["patterns"]
    for tid in lf.BOARD:
        assert lf.TOPIC_PATTERNS[tid] == patterns[tid]["re"], (
            f"{tid} drifted from the validated pattern file"
        )


def test_board_has_six_topics_and_each_compiles():
    assert lf.BOARD == ["T01", "T02", "T03", "T05", "T06", "T07"]
    for tid in lf.BOARD:
        assert tid in lf.TOPIC_RE  # compiled without error at import


# --- article capture + feed roll-up ----------------------------------------
def test_article_row_parses_columns():
    row = [""] * 16
    row[lf.C_DATE] = "20260614013000"
    row[lf.C_DOMAIN] = "example.com"
    row[lf.C_URL] = "https://example.com/iran-vote"
    row[lf.C_TONE] = "-3.2,1,4,5"
    hits = [1, 0, 0, 0, 0, 0]  # first matched board topic -> T01
    art = lf._article_row(row, hits, "20260614013000")
    assert art["url"] == "https://example.com/iran-vote"
    assert art["domain"] == "example.com"
    assert art["dt"] == "20260614013000"
    assert art["tone"] == -3.2
    assert art["topic"] == "T01"
    assert art["topicLabel"] == "Electoral"


def test_article_row_none_without_url():
    row = [""] * 16
    assert lf._article_row(row, [1, 0, 0, 0, 0, 0], "20260614013000") is None


def test_article_row_unparseable_tone_is_null():
    row = [""] * 16
    row[lf.C_URL] = "https://x.com/a"
    row[lf.C_TONE] = "not-a-number"
    art = lf._article_row(row, [0, 1, 0, 0, 0, 0], "20260614013000")
    assert art["tone"] is None
    assert art["topic"] == "T02"


def test_merge_articles_dedup_window_and_strip_iso3():
    from datetime import datetime

    t0 = datetime(2026, 6, 14, 1, 30, 0)
    existing = {"LBN": [{"dt": "20260613020000", "url": "u-old", "topic": "T02"}]}
    new_rows = [
        {"iso3": "LBN", "dt": "20260614010000", "url": "u-new", "topic": "T05"},
        {"iso3": "LBN", "dt": "20260614013000", "url": "u-old", "topic": "T02"},  # newer dup
        {"iso3": "EGY", "dt": "20260601000000", "url": "u-stale", "topic": "T01"},  # > 24h old
    ]
    out = lf.merge_articles(existing, new_rows, t0, window_hours=24, cap=40)
    assert [r["url"] for r in out["LBN"]] == ["u-old", "u-new"]  # newest first
    assert out["LBN"][0]["dt"] == "20260614013000"  # dedup kept the newer copy
    assert all("iso3" not in r for r in out["LBN"])
    assert "EGY" not in out  # only row was older than the window -> country dropped


def test_merge_articles_respects_per_country_cap():
    from datetime import datetime

    t0 = datetime(2026, 6, 14, 1, 30, 0)
    new_rows = [
        {"iso3": "LBN", "dt": f"2026061401{i:02d}00", "url": f"u{i}", "topic": "T02"}
        for i in range(10)
    ]
    out = lf.merge_articles({}, new_rows, t0, window_hours=24, cap=3)
    assert len(out["LBN"]) == 3
    assert out["LBN"][0]["url"] == "u9"  # newest kept
