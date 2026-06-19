"""ILOSTAT SDMX fetcher (enrichment stage 2) — spec-driven.

One Fargate task per IL-xx indicator (dispatcher sends INDICATOR_ID or
INDICATORS_JSON).  Pulls the ILOSTAT SDMX REST API (sdmx.ilo.org/rest/,
no auth, CC BY 4.0), aggregates to (canonical country, year, value), and
hands the frame to the shared base which writes parquet-completed + DDB +
tracker + counter.

SPEC-DRIVEN DESIGN
------------------
All indicator definitions live in src/specs.json (baked into the image).
Each entry has:
  code            : canonical indicator id (IL-01 … IL-22+)
  dataflow        : ILOSTAT dataset ID  (without the "ILO,DF_" prefix)
  key             : dot-separated SDMX key; empty segment = wildcard
  is_derived      : bool — if true the indicator is computed from 1-2 base series
  derivation      : (derived only) dict describing the computation:
                    type = "ratio" | "annual_change" | "per1000" | "binary"
  dataflow_numerator / key_numerator  : (ratio) numerator fetch
  dataflow_denominator / key_denominator : (ratio) denominator fetch
  dataflow_base / key_base            : (annual_change / per1000 / binary) base fetch

Adding a new indicator = edit specs.json + rebuild the image.  No Python changes
needed for standard non-derived indicators.

COUNTRY CODES
-------------
ILOSTAT SDMX uses ISO alpha-3 in the REF_AREA dimension → mapped to canonical
name_1 via the shared country-m49-map (iso_alpha3 column).

SDMX URL PATTERN
----------------
  https://sdmx.ilo.org/rest/data/ILO,DF_<DATAFLOW>,1.0/<KEY>
  (pandasdmx constructs this automatically from dataflow + key)

DIMENSION-KEY CONVENTIONS (ILOSTAT)
------------------------------------
  _T / SEX_T              = total (both sexes)
  AGE_AGGREGATE_TOTAL     = all ages
  ECO_AGGREGATE_TOTAL     = all industries
  NOC                     = no classification (single-dim datasets)
  DUR_GE12M               = duration >=12 months

NOTE: dataflow IDs and dimension keys were confirmed via DBnomics ILO catalogue
and SDMX REST endpoint listing 2026-06-26.  Run ONE live smoke per indicator on
AWS before production to confirm field names (the parse logic is unit-tested
against a representative synthetic payload matching the pandasdmx Series index).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Shared base is COPYed next to this script in the image (see Dockerfile).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")
import qgi_fetcher_base as base  # noqa: E402

ILO_BASE = "https://sdmx.ilo.org/rest"
YEAR_FROM = 1990

# ---------------------------------------------------------------------------
# Load specs.json — baked alongside this script in the image.
# The dict is keyed by 'code' for O(1) lookup at task runtime.
# ---------------------------------------------------------------------------
_SPECS_PATH = Path(__file__).resolve().parent / "specs.json"


def _load_specs() -> dict[str, dict[str, Any]]:
    with open(_SPECS_PATH, encoding="utf-8") as fh:
        entries = json.load(fh)
    return {e["code"]: e for e in entries}


# SPECS is module-level so tests can inspect it without re-parsing each time.
SPECS: dict[str, dict[str, Any]] = _load_specs()


# ---------------------------------------------------------------------------
# Raw SDMX fetch (pandasdmx / sdmx1, lazy import)
# ---------------------------------------------------------------------------


def fetch_ilostat_raw(dataflow: str, key: str) -> "pd.Series":
    """Fetch one ILOSTAT SDMX dataflow slice via pandasdmx.

    Returns the raw pandasdmx observation Series (multi-indexed by dimensions).
    Raises on HTTP errors so the base harness can catch and log them.
    """
    import sdmx  # sdmx1 on PyPI — lazy import so module loads clean under test

    client = sdmx.Client("ILO")
    resp = client.data(
        dataflow,
        key=key,
        params={"startPeriod": str(YEAR_FROM)},
    )
    ds = sdmx.to_pandas(resp)
    # to_pandas returns a Series or a dict of Series; flatten either case.
    if isinstance(ds, dict):
        if not ds:
            return pd.Series(dtype=float)
        ds = pd.concat(list(ds.values()))
    return ds


# ---------------------------------------------------------------------------
# Parse pandasdmx observation Series → DataFrame[country, year, value]
# ---------------------------------------------------------------------------


def parse_ilostat_records(
    obs_series: "pd.Series | None",
    iso3_map: dict[str, str],
) -> pd.DataFrame:
    """PURE: pandasdmx observation Series -> DataFrame[country, year, value].

    The pandasdmx 1.x client returns a pandas Series whose index is a
    MultiIndex containing (at minimum) a REF_AREA level with ISO alpha-3 codes
    and a TIME_PERIOD level with period strings like '2015' or '2015-Q1'.

    Aggregation to annual: for quarterly/monthly sources we take the mean
    per (country, year).  Annual sources pass through unchanged.

    Rows whose REF_AREA ISO3 doesn't resolve to a canonical name are dropped
    (regional aggregates, unknown codes, territories not in the QGI map).
    """
    if obs_series is None or obs_series.empty:
        return pd.DataFrame(columns=["country", "year", "value"])

    frame = obs_series.reset_index()

    # Identify columns regardless of position — pandasdmx names them by the
    # dimension ID from the DSD.
    ref_col = next(
        (c for c in frame.columns if str(c).upper() in ("REF_AREA", "AREA", "COUNTRY")),
        None,
    )
    time_col = next(
        (c for c in frame.columns if str(c).upper() in ("TIME_PERIOD", "TIME", "PERIOD", "YEAR")),
        None,
    )
    # OBS_VALUE by name; fall back to last column.
    val_col = next(
        (c for c in frame.columns if str(c).upper() == "OBS_VALUE"),
        frame.columns[-1],
    )

    if ref_col is None or time_col is None:
        base.logger.warning(
            f"parse_ilostat_records: could not detect REF_AREA/TIME_PERIOD columns in {list(frame.columns)}"
        )
        return pd.DataFrame(columns=["country", "year", "value"])

    rows = []
    for _, row in frame.iterrows():
        iso = str(row[ref_col]).strip().upper()
        name = iso3_map.get(iso)
        if not name:
            continue
        raw_time = str(row[time_col]).strip()
        year_str = raw_time[:4]  # works for 'YYYY', 'YYYY-Qn', 'YYYY-Mn', 'YYYY-Sn'
        try:
            year = int(year_str)
        except ValueError:
            continue
        if year < YEAR_FROM:
            continue
        try:
            val = float(row[val_col])
        except (TypeError, ValueError):
            continue
        if val != val:  # NaN guard
            continue
        rows.append({"country": name, "year": year, "value": val})

    if not rows:
        return pd.DataFrame(columns=["country", "year", "value"])

    df = pd.DataFrame(rows)
    # Aggregate sub-annual observations to annual mean (no-op for annual data).
    return df.groupby(["country", "year"], as_index=False)["value"].mean().reset_index(drop=True)


# ---------------------------------------------------------------------------
# Derived-indicator computation
# ---------------------------------------------------------------------------


def _fetch_and_parse(dataflow: str, key: str, iso3_map: dict[str, str]) -> pd.DataFrame:
    """Fetch one SDMX slice and parse to [country, year, value]."""
    raw = fetch_ilostat_raw(dataflow, key)
    return parse_ilostat_records(raw, iso3_map)


def compute_derived(spec: dict[str, Any], iso3_map: dict[str, str]) -> pd.DataFrame:
    """Compute a derived indicator per the derivation spec.

    Supported types:
      ratio         : numerator / denominator * 100  (percentage ratio)
      annual_change : year-on-year diff of the base series
      binary        : 1 if base > 0 else 0
    """
    derivation = spec.get("derivation") or {}
    deriv_type = derivation.get("type", "")
    code = spec["code"]

    if deriv_type == "ratio":
        num_df = _fetch_and_parse(spec["dataflow_numerator"], spec["key_numerator"], iso3_map)
        den_df = _fetch_and_parse(spec["dataflow_denominator"], spec["key_denominator"], iso3_map)
        if num_df.empty or den_df.empty:
            base.logger.warning(f"{code}: ratio derivation returned empty component frame")
            return pd.DataFrame(columns=["country", "year", "value"])
        merged = num_df.merge(den_df, on=["country", "year"], suffixes=("_num", "_den"))
        merged = merged[merged["value_den"] != 0].copy()
        merged["value"] = merged["value_num"] / merged["value_den"] * 100.0
        return merged[["country", "year", "value"]].reset_index(drop=True)

    elif deriv_type == "annual_change":
        base_df = _fetch_and_parse(spec["dataflow_base"], spec["key_base"], iso3_map)
        if base_df.empty:
            return pd.DataFrame(columns=["country", "year", "value"])
        base_df = base_df.sort_values(["country", "year"])
        base_df["value"] = base_df.groupby("country")["value"].diff()
        # Drop rows where diff is NaN (first observation per country).
        base_df = base_df.dropna(subset=["value"])
        return base_df[["country", "year", "value"]].reset_index(drop=True)

    elif deriv_type == "binary":
        base_df = _fetch_and_parse(spec["dataflow_base"], spec["key_base"], iso3_map)
        if base_df.empty:
            return pd.DataFrame(columns=["country", "year", "value"])
        base_df = base_df.copy()
        base_df["value"] = (base_df["value"] > 0).astype(float)
        return base_df[["country", "year", "value"]].reset_index(drop=True)

    else:
        raise ValueError(f"{code}: unknown derivation type {deriv_type!r}. Supported: ratio, annual_change, binary")


# ---------------------------------------------------------------------------
# fetch_one — dispatcher entry point called by run_fetcher
# ---------------------------------------------------------------------------


def fetch_one(spec: dict[str, Any]) -> pd.DataFrame:
    """Fetch and parse one indicator.  spec must contain 'id_string'."""
    iid = spec["id_string"]
    cfg = SPECS.get(iid)
    if cfg is None:
        raise ValueError(f"unknown ILOSTAT indicator {iid!r}")

    iso3_map = base.load_iso3_country_map()

    if cfg.get("is_derived"):
        base.logger.info(f"{iid}: computing derived indicator (type={cfg.get('derivation', {}).get('type', '?')})")
        return compute_derived(cfg, iso3_map)

    # Standard (non-derived) fetch
    base.logger.info(f"{iid}: fetching dataflow={cfg['dataflow']!r} key={cfg['key']!r}")
    raw = fetch_ilostat_raw(cfg["dataflow"], cfg["key"])
    return parse_ilostat_records(raw, iso3_map)


if __name__ == "__main__":
    base.run_fetcher("ILOSTAT", fetch_one)
