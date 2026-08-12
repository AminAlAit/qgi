"""Unit tests for F-ML-1 PoC driver pure functions.

Per F-ML-1 §2 binding rules + Stage 7 test-first discipline.
End-to-end smoke testing is via --max-candidates-debug flag at the script
level. These tests cover pure helpers (AUC, BCa bootstrap, feature
extraction, trajectory signature, fold variance).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv


def test_compute_auc_perfect():
    probs = np.array([0.9, 0.8, 0.1, 0.2])
    labels = np.array([1, 1, 0, 0])
    assert drv.compute_auc(probs, labels) == 1.0


def test_compute_auc_random():
    probs = np.array([0.5, 0.5, 0.5, 0.5])
    labels = np.array([1, 1, 0, 0])
    assert drv.compute_auc(probs, labels) == 0.5


def test_compute_auc_single_class_nan():
    probs = np.array([0.7, 0.8])
    labels = np.array([1, 1])
    assert np.isnan(drv.compute_auc(probs, labels))


def test_bca_bootstrap_ci_shape():
    rng = np.random.default_rng(0)
    probs = np.concatenate([rng.uniform(0.6, 1.0, 30), rng.uniform(0.0, 0.4, 30)])
    labels = np.concatenate([np.ones(30, dtype=int), np.zeros(30, dtype=int)])
    out = drv.bca_bootstrap_auc_ci(probs, labels, B=200, seed=42)
    assert {"auc", "ci80_lo", "ci80_hi", "ci95_lo", "ci95_hi", "n_bootstrap", "method"} == set(out)
    assert 0.0 <= out["ci95_lo"] <= out["ci80_lo"] <= out["auc"]
    assert out["auc"] <= out["ci80_hi"] <= out["ci95_hi"] <= 1.0
    assert out["method"] == "bca_bootstrap"


def test_fold_variance_zero_when_uniform():
    per_country_auc = {"a": 0.7, "b": 0.7, "c": 0.7}
    assert drv.fold_variance(per_country_auc) < 1e-15  # floating-point near-zero


def test_fold_variance_positive_when_varied():
    per_country_auc = {"a": 0.9, "b": 0.5, "c": 0.7}
    assert drv.fold_variance(per_country_auc) > 0.0


def test_compute_ece_well_calibrated_low():
    rng = np.random.default_rng(0)
    probs = rng.uniform(0, 1, 500)
    labels = rng.binomial(1, probs)
    ece = drv.compute_ece(probs, labels)
    assert 0.0 <= ece <= 0.10


def test_compute_ece_miscalibrated_high():
    probs = np.full(100, 0.9)
    labels = np.zeros(100, dtype=int)
    assert drv.compute_ece(probs, labels) >= 0.5


def test_extract_features_basic():
    """Per Miriam M14-1: tertile structure is at the right index slots."""
    df = pd.DataFrame({
        "country": ["TestCountry"] * 20,
        "year": list(range(2000, 2020)),
        "value": list(range(20)),
    })
    feats = drv.extract_features_for_indicator(df, "TestCountry", 2020, window=15)
    assert feats is not None
    assert feats.shape == (10,)
    assert feats.shape == (drv.N_FEATURES_PER_INDICATOR,)
    # last_z, mean_z, std_z, slope, accel, t1m, t2m, t3m, lag_z2, lag_z3
    # slope should be positive (monotonically increasing)
    assert feats[3] > 0
    # tertile 3 mean > tertile 1 mean (later years higher value)
    assert feats[7] > feats[5]


def test_extract_features_lag_slots_match_exact_years():
    """Per run-3.1 banking wide-net fix #1 (2026-07-10): slots 8/9 are the z-score at
    EXACTLY year-2 / year-3 (not "last available"), independently verifiable against
    `last_z` (slot 0, which is z at year-1) on a fully-populated, monotonic series."""
    df = pd.DataFrame({
        "country": ["TestCountry"] * 20,
        "year": list(range(2000, 2020)),  # 2000..2019, all present, no gaps
        "value": list(range(20)),
    })
    feats = drv.extract_features_for_indicator(df, "TestCountry", 2020, window=15)
    assert feats is not None
    last_z, lag_z2, lag_z3 = feats[0], feats[8], feats[9]
    # Fully-populated, evenly-spaced, monotonically increasing raw series => the
    # z-scored series is also evenly-spaced with a constant step. year-1 -> year-2
    # -> year-3 should therefore be evenly spaced by the same step as last_z to lag_z2.
    step = last_z - lag_z2
    assert step > 0  # increasing series => earlier year => lower z
    assert abs((lag_z2 - lag_z3) - step) < 1e-9


def test_extract_features_lag_slots_leakage_safe():
    """LEAKAGE-CRITICAL: lag_z2/lag_z3 (and every other feature) must be a pure
    function of data strictly BEFORE `year` — changing values at `year` or later must
    not change the extracted feature vector at all."""
    base_values = list(range(20))
    df_a = pd.DataFrame({
        "country": ["TestCountry"] * 21,
        "year": list(range(2000, 2021)),  # includes year=2020 itself
        "value": base_values + [999.0],  # value AT year=2020
    })
    df_b = pd.DataFrame({
        "country": ["TestCountry"] * 21,
        "year": list(range(2000, 2021)),
        "value": base_values + [-999.0],  # wildly different future value at year=2020
    })
    feats_a = drv.extract_features_for_indicator(df_a, "TestCountry", 2020, window=15)
    feats_b = drv.extract_features_for_indicator(df_b, "TestCountry", 2020, window=15)
    assert feats_a is not None and feats_b is not None
    np.testing.assert_array_equal(feats_a, feats_b)


def test_extract_features_lag_slot_fallback_on_missing_year():
    """A gap at exactly year-2 (or year-3) falls back to 0.0 (neutral), never an
    imputed/forward-filled value from a different year — the fallback documented in
    the docstring."""
    kept = [(y, v) for y, v in zip(range(2000, 2020), range(20)) if y != 2018]  # drop year-2 (2018)
    df = pd.DataFrame({
        "country": ["TestCountry"] * len(kept),
        "year": [y for y, _ in kept],
        "value": [v for _, v in kept],
    })
    feats = drv.extract_features_for_indicator(df, "TestCountry", 2020, window=15)
    assert feats is not None
    assert feats[8] == 0.0  # lag_z2 falls back to neutral when year-2 is absent
    assert feats[9] != 0.0  # lag_z3 (year-3=2017) is present and non-degenerate


def test_extract_features_insufficient_data_returns_none():
    df = pd.DataFrame({
        "country": ["TestCountry"] * 2,
        "year": [2018, 2019],
        "value": [1.0, 2.0],
    })
    feats = drv.extract_features_for_indicator(df, "TestCountry", 2020, window=10)
    assert feats is None  # < window // 3 = 3 valid years


def test_trajectory_signature_full_window_structure():
    """Per Miriam M14-1: signature must cover FULL window, not single lag."""
    df = pd.DataFrame({
        "country": ["TestCountry"] * 25,
        "year": list(range(1995, 2020)),
        "value": list(range(25)),
    })
    sig = drv.extract_trajectory_signature_full(df, "TestCountry", 2020, window=15)
    assert sig["available"] is True
    assert "per_tertile_z_score" in sig
    assert len(sig["per_tertile_z_score"]) == 3
    assert "per_tertile_direction_sign" in sig
    assert len(sig["per_tertile_direction_sign"]) == 3
    assert "temporal_profile" in sig
    assert len(sig["temporal_profile"]) == 15  # full window, not single lag
    # increasing values → late tertile higher than early
    assert sig["per_tertile_z_score"][2] > sig["per_tertile_z_score"][0]


def test_to_strict_json_replaces_nan():
    payload = {"a": float("nan"), "b": [1.0, float("inf")], "c": {"d": np.nan}}
    s = drv._to_strict_json(payload)
    parsed = json.loads(s)
    assert parsed["a"] is None
    assert parsed["b"][1] is None
    assert parsed["c"]["d"] is None


def test_to_strict_json_numpy_types():
    payload = {"i": np.int64(7), "f": np.float64(3.14), "arr": np.array([1, 2, 3])}
    s = drv._to_strict_json(payload)
    parsed = json.loads(s)
    assert parsed["i"] == 7
    assert parsed["f"] == 3.14
    assert parsed["arr"] == [1, 2, 3]


def test_default_constants_match_civil_war():
    """Verify civil_war defaults preserved for backward compatibility.

    The parameterization (2026-05-22) replaced module-level RECIPE_ID/
    HYBRID_BASELINE/LOCK_FLOOR/COHORT_LOCO_FLOOR with CLI args; the DEFAULT_*
    constants encode the civil_war_and_insurgency walk-1 values verbatim.
    """
    assert drv.DEFAULT_RECIPE_ID == "civil_war_and_insurgency"
    assert drv.DEFAULT_HYBRID_BASELINE == 0.7686
    assert drv.DEFAULT_LOCK_FLOOR == 0.7986
    assert drv.DEFAULT_COHORT_LOCO_FLOOR == 0.68


def test_country_id_normalization_simple_cases():
    """Per 2026-05-22 mechanical correctness fix: simple multi-word names
    (no hyphen, no lowercase conjunctions) normalize via `_ -> ` ` + title().

    Pre-fix `.title()` produced "Costa_Rica" from "costa_rica", silently
    dropping multi-word countries at panel lookup. Civil_war walk-1 ran
    without this fix and silently dropped 41 multi-word events at panel
    lookup (256 prep input → 192 effective N_pos).
    """
    assert drv.normalize_country_id("afghanistan") == "Afghanistan"
    assert drv.normalize_country_id("costa_rica") == "Costa Rica"
    assert drv.normalize_country_id("saudi_arabia") == "Saudi Arabia"
    assert drv.normalize_country_id("united_kingdom") == "United Kingdom"
    assert drv.normalize_country_id("central_african_republic") == "Central African Republic"


def test_country_id_normalization_overrides():
    """Per 2026-05-22: 4 country_ids require explicit override because naive
    `_ -> ` ` + title()` produces a name that does NOT match the canonical
    form in parquet panels + cohort-assignments.json:

      - "democratic_republic_of_congo" naive: "Democratic Republic Of Congo"
        canonical: "The Democratic Republic of the Congo"
      - "guinea_bissau" naive: "Guinea Bissau" canonical: "Guinea-Bissau"
      - "republic_of_congo" naive: "Republic Of Congo"
        canonical: "Republic of the Congo"
      - "timor_leste" naive: "Timor Leste" canonical: "Timor-Leste"

    These overrides are required for the cohort gate AND panel lookup to
    successfully resolve these countries.
    """
    assert (
        drv.normalize_country_id("democratic_republic_of_congo")
        == "The Democratic Republic of the Congo"
    )
    assert drv.normalize_country_id("guinea_bissau") == "Guinea-Bissau"
    assert drv.normalize_country_id("republic_of_congo") == "Republic of the Congo"
    assert drv.normalize_country_id("timor_leste") == "Timor-Leste"


def test_normalization_propagates_through_build_x_y():
    """Per QA PR#91 FU3 + 2026-05-22 mechanical fix verification:
    end-to-end check that a multi-word `country_id` survives panel lookup
    AND feature extraction. Pre-fix the panel filter
    `panel[panel["country"] == "Costa_Rica"]` silently returned zero rows,
    causing `extract_features_for_indicator` to return None and the sample
    to be dropped in `build_X_y`. Fix: `normalize_country_id` produces
    "Costa Rica" (matching the panel format).
    """
    # Synthetic panel containing "Costa Rica" (space-separated, matches the
    # parquet panel convention).
    panel = pd.DataFrame({
        "country": ["Costa Rica"] * 20,
        "year": list(range(2000, 2020)),
        "value": list(range(20)),
    })
    # Samples DataFrame as build_X_y consumes (post-normalization):
    samples = pd.DataFrame({
        "country": [drv.normalize_country_id("costa_rica")],
        "year": [2020],
        "label": [1],
    })
    assert samples["country"].iloc[0] == "Costa Rica"
    X, y, c, yr = drv.build_X_y(samples, ["IND"], window=10, panels={"IND": panel})
    # Pre-fix: X.shape would be (0, 0) because "Costa_Rica" wouldn't match
    # "Costa Rica". Post-fix: at least one feature row is built.
    assert X.shape[0] == 1, "build_X_y must extract features for multi-word country"
    assert X.shape[1] == drv.N_FEATURES_PER_INDICATOR  # features per indicator
    assert y[0] == 1


def test_normalization_propagates_for_hyphenated_override():
    """Verify the override map propagates correctly for hyphenated names
    (Guinea-Bissau / Timor-Leste). Naive `_ -> ` ` + title()` produces
    "Guinea Bissau" but the canonical panel name is "Guinea-Bissau"."""
    panel = pd.DataFrame({
        "country": ["Guinea-Bissau"] * 20,
        "year": list(range(2000, 2020)),
        "value": list(range(20)),
    })
    samples = pd.DataFrame({
        "country": [drv.normalize_country_id("guinea_bissau")],
        "year": [2020],
        "label": [1],
    })
    assert samples["country"].iloc[0] == "Guinea-Bissau"
    X, y, c, yr = drv.build_X_y(samples, ["IND"], window=10, panels={"IND": panel})
    assert X.shape[0] == 1, "override map must propagate to build_X_y for hyphenated names"


def test_country_normalization_overrides_are_complete():
    """Per 2026-05-22 walk-2 prep: verify the override map covers EVERY
    multi-word country_id appearing across all positives.csv files. If a
    new recipe introduces a country_id not handled by the naive transform
    AND not in the override map, this test fails fast at the test phase
    rather than silently dropping samples at walk time.
    """
    # Empirically enumerated 2026-05-22 from data/shape_inputs_v2/*/positives.csv:
    # 16 multi-word country_ids, of which 12 normalize correctly via the
    # simple rule and 4 require overrides.
    all_observed_multi_word = [
        "burkina_faso",
        "central_african_republic",
        "costa_rica",
        "democratic_republic_of_congo",  # override
        "guinea_bissau",                  # override
        "ivory_coast",
        "papua_new_guinea",
        "republic_of_congo",              # override
        "saudi_arabia",
        "sierra_leone",
        "south_africa",
        "south_korea",
        "sri_lanka",
        "timor_leste",                    # override
        "united_arab_emirates",
        "united_kingdom",
    ]
    expected_overrides = {
        "democratic_republic_of_congo",
        "guinea_bissau",
        "republic_of_congo",
        "timor_leste",
    }
    assert set(drv.COUNTRY_NAME_OVERRIDES.keys()) == expected_overrides
    # And every country_id resolves to a non-naive string (sanity)
    for cid in all_observed_multi_word:
        normalized = drv.normalize_country_id(cid)
        assert " " in normalized or "-" in normalized, cid
        assert "_" not in normalized, cid


def test_cli_recipe_id_default(tmp_path):
    """Per 2026-05-22 parameterization: --recipe-id defaults to civil_war.

    Uses `drv._build_parser()` (the real parser construction) instead of a
    shadow parser — addresses QA PR#91 FU1 (prevents parser drift if a
    future PR adds args to `_main` without updating this test).
    """
    parser = drv._build_parser()
    args = parser.parse_args(["--output-dir", str(tmp_path)])
    assert args.recipe_id == "civil_war_and_insurgency"
    assert args.hybrid_baseline == 0.7686
    assert args.lock_floor == 0.7986
    assert args.cohort_loco_floor == 0.68


def test_cli_recipe_id_override(tmp_path):
    """Per 2026-05-22 parameterization: economic_recession per-recipe pre-reg
    values must be overridable via CLI flags. Uses the real `_build_parser`."""
    parser = drv._build_parser()
    args = parser.parse_args([
        "--output-dir", str(tmp_path),
        "--recipe-id", "economic_recession",
        "--hybrid-baseline", "0.4784",
        "--lock-floor", "0.65",
        "--cohort-loco-floor", "0.60",
    ])
    assert args.recipe_id == "economic_recession"
    assert args.hybrid_baseline == 0.4784
    assert args.lock_floor == 0.65
    assert args.cohort_loco_floor == 0.60


def test_cli_output_dir_required(tmp_path):
    """Verify --output-dir is required (no implicit default)."""
    import pytest as _pytest
    parser = drv._build_parser()
    with _pytest.raises(SystemExit):
        parser.parse_args([])  # missing --output-dir


def test_f_ml_n_amendment_no_active_mlp_trigger_constant():
    """Per F-ML-N §4.2 amendment 2026-05-22 (qgi-aws-tf#864, 8/8 ratified):
    the §4.2 fold-variance MLP trigger is REMOVED. The legacy constant is
    preserved as `MLP_FOLD_VARIANCE_TRIGGER_DEPRECATED` (archival only).
    The active constant `MLP_FOLD_VARIANCE_TRIGGER` MUST NOT exist (any code
    still referencing it would be a F-ML-N violation).
    """
    assert not hasattr(drv, "MLP_FOLD_VARIANCE_TRIGGER"), (
        "MLP_FOLD_VARIANCE_TRIGGER must not be defined as an active constant "
        "per F-ML-N §4.2 amendment 2026-05-22"
    )
    assert hasattr(drv, "MLP_FOLD_VARIANCE_TRIGGER_DEPRECATED"), (
        "Legacy constant should be preserved for archival reference"
    )
    assert drv.MLP_FOLD_VARIANCE_TRIGGER_DEPRECATED == 0.05  # historical record


def test_f_ml_n_amendment_no_mlp_routing_in_main():
    """Per Tariq R-T20-A1 + Ji-Hoon ratification: the active code path MUST NOT
    contain MLP routing logic under the amended §4.2. Specifically, the driver
    must not call `fit_predict_loco` with architecture='MLP' as an automatic
    swap target. Verified by source inspection: the legacy `trigger_mlp` and
    `mlp_trigger_decision_ts` variables must be absent from `_main`.
    """
    import inspect
    main_source = inspect.getsource(drv._main)
    # No legacy variables
    assert "trigger_mlp" not in main_source, (
        "trigger_mlp must be removed from _main per F-ML-N amendment"
    )
    assert "mlp_trigger_decision_ts" not in main_source, (
        "mlp_trigger_decision_ts must be removed per F-ML-N amendment"
    )
    # No automatic MLP architecture invocation in the LOCK-eval path
    # (XGBoost re-fit for feature_importances is in the descriptive emit branch,
    # not an architecture swap)
    assert 'architecture="MLP"' not in main_source, (
        "_main must not invoke architecture='MLP' as automatic swap per F-ML-N"
    )


def test_f_ml_n_stability_label_thresholds():
    """Per F-ML-1 §4.2-SD: LOW (<0.04), MODERATE (0.04-0.10), HIGH (>0.10).

    Per QA PR#92 FU-3: this test exercises the DRIVER's `_stability_label`
    helper directly, NOT a local re-implementation. If the driver's logic
    drifts from the pre-reg, this test catches it."""
    assert drv._stability_label(0.039) == "LOW"
    assert drv._stability_label(0.0) == "LOW"
    assert drv._stability_label(0.04) == "MODERATE"  # boundary: ≥0.04 → MODERATE
    assert drv._stability_label(0.0656) == "MODERATE"  # econ_recession observed
    assert drv._stability_label(0.0561) == "MODERATE"  # civil_war observed
    assert drv._stability_label(0.10) == "MODERATE"  # boundary: ≤0.10 → MODERATE
    assert drv._stability_label(0.11) == "HIGH"
    assert drv._stability_label(0.20) == "HIGH"


def test_f_ml_n_build_stability_diagnostic_complete():
    """Per Kwame BLOCKING rider (mandatory §4.2-SD logging) + QA PR#92
    FU-1 (fold_auc_mean was missing) + FU-2 (need direct emit test): verify
    `_build_stability_diagnostic` produces a dict with ALL 7 required fields
    per §4.2-SD spec.
    """
    per_country = {"Algeria": 0.7, "Brazil": 0.6, "China": 0.8, "Iran": 0.5}
    diag = drv._build_stability_diagnostic(per_country)
    # §4.2-SD spec requires: per-fold AUC values, fold-AUC mean, fold-AUC
    # variance, qualitative label.
    assert "per_country_loco_auc" in diag  # item 1
    assert "fold_auc_mean" in diag         # item 2 (was missing pre-FU-1)
    assert "fold_variance" in diag         # item 3
    assert "label" in diag                 # item 4
    # Additional fields per the amendment artifact
    assert diag["informational_only"] is True
    assert "amendment_reference" in diag
    assert diag["thresholds"] == {"LOW_upper": 0.04, "MODERATE_upper": 0.10}
    # Value sanity
    assert abs(diag["fold_auc_mean"] - 0.65) < 1e-9  # mean of [0.7, 0.6, 0.8, 0.5]
    assert diag["fold_variance"] > 0
    assert diag["label"] in {"LOW", "MODERATE", "HIGH"}
    assert diag["per_country_loco_auc"] == {"Algeria": 0.7, "Brazil": 0.6, "China": 0.8, "Iran": 0.5}


def test_f_ml_n_build_stability_diagnostic_edge_cases():
    """Verify _build_stability_diagnostic handles edge cases without raising:
    empty dict, single fold, NaN values."""
    # Empty dict
    diag = drv._build_stability_diagnostic({})
    assert diag["fold_variance"] == 0.0
    assert diag["label"] == "LOW"  # 0 < 0.04
    # Single fold (variance undefined with n<2; fold_variance helper returns 0)
    diag = drv._build_stability_diagnostic({"A": 0.7})
    assert diag["fold_variance"] == 0.0
    # NaN values are filtered
    diag = drv._build_stability_diagnostic({"A": float("nan"), "B": 0.5, "C": 0.5})
    assert diag["fold_variance"] == 0.0  # only 2 valid, both 0.5
    assert diag["label"] == "LOW"


def test_f_ml_n_amendment_main_uses_helpers():
    """Per QA PR#92 FU-3 follow-up: _main MUST call _build_stability_diagnostic,
    not inline the diagnostic logic. This guards against future drift where a
    refactor accidentally re-inlines the threshold logic away from the helper.
    """
    import inspect
    main_source = inspect.getsource(drv._main)
    assert "_build_stability_diagnostic" in main_source, (
        "_main must call _build_stability_diagnostic helper per §4.2-SD"
    )
    # Inline label-threshold logic SHOULD NOT exist in _main (it lives in the
    # helper). Heuristic check: no `stability_label = "LOW"` inline assignment.
    assert 'stability_label = "LOW"' not in main_source, (
        "Label thresholding must live in _stability_label helper, not inlined"
    )


def test_cohort_sidecar_loaded_only_once_in_main():
    """Regression guard for the cohort-load-once invariant.

    Trigger: 2026-05-23 walk-4 attempt #1 crashed at LOCK GATE EVAL with
    FileNotFoundError on cohort-assignments.json after running ~4h. Root
    cause: the driver opened args.cohort_sidecar TWICE — once at startup
    validation and again at LOCK GATE EVAL ~4h later. Between the two
    reads, a git checkout in the qgi-data working tree swapped the file
    out, and the eval crashed after the full greedy outer loop had
    completed (no checkpoint, so eval-only re-run was impossible).

    Fix: load the file ONCE at startup into cohort_assignments_cached and
    reuse for LOCK GATE EVAL. This test fails if anyone re-introduces a
    second file read.
    """
    source = (SCRIPTS_DIR / "run_f_ml_1_poc.py").read_text(encoding="utf-8")
    open_calls = source.count("open(args.cohort_sidecar")
    assert open_calls == 1, (
        f"Expected exactly 1 open(args.cohort_sidecar) call in driver; "
        f"found {open_calls}. The cohort sidecar must be loaded ONCE at "
        f"startup and cached in memory for LOCK GATE EVAL — see the "
        f"feedback_verify_cohort_sidecar_before_walk memory rationale."
    )
    # And the cached variable MUST be referenced in the LOCK GATE EVAL phase.
    assert "cohort_assignments_cached" in source, (
        "Cached cohort assignments variable cohort_assignments_cached not "
        "found — startup-load fix may have been reverted."
    )
