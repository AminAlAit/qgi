"""
Golden-file test for Phase A worker transform logic (#97).

Tests the ETLWorker's data transformation pipeline:
  raw World Bank DataFrame → melt → rename → country mapping → filter → sorted output

Compares the output against committed golden Parquet files.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from .conftest import EXPECTED_DIR, FIXTURES_DIR, load_lambda_module


class TestPhaseATransform:
    """Test the a-worker's core transform logic in isolation."""

    @pytest.fixture(autouse=True)
    def setup(self, countries_csv_path):
        """Load the a-worker module with boto3 stubbed."""
        self.countries_csv_path = countries_csv_path
        self.mod = load_lambda_module("pipeline-a-worker")
        self.worker = self.mod.ETLWorker()

    def _make_world_bank_df(self):
        """
        Create a synthetic DataFrame matching World Bank API output format.
        Columns: YR2010 .. YR2023, index = economy codes.
        Uses the country name_2 values as economy codes (what wbgapi returns).
        """
        countries_df = pd.read_csv(self.countries_csv_path)
        economies = countries_df["name_2"].tolist()
        years = list(range(2010, 2024))

        import numpy as np

        rng = np.random.RandomState(99)

        data = {}
        for yr in years:
            data[f"YR{yr}"] = [round(rng.uniform(10, 100), 4) for _ in economies]

        df = pd.DataFrame(data, index=economies)
        df.index.name = None  # wbgapi doesn't set index name
        return df

    def _run_transform(self, raw_df):
        """
        Replicate the a-worker transform steps (lines 108-118 of lambda_function.py).
        Injects the country mapping from fixtures.
        """
        # Mock S3 to return the fixture countries.csv
        csv_bytes = self.countries_csv_path.read_bytes()
        mock_body = MagicMock()
        mock_body.read.return_value = csv_bytes
        self.mod.s3_client.get_object = MagicMock(return_value={"Body": mock_body})

        # Force reload of country mapping
        self.worker.country_mapping = None
        mapping = self.worker._get_country_mapping()

        # Now apply the same transform the worker does
        df = raw_df.dropna(axis="columns", how="all").copy()
        df["economy"] = df.index
        df_long = pd.melt(df, id_vars=["economy"], var_name="year", value_name="value")
        df_long["year"] = df_long["year"].str.extract(r"(\d+)").astype(int)
        df_long = df_long.rename(columns={"economy": "country"})
        df_long["country"] = df_long["country"].map(mapping).fillna(df_long["country"])
        canonical_names = set(mapping.values())
        df_long = df_long[df_long["country"].isin(canonical_names)]
        final_df = df_long.dropna(subset=["value"]).sort_values(by=["country", "year"])
        return final_df.reset_index(drop=True)

    def test_transform_output_schema(self):
        """Output has exactly (country, year, value) columns."""
        raw = self._make_world_bank_df()
        result = self._run_transform(raw)
        assert list(result.columns) == ["country", "year", "value"]

    def test_transform_maps_country_names(self):
        """Economy codes (name_2) are mapped to canonical names (name_1)."""
        raw = self._make_world_bank_df()
        result = self._run_transform(raw)
        countries_df = pd.read_csv(self.countries_csv_path)
        canonical = set(countries_df["name_1"])
        assert set(result["country"].unique()) == canonical

    def test_transform_row_count(self):
        """5 countries × 14 years = 70 rows (no NaN values in synthetic data)."""
        raw = self._make_world_bank_df()
        result = self._run_transform(raw)
        assert len(result) == 5 * 14

    def test_transform_sorted_by_country_year(self):
        """Output is sorted by (country, year)."""
        raw = self._make_world_bank_df()
        result = self._run_transform(raw)
        sorted_df = result.sort_values(by=["country", "year"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(result, sorted_df)

    def test_transform_filters_unmapped_economies(self):
        """Economies not in countries.csv are dropped."""
        raw = self._make_world_bank_df()
        # Add an extra row for an unmapped economy
        raw.loc["Unknown Republic"] = [50.0] * 14
        result = self._run_transform(raw)
        assert "Unknown Republic" not in result["country"].values

    def test_transform_golden_file(self):
        """
        Full golden-file comparison: transform output matches committed expected file.
        Update with: python tests/golden/generate_fixtures.py
        """
        raw = self._make_world_bank_df()
        result = self._run_transform(raw)

        golden_path = EXPECTED_DIR / "phase_a_transform.parquet"
        if not golden_path.exists():
            # First run: create golden file
            result.to_parquet(golden_path, index=False, engine="pyarrow", compression="snappy")
            pytest.skip("Golden file created — re-run to validate")

        expected = pd.read_parquet(golden_path)
        pd.testing.assert_frame_equal(result, expected, check_dtype=False)
