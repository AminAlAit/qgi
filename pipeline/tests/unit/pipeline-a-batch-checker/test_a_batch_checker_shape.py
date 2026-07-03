"""
Contract test for pipeline-a-batch-checker (#FAR-1, #154, #178 scan-count).

Asserts the checker returns the exact shape the Step Function
'Fetchers Done?' choice state references: {done, pending, total, run_id,
deadman_expired}. The choice state specifically reads $.a_check.done.

#178 rewrite: checker now scans tracker table rows instead of reading an
atomic decrement counter. Tests mock both the counter table (for `total`)
and the tracker table (for scan-count).
"""

import importlib.util
import os
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"


def _load_checker(counter_item, tracker_count=0):
    """Load with mocked DDB counter_table + tracker_table.

    counter_item: dict for counter table get_item (provides `total`)
    tracker_count: int — how many tracker rows the scan-count query returns
    """
    counter_table = MagicMock()
    counter_table.get_item.return_value = {"Item": counter_item} if counter_item is not None else {}

    tracker_table = MagicMock()
    tracker_table.query.return_value = {
        "Count": tracker_count,
        # no LastEvaluatedKey = single page
    }

    def table_factory(name):
        if "counter" in name.lower():
            return counter_table
        return tracker_table

    ddb_resource = MagicMock()
    ddb_resource.Table.side_effect = table_factory

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = MagicMock(return_value=MagicMock())
    boto3_stub.resource = MagicMock(return_value=ddb_resource)

    # Need to stub boto3.dynamodb.conditions.Key
    ddb_conditions = types.ModuleType("boto3.dynamodb.conditions")
    ddb_conditions.Key = MagicMock(return_value=MagicMock(eq=MagicMock(return_value="key_cond")))
    boto3_ddb = types.ModuleType("boto3.dynamodb")
    boto3_ddb.conditions = ddb_conditions

    env = {
        "COUNTER_TABLE": "qgi-pipeline-a-counter",
        "TRACKER_TABLE": "qgi-indicator-updates",
        "DEADMAN_TIMEOUT_S": "5400",
    }
    with (
        patch.dict(
            sys.modules,
            {
                "boto3": boto3_stub,
                "boto3.dynamodb": boto3_ddb,
                "boto3.dynamodb.conditions": ddb_conditions,
            },
        ),
        patch.dict(os.environ, env),
    ):
        spec = importlib.util.spec_from_file_location(
            "a_batch_checker",
            str(_LAMBDAS_DIR / "pipeline-a-batch-checker" / "lambda_function.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


_REQUIRED_KEYS = {"done", "pending", "total", "run_id", "deadman_expired"}


def test_return_shape_has_all_required_keys():
    """Step Function 'Fetchers Done?' reads $.a_check.done. Reporter also
    consumes .total, .pending, .deadman_expired via parameters mapping."""
    mod = _load_checker({"pending": 0, "total": 60}, tracker_count=60)
    result = mod.lambda_handler({"run_id": "test-run", "total": 60}, None)
    missing = _REQUIRED_KEYS - set(result.keys())
    assert not missing, f"missing keys {missing}. Got {result}"
    assert isinstance(result["done"], bool)
    assert isinstance(result["pending"], int)
    assert isinstance(result["total"], int)


def test_done_true_when_all_tracker_rows_present():
    """#178: done when tracker_count >= total (scan-count pattern)."""
    mod = _load_checker({"pending": 999, "total": 60}, tracker_count=60)
    result = mod.lambda_handler({"run_id": "r1", "total": 60}, None)
    assert result["done"] is True
    assert result["pending"] == 0
    assert result["deadman_expired"] is False


def test_done_false_when_tracker_rows_missing():
    """#178: 55/60 tracker rows = not done yet."""
    mod = _load_checker({"pending": 999, "total": 60}, tracker_count=55)
    result = mod.lambda_handler(
        {"run_id": "r1", "total": 60, "phase1_started_at": int(time.time()) - 60},
        None,
    )
    assert result["done"] is False
    assert result["pending"] == 5
    assert result["deadman_expired"] is False


def test_deadman_forces_done_true_after_timeout():
    """L5 deadman still works with scan-count: forces done after 90 min."""
    mod = _load_checker({"pending": 999, "total": 60}, tracker_count=57)
    result = mod.lambda_handler(
        {"run_id": "r1", "total": 60, "phase1_started_at": int(time.time()) - 9999},
        None,
    )
    assert result["done"] is True
    assert result["deadman_expired"] is True
    assert result["pending"] == 3


def test_missing_counter_row_returns_not_done():
    """Dispatcher hasn't run yet or counter was wiped. Must not crash."""
    mod = _load_checker(None, tracker_count=0)
    result = mod.lambda_handler({"run_id": "r1"}, None)
    assert result["done"] is False
    assert set(result.keys()) >= _REQUIRED_KEYS


def test_spot_interrupted_task_not_stuck():
    """#178 headline test: 59/60 tracker rows (one Spot-killed task) should
    NOT be done=True. The deadman handles it, or Batch retries fill the gap."""
    mod = _load_checker({"pending": 1, "total": 60}, tracker_count=59)
    result = mod.lambda_handler(
        {"run_id": "r1", "total": 60, "phase1_started_at": int(time.time()) - 60},
        None,
    )
    assert result["done"] is False
    assert result["pending"] == 1
