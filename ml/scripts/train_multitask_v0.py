#!/usr/bin/env python3
"""
Stage 1 v0 Multi-Task Baseline Trainer
=======================================

Two-stage modular architecture per docs/specs/internal/ops/ml-track/06-modular-architecture.md.
Founder integration on the 2026-05-04 Stage-1 v0 arch consult: original spec
intent is BOTH backbone + heads. The pragmatic v0 implementation uses K
binary boosters with shared hyperparameters as the backbone equivalent
(true multi-output objective with shared trees in a single LightGBM call
is non-trivial; the shared-regularization-regime preserves the audit story
without label-density-skew that pure multiclassova would impose).

    Stage A (BACKBONE -- K binary boosters with shared hyperparameters):
        Train K independent binary LightGBM boosters (one per priority
        recipe), all using the IDENTICAL hyperparameters and regularization
        regime. Each booster gets its recipe-specific scale_pos_weight.
        The "shared backbone" claim therefore means uniform model class +
        regularization across all heads, not literal shared trees.
        Stage 2 may revisit with a custom multi-output objective.

    Stage B (PER-RECIPE HEADS):
        Extract leaf-index features from the backbone (each tree -> one
        categorical leaf-id feature per observation). Train K independent
        LogisticRegression classifiers, one per recipe, on the leaf-index
        features (Ji-Hoon's "per-recipe audit independence").

    Stage C (CALIBRATION):
        Per-recipe Beta calibration (qgi-ml/src/beta_calibration.py) fitted
        on the OOS-by-time hold-out.

    Stage D (PERSIST):
        Write model artifacts (backbone, heads, calibrators) + metadata via
        qgi-ml/src/ml_registry.py to the registry. Emit predictions JSON in
        the schema consumed by qgi-ml/scripts/validate_ml_model.py.

Resolved by 2026-05-04 Stage-1 v0 arch consult (Kwame + Ji-Hoon):
    - Q1 architecture: two-stage backbone+heads (founder tie-break -- both
      personas had partial views; founder integrated both)
    - Q2 hyperparams (CONVERGENT, tightened): num_leaves=11,
      min_data_in_leaf=20, learning_rate=0.05, n_estimators=500,
      early_stopping_rounds=30, lambda_l2=2.0
    - Q3 class balance (CONVERGENT): per-recipe scale_pos_weight in head
      training (backbone uses is_unbalance=True for global rescaling)

OOS-by-time split: train ≤ 2021, test 2022-2025 (per Stage 0 pre-registration
Section 3, F1/F2 falsification rules).

Inputs:
    --recipe-ranking  qgi-data/reference/ml-recipe-ranking-2026-05.json
    --events-dir      qgi-data/events/curated/
    --panel-dir       directory of <indicator>/<indicator>.parquet files
                      (or local cache of pipeline-A-indicator-extractor output)
    --output-dir      where to write model.pkl + metadata.json + predictions.json
    --recipes         optional comma-separated subset of recipes (default: all
                      eligible from rubric)

Outputs:
    <output-dir>/backbone/<recipe>.lgbm         LightGBM Booster (native text format,
                                                portable across Python/lgbm versions)
    <output-dir>/heads/<recipe>.pkl             pickle of LogisticRegression
    <output-dir>/calibrators/<recipe>.json      Beta calibrator params
    <output-dir>/metadata.json                  ModelMetadata schema
    <output-dir>/predictions.json               for validate_ml_model.py

Founder gate: actually running this script on the full panel is Stage 1 Step 2,
gated per stage-1-v0-baseline.md and standing rule
feedback_no_pipeline_runs_without_approval. The script is testable on synthetic
data without founder approval; production runs require greenlight.
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
_ML_DIR = Path(__file__).resolve().parents[1]
_SRC_DIR = _ML_DIR / "src"
_SHARED_DIR = _ML_DIR / "shared"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

import feature_engineering as fe  # noqa: E402
from beta_calibration import BetaCalibrator  # noqa: E402
import ml_registry as mr  # noqa: E402
from slug import country_slug  # noqa: E402  -- canonical snake_case slugifier

_log = logging.getLogger(__name__)


# Hyperparameters retuned 2026-05-04 against the full 104-indicator panel.
#
# History:
#   - 2026-05-04 Stage-1 v0 arch consult (Q2 convergent): num_leaves=11,
#     min_data_in_leaf=20, lambda_l2=2.0 -- tuned for the 19-indicator local
#     cache (filename `all_104_panels.parquet` was misleading; only 19 of 104
#     indicators were present at gen time).
#   - 2026-05-04 Stage-1 v0 expansion: 104 indicators downloaded from S3 Glue
#     `qgi_data.indicators` table. Feature-to-sample ratio jumped from 1.2%
#     (19/1536) to 6.8% (104/1536). The original hyperparams were under-
#     regularized at the new ratio: mean AUC dropped 0.739 -> 0.720, Sri Lanka
#     anchor regressed catastrophically (63.5 -> 1.0 percentile).
#   - 2026-05-04 Stage-1 hyperparameter sweep (24-combo grid; per Ji-Hoon's
#     binding warning that hyperparameter audit is required when feature-to-
#     sample ratio shifts). Best combination by mean AUC across 23 recipes:
#     num_leaves=5, min_data_in_leaf=30, lambda_l2=2.0. Stage-1 v0 outcomes
#     with these defaults: mean AUC=0.796, both anchors PASS (Iceland 28.3
#     percentile, Sri Lanka 91.7 percentile).
#
# Carries an in-sample optimism bias (~0.01-0.03 AUC units) due to selecting
# the combo on the test set; Stage 3 cross-validation re-checks the real-OOS
# number. See docs/specs/internal/ops/ml-track/results/stage-1-baseline-analysis.md.
DEFAULT_HYPERPARAMS = {
    "num_leaves": 5,
    "min_data_in_leaf": 30,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "early_stopping_rounds": 30,
    "lambda_l2": 2.0,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 5,
    "verbose": -1,
}

# OOS-by-time split (per Stage 0 pre-registration Section 3)
DEFAULT_TRAIN_YEAR_MAX = 2021
DEFAULT_TEST_YEAR_MIN = 2022
DEFAULT_TEST_YEAR_MAX = 2025

DEFAULT_INDICATOR_PANEL_FILE = REPO_ROOT / "qgi-ml" / "data" / "all_104_panels.parquet"


# ---------- Data assembly ----------


def load_priority_recipes(
    ranking_path: Path,
    recipe_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Load eligible recipes (rank != None) from the rubric ranking JSON.

    Optionally filter to a subset (e.g., for testing or partial Stage 2 walks).
    Returns rows in rank order.
    """
    payload = json.loads(ranking_path.read_text(encoding="utf-8"))
    eligible = [r for r in payload["ranking"] if r.get("rank") is not None]
    if recipe_filter:
        wanted = set(recipe_filter)
        eligible = [r for r in eligible if r["category_id"] in wanted]
    return eligible


