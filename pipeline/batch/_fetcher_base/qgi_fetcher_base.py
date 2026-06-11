"""Shared Fargate-fetcher base for new indicator providers (enrichment stage 2).

The WB (`fetch_one.py`) and FAOSTAT (`fetch_domain.py`) fetchers each duplicate
the same boilerplate: env wiring, country mapping, parquet write to the shared
`parquet-completed/` layout, Glue partition registration, DDB mirror, status
tracker, and counter decrement. New providers (ILOSTAT/UNHCR/IDMC/UCDP/UNDP/
OECD/OWID) all share that contract, so it lives here once.

A provider plugin only implements ``fetch_one(spec) -> DataFrame[country, year,
value]`` (country = canonical name_1) and calls ``run_fetcher(provider,
fetch_one)``. The base enforces the schema, writes to
`pipeline-A-indicator-extractor/output/parquet-completed/{id}/{id}.parquet`
(the SCDI/recipe-fleet-compatible path), and handles all DDB/Athena/counter I/O.

Faithful to fetch_one.py / fetch_domain.py, with two deliberate improvements:
  * AWS clients + required env are LAZY (read on first use) so the pure transform
    functions import cleanly under test without S3_BUCKET/RUN_ID set.
  * the Glue partition LOCATION points at `parquet-completed/` (fetch_one.py's
    points at the older `parquet/` - a known mismatch for multi-source reads).

Output contract (Phase 2 SCDI + recipe-fleet read this): country:str(name_1),
year:int64, value:float64, is_predicted:bool. Local logic is unit-tested; the
AWS I/O is copied from the proven WB/FAO fetchers. No imports of boto3 at module
load (lazy) so this is importable in CI without AWS.
"""

from __future__ import annotations

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
from typing import Any, Callable

import pandas as pd

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("qgi-fetcher")

REGION = os.environ.get("AWS_REGION", "eu-central-1")
S3_OUTPUT_PREFIX = "pipeline-A-indicator-extractor/output"
PARQUET_COMPLETED_PREFIX = f"{S3_OUTPUT_PREFIX}/parquet-completed"
COUNTRIES_CSV_KEY = "pipeline-A-indicator-extractor/countries/countries.csv"
COUNTRY_M49_MAP_KEY = "pipeline-A-indicator-extractor/registries/country-m49-map.csv"
ATHENA_DATABASE = os.environ.get("ATHENA_DATABASE", "qgi_data")
ATHENA_WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")
INDICATORS_TABLE_NAME = "indicators"
JITTER_MIN_S = int(os.environ.get("JITTER_MIN_S", "60"))
JITTER_MAX_S = int(os.environ.get("JITTER_MAX_S", "300"))

OUTPUT_COLUMNS = ["country", "year", "value", "is_predicted"]

# ---- lazy AWS accessors (so pure transforms import without boto3/env) --------
_cache: dict[str, Any] = {}


def bucket() -> str:
    return os.environ["S3_BUCKET"]


def run_id() -> str:
    return os.environ["RUN_ID"]


def _s3():
    if "s3" not in _cache:
        import boto3

        _cache["s3"] = boto3.client("s3", region_name=REGION)
    return _cache["s3"]


def _ddb_table(name: str):
    key = f"ddb:{name}"
    if key not in _cache:
        import boto3

        _cache[key] = boto3.resource("dynamodb", region_name=REGION).Table(name)
    return _cache[key]


def _athena():
    if "athena" not in _cache:
        import boto3

        _cache["athena"] = boto3.client("athena", region_name=REGION)
    return _cache["athena"]


# ---- country mapping (pure builders + S3 loaders) ---------------------------


def iso3_map_from_df(df: pd.DataFrame) -> dict[str, str]:
    """Build {ISO_ALPHA3(upper): canonical name_1} from a country-m49-map frame."""
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        val = row.get("iso_alpha3")
        if pd.isna(val) or val is None:
            continue
        iso = str(val).strip().upper()
        name_val = row.get("qgi_name")
        if pd.isna(name_val) or name_val is None:
            continue
        name = str(name_val).strip()
        if iso and name and iso != "NAN":
            out[iso] = name
    return out


