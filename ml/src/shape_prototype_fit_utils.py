"""Helper functions for the shape-prototype fitter (Stage 6 §3 binding math).

Per `docs/specs/internal/ops/ml-track/stage-6-shape-feature-prereg.md` §3
(Priya, the math primitive). This module holds pure functions —
basis construction, indicator-level normalization, FPCA in the Sobolev
metric, M_r selection, and diagnostic gates — that are independently
unit-testable. The end-to-end fitter is in `scripts/fit_shape_prototype.py`
and composes these primitives.

All functions are deterministic (no random state). The only stochastic
piece of the pipeline is the PyMC NUTS sampler inside the fitter, which is
seeded explicitly per recipe at fit time.

Authority lineage:
    Methodology Charter (2026-05-17)
      -> DECISION (2026-05-17, R3 + R4 binding)
        -> Stage 6 §3 (Priya, Bayesian FPCA + hierarchical Bayes)
          -> this module.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.interpolate import BSpline
from scipy.linalg import eigh

logger = logging.getLogger(__name__)


# Per §3.1.2 binding: cubic B-spline with K_basis = 8 interior knots.
K_BASIS_INTERIOR_KNOTS: Final[int] = 8
SPLINE_DEGREE: Final[int] = 3  # cubic

# Per §3.1.2 binding: M_r in {3, 4} with floor 3 and ceiling 4.
M_R_FLOOR: Final[int] = 3
M_R_CEILING: Final[int] = 4
M_R_VARIANCE_TARGET: Final[float] = 0.80

# Per §3.1.5: scree elbow operationalization — ratio of (M_r+1)-th to M_r-th
# eigenvalue <= 0.4 signals an elbow.
SCREE_ELBOW_RATIO: Final[float] = 0.4

# Per §3.1.3 sampler diagnostic gates.
RHAT_GATE: Final[float] = 1.01
ESS_GATE: Final[int] = 400
TARGET_ACCEPT_DEFAULT: Final[float] = 0.95
TARGET_ACCEPT_REFIT: Final[float] = 0.99
MAX_TREEDEPTH: Final[int] = 12

# F-H-4-A4 (docs-specs 2026-05-20, 8-seat ratified 8/8 APPROVE with Roshani + Marcus
# operational riders). §3.1.3 divergence gate relaxed from strict 0 to:
#   ≤ DIVERGENCE_ABS_GATE absolute divergent transitions AND
#   ≤ DIVERGENCE_RATE_GATE divergence rate over post-warmup draws.
# Justification (first-principles, F-Shape-1 compliant — NOT walk-data informed):
# Betancourt 2017 §4.2 + Stan ref manual §15.1.2 + PyMC docs all converge on
# "<1% divergence rate with passing R-hat/ESS = posterior trustworthy" as the
# community standard. Strict 0 was more conservative than this consensus and
# unattainable under the (α, ℓ) ridge geometry inherent to GP regression with
# SE kernel (Rasmussen & Williams 2006 §5.5). Single-divergence refit logic
# at target_accept=0.99 unchanged; relaxed gate evaluated only on refit result.
DIVERGENCE_ABS_GATE: Final[int] = 5
DIVERGENCE_RATE_GATE: Final[float] = 0.005  # 0.5% of post-warmup draws

# Per §3.5.4 LOIO calibration gate.
LOIO_COVERAGE_GATE: Final[float] = 0.70
LOIO_NOMINAL_LEVEL: Final[float] = 0.80


# ---- Basis construction (§3.1.2) --------------------------------------------


def build_cubic_bspline_basis(
    T_r: int,
    *,
    n_interior_knots: int = K_BASIS_INTERIOR_KNOTS,
) -> tuple[np.ndarray, np.ndarray]:
    """Construct a cubic B-spline basis matrix and Sobolev penalty matrix.

    Per §3.1.2 binding (Ramsay & Silverman ch. 8): K_basis = 8 interior knots
    on [-T_r, 0]. This implementation uses **equispaced (uniform-fraction)
    knot placement**, which equals data-quantile placement only on the
    integer grid ``t in {-T_r, ..., -1}`` (the production trajectory grid;
    on that grid uniform-fraction == empirical-quantile by construction).
    If irregular sampling is ever introduced (e.g. monthly or event-time
    grids), this implementation MUST be revisited and the quantile route
    re-derived. An assertion at function entry pins the integer-grid
    invariant.

    The Sobolev penalty matrix R is computed as the **analytic integral**
    per Priya's adjudication of QA B2 (2026-05-17):
    ``R_{ij} = ∫ φ_i''(t) φ_j''(t) dt`` over [-T_r, 0] via
    ``scipy.interpolate.BSpline.derivative(2)`` plus 8-point Gauss-Legendre
    quadrature on each knot subinterval. This matches the canonical
    Ramsay & Silverman §5.5 definition by direct citation; the prior
    finite-difference proxy diverged from the analytic integral at the
    production scale (T_r ∈ [4, 8]).

    Args:
        T_r: Canonical length (number of integer year offsets in the
            trajectory window, t in {-T_r, ..., -1}). MUST be an integer >= 4.
        n_interior_knots: Per spec, 8. Exposed for testability but spec-binding.

    Returns:
        (Phi, R) where:
          Phi: (T_r, n_interior_knots) evaluated basis matrix. Row i is
            phi_1..phi_K evaluated at t = -T_r + i.
          R: (n_interior_knots, n_interior_knots) Sobolev penalty matrix
            (analytic integral of second-derivative outer products via
            Gauss-Legendre quadrature); the metric used in FPCA's Sobolev
            inner product.

    Raises:
        ValueError: if T_r < 4 (basis cannot interpolate fewer than 4 points
            with a cubic spline + 8 interior knots while remaining stable).
        AssertionError: if T_r is not an integer (uniform-fraction knots
            equal quantile knots only on the integer grid; non-integer T_r
            invalidates the binding equivalence and must trigger a spec
            revisit).
    """
    # Per B1 (QA review 2026-05-17): pin the integer-grid invariant.
    # Uniform-fraction knot placement equals empirical-quantile placement
    # iff the sampling grid is integer-spaced; production trajectories use
    # ``t in {-T_r, ..., -1}`` with unit step. Any deviation invalidates
    # the docstring's binding equivalence.
    assert isinstance(T_r, (int, np.integer)) and not isinstance(T_r, bool), (
        f"T_r must be an integer (uniform-fraction == quantile knots only on "
        f"the integer grid); got type {type(T_r).__name__}={T_r!r}."
    )
    if T_r < 4:
        raise ValueError(
            f"T_r={T_r} is too short for cubic spline basis; minimum is 4. "
            f"Per Stage 6 §3.2 this should fall to the §3.1.4 hierarchical "
            f"Bayes + GP fallback path."
        )
    if n_interior_knots < 4:
        raise ValueError(
            f"n_interior_knots={n_interior_knots} below spec minimum 4"
        )

    # Evaluation grid: integer year offsets in [-T_r, -1].
    t_grid = np.arange(-T_r, 0, dtype=float)  # length T_r

    # Equispaced (uniform-fraction) interior knots on (-T_r, 0). Use linspace
    # on fractions 1/(K+1), ..., K/(K+1) for evenly-spaced positions,
    # deterministic across calls. On the integer grid t in {-T_r, ..., -1}
    # this coincides with empirical-quantile knot placement; see docstring
    # B1 note on irregular-grid divergence.
    quantile_positions = np.linspace(
        1.0 / (n_interior_knots + 1),
        n_interior_knots / (n_interior_knots + 1),
        n_interior_knots,
    )
    interior_knots = -T_r + quantile_positions * T_r  # in (-T_r, 0)

    # Augmented knot vector for cubic B-spline: replicate boundary knots
    # SPLINE_DEGREE+1 times to clamp endpoints.
    boundary_lo = np.full(SPLINE_DEGREE + 1, -T_r, dtype=float)
    boundary_hi = np.full(SPLINE_DEGREE + 1, -1e-9, dtype=float)
    # Use -1e-9 (not 0.0) so that the right-endpoint sample at t=-1 is
    # strictly inside the support [-T_r, 0); BSpline is right-open by default.
    full_knots = np.concatenate([boundary_lo, interior_knots, boundary_hi])

    # The cubic B-spline has n_interior_knots basis functions when the knot
    # vector has length n_interior_knots + 2*(SPLINE_DEGREE+1). With clamped
    # boundaries plus interior knots, the count of B-spline basis functions is
    # len(full_knots) - SPLINE_DEGREE - 1.
    n_basis = len(full_knots) - SPLINE_DEGREE - 1

    # Build identity-coefficient basis functions and evaluate at t_grid.
    Phi = np.zeros((T_r, n_basis), dtype=float)
    for j in range(n_basis):
        coeffs = np.zeros(n_basis, dtype=float)
        coeffs[j] = 1.0
        spline = BSpline(full_knots, coeffs, SPLINE_DEGREE, extrapolate=False)
        Phi[:, j] = spline(t_grid)

    # Replace NaN (out-of-support) with 0 (occurs only at the open right
    # boundary). Then truncate Phi to exactly n_interior_knots basis columns
    # via the central (highest-mass) columns to honor the spec's K_basis = 8.
    Phi = np.nan_to_num(Phi, nan=0.0)

    # Reduce to the central n_interior_knots columns. The clamped cubic
    # B-spline with K interior knots produces K + SPLINE_DEGREE + 1 basis
    # functions; we keep the "interior" central K of those by dropping the
    # outermost (SPLINE_DEGREE+1)//2 on each side. This gives a stable
    # K-column basis that integrates well on the bounded support.
    drop_per_side = (n_basis - n_interior_knots) // 2
    if n_basis > n_interior_knots:
        Phi = Phi[:, drop_per_side : drop_per_side + n_interior_knots]

    # Renormalize each basis column to unit L2-norm on the discrete grid,
    # for numerical conditioning. This is a standard FPCA preprocessing
    # step and does not change the span of the basis.
    col_norms = np.linalg.norm(Phi, axis=0)
    col_norms = np.where(col_norms < 1e-12, 1.0, col_norms)
    Phi = Phi / col_norms[np.newaxis, :]

    # Penalty matrix R: analytic integral R_{ij} = ∫ φ_i''(t) φ_j''(t) dt
    # over [-T_r, 0] per §3.1.2 binding (Ramsay & Silverman §5.5, ch. 8).
    # Implemented via scipy.interpolate.BSpline.derivative(2) plus 8-point
    # Gauss-Legendre quadrature on each knot subinterval. This is exact for
    # polynomials up to degree 15; cubic-spline second derivatives are
    # piecewise linear, so 2-point would suffice — 8-point is for robustness
    # at corner cases. Per Priya's B2 adjudication (2026-05-17): this
    # replaces the prior finite-difference proxy that diverged from the
    # cited R&S canonical definition at production scale.
    R = np.zeros((Phi.shape[1], Phi.shape[1]), dtype=float)
    # Build the n_basis_full second-derivative B-splines once.
    second_derivs: list[BSpline] = []
    n_basis_full = len(full_knots) - SPLINE_DEGREE - 1
    for j in range(n_basis_full):
        coeffs = np.zeros(n_basis_full, dtype=float)
        coeffs[j] = 1.0
        spl = BSpline(full_knots, coeffs, SPLINE_DEGREE, extrapolate=False)
        second_derivs.append(spl.derivative(2))
    # Apply same central-trim as Phi for index consistency.
    if n_basis_full > n_interior_knots:
        second_derivs = second_derivs[drop_per_side : drop_per_side + n_interior_knots]
    # Account for the L2-renormalization applied to Phi: the basis functions
    # φ_j used in the analytic integral are the SAME functions whose discrete
    # evaluations were L2-normalized in Phi. To keep R consistent with that
    # scaling, divide each second-derivative spline output by the same col_norm.
    inv_col_norms = 1.0 / col_norms  # broadcast factor per basis column

    # Gauss-Legendre 8-point quadrature per knot subinterval.
    gl_nodes, gl_weights = leggauss(8)
    # Unique sorted break points inside [-T_r, 0).
    break_points = np.unique(full_knots)
    break_points = break_points[(break_points >= -T_r) & (break_points < 0)]
    if break_points.size == 0 or break_points[0] > -T_r:
        break_points = np.concatenate([[-T_r], break_points])
    if break_points[-1] < -1e-9:
        break_points = np.concatenate([break_points, [-1e-9]])

    for k_seg in range(len(break_points) - 1):
        a, b = float(break_points[k_seg]), float(break_points[k_seg + 1])
        if b - a <= 0.0:
            continue
        half = 0.5 * (b - a)
        mid = 0.5 * (b + a)
        pts = mid + half * gl_nodes  # mapped quadrature nodes
        wts = half * gl_weights
        # Evaluate all kept second-derivative basis functions at pts and
        # apply the same L2 renormalization Phi used.
        D2_vals = np.zeros((len(pts), len(second_derivs)), dtype=float)
        for j, spl_dd in enumerate(second_derivs):
            D2_vals[:, j] = np.nan_to_num(spl_dd(pts), nan=0.0)
        D2_vals = D2_vals * inv_col_norms[np.newaxis, :]
        # Accumulate the outer-product integral.
        R += (D2_vals * wts[:, np.newaxis]).T @ D2_vals

    # Symmetrize + add tiny ridge for positive-definiteness in the eigendecomp
    # used by FPCA.
    R = 0.5 * (R + R.T) + 1e-8 * np.eye(R.shape[0])

    return Phi, R


def project_to_basis_coefficients(
    trajectory: np.ndarray,
    Phi: np.ndarray,
) -> np.ndarray:
    """Least-squares projection of a trajectory onto the spline basis.

    Args:
        trajectory: (T_r,) array of evaluated function values (must match
            Phi's row count).
        Phi: (T_r, K_basis) evaluated basis matrix from build_cubic_bspline_basis.

    Returns:
        beta: (K_basis,) basis-coefficient vector.

    Raises:
        ValueError: if trajectory and Phi rows disagree.
    """
    trajectory = np.asarray(trajectory, dtype=float)
    if trajectory.shape[0] != Phi.shape[0]:
        raise ValueError(
            f"trajectory length {trajectory.shape[0]} does not match basis "
            f"rows {Phi.shape[0]}"
        )
    # OLS in Phi-coefficient space. Phi is full column rank by construction.
    beta, _, _, _ = np.linalg.lstsq(Phi, trajectory, rcond=None)
    return beta


# ---- Indicator-level normalization (§3.2.2) ---------------------------------


@dataclass(frozen=True)
class NormalizationResult:
    """Result of per-country indicator-level z-scoring.

    Carries the normalized trajectory plus the baseline statistics for
    audit / provenance.
    """

    y_normalized: np.ndarray  # (T_r,) normalized trajectory
    baseline_mean: float
    baseline_sd: float
    baseline_n_years: int  # actual count of pre-window years available
    floored: bool  # True if sigma_floor was applied (near-constant series)


def per_country_z_score(
    raw_trajectory: np.ndarray,
    pre_window_baseline: np.ndarray,
    *,
    median_sd_for_floor: float | None = None,
) -> NormalizationResult:
    """Apply per-country indicator-level normalization per §3.2.2.

    Computes 20-year (or shorter, if pre_window_baseline is shorter) pre-event
    mean and SD; z-scores the alignment window against those statistics; applies
    the sigma_min floor when the country's pre-window SD is degenerate.

    Args:
        raw_trajectory: (T_r,) array of raw observed values in the alignment
            window t in {-T_r, ..., -1}.
        pre_window_baseline: (<=20,) array of raw observed values in the
            pre-window window t in {-T_r-20, ..., -T_r-1}. May be shorter if
            the country has fewer pre-window years.
        median_sd_for_floor: Optional cross-country median SD for this
            indicator (computed at fit time across all training countries).
            When provided, sigma_min = 1e-3 * median_sd_for_floor per §3.2.2.
            When None, sigma_min defaults to 1e-6 (kernel-time fallback when
            the prototype carries the median for floor computation).

    Returns:
        NormalizationResult dataclass.

    Raises:
        ValueError: if pre_window_baseline has zero length.
    """
    raw_trajectory = np.asarray(raw_trajectory, dtype=float)
    pre_window_baseline = np.asarray(pre_window_baseline, dtype=float)
    if pre_window_baseline.size == 0:
        raise ValueError(
            "pre_window_baseline must have at least 1 year; per §3.2.2 "
            "instances with <20 pre-window years carry the BASELINE_TOO_SHORT "
            "flag and are dropped from training. Kernel-time queries with "
            "insufficient baseline should raise SubstrateInsufficientError."
        )

    baseline_mean = float(np.mean(pre_window_baseline))
    baseline_sd = float(np.std(pre_window_baseline, ddof=1)) if pre_window_baseline.size >= 2 else 0.0

    if median_sd_for_floor is not None and median_sd_for_floor > 0:
        sigma_floor = 1e-3 * median_sd_for_floor
    else:
        sigma_floor = 1e-6

    floored = baseline_sd < sigma_floor
    effective_sd = max(baseline_sd, sigma_floor)

    y_normalized = (raw_trajectory - baseline_mean) / effective_sd

    return NormalizationResult(
        y_normalized=y_normalized,
        baseline_mean=baseline_mean,
        baseline_sd=baseline_sd,
        baseline_n_years=int(pre_window_baseline.size),
        floored=floored,
    )


# ---- FPCA in the Sobolev metric (§3.1.2) ------------------------------------


@dataclass(frozen=True)
class FPCAResult:
    """FPCA decomposition result.

    Per §3.1.2 binding: M_r in {3, 4} selected by cumulative variance >= 0.80
    with floor 3, ceiling 4. If selection fails, ``selected_M_r`` is None and
    the caller routes to the §3.1.4 fallback.
    """

    V: np.ndarray  # (K_basis * K_indicators, M_max) principal directions
    eigenvalues: np.ndarray  # full eigenvalue spectrum (descending)
    cumulative_variance: np.ndarray  # cumulative fraction of variance explained
    scores: np.ndarray  # (N_r, M_max) per-instance scores onto V
    beta_mean: np.ndarray  # mean basis-coefficient vector across instances
    selected_M_r: int | None  # chosen M_r in {3, 4} or None if fit fails
    selection_reason: str  # human-readable reason for selection / failure
    scree_ratio_at_selected: float  # (M_r+1)-th / M_r-th eigenvalue ratio


def fit_fpca(
    beta_matrix: np.ndarray,
    R: np.ndarray,
    *,
    M_max: int = M_R_CEILING,
) -> FPCAResult:
    """Fit FPCA on basis coefficients with the Sobolev inner-product metric.

    Per §3.1.2 binding equation: scores s_c = V_r^T R (beta_c - bar_beta_r).
    The FPCA is computed by solving the generalized eigenvalue problem

        Cov(beta) v = lambda R v

    where R is the **positive-definite metric** (the Sobolev penalty matrix,
    NOT its inverse). Under this convention ``scipy.linalg.eigh(cov, R)``
    returns eigenvectors V satisfying ``V^T R V = I`` (R-orthonormality),
    and the per-instance scores ``s_c = V^T R (beta_c - bar_beta_r)`` are
    consistent with that normalization. Per QA B3 (2026-05-17) the
    earlier docstring stated ``R^{-1}`` which was wrong; implementation
    was already correct.

    Args:
        beta_matrix: (N_r, K_basis * K_indicators) stacked per-instance
            basis coefficients. Row c is instance c's flattened coefficient
            vector across K_indicators indicators.
        R: (K_basis * K_indicators, K_basis * K_indicators) Sobolev penalty
            matrix (block-diagonal across indicators with identical per-
            indicator R blocks).
        M_max: Hard ceiling on number of FPCA components retained. Default
            equals spec ceiling 4.

    Returns:
        FPCAResult dataclass.

    Raises:
        ValueError: if beta_matrix has fewer than 2 rows (FPCA undefined).
    """
    if beta_matrix.shape[0] < 2:
        raise ValueError(
            f"FPCA requires N_r >= 2 instances; got {beta_matrix.shape[0]}. "
            f"Per §3.1.5 sparse recipes route to the §3.1.4 GP fallback."
        )
    if R.shape[0] != beta_matrix.shape[1]:
        raise ValueError(
            f"R dim {R.shape} mismatches beta width {beta_matrix.shape[1]}"
        )

    # Center.
    beta_mean = np.mean(beta_matrix, axis=0)
    beta_centered = beta_matrix - beta_mean[np.newaxis, :]

    # Covariance in coefficient space.
    N_r = beta_matrix.shape[0]
    cov = (beta_centered.T @ beta_centered) / max(N_r - 1, 1)
    cov = 0.5 * (cov + cov.T)  # symmetrize

    # Generalized eigenproblem: cov v = lambda R v (R as positive-definite
    # metric, NOT its inverse — see docstring B3 correction).
    # scipy.linalg.eigh(A, B) solves A v = lambda B v; here A=cov, B=R.
    # Returned eigenvectors V satisfy V^T R V = I.
    # eigh returns eigenvalues ascending; reverse for descending.
    try:
        eigvals_asc, eigvecs_asc = eigh(cov, R)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"FPCA generalized eigendecomposition failed: {exc}") from exc

    # Descending order.
    idx = np.argsort(eigvals_asc)[::-1]
    eigvals = eigvals_asc[idx]
    eigvecs = eigvecs_asc[:, idx]

    # Clip negative eigenvalues that arise from numerical noise to 0.
    eigvals = np.clip(eigvals, a_min=0.0, a_max=None)

    total_var = float(np.sum(eigvals))
    if total_var <= 0:
        cumvar = np.zeros_like(eigvals)
    else:
        cumvar = np.cumsum(eigvals) / total_var

    # Retain leading M_max directions.
    M_max_eff = min(M_max, eigvecs.shape[1])
    V = eigvecs[:, :M_max_eff]

    # Per-instance scores: s_c = V^T R (beta_c - bar_beta_r).
    scores = beta_centered @ R @ V

    # M_r selection rule (§3.1.2 + §3.1.5):
    #   1. smallest M_r >= floor with cumulative variance >= target,
    #   2. with hard ceiling M_max,
    #   3. scree elbow at chosen M_r per §3.1.5 operationalization
    #      (eigval[M_r+1] / eigval[M_r] <= 0.4).
    selected: int | None = None
    reason = "no_candidate_satisfies_variance_target"
    for candidate_M in range(M_R_FLOOR, M_max_eff + 1):
        # Cumulative variance is 1-indexed via the index candidate_M - 1.
        cum_at_candidate = cumvar[candidate_M - 1] if candidate_M - 1 < len(cumvar) else 0.0
        if cum_at_candidate >= M_R_VARIANCE_TARGET:
            selected = candidate_M
            reason = f"M_r={candidate_M} reaches cumulative variance {cum_at_candidate:.4f} >= {M_R_VARIANCE_TARGET}"
            break

    scree_ratio = 0.0
    if selected is not None:
        next_eig = eigvals[selected] if selected < len(eigvals) else 0.0
        curr_eig = eigvals[selected - 1] if selected - 1 < len(eigvals) else 1e-12
        scree_ratio = float(next_eig / max(curr_eig, 1e-12))
        # §3.1.5 scree elbow check is INFORMATIONAL at primary selection;
        # the fitter logs scree_ratio but uses cumulative variance as the
        # binding rule (§3.1.2 takes precedence over the §3.1.5 elbow heuristic
        # when both fire).

    return FPCAResult(
        V=V,
        eigenvalues=eigvals,
        cumulative_variance=cumvar,
        scores=scores,
        beta_mean=beta_mean,
        selected_M_r=selected,
        selection_reason=reason,
        scree_ratio_at_selected=scree_ratio,
    )


# ---- Diagnostic gates (§3.1.3 + §3.5.4) -------------------------------------


@dataclass(frozen=True)
class SamplerDiagnostics:
    """NUTS sampler diagnostic gates per §3.1.3 (post-F-H-4-A4)."""

    rhat_max: float
    ess_min: float
    n_divergences: int
    n_post_warmup_draws: int  # F-H-4-A4: required for rate-gate evaluation
    divergence_rate: float    # F-H-4-A4: n_divergences / n_post_warmup_draws
    rhat_gate_pass: bool
    ess_gate_pass: bool
    divergence_gate_pass: bool

    @property
    def all_pass(self) -> bool:
        return self.rhat_gate_pass and self.ess_gate_pass and self.divergence_gate_pass


def evaluate_sampler_diagnostics(
    rhat_values: np.ndarray | list[float],
    ess_values: np.ndarray | list[float],
    n_divergences: int,
    n_post_warmup_draws: int | None = None,
) -> SamplerDiagnostics:
    """Evaluate the three §3.1.3 sampler gates (post-F-H-4-A4 divergence relaxation).

    Per §3.1.3 binding (after F-H-4-A4 amendment, docs-specs 2026-05-20):
      - All R-hat <= RHAT_GATE (1.01)
      - Effective sample size >= ESS_GATE (400) on every parameter
      - Divergent transitions <= DIVERGENCE_ABS_GATE (5 absolute) AND
        divergence rate <= DIVERGENCE_RATE_GATE (0.5%) over post-warmup draws
        (single divergence => refit at target_accept=0.99 — existing behavior;
         relaxed gate evaluated only on refit result)

    Args:
        rhat_values: per-parameter R-hat values from arviz summary.
        ess_values: per-parameter ESS values from arviz summary.
        n_divergences: total divergent transitions (post-warmup) from
            ``idata.sample_stats["diverging"].sum()``.
        n_post_warmup_draws: total post-warmup draws (= n_chains * n_draws).
            Required for the F-H-4-A4 rate gate. If None, only the absolute
            gate fires (backward-compatible with pre-A4 callers, but emits
            divergence_rate = NaN — callers should always pass this).

    Returns:
        SamplerDiagnostics with all gate-pass flags + rate provenance.
    """
    rhat_arr = np.asarray(rhat_values, dtype=float)
    ess_arr = np.asarray(ess_values, dtype=float)
    rhat_max = float(np.nanmax(rhat_arr)) if rhat_arr.size > 0 else 0.0
    ess_min = float(np.nanmin(ess_arr)) if ess_arr.size > 0 else 0.0
    n_div = int(n_divergences)
    if n_post_warmup_draws is None or n_post_warmup_draws <= 0:
        div_rate = float("nan")
        # Without n_post_warmup_draws, can only enforce the absolute gate.
        div_pass = n_div <= DIVERGENCE_ABS_GATE
    else:
        div_rate = n_div / float(n_post_warmup_draws)
        div_pass = (n_div <= DIVERGENCE_ABS_GATE) and (div_rate <= DIVERGENCE_RATE_GATE)
    return SamplerDiagnostics(
        rhat_max=rhat_max,
        ess_min=ess_min,
        n_divergences=n_div,
        n_post_warmup_draws=int(n_post_warmup_draws) if n_post_warmup_draws else 0,
        divergence_rate=div_rate,
        rhat_gate_pass=rhat_max <= RHAT_GATE,
        ess_gate_pass=ess_min >= ESS_GATE,
        divergence_gate_pass=div_pass,
    )


def loio_coverage(
    held_out_log_predictive: np.ndarray | list[float],
    nominal_level: float = LOIO_NOMINAL_LEVEL,
) -> float:
    """Compute mean LOIO posterior-predictive coverage at nominal level.

    Per §3.5.4 binding: the fraction of held-out instances whose true label's
    posterior-predictive density falls inside the central `nominal_level`
    interval of the predicted distribution.

    Args:
        held_out_log_predictive: (N_r,) array of per-instance booleans (or
            0/1 floats) where True/1 indicates the held-out instance's
            label was covered by its LOIO predicted central interval.
        nominal_level: nominal coverage level (default 0.80 per §3.5.4).

    Returns:
        Mean coverage as a float in [0, 1].
    """
    coverage = np.asarray(held_out_log_predictive, dtype=float)
    if coverage.size == 0:
        return 0.0
    if not 0.0 <= nominal_level <= 1.0:
        raise ValueError(f"nominal_level must be in [0,1]; got {nominal_level}")
    return float(np.mean(coverage))


# ---- DTW (deterministic, used by kernel) ------------------------------------


def dtw_distance(
    a: np.ndarray,
    b: np.ndarray,
) -> tuple[float, int]:
    """Compute Dynamic Time Warping distance + minimum-lag index.

    Used by the shape kernel (§4.2) to score `shape_dtw_score` and
    `shape_phase_alignment`. Deterministic; no random state.

    Args:
        a: (T_a,) array (the country's z-scored trajectory).
        b: (T_b,) array (the prototype's posterior-mean trajectory).

    Returns:
        (distance, optimal_lag) where:
          distance: scalar DTW distance.
          optimal_lag: signed integer lag (b shifted by this much relative
            to a) at which the warping path's final alignment lands; the
            kernel converts this to a [-1, 1] phase-alignment cosine.

    Raises:
        ValueError: if either input is empty.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size == 0 or b.size == 0:
        raise ValueError("DTW inputs must be non-empty")

    n, m = a.shape[0], b.shape[0]
    # Cost matrix with +inf padding for clean recurrence.
    D = np.full((n + 1, m + 1), np.inf, dtype=float)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        ai = a[i - 1]
        for j in range(1, m + 1):
            cost = abs(ai - b[j - 1])
            D[i, j] = cost + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])

    distance = float(D[n, m])

    # Recover the warping path to extract the dominant lag.
    i, j = n, m
    path_lags: list[int] = []
    while i > 0 and j > 0:
        path_lags.append(j - i)
        # Move to predecessor with min cost. Per N3 (QA 2026-05-17):
        # np.argmin is clearer than list.sort on the hot path.
        cand_costs = np.array(
            [D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]], dtype=float
        )
        cand_indices = (
            (i - 1, j - 1),
            (i - 1, j),
            (i, j - 1),
        )
        choice = int(np.argmin(cand_costs))
        i, j = cand_indices[choice]

    if path_lags:
        # Use the median lag along the warping path as the representative
        # offset (robust to single-step path noise).
        optimal_lag = int(np.median(path_lags))
    else:
        optimal_lag = 0

    return distance, optimal_lag


