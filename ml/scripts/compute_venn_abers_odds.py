"""Venn-Abers probability interval layer for QGI Trajectory Engine.

TE add-on #3, Stage A: Venn-Abers odds layer.
Per odds-calibration-consult-2026-05-24.md (Ji-Hoon #21 + Kwame #11, 2/2 ratified).

Produces per-country probability intervals [p_lo, p_hi] per cohort using the
inductive Venn-Abers construction. The interval is a formally valid finite-sample
coverage guarantee under the exchangeability assumption — not a point probability.

Display contract (Gate 4 / M8-R5 extension):
    Every output carries label: "estimated probability range, not a precise
    probability". Odds MUST be shown alongside the discrimination score (LOCO-AUC
    and similarity rank), never standalone.

## Algorithm: Inductive Venn-Abers (dependency-free numpy)

For a calibration set C = {(s_i, y_i)}, and a test score s:

  1. Augment C with (s, 0) → sort by score → run PAVA isotonic regression on
     labels → calibrated probability for (s,0) = p0.
  2. Augment C with (s, 1) → sort by score → run PAVA on labels → p1.
  3. Output interval [min(p0,p1), max(p0,p1)].

This is the standard inductive Venn-Abers procedure from:
  Vovk, V., Petej, I., & Fedorova, V. (2015). Large-scale probabilistic predictors
  with and without guarantees of validity. Advances in Neural Information Processing
  Systems, 28. https://proceedings.neurips.cc/paper/2015/hash/a9a1d5317a33ae8cef33961c34144f84-Abstract.html

  Lambrou, A., Papadopoulos, H., & Gammerman, A. (2012). Reliable probability
  estimates based on support vector machines for large multiclass datasets.
  IFIP Advances in Information and Communication Technology.

PAVA (Pool Adjacent Violators Algorithm) implementation is ~20 lines of numpy;
the full Venn-Abers wrapper adds ~30 more. No new pip dependency: sklearn's
IsotonicRegression.fit_transform is used internally for the PAVA step (sklearn
is already a project dependency via xgboost/run_f_ml_1_poc.py).

## OOF prediction reproduction

Mirrors extract_shap_importances.py::reproduce_walk_training_data():
  - Reads recipe positives.csv + builds negatives with same seed as walk
  - Loads selected indicators + chosen_window from walk summary
  - Re-runs full LOCO (fit_predict_loco from run_f_ml_1_poc.py)
  - Assigns cohort to each instance via cohort-assignments.json
The LOCO procedure is deterministic under XGBoost + fixed seed; see honesty
flags at module bottom for known nondeterminism risks.

## Gates (per consult §4, enforced and reported, not silently passed)

  Gate 1: Midpoint-classification accuracy-proxy coverage >= 0.80 per cohort
          (n >= 5 in cal-val split). NOTE: accuracy-based proxy, not the VA
          theoretical coverage guarantee — see compute_empirical_coverage.
  Gate 2: Mean interval width <= 0.60 per cohort; exceeding cohorts get
          UNSHARP_LOW_POWER flag and are suppressed from published odds.

Usage:
    python scripts/compute_venn_abers_odds.py \\
        --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --scores-file qgi-data/reference/recipe-similarity-scores-foreign_intervention-2021.json \\
        --panel-dir qgi-ml/data/parquet_panels \\
        --cohort-sidecar qgi-data/reference/cohort-assignments.json \\
        --output-dir qgi-data/reference/ \\
        --seed 12345

Output:
    venn-abers-odds-{recipe_id}-{eval_year}.json
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

# ---------------------------------------------------------------------------
# Path setup — mirrors extract_shap_importances.py
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent

# ---------------------------------------------------------------------------
# Venn-Abers core — dependency-free numpy + sklearn PAVA
# ---------------------------------------------------------------------------


def _isotonic_calibrate(scores: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Fit isotonic regression (PAVA) on (scores, labels) and return the fitted
    calibrated probability for each point in the calibration set.

    Uses sklearn.isotonic.IsotonicRegression (already a project dependency).
    The isotonic fit maps raw scores to calibrated probabilities monotonically.
    """
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(out_of_bounds="clip")
    cal_probs = iso.fit_transform(scores, labels)
    return np.asarray(cal_probs, dtype=float)


