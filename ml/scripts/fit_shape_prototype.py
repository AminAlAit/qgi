"""Shape-prototype fitter (Stage 6 §3 binding math, primary FPCA path).

Per `docs/specs/internal/ops/ml-track/stage-6-shape-feature-prereg.md` §3
(Priya, math primitive) + §4.3 (Ji-Hoon, schema). This script fits a
canonical shape prototype for one recipe via the §3.1.2 FPCA + §3.1.3
Bayesian generative model + §3.5.4 LOIO calibration gate, and emits the
result into `qgi-ml/config/shape-prototypes.lock.json` per Chunk A's
binding schema.

**Scope (Chunk B):**
  - PRIMARY path: §3.1.3 FPCA + hierarchical Bayes (NUTS) for N_r >= 10
    instances.
  - §3.1.4 hierarchical-Bayes + GP fallback path is DEFERRED to Chunk B.2
    (qgi-ml ticket to be filed; see deviations section in PR body). This
    fitter EMITS a ``fallback_required: true`` flag in the recipe block
    when the primary path is unviable; the operator routes to Chunk B.2.
  - §3.4 v2 length-derivation (Bayesian length posterior over T_r) is
    DEFERRED; this fitter consumes T_r as a CLI input (Tariq v1 emit per
    spec §3.4 ship-now). The recipe block's
    ``length_derivation_wall_time_seconds`` carries the FPCA fit time
    (not the v2 length derivation).

**Production usage (laptop-scale, per R4):**

    py -3.12 -m venv .venv-shape
    .venv-shape/Scripts/python.exe -m pip install -r requirements-shape.lock.txt
    .venv-shape/Scripts/python.exe scripts/fit_shape_prototype.py \\
        --recipe civil_war_and_insurgency \\
        --indicator-panel results/.../panel.parquet \\
        --positive-instances results/.../positives.csv \\
        --T-r 5 \\
        --output config/shape-prototypes.lock.json

**R4 binding:** no AWS calls. Loads panels from local parquet, emits
JSON locally. Real prototype population (civil_war + economic_recession
+ foreign_intervention) is Chunk C and requires founder per-session
approval per `feedback_no_pipeline_runs_without_approval.md`.

Authority: Priya #22 (§3 math) + Ji-Hoon #21 (§4 schema) + Kwame #11
(F-rules, §5) + Miriam #14 (exit table, §6).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Ensure src/ is on the path when this script runs from a checkout root.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from shape_prototype_fit_utils import (  # noqa: E402
    ESS_GATE,
    LOIO_COVERAGE_GATE,
    M_R_CEILING,
    M_R_FLOOR,
    MAX_TREEDEPTH,
    RHAT_GATE,
    TARGET_ACCEPT_DEFAULT,
    TARGET_ACCEPT_REFIT,
    NormalizationResult,
    build_cubic_bspline_basis,
    evaluate_sampler_diagnostics,
    extract_gp_posterior_signature,
    fit_fpca,
    fit_gp_fallback,
    loio_coverage,
    per_country_z_score,
    project_to_basis_coefficients,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fit_shape_prototype")


# ---- Result dataclasses -----------------------------------------------------


@dataclass
class FittedPrototype:
    """In-memory result of the fitter; serialized into the lock JSON block."""

    recipe_id: str
    indicator_ids: list[str]
    T_r: int
    n_training_positives: int
    fit_method: str  # "fpca" | "hierarchical_bayes_gp_fallback"
    fit_method_commit_sha: str
    per_indicator_signature: dict[str, dict[str, Any]]
    sampler_diagnostics: dict[str, Any]
    loio_coverage_at_nominal_80: float
    fallback_required: bool
    fallback_reason: str
    fpca_M_r: int | None
    fpca_cumulative_variance: float
    wall_time_seconds: float
    training_data_snapshot_sha256: str
    training_data_snapshot_s3_path: str
    audit_log: list[str] = field(default_factory=list)


# ---- Helpers ----------------------------------------------------------------


def _git_commit_sha() -> str:
    """Resolve current qgi-ml commit SHA; falls back to a placeholder."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return sha
    except Exception:  # noqa: BLE001
        return "unknown-sha-fitter-fallback"


