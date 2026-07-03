"""
pipeline-pattern-density-generator (GH#278)

Queries pattern density by year per country from the Athena patterns table
and writes pattern-density.json to S3 at dashboard/pattern-density.json.

Output format:
  {
    "<country_id>": {
      "years":  [<int>, ...],
      "counts": [<int>, ...],
      "total":  <int>
    },
    ...
  }

Years and counts are parallel arrays ordered by ascending year.

Environment variables:
  S3_BUCKET              — data lake bucket (required)
  ATHENA_DATABASE        — default: qgi_data
  ATHENA_WORKGROUP       — default: QGI-Lambda-Workgroup
  ATHENA_OUTPUT_LOCATION — S3 URI for Athena query results (optional,
                           workgroup default used if not set)

Timeout: 900s  Memory: 256 MB
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get("S3_BUCKET")
ATHENA_DB = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WG = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
# #371 — ATHENA_OUTPUT_LOCATION removed; workgroup enforces its own output location.
DASHBOARD_PREFIX = "dashboard"
OUTPUT_KEY = f"{DASHBOARD_PREFIX}/pattern-density.json"

DENSITY_QUERY = """
SELECT country_a_id, start_year_a as year, count(*) as cnt
FROM qgi_data.patterns
GROUP BY country_a_id, start_year_a
ORDER BY country_a_id, start_year_a
"""

athena = boto3.client("athena")
s3 = boto3.client("s3")


def lambda_handler(event, context):
    run_id = event.get("run_id", "manual")
    logger.info(f"pattern-density-generator starting. run_id={run_id}")

    # Run Athena query
    logger.info("Running density Athena query")
    query_id = _run_query(DENSITY_QUERY)
    rows = _fetch_all_rows(query_id)
    logger.info(f"Got {len(rows)} density rows")

    # Build {country_id -> {years: [...], counts: [...], total: N}}
    density: dict[str, dict] = {}
    for row in rows:
        cid = row["country_a_id"]
        year = _to_int(row["year"])
        cnt = _to_int(row["cnt"])
        if cid not in density:
            density[cid] = {"years": [], "counts": [], "total": 0}
        density[cid]["years"].append(year)
        density[cid]["counts"].append(cnt)
        density[cid]["total"] += cnt

    logger.info(f"Pattern density built for {len(density)} countries")

    # Write to S3
    payload = json.dumps(density, separators=(",", ":")).encode("utf-8")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=OUTPUT_KEY,
        Body=payload,
        ContentType="application/json",
        CacheControl="public, max-age=300, s-maxage=86400",
    )
    logger.info(f"Wrote s3://{S3_BUCKET}/{OUTPUT_KEY} ({len(payload)} bytes, {len(density)} countries)")

    return {
        "statusCode": 200,
        "country_count": len(density),
        "row_count": len(rows),
        "output_key": OUTPUT_KEY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _run_query(sql: str) -> str:
    """Submit Athena query and poll until SUCCEEDED. Returns query execution ID."""
    # #371 — ResultConfiguration omitted; workgroup enforces its own location.
    # See #369 Fix 7 for the failure class this pattern avoids.
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
        time.sleep(1)


def _fetch_all_rows(query_id: str) -> list[dict]:
    """Paginate through Athena results and return all rows as dicts."""
    rows = []
    headers = None
    next_token = None

    while True:
        kwargs = {"QueryExecutionId": query_id}
        if next_token:
            kwargs["NextToken"] = next_token
        result = athena.get_query_results(**kwargs)
        result_rows = result["ResultSet"]["Rows"]

        if headers is None:
            headers = [col.get("VarCharValue", "") for col in result_rows[0]["Data"]]
            data_rows = result_rows[1:]
        else:
            data_rows = result_rows

        for row in data_rows:
            cells = row.get("Data", [])
            rows.append(
                {headers[i]: cells[i].get("VarCharValue", "") if i < len(cells) else "" for i in range(len(headers))}
            )

        next_token = result.get("NextToken")
        if not next_token:
            break

    return rows


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
