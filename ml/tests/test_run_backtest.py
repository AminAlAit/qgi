"""Unit tests for run_backtest.py pure functions.

Covers:
  - log_score()              — V1.6 scoring formula
  - compute_metrics()        — F1/precision/recall/AUPRC/NDCG/Brier + all sub-metrics
  - apply_recency()          — recency boost
  - renormalize()            — min-max normalization
  - zscore_per_country()     — within-country z-score (run_backtest copy)
  - rank_fusion_ensemble()   — RRF ensemble
  - build_arrays()           — aligned numpy array builder

Note: zscore_per_country() and rank_fusion_ensemble() in run_backtest.py are
independent copies of the same functions in generate_country_risks.py /
top10_per_tier.py. The math is tested here against run_backtest's local
implementations; test_generate_country_risks.py covers the gcr variants.

No AWS calls. Deterministic, offline-only.

#373 script test coverage audit.
"""
from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import run_backtest as rb  # noqa: E402


# ===========================================================================
# log_score()
# ===========================================================================

class TestLogScore:

    def test_v15_fallback_no_eligible(self):
        """Without eligible_countries, uses V1.5.3 log-count formula."""
        score = rb.log_score(count=10, correlation=0.8, indicator_count=5)
        expected = (
            0.4 * math.log(10 + 1)
            + 0.4 * 0.8
            + 0.2 * math.log(5 + 1)
        )
        assert abs(score - expected) < 1e-9

    def test_v16_prevalence_with_eligible(self):
        """With eligible_countries > 0, uses V1.6 prevalence formula."""
        score = rb.log_score(count=10, correlation=0.8, indicator_count=5, eligible_countries=50)
        prevalence = 10 / 50
        expected = (
            0.30 * math.log(prevalence + 0.01)
            + 0.40 * 0.8
            + 0.15 * math.log(5 + 1)
            + 0.15
        )
        assert abs(score - expected) < 1e-9

    def test_eligible_zero_uses_fallback(self):
        """eligible_countries=0 is falsy → falls back to V1.5.3 log-count formula."""
        score_zero = rb.log_score(count=10, correlation=0.8, indicator_count=5, eligible_countries=0)
        score_none = rb.log_score(count=10, correlation=0.8, indicator_count=5)
        assert abs(score_zero - score_none) < 1e-9

    def test_eligible_below_floor_clamped_to_5(self):
        """Denominator is clamped to max(eligible_countries, 5) to avoid inflated prevalence."""
        # eligible=2 → clamped to 5; eligible=10 → not clamped
        score_small = rb.log_score(count=5, correlation=0.5, indicator_count=3, eligible_countries=2)
        score_five = rb.log_score(count=5, correlation=0.5, indicator_count=3, eligible_countries=5)
        assert abs(score_small - score_five) < 1e-9

    def test_count_zero_no_crash(self):
        """count=0 must not raise (log(0+1) = 0 for V1.5 path)."""
        score = rb.log_score(count=0, correlation=0.5, indicator_count=3)
        assert isinstance(score, float)

    def test_higher_correlation_higher_score(self):
        """Higher correlation → higher score (all else equal)."""
        s_low = rb.log_score(count=10, correlation=0.3, indicator_count=5)
        s_high = rb.log_score(count=10, correlation=0.9, indicator_count=5)
        assert s_high > s_low

    def test_higher_count_higher_score(self):
        """Higher count → higher score (all else equal)."""
        s_small = rb.log_score(count=1, correlation=0.6, indicator_count=5)
        s_large = rb.log_score(count=100, correlation=0.6, indicator_count=5)
        assert s_large > s_small


# ===========================================================================
# compute_metrics()
# ===========================================================================

