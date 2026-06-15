"""UCDP conflict fetcher (enrichment stage 2) — spec-driven, bulk-CSV edition.

Replaces the old paginated REST API approach (which requires a token since 2025)
with UCDP's open bulk CSV downloads:

  GED       https://ucdp.uu.se/downloads/ged/ged251-csv.zip
  one-sided https://ucdp.uu.se/downloads/nsos/ucdp-onesided-241-csv.zip
  ACD       https://ucdp.uu.se/downloads/ucdpprio/ucdp-prio-acd-261-csv.zip
  OV CY     https://ucdp.uu.se/downloads/organizedviolencecy/organizedviolencecy-261-csv.zip
  Onset     https://ucdp.uu.se/downloads/onset/ucdp-intrastate-country-onset-251.csv

NOTE: UCDP bulk URLs are version/date-stamped (the numeric suffix encodes the
dataset version, e.g., 251 = v25.1, 241 = v24.1, 261 = v26.1).  When a new
annual release is published (~June each year), update the bulk_url values in
specs.json accordingly.  Column names can also change across versions — always
verify against the codebook PDF bundled inside each zip.

Each zip is downloaded once and cached in-process across all indicators that
share the same source so repeated task invocations within one Batch job never
re-download the same archive.

INDICATOR REGISTRY (specs.json — loaded at startup):
  Legacy seed codes (kept working):
    UC-01   state-based deaths (GED type_of_violence==1 sum best)
    UC-04   one-sided violence deaths (GED type_of_violence==3 sum best)
  Enrichment codes:
    UCDP_GED_TOTAL_DEATHS     sum(best) all tov
    UCDP_SB_DEATHS_BEST       sum(best) tov=1
    UCDP_NS_DEATHS_BEST       sum(best) tov=2
    UCDP_OS_DEATHS_BEST       sum(best) tov=3
    UCDP_GED_CIV_DEATHS       sum(deaths_civilians) all tov
    UCDP_GED_OS_EVENTS        count events tov=3
    UCDP_GED_NS_EVENTS        count events tov=2
    UCDP_GED_GEOREGION_SPREAD nunique(adm_1) all tov
    UCDP_OS_DEATHS_GOVT       sum(deaths_best) govt-perp from onesided
    UCDP_OS_GOVT_PERP         binary(UCDP_OS_DEATHS_GOVT>0)    [derived]
    UCDP_OS_ACTOR_COUNT       nunique(actor_id) from onesided
    UCDP_SB_INTENSITY_WAR     binary(max intensity_level==2)   [derived]
    UCDP_SB_CONFLICT_COUNT    nunique(conflict_id) from ACD
    UCDP_SB_ONSET             binary onset from onset CSV
    UCDP_YEARS_SINCE_LAST_CONFLICT  derived from OV CY        [derived]

Country mapping:
  GED/onset: country NAME string -> canonical via UCDP_NAME_OVERRIDES + alias map
  onesided/ACD/OV: gwno_where / gwno_loc / gwno_a (Gleditsch-Ward numeric codes)
    -> ISO3 via GW_ISO3_OVERRIDES; then ISO3 -> canonical via load_iso3_country_map

GW->ISO3 crosswalk: embedded GW_ISO3_OVERRIDES (covering ~200 UCDP-active countries);
extend if unmapped codes appear in logs.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

# --- path wiring (image: base is at /app; test: both dirs on sys.path) --------
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")
import qgi_fetcher_base as base  # noqa: E402

logger = logging.getLogger("qgi-fetcher")

# ---------------------------------------------------------------------------
# Specs registry — load once at module import
# ---------------------------------------------------------------------------
_SPECS_PATH = Path(__file__).resolve().parent / "specs.json"
with _SPECS_PATH.open("r", encoding="utf-8") as _fh:
    _RAW_SPECS: list[dict[str, Any]] = json.load(_fh)

SPECS_BY_CODE: dict[str, dict[str, Any]] = {s["code"]: s for s in _RAW_SPECS}

# ---------------------------------------------------------------------------
# Country-name overrides (UCDP GED / onset use NAME strings, not ISO codes)
# ---------------------------------------------------------------------------
UCDP_NAME_OVERRIDES: dict[str, str] = {
    "DR Congo (Zaire)": "The Democratic Republic of the Congo",
    "Myanmar (Burma)": "Myanmar",
    "Russia (Soviet Union)": "Russia",
    "Yemen (North Yemen)": "Yemen",
    "Serbia (Yugoslavia)": "Serbia",
    "Cambodia (Kampuchea)": "Cambodia",
    "Zimbabwe (Rhodesia)": "Zimbabwe",
    "Madagascar (Malagasy)": "Madagascar",
    "United States of America": "United States",
    "Ivory Coast": "Cote d'Ivoire",
    "Kingdom of eSwatini (Swaziland)": "Eswatini",
    "South Vietnam": "Vietnam",
    "Vietnam (South Vietnam)": "Vietnam",
    "Pakistan (West Pakistan)": "Pakistan",
    "Iran (Persia)": "Iran",
    "Iraq (Ottoman Empire)": "Iraq",
    "Turkey (Ottoman Empire)": "Turkey",
    "Libya (Tripolitania)": "Libya",
    "Tanzania (Tanganyika)": "Tanzania",
    "Burkina Faso (Upper Volta)": "Burkina Faso",
    "Benin (Dahomey)": "Benin",
    "Sri Lanka (Ceylon)": "Sri Lanka",
    "Bolivia (Plurinational State of)": "Bolivia",
    "Venezuela (Bolivarian Republic of)": "Venezuela",
    "Moldova (Republic of)": "Moldova",
    "Korea, Democratic People's Republic of": "North Korea",
    "Korea, Republic of": "South Korea",
    "Lao People's Democratic Republic": "Laos",
    "Syrian Arab Republic": "Syria",
    "Viet Nam": "Vietnam",
    "Timor-Leste": "Timor-Leste",
    "Congo": "Republic of the Congo",
    "Congo, the Democratic Republic of the": "The Democratic Republic of the Congo",
}

# ---------------------------------------------------------------------------
# Gleditsch-Ward (GW) numeric -> ISO alpha-3 crosswalk
# Covers countries appearing in UCDP onesided/ACD/OV datasets.
# Source: COW/Gleditsch-Ward state list crosswalked to ISO 3166-1 alpha-3.
# Extend GW_ISO3_OVERRIDES when unmapped codes appear in logs.
# ---------------------------------------------------------------------------
GW_ISO3_OVERRIDES: dict[int, str] = {
    2: "USA",
    20: "CAN",
    40: "CUB",
    41: "HTI",
    42: "DOM",
    51: "JAM",
    52: "TTO",
    53: "BRB",
    54: "DMA",
    55: "GRD",
    56: "ATG",
    57: "LCA",
    58: "VCT",
    60: "BLZ",
    70: "MEX",
    80: "GTM",
    90: "HND",
    91: "ELS",
    92: "NIC",
    93: "CRI",
    94: "PAN",
    100: "COL",
    101: "VEN",
    110: "GUY",
    115: "SUR",
    130: "ECU",
    135: "PER",
    140: "BRA",
    145: "BOL",
    150: "PRY",
    155: "CHL",
    160: "ARG",
    165: "URY",
    200: "GBR",
    205: "IRL",
    210: "NLD",
    211: "BEL",
    212: "LUX",
    220: "FRA",
    225: "CHE",
    230: "ESP",
    235: "PRT",
    255: "DEU",
    260: "DEU",
    265: "DEU",
    267: "DEU",
    269: "DEU",
    270: "DEU",
    275: "DEU",
    290: "POL",
    300: "AUT",
    305: "HUN",
    310: "CZE",
    315: "CZE",
    316: "SVK",
    317: "SVK",
    325: "ITA",
    338: "MLT",
    339: "ALB",
    343: "MKD",
    344: "HRV",
    345: "SRB",
    346: "BIH",
    347: "KOS",
    349: "SVN",
    350: "GRC",
    352: "CYP",
    355: "BGR",
    360: "ROU",
    365: "RUS",
    366: "EST",
    367: "LVA",
    368: "LTU",
    369: "UKR",
    370: "BLR",
    371: "MDA",
    372: "GEO",
    373: "AZE",
    374: "ARM",
    375: "FIN",
    380: "SWE",
    385: "NOR",
    390: "DNK",
    395: "ISL",
    402: "CPV",
    403: "STP",
    404: "GNQ",
    411: "GAB",
    420: "COG",
    435: "GMB",
    436: "MLI",
    437: "SEN",
    438: "BEN",
    439: "MRT",
    450: "LBR",
    451: "SLE",
    452: "GHA",
    461: "TGO",
    471: "CMR",
    475: "NGA",
    481: "CAF",
    482: "COD",
    483: "COD",  # Zaire -> DRC
    484: "COD",
    490: "UGA",
    500: "KEN",
    501: "TZA",
    510: "SOM",
    516: "BDI",
    517: "RWA",
    520: "ETH",
    522: "ERI",
    530: "ETH",
    531: "ERI",
    540: "AGO",
    541: "MOZ",
    551: "ZMB",
    552: "ZWE",
    553: "MWI",
    560: "ZAF",
    565: "NAM",
    570: "LSO",
    571: "BWA",
    572: "SWZ",
    580: "MDG",
    590: "MUS",
    600: "MAR",
    615: "DZA",
    616: "TUN",
    620: "LBY",
    625: "SDN",
    626: "SSD",
    630: "IRN",
    640: "TUR",
    645: "IRQ",
    651: "EGY",
    652: "SYR",
    660: "LBN",
    663: "JOR",
    666: "ISR",
    667: "PSE",
    670: "SAU",
    678: "YEM",
    679: "YEM",
    680: "YEM",
    690: "KWT",
    692: "BHR",
    694: "QAT",
    696: "ARE",
    698: "OMN",
    700: "AFG",
    701: "PAK",
    703: "BGD",
    710: "CHN",
    711: "TWN",
    712: "MNG",
    713: "KOR",
    731: "PRK",
    732: "KOR",
    740: "JPN",
    750: "IND",
    760: "BTN",
    770: "PAK",
    771: "BGD",
    775: "MMR",
    780: "LKA",
    781: "MDV",
    790: "NPL",
    800: "THA",
    811: "KHM",
    812: "LAO",
    816: "VNM",
    817: "VNM",
    820: "MYS",
    830: "SGP",
    835: "BRN",
    840: "PHL",
    850: "IDN",
    860: "TLS",
    900: "AUS",
    910: "PNG",
    920: "NZL",
    940: "SOL",
    950: "FJI",
}


# ---------------------------------------------------------------------------
# Bulk-download cache: {url: DataFrame}
# ---------------------------------------------------------------------------
_bulk_cache: dict[str, pd.DataFrame] = {}


def _download_zip_csv(url: str, zip_csv_pattern: str | None = None) -> pd.DataFrame:
    """Download a zip URL and read the first (or pattern-matched) CSV inside it."""
    import requests

    logger.info(f"Downloading bulk CSV: {url}")
    resp = requests.get(url, timeout=600, stream=True)
    resp.raise_for_status()
    raw = resp.content
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError(f"No CSV found in zip: {url}")
        if zip_csv_pattern:
            matched = [n for n in names if zip_csv_pattern.lower() in n.lower()]
            chosen = matched[0] if matched else names[0]
        else:
            chosen = names[0]
        logger.info(f"Reading {chosen} from {url}")
        with zf.open(chosen) as fh:
            df = pd.read_csv(fh, low_memory=False)
    logger.info(f"Loaded {len(df):,} rows from {chosen}")
    return df


def _download_direct_csv(url: str) -> pd.DataFrame:
    """Download a plain CSV URL (no zip)."""
    import requests

    logger.info(f"Downloading CSV: {url}")
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), low_memory=False)
    logger.info(f"Loaded {len(df):,} rows from {url}")
    return df


def _load_bulk(spec: dict[str, Any]) -> pd.DataFrame:
    """Fetch (or return cached) the bulk DataFrame for a given spec's source."""
    url = spec["bulk_url"]
    if url in _bulk_cache:
        return _bulk_cache[url]
    if url.endswith(".csv"):
        df = _download_direct_csv(url)
    else:
        df = _download_zip_csv(url)
    _bulk_cache[url] = df
    return df


