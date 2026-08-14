"""Tests for `qgi_ml.src.cross_recipe_corr`."""
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

from cross_recipe_corr import (  # noqa: E402
    CorrelationMatrixSnapshot,
    compute_correlation_matrix,
    compute_per_year_snapshots,
    find_persistent_high_corrs,
    matrix_stability_over_time,
    predictions_to_country_recipe_matrix,
)


def _build_predictions(years=(2022, 2023), n_countries=50, n_recipes=3, seed=0,
                      coupling_strength=0.0):
    """Build synthetic predictions list. coupling_strength=0 → independent
    recipes; >0 → recipes share signal across countries."""
    rng = np.random.default_rng(seed)
    rows = []
    for year in years:
        for c_idx in range(n_countries):
            country = f"c{c_idx}"
            base = rng.uniform(0.01, 0.99)
            for r_idx in range(n_recipes):
                p = (1 - coupling_strength) * rng.uniform(0.01, 0.99) + coupling_strength * base
                rows.append({
                    "country": country, "year": year,
                    "recipe_id": f"recipe_{r_idx}",
                    "predicted_probability": float(p),
                    "label": int(rng.integers(0, 2)),
                })
    return rows


# -- predictions_to_country_recipe_matrix ---------------------------------


class TestPredictionsToCountryRecipeMatrix:
    def test_returns_country_x_recipe_shape(self):
        preds = _build_predictions(years=(2022,), n_countries=10, n_recipes=4)
        matrix, recipe_ids = predictions_to_country_recipe_matrix(preds, year=2022)
        assert matrix.shape == (10, 4)
        assert len(recipe_ids) == 4

    def test_filters_by_year(self):
        preds = _build_predictions(years=(2022, 2023), n_countries=5, n_recipes=2)
        matrix, _ = predictions_to_country_recipe_matrix(preds, year=2022)
        # Only 2022's predictions should appear
        assert matrix.shape == (5, 2)

    def test_empty_when_year_absent(self):
        preds = _build_predictions(years=(2022,), n_countries=5, n_recipes=2)
        matrix, recipe_ids = predictions_to_country_recipe_matrix(preds, year=2025)
        assert matrix.empty
        assert recipe_ids == []

    def test_missing_columns_raises(self):
        bad = [{"country": "x", "year": 2022}]
        with pytest.raises(ValueError, match="missing required keys"):
            predictions_to_country_recipe_matrix(bad, year=2022)


# -- compute_correlation_matrix -------------------------------------------


class TestComputeCorrelationMatrix:
    def test_independent_recipes_low_correlation(self):
        rng = np.random.default_rng(0)
        df = pd.DataFrame(rng.normal(0, 1, (200, 3)), columns=["a", "b", "c"])
        corr = compute_correlation_matrix(df)
        assert corr.shape == (3, 3)
        # Off-diagonal correlations should be near 0 with n=200 random samples
        assert abs(corr[0, 1]) < 0.2

    def test_perfectly_correlated_yields_1(self):
        df = pd.DataFrame({
            "a": np.linspace(0, 1, 100),
            "b": np.linspace(0, 1, 100),
        })
        corr = compute_correlation_matrix(df)
        np.testing.assert_allclose(corr[0, 1], 1.0)

    def test_perfectly_anticorrelated_yields_neg1(self):
        df = pd.DataFrame({
            "a": np.linspace(0, 1, 100),
            "b": np.linspace(1, 0, 100),
        })
        corr = compute_correlation_matrix(df)
        np.testing.assert_allclose(corr[0, 1], -1.0)

    def test_diagonal_is_1(self):
        rng = np.random.default_rng(0)
        df = pd.DataFrame(rng.normal(0, 1, (100, 3)), columns=["a", "b", "c"])
        corr = compute_correlation_matrix(df)
        np.testing.assert_allclose(np.diag(corr), 1.0)

    def test_invalid_method_raises(self):
        df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        with pytest.raises(ValueError, match="method must be"):
            compute_correlation_matrix(df, method="bogus")

    def test_empty_df_returns_empty_matrix(self):
        corr = compute_correlation_matrix(pd.DataFrame())
        assert corr.shape == (0, 0)

    def test_spearman_method(self):
        # Spearman on monotone but non-linear data
        df = pd.DataFrame({
            "a": np.arange(100),
            "b": np.arange(100) ** 2,  # monotone but non-linear
        })
        corr_s = compute_correlation_matrix(df, method="spearman")
        np.testing.assert_allclose(corr_s[0, 1], 1.0)


