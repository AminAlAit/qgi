"""SHAP attribution + indicator fingerprint per recipe.

Implements Component 8 prong 3 (SHAP attribution sanity check) of
`docs/specs/internal/ops/ml-track/07-validation-framework.md` AND the
ML-Opus-track `ML indicator fingerprint` deliverable (= SHAP top-K per
recipe head, per founder's 2026-05-04 question).

Key decisions:

- Use LightGBM's built-in TreeSHAP via `predict(..., pred_contrib=True)`.
  Returns shape (n_samples, n_features + 1) — last column is the bias
  (a.k.a. expected value). We strip it for feature attribution.
- Global feature importance = mean |SHAP value| over the explanation
  set (typically the test set). This is the standard ML-practitioner
  default and is monotonic with `gain`-based importance under tree
  models.
- Per-indicator "time-series variance" reference: for each indicator,
  compute the per-country std over the training-window observations,
  then aggregate across countries by MEDIAN. This isolates within-
  country temporal variation and ignores between-country level
  differences (which are exactly what country fixed-effect proxies
  exploit).
- Fixed-effect-suspect flag fires when a top-K feature's panel-median
  within-country std is below the panel median across all indicators.
  Tariq's spec language: "indicators with time-series variance below
  median panel variance ... proxy for country fixed effects."

Output JSON shape::

    {
      "schema_version": 1,
      "generated_at_utc": "...",
      "purpose": "...",
      "method": {...},
      "policy": {...},
      "training_window": {"start": int, "end": int},
      "explanation_set": {"start": int, "end": int, "n_samples": int},
      "indicator_variance": {
        "definition": "median across countries of within-country std",
        "panel_median": float,
        "values": {indicator_id: float, ...}
      },
      "recipes": {
        recipe_id: {
          "n_samples_explained": int,
          "top_k": [
            {
              "rank": 1,
              "indicator_id": "...",
              "mean_abs_shap": 0.123,
              "within_country_std_median": 0.045,
              "variance_ratio_vs_panel_median": 0.18,
              "fixed_effect_suspect": true,
              "rationale": "below_panel_median_within_country_std"
            },
            ...
          ]
        },
        ...
      }
    }
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

DEFAULT_TOP_K = 10
DEFAULT_PERCENTILE_THRESHOLD = 0.50  # below median = suspect
EXPECTED_BIAS_COLUMN_OFFSET = 1  # TreeSHAP appends +1 column for bias


def compute_treeshap_attribution(booster: Any, X: np.ndarray) -> np.ndarray:
    """Compute SHAP values for a LightGBM booster on input X.

    Wraps `booster.predict(X, pred_contrib=True)`. Returns array of
    shape (n_samples, n_features) — the bias column is stripped.

    Raises
    ------
    ValueError
        If the returned shape does not match (n_samples, n_features+1).
    """
    raw = booster.predict(X, pred_contrib=True)
    raw = np.asarray(raw, dtype=float)

    n_samples, n_cols = raw.shape
    expected_n_features = booster.num_feature()

    if n_cols != expected_n_features + EXPECTED_BIAS_COLUMN_OFFSET:
        msg = (
            f"unexpected pred_contrib shape: got {raw.shape}, expected "
            f"({n_samples}, {expected_n_features + EXPECTED_BIAS_COLUMN_OFFSET})"
        )
        raise ValueError(msg)

    # Strip bias column (last col).
    return raw[:, :-1]


def aggregate_to_global_importance(
    shap_values: np.ndarray,
    feature_names: list[str],
) -> dict[str, float]:
    """Mean |SHAP| per feature across samples → dict {feature: importance}."""
    if shap_values.shape[1] != len(feature_names):
        msg = (
            f"shap shape mismatch: shap has {shap_values.shape[1]} cols, "
            f"feature_names has {len(feature_names)}"
        )
        raise ValueError(msg)

    mean_abs = np.mean(np.abs(shap_values), axis=0)
    return {name: float(value) for name, value in zip(feature_names, mean_abs)}


def top_k_features(importance: dict[str, float], k: int = DEFAULT_TOP_K) -> list[dict[str, Any]]:
    """Sort by importance descending, return top K as ordered list of dicts.

    Each dict has keys: rank, indicator_id, mean_abs_shap.
    Ties are broken by alphabetical indicator_id order (stable, deterministic).
    """
    if k < 1:
        msg = f"k must be >= 1, got {k}"
        raise ValueError(msg)

    # Sort: primary descending importance, secondary ascending name (tie-breaker).
    items = sorted(importance.items(), key=lambda kv: (-kv[1], kv[0]))
    top = items[:k]
    return [
        {"rank": i + 1, "indicator_id": name, "mean_abs_shap": value}
        for i, (name, value) in enumerate(top)
    ]


def compute_indicator_variance(
    panel_long: pd.DataFrame,
    *,
    window_start: int,
    window_end: int,
) -> dict[str, float]:
    """Per-indicator panel-median of within-country temporal std.

    Approach:
      1. Filter panel to [window_start, window_end].
      2. For each (country, indicator), compute std of values across years.
      3. For each indicator, take the median std across countries.

    This isolates within-country temporal variation; an indicator with
    low values here is a country fixed-effect proxy (changes little over
    time within any country).

    Parameters
    ----------
    panel_long : pd.DataFrame
        Long-format panel with columns {country, year, indicator_id, value}.
    window_start, window_end : int
        Inclusive window for std computation.

    Returns
    -------
    dict[indicator_id, median_within_country_std]
        Indicators with no testable country (constant or single-obs in
        every country in the window) get NaN.
    """
    required = {"country", "year", "indicator_id", "value"}
    missing = required - set(panel_long.columns)
    if missing:
        msg = f"panel_long missing columns: {missing}"
        raise ValueError(msg)

    sub = panel_long[
        (panel_long["year"] >= window_start) & (panel_long["year"] <= window_end)
    ]
    if sub.empty:
        return {}

    # Per-(indicator, country) std.
    grouped = sub.groupby(["indicator_id", "country"])["value"].std(ddof=1)
    # Per-indicator median across countries (ignore NaN std for single-obs countries).
    per_indicator = grouped.groupby(level="indicator_id").median()
    return {idx: (float(v) if pd.notna(v) else float("nan")) for idx, v in per_indicator.items()}


def annotate_top_k_with_variance(
    top_k_list: list[dict[str, Any]],
    variance_map: dict[str, float],
    panel_median: float,
    *,
    threshold_factor: float = 1.0,
) -> list[dict[str, Any]]:
    """Add `within_country_std_median`, `variance_ratio`,
    `fixed_effect_suspect`, `rationale` to each top-K record.

    `fixed_effect_suspect` fires when the indicator's median within-
    country std is below `threshold_factor * panel_median` (default
    factor 1.0 = literal panel median per Tariq's spec).

    Indicators with NaN variance (e.g., engineered features not in the
    raw panel) are flagged with `rationale = "variance_unavailable"`
    and `fixed_effect_suspect = None`.
    """
    out = []
    for rec in top_k_list:
        ind_id = rec["indicator_id"]
        std_value = variance_map.get(ind_id, float("nan"))
        if pd.isna(std_value) or pd.isna(panel_median) or panel_median == 0.0:
            suspect = None
            ratio = None
            rationale = "variance_unavailable"
        else:
            ratio = float(std_value / panel_median)
            below_threshold = std_value < threshold_factor * panel_median
            suspect = bool(below_threshold)
            rationale = (
                "below_panel_median_within_country_std"
                if below_threshold
                else "above_panel_median_within_country_std"
            )

        annotated = {**rec}
        annotated["within_country_std_median"] = (
            None if pd.isna(std_value) else float(std_value)
        )
        annotated["variance_ratio_vs_panel_median"] = ratio
        annotated["fixed_effect_suspect"] = suspect
        annotated["rationale"] = rationale
        out.append(annotated)
    return out


def panel_median_variance(variance_map: dict[str, float]) -> float:
    """Median of indicator-level within-country std values, ignoring NaNs."""
    valid = [v for v in variance_map.values() if not pd.isna(v)]
    if not valid:
        return float("nan")
    return float(np.median(valid))


def compute_feature_variance_from_wide(
    wide_panel: pd.DataFrame,
    feature_columns: list[str],
    *,
    window_start: int,
    window_end: int,
) -> dict[str, float]:
    """Per-feature panel-median of within-country temporal std, on a
    wide-format engineered feature panel.

    Mirrors `compute_indicator_variance` but consumes the trainer's
    output shape: one row per (country, year), one column per
    engineered feature. This is the right reference space for SHAP
    fingerprint annotation because the model SEES these columns
    (raw indicators after first-differencing have different IDs and
    different variance distributions than their pre-engineered form).

    Parameters
    ----------
    wide_panel : pd.DataFrame
        Must have `country`, `year` columns plus one column per feature
        listed in `feature_columns`.
    feature_columns : list[str]
        Feature columns to compute variance for.
    window_start, window_end : int
        Inclusive window.

    Returns
    -------
    dict[feature_name, median_within_country_std]
    """
    required = {"country", "year"}.union(feature_columns)
    missing = required - set(wide_panel.columns)
    if missing:
        msg = f"wide_panel missing columns: {sorted(missing)}"
        raise ValueError(msg)

    sub = wide_panel[
        (wide_panel["year"] >= window_start) & (wide_panel["year"] <= window_end)
    ]
    if sub.empty:
        return {feat: float("nan") for feat in feature_columns}

    out: dict[str, float] = {}
    # Per-country std per feature → median across countries.
    grouped = sub.groupby("country")[feature_columns].std(ddof=1)
    medians = grouped.median(skipna=True)
    for feat in feature_columns:
        v = medians.get(feat, float("nan"))
        out[feat] = float(v) if pd.notna(v) else float("nan")
    return out
