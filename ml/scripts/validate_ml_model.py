#!/usr/bin/env python3
"""
ML Validation Framework Scaffolding (Stage 0 v1)
=================================================

Implements the v1 subset of the validation framework specified in
docs/specs/internal/ops/ml-track/07-validation-framework.md:

    Component 1 — OOS-by-time AUC + bootstrap 95% CI (PRIMARY metric)
    Component 3 — Calibration audit per recipe + ECE post-Beta
    Component 4 — Brier score decomposition (reliability/resolution/uncertainty)
    Component 6 — Anchor-case battery (pass/fail per case)

Components 2, 5, 7, 8, 9 are Stage 2 / Stage 3 extensions and are NOT
implemented here — they require richer per-cohort data and the full
modular architecture.

Stage 0 deliverable per docs/specs/internal/ops/ml-track/stage-0-pre-registration.md.
The orchestrator + the pure computation functions are usable independently;
Stage 1 wires real model artifacts + test predictions through them.

Inputs (CLI):
    --metadata    qgi-ml/src/ml_registry.ModelMetadata JSON (from registry)
    --predictions test-set predictions JSON (schema below)
    --anchors     qgi-data/reference/anchor-case-battery.json
    --output      output validation report JSON (defaults to stdout)

Predictions JSON schema (v1):
    {
      "schema_version": 1,
      "model_metadata_uri": "s3://...",
      "predictions": [
        {"country": "...", "year": ...,
         "recipe_id": "...", "predicted_probability": 0.0-1.0, "label": 0|1},
        ...
      ]
    }

Output JSON schema (v1) -- emitted to args.output:
    {
      "schema_version": 1,
      "validation_run_id": "...",
      "generated_at_utc": "...",
      "model_metadata_uri": "...",
      "validation_script_fingerprint": {file_sha256, git_commit_sha, git_dirty, ...},
      "components": {
        "oos_by_time": {"per_recipe": {<recipe>: {auc_point, auc_ci_95, n}}},
        "calibration":  {"per_recipe": {<recipe>: {ece, n_bins, reliability_diagram}}},
        "brier":        {"per_recipe": {<recipe>: {reliability, resolution, uncertainty, brier_score}}},
        "anchor_battery": {"active": [{...}], "deferred": [{...}]}
      }
    }

Per-recipe blocks key on recipe_id present in predictions.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import math
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

_log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANCHORS = REPO_ROOT / "qgi-data" / "reference" / "anchor-case-battery.json"

# Lazy import of ml_registry for fingerprint helper
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


# ---------- AUC + bootstrap CI (Component 1) ----------


def compute_auc_pr(predictions: np.ndarray, labels: np.ndarray) -> float:
    """Average Precision (PR-AUC) — rank discrimination on the rare-event axis.

    Better than ROC-AUC for class-imbalanced settings (QGI's positive
    rates are ~0.3-1.8% per recipe). Computed via the standard
    sum-of-(R_k - R_{k-1}) * P_k formulation, sklearn-equivalent.

    Returns NaN if labels are all one class.
    """
    predictions = np.asarray(predictions, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if predictions.shape != labels.shape:
        msg = f"shape mismatch: {predictions.shape} vs {labels.shape}"
        raise ValueError(msg)
    n_pos = int((labels == 1).sum())
    if predictions.size == 0 or n_pos == 0:
        return float("nan")
    # Sort descending by predictions, stable.
    order = np.argsort(-predictions, kind="mergesort")
    sorted_labels = labels[order]
    tp = np.cumsum(sorted_labels)
    fp = np.cumsum(1 - sorted_labels)
    denom = tp + fp
    # Avoid 0/0 at the very first row if it's a true positive: precision = 1.
    precision = np.where(denom > 0, tp / np.maximum(denom, 1), 0.0)
    recall = tp / n_pos
    # AP = sum_k (R_k - R_{k-1}) * P_k, with R_0 = 0
    recall_diff = np.diff(recall, prepend=0.0)
    ap = float((precision * recall_diff).sum())
    return ap


def compute_log_loss(
    predictions: np.ndarray,
    labels: np.ndarray,
    *,
    eps: float = 1e-15,
) -> float:
    """Cross-entropy loss. Penalizes confident wrong predictions.

    AUC ignores how confident wrong predictions are; log-loss exposes
    overconfident misses (the failure mode that matters most for
    buyer trust — confidently wrong is worse than humble wrong).

    Predictions are clipped to [eps, 1-eps] for numerical stability.
    Returns NaN if input is empty.
    """
    predictions = np.asarray(predictions, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if predictions.shape != labels.shape:
        msg = f"shape mismatch: {predictions.shape} vs {labels.shape}"
        raise ValueError(msg)
    if predictions.size == 0:
        return float("nan")
    p = np.clip(predictions, eps, 1.0 - eps)
    ll = -float(np.mean(labels * np.log(p) + (1 - labels) * np.log(1.0 - p)))
    return ll


def compute_brier_skill_score(
    predictions: np.ndarray,
    labels: np.ndarray,
) -> float:
    """Brier Skill Score — Brier improvement vs base-rate baseline.

    BSS = 1 - (Brier_model / Brier_baseline)
        where Brier_baseline = base_rate * (1 - base_rate)
              (= Brier of always predicting base_rate)

    BSS = 1 → perfect; BSS = 0 → no better than predicting the base
    rate; BSS < 0 → worse than the base-rate baseline. Makes raw
    Brier numerically interpretable.

    Returns NaN if base_rate is 0 or 1 (denominator undefined) or
    input is empty.
    """
    predictions = np.asarray(predictions, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if predictions.shape != labels.shape:
        msg = f"shape mismatch: {predictions.shape} vs {labels.shape}"
        raise ValueError(msg)
    if predictions.size == 0:
        return float("nan")
    base_rate = float(labels.mean())
    brier_baseline = base_rate * (1.0 - base_rate)
    if brier_baseline <= 0.0:
        return float("nan")
    brier_model = float(((predictions - labels) ** 2).mean())
    return 1.0 - (brier_model / brier_baseline)


def compute_anchor_drift_metrics(
    anchor_results: dict,
) -> dict:
    """Compute Anchor Drift Score (ADS) + Anchor Hit Rate (AHR) + Anchor
    Health Index (AHI) from an anchor-battery evaluation payload.

    Per founder spec (2026-05-05):
    - For each anchor case (PASS or FAIL only — DEFERRED / NYI / SKIPPED
      excluded): compute |drift| = signed distance from observed_rank
      to expected_rank_band, in [0, 1].
    - **ADS** (Anchor Drift Score) = mean(|drift|) across all evaluable
      anchors. Lower is better. Range [0, 1] (in pp = ADS × 100).
    - **AHR** (Anchor Hit Rate) = count(|drift| = 0) / N_evaluable.
      Higher is better. Range [0, 1].
    - **AHI** (Anchor Health Index) = AHR × (1 - ADS). Composite.
      Range [0, 1]. Higher = better. Both factors must be high for AHI
      to be high (multiplicative penalty).

    REPORTED only (not gated). Surfaces per founder ratification
    2026-05-05.

    Parameters
    ----------
    anchor_results : dict
        The output of `evaluate_anchor_battery(...)` — must contain an
        `active` key with per-case payloads. Each payload has `verdict`,
        `observed_percentile`, `expected_rank_band`.

    Returns
    -------
    dict with: ads, ahr, ahi, n_evaluable, n_excluded_non_evaluable,
        per_case_drifts (list of (id, signed_drift) for transparency).
    """
    if not isinstance(anchor_results, dict):
        return {
            "ads": float("nan"), "ahr": float("nan"), "ahi": float("nan"),
            "n_evaluable": 0, "n_excluded_non_evaluable": 0,
            "per_case_drifts": [],
        }
    active = anchor_results.get("active") or []
    drifts: list[tuple[Any, float]] = []
    n_excluded = 0
    for case in active:
        # `evaluate_anchor_case` emits `status`, but downstream readers
        # may have written `verdict` historically. Accept either.
        status = case.get("status") or case.get("verdict")
        if status not in ("PASS", "FAIL"):
            n_excluded += 1
            continue
        observed = case.get("observed_percentile")
        band = case.get("expected_rank_band")
        if observed is None or band is None or len(band) != 2:
            n_excluded += 1
            continue
        low, high = float(band[0]), float(band[1])
        obs = float(observed)
        # signed drift: 0 in band; negative if below; positive if above
        if low <= obs <= high:
            signed = 0.0
        elif obs < low:
            signed = obs - low  # negative
        else:
            signed = obs - high  # positive
        drifts.append((case.get("id"), signed))

    n_eval = len(drifts)
    if n_eval == 0:
        return {
            "ads": float("nan"), "ahr": float("nan"), "ahi": float("nan"),
            "n_evaluable": 0, "n_excluded_non_evaluable": n_excluded,
            "per_case_drifts": [],
        }
    abs_drifts = [abs(d) for _, d in drifts]
    ads = float(sum(abs_drifts) / n_eval)
    n_in_band = sum(1 for d in abs_drifts if d == 0.0)
    ahr = float(n_in_band / n_eval)
    ahi = float(ahr * (1.0 - ads))
    return {
        "ads": ads,
        "ahr": ahr,
        "ahi": ahi,
        "ads_pct_pp": float(ads * 100.0),
        "ahr_pct": float(ahr * 100.0),
        "ahi_pct": float(ahi * 100.0),
        "n_evaluable": n_eval,
        "n_excluded_non_evaluable": n_excluded,
        "per_case_drifts": [
            {"id": cid, "signed_drift": float(d)} for cid, d in drifts
        ],
        "policy": (
            "REPORTED only, not gated. ADS = mean |drift| across "
            "evaluable anchors (PASS/FAIL only); AHR = fraction in-band; "
            "AHI = AHR * (1 - ADS) composite. Founder ratification "
            "2026-05-05."
        ),
    }


def compute_auc(predictions: np.ndarray, labels: np.ndarray) -> float:
    """ROC-AUC computed via the rank statistic.

    Returns NaN if labels contain only one class (AUC undefined).
    Self-contained -- avoids the sklearn dep in this hot path.
    """
    predictions = np.asarray(predictions, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if predictions.shape != labels.shape:
        raise ValueError(f"shape mismatch: predictions {predictions.shape} vs labels {labels.shape}")
    n_pos = int((labels == 1).sum())
    n_neg = int((labels == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    # Rank-statistic AUC: average rank of positives among all observations.
    # Equivalent to Mann-Whitney U / (n_pos * n_neg).
    order = np.argsort(predictions, kind="mergesort")
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(predictions) + 1)
    # Average ranks of tied predictions (standard convention)
    sorted_preds = predictions[order]
    i = 0
    while i < len(sorted_preds):
        j = i
        while j + 1 < len(sorted_preds) and sorted_preds[j + 1] == sorted_preds[i]:
            j += 1
        if j > i:
            mean_rank = ranks[order[i:j + 1]].mean()
            ranks[order[i:j + 1]] = mean_rank
        i = j + 1
    sum_ranks_pos = ranks[labels == 1].sum()
    auc = (sum_ranks_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return float(auc)


def bootstrap_auc_ci(
    predictions: np.ndarray,
    labels: np.ndarray,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 0,
    baseline_auc: float = 0.5,
) -> dict[str, Any]:
    """Bootstrap CI on AUC + delta-vs-baseline (per spec F2 falsification rule).

    Spec 05-recipe-prioritization-rubric.md Rule F2: "Bootstrap 95% CI on
    OOS-by-time AUC delta vs naive base-rate classifier does NOT exclude 0".
    A naive constant predictor has AUC=0.5 by the rank-statistic definition
    (all observations tied -> averaged ranks -> 0.5 regardless of class balance).
    The default baseline_auc=0.5 implements this; callers comparing to a
    backbone or multi-task-v0 baseline pass that baseline's AUC instead.

    Returns:
        auc_point          point estimate of AUC
        auc_ci_low/high    raw CI on AUC (informational)
        delta_point        AUC - baseline_auc
        delta_ci_low/high  CI on (AUC_resample - baseline_auc)  <- F2 check
        baseline_auc       the value subtracted
        ...

    Stage 2 falsification check: `delta_ci_low > 0` (and point >= 0.57 for F2).

    Method: percentile bootstrap. Acceptable as Stage 0 scaffold per QA
    review 2026-05-04; BCa (bias-corrected accelerated) bootstrap is a Stage 1
    upgrade candidate -- ~5x more compute but more defensible for skewed
    sampling distributions in small-N imbalanced recipes. To be confirmed
    with Ji-Hoon in a Stage 1 mini-consult before Stage 2 falsification
    decisions go live.
    """
    predictions = np.asarray(predictions, dtype=float)
    labels = np.asarray(labels, dtype=int)
    n = len(predictions)
    point = compute_auc(predictions, labels)
    if not (0.0 <= confidence < 1.0):
        raise ValueError(f"confidence must be in [0, 1); got {confidence}")
    rng = np.random.default_rng(seed)
    aucs: list[float] = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        a = compute_auc(predictions[idx], labels[idx])
        if not math.isnan(a):
            aucs.append(a)
    if not aucs:
        ci_low = ci_high = float("nan")
        delta_ci_low = delta_ci_high = float("nan")
    else:
        lo_pct = (1 - confidence) / 2 * 100
        hi_pct = (1 + confidence) / 2 * 100
        ci_low = float(np.percentile(aucs, lo_pct))
        ci_high = float(np.percentile(aucs, hi_pct))
        deltas = [a - baseline_auc for a in aucs]
        delta_ci_low = float(np.percentile(deltas, lo_pct))
        delta_ci_high = float(np.percentile(deltas, hi_pct))
    delta_point = float("nan") if math.isnan(point) else point - baseline_auc
    return {
        "auc_point": point,
        "auc_ci_low": ci_low,
        "auc_ci_high": ci_high,
        "baseline_auc": baseline_auc,
        "delta_point": delta_point,
        "delta_ci_low": delta_ci_low,
        "delta_ci_high": delta_ci_high,
        "confidence": confidence,
        "n": n,
        "n_bootstrap": n_bootstrap,
        "n_valid_resamples": len(aucs),
        "method": "percentile",  # Stage 1 may upgrade to "BCa"
    }


# ---------- Calibration / ECE (Component 3) ----------


def compute_ece_and_reliability(
    predictions: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Expected Calibration Error + reliability diagram (decile bucketing).

    ECE = sum_b (n_b / N) * |observed_rate_b - predicted_mean_b|
    """
    predictions = np.asarray(predictions, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if predictions.size == 0:
        return {"ece": float("nan"), "n_bins": n_bins, "reliability_diagram": []}
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[dict[str, Any]] = []
    ece_acc = 0.0
    n = len(predictions)
    for k in range(n_bins):
        lo, hi = edges[k], edges[k + 1]
        # Upper edge inclusive on the last bin so 1.0 lands somewhere
        if k == n_bins - 1:
            mask = (predictions >= lo) & (predictions <= hi)
        else:
            mask = (predictions >= lo) & (predictions < hi)
        n_b = int(mask.sum())
        if n_b == 0:
            bins.append({
                "bin": k, "edge_low": float(lo), "edge_high": float(hi),
                "n": 0, "predicted_mean": None, "observed_rate": None,
            })
            continue
        pred_mean = float(predictions[mask].mean())
        obs_rate = float(labels[mask].mean())
        bins.append({
            "bin": k, "edge_low": float(lo), "edge_high": float(hi),
            "n": n_b, "predicted_mean": pred_mean, "observed_rate": obs_rate,
        })
        ece_acc += (n_b / n) * abs(obs_rate - pred_mean)
    return {"ece": float(ece_acc), "n_bins": n_bins, "reliability_diagram": bins}


def compute_ece_bootstrap_diagnostic(
    predictions: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    n_bootstrap: int = 1000,
    seed: int = 0,
) -> dict[str, Any]:
    """Bootstrap diagnostic for ECE — captures sampling variability of the
    in-sample ECE estimate.

    Per founder tie-break on 2026-05-04 calibration policy consult:
    the F1 falsification gate uses the in-sample ECE (option a) from
    compute_ece_and_reliability, but this bootstrap distribution is reported
    side-by-side as a transparency diagnostic showing how shaky each recipe's
    ECE point estimate is in the small-N regime.

    Method: resample (predictions, labels) with replacement n_bootstrap
    times; compute ECE on each resample; return distribution summary
    including Ji-Hoon's preferred 75th-percentile (a slightly-pessimistic
    single number that absorbs ~1-3 percentile points of in-sample bias).

    Note: this bootstrap captures SAMPLING variability of the ECE estimate
    on the test set's existing calibrated predictions; it does NOT refit
    the Beta calibrator per resample (which would also capture
    calibration-fit variability). Refit-per-resample is a Stage 2 upgrade
    candidate per Ji-Hoon's full POV (filed at docs/specs/internal/majles/
    in-progress/2026-05-04_Ihsa_stage_1_calibration_jihoon.md). For the
    Stage 1 v0 diagnostic this simpler form is sufficient.
    """
    predictions = np.asarray(predictions, dtype=float)
    labels = np.asarray(labels, dtype=int)
    n = len(predictions)
    if n == 0:
        return {
            "n_bootstrap": n_bootstrap, "n_valid_resamples": 0,
            "ece_bootstrap_mean": float("nan"),
            "ece_bootstrap_median": float("nan"),
            "ece_bootstrap_p25": float("nan"),
            "ece_bootstrap_p75": float("nan"),
            "ece_bootstrap_p95": float("nan"),
            "ece_bootstrap_min": float("nan"),
            "ece_bootstrap_max": float("nan"),
            "method": "resample_only",
        }
    rng = np.random.default_rng(seed)
    eces: list[float] = []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        out = compute_ece_and_reliability(predictions[idx], labels[idx], n_bins=n_bins)
        e = float(out["ece"])
        if not np.isnan(e):  # numpy-idiomatic; works for python float and np.float
            eces.append(e)
    if not eces:
        return {
            "n_bootstrap": n_bootstrap, "n_valid_resamples": 0,
            "ece_bootstrap_mean": float("nan"),
            "ece_bootstrap_median": float("nan"),
            "ece_bootstrap_p25": float("nan"),
            "ece_bootstrap_p75": float("nan"),
            "ece_bootstrap_p95": float("nan"),
            "ece_bootstrap_min": float("nan"),
            "ece_bootstrap_max": float("nan"),
            "method": "resample_only",
        }
    arr = np.array(eces, dtype=float)
    # np.quantile is the modern idiom (numpy >= 1.22); units consistent with
    # the summary key names (p25, p75, etc. are quantile fractions, not %).
    return {
        "n_bootstrap": n_bootstrap,
        "n_valid_resamples": len(eces),
        "ece_bootstrap_mean": float(arr.mean()),
        "ece_bootstrap_median": float(np.quantile(arr, 0.50)),
        "ece_bootstrap_p25": float(np.quantile(arr, 0.25)),
        "ece_bootstrap_p75": float(np.quantile(arr, 0.75)),
        "ece_bootstrap_p95": float(np.quantile(arr, 0.95)),
        "ece_bootstrap_min": float(arr.min()),
        "ece_bootstrap_max": float(arr.max()),
        "method": "resample_only",
    }


# ---------- Brier decomposition (Component 4) ----------


def compute_brier_decomposition(
    predictions: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Decompose Brier score into reliability / resolution / uncertainty.

    Standard Murphy-Winkler (1977) decomposition:

        BS = reliability - resolution + uncertainty

    Where:
        uncertainty = p * (1 - p)        p = base rate (irreducible noise)
        reliability = sum_b (n_b/N) * (predicted_mean_b - observed_rate_b)^2
                      penalty for miscalibration
        resolution  = sum_b (n_b/N) * (predicted_mean_b - p)^2
                      reward for spreading predictions away from base rate
    """
    predictions = np.asarray(predictions, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if predictions.size == 0:
        return {
            "brier_score": float("nan"), "uncertainty": float("nan"),
            "resolution": float("nan"), "reliability": float("nan"), "n_bins": n_bins,
        }
    n = len(predictions)
    base_rate = float(labels.mean())
    brier_score = float(((predictions - labels) ** 2).mean())
    uncertainty = base_rate * (1 - base_rate)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    resolution_acc = 0.0
    reliability_acc = 0.0
    for k in range(n_bins):
        lo, hi = edges[k], edges[k + 1]
        if k == n_bins - 1:
            mask = (predictions >= lo) & (predictions <= hi)
        else:
            mask = (predictions >= lo) & (predictions < hi)
        n_b = int(mask.sum())
        if n_b == 0:
            continue
        pred_mean = float(predictions[mask].mean())
        obs_rate = float(labels[mask].mean())
        resolution_acc += (n_b / n) * (pred_mean - base_rate) ** 2
        reliability_acc += (n_b / n) * (pred_mean - obs_rate) ** 2
    return {
        "brier_score": brier_score,
        "uncertainty": uncertainty,
        "resolution": float(resolution_acc),
        "reliability": float(reliability_acc),
        "n_bins": n_bins,
        "base_rate": base_rate,
    }


# ---------- Anchor battery (Component 6) ----------


def evaluate_anchor_case(
    case: dict[str, Any],
    predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate a single anchor case.

    For point cases (single recipe + country + expected_rank_band): compute
    the country's percentile rank within that recipe's prediction distribution
    and check whether it falls in expected_rank_band.

    For rank-stability cases (expected_rank_volatility_max, e.g. Venezuela
    case 6): NOT YET IMPLEMENTED -- requires comparing rank across model
    versions, which is a multi-run interface. Returns a documented
    NOT_YET_IMPLEMENTED status. Stage 1 implements when multi-version
    comparison is available.

    For sentinel cases (recipe_sentinel + resolves_to_layer1): a placeholder
    result indicating the test is composable but requires layer1 lookup
    (Stage 1 will populate this based on the recipe-rubric output).

    Returns:
      {case_id, country, recipe_or_sentinel, status: PASS/FAIL/SKIPPED/
       DEFERRED_TO_STAGE_1/NOT_YET_IMPLEMENTED,
       observed_percentile (if PASS/FAIL), expected_rank_band, reason}
    """
    case_id = case["id"]
    country = case["country"]
    # Predictions JSON uses snake_case country slugs (per qgi-ml/shared/slug.py)
    # in production. The anchor case JSON in qgi-data carries both "country"
    # (display) and "country_slug" (matching). When `country_slug` is provided
    # use it; otherwise fall back to the raw `country` value (test fixtures /
    # legacy callers pass display names directly without slugification).
    match_country = case.get("country_slug") or country
    expected_band = case.get("expected_rank_band")
    # Rank-stability case (Venezuela id=6): not implemented in v1; documented
    # gap for Stage 1.
    if "expected_rank_volatility_max" in case and expected_band is None:
        return {
            "case_id": case_id, "country": country,
            "recipe": case.get("recipe"),
            "status": "NOT_YET_IMPLEMENTED",
            "reason": "rank-stability test requires multi-version comparison; "
                      "Stage 1 implements when prior validation reports are available",
            "expected_rank_volatility_max": case["expected_rank_volatility_max"],
        }
    if "recipe" in case:
        recipe = case["recipe"]
        year_window = case.get("year_window")
        relevant = [p for p in predictions if p.get("recipe_id") == recipe]
        if year_window is not None:
            lo, hi = year_window
            relevant = [p for p in relevant if lo <= p.get("year", -1) <= hi]
        if not relevant:
            return {
                "case_id": case_id, "country": country, "recipe": recipe,
                "status": "SKIPPED",
                "reason": "no predictions for this recipe (or window)",
            }
        country_rows = [p for p in relevant if p.get("country") == match_country]
        if not country_rows:
            return {
                "case_id": case_id, "country": country, "recipe": recipe,
                "status": "SKIPPED",
                "reason": f"no predictions for country {match_country!r} (slug) in this recipe (or window)",
            }
        if len(country_rows) > 1:
            # Multi-row case (multi-year window or duplicate predictions). Take
            # the MEAN probability across rows; warn so Stage 1 can decide if
            # this aggregation is correct (max may be more appropriate for
            # "did the model ever rank country X high in the window?").
            _log.warning(
                "anchor case id=%s: %d prediction rows for country %s recipe %s; "
                "taking mean probability across the window. Stage 1 should "
                "confirm this aggregation is desired.",
                case_id, len(country_rows), country, recipe,
            )
            country_prob = float(np.mean([r["predicted_probability"] for r in country_rows]))
            country_prob_aggregation = "mean"
        else:
            country_prob = country_rows[0]["predicted_probability"]
            country_prob_aggregation = "single_row"
        # For multi-row windows, also collapse the relevant pool by country
        # (mean probability per country) so the percentile rank is meaningful.
        if year_window is not None and (year_window[0] != year_window[1]):
            by_country: dict[str, list[float]] = defaultdict(list)
            for p in relevant:
                by_country[p["country"]].append(p["predicted_probability"])
            sorted_preds = sorted(float(np.mean(v)) for v in by_country.values())
        else:
            sorted_preds = sorted(p["predicted_probability"] for p in relevant)
        # Percentile rank: fraction of countries with strictly lower probability
        n_below = sum(1 for v in sorted_preds if v < country_prob)
        n_total = len(sorted_preds)
        percentile = n_below / n_total if n_total > 0 else float("nan")
        pass_fail = (
            "PASS" if expected_band[0] <= percentile <= expected_band[1] else "FAIL"
        )
        return {
            "case_id": case_id, "country": country, "recipe": recipe,
            "status": pass_fail,
            "observed_percentile": percentile,
            "country_prob": country_prob,
            "country_prob_aggregation": country_prob_aggregation,
            "expected_rank_band": expected_band,
            "n_total": n_total,
        }
    # Sentinel case: requires Layer-1 recipe lookup. Stage 1 fills in the
    # mapping from layer1_id -> [recipe_id, ...] using the rubric output.
    return {
        "case_id": case_id, "country": country,
        "recipe_sentinel": case.get("recipe_sentinel"),
        "resolves_to_layer1": case.get("resolves_to_layer1"),
        "status": "DEFERRED_TO_STAGE_1",
        "reason": "sentinel case requires Layer-1 recipe lookup; orchestrator wires this in Stage 1",
    }


def evaluate_anchor_battery(
    predictions: list[dict[str, Any]],
    anchor_battery: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate the full anchor battery (active + deferred from JSON)."""
    active_results = [
        evaluate_anchor_case(c, predictions)
        for c in anchor_battery.get("active_cases", [])
    ]
    deferred_results = [
        {
            "case_id": c["id"], "country": c["country"], "recipe": c.get("recipe"),
            "status": "DEFERRED_BY_HARD_GATE",
            "reason": c.get("deferred_reason", "deferred per anchor JSON"),
        }
        for c in anchor_battery.get("deferred_cases", [])
    ]
    return {
        "active": active_results,
        "deferred": deferred_results,
        "n_active": len(active_results),
        "n_active_pass": sum(1 for r in active_results if r.get("status") == "PASS"),
        "n_active_fail": sum(1 for r in active_results if r.get("status") == "FAIL"),
        "n_active_skipped": sum(1 for r in active_results if r.get("status") == "SKIPPED"),
        "n_active_deferred_to_stage_1": sum(
            1 for r in active_results if r.get("status") == "DEFERRED_TO_STAGE_1"
        ),
        "n_active_not_yet_implemented": sum(
            1 for r in active_results if r.get("status") == "NOT_YET_IMPLEMENTED"
        ),
        "n_deferred_by_hard_gate": len(deferred_results),
    }


# ---------- Orchestrator ----------


def run_validation(
    predictions: list[dict[str, Any]],
    anchor_battery: dict[str, Any] | None = None,
    n_bootstrap: int = 1000,
    n_bins: int = 10,
    seed: int = 0,
    model_metadata_uri: str | None = None,
    validation_script_fingerprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute all v1 components and return the report payload."""
    # Group predictions by recipe_id
    by_recipe: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in predictions:
        rid = p.get("recipe_id")
        if rid is not None:
            by_recipe[rid].append(p)
    oos_per_recipe: dict[str, Any] = {}
    cal_per_recipe: dict[str, Any] = {}
    cal_bootstrap_per_recipe: dict[str, Any] = {}
    brier_per_recipe: dict[str, Any] = {}
    recipe_counts_per_recipe: dict[str, Any] = {}
    predictive_metrics_per_recipe: dict[str, Any] = {}
    for rid, rows in by_recipe.items():
        preds = np.array([r["predicted_probability"] for r in rows], dtype=float)
        labels = np.array([r["label"] for r in rows], dtype=int)
        # Per-recipe sample counts on the test set. n_pos_test feeds the
        # F5 head-class assignment rubric (HARD GATE: n_positive_verified
        # < 8 → recipe excluded). Surfaced here so Stage 2 walks can read
        # it directly from the canonical validation JSON without
        # rebuilding test-set tallies.
        n_test = int(labels.size)
        n_pos_test = int((labels == 1).sum())
        recipe_counts_per_recipe[rid] = {
            "n_test": n_test,
            "n_pos_test": n_pos_test,
            "n_neg_test": n_test - n_pos_test,
            "positive_rate": (n_pos_test / n_test) if n_test else 0.0,
        }
        oos_per_recipe[rid] = bootstrap_auc_ci(preds, labels, n_bootstrap=n_bootstrap, seed=seed)
        # Calibration: F1 GATE uses in-sample ECE (option a per founder
        # tie-break 2026-05-04). Bootstrap distribution reported alongside
        # as transparency diagnostic (option c, repurposed as side-by-side
        # rather than gate input).
        cal_per_recipe[rid] = compute_ece_and_reliability(preds, labels, n_bins=n_bins)
        cal_bootstrap_per_recipe[rid] = compute_ece_bootstrap_diagnostic(
            preds, labels, n_bins=n_bins, n_bootstrap=n_bootstrap, seed=seed,
        )
        brier_per_recipe[rid] = compute_brier_decomposition(preds, labels, n_bins=n_bins)
        # New REPORTED-only predictive metrics per founder ratification
        # 2026-05-05: AUC-PR (rare-event rank discrimination), BSS (Brier
        # vs base-rate baseline), Log Loss (penalizes confident-wrong).
        # Not gated; complement existing AUC + ECE + Brier on the
        # dashboard.
        predictive_metrics_per_recipe[rid] = {
            "auc_pr": compute_auc_pr(preds, labels),
            "brier_skill_score": compute_brier_skill_score(preds, labels),
            "log_loss": compute_log_loss(preds, labels),
        }
    anchor_results = (
        evaluate_anchor_battery(predictions, anchor_battery)
        if anchor_battery is not None else None
    )
    # Anchor Drift Score / Hit Rate / Health Index — REPORTED only,
    # not gated. Per founder ratification 2026-05-05. Higher AHI = better.
    anchor_drift_metrics = (
        compute_anchor_drift_metrics(anchor_results)
        if anchor_results is not None else None
    )
    return {
        "schema_version": 1,
        "validation_run_id": _generate_validation_run_id(),
        "generated_at_utc": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
        "model_metadata_uri": model_metadata_uri,
        "validation_script_fingerprint": validation_script_fingerprint,
        "n_predictions": len(predictions),
        "n_recipes": len(by_recipe),
        "params": {"n_bootstrap": n_bootstrap, "n_bins": n_bins, "seed": seed},
        "components": {
            "oos_by_time": {"per_recipe": oos_per_recipe},
            "calibration": {
                "per_recipe": cal_per_recipe,
                "per_recipe_bootstrap_diagnostic": cal_bootstrap_per_recipe,
                "gate_uses": "in_sample_ece (option a per founder tie-break 2026-05-04)",
                "diagnostic_only": (
                    "per_recipe_bootstrap_diagnostic — sampling-variability of in-sample ECE; "
                    "75th percentile is Ji-Hoon's preferred conservative number for transparency, "
                    "NOT applied to the F1 0.08 gate"
                ),
            },
            "brier": {"per_recipe": brier_per_recipe},
            "anchor_battery": anchor_results,
            "anchor_drift_metrics": anchor_drift_metrics,
            "predictive_metrics": {
                "per_recipe": predictive_metrics_per_recipe,
                "purpose": (
                    "REPORTED-only predictive-power metrics (not gated). "
                    "auc_pr = Average Precision (rank discrimination on "
                    "rare-event axis); brier_skill_score = Brier vs base- "
                    "rate baseline (1=perfect, 0=naive, <0=worse); "
                    "log_loss = cross-entropy (penalizes confident wrong "
                    "predictions). Founder ratification 2026-05-05."
                ),
            },
            "recipe_counts": {
                "per_recipe": recipe_counts_per_recipe,
                "purpose": (
                    "Per-recipe test-set sample counts. n_pos_test is "
                    "the F5 rubric HARD GATE input (n_pos < 8 -> recipe "
                    "excluded from head-class assignment per "
                    "docs/specs/internal/ops/ml-track/06-modular-architecture.md)."
                ),
            },
        },
        "components_implemented_v1": [1, 3, 4, 6],
        "components_deferred": {
            "stage_2_or_3": [2, 5, 7, 8, 9],
            "rationale": "Stage 1 v0 baseline minimum is components 1+3+4+6 per Stage 0 spec",
        },
    }


def _generate_validation_run_id() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ_validation")


# ---------- CLI ----------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--predictions", type=Path, required=True,
                        help="JSON file with predictions (schema v1)")
    parser.add_argument("--anchors", type=Path, default=DEFAULT_ANCHORS,
                        help=f"anchor-case-battery JSON (default: {DEFAULT_ANCHORS})")
    parser.add_argument("--metadata", type=Path, default=None,
                        help="model metadata URI/path (recorded in report)")
    parser.add_argument("--output", type=Path, default=None,
                        help="output JSON path (default: stdout)")
    parser.add_argument("--n-bootstrap", type=int, default=1000)
    parser.add_argument("--n-bins", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    pred_payload = json.loads(args.predictions.read_text(encoding="utf-8"))
    predictions = pred_payload["predictions"]
    anchors = json.loads(args.anchors.read_text(encoding="utf-8")) if args.anchors.exists() else None
    model_metadata_uri = pred_payload.get("model_metadata_uri")
    if args.metadata:
        model_metadata_uri = str(args.metadata)
    fingerprint = None
    try:
        from ml_registry import fingerprint_validation_script
        fingerprint = asdict(fingerprint_validation_script(Path(__file__)))
    except Exception:
        pass

    report = run_validation(
        predictions=predictions,
        anchor_battery=anchors,
        n_bootstrap=args.n_bootstrap,
        n_bins=args.n_bins,
        seed=args.seed,
        model_metadata_uri=model_metadata_uri,
        validation_script_fingerprint=fingerprint,
    )
    out = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
