"""
Unit tests for run_v0_2_demeaned_spotcheck.py (T6 / #670).

Pins the Stage F transform chain + ADF classifier mirroring against the
qgi-pipeline source-of-truth. If the qgi-pipeline dscdi_finder.py ever
changes its transform / demean semantics, these tests force the spot-check
to follow before any T6 re-run produces an audit that diverges from
production.

Generated: 2026-05-12
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "run_v0_2_demeaned_spotcheck.py"
)
_spec = importlib.util.spec_from_file_location("run_v0_2_demeaned_spotcheck", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["run_v0_2_demeaned_spotcheck"] = mod
_spec.loader.exec_module(mod)


# ===========================================================================
# T6 target list (must be exactly the 9 indicators from the ticket)
# ===========================================================================

def test_t6_target_list_has_9_indicators():
    """T6 ticket #670 spec: 4 Class-A demeaning-insufficient + 5 V-Dem
    low-survival tail. Total = 9. Any deviation is a Protocol 5 breach
    against Tariq's T1 sign-off."""
    assert len(mod.T6_TARGETS) == 9


def test_t6_target_list_contains_the_4_class_a_flags_verbatim():
    """The 4 demeaning-insufficient Class A flags must be present
    verbatim (charter §148 + JSON config + spec §8.1)."""
    ids = {t["id"] for t in mod.T6_TARGETS}
    required_class_a = {
        "FP.CPI.TOTL.ZG", "NY.GDP.PCAP.CD", "SH.DYN.MORT", "SP.POP.TOTL",
    }
    assert required_class_a.issubset(ids)


def test_t6_target_list_contains_the_5_v_dem_random_draws():
    """The 5 V-Dem random-draw indicators must be present verbatim
    (charter §148 / spec §8.1)."""
    ids = {t["id"] for t in mod.T6_TARGETS}
    required_v_dem = {
        "v2elintmon", "v2x_regime", "v2x_gender", "v2pepwrgen", "v2x_partip",
    }
    assert required_v_dem.issubset(ids)


# ===========================================================================
# Stage F transform-chain mirror (must match qgi-pipeline verbatim)
# ===========================================================================

def test_class_a_severe_csd_set_matches_pipeline():
    """The CLASS_A_SEVERE_CSD set in this script MUST match
    qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py verbatim. If the
    pipeline updates its Class A roster and this set drifts, the spot-check
    will apply the wrong transform/demean chain — making the audit
    methodologically incompatible with production Stage F."""
    expected = frozenset({
        "v2x_libdem", "NY.GDP.PCAP.CD", "FP.CPI.TOTL.ZG", "SL.UEM.TOTL.ZS",
        "CC.EST",
        "v2x_polyarchy", "MS.MIL.XPND.GD.ZS", "NE.EXP.GNFS.ZS", "NE.IMP.GNFS.ZS",
        "SE.PRM.ENRR", "SH.DYN.MORT", "SP.DYN.LE00.IN", "SP.DYN.TFRT.IN",
        "IT.CEL.SETS.P2",
    })
    assert mod.CLASS_A_SEVERE_CSD == expected


def test_outlier_no_transform_set_matches_pipeline():
    assert mod.OUTLIER_NO_TRANSFORM == frozenset({"NY.GDP.MKTP.KD.ZG"})


def test_outlier_log_difference_set_matches_pipeline():
    assert mod.OUTLIER_LOG_DIFFERENCE == frozenset({"SP.POP.TOTL"})


# ---------------------------------------------------------------------------
# determine_transform_and_demean dispatch
# ---------------------------------------------------------------------------

def test_dispatch_outlier_no_transform_pass_through_no_demean():
    """NY.GDP.MKTP.KD.ZG is a growth rate; pass-through, no demean."""
    transform, demean = mod.determine_transform_and_demean(
        "NY.GDP.MKTP.KD.ZG", "I(0)"
    )
    assert transform == "pass_through"
    assert demean is False


def test_dispatch_outlier_log_difference_log_diff_with_demean():
    """SP.POP.TOTL is log-differenced AND demeaned (Class A)."""
    transform, demean = mod.determine_transform_and_demean(
        "SP.POP.TOTL", "I(2)_or_higher"
    )
    assert transform == "log_diff"
    assert demean is True


def test_dispatch_class_a_severe_csd_first_diff_with_demean_for_i1():
    """CLASS_A_SEVERE_CSD member with I(1) classification gets first_diff + demean."""
    transform, demean = mod.determine_transform_and_demean(
        "FP.CPI.TOTL.ZG", "I(1)"
    )
    assert transform == "first_diff"
    assert demean is True


