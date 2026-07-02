"""
Unit tests for pipeline-a-batch-failure-handler (#243 + #241 Phase B).

The QA safety review on 2026-04-20 flagged this as the BLOCKER
for Phase B rollout: the handler was written assuming one INDICATOR_ID
per Batch job (the WB pattern), but #241 Phase B introduces FAOSTAT
tasks that carry N indicators via INDICATORS_JSON. A hard-killed
FAOSTAT domain task would have left tracker_count N-1 short of total
and hung the Phase 1 checker for 90 min.

Covers:
- Legacy single-INDICATOR_ID path (WB hard-kill) still works
- INDICATORS_JSON multi-indicator path writes N tracker rows +
  decrements counter by N
- INDICATORS_JSON takes priority over INDICATOR_ID when both present
- Malformed INDICATORS_JSON falls back to INDICATOR_ID gracefully
- Missing run_id / missing indicator env vars both skip cleanly
- Job-name fallback still works for WB jobs when env is entirely
  absent (Fargate failing before env-var injection, edge case)
- Failure-kind classification (TIMEOUT / SPOT_RECLAIM / OOM / BATCH_FAILED)
- Partial tracker-write failures still decrement counter by full count
"""

import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_LAMBDA_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "lambdas"
    / "pipeline-a-batch-failure-handler"
    / "lambda_function.py"
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TRACKER_TABLE", "qgi-indicator-updates")
    monkeypatch.setenv("COUNTER_TABLE", "qgi-pipeline-a-counter")


def _load_handler():
    """Load the handler with boto3 mocked."""
    tracker_table = MagicMock()
    counter_table = MagicMock()
    ddb_resource = MagicMock()
    ddb_resource.Table.side_effect = lambda name: {
        "qgi-indicator-updates": tracker_table,
        "qgi-pipeline-a-counter": counter_table,
    }.get(name, MagicMock())

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.resource = MagicMock(return_value=ddb_resource)
    boto3_stub.client = MagicMock()

    with patch.dict(sys.modules, {"boto3": boto3_stub}):
        spec = importlib.util.spec_from_file_location("failure_handler", str(_LAMBDA_PATH))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod, tracker_table, counter_table


def _make_event(
    *,
    env: dict[str, str] | None = None,
    job_name: str = "qgi-fetch-NY-GDP-MKTP-CD-20260420abcd",
    status_reason: str = "Essential container in task exited",
    job_id: str = "test-job-id",
):
    """Build a Batch JobStateChange=FAILED event dict."""
    env_list = [{"name": k, "value": v} for k, v in (env or {}).items()]
    return {
        "detail": {
            "jobId": job_id,
            "jobName": job_name,
            "statusReason": status_reason,
            "container": {"environment": env_list},
        }
    }


# ---------------------------------------------------------------------- #
# Legacy single-indicator WB path                                        #
# ---------------------------------------------------------------------- #


def test_wb_single_indicator_writes_one_tracker_and_decrements_by_one():
    mod, tracker, counter = _load_handler()
    event = _make_event(
        env={
            "RUN_ID": "run-1",
            "INDICATOR_ID": "NY.GDP.MKTP.CD",
            "PROVIDER": "WB",
        }
    )
    result = mod.lambda_handler(event, None)
    assert result["status"] == "handled"
    assert result["indicator_count"] == 1
    assert result["tracker_rows_written"] == 1
    # One tracker row, one counter decrement of -1
    assert tracker.put_item.call_count == 1
    tracker.put_item.assert_called_once()
    item = tracker.put_item.call_args.kwargs["Item"]
    assert item["indicator_id"] == "NY.GDP.MKTP.CD"
    assert item["status"] == "FAILED"
    assert item["provider"] == "WB"
    # Counter decremented by 1
    counter.update_item.assert_called_once()
    assert counter.update_item.call_args.kwargs["ExpressionAttributeValues"][":neg"] == -1


