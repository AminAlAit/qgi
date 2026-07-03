"""#919: pipeline-c-worker's run_athena_query must abort (TimeoutError) when <30s of
Lambda budget remains — the worker's INSERT is the one that risks a DUPLICATE INSERT if
the Lambda is killed mid-poll before the message is deleted and the query commits."""

import os
import sys
import types
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"


def _load_module():
    stub = types.ModuleType("boto3")
    stub.client = MagicMock(return_value=MagicMock())
    stub.resource = MagicMock(return_value=MagicMock())
    env = {
        "S3_BUCKET": "b",
        "ATHENA_WORKGROUP": "wg",
        "ATHENA_DATABASE": "qgi_data",
        "SQS_QUEUE_URL": "u",
        "COMPLETION_TABLE": "t",
        "S3_OUTPUT_LOCATION": "s3://b/o/",
    }
    with patch.dict(sys.modules, {"boto3": stub}), patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "c_worker_guard", str(_LAMBDAS_DIR / "pipeline-c-worker" / "lambda_function.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


def _running():
    return {"QueryExecution": {"Status": {"State": "RUNNING"}}}


def _succeeded():
    return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}


def test_worker_poll_aborts_when_budget_low(monkeypatch):
    m = _load_module()
    m.athena_client = MagicMock()
    m.athena_client.start_query_execution.return_value = {"QueryExecutionId": "q1"}
    m.athena_client.get_query_execution.return_value = _running()
    monkeypatch.setattr(m.time, "sleep", lambda *_: None)
    ctx = MagicMock()
    ctx.get_remaining_time_in_millis.return_value = 10_000
    with pytest.raises(TimeoutError):
        m.run_athena_query("SELECT 1", "wg", "db", "s3://x/", context=ctx)


def test_worker_poll_ok_when_budget_ample(monkeypatch):
    m = _load_module()
    m.athena_client = MagicMock()
    m.athena_client.start_query_execution.return_value = {"QueryExecutionId": "q1"}
    m.athena_client.get_query_execution.side_effect = [_running(), _succeeded()]
    monkeypatch.setattr(m.time, "sleep", lambda *_: None)
    ctx = MagicMock()
    ctx.get_remaining_time_in_millis.return_value = 600_000
    assert m.run_athena_query("SELECT 1", "wg", "db", "s3://x/", context=ctx) is None


def test_worker_no_context_keeps_legacy_wait(monkeypatch):
    """No context → no budget guard; waits to completion (back-compat). FU2."""
    m = _load_module()
    m.athena_client = MagicMock()
    m.athena_client.start_query_execution.return_value = {"QueryExecutionId": "q1"}
    m.athena_client.get_query_execution.side_effect = [_running(), _running(), _succeeded()]
    monkeypatch.setattr(m.time, "sleep", lambda *_: None)
    assert m.run_athena_query("SELECT 1", "wg", "db", "s3://x/") is None  # no TimeoutError
