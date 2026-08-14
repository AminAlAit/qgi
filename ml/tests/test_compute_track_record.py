"""Unit tests for compute_track_record.py — pure-function coverage.

No IO, no panels, no parquet, no AWS. All tests operate on synthetic
in-memory data.

Coverage:
  - wilson_ci: correctness on known textbook cases (0/5, 5/5, 3/10)
  - wilson_ci: output in [0,1], lo <= hi for all inputs
  - wilson_ci: n=0 edge case (return 0, 0 gracefully)
  - bin_oof_predictions: correct bin assignment on boundary cases
  - bin_oof_predictions: suppression fires at n < 5 (INSUFFICIENT_DATA)
  - bin_oof_predictions: n < 5 bins are suppressed=True; n >= 5 bins are suppressed=False
  - bin_oof_predictions: ppv = n_pos/n (never a bare point — always with CI)
  - bin_oof_predictions: ppv field always present even when suppressed
  - bin_oof_predictions: output schema keys present
  - bin_oof_predictions: baseline_rate = n_pos/n_total
  - bin_oof_predictions: monotonicity soft sanity (bins from well-separated AUC≈1 data
    should show non-decreasing ppv across non-suppressed bins)
  - BINS constant: pre-registered bins fixed before results
  - compute_track_record_from_oof: schema keys present in returned dict
  - CLI: parser accepts all documented flags + defaults

Per test-first rule (#373, feedback_test_first_rule.md):
tests written before the implementation is run.
Mirror style of tests/test_compute_venn_abers_odds.py.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import compute_track_record as ctr  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_perfect_oof(n_pos: int = 50, n_neg: int = 150, seed: int = 0) -> dict:
    """OOF predictions where positives score in [0.85, 1.0] and negatives in [0.0, 0.35].
    Perfect separation → AUC ≈ 1.0; high-score bins should have ppv near 1.
    """
    rng = np.random.default_rng(seed)
    pos_scores = rng.uniform(0.85, 0.99, n_pos)
    neg_scores = rng.uniform(0.0, 0.35, n_neg)
    probs = np.concatenate([pos_scores, neg_scores])
    labels = np.concatenate([np.ones(n_pos, dtype=int), np.zeros(n_neg, dtype=int)])
    return {"probs": probs, "labels": labels}


def _make_random_oof(n: int = 200, seed: int = 0) -> dict:
    """OOF predictions with no discrimination (random scores)."""
    rng = np.random.default_rng(seed)
    probs = rng.uniform(0, 1, n)
    labels = rng.integers(0, 2, n)
    return {"probs": probs, "labels": labels}


# ---------------------------------------------------------------------------
# Tests: wilson_ci — correctness against textbook values
# ---------------------------------------------------------------------------


def test_wilson_ci_zero_successes():
    """0/5: Wilson lo should be 0, hi should be > 0 (one-sided bound)."""
    lo, hi = ctr.wilson_ci(n_pos=0, n=5, z=1.96)
    assert lo == pytest.approx(0.0, abs=1e-9), f"lo should be 0 for 0 successes, got {lo:.6f}"
    assert hi > 0.0, f"hi should be > 0 for 0 successes, got {hi:.6f}"
    # Textbook: Wilson hi ≈ 0.522 for 0/5 at 95%
    assert hi < 0.60, f"hi too large for 0/5 at 95%: {hi:.4f}"


def test_wilson_ci_all_successes():
    """5/5: Wilson hi should be 1 (or very close), lo should be > 0."""
    lo, hi = ctr.wilson_ci(n_pos=5, n=5, z=1.96)
    assert hi == pytest.approx(1.0, abs=1e-9), f"hi should be 1 for all successes, got {hi:.6f}"
    assert lo > 0.0, f"lo should be > 0 for 5/5, got {lo:.6f}"


def test_wilson_ci_three_out_of_ten():
    """3/10: Wilson 95% CI cross-checked against the formula.

    For p_hat=0.3, n=10, z=1.96 the Wilson formula gives approximately:
        lo ≈ 0.1078, hi ≈ 0.6003
    (Note: the Clopper-Pearson exact interval is narrower/different;
    the Wilson interval at small n shifts the center toward 0.5 due to
    the z²/(2n) term in the numerator.)
    """
    lo, hi = ctr.wilson_ci(n_pos=3, n=10, z=1.96)
    # Verified against formula output: lo ≈ 0.1078, hi ≈ 0.6003
    assert lo == pytest.approx(0.1078, abs=0.005), f"lo={lo:.4f}, expected ~0.108"
    assert hi == pytest.approx(0.6003, abs=0.005), f"hi={hi:.4f}, expected ~0.600"
    # Also verify lo < p_hat < hi (interval must contain the observed proportion)
    assert lo < 0.3 < hi, f"Wilson CI [{lo:.4f}, {hi:.4f}] must contain p_hat=0.3"


def test_wilson_ci_midpoint_matches_proportion():
    """Wilson CI midpoint (center) should be close to the sample proportion."""
    lo, hi = ctr.wilson_ci(n_pos=7, n=10, z=1.96)
    # p = 0.7; Wilson midpoint is not exactly p but close for moderate n
    mid = (lo + hi) / 2.0
    assert abs(mid - 0.7) < 0.15, f"midpoint={mid:.4f} unexpectedly far from p=0.7"


def test_wilson_ci_output_in_unit_range():
    """lo and hi must always lie in [0, 1] across a range of inputs."""
    for n_pos, n in [(0, 1), (1, 1), (0, 5), (5, 5), (3, 10), (0, 100), (100, 100), (50, 100)]:
        lo, hi = ctr.wilson_ci(n_pos=n_pos, n=n, z=1.96)
        assert 0.0 <= lo <= 1.0, f"lo={lo:.6f} outside [0,1] for {n_pos}/{n}"
        assert 0.0 <= hi <= 1.0, f"hi={hi:.6f} outside [0,1] for {n_pos}/{n}"
        assert lo <= hi, f"lo={lo:.6f} > hi={hi:.6f} for {n_pos}/{n}"


def test_wilson_ci_n_zero_edge():
    """n=0 should return (0.0, 0.0) without raising."""
    lo, hi = ctr.wilson_ci(n_pos=0, n=0, z=1.96)
    assert lo == 0.0
    assert hi == 0.0


# ---------------------------------------------------------------------------
# Tests: BINS constant — pre-registered before results
# ---------------------------------------------------------------------------


def test_bins_pre_registered():
    """BINS must be exactly the pre-registered list from the spec."""
    expected = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.0)]
    assert len(ctr.BINS) == len(expected), (
        f"Expected {len(expected)} bins, got {len(ctr.BINS)}"
    )
    for i, (exp, got) in enumerate(zip(expected, ctr.BINS)):
        assert got[0] == pytest.approx(exp[0], abs=1e-12), (
            f"Bin {i} lo mismatch: expected {exp[0]}, got {got[0]}"
        )
        assert got[1] == pytest.approx(exp[1], abs=1e-12), (
            f"Bin {i} hi mismatch: expected {exp[1]}, got {got[1]}"
        )


def test_bins_cover_full_range():
    """All 5 bins together should cover [0, 1.0] without gaps."""
    lows = [b[0] for b in ctr.BINS]
    highs = [b[1] for b in ctr.BINS]
    assert lows[0] == pytest.approx(0.0, abs=1e-12)
    assert highs[-1] == pytest.approx(1.0, abs=1e-12)
    # Adjacent bins should be contiguous
    for i in range(len(ctr.BINS) - 1):
        assert highs[i] == pytest.approx(lows[i + 1], abs=1e-12), (
            f"Gap between bin {i} hi={highs[i]} and bin {i+1} lo={lows[i+1]}"
        )


# ---------------------------------------------------------------------------
# Tests: bin_oof_predictions — bin assignment correctness
# ---------------------------------------------------------------------------


def test_bin_assignment_boundary_cases():
    """Score exactly at a bin boundary should fall into the upper bin (left-closed)."""
    # Score 0.5 is in [0.5, 0.7), NOT [0, 0.5)
    # Score 0.0 is in [0.0, 0.5)
    # Score 0.7 is in [0.7, 0.85)
    # Score 0.85 is in [0.85, 0.95)
    # Score 0.95 is in [0.95, 1.0]
    # Score 1.0 is in [0.95, 1.0]
    probs = np.array([0.0, 0.5, 0.7, 0.85, 0.95, 1.0])
    labels = np.array([0, 1, 1, 1, 1, 1])
    result = ctr.bin_oof_predictions(probs, labels)
    bins_out = result["bins"]
    # Bin 0: [0, 0.5) — contains only 0.0 → n=1
    # Bin 1: [0.5, 0.7) — contains 0.5 → n=1
    # Bin 2: [0.7, 0.85) — contains 0.7 → n=1
    # Bin 3: [0.85, 0.95) — contains 0.85 → n=1
    # Bin 4: [0.95, 1.0] — contains 0.95 and 1.0 → n=2
    assert bins_out[0]["n"] == 1, f"Bin 0 n expected 1, got {bins_out[0]['n']}"
    assert bins_out[1]["n"] == 1, f"Bin 1 n expected 1, got {bins_out[1]['n']}"
    assert bins_out[4]["n"] == 2, f"Bin 4 n expected 2, got {bins_out[4]['n']}"


def test_suppression_fires_at_n_lt_5():
    """Any bin with n < 5 must have suppressed=True and flag='INSUFFICIENT_DATA'."""
    # Use just 2 scores in bin [0.85, 0.95) and 6 in bin [0, 0.5)
    probs = np.array([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.87, 0.90])
    labels = np.array([0, 0, 0, 0, 0, 0, 1, 1])
    result = ctr.bin_oof_predictions(probs, labels)
    bins_out = result["bins"]
    # Find bin [0.85, 0.95): n=2 → must be suppressed
    bin_idx = 3  # [0.85, 0.95)
    assert bins_out[bin_idx]["n"] == 2, (
        f"Expected n=2 in bin [0.85,0.95), got {bins_out[bin_idx]['n']}"
    )
    assert bins_out[bin_idx]["suppressed"] is True, (
        "n=2 bin must be suppressed"
    )
    assert bins_out[bin_idx]["flag"] == "INSUFFICIENT_DATA", (
        f"Expected flag=INSUFFICIENT_DATA, got {bins_out[bin_idx]['flag']!r}"
    )


def test_suppression_not_fires_at_n_geq_5():
    """A bin with exactly n=5 must NOT be suppressed."""
    probs = np.array([0.86, 0.87, 0.88, 0.89, 0.90])
    labels = np.array([1, 1, 0, 1, 1])
    result = ctr.bin_oof_predictions(probs, labels)
    bins_out = result["bins"]
    bin_idx = 3  # [0.85, 0.95)
    assert bins_out[bin_idx]["n"] == 5
    assert bins_out[bin_idx]["suppressed"] is False, (
        "n=5 bin must NOT be suppressed"
    )
    assert bins_out[bin_idx]["flag"] is None, (
        f"n=5 bin should have no flag, got {bins_out[bin_idx]['flag']!r}"
    )


def test_ppv_always_present_even_when_suppressed():
    """Even suppressed bins must have ppv, wilson_lo, wilson_hi — never a bare point."""
    probs = np.array([0.87, 0.88])  # n=2 in bin [0.85, 0.95)
    labels = np.array([1, 0])
    result = ctr.bin_oof_predictions(probs, labels)
    bins_out = result["bins"]
    bin_idx = 3
    assert bins_out[bin_idx]["suppressed"] is True
    assert "ppv" in bins_out[bin_idx], "ppv must be present even when suppressed"
    assert "wilson_lo" in bins_out[bin_idx], "wilson_lo must be present even when suppressed"
    assert "wilson_hi" in bins_out[bin_idx], "wilson_hi must be present even when suppressed"
    assert bins_out[bin_idx]["ppv"] is not None, "ppv must not be None even when suppressed"


def test_ppv_equals_n_pos_over_n():
    """ppv must equal n_positive / n exactly."""
    probs = np.array([0.86, 0.87, 0.88, 0.89, 0.90, 0.91])  # n=6 in [0.85,0.95)
    labels = np.array([1, 1, 0, 0, 1, 0])  # n_positive=3
    result = ctr.bin_oof_predictions(probs, labels)
    bins_out = result["bins"]
    bin_idx = 3
    assert bins_out[bin_idx]["n"] == 6
    assert bins_out[bin_idx]["n_positive"] == 3
    assert bins_out[bin_idx]["ppv"] == pytest.approx(0.5, abs=1e-9), (
        f"ppv={bins_out[bin_idx]['ppv']:.6f} != 3/6=0.5"
    )


def test_output_schema_keys_present():
    """bin_oof_predictions result must contain required top-level and per-bin keys."""
    oof = _make_perfect_oof(n_pos=30, n_neg=90)
    result = ctr.bin_oof_predictions(oof["probs"], oof["labels"])
    required_top = {"bins", "baseline_rate", "n_total", "n_positive"}
    assert required_top.issubset(set(result.keys())), (
        f"Missing top-level keys: {required_top - set(result.keys())}"
    )
    required_bin = {"score_range", "n", "n_positive", "ppv", "wilson_lo", "wilson_hi", "suppressed", "flag"}
    for b in result["bins"]:
        assert required_bin.issubset(set(b.keys())), (
            f"Bin {b.get('score_range')} missing keys: {required_bin - set(b.keys())}"
        )


def test_baseline_rate_equals_n_pos_over_n_total():
    """baseline_rate = n_pos / n_total across all OOF samples."""
    oof = _make_perfect_oof(n_pos=30, n_neg=90)
    result = ctr.bin_oof_predictions(oof["probs"], oof["labels"])
    expected_baseline = 30 / 120
    assert result["baseline_rate"] == pytest.approx(expected_baseline, abs=1e-9), (
        f"baseline_rate={result['baseline_rate']:.6f}, expected {expected_baseline:.6f}"
    )


def test_n_total_matches_input():
    """n_total in the output must equal the length of the input arrays."""
    oof = _make_perfect_oof(n_pos=20, n_neg=60)
    result = ctr.bin_oof_predictions(oof["probs"], oof["labels"])
    assert result["n_total"] == 80, f"n_total={result['n_total']}, expected 80"


def test_n_positive_matches_sum_of_labels():
    """n_positive in the output must equal sum(labels)."""
    oof = _make_perfect_oof(n_pos=25, n_neg=75)
    result = ctr.bin_oof_predictions(oof["probs"], oof["labels"])
    assert result["n_positive"] == 25, f"n_positive={result['n_positive']}, expected 25"


def test_bin_n_sums_to_n_total():
    """Sum of n across all bins must equal n_total."""
    oof = _make_perfect_oof(n_pos=30, n_neg=90)
    result = ctr.bin_oof_predictions(oof["probs"], oof["labels"])
    total_from_bins = sum(b["n"] for b in result["bins"])
    assert total_from_bins == result["n_total"], (
        f"Sum of bin n={total_from_bins} != n_total={result['n_total']}"
    )


def test_bin_n_positive_sums_to_n_positive():
    """Sum of n_positive across bins must equal overall n_positive."""
    oof = _make_perfect_oof(n_pos=30, n_neg=90)
    result = ctr.bin_oof_predictions(oof["probs"], oof["labels"])
    total_pos = sum(b["n_positive"] for b in result["bins"])
    assert total_pos == result["n_positive"], (
        f"Sum of bin n_positive={total_pos} != n_positive={result['n_positive']}"
    )


def test_score_range_matches_bins_constant():
    """Each bin's score_range must match the pre-registered BINS constant."""
    oof = _make_perfect_oof()
    result = ctr.bin_oof_predictions(oof["probs"], oof["labels"])
    for i, (b_out, b_spec) in enumerate(zip(result["bins"], ctr.BINS)):
        lo_str = str(b_spec[0])
        hi_str = str(b_spec[1])
        assert lo_str in b_out["score_range"], (
            f"Bin {i} score_range {b_out['score_range']!r} should contain {lo_str}"
        )


