"""
Phase 2 — Empirical Bayes hyperprior estimation per (sector, L1) cell.

Inputs (all local / cached, no Athena $$):
  - qgi-data/reference/indicator-sectors.json (Miriam's 142-indicator -> 10-sector map)
  - qgi-data/events/taxonomy_hierarchy.json (8 L1 categories -> 71 L3 event_categories)
  - docs/specs/methodology/indicator-catalog-detailed.md (parse for catalog_code -> API_code)
  - indicator_map.csv (cached from S3: API_code -> numeric_id)
  - recipes_aggregated unnested rows (event_category x numeric_id x frequency x total_instances)
    -- pulled via Athena once at start, ~$0

Estimation:
  Type-II MLE on hierarchical Beta-Binomial likelihood per (sector, L1) cell.
  For each cell, indicators contribute (k_d, n_d) pairs where:
    k_d = round(frequency_d * total_instances_d) = recipes_with_indicator
    n_d = total_instances_d = n_recipes in category

  Likelihood per cell:
    L(alpha, beta | {(k_d, n_d)}) = prod_d BetaBinomial(k_d | n_d, alpha, beta)

  Optimize log L w.r.t. (log alpha, log beta) via scipy.optimize, then transform back.

Output:
  qgi-data/reference/eb-hyperpriors.json with structure:
    {
      "schema_version": 1,
      "generated": "<iso>",
      "cells": {
        "<sector>__<L1>": {
          "alpha": float, "beta": float,
          "n_observations": int,    # number of (k_d, n_d) pairs in cell
          "n_indicators": int,
          "mean": alpha/(alpha+beta),
          "concentration": alpha+beta,
          "fit_converged": bool,
          "fit_method": "Type-II MLE (scipy L-BFGS-B)",
          "loglik_at_fit": float
        }
      }
    }
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import boto3
import numpy as np
from scipy.optimize import minimize
from scipy.stats import betabinom


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent.parent
SECTORS_JSON = ROOT / "qgi-data" / "reference" / "indicator-sectors.json"
TAXONOMY_JSON = ROOT / "qgi-data" / "events" / "taxonomy_hierarchy.json"
CATALOG_MD = ROOT / "docs-specs" / "methodology" / "indicator-catalog-detailed.md"
OUTPUT_JSON = ROOT / "qgi-data" / "reference" / "eb-hyperpriors.json"

# DEVELOPER-LOCAL: these paths point to ephemeral cache files set up by
# the developer running the script (cred refresh + S3 download of the
# indicator_map). Override via env vars QGI_INDICATOR_MAP_CSV and
# QGI_STAGING_CREDS_FILE for CI / other-developer runs. Defaults assume
# the QGI dev-machine layout under %LOCALAPPDATA%/qgi/.
import os as _os
_dev_cache = Path(_os.environ.get("LOCALAPPDATA", r"C:/Users/Amin/AppData/Local")) / "Temp" / "qgi"
INDICATOR_MAP_CSV = Path(_os.environ.get("QGI_INDICATOR_MAP_CSV", str(_dev_cache / "indicator_map.csv")))
CREDS_FILE = Path(_os.environ.get("QGI_STAGING_CREDS_FILE", str(_dev_cache / "staging_creds.json")))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_sectors() -> dict[str, str]:
    """catalog_code (WB-01) -> sector_code (CONFLICT)."""
    d = json.loads(SECTORS_JSON.read_text(encoding="utf-8"))
    return {k: v["sector"] for k, v in d["indicator_to_sector"].items()}


def load_event_l1_map() -> dict[str, str]:
    """L3 event_category -> L1 letter (A-H)."""
    d = json.loads(TAXONOMY_JSON.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for l1_entry in d["layer1"]:
        l1_id = l1_entry["id"]
        for l2 in l1_entry.get("layer2", []):
            for l3 in l2.get("layer3", []):
                out[l3] = l1_id
    return out


def load_l1_labels() -> dict[str, str]:
    """L1 letter -> human-readable label (e.g. A -> Political Power & Regime)."""
    d = json.loads(TAXONOMY_JSON.read_text(encoding="utf-8"))
    return {e["id"]: e["label"] for e in d["layer1"]}


def parse_catalog_api_to_catalog_code() -> dict[str, str]:
    """Parse indicator-catalog-detailed.md to build {api_code -> catalog_code}.

    Catalog rows look like:
      | WB-01 | VC.BTL.DETH | Battle-related deaths ... | ... |
      | VD-01 | v2x_polyarchy | Electoral Democracy ... | ... |

    Some rows have no API code in column 2 (UCDP, GDELT, etc.) — those use
    a Name column directly. The heuristic below captures only the rows with
    real API codes. Indicators with name-only column 2 won't reach the EB
    cells anyway because they are not in indicator_map.csv (the pipeline's
    numeric_id ↔ api_code bridge), so silently skipping them here is fine.
    """
    md = CATALOG_MD.read_text(encoding="utf-8")
    api_to_catalog: dict[str, str] = {}
    pattern = re.compile(r"^\|\s*([A-Z]{2}-[A-Z0-9]+)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
    for m in pattern.finditer(md):
        catalog_code = m.group(1).strip()
        col2 = m.group(2).strip()
        if col2 and not col2.startswith("Battle") and len(col2) < 60:
            api_to_catalog[col2] = catalog_code
    return api_to_catalog


def load_numeric_to_api() -> dict[int, str]:
    """numeric_id -> API code, from indicator_map.csv."""
    out: dict[int, str] = {}
    with INDICATOR_MAP_CSV.open(encoding="utf-8") as f:
        next(f)  # skip header: id_string,numeric_id
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != 2:
                continue
            api_code, num_id = parts[0].strip(), parts[1].strip()
            try:
                out[int(num_id)] = api_code
            except ValueError:
                continue
    return out


# ---------------------------------------------------------------------------
# Athena: pull (event_category, numeric_id, k_d, n_d) rows
# ---------------------------------------------------------------------------

def pull_observations() -> list[tuple[str, int, int, int]]:
    """Return [(event_category, numeric_id, k_d, n_d), ...]."""
    creds = json.loads(CREDS_FILE.read_text())
    sess = boto3.Session(
        aws_access_key_id=creds["ak"],
        aws_secret_access_key=creds["sk"],
        aws_session_token=creds["st"],
        region_name="eu-central-1",
    )
    athena = sess.client("athena")
    sql = """
    SELECT
        event_category,
        cast(ifp.indicator_id as integer) AS numeric_id,
        ifp.frequency,
        total_instances
    FROM qgi_data.recipes_aggregated
    CROSS JOIN UNNEST(indicator_fingerprint) AS t(ifp)
    """
    print("  [athena] submitting unnest query")
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": "qgi_data"},
        WorkGroup="QGI-Lambda-Workgroup",
    )["QueryExecutionId"]

    import time
    while True:
        time.sleep(2.0)
        s = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        if s["Status"]["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
    if s["Status"]["State"] != "SUCCEEDED":
        raise RuntimeError(f"athena query failed: {s['Status'].get('StateChangeReason')}")
    print(f"  [athena] scan: {s['Statistics']['DataScannedInBytes']:,} bytes")

    # Paginate results
    rows = []
    paginator = athena.get_paginator("get_query_results")
    is_first = True
    for page in paginator.paginate(QueryExecutionId=qid):
        for r in page["ResultSet"]["Rows"]:
            if is_first:
                is_first = False
                continue  # skip header row
            cells = [c.get("VarCharValue") for c in r["Data"]]
            event_cat, num_id_s, freq_s, total_s = cells
            if not all([event_cat, num_id_s, freq_s, total_s]):
                continue
            num_id = int(num_id_s)
            freq = float(freq_s)
            n_d = int(total_s)
            k_d = int(round(freq * n_d))
            # Clamp to valid binomial range
            if k_d < 0:
                k_d = 0
            if k_d > n_d:
                k_d = n_d
            rows.append((event_cat, num_id, k_d, n_d))
    return rows


# ---------------------------------------------------------------------------
# Type-II MLE on Beta-Binomial
# ---------------------------------------------------------------------------

def neg_loglik(log_params: np.ndarray, k_arr: np.ndarray, n_arr: np.ndarray) -> float:
    """Negative log-likelihood for Beta-Binomial in log-parameterization.

    log_params = (log_alpha, log_beta). Constraints alpha, beta > 0
    are enforced by the log transform.
    """
    log_a, log_b = log_params
    # Cap exponents to avoid overflow on stray steps
    log_a = np.clip(log_a, -20, 20)
    log_b = np.clip(log_b, -20, 20)
    a = np.exp(log_a)
    b = np.exp(log_b)
    ll = betabinom.logpmf(k_arr, n_arr, a, b).sum()
    if not np.isfinite(ll):
        return 1e10
    return -ll


@dataclass
class FitResult:
    alpha: float
    beta: float
    n_observations: int
    n_indicators: int
    mean: float
    concentration: float
    converged: bool
    loglik: float
    method: str
    degenerate: bool       # True if the fit is unreliable (insufficient data)
    degenerate_reason: str  # explanation; empty when degenerate=False


# Thresholds for flagging a fit as degenerate. These are NOT optimizer
# parameters — the fit still runs and produces (alpha, beta) values, but
# the result is unreliable for Phase 3 shrinkage. Phase 3 should apply
# the (alpha=1, beta=1) uniform fallback when degenerate=True.
#
# Rationale (QA review 2026-05-03 caught REPRESSION__C with n_obs=2,
# concentration=312,736 — optimizer converged on a flat ridge, no
# information, would shrink any indicator in that cell to a near-point-mass):
#
# - DEGENERATE_MIN_OBS = 5: cannot reliably estimate 2 parameters
#   (alpha, beta) from fewer than ~5 Beta-Binomial observations.
# - DEGENERATE_MAX_CONCENTRATION = 5000: empirical threshold from the
#   distribution of legitimate fits; concentration above this is
#   typically a ridge-convergence artifact.
DEGENERATE_MIN_OBS = 5
DEGENERATE_MAX_CONCENTRATION = 5000.0


def fit_cell(observations: list[tuple[int, int]], indicator_ids: set[int]) -> FitResult:
    """observations = [(k_d, n_d), ...] within one (sector x L1) cell."""
    if not observations:
        return FitResult(np.nan, np.nan, 0, 0, np.nan, np.nan, False, np.nan,
                          "skipped (no data)", True, "no observations in cell")
    k_arr = np.array([k for k, n in observations], dtype=np.int64)
    n_arr = np.array([n for k, n in observations], dtype=np.int64)

    # Method-of-moments init for stable optimization
    p_hat = k_arr / np.maximum(n_arr, 1)
    mu = float(np.mean(p_hat))
    var = float(np.var(p_hat))
    # Avoid degenerate: clamp mu and var
    mu = max(min(mu, 0.999), 0.001)
    if var < 1e-8:
        # Almost no spread => high concentration. Start with concentration=20.
        nu_init = 20.0
    else:
        nu_init = max(mu * (1 - mu) / var - 1.0, 1.0)
    a_init = mu * nu_init
    b_init = (1 - mu) * nu_init
    x0 = np.array([np.log(max(a_init, 0.1)), np.log(max(b_init, 0.1))])

    res = minimize(
        neg_loglik,
        x0,
        args=(k_arr, n_arr),
        method="L-BFGS-B",
        bounds=[(-15, 15), (-15, 15)],
        options={"maxiter": 500, "ftol": 1e-9},
    )
    method_used = "L-BFGS-B"
    if not res.success:
        # Retry with Nelder-Mead from a NEUTRAL start point (Beta(1, 1) =
        # uniform prior, log(1, 1) = (0, 0)). Reusing the moment-of-methods
        # x0 here would re-seed the second optimizer at the same flat-region
        # init that defeated L-BFGS-B; a different starting point is what
        # makes the fallback meaningful. QA review caught this 2026-05-03.
        x0_nm = np.array([0.0, 0.0])
        res_nm = minimize(neg_loglik, x0_nm, args=(k_arr, n_arr), method="Nelder-Mead",
                          options={"maxiter": 2000, "xatol": 1e-6})
        if res_nm.success or res_nm.fun < res.fun:
            res = res_nm
            method_used = "Nelder-Mead (fallback)"

    a = float(np.exp(np.clip(res.x[0], -20, 20)))
    b = float(np.exp(np.clip(res.x[1], -20, 20)))
    n_obs = len(observations)
    concentration = a + b
    # Flag degenerate fits — see DEGENERATE_* threshold definitions above.
    degenerate = False
    degenerate_reason = ""
    if n_obs < DEGENERATE_MIN_OBS:
        degenerate = True
        degenerate_reason = f"n_observations={n_obs} < {DEGENERATE_MIN_OBS} floor"
    elif concentration > DEGENERATE_MAX_CONCENTRATION:
        degenerate = True
        degenerate_reason = (
            f"concentration={concentration:.0f} > {DEGENERATE_MAX_CONCENTRATION:.0f} "
            f"(likely ridge-convergence on flat likelihood)"
        )
    return FitResult(
        alpha=a,
        beta=b,
        n_observations=n_obs,
        n_indicators=len(indicator_ids),
        mean=a / (a + b),
        concentration=concentration,
        converged=bool(res.success),
        loglik=-float(res.fun),
        method=f"{method_used} (success={res.success})",
        degenerate=degenerate,
        degenerate_reason=degenerate_reason,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("[1] Loading static maps")
    sectors = load_sectors()  # WB-01 -> CONFLICT
    print(f"    sectors: {len(sectors)} indicators across {len(set(sectors.values()))} sectors")

    event_l1 = load_event_l1_map()  # event_category -> L1 letter
    l1_labels = load_l1_labels()
    print(f"    event_l1: {len(event_l1)} L3 categories -> {len(set(event_l1.values()))} L1 letters")

    api_to_catalog = parse_catalog_api_to_catalog_code()
    print(f"    catalog: {len(api_to_catalog)} api_code -> catalog_code mappings parsed")

    num_to_api = load_numeric_to_api()
    print(f"    numeric_map: {len(num_to_api)} numeric_id -> api_code mappings")

    # Build numeric_id -> sector via chain
    num_to_sector: dict[int, str] = {}
    unmapped_apis: set[str] = set()
    unmapped_catalog: set[str] = set()
    for num_id, api_code in num_to_api.items():
        cat_code = api_to_catalog.get(api_code)
        if cat_code is None:
            unmapped_apis.add(api_code)
            continue
        sector = sectors.get(cat_code)
        if sector is None:
            unmapped_catalog.add(cat_code)
            continue
        num_to_sector[num_id] = sector

    print(f"    chain coverage: {len(num_to_sector)}/{len(num_to_api)} numeric_ids mapped to sector")
    if unmapped_apis:
        print(f"    [WARN] {len(unmapped_apis)} api_codes not in catalog (sample: {sorted(unmapped_apis)[:5]})")
    if unmapped_catalog:
        print(f"    [WARN] {len(unmapped_catalog)} catalog_codes not in sectors map (sample: {sorted(unmapped_catalog)[:5]})")

    print("\n[2] Pulling observations from Athena (recipes_aggregated UNNEST)")
    obs = pull_observations()
    print(f"    pulled {len(obs)} (event_category, numeric_id, k_d, n_d) rows")

    print("\n[3] Bucketing observations into (sector, L1) cells")
    cells: dict[tuple[str, str], list[tuple[int, int]]] = {}
    cell_indicators: dict[tuple[str, str], set[int]] = {}
    skipped_no_sector = 0
    skipped_no_l1 = 0
    for event_cat, num_id, k_d, n_d in obs:
        sector = num_to_sector.get(num_id)
        if sector is None:
            skipped_no_sector += 1
            continue
        l1 = event_l1.get(event_cat)
        if l1 is None:
            skipped_no_l1 += 1
            continue
        key = (sector, l1)
        cells.setdefault(key, []).append((k_d, n_d))
        cell_indicators.setdefault(key, set()).add(num_id)
    print(f"    cells with data: {len(cells)}")
    print(f"    skipped (no sector): {skipped_no_sector}")
    print(f"    skipped (no L1):     {skipped_no_l1}")

    # Loud warning when most observations got skipped — Phase 3 priors are
    # then based on a small data slice, with the rest of the cells defaulting
    # to flat Beta(1,1). This is correct per methodology, but operators
    # consuming the EB output should know the coverage is partial.
    skip_frac = (skipped_no_sector + skipped_no_l1) / max(len(obs), 1)
    if skip_frac > 0.60:
        used_frac = 1.0 - skip_frac
        print(
            f"\n  [WARN] {skip_frac:.1%} of observations skipped due to missing sector "
            f"or L1 mapping. Phase 3 EB priors are based on {used_frac:.1%} of available "
            f"data; the remaining cells fall back to uniform Beta(1, 1) downstream. "
            f"See companion ticket on filtering legacy non-catalog indicators.",
            file=sys.stderr,
        )

    print("\n[4] Fitting Beta(alpha, beta) per cell via Type-II MLE")
    results: dict[str, dict] = {}
    cells_below_floor: list[str] = []
    for (sector, l1), observations in sorted(cells.items()):
        ids = cell_indicators[(sector, l1)]
        fit = fit_cell(observations, ids)
        cell_key = f"{sector}__{l1}"
        cell_record = {
            "sector": sector,
            "L1": l1,
            "L1_label": l1_labels.get(l1, ""),
            "alpha": fit.alpha,
            "beta": fit.beta,
            "n_observations": fit.n_observations,
            "n_indicators": fit.n_indicators,
            "mean": fit.mean,
            "concentration": fit.concentration,
            "converged": fit.converged,
            "loglik": fit.loglik,
            "method": fit.method,
            "degenerate": fit.degenerate,
            "degenerate_reason": fit.degenerate_reason,
        }
        if fit.degenerate:
            # Phase 3 should fall back to Beta(1, 1) uniform when degenerate.
            cell_record["fallback_alpha"] = 1.0
            cell_record["fallback_beta"] = 1.0
            cells_below_floor.append(cell_key)
        results[cell_key] = cell_record

    # Print summary table
    print("\n    Cell summary (sorted by sector, L1):")
    print(f"    {'cell':25s}  {'n_obs':>5s}  {'n_ind':>5s}  {'mean':>7s}  {'conc':>9s}  {'alpha':>9s}  {'beta':>9s}  conv")
    for cell_key, r in sorted(results.items()):
        print(f"    {cell_key:25s}  {r['n_observations']:>5d}  {r['n_indicators']:>5d}  "
              f"{r['mean']:>7.4f}  {r['concentration']:>9.2f}  {r['alpha']:>9.3f}  {r['beta']:>9.3f}  "
              f"{'YES' if r['converged'] else 'no '}")

    # Save
    # Sectors that have NO cells at all in the output (because no
    # indicator from those sectors appeared in the data). Phase 3
    # consumer should treat these as uniform Beta(1, 1).
    fit_sectors = set(c["sector"] for c in results.values())
    all_sectors = set(s for s in sectors.values())
    sectors_not_fit = sorted(all_sectors - fit_sectors)

    print(f"\n[5] Writing {OUTPUT_JSON}")
    output = {
        "schema_version": 2,  # bumped 2026-05-03: added degenerate flag, fallback policy, sectors_not_fit
        "generated": datetime.now(timezone.utc).isoformat(),
        "source_data": {
            "recipes_aggregated_pipeline_version": "V2.0-dev",
            "recipes_aggregated_baked": "2026-05-03T00:33:35Z (Greenlight 5)",
            "sector_taxonomy_version": json.loads(SECTORS_JSON.read_text())["schema_version"],
            "n_indicators_total": len(sectors),
            "n_indicators_in_data": len(set(num_to_sector.values())),
            "n_observations_total": len(obs),
            "n_observations_used": sum(len(v) for v in cells.values()),
        },
        "estimation_method": "Type-II MLE on hierarchical Beta-Binomial; L-BFGS-B in log-(alpha,beta) parameterization with method-of-moments init; Nelder-Mead fallback from Beta(1,1) start if L-BFGS-B fails",
        "fallback_policy": {
            "rule": "When `degenerate=true` for a cell, OR when a (sector, L1) cell is absent from `cells`, Phase 3 must use Beta(alpha=1, beta=1) (uniform) instead of the fitted alpha/beta. The fitted values for degenerate cells are kept for diagnostic purposes only.",
            "degenerate_thresholds": {
                "min_n_observations": DEGENERATE_MIN_OBS,
                "max_concentration": DEGENERATE_MAX_CONCENTRATION,
            },
        },
        "sectors_not_fit": sectors_not_fit,
        "cells_below_floor": cells_below_floor,
        "cells": results,
    }
    OUTPUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")
    n_degen = sum(1 for c in results.values() if c["degenerate"])
    print(f"    wrote {len(results)} cells; {n_degen} flagged degenerate; "
          f"{len(sectors_not_fit)} sectors not fit at all (Phase 3 will use Beta(1,1) for those)")


if __name__ == "__main__":
    main()
