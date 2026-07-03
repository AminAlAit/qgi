"""
Phase 1.5 — Indicator Completion

Runs after Phase 1 (ingest) and before Phase 2 (Batch SCDI).

For every indicator in the data lake, and for every country within that
indicator, this Lambda detects gaps between the last real data year and the
current year, then self-predicts the missing values using Holt-Winters
exponential smoothing (ETS).

The completed series is written to a separate S3 prefix
(output/csv-completed/) so the raw worker output is never modified.
scdi-finder reads from csv-completed/.

Output schema: country, year, value, is_predicted
  is_predicted=False  → original World Bank value
  is_predicted=True   → ETS forecast

Rules:
  - Skip country if fewer than MIN_HISTORY real data points
  - Skip country if gap > MAX_FORECAST_YEARS
  - If skipped, the raw series is copied as-is with is_predicted=False
"""

import os
import io
import logging
import datetime
import time
import boto3
import numpy as np
import pandas as pd

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")
athena = boto3.client("athena")
dynamodb = boto3.resource("dynamodb")

S3_BUCKET = os.environ["S3_BUCKET"]
INPUT_PREFIX = os.environ["INPUT_PREFIX"]  # pipeline-A-indicator-extractor/output/csv
OUTPUT_PREFIX = os.environ["OUTPUT_PREFIX"]  # pipeline-A-indicator-extractor/output/csv-completed
INDICATOR_MAP_KEY = os.environ["INDICATOR_MAP_KEY"]  # pipeline-A-indicator-extractor/input/indicator_map.csv

# #149: Glue partition auto-registration for qgi_data.indicators_completed.
# The table is partitioned by indicator_id but the S3 layout is bare
# ({INDICATOR_ID}/) rather than Hive-style (indicator_id={INDICATOR_ID}/),
# so MSCK REPAIR can't discover new partitions. We run a single batched
# ALTER TABLE ADD IF NOT EXISTS for every completed indicator at the end
# of the handler, plus a parallel registration on qgi_data.indicators for
# any raw-table partitions that the worker may have missed.
ATHENA_DATABASE = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
ATHENA_OUTPUT_LOCATION = os.environ.get("ATHENA_OUTPUT_LOCATION", f"s3://{S3_BUCKET}/query_results/")
INDICATORS_TABLE = "indicators"
INDICATORS_COMPLETED_TABLE = "indicators_completed"

# #148: DynamoDB table for fast frontend reads of indicator values.
# Schema:
#   PK   indicator_country : S   (e.g. "SP.POP.TOTL#South Korea")
#   SK   year              : N
#   attr value             : N
# The frontend issues BatchGetItem with up to 100 (PK, SK) tuples per call,
# replacing the per-(indicator, country) Athena query that was 2-10s cold.
INDICATOR_VALUES_TABLE_NAME = os.environ.get("INDICATOR_VALUES_TABLE_NAME", "")
_indicator_values_table = dynamodb.Table(INDICATOR_VALUES_TABLE_NAME) if INDICATOR_VALUES_TABLE_NAME else None

MIN_HISTORY = 5  # minimum real data points required to attempt forecasting
MAX_FORECAST_YEARS = 5  # refuse to extrapolate more than 5 years forward


def _current_year() -> int:
    return datetime.datetime.utcnow().year


def _list_indicator_ids() -> list[str]:
    """Returns all indicator IDs that have a parquet file under INPUT_PREFIX."""
    paginator = s3.get_paginator("list_objects_v2")
    ids = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=INPUT_PREFIX + "/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".parquet"):
                # key shape: {INPUT_PREFIX}/{id}/{id}.parquet
                parts = key.split("/")
                if len(parts) >= 2:
                    ids.append(parts[-2])
    return ids


def _read_parquet(key: str) -> pd.DataFrame:
    obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))


def _write_parquet(df: pd.DataFrame, key: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow", compression="snappy")
    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=buf.getvalue())


def _mirror_to_dynamodb(df: pd.DataFrame, indicator_id: str) -> int:
    """#148: mirror this indicator's completed values to qgi-indicator-values.

    Items are keyed (indicator_country=f'{indicator_id}#{country}', year=year)
    with a single 'value' attribute. Items where value is NaN/None are
    skipped — the frontend treats missing keys as 'data unavailable' and
    renders gaps in the chart (consistent with the #125 missing-data UX).

    Best-effort: failures are logged and counted but never break the
    pipeline. Returns the number of items written.

    DDB BatchWriteItem caps at 25 items per request, so we batch 25 at a
    time. Idempotent: re-runs simply overwrite existing items with the
    same (PK, SK) — values are immutable historical for any given year.
    """
    if _indicator_values_table is None:
        logger.warning(f"INDICATOR_VALUES_TABLE_NAME not set; skipping DDB mirror for {indicator_id}")
        return 0

    # Build the put-item list, dropping NaN values
    items = []
    for row in df.itertuples(index=False):
        country = str(row.country) if row.country is not None else None
        year = row.year
        value = row.value
        if not country:
            continue
        try:
            year_int = int(year)
        except (TypeError, ValueError):
            continue
        try:
            value_float = float(value)
        except (TypeError, ValueError):
            continue
        if value_float != value_float:  # NaN check (NaN != NaN)
            continue
        items.append(
            {
                "indicator_country": f"{indicator_id}#{country}",
                "year": year_int,
                # DDB doesn't accept Python float; the resource API converts
                # via Decimal — but Decimal(float) raises on NaN/Inf, which
                # we already filtered above.
                "value": _to_ddb_number(value_float),
            }
        )

    if not items:
        return 0

    written = 0
    try:
        with _indicator_values_table.batch_writer(overwrite_by_pkeys=["indicator_country", "year"]) as batch:
            for item in items:
                batch.put_item(Item=item)
                written += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"DDB mirror partial failure for {indicator_id} after {written}/{len(items)} items: {exc}")
    return written


