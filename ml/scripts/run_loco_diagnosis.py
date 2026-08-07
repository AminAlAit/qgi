"""# THROWAWAY -- one-shot diagnostic. Phase C step C1, Priya's LOCO
(Leave-One-Country-Out) diagnosis.

Per post-PoC trio convening (2026-05-05): test whether Stage 1 v0's
mean AUC=0.778 is REAL signal generalizing across countries, OR
country-fixed-effect leakage (model memorizing country IDs).

**Method:** for each held-out country X, retrain the FULL Stage 1
pipeline (backbone + per-recipe LR heads) on all data EXCLUDING X,
then predict on X's test-window rows. Aggregate per-recipe AUC over
the union of held-out countries' predictions.

**Interpretation:**
- LOCO-AUC ≈ in-sample AUC → model generalizes; Stage 1 result is real
- LOCO-AUC << in-sample AUC → model memorized country identities;
  Stage 1's score is fixed-effect leakage; foundation needs fixing
  before any further walks.

**Country selection (15 representative):**
- 5 stable democracies that ranked HIGH on civil_war anchors (the
  direct fixed-effect test): Norway, Sweden, Switzerland, Netherlands,
  Estonia
- 5 active conflicts the model "needs": Ukraine, Sudan, Myanmar, Yemen,
  Russia
- 5 middle-ground: Brazil, Indonesia, South Korea, Mexico, Turkiye

If holding out the 5 stable democracies craters AUC, that confirms
the contamination story — the model relies on knowing those countries
are "low risk" rather than learning low-risk dynamics.

If holding out the 5 conflict-active countries craters AUC, that says
the model relies on memorizing those specific high-risk profiles.

If LOCO-AUC stays close to in-sample for both groups, the model is
learning generalizable patterns.

Usage::

    python scripts/run_loco_diagnosis.py \
        --panel data/panel_104_2026_05_04.parquet \
        --events-dir ../qgi-data/events/curated \
        --rubric ../qgi-data/reference/ml-recipe-ranking-2026-05.json \
        --countries norway,sweden,switzerland,netherlands,estonia,ukraine,sudan,myanmar,yemen,russia,brazil,indonesia,south_korea,mexico,turkiye \
        --recipes elections_and_voting,civil_war_and_insurgency,mass_protest,terrorist_attack,migration_and_refugees \
        --out ../qgi-data/reference/loco-diagnosis-2026-05.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SRC_ROOT = REPO_ROOT / "src"
SHARED_ROOT = REPO_ROOT / "shared"
for _p in (str(SCRIPTS_ROOT), str(SRC_ROOT), str(SHARED_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from train_multitask_v0 import (  # noqa: E402
    DEFAULT_HYPERPARAMS,
    build_feature_panel,
    extract_leaf_features,
    load_event_labels,
    load_priority_recipes,
    predict_per_recipe,
    train_backbone,
    train_per_recipe_heads,
)
# Note: Beta calibration is intentionally NOT used in this diagnostic.
# AUC is rank-statistic and unaffected by monotone calibration; the
# diagnosis question is whether the BACKBONE+HEAD generalizes across
# countries, not whether the calibrator quality holds.

# Locked windows (match Stage 1 pre-reg)
TRAIN_YEAR_MAX = 2021
TEST_YEAR_MIN = 2022
TEST_YEAR_MAX = 2025
LABEL_WINDOW_LOWER = 2014


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--events-dir", type=Path, required=True)
    p.add_argument("--rubric", type=Path, required=True)
    p.add_argument("--countries", type=str, required=True,
                   help="Comma-separated country slugs to hold out one-at-a-time")
    p.add_argument("--recipes", type=str, default="",
                   help="Optional comma-separated recipe IDs to focus the diagnosis "
                        "(default: all rubric-eligible). Smaller list = faster.")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args()


def compute_auc_simple(probs: np.ndarray, labels: np.ndarray) -> float:
    """Bare-metal AUC; NaN if single-class."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    n_pos = int((labels == 1).sum())
    n_neg = int((labels == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    order = np.argsort(probs, kind="mergesort")
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(probs) + 1)
    sorted_p = probs[order]
    i = 0
    while i < len(sorted_p):
        j = i
        while j + 1 < len(sorted_p) and sorted_p[j + 1] == sorted_p[i]:
            j += 1
        if j > i:
            mr = ranks[order[i:j + 1]].mean()
            ranks[order[i:j + 1]] = mr
        i = j + 1
    s = ranks[labels == 1].sum()
    return float((s - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def train_and_predict_excluding(
    held_out_country: str,
    feature_panel: pd.DataFrame,
    label_wide: pd.DataFrame,
    recipe_ids: list[str],
    seed: int,
) -> tuple[pd.DataFrame, dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Train Stage 1 v0 pipeline excluding `held_out_country`, predict
    for it on the test window.

    Returns:
        held_out_test_df : test rows for the held-out country
        calibrated_preds : recipe_id -> predictions on held_out_test_df
        held_out_labels  : recipe_id -> ground truth labels
    """
    merged = feature_panel.merge(label_wide, on=["country", "year"], how="inner")
    if held_out_country not in set(merged["country"]):
        msg = f"held_out_country '{held_out_country}' not in merged frame"
        raise ValueError(msg)

    label_cols = [c for c in recipe_ids if c in merged.columns]
    feature_cols = [c for c in merged.columns
                    if c not in ("country", "year") and c not in label_cols]

    # Train: all countries EXCEPT held-out, year ≤ 2021
    train_mask = (merged["country"] != held_out_country) & (merged["year"] <= TRAIN_YEAR_MAX)
    # Held-out test: held_out country, 2022-2025
    held_out_mask = (merged["country"] == held_out_country) & \
                    (merged["year"] >= TEST_YEAR_MIN) & (merged["year"] <= TEST_YEAR_MAX)
    train_df = merged[train_mask].reset_index(drop=True)
    held_out_test_df = merged[held_out_mask].reset_index(drop=True)

    if held_out_test_df.empty:
        return held_out_test_df, {}, {}

    X_train = train_df[feature_cols].to_numpy(dtype=float)
    X_held = held_out_test_df[feature_cols].to_numpy(dtype=float)
    Y_train = train_df[label_cols].fillna(0).to_numpy(dtype=int)
    Y_held = held_out_test_df[label_cols].fillna(0).to_numpy(dtype=int)

    # Train backbone (use a small in-sample val split for early stopping; here
    # we just use the held-out as val placeholder since we ARE the eval target —
    # better: split train_df into train/val 90/10 to honor early stopping
    # without contaminating held-out test).
    rng = np.random.default_rng(seed)
    n_train = len(train_df)
    perm = rng.permutation(n_train)
    val_size = max(int(n_train * 0.1), 50)
    val_idx = perm[:val_size]
    tr_idx = perm[val_size:]
    boosters = train_backbone(
        X_train[tr_idx], Y_train[tr_idx],
        X_train[val_idx], Y_train[val_idx],
        DEFAULT_HYPERPARAMS, seed=seed,
    )

    leaf_train = extract_leaf_features(boosters, X_train)
    leaf_held = extract_leaf_features(boosters, X_held)

    heads = train_per_recipe_heads(leaf_train, Y_train, label_cols, seed=seed)
    raw_preds = predict_per_recipe(heads, leaf_held)

    # Calibrate on the held-out test set is wrong (cheating) — for LOCO we
    # report RAW predictions. Calibration is downstream concern. The
    # diagnosis question is whether the BACKBONE+HEAD generalizes.
    held_out_labels = {rid: Y_held[:, i] for i, rid in enumerate(label_cols)}
    return held_out_test_df, raw_preds, held_out_labels


def main() -> int:
    args = parse_args()

    countries = [c.strip().lower() for c in args.countries.split(",") if c.strip()]
    recipes_filter = [r.strip() for r in args.recipes.split(",") if r.strip()]

    print(f"[loco] held-out countries ({len(countries)}): {', '.join(countries)}",
          file=sys.stderr)
    if recipes_filter:
        print(f"[loco] recipes filter ({len(recipes_filter)}): {', '.join(recipes_filter)}",
              file=sys.stderr)

    # 1. Recipes
    recipes = load_priority_recipes(args.rubric, recipe_filter=recipes_filter or None)
    recipe_ids = [r["category_id"] for r in recipes]
    print(f"[loco] eligible recipes: {len(recipe_ids)}", file=sys.stderr)

    # 2. Labels (full window)
    label_window = (LABEL_WINDOW_LOWER, TEST_YEAR_MAX)
    print("[loco] loading labels...", file=sys.stderr)
    labels = load_event_labels(args.events_dir, recipe_ids, label_window, verified_only=True)
    label_wide = labels.pivot_table(
        index=["country", "year"], columns="recipe_id", values="label", aggfunc="first",
    ).reset_index()
    label_wide.columns.name = None

    # 3. Features (full panel)
    print("[loco] building feature panel...", file=sys.stderr)
    feature_panel = build_feature_panel(args.panel, train_year_max=TRAIN_YEAR_MAX)

    # 4. Per-country LOCO loop
    per_country_results: dict[str, dict[str, Any]] = {}
    pooled_preds: dict[str, list[float]] = {rid: [] for rid in recipe_ids}
    pooled_labels: dict[str, list[int]] = {rid: [] for rid in recipe_ids}

    for c in countries:
        t0 = time.time()
        print(f"[loco] holding out '{c}'...", file=sys.stderr, flush=True)
        try:
            held_df, preds, ho_labels = train_and_predict_excluding(
                c, feature_panel, label_wide, recipe_ids, args.seed,
            )
        except ValueError as e:
            print(f"[loco]   skipped ({e})", file=sys.stderr)
            per_country_results[c] = {"error": str(e)}
            continue

        if held_df.empty:
            print(f"[loco]   no test rows for {c}; skipping", file=sys.stderr)
            per_country_results[c] = {"n_test": 0, "per_recipe_auc": {}}
            continue

        per_recipe_auc: dict[str, dict] = {}
        for rid in recipe_ids:
            if rid not in preds:
                continue
            p = preds[rid]
            y = ho_labels[rid]
            auc = compute_auc_simple(p, y)
            per_recipe_auc[rid] = {
                "auc": auc,
                "n": int(p.size),
                "n_pos": int((y == 1).sum()),
                "n_neg": int((y == 0).sum()),
            }
            pooled_preds[rid].extend([float(x) for x in p])
            pooled_labels[rid].extend([int(x) for x in y])

        elapsed = time.time() - t0
        n_pos_total = int(sum(v["n_pos"] for v in per_recipe_auc.values()))
        per_country_results[c] = {
            "n_test_rows": int(len(held_df)),
            "n_pos_total": n_pos_total,
            "per_recipe_auc": per_recipe_auc,
            "elapsed_sec": round(elapsed, 1),
        }
        print(f"[loco]   {c}: {len(held_df)} test rows, {n_pos_total} positives, "
              f"{elapsed:.1f}s", file=sys.stderr)

    # 5. Pooled per-recipe LOCO AUC (across all held-out countries)
    print("[loco] computing pooled LOCO AUC per recipe...", file=sys.stderr)
    pooled_auc: dict[str, dict] = {}
    for rid in recipe_ids:
        p_arr = np.asarray(pooled_preds[rid], dtype=float)
        y_arr = np.asarray(pooled_labels[rid], dtype=int)
        pooled_auc[rid] = {
            "loco_auc_pooled": compute_auc_simple(p_arr, y_arr) if p_arr.size > 0 else float("nan"),
            "n_total": int(p_arr.size),
            "n_pos_total": int((y_arr == 1).sum()),
        }

    # 6. Write output
    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Phase C step C1 LOCO diagnosis -- tests whether Stage 1 v0's "
            "mean AUC=0.778 is real generalizing signal or country-fixed-"
            "effect leakage (model memorizing country IDs). For each "
            "held-out country, retrains the full Stage 1 pipeline on "
            "all-except-X, predicts on X's 2022-2025 test rows. Pooled "
            "LOCO-AUC across all held-out countries gives the answer."
        ),
        "method": {
            "algorithm": "leave-one-country-out CV with full backbone+head retrain",
            "panel": str(args.panel),
            "rubric": str(args.rubric),
            "label_window": [LABEL_WINDOW_LOWER, TEST_YEAR_MAX],
            "train_year_max": TRAIN_YEAR_MAX,
            "test_year_range": [TEST_YEAR_MIN, TEST_YEAR_MAX],
            "calibration": "RAW predictions (uncalibrated) -- diagnosis is on "
                           "backbone+head generalization, not calibrator quality",
        },
        "consult_attribution": (
            "Diagnosis recommended by Priya Venkataraman-Szabo (Stats 6/ML 2, "
            "Majles seat #22) at 2026-05-05 trio convening on the F5_FALLBACK "
            "verdict from elections_and_voting walk. The diagnostic question: "
            "if LOCO-AUC craters vs Stage 1's in-sample AUC=0.778, the model "
            "is memorizing country identity rather than learning dynamic "
            "risk signals; Tariq's binding warning on country-fixed-effect "
            "contamination then becomes a MUST-FIX-FIRST blocker before "
            "any Stage 2 walks."
        ),
        "countries_held_out": countries,
        "recipes_evaluated": recipe_ids,
        "per_country": per_country_results,
        "pooled_loco_auc_per_recipe": pooled_auc,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"[loco] wrote {args.out}", file=sys.stderr)

    # 7. Quick stdout summary
    print("\n=== Pooled LOCO-AUC per recipe (vs Stage 1 in-sample baseline) ===", file=sys.stderr)
    print(f"{'recipe':<40} {'LOCO-AUC':>10} {'n':>5} {'n_pos':>6}", file=sys.stderr)
    for rid, v in pooled_auc.items():
        auc_str = f"{v['loco_auc_pooled']:.4f}" if not np.isnan(v["loco_auc_pooled"]) else "NaN"
        print(f"{rid:<40} {auc_str:>10} {v['n_total']:>5} {v['n_pos_total']:>6}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
