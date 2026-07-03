"""Tests for the UNHCR fetcher — spec-driven enrichment stage 2.

Pure logic only — no AWS, no network.  The base's AWS clients are lazy and
the UNHCR/WB HTTP calls are behind helper functions we mock with monkeypatch,
so importing these modules needs neither boto3 nor live credentials.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup (runs from repo root: qgi-pipeline-img-wt/)
# ---------------------------------------------------------------------------

_QGI_PIPELINE = Path(__file__).resolve().parents[3]
_BASE_DIR = _QGI_PIPELINE / "batch" / "_fetcher_base"
_UNHCR_SRC = _QGI_PIPELINE / "batch" / "indicator-fetcher-unhcr" / "src"
for _p in (_BASE_DIR, _UNHCR_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qgi_fetcher_base as base  # noqa: E402
import fetch_unhcr as f  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

ISO3 = {"AFG": "Afghanistan", "SYR": "Syria", "USA": "United States", "TUR": "Turkey", "PAK": "Pakistan"}

SAMPLE_POP_RECORDS = [
    {
        "coo_iso": "AFG",
        "coa_iso": "PAK",
        "year": 2015,
        "refugees": "100",
        "idps": "500",
        "asylum_seekers": "20",
        "stateless": "0",
    },
    {
        "coo_iso": "AFG",
        "coa_iso": "IRN",
        "year": 2015,
        "refugees": "50",
        "idps": "300",
        "asylum_seekers": "10",
        "stateless": "5",
    },
    {
        "coo_iso": "SYR",
        "coa_iso": "TUR",
        "year": 2016,
        "refugees": 200,
        "idps": "0",
        "asylum_seekers": "80",
        "stateless": "0",
    },
    {
        "coo_iso": "ZZZ",
        "coa_iso": "TUR",
        "year": 2016,
        "refugees": 999,
        "idps": "50",
        "asylum_seekers": "5",
        "stateless": "0",
    },  # unknown iso -> dropped
    {
        "coo_iso": "USA",
        "coa_iso": "CAN",
        "year": 2016,
        "refugees": "",
        "idps": "",
        "asylum_seekers": "",
        "stateless": "",
    },  # blanks -> 0
]

SAMPLE_ASYDEC_RECORDS = [
    {"coo_iso": "AFG", "coa_iso": "DEU", "year": 2015, "dec_recognized": "80", "dec_total": "100"},
    {
        "coo_iso": "AFG",
        "coa_iso": "SWE",
        "year": 2015,
        "dec_recognized": "40",
        "dec_total": "50",
    },  # AFG 2015: 120/150 = 80%
    {"coo_iso": "SYR", "coa_iso": "DEU", "year": 2016, "dec_recognized": "900", "dec_total": "1000"},
    {"coo_iso": "SYR", "coa_iso": "AUT", "year": 2016, "dec_recognized": "0", "dec_total": "0"},  # den=0, skip
]

# ---------------------------------------------------------------------------
# Shared base tests (kept from original)
# ---------------------------------------------------------------------------


def test_iso3_map_from_df_uppercases_and_skips_blanks():
    df = pd.DataFrame(
        {
            "iso_alpha3": ["afg", "USA", "", None],
            "qgi_name": ["Afghanistan", "United States", "Nowhere", "AlsoNowhere"],
        }
    )
    m = base.iso3_map_from_df(df)
    assert m == {"AFG": "Afghanistan", "USA": "United States"}


def test_to_canonical_frame_coerces_dedups_sorts_drops_nan():
    df = pd.DataFrame(
        {
            "country": ["B", "A", "A", "A"],
            "year": ["2001", 2000, 2000, 2002],
            "value": [1.0, 5.0, 9.0, np.nan],
            "extra": [1, 2, 3, 4],
        }
    )
    out = base.to_canonical_frame(df)
    assert list(out.columns) == base.OUTPUT_COLUMNS
    assert out["year"].dtype == np.int64 and out["value"].dtype == np.float64
    assert (out["is_predicted"] == False).all()  # noqa: E712
    assert out.to_dict("records") == [
        {"country": "A", "year": 2000, "value": 9.0, "is_predicted": False},
        {"country": "B", "year": 2001, "value": 1.0, "is_predicted": False},
    ]


def test_to_canonical_frame_requires_core_columns():
    with pytest.raises(ValueError):
        base.to_canonical_frame(pd.DataFrame({"country": ["A"], "year": [2000]}))


# ---------------------------------------------------------------------------
# specs.json load
# ---------------------------------------------------------------------------


def test_specs_json_loaded_and_has_all_codes():
    """All expected codes are present in the baked specs.json."""
    expected = {
        # legacy seed codes
        "UN-01",
        "UN-02",
        "UN-03",
        "UN-04",
        "UN-05",
        "UN-06",
        # enrichment codes
        "UNHCR_IDP",
        "UNHCR_IDP_CHANGE_RATE",
        "UNHCR_REF_COO",
        "UNHCR_REF_COA",
        "UNHCR_FORCDISP_TOTAL",
        "UNHCR_STA",
        "UNHCR_ASYAPP_NEW_COO",
        "UNHCR_RECOG_RATE",
        "UNHCR_ASY_BACKLOG_YEARS",
        "UNHCR_REF_RATIO_POP",
        "UNHCR_IDP_RATIO_POP",
    }
    assert expected.issubset(set(f.SPECS.keys()))


def test_specs_json_all_have_required_keys():
    """Every spec entry has the minimum required keys."""
    required = {"code", "transform", "is_derived"}
    for code, spec in f.SPECS.items():
        missing = required - set(spec.keys())
        assert not missing, f"Spec {code} missing keys: {missing}"


# ---------------------------------------------------------------------------
# parse_unhcr_records — sum transform
# ---------------------------------------------------------------------------


def test_parse_sum_aggregates_by_country_year_and_maps_iso3():
    out = f.parse_unhcr_records(SAMPLE_POP_RECORDS, "refugees", "coo_iso", ISO3, transform="sum")
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # AFG 2015: 100 + 50 = 150
    assert recs[("Afghanistan", 2015)] == 150.0
    # SYR 2016: 200
    assert recs[("Syria", 2016)] == 200.0
    # USA 2016: blank -> 0
    assert recs[("United States", 2016)] == 0.0
    # ZZZ is unknown -> not in output
    assert all(c != "ZZZ" for c, _ in recs)


def test_parse_sum_empty_when_nothing_resolves():
    out = f.parse_unhcr_records(
        [{"coo_iso": "ZZZ", "year": 2015, "refugees": 5}],
        "refugees",
        "coo_iso",
        ISO3,
        transform="sum",
    )
    assert list(out.columns) == ["country", "year", "value"]
    assert len(out) == 0


def test_parse_coa_field():
    """country_field=coa_iso groups by asylum country, not origin.

    The ZZZ row has coa_iso=TUR (Turkey) — the ORIGIN (coo_iso=ZZZ) is unknown,
    but Turkey as asylum country resolves fine, so the row is KEPT when grouping
    by coa_iso.  Turkey 2016 = refugees from SYR (200) + refugees from ZZZ (999)
    = 1199.  The ZZZ filter only drops rows whose country_field is unresolvable.
    """
    out = f.parse_unhcr_records(SAMPLE_POP_RECORDS, "refugees", "coa_iso", ISO3, transform="sum")
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # PAK hosts 100 from AFG 2015
    assert recs.get(("Pakistan", 2015), 0.0) == 100.0
    # Turkey hosts 200 from SYR 2016 + 999 from ZZZ origin (coo_iso=ZZZ unresolvable
    # but coa_iso=TUR resolves, so row contributes to Turkey's total) = 1199
    assert recs.get(("Turkey", 2016), 0.0) == 1199.0


# ---------------------------------------------------------------------------
# parse_unhcr_records — sum_fields transform (UNHCR_FORCDISP_TOTAL)
# ---------------------------------------------------------------------------


def test_parse_sum_fields_forcdisp_total():
    """UNHCR_FORCDISP_TOTAL = refugees + asylum_seekers + idps by coa_iso.

    The ZZZ-origin row has coa_iso=TUR (Turkey), so it contributes to Turkey
    even though the origin country is unresolvable — the filter is on coa_iso.
    Turkey 2016: SYR row (200+80+0=280) + ZZZ row (999+5+50=1054) = 1334.
    """
    out = f.parse_unhcr_records(
        SAMPLE_POP_RECORDS,
        ["refugees", "asylum_seekers", "idps"],
        "coa_iso",
        ISO3,
        transform="sum_fields",
    )
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # PAK 2015: refugees=100, asylum_seekers=20, idps=500 => 620
    assert recs.get(("Pakistan", 2015), 0.0) == 620.0
    # Turkey 2016: includes ZZZ-origin rows (coa_iso=TUR resolves) — total = 1334
    assert recs.get(("Turkey", 2016), 0.0) == 1334.0


def test_parse_sum_fields_blanks_treated_as_zero():
    """Blank/None/'-' values in any summed field count as 0."""
    records = [{"coa_iso": "AFG", "year": 2020, "refugees": "-", "asylum_seekers": None, "idps": "300"}]
    out = f.parse_unhcr_records(
        records, ["refugees", "asylum_seekers", "idps"], "coa_iso", ISO3, transform="sum_fields"
    )
    assert out.iloc[0]["value"] == 300.0


# ---------------------------------------------------------------------------
# parse_unhcr_records — ratio_pct transform (UNHCR_RECOG_RATE)
# ---------------------------------------------------------------------------


def test_parse_ratio_pct_recognition_rate():
    """UNHCR_RECOG_RATE: sum numerators, sum denominators, then divide."""
    out = f.parse_unhcr_records(
        SAMPLE_ASYDEC_RECORDS,
        ["dec_recognized", "dec_total"],
        "coo_iso",
        ISO3,
        transform="ratio_pct",
    )
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # AFG 2015: (80+40)/(100+50)*100 = 120/150*100 = 80.0
    assert abs(recs[("Afghanistan", 2015)] - 80.0) < 1e-9
    # SYR 2016: 900/1000*100 = 90.0 (the den=0 row is excluded in groupby)
    assert abs(recs[("Syria", 2016)] - 90.0) < 1e-9


def test_parse_ratio_pct_skips_zero_denominator():
    """Rows where dec_total aggregates to 0 are excluded."""
    records = [{"coo_iso": "USA", "coa_iso": "CAN", "year": 2020, "dec_recognized": "5", "dec_total": "0"}]
    out = f.parse_unhcr_records(records, ["dec_recognized", "dec_total"], "coo_iso", ISO3, transform="ratio_pct")
    assert out.empty


# ---------------------------------------------------------------------------
# apply_annual_change_rate (UNHCR_IDP_CHANGE_RATE)
# ---------------------------------------------------------------------------


def test_apply_annual_change_rate_basic():
    """YoY % change: first year NaN, subsequent years computed correctly."""
    df = pd.DataFrame(
        {
            "country": ["Afghanistan"] * 4,
            "year": [2010, 2011, 2012, 2013],
            "value": [1000.0, 1200.0, 1200.0, 600.0],
        }
    )
    out = f.apply_annual_change_rate(df)
    recs = {r["year"]: r["value"] for r in out.to_dict("records")}
    # 2010 -> NaN (no prior), not in output
    assert 2010 not in recs
    # 2011: (1200-1000)/1000*100 = 20.0
    assert abs(recs[2011] - 20.0) < 1e-9
    # 2012: (1200-1200)/1200*100 = 0.0
    assert abs(recs[2012] - 0.0) < 1e-9
    # 2013: (600-1200)/1200*100 = -50.0
    assert abs(recs[2013] - (-50.0)) < 1e-9


def test_apply_annual_change_rate_zero_denominator_excluded():
    """If prior year value is 0, pct change is NaN -> excluded from output."""
    df = pd.DataFrame(
        {
            "country": ["Syria", "Syria"],
            "year": [2010, 2011],
            "value": [0.0, 500.0],
        }
    )
    out = f.apply_annual_change_rate(df)
    assert out.empty  # 2010=first year; 2011 has prev=0, skipped


def test_apply_annual_change_rate_multiple_countries():
    """Change rate is computed per country independently."""
    df = pd.DataFrame(
        {
            "country": ["Afghanistan", "Afghanistan", "Syria", "Syria"],
            "year": [2010, 2011, 2010, 2011],
            "value": [1000.0, 2000.0, 500.0, 250.0],
        }
    )
    out = f.apply_annual_change_rate(df)
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert abs(recs[("Afghanistan", 2011)] - 100.0) < 1e-9
    assert abs(recs[("Syria", 2011)] - (-50.0)) < 1e-9


# ---------------------------------------------------------------------------
# apply_wb_pop_ratio (UNHCR_REF_RATIO_POP, UNHCR_IDP_RATIO_POP)
# ---------------------------------------------------------------------------


def test_apply_wb_pop_ratio_basic():
    df_num = pd.DataFrame(
        {
            "country": ["Afghanistan", "Syria"],
            "year": [2015, 2016],
            "value": [300000.0, 5000000.0],
        }
    )
    wb_pop = pd.DataFrame(
        {
            "iso3": ["AFG", "SYR"],
            "year": [2015, 2016],
            "population": [30000000.0, 18000000.0],
        }
    )
    out = f.apply_wb_pop_ratio(df_num, wb_pop, ISO3)
    recs = {r["country"]: r["value"] for r in out.to_dict("records")}
    # 300000 / 30000000 * 100 = 1.0
    assert abs(recs["Afghanistan"] - 1.0) < 1e-9
    # 5000000 / 18000000 * 100 ~= 27.78
    assert abs(recs["Syria"] - (5_000_000 / 18_000_000 * 100)) < 1e-6


def test_apply_wb_pop_ratio_missing_pop_dropped():
    """Country-years without WB population are dropped (inner join)."""
    df_num = pd.DataFrame(
        {
            "country": ["Afghanistan", "Unknown"],
            "year": [2015, 2015],
            "value": [300000.0, 100.0],
        }
    )
    wb_pop = pd.DataFrame(
        {
            "iso3": ["AFG"],
            "year": [2015],
            "population": [30000000.0],
        }
    )
    out = f.apply_wb_pop_ratio(df_num, wb_pop, ISO3)
    assert len(out) == 1
    assert out.iloc[0]["country"] == "Afghanistan"


# ---------------------------------------------------------------------------
# fetch_one — spec lookup errors
# ---------------------------------------------------------------------------


def test_fetch_one_rejects_unknown_id():
    with pytest.raises(ValueError, match="unknown UNHCR indicator"):
        f.fetch_one({"id_string": "ZZ-99"})


# ---------------------------------------------------------------------------
# fetch_one — spec-driven path with mocked HTTP (new codes)
# ---------------------------------------------------------------------------


def test_fetch_one_unhcr_idp_mocks_network():
    """UNHCR_IDP: fetch_unhcr_raw mocked; parse + return correct frame."""
    mock_records = [
        {
            "coo_iso": "AFG",
            "coa_iso": "AFG",
            "year": 2020,
            "idps": "1000000",
            "refugees": "0",
            "asylum_seekers": "0",
            "stateless": "0",
        },
        {
            "coo_iso": "SYR",
            "coa_iso": "SYR",
            "year": 2020,
            "idps": "6000000",
            "refugees": "0",
            "asylum_seekers": "0",
            "stateless": "0",
        },
    ]
    iso3_map = {"AFG": "Afghanistan", "SYR": "Syria"}

    with (
        patch.object(f, "fetch_unhcr_raw", return_value=mock_records),
        patch.object(base, "load_iso3_country_map", return_value=iso3_map),
    ):
        result = f.fetch_one({"id_string": "UNHCR_IDP"})

    assert result is not None
    recs = {r["country"]: r["value"] for r in result.to_dict("records")}
    assert recs["Afghanistan"] == 1_000_000.0
    assert recs["Syria"] == 6_000_000.0


def test_fetch_one_unhcr_idp_change_rate_mocks_network():
    """UNHCR_IDP_CHANGE_RATE: derives YoY change from the same raw pull."""
    mock_records = [
        {"coo_iso": "AFG", "coa_iso": "AFG", "year": 2019, "idps": "1000000"},
        {"coo_iso": "AFG", "coa_iso": "AFG", "year": 2020, "idps": "1500000"},
    ]
    iso3_map = {"AFG": "Afghanistan"}

    with (
        patch.object(f, "fetch_unhcr_raw", return_value=mock_records),
        patch.object(base, "load_iso3_country_map", return_value=iso3_map),
    ):
        result = f.fetch_one({"id_string": "UNHCR_IDP_CHANGE_RATE"})

    assert result is not None
    recs = {r["year"]: r["value"] for r in result.to_dict("records")}
    # Only 2020 should be present: (1.5M - 1M) / 1M * 100 = 50%
    assert 2019 not in recs  # first year -> no prior
    assert abs(recs[2020] - 50.0) < 1e-9


def test_fetch_one_unhcr_forcdisp_total_mocks_network():
    """UNHCR_FORCDISP_TOTAL: refugees + asylum_seekers + idps summed."""
    mock_records = [
        {
            "coo_iso": "SYR",
            "coa_iso": "SYR",
            "year": 2020,
            "refugees": "1000",
            "asylum_seekers": "200",
            "idps": "5000",
            "stateless": "0",
        },
    ]
    iso3_map = {"SYR": "Syria"}

    with (
        patch.object(f, "fetch_unhcr_raw", return_value=mock_records),
        patch.object(base, "load_iso3_country_map", return_value=iso3_map),
    ):
        result = f.fetch_one({"id_string": "UNHCR_FORCDISP_TOTAL"})

    assert result is not None
    assert result.iloc[0]["value"] == 6200.0


def test_fetch_one_unhcr_recog_rate_mocks_network():
    """UNHCR_RECOG_RATE: ratio_pct transform via asylum-decisions endpoint."""
    mock_records = [
        {"coo_iso": "AFG", "coa_iso": "DEU", "year": 2019, "dec_recognized": "800", "dec_total": "1000"},
        {"coo_iso": "AFG", "coa_iso": "SWE", "year": 2019, "dec_recognized": "100", "dec_total": "200"},
    ]
    iso3_map = {"AFG": "Afghanistan"}

    with (
        patch.object(f, "fetch_unhcr_raw", return_value=mock_records),
        patch.object(base, "load_iso3_country_map", return_value=iso3_map),
    ):
        result = f.fetch_one({"id_string": "UNHCR_RECOG_RATE"})

    assert result is not None
    # (800+100)/(1000+200)*100 = 900/1200*100 = 75.0
    assert abs(result.iloc[0]["value"] - 75.0) < 1e-9


def test_fetch_one_unhcr_ref_ratio_pop_mocks_network():
    """UNHCR_REF_RATIO_POP: UNHCR numerator / WB population * 100."""
    mock_records = [
        {"coo_iso": "AFG", "coa_iso": "PAK", "year": 2020, "refugees": "2000000"},
    ]
    iso3_map = {"AFG": "Afghanistan"}
    mock_wb_pop = pd.DataFrame(
        {
            "iso3": ["AFG"],
            "year": [2020],
            "population": [40_000_000.0],
        }
    )

    with (
        patch.object(f, "fetch_unhcr_raw", return_value=mock_records),
        patch.object(base, "load_iso3_country_map", return_value=iso3_map),
        patch.object(f, "fetch_wb_population_all", return_value=mock_wb_pop),
    ):
        result = f.fetch_one({"id_string": "UNHCR_REF_RATIO_POP"})

    assert result is not None
    # 2_000_000 / 40_000_000 * 100 = 5.0%
    assert abs(result.iloc[0]["value"] - 5.0) < 1e-9


def test_fetch_one_unhcr_asy_backlog_years_mocks_network():
    """UNHCR_ASY_BACKLOG_YEARS: cross_endpoint_ratio — two separate endpoint fetches."""
    mock_pop_records = [
        {"coo_iso": "AFG", "coa_iso": "DEU", "year": 2020, "asylum_seekers": "60000"},
    ]
    mock_dec_records = [
        {"coo_iso": "AFG", "coa_iso": "DEU", "year": 2020, "dec_total": "20000"},
    ]
    iso3_map = {"AFG": "Afghanistan", "DEU": "Germany"}

    def _mock_fetch_raw(endpoint, filter_params=None):
        if endpoint == "population":
            return mock_pop_records
        if endpoint == "asylum-decisions":
            return mock_dec_records
        return []

    with (
        patch.object(f, "fetch_unhcr_raw", side_effect=_mock_fetch_raw),
        patch.object(base, "load_iso3_country_map", return_value=iso3_map),
    ):
        result = f.fetch_one({"id_string": "UNHCR_ASY_BACKLOG_YEARS"})

    assert result is not None
    # 60000 / 20000 = 3.0 years
    assert abs(result.iloc[0]["value"] - 3.0) < 1e-9


# ---------------------------------------------------------------------------
# Legacy seed codes (UN-01..UN-06) still work via new spec path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,vfield,cfield",
    [
        ("UN-01", "refugees", "coo_iso"),
        ("UN-02", "refugees", "coa_iso"),
        ("UN-04", "idps", "coa_iso"),
        ("UN-06", "stateless", "coa_iso"),
    ],
)
def test_legacy_population_codes_work(code, vfield, cfield):
    """Legacy UN-0x codes resolve via specs.json and parse correctly."""
    mock_records = [
        {
            "coo_iso": "AFG",
            "coa_iso": "PAK",
            "year": 2010,
            "refugees": "500",
            "idps": "200",
            "stateless": "50",
            "asylum_seekers": "30",
        },
    ]
    iso3_map = {"AFG": "Afghanistan", "PAK": "Pakistan"}

    with (
        patch.object(f, "fetch_unhcr_raw", return_value=mock_records),
        patch.object(base, "load_iso3_country_map", return_value=iso3_map),
    ):
        result = f.fetch_one({"id_string": code})

    assert result is not None and not result.empty


def test_legacy_un03_asylum_applications():
    """UN-03 uses asylum-applications endpoint."""
    mock_records = [
        {"coo_iso": "SYR", "coa_iso": "DEU", "year": 2015, "applied": "100000"},
    ]
    iso3_map = {"SYR": "Syria", "DEU": "Germany"}

    with (
        patch.object(f, "fetch_unhcr_raw", return_value=mock_records),
        patch.object(base, "load_iso3_country_map", return_value=iso3_map),
    ):
        result = f.fetch_one({"id_string": "UN-03"})

    assert result is not None
    assert result.iloc[0]["value"] == 100_000.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_fetch_one_returns_none_when_empty_records():
    """If API returns no parseable rows, fetch_one returns None (not empty DF)."""
    with (
        patch.object(f, "fetch_unhcr_raw", return_value=[]),
        patch.object(base, "load_iso3_country_map", return_value={}),
    ):
        result = f.fetch_one({"id_string": "UNHCR_REF_COO"})

    assert result is None


def test_safe_float_handles_sentinel_values():
    """_safe_float converts blanks and dashes to 0.0."""
    assert f._safe_float(None) == 0.0
    assert f._safe_float("") == 0.0
    assert f._safe_float("-") == 0.0
    assert f._safe_float("N/A") == 0.0
    assert f._safe_float("1234.5") == 1234.5
    assert f._safe_float(500) == 500.0
