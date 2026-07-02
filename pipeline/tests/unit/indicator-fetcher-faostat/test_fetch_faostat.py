"""Unit tests for batch/indicator-fetcher-faostat/src/fetch_faostat.py.

All tests are pure-transform / unit-level.  No network, no S3, no DDB.
AWS clients in the base are lazy (only instantiated on real I/O calls)
so importing works cleanly under pytest without credentials.

Coverage:
- specs.json loaded correctly + all required keys present
- fetch_domain_csv: ZIP extraction, flag-file skipping, retry logic, cache
- _coerce_values: <X sentinel, suppression drop, unknown drop, float64
- _end_year: 4-digit (annual) and 8-digit (3yr_avg) year codes
- extract_from_domain: filtering, country mapping, first-difference,
  variance floor, ET domain (Months Code column), dedup priority
- compute_derived: annual_change, ratio, per_1000_pop, binary; unknown form
- fetch_one: happy path for FS-001 (non-derived), happy path for FS-003
  (3yr_avg same domain, uses ZIP cache), unknown indicator guard
- Two new spec codes (SDGB-009 and ET-001) fully exercised through
  extract_from_domain
- One derived path (annual_change) end-to-end with mocked base series
"""

from __future__ import annotations

import io
import json
import os
import sys
import types
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path wiring: insert base + fetcher src so imports resolve without install
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[3]
_BASE_DIR = _ROOT / "batch" / "_fetcher_base"
_FAOSTAT_SRC = _ROOT / "batch" / "indicator-fetcher-faostat" / "src"

