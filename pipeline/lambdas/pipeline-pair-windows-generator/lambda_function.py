"""
pipeline-pair-windows-generator (GH#281)

Queries the Athena patterns table for ALL pattern windows ordered by
(country_a_id, country_b_id, pattern_power_score DESC), takes the top 200
windows per (country_a, country_b) pair, and writes one JSON file per
predictor country to S3:

  s3://{bucket}/dashboard/pair-windows/{country_a_id}.json

Output format per file (keyed by country_b_id as string):
  {
    "34": {
      "top": [
        {"l": 30, "sa": 1997, "sb": 1997, "ic": 26, "ac": 0.843, "pps": 657.5},
        ...  (up to 200 entries, sorted pps desc)
      ],
      "hist": {"3": 120, "4": 340, "5": 510, ...}
    },
    ...
  }

Short key legend: l=length, sa=start_year_a, sb=start_year_b,
  ic=indicator_count, ac=avg_correlation, pps=pattern_power_score.

The Athena result set is large (2 B+ rows). Rows are paginated via
NextToken and processed in streaming fashion — per-country accumulators
are flushed to S3 as soon as the predicting country changes, keeping
memory bounded to the data for one (country_a, country_b) pair family
at a time.

Environment variables:
  S3_BUCKET              — data lake bucket (required)
  ATHENA_DATABASE        — default: qgi_data
  ATHENA_WORKGROUP       — default: QGI-Lambda-Workgroup
  ATHENA_OUTPUT_LOCATION — S3 URI for Athena query results (optional,
                           workgroup default used if not set)

Timeout: 900s  Memory: 1024 MB
"""

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get("S3_BUCKET")
ATHENA_DB = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WG = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
# #371 — ATHENA_OUTPUT_LOCATION removed; workgroup enforces its own output location.
DASHBOARD_PREFIX = "dashboard/pair-windows"
TOP_N = 200

# Columns returned by the query (order must match SELECT)
WINDOWS_QUERY = """
SELECT country_a_id, country_b_id, length, start_year_a, start_year_b,
       indicator_count, avg_correlation, pattern_power_score
FROM qgi_data.patterns
ORDER BY country_a_id, country_b_id, pattern_power_score DESC
"""

athena = boto3.client("athena")
s3 = boto3.client("s3")


def lambda_handler(event, context):
    run_id = event.get("run_id", "manual")
    logger.info(f"pair-windows-generator starting. run_id={run_id}")

    query_id = _run_query(WINDOWS_QUERY)
    country_files_written = _stream_and_write(query_id)

    logger.info(f"pair-windows-generator done. files_written={country_files_written}")
    return {
        "statusCode": 200,
        "country_files_written": country_files_written,
        "output_prefix": f"s3://{S3_BUCKET}/{DASHBOARD_PREFIX}/",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Streaming processor
# ---------------------------------------------------------------------------


def _stream_and_write(query_id: str) -> int:
    """
    Paginate Athena results row by row. Because the query is ordered by
    country_a_id, country_b_id, we accumulate windows for one (a, b) pair
    and flush to S3 per country_a as soon as country_a changes.

    Returns the number of per-country S3 files written.
    """
    headers = None
    next_token = None

    # Accumulators for the current country_a batch
    current_a_id: str | None = None
    # {country_b_id: [window dicts]} for current_a_id
    pairs_buf: dict[str, list[dict]] = defaultdict(list)

    files_written = 0
    total_rows = 0

    while True:
        kwargs = {"QueryExecutionId": query_id, "MaxResults": 1000}
        if next_token:
            kwargs["NextToken"] = next_token
        result = athena.get_query_results(**kwargs)
        result_rows = result["ResultSet"]["Rows"]

        # First page: row 0 is the header
        if headers is None:
            headers = [col.get("VarCharValue", "") for col in result_rows[0]["Data"]]
            data_rows = result_rows[1:]
        else:
            data_rows = result_rows

        for raw_row in data_rows:
            cells = raw_row.get("Data", [])
            row = {headers[i]: cells[i].get("VarCharValue", "") if i < len(cells) else "" for i in range(len(headers))}
            total_rows += 1

            a_id = row["country_a_id"]
            b_id = row["country_b_id"]

            # Detect country_a transition → flush accumulated data
            if current_a_id is not None and a_id != current_a_id:
                _write_country_file(current_a_id, pairs_buf)
                files_written += 1
                pairs_buf = defaultdict(list)

            current_a_id = a_id

            # Only keep top TOP_N per pair (query is already sorted desc by pps)
            pair_list = pairs_buf[b_id]
            if len(pair_list) < TOP_N:
                pair_list.append(
                    {
                        "l": _to_int(row["length"]),
                        "sa": _to_int(row["start_year_a"]),
                        "sb": _to_int(row["start_year_b"]),
                        "ic": _to_int(row["indicator_count"]),
                        "ac": round(_to_float(row["avg_correlation"]), 3),
                        "pps": round(_to_float(row["pattern_power_score"]), 2),
                    }
                )

        next_token = result.get("NextToken")
        if not next_token:
            break

        if total_rows % 500_000 == 0:
            logger.info(f"Processed {total_rows:,} rows, {files_written} files written so far")

    # Flush the last country_a
    if current_a_id is not None and pairs_buf:
        _write_country_file(current_a_id, pairs_buf)
        files_written += 1

    logger.info(f"Total rows processed: {total_rows:,}")
    return files_written


def _write_country_file(country_a_id: str, pairs: dict[str, list[dict]]) -> None:
    """Serialise per-country pair data and write to S3."""
    output: dict[str, dict] = {}
    for b_id, windows in pairs.items():
        # Compute length histogram from whichever windows we kept
        hist: dict[str, int] = defaultdict(int)
        for w in windows:
            if w["l"] is not None:
                hist[str(w["l"])] += 1
        output[b_id] = {
            "top": windows,
            "hist": dict(hist),
        }

    key = f"{DASHBOARD_PREFIX}/{country_a_id}.json"
    payload = json.dumps(output, separators=(",", ":")).encode("utf-8")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=payload,
        ContentType="application/json",
        CacheControl="public, max-age=300, s-maxage=86400",
    )
    logger.debug(f"Wrote s3://{S3_BUCKET}/{key} ({len(payload)} bytes, {len(output)} partners)")


# ---------------------------------------------------------------------------
# Athena helpers
# ---------------------------------------------------------------------------


def _run_query(sql: str) -> str:
    """Submit Athena query and poll until SUCCEEDED. Returns query execution ID."""
    # #371 — ResultConfiguration omitted; workgroup enforces its own location.
    # (Legacy Lambda — slated for deletion per #369; patched for consistency.)
    kwargs = {
        "QueryString": sql,
        "QueryExecutionContext": {"Database": ATHENA_DB},
        "WorkGroup": ATHENA_WG,
    }

    response = athena.start_query_execution(**kwargs)
    query_id = response["QueryExecutionId"]
    logger.info(f"Athena query {query_id}: started")

    while True:
        status = athena.get_query_execution(QueryExecutionId=query_id)
        state = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            logger.info(f"Athena query {query_id}: SUCCEEDED")
            return query_id
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
            logger.error(f"Athena query {query_id}: {state} — {reason}")
            raise RuntimeError(f"Athena query {state}: {reason}")
        time.sleep(2)


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------


def _to_int(value) -> int | None:
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
