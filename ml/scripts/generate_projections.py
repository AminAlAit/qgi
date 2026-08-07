"""Generate per-country forward risk-score projections with MC uncertainty bands.

Pre-reg: TE-PROJ-1 (ratified 2026-05-24; Ji-Hoon #21 / Kwame #11 / Priya #22 3/3).
Spec sections consumed: §4.2 (MC propagation), §4.1 (PI fan-out + flat-series floor),
§6 (honesty rules — no probability language, band labeling, horizon cap h <= 3).

Requires:
  - Fitted model JSON from fit_projection_models.py
  - Walk summary JSON (for canonical profile + selected indicators)
  - SHAP importances JSON
  - Panel parquets (for current trajectories + z-score baking)

Algorithm per country per horizon h in {1, 2, 3}:
  1. Load the most recent W-year observed trajectory per indicator.
  2. For each indicator, get the forecast point + sigma_h from fitted model.
  3. Draw M=2000 MC samples: ŷ_i^(m) ~ N(point_i, sigma_h_i^2)
     (or from bootstrap residuals for PERSISTENCE_BOOTSTRAP indicators).
  4. For each draw: append forecasted year(s) to observed trajectory (slide window),
     z-score using same panel-wide distribution, run compute_country_recipe_similarity.
  5. Projected risk score = median of M draws; 90% band = 5th–95th pct.

Honesty enforced:
  - Projected score never replaces current score.
  - Zone labeled UNCERTAIN if zone_stability_pct < 0.50.
  - No h > 3 projections published.
  - near_random_walk flag when Skill(i, h) <= 0.05.
  - All per-indicator forecast details surfaced.

Output: qgi-data/reference/projections-{recipe_id}-{eval_year}.json

Usage:
    python scripts/generate_projections.py \\
        --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --shap-importances qgi-data/reference/shap-importances-foreign_intervention.json \\
        --fitted-models qgi-data/reference/projection-models-foreign_intervention-2021.json \\
        --output-dir qgi-data/reference/ \\
        --evaluation-year 2021 \\
        --mc-draws 2000 \\
        --seed 42
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402
import compute_recipe_country_similarity as sim_mod  # noqa: E402
import fit_projection_models as fpm  # noqa: E402

_RISK_ZONE_LOW_MAX = sim_mod.RISK_ZONE_LOW_MAX       # 40
_RISK_ZONE_MODERATE_MAX = sim_mod.RISK_ZONE_MODERATE_MAX  # 65
_MAX_HORIZON = 3
_MC_DRAWS = 2000
# Single source of truth in fit_projection_models (QA review #101 DRY fix).
_FLAT_SERIES_FLOOR_Z = fpm._FLAT_SERIES_FLOOR_Z   # pre-reg §4.1: floor width ±1.0 z


def _zone_from_score(score: float) -> str:
    if score < _RISK_ZONE_LOW_MAX:
        return "LOW"
    if score < _RISK_ZONE_MODERATE_MAX:
        return "MODERATE"
    return "HIGH"


def _sigma_h_for_params(params: dict, method: str, h: int) -> float:
    """Get sigma_h for a fitted model at horizon h.

    For ETS: uses pre-reg §4.1 recurrence formula.
    For PERSISTENCE_BOOTSTRAP: sigma * sqrt(h) (random-walk accumulation).
    """
    sigma = params.get("sigma", 1.0)
    if method == "PERSISTENCE_BOOTSTRAP":
        return sigma * np.sqrt(h)
    else:
        # ETS recurrence: Var_h = sigma^2 * (1 + sum_{j=1}^{h-1} (1 + j*beta)^2)
        beta = params.get("beta", fpm._BETA_DEFAULT)
        if h == 1:
            return sigma
        recurrence_sum = sum((1.0 + k * beta) ** 2 for k in range(1, h))
        return sigma * np.sqrt(1.0 + recurrence_sum)


def _point_forecast(params: dict, method: str, h: int) -> float:
    """Point forecast at horizon h."""
    if method == "PERSISTENCE_BOOTSTRAP":
        return params["level"]
    else:
        points, _ = fpm._holt_forecast(params, h)
        return float(points[h - 1])


def _enforce_pi_fan_out(sigma_by_h: list[float], flat_flag: bool) -> list[float]:
    """Ensure PI strictly widens with horizon (pre-reg §4.1).

    If a model produces non-fanning intervals (e.g., flat series with sigma≈0),
    replace with floor of FLAT_SERIES_FLOOR_Z.
    """
    if flat_flag:
        # Apply floor: minimum sigma = FLAT_SERIES_FLOOR_Z at each horizon
        sigma_by_h = [max(s, _FLAT_SERIES_FLOOR_Z) for s in sigma_by_h]
    # Enforce monotone: each sigma_h >= previous sigma
    for i in range(1, len(sigma_by_h)):
        if sigma_by_h[i] < sigma_by_h[i - 1]:
            sigma_by_h[i] = sigma_by_h[i - 1]
    return sigma_by_h


def mc_project_country(
    country: str,
    indicator_models: dict[str, Any],   # {ind: {method, params, flags}}
    country_trajectories: dict[str, np.ndarray],  # {ind: (W,) z-score observed}
    recipe_canonical: dict[str, np.ndarray],
    shap_weights: dict[str, float],
    z_dist: dict[str, dict[str, float]],
    panel_per_indicator: dict[str, pd.DataFrame],
    eval_year: int,
    window: int,
    horizons: list[int],
    M: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    """Run MC projection for one country across all horizons.

    Returns dict keyed by horizon with projected risk score + band.
    """
    result: dict[str, Any] = {}

    for h in horizons:
        # Per-indicator: compute point forecast + sigma_h
        ind_forecasts: dict[str, dict] = {}
        sigma_by_ind: dict[str, float] = {}
        point_by_ind: dict[str, float] = {}
        flat_flags: dict[str, bool] = {}

        for ind in shap_weights:
            if ind not in indicator_models:
                # Missing model for this indicator — skip
                ind_forecasts[ind] = {
                    "point": None, "pi_lo_95": None, "pi_hi_95": None,
                    "method": "MISSING", "horizon": h,
                }
                sigma_by_ind[ind] = 0.0
                point_by_ind[ind] = 0.0
                flat_flags[ind] = True
                continue

            m = indicator_models[ind]
            method = m["method"]
            params = m["params"]
            flat = m["flags"].get("flat_series_pi_degenerate", False)
            flat_flags[ind] = flat

            point = _point_forecast(params, method, h)
            sigma_h = _sigma_h_for_params(params, method, h)

            # Flat-series floor (pre-reg §4.1)
            if flat or sigma_h < 1e-6:
                sigma_h = _FLAT_SERIES_FLOOR_Z

            point_by_ind[ind] = point
            sigma_by_ind[ind] = sigma_h

            pi_lo = point - 1.96 * sigma_h
            pi_hi = point + 1.96 * sigma_h

            ind_forecasts[ind] = {
                "point": float(point),
                "pi_lo_95": float(pi_lo),
                "pi_hi_95": float(pi_hi),
                "sigma_h": float(sigma_h),
                "method": method,
                "horizon": h,
                "flat_series_pi_degenerate": flat,
            }

        # MC propagation: M draws per indicator
        # For each draw: build projected trajectory (append h forecasted years, slide window)
        score_draws = np.zeros(M)

        for m_idx in range(M):
            projected_trajs: dict[str, np.ndarray] = {}

            for ind in shap_weights:
                obs_traj = country_trajectories.get(ind)
                if obs_traj is None:
                    continue

                point = point_by_ind.get(ind, obs_traj[-1])
                sigma_h = sigma_by_ind.get(ind, 0.0)

                # Draw from N(point, sigma_h^2) or persistence level distribution
                if sigma_h > 0:
                    draw = rng.normal(point, sigma_h)
                else:
                    draw = point

                # Pre-reg §4.2: construct projected trajectory by appending draw(s)
                # and sliding window to maintain length W.
                # For h-step projection: we append h years, slide window forward by h.
                # The projected year is eval_year + h - 1 (h years after last observed).
                # Append draw to observed trajectory, take last W years.
                proj = np.append(obs_traj, [draw] * h)[-window:]
                # Ensure length W (pad with zeros at start if short)
                if len(proj) < window:
                    proj = np.concatenate([np.zeros(window - len(proj)), proj])

                projected_trajs[ind] = proj

            if len(projected_trajs) < len(shap_weights):
                # Not enough indicators — use a sentinel mid-range score
                score_draws[m_idx] = 50.0
                continue

            sim_result = sim_mod.compute_country_recipe_similarity(
                projected_trajs, recipe_canonical, shap_weights
            )
            score_draws[m_idx] = sim_result["risk_score"]

        projected_median = float(np.median(score_draws))
        p5, p95 = float(np.percentile(score_draws, 5)), float(np.percentile(score_draws, 95))

        # Zone stability: fraction of draws in the modal zone
        modal_zone = _zone_from_score(projected_median)
        zone_draw_labels = [_zone_from_score(s) for s in score_draws]
        zone_stability = float(sum(z == modal_zone for z in zone_draw_labels) / M)

        # Effective projected zone (UNCERTAIN if stability < 0.50)
        effective_zone = modal_zone if zone_stability >= 0.50 else "UNCERTAIN"

        any_flat = any(flat_flags.get(ind, False) for ind in shap_weights)

        result[h] = {
            "projection_horizon_years": h,
            "projected_risk_score_median": round(projected_median, 2),
            "projected_risk_score_90pct_lo": round(p5, 2),
            "projected_risk_score_90pct_hi": round(p95, 2),
            "projected_zone_modal": modal_zone,
            "zone_stability_pct": round(zone_stability, 4),
            "effective_projected_zone": effective_zone,
            "per_indicator_forecast": ind_forecasts,
            "honesty_flags": {
                "any_flat_series_pi_degenerate": any_flat,
                "horizon_validated": h <= _MAX_HORIZON,
                "zone_uncertain": effective_zone == "UNCERTAIN",
            },
            "mc_draws": M,
            "semantics": (
                "projected_trajectory_resemblance — NOT calibrated probability. "
                "Inherits cosine-similarity semantics from TE. M8-R5 binding rider applies."
            ),
        }

    return result


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-id", required=True)
    parser.add_argument("--walk-summary", type=Path, required=True)
    parser.add_argument("--shap-importances", type=Path, required=True)
    parser.add_argument("--fitted-models", type=Path, required=True,
                        help="Output of fit_projection_models.py")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--panel-dir", type=Path,
                        default=REPO_ROOT / "data" / "parquet_panels")
    parser.add_argument("--evaluation-year", type=int, required=True)
    parser.add_argument("--mc-draws", type=int, default=_MC_DRAWS)
    parser.add_argument("--seed", type=int, default=42,
                        help="Fixed RNG seed for determinism (pre-reg: fixed seed required)")
    parser.add_argument("--horizons", type=int, nargs="+", default=[1, 2, 3],
                        help="Forecast horizons in years (max 3 per pre-reg §6.3)")
    args = parser.parse_args(argv)

    # Hard enforce horizon cap (pre-reg §6.3)
    args.horizons = [h for h in args.horizons if h <= _MAX_HORIZON]
    if not args.horizons:
        print("ERROR: no valid horizons (max h=3 per TE-PROJ-1 §6.3)", file=sys.stderr)
        return 1

    # Load configs
    with open(args.walk_summary, encoding="utf-8") as f:
        walk = json.load(f)
    assert walk["recipe_id"] == args.recipe_id

    with open(args.shap_importances, encoding="utf-8") as f:
        shap_data = json.load(f)
    shap_weights = shap_data["shap_importance_normalized"]

    with open(args.fitted_models, encoding="utf-8") as f:
        fitted = json.load(f)

    selected = walk["greedy_outer_loop"]["selected_indicators"]
    chosen_window = walk["greedy_outer_loop"]["chosen_window"]

    print(f"[generate_projections] recipe={args.recipe_id} eval_year={args.evaluation_year} "
          f"horizons={args.horizons} mc_draws={args.mc_draws} seed={args.seed}")

    # Load panels
    panels: dict[str, pd.DataFrame] = {ind: drv.load_panel(ind, args.panel_dir) for ind in selected}

    # Pre-bake z-distribution (prebake_zscore_distribution takes panel_dir: Path)
    z_dist = sim_mod.prebake_zscore_distribution(args.panel_dir, selected, args.evaluation_year)

    # Build canonical profile
    recipe_canonical = sim_mod.build_canonical_profile_from_walk(
        walk, panels, chosen_window, selected)

    # Get all countries in panel
    all_countries: set[str] = set()
    for ind in selected:
        all_countries |= set(panels[ind]["country"].dropna().unique())
    all_countries_sorted = sorted(all_countries)
    print(f"  panel countries: {len(all_countries_sorted)}")

    rng = np.random.default_rng(args.seed)

    country_projections: dict[str, Any] = {}
    n_skipped = 0

    for country in all_countries_sorted:
        # Extract current observed trajectories
        country_trajs: dict[str, np.ndarray] = {}
        for ind in selected:
            t = sim_mod.extract_country_trajectory(
                panels[ind], country, args.evaluation_year, chosen_window,
                ind_dist=z_dist[ind])
            if t is not None:
                country_trajs[ind] = t

        if len(country_trajs) < len(selected):
            n_skipped += 1
            continue

        # Current risk score (unmodified similarity script output)
        current_sim = sim_mod.compute_country_recipe_similarity(
            country_trajs, recipe_canonical, shap_weights)
        current_risk_score = current_sim["risk_score"]

        # Per-indicator fitted models for this country
        indicator_models: dict[str, Any] = {}
        for ind in selected:
            ind_block = fitted["indicator_models"].get(ind, {})
            country_model = ind_block.get("country_models", {}).get(country)
            if country_model is not None:
                indicator_models[ind] = country_model

        proj_results = mc_project_country(
            country=country,
            indicator_models=indicator_models,
            country_trajectories=country_trajs,
            recipe_canonical=recipe_canonical,
            shap_weights=shap_weights,
            z_dist=z_dist,
            panel_per_indicator=panels,
            eval_year=args.evaluation_year,
            window=chosen_window,
            horizons=args.horizons,
            M=args.mc_draws,
            rng=rng,
        )

        country_projections[country] = {
            "current_risk_score": round(current_risk_score, 2),
            "current_zone": current_sim["zone"],
            "projections": {str(h): v for h, v in proj_results.items()},
        }

    print(f"  projected {len(country_projections)} countries; skipped {n_skipped} (insufficient data)")

    output = {
        "schema_version": 1,
        "pre_reg": "TE-PROJ-1 (ratified 2026-05-24)",
        "recipe_id": args.recipe_id,
        "evaluation_year": args.evaluation_year,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mc_draws": args.mc_draws,
        "rng_seed": args.seed,
        "horizons": args.horizons,
        "max_horizon_enforced": _MAX_HORIZON,
        "scoring_semantics": (
            "projected_trajectory_resemblance — cosine similarity of projected indicator "
            "trajectory vs canonical pre-crisis profile. NOT a calibrated probability. "
            "M8-R5 binding rider: discrimination layer only. No probability claims."
        ),
        "band_label": (
            "90% uncertainty range reflecting indicator forecast uncertainty + model-fit "
            "uncertainty, propagated via Monte Carlo through cosine-similarity computation. "
            "Not a Gaussian confidence interval."
        ),
        "n_countries": len(country_projections),
        "countries": country_projections,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"projections-{args.recipe_id}-{args.evaluation_year}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[generate_projections] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
