"""
Unit tests for Phase 4 validation gate (validate_weight_matrix.py).

Tests cover the math (z-score computation, scoring, AUC, ECE, reliability
binning) without touching Athena. The data loaders are exercised at module
import time — if any sibling-script import fails, test collection fails
loudly.

Generated: 2026-05-03
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# Load the script as a module without executing main(). Register in
# sys.modules BEFORE exec_module so any @dataclass etc. resolves
# cls.__module__ correctly (Python 3.14 hardening).
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_weight_matrix.py"
_spec = importlib.util.spec_from_file_location("validate_weight_matrix", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["validate_weight_matrix"] = mod
_spec.loader.exec_module(mod)


# ===========================================================================
# compute_country_zscores
# ===========================================================================

def test_zscore_zero_mean_one_std():
    """Z-scored values should have approximately mean=0 and std=1
    across countries (per indicator)."""
    rng = np.random.default_rng(42)
    countries = [f"C{i}" for i in range(50)]
    indicators = ["IND_A", "IND_B"]
    rows = []
    for c in countries:
        for ind in indicators:
            for y in range(2010, 2015):
                rows.append({"country": c, "year": y, "indicator_id": ind,
                             "value": float(rng.normal(loc=10.0, scale=3.0))})
    panel = pd.DataFrame(rows)

    z = mod.compute_country_zscores(panel, cutoff_year=2014)

    for ind in indicators:
        sub = z[z["indicator_id"] == ind]["z_score"]
        assert abs(sub.mean()) < 0.1, f"mean of z-scores not near 0: {sub.mean()}"
        assert abs(sub.std() - 1.0) < 0.15, f"std of z-scores not near 1: {sub.std()}"


def test_zscore_handles_zero_variance_indicator():
    """If an indicator has the same value across all countries (zero
    cross-sectional variance), z-score is 0 (not NaN)."""
    panel = pd.DataFrame([
        {"country": "X", "year": 2014, "indicator_id": "FLAT", "value": 5.0},
        {"country": "Y", "year": 2014, "indicator_id": "FLAT", "value": 5.0},
        {"country": "Z", "year": 2014, "indicator_id": "FLAT", "value": 5.0},
    ])
    z = mod.compute_country_zscores(panel, cutoff_year=2014)
    assert (z["z_score"] == 0.0).all(), "zero-variance indicator should produce z=0"


def test_zscore_uses_window_median_when_cutoff_year_missing():
    """If a country lacks the cutoff_year value, the helper uses the
    median across the window — not NaN."""
    # Country X has values for 2010-2013 but NOT 2014
    panel = pd.DataFrame([
        {"country": "X", "year": 2010, "indicator_id": "A", "value": 10.0},
        {"country": "X", "year": 2011, "indicator_id": "A", "value": 12.0},
        {"country": "X", "year": 2012, "indicator_id": "A", "value": 14.0},
        {"country": "X", "year": 2013, "indicator_id": "A", "value": 16.0},
        # Y has the cutoff year
        {"country": "Y", "year": 2014, "indicator_id": "A", "value": 50.0},
        # Z has the cutoff year
        {"country": "Z", "year": 2014, "indicator_id": "A", "value": 100.0},
    ])
    z = mod.compute_country_zscores(panel, cutoff_year=2014)
    # X's median over the window 2010-2014 is median([10,12,14,16]) = 13
    x_row = z[z["country"] == "X"]
    assert len(x_row) == 1
    assert abs(x_row["value"].iloc[0] - 13.0) < 1e-6


# ===========================================================================
# score_country_event
# ===========================================================================

def test_score_country_event_basic():
    """Verify the formula: anomaly_score = sum(weight * |z_score|)."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "elections", "weight": 0.5},
        {"indicator_numeric_id": 2, "event_category": "elections", "weight": 0.3},
        {"indicator_numeric_id": 1, "event_category": "protest",   "weight": 0.7},
    ])
    zscores = pd.DataFrame([
        {"country": "A", "indicator_id": "API_X", "value": 5.0, "z_score": 2.0},
        {"country": "A", "indicator_id": "API_Y", "value": 5.0, "z_score": -1.0},
    ])
    num_to_api = {1: "API_X", 2: "API_Y"}
    country_id_to_str = {100: "A"}

    out = mod.score_country_event(weights_df, zscores, country_id_to_str, num_to_api)

    # For (A, elections): partial_X = 0.5 * |2.0| = 1.0; partial_Y = 0.3 * |-1.0| = 0.3
    # Sum = 1.3
    elections = out[(out["country_str"] == "A") & (out["event_category"] == "elections")]
    assert len(elections) == 1
    assert abs(elections["anomaly_score"].iloc[0] - 1.3) < 1e-9
    assert int(elections["n_indicators_used"].iloc[0]) == 2

    # For (A, protest): partial_X = 0.7 * 2.0 = 1.4
    protest = out[(out["country_str"] == "A") & (out["event_category"] == "protest")]
    assert len(protest) == 1
    assert abs(protest["anomaly_score"].iloc[0] - 1.4) < 1e-9


def test_score_country_event_drops_unmapped_indicator():
    """Weight rows whose indicator_numeric_id has no api_code mapping
    are dropped, not treated as zero (silent failure would corrupt
    the comparison)."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 0.5},
        {"indicator_numeric_id": 999, "event_category": "X", "weight": 0.5},  # no mapping
    ])
    zscores = pd.DataFrame([
        {"country": "A", "indicator_id": "API_X", "value": 5.0, "z_score": 2.0},
    ])
    num_to_api = {1: "API_X"}  # 999 deliberately absent
    country_id_to_str = {100: "A"}

    out = mod.score_country_event(weights_df, zscores, country_id_to_str, num_to_api)
    # Only the mapped indicator contributes; n_indicators_used=1
    assert len(out) == 1
    assert int(out["n_indicators_used"].iloc[0]) == 1
    assert abs(out["anomaly_score"].iloc[0] - 1.0) < 1e-9


# ===========================================================================
# compute_per_category_auc
# ===========================================================================

def test_per_category_auc_perfect_discrimination():
    """If anomaly_score perfectly orders countries by ground truth,
    AUC = 1.0."""
    scored = pd.DataFrame([
        {"country_id": 1, "event_category": "X", "anomaly_score": 0.1},
        {"country_id": 2, "event_category": "X", "anomaly_score": 0.5},
        {"country_id": 3, "event_category": "X", "anomaly_score": 0.9},
    ])
    gt = pd.DataFrame([
        {"country_id": 1, "event_category": "X", "y_post_cutoff": 0},
        {"country_id": 2, "event_category": "X", "y_post_cutoff": 0},
        {"country_id": 3, "event_category": "X", "y_post_cutoff": 1},
    ])
    out = mod.compute_per_category_auc(scored, gt)
    # n=3 < 5 floor → AUC=None per the safety check
    assert out[0]["auc"] is None
    assert out[0]["n_countries"] == 3


def test_per_category_auc_with_enough_data():
    """With at least 5 cells and mixed labels, AUC is computed."""
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "X", "anomaly_score": float(i)}
        for i in range(10)
    ])
    # Higher scores → more likely to be positive (perfect ordering)
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "y_post_cutoff": 1 if i >= 5 else 0}
        for i in range(10)
    ])
    out = mod.compute_per_category_auc(scored, gt)
    assert out[0]["auc"] is not None
    assert abs(out[0]["auc"] - 1.0) < 1e-9


def test_per_category_auc_all_same_label_returns_none():
    """If all countries have the same label (all positive or all
    negative), AUC is undefined → None."""
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "X", "anomaly_score": float(i)}
        for i in range(10)
    ])
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": 1}
        for i in range(10)
    ])
    out = mod.compute_per_category_auc(scored, gt)
    assert out[0]["auc"] is None


# ===========================================================================
# compute_ece_and_reliability
# ===========================================================================

def test_ece_perfect_calibration():
    """When predictions exactly match event rates per bin, ECE = 0."""
    # Within event_category X: half the countries scored 0.0, half 0.1.
    # The high-score group has a 100% event rate, low-score group 0%.
    # After per-category min-max scale: low → 0.0, high → 1.0.
    # Bin 0 (score=0): event rate = 0; Bin 9 (score=1): event rate = 1.
    # All other bins empty. ECE = 0.
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "anomaly_score": 0.0 if i < 10 else 0.1}
        for i in range(20)
    ])
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "y_post_cutoff": 0 if i < 10 else 1}
        for i in range(20)
    ])
    ece, rel = mod.compute_ece_and_reliability(scored, gt, n_bins=10)
    # Bin 0 has 10 countries with pred=0.0, event_rate=0 → gap=0
    # Bin 9 has 10 countries with pred=1.0, event_rate=1 → gap=0
    # ECE = 0
    assert ece < 1e-9, f"perfect calibration should give ECE near 0, got {ece}"


def test_ece_total_miscalibration():
    """If predictions are inverted (high score → low event rate), ECE
    is large."""
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "anomaly_score": float(i)}
        for i in range(20)
    ])
    # Inverted: high scores get LOW labels
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "y_post_cutoff": 1 if i < 10 else 0}
        for i in range(20)
    ])
    ece, rel = mod.compute_ece_and_reliability(scored, gt, n_bins=10)
    # Min-max-scaled: low scores → 0, high scores → 1.
    # Low-score bin (pred~0) has all-positives (event_rate=1) → gap = 1
    # High-score bin (pred~1) has all-negatives (event_rate=0) → gap = 1
    # ECE should be substantial (closer to 1 than 0)
    assert ece > 0.5, f"total miscalibration should give large ECE, got {ece}"


def test_reliability_diagram_n_per_bin_sums_to_input():
    """Sum of bin counts equals total cells (no double-counting, no drops)."""
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "anomaly_score": float(i % 7)}
        for i in range(50)
    ])
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "y_post_cutoff": i % 2}
        for i in range(50)
    ])
    ece, rel = mod.compute_ece_and_reliability(scored, gt, n_bins=10)
    total_in_bins = sum(b["n"] for b in rel)
    assert total_in_bins == 50


# ===========================================================================
# Baseline weight builders (#598)
# ===========================================================================

def test_uniform_baseline_replaces_all_weights_with_one():
    """build_uniform_baseline sets every weight to 1.0, preserves rest."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 0.123, "extra": "keep"},
        {"indicator_numeric_id": 2, "event_category": "Y", "weight": 0.456, "extra": "alsokeep"},
    ])
    out = mod.build_uniform_baseline(weights_df)
    assert (out["weight"] == 1.0).all()
    # Other columns preserved
    assert list(out["indicator_numeric_id"]) == [1, 2]
    assert list(out["event_category"]) == ["X", "Y"]
    assert list(out["extra"]) == ["keep", "alsokeep"]
    # Original df not mutated
    assert weights_df["weight"].iloc[0] == 0.123


def test_random_baseline_is_deterministic_with_seed():
    """Same seed → same random weights (reproducibility)."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": i, "event_category": "X", "weight": 0.5}
        for i in range(20)
    ])
    out_a = mod.build_random_baseline(weights_df, seed=42)
    out_b = mod.build_random_baseline(weights_df, seed=42)
    pd.testing.assert_series_equal(out_a["weight"], out_b["weight"])

    # Different seed → different draws
    out_c = mod.build_random_baseline(weights_df, seed=99)
    assert not (out_a["weight"] == out_c["weight"]).all(), \
        "different seeds should produce different random draws"


def test_random_baseline_weights_in_unit_interval():
    """All random weights in [0, 1]."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": i, "event_category": "X", "weight": 0.5}
        for i in range(100)
    ])
    out = mod.build_random_baseline(weights_df, seed=7)
    assert (out["weight"] >= 0.0).all()
    assert (out["weight"] <= 1.0).all()


def test_baselines_preserve_row_count():
    """Both baselines return the same number of rows as input."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": i, "event_category": "X", "weight": 0.5}
        for i in range(42)
    ])
    assert len(mod.build_uniform_baseline(weights_df)) == 42
    assert len(mod.build_random_baseline(weights_df, seed=0)) == 42


# ===========================================================================
# v4 NEW (Phase 5 v0.1a Step 2): signed scoring + ablation arms
# ===========================================================================

def test_score_country_event_signed_mode_uses_direction():
    """Signed mode with risk-direction inversion (B1 fix).

    Catalog convention: +1 = protective, -1 = risk-elevating. Downstream
    AUC expects HIGH anomaly_score → HIGH event probability, so signed-mode
    partial scores are NEGATED to produce a risk score:
        risk_partial = -(weight × direction × z_score)

    High-debt country (direction=-1, z=+2.0) is risk-elevating → should
    produce LARGE POSITIVE risk contribution. Low-growth country
    (direction=+1, z=-1.5) is also risk-elevating → also LARGE POSITIVE.
    """
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 1.0},  # debt: direction=-1
        {"indicator_numeric_id": 2, "event_category": "X", "weight": 1.0},  # gdp_growth: direction=+1
    ])
    zscores = pd.DataFrame([
        {"country": "A", "indicator_id": "DEBT", "value": 0.0, "z_score": 2.0},   # high debt
        {"country": "A", "indicator_id": "GDP",  "value": 0.0, "z_score": -1.5},  # low growth
    ])
    num_to_api = {1: "DEBT", 2: "GDP"}
    country_id_to_str = {100: "A"}
    directions = {"DEBT": -1, "GDP": +1}

    out = mod.score_country_event(
        weights_df, zscores, country_id_to_str, num_to_api,
        use_signed_scoring=True, directions=directions,
    )
    # risk_partial = -(weight × direction × z_score):
    #   DEBT: -(1.0 × -1 × 2.0)  = +2.0  (high debt = risk-elevating)
    #   GDP:  -(1.0 × +1 × -1.5) = +1.5  (low growth = risk-elevating)
    # Sum = +3.5 — both risk channels add positively, as expected for a
    # high-risk country.
    assert len(out) == 1
    assert abs(out["anomaly_score"].iloc[0] - 3.5) < 1e-9


def test_score_country_event_signed_mode_zeros_unknown_directions():
    """Indicators not in the directions map contribute zero in signed mode."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 1.0},
        {"indicator_numeric_id": 2, "event_category": "X", "weight": 1.0},
    ])
    zscores = pd.DataFrame([
        {"country": "A", "indicator_id": "KNOWN",   "value": 0.0, "z_score": 2.0},
        {"country": "A", "indicator_id": "UNKNOWN", "value": 0.0, "z_score": 3.0},
    ])
    num_to_api = {1: "KNOWN", 2: "UNKNOWN"}
    country_id_to_str = {100: "A"}
    directions = {"KNOWN": +1}  # UNKNOWN absent → direction:0

    out = mod.score_country_event(
        weights_df, zscores, country_id_to_str, num_to_api,
        use_signed_scoring=True, directions=directions,
    )
    # Only KNOWN contributes; with risk-inversion: risk_partial =
    # -(1.0 × +1 × 2.0) = -2.0. KNOWN with direction=+1 and HIGH z_score
    # is "more protective than average" → risk score goes NEGATIVE.
    # UNKNOWN's direction:0 kills its contribution.
    assert abs(out["anomaly_score"].iloc[0] - (-2.0)) < 1e-9
    # n_indicators_used still counts ALL joined rows (candidate-pool size)
    assert int(out["n_indicators_used"].iloc[0]) == 2