def load_iso3_country_map() -> dict[str, str]:
    obj = _s3().get_object(Bucket=bucket(), Key=COUNTRY_M49_MAP_KEY)
    return iso3_map_from_df(pd.read_csv(obj["Body"]))


def name_alias_map_from_df(df: pd.DataFrame) -> dict[str, str]:
    """Build {alias: name_1} from countries.csv (every non-name_1 column is an alias)."""
    df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
    if "name_1" not in df.columns:
        raise ValueError("countries.csv missing 'name_1'")
    mapping: dict[str, str] = {}
    for col in df.columns:
        if col != "name_1":
            mapping.update(df.dropna(subset=[col]).set_index(col)["name_1"].to_dict())
    return mapping


def load_name_alias_map() -> dict[str, str]:
    obj = _s3().get_object(Bucket=bucket(), Key=COUNTRIES_CSV_KEY)
    return name_alias_map_from_df(pd.read_csv(StringIO(obj["Body"].read().decode("utf-8"))))


# ---- schema + write ---------------------------------------------------------


def to_canonical_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a provider frame to the 4-column output contract.

    Requires columns country, year, value. is_predicted defaults False. Drops
    NaN values, de-dups (country, year) keeping the last, sorts.
    """
    missing = {"country", "year", "value"} - set(df.columns)
    if missing:
        raise ValueError(f"frame missing columns {missing}")
    out = df.copy()
    out["country"] = out["country"].astype(str)
    out["year"] = pd.to_numeric(out["year"], errors="coerce").astype("Int64")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out["is_predicted"] = out["is_predicted"].astype(bool) if "is_predicted" in out.columns else False
    out = out.dropna(subset=["year", "value"])
    out["year"] = out["year"].astype("int64")
    out["value"] = out["value"].astype("float64")
    out = out.drop_duplicates(subset=["country", "year"], keep="last").sort_values(["country", "year"])
    return out[OUTPUT_COLUMNS].reset_index(drop=True)


def write_indicator_parquet(df: pd.DataFrame, indicator_id: str) -> str:
    """Write the canonical frame to parquet-completed (hash-skip if unchanged).
    Returns UPDATED / UNCHANGED / SKIPPED."""
    if df.empty:
        return "SKIPPED"
    key = f"{PARQUET_COMPLETED_PREFIX}/{indicator_id}/{indicator_id}.parquet"
    new_hash = hashlib.md5(df.to_csv(index=False).encode("utf-8")).hexdigest()
    try:
        head = _s3().head_object(Bucket=bucket(), Key=key)
        if head["Metadata"].get("content_hash") == new_hash:
            logger.info(f"{indicator_id}: unchanged (hash match)")
            return "UNCHANGED"
    except Exception:
        pass
    buf = BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow", compression="snappy")
    _s3().put_object(Bucket=bucket(), Key=key, Body=buf.getvalue(), Metadata={"content_hash": new_hash})
    logger.info(
        f"{indicator_id}: wrote {len(df):,} rows ({df['country'].nunique()} countries x {df['year'].nunique()} years)"
    )
    register_glue_partition(indicator_id)
    return "UPDATED"


def register_glue_partition(indicator_id: str) -> None:
    """ALTER TABLE qgi_data.indicators ADD PARTITION at the parquet-completed location."""
    location = f"s3://{bucket()}/{PARQUET_COMPLETED_PREFIX}/{indicator_id}/"
    sql = (
        f"ALTER TABLE {ATHENA_DATABASE}.{INDICATORS_TABLE_NAME} "
        f"ADD IF NOT EXISTS PARTITION (indicator_id='{indicator_id}') LOCATION '{location}'"
    )
    try:
        qid = _athena().start_query_execution(
            QueryString=sql, QueryExecutionContext={"Database": ATHENA_DATABASE}, WorkGroup=ATHENA_WORKGROUP
        )["QueryExecutionId"]
        for _ in range(20):
            state = _athena().get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                return
            if state in ("FAILED", "CANCELLED"):
                logger.warning(f"ALTER TABLE {indicator_id} -> {state}")
                return
            time.sleep(0.5)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Glue partition register failed for {indicator_id}: {e}")


def mirror_to_ddb(df: pd.DataFrame, indicator_id: str) -> int:
    table = _ddb_table(os.environ.get("INDICATOR_VALUES_TABLE", "qgi-indicator-values"))
    items = []
    for r in df.itertuples(index=False):
        c = str(r.country)
        if not c:
            continue
        v = float(r.value)
        if v != v:  # NaN
            continue
        items.append(
            {"indicator_country": f"{indicator_id}#{c}", "year": int(r.year), "value": Decimal(format(v, ".6g"))}
        )
    if not items:
        return 0
    written = 0
    try:
        with table.batch_writer(overwrite_by_pkeys=["indicator_country", "year"]) as b:
            for it in items:
                b.put_item(Item=it)
                written += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(f"DDB mirror partial failure {indicator_id}: {e}")
    return written


def write_tracker(indicator_id: str, status: str, provider: str, error: str | None = None) -> None:
    item = {
        "run_id": run_id(),
        "indicator_id": indicator_id,
        "status": status,
        "provider": provider,
        "timestamp": int(time.time()),
        "expire_at": int(time.time()) + 30 * 24 * 60 * 60,
    }
    if error:
        item["error"] = error[:1000]
    try:
        _ddb_table(os.environ.get("TRACKER_TABLE", "qgi-indicator-updates")).put_item(Item=item)
    except Exception as e:  # noqa: BLE001
        logger.error(f"tracker write failed {indicator_id}: {e}")


def decrement_counter(by: int = 1) -> None:
    """Decrement qgi-pipeline-a-counter[run_id].pending by N (one per indicator)."""
    try:
        _ddb_table(os.environ.get("COUNTER_TABLE", "qgi-pipeline-a-counter")).update_item(
            Key={"run_id": run_id()},
            UpdateExpression="ADD pending :neg",
            ExpressionAttributeValues={":neg": Decimal(-by)},
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"counter decrement failed: {e}")


def jitter_sleep() -> None:
    s = random.uniform(JITTER_MIN_S, JITTER_MAX_S)
    logger.info(f"jitter sleep {s:.1f}s")
    time.sleep(s)


def resolve_indicator_specs() -> list[dict[str, Any]]:
    """Specs to fetch this task: INDICATORS_JSON (bulk) or one {id_string: INDICATOR_ID}."""
    raw = os.environ.get("INDICATORS_JSON")
    if raw:
        return json.loads(raw)
    return [{"id_string": os.environ["INDICATOR_ID"]}]


def run_fetcher(provider: str, fetch_one: Callable[[dict[str, Any]], pd.DataFrame | None]) -> None:
    """Harness: jitter, fetch+write each spec, tracker per indicator, decrement by
    total, exit 0 (Batch retries are reserved for infra failures, not data errors)."""
    specs = resolve_indicator_specs()
    logger.info(f"=== {provider} fetcher: {len(specs)} indicator(s) run_id={run_id()} ===")
    jitter_sleep()
    for spec in specs:
        iid = spec["id_string"]
        status, err, df = "FAILED", None, None
        try:
            raw = fetch_one(spec)
            if raw is None or len(raw) == 0:
                status = "SKIPPED"
            else:
                df = to_canonical_frame(raw)
                status = write_indicator_parquet(df, iid)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            logger.error(f"{iid} FAILED: {err}")
            logger.error(traceback.format_exc())
        if df is not None and status in ("UPDATED", "UNCHANGED"):
            try:
                mirror_to_ddb(df, iid)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"{iid} ddb mirror failed: {e}")
        write_tracker(iid, status, provider, err)
        logger.info(f"{iid}: {status}")
    decrement_counter(by=len(specs))
    sys.exit(0)
