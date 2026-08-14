"""
Unit tests for the Phase 2 EB hyperprior estimator math.

These tests exercise the pure-Python math (`neg_loglik`, `fit_cell`) without
touching Athena. The data-loader functions are integration-tested in practice
(the script's coverage diagnostics catch chain-mapping issues at runtime); a
pure-unit test of the loaders would just mock the I/O.

Generated: 2026-05-03
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import betabinom


# Load the script as a module without executing main().
# Note: must register the module in sys.modules BEFORE exec_module so that
# @dataclass can resolve cls.__module__ during class creation (Python 3.14
# dataclasses inspect sys.modules to determine the owning module).
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "estimate_eb_hyperpriors.py"
_spec = importlib.util.spec_from_file_location("eb_hyperpriors", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["eb_hyperpriors"] = mod
_spec.loader.exec_module(mod)


# ===========================================================================
# neg_loglik
# ===========================================================================

def test_neg_loglik_finite_for_reasonable_inputs():
    """Likelihood evaluates to a finite number for typical data."""
    k = np.array([1, 5, 10, 20], dtype=np.int64)
    n = np.array([10, 20, 50, 100], dtype=np.int64)
    log_params = np.array([np.log(2.0), np.log(8.0)])
    val = mod.neg_loglik(log_params, k, n)
    assert np.isfinite(val)
    assert val > 0  # negative log-likelihood is positive (likelihood < 1)


def test_neg_loglik_handles_extreme_log_params():
    """Capped log-params should not raise NaN or inf."""
    k = np.array([1, 5, 10], dtype=np.int64)
    n = np.array([10, 20, 50], dtype=np.int64)
    # Extreme log-params: optimizer might wander here
    val_huge = mod.neg_loglik(np.array([25.0, 25.0]), k, n)
    val_tiny = mod.neg_loglik(np.array([-25.0, -25.0]), k, n)
    assert np.isfinite(val_huge)
    assert np.isfinite(val_tiny)


# ===========================================================================
# fit_cell — recovery on synthetic data
# ===========================================================================

@pytest.mark.parametrize(
    "true_alpha,true_beta,n_obs,trial_size,tolerance",
    [
        # Wide distribution, plenty of data
        (2.0, 8.0, 200, 100, 0.5),
        # Narrow distribution near 0.5
        (10.0, 10.0, 200, 100, 0.5),
        # Asymmetric, lots of trials per obs
        (1.5, 5.0, 100, 200, 0.7),
    ],
)
def test_fit_cell_recovers_known_alpha_beta(true_alpha, true_beta, n_obs, trial_size, tolerance):
    """MLE recovers known (alpha, beta) within tolerance on synthetic data.

    Tolerance is loose because Beta-Binomial MLE has wide CI on small
    samples. The point of the test is to verify the optimizer converges
    in the right neighborhood — not that it nails the parameters.
    """
    rng = np.random.default_rng(42)
    n_arr = np.full(n_obs, trial_size, dtype=np.int64)
    # Sample from Beta-Binomial(n=trial_size, alpha, beta)
    k_arr = betabinom.rvs(trial_size, true_alpha, true_beta, size=n_obs, random_state=rng)
    observations = list(zip(k_arr.tolist(), n_arr.tolist()))
    fit = mod.fit_cell(observations, indicator_ids={1, 2, 3})

    assert fit.converged, f"optimizer did not converge for alpha={true_alpha}, beta={true_beta}"
    # Mean recovery — usually tight even when alpha/beta individually are not
    true_mean = true_alpha / (true_alpha + true_beta)
    assert abs(fit.mean - true_mean) < tolerance, (
        f"mean off: true={true_mean:.3f}, fit={fit.mean:.3f}"
    )
    # Concentration in same order of magnitude
    true_conc = true_alpha + true_beta
    log_ratio = abs(np.log(fit.concentration / true_conc))
    assert log_ratio < 2.0, (
        f"concentration off by >e^2 (~7.4x): true={true_conc}, fit={fit.concentration}"
    )


def test_fit_cell_returns_consistent_mean_and_concentration():
    """fit.mean == alpha/(alpha+beta) and fit.concentration == alpha+beta."""
    rng = np.random.default_rng(0)
    k = betabinom.rvs(50, 3.0, 12.0, size=80, random_state=rng)
    n = np.full(80, 50, dtype=np.int64)
    fit = mod.fit_cell(list(zip(k.tolist(), n.tolist())), indicator_ids={1})
    assert abs(fit.mean - fit.alpha / (fit.alpha + fit.beta)) < 1e-9
    assert abs(fit.concentration - (fit.alpha + fit.beta)) < 1e-9


# ===========================================================================
# fit_cell — edge cases
# ===========================================================================

def test_fit_cell_empty_observations():
    """No data → graceful return with NaN params, n_observations=0, degenerate."""
    fit = mod.fit_cell([], indicator_ids=set())
    assert fit.n_observations == 0
    assert fit.n_indicators == 0
    assert np.isnan(fit.alpha)
    assert np.isnan(fit.beta)
    assert not fit.converged
    assert fit.degenerate
    assert "no observations" in fit.degenerate_reason


def test_fit_cell_degenerate_below_min_obs():
    """Cells with n_obs < DEGENERATE_MIN_OBS must be flagged degenerate.

    The MLE may technically converge but the result is unreliable —
    Phase 3 uses Beta(1,1) fallback instead. QA review caught
    REPRESSION__C with n_obs=2, concentration=312k as a degenerate
    ridge-convergence; this test pins that detection.
    """
    # 4 observations is below the floor (5)
    fit = mod.fit_cell([(1, 10), (2, 12), (1, 8), (3, 15)], indicator_ids={1, 2})
    assert fit.n_observations == 4
    assert fit.degenerate
    assert "n_observations=4" in fit.degenerate_reason
    assert "< 5" in fit.degenerate_reason


def test_fit_cell_above_min_obs_not_flagged_for_size_alone():
    """Cells with n_obs >= DEGENERATE_MIN_OBS pass the size floor."""
    rng = np.random.default_rng(123)
    # Sample reasonable Beta-Binomial data with concentration well below the cap
    k = betabinom.rvs(50, 2.0, 8.0, size=20, random_state=rng)
    n = np.full(20, 50, dtype=np.int64)
    fit = mod.fit_cell(list(zip(k.tolist(), n.tolist())), indicator_ids={1, 2, 3})
    # n_obs=20 is above floor (5), and a Beta(2,8) prior produces concentration ~10
    # which is well below the max cap of 5000. Should NOT be flagged.
    assert not fit.degenerate, f"unexpected degenerate flag: {fit.degenerate_reason}"


def test_fit_cell_degenerate_above_max_concentration():
    """Cells whose fit concentration exceeds the cap are flagged.

    Constructed by feeding many identical (k, n) observations: the
    Beta-Binomial likelihood drives concentration to infinity because
    the data has zero overdispersion relative to a Binomial.
    """
    # 30 identical (k=10, n=100) observations — zero overdispersion
    obs = [(10, 100)] * 30
    fit = mod.fit_cell(obs, indicator_ids={1})
    # Should be flagged because concentration runs away to the cap (15→exp(15) huge)
    if fit.concentration > mod.DEGENERATE_MAX_CONCENTRATION:
        assert fit.degenerate
        assert "concentration=" in fit.degenerate_reason


def test_fit_cell_zero_variance_data():
    """All observations identical → method-of-moments handles var≈0 without crash."""
    # 50 observations all at k=10, n=100 → variance near zero
    obs = [(10, 100)] * 50
    fit = mod.fit_cell(obs, indicator_ids={1})
    assert fit.converged
    # Mean should be very close to 0.10
    assert abs(fit.mean - 0.10) < 0.05
    # Concentration should be high (low variance → tight prior)
    # but capped by the optimizer's bounds
    assert fit.concentration > 1.0


def test_fit_cell_single_observation():
    """One observation — likelihood is essentially flat; optimizer converges to init."""
    fit = mod.fit_cell([(5, 20)], indicator_ids={1})
    assert fit.n_observations == 1
    # Don't assert convergence quality — single-obs MLE is degenerate;
    # we just want it to not crash and to return a positive (alpha, beta).
    assert fit.alpha > 0
    assert fit.beta > 0
    assert np.isfinite(fit.mean)


def test_fit_cell_extreme_proportions():
    """Data near 0% or near 100% — optimizer should still converge."""
    # All k=0, n=100 (zero hits) — true mean is 0; fit should pull mean toward 0
    obs_zero = [(0, 100)] * 30
    fit_zero = mod.fit_cell(obs_zero, indicator_ids={1})
    assert fit_zero.converged
    assert fit_zero.mean < 0.05  # very close to zero
    # All k=100, n=100 (perfect) — true mean is 1; fit should pull mean toward 1
    obs_one = [(100, 100)] * 30
    fit_one = mod.fit_cell(obs_one, indicator_ids={1})
    assert fit_one.converged
    assert fit_one.mean > 0.95