# ---------------------------------------------------------------------------
# Tests: monotonicity — soft sanity on high-AUC data
# ---------------------------------------------------------------------------


def test_ppv_monotonicity_on_perfect_separation():
    """On perfectly separated OOF predictions (AUC≈1), non-suppressed bins
    with both positives and negatives should show non-decreasing ppv.

    This is a SOFT assert (allows thin-bin noise per spec), applied only
    across adjacent non-suppressed bins. We allow a tolerance of 0.15 for
    monotonicity violations to accommodate thin-bin noise.
    """
    oof = _make_perfect_oof(n_pos=50, n_neg=150, seed=42)
    result = ctr.bin_oof_predictions(oof["probs"], oof["labels"])
    unsuppressed = [b for b in result["bins"] if not b["suppressed"]]
    # At least 2 unsuppressed bins are needed for the test to be meaningful
    if len(unsuppressed) < 2:
        pytest.skip("Fewer than 2 unsuppressed bins — monotonicity test not applicable")
    ppvs = [b["ppv"] for b in unsuppressed]
    for i in range(len(ppvs) - 1):
        assert ppvs[i] <= ppvs[i + 1] + 0.15, (
            f"Soft monotonicity violated (> 0.15 drop): bin {i} ppv={ppvs[i]:.3f} "
            f"> bin {i+1} ppv={ppvs[i+1]:.3f} (tolerance 0.15 for thin-bin noise)"
        )