class TestComputeMetrics:

    def test_perfect_classifier(self):
        """Perfect predictions give F1=1, precision=1, recall=1."""
        y_true = np.array([1, 1, 0, 0])
        y_scores = np.array([0.9, 0.8, 0.2, 0.1])
        m = rb.compute_metrics(y_true, y_scores, threshold=0.5)
        assert m["f1"] == pytest.approx(1.0)
        assert m["precision"] == pytest.approx(1.0)
        assert m["recall"] == pytest.approx(1.0)

    def test_all_wrong_predictions(self):
        """Predicting all negatives when all are positive: precision=0, recall=0, F1=0."""
        y_true = np.array([1, 1, 1])
        y_scores = np.array([0.1, 0.1, 0.1])
        m = rb.compute_metrics(y_true, y_scores, threshold=0.5)
        assert m["f1"] == pytest.approx(0.0)
        assert m["precision"] == pytest.approx(0.0)
        assert m["recall"] == pytest.approx(0.0)

    def test_precision_recall_tradeoff(self):
        """Higher threshold raises precision, lowers recall."""
        y_true = np.array([1, 1, 0, 0, 1])
        y_scores = np.array([0.9, 0.7, 0.6, 0.3, 0.4])
        m_low = rb.compute_metrics(y_true, y_scores, threshold=0.35)
        m_high = rb.compute_metrics(y_true, y_scores, threshold=0.65)
        assert m_high["precision"] >= m_low["precision"]
        assert m_high["recall"] <= m_low["recall"]

    def test_f1_formula_consistency(self):
        """F1 must equal 2*P*R/(P+R)."""
        y_true = np.array([1, 1, 0, 1, 0])
        y_scores = np.array([0.8, 0.6, 0.7, 0.3, 0.1])
        m = rb.compute_metrics(y_true, y_scores, threshold=0.5)
        p, r = m["precision"], m["recall"]
        if p + r > 0:
            expected_f1 = round(2 * p * r / (p + r), 4)
            assert m["f1"] == pytest.approx(expected_f1, abs=1e-3)

    def test_n_total_matches_input_length(self):
        """n_total must equal len(y_true)."""
        y_true = np.array([1, 0, 1, 0, 1])
        y_scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
        m = rb.compute_metrics(y_true, y_scores, threshold=0.6)
        assert m["n_total"] == 5

    def test_n_ground_truth_matches_sum(self):
        """n_ground_truth must equal y_true.sum()."""
        y_true = np.array([1, 1, 0, 0, 1])
        y_scores = np.array([0.9, 0.8, 0.3, 0.2, 0.7])
        m = rb.compute_metrics(y_true, y_scores, threshold=0.5)
        assert m["n_ground_truth"] == 3

    def test_brier_skill_score_positive_for_good_model(self):
        """BSS > 0 for a better-than-baseline model."""
        y_true = np.array([1, 1, 0, 0] * 5)
        y_scores = np.array([0.9, 0.8, 0.2, 0.1] * 5)
        m = rb.compute_metrics(y_true, y_scores, threshold=0.5)
        assert m["brier_skill_score"] > 0

    def test_auprc_bounded_0_1(self):
        """AUPRC must be in [0, 1]."""
        y_true = np.array([1, 0, 1, 0, 1])
        y_scores = np.array([0.9, 0.4, 0.7, 0.3, 0.6])
        m = rb.compute_metrics(y_true, y_scores, threshold=0.5)
        assert 0.0 <= m["auprc"] <= 1.0

    def test_all_negative_ground_truth(self):
        """All-negative ground truth: no crash, F1=0."""
        y_true = np.zeros(5)
        y_scores = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
        m = rb.compute_metrics(y_true, y_scores, threshold=0.5)
        assert m["f1"] == pytest.approx(0.0)

    def test_lift_ratio_to_base_rate(self):
        """Lift must equal precision / base_rate."""
        y_true = np.array([1, 1, 0, 0, 0, 0, 1, 0])
        y_scores = np.array([0.9, 0.8, 0.3, 0.2, 0.1, 0.1, 0.7, 0.05])
        m = rb.compute_metrics(y_true, y_scores, threshold=0.5)
        if m["base_rate"] > 0 and m["precision"] > 0:
            expected_lift = round(m["precision"] / m["base_rate"], 2)
            assert m["lift"] == pytest.approx(expected_lift, abs=1e-2)


# ===========================================================================
# apply_recency()
# ===========================================================================

