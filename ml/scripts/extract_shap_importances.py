"""Extract SHAP-derived per-indicator importances for risk-metric similarity weighting.

Per Miriam M14-R5 BINDING rider on the risk-metric design v1 (3-Reviewer ratified
2026-05-22): the country × recipe similarity pipeline MUST use SHAP-derived
importances, NOT raw XGBoost feature_importances_, because walk-3.1's
calibration failure (HARD_FAIL-CALIBRATION) means the XGBoost score-to-
probability mapping is broken. Raw feature_importances_ from a miscalibrated
model may not faithfully represent indicator importance for shape-matching.
SHAP values are less sensitive to calibration artifacts.

Per design v1 §"Indicator importance":
  1. Load the trained XGBoost model from walk-N (re-train deterministically
     from the walk's data + seed if model not cached).
  2. Compute SHAP values on the full positive-instance training set.
  3. For each indicator i: w_i^SHAP = mean(|SHAP[i, feature_j]|) summed
     across the 8 features per indicator (the F-ML-1 driver emits 8 features
     per indicator: last_z, mean_z, std_z, slope, accel, t1m, t2m, t3m).
  4. Normalize: w_i = w_i^SHAP / sum(w_j^SHAP).
  5. Output to JSON for consumption by compute_recipe_country_similarity.py.

Run-time: <1min laptop per recipe. Zero AWS.

Usage:
    python scripts/extract_shap_importances.py --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/qgi-rnd-002/f-ml-1-foreign-intervention-run/f-ml-1-poc-summary.json \\
        --output-dir qgi-data/reference/

Output:
    shap-importances-{recipe-id}.json
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

REPO_ROOT = SCRIPTS_DIR.parent


# Per F-ML-1 driver: each indicator emits 8 features in a fixed order:
#   [last_z, mean_z, std_z, slope, accel, tertile1_mean, tertile2_mean, tertile3_mean]
N_FEATURES_PER_INDICATOR = 8
FEATURE_NAMES = ["last_z", "mean_z", "std_z", "slope", "accel", "tertile1_mean", "tertile2_mean", "tertile3_mean"]


def reproduce_walk_training_data(walk_summary: dict, seed: int = 12345) -> tuple[np.ndarray, np.ndarray, list[str], int, list[str]]:
    """Reproduce the (X, y, selected_indicators, chosen_window, country_names_per_row)
    used in the walk's final XGBoost fit. Deterministic given the walk's seed +
    recipe-id + driver code (PR #91+#92 merged).

    Returns:
        X: (N, 8*k) feature matrix
        y: (N,) labels
        selected: list of k selected indicator IDs (matches walk-3.1 SHAP target)
        chosen_window: int W
        country_names: per-row country names (for cohort attribution if needed)
    """
    recipe_id = walk_summary["recipe_id"]
    selected = walk_summary["greedy_outer_loop"]["selected_indicators"]
    chosen_window = walk_summary["greedy_outer_loop"]["chosen_window"]

    # Reproduce positives + negatives with same seed (mirrors driver _main)
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
        y_pick = int(valid_years[rng.integers(0, len(valid_years))])
        if (c, y_pick) in pos_set:
            continue
        negs.append({"country": c, "year": y_pick, "label": 0})
    samples = pd.concat([pos[["country", "year", "label"]], pd.DataFrame(negs)], ignore_index=True)

    # Build X, y, countries via the driver helpers
    panels = {ind: drv.load_panel(ind, REPO_ROOT / "data" / "parquet_panels") for ind in selected}
    X, y, c, _yr = drv.build_X_y(samples, selected, chosen_window, panels)

    return X, y, selected, chosen_window, [str(x) for x in c.tolist()]


def compute_shap_importances(X: np.ndarray, y: np.ndarray, selected: list[str], seed: int = 12345) -> dict[str, Any]:
    """Refit XGBoost on full data + compute SHAP values + aggregate to per-indicator.

    The full-data refit matches the driver's descriptive-emit refit pattern.
    SHAP values are computed via TreeExplainer (exact, polynomial-time for trees).
    """
    import xgboost
    import shap as shap_lib

    X = np.where(np.isfinite(X), X, 0.0)

    # Full-data refit XGBoost (mirrors driver descriptive emit refit)
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    spw = (n_neg / max(n_pos, 1)) if n_pos > 0 else 1.0
    clf = xgboost.XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        reg_alpha=0.1,
        scale_pos_weight=spw, eval_metric="logloss",
        random_state=seed, verbosity=0, n_jobs=1,
    )
    clf.fit(X, y)

    # SHAP TreeExplainer
    explainer = shap_lib.TreeExplainer(clf)
    shap_values = explainer.shap_values(X)
    # Newer SHAP (>=0.40) may return Explanation object; older returns ndarray
    if hasattr(shap_values, "values"):
        shap_values = shap_values.values
    # For XGBoost binary classifier, shap_values shape is (N, n_features)
    assert shap_values.shape == X.shape, f"Unexpected SHAP shape: {shap_values.shape} vs X {X.shape}"

    # Aggregate to per-indicator: sum of mean(|SHAP|) across the 8 features per indicator
    n_features_total = X.shape[1]
    k = len(selected)
    assert n_features_total == N_FEATURES_PER_INDICATOR * k, (
        f"Expected {N_FEATURES_PER_INDICATOR * k} features, got {n_features_total}"
    )

    # Mean absolute SHAP per feature
    mean_abs_shap_per_feature = np.mean(np.abs(shap_values), axis=0)

    # Per-indicator: sum across the 8 features
    w_shap_per_indicator: dict[str, float] = {}
    per_feature_breakdown: dict[str, dict[str, float]] = {}
    for i, ind in enumerate(selected):
        feature_block = mean_abs_shap_per_feature[i * N_FEATURES_PER_INDICATOR : (i + 1) * N_FEATURES_PER_INDICATOR]
        w_shap_per_indicator[ind] = float(feature_block.sum())
        per_feature_breakdown[ind] = {
            FEATURE_NAMES[j]: float(feature_block[j]) for j in range(N_FEATURES_PER_INDICATOR)
        }

    # Normalize to sum to 1
    total = sum(w_shap_per_indicator.values())
    w_normalized: dict[str, float] = {}
    if total > 0:
        w_normalized = {k_: v / total for k_, v in w_shap_per_indicator.items()}
    else:
        # Fallback: uniform if all SHAP values are zero (degenerate)
        w_normalized = {k_: 1.0 / len(selected) for k_ in selected}

    # Direction sign per indicator: aggregate SHAP value sign (positive SHAP = pushes
    # toward positive class; negative = toward negative class). For similarity weighting,
    # the magnitude matters; direction is informational.
    mean_signed_shap_per_feature = np.mean(shap_values, axis=0)
    direction_signs: dict[str, int] = {}
    for i, ind in enumerate(selected):
        block_signed = mean_signed_shap_per_feature[i * N_FEATURES_PER_INDICATOR : (i + 1) * N_FEATURES_PER_INDICATOR]
        direction_signs[ind] = int(np.sign(block_signed.sum()))

    return {
        "selected_indicators": selected,
        "shap_importance_raw": w_shap_per_indicator,
        "shap_importance_normalized": w_normalized,
        "shap_direction_signs": direction_signs,
        "per_feature_breakdown": per_feature_breakdown,
        "n_samples_for_shap": int(X.shape[0]),
        "n_positives_in_sample": n_pos,
        "n_negatives_in_sample": n_neg,
        "shap_method": "TreeExplainer (exact, polynomial-time for XGBoost trees)",
        "model_refit": "full-data refit; mirrors F-ML-1 driver descriptive-emit refit pattern",
        "binding_rider_provenance": "Miriam M14-R5 BINDING (risk-metric design v1, 3-Reviewer ratified 2026-05-22)",
    }


def compare_to_raw_xgboost_importances(walk_summary: dict, shap_normalized: dict[str, float]) -> dict[str, Any]:
    """Compute side-by-side comparison: raw XGBoost feature_importances_ vs SHAP-derived.

    Per Miriam M14-R5: provides the disclosure that justifies the SHAP switch.
    """
    raw_emit = walk_summary["descriptive_emit"]["indicator_importance_profile"]
    raw_dict = {row["indicator_id"]: row["importance_mean_abs"] for row in raw_emit}
    # Normalize raw to sum to 1 for fair comparison
    raw_total = sum(raw_dict.values())
    raw_normalized = {k_: v / raw_total for k_, v in raw_dict.items()} if raw_total > 0 else raw_dict

    comparison = []
    for ind in shap_normalized:
        raw_w = raw_normalized.get(ind, 0.0)
        shap_w = shap_normalized[ind]
        delta = shap_w - raw_w
        comparison.append({
            "indicator_id": ind,
            "raw_xgboost_importance_normalized": float(raw_w),
            "shap_importance_normalized": float(shap_w),
            "delta_shap_minus_raw": float(delta),
        })
    comparison.sort(key=lambda r: -abs(r["delta_shap_minus_raw"]))

    return {
        "comparison_ranked_by_abs_delta": comparison,
        "interpretation_note": (
            "Per Miriam M14-R5 BINDING: deltas reveal how much the SHAP-derived "
            "importances differ from raw XGBoost feature_importances_. Large "
            "deltas indicate the calibration artifact affected the raw weights. "
            "SHAP is the binding weighting for the similarity metric."
        ),
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-id", required=True)
    parser.add_argument("--walk-summary", type=Path, required=True,
                        help="Path to walk's f-ml-1-poc-summary.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=12345,
                        help="Must match walk's seed for deterministic reproduction.")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.walk_summary, encoding="utf-8") as f:
        walk_summary = json.load(f)

    assert walk_summary["recipe_id"] == args.recipe_id, (
        f"Walk summary recipe_id {walk_summary['recipe_id']} != requested {args.recipe_id}"
    )

    print(f"Reproducing walk training data for {args.recipe_id} (seed={args.seed})...")
    X, y, selected, chosen_window, _countries = reproduce_walk_training_data(walk_summary, seed=args.seed)
    print(f"  X shape: {X.shape}; selected: {selected}; window: {chosen_window}y")

    print("Computing SHAP importances (TreeExplainer on full-data refit)...")
    shap_result = compute_shap_importances(X, y, selected, seed=args.seed)

    print("Comparing SHAP vs raw XGBoost feature_importances_ (Miriam M14-R5 disclosure)...")
    comparison = compare_to_raw_xgboost_importances(walk_summary, shap_result["shap_importance_normalized"])

    output = {
        "recipe_id": args.recipe_id,
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "walk_summary_reference": str(args.walk_summary),
        "seed_used": args.seed,
        "chosen_window_from_walk": chosen_window,
        "binding_rider_provenance": (
            "Miriam M14-R5 BINDING on risk-metric design v1 (3-Reviewer ratified 2026-05-22). "
            "SHAP-derived importances REPLACE raw XGBoost feature_importances_ for "
            "similarity-metric weighting due to walk-3.1 calibration failure indicating "
            "raw weights may be unreliable for shape-matching purposes."
        ),
        **shap_result,
        "raw_vs_shap_comparison": comparison,
    }

    out_path = args.output_dir / f"shap-importances-{args.recipe_id}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")

    # Print summary
    print()
    print(f"=== SHAP-normalized importances ({args.recipe_id}) ===")
    sorted_shap = sorted(shap_result["shap_importance_normalized"].items(), key=lambda x: -x[1])
    for ind, w in sorted_shap:
        sign = shap_result["shap_direction_signs"][ind]
        sign_label = "(+)" if sign > 0 else ("(-)" if sign < 0 else "(0)")
        print(f"  {ind}: w={w:.4f} {sign_label}")
    print()
    print("=== Top 3 SHAP-vs-raw deltas (Miriam M14-R5 disclosure) ===")
    for row in comparison["comparison_ranked_by_abs_delta"][:3]:
        print(f"  {row['indicator_id']}: raw={row['raw_xgboost_importance_normalized']:.4f}, "
              f"shap={row['shap_importance_normalized']:.4f}, "
              f"delta={row['delta_shap_minus_raw']:+.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
