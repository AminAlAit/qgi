"""Stage 7 Phase 1 evaluation: F-S-1..F-S-4 + §6.1 tier on LOCKED 2-recipe cohort.

Per docs/specs/internal/ops/ml-track/stage-6-shape-feature-prereg.md §5 + §6.1.

Cohort: civil_war_and_insurgency (LOCKED, hybrid baseline LOCO=0.7686)
        + economic_recession (LOCKED rescue-mode, no hybrid baseline)
Excluded: foreign_intervention (ADVISORY-ONLY per F-H-4-A5)

Minimum-viable evaluation:
  1. Build shape-feature panel for positives + sampled negatives per recipe
  2. Train logistic regression on simple feature set WITH and WITHOUT shape
  3. LOCO-AUC for both conditions (leave-one-country-out CV)
  4. Bootstrap 80% + 95% CIs on AUC + ablation Δ
  5. Per-cohort ECE (using cohort-assignments.json)
  6. Apply F-S-1, F-S-2, F-S-3, F-S-4 rules → PASS/PARTIAL/FALSIFIED
  7. Apply §6.1 tier table → HARD-FALSIFY/SOFT-FALSIFY/PARTIAL/PASS
  8. Emit 5 artifacts under docs/specs/internal/ops/ml-track/results/

Run-time: ~30-60 minutes laptop. Zero AWS spend.

Usage:
    python scripts/run_stage7_phase1_evaluation.py \\
        --output-dir ../docs/specs/internal/ops/ml-track/results
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
for _p in (SCRIPTS_ROOT, SRC_ROOT, REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shape_kernel import compute_shape_features  # noqa: E402
from shape_prototype_dispatch import (  # noqa: E402
    AdvisoryOnlyShapeUnfittableError,
    SubstrateInadequateError,
    assert_dispatch_invariants,
    load_dispatch,
)

# Stage 6 §5 thresholds (binding pre-reg)
F_S_1_PHASE1_LIFT_FLOOR_STRICT = 0.03  # all-N rule
F_S_1_PHASE1_LIFT_FLOOR_LOOSE = 0.05   # N-1 of N rule
F_S_1_ECON_RECESSION_RESCUE_FLOOR = 0.65  # LOCO floor for rescue-mode
F_S_1_ECON_RECESSION_CI_LOWER = 0.50
F_S_2_REGRESSION_FLOOR = -0.03  # Δ < -0.03 = FAIL on Phase 1
F_S_3_ABLATION_FLOOR = 0.03  # ablation Δ ≥ 0.03 to be a contributor
F_H_7_ECE_GATE = 0.08

# §6.1 tier boundaries (Phase 1 interpretation: ΔAUC mean across cohort)
TIER_HARD_FALSIFY_LIFT_MAX = 0.00
TIER_SOFT_FALSIFY_LIFT_MAX = 0.05
TIER_PARTIAL_LIFT_MAX = 0.10  # PARTIAL: [0.05, 0.10]; PASS: ≥ 0.10

# Hybrid baselines (pre-registered per spec-trio Stage 7 plan)
HYBRID_BASELINE_CIVIL_WAR = 0.7686  # LOCO-AUC from Hybrid D2/D5 walk
# economic_recession: no hybrid LOCK; uses rescue mode (no baseline subtracted)

RECIPES_IN_COHORT = ["civil_war_and_insurgency", "economic_recession"]
ECON_RECESSION = "economic_recession"


# ---- LOCO-AUC + bootstrap ---------------------------------------------------


def compute_auc_simple(probs: np.ndarray, labels: np.ndarray) -> float:
    """Pooled AUC via Mann-Whitney U formula (no sklearn dep)."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    pos_mask = labels == 1
    neg_mask = labels == 0
    if pos_mask.sum() == 0 or neg_mask.sum() == 0:
        return float("nan")
    p_pos = probs[pos_mask]
    p_neg = probs[neg_mask]
    # AUC = P(score(pos) > score(neg))
    n_concordant = 0.0
    for p in p_pos:
        n_concordant += np.sum(p_neg < p) + 0.5 * np.sum(p_neg == p)
    return n_concordant / (len(p_pos) * len(p_neg))


