"""Unit tests for the T12 real-data MCMC sweep driver.

Scope (per qgi-aws-tf#743 + #744 follow-ups):
  - `route_verdict_against_5_2_2` — pure function, exhaustively tested against
    the spec §5.2.2 4-tier exit table (docs-specs `0db64f9`) + §5.2.5 silent-corner
    protocol additions (HDI-entirely-negative case from v6, P>0.25-while-straddling
    case flagged by QA review of qgi-ml#71).

The function lives in scripts/run_t12_real_data_sweep.py. Loading the script
under a stub `validate_weight_matrix_bayes` module so we don't accidentally
import pymc/arviz in unit tests.

"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_t12_real_data_sweep.py"


def _load_driver_module():
    """Import the driver module while stubbing pymc + arviz so unit tests
    can run without the heavy MCMC dependencies installed."""
    had_pymc = "pymc" in sys.modules
    had_arviz = "arviz" in sys.modules
    sys.modules.setdefault("pymc", MagicMock())
    sys.modules.setdefault("arviz", MagicMock())
    if "validate_weight_matrix_bayes" not in sys.modules:
        stub = MagicMock()
        stub.N_CHAINS = 4
        stub.N_TUNE = 1000
        stub.N_DRAWS = 2000
        stub.TARGET_ACCEPT = 0.99
        stub.MAX_TREEDEPTH = 12
        sys.modules["validate_weight_matrix_bayes"] = stub
    try:
        spec = importlib.util.spec_from_file_location("run_t12_real_data_sweep", _SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["run_t12_real_data_sweep"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if not had_pymc:
            sys.modules.pop("pymc", None)
        if not had_arviz:
            sys.modules.pop("arviz", None)


driver = _load_driver_module()


# ============================================================================
# §5.2.2 4-tier exit table — verbatim spec coverage
# ============================================================================

def test_hard_falsify_typical():
    """HDI straddles zero AND P(swing > 0.05) < 0.05."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.01, hdi_low=-0.04, hdi_high=0.06,
        posterior_prob_swing_gt_005=0.03,
        anchor_battery_pass_count=1,
    )
    assert v["tier"] == "HARD-FALSIFY"
    assert "HARD-FALSIFY" in v["consequence"] or "T14" in v["consequence"]


def test_hard_falsify_boundary_just_below_005():
    """Boundary: P = 0.049 → HARD-FALSIFY (under 0.05)."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.0, hdi_low=-0.05, hdi_high=0.05,
        posterior_prob_swing_gt_005=0.049,
        anchor_battery_pass_count=2,
    )
    assert v["tier"] == "HARD-FALSIFY"


def test_soft_falsify_typical():
    """HDI straddles zero AND P ∈ [0.05, 0.25]."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.02, hdi_low=-0.03, hdi_high=0.07,
        posterior_prob_swing_gt_005=0.15,
        anchor_battery_pass_count=1,
    )
    assert v["tier"] == "SOFT-FALSIFY"
    assert "ML" in v["consequence"]


def test_soft_falsify_boundary_at_005():
    """Boundary: P = 0.05 → SOFT-FALSIFY (inclusive lower)."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.02, hdi_low=-0.03, hdi_high=0.07,
        posterior_prob_swing_gt_005=0.05,
        anchor_battery_pass_count=1,
    )
    assert v["tier"] == "SOFT-FALSIFY"


def test_soft_falsify_boundary_at_025():
    """Boundary: P = 0.25 → SOFT-FALSIFY (inclusive upper)."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.03, hdi_low=-0.04, hdi_high=0.10,
        posterior_prob_swing_gt_005=0.25,
        anchor_battery_pass_count=1,
    )
    assert v["tier"] == "SOFT-FALSIFY"