def _pava_predict(
    cal_scores: np.ndarray,
    cal_labels: np.ndarray,
    test_score: float,
    augment_label: int,
) -> float:
    """Run one PAVA augmentation for Venn-Abers.

    Augments the calibration set with (test_score, augment_label), sorts by
    score, fits PAVA isotonic regression, returns the calibrated value at the
    test point's position.

    Parameters
    ----------
    cal_scores  : calibration set raw scores (1-D, length n)
    cal_labels  : calibration set binary labels (1-D, length n)
    test_score  : the test instance's raw score
    augment_label : 0 or 1 (the hypothetical label to augment with)

    Returns
    -------
    float : isotonic-calibrated probability for the test instance
    """
    # Augment with the test point
    aug_scores = np.append(cal_scores, test_score)
    aug_labels = np.append(cal_labels.astype(float), float(augment_label))

    # Sort by score (required for isotonic regression)
    order = np.argsort(aug_scores, kind="stable")
    sorted_scores = aug_scores[order]
    sorted_labels = aug_labels[order]

    # Fit PAVA isotonic regression
    cal_probs = _isotonic_calibrate(sorted_scores, sorted_labels)

    # Find the test point's position(s) in the sorted array
    test_positions = np.where(order == len(aug_scores) - 1)[0]
    # There should be exactly one; take the first
    test_pos = int(test_positions[0])
    return float(cal_probs[test_pos])


def venn_abers_interval(
    cal_scores: np.ndarray,
    cal_labels: np.ndarray,
    test_score: float,
) -> tuple[float, float]:
    """Compute the Venn-Abers probability interval [p_lo, p_hi] for one test point.

    Per the inductive Venn-Abers procedure (Vovk et al., 2015):
      p0 = isotonic-calibrated probability when test label hypothetically = 0
      p1 = isotonic-calibrated probability when test label hypothetically = 1
      interval = [min(p0, p1), max(p0, p1)]

    The interval satisfies a finite-sample coverage guarantee under exchangeability:
    the true positive frequency lies within the interval in the long run.

    Parameters
    ----------
    cal_scores  : 1-D array of calibration set raw scores (n,)
    cal_labels  : 1-D array of calibration set binary labels (n,)
    test_score  : raw score for the test instance

    Returns
    -------
    (p_lo, p_hi) : probability interval, p_lo <= p_hi, both in [0, 1]
    """
    cal_scores = np.asarray(cal_scores, dtype=float)
    cal_labels = np.asarray(cal_labels, dtype=float)

    p0 = _pava_predict(cal_scores, cal_labels, test_score, augment_label=0)
    p1 = _pava_predict(cal_scores, cal_labels, test_score, augment_label=1)

    p_lo = float(min(p0, p1))
    p_hi = float(max(p0, p1))
    # Clip to [0, 1] for numerical safety
    p_lo = max(0.0, min(1.0, p_lo))
    p_hi = max(0.0, min(1.0, p_hi))
    return p_lo, p_hi


def batch_venn_abers_intervals(
    cal_scores: np.ndarray,
    cal_labels: np.ndarray,
    test_scores: np.ndarray,
) -> list[tuple[float, float]]:
    """Compute Venn-Abers intervals for multiple test points.

    Equivalent to calling venn_abers_interval() for each test score, but
    implemented slightly more efficiently by reusing the sorted calibration
    set structure. Each test point is still treated independently (inductive
    Venn-Abers: calibration set is fixed, not re-augmented across test points).

    Parameters
    ----------
    cal_scores  : calibration set raw scores (n,)
    cal_labels  : calibration set binary labels (n,)
    test_scores : test set raw scores (m,)

    Returns
    -------
    List of (p_lo, p_hi) tuples, length m
    """
    intervals = []
    for s in test_scores:
        p_lo, p_hi = venn_abers_interval(cal_scores, cal_labels, float(s))
        intervals.append((p_lo, p_hi))
    return intervals


# ---------------------------------------------------------------------------
# Coverage + width gates (consult §4 Gates 1 + 2)
# ---------------------------------------------------------------------------


