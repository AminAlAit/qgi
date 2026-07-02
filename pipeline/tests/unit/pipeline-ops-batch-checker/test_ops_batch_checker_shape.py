"""
Contract test for pipeline-ops-batch-checker (issue #154).

Background: The deployed Lambda drifted to a placeholder stub returning
{statusCode, body} instead of {jobs_running}, which silently broke the
Step Function 'Batch Done?' choice state. See session handoff 2026-04-08
for the full incident.

This test asserts the checker returns the exact shape the Step Function
Choice state references: {jobs_running: int}. Mocks AWS Batch's list_jobs
so the test runs offline with no AWS calls.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"


def _load_checker(list_jobs_counts):
    """Load the checker module with boto3 stubbed to return the given
    count for each of the 5 active statuses (SUBMITTED, PENDING, RUNNABLE,
    STARTING, RUNNING). list_jobs_counts must be a list of 5 ints.
    """
    batch_client = MagicMock()
    batch_client.list_jobs.side_effect = [
        {"jobSummaryList": [{"jobId": f"j{i}"} for i in range(n)]} for n in list_jobs_counts
    ]

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = MagicMock(return_value=batch_client)
    boto3_stub.resource = MagicMock(return_value=MagicMock())

    # JOB_QUEUE is read inside the handler (not at import), so it must
    # persist after the `with` block exits. Set it on os.environ directly.
    os.environ["JOB_QUEUE"] = "test-queue"
    with patch.dict(sys.modules, {"boto3": boto3_stub}):
        spec = importlib.util.spec_from_file_location(
            "ops_batch_checker",
            str(_LAMBDAS_DIR / "pipeline-ops-batch-checker" / "lambda_function.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod, batch_client


def test_return_shape_has_jobs_running_int_key():
    """Shape contract: must return a dict with 'jobs_running' as int."""
    mod, _ = _load_checker([0, 0, 0, 0, 0])
    result = mod.lambda_handler({}, None)
    assert isinstance(result, dict), f"expected dict, got {type(result)}"
    assert "jobs_running" in result, (
        f"missing 'jobs_running' key — Step Function 'Batch Done?' "
        f"choice state requires $.batch_status.jobs_running. Got: {result}"
    )
    assert isinstance(result["jobs_running"], int), (
        f"'jobs_running' must be int for NumericGreaterThan comparison, got {type(result['jobs_running'])}"
    )


def test_return_does_not_look_like_placeholder_stub():
    """Regression guard: the stub that drifted live returned {statusCode, body}.
    If anyone pastes that back in, this test must fail loudly."""
    mod, _ = _load_checker([0, 0, 0, 0, 0])
    result = mod.lambda_handler({}, None)
    assert "statusCode" not in result, (
        "checker is returning the old placeholder stub shape; see issue #154 and session handoff 2026-04-08"
    )
    assert result != {"statusCode": 200, "body": "placeholder"}


def test_zero_running_jobs_returns_zero():
    """All 5 active statuses empty → jobs_running == 0 → Choice state falls
    through to 'Phase 3: MSCK Repair scdis'."""
    mod, _ = _load_checker([0, 0, 0, 0, 0])
    result = mod.lambda_handler({}, None)
    assert result["jobs_running"] == 0


def test_nonzero_sums_across_all_active_statuses():
    """Counts from SUBMITTED + PENDING + RUNNABLE + STARTING + RUNNING sum.
    Regression guard against only-counting-RUNNING bugs."""
    mod, batch_client = _load_checker([1, 2, 0, 3, 4])
    result = mod.lambda_handler({}, None)
    assert result["jobs_running"] == 10
    # Verify all 5 active statuses were polled
    statuses_called = [call.kwargs["jobStatus"] for call in batch_client.list_jobs.call_args_list]
    assert set(statuses_called) == {"SUBMITTED", "PENDING", "RUNNABLE", "STARTING", "RUNNING"}


def test_uses_configured_job_queue_env_var():
    """JOB_QUEUE env var must be passed to list_jobs."""
    mod, batch_client = _load_checker([0, 0, 0, 0, 0])
    mod.lambda_handler({}, None)
    for call in batch_client.list_jobs.call_args_list:
        assert call.kwargs["jobQueue"] == "test-queue"