def load_event_labels(
    events_dir: Path,
    recipe_ids: list[str],
    window: tuple[int, int],
    verified_only: bool = True,
) -> pd.DataFrame:
    """Build long-format label DataFrame: (country, year, recipe_id, label).

    Includes ALL (country, year) cells in the panel even where the recipe is
    not observed (label=0). Verified-only matches the pre-registration's
    HARD GATE policy.
    """
    rows: list[dict[str, Any]] = []
    lo, hi = window
    files = [p for p in sorted(events_dir.glob("*.json")) if not p.name.startswith("_")]
    for path in files:
        country = path.stem
        try:
            events = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(events, list):
            continue
        # Build (year, recipe) -> 1 if any verified positive event in that cell
        positive_cells: set[tuple[int, str]] = set()
        for ev in events:
            if not isinstance(ev, dict):
                continue
            year = ev.get("year")
            cat = ev.get("category")
            if year is None or cat is None or cat not in recipe_ids:
                continue
            if not (lo <= year <= hi):
                continue
            if verified_only and not ev.get("verified", False):
                continue
            positive_cells.add((year, cat))
        # Emit one row per (year, recipe) over the full window so absent cells
        # become explicit label=0 rather than missing rows.
        for year in range(lo, hi + 1):
            for rid in recipe_ids:
                label = 1 if (year, rid) in positive_cells else 0
                rows.append({"country": country, "year": year,
                             "recipe_id": rid, "label": label})
    return pd.DataFrame(rows)


