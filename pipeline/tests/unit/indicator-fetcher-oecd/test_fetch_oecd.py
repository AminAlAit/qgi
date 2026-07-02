"""Tests for the OECD SDMX fetcher transform (enrichment stage 2).

Pure logic only — no AWS, no network (the base's AWS clients are lazy and
requests is lazy-imported inside _fetch_oecd_csv, so importing the module
needs neither boto3 nor requests).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_QGI_PIPELINE = Path(__file__).resolve().parents[3]
_BASE_DIR = _QGI_PIPELINE / "batch" / "_fetcher_base"
_OECD_SRC = _QGI_PIPELINE / "batch" / "indicator-fetcher-oecd" / "src"
for _p in (_BASE_DIR, _OECD_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qgi_fetcher_base as base  # noqa: E402
import fetch_oecd as f  # noqa: E402


# ---- helpers -----------------------------------------------------------------

ISO3 = {
    "USA": "United States",
    "DEU": "Germany",
    "FRA": "France",
    "GBR": "United Kingdom",
    "JPN": "Japan",
    "AUS": "Australia",
}


def _make_csv_df(rows: list[dict]) -> pd.DataFrame:
    """Build a representative OECD SDMX csvfilewithlabels DataFrame from a list
    of row dicts.  All missing keys default to empty string so the parser
    doesn't crash on optional columns."""
    # Union of all keys across rows as columns
    all_keys: set[str] = set()
    for r in rows:
        all_keys.update(r.keys())
    out = []
    for r in rows:
        out.append({k: r.get(k, "") for k in all_keys})
    return pd.DataFrame(out)


# ---- _to_iso3 ---------------------------------------------------------------


def test_to_iso3_passes_through_alpha3():
    assert f._to_iso3("USA") == "USA"
    assert f._to_iso3("deu") == "DEU"


def test_to_iso3_converts_alpha2():
    assert f._to_iso3("US") == "USA"
    assert f._to_iso3("de") == "DEU"
    assert f._to_iso3("GB") == "GBR"


def test_to_iso3_unknown_returns_empty():
    assert f._to_iso3("XX") == ""
    assert f._to_iso3("XXXX") == ""
    assert f._to_iso3("") == ""


# ---- _extract_year ----------------------------------------------------------


def test_extract_year_annual():
    assert f._extract_year("2023") == 2023


def test_extract_year_quarterly():
    assert f._extract_year("2022-Q3") == 2022
    assert f._extract_year("2021-Q1") == 2021


def test_extract_year_monthly():
    assert f._extract_year("2020-03") == 2020
    assert f._extract_year("2019-12") == 2019


def test_extract_year_invalid():
    assert f._extract_year("") is None
    assert f._extract_year("Q1-2023") is None
    assert f._extract_year(None) is None


# ---- parse_oecd_csv — OE-01 CLI (monthly -> annual mean) --------------------

CLI_SPEC = f.SPECS["OE-01"]


def test_cli_monthly_aggregated_to_annual_mean():
    """Monthly CLI records for the same country-year should be meaned."""
    rows = [
        {"REF_AREA": "USA", "TIME_PERIOD": "2022-01", "OBS_VALUE": "100.0", "SUBJECT": "LI", "MEASURE": "AA"},
        {"REF_AREA": "USA", "TIME_PERIOD": "2022-06", "OBS_VALUE": "102.0", "SUBJECT": "LI", "MEASURE": "AA"},
        {"REF_AREA": "USA", "TIME_PERIOD": "2022-12", "OBS_VALUE": "98.0", "SUBJECT": "LI", "MEASURE": "AA"},
        # Different year
        {"REF_AREA": "DEU", "TIME_PERIOD": "2022-06", "OBS_VALUE": "99.5", "SUBJECT": "LI", "MEASURE": "AA"},
    ]
    df_raw = _make_csv_df(rows)
    out = f.parse_oecd_csv(df_raw, CLI_SPEC, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}

    # USA 2022: mean(100, 102, 98) = 100.0
    assert abs(recs[("United States", 2022)] - 100.0) < 1e-9
    assert abs(recs[("Germany", 2022)] - 99.5) < 1e-9