# ---- GP fallback constants (§3.1.4 binding) ---------------------------------

# Same NUTS gate constants apply to the GP fallback (§3.1.3 imported by
# §3.1.4 by reference).  No additional constants needed; the GP model
# uses the same RHAT_GATE / ESS_GATE / TARGET_ACCEPT_DEFAULT values.

# Placeholder sentinel values for schema fields that are FPCA-specific
# but required by the indicator_signature schema even in fallback entries.
# The schema's ``fpca_component_scores`` is defined as "LKJ posterior mean
# of μ_r in FPCA score space"; for the GP fallback there is no FPCA score
# space, so we emit an empty list (valid JSON array of numbers, passes
# schema's ``type: array, items: number``).
GP_FALLBACK_FPCA_SCORES_SENTINEL: list[float] = []
GP_FALLBACK_FPCA_CUMVAR_SENTINEL: float = 0.0
GP_FALLBACK_FPCA_BASIS_LABEL: str = "gp_fallback_no_fpca_basis"


# ---- §3.1.4 GP Fallback models -----------------------------------------------


@dataclass(frozen=True)
class GPFallbackPosterior:
    """Posterior summary from the §3.1.4 hierarchical Bayes + GP fallback fit.

    Carries:
      - per-indicator posterior mean trajectory (recipe-level GP mean f_r^(k))
      - per-indicator posterior covariance diagonal (time-diagonal of the
        posterior covariance of f_r^(k); this is the "posterior kernel-induced
        covariance" §3.5.1 refers to for Mahalanobis scoring under fallback)
      - sampler diagnostics for the gate evaluation
    """

    posterior_mean_trajectories: list[np.ndarray]  # one per indicator, (T_r,)
    posterior_cov_diags: list[np.ndarray]  # one per indicator, (T_r,)
    sampler_diagnostics: "SamplerDiagnostics"
    idata: object  # arviz InferenceData; TYPE_CHECKING only, avoid circular import