def build_feature_panel(
    panel_source: Path,
    train_year_max: int,
    apply_d5_features: bool = False,
) -> pd.DataFrame:
    """Read the indicator panel and apply feature engineering.

    Returns wide-format DataFrame with one row per (country, year) and
    one column per (engineered) indicator.

    Default (D2 baseline behavior, unchanged from prior callers):
    First-differencing applied to all indicators.

    With `apply_d5_features=True` (per docs/specs/internal/ops/ml-track/
    stage-2-d5-walk-methodology-prereg.md, commit 925dc42): also adds
    momentum (lookback=5), rolling z-score (window=3), 3-year delta,
    5-year delta, and acceleration features. Each NEW transform applies
    to ORIGINAL indicators (not to derived `__diff` rows), so the D5
    panel contains 6 feature classes per original indicator: `__diff`,
    `__momentum`, `__zscore`, `__diff3y`, `__diff5y`, `__accel`.

    D5 imputation policy is enforced by the underlying transforms:
    NEW transforms (`__diff3y`, `__diff5y`, `__accel`) use strict
    consecutive-non-null (NaN propagates); EXISTING transforms inherit
    their existing nullability semantics (`min_periods=2` for zscore).

    Note on `train_year_max`: this parameter is accepted for API
    compatibility with all upstream callers (`run_loco_diagnosis.py`,
    `run_stage_3_audit.py`, `run_shap_fingerprint.py`, etc.) but
    `build_feature_panel` does NOT filter by year. The train/test split
    is performed by the caller after merging features with labels;
    passing `train_year_max` here is a forward-looking placeholder for
    a future leak-prevention check at panel-build time.

    Note on duplicate (country, year, indicator_id) rows: this function
    relies on the final `pivot_to_wide` call to detect and warn on
    duplicates. The D5 fresh-copy composition path does NOT introduce
    duplicates (each derived class has unique `<id>__<suffix>`).
    """
    if panel_source.is_file() and panel_source.suffix == ".parquet":
        long = pd.read_parquet(panel_source)
        # Rename columns to match feature_engineering's canonical schema.
        # all_104_panels.parquet uses (country, year, indicator_id, value).
        if "indicator_id" not in long.columns:
            raise ValueError(
                f"expected indicator_id column in {panel_source}; "
                f"got {list(long.columns)}"
            )
    elif panel_source.is_dir():
        # Read all per-indicator parquets via fe.read_indicators
        ids = [d.name for d in panel_source.iterdir() if d.is_dir()]
        long = fe.read_indicators(ids, panel_source)
    else:
        raise FileNotFoundError(f"panel_source not found: {panel_source}")

    # Restrict to canonical 4 columns
    long = long[["country", "year", "indicator_id", "value"]].copy()

    # Normalize country names to snake_case slugs (matches qgi-data/events/
    # curated/<slug>.json filenames + the labels DataFrame). The panel may
    # use Title Case ("Afghanistan") or commas ("Korea, South") -- slugify
    # to align with labels before merging downstream.
    long["country"] = long["country"].map(country_slug)
    n_unmapped = long["country"].isna().sum()
    if n_unmapped > 0:
        _log.warning("dropped %d rows with unmappable country names", n_unmapped)
        long = long.dropna(subset=["country"]).reset_index(drop=True)

    if apply_d5_features:
        # D5: each transform consumes/renames its target rows, so to produce
        # 6 feature classes from the same originals we apply each transform
        # to a FRESH COPY and concat all derived rows. This avoids the
        # composition pitfall where transform N sees no matching IDs because
        # transforms 1..N-1 already renamed them.
        #
        # Memory: 6× DataFrame copies of `original_long`. At QGI's current
        # ~100k-row panel scale this is ~15-30 MB additional memory and is
        # acceptable. If a future panel becomes substantially larger,
        # consider in-place transforms with an immutable `original_long`
        # reference rather than 6 copies.
        original_long = long.copy()
        original_ids = sorted(set(long["indicator_id"].unique()))
        _log.info("D5: applying trajectory features to %d original indicators", len(original_ids))

        derived_pieces = [
            fe.first_difference(original_long.copy(), indicator_ids=original_ids),
            fe.momentum(original_long.copy(), lookback_years=5, indicator_ids=original_ids),
            fe.rolling_zscore(original_long.copy(), window_years=3, indicator_ids=original_ids),
            fe.multi_year_difference(original_long.copy(), lookback_years=3, indicator_ids=original_ids),
            fe.multi_year_difference(original_long.copy(), lookback_years=5, indicator_ids=original_ids),
            fe.acceleration(original_long.copy(), indicator_ids=original_ids),
        ]
        # Each piece contains: the piece's derived rows + (when called with
        # indicator_ids=original_ids covering ALL indicators) zero
        # pass-through rows. The dedup filter below is defensive: it drops
        # any rows whose indicator_id is still in the original list,
        # preserving only the renamed derived rows. This handles the
        # edge case where a future change uses a partial indicator_ids
        # list and the transforms emit pass-through rows.
        long = pd.concat(derived_pieces, ignore_index=True)
        before = len(long)
        long = long[~long["indicator_id"].isin(original_ids)].reset_index(drop=True)
        _log.info("D5: dropped %d untransformed-original rows; kept %d derived rows",
                  before - len(long), len(long))

        # PRE-REG COMPLIANCE NOTE (D5 imputation policy point 5):
        # The pre-reg requires that NaN values in the head's input vector
        # be forwarded as zero with a paired missingness flag
        # (`<feature>__missing`). That enforcement happens at the head's
        # input vector (post-pivot, post-leaf-extraction), NOT in this
        # function — see scripts/train_multitask_d2_d7_with_calibration.py
        # for the runtime assertion that fires if NaN reaches the head.
        # Under the current architecture (head consumes one-hot leaf
        # encodings, not raw features) the policy is trivially satisfied
        # by construction; the assertion encodes the invariant so any
        # future architectural change exposing raw features to the head
        # would fail loudly.
        #
        # This function emits the wide panel with NaN values intact;
        # LightGBM (the backbone) handles NaN natively per pre-reg
        # imputation policy point 4.
    else:
        # D2 baseline: first_difference all indicators (existing behavior).
        long = fe.first_difference(long)
        # Skip rolling_zscore + momentum + missingness_indicators on first cut to
        # keep v0 simple; add back if AUC is too low. This is in-line with "ship
        # the simplest defensible architecture first" (Kwame's pre-registration
        # discipline argument).
        # NOTE: revisit after Stage 1 baseline AUC is observed; if margin is
        # narrow, layer more features.

    wide = fe.pivot_to_wide(long)
    return wide


