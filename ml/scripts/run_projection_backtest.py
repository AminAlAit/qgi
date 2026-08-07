"""Projection backtest — HARD GATE before any projection publishes.

Pre-reg: TE-PROJ-1 (ratified 2026-05-24; Ji-Hoon #21 / Kwame #11 / Priya #22 3/3).
Spec sections consumed: §5 (backtest procedure), §5.1 (K=5 holdout), §5.2 (metrics),
§5.3 (pass thresholds), §6.4 (near-RW disclosure).

Hard gate thresholds (pre-reg §5.3 — NOT adjustable based on recipe result):
  Coverage(i, h) >= 0.80 in every (indicator x horizon) cell
  Skill(risk_score, h) >= 0.00 on the weighted-mean projected risk score

If Skill < 0 overall: projections SUPPRESSED. Honest persistence-baseline disclosed.

FLAT_SERIES_PI_DEGENERATE count logged per Kwame's note (ratification record).

Output: qgi-data/reference/projection-backtest-{recipe_id}-{eval_year}.json
        (same discipline as F-ML-1 DECISION files; requires 3/3 Majles ratification
         from Ji-Hoon #21, Kwame #11, Priya #22 before projections go live)

Usage:
    python scripts/run_projection_backtest.py \\
        --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --shap-importances qgi-data/reference/shap-importances-foreign_intervention.json \\
        --output-dir qgi-data/reference/ \\
        --evaluation-year 2021 \\
        --panel-dir data/parquet_panels/ \\
        --mc-draws 500 \\
        --seed 42
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
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
import generate_projections as gp  # noqa: E402

_HOLDOUT_K = 5
_MAX_HORIZON = 3
_COVERAGE_FLOOR = 0.80     # pre-reg §5.3 — NOT adjustable
_SKILL_FLOOR = 0.0         # pre-reg §5.3 — NOT adjustable
_NEAR_RW_SKILL_THRESHOLD = 0.05   # pre-reg §6.4 — near-RW disclosure threshold
_MC_DRAWS_BACKTEST = 500   # reduced for backtest speed; 2000 for production


def _build_expanding_origins(all_years: list[int], k: int) -> list[int]:
    """Return K expanding-window forecast origins.

    For K=5, origins = [max_year - k, ..., max_year - 1] (year AFTER training).
    Training for origin t uses data up to (but not including) t.
    """
    if not all_years or k <= 0:
        return []
    sorted_years = sorted(all_years)
    if len(sorted_years) <= k:
        return sorted_years
    return sorted_years[-k:]


def compute_coverage(actuals: list[float], pi_lo_list: list[float],
                     pi_hi_list: list[float]) -> float:
    """Empirical 90% PI coverage fraction."""
    if not actuals:
        return float("nan")
    covered = sum(lo <= a <= hi for a, lo, hi in zip(actuals, pi_lo_list, pi_hi_list))
    return covered / len(actuals)


def compute_skill(mae_model: float, mae_persistence: float) -> float:
    """MAE skill score: 1 - MAE_model / MAE_persistence. Positive = beats persistence."""
    if mae_persistence < 1e-12:
        return 0.0   # degenerate (flat series): treat as zero skill, not inf
    return 1.0 - mae_model / mae_persistence


def _persistence_forecast_at_h(y_train: np.ndarray, h: int) -> float:
    """Naive persistence baseline: last observed value."""
    if len(y_train) == 0:
        return 0.0
    return float(y_train[-1])


def _get_actual_value(panel: pd.DataFrame, country: str, year: int) -> float | None:
    """Get actual indicator value for a country-year. Returns None if missing."""
    cdf = panel[(panel["country"] == country) & (panel["year"] == year)]
    if len(cdf) == 0 or cdf["value"].isna().all():
        return None
    return float(cdf["value"].iloc[0])


def run_indicator_backtest(
    panel: pd.DataFrame,
    indicator: str,
    countries: list[str],
    eval_year: int,
    window: int,
    k: int,
    panel_method: str,
    horizons: list[int],
) -> dict[str, Any]:
    """Run indicator-level holdout evaluation across K origins x all countries.

    Returns per-horizon: coverage, MAE_model, MAE_persistence, skill, flat counts.
    """
    # Collect results per horizon
    actuals_by_h: dict[int, list[float]] = {h: [] for h in horizons}
    model_preds_by_h: dict[int, list[float]] = {h: [] for h in horizons}
    pi_lo_by_h: dict[int, list[float]] = {h: [] for h in horizons}
    pi_hi_by_h: dict[int, list[float]] = {h: [] for h in horizons}
    persistence_preds_by_h: dict[int, list[float]] = {h: [] for h in horizons}
    flat_count = 0

    # Expanding-window origins: forecast from each of the K origins
    # For each origin t: train on data up to (t - 1), forecast t, t+1, ..., t+h-1
    for country in countries:
        cdf = panel[panel["country"] == country]
        if len(cdf) == 0:
            continue
        series = cdf.set_index("year")["value"].sort_index().dropna()
        if len(series) < k + 4:
            continue

        available_years = sorted(series.index.tolist())
        # Use the K years immediately before eval_year as holdout origins
        holdout_start = eval_year - k
        origins = [yr for yr in available_years if holdout_start <= yr < eval_year]
        if not origins:
            continue

        for origin_year in origins:
            # Training series: all data strictly before origin_year
            y_train = series[series.index < origin_year].values.astype(float)
            if len(y_train) < 3:
                continue

            # Fit model on training data
            flat_flag = False
            if panel_method == "PERSISTENCE_BOOTSTRAP":
                params = fpm._persistence_fit(y_train)
                method = "PERSISTENCE_BOOTSTRAP"
            elif panel_method == "ETS_A_Ad_N":
                params = fpm._holt_fit_numpy(y_train, damped=True)
                method = "ETS_A_Ad_N"
            else:
                params = fpm._holt_fit_numpy(y_train, damped=False)
                method = "ETS_A_A_N"

            if params.get("sigma", 0.0) < 1e-6:
                flat_flag = True
                params["sigma"] = fpm._FLAT_SERIES_FLOOR_Z
                flat_count += 1

            for h in horizons:
                # Actual value at origin_year + h - 1
                target_year = origin_year + h - 1
                actual = _get_actual_value(panel, country, target_year)
                if actual is None:
                    continue

                # Model forecast
                point = gp._point_forecast(params, method, h)
                sigma_h = gp._sigma_h_for_params(params, method, h)
                if flat_flag or sigma_h < 1e-6:
                    sigma_h = fpm._FLAT_SERIES_FLOOR_Z

                pi_lo = point - 1.645 * sigma_h   # 90% PI: z=1.645
                pi_hi = point + 1.645 * sigma_h

                actuals_by_h[h].append(actual)
                model_preds_by_h[h].append(point)
                pi_lo_by_h[h].append(pi_lo)
                pi_hi_by_h[h].append(pi_hi)

                # Persistence baseline
                pers_pred = _persistence_forecast_at_h(y_train, h)
                persistence_preds_by_h[h].append(pers_pred)

    # Compute metrics per horizon
    metrics: dict[int, dict] = {}
    for h in horizons:
        acts = actuals_by_h[h]
        m_preds = model_preds_by_h[h]
        p_preds = persistence_preds_by_h[h]
        lo_list = pi_lo_by_h[h]
        hi_list = pi_hi_by_h[h]

        n = len(acts)
        if n == 0:
            metrics[h] = {"n_obs": 0, "coverage_90pct": float("nan"),
                          "mae_model": float("nan"), "mae_persistence": float("nan"),
                          "skill": float("nan"), "coverage_pass": False}
            continue

        acts_arr = np.array(acts)
        m_arr = np.array(m_preds)
        p_arr = np.array(p_preds)

        mae_model = float(np.mean(np.abs(m_arr - acts_arr)))
        mae_persistence = float(np.mean(np.abs(p_arr - acts_arr)))
        skill = compute_skill(mae_model, mae_persistence)
        coverage = compute_coverage(acts, lo_list, hi_list)
        coverage_pass = bool((not np.isnan(coverage)) and (coverage >= _COVERAGE_FLOOR))

        near_rw = skill <= _NEAR_RW_SKILL_THRESHOLD

        metrics[h] = {
            "n_obs": n,
            "coverage_90pct": round(coverage, 4),
            "coverage_pass": coverage_pass,
            "coverage_floor": _COVERAGE_FLOOR,
            "mae_model": round(mae_model, 6),
            "mae_persistence": round(mae_persistence, 6),
            "skill": round(skill, 4),
            "near_random_walk": near_rw,
        }

    return {"per_horizon": metrics, "flat_series_count": flat_count}


def run_risk_score_backtest(
    panels: dict[str, pd.DataFrame],
    selected: list[str],
    shap_weights: dict[str, float],
    recipe_canonical: dict[str, np.ndarray],
    z_dist: dict[str, dict],
    countries: list[str],
    eval_year: int,
    window: int,
    k: int,
    override_log: dict[str, str],
    horizons: list[int],
    mc_draws: int,
    seed: int,
) -> dict[str, Any]:
    """Compute projected risk-score skill vs persistence baseline.

    For each (country, origin, horizon): compare projected risk score to actual
    risk score (computed from actual observed window at that point) vs naive
    persistence of the current risk score.
    """
    rng = np.random.default_rng(seed)

    model_scores_by_h: dict[int, list[float]] = {h: [] for h in horizons}
    pers_scores_by_h: dict[int, list[float]] = {h: [] for h in horizons}
    actual_scores_by_h: dict[int, list[float]] = {h: [] for h in horizons}

    for country in countries:
        # Check that all indicators have data for this country
        has_data = all(
            len(panels[ind][panels[ind]["country"] == country]) > 0
            for ind in selected
        )
        if not has_data:
            continue

        # Use K expanding origins
        # Find years where all indicators have data
        year_coverage = None
        for ind in selected:
            cdf = panels[ind][panels[ind]["country"] == country].dropna(subset=["value"])
            ind_years = set(cdf["year"].tolist())
            year_coverage = ind_years if year_coverage is None else year_coverage & ind_years
        if not year_coverage:
            continue

        holdout_start = eval_year - k
        origins = sorted(yr for yr in year_coverage if holdout_start <= yr < eval_year)
        if not origins:
            continue

        for origin_year in origins:
            # Current observed trajectory at origin_year (our "time zero")
            current_trajs: dict[str, np.ndarray] = {}
            for ind in selected:
                t = sim_mod.extract_country_trajectory(
                    panels[ind], country, origin_year, window,
                    ind_dist=z_dist[ind])
                if t is not None:
                    current_trajs[ind] = t

            if len(current_trajs) < len(selected):
                continue

            current_sim = sim_mod.compute_country_recipe_similarity(
                current_trajs, recipe_canonical, shap_weights)
            current_score = current_sim["risk_score"]

            for h in horizons:
                target_year = origin_year + h

                # Actual risk score at target_year
                actual_trajs: dict[str, np.ndarray] = {}
                for ind in selected:
                    t = sim_mod.extract_country_trajectory(
                        panels[ind], country, target_year, window,
                        ind_dist=z_dist[ind])
                    if t is not None:
                        actual_trajs[ind] = t

                if len(actual_trajs) < len(selected):
                    continue

                actual_sim = sim_mod.compute_country_recipe_similarity(
                    actual_trajs, recipe_canonical, shap_weights)
                actual_score = actual_sim["risk_score"]

                # Fit models on training data up to origin_year
                indicator_models: dict[str, Any] = {}
                for ind in selected:
                    panel = panels[ind]
                    method = override_log.get(ind, "ETS_A_A_N")
                    cdf = panel[panel["country"] == country]
                    series = cdf.set_index("year")["value"].sort_index().dropna()
                    y_train = series[series.index < origin_year].values.astype(float)

                    if len(y_train) < 2:
                        params = fpm._persistence_fit(y_train)
                        m = {"method": "PERSISTENCE_BOOTSTRAP", "params": params,
                             "flags": {"n_obs": len(y_train), "flat_series_pi_degenerate": False}}
                    elif method == "PERSISTENCE_BOOTSTRAP":
                        params = fpm._persistence_fit(y_train)
                        m = {"method": method, "params": params,
                             "flags": {"n_obs": len(y_train), "flat_series_pi_degenerate": False}}
                    else:
                        damped = (method == "ETS_A_Ad_N")
                        params = fpm._holt_fit_numpy(y_train, damped=damped)
                        flat = params.get("sigma", 0.0) < 1e-6
                        if flat:
                            params["sigma"] = fpm._FLAT_SERIES_FLOOR_Z
                        m = {"method": method, "params": params,
                             "flags": {"n_obs": len(y_train), "flat_series_pi_degenerate": flat}}
                    indicator_models[ind] = m

                # MC projection of risk score at h
                proj_result = gp.mc_project_country(
                    country=country,
                    indicator_models=indicator_models,
                    country_trajectories=current_trajs,
                    recipe_canonical=recipe_canonical,
                    shap_weights=shap_weights,
                    z_dist=z_dist,
                    panel_per_indicator=panels,
                    eval_year=origin_year,
                    window=window,
                    horizons=[h],
                    M=mc_draws,
                    rng=rng,
                )

                projected_score = proj_result[h]["projected_risk_score_median"]

                model_scores_by_h[h].append(projected_score)
                actual_scores_by_h[h].append(actual_score)
                pers_scores_by_h[h].append(current_score)  # persistence = no change

    # Compute risk-score level MAE skill per horizon
    risk_score_metrics: dict[int, dict] = {}
    for h in horizons:
        acts = np.array(actual_scores_by_h[h])
        m_preds = np.array(model_scores_by_h[h])
        p_preds = np.array(pers_scores_by_h[h])
        n = len(acts)

        if n == 0:
            risk_score_metrics[h] = {"n_obs": 0, "mae_model": float("nan"),
                                     "mae_persistence": float("nan"),
                                     "skill": float("nan"), "skill_pass": False}
            continue

        mae_model = float(np.mean(np.abs(m_preds - acts)))
        mae_persistence = float(np.mean(np.abs(p_preds - acts)))
        skill = compute_skill(mae_model, mae_persistence)

        risk_score_metrics[h] = {
            "n_obs": n,
            "mae_model": round(mae_model, 4),
            "mae_persistence": round(mae_persistence, 4),
            "skill": round(skill, 4),
            "skill_pass": bool(skill >= _SKILL_FLOOR),
            "skill_floor": _SKILL_FLOOR,
        }

    return risk_score_metrics


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-id", required=True)
    parser.add_argument("--walk-summary", type=Path, required=True)
    parser.add_argument("--shap-importances", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--panel-dir", type=Path,
                        default=REPO_ROOT / "data" / "parquet_panels")
    parser.add_argument("--evaluation-year", type=int, required=True)
    parser.add_argument("--holdout-k", type=int, default=_HOLDOUT_K,
                        help="Number of holdout years (K=5 per TE-PROJ-1 §5.1 — do not change without amendment)")
    parser.add_argument("--horizons", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--mc-draws", type=int, default=_MC_DRAWS_BACKTEST)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    args.horizons = [h for h in args.horizons if h <= _MAX_HORIZON]

    with open(args.walk_summary, encoding="utf-8") as f:
        walk = json.load(f)
    assert walk["recipe_id"] == args.recipe_id

    with open(args.shap_importances, encoding="utf-8") as f:
        shap_data = json.load(f)
    shap_weights = shap_data["shap_importance_normalized"]

    selected = walk["greedy_outer_loop"]["selected_indicators"]
    chosen_window = walk["greedy_outer_loop"]["chosen_window"]

    print(f"[run_projection_backtest] recipe={args.recipe_id} eval_year={args.evaluation_year} "
          f"holdout_k={args.holdout_k} horizons={args.horizons} mc_draws={args.mc_draws}")

    panels: dict[str, pd.DataFrame] = {ind: drv.load_panel(ind, args.panel_dir) for ind in selected}

    # Pre-bake z-distribution at eval_year (full panel, not held-out — z-dist is pre-baked cross-sectionally)
    z_dist = sim_mod.prebake_zscore_distribution(args.panel_dir, selected, args.evaluation_year)

    # Build canonical profile (full history)
    recipe_canonical = sim_mod.build_canonical_profile_from_walk(
        walk, panels, chosen_window, selected)

    # Countries with coverage in all indicators
    all_countries: set[str] = set()
    for ind in selected:
        if len(all_countries) == 0:
            all_countries = set(panels[ind]["country"].dropna().unique())
        else:
            all_countries &= set(panels[ind]["country"].dropna().unique())
    countries = sorted(all_countries)
    print(f"  candidate countries (all-indicator coverage): {len(countries)}")

    # Determine method overrides (same logic as fit_projection_models.py)
    override_log: dict[str, str] = {}
    for ind in selected:
        series_list = fpm._load_panel_series_for_override(
            panels[ind], countries, args.evaluation_year, chosen_window)
        override_log[ind] = fpm._detect_method_override(series_list, ind)
        print(f"  {ind}: method={override_log[ind]}")

    # ------------------------------------------------------------------ #
    # Part A: Per-indicator backtest (coverage + MAE skill)               #
    # ------------------------------------------------------------------ #
    print("\n--- Part A: per-indicator holdout (coverage + skill) ---")
    indicator_results: dict[str, Any] = {}
    total_flat_count = 0

    for ind in selected:
        bt = run_indicator_backtest(
            panel=panels[ind],
            indicator=ind,
            countries=countries,
            eval_year=args.evaluation_year,
            window=chosen_window,
            k=args.holdout_k,
            panel_method=override_log[ind],
            horizons=args.horizons,
        )
        indicator_results[ind] = bt
        total_flat_count += bt["flat_series_count"]

        for h, m in bt["per_horizon"].items():
            status = "PASS" if m.get("coverage_pass", False) else "FAIL"
            print(f"  {ind} h={h}: coverage={m.get('coverage_90pct', 'nan'):.3f} [{status}] "
                  f"skill={m.get('skill', 'nan'):.3f} n={m.get('n_obs', 0)}")

    # Coverage gate: ALL (indicator x horizon) cells must pass
    coverage_cells_pass: dict[str, dict[int, bool]] = {}
    coverage_gate_pass = True
    for ind, bt in indicator_results.items():
        coverage_cells_pass[ind] = {}
        for h, m in bt["per_horizon"].items():
            cell_pass = m.get("coverage_pass", False)
            coverage_cells_pass[ind][h] = cell_pass
            if not cell_pass:
                coverage_gate_pass = False

    print(f"\nCoverage gate (all cells >= {_COVERAGE_FLOOR}): {'PASS' if coverage_gate_pass else 'FAIL'}")

    # Kwame's note: report FLAT_SERIES_PI_DEGENERATE counts in backtest file
    print(f"FLAT_SERIES_PI_DEGENERATE total across all indicator x country x origin cells: {total_flat_count}")

    # ------------------------------------------------------------------ #
    # Part B: Risk-score level skill vs persistence                       #
    # ------------------------------------------------------------------ #
    print("\n--- Part B: projected risk-score skill vs persistence ---")
    risk_metrics = run_risk_score_backtest(
        panels=panels,
        selected=selected,
        shap_weights=shap_weights,
        recipe_canonical=recipe_canonical,
        z_dist=z_dist,
        countries=countries,
        eval_year=args.evaluation_year,
        window=chosen_window,
        k=args.holdout_k,
        override_log=override_log,
        horizons=args.horizons,
        mc_draws=args.mc_draws,
        seed=args.seed,
    )

    skill_gate_pass = True
    for h, m in risk_metrics.items():
        skill_pass = m.get("skill_pass", False)
        if not skill_pass:
            skill_gate_pass = False
        print(f"  Risk score h={h}: skill={m.get('skill', 'nan'):.4f} "
              f"[{'PASS' if skill_pass else 'FAIL'}] "
              f"mae_model={m.get('mae_model', 'nan'):.4f} "
              f"mae_persistence={m.get('mae_persistence', 'nan'):.4f} "
              f"n={m.get('n_obs', 0)}")

    # Overall gate
    gate_pass = coverage_gate_pass and skill_gate_pass

    # ------------------------------------------------------------------ #
    # SUPPRESSED disclosure (pre-reg §5.3)                                #
    # ------------------------------------------------------------------ #
    # Suppress on EITHER gate failure, not skill alone (QA review #101):
    # a recipe that beats persistence (skill PASS) but whose prediction
    # intervals under-cover (coverage FAIL) would otherwise publish
    # over-confident bands. suppressed tracks the full gate.
    suppressed = not gate_pass
    suppression_message = None
    if suppressed:
        if not skill_gate_pass:
            reason = (
                "did not outperform naive persistence for this recipe on historical "
                "holdout data"
            )
        else:
            reason = (
                "produced prediction intervals that failed empirical coverage on "
                "historical holdout data"
            )
        suppression_message = (
            f"QGI's projection engine {reason}. Projected risk scores are not displayed. "
            "Current risk score (observed window): [see current_risk_score per country]."
        )

    print(f"\n{'='*60}")
    print(f"GATE RESULT: {'PASS' if gate_pass else 'FAIL'}")
    print(f"  Coverage gate: {'PASS' if coverage_gate_pass else 'FAIL'}")
    print(f"  Skill gate:    {'PASS' if skill_gate_pass else 'FAIL'}")
    if suppressed:
        print(f"\nSUPPRESSED: {suppression_message}")
    print(f"{'='*60}\n")

    # ------------------------------------------------------------------ #
    # Write backtest report JSON                                           #
    # ------------------------------------------------------------------ #
    report = {
        "schema_version": 1,
        "pre_reg": "TE-PROJ-1 (ratified 2026-05-24)",
        "recipe_id": args.recipe_id,
        "evaluation_year": args.evaluation_year,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "holdout_k": args.holdout_k,
        "horizons_evaluated": args.horizons,
        "mc_draws": args.mc_draws,
        "rng_seed": args.seed,
        "gate_pass": gate_pass,
        "coverage_gate_pass": coverage_gate_pass,
        "skill_gate_pass": skill_gate_pass,
        "suppressed": suppressed,
        "suppression_message": suppression_message,
        "gate_thresholds": {
            "coverage_floor": _COVERAGE_FLOOR,
            "skill_floor": _SKILL_FLOOR,
            "note": "NOT adjustable based on this recipe's result. Amendment requires TE-PROJ-N with prior-walk provenance.",
        },
        "per_indicator_backtest": {
            ind: {
                "method": override_log[ind],
                "flat_series_count": res["flat_series_count"],
                "per_horizon": {str(h): v for h, v in res["per_horizon"].items()},
                "near_random_walk_any_horizon": any(
                    v.get("near_random_walk", False) for v in res["per_horizon"].values()
                ),
            }
            for ind, res in indicator_results.items()
        },
        "risk_score_backtest": {
            str(h): v for h, v in risk_metrics.items()
        },
        "flat_series_pi_degenerate_total": total_flat_count,
        "coverage_cells_pass": {ind: {str(h): v for h, v in cells.items()}
                                 for ind, cells in coverage_cells_pass.items()},
        "method_overrides": override_log,
        "ratification_required": {
            "seats": ["Ji-Hoon Yamamoto-Costa #21", "Kwame Asante #11", "Priya Chandrasekaran #22"],
            "threshold": "3/3",
            "note": "Required before projections appear in buyer-facing surfaces. Same discipline as F-ML-1 DECISION files.",
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"projection-backtest-{args.recipe_id}-{args.evaluation_year}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[run_projection_backtest] wrote {out_path}")

    # Exit code: 0 even on gate FAIL (orchestrator reads gate_pass from JSON)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
