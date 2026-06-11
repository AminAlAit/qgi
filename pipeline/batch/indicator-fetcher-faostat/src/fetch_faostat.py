"""FAOSTAT bulk-download fetcher — spec-driven, enrichment stage 2.

Replaces the old per-domain ``fetch_domain.py`` seed approach with a
spec-driven model where every indicator lives in ``src/specs.json``.
The fetcher is invoked per-indicator by the dispatcher (INDICATOR_ID env)
or per-batch (INDICATORS_JSON env) and uses the base harness for all
AWS I/O.

Architecture
------------
* **specs.json** (baked in the image) contains every FAOSTAT indicator
  the panel selected.  Each entry carries the bulk-download URL, the
  column used as the item filter (``item_column`` — normally "Item Code"
  but "Months Code" for the ET/temperature domain), the element code,
  transform hint, and derivation instructions.
* The fetcher downloads the domain ZIP once per run (cached in-process
  when multiple indicators share a domain, e.g. FS-001/FS-003/FS-004
  all come from the FS bulk file).
* **Derived indicators** (``is_derived=true``) are computed from base
  series fetched during the same run.  Currently supported derivation
  forms: ``ratio``, ``rate``, ``per_1000_pop``, ``annual_change``,
  ``binary``.  Cross-source ratios that need population use the World
  Bank SP.POP.TOTL series via the base's WB helper.
* **First-differencing** for 3-year-rolling-average series
  (``transform="first-difference"``): applied per-country to break the
  mechanical autocorrelation of overlapping windows.
* **Value coercion**: ``<X`` sentinel -> X/2; ``...`` suppression ->
  drop; everything else non-numeric -> drop.
* **Variance floor**: std < 1e-6 per country-series -> drop (prevents
  flat imputed series from polluting SCDI with undefined Pearson).

Country mapping
---------------
FAOSTAT "Area Code" (FAO M49-adjacent numbering) is resolved to QGI
canonical country names via ``country-m49-map.csv`` loaded from S3
(``fao_area_code`` column -> ``qgi_name``).

Output contract
---------------
Hands a ``DataFrame[country, year, value]`` to
``base.to_canonical_frame`` which enforces the 4-column schema
(country:str, year:int64, value:float64, is_predicted:bool=False) and
writes to ``parquet-completed/{id}/{id}.parquet``.

Dispatcher contract
-------------------
INDICATOR_ID  — single indicator code matching a key in SPECS (from specs.json)
INDICATORS_JSON — JSON array of ``{"id_string": "FS-001", ...}`` dicts (bulk)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import zipfile
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Import shared base (COPY'd to /app/qgi_fetcher_base.py in the image;
# for local tests the _fetcher_base/ dir is on sys.path via conftest).
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")
import qgi_fetcher_base as base  # noqa: E402

logger = base.logger

# ---------------------------------------------------------------------------
# Load specs.json (baked into the image at build time)
# ---------------------------------------------------------------------------
_SPECS_PATH = Path(__file__).resolve().parent / "specs.json"

with open(_SPECS_PATH) as _fh:
    _RAW_SPECS: list[dict[str, Any]] = json.load(_fh)

# Keyed by indicator code for O(1) lookup
SPECS: dict[str, dict[str, Any]] = {s["code"]: s for s in _RAW_SPECS}

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QGI-pipeline/2.0; +https://qgintelligence.com)",
}
MAX_FETCH_ATTEMPTS = int(os.environ.get("MAX_FETCH_ATTEMPTS", "5"))

# In-process ZIP cache: {bulk_url: bytes-of-csv} to avoid re-downloading the
# same domain ZIP when multiple indicators share one bulk file (e.g. FS domain).
_ZIP_CSV_CACHE: dict[str, bytes] = {}


def fetch_domain_csv(bulk_url: str) -> bytes:
    """Download a FAOSTAT bulk ZIP and return the main CSV bytes.

    Skips files with ``_flag`` in the filename (FAOSTAT ships a separate
    flags CSV alongside the data CSV in some ZIPs).  Caches in-process.
    """
    if bulk_url in _ZIP_CSV_CACHE:
        logger.info(f"ZIP cache hit for {bulk_url}")
        return _ZIP_CSV_CACHE[bulk_url]

    last_exc: Exception | None = None
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            resp = requests.get(bulk_url, timeout=300, headers=_HTTP_HEADERS)
            resp.raise_for_status()
            logger.info(f"Downloaded {len(resp.content):,} bytes (attempt {attempt}) from {bulk_url}")
            with zipfile.ZipFile(BytesIO(resp.content)) as zf:
                csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv") and "_flag" not in n.lower()]
                if not csv_names:
                    raise RuntimeError(f"No main CSV in ZIP {bulk_url}. Contents: {zf.namelist()}")
                csv_name = csv_names[0]
                logger.info(f"Extracting {csv_name}")
                csv_bytes = zf.read(csv_name)
            _ZIP_CSV_CACHE[bulk_url] = csv_bytes
            return csv_bytes
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            backoff = min(60, 2**attempt)
            logger.warning(f"Attempt {attempt}/{MAX_FETCH_ATTEMPTS} failed: {exc}. Backoff {backoff}s")
            time.sleep(backoff)
    raise RuntimeError(f"FAOSTAT download from {bulk_url} failed after {MAX_FETCH_ATTEMPTS} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Country mapping
# ---------------------------------------------------------------------------


def _build_fao_area_map() -> dict[int, str]:
    """Return {fao_area_code(int): qgi_canonical_name} from country-m49-map.csv."""
    obj = base._s3().get_object(Bucket=base.bucket(), Key=base.COUNTRY_M49_MAP_KEY)
    df = pd.read_csv(obj["Body"])
    out: dict[int, str] = {}
    for _, row in df.iterrows():
        fao = row.get("fao_area_code")
        name = str(row.get("qgi_name") or "").strip()
        if pd.isna(fao) or not name:
            continue
        try:
            out[int(fao)] = name
        except (ValueError, TypeError):
            pass
    logger.info(f"Loaded {len(out)} FAO area code -> QGI name mappings")
    return out


# ---------------------------------------------------------------------------
# Value coercion (shared with old fetch_domain.py logic)
# ---------------------------------------------------------------------------


def _coerce_values(series: pd.Series) -> pd.Series:
    """Coerce FAOSTAT Value column to float64.

    * ``<X``  -> X/2 (half-limit imputation for left-censored food-security data)
    * ``...`` / ``..`` -> NaN (suppressed, will be dropped)
    * Non-numeric -> NaN (will be dropped)
    """
    raw = series.astype(str)

    # Pass 1: below-detection sentinel  "<0.1" -> "0.05"
    below_detect = raw.str.match(r"^\s*<\s*\d+\.?\d*\s*$", na=False)
    if below_detect.any():

        def _half(s: str) -> str:
            m = re.match(r"^\s*<\s*(\d+\.?\d*)\s*$", s)
            return str(float(m.group(1)) / 2.0) if m else s

        series = series.copy().astype(str)
        series.loc[below_detect] = raw[below_detect].apply(_half)

    numeric = pd.to_numeric(series, errors="coerce")
    suppressed = (~numeric.notna()) & raw.str.match(r"^\s*\.{2,3}\s*$", na=False)
    unknown = (~numeric.notna()) & (~suppressed)

    n_bd = int(below_detect.sum())
    n_sup = int(suppressed.sum())
    n_unk = int(unknown.sum())
    logger.info(
        f"  Value coercion: {n_bd} '<X'->X/2; {n_sup} suppressed dropped; "
        f"{n_unk} unknown dropped; {int(numeric.notna().sum())} retained"
    )
    return numeric.astype("float64")


# ---------------------------------------------------------------------------
# Year code -> end year
# ---------------------------------------------------------------------------


def _end_year(year_code) -> int:
    """Extract end-year from FAOSTAT Year Code.

    Annual: 4-digit int -> year as-is.
    3yr_avg: 8-digit int (e.g. 20002002) -> last 4 digits (end year).
    """
    s = str(int(year_code))
    return int(s[-4:])


def _is_3yr_avg(year_code) -> bool:
    return len(str(int(year_code))) == 8


# ---------------------------------------------------------------------------
# Core extraction from a parsed domain DataFrame
# ---------------------------------------------------------------------------


def extract_from_domain(
    df_domain: pd.DataFrame,
    spec: dict[str, Any],
    fao_area_map: dict[int, str],
) -> pd.DataFrame:
    """Filter a parsed domain CSV to one indicator and return (country, year, value).

    Handles:
    - Generic item_column (``Item Code`` or ``Months Code`` for ET domain)
    - String comparison for mixed int/string item codes (e.g. ``24027-_T``)
    - First-differencing for 3yr_avg frequency
    - Variance floor filter
    - Below-detect imputation + suppression drop
    """
    item_col = spec.get("item_column", "Item Code")
    elem_col = spec.get("element_column", "Element Code")
    item_val = str(spec["fao_item_code"])
    elem_val = str(spec["fao_element_code"])

    if item_col not in df_domain.columns:
        raise ValueError(f"Column {item_col!r} not in domain CSV. Available: {list(df_domain.columns)[:20]}")

    subset = df_domain[
        (df_domain[item_col].astype(str) == item_val) & (df_domain[elem_col].astype(str) == elem_val)
    ].copy()

    if subset.empty:
        logger.warning(f"  {spec['code']}: 0 rows for {item_col}={item_val}, {elem_col}={elem_val}")
        return pd.DataFrame(columns=["country", "year", "value"])

    # Map FAO area codes to canonical names
    def _map_area(code):
        try:
            return fao_area_map.get(int(code))
        except (TypeError, ValueError):
            return None

    subset["country"] = subset["Area Code"].apply(_map_area)
    before = len(subset)
    subset = subset[subset["country"].notna()].copy()
    dropped = before - len(subset)
    if dropped:
        logger.info(f"  Dropped {dropped} rows with unmapped FAO area codes")

    # Year extraction
    subset["year"] = subset["Year Code"].apply(_end_year)

    # Value coercion
    subset["value"] = _coerce_values(subset["Value"])
    subset = subset.dropna(subset=["value"]).reset_index(drop=True)

    if subset.empty:
        return pd.DataFrame(columns=["country", "year", "value"])

    # Source type classification (annual vs 3yr_avg)
    subset["_is_3ya"] = subset["Year Code"].apply(_is_3yr_avg)

    # Dedup (country, year): prefer annual over 3yr_avg, reported over estimate
    is_estimate = subset.get("Flag", pd.Series(dtype=str)).astype(str).str.upper() == "E"
    subset["_est"] = is_estimate.astype(int)
    subset["_shape_rank"] = subset["_is_3ya"].astype(int)  # 0=annual wins, 1=3yr_avg loses
    subset = subset.sort_values(["country", "year", "_shape_rank", "_est"]).drop_duplicates(
        subset=["country", "year"], keep="first"
    )

    # First-difference for 3yr_avg series
    transform = spec.get("transform", "none")
    if transform == "first-difference":
        _ya_mask = subset["_is_3ya"]
        if _ya_mask.any():
            subset = subset.sort_values(["country", "year"]).reset_index(drop=True)
            diff_mask = subset["_is_3ya"]
            subset.loc[diff_mask, "value"] = subset.loc[diff_mask].groupby("country")["value"].diff()
            before_len = len(subset)
            subset = subset.dropna(subset=["value"]).reset_index(drop=True)
            logger.info(
                f"  First-diff: {diff_mask.sum()} 3yr_avg rows -> {before_len - len(subset)} leading NaNs dropped"
            )

    # Variance floor
    _VARIANCE_FLOOR = 1e-6
    stds = subset.groupby("country")["value"].transform("std")
    flat_mask = stds.fillna(0) < _VARIANCE_FLOOR
    n_flat = int(flat_mask.sum())
    if n_flat:
        flat_countries = subset.loc[flat_mask, "country"].drop_duplicates().head(10).tolist()
        logger.info(
            f"  Variance floor: dropped {n_flat} rows from {len(flat_countries)}+ "
            f"flat-series countries: {flat_countries}"
        )
        subset = subset[~flat_mask].reset_index(drop=True)

    return subset[["country", "year", "value"]].copy()


# ---------------------------------------------------------------------------
# Derived indicator computation
# ---------------------------------------------------------------------------


def compute_derived(
    spec: dict[str, Any],
    fao_area_map: dict[int, str],
) -> pd.DataFrame:
    """Compute a derived indicator per its derivation instructions.

    Supported derivation forms (``derivation`` field in spec):
    - ``annual_change:<base_code>``      — year-over-year diff of base series
    - ``ratio:<num_code>/<den_code>``    — ratio of two FAOSTAT series (both fetched)
    - ``per_1000_pop:<base_code>``       — base / (WB population / 1000)
    - ``binary:<base_code>:<threshold>`` — 1 if base > threshold else 0
    - ``rate:<num_code>/<den_code>``     — synonym for ratio (expresses as %)

    The base series for the derivation are fetched from the specs in SPECS dict
    (recursively, non-derived only).  If a code is not in SPECS, raises ValueError.
    """
    derivation = spec.get("derivation") or ""
    code = spec["code"]
    logger.info(f"  {code}: computing derived indicator (derivation={derivation!r})")

    # Parse derivation string
    if derivation.startswith("annual_change:"):
        base_code = derivation.split(":", 1)[1].strip()
        base_df = _fetch_base_series(base_code, fao_area_map)
        if base_df.empty:
            return pd.DataFrame(columns=["country", "year", "value"])
        base_df = base_df.sort_values(["country", "year"])
        base_df["value"] = base_df.groupby("country")["value"].diff()
        return base_df.dropna(subset=["value"])[["country", "year", "value"]]

    elif derivation.startswith("ratio:") or derivation.startswith("rate:"):
        rest = derivation.split(":", 1)[1]
        num_code, den_code = rest.split("/", 1)
        num_df = _fetch_base_series(num_code.strip(), fao_area_map)
        den_df = _fetch_base_series(den_code.strip(), fao_area_map)
        if num_df.empty or den_df.empty:
            return pd.DataFrame(columns=["country", "year", "value"])
        merged = num_df.merge(den_df, on=["country", "year"], suffixes=("_num", "_den"))
        merged = merged[merged["value_den"] != 0]
        merged["value"] = merged["value_num"] / merged["value_den"]
        return merged[["country", "year", "value"]]

    elif derivation.startswith("per_1000_pop:"):
        base_code = derivation.split(":", 1)[1].strip()
        base_df = _fetch_base_series(base_code, fao_area_map)
        pop_df = _fetch_wb_population()
        if base_df.empty or pop_df.empty:
            return pd.DataFrame(columns=["country", "year", "value"])
        merged = base_df.merge(pop_df, on=["country", "year"], suffixes=("", "_pop"))
        merged = merged[merged["value_pop"] > 0]
        merged["value"] = merged["value"] / (merged["value_pop"] / 1000.0)
        return merged[["country", "year", "value"]]

    elif derivation.startswith("binary:"):
        rest = derivation.split(":", 1)[1]
        parts = rest.split(":")
        base_code = parts[0].strip()
        threshold = float(parts[1]) if len(parts) > 1 else 0.0
        base_df = _fetch_base_series(base_code, fao_area_map)
        if base_df.empty:
            return pd.DataFrame(columns=["country", "year", "value"])
        base_df["value"] = (base_df["value"] > threshold).astype(float)
        return base_df[["country", "year", "value"]]

    else:
        raise ValueError(
            f"{code}: unrecognised derivation format {derivation!r}. "
            "Supported: annual_change:<code>, ratio:<n>/<d>, rate:<n>/<d>, "
            "per_1000_pop:<code>, binary:<code>:<threshold>"
        )


def _fetch_base_series(code: str, fao_area_map: dict[int, str]) -> pd.DataFrame:
    """Fetch a non-derived FAOSTAT series for use in derivation."""
    if code not in SPECS:
        raise ValueError(f"Base series {code!r} not found in SPECS (needed for derivation)")
    base_spec = SPECS[code]
    if base_spec.get("is_derived"):
        raise ValueError(f"Base series {code!r} is itself derived — chained derivations not supported")
    csv_bytes = fetch_domain_csv(base_spec["bulk_url"])
    df_domain = pd.read_csv(StringIO(csv_bytes.decode("latin-1")))
    return extract_from_domain(df_domain, base_spec, fao_area_map)


def _fetch_wb_population() -> pd.DataFrame:
    """Fetch World Bank SP.POP.TOTL via the base's WB helper mechanism.

    The base does not expose a dedicated WB fetch helper, so we hit the
    WB REST API directly.  This is intentionally simple: annual, all countries,
    SP.POP.TOTL.  Cached in-process.
    """
    if "_WB_POP" in _ZIP_CSV_CACHE:  # abuse the cache dict for non-ZIP bytes too
        return json.loads(_ZIP_CSV_CACHE["_WB_POP"].decode())

    url = "https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000&mrv=60"
    try:
        resp = requests.get(url, timeout=60, headers=_HTTP_HEADERS)
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 2 or not data[1]:
            return pd.DataFrame(columns=["country", "year", "value"])
        rows = []
        # We need the QGI canonical name, but the WB endpoint only gives us country ISO2/name.
        # Load the ISO3 map from the base to resolve.
        iso3_map = base.load_iso3_country_map()
        for item in data[1]:
            if not item.get("value"):
                continue
            iso3 = (item.get("countryiso3code") or "").strip().upper()
            name = iso3_map.get(iso3)
            if not name:
                continue
            try:
                year = int(item["date"])
                val = float(item["value"])
            except (TypeError, ValueError):
                continue
            rows.append({"country": name, "year": year, "value": val})
        df = pd.DataFrame(rows)
        # Cache as JSON bytes
        _ZIP_CSV_CACHE["_WB_POP"] = json.dumps(df.to_dict("records")).encode()
        return df
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"WB population fetch failed: {exc}")
        return pd.DataFrame(columns=["country", "year", "value"])


# ---------------------------------------------------------------------------
# Main fetch_one — entry point for the base harness
# ---------------------------------------------------------------------------


def fetch_one(spec: dict[str, Any]) -> pd.DataFrame | None:
    """Fetch or compute one FAOSTAT indicator.

    ``spec`` must contain ``id_string`` matching a key in SPECS.  The base
    harness calls this and routes the result through ``to_canonical_frame``
    and ``write_indicator_parquet``.
    """
    iid = spec["id_string"]
    if iid not in SPECS:
        raise ValueError(f"Unknown FAOSTAT indicator {iid!r}. Available codes: {sorted(SPECS)}")
    ind_spec = SPECS[iid]
    logger.info(f"{iid}: {ind_spec['name']}")

    # Country map (FAO area code -> canonical name)
    fao_area_map = _build_fao_area_map()

    if ind_spec.get("is_derived"):
        df = compute_derived(ind_spec, fao_area_map)
    else:
        csv_bytes = fetch_domain_csv(ind_spec["bulk_url"])
        # FAOSTAT CSVs use latin-1 encoding (accented country names)
        df_domain = pd.read_csv(StringIO(csv_bytes.decode("latin-1")))
        df = extract_from_domain(df_domain, ind_spec, fao_area_map)

    if df is None or df.empty:
        logger.warning(f"{iid}: no data — skipping")
        return None

    logger.info(f"{iid}: {len(df):,} rows ({df['country'].nunique()} countries x {df['year'].nunique()} years)")
    return df


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    base.run_fetcher("FAOSTAT", fetch_one)
