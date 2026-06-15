"""OWID spec-driven CSV fetcher (enrichment stage 2).

One Fargate task handles OW-xx / OWID_* indicators sourced from OWID's
publicly hosted grapher CSVs (ourworldindata.org/grapher/<slug>.csv) or
GitHub-raw CSVs.  All are CC BY 4.0, no auth required.

The dispatcher sends INDICATORS_JSON with relevant indicator IDs; the base
harness iterates them.  Each indicator downloads its own small CSV and is
parsed generically using the baked ``specs.json`` configuration.

SPEC-DRIVEN DESIGN
------------------
``src/specs.json`` is the single source of truth for all OWID indicators.
Future indicators = add an entry to specs.json + rebuild the Docker image.
The fetcher loads specs.json at import time (keyed by ``code``), then for
each indicator dispatched:

  1. Look up the spec by indicator code.
  2. Download the CSV from ``endpoint_or_dataset``.
  3. If ``is_derived=true``, compute the derived value from the raw columns
     per the ``derivation`` string.
  4. Otherwise, extract ``value_field`` directly.
  5. Drop continental/regional aggregates (empty code or OWID_ prefix).
  6. Map ISO-3 codes -> canonical country names via the shared base.
  7. Aggregate per (country, year) and return.

SUPPORTED TRANSFORMS / DERIVATIONS
------------------------------------
  ages_15_24_share : OWID_POP_YOUNG — (Ages 15-24 / sum(all_age_cols)) * 100
                     All age columns present in the same CSV row.

INDICATORS WIRED
-----------------
  OW-01             Polity V democracy score (-10 to +10), static after 2018.
  OW-04             CO2 emissions annual growth rate (% YoY, GCP via OWID).
                    Falls back to computing from co2 level column if the
                    co2_growth_prct column is absent.
  OWID_REGIMETYPE   V-Dem RoW 4-category regime type (0-3 ordinal integer).
  OWID_AUTOCRATIZATION
                    V-Dem ERT binary flag: 1 = active autocratization episode.
  OWID_POP_YOUNG    Youth bulge share: % of total population aged 15-24.
                    (DERIVED from OWID population-by-age-group.csv)
  OWID_SLUM_SHARE   % urban population living in slums (UN-Habitat SDG 11.1.1).
  OWID_STATECAP     Hanson & Sigman (2021) composite state-capacity index.

COUNTRY-CODE COLUMNS
---------------------
Most OWID grapher CSVs use 'Code' (ISO alpha-3). The ERT dataset uses
'country_text_id' (ISO-3 uppercase). Both are handled via ``country_field``
in the spec.  Rows where the code is empty, 'nan', or starts with 'OWID_'
are continental/regional aggregates and are dropped before ISO-3 mapping.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

# Shared base is COPYed next to this script in the image (see Dockerfile).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")
import qgi_fetcher_base as base  # noqa: E402

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Load baked specs at import time
# ---------------------------------------------------------------------------

_SPECS_PATH = Path(__file__).resolve().parent / "specs.json"


def _load_specs() -> dict[str, dict]:
    """Load specs.json and key by code. Raises if the file is missing."""
    with open(_SPECS_PATH, encoding="utf-8") as fh:
        raw: list[dict] = json.load(fh)
    return {entry["code"]: entry for entry in raw if entry.get("fetchable", True)}


SPECS: dict[str, dict] = _load_specs()

# ---------------------------------------------------------------------------
# Age-group columns for OWID_POP_YOUNG derivation
# ---------------------------------------------------------------------------

_AGE_GROUP_COLS = ["Under-5s", "Ages 5-14", "Ages 15-24", "Ages 25-64", "Ages 65+"]


# ---------------------------------------------------------------------------
# Pure transform (unit-tested, no network / no AWS)
# ---------------------------------------------------------------------------


def _apply_derivation(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Apply the derivation for is_derived=true indicators.

    Currently supported derivation key: ``ages_15_24_share``.

    Parameters
    ----------
    df      : raw CSV DataFrame (all columns present).
    spec    : the spec dict for this indicator.

    Returns
    -------
    DataFrame with a ``_derived_value`` column added.
    Raises ValueError for unknown derivation strings.
    """
    derivation: str = spec.get("derivation") or ""

    if "ages_15_24_share" in derivation:
        # Compute youth share from absolute age-group counts in the same row.
        missing = [c for c in _AGE_GROUP_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"OWID_POP_YOUNG: missing age-group columns {missing}; available: {list(df.columns)}")
        total = sum(pd.to_numeric(df[col], errors="coerce").fillna(0.0) for col in _AGE_GROUP_COLS)
        youth = pd.to_numeric(df["Ages 15-24"], errors="coerce")
        # Guard against division by zero
        share = youth.where(total > 0).div(total.where(total > 0)) * 100.0
        df = df.copy()
        df["_derived_value"] = share
        return df

    raise ValueError(
        f"Unknown derivation string {derivation!r} for code {spec.get('code')}. Add a handler in _apply_derivation()."
    )