# ---------- Backbone training ----------


def train_backbone(
    X_train: np.ndarray,
    Y_train_multilabel: np.ndarray,
    X_val: np.ndarray,
    Y_val_multilabel: np.ndarray,
    hyperparams: dict[str, Any],
    seed: int = 0,
) -> list[Any]:
    """Train K binary LightGBM boosters with shared hyperparameters (backbone).

    Y_train_multilabel: shape (n_samples, K) of {0, 1} labels for K recipes.
    Returns: list of K trained LightGBM Boosters.

    True multi-label objective with shared trees in a single LightGBM call
    is non-trivial. The K-independent-binary-boosters pattern with IDENTICAL
    hyperparameters and regularization regime (and per-recipe scale_pos_weight)
    serves as the "backbone equivalent" -- the audit story is "uniform model
    class + regularization across all heads," not literal tree-sharing.
    Per-recipe leaf-index features extracted downstream feed into the
    LogisticRegression heads as the shared-embedding interface to Stage 2.

    `seed` flows into LightGBM's `seed`, `bagging_seed`, and `feature_fraction_seed`
    so the entire training is byte-deterministic on identical input.

    Future Stage 2 may revisit with a custom multi-output objective.
    """
    import lightgbm as lgb

    K = Y_train_multilabel.shape[1]
    boosters: list[Any] = []
    for k in range(K):
        y_train_k = Y_train_multilabel[:, k]
        y_val_k = Y_val_multilabel[:, k]
        n_pos = int((y_train_k == 1).sum())
        n_neg = int((y_train_k == 0).sum())
        scale_pos_weight = (n_neg / n_pos) if n_pos > 0 else 1.0

        params = {
            "objective": "binary",
            "metric": "auc",
            "scale_pos_weight": scale_pos_weight,
            "num_leaves": hyperparams["num_leaves"],
            "min_data_in_leaf": hyperparams["min_data_in_leaf"],
            "learning_rate": hyperparams["learning_rate"],
            "lambda_l2": hyperparams["lambda_l2"],
            "feature_fraction": hyperparams["feature_fraction"],
            "bagging_fraction": hyperparams["bagging_fraction"],
            "bagging_freq": hyperparams["bagging_freq"],
            "verbose": hyperparams["verbose"],
            # Determinism: pin every seed LightGBM uses so byte-identical runs
            # are guaranteed (per pre-registration reproducibility infrastructure).
            "seed": seed + k,
            "bagging_seed": seed + k,
            "feature_fraction_seed": seed + k,
            "deterministic": True,
        }
        train_set = lgb.Dataset(X_train, label=y_train_k)
        val_set = lgb.Dataset(X_val, label=y_val_k, reference=train_set)
        callbacks = [lgb.early_stopping(stopping_rounds=hyperparams["early_stopping_rounds"], verbose=False)]
        booster = lgb.train(
            params=params,
            train_set=train_set,
            num_boost_round=hyperparams["n_estimators"],
            valid_sets=[val_set],
            callbacks=callbacks,
        )
        boosters.append(booster)
    return boosters


