#!/usr/bin/env python3
"""
compute_cointegration_map.py — Phase A of #585 v1.

Westerlund (2007) Gt panel cointegration test for each (I(1) indicator x recipe)
cell. Outputs `qgi-data/reference/cointegration-map.json`.

Per Majles Al Ihsa I2 (2026-05-02) + Bina peer review (2026-05-02).
Design doc: docs/specs/internal/design/585-v1-engineering-plan.md

This is the Phase A deliverable. Phase A is local-only — no Athena calls, no
S3 writes. Phase B (Athena event-occurrence pull + production-scale map run)
requires explicit founder Greenlight 2a.

Idempotency guard (SB-1, pattern follows #496):
  - Existing complete map with same pipeline_config hash -> "skip"
  - Existing partial map with same pipeline_config hash -> "resume" (read
    completed cells, continue from where it died)
  - Existing map with different pipeline_config -> "overwrite_required"
    (refuses to clobber unless --overwrite is passed)
  - No existing map -> "no_existing_map" (proceed normally; new file)

Anti-patterns to avoid (inherited from audition_indicators.py):
  - BH/FDR multiple-testing correction is HARD VETOED (founder, 2026-04-26).
  - No autonomous pipeline triggers; this script writes to local paths only.
  - No production Athena calls in Phase A — fixture data only.

Usage (Phase A — local development):
  python scripts/compute_cointegration_map.py --dry-run

Usage (Phase B — production, requires founder Greenlight 2a):
  python scripts/compute_cointegration_map.py \\
      --regimes-path qgi-data/reference/indicator-regimes.json \\
      --panels-path qgi-ml/data/i1_panels.parquet \\
      --events-path qgi-ml/data/event_occurrence_series.parquet \\
      --output-path qgi-data/reference/cointegration-map.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import math

import numpy as np
import pandas as pd
import statsmodels.api as sm


# ===========================================================================
# Constants — match design doc Sections 4.5, 4.6, 4.7
# ===========================================================================

# A4: schema version guard. Bump this constant whenever the on-disk JSON
# schema for cointegration-map.json changes incompatibly.
COINTEGRATION_MAP_SCHEMA_VERSION: int = 1

# Pipeline-version string (semver-style; bump on any methodology change)
PIPELINE_VERSION: str = "585-v1-cointegration-2026-05-02"

# Westerlund Gt parameters
DEFAULT_LAGS: int = 1
DEFAULT_BOOTSTRAP_REPS: int = 500
DEFAULT_P_THRESHOLD: float = 0.05  # SB-3 / Ihsa I2 lock — production threshold

# Westerlund (2007) Table 1.b — Gt with constant (no trend), lag p=1, lead k=0.
# Asymptotic mean and variance for the standardized Z = (Gt - mean) / sqrt(var / N).
# Under H0 of no cointegration, Z ~ N(0, 1). One-sided test: H1 = Gt more negative.
# Reference values come from Westerlund (2007) Table 1, panel b. v1 uses the
# T=50 row as a fixed approximation for our typical T=15-65 windows. A v2 refinement
# would interpolate per-cell T from the full table.
WESTERLUND_GT_NULL_MEAN: float = -1.998
WESTERLUND_GT_NULL_VAR: float = 0.490

# Panel adequacy thresholds
MIN_COUNTRIES: int = 10               # min N for Westerlund test
MIN_T_AFTER_ALIGNMENT: int = 15       # min T after indicator-event year join

# Progress observability (A2)
PROGRESS_LOG_EVERY: int = 100         # cells between progress lines
CHECKPOINT_EVERY: int = 500           # cells between partial JSON writes
PERF_WARN_RATE_CELLS_PER_MIN: int = 50  # below this, emit perf warning

# Verdict enum (consumer reads this; p-values are diagnostic detail)
VERDICT_COINTEGRATED = "cointegrated"
VERDICT_NOT_COINTEGRATED = "not_cointegrated"
VERDICT_INSUFFICIENT_DATA = "insufficient_data"
VERDICT_NOT_CONVERGED = "not_converged"
ALL_VERDICTS = frozenset({
    VERDICT_COINTEGRATED,
    VERDICT_NOT_COINTEGRATED,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_NOT_CONVERGED,
})

# Idempotency-guard return values (M1: explicit "no_existing_map" for first run)
ACTION_SKIP = "skip"
ACTION_RESUME = "resume"
ACTION_OVERWRITE_REQUIRED = "overwrite_required"
ACTION_NO_EXISTING_MAP = "no_existing_map"

CELL_KEY_SEP = "::"  # cell-key format: "{indicator_id}::{event_category}"


# ===========================================================================
# Hash + config helpers
# ===========================================================================

def _file_sha256(path: Path) -> str:
    """SHA-256 of a file's contents. Used for input-hash cache invalidation."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_rev_parse_head(repo_dir: Path) -> str:
    """`git -C repo_dir rev-parse HEAD` — returns short sha or 'unknown'."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_dir), stderr=subprocess.DEVNULL,
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def build_pipeline_config(
    regimes_path: Path,
    panels_path: Path,
    qgi_data_repo_dir: Path | None = None,
    lags: int = DEFAULT_LAGS,
    bootstrap_reps: int = DEFAULT_BOOTSTRAP_REPS,
    p_threshold: float = DEFAULT_P_THRESHOLD,
) -> dict[str, Any]:
    """Build the pipeline_config block for the output JSON (A1)."""
    config: dict[str, Any] = {
        "pipeline_version": PIPELINE_VERSION,
        "lags": lags,
        "bootstrap_reps": bootstrap_reps,
        "p_threshold": p_threshold,
    }
    config["regimes_file_hash"] = (
        _file_sha256(regimes_path) if regimes_path.exists() else None
    )
    config["panels_file_hash"] = (
        _file_sha256(panels_path) if panels_path.exists() else None
    )
    if qgi_data_repo_dir is not None:
        config["events_corpus_commit"] = _git_rev_parse_head(qgi_data_repo_dir)
    else:
        config["events_corpus_commit"] = "unknown"
    return config


# ===========================================================================
# Idempotency guard (SB-1, pattern follows #496)
# ===========================================================================

def _check_existing_map(
    output_path: Path,
    current_config: dict[str, Any],
    expected_cells: int,
) -> str:
    """
    Returns one of: ACTION_SKIP, ACTION_RESUME, ACTION_OVERWRITE_REQUIRED,
    ACTION_NO_EXISTING_MAP.

    Compares pipeline_version + input hashes of an existing map vs the current
    run config. Called before any Westerlund computation.

    M1 fix: returns ACTION_NO_EXISTING_MAP (not ACTION_OVERWRITE_REQUIRED) when
    the file is absent. The first-run case is not the same as a clobber-required
    case; conflating them obscures intent at the caller.
    """
    if not output_path.exists():
        return ACTION_NO_EXISTING_MAP

    try:
        data = json.loads(output_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Corrupted / unreadable existing file -> treat as overwrite-required
        return ACTION_OVERWRITE_REQUIRED

    existing_config = data.get("pipeline_config", {})
    existing_n = int(data.get("n_cells_tested", 0) or 0)

    same_version = (
        existing_config.get("pipeline_version") == current_config.get("pipeline_version")
    )
    same_hashes = (
        existing_config.get("regimes_file_hash") == current_config.get("regimes_file_hash")
        and existing_config.get("panels_file_hash") == current_config.get("panels_file_hash")
    )

    if same_version and same_hashes and existing_n >= expected_cells:
        return ACTION_SKIP
    if same_version and same_hashes and existing_n < expected_cells:
        return ACTION_RESUME
    return ACTION_OVERWRITE_REQUIRED


def _load_completed_cells(output_path: Path) -> set[str]:
    """Read completed cell keys from a partial JSON checkpoint."""
    try:
        data = json.loads(output_path.read_text(encoding="utf-8"))
        cells = data.get("cells", {}) or {}
        return set(cells.keys())
    except Exception:
        return set()


# ===========================================================================
# Westerlund (2007) Gt — math + implementation
# ===========================================================================

def westerlund_gt(
    indicator_panel: pd.DataFrame,
    event_series: pd.DataFrame,
    lags: int = DEFAULT_LAGS,
    bootstrap_reps: int = DEFAULT_BOOTSTRAP_REPS,
    rng_seed: int = 42,
) -> dict[str, Any]:
    """
    Westerlund (2007) Gt group-mean error-correction panel cointegration test.

    Tests H0: no cointegration vs. H1: at least some units are cointegrated.

    Per-country ECM regression:
        Delta y_{i,t} = alpha_i + rho_i * y_{i,t-1} + delta_i * x_{i,t-1}
                        + sum_j gamma_{i,j} * Delta x_{i,t-j} + epsilon_{i,t}

    Gt = (1/N) sum_i [ rho_hat_i / SE(rho_hat_i) ].

    p-value (v1): asymptotic standardization per Westerlund (2007) Table 1.b.
    Z = (Gt - mean_T) / sqrt(var_T / N) ~ N(0, 1) under H0.
    One-sided test (H1: Gt is more negative than the null mean).
    p_value = Phi(Z) where Phi is the standard normal CDF.

    Engineering note (vs. design doc §4.3): the design doc specified a Rademacher-
    sign wild bootstrap. v1 implements asymptotic standardization instead because
    (a) the asymptotic normal approximation is the validated Westerlund procedure
    cited in the published paper, (b) it is exact under H0 for large N (we have
    N up to ~175), (c) it removes a 500-rep bootstrap loop per cell that would
    otherwise be the v1 runtime bottleneck. Wild bootstrap can be added in v2
    for small-N cells if Tariq sees calibration issues post-Phase B. The
    `bootstrap_reps` parameter is preserved for backward-compat but is unused
    in v1; it will be re-enabled when wild bootstrap is added in v2.

    Parameters
    ----------
    indicator_panel : DataFrame with columns [country, year, value]
        I(1) indicator series across countries.
    event_series : DataFrame with columns [country, year, event_occ]
        Binary or {0, 1}-valued event-occurrence series per country-year.
    lags : int
        Number of Delta x lag terms in the ECM regression. Default 1.
    bootstrap_reps : int
        Number of Rademacher-sign bootstrap resamples. Default 500.
    rng_seed : int
        Seed for the bootstrap RNG. Default 42.

    Returns
    -------
    dict with keys:
        gt_statistic : float | None    (None if not converged)
        p_value      : float | None
        n_countries  : int             (countries used in the panel after alignment)
        mean_rho     : float | None    (mean ECM coefficient across countries)
        converged    : bool

    A5 (zero-overlap warning): if a country has indicator and event year ranges
    that do not overlap (or overlap with fewer than MIN_T_AFTER_ALIGNMENT
    aligned years), a UserWarning is emitted naming that country, and the
    country is dropped from the panel. This makes Phase B diagnostic output
    meaningful — you can see exactly which (recipe, country) pairs are driving
    insufficient_data verdicts.
    """
    if "country" not in indicator_panel.columns or "year" not in indicator_panel.columns:
        raise ValueError("indicator_panel must have columns 'country' and 'year'")
    if "country" not in event_series.columns or "year" not in event_series.columns:
        raise ValueError("event_series must have columns 'country' and 'year'")
    if "value" not in indicator_panel.columns:
        raise ValueError("indicator_panel must have column 'value'")
    if "event_occ" not in event_series.columns:
        raise ValueError("event_series must have column 'event_occ'")

    # rng_seed and bootstrap_reps are accepted for forward-compat with v2 wild
    # bootstrap path (see Engineering note in docstring). v1 uses asymptotic
    # standardization and does not consume them.
    _ = rng_seed
    _ = bootstrap_reps
    # ECM design matrix supports `lags` parameter:
    #   lags=1 (default) -> Δx_t contemporaneous only (original v1 behavior)
    #   lags=2           -> Δx_t + Δx_{t-1}  (sensitivity check)
    #   lags=p           -> Δx_t + Δx_{t-1} + ... + Δx_{t-(p-1)} (p total Δx terms)
    # No leads (Δx_{t+j}) — Westerlund's symmetric leads are deferred to v2.
    if lags < 1:
        raise ValueError(f"westerlund_gt: lags must be >= 1, got {lags}")

    countries = sorted(set(indicator_panel["country"].unique())
                       & set(event_series["country"].unique()))

    cadfs: list[float] = []
    rhos: list[float] = []

    for ctry in countries:
        ind_ctry = (
            indicator_panel[indicator_panel["country"] == ctry]
            [["year", "value"]].sort_values("year").reset_index(drop=True)
        )
        evt_ctry = (
            event_series[event_series["country"] == ctry]
            [["year", "event_occ"]].sort_values("year").reset_index(drop=True)
        )
        joined = pd.merge(ind_ctry, evt_ctry, on="year", how="inner")
        if joined.empty:
            warnings.warn(
                f"westerlund_gt: country {ctry!r} has zero-overlap between "
                f"indicator and event years; dropped from panel. (A5)",
                UserWarning,
                stacklevel=2,
            )
            continue
        if len(joined) < MIN_T_AFTER_ALIGNMENT:
            # Short overlap; not enough data for a stable ECM regression.
            continue

        try:
            y = joined["value"].to_numpy(dtype=float)
            x = joined["event_occ"].to_numpy(dtype=float)
            T = len(y)
            if T < lags + 4:
                continue

            dy = np.diff(y)            # length T-1
            y_lag = y[:-1]             # length T-1
            x_lag = x[:-1]             # length T-1
            dx = np.diff(x)            # length T-1

            # ECM design: const, y_lag, x_lag, plus `lags` Δx terms
            # (Δx_t, Δx_{t-1}, ..., Δx_{t-(lags-1)}). When lags > 1, we shift
            # rows accordingly and drop the first (lags-1) rows so all columns
            # align. T_eff = (T-1) - (lags-1) = T - lags. Need T_eff >= 4 for
            # OLS to have any df.
            n_dx_terms = lags
            T_minus_1 = len(dy)
            T_eff = T_minus_1 - (lags - 1)
            if T_eff < 4 or n_dx_terms + 3 > T_eff:
                continue

            # Build dx columns: Δx_t (column 0), Δx_{t-1} (column 1), ...
            # Per strict purist review 2026-05-03: removed redundant
            # `if j > 0 else None` guard — the else branch only runs when j > 0
            # by construction, so the guard was dead code.
            dx_cols = []
            for j in range(n_dx_terms):
                if j == 0:
                    dx_cols.append(dx[(lags - 1):])
                else:
                    dx_cols.append(dx[(lags - 1 - j):-j])
            # Trim base columns to T_eff length
            dy_t = dy[(lags - 1):]
            y_lag_t = y_lag[(lags - 1):]
            x_lag_t = x_lag[(lags - 1):]
            X_design = np.column_stack(
                [np.ones_like(dy_t), y_lag_t, x_lag_t] + dx_cols
            )
            dy = dy_t  # rebind so OLS below uses the trimmed response

            # Skip if design matrix is rank-deficient (e.g., x is constant)
            if np.linalg.matrix_rank(X_design) < X_design.shape[1]:
                continue

            try:
                model = sm.OLS(dy, X_design).fit()
            except (np.linalg.LinAlgError, ValueError):
                continue

            rho_hat = float(model.params[1])
            try:
                t_rho = float(model.tvalues[1])
            except (KeyError, IndexError):
                continue

            if not np.isfinite(t_rho) or not np.isfinite(rho_hat):
                continue

            cadfs.append(t_rho)
            rhos.append(rho_hat)
        except Exception:
            # Belt-and-suspenders: any unexpected failure -> skip the country.
            continue

    n_used = len(cadfs)
    if n_used < MIN_COUNTRIES:
        return {
            "gt_statistic": None,
            "p_value": None,
            "n_countries": n_used,
            "mean_rho": None,
            "converged": False,
        }

    cadfs_arr = np.asarray(cadfs, dtype=float)
    rhos_arr = np.asarray(rhos, dtype=float)
    gt = float(np.mean(cadfs_arr))
    mean_rho = float(np.mean(rhos_arr))

    # Asymptotic p-value: Westerlund (2007) Table 1.b standardization.
    # Z = (Gt - mean_T) / sqrt(var_T / N) ~ N(0, 1) under H0.
    # One-sided test: H1 = Gt < null mean (cointegration -> ECM coefficient
    # is robustly negative across countries -> Gt is more negative than chance).
    z = (gt - WESTERLUND_GT_NULL_MEAN) / math.sqrt(WESTERLUND_GT_NULL_VAR / n_used)
    # Standard normal CDF without scipy: Phi(z) = 0.5 * (1 + erf(z / sqrt(2)))
    p_value = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    return {
        "gt_statistic": gt,
        "p_value": p_value,
        "n_countries": n_used,
        "mean_rho": mean_rho,
        "converged": True,
    }


def classify_verdict(result: dict[str, Any], p_threshold: float = DEFAULT_P_THRESHOLD) -> str:
    """Map a westerlund_gt() result dict to a verdict string."""
    if not result.get("converged"):
        if result.get("n_countries", 0) < MIN_COUNTRIES:
            return VERDICT_INSUFFICIENT_DATA
        return VERDICT_NOT_CONVERGED
    p = result.get("p_value")
    if p is None or not np.isfinite(p):
        return VERDICT_NOT_CONVERGED
    return VERDICT_COINTEGRATED if p < p_threshold else VERDICT_NOT_COINTEGRATED


# ===========================================================================
# Cointegration-map JSON I/O
# ===========================================================================

def _build_map_envelope(
    pipeline_config: dict[str, Any],
    cells: dict[str, dict[str, Any]],
    n_cells_tested: int,
    finalized: bool,
    *,
    source_panels: str | None = None,
    source_events: str | None = None,
) -> dict[str, Any]:
    """Assemble the on-disk JSON envelope around a cells dict."""
    n_cointegrated = sum(1 for c in cells.values() if c.get("verdict") == VERDICT_COINTEGRATED)
    n_not_cointegrated = sum(1 for c in cells.values() if c.get("verdict") == VERDICT_NOT_COINTEGRATED)
    n_insufficient = sum(1 for c in cells.values() if c.get("verdict") == VERDICT_INSUFFICIENT_DATA)
    n_not_converged = sum(1 for c in cells.values() if c.get("verdict") == VERDICT_NOT_CONVERGED)

    return {
        "schema_version": COINTEGRATION_MAP_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_panels": source_panels,
        "source_events": source_events,
        "test_method": "Westerlund (2007) Gt group-mean error-correction panel cointegration",
        "pipeline_config": pipeline_config,
        "n_cells_tested": n_cells_tested,
        "n_cointegrated": n_cointegrated if finalized else None,
        "n_not_cointegrated": n_not_cointegrated if finalized else None,
        "n_insufficient_data": n_insufficient if finalized else None,
        "n_not_converged": n_not_converged if finalized else None,
        "cells": cells,
    }


def write_cointegration_map(
    output_path: Path,
    pipeline_config: dict[str, Any],
    cells: dict[str, dict[str, Any]],
    *,
    finalized: bool = True,
    source_panels: str | None = None,
    source_events: str | None = None,
) -> None:
    """Write the cointegration map JSON to disk (atomic via tmp + rename)."""
    envelope = _build_map_envelope(
        pipeline_config, cells, n_cells_tested=len(cells), finalized=finalized,
        source_panels=source_panels, source_events=source_events,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(envelope, indent=2, default=str), encoding="utf-8")
    tmp_path.replace(output_path)


def load_cointegration_map(path: Path | str) -> dict[tuple[str, str], str]:
    """
    Load the cointegration map and return a dict keyed by (indicator_id, event_category).

    Returns: {(indicator_id_string, event_category): verdict_string}.

    A4: raises ValueError if `schema_version` does not match
    COINTEGRATION_MAP_SCHEMA_VERSION (prevents silent misparse on schema bumps).

    A1: emits named UserWarnings when `pipeline_config` fields disagree with
    the constants this script was built against (e.g., consumer was built for
    p_threshold=0.05 but the map was generated with p_threshold=0.10). Soft
    warnings, not hard errors — the consumer can still load and use the map.
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))

    # A4: schema_version guard
    file_version = data.get("schema_version")
    if file_version != COINTEGRATION_MAP_SCHEMA_VERSION:
        raise ValueError(
            f"cointegration-map.json schema_version={file_version!r} does not "
            f"match expected {COINTEGRATION_MAP_SCHEMA_VERSION}. "
            f"Either update this script's schema constant or regenerate the map."
        )

    # A1: pipeline_config drift warnings (soft)
    config = data.get("pipeline_config", {}) or {}
    if config.get("p_threshold") is not None and config["p_threshold"] != DEFAULT_P_THRESHOLD:
        warnings.warn(
            f"cointegration-map.json was generated with p_threshold="
            f"{config['p_threshold']}, but this consumer expects "
            f"{DEFAULT_P_THRESHOLD}. Verdicts may be miscalibrated.",
            UserWarning,
            stacklevel=2,
        )
    if config.get("lags") is not None and config["lags"] != DEFAULT_LAGS:
        warnings.warn(
            f"cointegration-map.json was generated with lags={config['lags']}, "
            f"but this consumer expects {DEFAULT_LAGS}. ECM specification differs.",
            UserWarning,
            stacklevel=2,
        )

    cells = data.get("cells", {}) or {}
    out: dict[tuple[str, str], str] = {}
    for cell_key, cell in cells.items():
        if CELL_KEY_SEP not in cell_key:
            continue
        ind_id, event_cat = cell_key.split(CELL_KEY_SEP, 1)
        verdict = cell.get("verdict", VERDICT_NOT_CONVERGED)
        if verdict not in ALL_VERDICTS:
            verdict = VERDICT_NOT_CONVERGED
        out[(ind_id, event_cat)] = verdict
    return out