# ---------------------------------------------------------------------------
# Tests: NEVER_PROBABILITY constant
# ---------------------------------------------------------------------------


def test_artifact_m8_r5_note_is_honest_not_probability():
    """HONESTY GUARD (review 2026-05-24): build a real artifact and assert its
    m8_r5_note explicitly frames PPV as out-of-fold FREQUENCY and explicitly
    denies it is a calibrated probability. The old form merely grepped the
    module source for the word 'frequency' (which appears in unrelated docstrings)
    — it guarded nothing."""
    oof = _make_perfect_oof()
    artifact = ctr.compute_track_record_from_oof(
        np.asarray(oof["probs"]), np.asarray(oof["labels"]),
        recipe_id="r", eval_year=2021, seed=0, auc=0.99,
    )
    note = artifact["m8_r5_note"].lower()
    assert "frequency" in note, "note must frame PPV as a frequency"
    assert "not a calibrated probability" in note, "note must explicitly deny it is a probability"
    # The 1:3-sampling disclosure must be present (don't let PPV read as a real-world rate).
    assert "sampling_disclosure" in artifact and "1:3" in artifact["sampling_disclosure"], (
        "artifact must disclose the 1:3 OOF sampling so PPV isn't read as real-world prevalence"
    )


# ---------------------------------------------------------------------------
# Tests: compute_track_record_from_oof — output schema
# ---------------------------------------------------------------------------