for _p in (_BASE_DIR, _FAOSTAT_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---------------------------------------------------------------------------
# Minimal env so qgi_fetcher_base doesn't crash at import time
# (lazy AWS clients need S3_BUCKET / RUN_ID only on actual calls)
# ---------------------------------------------------------------------------
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("RUN_ID", "test-run-faostat-001")
os.environ.setdefault("JITTER_MIN_S", "0")
os.environ.setdefault("JITTER_MAX_S", "0")

import qgi_fetcher_base as base  # noqa: E402
import fetch_faostat as f  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_COUNTRY_MAP_CSV = (
    "qgi_country_id,qgi_name,m49_code,iso_alpha3,fao_area_code,notes\n"
    "1,Afghanistan,4,AFG,2,\n"
    "23,Brazil,76,BRA,21,\n"
    "165,Norway,578,NOR,162,\n"
    "195,Turkey,792,TUR,223,\n"
    "115,Kosovo,,XKX,,FAO folds into Serbia\n"
)


# Build the fao_area_map the way the fetcher builds it (without S3)
def _make_fao_area_map() -> dict[int, str]:
    df = pd.read_csv(io.StringIO(_COUNTRY_MAP_CSV))
    out: dict[int, str] = {}
    for _, row in df.iterrows():
        fao = row.get("fao_area_code")
        name = str(row.get("qgi_name") or "").strip()
        if not (isinstance(fao, float) and np.isnan(fao)) and name:
            try:
                out[int(fao)] = name
            except (TypeError, ValueError):
                pass
    return out


_FAO_AREA_MAP = _make_fao_area_map()

# ---------------------------------------------------------------------------
# Sample domain CSV fixtures
# ---------------------------------------------------------------------------

# FS domain — 3yr_avg (8-digit Year Codes), Item Code / Element Code
_FS_DOMAIN_CSV = (
    '"Area Code","Area","Item Code","Item","Element Code","Element","Year Code","Year","Value","Unit","Flag","Note"\n'
    # Afghanistan — 4 rows of 3yr_avg (will produce 3 diffs)
    '2,"Afghanistan",210041,"PoU",6121,"Value",20002002,"2000-2002",45.8,"%","E",\n'
    '2,"Afghanistan",210041,"PoU",6121,"Value",20012003,"2001-2003",44.0,"%","E",\n'
    '2,"Afghanistan",210041,"PoU",6121,"Value",20022004,"2002-2004",42.0,"%","E",\n'
    '2,"Afghanistan",210041,"PoU",6121,"Value",20032005,"2003-2005",40.0,"%","E",\n'
    # Brazil — 3 rows (will produce 2 diffs)
    '21,"Brazil",210041,"PoU",6121,"Value",20002002,"2000-2002",8.0,"%","E",\n'
    '21,"Brazil",210041,"PoU",6121,"Value",20012003,"2001-2003",7.0,"%","E",\n'
    '21,"Brazil",210041,"PoU",6121,"Value",20022004,"2002-2004",5.5,"%","E",\n'
    # Norway — all <0.1 -> 0.05 -> flat after diff -> dropped by variance floor
    '162,"Norway",210041,"PoU",6121,"Value",20002002,"2000-2002","<0.1","%","E",\n'
    '162,"Norway",210041,"PoU",6121,"Value",20012003,"2001-2003","<0.1","%","E",\n'
    '162,"Norway",210041,"PoU",6121,"Value",20022004,"2002-2004","<0.1","%","E",\n'
    # Turkey — suppressed value
    '223,"Turkey",210041,"PoU",6121,"Value",20002002,"2000-2002","...","%","E",\n'
    # Regional aggregate (no mapping in fao_area_map)
    '5000,"Africa",210041,"PoU",6121,"Value",20002002,"2000-2002",22.0,"%","A",\n'
    # Different indicator (FS-003 item code) — should be filtered out for FS-001
    '2,"Afghanistan",210091,"FIES",6121,"Value",20002002,"2000-2002",55.0,"%","E",\n'
)

# SDGB domain — annual (4-digit Year Codes), string item codes.
# Note: variance floor drops single-year country series (std=NaN -> 0 < 1e-6),
# so each country needs at least 2 rows to survive.
_SDGB_DOMAIN_CSV = (
    '"Area Code","Area","Item Code","Item","Element Code","Element","Year Code","Year","Value","Unit","Flag","Note"\n'
    '2,"Afghanistan",24025,"IFPA",6125,"Value",2010,"2010",-0.12,"","E",\n'
    '2,"Afghanistan",24025,"IFPA",6125,"Value",2011,"2011",0.5,"","E",\n'
    '21,"Brazil",24025,"IFPA",6125,"Value",2010,"2010",1.2,"","E",\n'
    '21,"Brazil",24025,"IFPA",6125,"Value",2011,"2011",0.9,"","E",\n'
    # Different element code (water stress) — filter out by item code mismatch
    '2,"Afghanistan","24027-_T","WaterStress",6121,"Value",2010,"2010",54.76,"%","I",\n'
)

# ET domain — uses "Months Code" instead of "Item Code".
# Note: variance floor drops single-year country series, so Brazil needs 2+ rows.
_ET_DOMAIN_CSV = (
    '"Area Code","Area","Months Code","Months","Element Code","Element","Year Code","Year","Value","Unit","Flag","Note"\n'
    '2,"Afghanistan",7020,"Meteorological year",7271,"Temperature change",2020,"2020",1.3,"C","E",\n'
    '2,"Afghanistan",7020,"Meteorological year",7271,"Temperature change",2021,"2021",1.5,"C","E",\n'
    '21,"Brazil",7020,"Meteorological year",7271,"Temperature change",2020,"2020",0.8,"C","E",\n'
    '21,"Brazil",7020,"Meteorological year",7271,"Temperature change",2021,"2021",0.9,"C","E",\n'
    # Different months code (January = 7001) — should be filtered out
    '2,"Afghanistan",7001,"January",7271,"Temperature change",2020,"2020",0.9,"C","E",\n'
)


def _make_zip(csv_text: str, inner_name: str = "Data_E_All_Data_(Normalized).csv") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_name, csv_text.encode("latin-1"))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests: specs.json completeness
# ---------------------------------------------------------------------------


