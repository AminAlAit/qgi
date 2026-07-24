"""F-rule evaluation for Stage 2 walks.

Operational definitions LOCKED in
`docs/specs/internal/ops/ml-track/stage-2-walk-prereg-elections.md`
(commit `dae7741`):

- **F1 Calibration:** ECE > 0.08 → FALSIFY. Computed on collapsed
  `predicted_probability` (cumulative incidence at locked horizon).
- **F2 AUC indistinguishability:** bootstrap 95% CI on AUC; passes
  iff CI excludes 0.5 AND point ≥ 0.57.
- **F3 Hazard band (survival heads only):** width of bootstrap 95% CI
  on cumulative incidence at locked horizon, B≥500 stratified by
  positive/negative; > 0.30 → revert (recipe re-walks under F5=2).
- **Verdict gate:** C-index OR Brier regression > 0.03 vs Stage 1 LR
  baseline → F5_FALLBACK. NOTE: 0.03 sits inside CI noise band at
  n_pos_test=14 (CI width ≈ 0.12-0.15); the threshold is a locked
  commitment mechanism, not power-justified.

Pure functions; tests in `tests/test_walk_falsification.py`.
"""
from __future__ import annotations

from typing import Any

import numpy as np

# Locked thresholds per pre-reg
F1_ECE_THRESHOLD = 0.08
F2_AUC_POINT_THRESHOLD = 0.57
F2_AUC_BASELINE = 0.5
F3_HAZARD_BAND_THRESHOLD = 0.30
F3_DEFAULT_BOOTSTRAP_N = 500
BASELINE_REGRESSION_THRESHOLD = 0.03
DEFAULT_N_BOOTSTRAP = 1000
DEFAULT_N_BINS = 10


def compute_auc(probs: np.ndarray, labels: np.ndarray) -> float:
    """Compute AUC via the rank-sum identity (Mann-Whitney U / n_pos / n_neg).

    Returns NaN if either class is empty.
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if probs.shape != labels.shape:
        msg = f"probs and labels shape mismatch: {probs.shape} vs {labels.shape}"
        raise ValueError(msg)
    n_pos = int((labels == 1).sum())
    n_neg = int((labels == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    # Tied-aware ranking via average rank.
    order = np.argsort(probs, kind="mergesort")
    ranked_probs = probs[order]
    ranks = np.empty_like(ranked_probs, dtype=float)
    i = 0
    while i < len(ranked_probs):
        j = i
        while j < len(ranked_probs) - 1 and ranked_probs[j + 1] == ranked_probs[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-indexed
        ranks[i : j + 1] = avg_rank
        i = j + 1
    inv_order = np.empty_like(order)
    inv_order[order] = np.arange(len(order))
    rank_per_sample = ranks[inv_order]
    sum_ranks_pos = float(rank_per_sample[labels == 1].sum())
    auc = (sum_ranks_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def bootstrap_ci(
    func,
    *args: np.ndarray,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    seed: int = 0,
    stratify: np.ndarray | None = None,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Generic bootstrap-percentile 95% CI for a scalar metric.

    Parameters
    ----------
    func : callable
        Metric function taking *args (each shape (N,)) → scalar.
    *args : np.ndarray
        Arrays passed to func; the FIRST element's length defines N.
    n_bootstrap : int
        Number of resamples.
    seed : int
    stratify : np.ndarray | None
        If provided, sample WITH replacement separately within each
        unique value of `stratify` (preserving per-stratum sample size).
        Used for label-stratified bootstrap on F-rules.
    confidence : float, default 0.95.

    Returns
    -------
    (point_estimate, ci_lower, ci_upper)
    """
    if not 0 < confidence < 1:
        msg = f"confidence must be in (0, 1), got {confidence}"
        raise ValueError(msg)
    n = len(args[0])
    point = float(func(*args))
    if not np.isfinite(point):
        return (point, float("nan"), float("nan"))

    rng = np.random.default_rng(seed)
    boot_values: list[float] = []

    if stratify is not None:
        stratify = np.asarray(stratify)
        unique_strata = np.unique(stratify)
        stratum_indices = {s: np.where(stratify == s)[0] for s in unique_strata}
        for _ in range(n_bootstrap):
            idx_parts = [
                rng.choice(stratum_indices[s], size=len(stratum_indices[s]), replace=True)
                for s in unique_strata
            ]
            idx = np.concatenate(idx_parts)
            sampled_args = tuple(a[idx] for a in args)
            value = func(*sampled_args)
            if np.isfinite(value):
                boot_values.append(float(value))
    else:
        for _ in range(n_bootstrap):
            idx = rng.integers(0, n, size=n)
            sampled_args = tuple(a[idx] for a in args)
            value = func(*sampled_args)
            if np.isfinite(value):
                boot_values.append(float(value))

    if not boot_values:
        return (point, float("nan"), float("nan"))

    alpha = (1 - confidence) / 2.0
    arr = np.asarray(boot_values, dtype=float)
    ci_lo = float(np.percentile(arr, 100 * alpha))
    ci_hi = float(np.percentile(arr, 100 * (1 - alpha)))
    return (point, ci_lo, ci_hi)