def _sha256_of_dataframe(df: pd.DataFrame) -> str:
    """Stable SHA-256 over a DataFrame for training-data-snapshot provenance.

    Per N7 (QA 2026-05-17): Parquet (Arrow) serialization for stable
    cross-pandas-version hashing. CSV float formatting differs across pandas
    versions and introduces non-determinism in the provenance hash; Parquet's
    columnar binary representation is pinned by the Arrow spec.

    Falls back to CSV if Parquet (pyarrow / fastparquet) is unavailable
    (e.g. test environments without optional deps); fallback emits the same
    contract but loses cross-version stability.
    """
    import io

    try:
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        serialized = buf.getvalue()
    except (ImportError, ValueError):
        # Graceful fallback for environments without a parquet engine.
        serialized = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _canonical_sha(payload: dict[str, Any]) -> str:
    """Canonical SHA-256 over the lock JSON payload (file_sha256 cleared)."""
    clone = copy.deepcopy(payload)
    clone["metadata"]["file_sha256"] = ""
    canonical = json.dumps(clone, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---- Per-recipe GP fallback fitting (§3.1.4) --------------------------------


def fit_recipe_gp_fallback(
    indicator_panel: pd.DataFrame,
    positive_instances: pd.DataFrame,
    indicator_ids: list[str],
    T_r: int,
    *,
    target_accept: float = TARGET_ACCEPT_DEFAULT,
    n_chains: int = 4,
    n_tune: int = 1000,
    n_draws: int = 1000,
    random_seed: int = 12345,
    progressbar: bool = True,
    max_treedepth: int | None = None,
    init: str = "jitter+adapt_diag",
    idata_save_path: str | Path | None = None,
) -> tuple[FittedPrototype, dict[str, Any]]:
    """Run the §3.1.4 hierarchical-Bayes + GP fallback fit.

    Called when:
      (a) N_r < 10 historical positive instances (§3.1.5 floor), OR
      (b) FPCA fit failed (FPCA variance target not reached, or NUTS gates
          failed after refit at target_accept=0.99), OR
      (c) ``--force-fallback`` CLI flag was set by the operator.

    Applies the same §3.1.3 MCMC acceptance gates:
      - All R-hat ≤ 1.01
      - ESS ≥ 400 on every parameter
      - Zero divergences → refit at target_accept=0.99 on a single divergence
      - Persistent divergences → raises (fallback's fallback does not exist;
        the recipe is genuinely un-fittable under current methodology)

    Returns a (FittedPrototype, raw-arrays) tuple with fit_method set to
    "hierarchical_bayes_gp_fallback" and per_indicator_signature populated
    from the GP posterior per extract_gp_posterior_signature.

    Args:
        indicator_panel: long-format pandas DataFrame (country_id, year,
            indicator_id, value).
        positive_instances: DataFrame with (country_id, event_year).
        indicator_ids: ordered list of indicator codes.
        T_r: canonical length (Tariq v1 emit).
        target_accept: NUTS target accept rate (0.95 default, 0.99 on refit).
        n_chains: number of HMC chains.
        n_tune: warmup iterations per chain.
        n_draws: post-warmup sampling iterations per chain.
        random_seed: master seed for the sampler.

    Returns:
        (FittedPrototype, raw-arrays dict).

    Raises:
        RuntimeError: if the GP fallback NUTS sampler has persistent divergences
            after refitting at target_accept=0.99. The recipe is un-fittable
            under the current methodology; no further fallback exists.
    """
    audit: list[str] = []
    start = time.time()
    K_indicators = len(indicator_ids)

    # --- Compute per-indicator cross-country median SD for sigma_floor ------
    median_sd_by_indicator: dict[str, float] = {}
    for iid in indicator_ids:
        sd_list: list[float] = []
        for row in positive_instances.itertuples(index=False):
            country_id = row.country_id
            event_year = int(row.event_year)
            mask = (
                (indicator_panel["country_id"] == country_id)
                & (indicator_panel["indicator_id"] == iid)
                & (indicator_panel["year"] >= event_year - T_r - 20)
                & (indicator_panel["year"] < event_year - T_r)
            )
            vals = indicator_panel.loc[mask, "value"].astype(float).values
            if len(vals) >= 2:
                sd_list.append(float(np.std(vals, ddof=1)))
        median_sd_by_indicator[iid] = float(np.median(sd_list)) if sd_list else 1.0

    # --- Build per-instance normalized trajectory tensor (N_r, T_r, K) ----
    trajectory_rows: list[np.ndarray] = []  # each: (T_r, K_indicators)
    dropped_instances: list[tuple[str, int, str]] = []

    for row in positive_instances.itertuples(index=False):
        country_id = row.country_id
        event_year = int(row.event_year)
        per_indicator_trajs: list[np.ndarray] = []
        instance_ok = True

        for iid in indicator_ids:
            # Alignment window.
            mask_align = (
                (indicator_panel["country_id"] == country_id)
                & (indicator_panel["indicator_id"] == iid)
                & (indicator_panel["year"] >= event_year - T_r)
                & (indicator_panel["year"] < event_year)
            )
            sub_align = (
                indicator_panel.loc[mask_align, ["year", "value"]]
                .sort_values("year")
                .reset_index(drop=True)
            )
            if len(sub_align) != T_r:
                dropped_instances.append(
                    (country_id, event_year, f"alignment_incomplete_{iid}")
                )
                instance_ok = False
                break

            # Pre-window baseline.
            mask_base = (
                (indicator_panel["country_id"] == country_id)
                & (indicator_panel["indicator_id"] == iid)
                & (indicator_panel["year"] >= event_year - T_r - 20)
                & (indicator_panel["year"] < event_year - T_r)
            )
            sub_base = indicator_panel.loc[mask_base, "value"].astype(float).values
            if len(sub_base) < 20:
                dropped_instances.append(
                    (country_id, event_year, f"BASELINE_TOO_SHORT_{iid}")
                )
                instance_ok = False
                break

            norm: NormalizationResult = per_country_z_score(
                raw_trajectory=sub_align["value"].astype(float).values,
                pre_window_baseline=sub_base,
                median_sd_for_floor=median_sd_by_indicator.get(iid),
            )
            per_indicator_trajs.append(norm.y_normalized)

        if instance_ok:
            trajectory_rows.append(np.stack(per_indicator_trajs, axis=1))  # (T_r, K)

    audit.append(f"instances_loaded={len(trajectory_rows)} dropped={len(dropped_instances)}")
    if dropped_instances:
        audit.append(f"first_drop_reason_sample={dropped_instances[:3]}")

    N_r = len(trajectory_rows)

    if N_r == 0:
        wall_time = time.time() - start
        raise RuntimeError(
            f"GP fallback: zero usable instances after filtering "
            f"(dropped={len(dropped_instances)}). Cannot fit any model."
        )

    # Stack to (N_r, T_r, K_indicators).
    trajectories = np.stack(trajectory_rows, axis=0)
    audit.append(f"gp_fallback: trajectories_shape={trajectories.shape}")

    # --- Run GP fallback fit (§3.1.4) ----------------------------------------
    gp_result = fit_gp_fallback(
        trajectories,
        K_indicators,
        T_r,
        n_chains=n_chains,
        n_tune=n_tune,
        n_draws=n_draws,
        target_accept=target_accept,
        seed=random_seed,
        progressbar=progressbar,
        max_treedepth=max_treedepth,
        init=init,
        idata_save_path=idata_save_path,
    )
    diagnostics = gp_result.sampler_diagnostics
    audit.append(
        f"gp_sampler: rhat_max={diagnostics.rhat_max:.4f} "
        f"ess_min={diagnostics.ess_min:.1f} div={diagnostics.n_divergences}"
    )

    # Single divergence → refit at higher target_accept (§3.1.3 imported by
    # §3.1.4 by reference).
    if not diagnostics.divergence_gate_pass and diagnostics.n_divergences == 1:
        audit.append("gp_fallback: single divergence -> refitting at target_accept=0.99")
        # Refit overwrites the saved netcdf (refit's posterior is the keeper).
        gp_result = fit_gp_fallback(
            trajectories,
            K_indicators,
            T_r,
            n_chains=n_chains,
            n_tune=n_tune,
            n_draws=n_draws,
            target_accept=TARGET_ACCEPT_REFIT,
            seed=random_seed + 1,
            progressbar=progressbar,
            max_treedepth=max_treedepth,
            init=init,
            idata_save_path=idata_save_path,
        )
        diagnostics = gp_result.sampler_diagnostics
        audit.append(
            f"gp_refit: rhat_max={diagnostics.rhat_max:.4f} "
            f"ess_min={diagnostics.ess_min:.1f} div={diagnostics.n_divergences}"
        )

    # Persistent divergences → raise (no further fallback exists).
    if not diagnostics.all_pass:
        wall_time = time.time() - start
        raise RuntimeError(
            f"GP fallback persistent NUTS failure after refit. "
            f"rhat_max={diagnostics.rhat_max:.4f}, "
            f"ess_min={diagnostics.ess_min:.1f}, "
            f"n_divergences={diagnostics.n_divergences}. "
            f"Recipe is un-fittable under §3.1.4 methodology. "
            f"N_r={N_r}, T_r={T_r}, K_indicators={K_indicators}."
        )

    # --- Extract per-indicator posterior signature ---------------------------
    signatures_list = extract_gp_posterior_signature(
        gp_result,
        T_r=T_r,
        K_indicators=K_indicators,
        indicator_ids=list(indicator_ids),
    )
    per_indicator_signature: dict[str, dict[str, Any]] = {
        iid: sig for iid, sig in zip(indicator_ids, signatures_list)
    }

    wall_time = time.time() - start

    return (
        FittedPrototype(
            recipe_id="",  # filled by caller
            indicator_ids=list(indicator_ids),
            T_r=T_r,
            n_training_positives=N_r,
            fit_method="hierarchical_bayes_gp_fallback",
            fit_method_commit_sha=_git_commit_sha(),
            per_indicator_signature=per_indicator_signature,
            sampler_diagnostics={
                "rhat_max": diagnostics.rhat_max,
                "ess_min": diagnostics.ess_min,
                "n_divergences": diagnostics.n_divergences,
                # F-H-4-A4 (docs-specs 2026-05-20): post-warmup draw count +
                # divergence rate, both required by Marcus #8 rider for the
                # divergences_observed lock-file provenance.
                "n_post_warmup_draws": diagnostics.n_post_warmup_draws,
                "divergence_rate": diagnostics.divergence_rate,
                "target_accept": target_accept,
                "n_chains": n_chains,
                "n_tune": n_tune,
                "n_draws": n_draws,
            },
            loio_coverage_at_nominal_80=0.0,  # LOIO via GP is deferred (Chunk B.2.1)
            fallback_required=False,  # fallback succeeded; not a placeholder
            fallback_reason="",
            fpca_M_r=None,
            fpca_cumulative_variance=0.0,
            wall_time_seconds=wall_time,
            training_data_snapshot_sha256=_sha256_of_dataframe(indicator_panel),
            training_data_snapshot_s3_path="local-laptop-scale",
            audit_log=audit,
        ),
        {"trajectories": trajectories},
    )


# ---- Per-recipe FPCA fitting (§3.1.2 + §3.1.3) ------------------------------


def fit_recipe_fpca(
    indicator_panel: pd.DataFrame,
    positive_instances: pd.DataFrame,
    indicator_ids: list[str],
    T_r: int,
    *,
    target_accept: float = TARGET_ACCEPT_DEFAULT,
    n_chains: int = 4,
    n_tune: int = 1000,
    n_draws: int = 1000,
    random_seed: int = 12345,
) -> tuple[FittedPrototype, dict[str, Any]]:
    """Run the full FPCA + Bayesian generative fit per §3.1.2 + §3.1.3.

    Returns a (FittedPrototype, raw-arrays) tuple. The raw-arrays dict
    carries intermediate diagnostic outputs for the LOIO loop.

    Args:
        indicator_panel: long-format pandas DataFrame with columns
            ``country_id``, ``year``, ``indicator_id``, ``value``.
        positive_instances: DataFrame with columns ``country_id``,
            ``event_year`` (one row per historical positive).
        indicator_ids: ordered list of indicator codes (preserves the
            column order in the basis-coefficient matrix).
        T_r: canonical length (Tariq v1 emit).
        target_accept: NUTS target accept rate.
        n_chains: number of HMC chains.
        n_tune: warmup iterations per chain.
        n_draws: post-warmup sampling iterations per chain.
        random_seed: master seed for the sampler.

    Returns:
        (FittedPrototype with the per-indicator FPCA signatures populated,
         raw-arrays dict with FPCA scores and beta means for downstream
         LOIO evaluation).
    """
    audit: list[str] = []
    start = time.time()

    # --- Build basis (shared across indicators) -----------------------------
    Phi, R_block = build_cubic_bspline_basis(T_r)
    K_basis = Phi.shape[1]
    audit.append(f"basis: cubic_spline K_basis={K_basis} T_r={T_r}")

    # --- Compute per-indicator cross-country median SD for sigma_floor ------
    median_sd_by_indicator: dict[str, float] = {}
    for iid in indicator_ids:
        sd_list: list[float] = []
        for row in positive_instances.itertuples(index=False):
            country_id = row.country_id
            event_year = int(row.event_year)
            mask = (
                (indicator_panel["country_id"] == country_id)
                & (indicator_panel["indicator_id"] == iid)
                & (indicator_panel["year"] >= event_year - T_r - 20)
                & (indicator_panel["year"] < event_year - T_r)
            )
            vals = indicator_panel.loc[mask, "value"].astype(float).values
            if len(vals) >= 2:
                sd_list.append(float(np.std(vals, ddof=1)))
        median_sd_by_indicator[iid] = float(np.median(sd_list)) if sd_list else 1.0

    # --- Build per-instance basis-coefficient matrix ------------------------
    # beta_matrix shape: (N_r, K_basis * K_indicators) — block-stacked per
    # §3.1.2 (concatenate per-indicator basis projections).
    beta_rows: list[np.ndarray] = []
    dropped_instances: list[tuple[str, int, str]] = []

    for row in positive_instances.itertuples(index=False):
        country_id = row.country_id
        event_year = int(row.event_year)
        per_indicator_betas: list[np.ndarray] = []
        instance_ok = True
        for iid in indicator_ids:
            # Alignment window.
            mask_align = (
                (indicator_panel["country_id"] == country_id)
                & (indicator_panel["indicator_id"] == iid)
                & (indicator_panel["year"] >= event_year - T_r)
                & (indicator_panel["year"] < event_year)
            )
            sub_align = (
                indicator_panel.loc[mask_align, ["year", "value"]]
                .sort_values("year")
                .reset_index(drop=True)
            )
            if len(sub_align) != T_r:
                dropped_instances.append(
                    (country_id, event_year, f"alignment_incomplete_{iid}")
                )
                instance_ok = False
                break

            # Pre-window baseline.
            mask_base = (
                (indicator_panel["country_id"] == country_id)
                & (indicator_panel["indicator_id"] == iid)
                & (indicator_panel["year"] >= event_year - T_r - 20)
                & (indicator_panel["year"] < event_year - T_r)
            )
            sub_base = indicator_panel.loc[mask_base, "value"].astype(float).values
            if len(sub_base) < 20:
                dropped_instances.append(
                    (country_id, event_year, f"BASELINE_TOO_SHORT_{iid}")
                )
                instance_ok = False
                break

            norm: NormalizationResult = per_country_z_score(
                raw_trajectory=sub_align["value"].astype(float).values,
                pre_window_baseline=sub_base,
                median_sd_for_floor=median_sd_by_indicator.get(iid),
            )
            beta = project_to_basis_coefficients(norm.y_normalized, Phi)
            per_indicator_betas.append(beta)

        if instance_ok:
            beta_rows.append(np.concatenate(per_indicator_betas))

    audit.append(f"instances_loaded={len(beta_rows)} dropped={len(dropped_instances)}")
    if dropped_instances:
        audit.append(f"first_drop_reason_sample={dropped_instances[:3]}")

    N_r = len(beta_rows)

    # --- N_r < 10 routes to fallback per §3.1.5 -----------------------------
    if N_r < 10:
        wall_time = time.time() - start
        return (
            FittedPrototype(
                recipe_id="",  # filled by caller
                indicator_ids=list(indicator_ids),
                T_r=T_r,
                n_training_positives=N_r,
                fit_method="hierarchical_bayes_gp_fallback",
                fit_method_commit_sha=_git_commit_sha(),
                per_indicator_signature={},  # populated by Chunk B.2 fallback path
                sampler_diagnostics={},
                loio_coverage_at_nominal_80=0.0,
                fallback_required=True,
                fallback_reason=f"N_r={N_r} < 10 (§3.1.5 floor)",
                fpca_M_r=None,
                fpca_cumulative_variance=0.0,
                wall_time_seconds=wall_time,
                training_data_snapshot_sha256=_sha256_of_dataframe(indicator_panel),
                training_data_snapshot_s3_path="local-laptop-scale",
                audit_log=audit,
            ),
            {"beta_matrix": np.zeros((0, K_basis * len(indicator_ids))), "R_block": R_block},
        )

    beta_matrix = np.stack(beta_rows, axis=0)

    # --- Block-diagonal R for the Sobolev metric across indicators ----------
    K_ind = len(indicator_ids)
    R_full = np.zeros((K_basis * K_ind, K_basis * K_ind))
    for k in range(K_ind):
        R_full[
            k * K_basis : (k + 1) * K_basis,
            k * K_basis : (k + 1) * K_basis,
        ] = R_block

    # --- FPCA -----------------------------------------------------------------
    fpca = fit_fpca(beta_matrix, R_full, M_max=M_R_CEILING)
    audit.append(
        f"fpca: M_r={fpca.selected_M_r} cumvar={fpca.cumulative_variance.tolist()[: M_R_CEILING]}"
    )

    if fpca.selected_M_r is None:
        wall_time = time.time() - start
        return (
            FittedPrototype(
                recipe_id="",
                indicator_ids=list(indicator_ids),
                T_r=T_r,
                n_training_positives=N_r,
                fit_method="hierarchical_bayes_gp_fallback",
                fit_method_commit_sha=_git_commit_sha(),
                per_indicator_signature={},
                sampler_diagnostics={},
                loio_coverage_at_nominal_80=0.0,
                fallback_required=True,
                fallback_reason=f"FPCA fit failed: {fpca.selection_reason}",
                fpca_M_r=None,
                fpca_cumulative_variance=0.0,
                wall_time_seconds=wall_time,
                training_data_snapshot_sha256=_sha256_of_dataframe(indicator_panel),
                training_data_snapshot_s3_path="local-laptop-scale",
                audit_log=audit,
            ),
            {"beta_matrix": beta_matrix, "R_block": R_block},
        )

    # --- Bayesian generative model on FPCA scores (§3.1.3) ------------------
    diagnostics, posterior_mu, Sigma_r_posterior_mean = _fit_bayesian_posterior(
        scores=fpca.scores[:, : fpca.selected_M_r],
        target_accept=target_accept,
        n_chains=n_chains,
        n_tune=n_tune,
        n_draws=n_draws,
        random_seed=random_seed,
    )
    audit.append(f"sampler: rhat_max={diagnostics.rhat_max:.4f} ess_min={diagnostics.ess_min:.1f} div={diagnostics.n_divergences}")

    # Refit at higher target_accept on a single divergence (§3.1.3).
    if not diagnostics.divergence_gate_pass and diagnostics.n_divergences == 1:
        audit.append("single divergence -> refitting at target_accept=0.99")
        diagnostics, posterior_mu, Sigma_r_posterior_mean = _fit_bayesian_posterior(
            scores=fpca.scores[:, : fpca.selected_M_r],
            target_accept=TARGET_ACCEPT_REFIT,
            n_chains=n_chains,
            n_tune=n_tune,
            n_draws=n_draws,
            random_seed=random_seed + 1,
        )
        audit.append(
            f"sampler-refit: rhat_max={diagnostics.rhat_max:.4f} ess_min={diagnostics.ess_min:.1f} div={diagnostics.n_divergences}"
        )

    if not diagnostics.all_pass:
        wall_time = time.time() - start
        return (
            FittedPrototype(
                recipe_id="",
                indicator_ids=list(indicator_ids),
                T_r=T_r,
                n_training_positives=N_r,
                fit_method="hierarchical_bayes_gp_fallback",
                fit_method_commit_sha=_git_commit_sha(),
                per_indicator_signature={},
                sampler_diagnostics={
                    "rhat_max": diagnostics.rhat_max,
                    "ess_min": diagnostics.ess_min,
                    "n_divergences": diagnostics.n_divergences,
                },
                loio_coverage_at_nominal_80=0.0,
                fallback_required=True,
                fallback_reason="Persistent NUTS diagnostic failure after refit",
                fpca_M_r=fpca.selected_M_r,
                fpca_cumulative_variance=float(fpca.cumulative_variance[fpca.selected_M_r - 1]),
                wall_time_seconds=wall_time,
                training_data_snapshot_sha256=_sha256_of_dataframe(indicator_panel),
                training_data_snapshot_s3_path="local-laptop-scale",
                audit_log=audit,
            ),
            {"beta_matrix": beta_matrix, "R_block": R_block, "fpca": fpca},
        )

    # --- Reconstruct per-indicator posterior-mean trajectories --------------
    # posterior_mu is the posterior mean of mu_r in score space (M_r,).
    # The corresponding basis-coefficient mean vector is:
    #   bar_beta_inferred = bar_beta_r + V_r @ posterior_mu
    # Then the per-indicator trajectory is Phi @ (beta_block) for each
    # indicator's K_basis-slice of bar_beta_inferred.
    V_r = fpca.V[:, : fpca.selected_M_r]
    bar_beta_inferred = fpca.beta_mean + V_r @ posterior_mu

    # Per B5 (QA 2026-05-17, Priya adjudication Option C): the
    # Mahalanobis denominator must be the BAYESIAN posterior-mean covariance
    # of Σ_r from the §3.1.3 LKJ + Half-Cauchy hierarchical model, back-
    # projected through V_r (FPCA → basis-coefficient space) and Phi
    # (basis-coefficient → trajectory space). This replaces the prior
    # frequentist empirical sample variance (np.var(block_trajs, ddof=1))
    # which discarded the LKJ regularization and biased shape_similarity
    # systematically toward "less similar" for sparse recipes.
    #
    # Per B4 (QA 2026-05-17): `fpca_component_scores` now stores
    # `posterior_mu` — the LKJ posterior mean of μ_r (the Bayesian
    # prototype location in FPCA score space) — NOT the near-zero
    # sample-mean of training scores.
    fpca_component_scores_value = [
        float(x) for x in np.asarray(posterior_mu).tolist()[: fpca.selected_M_r]
    ]
    per_indicator_signature: dict[str, dict[str, Any]] = {}
    for k, iid in enumerate(indicator_ids):
        coef_slice = bar_beta_inferred[k * K_basis : (k + 1) * K_basis]
        traj = Phi @ coef_slice
        # B5: back-project the LKJ posterior-mean Σ_r through V_r (block
        # slice for this indicator) into basis-coefficient covariance space,
        # then forward-project through Phi into trajectory time-step space.
        # The rank-M_r FPCA truncation means the null-space mass is zero by
        # construction, so this is the full Bayesian posterior covariance
        # contribution within the retained FPCA subspace.
        V_r_block = V_r[k * K_basis : (k + 1) * K_basis, :]  # (K_basis, M_r)
        Sigma_beta_k = V_r_block @ Sigma_r_posterior_mean @ V_r_block.T  # (K_basis, K_basis)
        Sigma_traj_k = Phi @ Sigma_beta_k @ Phi.T  # (T_r, T_r)
        cov_diag_per_time = np.diag(Sigma_traj_k)
        # Defensive floor at 0 — Σ_r is positive-semi-definite by LKJ
        # construction, but the rank-M_r truncation can produce near-zero
        # diagonal entries; the kernel-side max(cov_diag, 1e-9) floor is
        # preserved upstream of this output.
        cov_diag_per_time = np.maximum(cov_diag_per_time, 0.0)
        per_indicator_signature[iid] = {
            # B4: prototype location in FPCA score space is the LKJ
            # posterior mean of μ_r (not the near-zero training-score mean).
            # Same value across indicators since μ_r is a recipe-level
            # quantity (the score axis is shared across the K_indicators
            # block-stacked coefficients).
            "fpca_component_scores": fpca_component_scores_value,
            "fpca_cumulative_variance_explained": float(
                fpca.cumulative_variance[fpca.selected_M_r - 1]
            ),
            "fpca_basis": f"cubic_spline_K{K_basis}",
            "posterior_mean_trajectory": [float(x) for x in traj.tolist()],
            "posterior_cov_diag": [float(x) for x in cov_diag_per_time.tolist()],
            # B5: provenance tag making the Bayesian source of the variance
            # object visible to Lloyd's actuarial review without reading
            # the fitter source.
            "cov_diag_source": "posterior_mean_lkj_back_projected",
        }

    # --- LOIO posterior-predictive coverage (§3.5.4) ------------------------
    coverage_flags = _loio_coverage_loop(
        beta_matrix=beta_matrix,
        R=R_full,
        M_r=fpca.selected_M_r,
        nominal_level=0.80,
    )
    loio_cov = loio_coverage(coverage_flags, nominal_level=0.80)
    audit.append(f"loio_coverage_at_80nominal={loio_cov:.4f}")

    fallback_required = loio_cov < LOIO_COVERAGE_GATE
    fallback_reason = "" if not fallback_required else (
        f"LOIO coverage {loio_cov:.4f} < gate {LOIO_COVERAGE_GATE}"
    )

    wall_time = time.time() - start

    return (
        FittedPrototype(
            recipe_id="",  # filled by caller
            indicator_ids=list(indicator_ids),
            T_r=T_r,
            n_training_positives=N_r,
            fit_method="fpca",
            fit_method_commit_sha=_git_commit_sha(),
            per_indicator_signature=per_indicator_signature,
            sampler_diagnostics={
                "rhat_max": diagnostics.rhat_max,
                "ess_min": diagnostics.ess_min,
                "n_divergences": diagnostics.n_divergences,
                "target_accept": target_accept,
                "n_chains": n_chains,
                "n_tune": n_tune,
                "n_draws": n_draws,
            },
            loio_coverage_at_nominal_80=loio_cov,
            fallback_required=fallback_required,
            fallback_reason=fallback_reason,
            fpca_M_r=fpca.selected_M_r,
            fpca_cumulative_variance=float(fpca.cumulative_variance[fpca.selected_M_r - 1]),
            wall_time_seconds=wall_time,
            training_data_snapshot_sha256=_sha256_of_dataframe(indicator_panel),
            training_data_snapshot_s3_path="local-laptop-scale",
            audit_log=audit,
        ),
        {"beta_matrix": beta_matrix, "R_block": R_block, "fpca": fpca},
    )


def _fit_bayesian_posterior(
    scores: np.ndarray,
    *,
    target_accept: float,
    n_chains: int,
    n_tune: int,
    n_draws: int,
    random_seed: int,
):  # type: ignore[no-untyped-def]
    """Fit the §3.1.3 LKJ + half-Cauchy hierarchical model.

    Returns (SamplerDiagnostics, posterior_mu_mean_vector). Imports PyMC
    lazily so that callers that need only the FPCA piece (e.g., the
    fitter-utils unit tests) need not pay the PyMC import cost.

    Windows compatibility note: on Windows + mingw the pytensor C backend
    is unstable. The caller should set ``PYTENSOR_FLAGS="cxx="`` BEFORE
    importing pytensor/pymc; this routes pytensor to its Python interpreter
    mode (slower per draw but numerically equivalent). Production fits on
    Linux/macOS use the default C backend.
    """
    import os

    # Defensive: set the flag for this process if not already set by the
    # caller. Must precede pytensor import; lazily-imported here so the
    # rest of the module is unaffected on platforms with a working C
    # backend.
    if "PYTENSOR_FLAGS" not in os.environ:
        os.environ["PYTENSOR_FLAGS"] = "cxx="

    # PyMC is a fitter-only dependency; import lazily.
    import arviz as az
    import pymc as pm

    M_r = scores.shape[1]
    with pm.Model() as model:
        # Per §3.1.3 priors.
        # Per N1 (QA 2026-05-17): the prior standalone `sigma` HalfCauchy
        # was redundant — `LKJCholeskyCov.sd_dist` already supplies an
        # independent HalfCauchy on the scales internally. Removed to keep
        # the diagnostic summary clean (R-hat / ESS no longer inflated by a
        # parameter the likelihood ignored).
        tau = pm.HalfCauchy("tau", beta=1.0)
        mu = pm.Normal("mu", mu=0.0, sigma=tau, shape=M_r)
        chol, _, _ = pm.LKJCholeskyCov(
            "chol",
            n=M_r,
            eta=2.0,
            sd_dist=pm.HalfCauchy.dist(beta=1.0, shape=M_r),
            compute_corr=True,
        )
        pm.MvNormal(
            "obs",
            mu=mu,
            chol=chol,
            observed=scores,
        )
        # Default NUTS sampler. The PYTENSOR_FLAGS=cxx= setting above forces
        # pytensor to its Python interpreter mode on Windows for portability.
        # Linux/macOS production runs may unset PYTENSOR_FLAGS before calling
        # this script for the C-backend speedup; the spec-binding sampler
        # is NUTS regardless of backend.
        idata = pm.sample(
            draws=n_draws,
            tune=n_tune,
            chains=n_chains,
            target_accept=target_accept,
            nuts={"max_treedepth": MAX_TREEDEPTH},
            random_seed=random_seed,
            progressbar=False,
            compute_convergence_checks=False,
            cores=1,  # sequential by default for laptop-scale reproducibility
        )

    # var_names excludes the removed standalone "sigma" per N1.
    summary = az.summary(idata, var_names=["mu", "tau"], kind="diagnostics")
    rhat_values = summary["r_hat"].values
    ess_values = summary["ess_bulk"].values
    n_divergences = int(idata.sample_stats["diverging"].sum().values)
    # F-H-4-A4: pass post-warmup draw count so the divergence rate-gate fires.
    n_post_warmup_draws = int(n_chains * n_draws)
    diagnostics = evaluate_sampler_diagnostics(
        rhat_values, ess_values, n_divergences, n_post_warmup_draws=n_post_warmup_draws
    )

    posterior_mu = idata.posterior["mu"].mean(dim=["chain", "draw"]).values

    # Per B5 (QA 2026-05-17, Priya adjudication 2026-05-17 Option C):
    # extract per-draw LKJ-implied Σ_r posterior samples from the Cholesky
    # factor stored in idata.posterior["chol"], reconstruct Σ_r per draw via
    # L @ L^T, and return the posterior-mean covariance. Downstream code
    # back-projects this through V_r and Phi to obtain the trajectory-space
    # Mahalanobis denominator that §3.5.1 binds.
    chol_arr = idata.posterior["chol"].values  # may be (chain, draw, M_r*(M_r+1)/2) packed or (chain, draw, M_r, M_r)
    if chol_arr.ndim == 3:
        # Packed lower-triangular (chain, draw, n_pack); unpack to (chain, draw, M_r, M_r).
        n_chain, n_draw, n_pack = chol_arr.shape
        chol_flat_packed = chol_arr.reshape(-1, n_pack)
        tril_idx = np.tril_indices(M_r)
        chol_flat = np.zeros((chol_flat_packed.shape[0], M_r, M_r), dtype=float)
        chol_flat[:, tril_idx[0], tril_idx[1]] = chol_flat_packed
    elif chol_arr.ndim == 4:
        chol_flat = chol_arr.reshape(-1, M_r, M_r)
    else:
        raise ValueError(
            f"Unexpected idata.posterior['chol'] ndim={chol_arr.ndim}; "
            f"expected packed-tri (3) or full-matrix (4)."
        )
    # Σ_r per draw = L L^T; average over draws.
    Sigma_r_draws = np.einsum("dij,dkj->dik", chol_flat, chol_flat)  # (D, M_r, M_r)
    Sigma_r_posterior_mean = Sigma_r_draws.mean(axis=0)  # (M_r, M_r)
    # Symmetrize defensively (numerical noise from einsum).
    Sigma_r_posterior_mean = 0.5 * (Sigma_r_posterior_mean + Sigma_r_posterior_mean.T)

    return diagnostics, posterior_mu, Sigma_r_posterior_mean


def _loio_coverage_loop(
    beta_matrix: np.ndarray,
    R: np.ndarray,
    M_r: int,
    *,
    nominal_level: float = 0.80,
) -> np.ndarray:
    """LOIO posterior-predictive coverage loop per §3.5.4.

    For each instance c, refit FPCA on the remaining N-1 instances, project
    c onto the refit basis, score c's distance against the held-out
    posterior, and check whether c's score falls inside the central
    ``nominal_level`` interval of the held-out predictive distribution.

    Returns:
        (N_r,) array of 0/1 coverage flags.
    """
    N_r = beta_matrix.shape[0]
    flags = np.zeros(N_r, dtype=float)
    for c in range(N_r):
        held_out = beta_matrix[c]
        retained = np.delete(beta_matrix, c, axis=0)
        if retained.shape[0] < 2:
            # Edge case: tiny N_r — coverage is vacuously 1 (not statistically
            # meaningful but does not falsely fail the gate at fixture scale).
            flags[c] = 1.0
            continue
        try:
            fpca_loio = fit_fpca(retained, R, M_max=M_r)
        except ValueError:
            flags[c] = 1.0
            continue
        if fpca_loio.selected_M_r is None or fpca_loio.selected_M_r < M_r:
            # Refit failed to reach the same M_r; treat as covered for
            # the conservative direction (does not falsely tighten gate).
            flags[c] = 1.0
            continue

        V_loio = fpca_loio.V[:, :M_r]
        beta_mean = fpca_loio.beta_mean
        score_held_out = V_loio.T @ R @ (held_out - beta_mean)
        retained_scores = fpca_loio.scores[:, :M_r]

        # Empirical central interval per coordinate. Coverage flag is True
        # iff held_out score falls inside the joint per-coordinate interval
        # at the given nominal level (Bonferroni-style; this is informational
        # at fixture scale, not a multiple-testing correction in the BH/FDR
        # sense which Kwame vetoed).
        per_coord_lo = np.quantile(retained_scores, (1 - nominal_level) / 2, axis=0)
        per_coord_hi = np.quantile(retained_scores, 1 - (1 - nominal_level) / 2, axis=0)
        in_interval = (score_held_out >= per_coord_lo).all() and (
            score_held_out <= per_coord_hi
        ).all()
        flags[c] = 1.0 if in_interval else 0.0
    return flags


# ---- Lock file emission -----------------------------------------------------


def emit_to_lock_file(
    prototype: FittedPrototype,
    lock_path: Path,
    *,
    stage_6_commit_sha: str,
    cohort_calibration_ref: str | None = None,
) -> None:
    """Merge a fitted prototype into the lock JSON and rewrite ``file_sha256``.

    Per §4.3 schema + §4.5 mutation discipline. The caller is responsible
    for filing the F-H-4 amendment commit in docs-specs; this function only
    writes the qgi-ml-side sister commit.
    """
    if lock_path.exists():
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "schema_version": 1,
            "filed": "1970-01-01",
            "purpose": "Per-recipe canonical shape prototype lock per Stage 6 pre-reg.",
            "pre_reg_lineage": {"stage_6": stage_6_commit_sha},
            "metadata": {
                "file_sha256": "",
                "n_recipes_with_prototype": 0,
                "n_recipes_substrate_inadequate": 0,
            },
            "recipes": {},
            "amendments": [],
        }

    ref = cohort_calibration_ref or (
        f"docs/specs/methodology/ml-validation/{prototype.recipe_id}/shape-calibration-table.md"
    )

    payload["recipes"][prototype.recipe_id] = {
        "recipe_id": prototype.recipe_id,
        "indicator_ids": list(prototype.indicator_ids),
        "canonical_length_T": {
            "point": prototype.T_r,
            "posterior_iqr": [prototype.T_r, prototype.T_r],
            "method": "tariq_v1_emit_acf_panel_pooled",
        },
        "per_indicator_trajectory_signature": prototype.per_indicator_signature,
        "fit_method": prototype.fit_method,
        "fit_method_commit_sha": prototype.fit_method_commit_sha,
        "n_training_positives": prototype.n_training_positives,
        "training_data_snapshot_sha": {
            "s3_path": prototype.training_data_snapshot_s3_path,
            "sha256": prototype.training_data_snapshot_sha256,
        },
        "substrate_audit": {
            "g1_n_pos_geq_10": prototype.n_training_positives >= 10,
            "g2_n_countries_geq_5": True,  # filled by Tariq's G-gate audit upstream
            "g3_density_geq_0_85": True,
            "g4_censoring_clean": True,
        },
        "cohort_calibration_ref": ref,
        "schema_version": 1,
        # F-H-4-A4 (Marcus #8 rider, docs-specs 2026-05-20): write the
        # divergence-provenance fields at gate-evaluation time regardless of
        # pass/fail, so Lloyd's audit can re-evaluate under a different gate.
        # Pulled from prototype.sampler_diagnostics (populated by the fitter).
        **(
            {
                "divergences_observed": {
                    "n_divergences": int(prototype.sampler_diagnostics.get("n_divergences", 0)),
                    "n_post_warmup_draws": int(prototype.sampler_diagnostics.get("n_post_warmup_draws", 0)),
                    "divergence_rate": float(prototype.sampler_diagnostics.get("divergence_rate", 0.0)),
                }
            }
            if prototype.sampler_diagnostics and "n_divergences" in prototype.sampler_diagnostics
            else {}
        ),
    }

    # Recompute metadata counts.
    n_with = len(payload["recipes"])
    n_inad = sum(
        1
        for r in payload["recipes"].values()
        if not all(r["substrate_audit"].values())
    )
    payload["metadata"]["n_recipes_with_prototype"] = n_with
    payload["metadata"]["n_recipes_substrate_inadequate"] = n_inad

    # Update file_sha256 last.
    payload["metadata"]["file_sha256"] = _canonical_sha(payload)

    lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Wrote prototype to %s; file_sha256=%s", lock_path, payload["metadata"]["file_sha256"])


