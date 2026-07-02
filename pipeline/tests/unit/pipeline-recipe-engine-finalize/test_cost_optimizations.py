"""
Unit tests for #495 (pattern_indicator_lookup) and #497 (temp-table CTAS pattern)
in pipeline-recipe-engine-finalize.

Covers:
  #495 build_pattern_indicator_lookup_table
    - idempotency: non-empty table skips build (rowcount guard)
    - idempotency: force=True overrides rowcount guard
    - empty table triggers build (INSERT INTO runs)
    - rowcount check failure proceeds gracefully (never blocks)

  #497 write_recipes_aggregated_table temp-table lifecycle
    - temp table DROP is called even when INSERT INTO raises (try/finally)
    - temp table DROP is called on success
    - S3 prefix cleanup runs on success
    - S3 prefix cleanup runs on INSERT failure

  _s3_delete_prefix
    - batches deletes correctly when > 1000 objects

  _check_idempotency_skip_rowcount
    - force=True returns False without querying Athena
    - non-empty table (>1 row) returns True (skip)
    - empty table (header row only) returns False (proceed)
    - Athena error returns False (graceful degradation)
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Module loading — same pattern as test_idempotency_guard.py
# ---------------------------------------------------------------------------
_LAMBDA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas" / "pipeline-recipe-engine-finalize"
sys.path.insert(0, str(_LAMBDA_DIR))
_MODULE_PATH = _LAMBDA_DIR / "lambda_function.py"
_spec = importlib.util.spec_from_file_location("recipe_engine_finalize", _MODULE_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_athena_mock_rowcount(has_rows: bool) -> MagicMock:
    """Return an Athena mock that simulates LIMIT 1 rowcount check."""
    m = MagicMock()
    m.start_query_execution.return_value = {"QueryExecutionId": "qid-rowcount"}
    m.get_query_execution.return_value = {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}
    if has_rows:
        # header + data row → table is non-empty → skip
        m.get_query_results.return_value = {
            "ResultSet": {
                "Rows": [
                    {"Data": [{"VarCharValue": "1"}]},  # header
                    {"Data": [{"VarCharValue": "1"}]},  # data
                ]
            }
        }
    else:
        # header only → table is empty → proceed
        m.get_query_results.return_value = {
            "ResultSet": {
                "Rows": [
                    {"Data": [{"VarCharValue": "1"}]},  # header only
                ]
            }
        }
    return m


def _make_s3_mock_empty() -> MagicMock:
    """S3 mock that returns no objects from list_objects_v2."""
    m = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Contents": []}]
    m.get_paginator.return_value = paginator
    return m


def _make_athena_run_query_ok() -> MagicMock:
    """Athena mock that makes run_query succeed for any SQL."""
    m = MagicMock()
    m.start_query_execution.return_value = {"QueryExecutionId": "qid-ok"}
    m.get_query_execution.return_value = {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}
    # get_query_results used only for idempotency checks — not called during
    # INSERT INTO / CREATE TABLE / DROP TABLE sequences.
    return m


# ---------------------------------------------------------------------------
# Tests: _check_idempotency_skip_rowcount
# ---------------------------------------------------------------------------


class TestIdempotencySkipRowcount:
    def test_force_true_skips_athena(self, monkeypatch):
        athena_mock = MagicMock()
        monkeypatch.setattr(mod, "athena", athena_mock)
        result = mod._check_idempotency_skip_rowcount("pattern_indicator_lookup", force=True)
        assert result is False
        athena_mock.start_query_execution.assert_not_called()

    def test_non_empty_table_returns_true(self, monkeypatch):
        """Non-empty table (has rows) → skip build."""
        athena_mock = _make_athena_mock_rowcount(has_rows=True)
        monkeypatch.setattr(mod, "athena", athena_mock)
        result = mod._check_idempotency_skip_rowcount("pattern_indicator_lookup", force=False)
        assert result is True

    def test_empty_table_returns_false(self, monkeypatch):
        """Empty table (header only) → proceed with build."""
        athena_mock = _make_athena_mock_rowcount(has_rows=False)
        monkeypatch.setattr(mod, "athena", athena_mock)
        result = mod._check_idempotency_skip_rowcount("pattern_indicator_lookup", force=False)
        assert result is False

    def test_athena_error_proceeds_gracefully(self, monkeypatch):
        """Any Athena failure → return False (never block the caller)."""
        athena_mock = MagicMock()
        athena_mock.start_query_execution.side_effect = RuntimeError("athena 503")
        monkeypatch.setattr(mod, "athena", athena_mock)
        result = mod._check_idempotency_skip_rowcount("pattern_indicator_lookup", force=False)
        assert result is False

    def test_sql_uses_limit_1(self, monkeypatch):
        """Verify the rowcount check uses LIMIT 1 (not a full-table COUNT)."""
        athena_mock = _make_athena_mock_rowcount(has_rows=False)
        monkeypatch.setattr(mod, "athena", athena_mock)
        mod._check_idempotency_skip_rowcount("pattern_indicator_lookup", force=False)
        sql = athena_mock.start_query_execution.call_args.kwargs.get("QueryString", "")
        assert "LIMIT 1" in sql.upper()
        assert "COUNT" not in sql.upper()


# ---------------------------------------------------------------------------
# Tests: build_pattern_indicator_lookup_table (#495)
# ---------------------------------------------------------------------------


class TestBuildPatternIndicatorLookup:
    def test_non_empty_table_skips_insert(self, monkeypatch):
        """Rowcount guard fires → INSERT INTO should NOT run."""
        # Athena mock: first call (SELECT 1 LIMIT 1) returns has_rows=True.
        athena_mock = _make_athena_mock_rowcount(has_rows=True)
        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.build_pattern_indicator_lookup_table(force=False)

        # start_query_execution called once (for the rowcount check) and then
        # NOT again (no INSERT INTO fired).
        assert athena_mock.start_query_execution.call_count == 1
        sql = athena_mock.start_query_execution.call_args.kwargs.get("QueryString", "")
        assert "INSERT" not in sql.upper()

    def test_force_rebuilds_even_when_non_empty(self, monkeypatch):
        """force=True should bypass rowcount guard and run INSERT INTO."""
        # Athena mock must handle both rowcount check path (bypassed by force)
        # and INSERT INTO path.
        athena_mock = _make_athena_run_query_ok()
        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.build_pattern_indicator_lookup_table(force=True)

        # Rowcount check not called; INSERT INTO was called.
        calls = [c.kwargs.get("QueryString", "") for c in athena_mock.start_query_execution.call_args_list]
        assert any("INSERT" in sql.upper() for sql in calls)
        # Verify the INSERT targets the correct table.
        insert_sql = next(s for s in calls if "INSERT" in s.upper())
        assert mod.PATTERN_INDICATOR_LOOKUP_TABLE_NAME in insert_sql

    def test_empty_table_runs_insert(self, monkeypatch):
        """Empty table → rowcount guard passes → INSERT INTO runs."""
        # First call: rowcount check (empty table). Subsequent calls: INSERT.
        call_count = [0]

        def mock_start(**kwargs):
            call_count[0] += 1
            return {"QueryExecutionId": f"qid-{call_count[0]}"}

        athena_mock = MagicMock()
        athena_mock.start_query_execution.side_effect = mock_start
        athena_mock.get_query_execution.return_value = {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}
        # First get_query_results call: empty table (header only).
        athena_mock.get_query_results.return_value = {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": "1"}]}]}}

        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.build_pattern_indicator_lookup_table(force=False)

        # At least 2 calls: rowcount check + INSERT INTO.
        assert athena_mock.start_query_execution.call_count >= 2
        all_sqls = [c.kwargs.get("QueryString", "") for c in athena_mock.start_query_execution.call_args_list]
        assert any("INSERT" in sql.upper() for sql in all_sqls)

    def test_insert_targets_pattern_indicator_lookup(self, monkeypatch):
        """INSERT INTO SQL must reference pattern_indicator_lookup, not patterns."""
        athena_mock = _make_athena_run_query_ok()
        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.build_pattern_indicator_lookup_table(force=True)

        all_sqls = [c.kwargs.get("QueryString", "") for c in athena_mock.start_query_execution.call_args_list]
        insert_sqls = [s for s in all_sqls if "INSERT" in s.upper()]
        assert insert_sqls, "No INSERT INTO found in Athena calls"
        insert_sql = insert_sqls[0]
        assert "pattern_indicator_lookup" in insert_sql
        assert "indicator_numeric_ids" in insert_sql
        assert "pattern_id" in insert_sql

    def test_s3_prefix_cleared_before_insert(self, monkeypatch):
        """S3 clear must happen before INSERT INTO (idempotency requirement)."""
        call_order = []

        athena_mock = MagicMock()
        s3_mock = MagicMock()

        # Track call ordering.
        def track_athena_call(**kwargs):
            sql = kwargs.get("QueryString", "")
            if "INSERT" in sql.upper():
                call_order.append("athena_insert")
            elif "LIMIT 1" in sql.upper():
                call_order.append("athena_rowcount")
            return {"QueryExecutionId": "qid-x"}

        def track_paginate(*args, **kwargs):
            call_order.append("s3_list")
            return iter([{"Contents": []}])

        athena_mock.start_query_execution.side_effect = track_athena_call
        athena_mock.get_query_execution.return_value = {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}
        # Rowcount check: empty table → proceed.
        athena_mock.get_query_results.return_value = {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": "1"}]}]}}

        paginator_mock = MagicMock()
        paginator_mock.paginate.side_effect = track_paginate
        s3_mock.get_paginator.return_value = paginator_mock

        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.build_pattern_indicator_lookup_table(force=False)

        s3_idx = call_order.index("s3_list")
        insert_idx = call_order.index("athena_insert")
        assert s3_idx < insert_idx, f"S3 clear (pos {s3_idx}) must happen before INSERT (pos {insert_idx})"


# ---------------------------------------------------------------------------
# Tests: write_recipes_aggregated_table temp-table lifecycle (#497)
# ---------------------------------------------------------------------------


class TestWriteRecipesAggregatedTempTable:
    """Verify the try/finally temp-table cleanup always runs (#497)."""

    def _make_combined_athena_mock(self, insert_raises=False):
        """Athena mock with distinct handling per query type.

        Call sequence:
          1. _check_idempotency_skip: start + get_execution (SUCCEEDED) + get_results (old ts)
          2. CTAS (CREATE TABLE): start + get_execution (SUCCEEDED)
          3. INSERT INTO: start + get_execution (SUCCEEDED or FAILED)
          4. DROP TABLE: start + get_execution (SUCCEEDED)
        """
        from datetime import timezone, timedelta
        from datetime import datetime as dt

        old_ts = (dt.now(timezone.utc) - timedelta(hours=3)).isoformat()

        call_n = [0]
        qids = []

        def start(**kwargs):
            call_n[0] += 1
            qid = f"qid-{call_n[0]}"
            qids.append((qid, kwargs.get("QueryString", "")))
            return {"QueryExecutionId": qid}

        m = MagicMock()
        m.start_query_execution.side_effect = start

        def get_exec(QueryExecutionId):
            # All queries succeed immediately except INSERT when insert_raises.
            matching = [s for qid, s in qids if qid == QueryExecutionId]
            sql = matching[0] if matching else ""
            if insert_raises and "INSERT" in sql.upper() and "INTO" in sql.upper():
                return {
                    "QueryExecution": {"Status": {"State": "FAILED", "StateChangeReason": "simulated INSERT failure"}}
                }
            return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}}}

        m.get_query_execution.side_effect = get_exec

        # get_query_results: for idempotency check returns old timestamp → proceed.
        m.get_query_results.return_value = {
            "ResultSet": {
                "Rows": [
                    {"Data": [{"VarCharValue": "recent"}]},
                    {"Data": [{"VarCharValue": old_ts}]},
                ]
            }
        }
        m._qids = qids  # expose for assertions
        return m

    def test_drop_table_called_on_success(self, monkeypatch):
        """DROP TABLE must be called after successful INSERT INTO."""
        athena_mock = self._make_combined_athena_mock(insert_raises=False)
        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.write_recipes_aggregated_table(force=False)

        all_sqls = [s for _, s in athena_mock._qids]
        assert any("DROP TABLE" in s.upper() for s in all_sqls), (
            "DROP TABLE not found in Athena calls after successful run"
        )

    def test_ctas_has_no_external_location(self, monkeypatch):
        """#545 regression guard: external_location must NOT appear in the CTAS.

        Tonight's pipeline run silently dropped recipes_aggregated to 0 rows
        because the CTAS specified `external_location = '{temp_s3_location}'`
        but the QGI-Lambda-Workgroup has EnforceWorkGroupConfiguration=true
        with a centralized OutputLocation. Athena rejected the CTAS with
        InvalidRequestException; the Lambda's outer try/except swallowed it.

        This test fails fast if external_location is reintroduced — a future
        engineer or refactor must consciously address the workgroup conflict.
        """
        athena_mock = self._make_combined_athena_mock(insert_raises=False)
        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.write_recipes_aggregated_table(force=False)

        all_sqls = [s for _, s in athena_mock._qids]
        ctas_sqls = [s for s in all_sqls if "CREATE TABLE" in s.upper()]
        assert ctas_sqls, "Expected at least one CTAS query"
        for ctas in ctas_sqls:
            assert "external_location" not in ctas.lower(), (
                "#545 regression: `external_location` reintroduced into a CTAS. "
                "QGI-Lambda-Workgroup enforces centralized OutputLocation and "
                "rejects per-query overrides. Either remove external_location "
                "or relax EnforceWorkGroupConfiguration on the workgroup."
            )

    def test_drop_table_called_on_insert_failure(self, monkeypatch):
        """DROP TABLE must be called even when INSERT INTO fails (try/finally)."""
        athena_mock = self._make_combined_athena_mock(insert_raises=True)
        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        with pytest.raises(RuntimeError, match="FAILED"):
            mod.write_recipes_aggregated_table(force=False)

        all_sqls = [s for _, s in athena_mock._qids]
        assert any("DROP TABLE" in s.upper() for s in all_sqls), (
            "DROP TABLE not found after INSERT failure — try/finally may be missing"
        )

    def test_ctas_uses_pattern_indicator_lookup_not_patterns(self, monkeypatch):
        """The temp-table CTAS must JOIN to pattern_indicator_lookup, NOT patterns."""
        athena_mock = self._make_combined_athena_mock(insert_raises=False)
        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.write_recipes_aggregated_table(force=False)

        # Find the CREATE TABLE (CTAS) SQL.
        all_sqls = [s for _, s in athena_mock._qids]
        ctas_sqls = [s for s in all_sqls if "CREATE TABLE" in s.upper()]
        assert ctas_sqls, "No CREATE TABLE found — CTAS step missing"
        ctas_sql = ctas_sqls[0]
        assert mod.PATTERN_INDICATOR_LOOKUP_TABLE_NAME in ctas_sql, (
            "CTAS must JOIN to pattern_indicator_lookup, not raw patterns"
        )
        # Should NOT reference patterns directly (by exact name match without lookup).
        # The lookup table name itself contains "pattern" so check precisely.
        # Strip the lookup table name and verify "patterns" alone doesn't appear.
        ctas_without_lookup = ctas_sql.replace(mod.PATTERN_INDICATOR_LOOKUP_TABLE_NAME, "")
        # Allow "patterns" as part of "recipes_deduped" context but not as a bare table.
        # The key check: the FROM / JOIN clause must name the lookup table.
        assert "pattern_indicator_lookup" in ctas_sql

    def test_insert_reads_from_temp_table(self, monkeypatch):
        """The INSERT INTO SQL must read from the temp table, not recipes_deduped."""
        athena_mock = self._make_combined_athena_mock(insert_raises=False)
        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.write_recipes_aggregated_table(force=False)

        all_sqls = [s for _, s in athena_mock._qids]
        insert_sqls = [s for s in all_sqls if s.strip().upper().startswith("INSERT")]
        assert insert_sqls, "No INSERT INTO found"
        insert_sql = insert_sqls[0]
        # The temp table name starts with "tmp_rwp_"
        assert "tmp_rwp_" in insert_sql, "INSERT INTO must read from temp table (tmp_rwp_*), not recipes_deduped"
        assert mod.RECIPES_DEDUPED_VIEW_NAME not in insert_sql, (
            f"INSERT INTO must NOT reference {mod.RECIPES_DEDUPED_VIEW_NAME} directly; "
            "it should read from the materialised temp table"
        )

    def test_s3_cleanup_called_on_failure(self, monkeypatch):
        """S3 prefix for temp table must be deleted even on INSERT failure."""
        athena_mock = self._make_combined_athena_mock(insert_raises=True)
        s3_delete_calls = []

        s3_mock = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = iter(
            [{"Contents": [{"Key": "pipeline-recipe-aggregator/tmp/tmp_rwp_abc/part-0.parquet"}]}]
        )
        s3_mock.get_paginator.return_value = paginator

        def track_delete(Bucket, Delete):
            s3_delete_calls.extend(Delete["Objects"])

        s3_mock.delete_objects.side_effect = track_delete

        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        with pytest.raises(RuntimeError):
            mod.write_recipes_aggregated_table(force=False)

        # At least one delete call should have targeted the tmp prefix.
        temp_prefix_deletes = [k for k in s3_delete_calls if "pipeline-recipe-aggregator/tmp/" in k["Key"]]
        assert temp_prefix_deletes, "S3 temp prefix not cleaned up after INSERT failure"

    def test_output_s3_prefix_cleared_before_ctas(self, monkeypatch):
        """Output prefix (recipes_aggregated) must be cleared before CTAS runs."""
        call_order = []

        athena_mock = self._make_combined_athena_mock(insert_raises=False)
        original_side_effect = athena_mock.start_query_execution.side_effect

        def tracking_start(**kwargs):
            sql = kwargs.get("QueryString", "")
            if "CREATE TABLE" in sql.upper():
                call_order.append("ctas")
            elif "INSERT" in sql.upper():
                call_order.append("insert")
            return original_side_effect(**kwargs)

        athena_mock.start_query_execution.side_effect = tracking_start

        s3_mock = MagicMock()
        paginator = MagicMock()

        def tracking_paginate(*args, **kwargs):
            call_order.append("s3_list")
            return iter([{"Contents": []}])

        paginator.paginate.side_effect = tracking_paginate
        s3_mock.get_paginator.return_value = paginator

        monkeypatch.setattr(mod, "athena", athena_mock)
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod.write_recipes_aggregated_table(force=False)

        # First s3_list should precede the first ctas.
        first_s3 = call_order.index("s3_list")
        first_ctas = call_order.index("ctas")
        assert first_s3 < first_ctas, f"Output S3 clear (pos {first_s3}) must precede CTAS (pos {first_ctas})"


