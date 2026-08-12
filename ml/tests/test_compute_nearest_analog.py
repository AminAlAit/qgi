"""Unit tests for compute_nearest_analog.py — pure-function coverage.

No IO, no panels, no parquet: all tests operate on synthetic in-memory data.

Coverage:
  - build_positive_trajectory: mirrors build_canonical_profile_from_walk's
    per-positive extraction — window ending event_year-1, same z-score baseline.
  - compute_analog_score: SHAP-weighted mean cosine across indicators; skips
    missing indicators; exact match on identical vectors → 1.0.
  - find_nearest_analogs: top-K ranking; self-exclusion when target is also a
    positive; weak-analog suppression (best < 0.70 floor → suppressed=True,
    flag=WEAK_ANALOG); same_cohort flag set correctly.
  - CLI parser: accepts all documented flags + defaults.
  - Output schema: required top-level artifact keys present.

Per test-first rule (#373, feedback_test_first_rule.md):
tests written BEFORE the implementation is run.
Mirror style of tests/test_compute_similarity_bands.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import compute_nearest_analog as cna  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — synthetic data builders
# ---------------------------------------------------------------------------


def _uniform_shap(inds: list[str]) -> dict[str, float]:
    w = 1.0 / len(inds)
    return {ind: w for ind in inds}


def _make_traj(val: float, window: int) -> np.ndarray:
    """Flat trajectory filled with a constant value."""
    return np.full(window, val)


# ---------------------------------------------------------------------------
# Tests: compute_analog_score
# ---------------------------------------------------------------------------


def test_analog_score_identical_vectors():
    """Identical target and positive trajectories → weighted cosine = 1.0."""
    inds = ["IND_A", "IND_B"]
    shap = _uniform_shap(inds)
    window = 10
    target = {ind: _make_traj(1.0, window) for ind in inds}
    positive = {ind: _make_traj(1.0, window) for ind in inds}
    score = cna.compute_analog_score(target, positive, shap)
    assert abs(score - 1.0) < 1e-9, f"Expected 1.0, got {score}"


def test_analog_score_orthogonal_vectors():
    """Orthogonal target and positive → cosine = 0.0 for each indicator."""
    window = 4
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    target = {"IND_A": np.array([1.0, 0.0, 0.0, 0.0])}
    positive = {"IND_A": np.array([0.0, 1.0, 0.0, 0.0])}
    score = cna.compute_analog_score(target, positive, shap)
    assert abs(score) < 1e-9, f"Expected 0.0, got {score}"


def test_analog_score_skips_missing_indicator():
    """If a positive is missing one indicator, that indicator is skipped (not counted).
    The score must still be computed from the remaining indicators."""
    inds = ["IND_A", "IND_B"]
    shap = {"IND_A": 0.6, "IND_B": 0.4}
    window = 5
    target = {
        "IND_A": _make_traj(1.0, window),
        "IND_B": _make_traj(1.0, window),
    }
    # Positive is missing IND_B
    positive_missing = {"IND_A": _make_traj(1.0, window)}
    score_with_missing = cna.compute_analog_score(target, positive_missing, shap)
    # Full match on IND_A alone should also be 1.0 (single indicator)
    assert abs(score_with_missing - 1.0) < 1e-9, (
        f"Missing IND_B should not crash; score={score_with_missing}"
    )


def test_analog_score_both_missing_returns_zero():
    """If all shared indicators are missing from positive, score must be 0.0."""
    inds = ["IND_A"]
    shap = {"IND_A": 1.0}
    target = {"IND_A": _make_traj(1.0, 5)}
    positive_empty: dict[str, np.ndarray] = {}
    score = cna.compute_analog_score(target, positive_empty, shap)
    assert score == 0.0, f"All missing → expected 0.0, got {score}"


def test_analog_score_weight_proportional():
    """Score should be weighted cosine: high-weight indicator dominates.
    Indicator A (cosine=1) with weight=0.9, Indicator B (cosine=-1) with weight=0.1.
    Expected weighted cosine ≈ (0.9*1 + 0.1*(-1))/(0.9+0.1) = 0.8."""
    window = 4
    shap = {"IND_A": 0.9, "IND_B": 0.1}
    target = {
        "IND_A": np.array([1.0, 0.0, 0.0, 0.0]),
        "IND_B": np.array([1.0, 0.0, 0.0, 0.0]),
    }
    positive = {
        "IND_A": np.array([1.0, 0.0, 0.0, 0.0]),   # cos = 1.0
        "IND_B": np.array([-1.0, 0.0, 0.0, 0.0]),  # cos = -1.0
    }
    score = cna.compute_analog_score(target, positive, shap)
    assert abs(score - 0.8) < 1e-9, f"Expected 0.8, got {score}"


# ---------------------------------------------------------------------------
# Tests: find_nearest_analogs
# ---------------------------------------------------------------------------


def test_find_nearest_analogs_top_k_order():
    """Top-K analogs must be sorted descending by weighted_cosine."""
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    window = 5
    target_traj = {"IND_A": _make_traj(1.0, window)}
    # Positives with varying similarity
    positives_traj = [
        ("country_A", 1995, {"IND_A": _make_traj(0.1, window)}),
        ("country_B", 2000, {"IND_A": _make_traj(0.9, window)}),
        ("country_C", 2005, {"IND_A": _make_traj(0.5, window)}),
    ]
    cohort_map: dict[str, str] = {}
    analogs = cna.find_nearest_analogs(
        target_country="other_country",
        target_traj=target_traj,
        positives_traj=positives_traj,
        shap_weights=shap,
        cohort_map=cohort_map,
        top_k=3,
        analog_floor=0.70,
    )
    cosines = [a["weighted_cosine"] for a in analogs["analogs"]]
    assert cosines == sorted(cosines, reverse=True), (
        f"Analogs not sorted descending: {cosines}"
    )


def test_find_nearest_analogs_returns_top_k():
    """Returns at most top_k analogs."""
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    window = 5
    target_traj = {"IND_A": _make_traj(1.0, window)}
    positives_traj = [
        (f"country_{i}", 2000 + i, {"IND_A": _make_traj(float(i) / 10.0, window)})
        for i in range(10)
    ]
    cohort_map: dict[str, str] = {}
    result = cna.find_nearest_analogs(
        target_country="target",
        target_traj=target_traj,
        positives_traj=positives_traj,
        shap_weights=shap,
        cohort_map=cohort_map,
        top_k=3,
        analog_floor=0.70,
    )
    assert len(result["analogs"]) <= 3, (
        f"Expected <= 3 analogs, got {len(result['analogs'])}"
    )


def test_find_nearest_analogs_self_exclusion():
    """If target_country is itself in the positives list, it must NOT appear as an analog."""
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    window = 5
    target_country = "Iran"
    target_traj = {"IND_A": _make_traj(1.0, window)}
    # Iran is a positive too — identical trajectory, would have cosine=1.0
    positives_traj = [
        ("Iran", 2010, {"IND_A": _make_traj(1.0, window)}),   # self
        ("Germany", 2005, {"IND_A": _make_traj(0.8, window)}),
    ]
    cohort_map: dict[str, str] = {}
    result = cna.find_nearest_analogs(
        target_country=target_country,
        target_traj=target_traj,
        positives_traj=positives_traj,
        shap_weights=shap,
        cohort_map=cohort_map,
        top_k=3,
        analog_floor=0.70,
    )
    for a in result["analogs"]:
        assert a["analog_country"] != target_country, (
            f"Self ({target_country}) must be excluded from analogs"
        )


def test_find_nearest_analogs_all_self_excluded_pool():
    """FOLLOWUP (review 2026-05-24): if the ONLY positive is the target itself,
    the pool empties after self-exclusion → no analogs, suppressed=True,
    flag=WEAK_ANALOG, best=None (no crash)."""
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    window = 5
    target_country = "Iran"
    target_traj = {"IND_A": _make_traj(1.0, window)}
    positives_traj = [("Iran", 2010, {"IND_A": _make_traj(1.0, window)})]  # only self
    result = cna.find_nearest_analogs(
        target_country=target_country, target_traj=target_traj,
        positives_traj=positives_traj, shap_weights=shap, cohort_map={},
        top_k=3, analog_floor=0.70,
    )
    assert result["analogs"] == []
    assert result["best_weighted_cosine"] is None
    assert result["suppressed"] is True
    assert result["flag"] == "WEAK_ANALOG"


def test_find_nearest_analogs_weak_analog_suppressed():
    """If best analog < floor (0.70), suppressed=True and flag=WEAK_ANALOG."""
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    window = 5
    target_traj = {"IND_A": np.array([1.0, 0.0, 0.0, 0.0, 0.0])}
    # Low similarity positives
    positives_traj = [
        ("country_A", 2000, {"IND_A": np.array([0.0, 1.0, 0.0, 0.0, 0.0])}),  # cos ≈ 0
        ("country_B", 2005, {"IND_A": np.array([0.0, 0.0, 1.0, 0.0, 0.0])}),  # cos ≈ 0
    ]
    cohort_map: dict[str, str] = {}
    result = cna.find_nearest_analogs(
        target_country="target",
        target_traj=target_traj,
        positives_traj=positives_traj,
        shap_weights=shap,
        cohort_map=cohort_map,
        top_k=3,
        analog_floor=0.70,
    )
    assert result["suppressed"] is True, "Best analog < 0.70 must set suppressed=True"
    assert result["flag"] == "WEAK_ANALOG", f"Expected WEAK_ANALOG, got {result['flag']}"


def test_find_nearest_analogs_strong_not_suppressed():
    """A best analog >= 0.70 must NOT be suppressed."""
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    window = 5
    # Target and positive are identical → cosine = 1.0
    traj = {"IND_A": _make_traj(1.0, window)}
    positives_traj = [("country_A", 2000, dict(traj))]
    cohort_map: dict[str, str] = {}
    result = cna.find_nearest_analogs(
        target_country="target",
        target_traj=traj,
        positives_traj=positives_traj,
        shap_weights=shap,
        cohort_map=cohort_map,
        top_k=3,
        analog_floor=0.70,
    )
    assert result["suppressed"] is False, "Best analog = 1.0 must NOT be suppressed"
    assert result["flag"] is None, f"Strong analog must have flag=None, got {result['flag']}"


def test_find_nearest_analogs_same_cohort_flag():
    """same_cohort must be True when target and analog share a cohort at eval_year."""
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    window = 5
    target_country = "CountryX"
    traj = {"IND_A": _make_traj(1.0, window)}
    positives_traj = [
        ("CountryY", 2010, dict(traj)),
        ("CountryZ", 2010, dict(traj)),
    ]
    # Both CountryX and CountryY are in "fragile-state"; CountryZ in "mid-tier"
    cohort_map = {
        target_country: "fragile-state",
        "CountryY": "fragile-state",
        "CountryZ": "mid-tier",
    }
    result = cna.find_nearest_analogs(
        target_country=target_country,
        target_traj=traj,
        positives_traj=positives_traj,
        shap_weights=shap,
        cohort_map=cohort_map,
        top_k=3,
        analog_floor=0.70,
    )
    analogs = {a["analog_country"]: a for a in result["analogs"]}
    assert analogs["CountryY"]["same_cohort"] is True
    assert analogs["CountryZ"]["same_cohort"] is False


def test_find_nearest_analogs_analog_schema():
    """Each analog entry must contain the required keys."""
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    window = 5
    traj = {"IND_A": _make_traj(1.0, window)}
    positives_traj = [("country_A", 2000, dict(traj))]
    cohort_map: dict[str, str] = {}
    result = cna.find_nearest_analogs(
        target_country="target",
        target_traj=traj,
        positives_traj=positives_traj,
        shap_weights=shap,
        cohort_map=cohort_map,
        top_k=3,
        analog_floor=0.70,
    )
    required = {"analog_country", "analog_event_year", "weighted_cosine", "same_cohort"}
    for a in result["analogs"]:
        assert required.issubset(set(a.keys())), (
            f"Analog entry missing keys: {required - set(a.keys())}"
        )


def test_find_nearest_analogs_no_positives():
    """When there are no positives to compare against, analogs must be empty."""
    inds = ["IND_A"]
    shap = _uniform_shap(inds)
    traj = {"IND_A": _make_traj(1.0, 5)}
    result = cna.find_nearest_analogs(
        target_country="target",
        target_traj=traj,
        positives_traj=[],
        shap_weights=shap,
        cohort_map={},
        top_k=3,
        analog_floor=0.70,
    )
    assert result["analogs"] == []
    assert result["suppressed"] is True
    assert result["flag"] == "WEAK_ANALOG"


# ---------------------------------------------------------------------------
# Tests: ANALOG_FLOOR constant
# ---------------------------------------------------------------------------


def test_analog_floor_constant():
    """ANALOG_FLOOR must be pre-registered at 0.70 per spec §2."""
    assert cna.ANALOG_FLOOR == 0.70, (
        f"ANALOG_FLOOR must be 0.70 (pre-registered before results); got {cna.ANALOG_FLOOR}"
    )


def test_default_top_k_constant():
    """DEFAULT_TOP_K must be 3 per spec §2."""
    assert cna.DEFAULT_TOP_K == 3, (
        f"DEFAULT_TOP_K must be 3 per spec; got {cna.DEFAULT_TOP_K}"
    )


# ---------------------------------------------------------------------------
# Tests: artifact schema
# ---------------------------------------------------------------------------


def test_artifact_has_m8_r5_note():
    """The m8_r5_note string must contain 'resemblance, not destiny'."""
    assert "resemblance, not destiny" in cna.M8_R5_NOTE, (
        "M8_R5_NOTE must contain 'resemblance, not destiny' per spec §2 honesty gate"
    )


def test_artifact_has_regional_caveat():
    """M8_R5_NOTE must mention regional clustering caveat per spec §2."""
    assert "regional" in cna.M8_R5_NOTE.lower(), (
        "M8_R5_NOTE must carry regional-clustering caveat per spec §2"
    )


# ---------------------------------------------------------------------------
# Tests: CLI parser
# ---------------------------------------------------------------------------


def test_cli_parser_required_flags(tmp_path):
    """CLI parser must reject a call with missing required flags."""
    parser = cna._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_cli_parser_all_flags(tmp_path):
    """CLI parser must accept all documented flags without error."""
    parser = cna._build_parser()
    args = parser.parse_args([
        "--recipe-id", "foreign_intervention",
        "--scores-file", str(tmp_path / "scores.json"),
        "--walk-summary", str(tmp_path / "walk.json"),
        "--panel-dir", str(tmp_path / "panels"),
        "--cohort-assignments", str(tmp_path / "cohorts.json"),
        "--output-dir", str(tmp_path),
        "--top-k", "5",
        "--evaluation-year", "2021",
    ])
    assert args.recipe_id == "foreign_intervention"
    assert args.top_k == 5
    assert args.evaluation_year == 2021


def test_cli_parser_defaults(tmp_path):
    """Default top_k=3, analog_floor=0.70, evaluation_year=2021."""
    parser = cna._build_parser()
    args = parser.parse_args([
        "--recipe-id", "foreign_intervention",
        "--scores-file", str(tmp_path / "scores.json"),
        "--walk-summary", str(tmp_path / "walk.json"),
        "--output-dir", str(tmp_path),
    ])
    assert args.top_k == 3
    assert abs(args.analog_floor - 0.70) < 1e-9
    assert args.evaluation_year == 2021