def build_gp_fallback_model(
    trajectories: np.ndarray,
    K_indicators: int,
    T_r: int,
) -> Any:
    """Construct the PyMC model for the §3.1.4 hierarchical-Bayes + GP fallback.

    **Post-F-H-4-A1 model** (docs-specs 2026-05-18, 8-seat ratified 8/8):

        y_c^(k)(t) = f_r^(k)(t) + ε_c,t^(k)

        f_r^(k)  ~ GP(0, κ_recipe^(k)(t, t'))      — recipe-level functional mean
        ε_c,t^(k) ~ N(0, σ_ε²)                     — observation noise

    Squared-exponential kernel:
        κ_recipe^(k)(t,t') = α_k² exp(-(t-t')²/(2ℓ_k²))

    Hyperpriors per Priya §3.1.4 (vectorized across indicators):
        α_recipe  ~ HalfCauchy(0, 1),                shape=(K,)
        ℓ_recipe  ~ LogNormal(log(1.5), 0.5),        shape=(K,)   — F-H-4-A3 (was InvGamma(2,1))
        σ_ε       ~ HalfCauchy(0, 0.5),              shape=(K,)

    Per-indicator slices: α_k = α_recipe[k], ℓ_k = ℓ_recipe[k], σ_ε_k = σ_ε[k].
    Methodology unchanged from F-H-4-A1: same priors, same posteriors, same
    likelihood. Vectorization is a code-structure refactor to reduce gradient
    fan-in (see substrate note below).

    **F-H-4-A1 amendment context (binding):** the instance-level residual GP
    g_c^(k) and its hyperpriors (α_inst_k, ℓ_inst_k) were removed from
    §3.1.4 per docs-specs#115 (merged 396aa67). Justification: the production-
    scale model (K_indicators = 5, yielding 35 scalar free variables)
    exceeded the PyTensor Python-interpreter-mode kernel argument limit
    under the PYTENSOR_FLAGS=cxx= pin (Windows substrate constraint
    inherited from Path-B Bayes). The crash occurred at model dispatch
    before any sample was drawn — F-Shape-1 not violated. Instance-level
    variation now absorbed into σ_ε^(k) per indicator (homoskedastic).

    **Substrate note (vectorization refactor 2026-05-18):** F-H-4-A1
    alone (15 scalar hyperpriors at K=5) STILL crashed at NUTS dispatch.
    Inspection of attempt-2 failing Apply node (Add at toposort 520) showed
    40 inputs — the gradient accumulator's fan-in, not the free-RV count,
    is the binding limit. Refactored to declare each hyperprior as a single
    vector RV of shape (K,) so the gradient compute sees 3 vector inputs
    rather than 3K scalar inputs. NOT an F-H-4 amendment — the model
    equations, priors, and posteriors are mathematically identical. Per-
    indicator parameter values are now `alpha_recipe[k]`, `ell_recipe[k]`,
    `sigma_eps[k]`. Lock JSON provenance unchanged (gp_fallback_variant
    remains "v2_no_instance_gp"; gp_fallback_amendment remains "F-H-4-A1").

    §3.5.1 posterior_cov_diag contract preserved: still extracted from the
    Bayesian posterior over f_r^(k) at integer time points.

    Restoration path: if Linux/WSL2 substrate enables PyTensor C-compiler
    mode, restore g_c^(k) per pre-amendment §3.1.4 + file fresh F-H-4
    amendment retracting F-H-4-A1.

    Args:
        trajectories: (N_r, T_r, K_indicators) array of normalized trajectories.
            Axis 0 = instances, axis 1 = time steps, axis 2 = indicators.
            The time axis runs over integer offsets {-T_r, ..., -1} (aliased to
            indices 0, 1, ..., T_r-1 for zero-based array indexing).
        K_indicators: number of key indicators (axis-2 extent of trajectories).
        T_r: canonical length (number of integer time steps).

    Returns:
        A PyMC Model object; caller must invoke pm.sample() within a ``with
        model:`` block or use pm.sample(model=model).

    Raises:
        ImportError: if pymc is not installed (this function imports lazily so
            the rest of the module does not pay the PyMC import cost).
        ValueError: if trajectories.shape does not match (*, T_r, K_indicators).
    """
    import os

    if trajectories.ndim != 3:
        raise ValueError(
            f"trajectories must be 3-D (N_r, T_r, K_indicators); got shape {trajectories.shape}"
        )
    N_r, T_r_actual, K_actual = trajectories.shape
    if T_r_actual != T_r or K_actual != K_indicators:
        raise ValueError(
            f"trajectories shape {trajectories.shape} does not match "
            f"(N_r={N_r}, T_r={T_r}, K_indicators={K_indicators})"
        )

    if "PYTENSOR_FLAGS" not in os.environ:
        os.environ["PYTENSOR_FLAGS"] = "cxx="

    import pymc as pm

    # Integer time grid 0..T_r-1 (represents year offsets -T_r..-1 normalised
    # to a 0-based index for the covariance algebra; distances are scale-free
    # in the SE kernel so the offset choice does not affect the posterior shape).
    t_grid = np.arange(T_r, dtype=float)  # (T_r,)

    # Precompute squared distances matrix: D2[i,j] = (t_i - t_j)^2.
    t_col = t_grid[:, None]  # (T_r, 1)
    t_row = t_grid[None, :]  # (1, T_r)
    D2 = (t_col - t_row) ** 2  # (T_r, T_r)

    with pm.Model() as model:  # noqa: SIM117
        # --- Vectorized hyperpriors (§3.1.4 binding, F-H-4-A1) ---
        # Single vector RV of shape (K,) per hyperprior type. Reduces the
        # gradient accumulator's fan-in from 3K scalar inputs to 3 vector
        # inputs (see substrate note in docstring). Per-indicator parameter
        # values are accessed via array indexing inside the loop below.
        alpha_recipe = pm.HalfCauchy(
            "alpha_recipe", beta=1.0, shape=(K_indicators,)
        )
        # F-H-4-A3 (docs-specs 2026-05-19, 8-seat ratified 8/8 with Marcus rider):
        # ell_recipe prior changed from InvGamma(2,1) to LogNormal(log(1.5), 0.5).
        # Justification (first-principles, F-Shape-1 compliant — NOT walk-data
        # informed): InvGamma(2,1) puts ~11% prior mass above ell=5 per indicator,
        # which at T_r=5 saturates the SE kernel (Gram matrix → rank-1) and creates
        # a flat marginal likelihood mode in the saturation regime. With K=5
        # independent indicators, P(at least one initialises in flat mode) ≈ 43%,
        # which produces multimodal hyperparameter posterior + NUTS mode-hopping
        # (Rasmussen & Williams 2006 §5.4.5; Stein 1999 §2.7).
        # LogNormal(log(1.5), 0.5) has 99th percentile ≈ 4.80, cutting saturation-
        # regime mass to <1% per indicator. Substrate-general: applies to any
        # recipe with T_r ≤ 6 routed through §3.1.4.
        ell_recipe = pm.LogNormal(
            "ell_recipe", mu=np.log(1.5), sigma=0.5, shape=(K_indicators,)
        )
        # Observation noise (§3.1.4 binding, post-F-H-4-A1). Instance-level
        # GP g_c^(k) removed per docs-specs#115 (8-seat ratified 8/8 APPROVE);
        # instance-level variation absorbed into sigma_eps (homoskedastic
        # per indicator). §3.5.1 posterior_cov_diag contract preserved
        # (still from f_r_k NUTS posterior draws).
        sigma_eps = pm.HalfCauchy(
            "sigma_eps", beta=0.5, shape=(K_indicators,)
        )

        # --- Analytic GP marginalization (§3.1.4 — mathematically identical,
        #     implementation optimization 2026-05-18) ---
        #
        # The latent f_r^(k) is integrated out analytically.  The marginal
        # likelihood is:
        #
        #     y_c^(k) ~ MvNormal(0, C_k)  for each of the N_r instances
        #
        # where  C_k = K_recipe^(k) + σ_ε_k² I_{T_r}  is the marginal
        # covariance.  This is the standard GP marginal likelihood identity
        # (Rasmussen & Williams §2.2):
        #
        #     p(Y_k | α_k, ℓ_k, σ_ε_k)
        #       = ∫ p(Y_k | f_r^(k), σ_ε_k) p(f_r^(k) | α_k, ℓ_k) df_r^(k)
        #
        # The NUTS hyperprior posteriors on (α_k, ℓ_k, σ_ε_k) are mathematically
        # identical to those obtained from the explicit-latent formulation.
        # No F-H-4 amendment needed: same priors, same posteriors, same §3.5.1
        # contract (posterior_mean_trajectory + posterior_cov_diag recovered
        # analytically in fit_gp_fallback from the hyperprior draws).
        #
        # Speedup rationale: removes 5 MvNormal latent vectors (K×T_r = 25
        # scalar free RVs) from the NUTS state space.  NUTS tree depth for
        # smooth hyperprior-only posteriors is typically 3-4 vs 7-8 for the
        # full latent model, giving ~16× reduction in leapfrog evaluations.
        for k in range(K_indicators):
            obs_k = trajectories[:, :, k]  # (N_r, T_r)

            alpha_k = alpha_recipe[k]
            ell_k = ell_recipe[k]
            sigma_eps_k = sigma_eps[k]

            # Squared-exponential kernel matrix.
            K_recipe = alpha_k**2 * pm.math.exp(-D2 / (2.0 * ell_k**2))
            # Marginal covariance C_k = K_recipe + σ_ε_k² I  (jitter folded in).
            C_k = K_recipe + (sigma_eps_k**2 + 1e-6) * np.eye(T_r)

            # Each row y_c^(k) is i.i.d. MvNormal(0, C_k).
            # PyMC handles the N_r i.i.d. factor automatically when
            # observed has shape (N_r, T_r).
            pm.MvNormal(
                f"obs_{k}",
                mu=np.zeros(T_r),
                cov=C_k,
                observed=obs_k,  # shape (N_r, T_r)
            )

    return model


