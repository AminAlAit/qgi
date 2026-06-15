"""OECD SDMX fetcher (enrichment stage 2 plugin).

One Fargate task per OE-xx indicator (dispatcher sends INDICATOR_ID). Pulls the
OECD SDMX REST API (sdmx.oecd.org/public/rest/, no auth, CC BY 4.0), maps ISO
alpha-3 country codes to canonical name_1, aggregates sub-annual frequencies to
annual mean per country-year, and hands the frame to the shared base which writes
parquet-completed + DDB + tracker + counter.

Country codes: ISO alpha-3 (REF_AREA dimension in all OECD SDMX datasets). The
API sometimes uses alpha-2 codes for older KEI/BTS dataflows — handle both
(alpha-2 via iso3166 lib or best-effort skip).

Dataflows (all accessed via sdmx.oecd.org/public/rest/):
  OE-01  CLI (Composite Leading Indicators)
           OECD.SDD.STES,DSD_STES@DF_CLI — monthly; amplitude-adjusted index (LI,AA,IX)
  OE-02  CCI (Consumer Confidence Index)
           OECD.SDD.STES,DSD_KEI@DF_KEI  — quarterly; CCSCONF measure
  OE-03  BCI (Business Confidence Index)
           OECD.SDD.STES,DSD_KEI@DF_KEI  — quarterly; BSCICP02 measure
  OE-04  Total social spending % GDP (SOCX)
           OECD.ELS.SPD,DSD_SOCX_AGG@DF_SOCX_AGG — annual; unit PT_B1GQ
  OE-05  Gini disposable income
           OECD.WISE.INE,DSD_WISE_IDD@DF_IDD — annual; measure INC_DISP_GINI
  OE-06  Tax revenue % GDP
           OECD.CTP.TPS,DSD_REV_COMP_GLOBAL@DF_RSGLOBAL — annual; _T + PT_B1GQ
  OE-07  Total Factor Productivity growth
           OECD.SDD.TPS,DSD_PDB@DF_PDB_GR — annual; MFP (multifactor productivity)

NOTE: verify exact dimension-key strings with a live smoke on AWS before the first
production fetch; the parse logic is unit-tested against synthetic payloads.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Shared base is COPYed next to this script in the image (see Dockerfile).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")
import qgi_fetcher_base as base  # noqa: E402

OECD_SDMX_REST = "https://sdmx.oecd.org/public/rest"

# ---- indicator spec catalogue -----------------------------------------------
# Each entry defines how to pull one indicator from the OECD SDMX REST API.
# Fields:
#   agency       — OECD agency identifier (before the comma in the flow ref)
#   dataflow     — dataflow id (DSD@DF notation)
#   dim_key      — positional dimension key (wildcards = empty string between +)
#                  passed to the /data endpoint as the key parameter
#   freq         — "A" annual, "Q" quarterly, "M" monthly
#   country_dim  — name of the dimension that holds the country code
#   obs_value    — field name for the observation value in the CSV response
#   note         — human-readable description
#
# We always request format=csvfilewithlabels and parse with pandas so we avoid
# the heavier pandasdmx XML parse in the base hot-path. pandasdmx is used only
# as a lazy import for optional structure queries — the actual data fetch is a
# direct requests.get to the CSV endpoint.

SPECS: dict[str, dict] = {
    # OE-01: Composite Leading Indicator — monthly amplitude-adjusted index
    # dim key: {COUNTRY}.{FREQ}.{SUBJECT}.{MEASURE}.{UNIT}.{POWERCODE}.{REF_PERIOD}
    # LI = leading indicator, AA = amplitude adjusted, IX = index
    "OE-01": {
        "agency": "OECD.SDD.STES",
        "dataflow": "DSD_STES@DF_CLI",
        "dim_key": "all",
        "params": {
            "format": "csvfilewithlabels",
            "dimensionAtObservation": "AllDimensions",
        },
        # CSV filter applied AFTER download (subsets the large response)
        "filters": {"SUBJECT": "LI", "MEASURE": "AA"},
        "freq": "M",  # monthly → aggregate to annual mean
        "country_col": "REF_AREA",
        "value_col": "OBS_VALUE",
        "period_col": "TIME_PERIOD",
        "note": "CLI amplitude-adjusted index (monthly → annual mean)",
    },
    # OE-02: Consumer Confidence Index — quarterly
    # KEI dataset contains CCSCONF (Consumer Confidence composite)
    "OE-02": {
        "agency": "OECD.SDD.STES",
        "dataflow": "DSD_KEI@DF_KEI",
        "dim_key": "all",
        "params": {
            "format": "csvfilewithlabels",
            "dimensionAtObservation": "AllDimensions",
        },
        "filters": {"SUBJECT": "CCSCONF"},
        "freq": "Q",  # quarterly → aggregate to annual mean
        "country_col": "REF_AREA",
        "value_col": "OBS_VALUE",
        "period_col": "TIME_PERIOD",
        "note": "Consumer Confidence composite (quarterly → annual mean)",
    },
    # OE-03: Business Confidence Index — quarterly
    # KEI dataset contains BSCICP02 (Business Confidence Indicator)
    "OE-03": {
        "agency": "OECD.SDD.STES",
        "dataflow": "DSD_KEI@DF_KEI",
        "dim_key": "all",
        "params": {
            "format": "csvfilewithlabels",
            "dimensionAtObservation": "AllDimensions",
        },
        "filters": {"SUBJECT": "BSCICP02"},
        "freq": "Q",
        "country_col": "REF_AREA",
        "value_col": "OBS_VALUE",
        "period_col": "TIME_PERIOD",
        "note": "Business Confidence Indicator (quarterly → annual mean)",
    },
    # OE-04: Total social spending % GDP (SOCX aggregates)
    # dim key pattern: {COUNTRY}.{FREQ}.{EXPEND}.{UNIT}.{SOURCE}.{BRANCH}.{TYPE}
    # All public+mandatory private, total branches, % GDP (PT_B1GQ)
    # ES10 = total social policy areas; _T = all sources
    "OE-04": {
        "agency": "OECD.ELS.SPD",
        "dataflow": "DSD_SOCX_AGG@DF_SOCX_AGG",
        "dim_key": "all",
        "params": {
            "format": "csvfilewithlabels",
            "dimensionAtObservation": "AllDimensions",
        },
        "filters": {"UNIT_MEASURE": "PT_B1GQ", "EXPENDITURE": "ES10"},
        "freq": "A",
        "country_col": "REF_AREA",
        "value_col": "OBS_VALUE",
        "period_col": "TIME_PERIOD",
        "note": "Total social spending % GDP (SOCX, annual)",
    },
    # OE-05: Gini coefficient of disposable income (Income Distribution DB)
    # Measure: INC_DISP_GINI; methodology: METH2012; age: _T (all); definition: D_CUR
    "OE-05": {
        "agency": "OECD.WISE.INE",
        "dataflow": "DSD_WISE_IDD@DF_IDD",
        "dim_key": "all",
        "params": {
            "format": "csvfilewithlabels",
            "dimensionAtObservation": "AllDimensions",
        },
        "filters": {"MEASURE": "INC_DISP_GINI", "AGE": "_T"},
        "freq": "A",
        "country_col": "REF_AREA",
        "value_col": "OBS_VALUE",
        "period_col": "TIME_PERIOD",
        "note": "Gini coefficient of disposable income (annual)",
    },
    # OE-06: Total tax revenue % GDP (Global Revenue Statistics)
    # STANDARD_REVENUE: _T = total taxes; SECTOR: S13 = general government;
    # UNIT_MEASURE: PT_B1GQ = % GDP
    "OE-06": {
        "agency": "OECD.CTP.TPS",
        "dataflow": "DSD_REV_COMP_GLOBAL@DF_RSGLOBAL",
        "dim_key": "all",
        "params": {
            "format": "csvfilewithlabels",
            "dimensionAtObservation": "AllDimensions",
        },
        "filters": {"STANDARD_REVENUE": "_T", "SECTOR": "S13", "UNIT_MEASURE": "PT_B1GQ"},
        "freq": "A",
        "country_col": "REF_AREA",
        "value_col": "OBS_VALUE",
        "period_col": "TIME_PERIOD",
        "note": "Total tax revenue % GDP (annual)",
    },
    # OE-07: Total Factor Productivity (MFP) growth rate
    # PDB growth rates dataset — annual; MEASURE: T_GDPHRS_MAT (MFP contribution)
    # or MFP_GR if available; UNIT_MEASURE: PC (percentage change)
    # ACTIVITY: _T = total economy
    "OE-07": {
        "agency": "OECD.SDD.TPS",
        "dataflow": "DSD_PDB@DF_PDB_GR",
        "dim_key": "all",
        "params": {
            "format": "csvfilewithlabels",
            "dimensionAtObservation": "AllDimensions",
        },
        # MFP = Multi-Factor Productivity (OECD term for TFP)
        # Filter by measure containing MFP and activity = total economy (_T)
        "filters": {"MEASURE": "MFP", "ACTIVITY": "_T"},
        "freq": "A",
        "country_col": "REF_AREA",
        "value_col": "OBS_VALUE",
        "period_col": "TIME_PERIOD",
        "note": "TFP (MFP) growth rate, total economy (annual)",
    },
}

# alpha-2 -> alpha-3 fallback for older OECD datasets that use ISO-3166-1 alpha-2
# (e.g. CLI uses country codes like "AUS" already, KEI uses "AU" sometimes)
# We attempt conversion below; rows that cannot resolve are dropped (per contract).
_ALPHA2_TO_ALPHA3: dict[str, str] = {
    "AU": "AUS",
    "AT": "AUT",
    "BE": "BEL",
    "CA": "CAN",
    "CL": "CHL",
    "CO": "COL",
    "CR": "CRI",
    "CZ": "CZE",
    "DK": "DNK",
    "EE": "EST",
    "FI": "FIN",
    "FR": "FRA",
    "DE": "DEU",
    "GR": "GRC",
    "HU": "HUN",
    "IS": "ISL",
    "IE": "IRL",
    "IL": "ISR",
    "IT": "ITA",
    "JP": "JPN",
    "KR": "KOR",
    "LV": "LVA",
    "LT": "LTU",
    "LU": "LUX",
    "MX": "MEX",
    "NL": "NLD",
    "NZ": "NZL",
    "NO": "NOR",
    "PL": "POL",
    "PT": "PRT",
    "SK": "SVK",
    "SI": "SVN",
    "ES": "ESP",
    "SE": "SWE",
    "CH": "CHE",
    "TR": "TUR",
    "GB": "GBR",
    "US": "USA",
    "BR": "BRA",
    "CN": "CHN",
    "IN": "IND",
    "ID": "IDN",
    "RU": "RUS",
    "ZA": "ZAF",
    "AR": "ARG",
    "SA": "SAU",
}


def _to_iso3(code: str) -> str:
    """Normalise a country code to ISO alpha-3 upper-case.

    Handles both alpha-3 (pass-through) and alpha-2 (mapped via small lookup).
    Returns an empty string if neither form resolves.
    """
    code = str(code or "").strip().upper()
    if len(code) == 3:
        return code
    if len(code) == 2:
        return _ALPHA2_TO_ALPHA3.get(code, "")
    return ""


def _extract_year(period: str) -> int | None:
    """Extract the calendar year from an SDMX TIME_PERIOD string.

    Handles:
        "2023"      — annual
        "2023-Q3"   — quarterly
        "2023-03"   — monthly (YYYY-MM)
    Returns None if unparseable.
    """
    s = str(period or "").strip()
    if not s:
        return None
    # Annual: "2023"
    if len(s) == 4 and s.isdigit():
        try:
            return int(s)
        except ValueError:
            return None
    # Quarterly: "2023-Q3" or monthly: "2023-03"
    parts = s.split("-")
    if parts and len(parts[0]) == 4 and parts[0].isdigit():
        try:
            return int(parts[0])
        except ValueError:
            return None
    return None


def parse_oecd_csv(
    df_raw: "pd.DataFrame",
    spec: dict,
    iso3_map: dict[str, str],
) -> pd.DataFrame:
    """PURE: OECD SDMX CSV DataFrame -> DataFrame[country, year, value].

    Steps:
      1. Apply column-level filters from spec['filters'] to narrow to the
         right measure/unit/subject within a multi-series bulk response.
      2. Map country codes (alpha-2 or alpha-3) to canonical name_1.
      3. Extract integer year from TIME_PERIOD (handles M/Q/A periods).
      4. For sub-annual frequencies aggregate to annual mean per
         (canonical country, year).
      5. Return [country, year, value]; let the base add is_predicted=False.

    Pure function: no network, no AWS — fully unit-testable.
    """
    country_col = spec["country_col"]
    value_col = spec["value_col"]
    period_col = spec["period_col"]

    # Normalise column names (the csvfilewithlabels format may include spaces or
    # differ in casing between datasets)
    df = df_raw.copy()
    df.columns = [c.strip() for c in df.columns]

    # --- apply post-download column filters ---
    filters: dict[str, str] = spec.get("filters", {})
    for col, val in filters.items():
        if col in df.columns:
            # csvfilewithlabels may render a cell as "CODE: Label" - compare the code part.
            codes = df[col].astype(str).str.split(":").str[0].str.strip().str.upper()
            df = df[codes == val.upper()]

    if df.empty or country_col not in df.columns:
        return pd.DataFrame(columns=["country", "year", "value"])

    rows = []
    for _, row in df.iterrows():
        raw_code = str(row.get(country_col) or "").split(":")[0].strip()
        iso3 = _to_iso3(raw_code)
        canonical = iso3_map.get(iso3)
        if not canonical:
            continue
        period = row.get(period_col)
        year = _extract_year(str(period) if period is not None else "")
        if year is None:
            continue
        raw_val = row.get(value_col)
        try:
            val = float(raw_val)
        except (TypeError, ValueError):
            continue
        if val != val:  # NaN
            continue
        rows.append({"country": canonical, "year": year, "value": val})

    if not rows:
        return pd.DataFrame(columns=["country", "year", "value"])

    # Aggregate sub-annual periods to annual mean per (country, year)
    result = pd.DataFrame(rows).groupby(["country", "year"], as_index=False)["value"].mean()
    return result


def _fetch_oecd_csv(agency: str, dataflow: str, params: dict) -> pd.DataFrame:
    """Fetch an OECD SDMX dataflow as CSV (lazy-imports requests).

    Uses the /data endpoint with format=csvfilewithlabels.  Downloads the full
    dataflow (dim_key=all) and lets parse_oecd_csv apply measure/filter selects
    in-process — avoids per-series HTTP round-trips and keeps the network logic
    minimal and testable-around.
    """
    import io
    import requests  # lazy import — tests never hit this

    url = f"{OECD_SDMX_REST}/data/{agency},{dataflow}/all"
    base.logger.info(f"OECD fetch: GET {url} params={params}")
    resp = requests.get(url, params=params, timeout=300)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    base.logger.info(f"OECD {dataflow}: {len(df):,} raw rows, {len(df.columns)} columns")
    return df


def fetch_one(spec: dict) -> pd.DataFrame:
    iid = spec["id_string"]
    if iid not in SPECS:
        raise ValueError(f"unknown OECD indicator {iid!r}")
    cfg = SPECS[iid]
    iso3_map = base.load_iso3_country_map()
    raw_df = _fetch_oecd_csv(cfg["agency"], cfg["dataflow"], cfg["params"])
    return parse_oecd_csv(raw_df, cfg, iso3_map)


if __name__ == "__main__":
    base.run_fetcher("OECD", fetch_one)