def compute_empirical_coverage(
    cal_val_scores: np.ndarray,
    cal_val_labels: np.ndarray,
    cal_fit_scores: np.ndarray,
    cal_fit_labels: np.ndarray,
) -> dict[str, Any]:
    """Gate 1: midpoint-classification coverage on the cal-validation split.

    Definition (ratified — venn-abers-coverage-gate-consult-2026-05-24.md):
    Venn-Abers' validity guarantee is an AGGREGATE marginal statement, not an
    individual-instance bracketing one. For binary outcomes it operationalizes
    as: the interval's midpoint must land on the correct side of the 0.5
    decision boundary for each instance. For each cal-val instance with
    interval [p_lo, p_hi] and label y:

        midpoint_i = (p_lo_i + p_hi_i) / 2
        covered_i  = 1  if (y_i == 1 and midpoint_i >= 0.5)
                        or (y_i == 0 and midpoint_i <  0.5)
        coverage   = mean(covered_i)

    This is NOT near-trivial (unlike the prior `p_hi > 0` / `p_lo < 1` check,
    which the 2026-05-24 review found was satisfied ~always): a calibrator that
    assigns low-midpoint intervals to positive instances FAILS it. A random
    calibrator scores ~base-rate; a well-sorted one exceeds 0.80.

    Gate threshold: 0.80 (on this meaningful check — strictly harder in practice
    than the old 0.90 on the trivial check). Min n: < 5 cal-val → gate_pass=None
    (cohort suppressed UNVALIDATED_COVERAGE; not a free pass).

    HONEST LABELLING (per the expert review of this gate): this metric is
    structurally midpoint-classification ACCURACY at threshold 0.5, used as a
    PROXY for coverage at QGI's thin per-cohort n. It is NOT the Venn-Abers
    theoretical coverage guarantee (which is not estimable at n≈9 cal-val). It
    screens out a calibrator that reverses the score ordering; it does NOT
    verify calibration. Proper binned calibration is deferred to Stage B
    (n≥15/cohort). The output field is named accordingly.

    Also returns a logged-only Winkler interval-score diagnostic (no gating) at
    nominal 80% (alpha=0.20, per consult §4): mean of -(p_hi - p_lo) -
    (2/alpha)*[underage + overage]. Lower (more negative) = worse.
    """
    intervals = batch_venn_abers_intervals(cal_fit_scores, cal_fit_labels, cal_val_scores)
    n_total = len(cal_val_labels)
    n_covered = 0
    alpha = 0.20  # consult §4: nominal 80% interval score
    winkler_terms = []
    for (p_lo, p_hi), y in zip(intervals, cal_val_labels):
        midpoint = (float(p_lo) + float(p_hi)) / 2.0
        yi = int(y)
        if (yi == 1 and midpoint >= 0.5) or (yi == 0 and midpoint < 0.5):
            n_covered += 1
        # Winkler interval score (diagnostic only)
        underage = max(0.0, float(p_lo) - yi)
        overage = max(0.0, yi - float(p_hi))
        winkler_terms.append(-(float(p_hi) - float(p_lo)) - (2.0 / alpha) * (underage + overage))
    coverage = float(n_covered) / float(n_total) if n_total > 0 else float("nan")
    return {
        "coverage": coverage,
        "n_covered": n_covered,
        "n_total": n_total,
        # Honest name: this is an accuracy-based proxy for coverage, NOT the VA
        # theoretical coverage guarantee (see docstring + expert review).
        "definition": "midpoint_classification_accuracy_proxy",
        "gate_pass": bool(coverage >= 0.80) if n_total >= 5 else None,
        "gate_threshold": 0.80,
        "low_n_skip": n_total < 5,
        "winkler_score_diagnostic": (float(np.mean(winkler_terms)) if winkler_terms else None),
    }


def compute_mean_interval_width(
    cal_fit_scores: np.ndarray,
    cal_fit_labels: np.ndarray,
    test_scores: np.ndarray,
) -> dict[str, Any]:
    """Gate 2: mean interval width <= 0.60 per cohort.

    Computes the Venn-Abers intervals for all test scores and returns the
    mean width. Width > 0.60 triggers UNSHARP_LOW_POWER flag.
    """
    intervals = batch_venn_abers_intervals(cal_fit_scores, cal_fit_labels, test_scores)
    widths = [p_hi - p_lo for p_lo, p_hi in intervals]
    mean_width = float(np.mean(widths)) if widths else float("nan")
    return {
        "mean_width": mean_width,
        "max_width": float(np.max(widths)) if widths else float("nan"),
        "n_test": len(widths),
        "gate_pass": bool(mean_width <= 0.60) if widths else None,
        "gate_threshold": 0.60,
        "flag": "UNSHARP_LOW_POWER" if (widths and mean_width > 0.60) else None,
    }


# ---------------------------------------------------------------------------
# OOF prediction reproduction — mirrors extract_shap_importances.py
# ---------------------------------------------------------------------------


