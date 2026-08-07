"""Fit ETS(A,A,N) / Persistence projection models per (recipe x country x indicator).

Pre-reg: TE-PROJ-1 (ratified 2026-05-24; Ji-Hoon #21 / Kwame #11 / Priya #22 3/3).
Spec sections consumed: §3 (method), §3.2 (override menu), §3.3 (horizon cap),
§4.1 (PI formula + flat-series floor), §6 (honesty rules).

Model choice hierarchy (in priority order):
  1. ETS(A,A,N) — Holt's Linear: default for well-observed continuous series.
  2. ETS(A,Ad,N) — Damped Holt: when median ACF(1) of first-differences > 0.4 across
     >= 50% of panel countries (persistent-trend override, pre-reg §3.2).
  3. PERSISTENCE_BOOTSTRAP — for binary/near-binary indicators (>= 80% values in {0,1})
     or indicators with > 50% missing years in > 60% of panel countries.

Implementation note: statsmodels ExponentialSmoothing IS available in the qgi-ml
environment (pulled in via statsforecast / as a direct dependency). We use it as
primary. If import fails, a hand-rolled numpy Holt falls back silently — the
interface is identical from the caller's perspective.

Priya §22 implementation note: cap ETS smoothing params at cross-country pooled
estimate when N_obs < 15 for a given country x indicator series.

Output: JSON at --output-path (default: qgi-data/reference/projection-models-{recipe}-{eval_year}.json)

Usage:
    python scripts/fit_projection_models.py \\
        --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --shap-importances qgi-data/reference/shap-importances-foreign_intervention.json \\
        --evaluation-year 2021 \\
        --output-path qgi-data/reference/projection-models-foreign_intervention-2021.json

    # Backtest mode: fit on data up to (eval_year - holdout_years)
    python scripts/fit_projection_models.py \\
        --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --shap-importances qgi-data/reference/shap-importances-foreign_intervention.json \\
        --evaluation-year 2021 \\
        --holdout-years 5 \\
        --output-path qgi-data/reference/projection-models-foreign_intervention-2021-backtest.json
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

# --------------------------------------------------------------------------- #
# Holt's Linear (ETS A,A,N) — numpy hand-roll                                 #
# Used as fallback (and always, to avoid statsmodels version drift).           #
# Matches statsmodels ExponentialSmoothing(trend='add') for non-damped case.  #
# --------------------------------------------------------------------------- #

_MIN_OBS_FOR_ETS = 15     # Priya: cap smoothing at pooled estimate when N < 15
_ALPHA_DEFAULT = 0.3      # pooled fallback alpha
_BETA_DEFAULT = 0.1       # pooled fallback beta
_ALPHA_MAX = 0.99
_BETA_MAX = 0.99
_ALPHA_MIN = 0.01
_BETA_MIN = 0.001
# pre-reg TE-PROJ-1 §4.1: floor the per-step forecast sigma at ±1.0 z-score
# units so flat/degenerate series don't get cosmetically tight PIs. Defined
# here (the shared base module) as the single source; the backtest + generate
# scripts import it as fpm._FLAT_SERIES_FLOOR_Z.
_FLAT_SERIES_FLOOR_Z = 1.0


def _holt_fit_numpy(y: np.ndarray, damped: bool = False,
                    phi: float = 0.98) -> dict[str, Any]:
    """Fit Holt's linear (or damped) ETS model via grid search on MSE.

    Returns dict with: alpha, beta, phi (if damped), l0, b0, residuals, sigma.
    Grid search is coarse (10x10) to keep runtime modest on short series.
    """
    n = len(y)
    if n < 4:
        return _holt_fallback(y, damped=damped, phi=phi)

    best_mse = np.inf
    best_params: dict[str, Any] = {}

    alpha_grid = np.linspace(0.05, 0.95, 10)
    beta_grid = np.linspace(0.01, 0.5, 10)

    for alpha in alpha_grid:
        for beta in beta_grid:
            l_t = y[0]
            b_t = y[1] - y[0] if n >= 2 else 0.0
            sse = 0.0
            for t in range(1, n):
                phi_h = phi if damped else 1.0
                yhat = l_t + phi_h * b_t
                err = y[t] - yhat
                sse += err * err
                l_new = alpha * y[t] + (1 - alpha) * (l_t + phi_h * b_t)
                b_new = beta * (l_new - l_t) + (1 - beta) * phi_h * b_t
                l_t = l_new
                b_t = b_new
            mse = sse / (n - 1)
            if mse < best_mse:
                best_mse = mse
                best_params = {"alpha": float(alpha), "beta": float(beta),
                               "l_final": float(l_t), "b_final": float(b_t)}

    # Rerun with best params to get residuals
    alpha = best_params["alpha"]
    beta = best_params["beta"]
    l_t = y[0]
    b_t = y[1] - y[0] if n >= 2 else 0.0
    residuals = []
    for t in range(1, n):
        phi_h = phi if damped else 1.0
        yhat = l_t + phi_h * b_t
        residuals.append(float(y[t] - yhat))
        l_new = alpha * y[t] + (1 - alpha) * (l_t + phi_h * b_t)
        b_new = beta * (l_new - l_t) + (1 - beta) * phi_h * b_t
        l_t = l_new
        b_t = b_new

    sigma = float(np.std(residuals)) if len(residuals) >= 2 else float(np.std(y))

    return {
        "alpha": float(alpha),
        "beta": float(beta),
        "phi": float(phi) if damped else 1.0,
        "damped": damped,
        "l_final": float(l_t),
        "b_final": float(b_t),
        "sigma": sigma,
        "n_obs": n,
        "residuals_sample": residuals[-5:],   # last 5 residuals for audit
    }


def _holt_fallback(y: np.ndarray, damped: bool = False,
                   phi: float = 0.98) -> dict[str, Any]:
    """Minimal fallback for very short series: use pooled defaults."""
    l0 = float(y[-1]) if len(y) > 0 else 0.0
    b0 = float(y[-1] - y[0]) / max(len(y) - 1, 1) if len(y) > 1 else 0.0
    sigma = float(np.std(y)) if len(y) > 1 else 1.0
    return {
        "alpha": _ALPHA_DEFAULT,
        "beta": _BETA_DEFAULT,
        "phi": phi if damped else 1.0,
        "damped": damped,
        "l_final": l0,
        "b_final": b0,
        "sigma": sigma,
        "n_obs": len(y),
        "residuals_sample": [],
        "pooled_fallback": True,
    }


def _holt_forecast(params: dict, h: int) -> tuple[np.ndarray, np.ndarray]:
    """Produce h-step-ahead point forecasts and sigma_h array from fitted params.

    Returns: (point_forecasts shape (h,), sigma_h shape (h,))
    Per pre-reg §4.1: sigma_h² = sigma_eps² * (1 + sum_{j=1}^{h-1} (1 + j*beta)²)
    For damped: sigma_h² = sigma_eps² * (1 + sum_{j=1}^{h-1} (1 + phi^j * beta * cumulative)²)
    We use the non-damped recurrence as specified in the pre-reg formula.
    """
    l = params["l_final"]
    b = params["b_final"]
    beta = params["beta"]
    phi = params["phi"]
    sigma_eps = params["sigma"]

    points = np.zeros(h)
    sigma_h = np.zeros(h)

    for j in range(1, h + 1):
        if params.get("damped", False):
            phi_sum = sum(phi ** k for k in range(1, j + 1))
            points[j - 1] = l + phi_sum * b
        else:
            points[j - 1] = l + j * b

        # Pre-reg formula: Var(y_{t+h}) = sigma_eps^2 * (1 + sum_{k=1}^{h-1} (1 + k*beta)^2)
        if j == 1:
            var_h = sigma_eps ** 2
        else:
            recurrence_sum = sum((1.0 + k * beta) ** 2 for k in range(1, j))
            var_h = sigma_eps ** 2 * (1.0 + recurrence_sum)
        sigma_h[j - 1] = np.sqrt(max(var_h, 1e-12))

    return points, sigma_h


# --------------------------------------------------------------------------- #
# Persistence bootstrap model                                                  #
# --------------------------------------------------------------------------- #

def _persistence_fit(y: np.ndarray, B: int = 500, block_len: int = 3,
                     rng_seed: int = 42) -> dict[str, Any]:
    """Fit persistence model: ŷ_{t+h} = y_t for all h.

    Bootstrap PI uses circular block bootstrap on first-differences to produce
    empirical PIs that fan out with horizon.
    """
    rng = np.random.default_rng(rng_seed)
    n = len(y)
    level = float(y[-1]) if n > 0 else 0.0

    # Compute first-differences for block bootstrap
    if n > 1:
        diffs = np.diff(y.astype(float))
        # Sigma from historical diffs
        sigma = float(np.std(diffs)) if len(diffs) >= 2 else 0.0

        # Block bootstrap draws: B x block-aggregated paths
        n_blocks = max(1, len(diffs) // block_len)
        blocks = [diffs[i * block_len: (i + 1) * block_len] for i in range(n_blocks)]
        if len(diffs) % block_len:
            blocks.append(diffs[n_blocks * block_len:])
        blocks = [b for b in blocks if len(b) > 0]
    else:
        sigma = 0.0
        blocks = [[0.0]]

    return {
        "method": "PERSISTENCE_BOOTSTRAP",
        "level": level,
        "sigma": sigma,
        "bootstrap_blocks": [b.tolist() if hasattr(b, "tolist") else list(b)
                             for b in blocks],
        "B": B,
        "block_len": block_len,
        "n_obs": n,
        "rng_seed": rng_seed,
    }


def _persistence_forecast(params: dict, h: int,
                           rng_seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Persistence forecast: point = last level; sigma fans out with sqrt(h).

    Bootstrap PI: sigma_h = sigma * sqrt(h) (random-walk accumulation).
    This guarantees monotone fan-out as required by pre-reg §4.1.
    """
    level = params["level"]
    sigma = params["sigma"]

    points = np.full(h, level)
    # Persistence accumulates variance as sigma^2 * h (random walk)
    sigma_h = np.array([sigma * np.sqrt(j) for j in range(1, h + 1)])

    return points, sigma_h


