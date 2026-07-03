"""Unit tests for FLEET-5 / trio Condition A: assert_floor_ordering.

A per-recipe floor must be provably FROZEN BEFORE the walk it judges — otherwise a
floor re-derived from the same corpus the fleet is about to walk is a floor-shopping
vector that re-creates the foreign_intervention failure class at fleet scale. The
entrypoint refuses to run the fleet unless the floors artifact carries frozen-before-walk
provenance AND its frozen_at_utc strictly precedes the run launch.

The entrypoint lives under batch/recipe-fleet/ (not a package); load via importlib.
No AWS, no network.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ENTRYPOINT = Path(__file__).resolve().parents[3] / "batch" / "recipe-fleet" / "recipe_fleet_entrypoint.py"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("recipe_fleet_entrypoint", _ENTRYPOINT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["recipe_fleet_entrypoint"] = mod
    spec.loader.exec_module(mod)
    return mod


ep = _load_entrypoint()

_LAUNCH = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)


def _floors(**over):
    base = {
        "frozen_at_utc": (_LAUNCH - timedelta(hours=1)).isoformat(),  # frozen before launch
        "git_commit_sha": "abc1234",
        "panel_fingerprint": "fp-deadbeef",
        "floors": {"x": {"lock_floor": 0.70}},
    }
    base.update(over)
    return base


def test_ok_when_frozen_before_launch():
    ep.assert_floor_ordering(_floors(), _LAUNCH)  # no raise


@pytest.mark.parametrize("missing", ["frozen_at_utc", "git_commit_sha", "panel_fingerprint"])
def test_missing_provenance_field_refuses(missing):
    bad = _floors()
    bad[missing] = None
    with pytest.raises(ep.FloorOrderingError, match="provenance"):
        ep.assert_floor_ordering(bad, _LAUNCH)


def test_absent_provenance_key_refuses():
    bad = _floors()
    del bad["panel_fingerprint"]
    with pytest.raises(ep.FloorOrderingError, match="provenance"):
        ep.assert_floor_ordering(bad, _LAUNCH)


def test_frozen_at_launch_is_floor_shopping():
    """frozen_at == launch (not strictly before) must be refused."""
    with pytest.raises(ep.FloorOrderingError, match="FLOOR-SHOPPING"):
        ep.assert_floor_ordering(_floors(frozen_at_utc=_LAUNCH.isoformat()), _LAUNCH)


def test_frozen_after_launch_is_floor_shopping():
    after = (_LAUNCH + timedelta(seconds=1)).isoformat()
    with pytest.raises(ep.FloorOrderingError, match="FLOOR-SHOPPING"):
        ep.assert_floor_ordering(_floors(frozen_at_utc=after), _LAUNCH)


def test_naive_timestamp_assumed_utc():
    """A naive (tz-less) frozen_at_utc is treated as UTC, not crashed on."""
    naive_before = "2026-05-27T10:00:00"  # before _LAUNCH (12:00Z)
    ep.assert_floor_ordering(_floors(frozen_at_utc=naive_before), _LAUNCH)  # no raise


def test_non_iso_timestamp_refuses():
    with pytest.raises(ep.FloorOrderingError, match="ISO-8601"):
        ep.assert_floor_ordering(_floors(frozen_at_utc="last tuesday"), _LAUNCH)
