"""Beta calibration (Kull, Silva Filho, Flach 2017).

Used by Stage 1+ per-recipe heads. Fits 3 parameters (a, b, c):

    g(s)            = a*log(s) + b*log(1-s) + c
    p_calibrated(s) = sigmoid(g(s))

via maximum likelihood under L-BFGS-B with non-negativity constraints on a, b
(which ensures monotonicity in the resulting calibration function).

Beta calibration is preferred over Platt for rare-event regimes
(per docs/specs/internal/ops/ml-track/06-modular-architecture.md):
the Beta family is the natural conjugate for probability outputs and does
not assume sigmoid linearity.

Stage 0 deliverable extension per stage-1 build.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

_EPS = 1e-12


@dataclass
class BetaCalibrator:
    """Beta-calibration parameters fitted via MLE.

    Use:
        calibrator = BetaCalibrator.fit(raw_scores, labels)
        calibrated = calibrator.predict(raw_scores)
    """
    a: float
    b: float
    c: float
    n_fit: int
    converged: bool

    @classmethod
    def fit(
        cls,
        raw_scores: np.ndarray,
        labels: np.ndarray,
        x0: tuple[float, float, float] = (1.0, 1.0, 0.0),
    ) -> "BetaCalibrator":
        s = np.clip(np.asarray(raw_scores, dtype=float), _EPS, 1 - _EPS)
        y = np.asarray(labels, dtype=int)
        if s.shape != y.shape:
            raise ValueError(f"shape mismatch: scores {s.shape} vs labels {y.shape}")
        if s.size < 2:
            # Degenerate — return identity calibrator
            return cls(a=1.0, b=1.0, c=0.0, n_fit=int(s.size), converged=False)
        log_s = np.log(s)
        log_1_s = np.log(1 - s)

        def neg_log_likelihood(params: np.ndarray) -> float:
            a, b, c = params
            g = a * log_s + b * log_1_s + c
            # log Bernoulli likelihood: y*log(sigmoid(g)) + (1-y)*log(1-sigmoid(g))
            #                         = y*g - log(1 + exp(g))
            # logaddexp(0, g) = log(1+exp(g)), numerically stable
            ll = (y * g - np.logaddexp(0.0, g)).sum()
            return -ll

        # Bounds: a, b >= 0 enforces monotonicity; c is unbounded.
        result = minimize(
            neg_log_likelihood,
            x0=np.array(x0, dtype=float),
            method="L-BFGS-B",
            bounds=[(0.0, None), (0.0, None), (None, None)],
        )
        a, b, c = float(result.x[0]), float(result.x[1]), float(result.x[2])
        return cls(a=a, b=b, c=c, n_fit=int(s.size), converged=bool(result.success))

    def predict(self, raw_scores: np.ndarray) -> np.ndarray:
        s = np.clip(np.asarray(raw_scores, dtype=float), _EPS, 1 - _EPS)
        g = self.a * np.log(s) + self.b * np.log(1 - s) + self.c
        # sigmoid(g) numerically stable
        return 1.0 / (1.0 + np.exp(-g))

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "c": self.c,
                "n_fit": self.n_fit, "converged": self.converged}


# -----------------------------------------------------------------------------
# Calibration emit helpers (#969 — F-ML-1 walk-driver emit; FRONTEND §3.6).
# Pure functions consumed by run_f_ml_1_poc.py at emit time. The dashboard's
# CalibrationPanel renders the bins + ECE directly; the verdict policy
# (LOCK requires ECE <= floor) is a METHODOLOGY GATE handled separately via
# Majles ratification — these helpers ship the data the policy will consume.
# -----------------------------------------------------------------------------

_N_BINS_DEFAULT = 10  # frontend convention: 10 bins of 10pp width


def compute_calibration_bins(probs: np.ndarray, labels: np.ndarray,
                              n_bins: int = _N_BINS_DEFAULT) -> list[dict]:
    """10 bins of 10pp width on the predicted axis. Each bin reports `predicted_lo`,
    `predicted_hi`, `count`, and `observed_rate` (None when the bin is empty — the
    dashboard renders the gap honestly rather than zero-filling)."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    bins: list[dict] = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        # Last bin is closed on the right so a prediction of 1.0 isn't dropped.
        if i == n_bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        count = int(mask.sum())
        bins.append({"predicted_lo": float(lo),
                      "predicted_hi": float(hi),
                      "count": count,
                      "observed_rate": float(labels[mask].mean()) if count else None})
    return bins


def compute_ece(probs: np.ndarray, labels: np.ndarray,
                n_bins: int = _N_BINS_DEFAULT) -> float:
    """Expected Calibration Error (Naeini et al. 2015): weighted average of
    |mean_pred - mean_obs| over bins, weights = bin_count / total. Returns NaN
    on empty input (honest gap, not silent zero)."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    total = int(probs.size)
    if total == 0:
        return float("nan")
    ece = 0.0
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        if i == n_bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        n_bin = int(mask.sum())
        if n_bin == 0:
            continue
        mean_pred = float(probs[mask].mean())
        mean_obs = float(labels[mask].mean())
        ece += (n_bin / total) * abs(mean_pred - mean_obs)
    return float(ece)


def compute_calibration_block(probs: np.ndarray, labels: np.ndarray) -> dict:
    """One-stop computation of the `calibration` block the F-ML-1 walk emits into
    `f-ml-1-poc-summary.json` per #969. ALWAYS returns a well-formed dict (either
    `computed:True` + populated, or `computed:False` + reason) so the dashboard's
    CalibrationPanel can render honestly under every condition.

    Methodology: fits a 3-parameter Beta calibration on the pooled LOCO predictions
    (BetaCalibrator above), applies the calibration to the same predictions, then
    bins the CALIBRATED probabilities and computes ECE on them. This is the data
    the verdict-policy gate will consume once Majles ratifies the LOCK-requires-ECE
    rule — this PR is emit-only; verdict logic is unchanged.
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if probs.shape != labels.shape:
        return {"computed": False,
                "reason": f"shape mismatch: probs {probs.shape} vs labels {labels.shape}"}
    if probs.size < 10:
        return {"computed": False,
                "reason": f"too few predictions ({probs.size} < 10) for a defensible MLE fit"}
    n_pos, n_neg = int((labels == 1).sum()), int((labels == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return {"computed": False,
                "reason": f"single-class predictions (n_pos={n_pos}, n_neg={n_neg}); "
                          f"calibration is undefined"}
    try:
        cal = BetaCalibrator.fit(probs, labels)
    except (ValueError, RuntimeError) as exc:
        return {"computed": False, "reason": f"fit error: {exc}"}
    if not cal.converged:
        return {"computed": False,
                "reason": "MLE L-BFGS-B did not converge"}
    cal_probs = cal.predict(probs)
    bins = compute_calibration_bins(cal_probs, labels)
    ece = compute_ece(cal_probs, labels)
    return {
        "computed": True,
        "method": "beta-3param (Kull, Silva Filho, Flach 2017) — sigmoid(a*log(p) + b*log(1-p) + c)",
        "fit": cal.to_dict(),
        "bins": bins,
        "ece": ece,
        "n_predictions": int(probs.size),
        "notes": (
            "ECE computed on the CALIBRATED probabilities (post-Beta). The verdict "
            "policy (whether LOCK requires ECE <= floor) is a methodology gate "
            "handled separately under qgi-aws-tf#969 + Majles ratification; this "
            "emit is the data the policy will consume."
        ),
    }