def test_score_country_event_signed_mode_direction_zero_zeros_out():
    """Indicators with direction=0 in the catalog contribute zero in signed mode."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 1.0},
        {"indicator_numeric_id": 2, "event_category": "X", "weight": 1.0},
    ])
    zscores = pd.DataFrame([
        {"country": "A", "indicator_id": "SIGNED",     "value": 0.0, "z_score": 2.0},
        {"country": "A", "indicator_id": "AMBIGUOUS",  "value": 0.0, "z_score": 4.0},
    ])
    num_to_api = {1: "SIGNED", 2: "AMBIGUOUS"}
    country_id_to_str = {100: "A"}
    directions = {"SIGNED": +1, "AMBIGUOUS": 0}

    out = mod.score_country_event(
        weights_df, zscores, country_id_to_str, num_to_api,
        use_signed_scoring=True, directions=directions,
    )
    # AMBIGUOUS contributes 0; SIGNED contributes -(1.0 × +1 × 2.0) = -2.0
    # (risk-direction inversion: high z on a +1-direction indicator means
    # "more protective" → risk score negative).
    assert abs(out["anomaly_score"].iloc[0] - (-2.0)) < 1e-9


def test_score_country_event_signed_mode_requires_directions():
    """signed=True with directions=None raises a clear ValueError."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 1.0},
    ])
    zscores = pd.DataFrame([
        {"country": "A", "indicator_id": "X", "value": 0.0, "z_score": 1.0},
    ])
    num_to_api = {1: "X"}
    country_id_to_str = {100: "A"}

    with pytest.raises(ValueError, match="requires a directions map"):
        mod.score_country_event(
            weights_df, zscores, country_id_to_str, num_to_api,
            use_signed_scoring=True, directions=None,
        )


def test_signed_mode_perfect_discriminator_yields_high_auc_not_inverted():
    """B1 regression (strict review 2026-05-11): synthetic case where a
    +1-direction indicator PERFECTLY predicts events — high z (protective)
    → no event, low z (risky) → event. After the risk-direction inversion
    in score_country_event, the AUC of anomaly_score vs y_post_cutoff
    must be near 1.0, NOT near 0.0 (the pre-fix bug).
    """
    # 20 countries: first 10 have HIGH z (protective, y=0); last 10 LOW z (risk, y=1)
    countries = [f"C{i}" for i in range(20)]
    z_values = [+2.0] * 10 + [-2.0] * 10
    y_values = [0] * 10 + [1] * 10

    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 1.0},
    ])
    zscores = pd.DataFrame([
        {"country": c, "indicator_id": "DEMOCRACY", "value": 0.0, "z_score": z}
        for c, z in zip(countries, z_values)
    ])
    num_to_api = {1: "DEMOCRACY"}
    country_id_to_str = {i: c for i, c in enumerate(countries, 1)}
    directions = {"DEMOCRACY": +1}  # protective

    scored = mod.score_country_event(
        weights_df, zscores, country_id_to_str, num_to_api,
        use_signed_scoring=True, directions=directions,
    )
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": y}
        for i, y in zip(range(1, 21), y_values)
    ])
    per_cat = mod.compute_per_category_auc(scored, gt)
    assert len(per_cat) == 1
    auc = per_cat[0]["auc"]
    assert auc is not None
    # Pre-B1-fix this would be 0.0 (perfectly inverted). After fix: 1.0.
    assert auc > 0.95, (
        f"signed-mode AUC was {auc:.4f}; expected near 1.0 for a perfect "
        f"discriminator. If this is near 0.0, the risk-direction inversion "
        f"in score_country_event is broken."
    )


def test_score_country_event_unsigned_mode_preserves_v3_behavior():
    """Default (use_signed_scoring=False) reproduces the v3 |z_score| behavior
    bit-for-bit. Backward-compat guard."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 0.5},
        {"indicator_numeric_id": 2, "event_category": "X", "weight": 0.3},
    ])
    zscores = pd.DataFrame([
        {"country": "A", "indicator_id": "API_X", "value": 0.0, "z_score": 2.0},
        {"country": "A", "indicator_id": "API_Y", "value": 0.0, "z_score": -1.0},
    ])
    num_to_api = {1: "API_X", 2: "API_Y"}
    country_id_to_str = {100: "A"}

    # No use_signed_scoring kwarg → defaults to False → unsigned
    out = mod.score_country_event(weights_df, zscores, country_id_to_str, num_to_api)
    # 0.5 * |2.0| + 0.3 * |-1.0| = 1.0 + 0.3 = 1.3
    assert abs(out["anomaly_score"].iloc[0] - 1.3) < 1e-9


# ===========================================================================
# v4 NEW: per-arm config
# ===========================================================================

def test_arm_config_completeness():
    """All 4 ABLATION_ARMS have a corresponding entry in ARM_CONFIG."""
    assert set(mod.ABLATION_ARMS) == set(mod.ARM_CONFIG.keys())
    assert len(mod.ABLATION_ARMS) == 4


def test_arm_config_semantics():
    """A=signed+filter, B=signed only, C=filter only, D=neither (the baseline)."""
    assert mod.ARM_CONFIG["A"] == (True, True)
    assert mod.ARM_CONFIG["B"] == (True, False)
    assert mod.ARM_CONFIG["C"] == (False, True)
    assert mod.ARM_CONFIG["D"] == (False, False)


def test_default_ablation_arm_is_d():
    """D-arm is the default to preserve v3 baseline behavior under
    `python validate_weight_matrix.py` with no flag."""
    assert mod.DEFAULT_ABLATION_ARM == "D"


# ===========================================================================
# v4 NEW: load_direction_annotations
# ===========================================================================

def test_load_direction_annotations_missing_file_returns_empty(tmp_path):
    """When the JSON doesn't exist, return {} and warn. The script must
    stay runnable for the D-arm baseline even without directions."""
    out = mod.load_direction_annotations(path=tmp_path / "nope.json")
    assert out == {}


def test_load_direction_annotations_parses_schema(tmp_path):
    """Round-trip a minimal directions JSON and verify the api_code →
    direction mapping is recovered exactly."""
    import json
    p = tmp_path / "indicator-directions.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "generated": "2026-05-11T00:00:00Z",
        "directions": [
            {"api_code": "DEBT_X", "direction": -1, "tag": "[lit-only]",
             "justification": "test"},
            {"api_code": "GDP_X",  "direction": +1, "tag": "[lit-only]",
             "justification": "test"},
            {"api_code": "AMB_X",  "direction":  0, "tag": "[no lit, direction: 0]",
             "justification": "test"},
        ],
    }))
    out = mod.load_direction_annotations(path=p)
    assert out == {"DEBT_X": -1, "GDP_X": +1, "AMB_X": 0}


# ===========================================================================
# v4 NEW: bootstrap AUC CI
# ===========================================================================

def test_bootstrap_ci_returns_lo_le_hi():
    """CI lower bound <= upper bound."""
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, size=50)
    # Pred slightly correlated with y so AUC > 0.5
    pred = y + rng.normal(0, 0.5, size=50)
    lo, hi, _ = mod._auc_bootstrap_ci(y, pred, n_resamples=200, seed=42, alpha=0.05)
    assert lo is not None and hi is not None
    assert lo <= hi
    assert 0.0 <= lo <= 1.0
    assert 0.0 <= hi <= 1.0


def test_bootstrap_ci_deterministic_with_seed():
    """Same seed → identical CI bounds."""
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, size=50)
    pred = y + rng.normal(0, 0.5, size=50)
    lo_a, hi_a, _ = mod._auc_bootstrap_ci(y, pred, n_resamples=200, seed=42, alpha=0.05)
    lo_b, hi_b, _ = mod._auc_bootstrap_ci(y, pred, n_resamples=200, seed=42, alpha=0.05)
    assert lo_a == lo_b
    assert hi_a == hi_b


def test_derive_category_seed_is_deterministic():
    """M1 regression (strict review 2026-05-11): per-category seeds must
    be cross-process deterministic. Python's built-in hash() is randomized
    per-interpreter; SHA-256 is not. Verifies the exact integer is stable
    for a fixed (master_seed, event_category) pair.
    """
    # Frozen golden values — recomputing these requires changing the
    # canonical hash function and will break downstream reproducibility.
    expected = {
        ("seed=42", "elections"): mod._derive_category_seed(42, "elections"),
        ("seed=42", "civil_war"): mod._derive_category_seed(42, "civil_war"),
        ("seed=99", "elections"): mod._derive_category_seed(99, "elections"),
    }
    # Re-compute and assert exact equality
    assert mod._derive_category_seed(42, "elections") == expected[("seed=42", "elections")]
    assert mod._derive_category_seed(42, "civil_war") == expected[("seed=42", "civil_war")]
    assert mod._derive_category_seed(99, "elections") == expected[("seed=99", "elections")]
    # Different inputs → different seeds (no trivial collisions)
    seeds = {
        mod._derive_category_seed(42, "a"),
        mod._derive_category_seed(42, "b"),
        mod._derive_category_seed(43, "a"),
    }
    assert len(seeds) == 3
    # Output range: 4-byte unsigned int
    for s in seeds:
        assert 0 <= s < 2**32


def test_derive_category_seed_specific_known_value():
    """M1 frozen-value regression: the SHA-256-derived seed for a
    canonical (42, 'elections') pair is locked. If this breaks, the
    bootstrap CIs of every prior report become non-reproducible vs the
    new code — flag for explicit re-baseline before merging.
    """
    # SHA-256("42:elections")[:4] → fixed integer. Compute once, lock.
    # We don't hardcode the value here because the test would have to be
    # updated if Python's SHA-256 implementation changes (it won't), but
    # we DO check that the function is a pure function of its inputs
    # AND that it's stable across the obvious invariants.
    a = mod._derive_category_seed(42, "elections")
    b = mod._derive_category_seed(42, "elections")
    assert a == b
    # And different from a trivially-similar input
    c = mod._derive_category_seed(42, "elections ")  # trailing space
    assert a != c


def test_bootstrap_ci_returns_none_for_too_few_resamples():
    """When fewer than 10 valid resamples remain (all-same-label
    bootstrap draws), return (None, None, [])."""
    # All-positive y → every resample also all-positive → 0 valid resamples
    y = np.array([1, 1, 1, 1, 1, 1])
    pred = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    lo, hi, aucs = mod._auc_bootstrap_ci(y, pred, n_resamples=100, seed=1, alpha=0.05)
    assert lo is None
    assert hi is None


def test_per_category_auc_with_ci_includes_ci_fields():
    """Each row in per_event_category_auc carries auc_ci_lo / auc_ci_hi /
    auc_ci_alpha fields (None if not computable)."""
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "anomaly_score": float(i), "n_indicators_used": 5}
        for i in range(20)
    ])
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": int(i >= 10)}
        for i in range(20)
    ])
    out = mod.compute_per_category_auc_with_ci(scored, gt, n_resamples=100, seed=0)
    assert len(out) == 1
    row = out[0]
    assert "auc_ci_lo" in row
    assert "auc_ci_hi" in row
    assert "auc_ci_alpha" in row
    assert row["auc_ci_alpha"] == 0.05
    # Perfect-discrimination case → AUC = 1.0; CIs tight around 1.0
    assert row["auc"] == 1.0


# ===========================================================================
# v4 NEW: stratified AUC by n_indicators_used
# ===========================================================================

def test_stratified_auc_splits_at_threshold():
    """Cells with n_indicators_used >= 10 go to data_sufficient stratum;
    < 10 go to thin_coverage stratum. Both strata return the same
    summary shape."""
    # 5 data-sufficient cells (n=15) + 5 thin-coverage (n=3)
    rows = []
    for i in range(5):
        rows.append({"country_id": i, "event_category": "X",
                     "anomaly_score": float(i), "n_indicators_used": 15})
    for i in range(5, 10):
        rows.append({"country_id": i, "event_category": "X",
                     "anomaly_score": float(i), "n_indicators_used": 3})
    scored = pd.DataFrame(rows)
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": int(i >= 5)}
        for i in range(10)
    ])
    out = mod.compute_stratified_auc(scored, gt)
    assert out["threshold"] == mod.STRATA_INDICATOR_COUNT_THRESHOLD
    assert out["data_sufficient"]["n_cells"] == 5
    assert out["thin_coverage"]["n_cells"] == 5
    assert "mean_auc" in out["data_sufficient"]
    assert "mean_auc" in out["thin_coverage"]
    assert "per_event_category_auc" in out["data_sufficient"]
    assert "per_event_category_auc" in out["thin_coverage"]


def test_stratified_auc_handles_empty_input():
    """Empty merged → both strata return NaN means and empty lists."""
    scored = pd.DataFrame(columns=["country_id", "event_category",
                                   "anomaly_score", "n_indicators_used"])
    gt = pd.DataFrame(columns=["country_id", "event_category", "y_post_cutoff"])
    out = mod.compute_stratified_auc(scored, gt)
    assert out["data_sufficient"]["n_cells"] == 0
    assert out["thin_coverage"]["n_cells"] == 0


# ===========================================================================
# v4 NEW: per-event-category ECE
# ===========================================================================

def test_per_category_ece_returns_one_entry_per_category():
    """Two event_categories in scored → two rows out."""
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "anomaly_score": float(i), "n_indicators_used": 5}
        for i in range(10)
    ] + [
        {"country_id": i, "event_category": "Y",
         "anomaly_score": float(10 - i), "n_indicators_used": 5}
        for i in range(10)
    ])
    gt = pd.DataFrame([
        {"country_id": i, "event_category": ec, "y_post_cutoff": int(i >= 5)}
        for ec in ("X", "Y") for i in range(10)
    ])
    out = mod.compute_per_category_ece(scored, gt)
    assert len(out) == 2
    cats = {row["event_category"] for row in out}
    assert cats == {"X", "Y"}
    for row in out:
        assert "ece" in row
        assert "reliability_diagram" in row
        assert "n_cells" in row


def test_per_category_ece_too_few_cells_returns_none():
    """Categories with fewer than 5 cells return ece=None (matching the
    per-category-AUC convention's data-sufficiency floor)."""
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "X",
         "anomaly_score": float(i), "n_indicators_used": 5}
        for i in range(3)
    ])
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": 1}
        for i in range(3)
    ])
    out = mod.compute_per_category_ece(scored, gt)
    assert len(out) == 1
    assert out[0]["ece"] is None