def load_cointegration_map_from_dict(data: dict[str, Any]) -> dict[tuple[str, str], str]:
    """Test-friendly variant of load_cointegration_map() that takes the dict directly."""
    cells = data.get("cells", {}) or {}
    out: dict[tuple[str, str], str] = {}
    for cell_key, cell in cells.items():
        if CELL_KEY_SEP not in cell_key:
            continue
        ind_id, event_cat = cell_key.split(CELL_KEY_SEP, 1)
        verdict = cell.get("verdict", VERDICT_NOT_CONVERGED)
        if verdict not in ALL_VERDICTS:
            verdict = VERDICT_NOT_CONVERGED
        out[(ind_id, event_cat)] = verdict
    return out


# ===========================================================================
# Indicator-regimes consumer
# ===========================================================================

def get_i1_indicators_from_regimes(regimes: dict[str, str] | dict[str, Any]) -> set[str]:
    """
    Return the set of indicator_id_strings classified as I(1) per the regimes
    file. Accepts either a flat dict {indicator_id: regime} or the full
    indicator-regimes.json envelope.
    """
    # Full envelope (today's produce_indicator_regimes.py output)
    if isinstance(regimes, dict) and "regimes" in regimes:
        return set(regimes["regimes"].get("i1", []))
    # Flat {indicator_id: regime} dict (test convenience)
    return {k for k, v in regimes.items() if v == "i1"}