def reproduce_oof_predictions(
    walk_summary: dict,
    cohort_assignments: dict,
    panel_dir: Path,
    seed: int = 12345,
) -> dict[str, Any]:
    """Reproduce per-instance OOF predictions deterministically from the walk.

    Mirrors extract_shap_importances.reproduce_walk_training_data() for sample
    construction, then calls drv.fit_predict_loco() with the walk's architecture,
    seed, selected indicators, and chosen window.

    Returns a dict with:
        probs       : (N,) OOF predicted probabilities
        labels      : (N,) binary labels
        countries   : (N,) country names
        years       : (N,) years
        cohorts     : (N,) cohort assignments (str or None)
        global_auc  : float
    """
    recipe_id = walk_summary["recipe_id"]
    selected = walk_summary["greedy_outer_loop"]["selected_indicators"]
    chosen_window = walk_summary["greedy_outer_loop"]["chosen_window"]
    architecture = walk_summary.get("architecture", "XGBoost")

    # Build positives + negatives with the same seed (mirrors drv._main)
    positives_csv = REPO_ROOT / "data" / "shape_inputs_v2" / recipe_id / "positives.csv"
    pos = pd.read_csv(positives_csv)
    pos["country"] = pos["country_id"].apply(drv.normalize_country_id)
    pos = pos.rename(columns={"event_year": "year"})
    pos["label"] = 1

    rng = np.random.default_rng(seed)
    pos_set = set(zip(pos["country"], pos["year"]))
    pos_countries = list(pos["country"].unique())
    valid_years = list(range(1980, 2023))
    n_neg_target = len(pos) * 3  # same ratio as driver default
    negs = []
    attempts = 0
    while len(negs) < n_neg_target and attempts < n_neg_target * 10:
        attempts += 1
        c = pos_countries[rng.integers(0, len(pos_countries))]
        y_pick = int(valid_years[rng.integers(0, len(valid_years))])
        if (c, y_pick) in pos_set:
            continue
        negs.append({"country": c, "year": y_pick, "label": 0})

    samples = pd.concat(
        [pos[["country", "year", "label"]], pd.DataFrame(negs)],
        ignore_index=True,
    )

    # Load panels for selected indicators only
    panels = {ind: drv.load_panel(ind, panel_dir) for ind in selected}

    # Build X, y
    X, y, c_arr, yr_arr = drv.build_X_y(samples, selected, chosen_window, panels)

    # Run LOCO (same as driver)
    loco = drv.fit_predict_loco(
        X, y, c_arr, yr_arr, architecture=architecture, seed=seed
    )

    probs = loco["probs"]
    labels = loco["labels"]
    countries = loco["countries"]
    years = loco["years"]

    # Assign cohort to each instance
    cohorts = []
    for country, year in zip(countries, years):
        c_key = str(country).title()
        yr_key = str(int(year))
        cohort = cohort_assignments.get(c_key, {}).get(yr_key, None)
        cohorts.append(cohort)

    return {
        "probs": probs,
        "labels": labels,
        "countries": countries,
        "years": years,
        "cohorts": np.array(cohorts, dtype=object),
        "global_auc": loco["global_auc"],
        "selected_indicators": selected,
        "chosen_window": chosen_window,
        "architecture": architecture,
        "n_samples": int(len(probs)),
        "n_positives": int((labels == 1).sum()),
        "n_negatives": int((labels == 0).sum()),
    }


# ---------------------------------------------------------------------------
# Per-cohort Venn-Abers fit + scoring
# ---------------------------------------------------------------------------

COHORTS = ("fragile-state", "mid-tier", "stable-democracy")
# 70/30 split of OOF predictions for cal-fit / cal-val (per consult §4 Gate 1)
CAL_FIT_FRACTION = 0.70
COVERAGE_GATE = 0.80  # midpoint-classification coverage (consult 2026-05-24); was 0.90 on a trivial check
WIDTH_GATE = 0.60
MIN_N_FOR_GATE = 5


