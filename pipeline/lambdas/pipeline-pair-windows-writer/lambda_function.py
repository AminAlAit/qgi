"""
pipeline-pair-windows-writer (#369)

Phase 5b.10c Distributed Map child: reads one ``country_a_id``'s
partition from the ``pair_windows_staging`` Parquet table (already
top-200-filtered by the 5b.10a CTAS), builds the per-partner JSON
blob matching the existing contract, and writes it to
``s3://<bucket>/dashboard/pair-windows/{country_a_id}.json``.

Replaces the streaming path inside the legacy
``pipeline-pair-windows-generator`` Lambda, which couldn't finish
within the 900s Lambda ceiling once the patterns table got past
~1B rows.

Output contract (UNCHANGED from legacy):
    {
      "<country_b_id>": {
        "top": [
          {"l": 30, "sa": 1997, "sb": 1997, "ic": 26,
           "ac": 0.843, "pps": 657.5},
          ...  (up to 200 entries, sorted pps desc)
        ],
        "hist": {"3": 120, "4": 340, ...}
      },
      ...
    }

Short-key legend: l=length, sa=start_year_a, sb=start_year_b,
ic=indicator_count, ac=avg_correlation, pps=pattern_power_score.

Input event (from Distributed Map per-item):
    {
        "country_a_id": "34",
        "bucket":       "qgi-data-lake-<acct>",
        "run_id":       "<sf-execution-name>"
    }

Env vars:
    ATHENA_DATABASE        — defaults to "qgi_data"
    ATHENA_WORKGROUP       — defaults to "QGI-Lambda-Workgroup"
    ATHENA_OUTPUT_LOCATION — s3://.../query_results/ (optional)
"""

import json
import logging
import os
import time
from collections import defaultdict

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ATHENA_DB = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WG = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
# #371 — ATHENA_OUTPUT_LOCATION removed; workgroup enforces its own output location.

DASHBOARD_PREFIX = "dashboard/pair-windows"

athena = boto3.client("athena")
s3 = boto3.client("s3")


# ---------------------------------------------------------------------------
# Athena helpers
# ---------------------------------------------------------------------------


def _run_query_sync(sql: str) -> str:
    """Start an Athena query and poll until SUCCEEDED. Returns QueryExecutionId.

    Per-country partition scans on the Parquet staging table are fast
    (<10s typical). Poll interval 1s.
    """
    # #371 — ResultConfiguration omitted; workgroup enforces its own location.
    # See #369 Fix 7 for the failure class this pattern avoids.
    kwargs = {
        "QueryString": sql,
        "QueryExecutionContext": {"Database": ATHENA_DB},
        "WorkGroup": ATHENA_WG,
    }

    qid = athena.start_query_execution(**kwargs)["QueryExecutionId"]

    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            return qid
        if state in ("FAILED", "CANCELLED"):
            reason = status.get("StateChangeReason", "unknown")
            raise RuntimeError(f"Athena query {qid} {state}: {reason}")
        time.sleep(1)


# ---------------------------------------------------------------------------
# Type coercion (match legacy Lambda exactly for backward-compatible output)
# ---------------------------------------------------------------------------


def _to_int(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def lambda_handler(event, context):
    a_id = str(event["country_a_id"])
    bucket = event["bucket"]
    run_id = event.get("run_id", "manual")
    logger.info(f"pair-windows-writer: country_a_id={a_id} run_id={run_id}")

    # Read this country_a's partition. The CTAS already applied
    # ROW_NUMBER top-200 per pair, so we just need to pull this
    # country's rows and group by country_b. Ordered by pps desc so
    # we preserve order when accumulating.
    sql = (
        f"SELECT country_b_id, length, start_year_a, start_year_b, "
        f"indicator_count, avg_correlation, pattern_power_score "
        f"FROM {ATHENA_DB}.pair_windows_staging "
        f"WHERE country_a_id = {a_id} "
        f"ORDER BY country_b_id, pattern_power_score DESC"
    )
    qid = _run_query_sync(sql)

    # Paginate through results. Bounded per child: up to 214 partners
    # × 200 rows = ~42,800 rows max. Easily fits in memory + time.
    headers: list[str] | None = None
    next_token: str | None = None
    pairs_buf: dict[str, list[dict]] = defaultdict(list)
    total_rows = 0

    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if next_token:
            kw["NextToken"] = next_token
        resp = athena.get_query_results(**kw)
        rows = resp["ResultSet"]["Rows"]

        if headers is None:
            headers = [c.get("VarCharValue", "") for c in rows[0]["Data"]]
            data_rows = rows[1:]
        else:
            data_rows = rows

        for raw in data_rows:
            cells = raw.get("Data", [])
            row = {headers[i]: cells[i].get("VarCharValue", "") if i < len(cells) else "" for i in range(len(headers))}
            total_rows += 1
            b_id = row["country_b_id"]
            pairs_buf[b_id].append(
                {
                    "l": _to_int(row["length"]),
                    "sa": _to_int(row["start_year_a"]),
                    "sb": _to_int(row["start_year_b"]),
                    "ic": _to_int(row["indicator_count"]),
                    "ac": round(_to_float(row["avg_correlation"]), 3),
                    "pps": round(_to_float(row["pattern_power_score"]), 2),
                }
            )

        next_token = resp.get("NextToken")
        if not next_token:
            break

    # Build the output JSON. Histogram is computed over the (already
    # top-200-filtered) kept windows — matches legacy Lambda behavior
    # exactly.
    output: dict[str, dict] = {}
    for b_id, windows in pairs_buf.items():
        hist: dict[str, int] = defaultdict(int)
        for w in windows:
            if w["l"] is not None:
                hist[str(w["l"])] += 1
        output[b_id] = {"top": windows, "hist": dict(hist)}

    key = f"{DASHBOARD_PREFIX}/{a_id}.json"
    payload = json.dumps(output, separators=(",", ":")).encode("utf-8")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType="application/json",
        CacheControl="public, max-age=300, s-maxage=86400",
    )
    logger.info(
        f"Wrote s3://{bucket}/{key} — {len(payload):,} bytes, {len(output)} partners, {total_rows} rows processed"
    )

    return {
        "country_a_id": a_id,
        "key": key,
        "partners": len(output),
        "rows": total_rows,
    }