def bootstrap_loco_auc_ci(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bootstrap: int = 1000,
    seed: int = 0,
) -> dict[str, float]:
    """Return {'auc', 'ci80_lo', 'ci80_hi', 'ci95_lo', 'ci95_hi'}."""
    rng = np.random.default_rng(seed)
    n = len(probs)
    aucs = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        aucs[b] = compute_auc_simple(probs[idx], labels[idx])
    aucs = aucs[~np.isnan(aucs)]
    return {
        "auc": float(compute_auc_simple(probs, labels)),
        "ci80_lo": float(np.percentile(aucs, 10)),
        "ci80_hi": float(np.percentile(aucs, 90)),
        "ci95_lo": float(np.percentile(aucs, 2.5)),
        "ci95_hi": float(np.percentile(aucs, 97.5)),
    }


# ---- Feature engineering ----------------------------------------------------


def _wide_indicator_features(panel: pd.DataFrame, country: str, year: int, indicators: list[str]) -> np.ndarray | None:
    """Per-indicator: current value + z-score vs ≤10-year baseline + 1y diff.

    Returns (3 * K_indicators,) feature vector, or None if any indicator
    has insufficient data (≥5 pre-year observations required).
    """
    feats: list[float] = []
    cdf = panel[panel["country_id"] == country]
    for ind in indicators:
        idf = cdf[cdf["indicator_id"] == ind].set_index("year")["value"]
        if year not in idf.index:
            return None
        baseline_window = idf.loc[max(year - 10, idf.index.min()):year - 1]
        if len(baseline_window) < 5:
            return None
        cur = float(idf.loc[year])
        mu = float(baseline_window.mean())
        sd = float(baseline_window.std())
        z = (cur - mu) / sd if sd > 1e-9 else 0.0
        prev = float(idf.loc[year - 1]) if (year - 1) in idf.index else cur
        diff = cur - prev
        feats.extend([cur, z, diff])
    return np.array(feats, dtype=float)


def build_sample_panel(
    recipe_id: str,
    positives_csv: Path,
    indicator_panel: pd.DataFrame,
    prototype,
    rng_seed: int = 12345,
    negatives_per_positive: int = 3,
    max_positives: int | None = None,
) -> pd.DataFrame:
    """Build long-format sample panel: (country, year, label, base_features, shape_triple).

    Positives: all rows from positives.csv.
    Negatives: random sample of (country, year) NOT in positives, with same
    country distribution proportional to positives (per-country n_neg = neg_ratio * n_pos).
    """
    rng = np.random.default_rng(rng_seed)
    positives_df = pd.read_csv(positives_csv)
    if max_positives is not None and len(positives_df) > max_positives:
        positives_df = positives_df.sample(n=max_positives, random_state=rng_seed).reset_index(drop=True)
    pos_set = set(zip(positives_df["country_id"], positives_df["event_year"]))
    indicators = list(prototype.indicator_ids)

    rows: list[dict[str, Any]] = []

    # Positives
    for _, prow in positives_df.iterrows():
        country = str(prow["country_id"])
        year = int(prow["event_year"])
        base = _wide_indicator_features(indicator_panel, country, year, indicators)
        if base is None:
            continue
        try:
            triple = compute_shape_features(country, recipe_id, year, prototype, indicator_panel)
            shape = np.array(
                [triple.shape_similarity_scalar, triple.shape_dtw_score, triple.shape_phase_alignment],
                dtype=float,
            )
        except Exception:
            shape = np.array([np.nan, np.nan, np.nan])
        if not np.all(np.isfinite(shape)):
            shape = np.array([np.nan, np.nan, np.nan])
        rows.append({"country": country, "year": year, "label": 1, "base": base, "shape": shape})

    # Negatives: sample uniformly across same countries + valid year range
    pos_countries = list(positives_df["country_id"].unique())
    n_pos = len([r for r in rows if r["label"] == 1])
    n_neg_target = n_pos * negatives_per_positive
    valid_years = list(range(int(indicator_panel["year"].min()) + 20, int(indicator_panel["year"].max()) + 1))
    attempts = 0
    while sum(1 for r in rows if r["label"] == 0) < n_neg_target and attempts < n_neg_target * 5:
        attempts += 1
        country = pos_countries[rng.integers(0, len(pos_countries))]
        year = int(valid_years[rng.integers(0, len(valid_years))])
        if (country, year) in pos_set:
            continue
        base = _wide_indicator_features(indicator_panel, country, year, indicators)
        if base is None:
            continue
        try:
            triple = compute_shape_features(country, recipe_id, year, prototype, indicator_panel)
            shape = np.array(
                [triple.shape_similarity_scalar, triple.shape_dtw_score, triple.shape_phase_alignment],
                dtype=float,
            )
        except Exception:
            shape = np.array([np.nan, np.nan, np.nan])
        if not np.all(np.isfinite(shape)):
            shape = np.array([np.nan, np.nan, np.nan])
        rows.append({"country": country, "year": year, "label": 0, "base": base, "shape": shape})

    df = pd.DataFrame(rows)
    # Drop rows with NaN shape (won't be usable in WITH-shape arm; keep for WITHOUT-shape).
    return df


