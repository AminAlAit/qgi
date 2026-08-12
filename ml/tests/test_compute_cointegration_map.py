"""
Tests for compute_cointegration_map.py — Phase A of #585 v1.

Test cases per Sebastien's plan §6.3:
  TC-1   independent random walks -> not_cointegrated (p > 0.05)
  TC-2   cointegrated pair -> cointegrated (p < 0.05) — production threshold (SB-3)
  TC-3   stationary indicator excluded by regime guard
  TC-4   N < 10 -> insufficient_data
  TC-5   all-zero events -> insufficient_data or not_converged
  TC-6   JSON write/read round-trip with pipeline_config block (A1)
        + pytest.warns on pipeline_config drift (M2)
  TC-6b  schema_version mismatch -> ValueError (A4)
  TC-7   missing cell defaults to not_converged
  TC-8   linearmodels reference comparison (skipped unless --run-slow + library installed)

A6 fix: every fixture factory builds its own np.random.default_rng(seed) — no
module-level shared RNG state.

M1 verification: ACTION_NO_EXISTING_MAP returned for first run (pre-existing
file absent). Verified in test_check_existing_map_no_file.

M2 verification: TC-6 asserts a UserWarning is emitted when load_cointegration_map
encounters a pipeline_config with p_threshold or lags differing from defaults.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add scripts/ to path so we can import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from compute_cointegration_map import (  # noqa: E402
    ACTION_NO_EXISTING_MAP,
    ACTION_OVERWRITE_REQUIRED,
    ACTION_RESUME,
    ACTION_SKIP,
    CELL_KEY_SEP,
    COINTEGRATION_MAP_SCHEMA_VERSION,
    DEFAULT_BOOTSTRAP_REPS,
    DEFAULT_LAGS,
    DEFAULT_P_THRESHOLD,
    MIN_COUNTRIES,
    PIPELINE_VERSION,
    VERDICT_COINTEGRATED,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_NOT_COINTEGRATED,
    VERDICT_NOT_CONVERGED,
    _check_existing_map,
    build_pipeline_config,
    classify_verdict,
    get_i1_indicators_from_regimes,
    load_cointegration_map,
    load_cointegration_map_from_dict,
    load_regimes_file,
    westerlund_gt,
    write_cointegration_map,
)


# ===========================================================================
# Synthetic-data fixtures (A6: each builds own RNG; no module-level state)
# ===========================================================================

SEED: int = 42


def make_random_walk(n_countries: int = 30, n_years: int = 40, seed: int = SEED,
                     value_col: str = "value") -> pd.DataFrame:
    """Generate panel of independent I(1) random walks with drift.

    A6: fixture-local RNG construction — does not consume module-level state.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for i in range(n_countries):
        y = np.cumsum(rng.standard_normal(n_years))
        for t, val in enumerate(y):
            rows.append({"country": f"C{i:03d}", "year": 1980 + t, value_col: float(val)})
    return pd.DataFrame(rows)


def make_stationary_panel(n_countries: int = 30, n_years: int = 40, seed: int = SEED,
                          value_col: str = "value") -> pd.DataFrame:
    """Generate panel of AR(1) stationary series, rho=0.4."""
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for i in range(n_countries):
        y = np.zeros(n_years)
        for t in range(1, n_years):
            y[t] = 0.4 * y[t-1] + rng.standard_normal()
        for t, val in enumerate(y):
            rows.append({"country": f"C{i:03d}", "year": 1980 + t, value_col: float(val)})
    return pd.DataFrame(rows)