def fit_gp_fallback(
    trajectories: np.ndarray,
    K_indicators: int,
    T_r: int,
    *,
    n_chains: int = 4,
    n_tune: int = 1000,
    n_draws: int = 1000,
    target_accept: float = TARGET_ACCEPT_DEFAULT,
    seed: int = 12345,
    progressbar: bool = True,
    max_treedepth: int | None = None,
    init: str = "jitter+adapt_diag",
    idata_save_path: "str | Path | None" = None,
) -> "GPFallbackPosterior":
    """Run the §3.1.4 GP fallback NUTS sampler and return posterior summary.

    Same MCMC acceptance gates apply as §3.1.3 (imported by reference):
      - All R-hat ≤ 1.01 across all α_k, ℓ_k, σ_ε, f_r_k parameters
      - ESS ≥ 400 on every parameter
      - Zero divergent transitions after warmup
        (single divergence → caller must refit at target_accept=0.99)
        (persistent divergences → caller must raise; fallback's fallback
         does not exist per scope guardrails)

    Args:
        trajectories: (N_r, T_r, K_indicators) normalized trajectory array.
        K_indicators: number of key indicators.
        T_r: canonical length.
        n_chains: number of HMC chains.
        n_tune: warmup iterations per chain.
        n_draws: post-warmup sampling iterations per chain.
        target_accept: NUTS target acceptance rate.
        seed: master random seed.
        progressbar: show NUTS progress bar (default True; set False for CI/cron).
        max_treedepth: NUTS max tree depth override (default: MAX_TREEDEPTH constant).
        init: PyMC NUTS initialization strategy (default: jitter+adapt_diag).

    Returns:
        GPFallbackPosterior with posterior mean trajectories + cov diags +
        sampler diagnostics.
    """
    import os

    if "PYTENSOR_FLAGS" not in os.environ:
        os.environ["PYTENSOR_FLAGS"] = "cxx="

    import arviz as az
    import pymc as pm

    model = build_gp_fallback_model(trajectories, K_indicators, T_r)

    _nuts_kwargs: dict = {
        "max_treedepth": max_treedepth if max_treedepth is not None else MAX_TREEDEPTH
    }
    N_r = trajectories.shape[0]
    logger.info(
        "fit_gp_fallback: NUTS start — K=%d T_r=%d N=%d "
        "chains=%d tune=%d draws=%d target_accept=%.2f max_treedepth=%d init=%s",
        K_indicators, T_r, N_r,
        n_chains, n_tune, n_draws, target_accept,
        _nuts_kwargs["max_treedepth"], init,
    )
    _t_sample_start = time.time()

    with model:
        idata = pm.sample(
            draws=n_draws,
            tune=n_tune,
            chains=n_chains,
            target_accept=target_accept,
            nuts=_nuts_kwargs,
            init=init,
            random_seed=seed,
            progressbar=progressbar,
            compute_convergence_checks=False,
            cores=1,
        )

    _elapsed = time.time() - _t_sample_start
    logger.info(
        "fit_gp_fallback: NUTS complete — elapsed=%.1fs (%.2f min)",
        _elapsed, _elapsed / 60,
    )

    # Persist InferenceData to disk so future formula corrections cost
    # ~30 seconds (recompute analytic-marginalization posterior from saved
    # hyperprior draws) instead of ~10 hours (full NUTS re-fit). 2026-05-21
    # bug review consensus: this is the single most-leverage piece of
    # operational infrastructure for the analytic-marginalization branch.
    if idata_save_path is not None:
        from pathlib import Path
        _idata_path = Path(idata_save_path)
        _idata_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            idata.to_netcdf(str(_idata_path))
            logger.info(
                "fit_gp_fallback: InferenceData persisted to %s (%.1f MB)",
                _idata_path,
                _idata_path.stat().st_size / (1024 * 1024),
            )
        except Exception as e:
            # Non-fatal: NetCDF persistence is for future-proofing, not the
            # critical fit path. Log + continue.
            logger.warning(
                "fit_gp_fallback: idata.to_netcdf(%s) failed: %s — continuing "
                "without disk persistence; re-fits will be required if the "
                "extraction formula changes.",
                _idata_path, e,
            )

    # --- Collect diagnostic variable names ---
    # Post-analytic-marginalization (2026-05-18): f_r_{k} are no longer
    # sampled by NUTS (they are integrated out analytically). Only the 3
    # vectorized hyperpriors remain as NUTS free RVs. R-hat / ESS gated on
    # hyperpriors only; semantically identical gate — if α_k, ℓ_k, σ_ε
    # converge, the posterior over f_r^(k) (recovered analytically below)
    # also converges.
    diag_var_names = ["alpha_recipe", "ell_recipe", "sigma_eps"]

    summary = az.summary(idata, var_names=diag_var_names, kind="diagnostics")
    rhat_values = summary["r_hat"].values
    ess_values = summary["ess_bulk"].values
    n_divergences = int(idata.sample_stats["diverging"].sum().values)
    # F-H-4-A4: pass post-warmup draw count for rate-gate evaluation.
    n_post_warmup_draws = int(n_chains * n_draws)
    diagnostics = evaluate_sampler_diagnostics(
        rhat_values, ess_values, n_divergences, n_post_warmup_draws=n_post_warmup_draws
    )

    # --- Recover posterior mean + covariance analytically (§3.5.1 contract) ---
    # Given NUTS draws of (α_k, ℓ_k, σ_ε_k), the GP conditional posterior of
    # f_r^(k) is closed-form (Rasmussen & Williams §2.2):
    #
    #   mu_post^(s)  = K_k^(s) @ C_k^(s)^{-1} @ Y_bar_k
    #   K_post^(s)   = K_k^(s) - N_r · K_k^(s) @ C_k^(s)^{-1} @ K_k^(s)
    #
    # where Y_bar_k = mean over all N_r instances (the sufficient statistic),
    # C_k^(s) = K_k^(s) + σ_ε_k^(s)² I, and N_r appears because the
    # marginal precision is N_r times the single-instance precision.
    #
    # posterior_mean_trajectory  = E_θ[mu_post^(s)]   — §3.5.1 semantics preserved
    # posterior_cov_diag         = diag(E_θ[K_post^(s)])  — §3.5.1 semantics preserved
    #
    # This is the Bayesian posterior of f_r^(k) at integer time points,
    # identical in semantics to the NUTS-sampled version (Chunk B Priya
    # adjudication precedent from B5: posterior source, not sample-variance).
    N_r = trajectories.shape[0]
    t_grid = np.arange(T_r, dtype=float)
    t_col = t_grid[:, None]
    t_row = t_grid[None, :]
    D2_np = (t_col - t_row) ** 2  # (T_r, T_r) — NumPy, not PyTensor

    # Flatten NUTS draws to (S, K)
    alpha_draws = idata.posterior["alpha_recipe"].values   # (chains, draws, K)
    ell_draws   = idata.posterior["ell_recipe"].values     # (chains, draws, K)
    sigma_draws = idata.posterior["sigma_eps"].values      # (chains, draws, K)
    alpha_flat = alpha_draws.reshape(-1, K_indicators)     # (S, K)
    ell_flat   = ell_draws.reshape(-1, K_indicators)       # (S, K)
    sigma_flat = sigma_draws.reshape(-1, K_indicators)     # (S, K)
    S = alpha_flat.shape[0]

    posterior_mean_trajectories: list[np.ndarray] = []
    posterior_cov_diags: list[np.ndarray] = []

    # Vectorized posterior extraction: batch over S draws using einsum /
    # broadcasting to avoid the pure-Python for-s loop overhead.
    # Shapes: alpha_flat (S, K), ell_flat (S, K), sigma_flat (S, K).
    # D2_np: (T_r, T_r).
    # Per indicator k:
    #   K_all[s] = α_s² exp(-D2/(2ℓ_s²))    → (S, T_r, T_r)
    #   C_all[s] = K_all[s] + σ_s² I         → (S, T_r, T_r)
    #   C_inv[s] = inv(C_all[s])             → (S, T_r, T_r)   via np.linalg.inv
    #   mu_post[s] = K_all[s] @ C_inv[s] @ Y_bar_k  → (S, T_r)
    #   K_post[s] = K_all[s] - N_r * K_all[s] @ C_inv[s] @ K_all[s]  → (S, T_r, T_r)
    eye_T = np.eye(T_r)[None, :, :]   # (1, T_r, T_r) for broadcast

    for k in range(K_indicators):
        obs_k   = trajectories[:, :, k]   # (N_r, T_r)
        Y_bar_k = obs_k.mean(axis=0)      # (T_r,)

        a_k   = alpha_flat[:, k]           # (S,)
        l_k   = ell_flat[:, k]             # (S,)
        sig_k = sigma_flat[:, k]           # (S,)

        # K_all: (S, T_r, T_r)
        K_all = (a_k[:, None, None] ** 2) * np.exp(
            -D2_np[None, :, :] / (2.0 * l_k[:, None, None] ** 2)
        )
        # C_all: (S, T_r, T_r) — POSTERIOR-CONDITIONING NOISE.
        # Bug fix 2026-05-21 (spec-trio reviewed; F-Shape-1 compliant —
        # operational tooling correction, NOT a threshold amendment): the
        # posterior of f_r given N i.i.d. observations y_c ~ N(f_r, σ²·I)
        # uses sufficient statistic y_bar ~ N(f_r, σ²/N · I). The conditioning
        # noise is σ²/N, NOT σ². Prior commit used σ² + 1e-6 here AND applied
        # an N_r multiplier in K_post — algebraically inconsistent: produced
        # K_post ≈ -980 · I (raw) clamped to 0 by np.maximum, killing the
        # §3.5.1 Mahalanobis denominator. Closed-form Woodbury check:
        # (K^-1 + N/σ² · I)^-1 = K - K (K + σ²/N · I)^-1 K  ✓
        # Reference: Rasmussen & Williams 2006 §2.2 (GP regression posterior).
        C_all = K_all + (sig_k[:, None, None] ** 2 / N_r + 1e-6) * eye_T
        # C_inv: (S, T_r, T_r) — np.linalg.inv handles batched inversion
        C_inv = np.linalg.inv(C_all)

        # mu_post: (S, T_r) — K @ C_inv @ y_bar  per draw
        KC_inv = K_all @ C_inv                          # (S, T_r, T_r)
        mu_post = KC_inv @ Y_bar_k                      # (S, T_r)

        # K_post: (S, T_r, T_r) — K - K @ C_inv @ K  per draw.
        # No N_r multiplier (the per-mean conditioning is already baked into
        # C_all via σ²/N). K_post is PSD by construction (Woodbury identity);
        # the 1e-9·I diagonal floor is a numerical safety net for ill-
        # conditioned K matrices (e.g., near-rank-1 SE kernel at small ℓ).
        K_post = K_all - KC_inv @ K_all                 # (S, T_r, T_r)

        mean_traj = mu_post.mean(axis=0)                # (T_r,)
        cov_mean  = K_post.mean(axis=0)                 # (T_r, T_r)

        cov_diag = np.diag(cov_mean) if T_r > 1 else np.array([float(cov_mean[0, 0])])
        # 1e-9 numerical floor (not a 0-clamp). PSD-by-construction posterior
        # never goes meaningfully negative; this only catches roundoff at
        # ill-conditioned K matrices.
        cov_diag = np.maximum(cov_diag, 1e-9)

        posterior_mean_trajectories.append(mean_traj)
        posterior_cov_diags.append(cov_diag)

    return GPFallbackPosterior(
        posterior_mean_trajectories=posterior_mean_trajectories,
        posterior_cov_diags=posterior_cov_diags,
        sampler_diagnostics=diagnostics,
        idata=idata,
    )