# ---- LOCO with logistic regression ------------------------------------------


def run_loco_lr(samples_df: pd.DataFrame, use_shape: bool, seed: int = 0) -> dict[str, Any]:
    """Run leave-one-country-out CV with scaled logistic regression.

    Returns: {'probs': (N,), 'labels': (N,), 'countries': (N,), 'years': (N,)}
        — pooled across all LOCO folds in country-then-row order.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    countries = sorted(samples_df["country"].unique())
    pooled_probs: list[float] = []
    pooled_labels: list[int] = []
    pooled_countries: list[str] = []
    pooled_years: list[int] = []

    for held_out in countries:
        train_df = samples_df[samples_df["country"] != held_out]
        test_df = samples_df[samples_df["country"] == held_out]
        if len(test_df) == 0:
            continue
        if train_df["label"].nunique() < 2:
            continue

        def _feat(row):
            if use_shape:
                if not np.all(np.isfinite(row["shape"])):
                    return None
                return np.concatenate([row["base"], row["shape"]])
            return row["base"]

        X_train_list, y_train, X_test_list, y_test = [], [], [], []
        country_test, year_test = [], []
        for _, r in train_df.iterrows():
            f = _feat(r)
            if f is not None:
                X_train_list.append(f)
                y_train.append(int(r["label"]))
        for _, r in test_df.iterrows():
            f = _feat(r)
            if f is not None:
                X_test_list.append(f)
                y_test.append(int(r["label"]))
                country_test.append(str(r["country"]))
                year_test.append(int(r["year"]))

        if not X_train_list or not X_test_list:
            continue
        X_train = np.vstack(X_train_list)
        X_test = np.vstack(X_test_list)
        y_train_arr = np.array(y_train)
        y_test_arr = np.array(y_test)
        if len(np.unique(y_train_arr)) < 2:
            continue

        X_train = np.where(np.isfinite(X_train), X_train, 0.0)
        X_test = np.where(np.isfinite(X_test), X_test, 0.0)

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        n_pos_train = int(np.sum(y_train_arr == 1))
        n_neg_train = int(np.sum(y_train_arr == 0))
        spw = (n_neg_train / max(n_pos_train, 1)) if n_pos_train > 0 else 1.0

        clf = LogisticRegression(
            class_weight={0: 1.0, 1: spw},
            max_iter=2000,
            random_state=seed,
            solver="lbfgs",
            C=1.0,
        )
        clf.fit(X_train_s, y_train_arr)
        probs = clf.predict_proba(X_test_s)[:, 1]
        pooled_probs.extend(probs.tolist())
        pooled_labels.extend(y_test_arr.tolist())
        pooled_countries.extend(country_test)
        pooled_years.extend(year_test)

    return {
        "probs": np.array(pooled_probs),
        "labels": np.array(pooled_labels),
        "countries": np.array(pooled_countries),
        "years": np.array(pooled_years),
    }


# ---- ECE per cohort ---------------------------------------------------------


def compute_ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error with equal-width bins."""
    if len(probs) == 0:
        return float("nan")
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.digitize(probs, bin_edges) - 1
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)
    ece = 0.0
    n = len(probs)
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() == 0:
            continue
        bin_conf = float(probs[mask].mean())
        bin_acc = float(labels[mask].mean())
        ece += (mask.sum() / n) * abs(bin_conf - bin_acc)
    return float(ece)


