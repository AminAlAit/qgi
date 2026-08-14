"""Tests for the indicator-enrichment challenger gate (stage 3).

Pure-logic tests (cutoff derivation, crack classification, positives loading)
always run. The end-to-end LR-LOCO test runs only if scikit-learn is installed.
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

_HAS_SKLEARN = importlib.util.find_spec("sklearn") is not None

# challenger_gate lives in scripts/enrichment/; add scripts/enrichment to the path.
ENRICH_DIR = Path(__file__).resolve().parents[1] / "scripts" / "enrichment"
if str(ENRICH_DIR) not in sys.path:
    sys.path.insert(0, str(ENRICH_DIR))

import challenger_gate as cg  # noqa: E402


# ---- compute_cutoff ---------------------------------------------------------

def test_compute_cutoff_full_pool_returns_40th_best():
    # 45 indicators, AUC strictly descending; ranked is already sorted desc.
    ranked = [f"ind{i:02d}" for i in range(45)]
    scores = {f"ind{i:02d}": {"univariate_loco_auc": 0.90 - i * 0.01} for i in range(45)}
    cutoff, cutoff_id, n_valid = cg.compute_cutoff(ranked, scores, top_n=40)
    assert n_valid == 45
    assert cutoff_id == "ind39"
    assert cutoff == pytest.approx(0.90 - 39 * 0.01)  # 0.51


def test_compute_cutoff_ignores_nan_and_coverage_failed():
    # 40 finite + 5 nan -> exactly 40 valid -> cutoff is the 40th finite.
    ranked = [f"ind{i:02d}" for i in range(40)] + [f"bad{i}" for i in range(5)]
    scores = {f"ind{i:02d}": {"univariate_loco_auc": 0.90 - i * 0.01} for i in range(40)}
    for i in range(5):
        scores[f"bad{i}"] = {"univariate_loco_auc": float("nan"), "coverage_fail": True}
    cutoff, cutoff_id, n_valid = cg.compute_cutoff(ranked, scores, top_n=40)
    assert n_valid == 40
    assert cutoff_id == "ind39"
    assert math.isfinite(cutoff)


def test_compute_cutoff_exactly_40_indicators():
    # Boundary: n_valid == top_n -> cutoff is the 40th (last) indicator.
    ranked = [f"ind{i:02d}" for i in range(40)]
    scores = {f"ind{i:02d}": {"univariate_loco_auc": 0.90 - i * 0.01} for i in range(40)}
    cutoff, cutoff_id, n_valid = cg.compute_cutoff(ranked, scores, top_n=40)
    assert n_valid == 40
    assert cutoff_id == "ind39"
    assert cutoff == pytest.approx(0.90 - 39 * 0.01)


def test_compute_cutoff_thin_pool_is_neg_inf():
    # Fewer than top_n valid indicators -> any coverage-passing candidate enters.
    ranked = [f"ind{i}" for i in range(10)]
    scores = {f"ind{i}": {"univariate_loco_auc": 0.7} for i in range(10)}
    cutoff, cutoff_id, n_valid = cg.compute_cutoff(ranked, scores, top_n=40)
    assert cutoff == float("-inf")
    assert cutoff_id is None
    assert n_valid == 10


# ---- classify_crack ---------------------------------------------------------

def test_classify_crack_above_cutoff():
    assert cg.classify_crack(0.80, 0.70, coverage_fail=False) is True


def test_classify_crack_below_or_equal_cutoff():
    assert cg.classify_crack(0.60, 0.70, coverage_fail=False) is False
    assert cg.classify_crack(0.70, 0.70, coverage_fail=False) is False  # strict >


def test_classify_crack_coverage_fail_never_cracks():
    assert cg.classify_crack(0.99, 0.70, coverage_fail=True) is False


def test_classify_crack_nan_never_cracks():
    assert cg.classify_crack(float("nan"), 0.70, coverage_fail=False) is False


def test_classify_crack_thin_pool_any_finite_cracks():
    assert cg.classify_crack(0.55, float("-inf"), coverage_fail=False) is True


# ---- load_positives ---------------------------------------------------------

def test_load_positives_normalizes_country_and_sets_label(tmp_path):
    rdir = tmp_path / "some_recipe"
    rdir.mkdir()
    (rdir / "positives.csv").write_text(
        "country_id,event_year\n"
        "afghanistan,1979\n"
        "guinea_bissau,1998\n"
        "costa_rica,2002\n",
        encoding="utf-8",
    )
    df = cg.load_positives("some_recipe", tmp_path)
    assert list(df.columns) == ["country", "year", "label"]
    assert (df["label"] == 1).all()
    countries = set(df["country"])
    assert "Afghanistan" in countries
    assert "Guinea-Bissau" in countries          # COUNTRY_NAME_OVERRIDES applied
    assert "Costa Rica" in countries
    assert df["year"].dtype.kind in ("i", "u")    # integer years


# ---- forecast_cost ----------------------------------------------------------

def test_forecast_cost_uses_anchors_and_median():
    fc = cg.forecast_cost(["elections_and_voting", "some_unknown_recipe"])
    assert fc["n_flagged_recipes"] == 2
    # 21.8 (anchor) + 4.0 (median) = 25.8
    assert fc["total_walk_hours_estimate"] == pytest.approx(25.8, abs=0.1)
    assert fc["per_recipe_hours"]["some_unknown_recipe"] == cg.MEDIAN_WALK_H


# ---- end-to-end LR-LOCO (needs scikit-learn) --------------------------------

def _synthetic_panel(countries, years, value_fn):
    rows = [{"country": c, "year": y, "value": float(value_fn(c, y))}
            for c in countries for y in years]
    return pd.DataFrame(rows)


@pytest.mark.skipif(not _HAS_SKLEARN, reason="scikit-learn required for LR-LOCO")
def test_evaluate_recipe_separates_signal_from_noise():
    countries = [f"C{i:02d}" for i in range(15)]
    years = list(range(1980, 2021))

    def cidx(c):
        return int(c[1:])

    # 3 distinct event years per country in 1997-2018 -> 45 positives (>= MIN_EFFECTIVE_NPOS=30).
    events = {c: sorted({1997 + cidx(c) % 5, 2004 + cidx(c) % 6, 2012 + cidx(c) % 5})
              for c in countries}
    pos_rows = [{"country": c, "year": y, "label": 1} for c, ys in events.items() for y in ys]
    positives = pd.DataFrame(pos_rows)

    def is_pre_event(c, y):
        return any(1 <= (ye - y) <= 10 for ye in events[c])

    # Deterministic, PYTHONHASHSEED-independent pseudo-noise in [0, 1).
    def jitter(c, y, shift=0):
        return ((cidx(c) * 97 + (y - 1980 + shift) * 31) % 1000) / 1000.0

    # "good": elevated in the 10y window before an event (strong, generalizable signal).
    good = _synthetic_panel(countries, years, lambda c, y: 1.0 if is_pre_event(c, y) else 0.0)
    # two uninformative indicators with no event relationship.
    noise1 = _synthetic_panel(countries, years, lambda c, y: jitter(c, y))
    noise2 = _synthetic_panel(countries, years, lambda c, y: jitter(c, y, shift=7))

    panels = {"good": good, "noise1": noise1, "noise2": noise2}

    result = cg.evaluate_recipe(
        "test_recipe",
        candidate_ids=["good", "noise2"],
        current_pool_ids=["noise1"],
        panels=panels,
        positives=positives,
        seed=0,
    )

    assert result["recipe_id"] == "test_recipe"
    assert result["n_pos"] == len(positives)
    by_id = {c["candidate_id"]: c for c in result["per_candidate"]}
    assert set(by_id) == {"good", "noise2"}
    # The pre-event signal must score a finite AUC well above the noise indicator.
    assert by_id["good"]["candidate_auc"] is not None
    assert by_id["noise2"]["candidate_auc"] is not None
    assert by_id["good"]["candidate_auc"] > by_id["noise2"]["candidate_auc"]
    # Thin current pool (1 indicator < 40) -> cutoff is -inf -> the signal cracks.
    assert by_id["good"]["cracks_top40"] is True
    assert result["flagged"] is True


def test_run_gate_handles_missing_positives(tmp_path):
    # A recipe whose positives.csv is absent must surface as an error row, not crash,
    # and must not appear in flagged/unflagged. (No sklearn needed: the recipe errors
    # out at load_positives before any screen runs.)
    pdir = tmp_path / "panels"
    for ind in ("pool_ind", "cand_ind"):
        d = pdir / ind
        d.mkdir(parents=True)
        pd.DataFrame({"country": ["C00", "C00"], "year": [2000, 2001], "value": [1.0, 2.0]}).to_parquet(
            d / f"{ind}.parquet")
    shape = tmp_path / "shapes"
    shape.mkdir()  # empty -> positives.csv absent for every recipe
    manifest = cg.run_gate(
        panel_dir=pdir,
        candidate_ids=["cand_ind"],
        recipes=[{"recipe_id": "nonexistent", "status": "walked_no_graduation"}],
        shape_dir=shape,
    )
    rec = manifest["per_recipe"][0]
    assert rec["recipe_id"] == "nonexistent"
    assert "error" in rec
    assert "nonexistent" not in manifest["flagged_recipes"]
    assert "nonexistent" not in manifest["unflagged_recipes"]
    # All recipes errored -> candidate never screened: not_evaluated, NOT inert.
    assert manifest["not_evaluated_candidates"] == ["cand_ind"]
    assert manifest["inert_candidates"] == []


def test_run_gate_coverage_failed_everywhere(tmp_path):
    # A candidate too sparse to clear the coverage gate on the only recipe lands in
    # coverage_failed_everywhere (a data problem), NOT inert. No sklearn needed: the
    # candidate coverage-fails before any LR, and the pool is empty.
    pdir = tmp_path / "panels"
    d = pdir / "cand_sparse"
    d.mkdir(parents=True)
    # covers only 3 countries -> n_countries_survive (3) < MIN_SURVIVE_COUNTRIES (10)
    rows = [{"country": c, "year": y, "value": float(y)}
            for c in ("C00", "C01", "C02") for y in range(2000, 2021)]
    pd.DataFrame(rows).to_parquet(d / "cand_sparse.parquet")
    shape = tmp_path / "shapes" / "r1"
    shape.mkdir(parents=True)
    pos = [f"c{i % 12:02d},{2010 + (i % 8)}" for i in range(40)]   # 40 positives over 12 countries
    (shape / "positives.csv").write_text("country_id,event_year\n" + "\n".join(pos) + "\n", encoding="utf-8")
    manifest = cg.run_gate(
        panel_dir=pdir,
        candidate_ids=["cand_sparse"],
        recipes=[{"recipe_id": "r1", "status": "walked_no_graduation"}],
        shape_dir=tmp_path / "shapes",
    )
    assert manifest["coverage_failed_everywhere"] == ["cand_sparse"]
    assert manifest["inert_candidates"] == []
    assert manifest["active_candidates"] == []
    assert manifest["not_evaluated_candidates"] == []