def test_dispatch_i2_fallback_diverges_from_pipeline_intentionally(capsys):
    """T6 PR #57 review NIT 1: the pipeline raises ValueError for any
    I(2)_or_higher indicator outside OUTLIER_LOG_DIFFERENCE; the audit
    script uses a conservative first_diff fallback for robustness.

    This test pins the intentional divergence so a future refactor
    can't silently change it without updating the comment + warning.
    A bogus indicator (not in OUTLIER_LOG_DIFFERENCE) with classification
    I(2)_or_higher must:
      - NOT raise (script tolerates the audit)
      - Return transform=first_diff
      - Emit a warning to stderr making the divergence visible
    """
    transform, demean = mod.determine_transform_and_demean(
        "NOT_AN_OUTLIER_INDICATOR", "I(2)_or_higher"
    )
    assert transform == "first_diff", (
        "I(2) fallback must use first_diff — the conservative-fallback "
        "contract documented in the script comment"
    )
    captured = capsys.readouterr()
    assert "I(2)_or_higher" in captured.err
    assert "Tariq consultation" in captured.err, (
        "warning print must mention Tariq consultation so the divergence "
        "from pipeline raise-behavior is visible at audit run time"
    )


def test_dispatch_i2_outlier_short_circuits_before_fallback(capsys):
    """SP.POP.TOTL is in OUTLIER_LOG_DIFFERENCE and must short-circuit
    to log_diff + demean WITHOUT triggering the I(2) fallback warning —
    pinning that the OUTLIER_LOG_DIFFERENCE check fires before the
    classification-driven branch."""
    transform, demean = mod.determine_transform_and_demean(
        "SP.POP.TOTL", "I(2)_or_higher"
    )
    assert transform == "log_diff"
    assert demean is True
    captured = capsys.readouterr()
    # No I(2) fallback warning — the outlier path bypassed the branch
    assert "I(2)_or_higher classification reached" not in captured.err


def test_dispatch_v_dem_indicator_is_class_c_no_demean():
    """V-Dem indicators are NOT in CLASS_A_SEVERE_CSD or CLASS_B_WGI, so
    they are Class C — get a transform but NO demeaning. This is critical:
    if the V-Dem 5 were treated as Class A, the spot-check would demean
    them and the verdict would be methodologically wrong."""
    for v_dem in ("v2elintmon", "v2x_regime", "v2x_gender", "v2pepwrgen", "v2x_partip"):
        transform, demean = mod.determine_transform_and_demean(v_dem, "I(1)")
        assert demean is False, (
            f"{v_dem} should be Class C (no demean), got demean=True. "
            f"If qgi-pipeline added V-Dem indicators to CLASS_A_SEVERE_CSD, "
            f"update both CLASS_A_SEVERE_CSD and this test."
        )


# ---------------------------------------------------------------------------
# transform_panel math
# ---------------------------------------------------------------------------

def test_transform_panel_pass_through_is_identity():
    panel = pd.DataFrame({"A": [1.0, 2.0, 3.0], "B": [10.0, 20.0, 30.0]})
    out = mod.transform_panel(panel, "pass_through")
    pd.testing.assert_frame_equal(out, panel)


def test_transform_panel_first_diff_matches_pandas_diff():
    panel = pd.DataFrame({"A": [1.0, 2.0, 5.0], "B": [10.0, 30.0, 70.0]})
    out = mod.transform_panel(panel, "first_diff")
    expected = pd.DataFrame({"A": [np.nan, 1.0, 3.0], "B": [np.nan, 20.0, 40.0]})
    pd.testing.assert_frame_equal(out, expected)


def test_transform_panel_log_diff_handles_non_positive_via_nan():
    """log_diff: log(x_t / x_{t-1}). Non-positive entries → NaN."""
    panel = pd.DataFrame({"A": [1.0, 2.0, 4.0], "B": [0.0, 1.0, 2.0]})
    out = mod.transform_panel(panel, "log_diff")
    # A: log(2/1)=log(2), log(4/2)=log(2)
    # B: 0.0 becomes NaN before diff, so first diff is NaN, second is NaN (log(2)-NaN=NaN)
    assert out.loc[1, "A"] == pytest.approx(np.log(2))
    assert out.loc[2, "A"] == pytest.approx(np.log(2))
    assert pd.isna(out.loc[0, "A"])
    assert pd.isna(out.loc[0, "B"])
    assert pd.isna(out.loc[1, "B"])  # 0.0 -> NaN propagates


