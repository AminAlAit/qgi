"""B5 test (QA 2026-05-17, Priya adjudication 2026-05-17 Option C).

Validates that ``posterior_cov_diag`` in the per-indicator signature is the
**Bayesian back-projected LKJ posterior-mean covariance** (the spec-binding
§3.5.1 Mahalanobis denominator), NOT the prior frequentist empirical sample
variance ``np.var(block_trajs, ddof=1)``.

The full end-to-end fit (synthetic recipe → NUTS → per-indicator signature)
is exercised in ``tests/test_shape_prototype_fit.py::test_fit_recipe_fpca_converges_on_synthetic_data``
which validates the production code path emits the new B5 fields.

These tests target the back-projection math directly via
``_fit_bayesian_posterior`` and the per-indicator block construction, so
they:
  - Don't depend on LOIO coverage passing at small N_r (which is fragile
    under reduced NUTS sampling at test scale).
  - Validate the priors-regularize-at-small-N_r vs converges-at-large-N_r
    invariants directly on the recovered ``Sigma_r_posterior_mean``.

Per Priya's adjudication doc (lines 148-152):
  - Synthetic recipe with N_r = 10 (Phase 1 production floor): posterior
    cov differs from empirical sample variance by >= 5% relative error in
    median (validates that the LKJ + Half-Cauchy priors are actually
    regularizing at the sparse regime).
  - Synthetic recipe with N_r = 100 (data-dominant regime): the gap
    closes to < 2% relative error in median (validates Bayesian →
    frequentist convergence; test-time slack is 10% under reduced
    NUTS draws).

Marked SLOW because NUTS sampling dominates wall time (~5-10 min total).
"""
from __future__ import annotations

import os