def test_cli_filters_out_non_aa_measure():
    """Rows with MEASURE != AA should be filtered before aggregation."""
    rows = [
        {
            "REF_AREA": "USA",
            "TIME_PERIOD": "2022-01",
            "OBS_VALUE": "105.0",
            "SUBJECT": "LI",
            "MEASURE": "TR",
        },  # trend — should be dropped
        {
            "REF_AREA": "USA",
            "TIME_PERIOD": "2022-01",
            "OBS_VALUE": "100.0",
            "SUBJECT": "LI",
            "MEASURE": "AA",
        },  # amplitude-adjusted — kept
    ]
    df_raw = _make_csv_df(rows)
    out = f.parse_oecd_csv(df_raw, CLI_SPEC, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # Only the AA row survives
    assert recs[("United States", 2022)] == 100.0
    assert len(out) == 1


def test_cli_drops_unknown_iso3():
    rows = [
        {"REF_AREA": "ZZZ", "TIME_PERIOD": "2022-03", "OBS_VALUE": "99.0", "SUBJECT": "LI", "MEASURE": "AA"},
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), CLI_SPEC, ISO3)
    assert len(out) == 0


def test_cli_alpha2_country_resolved():
    """Some OECD datasets use alpha-2 codes; they should resolve via the fallback map."""
    rows = [
        {"REF_AREA": "US", "TIME_PERIOD": "2021-06", "OBS_VALUE": "101.5", "SUBJECT": "LI", "MEASURE": "AA"},
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), CLI_SPEC, ISO3)
    assert len(out) == 1
    assert out.iloc[0]["country"] == "United States"


# ---- parse_oecd_csv — OE-02 CCI (quarterly -> annual mean) ------------------

CCI_SPEC = f.SPECS["OE-02"]


def test_cci_quarterly_aggregated_to_annual_mean():
    rows = [
        {"REF_AREA": "FRA", "TIME_PERIOD": "2021-Q1", "OBS_VALUE": "95.0", "SUBJECT": "CCSCONF"},
        {"REF_AREA": "FRA", "TIME_PERIOD": "2021-Q2", "OBS_VALUE": "97.0", "SUBJECT": "CCSCONF"},
        {"REF_AREA": "FRA", "TIME_PERIOD": "2021-Q3", "OBS_VALUE": "99.0", "SUBJECT": "CCSCONF"},
        {"REF_AREA": "FRA", "TIME_PERIOD": "2021-Q4", "OBS_VALUE": "101.0", "SUBJECT": "CCSCONF"},
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), CCI_SPEC, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # mean(95,97,99,101) = 98.0
    assert abs(recs[("France", 2021)] - 98.0) < 1e-9


def test_cci_filters_out_wrong_subject():
    """Rows with SUBJECT != CCSCONF must be dropped."""
    rows = [
        {
            "REF_AREA": "USA",
            "TIME_PERIOD": "2021-Q1",
            "OBS_VALUE": "102.0",
            "SUBJECT": "BSCICP02",
        },  # BCI — wrong for CCI spec
        {"REF_AREA": "USA", "TIME_PERIOD": "2021-Q2", "OBS_VALUE": "98.0", "SUBJECT": "CCSCONF"},
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), CCI_SPEC, ISO3)
    recs = out.to_dict("records")
    assert len(recs) == 1
    assert recs[0]["country"] == "United States"
    assert recs[0]["value"] == 98.0


# ---- parse_oecd_csv — OE-03 BCI (quarterly -> annual mean) ------------------

BCI_SPEC = f.SPECS["OE-03"]


def test_bci_quarterly_aggregated_and_filtered():
    rows = [
        {"REF_AREA": "GBR", "TIME_PERIOD": "2020-Q1", "OBS_VALUE": "99.0", "SUBJECT": "BSCICP02"},
        {"REF_AREA": "GBR", "TIME_PERIOD": "2020-Q2", "OBS_VALUE": "91.0", "SUBJECT": "BSCICP02"},
        {"REF_AREA": "GBR", "TIME_PERIOD": "2020-Q3", "OBS_VALUE": "95.0", "SUBJECT": "BSCICP02"},
        {"REF_AREA": "GBR", "TIME_PERIOD": "2020-Q4", "OBS_VALUE": "97.0", "SUBJECT": "BSCICP02"},
        # Different year
        {"REF_AREA": "GBR", "TIME_PERIOD": "2021-Q1", "OBS_VALUE": "103.0", "SUBJECT": "BSCICP02"},
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), BCI_SPEC, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # mean(99, 91, 95, 97) = 95.5
    assert abs(recs[("United Kingdom", 2020)] - 95.5) < 1e-9
    assert abs(recs[("United Kingdom", 2021)] - 103.0) < 1e-9


