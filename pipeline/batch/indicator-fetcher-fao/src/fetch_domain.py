#!/usr/bin/env python3
"""
Phase 1 — FAOSTAT domain fetcher (one Fargate Spot task per FAOSTAT domain).

Sibling to batch/indicator-fetcher/src/fetch_one.py (the per-indicator
World Bank fetcher). FAOSTAT's bulk-download pattern is different:
each domain (FS, RL, RFB, TM, PP, Forestry, GT, QCL) exposes ONE ZIP
file containing all indicators, years, and countries in that domain.
Downloading 8 domain ZIPs is far more efficient than 15 per-indicator
API calls, which is why this fetcher is invoked per-domain, not
per-indicator.

## Inputs (env vars set by dispatcher, #240 Phase A)

- DOMAIN_CODE       — e.g., "FS" (Food Security). Drives the ZIP URL.
- INDICATORS_JSON   — JSON array of indicator specs in this domain:
  ``[{"id_string": "FA-01", "numeric_id": 59,
      "item_code": 21010, "element_code": 6121}, ...]``
  The fetcher filters the domain CSV to rows matching
  ``(item_code, element_code)`` per indicator and emits one Parquet
  per indicator id_string (matching the WB layout).
- RUN_ID            — Step Function execution ID, used for tracker rows.
- S3_BUCKET         — data-lake bucket.
- COUNTER_TABLE, TRACKER_TABLE, INDICATOR_VALUES_TABLE — DDB tables
  (same ones the WB fetcher writes to).

## Output layout (matches WB fetcher, so downstream Phase 2/3 are
blind to the source)

``s3://{BUCKET}/pipeline-A-indicator-extractor/output/parquet/{id_string}/year=YYYY/country=XXX/data.parquet``

One Parquet file per (indicator, year, country) partition. Keeps the
Glue table's partition key scheme identical to the WB side.

## Failure handling

- L1: 5 exponential-backoff retries on the domain ZIP download
- L2: Batch job retry (attempts=2, same as WB — timeouts aren't
  transient). Hard-killed tasks are caught by the #243 EventBridge
  failure-handler Lambda which writes FAILED tracker rows externally.
- L3: best-effort counter decrement on any uncaught exception so the
  Phase 1 checker doesn't hang waiting for a dead task.
- L4: per-indicator decrement (this task writes N tracker rows and
  decrements the counter by N — one per indicator in INDICATORS_JSON).

## Country code mapping

FAOSTAT uses its own "area code" numbering distinct from both UN M49
and ISO 3166. The mapping lives in ``qgi-data/registries/country-m49-map.csv``
which the fetcher reads from S3 at startup. Area codes that don't map
to a QGI canonical country (e.g., regional aggregates like "Africa")
are dropped.
"""

import json
import logging
import os
import random
import re
import sys
import time
import traceback
import zipfile
from decimal import Decimal
from io import BytesIO, StringIO

import boto3
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

REGION = os.environ.get("AWS_REGION", "eu-central-1")
BUCKET = os.environ["S3_BUCKET"]
RUN_ID = os.environ["RUN_ID"]
DOMAIN_CODE = os.environ["DOMAIN_CODE"]
INDICATORS_JSON_RAW = os.environ["INDICATORS_JSON"]

COUNTER_TABLE = os.environ.get("COUNTER_TABLE", "qgi-pipeline-a-counter")
TRACKER_TABLE = os.environ.get("TRACKER_TABLE", "qgi-indicator-updates")
INDICATOR_VALUES_TABLE = os.environ.get("INDICATOR_VALUES_TABLE", "qgi-indicator-values")

# FAOSTAT bulk-download URL template (updated 2026-04-20 Phase B smoke test).
#
# FAOSTAT retired ``https://bulks-faostat.fao.org/production/{DOMAIN_CODE}...``
# sometime after the original design — both the host and the filename
# prefix changed. The current (working) path is
# ``https://fenixservices.fao.org/faostat/static/bulkdownloads/{Domain_Full_Name}_E_All_Data_(Normalized).zip``
# where ``Domain_Full_Name`` is the human-readable domain name with
# underscores (e.g. ``Food_Security_Data``, not the short code ``FS``).
#
# We keep short codes in the XLSX and map to full names here. If a
# domain we haven't mapped yet is requested, the fetcher raises a
# descriptive error pointing at this block. To extend: append to
# ``_FAO_DOMAIN_FULL_NAMES`` — no code change elsewhere.
FAO_BULK_URL_TEMPLATE = os.environ.get(
    "FAO_BULK_URL_TEMPLATE",
    "https://fenixservices.fao.org/faostat/static/bulkdownloads/{domain_full}_E_All_Data_(Normalized).zip",
)

