"""Unit tests for the truncation-leak bugfix SECONDARY facets (Majles 2026-05-25):

  facet 1 — time-matched negatives (temporal confound)   -> build_samples / temporal_confound_auc
  facet 2 — floor cap 0.90 (unreachable >1.0 floor bug)  -> compute_naive_baselines.compute_floor
  facet 3 — chance-baseline gate (MR-14-A2)              -> classify_verdict
  facet 4 — era-stratified LOCO (diagnostic)             -> era_stratified_loco

Synthetic, in-memory only. No panels, no AWS, deterministic seeds.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402
import compute_naive_baselines as nb  # noqa: E402


# --- facet 1: time-matched negatives -----------------------------------------

def _positives(years):
    pos = pd.DataFrame({"country": [f"C{i:02d}" for i in range(len(years))], "year": years})
    pos["label"] = 1
    return pos


def test_time_matched_negatives_share_positive_year_support():
    """Time-matched negatives draw years ONLY from the positives' year set, so the
    two classes share the same calendar-time support (no era separation)."""
    years = list(range(1965, 1990))  # positives clustered OLD
    pos = _positives(years)
    s = drv.build_samples(pos, negatives_per_positive=3, seed=0, time_matched=True)
    neg_years = set(s.loc[s["label"] == 0, "year"].tolist())
    assert neg_years.issubset(set(years)), "time-matched neg years must come from positive years"


def test_time_matched_neutralises_temporal_confound():
    """With positives clustered old, LEGACY uniform-year negatives let YEAR alone
    separate the classes (confound AUC far from 0.5); time-matched negatives pull it
    back toward chance."""
    pos = _positives(list(range(1965, 1990)))  # all pre-1990
    legacy = drv.build_samples(pos, negatives_per_positive=5, seed=1, time_matched=False)
    matched = drv.build_samples(pos, negatives_per_positive=5, seed=1, time_matched=True)
    auc_legacy = drv.temporal_confound_auc(legacy)
    auc_matched = drv.temporal_confound_auc(matched)
    # legacy: negatives skew recent (1980-2022) vs old positives -> year strongly separates
    assert abs(auc_legacy - 0.5) > 0.30
    # matched: same year support -> year is near-useless
    assert abs(auc_matched - 0.5) < 0.15
    assert abs(auc_matched - 0.5) < abs(auc_legacy - 0.5)


def test_time_matched_is_default():
    pos = _positives(list(range(1970, 1985)))
    default = drv.build_samples(pos, negatives_per_positive=3, seed=2)
    explicit = drv.build_samples(pos, negatives_per_positive=3, seed=2, time_matched=True)
    assert default.equals(explicit)


# --- facet 2: floor cap 0.90 -------------------------------------------------

def test_floor_cap_blocks_unreachable_floor():
    """A near-perfect naive (0.98) would push the relative floor to 1.01 (impossible).
    The cap pins it at 0.90 and records the basis."""
    _, floor, basis = nb.compute_floor(naive_auc=0.98, ci_hi=0.99, n_pos=500)
    assert floor == nb.FLOOR_CAP == 0.90
    assert basis == "capped_0.90"


def test_floor_absolute_backstop():
    """A weak naive falls back to the 0.70 absolute floor."""
    _, floor, basis = nb.compute_floor(naive_auc=0.55, ci_hi=0.60, n_pos=500)
    assert floor == nb.ABS_FLOOR == 0.70
    assert basis == "absolute_0.70"


def test_floor_relative_midband():
    """A mid-band naive yields naive+delta, uncapped, above the absolute floor."""
    _, floor, basis = nb.compute_floor(naive_auc=0.80, ci_hi=0.83, n_pos=500)
    assert floor == pytest.approx(0.83)  # 0.80 + 0.03
    assert basis == "relative"


def test_floor_thin_recipe_uses_upper_ci():
    """Thin recipes (N_pos < cut) anchor to the upper-CI, not the point estimate."""
    basis_val, floor, _ = nb.compute_floor(naive_auc=0.72, ci_hi=0.85, n_pos=10)
    assert basis_val == 0.85  # upper-CI used as the basis
    assert floor == pytest.approx(0.88)  # 0.85 + 0.03


# --- facet 3: chance-baseline gate (classify_verdict) ------------------------

def test_chance_fail_overrides_otherwise_passing_walk():
    """Even with all three LOCK gates green, a chance-level CI -> CHANCE_FAIL."""
    v = drv.classify_verdict(coverage_pass=True, chance_pass=False,
                             global_pass=True, cohort_loco_pass=True, cohort_ece_pass=True)
    assert v == "CHANCE_FAIL"


def test_coverage_fail_takes_priority_over_chance():
    v = drv.classify_verdict(coverage_pass=False, chance_pass=False,
                             global_pass=True, cohort_loco_pass=True, cohort_ece_pass=True)
    assert v == "COVERAGE_FAIL"


def test_lock_requires_all_gates_including_chance():
    assert drv.classify_verdict(True, True, True, True, True) == "LOCK"
    assert drv.classify_verdict(True, True, True, True, False) == "MARGINAL_PENDING_BETA_CALIBRATION"
    assert drv.classify_verdict(True, True, False, True, True) == "HARD_FAIL"


def test_chance_floor_is_one_half():
    assert drv.CHANCE_FLOOR == 0.50


def test_borderline_only_meaningful_on_lock(monkeypatch):
    """PVS-2: the `borderline_lock` annotation (CI lower < floor) is defined ONLY for a
    LOCK verdict. On a COVERAGE_FAIL / CHANCE_FAIL verdict it must be False even if the
    CI lower bound happens to sit below the LOCK floor — replicate the driver's guard
    `borderline = (ci95_lo < floor) if verdict == 'LOCK' else False`."""
    floor = 0.80
    ci_lo = 0.40  # below floor AND below chance
    def borderline_for(verdict):
        return bool(ci_lo < floor) if verdict == "LOCK" else False
    assert borderline_for("LOCK") is True
    assert borderline_for(drv.classify_verdict(True, False, True, True, True)) is False  # CHANCE_FAIL
    assert borderline_for(drv.classify_verdict(False, False, True, True, True)) is False  # COVERAGE_FAIL
    assert borderline_for("HARD_FAIL") is False


# --- facet 4: era-stratified LOCO -------------------------------------------

def test_era_stratified_reports_pre_post_and_decades():
    rng = np.random.default_rng(0)
    years = np.array([1980] * 50 + [2010] * 50)
    labels = np.array([0, 1] * 50)
    # perfect separation post-2000, pure noise pre-2000
    probs = np.where(years >= 2000, labels.astype(float), rng.random(len(years)))
    era = drv.era_stratified_loco(probs, labels, years, boundary=2000, min_n=10)
    assert era["post_boundary"]["auc"] == 1.0
    assert era["post_boundary"]["n"] == 50
    assert era["pre_boundary"]["auc"] is not None
    assert era["pre_post_spread"] is not None and era["pre_post_spread"] > 0.3
    assert "1980s" in era["by_decade"] and "2010s" in era["by_decade"]


def test_era_cell_below_min_n_reports_none_auc():
    years = np.array([1995] * 5 + [2015] * 40)
    labels = np.array([0, 1] * 2 + [0] + ([0, 1] * 20))
    probs = labels.astype(float)
    era = drv.era_stratified_loco(probs, labels, years, boundary=2000, min_n=20)
    assert era["pre_boundary"]["auc"] is None  # only 5 rows < min_n
    assert era["pre_boundary"]["n"] == 5
    assert era["pre_post_spread"] is None  # can't spread with one missing cell