def test_partial_hdi_excludes_zero_lower_below_010():
    """HDI excludes zero in methodology-favoring direction; HDI_low < 0.10."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.06, hdi_low=0.02, hdi_high=0.10,
        posterior_prob_swing_gt_005=0.55,
        anchor_battery_pass_count=4,
    )
    assert v["tier"] == "PARTIAL"
    assert "6-seat" in v["consequence"]


def test_pass_typical():
    """HDI_low ≥ 0.10 AND anchor ≥ 6/8."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.20, hdi_low=0.12, hdi_high=0.28,
        posterior_prob_swing_gt_005=0.99,
        anchor_battery_pass_count=7,
    )
    assert v["tier"] == "PASS"
    assert "Phase 6" in v["consequence"]


def test_pass_anchor_short_demotes_to_partial():
    """HDI_low ≥ 0.10 BUT anchor < 6/8 → PARTIAL (country-axis evidence weak)."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.20, hdi_low=0.15, hdi_high=0.28,
        posterior_prob_swing_gt_005=0.99,
        anchor_battery_pass_count=5,
    )
    assert v["tier"] == "PARTIAL"


def test_pass_boundary_hdi_low_at_010():
    """Boundary: HDI_low = 0.10 → PASS (inclusive ≥)."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.20, hdi_low=0.10, hdi_high=0.28,
        posterior_prob_swing_gt_005=0.99,
        anchor_battery_pass_count=8,
    )
    assert v["tier"] == "PASS"


# ============================================================================
# §5.2.5 silent-corner protocol — NEW post-v6
# ============================================================================

def test_inconsistent_anti_methodology_v6_case():
    """v6 ACTUAL CASE: HDI entirely below zero. Driver MUST route to
    INCONSISTENT-anti-methodology, NOT spec-literal PARTIAL — this was
    the bug QA flagged in the original driver (qgi-ml#71)."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=-0.335, hdi_low=-0.346, hdi_high=-0.325,
        posterior_prob_swing_gt_005=0.0,
        anchor_battery_pass_count=0,
    )
    assert v["tier"] == "INCONSISTENT-anti-methodology"
    assert "6-seat" in v["consequence"]
    assert "HARD-FALSIFY-direction" in v["tier_definition"]
    assert "§5.2.5" in v["tier_definition"] or "silent" in v["tier_definition"]


def test_inconsistent_anti_methodology_boundary():
    """Boundary: HDI_high just below zero → INCONSISTENT-anti-methodology."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=-0.02, hdi_low=-0.05, hdi_high=-0.001,
        posterior_prob_swing_gt_005=0.0,
        anchor_battery_pass_count=0,
    )
    assert v["tier"] == "INCONSISTENT-anti-methodology"


