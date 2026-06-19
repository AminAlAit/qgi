#!/usr/bin/env python3
"""
Phase 1 — Single-indicator fetcher (one Fargate Spot task per indicator).

This is the per-task script that replaces the legacy single-EC2 fetcher.
A dispatcher Lambda submits N AWS Batch jobs (one per active indicator),
Fargate Spot provisions each one independently, and each task runs this
script to fetch its single assigned indicator from the World Bank API.

## Why one task per indicator
1. **Rate limiting via natural distribution.** Each task sleeps a uniform
   random 60-300s before its API call, so 52 tasks spread their hits over
   ~5 minutes. Each Fargate Spot task has its OWN public IP, so WB sees
   them as 52 independent clients (per-IP rate limit, not per-task).
2. **Infinite scaling.** No SSM 1-hour cap, no single-process bottleneck.
3. **Fault isolation.** One failing indicator doesn't block the other 51.
4. **Cost.** Fargate Spot at 0.25 vCPU x 512 MB = ~$0.0008 per task.

## Architecture (#FAR-1)
  Dispatcher Lambda
    ├── reads indicators.json
    ├── PutItem qgi-pipeline-a-counter (run_id, pending=N)
    └── for each indicator: SubmitJob with INDICATOR_ID env var
                                                |
                                                v
  Fargate Spot task (this script)
    1. Random sleep 60-300s (rate limit jitter)
    2. WB API fetch with 10x exponential backoff
    3. Country mapping + transform
    4. Hash compare against existing parquet metadata
    5. If unchanged: skip upload, mark UNCHANGED
    6. If changed: upload to S3 + register Glue partition
    7. Mirror values to qgi-indicator-values DDB (#148)
    8. Write status row to qgi-indicator-updates
    9. Decrement qgi-pipeline-a-counter (ALWAYS, even on failure)

## Fault tolerance layers
- L1 (in-script): 10 exponential backoff retries on the WB API call
- L2 (Batch retry): job def attempts=2, Batch resubmits on container exit
  != 0 OR Fargate Spot reclaim
- L3 (graceful degradation): final exception catches, writes FAILED row,
  decrements counter, exits 0 — pipeline does not hang
- L4 (ops report): qgi-indicator-updates rows surfaced in Phase 6
- L5 (Step Function deadman): checker Lambda gives up after 90 min wall
"""

import hashlib
import json
import logging
import os
import random
import sys
import time
import traceback
from decimal import Decimal
from io import BytesIO, StringIO

import boto3
import pandas as pd
import wbgapi as wb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment (set by the Batch job definition / dispatcher)
# ---------------------------------------------------------------------------

REGION = os.environ.get("AWS_REGION", "eu-central-1")
BUCKET = os.environ["S3_BUCKET"]
INDICATOR_ID = os.environ["INDICATOR_ID"]
RUN_ID = os.environ["RUN_ID"]

# DynamoDB tables
COUNTER_TABLE = os.environ.get("COUNTER_TABLE", "qgi-pipeline-a-counter")
TRACKER_TABLE = os.environ.get("TRACKER_TABLE", "qgi-indicator-updates")
INDICATOR_VALUES_TABLE = os.environ.get("INDICATOR_VALUES_TABLE", "qgi-indicator-values")

# Athena (for #149 partition registration)
ATHENA_DATABASE = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
# #416 — ATHENA_OUTPUT_LOCATION removed; workgroup enforces its own location.
INDICATORS_TABLE_NAME = "indicators"

# Rate-limit jitter window (seconds). Each task sleeps a uniform random
# value in this range before making its first WB API call.
JITTER_MIN_S = int(os.environ.get("JITTER_MIN_S", "60"))
JITTER_MAX_S = int(os.environ.get("JITTER_MAX_S", "300"))

# In-script retry budget for the WB API call
MAX_FETCH_ATTEMPTS = int(os.environ.get("MAX_FETCH_ATTEMPTS", "10"))

# S3 layout
S3_INPUT_PREFIX = "pipeline-A-indicator-extractor/input"
S3_OUTPUT_PREFIX = "pipeline-A-indicator-extractor/output"
# #413 — countries.csv moved to a dedicated prefix after #370 (Glue
# table pollution fix). Keep S3_INPUT_PREFIX untouched — other Phase 1
# indicator-map files still live there and this container reads them.
COUNTRIES_CSV_KEY = "pipeline-A-indicator-extractor/countries/countries.csv"