def parse_owid_records(
    raw_df: pd.DataFrame,
    value_col: str,
    iso3_map: dict[str, str],
    *,
    code_col: str = "Code",
    year_col: str = "Year",
    agg: str = "mean",
    fallback_level_col: str | None = None,
    derivation: str | None = None,
    spec: dict | None = None,
) -> pd.DataFrame:
    """PURE: OWID raw DataFrame -> DataFrame[country, year, value].

    Parameters
    ----------
    raw_df            : the raw CSV loaded into a DataFrame (all columns present).
    value_col         : name of the column to use as the indicator value.
    iso3_map          : {ISO3_UPPER: canonical name_1} from the shared base.
    code_col          : name of the ISO-3 column in raw_df (default 'Code').
    year_col          : name of the year column in raw_df (default 'Year').
    agg               : 'mean' or 'sum' for the per-(country,year) roll-up.
    fallback_level_col: if value_col is entirely missing or all-NaN AND this is
                        set, compute annual YoY % change from this column instead.
                        Used for OW-04 as a safety net.
    derivation        : derivation string from spec (e.g. 'ages_15_24_share:...').
                        If set, _apply_derivation() is called first and the result
                        column ``_derived_value`` is used as the value.
    spec              : full spec dict (passed to _apply_derivation when needed).

    Returns
    -------
    DataFrame[country, year, value]
        - country  : canonical name_1 string
        - year     : int
        - value    : float
    Rows whose ISO-3 code is empty or starts with 'OWID_' (aggregates/continents)
    are dropped before mapping.  Rows that don't resolve to a canonical name are
    also dropped.
    """
    df = raw_df.copy()

    # --- 1. drop aggregate / continent rows ---------------------------------
    code_series = df[code_col].astype(str).str.strip()
    mask_keep = code_series.ne("") & code_series.ne("nan") & ~code_series.str.startswith("OWID_")
    df = df[mask_keep].copy()
    if df.empty:
        return pd.DataFrame(columns=["country", "year", "value"])

    # --- 2. resolve ISO-3 -> canonical name ---------------------------------
    df["_iso"] = df[code_col].astype(str).str.strip().str.upper()
    df["_country"] = df["_iso"].map(iso3_map)
    df = df.dropna(subset=["_country"])
    if df.empty:
        return pd.DataFrame(columns=["country", "year", "value"])

    # --- 3. resolve value column: derivation / direct / fallback YoY --------
    if derivation and spec is not None:
        df = _apply_derivation(df, spec)
        effective_col = "_derived_value"
    elif value_col not in df.columns or df[value_col].isna().all():
        if fallback_level_col and fallback_level_col in df.columns:
            base.logger.warning(
                f"parse_owid_records: '{value_col}' missing/all-NaN; computing YoY % change from '{fallback_level_col}'"
            )
            df = df.sort_values(["_country", year_col])
            df["_level"] = pd.to_numeric(df[fallback_level_col], errors="coerce")
            df["_fallback_yoy"] = df.groupby("_country")["_level"].pct_change() * 100.0
            effective_col = "_fallback_yoy"
        else:
            base.logger.warning(f"parse_owid_records: '{value_col}' not found and no fallback")
            return pd.DataFrame(columns=["country", "year", "value"])
    else:
        effective_col = value_col

    # --- 4. coerce year + value, drop NaNs ----------------------------------
    df["_year"] = pd.to_numeric(df[year_col], errors="coerce")
    df["_value"] = pd.to_numeric(df[effective_col], errors="coerce")
    df = df.dropna(subset=["_year", "_value"])
    df["_year"] = df["_year"].astype(int)

    # --- 5. aggregate per (country, year) -----------------------------------
    grp = df.groupby(["_country", "_year"], as_index=False)["_value"]
    result = grp.mean() if agg == "mean" else grp.sum()
    result = result.rename(columns={"_country": "country", "_year": "year", "_value": "value"})
    return result[["country", "year", "value"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Network I/O (lazy import of requests)
# ---------------------------------------------------------------------------


def _fetch_csv(url: str) -> pd.DataFrame:
    """Download a CSV from a URL and return as a DataFrame. Lazy-imports requests."""
    import io
    import requests  # lazy — keeps the module importable without requests installed

    base.logger.info(f"OWID: downloading {url}")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    base.logger.info(f"OWID: {len(df)} rows x {len(df.columns)} cols")
    return df


# ---------------------------------------------------------------------------
# fetch_one (called by the harness for each spec)
# ---------------------------------------------------------------------------


def fetch_one(spec: dict) -> pd.DataFrame | None:
    """Fetch and parse a single OWID indicator.

    Parameters
    ----------
    spec : dict with at least ``id_string`` (the indicator code).
           All other parameters are resolved from specs.json.

    Returns
    -------
    DataFrame[country, year, value] or None if no rows parsed.
    """
    iid = spec["id_string"]
    if iid not in SPECS:
        raise ValueError(f"unknown OWID indicator {iid!r}; add it to src/specs.json to enable fetching")

    cfg = SPECS[iid]
    iso3_map = base.load_iso3_country_map()
    raw_df = _fetch_csv(cfg["endpoint_or_dataset"])

    df = parse_owid_records(
        raw_df=raw_df,
        value_col=cfg["value_field"],
        iso3_map=iso3_map,
        code_col=cfg["country_field"],
        year_col=cfg.get("year_field", "Year"),
        agg="mean",
        fallback_level_col=cfg.get("fallback_level_col"),
        derivation=cfg.get("derivation") if cfg.get("is_derived") else None,
        spec=cfg if cfg.get("is_derived") else None,
    )
    if df.empty:
        base.logger.warning(f"{iid}: no rows parsed from OWID source")
        return None
    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    base.run_fetcher("OWID", fetch_one)