class TestApplyRecency:

    def test_recent_event_boosted(self):
        """Key present in recency with event 1 year ago gets a boost."""
        preds = {(1, "elections"): 0.5}
        recency = {(1, "elections"): 2019}
        result = rb.apply_recency(preds, recency, cutoff=2020)
        # boost = 0.85^1 = 0.85; weight=0.15; total = 0.5 + 0.15 * 0.85
        expected = 0.5 + 0.15 * (0.85 ** 1)
        assert abs(result[(1, "elections")] - expected) < 1e-9

    def test_old_event_minimal_boost(self):
        """Event 30 years ago gets a small but non-zero boost (0.85^30 * 0.15 ≈ 0.00114)."""
        preds = {(1, "elections"): 0.5}
        recency = {(1, "elections"): 1990}
        result = rb.apply_recency(preds, recency, cutoff=2020)
        expected_boost = 0.15 * (0.85 ** 30)
        assert abs(result[(1, "elections")] - (0.5 + expected_boost)) < 1e-9
        # The boost is very small (< 0.002) compared to a 1-year-ago event
        preds_recent = {(1, "elections"): 0.5}
        recency_recent = {(1, "elections"): 2019}
        result_recent = rb.apply_recency(preds_recent, recency_recent, cutoff=2020)
        assert result[(1, "elections")] < result_recent[(1, "elections")]

    def test_no_recency_key_unchanged(self):
        """Key absent from recency must pass through unchanged."""
        preds = {(2, "elections"): 0.7}
        recency = {}
        result = rb.apply_recency(preds, recency, cutoff=2020)
        assert result[(2, "elections")] == pytest.approx(0.7)

    def test_custom_decay_and_weight(self):
        """Custom decay and weight parameters are respected."""
        preds = {(1, "a"): 0.0}
        recency = {(1, "a"): 2019}
        result = rb.apply_recency(preds, recency, cutoff=2020, decay=0.5, weight=1.0)
        expected = 0.0 + 1.0 * (0.5 ** 1)
        assert abs(result[(1, "a")] - expected) < 1e-9

    def test_empty_preds_returns_empty(self):
        assert rb.apply_recency({}, {}, cutoff=2020) == {}


# ===========================================================================
# renormalize()
# ===========================================================================

class TestRenormalize:

    def test_range_becomes_0_to_1(self):
        """Min becomes 0, max becomes 1."""
        preds = {(1, "a"): 2.0, (1, "b"): 4.0, (1, "c"): 1.0}
        result = rb.renormalize(preds)
        assert result[(1, "c")] == pytest.approx(0.0)
        assert result[(1, "b")] == pytest.approx(1.0)

    def test_midpoint_correct(self):
        """Middle value maps to 0.5 when evenly spaced."""
        preds = {(1, "a"): 0.0, (1, "b"): 5.0, (1, "c"): 10.0}
        result = rb.renormalize(preds)
        assert result[(1, "b")] == pytest.approx(0.5)

    def test_all_equal_no_divzero(self):
        """All-equal scores: range=0, clamped to 1 → all become 0."""
        preds = {(1, "a"): 3.0, (1, "b"): 3.0}
        result = rb.renormalize(preds)
        for v in result.values():
            assert v == pytest.approx(0.0)

    def test_single_entry_no_crash(self):
        """Single entry: min==max → range clamped, returns 0.0."""
        preds = {(1, "a"): 7.0}
        result = rb.renormalize(preds)
        assert result[(1, "a")] == pytest.approx(0.0)

    def test_empty_input_returned_unchanged(self):
        assert rb.renormalize({}) == {}


# ===========================================================================
# zscore_per_country()  — run_backtest local copy
# ===========================================================================

class TestZscorePerCountryBacktest:
    """Tests run_backtest's local zscore_per_country copy.

    The math is the same as gcr.zscore_per_country (already tested in
    test_generate_country_risks.py). These tests ensure the local copy
    hasn't diverged.
    """

    def test_two_country_normalization_independent(self):
        """Each country normalizes independently."""
        preds = {
            (1, "civil_war"): 10.0,
            (1, "elections"): 20.0,
            (2, "civil_war"): 0.5,
            (2, "elections"): 1.5,
        }
        result = rb.zscore_per_country(preds)
        c1 = [result[(1, "civil_war")], result[(1, "elections")]]
        c2 = [result[(2, "civil_war")], result[(2, "elections")]]
        for vals in (c1, c2):
            m = sum(vals) / len(vals)
            assert abs(m) < 1e-9

    def test_single_category_passes_through(self):
        preds = {(5, "elections"): 3.0}
        result = rb.zscore_per_country(preds)
        assert result == {(5, "elections"): 3.0}

    def test_all_equal_no_divzero(self):
        preds = {(3, "a"): 4.0, (3, "b"): 4.0}
        result = rb.zscore_per_country(preds)
        for v in result.values():
            assert abs(v) < 1e-3

    def test_empty_input(self):
        assert rb.zscore_per_country({}) == {}


# ===========================================================================
# rank_fusion_ensemble()
# ===========================================================================

