"""Tests for `qgi_ml.src.walk.falsification`."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from walk.falsification import (  # noqa: E402
    BASELINE_REGRESSION_THRESHOLD,
    F1_ECE_THRESHOLD,
    F2_AUC_BASELINE,
    F2_AUC_POINT_THRESHOLD,
    F3_HAZARD_BAND_THRESHOLD,
    bootstrap_ci,
    compute_auc,
    compute_brier,
    compute_ece,
    decide_verdict,
    evaluate_baseline_comparison,
    evaluate_f1,
    evaluate_f2,
    evaluate_f3,
)


# -- compute_auc --------------------------------------------------------------


class TestComputeAuc:
    def test_perfect_ranking_auc_1(self) -> None:
        probs = np.array([0.1, 0.2, 0.8, 0.9])
        labels = np.array([0, 0, 1, 1])
        assert compute_auc(probs, labels) == 1.0

    def test_inverse_ranking_auc_0(self) -> None:
        probs = np.array([0.1, 0.2, 0.8, 0.9])
        labels = np.array([1, 1, 0, 0])
        assert compute_auc(probs, labels) == 0.0

    def test_random_shuffle_close_to_half(self) -> None:
        rng = np.random.default_rng(42)
        n = 1000
        probs = rng.random(n)
        labels = rng.integers(0, 2, n)
        auc = compute_auc(probs, labels)
        assert 0.45 <= auc <= 0.55

    def test_single_class_returns_nan(self) -> None:
        assert np.isnan(compute_auc(np.array([0.1, 0.5]), np.array([0, 0])))
        assert np.isnan(compute_auc(np.array([0.1, 0.5]), np.array([1, 1])))

    def test_ties_handled_via_average_rank(self) -> None:
        probs = np.array([0.5, 0.5, 0.5, 0.5])
        labels = np.array([0, 0, 1, 1])
        # All tied → AUC = 0.5
        assert compute_auc(probs, labels) == 0.5

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="shape mismatch"):
            compute_auc(np.array([0.1, 0.2]), np.array([0, 0, 1]))


# -- compute_ece --------------------------------------------------------------


class TestComputeEce:
    def test_perfect_calibration_zero(self) -> None:
        # All probs = 0.5; half labels = 1, half = 0 → mean label = 0.5 = mean prob
        probs = np.full(100, 0.5)
        labels = np.array([0] * 50 + [1] * 50)
        assert compute_ece(probs, labels, n_bins=10) == 0.0

    def test_total_miscalibration_high(self) -> None:
        # Predicts 1.0 always; actual = all zero → ECE = 1.0
        probs = np.full(100, 0.99)
        labels = np.zeros(100, dtype=int)
        ece = compute_ece(probs, labels, n_bins=10)
        assert ece > 0.95

    def test_empty_returns_nan(self) -> None:
        assert np.isnan(compute_ece(np.array([]), np.array([]), n_bins=10))

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="shape mismatch"):
            compute_ece(np.array([0.1]), np.array([0, 1]))


# -- bootstrap_ci -------------------------------------------------------------


class TestBootstrapCi:
    def test_seeded_reproducibility(self) -> None:
        rng = np.random.default_rng(0)
        probs = rng.random(100)
        labels = rng.integers(0, 2, 100)
        result_a = bootstrap_ci(compute_auc, probs, labels, n_bootstrap=50, seed=42)
        result_b = bootstrap_ci(compute_auc, probs, labels, n_bootstrap=50, seed=42)
        assert result_a == result_b

    def test_returns_three_values(self) -> None:
        rng = np.random.default_rng(0)
        probs = rng.random(100)
        labels = rng.integers(0, 2, 100)
        point, lo, hi = bootstrap_ci(compute_auc, probs, labels, n_bootstrap=50, seed=0)
        assert lo <= point <= hi

    def test_invalid_confidence_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            bootstrap_ci(
                compute_auc, np.array([0.1]), np.array([0]),
                n_bootstrap=10, confidence=1.5,
            )

    def test_stratified_preserves_per_class_size(self) -> None:
        labels = np.array([0] * 90 + [1] * 10)
        probs = labels.astype(float) + 0.5  # perfect signal
        # Stratified bootstrap on tiny positive class — should still
        # discriminate well because positive class is preserved.
        point, lo, hi = bootstrap_ci(
            compute_auc, probs, labels,
            n_bootstrap=200, seed=0, stratify=labels,
        )
        # Perfect signal AUC on stratified bootstrap should be close to 1
        assert lo > 0.99


# -- evaluate_f1 --------------------------------------------------------------


class TestEvaluateF1:
    def test_passes_when_well_calibrated(self) -> None:
        probs = np.full(100, 0.5)
        labels = np.array([0] * 50 + [1] * 50)
        result = evaluate_f1(probs, labels)
        assert result["passed"] is True
        assert result["value"] == 0.0

    def test_fails_when_miscalibrated_above_threshold(self) -> None:
        probs = np.full(100, 0.99)
        labels = np.zeros(100, dtype=int)
        result = evaluate_f1(probs, labels)
        assert result["passed"] is False
        assert result["value"] > F1_ECE_THRESHOLD

    def test_threshold_locked_to_pre_reg(self) -> None:
        assert F1_ECE_THRESHOLD == 0.08


# -- evaluate_f2 --------------------------------------------------------------


class TestEvaluateF2:
    def test_passes_with_strong_signal(self) -> None:
        rng = np.random.default_rng(0)
        n = 200
        labels = (rng.random(n) < 0.5).astype(int)
        # Very strong signal: probs strongly correlated with labels.
        probs = labels.astype(float) * 0.7 + rng.normal(0, 0.05, n)
        probs = np.clip(probs, 0.01, 0.99)
        result = evaluate_f2(probs, labels, n_bootstrap=100, seed=0)
        assert result["passed"] is True
        assert result["value"] >= F2_AUC_POINT_THRESHOLD
        assert result["ci_lower"] > F2_AUC_BASELINE

    def test_fails_when_anti_signal(self) -> None:
        # Anti-signal: probs INVERSELY correlated with labels →
        # point AUC near 0.0, far below the F2 0.57 threshold and
        # the CI cannot exclude 0.5 in the desired direction.
        # This is more reliable than truly-random probs at small n.
        rng = np.random.default_rng(0)
        n = 200
        labels = np.array([0] * 100 + [1] * 100)
        probs = (1.0 - labels.astype(float)) * 0.5 + rng.normal(0, 0.05, n)
        probs = np.clip(probs, 0.01, 0.99)
        result = evaluate_f2(probs, labels, n_bootstrap=200, seed=0)
        assert result["passed"] is False
        assert result["value"] < 0.5  # anti-signal yields low AUC

    def test_pre_reg_thresholds_locked(self) -> None:
        assert F2_AUC_POINT_THRESHOLD == 0.57
        assert F2_AUC_BASELINE == 0.5


# -- evaluate_f3 --------------------------------------------------------------


class TestEvaluateF3:
    def test_passes_when_band_narrow(self) -> None:
        rng = np.random.default_rng(0)
        # Many samples, low variance probs → narrow CI
        probs = np.full(500, 0.3) + rng.normal(0, 0.01, 500)
        labels = rng.integers(0, 2, 500)
        result = evaluate_f3(probs, labels, n_bootstrap=200, seed=0)
        assert result["passed"] is True
        assert result["value"] < F3_HAZARD_BAND_THRESHOLD

    def test_pre_reg_threshold_locked(self) -> None:
        assert F3_HAZARD_BAND_THRESHOLD == 0.30


# -- evaluate_baseline_comparison --------------------------------------------


class TestEvaluateBaselineComparison:
    def test_passes_when_deephit_matches_baseline(self) -> None:
        rng = np.random.default_rng(0)
        n = 100
        labels = rng.integers(0, 2, n)
        probs_same = rng.random(n)
        result = evaluate_baseline_comparison(probs_same, probs_same, labels)
        assert result["passed"] is True
        assert result["delta_auc"] == 0.0
        assert result["delta_brier"] == 0.0

    def test_fails_when_deephit_auc_regresses(self) -> None:
        # Baseline has perfect signal; deephit is noise.
        labels = np.array([0, 0, 1, 1, 0, 1, 1, 0, 0, 1])
        baseline = labels.astype(float) * 0.9 + 0.05  # AUC = 1.0
        deephit = np.array([0.5] * 10)  # AUC = NaN (single value)
        # Synthesize a noisy deephit that gets ~0.4 AUC
        deephit = np.array([0.5, 0.5, 0.5, 0.4, 0.6, 0.4, 0.5, 0.5, 0.5, 0.5])
        result = evaluate_baseline_comparison(deephit, baseline, labels)
        # Baseline AUC = 1.0, deephit AUC < 1, delta < 0
        assert result["delta_auc"] < 0
        assert result["passed"] is False
        assert "noise_band_disclosure" in result

    def test_pre_reg_threshold_locked(self) -> None:
        assert BASELINE_REGRESSION_THRESHOLD == 0.03


# -- decide_verdict ----------------------------------------------------------


class TestDecideVerdict:
    def _make_passing_results(self):
        f1 = {"passed": True, "rule": "F1_calibration", "value": 0.05, "threshold": 0.08}
        f2 = {
            "passed": True, "rule": "F2_auc", "value": 0.65, "ci_lower": 0.55,
            "ci_excludes_baseline": True, "point_meets_threshold": True,
            "baseline": 0.5, "point_threshold": 0.57,
        }
        f3 = {"passed": True, "rule": "F3_hazard_band", "value": 0.10, "threshold": 0.30}
        baseline = {
            "passed": True, "delta_auc": 0.01, "delta_brier": -0.01,
            "auc_regression": False, "brier_regression": False,
        }
        return f1, f2, f3, baseline

    def test_all_pass_yields_locked(self) -> None:
        f1, f2, f3, baseline = self._make_passing_results()
        verdict = decide_verdict(f1, f2, f3, baseline)
        assert verdict["verdict"] == "LOCKED"

    def test_f1_fail_yields_falsified(self) -> None:
        f1, f2, f3, baseline = self._make_passing_results()
        f1["passed"] = False
        verdict = decide_verdict(f1, f2, f3, baseline)
        assert verdict["verdict"] == "FALSIFIED"

    def test_f3_fail_takes_precedence_over_f1_fail(self) -> None:
        f1, f2, f3, baseline = self._make_passing_results()
        f1["passed"] = False
        f3["passed"] = False
        verdict = decide_verdict(f1, f2, f3, baseline)
        assert verdict["verdict"] == "F5_FALLBACK"

    def test_baseline_regression_yields_fallback(self) -> None:
        f1, f2, f3, baseline = self._make_passing_results()
        baseline["passed"] = False
        baseline["auc_regression"] = True
        baseline["delta_auc"] = -0.05
        verdict = decide_verdict(f1, f2, f3, baseline)
        assert verdict["verdict"] == "F5_FALLBACK"

    def test_f3_none_for_non_survival_heads(self) -> None:
        # F5=2 (asymmetric GBM) doesn't apply F3.
        f1, f2, _, baseline = self._make_passing_results()
        verdict = decide_verdict(f1, f2, f3=None, baseline_cmp=baseline)
        assert verdict["verdict"] == "LOCKED"

    def test_f2_fail_yields_falsified(self) -> None:
        f1, f2, f3, baseline = self._make_passing_results()
        f2["passed"] = False
        f2["point_meets_threshold"] = False
        f2["value"] = 0.50
        verdict = decide_verdict(f1, f2, f3, baseline)
        assert verdict["verdict"] == "FALSIFIED"


# -- compute_brier -----------------------------------------------------------


class TestComputeBrier:
    def test_perfect_predictor(self) -> None:
        probs = np.array([0.0, 0.0, 1.0, 1.0])
        labels = np.array([0, 0, 1, 1])
        assert compute_brier(probs, labels) == 0.0

    def test_constant_at_base_rate(self) -> None:
        probs = np.full(10, 0.5)
        labels = np.array([0] * 5 + [1] * 5)
        # Brier = mean( (0.5 - y)^2 ) = mean(0.25) = 0.25
        assert compute_brier(probs, labels) == 0.25

    def test_empty_returns_nan(self) -> None:
        assert np.isnan(compute_brier(np.array([]), np.array([])))

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="shape mismatch"):
            compute_brier(np.array([0.1]), np.array([0, 1]))