def test_wb_job_name_fallback_when_env_missing():
    """If both env vars are absent, parse INDICATOR_ID from job name —
    works for WB-style `qgi-fetch-{safe_id}-{suffix}` names."""
    mod, tracker, counter = _load_handler()
    event = _make_event(
        env={"RUN_ID": "run-1"},  # INDICATOR_ID missing
        job_name="qgi-fetch-NY-GDP-MKTP-CD-20260420abcd",
    )
    result = mod.lambda_handler(event, None)
    assert result["status"] == "handled"
    assert result["indicator_ids"] == ["NY.GDP.MKTP.CD"]


# ---------------------------------------------------------------------- #
# #241 Phase B — FAOSTAT multi-indicator path                           #
# ---------------------------------------------------------------------- #


def test_faostat_indicators_json_writes_n_tracker_rows_and_decrements_by_n():
    """This is the core #241 Phase B BLOCKER fix.

    A FAOSTAT domain task covers N indicators via INDICATORS_JSON. If
    the task hard-dies, we MUST write N FAILED rows and decrement the
    counter by N — not 1. Otherwise Phase 1 hangs for 90 min."""
    mod, tracker, counter = _load_handler()
    indicators = [
        {"id_string": "FA-01", "numeric_id": 59, "item_code": 21010},
        {"id_string": "FA-02", "numeric_id": 60, "item_code": 21011},
        {"id_string": "FA-03", "numeric_id": 61, "item_code": 21012},
        {"id_string": "FA-04", "numeric_id": 62, "item_code": 21013},
        {"id_string": "FA-05", "numeric_id": 63, "item_code": 21014},
        {"id_string": "FA-14", "numeric_id": 72, "item_code": 21015},
    ]
    event = _make_event(
        env={
            "RUN_ID": "run-1",
            "DOMAIN_CODE": "FS",
            "INDICATORS_JSON": json.dumps(indicators),
            "PROVIDER": "FAOSTAT",
        }
    )
    result = mod.lambda_handler(event, None)

    assert result["status"] == "handled"
    assert result["indicator_count"] == 6
    assert result["tracker_rows_written"] == 6
    assert result["provider"] == "FAOSTAT"

    # 6 tracker rows, one per indicator, all with provider=FAOSTAT
    assert tracker.put_item.call_count == 6
    written_ids = {c.kwargs["Item"]["indicator_id"] for c in tracker.put_item.call_args_list}
    assert written_ids == {"FA-01", "FA-02", "FA-03", "FA-04", "FA-05", "FA-14"}
    for call in tracker.put_item.call_args_list:
        assert call.kwargs["Item"]["provider"] == "FAOSTAT"
        assert call.kwargs["Item"]["status"] == "FAILED"

    # Counter decremented by 6 (one atomic op, not 6)
    counter.update_item.assert_called_once()
    assert counter.update_item.call_args.kwargs["ExpressionAttributeValues"][":neg"] == -6


def test_indicators_json_takes_priority_over_indicator_id():
    """If both env vars are present (ambiguous, shouldn't happen but be
    defensive), INDICATORS_JSON wins — it has the authoritative count."""
    mod, tracker, counter = _load_handler()
    event = _make_event(
        env={
            "RUN_ID": "run-1",
            "INDICATOR_ID": "FA-01",  # decoy
            "INDICATORS_JSON": json.dumps(
                [
                    {"id_string": "FA-01"},
                    {"id_string": "FA-02"},
                ]
            ),
            "PROVIDER": "FAOSTAT",
        }
    )
    result = mod.lambda_handler(event, None)
    assert result["indicator_count"] == 2
    assert counter.update_item.call_args.kwargs["ExpressionAttributeValues"][":neg"] == -2