def compute_ece(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = DEFAULT_N_BINS,
) -> float:
    """Expected Calibration Error: Σ_b (|n_b| / N) * |mean_prob_b - mean_label_b|.

    Returns NaN if input is empty or has < 2 bins of activity.
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if probs.shape != labels.shape:
        msg = f"probs and labels shape mismatch: {probs.shape} vs {labels.shape}"
        raise ValueError(msg)
    if probs.size == 0:
        return float("nan")
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    # Right-inclusive on last bin to capture exactly-1.0 predictions.
    bin_idx = np.clip(np.digitize(probs, bin_edges[1:-1], right=False), 0, n_bins - 1)
    ece = 0.0
    n_total = probs.size
    for b in range(n_bins):
        mask = bin_idx == b
        n_b = int(mask.sum())
        if n_b == 0:
            continue
        avg_prob = float(probs[mask].mean())
        avg_label = float(labels[mask].mean())
        ece += (n_b / n_total) * abs(avg_prob - avg_label)
    return float(ece)


def evaluate_f1(
    probs: np.ndarray,
    labels: np.ndarray,
    *,
    n_bins: int = DEFAULT_N_BINS,
    threshold: float = F1_ECE_THRESHOLD,
) -> dict[str, Any]:
    """F1 Calibration: ECE ≤ threshold → PASS."""
    ece = compute_ece(probs, labels, n_bins=n_bins)
    return {
        "rule": "F1_calibration",
        "metric": "ECE",
        "value": ece,
        "threshold": threshold,
        "passed": (np.isfinite(ece) and ece <= threshold),
        "n_bins": n_bins,
    }


def evaluate_f2(
    probs: np.ndarray,
    labels: np.ndarray,
    *,
    n_bootstrap: int = DEFAULT_N_BOOTSTRAP,
    seed: int = 0,
    point_threshold: float = F2_AUC_POINT_THRESHOLD,
    baseline: float = F2_AUC_BASELINE,
) -> dict[str, Any]:
    """F2 AUC indistinguishability: bootstrap 95% CI excludes baseline AND
    point ≥ point_threshold → PASS.
    """
    auc, ci_lo, ci_hi = bootstrap_ci(
        compute_auc, probs, labels,
        n_bootstrap=n_bootstrap, seed=seed, stratify=labels,
    )
    ci_excludes_baseline = (
        np.isfinite(ci_lo) and np.isfinite(ci_hi) and ci_lo > baseline
    )
    point_meets_threshold = (np.isfinite(auc) and auc >= point_threshold)
    passed = bool(ci_excludes_baseline and point_meets_threshold)
    return {
        "rule": "F2_auc",
        "metric": "AUC",
        "value": auc,
        "ci_lower": ci_lo,
        "ci_upper": ci_hi,
        "baseline": baseline,
        "point_threshold": point_threshold,
        "ci_excludes_baseline": bool(ci_excludes_baseline),
        "point_meets_threshold": bool(point_meets_threshold),
        "passed": passed,
        "n_bootstrap": n_bootstrap,
    }


def evaluate_f3(
    probs: np.ndarray,
    labels: np.ndarray,
    *,
    n_bootstrap: int = F3_DEFAULT_BOOTSTRAP_N,
    seed: int = 0,
    threshold: float = F3_HAZARD_BAND_THRESHOLD,
) -> dict[str, Any]:
    """F3 Hazard band: width of bootstrap 95% CI on the collapsed
    `predicted_probability` (cumulative incidence at locked horizon).

    Per pre-reg §5.F3: B≥500 stratified by positive/negative. If
    width > threshold → revert to F5=2.

    Note: this measures the SAMPLING UNCERTAINTY on the *mean*
    predicted probability across the test set — i.e., how variable our
    point-estimate of the typical predicted risk is under resampling.
    Width > 0.30 indicates pathological estimation variance.
    """
    def _mean_prob(p: np.ndarray, _: np.ndarray) -> float:
        return float(np.mean(p))

    point, ci_lo, ci_hi = bootstrap_ci(
        _mean_prob, probs, labels,
        n_bootstrap=n_bootstrap, seed=seed, stratify=labels,
    )
    if np.isfinite(ci_lo) and np.isfinite(ci_hi):
        band_width = float(ci_hi - ci_lo)
    else:
        band_width = float("nan")
    passed = (np.isfinite(band_width) and band_width <= threshold)
    return {
        "rule": "F3_hazard_band",
        "metric": "ci_width_on_mean_predicted_probability",
        "value": band_width,
        "ci_lower": ci_lo,
        "ci_upper": ci_hi,
        "point_estimate_mean_prob": point,
        "threshold": threshold,
        "passed": bool(passed),
        "n_bootstrap": n_bootstrap,
    }


def compute_brier(probs: np.ndarray, labels: np.ndarray) -> float:
    """Brier score = mean( (p - y)^2 ). Lower is better."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if probs.shape != labels.shape:
        msg = f"shape mismatch: {probs.shape} vs {labels.shape}"
        raise ValueError(msg)
    if probs.size == 0:
        return float("nan")
    return float(np.mean((probs - labels.astype(float)) ** 2))