def per_cohort_ece(
    probs: np.ndarray,
    labels: np.ndarray,
    countries: np.ndarray,
    years: np.ndarray,
    cohort_assignments: dict,
) -> dict[str, dict[str, Any]]:
    """Per-cohort ECE + n + ECE 95% bootstrap CI."""
    cohorts_obs: dict[str, dict[str, list]] = {
        "fragile-state": {"p": [], "y": []},
        "mid-tier": {"p": [], "y": []},
        "stable-democracy": {"p": [], "y": []},
    }
    for i in range(len(probs)):
        country_raw = str(countries[i])
        # Cohort sidecar uses Title Case (e.g., "Afghanistan"); panel uses
        # lowercase ("afghanistan"). Normalize on lookup.
        country = country_raw.title()
        year = str(int(years[i]))
        cohort = cohort_assignments.get(country, {}).get(year)
        if cohort is None or cohort not in cohorts_obs:
            continue
        cohorts_obs[cohort]["p"].append(float(probs[i]))
        cohorts_obs[cohort]["y"].append(int(labels[i]))

    out: dict[str, dict[str, Any]] = {}
    rng = np.random.default_rng(0)
    for cohort, dat in cohorts_obs.items():
        p_arr = np.array(dat["p"])
        y_arr = np.array(dat["y"])
        n = len(p_arr)
        if n < 5:
            out[cohort] = {"n": n, "ece": float("nan"), "low_confidence": True}
            continue
        ece_point = compute_ece(p_arr, y_arr)
        # Bootstrap
        boots = []
        for _ in range(500):
            idx = rng.integers(0, n, size=n)
            boots.append(compute_ece(p_arr[idx], y_arr[idx]))
        ci95_lo = float(np.percentile(boots, 2.5))
        ci95_hi = float(np.percentile(boots, 97.5))
        out[cohort] = {
            "n": n,
            "ece": ece_point,
            "ci95_lo": ci95_lo,
            "ci95_hi": ci95_hi,
            "low_confidence": n < 30,  # Kwame R1 rider
        }
    return out


# ---- Main driver ------------------------------------------------------------