# Short domain code (as written in the XLSX) → full name used in the
# FAOSTAT bulk-download URL. Start small; extend as more FAO domains
# land in the catalog. Extracted from the FAOSTAT bulk-downloads page.
_FAO_DOMAIN_FULL_NAMES = {
    "FS": "Food_Security_Data",  # Suite of Food Security Indicators
    # Future (verify at https://www.fao.org/faostat/en/#data before use):
    # "RL":     "Inputs_LandUse",
    # "RFB":    "FertilizersProduct",        # or Inputs_FertilizersArchive
    # "TM":     "Trade_DetailedTradeMatrix",
    # "PP":     "Prices",
    # "QCL":    "Production_Crops_Livestock",
    # "GT":     "Emissions_Totals",
    # "Forestry":"Forestry",
}

# Browser-like User-Agent — some FAOSTAT CDNs (and many other bulk hosts)
# block the default ``python-requests/X.Y.Z`` UA.
_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QGI-pipeline/1.0; +https://qgintelligence.com)",
}

JITTER_MIN_S = int(os.environ.get("JITTER_MIN_S", "60"))
JITTER_MAX_S = int(os.environ.get("JITTER_MAX_S", "300"))
MAX_FETCH_ATTEMPTS = int(os.environ.get("MAX_FETCH_ATTEMPTS", "5"))

S3_OUTPUT_PREFIX = "pipeline-A-indicator-extractor/output"
# Country code map lives in qgi-data-synced-to-S3 at a deterministic key
# so the fetcher doesn't need the qgi-data repo mounted. Produced by
# qgi-data/scripts/sync_curated_events.py (extended) — see #241.
# NOTE (2026-04-20): moved out of ``input/`` prefix because the Glue
# ``qgi_data.countries`` table scans that prefix recursively and
# fails Phase 5b.4 Seed CTAS with ``INVALID_CAST_ARGUMENT: Cannot
# cast 'Afghanistan' to INT`` when the m49 map's ``qgi_name`` column
# lands in Glue's expected ``id`` column position. Keeping this file
# in ``registries/`` avoids the pollution.
COUNTRY_M49_MAP_KEY = "pipeline-A-indicator-extractor/registries/country-m49-map.csv"


# ---------------------------------------------------------------------------
# Boto3 clients
# ---------------------------------------------------------------------------

s3 = boto3.client("s3", region_name=REGION)
dynamodb_resource = boto3.resource("dynamodb", region_name=REGION)

counter_table = dynamodb_resource.Table(COUNTER_TABLE)
tracker_table = dynamodb_resource.Table(TRACKER_TABLE)
indicator_values_table = dynamodb_resource.Table(INDICATOR_VALUES_TABLE)


# ---------------------------------------------------------------------------
# Country mapping
# ---------------------------------------------------------------------------


def load_canonical_country_names() -> dict[int, str]:
    """Return ``{qgi_country_id: canonical_name_1}`` from countries.csv.

    The WB fetcher writes the canonical ``name_1`` column from
    ``pipeline-A-indicator-extractor/input/countries.csv`` as its
    Parquet ``country`` column (see ``fetch_one.py`` ``get_country_mapping``).
    The FAOSTAT fetcher must do the same so the two providers'
    Parquet outputs share a column contract — Phase 2 SCDI joins on
    ``country`` (string), not on ``country_id`` (integer).

    If a qgi_country_id appears in the m49 country map but not in
    countries.csv (shouldn't happen, but defensive), the row is
    dropped upstream with a WARNING.
    """
    # #413 — canonical path after #370 dual-location consolidation.
    # Was `pipeline-A-indicator-extractor/input/countries.csv`; moved
    # to a dedicated prefix because the shared `input/` prefix can
    # receive any indicator-map CSV (Phase 1 surface).
    key = "pipeline-A-indicator-extractor/countries/countries.csv"
    logger.info(f"Loading canonical country names from s3://{BUCKET}/{key}")
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    df = pd.read_csv(BytesIO(obj["Body"].read()))
    if "id" not in df.columns or "name_1" not in df.columns:
        raise ValueError(f"countries.csv missing id/name_1 columns. Found: {df.columns.tolist()}")
    out = {int(row["id"]): str(row["name_1"]) for _, row in df.iterrows()}
    logger.info(f"Loaded {len(out)} canonical country names")
    return out