class TestRankFusionEnsemble:

    def test_rrf_math_two_keys(self):
        """Verify exact RRF formula with k=60 for a two-key input."""
        recipe = {(1, "a"): 10.0, (1, "b"): 5.0}
        persist = {(1, "a"): 3.0, (1, "b"): 1.0}
        result = rb.rank_fusion_ensemble(recipe, persist, k=60)
        # Both rank 1 in both signals
        expected_a = 1 / (60 + 1) + 1 / (60 + 1)
        assert abs(result[(1, "a")] - expected_a) < 1e-9

    def test_higher_ranked_in_both_scores_higher(self):
        recipe = {(1, "a"): 10.0, (1, "b"): 5.0}
        persist = {(1, "a"): 3.0, (1, "b"): 1.0}
        result = rb.rank_fusion_ensemble(recipe, persist)
        assert result[(1, "a")] > result[(1, "b")]

    def test_key_missing_from_persist_gets_max_rank(self):
        """Key absent from persist gets max_rank fallback."""
        recipe = {(1, "a"): 10.0, (1, "b"): 5.0}
        persist = {(1, "a"): 3.0}
        result = rb.rank_fusion_ensemble(recipe, persist)
        # (1, "b") is absent from persist → lower score than (1, "a")
        assert result[(1, "a")] > result[(1, "b")]

    def test_all_keys_in_output(self):
        """Output contains union of all input keys."""
        recipe = {(1, "a"): 5.0, (1, "b"): 3.0}
        persist = {(1, "b"): 2.0, (1, "c"): 1.0}
        result = rb.rank_fusion_ensemble(recipe, persist)
        assert set(result.keys()) == {(1, "a"), (1, "b"), (1, "c")}

    def test_empty_inputs(self):
        assert rb.rank_fusion_ensemble({}, {}) == {}


# ===========================================================================
# build_arrays()
# ===========================================================================

class TestBuildArrays:

    def test_ground_truth_keys_get_label_1(self):
        """Keys in ground_truth get y_true=1."""
        preds = {(1, "a"): 0.9, (1, "b"): 0.3}
        gt = {(1, "a")}
        y_true, y_scores = rb.build_arrays(preds, gt)
        # Find index of (1, "a")
        all_pairs = sorted(set(preds.keys()) | gt)
        idx_a = all_pairs.index((1, "a"))
        assert y_true[idx_a] == 1

    def test_non_ground_truth_keys_get_label_0(self):
        preds = {(1, "a"): 0.9, (1, "b"): 0.3}
        gt = {(1, "a")}
        y_true, y_scores = rb.build_arrays(preds, gt)
        all_pairs = sorted(set(preds.keys()) | gt)
        idx_b = all_pairs.index((1, "b"))
        assert y_true[idx_b] == 0

    def test_missing_pred_key_gets_zero_score(self):
        """Key in ground_truth but not in preds gets score=0."""
        preds = {(1, "a"): 0.9}
        gt = {(1, "a"), (1, "b")}
        y_true, y_scores = rb.build_arrays(preds, gt)
        all_pairs = sorted(set(preds.keys()) | gt)
        idx_b = all_pairs.index((1, "b"))
        assert y_scores[idx_b] == pytest.approx(0.0)

    def test_arrays_same_length(self):
        preds = {(1, "a"): 0.9, (2, "b"): 0.5, (3, "c"): 0.1}
        gt = {(1, "a"), (4, "d")}
        y_true, y_scores = rb.build_arrays(preds, gt)
        assert len(y_true) == len(y_scores)

    def test_output_is_numpy_array(self):
        preds = {(1, "a"): 0.5}
        gt = {(1, "a")}
        y_true, y_scores = rb.build_arrays(preds, gt)
        assert isinstance(y_true, np.ndarray)
        assert isinstance(y_scores, np.ndarray)


# ===========================================================================
# build_arrays_with_pairs()  — #400 / #401 variant
# ===========================================================================

class TestBuildArraysWithPairs:

    def test_returns_pairs_aligned_with_arrays(self):
        preds = {(1, "a"): 0.9, (2, "b"): 0.4}
        gt = {(1, "a"), (3, "c")}
        y_true, y_scores, pairs = rb.build_arrays_with_pairs(preds, gt)
        # Pairs should be the sorted union of prediction + ground-truth keys.
        assert pairs == sorted({(1, "a"), (2, "b"), (3, "c")})
        # Arrays aligned to pairs.
        for p, t, s in zip(pairs, y_true, y_scores):
            assert t == (1 if p in gt else 0)
            assert s == pytest.approx(preds.get(p, 0.0))


# ===========================================================================
# stratified_metrics()  — #400 / #401
# ===========================================================================

