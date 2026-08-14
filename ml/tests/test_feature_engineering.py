"""Unit tests for src/feature_engineering.py.

Stage 0 deliverable per docs/specs/internal/ops/ml-track/stage-0-pre-registration.md.

Synthesizes a tiny long-format panel and exercises every transform:
read_indicators, pivot_to_wide / pivot_to_long, first_difference,
rolling_zscore, momentum, cross_indicator_ratios, missingness_indicators,
multiple_imputation_mice.
"""
from __future__ import annotations

import math
import pathlib
import sys

import pandas as pd
import pytest

SRC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import feature_engineering as fe  # noqa: E402


# ---------- Schema validation ----------


def test_check_long_schema_rejects_missing_columns():
    df = pd.DataFrame({"country": ["x"], "year": [2020]})
    with pytest.raises(ValueError, match="missing required columns"):
        fe._check_long_schema(df)


def test_check_long_schema_accepts_canonical_columns():
    df = pd.DataFrame(columns=list(fe.REQUIRED_COLS))
    fe._check_long_schema(df)  # no exception


# ---------- read_indicators ----------


def _write_indicator_parquet(panel_dir: pathlib.Path, indicator_id: str, rows: list[dict]):
    sub = panel_dir / indicator_id
    sub.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_parquet(sub / f"{indicator_id}.parquet")


def test_read_indicators_reads_parquets_and_concatenates(tmp_path):
    _write_indicator_parquet(tmp_path, "WB-01", [
        {"country": "atlantis", "year": 2020, "indicator_id": "WB-01", "value": 1.0},
        {"country": "atlantis", "year": 2021, "indicator_id": "WB-01", "value": 2.0},
    ])
    _write_indicator_parquet(tmp_path, "VD-01", [
        {"country": "atlantis", "year": 2020, "indicator_id": "VD-01", "value": 0.5},
    ])
    df = fe.read_indicators(["WB-01", "VD-01"], tmp_path)
    assert len(df) == 3
    assert set(df["indicator_id"]) == {"WB-01", "VD-01"}


def test_read_indicators_silently_skips_missing(tmp_path):
    _write_indicator_parquet(tmp_path, "WB-01", [
        {"country": "x", "year": 2020, "indicator_id": "WB-01", "value": 1.0},
    ])
    df = fe.read_indicators(["WB-01", "NON-EXISTENT"], tmp_path)
    assert len(df) == 1
    assert df["indicator_id"].iloc[0] == "WB-01"


def test_read_indicators_backfills_indicator_id_from_path(tmp_path):
    """If a parquet file lacks indicator_id col, it's inferred from the dirname."""
    sub = tmp_path / "WB-99"
    sub.mkdir()
    df = pd.DataFrame([
        {"country": "x", "year": 2020, "value": 1.0},  # no indicator_id col
    ])
    df.to_parquet(sub / "WB-99.parquet")
    out = fe.read_indicators(["WB-99"], tmp_path)
    assert (out["indicator_id"] == "WB-99").all()


def test_read_indicators_returns_empty_when_no_matches(tmp_path):
    df = fe.read_indicators(["NOPE"], tmp_path)
    assert df.empty
    assert list(df.columns) == list(fe.REQUIRED_COLS)


def test_read_indicators_raises_on_missing_dir(tmp_path):
    with pytest.raises(NotADirectoryError):
        fe.read_indicators(["WB-01"], tmp_path / "no_such_dir")


# ---------- pivot helpers ----------


def _sample_long():
    return pd.DataFrame([
        {"country": "atlantis", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "atlantis", "year": 2020, "indicator_id": "B", "value": 2.0},
        {"country": "atlantis", "year": 2021, "indicator_id": "A", "value": 3.0},
        {"country": "atlantis", "year": 2021, "indicator_id": "B", "value": 4.0},
        {"country": "rapture", "year": 2020, "indicator_id": "A", "value": 5.0},
    ])


def test_pivot_to_wide_one_row_per_country_year():
    long = _sample_long()
    wide = fe.pivot_to_wide(long)
    assert len(wide) == 3  # (atlantis,2020), (atlantis,2021), (rapture,2020)
    assert set(wide.columns) >= {"country", "year", "A", "B"}