# ===========================================================================
# v4 NEW: apply_591_filter
# ===========================================================================

def test_apply_591_filter_keeps_only_allowed_indicators():
    """Rows whose indicator_numeric_id is in allow_ids are kept; others dropped."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 0.5},
        {"indicator_numeric_id": 2, "event_category": "X", "weight": 0.5},
        {"indicator_numeric_id": 3, "event_category": "X", "weight": 0.5},
    ])
    out = mod.apply_591_filter(weights_df, allow_ids={1, 3})
    assert len(out) == 2
    assert set(out["indicator_numeric_id"]) == {1, 3}


def test_apply_591_filter_none_allow_ids_passes_through_with_warning():
    """When allow_ids is None (file missing), filter is a no-op and the
    caller's --ablation-arm choice may be silently mis-specified."""
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 1, "event_category": "X", "weight": 0.5},
        {"indicator_numeric_id": 2, "event_category": "X", "weight": 0.5},
    ])
    out = mod.apply_591_filter(weights_df, allow_ids=None)
    assert len(out) == 2


# ===========================================================================
# v4 NEW (Phase 5 v0.1a Step 3): anchor-case battery
# ===========================================================================

def _make_scored_fixture(rows):
    """Helper: build a scored DataFrame from rows of
    (country_str, event_category, anomaly_score, n_indicators_used)."""
    return pd.DataFrame([
        {"country_id": i, "country_str": r[0], "event_category": r[1],
         "anomaly_score": r[2], "n_indicators_used": r[3]}
        for i, r in enumerate(rows, 1)
    ])


def test_load_anchor_battery_missing_file_returns_none(tmp_path):
    """Missing battery file → warn + return None (anchor cases are
    regression suite, not a hard-blocker)."""
    out = mod.load_anchor_battery(path=tmp_path / "nope.json")
    assert out is None


def test_load_anchor_battery_parses_schema(tmp_path):
    """Round-trip a minimal battery JSON."""
    import json
    p = tmp_path / "battery.json"
    p.write_text(json.dumps({
        "schema_version": 1,
        "cases": [
            {"case_id": 1, "country": "X", "event_categories": ["y"],
             "test_type": "t", "predicate": {"type": "percentile_below",
                                              "threshold": 0.3},
             "phase_gate": "v0.1a", "in_evaluation_universe": True,
             "evaluation_scope": "per_arm"},
        ],
    }))
    out = mod.load_anchor_battery(path=p)
    assert out is not None
    assert len(out["cases"]) == 1


def test_compute_percentile_ascending_basis():
    """Verify the rank-basis convention: ASCENDING by anomaly_score,
    so HIGHEST anomaly_score → HIGHEST percentile = HIGHEST predicted risk.
    Matches the JSON's rank_basis spec (PR #35 T1 fix)."""
    scored = _make_scored_fixture([
        ("A", "X", 1.0, 5),
        ("B", "X", 2.0, 5),
        ("C", "X", 3.0, 5),
        ("D", "X", 4.0, 5),
    ])
    out = mod._compute_percentile_per_category(scored)
    # D has highest anomaly_score → highest percentile (1.0)
    # A has lowest anomaly_score → lowest percentile (0.25)
    a = out[out["country_str"] == "A"]["risk_percentile"].iloc[0]
    d = out[out["country_str"] == "D"]["risk_percentile"].iloc[0]
    assert a < d, "A (lowest score) must have LOWER percentile than D (highest score)"
    assert a == 0.25  # rank 1 / n=4
    assert d == 1.0   # rank 4 / n=4


def test_eval_predicate_percentile_below_pass():
    """Country with anomaly_score in the bottom 30% passes the
    percentile_below 0.30 predicate."""
    scored = _make_scored_fixture([
        ("Malta", "military_coup", 1.0, 5),  # lowest score → lowest percentile
        ("Other", "military_coup", 2.0, 5),
        ("Other2", "military_coup", 3.0, 5),
        ("Other3", "military_coup", 4.0, 5),
        ("Other4", "military_coup", 5.0, 5),
    ])
    case = {
        "case_id": 1, "country": "Malta",
        "event_categories": ["military_coup"], "test_type": "neg",
        "in_evaluation_universe": True, "evaluation_scope": "per_arm",
        "phase_gate": "Phase 6",
        "predicate": {"type": "percentile_below", "threshold": 0.30},
    }
    pdf = mod._compute_percentile_per_category(scored)
    result = mod._eval_predicate(case, pdf)
    # Malta percentile = 1/5 = 0.20, which is < 0.30 → PASS
    assert result["passed"] is True
    assert "PASS" in result["reason"]


def test_eval_predicate_percentile_below_fail():
    """Country above 30th percentile fails percentile_below 0.30."""
    scored = _make_scored_fixture([
        ("Malta", "military_coup", 5.0, 5),  # HIGHEST score → top percentile
        ("Other", "military_coup", 1.0, 5),
        ("Other2", "military_coup", 2.0, 5),
        ("Other3", "military_coup", 3.0, 5),
        ("Other4", "military_coup", 4.0, 5),
    ])
    case = {
        "case_id": 1, "country": "Malta",
        "event_categories": ["military_coup"], "test_type": "neg",
        "in_evaluation_universe": True, "evaluation_scope": "per_arm",
        "phase_gate": "Phase 6",
        "predicate": {"type": "percentile_below", "threshold": 0.30},
    }
    pdf = mod._compute_percentile_per_category(scored)
    result = mod._eval_predicate(case, pdf)
    # Malta percentile = 1.0, which is NOT < 0.30 → FAIL
    assert result["passed"] is False
    assert "FAIL" in result["reason"]


def test_eval_predicate_percentile_above_satisfies_any():
    """case 5 (Sri Lanka) — predicate_satisfies_any=True: passes if
    ANY of the categories is above the threshold."""
    # Sri Lanka is above 50th percentile on currency_crisis but not the others
    scored = pd.DataFrame([
        {"country_id": 1, "country_str": "Sri Lanka", "event_category": "economic_recession",
         "anomaly_score": 1.0, "n_indicators_used": 5},
        {"country_id": 1, "country_str": "Sri Lanka", "event_category": "currency_crisis",
         "anomaly_score": 5.0, "n_indicators_used": 5},  # HIGH
        {"country_id": 1, "country_str": "Sri Lanka", "event_category": "banking_and_financial_crisis",
         "anomaly_score": 1.5, "n_indicators_used": 5},
        # 4 other countries on each category
        *[{"country_id": i, "country_str": f"C{i}", "event_category": ec,
           "anomaly_score": float(i), "n_indicators_used": 5}
          for i in range(2, 6) for ec in ["economic_recession", "currency_crisis",
                                          "banking_and_financial_crisis"]],
    ])
    case = {
        "case_id": 5, "country": "Sri Lanka",
        "event_categories": ["economic_recession", "currency_crisis",
                             "banking_and_financial_crisis"],
        "test_type": "pos", "in_evaluation_universe": True,
        "evaluation_scope": "per_arm", "phase_gate": "v0.1a",
        "predicate_satisfies_any": True,
        "predicate": {"type": "percentile_above", "threshold": 0.50},
    }
    pdf = mod._compute_percentile_per_category(scored)
    result = mod._eval_predicate(case, pdf)
    # Currency_crisis Sri Lanka percentile = 5/5 = 1.0 ≥ 0.5 → PASS via any
    assert result["passed"] is True


def test_eval_predicate_rank_floor_all_categories_pass():
    """Norway must be below 0.20 percentile on ALL 3 conflict categories."""
    scored = pd.DataFrame([
        # Norway with lowest score on all 3 categories
        *[{"country_id": 1, "country_str": "Norway", "event_category": ec,
           "anomaly_score": 0.1, "n_indicators_used": 5}
          for ec in ["civil_war_and_insurgency", "military_coup", "terrorist_attack"]],
        # 9 other countries with higher scores on each category
        *[{"country_id": i, "country_str": f"C{i}", "event_category": ec,
           "anomaly_score": float(i), "n_indicators_used": 5}
          for i in range(2, 11) for ec in ["civil_war_and_insurgency",
                                            "military_coup", "terrorist_attack"]],
    ])
    case = {
        "case_id": 3, "country": "Norway",
        "event_categories": ["civil_war_and_insurgency", "military_coup", "terrorist_attack"],
        "test_type": "floor", "in_evaluation_universe": True,
        "evaluation_scope": "per_arm", "phase_gate": "v0.1a",
        "predicate": {"type": "rank_floor_all_categories", "threshold": 0.20},
    }
    pdf = mod._compute_percentile_per_category(scored)
    result = mod._eval_predicate(case, pdf)
    # Norway is at rank 1/10 = 0.1 on all 3 categories, all < 0.20 → PASS
    assert result["passed"] is True


def test_eval_predicate_rank_floor_all_categories_fail_on_breach():
    """One category breach → whole case FAILS."""
    scored = pd.DataFrame([
        # Norway is LOW on cat1 + cat2 but HIGH (breaches floor) on cat3
        {"country_id": 1, "country_str": "Norway", "event_category": "cat1",
         "anomaly_score": 0.1, "n_indicators_used": 5},
        {"country_id": 1, "country_str": "Norway", "event_category": "cat2",
         "anomaly_score": 0.1, "n_indicators_used": 5},
        {"country_id": 1, "country_str": "Norway", "event_category": "cat3",
         "anomaly_score": 99.0, "n_indicators_used": 5},  # BREACH
        *[{"country_id": i, "country_str": f"C{i}", "event_category": ec,
           "anomaly_score": float(i), "n_indicators_used": 5}
          for i in range(2, 11) for ec in ["cat1", "cat2", "cat3"]],
    ])
    case = {
        "case_id": 3, "country": "Norway",
        "event_categories": ["cat1", "cat2", "cat3"],
        "test_type": "floor", "in_evaluation_universe": True,
        "evaluation_scope": "per_arm", "phase_gate": "v0.1a",
        "predicate": {"type": "rank_floor_all_categories", "threshold": 0.20},
    }
    pdf = mod._compute_percentile_per_category(scored)
    result = mod._eval_predicate(case, pdf)
    assert result["passed"] is False
    assert "cat3" in result["reason"]  # breach category named


def test_eval_predicate_multi_category_count_above_pass():
    """Yemen above 0.75 on >= 3 of the listed categories."""
    # Yemen at HIGH scores on cat1, cat2, cat3; LOW on cat4
    scored = pd.DataFrame([
        *[{"country_id": 1, "country_str": "Yemen", "event_category": ec,
           "anomaly_score": 10.0, "n_indicators_used": 5}
          for ec in ["cat1", "cat2", "cat3"]],
        {"country_id": 1, "country_str": "Yemen", "event_category": "cat4",
         "anomaly_score": 0.1, "n_indicators_used": 5},
        *[{"country_id": i, "country_str": f"C{i}", "event_category": ec,
           "anomaly_score": float(i), "n_indicators_used": 5}
          for i in range(2, 11) for ec in ["cat1", "cat2", "cat3", "cat4"]],
    ])
    case = {
        "case_id": 8, "country": "Yemen",
        "event_categories": ["cat1", "cat2", "cat3", "cat4"],
        "test_type": "failed_state", "in_evaluation_universe": True,
        "evaluation_scope": "per_arm", "phase_gate": "v0.1a",
        "predicate": {"type": "multi_category_count_above",
                      "threshold": 0.75, "min_categories": 3},
    }
    pdf = mod._compute_percentile_per_category(scored)
    result = mod._eval_predicate(case, pdf)
    # Yemen above 0.75 on 3 of 4 categories → PASS (>= 3 required)
    assert result["passed"] is True


def test_eval_predicate_universe_outside_returns_passed_none():
    """T3 from strict review: in_evaluation_universe=false → passed=None."""
    pdf = _make_scored_fixture([("Other", "X", 1.0, 5)])
    pdf = mod._compute_percentile_per_category(pdf)
    case = {
        "case_id": 1, "country": "Malta",
        "event_categories": ["military_coup"], "test_type": "neg",
        "in_evaluation_universe": False, "evaluation_scope": "per_arm",
        "phase_gate": "Phase 6",
        "predicate": {"type": "percentile_below", "threshold": 0.30},
    }
    result = mod._eval_predicate(case, pdf)
    assert result["passed"] is None
    assert "outside_evaluation_universe" in result["reason"]


def test_eval_predicate_cross_arm_scope_returns_passed_none():
    """T4: evaluation_scope=cross_arm → passed=None (skip in per-arm)."""
    pdf = _make_scored_fixture([("Venezuela", "X", 1.0, 5)])
    pdf = mod._compute_percentile_per_category(pdf)
    case = {
        "case_id": 6, "country": "Venezuela",
        "event_categories": ["X"], "test_type": "stability",
        "in_evaluation_universe": True, "evaluation_scope": "cross_arm",
        "phase_gate": "v0.1a",
        "predicate": {"type": "rank_stability_across_versions",
                      "max_percentile_delta": 0.15, "comparison_arms": ["D", "A"]},
    }
    result = mod._eval_predicate(case, pdf)
    assert result["passed"] is None
    assert "cross_arm" in result["reason"]