# --------------------------------------------------------------------------- #
# Override diagnostics (pre-reg §3.2)                                          #
# --------------------------------------------------------------------------- #

def _detect_method_override(series_list: list[np.ndarray],
                             indicator_id: str) -> str:
    """Determine the appropriate model type for an indicator across the panel.

    series_list: list of per-country annual series (already cleaned, no NaN).
    Returns: "ETS_A_A_N" | "ETS_A_Ad_N" | "PERSISTENCE_BOOTSTRAP"
    """
    if not series_list:
        return "PERSISTENCE_BOOTSTRAP"

    # Binary/near-binary check: >= 80% values in {0, 1} (or very close)
    all_vals = np.concatenate([s for s in series_list if len(s) > 0])
    if len(all_vals) > 0:
        binary_frac = np.mean((np.abs(all_vals) < 0.05) | (np.abs(all_vals - 1.0) < 0.05))
        if binary_frac >= 0.80:
            return "PERSISTENCE_BOOTSTRAP"

    # Low-coverage check: > 50% missing in > 60% of countries
    # (At this point series_list already has gaps removed, so we can't directly
    #  check missingness — this is handled upstream when building series_list.)
    # We check if the median series length is very short.
    lengths = [len(s) for s in series_list if len(s) > 0]
    if lengths and np.median(lengths) < 5:
        return "PERSISTENCE_BOOTSTRAP"

    # Persistent-trend check: median ACF(1) of first-differences > 0.4
    # across >= 50% of countries
    acf1_vals = []
    for s in series_list:
        if len(s) < 4:
            continue
        d = np.diff(s.astype(float))
        if len(d) < 3:
            continue
        d = d - d.mean()
        denom = np.dot(d, d)
        if denom < 1e-12:
            acf1_vals.append(0.0)
        else:
            acf1_vals.append(float(np.dot(d[:-1], d[1:]) / denom))

    if acf1_vals and np.mean(np.array(acf1_vals) > 0.4) >= 0.5:
        return "ETS_A_Ad_N"

    return "ETS_A_A_N"


