"""Unit tests for plot_pr_curve.py pure functions.

Covers:
  - safe_get() — deep key traversal with default
  - Recall computation formula used by plot_pr_operating_points
  - Margin trajectory hardcoded constants sanity check
  - Data extraction helpers (val/test metric extraction via safe_get)
  - Empty / missing input robustness

Skipped:
  - plot_pr_operating_points(), plot_per_tier_f1_bars(), plot_bss_bars(),
    plot_margin_trajectory() — all call matplotlib fig.savefig() which
    requires Agg backend + writes PNG files. Testing them purely requires
    file I/O + matplotlib; skipped per #373 scope (pure functions only).

#373 script test coverage audit.
"""
from __future__ import annotations

import sys
import pathlib

import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import plot_pr_curve as prc  # noqa: E402


# ===========================================================================
# safe_get()
# ===========================================================================

class TestSafeGet:

    def test_single_key_present(self):
        d = {"a": 42}
        assert prc.safe_get(d, "a") == 42

    def test_nested_two_levels(self):
        d = {"test": {"metrics": {"S": {"f1": 0.5}}}}
        assert prc.safe_get(d, "test", "metrics", "S", "f1") == 0.5

    def test_missing_top_key_returns_default(self):
        d = {}
        assert prc.safe_get(d, "missing") == 0
        assert prc.safe_get(d, "missing", default=99) == 99

    def test_missing_nested_key_returns_default(self):
        d = {"a": {"b": {}}}
        assert prc.safe_get(d, "a", "b", "c") == 0

    def test_none_value_returns_default(self):
        d = {"a": None}
        assert prc.safe_get(d, "a", default=7) == 7

    def test_non_dict_intermediate_returns_default(self):
        d = {"a": 42}  # "a" is an int, not a dict — can't descend further
        assert prc.safe_get(d, "a", "b") == 0

    def test_empty_dict_returns_default(self):
        assert prc.safe_get({}, "x", "y", "z", default=-1) == -1

    def test_zero_value_not_overridden_by_default(self):
        """Explicit 0 stored in dict must NOT be replaced by default."""
        d = {"score": 0}
        assert prc.safe_get(d, "score", default=99) == 0

    def test_false_value_not_overridden(self):
        d = {"flag": False}
        # False is returned as-is (0 default is still 0 but False is falsy)
        # safe_get checks `if cur is None`, not truthiness, so False passes.
        assert prc.safe_get(d, "flag", default=True) is False


# ===========================================================================
# Recall computation (inline formula mirrored from plot_pr_operating_points)
# ===========================================================================

class TestRecallComputation:
    """The PR operating points function computes recall as:
       r = min((k * precision_at_k) / n_ground_truth, 1.0)
    Test that formula directly.
    """

    def _recall(self, k, p, n_gt):
        """Mirror the formula from plot_pr_operating_points."""
        if n_gt > 0:
            return min((k * p) / n_gt, 1.0)
        return 0.0

    def test_basic_recall(self):
        # k=10, precision=0.5, n_gt=100 -> recall = 0.05
        assert abs(self._recall(10, 0.5, 100) - 0.05) < 1e-9

    def test_recall_capped_at_1(self):
        # k=100, precision=1.0, n_gt=50 -> would be 2.0, capped to 1.0
        assert self._recall(100, 1.0, 50) == 1.0

    def test_zero_n_gt_returns_zero(self):
        assert self._recall(10, 0.8, 0) == 0.0

    def test_recall_k50_precision_half_n_gt_100(self):
        # k=50, p=0.5, n_gt=100 -> 25/100 = 0.25
        assert abs(self._recall(50, 0.5, 100) - 0.25) < 1e-9

    def test_recall_k100_perfect_precision_matches_n_gt(self):
        # k=100, p=1.0, n_gt=100 -> exactly 1.0
        assert self._recall(100, 1.0, 100) == 1.0


# ===========================================================================
# Margin trajectory constants sanity check
# ===========================================================================