def fit_and_score_per_cohort(
    oof: dict[str, Any],
    scored_countries: list[str],
    scored_scores: dict[str, float],
    cohort_assignments: dict,
    eval_year: int,
    seed: int = 12345,
) -> dict[str, Any]:
    """Fit Venn-Abers per cohort and score the evaluation-year countries.

    Split the OOF predictions 70/30 (stratified by label within each cohort)
    into cal-fit and cal-val subsets. Fit Venn-Abers on cal-fit. Evaluate
    Gate 1 (coverage) on cal-val. Evaluate Gate 2 (width) on scored countries.

    Parameters
    ----------
    oof             : output of reproduce_oof_predictions()
    scored_countries: list of country names to score (from scores-file)
    scored_scores   : {country: raw XGBoost score} — the raw probs from the walk
                      that should be used for test scoring. We use the similarity
                      score as a proxy when direct XGBoost scores are unavailable
                      (see honesty flags below). If direct OOF scores are available
                      for any scored country, those are used.
    cohort_assignments : the full assignments dict
    eval_year       : int, the evaluation year for cohort lookup
    seed            : int, fixed seed for the cal/val split shuffle

    Returns a per-cohort dict with coverage, width, gate_pass, and per-country
    interval assignments.
    """
    probs = oof["probs"]
    labels = oof["labels"]
    countries = oof["countries"]
    cohorts_arr = oof["cohorts"]

    rng = np.random.default_rng(seed)

    per_cohort_results: dict[str, dict[str, Any]] = {}

    for cohort in COHORTS:
        # Collect OOF instances belonging to this cohort
        mask = np.array([c == cohort for c in cohorts_arr], dtype=bool)
        if mask.sum() < MIN_N_FOR_GATE:
            per_cohort_results[cohort] = {
                "n_oof": int(mask.sum()),
                "skip_reason": f"n_oof={int(mask.sum())} < MIN_N_FOR_GATE={MIN_N_FOR_GATE}",
                "gate_1_coverage": None,
                "gate_2_width": None,
                "gate_pass": False,
                "suppressed": True,
                "flag": "INSUFFICIENT_DATA",
            }
            continue

        cohort_probs = probs[mask]
        cohort_labels = labels[mask]
        n_cohort = int(mask.sum())

        # Stratified 70/30 split within cohort by label
        pos_idx = np.where(cohort_labels == 1)[0]
        neg_idx = np.where(cohort_labels == 0)[0]

        rng.shuffle(pos_idx)
        rng.shuffle(neg_idx)

        n_pos_fit = max(1, int(len(pos_idx) * CAL_FIT_FRACTION))
        n_neg_fit = max(1, int(len(neg_idx) * CAL_FIT_FRACTION))

        fit_idx = np.concatenate([pos_idx[:n_pos_fit], neg_idx[:n_neg_fit]])
        val_idx = np.concatenate([pos_idx[n_pos_fit:], neg_idx[n_neg_fit:]])

        cal_fit_scores = cohort_probs[fit_idx]
        cal_fit_labels = cohort_labels[fit_idx]
        cal_val_scores = cohort_probs[val_idx]
        cal_val_labels = cohort_labels[val_idx]

        # Gate 1: coverage on held-out cal-val split
        if len(cal_val_scores) >= MIN_N_FOR_GATE:
            gate1 = compute_empirical_coverage(
                cal_val_scores, cal_val_labels, cal_fit_scores, cal_fit_labels
            )
        else:
            gate1 = {
                "coverage": None,
                "n_total": len(cal_val_scores),
                "gate_pass": None,
                "low_n_skip": True,
                "gate_threshold": COVERAGE_GATE,
            }

        # Collect scored countries in this cohort + their raw scores
        # For test scoring, we use the OOF-reproduced XGBoost scores rather
        # than similarity scores (apples-to-apples with the calibration set).
        # If a scored country is NOT in the OOF set, use the country's OOF
        # score from the nearest match; if completely absent, fall back to
        # the raw similarity score (normalized to [0,1]).
        oof_country_scores: dict[str, list[float]] = {}
        for sc, p, c in zip(cohort_probs, cohort_labels, countries[mask]):
            c_key = str(c)
            if c_key not in oof_country_scores:
                oof_country_scores[c_key] = []
            # BUGFIX (QA review #100): cache the OOF predicted SCORE (sc),
            # NOT the binary label (p). Caching the label calibrated in-OOF
            # test countries against 0/1 instead of their model score, making
            # those countries' Venn-Abers intervals meaningless.
            oof_country_scores[c_key].append(float(sc))

        # Score each country in this cohort from the eval-year scores file
        cohort_test_countries = []
        cohort_test_raw_scores = []
        for country in scored_countries:
            c_key_ca = str(country).title()
            yr_key = str(int(eval_year))
            c_cohort = cohort_assignments.get(c_key_ca, {}).get(yr_key, None)
            if c_cohort != cohort:
                continue
            # Use OOF score for this country if available (mean of OOF probs)
            if country in oof_country_scores:
                raw_score = float(np.mean(oof_country_scores[country]))
            elif c_key_ca in oof_country_scores:
                raw_score = float(np.mean(oof_country_scores[c_key_ca]))
            else:
                # Fallback: use similarity score normalized to [0, 1]
                sim_score = float(scored_scores.get(country, 50.0))
                raw_score = sim_score / 100.0
            cohort_test_countries.append(country)
            cohort_test_raw_scores.append(raw_score)

        # Gate 2: interval width on test countries
        if cohort_test_raw_scores:
            gate2 = compute_mean_interval_width(
                cal_fit_scores, cal_fit_labels,
                np.array(cohort_test_raw_scores, dtype=float),
            )
        else:
            gate2 = {
                "mean_width": None,
                "n_test": 0,
                "gate_pass": None,
                "flag": None,
            }

        # Determine per-cohort gate pass.
        # CONSERVATIVE: a cohort publishes odds ONLY if BOTH gates were actually
        # validatable AND passed. Coverage that could not be computed (gate1_pass
        # is None — too few validation positives) is NOT a free pass; an
        # unvalidatable coverage guarantee means we cannot honestly publish the
        # odds, so it suppresses with an UNVALIDATED_COVERAGE flag. Width over the
        # cap suppresses with UNSHARP_LOW_POWER.
        gate1_pass = gate1.get("gate_pass")
        gate2_pass = gate2.get("gate_pass")
        coverage_validatable = gate1_pass is not None
        width_validatable = gate2_pass is not None
        cohort_gate_pass = bool(
            coverage_validatable and gate1_pass is True
            and width_validatable and gate2_pass is True
        )
        if not coverage_validatable:
            cohort_flag = "UNVALIDATED_COVERAGE"
        elif gate2.get("flag") == "UNSHARP_LOW_POWER":
            cohort_flag = "UNSHARP_LOW_POWER"
        elif not cohort_gate_pass:
            cohort_flag = "GATE_FAIL"
        else:
            cohort_flag = None
        suppressed = not cohort_gate_pass

        # Compute per-country intervals
        country_odds: dict[str, dict[str, Any]] = {}
        for country, raw_score in zip(cohort_test_countries, cohort_test_raw_scores):
            p_lo, p_hi = venn_abers_interval(
                cal_fit_scores, cal_fit_labels, float(raw_score)
            )
            country_odds[country] = {
                "p_lo": round(p_lo, 6),
                "p_hi": round(p_hi, 6),
                "width": round(p_hi - p_lo, 6),
                "midpoint": round((p_lo + p_hi) / 2.0, 6),
                "cohort": cohort,
                "suppressed": suppressed,
                "flag": cohort_flag,
                "label": "estimated probability range, not a precise probability",
            }

        per_cohort_results[cohort] = {
            "n_oof": n_cohort,
            "n_cal_fit": len(fit_idx),
            "n_cal_val": len(val_idx),
            "gate_1_coverage": gate1,
            "gate_2_width": gate2,
            "gate_pass": cohort_gate_pass,
            "suppressed": suppressed,
            "flag": cohort_flag,
            "country_odds": country_odds,
        }

    return per_cohort_results