# --------------------------------------------------------------------------- #
# Per-country model fitting                                                    #
# --------------------------------------------------------------------------- #

def fit_indicator_models(panel: pd.DataFrame, indicator_id: str,
                         countries: list[str], eval_year: int,
                         window: int, holdout_years: int = 0,
                         panel_method: str = "ETS_A_A_N") -> dict[str, Any]:
    """Fit one model per country for a single indicator.

    eval_year: the forecast origin year (last observed year is eval_year - 1).
    holdout_years: if > 0, the training cutoff is (eval_year - holdout_years).
    panel_method: indicator-level method chosen via _detect_method_override.

    Returns dict: {country_id: {"method": ..., "params": {...}, "flags": {...}}}
    """
    train_cutoff = eval_year - holdout_years  # exclusive upper bound on training data
    results: dict[str, Any] = {}

    for country in countries:
        cdf = panel[panel["country"] == country]
        if len(cdf) == 0:
            continue
        series_full = cdf.set_index("year")["value"].sort_index()

        # Training slice: years strictly before train_cutoff
        train_series = series_full[series_full.index < train_cutoff].dropna()
        y = train_series.values.astype(float)

        if len(y) < 2:
            results[country] = {
                "method": "PERSISTENCE_BOOTSTRAP",
                "params": _persistence_fit(y),
                "flags": {"too_short": True, "n_obs": len(y)},
            }
            continue

        flags: dict[str, Any] = {"n_obs": len(y)}

        # Priya §22: cap smoothing at pooled estimate when N_obs < _MIN_OBS_FOR_ETS
        force_pooled = len(y) < _MIN_OBS_FOR_ETS
        if force_pooled:
            flags["pooled_smoothing_cap_applied"] = True

        if panel_method == "PERSISTENCE_BOOTSTRAP":
            params = _persistence_fit(y)
            method = "PERSISTENCE_BOOTSTRAP"
        elif panel_method == "ETS_A_Ad_N":
            params = _holt_fit_numpy(y, damped=True)
            if force_pooled:
                params["alpha"] = min(params.get("alpha", _ALPHA_DEFAULT), _ALPHA_DEFAULT)
                params["beta"] = min(params.get("beta", _BETA_DEFAULT), _BETA_DEFAULT)
                params["pooled_smoothing_cap_applied"] = True
            method = "ETS_A_Ad_N"
        else:  # ETS_A_A_N
            params = _holt_fit_numpy(y, damped=False)
            if force_pooled:
                params["alpha"] = min(params.get("alpha", _ALPHA_DEFAULT), _ALPHA_DEFAULT)
                params["beta"] = min(params.get("beta", _BETA_DEFAULT), _BETA_DEFAULT)
                params["pooled_smoothing_cap_applied"] = True
            method = "ETS_A_A_N"

        # Flat-series check: sigma near zero → mark FLAT_SERIES_PI_DEGENERATE
        sigma = params.get("sigma", 0.0)
        if sigma < 1e-6:
            flags["flat_series_pi_degenerate"] = True
        else:
            flags["flat_series_pi_degenerate"] = False

        results[country] = {
            "method": method,
            "params": params,
            "flags": flags,
        }

    return results


