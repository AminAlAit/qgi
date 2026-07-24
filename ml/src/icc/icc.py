"""Phase D D1 — Intraclass Correlation Coefficient (ICC) for fixed-effect-proxy detection.

Per docs/specs/internal/ops/ml-track/stage-2-amendment-2026-05-05.md
(commit `04fa5fb`) D1: replace the binary `fixed_effect_suspect`
flag with a continuous ICC shrinkage weight per feature.

## What ICC measures

For each feature `f` in the engineered panel:

    ICC(f) = sigma_between_country^2 / (sigma_between_country^2 + sigma_within_country^2)

Where:
- sigma_between_country^2 = variance of country-level mean(f) across countries
- sigma_within_country^2  = mean across countries of within-country variance(f, year)

Interpretation:
- ICC ≈ 1.0 → feature mostly varies BETWEEN countries (country-identity proxy)
- ICC ≈ 0.0 → feature mostly varies WITHIN countries (true dynamic signal)
- ICC ≈ 0.5 → roughly equal between/within variance

## Why this replaces the binary flag

The Stage 2 Prereq D SHAP fingerprint output uses a binary
`fixed_effect_suspect` flag (per-feature std < panel median std).
That binary loses the GRADIENT — a feature with ICC=0.30 and one
with ICC=0.85 are treated identically (both "non-suspect" or both
"suspect" depending on threshold). Continuous ICC + uncertainty (CI
on the estimate via bootstrap) lets head training apply
proportional regularization.

## Per-feature, not per-(feature, recipe), at this stage

The Stage 2 amendment proposed a 104 × 23 ICC matrix. In practice,
since all recipes train on the same 2014-2021 engineered panel, ICC
collapses to per-feature (each recipe head sees the same 104-vector).
A per-(feature, recipe) variant — ICC computed on a recipe-conditional
data slice — is a future extension.

## Pure functions; tests in tests/test_icc.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_BOOTSTRAP_N = 200
DEFAULT_BOOTSTRAP_SEED = 0
DEFAULT_MIN_COUNTRIES = 3
DEFAULT_MIN_OBSERVATIONS_PER_COUNTRY = 2


@dataclass
class ICCResult:
    """Single-feature ICC estimate with bootstrap CI."""

    icc: float
    ci_lower: float
    ci_upper: float
    sigma_between: float
    sigma_within: float
    n_countries_used: int
    n_observations_used: int
    skip_reason: str | None = None
    soft_flag_high_icc: bool = field(default=False)
    """ICC > 0.7 => high country-identity-proxy concern."""


def compute_icc(
    values: np.ndarray,
    country_ids: np.ndarray,
    *,
    min_countries: int = DEFAULT_MIN_COUNTRIES,
    min_observations_per_country: int = DEFAULT_MIN_OBSERVATIONS_PER_COUNTRY,
) -> ICCResult:
    """Compute single-feature ICC via one-way variance partitioning.

    Parameters
    ----------
    values : ndarray of shape (N,)
        Feature values, one per (country, year) cell. NaN-filtered.
    country_ids : ndarray of shape (N,)
        Country identifier for each cell.
    min_countries : int
        Skip if fewer countries have testable data.
    min_observations_per_country : int
        Drop countries with fewer observations than this.

    Returns
    -------
    ICCResult with `icc`, `ci_lower`/`ci_upper` populated by the caller
    via bootstrap (this function returns the point estimate; bootstrap
    CI is computed via `bootstrap_icc_ci` separately for testability).
    """
    values = np.asarray(values, dtype=float)
    country_ids = np.asarray(country_ids)

    if values.shape != country_ids.shape:
        msg = f"shape mismatch: values {values.shape} vs country_ids {country_ids.shape}"
        raise ValueError(msg)

    # Drop NaN values
    valid = ~np.isnan(values)
    values = values[valid]
    country_ids = country_ids[valid]

    if values.size == 0:
        return ICCResult(
            icc=float("nan"), ci_lower=float("nan"), ci_upper=float("nan"),
            sigma_between=float("nan"), sigma_within=float("nan"),
            n_countries_used=0, n_observations_used=0,
            skip_reason="no_observations_after_nan_filter",
        )

    # Group by country
    df = pd.DataFrame({"value": values, "country": country_ids})
    grouped = df.groupby("country")["value"]
    sizes = grouped.size()
    # Filter countries with enough observations
    eligible_countries = sizes[sizes >= min_observations_per_country].index.tolist()
    if len(eligible_countries) < min_countries:
        return ICCResult(
            icc=float("nan"), ci_lower=float("nan"), ci_upper=float("nan"),
            sigma_between=float("nan"), sigma_within=float("nan"),
            n_countries_used=len(eligible_countries),
            n_observations_used=int(sizes.loc[eligible_countries].sum()),
            skip_reason=f"insufficient_countries_n_{len(eligible_countries)}_below_{min_countries}",
        )
    sub = df[df["country"].isin(eligible_countries)]
    grouped = sub.groupby("country")["value"]

    # Country means + within-country variance
    country_means = grouped.mean()
    country_within_var = grouped.var(ddof=1)  # sample variance per country
    # Some countries may have NaN within-var (n=1); exclude them from within calculation
    valid_within = country_within_var.dropna()
    if valid_within.empty:
        return ICCResult(
            icc=float("nan"), ci_lower=float("nan"), ci_upper=float("nan"),
            sigma_between=float("nan"), sigma_within=float("nan"),
            n_countries_used=int(sub["country"].nunique()),
            n_observations_used=int(len(sub)),
            skip_reason="no_country_with_within_year_variance",
        )

    sigma_within = float(valid_within.mean())
    sigma_between = float(country_means.var(ddof=1))

    denom = sigma_between + sigma_within
    if denom <= 0.0:
        # All values identical → no variance to partition; ICC undefined
        return ICCResult(
            icc=float("nan"), ci_lower=float("nan"), ci_upper=float("nan"),
            sigma_between=sigma_between, sigma_within=sigma_within,
            n_countries_used=int(sub["country"].nunique()),
            n_observations_used=int(len(sub)),
            skip_reason="zero_total_variance",
        )

    icc = float(sigma_between / denom)
    return ICCResult(
        icc=icc,
        ci_lower=float("nan"),  # caller fills via bootstrap
        ci_upper=float("nan"),
        sigma_between=sigma_between,
        sigma_within=sigma_within,
        n_countries_used=int(sub["country"].nunique()),
        n_observations_used=int(len(sub)),
        skip_reason=None,
        soft_flag_high_icc=(icc > 0.7),
    )


def bootstrap_icc_ci(
    values: np.ndarray,
    country_ids: np.ndarray,
    *,
    n_bootstrap: int = DEFAULT_BOOTSTRAP_N,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    confidence: float = 0.95,
    min_countries: int = DEFAULT_MIN_COUNTRIES,
    min_observations_per_country: int = DEFAULT_MIN_OBSERVATIONS_PER_COUNTRY,
) -> tuple[float, float, float]:
    """Bootstrap percentile 95% CI on ICC, resampling COUNTRIES with
    replacement (cluster bootstrap).

    Returns
    -------
    (icc_point, ci_lower, ci_upper)

    See `bootstrap_icc_ci_with_result` for a richer return shape that
    avoids the double-compute pattern when callers need both the CI
    and the underlying ICCResult details (sigma_between, sigma_within,
    skip_reason, etc.).
    """
    _result, ci_lo, ci_hi = bootstrap_icc_ci_with_result(
        values, country_ids,
        n_bootstrap=n_bootstrap, seed=seed, confidence=confidence,
        min_countries=min_countries,
        min_observations_per_country=min_observations_per_country,
    )
    return (_result.icc, ci_lo, ci_hi)


def bootstrap_icc_ci_with_result(
    values: np.ndarray,
    country_ids: np.ndarray,
    *,
    n_bootstrap: int = DEFAULT_BOOTSTRAP_N,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    confidence: float = 0.95,
    min_countries: int = DEFAULT_MIN_COUNTRIES,
    min_observations_per_country: int = DEFAULT_MIN_OBSERVATIONS_PER_COUNTRY,
) -> tuple["ICCResult", float, float]:
    """Same as `bootstrap_icc_ci` but returns the full ICCResult object
    alongside the CI bounds. Use this in batch orchestrators to avoid
    re-computing the point estimate per feature (QA review of PR
    #32 caught the double-call inefficiency).

    Returns
    -------
    (point_result, ci_lower, ci_upper)
    """
    if not 0 < confidence < 1:
        msg = f"confidence must be in (0, 1), got {confidence}"
        raise ValueError(msg)

    point_result = compute_icc(
        values, country_ids,
        min_countries=min_countries,
        min_observations_per_country=min_observations_per_country,
    )
    if not np.isfinite(point_result.icc):
        return (point_result, float("nan"), float("nan"))

    # Build a per-country index map
    valid = ~np.isnan(values)
    values = np.asarray(values, dtype=float)[valid]
    country_ids = np.asarray(country_ids)[valid]
    unique_countries = np.unique(country_ids)
    country_to_indices = {c: np.where(country_ids == c)[0] for c in unique_countries}

    rng = np.random.default_rng(seed)
    boot_iccs: list[float] = []
    for _ in range(n_bootstrap):
        # Resample countries with replacement (cluster bootstrap)
        sampled_countries = rng.choice(unique_countries, size=len(unique_countries), replace=True)
        sampled_idx_parts = [country_to_indices[c] for c in sampled_countries]
        sampled_idx = np.concatenate(sampled_idx_parts)
        # Synthesize new country IDs (since same country may appear multiple times,
        # we treat each draw as a distinct cluster)
        new_country_ids = np.concatenate([
            np.full_like(idx, fill_value=i, dtype=object)
            for i, idx in enumerate(sampled_idx_parts)
        ])
        result = compute_icc(
            values[sampled_idx], new_country_ids,
            min_countries=min_countries,
            min_observations_per_country=min_observations_per_country,
        )
        if np.isfinite(result.icc):
            boot_iccs.append(result.icc)

    if not boot_iccs:
        return (point_result, float("nan"), float("nan"))

    arr = np.asarray(boot_iccs, dtype=float)
    alpha = (1 - confidence) / 2.0
    ci_lo = float(np.percentile(arr, 100 * alpha))
    ci_hi = float(np.percentile(arr, 100 * (1 - alpha)))
    return (point_result, ci_lo, ci_hi)


def compute_icc_for_features(
    panel_long: pd.DataFrame,
    feature_columns: list[str],
    *,
    country_col: str = "country",
    year_col: str = "year",
    window_start: int | None = None,
    window_end: int | None = None,
    n_bootstrap: int = DEFAULT_BOOTSTRAP_N,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    min_countries: int = DEFAULT_MIN_COUNTRIES,
    min_observations_per_country: int = DEFAULT_MIN_OBSERVATIONS_PER_COUNTRY,
) -> dict[str, ICCResult]:
    """Compute ICC + bootstrap CI for each feature in `feature_columns`.

    Expected input shape: WIDE-format panel with `country`, `year`, and
    one column per feature (matches the trainer's `build_feature_panel`
    output).

    Returns
    -------
    dict[feature_name, ICCResult]
    """
    required = {country_col, year_col, *feature_columns}
    missing = required - set(panel_long.columns)
    if missing:
        msg = f"panel_long missing columns: {sorted(missing)}"
        raise ValueError(msg)

    # Apply window filter if specified
    sub = panel_long
    if window_start is not None:
        sub = sub[sub[year_col] >= window_start]
    if window_end is not None:
        sub = sub[sub[year_col] <= window_end]

    if sub.empty:
        return {feat: ICCResult(
            icc=float("nan"), ci_lower=float("nan"), ci_upper=float("nan"),
            sigma_between=float("nan"), sigma_within=float("nan"),
            n_countries_used=0, n_observations_used=0,
            skip_reason="no_observations_in_window",
        ) for feat in feature_columns}

    country_array = sub[country_col].to_numpy()
    out: dict[str, ICCResult] = {}
    for feat in feature_columns:
        values = sub[feat].to_numpy(dtype=float)
        # Use _with_result variant to avoid double-compute (QA review
        # of PR #32 caught the pattern: previous code called compute_icc
        # twice per feature, doubling wall time at scale).
        point_result, ci_lo, ci_hi = bootstrap_icc_ci_with_result(
            values, country_array,
            n_bootstrap=n_bootstrap,
            seed=seed,
            min_countries=min_countries,
            min_observations_per_country=min_observations_per_country,
        )
        point_result.ci_lower = ci_lo
        point_result.ci_upper = ci_hi
        out[feat] = point_result
    return out


def shrinkage_weight_from_icc(icc: float) -> float:
    """Convert ICC to a head-training shrinkage weight in [0, 1].

    A simple linear conversion: weight = 1 - icc.
    - ICC = 0 → weight = 1 (full feature weight)
    - ICC = 1 → weight = 0 (fully suppressed)
    - ICC = 0.5 → weight = 0.5

    NaN ICC (skipped feature) → weight = 0 (conservatively suppress).

    More sophisticated transformations (sigmoid, threshold) are possible
    but this linear form is the simplest defensible default.
    """
    if not np.isfinite(icc):
        return 0.0
    return float(max(0.0, min(1.0, 1.0 - icc)))
