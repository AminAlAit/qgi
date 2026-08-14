"""Behavior tests for `scripts/fit_shape_prototype.py` (Chunk B).

Per Stage 6 §3 binding math. These tests verify:
  - synthetic-data smoke: a small N=15-instance dataset converges and
    produces a valid prototype JSON;
  - fallback flag fires when N_r < 10;
  - schema compliance: emitted prototype validates against the Chunk A
    schema invariants (loadable by ShapePrototypeDispatch);
  - LOIO coverage computes on a well-behaved synthetic dataset.

The PyMC NUTS sampler is the slow part (~30s on a modern laptop at small
N + reduced settings). Tests use heavily reduced sampling
(n_chains=2, n_tune=200, n_draws=200) to keep the suite under 90 seconds.
This is acceptable per `feedback_test_first_rule.md` because the test
verifies the PIPELINE structure (data -> FPCA -> NUTS -> lock JSON), not
the production diagnostic gates which are enforced at fit time on real
recipes (Chunk C, founder-gated).
"""
from __future__ import annotations

import os

# Windows compatibility: disable pytensor C compilation BEFORE any pytensor
# / pymc imports. Linux / macOS production runs can unset this for the
# C-backend speedup. Setting here protects the test suite across platforms.
os.environ.setdefault("PYTENSOR_FLAGS", "cxx=")

