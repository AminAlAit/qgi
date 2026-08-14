"""Unit tests for build_verified_positives.py (#112) — synthetic curated +
verification dirs in tmp; no real data, no IO outside tmp_path."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_verified_positives as bvp  # noqa: E402


def _write(d: Path, name: str, events: list[dict]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(events), encoding="utf-8")


@pytest.fixture
def dirs(tmp_path):
    cur = tmp_path / "curated"
    ver = tmp_path / "verification"
    # alpha: cat X 2000 TRUE, cat X 2001 FALSE, cat Y 2002 TRUE, dup X 2000
    _write(cur, "alpha", [
        {"category": "X", "year": 2000, "title": "x-a-2000"},
        {"category": "X", "year": 2001, "title": "x-a-2001"},
        {"category": "Y", "year": 2002, "title": "y-a-2002"},
        {"category": "X", "year": 2000, "title": "x-a-2000"},      # dup → collapses
        {"category": "X", "year": 1700, "title": "x-a-1700"},      # out of window
    ])
    _write(ver, "alpha", [
        {"year": 2000, "title": "x-a-2000", "verdict": "TRUE"},
        {"year": 2001, "title": "x-a-2001", "verdict": "FALSE"},
        {"year": 2002, "title": "y-a-2002", "verdict": "TRUE"},
        {"year": 1700, "title": "x-a-1700", "verdict": "TRUE"},     # in-verdict but out-of-window
    ])
    # beta: cat X 2000 TRUE, cat X 2003 PARTIAL (excluded), one unmatched title
    _write(cur, "beta", [
        {"category": "X", "year": 2000, "title": "x-b-2000"},
        {"category": "X", "year": 2003, "title": "x-b-2003"},
        {"category": "X", "year": 2004, "title": "x-b-2004-unmatched"},
    ])
    _write(ver, "beta", [
        {"year": 2000, "title": "x-b-2000", "verdict": "TRUE"},
        {"year": 2003, "title": "x-b-2003", "verdict": "PARTIAL"},
        # 2004 deliberately absent → unmatched
    ])
    # gamma: curated events but NO verification file → excluded from positives + rate
    _write(cur, "gamma", [
        {"category": "X", "year": 2000, "title": "x-g-2000"},
        {"category": "Z", "year": 2001, "title": "z-g-2001"},
    ])
    return cur, ver


def test_verdict_true_filter_and_dedup(dirs):
    cur, ver = dirs
    vmap = bvp.load_verdict_map(ver)
    positives, diag = bvp.build_positives(cur, vmap)
    # X: alpha-2000 (TRUE, dup collapses), beta-2000 (TRUE). NOT alpha-2001(FALSE),
    # beta-2003(PARTIAL), beta-2004(unmatched), alpha-1700(out of window), gamma(no verif).
    assert positives["X"] == {("alpha", 2000), ("beta", 2000)}
    assert positives["Y"] == {("alpha", 2002)}
    assert "Z" not in positives  # gamma unverified → excluded


def test_match_rate_excludes_unverified_countries(dirs):
    cur, ver = dirs
    vmap = bvp.load_verdict_map(ver)
    _, diag = bvp.build_positives(cur, vmap)
    # verified-country curated in window: alpha {2000,2001,2002} + beta {2000,2003,2004} = 6
    # (alpha dup 2000 counts each curated row; alpha 1700 out of window excluded)
    assert diag["n_curated_in_verified_countries"] == 7  # alpha:4 in-window rows + beta:3
    # matched a verdict: alpha 2000,2001,2002 (+dup 2000) = 4; beta 2000,2003 = 2 → 6
    assert diag["n_matched_a_verdict"] == 6
    assert diag["n_countries_without_verification"] == 1  # gamma
    assert "gamma" in diag["countries_without_verification"]
    assert abs(diag["match_rate_among_verified_countries"] - 6 / 7) < 1e-3  # code rounds to 4dp


def test_norm_title_recovers_encoding_drift():
    """Regression: the curated titles carry a corrupted/replacement char (U+FFFD)
    where verification carries the proper em-dash (U+2014). The normalized join key
    must collapse both to the same string so the verified-TRUE positive is NOT
    silently dropped (this drift was losing ~40-57% of events for ~10 countries;
    fixing it lifted the match rate 94.5% -> 97.7% and recovered +332 positives)."""
    assert (bvp._norm_title("Suez Crisis � France Intervenes")
            == bvp._norm_title("Suez Crisis — France Intervenes")
            == "suez crisis france intervenes")
    # casing / punctuation / whitespace drift also collapses
    assert bvp._norm_title("  Treaty of Rome: Signed!  ") == bvp._norm_title("treaty of rome  signed")


def test_tier_thresholds():
    assert bvp.tier(60) == "runnable"
    assert bvp.tier(59) == "thin"
    assert bvp.tier(8) == "thin"
    assert bvp.tier(7) == "skip"


def test_fixture_positives_are_skip_tier(dirs):
    """X has 2 positives, Y has 1 → both below THIN_MIN (8) → skip tier."""
    cur, ver = dirs
    vmap = bvp.load_verdict_map(ver)
    positives, _ = bvp.build_positives(cur, vmap)
    assert bvp.tier(len(positives["X"])) == "skip"  # 2 < 8


def test_write_positives_dry_run_writes_nothing(tmp_path):
    # hand-built dict with >=8 positives so the recipe is a thin (writable) tier
    positives = {"recipeA": {(f"c{i}", 2000) for i in range(10)}}
    out = tmp_path / "out"
    summary = bvp.write_positives(positives, out, dry_run=True)
    assert not out.exists()
    assert summary["recipeA"]["n_pos"] == 10 and summary["recipeA"]["tier"] == "thin"
    assert summary["recipeA"]["written"] is False


def test_write_positives_real_writes_csv(tmp_path):
    positives = {"recipeA": {("beta", 2001), ("alpha", 2000)} | {(f"c{i}", 2000) for i in range(8)}}
    out = tmp_path / "out"
    bvp.write_positives(positives, out, dry_run=False)
    csv_path = out / "recipeA" / "positives.csv"
    assert csv_path.exists()
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "country_id,event_year"
    # deterministic sorted order: alpha,2000 then beta,2001 then c0..c7
    assert lines[1] == "alpha,2000"
    assert lines[2] == "beta,2001"


def test_main_fail_loud_exit_code(dirs, tmp_path):
    """_main returns 2 when match rate < --min-match-rate (the build gate), and 0
    when the threshold is satisfiable. Fixture match rate is 6/7 ≈ 0.857."""
    cur, ver = dirs
    out = tmp_path / "out"
    base = ["--curated-dir", str(cur), "--verification-dir", str(ver),
            "--out-dir", str(out), "--dry-run"]
    assert bvp._main(base + ["--min-match-rate", "0.99"]) == 2   # 0.857 < 0.99 → fail loud
    assert bvp._main(base + ["--min-match-rate", "0.50"]) == 0   # 0.857 >= 0.50 → ok


def test_partial_verdict_counts_as_matched_not_true(dirs):
    """A PARTIAL verdict (beta-2003) is MATCHED (join health) but NOT a positive
    (only TRUE). match_rate measures join health, not approval rate."""
    cur, ver = dirs
    vmap = bvp.load_verdict_map(ver)
    positives, diag = bvp.build_positives(cur, vmap)
    assert ("beta", 2003) not in positives.get("X", set())  # PARTIAL excluded from positives
    assert diag["n_matched_a_verdict"] == 6                  # but counted as matched (incl. beta-2003)


def test_skip_tier_not_written(tmp_path):
    # a recipe with <8 positives must not get a positives.csv
    positives = {"thinrecipe": {("a", 2000), ("b", 2001)}}
    out = tmp_path / "out"
    summary = bvp.write_positives(positives, out, dry_run=False)
    assert summary["thinrecipe"]["tier"] == "skip"
    assert not (out / "thinrecipe").exists()
