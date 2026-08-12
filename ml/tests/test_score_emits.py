"""Unit tests for score_countries.py emit helpers (frontend bake-request §A.1 / #974:
signed per-country SHAP magnitude). Pure numpy over a SHAP row — no XGBoost/SHAP fit.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import score_countries as sc  # noqa: E402


def test_signed_shap_sums_each_8_feature_block_with_sign():
    # 2 indicators x 8 features: block 0 all +1 (-> +8), block 1 all -2 (-> -16)
    row = np.array([1.0] * 8 + [-2.0] * 8)
    assert sc.signed_shap_per_indicator(row) == [8.0, -16.0]


def test_signed_shap_preserves_sign_where_share_discards_it():
    # signal_share takes |shap| (always >=0); signed keeps the direction.
    row = np.array([1.0] * 8 + [-2.0] * 8)
    share = sc.signal_share_per_indicator(row)   # [8/24, 16/24] * 100
    signed = sc.signed_shap_per_indicator(row)
    assert share[1] > 0                          # share is magnitude-only
    assert signed[1] < 0                          # signed shows "pushes away"
    # block 0: all positive, so share and sign agree in direction
    assert signed[0] > 0


def test_signed_shap_partial_cancellation_within_block():
    # one indicator, 8 features summing to a small signed net (+3 -1 ... )
    row = np.array([3.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert sc.signed_shap_per_indicator(row) == [2.0]


def test_signed_shap_same_block_grouping_as_signal_share():
    # both helpers must reshape identically (indicator-major, 8 per group)
    row = np.arange(24.0)  # 3 indicators
    assert len(sc.signed_shap_per_indicator(row)) == 3
    assert len(sc.signal_share_per_indicator(row)) == 3


# ---- trajectory_window (§A.2) -----------------------------------------------

def _panel(values, years, country="X"):
    return pd.DataFrame({"country": [country] * len(years), "year": years, "value": values})


def test_trajectory_window_uses_25y_baseline_not_within_window():
    # years 2016-2020, values 10..50. window=3 -> last 3 years (2018,2019,2020).
    panel = _panel([10.0, 20.0, 30.0, 40.0, 50.0], [2016, 2017, 2018, 2019, 2020])
    row = sc.country_movement_12y("X", {"ind1": panel}, ["ind1"], window=3)[0]
    assert row["trajectory_window_years"] == [2018, 2019, 2020]
    # z'd against the 25y baseline (all 5: mean 30, std sqrt(200)=14.1421), NOT the
    # 3y window mean (40). value 30 == baseline mean -> 0.0 proves baseline-z.
    assert row["trajectory_window"] == [0.0, 0.7071, 1.4142]


def test_trajectory_window_overlay_scale_matches_canonical_baseline_z():
    # The whole point: window z uses baseline mean/std, so the window's own first
    # point is NOT forced to a within-window anchor. (within-window z would give
    # value 30 -> (30-40)/8.165 = -1.2247, which we must NOT see.)
    panel = _panel([10.0, 20.0, 30.0, 40.0, 50.0], [2016, 2017, 2018, 2019, 2020])
    row = sc.country_movement_12y("X", {"ind1": panel}, ["ind1"], window=3)[0]
    assert row["trajectory_window"][0] == 0.0  # baseline-z, not within-window


def test_trajectory_12q_unchanged_regression():
    panel = _panel([10.0, 20.0, 30.0, 40.0, 50.0], [2016, 2017, 2018, 2019, 2020])
    row = sc.country_movement_12y("X", {"ind1": panel}, ["ind1"], window=3)[0]
    # within-window z over the available 5 points (mean 30, std 14.1421) — pre-existing
    assert [round(v, 4) for v in row["trajectory_12q"]] == [-1.4142, -0.7071, 0.0, 0.7071, 1.4142]
    assert round(row["z_score_change"], 4) == 2.8284


def test_trajectory_window_empty_country_has_new_keys():
    panel = _panel([1.0, 2.0], [2019, 2020], country="OTHER")
    row = sc.country_movement_12y("X", {"ind1": panel}, ["ind1"], window=3)[0]
    assert row["trajectory_window"] == [] and row["trajectory_window_years"] == []


def test_trajectory_window_short_history_returns_what_exists():
    # only 3 years of data, window=12 -> a 3-point window, not an error.
    panel = _panel([10.0, 20.0, 30.0], [2018, 2019, 2020])
    row = sc.country_movement_12y("X", {"ind1": panel}, ["ind1"], window=12)[0]
    assert row["trajectory_window_years"] == [2018, 2019, 2020]
    assert len(row["trajectory_window"]) == 3


def test_trajectory_window_drops_nan_baseline_values():
    # a NaN in the panel must not poison the baseline mean/std (parity with the
    # walk's .dropna()).
    panel = _panel([10.0, float("nan"), 30.0, 40.0, 50.0], [2016, 2017, 2018, 2019, 2020])
    row = sc.country_movement_12y("X", {"ind1": panel}, ["ind1"], window=3)[0]
    # baseline = [10,30,40,50] (NaN dropped), mean 32.5; window years still 2018-2020
    assert row["trajectory_window_years"] == [2018, 2019, 2020]
    assert all(v == v for v in row["trajectory_window"])  # no NaN propagated
