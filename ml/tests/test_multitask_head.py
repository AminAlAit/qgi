"""Tests for `qgi_ml.src.heads.multitask`."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from heads.multitask import (  # noqa: E402
    DEFAULT_HIDDEN_DIMS,
    MultiTaskHead,
    MultiTaskHeadConfig,
)


class TestMultiTaskHead:
    def _synthetic(self, n_samples: int = 300, input_dim: int = 50,
                   n_recipes: int = 5, seed: int = 0):
        """Build (X, Y) where some recipes share signal, others are
        independent. Adapts to any n_recipes >= 1."""
        pytest.importorskip("torch")
        rng = np.random.default_rng(seed)
        X = rng.normal(0, 1, (n_samples, input_dim)).astype(np.float32)
        logits = np.zeros((n_samples, n_recipes), dtype=np.float32)
        # Recipe 0: depends on X[:, 0] strongly (always present)
        logits[:, 0] = 2.0 * X[:, 0] + rng.normal(0, 0.3, n_samples)
        if n_recipes >= 2:
            # Recipe 1 shares signal with recipe 0 — multi-task should help
            logits[:, 1] = 2.0 * X[:, 0] + rng.normal(0, 0.3, n_samples)
        if n_recipes >= 3:
            # Recipe 2: orthogonal signal
            logits[:, 2] = 2.0 * X[:, 5] + rng.normal(0, 0.3, n_samples)
        # Remaining recipes: noise
        for k in range(3, n_recipes):
            logits[:, k] = rng.normal(0, 1, n_samples)
        Y = (logits > 0).astype(int)
        return X, Y

    def test_fit_and_predict_returns_correct_shapes(self) -> None:
        X, Y = self._synthetic(n_samples=200, n_recipes=5)
        head = MultiTaskHead(
            config=MultiTaskHeadConfig(max_epochs=5, batch_size=32, seed=0),
            n_recipes=5,
        )
        head.fit(X, Y)
        preds = head.predict_proba(X)
        assert preds.shape == (X.shape[0], 5)
        assert (preds >= 0).all() and (preds <= 1).all()

    def test_predict_proba_for_recipe(self) -> None:
        X, Y = self._synthetic(n_samples=200, n_recipes=5)
        head = MultiTaskHead(
            config=MultiTaskHeadConfig(max_epochs=5, batch_size=32, seed=0),
            n_recipes=5,
        )
        head.fit(X, Y)
        preds_all = head.predict_proba(X)
        preds_r0 = head.predict_proba_for_recipe(X, recipe_idx=0)
        np.testing.assert_allclose(preds_r0, preds_all[:, 0])

    def test_invalid_recipe_idx_raises(self) -> None:
        X, Y = self._synthetic(n_samples=100, n_recipes=3)
        head = MultiTaskHead(
            config=MultiTaskHeadConfig(max_epochs=2, batch_size=32, seed=0),
            n_recipes=3,
        )
        head.fit(X, Y)
        with pytest.raises(ValueError, match="recipe_idx must be in"):
            head.predict_proba_for_recipe(X, recipe_idx=10)

    def test_unfitted_raises(self) -> None:
        head = MultiTaskHead(n_recipes=3)
        with pytest.raises(RuntimeError, match="not fitted"):
            head.predict_proba(np.zeros((5, 10)))

    def test_shape_mismatch_raises(self) -> None:
        head = MultiTaskHead(n_recipes=5)
        X = np.zeros((10, 20))
        Y = np.zeros((10, 3), dtype=int)  # wrong K
        with pytest.raises(ValueError, match="Y_train shape"):
            head.fit(X, Y)

    def test_seeded_determinism(self) -> None:
        X, Y = self._synthetic(n_samples=200, n_recipes=5, seed=1)
        head_a = MultiTaskHead(
            config=MultiTaskHeadConfig(max_epochs=5, batch_size=32, seed=42),
            n_recipes=5,
        )
        head_b = MultiTaskHead(
            config=MultiTaskHeadConfig(max_epochs=5, batch_size=32, seed=42),
            n_recipes=5,
        )
        head_a.fit(X, Y)
        head_b.fit(X, Y)
        np.testing.assert_allclose(
            head_a.predict_proba(X[:5]),
            head_b.predict_proba(X[:5]),
            atol=1e-5,
        )

    def test_default_config(self) -> None:
        cfg = MultiTaskHeadConfig()
        assert cfg.hidden_dims == (128, 64)
        assert DEFAULT_HIDDEN_DIMS == (128, 64)

    def test_pos_weights_computed_per_recipe(self) -> None:
        X, Y = self._synthetic(n_samples=200, n_recipes=5)
        head = MultiTaskHead(
            config=MultiTaskHeadConfig(max_epochs=2, batch_size=32, seed=0),
            n_recipes=5,
        )
        head.fit(X, Y)
        assert head._pos_weights is not None
        assert head._pos_weights.shape == (5,)
        # All pos_weights must be positive (no zero-positive recipes in synthetic)
        assert (head._pos_weights > 0).all()

    def test_learns_synthetic_signal(self) -> None:
        """Smoke test: with strong signal, the head should learn AUC > 0.7
        on recipe 0 (which depends on X[:, 0])."""
        X, Y = self._synthetic(n_samples=500, n_recipes=5, seed=0)
        head = MultiTaskHead(
            config=MultiTaskHeadConfig(max_epochs=30, batch_size=64, seed=0),
            n_recipes=5,
        )
        head.fit(X, Y)
        preds = head.predict_proba_for_recipe(X, recipe_idx=0)
        # Compute AUC on recipe 0 — should be high because Y[:, 0] depends
        # strongly on X[:, 0]
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(Y[:, 0], preds)
        assert auc > 0.85

    def test_early_stopping_runs(self) -> None:
        X, Y = self._synthetic(n_samples=300, n_recipes=5, seed=2)
        n = X.shape[0]
        split = int(0.8 * n)
        head = MultiTaskHead(
            config=MultiTaskHeadConfig(
                max_epochs=200, early_stop_patience=3, seed=2, batch_size=32,
            ),
            n_recipes=5,
        )
        head.fit(X[:split], Y[:split], X_val=X[split:], Y_val=Y[split:])
        assert len(head._train_history) <= 200