# ---- parse_oecd_csv — OE-04 SOCX (annual % GDP) ----------------------------

SOCX_SPEC = f.SPECS["OE-04"]


def test_socx_annual_filters_unit_and_expenditure():
    rows = [
        {
            "REF_AREA": "DEU",
            "TIME_PERIOD": "2019",
            "OBS_VALUE": "25.9",
            "UNIT_MEASURE": "PT_B1GQ",
            "EXPENDITURE": "ES10",
        },
        # Wrong unit — should be dropped
        {"REF_AREA": "DEU", "TIME_PERIOD": "2019", "OBS_VALUE": "999.9", "UNIT_MEASURE": "USD", "EXPENDITURE": "ES10"},
        # Wrong expenditure type — should be dropped
        {
            "REF_AREA": "DEU",
            "TIME_PERIOD": "2019",
            "OBS_VALUE": "5.0",
            "UNIT_MEASURE": "PT_B1GQ",
            "EXPENDITURE": "ES20_30",
        },
        {
            "REF_AREA": "JPN",
            "TIME_PERIOD": "2020",
            "OBS_VALUE": "21.5",
            "UNIT_MEASURE": "PT_B1GQ",
            "EXPENDITURE": "ES10",
        },
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), SOCX_SPEC, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert abs(recs[("Germany", 2019)] - 25.9) < 1e-9
    assert abs(recs[("Japan", 2020)] - 21.5) < 1e-9
    assert len(out) == 2


# ---- parse_oecd_csv — OE-05 Gini (annual) -----------------------------------

GINI_SPEC = f.SPECS["OE-05"]


def test_gini_filters_measure_and_age():
    rows = [
        {"REF_AREA": "USA", "TIME_PERIOD": "2018", "OBS_VALUE": "0.390", "MEASURE": "INC_DISP_GINI", "AGE": "_T"},
        # Wrong measure
        {"REF_AREA": "USA", "TIME_PERIOD": "2018", "OBS_VALUE": "0.450", "MEASURE": "INC_MKT_GINI", "AGE": "_T"},
        # Wrong age group
        {"REF_AREA": "USA", "TIME_PERIOD": "2018", "OBS_VALUE": "0.410", "MEASURE": "INC_DISP_GINI", "AGE": "Y18T65"},
        {"REF_AREA": "DEU", "TIME_PERIOD": "2019", "OBS_VALUE": "0.289", "MEASURE": "INC_DISP_GINI", "AGE": "_T"},
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), GINI_SPEC, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert abs(recs[("United States", 2018)] - 0.390) < 1e-9
    assert abs(recs[("Germany", 2019)] - 0.289) < 1e-9
    assert len(out) == 2


# ---- parse_oecd_csv — OE-06 Tax revenue % GDP (annual) ----------------------

TAX_SPEC = f.SPECS["OE-06"]


def test_tax_filters_sector_revenue_and_unit():
    rows = [
        # Correct: total tax, general government, % GDP
        {
            "REF_AREA": "FRA",
            "TIME_PERIOD": "2021",
            "OBS_VALUE": "46.2",
            "STANDARD_REVENUE": "_T",
            "SECTOR": "S13",
            "UNIT_MEASURE": "PT_B1GQ",
        },
        # Wrong sector
        {
            "REF_AREA": "FRA",
            "TIME_PERIOD": "2021",
            "OBS_VALUE": "20.0",
            "STANDARD_REVENUE": "_T",
            "SECTOR": "S1",
            "UNIT_MEASURE": "PT_B1GQ",
        },
        # Wrong unit
        {
            "REF_AREA": "FRA",
            "TIME_PERIOD": "2021",
            "OBS_VALUE": "9999.0",
            "STANDARD_REVENUE": "_T",
            "SECTOR": "S13",
            "UNIT_MEASURE": "USD",
        },
        {
            "REF_AREA": "AUS",
            "TIME_PERIOD": "2020",
            "OBS_VALUE": "29.5",
            "STANDARD_REVENUE": "_T",
            "SECTOR": "S13",
            "UNIT_MEASURE": "PT_B1GQ",
        },
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), TAX_SPEC, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert abs(recs[("France", 2021)] - 46.2) < 1e-9
    assert abs(recs[("Australia", 2020)] - 29.5) < 1e-9
    assert len(out) == 2


