"""Unit tests for validate_indicator_catalog.py pure functions.

Covers:
  - _is_skip() — sheet-name skip logic
  - _validate_essentials() — essential column presence + per-row checks
  - _validate_provider_specific() — FAOSTAT/FAO column requirements
  - _validate_no_duplicate_numeric_ids() — cross-sheet PK uniqueness
  - Multiple errors surface together (not fail-fast)

Skipped:
  - validate() + main() — both require a real .xlsx file on disk (pandas
    ExcelFile / openpyxl). Covered by integration tests against the real
    catalog. The internal rule functions (_validate_essentials etc.) are
    fully tested here without any file I/O.

#373 script test coverage audit.
"""
from __future__ import annotations

import sys
import pathlib

import pandas as pd
import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_indicator_catalog as vic  # noqa: E402


# ===========================================================================
# Helpers
# ===========================================================================

def _df(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame whose columns are the union of all keys in rows."""
    return pd.DataFrame(rows)


# ===========================================================================
# _is_skip()
# ===========================================================================

class TestIsSkip:

    def test_archive_skipped(self):
        assert vic._is_skip("archive") is True

    def test_meta_skipped(self):
        assert vic._is_skip("meta") is True

    def test_notes_skipped(self):
        assert vic._is_skip("notes") is True

    def test_readme_skipped(self):
        assert vic._is_skip("readme") is True

    def test_case_insensitive(self):
        assert vic._is_skip("ARCHIVE") is True
        assert vic._is_skip("Meta") is True

    def test_underscore_prefix_skipped(self):
        assert vic._is_skip("_internal") is True
        assert vic._is_skip("_") is True

    def test_normal_sheets_not_skipped(self):
        for name in ("FAOSTAT", "WB", "VDem", "ILOSTAT", "Sheet1"):
            assert vic._is_skip(name) is False


# ===========================================================================
# _validate_essentials()
# ===========================================================================

class TestValidateEssentials:

    def test_valid_row_produces_no_errors(self):
        df = _df([{"id_string": "wb_gdp", "numeric_id": 1,
                   "name": "GDP per capita", "status": "process"}])
        errors = vic._validate_essentials(df, "WB")
        assert errors == []

    def test_missing_essential_column_error(self):
        df = _df([{"id_string": "x", "name": "y", "status": "process"}])
        # numeric_id column entirely absent
        errors = vic._validate_essentials(df, "WB")
        assert any("missing essential columns" in e for e in errors)

    def test_blank_id_string_error(self):
        df = _df([{"id_string": "", "numeric_id": 1,
                   "name": "X", "status": "process"}])
        errors = vic._validate_essentials(df, "WB")
        assert any("id_string missing" in e for e in errors)

    def test_whitespace_only_id_string_error(self):
        df = _df([{"id_string": "   ", "numeric_id": 1,
                   "name": "X", "status": "process"}])
        errors = vic._validate_essentials(df, "WB")
        assert any("id_string missing" in e for e in errors)

    def test_missing_numeric_id_error(self):
        df = _df([{"id_string": "x", "numeric_id": float("nan"),
                   "name": "X", "status": "process"}])
        errors = vic._validate_essentials(df, "WB")
        assert any("numeric_id missing" in e for e in errors)

    def test_non_integer_numeric_id_error(self):
        df = _df([{"id_string": "x", "numeric_id": "abc",
                   "name": "X", "status": "process"}])
        errors = vic._validate_essentials(df, "WB")
        assert any("not an integer" in e for e in errors)

    def test_float_numeric_id_is_accepted(self):
        """Pandas reads integers from Excel as float64 (e.g., 1.0). Accept them."""
        df = _df([{"id_string": "x", "numeric_id": 1.0,
                   "name": "X", "status": "process"}])
        errors = vic._validate_essentials(df, "WB")
        # 1.0 -> int(1.0) = 1 without error
        assert not any("not an integer" in e for e in errors)

    def test_blank_status_error(self):
        df = _df([{"id_string": "x", "numeric_id": 1,
                   "name": "X", "status": float("nan")}])
        errors = vic._validate_essentials(df, "WB")
        assert any("status is blank" in e for e in errors)

    def test_invalid_status_value_error(self):
        df = _df([{"id_string": "x", "numeric_id": 1,
                   "name": "X", "status": "active"}])
        errors = vic._validate_essentials(df, "WB")
        assert any("not in" in e for e in errors)

    def test_valid_statuses_all_accepted(self):
        for s in ("process", "hold", "deprecated", "planned"):
            df = _df([{"id_string": "x", "numeric_id": 1, "name": "X", "status": s}])
            errors = vic._validate_essentials(df, "WB")
            assert errors == [], f"Status {s!r} should be valid"

    def test_multiple_errors_surface_together(self):
        """Two bad rows should each contribute errors, not abort after first."""
        df = _df([
            {"id_string": "", "numeric_id": 1, "name": "X", "status": "process"},
            {"id_string": "y", "numeric_id": "bad", "name": "Y", "status": "active"},
        ])
        errors = vic._validate_essentials(df, "WB")
        # Row 1 error: id_string missing
        assert any("id_string missing" in e for e in errors)
        # Row 2 errors: numeric_id not int + invalid status
        assert any("not an integer" in e for e in errors)
        assert any("not in" in e for e in errors)
        assert len(errors) >= 3

    def test_multiple_valid_rows_no_errors(self):
        df = _df([
            {"id_string": "wb_a", "numeric_id": 1, "name": "A", "status": "process"},
            {"id_string": "wb_b", "numeric_id": 2, "name": "B", "status": "hold"},
            {"id_string": "wb_c", "numeric_id": 3, "name": "C", "status": "deprecated"},
        ])
        errors = vic._validate_essentials(df, "WB")
        assert errors == []


# ===========================================================================
# _validate_provider_specific()
# ===========================================================================

class TestValidateProviderSpecific:

    def _fao_row(self, domain="Q", item=1234, element=5110):
        return {
            "id_string": "fao_x", "numeric_id": 1, "name": "X", "status": "process",
            "fao_domain_code": domain, "fao_item_code": item,
            "fao_element_code": element,
        }

    def test_valid_faostat_row_no_errors(self):
        df = _df([self._fao_row()])
        errors = vic._validate_provider_specific(df, "FAOSTAT")
        assert errors == []

    def test_fao_alias_same_as_faostat(self):
        df = _df([self._fao_row()])
        errors_fao = vic._validate_provider_specific(df, "FAO")
        errors_faostat = vic._validate_provider_specific(df, "FAOSTAT")
        assert errors_fao == errors_faostat

    def test_missing_fao_domain_code_column(self):
        row = self._fao_row()
        del row["fao_domain_code"]
        df = _df([row])
        errors = vic._validate_provider_specific(df, "FAOSTAT")
        assert any("fao_domain_code" in e and "missing" in e for e in errors)

    def test_blank_fao_domain_code_error(self):
        row = self._fao_row(domain=float("nan"))
        df = _df([row])
        errors = vic._validate_provider_specific(df, "FAOSTAT")
        assert any("fao_domain_code" in e and "blank" in e for e in errors)

    def test_blank_fao_item_code_error(self):
        row = self._fao_row(item=float("nan"))
        df = _df([row])
        errors = vic._validate_provider_specific(df, "FAOSTAT")
        assert any("fao_item_code" in e and "blank" in e for e in errors)

    def test_non_integer_fao_item_code_error(self):
        row = self._fao_row(item="not_an_int")
        df = _df([row])
        errors = vic._validate_provider_specific(df, "FAOSTAT")
        assert any("fao_item_code" in e and "not an integer" in e for e in errors)

    def test_non_integer_fao_element_code_error(self):
        row = self._fao_row(element="5110x")
        df = _df([row])
        errors = vic._validate_provider_specific(df, "FAOSTAT")
        assert any("fao_element_code" in e and "not an integer" in e for e in errors)

    def test_float_fao_codes_accepted(self):
        """Excel reads ints as float64; e.g. 1234.0 must be accepted."""
        df = _df([self._fao_row(item=1234.0, element=5110.0)])
        errors = vic._validate_provider_specific(df, "FAOSTAT")
        assert errors == []

    def test_unknown_sheet_no_errors(self):
        """Non-FAOSTAT/non-FAO sheet: no provider-specific rules -> no errors."""
        df = _df([{"id_string": "vd", "numeric_id": 1, "name": "X", "status": "process"}])
        errors = vic._validate_provider_specific(df, "VDem")
        assert errors == []

    def test_multiple_faostat_errors_surface_together(self):
        df = _df([
            self._fao_row(item=float("nan"), element="bad"),
        ])
        errors = vic._validate_provider_specific(df, "FAOSTAT")
        assert any("fao_item_code" in e for e in errors)
        assert any("fao_element_code" in e for e in errors)


# ===========================================================================
# _validate_no_duplicate_numeric_ids()
# ===========================================================================

class TestValidateNoDuplicateNumericIds:

    def test_no_duplicates_returns_empty(self):
        rows = [("WB", 2, 1), ("WB", 3, 2), ("FAOSTAT", 2, 3)]
        errors = vic._validate_no_duplicate_numeric_ids(rows)
        assert errors == []

    def test_duplicate_within_sheet_detected(self):
        rows = [("WB", 2, 5), ("WB", 3, 5)]
        errors = vic._validate_no_duplicate_numeric_ids(rows)
        assert len(errors) == 1
        assert "5" in errors[0]

    def test_duplicate_across_sheets_detected(self):
        rows = [("WB", 2, 10), ("FAOSTAT", 3, 10)]
        errors = vic._validate_no_duplicate_numeric_ids(rows)
        assert len(errors) == 1
        assert "WB" in errors[0]
        assert "FAOSTAT" in errors[0]

    def test_none_numeric_id_skipped(self):
        """None values (from blank cells) must be silently skipped."""
        rows = [("WB", 2, None), ("WB", 3, None)]
        errors = vic._validate_no_duplicate_numeric_ids(rows)
        assert errors == []

    def test_multiple_duplicates_all_surfaced(self):
        """Three duplicate IDs -> two error messages (second+third occurrences)."""
        rows = [("S1", 2, 99), ("S2", 3, 99), ("S3", 4, 99)]
        errors = vic._validate_no_duplicate_numeric_ids(rows)
        # First seen: S1. Second and third duplicates -> 2 errors.
        assert len(errors) == 2

    def test_first_reference_in_error_message(self):
        rows = [("SheetA", 2, 7), ("SheetB", 5, 7)]
        errors = vic._validate_no_duplicate_numeric_ids(rows)
        assert len(errors) == 1
        # Error message references first-seen location
        assert "SheetA" in errors[0]
        assert "SheetB" in errors[0]

    def test_empty_rows_returns_empty(self):
        assert vic._validate_no_duplicate_numeric_ids([]) == []


# ===========================================================================
# Constants sanity
# ===========================================================================

class TestConstants:

    def test_essential_columns_set(self):
        assert vic._ESSENTIAL_COLUMNS == {"id_string", "numeric_id", "name", "status"}

    def test_valid_statuses_set(self):
        assert vic._VALID_STATUSES == {"process", "hold", "deprecated", "planned"}

    def test_skip_sheets_set(self):
        for s in ("archive", "meta", "notes", "readme"):
            assert s in vic._SKIP_SHEETS

    def test_faostat_provider_columns_registered(self):
        assert "FAOSTAT" in vic._PROVIDER_REQUIRED_COLUMNS
        cols = [c for c, _ in vic._PROVIDER_REQUIRED_COLUMNS["FAOSTAT"]]
        assert "fao_domain_code" in cols
        assert "fao_item_code" in cols
        assert "fao_element_code" in cols