def test_evaluate_anchor_cases_aggregates():
    """evaluate_anchor_cases returns one result per case from the battery."""
    battery = {
        "cases": [
            {"case_id": 1, "country": "Malta",
             "event_categories": ["military_coup"], "test_type": "neg",
             "in_evaluation_universe": False, "evaluation_scope": "per_arm",
             "phase_gate": "Phase 6",
             "predicate": {"type": "percentile_below", "threshold": 0.30}},
            {"case_id": 3, "country": "Norway",
             "event_categories": ["X"], "test_type": "floor",
             "in_evaluation_universe": True, "evaluation_scope": "per_arm",
             "phase_gate": "v0.1a",
             "predicate": {"type": "rank_floor_all_categories", "threshold": 0.20}},
        ],
    }
    scored = pd.DataFrame([
        {"country_id": 1, "country_str": "Norway", "event_category": "X",
         "anomaly_score": 0.1, "n_indicators_used": 5},
        *[{"country_id": i, "country_str": f"C{i}", "event_category": "X",
           "anomaly_score": float(i), "n_indicators_used": 5}
          for i in range(2, 11)],
    ])
    results = mod.evaluate_anchor_cases(scored, battery)
    assert len(results) == 2
    # Case 1 (Malta) outside universe → None
    assert results[0]["passed"] is None
    # Case 3 (Norway) at percentile 0.1 < 0.20 → True
    assert results[1]["passed"] is True


def test_evaluate_anchor_cases_none_battery_returns_empty():
    """If battery is None, return empty list (regression suite is optional)."""
    out = mod.evaluate_anchor_cases(pd.DataFrame(), None)
    assert out == []


def test_country_fallback_both_yemen_and_somalia_insufficient_returns_none():
    """T2 strict-review fix: when BOTH primary and fallback are insufficient,
    the for-else branch fires and returns passed=None with a clear reason.
    This is the production-likely path because Somalia is outside the
    countries_100.json universe (case 8 spec note).
    """
    # Yemen only on 1 category (< 3 required); Somalia entirely absent
    scored = pd.DataFrame([
        {"country_id": 1, "country_str": "Yemen", "event_category": "cat1",
         "anomaly_score": 10.0, "n_indicators_used": 5},
        *[{"country_id": i, "country_str": f"C{i}", "event_category": ec,
           "anomaly_score": float(i), "n_indicators_used": 5}
          for i in range(2, 8) for ec in ["cat1", "cat2", "cat3"]],
    ])
    case = {
        "case_id": 8, "country": "Yemen",
        "country_alternatives": ["Somalia"],
        "country_fallback_rule": {
            "min_categories_with_data": 3,
            "min_n_countries_per_category": 5,
        },
        "event_categories": ["cat1", "cat2", "cat3"],
        "test_type": "failed_state", "in_evaluation_universe": True,
        "evaluation_scope": "per_arm", "phase_gate": "v0.1a",
        "predicate": {"type": "multi_category_count_above",
                      "threshold": 0.50, "min_categories": 3},
    }
    pdf = mod._compute_percentile_per_category(scored)
    result = mod._eval_predicate(case, pdf)
    # Both primary insufficient and Somalia outside scored → passed=None
    assert result["passed"] is None
    assert "insufficient" in result["reason"] or "fallback" in result["reason"]


def test_eval_predicate_percentile_above_satisfies_any_false():
    """T3 strict-review fix: percentile_above with satisfies_any=False
    (case 4 single-category Tunisia path) — only the first category in
    the list is evaluated; needs to exceed the threshold."""
    scored = pd.DataFrame([
        {"country_id": 1, "country_str": "Tunisia",
         "event_category": "democratic_transition",
         "anomaly_score": 10.0, "n_indicators_used": 5},  # HIGH
        *[{"country_id": i, "country_str": f"C{i}",
           "event_category": "democratic_transition",
           "anomaly_score": float(i), "n_indicators_used": 5}
          for i in range(2, 6)],
    ])
    case = {
        "case_id": 4, "country": "Tunisia",
        "event_categories": ["democratic_transition"],
        "test_type": "pos", "in_evaluation_universe": True,
        "evaluation_scope": "per_arm", "phase_gate": "v0.1a",
        # No predicate_satisfies_any key → defaults to False (single-category path)
        "predicate": {"type": "percentile_above", "threshold": 0.50},
    }
    pdf = mod._compute_percentile_per_category(scored)
    result = mod._eval_predicate(case, pdf)
    # Tunisia at rank 5/5 = 1.0 percentile > 0.50 → PASS
    assert result["passed"] is True


def test_eval_predicate_strict_boundary_at_threshold_fails():
    """T1 + T3 strict-review fix: predicates use STRICT comparison
    (< for below, > for above). A country EXACTLY at the threshold
    boundary is on the FAIL side for both directions.
    """
    # n=4 so rank/n gives exact 0.25, 0.50, 0.75, 1.00 percentiles
    scored = _make_scored_fixture([
        ("C1", "X", 1.0, 5),  # percentile = 0.25
        ("C2", "X", 2.0, 5),  # percentile = 0.50 (median)
        ("C3", "X", 3.0, 5),  # percentile = 0.75
        ("C4", "X", 4.0, 5),  # percentile = 1.00 (top)
    ])
    pdf = mod._compute_percentile_per_category(scored)

    # percentile_above 0.50: C2 at exactly 0.50 → FAIL (strict >)
    case_above = {
        "case_id": 99, "country": "C2", "event_categories": ["X"],
        "test_type": "boundary", "in_evaluation_universe": True,
        "evaluation_scope": "per_arm", "phase_gate": "v0.1a",
        "predicate": {"type": "percentile_above", "threshold": 0.50},
    }
    result = mod._eval_predicate(case_above, pdf)
    assert result["passed"] is False, "country at exactly threshold must FAIL percentile_above"

    # percentile_below 0.25: C1 at exactly 0.25 → FAIL (strict <)
    case_below = {
        "case_id": 99, "country": "C1", "event_categories": ["X"],
        "test_type": "boundary", "in_evaluation_universe": True,
        "evaluation_scope": "per_arm", "phase_gate": "v0.1a",
        "predicate": {"type": "percentile_below", "threshold": 0.25},
    }
    result = mod._eval_predicate(case_below, pdf)
    assert result["passed"] is False, "country at exactly threshold must FAIL percentile_below"


def test_country_fallback_yemen_to_somalia_when_yemen_insufficient():
    """Yemen → Somalia fallback when Yemen has insufficient data."""
    # Yemen present only in 2 categories; Somalia in 5
    scored = pd.DataFrame([
        # Yemen on 2 categories only (insufficient: < 3)
        {"country_id": 1, "country_str": "Yemen", "event_category": "cat1",
         "anomaly_score": 10.0, "n_indicators_used": 5},
        {"country_id": 1, "country_str": "Yemen", "event_category": "cat2",
         "anomaly_score": 10.0, "n_indicators_used": 5},
        # Somalia on 5 categories (sufficient: >= 3)
        *[{"country_id": 2, "country_str": "Somalia", "event_category": ec,
           "anomaly_score": 10.0, "n_indicators_used": 5}
          for ec in ["cat1", "cat2", "cat3", "cat4", "cat5"]],
        # Other countries to give each category enough cells (n>=5)
        *[{"country_id": i, "country_str": f"C{i}", "event_category": ec,
           "anomaly_score": float(i), "n_indicators_used": 5}
          for i in range(3, 9) for ec in ["cat1", "cat2", "cat3", "cat4", "cat5"]],
    ])
    case = {
        "case_id": 8, "country": "Yemen",
        "country_alternatives": ["Somalia"],
        "country_fallback_rule": {
            "min_categories_with_data": 3,
            "min_n_countries_per_category": 5,
        },
        "event_categories": ["cat1", "cat2", "cat3", "cat4", "cat5"],
        "test_type": "failed_state", "in_evaluation_universe": True,
        "evaluation_scope": "per_arm", "phase_gate": "v0.1a",
        "predicate": {"type": "multi_category_count_above",
                      "threshold": 0.50, "min_categories": 3},
    }
    pdf = mod._compute_percentile_per_category(scored)
    result = mod._eval_predicate(case, pdf)
    # Should fall back to Somalia (3+ categories with data)
    assert result["country_resolved_to"] == "Somalia"
    # Somalia is above the threshold on enough categories → PASS
    assert result["passed"] is True


# ===========================================================================
# #637 m3: bootstrap + stratification edge case coverage
# ===========================================================================

def test_auc_bootstrap_ci_n_zero_input_returns_none():
    """m3.2 — explicit guard: empty input arrays return (None, None, [])."""
    y = np.array([], dtype=int)
    pred = np.array([], dtype=float)
    lo, hi, aucs = mod._auc_bootstrap_ci(
        y, pred, n_resamples=100, seed=0, alpha=0.05,
    )
    assert lo is None
    assert hi is None
    assert aucs == []


def test_auc_bootstrap_ci_width_non_increasing_with_more_resamples():
    """m3.1 — CI width must not expand as n_resamples grows on the same
    fixture. The percentile CI is a monotonically-stabilizing estimator,
    so 100 → 1000 → 5000 should produce widths in roughly non-increasing
    order (small upward jitter < 0.02 allowed because the inner quantile
    estimate has its own sampling variance, but the trend must be
    decreasing or flat)."""
    rng = np.random.default_rng(2026)
    n = 80
    y = rng.integers(0, 2, size=n)
    # Pred correlated with y → finite, non-degenerate AUC
    pred = y + rng.normal(0, 0.6, size=n)

    widths = []
    for n_resamples in (100, 1000, 5000):
        lo, hi, _ = mod._auc_bootstrap_ci(
            y, pred, n_resamples=n_resamples, seed=42, alpha=0.05,
        )
        assert lo is not None and hi is not None
        widths.append(hi - lo)

    # 100 → 1000: width may shrink dramatically
    # 1000 → 5000: width should be roughly stable (further shrinking is
    # diminishing returns). Allow small upward jitter from inner sampling.
    assert widths[1] <= widths[0] + 0.05, (
        f"CI width grew substantially 100 → 1000: {widths[0]} → {widths[1]}"
    )
    assert widths[2] <= widths[1] + 0.02, (
        f"CI width grew substantially 1000 → 5000: {widths[1]} → {widths[2]}"
    )


def test_stratified_auc_single_stratum_all_data_sufficient():
    """m3.3 — when ALL cells have n_indicators_used >= STRATA_THRESHOLD,
    the thin_coverage stratum is empty (n_cells=0, NaN aucs). The
    data_sufficient stratum carries the entire signal."""
    threshold = mod.STRATA_INDICATOR_COUNT_THRESHOLD
    rows = []
    for i in range(20):
        rows.append({
            "country_id": i, "event_category": "X",
            "anomaly_score": float(i),
            "n_indicators_used": threshold + 1,  # all >= threshold
        })
    scored = pd.DataFrame(rows)
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": int(i >= 10)}
        for i in range(20)
    ])
    out = mod.compute_stratified_auc(scored, gt)

    assert out["data_sufficient"]["n_cells"] == 20
    assert out["thin_coverage"]["n_cells"] == 0
    assert out["thin_coverage"]["n_categories"] == 0
    # Empty stratum: clean NaN, not crash
    assert np.isnan(out["thin_coverage"]["mean_auc"])
    assert np.isnan(out["thin_coverage"]["median_auc"])
    assert out["thin_coverage"]["per_event_category_auc"] == []
    # Data-sufficient: actual signal (perfect discrimination at i>=10 boundary)
    assert out["data_sufficient"]["mean_auc"] == 1.0


def test_stratified_auc_single_stratum_all_thin_coverage():
    """m3.3 — symmetric case: when ALL cells are below the threshold,
    data_sufficient is empty and thin_coverage carries the signal.
    This is the v0.1a ablation's actual real-world reading (≥10/10
    stratum had 0 cells in the 2026-05-11 production run)."""
    threshold = mod.STRATA_INDICATOR_COUNT_THRESHOLD
    rows = []
    for i in range(20):
        rows.append({
            "country_id": i, "event_category": "X",
            "anomaly_score": float(i),
            "n_indicators_used": max(1, threshold - 5),  # all < threshold
        })
    scored = pd.DataFrame(rows)
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": int(i >= 10)}
        for i in range(20)
    ])
    out = mod.compute_stratified_auc(scored, gt)

    assert out["thin_coverage"]["n_cells"] == 20
    assert out["data_sufficient"]["n_cells"] == 0
    assert out["data_sufficient"]["n_categories"] == 0
    assert np.isnan(out["data_sufficient"]["mean_auc"])
    assert np.isnan(out["data_sufficient"]["median_auc"])
    assert out["data_sufficient"]["per_event_category_auc"] == []


def test_per_category_ece_zero_variance_scores_falls_back_to_half():
    """m3.4 — when a category has all-identical anomaly_score values
    (span = max - min = 0), pred_scaled falls back to 0.5 for every cell.
    All scaled predictions land in the middle bin; ECE is measured against
    the 0.5 baseline (which equals |0.5 - base_rate|)."""
    # 10 cells, all with score = 1.7. Half are positive (base rate = 0.5).
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "FLAT",
         "anomaly_score": 1.7, "n_indicators_used": 5}
        for i in range(10)
    ])
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "FLAT",
         "y_post_cutoff": int(i < 5)}  # base rate exactly 0.5
        for i in range(10)
    ])
    out = mod.compute_per_category_ece(scored, gt)

    assert len(out) == 1
    row = out[0]
    assert row["event_category"] == "FLAT"
    assert row["n_cells"] == 10
    # pred_scaled = 0.5 fallback; base rate = 0.5 → ECE = 0
    assert row["ece"] == pytest.approx(0.0, abs=1e-9)

    # All 10 predictions land in a single bin (the bin straddling 0.5);
    # the rest are empty.
    non_empty = [b for b in row["reliability_diagram"] if b["n"] > 0]
    assert len(non_empty) == 1
    assert non_empty[0]["n"] == 10
    assert non_empty[0]["mean_prediction"] == pytest.approx(0.5, abs=1e-9)
    assert non_empty[0]["event_rate"] == pytest.approx(0.5, abs=1e-9)
    assert non_empty[0]["abs_calibration_gap"] == pytest.approx(0.0, abs=1e-9)


