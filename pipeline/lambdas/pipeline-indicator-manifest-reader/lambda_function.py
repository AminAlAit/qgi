"""
Phase 1 manifest reader (#175 — decoupled indicator fetching).

Reads the fetch manifest from S3 (written by the separate Fetch SF's
reporter step) and returns it for the Main SF to route through. This
replaces the old Fargate dispatch + poll + reporter chain in the Main SF
with a single < 1 second S3 read.

The manifest contains:
  - updated_ids: indicators that changed in the last fetch
  - updated_count: len(updated_ids)
  - all_indicator_ids: every indicator that was processed (regardless of change)
  - run_id, timestamp, total_fetched, failed_ids

When `force_full_run=true` is passed in the event, `updated_ids` is
replaced with `all_indicator_ids` so Phase 2 dispatches SCDI Batch jobs
for every indicator, not just the changed ones.

Output is written to `$.reporter_result` by the SF so all downstream
states (1g Completer, 1h Updates Found?, 2a SCDI Dispatch) work
unchanged — they already reference `$.reporter_result.updated_ids`.
"""

import os
import json
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get("S3_BUCKET")
MANIFEST_KEY = os.environ.get("MANIFEST_KEY", "indicator-freshness/latest-fetch-manifest.json")

s3 = boto3.client("s3")


def lambda_handler(event, context):
    force_full_run = event.get("force_full_run", False)

    logger.info(f"Manifest reader starting. bucket={S3_BUCKET}, key={MANIFEST_KEY}, force_full_run={force_full_run}")

    # Read manifest from S3
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=MANIFEST_KEY)
        manifest = json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            raise RuntimeError(
                f"Fetch manifest not found at s3://{S3_BUCKET}/{MANIFEST_KEY}. "
                f"Run the qgi-indicator-data-refresher Step Function first to "
                f"populate the manifest, then retry the main pipeline."
            ) from e
        raise

    updated_ids = manifest.get("updated_ids", [])
    all_ids = manifest.get("all_indicator_ids", [])
    run_id = manifest.get("run_id", "unknown")
    timestamp = manifest.get("timestamp", "unknown")

    if force_full_run:
        logger.info(
            f"force_full_run=true: overriding updated_ids ({len(updated_ids)}) with all_indicator_ids ({len(all_ids)})"
        )
        updated_ids = all_ids

    result = {
        "status": "Complete",
        "updated_ids": updated_ids,
        "updated_count": len(updated_ids),
        "all_indicator_ids": all_ids,
        "run_id": run_id,
        "timestamp": timestamp,
        "total_fetched": manifest.get("total_fetched", 0),
        "failed_ids": manifest.get("failed_ids", []),
        "failed_count": len(manifest.get("failed_ids", [])),
        "manifest_source": f"s3://{S3_BUCKET}/{MANIFEST_KEY}",
        "force_full_run": force_full_run,
    }

    logger.info(
        f"Manifest read: {result['updated_count']} updated indicators "
        f"(of {len(all_ids)} total) from fetch run {run_id} at {timestamp}"
    )

    return result
