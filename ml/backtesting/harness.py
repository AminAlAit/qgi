"""Rolling-window out-of-sample backtest harness for QGI endogenous trajectory models."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ml.backtesting.baselines import naive_persistence_baseline
from ml.backtesting.metrics import brier_score, log_loss_score


@dataclass(frozen=True)
class BacktestReport:
    recipe_id: str
    n_samples: int
    model_brier: float
    baseline_brier: float
    model_log_loss: float
    baseline_log_loss: float

    @property
    def outperforms_baseline(self) -> bool:
        return self.model_brier < self.baseline_brier and self.model_log_loss < self.baseline_log_loss


def run_rolling_backtest(
    recipe_id: str,
    y_true: np.ndarray,
    model_probs: np.ndarray,
) -> BacktestReport:
    """Evaluate out-of-sample model probabilities against naive persistence baseline."""
    yt = np.asarray(y_true, dtype=float)
    mp = np.asarray(model_probs, dtype=float)
    if yt.shape != mp.shape or yt.ndim != 1:
        raise ValueError(f"Mismatched 1D arrays: {yt.shape} vs {mp.shape}")
    base_probs = naive_persistence_baseline(yt)
    return BacktestReport(
        recipe_id=recipe_id,
        n_samples=int(yt.size),
        model_brier=brier_score(yt, mp),
        baseline_brier=brier_score(yt, base_probs),
        model_log_loss=log_loss_score(yt, mp),
        baseline_log_loss=log_loss_score(yt, base_probs),
    )
