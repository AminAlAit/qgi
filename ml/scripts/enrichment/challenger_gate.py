"""Challenger gate - indicator-enrichment pipeline stage 3 (the brain).

Decides, deterministically and cheaply, which walked recipes a set of NEW
candidate indicators could actually change - and therefore which recipes need a
single-recipe re-walk when the pool grows (109 -> 250 -> 500).

Premise (indicator-enrichment-cicd-design.md SS3; run_f_ml_1_poc.py:140
``TOP_N_PREFILTER = 40``): the greedy XGBoost walk only ever sees the top-40
indicators by univariate LR-LOCO AUC. A new indicator can change a recipe's
greedy result ONLY if it out-ranks that recipe's current 40th-best indicator on
the SAME univariate screen (including the exact coverage gate). Indicators below
the cutoff are provably inert for that recipe and can be skipped.

This module reuses ``run_f_ml_1_poc`` verbatim (``univariate_loco_screen``,
``build_samples``, the coverage gate) so the gate runs the EXACT prefilter
mechanism the walk uses - not an approximation of it. The per-recipe cutoff is
NOT persisted by the walk, so it is recomputed here on the current pool with the
SAME samples the candidates are evaluated on (so the pool-vs-candidate
comparison is internally consistent). To reproduce a *specific* walk's cutoff
bit-for-bit, pass that walk's negative-sampling seed via ``--seed`` (the fleet
production default is 12345, which is this module's default). A different seed
draws a different negative set, which can shift borderline AUCs slightly.

Doubles as the deterministic cost-preflight (qgi-aws-tf#807): the flagged-recipe
set x known per-recipe walk-time anchors = a $/wall-clock forecast before any
AWS spend.

Local, $0, no AWS. Run BEFORE any ingest or re-walk.

Usage:
    python scripts/enrichment/challenger_gate.py \\
        --panel-dir data/parquet_panels \\
        --candidates IL-01 IL-02 UN-01 \\
        --output results/enrichment/challenger-manifest.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# Import the walk driver verbatim (mirrors compute_recipe_country_similarity.py).
SCRIPTS_DIR = Path(__file__).resolve().parents[1]  # qgi-ml/scripts
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import run_f_ml_1_poc as drv  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent  # qgi-ml
DEFAULT_PANEL_DIR = REPO_ROOT / "data" / "parquet_panels"
DEFAULT_SHAPE_DIR = REPO_ROOT / "data" / "shape_inputs_v2"
DEFAULT_TRACKER = REPO_ROOT.parent / "qgi-frontend" / "data" / "recipe-tracker.json"

# recipe-tracker.json status values. Default scope = the 39 walked_no_graduation
# recipes (true F-ML-1 walks). The 3 live_legacy recipes (42 total have a trained
# model) were walked under the older D2+D7-Beta architecture - no F-ML-1
# greedy/univariate prefilter - so the top-40 cutoff concept does not strictly
# apply; they are included only with --include-legacy.
WALKED_STATUS = "walked_no_graduation"
LEGACY_STATUS = "live_legacy"

# Fleet production negative-sampling seed (run_f_ml_1_poc.py _main default, line ~1488).
# Default here so the recomputed cutoff tracks the real walks' cutoff.
DEFAULT_SEED = 12345

# Known per-recipe walk-time anchors in HOURS (indicator-enrichment-cicd-design.md SS3b).
# Recipes without an anchor use the median. Informational cost forecast only - the
# binding cost-ack still comes from the canary (qgi-aws-tf#807).
WALK_TIME_ANCHORS_H: dict[str, float] = {
    "foreign_intervention": 2.0,
    "terrorist_attack": 2.4,
    "economic_recession": 4.0,
    "civil_war_and_insurgency": 5.3,
    "elections_and_voting": 21.8,
}
MEDIAN_WALK_H = 4.0
# Per-recipe-hour $ rate for the rough band. TE fleet runs single-threaded walks on
# 2-vCPU c7g.large Spot (instance-rule exception, 2026-05-24); $0.05/vCPU-hr is design
# SS2a's conservative ~3x-on-demand upper bound -> ~$0.10/recipe-hour. Informational
# only; the binding cost-ack comes from the canary.
USD_PER_RECIPE_HOUR = 0.05 * 2


def _is_finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def load_walked_recipes(tracker_path: Path, include_legacy: bool = False) -> list[dict[str, str]]:
    """Return [{recipe_id, status}] for recipes that have a trained model.

    Default scope = the 39 F-ML-1-walked recipes (status=walked_no_graduation).
    """
    data = json.loads(Path(tracker_path).read_text(encoding="utf-8"))
    allowed = {WALKED_STATUS}
    if include_legacy:
        allowed.add(LEGACY_STATUS)
    return [
        {"recipe_id": r["recipe_id"], "status": r.get("status", "")}
        for r in data.get("recipes", [])
        if r.get("status") in allowed
    ]


def load_positives(recipe_id: str, shape_dir: Path) -> pd.DataFrame:
    """Load a recipe's positives.csv -> samples-ready frame [country, year, label=1].

    positives.csv columns: country_id (lowercase underscore), event_year (int).
    Country ids are normalized to the Title-Case canonical form the panels use,
    via drv.normalize_country_id (the 4 COUNTRY_NAME_OVERRIDES are binding).
    """
    path = Path(shape_dir) / recipe_id / "positives.csv"
    df = pd.read_csv(path)
    df = df.rename(columns={"event_year": "year"})
    df["country"] = df["country_id"].apply(drv.normalize_country_id)
    df["year"] = df["year"].astype(int)
    df["label"] = 1
    return df[["country", "year", "label"]]


def compute_cutoff(
    ranked: list[str], scores: dict[str, dict], top_n: int = drv.TOP_N_PREFILTER
) -> tuple[float, str | None, int]:
    """Derive a recipe's current top-N univariate cutoff.

    ``ranked`` must be the FULL ranking (call univariate_loco_screen with
    top_n=len(pool)); ranked is sorted desc by AUC with coverage-failed / nan
    indicators sorted last. Returns (cutoff_auc, cutoff_indicator_id, n_valid).

    If fewer than ``top_n`` indicators pass the coverage gate, the cutoff is
    -inf: any coverage-passing candidate automatically enters the greedy pool.
    """
    valid = [
        (i, float(scores[i]["univariate_loco_auc"]))
        for i in ranked
        if _is_finite(scores.get(i, {}).get("univariate_loco_auc"))
    ]
    n_valid = len(valid)
    if n_valid < top_n:
        return float("-inf"), None, n_valid
    cutoff_id, cutoff_auc = valid[top_n - 1]
    return cutoff_auc, cutoff_id, n_valid


def classify_crack(candidate_auc: Any, cutoff_auc: float, coverage_fail: bool) -> bool:
    """A candidate cracks a recipe's top-N iff it passes the coverage gate, has a
    finite AUC, and strictly out-ranks the current cutoff."""
    if coverage_fail or not _is_finite(candidate_auc):
        return False
    return float(candidate_auc) > cutoff_auc


def evaluate_recipe(
    recipe_id: str,
    candidate_ids: list[str],
    current_pool_ids: list[str],
    panels: dict[str, pd.DataFrame],
    positives: pd.DataFrame,
    *,
    seed: int = DEFAULT_SEED,
    negatives_per_positive: int = 3,
    top_n: int = drv.TOP_N_PREFILTER,
) -> dict[str, Any]:
    """Core, in-memory gate for one recipe (no filesystem - directly testable).

    Builds the recipe's LOCO samples once, derives the current top-N cutoff from
    the current pool, then screens each candidate on the SAME samples and flags
    those that crack the cutoff.
    """
    samples = drv.build_samples(positives, negatives_per_positive=negatives_per_positive, seed=seed)
    n_pos = int((samples["label"] == 1).sum())
    n_neg = int((samples["label"] == 0).sum())

    # Current pool cutoff. top_n=len(pool) forces univariate_loco_screen to return
    # the FULL ranking (it otherwise truncates to its own top_n) so compute_cutoff
    # can pick the exact Nth-best.
    ranked_pool, scores_pool = drv.univariate_loco_screen(
        samples, current_pool_ids, panels, top_n=len(current_pool_ids)
    )
    assert len(ranked_pool) == len(current_pool_ids), (
        "univariate_loco_screen must return the full pool ranking for an exact cutoff")
    cutoff_auc, cutoff_id, n_valid_pool = compute_cutoff(ranked_pool, scores_pool, top_n=top_n)

    # Candidate screen on the identical samples (same coverage gate + LR LOCO).
    _, scores_cand = drv.univariate_loco_screen(
        samples, candidate_ids, panels, top_n=len(candidate_ids)
    )

    per_candidate = []
    for cid in candidate_ids:
        sc = scores_cand.get(cid, {})
        auc = sc.get("univariate_loco_auc", float("nan"))
        cov_fail = bool(sc.get("coverage_fail", False))
        cracks = classify_crack(auc, cutoff_auc, cov_fail)
        per_candidate.append({
            "candidate_id": cid,
            "candidate_auc": (None if not _is_finite(auc) else round(float(auc), 4)),
            "coverage_fail": cov_fail,
            "cracks_top40": cracks,
        })

    return {
        "recipe_id": recipe_id,
        "n_pos": n_pos,
        "n_neg": n_neg,
        "n_valid_current_pool": n_valid_pool,
        "cutoff_auc": (None if not math.isfinite(cutoff_auc) else round(cutoff_auc, 4)),
        "cutoff_indicator_id": cutoff_id,
        "per_candidate": per_candidate,
        "flagged": any(c["cracks_top40"] for c in per_candidate),
    }


def forecast_cost(flagged_recipe_ids: list[str]) -> dict[str, Any]:
    """Deterministic cost-preflight: flagged recipes x known walk-time anchors."""
    hours = {r: WALK_TIME_ANCHORS_H.get(r, MEDIAN_WALK_H) for r in flagged_recipe_ids}
    total_h = sum(hours.values())
    return {
        "n_flagged_recipes": len(flagged_recipe_ids),
        "total_walk_hours_estimate": round(total_h, 1),
        "usd_estimate_band": [round(total_h * USD_PER_RECIPE_HOUR * 0.5, 2),
                              round(total_h * USD_PER_RECIPE_HOUR, 2)],
        "per_recipe_hours": hours,
        "note": ("Wall-clock assumes MaxConcurrency serialization upper bound; "
                 "real fan-out at MaxConcurrency=2 is ~half. Binding cost-ack "
                 "comes from the canary (qgi-aws-tf#807)."),
    }


def load_panels(ids: list[str], panel_dir: Path) -> dict[str, pd.DataFrame]:
    return {i: drv.load_panel(i, panel_dir) for i in ids}


def run_gate(
    *,
    panel_dir: Path,
    candidate_ids: list[str],
    candidate_panel_dir: Path | None = None,
    recipes: list[dict[str, str]],
    shape_dir: Path,
    seed: int = DEFAULT_SEED,
    negatives_per_positive: int = 3,
    top_n: int = drv.TOP_N_PREFILTER,
) -> dict[str, Any]:
    """Full gate over all recipes. Loads panels once, evaluates each recipe.

    Loads the whole pool into memory once (fine at the 109/250 scale; revisit a
    lazy/streamed load at the 500 scale). Current pool = every panel in
    ``panel_dir`` MINUS the candidates, so candidates may live in ``panel_dir``
    (already ingested) or a separate ``candidate_panel_dir`` - either way they are
    excluded from the pool and read from their own dir.
    """
    candidate_panel_dir = candidate_panel_dir or panel_dir
    candidate_set = set(candidate_ids)
    pool_ids = [i for i in drv.list_candidate_indicators(panel_dir) if i not in candidate_set]

    panels = load_panels(pool_ids, panel_dir)
    panels.update(load_panels(candidate_ids, candidate_panel_dir))

    per_recipe = []
    for rec in recipes:
        rid = rec["recipe_id"]
        try:
            positives = load_positives(rid, shape_dir)
        except FileNotFoundError:
            per_recipe.append({"recipe_id": rid, "error": "positives.csv not found", "flagged": False})
            continue
        result = evaluate_recipe(
            rid, candidate_ids, pool_ids, panels, positives,
            seed=seed, negatives_per_positive=negatives_per_positive, top_n=top_n,
        )
        result["status"] = rec.get("status")
        per_recipe.append(result)

    flagged = [r["recipe_id"] for r in per_recipe if r.get("flagged")]
    unflagged = [r["recipe_id"] for r in per_recipe if not r.get("flagged") and "error" not in r]

    # Roll up each candidate across recipes. A candidate is:
    #   active                     - cracks the top-40 of >= 1 recipe (worth ingesting)
    #   not_evaluated              - appeared in ZERO successful per-recipe screens
    #                                (e.g. every recipe errored / no recipes) -> NOT inert
    #   coverage_failed_everywhere - never cracks AND coverage-failed on every recipe
    #                                (a data/coverage problem, not a weak signal)
    #   inert                      - never cracks but was genuinely screened somewhere
    #                                (provably below every cutoff -> skippable)
    active_candidates, inert_candidates, coverage_failed_everywhere, not_evaluated = [], [], [], []
    for cid in candidate_ids:
        entries = [c for r in per_recipe for c in r.get("per_candidate", [])
                   if c["candidate_id"] == cid]
        if any(c["cracks_top40"] for c in entries):
            active_candidates.append(cid)
        elif not entries:
            not_evaluated.append(cid)
        elif all(c["coverage_fail"] for c in entries):
            coverage_failed_everywhere.append(cid)
        else:
            inert_candidates.append(cid)

    return {
        "schema_version": 1,
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "pool_size": len(pool_ids),
        "n_candidates": len(candidate_ids),
        "n_recipes_evaluated": len(per_recipe),
        "top_n_prefilter": top_n,
        "flagged_recipes": flagged,
        "unflagged_recipes": unflagged,
        "active_candidates": active_candidates,
        "inert_candidates": inert_candidates,
        "coverage_failed_everywhere": coverage_failed_everywhere,
        "not_evaluated_candidates": not_evaluated,
        "cost_forecast": forecast_cost(flagged),
        "per_recipe": per_recipe,
    }


def _parse_candidates(args: argparse.Namespace) -> list[str]:
    if args.candidates_file:
        text = Path(args.candidates_file).read_text(encoding="utf-8")
        return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    return list(args.candidates or [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Challenger gate: which recipes a candidate set could change.")
    ap.add_argument("--panel-dir", type=Path, default=DEFAULT_PANEL_DIR,
                    help="Dir of current-pool panels: {id}/{id}.parquet")
    ap.add_argument("--candidate-panel-dir", type=Path, default=None,
                    help="Dir of NEW candidate panels (default: same as --panel-dir)")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--candidates", nargs="+", help="New candidate indicator ids")
    grp.add_argument("--candidates-file", type=Path, help="File with one candidate id per line")
    ap.add_argument("--tracker", type=Path, default=DEFAULT_TRACKER, help="recipe-tracker.json")
    ap.add_argument("--shape-dir", type=Path, default=DEFAULT_SHAPE_DIR, help="shape_inputs_v2 dir")
    ap.add_argument("--include-legacy", action="store_true", help="Also evaluate the 3 live_legacy recipes")
    ap.add_argument("--recipe-ids", nargs="+", default=None, help="Override: evaluate only these recipes")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help="Negative-sampling seed; match the target walk's --seed for an exact cutoff "
                         f"(default {DEFAULT_SEED}, the fleet production default)")
    ap.add_argument("--negatives-per-positive", type=int, default=3)
    ap.add_argument("--top-n", type=int, default=drv.TOP_N_PREFILTER,
                    help=f"Prefilter cutoff rank (default {drv.TOP_N_PREFILTER}, the walk's TOP_N_PREFILTER)")
    ap.add_argument("--output", type=Path, default=None, help="Write manifest JSON here")
    args = ap.parse_args(argv)

    candidate_ids = _parse_candidates(args)
    if not candidate_ids:
        ap.error("no candidates provided")

    if args.recipe_ids:
        recipes = [{"recipe_id": r, "status": "override"} for r in args.recipe_ids]
    else:
        recipes = load_walked_recipes(args.tracker, include_legacy=args.include_legacy)

    manifest = run_gate(
        panel_dir=args.panel_dir,
        candidate_ids=candidate_ids,
        candidate_panel_dir=args.candidate_panel_dir,
        recipes=recipes,
        shape_dir=args.shape_dir,
        seed=args.seed,
        negatives_per_positive=args.negatives_per_positive,
        top_n=args.top_n,
    )

    out = json.dumps(manifest, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
        print(f"Wrote manifest -> {args.output}")
    fc = manifest["cost_forecast"]
    cfe = len(manifest["coverage_failed_everywhere"])
    print(f"Flagged {len(manifest['flagged_recipes'])}/{manifest['n_recipes_evaluated']} recipes; "
          f"{len(manifest['active_candidates'])}/{manifest['n_candidates']} candidates active, "
          f"{len(manifest['inert_candidates'])} inert"
          + (f", {cfe} coverage-failed-everywhere" if cfe else "") + "; "
          f"~{fc['total_walk_hours_estimate']}h re-walk, ${fc['usd_estimate_band'][0]}-{fc['usd_estimate_band'][1]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
