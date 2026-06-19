"""DSCDI Finder Batch entrypoint — Phase 5 v0.0b Stage F.

Wraps the pure-function library at `dscdi_finder.py` with S3 I/O and
env-var-driven orchestration. One Batch job processes one indicator across
all countries (per-indicator fan-out, not per-country like SCDI).

# NOT RUN AGAINST PRODUCTION until Stage F authorization. Per founder
# direction 2026-05-04 / 2026-05-05 / 2026-05-06: Stage F (TF apply +
# pipeline-B re-bake) is DEFERRED to end-of-cascade-mandate test-run.

Output schema — TWO Glue tables fed by this entrypoint:

  qgi_data.dscdis (partitioned by country_a_id):
    country_b_id, correlation, indicator_numeric_id, contains_predicted,
    is_demeaned, indicator_class
    (see qgi-infra/modules/storage/main.tf aws_glue_catalog_table.dscdis)

  qgi_data.dscdi_indicator_manifest (unpartitioned, one row per indicator):
    indicator_id, indicator_class, transform, n_countries,
    mean_abs_pairwise_corr, demeaning_applied, demeaning_insufficient,
    suppressed_reason
    (see qgi-infra/modules/storage/main.tf aws_glue_catalog_table.dscdi_indicator_manifest)

Methodology authority:
  - 6-way mini-Majles CSD reconvene DECISION 2026-05-05
  - Stage C input spec
  - Stage E completion report (109/109 indicators, 4 Class A flagged)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from io import BytesIO

import boto3
import numpy as np
import pandas as pd

import dscdi_finder

# ---------------------------------------------------------------------------
# Section 1 — Env-var contract
# ---------------------------------------------------------------------------
# Required env vars surface as KeyError if absent (fail fast at module
# load is intentional — Batch will mark the job FAILED, not silently
# default to wrong paths).
S3_BUCKET = os.environ.get("S3_BUCKET")
S3_INPUT_PREFIX = os.environ.get(
    "S3_INPUT_PREFIX",
    "pipeline-A-indicator-extractor/output/parquet-completed/",
)
S3_OUTPUT_PREFIX = os.environ.get("S3_OUTPUT_PREFIX", "pipeline-B-dscdi-finder/dscdis")
# MANIFEST_S3_PREFIX has a trailing slash (qgi-infra PR-2b decision):
# the entrypoint joins {prefix}{indicator_id}.parquet directly without
# re-adding a separator. Matches the Glue table location declaration.
MANIFEST_S3_PREFIX = os.environ.get("MANIFEST_S3_PREFIX", "pipeline-B-dscdi-finder/manifest/")
AUDIT_JSON_S3_KEY = os.environ.get("AUDIT_JSON_S3_KEY", "reference/indicator-stationarity-audit-v2.json")
INDICATOR_ID = os.environ.get("INDICATOR_ID")
MIN_LENGTH = int(os.environ.get("MIN_LENGTH", "3"))

# Canonical S3 paths verified against scdi_finder.py:518-521 comment.
INDICATOR_MAP_KEY = "pipeline-A-indicator-extractor/input/indicator_map.csv"
COUNTRIES_CSV_KEY = "pipeline-A-indicator-extractor/countries/countries.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

s3_client = boto3.client("s3")


# ---------------------------------------------------------------------------
# Section 2 — Load wide panel from S3
# ---------------------------------------------------------------------------
def load_panel(bucket: str, prefix: str, indicator_id: str) -> pd.DataFrame:
    """Read the per-indicator parquet from S3 and pivot long → wide.

    Source schema (long format): year, country, value (+ optional is_predicted).
    Returned wide schema: index=year, columns=country labels, values=value.
    """
    key = f"{prefix.rstrip('/')}/{indicator_id}/{indicator_id}.parquet"
    logger.info(f"[load_panel] reading s3://{bucket}/{key}")
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    df = pd.read_parquet(BytesIO(obj["Body"].read()))

    required = {"year", "country", "value"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"panel parquet for {indicator_id} missing columns: {sorted(missing)}; available={sorted(df.columns)}"
        )

    panel = df.pivot_table(index="year", columns="country", values="value", aggfunc="first")
    panel = panel.sort_index()
    logger.info(f"[load_panel] {indicator_id} panel shape={panel.shape} (years × countries)")
    return panel


# ---------------------------------------------------------------------------
# Section 3 — Load v2 audit JSON from S3
# ---------------------------------------------------------------------------
def load_audit(bucket: str, key: str) -> dict[str, str]:
    """Fetch the audit JSON from S3 and return {indicator_id: classification}.

    Bridges S3 to the existing dscdi_finder.load_audit_classifications()
    library function (which takes a file path). Downloads to a temp file
    and reuses the library function so the JSON parsing + skip-failures
    logic stays in one place.
    """
    logger.info(f"[load_audit] reading s3://{bucket}/{key}")
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    payload = obj["Body"].read()
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
        f.write(payload)
        tmp_path = f.name
    try:
        classifications = dscdi_finder.load_audit_classifications(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    logger.info(f"[load_audit] loaded {len(classifications)} classifications")
    return classifications


# ---------------------------------------------------------------------------
# Section 4 — Indicator map (id_string → numeric_id)
# ---------------------------------------------------------------------------
def load_indicator_map(bucket: str) -> dict[str, int]:
    """Read indicator_map.csv and return {id_string: numeric_id}."""
    logger.info(f"[load_indicator_map] reading s3://{bucket}/{INDICATOR_MAP_KEY}")
    obj = s3_client.get_object(Bucket=bucket, Key=INDICATOR_MAP_KEY)
    df = pd.read_csv(BytesIO(obj["Body"].read()))
    required = {"id_string", "numeric_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"indicator_map.csv missing columns: {sorted(missing)}; available={sorted(df.columns)}")
    return df.set_index("id_string")["numeric_id"].to_dict()


# ---------------------------------------------------------------------------
# Section 5 — Countries map (name → integer id)
# ---------------------------------------------------------------------------
def load_countries_map(bucket: str) -> dict[str, int]:
    """Read countries.csv and return {name_1: id}.

    `name_1` is the canonical country-label column matching the panel
    parquet's `country` field (per scdi_finder.py:521 reference).
    """
    logger.info(f"[load_countries_map] reading s3://{bucket}/{COUNTRIES_CSV_KEY}")
    obj = s3_client.get_object(Bucket=bucket, Key=COUNTRIES_CSV_KEY)
    df = pd.read_csv(BytesIO(obj["Body"].read()))
    required = {"name_1", "id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"countries.csv missing columns: {sorted(missing)}; available={sorted(df.columns)}")
    return df.set_index("name_1")["id"].to_dict()


# ---------------------------------------------------------------------------
# Section 6 — Pivot N×N correlation matrix → long-format pair rows
# ---------------------------------------------------------------------------
def _matrix_to_long(corr_matrix: pd.DataFrame, countries_map: dict[str, int]) -> pd.DataFrame:
    """Pivot a country×country correlation DataFrame to long format.

    Returns a DataFrame with columns: country_a_id (uint16),
    country_b_id (uint16), correlation (float32). Self-correlation
    (A==B) rows are excluded. Both A→B and B→A pairs are included
    (matching scdi convention; downstream consumers handle directionality).

    Raises ValueError if any country label in the matrix is absent from
    countries_map (M-1 NaN guard from plan v5: silently mapping to NaN
    and downcasting to uint16 would produce 0 IDs for unknown countries,
    breaking Phase 6 joins on country_a_id).
    """
    if corr_matrix.empty:
        return pd.DataFrame(columns=["country_a_id", "country_b_id", "correlation"]).astype(
            {"country_a_id": "uint16", "country_b_id": "uint16", "correlation": "float32"}
        )

    # Stack to long format. NaN correlations (insufficient overlap) are
    # dropped after the stack — pairs without enough overlap would not
    # contribute to Phase 6 anyway.
    # `future_stack=True` adopts pandas 2.1+ semantics (the legacy
    # `dropna=True` arg is deprecated and the new path matches our
    # intent: keep NaN, then drop explicitly so the behavior is visible).
    #
    # rename_axis BEFORE stack: production panels are pivoted from a
    # long frame with `pivot_table(columns="country", ...)`, which sets
    # BOTH the index name AND the columns axis name to "country" on the
    # subsequent panel.corr() result. Stacking + reset_index then tries
    # to insert two columns both called "country" and raises
    # `ValueError: cannot insert country, already exists`. Synthetic
    # test panels avoided this because they were built with
    # `pd.DataFrame(data, index=...)` without a named columns axis —
    # see test gap closed in tests/unit/dscdi-finder/conftest.py.
    long_form = (
        corr_matrix.rename_axis(index="country_a_label", columns="country_b_label")
        .stack(future_stack=True)
        .dropna()
        .rename("correlation")
        .reset_index()
    )

    # Drop self-correlation (always 1.0 for non-NaN diagonal cells)
    long_form = long_form[long_form["country_a_label"] != long_form["country_b_label"]]

    # NaN guard (M-1): every label must map to a numeric ID. Detect
    # unmapped labels BEFORE casting to uint16.
    all_labels = set(long_form["country_a_label"]).union(long_form["country_b_label"])
    unknown = sorted(all_labels - countries_map.keys())
    if unknown:
        raise ValueError(
            f"country labels in correlation matrix not found in countries_map: "
            f"{unknown[:10]}{'...' if len(unknown) > 10 else ''} "
            f"({len(unknown)} total). The panel parquet has country names "
            f"that diverge from countries.csv name_1 — check upstream "
            f"ingestion before continuing."
        )

    long_form["country_a_id"] = long_form["country_a_label"].map(countries_map).astype("uint16")
    long_form["country_b_id"] = long_form["country_b_label"].map(countries_map).astype("uint16")
    long_form["correlation"] = long_form["correlation"].astype("float32")

    return long_form[["country_a_id", "country_b_id", "correlation"]].reset_index(drop=True)


def build_pairwise_rows(
    result: dscdi_finder.DSCDIResult,
    indicator_numeric_id: int,
    countries_map: dict[str, int],
) -> pd.DataFrame:
    """Build the long-format pairwise rows for the dscdis Glue table.

    For Class A indicators where demeaning was applied, emits TWO row
    sets (Miriam's three-substrate ablation):
      - is_demeaned=True rows from result.primary (the demeaned canonical)
      - is_demeaned=False rows from result.baseline_undemeaned (Pass 1)

    For Class B/C and the NY.GDP.MKTP.KD.ZG special case, emits ONE row
    set with is_demeaned=False (no baseline substrate exists).
    """
    indicator_class = result.disposition.indicator_class

    primary_long = _matrix_to_long(result.primary, countries_map)
    primary_long["indicator_numeric_id"] = np.uint16(indicator_numeric_id)
    primary_long["contains_predicted"] = False  # v0 sentinel; D7 future-wire TODO
    primary_long["is_demeaned"] = result.demeaning_applied
    primary_long["indicator_class"] = indicator_class

    if result.baseline_undemeaned is not None:
        baseline_long = _matrix_to_long(result.baseline_undemeaned, countries_map)
        baseline_long["indicator_numeric_id"] = np.uint16(indicator_numeric_id)
        baseline_long["contains_predicted"] = False
        baseline_long["is_demeaned"] = False  # explicit: this IS the undemeaned pass
        baseline_long["indicator_class"] = indicator_class
        return pd.concat([primary_long, baseline_long], ignore_index=True)

    return primary_long


# ---------------------------------------------------------------------------
# Section 7 — Write pairwise output partitioned by country_a_id
# ---------------------------------------------------------------------------
_VALID_INDICATOR_CLASSES = frozenset({"A", "B", "C"})


def write_pairwise_output(output: pd.DataFrame, bucket: str, prefix: str, indicator_id: str) -> int:
    """Group output by country_a_id and write one Parquet per partition.

    Returns the number of partition files written (zero if output is empty).
    """
    if output.empty:
        logger.info(f"[write_pairwise_output] {indicator_id}: empty output, no files written")
        return 0

    # Writer-side runtime assertion (Flag 1 of #613). The IndicatorClass
    # Literal["A", "B", "C"] in dscdi_finder.py is a type-check-time guarantee
    # only; Python doesn't enforce Literal at runtime, so a future writer bug
    # emitting "a" / "Class A" / "" / numpy.nan would silently mis-filter
    # downstream Athena queries (WHERE indicator_class = 'A'). Glue/Hive
    # Metastore doesn't support CHECK constraints natively, so this is the
    # canonical enforcement point.
    bad_classes = sorted(set(output["indicator_class"].astype(str).unique()) - _VALID_INDICATOR_CLASSES)
    if bad_classes:
        raise ValueError(
            f"writer emitted indicator_class values outside the {{A, B, C}} "
            f"vocabulary: {bad_classes}. Glue/Athena downstream filters will "
            f"silently exclude these rows. Indicator: {indicator_id}."
        )

    n_files = 0
    for country_a_id, group in output.groupby("country_a_id"):
        group_data = group.drop(columns=["country_a_id"]).reset_index(drop=True)
        key = f"{prefix.rstrip('/')}/country_a_id={int(country_a_id)}/{indicator_id}.parquet"
        buf = BytesIO()
        group_data.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
        buf.seek(0)
        s3_client.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())
        n_files += 1

    logger.info(
        f"[write_pairwise_output] {indicator_id}: wrote {n_files} "
        f"country_a_id partitions ({len(output)} pair rows total)"
    )
    return n_files


# ---------------------------------------------------------------------------
# Section 8 — Write per-indicator manifest fragment
# ---------------------------------------------------------------------------
# Map of suppressed_reason values per the qgi-infra schema producer
# contract (modules/storage/main.tf dscdi_indicator_manifest comment).
def _suppressed_reason(indicator_id: str, demeaning_applied: bool) -> str | None:
    """Derive the suppressed_reason column at write time.

    Returns the reason demeaning was suppressed for an otherwise-Class-A
    indicator. Returns None when demeaning was applied (the canonical
    Class A path) or when the indicator is Class B/C (demeaning was
    never expected; suppressed_reason is meaningful only for Class A).

    Note: when demeaning_applied=True AND demeaning_insufficient=True (the
    4 Stage E flagged indicators), suppressed_reason is still None — use
    the demeaning_insufficient column for that signal. suppressed_reason
    answers "why was demeaning not done" specifically.
    """
    if demeaning_applied:
        return None
    if indicator_id in dscdi_finder.OUTLIER_NO_TRANSFORM:
        return "no_transform_outlier"
    # Class B/C: demeaning never expected, no suppression to report.
    return None


def write_manifest(result: dscdi_finder.DSCDIResult, bucket: str, prefix: str) -> str:
    """Write the per-indicator manifest fragment to S3.

    Single-row Parquet at {prefix}{indicator_id}.parquet. The unpartitioned
    Glue table dscdi_indicator_manifest reads all 109 fragments unioned.
    Idempotent: re-running a Batch job overwrites the same key.
    """
    indicator_id = result.indicator_id
    row = {
        "indicator_id": indicator_id,
        "indicator_class": result.disposition.indicator_class,
        "transform": result.disposition.transform,
        "n_countries": int(result.n_countries),
        "mean_abs_pairwise_corr": float(result.mean_abs_pairwise_corr),
        "demeaning_applied": bool(result.demeaning_applied),
        "demeaning_insufficient": bool(result.demeaning_insufficient),
        "suppressed_reason": _suppressed_reason(indicator_id, result.demeaning_applied),
    }
    df = pd.DataFrame([row])
    # Glue manifest schema: n_countries=bigint matches pandas int64 default;
    # mean_abs_pairwise_corr=double matches pandas float64 default. No
    # explicit casts needed (uint16-style precision tightening would
    # downcast n_countries to int32 which Athena reads as INT, breaking
    # the bigint contract).

    # Trailing slash on prefix → join directly without re-adding separator.
    # Matches qgi-infra PR-2b MANIFEST_S3_PREFIX env var convention.
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    key = f"{prefix}{indicator_id}.parquet"

    buf = BytesIO()
    df.to_parquet(buf, engine="pyarrow", compression="snappy", index=False)
    buf.seek(0)
    s3_client.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())
    logger.info(f"[write_manifest] wrote s3://{bucket}/{key}")
    return key


# ---------------------------------------------------------------------------
# Section 9 — main()
# ---------------------------------------------------------------------------
def main() -> int:
    """End-to-end DSCDI Batch job for one indicator.

    Returns the process exit code (0 success, 1 on error).
    """
    if not S3_BUCKET:
        logger.error("S3_BUCKET env var is required")
        return 1
    if not INDICATOR_ID:
        logger.error("INDICATOR_ID env var is required")
        return 1

    logger.info(f"--- Starting DSCDI Finder Job for Indicator: {INDICATOR_ID} ---")
    logger.info(
        f"S3_BUCKET={S3_BUCKET} S3_INPUT_PREFIX={S3_INPUT_PREFIX} "
        f"S3_OUTPUT_PREFIX={S3_OUTPUT_PREFIX} "
        f"MANIFEST_S3_PREFIX={MANIFEST_S3_PREFIX} "
        f"AUDIT_JSON_S3_KEY={AUDIT_JSON_S3_KEY} MIN_LENGTH={MIN_LENGTH}"
    )

    panel = load_panel(S3_BUCKET, S3_INPUT_PREFIX, INDICATOR_ID)
    audit_classifications = load_audit(S3_BUCKET, AUDIT_JSON_S3_KEY)
    indicator_map = load_indicator_map(S3_BUCKET)
    countries_map = load_countries_map(S3_BUCKET)

    if INDICATOR_ID not in audit_classifications:
        logger.error(
            f"INDICATOR_ID {INDICATOR_ID!r} not in audit JSON "
            f"(or filtered out for load_failed/test_failed/insufficient_data)."
        )
        return 1
    classification = audit_classifications[INDICATOR_ID]

    if INDICATOR_ID not in indicator_map:
        logger.error(f"INDICATOR_ID {INDICATOR_ID!r} not found in indicator_map.csv")
        return 1
    indicator_numeric_id = int(indicator_map[INDICATOR_ID])

    logger.info(
        f"Running run_dscdi_pass(indicator_id={INDICATOR_ID}, "
        f"audit_classification={classification!r}, min_obs={MIN_LENGTH})"
    )
    result = dscdi_finder.run_dscdi_pass(
        indicator_id=INDICATOR_ID,
        panel=panel,
        audit_classification=classification,
        min_obs=MIN_LENGTH,
    )
    logger.info(
        f"DSCDIResult: class={result.disposition.indicator_class} "
        f"transform={result.disposition.transform} "
        f"n_countries={result.n_countries} "
        f"demeaning_applied={result.demeaning_applied} "
        f"mean_abs_pairwise_corr={result.mean_abs_pairwise_corr:.6f} "
        f"demeaning_insufficient={result.demeaning_insufficient}"
    )

    output = build_pairwise_rows(result, indicator_numeric_id, countries_map)
    n_files = write_pairwise_output(output, S3_BUCKET, S3_OUTPUT_PREFIX, INDICATOR_ID)
    manifest_key = write_manifest(result, S3_BUCKET, MANIFEST_S3_PREFIX)

    logger.info(
        f"--- DSCDI Finder Job COMPLETE for {INDICATOR_ID}: {n_files} partition files + manifest at {manifest_key} ---"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        logger.exception("DSCDI entrypoint crashed")
        sys.exit(1)
