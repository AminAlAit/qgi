"""Tests for the UCDP fetcher (enrichment stage 2). Pure logic; no net/AWS.

Covers:
  - Legacy UC-01 / UC-04 compatibility via parse_ged_records
  - build_name_map: alias merge + UCDP overrides
  - _aggregate_ged: sum / count / count_distinct / filter_params
  - _aggregate_onesided: sum, binary (derived), count_distinct, multi-gw expansion
  - _aggregate_acd: binary (intensity_level==2), count_distinct
  - _aggregate_onset_csv: field auto-detection, binary max per country-year
  - _aggregate_ov (derived): years_since_last_conflict computation
  - fetch_one: dispatches to correct aggregator via spec source field
  - fetch_one: raises on unknown indicator code
  - SPECS_BY_CODE: all fetchable codes present
  - _resolve_gw_codes: semicolon parsing
  - build_gw_to_canonical: wires GW codes to canonical names
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path wiring — add both src dirs before importing
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[3]
_BASE_DIR = _ROOT / "batch" / "_fetcher_base"
_SRC_DIR = _ROOT / "batch" / "indicator-fetcher-ucdp" / "src"
for _p in (_BASE_DIR, _SRC_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Stub out boto3 so the base imports cleanly without AWS credentials
_boto3_stub = types.ModuleType("boto3")
_boto3_stub.client = MagicMock(return_value=MagicMock())
_boto3_stub.resource = MagicMock(return_value=MagicMock())
sys.modules.setdefault("boto3", _boto3_stub)

import fetch_ucdp as f  # noqa: E402
import qgi_fetcher_base as base  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

NAME_MAP: dict[str, str] = {
    "Afghanistan": "Afghanistan",
    "DR Congo (Zaire)": "The Democratic Republic of the Congo",
    "Syria": "Syria",
    "Iraq": "Iraq",
    "Somalia": "Somalia",
}

# Minimal GW->canonical map for tests (covers GW codes used in test rows)
GW_MAP: dict[int, str] = {
    700: "Afghanistan",  # AFG
    652: "Syria",  # SYR
    645: "Iraq",  # IRQ
    510: "Somalia",  # SOM
    625: "Sudan",  # SDN
    482: "The Democratic Republic of the Congo",  # COD
}

# ---------------------------------------------------------------------------
# Legacy UC-01 / UC-04 compatibility (parse_ged_records, build_name_map)
# ---------------------------------------------------------------------------


class TestLegacyCompatibility:
    def test_parse_ged_filters_by_type_of_violence_and_sums(self):
        records = [
            {"country": "Afghanistan", "year": 2001, "best": 100, "type_of_violence": 1},
            {"country": "Afghanistan", "year": 2001, "best": 50, "type_of_violence": 1},
            {"country": "Afghanistan", "year": 2001, "best": 999, "type_of_violence": 3},
            {"country": "Syria", "year": 2012, "best": 200, "type_of_violence": 1},
        ]
        out = f.parse_ged_records(records, tov=1, name_map=NAME_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2001)] == 150.0
        assert recs[("Syria", 2012)] == 200.0
        assert len(recs) == 2

    def test_parse_ged_one_sided_and_override_mapping(self):
        records = [
            {"country": "DR Congo (Zaire)", "year": 2017, "best": 30, "type_of_violence": 3},
            {"country": "Nowhere", "year": 2017, "best": 5, "type_of_violence": 3},
        ]
        out = f.parse_ged_records(records, tov=3, name_map=NAME_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs == {("The Democratic Republic of the Congo", 2017): 30.0}

    def test_build_name_map_merges_overrides(self):
        merged = f.build_name_map({"Afghanistan": "Afghanistan"})
        assert merged["Afghanistan"] == "Afghanistan"
        assert merged["DR Congo (Zaire)"] == "The Democratic Republic of the Congo"
        assert merged["Myanmar (Burma)"] == "Myanmar"

    def test_parse_ged_empty_when_no_match(self):
        records = [
            {"country": "Afghanistan", "year": 2001, "best": 100, "type_of_violence": 1},
        ]
        out = f.parse_ged_records(records, tov=3, name_map=NAME_MAP)
        assert out.empty
        assert list(out.columns) == ["country", "year", "value"]


# ---------------------------------------------------------------------------
# SPECS_BY_CODE and specs.json integrity
# ---------------------------------------------------------------------------


class TestSpecsRegistry:
    def test_all_fetchable_codes_present(self):
        # Every fetchable spec in specs.json must be in SPECS_BY_CODE
        specs_path = _SRC_DIR / "specs.json"
        raw = json.loads(specs_path.read_text(encoding="utf-8"))
        fetchable_codes = {s["code"] for s in raw if s.get("fetchable")}
        assert fetchable_codes == set(f.SPECS_BY_CODE.keys())

    def test_legacy_seed_codes_present(self):
        assert "UC-01" in f.SPECS_BY_CODE
        assert "UC-04" in f.SPECS_BY_CODE

    def test_enrichment_codes_present(self):
        expected = {
            "UCDP_GED_TOTAL_DEATHS",
            "UCDP_SB_DEATHS_BEST",
            "UCDP_NS_DEATHS_BEST",
            "UCDP_OS_DEATHS_BEST",
            "UCDP_GED_CIV_DEATHS",
            "UCDP_GED_OS_EVENTS",
            "UCDP_GED_NS_EVENTS",
            "UCDP_GED_GEOREGION_SPREAD",
            "UCDP_OS_DEATHS_GOVT",
            "UCDP_OS_GOVT_PERP",
            "UCDP_OS_ACTOR_COUNT",
            "UCDP_SB_INTENSITY_WAR",
            "UCDP_SB_CONFLICT_COUNT",
            "UCDP_SB_ONSET",
            "UCDP_YEARS_SINCE_LAST_CONFLICT",
        }
        for code in expected:
            assert code in f.SPECS_BY_CODE, f"Missing: {code}"

    def test_derived_codes_flagged(self):
        derived = [c for c, s in f.SPECS_BY_CODE.items() if s.get("is_derived")]
        assert "UCDP_OS_GOVT_PERP" in derived
        assert "UCDP_SB_INTENSITY_WAR" in derived
        assert "UCDP_YEARS_SINCE_LAST_CONFLICT" in derived


# ---------------------------------------------------------------------------
# _resolve_gw_codes
# ---------------------------------------------------------------------------


class TestResolveGwCodes:
    def test_single_code(self):
        assert f._resolve_gw_codes(700) == [700]

    def test_semicolon_separated(self):
        assert f._resolve_gw_codes("700;652;645") == [700, 652, 645]

    def test_comma_separated(self):
        assert f._resolve_gw_codes("700,652") == [700, 652]

    def test_float_code(self):
        assert f._resolve_gw_codes(700.0) == [700]

    def test_nan_returns_empty(self):
        import math

        assert f._resolve_gw_codes(float("nan")) == []

    def test_none_returns_empty(self):
        assert f._resolve_gw_codes(None) == []


# ---------------------------------------------------------------------------
# build_gw_to_canonical
# ---------------------------------------------------------------------------


class TestBuildGwToCanonical:
    def test_known_gw_maps_to_canonical(self):
        iso3_map = {"AFG": "Afghanistan", "SYR": "Syria", "IRQ": "Iraq"}
        result = f.build_gw_to_canonical(iso3_map)
        assert result[700] == "Afghanistan"
        assert result[652] == "Syria"
        assert result[645] == "Iraq"

    def test_unmapped_iso3_excluded(self):
        # If ISO3 map doesn't contain a code, that GW code should be absent
        iso3_map = {"AFG": "Afghanistan"}
        result = f.build_gw_to_canonical(iso3_map)
        assert 700 in result
        # SYR not in iso3_map -> 652 absent
        assert 652 not in result


# ---------------------------------------------------------------------------
# _aggregate_ged
# ---------------------------------------------------------------------------


class TestAggregateGed:
    def _make_ged_df(self):
        return pd.DataFrame(
            [
                {
                    "country": "Afghanistan",
                    "year": 2020,
                    "type_of_violence": 1,
                    "best": 100,
                    "deaths_civilians": 10,
                    "adm_1": "Kabul",
                    "id": "e1",
                },
                {
                    "country": "Afghanistan",
                    "year": 2020,
                    "type_of_violence": 1,
                    "best": 200,
                    "deaths_civilians": 20,
                    "adm_1": "Kandahar",
                    "id": "e2",
                },
                {
                    "country": "Afghanistan",
                    "year": 2020,
                    "type_of_violence": 2,
                    "best": 50,
                    "deaths_civilians": 5,
                    "adm_1": "Kabul",
                    "id": "e3",
                },
                {
                    "country": "Syria",
                    "year": 2020,
                    "type_of_violence": 3,
                    "best": 300,
                    "deaths_civilians": 150,
                    "adm_1": "Aleppo",
                    "id": "e4",
                },
                {
                    "country": "Unknown",
                    "year": 2020,
                    "type_of_violence": 1,
                    "best": 999,
                    "deaths_civilians": 99,
                    "adm_1": "X",
                    "id": "e5",
                },
            ]
        )

    def test_sum_with_tov_filter(self):
        df = self._make_ged_df()
        spec = {
            "value_field": "best",
            "country_field": "country",
            "filter_params": {"type_of_violence": 1},
            "transform": "sum",
        }
        out = f._aggregate_ged(df, spec, NAME_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2020)] == 300.0  # 100+200
        assert ("Syria", 2020) not in recs  # tov=3, filtered out
        assert ("Unknown", 2020) not in recs  # unmapped

    def test_sum_all_tov(self):
        df = self._make_ged_df()
        spec = {
            "value_field": "best",
            "country_field": "country",
            "filter_params": {},
            "transform": "sum",
        }
        out = f._aggregate_ged(df, spec, NAME_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        # Afghanistan: 100+200+50=350; Syria: 300
        assert recs[("Afghanistan", 2020)] == 350.0
        assert recs[("Syria", 2020)] == 300.0

    def test_sum_civ_deaths(self):
        df = self._make_ged_df()
        spec = {
            "value_field": "deaths_civilians",
            "country_field": "country",
            "filter_params": {},
            "transform": "sum",
        }
        out = f._aggregate_ged(df, spec, NAME_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2020)] == 35.0  # 10+20+5

    def test_count_events(self):
        df = self._make_ged_df()
        spec = {
            "value_field": "id",
            "country_field": "country",
            "filter_params": {"type_of_violence": 3},
            "transform": "count",
        }
        out = f._aggregate_ged(df, spec, NAME_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Syria", 2020)] == 1.0
        assert ("Afghanistan", 2020) not in recs

    def test_count_distinct_adm1(self):
        df = self._make_ged_df()
        spec = {
            "value_field": "adm_1",
            "country_field": "country",
            "filter_params": {},
            "transform": "count_distinct",
        }
        out = f._aggregate_ged(df, spec, NAME_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        # Afghanistan has Kabul (2x) + Kandahar = 2 distinct (kabul+kandahar lowercased)
        assert recs[("Afghanistan", 2020)] == 2.0
        assert recs[("Syria", 2020)] == 1.0

    def test_unknown_transform_raises(self):
        df = self._make_ged_df()
        spec = {
            "value_field": "best",
            "country_field": "country",
            "filter_params": {},
            "transform": "bogus",
        }
        with pytest.raises(ValueError, match="Unknown transform"):
            f._aggregate_ged(df, spec, NAME_MAP)


# ---------------------------------------------------------------------------
# _aggregate_onesided (includes derived UCDP_OS_GOVT_PERP)
# ---------------------------------------------------------------------------


class TestAggregateOnesided:
    def _make_onesided_df(self):
        return pd.DataFrame(
            [
                # Government of Afghanistan in AFG (gw=700)
                {
                    "gwno_where": "700",
                    "year": 2020,
                    "side_a": "Government of Afghanistan",
                    "deaths_best": 50,
                    "actor_id": "A1",
                },
                # Non-govt actor in AFG
                {"gwno_where": "700", "year": 2020, "side_a": "Taliban", "deaths_best": 30, "actor_id": "A2"},
                # Govt in Syria (gw=652) — multi-GW: SYR+IRQ
                {
                    "gwno_where": "652;645",
                    "year": 2019,
                    "side_a": "Government of Syria",
                    "deaths_best": 100,
                    "actor_id": "A3",
                },
                # Somalia (gw=510) - no deaths
                {"gwno_where": "510", "year": 2020, "side_a": "Al-Shabaab", "deaths_best": 0, "actor_id": "A4"},
            ]
        )

    def test_sum_govt_perp(self):
        df = self._make_onesided_df()
        spec = {
            "value_field": "deaths_best",
            "country_field": "gwno_where",
            "filter_params": {"side_a_dset_id_type": "government"},
            "transform": "sum",
        }
        out = f._aggregate_onesided(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2020)] == 50.0
        assert recs[("Syria", 2019)] == 100.0
        assert recs[("Iraq", 2019)] == 100.0  # multi-GW expansion
        assert ("Somalia", 2020) not in recs or recs.get(("Somalia", 2020), 0) == 0

    def test_binary_govt_perp_derived(self):
        """UCDP_OS_GOVT_PERP: binary=1 if govt deaths > 0."""
        df = self._make_onesided_df()
        spec = {
            "value_field": "deaths_best",
            "country_field": "gwno_where",
            "filter_params": {"side_a_dset_id_type": "government"},
            "transform": "binary",
        }
        out = f._aggregate_onesided(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2020)] == 1.0
        assert recs[("Syria", 2019)] == 1.0

    def test_count_distinct_actors(self):
        """UCDP_OS_ACTOR_COUNT: nunique actor_id per country-year."""
        df = self._make_onesided_df()
        spec = {
            "value_field": "actor_id",
            "country_field": "gwno_where",
            "filter_params": {},
            "transform": "count_distinct",
        }
        out = f._aggregate_onesided(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        # AFG 2020: A1 + A2 = 2
        assert recs[("Afghanistan", 2020)] == 2.0
        # SYR 2019: A3 = 1
        assert recs[("Syria", 2019)] == 1.0

    def test_no_govt_filter_returns_all(self):
        df = self._make_onesided_df()
        spec = {
            "value_field": "deaths_best",
            "country_field": "gwno_where",
            "filter_params": {},
            "transform": "sum",
        }
        out = f._aggregate_onesided(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        # AFG: 50 (govt) + 30 (non-govt) = 80
        assert recs[("Afghanistan", 2020)] == 80.0

    def test_unmapped_gw_code_dropped(self):
        df = pd.DataFrame(
            [
                {"gwno_where": "9999", "year": 2020, "side_a": "Rebel", "deaths_best": 100, "actor_id": "X"},
            ]
        )
        spec = {
            "value_field": "deaths_best",
            "country_field": "gwno_where",
            "filter_params": {},
            "transform": "sum",
        }
        out = f._aggregate_onesided(df, spec, GW_MAP)
        assert out.empty


# ---------------------------------------------------------------------------
# _aggregate_acd (UCDP_SB_INTENSITY_WAR, UCDP_SB_CONFLICT_COUNT)
# ---------------------------------------------------------------------------


class TestAggregateAcd:
    def _make_acd_df(self):
        return pd.DataFrame(
            [
                {"gwno_loc": "700", "year": 2018, "intensity_level": 2, "conflict_id": "C1"},
                {"gwno_loc": "700", "year": 2018, "intensity_level": 1, "conflict_id": "C2"},
                {"gwno_loc": "652", "year": 2018, "intensity_level": 1, "conflict_id": "C3"},
                {"gwno_loc": "652;510", "year": 2019, "intensity_level": 2, "conflict_id": "C4"},
                {"gwno_loc": "700", "year": 2019, "intensity_level": 1, "conflict_id": "C1"},
            ]
        )

    def test_intensity_war_binary(self):
        """UCDP_SB_INTENSITY_WAR: 1 if any conflict hit intensity_level==2 in year."""
        df = self._make_acd_df()
        spec = {
            "value_field": "intensity_level",
            "country_field": "gwno_loc",
            "filter_params": {},
            "transform": "binary",
        }
        out = f._aggregate_acd(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2018)] == 1.0  # C1 at level 2
        assert recs[("Syria", 2018)] == 0.0  # only level 1
        assert recs[("Syria", 2019)] == 1.0  # C4 at level 2 via multi-GW
        assert recs[("Somalia", 2019)] == 1.0  # C4 multi-GW expansion
        assert recs[("Afghanistan", 2019)] == 0.0  # only level 1

    def test_conflict_count_distinct(self):
        """UCDP_SB_CONFLICT_COUNT: distinct conflict_ids per country-year."""
        df = self._make_acd_df()
        spec = {
            "value_field": "conflict_id",
            "country_field": "gwno_loc",
            "filter_params": {},
            "transform": "count_distinct",
        }
        out = f._aggregate_acd(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2018)] == 2.0  # C1, C2
        assert recs[("Syria", 2018)] == 1.0  # C3
        assert recs[("Syria", 2019)] == 1.0  # C4


# ---------------------------------------------------------------------------
# _aggregate_onset_csv (UCDP_SB_ONSET)
# ---------------------------------------------------------------------------


class TestAggregateOnsetCsv:
    def _make_onset_df_named(self, field: str):
        return pd.DataFrame(
            [
                {"gwno_a": "700", "year": 2000, field: 1},
                {"gwno_a": "700", "year": 2001, field: 0},
                {"gwno_a": "652", "year": 2000, field: 0},
                {"gwno_a": "652", "year": 2011, field: 1},
                # Multi-country via semicolons
                {"gwno_a": "510;625", "year": 2005, field: 1},
            ]
        )

    def test_onset_field_detection_and_binary(self):
        df = self._make_onset_df_named("onset")
        spec = {
            "value_field": "onset",
            "country_field": "gwno_a",
            "filter_params": {},
            "transform": "binary",
        }
        out = f._aggregate_onset_csv(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2000)] == 1.0
        assert recs[("Afghanistan", 2001)] == 0.0
        assert recs[("Syria", 2011)] == 1.0

    def test_onset_new_conflict_field_fallback(self):
        """If 'onset' not present, should fall back to 'new_conflict'."""
        df = self._make_onset_df_named("new_conflict")
        spec = {
            "value_field": "onset",
            "country_field": "gwno_a",
            "filter_params": {},
            "transform": "binary",
        }
        out = f._aggregate_onset_csv(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2000)] == 1.0

    def test_onset_multi_gw_expansion(self):
        df = self._make_onset_df_named("onset")
        spec = {
            "value_field": "onset",
            "country_field": "gwno_a",
            "filter_params": {},
            "transform": "binary",
        }
        out = f._aggregate_onset_csv(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        # gwno "510;625" => Somalia (510) + Sudan (625)
        assert recs[("Somalia", 2005)] == 1.0
        assert recs[("Sudan", 2005)] == 1.0

    def test_onset_no_field_returns_empty(self):
        df = pd.DataFrame([{"gwno_a": "700", "year": 2000, "conflict_id": "C1"}])
        spec = {
            "value_field": "onset",
            "country_field": "gwno_a",
            "filter_params": {},
            "transform": "binary",
        }
        out = f._aggregate_onset_csv(df, spec, GW_MAP)
        assert out.empty


# ---------------------------------------------------------------------------
# _aggregate_ov — UCDP_YEARS_SINCE_LAST_CONFLICT (derived)
# ---------------------------------------------------------------------------


class TestAggregateOv:
    def _make_ov_df(self):
        # Afghanistan: active 2010-2012, then peace; Syria: active 2011+2013 (gap 2012)
        return pd.DataFrame(
            [
                {"gwno_loc": "700", "year": 2010, "sb_exist": "1", "ns_exist": "0", "os_exist": "0"},
                {"gwno_loc": "700", "year": 2011, "sb_exist": "1", "ns_exist": "0", "os_exist": "0"},
                {"gwno_loc": "700", "year": 2012, "sb_exist": "1", "ns_exist": "0", "os_exist": "0"},
                {"gwno_loc": "700", "year": 2013, "sb_exist": "0", "ns_exist": "0", "os_exist": "0"},
                {"gwno_loc": "700", "year": 2014, "sb_exist": "0", "ns_exist": "0", "os_exist": "0"},
                {"gwno_loc": "652", "year": 2011, "sb_exist": "1", "ns_exist": "0", "os_exist": "0"},
                {"gwno_loc": "652", "year": 2012, "sb_exist": "0", "ns_exist": "0", "os_exist": "0"},
                {"gwno_loc": "652", "year": 2013, "sb_exist": "1", "ns_exist": "0", "os_exist": "0"},
            ]
        )

    def test_years_since_last_conflict_active_is_zero(self):
        df = self._make_ov_df()
        spec = {
            "value_field": "sb_exist",
            "country_field": "gwno_loc",
            "filter_params": {},
            "transform": "years_since",
        }
        out = f._aggregate_ov(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        # Active years -> 0
        assert recs[("Afghanistan", 2010)] == 0.0
        assert recs[("Afghanistan", 2011)] == 0.0
        assert recs[("Afghanistan", 2012)] == 0.0
        assert recs[("Syria", 2011)] == 0.0
        assert recs[("Syria", 2013)] == 0.0

    def test_years_since_last_conflict_peace_increments(self):
        df = self._make_ov_df()
        spec = {
            "value_field": "sb_exist",
            "country_field": "gwno_loc",
            "filter_params": {},
            "transform": "years_since",
        }
        out = f._aggregate_ov(df, spec, GW_MAP)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        # AFG: last active = 2012; 2013 -> 1, 2014 -> 2
        assert recs[("Afghanistan", 2013)] == 1.0
        assert recs[("Afghanistan", 2014)] == 2.0
        # SYR: gap year 2012 -> last_active=2011 -> 2012-2011=1
        assert recs[("Syria", 2012)] == 1.0

    def test_years_since_no_prior_conflict_excluded(self):
        """Country with no active conflict row in the dataset -> no output row."""
        df = pd.DataFrame(
            [
                {"gwno_loc": "700", "year": 2015, "sb_exist": "0", "ns_exist": "0", "os_exist": "0"},
            ]
        )
        spec = {
            "value_field": "sb_exist",
            "country_field": "gwno_loc",
            "filter_params": {},
            "transform": "years_since",
        }
        out = f._aggregate_ov(df, spec, GW_MAP)
        # No prior conflict -> no rows (not 0, since we have no baseline)
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert ("Afghanistan", 2015) not in recs


# ---------------------------------------------------------------------------
# fetch_one dispatch (mocked _load_bulk + base helpers)
# ---------------------------------------------------------------------------


class TestFetchOneDispatch:
    """fetch_one should delegate to the correct aggregator based on spec source."""

    def _stub_ged_df(self):
        return pd.DataFrame(
            [
                {
                    "country": "Afghanistan",
                    "year": 2020,
                    "type_of_violence": 1,
                    "best": 500,
                    "deaths_civilians": 50,
                    "adm_1": "Kabul",
                    "id": "e1",
                },
            ]
        )

    def _stub_onesided_df(self):
        # Column names match the live UCDP One-sided v24.1 CSV:
        # gwno_location (not gwno_where), best_fatality_estimate (not deaths_best),
        # is_government_actor (1/0 integer flag present in v24.1+)
        return pd.DataFrame(
            [
                {
                    "gwno_location": "700",
                    "year": 2020,
                    "is_government_actor": 1,
                    "best_fatality_estimate": 100,
                    "actor_id": "A1",
                },
            ]
        )

    def _stub_acd_df(self):
        return pd.DataFrame(
            [
                {"gwno_loc": "700", "year": 2020, "intensity_level": 2, "conflict_id": "C1"},
            ]
        )

    def _stub_onset_df(self):
        return pd.DataFrame(
            [
                {"gwno_a": "700", "year": 2020, "onset": 1},
            ]
        )

    def _stub_ov_df(self):
        # Dataset v26.1 (organizedviolencecy-261) uses a name-based 'country'
        # column (no gwno_loc); canonical mapping goes via name_map.
        # NAME_MAP maps "Afghanistan" -> "Afghanistan" directly.
        return pd.DataFrame(
            [
                {"country": "Afghanistan", "year": 2019, "sb_exist": "1", "ns_exist": "0", "os_exist": "0"},
                {"country": "Afghanistan", "year": 2020, "sb_exist": "0", "ns_exist": "0", "os_exist": "0"},
            ]
        )

    def _mock_base_helpers(self, name_map=None, iso3_map=None):
        """Return a pair of (name_alias_mock, iso3_mock) patch targets."""
        if name_map is None:
            name_map = NAME_MAP
        if iso3_map is None:
            iso3_map = {
                "AFG": "Afghanistan",
                "SYR": "Syria",
                "IRQ": "Iraq",
                "SOM": "Somalia",
                "SDN": "Sudan",
                "COD": "The Democratic Republic of the Congo",
            }
        return name_map, iso3_map

    def test_fetch_one_ged_sum_code(self):
        nm, iso3 = self._mock_base_helpers()
        with (
            patch.object(f, "_load_bulk", return_value=self._stub_ged_df()),
            patch.object(base, "load_name_alias_map", return_value=nm),
            patch.object(f, "_gw_to_canonical_cache", None),
            patch.object(base, "load_iso3_country_map", return_value=iso3),
        ):
            out = f.fetch_one({"id_string": "UCDP_SB_DEATHS_BEST"})
        assert not out.empty
        assert "Afghanistan" in out["country"].values
        assert out[out["country"] == "Afghanistan"]["value"].iloc[0] == 500.0

    def test_fetch_one_ged_count_code(self):
        nm, iso3 = self._mock_base_helpers()
        with (
            patch.object(f, "_load_bulk", return_value=self._stub_ged_df()),
            patch.object(base, "load_name_alias_map", return_value=nm),
            patch.object(base, "load_iso3_country_map", return_value=iso3),
        ):
            out = f.fetch_one({"id_string": "UCDP_GED_OS_EVENTS"})
        # tov filter=3 -> Afghanistan row has tov=1 -> empty output
        assert out.empty or len(out) == 0

    def test_fetch_one_onesided_sum(self):
        nm, iso3 = self._mock_base_helpers()
        # Reset GW cache so it rebuilds with our iso3_map
        f._gw_to_canonical_cache = None
        with (
            patch.object(f, "_load_bulk", return_value=self._stub_onesided_df()),
            patch.object(base, "load_iso3_country_map", return_value=iso3),
        ):
            out = f.fetch_one({"id_string": "UCDP_OS_DEATHS_GOVT"})
        assert not out.empty
        assert out[out["country"] == "Afghanistan"]["value"].iloc[0] == 100.0

    def test_fetch_one_derived_binary_govt_perp(self):
        nm, iso3 = self._mock_base_helpers()
        f._gw_to_canonical_cache = None
        with (
            patch.object(f, "_load_bulk", return_value=self._stub_onesided_df()),
            patch.object(base, "load_iso3_country_map", return_value=iso3),
        ):
            out = f.fetch_one({"id_string": "UCDP_OS_GOVT_PERP"})
        assert not out.empty
        # Should be 1.0 (binary, govt deaths > 0)
        assert out[out["country"] == "Afghanistan"]["value"].iloc[0] == 1.0

    def test_fetch_one_acd_intensity_war(self):
        nm, iso3 = self._mock_base_helpers()
        f._gw_to_canonical_cache = None
        with (
            patch.object(f, "_load_bulk", return_value=self._stub_acd_df()),
            patch.object(base, "load_iso3_country_map", return_value=iso3),
        ):
            out = f.fetch_one({"id_string": "UCDP_SB_INTENSITY_WAR"})
        assert not out.empty
        assert out[out["country"] == "Afghanistan"]["value"].iloc[0] == 1.0

    def test_fetch_one_onset(self):
        nm, iso3 = self._mock_base_helpers()
        f._gw_to_canonical_cache = None
        with (
            patch.object(f, "_load_bulk", return_value=self._stub_onset_df()),
            patch.object(base, "load_iso3_country_map", return_value=iso3),
        ):
            out = f.fetch_one({"id_string": "UCDP_SB_ONSET"})
        assert not out.empty
        assert out[out["country"] == "Afghanistan"]["value"].iloc[0] == 1.0

    def test_fetch_one_years_since_last_conflict(self):
        nm, iso3 = self._mock_base_helpers()
        f._gw_to_canonical_cache = None
        # ov_bulk path calls base.load_name_alias_map() to build the name map
        # (OV v26.1 uses a name-based 'country' column).  Patch it alongside
        # load_iso3_country_map so the test never touches S3.
        with (
            patch.object(f, "_load_bulk", return_value=self._stub_ov_df()),
            patch.object(base, "load_iso3_country_map", return_value=iso3),
            patch.object(base, "load_name_alias_map", return_value=nm),
        ):
            out = f.fetch_one({"id_string": "UCDP_YEARS_SINCE_LAST_CONFLICT"})
        recs = {(r["country"], r["year"]): r["value"] for r in out.to_dict("records")}
        assert recs[("Afghanistan", 2019)] == 0.0  # active
        assert recs[("Afghanistan", 2020)] == 1.0  # 1 year since 2019

    def test_fetch_one_unknown_code_raises(self):
        with pytest.raises(ValueError, match="unknown indicator"):
            f.fetch_one({"id_string": "UC-99-NONEXISTENT"})

    def test_fetch_one_legacy_uc01(self):
        """UC-01 still works via spec-driven path (ged_bulk source)."""
        nm, iso3 = self._mock_base_helpers()
        f._gw_to_canonical_cache = None
        with (
            patch.object(f, "_load_bulk", return_value=self._stub_ged_df()),
            patch.object(base, "load_name_alias_map", return_value=nm),
            patch.object(base, "load_iso3_country_map", return_value=iso3),
        ):
            out = f.fetch_one({"id_string": "UC-01"})
        # tov filter=1 -> Afghanistan row passes
        assert not out.empty
        assert out[out["country"] == "Afghanistan"]["value"].iloc[0] == 500.0

    def test_fetch_one_legacy_uc04(self):
        """UC-04 still works via spec-driven path (ged_bulk source, tov=3)."""
        nm, iso3 = self._mock_base_helpers()
        with (
            patch.object(f, "_load_bulk", return_value=self._stub_ged_df()),
            patch.object(base, "load_name_alias_map", return_value=nm),
            patch.object(base, "load_iso3_country_map", return_value=iso3),
        ):
            out = f.fetch_one({"id_string": "UC-04"})
        # tov filter=3 -> Afghanistan row has tov=1 -> empty
        assert out.empty or len(out) == 0
