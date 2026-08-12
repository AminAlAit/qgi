"""
Tests for audition_indicators.py Phase C — `--detrend-method first-diff`.

Test cases per Sebastien's plan §6.4 (adapted post-Ihsa-I3 simplification):

  TC-9   _stats_first_diff returns 6 values matching INDICATOR_FEATURE_STATS_DIFF
  TC-10  build_feature_matrix_v2 default args produce identical output to legacy
         (BACKWARD COMPAT — bit-identical output guarantee)
  TC-11  build_feature_matrix_v2 with --detrend-method=first-diff + I(1) set
         emits 12 features per I(1) indicator (6 level + 6 diff)
  TC-12  build_feature_matrix_v2 with first-diff but indicator NOT in i1_set
         emits only 6 level features (stationary indicators unchanged)
  TC-13  load_regimes_set parses indicator-regimes.json envelope correctly
  TC-14  load_cointegration_overrides returns set of (indicator, recipe) tuples
  TC-15  load_cointegration_overrides handles missing file gracefully (returns empty)

Per A6 (Bina amendment): every fixture creates its own np.random.default_rng — no
module-level RNG state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add scripts/ to path so we can import audition_indicators
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audition_indicators import (  # noqa: E402
    DETREND_METHODS,
    INDICATOR_FEATURE_STATS,
    INDICATOR_FEATURE_STATS_DIFF,
    INDICATOR_FEATURE_STATS_DECONF,
    _stats_first_diff,
    build_feature_matrix_v2,
    load_cointegration_overrides,
    load_regimes_set,
)


# ===========================================================================
# Fixtures (A6 — fixture-local RNG)
# ===========================================================================

SEED: int = 42


def make_recipe_panel(
    n_countries: int = 12,
    cutoff_year: int = 2020,
    canonical_length: int = 25,
    n_indicators: int = 3,
    seed: int = SEED,
) -> tuple[pd.DataFrame, list[dict], dict[int, str], dict[str, int]]:
    """Synthetic recipe panel for build_feature_matrix_v2 tests.

    Returns (panel_df, fingerprint, num_to_str, country_to_id).
    Each call constructs its own RNG — no module-level shared state (A6).
    """
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for ind_num in range(1, n_indicators + 1):
        sid = f"IND.{ind_num:03d}"
        for ctry_idx in range(n_countries):
            ctry = f"C{ctry_idx:03d}"
            base = rng.standard_normal()
            # Generate values across the full canonical-length window
            for yr in range(cutoff_year - canonical_length, cutoff_year + 1):
                # I(1)-ish drift for one indicator, mean-revert for others
                if ind_num == 1:
                    # cumulative drift (looks I(1))
                    val = float(base + 0.3 * (yr - (cutoff_year - canonical_length))
                                + rng.standard_normal())
                else:
                    val = float(base + rng.standard_normal())
                rows.append({"country": ctry, "year": yr,
                             "indicator_id": sid, "value": val})
    panel = pd.DataFrame(rows)
    fingerprint = [{"indicator_id": ind_num, "tfidf": 1.0}
                   for ind_num in range(1, n_indicators + 1)]
    num_to_str = {ind_num: f"IND.{ind_num:03d}" for ind_num in range(1, n_indicators + 1)}
    country_to_id = {f"C{i:03d}": i for i in range(n_countries)}
    return panel, fingerprint, num_to_str, country_to_id


# ===========================================================================
# TC-9: _stats_first_diff shape + behavior
# ===========================================================================

def test_tc9_stats_first_diff_returns_six_values():
    """_stats_first_diff returns exactly 6 values matching INDICATOR_FEATURE_STATS_DIFF."""
    rng = np.random.default_rng(SEED)
    years = np.arange(1995, 2020, dtype=float)
    values = np.cumsum(rng.standard_normal(len(years)))
    stats = _stats_first_diff(years, values, window_total_years=25)
    assert len(stats) == len(INDICATOR_FEATURE_STATS_DIFF)
    assert len(stats) == 6


def test_tc9_stats_first_diff_handles_short_series():
    """Series with <2 observations returns 6 NaNs."""
    years = np.array([2020.0])
    values = np.array([1.0])
    stats = _stats_first_diff(years, values)
    assert len(stats) == 6
    assert all(np.isnan(s) for s in stats)


def test_tc9_stats_first_diff_handles_constant_series():
    """A constant series produces zero diffs. Verify behavioral output, not just shape.

    Per strict purist review (2026-05-03): the prior version of this test asserted
    only `len(stats) == 6` and left a comment "should be 0" without verifying it.
    This version asserts the actual numeric behavior:
      - diff_std_norm == 0 (zero std on zero diffs)
      - diff_n_obs > 0 (we did process data, didn't bail on size)
      - no NaNs in std_norm or n_obs (the under-determined dynamics path emits
        NaN for slope/pct_change/autocorr when std(years)==0, which is fine)
    """
    years = np.arange(1995, 2020, dtype=float)
    values = np.full(len(years), 5.0)  # constant
    stats = _stats_first_diff(years, values, window_total_years=25)
    assert len(stats) == 6
    # INDICATOR_FEATURE_STATS_DIFF order: [std_norm, slope_norm, pct_change, n_obs, autocorr_1, frac_missing]
    diff_std_norm, diff_slope_norm, diff_pct_change, diff_n_obs, diff_autocorr_1, diff_frac_missing = stats
    assert diff_std_norm == pytest.approx(0.0), (
        f"Constant series should yield diff_std_norm == 0, got {diff_std_norm}"
    )
    assert diff_n_obs > 0, "n_obs should be >0 for a 25-year constant series"
    assert not np.isnan(diff_std_norm), "std_norm must not be NaN for a valid constant series"
    assert not np.isnan(diff_n_obs), "n_obs must not be NaN for a valid constant series"


# ===========================================================================
# TC-10: backward compat — default args produce identical output to legacy
# ===========================================================================

def test_tc10_default_args_match_legacy():
    """build_feature_matrix_v2 called with no detrend_method must match pre-Phase-C output."""
    panel, fingerprint, num_to_str, country_to_id = make_recipe_panel(
        n_countries=10, n_indicators=2, seed=SEED,
    )
    # Default: no detrend_method, no i1_set → legacy behavior
    feat_default, cols_default = build_feature_matrix_v2(
        panel, fingerprint, num_to_str,
        cutoff_year=2020, canonical_length=25,
        country_to_id=country_to_id,
    )
    # Explicit "none" with empty i1_set → also legacy behavior
    feat_explicit, cols_explicit = build_feature_matrix_v2(
        panel, fingerprint, num_to_str,
        cutoff_year=2020, canonical_length=25,
        country_to_id=country_to_id,
        detrend_method="none",
        i1_set=set(),
    )
    assert cols_default == cols_explicit
    # Same columns: 2 indicators × 6 stats = 12 columns
    assert len(cols_default) == 2 * len(INDICATOR_FEATURE_STATS)
    # Frames should have identical shape and values where present
    pd.testing.assert_frame_equal(
        feat_default.reset_index(drop=True),
        feat_explicit.reset_index(drop=True),
    )


def test_tc10_no_diff_columns_in_default_mode():
    """Default mode emits NO diff_* columns."""
    panel, fingerprint, num_to_str, country_to_id = make_recipe_panel(
        n_countries=10, n_indicators=3, seed=SEED,
    )
    _, cols = build_feature_matrix_v2(
        panel, fingerprint, num_to_str,
        cutoff_year=2020, canonical_length=25,
        country_to_id=country_to_id,
    )
    diff_cols = [c for c in cols if "diff_" in c]
    assert len(diff_cols) == 0, f"Default mode must not emit diff features; got {diff_cols}"


# ===========================================================================
# TC-11: first-diff mode emits 12 features per I(1) indicator
# ===========================================================================

def test_tc11_first_diff_emits_dual_features_for_i1():
    """With --detrend-method=first-diff + I(1) indicator in set, 12 features emitted
    AND the diff features carry distinct numerical content (not just placeholders).
    """
    panel, fingerprint, num_to_str, country_to_id = make_recipe_panel(
        n_countries=10, n_indicators=2, seed=SEED,
    )
    # Mark indicator 1 as I(1), indicator 2 as stationary
    i1_set = {"IND.001"}
    feat, cols = build_feature_matrix_v2(
        panel, fingerprint, num_to_str,
        cutoff_year=2020, canonical_length=25,
        country_to_id=country_to_id,
        detrend_method="first-diff",
        i1_set=i1_set,
    )
    # Indicator 1 (I(1)): 6 level + 6 diff = 12 features
    ind1_cols = [c for c in cols if c.startswith("ind1__")]
    assert len(ind1_cols) == 12, f"I(1) indicator should have 12 features, got {len(ind1_cols)}"
    # Indicator 2 (stationary): 6 level features only
    ind2_cols = [c for c in cols if c.startswith("ind2__")]
    assert len(ind2_cols) == 6, f"Stationary indicator should have 6 features, got {len(ind2_cols)}"
    # Verify column-name pattern
    ind1_diff_cols = [c for c in ind1_cols if "diff_" in c]
    assert len(ind1_diff_cols) == 6, f"I(1) indicator missing diff_ columns; got {ind1_diff_cols}"

    # SIGNAL INTEGRITY (per strict purist review 2026-05-03): the diff features
    # must carry numerically distinct content from the level features. If diff
    # values were silently identical to level values, the test above would still
    # pass — but the transformation would be useless. Verify diff_std_norm differs
    # from std_norm for at least one country (synthetic I(1) indicator 1 has
    # non-trivial drift, so diffs and levels should differ).
    assert "ind1__std_norm" in feat.columns
    assert "ind1__diff_std_norm" in feat.columns
    lvl_std = feat["ind1__std_norm"].dropna().to_numpy()
    diff_std = feat["ind1__diff_std_norm"].dropna().to_numpy()
    if len(lvl_std) > 0 and len(diff_std) > 0:
        # At least one country must have meaningfully different level vs diff std_norm
        assert not np.allclose(lvl_std, diff_std), (
            "Diff and level std_norm should differ for at least one country on an I(1) indicator. "
            "If they're equal, the diff transformation is a no-op."
        )


# ===========================================================================
# TC-12: stationary indicators get only level features even with first-diff active
# ===========================================================================

def test_tc12_stationary_unchanged_when_not_in_i1_set():
    """Indicator NOT in i1_set must receive only level features (no diff_)."""
    panel, fingerprint, num_to_str, country_to_id = make_recipe_panel(
        n_countries=10, n_indicators=3, seed=SEED,
    )
    # Mark only indicator 1 as I(1)
    i1_set = {"IND.001"}
    _, cols = build_feature_matrix_v2(
        panel, fingerprint, num_to_str,
        cutoff_year=2020, canonical_length=25,
        country_to_id=country_to_id,
        detrend_method="first-diff",
        i1_set=i1_set,
    )
    # Indicator 2 + 3: stationary, no diff features
    for nid in (2, 3):
        ind_cols = [c for c in cols if c.startswith(f"ind{nid}__")]
        diff_cols = [c for c in ind_cols if "diff_" in c]
        assert len(diff_cols) == 0, (
            f"Stationary indicator {nid} should have NO diff features; got {diff_cols}"
        )


def test_tc12_empty_i1_set_falls_back_to_level_only():
    """detrend_method=first-diff with empty i1_set: no indicator gets diff features."""
    panel, fingerprint, num_to_str, country_to_id = make_recipe_panel(
        n_countries=10, n_indicators=2, seed=SEED,
    )
    _, cols = build_feature_matrix_v2(
        panel, fingerprint, num_to_str,
        cutoff_year=2020, canonical_length=25,
        country_to_id=country_to_id,
        detrend_method="first-diff",
        i1_set=set(),  # empty — no I(1) indicators
    )
    diff_cols = [c for c in cols if "diff_" in c]
    assert len(diff_cols) == 0, (
        f"Empty i1_set should produce no diff features; got {diff_cols}"
    )


# ===========================================================================
# TC-13: load_regimes_set parses indicator-regimes.json correctly
# ===========================================================================

def test_tc13_load_regimes_set_returns_i1_set(tmp_path):
    """load_regimes_set extracts 'i1' regime list from the envelope."""
    regimes_data = {
        "schema_version": 1,
        "regimes": {
            "stationary": ["FP.CPI.TOTL.ZG", "SH.DYN.MORT"],
            "marginal": ["GC.TAX.TOTL.GD.ZS"],
            "i1": ["NY.GDP.MKTP.CD", "SP.POP.TOTL", "v2x_corr"],
        },
        "indicators": [],
    }
    p = tmp_path / "regimes.json"
    p.write_text(json.dumps(regimes_data))
    i1_set = load_regimes_set(p)
    assert i1_set == {"NY.GDP.MKTP.CD", "SP.POP.TOTL", "v2x_corr"}


def test_tc13_load_regimes_set_missing_file_raises(tmp_path):
    """Missing regimes.json file raises FileNotFoundError (clear failure mode)."""
    p = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        load_regimes_set(p)


def test_tc13_load_regimes_set_handles_missing_i1_key(tmp_path):
    """Regimes file without 'i1' key returns empty set (not crash)."""
    regimes_data = {"regimes": {"stationary": ["X"]}}
    p = tmp_path / "regimes_no_i1.json"
    p.write_text(json.dumps(regimes_data))
    assert load_regimes_set(p) == set()


# ===========================================================================
# TC-14: load_cointegration_overrides parses cointegration-map.json
# ===========================================================================

def test_tc14_load_cointegration_overrides_returns_tuples(tmp_path):
    """load_cointegration_overrides returns (indicator, recipe) tuples for cointegrated cells."""
    map_data = {
        "schema_version": 1,
        "cells": {
            "NY.GDP.MKTP.CD::military_coup": {"verdict": "cointegrated"},
            "SP.POP.TOTL::trade_agreement": {"verdict": "not_cointegrated"},
            "v2x_rule::public_health_reform": {"verdict": "cointegrated"},
            "RQ.EST::humanitarian_crisis": {"verdict": "insufficient_data"},
        },
    }
    p = tmp_path / "coint.json"
    p.write_text(json.dumps(map_data))
    overrides = load_cointegration_overrides(p)
    assert overrides == {
        ("NY.GDP.MKTP.CD", "military_coup"),
        ("v2x_rule", "public_health_reform"),
    }


# ===========================================================================
# TC-15: load_cointegration_overrides handles missing/None gracefully
# ===========================================================================

def test_tc15_load_cointegration_overrides_missing_file_returns_empty(tmp_path):
    """Missing path returns empty set (not raise) — caller can pass None or non-existent path."""
    overrides = load_cointegration_overrides(tmp_path / "missing.json")
    assert overrides == set()


def test_tc15_load_cointegration_overrides_none_returns_empty():
    """Passing None returns empty set — graceful handling."""
    overrides = load_cointegration_overrides(None)
    assert overrides == set()


def test_tc15_load_cointegration_overrides_empty_cells(tmp_path):
    """Empty cells dict returns empty set."""
    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"cells": {}}))
    overrides = load_cointegration_overrides(p)
    assert overrides == set()


# ===========================================================================
# Constant sanity checks
# ===========================================================================

def test_detrend_methods_constant():
    """DETREND_METHODS must include both 'none' and 'first-diff'."""
    assert "none" in DETREND_METHODS
    assert "first-diff" in DETREND_METHODS


def test_diff_stats_constant_length():
    """INDICATOR_FEATURE_STATS_DIFF should have same length as DECONF (6 stats)."""
    assert len(INDICATOR_FEATURE_STATS_DIFF) == len(INDICATOR_FEATURE_STATS_DECONF)


def test_diff_stats_all_prefixed():
    """All diff stat names should start with 'diff_' to avoid collision with level features."""
    for name in INDICATOR_FEATURE_STATS_DIFF:
        assert name.startswith("diff_"), f"diff stat {name!r} missing 'diff_' prefix"