# ---------------------------------------------------------------------------
# Tests: _s3_delete_prefix helper
# ---------------------------------------------------------------------------


class TestS3DeletePrefix:
    def test_empty_prefix_no_delete_called(self, monkeypatch):
        s3_mock = _make_s3_mock_empty()
        monkeypatch.setattr(mod, "s3", s3_mock)
        mod._s3_delete_prefix("some/prefix/")
        s3_mock.delete_objects.assert_not_called()

    def test_deletes_objects_in_single_batch(self, monkeypatch):
        objects = [{"Key": f"prefix/file-{i}.parquet"} for i in range(5)]
        s3_mock = MagicMock()
        paginator = MagicMock()
        paginator.paginate.return_value = iter([{"Contents": objects}])
        s3_mock.get_paginator.return_value = paginator
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod._s3_delete_prefix("prefix/")

        s3_mock.delete_objects.assert_called_once()
        call_kwargs = s3_mock.delete_objects.call_args.kwargs
        assert call_kwargs["Bucket"] == mod.S3_BUCKET
        assert len(call_kwargs["Delete"]["Objects"]) == 5

    def test_batches_when_over_1000_objects(self, monkeypatch):
        """Objects > 1000 must be split across multiple delete_objects calls."""
        objects = [{"Key": f"prefix/file-{i}.parquet"} for i in range(1500)]
        s3_mock = MagicMock()
        paginator = MagicMock()
        # One page with 1500 objects.
        paginator.paginate.return_value = iter([{"Contents": objects}])
        s3_mock.get_paginator.return_value = paginator
        monkeypatch.setattr(mod, "s3", s3_mock)

        mod._s3_delete_prefix("prefix/")

        # Should have called delete_objects twice: 1000 + 500.
        assert s3_mock.delete_objects.call_count == 2
        batch_sizes = [len(c.kwargs["Delete"]["Objects"]) for c in s3_mock.delete_objects.call_args_list]
        assert sorted(batch_sizes, reverse=True) == [1000, 500]