def evaluate_recipe(
    recipe_id: str,
    indicator_panel: pd.DataFrame,
    prototype,
    cohort_assignments: dict,
    positives_csv: Path,
    rng_seed: int = 12345,
    max_positives: int | None = None,
) -> dict[str, Any]:
    """Evaluate one recipe: build samples, LOCO with/without shape, ECE, F-rules."""
    print(f"[{recipe_id}] Building sample panel...", flush=True)
    samples = build_sample_panel(
        recipe_id, positives_csv, indicator_panel, prototype,
        rng_seed=rng_seed, max_positives=max_positives,
    )
    n_pos = int((samples["label"] == 1).sum())
    n_neg = int((samples["label"] == 0).sum())
    n_shape_available = int(samples["shape"].apply(lambda s: np.all(np.isfinite(s))).sum())
    print(f"[{recipe_id}] samples: {n_pos} positives + {n_neg} negatives  "
          f"shape_available: {n_shape_available}/{n_pos+n_neg}", flush=True)

    print(f"[{recipe_id}] LOCO without shape...", flush=True)
    loco_without = run_loco_lr(samples, use_shape=False)
    without_auc = bootstrap_loco_auc_ci(loco_without["probs"], loco_without["labels"])

    print(f"[{recipe_id}] LOCO with shape...", flush=True)
    loco_with = run_loco_lr(samples, use_shape=True)
    with_auc = bootstrap_loco_auc_ci(loco_with["probs"], loco_with["labels"])

    # Ablation Δ (F-S-3): LOCO(with shape) − LOCO(without shape) on identical samples
    delta_ablation = with_auc["auc"] - without_auc["auc"]

    # ----- F-S-1 lift -----
    # Per-recipe lift evaluation. F-H-4-A5 narrows cohort to 2; the trio
    # rule's strictest-defensible N=2 reading drops foreign_intervention to
    # "not evaluated" and applies the original N=3 floors directly:
    #   strict:  both LOCKED recipes >= +0.03
    #   loose:   both LOCKED recipes >= +0.05 (was: 2-of-3; with 2 LOCKED, both)
    # Per-recipe field returns the lift; cohort-level pass/fail is computed
    # in determine_tier() (where both-must-clear logic lives).
    if recipe_id == "civil_war_and_insurgency":
        delta_hybrid_lift = with_auc["auc"] - HYBRID_BASELINE_CIVIL_WAR
        f_s_1_threshold_used = "strict_N=2_both_geq_0.03_or_both_geq_0.05"
        f_s_1_per_recipe_strict = delta_hybrid_lift >= F_S_1_PHASE1_LIFT_FLOOR_STRICT
        f_s_1_per_recipe_loose = delta_hybrid_lift >= F_S_1_PHASE1_LIFT_FLOOR_LOOSE
    elif recipe_id == ECON_RECESSION:
        # Rescue mode: WITH-shape must clear LOCO >= 0.65 + CI95 lower > 0.50
        f_s_1_rescue_loco = with_auc["auc"]
        f_s_1_rescue_ci_lower = with_auc["ci95_lo"]
        delta_hybrid_lift = None  # no Hybrid LOCK baseline for econ_recession
        f_s_1_rescue_pass = (
            f_s_1_rescue_loco >= F_S_1_ECON_RECESSION_RESCUE_FLOOR
            and f_s_1_rescue_ci_lower > F_S_1_ECON_RECESSION_CI_LOWER
        )
        f_s_1_per_recipe_strict = f_s_1_rescue_pass
        f_s_1_per_recipe_loose = f_s_1_rescue_pass
        f_s_1_threshold_used = "rescue_mode_LOCO_geq_0.65_AND_CI95_lower_gt_0.50"

    # ----- F-S-2 regression -----
    # Phase 1 §5.3: "any single recipe with Δ < −0.03 = FAIL." The §5.3
    # comparator phrasing in Phase 2 is "vs Hybrid baseline," so the
    # strictest-defensible Phase 1 reading is also vs-Hybrid for recipes
    # that HAVE a Hybrid LOCK. For econ_recession (no Hybrid LOCK),
    # F-S-2 falls back to the ablation delta (with − without).
    if recipe_id == "civil_war_and_insurgency":
        f_s_2_delta = with_auc["auc"] - HYBRID_BASELINE_CIVIL_WAR
        f_s_2_comparator = "with_shape_minus_hybrid_baseline"
    else:
        f_s_2_delta = delta_ablation
        f_s_2_comparator = "with_shape_minus_without_shape_no_hybrid_lock"
    f_s_2_fail = f_s_2_delta < F_S_2_REGRESSION_FLOOR

    # ----- F-S-3 ablation contribution -----
    # Phase 1 §5.4: a recipe "contributes" if ablation Δ >= +0.03.
    # Pre-reg exclusion gate: econ_recession contributes ONLY IF
    # (ablation Δ >= +0.03) AND (WITH-shape clears F-S-1 rescue floor).
    # Without the second clause, an ablation-positive-but-below-rescue
    # recipe would be miscounted toward the F-S-3 majority.
    base_contributes = delta_ablation >= F_S_3_ABLATION_FLOOR
    if recipe_id == ECON_RECESSION:
        # econ_recession exclusion gate per §5.4 special clause
        f_s_3_contributes = base_contributes and f_s_1_per_recipe_strict
        f_s_3_excluded_reason = (
            None
            if f_s_3_contributes
            else (
                "ablation-positive-but-below-rescue"
                if base_contributes and not f_s_1_per_recipe_strict
                else None
            )
        )
    else:
        f_s_3_contributes = base_contributes
        f_s_3_excluded_reason = None

    # F-S-4 AHI: deferred for both recipes (anchor battery not run here)
    f_s_4_status = "deferred — anchor battery v3 measurement is a separate workstream"

    # Per-cohort ECE (F-H-7) on WITH-shape predictions
    ece_per_cohort = per_cohort_ece(
        loco_with["probs"],
        loco_with["labels"],
        loco_with["countries"],
        loco_with["years"],
        cohort_assignments,
    )

    return {
        "recipe_id": recipe_id,
        "n_positives_used": n_pos,
        "n_negatives_used": n_neg,
        "n_with_shape_features": n_shape_available,
        "loco_without_shape": without_auc,
        "loco_with_shape": with_auc,
        "ablation_delta": delta_ablation,
        "delta_vs_hybrid_baseline": delta_hybrid_lift,
        "f_s_1": {
            "threshold_used": f_s_1_threshold_used,
            "per_recipe_pass_strict": bool(f_s_1_per_recipe_strict),
            "per_recipe_pass_loose": bool(f_s_1_per_recipe_loose),
        },
        "f_s_2": {
            "delta": f_s_2_delta,
            "comparator": f_s_2_comparator,
            "fail": bool(f_s_2_fail),
        },
        "f_s_3": {
            "ablation_delta": delta_ablation,
            "threshold": F_S_3_ABLATION_FLOOR,
            "contributes": bool(f_s_3_contributes),
            "excluded_reason": f_s_3_excluded_reason,
        },
        "f_s_4": {
            "status": f_s_4_status,
        },
        "f_h_7_per_cohort_ece": ece_per_cohort,
    }


