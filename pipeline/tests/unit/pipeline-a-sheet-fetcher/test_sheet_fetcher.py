"""
Unit tests for pipeline-a-sheet-fetcher (#240, 2026-04-19).

Covers:
- Multi-sheet XLSX → per-provider CSVs + combined indicators.json
- Provider-specific columns (fao_domain_code, wb_indicator_code, etc.)
  pass through without a per-provider code change
- Each indicator is tagged with its `provider` field in the output JSON
- Legacy single-sheet ('phase_2_indicators') XLSX still works unchanged
- Sheets starting with '_' or named 'archive'/'meta' are skipped
- Rows missing essential columns (id_string/numeric_id) are silently
  dropped without failing the whole sheet
- Legacy combined CSV is always written for backward-compat with
  consumers (scdi-finder Batch) that pre-date per-provider sheets

The Lambda uses boto3 S3; we mock via a MagicMock + module-level
patching so no real AWS calls happen.
"""

import importlib.util
import io
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openpyxl import Workbook

_LAMBDAS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas"
_SHEET_FETCHER_PATH = _LAMBDAS_DIR / "pipeline-a-sheet-fetcher" / "lambda_function.py"


def _build_xlsx(sheets: dict[str, list[dict]]) -> bytes:
    """Build an in-memory XLSX with the given sheets.

    `sheets`: mapping of sheet_name -> list of row dicts. Each sheet's
    column order is taken from the union of keys across its rows (with
    the common columns first, then whatever else appears).
    """
    wb = Workbook()
    # Default sheet is the first one we add; remove the auto-created
    # 'Sheet' if the caller supplied a name.
    default_sheet = wb.active
    wb.remove(default_sheet)

    for sheet_name, rows in sheets.items():
        ws = wb.create_sheet(title=sheet_name)
        if not rows:
            ws.append([])
            continue
        # Build a stable column ordering: common cols first, then the
        # rest alphabetically.
        all_cols_set: set[str] = set()
        for r in rows:
            all_cols_set.update(r.keys())
        common_first = [
            c
            for c in (
                "id_string",
                "numeric_id",
                "name",
                "status",
                "category",
                "description",
                "license",
                "hidden_source",
            )
            if c in all_cols_set
        ]
        remaining = sorted(all_cols_set - set(common_first))
        cols = common_first + remaining
        ws.append(cols)
        for r in rows:
            ws.append([r.get(c) for c in cols])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_ENV = {
    "INPUT_BUCKET": "test-bucket",
    "INPUT_KEY": "test.xlsx",
    "OUTPUT_BUCKET": "test-bucket",
    "OUTPUT_KEY": "indicators/indicators.json",
    "INDICATOR_MAP_KEY": "pipeline-A-indicator-extractor/input/indicator_map.csv",
}


@pytest.fixture(autouse=True)
def _env_vars(monkeypatch):
    """Sheet-fetcher reads os.environ inside lambda_handler (not at
    module load), so the env vars must be set for the handler call too.
    autouse fixture = every test in this file gets these."""
    for k, v in _ENV.items():
        monkeypatch.setenv(k, v)


def _load_fetcher(xlsx_bytes: bytes):
    """Load the fetcher module with boto3.s3 mocked to return `xlsx_bytes`."""
    s3_client = MagicMock()
    s3_client.get_object.return_value = {"Body": io.BytesIO(xlsx_bytes)}

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = MagicMock(return_value=s3_client)

    with patch.dict(sys.modules, {"boto3": boto3_stub}):
        spec = importlib.util.spec_from_file_location("sheet_fetcher", str(_SHEET_FETCHER_PATH))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod, s3_client


def _get_output_json(s3_client, key: str = "indicators/indicators.json") -> dict:
    """Extract the JSON body put_object'd to `key`, parsed."""
    for call in s3_client.put_object.call_args_list:
        if call.kwargs.get("Key") == key:
            return json.loads(call.kwargs["Body"])
    raise AssertionError(f"no put_object call to Key={key!r}")


def _get_output_csv(s3_client, key_substring: str) -> str:
    """Extract the CSV body put_object'd to a key containing `key_substring`."""
    for call in s3_client.put_object.call_args_list:
        if key_substring in call.kwargs.get("Key", ""):
            return call.kwargs["Body"]
    raise AssertionError(f"no put_object call to a Key containing {key_substring!r}")


# ---------------------------------------------------------------------- #
# Tests                                                                  #
# ---------------------------------------------------------------------- #


