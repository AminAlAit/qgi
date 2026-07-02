"""
Unit tests for pipeline-c-checker: verifies the S3 partition count fallback.
When processed_c counter is stale but S3 partitions >= expected, checker
must return done=True (avoids indefinite Phase C stall).
"""

import sys
import types
import importlib
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"


def _make_boto3_stub():
    stub = types.ModuleType("boto3")
    stub.client = MagicMock(return_value=MagicMock())
    stub.resource = MagicMock(return_value=MagicMock())
    return stub


def _load_module():
    boto3_stub = _make_boto3_stub()
    env_patch = {
        "COMPLETION_TABLE": "qgi-completion-counters",
        "S3_BUCKET": "test-bucket",
    }
    with patch.dict(sys.modules, {"boto3": boto3_stub}), patch.dict(os.environ, env_patch):
        spec = importlib.util.spec_from_file_location(
            "c_checker",
            str(_LAMBDAS_DIR / "pipeline-c-checker" / "lambda_function.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


MODULE = _load_module()


def _make_mock_table(processed_c):
    table = MagicMock()
    item = {"processed_c": processed_c} if processed_c is not None else {}
    table.get_item.return_value = {"Item": item} if item else {"Item": {}}
    mock_resource = MagicMock()
    mock_resource.Table.return_value = table
    return mock_resource, table


class TestCheckerCounterPath:
    def test_done_when_counter_reaches_expected(self):
        mock_resource, _ = _make_mock_table(50)
        with patch.object(MODULE.dynamodb, "Table", mock_resource.Table):
            result = MODULE.lambda_handler({"run_id": "r1", "expected": 50}, {})
        assert result["done"] is True
        assert result["source"] == "counter"

    def test_not_done_when_counter_below_expected_and_s3_also_below(self):
        mock_resource, _ = _make_mock_table(30)

        def fake_count(bucket, prefix):
            return 30  # S3 also at 30, not enough

        with (
            patch.object(MODULE.dynamodb, "Table", mock_resource.Table),
            patch.object(MODULE, "_count_s3_partitions", side_effect=fake_count),
        ):
            result = MODULE.lambda_handler({"run_id": "r2", "expected": 50}, {})
        assert result["done"] is False

    def test_counter_zero_is_not_done(self):
        mock_resource, _ = _make_mock_table(0)

        with (
            patch.object(MODULE.dynamodb, "Table", mock_resource.Table),
            patch.object(MODULE, "_count_s3_partitions", return_value=0),
        ):
            result = MODULE.lambda_handler({"run_id": "r3", "expected": 50}, {})
        assert result["done"] is False


class TestCheckerS3Fallback:
    def test_s3_fallback_triggers_when_counter_stale_but_s3_complete(self):
        """
        Key regression test: counter at 233, S3 at 261, expected 261
        → must return done=True via s3_fallback (not wait forever).
        This is the exact condition that caused the prod-e2e-20260402 stall.
        """
        mock_resource, _ = _make_mock_table(233)

        def fake_count(bucket, prefix):
            return 261

        with (
            patch.object(MODULE.dynamodb, "Table", mock_resource.Table),
            patch.object(MODULE, "_count_s3_partitions", side_effect=fake_count),
        ):
            result = MODULE.lambda_handler({"run_id": "prod-stall", "expected": 261}, {})

        assert result["done"] is True
        assert result["source"] == "s3_fallback"
        assert result["processed"] == 261

    def test_s3_fallback_not_used_when_counter_already_done(self):
        """S3 should not even be queried if the counter already shows completion."""
        mock_resource, _ = _make_mock_table(261)
        mock_s3_count = MagicMock()

        with (
            patch.object(MODULE.dynamodb, "Table", mock_resource.Table),
            patch.object(MODULE, "_count_s3_partitions", mock_s3_count),
        ):
            result = MODULE.lambda_handler({"run_id": "r4", "expected": 261}, {})

        mock_s3_count.assert_not_called()
        assert result["source"] == "counter"
