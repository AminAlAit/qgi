"""# THROWAWAY -- one-off training script. Phase D D2 + D7 combined:
multi-task head + isotonic calibration + posterior predictive intervals
via cluster-bootstrap of the calibrator.

Per docs/specs/internal/ops/ml-track/stage-2-amendment-2026-05-05.md
(commit `04fa5fb`):
- D2: multi-task head with shared representation (already done; head
  module merged in qgi-ml#34, training+LOCO in qgi-ml#35)
- D7: posterior predictive intervals as first-class output. Per Priya's
  recommendation: ML-Opus must commit NOW to storing predictive
  intervals, not retrofit at Stage 4. This script delivers that.

## What's added vs train_multitask_head_on_frozen_backbone.py (D2 only)

1. **Isotonic calibration per recipe.** Fits sklearn IsotonicRegression
   on cal-fold raw predictions vs cal-fold labels per recipe. Restores
   the calibration that was deferred in the D2-only PR (D2 raw test
   ECE was bad because we skipped calibration entirely).

2. **Posterior predictive intervals via bootstrap of the calibrator.**
   For each test cell + recipe: bootstrap-resample the cal-fold B times,
   refit isotonic, predict; emit (mean, ci_lower, ci_upper) at 95%.
   This is the cheapest defensible per-cell uncertainty estimate.

3. **Output schema extends to (mean, ci_lower, ci_upper, std).**
   Stage 4 heatmap will use opacity proportional to (ci_upper -
   ci_lower) per Priya's UI requirement.

Usage::

    python scripts/train_multitask_d2_d7_with_calibration.py \\
        --backbone-dir results/hp_sweep_5_30_2/backbone \\
        --panel data/panel_104_2026_05_04.parquet \\
        --events-dir ../qgi-data/events/curated \\
        --rubric ../qgi-data/reference/ml-recipe-ranking-2026-05.json \\
        --output-dir results/d2_d7_multitask_2026_05 \\
        --n-bootstrap 50
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

from beta_calibration import BetaCalibrator  # noqa: E402
from heads.multitask import MultiTaskHead, MultiTaskHeadConfig  # noqa: E402
from train_multitask_v0 import (  # noqa: E402
    build_feature_panel,
    extract_leaf_features,
    load_event_labels,
    load_priority_recipes,
)
from walk.calibrate import IsotonicCalibrator, stratified_train_cal_split  # noqa: E402


def _make_calibrator_factory(method: str):
    """Returns a fit_and_predict callable consistent across methods."""
    if method == "beta":
        def beta_fit_predict(cal_raw, cal_labels, test_raw):
            cal = BetaCalibrator.fit(cal_raw, cal_labels)
            return cal.predict(test_raw)
        return beta_fit_predict
    elif method == "isotonic":
        def iso_fit_predict(cal_raw, cal_labels, test_raw):
            cal = IsotonicCalibrator()
            cal.fit(cal_raw, cal_labels)
            return cal.predict(test_raw)
        return iso_fit_predict
    else:
        raise ValueError(f"Unknown calibration method: {method}")

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
    p.add_argument("--n-bootstrap", type=int, default=50,
                   help="Calibrator bootstrap iterations for posterior intervals")
    p.add_argument("--calibration-method", choices=["isotonic", "beta"], default="beta",
                   help="Calibration method. Beta is the production default (smooth, "
                        "no step ties). Isotonic supported for diagnostic comparison.")
    p.add_argument("--apply-d5-features", action="store_true",
                   help="Enable Phase D D5 trajectory features in build_feature_panel. "
                        "Requires the D5 pre-reg "
                        "(docs/specs/internal/ops/ml-track/stage-2-d5-walk-methodology-prereg.md, "
                        "commit 925dc42) and the tier pre-reg "
                        "(stage-2-tier-threshold-prereg.md, commit 2c87f06) to be in force. "
                        "Adds momentum, rolling z-score, multi-year deltas, and acceleration "
                        "features (~6x input dim).")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def _log(msg: str, *, quiet: bool = False) -> None:
    if not quiet:
        print(msg, file=sys.stderr)


def _bootstrap_calibrator_predictions(
    cal_raw: np.ndarray,
    cal_labels: np.ndarray,
    test_raw: np.ndarray,
    *,
    n_bootstrap: int,
    seed: int,
    method: str = "beta",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Bootstrap the cal-fold; refit calibrator per resample; predict
    on test. Returns (mean, ci_lower, ci_upper, std) per test cell.

    Cluster: bootstrap is on (raw, label) pairs; preserves cal-fold size.
    Confidence: 95%.
    """
    fit_predict = _make_calibrator_factory(method)
    rng = np.random.default_rng(seed)
    n_cal = len(cal_raw)
    boot_preds: list[np.ndarray] = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n_cal, size=n_cal)
        cal_resampled_raw = cal_raw[idx]
        cal_resampled_lab = cal_labels[idx]
        try:
            preds = fit_predict(cal_resampled_raw, cal_resampled_lab, test_raw)
            boot_preds.append(preds)
        except (ValueError, RuntimeError):
            continue
    if not boot_preds:
        return np.zeros_like(test_raw), np.zeros_like(test_raw), np.zeros_like(test_raw), np.zeros_like(test_raw)
    arr = np.stack(boot_preds, axis=0)  # (B, n_test)
    mean = arr.mean(axis=0)
    ci_lower = np.percentile(arr, 2.5, axis=0)
    ci_upper = np.percentile(arr, 97.5, axis=0)
    std = arr.std(axis=0)
    return mean, ci_lower, ci_upper, std