def test_legacy_single_sheet_still_works():
    """The legacy `phase_2_indicators` sheet name is mapped to provider 'WB'
    and its indicators flow through with no extra config."""
    xlsx = _build_xlsx(
        {
            "phase_2_indicators": [
                {
                    "id_string": "NY.GDP.MKTP.CD",
                    "numeric_id": 1,
                    "name": "GDP",
                    "status": "process",
                    "category": "Economic",
                },
                {
                    "id_string": "SP.POP.TOTL",
                    "numeric_id": 2,
                    "name": "Population",
                    "status": "process",
                    "category": "Demographic",
                },
            ],
        }
    )
    mod, s3 = _load_fetcher(xlsx)
    result = mod.lambda_handler({}, None)

    assert result["status"] == "Success"
    assert result["indicators_fetched"] == 2
    assert result["providers"] == ["WB"]

    out = _get_output_json(s3)
    assert out["metadata"]["provider_count"] == 1
    assert out["metadata"]["total_indicators"] == 2
    assert out["metadata"]["active_indicators"] == 2
    # Every indicator tagged with provider='WB'
    for ind in out["indicators"]:
        assert ind["provider"] == "WB"


def test_multi_sheet_produces_per_provider_data():
    """XLSX with two sheets (WB, FAOSTAT) yields two providers, each
    indicator tagged with its provider."""
    xlsx = _build_xlsx(
        {
            "WB": [
                {
                    "id_string": "NY.GDP.MKTP.CD",
                    "numeric_id": 1,
                    "name": "GDP",
                    "status": "process",
                    "wb_indicator_code": "NY.GDP.MKTP.CD",
                },
            ],
            "FAOSTAT": [
                {
                    "id_string": "FA-01",
                    "numeric_id": 59,
                    "name": "PoU",
                    "status": "process",
                    "fao_domain_code": "FS",
                    "fao_item_code": 21010,
                    "fao_element_code": 6121,
                },
                {
                    "id_string": "FA-04",
                    "numeric_id": 62,
                    "name": "Cereal Import Dependency Ratio",
                    "status": "process",
                    "fao_domain_code": "FS",
                    "fao_item_code": 21013,
                    "fao_element_code": 6128,
                },
            ],
        }
    )
    mod, s3 = _load_fetcher(xlsx)
    result = mod.lambda_handler({}, None)

    assert result["indicators_fetched"] == 3
    assert set(result["providers"]) == {"WB", "FAOSTAT"}

    out = _get_output_json(s3)
    # Providers section
    providers_by_name = {p["name"]: p for p in out["providers"]}
    assert set(providers_by_name) == {"WB", "FAOSTAT"}
    assert len(providers_by_name["WB"]["indicators"]) == 1
    assert len(providers_by_name["FAOSTAT"]["indicators"]) == 2

    # Every indicator tagged with its provider
    for ind in out["indicators"]:
        if ind["id_string"].startswith("FA-"):
            assert ind["provider"] == "FAOSTAT"
        else:
            assert ind["provider"] == "WB"


def test_provider_specific_columns_pass_through():
    """FAOSTAT-specific columns (fao_domain_code, fao_item_code,
    fao_element_code) must survive to the output JSON, preserving
    integer types for numeric codes.

    This is the core #240 acceptance test: adding a new provider should
    be a SHEET addition, not a code change."""
    xlsx = _build_xlsx(
        {
            "FAOSTAT": [
                {
                    "id_string": "FA-01",
                    "numeric_id": 59,
                    "name": "PoU",
                    "status": "process",
                    "fao_domain_code": "FS",
                    "fao_item_code": 21010,
                    "fao_element_code": 6121,
                    "fao_unit": "percent",
                },
            ],
        }
    )
    mod, s3 = _load_fetcher(xlsx)
    mod.lambda_handler({}, None)

    out = _get_output_json(s3)
    ind = out["indicators"][0]
    assert ind["id_string"] == "FA-01"
    assert ind["fao_domain_code"] == "FS"
    assert ind["fao_item_code"] == 21010  # int preserved, not stringified
    assert ind["fao_element_code"] == 6121
    assert ind["fao_unit"] == "percent"
    assert ind["provider"] == "FAOSTAT"


def test_skipped_sheets_do_not_appear():
    """Sheets starting with '_' or named 'archive'/'meta' are skipped."""
    xlsx = _build_xlsx(
        {
            "_scratch": [
                {"id_string": "X", "numeric_id": 999, "name": "scratch", "status": "process"},
            ],
            "archive": [
                {"id_string": "Y", "numeric_id": 998, "name": "archived", "status": "process"},
            ],
            "WB": [
                {"id_string": "NY.GDP.MKTP.CD", "numeric_id": 1, "name": "GDP", "status": "process"},
            ],
        }
    )
    mod, s3 = _load_fetcher(xlsx)
    result = mod.lambda_handler({}, None)

    assert result["providers"] == ["WB"]
    assert result["indicators_fetched"] == 1
    out = _get_output_json(s3)
    assert {ind["id_string"] for ind in out["indicators"]} == {"NY.GDP.MKTP.CD"}


