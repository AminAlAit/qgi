"""Structural-break audit on per-(country, indicator) time series.

Implements Component 7 of `docs/specs/internal/ops/ml-track/07-validation-framework.md`
per Ji-Hoon + Kwame mini-consult guidance (2026-05-04):

- Method: OLS-CUSUM on residuals of `value ~ year` (linear trend).
  Zivot-Andrews dropped: unit-root null is wrong for trend-stationary series
  (V-Dem scores, GDP per capita) and fails on n=8.
- No binarization at single alpha — emit raw p-values + test stats.
  Two descriptive flags: `soft_flag_p_lt_010` (Ji-Hoon) and
  `high_conf_break_p_lt_001` (Kwame). Neither is a gate.
- Skip n < `min_n_observations` (default 6); warn when n < `low_power_threshold`
  (default 15) per Ji-Hoon's reliability floor for CUSUM.
- Diagnostic-only — Stage 2 falsification rules (F1/F2/F3) do NOT consume
  this output. Stage 2 walk consumes it for per-recipe cell handling.

Pre-registration: the JSON is committed to qgi-data BEFORE any Stage 2 walk;
commit timestamp is the pre-registration timestamp per Kwame's rigor note.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Avoid eager statsmodels import to keep test collection fast.
# The OLS + CUSUM are imported inside `cusum_test`.

DEFAULT_MIN_N_OBSERVATIONS = 6
DEFAULT_LOW_POWER_THRESHOLD = 15
NARROW_WINDOW = (2014, 2021)
EXTENDED_WINDOW_END = 2021


def cusum_test(
    values: np.ndarray | list,
    *,
    min_n_observations: int = DEFAULT_MIN_N_OBSERVATIONS,
    low_power_threshold: int = DEFAULT_LOW_POWER_THRESHOLD,
) -> dict[str, Any]:
    """Run OLS-CUSUM on a single time series.

    Regress values on an integer time index (linear trend + intercept), then
    apply `breaks_cusumolsresid` from statsmodels.

    Parameters
    ----------
    values : array-like
        Numeric values, ordered by time. NaN entries are dropped before
        the test.
    min_n_observations : int
        Minimum number of non-NaN observations required to run the test.
        Below this, return a skip record.
    low_power_threshold : int
        Below this, set `low_power_warning=True`. CUSUM has weak power
        below ~15 observations.

    Returns
    -------
    dict with keys:
        n_observations : int
        test_used : str | None  (None if skipped)
        test_statistic_sup_b : float | None
        p_value : float | None
        soft_flag_p_lt_010 : bool | None
        high_conf_break_p_lt_001 : bool | None
        low_power_warning : bool | None
        skip_reason : str | None
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    n = int(arr.size)

    skip_record: dict[str, object] = {
        "n_observations": n,
        "test_used": None,
        "test_statistic_sup_b": None,
        "p_value": None,
        "soft_flag_p_lt_010": None,
        "high_conf_break_p_lt_001": None,
        "low_power_warning": None,
        "skip_reason": None,
    }

    if n < min_n_observations:
        skip_record["skip_reason"] = f"insufficient_observations_n_{n}_below_{min_n_observations}"
        return skip_record

    # Constant series → no break, no variance — flag as skip rather than
    # let statsmodels divide by zero or return NaN.
    if np.allclose(arr, arr[0]):
        skip_record["skip_reason"] = "constant_series"
        return skip_record

    # Late import: keep test collection cheap.
    import statsmodels.api as sm  # noqa: PLC0415
    from statsmodels.stats.diagnostic import breaks_cusumolsresid  # noqa: PLC0415

    time_index = np.arange(n)
    X = sm.add_constant(time_index, has_constant="add")

    try:
        ols_result = sm.OLS(arr, X).fit()
    except (np.linalg.LinAlgError, ValueError) as exc:
        skip_record["skip_reason"] = f"ols_failure:{exc.__class__.__name__}"
        return skip_record

    try:
        sup_b, p_value, _crit = breaks_cusumolsresid(ols_result.resid, ddof=2)
    except Exception as exc:  # noqa: BLE001 — statsmodels raises mixed types
        skip_record["skip_reason"] = f"cusum_failure:{exc.__class__.__name__}"
        return skip_record

    p_value_float = float(p_value)
    return {
        "n_observations": n,
        "test_used": "cusum_olsresid_linear_trend",
        "test_statistic_sup_b": float(sup_b),
        "p_value": p_value_float,
        "soft_flag_p_lt_010": p_value_float < 0.10,
        "high_conf_break_p_lt_001": p_value_float < 0.01,
        "low_power_warning": n < low_power_threshold,
        "skip_reason": None,
    }


def audit_pair(
    years: np.ndarray | list,
    values: np.ndarray | list,
    *,
    window_start: int | None,
    window_end: int,
    min_n_observations: int = DEFAULT_MIN_N_OBSERVATIONS,
    low_power_threshold: int = DEFAULT_LOW_POWER_THRESHOLD,
) -> dict[str, Any]:
    """Slice (years, values) to [window_start, window_end] and run CUSUM.

    `window_start=None` means open-ended (use earliest available year up
    to `window_end`).
    """
    years_arr = np.asarray(years, dtype=int)
    values_arr = np.asarray(values, dtype=float)

    if years_arr.size != values_arr.size:
        msg = f"years and values length mismatch: {years_arr.size} vs {values_arr.size}"
        raise ValueError(msg)

    # Sort by year (defensive — caller might pass unsorted).
    order = np.argsort(years_arr)
    years_arr = years_arr[order]
    values_arr = values_arr[order]

    # Apply window filter.
    if window_start is not None:
        mask = (years_arr >= window_start) & (years_arr <= window_end)
    else:
        mask = years_arr <= window_end
    years_in = years_arr[mask]
    values_in = values_arr[mask]

    record = cusum_test(
        values_in,
        min_n_observations=min_n_observations,
        low_power_threshold=low_power_threshold,
    )

    if years_in.size > 0:
        record["window_start_actual"] = int(years_in.min())
        record["window_end_actual"] = int(years_in.max())
    else:
        record["window_start_actual"] = None
        record["window_end_actual"] = None
    return record


def compute_panel_snapshot_id(panel_path: Path | str) -> str:
    """SHA-256 of the parquet file content. Used as `panel_snapshot_id`
    in the audit JSON header so future re-runs can diff against it.
    """
    path = Path(panel_path)
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
