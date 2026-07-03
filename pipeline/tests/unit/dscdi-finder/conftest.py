"""Shared fixtures for dscdi-finder entrypoint tests.

The entrypoint module (`run_dscdi_entrypoint.py`) imports `dscdi_finder`
as a top-level module. Both modules live under `batch/dscdi-finder/src/`
which is NOT a Python package. Tests must register both in sys.modules
via importlib so the import resolves.

moto[s3] fixtures provide a mock S3 bucket pre-populated with the
canonical input artifacts the entrypoint expects (audit JSON, indicator
map CSV, countries CSV) so tests don't need to construct them per test.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from io import BytesIO
from pathlib import Path

import boto3
import pandas as pd
import pytest
from moto import mock_aws

_SRC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "batch" / "dscdi-finder" / "src"


def _load_module(name: str, src_path: Path):
    """Load a single module via importlib + register in sys.modules."""
    spec = importlib.util.spec_from_file_location(name, src_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def dscdi_finder_mod():
    """The pure-function library module."""
    return _load_module("dscdi_finder", _SRC_DIR / "dscdi_finder.py")


TEST_BUCKET = "qgi-test-bucket"
TEST_INDICATOR_ID = "v2x_libdem"  # Class A → triggers two-substrate write


@pytest.fixture
def aws_creds(monkeypatch):
    """Set bogus AWS creds so boto3 doesn't read real ones."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")


@pytest.fixture
def s3_mock(aws_creds):
    """Yields a mocked S3 client + bucket name for tests to populate."""
    with mock_aws():
        client = boto3.client("s3", region_name="eu-central-1")
        client.create_bucket(
            Bucket=TEST_BUCKET,
            CreateBucketConfiguration={"LocationConstraint": "eu-central-1"},
        )
        yield client, TEST_BUCKET


@pytest.fixture
def entrypoint_env(monkeypatch, s3_mock):
    """Set the entrypoint env vars to test values BEFORE module load."""
    _, bucket = s3_mock
    monkeypatch.setenv("S3_BUCKET", bucket)
    monkeypatch.setenv("S3_INPUT_PREFIX", "panels/")
    monkeypatch.setenv("S3_OUTPUT_PREFIX", "dscdis")
    monkeypatch.setenv("MANIFEST_S3_PREFIX", "manifest/")
    monkeypatch.setenv("AUDIT_JSON_S3_KEY", "reference/audit-v2.json")
    monkeypatch.setenv("INDICATOR_ID", TEST_INDICATOR_ID)
    monkeypatch.setenv("MIN_LENGTH", "3")
    yield


@pytest.fixture
def entrypoint_mod(dscdi_finder_mod, entrypoint_env):
    """Load the entrypoint module with test env vars set."""
    # Force re-import so module-level env-var reads pick up monkeypatched values.
    sys.modules.pop("run_dscdi_entrypoint", None)
    return _load_module("run_dscdi_entrypoint", _SRC_DIR / "run_dscdi_entrypoint.py")


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------


def make_synthetic_panel(countries: list[str], n_years: int = 30, seed: int = 42) -> pd.DataFrame:
    """Build a wide panel with a strong common factor (drives Class A demeaning).

    Years are 1990..1990+n_years-1; columns are countries; values are a
    common time trend + small per-country noise. Designed so the
    correlation structure is largely common-factor (high pairwise corr
    pre-demeaning, low post-demeaning).

    Both axes carry names ("year", "country") to match what production
    panels look like — production panels come from
    `df.pivot_table(index="year", columns="country", ...)` which names
    both axes from the source columns. The 2026-05-10 Stage F smoke run
    surfaced a _matrix_to_long bug that ONLY reproduced with a named
    columns axis, so the fixture must mirror production.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    years = list(range(1990, 1990 + n_years))
    common_trend = np.linspace(0, 10, n_years)  # strong global signal
    data = {}
    for c in countries:
        idiosyncratic = rng.normal(0, 0.3, n_years)
        data[c] = common_trend + idiosyncratic
    panel = pd.DataFrame(data, index=pd.Index(years, name="year"))
    panel.columns.name = "country"
    return panel


def make_long_panel_parquet(countries: list[str], n_years: int = 30, seed: int = 42) -> bytes:
    """Build a long-format parquet payload (year, country, value)."""
    wide = make_synthetic_panel(countries, n_years, seed)
    long = wide.reset_index().melt(id_vars=["year"], var_name="country", value_name="value")
    buf = BytesIO()
    long.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    return buf.getvalue()


def make_indicator_map_csv(indicator_to_id: dict[str, int]) -> bytes:
    df = pd.DataFrame([{"id_string": k, "numeric_id": v} for k, v in indicator_to_id.items()])
    buf = BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def make_countries_csv(country_to_id: dict[str, int]) -> bytes:
    df = pd.DataFrame([{"name_1": k, "id": v} for k, v in country_to_id.items()])
    buf = BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def make_audit_json(indicator_to_classification: dict[str, str]) -> bytes:
    payload = {
        "schema_version": 2,
        "results": {ind_id: {"classification": cls} for ind_id, cls in indicator_to_classification.items()},
    }
    return json.dumps(payload).encode("utf-8")


COUNTRIES_DEFAULT = [f"Country{i:02d}" for i in range(1, 21)]
COUNTRIES_TO_ID_DEFAULT = {c: i for i, c in enumerate(COUNTRIES_DEFAULT, start=1)}


@pytest.fixture
def populated_s3(s3_mock):
    """Pre-populate the mock bucket with all canonical inputs.

    Tests that need a "happy path" indicator can rely on this fixture
    to have:
      - panel parquet for v2x_libdem (Class A) at panels/v2x_libdem/v2x_libdem.parquet
      - panel parquet for RL.EST (Class B) at panels/RL.EST/RL.EST.parquet
      - panel parquet for NY.GDP.MKTP.KD.ZG (Class A no-transform outlier)
      - audit JSON at reference/audit-v2.json
      - indicator_map.csv at the canonical path
      - countries.csv at the canonical path
    """
    client, bucket = s3_mock

    countries = COUNTRIES_DEFAULT
    countries_to_id = COUNTRIES_TO_ID_DEFAULT

    indicator_map = {
        "v2x_libdem": 1001,
        "RL.EST": 2001,
        "NY.GDP.MKTP.KD.ZG": 3001,
    }
    audit = {
        "v2x_libdem": "I(1)",
        "RL.EST": "I(0)",
        "NY.GDP.MKTP.KD.ZG": "I(0)",
    }

    # Panel parquets (one per indicator, all using the same synthetic data
    # for simplicity — the methodology classification differs per indicator).
    for ind in indicator_map:
        client.put_object(
            Bucket=bucket,
            Key=f"panels/{ind}/{ind}.parquet",
            Body=make_long_panel_parquet(countries),
        )
    client.put_object(
        Bucket=bucket,
        Key="reference/audit-v2.json",
        Body=make_audit_json(audit),
    )
    client.put_object(
        Bucket=bucket,
        Key="pipeline-A-indicator-extractor/input/indicator_map.csv",
        Body=make_indicator_map_csv(indicator_map),
    )
    client.put_object(
        Bucket=bucket,
        Key="pipeline-A-indicator-extractor/countries/countries.csv",
        Body=make_countries_csv(countries_to_id),
    )

    return client, bucket
