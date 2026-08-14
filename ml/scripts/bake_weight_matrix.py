"""
Phase 3 — bake the (indicator x event_category) weight matrix using
the Phase 2 EB hyperpriors.

For each (event_category, indicator_id) cell in recipes_aggregated:

  weight = (k_d + alpha_cell) / (n_d + alpha_cell + beta_cell)

where (alpha_cell, beta_cell) is the EB hyperprior for the
(sector, L1) cell that this (indicator, event_category) maps into:

  - sector       <- indicator-sectors.json (Miriam's classification)
  - L1           <- taxonomy_hierarchy.json (event_category -> L1 letter)
  - cell prior   <- eb-hyperpriors.json (Phase 2 output)

Fallback policy (per qgi-data/reference/eb-hyperpriors.json fallback_policy):
  - If the cell is flagged degenerate, OR the cell is missing entirely
    (sector_not_fit), use the uniform Beta(1, 1) prior.
  - The fallback flag is recorded per-row so downstream consumers can
    treat fallback weights differently if desired.

Inputs (all local / cached, no Athena $$):
  - qgi-data/reference/indicator-sectors.json
  - qgi-data/events/taxonomy_hierarchy.json
  - docs/specs/methodology/indicator-catalog-detailed.md
  - indicator_map.csv (cached from S3)
  - recipes_aggregated UNNEST via Athena (~$0)
  - qgi-data/reference/eb-hyperpriors.json

Output:
  - qgi-data/reference/weight-matrix.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
import numpy as np

# Reuse loaders from estimate_eb_hyperpriors.py (sibling script). Avoids
# duplicating the catalog parser, sector loader, and Athena puller.
_SIBLING = Path(__file__).resolve().parent / "estimate_eb_hyperpriors.py"
_spec = importlib.util.spec_from_file_location("eb_hyperpriors", _SIBLING)
eb = importlib.util.module_from_spec(_spec)
sys.modules["eb_hyperpriors"] = eb
_spec.loader.exec_module(eb)


ROOT = Path(__file__).resolve().parent.parent.parent
EB_HYPERPRIORS_JSON = ROOT / "qgi-data" / "reference" / "eb-hyperpriors.json"
OUTPUT_JSON = ROOT / "qgi-data" / "reference" / "weight-matrix.json"

# Fallback prior: Beta(1, 1) is the uniform-mean-with-precision-2
# no-information default. Documented in eb-hyperpriors.json
# fallback_policy field.
FALLBACK_ALPHA = 1.0
FALLBACK_BETA = 1.0


def load_eb_priors() -> dict:
    """Load the Phase 2 EB hyperpriors JSON.

    Returns the dict including 'cells', 'sectors_not_fit', and
    'fallback_policy'.
    """
    return json.loads(EB_HYPERPRIORS_JSON.read_text(encoding="utf-8"))


def lookup_cell_prior(eb_data: dict, sector: str, l1: str) -> tuple[float, float, bool, str]:
    """Resolve (alpha, beta, used_fallback, reason) for a (sector, L1) cell.

    Decision tree (precedence top-to-bottom — checked in this order):
      1. Sector is in `sectors_not_fit`        -> FALLBACK_*, reason='sector_not_fit'
         (`sectors_not_fit` takes precedence over cell-level lookup, even if
         a cell key exists for the sector — the EB JSON's contract is that a
         sector in this list has no usable priors regardless of which L1 was
         partially populated.)
      2. Cell key absent entirely              -> FALLBACK_*, reason='cell_missing'
      3. Cell exists and `degenerate=True`     -> FALLBACK_*, reason='cell_degenerate'
         Note: this branch ALWAYS uses Phase 3's local FALLBACK_ALPHA/FALLBACK_BETA
         constants, ignoring any `fallback_alpha`/`fallback_beta` fields the EB
         JSON might carry. This decouples Phase 3 from Phase 2's choice of
         fallback values — if Phase 2 ever changes its emitted fallbacks,
         Phase 3's behavior here stays the same. The Phase 2 review caught
         the exact regression this guards against (REPRESSION__C with
         fitted concentration=312k that would corrupt shrinkage).
      4. Cell exists and `degenerate=False`    -> cell.alpha, cell.beta, reason=''

    Phase 3 must never silently use a degenerate cell's fitted alpha/beta.
    """
    if sector in eb_data.get("sectors_not_fit", []):
        return FALLBACK_ALPHA, FALLBACK_BETA, True, "sector_not_fit"
    cell_key = f"{sector}__{l1}"
    cell = eb_data.get("cells", {}).get(cell_key)
    if cell is None:
        return FALLBACK_ALPHA, FALLBACK_BETA, True, "cell_missing"
    if cell.get("degenerate", False):
        # Always FALLBACK_* — do NOT trust cell.fallback_alpha/beta. See
        # docstring rationale (decoupling guard).
        return FALLBACK_ALPHA, FALLBACK_BETA, True, "cell_degenerate"
    return float(cell["alpha"]), float(cell["beta"]), False, ""


def compute_weight(k_d: int, n_d: int, alpha: float, beta: float) -> float:
    """EB-shrunken weight: posterior mean of Beta(k+alpha, n-k+beta).

    For Binomial-with-Beta-prior conjugacy:
        posterior = Beta(k + alpha, n - k + beta)
        posterior mean = (k + alpha) / (n + alpha + beta)

    With k = recipes_with_indicator and n = total_instances per
    category, this is the shrunken estimate of the indicator's
    "frequency in this category" given the cell hyperprior.
    """
    if n_d < 0 or k_d < 0 or k_d > n_d:
        raise ValueError(f"invalid (k_d={k_d}, n_d={n_d})")
    return (k_d + alpha) / (n_d + alpha + beta)


def main() -> None:
    print("[1] Loading EB priors")
    eb_data = load_eb_priors()
    n_cells = len(eb_data.get("cells", {}))
    n_not_fit = len(eb_data.get("sectors_not_fit", []))
    n_below_floor = len(eb_data.get("cells_below_floor", []))
    print(f"    cells: {n_cells}, sectors_not_fit: {n_not_fit}, cells_below_floor: {n_below_floor}")

    print("\n[2] Loading static maps (sectors, L1, catalog, indicator_map)")
    sectors = eb.load_sectors()              # WB-01 -> CONFLICT
    event_l1 = eb.load_event_l1_map()        # event_category -> L1 letter
    l1_labels = eb.load_l1_labels()
    api_to_catalog = eb.parse_catalog_api_to_catalog_code()  # API_code -> WB-01
    num_to_api = eb.load_numeric_to_api()    # numeric_id -> API_code
    print(f"    chain: {len(num_to_api)} numeric_id -> {len(api_to_catalog)} catalog_codes -> {len(sectors)} sectors")

    # Build numeric_id -> sector chain
    num_to_sector: dict[int, str] = {}
    num_to_str_id: dict[int, str] = {}
    for num_id, api_code in num_to_api.items():
        cat_code = api_to_catalog.get(api_code)
        if cat_code is None:
            continue
        num_to_str_id[num_id] = cat_code
        sector = sectors.get(cat_code)
        if sector:
            num_to_sector[num_id] = sector
    print(f"    chain coverage: {len(num_to_sector)}/{len(num_to_api)} numeric_ids -> sector")

    print("\n[3] Pulling observations from Athena (recipes_aggregated UNNEST)")
    obs = eb.pull_observations()
    print(f"    pulled {len(obs)} (event_category, numeric_id, k_d, n_d) rows")

    print("\n[4] Computing per-cell shrunken weights")
    weights: list[dict] = []
    skipped_no_sector = 0
    skipped_no_l1 = 0
    fallback_counts: dict[str, int] = {}
    for event_cat, num_id, k_d, n_d in obs:
        sector = num_to_sector.get(num_id)
        if sector is None:
            skipped_no_sector += 1
            continue
        l1 = event_l1.get(event_cat)
        if l1 is None:
            skipped_no_l1 += 1
            continue
        alpha, beta, used_fallback, reason = lookup_cell_prior(eb_data, sector, l1)
        if used_fallback:
            fallback_counts[reason] = fallback_counts.get(reason, 0) + 1
        w = compute_weight(k_d, n_d, alpha, beta)
        weights.append({
            "indicator_numeric_id": int(num_id),
            "indicator_catalog_id": num_to_str_id.get(num_id, ""),
            "event_category": event_cat,
            "L1": l1,
            "L1_label": l1_labels.get(l1, ""),
            "sector": sector,
            "weight": float(w),
            "k_d": int(k_d),
            "n_d": int(n_d),
            "alpha_used": float(alpha),
            "beta_used": float(beta),
            "used_fallback": bool(used_fallback),
            "fallback_reason": reason,
        })

    print(f"    weights computed: {len(weights)}")
    print(f"    skipped (no sector): {skipped_no_sector}")
    print(f"    skipped (no L1):     {skipped_no_l1}")

    # Loud warning when most observations are dropped — mirror Phase 2's
    # >60% threshold for consistency (QA review 2026-05-03 caught
    # that Phase 3 was silent on this case while Phase 2 warned). Phase 3
    # currently expects high skip rates (#591 legacy WB indicators) so
    # >60% is loud-but-expected; >90% is a regression signal.
    skip_frac = (skipped_no_sector + skipped_no_l1) / max(len(obs), 1)
    if skip_frac > 0.90:
        print(
            f"\n  [WARN] {skip_frac:.1%} of observations skipped — coverage "
            f"REGRESSION suspected. Expected ~78% pre-#591; >90% means the "
            f"sector chain or recipes_aggregated drifted. Investigate before "
            f"trusting weight-matrix.json downstream.",
            file=sys.stderr,
        )
    elif skip_frac > 0.60:
        print(
            f"\n  [INFO] {skip_frac:.1%} of observations skipped (sector or L1 "
            f"missing). Within expected range pre-#591 legacy WB indicator "
            f"filtering; the {len(weights)} computed weights cover the "
            f"V-Dem-derived methodology surface that the pipeline currently "
            f"surfaces. Phase 4 validation can proceed; new sectors fill in "
            f"as ingestion catches up.",
            file=sys.stderr,
        )

    print("    fallback breakdown:")
    for reason, n in sorted(fallback_counts.items()):
        print(f"      {reason:25s}: {n:>5d}")
    n_eb_priors = len(weights) - sum(fallback_counts.values())
    print(f"      (full EB prior used)  : {n_eb_priors:>5d}")

    # Sanity: weights in [0, 1]
    if weights:
        ws = np.array([w["weight"] for w in weights])
        print(f"\n    weight distribution: min={ws.min():.4f}  max={ws.max():.4f}  "
              f"mean={ws.mean():.4f}  median={np.median(ws):.4f}")
        assert ws.min() >= 0.0 and ws.max() <= 1.0, "weight out of [0,1] range"

    print(f"\n[5] Writing {OUTPUT_JSON}")
    output = {
        "schema_version": 1,
        "generated": datetime.now(timezone.utc).isoformat(),
        "source_data": {
            "eb_hyperpriors_schema_version": eb_data.get("schema_version"),
            "eb_hyperpriors_generated": eb_data.get("generated"),
            "recipes_aggregated_baked": eb_data.get("source_data", {}).get("recipes_aggregated_baked"),
            "n_observations_total": len(obs),
            "n_weights_computed": len(weights),
            "n_skipped_no_sector": skipped_no_sector,
            "n_skipped_no_l1": skipped_no_l1,
        },
        "method": (
            "Posterior mean of Beta(k_d + alpha, n_d - k_d + beta) under "
            "Beta-Binomial conjugacy. weight = (k_d + alpha) / (n_d + alpha + beta). "
            "(alpha, beta) is the EB hyperprior for the (sector, L1) cell from "
            "Phase 2; degenerate cells and unfit sectors fall back to Beta(1, 1) "
            "uniform per the eb-hyperpriors.json fallback_policy."
        ),
        "fallback_breakdown": fallback_counts,
        "n_full_eb_prior": n_eb_priors,
        "weights": weights,
    }
    OUTPUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"    wrote {len(weights)} weight rows; "
          f"{n_eb_priors} used full EB prior, "
          f"{sum(fallback_counts.values())} used Beta(1,1) fallback")


if __name__ == "__main__":
    main()
