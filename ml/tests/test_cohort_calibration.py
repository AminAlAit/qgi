"""Tests for `qgi_ml.src.cohort_calibration`."""
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

from cohort_calibration import (  # noqa: E402
    CalibrationTableRow,
    CohortCalibrationReport,
    assign_coverage_cohorts,
    calibration_table,
    compute_ece,
    stratified_calibration_per_recipe,
)


# -- assign_coverage_cohorts -------------------------------------------------


class TestAssignCoverageCohorts:
    def _build_panel(self):
        # 3 countries × 5 years; A is dense, B is mid, C is sparse
        rows = []
        for c, completion in [("A", 1.0), ("B", 0.5), ("C", 0.1)]:
            for year in range(2014, 2019):
                row = {"country": c, "year": year}
                for f in range(5):
                    # Set non-null probabilistically based on completion
                    row[f"f{f}"] = float(f) if (f / 5.0 < completion) else np.nan
                rows.append(row)
        return pd.DataFrame(rows)

    def test_returns_one_row_per_country(self):
        panel = self._build_panel()
        out = assign_coverage_cohorts(panel)
        assert set(out["country"]) == {"A", "B", "C"}

    def test_high_low_cohorts_correctly_assigned(self):
        panel = self._build_panel()
        out = assign_coverage_cohorts(panel)
        cohorts = dict(zip(out["country"], out["cohort"]))
        # A is densest, C is sparsest → A=high, C=low
        assert cohorts["A"] == "high"
        assert cohorts["C"] == "low"

    def test_missing_country_column_raises(self):
        panel = pd.DataFrame({"year": [2020], "f1": [1.0]})
        with pytest.raises(ValueError, match="missing 'country' column"):
            assign_coverage_cohorts(panel)

    def test_invalid_percentiles_raise(self):
        panel = self._build_panel()
        with pytest.raises(ValueError, match="percentiles must satisfy"):
            assign_coverage_cohorts(panel, low_pctile=80, high_pctile=20)


# -- compute_ece -------------------------------------------------------------


class TestComputeEce:
    def test_perfect_calibration(self):
        probs = np.full(100, 0.5)
        labels = np.array([0] * 50 + [1] * 50)
        assert compute_ece(probs, labels) == 0.0

    def test_empty_returns_nan(self):
        assert np.isnan(compute_ece(np.array([]), np.array([])))


# -- calibration_table ------------------------------------------------------


class TestCalibrationTable:
    def test_returns_n_bins_rows(self):
        rng = np.random.default_rng(0)
        probs = rng.random(500)
        labels = (rng.random(500) < probs).astype(int)
        table = calibration_table(probs, labels, n_bins=10)
        assert len(table) == 10
        for row in table:
            if row.n_observations > 0:
                assert 0 <= row.mean_predicted_prob <= 1
                assert 0 <= row.observed_event_rate <= 1
                assert row.observed_rate_ci_lower <= row.observed_event_rate <= row.observed_rate_ci_upper

    def test_empty_input_returns_empty_table(self):
        assert calibration_table(np.array([]), np.array([])) == []

    def test_table_buckets_increase(self):
        rng = np.random.default_rng(0)
        probs = rng.random(500)
        labels = (rng.random(500) < probs).astype(int)
        table = calibration_table(probs, labels, n_bins=10)
        # Bin edges are non-decreasing
        for i in range(len(table) - 1):
            assert table[i].bin_high <= table[i + 1].bin_low + 1e-9

    def test_well_calibrated_data_yields_close_obs_to_pred(self):
        # Construct: probs are exactly the event rate by design
        rng = np.random.default_rng(0)
        n = 5000
        probs = rng.uniform(0, 1, n)
        labels = (rng.uniform(0, 1, n) < probs).astype(int)
        table = calibration_table(probs, labels, n_bins=10, n_bootstrap=50)
        # Average diff should be small
        diffs = [abs(r.mean_predicted_prob - r.observed_event_rate)
                 for r in table if r.n_observations > 50]
        assert max(diffs) < 0.1


# -- stratified_calibration_per_recipe --------------------------------------


class TestStratifiedCalibrationPerRecipe:
    def test_groups_by_recipe_and_cohort(self):
        predictions = []
        for c in ["A", "B"]:
            for r in ["recipe_1", "recipe_2"]:
                for i in range(50):
                    predictions.append({
                        "country": c, "year": 2022, "recipe_id": r,
                        "predicted_probability": float(i % 10) / 10.0,
                        "label": int(i % 5 == 0),
                    })
        cohort_map = {"A": "high", "B": "low"}
        out = stratified_calibration_per_recipe(predictions, cohort_map,
                                                 n_bootstrap=20)
        assert set(out.keys()) == {"recipe_1", "recipe_2"}
        for rid in out:
            assert set(out[rid].keys()) == {"high", "low"}

    def test_handles_unknown_country(self):
        predictions = [{
            "country": "Unknown", "year": 2022, "recipe_id": "r1",
            "predicted_probability": 0.5, "label": 1,
        }]
        out = stratified_calibration_per_recipe(predictions, {}, n_bootstrap=10)
        assert "r1" in out
        assert "unknown" in out["r1"]

    def test_empty_predictions_returns_empty(self):
        out = stratified_calibration_per_recipe([], {}, n_bootstrap=10)
        assert out == {}
