"""Unit tests for compute_momentum.py — pure-function coverage.

No IO, no panels, no parquet: all tests operate on synthetic in-memory data.

Coverage:
  - fit_slope: exact slope on a hand-built linear series.
  - fit_slope: single-point returns 0.0 (degenerate case).
  - classify_direction: rising/flat/falling with epsilon boundaries.
  - compute_country_momentum: rising trajectory → positive slope + "rising".
  - compute_country_momentum: falling trajectory → negative slope + "falling".
  - compute_country_momentum: flat trajectory → slope near 0 + "flat".
  - compute_country_momentum: <3 years available → suppressed + INSUFFICIENT_HISTORY.
  - compute_country_momentum: n_years_available reported correctly.
  - compute_country_momentum: scores_by_year keys match the requested offsets.
  - MOMENTUM_EPS constant existence and value.
  - Artifact schema: m8_r5_note has RETROSPECTIVE / not a forecast framing.
  - CLI parser: accepts all documented flags + defaults.

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

import compute_momentum as cm  # noqa: E402
from compute_recipe_country_similarity import compute_country_recipe_similarity  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uniform_shap(inds: list[str]) -> dict[str, float]:
    w = 1.0 / len(inds)
    return {ind: w for ind in inds}


def _make_traj(val: float, window: int) -> np.ndarray:
    return np.full(window, val)


def _make_canonical(inds: list[str], window: int, val: float = 1.0) -> dict[str, np.ndarray]:
    return {ind: _make_traj(val, window) for ind in inds}


# ---------------------------------------------------------------------------
# Tests: fit_slope
# ---------------------------------------------------------------------------


def test_fit_slope_exact_linear():
    """Hand-built y = 0.5*x series: slope must be exactly 0.5."""
    years = [2018, 2019, 2020, 2021]
    scores = [0.0, 0.5, 1.0, 1.5]
    slope = cm.fit_slope(years, scores)
    assert abs(slope - 0.5) < 1e-9, f"Expected slope=0.5, got {slope}"


def test_fit_slope_negative():
    """Decreasing series → negative slope."""
    years = [2018, 2019, 2020, 2021]
    scores = [1.5, 1.0, 0.5, 0.0]
    slope = cm.fit_slope(years, scores)
    assert slope < 0, f"Expected negative slope, got {slope}"
    assert abs(slope - (-0.5)) < 1e-9


def test_fit_slope_flat():
    """Constant series → slope = 0.0."""
    years = [2018, 2019, 2020, 2021]
    scores = [50.0, 50.0, 50.0, 50.0]
    slope = cm.fit_slope(years, scores)
    assert abs(slope) < 1e-9, f"Flat series: expected slope=0, got {slope}"


def test_fit_slope_single_point_returns_zero():
    """A single point is degenerate: slope must be 0.0."""
    slope = cm.fit_slope([2021], [75.0])
    assert slope == 0.0, f"Single-point: expected 0.0, got {slope}"


def test_fit_slope_two_points():
    """Two points: slope = (y1-y0)/(x1-x0)."""
    years = [2020, 2021]
    scores = [60.0, 70.0]
    slope = cm.fit_slope(years, scores)
    assert abs(slope - 10.0) < 1e-9, f"Expected slope=10.0, got {slope}"


# ---------------------------------------------------------------------------
# Tests: classify_direction
# ---------------------------------------------------------------------------


def test_classify_direction_rising():
    """Slope > +eps → 'rising'."""
    direction = cm.classify_direction(slope=0.1, eps=cm.MOMENTUM_EPS)
    assert direction == "rising", f"Expected 'rising', got '{direction}'"


def test_classify_direction_falling():
    """Slope < -eps → 'falling'."""
    direction = cm.classify_direction(slope=-0.1, eps=cm.MOMENTUM_EPS)
    assert direction == "falling", f"Expected 'falling', got '{direction}'"


def test_classify_direction_flat_positive_edge():
    """Slope == +eps → 'flat' (boundary is flat)."""
    direction = cm.classify_direction(slope=cm.MOMENTUM_EPS, eps=cm.MOMENTUM_EPS)
    assert direction == "flat", f"Expected 'flat' at +eps boundary, got '{direction}'"


def test_classify_direction_flat_negative_edge():
    """Slope == -eps → 'flat' (boundary is flat)."""
    direction = cm.classify_direction(slope=-cm.MOMENTUM_EPS, eps=cm.MOMENTUM_EPS)
    assert direction == "flat", f"Expected 'flat' at -eps boundary, got '{direction}'"


def test_classify_direction_zero():
    """Slope = 0.0 → 'flat'."""
    direction = cm.classify_direction(0.0, eps=cm.MOMENTUM_EPS)
    assert direction == "flat"


# ---------------------------------------------------------------------------
# Tests: compute_country_momentum
# ---------------------------------------------------------------------------


def _make_rising_scores_fn(base: float = 30.0, step: float = 8.0):
    """Returns a callable that, given eval_year, returns score = base + step*(year-2018)."""
    def score_fn(eval_year: int) -> float | None:
        return base + step * (eval_year - 2018)
    return score_fn


def _make_falling_scores_fn(base: float = 80.0, step: float = 8.0):
    def score_fn(eval_year: int) -> float | None:
        return base - step * (eval_year - 2018)
    return score_fn


def test_compute_country_momentum_rising():
    """A trajectory with monotonically increasing scores yields direction='rising'."""
    # Provide a callable that maps eval_year → risk_score (rising)
    score_fn = _make_rising_scores_fn()
    result = cm.compute_country_momentum(
        target_year=2021,
        score_fn=score_fn,
        n_offsets=4,
    )
    assert result["direction"] == "rising", (
        f"Rising trajectory: expected 'rising', got '{result['direction']}'"
    )
    assert result["slope_per_year"] > 0, (
        f"Rising: slope must be positive, got {result['slope_per_year']}"
    )


def test_compute_country_momentum_carries_retrospective_label():
    """FOLLOWUP (review 2026-05-24): every per-country result must carry the
    observation_label marking it RETROSPECTIVE / NOT a forecast — the honesty
    contract that distinguishes momentum from the (suppressed) projection."""
    result = cm.compute_country_momentum(
        target_year=2021, score_fn=_make_rising_scores_fn(), n_offsets=4,
    )
    assert "observation_label" in result, "per-country result must include observation_label"
    label = result["observation_label"].upper()
    assert "RETROSPECTIVE" in label and "NOT A FORECAST" in label, (
        f"observation_label must mark this retrospective and not a forecast, got: {result['observation_label']!r}"
    )


def test_compute_country_momentum_falling():
    """Monotonically decreasing scores → direction='falling'."""
    score_fn = _make_falling_scores_fn()
    result = cm.compute_country_momentum(
        target_year=2021,
        score_fn=score_fn,
        n_offsets=4,
    )
    assert result["direction"] == "falling"
    assert result["slope_per_year"] < 0


def test_compute_country_momentum_flat():
    """Constant scores across all offsets → direction='flat', slope≈0."""
    score_fn = lambda _year: 50.0  # noqa: E731
    result = cm.compute_country_momentum(
        target_year=2021,
        score_fn=score_fn,
        n_offsets=4,
    )
    assert result["direction"] == "flat"
    assert abs(result["slope_per_year"]) < 1e-6


def test_compute_country_momentum_scores_by_year_keys():
    """scores_by_year must contain keys for all 4 offsets (2021, 2020, 2019, 2018)."""
    score_fn = lambda y: float(y - 2010)  # noqa: E731
    result = cm.compute_country_momentum(
        target_year=2021,
        score_fn=score_fn,
        n_offsets=4,
    )
    expected_years = {2021, 2020, 2019, 2018}
    assert set(result["scores_by_year"].keys()) == expected_years, (
        f"Expected years {expected_years}, got {set(result['scores_by_year'].keys())}"
    )


def test_compute_country_momentum_n_years_available():
    """n_years_available must count only non-None entries in scores_by_year."""
    call_count = [0]

    def score_fn_partial(eval_year: int) -> float | None:
        call_count[0] += 1
        if eval_year >= 2020:
            return 60.0
        return None  # Missing for 2018, 2019

    result = cm.compute_country_momentum(
        target_year=2021,
        score_fn=score_fn_partial,
        n_offsets=4,
    )
    assert result["n_years_available"] == 2, (
        f"Expected 2 available years (2020, 2021), got {result['n_years_available']}"
    )


def test_compute_country_momentum_insufficient_history_suppressed():
    """< 3 of 4 offset-years available → suppressed=True, flag=INSUFFICIENT_HISTORY."""
    def score_fn_sparse(eval_year: int) -> float | None:
        # Only 2 years available
        return 70.0 if eval_year >= 2020 else None

    result = cm.compute_country_momentum(
        target_year=2021,
        score_fn=score_fn_sparse,
        n_offsets=4,
    )
    assert result["suppressed"] is True, (
        "< 3 years available must set suppressed=True"
    )
    assert result["flag"] == "INSUFFICIENT_HISTORY", (
        f"Expected INSUFFICIENT_HISTORY, got {result['flag']}"
    )


def test_compute_country_momentum_sufficient_history_not_suppressed():
    """3 of 4 years available → suppressed=False."""
    def score_fn_three(eval_year: int) -> float | None:
        return 55.0 if eval_year >= 2019 else None  # 3 years: 2019, 2020, 2021

    result = cm.compute_country_momentum(
        target_year=2021,
        score_fn=score_fn_three,
        n_offsets=4,
    )
    assert result["suppressed"] is False, (
        "3 years available must NOT be suppressed"
    )
    assert result["flag"] is None


def test_compute_country_momentum_slope_sign_correct_on_handbuilt():
    """Hand-built series: scores 40→50→60→70 (years 2018→2019→2020→2021).
    Simple LS over 4 points → slope = +10/year. Direction = 'rising'."""
    scores_map = {2018: 40.0, 2019: 50.0, 2020: 60.0, 2021: 70.0}

    def score_fn(y: int) -> float | None:
        return scores_map.get(y)

    result = cm.compute_country_momentum(
        target_year=2021,
        score_fn=score_fn,
        n_offsets=4,
    )
    assert abs(result["slope_per_year"] - 10.0) < 1e-6, (
        f"Expected slope=10.0, got {result['slope_per_year']}"
    )
    assert result["direction"] == "rising"
    assert result["n_years_available"] == 4


# ---------------------------------------------------------------------------
# Tests: MOMENTUM_EPS constant
# ---------------------------------------------------------------------------


def test_momentum_eps_positive():
    """MOMENTUM_EPS must be a positive float (the boundary between flat and directional)."""
    assert isinstance(cm.MOMENTUM_EPS, float)
    assert cm.MOMENTUM_EPS > 0.0, f"MOMENTUM_EPS must be > 0, got {cm.MOMENTUM_EPS}"


def test_momentum_min_years_constant():
    """MIN_YEARS_AVAILABLE must be 3 per spec §3 honesty gate."""
    assert cm.MIN_YEARS_AVAILABLE == 3, (
        f"MIN_YEARS_AVAILABLE must be 3 per spec, got {cm.MIN_YEARS_AVAILABLE}"
    )


# ---------------------------------------------------------------------------
# Tests: m8_r5 artifact note
# ---------------------------------------------------------------------------


def test_m8_r5_note_retrospective():
    """M8_R5_NOTE must contain 'RETROSPECTIVE' per spec §3 honesty gate."""
    note = cm.M8_R5_NOTE
    assert "RETROSPECTIVE" in note, (
        "M8_R5_NOTE must contain 'RETROSPECTIVE' per spec §3"
    )


def test_m8_r5_note_not_forecast():
    """M8_R5_NOTE must explicitly say this is NOT a forecast."""
    note = cm.M8_R5_NOTE.lower()
    assert "not" in note and "forecast" in note, (
        "M8_R5_NOTE must contain 'not' and 'forecast' (explicit NOT-a-forecast framing)"
    )


# ---------------------------------------------------------------------------
# Tests: CLI parser
# ---------------------------------------------------------------------------


def test_cli_parser_required_flags(tmp_path):
    """CLI parser must reject a call with missing required flags."""
    parser = cm._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_cli_parser_all_flags(tmp_path):
    """CLI parser must accept all documented flags without error."""
    parser = cm._build_parser()
    args = parser.parse_args([
        "--recipe-id", "foreign_intervention",
        "--scores-file", str(tmp_path / "scores.json"),
        "--walk-summary", str(tmp_path / "walk.json"),
        "--panel-dir", str(tmp_path / "panels"),
        "--output-dir", str(tmp_path),
        "--evaluation-year", "2021",
        "--n-offsets", "4",
    ])
    assert args.recipe_id == "foreign_intervention"
    assert args.n_offsets == 4
    assert args.evaluation_year == 2021


def test_cli_parser_defaults(tmp_path):
    """Default n_offsets=4, evaluation_year=2021."""
    parser = cm._build_parser()
    args = parser.parse_args([
        "--recipe-id", "foreign_intervention",
        "--scores-file", str(tmp_path / "scores.json"),
        "--walk-summary", str(tmp_path / "walk.json"),
        "--output-dir", str(tmp_path),
    ])
    assert args.n_offsets == 4
    assert args.evaluation_year == 2021
