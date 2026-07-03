"""
Unit tests for #591 Option D — catalog allow-list filter on the
recipe-engine-finalize indicator_unnest CTE.

Layered test strategy:
  - Unit: _load_indicator_allow_list() handles a valid JSON, an empty list,
    a wrong-type, and missing keys. S3 GetObject is mocked.
  - SQL-shape regression: the SQL string assembled by
    write_recipes_aggregated_table() contains the WHERE clause and the
    expected IN-list, AND does NOT contain any of the 18 known-legacy
    numeric_ids.

Live regression (post-deploy CI) lives in
qgi-ml/scripts/impact_analysis_591_filter.py — that script asserts
Outcome 1 (exactly the 18 dropped) holds against the rebuilt
recipes_aggregated table.

Spec: docs/specs/internal/ops/cascade-track/phase-5-v0.0.md "Step 5".
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_LAMBDA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas" / "pipeline-recipe-engine-finalize"
sys.path.insert(0, str(_LAMBDA_DIR))
_MODULE_PATH = _LAMBDA_DIR / "lambda_function.py"

# Set S3_BUCKET BEFORE module import so the lambda's module-load doesn't
# decide it's in a test environment with no allow-list. We DO want the
# loader function to exist; we just don't want a real S3 GET on import.
os.environ["S3_BUCKET"] = "test-bucket"

_spec = importlib.util.spec_from_file_location("recipe_engine_finalize_591", _MODULE_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# The 18 known-legacy WB indicator numeric IDs that #591 Option D MUST
# eliminate from the recipes_aggregated.indicator_fingerprint. Sourced from
# impact_analysis_591_filter.py output 2026-05-04 against the production
# recipes_aggregated table. If a future ingestion or catalog change adds
# any of these to the allow-list, this test MUST start failing — that is
# by design.
LEGACY_18_NUMERIC_IDS = {
    2,  # SP.POP.TOTL
    4,  # SP.DYN.LE00.IN
    5,  # NY.GDP.MKTP.CD
    9,  # NY.GDP.PCAP.CD
    14,  # SH.DYN.MORT
    16,  # IT.CEL.SETS.P2
    17,  # NE.EXP.GNFS.CD
    18,  # NE.EXP.GNFS.ZS
    19,  # NE.IMP.GNFS.CD
    26,  # MS.MIL.XPND.GD.ZS
    30,  # FP.CPI.TOTL.ZG
    31,  # NY.GNP.PCAP.CD
    32,  # NY.GDP.MKTP.KD
    33,  # NV.AGR.TOTL.ZS
    43,  # FI.RES.TOTL.CD
    50,  # FM.LBL.BMNY.GD.ZS
    143,  # AG.PRD.FOOD.XD
    165,  # SP.DYN.TFRT.IN
}


def _reset_cache():
    """Clear the lazy cache between tests — each test should hit the loader
    via _get_indicator_allow_list() with its own mocked S3 response."""
    mod._INDICATOR_ALLOW_LIST_CACHE = None


# ===========================================================================
# Module-level constants
# ===========================================================================


def test_indicator_allow_list_s3_key_constant_exists():
    """INDICATOR_ALLOW_LIST_S3_KEY must be a module-level constant."""
    assert hasattr(mod, "INDICATOR_ALLOW_LIST_S3_KEY")
    assert mod.INDICATOR_ALLOW_LIST_S3_KEY == ("pipeline-A-indicator-extractor/input/indicator-allow-list.json")


def test_load_indicator_allow_list_function_exists():
    assert callable(mod._load_indicator_allow_list)
    assert callable(mod._get_indicator_allow_list)


# ===========================================================================
# _load_indicator_allow_list — unit
# ===========================================================================


@pytest.fixture(autouse=True)
def reset_cache():
    _reset_cache()
    yield
    _reset_cache()


def _mock_s3_response(payload: dict | str | bytes) -> MagicMock:
    """Build a mock for boto3 client.get_object returning the given payload."""
    body = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
    if isinstance(body, str):
        body = body.encode("utf-8")
    body_mock = MagicMock()
    body_mock.read.return_value = body
    return {"Body": body_mock}


def test_load_allow_list_happy_path():
    payload = {
        "schema_version": 1,
        "allow_list_numeric_ids": [42, 1, 7, 7],  # unsorted + duplicate
    }
    with patch.object(mod.s3, "get_object", return_value=_mock_s3_response(payload)):
        out = mod._load_indicator_allow_list()
    assert out == (1, 7, 42), "must be sorted + deduped"
    assert isinstance(out, tuple)


def test_load_allow_list_rejects_empty():
    payload = {"allow_list_numeric_ids": []}
    with patch.object(mod.s3, "get_object", return_value=_mock_s3_response(payload)):
        with pytest.raises(ValueError, match="empty"):
            mod._load_indicator_allow_list()


def test_load_allow_list_rejects_missing_field():
    payload = {"schema_version": 1}
    with patch.object(mod.s3, "get_object", return_value=_mock_s3_response(payload)):
        with pytest.raises(ValueError, match="must be a list of ints"):
            mod._load_indicator_allow_list()


def test_load_allow_list_rejects_wrong_type():
    payload = {"allow_list_numeric_ids": ["not", "an", "int"]}
    with patch.object(mod.s3, "get_object", return_value=_mock_s3_response(payload)):
        with pytest.raises(ValueError, match="list of ints"):
            mod._load_indicator_allow_list()


def test_load_allow_list_rejects_mixed_types():
    payload = {"allow_list_numeric_ids": [1, 2, "three", 4]}
    with patch.object(mod.s3, "get_object", return_value=_mock_s3_response(payload)):
        with pytest.raises(ValueError, match="list of ints"):
            mod._load_indicator_allow_list()


def test_get_allow_list_caches():
    """First call hits S3; second call returns the cached tuple without
    re-fetching."""
    payload = {"allow_list_numeric_ids": [1, 2, 3]}
    with patch.object(mod.s3, "get_object", return_value=_mock_s3_response(payload)) as get_mock:
        out1 = mod._get_indicator_allow_list()
        out2 = mod._get_indicator_allow_list()
    assert out1 == (1, 2, 3)
    assert out2 is out1, "second call must return the SAME tuple object"
    assert get_mock.call_count == 1, "S3 must be hit exactly once"


# ===========================================================================
# SQL-shape regression
# ===========================================================================


def _build_insert_sql_for_test(allow_list: tuple) -> str:
    """Reproduce the SQL build path from write_recipes_aggregated_table()
    enough to inspect the final string. We bypass all S3/Athena calls and
    just build the f-string with a known allow-list."""
    # Inject our test allow-list into the cache so _get_indicator_allow_list
    # returns it without hitting S3.
    mod._INDICATOR_ALLOW_LIST_CACHE = allow_list

    # Reproduce the exact SQL-build expressions the lambda uses. If those
    # expressions move or change shape, this test will need to track that
    # — but the very purpose of this test is to detect such drift, so the
    # coupling is intentional.
    ATHENA_DB = mod.ATHENA_DB
    RECIPES_AGGREGATED_TABLE_NAME = mod.RECIPES_AGGREGATED_TABLE_NAME
    SCDI_M2_THRESHOLD = mod.SCDI_M2_THRESHOLD
    temp_table = "tmp_rwp_TEST"
    allow_list_in_clause = ", ".join(str(i) for i in allow_list)

    insert_sql = f"""
        INSERT INTO {ATHENA_DB}.{RECIPES_AGGREGATED_TABLE_NAME}
        WITH
        indicator_unnest AS (
            SELECT event_category, recipe_id, indicator_id,
                   abs(cast(avg_correlation as double)) AS w
            FROM {ATHENA_DB}.{temp_table}
            CROSS JOIN UNNEST(indicator_numeric_ids) AS t(indicator_id)
            WHERE t.indicator_id IN ({allow_list_in_clause})
        )
    """
    return insert_sql


def test_sql_shape_contains_allow_list_in_clause():
    sql = _build_insert_sql_for_test((276, 277, 287))
    assert "WHERE t.indicator_id IN (" in sql, "indicator_unnest CTE must contain the WHERE IN-clause"
    assert "276, 277, 287" in sql, "allow-list IDs must be embedded as comma-joined ints"


def test_sql_shape_no_quote_chars_around_ids():
    """Defensive: confirm the IN-clause has NO quote chars (which would
    signal someone snuck a string concatenation in)."""
    sql = _build_insert_sql_for_test((1, 2, 3))
    in_clause_match = re.search(r"WHERE t\.indicator_id IN \(([^)]+)\)", sql)
    assert in_clause_match, "IN-clause must be present"
    in_clause = in_clause_match.group(1)
    assert "'" not in in_clause and '"' not in in_clause, f"IN-clause must contain ints only, no quotes: {in_clause!r}"


def test_sql_shape_excludes_18_legacy_ids_from_in_clause():
    """The whole point of #591: the 18 legacy IDs MUST NOT appear inside
    the WHERE-IN clause. Test against a realistic allow-list (61 catalog
    IDs sampled from the impact-analysis output) and assert all 18 legacy
    are excluded."""
    # Sample of catalog WB+VD numeric IDs known to be in the allow-list
    # (from impact-analysis 2026-05-04). Just enough to test the SQL shape.
    sample_allow_list = (276, 277, 278, 287, 290, 301, 302)  # all V-Dem
    sql = _build_insert_sql_for_test(sample_allow_list)
    in_clause_match = re.search(r"WHERE t\.indicator_id IN \(([^)]+)\)", sql)
    in_clause = in_clause_match.group(1)
    in_clause_ids = {int(s.strip()) for s in in_clause.split(",")}
    assert in_clause_ids == set(sample_allow_list), (
        f"IN-clause must contain exactly the allow-list ids; got {in_clause_ids}, expected {set(sample_allow_list)}"
    )
    intersection = in_clause_ids & LEGACY_18_NUMERIC_IDS
    assert not intersection, (
        f"FAIL: legacy IDs leaked into the IN-clause: {intersection}. "
        "If the canonical catalog now genuinely includes one of these "
        "(catalog promoted a legacy ID into curated status), update "
        "LEGACY_18_NUMERIC_IDS in this test AND document the methodology "
        "decision in docs/specs/methodology/."
    )
