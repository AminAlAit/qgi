"""Phase D D6 — Cross-recipe correlation tensor over time.

Per docs/specs/internal/ops/ml-track/stage-2-amendment-2026-05-05.md
(commit `04fa5fb`) D6 — Ji-Hoon Yamamoto-Costa's "free inference"
proposal at the post-PoC trio convening.

## What this measures

For each test year t, computes the (n_recipes × n_recipes) correlation
matrix of predicted_probability across countries:

    M_t[i, j] = correlation(predictions[country, recipe_i, t],
                            predictions[country, recipe_j, t])
                computed across all countries with predictions at year t

Tracks how this matrix changes over time (2022, 2023, 2024, 2025).

## What the structure tells us

- **Stable matrix over time** → recipes measure genuinely distinct
  phenomena (low cross-correlation) OR consistently coupled phenomena
  (high cross-correlation)
- **Shifting matrix over time** → regime change / conflict onset /
  structural shift in the world being modeled
- **Persistently high cross-correlations** for specific recipe pairs
  → those recipes may be informationally redundant (consider
  consolidation in future work)

## Free inference

This is computed from EXISTING predictions.json artifacts. No new
model training, no new data. Pure post-hoc analysis.

## Pure functions; tests in tests/test_cross_recipe_corr.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_MIN_COUNTRIES_PER_YEAR = 30


@dataclass
class CorrelationMatrixSnapshot:
    """Single-year correlation matrix snapshot."""

    year: int
    n_countries: int
    n_recipes: int
    recipe_ids: list[str]
    matrix: list[list[float]]  # n_recipes × n_recipes
    matrix_method: str  # "pearson" | "spearman"
    skip_reason: str | None = None


def predictions_to_country_recipe_matrix(
    predictions: list[dict[str, Any]],
    year: int,
) -> tuple[pd.DataFrame, list[str]]:
    """Pivot predictions list to a (countries × recipes) DataFrame for
    a single year.

    Parameters
    ----------
    predictions : list of {country, year, recipe_id, predicted_probability, ...}
    year : the year to filter on

    Returns
    -------
    (matrix, recipe_ids) where matrix is a DataFrame with one row per
    country and one column per recipe.
    """
    df = pd.DataFrame(predictions)
    if not all(c in df.columns for c in ("country", "year", "recipe_id", "predicted_probability")):
        msg = "predictions missing required keys: country/year/recipe_id/predicted_probability"
        raise ValueError(msg)
    sub = df[df["year"] == year]
    if sub.empty:
        return pd.DataFrame(), []
    pivot = sub.pivot_table(
        index="country",
        columns="recipe_id",
        values="predicted_probability",
        aggfunc="mean",
    )
    recipe_ids = sorted(pivot.columns.tolist())
    return pivot[recipe_ids], recipe_ids


def compute_correlation_matrix(
    cr_matrix: pd.DataFrame,
    method: str = "pearson",
) -> np.ndarray:
    """Recipe-recipe correlation across countries.

    Parameters
    ----------
    cr_matrix : DataFrame (n_countries × n_recipes)
    method : 'pearson' or 'spearman'

    Returns
    -------
    ndarray (n_recipes × n_recipes) symmetric correlation matrix
    """
    if method not in ("pearson", "spearman"):
        msg = f"method must be 'pearson' or 'spearman', got {method!r}"
        raise ValueError(msg)
    if cr_matrix.empty or cr_matrix.shape[1] == 0:
        return np.zeros((0, 0), dtype=float)
    return cr_matrix.corr(method=method).to_numpy()


def compute_per_year_snapshots(
    predictions: list[dict[str, Any]],
    *,
    method: str = "pearson",
    min_countries_per_year: int = DEFAULT_MIN_COUNTRIES_PER_YEAR,
) -> list[CorrelationMatrixSnapshot]:
    """Loop over years in `predictions`; compute one correlation snapshot
    per year. Skips years with < min_countries_per_year countries.
    """
    df = pd.DataFrame(predictions)
    years = sorted(df["year"].unique())
    snapshots: list[CorrelationMatrixSnapshot] = []
    for year in years:
        cr_matrix, recipe_ids = predictions_to_country_recipe_matrix(predictions, year)
        n_countries = len(cr_matrix)
        if n_countries < min_countries_per_year:
            snapshots.append(CorrelationMatrixSnapshot(
                year=int(year), n_countries=n_countries, n_recipes=len(recipe_ids),
                recipe_ids=recipe_ids, matrix=[], matrix_method=method,
                skip_reason=f"insufficient_countries_n_{n_countries}_below_{min_countries_per_year}",
            ))
            continue
        # Drop countries with NaN in any recipe (alignment requirement for
        # correlation matrix).
        clean = cr_matrix.dropna(how="any")
        if len(clean) < min_countries_per_year:
            snapshots.append(CorrelationMatrixSnapshot(
                year=int(year), n_countries=int(len(clean)), n_recipes=len(recipe_ids),
                recipe_ids=recipe_ids, matrix=[], matrix_method=method,
                skip_reason=f"insufficient_countries_after_dropna_n_{len(clean)}_below_{min_countries_per_year}",
            ))
            continue
        corr = compute_correlation_matrix(clean, method=method)
        snapshots.append(CorrelationMatrixSnapshot(
            year=int(year), n_countries=int(len(clean)), n_recipes=len(recipe_ids),
            recipe_ids=recipe_ids,
            matrix=[[float(corr[i, j]) for j in range(corr.shape[1])]
                    for i in range(corr.shape[0])],
            matrix_method=method,
            skip_reason=None,
        ))
    return snapshots


def matrix_stability_over_time(
    snapshots: list[CorrelationMatrixSnapshot],
) -> dict[str, Any]:
    """Frobenius-norm distance between consecutive years' matrices.

    Returns dict with `per_year_distance` (list of (year_pair, distance))
    and `mean_distance` summary.

    Smaller distance → more stable structure. Larger → regime shift.
    """
    valid = [s for s in snapshots if s.skip_reason is None and s.matrix]
    if len(valid) < 2:
        return {"per_year_distance": [], "mean_distance": float("nan"),
                "n_year_pairs": 0,
                "skip_reason": "fewer_than_2_valid_snapshots"}
    # Find the recipe set common to all valid snapshots
    common_recipes = set(valid[0].recipe_ids)
    for s in valid[1:]:
        common_recipes &= set(s.recipe_ids)
    common_list = sorted(common_recipes)
    if len(common_list) < 2:
        return {"per_year_distance": [], "mean_distance": float("nan"),
                "n_year_pairs": 0,
                "skip_reason": "fewer_than_2_common_recipes"}

    def _restrict(snap: CorrelationMatrixSnapshot) -> np.ndarray:
        # Restrict the snapshot's matrix to common_list ordering
        idx = [snap.recipe_ids.index(r) for r in common_list]
        m = np.asarray(snap.matrix, dtype=float)
        return m[np.ix_(idx, idx)]

    distances: list[dict[str, Any]] = []
    for i in range(len(valid) - 1):
        m_prev = _restrict(valid[i])
        m_next = _restrict(valid[i + 1])
        # Frobenius norm of difference
        diff = m_next - m_prev
        dist = float(np.linalg.norm(diff, ord="fro"))
        distances.append({
            "year_from": valid[i].year,
            "year_to": valid[i + 1].year,
            "frobenius_distance": dist,
        })
    mean_dist = float(np.mean([d["frobenius_distance"] for d in distances])) \
        if distances else float("nan")
    return {
        "per_year_distance": distances,
        "mean_distance": mean_dist,
        "n_year_pairs": len(distances),
        "n_common_recipes": len(common_list),
        "common_recipes": common_list,
    }


def find_persistent_high_corrs(
    snapshots: list[CorrelationMatrixSnapshot],
    *,
    threshold: float = 0.7,
) -> list[dict[str, Any]]:
    """Pairs of recipes with correlation > threshold in EVERY valid year.

    These pairs may be informationally redundant — flag for inspection.
    """
    valid = [s for s in snapshots if s.skip_reason is None and s.matrix]
    if len(valid) < 2:
        return []
    common_recipes = set(valid[0].recipe_ids)
    for s in valid[1:]:
        common_recipes &= set(s.recipe_ids)
    common_list = sorted(common_recipes)

    persistent: list[dict[str, Any]] = []
    n = len(common_list)
    for i in range(n):
        for j in range(i + 1, n):
            ri, rj = common_list[i], common_list[j]
            corrs_per_year: list[float] = []
            all_above = True
            for s in valid:
                idx_i = s.recipe_ids.index(ri)
                idx_j = s.recipe_ids.index(rj)
                c = float(s.matrix[idx_i][idx_j])
                corrs_per_year.append(c)
                if abs(c) <= threshold:
                    all_above = False
            if all_above:
                persistent.append({
                    "recipe_a": ri,
                    "recipe_b": rj,
                    "corrs_per_year": corrs_per_year,
                    "mean_abs_corr": float(np.mean([abs(c) for c in corrs_per_year])),
                })
    return persistent