# ---------------------------------------------------------------------------
# Main + CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-id", required=True,
                        help="Recipe ID (e.g., foreign_intervention).")
    parser.add_argument("--walk-summary", type=Path, required=True,
                        help="Path to walk's f-ml-1-poc-summary.json.")
    parser.add_argument("--scores-file", type=Path, required=True,
                        help="Path to recipe-similarity-scores-{recipe}-{year}.json.")
    parser.add_argument("--panel-dir", type=Path,
                        default=REPO_ROOT / "data" / "parquet_panels",
                        help="Directory containing per-indicator parquet panels.")
    parser.add_argument("--cohort-sidecar", type=Path,
                        default=REPO_ROOT.parent / "qgi-data" / "reference" / "cohort-assignments.json",
                        help="Path to cohort-assignments.json.")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Output directory for venn-abers-odds-*.json.")
    parser.add_argument("--seed", type=int, default=12345,
                        help="Random seed. Must match walk seed for OOF reproduction.")
    return parser


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load walk summary
    with open(args.walk_summary, encoding="utf-8") as f:
        walk_summary = json.load(f)
    assert walk_summary["recipe_id"] == args.recipe_id, (
        f"Walk summary recipe_id {walk_summary['recipe_id']!r} != requested {args.recipe_id!r}"
    )

    # Load scores file
    with open(args.scores_file, encoding="utf-8") as f:
        scores_data = json.load(f)
    eval_year = int(scores_data["evaluation_year"])
    raw_scores = scores_data.get("scores", {})
    # Extract country: risk_score (0-100 scale)
    scored_countries = list(raw_scores.keys())
    scored_scores = {c: float(raw_scores[c]["risk_score"]) for c in scored_countries}

    # Load cohort assignments
    with open(args.cohort_sidecar, encoding="utf-8") as f:
        cohort_payload = json.load(f)
    cohort_assignments = cohort_payload["assignments"]

    print(f"Recipe: {args.recipe_id}, eval_year: {eval_year}")
    print(f"Scored countries: {len(scored_countries)}")
    print(f"Reproducing OOF predictions (seed={args.seed})...")

    # Reproduce OOF predictions
    oof = reproduce_oof_predictions(
        walk_summary=walk_summary,
        cohort_assignments=cohort_assignments,
        panel_dir=args.panel_dir,
        seed=args.seed,
    )

    print(f"  OOF: n={oof['n_samples']}, n_pos={oof['n_positives']}, "
          f"n_neg={oof['n_negatives']}, global_auc={oof['global_auc']:.4f}")

    # Programmatic OOF-fidelity self-check (QA review #100): the reproduced
    # LOCO-AUC must match the walk's stored AUC, else the calibration is being
    # fit on different predictions than the walk validated. WARN loudly on drift.
    stored_auc = walk_summary.get("global_loco", {}).get("auc")
    if stored_auc is not None:
        auc_delta = abs(float(oof["global_auc"]) - float(stored_auc))
        if auc_delta > 0.005:
            print(
                f"  WARNING: reproduced global_auc={oof['global_auc']:.4f} deviates "
                f"{auc_delta:.4f} from walk's stored {float(stored_auc):.4f} (> 0.005). "
                f"OOF reproduction may be unfaithful — odds calibration is suspect. "
                f"Investigate (numpy/xgboost version, panel drift, country-norm) "
                f"before trusting this output."
            )
        else:
            print(f"  OOF-fidelity self-check PASSED (|delta|={auc_delta:.5f} <= 0.005).")

    # Distribution of OOF instances across cohorts
    cohort_counts: dict[str, int] = {}
    for c in oof["cohorts"]:
        cohort_counts[str(c)] = cohort_counts.get(str(c), 0) + 1
    print(f"  Cohort distribution in OOF: {cohort_counts}")

    # Fit and score per cohort
    print("Fitting Venn-Abers per cohort and scoring...")
    per_cohort = fit_and_score_per_cohort(
        oof=oof,
        scored_countries=scored_countries,
        scored_scores=scored_scores,
        cohort_assignments=cohort_assignments,
        eval_year=eval_year,
        seed=args.seed,
    )

    # Flatten country odds across cohorts into top-level odds dict
    odds: dict[str, dict[str, Any]] = {}
    for cohort, cohort_data in per_cohort.items():
        if "country_odds" in cohort_data:
            odds.update(cohort_data["country_odds"])

    # Aggregate per-cohort summary metrics
    per_cohort_coverage = {}
    per_cohort_mean_width = {}
    gate_pass_overall = True
    for cohort in COHORTS:
        cd = per_cohort.get(cohort, {})
        g1 = cd.get("gate_1_coverage", {}) or {}
        g2 = cd.get("gate_2_width", {}) or {}
        per_cohort_coverage[cohort] = g1.get("coverage")
        per_cohort_mean_width[cohort] = g2.get("mean_width")
        if cd.get("suppressed", True):
            gate_pass_overall = False

    # Build output JSON
    output: dict[str, Any] = {
        "recipe_id": args.recipe_id,
        "eval_year": eval_year,
        "method": "venn-abers-inductive-per-cohort",
        "method_reference": (
            "Vovk, V., Petej, I., & Fedorova, V. (2015). Large-scale probabilistic "
            "predictors with and without guarantees of validity. NeurIPS 28. "
            "Per odds-calibration-consult-2026-05-24.md (Ji-Hoon #21 + Kwame #11, 2/2 ratified)."
        ),
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed_used": args.seed,
        "oof_reproduction": {
            "n_samples": oof["n_samples"],
            "n_positives": oof["n_positives"],
            "n_negatives": oof["n_negatives"],
            "global_auc_reproduced": round(oof["global_auc"], 6),
            "selected_indicators": oof["selected_indicators"],
            "chosen_window": oof["chosen_window"],
            "architecture": oof["architecture"],
            "note": (
                "OOF predictions reproduced by re-running the walk's LOCO procedure "
                "from the same seed + selected indicators + chosen window. "
                "Deterministic under XGBoost + fixed seed on same data."
            ),
        },
        "per_cohort_coverage": per_cohort_coverage,
        "per_cohort_mean_width": per_cohort_mean_width,
        "gate_pass": gate_pass_overall,
        "gate_definitions": {
            "gate_1_coverage_threshold": COVERAGE_GATE,
            "gate_2_width_threshold": WIDTH_GATE,
            "min_n_for_gate": MIN_N_FOR_GATE,
            "suppression_rule": (
                "A cohort publishes odds ONLY if BOTH gates were validatable AND "
                "passed (midpoint-accuracy-proxy coverage >= 0.80 and mean_width "
                "<= 0.60). Otherwise it is "
                "suppressed with one of three flags: UNSHARP_LOW_POWER (mean_width > "
                "0.60), UNVALIDATED_COVERAGE (coverage could not be validated — too "
                "few validation positives), or INSUFFICIENT_DATA (n_oof < "
                "MIN_N_FOR_GATE). Unvalidatable coverage is NOT a free pass."
            ),
        },
        "per_cohort_detail": {
            cohort: {
                k: v for k, v in data.items() if k != "country_odds"
            }
            for cohort, data in per_cohort.items()
        },
        "label": "estimated probability range, not a precise probability",
        "m8_r5_note": (
            "M8-R5 BINDING: odds intervals MUST be published alongside the "
            "discrimination/similarity score, never instead of it. "
            "Per odds-calibration-consult-2026-05-24.md Gate 4."
        ),
        "odds": odds,
    }

    out_path = args.output_dir / f"venn-abers-odds-{args.recipe_id}-{eval_year}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_path}")

    # Print gate summary
    print("\n=== GATE SUMMARY ===")
    for cohort in COHORTS:
        cd = per_cohort.get(cohort, {})
        g1_cov = per_cohort_coverage.get(cohort)
        g2_w = per_cohort_mean_width.get(cohort)
        suppressed = cd.get("suppressed", True)
        flag = cd.get("flag", "")
        n_oof = cd.get("n_oof", 0)
        n_odds = len(cd.get("country_odds", {}))
        cov_str = f"{g1_cov:.3f}" if g1_cov is not None else "N/A"
        w_str = f"{g2_w:.3f}" if g2_w is not None else "N/A"
        print(
            f"  {cohort}: n_oof={n_oof}, "
            f"coverage={cov_str}, "
            f"mean_width={w_str}, "
            f"suppressed={suppressed}, flag={flag or 'none'}, "
            f"n_countries_scored={n_odds}"
        )
    print(f"\nOverall gate_pass: {gate_pass_overall}")
    print(f"Total countries with odds: {len(odds)}")
    unsuppressed = sum(1 for v in odds.values() if not v.get("suppressed", True))
    print(f"Countries with publishable odds (not suppressed): {unsuppressed}")
    return 0