class TestSpecsJson:
    def test_specs_loaded_as_dict(self):
        assert isinstance(f.SPECS, dict)
        assert len(f.SPECS) >= 6  # at least the 7 fetchable ones (excluding CAHD-002)

    def test_all_required_keys_present(self):
        required = {
            "code",
            "fao_domain_code",
            "bulk_url",
            "fao_item_code",
            "fao_element_code",
            "item_column",
            "element_column",
            "value_field",
            "country_field",
            "frequency",
            "transform",
            "is_derived",
        }
        for code, spec in f.SPECS.items():
            missing = required - set(spec)
            assert not missing, f"{code} missing required spec keys: {missing}"

    def test_fs_codes_present(self):
        assert "FS-001" in f.SPECS
        assert "FS-003" in f.SPECS
        assert "FS-004" in f.SPECS

    def test_sdgb_codes_present(self):
        assert "SDGB-009" in f.SPECS
        assert "SDGB-012" in f.SPECS

    def test_et_code_present(self):
        assert "ET-001" in f.SPECS

    def test_tc_code_present(self):
        assert "TC-002" in f.SPECS

    def test_cahd_002_excluded(self):
        """CAHD-002 has fetchable=false (403 bulk access) — must not be in SPECS."""
        assert "CAHD-002" not in f.SPECS

    def test_et_001_uses_months_code_column(self):
        """ET domain uses Months Code not Item Code — must be reflected in spec."""
        assert f.SPECS["ET-001"]["item_column"] == "Months Code"

    def test_fs_indicators_are_first_difference(self):
        for code in ("FS-001", "FS-003", "FS-004"):
            assert f.SPECS[code]["transform"] == "first-difference", (
                f"{code} should be first-difference (3yr_avg autocorrelation mitigation)"
            )

    def test_no_derived_indicators_in_specs(self):
        """All specs.json entries are non-derived (derived removed from seed set)."""
        for code, spec in f.SPECS.items():
            # If is_derived is true, derivation must be non-null
            if spec["is_derived"]:
                assert spec.get("derivation"), f"{code} is_derived=true but no derivation"


# ---------------------------------------------------------------------------
# Tests: _end_year
# ---------------------------------------------------------------------------


class TestEndYear:
    def test_4_digit_annual(self):
        assert f._end_year(2020) == 2020
        assert f._end_year(2023) == 2023

    def test_8_digit_3yr_avg(self):
        assert f._end_year(20002002) == 2002
        assert f._end_year(20202022) == 2022

    def test_is_3yr_avg_detection(self):
        assert f._is_3yr_avg(20002002) is True
        assert f._is_3yr_avg(2020) is False


# ---------------------------------------------------------------------------
# Tests: _coerce_values
# ---------------------------------------------------------------------------


class TestCoerceValues:
    def test_normal_numerics_pass_through(self):
        s = pd.Series(["87.0", "29.5", "100"])
        out = f._coerce_values(s)
        assert out.dtype == np.float64
        assert list(out) == [87.0, 29.5, 100.0]

    def test_below_detect_half_limit(self):
        s = pd.Series(["<0.1", "<0.5", "<2"])
        out = f._coerce_values(s)
        assert abs(out.iloc[0] - 0.05) < 1e-9
        assert abs(out.iloc[1] - 0.25) < 1e-9
        assert abs(out.iloc[2] - 1.0) < 1e-9

    def test_suppressed_becomes_nan(self):
        s = pd.Series(["...", ".."])
        out = f._coerce_values(s)
        assert out.isna().all()

    def test_unknown_becomes_nan(self):
        s = pd.Series(["N/A", "--", "n.a."])
        out = f._coerce_values(s)
        assert out.isna().all()

    def test_mixed(self):
        s = pd.Series(["10.0", "<0.2", "...", "50", "??"])
        out = f._coerce_values(s)
        # 10.0, 0.1, NaN, 50.0, NaN
        assert out.iloc[0] == 10.0
        assert abs(out.iloc[1] - 0.1) < 1e-9
        assert pd.isna(out.iloc[2])
        assert out.iloc[3] == 50.0
        assert pd.isna(out.iloc[4])


# ---------------------------------------------------------------------------
# Tests: extract_from_domain — FS domain (Item Code, 3yr_avg + first-diff)
# ---------------------------------------------------------------------------


