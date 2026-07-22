"""F5=3 DeepHit-lite discrete-time hazard head for QGI Stage 2 walks.

Pre-registered architecture per `docs/specs/internal/ops/ml-track/
stage-2-walk-prereg-elections.md` (commit `dae7741`):

- **Input**: leaf-index features from frozen Stage 1 LightGBM backbones,
  one-hot encoded (max ≈ 4780 binary features for the tuned 956-tree
  model across 23 boosters).
- **Architecture**: 2-layer MLP (D → 64 → 32 → T) with ReLU activations,
  per-bin sigmoid hazards as outputs.
- **Loss**: discrete-time logit-hazard NLL with survival masking. No
  ranking loss (single-event-type recipes don't need DeepHit's
  competing-risks ranking term).
- **Output collapse**: cumulative incidence at locked horizon T_eval=1y
  → for 1-year horizon, cumulative incidence = h_1 (single-bin hazard).
- **Calibration**: applied OUTSIDE this head (isotonic on the collapsed
  scalar). This module produces raw cumulative-incidence values; the
  walk runner fits + applies the calibrator.
- **Locked decisions** (touching invalidates the walk):
    - episode framing: each (country, year) row = one observation
    - target tensor: forward labels at horizons 1..T (years t+1..t+T)
    - mask: 1 where target year ≤ data boundary, 0 elsewhere
    - num_horizons T = 4 (predicts 1y..4y forward; F-rules use h_1)

This module exposes **pure-function** training/prediction utilities
(easy to unit-test) AND a thin **DeepHitLiteHead** class wrapping them
into a sklearn-style fit/predict interface for the walk runner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_MAX_HORIZON = 4
DEFAULT_HIDDEN_DIMS = (64, 32)
DEFAULT_LEARNING_RATE = 1e-3
DEFAULT_MAX_EPOCHS = 100
DEFAULT_BATCH_SIZE = 256
DEFAULT_EARLY_STOP_PATIENCE = 10
DEFAULT_DROPOUT = 0.0
DEFAULT_WEIGHT_DECAY = 1e-4
DEFAULT_SEED = 0
EVAL_HORIZON_YEARS = 1  # locked: predicted_probability collapse at year+1


# ---------- Episode tensor construction (testable, no torch) -------------


def build_forward_targets(
    df: pd.DataFrame,
    *,
    label_col: str = "label",
    country_col: str = "country",
    year_col: str = "year",
    max_horizon: int = DEFAULT_MAX_HORIZON,
    data_year_max: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Build (Y, mask) tensors of shape (N, T) from a long-format
    (country, year, label) DataFrame.

    Y[i, t-1] = 1 if country_i had an event at (year_i + t), else 0.
    mask[i, t-1] = 1 if (year_i + t) <= data_year_max, else 0.

    Mask is conservatively zero where ground-truth labels at the future
    year are unobservable. This means the head's loss only penalizes
    bins where we have observed labels.

    Parameters
    ----------
    df : DataFrame with `country_col`, `year_col`, `label_col`
    max_horizon : T (number of forward bins)
    data_year_max : last year for which labels are observed; defaults
        to df[year_col].max()

    Returns
    -------
    Y : ndarray (N, T) int
    mask : ndarray (N, T) int
    """
    required = {country_col, year_col, label_col}
    missing = required - set(df.columns)
    if missing:
        msg = f"build_forward_targets: missing columns {missing}"
        raise ValueError(msg)

    if data_year_max is None:
        data_year_max = int(df[year_col].max())

    # Index labels by (country, year) for fast lookup.
    label_lookup: dict[tuple[Any, int], int] = {}
    for _, row in df.iterrows():
        label_lookup[(row[country_col], int(row[year_col]))] = int(row[label_col])

    n = len(df)
    Y = np.zeros((n, max_horizon), dtype=int)
    mask = np.zeros((n, max_horizon), dtype=int)

    rows = df[[country_col, year_col]].itertuples(index=False)
    for i, (country, year) in enumerate(rows):
        year_int = int(year)
        for t in range(1, max_horizon + 1):
            target_year = year_int + t
            if target_year <= data_year_max:
                mask[i, t - 1] = 1
                Y[i, t - 1] = label_lookup.get((country, target_year), 0)
            # else: mask stays 0, Y stays 0 (ignored by loss)
    return Y, mask