def load_country_map() -> dict[int, dict]:
    """Return ``{fao_area_code: {qgi_country_id, qgi_name, iso_alpha3}}``.

    Entries where fao_area_code is empty (Kosovo) are skipped because
    the lookup key wouldn't match anything in the FAOSTAT data anyway.
    """
    logger.info(f"Loading country map from s3://{BUCKET}/{COUNTRY_M49_MAP_KEY}")
    obj = s3.get_object(Bucket=BUCKET, Key=COUNTRY_M49_MAP_KEY)
    df = pd.read_csv(obj["Body"])
    out: dict[int, dict] = {}
    for _, row in df.iterrows():
        fao = row.get("fao_area_code")
        # Skip rows without a FAO code (Kosovo)
        if pd.isna(fao) or fao == "":
            continue
        out[int(fao)] = {
            "qgi_country_id": int(row["qgi_country_id"]),
            "qgi_name": str(row["qgi_name"]),
            "iso_alpha3": str(row.get("iso_alpha3") or ""),
        }
    logger.info(f"Loaded {len(out)} FAO→QGI country mappings")
    return out


# ---------------------------------------------------------------------------
# FAOSTAT download + extract
# ---------------------------------------------------------------------------


def _jitter_sleep() -> None:
    """Random 60-300s sleep before the HTTP call. Matches the WB fetcher's
    rate-limiting-via-distribution pattern. FAOSTAT doesn't rate-limit
    as aggressively as WB but the pattern keeps the 8 parallel domain
    tasks from hitting the CDN at the exact same second."""
    jitter = random.uniform(JITTER_MIN_S, JITTER_MAX_S)
    logger.info(f"Jitter sleep {jitter:.1f}s before domain download")
    time.sleep(jitter)


