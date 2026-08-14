"""Tests for `qgi_ml.src.structural_break`."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_break import (  # noqa: E402
    DEFAULT_LOW_POWER_THRESHOLD,
    DEFAULT_MIN_N_OBSERVATIONS,
    audit_pair,
    compute_panel_snapshot_id,
    cusum_test,
)


# -- cusum_test ---------------------------------------------------------------


class TestCusumTest:
    def test_stable_long_series_does_not_flag(self) -> None:
        rng = np.random.default_rng(42)
        years = np.arange(2000, 2022)
        values = 100 + 2 * (years - 2000) + rng.normal(0, 1, len(years))

        result = cusum_test(values)

        assert result["test_used"] == "cusum_olsresid_linear_trend"
        assert result["n_observations"] == 22
        assert result["p_value"] is not None
        assert result["p_value"] > 0.10
        assert result["soft_flag_p_lt_010"] is False
        assert result["high_conf_break_p_lt_001"] is False
        assert result["low_power_warning"] is False
        assert result["skip_reason"] is None

    def test_strong_break_in_long_series_flags(self) -> None:
        # OLS-CUSUM (with `value ~ year` trend regression) is poorly
        # powered against a midpoint level shift — the trend absorbs the
        # shift. A late-series spike is the canonical detectable
        # break: the linear trend cannot fit a sudden last-few-obs jump,
        # so residuals accumulate at the end and CUSUM fires.
        rng = np.random.default_rng(7)
        first = rng.normal(0, 0.5, 25)
        second = 100 + rng.normal(0, 0.5, 5)
        values = np.concatenate([first, second])

        result = cusum_test(values)

        assert result["test_used"] == "cusum_olsresid_linear_trend"
        assert result["n_observations"] == 30
        assert result["low_power_warning"] is False
        # The hard contract: the test must DETECT the break, not merely
        # run without crashing. With seed=7 + this late-spike fixture,
        # p reliably lands below 0.10 (typical run: ~0.022).
        assert result["p_value"] is not None
        assert result["p_value"] < 0.10, (
            f"Late-series spike should flag at p<0.10, got p={result['p_value']:.4f}"
        )
        assert result["soft_flag_p_lt_010"] is True
        # The sup_b should be noticeably larger than the stable case
        # (which gave sup_b ~ 0.5 in test_stable_long_series_does_not_flag).
        assert result["test_statistic_sup_b"] > 1.0

    def test_too_few_observations_skips(self) -> None:
        result = cusum_test([1.0, 2.0, 3.0])
        assert result["test_used"] is None
        assert result["skip_reason"] is not None
        assert "insufficient_observations" in result["skip_reason"]
        assert result["n_observations"] == 3

    def test_nans_dropped_before_count(self) -> None:
        result = cusum_test([np.nan, np.nan, 1.0, 2.0])
        # After dropping 2 NaNs, only 2 observations remain — below min 6.
        assert result["n_observations"] == 2
        assert result["test_used"] is None
        assert "insufficient_observations" in result["skip_reason"]

    def test_constant_series_skipped(self) -> None:
        result = cusum_test([5.0] * 20)
        assert result["test_used"] is None
        assert result["skip_reason"] == "constant_series"
        assert result["n_observations"] == 20

    def test_low_power_warning_at_n_below_threshold(self) -> None:
        rng = np.random.default_rng(0)
        # n=8: above min_n=6 but below low_power_threshold=15.
        values = 100 + rng.normal(0, 1, 8)
        result = cusum_test(values)
        assert result["test_used"] == "cusum_olsresid_linear_trend"
        assert result["n_observations"] == 8
        assert result["low_power_warning"] is True

    def test_low_power_warning_off_at_n_at_threshold(self) -> None:
        rng = np.random.default_rng(0)
        values = 100 + rng.normal(0, 1, DEFAULT_LOW_POWER_THRESHOLD)
        result = cusum_test(values)
        assert result["low_power_warning"] is False

    def test_min_n_default_matches_consult_decision(self) -> None:
        # Ji-Hoon + Kwame agreed on min_n=6 (skip below).
        assert DEFAULT_MIN_N_OBSERVATIONS == 6

    def test_low_power_default_matches_consult_decision(self) -> None:
        # Ji-Hoon's reliability floor for CUSUM = 15.
        assert DEFAULT_LOW_POWER_THRESHOLD == 15

    def test_p_value_thresholds_split_correctly(self) -> None:
        # `high_conf_break_p_lt_001` field shorthand: "p < 0.01"
        # (matches `soft_flag_p_lt_010` shorthand for "p < 0.10").
        # Verify the two flags are derived from p-value with the correct
        # thresholds, regardless of which range the p-value lands in.
        rng = np.random.default_rng(123)
        values = np.concatenate([
            rng.normal(0, 0.1, 25),
            rng.normal(2, 0.1, 25),
        ])
        result = cusum_test(values)
        assert result["p_value"] is not None
        assert result["soft_flag_p_lt_010"] == (result["p_value"] < 0.10)
        assert result["high_conf_break_p_lt_001"] == (result["p_value"] < 0.01)
        # Sanity: monotonicity — if high_conf is True, soft must be True.
        if result["high_conf_break_p_lt_001"]:
            assert result["soft_flag_p_lt_010"] is True


# -- audit_pair ---------------------------------------------------------------


class TestAuditPair:
    def test_narrow_window_filters_correctly(self) -> None:
        rng = np.random.default_rng(1)
        years = np.arange(2000, 2025)
        values = 100 + rng.normal(0, 1, len(years))

        result = audit_pair(
            years,
            values,
            window_start=2014,
            window_end=2021,
        )

        assert result["window_start_actual"] == 2014
        assert result["window_end_actual"] == 2021
        assert result["n_observations"] == 8
        # n=8 < low_power_threshold=15.
        assert result["low_power_warning"] is True

    def test_extended_window_uses_max_history(self) -> None:
        rng = np.random.default_rng(2)
        years = np.arange(1990, 2025)
        values = 100 + rng.normal(0, 1, len(years))

        result = audit_pair(
            years,
            values,
            window_start=None,
            window_end=2021,
        )

        assert result["window_start_actual"] == 1990
        assert result["window_end_actual"] == 2021
        assert result["n_observations"] == 32
        assert result["low_power_warning"] is False

    def test_unsorted_years_get_sorted(self) -> None:
        years = [2020, 2018, 2014, 2016, 2015, 2017, 2019, 2021]
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        result = audit_pair(
            years,
            values,
            window_start=2014,
            window_end=2021,
        )
        assert result["window_start_actual"] == 2014
        assert result["window_end_actual"] == 2021
        assert result["n_observations"] == 8

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="length mismatch"):
            audit_pair([2014, 2015], [1.0, 2.0, 3.0], window_start=2014, window_end=2021)

    def test_no_observations_in_window_returns_skip(self) -> None:
        years = np.arange(1990, 2010)
        values = np.arange(20, dtype=float)
        result = audit_pair(years, values, window_start=2014, window_end=2021)
        assert result["test_used"] is None
        assert result["skip_reason"] is not None
        assert result["n_observations"] == 0
        assert result["window_start_actual"] is None
        assert result["window_end_actual"] is None


# -- compute_panel_snapshot_id ------------------------------------------------


class TestComputePanelSnapshotId:
    def test_returns_sha256_hex(self, tmp_path: Path) -> None:
        f = tmp_path / "panel.parquet"
        f.write_bytes(b"hello world")
        digest = compute_panel_snapshot_id(f)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert digest == expected
        assert len(digest) == 64

    def test_changing_content_changes_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "panel.parquet"
        f.write_bytes(b"a")
        h1 = compute_panel_snapshot_id(f)
        f.write_bytes(b"b")
        h2 = compute_panel_snapshot_id(f)
        assert h1 != h2

    def test_streams_large_file_without_loading(self, tmp_path: Path) -> None:
        # Verify the function doesn't OOM on multi-MB files (it uses
        # chunked reads). Write 8 MB and check the hash still computes.
        f = tmp_path / "panel.parquet"
        payload = b"x" * (8 * 1024 * 1024)
        f.write_bytes(payload)
        digest = compute_panel_snapshot_id(f)
        assert digest == hashlib.sha256(payload).hexdigest()