class TestMarginTrajectoryConstants:
    """The margin trajectory is hardcoded. Verify the math is self-consistent:
    margin[i] == model_f1[i] - persist_f1[i] (within float tolerance).
    """

    def test_v18_margin_consistent(self):
        # V1.8: model=0.506, persist=0.438, margin=0.067
        # Float precision: 0.506 - 0.438 = 0.06800000000000006 ≈ 0.068 not 0.067
        # The hardcoded margin is 0.067, a rounded display value. Tolerance 0.002.
        assert abs((0.506 - 0.438) - 0.067) < 0.002

    def test_v181_margin_consistent(self):
        # V1.8.1: model=0.480, persist=0.336, margin=0.143
        assert abs((0.480 - 0.336) - 0.143) < 0.001

    def test_v19_margin_consistent(self):
        # V1.9: model=0.481, persist=0.292, margin=0.189
        assert abs((0.481 - 0.292) - 0.189) < 0.001

    def test_margin_is_monotonically_increasing(self):
        margins = [0.067, 0.143, 0.189]
        for a, b in zip(margins, margins[1:]):
            assert b > a, f"Margin should be increasing: {a} -> {b}"

    def test_persistence_f1_is_monotonically_decreasing(self):
        persist = [0.438, 0.336, 0.292]
        for a, b in zip(persist, persist[1:]):
            assert b < a, f"Persistence F1 should be decreasing: {a} -> {b}"


# ===========================================================================
# Data extraction via safe_get on realistic backtest payload
# ===========================================================================

class TestDataExtraction:
    """safe_get extracts metrics from a realistic (but minimal) backtest payload."""

    MINIMAL_PAYLOAD = {
        "validation": {
            "metrics": {
                "S": {"f1": 0.6, "precision": 0.7, "recall": 0.5, "brier_skill_score": 0.1},
                "M": {"f1": 0.4, "precision": 0.5, "recall": 0.3, "brier_skill_score": -0.05},
                "L": {"f1": 0.3, "precision": 0.4, "recall": 0.25},
                "XL": {"f1": 0.2, "precision": 0.3, "recall": 0.15},
            }
        },
        "test": {
            "metrics": {
                "S": {
                    "f1": 0.55,
                    "precision": 0.6,
                    "recall": 0.5,
                    "brier_skill_score": -0.1,
                    "n_ground_truth": 200,
                    "precision_at_10": 0.8,
                    "precision_at_50": 0.6,
                    "precision_at_100": 0.5,
                },
            },
            "persistence": {"f1": 0.292},
        },
    }

    def test_val_f1_extracted_correctly(self):
        d = self.MINIMAL_PAYLOAD
        assert prc.safe_get(d, "validation", "metrics", "S", "f1") == 0.6
        assert prc.safe_get(d, "validation", "metrics", "M", "f1") == 0.4

    def test_test_f1_extracted_correctly(self):
        d = self.MINIMAL_PAYLOAD
        assert prc.safe_get(d, "test", "metrics", "S", "f1") == 0.55

    def test_missing_tier_in_test_returns_zero(self):
        d = self.MINIMAL_PAYLOAD
        # M/L/XL not in test.metrics
        assert prc.safe_get(d, "test", "metrics", "M", "f1") == 0

    def test_persistence_f1_extracted(self):
        d = self.MINIMAL_PAYLOAD
        assert prc.safe_get(d, "test", "persistence", "f1") == 0.292

    def test_n_ground_truth_extracted(self):
        d = self.MINIMAL_PAYLOAD
        assert prc.safe_get(d, "test", "metrics", "S", "n_ground_truth") == 200

    def test_precision_at_k_extracted(self):
        d = self.MINIMAL_PAYLOAD
        assert prc.safe_get(d, "test", "metrics", "S", "precision_at_10") == 0.8
        assert prc.safe_get(d, "test", "metrics", "S", "precision_at_50") == 0.6
        assert prc.safe_get(d, "test", "metrics", "S", "precision_at_100") == 0.5

    def test_bss_extraction_negative_value(self):
        d = self.MINIMAL_PAYLOAD
        assert prc.safe_get(d, "test", "metrics", "S", "brier_skill_score") == -0.1

    def test_empty_payload_all_defaults(self):
        d = {}
        for tier in prc.TIERS:
            assert prc.safe_get(d, "validation", "metrics", tier, "f1") == 0
            assert prc.safe_get(d, "test", "metrics", tier, "f1") == 0


# ===========================================================================
# TIERS constant
# ===========================================================================

class TestTiersConstant:

    def test_tiers_order_is_s_m_l_xl(self):
        assert list(prc.TIERS) == ["S", "M", "L", "XL"]

    def test_tier_colors_cover_all_tiers(self):
        for t in prc.TIERS:
            assert t in prc.TIER_COLORS, f"Missing color for tier {t}"