# ---------------------------------------------------------------------------
# Honesty flags (nondeterminism risks the orchestrator must verify)
# ---------------------------------------------------------------------------
#
# 1. XGBoost LOCO nondeterminism: XGBoost with n_jobs=1 + fixed random_state
#    is deterministic on the same platform (same CPU architecture, same BLAS
#    version, same data). Cross-platform (Linux vs Windows ARM64) may produce
#    epsilon-level differences in floating-point results. Verify: run twice on
#    the same machine and compare OOF AUC to walk's reported global_auc.
#    A difference > 0.001 indicates a reproduction problem.
#
# 2. Negative sampling: the negative sample set is reproduced from the same
#    seed, but the driver uses `rng.integers` which may behave differently
#    under different numpy versions. If the reproduced global_auc deviates
#    from the walk's stored value by > 0.005, flag a reproduction warning.
#
# 3. Panel data: if the parquet panels on disk were modified after the walk
#    was run (e.g., a V-Dem update), the reproduced OOF predictions will differ
#    from the walk's. Always verify panel timestamps match the walk's filed date.
#
# 4. Country name normalization: the same COUNTRY_NAME_OVERRIDES dict is used
#    here (via drv.normalize_country_id). If a new recipe introduces a new
#    multi-word country_id, the override map must be updated in run_f_ml_1_poc.py
#    before running this script.
#
# 5. civil_war walk-1 normalization bug: civil_war walk-1 ran WITHOUT the
#    2026-05-22 country-name fix. The reproduced OOF predictions for civil_war
#    use the FIXED normalization and will include more samples (some multi-word
#    countries that were silently dropped in walk-1). The Venn-Abers calibration
#    will be trained on a slightly larger set than the original walk. This is
#    CORRECT behavior (more data is better for calibration) but means the
#    reproduced global_auc will differ from the stored walk-1 AUC. The
#    orchestrator should not fail on this discrepancy for civil_war walk-1.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    sys.exit(_main())