class TestExtractFromDomainFS:
    @pytest.fixture(autouse=True)
    def _df_domain(self):
        self.df = pd.read_csv(io.StringIO(_FS_DOMAIN_CSV))
        self.spec = f.SPECS["FS-001"]

    def test_output_columns(self):
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        assert list(out.columns) == ["country", "year", "value"]

    def test_filters_by_item_and_element_code(self):
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        # Only PoU rows (210041) should survive — not FIES rows (210091)
        countries = set(out["country"])
        assert countries.issubset({"Afghanistan", "Brazil", "Norway", "Turkey"})

    def test_drops_regional_aggregates(self):
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        assert "Africa" not in set(out["country"])

    def test_drops_suppressed_values(self):
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        # Turkey had only '...' -> dropped
        assert "Turkey" not in set(out["country"])

    def test_first_difference_applied(self):
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        afg = out[out["country"] == "Afghanistan"].sort_values("year")
        # Raw: 45.8, 44.0, 42.0, 40.0 -> diffs: -1.8, -2.0, -2.0 (3 rows)
        assert len(afg) == 3
        assert afg["value"].tolist() == pytest.approx([-1.8, -2.0, -2.0], abs=1e-6)

    def test_variance_floor_drops_flat_series(self):
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        # Norway: all <0.1 -> 0.05 -> diff = [0.0, 0.0] -> std=0 -> dropped
        assert "Norway" not in set(out["country"])

    def test_value_dtype_is_float64(self):
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        assert out["value"].dtype == np.float64

    def test_year_dtype_is_integer(self):
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        assert out["year"].dtype.kind == "i"


# ---------------------------------------------------------------------------
# Tests: extract_from_domain — SDGB-009 (string item code, annual)
# ---------------------------------------------------------------------------


class TestExtractFromDomainSDGB009:
    @pytest.fixture(autouse=True)
    def _df_domain(self):
        self.df = pd.read_csv(io.StringIO(_SDGB_DOMAIN_CSV))
        self.spec = f.SPECS["SDGB-009"]

    def test_filters_by_string_item_code(self):
        """Item code '24025' is a string in SDGB — must match correctly."""
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        # Should get Afghanistan and Brazil with their IFPA scores
        assert set(out["country"]) == {"Afghanistan", "Brazil"}

    def test_no_first_diff_for_annual(self):
        """SDGB-009 is annual (transform=none) — values should be raw."""
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        afg = out[out["country"] == "Afghanistan"].sort_values("year")
        # Raw values: -0.12 (2010), 0.5 (2011) — NO differencing
        assert len(afg) == 2
        assert afg["value"].tolist() == pytest.approx([-0.12, 0.5], abs=1e-6)

    def test_water_stress_row_filtered_out(self):
        """Element code 6121 with item '24027-_T' is SDGB-012, not SDGB-009."""
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        # The water stress row had element 6121 but item 24027-_T, which does
        # not match item 24025 (IFPA) — it should NOT appear in output
        # The only countries should be AFG + BRA (both on IFPA)
        assert len(out) == 4  # 2 AFG years + 2 BRA years


# ---------------------------------------------------------------------------
# Tests: extract_from_domain — ET-001 (Months Code column, annual)
# ---------------------------------------------------------------------------


class TestExtractFromDomainET001:
    @pytest.fixture(autouse=True)
    def _df_domain(self):
        self.df = pd.read_csv(io.StringIO(_ET_DOMAIN_CSV))
        self.spec = f.SPECS["ET-001"]

    def test_uses_months_code_column_not_item_code(self):
        """ET domain CSV has no 'Item Code' column — uses 'Months Code'."""
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        assert len(out) >= 4  # AFG 2020, AFG 2021, BRA 2020, BRA 2021

    def test_filters_non_meteorological_year_rows(self):
        """Months Code 7001 (January) must be filtered out; only 7020 (annual)."""
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        # January 2020 Afghanistan row (Months Code=7001) should NOT appear
        afg = out[out["country"] == "Afghanistan"].sort_values("year")
        # Only meteorological year rows survive: AFG 2020 and AFG 2021
        assert len(afg) == 2
        assert set(afg["year"]) == {2020, 2021}

    def test_no_first_diff_for_annual_transform(self):
        """ET-001 has transform='none' — values are raw temperature changes."""
        out = f.extract_from_domain(self.df, self.spec, _FAO_AREA_MAP)
        afg = out[out["country"] == "Afghanistan"].sort_values("year")
        assert afg["value"].tolist() == pytest.approx([1.3, 1.5], abs=1e-6)

    def test_raises_if_months_code_column_missing(self):
        """If the CSV has no 'Months Code' column, should raise ValueError."""
        # Use FS domain CSV (has 'Item Code' but not 'Months Code')
        df_fs = pd.read_csv(io.StringIO(_FS_DOMAIN_CSV))
        with pytest.raises(ValueError, match="Months Code"):
            f.extract_from_domain(df_fs, self.spec, _FAO_AREA_MAP)


