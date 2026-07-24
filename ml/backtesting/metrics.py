"""Calibration, proper scoring rules, and directional accuracy metrics for QGI backtests."""
from __future__ import annotations

import numpy as np


def brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Compute Brier score E[(p - y)^2]."""
    yt = np.asarray(y_true, dtype=float)
    yp = np.clip(np.asarray(y_prob, dtype=float), 0.0, 1.0)
    return float(np.mean((yp - yt) ** 2))


def log_loss_score(y_true: np.ndarray, y_prob: np.ndarray, eps: float = 1e-7) -> float:
    """Compute binary cross-entropy log-loss."""
    yt = np.asarray(y_true, dtype=float)
    yp = np.clip(np.asarray(y_prob, dtype=float), eps, 1.0 - eps)
    return float(-np.mean(yt * np.log(yp) + (1.0 - yt) * np.log(1.0 - yp)))


def directional_accuracy(y_true_delta: np.ndarray, y_pred_delta: np.ndarray) -> float:
    """Compute sign concordance accuracy on first differences."""
    yt = np.asarray(y_true_delta, dtype=float)
    yp = np.asarray(y_pred_delta, dtype=float)
    if yt.size == 0:
        return 0.0
    return float(np.mean(np.sign(yt) == np.sign(yp)))