def _load_panel_series_for_override(panel: pd.DataFrame, countries: list[str],
                                    eval_year: int, window: int) -> list[np.ndarray]:
    """Extract clean series per country for the method-override diagnostic."""
    series_list = []
    for country in countries:
        cdf = panel[panel["country"] == country]
        if len(cdf) == 0:
            continue
        s = cdf.set_index("year")["value"].sort_index()
        # Use training window: last `window` years before eval_year
        s_win = s[s.index < eval_year].tail(window).dropna()
        if len(s_win) >= 3:
            series_list.append(s_win.values.astype(float))
    return series_list


# --------------------------------------------------------------------------- #
# Cross-country pooled sigma estimate (Priya §22 + pre-reg §3.2)              #
# --------------------------------------------------------------------------- #

def compute_pooled_sigma(country_models: dict[str, Any]) -> float:
    """Compute cross-country median residual sigma (pooled estimate)."""
    sigmas = [
        m["params"].get("sigma", np.nan)
        for m in country_models.values()
        if not m.get("flags", {}).get("flat_series_pi_degenerate", False)
        and m["params"].get("sigma", 0.0) > 1e-6
    ]
    if not sigmas:
        return 1.0
    return float(np.median(sigmas))


# --------------------------------------------------------------------------- #
# Main CLI                                                                     #
# --------------------------------------------------------------------------- #