def test_pivot_round_trip_preserves_non_null_data():
    long = _sample_long()
    wide = fe.pivot_to_wide(long)
    long2 = fe.pivot_to_long(wide)
    # Sort both for comparison; pivot_to_long drops NaN values
    a = long.sort_values(["country", "year", "indicator_id"]).reset_index(drop=True)
    b = long2.sort_values(["country", "year", "indicator_id"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_pivot_to_wide_handles_empty_input():
    df = pd.DataFrame(columns=list(fe.REQUIRED_COLS))
    out = fe.pivot_to_wide(df)
    assert out.empty


# ---------- first_difference ----------


def test_first_difference_per_country_indicator():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 10.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 13.0},
        {"country": "x", "year": 2022, "indicator_id": "A", "value": 15.0},
    ])
    out = fe.first_difference(long, indicator_ids=["A"])
    diffed = out[out["indicator_id"] == "A__diff"].sort_values("year")
    assert pd.isna(diffed.iloc[0]["value"])  # first year NaN
    assert diffed.iloc[1]["value"] == 3.0
    assert diffed.iloc[2]["value"] == 2.0


def test_first_difference_resets_per_country():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 10.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 13.0},
        {"country": "y", "year": 2020, "indicator_id": "A", "value": 100.0},
        {"country": "y", "year": 2021, "indicator_id": "A", "value": 105.0},
    ])
    out = fe.first_difference(long, indicator_ids=["A"])
    diffed = out[out["indicator_id"] == "A__diff"]
    # Each country's 2020 row should be NaN (first observation)
    nan_2020 = diffed[diffed["year"] == 2020]["value"]
    assert nan_2020.isna().all()


def test_first_difference_passes_through_non_targeted_indicators():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 5.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 2.0},
        {"country": "x", "year": 2021, "indicator_id": "B", "value": 7.0},
    ])
    out = fe.first_difference(long, indicator_ids=["A"])
    # B passes through unchanged
    b_rows = out[out["indicator_id"] == "B"]
    assert len(b_rows) == 2
    assert set(b_rows["value"]) == {5.0, 7.0}


def test_first_difference_default_applies_to_all_indicators():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 2.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 5.0},
        {"country": "x", "year": 2021, "indicator_id": "B", "value": 8.0},
    ])
    out = fe.first_difference(long)
    assert "A__diff" in set(out["indicator_id"])
    assert "B__diff" in set(out["indicator_id"])


# ---------- rolling_zscore ----------


def test_rolling_zscore_normalizes_within_country():
    long = pd.DataFrame([
        {"country": "x", "year": 2018, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2019, "indicator_id": "A", "value": 2.0},
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 3.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 4.0},
    ])
    out = fe.rolling_zscore(long, window_years=3)
    z = out[out["indicator_id"] == "A__zscore"].sort_values("year")
    # 2018: NaN (need >=2 obs); 2019 onward: z computed
    assert pd.isna(z.iloc[0]["value"])
    assert pd.notna(z.iloc[1]["value"])  # 2019: 2 obs available
    assert pd.notna(z.iloc[3]["value"])


def test_rolling_zscore_zero_std_yields_nan_not_inf():
    """Constant series should produce NaN (not inf) due to inf replacement."""
    long = pd.DataFrame([
        {"country": "x", "year": 2018, "indicator_id": "A", "value": 5.0},
        {"country": "x", "year": 2019, "indicator_id": "A", "value": 5.0},
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 5.0},
    ])
    out = fe.rolling_zscore(long, window_years=3)
    z = out[out["indicator_id"] == "A__zscore"]
    # All NaN: no variance -> std=0 -> z is inf -> replaced with NaN
    assert z["value"].isna().all() or all(pd.isna(v) or v == 0 for v in z["value"])


def test_rolling_zscore_rejects_window_below_2():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
    ])
    with pytest.raises(ValueError):
        fe.rolling_zscore(long, window_years=1)


# ---------- momentum ----------