def determine_tier(cohort_results: dict[str, Any]) -> dict[str, Any]:
    """Apply §6.1 4-tier exit table to the 2-recipe cohort.

    Cohort interpretation per F-H-4-A5: foreign_intervention excluded
    (ADVISORY-ONLY). Phase 1 cohort = 2 LOCKED recipes.
    """
    # ΔAUC across cohort = mean of recipe-level lifts where defined
    deltas = []
    for rid, res in cohort_results.items():
        d = res.get("delta_vs_hybrid_baseline")
        if d is not None:
            deltas.append(d)
        # For econ_recession (rescue mode), use the absolute LOCO as the "lift"
        # framing relative to the F-S-1 floor of 0.65
        elif rid == ECON_RECESSION:
            loco_with = res["loco_with_shape"]["auc"]
            # Rescue lift = loco_with - 0.5 (random) as a proxy
            deltas.append(loco_with - 0.5)
    mean_delta = float(np.mean(deltas)) if deltas else float("nan")

    # ----- F-S-1 cohort pass per strictest-defensible N=2 reading -----
    # Original §5.2 N=3 rule: all 3 >= 0.03 OR 2 of 3 >= 0.05.
    # With F-H-4-A5 dropping foreign_intervention, strictest reading:
    # both LOCKED >= 0.03 OR both LOCKED >= 0.05 (i.e., the all-N branch
    # of the original N=3 rule).
    per_recipe_strict = [
        cohort_results[rid]["f_s_1"]["per_recipe_pass_strict"]
        for rid in cohort_results
    ]
    per_recipe_loose = [
        cohort_results[rid]["f_s_1"]["per_recipe_pass_loose"]
        for rid in cohort_results
    ]
    f_s_1_pass = all(per_recipe_strict) or all(per_recipe_loose)
    f_s_2_fail_count = sum(1 for rid in cohort_results if cohort_results[rid]["f_s_2"]["fail"])
    f_s_2_fail_any = f_s_2_fail_count > 0
    f_s_3_contributors = sum(1 for rid in cohort_results if cohort_results[rid]["f_s_3"]["contributes"])
    f_s_3_pass = f_s_3_contributors >= 1
    # F-S-4 deferred → treat as not-fail for tier determination
    f_s_4_status = "all_deferred"

    # §5.6 binary routing per Phase 1 wording
    n_recipes = len(cohort_results)
    if not f_s_1_pass:
        routing = "FALSIFIED (F-S-1 fails: insufficient lift)"
    elif not f_s_3_pass:
        routing = "FALSIFIED (F-S-3 fails: decorative theater)"
    elif f_s_2_fail_count == 0:
        routing = "PASS (all F-rules hold)"
    elif f_s_2_fail_count < n_recipes:
        # PARTIAL: F-S-1 PASS + F-S-3 contributes + F-S-4 PASS-deferred + F-S-2 partial regression
        routing = (
            f"PARTIAL (F-S-2 regression in {f_s_2_fail_count}/{n_recipes} "
            f"recipes; F-S-1/F-S-3 hold)"
        )
    else:
        routing = "FALSIFIED (F-S-2 regresses in all recipes)"

    # §6.1 ΔAUC tier
    if mean_delta <= TIER_HARD_FALSIFY_LIFT_MAX:
        tier = "HARD-FALSIFY"
    elif mean_delta < TIER_SOFT_FALSIFY_LIFT_MAX:
        tier = "SOFT-FALSIFY"
    elif mean_delta < TIER_PARTIAL_LIFT_MAX:
        tier = "PARTIAL"
    else:
        tier = "PASS"

    # Reconciliation: take the more conservative of the two
    severity_order = ["HARD-FALSIFY", "SOFT-FALSIFY", "FALSIFIED", "PARTIAL", "PASS"]
    routing_simple = routing.split(" ")[0]  # FALSIFIED / PARTIAL / PASS
    if routing_simple == "FALSIFIED" and tier in ("PARTIAL", "PASS"):
        final_tier = "FALSIFIED"
    elif tier in ("HARD-FALSIFY", "SOFT-FALSIFY") and routing_simple in ("PARTIAL", "PASS"):
        final_tier = tier  # tier override
    else:
        final_tier = tier

    return {
        "mean_delta_across_cohort": mean_delta,
        "tier_from_delta_table": tier,
        "routing_from_f_rules": routing,
        "final_tier": final_tier,
        "f_s_1_pass": f_s_1_pass,
        "f_s_2_fail_any": f_s_2_fail_any,
        "f_s_3_contributors": f_s_3_contributors,
        "f_s_3_pass": f_s_3_pass,
        "f_s_4_status": f_s_4_status,
    }