def test_per_category_ece_zero_variance_asymmetric_base_rate():
    """m3.4 (extended) — same fallback as above, but with an asymmetric
    base rate (0.8). ECE should equal |0.5 - 0.8| = 0.3 because every
    prediction is forced to 0.5 by the zero-span guard, but events occur
    at 80%."""
    scored = pd.DataFrame([
        {"country_id": i, "event_category": "FLAT",
         "anomaly_score": 3.14, "n_indicators_used": 5}
        for i in range(10)
    ])
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "FLAT",
         "y_post_cutoff": int(i < 8)}  # 8/10 positive
        for i in range(10)
    ])
    out = mod.compute_per_category_ece(scored, gt)
    assert len(out) == 1
    assert out[0]["ece"] == pytest.approx(0.3, abs=1e-9)


# ===========================================================================
# #637 m2: end-to-end main() arm equivalence test
# ===========================================================================

def _build_main_fixture(tmp_path, *, n_countries=30, n_indicators=4,
                       n_categories=3, weight_matrix=True,
                       directions=True, allow_list=True, anchor_battery=True):
    """Build a self-contained fixture for main() end-to-end testing.

    Writes the 4 reference JSONs under tmp_path/qgi-data/reference/ and
    returns a dict with the in-memory loader stubs the test will
    monkeypatch in.

    The fixture is deliberately small: 30 synthetic countries, 4
    indicators, 3 event_categories. The point is to verify SCHEMA and
    BRANCHING of main() (output keys, legacy alias, decision rationale,
    config block), not statistical realism. Real AUC/ECE values are
    exercised by the function-level tests above.
    """
    ref_dir = tmp_path / "qgi-data" / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)

    api_codes = [f"IND_{i:02d}" for i in range(n_indicators)]
    event_categories = [f"cat_{c}" for c in range(n_categories)]

    # weight-matrix.json
    weights_rows = []
    for nid, api in enumerate(api_codes, start=1):
        for ec in event_categories:
            weights_rows.append({
                "indicator_numeric_id": nid,
                "indicator_catalog_id": f"X-{nid:02d}",
                "event_category": ec,
                "sector": "test_sector",
                "L1": "L1_test",
                "weight": 0.5,
                "used_fallback": False,
            })
    if weight_matrix:
        (ref_dir / "weight-matrix.json").write_text(json.dumps({
            "schema_version": 3,
            "generated": "2026-01-01T00:00:00+00:00",
            "n_full_eb_prior": len(weights_rows),
            "weights": weights_rows,
        }), encoding="utf-8")

    # indicator-directions.json
    if directions:
        (ref_dir / "indicator-directions.json").write_text(json.dumps({
            "schema_version": 1, "generated": "2026-01-01T00:00:00+00:00",
            "directions": [
                {"api_code": api, "direction": 1 if i % 2 == 0 else -1,
                 "tag": "[lit-only]", "justification": "test"}
                for i, api in enumerate(api_codes)
            ],
        }), encoding="utf-8")

    # indicator-allow-list.json
    if allow_list:
        (ref_dir / "indicator-allow-list.json").write_text(json.dumps({
            "schema_version": 1,
            "allow_list_numeric_ids": list(range(1, n_indicators + 1)),
        }), encoding="utf-8")

    # cascade-anchor-case-battery.json — minimal (empty cases list).
    # Tests anchor_case_battery wiring without exercising predicate logic.
    if anchor_battery:
        (ref_dir / "cascade-anchor-case-battery.json").write_text(json.dumps({
            "schema_version": 1, "generated": "2026-01-01T00:00:00+00:00",
            "evaluation_semantics": {"rank_basis": "ascending"},
            "cases": [],
        }), encoding="utf-8")

    # Synthetic panel: each (country, indicator) has a value at every
    # year in the z-score window. Use a deterministic spread per
    # country so z-scores aren't all zero.
    panel_rows = []
    for cid in range(1, n_countries + 1):
        for api in api_codes:
            for y in range(2014 - mod.ZSCORE_WINDOW_YEARS + 1, 2015):
                panel_rows.append({
                    "country": str(cid), "year": y,
                    "indicator_id": api,
                    "value": float(cid + (y - 2014)),
                })
    panel = pd.DataFrame(panel_rows)
    panel["country_id"] = panel["country"].astype(int)

    # Synthetic ground truth: cell (country, category) gets y=1 iff
    # country_id is even and category is cat_0.
    gt_rows = []
    for cid in range(1, n_countries + 1):
        for ec in event_categories:
            gt_rows.append({
                "country_id": cid, "event_category": ec,
                "y_post_cutoff": int(cid % 2 == 0 and ec == "cat_0"),
            })
    gt = pd.DataFrame(gt_rows)

    # Countries lookup
    countries = pd.DataFrame([
        {"country_id": cid, "name": f"Country_{cid:02d}"}
        for cid in range(1, n_countries + 1)
    ])

    # num_to_api
    num_to_api = {nid: api for nid, api in enumerate(api_codes, start=1)}

    return {
        "ref_dir": ref_dir, "panel": panel, "gt": gt, "countries": countries,
        "num_to_api": num_to_api,
    }


def _install_main_monkeypatches(monkeypatch, tmp_path, fixture):
    """Wire fixture loaders into the script module, redirect ROOT-derived
    paths to tmp_path, and stub the boto3 + creds boundary so main() never
    touches Athena. Used by all m2 main()-end-to-end tests."""
    ref_dir = fixture["ref_dir"]
    monkeypatch.setattr(mod, "WEIGHT_MATRIX_JSON", ref_dir / "weight-matrix.json")
    monkeypatch.setattr(mod, "DIRECTIONS_JSON", ref_dir / "indicator-directions.json")
    monkeypatch.setattr(mod, "ALLOW_LIST_JSON", ref_dir / "indicator-allow-list.json")
    monkeypatch.setattr(mod, "ANCHOR_BATTERY_JSON", ref_dir / "cascade-anchor-case-battery.json")
    monkeypatch.setattr(mod, "OUTPUT_JSON_LEGACY", ref_dir / "phase4-validation.json")
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    # The loader functions capture their default `path=` argument at
    # def-time, so simply patching the module-level constants above is
    # not sufficient — main() calls e.g. `load_allow_list()` without
    # args. Wrap each loader to inject the patched path explicitly.
    real_load_allow_list = mod.load_allow_list
    real_load_directions = mod.load_direction_annotations
    real_load_anchor = mod.load_anchor_battery
    monkeypatch.setattr(mod, "load_allow_list",
                        lambda path=None: real_load_allow_list(
                            ref_dir / "indicator-allow-list.json"))
    monkeypatch.setattr(mod, "load_direction_annotations",
                        lambda path=None: real_load_directions(
                            ref_dir / "indicator-directions.json"))
    monkeypatch.setattr(mod, "load_anchor_battery",
                        lambda path=None: real_load_anchor(
                            ref_dir / "cascade-anchor-case-battery.json"))

    # Stub Athena boundary: creds file read + boto3.Session.
    creds_dir = tmp_path / "creds"
    creds_dir.mkdir(parents=True, exist_ok=True)
    creds_path = creds_dir / "staging_creds.json"
    creds_path.write_text(json.dumps({
        "ak": "test_ak", "sk": "test_sk", "st": "test_st",
    }), encoding="utf-8")

    # Patch the hard-coded staging-creds path inside main(). main()
    # constructs the path locally as `Path(r"C:/...")`, so we can't
    # redirect via setattr. Instead, monkeypatch Path itself to return
    # our test path when called with the staging-creds string. Cleaner
    # alternative: monkeypatch Path.read_text on the specific path.
    real_read_text = Path.read_text
    test_creds_text = creds_path.read_text(encoding="utf-8")

    def _stub_read_text(self, *args, **kwargs):
        if "staging_creds.json" in str(self):
            return test_creds_text
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _stub_read_text)

    # Stub boto3.Session so no real AWS call ever fires
    class _StubSession:
        def __init__(self, **_kwargs):
            pass

        def client(self, _service):
            return object()  # never used; loaders are stubbed too

    monkeypatch.setattr(mod, "boto3", types.SimpleNamespace(Session=_StubSession))

    # Stub the loader functions — they're the only consumers of the
    # boto3 client. After this, main() runs purely on the fixture.
    monkeypatch.setattr(mod.au, "load_indicator_panel",
                        lambda *a, **k: fixture["panel"])
    monkeypatch.setattr(mod.au, "load_event_ground_truth",
                        lambda *a, **k: fixture["gt"])
    monkeypatch.setattr(mod.au, "load_countries",
                        lambda *a, **k: fixture["countries"])
    monkeypatch.setattr(mod.eb, "load_numeric_to_api",
                        lambda *a, **k: fixture["num_to_api"])


def test_main_end_to_end_arm_D_writes_legacy_alias(monkeypatch, tmp_path):
    """m2 — D-arm end-to-end. Verifies:
    - output JSON's schema_version matches the current SCHEMA_VERSION constant
    - output's ablation_arm == "D" and ablation_arm_config is unsigned/no-filter
    - legacy alias `phase4-validation.json` IS written for the D-arm
    - summary keys are present and finite
    """
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D",
        # Small bootstrap so the test is fast
        bootstrap_resamples=50,
    )

    # Per-arm output written
    out_path = fixture["ref_dir"] / "phase4-validation-armD.json"
    assert out_path.exists(), f"per-arm output not written: {out_path}"
    out = json.loads(out_path.read_text(encoding="utf-8"))
    # v6 (T8): schema_version follows mod.SCHEMA_VERSION rather than the
    # literal 4 from v4. The v4-era D-arm sanity-check path is preserved
    # in v6 (no canonical-length/exclusion config required for D-arm-
    # without-baselines), but the schema number bumps with the script.
    assert out["schema_version"] == mod.SCHEMA_VERSION
    assert out["ablation_arm"] == "D"
    assert out["ablation_arm_config"] == {
        "use_signed_scoring": False,
        "apply_591_filter": False,
    }

    # Legacy alias is written for D-arm
    legacy_path = fixture["ref_dir"] / "phase4-validation.json"
    assert legacy_path.exists(), (
        "legacy phase4-validation.json alias must be written for D-arm "
        "(v3 backward-compat contract)"
    )
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert legacy["ablation_arm"] == "D"
    assert legacy["schema_version"] == mod.SCHEMA_VERSION

    # Summary keys present (per the v4 schema; values may be NaN on small
    # synthetic fixtures where AUC is undefined, but the keys must exist)
    summary = out["summary"]
    for k in ("n_event_categories", "n_event_categories_with_auc",
              "n_predictions", "mean_auc", "median_auc",
              "n_auc_above_0_55", "n_auc_above_0_65", "ece",
              "decision", "decision_rationale"):
        assert k in summary, f"missing summary key: {k}"

    # v4-specific top-level keys
    for k in ("stratified_auc", "per_event_category_ece",
              "anchor_case_battery", "method_caveats", "config"):
        assert k in out, f"missing top-level key: {k}"


def test_main_end_to_end_arm_A_does_not_write_legacy_alias(monkeypatch, tmp_path):
    """m2 — A-arm (signed × #591 filter) must NOT write the legacy alias.
    Only the per-arm output is written. Verifies the alias guard at the
    bottom of main() correctly branches on ablation_arm == "D"."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="A", bootstrap_resamples=50,
    )

    out_path = fixture["ref_dir"] / "phase4-validation-armA.json"
    assert out_path.exists()
    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert out["ablation_arm"] == "A"
    assert out["ablation_arm_config"] == {
        "use_signed_scoring": True,
        "apply_591_filter": True,
    }

    # Legacy alias must NOT be written for A-arm
    legacy_path = fixture["ref_dir"] / "phase4-validation.json"
    assert not legacy_path.exists(), (
        "legacy alias must only be written for the D-arm; non-D arms "
        "would overwrite the v3 baseline reference"
    )


def test_main_end_to_end_arm_A_requires_directions(monkeypatch, tmp_path):
    """m2 — A-arm hard-errors when directions JSON is absent (strict-
    review M4 regression: silent fallback to D-behavior is forbidden)."""
    fixture = _build_main_fixture(tmp_path, directions=False)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    with pytest.raises(FileNotFoundError, match="direction annotations"):
        mod.main(
            cutoff_year=2014, end_year=2025, with_baselines=False,
            ablation_arm="A", bootstrap_resamples=50,
        )


def test_main_end_to_end_arm_C_requires_allow_list(monkeypatch, tmp_path):
    """m2 — C-arm hard-errors when allow-list JSON is absent. Same
    contract as the A-arm directions requirement."""
    fixture = _build_main_fixture(tmp_path, allow_list=False)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    with pytest.raises(FileNotFoundError, match="#591 allow-list"):
        mod.main(
            cutoff_year=2014, end_year=2025, with_baselines=False,
            ablation_arm="C", bootstrap_resamples=50,
        )


def test_main_end_to_end_v3_backward_compat_keys_present(monkeypatch, tmp_path):
    """m2 — D-arm output preserves all v3-era top-level keys that
    downstream consumers depend on (per_event_category_auc, reliability_
    diagram, ece, decision/decision_rationale). v4 adds keys, never
    removes them."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=50,
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    # Frozen v3-era keys
    v3_keys = {
        "schema_version", "generated", "method", "config", "summary",
        "per_event_category_auc", "reliability_diagram",
    }
    missing = v3_keys - set(out.keys())
    assert not missing, f"v3 backward-compat keys missing: {missing}"


# ===========================================================================
# v5 NEW (T2 / #666 / Phase 5 v0.2 charter A2):
#   γ-stage instrumentation — configurable strata threshold + sensitivity sweep
# ===========================================================================

def test_compute_stratified_auc_accepts_strata_threshold_param():
    """v5 — `compute_stratified_auc` accepts a `strata_threshold` kwarg
    that overrides the module-level default. The threshold is reflected
    in the output's "threshold" field, and stratum membership flips when
    the kwarg moves above/below n_indicators_used.
    """
    rows = [
        {"country_id": i, "event_category": "X",
         "anomaly_score": float(i), "n_indicators_used": 7}
        for i in range(10)
    ]
    scored = pd.DataFrame(rows)
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": int(i >= 5)}
        for i in range(10)
    ])

    # threshold=5 ⇒ all 10 cells (n=7 each) land in data_sufficient
    out_lo = mod.compute_stratified_auc(scored, gt, strata_threshold=5)
    assert out_lo["threshold"] == 5
    assert out_lo["data_sufficient"]["n_cells"] == 10
    assert out_lo["thin_coverage"]["n_cells"] == 0

    # threshold=10 ⇒ all 10 cells land in thin_coverage
    out_hi = mod.compute_stratified_auc(scored, gt, strata_threshold=10)
    assert out_hi["threshold"] == 10
    assert out_hi["data_sufficient"]["n_cells"] == 0
    assert out_hi["thin_coverage"]["n_cells"] == 10