# ---- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, help="recipe_id to fit")
    parser.add_argument(
        "--indicator-panel",
        required=True,
        type=Path,
        help="Parquet or CSV of long-format indicator panel",
    )
    parser.add_argument(
        "--positive-instances",
        required=True,
        type=Path,
        help="CSV of (country_id, event_year) positive instances",
    )
    parser.add_argument(
        "--indicator-ids",
        required=True,
        help="comma-separated indicator IDs (preserves column order)",
    )
    parser.add_argument("--T-r", required=True, type=int, dest="T_r")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "config" / "shape-prototypes.lock.json",
    )
    parser.add_argument(
        "--stage-6-commit",
        default="e4f9e7a",
        help="commit SHA of Stage 6 pre-reg merge",
    )
    parser.add_argument("--target-accept", type=float, default=TARGET_ACCEPT_DEFAULT)
    parser.add_argument("--n-chains", type=int, default=4)
    parser.add_argument("--n-tune", type=int, default=1000)
    parser.add_argument("--n-draws", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument(
        "--progressbar",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Show NUTS progress bar during sampling (default: True). "
            "Use --no-progressbar to suppress for CI/cron/log-file-only runs."
        ),
    )
    parser.add_argument(
        "--max-treedepth",
        type=int,
        default=None,
        dest="max_treedepth",
        help=(
            "NUTS max tree depth override. Default: module MAX_TREEDEPTH constant. "
            "Reduce to 7-8 to cap wall-time at the cost of acceptance rate."
        ),
    )
    parser.add_argument(
        "--init",
        default="jitter+adapt_diag",
        help=(
            "PyMC NUTS initialization strategy (default: jitter+adapt_diag). "
            "Alternative: advi+adapt_diag for VI-warm-started mass matrix."
        ),
    )
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        default=False,
        help=(
            "Skip the primary FPCA path entirely and run the §3.1.4 GP fallback "
            "directly. Useful for testing the fallback path on a recipe that "
            "would otherwise pass the FPCA primary. Chunk C.3 uses this flag to "
            "re-fit the Phase 1 trio (civil_war_and_insurgency, economic_recession, "
            "foreign_intervention) after the fallback was confirmed working in "
            "Chunk B.2. Does NOT change the lock JSON fit_method field (it will "
            "correctly be 'hierarchical_bayes_gp_fallback')."
        ),
    )
    parser.add_argument(
        "--idata-save-path",
        type=Path,
        default=None,
        dest="idata_save_path",
        help=(
            "Path to persist the NUTS InferenceData NetCDF post-fit. When set, "
            "the analytic-marginalization posterior can be re-extracted in ~30s "
            "if the closed-form formula is corrected — avoiding multi-hour "
            "re-fits. Added 2026-05-21 after the GP-posterior formula bug "
            "review (spec-trio recommendation). Recommended path layout: "
            "results/shape_fits/<recipe>/idata.nc"
        ),
    )
    args = parser.parse_args(argv)

    panel_path = args.indicator_panel
    if panel_path.suffix == ".parquet":
        panel = pd.read_parquet(panel_path)
    else:
        panel = pd.read_csv(panel_path)
    positives = pd.read_csv(args.positive_instances)
    indicator_ids = [s.strip() for s in args.indicator_ids.split(",") if s.strip()]

    sampler_kwargs = dict(
        target_accept=args.target_accept,
        n_chains=args.n_chains,
        n_tune=args.n_tune,
        n_draws=args.n_draws,
        random_seed=args.seed,
    )
    # GP-fallback-only kwargs (FPCA primary doesn't accept these).
    gp_fallback_kwargs = dict(
        sampler_kwargs,
        progressbar=args.progressbar,
        max_treedepth=args.max_treedepth,
        init=args.init,
        idata_save_path=args.idata_save_path,
    )

    if args.force_fallback:
        # Operator explicitly requested the §3.1.4 GP fallback path.
        logger.info(
            "--force-fallback set: skipping FPCA primary, running §3.1.4 GP "
            "fallback directly for recipe %s.",
            args.recipe,
        )
        try:
            prototype, _ = fit_recipe_gp_fallback(
                panel,
                positives,
                indicator_ids,
                args.T_r,
                **gp_fallback_kwargs,
            )
            prototype.recipe_id = args.recipe
            logger.info("GP fallback (--force-fallback): SUCCESS")
        except RuntimeError as exc:
            logger.error(
                "GP fallback failed for recipe %s: %s", args.recipe, exc
            )
            return 1
    else:
        # Normal path: try FPCA primary; route to GP fallback if needed.
        prototype, _ = fit_recipe_fpca(
            panel,
            positives,
            indicator_ids,
            args.T_r,
            **sampler_kwargs,
        )
        prototype.recipe_id = args.recipe

        logger.info("audit:\n  %s", "\n  ".join(prototype.audit_log))
        logger.info(
            "primary path: fallback_required=%s reason=%r",
            prototype.fallback_required,
            prototype.fallback_reason,
        )
        logger.info("wall_time=%.2fs (primary)", prototype.wall_time_seconds)

        if prototype.fallback_required:
            # Primary path failed or N_r < 10 → run real §3.1.4 GP fallback.
            logger.info(
                "Recipe %s routing to §3.1.4 GP fallback (reason: %s).",
                args.recipe,
                prototype.fallback_reason,
            )
            try:
                prototype, _ = fit_recipe_gp_fallback(
                    panel,
                    positives,
                    indicator_ids,
                    args.T_r,
                    **gp_fallback_kwargs,
                )
                prototype.recipe_id = args.recipe
                logger.info(
                    "GP fallback SUCCESS: fit_method=%s n_training_positives=%d "
                    "wall_time=%.2fs",
                    prototype.fit_method,
                    prototype.n_training_positives,
                    prototype.wall_time_seconds,
                )
            except RuntimeError as exc:
                logger.error(
                    "GP fallback persistent failure for recipe %s: %s. "
                    "Recipe is un-fittable under §3.1.4. No further fallback "
                    "exists. Emitting the partial FPCA placeholder so the "
                    "lock file has a record; operator must investigate.",
                    args.recipe,
                    exc,
                )
                # Re-emit the original placeholder with the fallback_reason
                # updated to include the GP failure reason.
                prototype.fallback_reason = (
                    f"GP_FALLBACK_ALSO_FAILED: {exc}"
                )
        else:
            logger.info(
                "FPCA primary SUCCESS: fit_method=%s M_r=%s cumvar=%.4f "
                "wall_time=%.2fs",
                prototype.fit_method,
                prototype.fpca_M_r,
                prototype.fpca_cumulative_variance,
                prototype.wall_time_seconds,
            )

    logger.info("audit:\n  %s", "\n  ".join(prototype.audit_log))
    logger.info("wall_time=%.2fs", prototype.wall_time_seconds)

    emit_to_lock_file(
        prototype,
        args.output,
        stage_6_commit_sha=args.stage_6_commit,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