# Windows compatibility: disable pytensor C compilation BEFORE any pytensor /
# pymc imports.
os.environ.setdefault("PYTENSOR_FLAGS", "cxx=")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for p in (SRC_ROOT, SCRIPTS_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _synthetic_fpca_scores(N_r: int, M_r: int, seed: int) -> np.ndarray:
    """Synthetic FPCA scores drawn from a known multivariate normal.

    Generates N_r samples from N(mu_true, Sigma_true) where Sigma_true has
    moderate cross-component correlation. The LKJ + Half-Cauchy posterior
    over (mu, Sigma) should recover Sigma_true approximately, with prior
    regularization shrinking the estimate at small N_r and converging at
    large N_r.
    """
    rng = np.random.default_rng(seed)
    mu_true = np.array([0.3, -0.2, 0.1, 0.0][:M_r])
    # Construct Sigma_true with diagonal variance ≈ 1.0 and off-diagonal
    # correlation ≈ 0.3.
    corr = np.full((M_r, M_r), 0.3)
    np.fill_diagonal(corr, 1.0)
    L = np.linalg.cholesky(corr)
    return mu_true[np.newaxis, :] + rng.standard_normal((N_r, M_r)) @ L.T


def _bayesian_and_empirical_traj_cov_diag(
    N_r: int,
    *,
    seed: int,
    T_r: int = 5,
    M_r: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Run NUTS on synthetic FPCA scores and return (bayesian_traj_cov_diag,
    empirical_traj_cov_diag) using the SAME back-projection paths the
    fitter uses for the Mahalanobis denominator.

    Both are computed in trajectory time-step space:
      - Bayesian:  diag(Phi @ V_block @ Sigma_r_posterior_mean @ V_block^T @ Phi^T)
      - Empirical: empirical sample variance of (Phi @ block_betas.T) across
                   the synthetic instances.
    """
    from fit_shape_prototype import _fit_bayesian_posterior
    from shape_prototype_fit_utils import (
        build_cubic_bspline_basis,
        fit_fpca,
    )

    # Build basis + R for one indicator (simplest comparison surface).
    Phi, R_block = build_cubic_bspline_basis(T_r)
    K_basis = Phi.shape[1]

    # Synthesize per-instance basis coefficients from a low-rank latent.
    rng = np.random.default_rng(seed)
    # M_r-dim latent that we'll use for FPCA recovery.
    scores_true = _synthetic_fpca_scores(N_r, M_r, seed)
    # Random K_basis x M_r loading; QR for orthonormal columns.
    A = rng.standard_normal((K_basis, M_r))
    Q, _ = np.linalg.qr(A)  # Q: K_basis x M_r, orthonormal columns
    # Per-instance basis coefficients = scores @ Q^T + small noise.
    beta_matrix = scores_true @ Q.T + 0.05 * rng.standard_normal((N_r, K_basis))

    fpca = fit_fpca(beta_matrix, R_block, M_max=M_r)
    if fpca.selected_M_r is None or fpca.selected_M_r < M_r:
        pytest.skip(
            f"Synthetic FPCA failed to select M_r={M_r} at N_r={N_r} "
            f"(got {fpca.selected_M_r}); not a B5 test scenario."
        )

    V_r = fpca.V[:, : fpca.selected_M_r]
    diagnostics, posterior_mu, Sigma_r_posterior_mean = _fit_bayesian_posterior(
        scores=fpca.scores[:, : fpca.selected_M_r],
        target_accept=0.95,
        n_chains=2,
        n_tune=300,
        n_draws=300,
        random_seed=seed,
    )
    # Bayesian back-projected diagonal in trajectory space.
    Sigma_beta = V_r @ Sigma_r_posterior_mean @ V_r.T  # (K_basis, K_basis)
    Sigma_traj = Phi @ Sigma_beta @ Phi.T  # (T_r, T_r)
    bayesian_diag = np.maximum(np.diag(Sigma_traj), 0.0)

    # Empirical sample variance across trajectories.
    block_trajs = (Phi @ beta_matrix.T).T  # (N_r, T_r)
    empirical_diag = np.var(block_trajs, axis=0, ddof=1)

    return bayesian_diag, empirical_diag


@pytest.mark.slow
def test_posterior_cov_diag_diverges_from_empirical_at_small_N_r() -> None:
    """At N_r = 10, the LKJ posterior cov diff from empirical sample variance
    by >= 5% relative error in MEDIAN (validates priors are regularizing)."""
    bayesian_diag, empirical_diag = _bayesian_and_empirical_traj_cov_diag(
        N_r=10, seed=20260517
    )
    rel_errors = np.abs(bayesian_diag - empirical_diag) / np.maximum(
        np.abs(empirical_diag), 1e-9
    )
    median_rel_error = float(np.median(rel_errors))
    assert median_rel_error >= 0.05, (
        f"At N_r=10 the Bayesian posterior cov diag differs from the empirical "
        f"sample variance by median relative error {median_rel_error:.4f} "
        f"(< 5% threshold). This suggests the LKJ + Half-Cauchy priors are "
        f"NOT regularizing — either the back-projection is broken or the "
        f"synthetic data is too well-conditioned. Per Priya B5 adjudication: "
        f"a 5% gap at the production floor is the minimum signal that the "
        f"Bayesian denominator is doing methodologically meaningful work."
    )


@pytest.mark.slow
def test_posterior_cov_diag_converges_to_empirical_at_large_N_r() -> None:
    """At N_r = 100, the LKJ posterior cov gap to empirical sample variance
    closes (production target < 2%; test slack 10% under reduced NUTS draws)."""
    bayesian_diag, empirical_diag = _bayesian_and_empirical_traj_cov_diag(
        N_r=100, seed=20260517
    )
    rel_errors = np.abs(bayesian_diag - empirical_diag) / np.maximum(
        np.abs(empirical_diag), 1e-9
    )
    median_rel_error = float(np.median(rel_errors))
    # Production target per Priya B5 adjudication: < 2%. We allow 10%
    # slack at test scale because reduced NUTS sampling (n_draws=300)
    # limits posterior precision; the gap-closing-direction is the test
    # invariant, not the exact production threshold.
    assert median_rel_error < 0.10, (
        f"At N_r=100 the Bayesian posterior cov diag still differs from the "
        f"empirical sample variance by median relative error "
        f"{median_rel_error:.4f} (> 10% test-scale slack). This suggests "
        f"the Bayesian estimator is NOT converging to the frequentist one "
        f"in the data-dominant regime. Production target: < 2%."
    )


@pytest.mark.slow
def test_posterior_cov_diag_emitted_in_signature_has_provenance_tag() -> None:
    """The per-indicator signature emitted by the fitter carries the B5
    provenance tag ``cov_diag_source = posterior_mean_lkj_back_projected``.

    This is the Lloyd's-audit-surface invariant: a reviewer can read the
    lock JSON and immediately verify the variance object is Bayesian
    without reading the fitter source.
    """
    import pandas as pd

    from fit_shape_prototype import fit_recipe_fpca

    # Minimal synthetic panel (15 instances, 2 indicators, T_r=5).
    rng = np.random.default_rng(99)
    T_r = 5
    event_year = 2020
    rows = []
    positives = []
    for i in range(15):
        c = f"C{i:03d}"
        positives.append({"country_id": c, "event_year": event_year})
        baseline_mean = 100.0
        baseline_sd = 5.0
        d_off = baseline_sd * np.sqrt(19 / 20)
        for k in range(20):
            y = event_year - T_r - 20 + k
            v = baseline_mean + (d_off if k % 2 == 0 else -d_off)
            for iid in ("IND_A", "IND_B"):
                rows.append({"country_id": c, "year": y, "indicator_id": iid, "value": v})
        for j, y in enumerate(range(event_year - T_r, event_year)):
            z_a = j / (T_r - 1) + rng.normal(scale=0.1)
            z_b = (T_r - 1 - j) / (T_r - 1) + rng.normal(scale=0.1)
            rows.append(
                {"country_id": c, "year": y, "indicator_id": "IND_A",
                 "value": baseline_mean + baseline_sd * z_a}
            )
            rows.append(
                {"country_id": c, "year": y, "indicator_id": "IND_B",
                 "value": baseline_mean + baseline_sd * z_b}
            )
    panel = pd.DataFrame(rows)
    positives_df = pd.DataFrame(positives)
    prototype, _ = fit_recipe_fpca(
        panel,
        positives_df,
        indicator_ids=["IND_A", "IND_B"],
        T_r=T_r,
        target_accept=0.95,
        n_chains=2,
        n_tune=200,
        n_draws=200,
        random_seed=7,
    )
    if prototype.fallback_required:
        pytest.skip(
            f"Synthetic seed produced fallback (reason: "
            f"{prototype.fallback_reason!r}); B5 provenance tag is only "
            f"emitted on the primary FPCA path."
        )
    for iid in ("IND_A", "IND_B"):
        sig = prototype.per_indicator_signature[iid]
        assert sig.get("cov_diag_source") == "posterior_mean_lkj_back_projected", (
            f"per-indicator signature for {iid!r} is missing the B5 "
            f"provenance tag; got cov_diag_source="
            f"{sig.get('cov_diag_source')!r}."
        )
