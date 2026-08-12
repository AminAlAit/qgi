"""
Unit tests for compact_scdi_prefix.py.

Tests cover:
  - list_country_ids: parses `country_a_id={N}/` prefixes correctly,
    skips non-conforming directories
  - compact_one_country: idempotency, dry-run, error paths

S3 + PyArrow are mocked so tests run without AWS / real parquet files.

Generated: 2026-05-03
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Load the script as a module without executing main().
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "compact_scdi_prefix.py"
_spec = importlib.util.spec_from_file_location("compact_scdi_prefix", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["compact_scdi_prefix"] = mod
_spec.loader.exec_module(mod)


# ===========================================================================
# list_country_ids
# ===========================================================================

def test_list_country_ids_parses_partition_prefixes():
    """Discovers country_a_id={N}/ partitions; skips non-matching dirs."""
    mock_s3 = MagicMock()
    paginator = MagicMock()
    mock_s3.get_paginator.return_value = paginator
    paginator.paginate.return_value = [
        {
            "CommonPrefixes": [
                {"Prefix": "pipeline-B-scdi-finder/scdis/country_a_id=1/"},
                {"Prefix": "pipeline-B-scdi-finder/scdis/country_a_id=10/"},
                {"Prefix": "pipeline-B-scdi-finder/scdis/country_a_id=200/"},
                # Non-conforming entries should be skipped (defensive)
                {"Prefix": "pipeline-B-scdi-finder/scdis/_metadata/"},
                {"Prefix": "pipeline-B-scdi-finder/scdis/country_a_id=NOT_A_NUMBER/"},
            ],
        },
    ]
    out = mod.list_country_ids(mock_s3, "qgi-data-lake-X", "pipeline-B-scdi-finder/scdis/")
    assert out == [1, 10, 200], f"unexpected: {out}"


def test_list_country_ids_handles_empty_paginate_result():
    """No partitions → empty list, no crash."""
    mock_s3 = MagicMock()
    paginator = MagicMock()
    mock_s3.get_paginator.return_value = paginator
    paginator.paginate.return_value = [{"CommonPrefixes": None}]
    out = mod.list_country_ids(mock_s3, "qgi-data-lake-X", "pipeline-B-scdi-finder/scdis/")
    assert out == []


# ===========================================================================
# compact_one_country — idempotency + dry-run paths
# ===========================================================================

def _make_mock_s3fs(target_exists: bool, source_metadata_rows: int,
                    target_metadata_rows: int = 0):
    """Build a mock s3fs object that simulates source + target prefix
    parquet metadata reads.
    """
    mock_fs = MagicMock()
    mock_fs.exists = MagicMock(return_value=target_exists)

    # glob() returns a list of source files (the script counts metadata
    # across all of them). We use a single fake file per partition for
    # simplicity; tests exercise the count logic, not the multi-file path.
    mock_fs.glob = MagicMock(return_value=["fake_source_0.parquet"])

    # open() returns a MagicMock context manager. Tests then patch
    # ParquetFile.metadata.num_rows separately.
    mock_handle = MagicMock()
    mock_fs.open = MagicMock()
    mock_fs.open.return_value.__enter__ = MagicMock(return_value=mock_handle)
    mock_fs.open.return_value.__exit__ = MagicMock(return_value=False)

    return mock_fs


def test_compact_one_country_idempotent_skip():
    """If target exists with matching row count, return skipped_idempotent
    without reading or writing source files."""
    mock_fs = _make_mock_s3fs(target_exists=True, source_metadata_rows=1000)

    # ParquetFile is called twice: once for source count, once for target.
    # Both return num_rows=1000. The result is "skipped_idempotent".
    mock_pf = MagicMock()
    mock_pf.metadata.num_rows = 1000

    with patch.object(mod.pq, "ParquetFile", return_value=mock_pf):
        src_rows, written, status = mod.compact_one_country(
            mock_fs, "bucket", "src/", "tgt/",
            country_id=42, dry_run=False,
        )
    assert (src_rows, written, status) == (1000, 1000, "skipped_idempotent")


def test_compact_one_country_dry_run_does_not_write():
    """In dry-run mode, return dry_run status with written_rows=0,
    NEVER call write_table."""
    mock_fs = _make_mock_s3fs(target_exists=False, source_metadata_rows=500)
    mock_pf = MagicMock()
    mock_pf.metadata.num_rows = 500

    with patch.object(mod.pq, "ParquetFile", return_value=mock_pf), \
         patch.object(mod.pq, "write_table") as mock_write, \
         patch.object(mod.pq, "ParquetDataset") as mock_ds:
        src_rows, written, status = mod.compact_one_country(
            mock_fs, "bucket", "src/", "tgt/",
            country_id=42, dry_run=True,
        )
    assert (src_rows, written, status) == (500, 0, "dry_run")
    mock_write.assert_not_called()
    mock_ds.assert_not_called()


def test_compact_one_country_empty_source_partition():
    """Source partition has 0 rows → return error:empty_source_partition.

    Defensive: a country directory that exists but has no parquet files
    is a data-integrity issue, not a successful no-op.
    """
    mock_fs = _make_mock_s3fs(target_exists=False, source_metadata_rows=0)
    mock_fs.glob = MagicMock(return_value=[])  # no parquet files in source

    src_rows, written, status = mod.compact_one_country(
        mock_fs, "bucket", "src/", "tgt/",
        country_id=42, dry_run=False,
    )
    assert src_rows == 0
    assert status == "error:empty_source_partition"


def test_compact_one_country_unreadable_metadata():
    """Source metadata read raises → return error:source_metadata_unreadable."""
    mock_fs = MagicMock()
    mock_fs.glob = MagicMock(side_effect=Exception("S3 throttled"))

    src_rows, written, status = mod.compact_one_country(
        mock_fs, "bucket", "src/", "tgt/",
        country_id=42, dry_run=False,
    )
    # count_rows_via_metadata catches all exceptions and returns -1, which
    # propagates to the outer error message.
    assert status == "error:source_metadata_unreadable"
    assert src_rows == 0


# ===========================================================================
# count_rows_via_metadata — exception handling
# ===========================================================================

def test_count_rows_via_metadata_returns_zero_when_no_files():
    """Empty prefix returns 0, not -1 (distinguishes legitimate empty
    from unreadable error)."""
    mock_fs = MagicMock()
    mock_fs.glob = MagicMock(return_value=[])
    out = mod.count_rows_via_metadata(mock_fs, "bucket", "prefix/")
    assert out == 0


def test_count_rows_via_metadata_returns_neg1_on_error():
    """Any exception during metadata read returns -1 (distinguishes
    unreadable from empty)."""
    mock_fs = MagicMock()
    mock_fs.glob = MagicMock(side_effect=RuntimeError("timeout"))
    out = mod.count_rows_via_metadata(mock_fs, "bucket", "prefix/")
    assert out == -1


def test_count_rows_via_metadata_sums_across_files():
    """Across multiple parquet files, sums num_rows correctly."""
    mock_fs = MagicMock()
    mock_fs.glob = MagicMock(return_value=["a.parquet", "b.parquet", "c.parquet"])
    mock_handle = MagicMock()
    mock_fs.open = MagicMock()
    mock_fs.open.return_value.__enter__ = MagicMock(return_value=mock_handle)
    mock_fs.open.return_value.__exit__ = MagicMock(return_value=False)

    # ParquetFile returns different num_rows for each file
    side_effect = [
        MagicMock(metadata=MagicMock(num_rows=100)),
        MagicMock(metadata=MagicMock(num_rows=200)),
        MagicMock(metadata=MagicMock(num_rows=300)),
    ]
    with patch.object(mod.pq, "ParquetFile", side_effect=side_effect):
        out = mod.count_rows_via_metadata(mock_fs, "bucket", "prefix/")
    assert out == 600