def collapse_to_cumulative_incidence(
    hazards: np.ndarray,
    horizon_years: int = EVAL_HORIZON_YEARS,
) -> np.ndarray:
    """Collapse per-bin hazard predictions to single-number
    cumulative incidence at `horizon_years`.

    Formula: P(event by year+horizon) = 1 - prod_{t=1..horizon}(1 - h_t).

    For horizon=1 (the locked default): result = h_1.

    Parameters
    ----------
    hazards : ndarray (N, T)
    horizon_years : int, must be in [1, T]

    Returns
    -------
    cumulative_incidence : ndarray (N,)
    """
    if hazards.ndim != 2:
        msg = f"hazards must be 2D, got shape {hazards.shape}"
        raise ValueError(msg)
    if not 1 <= horizon_years <= hazards.shape[1]:
        msg = f"horizon_years must be in [1, {hazards.shape[1]}], got {horizon_years}"
        raise ValueError(msg)
    survival = np.prod(1.0 - hazards[:, :horizon_years], axis=1)
    return 1.0 - survival


# ---------- Head class (uses torch lazily) -------------------------------


@dataclass
class DeepHitLiteConfig:
    """Configuration for DeepHitLiteHead.

    Locked items per pre-registration:
    - max_horizon=4 (T)
    - hidden_dims=(64, 32) — Ji-Hoon's recommended defaults
    - eval_horizon_years=1 — F-rule applies at this horizon
    """

    max_horizon: int = DEFAULT_MAX_HORIZON
    hidden_dims: tuple[int, ...] = DEFAULT_HIDDEN_DIMS
    learning_rate: float = DEFAULT_LEARNING_RATE
    max_epochs: int = DEFAULT_MAX_EPOCHS
    batch_size: int = DEFAULT_BATCH_SIZE
    early_stop_patience: int = DEFAULT_EARLY_STOP_PATIENCE
    dropout: float = DEFAULT_DROPOUT
    weight_decay: float = DEFAULT_WEIGHT_DECAY
    seed: int = DEFAULT_SEED
    eval_horizon_years: int = EVAL_HORIZON_YEARS


