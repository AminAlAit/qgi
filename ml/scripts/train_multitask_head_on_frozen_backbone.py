"""# THROWAWAY -- one-off training script. Phase D D2 part 2: trains
the MultiTaskHead on top of the frozen Stage 1 v0 tuned backbone and
emits a new predictions JSON for downstream LOCO regression testing.

Per docs/specs/internal/ops/ml-track/stage-2-amendment-2026-05-05.md
(commit `04fa5fb`) D2 -- Priya Venkataraman-Szabo's recommendation
at the post-PoC trio convening 2026-05-05.

Pipeline:
1. Load Stage 1 v0 tuned backbones (all 23 .lgbm; FROZEN)
2. Build feature panel via build_feature_panel
3. Load labels for all 23 recipes
4. Merge + OOS-by-time split (train ≤ 2021, test 2022-2025)
5. Extract leaf features via extract_leaf_features (cross-recipe)
6. One-hot encode (fit on train)
7. Stratified 80/20 train/cal split
8. Fit MultiTaskHead on 80% (cal-fold as val for early stopping)
9. Predict on test set; emit predictions.json (Stage 1 v0 schema)

Output: results/d2_multitask_2026_05/predictions.json -- consumable
by the existing LOCO diagnostic script and validate_ml_model.py.

Usage::

    python scripts/train_multitask_head_on_frozen_backbone.py \\
        --backbone-dir results/hp_sweep_5_30_2/backbone \\
        --panel data/panel_104_2026_05_04.parquet \\
        --events-dir ../qgi-data/events/curated \\
        --rubric ../qgi-data/reference/ml-recipe-ranking-2026-05.json \\
        --output-dir results/d2_multitask_2026_05
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

from heads.multitask import MultiTaskHead, MultiTaskHeadConfig  # noqa: E402
from train_multitask_v0 import (  # noqa: E402
    build_feature_panel,
    extract_leaf_features,
    load_event_labels,
    load_priority_recipes,
)
from walk.calibrate import stratified_train_cal_split  # noqa: E402

LABEL_WINDOW_LOWER = 2014
TRAIN_YEAR_MAX = 2021
TEST_YEAR_MIN = 2022
TEST_YEAR_MAX = 2025
DEFAULT_SEED = 0
CAL_FOLD_SIZE = 0.20


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backbone-dir", type=Path, required=True)
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--events-dir", type=Path, required=True)
    p.add_argument("--rubric", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--max-epochs", type=int, default=100)
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def _log(msg: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(msg, file=sys.stderr)


def main() -> int:  # noqa: PLR0915, C901
    args = parse_args()

    # 1. Recipes
    recipes = load_priority_recipes(args.rubric, recipe_filter=None)
    recipe_ids = [r["category_id"] for r in recipes]
    _log(f"[d2-train] eligible recipes: {len(recipe_ids)}", quiet=args.quiet)

    # 2. Backbones
    import lightgbm as lgb
    backbone_paths = sorted(args.backbone_dir.glob("*.lgbm"))
    boosters = [lgb.Booster(model_file=str(p)) for p in backbone_paths]
    backbone_recipe_ids = [p.stem for p in backbone_paths]
    _log(f"[d2-train] loaded {len(boosters)} backbones", quiet=args.quiet)

    # Restrict recipe_ids to those with backbones
    recipe_ids = [r for r in recipe_ids if r in backbone_recipe_ids]
    _log(f"[d2-train] after backbone-availability filter: {len(recipe_ids)}", quiet=args.quiet)

    # 3. Labels
    _log("[d2-train] loading event labels...", quiet=args.quiet)
    label_window = (LABEL_WINDOW_LOWER, TEST_YEAR_MAX)
    labels = load_event_labels(args.events_dir, recipe_ids, label_window, verified_only=True)
    label_wide = labels.pivot_table(
        index=["country", "year"], columns="recipe_id", values="label", aggfunc="first",
    ).reset_index()
    label_wide.columns.name = None

    # 4. Feature panel
    _log("[d2-train] building feature panel...", quiet=args.quiet)
    feature_panel = build_feature_panel(args.panel, train_year_max=TRAIN_YEAR_MAX)

    # 5. Merge + OOS-by-time split
    merged = feature_panel.merge(label_wide, on=["country", "year"], how="inner")

    train_mask = merged["year"] <= TRAIN_YEAR_MAX
    test_mask = (merged["year"] >= TEST_YEAR_MIN) & (merged["year"] <= TEST_YEAR_MAX)
    train_df = merged[train_mask].reset_index(drop=True)
    test_df = merged[test_mask].reset_index(drop=True)

    label_cols = [c for c in recipe_ids if c in merged.columns]
    feature_cols = [c for c in merged.columns if c not in ("country", "year") and c not in label_cols]

    X_train = train_df[feature_cols].to_numpy(dtype=float)
    X_test = test_df[feature_cols].to_numpy(dtype=float)
    Y_train = train_df[label_cols].fillna(0).to_numpy(dtype=int)
    Y_test = test_df[label_cols].fillna(0).to_numpy(dtype=int)
    _log(f"[d2-train] train={len(train_df)}, test={len(test_df)}, "
         f"K={len(label_cols)}", quiet=args.quiet)

    # 6. Leaf features
    _log("[d2-train] extracting leaf features...", quiet=args.quiet)
    leaf_train = extract_leaf_features(boosters, X_train)
    leaf_test = extract_leaf_features(boosters, X_test)
    _log(f"[d2-train] leaf shape: train={leaf_train.shape}, test={leaf_test.shape}", quiet=args.quiet)

    # 7. One-hot encode
    from sklearn.preprocessing import OneHotEncoder
    encoder = OneHotEncoder(categories="auto", sparse_output=False, handle_unknown="ignore")
    encoder.fit(leaf_train)
    leaf_train_oh = encoder.transform(leaf_train).astype(np.float32)
    leaf_test_oh = encoder.transform(leaf_test).astype(np.float32)
    _log(f"[d2-train] one-hot shape: train={leaf_train_oh.shape}", quiet=args.quiet)

    # 8. Stratified 80/20 split (use first label column for stratification — proxy)
    # Multi-task split: use the recipe with most positives as the stratification anchor
    n_pos_per_recipe = Y_train.sum(axis=0)
    anchor_recipe_idx = int(np.argmax(n_pos_per_recipe))
    train_idx, cal_idx = stratified_train_cal_split(
        Y_train[:, anchor_recipe_idx],
        cal_size=CAL_FOLD_SIZE,
        seed=args.seed,
    )
    _log(f"[d2-train] stratification anchor: {label_cols[anchor_recipe_idx]} "
         f"(n_pos={int(n_pos_per_recipe[anchor_recipe_idx])})", quiet=args.quiet)
    _log(f"[d2-train] train fold n={len(train_idx)}, cal fold n={len(cal_idx)}",
         quiet=args.quiet)

    # 9. Fit MultiTaskHead
    _log("[d2-train] fitting multi-task head...", quiet=args.quiet)
    head = MultiTaskHead(
        config=MultiTaskHeadConfig(seed=args.seed, max_epochs=args.max_epochs),
        n_recipes=len(label_cols),
    )
    head.fit(
        leaf_train_oh[train_idx], Y_train[train_idx],
        X_val=leaf_train_oh[cal_idx], Y_val=Y_train[cal_idx],
    )
    _log(f"[d2-train] training complete; "
         f"epochs run = {len(head._train_history)}", quiet=args.quiet)

    # 10. Predict on test
    _log("[d2-train] predicting on test set...", quiet=args.quiet)
    raw_preds_test = head.predict_proba(leaf_test_oh)  # (n_test, K)

    # 11. Emit predictions.json (Stage 1 v0 schema)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions: list[dict] = []
    for i, row in enumerate(test_df.itertuples(index=False)):
        for k, rid in enumerate(label_cols):
            predictions.append({
                "country": str(row.country),
                "year": int(row.year),
                "recipe_id": rid,
                "predicted_probability": float(raw_preds_test[i, k]),
                "label": int(Y_test[i, k]),
            })
    payload = {
        "schema_version": 1,
        "model_metadata_uri": str(output_dir),
        "predictions": predictions,
        "metadata": {
            "model_kind": "multitask_head_d2_on_frozen_v0_backbone",
            "head_config": {
                "hidden_dims": list(MultiTaskHeadConfig().hidden_dims),
                "max_epochs": args.max_epochs,
                "early_stop_patience": MultiTaskHeadConfig().early_stop_patience,
                "seed": args.seed,
            },
            "n_train": int(len(train_idx)),
            "n_cal": int(len(cal_idx)),
            "n_test": int(len(test_df)),
            "n_recipes": len(label_cols),
            "input_dim": int(leaf_train_oh.shape[1]),
            "stratification_anchor": label_cols[anchor_recipe_idx],
            "pre_reg_amendment_commit": "04fa5fb",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    }
    out_path = output_dir / "predictions.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _log(f"[d2-train] wrote {out_path} ({len(predictions)} prediction rows)",
         quiet=args.quiet)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