# ---------------------------------------------------------------------------
# Name mapping helpers
# ---------------------------------------------------------------------------


def build_name_map(alias_map: dict[str, str]) -> dict[str, str]:
    """Merge the shared alias->name_1 map with UCDP-specific overrides."""
    m = dict(alias_map)
    m.update(UCDP_NAME_OVERRIDES)
    return m


def _resolve_gw_codes(raw_gwno: Any) -> list[int]:
    """Parse a semicolon- or comma-separated GW code string into a list of ints."""
    if pd.isna(raw_gwno):
        return []
    txt = str(raw_gwno).strip()
    parts = txt.replace(",", ";").split(";")
    out = []
    for p in parts:
        p = p.strip()
        if p:
            try:
                out.append(int(float(p)))
            except (ValueError, TypeError):
                pass
    return out


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _apply_tov_filter(df: pd.DataFrame, filter_params: dict) -> pd.DataFrame:
    """Apply type_of_violence filter if present.

    Supports:
      type_of_violence: int   — exact match
      type_of_violence_in: list[int] — membership filter (OR across values)
    """
    tov_in = filter_params.get("type_of_violence_in")
    if tov_in is not None and "type_of_violence" in df.columns:
        tov_nums = [int(v) for v in tov_in]
        df = df[pd.to_numeric(df["type_of_violence"], errors="coerce").isin(tov_nums)]
        return df
    tov = filter_params.get("type_of_violence")
    if tov is not None and "type_of_violence" in df.columns:
        df = df[pd.to_numeric(df["type_of_violence"], errors="coerce") == int(tov)]
    return df