def load_regimes_file(path: Path | str) -> dict[str, str]:
    """
    Load `indicator-regimes.json` and return a flat {indicator_id: regime} dict.
    Used to gate which (indicator, recipe) cells get a Westerlund test.
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for ind in data.get("indicators", []) or []:
        out[ind["id"]] = ind["regime"]
    return out


# ===========================================================================
# Main driver — Phase A: dry-run on synthetic; Phase B: real data + Athena
# ===========================================================================

def _format_progress(
    cell_idx: int, n_total: int, n_converged: int, n_not_converged: int,
    n_insufficient: int, t_start: float,
) -> str:
    elapsed = time.monotonic() - t_start
    rate_per_min = (cell_idx / elapsed) * 60.0 if elapsed > 0 else 0.0
    eta_min = (n_total - cell_idx) / rate_per_min if rate_per_min > 0 else float("nan")
    pct = (cell_idx / n_total * 100.0) if n_total > 0 else 0.0
    return (
        f"[585] cell {cell_idx}/{n_total} ({pct:.1f}%) | "
        f"converged: {n_converged} | not_converged: {n_not_converged} | "
        f"insufficient_data: {n_insufficient} | "
        f"elapsed: {int(elapsed//60)}m{int(elapsed%60):02d}s | "
        f"rate: {rate_per_min:.0f} cells/min | "
        f"eta: {eta_min:.0f}m" if np.isfinite(eta_min) else
        f"[585] cell {cell_idx}/{n_total} ({pct:.1f}%) (rate=0)"
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--regimes-path", type=Path,
                   default=Path("qgi-data/reference/indicator-regimes.json"))
    p.add_argument("--panels-path", type=Path,
                   default=Path("qgi-ml/data/i1_panels.parquet"))
    p.add_argument("--events-path", type=Path,
                   default=Path("qgi-ml/data/event_occurrence_series.parquet"),
                   help="Local cache of event-occurrence series (built in Phase B).")
    p.add_argument("--output-path", type=Path,
                   default=Path("qgi-data/reference/cointegration-map.json"))
    p.add_argument("--lags", type=int, default=DEFAULT_LAGS)
    p.add_argument("--bootstrap-reps", type=int, default=DEFAULT_BOOTSTRAP_REPS)
    p.add_argument("--p-threshold", type=float, default=DEFAULT_P_THRESHOLD)
    p.add_argument("--overwrite", action="store_true",
                   help="Force-clobber an existing cointegration-map.json with "
                        "a different pipeline_config. Without this, the script "
                        "refuses to overwrite.")
    p.add_argument("--dry-run", action="store_true",
                   help="Phase A dev mode: skip Phase B production data load, "
                        "print pipeline_config + idempotency-guard verdict, exit.")
    args = p.parse_args()

    pipeline_config = build_pipeline_config(
        regimes_path=args.regimes_path,
        panels_path=args.panels_path,
        qgi_data_repo_dir=Path("qgi-data"),
        lags=args.lags,
        bootstrap_reps=args.bootstrap_reps,
        p_threshold=args.p_threshold,
    )

    if args.dry_run:
        print("=" * 60)
        print("DRY RUN — Phase A development mode")
        print("=" * 60)
        print(f"pipeline_config: {json.dumps(pipeline_config, indent=2)}")
        action = _check_existing_map(args.output_path, pipeline_config, expected_cells=1)
        print(f"\nIdempotency-guard verdict for {args.output_path}: {action}")
        print(f"Schema version: {COINTEGRATION_MAP_SCHEMA_VERSION}")
        print("Phase A complete. Phase B (production cointegration map run) "
              "requires founder Greenlight 2a.")
        return 0

    # Phase B production path (requires Greenlight 2a — script does not enforce
    # this; the standing rule does. The script will run if invoked, so the
    # surrounding workflow must respect feedback_no_pipeline_runs_without_approval.md).
    print("[585-WARN] Phase A dry-run complete; production execution requires "
          "explicit founder Greenlight 2a per feedback_no_pipeline_runs_without_approval.md. "
          "Re-invoke without --dry-run only after greenlight.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