# ---------------------------------------------------------------------------
# Boto3 clients (created once per container, reused)
# ---------------------------------------------------------------------------

s3 = boto3.client("s3", region_name=REGION)
dynamodb_resource = boto3.resource("dynamodb", region_name=REGION)
athena = boto3.client("athena", region_name=REGION)

counter_table = dynamodb_resource.Table(COUNTER_TABLE)
tracker_table = dynamodb_resource.Table(TRACKER_TABLE)
indicator_values_table = dynamodb_resource.Table(INDICATOR_VALUES_TABLE)


# ---------------------------------------------------------------------------
# Country mapping (loaded lazily, once)
# ---------------------------------------------------------------------------

_country_mapping = None


def get_country_mapping():
    """Load the WB-economy → canonical-country-name lookup from S3.

    The countries.csv has multiple name columns (name_1 is canonical,
    others are aliases). We build a flat map from every alias to name_1.
    """
    global _country_mapping
    if _country_mapping is not None:
        return _country_mapping

    logger.info(f"Loading country mapping from s3://{BUCKET}/{COUNTRIES_CSV_KEY}")
    obj = s3.get_object(Bucket=BUCKET, Key=COUNTRIES_CSV_KEY)
    df = pd.read_csv(StringIO(obj["Body"].read().decode("utf-8")))
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
    if "name_1" not in df.columns:
        raise ValueError("countries.csv missing 'name_1' column")

    mapping = {}
    for col in df.columns:
        if col != "name_1":
            temp = df.dropna(subset=[col]).set_index(col)["name_1"].to_dict()
            mapping.update(temp)
    _country_mapping = mapping
    return mapping


# ---------------------------------------------------------------------------
# WB API fetch with exponential backoff (L1 retry layer)
# ---------------------------------------------------------------------------


class IndicatorNotFound(Exception):
    """Permanent error — the WB API returned an XML 'Data not found' body for
    this indicator/source pair. Retrying is pointless; the indicator id is
    either retired, moved to a different source database, or simply wrong.
    """


def fetch_with_retry(indicator_id):
    """10-attempt exponential backoff fetch from World Bank.

    Backoff schedule (seconds): 2, 4, 8, 16, 32, 60, 60, 60, 60, 60.
    Capped at 60s to keep tail latency bounded but still respect rate limits.

    Fail-fast on permanent errors:
    - The WB API returns HTTP 200 with an XML <wb:error> body when the
      requested indicator is not in the queried source. wbgapi blindly
      JSON-decodes the XML and raises ``APIResponseError: JSON decoding
      error``. Retrying that wastes 4+ minutes of Fargate time per task
      and drowns out real transient errors. We detect the "JSON decoding
      error" signature and abort immediately as IndicatorNotFound, which
      the caller maps to a clean FAILED tracker row with a clear cause.
    """
    last_err = None
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            logger.info(f"Fetching {indicator_id} (attempt {attempt}/{MAX_FETCH_ATTEMPTS})")
            return wb.data.DataFrame(indicator_id)
        except Exception as e:  # noqa: BLE001
            last_err = e
            # Permanent error — bail immediately, don't burn retry budget.
            if "JSON decoding error" in str(e):
                logger.error(
                    f"{indicator_id}: WB API returned XML error body (likely "
                    f"retired or wrong source). Failing fast — no retry."
                )
                raise IndicatorNotFound(
                    f"{indicator_id}: not found in WB source 2 (WDI). "
                    f"The id may have been retired, moved to another source, "
                    f"or be misspelled. Original: {e}"
                ) from e
            if attempt == MAX_FETCH_ATTEMPTS:
                logger.error(f"Final attempt failed for {indicator_id}: {e}")
                raise
            # Exponential backoff with cap (#175: 2x more generous)
            wait = min(120, 2 ** (attempt + 1))
            logger.warning(f"Attempt {attempt} failed for {indicator_id} ({e}); sleeping {wait}s before retry")
            time.sleep(wait)
    # Unreachable
    raise last_err  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Status writers
# ---------------------------------------------------------------------------


