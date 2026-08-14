"""Unit tests for src/beta_calibration.py.

Sections:
  - The 7 original tests for `BetaCalibrator` (pre-#969).
  - The new tests for `compute_calibration_bins` / `compute_ece` /
    `compute_calibration_block` (added for #969 — F-ML-1 walk emit).
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pytest

SRC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import beta_calibration as bc  # noqa: E402


def test_beta_calibrator_identity_on_perfectly_calibrated_input():
    """When raw scores already match observed rates, calibration should be near identity."""
    rng = np.random.default_rng(0)
    n = 2000
    raw = rng.uniform(0, 1, size=n)
    # Generate labels with rate exactly equal to raw score (perfect cal target)
    y = (rng.uniform(0, 1, size=n) < raw).astype(int)
    cal = bc.BetaCalibrator.fit(raw, y)
    # Predict on a clean grid; calibrated values should track input closely
    s_test = np.linspace(0.05, 0.95, 19)
    pred = cal.predict(s_test)
    # Expect near-monotonic, near-identity (some shrinkage is OK)
    assert np.all(np.diff(pred) >= -1e-6)  # monotonic non-decreasing
    # Mean absolute deviation should be small
    assert np.mean(np.abs(pred - s_test)) < 0.10


def test_beta_calibrator_corrects_overconfident_input():
    """Overconfident predictions (extreme 0/1 values) should be pulled back toward middle."""
    rng = np.random.default_rng(1)
    n = 1000
    # Half the samples: predicted 0.95, observed rate 0.7 (overconfident high)
    raw_high = np.full(n // 2, 0.95)
    y_high = (rng.uniform(0, 1, size=n // 2) < 0.7).astype(int)
    # Half: predicted 0.05, observed rate 0.3 (overconfident low)
    raw_low = np.full(n // 2, 0.05)
    y_low = (rng.uniform(0, 1, size=n // 2) < 0.3).astype(int)
    raw = np.concatenate([raw_high, raw_low])
    y = np.concatenate([y_high, y_low])
    cal = bc.BetaCalibrator.fit(raw, y)
    # Calibrated 0.95 should be pulled down toward ~0.7
    pred_high = cal.predict(np.array([0.95]))[0]
    pred_low = cal.predict(np.array([0.05]))[0]
    assert pred_high < 0.95  # corrected downward
    assert pred_low > 0.05   # corrected upward
    # Predictions on raw=0.5 should also be reasonable (near middle-region)
    assert 0.0 < cal.predict(np.array([0.5]))[0] < 1.0


def test_beta_calibrator_preserves_monotonicity():
    """a >= 0 + b >= 0 bounds enforce monotonic calibration in s."""
    rng = np.random.default_rng(2)
    n = 500
    raw = rng.uniform(0, 1, size=n)
    y = (rng.uniform(0, 1, size=n) < raw ** 2).astype(int)  # nonlinear truth
    cal = bc.BetaCalibrator.fit(raw, y)
    # Predictions on monotonic grid must be monotonic non-decreasing
    grid = np.linspace(0.01, 0.99, 99)
    pred = cal.predict(grid)
    assert np.all(np.diff(pred) >= -1e-6)


def test_beta_calibrator_handles_extreme_inputs():
    """Inputs of exactly 0 or 1 must not crash (clipped internally)."""
    raw = np.array([0.0, 0.5, 1.0])
    y = np.array([0, 1, 1])
    cal = bc.BetaCalibrator.fit(raw, y)
    pred = cal.predict(np.array([0.0, 0.5, 1.0]))
    assert np.all(np.isfinite(pred))
    assert np.all((pred >= 0) & (pred <= 1))


def test_beta_calibrator_degenerate_with_one_sample():
    """Single sample -> identity calibrator (no fit), should not crash."""
    cal = bc.BetaCalibrator.fit(np.array([0.5]), np.array([1]))
    assert cal.n_fit == 1
    # Identity init: a=1, b=1, c=0
    # g(s) = log(s) + log(1-s) = log(s*(1-s))
    # sigmoid(g) = s*(1-s) / (s*(1-s) + 1)
    pred = cal.predict(np.array([0.3]))
    expected = (0.3 * 0.7) / (0.3 * 0.7 + 1)  # = 0.21 / 1.21 ≈ 0.1736
    assert abs(pred[0] - expected) < 0.01


def test_beta_calibrator_to_dict_round_trip():
    cal = bc.BetaCalibrator(a=2.0, b=1.5, c=-0.5, n_fit=100, converged=True)
    d = cal.to_dict()
    assert d["a"] == 2.0
    assert d["b"] == 1.5
    assert d["c"] == -0.5
    assert d["n_fit"] == 100
    assert d["converged"] is True


def test_beta_calibrator_shape_mismatch_raises():
    with pytest.raises(ValueError, match="shape mismatch"):
        bc.BetaCalibrator.fit(np.array([0.5, 0.6]), np.array([1, 1, 0]))


# ============================================================================
# #969 — Beta calibration emit helpers (compute_calibration_bins / compute_ece /
# compute_calibration_block) — F-ML-1 walk-driver emit + frontend §3.6.
# ============================================================================

def _synthetic_well_calibrated(n=1000, seed=0):
    """Bernoulli draws with underlying prob === predicted prob. ECE near zero."""
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.01, 0.99, n)
    y = (rng.uniform(0, 1, n) < p).astype(int)
    return p, y


def _synthetic_overconfident(n=2000, seed=0):
    """Predictions 0.05 / 0.95 with true rates 0.4 / 0.6 — systematic overconfidence
    for the calibration-narrows-the-gap test."""
    rng = np.random.default_rng(seed)
    p = np.concatenate([np.full(n // 2, 0.05), np.full(n - n // 2, 0.95)])
    y_bot = (rng.uniform(0, 1, n // 2) < 0.4).astype(int)
    y_top = (rng.uniform(0, 1, n - n // 2) < 0.6).astype(int)
    return p, np.concatenate([y_bot, y_top])


# ---------- compute_calibration_bins ----------------------------------------

def test_ece_bins_cover_unit_interval_in_ten_steps():
    p, y = _synthetic_well_calibrated(n=500)
    bins = bc.compute_calibration_bins(p, y)
    assert len(bins) == 10
    assert bins[0]["predicted_lo"] == 0.0 and bins[-1]["predicted_hi"] == 1.0
    for i in range(9):
        assert bins[i]["predicted_hi"] == bins[i + 1]["predicted_lo"]


def test_ece_bin_counts_sum_to_total():
    p, y = _synthetic_well_calibrated(n=500)
    bins = bc.compute_calibration_bins(p, y)
    assert sum(b["count"] for b in bins) == p.size


def test_ece_empty_bin_has_None_observed_rate():
    """Frontend renders the gap honestly, not zero-fills."""
    p = np.array([0.1, 0.2, 0.8, 0.9])
    y = np.array([0, 0, 1, 1])
    bins = bc.compute_calibration_bins(p, y)
    for b in bins:
        if b["count"] == 0:
            assert b["observed_rate"] is None
        else:
            assert b["observed_rate"] is not None


def test_ece_last_bin_inclusive_on_1_0():
    """A prediction of EXACTLY 1.0 must land in the last bin, not be dropped."""
    bins = bc.compute_calibration_bins(np.array([1.0]), np.array([1]))
    assert bins[-1]["count"] == 1


# ---------- compute_ece ------------------------------------------------------

def test_ece_perfect_calibration_yields_near_zero():
    # Construct directly: every prediction MATCHES its bin's observed rate.
    p = np.array([0.05] * 100 + [0.95] * 100)
    y = np.concatenate([np.zeros(95), np.ones(5),
                         np.zeros(5), np.ones(95)])
    assert bc.compute_ece(p, y) < 0.005


def test_ece_systematic_overconfidence_yields_significant_value():
    p, y = _synthetic_overconfident(n=2000)
    # 0.95-predicting half has true rate ~0.6 (gap ~0.35); 0.05-half rate ~0.4 (gap ~0.35).
    assert 0.20 < bc.compute_ece(p, y) < 0.45


def test_ece_empty_input_returns_nan():
    assert np.isnan(bc.compute_ece(np.array([]), np.array([])))


# ---------- compute_calibration_block (the orchestrator) ---------------------

def test_calibration_block_well_conditioned_emits_full_block():
    p, y = _synthetic_well_calibrated(n=500)
    block = bc.compute_calibration_block(p, y)
    assert block["computed"] is True
    assert "method" in block
    assert {"a", "b", "c", "n_fit", "converged"} <= set(block["fit"])
    assert len(block["bins"]) == 10
    assert isinstance(block["ece"], float)
    assert block["n_predictions"] == 500


def test_calibration_block_too_small_input_emits_computed_false():
    block = bc.compute_calibration_block(np.array([0.3, 0.7]), np.array([0, 1]))
    assert block["computed"] is False and "reason" in block


def test_calibration_block_single_class_emits_computed_false():
    p = np.linspace(0.1, 0.9, 200)
    for y in (np.zeros_like(p, dtype=int), np.ones_like(p, dtype=int)):
        block = bc.compute_calibration_block(p, y)
        assert block["computed"] is False
        assert "single-class" in block["reason"]


def test_calibration_block_shape_mismatch_emits_computed_false():
    block = bc.compute_calibration_block(np.array([0.3, 0.5, 0.7]), np.array([0, 1]))
    assert block["computed"] is False and "shape mismatch" in block["reason"]


def test_calibration_block_non_convergence_emits_computed_false(monkeypatch):
    """FU-3 (QA PR#124): if BetaCalibrator.fit returns converged=False (e.g.
    L-BFGS-B hit iteration limit on an ill-conditioned but well-sized sample),
    the orchestrator must emit `computed:false` with a clear reason — never a
    silent populated block with a non-converged fit. MARGINAL_PENDING recipes are
    the primary consumers and may sit near this edge."""
    p, y = _synthetic_well_calibrated(n=500)
    real_fit = bc.BetaCalibrator.fit

    def _fake_fit(cls, raw_scores, labels, **kwargs):
        cal = real_fit(raw_scores, labels, **kwargs)
        # Same parameters as the real fit — we test the converged-flag handling,
        # not the math. Force converged=False.
        return bc.BetaCalibrator(a=cal.a, b=cal.b, c=cal.c,
                                  n_fit=cal.n_fit, converged=False)

    monkeypatch.setattr(bc.BetaCalibrator, "fit", classmethod(_fake_fit))
    block = bc.compute_calibration_block(p, y)
    assert block["computed"] is False
    assert "converge" in block["reason"].lower()


def test_calibration_narrows_gap_on_overconfident_input():
    """The methodology promise — Beta calibration must REDUCE ECE on a systematically
    over-confident classifier. Pre-calibration ECE is ~0.35; post-calibration ECE
    should be smaller."""
    p, y = _synthetic_overconfident(n=2000)
    pre = bc.compute_ece(p, y)
    block = bc.compute_calibration_block(p, y)
    assert block["computed"] is True
    assert block["ece"] < pre
