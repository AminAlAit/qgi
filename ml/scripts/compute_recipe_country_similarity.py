"""Compute country × recipe similarity scores for the risk-metric pipeline.

Per the risk-metric design v1 (3-Reviewer ratified 2026-05-22):
  docs/specs/internal/ops/ml-track/risk-metric-design-v1.md

Implements:
  - Cosine similarity on per-year full-window trajectory profiles (Miriam M14-R3)
  - Weighted ARITHMETIC mean aggregation (NOT geometric; per ML/stats synthesis)
  - SHAP-derived importance weights (per Miriam M14-R5; loaded from
    extract_shap_importances.py output)
  - Top-K trajectory overlay charts archived (Miriam M14-R4)
  - Per-cohort similarity distribution reporting (validation transparency)
  - Z-score distribution pre-baking (Kwame production-ML rider)

Risk scoring:
  - Cosine S(C, R) ∈ [-1, 1] mapped linearly to [0, 100]
  - 3-zone bands per Product/UX synthesis: LOW (<40), MODERATE (40-65), HIGH (>=65)
  - "Below 50 = trajectory moving away from crisis profile" copy (R10 continuity)

Run-time: <5min laptop per recipe × all countries.

Usage:
    python scripts/compute_recipe_country_similarity.py \\
        --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --shap-importances qgi-data/reference/shap-importances-foreign_intervention.json \\
        --output-dir qgi-data/reference/ \\
        --evaluation-year 2021

Output:
    recipe-similarity-scores-{recipe-id}-{year}.json   (per-country scores)
    panel-wide-z-distribution-{year}.parquet            (z-score pre-bake)
    audit-charts/{recipe-id}/                            (top-K trajectory overlays)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent


# Per design v1 §"Frontend quintile bands":
RISK_ZONE_LOW_MAX = 40       # raw < 40 → LOW
RISK_ZONE_MODERATE_MAX = 65  # 40 <= raw < 65 → MODERATE; raw >= 65 → HIGH


# ---- Nowcast fill (LOCF) constants — #111 fill contract ------------------
# Variance-graded Last-Observation-Carried-Forward for the TRAILING gap between
# a country's last observed year and the scoring frontier (D2). Interior/leading
# gaps keep the historical mean(0) treatment (unchanged) so historical eval years
# (validation/backtest/LOCO) are byte-identical to the prior behaviour — this is
# what auto-satisfies the JH-R1 firewall (no filled rows in any training fold).
# Band fans out as a random walk in z-space: half(h) = Z_CRIT · sd(Δz) · √h,
# mirroring fit_projection_models._persistence_forecast (sigma_h = sigma·√h).
# Ratified: Majles v2 fill ruling (agent a73e68bc73cc08310) + Opus nowcast consult
# (agent a19e0338c9a7f542c), founder decisions D1/D2/D3 + fill-all-no-skip, 2026-05-25.
_Z_CRIT = 1.96
_FLAT_SERIES_FLOOR_Z = 1.0    # min sd(Δz) for flat series → fill never claims 0 uncertainty
_FILL_MC_DRAWS = 2000         # MC draws to propagate fill band → score band (Majles: M>=2000)
_MAX_FILL_HORIZON_YEARS = 5   # T-R1 nowcast-gap soft cap: beyond this the anchor is "stale"


@dataclass
class CountryTrajectory:
    """Z-scored W-year scoring trajectory for one (country, indicator) + fill provenance.

    z                  : (W,) z-vector — observed where present, LOCF-carried across the
                         trailing nowcast gap, 0 for interior/leading absences.
    observed_mask      : (W,) True where a real observed value exists.
    filled_mask        : (W,) True for TRAILING-LOCF nowcast points (the is_predicted tail).
    band_half_z        : (W,) per-point half-width in z (Z_CRIT·sd(Δz)·√h); >0 only on the tail.
    n_filled           : number of trailing-LOCF points (years carried forward).
    last_observed_year : last genuinely observed year inside the window (None if none).
    frontier_year      : the scoring frontier (evaluation_year - 1).
    stale_anchor       : True if the nowcast gap exceeds _MAX_FILL_HORIZON_YEARS (T-R1).
    """
    z: np.ndarray
    observed_mask: np.ndarray
    filled_mask: np.ndarray
    band_half_z: np.ndarray
    n_filled: int
    last_observed_year: int | None
    frontier_year: int
    stale_anchor: bool = False


def _drop_predicted(panel: pd.DataFrame) -> pd.DataFrame:
    """D1: keep observed rows only. Production S3 panels carry an `is_predicted`
    boolean (ETS nowcast fill) which we DISCARD and re-fill ourselves via LOCF.
    No-op on frozen laptop panels that lack the column."""
    if "is_predicted" in panel.columns:
        return panel[~panel["is_predicted"].astype(bool)].copy()
    return panel


def _zone_of(risk_score: float) -> str:
    """Map a 0-100 risk score to its zone (single source of truth)."""
    if risk_score < RISK_ZONE_LOW_MAX:
        return "LOW"
    if risk_score < RISK_ZONE_MODERATE_MAX:
        return "MODERATE"
    return "HIGH"


# ---- Panel-wide z-score pre-baking (Kwame production-ML rider) -----------


def prebake_zscore_distribution(panel_dir: Path, selected_indicators: list[str],
                                 evaluation_year: int) -> dict[str, dict[str, float]]:
    """Pre-bake panel-wide mean + std for each indicator at evaluation_year - 1.

    Per Kwame production-ML rider: avoid on-the-fly recomputation at query time.
    """
    distribution = {}
    for ind in selected_indicators:
        panel = _drop_predicted(drv.load_panel(ind, panel_dir))
        panel_at_year = panel[panel["year"] == evaluation_year - 1]["value"].dropna()
        if len(panel_at_year) < 10:
            distribution[ind] = {
                "mean": float("nan"),
                "std": float("nan"),
                "n_countries": len(panel_at_year),
                "fallback_used": True,
                "note": "Fewer than 10 countries; per-country baseline fallback in extract_features",
            }
        else:
            distribution[ind] = {
                "mean": float(panel_at_year.mean()),
                "std": float(panel_at_year.std() or 1.0),
                "n_countries": int(len(panel_at_year)),
                "fallback_used": False,
            }
    return distribution


# ---- Country profile extraction -----------------------------------------


def extract_country_trajectory(panel: pd.DataFrame, country: str, evaluation_year: int,
                                window: int, ind_dist: dict[str, float] | None = None,
                                return_provenance: bool = False, forbid_fill: bool = False):
    """Extract z-scored trajectory T_C[t] for one country / one indicator across W years.

    By default returns the (W,) z-vector (back-compat with every existing caller),
    OR None if insufficient data. With ``return_provenance=True`` returns a
    :class:`CountryTrajectory` carrying the observed/filled masks + nowcast band,
    OR None if insufficient data.

    Fill contract (#111, Majles v2 + Opus nowcast consult, 2026-05-25):
      The TRAILING gap between the country's last observed year and the scoring
      frontier (``evaluation_year - 1``) is filled by LOCF — carry the last
      observed z forward — and flagged as predicted, with a random-walk band that
      fans out as ``Z_CRIT · sd(Δz) · √h``. Interior/leading gaps keep the
      historical mean(0) treatment, so historical eval years (where the frontier
      is already observed → no trailing gap) are byte-identical to prior behaviour.
    """
    cdf = panel[panel["country"] == country]
    if len(cdf) == 0:
        return None
    series = cdf.set_index("year")["value"].sort_index()
    # Reindex to full window, leaving gaps as NaN
    full_index = pd.RangeIndex(evaluation_year - window, evaluation_year)
    window_full = series.reindex(full_index)

    observed_mask = np.isfinite(window_full.values)
    if int(observed_mask.sum()) < max(3, window // 3):
        return None

    # Apply pre-baked panel-wide z-score (or per-country baseline fallback)
    if ind_dist is None or ind_dist.get("fallback_used"):
        baseline = series.loc[max(evaluation_year - 25, int(series.index.min())) : evaluation_year - 1].dropna()
        mu = float(baseline.mean()) if len(baseline) > 0 else 0.0
        sd = float(baseline.std() or 1.0)
    else:
        mu = float(ind_dist["mean"])
        sd = float(ind_dist["std"])
    if not np.isfinite(sd) or sd == 0.0:
        sd = 1.0

    # Z-score; interior/leading absences → 0 (historical behaviour, unchanged)
    z = (window_full.values - mu) / sd
    z = np.where(np.isfinite(z), z, 0.0)

    # ---- trailing LOCF nowcast fill (the only behaviour change vs v1) -------
    years = np.asarray(full_index)
    filled_mask = np.zeros(window, dtype=bool)
    band_half_z = np.zeros(window, dtype=float)
    last_obs_year: int | None = int(years[observed_mask].max()) if observed_mask.any() else None
    stale_anchor = False

    if last_obs_year is not None and last_obs_year < evaluation_year - 1:
        if forbid_fill:
            # JH-R1 HARD FIREWALL pre-flight: callers in any training / LOCO / OOT /
            # calibration fold pass forbid_fill=True; a trailing gap there means a
            # filled row would enter a fold, so fail LOUDLY rather than silently fill.
            raise RuntimeError(
                f"JH-R1 firewall: trailing nowcast fill would activate for '{country}' at "
                f"eval_year={evaluation_year} (last observed {last_obs_year}) but forbid_fill=True. "
                f"No filled rows may enter a training/validation fold."
            )
        # sd of first-differences in z-space. We deliberately estimate it over the
        # country's FULL observed history (≤ frontier, no future leakage) rather than
        # window-local: governance indicators are near-random-walks, so the diff SD is
        # ~stationary and the longer sample is the more stable estimator (Opus nowcast
        # consult). Mirrors fit_projection_models._persistence_forecast (np.std, ddof=0).
        z_hist = (series.loc[: evaluation_year - 1].dropna().to_numpy() - mu) / sd
        sd_dz = float(np.std(np.diff(z_hist))) if len(z_hist) >= 2 else 0.0
        if not np.isfinite(sd_dz) or sd_dz < 1e-9:
            sd_dz = _FLAT_SERIES_FLOOR_Z
        last_obs_idx = int(np.flatnonzero(years == last_obs_year)[0])
        fill_idx = np.arange(last_obs_idx + 1, window)
        z[fill_idx] = z[last_obs_idx]             # carry last observed forward
        filled_mask[fill_idx] = True
        h_arr = (years[fill_idx] - last_obs_year).astype(float)   # horizon 1, 2, 3, ...
        band_half_z[fill_idx] = _Z_CRIT * sd_dz * np.sqrt(h_arr)
        stale_anchor = (evaluation_year - 1 - last_obs_year) > _MAX_FILL_HORIZON_YEARS

    if not return_provenance:
        return z
    return CountryTrajectory(
        z=z, observed_mask=observed_mask, filled_mask=filled_mask,
        band_half_z=band_half_z, n_filled=int(filled_mask.sum()),
        last_observed_year=last_obs_year, frontier_year=evaluation_year - 1,
        stale_anchor=stale_anchor,
    )


# ---- Similarity computation (cosine + arithmetic mean) -------------------


def cosine_similarity(v1: np.ndarray, v2: np.ndarray, eps: float = 1e-9) -> float:
    """Cosine similarity in [-1, 1]. Returns 0 for zero vectors."""
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 < eps or norm2 < eps:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


def compute_country_recipe_similarity(country_trajectories: dict[str, np.ndarray],
                                       recipe_canonical: dict[str, np.ndarray],
                                       shap_weights: dict[str, float]) -> dict[str, Any]:
    """Compute weighted-arithmetic-mean cosine similarity for one (country, recipe).

    country_trajectories: {indicator_id: (W,) z-score vector}
    recipe_canonical: {indicator_id: (W,) canonical z-score vector}
    shap_weights: {indicator_id: normalized SHAP weight}

    Returns dict with cosine per-indicator + weighted aggregate + risk score.
    """
    per_indicator_cosines = {}
    for ind, weight in shap_weights.items():
        T_C = country_trajectories.get(ind)
        T_R = recipe_canonical.get(ind)
        if T_C is None or T_R is None:
            per_indicator_cosines[ind] = {
                "cosine": None,
                "weight": float(weight),
                "weighted_contribution": 0.0,
                "missing_reason": "missing country or canonical trajectory",
            }
            continue
        # Align dimensions (truncate to shorter if mismatch — both should be W)
        m = min(len(T_C), len(T_R))
        cos = cosine_similarity(T_C[:m], T_R[:m])
        per_indicator_cosines[ind] = {
            "cosine": float(cos),
            "weight": float(weight),
            "weighted_contribution": float(weight * cos),
        }

    # Weighted arithmetic mean
    contributions = [pi["weighted_contribution"] for pi in per_indicator_cosines.values()]
    total_weight = sum(shap_weights[ind] for ind, pi in per_indicator_cosines.items() if pi.get("cosine") is not None)
    if total_weight > 0:
        S = sum(contributions) / total_weight
    else:
        S = 0.0
    # Map [-1, 1] → [0, 100]
    risk_score = 100.0 * (S + 1.0) / 2.0
    # Zone
    if risk_score < RISK_ZONE_LOW_MAX:
        zone = "LOW"
        zone_label = "trajectory diverges from crisis profile"
    elif risk_score < RISK_ZONE_MODERATE_MAX:
        zone = "MODERATE"
        zone_label = "partial alignment with crisis profile"
    else:
        zone = "HIGH"
        zone_label = "trajectory aligns with crisis profile"

    return {
        "cosine_similarity_S": float(S),
        "risk_score": float(risk_score),
        "zone": zone,
        "zone_label": zone_label,
        "per_indicator": per_indicator_cosines,
        "aggregation_method": "weighted_arithmetic_mean (SHAP weights; per ML/stats synthesis 2026-05-22)",
    }


# ---- Fill-aware scoring: observed-only diagnostic + MC nowcast band -------


def _observed_only_similarity(country_trajectories: dict[str, "CountryTrajectory"],
                              recipe_canonical: dict[str, np.ndarray],
                              shap_weights: dict[str, float]) -> dict[str, Any]:
    """Recompute the weighted-cosine score using ONLY genuinely-observed positions
    per indicator (drops the LOCF-filled tail + absences). Diagnostic for the
    K-R1 'HIGH must not fire on the filled tail alone' flag."""
    contribs = 0.0
    tot_weight = 0.0
    for ind, weight in shap_weights.items():
        t = country_trajectories.get(ind)
        T_R = recipe_canonical.get(ind)
        if t is None or T_R is None:
            continue
        m = min(len(t.observed_mask), len(T_R))
        sel = t.observed_mask[:m]
        if int(sel.sum()) < 2:           # need ≥2 observed points for a meaningful cosine
            continue
        cos = cosine_similarity(t.z[:m][sel], np.asarray(T_R)[:m][sel])
        contribs += float(weight) * cos
        tot_weight += float(weight)
    S = (contribs / tot_weight) if tot_weight > 0 else 0.0
    risk = 100.0 * (S + 1.0) / 2.0
    return {"cosine_S": float(S), "risk_score": float(risk), "zone": _zone_of(risk)}


def compute_country_recipe_similarity_with_fill(
        country_trajectories: dict[str, "CountryTrajectory"],
        recipe_canonical: dict[str, np.ndarray],
        shap_weights: dict[str, float],
        mc_draws: int = _FILL_MC_DRAWS,
        seed: int = 12345) -> dict[str, Any]:
    """Point score (unchanged) + a ``fill`` block: provenance, observed-only
    diagnostic, MC-propagated nowcast band, and the K-R1 HIGH-depends-on-fill flag.

    country_trajectories: {indicator_id: CountryTrajectory}. The point estimate is
    byte-identical to compute_country_recipe_similarity({ind: t.z}) so all existing
    consumers see the same risk_score; the fill metadata is purely additive.
    """
    z_by_ind = {ind: t.z for ind, t in country_trajectories.items()}
    base = compute_country_recipe_similarity(z_by_ind, recipe_canonical, shap_weights)
    point_zone = base["zone"]
    point_score = base["risk_score"]

    obs_only = _observed_only_similarity(country_trajectories, recipe_canonical, shap_weights)

    total_filled = int(sum(t.n_filled for t in country_trajectories.values()))
    any_stale = any(t.stale_anchor for t in country_trajectories.values())

    # ---- MC-propagate the per-point z band → score band (Majles M≥2000) -----
    if total_filled > 0 and mc_draws > 0:
        rng = np.random.default_rng(seed)
        inds = list(country_trajectories.keys())
        scores = np.empty(mc_draws, dtype=float)
        # TODO(perf, #110): vectorize the MC draw — pre-draw an (M, n_filled) noise
        # matrix per indicator instead of this per-draw Python loop.
        for d in range(mc_draws):
            draw = {}
            for ind in inds:
                t = country_trajectories[ind]
                zz = t.z.copy()
                if t.n_filled > 0:
                    # Perturb ONLY the filled tail; observed positions stay exact
                    # (no zero-variance draws, no risk of noise leaking to observed).
                    fm = t.filled_mask
                    sigma = t.band_half_z[fm] / _Z_CRIT      # half_width = Z_CRIT·sigma
                    zz[fm] = zz[fm] + rng.normal(0.0, 1.0, size=int(fm.sum())) * sigma
                draw[ind] = zz
            scores[d] = compute_country_recipe_similarity(draw, recipe_canonical, shap_weights)["risk_score"]
        fill_band = {
            "ci80_lo": float(np.percentile(scores, 10.0)),
            "ci80_hi": float(np.percentile(scores, 90.0)),
            "ci95_lo": float(np.percentile(scores, 2.5)),
            "ci95_hi": float(np.percentile(scores, 97.5)),
            "mc_mean": float(scores.mean()),
            "mc_std": float(scores.std()),
            "zone_stability_pct": float(100.0 * np.mean([_zone_of(s) == point_zone for s in scores])),
            "mc_draws": int(mc_draws),
        }
    else:
        fill_band = {
            "ci80_lo": point_score, "ci80_hi": point_score,
            "ci95_lo": point_score, "ci95_hi": point_score,
            "mc_mean": point_score, "mc_std": 0.0,
            "zone_stability_pct": 100.0, "mc_draws": 0,
        }

    # K-R1: a country whose HIGH depends on the filled tail must be flagged and
    # must NOT auto-publish HIGH (also blocked when the anchor is stale, T-R1).
    high_depends_on_fill = (point_zone == "HIGH" and obs_only["zone"] != "HIGH")
    auto_publish_high = (point_zone == "HIGH" and not high_depends_on_fill and not any_stale)

    base["fill"] = {
        "is_predicted": total_filled > 0,                    # M-R1 provenance flag
        "n_filled_total": total_filled,
        "per_indicator": {
            ind: {
                "n_filled": int(t.n_filled),
                "last_observed_year": t.last_observed_year,
                "frontier_year": t.frontier_year,
                "stale_anchor": bool(t.stale_anchor),
            }
            for ind, t in country_trajectories.items()
        },
        "observed_only_risk_score": obs_only["risk_score"],
        "observed_only_zone": obs_only["zone"],
        "fill_band": fill_band,
        "high_depends_on_fill": bool(high_depends_on_fill),  # K-R1
        "auto_publish_high": bool(auto_publish_high),        # K-R1
        "stale_anchor": bool(any_stale),                     # T-R1 nowcast-gap cap
    }
    return base


# ---- Top-K trajectory overlay charts (Miriam M14-R4 BINDING) --------------


def plot_trajectory_overlay(country: str, recipe_id: str, evaluation_year: int,
                             country_trajectories: dict[str, np.ndarray],
                             recipe_canonical: dict[str, np.ndarray],
                             save_path: Path, risk_score: float) -> bool:
    """Per Miriam M14-R4 BINDING: archived overlay chart per (country, recipe) pair
    for top-K results. Indicator-by-indicator overlay: country current trajectory
    vs canonical pre-crisis profile."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        inds = list(recipe_canonical.keys())
        n_inds = len(inds)
        fig, axes = plt.subplots(n_inds, 1, figsize=(10, 2.5 * n_inds), squeeze=False)
        for k, ind in enumerate(inds):
            ax = axes[k, 0]
            T_R = recipe_canonical[ind]
            traj = country_trajectories.get(ind)
            # Accept either a plain (W,) z-vector or a CountryTrajectory (provenance).
            T_C = traj.z if isinstance(traj, CountryTrajectory) else traj
            filled = traj.filled_mask if isinstance(traj, CountryTrajectory) else None
            ax.plot(T_R, label="Canonical (pre-crisis)", color="red", linewidth=2)
            if T_C is not None:
                m = min(len(T_C), len(T_R))
                # M-R2: render the observed run solid and the LOCF-filled tail dashed.
                if filled is not None and bool(filled[:m].any()):
                    first_fill = int(np.flatnonzero(filled[:m])[0])
                    ax.plot(range(first_fill + 1), T_C[:first_fill + 1],
                            label=f"{country} (observed)", color="blue", linewidth=2)
                    ax.plot(range(first_fill, m), T_C[first_fill:m],
                            label=f"{country} (carried forward)", color="blue",
                            linewidth=2, linestyle="--", alpha=0.7)
                else:
                    ax.plot(T_C[:m], label=f"{country} (observed)", color="blue", linewidth=2)
            ax.axhline(0, color="grey", linewidth=0.5, alpha=0.5)
            ax.set_title(f"{ind} — z-score trajectory")
            ax.set_xlabel("years before evaluation")
            ax.set_ylabel("z-score")
            ax.legend(fontsize=8)
            ax.grid(alpha=0.2)
        fig.suptitle(f"{country} vs {recipe_id} (risk_score={risk_score:.1f}; eval_year={evaluation_year})",
                     fontsize=12, y=1.0 + 0.02 / n_inds)
        plt.tight_layout()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=70, bbox_inches="tight")
        plt.close()
        return True
    except Exception as e:
        print(f"WARNING: chart generation failed for {country}/{recipe_id}: {e}")
        return False


