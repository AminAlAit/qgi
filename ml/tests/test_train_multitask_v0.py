"""End-to-end pipeline tests for scripts/train_multitask_v0.py.

Synthesizes a tiny event corpus + indicator panel + recipe ranking, runs the
full Stage 1 v0 training pipeline, and verifies artifacts are written + the
predictions JSON has the expected schema.

NOT a model-quality test (synthetic data has no real signal). The goal is
to prove the pipeline executes end-to-end without crashing and emits
spec-compliant outputs.
"""
from __future__ import annotations

import json
import pathlib
import pickle
import sys

import numpy as np
import pandas as pd
import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import train_multitask_v0 as t  # noqa: E402


@pytest.fixture
def synthetic_setup(tmp_path):
    """Build a tiny synthetic dataset: 20 countries, 12 years, 3 indicators, 3 recipes."""
    countries = [f"country_{i}" for i in range(20)]
    years = list(range(2014, 2026))
    indicators = ["IND-A", "IND-B", "IND-C"]
    recipes = ["recipe_alpha", "recipe_beta", "recipe_gamma"]

    rng = np.random.default_rng(0)

    # 1. Indicator panel (long format)
    panel_rows = []
    for c in countries:
        for y in years:
            for ind in indicators:
                panel_rows.append({
                    "country": c, "year": y, "indicator_id": ind,
                    "value": float(rng.normal(0, 1)),
                })
    panel_df = pd.DataFrame(panel_rows)
    panel_path = tmp_path / "panel.parquet"
    panel_df.to_parquet(panel_path)

    # 2. Events corpus (per-country JSONs in events_dir)
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    for c in countries:
        events = []
        # Sparse positives: ~10% of country-year-recipe cells get a verified event
        for y in years:
            for r in recipes:
                if rng.uniform(0, 1) < 0.10:
                    events.append({
                        "year": y,
                        "category": r,
                        "verified": True,  # all verified for test (real data: 14% verified)
                        "title": f"event in {c} {y}",
                    })
        (events_dir / f"{c}.json").write_text(json.dumps(events), encoding="utf-8")

    # 3. Recipe ranking JSON (mimics ml-recipe-ranking-2026-05.json shape)
    ranking = {
        "schema_version": 1,
        "weights": {"A": 0.35, "B": 0.25, "C": 0.25, "D": 0.15},
        "hard_gate": {"min_n_positive": 8},
        "ranking": [
            {"rank": k + 1, "category_id": r, "S": 0.8 - k * 0.05,
             "n_positive_verified": 12, "n_positive_total": 30,
             "excluded_by_hard_gate": False, "F5": 1, "head_class": "standard GBM"}
            for k, r in enumerate(recipes)
        ],
    }
    ranking_path = tmp_path / "ranking.json"
    ranking_path.write_text(json.dumps(ranking), encoding="utf-8")

    return {
        "panel_path": panel_path,
        "events_dir": events_dir,
        "ranking_path": ranking_path,
        "output_dir": tmp_path / "out",
        "recipes": recipes,
    }


def test_load_priority_recipes_returns_eligible_only(synthetic_setup):
    out = t.load_priority_recipes(synthetic_setup["ranking_path"])
    assert len(out) == 3
    assert all(r["rank"] is not None for r in out)


def test_load_priority_recipes_filters_to_subset(synthetic_setup):
    out = t.load_priority_recipes(
        synthetic_setup["ranking_path"],
        recipe_filter=["recipe_alpha"],
    )
    assert len(out) == 1
    assert out[0]["category_id"] == "recipe_alpha"


def test_load_event_labels_emits_full_grid(synthetic_setup):
    """Label loader should emit one row per (country, year, recipe) over the
    full window — including label=0 cells where no event was curated."""
    labels = t.load_event_labels(
        synthetic_setup["events_dir"],
        recipe_ids=["recipe_alpha", "recipe_beta", "recipe_gamma"],
        window=(2014, 2025),
        verified_only=True,
    )
    n_countries = 20
    n_years = 12
    n_recipes = 3
    assert len(labels) == n_countries * n_years * n_recipes
    # Label values are 0 or 1
    assert set(labels["label"].unique()).issubset({0, 1})