# -- compute_per_year_snapshots -------------------------------------------


class TestComputePerYearSnapshots:
    def test_one_snapshot_per_year(self):
        preds = _build_predictions(years=(2022, 2023, 2024), n_countries=50, n_recipes=3)
        snaps = compute_per_year_snapshots(preds, min_countries_per_year=10)
        assert len(snaps) == 3
        assert {s.year for s in snaps} == {2022, 2023, 2024}

    def test_skips_low_country_count(self):
        preds = _build_predictions(years=(2022,), n_countries=5, n_recipes=2)
        snaps = compute_per_year_snapshots(preds, min_countries_per_year=10)
        assert len(snaps) == 1
        assert snaps[0].skip_reason is not None

    def test_independent_recipes_show_low_off_diagonal(self):
        preds = _build_predictions(years=(2022,), n_countries=200, n_recipes=3, seed=42)
        snaps = compute_per_year_snapshots(preds, min_countries_per_year=20)
        assert snaps[0].skip_reason is None
        m = np.asarray(snaps[0].matrix)
        # Independent recipes → off-diagonal near 0
        assert abs(m[0, 1]) < 0.2

    def test_coupled_recipes_show_high_off_diagonal(self):
        preds = _build_predictions(years=(2022,), n_countries=200, n_recipes=3, seed=42,
                                   coupling_strength=0.95)
        snaps = compute_per_year_snapshots(preds, min_countries_per_year=20)
        m = np.asarray(snaps[0].matrix)
        # Coupled recipes → off-diagonal high
        assert m[0, 1] > 0.5


# -- matrix_stability_over_time -------------------------------------------


class TestMatrixStabilityOverTime:
    def test_stable_matrix_low_distance(self):
        preds = _build_predictions(years=(2022, 2023, 2024), n_countries=200, n_recipes=3, seed=0)
        snaps = compute_per_year_snapshots(preds, min_countries_per_year=20)
        stability = matrix_stability_over_time(snaps)
        # Independent random predictions → matrices ~ same (all near 0 off-diag) → low distance
        assert stability["mean_distance"] < 1.0
        assert stability["n_year_pairs"] == 2

    def test_handles_single_snapshot(self):
        preds = _build_predictions(years=(2022,), n_countries=200, n_recipes=3, seed=0)
        snaps = compute_per_year_snapshots(preds, min_countries_per_year=20)
        stability = matrix_stability_over_time(snaps)
        assert stability["n_year_pairs"] == 0
        assert stability["skip_reason"] is not None


# -- find_persistent_high_corrs -------------------------------------------


class TestFindPersistentHighCorrs:
    def test_finds_coupled_recipe_pairs(self):
        preds = _build_predictions(years=(2022, 2023), n_countries=200, n_recipes=3, seed=0,
                                   coupling_strength=0.9)
        snaps = compute_per_year_snapshots(preds, min_countries_per_year=20)
        persistent = find_persistent_high_corrs(snaps, threshold=0.5)
        # All 3 recipes are highly coupled → C(3,2) = 3 pairs
        assert len(persistent) == 3
        for p in persistent:
            assert p["mean_abs_corr"] > 0.5

    def test_finds_no_pairs_when_independent(self):
        preds = _build_predictions(years=(2022, 2023), n_countries=200, n_recipes=3, seed=0)
        snaps = compute_per_year_snapshots(preds, min_countries_per_year=20)
        persistent = find_persistent_high_corrs(snaps, threshold=0.5)
        # Independent recipes → no persistent high-corr pairs
        assert len(persistent) == 0
