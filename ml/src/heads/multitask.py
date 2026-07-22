"""Phase D D2 — Multi-task head with shared representation across recipes.

Per docs/specs/internal/ops/ml-track/stage-2-amendment-2026-05-05.md
(commit `04fa5fb`) D2 — Priya Venkataraman-Szabo's recommendation
at the post-PoC trio convening 2026-05-05.

## Why this matters

Stage 1 v0 architecture has a SHARED backbone (23 binary LightGBM
boosters with identical hyperparams) but INDEPENDENT per-recipe LR
heads. The independent heads cannot borrow strength across recipes
for countries with sparse event histories.

Phase C LOCO diagnosis empirically showed that for `civil_war_and_
insurgency` and `bilateral_treaty`, the model relies heavily on
country-identity memorization (LOCO-AUC catastrophic drop from
in-sample). ICC analysis (Phase D D1) showed only 2 features are
high-ICC scale features (population, GDP); the leak must therefore
come from non-linear LightGBM-tree combinations encoding country
identity.

Multi-task with shared representation addresses this: by forcing the
intermediate layer to learn a SHARED embedding that works for ALL
23 recipes, the model is regularized away from recipe-specific
country-identity shortcuts.

## Architecture

```
Input: leaf one-hot features (~4780-dim from frozen Stage 1 backbone)
        |
        v
Shared MLP: D -> 128 -> 64 (cross-recipe representation)
        |
        v
K parallel sigmoid heads (one per recipe)
        |
        v
K predictions per (country, year) sample
```

## Loss

Sum of per-recipe BCE losses, with per-recipe class_weight to handle
positive-class imbalance:

    L = sum_k mean_over_batch(BCE_k(pred_k, label_k) * pos_weight_k)
      = (loss_per_element).mean(dim=0).sum()

The `.mean(dim=0).sum()` aggregation is the canonical multi-task BCE
form: mean over batch (so gradient scale is sample-count-invariant),
sum over recipes (so gradient scale is recipe-count-invariant per
recipe). QA review of PR #34 caught that the original
`.mean()` over the full (B×K) tensor silently divided per-recipe
gradients by K=23.

This is the "hard parameter sharing" multi-task pattern — all
recipes share the embedding layers, only the output heads diverge.

## Pure functions; tests in tests/test_multitask_head.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

DEFAULT_HIDDEN_DIMS = (128, 64)
DEFAULT_LR = 1e-3
DEFAULT_MAX_EPOCHS = 100
DEFAULT_BATCH_SIZE = 256
DEFAULT_EARLY_STOP_PATIENCE = 10
DEFAULT_DROPOUT = 0.0
DEFAULT_WEIGHT_DECAY = 1e-4
DEFAULT_SEED = 0


@dataclass
class MultiTaskHeadConfig:
    """Configuration for MultiTaskHead.

    Locked items per Phase D D2 (docs-specs commit `04fa5fb`):
    - Shared MLP architecture
    - Per-recipe sigmoid output
    - Hard parameter sharing
    """

    hidden_dims: tuple[int, ...] = DEFAULT_HIDDEN_DIMS
    learning_rate: float = DEFAULT_LR
    max_epochs: int = DEFAULT_MAX_EPOCHS
    batch_size: int = DEFAULT_BATCH_SIZE
    early_stop_patience: int = DEFAULT_EARLY_STOP_PATIENCE
    dropout: float = DEFAULT_DROPOUT
    weight_decay: float = DEFAULT_WEIGHT_DECAY
    seed: int = DEFAULT_SEED


@dataclass
class MultiTaskHead:
    """Multi-task PyTorch head: shared representation + K sigmoid heads.

    Usage::

        head = MultiTaskHead(config=MultiTaskHeadConfig(), n_recipes=23)
        head.fit(X_train, Y_train_multilabel,
                 X_val=X_val, Y_val=Y_val_multilabel)
        preds = head.predict_proba(X_test)  # (N, K) array
    """

    config: MultiTaskHeadConfig = field(default_factory=MultiTaskHeadConfig)
    n_recipes: int = 23
    _torch_module: Any = field(init=False, default=None)
    _input_dim: int = field(init=False, default=0)
    _is_fitted: bool = field(init=False, default=False)
    _train_history: list[dict[str, float]] = field(init=False, default_factory=list)
    _pos_weights: np.ndarray | None = field(init=False, default=None)

    def fit(
        self,
        X_train: np.ndarray,
        Y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        Y_val: np.ndarray | None = None,
    ) -> "MultiTaskHead":
        """Train the multi-task head.

        Parameters
        ----------
        X_train : ndarray (N, D) - input features (e.g., leaf one-hot)
        Y_train : ndarray (N, K) int multi-label targets ({0, 1})
        X_val, Y_val : optional held-out for early stopping
        """
        n_samples, input_dim = X_train.shape
        if Y_train.shape != (n_samples, self.n_recipes):
            msg = f"Y_train shape {Y_train.shape} != ({n_samples}, {self.n_recipes})"
            raise ValueError(msg)

        import torch
        import torch.nn as nn
        import torch.optim as optim

        torch.manual_seed(self.config.seed)
        np.random.seed(self.config.seed)

        self._input_dim = input_dim
        self._torch_module = self._build_module(input_dim)

        # Per-recipe pos_weight for class imbalance — scale_pos_weight = n_neg / n_pos
        n_pos_per_recipe = (Y_train == 1).sum(axis=0)
        n_neg_per_recipe = (Y_train == 0).sum(axis=0)
        # Avoid div-by-zero; recipes with zero positives get pos_weight=1
        pos_weights = np.where(
            n_pos_per_recipe > 0,
            n_neg_per_recipe / np.maximum(n_pos_per_recipe, 1),
            1.0,
        ).astype(np.float32)
        self._pos_weights = pos_weights
        pos_weight_tensor = torch.from_numpy(pos_weights)

        optimizer = optim.AdamW(
            self._torch_module.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )
        # BCEWithLogitsLoss with pos_weight: per-recipe class-balancing
        bce_per_element = nn.BCEWithLogitsLoss(
            pos_weight=pos_weight_tensor, reduction="none",
        )

        X_t = torch.from_numpy(X_train.astype(np.float32))
        Y_t = torch.from_numpy(Y_train.astype(np.float32))
        n_train = X_t.shape[0]

        if X_val is not None and Y_val is not None:
            X_v = torch.from_numpy(X_val.astype(np.float32))
            Y_v = torch.from_numpy(Y_val.astype(np.float32))
        else:
            X_v = Y_v = None

        best_val_loss = float("inf")
        epochs_without_improvement = 0
        best_state: dict[str, Any] | None = None

        rng = np.random.default_rng(self.config.seed)
        for epoch in range(self.config.max_epochs):
            perm = rng.permutation(n_train)
            self._torch_module.train()
            # Accumulate raw element-sums + counts; divide ONCE at epoch
            # end to match DeepHit-lite's pattern (see QA PR #25
            # blocker fix). Loss aggregation: mean over batch, sum over
            # recipes -- canonical multi-task BCE form.
            train_loss_sum_total = 0.0  # sum over batches of (sum-over-recipes-of-batch-mean)
            train_n_batches = 0
            for start in range(0, n_train, self.config.batch_size):
                idx = perm[start : start + self.config.batch_size]
                xb = X_t[idx]
                yb = Y_t[idx]
                logits = self._torch_module(xb)  # (B, K)
                loss_per_element = bce_per_element(logits, yb)  # (B, K)
                # mean over batch -> sum over recipes. Gradient scale
                # independent of K and B; matches docstring "sum of
                # per-recipe BCE losses."
                loss = loss_per_element.mean(dim=0).sum()
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                train_loss_sum_total += float(loss.item())
                train_n_batches += 1
            train_loss_mean = train_loss_sum_total / max(train_n_batches, 1)

            val_loss_mean = float("nan")
            if X_v is not None:
                self._torch_module.eval()
                with torch.no_grad():
                    logits_v = self._torch_module(X_v)
                    loss_per_element_v = bce_per_element(logits_v, Y_v)
                    # Same aggregation as training for consistency
                    val_loss_mean = float(loss_per_element_v.mean(dim=0).sum().item())

            self._train_history.append({
                "epoch": epoch,
                "train_loss": train_loss_mean,
                "val_loss": val_loss_mean,
            })

            if X_v is not None:
                if val_loss_mean < best_val_loss - 1e-6:
                    best_val_loss = val_loss_mean
                    best_state = {k: v.clone() for k, v in self._torch_module.state_dict().items()}
                    epochs_without_improvement = 0
                else:
                    epochs_without_improvement += 1
                    if epochs_without_improvement >= self.config.early_stop_patience:
                        break

        if best_state is not None:
            self._torch_module.load_state_dict(best_state)

        self._is_fitted = True
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return (N, K) sigmoid probabilities for each recipe."""
        if not self._is_fitted:
            msg = "MultiTaskHead not fitted; call fit() first"
            raise RuntimeError(msg)
        import torch

        self._torch_module.eval()
        X_t = torch.from_numpy(X.astype(np.float32))
        with torch.no_grad():
            logits = self._torch_module(X_t)
            probs = torch.sigmoid(logits).cpu().numpy()
        return probs

    def predict_proba_for_recipe(self, X: np.ndarray, recipe_idx: int) -> np.ndarray:
        """Return (N,) probabilities for a specific recipe index."""
        if not 0 <= recipe_idx < self.n_recipes:
            msg = f"recipe_idx must be in [0, {self.n_recipes}), got {recipe_idx}"
            raise ValueError(msg)
        return self.predict_proba(X)[:, recipe_idx]

    def _build_module(self, input_dim: int):
        import torch.nn as nn

        layers: list[Any] = []
        prev = input_dim
        for h in self.config.hidden_dims:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.ReLU())
            if self.config.dropout > 0:
                layers.append(nn.Dropout(self.config.dropout))
            prev = h
        # K parallel output heads
        layers.append(nn.Linear(prev, self.n_recipes))
        return nn.Sequential(*layers)