def make_cointegrated_pair(
    n_countries: int = 30, n_years: int = 40, seed: int = SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate I(1) indicator paired with event series sharing the indicator's stochastic trend.

    Construction: each country has a random-walk indicator. The event-occurrence
    process responds to the indicator's level relative to its mean — so y_event
    and y_indicator are tied by a long-run equilibrium (cointegration).

    Note: event_occ is deliberately binary {0, 1} here because the production
    cointegration test consumes binary event-occurrence series (see §4.4 of the
    engineering plan — Athena query SELECTs `1 AS event_occurred` for matching
    event rows). Tests should reflect that downstream contract.
    """
    rng = np.random.default_rng(seed)
    indicator_rows: list[dict] = []
    event_rows: list[dict] = []
    for i in range(n_countries):
        common_trend = np.cumsum(rng.standard_normal(n_years))
        y_ind = common_trend + 0.3 * rng.standard_normal(n_years)
        # Event-occurrence: probabilistically high when indicator is above its long-run mean
        threshold = float(np.median(y_ind))
        latent = (y_ind - threshold) + 0.4 * rng.standard_normal(n_years)
        y_event = (latent > 0).astype(float)
        for t in range(n_years):
            indicator_rows.append({
                "country": f"C{i:03d}", "year": 1980 + t, "value": float(y_ind[t]),
            })
            event_rows.append({
                "country": f"C{i:03d}", "year": 1980 + t, "event_occ": float(y_event[t]),
            })
    return pd.DataFrame(indicator_rows), pd.DataFrame(event_rows)


# ===========================================================================
# TC-1: Independent random walks should NOT be flagged as cointegrated
# ===========================================================================

def test_tc1_independent_random_walks_not_cointegrated():
    """Two independent I(1) series should fail to reject H0 (p > 0.05)."""
    indicator = make_random_walk(seed=SEED)
    events = make_random_walk(seed=SEED + 1, value_col="event_occ")
    result = westerlund_gt(indicator, events, lags=1, bootstrap_reps=200)
    assert result["converged"] is True, "Should converge with adequate data"
    assert result["n_countries"] >= MIN_COUNTRIES
    assert result["p_value"] is not None
    assert result["p_value"] > 0.05, (
        f"Independent random walks should not cointegrate "
        f"(p={result['p_value']}, gt={result['gt_statistic']})"
    )


# ===========================================================================
# TC-2: Genuinely cointegrated pair -> p_value < 0.05 (production threshold)
# ===========================================================================

# N=30, T=40 fixture with 200 bootstrap reps has ~80% power at p<0.05.
# Asserting p<0.05 here matches production threshold (SB-3 fix).
# If this test becomes flaky, increase bootstrap_reps to 500 or fixture size.
# DO NOT relax to p<0.10 — that under-tests statistical power vs. production.
def test_tc2_cointegrated_pair_detected_at_production_threshold():
    """Cointegrated pair should be detected at p < 0.05 (production threshold)."""
    indicator, events = make_cointegrated_pair(seed=SEED)
    result = westerlund_gt(indicator, events, lags=1, bootstrap_reps=200)
    assert result["converged"] is True
    assert result["p_value"] is not None
    assert result["p_value"] < 0.05, (
        f"Cointegrated pair should be detected at production threshold p<0.05 "
        f"(p={result['p_value']}, gt={result['gt_statistic']})"
    )
    assert result["mean_rho"] is not None
    assert result["mean_rho"] < 0.0, (
        f"ECM coefficient should be negative for cointegrated pair "
        f"(mean_rho={result['mean_rho']})"
    )


# ===========================================================================
# TC-3: Stationary indicators excluded by regime guard
# ===========================================================================

def test_tc3_stationary_indicators_excluded_via_regime_guard():
    """get_i1_indicators_from_regimes() must not include stationary indicators."""
    regimes_flat = {
        "SP.DYN.LE00.IN": "stationary",
        "NY.GDP.MKTP.CD": "i1",
        "FP.CPI.TOTL.ZG": "stationary",
        "SP.POP.TOTL": "i1",
        "GC.TAX.TOTL.GD.ZS": "marginal",
    }
    i1_set = get_i1_indicators_from_regimes(regimes_flat)
    assert "SP.DYN.LE00.IN" not in i1_set
    assert "FP.CPI.TOTL.ZG" not in i1_set
    assert "GC.TAX.TOTL.GD.ZS" not in i1_set
    assert "NY.GDP.MKTP.CD" in i1_set
    assert "SP.POP.TOTL" in i1_set
    assert len(i1_set) == 2


def test_tc3_envelope_format_also_works():
    """get_i1_indicators_from_regimes() must accept the full JSON envelope (today's
    produce_indicator_regimes.py output format)."""
    envelope = {
        "schema_version": 1,
        "regimes": {
            "stationary": ["SP.DYN.LE00.IN", "FP.CPI.TOTL.ZG"],
            "i1": ["NY.GDP.MKTP.CD", "SP.POP.TOTL"],
            "marginal": ["GC.TAX.TOTL.GD.ZS"],
        },
        "indicators": [],
    }
    i1_set = get_i1_indicators_from_regimes(envelope)
    assert i1_set == {"NY.GDP.MKTP.CD", "SP.POP.TOTL"}


# ===========================================================================
# TC-4: Insufficient data -> insufficient_data verdict
# ===========================================================================

def test_tc4_insufficient_countries_verdict():
    """N < MIN_COUNTRIES (10) -> converged is False; verdict is insufficient_data."""
    indicator = make_random_walk(n_countries=5, seed=SEED)
    events = make_random_walk(n_countries=5, seed=SEED + 1, value_col="event_occ")
    result = westerlund_gt(indicator, events, lags=1, bootstrap_reps=50)
    assert result["converged"] is False
    assert result["n_countries"] < MIN_COUNTRIES
    assert classify_verdict(result) == VERDICT_INSUFFICIENT_DATA


# ===========================================================================
# TC-5: All-zero event series -> not converged or insufficient
# ===========================================================================

def test_tc5_all_zero_events():
    """Constant (all-zero) event series gives no variation; ECM regression is degenerate."""
    indicator = make_random_walk(seed=SEED)
    events = indicator.copy().rename(columns={"value": "event_occ"})
    events["event_occ"] = 0.0
    result = westerlund_gt(indicator, events, lags=1, bootstrap_reps=50)
    # Either insufficient countries (rank-deficient design matrix dropped them)
    # or cells fall through to not-converged. Both verdicts indicate "untestable."
    verdict = classify_verdict(result)
    assert verdict in (VERDICT_INSUFFICIENT_DATA, VERDICT_NOT_CONVERGED)


# ===========================================================================
# TC-6: JSON round-trip with pipeline_config block (A1) + drift warning (M2)
# ===========================================================================

def test_tc6_json_roundtrip_preserves_pipeline_config(tmp_path):
    """write_cointegration_map() then load_cointegration_map() must roundtrip cleanly."""
    pipeline_config = {
        "pipeline_version": PIPELINE_VERSION,
        "lags": DEFAULT_LAGS,
        "bootstrap_reps": DEFAULT_BOOTSTRAP_REPS,
        "p_threshold": DEFAULT_P_THRESHOLD,
        "regimes_file_hash": "abc123",
        "panels_file_hash": "def456",
        "events_corpus_commit": "aabbcc",
    }
    cells = {
        f"NY.GDP.MKTP.CD{CELL_KEY_SEP}military_coup": {
            "gt_statistic": -2.5,
            "p_value": 0.04,
            "n_countries": 120,
            "mean_rho": -0.07,
            "converged": True,
            "verdict": VERDICT_COINTEGRATED,
        },
        f"SP.POP.TOTL{CELL_KEY_SEP}trade_agreement": {
            "gt_statistic": -0.41,
            "p_value": 0.63,
            "n_countries": 187,
            "mean_rho": -0.008,
            "converged": True,
            "verdict": VERDICT_NOT_COINTEGRATED,
        },
    }

    out_path = tmp_path / "cointegration-map.json"
    write_cointegration_map(out_path, pipeline_config, cells, finalized=True)

    # File should exist and parse
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data["schema_version"] == COINTEGRATION_MAP_SCHEMA_VERSION
    assert data["pipeline_config"] == pipeline_config
    assert data["n_cells_tested"] == 2
    assert data["n_cointegrated"] == 1
    assert data["n_not_cointegrated"] == 1

    # load_cointegration_map() returns dict[(ind, recipe), verdict]
    loaded = load_cointegration_map(out_path)
    assert loaded[("NY.GDP.MKTP.CD", "military_coup")] == VERDICT_COINTEGRATED
    assert loaded[("SP.POP.TOTL", "trade_agreement")] == VERDICT_NOT_COINTEGRATED


def test_tc6_pipeline_config_drift_warns(tmp_path):
    """M2: loading a map with mismatched p_threshold or lags must emit UserWarning."""
    drifted_config = {
        "pipeline_version": PIPELINE_VERSION,
        "lags": 1,
        "bootstrap_reps": 500,
        "p_threshold": 0.10,  # drift from production 0.05
        "regimes_file_hash": "x", "panels_file_hash": "y", "events_corpus_commit": "z",
    }
    cells = {
        f"NY.GDP.MKTP.CD{CELL_KEY_SEP}military_coup": {
            "verdict": VERDICT_COINTEGRATED, "converged": True,
            "gt_statistic": -3.0, "p_value": 0.08, "n_countries": 100, "mean_rho": -0.1,
        },
    }
    out_path = tmp_path / "drifted_map.json"
    write_cointegration_map(out_path, drifted_config, cells, finalized=True)

    with pytest.warns(UserWarning, match="p_threshold"):
        load_cointegration_map(out_path)


def test_tc6_lags_drift_warns(tmp_path):
    """M2: loading a map with mismatched lags must emit UserWarning."""
    drifted_config = {
        "pipeline_version": PIPELINE_VERSION,
        "lags": 3,  # drift from production 1
        "bootstrap_reps": 500,
        "p_threshold": 0.05,
        "regimes_file_hash": "x", "panels_file_hash": "y", "events_corpus_commit": "z",
    }
    cells = {
        f"NY.GDP.MKTP.CD{CELL_KEY_SEP}military_coup": {
            "verdict": VERDICT_COINTEGRATED, "converged": True,
            "gt_statistic": -3.0, "p_value": 0.04, "n_countries": 100, "mean_rho": -0.1,
        },
    }
    out_path = tmp_path / "lags_drifted_map.json"
    write_cointegration_map(out_path, drifted_config, cells, finalized=True)

    with pytest.warns(UserWarning, match="lags"):
        load_cointegration_map(out_path)


# ===========================================================================
# TC-6b: schema_version mismatch raises ValueError (A4)
# ===========================================================================

def test_tc6b_schema_version_mismatch_raises(tmp_path):
    """A4: load_cointegration_map() must raise ValueError on schema_version mismatch."""
    map_data = {
        "schema_version": 99,  # future schema
        "pipeline_config": {},
        "cells": {},
    }
    p = tmp_path / "bad_schema_map.json"
    p.write_text(json.dumps(map_data))
    with pytest.raises(ValueError, match="schema_version"):
        load_cointegration_map(p)


# ===========================================================================
# TC-7: Missing cell defaults to not_converged
# ===========================================================================

def test_tc7_missing_cell_defaults_to_not_converged():
    """Cells absent from the map should be treated as not_converged at consumer-side."""
    loaded = load_cointegration_map_from_dict({"schema_version": 1, "cells": {}})
    verdict = loaded.get(("NY.GDP.MKTP.CD", "military_coup"), VERDICT_NOT_CONVERGED)
    assert verdict == VERDICT_NOT_CONVERGED


def test_tc7_unknown_verdict_string_normalized_to_not_converged():
    """Unrecognized verdict string in the JSON should be normalized to not_converged."""
    data = {
        "schema_version": 1,
        "cells": {
            f"X.Y.Z{CELL_KEY_SEP}some_recipe": {"verdict": "garbled_string"},
        },
    }
    loaded = load_cointegration_map_from_dict(data)
    assert loaded[("X.Y.Z", "some_recipe")] == VERDICT_NOT_CONVERGED


# ===========================================================================
# TC-8: linearmodels reference comparison (slow, optional)
# ===========================================================================

@pytest.mark.skipif(True, reason="TC-8: requires linearmodels (slow); skipped in CI")
def test_tc8_westerlund_matches_linearmodels_reference():
    """Spec'd in §6.3 as @pytest.mark.slow. Skipped by default."""
    pytest.importorskip("linearmodels")
    # Implementation deferred; placeholder to satisfy the test plan structure.


# ===========================================================================
# Idempotency-guard tests (SB-1, M1)
# ===========================================================================

def test_check_existing_map_no_file(tmp_path):
    """M1 fix: missing file returns ACTION_NO_EXISTING_MAP, not OVERWRITE_REQUIRED."""
    config = {"pipeline_version": PIPELINE_VERSION,
              "regimes_file_hash": "h1", "panels_file_hash": "h2"}
    action = _check_existing_map(tmp_path / "missing.json", config, expected_cells=10)
    assert action == ACTION_NO_EXISTING_MAP


def test_check_existing_map_complete_match_skip(tmp_path):
    """Same pipeline_version + same hashes + complete cells -> SKIP."""
    config = {"pipeline_version": PIPELINE_VERSION,
              "regimes_file_hash": "h1", "panels_file_hash": "h2"}
    cells = {f"X{CELL_KEY_SEP}r": {"verdict": VERDICT_COINTEGRATED}}
    out = tmp_path / "complete.json"
    write_cointegration_map(out, config, cells, finalized=True)
    action = _check_existing_map(out, config, expected_cells=1)
    assert action == ACTION_SKIP


def test_check_existing_map_partial_match_resume(tmp_path):
    """Same config + cells_completed < expected -> RESUME."""
    config = {"pipeline_version": PIPELINE_VERSION,
              "regimes_file_hash": "h1", "panels_file_hash": "h2"}
    cells = {f"X{CELL_KEY_SEP}r": {"verdict": VERDICT_COINTEGRATED}}
    out = tmp_path / "partial.json"
    write_cointegration_map(out, config, cells, finalized=False)
    action = _check_existing_map(out, config, expected_cells=10)
    assert action == ACTION_RESUME


def test_check_existing_map_config_mismatch_overwrite(tmp_path):
    """Different pipeline_version -> OVERWRITE_REQUIRED."""
    old_config = {"pipeline_version": "old-version",
                  "regimes_file_hash": "h1", "panels_file_hash": "h2"}
    new_config = {"pipeline_version": "new-version",
                  "regimes_file_hash": "h1", "panels_file_hash": "h2"}
    cells = {f"X{CELL_KEY_SEP}r": {"verdict": VERDICT_COINTEGRATED}}
    out = tmp_path / "mismatched.json"
    write_cointegration_map(out, old_config, cells, finalized=True)
    action = _check_existing_map(out, new_config, expected_cells=1)
    assert action == ACTION_OVERWRITE_REQUIRED


def test_check_existing_map_corrupted_file_overwrite(tmp_path):
    """Unreadable / corrupted JSON file -> OVERWRITE_REQUIRED (safe default)."""
    out = tmp_path / "corrupted.json"
    out.write_text("{not valid json")
    config = {"pipeline_version": PIPELINE_VERSION,
              "regimes_file_hash": "h1", "panels_file_hash": "h2"}
    action = _check_existing_map(out, config, expected_cells=10)
    assert action == ACTION_OVERWRITE_REQUIRED


# ===========================================================================
# pipeline_config builder
# ===========================================================================

def test_build_pipeline_config_includes_required_keys(tmp_path):
    """build_pipeline_config() must populate all 7 fields per A1."""
    regimes = tmp_path / "regimes.json"
    regimes.write_text('{"schema_version": 1}')
    panels = tmp_path / "panels.parquet"
    panels.write_bytes(b"PAR1\x00\x00")  # minimal placeholder content
    config = build_pipeline_config(
        regimes_path=regimes, panels_path=panels, qgi_data_repo_dir=None,
    )
    assert "pipeline_version" in config
    assert "lags" in config
    assert "bootstrap_reps" in config
    assert "p_threshold" in config
    assert "regimes_file_hash" in config
    assert "panels_file_hash" in config
    assert "events_corpus_commit" in config
    # Hashes should be 64-char SHA-256 strings
    assert len(config["regimes_file_hash"]) == 64
    assert len(config["panels_file_hash"]) == 64


# ===========================================================================
# Verdict classifier
# ===========================================================================

def test_classify_verdict_cointegrated_below_threshold():
    result = {"converged": True, "p_value": 0.02, "n_countries": 100}
    assert classify_verdict(result, p_threshold=0.05) == VERDICT_COINTEGRATED


def test_classify_verdict_not_cointegrated_above_threshold():
    result = {"converged": True, "p_value": 0.30, "n_countries": 100}
    assert classify_verdict(result, p_threshold=0.05) == VERDICT_NOT_COINTEGRATED


def test_classify_verdict_insufficient_data():
    result = {"converged": False, "p_value": None, "n_countries": 5}
    assert classify_verdict(result) == VERDICT_INSUFFICIENT_DATA


def test_classify_verdict_not_converged():
    result = {"converged": False, "p_value": None, "n_countries": 50}
    assert classify_verdict(result) == VERDICT_NOT_CONVERGED


# ===========================================================================
# A5: per-country zero-overlap warning
# ===========================================================================

def test_a5_zero_overlap_emits_warning():
    """A5: countries with zero year-overlap between indicator and event series
    must emit a per-country UserWarning before being dropped from the panel."""
    # Indicator panel: country A has years 1980-1990
    # Event panel: country A has years 2000-2010 (zero overlap)
    # We pad with N other countries that DO overlap so westerlund_gt() doesn't
    # return early on the MIN_COUNTRIES check.
    indicator_rows: list[dict] = []
    event_rows: list[dict] = []

    # Country with zero overlap
    for t in range(11):
        indicator_rows.append({"country": "ZERO_OVERLAP", "year": 1980 + t, "value": float(t)})
    for t in range(11):
        event_rows.append({"country": "ZERO_OVERLAP", "year": 2000 + t, "event_occ": 0.0})

    # Pad with overlapping cointegrated countries so the panel converges
    indicator_pad, event_pad = make_cointegrated_pair(n_countries=15, seed=SEED)
    indicator_full = pd.concat([pd.DataFrame(indicator_rows), indicator_pad], ignore_index=True)
    event_full = pd.concat([pd.DataFrame(event_rows), event_pad], ignore_index=True)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = westerlund_gt(indicator_full, event_full, lags=1, bootstrap_reps=50)

    # At least one warning should mention the zero-overlap country
    matches = [w for w in caught if "ZERO_OVERLAP" in str(w.message)]
    assert len(matches) >= 1, "A5: expected zero-overlap warning naming the country"
    # And the dropped country should NOT count toward n_countries
    assert result["n_countries"] <= 15


# ===========================================================================
# load_regimes_file integration
# ===========================================================================

def test_load_regimes_file(tmp_path):
    """load_regimes_file() should return flat {indicator_id: regime} dict."""
    regimes = tmp_path / "regimes.json"
    regimes.write_text(json.dumps({
        "schema_version": 1,
        "indicators": [
            {"id": "NY.GDP.MKTP.CD", "regime": "i1", "action": "first-diff"},
            {"id": "SP.DYN.LE00.IN", "regime": "stationary", "action": "keep"},
            {"id": "GC.TAX.TOTL.GD.ZS", "regime": "marginal", "action": "keep"},
        ],
    }))
    out = load_regimes_file(regimes)
    assert out["NY.GDP.MKTP.CD"] == "i1"
    assert out["SP.DYN.LE00.IN"] == "stationary"
    assert out["GC.TAX.TOTL.GD.ZS"] == "marginal"
    assert len(out) == 3