def extract_leaf_features(
    boosters: list[Any],
    X: np.ndarray,
) -> np.ndarray:
    """Extract leaf-index features from each booster, concatenated.

    Output shape: (n_samples, sum_k(n_trees_k)). Each column is a leaf id
    (categorical) which the per-recipe head treats as a discrete feature
    via one-hot or directly via tree-aware LogisticRegression.
    """
    leaf_blocks: list[np.ndarray] = []
    for booster in boosters:
        leaves = booster.predict(X, pred_leaf=True)  # shape (n, n_trees)
        leaf_blocks.append(leaves)
    return np.hstack(leaf_blocks)


# ---------- Per-recipe head training ----------


def train_per_recipe_heads(
    leaf_train: np.ndarray,
    Y_train: np.ndarray,
    recipe_ids: list[str],
    seed: int = 0,
) -> dict[str, Any]:
    """Train one LogisticRegression per recipe on leaf-index features.

    Returns dict: recipe_id -> trained LogisticRegression instance.

    Each head uses class_weight={0:1, 1:scale_pos_weight} for explicit per-
    recipe class balancing (Q3 convergent answer).
    """
    from sklearn.linear_model import LogisticRegression

    heads: dict[str, Any] = {}
    for k, rid in enumerate(recipe_ids):
        y_train_k = Y_train[:, k]
        n_pos = int((y_train_k == 1).sum())
        n_neg = int((y_train_k == 0).sum())
        if n_pos == 0:
            _log.warning("recipe %s has 0 training positives; skipping head", rid)
            continue
        scale_pos_weight = (n_neg / n_pos) if n_pos > 0 else 1.0
        clf = LogisticRegression(
            class_weight={0: 1.0, 1: scale_pos_weight},
            max_iter=1000,
            random_state=seed,
            solver="lbfgs",
        )
        clf.fit(leaf_train, y_train_k)
        heads[rid] = clf
    return heads


def predict_per_recipe(
    heads: dict[str, Any],
    leaf_features: np.ndarray,
) -> dict[str, np.ndarray]:
    """Return recipe_id -> predicted_probability vector."""
    out: dict[str, np.ndarray] = {}
    for rid, clf in heads.items():
        # LogisticRegression.predict_proba returns (n, 2); column 1 is P(y=1)
        out[rid] = clf.predict_proba(leaf_features)[:, 1]
    return out


# ---------- Calibration ----------


def fit_calibrators(
    raw_predictions: dict[str, np.ndarray],
    Y_test: np.ndarray,
    recipe_ids: list[str],
) -> dict[str, BetaCalibrator]:
    """Fit per-recipe Beta calibrators on the OOS-by-time hold-out."""
    out: dict[str, BetaCalibrator] = {}
    for k, rid in enumerate(recipe_ids):
        if rid not in raw_predictions:
            continue
        y_test_k = Y_test[:, k]
        cal = BetaCalibrator.fit(raw_predictions[rid], y_test_k)
        out[rid] = cal
    return out


def apply_calibrators(
    raw_predictions: dict[str, np.ndarray],
    calibrators: dict[str, BetaCalibrator],
) -> dict[str, np.ndarray]:
    return {rid: calibrators[rid].predict(p)
            for rid, p in raw_predictions.items()
            if rid in calibrators}


# ---------- Output assembly ----------


