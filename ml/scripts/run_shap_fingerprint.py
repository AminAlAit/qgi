"""Stage 2 Prereq D — SHAP attribution + indicator fingerprint per recipe.

Implements Component 8 prong 3 of `docs/specs/internal/ops/ml-track/
07-validation-framework.md` AND the ML-Opus-track "ML indicator
fingerprint" deliverable (= SHAP top-K per recipe head, per founder's
2026-05-04 question).

Loads the trained Stage 1 v0 tuned backbones from a results directory,
rebuilds the feature panel via the same pipeline used at training time
(so column order matches), runs LightGBM TreeSHAP on the test window,
and emits a per-recipe top-K fingerprint with within-country variance
annotations for fixed-effect-suspect detection.

Usage::

    python scripts/run_shap_fingerprint.py \
        --backbone-dir results/hp_sweep_5_30_2/backbone \
        --panel data/panel_104_2026_05_04.parquet \
        --train-year-max 2021 \
        --test-year-start 2022 \
        --test-year-end 2025 \
        --top-k 10 \
        --out ../qgi-data/reference/shap-fingerprint-2026-05.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SHARED_ROOT = REPO_ROOT / "shared"
for _p in (str(SRC_ROOT), str(SCRIPTS_ROOT), str(SHARED_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shap_fingerprint import (  # noqa: E402
    DEFAULT_TOP_K,
    aggregate_to_global_importance,
    annotate_top_k_with_variance,
    compute_feature_variance_from_wide,
    compute_treeshap_attribution,
    panel_median_variance,
    top_k_features,
)
# Reuse trainer's panel build to guarantee feature ordering match.
from train_multitask_v0 import build_feature_panel  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backbone-dir",
        type=Path,
        required=True,
        help="Directory containing .lgbm backbone files (one per recipe).",
    )
    parser.add_argument(
        "--panel",
        type=Path,
        default=REPO_ROOT / "data" / "panel_104_2026_05_04.parquet",
        help="Path to the indicator panel parquet.",
    )
    parser.add_argument(
        "--train-year-max",
        type=int,
        default=2021,
        help="Last training-window year (inclusive). Used for variance reference.",
    )
    parser.add_argument(
        "--test-year-start",
        type=int,
        default=2022,
        help="First test-window year (inclusive). SHAP is computed on this slice.",
    )
    parser.add_argument(
        "--test-year-end",
        type=int,
        default=2025,
        help="Last test-window year (inclusive).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Top-K features to report per recipe. Default: 10.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSON path.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-recipe progress output.",
    )
    return parser.parse_args()


def main() -> int:  # noqa: C901, PLR0915 — top-level orchestration is intentionally linear
    args = parse_args()

    if not args.backbone_dir.exists():
        print(f"ERROR: backbone-dir not found: {args.backbone_dir}", file=sys.stderr)
        return 2
    if not args.panel.exists():
        print(f"ERROR: panel not found: {args.panel}", file=sys.stderr)
        return 2

    import lightgbm as lgb

    print(f"Reading panel: {args.panel}", file=sys.stderr)
    panel_long = pd.read_parquet(args.panel)
    panel_long = panel_long.dropna(subset=["country", "year", "indicator_id"])
    panel_long["year"] = panel_long["year"].astype(int)

    # Build feature panel via the same pipeline the trainer used.
    # This applies first-difference + pivot_to_wide and produces a
    # DataFrame whose columns ARE the engineered features (e.g.,
    # `<indicator_id>__diff`). The model SEES this feature space, so
    # both SHAP attribution AND the variance reference must operate on
    # it -- mismatched spaces would make every annotation
    # "variance_unavailable".
    print("Rebuilding feature panel via trainer's build_feature_panel...", file=sys.stderr)
    feature_panel = build_feature_panel(args.panel, train_year_max=args.train_year_max)
    feature_columns = [c for c in feature_panel.columns if c not in ("country", "year")]
    print(f"  Feature panel columns: {len(feature_columns)}", file=sys.stderr)

    # Compute per-feature within-country std on engineered features over
    # the training window. Tariq's spec language: "indicators with time-
    # series variance below median panel variance ... proxy for country
    # fixed effects." On engineered first-difference features, an
    # essentially-constant raw indicator becomes a near-zero-variance
    # difference series -- exactly the fixed-effect proxy this audit
    # targets.
    print(
        f"Computing per-feature within-country std on engineered training "
        f"panel [..{args.train_year_max}]...",
        file=sys.stderr,
    )
    train_mask = feature_panel["year"] <= args.train_year_max
    variance_map_full = compute_feature_variance_from_wide(
        feature_panel[train_mask],
        feature_columns,
        window_start=int(feature_panel.loc[train_mask, "year"].min()),
        window_end=args.train_year_max,
    )
    panel_median = panel_median_variance(variance_map_full)
    print(f"  Panel median within-country std (engineered): {panel_median:.6g}", file=sys.stderr)

    # Slice to test window. The feature panel (after first-difference)
    # has all years; we want test-window rows for SHAP attribution.
    test_mask = (
        (feature_panel["year"] >= args.test_year_start)
        & (feature_panel["year"] <= args.test_year_end)
    )
    test_panel = feature_panel[test_mask].reset_index(drop=True)
    print(
        f"  Test panel: {len(test_panel)} rows in [{args.test_year_start}, "
        f"{args.test_year_end}]",
        file=sys.stderr,
    )

    if test_panel.empty:
        print("ERROR: no test-window rows after panel build.", file=sys.stderr)
        return 1

    X_test = test_panel[feature_columns].to_numpy(dtype=float)

    # Iterate recipes.
    backbone_files = sorted(args.backbone_dir.glob("*.lgbm"))
    if not backbone_files:
        print(f"ERROR: no .lgbm files in {args.backbone_dir}", file=sys.stderr)
        return 2

    recipes: dict[str, dict] = {}
    for booster_path in backbone_files:
        recipe_id = booster_path.stem
        if not args.quiet:
            print(f"  SHAP-attributing {recipe_id}...", file=sys.stderr)

        booster = lgb.Booster(model_file=str(booster_path))
        if booster.num_feature() != len(feature_columns):
            print(
                f"WARNING: feature-count mismatch for {recipe_id}: "
                f"booster has {booster.num_feature()}, panel has {len(feature_columns)}. "
                f"Skipping.",
                file=sys.stderr,
            )
            continue

        shap_values = compute_treeshap_attribution(booster, X_test)
        importance = aggregate_to_global_importance(shap_values, feature_columns)
        top_k_list = top_k_features(importance, k=args.top_k)
        annotated = annotate_top_k_with_variance(
            top_k_list, variance_map_full, panel_median=panel_median
        )

        suspect_count = sum(
            1 for r in annotated if r.get("fixed_effect_suspect") is True
        )

        recipes[recipe_id] = {
            "n_samples_explained": int(X_test.shape[0]),
            "n_features": len(feature_columns),
            "n_top_k_fixed_effect_suspect": suspect_count,
            "top_k": annotated,
        }

    portfolio_summary = {
        "n_recipes": len(recipes),
        "n_recipes_with_any_suspect_top_k_feature": sum(
            1 for r in recipes.values() if r["n_top_k_fixed_effect_suspect"] > 0
        ),
        "median_suspect_count_per_recipe": (
            float(np.median([r["n_top_k_fixed_effect_suspect"] for r in recipes.values()]))
            if recipes
            else 0.0
        ),
    }

    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Stage 2 Prereq D: SHAP attribution + ML indicator fingerprint "
            "per recipe (Component 8 prong 3 of "
            "docs/specs/internal/ops/ml-track/07-validation-framework.md). "
            "Diagnostic for country-fixed-effect contamination per "
            "Tariq Sufi-Younes' binding warning. Stage 2 walk reads this "
            "to investigate top-K features ranked top by SHAP that have "
            "low within-country temporal variance (= fixed-effect proxies)."
        ),
        "method": {
            "shap_method": "TreeSHAP via lightgbm.Booster.predict(pred_contrib=True)",
            "global_importance": "mean_abs_shap over explanation set",
            "explanation_set": "test window predictions (out-of-time)",
            "variance_reference": (
                "for each engineered feature, per-country std over training "
                "window, then median across countries. Computed on the SAME "
                "feature space the model sees (post-first-difference) so "
                "indicator IDs match the SHAP top-K labels."
            ),
            "fixed_effect_suspect_threshold": (
                "indicator within_country_std_median < panel_median_within_country_std"
            ),
        },
        "policy": {
            "no_alpha_binarization": True,
            "no_bh_fdr_correction": True,
            "diagnostic_only_not_a_gate": True,
            "no_bh_fdr_note": (
                "QGI hard-veto per Kwame Adjei; raw mean_abs_shap values "
                "only; downstream consumers must not apply correction."
            ),
        },
        "training_window": {
            "year_min": int(panel_long["year"].min()),
            "year_max": int(args.train_year_max),
        },
        "test_window": {
            "year_min": args.test_year_start,
            "year_max": args.test_year_end,
        },
        "panel": {
            "path": str(args.panel.resolve()),
            "n_features_after_engineering": len(feature_columns),
            "n_indicators_with_variance_reference": len(variance_map_full),
            "panel_median_within_country_std": panel_median,
        },
        "portfolio_summary": portfolio_summary,
        "recipes": recipes,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}", file=sys.stderr)
    print(f"Portfolio summary: {portfolio_summary}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