def test_momentum_emits_yoy_change_in_rolling_mean():
    long = pd.DataFrame([
        {"country": "x", "year": 2018, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2019, "indicator_id": "A", "value": 2.0},
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 3.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 4.0},
    ])
    out = fe.momentum(long, lookback_years=2)
    m = out[out["indicator_id"] == "A__momentum"].sort_values("year")
    # 2018: NaN (need >=2 obs); 2019 onward: rolling-mean YoY change
    # Rolling-mean(2): 2018=NaN, 2019=1.5, 2020=2.5, 2021=3.5
    # Diff: 2018=NaN, 2019=NaN, 2020=1.0, 2021=1.0
    assert pd.isna(m.iloc[0]["value"])
    # 2020 should be diff(2.5 - 1.5) = 1.0
    val_2020 = m[m["year"] == 2020]["value"].iloc[0]
    assert math.isclose(val_2020, 1.0, abs_tol=1e-9)


def test_momentum_rejects_lookback_below_2():
    long = pd.DataFrame([{"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0}])
    with pytest.raises(ValueError):
        fe.momentum(long, lookback_years=1)


def test_momentum_does_not_bleed_across_indicators():
    """REGRESSION TEST for the bug QA caught: prior implementation grouped
    only on 'country' for the diff() call, which leaked momentum across
    indicator boundaries within a country. The fix groups on
    (country, indicator_id) for both the rolling-mean and the diff."""
    long = pd.DataFrame([
        {"country": "x", "year": 2018, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2019, "indicator_id": "A", "value": 2.0},
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 3.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 4.0},
        # Indicator B at a totally different scale; if momentum bled across,
        # the diff at the A->B boundary row would be a meaningless cross-
        # indicator delta involving values like 100 - mean_A.
        {"country": "x", "year": 2018, "indicator_id": "B", "value": 100.0},
        {"country": "x", "year": 2019, "indicator_id": "B", "value": 110.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 120.0},
        {"country": "x", "year": 2021, "indicator_id": "B", "value": 130.0},
    ])
    out = fe.momentum(long, lookback_years=2)
    a_mom = out[out["indicator_id"] == "A__momentum"].sort_values("year").reset_index(drop=True)
    b_mom = out[out["indicator_id"] == "B__momentum"].sort_values("year").reset_index(drop=True)
    # A rolling-mean(2): 2018=NaN, 2019=1.5, 2020=2.5, 2021=3.5; diffs: NaN, NaN, 1.0, 1.0
    # B rolling-mean(2): 2018=NaN, 2019=105, 2020=115, 2021=125; diffs: NaN, NaN, 10.0, 10.0
    assert math.isclose(a_mom[a_mom["year"] == 2020]["value"].iloc[0], 1.0, abs_tol=1e-9)
    assert math.isclose(a_mom[a_mom["year"] == 2021]["value"].iloc[0], 1.0, abs_tol=1e-9)
    assert math.isclose(b_mom[b_mom["year"] == 2020]["value"].iloc[0], 10.0, abs_tol=1e-9)
    assert math.isclose(b_mom[b_mom["year"] == 2021]["value"].iloc[0], 10.0, abs_tol=1e-9)


def test_rolling_zscore_independent_per_country():
    """Per-country independence: country a's z-score should NOT use country b's values."""
    long = pd.DataFrame([
        {"country": "a", "year": 2018, "indicator_id": "X", "value": 1.0},
        {"country": "a", "year": 2019, "indicator_id": "X", "value": 2.0},
        {"country": "a", "year": 2020, "indicator_id": "X", "value": 3.0},
        {"country": "b", "year": 2018, "indicator_id": "X", "value": 1000.0},
        {"country": "b", "year": 2019, "indicator_id": "X", "value": 1001.0},
        {"country": "b", "year": 2020, "indicator_id": "X", "value": 1002.0},
    ])
    out = fe.rolling_zscore(long, window_years=3)
    z = out[out["indicator_id"] == "X__zscore"]
    a_z_2020 = z[(z["country"] == "a") & (z["year"] == 2020)]["value"].iloc[0]
    b_z_2020 = z[(z["country"] == "b") & (z["year"] == 2020)]["value"].iloc[0]
    # If country bled, b's 2020 z would be huge (1002 vs combined-mean ~500).
    # With per-country windows, both z's are bounded by a single-series ramp.
    assert abs(a_z_2020) < 5.0
    assert abs(b_z_2020) < 5.0


def test_first_difference_single_observation_yields_nan():
    """Edge case: a country with only one observation must produce NaN value."""
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 5.0},
    ])
    out = fe.first_difference(long, indicator_ids=["A"])
    diffed = out[out["indicator_id"] == "A__diff"]
    assert len(diffed) == 1
    assert pd.isna(diffed.iloc[0]["value"])


