"""Stage 3 Component 5 — Stratified calibration by data-coverage cohort.

Per docs/specs/internal/ops/ml-track/07-validation-framework.md Component 5
+ stage-3-validation-audit.md deliverable 1 / 3.

Nasrin's binding requirement (post-PoC trio convening 2026-05-03):
*"a model that is well-calibrated only on data-rich countries is
commercially useless for political risk insurance, where the actual
coverage targets are fragile states."*

This module produces:
- Per-country data-coverage cohort assignment (high / mid / low)
- Per-(recipe, cohort) ECE + reliability diagram
- Per-(recipe, cohort) calibration table (decile-based)

Buyer-facing actuaries read calibration tables, not AUC charts.

## Cohort definition

Coverage = fraction of (country, year) cells with non-null indicator
values across the engineered feature panel in the training window
2014-2021.

- HIGH (top 33%): OECD-type rich-data countries
- MID (middle 33%): general
- LOW (bottom 33%): fragile/data-sparse states

This is a SIMPLE proxy. The pre-reg amendment may refine this with
sector-weighted coverage or other metrics; for PoC, missingness
fraction is sufficient.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_N_BINS = 10
DEFAULT_HIGH_PCTILE = 67  # top 33%
DEFAULT_LOW_PCTILE = 33   # bottom 33%


@dataclass
class CalibrationTableRow:
    """One decile bucket in a calibration table."""

    bin_low: float
    bin_high: float
    n_observations: int
    mean_predicted_prob: float
    observed_event_rate: float
    observed_rate_ci_lower: float
    observed_rate_ci_upper: float


@dataclass
class CohortCalibrationReport:
    """Per-(recipe, cohort) calibration report."""

    recipe_id: str
    cohort: str  # "high" | "mid" | "low"
    n_countries: int
    n_observations: int
    n_positives: int
    ece: float
    table: list[CalibrationTableRow] = field(default_factory=list)
    skip_reason: str | None = None


def assign_coverage_cohorts(
    panel: pd.DataFrame,
    *,
    feature_columns: list[str] | None = None,
    high_pctile: float = DEFAULT_HIGH_PCTILE,
    low_pctile: float = DEFAULT_LOW_PCTILE,
) -> pd.DataFrame:
    """Compute per-country data-coverage cohort assignment.

    Coverage = fraction of non-null values across `feature_columns`
    summed over country's rows in `panel`. Higher = more data.

    Returns
    -------
    DataFrame with columns: country, coverage_score, cohort
        cohort in {"high", "mid", "low"}.
    """
    if "country" not in panel.columns:
        msg = "panel missing 'country' column"
        raise ValueError(msg)
    if feature_columns is None:
        feature_columns = [c for c in panel.columns if c not in ("country", "year")]
    if not feature_columns:
        msg = "no feature columns available for coverage computation"
        raise ValueError(msg)
    if not 0 < low_pctile < high_pctile < 100:
        msg = f"percentiles must satisfy 0 < low < high < 100, got {low_pctile}, {high_pctile}"
        raise ValueError(msg)

    # Per-country non-null fraction
    sub = panel[["country"] + feature_columns]
    coverage_per_row = sub[feature_columns].notna().mean(axis=1)
    coverage_df = pd.DataFrame({"country": sub["country"], "coverage_per_row": coverage_per_row})
    coverage_score = coverage_df.groupby("country")["coverage_per_row"].mean().reset_index()
    coverage_score.columns = ["country", "coverage_score"]

    # Tertile-style cohort assignment
    high_thr = float(np.percentile(coverage_score["coverage_score"], high_pctile))
    low_thr = float(np.percentile(coverage_score["coverage_score"], low_pctile))

    def _label(score: float) -> str:
        if score >= high_thr:
            return "high"
        if score < low_thr:
            return "low"
        return "mid"

    coverage_score["cohort"] = coverage_score["coverage_score"].map(_label)
    return coverage_score


def compute_ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = DEFAULT_N_BINS) -> float:
    """ECE: sum_b (n_b/N) * |observed_b - predicted_b|."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if probs.size == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    n = probs.size
    ece = 0.0
    for k in range(n_bins):
        lo, hi = edges[k], edges[k + 1]
        if k == n_bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        n_b = int(mask.sum())
        if n_b == 0:
            continue
        avg_p = float(probs[mask].mean())
        obs_r = float(labels[mask].mean())
        ece += (n_b / n) * abs(obs_r - avg_p)
    return float(ece)


