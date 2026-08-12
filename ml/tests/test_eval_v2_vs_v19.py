"""Tests for the V2.0-vs-V1.9.1 eval harness (#463 Part C).

The eval framework is what gates the V2.0 frontend cutover (#466).
Wrong math here means wrong shipping decisions — pin every metric +
the decision rule with explicit cases.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

# Make the script importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from eval_v2_vs_v19 import (  # noqa: E402
    ScoringMetrics,
    brier_score,
    evaluate_decision_rule,
    precision_at_k,
    recall_at_k,
)


# ---------------------------------------------------------------------------
# precision_at_k
# ---------------------------------------------------------------------------

class TestPrecisionAtK:
    def test_all_correct_in_top_k(self):
        # Top-3 are all positives → precision = 1.0
        assert precision_at_k([True, True, True, False, False], 3) == 1.0

    def test_none_correct_in_top_k(self):
        assert precision_at_k([False, False, False, True, True], 3) == 0.0

    def test_partial_top_k(self):
        # 2 of 3 in top-3 are positives
        assert precision_at_k([True, True, False, False, True], 3) == pytest_approx(2 / 3)

    def test_k_larger_than_list(self):
        # K=10 on a 3-element list → uses all 3
        assert precision_at_k([True, False, True], 10) == pytest_approx(2 / 3)

    def test_empty_list(self):
        assert precision_at_k([], 5) == 0.0

    def test_k_zero(self):
        assert precision_at_k([True, True, True], 0) == 0.0


# ---------------------------------------------------------------------------
# recall_at_k
# ---------------------------------------------------------------------------

class TestRecallAtK:
    def test_all_positives_in_top_k(self):
        # 3 positives total, all in top-3 → recall = 1.0
        assert recall_at_k([True, True, True, False, False], 3) == 1.0

    def test_no_positives_anywhere(self):
        # No positives in the data → recall undefined → 0.0
        assert recall_at_k([False, False, False], 3) == 0.0

    def test_some_positives_outside_top_k(self):
        # 4 positives total, 2 in top-3 → recall = 2/4 = 0.5
        assert recall_at_k([True, True, False, True, True], 3) == 0.5

    def test_k_larger_than_list(self):
        # 2 positives, all in top-K → recall = 1.0
        assert recall_at_k([True, False, True], 10) == 1.0

    def test_empty_list(self):
        assert recall_at_k([], 5) == 0.0


# ---------------------------------------------------------------------------
# brier_score
# ---------------------------------------------------------------------------

class TestBrierScore:
    def test_perfect_predictions(self):
        # y_pred matches y_true exactly → Brier = 0
        assert brier_score([True, False, True], [1.0, 0.0, 1.0]) == 0.0

    def test_completely_wrong_predictions(self):
        # All flipped → Brier = 1.0
        assert brier_score([True, False], [0.0, 1.0]) == 1.0

    def test_uncertain_predictions(self):
        # 0.5 prediction on every outcome → Brier = 0.25
        assert brier_score([True, False, True, False], [0.5, 0.5, 0.5, 0.5]) == 0.25

    def test_empty_returns_nan(self):
        assert math.isnan(brier_score([], []))


# ---------------------------------------------------------------------------
# evaluate_decision_rule
# ---------------------------------------------------------------------------

def _metrics(system, p10=0.0, brier=1.0, margin=0.0, notes=""):
    """Helper: build a ScoringMetrics with the dimensions the rule cares about."""
    return ScoringMetrics(
        system=system,
        precision_at_10=p10,
        precision_at_50=p10,  # mirror p10 for simplicity unless overridden
        precision_at_100=p10,
        recall_at_10=0.0,
        recall_at_50=0.0,
        recall_at_100=0.0,
        brier_score=brier,
        margin_over_persistence=margin,
        n_predictions=100,
        coverage=1.0,
        notes=notes,
    )


class TestDecisionRule:
    def test_v20_better_on_precision_keeps_persistence_passes(self):
        persistence = _metrics("persistence", p10=0.5, brier=0.3, margin=0.0)
        v19 = _metrics("V1.9.1", p10=0.6, brier=0.25, margin=0.1)
        v20 = _metrics("V2.0", p10=0.7, brier=0.25, margin=0.1)
        passed, _ = evaluate_decision_rule(persistence, v19, v20)
        assert passed is True

    def test_v20_better_on_calibration_only_passes(self):
        persistence = _metrics("persistence", p10=0.5, brier=0.3, margin=0.0)
        v19 = _metrics("V1.9.1", p10=0.6, brier=0.25, margin=0.1)
        v20 = _metrics("V2.0", p10=0.6, brier=0.20, margin=0.1)
        passed, expl = evaluate_decision_rule(persistence, v19, v20)
        assert passed is True
        assert "calibration improved" in expl

    def test_v20_worse_on_persistence_fails(self):
        persistence = _metrics("persistence", p10=0.5, brier=0.3, margin=0.0)
        v19 = _metrics("V1.9.1", p10=0.6, brier=0.25, margin=0.1)
        v20 = _metrics("V2.0", p10=0.9, brier=0.10, margin=0.05)  # margin worse
        passed, expl = evaluate_decision_rule(persistence, v19, v20)
        assert passed is False
        assert "persistence margin" in expl

    def test_v20_no_improvement_fails(self):
        persistence = _metrics("persistence", p10=0.5, brier=0.3, margin=0.0)
        v19 = _metrics("V1.9.1", p10=0.6, brier=0.25, margin=0.1)
        v20 = _metrics("V2.0", p10=0.6, brier=0.25, margin=0.1)  # no change
        passed, _ = evaluate_decision_rule(persistence, v19, v20)
        assert passed is False

    def test_v20_pending_nan_fails(self):
        # Pending V2.0 with NaN metrics — must fail (don't ship a stub).
        persistence = _metrics("persistence", p10=0.5, brier=0.3, margin=0.0)
        v19 = _metrics("V1.9.1", p10=0.6, brier=0.25, margin=0.1)
        v20 = _metrics(
            "V2.0",
            p10=float("nan"), brier=float("nan"), margin=float("nan"),
            notes="PENDING",
        )
        passed, expl = evaluate_decision_rule(persistence, v19, v20)
        assert passed is False
        assert "PENDING" in expl


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def pytest_approx(expected, rel=1e-9, abs=1e-9):
    """Tiny pytest.approx replacement for environments without pytest available."""
    import pytest
    return pytest.approx(expected, rel=rel, abs=abs)