def _to_ddb_number(value: float):
    """Convert a Python float to a DDB-safe Decimal.

    boto3's resource API requires Decimal for numeric attributes; passing
    a raw float raises TypeError. We round to 6 significant digits to
    avoid the long binary-decimal expansion that Decimal(float) produces.
    """
    from decimal import Decimal

    # Format as a fixed-precision string then convert — sidesteps the
    # Decimal(float) precision-noise issue.
    return Decimal(format(value, ".6g"))


def _register_partitions_batched(
    table_name: str,
    prefix_template: str,
    indicator_ids: list[str],
) -> None:
    """#149: Batched ALTER TABLE ADD IF NOT EXISTS PARTITION for every
    indicator_id on the given table.

    prefix_template is an f-string-friendly template like
    '{prefix}/parquet-completed/{indicator_id}/' — the {indicator_id}
    placeholder is substituted per partition, and the result becomes the
    Hive LOCATION clause.

    Best-effort: log and swallow exceptions so a partition-registration
    hiccup never fails the handler. Idempotent via IF NOT EXISTS.
    """
    if not indicator_ids:
        return
    partitions_sql = "\n".join(
        f"PARTITION (indicator_id='{ind}') LOCATION 's3://{S3_BUCKET}/{prefix_template.format(indicator_id=ind)}'"
        for ind in sorted(set(indicator_ids))
    )
    sql = f"ALTER TABLE {ATHENA_DATABASE}.{table_name} ADD IF NOT EXISTS\n{partitions_sql}"
    try:
        response = athena.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={"Database": ATHENA_DATABASE},
            WorkGroup=ATHENA_WORKGROUP,
            ResultConfiguration={"OutputLocation": ATHENA_OUTPUT_LOCATION},
        )
        query_id = response["QueryExecutionId"]
        # ALTER TABLE with hundreds of partitions can take 5-15s
        for _ in range(60):
            status = athena.get_query_execution(QueryExecutionId=query_id)
            state = status["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                logger.info(f"Registered {len(indicator_ids)} partitions on {ATHENA_DATABASE}.{table_name}")
                return
            if state in ("FAILED", "CANCELLED"):
                reason = status["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
                logger.warning(f"Batched ALTER TABLE on {table_name} failed: {reason}")
                return
            time.sleep(0.5)
        logger.warning(f"Batched ALTER TABLE on {table_name} timed out (still RUNNING after 30s)")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Batched partition registration exception on {table_name}: {exc}")


def _ets_forecast(series: pd.Series, n_steps: int) -> list[float]:
    """
    Holt-Winters double exponential smoothing (additive trend, no seasonality).
    Pure numpy implementation — no statsmodels dependency.
    Grid-searches alpha/beta to minimise in-sample SSE.
    """
    y = np.array(series, dtype=float)
    n = len(y)

    best_sse = float("inf")
    best_alpha = 0.3
    best_beta = 0.1

    for alpha in np.arange(0.05, 1.0, 0.05):
        for beta in np.arange(0.01, 0.5, 0.05):
            l = y[0]
            b = y[1] - y[0] if n > 1 else 0.0
            sse = 0.0
            for t in range(1, n):
                l_prev, b_prev = l, b
                l = alpha * y[t] + (1 - alpha) * (l_prev + b_prev)
                b = beta * (l - l_prev) + (1 - beta) * b_prev
                sse += (y[t] - (l_prev + b_prev)) ** 2
            if sse < best_sse:
                best_sse = sse
                best_alpha, best_beta = alpha, beta

    # Final fit with best params
    l = y[0]
    b = y[1] - y[0] if n > 1 else 0.0
    for t in range(1, n):
        l_prev, b_prev = l, b
        l = best_alpha * y[t] + (1 - best_alpha) * (l_prev + b_prev)
        b = best_beta * (l - l_prev) + (1 - best_beta) * b_prev

    return [float(l + h * b) for h in range(1, n_steps + 1)]


def _complete_indicator(df: pd.DataFrame) -> pd.DataFrame:
    """
    Takes a raw indicator DataFrame (country, year, value) and returns
    a completed DataFrame (country, year, value, is_predicted).
    """
    current_year = _current_year()
    completed_parts = []

    for country, group in df.groupby("country"):
        group = group.sort_values("year").copy()
        group["is_predicted"] = False

        last_real_year = int(group["year"].max())
        gap = current_year - last_real_year

        if gap <= 0:
            # Already has current year data — no completion needed
            completed_parts.append(group)
            continue

        if gap > MAX_FORECAST_YEARS:
            logger.warning(f"  {country}: gap={gap} > MAX_FORECAST_YEARS={MAX_FORECAST_YEARS}, skipping forecast")
            completed_parts.append(group)
            continue

        real_values = group["value"].dropna()
        if len(real_values) < MIN_HISTORY:
            logger.warning(
                f"  {country}: only {len(real_values)} real points < MIN_HISTORY={MIN_HISTORY}, skipping forecast"
            )
            completed_parts.append(group)
            continue

        try:
            forecasts = _ets_forecast(real_values, gap)
        except Exception as e:
            logger.warning(f"  {country}: ETS failed ({e}), skipping forecast")
            completed_parts.append(group)
            continue

        predicted_rows = pd.DataFrame(
            {
                "country": [country] * gap,
                "year": list(range(last_real_year + 1, current_year + 1)),
                "value": forecasts,
                "is_predicted": [True] * gap,
            }
        )

        completed_parts.append(pd.concat([group, predicted_rows], ignore_index=True))

    if not completed_parts:
        return df.assign(is_predicted=False)

    return pd.concat(completed_parts, ignore_index=True).sort_values(["country", "year"])


def lambda_handler(event, context):
    # #157: only re-mirror indicators whose parquet actually changed this run.
    # Previously the completer mirrored every indicator on every invocation,
    # which cost ~720K DDB writes per run (60 indicators × ~200 countries ×
    # ~60 years). Most runs have just 0-2 indicator updates, so the mirror
    # was writing ~99.7% redundant data, burning ~$2/run on DDB writes.
    #
    # The Step Function now passes updated_ids from the reporter result.
    # If the list is empty or missing, we still complete all parquet files
    # (because the completer also writes output/csv-completed/ for scdi-finder
    # and handles forecast extension), BUT we only mirror-to-DDB the ones
    # that actually changed.
    all_indicator_ids = _list_indicator_ids()
    updated_set = set(event.get("updated_ids") or [])
    logger.info(
        f"Found {len(all_indicator_ids)} indicator files to complete; "
        f"{len(updated_set)} flagged as UPDATED this run "
        f"→ DDB mirror restricted to the updated set"
    )

    stats = {"completed": 0, "ddb_mirrored": 0, "ddb_skipped": 0, "failed": 0}

    for indicator_id in all_indicator_ids:
        input_key = f"{INPUT_PREFIX}/{indicator_id}/{indicator_id}.parquet"
        output_key = f"{OUTPUT_PREFIX}/{indicator_id}/{indicator_id}.parquet"

        try:
            df = _read_parquet(input_key)
            logger.info(f"Processing {indicator_id}: {len(df)} rows, {df['country'].nunique()} countries")

            completed = _complete_indicator(df)
            _write_parquet(completed, output_key)

            added = len(completed) - len(df)
            logger.info(f"  → wrote {len(completed)} rows (+{added} predicted) to {output_key}")

            # #148 + #157: mirror only if this indicator was updated this run.
            # When updated_set is empty (manual invoke, backward compat), fall
            # back to mirroring all — same behavior as before #157.
            should_mirror = (not updated_set) or (indicator_id in updated_set)
            if should_mirror:
                ddb_written = _mirror_to_dynamodb(completed, indicator_id)
                if ddb_written > 0:
                    logger.info(f"  → mirrored {ddb_written} items to DDB for {indicator_id}")
                stats["ddb_mirrored"] += 1
            else:
                stats["ddb_skipped"] += 1

            stats["completed"] += 1

        except Exception as e:
            logger.error(f"Failed to complete {indicator_id}: {e}", exc_info=True)
            stats["failed"] += 1

    # #149: Register Glue partitions for both tables.
    #   - indicators_completed: gets every indicator_id we just wrote
    #   - indicators (raw, written by pipeline-a-worker): also registered here
    #     as a safety net in case the worker skipped it (unchanged hash path,
    #     transient Athena error, etc). BOTH prefixes use bare
    #     {indicator_id}/ layout, not Hive-style.
    _register_partitions_batched(
        INDICATORS_COMPLETED_TABLE,
        # OUTPUT_PREFIX is e.g. 'pipeline-A-indicator-extractor/output/parquet-completed'
        f"{OUTPUT_PREFIX.rstrip('/')}/" + "{indicator_id}/",
        all_indicator_ids,
    )
    _register_partitions_batched(
        INDICATORS_TABLE,
        # INPUT_PREFIX is e.g. 'pipeline-A-indicator-extractor/output/parquet'
        f"{INPUT_PREFIX.rstrip('/')}/" + "{indicator_id}/",
        all_indicator_ids,
    )

    logger.info(f"Phase 1.5 complete: {stats}")
    return {
        "status": "Complete",
        "indicators_completed": stats["completed"],
        "indicators_failed": stats["failed"],
    }