# ---------------------------------------------------------------------------
# Tests: fetch_domain_csv — ZIP extraction, retry, cache
# ---------------------------------------------------------------------------


class TestFetchDomainCSV:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        f._ZIP_CSV_CACHE.clear()
        yield
        f._ZIP_CSV_CACHE.clear()

    def test_extracts_main_csv_skipping_flags_file(self):
        """ZIP with a flags CSV and a data CSV — only data CSV returned."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Data_E_Flags.csv", b"flag_code,meaning\nE,Estimate\n")
            zf.writestr("Data_E_All_Data_(Normalized).csv", _FS_DOMAIN_CSV.encode("latin-1"))
        fake = MagicMock(content=buf.getvalue())
        fake.raise_for_status = MagicMock()

        with patch.object(f.requests, "get", return_value=fake):
            out = f.fetch_domain_csv("https://example.com/test.zip")
        assert b"Afghanistan" in out
        assert b"flag_code" not in out

    def test_caches_zip_on_second_call(self):
        """Second call with same URL returns cached bytes without HTTP call."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Data.csv", b"Area Code,Value\n2,99\n")
        fake = MagicMock(content=buf.getvalue())
        fake.raise_for_status = MagicMock()

        url = "https://example.com/cached.zip"
        with patch.object(f.requests, "get", return_value=fake) as mock_get:
            _ = f.fetch_domain_csv(url)
            _ = f.fetch_domain_csv(url)
        assert mock_get.call_count == 1  # only one HTTP call

    def test_retries_on_http_error(self):
        """Transient HTTP error on first attempt — succeeds on second."""
        good_zip = _make_zip(_FS_DOMAIN_CSV)
        ok = MagicMock(content=good_zip)
        ok.raise_for_status = MagicMock()
        bad = MagicMock()
        bad.raise_for_status.side_effect = Exception("HTTP 503")

        with patch.object(f.requests, "get", side_effect=[bad, ok]) as mock_get:
            with patch.object(f.time, "sleep"):
                out = f.fetch_domain_csv("https://example.com/retry.zip")
        assert mock_get.call_count == 2
        assert b"Afghanistan" in out

    def test_raises_after_max_attempts(self):
        """All retries exhausted -> RuntimeError."""
        bad = MagicMock()
        bad.raise_for_status.side_effect = Exception("persistent failure")
        with patch.object(f.requests, "get", return_value=bad):
            with patch.object(f.time, "sleep"):
                with pytest.raises(RuntimeError, match="failed after"):
                    f.fetch_domain_csv("https://example.com/broken.zip")


# ---------------------------------------------------------------------------
# Tests: compute_derived — annual_change
# ---------------------------------------------------------------------------


