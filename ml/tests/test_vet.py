"""Tests for the indicator-enrichment vet gate (stage 1)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ENRICH_DIR = Path(__file__).resolve().parents[1] / "scripts" / "enrichment"
if str(ENRICH_DIR) not in sys.path:
    sys.path.insert(0, str(ENRICH_DIR))

import vet  # noqa: E402


def _panel(countries, years, value_fn):
    return pd.DataFrame(
        [{"country": c, "year": y, "value": value_fn(c, y)} for c in countries for y in years]
    )


# ---- individual checks ------------------------------------------------------

def test_history_depth_passes_long_fails_short():
    long = _panel(["C0"], range(2000, 2021), lambda c, y: float(y))
    assert vet.check_history_depth(long)["pass"] is True
    short = _panel(["C0"], range(2018, 2023), lambda c, y: float(y))  # 5 years
    r = vet.check_history_depth(short)
    assert r["pass"] is False
    assert r["n_years"] == 5


def test_history_depth_flags_short_history_but_still_passes():
    p = _panel(["C0"], range(2010, 2024), lambda c, y: float(y))  # 14 years, starts 2010
    r = vet.check_history_depth(p)
    assert r["pass"] is True            # >= MIN_YEARS distinct years
    assert r["short_history"] is True   # but starts after the flag year


def test_country_coverage():
    wide = _panel([f"C{i}" for i in range(25)], [2000, 2001], lambda c, y: 1.0 * y)
    assert vet.check_country_coverage(wide)["pass"] is True
    narrow = _panel([f"C{i}" for i in range(10)], [2000, 2001], lambda c, y: 1.0 * y)
    assert vet.check_country_coverage(narrow)["pass"] is False


def test_variance_floor_rejects_mostly_flat():
    countries = [f"C{i}" for i in range(10)]
    years = list(range(2000, 2010))
    # 8 flat (constant) + 2 varying -> frac_zero_variance = 0.8 > 0.20 -> fail
    def vfn(c, y):
        return 5.0 if int(c[1:]) < 8 else float(y)
    r = vet.check_variance_floor(_panel(countries, years, vfn))
    assert r["pass"] is False
    assert r["frac_zero_variance"] == pytest.approx(0.8)
    # all varying -> pass
    assert vet.check_variance_floor(_panel(countries, years, lambda c, y: float(y) + int(c[1:])))["pass"] is True


def test_stationarity_quarantines_i2_passes_i1_and_unknown():
    audit = {"results": {"X1": {"classification": "I(2)_or_higher"},
                         "X2": {"classification": "I(1)"},
                         "X3": {"classification": "I(0)"}}}
    assert vet.check_stationarity("X1", audit)["pass"] is False
    r2 = vet.check_stationarity("X2", audit)
    assert r2["pass"] is True and r2["action"] == "first-diff"
    assert vet.check_stationarity("X3", audit)["pass"] is True
    miss = vet.check_stationarity("X9", audit)        # not in audit
    assert miss["pass"] is True and miss["action"] == "audit-pending"


def test_license_tiers():
    assert vet.check_license("UCDP", "CC BY 4.0")["pass"] is True
    assert vet.check_license("UNDP", "CC BY 3.0 IGO")["tier"] == "cc-igo"
    assert vet.check_license(" X", "GDELT CC0 1.0")["tier"] == "cc0"
    bad = vet.check_license("ACLED", "Commercial license required")
    assert bad["pass"] is False and bad["tier"] == "restricted"
    assert vet.check_license("X", None)["pass"] is True  # unknown passes (forward-looking)


# ---- composed verdict -------------------------------------------------------

def test_vet_indicator_pass_on_clean_panel():
    countries = [f"C{i:02d}" for i in range(25)]
    years = list(range(2000, 2021))
    panel = _panel(countries, years, lambda c, y: float(y) + int(c[1:]))
    r = vet.vet_indicator(panel, indicator_id="IL-02", provider="ILOSTAT", license_str="CC BY 4.0")
    assert r["verdict"] == "PASS"
    assert r["quarantine_reasons"] == []


def test_vet_indicator_quarantines_flat_series():
    countries = [f"C{i:02d}" for i in range(25)]
    years = list(range(2000, 2016))
    panel = _panel(countries, years, lambda c, y: 5.0)  # totally flat
    r = vet.vet_indicator(panel, indicator_id="FLAT", provider="X", license_str="CC BY 4.0")
    assert r["verdict"] == "QUARANTINE"
    assert any(reason.startswith("variance_floor") for reason in r["quarantine_reasons"])


def test_vet_indicator_quarantines_sparse_coverage():
    panel = _panel([f"C{i}" for i in range(6)], range(2000, 2021), lambda c, y: float(y))
    r = vet.vet_indicator(panel, indicator_id="SPARSE", provider="X", license_str="CC BY 4.0")
    assert r["verdict"] == "QUARANTINE"
    assert any(reason.startswith("country_coverage") for reason in r["quarantine_reasons"])


def test_vet_indicator_quarantines_restricted_license():
    countries = [f"C{i:02d}" for i in range(25)]
    years = list(range(2000, 2021))
    panel = _panel(countries, years, lambda c, y: float(y) + int(c[1:]))
    r = vet.vet_indicator(panel, indicator_id="ACLED-1", provider="ACLED",
                          license_str="Commercial license required")
    assert r["verdict"] == "QUARANTINE"
    assert any(reason.startswith("license") for reason in r["quarantine_reasons"])


def test_vet_indicator_quarantines_i2_stationarity():
    countries = [f"C{i:02d}" for i in range(25)]
    years = list(range(2000, 2021))
    panel = _panel(countries, years, lambda c, y: float(y) + int(c[1:]))
    audit = {"results": {"X2IND": {"classification": "I(2)_or_higher"}}}
    r = vet.vet_indicator(panel, indicator_id="X2IND", provider="X",
                          license_str="CC BY 4.0", stationarity_audit=audit)
    assert r["verdict"] == "QUARANTINE"
    assert any(reason.startswith("stationarity") for reason in r["quarantine_reasons"])
    # the quarantined record's action is coherent, not the misleading 'keep'
    assert r["checks"]["stationarity"]["action"] == "quarantine"


def test_recipe_coverage_tripwire_uses_walk_gate():
    pytest.importorskip("run_f_ml_1_poc")  # the driver providing the coverage gate
    import run_f_ml_1_poc as drv
    countries = [f"C{i:02d}" for i in range(12)]
    years = list(range(2000, 2021))
    panel = _panel(countries, years, lambda c, y: float(y) + int(c[1:]))  # full coverage
    # 40 positives across 12 countries (>= MIN_EFFECTIVE_NPOS) -> coverage gate should pass
    pos = pd.DataFrame([{"country": countries[i % 12], "year": 2010 + (i % 8), "label": 1}
                        for i in range(40)])
    samples = drv.build_samples(pos, negatives_per_positive=3, seed=0)
    res = vet.check_recipe_coverage(panel, "IL-02", {"some_recipe": samples})
    assert res["n_recipes"] == 1
    assert res["n_recipes_ok"] == 1
    assert res["pass"] is True
