"""UNHCR population fetcher — spec-driven enrichment stage 2.

One Fargate task per indicator (dispatcher sends INDICATOR_ID or INDICATORS_JSON).
Pulls the UNHCR population REST API (api.unhcr.org/population/v1/, no auth, CC BY 4.0),
aggregates to (canonical country, year, value), and hands the frame to the shared
base which writes parquet-completed + DDB + tracker + counter.

All indicator definitions live in src/specs.json (loaded at startup).  Adding a new
indicator = add an entry there + rebuild the image.  No code change required.

Supported transform types
--------------------------
sum                 : sum value_field by (country_field, year)
annual_change_rate  : derive pct YoY change from the base series (same endpoint/fields)
sum_fields          : sum multiple fields from the SAME endpoint record, then sum by group
ratio_pct           : sum(field_a) / sum(field_b) * 100 by group (both from same endpoint)
cross_endpoint_ratio: sum(numerator endpoint) / sum(denominator endpoint) * 100 joined on (country, year)
per_wb_pop_pct      : sum(value_field) / WB SP.POP.TOTL * 100 (cross-provider join)

Country codes in the API are ISO alpha-3 -> mapped to canonical name_1 via the
shared country-m49-map (iso_alpha3 column).
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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

UNHCR_BASE = "https://api.unhcr.org/population/v1"
WB_BASE = "https://api.worldbank.org/v2"
YEAR_FROM = 1990

_SPECS_PATH = Path(__file__).resolve().parent / "specs.json"
_SPECS_RAW: list[dict] = json.loads(_SPECS_PATH.read_text(encoding="utf-8"))

# Keyed by code; used at lookup time.
SPECS: dict[str, dict] = {s["code"]: s for s in _SPECS_RAW}

# Legacy alias map keeps the old code names working via the same spec entries.
# UN-01..UN-06 are already in specs.json so this is implicit — no extra mapping needed.


# ---------------------------------------------------------------------------
# Raw-data cache (one network call per endpoint, shared across all indicators)
# ---------------------------------------------------------------------------

_raw_cache: dict[str, list[dict]] = {}


def fetch_unhcr_raw(endpoint: str, filter_params: dict[str, Any] | None = None) -> list[dict]:
    """Paginated GET of the UNHCR population API.  Returns the flat item list.

    Results are cached by endpoint so indicators sharing an endpoint (e.g. all
    four population-endpoint indicators) only hit the network once per task run.
    """
    cache_key = endpoint
    if cache_key in _raw_cache:
        return _raw_cache[cache_key]

    import requests

    params: dict[str, Any] = dict(filter_params or {})
    params.setdefault("yearFrom", YEAR_FROM)
    params.setdefault("limit", 10000)
    params.setdefault("coo_all", "true")
    params.setdefault("coa_all", "true")

    items: list[dict] = []
    page = 1
    while True:
        p = dict(params)
        p["page"] = page
        resp = requests.get(f"{UNHCR_BASE}/{endpoint}/", timeout=120, params=p)
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, list):
            batch, total_pages = body, 1
        else:
            batch = body.get("items", [])
            total_pages = int(body.get("maxPages") or body.get("totalPages") or 1)
        items.extend(batch)
        if page >= total_pages or not batch:
            break
        page += 1

    base.logger.info(f"UNHCR {endpoint}: {len(items)} records over {page} page(s)")
    _raw_cache[cache_key] = items
    return items


# ---------------------------------------------------------------------------
# World Bank population helper (for per_wb_pop_pct derived indicators)
# ---------------------------------------------------------------------------

_wb_pop_cache: dict[str, pd.DataFrame] | None = None


def fetch_wb_population_all() -> pd.DataFrame:
    """Fetch WB SP.POP.TOTL for all countries.  Returns DataFrame[iso3, year, population].

    Uses the WB bulk endpoint (all countries in one call).  Cached after first call.
    """
    global _wb_pop_cache
    if _wb_pop_cache is not None:
        return _wb_pop_cache

    import requests

    url = f"{WB_BASE}/country/all/indicator/SP.POP.TOTL"
    params = {"format": "json", "per_page": 20000, "date": f"{YEAR_FROM}:2030"}
    resp = requests.get(url, timeout=180, params=params)
    resp.raise_for_status()
    body = resp.json()

    # WB API returns [metadata_dict, [data_items]]
    if not isinstance(body, list) or len(body) < 2:
        base.logger.warning("WB SP.POP.TOTL: unexpected response shape")
        _wb_pop_cache = pd.DataFrame(columns=["iso3", "year", "population"])
        return _wb_pop_cache

    items = body[1] or []
    rows = []
    for it in items:
        iso = (it.get("countryiso3code") or "").strip().upper()
        if not iso or len(iso) != 3:
            continue
        date_raw = it.get("date")
        val = it.get("value")
        if date_raw is None or val is None:
            continue
        try:
            rows.append({"iso3": iso, "year": int(date_raw), "population": float(val)})
        except (ValueError, TypeError):
            continue

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["iso3", "year", "population"])
    base.logger.info(f"WB SP.POP.TOTL: {len(df)} country-year rows")
    _wb_pop_cache = df
    return _wb_pop_cache


# ---------------------------------------------------------------------------
# Pure transform helpers
# ---------------------------------------------------------------------------


def _safe_float(raw: Any) -> float:
    """Convert a raw API value (string/int/float/blank/'-') to float, 0.0 if unparseable."""
    if raw in (None, "", "-", "N/A", "n/a"):
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def parse_unhcr_records(
    records: list[dict],
    value_field: str | list[str],
    country_field: str,
    iso3_map: dict[str, str],
    *,
    transform: str = "sum",
) -> pd.DataFrame:
    """PURE: flat UNHCR JSON records -> DataFrame[country, year, value].

    Handles the following transforms:
        sum        : sum a single value_field by (country, year)
        sum_fields : sum multiple value_fields (list) by (country, year)
        ratio_pct  : value_field must be [numerator_col, denominator_col];
                     returns sum(num)/sum(den)*100 per group (skips den=0)

    Returns DataFrame[country, year, value] with str/int/float types.
    """
    rows: list[dict] = []
    for rec in records:
        iso = str(rec.get(country_field) or "").strip().upper()
        name = iso3_map.get(iso)
        if not name:
            continue
        year = rec.get("year")
        if year in (None, ""):
            continue
        try:
            yr = int(year)
        except (TypeError, ValueError):
            continue

        if transform == "sum_fields":
            fields = value_field if isinstance(value_field, list) else [value_field]
            val = sum(_safe_float(rec.get(f)) for f in fields)
            rows.append({"country": name, "year": yr, "value": val})

        elif transform == "ratio_pct":
            # value_field = [numerator_col, denominator_col]
            num_col, den_col = value_field[0], value_field[1]
            num = _safe_float(rec.get(num_col))
            den = _safe_float(rec.get(den_col))
            # Accumulate raw numerator and denominator; ratio computed after grouping.
            rows.append({"country": name, "year": yr, "_num": num, "_den": den})

        else:  # "sum"
            field = value_field if isinstance(value_field, str) else value_field[0]
            val = _safe_float(rec.get(field))
            rows.append({"country": name, "year": yr, "value": val})

    if not rows:
        return pd.DataFrame(columns=["country", "year", "value"])

    df = pd.DataFrame(rows)

    if transform == "ratio_pct":
        g = df.groupby(["country", "year"], as_index=False)[["_num", "_den"]].sum()
        mask = g["_den"] > 0
        g = g[mask].copy()
        if g.empty:
            return pd.DataFrame(columns=["country", "year", "value"])
        g["value"] = g["_num"] / g["_den"] * 100.0
        return g[["country", "year", "value"]].reset_index(drop=True)

    return df.groupby(["country", "year"], as_index=False)["value"].sum().reset_index(drop=True)


def apply_annual_change_rate(df: pd.DataFrame) -> pd.DataFrame:
    """PURE: given a sum-aggregated DataFrame[country, year, value], return
    year-on-year % change: (value_t - value_{t-1}) / value_{t-1} * 100.

    Zero or missing prior-year value -> NaN (dropped by to_canonical_frame).
    """
    df = df.sort_values(["country", "year"]).copy()
    df["_prev"] = df.groupby("country")["value"].shift(1)
    mask = df["_prev"].notna() & (df["_prev"] != 0)
    result = df[mask].copy()
    result["value"] = (result["value"] - result["_prev"]) / result["_prev"].abs() * 100.0
    return result[["country", "year", "value"]].reset_index(drop=True)


def apply_wb_pop_ratio(
    df_numerator: pd.DataFrame,
    wb_pop: pd.DataFrame,
    iso3_map: dict[str, str],
) -> pd.DataFrame:
    """PURE: divide numerator (country, year, value) by WB population, return *.

    wb_pop has columns [iso3, year, population] with canonical names resolved via
    iso3_map -> we join on canonical country name.
    """
    # Build a (canonical country, year, population) frame from WB data.
    pop = wb_pop.copy()
    pop["country"] = pop["iso3"].map(iso3_map)
    pop = pop.dropna(subset=["country"])
    pop = pop[pop["population"] > 0][["country", "year", "population"]]

    merged = df_numerator.merge(pop, on=["country", "year"], how="inner")
    if merged.empty:
        return pd.DataFrame(columns=["country", "year", "value"])

    merged["value"] = merged["value"] / merged["population"] * 100.0
    return merged[["country", "year", "value"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# fetch_one — dispatched by the harness for each indicator spec
# ---------------------------------------------------------------------------


def fetch_one(spec: dict) -> pd.DataFrame | None:
    """Resolve the indicator code from spec, load config, fetch + transform."""
    iid = spec["id_string"]
    if iid not in SPECS:
        raise ValueError(f"unknown UNHCR indicator {iid!r}")

    cfg = SPECS[iid]
    iso3_map = base.load_iso3_country_map()
    transform = cfg.get("transform", "sum")
    filter_params = cfg.get("filter_params") or {}

    # --- cross-endpoint ratio (UNHCR_ASY_BACKLOG_YEARS) ---------------------
    if transform == "cross_endpoint_ratio":
        ep_list = cfg["endpoint"]  # list of two endpoints
        vf_list = cfg["value_field"]  # [numerator_field, denominator_field]
        ep_num, ep_den = ep_list[0], ep_list[1]
        vf_num, vf_den = vf_list[0], vf_list[1]
        country_field = cfg["country_field"]

        raw_num = fetch_unhcr_raw(ep_num, filter_params)
        raw_den = fetch_unhcr_raw(ep_den, filter_params)

        df_num = parse_unhcr_records(raw_num, vf_num, country_field, iso3_map, transform="sum")
        df_den = parse_unhcr_records(raw_den, vf_den, country_field, iso3_map, transform="sum")

        if df_num.empty or df_den.empty:
            base.logger.warning(f"{iid}: one of the two endpoints returned no rows")
            return None

        merged = df_num.merge(
            df_den.rename(columns={"value": "_den"}),
            on=["country", "year"],
            how="inner",
        )
        mask = merged["_den"] > 0
        merged = merged[mask].copy()
        if merged.empty:
            return None
        merged["value"] = merged["value"] / merged["_den"]
        return merged[["country", "year", "value"]].reset_index(drop=True)

    # --- per-WB-population ratio (UNHCR_REF_RATIO_POP, UNHCR_IDP_RATIO_POP) --
    if transform == "per_wb_pop_pct":
        endpoint = cfg["endpoint"]
        value_field = cfg["value_field"]
        country_field = cfg["country_field"]

        raw = fetch_unhcr_raw(endpoint, filter_params)
        df_base = parse_unhcr_records(raw, value_field, country_field, iso3_map, transform="sum")
        if df_base.empty:
            base.logger.warning(f"{iid}: UNHCR base series empty")
            return None

        wb_pop = fetch_wb_population_all()
        df_result = apply_wb_pop_ratio(df_base, wb_pop, iso3_map)
        if df_result.empty:
            base.logger.warning(f"{iid}: no overlap between UNHCR and WB population data")
            return None
        return df_result

    # --- annual change rate (UNHCR_IDP_CHANGE_RATE) -------------------------
    if transform == "annual_change_rate":
        endpoint = cfg["endpoint"]
        value_field = cfg["value_field"]
        country_field = cfg["country_field"]

        raw = fetch_unhcr_raw(endpoint, filter_params)
        df_base = parse_unhcr_records(raw, value_field, country_field, iso3_map, transform="sum")
        if df_base.empty:
            return None
        return apply_annual_change_rate(df_base)

    # --- all other transforms handled by parse_unhcr_records ----------------
    endpoint = cfg["endpoint"]
    if isinstance(endpoint, list):
        raise ValueError(f"{iid}: multi-endpoint requires transform='cross_endpoint_ratio'")

    value_field = cfg["value_field"]
    country_field = cfg["country_field"]

    raw = fetch_unhcr_raw(endpoint, filter_params)
    df = parse_unhcr_records(raw, value_field, country_field, iso3_map, transform=transform)

    if df.empty:
        base.logger.warning(f"{iid}: no rows parsed")
        return None
    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    base.run_fetcher("UNHCR", fetch_one)
