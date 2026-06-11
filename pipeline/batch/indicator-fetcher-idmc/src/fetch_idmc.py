"""IDMC (Internal Displacement Monitoring Centre) fetcher (enrichment stage 2).

One Fargate task per ID-xx indicator (dispatcher sends INDICATOR_ID). Pulls the
IDMC GIDD REST API (helix-tools-api.idmcdb.org, requires API key), aggregates to
(canonical country, year, value), and hands the frame to the shared base which
writes parquet-completed + DDB + tracker + counter.

Country codes in the API are ISO alpha-3 -> mapped to canonical name_1 via the
shared country-m49-map (iso_alpha3 column).

Indicators wired:
  ID-01  New internal displacements by conflict (annual flow)
  ID-02  New internal displacements by disaster (annual flow)
  ID-03  IDP stock by conflict (end-of-year)

API contract (confirmed 2026-06-25 via live query):
  Base: https://helix-tools-api.idmcdb.org/external-api/gidd/
  Endpoint: public-figure-analyses/
  Auth: ?client_id=<IDMC_API_KEY>  (read from env; injected from SSM at runtime)
  Key fields in response items:
    iso3               str   ISO alpha-3
    year               int
    figure_cause_name  str   "Conflict" | "Disaster"
    figure_category_name str "Internal Displacements" | "IDPs"
    figures            int   exact count

Filtering strategy: fetch the full dataset in one paginated pass (total ~1,300
records) then filter in the pure parse function per indicator spec. This avoids
repeated API round-trips for each indicator while keeping network + parse logic
clearly separated.

NOTE: run ONE live smoke per indicator on AWS before the production fetch to
confirm field names are stable across API releases.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

# Shared base is COPYed next to this script in the image (see Dockerfile).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/app")
import qgi_fetcher_base as base  # noqa: E402

IDMC_BASE = "https://helix-tools-api.idmcdb.org/external-api/gidd"
PAGE_LIMIT = 500  # max records per page; keeps round-trips low

# id_string -> filter spec: which (cause_name, category_name) pair to keep
SPECS: dict[str, dict[str, str]] = {
    "ID-01": {
        "figure_cause_name": "Conflict",
        "figure_category_name": "Internal Displacements",
    },
    "ID-02": {
        "figure_cause_name": "Disaster",
        "figure_category_name": "Internal Displacements",
    },
    "ID-03": {
        "figure_cause_name": "Conflict",
        "figure_category_name": "IDPs",
    },
}


def parse_idmc_records(
    records: list[dict],
    cfg: dict[str, str],
    iso3_map: dict[str, str],
) -> pd.DataFrame:
    """PURE: IDMC public-figure-analyses records -> DataFrame[country, year, value].

    Keeps only rows matching cfg["figure_cause_name"] and
    cfg["figure_category_name"], maps ISO3 to canonical name_1, and sums any
    duplicate (country, year) pairs (should not occur in practice for stock/flow
    figures, but guarded for safety).

    Parameters
    ----------
    records:
        Flat list of items from all pages of the public-figure-analyses endpoint.
    cfg:
        Indicator spec dict with keys ``figure_cause_name`` and
        ``figure_category_name`` (values from SPECS above).
    iso3_map:
        {ISO_ALPHA3_UPPER: canonical_name_1} from base.load_iso3_country_map().

    Returns
    -------
    DataFrame with columns [country, year, value].  Empty frame with the same
    columns if nothing resolves.
    """
    cause_filter = cfg["figure_cause_name"]
    cat_filter = cfg["figure_category_name"]
    rows = []
    for rec in records:
        # cause + category filter
        if rec.get("figure_cause_name") != cause_filter:
            continue
        if rec.get("figure_category_name") != cat_filter:
            continue

        iso = str(rec.get("iso3") or "").strip().upper()
        name = iso3_map.get(iso)
        if not name:
            continue  # regional aggregates or unmapped codes -> drop

        year = rec.get("year")
        if year in (None, ""):
            continue

        raw = rec.get("figures")
        try:
            val = float(raw) if raw not in (None, "") else 0.0
        except (TypeError, ValueError):
            continue

        rows.append({"country": name, "year": int(year), "value": val})

    if not rows:
        return pd.DataFrame(columns=["country", "year", "value"])

    # sum any accidental duplicates; in practice IDMC publishes one figure per
    # (iso3, year, cause, category) but guard defensively.
    return pd.DataFrame(rows).groupby(["country", "year"], as_index=False)["value"].sum()


def fetch_idmc_raw() -> list[dict]:
    """Paginated GET of IDMC public-figure-analyses. Returns the flat item list.

    Uses the IDMC_API_KEY env var (injected from SSM at runtime via the Batch
    job definition). Raises if the env var is absent so the task fails fast with
    a clear message rather than a 401.
    """
    import requests  # lazy import: keeps module importable under test w/o requests

    api_key = os.environ.get("IDMC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "IDMC_API_KEY environment variable is not set. Inject it from SSM via the Batch job definition secrets."
        )

    url = f"{IDMC_BASE}/public-figure-analyses/"
    items: list[dict] = []
    offset = 0

    while True:
        resp = requests.get(
            url,
            timeout=120,
            params={
                "client_id": api_key,
                "limit": PAGE_LIMIT,
                "offset": offset,
            },
        )
        resp.raise_for_status()
        body = resp.json()

        # API returns {"count": N, "next": ..., "results": [...]} (or a bare list).
        if isinstance(body, list):
            items.extend(body)
            break
        batch = body.get("results", [])
        items.extend(batch)
        if not batch or body.get("next") is None:
            break
        offset += len(batch)

    base.logger.info(
        f"IDMC public-figure-analyses: {len(items)} records fetched over {offset // PAGE_LIMIT + 1} page(s)"
    )
    return items


def fetch_one(spec: dict) -> pd.DataFrame:
    """Called once per indicator by run_fetcher harness.

    Fetches the full IDMC dataset (all pages, ~1,300 records) and filters to the
    subset matching this indicator's cause + category combination. Because all
    three ID-xx indicators share the same endpoint, the first call performs the
    network round-trip; subsequent indicators within the same task invocation
    share the cached result.
    """
    iid = spec["id_string"]
    if iid not in SPECS:
        raise ValueError(f"unknown IDMC indicator {iid!r}")

    cfg = SPECS[iid]
    # Cache the full dataset across the (up to 3) ID-xx indicators in one task.
    if not hasattr(fetch_one, "_raw_cache"):
        fetch_one._raw_cache = fetch_idmc_raw()
    return parse_idmc_records(fetch_one._raw_cache, cfg, base.load_iso3_country_map())


if __name__ == "__main__":
    base.run_fetcher("IDMC", fetch_one)
