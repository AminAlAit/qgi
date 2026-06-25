"""
Phase 4 completion checker.

Called by Step Functions in a poll loop instead of the hard 60-min wait.
Primary signal: processed_c DynamoDB counter.
Fallback signal: count of S3 partition prefixes written by c-worker.
  Used when the counter stalls (DynamoDB throttle under burst) but the queue
  is fully drained — avoids indefinite stall without manual intervention.

Input:  {"run_id": "<run_id>", "expected": <int>}
Output: {"done": true/false, "processed": <int>, "total": <int>, "source": "counter"|"s3_fallback"}
"""

import boto3
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
TABLE_NAME = os.environ["COMPLETION_TABLE"]
S3_BUCKET = os.environ["S3_BUCKET"]
PATTERNS_S3_PREFIX = "pipeline-C-pattern-synthesizer/output/data/"


def _count_s3_partitions(bucket, prefix):
    """Count distinct country_a_id= partition prefixes written by c-worker."""
    paginator = s3_client.get_paginator("list_objects_v2")
    partitions = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            partitions.add(cp["Prefix"])
    return len(partitions)


def lambda_handler(event, context):
    run_id = event["run_id"]
    expected = int(event["expected"])

    table = dynamodb.Table(TABLE_NAME)
    item = table.get_item(Key={"run_id": run_id}).get("Item", {})
    processed = int(item.get("processed_c", 0))

    if processed >= expected:
        logger.info(f"run_id={run_id} processed={processed}/{expected} done=True source=counter")
        return {"done": True, "processed": processed, "total": expected, "source": "counter"}

    # Fallback: if counter is behind but S3 partition count has reached expected,
    # the workers all completed successfully — DynamoDB writes just failed silently
    # (bug documented in #108; fixed by re-raising, but this guard remains for safety).
    s3_count = _count_s3_partitions(S3_BUCKET, PATTERNS_S3_PREFIX)
    if s3_count >= expected:
        logger.warning(
            f"run_id={run_id} counter stale ({processed}/{expected}) but "
            f"S3 partitions={s3_count} >= expected={expected} — marking done via S3 fallback"
        )
        return {"done": True, "processed": s3_count, "total": expected, "source": "s3_fallback"}

    logger.info(f"run_id={run_id} processed={processed}/{expected} s3_partitions={s3_count} done=False")
    return {"done": False, "processed": processed, "total": expected, "source": "counter"}
