"""Unit tests for scripts/validate_ml_model.py.

Stage 0 deliverable per docs/specs/internal/ops/ml-track/stage-0-pre-registration.md.

Synthesizes predictions + labels with known ground-truth properties and
verifies the Component 1/3/4/6 computation functions behave correctly:
    - Perfect ranking -> AUC = 1.0
    - Random ranking -> AUC ~ 0.5
    - Single-class labels -> AUC = NaN
    - Perfectly-calibrated predictions -> ECE -> 0
    - Anchor battery PASS/FAIL/SKIPPED logic per case shape
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_ml_model as v  # noqa: E402


# ---------- compute_auc ----------


def test_compute_auc_perfect_ranking_is_one():
    preds = np.array([0.1, 0.2, 0.3, 0.4])
    labels = np.array([0, 0, 1, 1])
    assert v.compute_auc(preds, labels) == 1.0


def test_compute_auc_inverted_ranking_is_zero():
    preds = np.array([0.4, 0.3, 0.2, 0.1])
    labels = np.array([0, 0, 1, 1])
    assert v.compute_auc(preds, labels) == 0.0


def test_compute_auc_random_is_around_half():
    rng = np.random.default_rng(0)
    preds = rng.random(2000)
    labels = rng.integers(0, 2, size=2000)
    auc = v.compute_auc(preds, labels)
    assert 0.45 < auc < 0.55


def test_compute_auc_single_class_returns_nan():
    preds = np.array([0.1, 0.2, 0.3])
    labels = np.array([1, 1, 1])
    assert np.isnan(v.compute_auc(preds, labels))


def test_compute_auc_handles_ties_correctly():
    """Tied predictions should average ranks per standard convention."""
    preds = np.array([0.5, 0.5, 0.5, 0.5])
    labels = np.array([0, 0, 1, 1])
    # With all-tied predictions, AUC is exactly 0.5 (no discrimination)
    assert v.compute_auc(preds, labels) == 0.5


def test_compute_auc_shape_mismatch_raises():
    with pytest.raises(ValueError, match="shape mismatch"):
        v.compute_auc(np.array([0.5, 0.5]), np.array([0, 1, 0]))


# ---------- bootstrap_auc_ci ----------


def test_bootstrap_auc_ci_is_deterministic_with_seed():
    rng = np.random.default_rng(42)
    preds = rng.random(100)
    labels = rng.integers(0, 2, size=100)
    r1 = v.bootstrap_auc_ci(preds, labels, n_bootstrap=200, seed=0)
    r2 = v.bootstrap_auc_ci(preds, labels, n_bootstrap=200, seed=0)
    assert r1["auc_point"] == r2["auc_point"]
    assert r1["auc_ci_low"] == r2["auc_ci_low"]
    assert r1["auc_ci_high"] == r2["auc_ci_high"]


def test_bootstrap_auc_ci_returns_required_fields():
    rng = np.random.default_rng(0)
    preds = rng.random(100)
    labels = rng.integers(0, 2, size=100)
    out = v.bootstrap_auc_ci(preds, labels, n_bootstrap=100, seed=0)
    for key in ("auc_point", "auc_ci_low", "auc_ci_high", "n", "n_bootstrap", "n_valid_resamples"):
        assert key in out


def test_bootstrap_auc_ci_perfect_signal_high_ci_low():
    """Perfect AUC -> bootstrap CI should be tight near 1.0."""
    preds = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    labels = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    out = v.bootstrap_auc_ci(preds, labels, n_bootstrap=200, seed=0)
    assert out["auc_point"] == 1.0
    assert out["auc_ci_low"] > 0.85  # very tight CI for perfect signal


def test_bootstrap_auc_ci_rejects_invalid_confidence():
    with pytest.raises(ValueError, match="confidence"):
        v.bootstrap_auc_ci(np.array([0.5]), np.array([1]), confidence=1.5)


def test_bootstrap_auc_ci_returns_delta_vs_baseline():
    """Per spec F2: 'AUC delta vs naive base-rate classifier' -- baseline_auc=0.5
    by default; impl returns delta_point + delta_ci_low/high."""
    preds = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    labels = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    out = v.bootstrap_auc_ci(preds, labels, n_bootstrap=200, seed=0, baseline_auc=0.5)
    assert out["baseline_auc"] == 0.5
    assert out["delta_point"] == out["auc_point"] - 0.5
    # CI on delta is just CI on AUC shifted by -0.5
    assert abs(out["delta_ci_low"] - (out["auc_ci_low"] - 0.5)) < 1e-9
    assert abs(out["delta_ci_high"] - (out["auc_ci_high"] - 0.5)) < 1e-9
    # Method recorded for Stage 1 BCa upgrade audit trail
    assert out["method"] == "percentile"


def test_bootstrap_auc_ci_custom_baseline():
    """Caller can compare to a backbone or multi-task v0 baseline AUC."""
    preds = np.array([0.1, 0.2, 0.8, 0.9])
    labels = np.array([0, 0, 1, 1])
    out = v.bootstrap_auc_ci(preds, labels, n_bootstrap=100, seed=0, baseline_auc=0.7)
    assert out["baseline_auc"] == 0.7
    assert abs(out["delta_point"] - (out["auc_point"] - 0.7)) < 1e-9


# ---------- compute_ece_and_reliability ----------


def test_ece_perfect_calibration_is_zero():
    """If predicted probability exactly equals observed rate per bin, ECE = 0."""
    # Construct: 100 samples per decile bin, observed rate matches midpoint
    preds = []
    labels = []
    for i in range(10):
        midpoint = (i + 0.5) / 10
        n_pos = int(midpoint * 100)
        preds.extend([midpoint] * 100)
        labels.extend([1] * n_pos + [0] * (100 - n_pos))
    out = v.compute_ece_and_reliability(np.array(preds), np.array(labels), n_bins=10)
    assert out["ece"] < 0.01


def test_ece_high_when_predictions_uniform_observed_imbalanced():
    """All preds 0.5 but actual base rate 0.1 -> per-bin |0.5-0.1| = 0.4."""
    preds = np.array([0.5] * 100)
    labels = np.array([1] * 10 + [0] * 90)
    out = v.compute_ece_and_reliability(preds, labels, n_bins=10)
    assert abs(out["ece"] - 0.4) < 0.01


def test_ece_reliability_diagram_has_n_bins():
    preds = np.linspace(0.0, 1.0, 100)
    labels = (preds > 0.5).astype(int)
    out = v.compute_ece_and_reliability(preds, labels, n_bins=10)
    assert len(out["reliability_diagram"]) == 10
    # Each bin has expected schema fields
    for b in out["reliability_diagram"]:
        for key in ("bin", "edge_low", "edge_high", "n", "predicted_mean", "observed_rate"):
            assert key in b


def test_ece_handles_empty_input():
    out = v.compute_ece_and_reliability(np.array([]), np.array([]), n_bins=10)
    assert np.isnan(out["ece"])


# ---------- compute_ece_bootstrap_diagnostic ----------


def test_ece_bootstrap_returns_distribution_summary():
    """Bootstrap diagnostic surfaces 25th/median/75th/95th/min/max + mean."""
    rng = np.random.default_rng(0)
    preds = rng.uniform(0, 1, size=200)
    labels = (rng.uniform(0, 1, size=200) < preds).astype(int)
    out = v.compute_ece_bootstrap_diagnostic(preds, labels, n_bootstrap=100, seed=0)
    for key in ("ece_bootstrap_mean", "ece_bootstrap_median",
                "ece_bootstrap_p25", "ece_bootstrap_p75",
                "ece_bootstrap_p95", "ece_bootstrap_min", "ece_bootstrap_max",
                "n_bootstrap", "n_valid_resamples", "method"):
        assert key in out
    # Distribution sanity: min <= p25 <= median <= p75 <= p95 <= max
    assert out["ece_bootstrap_min"] <= out["ece_bootstrap_p25"] <= out["ece_bootstrap_median"]
    assert out["ece_bootstrap_median"] <= out["ece_bootstrap_p75"] <= out["ece_bootstrap_p95"]
    assert out["ece_bootstrap_p95"] <= out["ece_bootstrap_max"]


def test_ece_bootstrap_deterministic_with_seed():
    """Same seed -> same bootstrap distribution summary."""
    preds = np.linspace(0.05, 0.95, 200)
    labels = (preds > 0.5).astype(int)
    a = v.compute_ece_bootstrap_diagnostic(preds, labels, n_bootstrap=50, seed=42)
    b = v.compute_ece_bootstrap_diagnostic(preds, labels, n_bootstrap=50, seed=42)
    assert a["ece_bootstrap_p75"] == b["ece_bootstrap_p75"]
    assert a["ece_bootstrap_mean"] == b["ece_bootstrap_mean"]


def test_ece_bootstrap_handles_empty_input():
    out = v.compute_ece_bootstrap_diagnostic(np.array([]), np.array([]), n_bootstrap=10)
    assert np.isnan(out["ece_bootstrap_p75"])
    assert out["n_valid_resamples"] == 0


def test_run_validation_includes_bootstrap_diagnostic_alongside_gate():
    """Founder tie-break compromise: gate uses in-sample ECE; diagnostic reported alongside.

    Asserts the happy path: a balanced 50-row sample with 20 resamples should
    produce 20 valid resamples (no degenerate single-class draws).
    """
    rng = np.random.default_rng(0)
    preds_list = []
    for i in range(50):
        preds_list.append({
            "country": f"c{i}", "year": 2024, "recipe_id": "test_recipe",
            "predicted_probability": float(rng.random()),
            "label": int(rng.integers(0, 2)),
        })
    out = v.run_validation(predictions=preds_list, anchor_battery=None,
                           n_bootstrap=20, seed=0)
    cal = out["components"]["calibration"]
    assert "per_recipe" in cal  # gate input (option a)
    assert "per_recipe_bootstrap_diagnostic" in cal  # diagnostic (option c)
    assert "gate_uses" in cal
    assert "in_sample_ece" in cal["gate_uses"]
    # Diagnostic has the bootstrap fields
    diag = cal["per_recipe_bootstrap_diagnostic"]["test_recipe"]
    assert "ece_bootstrap_p75" in diag
    # Happy-path resample count: 20 requested, 20 succeeded (balanced 50-row pool)
    assert diag["n_valid_resamples"] == 20


# ---------- compute_brier_decomposition ----------


def test_brier_decomposition_constant_prediction_at_base_rate():
    """If pred = base_rate everywhere, BS = uncertainty exactly.
    Resolution = 0 (no spread), reliability = 0 (perfect agreement)."""
    base_rate = 0.3
    n = 1000
    preds = np.array([base_rate] * n)
    labels = np.array([1] * 300 + [0] * 700)
    out = v.compute_brier_decomposition(preds, labels, n_bins=10)
    assert abs(out["brier_score"] - base_rate * (1 - base_rate)) < 0.01
    assert abs(out["uncertainty"] - base_rate * (1 - base_rate)) < 1e-9
    assert out["resolution"] < 0.01
    assert out["reliability"] < 0.01


def test_brier_decomposition_perfect_predictor_has_max_resolution():
    """Predictions = labels -> brier 0; resolution = uncertainty."""
    n = 1000
    preds = np.array([1.0] * 500 + [0.0] * 500)
    labels = np.array([1] * 500 + [0] * 500)
    out = v.compute_brier_decomposition(preds, labels, n_bins=10)
    assert out["brier_score"] < 0.01
    # Uncertainty = 0.5 * 0.5 = 0.25; resolution should equal uncertainty
    assert abs(out["resolution"] - 0.25) < 0.01
    assert out["reliability"] < 0.01


def test_brier_decomposition_handles_empty():
    out = v.compute_brier_decomposition(np.array([]), np.array([]), n_bins=10)
    assert np.isnan(out["brier_score"])


# ---------- evaluate_anchor_case ----------


def _mk_pred(country: str, year: int, recipe: str, p: float, label: int = 0) -> dict:
    return {"country": country, "year": year, "recipe_id": recipe,
            "predicted_probability": p, "label": label}


def test_evaluate_anchor_case_pass_when_country_in_band():
    """Production predictions use snake_case country slugs; anchor case carries
    country_slug; matching is on the slug."""
    case = {
        "id": 1, "country": "Malta", "country_slug": "malta",
        "recipe": "military_coup",
        "expected_rank_band": [0.0, 0.30],
    }
    preds = [_mk_pred("malta", 2020, "military_coup", 0.05)]
    preds += [_mk_pred(f"c{i}", 2020, "military_coup", 0.5 + i * 0.01) for i in range(50)]
    out = v.evaluate_anchor_case(case, preds)
    assert out["status"] == "PASS"
    assert out["observed_percentile"] < 0.30


def test_evaluate_anchor_case_fail_when_country_outside_band():
    case = {
        "id": 1, "country": "Malta", "country_slug": "malta",
        "recipe": "military_coup",
        "expected_rank_band": [0.0, 0.30],
    }
    # Malta gets a high prediction (above 30th percentile)
    preds = [_mk_pred("malta", 2020, "military_coup", 0.95)]
    preds += [_mk_pred(f"c{i}", 2020, "military_coup", i * 0.005) for i in range(50)]
    out = v.evaluate_anchor_case(case, preds)
    assert out["status"] == "FAIL"
    assert out["observed_percentile"] > 0.30


def test_evaluate_anchor_case_skipped_when_no_predictions_for_recipe():
    case = {
        "id": 99, "country": "Mars", "recipe": "no_such_recipe",
        "expected_rank_band": [0.0, 0.30],
    }
    out = v.evaluate_anchor_case(case, [_mk_pred("Mars", 2020, "other_recipe", 0.5)])
    assert out["status"] == "SKIPPED"


def test_evaluate_anchor_case_skipped_when_country_not_in_predictions():
    case = {
        "id": 1, "country": "Atlantis", "recipe": "civil_war_and_insurgency",
        "expected_rank_band": [0.0, 0.30],
    }
    out = v.evaluate_anchor_case(case, [_mk_pred("Norway", 2020, "civil_war_and_insurgency", 0.1)])
    assert out["status"] == "SKIPPED"


def test_evaluate_anchor_case_year_window_filters():
    case = {
        "id": 5, "country": "Sri Lanka", "recipe": "economic_recession",
        "year_window": [2022, 2022], "expected_rank_band": [0.5, 1.0],
    }
    # Sri Lanka in 2022 is high; in 2018 is low (filtered out by window)
    preds = [
        _mk_pred("Sri Lanka", 2022, "economic_recession", 0.95),
        _mk_pred("Sri Lanka", 2018, "economic_recession", 0.05),
    ]
    preds += [_mk_pred(f"c{i}", 2022, "economic_recession", i * 0.005) for i in range(50)]
    out = v.evaluate_anchor_case(case, preds)
    assert out["status"] == "PASS"


def test_evaluate_anchor_case_sentinel_returns_deferred():
    case = {
        "id": 3, "country": "Norway",
        "recipe_sentinel": "any_conflict_category",
        "resolves_to_layer1": "B",
        "expected_rank_band": [0.0, 0.20],
    }
    preds = [_mk_pred("Norway", 2020, "civil_war_and_insurgency", 0.1)]
    out = v.evaluate_anchor_case(case, preds)
    assert out["status"] == "DEFERRED_TO_STAGE_1"


def test_evaluate_anchor_case_rank_stability_not_yet_implemented():
    """Venezuela case 6 (rank stability) requires multi-version comparison;
    documented as NOT_YET_IMPLEMENTED in v1, not silently SKIPPED."""
    case = {
        "id": 6, "country": "Venezuela", "recipe": "economic_recession",
        "expected_rank_volatility_max": 0.10,
        # No expected_rank_band
    }
    out = v.evaluate_anchor_case(case, [])
    assert out["status"] == "NOT_YET_IMPLEMENTED"
    assert out["expected_rank_volatility_max"] == 0.10
    assert "multi-version" in out["reason"]


def test_evaluate_anchor_case_multi_row_window_takes_mean(caplog):
    """When a country appears multiple times in a multi-year window, take
    mean probability + log a warning so Stage 1 can confirm aggregation choice."""
    case = {
        "id": 99, "country": "Venezuela", "recipe": "economic_recession",
        "year_window": [2018, 2020],  # multi-year
        "expected_rank_band": [0.5, 1.0],
    }
    preds = [
        _mk_pred("Venezuela", 2018, "economic_recession", 0.6),
        _mk_pred("Venezuela", 2019, "economic_recession", 0.8),
        _mk_pred("Venezuela", 2020, "economic_recession", 0.9),
    ] + [_mk_pred(f"c{i}", 2019, "economic_recession", i * 0.005) for i in range(50)]
    with caplog.at_level("WARNING", logger="validate_ml_model"):
        out = v.evaluate_anchor_case(case, preds)
    # Should use mean probability across Venezuela's 3 rows
    assert out["country_prob_aggregation"] == "mean"
    assert abs(out["country_prob"] - (0.6 + 0.8 + 0.9) / 3) < 1e-9
    # Warning emitted
    assert any("3 prediction rows" in r.message for r in caplog.records)


# ---------- evaluate_anchor_battery ----------


def test_evaluate_anchor_battery_separates_active_and_deferred():
    battery = {
        "active_cases": [{
            "id": 2, "country": "Iceland", "recipe": "civil_war_and_insurgency",
            "expected_rank_band": [0.0, 0.30],
        }],
        "deferred_cases": [{
            "id": 1, "country": "Malta", "recipe": "military_coup",
            "deferred_reason": "hard-gated",
        }],
    }
    preds = [
        _mk_pred("Iceland", 2020, "civil_war_and_insurgency", 0.05),
    ] + [_mk_pred(f"c{i}", 2020, "civil_war_and_insurgency", 0.5 + i * 0.01) for i in range(20)]
    out = v.evaluate_anchor_battery(preds, battery)
    assert out["n_active"] == 1
    assert out["n_active_pass"] == 1
    assert out["n_deferred_by_hard_gate"] == 1
    assert out["deferred"][0]["status"] == "DEFERRED_BY_HARD_GATE"


def test_evaluate_anchor_battery_handles_empty_battery():
    out = v.evaluate_anchor_battery([], {"active_cases": [], "deferred_cases": []})
    assert out["n_active"] == 0


# ---------- run_validation orchestrator ----------


def test_run_validation_emits_full_payload_shape():
    rng = np.random.default_rng(0)
    preds_list = []
    for recipe in ("a", "b"):
        for i in range(50):
            preds_list.append({
                "country": f"c{i}",
                "year": 2024,
                "recipe_id": recipe,
                "predicted_probability": float(rng.random()),
                "label": int(rng.integers(0, 2)),
            })
    out = v.run_validation(predictions=preds_list, anchor_battery=None, n_bootstrap=50, seed=0)
    assert out["schema_version"] == 1
    assert out["n_predictions"] == 100
    assert out["n_recipes"] == 2
    for recipe in ("a", "b"):
        assert recipe in out["components"]["oos_by_time"]["per_recipe"]
        assert recipe in out["components"]["calibration"]["per_recipe"]
        assert recipe in out["components"]["brier"]["per_recipe"]
        assert recipe in out["components"]["recipe_counts"]["per_recipe"]
    assert out["components"]["anchor_battery"] is None  # no anchors passed
    assert "recipe_counts" in out["components"]  # canonical completeness check


def test_run_validation_includes_recipe_counts_with_n_pos_test():
    """recipe_counts per-recipe section surfaces n_pos_test for F5 rubric."""
    preds_list = [
        # Recipe `r1`: 12 positives out of 30 → above F5 hard gate (>= 8)
        *(
            {"country": f"c{i}", "year": 2024, "recipe_id": "r1",
             "predicted_probability": 0.5, "label": (1 if i < 12 else 0)}
            for i in range(30)
        ),
        # Recipe `r2`: 5 positives out of 20 → below F5 hard gate
        *(
            {"country": f"c{i}", "year": 2024, "recipe_id": "r2",
             "predicted_probability": 0.5, "label": (1 if i < 5 else 0)}
            for i in range(20)
        ),
    ]
    out = v.run_validation(predictions=preds_list, anchor_battery=None, n_bootstrap=10, seed=0)
    counts = out["components"]["recipe_counts"]["per_recipe"]
    assert counts["r1"]["n_pos_test"] == 12
    assert counts["r1"]["n_test"] == 30
    assert counts["r1"]["n_neg_test"] == 18
    assert counts["r1"]["positive_rate"] == pytest.approx(12 / 30)
    assert counts["r2"]["n_pos_test"] == 5
    assert counts["r2"]["n_test"] == 20
    # purpose string mentions F5 hard gate threshold for downstream readability.
    assert "F5" in out["components"]["recipe_counts"]["purpose"]
    assert "n_pos" in out["components"]["recipe_counts"]["purpose"]


def test_run_validation_includes_anchors_when_provided():
    preds = [
        {"country": "Iceland", "year": 2024, "recipe_id": "civil_war_and_insurgency",
         "predicted_probability": 0.05, "label": 0},
    ] + [
        {"country": f"c{i}", "year": 2024, "recipe_id": "civil_war_and_insurgency",
         "predicted_probability": 0.5 + i * 0.01, "label": 0}
        for i in range(20)
    ]
    battery = {
        "active_cases": [{
            "id": 2, "country": "Iceland", "recipe": "civil_war_and_insurgency",
            "expected_rank_band": [0.0, 0.30],
        }],
        "deferred_cases": [],
    }
    out = v.run_validation(predictions=preds, anchor_battery=battery, n_bootstrap=20, seed=0)
    assert out["components"]["anchor_battery"]["n_active"] == 1


# ---------- New REPORTED-only predictive metrics (founder ratification 2026-05-05) ----------


class TestComputeAucPr:
    def test_perfect_ranking_returns_1(self):
        preds = np.array([0.1, 0.2, 0.8, 0.9])
        labels = np.array([0, 0, 1, 1])
        assert v.compute_auc_pr(preds, labels) == pytest.approx(1.0)

    def test_inverse_ranking_low_ap(self):
        preds = np.array([0.9, 0.8, 0.2, 0.1])
        labels = np.array([0, 0, 1, 1])
        # AP for inverse ranking is base rate (= 0.5 here for 50/50)
        ap = v.compute_auc_pr(preds, labels)
        assert ap < 0.6

    def test_random_ap_near_base_rate(self):
        rng = np.random.default_rng(0)
        n = 1000
        preds = rng.random(n)
        labels = rng.integers(0, 2, n)
        ap = v.compute_auc_pr(preds, labels)
        base_rate = labels.mean()
        # AP for random predictions ≈ base rate
        assert abs(ap - base_rate) < 0.10

    def test_no_positives_returns_nan(self):
        assert np.isnan(v.compute_auc_pr(np.array([0.1, 0.5]), np.array([0, 0])))

    def test_empty_returns_nan(self):
        assert np.isnan(v.compute_auc_pr(np.array([]), np.array([])))

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="shape mismatch"):
            v.compute_auc_pr(np.array([0.1, 0.2]), np.array([0, 0, 1]))

    def test_imbalanced_class_handles_correctly(self):
        # 5 positives in 100 → base rate 0.05; perfect signal
        labels = np.zeros(100, dtype=int)
        labels[-5:] = 1
        preds = labels.astype(float) * 0.9 + 0.05
        ap = v.compute_auc_pr(preds, labels)
        assert ap > 0.95


class TestComputeLogLoss:
    def test_perfect_predictions(self):
        preds = np.array([0.001, 0.001, 0.999, 0.999])
        labels = np.array([0, 0, 1, 1])
        ll = v.compute_log_loss(preds, labels)
        # Near-perfect predictions yield very small log loss
        assert ll < 0.01

    def test_constant_at_50_pct(self):
        preds = np.full(100, 0.5)
        labels = np.array([0] * 50 + [1] * 50)
        ll = v.compute_log_loss(preds, labels)
        # log(0.5) for both classes = log(2) ≈ 0.693
        assert ll == pytest.approx(np.log(2.0), abs=1e-6)

    def test_confident_wrong_high_loss(self):
        preds = np.array([0.99, 0.99, 0.01, 0.01])
        labels = np.array([0, 0, 1, 1])
        ll = v.compute_log_loss(preds, labels)
        # Confidently wrong → log loss should be very high
        assert ll > 4.0

    def test_clipping_prevents_inf(self):
        # Predictions of exactly 0 or 1 with wrong label would give -inf without clipping
        preds = np.array([0.0, 1.0])
        labels = np.array([1, 0])  # both confidently wrong
        ll = v.compute_log_loss(preds, labels)
        assert np.isfinite(ll)
        assert ll > 30  # near log(1e15) ≈ 34.5

    def test_empty_returns_nan(self):
        assert np.isnan(v.compute_log_loss(np.array([]), np.array([])))

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="shape mismatch"):
            v.compute_log_loss(np.array([0.1]), np.array([0, 1]))


class TestComputeBrierSkillScore:
    def test_perfect_predictions_bss_1(self):
        preds = np.array([0.0, 0.0, 1.0, 1.0])
        labels = np.array([0, 0, 1, 1])
        assert v.compute_brier_skill_score(preds, labels) == pytest.approx(1.0)

    def test_constant_at_base_rate_bss_0(self):
        # Always predict 0.5 with 50/50 labels: Brier = 0.25 = uncertainty
        preds = np.full(10, 0.5)
        labels = np.array([0] * 5 + [1] * 5)
        bss = v.compute_brier_skill_score(preds, labels)
        # BSS = 1 - (0.25 / 0.25) = 0.0
        assert bss == pytest.approx(0.0)

    def test_worse_than_baseline_negative_bss(self):
        # Inverse-correlated predictions: very wrong
        preds = np.array([0.99, 0.99, 0.01, 0.01])
        labels = np.array([0, 0, 1, 1])
        bss = v.compute_brier_skill_score(preds, labels)
        # base_rate=0.5, baseline brier = 0.25; model brier ≈ 0.97; BSS ≈ -2.88
        assert bss < -2.0

    def test_all_one_class_returns_nan(self):
        preds = np.array([0.5, 0.5, 0.5])
        labels = np.array([0, 0, 0])  # all-zero → base_rate=0 → undefined
        assert np.isnan(v.compute_brier_skill_score(preds, labels))

    def test_empty_returns_nan(self):
        assert np.isnan(v.compute_brier_skill_score(np.array([]), np.array([])))


class TestComputeAnchorDriftMetrics:
    def _make_anchor_results(self, *cases):
        return {"active": list(cases), "deferred": [],
                "n_active": len(cases), "n_active_pass": 0,
                "n_active_fail": 0, "n_active_skipped": 0,
                "n_active_deferred_to_stage_1": 0,
                "n_active_not_yet_implemented": 0}

    def test_all_pass_yields_perfect_ahi(self):
        cases = [
            {"id": 1, "status": "PASS", "observed_percentile": 0.85,
             "expected_rank_band": [0.75, 1.0]},
            {"id": 2, "status": "PASS", "observed_percentile": 0.10,
             "expected_rank_band": [0.0, 0.30]},
        ]
        out = v.compute_anchor_drift_metrics(self._make_anchor_results(*cases))
        assert out["ads"] == 0.0
        assert out["ahr"] == 1.0
        assert out["ahi"] == 1.0
        assert out["n_evaluable"] == 2

    def test_one_fail_below_band(self):
        cases = [
            {"id": 1, "status": "FAIL", "observed_percentile": 0.10,
             "expected_rank_band": [0.75, 1.0]},  # drift = -0.65
        ]
        out = v.compute_anchor_drift_metrics(self._make_anchor_results(*cases))
        assert out["ads"] == pytest.approx(0.65)
        assert out["ahr"] == 0.0
        assert out["ahi"] == 0.0
        assert out["per_case_drifts"][0]["signed_drift"] == pytest.approx(-0.65)

    def test_mixed_pass_fail_composite(self):
        cases = [
            {"id": 1, "status": "PASS", "observed_percentile": 0.85,
             "expected_rank_band": [0.75, 1.0]},  # drift = 0
            {"id": 2, "status": "FAIL", "observed_percentile": 0.50,
             "expected_rank_band": [0.0, 0.30]},  # drift = +0.20
            {"id": 3, "status": "PASS", "observed_percentile": 0.20,
             "expected_rank_band": [0.0, 0.30]},  # drift = 0
            {"id": 4, "status": "FAIL", "observed_percentile": 0.10,
             "expected_rank_band": [0.75, 1.0]},  # drift = -0.65
        ]
        out = v.compute_anchor_drift_metrics(self._make_anchor_results(*cases))
        # ADS = mean of (0, 0.20, 0, 0.65) = 0.2125
        assert out["ads"] == pytest.approx(0.2125)
        # AHR = 2/4 = 0.5
        assert out["ahr"] == pytest.approx(0.5)
        # AHI = 0.5 * (1 - 0.2125) = 0.39375
        assert out["ahi"] == pytest.approx(0.5 * (1 - 0.2125))

    def test_deferred_and_nyi_excluded(self):
        cases = [
            {"id": 1, "status": "PASS", "observed_percentile": 0.85,
             "expected_rank_band": [0.75, 1.0]},
            {"id": 2, "status": "DEFERRED_TO_STAGE_1"},
            {"id": 3, "status": "NOT_YET_IMPLEMENTED"},
            {"id": 4, "status": "SKIPPED"},
        ]
        out = v.compute_anchor_drift_metrics(self._make_anchor_results(*cases))
        assert out["n_evaluable"] == 1
        assert out["n_excluded_non_evaluable"] == 3
        assert out["ahi"] == 1.0

    def test_no_evaluable_returns_nan(self):
        cases = [{"id": 1, "status": "DEFERRED_TO_STAGE_1"}]
        out = v.compute_anchor_drift_metrics(self._make_anchor_results(*cases))
        assert np.isnan(out["ads"])
        assert np.isnan(out["ahr"])
        assert np.isnan(out["ahi"])

    def test_invalid_input_yields_nan(self):
        out = v.compute_anchor_drift_metrics(None)
        assert np.isnan(out["ads"])

    def test_pp_units_in_output(self):
        cases = [
            {"id": 1, "status": "FAIL", "observed_percentile": 0.50,
             "expected_rank_band": [0.0, 0.30]},  # drift = +0.20 = 20pp
        ]
        out = v.compute_anchor_drift_metrics(self._make_anchor_results(*cases))
        assert out["ads_pct_pp"] == pytest.approx(20.0)
        assert out["ahr_pct"] == 0.0


def test_run_validation_includes_predictive_metrics_and_anchor_drift():
    """Verifies the new components.predictive_metrics + components.
    anchor_drift_metrics sections are emitted by run_validation."""
    rng = np.random.default_rng(0)
    preds_list = [
        {"country": f"c{i}", "year": 2024, "recipe_id": "r1",
         "predicted_probability": float(rng.random()),
         "label": int(rng.integers(0, 2))}
        for i in range(50)
    ]
    battery = {
        "active_cases": [{
            "id": 99, "country": "c0", "recipe": "r1",
            "expected_rank_band": [0.0, 0.30],
        }],
        "deferred_cases": [],
    }
    out = v.run_validation(predictions=preds_list, anchor_battery=battery,
                           n_bootstrap=10, seed=0)
    # New predictive metrics section
    assert "predictive_metrics" in out["components"]
    pm = out["components"]["predictive_metrics"]["per_recipe"]["r1"]
    assert "auc_pr" in pm
    assert "brier_skill_score" in pm
    assert "log_loss" in pm
    # New anchor drift section
    assert "anchor_drift_metrics" in out["components"]
    adm = out["components"]["anchor_drift_metrics"]
    assert "ads" in adm
    assert "ahr" in adm
    assert "ahi" in adm
