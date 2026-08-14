"""Tests for `qgi_ml.src.icc.icc`."""
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

from icc.icc import (  # noqa: E402
    ICCResult,
    bootstrap_icc_ci,
    compute_icc,
    compute_icc_for_features,
    shrinkage_weight_from_icc,
)


# -- compute_icc -------------------------------------------------------------


class TestComputeIcc:
    def test_pure_country_identity_high_icc(self) -> None:
        # Country A: always 100; Country B: always 200; Country C: always 300
        # Each country is constant within itself; differs strongly between countries.
        # Within-country variance = 0; between-country variance > 0.
        # ICC should be 1.0 (or very close).
        values = np.array([100, 100, 100, 200, 200, 200, 300, 300, 300], dtype=float)
        countries = np.array(["A", "A", "A", "B", "B", "B", "C", "C", "C"])
        # Within-country variance is 0; need to handle the edge case
        # where sigma_within = 0. Add tiny noise.
        values = values + np.random.default_rng(0).normal(0, 0.001, len(values))
        result = compute_icc(values, countries)
        assert result.icc > 0.99

    def test_pure_within_country_variance_low_icc(self) -> None:
        # All countries fluctuate identically around 0; means are identical.
        # Within-country variance > 0; between-country variance ≈ 0.
        rng = np.random.default_rng(42)
        n_per_country = 20
        values_a = rng.normal(0, 1, n_per_country)
        values_b = rng.normal(0, 1, n_per_country)
        values_c = rng.normal(0, 1, n_per_country)
        values = np.concatenate([values_a, values_b, values_c])
        countries = np.array(["A"] * n_per_country + ["B"] * n_per_country + ["C"] * n_per_country)
        result = compute_icc(values, countries)
        # ICC should be close to 0 (or at least < 0.4 with this much within variance)
        assert result.icc < 0.4

    def test_balanced_within_between_icc_around_half(self) -> None:
        rng = np.random.default_rng(7)
        # Mix: each country has different mean (between) AND noise (within)
        values_a = rng.normal(0, 1, 20)
        values_b = rng.normal(2, 1, 20)
        values_c = rng.normal(4, 1, 20)
        values = np.concatenate([values_a, values_b, values_c])
        countries = np.array(["A"] * 20 + ["B"] * 20 + ["C"] * 20)
        result = compute_icc(values, countries)
        # With std=1 within and means {0,2,4} (between SD ~2):
        # sigma_within ~1; sigma_between ~4 → ICC = 4/5 = 0.8
        assert 0.5 < result.icc < 0.95

    def test_too_few_countries_skips(self) -> None:
        values = np.array([1, 2, 3, 4, 5], dtype=float)
        countries = np.array(["A", "A", "A", "A", "A"])  # only 1 country
        result = compute_icc(values, countries, min_countries=3)
        assert np.isnan(result.icc)
        assert result.skip_reason is not None
        assert "insufficient_countries" in result.skip_reason

    def test_zero_total_variance_skipped(self) -> None:
        # All values identical
        values = np.full(20, 5.0)
        countries = np.repeat(["A", "B", "C", "D"], 5)
        result = compute_icc(values, countries)
        assert np.isnan(result.icc)
        assert result.skip_reason == "zero_total_variance"

    def test_nan_values_dropped(self) -> None:
        values = np.array([1.0, np.nan, 2.0, np.nan, 3.0, 4.0, 5.0, 6.0])
        countries = np.array(["A", "A", "B", "B", "C", "C", "D", "D"])
        result = compute_icc(values, countries, min_observations_per_country=1)
        # After NaN drop: 6 obs across 4 countries
        assert result.n_observations_used == 6

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="shape mismatch"):
            compute_icc(np.array([1.0, 2.0]), np.array(["A", "B", "C"]))

    def test_high_icc_soft_flag_at_0_7(self) -> None:
        # Country A: 100±0.01, Country B: 200±0.01 → very high ICC
        rng = np.random.default_rng(0)
        values = np.concatenate([
            rng.normal(100, 0.01, 20),
            rng.normal(200, 0.01, 20),
            rng.normal(300, 0.01, 20),
        ])
        countries = np.repeat(["A", "B", "C"], 20)
        result = compute_icc(values, countries)
        assert result.icc > 0.7
        assert result.soft_flag_high_icc is True

    def test_n_observations_tracked(self) -> None:
        rng = np.random.default_rng(0)
        values = np.concatenate([
            rng.normal(0, 1, 10),
            rng.normal(0, 1, 10),
            rng.normal(0, 1, 10),
        ])
        countries = np.repeat(["A", "B", "C"], 10)
        result = compute_icc(values, countries, min_observations_per_country=2)
        assert result.n_observations_used == 30
        assert result.n_countries_used == 3


# -- bootstrap_icc_ci --------------------------------------------------------


