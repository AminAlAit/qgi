"""FLEET-4c: run_walk forwards N_JOBS (set by the SFN Map per #962) to the walk's
--n-jobs (the #961 parallel grid). Defaults to 1 when unset/invalid.

The entrypoint lives under batch/recipe-fleet/ (not a package); load via importlib.
subprocess is monkeypatched so no walk actually runs.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
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


def _capture_cmd(monkeypatch, tmp_path, n_jobs_env):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        raise subprocess.CalledProcessError(1, cmd)  # short-circuit post-processing

    monkeypatch.setattr(ep.subprocess, "run", fake_run)
    monkeypatch.setattr(ep, "_find_script", lambda name: tmp_path / "run_f_ml_1_poc.py")
    if n_jobs_env is None:
        monkeypatch.delenv("N_JOBS", raising=False)
    else:
        monkeypatch.setenv("N_JOBS", n_jobs_env)
    ep.run_walk("rx", tmp_path, tmp_path / "out", tmp_path / "cohort.json", lock_floor=0.70, cohort_loco_floor=0.64)
    return captured["cmd"]


def _n_jobs_value(cmd):
    assert "--n-jobs" in cmd
    return cmd[cmd.index("--n-jobs") + 1]


def test_forwards_sized_n_jobs(monkeypatch, tmp_path):
    assert _n_jobs_value(_capture_cmd(monkeypatch, tmp_path, "16")) == "16"


def test_defaults_to_1_when_unset(monkeypatch, tmp_path):
    assert _n_jobs_value(_capture_cmd(monkeypatch, tmp_path, None)) == "1"


@pytest.mark.parametrize("bad", ["", "0", "-4", "8.5", "abc"])
def test_invalid_n_jobs_falls_back_to_1(monkeypatch, tmp_path, bad):
    assert _n_jobs_value(_capture_cmd(monkeypatch, tmp_path, bad)) == "1"
