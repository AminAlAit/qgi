"""Stage 2 walk-runner: walks ONE recipe end-to-end.

Per pre-registration `docs/specs/internal/ops/ml-track/
stage-2-walk-prereg-elections-v2.md` (commit `d321fde`, supersedes
v1 `dae7741`). v2 locks forward-1y label semantics for both
DeepHit-lite + LR baseline.

Pipeline:
1. Load rubric metadata for `--recipe-id`
2. Load Stage 1 frozen backbones from `--backbone-dir` (all 23 .lgbm)
3. Build engineered feature panel via trainer's `build_feature_panel`
4. Load event labels for the recipe; pivot to (country, year) → label
5. Merge features + labels; OOS-by-time split (train ≤ 2021, test 2022-2025)
6. Extract leaf features via trainer's `extract_leaf_features`
7. One-hot encode leaf features (fit on train)
8. Build forward targets (Y, mask) for max_horizon=4
9. Stratified 80/20 train/cal split (LOCKED in pre-reg §3)
10. Fit DeepHit-lite head on 80% (with 20% as val for early stopping)
11. Fit Stage 1 LR baseline head on the same 80% (for verdict-gate comparison)
12. Predict on cal-fold; fit isotonic on collapsed cumulative incidence
13. Predict on test window; apply isotonic
14. Compute F1 (ECE), F2 (AUC + bootstrap CI), F3 (hazard band)
15. Compute baseline comparison (DeepHit vs Stage 1 LR on test)
16. Decide verdict: LOCKED / FALSIFIED / F5_FALLBACK
17. Write outputs:
    - `predictions.json` — calibrated test predictions
    - `walk_metadata.json` — all metrics + verdict + replication signature
    - `walk_report.md` — per-recipe markdown (per pre-reg §10 format)

Usage::

    python scripts/walk_recipe.py \
        --recipe-id elections_and_voting \
        --backbone-dir results/hp_sweep_5_30_2/backbone \
        --panel data/panel_104_2026_05_04.parquet \
        --events-dir ../qgi-data/events/curated \
        --rubric ../qgi-data/reference/ml-recipe-ranking-2026-05.json \
        --output-dir results/walks \
        --pre-reg-commit dae7741
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

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SHARED_ROOT = REPO_ROOT / "shared"
for _p in (str(SRC_ROOT), str(SCRIPTS_ROOT), str(SHARED_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from heads.deephit_lite import (  # noqa: E402
    DeepHitLiteConfig,
    DeepHitLiteHead,
    build_forward_targets,
)
from train_multitask_v0 import build_feature_panel, extract_leaf_features, load_event_labels  # noqa: E402
from walk.calibrate import IsotonicCalibrator, stratified_train_cal_split  # noqa: E402
from walk.falsification import (  # noqa: E402
    decide_verdict,
    evaluate_baseline_comparison,
    evaluate_f1,
    evaluate_f2,
    evaluate_f3,
)
from walk.report import render_walk_report  # noqa: E402

# Locked by pre-reg
LABEL_WINDOW_LOWER = 2014
TRAIN_YEAR_MAX = 2021
TEST_YEAR_MIN = 2022
TEST_YEAR_MAX = 2025
CAL_FOLD_SIZE = 0.20
WALK_SEED = 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recipe-id", required=True, help="Recipe to walk (e.g. elections_and_voting)")
    p.add_argument("--backbone-dir", type=Path, required=True, help="Stage 1 .lgbm backbones directory")
    p.add_argument("--panel", type=Path, required=True, help="Indicator panel parquet")
    p.add_argument("--events-dir", type=Path, required=True, help="qgi-data events curated directory")
    p.add_argument("--rubric", type=Path, required=True, help="Rubric ranking JSON")
    p.add_argument("--output-dir", type=Path, required=True, help="Walk output directory root")
    p.add_argument("--pre-reg-commit", required=True, help="Pre-reg docs-specs commit SHA (replication signature)")
    p.add_argument("--seed", type=int, default=WALK_SEED, help="Random seed (default 0)")
    p.add_argument("--n-bootstrap", type=int, default=1000, help="F2 bootstrap iterations")
    p.add_argument("--quiet", action="store_true", help="Suppress per-step progress output")
    return p.parse_args()


def _log(msg: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(msg, file=sys.stderr)


def main() -> int:  # noqa: PLR0915, C901 — top-level orchestration is intentionally linear
    args = parse_args()

    walk_run_id = datetime.now(tz=timezone.utc).strftime(
        f"%Y-%m-%dT%H%M%SZ_walk_{args.recipe_id}"
    )
    output_dir = args.output_dir / walk_run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    _log(f"[walk] run id: {walk_run_id}", quiet=args.quiet)
    _log(f"[walk] output: {output_dir}", quiet=args.quiet)

    # 1. Rubric metadata
    rubric = json.loads(args.rubric.read_text(encoding="utf-8"))
    rubric_entry = next(
        (r for r in rubric.get("ranking", []) if r.get("category_id") == args.recipe_id),
        None,
    )
    if rubric_entry is None:
        print(f"ERROR: recipe {args.recipe_id} not in rubric", file=sys.stderr)
        return 2
    _log(f"[walk] rubric rank={rubric_entry['rank']}, S(r)={rubric_entry['S']:.4f}, "
         f"F5={rubric_entry['F5']} ({rubric_entry['head_class']})", quiet=args.quiet)

    # 2. Backbones — all 23 (Stage 1 LR head used cross-recipe leaf features).
    import lightgbm as lgb  # noqa: PLC0415
    backbone_paths = sorted(args.backbone_dir.glob("*.lgbm"))
    boosters = [lgb.Booster(model_file=str(p)) for p in backbone_paths]
    backbone_recipe_ids = [p.stem for p in backbone_paths]
    if args.recipe_id not in backbone_recipe_ids:
        print(f"ERROR: recipe {args.recipe_id} not in backbone directory", file=sys.stderr)
        return 2
    _log(f"[walk] loaded {len(boosters)} backbones", quiet=args.quiet)

    # 3. Feature panel
    _log("[walk] building feature panel...", quiet=args.quiet)
    feature_panel = build_feature_panel(args.panel, train_year_max=TRAIN_YEAR_MAX)

    # 4. Labels — restrict to our recipe of interest + test window upper bound.
    _log("[walk] loading event labels...", quiet=args.quiet)
    label_window = (LABEL_WINDOW_LOWER, TEST_YEAR_MAX)
    labels = load_event_labels(
        args.events_dir, [args.recipe_id], label_window, verified_only=True,
    )
    label_wide = labels.pivot_table(
        index=["country", "year"], columns="recipe_id", values="label", aggfunc="first",
    ).reset_index()
    label_wide.columns.name = None

    # 5. Merge + OOS-by-time split + v2 forward-1y label join
    merged = feature_panel.merge(label_wide, on=["country", "year"], how="inner")
    if merged.empty:
        print("ERROR: empty feature+label merge; check country naming + year coverage", file=sys.stderr)
        return 2

    if args.recipe_id not in merged.columns:
        print(f"ERROR: label column {args.recipe_id} missing from merged frame", file=sys.stderr)
        return 2

    # v2 forward-1y label semantics per docs-specs commit d321fde:
    # - LR baseline + F-rules use label_{t+1} for row at year t
    # - DeepHit-lite already uses forward labels via build_forward_targets
    # - Test rows where label_{t+1} is unobservable (year t = TEST_YEAR_MAX) are EXCLUDED
    forward_label_col = f"{args.recipe_id}__forward1"
    shift_table = merged[["country", "year", args.recipe_id]].copy()
    shift_table["year"] = shift_table["year"] - 1  # so year_{t-1} carries label_{t}
    shift_table = shift_table.rename(columns={args.recipe_id: forward_label_col})
    merged = merged.merge(shift_table, on=["country", "year"], how="left")

    # Drop rows where forward label is unobservable (NaN). Train rows at
    # year=2021 keep observable forward labels (label_{2022}); test rows at
    # year=2025 are dropped (no label_{2026}).
    n_pre_drop = len(merged)
    merged = merged.dropna(subset=[forward_label_col]).reset_index(drop=True)
    merged[forward_label_col] = merged[forward_label_col].astype(int)
    _log(f"[walk] v2 forward-label filter: {n_pre_drop} -> {len(merged)} rows "
         f"(dropped {n_pre_drop - len(merged)} rows missing label_{{t+1}})", quiet=args.quiet)

    train_mask = merged["year"] <= TRAIN_YEAR_MAX
    test_mask = (merged["year"] >= TEST_YEAR_MIN) & (merged["year"] <= TEST_YEAR_MAX)
    train_df = merged[train_mask].reset_index(drop=True)
    test_df = merged[test_mask].reset_index(drop=True)

    feature_cols = [c for c in merged.columns
                    if c not in ("country", "year", args.recipe_id, forward_label_col)]
    X_train_features = train_df[feature_cols].to_numpy(dtype=float)
    X_test_features = test_df[feature_cols].to_numpy(dtype=float)
    # v1 labels (contemporaneous) — kept for reference / sample-count tracking
    y_train_label_v1 = train_df[args.recipe_id].fillna(0).astype(int).to_numpy()
    y_test_label_v1 = test_df[args.recipe_id].fillna(0).astype(int).to_numpy()
    # v2 labels (forward-1y) — used for training + F-rule evaluation
    y_train_label = train_df[forward_label_col].astype(int).to_numpy()
    y_test_label = test_df[forward_label_col].astype(int).to_numpy()
    _log(f"[walk] train={len(train_df)} rows, test={len(test_df)} rows, "
         f"n_features={len(feature_cols)}", quiet=args.quiet)
    _log(f"[walk] v2 forward labels: n_pos_train={int(y_train_label.sum())}, "
         f"n_pos_test={int(y_test_label.sum())} "
         f"(v1 contemp would have been: n_pos_train={int(y_train_label_v1.sum())}, "
         f"n_pos_test={int(y_test_label_v1.sum())})", quiet=args.quiet)

    # 6. Leaf features via Stage 1 trainer's helper
    _log("[walk] extracting leaf features (all 23 backbones)...", quiet=args.quiet)
    leaf_train = extract_leaf_features(boosters, X_train_features)
    leaf_test = extract_leaf_features(boosters, X_test_features)
    _log(f"[walk] leaf shape: train={leaf_train.shape}, test={leaf_test.shape}", quiet=args.quiet)

    # 7. One-hot encode (fit on train)
    from sklearn.preprocessing import OneHotEncoder  # noqa: PLC0415
    _log("[walk] one-hot encoding leaf indices...", quiet=args.quiet)
    encoder = OneHotEncoder(categories="auto", sparse_output=False, handle_unknown="ignore")
    encoder.fit(leaf_train)
    leaf_train_oh = encoder.transform(leaf_train).astype(np.float32)
    leaf_test_oh = encoder.transform(leaf_test).astype(np.float32)
    _log(f"[walk] one-hot shape: train={leaf_train_oh.shape}", quiet=args.quiet)

    # 8. Forward targets for DeepHit-lite (max_horizon=4)
    # IMPORTANT: pass the FULL merged frame's contemporaneous labels (not
    # the v2 forward column) -- build_forward_targets already shifts by t.
    # Use the contemporaneous label_{t} from the full merged frame so the
    # internal lookup can resolve label_{t+1}, label_{t+2}, etc., for
    # train rows up to TRAIN_YEAR_MAX. data_year_max=TRAIN_YEAR_MAX masks
    # bins where forward label would land in the test window (≥ 2022).
    _log("[walk] building forward targets...", quiet=args.quiet)
    Y_train_forward, mask_train_forward = build_forward_targets(
        train_df.assign(label=y_train_label_v1),  # contemp label for trainer's lookup
        country_col="country", year_col="year", label_col="label",
        max_horizon=DeepHitLiteConfig().max_horizon,
        data_year_max=TRAIN_YEAR_MAX,  # train fold cannot peek at test labels
    )

    # 9. Stratified 80/20 train/cal split (pre-reg §3)
    _log("[walk] splitting 80/20 train/cal-fold...", quiet=args.quiet)
    train_idx, cal_idx = stratified_train_cal_split(
        y_train_label, cal_size=CAL_FOLD_SIZE, seed=args.seed,
    )
    _log(f"[walk] train fold n={len(train_idx)} (n_pos={int(y_train_label[train_idx].sum())}), "
         f"cal fold n={len(cal_idx)} (n_pos={int(y_train_label[cal_idx].sum())})",
         quiet=args.quiet)

    # 10. Fit DeepHit-lite on 80% (with cal-fold as val for early stopping)
    _log("[walk] fitting DeepHit-lite head...", quiet=args.quiet)
    head = DeepHitLiteHead(config=DeepHitLiteConfig(seed=args.seed))
    head.fit(
        leaf_train_oh[train_idx], Y_train_forward[train_idx], mask_train_forward[train_idx],
        X_val=leaf_train_oh[cal_idx], Y_val=Y_train_forward[cal_idx],
        mask_val=mask_train_forward[cal_idx],
    )

    # 11. Fit Stage 1 LR baseline on the same 80% (verdict-gate comparison)
    _log("[walk] fitting Stage 1 LR baseline (for verdict-gate)...", quiet=args.quiet)
    from sklearn.linear_model import LogisticRegression  # noqa: PLC0415
    n_pos_train_fold = int(y_train_label[train_idx].sum())
    n_neg_train_fold = int((y_train_label[train_idx] == 0).sum())
    spw = (n_neg_train_fold / n_pos_train_fold) if n_pos_train_fold > 0 else 1.0
    baseline_lr = LogisticRegression(
        class_weight={0: 1.0, 1: spw},
        max_iter=1000,
        random_state=args.seed,
        solver="lbfgs",
    )
    # Stage 1 LR head consumes RAW integer leaf indices (not one-hot).
    baseline_lr.fit(leaf_train[train_idx], y_train_label[train_idx])

    # 12. Calibration on 20% cal-fold
    _log("[walk] fitting isotonic calibrator on cal-fold...", quiet=args.quiet)
    raw_cal_proba = head.predict_proba(leaf_train_oh[cal_idx])
    calibrator = IsotonicCalibrator().fit(raw_cal_proba, y_train_label[cal_idx])

    # 13. Predict on test
    _log("[walk] predicting on test window 2022-2025...", quiet=args.quiet)
    raw_test_proba = head.predict_proba(leaf_test_oh)
    calibrated_test_proba = calibrator.predict(raw_test_proba)
    baseline_test_proba = baseline_lr.predict_proba(leaf_test)[:, 1]

    # 14. F-rules
    _log("[walk] evaluating F1 / F2 / F3...", quiet=args.quiet)
    f1 = evaluate_f1(calibrated_test_proba, y_test_label)
    f2 = evaluate_f2(calibrated_test_proba, y_test_label, n_bootstrap=args.n_bootstrap, seed=args.seed)
    # F3 only applies to F5=3 (survival head) — which IS our case.
    f3 = evaluate_f3(calibrated_test_proba, y_test_label, seed=args.seed) \
        if rubric_entry.get("F5") == 3 else None

    # 15. Verdict-gate baseline comparison
    _log("[walk] computing verdict-gate vs Stage 1 LR baseline...", quiet=args.quiet)
    baseline_cmp = evaluate_baseline_comparison(
        calibrated_test_proba, baseline_test_proba, y_test_label,
    )

    # 16. Decide verdict
    verdict = decide_verdict(f1, f2, f3, baseline_cmp)
    _log(f"[walk] VERDICT: {verdict['verdict']} — {verdict['reason']}", quiet=args.quiet)

    # 17. Write outputs
    _write_outputs(
        output_dir=output_dir,
        recipe_id=args.recipe_id,
        rubric_entry=rubric_entry,
        test_df=test_df,
        calibrated_test_proba=calibrated_test_proba,
        raw_test_proba=raw_test_proba,
        baseline_test_proba=baseline_test_proba,
        y_test_label=y_test_label,
        train_idx=train_idx,
        cal_idx=cal_idx,
        y_train_label=y_train_label,
        f1=f1, f2=f2, f3=f3,
        baseline_cmp=baseline_cmp,
        verdict=verdict,
        head_train_history=head._train_history,
        calibrator=calibrator,
        encoder_n_features_out=int(leaf_train_oh.shape[1]),
        backbone_dir=str(args.backbone_dir),
        pre_reg_commit_sha=args.pre_reg_commit,
        walk_run_id=walk_run_id,
        seed=args.seed,
        n_bootstrap=args.n_bootstrap,
    )

    return 0


def _write_outputs(
    *,
    output_dir: Path,
    recipe_id: str,
    rubric_entry: dict,
    test_df: pd.DataFrame,
    calibrated_test_proba: np.ndarray,
    raw_test_proba: np.ndarray,
    baseline_test_proba: np.ndarray,
    y_test_label: np.ndarray,
    train_idx: np.ndarray,
    cal_idx: np.ndarray,
    y_train_label: np.ndarray,
    f1: dict,
    f2: dict,
    f3: dict | None,
    baseline_cmp: dict,
    verdict: dict,
    head_train_history: list[dict],
    calibrator: IsotonicCalibrator,
    encoder_n_features_out: int,
    backbone_dir: str,
    pre_reg_commit_sha: str,
    walk_run_id: str,
    seed: int,
    n_bootstrap: int,
) -> None:
    # predictions.json. Use enumerate over itertuples for sequential
    # numpy index (i=0..N-1) instead of iterrows() which yields the
    # pandas DataFrame index. QA review of PR #26 caught that the
    # iterrows pattern only works because reset_index(drop=True) was
    # called upstream; a future refactor could break that and silently
    # corrupt predictions.json by indexing wrong rows.
    predictions_payload = {
        "schema_version": 1,
        "recipe_id": recipe_id,
        "walk_run_id": walk_run_id,
        "horizon_eval_years": 1,
        "predictions": [
            {
                "country": str(row.country),
                "year": int(row.year),
                "recipe_id": recipe_id,
                "predicted_probability": float(calibrated_test_proba[i]),
                "raw_predicted_probability_pre_isotonic": float(raw_test_proba[i]),
                "stage1_lr_baseline_probability": float(baseline_test_proba[i]),
                "label": int(y_test_label[i]),
            }
            for i, row in enumerate(test_df.itertuples(index=False))
        ],
    }
    (output_dir / "predictions.json").write_text(
        json.dumps(predictions_payload, indent=2), encoding="utf-8",
    )

    # walk_metadata.json
    metadata_payload = {
        "schema_version": 1,
        "walk_run_id": walk_run_id,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "pre_reg_commit_sha": pre_reg_commit_sha,
        "recipe_id": recipe_id,
        "rubric_entry": rubric_entry,
        "params": {
            "seed": seed,
            "n_bootstrap": n_bootstrap,
            "label_window_lower": LABEL_WINDOW_LOWER,
            "train_year_max": TRAIN_YEAR_MAX,
            "test_year_range": [TEST_YEAR_MIN, TEST_YEAR_MAX],
            "cal_fold_size": CAL_FOLD_SIZE,
        },
        "sample_sizes": {
            "n_train_fold": int(len(train_idx)),
            "n_cal_fold": int(len(cal_idx)),
            "n_test": int(len(test_df)),
            "n_pos_train_fold": int(y_train_label[train_idx].sum()),
            "n_pos_cal_fold": int(y_train_label[cal_idx].sum()),
            "n_pos_test": int(y_test_label.sum()),
        },
        "encoder": {
            "type": "OneHotEncoder",
            "n_features_out": encoder_n_features_out,
        },
        "backbone_dir": backbone_dir,
        "head_train_history": head_train_history,
        "calibrator": calibrator.to_dict(),
        "f_rules": {
            "F1": f1,
            "F2": f2,
            "F3": f3,
        },
        "baseline_comparison": baseline_cmp,
        "verdict": verdict,
    }
    (output_dir / "walk_metadata.json").write_text(
        json.dumps(metadata_payload, indent=2, default=_json_default), encoding="utf-8",
    )

    # walk_report.md
    md = render_walk_report(
        recipe_id=recipe_id,
        rank=rubric_entry.get("rank"),
        rubric_metadata=rubric_entry,
        n_train=int(len(train_idx)),
        n_cal=int(len(cal_idx)),
        n_test=int(len(test_df)),
        n_pos_train=int(y_train_label[train_idx].sum()),
        n_pos_cal=int(y_train_label[cal_idx].sum()),
        n_pos_test=int(y_test_label.sum()),
        f1_result=f1,
        f2_result=f2,
        f3_result=f3,
        baseline_comparison=baseline_cmp,
        verdict=verdict,
        pre_reg_commit_sha=pre_reg_commit_sha,
        backbone_dir=backbone_dir,
        walk_run_id=walk_run_id,
    )
    (output_dir / "walk_report.md").write_text(md, encoding="utf-8")
    print(f"[walk] outputs written to {output_dir}", file=sys.stderr)
    print(f"[walk] verdict: {verdict['verdict']}", file=sys.stderr)


def _json_default(obj):
    """Fallback for json.dumps when encountering numpy scalars / arrays."""
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.bool_):
        return bool(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
