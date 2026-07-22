"""Baseline predictors for out-of-sample rolling backtest comparison."""
from __future__ import annotations

import numpy as np


def naive_persistence_baseline(y_history: np.ndarray) -> np.ndarray:
    """Predict t+1 probability as the trailing empirical base rate up to t."""
    y = np.asarray(y_history, dtype=float)
    if y.size == 0:
        return np.array([], dtype=float)
    csum = np.cumsum(y)
    counts = np.arange(1, y.size + 1, dtype=float)
    preds = np.empty_like(y, dtype=float)
    preds[0] = float(np.mean(y))
    if y.size > 1:
        preds[1:] = csum[:-1] / counts[:-1]
    return np.clip(preds, 1e-6, 1.0 - 1e-6)


def random_walk_baseline(series: np.ndarray) -> np.ndarray:
    """Predict t+1 continuous trajectory value as y_{t} (martingale persistence)."""
    arr = np.asarray(series, dtype=float)
    if arr.size == 0:
        return np.array([], dtype=float)
    out = np.empty_like(arr, dtype=float)
    out[0] = arr[0]
    if arr.size > 1:
        out[1:] = arr[:-1]
    return out
