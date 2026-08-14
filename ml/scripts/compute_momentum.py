"""Compute retrospective momentum (trajectory direction) per country.

Capability #3 of the 5 new TE capabilities (te-new-capabilities-spec.md §3).

For each scored country, recomputes the SHAP-weighted cosine risk_score at
window-end offsets t=eval_year, t-1, t-2, t-3 (4 offsets total). The
canonical recipe profile stays FIXED (from the walk). Fits a least-squares
slope of risk_score vs year over the available offset-years. Sign = direction;
magnitude = pace.

Honesty gate (binding, spec §3):
  - Labelled RETROSPECTIVE / observed in the artifact; explicitly NOT a forecast.
  - Suppress (flag INSUFFICIENT_HISTORY) if < 3 of the 4 offset-years have data.

M8-R5 binding: discrimination/similarity layer only. This capability is the
honest cousin of the suppressed Holt-ETS forecast: it reports where the
country HAS BEEN going in trajectory-space; it claims nothing about where it
WILL go.

Usage:
    python scripts/compute_momentum.py \\
        --recipe-id foreign_intervention \\
        --scores-file qgi-data/reference/recipe-similarity-scores-foreign_intervention-2021.json \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --panel-dir data/parquet_panels \\
        --output-dir qgi-data/reference/ \\
        --evaluation-year 2021 \\
        --n-offsets 4

Output:
    momentum-{recipe_id}-{year}.json  (per-country direction, slope, scores_by_year)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402
from compute_recipe_country_similarity import (  # noqa: E402
    extract_country_trajectory,
    compute_country_recipe_similarity,
    build_canonical_profile_from_walk,
    prebake_zscore_distribution,
)

REPO_ROOT = SCRIPTS_DIR.parent

# ---------------------------------------------------------------------------
# Pre-registered constants (must not change after results are seen; spec §3)
# ---------------------------------------------------------------------------

MOMENTUM_EPS: float = 0.05
"""Score-points-per-year boundary between flat and directional.