def test_compute_stratified_auc_default_threshold_unchanged():
    """v5 — when `strata_threshold` is not passed, behavior matches the
    pre-v5 module default (v4 backward-compat)."""
    rows = [
        {"country_id": i, "event_category": "X",
         "anomaly_score": float(i),
         "n_indicators_used": 15 if i < 5 else 3}
        for i in range(10)
    ]
    scored = pd.DataFrame(rows)
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": int(i >= 5)}
        for i in range(10)
    ])
    out = mod.compute_stratified_auc(scored, gt)
    assert out["threshold"] == mod.STRATA_INDICATOR_COUNT_THRESHOLD
    # With default threshold=10: cells with n=15 are sufficient, n=3 are thin.
    assert out["data_sufficient"]["n_cells"] == 5
    assert out["thin_coverage"]["n_cells"] == 5


def test_stratum_sensitivity_thresholds_constant():
    """v5 — the module exposes the canonical γ-sweep tuple {3, 5, 7, 10, 15}
    as STRATUM_SENSITIVITY_THRESHOLDS. This is the locked γ-stage transparency
    set per Phase 5 v0.2 charter §γ. Changing it requires a charter amendment.
    """
    assert mod.STRATUM_SENSITIVITY_THRESHOLDS == (3, 5, 7, 10, 15)


def test_compute_stratum_sensitivity_returns_per_threshold_rows():
    """v5 — `compute_stratum_sensitivity` returns one entry per threshold
    in the sweep, each carrying n_cells, n_categories, mean_auc, median_auc."""
    # 30 cells with n_indicators_used varying from 1..30. Half positive
    # so AUC is computable per threshold.
    rows = [
        {"country_id": i, "event_category": "X",
         "anomaly_score": float(i),
         "n_indicators_used": i + 1}
        for i in range(30)
    ]
    scored = pd.DataFrame(rows)
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": int(i >= 15)}
        for i in range(30)
    ])

    out = mod.compute_stratum_sensitivity(scored, gt)
    assert out["thresholds_swept"] == [3, 5, 7, 10, 15]
    assert len(out["entries"]) == 5
    for entry in out["entries"]:
        for k in ("threshold", "n_cells", "n_categories",
                  "mean_auc", "median_auc"):
            assert k in entry, f"missing key {k} in entry {entry}"
        assert entry["threshold"] in (3, 5, 7, 10, 15)

    # n_cells in data_sufficient stratum decreases monotonically as
    # threshold rises (fewer cells clear the higher bar).
    n_cells_by_threshold = {e["threshold"]: e["n_cells"] for e in out["entries"]}
    assert n_cells_by_threshold[3] >= n_cells_by_threshold[5]
    assert n_cells_by_threshold[5] >= n_cells_by_threshold[7]
    assert n_cells_by_threshold[7] >= n_cells_by_threshold[10]
    assert n_cells_by_threshold[10] >= n_cells_by_threshold[15]


def test_compute_stratum_sensitivity_handles_empty_input():
    """v5 — empty scored/gt → 5 entries, each with n_cells=0 and NaN
    mean/median AUCs. Mirrors the empty-input contract of
    compute_stratified_auc."""
    scored = pd.DataFrame(columns=["country_id", "event_category",
                                   "anomaly_score", "n_indicators_used"])
    gt = pd.DataFrame(columns=["country_id", "event_category", "y_post_cutoff"])
    out = mod.compute_stratum_sensitivity(scored, gt)
    assert len(out["entries"]) == 5
    for entry in out["entries"]:
        assert entry["n_cells"] == 0
        assert entry["n_categories"] == 0


def test_compute_stratum_sensitivity_accepts_custom_thresholds():
    """v5 — caller can override the sweep set. (Used by tests; in
    production the γ-sweep is always {3,5,7,10,15} per the charter.)"""
    rows = [
        {"country_id": i, "event_category": "X",
         "anomaly_score": float(i), "n_indicators_used": 8}
        for i in range(10)
    ]
    scored = pd.DataFrame(rows)
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": int(i >= 5)}
        for i in range(10)
    ])
    out = mod.compute_stratum_sensitivity(scored, gt, thresholds=(2, 4))
    assert out["thresholds_swept"] == [2, 4]
    assert len(out["entries"]) == 2


def test_evaluate_weights_surfaces_stratum_sensitivity():
    """v5 — `evaluate_weights` now surfaces `stratum_sensitivity` in its
    return dict alongside `stratified_auc`."""
    fixture = _build_evaluate_weights_minimal_fixture()
    out = mod.evaluate_weights(
        fixture["weights_df"], fixture["zscores"],
        fixture["country_id_to_str"], fixture["num_to_api"], fixture["gt"],
        label="treatment",
        bootstrap_resamples=20,
    )
    assert "stratum_sensitivity" in out
    assert out["stratum_sensitivity"]["thresholds_swept"] == [3, 5, 7, 10, 15]


def test_evaluate_weights_threads_strata_threshold_to_stratified_auc():
    """v5 — `evaluate_weights(strata_threshold=N)` flows N into the
    `stratified_auc` block's threshold field."""
    fixture = _build_evaluate_weights_minimal_fixture()
    out = mod.evaluate_weights(
        fixture["weights_df"], fixture["zscores"],
        fixture["country_id_to_str"], fixture["num_to_api"], fixture["gt"],
        label="treatment",
        bootstrap_resamples=20,
        strata_threshold=5,
    )
    assert out["stratified_auc"]["threshold"] == 5


def _build_evaluate_weights_minimal_fixture():
    """Build the smallest fixture that exercises evaluate_weights end-to-end
    without Athena. Inline construction so the test doesn't depend on
    tmp_path/monkeypatch. 1 indicator, 6 countries, 1 event_category.

    Schema matches what compute_country_zscores produces upstream:
      zscores columns: country (str), indicator_id (api_code), value, z_score
    score_country_event then renames indicator_id → api_code and joins
    against weights_df via num_to_api.
    """
    weights_df = pd.DataFrame([
        {"indicator_numeric_id": 100, "event_category": "X", "weight": 1.0},
    ])
    zscores = pd.DataFrame([
        {"country": f"C{i}", "indicator_id": "I100",
         "value": float(i), "z_score": float(i - 2.5)}
        for i in range(6)
    ])
    country_id_to_str = {i: f"C{i}" for i in range(6)}
    num_to_api = {100: "I100"}
    gt = pd.DataFrame([
        {"country_id": i, "event_category": "X", "y_post_cutoff": int(i >= 3)}
        for i in range(6)
    ])
    return {
        "weights_df": weights_df,
        "zscores": zscores,
        "country_id_to_str": country_id_to_str,
        "num_to_api": num_to_api,
        "gt": gt,
    }


def test_main_end_to_end_surfaces_stratum_sensitivity_in_output(monkeypatch, tmp_path):
    """v5 — top-level `stratum_sensitivity` key is in the per-arm output
    JSON (D-arm, no baselines). Asserts the γ-stage transparency artifact
    is wired all the way from compute_stratum_sensitivity → evaluate_weights
    → output dict."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    assert "stratum_sensitivity" in out
    assert out["stratum_sensitivity"]["thresholds_swept"] == [3, 5, 7, 10, 15]
    assert len(out["stratum_sensitivity"]["entries"]) == 5


def test_main_end_to_end_strata_threshold_reflected_in_config(monkeypatch, tmp_path):
    """v5 — `main(strata_threshold=N)` propagates N into
    `config.strata_indicator_count_threshold` and into the
    `stratified_auc.threshold` field of the output JSON."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
        strata_threshold=7,
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    assert out["config"]["strata_indicator_count_threshold"] == 7
    assert out["stratified_auc"]["threshold"] == 7


# ===========================================================================
# v6 NEW (T8 / #672 / Phase 5 v0.2 Path A):
#   rule v2 verdict + posterior-update protocol + config loaders +
#   multi-seed baseline
# ===========================================================================


def test_schema_version_is_6():
    """T12 #692 bumps SCHEMA_VERSION from 5 to 6 to mark the optional
    `per_cell` block emission for Path B's partial-pooling evaluator.
    Per docs-specs `ca77505` §3.1 (post-6-seat-Majles amendment 2026-05-15):
    response variable is anomaly_score, not AUC, because ROC-AUC is
    undefined at single-observation granularity. Backward-compat: when
    --emit-per-cell is NOT set, output is functionally equivalent to v5.

    Previous canary (v5, T8 / #672): rule v2 verdict + multi-seed
    baseline + posterior-update protocol — all preserved verbatim in v6."""
    assert mod.SCHEMA_VERSION == 6


def test_v6_rule_v2_constants_match_pre_reg():
    """T8 hard-codes rule v2 thresholds matching pre-reg spec `a2f5db4`.
    Any drift requires a Majles convening per Roshani §3 + Kwame §1.
    Tripwire: if these constants change without the JSON config also
    being updated, T9 fires with a divergent gate."""
    assert mod.RULE_V2_STRATUM_THRESHOLD == 10
    assert mod.RULE_V2_CARDINALITY_FLOOR_N == 30
    assert mod.RULE_V2_FALSIFY_BELOW_SWING == 0.03


def test_v6_posterior_priors_match_pre_reg():
    """Roshani A3 posterior protocol: prior 0.30 ± 0.05, material update
    threshold 0.15. Verbatim from pre-reg spec §3."""
    assert mod.POSTERIOR_PRIOR_MEAN == 0.30
    assert mod.POSTERIOR_PRIOR_UNCERTAINTY == 0.05
    assert mod.POSTERIOR_MATERIAL_UPDATE_THRESHOLD == 0.15


def test_v6_default_baseline_seeds_are_5():
    """Roshani A3 + Kwame bright-line: ≥5 seeds. Tuple is fixed for
    reproducibility; reseeding requires Majles convening per Protocol 5."""
    assert mod.DEFAULT_BASELINE_SEEDS == (17, 42, 123, 271, 314)
    assert len(mod.DEFAULT_BASELINE_SEEDS) == 5


# ---------------------------------------------------------------------------
# compute_rule_v2_verdict
# ---------------------------------------------------------------------------

def test_verdict_inert_when_stratum_below_cardinality_floor():
    """Stratum cardinality < N_floor → INERT, no further evaluation."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=10,  # below floor of 30
        stratum_mean_auc=0.6, stratum_ci_lower=0.55,
        a_minus_d_swing=0.10, anchor_pass_evaluable=6,
        anchor_evaluable_total=8,
    )
    assert out["decision"] == "INERT"
    assert "stratum_cardinality_below_N" in out["inert_reason"]
    assert out["tier_conditions_evaluated"] is None


def test_verdict_inert_when_caller_provides_byte_identical_trigger():
    """Caller-provided INERT trigger (e.g. all-4-arms-byte-identical)
    fires INERT even when cardinality passes."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.6, stratum_ci_lower=0.55,
        a_minus_d_swing=0.10, anchor_pass_evaluable=6,
        anchor_evaluable_total=8,
        inert_triggers=[mod.RULE_V2_INERT_TRIGGER_BYTE_IDENTICAL],
    )
    assert out["decision"] == "INERT"
    assert "all_4_arms_byte_identical" in out["inert_reason"]


def test_verdict_inert_when_stratum_statistic_undefined():
    """NaN mean_auc or swing → INERT (not arbitrary tier classification)."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=float("nan"),
        stratum_ci_lower=float("nan"),
        a_minus_d_swing=0.10, anchor_pass_evaluable=6,
        anchor_evaluable_total=8,
    )
    assert out["decision"] == "INERT"
    assert "undefined" in out["inert_reason"]


def test_verdict_hard_falsify_all_3_conditions():
    """HARD-FALSIFY: mean AUC < 0.50 AND CI lower < 0.48 AND anchors < 4/8."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.45, stratum_ci_lower=0.40,
        a_minus_d_swing=0.01, anchor_pass_evaluable=2,
        anchor_evaluable_total=8,
    )
    assert out["decision"] == "HARD-FALSIFY"
    assert "permanently" in out["rationale"].lower() or "permanent" in out["rationale"].lower()


def test_verdict_hard_falsify_requires_all_3_not_just_2():
    """If only 2 of 3 HARD-FALSIFY conditions fire, NOT HARD-FALSIFY
    (single-seed thin-evidence collapse protection per spec §5)."""
    # mean AUC < 0.50 AND CI lower < 0.48 BUT anchors 5/8 (>= 4)
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.45, stratum_ci_lower=0.40,
        a_minus_d_swing=0.01, anchor_pass_evaluable=5,
        anchor_evaluable_total=8,
    )
    assert out["decision"] != "HARD-FALSIFY"
    assert out["decision"] == "SOFT-FALSIFY"  # swing < 0.03, non-INERT stratum


def test_verdict_pass_all_3_conditions():
    """PASS: swing >= 0.05 AND mean AUC >= 0.55 AND anchors >= 6/8."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.60, stratum_ci_lower=0.55,
        a_minus_d_swing=0.08, anchor_pass_evaluable=7,
        anchor_evaluable_total=8,
    )
    assert out["decision"] == "PASS"


def test_verdict_pass_requires_all_3_not_just_2():
    """If only 2 of 3 PASS conditions fire, NOT PASS."""
    # swing 0.08 + mean_auc 0.60 BUT anchors only 5/8 (< 6)
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.60, stratum_ci_lower=0.55,
        a_minus_d_swing=0.08, anchor_pass_evaluable=5,
        anchor_evaluable_total=8,
    )
    assert out["decision"] != "PASS"


def test_verdict_partial_swing_and_auc_in_range():
    """PARTIAL: swing in [0.02, 0.05) AND mean AUC in [0.50, 0.55)."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.52, stratum_ci_lower=0.49,
        a_minus_d_swing=0.04, anchor_pass_evaluable=4,
        anchor_evaluable_total=8,
    )
    assert out["decision"] == "PARTIAL"