def fetch_domain_csv(domain_code: str) -> bytes:
    """Download the FAOSTAT domain ZIP and return the extracted CSV bytes.

    FAOSTAT bulk ZIPs contain at least one main CSV (we select the first
    non-flags .csv in the ZIP via a heuristic — the filename prefix
    matches the full domain name, not the short code). Returns the raw
    CSV bytes (may be large — 50-200MB).
    """
    domain_full = _FAO_DOMAIN_FULL_NAMES.get(domain_code)
    if domain_full is None:
        raise RuntimeError(
            f"Unknown FAOSTAT domain {domain_code!r}. Add it to "
            f"_FAO_DOMAIN_FULL_NAMES in fetch_domain.py — see the "
            f"comment above that dict for the FAOSTAT URL convention."
        )
    url = FAO_BULK_URL_TEMPLATE.format(domain_full=domain_full)
    logger.info(f"Downloading FAOSTAT domain {domain_code} (full={domain_full!r}) from {url}")
    last_exc: Exception | None = None
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            # 5-minute timeout — large ZIPs on the FAO CDN can be slow.
            # The Fargate task has a 60-min overall timeout so this is
            # conservatively inside that budget.
            resp = requests.get(url, timeout=300, headers=_HTTP_HEADERS)
            resp.raise_for_status()
            logger.info(f"Downloaded {len(resp.content):,} bytes in attempt {attempt}")
            with zipfile.ZipFile(BytesIO(resp.content)) as zf:
                # Heuristic: pick the *.csv that's NOT a flags-only file.
                # FAOSTAT bulk ZIPs sometimes include a separate flags CSV
                # (e.g., FS_E_Flags.csv) we don't need.
                csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv") and "_flag" not in n.lower()]
                if not csv_names:
                    raise RuntimeError(f"No main CSV found in {domain_code} ZIP. Contents: {zf.namelist()}")
                csv_name = csv_names[0]
                logger.info(f"Extracting {csv_name} from ZIP")
                return zf.read(csv_name)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            backoff = min(60, 2**attempt)
            logger.warning(f"Attempt {attempt}/{MAX_FETCH_ATTEMPTS} failed: {exc}. Backing off {backoff}s")
            time.sleep(backoff)
    raise RuntimeError(f"FAOSTAT download for {domain_code} failed after {MAX_FETCH_ATTEMPTS} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Indicator extraction + write
# ---------------------------------------------------------------------------


def extract_indicator(
    df_domain: pd.DataFrame,
    indicator_spec: dict,
    country_map: dict[int, dict],
    canonical_names: dict[int, str],
) -> pd.DataFrame:
    """Filter the domain-wide CSV to one indicator's rows and attach
    canonical country names. Returns a DataFrame with columns:
    ``(country, year, value)`` — matching the WB fetcher's column
    contract exactly so Phase 2 SCDI is provider-agnostic.

    ``indicator_spec`` must have item + element codes. Both short
    (``item_code`` / ``element_code``) and XLSX-native long
    (``fao_item_code`` / ``fao_element_code``) keys are accepted —
    dispatcher pass-through preserves the XLSX column names verbatim,
    so the long form is what arrives in practice. The short form is
    retained for hand-authored smoke tests and legacy payloads.
    """

    def _coerce(spec: dict, *candidates: str) -> int:
        for key in candidates:
            if key in spec and spec[key] is not None:
                return int(spec[key])
        raise KeyError(
            f"Indicator {spec.get('id_string', '?')!r} missing required "
            f"FAOSTAT code: tried {candidates}. Keys present: {list(spec)}"
        )

    item_code = _coerce(indicator_spec, "item_code", "fao_item_code")
    element_code = _coerce(indicator_spec, "element_code", "fao_element_code")

    # Compare as strings. FAOSTAT item codes are a mix of pure ints
    # ("21010") and int-with-letter-suffix ("210401M", "210400TSUB"),
    # so pandas loads the column as `object` dtype. An `int == object`
    # comparison silently returns all-False rather than raising, which
    # bit us during the #241 Phase B smoke test (every indicator looked
    # like "0 rows matched"). Coercing both sides to str gives reliable
    # equality and will still work if we later add string-coded
    # indicators in the catalog.
    item_code_s = str(item_code)
    element_code_s = str(element_code)
    subset = df_domain[
        (df_domain["Item Code"].astype(str) == item_code_s) & (df_domain["Element Code"].astype(str) == element_code_s)
    ].copy()

    if subset.empty:
        logger.warning(
            f"Indicator {indicator_spec['id_string']} (item={item_code}, "
            f"element={element_code}) returned 0 rows from domain CSV"
        )
        return pd.DataFrame(columns=["country_id", "country_name", "year", "value"])

    # Map FAOSTAT "Area Code" to QGI country_id. Drop unmapped rows
    # (regional aggregates, USSR pre-1991, etc.).
    def _mapper(area_code):
        entry = country_map.get(int(area_code)) if pd.notna(area_code) else None
        return entry

    subset["_qgi"] = subset["Area Code"].apply(_mapper)
    before = len(subset)
    subset = subset[subset["_qgi"].notna()]
    after = len(subset)
    if before != after:
        logger.info(f"  Dropped {before - after} rows with unmapped FAO area codes (regional aggregates, etc.)")

    subset["country_id"] = subset["_qgi"].apply(lambda x: x["qgi_country_id"])
    # Canonical country name from countries.csv ``name_1`` — the
    # authoritative source the WB fetcher uses. Drop rows whose
    # qgi_country_id is in the m49 map but missing from countries.csv
    # (structural gap; should not happen in practice but logged).
    subset["country"] = subset["country_id"].map(canonical_names)
    missing_canon = subset["country"].isna().sum()
    if missing_canon:
        dropped_ids = sorted(subset.loc[subset["country"].isna(), "country_id"].unique().tolist())
        logger.warning(
            f"  {missing_canon} rows dropped — qgi_country_ids {dropped_ids[:10]} "
            f"present in m49 map but missing from countries.csv"
        )
        subset = subset.dropna(subset=["country"])

    # Year normalization.
    #
    # FAOSTAT domains mix two year encodings:
    #   * single year: ``Year`` = "2023", ``Year Code`` = 2023
    #   * 3-year average (FS, some others): ``Year`` = "2000-2002"
    #     (range string, not int-castable), ``Year Code`` = 20002002
    #     (concat of start+end).
    # We use ``Year Code`` as the authoritative numeric year because
    # it's always integer-castable. For ranges we take the END year
    # (the last 4 digits) — that matches FAOSTAT's convention of
    # labelling 3-year averages by their terminal year, and keeps
    # the Parquet partition layout (``year=YYYY``) stable across
    # single-year and range indicators.
    def _end_year_from_code(yc):
        s = str(int(yc))  # "20002002" or "2023"
        return int(s[-4:])

    subset["year"] = subset["Year Code"].apply(_end_year_from_code)
    subset = subset.rename(columns={"Value": "value"})

    # F4 — Source-type classification (annual vs 3yr_avg) + provenance flag.
    #
    # FAOSTAT bulk CSVs have two orthogonal signals about each row:
    #   (a) Year shape — derived from ``Year Code`` length:
    #       * ``annual``  — single-year observation (Year Code = 4 digits)
    #       * ``3yr_avg`` — 3-year rolling average (Year Code = 8 digits,
    #         concat of start+end; ``Year`` column is a range like
    #         "2020-2022"). These have mechanical autocorrelation of
    #         ~0.67 between neighbouring end-years even in an IID
    #         series, which Phase 2 Pearson SCDI cannot tell apart
    #         from real signal.
    #   (b) Value provenance — ``Flag`` column: ``"E"`` means FAO
    #       computed this value (model / imputation), blank / other
    #       means it was directly reported by the country.
    #
    # These are INDEPENDENT. An ``annual`` row can be ``fao_estimate``
    # (e.g., single-year nowcast), and a ``3yr_avg`` row can be
    # directly reported. We track them as two columns so downstream
    # code makes the right decisions:
    #   * First-differencing targets ``3yr_avg`` shape (autocorrelation
    #     mitigation), regardless of ``is_estimate``
    #   * Dedup priority on collisions: prefer ``annual`` over ``3yr_avg``
    #     (shape first); within same shape, prefer reported over estimate.
    #
    # (An earlier revision collapsed both into one column with
    # priority ``annual > fao_estimate > 3yr_avg``. That was wrong —
    # it silently kept 3yr_avg data UN-differenced whenever the Flag
    # column was ``"E"``, which is nearly 100% of indicators in the
    # FS domain. Dry-run surfaced the bug before commit.)
    _yc_len = subset["Year Code"].astype(str).str.len()
    subset["source_type"] = _yc_len.map({4: "annual", 8: "3yr_avg"}).fillna(
        "3yr_avg"
    )  # unknown length defaults to 3yr_avg (conservative)
    subset["is_estimate"] = subset.get("Flag", pd.Series(dtype=str)).astype(str).str.upper() == "E"
    logger.info(
        f"  Source-type mix: "
        f"shape={subset['source_type'].value_counts().to_dict()}; "
        f"is_estimate={int(subset['is_estimate'].sum())}/{len(subset)}"
    )

    # Value coercion to numeric.
    #
    # FAOSTAT ``Value`` cells contain a mix of:
    #   * pure numerics ("87", "29.5") — the common case
    #   * below-detection-limit sentinels ("<0.1", "<0.5") — LEFT-
    #     CENSORED observations. Dropping them silently removes
    #     food-secure countries (Norway, Japan, Singapore) from the
    #     SCDI graph — a reporting bias the three expert reviewers
    #     (UN/MIT/TUM) all flagged as unacceptable. Epidemiology
    #     convention: impute as half the detection limit (0.1 -> 0.05).
    #   * suppression sentinels ("...", "..") — MNAR (Missing Not At
    #     Random, typically low-capacity statistical systems or
    #     confidentiality). Drop with a separate counter so the ops
    #     report can distinguish data gaps from censoring.
    #   * unknown flag characters — anything else non-numeric. Drop
    #     and log so a future FAOSTAT schema change does not
    #     silently evaporate rows.
    #
    # Without this block every Parquet's ``value`` column is written
    # as object (string) dtype, which Phase 2 SCDI cannot compute
    # Pearson on. Blocker for the #241 Phase B full pipeline run.
    raw = subset["value"].astype(str)

    # Pass 1: below-detection ("<0.1") -> half-limit ("0.05"). Do this
    # BEFORE numeric coercion so these cells survive as real floats.
    _BELOW_DETECT = raw.str.match(r"^\s*<\s*\d+\.?\d*\s*$", na=False)
    if _BELOW_DETECT.any():

        def _half_limit(s: str) -> str:
            m = re.match(r"^\s*<\s*(\d+\.?\d*)\s*$", s)
            return str(float(m.group(1)) / 2.0) if m else s

        subset.loc[_BELOW_DETECT, "value"] = raw[_BELOW_DETECT].apply(_half_limit)

    # Pass 2: identify suppression and unknown tokens BEFORE coercion
    # so we can count them distinctly for ops reporting.
    numeric = pd.to_numeric(subset["value"], errors="coerce")
    _NUMERIC_OK = numeric.notna()
    _SUPPRESSED = ~_NUMERIC_OK & raw.str.match(r"^\s*\.{2,3}\s*$", na=False)
    _UNKNOWN = ~_NUMERIC_OK & ~_SUPPRESSED

    n_below_detect = int(_BELOW_DETECT.sum())
    n_suppressed = int(_SUPPRESSED.sum())
    n_unknown = int(_UNKNOWN.sum())
    logger.info(
        f"  Value coercion: {n_below_detect} '<X' -> X/2; "
        f"{n_suppressed} suppressed ('...') dropped; "
        f"{n_unknown} unknown-flag rows dropped; "
        f"{int(_NUMERIC_OK.sum())} rows retained as numeric"
    )
    if n_unknown:
        # Log up to 5 examples so a schema change is discoverable.
        examples = raw[_UNKNOWN].drop_duplicates().head(5).tolist()
        logger.warning(f"  Unknown non-numeric tokens in Value column (first 5 distinct): {examples}")

    # Force float64 always — pandas would infer int64 if all remaining
    # values happen to be integer-valued (e.g., Avg Dietary Energy Supply
    # Adequacy is whole percentages). WB fetcher writes float64 for every
    # indicator. Keeping both providers on the same Parquet ``value``
    # dtype lets Athena UNION WB and FAOSTAT rows in a single Glue
    # partitioned table without schema-evolution compromises.
    subset["value"] = numeric.astype("float64")
    subset = subset.dropna(subset=["value"])

    # F4 — Dedup collisions on (country, year) using source_type + is_estimate.
    #
    # When both an annual and a 3yr_avg row exist for the same
    # (country, year), keep the higher-priority one. Priority order:
    #   1. ``annual`` beats ``3yr_avg`` (shape-based; the annual row
    #      is the direct observation and is not inflated by smoothing)
    #   2. Within same shape: directly reported (is_estimate=False)
    #      beats FAO-computed (is_estimate=True)
    #
    # Ordered categorical sort makes this deterministic and
    # auditable — expert consensus (UN/MIT/TUM) was unanimous that
    # the previous sort-by-Year-Code heuristic was fragile to
    # FAOSTAT API row-order changes.
    _SHAPE_PRIORITY = ["annual", "3yr_avg"]
    subset["_sort_shape"] = pd.Categorical(subset["source_type"], categories=_SHAPE_PRIORITY, ordered=True)
    # is_estimate=False (reported) sorts before True (estimated)
    subset["_sort_est"] = subset["is_estimate"].astype(int)
    _before = len(subset)
    subset = (
        subset.sort_values(["country", "year", "_sort_shape", "_sort_est"])
        .drop_duplicates(subset=["country", "year"], keep="first")
        .drop(columns=["_sort_shape", "_sort_est"])
    )
    _dedup = _before - len(subset)
    if _dedup:
        logger.info(
            f"  Dedup: dropped {_dedup} (country, year) collisions "
            f"(annual preferred over 3yr_avg; reported over estimate)"
        )

    # F1 — First-difference rolling-average series to break the
    # mechanical autocorrelation induced by the 3-year smoothing window.
    #
    # The three expert reviewers (UN/MIT/TUM) were unanimous that
    # applying Pearson correlation directly to overlapping-window 3YA
    # series produces spurious SCDIs — a moving-average over an AR(1)
    # process inflates lag-1 autocorrelation from φ to (1+2φ)/3 ≈
    # 0.53 at φ=0.3, well above the SCDI threshold of 0.5 with zero
    # underlying signal.
    #
    # We first-difference PER-COUNTRY so each country's series
    # becomes year-over-year change. ``annual`` series do NOT need
    # this transform (they have no induced autocorrelation) — but
    # note that raw annual levels can still be spuriously correlated
    # via shared trend. That's a separate concern (deferred to
    # post-V1 via first-differencing all level indicators + ADF
    # test per series). For smoke we only diff ``3yr_avg`` rows.
    _is_3ya = subset["source_type"] == "3yr_avg"
    if _is_3ya.any():
        # Apply within each country: sort, diff, drop leading NaN.
        subset = subset.sort_values(["country", "year"]).reset_index(drop=True)
        diff_mask = subset["source_type"] == "3yr_avg"
        subset.loc[diff_mask, "value"] = subset.loc[diff_mask].groupby("country")["value"].diff()
        _before_diff = len(subset)
        subset = subset.dropna(subset=["value"]).reset_index(drop=True)
        logger.info(
            f"  First-diff: {diff_mask.sum()} 3yr_avg rows transformed "
            f"to year-over-year change; {_before_diff - len(subset)} "
            f"leading-year NaNs dropped"
        )

    # F2 — Variance floor filter.
    #
    # After <X imputation at L/2, some country-series collapse to
    # near-constant values (e.g., Norway's FIES prevalence stays at
    # 0.05 across all years after imputation). A series with
    # std ≈ 0 has undefined Pearson correlation and wastes SCDI
    # compute. Drop country-groups whose within-series std is below
    # a small floor. ε = 1e-6 is enough to keep any genuinely varying
    # series while excluding pure imputation artifacts.
    _VARIANCE_FLOOR = 1e-6
    _stds = subset.groupby("country")["value"].transform("std")
    _flat_mask = _stds.fillna(0) < _VARIANCE_FLOOR
    n_flat_dropped = int(_flat_mask.sum())
    if n_flat_dropped:
        flat_countries = subset.loc[_flat_mask, "country"].drop_duplicates().head(10).tolist()
        logger.info(
            f"  Variance floor: dropped {n_flat_dropped} rows from "
            f"{len(flat_countries)}+ flat-series countries "
            f"(first 10: {flat_countries})"
        )
        subset = subset[~_flat_mask].reset_index(drop=True)

    return subset[["country", "year", "value", "source_type", "is_estimate"]]


def write_parquet(
    df_indicator: pd.DataFrame,
    indicator_spec: dict,
) -> int:
    """Write ONE Parquet per indicator at the WB-compatible path.

    Layout (#241 Phase B F6, 2026-04-20 rewrite — was partitioned
    tree, now single file):

        s3://{BUCKET}/pipeline-A-indicator-extractor/output/parquet-completed/{id_string}/{id_string}.parquet

    Schema (must exactly match ``batch/indicator-fetcher/src/fetch_one.py``
    so Phase 2 SCDI reads both providers identically):

        country      : object (string, canonical name_1 from countries.csv)
        year         : int64
        value        : float64
        is_predicted : bool  (always False for FAOSTAT — raw data, no projections)

    The previous partitioned layout (``parquet/{id}/year=Y/country=C/data.parquet``)
    was incompatible with the SCDI finder's single-file read pattern
    (``fetch_one.py`` & ``scdi_finder.py`` load the whole indicator's
    series in one S3 GET). Returns 1 on successful write, 0 if the
    DataFrame is empty.
    """
    id_string = indicator_spec["id_string"]
    if df_indicator.empty:
        logger.warning(f"  {id_string}: empty DataFrame — skipping Parquet write")
        return 0

    # Assemble the WB-compatible schema + FAOSTAT ``source_type``.
    # ``is_predicted`` is a semantic distinction from the WB completer
    # Lambda (#148): any indicator value carried forward or forecast
    # forward has ``is_predicted=True``; raw source data has ``False``.
    # FAOSTAT bulk downloads are always raw observations, never
    # projections.
    #
    # ``source_type`` (annual / fao_estimate / 3yr_avg [+diffed]) is
    # FAOSTAT-specific provenance — Phase 2 SCDI ignores this column
    # silently, but it's part of the Parquet for audit + future
    # downstream consumers (ops report, ML backtest gates).
    out = df_indicator.copy()
    out["year"] = out["year"].astype("int64")
    out["value"] = out["value"].astype("float64")
    out["is_predicted"] = False
    # source_type may be Categorical post-dedup — cast to str for Parquet.
    if "source_type" in out.columns:
        out["source_type"] = out["source_type"].astype(str)
    else:
        out["source_type"] = "unknown"
    if "is_estimate" not in out.columns:
        out["is_estimate"] = False
    out["is_estimate"] = out["is_estimate"].astype(bool)
    out = out.sort_values(["country", "year"])[
        ["country", "year", "value", "is_predicted", "source_type", "is_estimate"]
    ]

    key = f"{S3_OUTPUT_PREFIX}/parquet-completed/{id_string}/{id_string}.parquet"
    buf = BytesIO()
    out.to_parquet(buf, index=False)
    buf.seek(0)
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=buf.read(),
        ContentType="application/octet-stream",
    )
    logger.info(
        f"  {id_string}: wrote {len(out):,} rows ({out['country'].nunique()} "
        f"countries × {out['year'].nunique()} years) to s3://{BUCKET}/{key}"
    )
    return 1