def test_compute_track_record_output_schema():
    """compute_track_record_from_oof must produce the documented JSON schema."""
    oof = _make_perfect_oof(n_pos=50, n_neg=150)
    result = ctr.compute_track_record_from_oof(
        probs=oof["probs"],
        labels=oof["labels"],
        recipe_id="test_recipe",
        eval_year=2021,
        seed=12345,
        auc=0.91,
    )
    required_top = {
        "recipe_id", "eval_year", "computed_at_utc", "seed_used",
        "oof", "bins", "baseline_rate", "binding_provenance", "m8_r5_note",
    }
    assert required_top.issubset(set(result.keys())), (
        f"Missing top-level keys: {required_top - set(result.keys())}"
    )
    oof_required = {"n_samples", "n_pos", "n_neg", "auc"}
    assert oof_required.issubset(set(result["oof"].keys())), (
        f"Missing oof keys: {oof_required - set(result['oof'].keys())}"
    )


def test_compute_track_record_recipe_id_and_year():
    """recipe_id and eval_year must be preserved in the output."""
    oof = _make_random_oof(n=100)
    result = ctr.compute_track_record_from_oof(
        probs=oof["probs"],
        labels=oof["labels"],
        recipe_id="foreign_intervention",
        eval_year=2021,
        seed=12345,
        auc=0.55,
    )
    assert result["recipe_id"] == "foreign_intervention"
    assert result["eval_year"] == 2021
    assert result["seed_used"] == 12345


