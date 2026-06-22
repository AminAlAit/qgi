"""
Phase 1 Batch Checker (#FAR-1, #178 scan-count rewrite)

Polled by the Step Function every 2 minutes after the dispatcher fans out
N AWS Batch jobs. Instead of reading an atomic decrement counter (which
gets stuck when Spot-interrupted tasks die before decrementing), this
version SCANS the tracker table for rows with the current run_id and
counts them. A dead task = a missing row = count is N-1, not a stuck
counter.

## Return shape (consumed by the `Fetchers Done?` Choice state)
  {
    "done": True/False,
    "pending": <int remaining>,
    "total": <int original>,
    "run_id": "...",
    "deadman_expired": True/False  # L5 safety net
  }

## Completion logic
  done = (tracker_count >= total) OR deadman_expired

The counter table is still read for `total` (seeded by the dispatcher).
The `pending` field in the counter is ignored — completion is determined
entirely by tracker row count.

## Deadman timer (L5)
If tracker_count < total and the run has been going for more than
DEADMAN_TIMEOUT_S (default 5400 = 90 min), we return done=True with
deadman_expired=True. This prevents infinite polling if Batch itself
goes sideways or WB API is completely down.
"""

import logging
import os
import time

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

COUNTER_TABLE = os.environ["COUNTER_TABLE"]
TRACKER_TABLE = os.environ.get("TRACKER_TABLE", "qgi-indicator-updates")
DEADMAN_TIMEOUT_S = int(os.environ.get("DEADMAN_TIMEOUT_S", "5400"))  # 90 min

counter_table = dynamodb.Table(COUNTER_TABLE)
tracker_table = dynamodb.Table(TRACKER_TABLE)


def lambda_handler(event, context):
    run_id = event.get("run_id", "unknown")
    started_at = event.get("phase1_started_at")  # epoch seconds
    total = int(event.get("total", 0))

    # If total not passed in event, read from counter table (backward compat)
    if total <= 0:
        response = counter_table.get_item(Key={"run_id": run_id})
        item = response.get("Item")
        if not item:
            logger.warning(f"No counter row for run_id={run_id}; reporting not-done")
            return {
                "done": False,
                "pending": -1,
                "total": -1,
                "run_id": run_id,
                "deadman_expired": False,
            }
        total = int(item.get("total", 0))

    # Scan-count: count tracker rows for this run_id (#178)
    tracker_count = _count_tracker_rows(run_id)
    pending = max(0, total - tracker_count)

    logger.info(f"Counter check: run_id={run_id} tracker_rows={tracker_count}/{total} pending={pending}")

    # Deadman timer (L5)
    deadman_expired = False
    if started_at and pending > 0:
        elapsed = time.time() - float(started_at)
        if elapsed > DEADMAN_TIMEOUT_S:
            logger.error(
                f"DEADMAN TIMER EXPIRED: run_id={run_id} "
                f"tracker_rows={tracker_count}/{total} "
                f"after {elapsed:.0f}s — forcing done=True"
            )
            deadman_expired = True

    return {
        "done": tracker_count >= total or deadman_expired,
        "pending": pending,
        "total": total,
        "run_id": run_id,
        "deadman_expired": deadman_expired,
    }


def _count_tracker_rows(run_id):
    """Count how many tracker rows exist for this run_id.

    Uses a Query on the run_id partition key (not a full table Scan).
    With ~60 items per run, this is essentially free (~1 RCU).
    """
    count = 0
    kwargs = {
        "KeyConditionExpression": Key("run_id").eq(run_id),
        "Select": "COUNT",
    }
    while True:
        response = tracker_table.query(**kwargs)
        count += response["Count"]
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return count
