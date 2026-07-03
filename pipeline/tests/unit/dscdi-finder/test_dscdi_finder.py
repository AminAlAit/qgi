"""Unit tests for dscdi_finder.py — Phase 5 v0.0b Stage C primary module.

Coverage:
- Disposition resolution (Class A/B/C, outlier overrides, transform mapping)
- Per-country transformations (pass_through, first_diff, log_diff)
- Common-factor demeaning (Priya's spec)
- DSCDI pass orchestration (two-pass for Class A, single-pass for B/C)
- Pairwise diagnostic (Stage C exit gate)
- Audit JSON loader
- Diagnostic report builder

All tests use synthetic data — no S3, no network, no production dependencies.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SCRIPT = Path(__file__).resolve().parent.parent.parent.parent / "batch" / "dscdi-finder" / "src" / "dscdi_finder.py"
_spec = importlib.util.spec_from_file_location("dscdi_finder", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
# Register before exec — required for Python 3.14 dataclass introspection
# (the @dataclass decorator looks up cls.__module__ in sys.modules).
sys.modules["dscdi_finder"] = mod
_spec.loader.exec_module(mod)

RNG = np.random.default_rng(42)


# ---------------------------------------------------------------------------
# Disposition resolution
# ---------------------------------------------------------------------------


def test_resolve_disposition_class_a_severe_csd_i1():
    """v2x_libdem is in CLASS_A_SEVERE_CSD; I(1) → first_diff."""
    d = mod.resolve_disposition("v2x_libdem", "I(1)")
    assert d.indicator_class == "A"
    assert d.transform == "first_diff"


def test_resolve_disposition_class_b_wgi_i1():
    """RL.EST is WGI (Class B); I(1) → first_diff."""
    d = mod.resolve_disposition("RL.EST", "I(1)")
    assert d.indicator_class == "B"
    assert d.transform == "first_diff"


def test_resolve_disposition_class_c_default():
    """Random uncurated indicator → Class C; I(1) → first_diff."""
    d = mod.resolve_disposition("AG.LND.AGRI.ZS", "I(1)")
    assert d.indicator_class == "C"
    assert d.transform == "first_diff"


def test_resolve_disposition_outlier_growth_rate():
    """NY.GDP.MKTP.KD.ZG (I(0)) → pass_through, Class A documentation."""
    d = mod.resolve_disposition("NY.GDP.MKTP.KD.ZG", "I(0)")
    assert d.indicator_class == "A"  # documentation marker
    assert d.transform == "pass_through"


def test_resolve_disposition_outlier_population():
    """SP.POP.TOTL (I(2)) → log_diff, Class A. Founder direction."""
    d = mod.resolve_disposition("SP.POP.TOTL", "I(2)_or_higher")
    assert d.indicator_class == "A"
    assert d.transform == "log_diff"


def test_resolve_disposition_ambiguous_to_first_diff():
    """Ambiguous → first_diff per Protocol 1 default."""
    d = mod.resolve_disposition("FA-01", "ambiguous")
    assert d.transform == "first_diff"


def test_resolve_disposition_i0_pass_through():
    """I(0) classification → pass_through (no transformation needed)."""
    d = mod.resolve_disposition("v2x_libdem", "I(0)")
    assert d.transform == "pass_through"


def test_resolve_disposition_i2_outside_outlier_raises():
    """Any I(2)_or_higher OUTSIDE OUTLIER_LOG_DIFFERENCE must raise.
    Per Protocol 2: requires Tariq consultation, not auto-double-diff."""
    with pytest.raises(ValueError, match="Tariq consultation"):
        mod.resolve_disposition("AG.LND.AGRI.ZS", "I(2)_or_higher")


def test_resolve_disposition_unknown_classification_raises():
    with pytest.raises(ValueError, match="unknown classification"):
        mod.resolve_disposition("v2x_libdem", "I(3)")


def test_class_b_wgi_excludes_cc_est():
    """CC.EST is in CLASS_A_SEVERE_CSD (Class A override); not in CLASS_B_WGI.

    This is a critical correctness test per the Stage C input spec:
    'CC.EST is also a WGI indicator but has elevated CD; Class A overrides
    Class B for this specific case.'"""
    assert "CC.EST" in mod.CLASS_A_SEVERE_CSD
    assert "CC.EST" not in mod.CLASS_B_WGI
    d = mod.resolve_disposition("CC.EST", "I(1)")
    assert d.indicator_class == "A"  # override applied