# ---- parse_oecd_csv — OE-07 TFP/MFP growth (annual) ------------------------

TFP_SPEC = f.SPECS["OE-07"]


def test_tfp_filters_measure_and_activity():
    rows = [
        {"REF_AREA": "JPN", "TIME_PERIOD": "2019", "OBS_VALUE": "-0.5", "MEASURE": "MFP", "ACTIVITY": "_T"},
        # Wrong measure
        {"REF_AREA": "JPN", "TIME_PERIOD": "2019", "OBS_VALUE": "1.2", "MEASURE": "GDPHRS", "ACTIVITY": "_T"},
        # Wrong activity
        {"REF_AREA": "JPN", "TIME_PERIOD": "2019", "OBS_VALUE": "0.8", "MEASURE": "MFP", "ACTIVITY": "MFG"},
        {"REF_AREA": "USA", "TIME_PERIOD": "2018", "OBS_VALUE": "0.7", "MEASURE": "MFP", "ACTIVITY": "_T"},
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), TFP_SPEC, ISO3)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert abs(recs[("Japan", 2019)] - (-0.5)) < 1e-9
    assert abs(recs[("United States", 2018)] - 0.7) < 1e-9
    assert len(out) == 2


# ---- edge cases across all specs --------------------------------------------


def test_empty_df_returns_empty():
    empty = pd.DataFrame(columns=["REF_AREA", "TIME_PERIOD", "OBS_VALUE", "SUBJECT", "MEASURE"])
    out = f.parse_oecd_csv(empty, CLI_SPEC, ISO3)
    assert list(out.columns) == ["country", "year", "value"]
    assert len(out) == 0


def test_missing_obs_value_dropped():
    """Rows where OBS_VALUE cannot be cast to float are silently skipped."""
    rows = [
        {"REF_AREA": "USA", "TIME_PERIOD": "2022-01", "OBS_VALUE": "N/A", "SUBJECT": "LI", "MEASURE": "AA"},
        {"REF_AREA": "DEU", "TIME_PERIOD": "2022-06", "OBS_VALUE": "100.0", "SUBJECT": "LI", "MEASURE": "AA"},
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), CLI_SPEC, ISO3)
    assert len(out) == 1
    assert out.iloc[0]["country"] == "Germany"


def test_multiple_country_years_deduped_after_mean():
    """After aggregation country-year pairs must be unique (mean collapses them)."""
    rows = [
        {"REF_AREA": "GBR", "TIME_PERIOD": "2023-Q1", "OBS_VALUE": "98.0", "SUBJECT": "CCSCONF"},
        {"REF_AREA": "GBR", "TIME_PERIOD": "2023-Q2", "OBS_VALUE": "100.0", "SUBJECT": "CCSCONF"},
    ]
    out = f.parse_oecd_csv(_make_csv_df(rows), CCI_SPEC, ISO3)
    assert len(out) == 1
    assert abs(out.iloc[0]["value"] - 99.0) < 1e-9


# ---- SPECS catalogue completeness ------------------------------------------


def test_specs_cover_all_seven():
    assert set(f.SPECS) == {"OE-01", "OE-02", "OE-03", "OE-04", "OE-05", "OE-06", "OE-07"}


def test_all_specs_have_required_keys():
    required = {"agency", "dataflow", "params", "freq", "country_col", "value_col", "period_col"}
    for iid, cfg in f.SPECS.items():
        missing = required - set(cfg)
        assert not missing, f"{iid} spec missing keys: {missing}"


def test_fetch_one_rejects_unknown_id():

    with pytest.raises(ValueError):
        f.fetch_one({"id_string": "ZZ-99"})
