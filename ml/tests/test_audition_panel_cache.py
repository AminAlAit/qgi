"""
Unit tests for the audition_indicators.py panel-cache helper (#596).

Tests cover the cache key stability and the cache-hit / cache-miss path,
without touching Athena. The actual `load_indicator_panel` Athena call
is mocked.

Generated: 2026-05-03
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# Load the script as a module without executing main().
# Note: must register the module in sys.modules BEFORE exec_module so that
# @dataclass can resolve cls.__module__ during class creation (Python 3.14
# dataclasses inspect sys.modules to determine the owning module).
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "audition_indicators.py"
_spec = importlib.util.spec_from_file_location("audition_indicators", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["audition_indicators"] = mod
_spec.loader.exec_module(mod)


# ===========================================================================
# Cache-key stability
# ===========================================================================

def test_panel_cache_key_deterministic():
    """Same inputs → same key, regardless of order on indicator_ids."""
    k1 = mod._panel_cache_key(["VD-01", "WB-01", "FA-15"], 2010, 2020)
    k2 = mod._panel_cache_key(["WB-01", "FA-15", "VD-01"], 2010, 2020)
    k3 = mod._panel_cache_key(["FA-15", "VD-01", "WB-01"], 2010, 2020)
    assert k1 == k2 == k3, "cache key must be order-independent on indicator_ids"


def test_panel_cache_key_differs_on_input_change():
    """Different inputs → different keys (no false-positive cache hits)."""
    base = mod._panel_cache_key(["VD-01", "WB-01"], 2010, 2020)
    # Different indicators
    assert mod._panel_cache_key(["VD-01", "WB-02"], 2010, 2020) != base
    # Different start year
    assert mod._panel_cache_key(["VD-01", "WB-01"], 2009, 2020) != base
    # Different end year
    assert mod._panel_cache_key(["VD-01", "WB-01"], 2010, 2021) != base


def test_panel_cache_key_returns_short_hex():
    """Key is 16-char hex (SHA-256 truncated). Stable form for filename use."""
    k = mod._panel_cache_key(["VD-01"], 2000, 2020)
    assert len(k) == 16
    assert all(c in "0123456789abcdef" for c in k)


# ===========================================================================
# _load_panel_with_cache — cache miss path
# ===========================================================================

def test_load_panel_with_cache_none_passes_through(tmp_path):
    """cache_dir=None means: just call load_indicator_panel directly."""
    fake_df = pd.DataFrame({"country": ["X"], "year": [2020], "indicator_id": ["VD-01"], "value": [0.5]})
    with patch.object(mod, "load_indicator_panel", return_value=fake_df) as mock_loader:
        result = mod._load_panel_with_cache(
            ath=None, bucket="b", workgroup="w",
            indicator_ids=["VD-01"], start_year=2010, end_year=2020,
            cache_dir=None,
        )
        # No cache dir: must call the loader, must not touch any cache path
        mock_loader.assert_called_once_with(None, "b", "w", ["VD-01"], 2010, 2020)
        # Even with no cache, the result must equal what the loader returned
        pd.testing.assert_frame_equal(result, fake_df)


def test_load_panel_with_cache_miss_then_hit(tmp_path):
    """First call: miss + write. Second call: hit + skip the loader."""
    cache_dir = tmp_path / "cache"
    fake_df = pd.DataFrame({
        "country": ["X", "Y"], "year": [2019, 2020],
        "indicator_id": ["VD-01", "VD-01"], "value": [0.4, 0.5],
    })
    with patch.object(mod, "load_indicator_panel", return_value=fake_df) as mock_loader:
        # First call: cache miss
        result_1 = mod._load_panel_with_cache(
            ath=None, bucket="b", workgroup="w",
            indicator_ids=["VD-01"], start_year=2010, end_year=2020,
            cache_dir=cache_dir,
        )
        assert mock_loader.call_count == 1
        # Cache file must exist after the miss
        cache_files = list(cache_dir.glob("panel_*.parquet"))
        assert len(cache_files) == 1, f"expected one cache file, got {cache_files}"

        # Second call with same inputs: cache hit, loader NOT called again
        result_2 = mod._load_panel_with_cache(
            ath=None, bucket="b", workgroup="w",
            indicator_ids=["VD-01"], start_year=2010, end_year=2020,
            cache_dir=cache_dir,
        )
        assert mock_loader.call_count == 1, "loader should not be called on cache hit"
        pd.testing.assert_frame_equal(result_1, result_2)


def test_load_panel_with_cache_different_inputs_different_files(tmp_path):
    """Different (indicator_ids | year-range) → different cache files."""
    cache_dir = tmp_path / "cache"
    fake_df_a = pd.DataFrame({"country": ["X"], "year": [2019], "indicator_id": ["VD-01"], "value": [0.4]})
    fake_df_b = pd.DataFrame({"country": ["X"], "year": [2019], "indicator_id": ["WB-01"], "value": [99.0]})

    def _fake_load(ath, bucket, workgroup, indicator_ids, start, end):
        return fake_df_a if "VD-01" in indicator_ids else fake_df_b

    with patch.object(mod, "load_indicator_panel", side_effect=_fake_load):
        # Two miss calls with different inputs
        mod._load_panel_with_cache(None, "b", "w", ["VD-01"], 2010, 2020, cache_dir=cache_dir)
        mod._load_panel_with_cache(None, "b", "w", ["WB-01"], 2010, 2020, cache_dir=cache_dir)
        cache_files = sorted(cache_dir.glob("panel_*.parquet"))
        assert len(cache_files) == 2, f"expected two distinct cache files, got {cache_files}"


def test_load_panel_with_cache_creates_dir_if_missing(tmp_path):
    """cache_dir doesn't exist? Helper creates it (mkdir parents=True, exist_ok=True)."""
    cache_dir = tmp_path / "deeply" / "nested" / "cache"
    fake_df = pd.DataFrame({"country": ["X"], "year": [2020], "indicator_id": ["VD-01"], "value": [0.5]})
    with patch.object(mod, "load_indicator_panel", return_value=fake_df):
        mod._load_panel_with_cache(
            ath=None, bucket="b", workgroup="w",
            indicator_ids=["VD-01"], start_year=2010, end_year=2020,
            cache_dir=cache_dir,
        )
    assert cache_dir.exists(), "nested cache dir should be created"
    parquet_files = list(cache_dir.glob("panel_*.parquet"))
    assert parquet_files, f"no parquet written to cache dir; got: {list(cache_dir.iterdir())}"


