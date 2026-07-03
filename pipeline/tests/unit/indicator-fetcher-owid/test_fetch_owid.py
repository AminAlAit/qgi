"""Tests for the OWID fetcher transform + shared fetcher base (enrichment stage 2).

Pure logic only — no AWS, no network (the base's AWS clients are lazy and the
requests import is lazy, so importing these modules needs neither).

Covers:
  - base.iso3_map_from_df  (shared, same smoke as UNHCR suite)
  - base.to_canonical_frame (shared)
  - parse_owid_records — OW-01 Polity path (Code / Year / Democracy)
  - parse_owid_records — OW-04 CO2 growth rate path (iso_code / year / co2_growth_prct)
  - parse_owid_records — OW-04 fallback: derive YoY % change from co2 level column
  - aggregate / continent rows dropped (empty Code and OWID_ prefix)
  - unknown ISO-3 codes dropped
  - SPECS dictionary now spec-driven (all codes from specs.json)

  NEW (spec-driven path):
  - OWID_REGIMETYPE — V-Dem RoW 4-category regime type (direct value)
  - OWID_AUTOCRATIZATION — V-Dem ERT binary flag (country_text_id country column)
  - OWID_POP_YOUNG — youth share derived from age-group columns (is_derived=true)
  - OWID_SLUM_SHARE — % urban population in slums (direct value)
  - OWID_STATECAP — Hanson & Sigman state capacity index (direct value)
  - _apply_derivation — ages_15_24_share path
  - _apply_derivation — unknown derivation raises ValueError
  - fetch_one rejects unknown indicator code
  - specs.json integrity — all expected codes present, key schema correct
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path wiring — mirrors test_fetch_unhcr.py exactly
# ---------------------------------------------------------------------------
_QGI_PIPELINE = Path(__file__).resolve().parents[3]
_BASE_DIR = _QGI_PIPELINE / "batch" / "_fetcher_base"
_OWID_SRC = _QGI_PIPELINE / "batch" / "indicator-fetcher-owid" / "src"
for _p in (_BASE_DIR, _OWID_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qgi_fetcher_base as base  # noqa: E402
import fetch_owid as f  # noqa: E402

# ---------------------------------------------------------------------------
# Shared ISO-3 map used across tests
# ---------------------------------------------------------------------------
ISO3: dict[str, str] = {
    "AFG": "Afghanistan",
    "CHN": "China",
    "BRA": "Brazil",
    "DEU": "Germany",
    "USA": "United States",
    "GBR": "United Kingdom",
    "KEN": "Kenya",
}

# ---------------------------------------------------------------------------
# Shared base smoke-tests (same intent as UNHCR suite — confirm imports work)
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
    assert out["year"].dtype == np.int64
    assert out["value"].dtype == np.float64
    assert (out["is_predicted"] == False).all()  # noqa: E712
    assert out.to_dict("records") == [
        {"country": "A", "year": 2000, "value": 9.0, "is_predicted": False},
        {"country": "B", "year": 2001, "value": 1.0, "is_predicted": False},
    ]


def test_to_canonical_frame_requires_core_columns():
    with pytest.raises(ValueError):
        base.to_canonical_frame(pd.DataFrame({"country": ["A"], "year": [2000]}))


# ---------------------------------------------------------------------------
# OW-01: Polity V score  (Entity / Code / Year / Democracy columns)
# ---------------------------------------------------------------------------


def _polity_df() -> pd.DataFrame:
    """Synthetic representative payload matching OWID Polity grapher CSV format."""
    return pd.DataFrame(
        {
            "Entity": [
                "Afghanistan",
                "Afghanistan",
                "China",
                "Brazil",
                "Africa (population-weighted)",  # aggregate — no Code
                "Asia",  # aggregate — OWID_ code
                "Germany",
                "Germany",
            ],
            "Code": [
                "AFG",
                "AFG",
                "CHN",
                "BRA",
                "",  # empty code -> drop
                "OWID_ASI",  # OWID_ prefix -> drop
                "DEU",
                "DEU",
            ],
            "Year": [2015, 2016, 2015, 2015, 2015, 2015, 2017, 2018],
            "Democracy": [-1, -1, -7, 8, -6, -7, 10, 10],
        }
    )


def test_parse_owid_polity_maps_iso3_and_drops_aggregates():
    out = f.parse_owid_records(
        raw_df=_polity_df(),
        value_col="Democracy",
        iso3_map=ISO3,
        code_col="Code",
        year_col="Year",
    )
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # known-good rows
    assert recs[("Afghanistan", 2015)] == -1.0
    assert recs[("Afghanistan", 2016)] == -1.0
    assert recs[("China", 2015)] == -7.0
    assert recs[("Brazil", 2015)] == 8.0
    assert recs[("Germany", 2017)] == 10.0
    assert recs[("Germany", 2018)] == 10.0
    # aggregates must be absent
    countries = {c for c, _ in recs}
    assert "Africa (population-weighted)" not in countries
    assert "Asia" not in countries


def test_parse_owid_polity_drops_unknown_iso3():
    df = pd.DataFrame(
        {
            "Entity": ["Ruritania"],
            "Code": ["RUR"],  # not in ISO3 map
            "Year": [2010],
            "Democracy": [5],
        }
    )
    out = f.parse_owid_records(df, "Democracy", ISO3, code_col="Code", year_col="Year")
    assert len(out) == 0
    assert list(out.columns) == ["country", "year", "value"]


def test_parse_owid_polity_returns_empty_when_all_aggregates():
    df = pd.DataFrame(
        {
            "Entity": ["World", "Asia"],
            "Code": ["OWID_WRL", "OWID_ASI"],
            "Year": [2010, 2010],
            "Democracy": [-3, -4],
        }
    )
    out = f.parse_owid_records(df, "Democracy", ISO3, code_col="Code", year_col="Year")
    assert len(out) == 0


def test_parse_owid_polity_aggregates_duplicate_country_year_by_mean():
    """If a country-year appears twice (shouldn't in Polity but defensive), mean is taken."""
    df = pd.DataFrame(
        {
            "Entity": ["Afghanistan", "Afghanistan"],
            "Code": ["AFG", "AFG"],
            "Year": [2010, 2010],
            "Democracy": [2.0, 4.0],
        }
    )
    out = f.parse_owid_records(df, "Democracy", ISO3, code_col="Code", year_col="Year")
    assert len(out) == 1
    assert out.iloc[0]["value"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# OW-04: CO2 growth rate  (country / iso_code / year / co2_growth_prct columns)
# ---------------------------------------------------------------------------


def _co2_df(include_growth_prct: bool = True) -> pd.DataFrame:
    """Synthetic representative payload matching owid-co2-data.csv format."""
    base_data: dict = {
        "country": ["Afghanistan", "China", "Brazil", "Germany", "World", "Asia"],
        "iso_code": ["AFG", "CHN", "BRA", "DEU", "", "OWID_ASI"],
        "year": [2020, 2020, 2020, 2020, 2020, 2020],
        "co2": [10.0, 11000.0, 500.0, 700.0, 37000.0, 15000.0],
        "co2_per_capita": [0.25, 7.7, 2.3, 8.4, 4.7, 3.9],
    }
    if include_growth_prct:
        base_data["co2_growth_prct"] = [3.5, 1.5, -2.0, -5.0, 1.0, 0.5]
    return pd.DataFrame(base_data)


def test_parse_owid_co2_growth_prct_primary_path():
    out = f.parse_owid_records(
        raw_df=_co2_df(include_growth_prct=True),
        value_col="co2_growth_prct",
        iso3_map=ISO3,
        code_col="iso_code",
        year_col="year",
    )
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    assert recs[("Afghanistan", 2020)] == pytest.approx(3.5)
    assert recs[("China", 2020)] == pytest.approx(1.5)
    assert recs[("Brazil", 2020)] == pytest.approx(-2.0)
    assert recs[("Germany", 2020)] == pytest.approx(-5.0)
    # aggregates must be absent
    countries = {c for c, _ in recs}
    assert "World" not in countries
    assert "Asia" not in countries


def test_parse_owid_co2_drops_empty_and_owid_codes():
    out = f.parse_owid_records(
        raw_df=_co2_df(include_growth_prct=True),
        value_col="co2_growth_prct",
        iso3_map=ISO3,
        code_col="iso_code",
        year_col="year",
    )
    # Only 4 real countries in ISO3 map; World (empty code) + Asia (OWID_) dropped
    assert len(out) == 4


def test_parse_owid_co2_fallback_yoy_pct_change_from_level():
    """When co2_growth_prct is absent, derive from the co2 level column."""
    # Build 3-year series for 2 countries (no growth_prct column)
    df = pd.DataFrame(
        {
            "country": ["Afghanistan"] * 3 + ["China"] * 3,
            "iso_code": ["AFG"] * 3 + ["CHN"] * 3,
            "year": [2018, 2019, 2020] * 2,
            "co2": [
                100.0,
                110.0,
                121.0,  # AFG: +10%, +10%
                1000.0,
                950.0,
                902.5,
            ],  # CHN: -5%, -5%
            "co2_per_capita": [0.25] * 6,
        }
    )
    # Note: no co2_growth_prct column
    out = f.parse_owid_records(
        raw_df=df,
        value_col="co2_growth_prct",
        iso3_map=ISO3,
        code_col="iso_code",
        year_col="year",
        fallback_level_col="co2",
    )
    recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
    # Year 2018 (first in each group) -> NaN pct_change -> dropped by to_canonical_frame / parse
    assert (2018) not in [yr for _, yr in recs]
    # AFG 2019: (110-100)/100 * 100 = 10%
    assert recs[("Afghanistan", 2019)] == pytest.approx(10.0, rel=1e-5)
    # AFG 2020: (121-110)/110 * 100 ≈ 10%
    assert recs[("Afghanistan", 2020)] == pytest.approx(10.0, rel=1e-5)
    # CHN 2019: (950-1000)/1000 * 100 = -5%
    assert recs[("China", 2019)] == pytest.approx(-5.0, rel=1e-5)
    # CHN 2020: (902.5-950)/950 * 100 = -5%
    assert recs[("China", 2020)] == pytest.approx(-5.0, rel=1e-5)


def test_parse_owid_co2_nan_growth_prct_rows_dropped():
    """Rows with NaN co2_growth_prct are silently dropped (not treated as 0)."""
    df = pd.DataFrame(
        {
            "country": ["Afghanistan", "Afghanistan"],
            "iso_code": ["AFG", "AFG"],
            "year": [1960, 2020],  # 1960 has no GCP data -> NaN growth_prct
            "co2_growth_prct": [np.nan, 3.5],
        }
    )
    out = f.parse_owid_records(
        raw_df=df,
        value_col="co2_growth_prct",
        iso3_map=ISO3,
        code_col="iso_code",
        year_col="year",
    )
    assert len(out) == 1
    assert out.iloc[0]["year"] == 2020
    assert out.iloc[0]["value"] == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# OWID_REGIMETYPE: V-Dem RoW regime type (new spec-driven code)
# ---------------------------------------------------------------------------


def _regime_type_df() -> pd.DataFrame:
    """Synthetic OWID political-regime.csv payload."""
    return pd.DataFrame(
        {
            "Entity": ["Afghanistan", "China", "Brazil", "Germany", "World"],
            "Code": ["AFG", "CHN", "BRA", "DEU", "OWID_WRL"],
            "Year": [2022, 2022, 2022, 2022, 2022],
            "Political regime": [0, 0, 2, 3, np.nan],
        }
    )


def test_parse_owid_regime_type_direct_value():
    """OWID_REGIMETYPE: regime integer extracted and OWID_ aggregate dropped."""
    out = f.parse_owid_records(
        raw_df=_regime_type_df(),
        value_col="Political regime",
        iso3_map=ISO3,
        code_col="Code",
        year_col="Year",
    )
    recs = {r["country"]: r["value"] for r in out.to_dict("records")}
    assert recs["Afghanistan"] == pytest.approx(0.0)  # closed autocracy
    assert recs["China"] == pytest.approx(0.0)  # closed autocracy
    assert recs["Brazil"] == pytest.approx(2.0)  # electoral democracy
    assert recs["Germany"] == pytest.approx(3.0)  # liberal democracy
    assert "World" not in recs  # OWID_ aggregate dropped


def test_parse_owid_regime_type_nan_world_row_drops():
    """World row has NaN regime value — must be dropped regardless of NaN drop or OWID_ rule."""
    df = pd.DataFrame(
        {
            "Entity": ["World"],
            "Code": ["OWID_WRL"],
            "Year": [2022],
            "Political regime": [np.nan],
        }
    )
    out = f.parse_owid_records(df, "Political regime", ISO3, code_col="Code", year_col="Year")
    assert len(out) == 0


# ---------------------------------------------------------------------------
# OWID_AUTOCRATIZATION: V-Dem ERT binary flag (non-standard country_text_id col)
# ---------------------------------------------------------------------------


def _ert_df() -> pd.DataFrame:
    """Synthetic ERT CSV payload (country_text_id column, not 'Code')."""
    return pd.DataFrame(
        {
            "country_text_id": ["AFG", "BRA", "CHN", "DEU", "GBR", ""],
            "year": [2020, 2020, 2020, 2020, 2020, 2020],
            "aut_ep": [1, 0, 1, 0, 0, 0],
            "other_col": [1, 2, 3, 4, 5, 6],
        }
    )


def test_parse_owid_autocratization_uses_country_text_id():
    """OWID_AUTOCRATIZATION uses country_text_id as the ISO-3 column."""
    out = f.parse_owid_records(
        raw_df=_ert_df(),
        value_col="aut_ep",
        iso3_map=ISO3,
        code_col="country_text_id",
        year_col="year",
    )
    recs = {r["country"]: r["value"] for r in out.to_dict("records")}
    assert recs["Afghanistan"] == pytest.approx(1.0)  # in autocratization episode
    assert recs["Brazil"] == pytest.approx(0.0)  # not in episode
    assert recs["China"] == pytest.approx(1.0)
    assert recs["Germany"] == pytest.approx(0.0)
    assert recs["United Kingdom"] == pytest.approx(0.0)
    # empty code row must be dropped
    assert len(recs) == 5


def test_parse_owid_autocratization_drops_empty_code():
    """Empty country_text_id rows (aggregates or unmatched) are dropped."""
    df = pd.DataFrame(
        {
            "country_text_id": ["", "AFG"],
            "year": [2020, 2020],
            "aut_ep": [1, 0],
        }
    )
    out = f.parse_owid_records(
        raw_df=df,
        value_col="aut_ep",
        iso3_map=ISO3,
        code_col="country_text_id",
        year_col="year",
    )
    assert len(out) == 1
    assert out.iloc[0]["country"] == "Afghanistan"


# ---------------------------------------------------------------------------
# OWID_POP_YOUNG: derived — youth-bulge share (is_derived=true)
# ---------------------------------------------------------------------------


def _pop_age_df() -> pd.DataFrame:
    """Synthetic OWID population-by-age-group.csv payload."""
    return pd.DataFrame(
        {
            "Entity": ["Afghanistan", "China", "Brazil", "World"],
            "Code": ["AFG", "CHN", "BRA", "OWID_WRL"],
            "Year": [2020, 2020, 2020, 2020],
            # Absolute counts (thousands)
            "Under-5s": [5_000, 80_000, 15_000, 600_000],
            "Ages 5-14": [8_000, 130_000, 25_000, 900_000],
            "Ages 15-24": [6_000, 170_000, 30_000, 1_200_000],
            "Ages 25-64": [15_000, 800_000, 90_000, 4_000_000],
            "Ages 65+": [2_000, 180_000, 20_000, 700_000],
        }
    )


def _pop_young_spec() -> dict:
    """Minimal spec dict for OWID_POP_YOUNG derivation."""
    return {
        "code": "OWID_POP_YOUNG",
        "is_derived": True,
        "derivation": "ages_15_24_share: value=(Ages 15-24)/(Under-5s+Ages 5-14+Ages 15-24+Ages 25-64+Ages 65+)*100",
    }


def test_apply_derivation_ages_15_24_share_correct_ratio():
    """_apply_derivation computes youth share = Ages15-24 / total_pop * 100."""
    df = _pop_age_df().copy()
    # Exclude OWID_ aggregate row for pure derivation test
    df = df[df["Code"] != "OWID_WRL"].reset_index(drop=True)
    result = f._apply_derivation(df, _pop_young_spec())
    assert "_derived_value" in result.columns
    # AFG: 6000 / (5000+8000+6000+15000+2000) = 6000/36000 ≈ 16.67%
    afg_row = result[result["Code"] == "AFG"].iloc[0]
    expected_afg = 6_000 / (5_000 + 8_000 + 6_000 + 15_000 + 2_000) * 100
    assert afg_row["_derived_value"] == pytest.approx(expected_afg, rel=1e-5)
    # CHN: 170000 / (80000+130000+170000+800000+180000) = 170000/1360000 ≈ 12.5%
    chn_row = result[result["Code"] == "CHN"].iloc[0]
    expected_chn = 170_000 / (80_000 + 130_000 + 170_000 + 800_000 + 180_000) * 100
    assert chn_row["_derived_value"] == pytest.approx(expected_chn, rel=1e-5)


def test_parse_owid_pop_young_end_to_end():
    """parse_owid_records with is_derived=True drops OWID_ aggregates and returns share."""
    spec = _pop_young_spec()
    out = f.parse_owid_records(
        raw_df=_pop_age_df(),
        value_col="Ages 15-24",  # value_col ignored for derived; derivation drives
        iso3_map=ISO3,
        code_col="Code",
        year_col="Year",
        derivation=spec["derivation"],
        spec=spec,
    )
    recs = {r["country"]: r["value"] for r in out.to_dict("records")}
    # OWID_WRL aggregate must be dropped
    assert "World" not in recs
    # AFG share sanity check
    expected_afg = 6_000 / (5_000 + 8_000 + 6_000 + 15_000 + 2_000) * 100
    assert recs["Afghanistan"] == pytest.approx(expected_afg, rel=1e-5)
    # All values should be percentages in a plausible range
    for country, share in recs.items():
        assert 0.0 < share < 100.0, f"{country}: unexpected share {share}"


def test_apply_derivation_unknown_raises():
    """Unknown derivation string must raise ValueError, not silently produce wrong output."""
    spec = {"code": "OW-99", "derivation": "magic_unsupported_transform"}
    with pytest.raises(ValueError, match="Unknown derivation string"):
        f._apply_derivation(pd.DataFrame({"x": [1]}), spec)


def test_apply_derivation_missing_age_cols_raises():
    """If any required age-group column is absent, ValueError is raised."""
    df = pd.DataFrame(
        {
            "Code": ["AFG"],
            "Year": [2020],
            "Ages 15-24": [6_000],
            # Missing Under-5s, Ages 5-14, Ages 25-64, Ages 65+
        }
    )
    spec = _pop_young_spec()
    with pytest.raises(ValueError, match="missing age-group columns"):
        f._apply_derivation(df, spec)


# ---------------------------------------------------------------------------
# OWID_SLUM_SHARE: direct value (new spec-driven code)
# ---------------------------------------------------------------------------


def _slum_df() -> pd.DataFrame:
    """Synthetic OWID slum-share CSV payload."""
    return pd.DataFrame(
        {
            "Entity": ["Kenya", "Brazil", "Germany", "Asia"],
            "Code": ["KEN", "BRA", "DEU", "OWID_ASI"],
            "Year": [2018, 2018, 2018, 2018],
            "Proportion of urban population living in slums (%)": [50.0, 24.3, 1.2, np.nan],
        }
    )


def test_parse_owid_slum_share_direct_value():
    """OWID_SLUM_SHARE: percentage value extracted directly, OWID_ aggregate dropped."""
    out = f.parse_owid_records(
        raw_df=_slum_df(),
        value_col="Proportion of urban population living in slums (%)",
        iso3_map=ISO3,
        code_col="Code",
        year_col="Year",
    )
    recs = {r["country"]: r["value"] for r in out.to_dict("records")}
    assert recs["Kenya"] == pytest.approx(50.0)
    assert recs["Brazil"] == pytest.approx(24.3)
    assert recs["Germany"] == pytest.approx(1.2)
    assert "Asia" not in recs  # OWID_ aggregate dropped


# ---------------------------------------------------------------------------
# SPECS dict sanity — updated for spec-driven approach
# ---------------------------------------------------------------------------

_EXPECTED_CODES = {
    "OW-01",
    "OW-04",
    "OWID_REGIMETYPE",
    "OWID_AUTOCRATIZATION",
    "OWID_POP_YOUNG",
    "OWID_SLUM_SHARE",
    "OWID_STATECAP",
}


def test_specs_covers_all_expected_codes():
    """specs.json must contain all expected indicator codes."""
    assert _EXPECTED_CODES.issubset(set(f.SPECS)), f"Missing codes: {_EXPECTED_CODES - set(f.SPECS)}"


def test_specs_ow01_correct_field_names():
    """OW-01 spec uses the standard OWID grapher Code/Year column names."""
    cfg = f.SPECS["OW-01"]
    assert cfg["country_field"] == "Code"
    assert cfg["year_field"] == "Year"
    assert cfg["value_field"] == "Democracy"
    assert not cfg.get("is_derived", False)


def test_specs_ow04_has_correct_fields_and_fallback():
    """OW-04 spec uses iso_code column and carries fallback_level_col."""
    cfg = f.SPECS["OW-04"]
    assert cfg["country_field"] == "iso_code"
    assert cfg["year_field"] == "year"
    assert cfg["value_field"] == "co2_growth_prct"
    assert cfg.get("fallback_level_col") == "co2"
    assert not cfg.get("is_derived", False)


def test_specs_owid_pop_young_is_derived_with_derivation():
    """OWID_POP_YOUNG must be marked is_derived=true with a non-null derivation string."""
    cfg = f.SPECS["OWID_POP_YOUNG"]
    assert cfg["is_derived"] is True
    assert cfg.get("derivation") is not None
    assert "ages_15_24_share" in cfg["derivation"]


def test_specs_owid_autocratization_uses_ert_country_col():
    """OWID_AUTOCRATIZATION must reference the ERT country_text_id column."""
    cfg = f.SPECS["OWID_AUTOCRATIZATION"]
    assert cfg["country_field"] == "country_text_id"
    assert cfg["value_field"] == "aut_ep"
    assert not cfg.get("is_derived", False)


def test_specs_all_entries_have_required_keys():
    """Every spec entry must carry the fields the fetcher depends on."""
    required = {"code", "fetchable", "endpoint_or_dataset", "value_field", "country_field"}
    for code, cfg in f.SPECS.items():
        missing = required - set(cfg)
        assert not missing, f"Spec {code!r} missing keys: {missing}"


def test_fetch_one_rejects_unknown_id():
    with pytest.raises(ValueError):
        f.fetch_one({"id_string": "ZZ-99"})