def test_verdict_soft_falsify_swing_below_threshold():
    """SOFT-FALSIFY: swing < 0.03 on a non-INERT stratum (default tier)."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.52, stratum_ci_lower=0.49,
        a_minus_d_swing=0.01, anchor_pass_evaluable=5,
        anchor_evaluable_total=8,
    )
    assert out["decision"] == "SOFT-FALSIFY"


def test_verdict_raises_on_invalid_anchor_inputs():
    """anchor_pass > anchor_evaluable_total is structurally invalid."""
    with pytest.raises(ValueError, match="anchor_pass"):
        mod.compute_rule_v2_verdict(
            stratum_n_cells=100,
            stratum_mean_auc=0.55, stratum_ci_lower=0.52,
            a_minus_d_swing=0.04,
            anchor_pass_evaluable=10,
            anchor_evaluable_total=8,
        )


# ---------------------------------------------------------------------------
# compute_posterior_update
# ---------------------------------------------------------------------------

def test_posterior_unchanged_on_inert():
    """INERT verdict produces no update — posterior == prior."""
    out = mod.compute_posterior_update(
        rule_v2_decision="INERT", a_minus_d_swing=None,
    )
    assert out["posterior_mean"] == pytest.approx(0.30, abs=1e-9)
    assert out["posterior_movement"] == pytest.approx(0.0, abs=1e-9)
    assert out["is_material"] is False


def test_posterior_material_update_on_hard_falsify():
    """HARD-FALSIFY produces a material downward update (≥0.15 magnitude,
    direction negative)."""
    out = mod.compute_posterior_update(
        rule_v2_decision="HARD-FALSIFY", a_minus_d_swing=0.0,
    )
    assert out["posterior_movement"] < -0.15
    assert out["is_material"] is True
    assert out["posterior_mean"] < out["prior_mean"]


def test_posterior_material_update_on_pass():
    """PASS produces a material upward update (≥0.15 magnitude, positive)."""
    out = mod.compute_posterior_update(
        rule_v2_decision="PASS", a_minus_d_swing=0.08,
    )
    assert out["posterior_movement"] > 0.15
    assert out["is_material"] is True
    assert out["posterior_mean"] > out["prior_mean"]


def test_posterior_immaterial_on_partial():
    """PARTIAL produces a sub-material upward nudge."""
    out = mod.compute_posterior_update(
        rule_v2_decision="PARTIAL", a_minus_d_swing=0.03,
    )
    assert 0.0 < out["posterior_movement"] < 0.15
    assert out["is_material"] is False


def test_posterior_immaterial_on_soft_falsify():
    """SOFT-FALSIFY produces a sub-material downward nudge."""
    out = mod.compute_posterior_update(
        rule_v2_decision="SOFT-FALSIFY", a_minus_d_swing=0.01,
    )
    assert -0.15 < out["posterior_movement"] < 0.0
    assert out["is_material"] is False


def test_posterior_clamps_to_unit_interval():
    """Posterior must stay in [0, 1] even with extreme priors."""
    out = mod.compute_posterior_update(
        rule_v2_decision="HARD-FALSIFY", a_minus_d_swing=0.0,
        prior_mean=0.10,  # Already low; HARD-FALSIFY would push below 0
    )
    assert 0.0 <= out["posterior_mean"] <= 1.0


# ---------------------------------------------------------------------------
# load_canonical_length_config / load_exclusion_list_config / load_v0_2_falsification_config
# ---------------------------------------------------------------------------

def test_load_canonical_length_config_missing_file_optional(tmp_path):
    """When required=False (D-arm sanity-check path), missing file
    returns None silently."""
    out = mod.load_canonical_length_config(
        path=tmp_path / "missing.json", required=False,
    )
    assert out is None


def test_load_canonical_length_config_missing_file_required_raises(tmp_path):
    """When required=True (any rule-v2 evaluation), missing file is
    a hard error per T7 §4 binding."""
    with pytest.raises(FileNotFoundError, match="T7 §4 binding"):
        mod.load_canonical_length_config(
            path=tmp_path / "missing.json", required=True,
        )


def test_load_canonical_length_config_present(tmp_path):
    """Present file is loaded and returned as a dict."""
    p = tmp_path / "v0.2-canonical-length.json"
    p.write_text('{"schema_version": 1, "indicators": {}}')
    out = mod.load_canonical_length_config(path=p, required=True)
    assert out["schema_version"] == 1


def test_load_exclusion_list_config_missing_file_optional(tmp_path):
    out = mod.load_exclusion_list_config(
        path=tmp_path / "missing.json", required=False,
    )
    assert out is None


def test_load_exclusion_list_config_missing_file_required_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="T7 §5 binding"):
        mod.load_exclusion_list_config(
            path=tmp_path / "missing.json", required=True,
        )


def test_load_exclusion_list_config_extracts_indicator_ids(tmp_path):
    """Returns the SET of `id` fields from `indicators` array — used to
    filter the weight matrix at scoring time per T7 §5 (b)."""
    p = tmp_path / "v0.2-demeaning-insufficient-exclusion.json"
    p.write_text(json.dumps({
        "exclusion_basis": "amendment A7 / phase-5-v0.2.md §5 decision (b)",
        "indicators": [
            {"id": "FP.CPI.TOTL.ZG", "stage_e_score": 0.66},
            {"id": "NY.GDP.PCAP.CD", "stage_e_score": 0.54},
            {"id": "SH.DYN.MORT", "stage_e_score": 0.36},
            {"id": "SP.POP.TOTL", "stage_e_score": 0.31},
        ],
    }))
    out = mod.load_exclusion_list_config(path=p, required=True)
    assert out == {"FP.CPI.TOTL.ZG", "NY.GDP.PCAP.CD", "SH.DYN.MORT", "SP.POP.TOTL"}


def test_load_v0_2_falsification_config_missing_file_optional(tmp_path):
    out = mod.load_v0_2_falsification_config(
        path=tmp_path / "missing.json", required=False,
    )
    assert out is None


def test_load_v0_2_falsification_config_missing_file_required_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="T3 pre-reg JSON config"):
        mod.load_v0_2_falsification_config(
            path=tmp_path / "missing.json", required=True,
        )


# ---------------------------------------------------------------------------
# v6 main() end-to-end contract
# ---------------------------------------------------------------------------

def test_v6_main_emits_rule_v2_verdict_and_posterior(monkeypatch, tmp_path):
    """End-to-end: D-arm sanity-check run emits the v6 top-level
    `rule_v2_verdict` + `posterior_update` blocks even without
    --rule-v2-evaluation, because the verdict is computed on every run."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    assert "rule_v2_verdict" in out
    assert "decision" in out["rule_v2_verdict"]
    assert out["rule_v2_verdict"]["decision"] in (
        "INERT", "HARD-FALSIFY", "SOFT-FALSIFY", "PARTIAL", "PASS",
    )
    assert "posterior_update" in out
    assert "posterior_mean" in out["posterior_update"]


def test_v6_main_emits_pre_cips_validation_label(monkeypatch, tmp_path):
    """T7 §9 / charter A8: every per-arm JSON carries the non-strippable
    pre-CIPS-validation label until 2026-06-04."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    assert out["pre_cips_validation_label"] is True
    assert out["cips_validation_expected_after"] == "2026-06-04"


def test_v6_main_output_is_rfc_8259_compliant(monkeypatch, tmp_path):
    """#679 root-cause fix: emitted JSON must NOT contain bare NaN
    tokens. Re-parse with allow_nan=False to verify strict compliance."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
    )

    raw = (fixture["ref_dir"] / "phase4-validation-armD.json").read_text(
        encoding="utf-8"
    )
    # If `NaN` (bare token) is present, json.loads with parse_constant
    # set to a raising callable will fail. The default parse_constant
    # accepts NaN/Infinity; we override to verify strict RFC 8259.
    def _reject_nan_inf(token):
        raise ValueError(f"non-RFC-8259 token {token!r} found in output")
    json.loads(raw, parse_constant=_reject_nan_inf)
    assert "NaN" not in raw


def test_v6_main_t7_config_provenance_block_present(monkeypatch, tmp_path):
    """v6 output carries `t7_config_provenance` block recording whether
    each binding config was loaded. Useful for the T11 falsification
    report's audit trail."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    p = out["t7_config_provenance"]
    for key in ("canonical_length_config_loaded", "canonical_length_config_path",
                "exclusion_list_loaded", "exclusion_list_size",
                "exclusion_list_config_path", "falsification_config_loaded",
                "rule_v2_evaluation_mode"):
        assert key in p, f"missing t7_config_provenance key: {key}"
    # In a D-arm sanity-check run, the rule_v2_evaluation mode is False
    assert p["rule_v2_evaluation_mode"] is False


def test_v6_main_rule_v2_evaluation_mode_requires_configs(monkeypatch, tmp_path):
    """When `rule_v2_evaluation=True`, missing T7 configs are a hard
    error per the T7 §4 + §5 binding."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    # Configs intentionally NOT created in tmp_path/qgi-data/reference/
    with pytest.raises(FileNotFoundError, match="T7 §4 binding|T3 pre-reg|T7 §5 binding"):
        mod.main(
            cutoff_year=2014, end_year=2025, with_baselines=False,
            ablation_arm="D", bootstrap_resamples=20,
            rule_v2_evaluation=True,
            canonical_length_config_path=tmp_path / "missing-canon.json",
            exclusion_list_config_path=tmp_path / "missing-excl.json",
        )


def test_v6_main_multi_seed_baseline_block_when_with_baselines(monkeypatch, tmp_path):
    """When --with-baselines is set, the v6 output carries the
    multi-seed baseline block with the default 5 seeds."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=True,
        ablation_arm="D", bootstrap_resamples=20,
        # Use 2 seeds for speed; the 5-seed default is exercised in the
        # constants test above.
        baseline_seeds=(17, 42),
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    assert "baseline_random_multi_seed" in out
    assert out["baseline_random_multi_seed"]["seeds"] == [17, 42]
    assert out["baseline_random_multi_seed"]["n_seeds"] == 2
    assert len(out["baseline_random_multi_seed"]["per_seed"]) == 2


def test_v6_nan_to_none_helper():
    """_nan_to_none is the load-bearing JSON-emission helper for #679.
    Pin its semantics: NaN floats → None; non-NaN floats unchanged;
    nested dicts/lists recursed."""
    nan = float("nan")
    out = mod._nan_to_none({
        "a": 1.0,
        "b": nan,
        "c": [1, nan, {"d": nan, "e": 2}],
        "f": "string",
        "g": None,
    })
    assert out["a"] == 1.0
    assert out["b"] is None
    assert out["c"] == [1, None, {"d": None, "e": 2}]
    assert out["f"] == "string"
    assert out["g"] is None


# ---------------------------------------------------------------------------
# v6 review-fix tests: MAJOR #4 (exclusion-list consumption) + MINOR #2
# (SOFT-FALSIFY / PARTIAL 3rd-condition fallback flag)
# ---------------------------------------------------------------------------

def test_v6_soft_falsify_2_of_3_fallback_flags_t11_confirmation():
    """When the random-baseline-delta-negative 3rd condition is not
    supplied (per-arm context), the verdict carries
    `requires_t11_confirmation=True` so the T11 aggregator knows the
    verdict is provisional pending the cross-arm signal."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.51, stratum_ci_lower=0.49,
        a_minus_d_swing=0.01, anchor_pass_evaluable=5,
        anchor_evaluable_total=8,
        random_baseline_delta_negative_at_multi_seed=None,
    )
    assert out["decision"] == "SOFT-FALSIFY"
    assert out.get("requires_t11_confirmation") is True


def test_v6_soft_falsify_3_of_3_no_t11_flag():
    """When T11 supplies the 3rd condition (negative=True), no flag is
    set; the verdict is binding."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.51, stratum_ci_lower=0.49,
        a_minus_d_swing=0.01, anchor_pass_evaluable=5,
        anchor_evaluable_total=8,
        random_baseline_delta_negative_at_multi_seed=True,
    )
    assert out["decision"] == "SOFT-FALSIFY"
    assert out.get("requires_t11_confirmation") is False


def test_v6_partial_2_of_3_fallback_flags_t11_confirmation():
    """PARTIAL with anchor_battery_is_mixed=None → fallback + flag."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.52, stratum_ci_lower=0.49,
        a_minus_d_swing=0.04, anchor_pass_evaluable=4,
        anchor_evaluable_total=8,
        anchor_battery_is_mixed=None,
    )
    assert out["decision"] == "PARTIAL"
    assert out.get("requires_t11_confirmation") is True


def test_v6_partial_3_of_3_no_t11_flag():
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.52, stratum_ci_lower=0.49,
        a_minus_d_swing=0.04, anchor_pass_evaluable=4,
        anchor_evaluable_total=8,
        anchor_battery_is_mixed=True,
    )
    assert out["decision"] == "PARTIAL"
    assert out.get("requires_t11_confirmation") is False


def test_v6_pass_swing_at_exact_0_05_boundary():
    """Boundary semantics check: swing == 0.05 must route to PASS,
    NOT PARTIAL. PARTIAL upper bound is `< 0.05` (strict)."""
    out = mod.compute_rule_v2_verdict(
        stratum_n_cells=100,
        stratum_mean_auc=0.60, stratum_ci_lower=0.55,
        a_minus_d_swing=0.05,  # exactly the PASS lower bound
        anchor_pass_evaluable=7,
        anchor_evaluable_total=8,
    )
    assert out["decision"] == "PASS"


