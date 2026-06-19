"""UNDP HDR spec-driven Fargate fetcher (enrichment stage 2).

Supports two namespaces of indicator codes:

SEED codes (UD-01 … UD-07) — original hardcoded set, still dispatched by
the older pipeline dispatcher.  They are resolved via INDICATOR_PREFIX and
routed through the same parse_undp_wide() path.

ENRICHMENT codes (IHDI, GII, INEQ_INC, MPI, …) — loaded at runtime from
src/specs.json (baked into the image).  Each spec entry declares:

  source: "hdr_composite_csv"  — melt from the HDR25 wide CSV using col_prefix
          "ophi_xlsx"          — download an XLSX and parse the MPI time-series
  is_derived: false/true       — if true, derivation string drives post-processing
  col_prefix                   — the column prefix for hdr_composite_csv sources
  endpoint_or_dataset          — URL of the data source
  derivation                   — formula string (annual_change / ratio / per_1000_pop
                                 / binary / none) for derived indicators

DERIVED INDICATOR MECHANICS
When is_derived=true the derivation field is a formula string.  Recognised
patterns:
  "annual_change"          — df.groupby(country).value.diff()  (row-to-row Δ)
  "ratio:<base>:<denom>"   — ratio of two already-fetched base codes
  "per_1000_pop"           — multiply value × 1000 / SP.POP.TOTL (via WB API)
  "binary:<threshold>"     — 1 if value >= threshold else 0
No current spec has is_derived=true; the mechanism is implemented so future
specs.json additions work without code changes.

CACHE
The HDR25 wide CSV is downloaded once per task invocation (module-level
_wide_df_cache keyed by URL).  XLSX downloads are also cached.

Source:  UNDP Human Development Reports Data Center
URL:     UNDP_CSV_URL env var (default = HDR25 composite time-series CSV)
License: CC BY 3.0 IGO  <https://hdr.undp.org/copyright-and-terms-use>

SEED INDICATORS (column prefix in the wide CSV):
    UD-01  hdi_   Human Development Index
    UD-02  ihdi_  Inequality-adjusted HDI
    UD-03  gii_   Gender Inequality Index
    UD-04  mpi_   Multidimensional Poverty Index (scaffolded — not in HDR25 CSV)
    UD-05  mys_   Mean Years of Schooling
    UD-06  eys_   Expected Years of Schooling
    UD-07  gdi_   Gender Development Index

ENRICHMENT INDICATORS (from specs.json):
    IHDI       ihdi_     (same series as UD-02, enrichment code alias)
    GII        gii_      (same series as UD-03, enrichment code alias)
    INEQ_INC   ineq_inc_ (Atkinson income inequality, HDR25 CSV)
    MPI        (OPHI Table 6 XLSX — sparse multi-year time series)
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Shared base is COPYed next to this script in the image (see Dockerfile).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")
import qgi_fetcher_base as base  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration — SEED codes (backward-compatible, never remove)
# ---------------------------------------------------------------------------

UNDP_CSV_URL_DEFAULT = (
    "https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Composite_indices_complete_time_series.csv"
)

# id_string -> column prefix in the wide CSV (original seed set)
INDICATOR_PREFIX: dict[str, str] = {
    "UD-01": "hdi_",
    "UD-02": "ihdi_",
    "UD-03": "gii_",
    "UD-04": "mpi_",  # scaffolded — not present in HDR25 CSV; yields SKIPPED
    "UD-05": "mys_",
    "UD-06": "eys_",
    "UD-07": "gdi_",
}

# ---------------------------------------------------------------------------
# Load enrichment specs from baked specs.json
# ---------------------------------------------------------------------------

_SPECS_PATH = Path(__file__).resolve().parent / "specs.json"


def _load_enrichment_specs() -> dict[str, dict[str, Any]]:
    """Load specs.json; return {code: spec} for fetchable entries only."""
    try:
        raw = json.loads(_SPECS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        base.logger.warning(f"specs.json not found at {_SPECS_PATH}; enrichment codes unavailable")
        return {}
    return {entry["code"]: entry for entry in raw if entry.get("fetchable", False)}


# Module-level registry: populated once on first use
_enrichment_specs: dict[str, dict[str, Any]] | None = None


def get_enrichment_specs() -> dict[str, dict[str, Any]]:
    global _enrichment_specs
    if _enrichment_specs is None:
        _enrichment_specs = _load_enrichment_specs()
    return _enrichment_specs


# ---------------------------------------------------------------------------
# Module-level download caches (one per URL)
# ---------------------------------------------------------------------------

_wide_df_cache: dict[str, pd.DataFrame] = {}
_xlsx_cache: dict[str, bytes] = {}


# ---------------------------------------------------------------------------
# Pure transform: HDR25 wide CSV -> long DataFrame (unit-tested, no I/O)
# ---------------------------------------------------------------------------


def parse_undp_wide(
    wide_df: pd.DataFrame,
    col_prefix: str,
    iso3_map: dict[str, str],
) -> pd.DataFrame:
    """PURE: melt one indicator prefix from the UNDP wide DataFrame.

    Parameters
    ----------
    wide_df:    the raw wide CSV as a DataFrame (contains iso3, country, and
                columns like hdi_1990, hdi_1991 … gdi_2023 …)
    col_prefix: e.g. "hdi_"  (the metric prefix including trailing underscore)
    iso3_map:   {ISO3_UPPER: canonical name_1}

    Returns
    -------
    DataFrame[country, year, value] — annual; rows without ISO3 resolution or
    with non-numeric values are dropped.  If the prefix is absent from the
    CSV the frame is empty (SKIPPED path in the harness).

    Notes
    -----
    Gender-disaggregated variants (e.g. hdi_f_1990, hdi_m_1990) are excluded
    because their year suffix is not purely numeric (len != 4 or !isdigit).
    Compound prefixes like ineq_inc_ work correctly since we use startswith +
    an exact 4-digit suffix check.
    """
    value_cols = [
        c
        for c in wide_df.columns
        if c.startswith(col_prefix) and c[len(col_prefix) :].isdigit() and len(c[len(col_prefix) :]) == 4
    ]
    if not value_cols:
        return pd.DataFrame(columns=["country", "year", "value"])

    iso3_col = "iso3" if "iso3" in wide_df.columns else wide_df.columns[0]
    id_cols = [iso3_col]
    subset = wide_df[id_cols + value_cols].copy()
    subset["_name"] = subset[iso3_col].astype(str).str.strip().str.upper().map(iso3_map)
    subset = subset.dropna(subset=["_name"])

    melted = subset.melt(
        id_vars=["_name"],
        value_vars=value_cols,
        var_name="_col",
        value_name="value",
    )
    melted["year"] = melted["_col"].str[len(col_prefix) :].astype(int)
    melted = melted.rename(columns={"_name": "country"})
    melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
    melted = melted.dropna(subset=["value"])

    result = melted.groupby(["country", "year"], as_index=False)["value"].mean()
    return result[["country", "year", "value"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Pure transform: OPHI XLSX Table 6 -> long DataFrame
# ---------------------------------------------------------------------------


def parse_ophi_mpi_xlsx(
    xlsx_bytes: bytes,
    iso3_map: dict[str, str],
) -> pd.DataFrame:
    """PURE: parse OPHI Table 6 (Trends Over Time MPI XLSX) to long format.

    The XLSX contains national-level MPI time-series for ~88 countries with
    2 time points per country (t0 / t1) stored in wide format.  Coverage is
    sparse by design (survey-year cadence, not annual).

    OPHI 2025 structure (Table_6_Trends_Over_Time_MPI_2025_30_Oct.xlsx):
    - Sheet 0 ("readme") contains only a license text block — no data.
    - Sheet "6.1 Harmonised MPI" holds the actual country-level data.
    - Header row is at Excel row 5 (0-indexed row 4 in openpyxl).
    - Rows 5-8 (header+4) are sub-header rows (t0/t1 labels, range notes, etc.)
      — the first real data row starts at position 4 within the loaded frame.
    - Columns (after header row 4):
        [0]  ISO\ncountry numeric code  (numeric M49, unused)
        [1]  ISO\ncountry code          (ISO-3 alpha, e.g. "AFG")
        [5]  Unnamed: 5               survey year for t0, e.g. "2015-2016"
        [7]  Unnamed: 7               survey year for t1, e.g. "2022-2023"
        [8]  Multidimensional Poverty Index (MPIT)   MPI value at t0
        [9]  Unnamed: 9               MPI value at t1
    We stack t0 and t1 into a long frame.  Survey years like "2015-2016" are
    resolved to their end year (2016).

    Falls back gracefully: if the sheet or expected columns are absent the
    function logs a warning and returns an empty frame (SKIPPED path in the
    harness).

    Returns DataFrame[country, year, value] with country = canonical name_1,
    year = integer survey end-year, value = float MPI (range 0..1).
    """
    # --- try the 2025 OPHI layout first (sheet "6.1 Harmonised MPI") --------
    DATA_SHEET = "6.1 Harmonised MPI"
    HEADER_ROW = 4  # 0-indexed row index in the Excel sheet
    DATA_START = 4  # rows to skip within the loaded frame (sub-headers)

    try:
        import openpyxl as _openpyxl  # available in requirements.txt

        wb = _openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        wb.close()

        if DATA_SHEET in sheet_names:
            df_raw = pd.read_excel(
                io.BytesIO(xlsx_bytes),
                sheet_name=DATA_SHEET,
                header=HEADER_ROW,
                engine="openpyxl",
            )
            df_raw.columns = [str(c).strip() for c in df_raw.columns]
            df = df_raw.iloc[DATA_START:].reset_index(drop=True)

            # ISO-3 column is always column index 1 in this layout
            iso3_col = df.columns[1]  # "ISO\ncountry code"
            mpi_t0_col = df.columns[8]  # "Multidimensional Poverty Index (MPIT)"
            mpi_t1_col = df.columns[9]  # "Unnamed: 9"
            yr_t0_col = df.columns[5]  # "Unnamed: 5"  e.g. "2015-2016"
            yr_t1_col = df.columns[7]  # "Unnamed: 7"  e.g. "2022-2023"

            def _survey_end_year(val) -> int | None:
                """'2015-2016' -> 2016; '2022' -> 2022; NaN -> None."""
                if val is None or (isinstance(val, float) and val != val):
                    return None
                s = str(val).strip()
                if not s or s.lower() in ("nan", "none", ""):
                    return None
                if "-" in s:
                    try:
                        return int(s.split("-")[-1])
                    except ValueError:
                        pass
                try:
                    return int(float(s))
                except (ValueError, TypeError):
                    return None

            rows = []
            for _, row in df.iterrows():
                iso = str(row.get(iso3_col) or "").strip().upper()
                name = iso3_map.get(iso)
                if not name:
                    continue
                # t0
                y0 = _survey_end_year(row.get(yr_t0_col))
                v0 = pd.to_numeric(row.get(mpi_t0_col), errors="coerce")
                if y0 is not None and pd.notna(v0):
                    rows.append({"country": name, "year": y0, "value": float(v0)})
                # t1 (may be absent for countries with only one survey)
                y1 = _survey_end_year(row.get(yr_t1_col))
                v1 = pd.to_numeric(row.get(mpi_t1_col), errors="coerce")
                if y1 is not None and pd.notna(v1):
                    rows.append({"country": name, "year": y1, "value": float(v1)})

            if rows:
                result = (
                    pd.DataFrame(rows)
                    .drop_duplicates(subset=["country", "year"])
                    .sort_values(["country", "year"])
                    .reset_index(drop=True)
                )
                base.logger.info(
                    f"MPI XLSX (2025 layout): {len(result)} rows ({result['country'].nunique()} countries)"
                )
                return result[["country", "year", "value"]]

    except Exception as exc:  # noqa: BLE001
        base.logger.warning(f"MPI XLSX (2025 layout) failed: {exc}; trying generic fallback")

    # --- generic fallback: search all sheets for a usable ISO3+year+MPI table -
    try:
        raw = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=0, header=None, engine="openpyxl")
    except Exception as exc:
        base.logger.warning(f"MPI XLSX parse error (sheet 0): {exc}")
        return pd.DataFrame(columns=["country", "year", "value"])

    # Find the header row: first row where >=3 cells are non-null strings
    header_row = None
    for idx, row in raw.iterrows():
        non_null = row.dropna()
        if len(non_null) >= 3:
            header_row = int(idx)
            break
    if header_row is None:
        base.logger.warning("MPI XLSX: could not locate header row")
        return pd.DataFrame(columns=["country", "year", "value"])

    df = pd.read_excel(
        io.BytesIO(xlsx_bytes),
        sheet_name=0,
        header=header_row,
        engine="openpyxl",
    )
    df.columns = [str(c).strip() for c in df.columns]

    # Probe for ISO3 column
    iso3_candidates = ["iso3", "ISO3", "ISO Country Code", "iso country code", "country code", "alpha3"]
    iso3_col = next((c for c in df.columns if c.lower() in [x.lower() for x in iso3_candidates]), None)
    if iso3_col is None:
        # Fallback: look for a column whose values look like ISO3
        for col in df.columns:
            sample = df[col].dropna().astype(str).str.strip()
            if sample.str.match(r"^[A-Z]{3}$").mean() > 0.5:
                iso3_col = col
                break
    if iso3_col is None:
        base.logger.warning("MPI XLSX: could not identify iso3 column; columns=" + str(list(df.columns[:10])))
        return pd.DataFrame(columns=["country", "year", "value"])

    # Probe for survey year column
    year_candidates = ["year", "survey year", "Year", "Survey Year", "reference year"]
    year_col = next((c for c in df.columns if c.lower() in [x.lower() for x in year_candidates]), None)

    # Probe for MPI value column
    mpi_candidates = [
        "mpi",
        "Multidimensional Poverty Index",
        "MPI Value",
        "mpi value",
        "MPI (Household)",
        "National MPI",
    ]
    mpi_col = next((c for c in df.columns if c.lower() in [x.lower() for x in mpi_candidates]), None)
    if mpi_col is None:
        # Fallback: first numeric column that isn't year or iso3
        skip = {iso3_col, year_col}
        for col in df.columns:
            if col in skip:
                continue
            if pd.to_numeric(df[col], errors="coerce").notna().mean() > 0.4:
                mpi_col = col
                break
    if mpi_col is None:
        base.logger.warning("MPI XLSX: could not identify MPI value column; columns=" + str(list(df.columns[:10])))
        return pd.DataFrame(columns=["country", "year", "value"])

    base.logger.info(f"MPI XLSX (fallback): iso3={iso3_col!r} year={year_col!r} mpi={mpi_col!r}")

    # Build long frame
    work = df[[iso3_col] + ([year_col] if year_col else []) + [mpi_col]].copy()
    work = work.rename(columns={mpi_col: "value"})
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    work = work.dropna(subset=["value"])

    # Resolve iso3 -> canonical name
    work["country"] = work[iso3_col].astype(str).str.strip().str.upper().map(iso3_map)
    work = work.dropna(subset=["country"])

    # Year handling: if no dedicated year column, we cannot build a time-series
    if year_col and year_col in work.columns:
        work["year"] = pd.to_numeric(work[year_col], errors="coerce").astype("Int64")
        work = work.dropna(subset=["year"])
        work["year"] = work["year"].astype(int)
    else:
        base.logger.warning("MPI XLSX: no year column found; rows will be dropped")
        return pd.DataFrame(columns=["country", "year", "value"])

    result = (
        work[["country", "year", "value"]]
        .groupby(["country", "year"], as_index=False)["value"]
        .mean()
        .reset_index(drop=True)
    )
    return result


# ---------------------------------------------------------------------------
# Pure transform: apply derivation to a long DataFrame
# ---------------------------------------------------------------------------


def apply_derivation(df: pd.DataFrame, derivation: str) -> pd.DataFrame:
    """PURE: apply a derivation formula to a country/year/value DataFrame.

    Supported derivation strings:
      "annual_change"          — year-over-year difference (diff within country)
      "binary:<threshold>"     — 1.0 if value >= threshold else 0.0
      "none" / None / ""       — return df unchanged

    Ratio and per-1000-pop derivations that require a second series are NOT
    supported inline here (they require a separate fetch and are documented
    as needing a multi-series combiner upstream).  If such a derivation string
    is encountered, a ValueError is raised so the harness marks the indicator
    FAILED rather than silently producing wrong data.
    """
    if not derivation or derivation.lower() in ("none", "null"):
        return df

    d = derivation.strip().lower()

    if d == "annual_change":
        out = df.sort_values(["country", "year"]).copy()
        out["value"] = out.groupby("country")["value"].diff()
        return out.dropna(subset=["value"]).reset_index(drop=True)

    if d.startswith("binary:"):
        try:
            threshold = float(d.split(":", 1)[1])
        except ValueError as exc:
            raise ValueError(f"invalid binary derivation threshold in {derivation!r}") from exc
        out = df.copy()
        out["value"] = (out["value"] >= threshold).astype(float)
        return out

    raise ValueError(
        f"unsupported derivation {derivation!r} — ratio/per_1000_pop require "
        "a multi-series combiner; implement upstream before dispatch"
    )


# ---------------------------------------------------------------------------
# Network I/O helpers
# ---------------------------------------------------------------------------


def _load_wide_df() -> pd.DataFrame:
    """Download (or return cached) the UNDP HDR25 composite CSV."""
    url = os.environ.get("UNDP_CSV_URL", UNDP_CSV_URL_DEFAULT)
    if url in _wide_df_cache:
        base.logger.info(f"UNDP CSV: using cached wide DataFrame ({url})")
        return _wide_df_cache[url]

    import requests  # lazy import — keeps module importable in tests

    base.logger.info(f"UNDP CSV: downloading {url}")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    base.logger.info(f"UNDP CSV: {len(df)} rows x {len(df.columns)} cols from {url}")
    _wide_df_cache[url] = df
    return df


def _load_xlsx_bytes(url: str) -> bytes:
    """Download (or return cached) raw XLSX bytes."""
    if url in _xlsx_cache:
        base.logger.info(f"XLSX: using cached bytes ({url})")
        return _xlsx_cache[url]

    import requests

    base.logger.info(f"XLSX: downloading {url}")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    _xlsx_cache[url] = resp.content
    base.logger.info(f"XLSX: {len(resp.content):,} bytes from {url}")
    return resp.content


# ---------------------------------------------------------------------------
# fetch_one — handles both seed codes and enrichment codes
# ---------------------------------------------------------------------------


def fetch_one(spec: dict) -> pd.DataFrame | None:
    """Fetch one indicator.

    Routing priority:
    1. If id_string is a seed code (UD-01..07) → use INDICATOR_PREFIX map +
       parse_undp_wide.
    2. If id_string is an enrichment code known in specs.json → use the spec's
       source/col_prefix/endpoint fields.
    3. Otherwise → ValueError (unknown code).

    After fetching, if the spec has is_derived=True, apply_derivation() is
    called on the raw series.

    The code lookup is validated BEFORE any network or AWS call so that an
    unknown id_string raises ValueError without touching AWS (important for
    tests that do not set S3_BUCKET).
    """
    iid = spec["id_string"]

    # Validate the code first (no AWS/network) — raises ValueError for unknowns
    enrichment = get_enrichment_specs()
    is_seed = iid in INDICATOR_PREFIX
    is_enrichment = iid in enrichment
    if not is_seed and not is_enrichment:
        raise ValueError(f"unknown UNDP indicator {iid!r} — not in INDICATOR_PREFIX or specs.json")

    iso3_map = base.load_iso3_country_map()

    # --- Path 1: seed codes ---
    if is_seed:
        col_prefix = INDICATOR_PREFIX[iid]
        wide_df = _load_wide_df()
        df = parse_undp_wide(wide_df, col_prefix, iso3_map)
        if df.empty:
            base.logger.warning(
                f"{iid}: no rows for prefix={col_prefix!r} (expected for UD-04/mpi_ — see module docstring)"
            )
            return None
        return df

    # --- Path 2: enrichment codes from specs.json ---
    if is_enrichment:
        espec = enrichment[iid]
        source = espec.get("source", "hdr_composite_csv")
        is_derived = espec.get("is_derived", False)
        derivation = espec.get("derivation") or "none"

        if source == "hdr_composite_csv":
            col_prefix = espec.get("col_prefix")
            if not col_prefix:
                raise ValueError(f"{iid}: enrichment spec has no col_prefix for hdr_composite_csv source")
            wide_df = _load_wide_df()
            df = parse_undp_wide(wide_df, col_prefix, iso3_map)
            if df.empty:
                base.logger.warning(f"{iid}: no rows for prefix={col_prefix!r}")
                return None

        elif source == "ophi_xlsx":
            url = espec["endpoint_or_dataset"]
            xlsx_bytes = _load_xlsx_bytes(url)
            df = parse_ophi_mpi_xlsx(xlsx_bytes, iso3_map)
            if df.empty:
                base.logger.warning(f"{iid}: OPHI XLSX parse returned empty frame — SKIPPED")
                return None

        else:
            raise ValueError(f"{iid}: unknown source type {source!r} in specs.json")

        # Apply derivation if declared
        if is_derived:
            df = apply_derivation(df, derivation)
            if df.empty:
                base.logger.warning(f"{iid}: derivation yielded empty frame — SKIPPED")
                return None

        return df

    # Should be unreachable (the guard at top of function covers all cases).
    raise AssertionError(f"fetch_one routing error for {iid!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    base.run_fetcher("UNDP", fetch_one)