def test_run_training_produces_all_artifacts(synthetic_setup):
    """End-to-end: pipeline should write backbone + heads + calibrators + predictions."""
    summary = t.run_training(
        ranking_path=synthetic_setup["ranking_path"],
        events_dir=synthetic_setup["events_dir"],
        panel_source=synthetic_setup["panel_path"],
        output_dir=synthetic_setup["output_dir"],
        train_year_max=2021,
        test_year_min=2022,
        test_year_max=2025,
        # Use small hyperparameters to speed up test
        hyperparams={"n_estimators": 20, "early_stopping_rounds": 5,
                     "min_data_in_leaf": 5, "num_leaves": 7,
                     "learning_rate": 0.1, "lambda_l2": 1.0,
                     "feature_fraction": 0.9, "bagging_fraction": 0.9,
                     "bagging_freq": 5, "verbose": -1},
    )
    out = synthetic_setup["output_dir"]
    # Artifacts exist
    assert (out / "backbone").is_dir()
    backbone_files = list((out / "backbone").glob("*.lgbm"))
    assert len(backbone_files) >= 1  # at least one booster saved in native lgbm format
    assert (out / "predictions.json").is_file()
    # Heads + calibrators exist for at least some recipes
    head_files = list((out / "heads").glob("*.pkl"))
    cal_files = list((out / "calibrators").glob("*.json"))
    assert len(head_files) >= 1
    assert len(cal_files) >= 1
    # Predictions JSON conforms to v1 schema
    preds = json.loads((out / "predictions.json").read_text(encoding="utf-8"))
    assert preds["schema_version"] == 1
    assert "predictions" in preds
    for row in preds["predictions"][:5]:
        for key in ("country", "year", "recipe_id", "predicted_probability", "label"):
            assert key in row
        assert 0.0 <= row["predicted_probability"] <= 1.0
        assert row["label"] in (0, 1)
    # Summary contains expected keys
    for key in ("n_recipes_trained", "n_train_observations", "n_test_observations",
                "n_features", "n_leaf_features", "hyperparameters"):
        assert key in summary


def test_run_training_predictions_loadable_by_validate_ml_model(synthetic_setup):
    """The predictions JSON must be consumable by the Stage 0 validation script."""
    t.run_training(
        ranking_path=synthetic_setup["ranking_path"],
        events_dir=synthetic_setup["events_dir"],
        panel_source=synthetic_setup["panel_path"],
        output_dir=synthetic_setup["output_dir"],
        hyperparams={"n_estimators": 20, "early_stopping_rounds": 5,
                     "min_data_in_leaf": 5, "num_leaves": 7,
                     "learning_rate": 0.1, "lambda_l2": 1.0,
                     "feature_fraction": 0.9, "bagging_fraction": 0.9,
                     "bagging_freq": 5, "verbose": -1},
    )
    preds_path = synthetic_setup["output_dir"] / "predictions.json"
    payload = json.loads(preds_path.read_text(encoding="utf-8"))

    # Import validate_ml_model from scripts and run on the predictions
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import validate_ml_model as v
    report = v.run_validation(
        predictions=payload["predictions"],
        anchor_battery=None,
        n_bootstrap=20,  # tiny for test speed
        seed=0,
    )
    assert report["schema_version"] == 1
    assert report["n_recipes"] >= 1
    # Each recipe has bootstrap CI + ECE + Brier
    for rid in report["components"]["oos_by_time"]["per_recipe"]:
        cell = report["components"]["oos_by_time"]["per_recipe"][rid]
        assert "auc_point" in cell
        assert "auc_ci_low" in cell
        assert "delta_ci_low" in cell  # rev1 addition


def test_extract_leaf_features_shape(synthetic_setup):
    """Leaf features should have one column per tree across the K boosters."""
    import lightgbm as lgb
    rng = np.random.default_rng(0)
    n_samples, n_features = 100, 5
    X = rng.normal(0, 1, size=(n_samples, n_features))
    y_a = rng.integers(0, 2, size=n_samples)
    y_b = rng.integers(0, 2, size=n_samples)
    booster_a = lgb.train(
        {"objective": "binary", "verbose": -1, "num_leaves": 7,
         "min_data_in_leaf": 5, "learning_rate": 0.1},
        lgb.Dataset(X, label=y_a),
        num_boost_round=10,
    )
    booster_b = lgb.train(
        {"objective": "binary", "verbose": -1, "num_leaves": 7,
         "min_data_in_leaf": 5, "learning_rate": 0.1},
        lgb.Dataset(X, label=y_b),
        num_boost_round=10,
    )
    leaves = t.extract_leaf_features([booster_a, booster_b], X)
    assert leaves.shape[0] == n_samples
    # 10 trees per booster, 2 boosters = 20 columns
    assert leaves.shape[1] == 20


def test_run_training_raises_on_missing_recipe_filter(synthetic_setup):
    """Filter to a non-existent recipe -> ValueError 'no eligible recipes'."""
    with pytest.raises(ValueError, match="no eligible recipes"):
        t.run_training(
            ranking_path=synthetic_setup["ranking_path"],
            events_dir=synthetic_setup["events_dir"],
            panel_source=synthetic_setup["panel_path"],
            output_dir=synthetic_setup["output_dir"],
            recipes_filter=["non_existent_recipe"],
        )


# ---------- Phase D D5 build_feature_panel test ----------
# Per docs/specs/internal/ops/ml-track/stage-2-d5-walk-methodology-prereg.md.


def test_build_feature_panel_d2_default_first_diff_only(synthetic_setup):
    """D2 default: only `__diff` features in the wide panel; backward-compatible
    with all existing callers (apply_d5_features defaults to False)."""
    wide = t.build_feature_panel(synthetic_setup["panel_path"], train_year_max=2021)
    feature_cols = [c for c in wide.columns if c not in ("country", "year")]
    suffix_counts = {}
    for col in feature_cols:
        for suffix in ["__diff3y", "__diff5y", "__accel", "__momentum", "__zscore", "__diff"]:
            if col.endswith(suffix):
                suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
                break
    # D2 default: ONLY `__diff` columns; no D5 trajectory features
    assert "__diff" in suffix_counts
    assert "__momentum" not in suffix_counts
    assert "__zscore" not in suffix_counts
    assert "__diff3y" not in suffix_counts
    assert "__diff5y" not in suffix_counts
    assert "__accel" not in suffix_counts


