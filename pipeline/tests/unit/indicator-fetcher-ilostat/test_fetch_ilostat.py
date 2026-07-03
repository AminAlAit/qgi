"""Tests for the ILOSTAT SDMX fetcher transform (enrichment stage 2).

Pure logic only — no AWS, no network. The base's AWS clients are lazy and the
pandasdmx import lives inside fetch_ilostat_raw(), so importing this module
under test needs neither sdmx1 nor AWS credentials.

The synthetic payloads mimic what pandasdmx 1.x returns from sdmx.to_pandas():
a pandas Series with a MultiIndex whose levels are named by the SDMX dimension
IDs (REF_AREA, TIME_PERIOD) plus OBS_VALUE as the final values column once
the series is reset_index()-ed and its last column is taken as the value.

We build the synthetic payloads directly as pandas Series with a MultiIndex so
no pandasdmx objects are needed in tests.
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

_QGI_PIPELINE = Path(__file__).resolve().parents[3]
_BASE_DIR = _QGI_PIPELINE / "batch" / "_fetcher_base"
_ILO_SRC = _QGI_PIPELINE / "batch" / "indicator-fetcher-ilostat" / "src"
for _p in (_BASE_DIR, _ILO_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qgi_fetcher_base as base  # noqa: E402
import fetch_ilostat as f  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — build synthetic pandasdmx-style observation Series
# ---------------------------------------------------------------------------

ISO3 = {
    "DEU": "Germany",
    "BRA": "Brazil",
    "IND": "India",
    "USA": "United States",
    "GBR": "United Kingdom",
}


def _make_obs_series(rows: list[tuple[str, str, float]]) -> pd.Series:
    """Build a Series that looks like what pandasdmx.to_pandas() returns.

    Each row is (iso3, time_period_str, obs_value).  The MultiIndex levels are
    named 'REF_AREA' and 'TIME_PERIOD', and the Series name (the value column)
    is 'OBS_VALUE'.  This matches the reset_index() structure that
    parse_ilostat_records inspects (it picks the last column as the value).
    """
    if not rows:
        return pd.Series(dtype=float, name="OBS_VALUE")
    idx = pd.MultiIndex.from_tuples(
        [(iso, tp) for iso, tp, _ in rows],
        names=["REF_AREA", "TIME_PERIOD"],
    )
    values = [v for _, _, v in rows]
    return pd.Series(values, index=idx, name="OBS_VALUE", dtype=float)


# ---------------------------------------------------------------------------
# Tests: parse_ilostat_records
# ---------------------------------------------------------------------------


class TestParseIlostatRecords:
    def test_maps_iso3_to_canonical_and_extracts_year(self):
        series = _make_obs_series(
            [
                ("DEU", "2015", 15.3),
                ("BRA", "2016", 45.0),
            ]
        )
        out = f.parse_ilostat_records(series, ISO3)
        assert set(out["country"]) == {"Germany", "Brazil"}
        assert list(out.loc[out["country"] == "Germany", "year"]) == [2015]
        assert list(out.loc[out["country"] == "Brazil", "value"]) == [45.0]

    def test_drops_unresolvable_iso3(self):
        series = _make_obs_series(
            [
                ("DEU", "2015", 20.0),
                ("ZZZ", "2015", 99.9),  # unknown ISO -> dropped
                ("XYZ", "2016", 1.0),  # unknown ISO -> dropped
            ]
        )
        out = f.parse_ilostat_records(series, ISO3)
        assert len(out) == 1
        assert out.iloc[0]["country"] == "Germany"

    def test_aggregates_quarterly_to_annual_mean(self):
        series = _make_obs_series(
            [
                ("DEU", "2020-Q1", 10.0),
                ("DEU", "2020-Q2", 20.0),
                ("DEU", "2020-Q3", 30.0),
                ("DEU", "2020-Q4", 40.0),
                ("BRA", "2020-Q1", 100.0),
                ("BRA", "2020-Q2", 200.0),
            ]
        )
        out = f.parse_ilostat_records(series, ISO3)
        deu = out.loc[out["country"] == "Germany"]
        bra = out.loc[out["country"] == "Brazil"]
        assert len(deu) == 1
        assert abs(deu.iloc[0]["value"] - 25.0) < 1e-9  # mean of 10,20,30,40
        assert abs(bra.iloc[0]["value"] - 150.0) < 1e-9  # mean of 100,200

    def test_drops_observations_before_year_from(self):
        series = _make_obs_series(
            [
                ("DEU", "1985", 5.0),  # before YEAR_FROM (1990) -> dropped
                ("DEU", "1990", 6.0),  # exactly 1990 -> kept
                ("BRA", "1989", 7.0),  # before -> dropped
            ]
        )
        out = f.parse_ilostat_records(series, ISO3)
        assert len(out) == 1
        assert out.iloc[0]["year"] == 1990

    def test_drops_nan_obs_values(self):
        series = _make_obs_series(
            [
                ("DEU", "2010", float("nan")),
                ("BRA", "2010", 50.0),
            ]
        )
        out = f.parse_ilostat_records(series, ISO3)
        assert len(out) == 1
        assert out.iloc[0]["country"] == "Brazil"

    def test_returns_empty_frame_for_none_series(self):
        out = f.parse_ilostat_records(None, ISO3)
        assert list(out.columns) == ["country", "year", "value"]
        assert len(out) == 0

    def test_returns_empty_frame_for_empty_series(self):
        out = f.parse_ilostat_records(pd.Series(dtype=float), ISO3)
        assert list(out.columns) == ["country", "year", "value"]
        assert len(out) == 0

    def test_deduplicates_via_groupby_mean(self):
        series = _make_obs_series(
            [
                ("DEU", "2020", 10.0),
                ("DEU", "2020", 20.0),
            ]
        )
        out = f.parse_ilostat_records(series, ISO3)
        assert len(out) == 1
        assert out.iloc[0]["value"] == 15.0

    def test_multi_country_multi_year(self):
        series = _make_obs_series(
            [
                ("DEU", "2000", 1.0),
                ("DEU", "2001", 2.0),
                ("BRA", "2000", 3.0),
                ("IND", "2005", 4.0),
            ]
        )
        out = f.parse_ilostat_records(series, ISO3)
        assert len(out) == 4
        assert set(out["country"]) == {"Germany", "Brazil", "India"}

    def test_handles_monthly_time_period(self):
        series = _make_obs_series(
            [
                ("USA", "2018-01", 100.0),
                ("USA", "2018-06", 200.0),
                ("USA", "2019-01", 300.0),
            ]
        )
        out = f.parse_ilostat_records(series, ISO3)
        assert len(out) == 2  # 2018 and 2019
        val_2018 = out.loc[out["year"] == 2018, "value"].iloc[0]
        assert abs(val_2018 - 150.0) < 1e-9  # mean of 100, 200


# ---------------------------------------------------------------------------
# Tests: SPECS coverage — spec-driven (loaded from specs.json)
# ---------------------------------------------------------------------------


class TestSpecs:
    def test_all_original_thirteen_indicators_present(self):
        """All original IL-01..IL-13 seed codes must still be in SPECS."""
        expected_seed = {f"IL-{i:02d}" for i in range(1, 14)}
        assert expected_seed.issubset(set(f.SPECS)), f"Missing seed codes: {expected_seed - set(f.SPECS)}"

    def test_new_enrichment_codes_present(self):
        """New IL-14..IL-20 codes from enrichment specs must be present."""
        expected_new = {f"IL-{i:02d}" for i in range(14, 21)}
        assert expected_new.issubset(set(f.SPECS)), f"Missing new codes: {expected_new - set(f.SPECS)}"

    def test_derived_indicators_present(self):
        """Derived IL-21 and IL-22 must be present."""
        assert "IL-21" in f.SPECS, "IL-21 (manufacturing share %) missing"
        assert "IL-22" in f.SPECS, "IL-22 (LT unemployment annual change) missing"

    def test_every_spec_has_required_keys(self):
        for code, cfg in f.SPECS.items():
            assert "code" in cfg, f"{code} missing 'code'"
            assert "dataflow" in cfg or cfg.get("is_derived"), f"{code}: non-derived spec must have 'dataflow'"
            assert "is_derived" in cfg, f"{code} missing 'is_derived'"
            assert "notes" in cfg, f"{code} missing 'notes'"

    def test_every_non_derived_has_dataflow_and_key(self):
        for code, cfg in f.SPECS.items():
            if not cfg.get("is_derived"):
                assert "dataflow" in cfg, f"{code} non-derived missing 'dataflow'"
                assert "key" in cfg, f"{code} non-derived missing 'key'"
                assert isinstance(cfg["dataflow"], str) and cfg["dataflow"], f"{code} dataflow must be non-empty string"
                assert isinstance(cfg["key"], str), f"{code} key must be string"

    def test_every_derived_has_derivation_block(self):
        for code, cfg in f.SPECS.items():
            if cfg.get("is_derived"):
                assert "derivation" in cfg, f"{code} derived but missing 'derivation'"
                assert "type" in cfg["derivation"], f"{code} derivation missing 'type'"

    def test_no_duplicate_dataflow_key_pairs_for_non_derived(self):
        seen: set[tuple[str, str]] = set()
        for code, cfg in f.SPECS.items():
            if cfg.get("is_derived"):
                continue
            pair = (cfg["dataflow"], cfg["key"])
            assert pair not in seen, f"Duplicate (dataflow, key) pair in {code}: {pair}"
            seen.add(pair)

    def test_specs_json_is_valid_json_array(self):
        """specs.json must be a valid JSON array with 'code' field per entry."""
        specs_path = _ILO_SRC / "specs.json"
        assert specs_path.exists(), "specs.json does not exist in src/"
        with open(specs_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data, list), "specs.json must be a JSON array"
        for entry in data:
            assert "code" in entry, f"specs.json entry missing 'code': {entry}"

    def test_il14_labour_income_share_direct_dataset(self):
        """IL-14 uses LAP_2GDP_NOC_RT (direct ILO labour income share dataset)."""
        cfg = f.SPECS["IL-14"]
        assert cfg["dataflow"] == "LAP_2GDP_NOC_RT"
        assert not cfg.get("is_derived")

    def test_il15_informal_employment_rate(self):
        """IL-15 uses EMP_NIFL_SEX_RT (survey-based informality rate)."""
        cfg = f.SPECS["IL-15"]
        assert cfg["dataflow"] == "EMP_NIFL_SEX_RT"
        assert "SEX_T" in cfg["key"]

    def test_il16_neet_survey_based(self):
        """IL-16 uses SDG_0861_SEX_RT (SDG 8.6.1 youth 15-24 NEET), distinct from IL-11."""
        cfg = f.SPECS["IL-16"]
        assert cfg["dataflow"] == "SDG_0861_SEX_RT", (
            f"IL-16 must use SDG_0861_SEX_RT (SDG 8.6.1 youth NEET 15-24), got {cfg['dataflow']!r}"
        )
        assert cfg["dataflow"] != f.SPECS["IL-11"]["dataflow"], "IL-16 and IL-11 must use different NEET dataflows"

    def test_il17_strike_workers_real_dataflow(self):
        """IL-17 uses real dataflow STR_WORK_ECO_NB (not synthetic STR_NWRK_NOC_NB)."""
        cfg = f.SPECS["IL-17"]
        assert cfg["dataflow"] == "STR_WORK_ECO_NB"
        assert cfg["dataflow"] != "STR_NWRK_NOC_NB", (
            "IL-17 must use real dataflow STR_WORK_ECO_NB, not synthetic panel code"
        )

    def test_il18_strike_days_real_dataflow(self):
        """IL-18 uses real dataflow STR_DAYS_ECO_NB (not synthetic STR_DAYS_NOC_NB)."""
        cfg = f.SPECS["IL-18"]
        assert cfg["dataflow"] == "STR_DAYS_ECO_NB"
        assert cfg["dataflow"] != "STR_DAYS_NOC_NB", (
            "IL-18 must use real dataflow STR_DAYS_ECO_NB, not synthetic panel code"
        )

    def test_il19_trade_union_density(self):
        """IL-19 uses ILR_TUMT_NOC_RT."""
        cfg = f.SPECS["IL-19"]
        assert cfg["dataflow"] == "ILR_TUMT_NOC_RT"

    def test_il20_low_pay_rate(self):
        """IL-20 uses EAR_XTLP_SEX_RT with SEX_T."""
        cfg = f.SPECS["IL-20"]
        assert cfg["dataflow"] == "EAR_XTLP_SEX_RT"
        assert "SEX_T" in cfg["key"]


# ---------------------------------------------------------------------------
# Tests: fetch_one raises on unknown indicator (no network needed)
# ---------------------------------------------------------------------------


class TestFetchOneUnknownIndicator:
    def test_raises_value_error_for_unknown_id(self):
        with pytest.raises(ValueError, match="unknown ILOSTAT indicator"):
            f.fetch_one({"id_string": "IL-99"})

    def test_raises_value_error_for_empty_id(self):
        with pytest.raises(ValueError, match="unknown ILOSTAT indicator"):
            f.fetch_one({"id_string": ""})


# ---------------------------------------------------------------------------
# Tests: spec-driven fetch path for new codes (mocked HTTP)
# ---------------------------------------------------------------------------


class TestSpecDrivenFetch:
    """Verify that fetch_one dispatches correctly for new spec codes."""

    def _make_iso3_map(self):
        return {"DEU": "Germany", "BRA": "Brazil", "IND": "India"}

    def _mock_raw_series(self, rows):
        return _make_obs_series(rows)

    def test_il15_informal_employment_rate_fetched_and_parsed(self, monkeypatch):
        """IL-15 (EMP_NIFL_SEX_RT) fetches and parses correctly end-to-end."""
        raw = self._mock_raw_series(
            [
                ("DEU", "2018", 5.2),
                ("BRA", "2019", 42.1),
                ("IND", "2020", 80.5),
            ]
        )
        monkeypatch.setattr(f, "fetch_ilostat_raw", lambda df, key: raw)
        monkeypatch.setattr(base, "load_iso3_country_map", self._make_iso3_map)

        result = f.fetch_one({"id_string": "IL-15"})
        assert len(result) == 3
        assert set(result["country"]) == {"Germany", "Brazil", "India"}
        # Check Germany's value
        ger = result.loc[result["country"] == "Germany"]
        assert abs(ger.iloc[0]["value"] - 5.2) < 1e-9

    def test_il19_trade_union_density_fetched_and_parsed(self, monkeypatch):
        """IL-19 (ILR_TUMT_NOC_RT) fetches and parses correctly."""
        raw = self._mock_raw_series(
            [
                ("DEU", "2015", 17.0),
                ("GBR", "2016", 23.5),
            ]
        )
        monkeypatch.setattr(f, "fetch_ilostat_raw", lambda df, key: raw)
        iso3_map = {**self._make_iso3_map(), "GBR": "United Kingdom"}
        monkeypatch.setattr(base, "load_iso3_country_map", lambda: iso3_map)

        result = f.fetch_one({"id_string": "IL-19"})
        assert len(result) == 2
        # Confirm the right dataflow/key was dispatched
        assert f.SPECS["IL-19"]["dataflow"] == "ILR_TUMT_NOC_RT"

    def test_il17_strike_workers_uses_real_dataflow(self, monkeypatch):
        """IL-17 must request STR_WORK_ECO_NB (not the synthetic panel code)."""
        called_with = {}

        def fake_fetch(dataflow, key):
            called_with["dataflow"] = dataflow
            called_with["key"] = key
            return _make_obs_series([("DEU", "2010", 12.0)])

        monkeypatch.setattr(f, "fetch_ilostat_raw", fake_fetch)
        monkeypatch.setattr(base, "load_iso3_country_map", self._make_iso3_map)

        f.fetch_one({"id_string": "IL-17"})
        assert called_with["dataflow"] == "STR_WORK_ECO_NB", (
            f"Expected STR_WORK_ECO_NB, got {called_with['dataflow']!r}"
        )

    def test_il18_strike_days_uses_real_dataflow(self, monkeypatch):
        """IL-18 must request STR_DAYS_ECO_NB (not the synthetic panel code)."""
        called_with = {}

        def fake_fetch(dataflow, key):
            called_with["dataflow"] = dataflow
            return _make_obs_series([("BRA", "2012", 500.0)])

        monkeypatch.setattr(f, "fetch_ilostat_raw", fake_fetch)
        monkeypatch.setattr(base, "load_iso3_country_map", self._make_iso3_map)

        f.fetch_one({"id_string": "IL-18"})
        assert called_with["dataflow"] == "STR_DAYS_ECO_NB"

    def test_il20_low_pay_rate(self, monkeypatch):
        """IL-20 (EAR_XTLP_SEX_RT) fetches low pay rate correctly."""
        raw = self._mock_raw_series(
            [
                ("USA", "2019", 25.3),
                ("DEU", "2019", 18.7),
            ]
        )
        monkeypatch.setattr(f, "fetch_ilostat_raw", lambda df, key: raw)
        iso3_map = {**self._make_iso3_map(), "USA": "United States"}
        monkeypatch.setattr(base, "load_iso3_country_map", lambda: iso3_map)

        result = f.fetch_one({"id_string": "IL-20"})
        assert len(result) == 2
        usa = result.loc[result["country"] == "United States"]
        assert abs(usa.iloc[0]["value"] - 25.3) < 1e-9


# ---------------------------------------------------------------------------
# Tests: derived indicator computation
# ---------------------------------------------------------------------------


class TestDerivedIndicators:
    """Test the two derived indicators: IL-21 (ratio) and IL-22 (annual_change)."""

    def _iso3(self):
        return {"DEU": "Germany", "BRA": "Brazil", "IND": "India"}

    def test_il21_manufacturing_share_ratio(self, monkeypatch):
        """IL-21 = manufacturing employment / total employment * 100."""
        # manufacturing (numerator): DEU 2015=5000, 2016=4800; BRA 2015=8000
        man_series = _make_obs_series(
            [
                ("DEU", "2015", 5000.0),
                ("DEU", "2016", 4800.0),
                ("BRA", "2015", 8000.0),
            ]
        )
        # total employment (denominator): DEU 2015=40000, 2016=41000; BRA 2015=50000
        tot_series = _make_obs_series(
            [
                ("DEU", "2015", 40000.0),
                ("DEU", "2016", 41000.0),
                ("BRA", "2015", 50000.0),
            ]
        )
        call_count = {"n": 0}

        def fake_fetch(dataflow, key):
            call_count["n"] += 1
            # First call = numerator (manufacturing), second = denominator (total)
            if call_count["n"] == 1:
                return man_series
            return tot_series

        monkeypatch.setattr(f, "fetch_ilostat_raw", fake_fetch)
        monkeypatch.setattr(base, "load_iso3_country_map", self._iso3)

        result = f.fetch_one({"id_string": "IL-21"})
        assert len(result) > 0, "IL-21 returned empty frame"
        deu_2015 = result.loc[(result["country"] == "Germany") & (result["year"] == 2015)]
        assert len(deu_2015) == 1
        expected_share = 5000.0 / 40000.0 * 100.0
        assert abs(deu_2015.iloc[0]["value"] - expected_share) < 1e-6

    def test_il22_long_term_unemployment_annual_change(self, monkeypatch):
        """IL-22 = year-on-year diff of long-term unemployment count."""
        # DEU: 2015=1000, 2016=1200, 2017=900 -> diffs: 2016=+200, 2017=-300
        # BRA: 2015=500, 2016=600 -> diff: 2016=+100
        base_series = _make_obs_series(
            [
                ("DEU", "2015", 1000.0),
                ("DEU", "2016", 1200.0),
                ("DEU", "2017", 900.0),
                ("BRA", "2015", 500.0),
                ("BRA", "2016", 600.0),
            ]
        )
        monkeypatch.setattr(f, "fetch_ilostat_raw", lambda df, key: base_series)
        monkeypatch.setattr(base, "load_iso3_country_map", self._iso3)

        result = f.fetch_one({"id_string": "IL-22"})
        # First year per country is dropped (no prior year to diff against)
        assert len(result) == 3  # DEU 2016, DEU 2017, BRA 2016
        deu_2016 = result.loc[(result["country"] == "Germany") & (result["year"] == 2016)]
        deu_2017 = result.loc[(result["country"] == "Germany") & (result["year"] == 2017)]
        bra_2016 = result.loc[(result["country"] == "Brazil") & (result["year"] == 2016)]

        assert abs(deu_2016.iloc[0]["value"] - 200.0) < 1e-9
        assert abs(deu_2017.iloc[0]["value"] - (-300.0)) < 1e-9
        assert abs(bra_2016.iloc[0]["value"] - 100.0) < 1e-9

    def test_il22_annual_change_empty_when_base_empty(self, monkeypatch):
        """IL-22 returns empty frame when base series is empty."""
        monkeypatch.setattr(f, "fetch_ilostat_raw", lambda df, key: pd.Series(dtype=float))
        monkeypatch.setattr(base, "load_iso3_country_map", self._iso3)

        result = f.fetch_one({"id_string": "IL-22"})
        assert result.empty or len(result) == 0

    def test_il21_ratio_drops_zero_denominator(self, monkeypatch):
        """IL-21 ratio must not produce inf/div-by-zero rows."""
        man_series = _make_obs_series([("DEU", "2020", 1000.0)])
        tot_series = _make_obs_series([("DEU", "2020", 0.0)])  # denominator is 0
        call_count = {"n": 0}

        def fake_fetch(dataflow, key):
            call_count["n"] += 1
            return man_series if call_count["n"] == 1 else tot_series

        monkeypatch.setattr(f, "fetch_ilostat_raw", fake_fetch)
        monkeypatch.setattr(base, "load_iso3_country_map", self._iso3)

        result = f.fetch_one({"id_string": "IL-21"})
        # Row with zero denominator must be dropped
        assert result.empty or len(result) == 0

    def test_il21_ratio_output_is_percentage(self, monkeypatch):
        """IL-21 output should be percentage (0-100 range for realistic data)."""
        man_series = _make_obs_series([("IND", "2018", 60000.0)])
        tot_series = _make_obs_series([("IND", "2018", 500000.0)])
        call_count = {"n": 0}

        def fake_fetch(dataflow, key):
            call_count["n"] += 1
            return man_series if call_count["n"] == 1 else tot_series

        monkeypatch.setattr(f, "fetch_ilostat_raw", fake_fetch)
        monkeypatch.setattr(base, "load_iso3_country_map", self._iso3)

        result = f.fetch_one({"id_string": "IL-21"})
        assert len(result) == 1
        expected = 60000.0 / 500000.0 * 100.0  # = 12.0 %
        assert abs(result.iloc[0]["value"] - expected) < 1e-9
        assert 0 < result.iloc[0]["value"] <= 100, "ratio should be a percentage"


# ---------------------------------------------------------------------------
# Tests: compute_derived dispatches to correct type
# ---------------------------------------------------------------------------


class TestComputeDerived:
    """Unit tests for the compute_derived function directly."""

    def _iso3(self):
        return {"DEU": "Germany", "BRA": "Brazil"}

    def test_unknown_derivation_type_raises(self, monkeypatch):
        """compute_derived raises ValueError for an unknown derivation type."""
        bad_spec = {
            "code": "IL-99",
            "is_derived": True,
            "derivation": {"type": "teleportation"},
            "dataflow_base": "FAKE",
            "key_base": ".A.",
            "notes": "",
        }
        with pytest.raises(ValueError, match="unknown derivation type"):
            f.compute_derived(bad_spec, self._iso3())

    def test_annual_change_single_country_single_obs_returns_empty(self, monkeypatch):
        """When only one year per country, annual_change has nothing to diff."""
        base_series = _make_obs_series([("DEU", "2020", 100.0)])
        monkeypatch.setattr(f, "fetch_ilostat_raw", lambda df, key: base_series)

        spec = {
            "code": "IL-99",
            "is_derived": True,
            "derivation": {"type": "annual_change"},
            "dataflow_base": "FAKE_DF",
            "key_base": ".A.",
            "notes": "",
        }
        result = f.compute_derived(spec, self._iso3())
        assert len(result) == 0, "single year per country should yield empty diff"


# ---------------------------------------------------------------------------
# Tests: base helpers (shared contract — same as UNHCR test mirrors)
# ---------------------------------------------------------------------------


class TestBaseFunctions:
    def test_iso3_map_from_df_uppercases_and_skips_blanks(self):
        df = pd.DataFrame(
            {
                "iso_alpha3": ["deu", "BRA", "", None],
                "qgi_name": ["Germany", "Brazil", "Nowhere", "AlsoNowhere"],
            }
        )
        m = base.iso3_map_from_df(df)
        assert m == {"DEU": "Germany", "BRA": "Brazil"}

    def test_to_canonical_frame_coerces_dedups_sorts_drops_nan(self):
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
        # (A,2000) last value = 9.0; (A,2002) dropped (NaN); (B,2001) = 1.0
        assert out.to_dict("records") == [
            {"country": "A", "year": 2000, "value": 9.0, "is_predicted": False},
            {"country": "B", "year": 2001, "value": 1.0, "is_predicted": False},
        ]

    def test_to_canonical_frame_requires_core_columns(self):
        with pytest.raises(ValueError):
            base.to_canonical_frame(pd.DataFrame({"country": ["A"], "year": [2000]}))