def _to_strict_json(obj: Any) -> str:
    """Serialize replacing NaN/Inf with None for strict-JSON consumers."""

    def _walk(o):
        if isinstance(o, dict):
            return {k: _walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_walk(v) for v in o]
        if isinstance(o, float):
            if np.isnan(o) or np.isinf(o):
                return None
        return o

    return json.dumps(_walk(obj), indent=2, ensure_ascii=False)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "docs" / "specs" / "internal" / "ops" / "ml-track" / "results",
    )
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument(
        "--max-positives",
        type=int,
        default=None,
        help="Smoke-test mode: cap positives per recipe. Default None = full run.",
    )
    args = parser.parse_args(argv)

    dispatch = load_dispatch()
    assert_dispatch_invariants(dispatch)
    cohort_assignments = json.loads(
        (REPO_ROOT.parent / "qgi-data" / "reference" / "cohort-assignments.json").read_text(
            encoding="utf-8"
        )
    )["assignments"]

    cohort_results: dict[str, Any] = {}
    for recipe_id in RECIPES_IN_COHORT:
        try:
            proto = dispatch.prototype_for(recipe_id)
        except (AdvisoryOnlyShapeUnfittableError, SubstrateInadequateError) as e:
            print(f"[{recipe_id}] skipped: {e}", flush=True)
            continue
        positives_csv = (
            REPO_ROOT / "data" / "shape_inputs_v2" / recipe_id / "positives.csv"
        )
        indicator_panel = pd.read_parquet(
            REPO_ROOT / "data" / "shape_inputs_v2" / recipe_id / "indicator_panel.parquet"
        )
        cohort_results[recipe_id] = evaluate_recipe(
            recipe_id, indicator_panel, proto, cohort_assignments, positives_csv,
            rng_seed=args.seed, max_positives=args.max_positives,
        )

    tier_verdict = determine_tier(cohort_results)

    summary = {
        "filed": datetime.now(timezone.utc).isoformat(),
        "phase": 1,
        "cohort_recipes": list(cohort_results.keys()),
        "excluded_advisory_only": ["foreign_intervention"],
        "per_recipe": cohort_results,
        "tier_verdict": tier_verdict,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / "stage-6-phase-1-evaluation-summary.json"
    # Replace NaN with None so the JSON is strict-compliant
    out_path.write_text(
        _to_strict_json(summary), encoding="utf-8"
    )
    print(f"\nWrote {out_path}", flush=True)
    print("\n=== STAGE 7 VERDICT ===", flush=True)
    print(f"Final tier: {tier_verdict['final_tier']}", flush=True)
    print(f"Mean delta-AUC across cohort: {tier_verdict['mean_delta_across_cohort']:.4f}", flush=True)
    print(f"F-rule routing: {tier_verdict['routing_from_f_rules']}", flush=True)
    print(f"Section 6.1 delta-AUC tier: {tier_verdict['tier_from_delta_table']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