def test_missingness_indicator_coverage_excludes_structural_absence():
    """In `indicator_coverage` mode, an indicator covering only 2018 should
    NOT be flagged missing for 2019/2020 (those are structural non-collection,
    not MNAR-within-coverage)."""
    long = pd.DataFrame([
        {"country": "x", "year": 2018, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2018, "indicator_id": "B", "value": 5.0},
        {"country": "x", "year": 2019, "indicator_id": "B", "value": 6.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 7.0},
    ])
    grid_out = fe.missingness_indicators(long, indicator_ids=["A"], universe="panel_grid")
    cov_out = fe.missingness_indicators(long, indicator_ids=["A"], universe="indicator_coverage")
    # panel_grid: 3 cells (2018-2020); 2018 observed (=0), 2019/2020 missing (=1)
    grid_a = grid_out[grid_out["indicator_id"] == "A__missing"]
    assert len(grid_a) == 3
    assert grid_a["value"].sum() == 2.0
    # indicator_coverage: A's window = [2018, 2018]; only 2018 is in scope
    cov_a = cov_out[cov_out["indicator_id"] == "A__missing"]
    assert len(cov_a) == 1
    assert cov_a.iloc[0]["value"] == 0.0


def test_missingness_indicators_rejects_invalid_universe():
    long = pd.DataFrame([{"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0}])
    with pytest.raises(ValueError, match="universe must be"):
        fe.missingness_indicators(long, universe="bogus_mode")


def test_pivot_to_wide_warns_on_duplicate_rows():
    """Data-quality issues should surface to callers via a warning, not silent absorption."""
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 99.0},  # duplicate
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 5.0},
    ])
    with pytest.warns(UserWarning, match="duplicate"):
        fe.pivot_to_wide(long)


# ---------- cross_indicator_ratios ----------


def test_cross_indicator_ratios_emits_derived_ratios():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "DEBT", "value": 100.0},
        {"country": "x", "year": 2020, "indicator_id": "GDP", "value": 50.0},
    ])
    out = fe.cross_indicator_ratios(long, indicator_pairs=[("DEBT", "GDP")])
    ratio_rows = out[out["indicator_id"] == "DEBT__div__GDP"]
    assert len(ratio_rows) == 1
    assert ratio_rows.iloc[0]["value"] == 2.0


def test_cross_indicator_ratios_zero_denominator_yields_nan():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 5.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 0.0},
    ])
    out = fe.cross_indicator_ratios(long, indicator_pairs=[("A", "B")])
    ratio = out[out["indicator_id"] == "A__div__B"]
    assert ratio["value"].isna().all()


def test_cross_indicator_ratios_missing_pair_silently_skipped():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
    ])
    out = fe.cross_indicator_ratios(long, indicator_pairs=[("A", "MISSING_B")])
    # No A__div__MISSING_B row should appear
    assert "A__div__MISSING_B" not in set(out["indicator_id"])


def test_cross_indicator_ratios_empty_pairs_returns_input_copy():
    long = _sample_long()
    out = fe.cross_indicator_ratios(long, indicator_pairs=[])
    pd.testing.assert_frame_equal(
        long.sort_values(["country", "year", "indicator_id"]).reset_index(drop=True),
        out.sort_values(["country", "year", "indicator_id"]).reset_index(drop=True),
    )


# ---------- missingness_indicators ----------


def test_missingness_indicators_flags_absent_country_year_cells():
    """Country x has indicator A in 2020 but NOT 2021. The 2021 cell is missing."""
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2021, "indicator_id": "B", "value": 2.0},  # other ind
    ])
    out = fe.missingness_indicators(long, indicator_ids=["A"])
    miss = out[out["indicator_id"] == "A__missing"]
    # Country x has 2 distinct (country, year) pairs in panel: 2020 + 2021
    assert len(miss) == 2
    # 2020: A present -> missing=0
    # 2021: A absent (only B present) -> missing=1
    miss_by_year = dict(zip(miss["year"], miss["value"]))
    assert miss_by_year[2020] == 0.0
    assert miss_by_year[2021] == 1.0