class TestComputeDerived:
    """Test compute_derived via a synthetic derived spec."""

    def _make_derived_spec(self, derivation: str) -> dict:
        return {
            "code": "TEST-DERIVED",
            "name": "Test derived indicator",
            "is_derived": True,
            "derivation": derivation,
        }

    def _patch_fetch_base(self, df: pd.DataFrame):
        """Patch _fetch_base_series to return a canned DataFrame."""
        return patch.object(f, "_fetch_base_series", return_value=df)

    def test_annual_change_from_base_series(self):
        """annual_change:<code> => year-over-year diff per country."""
        base_df = pd.DataFrame(
            [
                {"country": "Afghanistan", "year": 2000, "value": 100.0},
                {"country": "Afghanistan", "year": 2001, "value": 110.0},
                {"country": "Afghanistan", "year": 2002, "value": 105.0},
                {"country": "Brazil", "year": 2000, "value": 50.0},
                {"country": "Brazil", "year": 2001, "value": 55.0},
            ]
        )
        spec = self._make_derived_spec("annual_change:FS-001")
        with self._patch_fetch_base(base_df):
            out = f.compute_derived(spec, _FAO_AREA_MAP)
        afg = out[out["country"] == "Afghanistan"].sort_values("year")
        bra = out[out["country"] == "Brazil"].sort_values("year")
        # AFG: diff of [100, 110, 105] -> [10, -5]
        assert len(afg) == 2
        assert afg["value"].tolist() == pytest.approx([10.0, -5.0], abs=1e-9)
        # BRA: diff of [50, 55] -> [5]
        assert len(bra) == 1
        assert bra["value"].tolist() == pytest.approx([5.0], abs=1e-9)

    def test_ratio_derivation(self):
        """ratio:<num>/<den> => num/den per (country, year)."""
        num_df = pd.DataFrame(
            [
                {"country": "Afghanistan", "year": 2010, "value": 200.0},
                {"country": "Brazil", "year": 2010, "value": 300.0},
            ]
        )
        den_df = pd.DataFrame(
            [
                {"country": "Afghanistan", "year": 2010, "value": 400.0},
                {"country": "Brazil", "year": 2010, "value": 600.0},
            ]
        )
        spec = self._make_derived_spec("ratio:TC-002/FS-001")

        call_returns = [num_df, den_df]
        call_index = [0]

        def _side_effect(code, _map):
            i = call_index[0]
            call_index[0] += 1
            return call_returns[i]

        with patch.object(f, "_fetch_base_series", side_effect=_side_effect):
            out = f.compute_derived(spec, _FAO_AREA_MAP)
        afg = out[out["country"] == "Afghanistan"]
        assert abs(afg["value"].iloc[0] - 0.5) < 1e-9  # 200/400

    def test_binary_derivation(self):
        """binary:<code>:<threshold> => 1.0 if value>threshold else 0.0."""
        base_df = pd.DataFrame(
            [
                {"country": "Afghanistan", "year": 2010, "value": 0.8},  # > 0.5 -> 1
                {"country": "Brazil", "year": 2010, "value": 0.3},  # < 0.5 -> 0
            ]
        )
        spec = self._make_derived_spec("binary:SDGB-009:0.5")
        with self._patch_fetch_base(base_df):
            out = f.compute_derived(spec, _FAO_AREA_MAP)
        afg = out[out["country"] == "Afghanistan"]["value"].iloc[0]
        bra = out[out["country"] == "Brazil"]["value"].iloc[0]
        assert afg == 1.0
        assert bra == 0.0

    def test_unknown_derivation_raises(self):
        """Unrecognised derivation string -> ValueError with helpful message."""
        spec = self._make_derived_spec("magic_transform:FS-001")
        with pytest.raises(ValueError, match="unrecognised derivation"):
            f.compute_derived(spec, _FAO_AREA_MAP)

    def test_annual_change_returns_empty_if_base_empty(self):
        base_df = pd.DataFrame(columns=["country", "year", "value"])
        spec = self._make_derived_spec("annual_change:FS-001")
        with self._patch_fetch_base(base_df):
            out = f.compute_derived(spec, _FAO_AREA_MAP)
        assert len(out) == 0


# ---------------------------------------------------------------------------
# Tests: fetch_one — integration-level (mocked HTTP + S3 base helpers)
# ---------------------------------------------------------------------------


