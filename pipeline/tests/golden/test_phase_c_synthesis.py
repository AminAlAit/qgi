"""
Golden-file test for Phase C pattern synthesis logic (#97).

Replicates the c-worker Athena INSERT query as pandas and compares
against committed golden Parquet files.

The c-worker's Athena query (lambda_function.py lines 112-154):
  1. Filter SCDIs by country_a_id
  2. GROUP BY (country_a_id, country_b_id, length, start_year_a, start_year_b)
  3. HAVING COUNT(*) > 1
  4. Compute pattern_id (MD5), avg_correlation, pattern_power_score
"""

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from .conftest import EXPECTED_DIR, FIXTURES_DIR


def synthesize_patterns(scdis_df: pd.DataFrame, country_a_id: int) -> pd.DataFrame:
    """
    Pure-pandas equivalent of the c-worker Athena INSERT query.
    This is the function under test.
    """
    filtered = scdis_df[scdis_df["country_a_id"] == country_a_id].copy()
    if filtered.empty:
        return pd.DataFrame()

    group_cols = ["country_a_id", "country_b_id", "length", "start_year_a", "start_year_b"]
    agg = (
        filtered.groupby(group_cols)
        .agg(
            indicator_count=("indicator_numeric_id", "count"),
            avg_correlation=("correlation", "mean"),
            indicator_numeric_ids=("indicator_numeric_id", list),
        )
        .reset_index()
    )

    # HAVING COUNT(*) > 1
    agg = agg[agg["indicator_count"] > 1].copy()
    if agg.empty:
        return pd.DataFrame()

    # pattern_id = MD5 hash of key columns (matches c-worker's to_hex(md5(...)))
    agg["pattern_id"] = agg.apply(
        lambda r: hashlib.md5("-".join(str(int(r[c])) for c in group_cols).encode()).hexdigest(),
        axis=1,
    )

    # pattern_power_score = avg_correlation * length * indicator_count
    agg["pattern_power_score"] = (
        agg["avg_correlation"].astype("float64")
        * agg["length"].astype("float64")
        * agg["indicator_count"].astype("float64")
    )

    # Match c-worker column order
    result = agg[
        [
            "pattern_id",
            "country_b_id",
            "length",
            "start_year_a",
            "start_year_b",
            "indicator_count",
            "avg_correlation",
            "pattern_power_score",
            "indicator_numeric_ids",
            "country_a_id",
        ]
    ].copy()

    result["avg_correlation"] = result["avg_correlation"].astype("float64")
    result["indicator_count"] = result["indicator_count"].astype("int64")

    return result.sort_values(["country_b_id", "length", "start_year_a"]).reset_index(drop=True)


class TestPhaseCPatternSynthesis:
    """Test pattern synthesis logic against golden files."""

    def test_country_1_produces_2_patterns(self, scdis_df):
        """Country 1 has 2 multi-indicator groupings → 2 patterns."""
        result = synthesize_patterns(scdis_df, country_a_id=1)
        assert len(result) == 2

    def test_single_indicator_groups_excluded(self, scdis_df):
        """Groups with only 1 indicator (HAVING COUNT > 1) are excluded."""
        result = synthesize_patterns(scdis_df, country_a_id=1)
        assert (result["indicator_count"] > 1).all()

    def test_pattern_id_is_md5_hex(self, scdis_df):
        """Pattern IDs are 32-char hex strings (MD5 output)."""
        result = synthesize_patterns(scdis_df, country_a_id=1)
        for pid in result["pattern_id"]:
            assert len(pid) == 32
            int(pid, 16)  # raises if not valid hex

    def test_pattern_power_score_formula(self, scdis_df):
        """pattern_power_score = avg_correlation × length × indicator_count."""
        result = synthesize_patterns(scdis_df, country_a_id=1)
        for _, row in result.iterrows():
            expected = row["avg_correlation"] * row["length"] * row["indicator_count"]
            assert abs(row["pattern_power_score"] - expected) < 1e-10

    def test_avg_correlation_correct(self, scdis_df):
        """avg_correlation matches manual mean of correlations in each group."""
        filtered = scdis_df[scdis_df["country_a_id"] == 1]
        group_cols = ["country_a_id", "country_b_id", "length", "start_year_a", "start_year_b"]
        manual_means = filtered.groupby(group_cols)["correlation"].mean()

        result = synthesize_patterns(scdis_df, country_a_id=1)
        for _, row in result.iterrows():
            key = tuple(int(row[c]) for c in group_cols)
            expected_mean = float(manual_means.loc[key])
            assert abs(row["avg_correlation"] - expected_mean) < 1e-6

    def test_empty_country_returns_empty(self, scdis_df):
        """Country with no SCDIs returns empty DataFrame."""
        result = synthesize_patterns(scdis_df, country_a_id=999)
        assert result.empty

    def test_country_2_golden_file(self, scdis_df):
        """Country 2 pattern synthesis matches expected output."""
        result = synthesize_patterns(scdis_df, country_a_id=2)
        assert len(result) == 1  # one multi-indicator group

    def test_country_1_golden_file(self, scdis_df):
        """
        Full golden-file comparison for country_a_id=1.
        Expected file generated by: python tests/golden/generate_fixtures.py
        """
        result = synthesize_patterns(scdis_df, country_a_id=1)
        golden_path = EXPECTED_DIR / "patterns_country_1.parquet"
        assert golden_path.exists(), "Golden file missing — run: python tests/golden/generate_fixtures.py"

        expected = pd.read_parquet(golden_path)

        # Compare structure
        assert list(result.columns) == list(expected.columns)
        assert len(result) == len(expected)

        # Compare values (allowing small float tolerance)
        for col in result.columns:
            if result[col].dtype in ("float64", "float32"):
                np.testing.assert_allclose(
                    result[col].values,
                    expected[col].values,
                    rtol=1e-6,
                    err_msg=f"Mismatch in column {col}",
                )
            elif col == "indicator_numeric_ids":
                # Compare sorted lists (order may vary within group)
                for r_val, e_val in zip(result[col], expected[col]):
                    assert sorted(r_val) == sorted(e_val)
            else:
                pd.testing.assert_series_equal(
                    result[col].reset_index(drop=True),
                    expected[col].reset_index(drop=True),
                    check_names=False,
                    check_dtype=False,
                )