# ---- Main orchestrator ---------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-id", required=True)
    parser.add_argument("--walk-summary", type=Path, required=True)
    parser.add_argument("--shap-importances", type=Path, required=True,
                        help="Path to shap-importances-{recipe-id}.json from extract_shap_importances.py")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--panel-dir", type=Path, default=REPO_ROOT / "data" / "parquet_panels")
    parser.add_argument("--evaluation-year", dest="evaluation_year_raw", default="auto",
                        help="Scoring frontier: an int year, or 'auto' (default) = max observed "
                             "year + 1 across the recipe's indicators (D2). The canonical is ALWAYS "
                             "built at historical event years (observed); only the scoring trajectory "
                             "is LOCF-filled to this frontier.")
    parser.add_argument("--top-k-charts", type=int, default=10,
                        help="Generate trajectory overlay charts for top-K highest-similarity countries (Miriam M14-R4)")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load walk descriptive emit
    with open(args.walk_summary, encoding="utf-8") as f:
        walk = json.load(f)
    assert walk["recipe_id"] == args.recipe_id

    selected = walk["greedy_outer_loop"]["selected_indicators"]
    chosen_window = walk["greedy_outer_loop"]["chosen_window"]
    print(f"Recipe: {args.recipe_id} | indicators: {selected} | window: {chosen_window}y | eval_year: {args.evaluation_year_raw}")

    # Load SHAP importances (Miriam M14-R5 BINDING)
    with open(args.shap_importances, encoding="utf-8") as f:
        shap_data = json.load(f)
    shap_weights = shap_data["shap_importance_normalized"]
    assert set(shap_weights.keys()) == set(selected), (
        f"SHAP indicators {list(shap_weights.keys())} != walk selected {selected}"
    )

    # Load panels; D1: discard ETS-predicted rows (we re-fill the tail via LOCF ourselves).
    print("Loading panels (observed rows only; any ETS-predicted rows discarded)...")
    panels = {ind: _drop_predicted(drv.load_panel(ind, args.panel_dir)) for ind in selected}

    # D2: resolve the scoring frontier. The canonical stays at historical event years
    # (observed); only the scoring trajectory is LOCF-filled forward to this frontier.
    if str(args.evaluation_year_raw).lower() == "auto":
        max_obs = max(int(p.loc[p["value"].notna(), "year"].max()) for p in panels.values())
        evaluation_year = max_obs + 1
        print(f"  Auto scoring frontier: max observed year={max_obs} -> evaluation_year={evaluation_year}")
    else:
        evaluation_year = int(args.evaluation_year_raw)
        print(f"  Explicit evaluation_year={evaluation_year}")
    args.evaluation_year = evaluation_year

    # Pre-bake panel-wide z-distribution (Kwame production-ML rider)
    print("Pre-baking panel-wide z-score distribution...")
    z_dist = prebake_zscore_distribution(args.panel_dir, selected, evaluation_year)
    z_dist_path = args.output_dir / f"panel-wide-z-distribution-{evaluation_year}.json"
    z_dist_path.write_text(json.dumps({
        "evaluation_year": evaluation_year,
        "indicators": z_dist,
        "purpose": "Pre-baked panel-wide z-score distribution per Kwame production-ML rider on risk-metric design v1.",
    }, indent=2))
    print(f"  Wrote {z_dist_path}")

    # Load canonical trajectory signature (observed event-year windows only — JH-R1 firewall)
    print("Loading canonical recipe trajectory signatures (observed only)...")
    recipe_canonical = build_canonical_profile_from_walk(walk, panels, chosen_window, selected)

    # Extract country trajectories for ALL countries in panel
    print(f"Extracting country trajectories at frontier year {evaluation_year}...")
    all_countries: set[str] = set()
    for ind in selected:
        all_countries |= set(panels[ind]["country"].dropna().unique())
    print(f"  {len(all_countries)} candidate countries in panel")

    # Compute similarity for each country (fill-aware: provenance + nowcast band)
    print("Computing similarities (LOCF nowcast fill + MC band)...")
    results: dict[str, dict] = {}
    n_with_full_data = 0
    n_with_any_fill = 0
    n_high_depends_on_fill = 0
    for country in sorted(all_countries):
        country_traj: dict[str, CountryTrajectory] = {}
        for ind in selected:
            t = extract_country_trajectory(panels[ind], country, evaluation_year, chosen_window,
                                            ind_dist=z_dist[ind], return_provenance=True)
            if t is not None:
                country_traj[ind] = t
        if len(country_traj) < len(selected):
            continue  # Skip countries without full indicator coverage
        n_with_full_data += 1
        sim = compute_country_recipe_similarity_with_fill(country_traj, recipe_canonical, shap_weights)
        if sim["fill"]["is_predicted"]:
            n_with_any_fill += 1
        if sim["fill"]["high_depends_on_fill"]:
            n_high_depends_on_fill += 1
        results[country] = sim
    print(f"  {n_with_full_data} countries scored | {n_with_any_fill} used nowcast fill | "
          f"{n_high_depends_on_fill} HIGH-depends-on-fill (flagged, no auto-publish)")

    # Sort by risk_score and tag top-K
    sorted_countries = sorted(results.keys(), key=lambda c: -results[c]["risk_score"])
    top_k = sorted_countries[:args.top_k_charts]

    # Generate top-K trajectory overlay charts (Miriam M14-R4 BINDING)
    print(f"Generating top-{args.top_k_charts} trajectory overlay charts (Miriam M14-R4)...")
    chart_dir = args.output_dir / "audit-charts" / args.recipe_id
    chart_dir.mkdir(parents=True, exist_ok=True)
    n_charts_ok = 0
    for country in top_k:
        country_traj = {
            ind: extract_country_trajectory(panels[ind], country, evaluation_year, chosen_window,
                                            ind_dist=z_dist[ind], return_provenance=True)
            for ind in selected
        }
        chart_path = chart_dir / f"{country.replace(' ', '_')}-vs-{args.recipe_id}.png"
        ok = plot_trajectory_overlay(country, args.recipe_id, evaluation_year,
                                     country_traj, recipe_canonical, chart_path,
                                     results[country]["risk_score"])
        if ok:
            n_charts_ok += 1
            results[country]["audit_chart_path"] = str(chart_path)
    print(f"  {n_charts_ok}/{len(top_k)} charts saved")

    # Final output JSON
    output = {
        "schema_version": 2,
        "recipe_id": args.recipe_id,
        "evaluation_year": evaluation_year,
        "scoring_frontier_year": evaluation_year - 1,   # last year scored (filled if needed)
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "scoring_metric": "cosine_arithmetic_mean_shap_weighted_v2_locf_fill",
        "fill_contract": {
            "method": "variance_graded_LOCF_trailing_gap",
            "band": "horizon_fanning_random_walk_z: half(h) = 1.96 * sd(dz) * sqrt(h)",
            "flat_series_floor_z": _FLAT_SERIES_FLOOR_Z,
            "max_fill_horizon_years": _MAX_FILL_HORIZON_YEARS,
            "mc_draws": _FILL_MC_DRAWS,
            "firewall": "canonical built from observed event-year windows only (JH-R1)",
            "provenance": "per-country fill block carries is_predicted + observed_only_score + zone_stability (M-R1/M-R2/K-R1/T-R1)",
            "ratified": "Majles v2 fill ruling (a73e68bc73cc08310) + Opus nowcast consult (a19e0338c9a7f542c), 2026-05-25",
        },
        "binding_provenance": {
            "design_v1": "docs/specs/internal/ops/ml-track/risk-metric-design-v1.md (3-Reviewer ratified 2026-05-22)",
            "miriam_m14_r3": "Per-year full-window granularity (cosine on (W,) vectors); per-tertile diagnostic-only",
            "miriam_m14_r5": "SHAP-derived importances (NOT raw XGBoost feature_importances_)",
            "miriam_m14_r4": f"Top-{args.top_k_charts} trajectory overlay charts archived at audit-charts/{args.recipe_id}/",
            "ml_stats_synthesis": "Arithmetic mean aggregation (not geometric); preserves oppositional cosine signal",
            "kwame_prebake": "Panel-wide z-score distribution pre-baked at panel-wide-z-distribution.json",
        },
        "selected_indicators": selected,
        "chosen_window": chosen_window,
        "shap_importance_normalized": shap_weights,
        "n_countries_scored": n_with_full_data,
        "n_countries_with_fill": n_with_any_fill,
        "n_high_depends_on_fill": n_high_depends_on_fill,
        "scores": results,
        "top_k_for_audit_charts": top_k,
    }

    out_path = args.output_dir / f"recipe-similarity-scores-{args.recipe_id}-{evaluation_year}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")

    # Print top-10 summary
    print()
    print(f"=== Top-10 similarity for {args.recipe_id} (frontier={evaluation_year - 1}) ===")
    for country in sorted_countries[:10]:
        r = results[country]
        f = r["fill"]
        tag = ""
        if f["high_depends_on_fill"]:
            tag = "  [HIGH depends on fill — no auto-publish]"
        elif f["is_predicted"]:
            tag = f"  [+{f['n_filled_total']} filled pts; stability={f['fill_band']['zone_stability_pct']:.0f}%]"
        print(f"  {country:30s} risk={r['risk_score']:.1f}  {r['zone']:8s}  cos={r['cosine_similarity_S']:+.4f}{tag}")

    return 0