def _aggregate_ged(
    df: pd.DataFrame,
    spec: dict[str, Any],
    name_map: dict[str, str],
) -> pd.DataFrame:
    """Aggregate GED bulk CSV to (country, year, value)."""
    df = df.copy()
    df = _apply_tov_filter(df, spec.get("filter_params") or {})

    value_field = spec["value_field"]
    transform = spec["transform"]
    country_field = spec.get("country_field", "country")

    # Map country name -> canonical
    df["__canon"] = df[country_field].astype(str).str.strip().map(name_map)
    df = df.dropna(subset=["__canon"])

    # Year
    df["__year"] = pd.to_numeric(df.get("year", pd.Series([], dtype=float)), errors="coerce")
    df = df.dropna(subset=["__year"])
    df["__year"] = df["__year"].astype(int)

    if transform == "sum":
        df["__val"] = pd.to_numeric(df[value_field], errors="coerce").fillna(0.0)
        out = (
            df.groupby(["__canon", "__year"], as_index=False)["__val"]
            .sum()
            .rename(columns={"__canon": "country", "__year": "year", "__val": "value"})
        )
    elif transform == "count":
        out = (
            df.groupby(["__canon", "__year"], as_index=False)
            .size()
            .rename(columns={"__canon": "country", "__year": "year", "size": "value"})
        )
        out["value"] = out["value"].astype(float)
    elif transform == "count_distinct":
        # For adm_1: strip/lowercase before nunique
        col = df[value_field].astype(str).str.strip().str.lower()
        df["__distinct_key"] = col
        out = (
            df.groupby(["__canon", "__year"])["__distinct_key"]
            .nunique()
            .reset_index()
            .rename(columns={"__canon": "country", "__year": "year", "__distinct_key": "value"})
        )
        out["value"] = out["value"].astype(float)
    else:
        raise ValueError(f"Unknown transform {transform!r} for GED indicator")

    return out


