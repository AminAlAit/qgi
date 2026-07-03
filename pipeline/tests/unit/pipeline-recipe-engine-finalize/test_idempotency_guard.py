"""
Unit tests for #496 idempotency guard (`_check_idempotency_skip`) in
pipeline-recipe-engine-finalize.

Covers:
- force=True always returns False (proceed with CTAS)
- recent timestamp (within window) returns True (skip CTAS)
- old timestamp (outside window) returns False (proceed)
- empty table / NULL max() returns False (proceed)
- Athena query failure returns False (graceful degradation, never blocks)
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Load the Lambda module directly (no package install). lambda_function.py
# imports country_risks (a sibling in the Lambda dir), so we add the
# Lambda dir to sys.path before executing the spec.
_LAMBDA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "lambdas" / "pipeline-recipe-engine-finalize"
sys.path.insert(0, str(_LAMBDA_DIR))
_MODULE_PATH = _LAMBDA_DIR / "lambda_function.py"
_spec = importlib.util.spec_from_file_location("recipe_engine_finalize", _MODULE_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _mock_athena_max_query(athena_mock, max_value: str | None) -> None:
    """Wire the Athena mock so run_query + get_query_results return a
    single-row result with the given max(timestamp) value."""
    athena_mock.start_query_execution.return_value = {"QueryExecutionId": "qid-test"}
    # run_query polls in a loop; first iteration returns SUCCEEDED.
    athena_mock.get_query_execution.return_value = {
        "QueryExecution": {"Status": {"State": "SUCCEEDED"}},
    }
    if max_value is None:
        # Empty table case: only header row.
        athena_mock.get_query_results.return_value = {
            "ResultSet": {"Rows": [{"Data": [{"VarCharValue": "recent"}]}]},
        }
    else:
        athena_mock.get_query_results.return_value = {
            "ResultSet": {
                "Rows": [
                    {"Data": [{"VarCharValue": "recent"}]},  # header
                    {"Data": [{"VarCharValue": max_value}]},  # value row
                ]
            },
        }


class TestIdempotencyGuard:
    def test_force_true_always_proceeds(self, monkeypatch):
        athena_mock = MagicMock()
        monkeypatch.setattr(mod, "athena", athena_mock)
        # Even with a "recent" max — force=True wins.
        _mock_athena_max_query(athena_mock, datetime.now(timezone.utc).isoformat())
        skip = mod._check_idempotency_skip("recipes_aggregated", force=True)
        assert skip is False
        # Athena should NOT have been queried (the force shortcut returns first).
        athena_mock.start_query_execution.assert_not_called()

    def test_recent_timestamp_skips(self, monkeypatch):
        athena_mock = MagicMock()
        monkeypatch.setattr(mod, "athena", athena_mock)
        # 5 minutes ago < 60-min window
        recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        _mock_athena_max_query(athena_mock, recent_ts)
        skip = mod._check_idempotency_skip("recipes_aggregated", force=False, window_minutes=60)
        assert skip is True

    def test_old_timestamp_proceeds(self, monkeypatch):
        athena_mock = MagicMock()
        monkeypatch.setattr(mod, "athena", athena_mock)
        # 3 hours ago > 60-min window
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        _mock_athena_max_query(athena_mock, old_ts)
        skip = mod._check_idempotency_skip("recipes_aggregated", force=False, window_minutes=60)
        assert skip is False

    def test_empty_table_proceeds(self, monkeypatch):
        """Athena returns header-only (table has no rows yet) → don't skip."""
        athena_mock = MagicMock()
        monkeypatch.setattr(mod, "athena", athena_mock)
        _mock_athena_max_query(athena_mock, max_value=None)
        skip = mod._check_idempotency_skip("recipes_aggregated", force=False)
        assert skip is False

    def test_query_failure_proceeds_gracefully(self, monkeypatch):
        """If the idempotency check itself errors, never block the caller."""
        athena_mock = MagicMock()
        monkeypatch.setattr(mod, "athena", athena_mock)
        athena_mock.start_query_execution.side_effect = RuntimeError("athena 503")
        skip = mod._check_idempotency_skip("recipes_aggregated", force=False)
        assert skip is False

    def test_custom_window_respected(self, monkeypatch):
        athena_mock = MagicMock()
        monkeypatch.setattr(mod, "athena", athena_mock)
        # 30 min ago > 15-min window → proceed
        ts_30m = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        _mock_athena_max_query(athena_mock, ts_30m)
        skip = mod._check_idempotency_skip("recipes_aggregated", force=False, window_minutes=15)
        assert skip is False
        # Same timestamp, 60-min window → skip
        skip = mod._check_idempotency_skip("recipes_aggregated", force=False, window_minutes=60)
        assert skip is True

    def test_country_recipe_scores_uses_last_computed_at(self, monkeypatch):
        """Ensure the timestamp_col arg threads through to the SQL.

        write_country_recipe_scores passes timestamp_col='last_computed_at'
        because that table uses a different column name than recipes_aggregated.
        """
        athena_mock = MagicMock()
        monkeypatch.setattr(mod, "athena", athena_mock)
        recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        _mock_athena_max_query(athena_mock, recent_ts)

        skip = mod._check_idempotency_skip(
            "country_recipe_scores",
            force=False,
            timestamp_col="last_computed_at",
        )
        assert skip is True
        # Verify the SQL referenced last_computed_at, not last_recomputed_at
        call_args = athena_mock.start_query_execution.call_args
        sql = call_args.kwargs.get("QueryString") or call_args.args[0] if call_args.args else ""
        if not sql:
            sql = call_args.kwargs.get("QueryString", "")
        assert "last_computed_at" in sql
        assert "last_recomputed_at" not in sql