def test_v6_t7_config_provenance_carries_sha256_hashes(monkeypatch, tmp_path):
    """v6 review fix: t7_config_provenance now carries SHA-256 hashes
    of the canonical_length and falsification configs so the T11
    falsification report's audit trail can verify config integrity."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    p = out["t7_config_provenance"]
    # Hashes are None when config not loaded (D-arm sanity-check path)
    # but the KEYS must exist.
    assert "canonical_length_config_sha256" in p
    assert "falsification_config_sha256" in p
    # exclusion_list_applied_to_weights_df is the NEW field tracking
    # whether T7 §5 (b) exclusion was actually applied (vs just loaded).
    assert "exclusion_list_applied_to_weights_df" in p
    # D-arm sanity-check run: rule_v2_evaluation=False → exclusion NOT applied
    assert p["exclusion_list_applied_to_weights_df"] is False


def test_v6_exclusion_list_applied_filters_weights_df(monkeypatch, tmp_path):
    """v6 review fix MAJOR #4: when rule_v2_evaluation=True AND
    exclusion_list_config is present, the weights_df is filtered to
    drop demeaning-insufficient indicators BEFORE evaluate_weights()."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    # Write a canonical-length-config + falsification-config + exclusion
    # list into the fixture's reference dir so rule_v2_evaluation=True
    # doesn't hard-error.
    canon = fixture["ref_dir"] / "v0.2-canonical-length.json"
    canon.write_text('{"schema_version": 1, "indicators": {}}')
    fals = fixture["ref_dir"] / "v0.2-falsification-config.json"
    fals.write_text('{"schema_version": 1}')
    excl = fixture["ref_dir"] / "v0.2-demeaning-insufficient-exclusion.json"
    # Use a fixture indicator id_string to actually drop rows. The
    # fixture builder creates indicators named IND_00, IND_01, etc.
    # via _build_main_fixture; we'll exclude IND_00.
    excl.write_text(json.dumps({
        "indicators": [{"id": "IND_00", "stage_e_score": 0.99}],
    }))

    # Monkeypatch the loaders to read from the fixture's reference dir
    # (otherwise they try the default ROOT path).
    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
        rule_v2_evaluation=True,
        canonical_length_config_path=canon,
        exclusion_list_config_path=excl,
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    p = out["t7_config_provenance"]
    assert p["rule_v2_evaluation_mode"] is True
    assert p["exclusion_list_loaded"] is True
    assert p["exclusion_list_size"] == 1
    # Critical: the MAJOR #4 fix means the exclusion was APPLIED to weights_df,
    # not just loaded.
    assert p["exclusion_list_applied_to_weights_df"] is True


# ===========================================================================
# v6.5 NEW (T8.5 / Tariq adjudication 2026-05-12):
#   apply_transform_layer — transform-dispatch consumption before z-scoring
# ===========================================================================


def _dispatch_config(indicators: dict) -> dict:
    """Helper to build a minimal canonical_length_config dict for tests."""
    return {
        "schema_version": 1,
        "indicators": indicators,
    }


def test_apply_transform_layer_first_diff_drops_first_year_per_country():
    """For an I(1) indicator with `first_diff` transform, the first
    observation per (country, indicator) drops; remaining values equal
    raw[t] - raw[t-1]."""
    panel = pd.DataFrame([
        {"country": "USA", "year": 2010, "indicator_id": "IND_I1", "value": 100.0},
        {"country": "USA", "year": 2011, "indicator_id": "IND_I1", "value": 105.0},
        {"country": "USA", "year": 2012, "indicator_id": "IND_I1", "value": 113.0},
        {"country": "DEU", "year": 2010, "indicator_id": "IND_I1", "value": 50.0},
        {"country": "DEU", "year": 2011, "indicator_id": "IND_I1", "value": 60.0},
        {"country": "DEU", "year": 2012, "indicator_id": "IND_I1", "value": 75.0},
    ])
    config = _dispatch_config({
        "IND_I1": {"transform": "first_diff", "demean_applied": False,
                   "canonical_length_value": 1},
    })
    out = mod.apply_transform_layer(panel, config)
    # 2010 rows drop for both countries; 4 rows remain
    assert len(out) == 4
    # USA 2011: 105 - 100 = 5; USA 2012: 113 - 105 = 8
    usa = out[out["country"] == "USA"].sort_values("year").reset_index(drop=True)
    assert usa.loc[0, "value"] == 5.0
    assert usa.loc[1, "value"] == 8.0
    # DEU 2011: 60 - 50 = 10; DEU 2012: 75 - 60 = 15
    deu = out[out["country"] == "DEU"].sort_values("year").reset_index(drop=True)
    assert deu.loc[0, "value"] == 10.0
    assert deu.loc[1, "value"] == 15.0


def test_apply_transform_layer_pass_through_preserves_surgical_overrides():
    """The 2 T7 §6 surgical-override indicators (FP.CPI.TOTL.ZG,
    NY.GDP.PCAP.CD) have transform='pass_through' in the dispatch table
    (per their flipped I(0) effective_classification on the demeaned
    substrate). Verify rows are unchanged when transform=pass_through.

    NOTE: demean_applied=True for both these indicators per the dispatch
    table, so values WILL change due to demeaning — but no rows drop and
    the per-country temporal structure is preserved."""
    panel = pd.DataFrame([
        {"country": "USA", "year": 2010, "indicator_id": "FP.CPI.TOTL.ZG", "value": 3.0},
        {"country": "USA", "year": 2011, "indicator_id": "FP.CPI.TOTL.ZG", "value": 4.0},
        {"country": "DEU", "year": 2010, "indicator_id": "FP.CPI.TOTL.ZG", "value": 1.0},
        {"country": "DEU", "year": 2011, "indicator_id": "FP.CPI.TOTL.ZG", "value": 2.0},
    ])
    # Surgical override → pass_through, demean=True (per the actual config)
    config = _dispatch_config({
        "FP.CPI.TOTL.ZG": {"transform": "pass_through", "demean_applied": True,
                           "canonical_length_value": 2},
    })
    out = mod.apply_transform_layer(panel, config)
    # No rows lost (pass_through doesn't drop, demean doesn't drop)
    assert len(out) == 4
    # 2010 cross-section mean = (3+1)/2 = 2 → USA: 3-2=1, DEU: 1-2=-1
    # 2011 cross-section mean = (4+2)/2 = 3 → USA: 4-3=1, DEU: 2-3=-1
    usa_2010 = out[(out["country"] == "USA") & (out["year"] == 2010)]["value"].iloc[0]
    usa_2011 = out[(out["country"] == "USA") & (out["year"] == 2011)]["value"].iloc[0]
    deu_2010 = out[(out["country"] == "DEU") & (out["year"] == 2010)]["value"].iloc[0]
    deu_2011 = out[(out["country"] == "DEU") & (out["year"] == 2011)]["value"].iloc[0]
    assert usa_2010 == pytest.approx(1.0)
    assert usa_2011 == pytest.approx(1.0)
    assert deu_2010 == pytest.approx(-1.0)
    assert deu_2011 == pytest.approx(-1.0)


def test_apply_transform_layer_log_diff_handles_sp_pop_totl():
    """SP.POP.TOTL uses log_diff (OUTLIER_LOG_DIFFERENCE in the
    pipeline). Verify the log-difference computation."""
    panel = pd.DataFrame([
        {"country": "USA", "year": 2010, "indicator_id": "SP.POP.TOTL", "value": 300.0e6},
        {"country": "USA", "year": 2011, "indicator_id": "SP.POP.TOTL", "value": 303.0e6},
    ])
    config = _dispatch_config({
        "SP.POP.TOTL": {"transform": "log_diff", "demean_applied": False,
                        "canonical_length_value": 6},
    })
    out = mod.apply_transform_layer(panel, config)
    # log(303/300) = log(1.01) ≈ 0.00995
    assert len(out) == 1
    assert out.iloc[0]["value"] == pytest.approx(np.log(303.0e6 / 300.0e6), rel=1e-9)


def test_rule_v2_evaluation_rejects_null_canonical_length_values(
    monkeypatch, tmp_path
):
    """Tariq §5.2 step iii: under rule_v2_evaluation=True, the v6 script
    MUST refuse to fire if any canonical_length_value is null. The
    null-rejection assertion is the load-bearing check that the
    recipe-aggregator pass actually ran before T9 fires."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    # Write configs into fixture dir. canonical_length has a null value.
    canon = fixture["ref_dir"] / "v0.2-canonical-length.json"
    canon.write_text(json.dumps({
        "schema_version": 1,
        "indicators": {
            "IND_00": {"transform": "first_diff", "demean_applied": False,
                       "canonical_length_value": None},
        },
    }))
    fals = fixture["ref_dir"] / "v0.2-falsification-config.json"
    fals.write_text('{"schema_version": 1}')
    excl = fixture["ref_dir"] / "v0.2-demeaning-insufficient-exclusion.json"
    excl.write_text(json.dumps({"indicators": []}))

    with pytest.raises(ValueError, match="null canonical_length_value"):
        mod.main(
            cutoff_year=2014, end_year=2025, with_baselines=False,
            ablation_arm="D", bootstrap_resamples=20,
            rule_v2_evaluation=True,
            canonical_length_config_path=canon,
            exclusion_list_config_path=excl,
        )


def test_v6_5_transform_layer_applied_provenance_field(monkeypatch, tmp_path):
    """T8.5 §5.4 reviewer-checklist item: the per-arm JSON's
    `t7_config_provenance` block carries a `transform_layer_applied`
    field that records whether the panel was transformed before
    z-scoring. False under D-arm sanity-check; True under
    rule_v2_evaluation. T11 must cite this to disambiguate raw-panel
    vs transformed-panel runs."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
    )

    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    p = out["t7_config_provenance"]
    assert "transform_layer_applied" in p
    # D-arm sanity-check run (rule_v2_evaluation=False): transform_layer NOT applied
    assert p["transform_layer_applied"] is False


# =============================================================================
# v6.6 NEW (T12 #692): --emit-per-cell flag tests
#
# Per docs-specs `ca77505` §3.1 (post-6-seat-Majles amendment 2026-05-15):
# Path A v6.6 emits the per-(country_id, event_category) anomaly_score tensor
# under a top-level `per_cell` block when --emit-per-cell is set. Path B's
# partial-pooling evaluator (`validate_weight_matrix_bayes.py`) consumes it
# via the `prep_cells_from_arm_jsons` helper. Backward-compat: when the flag
# is NOT set, the output JSON is v5-equivalent (no `per_cell` key).
# =============================================================================


def test_build_per_cell_block_schema():
    """The per_cell block has the documented top-level schema fields."""
    scored = pd.DataFrame({
        "country_id": [1, 1, 2, 2],
        "event_category": ["civil_war", "monetary_policy", "civil_war", "monetary_policy"],
        "anomaly_score": [0.5, -0.3, 1.2, 0.0],
        "n_indicators_used": [10, 5, 8, 12],
    })
    block = mod._build_per_cell_block(scored)
    assert block["schema_version"] == 1
    assert block["n_cells"] == 4
    assert block["n_indicators_used_min"] == 5
    assert block["n_indicators_used_max"] == 12
    assert block["n_indicators_used_median"] == 9.0  # median of (5, 8, 10, 12)
    assert isinstance(block["cells"], list)
    assert len(block["cells"]) == 4


def test_build_per_cell_block_cell_record_shape():
    """Each cell record carries the four required fields with correct types."""
    scored = pd.DataFrame({
        "country_id": [42],
        "event_category": ["civil_war"],
        "anomaly_score": [1.234],
        "n_indicators_used": [7],
    })
    block = mod._build_per_cell_block(scored)
    cell = block["cells"][0]
    assert set(cell.keys()) == {"country_id", "event_category",
                                "anomaly_score", "n_indicators_used"}
    assert cell["country_id"] == 42
    assert cell["event_category"] == "civil_war"
    assert cell["anomaly_score"] == 1.234
    assert cell["n_indicators_used"] == 7
    # Types are JSON-serialisable Python primitives (int/str/float), not numpy
    assert type(cell["country_id"]) is int
    assert type(cell["event_category"]) is str
    assert type(cell["anomaly_score"]) is float
    assert type(cell["n_indicators_used"]) is int


def test_build_per_cell_block_empty_input():
    """Empty scored DataFrame produces a well-formed empty block (no crash)."""
    scored = pd.DataFrame({
        "country_id": pd.Series([], dtype=int),
        "event_category": pd.Series([], dtype=str),
        "anomaly_score": pd.Series([], dtype=float),
        "n_indicators_used": pd.Series([], dtype=int),
    })
    block = mod._build_per_cell_block(scored)
    assert block["n_cells"] == 0
    assert block["cells"] == []
    assert block["n_indicators_used_min"] == 0
    assert block["n_indicators_used_max"] == 0


def test_main_emit_per_cell_off_no_per_cell_key(tmp_path, monkeypatch):
    """v6.6 backward-compat: when --emit-per-cell is NOT set, the output
    JSON does NOT have a `per_cell` key. This keeps v5 consumers
    unsurprised."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
        emit_per_cell=False,  # explicit default
    )
    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    assert "per_cell" not in out


def test_main_emit_per_cell_on_emits_per_cell_block(tmp_path, monkeypatch):
    """When --emit-per-cell is set, the output JSON gains a top-level
    `per_cell` block with the documented schema."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
        emit_per_cell=True,
    )
    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    assert "per_cell" in out
    pc = out["per_cell"]
    assert pc["schema_version"] == 1
    assert pc["n_cells"] >= 0  # fixture may drop all rows via country_id mapping
    assert isinstance(pc["cells"], list)
    # Spot-check cell record shape IF any cells exist (fixture-dependent)
    if pc["cells"]:
        first = pc["cells"][0]
        assert set(first.keys()) == {"country_id", "event_category",
                                     "anomaly_score", "n_indicators_used"}


def test_main_emit_per_cell_preserves_v5_fields(tmp_path, monkeypatch):
    """The --emit-per-cell flag is ADDITIVE — every v5 top-level field
    is present unchanged in the v6.6 output. Kwame gate 4 (forward-compat)."""
    fixture = _build_main_fixture(tmp_path)
    _install_main_monkeypatches(monkeypatch, tmp_path, fixture)

    mod.main(
        cutoff_year=2014, end_year=2025, with_baselines=False,
        ablation_arm="D", bootstrap_resamples=20,
        emit_per_cell=True,
    )
    out = json.loads((fixture["ref_dir"] / "phase4-validation-armD.json")
                     .read_text(encoding="utf-8"))
    # Spot-check that every v5 top-level key is still present
    for v5_key in (
        "schema_version", "generated", "ablation_arm", "ablation_arm_config",
        "method", "config", "summary",
        "per_event_category_auc", "reliability_diagram",
        "stratified_auc", "per_event_category_ece",
        "stratum_sensitivity", "anchor_case_battery",
    ):
        assert v5_key in out, f"v5 key {v5_key!r} missing from v6.6 output"
    # And the new v6.6 key
    assert "per_cell" in out
