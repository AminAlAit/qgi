"""
Contract tests for pipeline-indicator-manifest-reader (#175).

The manifest reader is the bridge between the decoupled Fetch SF and the
Main SF. It reads a manifest JSON from S3 (written by the Fetch SF's
reporter) and returns it for the Main SF to route through. These tests
verify the critical behaviors:

1. Happy path: reads manifest, returns correct shape
2. force_full_run overrides updated_ids with all_indicator_ids
3. Missing manifest raises RuntimeError (fetch SF hasn't run)
4. Missing force_full_run key defaults to False
"""

import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"
_LAMBDA_FILE = _LAMBDAS_DIR / "pipeline-indicator-manifest-reader" / "lambda_function.py"

SAMPLE_MANIFEST = {
    "run_id": "fetch-test-001",
    "timestamp": "2026-04-10T06:00:00Z",
    "updated_ids": ["SP.POP.TOTL", "NY.GDP.MKTP.KD.ZG"],
    "updated_count": 2,
    "total_fetched": 60,
    "failed_ids": ["BROKEN.IND"],
    "all_indicator_ids": [
        "AG.PRD.FOOD.XD",
        "NY.GDP.MKTP.KD.ZG",
        "SP.POP.TOTL",
    ],
}


def _make_s3_mock(manifest_dict=None, raise_no_such_key=False):
    """Build a mock S3 client that returns the given manifest or raises."""
    s3_mock = MagicMock()
    if raise_no_such_key:
        from botocore.exceptions import ClientError

        s3_mock.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
            "GetObject",
        )
    elif manifest_dict is not None:
        body_mock = MagicMock()
        body_mock.read.return_value = json.dumps(manifest_dict).encode()
        s3_mock.get_object.return_value = {"Body": body_mock}
    return s3_mock


def _load_module(s3_mock):
    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = MagicMock(return_value=s3_mock)

    botocore_stub = types.ModuleType("botocore")
    botocore_exceptions = types.ModuleType("botocore.exceptions")
    from botocore.exceptions import ClientError

    botocore_exceptions.ClientError = ClientError
    botocore_stub.exceptions = botocore_exceptions

    env = {
        "S3_BUCKET": "test-bucket",
        "MANIFEST_KEY": "indicator-freshness/latest-fetch-manifest.json",
    }
    with (
        patch.dict(
            sys.modules,
            {
                "boto3": boto3_stub,
                "botocore": botocore_stub,
                "botocore.exceptions": botocore_exceptions,
            },
        ),
        patch.dict(os.environ, env),
    ):
        spec = importlib.util.spec_from_file_location(
            "manifest_reader",
            str(_LAMBDA_FILE),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def test_returns_manifest_from_s3():
    """Happy path: reads manifest, returns correct shape with updated_ids."""
    s3_mock = _make_s3_mock(SAMPLE_MANIFEST)
    mod = _load_module(s3_mock)
    result = mod.lambda_handler({}, None)

    assert result["updated_ids"] == ["SP.POP.TOTL", "NY.GDP.MKTP.KD.ZG"]
    assert result["updated_count"] == 2
    assert result["all_indicator_ids"] == SAMPLE_MANIFEST["all_indicator_ids"]
    assert result["run_id"] == "fetch-test-001"
    assert result["status"] == "Complete"
    assert result["force_full_run"] is False


def test_force_full_run_overrides_updated_ids():
    """force_full_run=true replaces updated_ids with all_indicator_ids."""
    s3_mock = _make_s3_mock(SAMPLE_MANIFEST)
    mod = _load_module(s3_mock)
    result = mod.lambda_handler({"force_full_run": True}, None)

    assert result["updated_ids"] == SAMPLE_MANIFEST["all_indicator_ids"]
    assert result["updated_count"] == 3  # all 3 indicators
    assert result["force_full_run"] is True


def test_missing_manifest_raises_runtime_error():
    """If manifest doesn't exist in S3, raise RuntimeError (fetch SF hasn't run)."""
    s3_mock = _make_s3_mock(raise_no_such_key=True)
    mod = _load_module(s3_mock)

    raised = False
    try:
        mod.lambda_handler({}, None)
    except RuntimeError as exc:
        raised = True
        assert "qgi-indicator-data-refresher" in str(exc)
    assert raised, "must raise RuntimeError when manifest is missing"


def test_default_force_full_run_is_false():
    """When force_full_run key is absent, only updated_ids are returned."""
    s3_mock = _make_s3_mock(SAMPLE_MANIFEST)
    mod = _load_module(s3_mock)
    result = mod.lambda_handler({}, None)  # no force_full_run key

    assert result["updated_ids"] == SAMPLE_MANIFEST["updated_ids"]
    assert result["updated_count"] == 2  # only 2 updated, not all 3