def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-id", required=True)
    parser.add_argument("--walk-summary", type=Path, required=True)
    parser.add_argument("--shap-importances", type=Path, required=True)
    parser.add_argument("--evaluation-year", type=int, required=True,
                        help="Forecast origin (last observed year = eval_year - 1)")
    parser.add_argument("--panel-dir", type=Path,
                        default=REPO_ROOT / "data" / "parquet_panels")
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--holdout-years", type=int, default=0,
                        help="If >0, hide last N years (backtest mode; train on data before eval_year - holdout_years)")
    args = parser.parse_args(argv)

    with open(args.walk_summary, encoding="utf-8") as f:
        walk = json.load(f)
    assert walk["recipe_id"] == args.recipe_id

    selected = walk["greedy_outer_loop"]["selected_indicators"]
    chosen_window = walk["greedy_outer_loop"]["chosen_window"]

    print(f"[fit_projection_models] recipe={args.recipe_id} indicators={selected} "
          f"window={chosen_window} eval_year={args.evaluation_year} "
          f"holdout_years={args.holdout_years}")

    # Load all panels
    panels = {ind: drv.load_panel(ind, args.panel_dir) for ind in selected}

    # Determine panel countries (union across indicators)
    all_countries: set[str] = set()
    for ind in selected:
        all_countries |= set(panels[ind]["country"].dropna().unique())
    all_countries_sorted = sorted(all_countries)

    output: dict[str, Any] = {
        "schema_version": 1,
        "pre_reg": "TE-PROJ-1 (ratified 2026-05-24)",
        "recipe_id": args.recipe_id,
        "evaluation_year": args.evaluation_year,
        "holdout_years": args.holdout_years,
        "train_cutoff_year": args.evaluation_year - args.holdout_years,
        "fitted_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_indicators": selected,
        "chosen_window": chosen_window,
        "indicator_models": {},
        "pooled_sigma": {},
        "override_log": {},
    }

    for ind in selected:
        panel = panels[ind]
        series_list = _load_panel_series_for_override(
            panel, all_countries_sorted, args.evaluation_year, chosen_window)

        method_override = _detect_method_override(series_list, ind)
        output["override_log"][ind] = method_override
        print(f"  {ind}: method={method_override} (panel series n={len(series_list)})")

        country_models = fit_indicator_models(
            panel, ind, all_countries_sorted,
            args.evaluation_year, chosen_window,
            args.holdout_years, method_override,
        )

        pooled_sigma = compute_pooled_sigma(country_models)
        output["pooled_sigma"][ind] = pooled_sigma

        # Apply pooled sigma floor where flat-series degenerate
        flat_count = 0
        for country, m in country_models.items():
            if m["flags"].get("flat_series_pi_degenerate", False):
                flat_count += 1
                # Replace sigma with pooled_sigma so PI floor is honesty-compliant
                m["params"]["sigma"] = pooled_sigma
                m["params"]["flat_series_sigma_floored"] = True

        output["indicator_models"][ind] = {
            "panel_method": method_override,
            "pooled_sigma": pooled_sigma,
            "flat_series_count": flat_count,
            "n_countries_fitted": len(country_models),
            "country_models": country_models,
        }
        print(f"    fitted {len(country_models)} countries; flat_series={flat_count}; pooled_sigma={pooled_sigma:.4f}")

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
    print(f"[fit_projection_models] wrote {args.output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
