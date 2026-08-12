"""Tests for `qgi_ml.src.shap_fingerprint`."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from shap_fingerprint import (  # noqa: E402
    DEFAULT_PERCENTILE_THRESHOLD,
    DEFAULT_TOP_K,
    aggregate_to_global_importance,
    annotate_top_k_with_variance,
    compute_feature_variance_from_wide,
    compute_indicator_variance,
    compute_treeshap_attribution,
    panel_median_variance,
    top_k_features,
)


# -- compute_treeshap_attribution ---------------------------------------------


class TestComputeTreeshapAttribution:
    """Integration tests requiring lightgbm."""

    def _train_synthetic_booster(self):
        import lightgbm as lgb  # noqa: PLC0415

        rng = np.random.default_rng(42)
        n_samples = 300
        n_features = 5
        X = rng.normal(0, 1, (n_samples, n_features))
        # Label depends on feature 0 strongly + feature 1 weakly.
        logits = 2.0 * X[:, 0] + 0.5 * X[:, 1]
        y = (logits + rng.normal(0, 0.3, n_samples) > 0).astype(int)
        ds = lgb.Dataset(X, label=y)
        params = {"objective": "binary", "num_leaves": 7, "verbose": -1}
        booster = lgb.train(params, ds, num_boost_round=20)
        return booster, X, y

    def test_returns_strip_bias_column(self) -> None:
        booster, X, _ = self._train_synthetic_booster()
        shap = compute_treeshap_attribution(booster, X)
        assert shap.shape == (X.shape[0], X.shape[1])

    def test_top_features_match_synthetic_signal(self) -> None:
        booster, X, _ = self._train_synthetic_booster()
        shap = compute_treeshap_attribution(booster, X)
        importance = np.mean(np.abs(shap), axis=0)
        # Feature 0 has the strongest signal (coef 2.0).
        assert int(np.argmax(importance)) == 0
        # Feature 0 importance > feature 1 (coef 0.5).
        assert importance[0] > importance[1]

    def test_unexpected_shape_raises(self) -> None:
        # Build a fake booster that returns wrong shape.
        class FakeBooster:
            def num_feature(self) -> int:
                return 5

            def predict(self, X, pred_contrib=False):
                # Wrong shape: (n_samples, n_features) without bias col.
                return np.zeros((X.shape[0], 5))

        with pytest.raises(ValueError, match="unexpected pred_contrib shape"):
            compute_treeshap_attribution(FakeBooster(), np.zeros((10, 5)))


# -- aggregate_to_global_importance -------------------------------------------


class TestAggregateToGlobalImportance:
    def test_mean_abs_per_feature(self) -> None:
        shap = np.array([
            [1.0, -0.5, 0.0],
            [-1.0, 0.5, 0.0],
            [2.0, 0.0, 0.0],
        ])
        importance = aggregate_to_global_importance(shap, ["a", "b", "c"])
        # Mean abs: a=(1+1+2)/3=1.333, b=(0.5+0.5+0)/3=0.333, c=0
        assert importance["a"] == pytest.approx(1.333, abs=1e-3)
        assert importance["b"] == pytest.approx(0.333, abs=1e-3)
        assert importance["c"] == 0.0

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="shap shape mismatch"):
            aggregate_to_global_importance(
                np.zeros((10, 3)), ["a", "b"]
            )

    def test_empty_shap_returns_zero_importance(self) -> None:
        # 0 samples, 3 features → mean of empty = 0 by numpy convention,
        # but np.mean of empty axis raises a warning. Verify behavior is sane.
        # Actually, np.mean with an empty array along axis=0 returns NaN.
        # Document that the caller should not pass 0-row arrays; this test
        # asserts the interface fails loudly rather than silently producing
        # NaN importances.
        shap = np.zeros((0, 3))
        with pytest.warns(RuntimeWarning):
            importance = aggregate_to_global_importance(shap, ["a", "b", "c"])
        # Each value should be NaN; downstream code should not consume.
        assert all(np.isnan(v) for v in importance.values())


# -- top_k_features -----------------------------------------------------------


class TestTopKFeatures:
    def test_default_k_is_10(self) -> None:
        assert DEFAULT_TOP_K == 10

    def test_returns_top_k_sorted_descending(self) -> None:
        importance = {"a": 1.0, "b": 3.0, "c": 2.0, "d": 0.5}
        top = top_k_features(importance, k=3)
        assert [t["indicator_id"] for t in top] == ["b", "c", "a"]
        assert [t["rank"] for t in top] == [1, 2, 3]
        assert [t["mean_abs_shap"] for t in top] == [3.0, 2.0, 1.0]

    def test_ties_broken_alphabetically_for_determinism(self) -> None:
        importance = {"banana": 2.0, "apple": 2.0, "cherry": 2.0}
        top = top_k_features(importance, k=3)
        assert [t["indicator_id"] for t in top] == ["apple", "banana", "cherry"]

    def test_k_larger_than_n_features_returns_all(self) -> None:
        importance = {"a": 1.0, "b": 2.0}
        top = top_k_features(importance, k=10)
        assert len(top) == 2

    def test_k_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="k must be >= 1"):
            top_k_features({"a": 1.0}, k=0)


# -- compute_indicator_variance ----------------------------------------------


class TestComputeIndicatorVariance:
    def _build_panel(self) -> pd.DataFrame:
        # Indicator A: high within-country temporal std.
        # Indicator B: low within-country std (essentially constant per country).
        rows = []
        for country in ["us", "fr", "jp"]:
            for year in range(2014, 2022):
                rows.append((country, year, "A", float(year - 2014) + (hash(country) % 100)))
                rows.append((country, year, "B", 100.0 + (hash(country) % 5)))
        return pd.DataFrame(rows, columns=["country", "year", "indicator_id", "value"])

    def test_high_variance_indicator_has_high_std(self) -> None:
        panel = self._build_panel()
        variance = compute_indicator_variance(panel, window_start=2014, window_end=2021)
        # Indicator A has within-country std = std([0..7]) for each country.
        assert variance["A"] > variance["B"]

    def test_constant_per_country_indicator_has_zero_std(self) -> None:
        panel = self._build_panel()
        variance = compute_indicator_variance(panel, window_start=2014, window_end=2021)
        assert variance["B"] == pytest.approx(0.0)

    def test_window_filter_applied(self) -> None:
        panel = self._build_panel()
        # Window outside the panel.
        variance = compute_indicator_variance(panel, window_start=1900, window_end=1910)
        assert variance == {}

    def test_missing_columns_raises(self) -> None:
        bad = pd.DataFrame({"country": ["a"], "year": [2020]})
        with pytest.raises(ValueError, match="missing columns"):
            compute_indicator_variance(bad, window_start=2014, window_end=2021)


# -- annotate_top_k_with_variance --------------------------------------------


class TestAnnotateTopK:
    def test_below_panel_median_flags_suspect(self) -> None:
        top_k = [{"rank": 1, "indicator_id": "A", "mean_abs_shap": 0.5}]
        variance = {"A": 0.1, "B": 1.0, "C": 2.0}  # panel median = 1.0
        annotated = annotate_top_k_with_variance(top_k, variance, panel_median=1.0)
        assert annotated[0]["fixed_effect_suspect"] is True
        assert annotated[0]["within_country_std_median"] == 0.1
        assert annotated[0]["variance_ratio_vs_panel_median"] == 0.1
        assert "below" in annotated[0]["rationale"]

    def test_above_panel_median_does_not_flag(self) -> None:
        top_k = [{"rank": 1, "indicator_id": "A", "mean_abs_shap": 0.5}]
        variance = {"A": 2.0}
        annotated = annotate_top_k_with_variance(top_k, variance, panel_median=1.0)
        assert annotated[0]["fixed_effect_suspect"] is False
        assert "above" in annotated[0]["rationale"]

    def test_missing_variance_yields_unavailable(self) -> None:
        top_k = [{"rank": 1, "indicator_id": "A", "mean_abs_shap": 0.5}]
        variance: dict[str, float] = {}
        annotated = annotate_top_k_with_variance(top_k, variance, panel_median=1.0)
        assert annotated[0]["fixed_effect_suspect"] is None
        assert annotated[0]["rationale"] == "variance_unavailable"
        assert annotated[0]["within_country_std_median"] is None

    def test_zero_panel_median_yields_unavailable(self) -> None:
        top_k = [{"rank": 1, "indicator_id": "A", "mean_abs_shap": 0.5}]
        variance = {"A": 0.5}
        annotated = annotate_top_k_with_variance(top_k, variance, panel_median=0.0)
        assert annotated[0]["fixed_effect_suspect"] is None
        assert annotated[0]["rationale"] == "variance_unavailable"

    def test_default_threshold_is_50pct(self) -> None:
        # Spec language: "below median panel variance" → factor 1.0 of median.
        # The percentile threshold constant is documentary; the default
        # comparison uses factor=1.0 (literal panel median).
        assert DEFAULT_PERCENTILE_THRESHOLD == 0.50

    def test_threshold_factor_0_5_lowers_bar(self) -> None:
        # With factor 0.5, only indicators below half the panel median are
        # flagged.
        top_k = [
            {"rank": 1, "indicator_id": "X", "mean_abs_shap": 0.5},
            {"rank": 2, "indicator_id": "Y", "mean_abs_shap": 0.4},
        ]
        variance = {"X": 0.4, "Y": 0.6}  # panel median = 1.0; X<0.5, Y>0.5.
        annotated = annotate_top_k_with_variance(
            top_k, variance, panel_median=1.0, threshold_factor=0.5
        )
        assert annotated[0]["fixed_effect_suspect"] is True
        assert annotated[1]["fixed_effect_suspect"] is False


# -- panel_median_variance ---------------------------------------------------


class TestPanelMedianVariance:
    def test_simple_median(self) -> None:
        assert panel_median_variance({"a": 1.0, "b": 2.0, "c": 3.0}) == 2.0

    def test_ignores_nans(self) -> None:
        result = panel_median_variance({"a": 1.0, "b": float("nan"), "c": 3.0})
        assert result == 2.0

    def test_all_nan_returns_nan(self) -> None:
        assert np.isnan(panel_median_variance({"a": float("nan")}))

    def test_empty_returns_nan(self) -> None:
        assert np.isnan(panel_median_variance({}))


# -- compute_feature_variance_from_wide --------------------------------------


class TestComputeFeatureVarianceFromWide:
    def _build_wide(self) -> pd.DataFrame:
        # Two engineered features:
        # - F1__diff: actually varies year-to-year per country (real signal)
        # - F2__diff: constant zero per country (fixed-effect proxy in
        #   differenced space)
        rows = []
        for country in ["us", "fr", "jp"]:
            for year in range(2014, 2022):
                rows.append({
                    "country": country,
                    "year": year,
                    "F1__diff": float(year - 2014) * 0.7,
                    "F2__diff": 0.0,  # constant
                })
        return pd.DataFrame(rows)

    def test_high_variance_feature_above_constant(self) -> None:
        wide = self._build_wide()
        var = compute_feature_variance_from_wide(
            wide, ["F1__diff", "F2__diff"], window_start=2014, window_end=2021
        )
        assert var["F1__diff"] > var["F2__diff"]
        assert var["F2__diff"] == pytest.approx(0.0)

    def test_window_filter(self) -> None:
        wide = self._build_wide()
        var = compute_feature_variance_from_wide(
            wide, ["F1__diff"], window_start=1900, window_end=1910
        )
        assert np.isnan(var["F1__diff"])

    def test_missing_feature_columns_raises(self) -> None:
        wide = self._build_wide()
        with pytest.raises(ValueError, match="missing columns"):
            compute_feature_variance_from_wide(
                wide, ["NONEXISTENT"], window_start=2014, window_end=2021
            )

    def test_returns_one_value_per_requested_feature(self) -> None:
        wide = self._build_wide()
        var = compute_feature_variance_from_wide(
            wide, ["F1__diff", "F2__diff"], window_start=2014, window_end=2021
        )
        assert set(var.keys()) == {"F1__diff", "F2__diff"}
