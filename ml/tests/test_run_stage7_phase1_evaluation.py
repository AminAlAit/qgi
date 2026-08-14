"""Unit tests for Stage 7 phase-1 evaluation driver pure functions.

End-to-end smoke testing is via the --max-positives flag at the script
level (manual run; not in CI). These tests cover the pure helpers
(AUC, bootstrap CI, ECE, cohort lookup, JSON serialization, tier
determination) that any end-to-end run depends on.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_stage7_phase1_evaluation as drv


def test_compute_auc_simple_perfect_separation():
    probs = np.array([0.9, 0.8, 0.1, 0.2])
    labels = np.array([1, 1, 0, 0])
    assert drv.compute_auc_simple(probs, labels) == 1.0


def test_compute_auc_simple_no_separation():
    probs = np.array([0.5, 0.5, 0.5, 0.5])
    labels = np.array([1, 1, 0, 0])
    assert drv.compute_auc_simple(probs, labels) == 0.5


def test_compute_auc_simple_single_class_returns_nan():
    probs = np.array([0.9, 0.8])
    labels = np.array([1, 1])
    assert np.isnan(drv.compute_auc_simple(probs, labels))


def test_bootstrap_loco_auc_ci_returns_well_formed():
    rng = np.random.default_rng(0)
    probs = np.concatenate([rng.uniform(0.6, 1.0, 50), rng.uniform(0.0, 0.4, 50)])
    labels = np.concatenate([np.ones(50, dtype=int), np.zeros(50, dtype=int)])
    out = drv.bootstrap_loco_auc_ci(probs, labels, n_bootstrap=200, seed=42)
    assert {"auc", "ci80_lo", "ci80_hi", "ci95_lo", "ci95_hi"} == set(out)
    assert 0.0 <= out["ci95_lo"] <= out["ci80_lo"] <= out["auc"]
    assert out["auc"] <= out["ci80_hi"] <= out["ci95_hi"] <= 1.0


def test_compute_ece_well_calibrated_is_low():
    rng = np.random.default_rng(0)
    n = 1000
    probs = rng.uniform(0.0, 1.0, n)
    labels = rng.binomial(1, probs)
    ece = drv.compute_ece(probs, labels)
    assert 0.0 <= ece <= 0.10


def test_compute_ece_miscalibrated_is_high():
    probs = np.full(100, 0.9)
    labels = np.zeros(100, dtype=int)
    ece = drv.compute_ece(probs, labels)
    assert ece >= 0.5


def test_per_cohort_ece_title_case_normalization():
    cohort_assignments = {
        "Afghanistan": {"2017": "fragile-state", "2018": "fragile-state"},
        "Sweden": {"2017": "stable-democracy"},
    }
    probs = np.array([0.7, 0.6, 0.3])
    labels = np.array([1, 1, 0])
    countries = np.array(["afghanistan", "afghanistan", "sweden"])
    years = np.array([2017, 2018, 2017])
    out = drv.per_cohort_ece(probs, labels, countries, years, cohort_assignments)
    assert out["fragile-state"]["n"] == 2
    assert out["stable-democracy"]["n"] == 1
    assert out["mid-tier"]["n"] == 0


def test_to_strict_json_replaces_nan():
    payload = {"a": float("nan"), "b": 1.0, "c": {"d": float("inf"), "e": [1.0, float("nan")]}}
    s = drv._to_strict_json(payload)
    parsed = json.loads(s)
    assert parsed["a"] is None
    assert parsed["b"] == 1.0
    assert parsed["c"]["d"] is None
    assert parsed["c"]["e"] == [1.0, None]


def _mk_recipe_result(
    rid: str,
    *,
    loco_with: float,
    loco_with_ci95_lo: float = 0.5,
    delta_vs_hybrid: float | None,
    per_recipe_pass_strict: bool,
    per_recipe_pass_loose: bool,
    f_s_2_fail: bool,
    f_s_3_contributes: bool,
    f_s_3_excluded_reason: str | None = None,
) -> dict:
    return {
        "recipe_id": rid,
        "loco_with_shape": {"auc": loco_with, "ci95_lo": loco_with_ci95_lo},
        "delta_vs_hybrid_baseline": delta_vs_hybrid,
        "f_s_1": {
            "per_recipe_pass_strict": per_recipe_pass_strict,
            "per_recipe_pass_loose": per_recipe_pass_loose,
        },
        "f_s_2": {"fail": f_s_2_fail},
        "f_s_3": {
            "contributes": f_s_3_contributes,
            "excluded_reason": f_s_3_excluded_reason,
        },
        "f_s_4": {"status": "deferred"},
    }


def test_determine_tier_pure_pass():
    cohort_results = {
        "civil_war_and_insurgency": _mk_recipe_result(
            "civil_war_and_insurgency",
            loco_with=0.85,
            delta_vs_hybrid=0.12,
            per_recipe_pass_strict=True,
            per_recipe_pass_loose=True,
            f_s_2_fail=False,
            f_s_3_contributes=True,
        ),
        "economic_recession": _mk_recipe_result(
            "economic_recession",
            loco_with=0.72,
            delta_vs_hybrid=None,
            per_recipe_pass_strict=True,
            per_recipe_pass_loose=True,
            f_s_2_fail=False,
            f_s_3_contributes=True,
        ),
    }
    verdict = drv.determine_tier(cohort_results)
    assert verdict["final_tier"] == "PASS"
    assert verdict["f_s_1_pass"] is True
    assert verdict["f_s_3_pass"] is True


def test_determine_tier_hard_falsify_when_no_lift():
    cohort_results = {
        "civil_war_and_insurgency": _mk_recipe_result(
            "civil_war_and_insurgency",
            loco_with=0.65,
            delta_vs_hybrid=-0.10,
            per_recipe_pass_strict=False,
            per_recipe_pass_loose=False,
            f_s_2_fail=True,
            f_s_3_contributes=False,
        ),
        "economic_recession": _mk_recipe_result(
            "economic_recession",
            loco_with=0.55,
            delta_vs_hybrid=None,
            per_recipe_pass_strict=False,
            per_recipe_pass_loose=False,
            f_s_2_fail=True,
            f_s_3_contributes=False,
        ),
    }
    verdict = drv.determine_tier(cohort_results)
    assert verdict["final_tier"] == "HARD-FALSIFY"
    assert verdict["f_s_1_pass"] is False


def test_determine_tier_f_s_1_n2_strictest_reading_both_must_clear():
    """QA review B1 regression guard.

    Per the N=2 strictest reading of pre-reg §5.2: BOTH recipes must
    clear 0.05 for loose pass, not 1 of 2. Asymmetric pattern (one
    recipe clears, the other does not) must NOT trigger F-S-1 pass.
    """
    cohort_results = {
        "civil_war_and_insurgency": _mk_recipe_result(
            "civil_war_and_insurgency",
            loco_with=0.85,
            delta_vs_hybrid=0.08,
            per_recipe_pass_strict=True,
            per_recipe_pass_loose=True,
            f_s_2_fail=False,
            f_s_3_contributes=True,
        ),
        "economic_recession": _mk_recipe_result(
            "economic_recession",
            loco_with=0.6,
            delta_vs_hybrid=None,
            per_recipe_pass_strict=False,
            per_recipe_pass_loose=False,
            f_s_2_fail=False,
            f_s_3_contributes=True,
        ),
    }
    verdict = drv.determine_tier(cohort_results)
    assert verdict["f_s_1_pass"] is False


def test_determine_tier_econ_recession_excluded_when_below_rescue():
    """QA review B3 regression guard.

    econ_recession with ablation Δ ≥ 0.03 BUT WITH-shape below rescue
    floor must NOT count as F-S-3 contributor. Pre-reg §5.4 special clause.
    """
    cohort_results = {
        "civil_war_and_insurgency": _mk_recipe_result(
            "civil_war_and_insurgency",
            loco_with=0.85,
            delta_vs_hybrid=0.10,
            per_recipe_pass_strict=True,
            per_recipe_pass_loose=True,
            f_s_2_fail=False,
            f_s_3_contributes=True,
        ),
        "economic_recession": _mk_recipe_result(
            "economic_recession",
            loco_with=0.55,
            delta_vs_hybrid=None,
            per_recipe_pass_strict=False,
            per_recipe_pass_loose=False,
            f_s_2_fail=False,
            f_s_3_contributes=False,
            f_s_3_excluded_reason="ablation-positive-but-below-rescue",
        ),
    }
    verdict = drv.determine_tier(cohort_results)
    assert verdict["f_s_3_contributors"] == 1
    assert verdict["f_s_3_pass"] is True


def test_determine_tier_partial_when_one_recipe_regresses():
    """Per QA B4 fix: F-S-2 fail in 1/N (not all) → PARTIAL, not FALSIFIED."""
    cohort_results = {
        "civil_war_and_insurgency": _mk_recipe_result(
            "civil_war_and_insurgency",
            loco_with=0.85,
            delta_vs_hybrid=0.10,
            per_recipe_pass_strict=True,
            per_recipe_pass_loose=True,
            f_s_2_fail=False,
            f_s_3_contributes=True,
        ),
        "economic_recession": _mk_recipe_result(
            "economic_recession",
            loco_with=0.72,
            delta_vs_hybrid=None,
            per_recipe_pass_strict=True,
            per_recipe_pass_loose=True,
            f_s_2_fail=True,
            f_s_3_contributes=True,
        ),
    }
    verdict = drv.determine_tier(cohort_results)
    assert "PARTIAL" in verdict["routing_from_f_rules"]
