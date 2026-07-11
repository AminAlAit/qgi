"""
Tests for `ingest_vdem.upload_per_indicator_parquet` write-path layout
(#510 fix, 2026-04-28).

V-Dem ingest used to write Hive-style paths
`output/parquet/indicator_id={ind}/{ind}.parquet`. That layout doesn't
match the WB/FAO sibling pattern, so the Phase A completer + Phase B
SCDI orchestrator never discovered V-Dem indicators. Switching to BARE
`output/parquet/{ind}/{ind}.parquet` so V-Dem joins the existing
auto-discovery pipeline.

These tests pin the bare-layout contract and surface any regression
that re-introduces the Hive prefix.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "ingest_vdem.py"
)


@pytest.fixture(scope="module")
def ingest_vdem():
    spec = importlib.util.spec_from_file_location(
        "ingest_vdem_under_test_510", str(SCRIPT_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------- #
# Source-text checks (always run, no AWS needed)                         #
# ---------------------------------------------------------------------- #


def test_no_hive_indicator_id_prefix_in_write_path():
    """The Hive-style `indicator_id={ind}/` prefix must NOT appear in
    the parquet write path. Defense against a future revert that
    restores the buggy Hive layout."""
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    # The bare-layout key construction is what's expected
    assert 'f"{S3_PARQUET_PREFIX}/{ind}/{ind}.parquet"' in text, (
        "expected bare-layout f-string for parquet key"
    )
    # The Hive-prefixed form must not exist as actual code (comments
    # documenting the migration are fine — they just won't match this
    # specific f-string pattern)
    assert 'f"{S3_PARQUET_PREFIX}/indicator_id={ind}/{ind}.parquet"' not in text, (
        "Hive-style parquet write path leaked back in (#510 regression)"
    )


# ---------------------------------------------------------------------- #
# Module-level write-path behavior                                       #
# ---------------------------------------------------------------------- #


def test_upload_writes_bare_layout(ingest_vdem):
    """Single indicator → exactly one S3 PutObject call at bare path
    `{prefix}/{ind}/{ind}.parquet`."""
    df = pd.DataFrame({
        "country": ["United States of America", "Germany"],
        "year": [2020, 2020],
        "value": [0.85, 0.92],
        "provider": ["VDEM", "VDEM"],
        "indicator_id": ["v2x_polyarchy", "v2x_polyarchy"],
    })

    fake_s3 = MagicMock()
    with patch("boto3.client", return_value=fake_s3):
        counts = ingest_vdem.upload_per_indicator_parquet(
            df, "qgi-data-lake-x", "eu-central-1", dry_run=False,
        )

    assert counts == {"v2x_polyarchy": 2}
    # Exactly one PutObject for the single indicator
    fake_s3.put_object.assert_called_once()
    put_kwargs = fake_s3.put_object.call_args.kwargs
    # The key has BARE layout — no `indicator_id=` prefix
    assert put_kwargs["Key"] == (
        "pipeline-A-indicator-extractor/output/parquet/v2x_polyarchy/v2x_polyarchy.parquet"
    )


def test_upload_handles_multiple_indicators(ingest_vdem):
    """Multiple indicators → one PutObject per indicator, all at bare
    layout."""
    df = pd.DataFrame({
        "country": ["USA"] * 4,
        "year": [2020, 2021, 2020, 2021],
        "value": [0.85, 0.86, 0.92, 0.91],
        "provider": ["VDEM"] * 4,
        "indicator_id": ["v2x_polyarchy", "v2x_polyarchy", "v2x_libdem", "v2x_libdem"],
    })

    fake_s3 = MagicMock()
    with patch("boto3.client", return_value=fake_s3):
        counts = ingest_vdem.upload_per_indicator_parquet(
            df, "qgi-data-lake-x", "eu-central-1", dry_run=False,
        )

    assert counts == {"v2x_polyarchy": 2, "v2x_libdem": 2}
    assert fake_s3.put_object.call_count == 2

    keys = [c.kwargs["Key"] for c in fake_s3.put_object.call_args_list]
    # Both keys are bare-layout
    assert all("indicator_id=" not in k for k in keys), (
        f"Hive-prefix leaked into a key: {keys}"
    )
    # Both end with /{ind}/{ind}.parquet
    assert any(k.endswith("/v2x_polyarchy/v2x_polyarchy.parquet") for k in keys)
    assert any(k.endswith("/v2x_libdem/v2x_libdem.parquet") for k in keys)


def test_upload_dry_run_skips_s3(ingest_vdem):
    """`--dry-run` mode validates the transform but does NOT call S3."""
    df = pd.DataFrame({
        "country": ["USA"],
        "year": [2020],
        "value": [0.85],
        "provider": ["VDEM"],
        "indicator_id": ["v2x_polyarchy"],
    })

    fake_s3 = MagicMock()
    with patch("boto3.client", return_value=fake_s3):
        counts = ingest_vdem.upload_per_indicator_parquet(
            df, "qgi-data-lake-x", "eu-central-1", dry_run=True,
        )

    # The counts dict is still populated (transform validates), but no
    # network call happens
    assert counts == {"v2x_polyarchy": 1}
    fake_s3.put_object.assert_not_called()


def test_upload_strips_indicator_id_column_from_parquet_body(ingest_vdem):
    """The parquet body must NOT carry the `indicator_id` column —
    Athena reads it from the path. Otherwise we'd have a redundant
    column AND the SCDI finder's pandas read would see an extra
    column it doesn't expect."""
    df = pd.DataFrame({
        "country": ["USA"],
        "year": [2020],
        "value": [0.85],
        "provider": ["VDEM"],
        "indicator_id": ["v2x_polyarchy"],
    })

    captured_bodies = {}

    def capture_put(**kwargs):
        captured_bodies[kwargs["Key"]] = kwargs["Body"]

    fake_s3 = MagicMock()
    fake_s3.put_object.side_effect = capture_put
    with patch("boto3.client", return_value=fake_s3):
        ingest_vdem.upload_per_indicator_parquet(
            df, "qgi-data-lake-x", "eu-central-1", dry_run=False,
        )

    assert len(captured_bodies) == 1
    parquet_bytes = next(iter(captured_bodies.values()))

    # Read the parquet back and confirm `indicator_id` column is gone
    import io
    import pyarrow.parquet as pq
    table = pq.read_table(io.BytesIO(parquet_bytes))
    cols = set(table.column_names)
    assert "indicator_id" not in cols, (
        f"indicator_id column leaked into parquet body: {cols}"
    )
    # Other columns must remain
    assert "country" in cols
    assert "year" in cols
    assert "value" in cols
    assert "provider" in cols


def test_s3_parquet_prefix_constant_unchanged(ingest_vdem):
    """The prefix itself is not affected by the #510 fix — only the
    layout below it. Pinning the constant catches a refactor that
    accidentally moves V-Dem to a different parent prefix."""
    assert ingest_vdem.S3_PARQUET_PREFIX == "pipeline-A-indicator-extractor/output/parquet"