Risk scores are on [0, 100]. A slope of < 0.05 risk-score-points/year
is considered flat (noise-level movement over 1 year). Pre-registered before
results are seen per te-new-capabilities-spec.md §3.
Rationale: 0.05 pts/yr = 0.20 pts over the 4-year window — a movement
smaller than this is indistinguishable from data noise at this scale.
"""

MIN_YEARS_AVAILABLE: int = 3
"""Minimum number of the 4 offset-years required to avoid INSUFFICIENT_HISTORY."""

M8_R5_NOTE: str = (
    "MOMENTUM (RETROSPECTIVE/observed only): This capability reports where this "
    "country HAS BEEN moving in similarity-to-crisis-profile space over the past "
    "1-3 years. It is explicitly NOT a forecast or projection — it does not claim "
    "the observed direction will continue. "
    "This is the honest cousin of the forward-projection that was deliberately "
    "SUPPRESSED at the honesty gate: that capability claimed to project future "
    "trajectory; this one reports only observed past movement. "
    "M8-R5 binding: discrimination layer only; never calibrated probability."
)


# ---------------------------------------------------------------------------
# Core pure functions
# ---------------------------------------------------------------------------


def fit_slope(years: list[int], scores: list[float]) -> float:
    """Least-squares slope of scores vs years.

    Uses simple OLS: slope = Cov(years, scores) / Var(years).
    Returns 0.0 when fewer than 2 points (degenerate case).

    Args:
        years:  List of year values (e.g. [2018, 2019, 2020, 2021]).
        scores: Corresponding risk_scores.

    Returns:
        Slope in risk-score-points-per-year (float).
    """
    n = len(years)
    if n < 2:
        return 0.0
    x = np.array(years, dtype=float)
    y = np.array(scores, dtype=float)
    x_mean = x.mean()
    y_mean = y.mean()
    cov = float(np.sum((x - x_mean) * (y - y_mean)))
    var = float(np.sum((x - x_mean) ** 2))
    if var < 1e-12:
        return 0.0
    return cov / var


def classify_direction(slope: float, eps: float = MOMENTUM_EPS) -> str:
    """Classify slope as 'rising', 'flat', or 'falling'.

    Boundaries are inclusive for 'flat': |slope| <= eps → 'flat'.
    This ensures the exact eps boundary does not spuriously trigger
    rising/falling.

    Args:
        slope: Least-squares slope from fit_slope.
        eps:   Flat-zone half-width in risk-score-points/year.

    Returns:
        'rising' | 'flat' | 'falling'
    """
    if slope > eps:
        return "rising"
    elif slope < -eps:
        return "falling"
    else:
        return "flat"


def compute_country_momentum(
    target_year: int,
    score_fn: Callable[[int], float | None],
    n_offsets: int = 4,
    eps: float = MOMENTUM_EPS,
    min_years: int = MIN_YEARS_AVAILABLE,
) -> dict[str, Any]:
    """Compute retrospective momentum for one country.

    Args:
        target_year: The evaluation year (e.g. 2021).
        score_fn:    Callable(eval_year) → float risk_score or None if data
                     unavailable for that year. Caller provides this closure
                     over the country/panels/canonical/shap_weights.
        n_offsets:   Number of offset years to evaluate (default 4: t, t-1, t-2, t-3).
        eps:         Flat-zone half-width in risk-score-points/year.
        min_years:   Minimum available years before suppressing (default 3).

    Returns:
        {
          "scores_by_year":   {year: score_or_None, ...},  # int keys
          "slope_per_year":   float,   # risk-score-points / year
          "direction":        str,     # 'rising' | 'flat' | 'falling'
          "n_years_available": int,
          "suppressed":       bool,
          "flag":             str | None,   # 'INSUFFICIENT_HISTORY' or None
          "observation_label": str,         # always 'RETROSPECTIVE/observed'
        }
    """
    scores_by_year: dict[int, float | None] = {}
    for offset in range(n_offsets):
        y = target_year - offset
        scores_by_year[y] = score_fn(y)

    available_years = [y for y, s in scores_by_year.items() if s is not None]
    available_scores = [scores_by_year[y] for y in available_years]  # type: ignore[index]
    n_available = len(available_years)

    suppressed = n_available < min_years
    flag = "INSUFFICIENT_HISTORY" if suppressed else None

    if suppressed or n_available < 2:
        slope = 0.0
    else:
        slope = fit_slope(available_years, available_scores)

    direction = classify_direction(slope, eps=eps)

    return {
        "scores_by_year": scores_by_year,
        "slope_per_year": float(slope),
        "direction": direction,
        "n_years_available": n_available,
        "suppressed": suppressed,
        "flag": flag,
        "observation_label": "RETROSPECTIVE/observed — NOT a forecast or projection",
    }


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recipe-id", required=True,
                   help="Recipe identifier (e.g. foreign_intervention)")
    p.add_argument("--scores-file", type=Path, required=True,
                   help="Path to recipe-similarity-scores-{recipe}-{year}.json")
    p.add_argument("--walk-summary", type=Path, required=True,
                   help="Path to f-ml-1-poc-summary.json from the walk run")
    p.add_argument("--panel-dir", type=Path,
                   default=REPO_ROOT / "data" / "parquet_panels",
                   help="Directory containing per-indicator parquet panels")
    p.add_argument("--output-dir", type=Path, required=True,
                   help="Directory to write momentum-{recipe}-{year}.json")
    p.add_argument("--evaluation-year", type=int, default=2021,
                   help="Target evaluation year (default: 2021)")
    p.add_argument("--n-offsets", type=int, default=4,
                   help="Number of offset years to evaluate (default: 4 → t, t-1, t-2, t-3)")
    return p


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load scores artifact
    with open(args.scores_file, encoding="utf-8") as f:
        scores_data = json.load(f)
    assert scores_data["recipe_id"] == args.recipe_id, (
        f"Scores artifact recipe_id={scores_data['recipe_id']} != {args.recipe_id}"
    )
    scored_countries = scores_data["scores"]
    selected_indicators: list[str] = scores_data["selected_indicators"]
    chosen_window: int = scores_data["chosen_window"]
    shap_weights: dict[str, float] = scores_data["shap_importance_normalized"]

    # Load walk summary
    with open(args.walk_summary, encoding="utf-8") as f:
        walk = json.load(f)
    assert walk["recipe_id"] == args.recipe_id

    # Load panels
    panels: dict[str, pd.DataFrame] = {
        ind: drv.load_panel(ind, args.panel_dir) for ind in selected_indicators
    }

    # Build canonical from walk (FIXED; same canonical for all eval_year offsets)
    print("Building canonical recipe profile from walk (FIXED)...")
    recipe_canonical = build_canonical_profile_from_walk(
        walk, panels, chosen_window, selected_indicators
    )

    # Compute momentum for each scored country
    print(f"Computing momentum for {len(scored_countries)} scored countries...")
    results: dict[str, Any] = {}
    n_suppressed = 0
    n_rising = n_falling = n_flat = 0

    for target_country in sorted(scored_countries.keys()):
        def _make_score_fn(country: str) -> Callable[[int], float | None]:
            """Closure over country, panels, chosen_window, recipe_canonical, shap_weights."""
            def score_fn(eval_year: int) -> float | None:
                # Pre-bake z-distribution at eval_year (must be per eval_year, not cached)
                ind_dist = prebake_zscore_distribution(
                    args.panel_dir, selected_indicators, eval_year
                )
                country_traj: dict[str, np.ndarray] = {}
                for ind in selected_indicators:
                    t = extract_country_trajectory(
                        panels[ind], country, eval_year, chosen_window,
                        ind_dist=ind_dist[ind],
                    )
                    if t is not None:
                        country_traj[ind] = t
                if not country_traj:
                    return None
                sim = compute_country_recipe_similarity(
                    country_traj, recipe_canonical, shap_weights
                )
                return sim["risk_score"]
            return score_fn

        score_fn = _make_score_fn(target_country)
        momentum = compute_country_momentum(
            target_year=args.evaluation_year,
            score_fn=score_fn,
            n_offsets=args.n_offsets,
        )
        results[target_country] = momentum
        if momentum["suppressed"]:
            n_suppressed += 1
        elif momentum["direction"] == "rising":
            n_rising += 1
        elif momentum["direction"] == "falling":
            n_falling += 1
        else:
            n_flat += 1

    print(f"  Rising: {n_rising}  Falling: {n_falling}  Flat: {n_flat}  "
          f"Suppressed: {n_suppressed}")

    # Build artifact
    artifact = {
        "schema_version": 1,
        "capability": "momentum",
        "recipe_id": args.recipe_id,
        "evaluation_year": args.evaluation_year,
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "binding_provenance": {
            "spec": "docs/specs/internal/ops/ml-track/te-new-capabilities-spec.md §3",
            "m8_r5": "M8-R5 discrimination/similarity layer; RETROSPECTIVE/observed only; NOT a forecast",
            "momentum_eps": MOMENTUM_EPS,
            "min_years_available": MIN_YEARS_AVAILABLE,
            "canonical_fixed": "Recipe canonical profile FIXED from walk; same for all offset years",
            "z_dist_rebaked_per_offset_year": (
                "Panel-wide z-score distribution is independently pre-baked at each "
                "offset year (eval_year, eval_year-1, eval_year-2, eval_year-3) per "
                "Kwame production-ML rider: avoid on-the-fly recomputation at query time."
            ),
        },
        "m8_r5_note": M8_R5_NOTE,
        "selected_indicators": selected_indicators,
        "chosen_window": chosen_window,
        "n_offsets": args.n_offsets,
        "n_scored_countries": len(results),
        "n_suppressed_insufficient_history": n_suppressed,
        "summary": {
            "rising": n_rising,
            "falling": n_falling,
            "flat": n_flat,
            "suppressed": n_suppressed,
        },
        "results": results,
    }

    out_path = args.output_dir / f"momentum-{args.recipe_id}-{args.evaluation_year}.json"
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")

    # Print summary: top-10 rising + a few falling
    print()
    print(f"=== Momentum summary for {args.recipe_id} (eval_year={args.evaluation_year}) ===")
    rising = [
        (c, r) for c, r in results.items()
        if not r["suppressed"] and r["direction"] == "rising"
    ]
    rising.sort(key=lambda t: t[1]["slope_per_year"], reverse=True)
    for country, r in rising[:5]:
        scores_str = " ".join(
            f"{y}:{s:.1f}" if s is not None else f"{y}:N/A"
            for y, s in sorted(r["scores_by_year"].items())
        )
        print(f"  RISING   {country:30s}  slope={r['slope_per_year']:+.3f}  [{scores_str}]")
    falling = [
        (c, r) for c, r in results.items()
        if not r["suppressed"] and r["direction"] == "falling"
    ]
    falling.sort(key=lambda t: t[1]["slope_per_year"])
    for country, r in falling[:5]:
        scores_str = " ".join(
            f"{y}:{s:.1f}" if s is not None else f"{y}:N/A"
            for y, s in sorted(r["scores_by_year"].items())
        )
        print(f"  FALLING  {country:30s}  slope={r['slope_per_year']:+.3f}  [{scores_str}]")

    return 0


if __name__ == "__main__":
    sys.exit(_main())