# ---------------------------------------------------------------------------
# transform_panel
# ---------------------------------------------------------------------------


def _wide_panel(n_years: int = 30, n_countries: int = 10) -> pd.DataFrame:
    """Random-walk panel for testing transformations."""
    data = {}
    for i in range(n_countries):
        data[f"C{i:02d}"] = np.cumsum(RNG.standard_normal(n_years))
    return pd.DataFrame(data, index=range(2000, 2000 + n_years))


def test_transform_pass_through_returns_copy():
    panel = _wide_panel()
    out = mod.transform_panel(panel, "pass_through")
    pd.testing.assert_frame_equal(out, panel)
    assert out is not panel  # must be a copy


def test_transform_first_diff_produces_nan_at_t0():
    panel = _wide_panel(n_years=30, n_countries=5)
    out = mod.transform_panel(panel, "first_diff")
    # First row is NaN (no prior observation to diff against)
    assert out.iloc[0].isna().all()
    # Subsequent rows = panel[t] - panel[t-1]
    expected_t1 = panel.iloc[1] - panel.iloc[0]
    pd.testing.assert_series_equal(out.iloc[1], expected_t1, check_names=False)


def test_transform_log_diff_produces_growth_rate():
    """log-diff on [100, 110, 121, ...] → log(1.10), log(1.10), ...
    For 10% YoY growth, log_diff ≈ 0.0953 each year."""
    growth = np.array([100.0 * (1.10**i) for i in range(20)])
    panel = pd.DataFrame({"C00": growth}, index=range(2000, 2020))
    out = mod.transform_panel(panel, "log_diff")
    # First entry NaN; remaining entries ≈ log(1.10)
    assert out.iloc[0]["C00"] != out.iloc[0]["C00"]  # NaN check (NaN != NaN)
    np.testing.assert_allclose(out.iloc[1:]["C00"].values, np.log(1.10), atol=1e-10)


def test_transform_log_diff_handles_nonpositive():
    """Non-positive values become NaN under log; subsequent diff is NaN."""
    panel = pd.DataFrame(
        {"C00": [100.0, 110.0, 0.0, 130.0]},
        index=[2000, 2001, 2002, 2003],
    )
    out = mod.transform_panel(panel, "log_diff")
    # Entries depending on the zero are NaN
    # log(0) → NaN; diff at 2002 and 2003 both NaN
    assert pd.isna(out.iloc[0]["C00"])
    # Year 2001 diff = log(110) - log(100); year 2002 has log(0) → NaN
    assert not pd.isna(out.iloc[1]["C00"])
    assert pd.isna(out.iloc[2]["C00"])


def test_transform_invalid_kind_raises():
    panel = _wide_panel()
    with pytest.raises(ValueError, match="unknown transform"):
        mod.transform_panel(panel, "foo")


# ---------------------------------------------------------------------------
# demean_cross_section (Priya's spec)
# ---------------------------------------------------------------------------


def test_demean_cross_section_subtracts_yearly_mean():
    """At each year t, subtract mean across countries from each country's value."""
    panel = pd.DataFrame(
        {
            "C00": [1.0, 2.0, 3.0],
            "C01": [3.0, 4.0, 5.0],
            "C02": [5.0, 6.0, 7.0],
        },
        index=[2000, 2001, 2002],
    )
    # Yearly means: 3.0, 4.0, 5.0
    # After demeaning: each country's row should be panel - mean
    out = mod.demean_cross_section(panel)
    # Row 2000: [1-3, 3-3, 5-3] = [-2, 0, 2]
    np.testing.assert_array_equal(out.loc[2000].values, [-2.0, 0.0, 2.0])
    np.testing.assert_array_equal(out.loc[2001].values, [-2.0, 0.0, 2.0])
    np.testing.assert_array_equal(out.loc[2002].values, [-2.0, 0.0, 2.0])


def test_demean_cross_section_preserves_nan():
    panel = pd.DataFrame(
        {
            "C00": [1.0, np.nan, 3.0],
            "C01": [3.0, 5.0, 5.0],
        },
        index=[2000, 2001, 2002],
    )
    out = mod.demean_cross_section(panel)
    # Row 2001: only C01 present → mean=5; demeaned = [NaN, 0]
    assert pd.isna(out.loc[2001, "C00"])
    assert out.loc[2001, "C01"] == 0.0