def test_compute_track_record_oof_fields():
    """oof dict must correctly capture n_samples, n_pos, n_neg, auc."""
    probs = np.array([0.9, 0.8, 0.1, 0.2, 0.7])
    labels = np.array([1, 1, 0, 0, 1])
    result = ctr.compute_track_record_from_oof(
        probs=probs,
        labels=labels,
        recipe_id="r",
        eval_year=2020,
        seed=1,
        auc=0.88,
    )
    assert result["oof"]["n_samples"] == 5
    assert result["oof"]["n_pos"] == 3
    assert result["oof"]["n_neg"] == 2
    assert result["oof"]["auc"] == pytest.approx(0.88, abs=1e-9)


def test_m8_r5_note_not_empty():
    """m8_r5_note in the output must be a non-empty string."""
    oof = _make_random_oof(n=80)
    result = ctr.compute_track_record_from_oof(
        probs=oof["probs"], labels=oof["labels"],
        recipe_id="r", eval_year=2021, seed=1, auc=0.60,
    )
    assert isinstance(result["m8_r5_note"], str) and len(result["m8_r5_note"]) > 20


def test_binding_provenance_present():
    """binding_provenance must be a non-empty string referencing the spec."""
    oof = _make_random_oof(n=80)
    result = ctr.compute_track_record_from_oof(
        probs=oof["probs"], labels=oof["labels"],
        recipe_id="r", eval_year=2021, seed=1, auc=0.60,
    )
    assert isinstance(result["binding_provenance"], str)
    assert len(result["binding_provenance"]) > 10