def test_missingness_indicators_default_covers_all_indicators():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 2.0},
    ])
    out = fe.missingness_indicators(long)
    assert "A__missing" in set(out["indicator_id"])
    assert "B__missing" in set(out["indicator_id"])


# ---------- multiple_imputation_mice ----------


def test_mice_imputes_missing_values():
    """Smoke test: MICE reduces NaN count on a simple wide panel."""
    try:
        import sklearn  # noqa: F401
    except ImportError:
        pytest.skip("sklearn not installed")
    import numpy as np
    wide = pd.DataFrame({
        "country": ["x", "x", "x", "y", "y", "y"],
        "year": [2018, 2019, 2020, 2018, 2019, 2020],
        "A": [1.0, 2.0, 3.0, 10.0, 20.0, 30.0],
        "B": [2.0, 4.0, np.nan, 20.0, np.nan, 60.0],  # 2 NaN
    })
    out = fe.multiple_imputation_mice(wide, n_iter=5, random_state=0)
    # Shape preserved
    assert out.shape == wide.shape
    # No NaN remain in indicator columns
    assert not out["B"].isna().any()
    # country + year preserved
    assert list(out["country"]) == list(wide["country"])
    assert list(out["year"]) == list(wide["year"])


def test_mice_handles_empty_input():
    out = fe.multiple_imputation_mice(pd.DataFrame(), n_iter=5)
    assert out.empty


def test_mice_raises_without_country_year():
    try:
        import sklearn  # noqa: F401
    except ImportError:
        pytest.skip("sklearn not installed")
    bad = pd.DataFrame({"A": [1.0, 2.0]})
    with pytest.raises(ValueError, match="country.*year"):
        fe.multiple_imputation_mice(bad)


# ---------- Phase D D5 trajectory features ----------
# Per docs/specs/internal/ops/ml-track/stage-2-d5-walk-methodology-prereg.md


# multi_year_difference --------------------------------------------------------


def test_multi_year_difference_3y_correct_values():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 10.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 12.0},
        {"country": "x", "year": 2022, "indicator_id": "A", "value": 15.0},
        {"country": "x", "year": 2023, "indicator_id": "A", "value": 17.0},
        {"country": "x", "year": 2024, "indicator_id": "A", "value": 22.0},
    ])
    out = fe.multi_year_difference(long, lookback_years=3, indicator_ids=["A"])
    diffed = out[out["indicator_id"] == "A__diff3y"].sort_values("year").reset_index(drop=True)
    # First 3 rows NaN, then v(t) - v(t-3)
    assert pd.isna(diffed.iloc[0]["value"])
    assert pd.isna(diffed.iloc[1]["value"])
    assert pd.isna(diffed.iloc[2]["value"])
    assert diffed.iloc[3]["value"] == 17.0 - 10.0  # 2023 - 2020
    assert diffed.iloc[4]["value"] == 22.0 - 12.0  # 2024 - 2021


def test_multi_year_difference_5y_first_5_years_nan():
    rows = [{"country": "x", "year": 2020 + i, "indicator_id": "A", "value": float(i)}
            for i in range(8)]
    long = pd.DataFrame(rows)
    out = fe.multi_year_difference(long, lookback_years=5, indicator_ids=["A"])
    diffed = out[out["indicator_id"] == "A__diff5y"].sort_values("year").reset_index(drop=True)
    # First 5 rows NaN
    for i in range(5):
        assert pd.isna(diffed.iloc[i]["value"])
    # Year 2025: v(2025) - v(2020) = 5 - 0 = 5
    assert diffed.iloc[5]["value"] == 5.0