def test_demean_cross_section_skipna_in_mean():
    """The yearly mean uses skipna=True; NaN countries don't contaminate."""
    panel = pd.DataFrame(
        {
            "C00": [1.0, 2.0, np.nan],
            "C01": [3.0, np.nan, 7.0],
            "C02": [5.0, 6.0, 9.0],
        },
        index=[2000, 2001, 2002],
    )
    out = mod.demean_cross_section(panel)
    # Row 2001 mean: (2 + 6) / 2 = 4. Demeaned: C00=-2, C01=NaN, C02=2
    assert out.loc[2001, "C00"] == -2.0
    assert pd.isna(out.loc[2001, "C01"])
    assert out.loc[2001, "C02"] == 2.0


# ---------------------------------------------------------------------------
# run_dscdi_pass — orchestration
# ---------------------------------------------------------------------------


def test_run_dscdi_pass_class_a_returns_baseline_and_primary():
    """Class A indicator gets two-pass: baseline (undemeaned) + primary (demeaned)."""
    panel = _wide_panel(n_years=30, n_countries=15)
    result = mod.run_dscdi_pass("v2x_libdem", panel, "I(1)")
    assert result.disposition.indicator_class == "A"
    assert result.demeaning_applied is True
    assert result.baseline_undemeaned is not None
    assert result.primary is not None
    assert result.baseline_undemeaned.shape == result.primary.shape
    # The two should differ — demeaning has non-trivial effect
    assert not np.allclose(
        result.baseline_undemeaned.fillna(0).values,
        result.primary.fillna(0).values,
    )


def test_run_dscdi_pass_class_b_no_baseline():
    """Class B: no demeaning, no separate baseline."""
    panel = _wide_panel(n_years=30, n_countries=15)
    result = mod.run_dscdi_pass("RL.EST", panel, "I(1)")
    assert result.disposition.indicator_class == "B"
    assert result.demeaning_applied is False
    assert result.baseline_undemeaned is None


def test_run_dscdi_pass_class_c_no_baseline():
    panel = _wide_panel(n_years=30, n_countries=15)
    result = mod.run_dscdi_pass("AG.LND.AGRI.ZS", panel, "I(1)")
    assert result.disposition.indicator_class == "C"
    assert result.demeaning_applied is False
    assert result.baseline_undemeaned is None


def test_run_dscdi_pass_growth_rate_no_demeaning():
    """NY.GDP.MKTP.KD.ZG: Class A doc, but demeaning suppressed (it's already
    a growth rate). demeaning_applied=False distinguishes this from
    'demeaning succeeded' for the Phase 6 ablation consumer."""
    panel = _wide_panel(n_years=30, n_countries=15)
    result = mod.run_dscdi_pass("NY.GDP.MKTP.KD.ZG", panel, "I(0)")
    assert result.disposition.indicator_class == "A"
    assert result.demeaning_applied is False  # suppressed; not "succeeded"
    assert result.baseline_undemeaned is None
    assert result.demeaning_insufficient is False  # cannot fire when not applied


def test_run_dscdi_pass_population_log_diff_with_demeaning():
    """SP.POP.TOTL: log_diff transform, then demeaned (Class A normal path)."""
    # Need positive values for log; population panel is always positive
    panel = pd.DataFrame(
        {
            f"C{i:02d}": np.cumprod(np.full(30, 1.01 + 0.001 * i))  # ~1% growth
            for i in range(15)
        },
        index=range(2000, 2030),
    )
    panel *= 1e6  # population scale
    result = mod.run_dscdi_pass("SP.POP.TOTL", panel, "I(2)_or_higher")
    assert result.disposition.transform == "log_diff"
    assert result.baseline_undemeaned is not None  # full Class A two-pass


def test_run_dscdi_pass_pairwise_diagnostic_threshold():
    """Stage C exit gate (Priya): mean abs > 0.25 → demeaning_insufficient flag.

    Negative path: a panel with a single dominant common factor — demeaning
    removes it cleanly, residuals are nearly independent, demeaning IS
    sufficient (flag = False)."""
    n_years = 30
    common = np.cumsum(RNG.standard_normal(n_years))  # shared trend
    panel_data = {}
    for i in range(15):
        panel_data[f"C{i:02d}"] = common + 0.1 * RNG.standard_normal(n_years)
    panel = pd.DataFrame(panel_data, index=range(2000, 2000 + n_years))
    result = mod.run_dscdi_pass("v2x_libdem", panel, "I(1)")
    assert result.disposition.indicator_class == "A"
    assert result.demeaning_applied is True
    assert result.baseline_undemeaned is not None
    baseline_mean_abs = mod._mean_abs_pairwise_off_diagonal(result.baseline_undemeaned)
    assert baseline_mean_abs > 0.5
    # Demeaning IS sufficient for single-factor case
    assert result.mean_abs_pairwise_corr < baseline_mean_abs
    assert result.demeaning_insufficient is False


