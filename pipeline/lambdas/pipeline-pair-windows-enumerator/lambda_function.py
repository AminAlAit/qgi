"""
pipeline-pair-windows-enumerator (#369)

Phase 5b.10b: AFTER 5b.10a has created the ``pair_windows_staging``
Parquet table, enumerate its distinct ``country_a_id`` values and
write the items array to S3 for the 5b.10c Distributed Map state.

Produces a thin payload (~1KB response) with an S3 pointer to the
items file — follows the same Map ItemReader pattern as 5b.3
``pipeline-recipe-engine-list-formatter``.

Input event:
    {"run_id": "<sf-execution-name>"}

Output:
    {
        "items_bucket": "qgi-data-lake-<acct>",
        "items_key":    "tmp/pair-windows-items-<run_id>.json",
        "country_a_count": <int>
    }

Env vars:
    S3_BUCKET                — data-lake bucket (required)
    ATHENA_DATABASE          — defaults to "qgi_data"
    ATHENA_WORKGROUP         — defaults to "QGI-Lambda-Workgroup"
    ATHENA_OUTPUT_LOCATION   — s3://.../query_results/ (optional)
"""

import json
import logging
import os
import time

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ["S3_BUCKET"]
ATHENA_DB = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WG = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
# #371 — ATHENA_OUTPUT_LOCATION removed; workgroup enforces its own output location.

athena = boto3.client("athena")
s3 = boto3.client("s3")


def _run_query_sync(sql: str) -> str:
    """Start an Athena query and poll until SUCCEEDED. Returns QueryExecutionId.

    Raises on FAILED / CANCELLED. Poll interval is short (2s) because
    the enumerate query is cheap — should finish within a few seconds.
    """
    # #371 — ResultConfiguration intentionally omitted; QGI-Lambda-Workgroup has
    # EnforceWorkGroupConfiguration=true and supplies its own OutputLocation.
    # Passing one here only works when it matches the workgroup's value
    # exactly — a latent sync-or-crash trap (same failure class as #369 Fix 7).
    kwargs = {
        "QueryString": sql,
        "QueryExecutionContext": {"Database": ATHENA_DB},
        "WorkGroup": ATHENA_WG,
    }

    qid = athena.start_query_execution(**kwargs)["QueryExecutionId"]
    logger.info(f"Athena query {qid} started: {sql[:80]}...")

    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            return qid
        if state in ("FAILED", "CANCELLED"):
            reason = status.get("StateChangeReason", "unknown")
            raise RuntimeError(f"Athena query {qid} {state}: {reason}")
        time.sleep(2)


def lambda_handler(event, context):
    run_id = event.get("run_id", "unknown")
    logger.info(f"pair-windows-enumerator starting. run_id={run_id}")

    # Small safe query: 214ish rows, single column, no aggregation.
    qid = _run_query_sync(f"SELECT DISTINCT country_a_id FROM {ATHENA_DB}.pair_windows_staging ORDER BY 1")

    # Paginate in case of >1000 countries (never today, but defensive).
    country_a_ids: list[str] = []
    next_token = None
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if next_token:
            kw["NextToken"] = next_token
        resp = athena.get_query_results(**kw)
        rows = resp["ResultSet"]["Rows"]
        # Header row only appears on first page.
        start = 1 if next_token is None else 0
        for row in rows[start:]:
            cell = row["Data"][0]
            # Athena returns empty dict {} for nulls — skip those.
            if "VarCharValue" in cell and cell["VarCharValue"].strip():
                country_a_ids.append(cell["VarCharValue"])
        next_token = resp.get("NextToken")
        if not next_token:
            break

    # Each item carries country_a_id + bucket, so the Map child has
    # everything it needs without re-reading state.
    items = [{"country_a_id": cid, "bucket": S3_BUCKET, "run_id": run_id} for cid in country_a_ids]

    items_key = f"tmp/pair-windows-items-{run_id}.json"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=items_key,
        Body=json.dumps(items).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info(f"Wrote {len(items)} items to s3://{S3_BUCKET}/{items_key}")

    return {
        "items_bucket": S3_BUCKET,
        "items_key": items_key,
        "country_a_count": len(items),
    }