class TestStratifiedMetrics:

    def test_groups_by_category(self):
        # 3 countries, 2 categories. Build y_pred so:
        #   civil_war: 2 TP out of 2 gt, 0 FP → F1=1.0
        #   elections: 1 TP out of 2 gt, 1 FP → precision=0.5, recall=0.5, F1=0.5
        pairs = [
            (1, "civil_war"), (1, "elections"),
            (2, "civil_war"), (2, "elections"),
            (3, "civil_war"), (3, "elections"),
            (4, "civil_war"), (4, "elections"),
            (5, "civil_war"), (5, "elections"),
        ]
        # Two civil_war positives, both predicted positive (TP×2, FP=0).
        # Two elections positives, one predicted positive (TP=1, FN=1),
        # plus one elections false positive (FP=1).
        y_true = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        y_pred = [1, 1, 1, 0, 0, 1, 0, 0, 0, 0]
        result = rb.stratified_metrics(
            pairs, y_true, y_pred, group_fn=lambda p: p[1], min_samples=1,
        )
        assert result["civil_war"]["f1"] == pytest.approx(1.0)
        assert result["civil_war"]["n_gt"] == 2
        assert result["elections"]["precision"] == pytest.approx(0.5)
        assert result["elections"]["recall"] == pytest.approx(0.5)
        assert result["elections"]["f1"] == pytest.approx(0.5)

    def test_groups_by_country(self):
        # Country 1: perfect (1 TP), Country 2: all wrong (1 FN, 1 FP)
        pairs = [
            (1, "a"), (1, "b"),
            (2, "a"), (2, "b"),
        ]
        y_true = [1, 0, 1, 0]
        y_pred = [1, 0, 0, 1]
        result = rb.stratified_metrics(
            pairs, y_true, y_pred, group_fn=lambda p: p[0], min_samples=1,
        )
        assert result[1]["f1"] == pytest.approx(1.0)
        assert result[2]["f1"] == pytest.approx(0.0)

    def test_min_samples_filter_drops_small_groups(self):
        pairs = [(1, "a")] * 3 + [(2, "b")] * 10
        y_true = [1, 0, 1] + [1] * 5 + [0] * 5
        y_pred = [1, 0, 1] + [1] * 5 + [0] * 5
        result = rb.stratified_metrics(
            pairs, y_true, y_pred, group_fn=lambda p: p[0], min_samples=5,
        )
        assert 1 not in result  # only 3 samples < 5
        assert 2 in result

    def test_zero_division_safe(self):
        """Group with zero predictions and zero positives → F1=0, no crash."""
        pairs = [(1, "a"), (1, "b"), (1, "c"), (1, "d"), (1, "e")]
        y_true = [0, 0, 0, 0, 0]
        y_pred = [0, 0, 0, 0, 0]
        result = rb.stratified_metrics(
            pairs, y_true, y_pred, group_fn=lambda p: p[0], min_samples=1,
        )
        assert result[1]["f1"] == 0.0
        assert result[1]["precision"] == 0.0
        assert result[1]["recall"] == 0.0

    def test_empty_inputs_returns_empty(self):
        result = rb.stratified_metrics([], [], [], group_fn=lambda p: p[0])
        assert result == {}


# ===========================================================================
# summarize_per_country_distribution()  — #401
# ===========================================================================

class TestSummarizePerCountryDistribution:

    def test_basic_percentiles_and_top_bottom(self):
        # 10 countries with F1 evenly spaced 0.1..1.0
        per_country = {
            i: {"f1": round(i * 0.1, 1), "precision": 0, "recall": 0, "n_gt": 1, "n_total": 5}
            for i in range(1, 11)
        }
        result = rb.summarize_per_country_distribution(per_country, top_k=3)
        assert result["n_countries"] == 10
        assert result["distribution"]["median"] == pytest.approx(0.5) or result["distribution"]["median"] == pytest.approx(0.6)
        # Worst 3 should be countries 1, 2, 3 (F1 0.1, 0.2, 0.3).
        assert [r["country_id"] for r in result["worst_k"]] == [1, 2, 3]
        # Best 3 should be countries 10, 9, 8 (F1 1.0, 0.9, 0.8).
        assert [r["country_id"] for r in result["best_k"]] == [10, 9, 8]

    def test_empty_input_returns_none(self):
        assert rb.summarize_per_country_distribution({}) is None

    def test_preserves_country_metrics_in_top_bottom(self):
        per_country = {
            "a": {"f1": 0.1, "precision": 0.2, "recall": 0.3, "n_gt": 4, "n_total": 10},
            "b": {"f1": 0.9, "precision": 0.9, "recall": 0.9, "n_gt": 9, "n_total": 10},
        }
        result = rb.summarize_per_country_distribution(per_country, top_k=2)
        # Worst should preserve full metrics
        assert result["worst_k"][0]["precision"] == 0.2
        assert result["worst_k"][0]["n_total"] == 10