def test_boundary_hdi_high_at_zero_routes_to_straddle():
    """Boundary: hdi_high == 0 exactly. Per the driver's documented
    convention, this falls to hdi_straddles_zero (inclusive), NOT to
    hdi_entirely_negative (strict). Measure-zero in practice but pinning
    the contract per QA review N-2 of qgi-ml#73."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=-0.02, hdi_low=-0.04, hdi_high=0.0,
        posterior_prob_swing_gt_005=0.0,
        anchor_battery_pass_count=1,
    )
    # Straddles + P < 0.05 → HARD-FALSIFY (spec branch), NOT silent corner
    assert v["tier"] == "HARD-FALSIFY"
    assert "INCONSISTENT" not in v["tier"]


def test_inconsistent_routing_anomaly_p_gt_025_while_straddling():
    """Edge case: HDI straddles zero AND P > 0.25. Spec is silent;
    must route to INCONSISTENT-routing-anomaly per §5.2.5, NOT to
    invented PARTIAL tier (the off-spec branch QA flagged in the
    original driver)."""
    v = driver.route_verdict_against_5_2_2(
        posterior_mean=0.04, hdi_low=-0.03, hdi_high=0.11,
        posterior_prob_swing_gt_005=0.40,
        anchor_battery_pass_count=2,
    )
    assert v["tier"] == "INCONSISTENT-routing-anomaly"
    assert "6-seat" in v["consequence"]


# ============================================================================
# Anchor loader contract (#743 follow-up DEFERRED but JSON-key fix in place)
# ============================================================================

def _make_anchor_json(tmp_path, cases):
    """Test helper — writes a minimal cascade-anchor-case-battery.json shape."""
    import json as _json
    p = tmp_path / "cascade-anchor-case-battery.json"
    p.write_text(_json.dumps({
        "schema_version": 1,
        "cases": cases,
    }), encoding="utf-8")
    return p


def _make_cells_stub(country_ids):
    """Test helper — cells stub with country_labels = str(int) for each id."""
    cells = MagicMock()
    cells.country_labels = [str(cid) for cid in country_ids]
    return cells


def test_anchor_loader_resolves_in_universe_cases(tmp_path, capsys):
    """post-qgi-data#54: anchor JSON has top-level `cases` (NOT
    `anchor_cases`) array with `country_id` integer field per case.
    Resolver returns in-universe + cells-present ids."""
    p = _make_anchor_json(tmp_path, [
        {"case_id": 1, "country": "Malta", "country_id": 134,
         "in_evaluation_universe": False},
        {"case_id": 4, "country": "Tunisia", "country_id": 227,
         "in_evaluation_universe": True},
        {"case_id": 5, "country": "Sri Lanka", "country_id": 211,
         "in_evaluation_universe": True},
        {"case_id": 8, "country": "Yemen", "country_id": 248,
         "in_evaluation_universe": True},
    ])
    cells = _make_cells_stub([227, 211, 248, 100, 50])  # 3 anchors in cells
    result = driver._load_anchor_country_ids(cells, p)
    assert sorted(result) == [211, 227, 248]
    captured = capsys.readouterr()
    assert "3 in-universe" in captured.out
    assert "1 out-of-universe" in captured.out


def test_anchor_loader_skips_out_of_universe(tmp_path):
    """in_evaluation_universe=false → skip per Phase 6 gate."""
    p = _make_anchor_json(tmp_path, [
        {"case_id": 1, "country": "Malta", "country_id": 134,
         "in_evaluation_universe": False},
        {"case_id": 2, "country": "Iceland", "country_id": 99,
         "in_evaluation_universe": False},
        {"case_id": 3, "country": "Norway", "country_id": 165,
         "in_evaluation_universe": True},
    ])
    cells = _make_cells_stub([134, 99, 165])  # all 3 in cells
    result = driver._load_anchor_country_ids(cells, p)
    assert result == [165]  # only Norway (in-universe)


def test_anchor_loader_skips_missing_from_cells(tmp_path, capsys):
    """in-universe anchor whose country_id is NOT in cells → skip with warning."""
    p = _make_anchor_json(tmp_path, [
        {"case_id": 4, "country": "Tunisia", "country_id": 227,
         "in_evaluation_universe": True},
        {"case_id": 5, "country": "Sri Lanka", "country_id": 211,
         "in_evaluation_universe": True},
    ])
    cells = _make_cells_stub([227])  # only Tunisia in cells; Sri Lanka missing
    result = driver._load_anchor_country_ids(cells, p)
    assert result == [227]
    captured = capsys.readouterr()
    assert "1 missing from v6 cells" in captured.out
    assert "Sri Lanka" in captured.out


def test_anchor_loader_warns_on_missing_country_id_field(tmp_path, capsys):
    """Case without country_id field → skip + warn (qgi-data#54 enrichment expected)."""
    p = _make_anchor_json(tmp_path, [
        {"case_id": 4, "country": "Tunisia",
         "in_evaluation_universe": True},  # NO country_id
    ])
    cells = _make_cells_stub([227])
    result = driver._load_anchor_country_ids(cells, p)
    assert result == []
    captured = capsys.readouterr()
    assert "missing country_id" in captured.out
    assert "qgi-data#54" in captured.out


def test_anchor_loader_missing_file_returns_empty(tmp_path):
    """Missing anchor JSON should not raise; emit warning + empty list."""
    missing_path = tmp_path / "nonexistent.json"
    cells_stub = MagicMock()
    result = driver._load_anchor_country_ids(cells_stub, missing_path)
    assert result == []