def test_rows_with_missing_essentials_are_dropped_silently():
    """Rows missing id_string or numeric_id (blank rows in the XLSX)
    should be skipped without failing the whole sheet."""
    xlsx = _build_xlsx(
        {
            "WB": [
                {"id_string": "NY.GDP.MKTP.CD", "numeric_id": 1, "name": "GDP", "status": "process"},
                {"id_string": None, "numeric_id": 2, "name": "missing id", "status": "process"},  # row dropped
                {
                    "id_string": "SP.POP.TOTL",
                    "numeric_id": None,
                    "name": "missing numeric_id",
                    "status": "process",
                },  # row dropped
                {"id_string": "NE.EXP.GNFS.CD", "numeric_id": 3, "name": "Exports", "status": "process"},
            ],
        }
    )
    mod, s3 = _load_fetcher(xlsx)
    result = mod.lambda_handler({}, None)

    # 2 of 4 rows kept; missing essentials dropped
    assert result["indicators_fetched"] == 2
    out = _get_output_json(s3)
    assert {ind["id_string"] for ind in out["indicators"]} == {"NY.GDP.MKTP.CD", "NE.EXP.GNFS.CD"}


def test_per_provider_csv_emitted_for_each_sheet():
    """Each non-legacy sheet produces its own indicator_map_<provider>.csv."""
    xlsx = _build_xlsx(
        {
            "WB": [
                {"id_string": "NY.GDP.MKTP.CD", "numeric_id": 1, "name": "GDP", "status": "process"},
            ],
            "FAOSTAT": [
                {"id_string": "FA-01", "numeric_id": 59, "name": "PoU", "status": "process"},
            ],
        }
    )
    mod, s3 = _load_fetcher(xlsx)
    mod.lambda_handler({}, None)

    wb_csv = _get_output_csv(s3, "indicator_map_wb.csv")
    fao_csv = _get_output_csv(s3, "indicator_map_faostat.csv")

    assert "NY.GDP.MKTP.CD,1" in wb_csv
    assert "FA-01,59" in fao_csv
    assert "FA-01" not in wb_csv  # providers are isolated per CSV


def test_legacy_combined_csv_contains_all_providers():
    """The legacy `indicator_map.csv` (consumed by scdi-finder Batch,
    which is not provider-aware) must contain every indicator across
    all providers."""
    xlsx = _build_xlsx(
        {
            "WB": [
                {"id_string": "NY.GDP.MKTP.CD", "numeric_id": 1, "name": "GDP", "status": "process"},
            ],
            "FAOSTAT": [
                {"id_string": "FA-01", "numeric_id": 59, "name": "PoU", "status": "process"},
            ],
        }
    )
    mod, s3 = _load_fetcher(xlsx)
    mod.lambda_handler({}, None)

    legacy_csv = _get_output_csv(s3, "indicator_map.csv")
    assert "NY.GDP.MKTP.CD,1" in legacy_csv
    assert "FA-01,59" in legacy_csv


def test_no_eligible_sheets_raises():
    """If every sheet is skipped (archive/meta/_prefix), raise loudly."""
    xlsx = _build_xlsx(
        {
            "_scratch": [
                {"id_string": "X", "numeric_id": 999, "name": "scratch", "status": "process"},
            ],
            "archive": [
                {"id_string": "Y", "numeric_id": 998, "name": "archived", "status": "process"},
            ],
        }
    )
    mod, _ = _load_fetcher(xlsx)
    with pytest.raises(ValueError, match="No eligible sheets"):
        mod.lambda_handler({}, None)


def test_provider_name_normalization():
    """Sheet names with spaces/dashes/lowercase get normalized to
    UPPER_SNAKE provider names so the per-provider CSV filenames are
    stable."""
    xlsx = _build_xlsx(
        {
            "v-dem": [
                {
                    "id_string": "v2x_polyarchy",
                    "numeric_id": 100,
                    "name": "EDI",
                    "status": "process",
                    "vdem_var_name": "v2x_polyarchy",
                },
            ],
        }
    )
    mod, s3 = _load_fetcher(xlsx)
    result = mod.lambda_handler({}, None)
    assert result["providers"] == ["V_DEM"]
    # CSV filename uses lowercase provider
    _get_output_csv(s3, "indicator_map_v_dem.csv")
    # JSON entry uses the normalized provider
    out = _get_output_json(s3)
    assert out["indicators"][0]["provider"] == "V_DEM"