def test_transform_panel_unknown_raises():
    with pytest.raises(ValueError, match="unknown transform"):
        mod.transform_panel(pd.DataFrame({"A": [1.0]}), "bogus")


# ---------------------------------------------------------------------------
# demean_cross_section math
# ---------------------------------------------------------------------------

def test_demean_cross_section_subtracts_row_mean():
    """Two countries, three years. Row means = [(1+3)/2, (2+4)/2, (5+7)/2]
    = [2, 3, 6]. Demeaned: A=[-1, -1, -1], B=[1, 1, 1]."""
    panel = pd.DataFrame({"A": [1.0, 2.0, 5.0], "B": [3.0, 4.0, 7.0]})
    out = mod.demean_cross_section(panel)
    assert out["A"].tolist() == [-1.0, -1.0, -1.0]
    assert out["B"].tolist() == [1.0, 1.0, 1.0]


def test_demean_cross_section_nan_safe():
    """If one country has NaN at year t, the row mean is computed from
    the other countries, NaN propagates through subtraction for the
    NaN-cell only."""
    panel = pd.DataFrame({"A": [1.0, np.nan, 3.0], "B": [3.0, 4.0, 7.0]})
    out = mod.demean_cross_section(panel)
    # Year 0: mean=(1+3)/2=2 -> A=-1, B=1
    # Year 1: mean=4 (only B) -> A=NaN, B=0
    # Year 2: mean=(3+7)/2=5 -> A=-2, B=2
    assert out["A"].tolist()[0] == -1.0
    assert pd.isna(out["A"].tolist()[1])
    assert out["A"].tolist()[2] == -2.0
    assert out["B"].tolist() == [1.0, 0.0, 2.0]


# ---------------------------------------------------------------------------
# ADF thresholds + min-obs (must match v2 baseline generator verbatim)
# ---------------------------------------------------------------------------

def test_adf_thresholds_match_v2_baseline_generator():
    """The thresholds must match run_i5_substrate_audit.py verbatim, or
    the spot-check is not apples-to-apples with the v2 baseline."""
    assert mod.ADF_FRAC_THRESHOLDS["I(0)_strong"] == 0.70
    assert mod.ADF_FRAC_THRESHOLDS["I(1)_strong"] == 0.30
    assert mod.ADF_FRAC_THRESHOLDS["I(2)_strong"] == 0.30
    assert mod.P_REJECT == 0.05
    assert mod.MIN_OBS_REQUIRED == 15


# ---------------------------------------------------------------------------
# classify_indicator_adf_fallback — synthetic stationarity examples
# ---------------------------------------------------------------------------

def test_classify_clean_i0_panel_yields_i0():
    """White-noise panel: every country's level rejects unit root → I(0)."""
    rng = np.random.default_rng(42)
    n_years, n_countries = 40, 30
    data = rng.normal(0, 1, size=(n_years, n_countries))
    panel = pd.DataFrame(data, index=range(2000, 2000 + n_years),
                          columns=[f"C{i}" for i in range(n_countries)])
    out = mod.classify_indicator_adf_fallback(panel)
    assert out["classification"] == "I(0)"
    assert out["frac_rejected_at_level"] >= 0.70


def test_classify_random_walk_panel_yields_i1():
    """Random-walk panel: levels do NOT reject; diffs do → I(1)."""
    rng = np.random.default_rng(123)
    n_years, n_countries = 40, 30
    innov = rng.normal(0, 1, size=(n_years, n_countries))
    rw = innov.cumsum(axis=0)
    panel = pd.DataFrame(rw, index=range(2000, 2000 + n_years),
                          columns=[f"C{i}" for i in range(n_countries)])
    out = mod.classify_indicator_adf_fallback(panel)
    assert out["classification"] == "I(1)"
    assert out["frac_rejected_at_level"] < 0.70
    assert out["frac_rejected_at_diff"] >= 0.70


def test_classify_too_few_obs_returns_insufficient():
    """Panel where every country has < min_obs_required observations
    must return 'insufficient_data' rather than crashing."""
    panel = pd.DataFrame({
        "A": [1.0, 2.0, 3.0],
        "B": [4.0, 5.0, 6.0],
    })
    out = mod.classify_indicator_adf_fallback(panel)
    assert out["classification"] == "insufficient_data"
    assert out["n_countries_tested_at_level"] == 0