def build_canonical_profile_from_walk(walk: dict, panels: dict[str, pd.DataFrame],
                                       chosen_window: int, selected: list[str],
                                       max_year: int | None = None) -> dict[str, np.ndarray]:
    """Build the canonical T_R[i, t] for each selected indicator.

    Per design v1: the recipe canonical profile is the AVERAGE z-scored trajectory
    across all positive instances at their event-year-minus-1.

    Per QA PR#95 B2 (validation harness fix): `max_year` parameter enables
    proper OOT holdout — when called from Validation 4, pass `max_year=2004` so
    the canonical profile is derived from pre-2005 positives only and the 2005+
    holdout positives are genuinely unseen. Production calls leave `max_year=None`
    to use all positives.
    """
    recipe_id = walk["recipe_id"]
    pos = pd.read_csv(REPO_ROOT / "data" / "shape_inputs_v2" / recipe_id / "positives.csv")
    pos["country"] = pos["country_id"].apply(drv.normalize_country_id)
    pos = pos.rename(columns={"event_year": "year"})
    if max_year is not None:
        pos = pos[pos["year"] <= max_year]

    canonical: dict[str, np.ndarray] = {}
    for ind in selected:
        panel = panels[ind]
        trajectories = []
        for _, row in pos.iterrows():
            country = str(row["country"])
            event_year = int(row["year"])
            cdf = panel[panel["country"] == country]
            if len(cdf) == 0:
                continue
            series = cdf.set_index("year")["value"]
            window_data = series.loc[event_year - chosen_window : event_year - 1]
            full_index = pd.RangeIndex(event_year - chosen_window, event_year)
            window_full = window_data.reindex(full_index)
            if window_full.dropna().shape[0] < max(3, chosen_window // 3):
                continue
            # Panel-wide z-score at event_year - 1
            panel_at_year = panel[panel["year"] == event_year - 1]["value"].dropna()
            if len(panel_at_year) < 10:
                baseline = series.loc[max(event_year - 25, series.index.min()) : event_year - 1].dropna()
                mu = float(baseline.mean())
                sd = float(baseline.std() or 1.0)
            else:
                mu = float(panel_at_year.mean())
                sd = float(panel_at_year.std() or 1.0)
            z = (window_full.values - mu) / sd
            z = np.where(np.isfinite(z), z, 0.0)
            trajectories.append(z)
        if len(trajectories) > 0:
            # Average across positive instances (per design v1: canonical = mean of pre-crisis trajectories)
            canonical[ind] = np.mean(np.array(trajectories), axis=0)
        else:
            canonical[ind] = np.zeros(chosen_window)
    return canonical


if __name__ == "__main__":
    sys.exit(_main())