def extract_gp_posterior_signature(
    gp_posterior: GPFallbackPosterior,
    T_r: int,
    K_indicators: int,
    indicator_ids: list[str],
) -> list[dict]:
    """Return per-indicator signature dicts for the lock JSON from a GP posterior.

    Per §3.1.4 fallback and §4.3 schema binding, each indicator signature must
    carry the standard fields that the shape kernel (§4.2) and the dispatch
    loader expect:

      - ``posterior_mean_trajectory``: posterior mean of f_r^(k)(t) at integer
        time points {-T_r, ..., -1} (stored as 0-based indices but semantically
        the pre-event trajectory offsets).
      - ``posterior_cov_diag``: diagonal of the posterior covariance over
        f_r^(k)(t) — the "posterior kernel-induced covariance" §3.5.1 refers
        to for Mahalanobis scoring under fallback.
      - ``fit_method``: "hierarchical_bayes_gp_fallback" (binding sentinel
        that allows the kernel to distinguish FPCA vs GP paths).
      - FPCA sentinel fields (``fpca_component_scores``, ``fpca_basis``,
        ``fpca_cumulative_variance_explained``) with GP-fallback placeholder
        values — required by the indicator_signature schema; consumers MUST
        check ``fit_method == "hierarchical_bayes_gp_fallback"`` before
        interpreting FPCA fields.

    Per B5 lesson (QA 2026-05-17, Priya adjudication Option C):
    ``posterior_cov_diag`` here is the empirical Bayesian posterior covariance
    diagonal of f_r^(k)(t) across MCMC draws — NOT the empirical variance of
    the training trajectories. The kernel's Mahalanobis computation
    (§3.5.1 → §4.2) uses this as the denominator for shape-distance per time
    step, consistent with the FPCA-path's LKJ-back-projected Σ_r.

    Args:
        gp_posterior: GPFallbackPosterior from fit_gp_fallback.
        T_r: canonical length (must match gp_posterior array shapes).
        K_indicators: number of indicators.
        indicator_ids: ordered list of indicator IDs (same order as trajectories
            axis 2 passed to fit_gp_fallback).

    Returns:
        List of per-indicator signature dicts (one per indicator) in the order
        of indicator_ids. Each dict matches the ``indicator_signature`` schema
        in ``shape-prototypes.lock.schema.json``.

    Raises:
        ValueError: if lengths do not match expectations.
    """
    if len(gp_posterior.posterior_mean_trajectories) != K_indicators:
        raise ValueError(
            f"GP posterior has {len(gp_posterior.posterior_mean_trajectories)} "
            f"mean trajectories but K_indicators={K_indicators}"
        )
    if len(indicator_ids) != K_indicators:
        raise ValueError(
            f"indicator_ids length {len(indicator_ids)} != K_indicators={K_indicators}"
        )

    signatures: list[dict] = []
    for k, iid in enumerate(indicator_ids):
        mean_traj = np.asarray(gp_posterior.posterior_mean_trajectories[k], dtype=float)
        cov_diag = np.asarray(gp_posterior.posterior_cov_diags[k], dtype=float)

        if mean_traj.shape[0] != T_r:
            raise ValueError(
                f"indicator {iid!r}: posterior_mean_trajectory length "
                f"{mean_traj.shape[0]} != T_r={T_r}"
            )
        if cov_diag.shape[0] != T_r:
            raise ValueError(
                f"indicator {iid!r}: posterior_cov_diag length "
                f"{cov_diag.shape[0]} != T_r={T_r}"
            )

        sig = {
            # FPCA sentinel fields required by indicator_signature schema.
            # These are meaningless for the GP path; consumers must inspect
            # ``fit_method`` at the recipe level to know which path was used.
            "fpca_component_scores": GP_FALLBACK_FPCA_SCORES_SENTINEL,
            "fpca_cumulative_variance_explained": GP_FALLBACK_FPCA_CUMVAR_SENTINEL,
            "fpca_basis": GP_FALLBACK_FPCA_BASIS_LABEL,
            # GP-specific posterior fields (the load-bearing data for §3.5.1).
            "posterior_mean_trajectory": [float(x) for x in mean_traj.tolist()],
            "posterior_cov_diag": [float(x) for x in np.maximum(cov_diag, 0.0).tolist()],
            # Provenance tag — parallel to the FPCA path's "posterior_mean_lkj_back_projected".
            "cov_diag_source": "posterior_gp_f_r_empirical_cov_diag",
            # F-H-4-A1 amendment provenance (docs-specs 2026-05-18, 8-seat ratified).
            # Instance-level GP g_c^(k) removed from §3.1.4 model per substrate
            # constraint (PyTensor Python-mode kernel arg limit). Restoration
            # path: WSL/Linux substrate → retract F-H-4-A1 + restore g_c^(k).
            "gp_fallback_variant": "v3_no_instance_gp_lognormal_ell",
            "gp_fallback_amendment": "F-H-4-A1+F-H-4-A3",
        }
        signatures.append(sig)

    return signatures


def phase_alignment_cosine(
    lag: int,
    *,
    max_lag: int,
) -> float:
    """Convert a DTW optimal lag to a [-1, 1] phase-alignment cosine.

    Per §4.2 binding: shape_phase_alignment in [-1, 1] where 1 = no lag
    (perfectly in-phase) and -1 = anti-phase. The cosine map below is
    monotone decreasing in |lag| from 1 (at lag=0) to -1 (at lag = max_lag).

    Args:
        lag: signed integer lag from dtw_distance().
        max_lag: scale (typically T_r) over which the cosine spans [1, -1].

    Returns:
        Phase-alignment cosine in [-1, 1].
    """
    if max_lag <= 0:
        return 1.0 if lag == 0 else 0.0
    # Clamp lag to [-max_lag, max_lag].
    clamped = max(-max_lag, min(max_lag, lag))
    return float(np.cos(np.pi * clamped / max_lag))
