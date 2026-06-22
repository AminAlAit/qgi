"""
Phase 1 Batch Failure Handler (#243 PERMA FIX for the pending-counter deadlock)

## Problem
When a Phase 1 fetcher Batch job dies HARD — Fargate Spot reclaim, container
OOM, or `attemptDurationSeconds` timeout — the worker process is SIGKILL'd
mid-execution. The `except` block in `fetch_one.py` does NOT run, so:

  - No tracker row is written for that indicator.
  - No counter decrement happens.

The checker Lambda's completion logic is `tracker_count >= total`. With a
hard-killed indicator, tracker_count can never reach total. The Step Function
sits in the F.2→F.4 wait/check loop until the 90-min L5 deadman fires.

## Fix
This Lambda is triggered by EventBridge for Batch JobStateChange events
where the new state is FAILED, scoped to the qgi-pipeline-a-fetcher-queue.
On invocation, it:

  1. Extracts the indicator id(s) from the job's container env.
  2. Extracts the run_id.
  3. Writes a FAILED tracker row per indicator to qgi-indicator-updates
     with the actual status reason from the Batch event — closing the
     loop the worker never got to close.
  4. Decrements the qgi-pipeline-a-counter by the indicator count.

This makes the checker progress correctly even when jobs die hard. The L5
deadman is now genuinely the LAST line of defence, not the first.

## #241 Phase B: multi-indicator FAOSTAT tasks

The dispatcher now groups FAOSTAT indicators by `fao_domain_code` and
submits ONE Batch job per domain with a list of indicators in the
`INDICATORS_JSON` env var (instead of one `INDICATOR_ID` per job).
If a FAOSTAT domain task is hard-killed, the single INDICATOR_ID-based
code path would miss writing N-1 tracker rows, and the counter would
only be decremented by 1 instead of N — leading to the exact 90-min
deadman deadlock this Lambda exists to prevent.

Fix: check for INDICATORS_JSON first. If present, parse the list and
treat this as N indicators. If absent, fall through to the legacy
single-INDICATOR_ID path for WB tasks (and any future per-indicator
providers).

## Idempotency
The tracker write is idempotent on (run_id, indicator_id) since the worker's
final state-overwrite happens in a different code path; if both the worker
and this handler write a tracker row for the same indicator, last-write-wins
on the PK, and both rows say FAILED.

## Env vars
  - TRACKER_TABLE  (default: qgi-indicator-updates)
  - COUNTER_TABLE  (default: qgi-pipeline-a-counter)

## EventBridge rule that triggers this:
  Pattern:
  {
    "source": ["aws.batch"],
    "detail-type": ["Batch Job State Change"],
    "detail": {
      "status": ["FAILED"],
      "jobQueue": ["arn:aws:batch:...:job-queue/qgi-pipeline-a-fetcher-queue"]
    }
  }
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from decimal import Decimal
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
TRACKER_TABLE_NAME = os.environ.get("TRACKER_TABLE", "qgi-indicator-updates")
COUNTER_TABLE_NAME = os.environ.get("COUNTER_TABLE", "qgi-pipeline-a-counter")
tracker_table = dynamodb.Table(TRACKER_TABLE_NAME)
counter_table = dynamodb.Table(COUNTER_TABLE_NAME)


def _extract_env(env_list: list[dict] | None, key: str) -> str | None:
    """Find the value of `key` in a Batch container env list of {name,value}."""
    if not env_list:
        return None
    for kv in env_list:
        if kv.get("name") == key:
            return kv.get("value")
    return None


def _parse_indicator_from_job_name(job_name: str) -> str | None:
    """Fallback: parse INDICATOR_ID from the job name when env is absent.

    Dispatcher names jobs as: ``qgi-fetch-{safe_id}-{run_id_suffix}``
    where ``safe_id`` is the indicator id with `.` and `_` replaced by `-`,
    and ``run_id_suffix`` is the last 12 chars of the run_id.

    We strip the prefix and the trailing 12-char suffix to recover the
    safe_id, then convert dashes BACK to dots (best effort — WB indicator ids
    use dots, not underscores, in the canonical form).
    """
    m = re.match(r"^qgi-fetch-(?P<body>.+)-(?P<suffix>[A-Za-z0-9]{12})$", job_name)
    if not m:
        return None
    safe_id = m.group("body")
    # World Bank indicator ids look like "FI.RES.TOTL.MO" — restore dots.
    return safe_id.replace("-", ".")


def _extract_indicator_ids(env_list: list[dict]) -> list[str]:
    """Return the list of indicator ids for the failed job.

    #241 Phase B: FAOSTAT tasks carry INDICATORS_JSON (a JSON array of
    indicator dicts, one per indicator in the domain). WB tasks carry
    a single INDICATOR_ID. Returns a list either way so the caller
    writes one tracker row per entry and decrements the counter by
    the full count.

    Priority order:
      1. INDICATORS_JSON (multi-indicator FAOSTAT-style tasks)
      2. INDICATOR_ID (legacy WB-style tasks)
      3. [] if neither is present (caller falls back to job-name parse)
    """
    indicators_json = _extract_env(env_list, "INDICATORS_JSON")
    if indicators_json:
        try:
            payload = json.loads(indicators_json)
            if isinstance(payload, list):
                ids = [str(i.get("id_string") or i) for i in payload if i is not None]
                ids = [i for i in ids if i and i != "None"]
                if ids:
                    return ids
        except (ValueError, TypeError) as exc:
            logger.warning(f"INDICATORS_JSON env var failed to parse: {exc}. Falling back to INDICATOR_ID.")

    single = _extract_env(env_list, "INDICATOR_ID")
    if single:
        return [single]
    return []


def lambda_handler(event: dict[str, Any], context):
    """Process one Batch JobStateChange=FAILED event."""
    detail = event.get("detail", {}) if isinstance(event, dict) else {}
    job_id = detail.get("jobId") or "unknown"
    job_name = detail.get("jobName") or ""
    status_reason = (detail.get("statusReason") or "")[:1000]

    # Container env carries the canonical indicator metadata + RUN_ID
    container = detail.get("container") or {}
    env_list = container.get("environment") or []
    indicator_ids = _extract_indicator_ids(env_list)
    # Final fallback: job-name parse. Only works for WB-style single-
    # indicator names (qgi-fetch-{safe_id}-{suffix}). FAOSTAT domain
    # jobs are named qgi-fetch-faostat-{domain}-{suffix} and won't
    # parse cleanly — but by this point INDICATORS_JSON or INDICATOR_ID
    # should have been present for FAOSTAT. This fallback is for
    # degraded cases where both env vars are missing on a WB job.
    if not indicator_ids:
        fallback = _parse_indicator_from_job_name(job_name)
        if fallback:
            indicator_ids = [fallback]

    provider = _extract_env(env_list, "PROVIDER") or "WB"
    run_id = _extract_env(env_list, "RUN_ID")

    if not run_id:
        logger.warning(
            f"Batch failure event missing RUN_ID env (job_name={job_name!r}, "
            f"job_id={job_id}). No tracker rows written. status_reason={status_reason!r}"
        )
        return {"status": "skipped", "reason": "no_run_id", "job_id": job_id}

    if not indicator_ids:
        logger.warning(
            f"Batch failure event missing both INDICATORS_JSON and INDICATOR_ID "
            f"for run_id={run_id} (job_name={job_name!r}, job_id={job_id}). "
            f"No tracker rows written — the Phase 1 counter may hang."
        )
        return {"status": "skipped", "reason": "no_indicator_ids", "job_id": job_id}

    # Classify the failure for the ops report. The reason text is whatever
    # Batch saw — we just preserve it and tag the high-level kind.
    # Case-insensitive because real Batch events use mixed case
    # ("Host EC2 was decommissioned", "OutOfMemoryError", etc.).
    reason_lower = status_reason.lower()
    if "duration exceeded timeout" in reason_lower:
        kind = "TIMEOUT"
    elif "host ec2" in reason_lower or "spot" in reason_lower:
        kind = "SPOT_RECLAIM"
    elif "outofmemory" in reason_lower or "oom" in reason_lower:
        kind = "OOM"
    else:
        kind = "BATCH_FAILED"

    # Write ONE tracker row per indicator so the checker's tracker_count
    # can reach total. For FAOSTAT domain tasks this can be N rows
    # from a single Batch failure event.
    now = int(time.time())
    written = 0
    for indicator_id in indicator_ids:
        item = {
            "run_id": run_id,
            "indicator_id": indicator_id,
            "status": "FAILED",
            "failure_kind": kind,
            "provider": provider,
            "timestamp": now,
            "expire_at": now + 30 * 24 * 60 * 60,
            "error": f"Batch hard failure: {status_reason}"[:1000],
            "job_id": job_id,
            "source": "batch_failure_handler",
        }
        try:
            tracker_table.put_item(Item=item)
            written += 1
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to write tracker row for {indicator_id}: {e}")
            # Keep going — partial write is better than none.

    logger.info(
        f"Wrote {written}/{len(indicator_ids)} FAILED tracker rows "
        f"(run_id={run_id}, kind={kind}, provider={provider}, "
        f"indicators={indicator_ids})"
    )

    # Decrement counter by the FULL indicator count (not the written
    # count, and not 1). The dispatcher seeded `pending = N_indicators`
    # regardless of how the indicators were grouped into tasks, so a
    # FAOSTAT domain task with 6 indicators MUST decrement by 6 even
    # if a couple of tracker writes failed.
    try:
        counter_table.update_item(
            Key={"run_id": run_id},
            UpdateExpression="ADD pending :neg",
            ExpressionAttributeValues={":neg": Decimal(-len(indicator_ids))},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Counter decrement failed for run_id={run_id} (wanted -{len(indicator_ids)}): {e} (non-fatal)")

    return {
        "status": "handled",
        "indicator_ids": indicator_ids,
        "indicator_count": len(indicator_ids),
        "tracker_rows_written": written,
        "run_id": run_id,
        "kind": kind,
        "provider": provider,
        "job_id": job_id,
    }
