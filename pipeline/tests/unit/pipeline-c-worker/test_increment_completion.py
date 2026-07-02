"""
Unit tests for _increment_completion() in pipeline-c-worker.
Verifies that DynamoDB failures are propagated (not swallowed).
"""

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"

# ---------------------------------------------------------------------------
# Minimal stub for boto3 so the module can be imported without real AWS creds
# ---------------------------------------------------------------------------


def _make_boto3_stub():
    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = MagicMock(return_value=MagicMock())
    boto3_stub.resource = MagicMock(return_value=MagicMock())
    return boto3_stub


def _load_module():
    """Import pipeline-c-worker lambda_function with boto3 stubbed out."""
    boto3_stub = _make_boto3_stub()
    with patch.dict(sys.modules, {"boto3": boto3_stub}):
        spec = importlib.util.spec_from_file_location(
            "lambda_function",
            str(_LAMBDAS_DIR / "pipeline-c-worker" / "lambda_function.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


MODULE = _load_module()


class TestIncrementCompletion:
    def _patch_resource(self, mock_table):
        """Patch boto3.resource on the already-loaded module object."""
        mock_resource = MagicMock()
        mock_resource.Table.return_value = mock_table
        return patch.object(MODULE.boto3, "resource", return_value=mock_resource)

    def test_success_calls_update_item(self):
        """Happy path: update_item is called once with the correct key."""
        mock_table = MagicMock()
        with self._patch_resource(mock_table):
            MODULE._increment_completion("my-table", "run-123")

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs["Key"] == {"run_id": "run-123"}

    def test_noop_when_table_name_empty(self):
        """Guard: no DynamoDB call when table_name is falsy."""
        mock_table = MagicMock()
        with self._patch_resource(mock_table):
            MODULE._increment_completion("", "run-123")
        mock_table.update_item.assert_not_called()

    def test_noop_when_run_id_unknown(self):
        """Guard: no DynamoDB call when run_id is the sentinel 'unknown'."""
        mock_table = MagicMock()
        with self._patch_resource(mock_table):
            MODULE._increment_completion("my-table", "unknown")
        mock_table.update_item.assert_not_called()

    def test_noop_when_run_id_none(self):
        """Guard: no DynamoDB call when run_id is None."""
        mock_table = MagicMock()
        with self._patch_resource(mock_table):
            MODULE._increment_completion("my-table", None)
        mock_table.update_item.assert_not_called()

    def test_dynamodb_error_is_propagated(self):
        """
        Critical: a DynamoDB failure must raise, not be swallowed.
        If this is silently caught the Phase C counter stalls indefinitely.
        """
        mock_table = MagicMock()
        mock_table.update_item.side_effect = Exception("ProvisionedThroughputExceededException")
        with self._patch_resource(mock_table):
            with pytest.raises(Exception, match="ProvisionedThroughputExceededException"):
                MODULE._increment_completion("my-table", "run-123")

    def test_dynamodb_throttle_is_propagated(self):
        """Throttle errors (ClientError-like) must not be swallowed."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}
        mock_table = MagicMock()
        mock_table.update_item.side_effect = ClientError(error_response, "UpdateItem")
        with self._patch_resource(mock_table):
            with pytest.raises(ClientError):
                MODULE._increment_completion("my-table", "run-456")
