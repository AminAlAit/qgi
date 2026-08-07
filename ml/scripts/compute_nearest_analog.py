"""Compute nearest historical analog per country for a given recipe.

Capability #2 of the 5 new TE capabilities (te-new-capabilities-spec.md §2).

For each scored country (from the recipe-similarity-scores artifact), builds
its evaluation-year z-trajectory over the selected indicators/window and
compares it against every historical positive's pre-event z-trajectory
(window ending event_year−1, mirroring build_canonical_profile_from_walk's
per-positive extraction exactly). Returns the top-K=3 analogs per country
ranked by SHAP-weighted mean cosine.

Honesty gate (binding, spec §2):
  - Pre-registered match-quality floor = 0.70 weighted cosine.
  - Countries with best analog < floor are flagged WEAK_ANALOG + suppressed=True.
  - m8_r5_note: "resemblance, not destiny" + regional-clustering caveat.
  - same_cohort flag for sanity (analogs may share governance trajectory
    because they are regional neighbours).

M8-R5 binding: discrimination/similarity layer only. Never calibrated
point-probability. Do not relabel weighted cosine as "probability" anywhere.

Usage:
    python scripts/compute_nearest_analog.py \\
        --recipe-id foreign_intervention \\
        --scores-file qgi-data/reference/recipe-similarity-scores-foreign_intervention-2021.json \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --panel-dir data/parquet_panels \\
        --cohort-assignments qgi-data/reference/cohort-assignments.json \\
        --output-dir qgi-data/reference/ \\
        --evaluation-year 2021

Output:
    nearest-analog-{recipe_id}-{year}.json   (per-country top-K analogs)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402
from compute_recipe_country_similarity import (  # noqa: E402
    extract_country_trajectory,
    cosine_similarity,
    prebake_zscore_distribution,
)

REPO_ROOT = SCRIPTS_DIR.parent

# ---------------------------------------------------------------------------
# Pre-registered constants (must not change after results are seen; spec §2)
# ---------------------------------------------------------------------------

ANALOG_FLOOR: float = 0.70
"""Pre-registered match-quality floor per te-new-capabilities-spec.md §2."""

DEFAULT_TOP_K: int = 3
"""Top-K analogs to return per country per spec §2."""

M8_R5_NOTE: str = (
    "NEAREST ANALOG: resemblance, not destiny. "
    "A high weighted cosine means this country's recent trajectory structurally "
    "resembles the pre-event trajectory of the historical case, not that the same "
    "outcome will recur. "
    "Regional-clustering caveat: analogs may be geographic or governance neighbours "
    "that share systemic trajectories; the same_cohort flag helps identify this. "
    "This capability is part of the M8-R5 discrimination/similarity layer and "
    "operates entirely in trajectory-space — it is NOT a calibrated probability "
    "and must never be relabelled as such."
)


# ---------------------------------------------------------------------------
# Core pure functions
# ---------------------------------------------------------------------------


def compute_analog_score(
    target_traj: dict[str, np.ndarray],
    positive_traj: dict[str, np.ndarray],
    shap_weights: dict[str, float],
) -> float:
    """SHAP-weighted mean cosine between target and a single historical positive.

    Mirrors compute_country_recipe_similarity's aggregation logic exactly:
    weighted arithmetic mean over indicators, skipping indicators missing
    from either target or positive (does NOT penalise missing ones —
    renormalises to the weight of present indicators).

    Args:
        target_traj:   {indicator_id: (W,) z-score vector} for the target country.
        positive_traj: {indicator_id: (W,) z-score vector} for the positive case.
        shap_weights:  {indicator_id: normalized SHAP weight}.

    Returns:
        SHAP-weighted mean cosine in [-1, 1]. Returns 0.0 when no indicator
        is present in both trajectories.
    """
    weighted_sum = 0.0
    total_weight = 0.0
    for ind, weight in shap_weights.items():
        T_target = target_traj.get(ind)
        T_pos = positive_traj.get(ind)
        if T_target is None or T_pos is None:
            continue
        m = min(len(T_target), len(T_pos))
        cos = cosine_similarity(T_target[:m], T_pos[:m])
        weighted_sum += weight * cos
        total_weight += weight
    if total_weight <= 0.0:
        return 0.0
    return weighted_sum / total_weight


def find_nearest_analogs(
    target_country: str,
    target_traj: dict[str, np.ndarray],
    positives_traj: list[tuple[str, int, dict[str, np.ndarray]]],
    shap_weights: dict[str, float],
    cohort_map: dict[str, str],
    top_k: int = DEFAULT_TOP_K,
    analog_floor: float = ANALOG_FLOOR,
) -> dict[str, Any]:
    """Find top-K nearest historical analogs for one target country.

    Args:
        target_country:  Country name (used for self-exclusion when target is
                         also a positive).
        target_traj:     {indicator_id: (W,) z-vector} for the target at eval_year.
        positives_traj:  List of (country, event_year, {ind: z-vector}) for all
                         historical positives. Pre-event trajectories (window ending
                         event_year−1) must have been extracted by the caller
                         following build_canonical_profile_from_walk's per-positive
                         logic exactly.
        shap_weights:    {indicator_id: normalized weight}.
        cohort_map:      {country: cohort_label} at eval_year (for same_cohort flag).
        top_k:           Maximum analogs to return (spec K=3).
        analog_floor:    Pre-registered suppression floor (0.70).

    Returns:
        {
          "analogs": [
              {
                  "analog_country": str,
                  "analog_event_year": int,
                  "weighted_cosine": float,
                  "same_cohort": bool,
              },
              ...   (sorted descending by weighted_cosine, len <= top_k)
          ],
          "best_weighted_cosine": float | None,
          "suppressed": bool,
          "flag": str | None,   # "WEAK_ANALOG" or None
        }
    """
    target_cohort = cohort_map.get(target_country)
    scored: list[tuple[float, str, int]] = []

    for pos_country, pos_event_year, pos_traj in positives_traj:
        # Self-exclusion: skip when target country is also a positive
        # (match on country id regardless of event_year)
        if pos_country == target_country:
            continue
        score = compute_analog_score(target_traj, pos_traj, shap_weights)
        scored.append((score, pos_country, pos_event_year))

    # Sort descending by cosine
    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:top_k]

    analogs = []
    for cos, country, ev_year in top:
        pos_cohort = cohort_map.get(country)
        same_cohort = (
            target_cohort is not None
            and pos_cohort is not None
            and target_cohort == pos_cohort
        )
        analogs.append({
            "analog_country": country,
            "analog_event_year": ev_year,
            "weighted_cosine": float(cos),
            "same_cohort": bool(same_cohort),
        })

    best_cos: float | None = analogs[0]["weighted_cosine"] if analogs else None
    suppressed = best_cos is None or best_cos < analog_floor
    flag = "WEAK_ANALOG" if suppressed else None

    return {
        "analogs": analogs,
        "best_weighted_cosine": best_cos,
        "suppressed": suppressed,
        "flag": flag,
    }


# ---------------------------------------------------------------------------
# Helper: extract pre-event z-trajectory for one positive
# (mirrors build_canonical_profile_from_walk's per-positive extraction exactly)
# ---------------------------------------------------------------------------


def _extract_positive_pretraj(
    pos_country: str,
    event_year: int,
    panels: dict[str, pd.DataFrame],
    chosen_window: int,
    selected_indicators: list[str],
) -> dict[str, np.ndarray]:
    """Build the pre-event z-trajectory for one historical positive.

    Window ending event_year−1 (i.e. [event_year−window, event_year−1]).
    Z-score baseline = panel-wide mean/std at event_year−1 (or per-country
    fallback when < 10 countries in panel). This is the IDENTICAL logic used
    by build_canonical_profile_from_walk in compute_recipe_country_similarity.py.

    Returns dict of {indicator: (W,) z-vector}; indicators with insufficient
    data are omitted.
    """
    traj: dict[str, np.ndarray] = {}
    for ind in selected_indicators:
        panel = panels[ind]
        cdf = panel[panel["country"] == pos_country]
        if len(cdf) == 0:
            continue
        series = cdf.set_index("year")["value"]
        window_data = series.loc[event_year - chosen_window: event_year - 1]
        full_index = pd.RangeIndex(event_year - chosen_window, event_year)
        window_full = window_data.reindex(full_index)
        if window_full.dropna().shape[0] < max(3, chosen_window // 3):
            continue
        # Panel-wide z-score at event_year−1 (same as build_canonical_profile_from_walk)
        panel_at_year = panel[panel["year"] == event_year - 1]["value"].dropna()
        if len(panel_at_year) < 10:
            baseline = series.loc[
                max(event_year - 25, series.index.min()): event_year - 1
            ].dropna()
            mu = float(baseline.mean()) if len(baseline) > 0 else 0.0
            sd = float(baseline.std() or 1.0)
        else:
            mu = float(panel_at_year.mean())
            sd = float(panel_at_year.std() or 1.0)
        z = (window_full.values - mu) / sd
        z = np.where(np.isfinite(z), z, 0.0)
        traj[ind] = z
    return traj


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recipe-id", required=True,
                   help="Recipe identifier (e.g. foreign_intervention)")
    p.add_argument("--scores-file", type=Path, required=True,
                   help="Path to recipe-similarity-scores-{recipe}-{year}.json")
    p.add_argument("--walk-summary", type=Path, required=True,
                   help="Path to f-ml-1-poc-summary.json from the walk run")
    p.add_argument("--panel-dir", type=Path,
                   default=REPO_ROOT / "data" / "parquet_panels",
                   help="Directory containing per-indicator parquet panels")
    p.add_argument("--cohort-assignments", type=Path,
                   default=REPO_ROOT.parent / "qgi-data" / "reference" / "cohort-assignments.json",
                   help="Path to cohort-assignments.json")
    p.add_argument("--output-dir", type=Path, required=True,
                   help="Directory to write nearest-analog-{recipe}-{year}.json")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                   help=f"Number of top analogs to return per country (default: {DEFAULT_TOP_K})")
    p.add_argument("--analog-floor", type=float, default=ANALOG_FLOOR,
                   help=f"Pre-registered suppression floor (default: {ANALOG_FLOOR})")
    p.add_argument("--evaluation-year", type=int, default=2021,
                   help="Evaluation year for target country trajectories (default: 2021)")
    return p


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load scores artifact
    with open(args.scores_file, encoding="utf-8") as f:
        scores_data = json.load(f)
    assert scores_data["recipe_id"] == args.recipe_id, (
        f"Scores artifact recipe_id={scores_data['recipe_id']} != {args.recipe_id}"
    )
    scored_countries = scores_data["scores"]
    selected_indicators: list[str] = scores_data["selected_indicators"]
    chosen_window: int = scores_data["chosen_window"]
    shap_weights: dict[str, float] = scores_data["shap_importance_normalized"]

    # Load walk summary (for positives path confirmation + recipe_id check)
    with open(args.walk_summary, encoding="utf-8") as f:
        walk = json.load(f)
    assert walk["recipe_id"] == args.recipe_id, (
        f"Walk recipe_id={walk['recipe_id']} != {args.recipe_id}"
    )

    # Load positives
    positives_path = REPO_ROOT / "data" / "shape_inputs_v2" / args.recipe_id / "positives.csv"
    pos_df = pd.read_csv(positives_path)
    pos_df["country"] = pos_df["country_id"].apply(drv.normalize_country_id)
    pos_df = pos_df.rename(columns={"event_year": "year"})
    print(f"Positives: {len(pos_df)} rows for {args.recipe_id}")

    # Load panels
    panels: dict[str, pd.DataFrame] = {
        ind: drv.load_panel(ind, args.panel_dir) for ind in selected_indicators
    }

    # Pre-bake z-distribution for target trajectories at evaluation_year
    print(f"Pre-baking z-distribution for eval_year={args.evaluation_year}...")
    ind_dist = prebake_zscore_distribution(args.panel_dir, selected_indicators, args.evaluation_year)

    # Build pre-event z-trajectories for all positives
    # (window ending event_year−1; same z-score baseline logic as build_canonical_profile_from_walk)
    print("Building positive pre-event trajectories...")
    positives_traj: list[tuple[str, int, dict[str, np.ndarray]]] = []
    for _, row in pos_df.iterrows():
        country = str(row["country"])
        event_year = int(row["year"])
        traj = _extract_positive_pretraj(
            pos_country=country,
            event_year=event_year,
            panels=panels,
            chosen_window=chosen_window,
            selected_indicators=selected_indicators,
        )
        if traj:  # Only include positives with at least one indicator extracted
            positives_traj.append((country, event_year, traj))
    print(f"  {len(positives_traj)} positive trajectories extracted "
          f"(from {len(pos_df)} positives rows)")

    # Load cohort assignments
    with open(args.cohort_assignments, encoding="utf-8") as f:
        cohort_data = json.load(f)
    cohort_assignments = cohort_data.get("assignments", cohort_data)

    def _get_cohort(country: str) -> str | None:
        country_cohorts = cohort_assignments.get(country, {})
        # Use the assignment at evaluation_year or the closest available year
        return country_cohorts.get(str(args.evaluation_year))

    # Build cohort_map for all relevant countries (scored + positives)
    cohort_map: dict[str, str] = {}
    for country in scored_countries:
        c = _get_cohort(country)
        if c:
            cohort_map[country] = c
    for country, _, _ in positives_traj:
        c = _get_cohort(country)
        if c:
            cohort_map[country] = c

    # Compute nearest analogs for each scored country
    print(f"Computing nearest analogs for {len(scored_countries)} scored countries...")
    results: dict[str, Any] = {}
    n_suppressed = 0
    for target_country in sorted(scored_countries.keys()):
        # Extract target's eval-year z-trajectory
        target_traj: dict[str, np.ndarray] = {}
        for ind in selected_indicators:
            t = extract_country_trajectory(
                panels[ind], target_country, args.evaluation_year, chosen_window,
                ind_dist=ind_dist[ind],
            )
            if t is not None:
                target_traj[ind] = t

        analog_result = find_nearest_analogs(
            target_country=target_country,
            target_traj=target_traj,
            positives_traj=positives_traj,
            shap_weights=shap_weights,
            cohort_map=cohort_map,
            top_k=args.top_k,
            analog_floor=args.analog_floor,
        )
        results[target_country] = analog_result
        if analog_result["suppressed"]:
            n_suppressed += 1

    n_total = len(results)
    n_available = n_total - n_suppressed
    print(f"  {n_available}/{n_total} countries with strong analog (>= {args.analog_floor:.2f}); "
          f"{n_suppressed} suppressed (WEAK_ANALOG)")

    # Build artifact
    artifact = {
        "schema_version": 1,
        "capability": "nearest_analog",
        "recipe_id": args.recipe_id,
        "evaluation_year": args.evaluation_year,
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "binding_provenance": {
            "spec": "docs/specs/internal/ops/ml-track/te-new-capabilities-spec.md §2",
            "m8_r5": "M8-R5 discrimination/similarity layer; never calibrated point-probability",
            "analog_floor_pre_registered": args.analog_floor,
            "top_k": args.top_k,
            "z_score_logic": (
                "Per-positive pre-event z-trajectories extracted with IDENTICAL logic "
                "as build_canonical_profile_from_walk in compute_recipe_country_similarity.py: "
                "window ending event_year-1; panel-wide z-score at event_year-1 "
                "(per-country fallback when <10 countries in panel)."
            ),
        },
        "m8_r5_note": M8_R5_NOTE,
        "selected_indicators": selected_indicators,
        "chosen_window": chosen_window,
        "shap_importance_normalized": shap_weights,
        "n_scored_countries": n_total,
        "n_positives_used": len(positives_traj),
        "n_suppressed_weak_analog": n_suppressed,
        "analog_floor": args.analog_floor,
        "results": results,
    }

    out_path = args.output_dir / f"nearest-analog-{args.recipe_id}-{args.evaluation_year}.json"
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")

    # Print top-10 strongest analogs as sanity check
    print()
    print(f"=== Top-10 strongest analogs for {args.recipe_id} (eval_year={args.evaluation_year}) ===")
    country_best = [
        (c, r["best_weighted_cosine"], r["analogs"])
        for c, r in results.items()
        if r["best_weighted_cosine"] is not None and not r["suppressed"]
    ]
    country_best.sort(key=lambda t: t[1] or 0.0, reverse=True)
    for country, best_cos, analogs in country_best[:10]:
        top_analog = analogs[0] if analogs else None
        if top_analog:
            print(
                f"  {country:30s}  best_cos={best_cos:.4f}  "
                f"-> {top_analog['analog_country']} ({top_analog['analog_event_year']})"
                f"  same_cohort={top_analog['same_cohort']}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(_main())