def test_panel_cache_key_dedups_duplicates():
    """`['VD-01', 'VD-01']` and `['VD-01']` MUST share a cache key.

    Athena's `IN` clause de-duplicates the SQL output, so both inputs
    produce identical query results. A stray duplicate from upstream
    must not cause a false cache miss. QA review 2026-05-03 caught
    this as a latent risk before the regression bit us in Phase 4.
    """
    k_dup = mod._panel_cache_key(["VD-01", "VD-01"], 2010, 2020)
    k_unique = mod._panel_cache_key(["VD-01"], 2010, 2020)
    assert k_dup == k_unique, (
        "duplicates in indicator_ids must not produce a different cache "
        "key — the SQL output is identical, so the cached parquet is too"
    )
    # Triple duplicates should also collide
    k_triple = mod._panel_cache_key(["VD-01", "VD-01", "VD-01"], 2010, 2020)
    assert k_triple == k_unique


def test_load_panel_with_cache_preserves_dtypes_across_hit(tmp_path):
    """Cache round-trip preserves int year + float value (no integer→float drift)."""
    cache_dir = tmp_path / "cache"
    fake_df = pd.DataFrame({
        "country": ["X", "Y"], "year": [2019, 2020],
        "indicator_id": ["VD-01", "VD-01"], "value": [0.4, 0.5],
    })
    fake_df["year"] = fake_df["year"].astype(int)
    fake_df["value"] = fake_df["value"].astype(float)
    with patch.object(mod, "load_indicator_panel", return_value=fake_df):
        result_miss = mod._load_panel_with_cache(
            None, "b", "w", ["VD-01"], 2010, 2020, cache_dir=cache_dir,
        )
        result_hit = mod._load_panel_with_cache(
            None, "b", "w", ["VD-01"], 2010, 2020, cache_dir=cache_dir,
        )
    # dtypes must match across the round-trip (regression guard against
    # silent int→float drift through parquet)
    assert result_hit["year"].dtype == result_miss["year"].dtype
    assert result_hit["value"].dtype == result_miss["value"].dtype
    pd.testing.assert_frame_equal(result_miss, result_hit)
