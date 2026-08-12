"""Unit tests for run_i5_substrate_audit.py classification logic.

Covers the 5 QA-review fixes (Stage B mini-Majles agreed):
  1. frac_diff denominator bug (now uses separate countries_tested_at_diff counter)
  2. min_obs_required raised 8 -> 15
  3. I(2) branch guard (requires frac_level < 0.30 too, not just frac_diff < 0.30)
  4. dead --include-uncurated flag removed (no test needed; covered by import)
  5. unused traceback import removed (no test needed)

Plus synthetic-panel tests for I(0)/I(1)/I(2) classifications. No S3 / no
network — purely tests of classify_indicator_adf_fallback.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "run_i5_substrate_audit.py"
)
_spec = importlib.util.spec_from_file_location("audit_mod", _SCRIPT)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


# Reproducibility: deterministic seed for synthetic panels
RNG = np.random.default_rng(42)


def make_panel(country_series: dict[str, np.ndarray]) -> pd.DataFrame:
    """Build a wide panel: index=year, columns=country, values=indicator value."""
    n_years = max(len(v) for v in country_series.values())
    years = list(range(2000, 2000 + n_years))
    return pd.DataFrame({
        c: pd.Series(v, index=years[:len(v)])
        for c, v in country_series.items()
    })


# ---------------------------------------------------------------------------
# Synthetic data generators
# ---------------------------------------------------------------------------

def i0_white_noise(n: int = 30) -> np.ndarray:
    """Stationary white noise: mean 0, std 1. ADF should reject unit root."""
    return RNG.standard_normal(n)


def i1_random_walk(n: int = 30) -> np.ndarray:
    """Random walk: classic I(1). ADF should NOT reject at level, but should
    reject at first-difference."""
    return np.cumsum(RNG.standard_normal(n))


def i2_double_random_walk(n: int = 30) -> np.ndarray:
    """Double random walk: I(2). ADF should NOT reject at level OR first-diff,
    but should reject at second difference."""
    return np.cumsum(np.cumsum(RNG.standard_normal(n)))


# ---------------------------------------------------------------------------
# Classification tests
# ---------------------------------------------------------------------------

def test_classify_i0_panel_returns_i0():
    """All-stationary panel: classifier must return I(0)."""
    panel = make_panel({f"C{i:02d}": i0_white_noise() for i in range(30)})
    result = audit.classify_indicator_adf_fallback(panel)
    assert result["classification"] == "I(0)", (
        f"expected I(0); got {result['classification']}; frac_level="
        f"{result['frac_rejected_at_level']}, frac_diff={result['frac_rejected_at_diff']}"
    )
    assert result["frac_rejected_at_level"] >= 0.7
    assert result["test"] == "per_country_adf"


def test_classify_i1_panel_returns_i1():
    """All-random-walk panel: classifier must return I(1).
    (level rejection low; diff rejection high)"""
    panel = make_panel({f"C{i:02d}": i1_random_walk() for i in range(30)})
    result = audit.classify_indicator_adf_fallback(panel)
    assert result["classification"] == "I(1)", (
        f"expected I(1); got {result['classification']}; frac_level="
        f"{result['frac_rejected_at_level']}, frac_diff={result['frac_rejected_at_diff']}"
    )
    assert result["frac_rejected_at_level"] < 0.30
    assert result["frac_rejected_at_diff"] >= 0.70


def test_classify_i2_panel_returns_i2_or_higher():
    """Double-random-walk panel: I(2). frac_level low AND frac_diff low.

    Uses 50 countries × 50 obs to get cleaner separation: with shorter
    series ADF can occasionally reject by chance, putting frac_level
    right at the 0.30 threshold and pushing classification to ambiguous.
    Longer series + more countries makes the I(2) signal unambiguous."""
    panel = make_panel({f"C{i:02d}": i2_double_random_walk(50) for i in range(50)})
    result = audit.classify_indicator_adf_fallback(panel)
    assert result["classification"] == "I(2)_or_higher", (
        f"expected I(2)_or_higher; got {result['classification']}; frac_level="
        f"{result['frac_rejected_at_level']}, frac_diff={result['frac_rejected_at_diff']}"
    )
    assert result["frac_rejected_at_level"] < 0.30
    assert result["frac_rejected_at_diff"] < 0.30


# ---------------------------------------------------------------------------
# QA fix 1 — frac_diff denominator bug
# ---------------------------------------------------------------------------

def test_frac_diff_denominator_uses_separate_counter():
    """The bug: countries_tested counted ALL countries passing level filter,
    even ones that failed diff filter. Fix: separate countries_tested_at_diff.

    Construct a panel where some countries have only 16 obs (passes level
    filter at 15) but only 14 diff obs (fails diff filter at 15). Confirm
    those countries are NOT in the diff denominator."""
    panel_data = {}
    # 10 countries with full 30 obs (will be in both level and diff counters)
    for i in range(10):
        panel_data[f"FULL{i:02d}"] = i1_random_walk(30)
    # 5 countries with only 16 obs (level OK at 16>=15; diff has 15 obs, OK)
    # Actually 16-1=15 diff obs which still passes 15. Use 15 level obs -> 14 diff (fails)
    for i in range(5):
        # 15 level obs, 14 diff obs (fails 15-min)
        panel_data[f"SHORT{i:02d}"] = np.concatenate([
            i1_random_walk(15),
            np.full(15, np.nan),  # pad to 30 with NaN
        ])
    panel = make_panel(panel_data)

    result = audit.classify_indicator_adf_fallback(panel)

    # The fix: countries_tested_at_level == 15 (10 full + 5 short),
    # but countries_tested_at_diff == 10 (only the full ones)
    assert result["n_countries_tested_at_level"] == 15
    assert result["n_countries_tested_at_diff"] == 10, (
        f"diff denominator bug: expected 10 countries with >=15 diff obs, "
        f"got {result['n_countries_tested_at_diff']}"
    )


# ---------------------------------------------------------------------------
# QA fix 2 — min_obs threshold raised to 15
# ---------------------------------------------------------------------------

def test_min_obs_threshold_skips_countries_under_15():
    """Countries with fewer than 15 level obs must NOT be tested."""
    panel_data = {}
    # 5 countries with 14 obs each (below new threshold)
    for i in range(5):
        panel_data[f"SHORT{i:02d}"] = i1_random_walk(14)
    # 5 countries with 30 obs (above threshold)
    for i in range(5):
        panel_data[f"FULL{i:02d}"] = i1_random_walk(30)
    panel = make_panel(panel_data)

    result = audit.classify_indicator_adf_fallback(panel)
    assert result["n_countries_tested_at_level"] == 5  # only the 30-obs ones
    assert result["n_countries_tested_at_diff"] == 5


# ---------------------------------------------------------------------------
# QA fix 3 — I(2) branch guard
# ---------------------------------------------------------------------------

def test_i2_branch_guard_heterogeneous_panel_classified_ambiguous():
    """Pre-fix bug: any panel with frac_diff < 0.30 was classified I(2),
    even when frac_level was 30-69% (heterogeneous). Fix: I(2) branch
    requires frac_level < 0.30 too. Heterogeneous panels are ambiguous.

    Construct a panel with mixed I(0) and I(2) series so frac_level is
    moderate (~40%) and frac_diff is low (~25%). Pre-fix would classify
    I(2); post-fix classifies ambiguous."""
    panel_data = {}
    # 12 stationary series (will reject at level)
    for i in range(12):
        panel_data[f"STAT{i:02d}"] = i0_white_noise(30)
    # 18 double-random-walk series (will reject at neither level nor diff)
    for i in range(18):
        panel_data[f"I2_{i:02d}"] = i2_double_random_walk(30)
    panel = make_panel(panel_data)

    result = audit.classify_indicator_adf_fallback(panel)

    # frac_level should be ~12/30 = 0.40; frac_diff should be low
    # I(2) branch (post-fix) requires BOTH frac_level < 0.30 AND frac_diff < 0.30.
    # frac_level=0.40 violates the level guard; classification falls through to ambiguous.
    assert result["frac_rejected_at_level"] > 0.30, (
        f"test setup invalid: expected frac_level > 0.30 to trigger guard, "
        f"got {result['frac_rejected_at_level']}"
    )
    assert result["classification"] != "I(2)_or_higher", (
        f"I(2) guard failed: heterogeneous panel mis-classified I(2). "
        f"frac_level={result['frac_rejected_at_level']}, "
        f"frac_diff={result['frac_rejected_at_diff']}, "
        f"classification={result['classification']}"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_classify_empty_panel_returns_insufficient_data():
    panel = pd.DataFrame()  # no countries
    result = audit.classify_indicator_adf_fallback(panel)
    assert result["classification"] == "insufficient_data"
    assert result["n_countries_tested_at_level"] == 0
    assert result["n_countries_tested_at_diff"] == 0


def test_classify_all_short_panel_returns_insufficient_data():
    """All countries below min_obs => insufficient_data."""
    panel_data = {f"C{i:02d}": i1_random_walk(10) for i in range(5)}  # 10 < 15
    panel = make_panel(panel_data)
    result = audit.classify_indicator_adf_fallback(panel)
    assert result["classification"] == "insufficient_data"
    assert result["n_countries_tested_at_level"] == 0


def test_classify_constant_series_handled_gracefully():
    """All-constant series triggers ValueError in adfuller; should be caught
    and assigned p=1.0 (fail-to-reject). Panel of constants -> I(2)_or_higher
    (or similar non-stationary classification, never crash)."""
    panel_data = {f"C{i:02d}": np.full(30, 5.0) for i in range(10)}
    panel = make_panel(panel_data)
    result = audit.classify_indicator_adf_fallback(panel)
    # Should NOT crash; classification can be I(2) or insufficient (since constant series fail diff test silently)
    assert result["classification"] in (
        "I(2)_or_higher", "ambiguous", "insufficient_data"
    )


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------

def test_schema_has_required_fields():
    panel = make_panel({f"C{i:02d}": i1_random_walk() for i in range(15)})
    result = audit.classify_indicator_adf_fallback(panel)
    expected_fields = {
        "classification",
        "n_countries_tested_at_level",
        "n_countries_tested_at_diff",
        "n_countries_total",
        "frac_rejected_at_level",
        "frac_rejected_at_diff",
        "test",
    }
    assert set(result.keys()) == expected_fields, (
        f"schema mismatch: got {set(result.keys())}, expected {expected_fields}"
    )


def test_module_has_no_traceback_import():
    """QA fix 5: unused traceback import removed."""
    assert not hasattr(audit, "traceback"), (
        "traceback import should have been removed"
    )


def test_main_no_include_uncurated_flag():
    """QA fix 4: dead --include-uncurated flag removed.
    Verified by inspecting the script source for the flag string."""
    src = _SCRIPT.read_text(encoding="utf-8")
    assert "--include-uncurated" not in src, (
        "--include-uncurated flag should have been removed"
    )
    assert "include_uncurated" not in src, (
        "include_uncurated reference should have been removed"
    )