def test_multi_year_difference_strict_consecutive_non_null():
    """Per D5 imputation policy: NaN at one of the lookback positions
    propagates to the diff; NOT interpolated. Two checks:
    (1) NaN at v(t-N) → result NaN at year t
    (2) NaN at v(t) → result NaN at year t (trivially)
    Critically, the test must place the NaN at a position the diff actually
    READS (t or t-N), not at an irrelevant interior year."""
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": float("nan")},  # v(t-3) for 2023 lookup
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 12.0},
        {"country": "x", "year": 2022, "indicator_id": "A", "value": 15.0},
        {"country": "x", "year": 2023, "indicator_id": "A", "value": 17.0},  # v(t)
        {"country": "x", "year": 2024, "indicator_id": "A", "value": float("nan")},  # v(t)
        {"country": "x", "year": 2025, "indicator_id": "A", "value": 25.0},  # diff = v(2025)-v(2022) = 25-15 = 10
    ])
    out = fe.multi_year_difference(long, lookback_years=3, indicator_ids=["A"])
    diffed = out[out["indicator_id"] == "A__diff3y"].sort_values("year").reset_index(drop=True)
    # 2023: needs v(2023)=17, v(2020)=NaN → result NaN (strict consecutive-non-null)
    assert pd.isna(diffed.iloc[3]["value"]), \
        "NaN at v(t-N) must propagate to diff result; got non-null"
    # 2024: needs v(2024)=NaN, v(2021)=12 → result NaN (NaN at v(t))
    assert pd.isna(diffed.iloc[4]["value"]), \
        "NaN at v(t) must propagate to diff result; got non-null"
    # 2025: needs v(2025)=25, v(2022)=15 → both non-null → result 10
    assert diffed.iloc[5]["value"] == 10.0


def test_multi_year_difference_preserves_per_country_isolation():
    """Per-country per-indicator isolation: country x's 2023 diff should NOT
    look back into country y's data even when concatenated. Uses dense
    annual panel matching the convention of first_difference."""
    rows = []
    for c, base, slope in [("x", 10.0, 1.0), ("y", 100.0, 1.5)]:
        for i, y in enumerate(range(2020, 2024)):
            rows.append({"country": c, "year": y, "indicator_id": "A",
                         "value": base + i * slope})
    long = pd.DataFrame(rows)
    out = fe.multi_year_difference(long, lookback_years=3, indicator_ids=["A"])
    diffed = out[out["indicator_id"] == "A__diff3y"]
    by_country_2023 = diffed[diffed["year"] == 2023].set_index("country")["value"]
    # x: v(2023)=13, v(2020)=10 → 3.0
    # y: v(2023)=104.5, v(2020)=100 → 4.5
    assert by_country_2023.loc["x"] == 3.0
    assert by_country_2023.loc["y"] == 4.5


def test_multi_year_difference_rejects_lookback_below_1():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
    ])
    with pytest.raises(ValueError, match="lookback_years must be >= 1"):
        fe.multi_year_difference(long, lookback_years=0)


def test_multi_year_difference_passes_through_non_targeted():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 5.0},
    ])
    out = fe.multi_year_difference(long, lookback_years=3, indicator_ids=["A"])
    b_rows = out[out["indicator_id"] == "B"]
    assert len(b_rows) == 1
    assert b_rows.iloc[0]["value"] == 5.0


def test_multi_year_difference_handles_empty():
    out = fe.multi_year_difference(pd.DataFrame(columns=["country", "year", "indicator_id", "value"]),
                                    lookback_years=3)
    assert out.empty


def test_multi_year_difference_default_applies_to_all_indicators():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2023, "indicator_id": "A", "value": 4.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 5.0},
        {"country": "x", "year": 2023, "indicator_id": "B", "value": 11.0},
    ])
    out = fe.multi_year_difference(long, lookback_years=3)
    out_ids = set(out["indicator_id"])
    assert "A__diff3y" in out_ids
    assert "B__diff3y" in out_ids


# acceleration -----------------------------------------------------------------


def test_acceleration_correct_second_difference():
    """accel(t) = v(t) - 2*v(t-1) + v(t-2)."""
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 10.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 13.0},
        {"country": "x", "year": 2022, "indicator_id": "A", "value": 17.0},
        {"country": "x", "year": 2023, "indicator_id": "A", "value": 20.0},
    ])
    out = fe.acceleration(long, indicator_ids=["A"])
    accel = out[out["indicator_id"] == "A__accel"].sort_values("year").reset_index(drop=True)
    # First 2 rows NaN
    assert pd.isna(accel.iloc[0]["value"])
    assert pd.isna(accel.iloc[1]["value"])
    # 2022: 17 - 2*13 + 10 = 17 - 26 + 10 = 1 (decel: growth slowed from +3 to +4)
    # Actually: (17-13) - (13-10) = 4 - 3 = 1
    assert accel.iloc[2]["value"] == 1.0
    # 2023: (20-17) - (17-13) = 3 - 4 = -1
    assert accel.iloc[3]["value"] == -1.0


