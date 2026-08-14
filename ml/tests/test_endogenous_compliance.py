"""Tests for Decisions D30 & D33 Endogenous-Only Catalog Compliance and Backtest Harness."""
from __future__ import annotations

import numpy as np

from ml.backtesting import run_rolling_backtest
from ml.registry import (
    DEACTIVATED_EXOGENOUS_MODELS,
    FLAGSHIP_ENDOGENOUS_MODELS,
    get_flagship_models,
    is_recipe_endogenous,
)
from qgi_ml.trajectory_engine import get_active_trend_catalog


def test_endogenous_catalog_compliance() -> None:
    """Verify Decisions D30 and D33: No exogenous shock models in active catalog."""
    catalog = get_active_trend_catalog()
    forbidden_models = {"natural_disaster", "epidemic_and_pandemic"}

    assert len(catalog) <= 69, f"Active trend catalog exceeds 69 limit: {len(catalog)}"
    assert len(catalog) > 0, "Active trend catalog must not be empty"
    assert forbidden_models.isdisjoint(set(catalog.keys())), (
        f"Forbidden exogenous models found in active catalog: {forbidden_models.intersection(catalog.keys())}"
    )


def test_flagship_endogenous_registry_has_12_models() -> None:
    """Verify Plan 2 / D30: 12 flagship endogenous models are registered and active."""
    models = get_flagship_models()
    assert len(models) == 12
    for code, spec in models.items():
        assert spec.is_active is True
        assert spec.is_endogenous is True
        assert is_recipe_endogenous(spec.recipe_id) is True

    for exog_id, spec in DEACTIVATED_EXOGENOUS_MODELS.items():
        assert spec.is_active is False
        assert spec.is_endogenous is False
        assert is_recipe_endogenous(exog_id) is False


def test_rolling_backtest_outperforms_naive_persistence() -> None:
    """Verify out-of-sample rolling backtest harness against naive persistence baseline."""
    rng = np.random.default_rng(42)
    y_true = np.array([0, 0, 1, 0, 1, 1, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0], dtype=float)
    model_probs = np.clip(0.75 * y_true + 0.12 + rng.normal(0.0, 0.03, size=y_true.size), 0.05, 0.95)
    report = run_rolling_backtest("civil_war_and_insurgency", y_true, model_probs)
    assert report.n_samples == y_true.size
    assert report.outperforms_baseline is True