def _aggregate_onesided(
    df: pd.DataFrame,
    spec: dict[str, Any],
    gw_to_canonical: dict[int, str],
) -> pd.DataFrame:
    """Aggregate onesided bulk CSV to (country, year, value).

    gwno_location may be semicolon-separated. Govt filter: is_government_actor==1.
    Also supports legacy side_a_dset_id_type filter for backward compat.
    """
    df = df.copy()
    filter_params = spec.get("filter_params") or {}
    value_field = spec["value_field"]
    transform = spec["transform"]

    # Govt-perp filter — prefer is_government_actor boolean column (v24.1+)
    if "is_government_actor" in filter_params:
        target_val = int(filter_params["is_government_actor"])
        if "is_government_actor" in df.columns:
            df = df[pd.to_numeric(df["is_government_actor"], errors="coerce") == target_val]
        else:
            # Fallback: substring on side_a for older dataset versions
            logger.warning("is_government_actor column not found; falling back to side_a substring")
            if "side_a" in df.columns:
                mask = df["side_a"].astype(str).str.lower().str.contains("government of|govt of", na=False)
                df = df[mask]
    elif filter_params.get("side_a_dset_id_type") == "government":
        # Legacy path: kept for any spec still using old filter key
        if "side_a" in df.columns:
            mask = df["side_a"].astype(str).str.lower().str.contains("government of|govt of", na=False)
            df = df[mask]

    # Year
    df["__year"] = pd.to_numeric(df.get("year", pd.Series([], dtype=float)), errors="coerce")
    df = df.dropna(subset=["__year"])
    df["__year"] = df["__year"].astype(int)

    # Expand gwno_where (semicolon-separated multi-country)
    gw_col = spec.get("country_field", "gwno_where")
    rows = []
    for _, row in df.iterrows():
        gw_codes = _resolve_gw_codes(row.get(gw_col))
        for gwno in gw_codes:
            canon = gw_to_canonical.get(gwno)
            if not canon:
                continue
            rows.append(
                {
                    "country": canon,
                    "year": int(row["__year"]),
                    "_val": row.get(value_field),
                    "_actor": row.get("actor_id", row.get("actorid", "")),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["country", "year", "value"])

    expanded = pd.DataFrame(rows)
    expanded["_val_num"] = pd.to_numeric(expanded["_val"], errors="coerce").fillna(0.0)

    if transform == "sum":
        out = (
            expanded.groupby(["country", "year"], as_index=False)["_val_num"]
            .sum()
            .rename(columns={"_val_num": "value"})
        )
    elif transform == "binary":
        agg = expanded.groupby(["country", "year"], as_index=False)["_val_num"].sum()
        agg["value"] = (agg["_val_num"] > 0).astype(float)
        out = agg[["country", "year", "value"]]
    elif transform == "count_distinct":
        out = (
            expanded.groupby(["country", "year"])["_actor"].nunique().reset_index().rename(columns={"_actor": "value"})
        )
        out["value"] = out["value"].astype(float)
    else:
        raise ValueError(f"Unknown transform {transform!r} for onesided indicator")

    return out


def _aggregate_acd(
    df: pd.DataFrame,
    spec: dict[str, Any],
    gw_to_canonical: dict[int, str],
) -> pd.DataFrame:
    """Aggregate UCDP/PRIO ACD bulk CSV to (country, year, value).

    gwno_loc is semicolon-separated. Supports:
      binary          — 1 if any row in country-year reached intensity_level==2
      binary_active   — 1 if any row present after pre_filter (used with pre_filter)
      count_distinct  — nunique(conflict_id) per country-year

    Optional spec key ``pre_filter``: {column: value} — numeric equality filter
    applied to ACD rows before expansion.  Used for type_of_conflict / incompatibility
    / ep_end slices.
    """
    df = df.copy()
    value_field = spec["value_field"]
    transform = spec["transform"]
    gw_col = spec.get("country_field", "gwno_loc")

    # Apply optional pre_filter (e.g. type_of_conflict==4, incompatibility==2, ep_end==1)
    pre_filter = spec.get("pre_filter") or {}
    for col, val in pre_filter.items():
        if col not in df.columns:
            logger.warning(f"ACD pre_filter column {col!r} not found; available: {list(df.columns)}")
            return pd.DataFrame(columns=["country", "year", "value"])
        df = df[pd.to_numeric(df[col], errors="coerce") == float(val)]
        logger.info(f"ACD pre_filter {col}=={val}: {len(df)} rows remain")

    # Year
    df["__year"] = pd.to_numeric(df.get("year", pd.Series([], dtype=float)), errors="coerce")
    df = df.dropna(subset=["__year"])
    df["__year"] = df["__year"].astype(int)

    rows = []
    for _, row in df.iterrows():
        gw_codes = _resolve_gw_codes(row.get(gw_col))
        for gwno in gw_codes:
            canon = gw_to_canonical.get(gwno)
            if not canon:
                continue
            rows.append(
                {
                    "country": canon,
                    "year": int(row["__year"]),
                    "_intensity": row.get("intensity_level"),
                    "_conflict_id": row.get("conflict_id", row.get("ConflictId", "")),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["country", "year", "value"])

    expanded = pd.DataFrame(rows)
    expanded["_intensity_num"] = pd.to_numeric(expanded["_intensity"], errors="coerce")

    if transform == "binary":
        # 1 if any conflict in country-year reached intensity_level==2 (war)
        agg = expanded.groupby(["country", "year"])["_intensity_num"].max().reset_index()
        agg["value"] = (agg["_intensity_num"] == 2).astype(float)
        out = agg[["country", "year", "value"]]
    elif transform == "binary_active":
        # 1 for any country-year that has at least one row after pre_filter
        out = expanded.groupby(["country", "year"], as_index=False).size().rename(columns={"size": "_cnt"})
        out["value"] = (out["_cnt"] > 0).astype(float)
        out = out[["country", "year", "value"]]
    elif transform == "count_distinct":
        out = (
            expanded.groupby(["country", "year"])["_conflict_id"]
            .nunique()
            .reset_index()
            .rename(columns={"_conflict_id": "value"})
        )
        out["value"] = out["value"].astype(float)
    else:
        raise ValueError(f"Unknown transform {transform!r} for ACD indicator")

    return out


def _aggregate_onset_csv(
    df: pd.DataFrame,
    spec: dict[str, Any],
    gw_to_canonical: dict[int, str],
) -> pd.DataFrame:
    """Aggregate UCDP Onset CSV to (country, year, value).

    The primary onset binary field may be called 'onset', 'new_conflict', or
    'onset_2'; try each in order and use the first found.
    """
    df = df.copy()
    gw_col = spec.get("country_field", "gwno_a")

    # Year
    df["__year"] = pd.to_numeric(df.get("year", pd.Series([], dtype=float)), errors="coerce")
    df = df.dropna(subset=["__year"])
    df["__year"] = df["__year"].astype(int)

    # Find the onset field — check spec value_field first, then fall back to candidates
    spec_value_field = spec.get("value_field", "")
    onset_candidates = [spec_value_field, "onset", "newconf", "new_conflict", "onset1", "onset_1", "onset2", "onset_2"]
    onset_field = None
    for cand in onset_candidates:
        if cand and cand in df.columns:
            onset_field = cand
            break
    if onset_field is None:
        logger.warning("UCDP Onset CSV: no onset field found; available: %s", list(df.columns))
        return pd.DataFrame(columns=["country", "year", "value"])

    logger.info(f"UCDP Onset: using field '{onset_field}'")

    rows = []
    for _, row in df.iterrows():
        gw_codes = _resolve_gw_codes(row.get(gw_col))
        for gwno in gw_codes:
            canon = gw_to_canonical.get(gwno)
            if not canon:
                continue
            onset_val = row.get(onset_field)
            try:
                val = float(onset_val) if onset_val not in (None, "") else 0.0
            except (TypeError, ValueError):
                val = 0.0
            rows.append({"country": canon, "year": int(row["__year"]), "value": val})

    if not rows:
        return pd.DataFrame(columns=["country", "year", "value"])

    out = (
        pd.DataFrame(rows).groupby(["country", "year"], as_index=False)["value"].max()
    )  # binary max = 1 if any row is 1
    out["value"] = (out["value"] > 0).astype(float)
    return out


def _aggregate_ov(
    df: pd.DataFrame,
    spec: dict[str, Any],
    gw_to_canonical: dict[int, str],
    name_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Aggregate OV (organized violence country-year) CSV to years_since_last_conflict.

    Looks for sb_exist, ns_exist, os_exist columns (or variants); builds a
    country-year panel of any-conflict activity, then derives years elapsed
    since the last active year up to each observation year.

    Dataset v26.1 (organizedviolencecy-261) uses a name-based 'country' column
    and integer 0/1 activity flags. Older versions used gwno_loc GW codes.
    Both layouts are handled: if country_field=='country', map via name_map;
    otherwise treat as semicolon-separated GW codes via gw_to_canonical.
    """
    df = df.copy()
    country_field = spec.get("country_field", "gwno_loc")

    # Year
    df["__year"] = pd.to_numeric(df.get("year", pd.Series([], dtype=float)), errors="coerce")
    df = df.dropna(subset=["__year"])
    df["__year"] = df["__year"].astype(int)

    # Detect activity-flag columns
    def _as_bool(series: pd.Series) -> pd.Series:
        """Convert various encoding ('yes'/'no', 1/0, True/False) to bool."""
        s = series.astype(str).str.strip().str.lower()
        return s.isin(["1", "yes", "true", "1.0"]).astype(int)

    def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
        for c in candidates:
            if c in df.columns:
                return c
        return None

    sb_col = _find_col(df, ["sb_exist", "sb_active", "sb"])
    ns_col = _find_col(df, ["ns_exist", "ns_active", "ns"])
    os_col = _find_col(df, ["os_exist", "os_active", "os"])

    if sb_col is None and ns_col is None and os_col is None:
        logger.warning("UCDP OV CSV: no activity flag columns found; cols: %s", list(df.columns))
        return pd.DataFrame(columns=["country", "year", "value"])

    # Build any_active flag
    flags = pd.DataFrame(index=df.index)
    for col in filter(None, [sb_col, ns_col, os_col]):
        flags[col] = _as_bool(df[col])
    df["__any_active"] = flags.max(axis=1)

    rows = []
    use_name_map = (country_field == "country") and name_map is not None

    if use_name_map:
        # v26.1 layout: country column is a name string
        for _, row in df.iterrows():
            raw_name = str(row.get(country_field, "")).strip()
            canon = name_map.get(raw_name)
            if not canon:
                continue
            rows.append(
                {
                    "country": canon,
                    "year": int(row["__year"]),
                    "active": int(row["__any_active"]),
                }
            )
    else:
        # Legacy layout: gwno-based country field
        for _, row in df.iterrows():
            gw_codes = _resolve_gw_codes(row.get(country_field))
            for gwno in gw_codes:
                canon = gw_to_canonical.get(gwno)
                if not canon:
                    continue
                rows.append(
                    {
                        "country": canon,
                        "year": int(row["__year"]),
                        "active": int(row["__any_active"]),
                    }
                )

    if not rows:
        return pd.DataFrame(columns=["country", "year", "value"])

    panel = (
        pd.DataFrame(rows).groupby(["country", "year"], as_index=False)["active"].max().sort_values(["country", "year"])
    )

    # For each country, compute years_since_last_active
    results = []
    for country, grp in panel.groupby("country"):
        grp = grp.sort_values("year").reset_index(drop=True)
        last_active: int | None = None
        for _, r in grp.iterrows():
            yr = int(r["year"])
            if int(r["active"]) == 1:
                last_active = yr
                results.append({"country": country, "year": yr, "value": 0.0})
            else:
                if last_active is not None:
                    results.append({"country": country, "year": yr, "value": float(yr - last_active)})
                # else: no prior conflict on record -> skip (NaN excluded)

    if not results:
        return pd.DataFrame(columns=["country", "year", "value"])
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# GW->canonical mapping (builds once using GW_ISO3_OVERRIDES + base ISO3 map)
# ---------------------------------------------------------------------------
_gw_to_canonical_cache: dict[int, str] | None = None


def build_gw_to_canonical(iso3_map: dict[str, str]) -> dict[int, str]:
    """Build {GW_code: canonical_name_1} from GW_ISO3_OVERRIDES + iso3_map."""
    out: dict[int, str] = {}
    for gw, iso3 in GW_ISO3_OVERRIDES.items():
        canon = iso3_map.get(iso3.upper())
        if canon:
            out[gw] = canon
    return out


def get_gw_to_canonical() -> dict[int, str]:
    global _gw_to_canonical_cache
    if _gw_to_canonical_cache is None:
        iso3_map = base.load_iso3_country_map()
        _gw_to_canonical_cache = build_gw_to_canonical(iso3_map)
    return _gw_to_canonical_cache


# ---------------------------------------------------------------------------
# fetch_one — the per-indicator entry point called by base.run_fetcher
# ---------------------------------------------------------------------------


def fetch_one(spec: dict[str, Any]) -> pd.DataFrame:
    """Fetch one UCDP indicator.

    spec must contain 'id_string' (the indicator code). The rest of the
    config is loaded from SPECS_BY_CODE[id_string] (specs.json).
    """
    iid = spec["id_string"]
    if iid not in SPECS_BY_CODE:
        raise ValueError(f"UCDP fetcher: unknown indicator {iid!r}. Known codes: {sorted(SPECS_BY_CODE)}")

    cfg = SPECS_BY_CODE[iid]
    source = cfg["source"]
    logger.info(f"UCDP fetch_one: {iid!r} source={source!r}")

    # Load bulk data (cached across indicators sharing the same URL)
    df_bulk = _load_bulk(cfg)

    if source == "ged_bulk":
        name_map = build_name_map(base.load_name_alias_map())
        return _aggregate_ged(df_bulk, cfg, name_map)

    elif source == "onesided_bulk":
        gw_map = get_gw_to_canonical()
        return _aggregate_onesided(df_bulk, cfg, gw_map)

    elif source == "acd_bulk":
        gw_map = get_gw_to_canonical()
        return _aggregate_acd(df_bulk, cfg, gw_map)

    elif source == "onset_csv":
        gw_map = get_gw_to_canonical()
        return _aggregate_onset_csv(df_bulk, cfg, gw_map)

    elif source == "ov_bulk":
        gw_map = get_gw_to_canonical()
        name_map = build_name_map(base.load_name_alias_map())
        return _aggregate_ov(df_bulk, cfg, gw_map, name_map=name_map)

    else:
        raise ValueError(f"UCDP fetcher: unknown source {source!r} for {iid!r}")


# ---------------------------------------------------------------------------
# Legacy parse_ged_records kept for backward compat + existing tests
# ---------------------------------------------------------------------------


def parse_ged_records(
    records: list[dict],
    tov: int,
    name_map: dict[str, str],
) -> pd.DataFrame:
    """PURE (legacy): GED event-record list -> DataFrame[country, year, value].

    Filters to type_of_violence==tov, maps country names, sums best fatalities.
    Kept so existing unit tests continue to pass unchanged.
    """
    rows = []
    for rec in records:
        if int(rec.get("type_of_violence", 0)) != tov:
            continue
        name = name_map.get(str(rec.get("country") or "").strip())
        if not name:
            continue
        year = rec.get("year")
        if year in (None, ""):
            continue
        try:
            best = float(rec.get("best") or 0)
        except (TypeError, ValueError):
            continue
        rows.append({"country": name, "year": int(year), "value": best})
    if not rows:
        return pd.DataFrame(columns=["country", "year", "value"])
    return pd.DataFrame(rows).groupby(["country", "year"], as_index=False)["value"].sum()


if __name__ == "__main__":
    base.run_fetcher("UCDP", fetch_one)