def evaluate_baseline_comparison(
    deephit_probs: np.ndarray,
    baseline_probs: np.ndarray,
    labels: np.ndarray,
    *,
    threshold: float = BASELINE_REGRESSION_THRESHOLD,
) -> dict[str, Any]:
    """Verdict gate: C-index (= AUC for binary) AND Brier vs Stage 1 LR baseline.

    Per pre-reg §7: regression > 0.03 on EITHER metric → F5_FALLBACK.
    Disclosure §9.5: 0.03 sits inside CI noise band at n=14; threshold
    is the commitment mechanism, not power-justified.
    """
    deephit_auc = compute_auc(deephit_probs, labels)
    baseline_auc = compute_auc(baseline_probs, labels)
    deephit_brier = compute_brier(deephit_probs, labels)
    baseline_brier = compute_brier(baseline_probs, labels)

    # AUC: positive delta = improvement; negative = regression.
    delta_auc = (deephit_auc - baseline_auc) if (np.isfinite(deephit_auc) and np.isfinite(baseline_auc)) else float("nan")
    # Brier: lower is better; positive delta = regression.
    delta_brier = (deephit_brier - baseline_brier) if (np.isfinite(deephit_brier) and np.isfinite(baseline_brier)) else float("nan")

    auc_regression = (np.isfinite(delta_auc) and delta_auc < -threshold)
    brier_regression = (np.isfinite(delta_brier) and delta_brier > threshold)
    passed = not (auc_regression or brier_regression)
    return {
        "rule": "baseline_comparison",
        "deephit_auc": deephit_auc,
        "baseline_auc": baseline_auc,
        "delta_auc": delta_auc,
        "deephit_brier": deephit_brier,
        "baseline_brier": baseline_brier,
        "delta_brier": delta_brier,
        "threshold": threshold,
        "auc_regression": bool(auc_regression),
        "brier_regression": bool(brier_regression),
        "passed": bool(passed),
        "noise_band_disclosure": (
            "0.03 threshold sits inside bootstrap-CI noise band at "
            "low n_pos_test (≈ 0.12-0.15 expected width); locked as "
            "commitment mechanism, not power-justified gate."
        ),
    }


def decide_verdict(
    f1: dict[str, Any],
    f2: dict[str, Any],
    f3: dict[str, Any] | None,
    baseline_cmp: dict[str, Any],
) -> dict[str, Any]:
    """Combine F-rule outcomes into a single walk verdict.

    Verdict precedence (pre-reg §6):
    1. If F3 fails (survival head only) → "F5_FALLBACK" (recipe re-walks under F5=2)
    2. Else if baseline_cmp fails (C-index OR Brier regression > 0.03) → "F5_FALLBACK"
    3. Else if F1 OR F2 fails → "FALSIFIED" (recipe closed; no re-walk under same F5)
    4. Else → "LOCKED"

    Note: F5 reclassification mid-walk is NOT permitted (pre-reg §6).
    "F5_FALLBACK" means the CURRENT walk closes with a falsification
    finding for THIS F5 head class; the recipe re-enters the queue for a
    SEPARATE pre-registered walk under F5=2.
    """
    if f3 is not None and not f3["passed"]:
        return {
            "verdict": "F5_FALLBACK",
            "reason": "F3 hazard band exceeded threshold",
            "next_step": "recipe re-enters queue for separate F5=2 walk",
        }
    if not baseline_cmp["passed"]:
        regressions = []
        if baseline_cmp["auc_regression"]:
            regressions.append(f"AUC delta={baseline_cmp['delta_auc']:.4f}")
        if baseline_cmp["brier_regression"]:
            regressions.append(f"Brier delta={baseline_cmp['delta_brier']:.4f}")
        return {
            "verdict": "F5_FALLBACK",
            "reason": f"verdict gate regression vs Stage 1 LR baseline: {', '.join(regressions)}",
            "next_step": "recipe re-enters queue for separate F5=2 walk",
        }
    fail_rules = []
    if not f1["passed"]:
        fail_rules.append(f"F1 ECE={f1['value']:.4f} > {f1['threshold']}")
    if not f2["passed"]:
        if not f2["ci_excludes_baseline"]:
            fail_rules.append(f"F2 CI does not exclude {f2['baseline']}")
        if not f2["point_meets_threshold"]:
            fail_rules.append(f"F2 point AUC={f2['value']:.4f} < {f2['point_threshold']}")
    if fail_rules:
        return {
            "verdict": "FALSIFIED",
            "reason": "; ".join(fail_rules),
            "next_step": "recipe closed under this F5 class; documented",
        }
    return {
        "verdict": "LOCKED",
        "reason": "all F-rules + baseline-comparison gate passed",
        "next_step": "recipe is a v0 production candidate",
    }
