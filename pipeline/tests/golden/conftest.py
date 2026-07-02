"""Shared fixtures for golden-file tests."""

import importlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_DIR = Path(__file__).parent / "expected"
LAMBDAS_DIR = Path(__file__).parent.parent.parent / "lambdas"


def _make_boto3_stub():
    """Create a boto3 stub that prevents real AWS calls at module load time."""
    stub = types.ModuleType("boto3")
    stub.client = MagicMock(return_value=MagicMock())
    stub.resource = MagicMock(return_value=MagicMock())
    return stub


def load_lambda_module(lambda_dir_name: str, env_vars: dict | None = None):
    """
    Dynamically load a Lambda handler module with boto3 stubbed out.
    Returns the module object.
    """
    env = env_vars or {}
    # Provide defaults for common env vars to avoid KeyError at import time
    defaults = {
        "S3_BUCKET": "test-bucket",
        "S3_INPUT_PREFIX": "input",
        "S3_OUTPUT_PREFIX": "output",
        "DYNAMODB_TABLE": "test-table",
        "LOG_LEVEL": "WARNING",
        "ATHENA_DATABASE": "test_db",
        "SCDIS_TABLE": "scdis",
        "COUNTRIES_NAMES_TABLE": "countries",
        "ATHENA_WORKGROUP": "test-workgroup",
        "S3_OUTPUT_LOCATION": "s3://test-bucket/query_results/",
        "SQS_QUEUE_URL": "https://sqs.eu-central-1.amazonaws.com/123456789/test-queue",
        "COMPLETION_TABLE": "test-counters",
        "SNS_TOPIC_ARN": "arn:aws:sns:eu-central-1:123456789:test-topic",
    }
    defaults.update(env)

    handler_path = LAMBDAS_DIR / lambda_dir_name / "lambda_function.py"
    if not handler_path.exists():
        pytest.skip(f"Lambda handler not found: {handler_path}")

    boto3_stub = _make_boto3_stub()

    # Also stub wbgapi if present (used by a-worker)
    wbgapi_stub = types.ModuleType("wbgapi")
    wbgapi_stub.data = MagicMock()
    wbgapi_stub.APIError = type("APIError", (Exception,), {})

    stubs = {"boto3": boto3_stub, "wbgapi": wbgapi_stub, "wb": wbgapi_stub}

    with patch.dict(sys.modules, stubs), patch.dict(os.environ, defaults, clear=False):
        spec = importlib.util.spec_from_file_location(
            f"lambda_{lambda_dir_name.replace('-', '_')}",
            str(handler_path),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

    return mod


@pytest.fixture
def countries_csv_path():
    return FIXTURES_DIR / "countries.csv"


@pytest.fixture
def countries_df(countries_csv_path):
    return pd.read_csv(countries_csv_path)


@pytest.fixture
def scdis_df():
    return pd.read_parquet(FIXTURES_DIR / "scdis.parquet")


@pytest.fixture
def indicator_001_df():
    return pd.read_parquet(FIXTURES_DIR / "indicators" / "TEST.IND.001" / "TEST.IND.001.parquet")


@pytest.fixture
def indicator_002_df():
    return pd.read_parquet(FIXTURES_DIR / "indicators" / "TEST.IND.002" / "TEST.IND.002.parquet")