# ---------------------------------------------------------------------------
# DynamoDB status writes
# ---------------------------------------------------------------------------


def write_tracker_row(indicator_id: str, status: str, **kwargs) -> None:
    """One row per (run_id, indicator_id) — same shape as WB side so the
    Phase 6 reporter can uniformly enumerate Phase 1 results."""
    item = {
        "run_id": RUN_ID,
        "indicator_id": indicator_id,
        "status": status,
        "provider": "FAOSTAT",
        "updated_at": Decimal(str(time.time())),
    }
    item.update(kwargs)
    tracker_table.put_item(Item=item)


def decrement_counter(by: int = 1) -> None:
    """Decrement ``qgi-pipeline-a-counter[run_id].pending`` by N.

    The dispatcher seeded ``pending=N`` where N is the total number of
    INDICATORS across ALL providers (not domains). So for FAOSTAT, a
    domain task that successfully emits 6 indicators decrements by 6.
    """
    counter_table.update_item(
        Key={"run_id": RUN_ID},
        UpdateExpression="ADD pending :neg",
        ExpressionAttributeValues={":neg": Decimal(-by)},
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    indicators = json.loads(INDICATORS_JSON_RAW)
    logger.info(f"FAOSTAT fetcher: domain={DOMAIN_CODE}, indicators={[i['id_string'] for i in indicators]}")

    _jitter_sleep()

    try:
        csv_bytes = fetch_domain_csv(DOMAIN_CODE)
    except Exception as exc:  # noqa: BLE001
        # Download failed after all retries. Write FAILED rows for every
        # indicator in this batch + decrement counter by their count so
        # the Phase 1 checker advances.
        logger.error(f"Domain fetch failed: {exc}\n{traceback.format_exc()}")
        for ind in indicators:
            write_tracker_row(ind["id_string"], "FAILED", error=str(exc)[:500])
        decrement_counter(by=len(indicators))
        return 1

    # Parse the CSV once and reuse across indicators in this domain.
    # FAOSTAT files use latin-1 encoding for some historical entries
    # (e.g., São Tomé e Príncipe).
    try:
        df_domain = pd.read_csv(StringIO(csv_bytes.decode("latin-1")))
    except Exception as exc:  # noqa: BLE001
        logger.error(f"CSV parse failed: {exc}")
        for ind in indicators:
            write_tracker_row(ind["id_string"], "FAILED", error=str(exc)[:500])
        decrement_counter(by=len(indicators))
        return 1

    country_map = load_country_map()
    canonical_names = load_canonical_country_names()

    for ind in indicators:
        try:
            df_ind = extract_indicator(df_domain, ind, country_map, canonical_names)
            written = write_parquet(df_ind, ind)
            write_tracker_row(
                ind["id_string"],
                "SUCCESS" if written > 0 else "EMPTY",
                rows=Decimal(len(df_ind)),
                parquet_files=Decimal(written),
            )
            logger.info(f"  {ind['id_string']}: {len(df_ind)} rows, {written} Parquet file(s) written")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Indicator {ind['id_string']} failed: {exc}\n{traceback.format_exc()}")
            write_tracker_row(ind["id_string"], "FAILED", error=str(exc)[:500])

    # Decrement counter by the full batch size at the end (one atomic op).
    decrement_counter(by=len(indicators))

    return 0


if __name__ == "__main__":
    sys.exit(main())