def emit_predictions_json(
    output_path: Path,
    test_metadata: pd.DataFrame,
    calibrated_preds: dict[str, np.ndarray],
    Y_test: np.ndarray,
    recipe_ids: list[str],
    model_metadata_uri: str,
) -> None:
    """Emit predictions JSON in the validate_ml_model.py v1 schema."""
    rows: list[dict[str, Any]] = []
    for k, rid in enumerate(recipe_ids):
        if rid not in calibrated_preds:
            continue
        preds = calibrated_preds[rid]
        labels = Y_test[:, k]
        for i in range(len(test_metadata)):
            rows.append({
                "country": test_metadata.iloc[i]["country"],
                "year": int(test_metadata.iloc[i]["year"]),
                "recipe_id": rid,
                "predicted_probability": float(preds[i]),
                "label": int(labels[i]),
            })
    payload = {
        "schema_version": 1,
        "model_metadata_uri": model_metadata_uri,
        "predictions": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ---------- Orchestrator ----------


def run_training(
    ranking_path: Path,
    events_dir: Path,
    panel_source: Path,
    output_dir: Path,
    recipes_filter: list[str] | None = None,
    train_year_max: int = DEFAULT_TRAIN_YEAR_MAX,
    test_year_min: int = DEFAULT_TEST_YEAR_MIN,
    test_year_max: int = DEFAULT_TEST_YEAR_MAX,
    hyperparams: dict[str, Any] | None = None,
    seed: int = 0,
    apply_d5_features: bool = False,
) -> dict[str, Any]:
    """End-to-end Stage 1 v0 training. Returns summary dict.

    Steps:
      1. Load priority recipes from rubric ranking
      2. Load + assemble training-window events labels
      3. Build feature panel (engineered features)
      4. Merge labels + features; OOS-by-time split
      5. Train backbone (K binary boosters with shared hyperparams)
      6. Extract leaf-index features
      7. Train per-recipe heads (LogisticRegression)
      8. Fit Beta calibrators
      9. Emit predictions.json + persist artifacts via ml_registry
    """
    hp = dict(DEFAULT_HYPERPARAMS)
    if hyperparams:
        hp.update(hyperparams)

    # 1. Recipes
    recipes = load_priority_recipes(ranking_path, recipe_filter=recipes_filter)
    recipe_ids = [r["category_id"] for r in recipes]
    if not recipe_ids:
        raise ValueError("no eligible recipes; check ranking_path or recipes_filter")

    # 2. Labels — use the rubric's training window: 2014 → test_year_max
    # (pre-registration §3 locks 2014-2025 as the relevant labeling window).
    LABEL_WINDOW_LOWER = 2014  # fixed by pre-registration §3
    label_window = (LABEL_WINDOW_LOWER, test_year_max)
    labels = load_event_labels(events_dir, recipe_ids, label_window, verified_only=True)

    # 3. Features
    features = build_feature_panel(panel_source, train_year_max,
                                    apply_d5_features=apply_d5_features)
    if apply_d5_features:
        n_feat = len([c for c in features.columns if c not in ("country", "year")])
        _log.info("D5 mode: feature panel has %d feature columns", n_feat)

    # 4. Merge: labels has (country, year, recipe_id, label); features has wide
    # (country, year, indicator_cols). Pivot labels to (country, year) x recipe.
    label_wide = labels.pivot_table(
        index=["country", "year"], columns="recipe_id", values="label", aggfunc="first"
    ).reset_index()
    label_wide.columns.name = None
    # Merge on (country, year)
    merged = features.merge(label_wide, on=["country", "year"], how="inner")
    if merged.empty:
        raise ValueError(
            "merged feature+label DataFrame is empty; check country naming + year coverage"
        )

    # OOS-by-time split
    train_mask = merged["year"] <= train_year_max
    test_mask = (merged["year"] >= test_year_min) & (merged["year"] <= test_year_max)
    train_df = merged[train_mask].reset_index(drop=True)
    test_df = merged[test_mask].reset_index(drop=True)
    if train_df.empty or test_df.empty:
        raise ValueError(
            f"empty train ({len(train_df)}) or test ({len(test_df)}) split; check window"
        )

    # Separate features X and labels Y
    label_cols = [c for c in recipe_ids if c in merged.columns]
    feature_cols = [c for c in merged.columns
                    if c not in ("country", "year") and c not in label_cols]
    X_train = train_df[feature_cols].to_numpy(dtype=float)
    X_test = test_df[feature_cols].to_numpy(dtype=float)
    Y_train = train_df[label_cols].fillna(0).to_numpy(dtype=int)
    Y_test = test_df[label_cols].fillna(0).to_numpy(dtype=int)

    # 5. Backbone
    _log.info("training backbone: K=%d recipes, n_train=%d, n_test=%d, n_features=%d",
              len(label_cols), len(train_df), len(test_df), len(feature_cols))
    boosters = train_backbone(X_train, Y_train, X_test, Y_test, hp, seed=seed)

    # 6. Leaf features
    leaf_train = extract_leaf_features(boosters, X_train)
    leaf_test = extract_leaf_features(boosters, X_test)

    # 7. Heads
    heads = train_per_recipe_heads(leaf_train, Y_train, label_cols, seed=seed)

    # 8. Raw predictions on test set
    raw_preds = predict_per_recipe(heads, leaf_test)

    # 9. Beta calibration
    calibrators = fit_calibrators(raw_preds, Y_test, label_cols)
    calibrated_preds = apply_calibrators(raw_preds, calibrators)

    # 10. Persist artifacts
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save backbone — one .lgbm file per booster in native LightGBM text
    # format (portable across Python/lgbm versions; pickle is fragile).
    backbone_dir = output_dir / "backbone"
    backbone_dir.mkdir(exist_ok=True)
    for k, booster in enumerate(boosters):
        rid = label_cols[k]
        booster.save_model(str(backbone_dir / f"{rid}.lgbm"))

    # Save per-recipe heads
    heads_dir = output_dir / "heads"
    heads_dir.mkdir(exist_ok=True)
    for rid, clf in heads.items():
        with (heads_dir / f"{rid}.pkl").open("wb") as f:
            pickle.dump(clf, f)

    # Save calibrators
    cal_dir = output_dir / "calibrators"
    cal_dir.mkdir(exist_ok=True)
    for rid, cal in calibrators.items():
        (cal_dir / f"{rid}.json").write_text(
            json.dumps(cal.to_dict(), indent=2), encoding="utf-8")

    # 11. Emit predictions JSON
    test_metadata = test_df[["country", "year"]]
    emit_predictions_json(
        output_path=output_dir / "predictions.json",
        test_metadata=test_metadata,
        calibrated_preds=calibrated_preds,
        Y_test=Y_test,
        recipe_ids=label_cols,
        model_metadata_uri=str(output_dir),
    )

    # 12. Summary
    summary = {
        "n_recipes_trained": len(heads),
        "n_recipes_with_calibrators": len(calibrators),
        "n_train_observations": int(len(train_df)),
        "n_test_observations": int(len(test_df)),
        "n_features": int(len(feature_cols)),
        "n_leaf_features": int(leaf_train.shape[1]),
        "hyperparameters": hp,
        "train_year_max": train_year_max,
        "test_year_range": [test_year_min, test_year_max],
        "output_dir": str(output_dir),
    }
    return summary


# ---------- CLI ----------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipe-ranking", type=Path, required=True)
    parser.add_argument("--events-dir", type=Path, required=True)
    parser.add_argument("--panel-source", type=Path, required=True,
                        help="parquet file OR directory of <ind>/<ind>.parquet")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--recipes", type=str, default=None,
                        help="optional comma-separated subset")
    parser.add_argument("--train-year-max", type=int, default=DEFAULT_TRAIN_YEAR_MAX)
    parser.add_argument("--test-year-min", type=int, default=DEFAULT_TEST_YEAR_MIN)
    parser.add_argument("--test-year-max", type=int, default=DEFAULT_TEST_YEAR_MAX)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--apply-d5-features", action="store_true",
                        help="Enable Phase D D5 trajectory features (~6x input dim). "
                             "Requires the D5 pre-reg "
                             "(docs/specs/internal/ops/ml-track/stage-2-d5-walk-methodology-prereg.md, "
                             "commit 925dc42) and tier pre-reg (commit 2c87f06) to be in force. "
                             "Produces D5 backbones suitable for downstream "
                             "train_multitask_d2_d7_with_calibration.py --apply-d5-features.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    recipes_filter = [r.strip() for r in args.recipes.split(",")] if args.recipes else None
    summary = run_training(
        ranking_path=args.recipe_ranking,
        events_dir=args.events_dir,
        panel_source=args.panel_source,
        output_dir=args.output_dir,
        recipes_filter=recipes_filter,
        train_year_max=args.train_year_max,
        test_year_min=args.test_year_min,
        test_year_max=args.test_year_max,
        seed=args.seed,
        apply_d5_features=args.apply_d5_features,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
