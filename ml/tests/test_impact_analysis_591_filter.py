"""Tests for impact_analysis_591_filter.athena_query timeout guard
(#600 Finding 5).

The script's previous athena_query() polled with `while True:
time.sleep(1.5)` and no max-iteration check — a stuck-in-RUNNING query
would hang the script forever. After #600 Finding 5, polling is capped
at max_poll_iterations (default 300 → ~7.5 minutes) and raises
TimeoutError when exceeded.

The test below patches `time.sleep` to a no-op so the suite stays fast,
and stubs the Athena client to return RUNNING forever; the test asserts
that the timeout fires and the error message includes the iteration
count + the SQL prefix.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "impact_analysis_591_filter.py"
)
_spec = importlib.util.spec_from_file_location("impact_analysis_591_filter", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["impact_analysis_591_filter"] = mod
_spec.loader.exec_module(mod)


def _make_stuck_athena_client(states: list[str]) -> MagicMock:
    """Build a mock Athena client whose get_query_execution returns the
    given sequence of states (last state repeats forever)."""
    client = MagicMock()
    client.start_query_execution.return_value = {"QueryExecutionId": "qid-test"}

    state_iter = iter(states)
    last_state = states[-1]

    def _get_query_execution(**_kwargs):
        nonlocal last_state
        try:
            last_state = next(state_iter)
        except StopIteration:
            pass
        return {"QueryExecution": {"Status": {"State": last_state}}}

    client.get_query_execution.side_effect = _get_query_execution
    return client


def test_athena_query_times_out_after_max_iterations(monkeypatch):
    """Stuck-in-RUNNING query: athena_query must raise TimeoutError
    after max_poll_iterations, not hang forever."""
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    client = _make_stuck_athena_client(["RUNNING"])

    with pytest.raises(TimeoutError) as exc_info:
        mod.athena_query(
            client, workgroup="test-wg", sql="SELECT 1",
            max_poll_iterations=5,
        )
    msg = str(exc_info.value)
    assert "5 poll iterations" in msg
    assert "'RUNNING'" in msg
    assert "SELECT 1" in msg


def test_athena_query_succeeds_within_iteration_budget(monkeypatch):
    """Happy path: query transitions to SUCCEEDED before the cap. Must
    not raise TimeoutError; results pagination should run normally."""
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    # First poll returns RUNNING, second returns SUCCEEDED
    client = _make_stuck_athena_client(["RUNNING", "SUCCEEDED"])
    # Stub paginator to return one empty page (header only)
    paginator = MagicMock()
    paginator.paginate.return_value = iter([{
        "ResultSet": {"Rows": [{"Data": [{"VarCharValue": "col_name"}]}]}
    }])
    client.get_paginator.return_value = paginator

    rows = mod.athena_query(
        client, workgroup="test-wg", sql="SELECT 1",
        max_poll_iterations=10,
    )
    # Header row is skipped; no data rows in this fixture
    assert rows == []


def test_athena_query_raises_runtime_error_on_failed_state(monkeypatch):
    """If the query reaches FAILED state, RuntimeError is raised (not
    TimeoutError) — distinct from the timeout path. The fix must not
    accidentally swallow this branch."""
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    client = _make_stuck_athena_client(["FAILED"])
    # Need to override the side effect to include StateChangeReason
    client.get_query_execution.side_effect = lambda **_: {
        "QueryExecution": {
            "Status": {"State": "FAILED", "StateChangeReason": "syntax error"}
        }
    }

    with pytest.raises(RuntimeError, match="FAILED"):
        mod.athena_query(
            client, workgroup="test-wg", sql="SELECT bad",
            max_poll_iterations=10,
        )


def test_athena_query_default_max_iterations_is_300():
    """Default cap is 300 iterations (~7.5 min). Lock this so future
    refactors don't silently change the budget."""
    import inspect
    sig = inspect.signature(mod.athena_query)
    assert sig.parameters["max_poll_iterations"].default == 300