def write_tracker(indicator_id, status, error=None):
    """Write a status row to qgi-indicator-updates for the ops report (L4)."""
    item = {
        "run_id": RUN_ID,
        "indicator_id": indicator_id,
        "status": status,
        "timestamp": int(time.time()),
        "expire_at": int(time.time()) + 30 * 24 * 60 * 60,
    }
    if error:
        item["error"] = error[:1000]  # cap to keep DDB item small
    try:
        tracker_table.put_item(Item=item)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to write tracker for {indicator_id}: {e}")
        # Tracker write failure is not fatal — keep going


def decrement_counter():
    """Atomically decrement qgi-pipeline-a-counter for this run.

    Called on success AND on graceful failure so the pipeline doesn't hang.
    Idempotent within a single task because it's only called once at the
    very end.
    """
    try:
        counter_table.update_item(
            Key={"run_id": RUN_ID},
            UpdateExpression="ADD pending :neg",
            ExpressionAttributeValues={":neg": Decimal(-1)},
            ReturnValues="UPDATED_NEW",
        )
        logger.info(f"Decremented counter for run_id={RUN_ID}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to decrement counter: {e}")
        # Don't re-raise — the checker Lambda has the deadman timer (L5)


# ---------------------------------------------------------------------------
# Glue partition register (#149)
# ---------------------------------------------------------------------------