def test_build_feature_panel_d5_emits_six_feature_classes(synthetic_setup):
    """D5: 6 feature classes per original indicator (`__diff`, `__momentum`,
    `__zscore`, `__diff3y`, `__diff5y`, `__accel`). Original raw rows dropped."""
    wide = t.build_feature_panel(synthetic_setup["panel_path"], train_year_max=2021,
                                  apply_d5_features=True)
    feature_cols = [c for c in wide.columns if c not in ("country", "year")]
    suffix_counts = {}
    for col in feature_cols:
        # Find the LAST trajectory suffix (so __diff doesn't shadow __diff3y)
        matched = None
        for suffix in ["__diff3y", "__diff5y", "__accel", "__momentum", "__zscore", "__diff"]:
            if col.endswith(suffix):
                matched = suffix
                break  # most-specific match wins via ordering
        if matched:
            suffix_counts[matched] = suffix_counts.get(matched, 0) + 1
    # Synthetic setup has 3 indicators, so each feature class should produce 3 columns.
    expected_classes = {"__diff", "__momentum", "__zscore", "__diff3y", "__diff5y", "__accel"}
    assert set(suffix_counts.keys()) == expected_classes, (
        f"missing feature classes: {expected_classes - set(suffix_counts.keys())}"
    )
    # Each class produces exactly N_indicators columns
    for cls, count in suffix_counts.items():
        assert count == 3, f"class {cls} has {count} cols, expected 3"
    # No raw original-indicator columns survived (e.g., 'IND-A' alone)
    raw_originals = {"IND-A", "IND-B", "IND-C"}
    surviving = raw_originals & set(feature_cols)
    assert not surviving, f"D5 must drop raw originals; found: {surviving}"


def test_build_feature_panel_d5_input_dim_grows_6x_vs_d2(synthetic_setup):
    """D5 input dimension is approximately 6x D2 baseline (one feature class
    per original indicator under D2; six under D5). Per pre-reg
    'input dimension grows ~5-6x'.

    Exact 6x ratio holds on this synthetic fixture (12 years of dense data,
    no all-NaN columns). On a real production panel with very-short-history
    indicators, some D5 feature columns may be all-NaN and dropped by
    pivot_to_wide implicitly, producing a ratio slightly below 6. This test
    is a regression-detection check on the synthetic fixture, NOT a
    production-accuracy assertion.
    """
    wide_d2 = t.build_feature_panel(synthetic_setup["panel_path"], train_year_max=2021)
    wide_d5 = t.build_feature_panel(synthetic_setup["panel_path"], train_year_max=2021,
                                     apply_d5_features=True)
    n_d2 = len([c for c in wide_d2.columns if c not in ("country", "year")])
    n_d5 = len([c for c in wide_d5.columns if c not in ("country", "year")])
    assert n_d5 == n_d2 * 6, (
        f"D5 should produce 6x D2 features on this synthetic fixture "
        f"(got D2={n_d2}, D5={n_d5}, ratio={n_d5/n_d2:.2f}x)"
    )


def test_run_training_d5_end_to_end_completes(synthetic_setup):
    """D5 training pipeline completes without crashing on synthetic data.

    Regression check that the apply_d5_features=True path through
    run_training doesn't break: builds D5 panel, trains backbones on
    expanded feature space, extracts leaves, fits heads, emits predictions.
    Not a quality test (synthetic data has no real signal) — purely a
    plumbing regression check that the pre-registered D5 architecture
    flag plumbs correctly through every stage.
    """
    summary = t.run_training(
        ranking_path=synthetic_setup["ranking_path"],
        events_dir=synthetic_setup["events_dir"],
        panel_source=synthetic_setup["panel_path"],
        output_dir=synthetic_setup["output_dir"] / "d5_run",
        apply_d5_features=True,
    )
    # Pipeline produced predictions
    pred_path = synthetic_setup["output_dir"] / "d5_run" / "predictions.json"
    assert pred_path.exists()
    pred_payload = json.loads(pred_path.read_text(encoding="utf-8"))
    preds = pred_payload.get("predictions", [])
    assert len(preds) > 0
    # Each prediction has the canonical schema
    for p in preds[:3]:
        assert "country" in p
        assert "year" in p
        assert "recipe_id" in p
        assert "predicted_probability" in p
    # All predicted probabilities bounded [0, 1] (pipeline correctness invariant)
    assert all(0.0 <= p["predicted_probability"] <= 1.0 for p in preds), \
        "predicted_probability must be in [0, 1] (calibration / sigmoid output)"
    # Summary dict has expected key from run_training
    assert "n_recipes_trained" in summary, \
        f"summary should report n_recipes_trained; got keys: {list(summary.keys())}"
