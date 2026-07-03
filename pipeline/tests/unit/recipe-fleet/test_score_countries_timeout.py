"""QA #967 follow-up B: the score_countries subprocess timeout in
`run_score_countries` is parameterised via the SCORE_COUNTRIES_TIMEOUT_SECONDS env
var (default 1800 s). The default suits current fleet recipes (N_pos 60-150) but
may be tight once fat recipes (N_pos > 300) enter — at that point the K × 5-fold
LOO ablation dominates and 30 min is not generous.

These tests pin: env-unset → 1800; env=parses → that value is forwarded as
`subprocess.run(..., timeout=...)`; env=garbage → falls back to 1800 with a warning;
env=zero/negative → falls back to 1800 with a warning.

subprocess.run is monkeypatched so no real script is launched.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_ENTRYPOINT = Path(__file__).resolve().parents[3] / "batch" / "recipe-fleet" / "recipe_fleet_entrypoint.py"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("recipe_fleet_entrypoint_score_timeout", _ENTRYPOINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ep():
    return _load_entrypoint()


def _make_inputs(tmp_path, ep):
    """Stage the on-disk preconditions that run_score_countries needs to get past
    the early-exit guards (summary present, positives present)."""
    recipe_id = "civil_war_and_insurgency"
    walk_dir = tmp_path / "walk"
    walk_dir.mkdir()
    (walk_dir / "f-ml-1-poc-summary.json").write_text("{}")
    # positives.csv lives at SHAPE_INPUTS_DIR/<recipe>/positives.csv. Point that
    # constant at tmp_path/shape_inputs for this test.
    shape_inputs = tmp_path / "shape_inputs"
    (shape_inputs / recipe_id).mkdir(parents=True)
    (shape_inputs / recipe_id / "positives.csv").write_text("country,year\n")
    ep.SHAPE_INPUTS_DIR = shape_inputs  # type: ignore[attr-defined]
    return recipe_id, walk_dir, tmp_path / "panels"


class _FakeCompleted:
    returncode = 0


def test_timeout_defaults_to_1800_when_env_unset(ep, tmp_path, monkeypatch):
    monkeypatch.delenv("SCORE_COUNTRIES_TIMEOUT_SECONDS", raising=False)
    captured = {}

    def fake_run(cmd, *, capture_output, check, timeout):
        captured["timeout"] = timeout
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    recipe_id, walk_dir, panel_dir = _make_inputs(tmp_path, ep)
    result = ep.run_score_countries(recipe_id, walk_dir, panel_dir)
    assert captured["timeout"] == 1800
    assert result["status"] == "ok"


def test_timeout_respects_env_var_when_set(ep, tmp_path, monkeypatch):
    monkeypatch.setenv("SCORE_COUNTRIES_TIMEOUT_SECONDS", "5400")  # 90 min
    captured = {}

    def fake_run(cmd, *, capture_output, check, timeout):
        captured["timeout"] = timeout
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    recipe_id, walk_dir, panel_dir = _make_inputs(tmp_path, ep)
    result = ep.run_score_countries(recipe_id, walk_dir, panel_dir)
    assert captured["timeout"] == 5400
    assert result["status"] == "ok"


def test_timeout_falls_back_to_default_on_garbage_value(ep, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("SCORE_COUNTRIES_TIMEOUT_SECONDS", "not-a-number")
    captured = {}

    def fake_run(cmd, *, capture_output, check, timeout):
        captured["timeout"] = timeout
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    recipe_id, walk_dir, panel_dir = _make_inputs(tmp_path, ep)
    import logging

    with caplog.at_level(logging.WARNING):
        result = ep.run_score_countries(recipe_id, walk_dir, panel_dir)
    assert captured["timeout"] == 1800
    assert result["status"] == "ok"
    assert any("SCORE_COUNTRIES_TIMEOUT_SECONDS" in rec.message for rec in caplog.records)


def test_timeout_falls_back_to_default_on_zero_or_negative(ep, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("SCORE_COUNTRIES_TIMEOUT_SECONDS", "0")
    captured = {}

    def fake_run(cmd, *, capture_output, check, timeout):
        captured["timeout"] = timeout
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    recipe_id, walk_dir, panel_dir = _make_inputs(tmp_path, ep)
    import logging

    with caplog.at_level(logging.WARNING):
        ep.run_score_countries(recipe_id, walk_dir, panel_dir)
    assert captured["timeout"] == 1800
    assert any("SCORE_COUNTRIES_TIMEOUT_SECONDS" in rec.message for rec in caplog.records)


def test_timeout_skipped_when_summary_missing_no_subprocess(ep, tmp_path, monkeypatch):
    """The env-var read MUST come after the precondition checks — confirm we
    don't even attempt subprocess.run when the walk summary is absent."""
    monkeypatch.setenv("SCORE_COUNTRIES_TIMEOUT_SECONDS", "999")
    called = {"n": 0}

    def fake_run(*a, **kw):  # pragma: no cover — should NOT be called
        called["n"] += 1
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)
    recipe_id = "civil_war_and_insurgency"
    walk_dir = tmp_path / "walk"
    walk_dir.mkdir()  # NO summary file inside
    result = ep.run_score_countries(recipe_id, walk_dir, tmp_path / "panels")
    assert result == {"status": "skipped", "reason": "summary_absent"}
    assert called["n"] == 0