class TestBootstrapIccCi:
    def _build_high_icc_data(self):
        rng = np.random.default_rng(0)
        n_per_country = 12
        n_countries = 8
        values = []
        countries = []
        for i in range(n_countries):
            values.append(rng.normal(i * 5, 0.5, n_per_country))
            countries.extend([f"c{i}"] * n_per_country)
        return np.concatenate(values), np.array(countries)

    def test_ci_brackets_point(self) -> None:
        values, countries = self._build_high_icc_data()
        point, lo, hi = bootstrap_icc_ci(values, countries, n_bootstrap=100, seed=0)
        assert lo <= point <= hi

    def test_seeded_determinism(self) -> None:
        values, countries = self._build_high_icc_data()
        a = bootstrap_icc_ci(values, countries, n_bootstrap=50, seed=42)
        b = bootstrap_icc_ci(values, countries, n_bootstrap=50, seed=42)
        assert a == b

    def test_invalid_confidence_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            bootstrap_icc_ci(np.array([1.0, 2.0]), np.array(["A", "B"]),
                             n_bootstrap=10, confidence=1.5)

    def test_high_icc_data_yields_high_lower_bound(self) -> None:
        values, countries = self._build_high_icc_data()
        # Strong between-country signal → CI should be high
        point, lo, hi = bootstrap_icc_ci(values, countries, n_bootstrap=200, seed=0)
        assert point > 0.85
        # Cluster bootstrap with replacement may produce lower CIs, but
        # the point estimate should still be solidly high
        assert lo > 0.5


# -- compute_icc_for_features ------------------------------------------------


class TestComputeIccForFeatures:
    def _build_panel(self) -> pd.DataFrame:
        rng = np.random.default_rng(0)
        rows = []
        for c_idx in range(5):
            country = f"c{c_idx}"
            for year in range(2014, 2022):
                rows.append({
                    "country": country, "year": year,
                    "country_proxy_feat": float(c_idx) * 100 + rng.normal(0, 0.1),
                    "dynamic_feat": rng.normal(0, 1),
                })
        return pd.DataFrame(rows)

    def test_distinguishes_country_proxy_from_dynamic(self) -> None:
        panel = self._build_panel()
        out = compute_icc_for_features(
            panel, ["country_proxy_feat", "dynamic_feat"],
            n_bootstrap=50, seed=0,
        )
        # Country-proxy feature: high ICC
        assert out["country_proxy_feat"].icc > 0.9
        assert out["country_proxy_feat"].soft_flag_high_icc is True
        # Dynamic feature: low ICC
        assert out["dynamic_feat"].icc < 0.4
        assert out["dynamic_feat"].soft_flag_high_icc is False

    def test_window_filter(self) -> None:
        panel = self._build_panel()
        out = compute_icc_for_features(
            panel, ["dynamic_feat"], window_start=1900, window_end=1910,
            n_bootstrap=10, seed=0,
        )
        # Empty window → skip
        assert out["dynamic_feat"].skip_reason is not None

    def test_missing_columns_raises(self) -> None:
        panel = self._build_panel()
        with pytest.raises(ValueError, match="missing columns"):
            compute_icc_for_features(panel, ["nonexistent_feature"], n_bootstrap=10)

    def test_returns_one_result_per_feature(self) -> None:
        panel = self._build_panel()
        out = compute_icc_for_features(
            panel, ["country_proxy_feat", "dynamic_feat"], n_bootstrap=10, seed=0,
        )
        assert set(out.keys()) == {"country_proxy_feat", "dynamic_feat"}


# -- shrinkage_weight_from_icc -----------------------------------------------


class TestShrinkageWeightFromIcc:
    def test_low_icc_full_weight(self) -> None:
        assert shrinkage_weight_from_icc(0.0) == 1.0

    def test_high_icc_zero_weight(self) -> None:
        assert shrinkage_weight_from_icc(1.0) == 0.0

    def test_medium_icc_half_weight(self) -> None:
        assert shrinkage_weight_from_icc(0.5) == 0.5

    def test_nan_icc_zero_weight_conservative(self) -> None:
        assert shrinkage_weight_from_icc(float("nan")) == 0.0

    def test_clamps_negative_icc(self) -> None:
        # ICC can be slightly negative due to bootstrap variance; clamp
        assert shrinkage_weight_from_icc(-0.1) == 1.0  # clamped (since 1 - (-0.1) = 1.1 → clamped to 1)

    def test_clamps_icc_above_1(self) -> None:
        assert shrinkage_weight_from_icc(1.5) == 0.0  # clamped (1 - 1.5 = -0.5 → clamped to 0)


# -- ICCResult dataclass -----------------------------------------------------


class TestICCResult:
    def test_default_soft_flag_false(self) -> None:
        r = ICCResult(
            icc=0.3, ci_lower=0.2, ci_upper=0.4,
            sigma_between=1.0, sigma_within=2.0,
            n_countries_used=10, n_observations_used=80,
        )
        assert r.soft_flag_high_icc is False

    def test_skip_reason_optional(self) -> None:
        r = ICCResult(
            icc=float("nan"), ci_lower=float("nan"), ci_upper=float("nan"),
            sigma_between=float("nan"), sigma_within=float("nan"),
            n_countries_used=0, n_observations_used=0,
            skip_reason="test_reason",
        )
        assert r.skip_reason == "test_reason"
