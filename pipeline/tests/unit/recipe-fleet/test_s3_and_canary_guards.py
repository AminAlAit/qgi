"""Unit tests for two fleet-entrypoint safety fixes (QA sweep 2026-05-26):

  #918 — s3_object_exists must return False ONLY on a 404; any other error
         (403/throttle/network) must RAISE, never be swallowed as "absent"
         (the resume-guard mis-skip / re-run bug).
  #920 — the canary result must look up the canary recipe's OWN summary entry by
         id and report canary_walked=False for a skipped (never-walked) canary, so
         the SFN gate cannot auto-approve the fan-out on a no-op.

The entrypoint lives under batch/recipe-fleet/ (not a package); load via importlib.
No AWS, no network — boto3 is mocked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

_ENTRYPOINT = Path(__file__).resolve().parents[3] / "batch" / "recipe-fleet" / "recipe_fleet_entrypoint.py"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("recipe_fleet_entrypoint", _ENTRYPOINT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["recipe_fleet_entrypoint"] = mod
    spec.loader.exec_module(mod)
    return mod


ep = _load_entrypoint()


class _FakeS3:
    """Minimal stand-in: head_object either succeeds or raises a coded ClientError."""

    def __init__(self, error_code: str | None):
        self._error_code = error_code

    def head_object(self, **_kwargs):
        if self._error_code is None:
            return {"ContentLength": 1}
        raise ClientError({"Error": {"Code": self._error_code}}, "HeadObject")


def _patch_s3(monkeypatch, error_code):
    monkeypatch.setattr(ep, "_s3", lambda: _FakeS3(error_code), raising=True)


# --- #918: s3_object_exists ---------------------------------------------------


def test_object_present_returns_true(monkeypatch):
    _patch_s3(monkeypatch, None)
    assert ep.s3_object_exists("b", "k") is True


def test_404_returns_false(monkeypatch):
    _patch_s3(monkeypatch, "404")
    assert ep.s3_object_exists("b", "k") is False


@pytest.mark.parametrize("code", ["NoSuchKey", "NotFound"])
def test_other_not_found_codes_return_false(monkeypatch, code):
    _patch_s3(monkeypatch, code)
    assert ep.s3_object_exists("b", "k") is False


@pytest.mark.parametrize("code", ["403", "AccessDenied", "ThrottlingException", "500"])
def test_non_404_errors_raise_not_swallowed(monkeypatch, code):
    """The whole point of the fix: a permissions/throttle error must NOT read as
    'object absent' (which would silently corrupt the resume-guard)."""
    _patch_s3(monkeypatch, code)
    with pytest.raises(ClientError):
        ep.s3_object_exists("b", "k")


# --- #920: resolve_canary_entry ----------------------------------------------


def test_canary_walked_picks_entry_by_id_not_position():
    # job_summary[0] is a SKIPPED other recipe; the canary is a later, walked entry.
    js = [
        {"recipe_id": "other", "status": "skipped"},
        {"recipe_id": "constitutional_change", "status": "HARD_FAIL", "walk_wall_clock_seconds": 1234},
    ]
    entry, status, walked = ep.resolve_canary_entry(js, "constitutional_change")
    assert walked is True
    assert status == "HARD_FAIL"
    assert entry["walk_wall_clock_seconds"] == 1234


@pytest.mark.parametrize("status", ["skipped", "skipped_no_floor"])
def test_skipped_canary_is_not_walked(status):
    js = [{"recipe_id": "r1", "status": status}]
    _entry, st, walked = ep.resolve_canary_entry(js, "r1")
    assert walked is False
    assert st == status


def test_missing_canary_entry_is_unknown_and_not_walked():
    _entry, status, walked = ep.resolve_canary_entry([], "r1")
    assert status == "unknown"
    assert walked is False


def test_genuine_lock_canary_is_walked():
    js = [{"recipe_id": "r1", "status": "LOCK", "walk_wall_clock_seconds": 9000}]
    _entry, status, walked = ep.resolve_canary_entry(js, "r1")
    assert walked is True and status == "LOCK"


@pytest.mark.parametrize("status", ["error", "timeout"])
def test_failed_walk_counts_as_walked_but_warns(status):
    """A walk that ran and then errored/timed out IS walked (not skipped), but the
    canary message must steer away from approving on a failed canary (review FU-1)."""
    js = [{"recipe_id": "r1", "status": status}]
    _entry, st, walked = ep.resolve_canary_entry(js, "r1")
    assert walked is True and st == status
    assert "DO NOT APPROVE" in ep._canary_message(walked, st)


# --- #920 message contract (review FU-3) -------------------------------------


def test_message_blocks_approval_for_skipped_and_failed_but_allows_clean():
    assert "DO NOT APPROVE" in ep._canary_message(False, "skipped")
    assert "DO NOT APPROVE" in ep._canary_message(True, "error")
    msg_ok = ep._canary_message(True, "ok")
    assert "DO NOT APPROVE" not in msg_ok and "approve the fan-out" in msg_ok