def test_run_dscdi_pass_demeaning_insufficient_positive_path():
    """Positive path for the exit-gate flag: construct a panel where
    demeaning does NOT bring residual correlation below 0.25.

    Strategy: TWO orthogonal common factors. Global demeaning subtracts
    the cross-sectional mean (a noisy estimate of factor 1), leaving
    factor 2's structure intact in the residuals → high pairwise
    correlation persists → flag fires.
    """
    n_years = 40
    # Factor 1: shared trend across ALL countries (gets removed by demeaning)
    factor_1 = np.cumsum(RNG.standard_normal(n_years))
    # Factor 2: a region-block factor — half the countries share it,
    # the other half DO NOT. Subtracting cross-sectional mean cannot
    # remove a factor that affects only half the panel; residuals in
    # group A remain correlated with each other (and anti-correlated
    # with group B residuals).
    factor_2 = np.cumsum(RNG.standard_normal(n_years))
    panel_data = {}
    for i in range(10):
        # Group A: factor_1 + 3*factor_2 + tiny noise
        panel_data[f"A{i:02d}"] = factor_1 + 3.0 * factor_2 + 0.05 * RNG.standard_normal(n_years)
    for i in range(10):
        # Group B: factor_1 - 3*factor_2 + tiny noise (opposite loading)
        panel_data[f"B{i:02d}"] = factor_1 - 3.0 * factor_2 + 0.05 * RNG.standard_normal(n_years)
    panel = pd.DataFrame(panel_data, index=range(2000, 2000 + n_years))
    result = mod.run_dscdi_pass("v2x_libdem", panel, "I(1)")
    # The flag should fire because Group A and Group B residuals after
    # demeaning still have strong (anti-)correlation from factor_2.
    assert result.demeaning_applied is True
    assert result.mean_abs_pairwise_corr > 0.25, (
        f"expected mean_abs > 0.25 (insufficient); got {result.mean_abs_pairwise_corr}"
    )
    assert result.demeaning_insufficient is True


def test_run_dscdi_pass_min_obs_filter():
    """Countries with < min_obs (default 15) observations are filtered."""
    panel_data = {}
    # 5 countries with full 30 obs
    for i in range(5):
        panel_data[f"FULL{i:02d}"] = np.cumsum(RNG.standard_normal(30))
    # 5 countries with only 10 obs (below min_obs=15)
    for i in range(5):
        s = np.full(30, np.nan)
        s[:10] = np.cumsum(RNG.standard_normal(10))
        panel_data[f"SHORT{i:02d}"] = s
    panel = pd.DataFrame(panel_data, index=range(2000, 2030))
    result = mod.run_dscdi_pass("v2x_libdem", panel, "I(1)")
    assert result.n_countries == 5  # only the FULL ones (10 obs is < 15 after diff)


# ---------------------------------------------------------------------------
# _mean_abs_pairwise_off_diagonal
# ---------------------------------------------------------------------------


def test_mean_abs_excludes_diagonal():
    """Diagonal correlations (self) are 1.0; must be excluded."""
    corr = pd.DataFrame(
        [[1.0, 0.3, 0.5], [0.3, 1.0, 0.7], [0.5, 0.7, 1.0]],
        index=["A", "B", "C"],
        columns=["A", "B", "C"],
    )
    result = mod._mean_abs_pairwise_off_diagonal(corr)
    # Off-diagonal: |0.3| + |0.5| + |0.3| + |0.7| + |0.5| + |0.7| = 3.0
    # Mean of 6 off-diagonal entries = 0.5
    np.testing.assert_allclose(result, 0.5)


def test_mean_abs_handles_nan_pairs():
    corr = pd.DataFrame(
        [[1.0, np.nan, 0.5], [np.nan, 1.0, 0.7], [0.5, 0.7, 1.0]],
        index=["A", "B", "C"],
        columns=["A", "B", "C"],
    )
    result = mod._mean_abs_pairwise_off_diagonal(corr)
    # Off-diagonal non-NaN: 0.5, 0.7 (each appears twice in symmetric matrix)
    # Mean = (0.5 + 0.5 + 0.7 + 0.7) / 4 = 0.6
    np.testing.assert_allclose(result, 0.6)