def register_glue_partition(indicator_id):
    """Register this indicator's partition with Glue via Athena ALTER TABLE.

    The qgi_data.indicators table is partitioned by indicator_id with a
    bare (non-Hive) S3 layout (parquet/{INDICATOR_ID}/...), so MSCK REPAIR
    can't discover new partitions automatically. We do it explicitly here.
    Same pattern as #149's pipeline-a-worker logic.

    Best-effort: failures are logged but don't fail the task. The Phase 1.5
    completer also re-registers as a safety net.
    """
    partition_location = f"s3://{BUCKET}/{S3_OUTPUT_PREFIX}/parquet/{indicator_id}/"
    sql = (
        f"ALTER TABLE {ATHENA_DATABASE}.{INDICATORS_TABLE_NAME} "
        f"ADD IF NOT EXISTS PARTITION (indicator_id='{indicator_id}') "
        f"LOCATION '{partition_location}'"
    )
    try:
        # #416 — ResultConfiguration omitted; workgroup enforces its own
        # OutputLocation. See #371 for the failure class this avoids.
        response = athena.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": ATHENA_DATABASE},
            WorkGroup=ATHENA_WORKGROUP,
        )
        query_id = response["QueryExecutionId"]
        # Poll briefly — ALTER TABLE is fast
        for _ in range(20):
            status = athena.get_query_execution(QueryExecutionId=query_id)
            state = status["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                logger.info(f"Glue partition registered: {indicator_id}")
                return
            if state in ("FAILED", "CANCELLED"):
                reason = status["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
                logger.warning(f"ALTER TABLE failed for {indicator_id}: {reason}")
                return
            time.sleep(0.5)
        logger.warning(f"ALTER TABLE timed out for {indicator_id}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Glue partition register exception for {indicator_id}: {e}")


# ---------------------------------------------------------------------------
# DDB mirror (#148)
# ---------------------------------------------------------------------------


def mirror_to_ddb(df, indicator_id):
    """Mirror this indicator's values to qgi-indicator-values DDB.

    Same logic as #148 in pipeline-a-completer but for the raw (not
    completed) values. The completer will mirror its own completed values
    later — these are the original WB data points.

    Idempotent via overwrite_by_pkeys. Best-effort: failures log but
    don't fail the task.
    """
    items = []
    for row in df.itertuples(index=False):
        country = str(row.country) if row.country is not None else None
        if not country:
            continue
        try:
            year_int = int(row.year)
            value_float = float(row.value)
        except (TypeError, ValueError):
            continue
        if value_float != value_float:  # NaN check
            continue
        items.append(
            {
                "indicator_country": f"{indicator_id}#{country}",
                "year": year_int,
                "value": Decimal(format(value_float, ".6g")),
            }
        )

    if not items:
        return 0

    written = 0
    try:
        with indicator_values_table.batch_writer(overwrite_by_pkeys=["indicator_country", "year"]) as batch:
            for item in items:
                batch.put_item(Item=item)
                written += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(f"DDB mirror partial failure for {indicator_id}: {e}")
    return written


# ---------------------------------------------------------------------------
# Main per-task workflow
# ---------------------------------------------------------------------------


def process_indicator(indicator_id):
    """Run the full pipeline for a single indicator.

    Returns the final status string (UPDATED, UNCHANGED, SKIPPED, FAILED).
    Caller is responsible for the counter decrement and tracker write.
    """
    # 1. Fetch from WB
    raw_df = fetch_with_retry(indicator_id)
    if raw_df.empty:
        logger.info(f"{indicator_id}: empty WB response, marking SKIPPED")
        return "SKIPPED", None

    # 2. Transform to long format with canonical country names
    mapping = get_country_mapping()
    df = raw_df.dropna(axis="columns", how="all").copy()
    df["economy"] = df.index
    df_long = pd.melt(df, id_vars=["economy"], var_name="year", value_name="value")
    df_long["year"] = df_long["year"].str.extract(r"(\d+)").astype(int)
    df_long = df_long.rename(columns={"economy": "country"})
    df_long["country"] = df_long["country"].map(mapping).fillna(df_long["country"])
    canonical = set(mapping.values())
    df_long = df_long[df_long["country"].isin(canonical)]
    final_df = df_long.dropna(subset=["value"]).sort_values(by=["country", "year"])

    # 3. Hash check vs existing parquet metadata
    csv_str = final_df.to_csv(index=False)
    new_hash = hashlib.md5(csv_str.encode("utf-8")).hexdigest()
    output_key = f"{S3_OUTPUT_PREFIX}/parquet/{indicator_id}/{indicator_id}.parquet"

    existing_hash = None
    try:
        head = s3.head_object(Bucket=BUCKET, Key=output_key)
        existing_hash = head["Metadata"].get("content_hash")
    except Exception:
        pass

    if existing_hash == new_hash:
        logger.info(f"{indicator_id}: data unchanged (hash match)")
        return "UNCHANGED", final_df

    # 4. Upload parquet
    logger.info(f"{indicator_id}: data changed, uploading parquet")
    parquet_buffer = BytesIO()
    final_df.to_parquet(parquet_buffer, index=False, engine="pyarrow", compression="snappy")
    s3.put_object(
        Bucket=BUCKET,
        Key=output_key,
        Body=parquet_buffer.getvalue(),
        Metadata={"content_hash": new_hash},
    )

    # 5. Register the Glue partition (#149)
    register_glue_partition(indicator_id)

    return "UPDATED", final_df


def main():
    logger.info(f"=== Phase 1 fetcher task starting === indicator={INDICATOR_ID} run_id={RUN_ID}")

    # ── Step 0: jitter sleep (rate-limit primitive) ──────────────────────
    jitter = random.uniform(JITTER_MIN_S, JITTER_MAX_S)
    logger.info(f"Jitter sleep: {jitter:.1f}s before WB API call")
    time.sleep(jitter)

    # ── Step 1: process the indicator ────────────────────────────────────
    status = "FAILED"
    error_msg = None
    final_df = None
    try:
        status, final_df = process_indicator(INDICATOR_ID)
    except Exception as e:  # noqa: BLE001
        status = "FAILED"
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"{INDICATOR_ID}: FAILED — {error_msg}")
        logger.error(traceback.format_exc())

    # ── Step 2: mirror values to DDB (#148) — only on UPDATED/UNCHANGED ──
    if final_df is not None and status in ("UPDATED", "UNCHANGED"):
        try:
            n = mirror_to_ddb(final_df, INDICATOR_ID)
            logger.info(f"{INDICATOR_ID}: mirrored {n} items to DDB")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"{INDICATOR_ID}: DDB mirror failed: {e}")

    # ── Step 3: write tracker row (L4) ───────────────────────────────────
    write_tracker(INDICATOR_ID, status, error=error_msg)

    # ── Step 4: decrement counter (always, even on failure) ──────────────
    decrement_counter()

    logger.info(f"=== Phase 1 fetcher task finished === indicator={INDICATOR_ID} status={status}")

    # Always exit 0 — Batch retries are reserved for infrastructure failures
    # (Fargate Spot reclaim, container OOM, etc.) where this script never
    # runs to completion. Application-level failures are surfaced via the
    # FAILED tracker row + counter decrement, not via process exit code.
    sys.exit(0)


if __name__ == "__main__":
    main()
