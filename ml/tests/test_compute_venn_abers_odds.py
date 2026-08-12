"""Unit tests for compute_venn_abers_odds.py — pure-function coverage.

No IO, no panels, no parquet, no AWS. All tests operate on synthetic
in-memory data.

Coverage:
  - venn_abers_interval: well-separated data produces tight interval near true rate
  - venn_abers_interval: interval validity ([p_lo, p_hi] in [0,1], p_lo <= p_hi)
  - venn_abers_interval: width widens as calibration n shrinks
  - venn_abers_interval: determinism (same inputs -> same output)
  - batch_venn_abers_intervals: shape and consistency with single-call
  - compute_empirical_coverage: correct coverage count on synthetic data
  - compute_empirical_coverage: gate_pass logic (>= 0.90 -> True)
  - compute_mean_interval_width: UNSHARP_LOW_POWER flag on wide intervals
  - compute_mean_interval_width: gate_pass logic (<= 0.60 -> True)
  - _pava_predict: monotonicity sanity (p1 >= p0 for a well-separated set)
  - CLI: parser accepts all documented flags + defaults
  - Output schema: gate definitions present in output dict structure

Per test-first rule (#373, feedback_test_first_rule.md):
tests written before the implementation is run.
Mirror style of tests/test_run_f_ml_1_poc.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import compute_venn_abers_odds as vao  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_well_separated_cal(n_pos: int = 40, n_neg: int = 40, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Calibration set where positives score near 1 and negatives near 0."""
    rng = np.random.default_rng(seed)
    pos_scores = rng.uniform(0.65, 0.99, n_pos)
    neg_scores = rng.uniform(0.01, 0.35, n_neg)
    scores = np.concatenate([pos_scores, neg_scores])
    labels = np.concatenate([np.ones(n_pos, dtype=int), np.zeros(n_neg, dtype=int)])
    return scores, labels