def test_mean_abs_empty_returns_zero():
    """No countries / single country → 0.0 (no off-diagonal pairs)."""
    assert mod._mean_abs_pairwise_off_diagonal(pd.DataFrame()) == 0.0
    single = pd.DataFrame([[1.0]], index=["A"], columns=["A"])
    assert mod._mean_abs_pairwise_off_diagonal(single) == 0.0


# ---------------------------------------------------------------------------
# load_audit_classifications
# ---------------------------------------------------------------------------


def test_load_audit_skips_failures(tmp_path: Path):
    audit_payload = {
        "results": {
            "v2x_libdem": {"classification": "I(1)"},
            "FA-01": {"classification": "ambiguous"},
            "broken_indicator": {"classification": "load_failed"},
            "another_broken": {"classification": "test_failed"},
            "thin_panel": {"classification": "insufficient_data"},
        }
    }
    audit_file = tmp_path / "audit.json"
    audit_file.write_text(json.dumps(audit_payload))
    out = mod.load_audit_classifications(audit_file)
    assert set(out.keys()) == {"v2x_libdem", "FA-01"}
    assert out["v2x_libdem"] == "I(1)"
    assert out["FA-01"] == "ambiguous"


# ---------------------------------------------------------------------------
# build_diagnostic_report
# ---------------------------------------------------------------------------


def test_diagnostic_report_shape():
    panel = _wide_panel(n_years=30, n_countries=15)
    results = [
        mod.run_dscdi_pass("v2x_libdem", panel, "I(1)"),  # Class A
        mod.run_dscdi_pass("RL.EST", panel, "I(1)"),  # Class B
        mod.run_dscdi_pass("AG.LND.AGRI.ZS", panel, "I(1)"),  # Class C
    ]
    report = mod.build_diagnostic_report(results)
    assert report["schema_version"] == 1
    assert report["threshold_demeaning_insufficient"] == 0.25
    assert report["summary"]["n_total"] == 3
    assert report["summary"]["n_class_A"] == 1
    assert report["summary"]["n_class_B"] == 1
    assert report["summary"]["n_class_C"] == 1
    assert "v2x_libdem" in report["indicators"]
    assert report["indicators"]["v2x_libdem"]["indicator_class"] == "A"
    assert report["indicators"]["RL.EST"]["indicator_class"] == "B"
    # Phase 6 ablation distinguishes "demeaning attempted" from "Class B/C"
    assert report["indicators"]["v2x_libdem"]["demeaning_applied"] is True
    assert report["indicators"]["RL.EST"]["demeaning_applied"] is False
    assert report["indicators"]["AG.LND.AGRI.ZS"]["demeaning_applied"] is False


def test_diagnostic_report_distinguishes_no_transform_outlier():
    """NY.GDP.MKTP.KD.ZG is Class A but demeaning_applied=False (special
    case suppression). Phase 6 must be able to tell this apart from a
    Class B/C indicator which is also demeaning_applied=False but for a
    different reason. The report exposes both fields so the consumer can
    reason about the combination."""
    panel = _wide_panel(n_years=30, n_countries=15)
    result = mod.run_dscdi_pass("NY.GDP.MKTP.KD.ZG", panel, "I(0)")
    report = mod.build_diagnostic_report([result])
    record = report["indicators"]["NY.GDP.MKTP.KD.ZG"]
    assert record["indicator_class"] == "A"  # Class A by spec
    assert record["demeaning_applied"] is False  # but suppressed
    assert record["transform"] == "pass_through"


def test_diagnostic_report_counts_demeaning_insufficient():
    """When demeaning is insufficient, the count rises."""
    # Construct panel where demeaning STILL leaves high correlation
    # (residuals are themselves correlated). Hard to engineer; use a hack:
    # mock a result with the flag set.
    from dataclasses import replace

    panel = _wide_panel(n_years=30, n_countries=15)
    real = mod.run_dscdi_pass("v2x_libdem", panel, "I(1)")
    insufficient = replace(real, demeaning_insufficient=True)
    sufficient = replace(real, demeaning_insufficient=False)
    report = mod.build_diagnostic_report([insufficient, sufficient])
    assert report["summary"]["n_demeaning_insufficient"] == 1