# ===========================================================================
# load_country_id_to_region()  — #396 YAML parser
# ===========================================================================

class TestLoadCountryIdToRegion:

    def _write_yaml(self, tmp_path, content):
        p = tmp_path / "country_regions.yaml"
        p.write_text(content, encoding="utf-8")
        return p

    def test_parses_basic_yaml_structure(self, tmp_path, monkeypatch):
        """Well-formed YAML with 2 regions produces correct alpha_2 → region map."""
        yaml = tmp_path / "country_regions.yaml"
        yaml.write_text(
            "version: 1\n"
            "AFR:\n  - KE\n  - NG\n  - ZA\n"
            "EUR:\n  - DE\n  - FR\n",
            encoding="utf-8",
        )
        # Mock run_query so we don't need Athena.
        mock_rows = [
            {"id": "1", "alpha_2": "KE"},
            {"id": "2", "alpha_2": "DE"},
            {"id": "3", "alpha_2": "NG"},
            {"id": "4", "alpha_2": "FR"},
            {"id": "5", "alpha_2": "US"},  # not in YAML → dropped
        ]
        monkeypatch.setattr(rb, "run_query", lambda *a, **kw: mock_rows)
        result = rb.load_country_id_to_region(
            athena=None, bucket="b", workgroup="w",
            regions_yaml_path=str(yaml),
        )
        assert result[1] == "AFR"
        assert result[2] == "EUR"
        assert result[3] == "AFR"
        assert result[4] == "EUR"
        # US wasn't in YAML → not mapped
        assert 5 not in result

    def test_missing_yaml_returns_empty_dict(self, tmp_path, monkeypatch):
        """Missing file → empty dict (graceful no-op, no crash)."""
        monkeypatch.setattr(rb, "run_query", lambda *a, **kw: [])
        result = rb.load_country_id_to_region(
            athena=None, bucket="b", workgroup="w",
            regions_yaml_path=str(tmp_path / "nonexistent.yaml"),
        )
        assert result == {}

    def test_skips_version_and_comments(self, tmp_path, monkeypatch):
        """version: and # comment lines don't pollute the region map."""
        yaml = tmp_path / "country_regions.yaml"
        yaml.write_text(
            "# This is a comment\n"
            "version: 1\n"
            "# Another comment\n"
            "AFR:\n  - KE\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            rb, "run_query",
            lambda *a, **kw: [{"id": "1", "alpha_2": "KE"}],
        )
        result = rb.load_country_id_to_region(
            athena=None, bucket="b", workgroup="w",
            regions_yaml_path=str(yaml),
        )
        assert result == {1: "AFR"}

    def test_non_region_keys_ignored(self, tmp_path, monkeypatch):
        """Keys that aren't 3-letter uppercase (e.g. 'metadata:') are skipped."""
        yaml = tmp_path / "country_regions.yaml"
        yaml.write_text(
            "metadata:\n  - FOO\n"
            "AFR:\n  - KE\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            rb, "run_query",
            lambda *a, **kw: [{"id": "1", "alpha_2": "KE"}, {"id": "99", "alpha_2": "FOO"}],
        )
        result = rb.load_country_id_to_region(
            athena=None, bucket="b", workgroup="w",
            regions_yaml_path=str(yaml),
        )
        # KE maps to AFR; FOO was under metadata: and should be ignored.
        assert result[1] == "AFR"
        assert 99 not in result

    def test_alpha_2_case_insensitive(self, tmp_path, monkeypatch):
        """Lower-case alpha_2 from Athena still resolves via upper-case YAML."""
        yaml = tmp_path / "country_regions.yaml"
        yaml.write_text("AFR:\n  - KE\n", encoding="utf-8")
        monkeypatch.setattr(
            rb, "run_query",
            lambda *a, **kw: [{"id": "1", "alpha_2": "ke"}],
        )
        result = rb.load_country_id_to_region(
            athena=None, bucket="b", workgroup="w",
            regions_yaml_path=str(yaml),
        )
        assert result[1] == "AFR"
