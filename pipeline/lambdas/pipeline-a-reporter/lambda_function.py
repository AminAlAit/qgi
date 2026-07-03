"""
Phase 1 Reporter (#FAR-1)

Sends a detailed end-of-Phase-1 email summary via SNS. The legacy
version was a 4-line totals dump; this is a multi-section breakdown
showing every indicator's status, the run duration, the failure
threshold check (#FAR-1: >20% = alarm), and any deadman trip.

The Step Function fires this Lambda after the checker reports done=True
(or deadman_expired=True). It returns the updated indicator id list so
the downstream branching (Updates Found?) still works the same way.

## Email format
  Subject: QGI Phase 1 Report — <run_id> — <K> updates, <F> failures
  Body:    multi-section markdown text with totals + failed list +
           updated list + freshness/deadman/threshold flags

The SNS topic must already be wired to an email subscription on Amin's
inbox (the topic ARN comes from qgi-infra storage module's
pipeline_notifications topic).
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")
s3 = boto3.client("s3")

# T11 #304 MEDIUM fix (2026-04-19): externalize tracker table name via
# env var so staging/qa/prod can point at different DDB tables. Default
# preserves existing legacy-account behavior.
TABLE_NAME = os.environ.get("TRACKER_TABLE", "qgi-indicator-updates")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
MANIFEST_KEY = os.environ.get("MANIFEST_KEY", "indicator-freshness/latest-fetch-manifest.json")
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]

# #FAR-1: failure threshold for the loud alarm. >20% failed = alarm in
# the email subject + body. Pipeline still continues to Phase 2.
FAILURE_THRESHOLD_PCT = float(os.environ.get("FAILURE_THRESHOLD_PCT", "20.0"))


def lambda_handler(event, context):
    run_id = event.get("run_id")
    if not run_id:
        return {"status": "Error", "message": "No run_id provided"}

    # The checker passes through deadman_expired=True if the L5 timer fired
    deadman_expired = bool(event.get("deadman_expired", False))
    pending_at_finish = event.get("pending", 0)
    total_dispatched = event.get("total", 0)

    table = dynamodb.Table(TABLE_NAME)

    # 1. Pull every indicator status row for this run
    response = table.query(KeyConditionExpression=Key("run_id").eq(run_id))
    items = response["Items"]
    # Handle pagination for runs with > 1MB of items
    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("run_id").eq(run_id),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response["Items"])

    # 2. Bucket by status
    by_status = {"UPDATED": [], "UNCHANGED": [], "SKIPPED": [], "FAILED": []}
    for item in items:
        status = item.get("status", "UNKNOWN")
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(item)

    updated = sorted(i["indicator_id"] for i in by_status["UPDATED"])
    unchanged = sorted(i["indicator_id"] for i in by_status["UNCHANGED"])
    skipped = sorted(i["indicator_id"] for i in by_status["SKIPPED"])
    failed = sorted(i["indicator_id"] for i in by_status["FAILED"])
    failed_with_errors = [
        (i["indicator_id"], i.get("error", "(no error message captured)")) for i in by_status["FAILED"]
    ]

    total_processed = len(items)
    total_failed = len(failed)
    failure_rate = (total_failed / total_processed * 100) if total_processed else 0
    alarm_triggered = failure_rate > FAILURE_THRESHOLD_PCT

    # 3. Build the email body
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    subject = f"QGI Phase 1 — {run_id} — {len(updated)} updated, {total_failed} failed"
    if alarm_triggered:
        subject = f"⚠ ALARM ({failure_rate:.0f}% failures) — {subject}"
    if deadman_expired:
        subject = f"⚠ DEADMAN — {subject}"

    lines = []
    lines.append("=" * 70)
    lines.append("QGI MONTHLY PIPELINE — PHASE 1 COMPLETE")
    lines.append(f"Run ID: {run_id}")
    lines.append(f"Report time: {now_iso}")
    lines.append("=" * 70)
    lines.append("")

    if deadman_expired:
        lines.append("⚠ DEADMAN TIMER FIRED")
        lines.append(
            f"  The Phase 1 checker gave up waiting for {pending_at_finish} of "
            f"{total_dispatched} indicators after the deadman timeout. The "
            f"missing indicators may still be running in Batch — check the "
            f"Batch console for run_id={run_id}."
        )
        lines.append("")

    if alarm_triggered:
        lines.append("⚠ FAILURE RATE ALARM")
        lines.append(
            f"  {total_failed}/{total_processed} indicators failed = "
            f"{failure_rate:.1f}% (threshold: {FAILURE_THRESHOLD_PCT:.0f}%)"
        )
        lines.append("  Pipeline will continue to Phase 2 with the surviving set.")
        lines.append("")

    lines.append("SUMMARY")
    lines.append("-" * 70)
    lines.append(f"  Total processed:  {total_processed}")
    lines.append(f"  Updated:          {len(updated)}")
    lines.append(f"  Unchanged:        {len(unchanged)}")
    lines.append(f"  Skipped (empty):  {len(skipped)}")
    lines.append(f"  Failed:           {total_failed}")
    if total_processed > 0:
        lines.append(f"  Failure rate:     {failure_rate:.1f}%")
    lines.append("")

    if failed_with_errors:
        lines.append("FAILED INDICATORS")
        lines.append("-" * 70)
        for ind_id, err in failed_with_errors:
            lines.append(f"  ✗ {ind_id}")
            # Truncate long errors but keep structure visible
            err_lines = err.splitlines() if isinstance(err, str) else [str(err)]
            for el in err_lines[:3]:
                lines.append(f"      {el[:200]}")
            if len(err_lines) > 3:
                lines.append(f"      … ({len(err_lines) - 3} more lines)")
        lines.append("")

    if updated:
        lines.append(f"UPDATED INDICATORS ({len(updated)})")
        lines.append("-" * 70)
        # Group 4 per line for compactness
        for i in range(0, len(updated), 4):
            chunk = updated[i : i + 4]
            lines.append("  " + ",  ".join(f"{x:25}" for x in chunk).rstrip())
        lines.append("")
    else:
        lines.append("UPDATED INDICATORS")
        lines.append("-" * 70)
        lines.append("  (none — Phase 2 SCDI compute will NOT run on new data)")
        lines.append("")

    if unchanged:
        lines.append(f"UNCHANGED INDICATORS ({len(unchanged)})")
        lines.append("-" * 70)
        for i in range(0, len(unchanged), 4):
            chunk = unchanged[i : i + 4]
            lines.append("  " + ",  ".join(f"{x:25}" for x in chunk).rstrip())
        lines.append("")

    if skipped:
        lines.append(f"SKIPPED INDICATORS ({len(skipped)})")
        lines.append("-" * 70)
        lines.append("  (these returned empty data from World Bank)")
        for i in range(0, len(skipped), 4):
            chunk = skipped[i : i + 4]
            lines.append("  " + ",  ".join(f"{x:25}" for x in chunk).rstrip())
        lines.append("")

    lines.append("=" * 70)
    lines.append(
        "Pipeline will now advance to Phase 1.5 (indicator completion) + Phase 2 (SCDI compute on Batch Spot)."
    )
    lines.append("=" * 70)

    body = "\n".join(lines)
    logger.info(
        f"Reporter publishing: {total_processed} processed, {total_failed} failed, "
        f"alarm={alarm_triggered}, deadman={deadman_expired}"
    )

    sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject[:99], Message=body)

    # #175: write fetch manifest to S3 so the decoupled Main SF can read it
    # via the manifest-reader Lambda instead of re-running the Fargate fetch.
    if S3_BUCKET:
        now_iso = datetime.now(timezone.utc).isoformat()
        manifest = {
            "run_id": run_id,
            "timestamp": now_iso,
            "updated_ids": updated,
            "updated_count": len(updated),
            "total_fetched": total_processed,
            "failed_ids": failed,
            "all_indicator_ids": sorted(set(updated + unchanged + skipped + failed)),
        }
        try:
            s3.put_object(
                Bucket=S3_BUCKET,
                Key=MANIFEST_KEY,
                Body=json.dumps(manifest, indent=2),
                ContentType="application/json",
            )
            logger.info(f"Fetch manifest written to s3://{S3_BUCKET}/{MANIFEST_KEY}")
        except Exception:
            logger.exception("Failed to write fetch manifest (non-fatal)")

    return {
        "status": "Complete",
        "updated_count": len(updated),
        "updated_ids": updated,
        "failed_count": total_failed,
        "alarm_triggered": alarm_triggered,
        "deadman_expired": deadman_expired,
    }