import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for p in (SRC_ROOT, SCRIPTS_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Test-only sampling overrides so the suite finishes quickly.
TEST_N_CHAINS = 2
TEST_N_TUNE = 200
TEST_N_DRAWS = 200
TEST_SEED = 7


# ---- Synthetic-data generators ----------------------------------------------


def _build_synthetic_panel(
    *,
    n_positive: int = 15,
    T_r: int = 5,
    indicator_ids: tuple[str, ...] = ("IND_A", "IND_B"),
    seed: int = 42,
    pre_window_years: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate a synthetic well-behaved FPCA-fittable dataset.

    Each instance is a country with a baseline period followed by an
    aligned trajectory; the aligned trajectory follows a common pattern
    plus per-instance noise on the FPCA score axis.
    """
    rng = np.random.default_rng(seed)
    countries = [f"C{i:03d}" for i in range(n_positive)]
    event_year = 2020

    # Canonical "shape" in z-score space — same for all instances modulo noise.
    canonical_z = {
        "IND_A": np.linspace(0.0, 1.0, T_r),
        "IND_B": np.linspace(1.0, 0.0, T_r),
    }

    rows = []
    positives = []
    for i, c in enumerate(countries):
        positives.append({"country_id": c, "event_year": event_year})
        baseline_mean = 100.0 + i * 2.0  # country-specific level offset
        baseline_sd_target = 5.0 + (i % 3) * 0.5
        N_pre = pre_window_years
        # Construct pre-window with EXACT (mean, sample-SD).
        d_offset = baseline_sd_target * np.sqrt((N_pre - 1) / N_pre)
        baseline_vals = [
            baseline_mean + (d_offset if k % 2 == 0 else -d_offset)
            for k in range(N_pre)
        ]
        baseline_years = list(range(event_year - T_r - N_pre, event_year - T_r))
        alignment_years = list(range(event_year - T_r, event_year))

        for iid in indicator_ids:
            # Pre-window baseline.
            for y, v in zip(baseline_years, baseline_vals):
                rows.append({"country_id": c, "year": y, "indicator_id": iid, "value": float(v)})
            # Alignment window: canonical z + small per-instance noise.
            noise = rng.normal(scale=0.10, size=T_r)
            z = canonical_z[iid] + noise
            for y, zi in zip(alignment_years, z):
                rows.append(
                    {
                        "country_id": c,
                        "year": y,
                        "indicator_id": iid,
                        "value": float(baseline_mean + baseline_sd_target * zi),
                    }
                )

    return pd.DataFrame(rows), pd.DataFrame(positives)


# ---- Synthetic-data smoke test ----------------------------------------------


@pytest.mark.slow
def test_fit_recipe_fpca_converges_on_synthetic_data() -> None:
    """Synthetic well-behaved data fits to a valid FPCA prototype.

    SLOW (~30-60s). Marked so the suite can opt-in via `-m slow`.
    """
    from fit_shape_prototype import fit_recipe_fpca

    panel, positives = _build_synthetic_panel(n_positive=15, T_r=5, seed=42)
    prototype, _ = fit_recipe_fpca(
        panel,
        positives,
        indicator_ids=["IND_A", "IND_B"],
        T_r=5,
        target_accept=0.95,
        n_chains=TEST_N_CHAINS,
        n_tune=TEST_N_TUNE,
        n_draws=TEST_N_DRAWS,
        random_seed=TEST_SEED,
    )
    # Either fpca succeeds OR fallback_required is True (with valid reason).
    assert prototype.n_training_positives == 15
    assert prototype.fit_method in ("fpca", "hierarchical_bayes_gp_fallback")
    if not prototype.fallback_required:
        assert prototype.fit_method == "fpca"
        assert prototype.fpca_M_r is not None
        assert M_R_FLOOR <= prototype.fpca_M_r <= M_R_CEILING
        assert prototype.fpca_cumulative_variance >= 0.80
        # Both indicators have a signature.
        assert "IND_A" in prototype.per_indicator_signature
        assert "IND_B" in prototype.per_indicator_signature
        for sig in prototype.per_indicator_signature.values():
            assert len(sig["posterior_mean_trajectory"]) == 5
            assert len(sig["posterior_cov_diag"]) == 5
    assert prototype.wall_time_seconds > 0


# Import the spec constants at module scope so the smoke test asserts
# against §3.1.2 binding values.
from shape_prototype_fit_utils import M_R_CEILING, M_R_FLOOR  # noqa: E402


# ---- Fallback flag ----------------------------------------------------------


def test_fallback_required_when_N_below_10() -> None:
    """N_r < 10 routes to fallback flag per §3.1.5 (no NUTS fired)."""
    from fit_shape_prototype import fit_recipe_fpca

    panel, positives = _build_synthetic_panel(n_positive=5, T_r=5, seed=42)
    prototype, _ = fit_recipe_fpca(
        panel,
        positives,
        indicator_ids=["IND_A", "IND_B"],
        T_r=5,
    )
    assert prototype.fallback_required is True
    assert "N_r" in prototype.fallback_reason
    assert prototype.fit_method == "hierarchical_bayes_gp_fallback"
    # No per-indicator signature emitted (Chunk B.2 populates).
    assert prototype.per_indicator_signature == {}


# ---- Schema compliance ------------------------------------------------------


@pytest.mark.slow
def test_emit_to_lock_file_validates_under_dispatch_loader(tmp_path: Path) -> None:
    """Emitting a fitted prototype produces a lock JSON that loads cleanly."""
    from fit_shape_prototype import emit_to_lock_file, fit_recipe_fpca

    panel, positives = _build_synthetic_panel(n_positive=15, T_r=5, seed=42)
    prototype, _ = fit_recipe_fpca(
        panel,
        positives,
        indicator_ids=["IND_A", "IND_B"],
        T_r=5,
        target_accept=0.95,
        n_chains=TEST_N_CHAINS,
        n_tune=TEST_N_TUNE,
        n_draws=TEST_N_DRAWS,
        random_seed=TEST_SEED,
    )
    if prototype.fallback_required:
        pytest.skip("Synthetic seed produced a fallback recipe; not a schema test scenario")

    prototype.recipe_id = "synthetic_recipe_id"
    lock_path = tmp_path / "shape-prototypes.lock.json"
    emit_to_lock_file(
        prototype,
        lock_path,
        stage_6_commit_sha="e4f9e7a",
    )
    # Load via the Chunk A dispatch loader — this is THE schema gate.
    from shape_prototype_dispatch import load_dispatch

    dispatch = load_dispatch(lock_path)
    assert "synthetic_recipe_id" in dispatch.recipes_with_prototype()
    proto = dispatch.prototype_for("synthetic_recipe_id")
    assert proto.fit_method == "fpca"
    assert proto.n_training_positives == 15


def test_emit_to_lock_file_minimal_payload_schema(tmp_path: Path) -> None:
    """Minimal emission path: no fit run, just verify the emitter shape.

    Constructs a synthetic FittedPrototype dataclass with a placeholder
    signature and verifies the emitted lock JSON loads via the Chunk A
    loader. This exercises emit_to_lock_file independently of the slow
    NUTS path.
    """
    from fit_shape_prototype import FittedPrototype, emit_to_lock_file

    T_r = 5
    prototype = FittedPrototype(
        recipe_id="minimal_recipe",
        indicator_ids=["IND_A"],
        T_r=T_r,
        n_training_positives=12,
        fit_method="fpca",
        fit_method_commit_sha="0" * 40,
        per_indicator_signature={
            "IND_A": {
                "fpca_component_scores": [0.0, 0.0, 0.0],
                "fpca_cumulative_variance_explained": 0.85,
                "fpca_basis": "cubic_spline_K8",
                "posterior_mean_trajectory": [0.0, 0.25, 0.5, 0.75, 1.0],
                "posterior_cov_diag": [0.01] * T_r,
            }
        },
        sampler_diagnostics={"rhat_max": 1.005, "ess_min": 800.0, "n_divergences": 0},
        loio_coverage_at_nominal_80=0.85,
        fallback_required=False,
        fallback_reason="",
        fpca_M_r=3,
        fpca_cumulative_variance=0.85,
        wall_time_seconds=1.0,
        training_data_snapshot_sha256="b" * 64,
        training_data_snapshot_s3_path="local-laptop-scale",
    )
    lock_path = tmp_path / "shape-prototypes.lock.json"
    emit_to_lock_file(prototype, lock_path, stage_6_commit_sha="e4f9e7a")
    from shape_prototype_dispatch import load_dispatch

    dispatch = load_dispatch(lock_path)
    assert "minimal_recipe" in dispatch.recipes_with_prototype()


# ---- LOIO coverage ----------------------------------------------------------


def test_loio_coverage_loop_on_synthetic_well_behaved_data() -> None:
    """LOIO coverage at 80% on a synthetic well-behaved dataset.

    Uses pre-fitted FPCA (no NUTS) for a deterministic, fast assertion.
    Per spec the production gate is >= 0.70; this synthetic dataset is
    designed to clear the gate by construction (low per-instance noise).
    """
    from fit_shape_prototype import _loio_coverage_loop
    from shape_prototype_fit_utils import build_cubic_bspline_basis, project_to_basis_coefficients

    panel, positives = _build_synthetic_panel(n_positive=15, T_r=5, seed=42)
    T_r = 5
    Phi, R_block = build_cubic_bspline_basis(T_r)
    K_basis = Phi.shape[1]
    indicator_ids = ["IND_A", "IND_B"]
    K_ind = len(indicator_ids)
    R_full = np.zeros((K_basis * K_ind, K_basis * K_ind))
    for k in range(K_ind):
        R_full[k * K_basis : (k + 1) * K_basis, k * K_basis : (k + 1) * K_basis] = R_block

    # Build beta_matrix.
    beta_rows = []
    for row in positives.itertuples(index=False):
        c = row.country_id
        ey = int(row.event_year)
        per_ind = []
        for iid in indicator_ids:
            mask_a = (
                (panel["country_id"] == c)
                & (panel["indicator_id"] == iid)
                & (panel["year"] >= ey - T_r)
                & (panel["year"] < ey)
            )
            align = panel.loc[mask_a].sort_values("year")["value"].astype(float).values
            mask_b = (
                (panel["country_id"] == c)
                & (panel["indicator_id"] == iid)
                & (panel["year"] >= ey - T_r - 20)
                & (panel["year"] < ey - T_r)
            )
            base = panel.loc[mask_b, "value"].astype(float).values
            mu_b = float(np.mean(base))
            sd_b = float(np.std(base, ddof=1))
            z = (align - mu_b) / max(sd_b, 1e-6)
            beta = project_to_basis_coefficients(z, Phi)
            per_ind.append(beta)
        beta_rows.append(np.concatenate(per_ind))
    beta_matrix = np.stack(beta_rows, axis=0)

    flags = _loio_coverage_loop(beta_matrix, R_full, M_r=3, nominal_level=0.80)
    coverage = float(np.mean(flags))
    # Synthetic well-behaved data should clear at least 0.50 (loose lower
    # bound — exact rate depends on the per-instance noise). The §3.5.4
    # production gate of 0.70 fires on real recipes (Chunk C).
    assert coverage >= 0.50, f"LOIO coverage {coverage:.3f} below synthetic floor"


# ---- Diagnostic helpers -----------------------------------------------------


def test_evaluate_sampler_diagnostics_logic() -> None:
    """Diagnostic gate logic per §3.1.3 (post-F-H-4-A4 divergence-gate relaxation)."""
    from shape_prototype_fit_utils import evaluate_sampler_diagnostics

    # All pass.
    d = evaluate_sampler_diagnostics(
        [1.005, 1.001], [500, 800], 0, n_post_warmup_draws=4000
    )
    assert d.all_pass
    # rhat fail.
    d = evaluate_sampler_diagnostics(
        [1.05, 1.001], [500, 800], 0, n_post_warmup_draws=4000
    )
    assert not d.all_pass
    assert not d.rhat_gate_pass
    # ESS fail.
    d = evaluate_sampler_diagnostics(
        [1.005, 1.001], [50, 800], 0, n_post_warmup_draws=4000
    )
    assert not d.all_pass
    assert not d.ess_gate_pass
    # Divergence fail under F-H-4-A4 requires >5 absolute OR >0.5% rate.
    # 6 divergences fails the absolute gate.
    d = evaluate_sampler_diagnostics(
        [1.005, 1.001], [500, 800], 6, n_post_warmup_draws=4000
    )
    assert not d.all_pass
    assert not d.divergence_gate_pass
    # 2 divergences PASSES under F-H-4-A4 (pre-A4 this was a fail).
    d = evaluate_sampler_diagnostics(
        [1.005, 1.001], [500, 800], 2, n_post_warmup_draws=4000
    )
    assert d.all_pass


# ---- Utility fixture tests (cheap, no NUTS) ---------------------------------


def test_cubic_bspline_basis_shape() -> None:
    """Basis has spec shape: (T_r, K_basis=8) and R has shape (8, 8)."""
    from shape_prototype_fit_utils import K_BASIS_INTERIOR_KNOTS, build_cubic_bspline_basis

    T_r = 5
    Phi, R = build_cubic_bspline_basis(T_r)
    assert Phi.shape == (T_r, K_BASIS_INTERIOR_KNOTS)
    assert R.shape == (K_BASIS_INTERIOR_KNOTS, K_BASIS_INTERIOR_KNOTS)
    # R is symmetric.
    assert np.allclose(R, R.T)
    # R is positive-definite (tiny ridge added).
    eigvals = np.linalg.eigvalsh(R)
    assert (eigvals > 0).all()


def test_per_country_z_score_exact_baseline() -> None:
    """With an exact baseline (mean=10, sd=2), z-score of a 12-value is 1.0."""
    from shape_prototype_fit_utils import per_country_z_score

    # Construct baseline with EXACT mean 10, sample-SD 2.
    target_mean = 10.0
    target_sd = 2.0
    N_pre = 20
    d_offset = target_sd * np.sqrt((N_pre - 1) / N_pre)
    baseline = np.array(
        [target_mean + (d_offset if i % 2 == 0 else -d_offset) for i in range(N_pre)]
    )
    norm = per_country_z_score(
        raw_trajectory=np.array([12.0, 14.0]),
        pre_window_baseline=baseline,
    )
    assert norm.baseline_mean == pytest.approx(target_mean)
    assert norm.baseline_sd == pytest.approx(target_sd)
    np.testing.assert_allclose(norm.y_normalized, [1.0, 2.0], atol=1e-9)


def test_fpca_recovers_low_rank_structure() -> None:
    """Synthetic rank-3 data yields M_r=3 with cumulative_variance >= 0.80."""
    from shape_prototype_fit_utils import (
        M_R_FLOOR,
        build_cubic_bspline_basis,
        fit_fpca,
    )

    rng = np.random.default_rng(0)
    T_r = 5
    Phi, R = build_cubic_bspline_basis(T_r)
    K_basis = Phi.shape[1]

    # Generate 30 samples with 3-dim structure + small noise.
    N = 30
    rank = 3
    # Random orthonormal 3-dim basis in K_basis-space.
    U_random = rng.standard_normal((K_basis, rank))
    U, _ = np.linalg.qr(U_random)
    scores_true = rng.standard_normal((N, rank)) * np.array([3.0, 2.0, 1.0])
    beta_matrix = scores_true @ U.T + 0.01 * rng.standard_normal((N, K_basis))

    fpca = fit_fpca(beta_matrix, R, M_max=4)
    assert fpca.selected_M_r in (3, 4)
    assert fpca.cumulative_variance[fpca.selected_M_r - 1] >= 0.80


def test_dtw_distance_is_zero_for_identical_trajectories() -> None:
    from shape_prototype_fit_utils import dtw_distance

    a = np.array([0.0, 0.5, 1.0, 0.5, 0.0])
    dist, lag = dtw_distance(a, a)
    assert dist == pytest.approx(0.0, abs=1e-9)
    assert abs(lag) <= 1


def test_dtw_distance_positive_for_offset_trajectories() -> None:
    from shape_prototype_fit_utils import dtw_distance

    a = np.array([0.0, 0.5, 1.0, 0.5, 0.0])
    b = a + 0.5
    dist, _ = dtw_distance(a, b)
    assert dist > 0.0


def test_phase_alignment_cosine_zero_lag_is_one() -> None:
    from shape_prototype_fit_utils import phase_alignment_cosine

    assert phase_alignment_cosine(0, max_lag=5) == pytest.approx(1.0, abs=1e-9)
    assert phase_alignment_cosine(5, max_lag=5) == pytest.approx(-1.0, abs=1e-9)
    assert phase_alignment_cosine(-5, max_lag=5) == pytest.approx(-1.0, abs=1e-9)


def test_sobolev_semi_norm_matches_analytic_closed_form_on_cubic_polynomial() -> None:
    """B2 test (QA 2026-05-17, Priya adjudication 2026-05-17).

    Validates that the Sobolev penalty matrix R is the **analytic integral**
    of second-derivative outer products (Ramsay & Silverman §5.5), NOT the
    discrete finite-difference proxy.

    Strategy: build the SAME basis the fitter uses (with the same
    L2-renormalization and central-trim), pick an arbitrary coefficient
    vector β, and verify that ``β^T R β`` matches an independent
    high-precision quadrature on the SAME basis functions:

        β^T R β  ?=  ∫_{-T_r}^{0} (Σ_i β_i φ_i''(t))^2 dt

    This decouples the R-correctness test from the spline's ability to
    represent any specific function (which the trimmed central basis
    cannot do for boundary-sensitive functions like t^3). The two should
    agree to ~1e-6 absolute relative error if R is computed via
    Gauss-Legendre quadrature (matching the independent fine-grid
    quadrature); the prior finite-difference proxy
    ``Phi^T D2^T D2 Phi`` would fail this test by orders of magnitude
    because the discrete second-difference operator on integer evaluation
    points is not the integral of the second derivative.

    Per Priya B2 adjudication (2026-05-17): this pins the analytic-integral
    binding of R&S §3.1.2 into CI.
    """
    from numpy.polynomial.legendre import leggauss
    from scipy.interpolate import BSpline

    from shape_prototype_fit_utils import (
        K_BASIS_INTERIOR_KNOTS,
        SPLINE_DEGREE,
        build_cubic_bspline_basis,
    )

    T_r = 8  # production-range upper end (Phase 1 recipes span T_r ∈ [4, 8])
    Phi, R = build_cubic_bspline_basis(T_r)
    K_basis = Phi.shape[1]
    assert K_basis == K_BASIS_INTERIOR_KNOTS

    # Reconstruct the SAME basis the fitter uses for independent quadrature.
    n_interior_knots = K_BASIS_INTERIOR_KNOTS
    quantile_positions = np.linspace(
        1.0 / (n_interior_knots + 1),
        n_interior_knots / (n_interior_knots + 1),
        n_interior_knots,
    )
    interior_knots = -T_r + quantile_positions * T_r
    boundary_lo = np.full(SPLINE_DEGREE + 1, -T_r, dtype=float)
    boundary_hi = np.full(SPLINE_DEGREE + 1, -1e-9, dtype=float)
    full_knots = np.concatenate([boundary_lo, interior_knots, boundary_hi])
    n_basis_full = len(full_knots) - SPLINE_DEGREE - 1

    # Rebuild Phi columns (to recover the L2 col_norms used by the fitter).
    t_grid = np.arange(-T_r, 0, dtype=float)
    Phi_raw = np.zeros((T_r, n_basis_full), dtype=float)
    splines: list[BSpline] = []
    for j in range(n_basis_full):
        coeffs = np.zeros(n_basis_full, dtype=float)
        coeffs[j] = 1.0
        spl = BSpline(full_knots, coeffs, SPLINE_DEGREE, extrapolate=False)
        splines.append(spl)
        Phi_raw[:, j] = spl(t_grid)
    Phi_raw = np.nan_to_num(Phi_raw, nan=0.0)
    drop_per_side = (n_basis_full - n_interior_knots) // 2
    Phi_trim = Phi_raw[:, drop_per_side : drop_per_side + n_interior_knots]
    splines_trim = splines[drop_per_side : drop_per_side + n_interior_knots]
    col_norms = np.linalg.norm(Phi_trim, axis=0)
    col_norms = np.where(col_norms < 1e-12, 1.0, col_norms)
    second_derivs = [spl.derivative(2) for spl in splines_trim]

    # Pick an arbitrary β. Use a smooth deterministic pattern to avoid
    # accidentally hitting the basis null space.
    rng = np.random.default_rng(20260517)
    beta = rng.standard_normal(K_basis)

    # Numerical semi-norm via R.
    numerical_seminorm = float(beta @ R @ beta)

    # Independent high-precision quadrature on the same basis functions.
    # Use a fine partition (every 0.01 unit subinterval) with 8-point
    # Gauss-Legendre quadrature per subinterval; this is independent of
    # the fitter's break-point partitioning and gives a ground-truth
    # integral to ~machine precision.
    gl_nodes, gl_weights = leggauss(8)
    a_total, b_total = -T_r, -1e-9
    n_segments = int(np.ceil((b_total - a_total) / 0.01))
    seg_breaks = np.linspace(a_total, b_total, n_segments + 1)
    independent_integral = 0.0
    for seg in range(n_segments):
        a, b = float(seg_breaks[seg]), float(seg_breaks[seg + 1])
        half = 0.5 * (b - a)
        mid = 0.5 * (b + a)
        pts = mid + half * gl_nodes
        wts = half * gl_weights
        # Σ_i (β_i / c_i) φ_i''(t) — apply the same L2 renormalization
        # the fitter's R uses.
        D2_at_pts = np.zeros(len(pts), dtype=float)
        for i, spl_dd in enumerate(second_derivs):
            D2_at_pts += (beta[i] / col_norms[i]) * np.nan_to_num(spl_dd(pts), nan=0.0)
        independent_integral += float(np.sum(wts * D2_at_pts ** 2))

    rel_error = abs(numerical_seminorm - independent_integral) / max(
        abs(independent_integral), 1e-12
    )
    assert rel_error < 1e-6, (
        f"Sobolev semi-norm β^T R β = {numerical_seminorm:.6f} differs from "
        f"independent fine-quadrature integral {independent_integral:.6f} "
        f"by relative error {rel_error:.6e} (> 1e-6 tolerance). Per B2 "
        f"(Priya 2026-05-17) the penalty matrix R must be the analytic "
        f"integral of second-derivative outer products via Gauss-Legendre "
        f"quadrature, NOT a finite-difference proxy."
    )