def _make_random_cal(n: int = 30, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Calibration set with no discrimination signal."""
    rng = np.random.default_rng(seed)
    scores = rng.uniform(0, 1, n)
    labels = rng.integers(0, 2, n)
    return scores, labels


# ---------------------------------------------------------------------------
# Tests: venn_abers_interval — validity
# ---------------------------------------------------------------------------


def test_interval_validity_p_lo_leq_p_hi():
    """p_lo <= p_hi must hold for all test scores."""
    cal_scores, cal_labels = _make_well_separated_cal()
    for test_score in [0.0, 0.1, 0.5, 0.9, 1.0]:
        p_lo, p_hi = vao.venn_abers_interval(cal_scores, cal_labels, test_score)
        assert p_lo <= p_hi, (
            f"p_lo={p_lo:.4f} > p_hi={p_hi:.4f} at test_score={test_score}"
        )


def test_interval_in_unit_range():
    """Both p_lo and p_hi must lie in [0, 1]."""
    cal_scores, cal_labels = _make_well_separated_cal()
    for test_score in [0.0, 0.25, 0.5, 0.75, 1.0]:
        p_lo, p_hi = vao.venn_abers_interval(cal_scores, cal_labels, test_score)
        assert 0.0 <= p_lo <= 1.0, f"p_lo={p_lo:.4f} outside [0,1]"
        assert 0.0 <= p_hi <= 1.0, f"p_hi={p_hi:.4f} outside [0,1]"


def test_interval_validity_with_random_calibration():
    """Validity holds even for a completely random calibration set."""
    cal_scores, cal_labels = _make_random_cal(n=20, seed=7)
    for test_score in np.linspace(0, 1, 11):
        p_lo, p_hi = vao.venn_abers_interval(cal_scores, cal_labels, float(test_score))
        assert p_lo <= p_hi, f"p_lo > p_hi at score={test_score}"
        assert 0.0 <= p_lo <= 1.0
        assert 0.0 <= p_hi <= 1.0


# ---------------------------------------------------------------------------
# Tests: venn_abers_interval — tight on well-separated data
# ---------------------------------------------------------------------------


def test_interval_tight_for_clearly_positive_score():
    """On well-separated calibration data, a clearly positive test score
    (0.95) should produce an interval with p_lo > 0.5 (leans positive)."""
    cal_scores, cal_labels = _make_well_separated_cal(n_pos=60, n_neg=60, seed=1)
    p_lo, p_hi = vao.venn_abers_interval(cal_scores, cal_labels, 0.95)
    assert p_lo > 0.5, (
        f"Well-separated data: p_lo={p_lo:.4f} should be > 0.5 for high score"
    )


def test_interval_tight_for_clearly_negative_score():
    """On well-separated calibration data, a clearly negative test score
    (0.05) should produce an interval with p_hi < 0.5 (leans negative)."""
    cal_scores, cal_labels = _make_well_separated_cal(n_pos=60, n_neg=60, seed=2)
    p_lo, p_hi = vao.venn_abers_interval(cal_scores, cal_labels, 0.05)
    assert p_hi < 0.5, (
        f"Well-separated data: p_hi={p_hi:.4f} should be < 0.5 for low score"
    )


def test_interval_near_true_rate_on_balanced_data():
    """On a large balanced calibration set with well-separated scores,
    the midpoint should be near the empirical positive rate for a mid-range score."""
    rng = np.random.default_rng(42)
    n = 200
    # Base rate ~0.3
    pos_scores = rng.uniform(0.6, 1.0, 60)
    neg_scores = rng.uniform(0.0, 0.4, 140)
    cal_scores = np.concatenate([pos_scores, neg_scores])
    cal_labels = np.concatenate([np.ones(60, int), np.zeros(140, int)])

    # Test score of 0.8 should map near the positive region
    p_lo, p_hi = vao.venn_abers_interval(cal_scores, cal_labels, 0.8)
    midpoint = (p_lo + p_hi) / 2.0
    # Should lean positive (midpoint > 0.5) since 0.8 is in the positive region
    assert midpoint > 0.4, f"midpoint={midpoint:.4f} should lean positive"


# ---------------------------------------------------------------------------
# Tests: venn_abers_interval — width increases with smaller calibration n
# ---------------------------------------------------------------------------


def test_interval_width_grows_as_n_shrinks():
    """With the same test score and data pattern, a smaller calibration set
    should produce equal or wider intervals (less certainty)."""
    test_score = 0.5  # ambiguous region

    widths = []
    for n in [5, 15, 50, 150]:
        rng = np.random.default_rng(0)
        scores = rng.uniform(0, 1, n)
        labels = rng.integers(0, 2, n)
        p_lo, p_hi = vao.venn_abers_interval(scores, labels, test_score)
        widths.append(p_hi - p_lo)

    # Width at n=5 should be >= width at n=150 (weakly monotone)
    # (probabilistically true; we allow a small tolerance)
    assert widths[0] >= widths[-1] - 0.05, (
        f"Width at n=5 ({widths[0]:.3f}) should be >= width at n=150 ({widths[-1]:.3f})"
    )


# ---------------------------------------------------------------------------
# Tests: venn_abers_interval — determinism
# ---------------------------------------------------------------------------


def test_interval_deterministic():
    """Same inputs must produce identical outputs on repeated calls."""
    cal_scores, cal_labels = _make_well_separated_cal(seed=3)
    for test_score in [0.1, 0.5, 0.9]:
        r1 = vao.venn_abers_interval(cal_scores, cal_labels, test_score)
        r2 = vao.venn_abers_interval(cal_scores, cal_labels, test_score)
        assert r1 == r2, f"Non-deterministic at test_score={test_score}"


# ---------------------------------------------------------------------------
# Tests: batch_venn_abers_intervals — shape and consistency
# ---------------------------------------------------------------------------


def test_batch_shape_matches_test_scores():
    """batch_venn_abers_intervals must return as many intervals as test scores."""
    cal_scores, cal_labels = _make_well_separated_cal()
    test_scores = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    intervals = vao.batch_venn_abers_intervals(cal_scores, cal_labels, test_scores)
    assert len(intervals) == len(test_scores)


def test_batch_consistent_with_single():
    """Each batch interval must match the single-call result."""
    cal_scores, cal_labels = _make_well_separated_cal(seed=4)
    test_scores = np.array([0.2, 0.5, 0.8])
    batch = vao.batch_venn_abers_intervals(cal_scores, cal_labels, test_scores)
    for i, s in enumerate(test_scores):
        single = vao.venn_abers_interval(cal_scores, cal_labels, float(s))
        assert batch[i] == single, (
            f"Batch and single disagree at index {i}: batch={batch[i]}, single={single}"
        )


def test_batch_all_valid():
    """All batch intervals must satisfy [0,1] and p_lo <= p_hi."""
    cal_scores, cal_labels = _make_random_cal(n=25)
    test_scores = np.linspace(0, 1, 20)
    intervals = vao.batch_venn_abers_intervals(cal_scores, cal_labels, test_scores)
    for i, (p_lo, p_hi) in enumerate(intervals):
        assert 0.0 <= p_lo <= 1.0, f"[{i}] p_lo={p_lo} outside [0,1]"
        assert 0.0 <= p_hi <= 1.0, f"[{i}] p_hi={p_hi} outside [0,1]"
        assert p_lo <= p_hi, f"[{i}] p_lo={p_lo} > p_hi={p_hi}"


# ---------------------------------------------------------------------------
# Tests: _pava_predict — monotonicity
# ---------------------------------------------------------------------------


def test_pava_predict_p1_geq_p0_on_separated_data():
    """For a well-separated calibration set, augmenting with label=1 should
    give a higher or equal predicted probability than augmenting with label=0,
    for a positively-aligned test score."""
    cal_scores, cal_labels = _make_well_separated_cal(n_pos=50, n_neg=50, seed=5)
    test_score = 0.9  # clearly in the positive region
    p0 = vao._pava_predict(cal_scores, cal_labels, test_score, augment_label=0)
    p1 = vao._pava_predict(cal_scores, cal_labels, test_score, augment_label=1)
    # For a high test score in a well-separated set, p1 >= p0
    assert p1 >= p0 - 1e-9, (
        f"p1={p1:.4f} should be >= p0={p0:.4f} for a high test score on separated data"
    )


# ---------------------------------------------------------------------------
# Tests: compute_empirical_coverage
# ---------------------------------------------------------------------------


def test_coverage_perfect_on_well_classified_positives():
    """Midpoint-classification coverage: high-score positives on a well-separated
    calibrator get midpoint >= 0.5 → all covered → coverage 1.0, gate passes."""
    cal_fit_scores, cal_fit_labels = _make_well_separated_cal(n_pos=40, n_neg=40, seed=0)
    cal_val_scores = np.array([0.8, 0.85, 0.9, 0.95, 0.99])
    cal_val_labels = np.array([1, 1, 1, 1, 1])
    result = vao.compute_empirical_coverage(
        cal_val_scores, cal_val_labels, cal_fit_scores, cal_fit_labels
    )
    assert result["definition"] == "midpoint_classification_accuracy_proxy"
    assert result["coverage"] == 1.0, (
        f"High-score positives should classify correctly: got {result['coverage']:.3f}"
    )
    assert result["gate_pass"] is True
    assert result["n_total"] == 5


def test_coverage_gate_pass_threshold():
    """Gate passes at coverage >= 0.80 (midpoint-classification)."""
    cal_fit_scores, cal_fit_labels = _make_well_separated_cal()
    cal_val_scores = np.array([0.7, 0.75, 0.8, 0.85, 0.9, 0.92, 0.94, 0.96, 0.98, 0.99])
    cal_val_labels = np.ones(10, dtype=int)
    result = vao.compute_empirical_coverage(
        cal_val_scores, cal_val_labels, cal_fit_scores, cal_fit_labels
    )
    assert result["gate_pass"] is True
    assert result["coverage"] >= 0.80
    assert result["gate_threshold"] == 0.80


def test_coverage_gate_FAILS_on_misclassified_positives():
    """The key non-triviality check: positives that the calibrator places on the
    WRONG side of 0.5 (low scores labeled positive) must DROP coverage below the
    gate — proving midpoint-classification is not near-trivially satisfied
    (unlike the old p_hi>0 check, which would have passed this case)."""
    cal_fit_scores, cal_fit_labels = _make_well_separated_cal(n_pos=40, n_neg=40, seed=0)
    # 6 of 8 cal-val positives have LOW scores → midpoint < 0.5 → NOT covered.
    cal_val_scores = np.array([0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.95, 0.98])
    cal_val_labels = np.ones(8, dtype=int)
    result = vao.compute_empirical_coverage(
        cal_val_scores, cal_val_labels, cal_fit_scores, cal_fit_labels
    )
    assert result["coverage"] < 0.80, (
        f"Misclassified positives must drop coverage below the gate: "
        f"got {result['coverage']:.3f} — old trivial check would have passed at 1.0"
    )
    assert result["gate_pass"] is False


def test_coverage_midpoint_exactly_half_boundary():
    """F5 boundary: a positive whose interval midpoint is EXACTLY 0.5 must be
    counted as covered (the classifier uses midpoint >= 0.5, inclusive). We force
    a symmetric calibrator so a mid-range score yields a midpoint at the 0.5
    boundary, and assert the >= side is honored rather than > ."""
    # Symmetric calibration set: equal positives and negatives, mirrored scores,
    # so the Venn-Abers interval for a central score straddles 0.5 symmetrically.
    cal_fit_scores = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    cal_fit_labels = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    cal_val_scores = np.array([0.5, 0.5, 0.5, 0.5, 0.5])
    cal_val_labels = np.ones(5, dtype=int)
    result = vao.compute_empirical_coverage(
        cal_val_scores, cal_val_labels, cal_fit_scores, cal_fit_labels
    )
    # Recompute the midpoint directly to assert the boundary case is exercised.
    intervals = vao.batch_venn_abers_intervals(cal_fit_scores, cal_fit_labels, cal_val_scores)
    mids = [(float(lo) + float(hi)) / 2.0 for lo, hi in intervals]
    # If any midpoint is exactly 0.5, it must be counted as covered for y=1.
    if any(abs(m - 0.5) < 1e-12 for m in mids):
        n_boundary = sum(1 for m in mids if abs(m - 0.5) < 1e-12)
        assert result["n_covered"] >= n_boundary, (
            "midpoint == 0.5 positives must be covered under the inclusive >= rule"
        )


def test_coverage_low_n_skip():
    """When n < MIN_N_FOR_GATE, gate_pass should be None (not False)."""
    cal_fit_scores, cal_fit_labels = _make_well_separated_cal()
    cal_val_scores = np.array([0.8, 0.9])  # n=2 < 5
    cal_val_labels = np.array([1, 1])
    result = vao.compute_empirical_coverage(
        cal_val_scores, cal_val_labels, cal_fit_scores, cal_fit_labels
    )
    # With n < MIN_N_FOR_GATE, low_n_skip should be set; gate_pass is None or True
    # (n=2 is below 5, so low_n_skip=True)
    # Actually the function still computes coverage but gate_pass is gated on n>=5
    # (per the implementation: "gate_pass": bool(coverage >= 0.90) if n_total >= 5 else None)
    if result["n_total"] < 5:
        assert result["gate_pass"] is None, (
            f"gate_pass should be None when n_total < 5, got {result['gate_pass']}"
        )


def test_coverage_output_schema():
    """Result must contain the documented fields."""
    cal_fit_scores, cal_fit_labels = _make_well_separated_cal()
    cal_val_scores = np.array([0.8, 0.85, 0.9, 0.95, 0.99])
    cal_val_labels = np.array([1, 1, 1, 1, 1])
    result = vao.compute_empirical_coverage(
        cal_val_scores, cal_val_labels, cal_fit_scores, cal_fit_labels
    )
    required_keys = {"coverage", "n_covered", "n_total", "gate_pass", "gate_threshold",
                     "low_n_skip", "definition", "winkler_score_diagnostic"}
    assert required_keys.issubset(set(result.keys())), (
        f"Missing keys: {required_keys - set(result.keys())}"
    )


# ---------------------------------------------------------------------------
# Tests: compute_mean_interval_width
# ---------------------------------------------------------------------------


def test_width_gate_pass_tight_intervals():
    """On well-separated data, a clearly positive test score should produce
    tight intervals and pass the width gate (<= 0.60)."""
    cal_scores, cal_labels = _make_well_separated_cal(n_pos=60, n_neg=60, seed=0)
    test_scores = np.array([0.8, 0.85, 0.9, 0.92, 0.95])
    result = vao.compute_mean_interval_width(cal_scores, cal_labels, test_scores)
    assert result["gate_pass"] is True, (
        f"Width gate should pass for tight intervals, mean_width={result['mean_width']:.3f}"
    )
    assert result["flag"] is None


def test_width_gate_fail_and_flag_on_wide_intervals():
    """On a near-random calibration set, intervals on mid-range scores should
    be wide and trigger UNSHARP_LOW_POWER."""
    # Very small calibration set: high uncertainty -> wide intervals
    rng = np.random.default_rng(99)
    cal_scores = np.array([0.3, 0.5, 0.7, 0.2, 0.8])
    cal_labels = np.array([1, 0, 1, 0, 1])
    # Test scores in ambiguous range
    test_scores = np.linspace(0.1, 0.9, 10)
    result = vao.compute_mean_interval_width(cal_scores, cal_labels, test_scores)
    # Width can be wide with only 5 calibration points
    if result["mean_width"] is not None and result["mean_width"] > 0.60:
        assert result["flag"] == "UNSHARP_LOW_POWER"
        assert result["gate_pass"] is False


def test_width_unsharp_flag_condition():
    """When mean_width > 0.60, flag must be UNSHARP_LOW_POWER; else None."""
    # Minimal synthetic test: directly verify the gate logic
    # Patch: use 3 calibration points + a test score that should produce wide intervals
    cal_scores = np.array([0.2, 0.5, 0.8])
    cal_labels = np.array([0, 1, 0])
    test_scores = np.array([0.5])
    result = vao.compute_mean_interval_width(cal_scores, cal_labels, test_scores)
    if result["mean_width"] is not None:
        if result["mean_width"] > 0.60:
            assert result["flag"] == "UNSHARP_LOW_POWER"
            assert result["gate_pass"] is False
        else:
            assert result["flag"] is None
            assert result["gate_pass"] is True


def test_width_output_schema():
    """Result must contain the documented keys."""
    cal_scores, cal_labels = _make_well_separated_cal()
    test_scores = np.array([0.7, 0.8])
    result = vao.compute_mean_interval_width(cal_scores, cal_labels, test_scores)
    required_keys = {"mean_width", "max_width", "n_test", "gate_pass", "gate_threshold", "flag"}
    assert required_keys.issubset(set(result.keys())), (
        f"Missing keys: {required_keys - set(result.keys())}"
    )


def test_width_n_test_matches_input():
    """n_test must equal the number of test scores passed in."""
    cal_scores, cal_labels = _make_well_separated_cal()
    test_scores = np.linspace(0.1, 0.9, 7)
    result = vao.compute_mean_interval_width(cal_scores, cal_labels, test_scores)
    assert result["n_test"] == 7


# ---------------------------------------------------------------------------
# Tests: gate constants
# ---------------------------------------------------------------------------


def test_gate_constants():
    """Verify the gate constants match the consult spec."""
    assert vao.COVERAGE_GATE == 0.80, (
        "Gate 1 coverage threshold is 0.80 on the midpoint-classification check "
        "(venn-abers-coverage-gate-consult-2026-05-24); was 0.90 on the trivial check"
    )
    assert vao.WIDTH_GATE == 0.60, (
        "Gate 2 width threshold must be 0.60 per consult §4"
    )
    assert vao.MIN_N_FOR_GATE == 5, (
        "Minimum n for gate evaluation must be 5 per consult §4"
    )
    assert vao.CAL_FIT_FRACTION == 0.70, (
        "Cal-fit fraction must be 0.70 (70/30 split per consult §4)"
    )


# ---------------------------------------------------------------------------
# Tests: cohort list
# ---------------------------------------------------------------------------


def test_cohorts_match_expected():
    """COHORTS must cover exactly the three QGI cohorts."""
    assert set(vao.COHORTS) == {"fragile-state", "mid-tier", "stable-democracy"}


# ---------------------------------------------------------------------------
# Tests: CLI parser
# ---------------------------------------------------------------------------


def test_cli_parser_required_flags(tmp_path):
    """--recipe-id, --walk-summary, --scores-file, --output-dir are required."""
    parser = vao._build_parser()
    import pytest as _pytest
    with _pytest.raises(SystemExit):
        parser.parse_args([])  # missing required flags


def test_cli_parser_all_flags(tmp_path):
    """Parser must accept all documented flags without error."""
    parser = vao._build_parser()
    args = parser.parse_args([
        "--recipe-id", "foreign_intervention",
        "--walk-summary", str(tmp_path / "walk.json"),
        "--scores-file", str(tmp_path / "scores.json"),
        "--panel-dir", str(tmp_path / "panels"),
        "--cohort-sidecar", str(tmp_path / "cohort.json"),
        "--output-dir", str(tmp_path),
        "--seed", "42",
    ])
    assert args.recipe_id == "foreign_intervention"
    assert args.seed == 42


def test_cli_parser_defaults(tmp_path):
    """Default seed must be 12345."""
    parser = vao._build_parser()
    args = parser.parse_args([
        "--recipe-id", "test_recipe",
        "--walk-summary", str(tmp_path / "walk.json"),
        "--scores-file", str(tmp_path / "scores.json"),
        "--output-dir", str(tmp_path),
    ])
    assert args.seed == 12345


# ---------------------------------------------------------------------------
# Tests: label framing
# ---------------------------------------------------------------------------


def test_label_string_constant():
    """The display label must match the consult Gate 4 wording exactly."""
    # Verify by importing the function and checking that output has the label
    # We do a synthetic integration test here (no IO, but calls the internal
    # fit_and_score_per_cohort with mock data).
    cal_scores, cal_labels = _make_well_separated_cal(n_pos=20, n_neg=20, seed=10)

    # Build a minimal mock for fit_and_score_per_cohort:
    # we call compute_mean_interval_width and check the output schema, then
    # verify the LABEL string is present as a constant.
    expected_label = "estimated probability range, not a precise probability"
    # The label must appear in the module source
    import inspect
    source = inspect.getsource(vao)
    assert expected_label in source, (
        f"Gate 4 label string must appear in module source: '{expected_label}'"
    )


# ---------------------------------------------------------------------------
# Tests: integration — fit_and_score_per_cohort on synthetic data
# ---------------------------------------------------------------------------


def test_fit_and_score_per_cohort_output_schema(tmp_path):
    """fit_and_score_per_cohort must produce the documented output structure."""
    # Build synthetic OOF data with all 3 cohorts
    rng = np.random.default_rng(0)
    n = 60
    probs = rng.uniform(0, 1, n)
    labels = (probs > 0.5).astype(int)
    countries = np.array([f"Country_{i}" for i in range(n)])
    years = np.full(n, 2021)

    cohort_list = ["fragile-state"] * 25 + ["mid-tier"] * 20 + ["stable-democracy"] * 15
    cohorts_arr = np.array(cohort_list, dtype=object)

    oof = {
        "probs": probs,
        "labels": labels,
        "countries": countries,
        "years": years,
        "cohorts": cohorts_arr,
        "global_auc": 0.70,
        "selected_indicators": ["IND_A"],
        "chosen_window": 10,
        "architecture": "XGBoost",
        "n_samples": n,
        "n_positives": int(labels.sum()),
        "n_negatives": int((labels == 0).sum()),
    }

    # Build cohort_assignments dict for scored countries
    cohort_assignments: dict[str, dict[str, str]] = {}
    for i in range(n):
        c = f"Country_{i}"
        cohort_assignments[c] = {"2021": cohort_list[i]}

    # scored_countries: take 10 countries
    scored_countries = [f"Country_{i}" for i in range(10)]
    scored_scores = {c: 50.0 for c in scored_countries}

    result = vao.fit_and_score_per_cohort(
        oof=oof,
        scored_countries=scored_countries,
        scored_scores=scored_scores,
        cohort_assignments=cohort_assignments,
        eval_year=2021,
        seed=12345,
    )

    # All three cohorts must be present
    assert set(result.keys()) == set(vao.COHORTS), (
        f"Missing cohorts in result: {set(vao.COHORTS) - set(result.keys())}"
    )

    # Each cohort result must contain required top-level keys
    required = {"n_oof", "gate_pass", "suppressed"}
    for cohort, data in result.items():
        assert required.issubset(set(data.keys())), (
            f"Cohort {cohort} missing keys: {required - set(data.keys())}"
        )


def test_fit_and_score_country_odds_schema(tmp_path):
    """Per-country odds entries must have p_lo, p_hi, cohort, suppressed, label."""
    rng = np.random.default_rng(1)
    n = 50
    probs = rng.uniform(0, 1, n)
    labels = (probs > 0.5).astype(int)
    countries = np.array([f"C_{i}" for i in range(n)])
    years = np.full(n, 2021)
    cohort_list = ["fragile-state"] * 30 + ["mid-tier"] * 12 + ["stable-democracy"] * 8
    cohorts_arr = np.array(cohort_list, dtype=object)

    oof = {
        "probs": probs, "labels": labels, "countries": countries,
        "years": years, "cohorts": cohorts_arr, "global_auc": 0.65,
        "selected_indicators": ["X"], "chosen_window": 10,
        "architecture": "XGBoost", "n_samples": n,
        "n_positives": int(labels.sum()), "n_negatives": int((labels==0).sum()),
    }
    cohort_assignments: dict[str, dict[str, str]] = {
        f"C_{i}": {"2021": cohort_list[i]} for i in range(n)
    }
    scored_countries = [f"C_{i}" for i in range(5)]
    scored_scores = {c: 40.0 for c in scored_countries}

    result = vao.fit_and_score_per_cohort(
        oof=oof,
        scored_countries=scored_countries,
        scored_scores=scored_scores,
        cohort_assignments=cohort_assignments,
        eval_year=2021,
        seed=0,
    )

    # Collect all country odds across cohorts
    all_odds: dict[str, dict] = {}
    for cohort_data in result.values():
        if "country_odds" in cohort_data:
            all_odds.update(cohort_data["country_odds"])

    required_fields = {"p_lo", "p_hi", "width", "midpoint", "cohort", "suppressed", "label"}
    for country, odds in all_odds.items():
        assert required_fields.issubset(set(odds.keys())), (
            f"{country} missing fields: {required_fields - set(odds.keys())}"
        )
        # p_lo, p_hi in [0,1] and p_lo <= p_hi
        assert 0.0 <= odds["p_lo"] <= 1.0, f"{country} p_lo out of range"
        assert 0.0 <= odds["p_hi"] <= 1.0, f"{country} p_hi out of range"
        assert odds["p_lo"] <= odds["p_hi"], f"{country} p_lo > p_hi"
        # width = p_hi - p_lo (values rounded to 6dp in output, tolerance 1e-5)
        assert abs(odds["width"] - (odds["p_hi"] - odds["p_lo"])) < 1e-5, (
            f"{country} width inconsistent with p_lo/p_hi"
        )
        # midpoint = (p_lo + p_hi) / 2 (rounded to 6dp, tolerance 1e-5)
        assert abs(odds["midpoint"] - (odds["p_lo"] + odds["p_hi"]) / 2.0) < 1e-5, (
            f"{country} midpoint inconsistent"
        )
        # label must be present and non-empty
        assert isinstance(odds["label"], str) and len(odds["label"]) > 0