# ---------------------------------------------------------------------------
# Tests: CLI parser
# ---------------------------------------------------------------------------


def test_cli_parser_required_flags(tmp_path):
    """--recipe-id, --walk-summary, --scores-file, --output-dir are required."""
    parser = ctr._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])  # missing required flags


def test_cli_parser_all_flags(tmp_path):
    """Parser must accept all documented flags without error."""
    parser = ctr._build_parser()
    args = parser.parse_args([
        "--recipe-id", "foreign_intervention",
        "--walk-summary", str(tmp_path / "walk.json"),
        "--scores-file", str(tmp_path / "scores.json"),
        "--panel-dir", str(tmp_path / "panels"),
        "--cohort-sidecar", str(tmp_path / "cohort.json"),
        "--output-dir", str(tmp_path),
        "--seed", "12345",
    ])
    assert args.recipe_id == "foreign_intervention"
    assert args.seed == 12345


def test_cli_parser_defaults(tmp_path):
    """Default seed must be 12345."""
    parser = ctr._build_parser()
    args = parser.parse_args([
        "--recipe-id", "foreign_intervention",
        "--walk-summary", str(tmp_path / "walk.json"),
        "--scores-file", str(tmp_path / "scores.json"),
        "--output-dir", str(tmp_path),
    ])
    assert args.seed == 12345