@dataclass
class DeepHitLiteHead:
    """sklearn-style head wrapping a 2-layer MLP for discrete-time hazards.

    Usage::

        head = DeepHitLiteHead(config=DeepHitLiteConfig())
        head.fit(X_train, Y_train, mask_train, X_val, Y_val, mask_val)
        cumulative_incidence_pred = head.predict_proba(X_test)  # (N,)
        hazards_pred = head.predict_hazards(X_test)             # (N, T)
    """

    config: DeepHitLiteConfig = field(default_factory=DeepHitLiteConfig)
    _torch_module: Any = field(init=False, default=None)
    _input_dim: int = field(init=False, default=0)
    _is_fitted: bool = field(init=False, default=False)
    _train_history: list[dict[str, float]] = field(init=False, default_factory=list)

    def fit(
        self,
        X_train: np.ndarray,
        Y_train: np.ndarray,
        mask_train: np.ndarray,
        X_val: np.ndarray | None = None,
        Y_val: np.ndarray | None = None,
        mask_val: np.ndarray | None = None,
    ) -> "DeepHitLiteHead":
        n_samples, input_dim = X_train.shape
        if Y_train.shape != (n_samples, self.config.max_horizon):
            msg = f"Y_train shape {Y_train.shape} != ({n_samples}, {self.config.max_horizon})"
            raise ValueError(msg)
        if mask_train.shape != Y_train.shape:
            msg = f"mask_train shape {mask_train.shape} != Y_train shape {Y_train.shape}"
            raise ValueError(msg)

        import torch
        import torch.nn as nn
        import torch.optim as optim

        # Reproducibility.
        torch.manual_seed(self.config.seed)
        np.random.seed(self.config.seed)

        self._input_dim = input_dim
        self._torch_module = self._build_module(input_dim)

        optimizer = optim.AdamW(
            self._torch_module.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )
        bce_per_element = nn.BCEWithLogitsLoss(reduction="none")

        X_t = torch.from_numpy(X_train.astype(np.float32))
        Y_t = torch.from_numpy(Y_train.astype(np.float32))
        M_t = torch.from_numpy(mask_train.astype(np.float32))
        n_train = X_t.shape[0]

        if X_val is not None and Y_val is not None and mask_val is not None:
            X_v = torch.from_numpy(X_val.astype(np.float32))
            Y_v = torch.from_numpy(Y_val.astype(np.float32))
            M_v = torch.from_numpy(mask_val.astype(np.float32))
        else:
            X_v = Y_v = M_v = None

        best_val_loss = float("inf")
        epochs_without_improvement = 0
        best_state = None

        rng = np.random.default_rng(self.config.seed)
        for epoch in range(self.config.max_epochs):
            # Shuffle indices each epoch.
            perm = rng.permutation(n_train)
            self._torch_module.train()
            # Accumulate raw masked-loss sums + mask-element counts across
            # batches; divide ONCE at epoch end. QA review of PR #25
            # caught that multiplying batch-mean by len(idx) and dividing
            # by total sample count double-normalizes (weights batches by
            # sample count instead of valid mask-element count) and feeds
            # a biased signal to early stopping. Match val-loss's
            # single-pass computation.
            train_masked_sum_total = 0.0
            train_mask_sum_total = 0.0
            for start in range(0, n_train, self.config.batch_size):
                idx = perm[start : start + self.config.batch_size]
                xb = X_t[idx]
                yb = Y_t[idx]
                mb = M_t[idx]
                logits = self._torch_module(xb)  # (B, T)
                loss_per_element = bce_per_element(logits, yb)  # (B, T)
                masked = loss_per_element * mb
                # Mean over masked elements (avoid zeros from masked-out cells).
                denom = mb.sum().clamp(min=1.0)
                loss = masked.sum() / denom
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                train_masked_sum_total += float(masked.sum().item())
                train_mask_sum_total += float(mb.sum().item())
            train_loss_mean = train_masked_sum_total / max(train_mask_sum_total, 1.0)

            # Validation.
            val_loss_mean = float("nan")
            if X_v is not None:
                self._torch_module.eval()
                with torch.no_grad():
                    logits_v = self._torch_module(X_v)
                    loss_per_element_v = bce_per_element(logits_v, Y_v)
                    masked_v = loss_per_element_v * M_v
                    denom_v = M_v.sum().clamp(min=1.0)
                    val_loss_mean = float((masked_v.sum() / denom_v).item())

            self._train_history.append({
                "epoch": epoch,
                "train_loss": train_loss_mean,
                "val_loss": val_loss_mean,
            })

            # Early stopping on val_loss.
            if X_v is not None:
                if val_loss_mean < best_val_loss - 1e-6:
                    best_val_loss = val_loss_mean
                    best_state = {k: v.clone() for k, v in self._torch_module.state_dict().items()}
                    epochs_without_improvement = 0
                else:
                    epochs_without_improvement += 1
                    if epochs_without_improvement >= self.config.early_stop_patience:
                        break

        # Restore best state if early-stopped on val.
        if best_state is not None:
            self._torch_module.load_state_dict(best_state)

        self._is_fitted = True
        return self

    def predict_hazards(self, X: np.ndarray) -> np.ndarray:
        if not self._is_fitted:
            msg = "DeepHitLiteHead not fitted; call fit() first"
            raise RuntimeError(msg)
        import torch

        self._torch_module.eval()
        X_t = torch.from_numpy(X.astype(np.float32))
        with torch.no_grad():
            logits = self._torch_module(X_t)
            hazards = torch.sigmoid(logits).cpu().numpy()
        return hazards

    def predict_proba(
        self,
        X: np.ndarray,
        horizon_years: int | None = None,
    ) -> np.ndarray:
        """Locked anchor-eval interface: returns scalar cumulative
        incidence at `horizon_years` (default = config.eval_horizon_years
        = 1). Output shape (N,)."""
        h = horizon_years if horizon_years is not None else self.config.eval_horizon_years
        hazards = self.predict_hazards(X)
        return collapse_to_cumulative_incidence(hazards, horizon_years=h)

    def _build_module(self, input_dim: int):
        import torch.nn as nn

        layers = []
        prev_dim = input_dim
        for hidden in self.config.hidden_dims:
            layers.append(nn.Linear(prev_dim, hidden))
            layers.append(nn.ReLU())
            if self.config.dropout > 0:
                layers.append(nn.Dropout(self.config.dropout))
            prev_dim = hidden
        layers.append(nn.Linear(prev_dim, self.config.max_horizon))
        return nn.Sequential(*layers)
