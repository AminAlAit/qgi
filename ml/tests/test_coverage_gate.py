"""Unit tests for the sample-truncation coverage gate (#truncation-leak bugfix,
Majles 5/5 2026-05-25). A sparse indicator that drops most positives must FAIL the
gate; a well-covered indicator passes. Synthetic in-memory panels only."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_f_ml_1_poc as drv  # noqa: E402


def _panel(countries, years, value_fn):
    rows = [{"country": c, "year": y, "value": value_fn(c, y)} for c in countries for y in years]
    return pd.DataFrame(rows)


@pytest.fixture
def setup():
    countries = [f"C{i:02d}" for i in range(20)]
    full_years = list(range(1960, 2021))        # broad coverage
    sparse_years = list(range(2010, 2021))       # recent-only (like WGI/NPL)
    panels = {
        "IND_FULL": _panel(countries, full_years, lambda c, y: hash((c, y)) % 100 / 100.0),
        "IND_SPARSE": _panel(countries, sparse_years, lambda c, y: hash((c, y)) % 100 / 100.0),
    }
    # positives clustered OLD (1970s-90s) + a few recent; negatives via build_samples
    pos_rows = [(f"c{i:02d}", 1970 + i) for i in range(18)]  # mostly pre-2010
    pos = pd.DataFrame(pos_rows, columns=["country_id", "year"])
    pos["country"] = pos["country_id"].apply(drv.normalize_country_id)
    pos["label"] = 1
    samples = drv.build_samples(pos, negatives_per_positive=3, seed=0)
    return samples, panels


def test_sparse_indicator_fails_coverage_gate(setup):
    samples, panels = setup
    cov = drv.coverage_report(samples, ["IND_SPARSE"], window=10, panels=panels)
    # sparse (2010+) indicator drops the old positives → low positive survival
    assert cov["pos_coverage"] < drv.MIN_POS_SURVIVAL
    assert drv.coverage_gate_ok(cov) is False


def test_full_indicator_better_coverage(setup):
    samples, panels = setup
    cov_full = drv.coverage_report(samples, ["IND_FULL"], window=10, panels=panels)
    cov_sparse = drv.coverage_report(samples, ["IND_SPARSE"], window=10, panels=panels)
    # the broadly-covered indicator retains far more positives than the sparse one
    assert cov_full["pos_coverage"] > cov_sparse["pos_coverage"]
    assert cov_full["n_pos_survive"] >= cov_sparse["n_pos_survive"]


def test_coverage_gate_thresholds_are_all_enforced():
    # each individual threshold breach trips the gate
    base = {"pos_coverage": 0.9, "neg_coverage": 0.9, "n_pos_survive": 50, "n_countries_survive": 15}
    assert drv.coverage_gate_ok(base) is True
    assert drv.coverage_gate_ok({**base, "pos_coverage": 0.4}) is False        # < MIN_POS_SURVIVAL
    assert drv.coverage_gate_ok({**base, "neg_coverage": 0.5}) is False        # < MIN_NEG_SURVIVAL
    assert drv.coverage_gate_ok({**base, "n_pos_survive": 20}) is False        # < MIN_EFFECTIVE_NPOS
    assert drv.coverage_gate_ok({**base, "n_countries_survive": 5}) is False   # < MIN_SURVIVE_COUNTRIES