def test_malformed_indicators_json_falls_back_to_single_indicator_id():
    """If INDICATORS_JSON is garbage (operator error during a TF apply or
    a mid-flight version mismatch), don't crash — fall back to
    INDICATOR_ID so the handler still closes the single-indicator case."""
    mod, tracker, counter = _load_handler()
    event = _make_event(
        env={
            "RUN_ID": "run-1",
            "INDICATORS_JSON": "not-json",
            "INDICATOR_ID": "NY.GDP.MKTP.CD",
            "PROVIDER": "WB",
        }
    )
    result = mod.lambda_handler(event, None)
    assert result["status"] == "handled"
    assert result["indicator_count"] == 1
    assert result["indicator_ids"] == ["NY.GDP.MKTP.CD"]


# ---------------------------------------------------------------------- #
# Skips and failure-kind classification                                  #
# ---------------------------------------------------------------------- #


def test_skip_when_run_id_missing():
    mod, tracker, counter = _load_handler()
    event = _make_event(env={"INDICATOR_ID": "X"})  # no RUN_ID
    result = mod.lambda_handler(event, None)
    assert result["status"] == "skipped"
    assert result["reason"] == "no_run_id"
    tracker.put_item.assert_not_called()
    counter.update_item.assert_not_called()


def test_skip_when_no_indicator_ids_and_job_name_unparsable():
    """Safety net for when env is entirely absent AND job_name is non-
    standard (shouldn't happen in prod, but the handler must not hang)."""
    mod, tracker, counter = _load_handler()
    event = _make_event(
        env={"RUN_ID": "run-1"},
        job_name="weird-standalone-name",  # won't match the regex
    )
    result = mod.lambda_handler(event, None)
    assert result["status"] == "skipped"
    assert result["reason"] == "no_indicator_ids"
    tracker.put_item.assert_not_called()
    counter.update_item.assert_not_called()


@pytest.mark.parametrize(
    "status_reason,expected_kind",
    [
        ("The job duration exceeded timeout", "TIMEOUT"),
        ("Spot reclaimed the task", "SPOT_RECLAIM"),
        ("Host EC2 was decommissioned", "SPOT_RECLAIM"),
        ("Container killed due to OutOfMemoryError", "OOM"),
        ("Random other failure", "BATCH_FAILED"),
    ],
)
def test_failure_kind_classification(status_reason, expected_kind):
    mod, tracker, _ = _load_handler()
    event = _make_event(
        env={"RUN_ID": "run-1", "INDICATOR_ID": "X", "PROVIDER": "WB"},
        status_reason=status_reason,
    )
    result = mod.lambda_handler(event, None)
    assert result["kind"] == expected_kind
    item = tracker.put_item.call_args.kwargs["Item"]
    assert item["failure_kind"] == expected_kind


# ---------------------------------------------------------------------- #
# Partial failure resilience                                             #
# ---------------------------------------------------------------------- #


def test_partial_tracker_write_failure_still_decrements_counter_by_full_count():
    """Critical: the counter decrement MUST be by the full indicator
    count, not by the number of successful tracker writes. Otherwise a
    partial DDB outage would leave the counter stuck."""
    mod, tracker, counter = _load_handler()
    # Make the 3rd tracker write fail
    call_count = {"n": 0}

    def flaky_put(**kw):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise RuntimeError("DDB throttled")
        return {}

    tracker.put_item.side_effect = flaky_put

    event = _make_event(
        env={
            "RUN_ID": "run-1",
            "INDICATORS_JSON": json.dumps(
                [
                    {"id_string": "FA-01"},
                    {"id_string": "FA-02"},
                    {"id_string": "FA-03"},  # this write will throw
                    {"id_string": "FA-04"},
                ]
            ),
            "PROVIDER": "FAOSTAT",
        }
    )
    result = mod.lambda_handler(event, None)
    assert result["status"] == "handled"
    # 3 successful writes (1, 2, 4), 1 failed (3)
    assert result["tracker_rows_written"] == 3
    assert result["indicator_count"] == 4
    # Counter decremented by 4 (full indicator count), not 3
    counter.update_item.assert_called_once()
    assert counter.update_item.call_args.kwargs["ExpressionAttributeValues"][":neg"] == -4