def main() -> int:  # noqa: PLR0915, C901
    args = parse_args()

    # 1. Recipes
    recipes = load_priority_recipes(args.rubric, recipe_filter=None)
    recipe_ids = [r["category_id"] for r in recipes]
    _log(f"[d2d7] eligible recipes: {len(recipe_ids)}", quiet=args.quiet)

    # 2. Backbones
    import lightgbm as lgb
    backbone_paths = sorted(args.backbone_dir.glob("*.lgbm"))
    boosters = [lgb.Booster(model_file=str(p)) for p in backbone_paths]
    backbone_recipe_ids = [p.stem for p in backbone_paths]
    recipe_ids = [r for r in recipe_ids if r in backbone_recipe_ids]
    _log(f"[d2d7] loaded {len(boosters)} backbones; {len(recipe_ids)} recipes", quiet=args.quiet)

    # 3. Labels + features
    _log("[d2d7] loading event labels...", quiet=args.quiet)
    label_window = (LABEL_WINDOW_LOWER, TEST_YEAR_MAX)
    labels = load_event_labels(args.events_dir, recipe_ids, label_window, verified_only=True)
    label_wide = labels.pivot_table(
        index=["country", "year"], columns="recipe_id", values="label", aggfunc="first",
    ).reset_index()
    label_wide.columns.name = None
    if args.apply_d5_features:
        _log("[d2d7] D5 mode: applying trajectory features (momentum, zscore, "
             "diff3y, diff5y, accel)...", quiet=args.quiet)
    _log("[d2d7] building feature panel...", quiet=args.quiet)
    feature_panel = build_feature_panel(args.panel, train_year_max=TRAIN_YEAR_MAX,
                                         apply_d5_features=args.apply_d5_features)
    n_feat_cols = len([c for c in feature_panel.columns if c not in ("country", "year")])
    _log(f"[d2d7] feature panel: {len(feature_panel)} rows × {n_feat_cols} feature columns "
         f"({'D5' if args.apply_d5_features else 'D2'} mode)", quiet=args.quiet)
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
    _log(f"[d2d7] train={len(train_df)}, test={len(test_df)}, K={len(label_cols)}",
         quiet=args.quiet)

    # 4. Leaf features + one-hot
    leaf_train = extract_leaf_features(boosters, X_train)
    leaf_test = extract_leaf_features(boosters, X_test)
    from sklearn.preprocessing import OneHotEncoder
    encoder = OneHotEncoder(categories="auto", sparse_output=False, handle_unknown="ignore")
    encoder.fit(leaf_train)
    leaf_train_oh = encoder.transform(leaf_train).astype(np.float32)
    leaf_test_oh = encoder.transform(leaf_test).astype(np.float32)

    # PRE-REG COMPLIANCE GUARD (D5 imputation policy point 5):
    # The pre-reg requires that the head input vector contain no NaN values
    # — every feature must be either a real value or zero-with-paired-flag.
    # Under the current architecture, the head consumes ONE-HOT-ENCODED LEAF
    # INDICES (not raw features), so by construction the head input has no
    # NaN values: leaf indices are integers, and one-hot encoding produces
    # only {0, 1} float entries. The policy is therefore trivially satisfied
    # by the architecture; this assertion encodes that invariant so any
    # future architectural change that exposes raw features to the head
    # would fail the assertion and force the implementer to add explicit
    # zero+flag substitution per the pre-reg.
    if args.apply_d5_features:
        n_train_nan = int(np.isnan(leaf_train_oh).sum())
        n_test_nan = int(np.isnan(leaf_test_oh).sum())
        if n_train_nan != 0 or n_test_nan != 0:
            raise RuntimeError(
                f"D5 pre-reg compliance: head input vector contains NaN "
                f"(train={n_train_nan}, test={n_test_nan}). The D5 imputation "
                f"policy point 5 requires zero-substitution + paired __missing "
                f"flag for any NaN reaching the head. The current architecture "
                f"feeds one-hot leaf encodings (which should be NaN-free by "
                f"construction); a NaN here indicates an architectural change "
                f"that violates the pre-reg. See "
                f"docs/specs/internal/ops/ml-track/stage-2-d5-walk-methodology-prereg.md "
                f"point 5 for the policy."
            )
        # Also report NaN fraction at the BACKBONE input — informational,
        # not a violation (LightGBM handles NaN natively per the pre-reg).
        backbone_train_nan_frac = float(np.isnan(X_train).sum()) / max(X_train.size, 1)
        backbone_test_nan_frac = float(np.isnan(X_test).sum()) / max(X_test.size, 1)
        _log(f"[d2d7] D5 backbone NaN fraction: train={backbone_train_nan_frac:.3f}, "
             f"test={backbone_test_nan_frac:.3f} (handled natively by LightGBM per "
             f"D5 pre-reg policy point 4)", quiet=args.quiet)

    # 5. Stratified train/cal split (anchor on max-positives recipe)
    n_pos_per_recipe = Y_train.sum(axis=0)
    anchor_recipe_idx = int(np.argmax(n_pos_per_recipe))
    train_idx, cal_idx = stratified_train_cal_split(
        Y_train[:, anchor_recipe_idx], cal_size=CAL_FOLD_SIZE, seed=args.seed,
    )
    _log(f"[d2d7] anchor recipe: {label_cols[anchor_recipe_idx]} "
         f"(n_pos={int(n_pos_per_recipe[anchor_recipe_idx])})", quiet=args.quiet)

    # 6. Fit MT head
    _log("[d2d7] fitting multi-task head...", quiet=args.quiet)
    head = MultiTaskHead(
        config=MultiTaskHeadConfig(seed=args.seed, max_epochs=args.max_epochs),
        n_recipes=len(label_cols),
    )
    head.fit(
        leaf_train_oh[train_idx], Y_train[train_idx],
        X_val=leaf_train_oh[cal_idx], Y_val=Y_train[cal_idx],
    )

    # 7. Predict raw on cal-fold + test
    raw_cal = head.predict_proba(leaf_train_oh[cal_idx])  # (n_cal, K)
    raw_test = head.predict_proba(leaf_test_oh)  # (n_test, K)

    # 8. Per-recipe isotonic + bootstrap calibrator
    _log(f"[d2d7] fitting isotonic + bootstrapping (B={args.n_bootstrap}) per recipe...",
         quiet=args.quiet)
    Y_cal = Y_train[cal_idx]  # (n_cal, K)
    calibrated_test_mean: np.ndarray = np.zeros((len(test_df), len(label_cols)))
    calibrated_test_ci_lo: np.ndarray = np.zeros_like(calibrated_test_mean)
    calibrated_test_ci_hi: np.ndarray = np.zeros_like(calibrated_test_mean)
    calibrated_test_std: np.ndarray = np.zeros_like(calibrated_test_mean)
    for k, rid in enumerate(label_cols):
        cal_raw_k = raw_cal[:, k]
        cal_labels_k = Y_cal[:, k]
        test_raw_k = raw_test[:, k]
        if cal_labels_k.sum() == 0:
            # No positives in cal-fold for this recipe -- skip calibration,
            # use raw predictions
            calibrated_test_mean[:, k] = test_raw_k
            calibrated_test_ci_lo[:, k] = test_raw_k
            calibrated_test_ci_hi[:, k] = test_raw_k
            continue

        # CANONICAL prediction: SINGLE calibrator fit on the full cal-fold.
        # This preserves monotonicity with raw_test (necessary so anchor
        # ranks computed across countries are stable). The per-recipe
        # bootstrap below ONLY drives CI bounds (uncertainty), NOT the
        # canonical prediction value. Bootstrap-mean breaks monotonicity
        # since different resamples reorder near-tie values; using
        # bootstrap-mean as canonical would degrade AHI vs raw despite
        # improving ECE. (Caught at integration time, 2026-05-06.)
        #
        # Beta is the production default: smooth function, no step ties.
        # Isotonic supported via --calibration-method=isotonic for
        # diagnostic comparison; both pass F1 ECE gate but Beta is
        # marginally better on AHI (26.68 vs 25.64 in 2026-05-06 sweep).
        fit_predict = _make_calibrator_factory(args.calibration_method)
        calibrated_test_mean[:, k] = fit_predict(cal_raw_k, cal_labels_k, test_raw_k)

        # Uncertainty: bootstrap calibrator B times for CI bounds only.
        _, lo, hi, std = _bootstrap_calibrator_predictions(
            cal_raw_k, cal_labels_k, test_raw_k,
            n_bootstrap=args.n_bootstrap, seed=args.seed + k,
            method=args.calibration_method,
        )
        calibrated_test_ci_lo[:, k] = lo
        calibrated_test_ci_hi[:, k] = hi
        calibrated_test_std[:, k] = std

    # 9. Emit predictions.json with (mean, ci_low, ci_high, std)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    predictions: list[dict] = []
    for i, row in enumerate(test_df.itertuples(index=False)):
        for k, rid in enumerate(label_cols):
            predictions.append({
                "country": str(row.country),
                "year": int(row.year),
                "recipe_id": rid,
                "predicted_probability": float(calibrated_test_mean[i, k]),
                "predicted_probability_ci_lower": float(calibrated_test_ci_lo[i, k]),
                "predicted_probability_ci_upper": float(calibrated_test_ci_hi[i, k]),
                "predicted_probability_std": float(calibrated_test_std[i, k]),
                "raw_predicted_probability": float(raw_test[i, k]),
                "label": int(Y_test[i, k]),
            })

    payload = {
        "schema_version": 2,  # bumped: adds posterior interval fields
        "model_metadata_uri": str(output_dir),
        "predictions": predictions,
        "metadata": {
            "model_kind": f"multitask_head_d2_with_d7_{args.calibration_method}_calibration",
            "calibration": {
                "method": f"{args.calibration_method}_per_recipe",
                "n_bootstrap": args.n_bootstrap,
                "ci_level": 0.95,
                "ci_lower_percentile": 2.5,
                "ci_upper_percentile": 97.5,
            },
            "head_config": {
                "hidden_dims": list(MultiTaskHeadConfig().hidden_dims),
                "max_epochs": args.max_epochs,
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
    _log(f"[d2d7] wrote {out_path} ({len(predictions)} prediction rows)", quiet=args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