def calibration_table(
    probs: np.ndarray,
    labels: np.ndarray,
    *,
    n_bins: int = DEFAULT_N_BINS,
    seed: int = 0,
    n_bootstrap: int = 200,
) -> list[CalibrationTableRow]:
    """Decile-based calibration table with bootstrap 95% CI on observed
    rate per bucket. Used for buyer-facing actuarial review."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    if probs.size == 0:
        return []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rng = np.random.default_rng(seed)
    rows: list[CalibrationTableRow] = []
    for k in range(n_bins):
        lo, hi = edges[k], edges[k + 1]
        if k == n_bins - 1:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)
        n_b = int(mask.sum())
        if n_b == 0:
            rows.append(CalibrationTableRow(
                bin_low=float(lo), bin_high=float(hi), n_observations=0,
                mean_predicted_prob=float("nan"), observed_event_rate=float("nan"),
                observed_rate_ci_lower=float("nan"), observed_rate_ci_upper=float("nan"),
            ))
            continue
        avg_p = float(probs[mask].mean())
        obs_r = float(labels[mask].mean())
        # Bootstrap CI on observed rate
        bin_labels = labels[mask]
        boots = []
        for _ in range(n_bootstrap):
            idx = rng.integers(0, n_b, size=n_b)
            boots.append(float(bin_labels[idx].mean()))
        ci_lo = float(np.percentile(boots, 2.5))
        ci_hi = float(np.percentile(boots, 97.5))
        rows.append(CalibrationTableRow(
            bin_low=float(lo), bin_high=float(hi), n_observations=n_b,
            mean_predicted_prob=avg_p, observed_event_rate=obs_r,
            observed_rate_ci_lower=ci_lo, observed_rate_ci_upper=ci_hi,
        ))
    return rows


def stratified_calibration_per_recipe(
    predictions: list[dict[str, Any]],
    cohort_map: dict[str, str],
    *,
    n_bins: int = DEFAULT_N_BINS,
    n_bootstrap: int = 200,
    seed: int = 0,
) -> dict[str, dict[str, CohortCalibrationReport]]:
    """Compute per-(recipe, cohort) calibration reports.

    Parameters
    ----------
    predictions : list of {country, year, recipe_id, predicted_probability, label}
    cohort_map : dict country_slug -> cohort_label

    Returns
    -------
    dict[recipe_id][cohort] -> CohortCalibrationReport
    """
    df = pd.DataFrame(predictions)
    if df.empty:
        return {}
    df["cohort"] = df["country"].map(cohort_map).fillna("unknown")
    out: dict[str, dict[str, CohortCalibrationReport]] = {}
    for rid, recipe_group in df.groupby("recipe_id"):
        out[rid] = {}
        for cohort, cohort_group in recipe_group.groupby("cohort"):
            probs = cohort_group["predicted_probability"].to_numpy(dtype=float)
            labels = cohort_group["label"].to_numpy(dtype=int)
            n_pos = int((labels == 1).sum())
            n_obs = int(probs.size)
            n_countries = int(cohort_group["country"].nunique())
            ece = compute_ece(probs, labels, n_bins=n_bins)
            table = calibration_table(probs, labels, n_bins=n_bins,
                                      n_bootstrap=n_bootstrap, seed=seed)
            out[rid][cohort] = CohortCalibrationReport(
                recipe_id=rid, cohort=cohort,
                n_countries=n_countries, n_observations=n_obs,
                n_positives=n_pos, ece=ece, table=table,
                skip_reason=None if n_obs > 0 else "empty_cohort",
            )
    return out