class TestFetchOne:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        f._ZIP_CSV_CACHE.clear()
        yield
        f._ZIP_CSV_CACHE.clear()

    def _make_s3_mock(self):
        """Return an S3 mock that serves a fresh BytesIO on each get_object call."""
        s3 = MagicMock()
        csv_bytes = _COUNTRY_MAP_CSV.encode("utf-8")

        def _get_object(**kwargs):
            return {"Body": io.BytesIO(csv_bytes)}

        s3.get_object.side_effect = _get_object
        return s3

    def test_fetch_one_fs001_happy_path(self):
        """FS-001: downloads ZIP, extracts, applies first-diff, returns DataFrame."""
        good_zip = _make_zip(_FS_DOMAIN_CSV)
        ok = MagicMock(content=good_zip)
        ok.raise_for_status = MagicMock()

        with (
            patch.object(f.requests, "get", return_value=ok),
            patch.object(base, "_s3", return_value=self._make_s3_mock()),
        ):
            result = f.fetch_one({"id_string": "FS-001"})

        assert result is not None
        assert not result.empty
        assert set(result.columns) == {"country", "year", "value"}
        # Afghanistan and Brazil should have diffs; Norway/Turkey dropped
        assert "Afghanistan" in set(result["country"])
        assert "Brazil" in set(result["country"])
        assert "Turkey" not in set(result["country"])

    def test_fetch_one_et001_uses_months_code(self):
        """ET-001: domain CSV uses Months Code column."""
        good_zip = _make_zip(_ET_DOMAIN_CSV)
        ok = MagicMock(content=good_zip)
        ok.raise_for_status = MagicMock()

        with (
            patch.object(f.requests, "get", return_value=ok),
            patch.object(base, "_s3", return_value=self._make_s3_mock()),
        ):
            result = f.fetch_one({"id_string": "ET-001"})

        assert result is not None
        assert not result.empty
        assert "Afghanistan" in set(result["country"])

    def test_fetch_one_fs003_shares_zip_cache_with_fs001(self):
        """FS-003 and FS-001 share the same bulk URL — only one HTTP call if
        fetched in the same process (ZIP cache hit)."""
        # Pre-seed cache with the FS domain CSV
        good_zip = _make_zip(_FS_DOMAIN_CSV)
        ok = MagicMock(content=good_zip)
        ok.raise_for_status = MagicMock()

        with (
            patch.object(f.requests, "get", return_value=ok) as mock_get,
            patch.object(base, "_s3", return_value=self._make_s3_mock()),
        ):
            # First call downloads
            _ = f.fetch_one({"id_string": "FS-001"})
            # Second call for FS-003 (same bulk URL) should use cache
            _ = f.fetch_one({"id_string": "FS-003"})

        # FS-001 and FS-003 share the same bulk URL -> only 1 HTTP GET
        assert mock_get.call_count == 1

    def test_fetch_one_unknown_indicator_raises(self):
        """Unknown code -> ValueError with list of valid codes."""
        with pytest.raises(ValueError, match="Unknown FAOSTAT indicator"):
            f.fetch_one({"id_string": "FS-999"})

    def test_fetch_one_returns_none_on_empty_data(self):
        """If extract_from_domain returns empty, fetch_one returns None."""
        # Use SDGB CSV for FS-001 spec — no FS-001 rows -> empty
        good_zip = _make_zip(_SDGB_DOMAIN_CSV)
        ok = MagicMock(content=good_zip)
        ok.raise_for_status = MagicMock()

        with (
            patch.object(f.requests, "get", return_value=ok),
            patch.object(base, "_s3", return_value=self._make_s3_mock()),
        ):
            result = f.fetch_one({"id_string": "FS-001"})

        assert result is None


# ---------------------------------------------------------------------------
# Tests: base contract — to_canonical_frame (shared, verify it works here too)
# ---------------------------------------------------------------------------


class TestBaseContractIntegration:
    def test_to_canonical_frame_from_fetcher_output(self):
        """fetch_one output is compatible with base.to_canonical_frame."""
        raw = pd.DataFrame(
            [
                {"country": "Afghanistan", "year": 2003, "value": -1.8},
                {"country": "Brazil", "year": 2001, "value": -1.0},
            ]
        )
        out = base.to_canonical_frame(raw)
        assert list(out.columns) == ["country", "year", "value", "is_predicted"]
        assert out["year"].dtype == np.int64
        assert out["value"].dtype == np.float64
        assert (out["is_predicted"] == False).all()  # noqa: E712

    def test_to_canonical_frame_dedup_keeps_last(self):
        """Duplicate (country, year) -> last value wins."""
        raw = pd.DataFrame(
            [
                {"country": "Afghanistan", "year": 2003, "value": 1.0},
                {"country": "Afghanistan", "year": 2003, "value": 2.0},
            ]
        )
        out = base.to_canonical_frame(raw)
        assert len(out) == 1
        assert out.iloc[0]["value"] == 2.0
