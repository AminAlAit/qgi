"""Validate the country × recipe similarity pipeline against design v1 requirements.

Runs 4 validations per the risk-metric design v1 (3-Reviewer ratified 2026-05-22):

1. **Validation 1 (HARD GATE — M8-R3 publication requirement)**: positive-instance
   recall — median similarity of crisis countries at event-year-minus-1 vs
   non-event countries at same year. HARD GATE: ≥ 20 percentile points separation.

2. **Validation 2 (RECOMMENDED)**: discrimination consistency — correlate similarity
   score with XGBoost-predicted probability. Strong positive correlation = defensible
   proxy.

3. **Validation 3 (RECOMMENDED)**: risk-landscape coherence — per-cohort distribution
   reporting (transparency, not gate per ML/stats synthesis).

4. **Validation 4 (HARD GATE — pre-frontend-flip)**: OOT holdout — train/test
   temporal split [pre-2005] / [2005-2021]. OOT positive-recall ≥ 60% at HIGH
   threshold (risk ≥ 65) at event-year-minus-1.

Run-time: <5min laptop per recipe.

Usage:
    python scripts/validate_similarity_pipeline.py \\
        --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --shap-importances qgi-data/reference/shap-importances-foreign_intervention.json \\
        --output-dir qgi-data/reference/

Outputs:
    similarity-validations-{recipe-id}.json   (all 4 validation results)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402
import compute_recipe_country_similarity as sim  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent


# Per design v1 §"Validation 1": HARD GATE = ≥ 20 percentile points separation
V1_HARD_GATE_PERCENTILE_GAP = 20

# Per design v1 §"Validation 4": HARD GATE = ≥ 60% OOT positive recall at HIGH threshold
V4_HARD_GATE_RECALL = 0.60
V4_OOT_SPLIT_YEAR = 2005

# HIGH zone threshold
HIGH_ZONE_THRESHOLD = 65


def load_panels(selected: list[str], panel_dir: Path) -> dict:
    return {ind: drv.load_panel(ind, panel_dir) for ind in selected}


def load_cohort_assignments() -> dict:
    with open(REPO_ROOT.parent / "qgi-data" / "reference" / "cohort-assignments.json", encoding="utf-8") as f:
        return json.load(f)["assignments"]


# ---- Validation 1: positive-instance recall (HARD GATE) -----------------


def validation_1_positive_recall(walk: dict, panels: dict, shap_weights: dict, recipe_canonical: dict,
                                  z_dist: dict, selected: list[str], chosen_window: int) -> dict:
    """Compute median similarity at event-year-minus-1 for positive vs non-event countries.

    HARD GATE per M8-R3: ≥ 20 percentile points separation.
    """
    recipe_id = walk["recipe_id"]
    pos = pd.read_csv(REPO_ROOT / "data" / "shape_inputs_v2" / recipe_id / "positives.csv")
    pos["country"] = pos["country_id"].apply(drv.normalize_country_id)
    pos = pos.rename(columns={"event_year": "year"})
    pos_set = set(zip(pos["country"].tolist(), pos["year"].tolist()))

    # Compute similarity at event-year-minus-1 for each positive
    # Per QA PR#95 B1 BLOCKING fix: explicitly skip incomplete-coverage samples
    # (matches production path; prevents weight-renormalization inflation)
    pos_scores = []
    n_pos_skipped_partial_coverage = 0
    for _, row in pos.iterrows():
        country = str(row["country"])
        eval_year = int(row["year"])  # event year (compute at event_year-1 via window pre-event)
        # The trajectory extraction uses years [eval_year-W, eval_year-1] which is the W years BEFORE the event
        country_traj = {ind: sim.extract_country_trajectory(panels[ind], country, eval_year, chosen_window,
                                                              ind_dist=z_dist[ind])
                        for ind in selected}
        # B1 BLOCKING fix: require FULL indicator coverage; skip otherwise
        if any(t is None for t in country_traj.values()):
            n_pos_skipped_partial_coverage += 1
            continue
        result = sim.compute_country_recipe_similarity(country_traj, recipe_canonical, shap_weights)
        pos_scores.append(result["risk_score"])

    # Non-event countries (sample from panel countries not in pos_set, at random years)
    all_panel_countries = set()
    for ind in selected:
        all_panel_countries |= set(panels[ind]["country"].dropna().unique())
    rng = np.random.default_rng(42)
    non_event_scores = []
    valid_years = list(range(1980, 2023))
    n_samples = len(pos_scores) * 3  # 3:1 negative sampling like walk
    attempts = 0
    while len(non_event_scores) < n_samples and attempts < n_samples * 5:
        attempts += 1
        country = list(all_panel_countries)[rng.integers(0, len(all_panel_countries))]
        year = int(valid_years[rng.integers(0, len(valid_years))])
        if (country, year) in pos_set:
            continue
        country_traj = {ind: sim.extract_country_trajectory(panels[ind], country, year, chosen_window,
                                                              ind_dist=z_dist[ind])
                        for ind in selected}
        if any(t is None for t in country_traj.values()):
            continue
        result = sim.compute_country_recipe_similarity(country_traj, recipe_canonical, shap_weights)
        non_event_scores.append(result["risk_score"])

    pos_median = float(np.median(pos_scores)) if pos_scores else float("nan")
    non_event_median = float(np.median(non_event_scores)) if non_event_scores else float("nan")
    separation = pos_median - non_event_median

    hard_gate_pass = separation >= V1_HARD_GATE_PERCENTILE_GAP

    return {
        "name": "validation_1_positive_instance_recall",
        "n_positive_evaluated": len(pos_scores),
        "n_positive_skipped_partial_coverage": n_pos_skipped_partial_coverage,
        "n_non_event_sampled": len(non_event_scores),
        "median_similarity_positive_at_eventY-1": pos_median,
        "median_similarity_non_event": non_event_median,
        "separation_percentile_points": separation,
        "hard_gate_threshold": V1_HARD_GATE_PERCENTILE_GAP,
        "hard_gate_pass": bool(hard_gate_pass),
        "b1_fix_applied": "QA PR#95 B1: partial-coverage samples explicitly skipped (no weight-renorm inflation)",
        "m8_r3_publication_anchor": (
            f"In the training panel, the median similarity score of countries one year before "
            f"{walk['recipe_id']} events was {pos_median:.1f}/100; the median for non-event "
            f"countries was {non_event_median:.1f}/100. Separation = {separation:.1f} points."
        ),
    }


# ---- Validation 2: XGBoost correlation -----------------------------------


def validation_2_xgboost_correlation(walk: dict, panels: dict, shap_weights: dict, recipe_canonical: dict,
                                      z_dist: dict, selected: list[str], chosen_window: int, seed: int = 12345) -> dict:
    """Correlate similarity scores with XGBoost-predicted probabilities on the same (country, year) pairs."""
    recipe_id = walk["recipe_id"]
    # Reproduce walk training (X, y, countries, years)
    import compute_recipe_country_similarity as cs  # noqa
    pos = pd.read_csv(REPO_ROOT / "data" / "shape_inputs_v2" / recipe_id / "positives.csv")
    pos["country"] = pos["country_id"].apply(drv.normalize_country_id)
    pos = pos.rename(columns={"event_year": "year"})
    pos["label"] = 1
    rng = np.random.default_rng(seed)
    pos_set = set(zip(pos["country"], pos["year"]))
    pos_countries = list(pos["country"].unique())
    valid_years = list(range(1980, 2023))
    n_neg_target = len(pos) * 3
    negs = []
    attempts = 0
    while len(negs) < n_neg_target and attempts < n_neg_target * 10:
        attempts += 1
        c = pos_countries[rng.integers(0, len(pos_countries))]
        y_ = int(valid_years[rng.integers(0, len(valid_years))])
        if (c, y_) in pos_set:
            continue
        negs.append({"country": c, "year": y_, "label": 0})
    samples = pd.concat([pos[["country", "year", "label"]], pd.DataFrame(negs)], ignore_index=True)

    X, y, c_arr, yr_arr = drv.build_X_y(samples, selected, chosen_window, panels)
    res = drv.fit_predict_loco(X, y, c_arr, yr_arr, architecture="XGBoost", seed=seed)
    xgb_probs = res["probs"]
    countries = res["countries"]
    years = res["years"]

    # Compute similarity for each (country, year) in res
    sim_scores = []
    matched_xgb_probs = []
    for i in range(len(xgb_probs)):
        country = str(countries[i])
        year = int(years[i])
        country_traj = {ind: sim.extract_country_trajectory(panels[ind], country, year, chosen_window,
                                                              ind_dist=z_dist[ind])
                        for ind in selected}
        if any(t is None for t in country_traj.values()):
            continue
        result = sim.compute_country_recipe_similarity(country_traj, recipe_canonical, shap_weights)
        sim_scores.append(result["risk_score"])
        matched_xgb_probs.append(float(xgb_probs[i]))

    if len(sim_scores) < 10:
        return {"name": "validation_2_xgboost_correlation", "skipped": True, "reason": "fewer than 10 matched pairs"}

    sim_arr = np.array(sim_scores)
    xgb_arr = np.array(matched_xgb_probs)
    pearson = float(np.corrcoef(sim_arr, xgb_arr)[0, 1])
    from scipy.stats import spearmanr
    spearman, _p = spearmanr(sim_arr, xgb_arr)

    return {
        "name": "validation_2_xgboost_correlation",
        "n_matched_pairs": len(sim_scores),
        "pearson_correlation": pearson,
        "spearman_correlation": float(spearman),
        "interpretation": (
            f"Pearson r = {pearson:.3f}, Spearman ρ = {spearman:.3f}. Positive correlation "
            f"indicates similarity is a defensible proxy for the XGBoost discriminator. "
            f"Strong (>0.6) is good; moderate (0.3-0.6) is acceptable; weak (<0.3) warrants review."
        ),
    }


# ---- Validation 3: risk-landscape coherence (per-cohort) ----------------


def validation_3_risk_landscape(walk: dict, panels: dict, shap_weights: dict, recipe_canonical: dict,
                                  z_dist: dict, selected: list[str], chosen_window: int, evaluation_year: int = 2021) -> dict:
    """Compute per-cohort similarity distributions for transparency."""
    cohort_assignments = load_cohort_assignments()
    all_panel_countries = set()
    for ind in selected:
        all_panel_countries |= set(panels[ind]["country"].dropna().unique())

    cohort_scores: dict[str, list[float]] = {"fragile-state": [], "mid-tier": [], "stable-democracy": [], "no-assignment": []}
    for country in all_panel_countries:
        country_traj = {ind: sim.extract_country_trajectory(panels[ind], country, evaluation_year, chosen_window,
                                                              ind_dist=z_dist[ind])
                        for ind in selected}
        if any(t is None for t in country_traj.values()):
            continue
        result = sim.compute_country_recipe_similarity(country_traj, recipe_canonical, shap_weights)
        cohort = cohort_assignments.get(country, {}).get(str(evaluation_year))
        if cohort in {"fragile-state", "mid-tier", "stable-democracy"}:
            cohort_scores[cohort].append(result["risk_score"])
        else:
            cohort_scores["no-assignment"].append(result["risk_score"])

    stats = {}
    for cohort, scores in cohort_scores.items():
        if len(scores) == 0:
            stats[cohort] = {"n": 0}
            continue
        stats[cohort] = {
            "n": len(scores),
            "median": float(np.median(scores)),
            "mean": float(np.mean(scores)),
            "q25": float(np.percentile(scores, 25)),
            "q75": float(np.percentile(scores, 75)),
            "max": float(np.max(scores)),
            "min": float(np.min(scores)),
        }

    return {
        "name": "validation_3_risk_landscape_per_cohort",
        "evaluation_year": evaluation_year,
        "cohort_distributions": stats,
        "interpretation": (
            "Per-cohort similarity distributions (Validation 3 per ML/stats synthesis). "
            "For domain-coherent risk landscape: fragile-state cohort should show higher "
            "median + max similarity to political-violence recipes than stable-democracy. "
            "Reporting only — NOT a gate at v0."
        ),
    }


# ---- Validation 4: OOT holdout (HARD GATE) ------------------------------


def validation_4_oot_holdout(walk: dict, panels: dict, shap_weights: dict, recipe_canonical: dict,
                              z_dist: dict, selected: list[str], chosen_window: int) -> dict:
    """OOT holdout: split positives into pre-2005 (train) and 2005+ (holdout).
    Check if holdout positives have HIGH similarity at event-year-minus-1.

    HARD GATE per ML/stats synthesis: ≥ 60% recall at HIGH threshold (risk ≥ 65).
    """
    recipe_id = walk["recipe_id"]
    pos = pd.read_csv(REPO_ROOT / "data" / "shape_inputs_v2" / recipe_id / "positives.csv")
    pos["country"] = pos["country_id"].apply(drv.normalize_country_id)
    pos = pos.rename(columns={"event_year": "year"})

    holdout = pos[pos["year"] >= V4_OOT_SPLIT_YEAR]
    print(f"  OOT holdout split: {len(holdout)} positives at year >= {V4_OOT_SPLIT_YEAR} (of {len(pos)} total)")

    # Per QA PR#95 B2 BLOCKING fix: rebuild canonical profile from PRE-2005 positives only.
    # The provided `recipe_canonical` was built from ALL positives (including 2005+), which would
    # make the OOT holdout an in-sample check for those events and bias the gate result optimistically.
    print(f"  Rebuilding canonical profile from PRE-{V4_OOT_SPLIT_YEAR} positives only (B2 fix)...")
    recipe_canonical_oot = sim.build_canonical_profile_from_walk(
        walk, panels, chosen_window, selected, max_year=V4_OOT_SPLIT_YEAR - 1
    )

    scores = []
    n_skipped = 0
    for _, row in holdout.iterrows():
        country = str(row["country"])
        event_year = int(row["year"])
        country_traj = {ind: sim.extract_country_trajectory(panels[ind], country, event_year, chosen_window,
                                                              ind_dist=z_dist[ind])
                        for ind in selected}
        # B1 fix: require FULL indicator coverage for honest OOT recall computation
        if any(t is None for t in country_traj.values()):
            n_skipped += 1
            continue
        # B2 fix: use the OOT-isolated canonical profile (rebuilt above from pre-2005 only)
        result = sim.compute_country_recipe_similarity(country_traj, recipe_canonical_oot, shap_weights)
        scores.append({
            "country": country,
            "event_year": event_year,
            "risk_score": result["risk_score"],
            "zone": result["zone"],
            "high_threshold_pass": bool(result["risk_score"] >= HIGH_ZONE_THRESHOLD),
        })

    n_high = sum(1 for s in scores if s["high_threshold_pass"])
    n_total = len(scores)
    recall = n_high / n_total if n_total > 0 else 0.0
    hard_gate_pass = recall >= V4_HARD_GATE_RECALL

    return {
        "name": "validation_4_oot_holdout",
        "oot_split_year": V4_OOT_SPLIT_YEAR,
        "n_holdout_positives": n_total,
        "n_holdout_skipped_partial_coverage": n_skipped,
        "n_at_or_above_high_threshold": n_high,
        "high_threshold_value": HIGH_ZONE_THRESHOLD,
        "recall_at_high_threshold": recall,
        "hard_gate_threshold": V4_HARD_GATE_RECALL,
        "hard_gate_pass": bool(hard_gate_pass),
        "b1_fix_applied": "QA PR#95 B1: partial-coverage samples explicitly skipped",
        "b2_fix_applied": (
            f"QA PR#95 B2: canonical profile rebuilt from pre-{V4_OOT_SPLIT_YEAR} positives only "
            f"(was previously using all positives including 2005+, which made the OOT 'holdout' "
            f"in-sample for those events and inflated the gate result optimistically). Genuine OOT."
        ),
        "interpretation": (
            f"OOT holdout: {n_high}/{n_total} = {100*recall:.1f}% of held-out crisis countries "
            f"had risk score >= {HIGH_ZONE_THRESHOLD} (HIGH zone) at event-year-minus-1, scored "
            f"against a canonical profile built ONLY from pre-{V4_OOT_SPLIT_YEAR} positives. "
            f"Hard gate threshold: {100*V4_HARD_GATE_RECALL:.0f}%. "
            f"{'PASS' if hard_gate_pass else 'FAIL'}."
        ),
        "per_event_details": scores[:20],  # First 20 for brevity
    }


# ---- Main orchestrator ---------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-id", required=True)
    parser.add_argument("--walk-summary", type=Path, required=True)
    parser.add_argument("--shap-importances", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--panel-dir", type=Path, default=REPO_ROOT / "data" / "parquet_panels")
    parser.add_argument("--evaluation-year", type=int, default=2021)
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.walk_summary, encoding="utf-8") as f:
        walk = json.load(f)
    assert walk["recipe_id"] == args.recipe_id

    with open(args.shap_importances, encoding="utf-8") as f:
        shap_data = json.load(f)
    shap_weights = shap_data["shap_importance_normalized"]
    selected = walk["greedy_outer_loop"]["selected_indicators"]
    chosen_window = walk["greedy_outer_loop"]["chosen_window"]

    print(f"Validation harness: {args.recipe_id} (window={chosen_window}y; indicators={selected})")
    panels = load_panels(selected, args.panel_dir)

    print("Pre-baking z-distribution + canonical profile...")
    z_dist = sim.prebake_zscore_distribution(args.panel_dir, selected, args.evaluation_year)
    recipe_canonical = sim.build_canonical_profile_from_walk(walk, panels, chosen_window, selected)

    print()
    print("=== Validation 1 (HARD GATE — M8-R3 publication) ===")
    v1 = validation_1_positive_recall(walk, panels, shap_weights, recipe_canonical, z_dist, selected, chosen_window)
    print(f"  pos_median={v1['median_similarity_positive_at_eventY-1']:.1f}, non_event_median={v1['median_similarity_non_event']:.1f}")
    print(f"  separation={v1['separation_percentile_points']:.1f}, gate={V1_HARD_GATE_PERCENTILE_GAP}, PASS={v1['hard_gate_pass']}")

    print()
    print("=== Validation 2 (RECOMMENDED — XGBoost correlation) ===")
    v2 = validation_2_xgboost_correlation(walk, panels, shap_weights, recipe_canonical, z_dist, selected, chosen_window)
    if v2.get("skipped"):
        print(f"  SKIPPED: {v2.get('reason')}")
    else:
        print(f"  n_pairs={v2['n_matched_pairs']}, Pearson={v2['pearson_correlation']:.3f}, Spearman={v2['spearman_correlation']:.3f}")

    print()
    print("=== Validation 3 (RECOMMENDED — risk landscape per-cohort) ===")
    v3 = validation_3_risk_landscape(walk, panels, shap_weights, recipe_canonical, z_dist, selected, chosen_window,
                                       evaluation_year=args.evaluation_year)
    for cohort, st in v3["cohort_distributions"].items():
        if st.get("n", 0) > 0:
            print(f"  {cohort:18s} n={st['n']:3d} median={st['median']:.1f} max={st['max']:.1f}")

    print()
    print("=== Validation 4 (HARD GATE — OOT holdout pre-frontend-flip) ===")
    v4 = validation_4_oot_holdout(walk, panels, shap_weights, recipe_canonical, z_dist, selected, chosen_window)
    print(f"  recall@HIGH={100*v4['recall_at_high_threshold']:.1f}%, gate={100*V4_HARD_GATE_RECALL:.0f}%, PASS={v4['hard_gate_pass']}")

    # Compose summary
    output = {
        "schema_version": 1,
        "recipe_id": args.recipe_id,
        "evaluation_year": args.evaluation_year,
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "design_v1_reference": "docs/specs/internal/ops/ml-track/risk-metric-design-v1.md (3-Reviewer ratified 2026-05-22)",
        "hard_gates_pass": {
            "v1_positive_recall": bool(v1["hard_gate_pass"]),
            "v4_oot_holdout": bool(v4["hard_gate_pass"]),
        },
        "all_hard_gates_pass": bool(v1["hard_gate_pass"] and v4["hard_gate_pass"]),
        "production_graduation_eligible": bool(v1["hard_gate_pass"] and v4["hard_gate_pass"]),
        "validations": {
            "v1": v1,
            "v2": v2,
            "v3": v3,
            "v4": v4,
        },
    }

    out_path = args.output_dir / f"similarity-validations-{args.recipe_id}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_path}")
    print(f"\nProduction graduation eligible: {output['production_graduation_eligible']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
