"""
pipeline-structural-twins-generator (GH#279)

Queries the top 5 structural twins per country from the Athena patterns table
and writes structural-twins.json to S3 at dashboard/structural-twins.json.

A structural twin is a country whose historical indicator trajectory closely
mirrors another country's — identified by the number of shared patterns,
mean correlation, and best pattern power score.

Output format:
  {
    "<country_id>": [
      {
        "partner_id":    <int>,
        "partner_name":  "<str>",
        "alpha2":        "<str>",
        "pattern_count": <int>,
        "mean_corr":     <float>,
        "best_pps":      <float>
      },
      ...   (up to 5 entries, sorted by pattern_count desc)
    ],
    ...
  }

Country name/alpha2 enrichment comes from countries.csv on S3 at
  pipeline-A-indicator-extractor/input/countries.csv

Environment variables:
  S3_BUCKET              — data lake bucket (required)
  ATHENA_DATABASE        — default: qgi_data
  ATHENA_WORKGROUP       — default: QGI-Lambda-Workgroup
  ATHENA_OUTPUT_LOCATION — S3 URI for Athena query results (optional,
                           workgroup default used if not set)

Timeout: 900s  Memory: 256 MB
"""

import csv
import io
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
COUNTRIES_CSV_KEY = "pipeline-A-indicator-extractor/input/countries.csv"
OUTPUT_KEY = f"{DASHBOARD_PREFIX}/structural-twins.json"
TOP_N = 5

TWINS_QUERY = """
SELECT country_a_id, country_b_id, count(*) as pattern_count,
       avg(avg_correlation) as mean_corr,
       max(pattern_power_score) as best_pps
FROM qgi_data.patterns
GROUP BY country_a_id, country_b_id
"""

athena = boto3.client("athena")
s3 = boto3.client("s3")


def lambda_handler(event, context):
    run_id = event.get("run_id", "manual")
    logger.info(f"structural-twins-generator starting. run_id={run_id}")

    # Load country lookup from S3 CSV
    id_to_name, id_to_alpha2 = _load_countries_csv()
    logger.info(f"Loaded {len(id_to_name)} countries from CSV")

    # Run Athena query
    logger.info("Running structural-twins Athena query")
    query_id = _run_query(TWINS_QUERY)
    rows = _fetch_all_rows(query_id)
    logger.info(f"Got {len(rows)} pair rows")

    # Group all partners per country_a_id
    pairs: dict[str, list] = {}
    for row in rows:
        a_id = row["country_a_id"]
        b_id = row["country_b_id"]
        if a_id not in pairs:
            pairs[a_id] = []
        pairs[a_id].append(
            {
                "partner_id": _to_int(b_id),
                "pattern_count": _to_int(row["pattern_count"]),
                "mean_corr": round(_to_float(row["mean_corr"]), 3),
                "best_pps": round(_to_float(row["best_pps"]), 2),
            }
        )

    # For each country take top-N by pattern_count, enrich with name/alpha2
    twins: dict[str, list] = {}
    for a_id, partner_list in pairs.items():
        partner_list.sort(key=lambda x: x["pattern_count"], reverse=True)
        top = partner_list[:TOP_N]
        for entry in top:
            pid = str(entry["partner_id"])
            entry["partner_name"] = id_to_name.get(pid, f"Country {pid}")
            entry["alpha2"] = id_to_alpha2.get(pid, "")
        twins[a_id] = top

    logger.info(f"Structural twins built for {len(twins)} countries")

    # Write to S3
    payload = json.dumps(twins, separators=(",", ":")).encode("utf-8")
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=OUTPUT_KEY,
        Body=payload,
        ContentType="application/json",
        CacheControl="public, max-age=300, s-maxage=86400",
    )
    logger.info(f"Wrote s3://{S3_BUCKET}/{OUTPUT_KEY} ({len(payload)} bytes, {len(twins)} countries)")

    return {
        "statusCode": 200,
        "country_count": len(twins),
        "pair_count": len(rows),
        "output_key": OUTPUT_KEY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_countries_csv():
    """Read countries.csv from S3. Returns (id_to_name, id_to_alpha2) dicts.

    Gracefully handles missing file — returns empty dicts so the Lambda
    still runs and twins are written with fallback names.
    """
    id_to_name: dict[str, str] = {}
    id_to_alpha2: dict[str, str] = {}
    try:
        obj = s3.get_object(Bucket=S3_BUCKET, Key=COUNTRIES_CSV_KEY)
        raw = obj["Body"].read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(raw))
        for row in reader:
            cid = str(row.get("id", "")).strip()
            if not cid:
                continue
            name = row.get("name") or row.get("name_1") or ""
            alpha2 = row.get("alpha_2") or row.get("alpha2") or ""
            id_to_name[cid] = name.strip()
            id_to_alpha2[cid] = alpha2.strip()
    except Exception:
        logger.warning(
            f"Could not load countries.csv from s3://{S3_BUCKET}/{COUNTRIES_CSV_KEY}; continuing with fallback names",
            exc_info=True,
        )
    return id_to_name, id_to_alpha2


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


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
