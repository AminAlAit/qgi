"""
Unit tests for Phase 3 weight matrix bake (bake_weight_matrix.py).

Tests cover the math (compute_weight) and the prior-lookup decision tree
(lookup_cell_prior) without touching Athena or the EB priors file. The
sibling-script import path (estimate_eb_hyperpriors.py) is exercised at
import time — if that fails, the test collection fails loudly.

Generated: 2026-05-03
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


# Load the script as a module without executing main().
# Note: must register in sys.modules BEFORE exec_module so that any
# @dataclass etc. inside the module can resolve cls.__module__ during
# class creation (Python 3.14 hardening).
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "bake_weight_matrix.py"
_spec = importlib.util.spec_from_file_location("bake_weight_matrix", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["bake_weight_matrix"] = mod
_spec.loader.exec_module(mod)


# ===========================================================================
# compute_weight — math correctness
# ===========================================================================

def test_compute_weight_uniform_prior_recovers_smoothed_proportion():
    """Beta(1, 1) prior + (k=10, n=100) → (10+1)/(100+2) = 0.108..."""
    w = mod.compute_weight(k_d=10, n_d=100, alpha=1.0, beta=1.0)
    assert abs(w - 11.0 / 102.0) < 1e-12


def test_compute_weight_strong_prior_pulls_toward_prior_mean():
    """Beta(50, 50) prior + (k=0, n=10) → posterior mean pulled toward 0.5."""
    # Without prior, MLE is 0/10 = 0.0
    # With Beta(50, 50): (0+50)/(10+100) = 50/110 ≈ 0.4545
    w = mod.compute_weight(k_d=0, n_d=10, alpha=50.0, beta=50.0)
    assert abs(w - 50.0 / 110.0) < 1e-9
    assert 0.40 < w < 0.50, "strong prior should pull toward 0.5"


def test_compute_weight_zero_observations_returns_prior_mean():
    """k=0, n=0 → posterior mean equals prior mean = alpha/(alpha+beta)."""
    w = mod.compute_weight(k_d=0, n_d=0, alpha=3.0, beta=7.0)
    assert abs(w - 3.0 / 10.0) < 1e-12


def test_compute_weight_in_unit_interval_for_random_inputs():
    """Sanity: weight always in [0, 1] for any valid (k, n, a, b)."""
    rng = np.random.default_rng(0)
    for _ in range(50):
        n_d = int(rng.integers(0, 1000))
        k_d = int(rng.integers(0, n_d + 1))
        alpha = float(rng.uniform(0.5, 50.0))
        beta = float(rng.uniform(0.5, 50.0))
        w = mod.compute_weight(k_d, n_d, alpha, beta)
        assert 0.0 <= w <= 1.0, f"weight out of range: w={w} for k={k_d}, n={n_d}, a={alpha}, b={beta}"


def test_compute_weight_rejects_invalid_k_n():
    """k > n or negative values → ValueError."""
    with pytest.raises(ValueError):
        mod.compute_weight(k_d=15, n_d=10, alpha=1.0, beta=1.0)
    with pytest.raises(ValueError):
        mod.compute_weight(k_d=-1, n_d=10, alpha=1.0, beta=1.0)
    with pytest.raises(ValueError):
        mod.compute_weight(k_d=5, n_d=-1, alpha=1.0, beta=1.0)


# ===========================================================================
# lookup_cell_prior — decision tree
# ===========================================================================

def _eb_data_with_cells(cells: dict, sectors_not_fit: list = None) -> dict:
    """Build a minimal eb-hyperpriors-style dict for tests."""
    return {
        "cells": cells,
        "sectors_not_fit": sectors_not_fit or [],
    }


def test_lookup_cell_prior_well_fit_cell_returns_cell_alpha_beta():
    """Healthy cell (degenerate=False) → use cell.alpha, cell.beta directly."""
    eb = _eb_data_with_cells({
        "GOV_INST__A": {
            "alpha": 27.1, "beta": 144.9,
            "degenerate": False,
        },
    })
    a, b, used_fb, reason = mod.lookup_cell_prior(eb, "GOV_INST", "A")
    assert (a, b) == (27.1, 144.9)
    assert not used_fb
    assert reason == ""


def test_lookup_cell_prior_degenerate_cell_uses_fallback():
    """Degenerate cell → Beta(1, 1) fallback regardless of fitted alpha/beta.

    Critical correctness requirement: the fitted values are kept for
    diagnostics but MUST NOT be used to compute weights. This test pins
    the regression QA review caught on Phase 2 (REPRESSION__C with
    n=2, conc=312k).
    """
    eb = _eb_data_with_cells({
        "REPRESSION__C": {
            "alpha": 34951.6, "beta": 277784.7,  # absurd values
            "degenerate": True,
            "degenerate_reason": "n_observations=2 < 5 floor",
            "fallback_alpha": 1.0, "fallback_beta": 1.0,
        },
    })
    a, b, used_fb, reason = mod.lookup_cell_prior(eb, "REPRESSION", "C")
    assert (a, b) == (1.0, 1.0), "degenerate cell must use fallback Beta(1,1), NOT the fitted alpha/beta"
    assert used_fb
    assert reason == "cell_degenerate"


def test_lookup_cell_prior_sector_not_fit_uses_fallback():
    """Sector listed in sectors_not_fit → Beta(1, 1) fallback."""
    eb = _eb_data_with_cells(
        cells={"GOV_INST__A": {"alpha": 27.0, "beta": 144.0, "degenerate": False}},
        sectors_not_fit=["CONFLICT", "DISPLACE"],
    )
    a, b, used_fb, reason = mod.lookup_cell_prior(eb, "CONFLICT", "B")
    assert (a, b) == (1.0, 1.0)
    assert used_fb
    assert reason == "sector_not_fit"


def test_lookup_cell_prior_missing_cell_uses_fallback():
    """Cell key absent (sector fit but specific L1 has no data) → fallback."""
    eb = _eb_data_with_cells({"GOV_INST__A": {"alpha": 27.0, "beta": 144.0, "degenerate": False}})
    a, b, used_fb, reason = mod.lookup_cell_prior(eb, "GOV_INST", "Z")
    assert (a, b) == (1.0, 1.0)
    assert used_fb
    assert reason == "cell_missing"


def test_lookup_cell_prior_degenerate_with_missing_fallback_fields_still_safe():
    """Degenerate cell missing fallback_alpha/beta fields → Beta(1,1).

    Defensive check: even if the EB script's output schema drops the
    explicit fallback fields in a future version, Phase 3 still
    produces a sane Beta(1,1) prior rather than crashing.
    """
    eb = _eb_data_with_cells({
        "REPRESSION__C": {
            "alpha": 999.0, "beta": 777.0,
            "degenerate": True,
            # fallback_alpha and fallback_beta intentionally absent
        },
    })
    a, b, used_fb, reason = mod.lookup_cell_prior(eb, "REPRESSION", "C")
    assert (a, b) == (1.0, 1.0)
    assert used_fb


def test_lookup_cell_prior_degenerate_ignores_cell_fallback_alpha_beta():
    """Even if a degenerate cell carries fallback_alpha/beta != 1.0,
    Phase 3 MUST always use FALLBACK_* constants (decoupled from
    Phase 2's emitted values).

    QA review 2026-05-03 round 2 explicitly required this
    decoupling: Phase 3 must not depend on Phase 2's choice of
    fallback values. If Phase 2 ever emits, e.g., fallback_alpha=0.5,
    Phase 3 must still return 1.0 because that's the no-information
    Beta(1, 1) default Phase 3 owns.
    """
    eb = _eb_data_with_cells({
        "REPRESSION__C": {
            "alpha": 999.0, "beta": 777.0,
            "degenerate": True,
            # Adversarial: cell carries non-1.0 fallback values that would
            # corrupt shrinkage if Phase 3 trusted them.
            "fallback_alpha": 0.5,
            "fallback_beta": 2.0,
        },
    })
    a, b, used_fb, reason = mod.lookup_cell_prior(eb, "REPRESSION", "C")
    assert (a, b) == (1.0, 1.0), (
        "Phase 3 must ignore cell.fallback_alpha/beta and always use "
        "FALLBACK_ALPHA/FALLBACK_BETA constants for degenerate cells"
    )
    assert used_fb
    assert reason == "cell_degenerate"


def test_lookup_cell_prior_sectors_not_fit_takes_precedence_over_cells():
    """If a sector is in `sectors_not_fit`, return fallback even if a
    cell for that sector exists in `cells` (precedence ordering).

    Edge case: a sector might be partially populated (one L1 has data,
    others don't). The EB JSON's `sectors_not_fit` is meant for
    sectors where pooling is unreliable wholesale. Phase 3's contract:
    the sectors_not_fit check fires FIRST.
    """
    eb = _eb_data_with_cells(
        cells={
            # A populated cell for a sector that's nonetheless flagged
            # as not-fit overall (hypothetical edge case for safety)
            "GOV_INST__A": {"alpha": 27.0, "beta": 144.0, "degenerate": False},
        },
        sectors_not_fit=["GOV_INST"],
    )
    a, b, used_fb, reason = mod.lookup_cell_prior(eb, "GOV_INST", "A")
    assert (a, b) == (1.0, 1.0)
    assert used_fb
    assert reason == "sector_not_fit", (
        "sectors_not_fit must take precedence over cell-level lookup"
    )


# ===========================================================================
# Integration smoke — module-level constants
# ===========================================================================

def test_fallback_alpha_beta_constants_are_uniform_prior():
    """FALLBACK_(ALPHA|BETA) must be 1.0 (uniform Beta) per fallback_policy."""
    assert mod.FALLBACK_ALPHA == 1.0
    assert mod.FALLBACK_BETA == 1.0


def test_module_imports_eb_hyperpriors_sibling():
    """The sibling-script import (estimate_eb_hyperpriors) must succeed.

    If the import path breaks (e.g., script renamed), test collection
    fails BEFORE any other test runs — fast-fail.
    """
    assert hasattr(mod, "eb")
    # Spot-check a few expected attributes from the sibling
    assert hasattr(mod.eb, "load_sectors")
    assert hasattr(mod.eb, "load_event_l1_map")
    assert hasattr(mod.eb, "parse_catalog_api_to_catalog_code")