def test_acceleration_constant_series_yields_zero():
    """A perfectly linear series has zero acceleration."""
    long = pd.DataFrame([
        {"country": "x", "year": 2020 + i, "indicator_id": "A", "value": 10.0 + i * 5}
        for i in range(5)
    ])
    out = fe.acceleration(long, indicator_ids=["A"])
    accel = out[out["indicator_id"] == "A__accel"].sort_values("year")
    # Years 2022-2024 should all be 0 (linear growth)
    non_nan = accel.dropna(subset=["value"])
    assert all(non_nan["value"] == 0.0)


def test_acceleration_strict_consecutive_non_null_propagates_nan():
    """If any of v(t), v(t-1), v(t-2) is NaN, accel is NaN."""
    import numpy as np
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 10.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": np.nan},
        {"country": "x", "year": 2022, "indicator_id": "A", "value": 17.0},
        {"country": "x", "year": 2023, "indicator_id": "A", "value": 20.0},
        {"country": "x", "year": 2024, "indicator_id": "A", "value": 25.0},
    ])
    out = fe.acceleration(long, indicator_ids=["A"])
    accel = out[out["indicator_id"] == "A__accel"].sort_values("year").reset_index(drop=True)
    # 2022: needs v(2022), v(2021)=NaN, v(2020) → NaN
    assert pd.isna(accel.iloc[2]["value"])
    # 2023: needs v(2023), v(2022), v(2021)=NaN → NaN
    assert pd.isna(accel.iloc[3]["value"])
    # 2024: needs v(2024), v(2023), v(2022) — all non-null
    # accel = (25-20) - (20-17) = 5 - 3 = 2
    assert accel.iloc[4]["value"] == 2.0


def test_acceleration_per_country_isolation():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 10.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 12.0},
        {"country": "x", "year": 2022, "indicator_id": "A", "value": 16.0},
        {"country": "y", "year": 2020, "indicator_id": "A", "value": 100.0},
        {"country": "y", "year": 2021, "indicator_id": "A", "value": 110.0},
        {"country": "y", "year": 2022, "indicator_id": "A", "value": 130.0},
    ])
    out = fe.acceleration(long, indicator_ids=["A"])
    accel = out[out["indicator_id"] == "A__accel"]
    accel_2022 = accel[accel["year"] == 2022].set_index("country")["value"]
    # x: (16-12) - (12-10) = 4 - 2 = 2
    assert accel_2022.loc["x"] == 2.0
    # y: (130-110) - (110-100) = 20 - 10 = 10
    assert accel_2022.loc["y"] == 10.0


def test_acceleration_handles_empty():
    out = fe.acceleration(pd.DataFrame(columns=["country", "year", "indicator_id", "value"]))
    assert out.empty


def test_acceleration_passes_through_non_targeted():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 5.0},
    ])
    out = fe.acceleration(long, indicator_ids=["A"])
    b_rows = out[out["indicator_id"] == "B"]
    assert len(b_rows) == 1
    assert b_rows.iloc[0]["value"] == 5.0


def test_acceleration_default_applies_to_all_indicators():
    long = pd.DataFrame([
        {"country": "x", "year": 2020, "indicator_id": "A", "value": 1.0},
        {"country": "x", "year": 2021, "indicator_id": "A", "value": 2.0},
        {"country": "x", "year": 2022, "indicator_id": "A", "value": 3.0},
        {"country": "x", "year": 2020, "indicator_id": "B", "value": 5.0},
        {"country": "x", "year": 2021, "indicator_id": "B", "value": 8.0},
        {"country": "x", "year": 2022, "indicator_id": "B", "value": 14.0},
    ])
    out = fe.acceleration(long)
    out_ids = set(out["indicator_id"])
    assert "A__accel" in out_ids
    assert "B__accel" in out_ids


def test_suffix_multi_year_diff_helper():
    assert fe._suffix_multi_year_diff(3) == "__diff3y"
    assert fe._suffix_multi_year_diff(5) == "__diff5y"
    assert fe._suffix_multi_year_diff(10) == "__diff10y"
