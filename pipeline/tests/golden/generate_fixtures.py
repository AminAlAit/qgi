"""
Generate deterministic golden-file test fixtures.

Run once to create fixtures + expected outputs:
    python tests/golden/generate_fixtures.py

Fixtures:
  - countries.csv — 5 countries with multi-name mapping
  - TEST.IND.001 / TEST.IND.002 — Parquet indicator files (a-worker output format)
  - scdis.parquet — pre-computed SCDIs for the 2 indicators across 3 countries

Expected:
  - patterns_country_1.parquet — Phase C pattern synthesis output for country_a_id=1
"""

import hashlib
import os
from pathlib import Path

import numpy as np
import pandas as pd

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_DIR = Path(__file__).parent / "expected"

np.random.seed(42)  # deterministic


def generate_countries_csv():
    """5-country mapping file matching the production countries.csv schema."""
    rows = [
        {"id": "1", "name_1": "Alphaland", "name_2": "Alpha Republic", "alpha_2": "AL", "alpha_3": "ALP"},
        {"id": "2", "name_1": "Betaland", "name_2": "Beta Kingdom", "alpha_2": "BT", "alpha_3": "BET"},
        {"id": "3", "name_1": "Gammastan", "name_2": "Gamma Union", "alpha_2": "GM", "alpha_3": "GAM"},
        {"id": "4", "name_1": "Deltaville", "name_2": "Delta State", "alpha_2": "DV", "alpha_3": "DEL"},
        {"id": "5", "name_1": "Epsilonia", "name_2": "Epsilon Isles", "alpha_2": "EP", "alpha_3": "EPS"},
    ]
    df = pd.DataFrame(rows)
    path = FIXTURES_DIR / "countries.csv"
    df.to_csv(path, index=False)
    print(f"  countries.csv: {len(df)} countries")
    return df


def generate_indicator_parquet(indicator_id: str, countries: list[str], years: range):
    """
    Generate a-worker output format: (country, year, value) Parquet.
    Uses deterministic random values seeded by indicator_id.
    """
    seed = int(hashlib.md5(indicator_id.encode()).hexdigest()[:8], 16) % (2**31)
    rng = np.random.RandomState(seed)

    rows = []
    for country in countries:
        for year in years:
            rows.append(
                {
                    "country": country,
                    "year": year,
                    "value": round(rng.uniform(10, 100), 4),
                }
            )
    df = pd.DataFrame(rows)
    path = FIXTURES_DIR / "indicators" / indicator_id / f"{indicator_id}.parquet"
    df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    print(f"  {indicator_id}.parquet: {len(df)} rows")
    return df


def generate_scdis(countries_df: pd.DataFrame):
    """
    Generate synthetic SCDI rows matching the Glue scdis table schema.
    Schema: country_a_id, country_b_id, length, start_year_a, start_year_b,
            correlation, indicator_numeric_id (partition: country_a_id)

    We create enough data so country_a_id=1 has patterns with >1 indicator
    (HAVING COUNT(*) > 1) for the pattern synthesis test.
    """
    rows = []
    # Country 1 vs Country 2: two indicators share the same (length=5, start_year_a=2015, start_year_b=2016)
    # This should produce a pattern in the golden output
    rows.append(
        {
            "country_a_id": 1,
            "country_b_id": 2,
            "length": 5,
            "start_year_a": 2015,
            "start_year_b": 2016,
            "correlation": 0.92,
            "indicator_numeric_id": 1,
        }
    )
    rows.append(
        {
            "country_a_id": 1,
            "country_b_id": 2,
            "length": 5,
            "start_year_a": 2015,
            "start_year_b": 2016,
            "correlation": 0.88,
            "indicator_numeric_id": 2,
        }
    )

    # Country 1 vs Country 3: two indicators share (length=3, start_year_a=2017, start_year_b=2017)
    rows.append(
        {
            "country_a_id": 1,
            "country_b_id": 3,
            "length": 3,
            "start_year_a": 2017,
            "start_year_b": 2017,
            "correlation": 0.85,
            "indicator_numeric_id": 1,
        }
    )
    rows.append(
        {
            "country_a_id": 1,
            "country_b_id": 3,
            "length": 3,
            "start_year_a": 2017,
            "start_year_b": 2017,
            "correlation": 0.79,
            "indicator_numeric_id": 2,
        }
    )

    # Country 1 vs Country 2: single indicator (should NOT produce a pattern — HAVING COUNT > 1)
    rows.append(
        {
            "country_a_id": 1,
            "country_b_id": 2,
            "length": 7,
            "start_year_a": 2010,
            "start_year_b": 2011,
            "correlation": 0.95,
            "indicator_numeric_id": 1,
        }
    )

    # Country 2 vs Country 1: two indicators (patterns for country_a_id=2)
    rows.append(
        {
            "country_a_id": 2,
            "country_b_id": 1,
            "length": 4,
            "start_year_a": 2018,
            "start_year_b": 2018,
            "correlation": 0.91,
            "indicator_numeric_id": 1,
        }
    )
    rows.append(
        {
            "country_a_id": 2,
            "country_b_id": 1,
            "length": 4,
            "start_year_a": 2018,
            "start_year_b": 2018,
            "correlation": 0.87,
            "indicator_numeric_id": 2,
        }
    )

    df = pd.DataFrame(rows)
    # Cast to match Glue schema types
    for col in ["country_a_id", "country_b_id", "length", "start_year_a", "start_year_b", "indicator_numeric_id"]:
        df[col] = df[col].astype("int16")
    df["correlation"] = df["correlation"].astype("float32")

    path = FIXTURES_DIR / "scdis.parquet"
    df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    print(f"  scdis.parquet: {len(df)} rows")
    return df


def generate_expected_patterns(scdis_df: pd.DataFrame, country_a_id: int):
    """
    Replicate the Phase C Athena INSERT query as pandas to produce the golden output.
    This is the reference implementation — test_phase_c_synthesis.py will do the same
    and compare to this output.
    """
    filtered = scdis_df[scdis_df["country_a_id"] == country_a_id].copy()

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

    # pattern_id = MD5 of concatenated key columns
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

    # Reorder columns to match c-worker output
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

    # Cast types
    result["avg_correlation"] = result["avg_correlation"].astype("float64")
    result["indicator_count"] = result["indicator_count"].astype("int64")
    result = result.sort_values(["country_b_id", "length", "start_year_a"]).reset_index(drop=True)

    path = EXPECTED_DIR / f"patterns_country_{country_a_id}.parquet"
    result.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    print(f"  patterns_country_{country_a_id}.parquet: {len(result)} patterns")
    return result


def main():
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating fixtures...")
    countries_df = generate_countries_csv()

    country_names = countries_df["name_1"].tolist()
    years = range(2010, 2024)
    generate_indicator_parquet("TEST.IND.001", country_names, years)
    generate_indicator_parquet("TEST.IND.002", country_names, years)

    print("\nGenerating SCDIs...")
    scdis_df = generate_scdis(countries_df)

    print("\nGenerating expected outputs...")
    generate_expected_patterns(scdis_df, country_a_id=1)

    print("\nDone! Fixtures and expected outputs are ready.")


if __name__ == "__main__":
    main()
