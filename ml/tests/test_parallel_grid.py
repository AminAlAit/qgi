"""Unit tests for #961: bit-identical parallel (candidate × window) grid in
greedy_outer_loop.

The contract: running the greedy with n_jobs>1 must produce results IDENTICAL to
n_jobs=1 (same selected indicators, same windows, same AUCs, same tie-breaks) —
parallelism changes only WHICH thread evaluates a cell, never which cell wins.

NOTE the fake here is deliberately THREAD-SAFE: the cell's AUC is encoded into the
returned X array (recovered by fit_predict_loco), so there is NO shared mutable state
between build_X_y and fit_predict_loco. (The shared-dict fake in test_greedy_checkpoint.py
/ test_early_abort.py would race under the thread backend — it is only used with the
default n_jobs=1.) These tests prove the ORDERING/REDUCE logic is bit-identical; they do
NOT exercise real-solver thread-safety (the real fit is monkeypatched out) — that is why
greedy_outer_loop hard-restricts n_jobs>1 to the XGBoost architecture. No IO, no panels,
no AWS.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_f_ml_1_poc as drv  # noqa: E402


@pytest.fixture
def fake_inner(monkeypatch):
    """Thread-safe deterministic fake: AUC = 0.5 + sum(values in trial set) + tiny
    window bonus, encoded into X[0, 0] so fit_predict_loco recovers it with no shared
    state. Tests set `fake_inner['values']`."""
    monkeypatch.setattr(drv, "WINDOW_GRID", [5, 10], raising=True)
    ctrl = {"values": {}}

    def fake_build_X_y(samples, trial_set, win, panels, feat_cache=None):
        auc = 0.5 + sum(ctrl["values"].get(i, 0.0) for i in trial_set) + 1e-4 * win
        X = np.full((40, 1), auc, dtype=float)   # AUC carried in the data, not a closure
        y = np.array([0, 1] * 20)
        return X, y, ["cc"] * 40, [2000] * 40

    def fake_loco(X, y, c, yr, architecture="LR", seed=0):
        auc = float(X[0, 0])
        return {"global_auc": auc, "per_country_auc": {"cc": auc},
                "probs": np.array([0.4, 0.6]), "labels": np.array([0, 1])}

    monkeypatch.setattr(drv, "build_X_y", fake_build_X_y, raising=True)
    monkeypatch.setattr(drv, "fit_predict_loco", fake_loco, raising=True)
    return ctrl


def _run(candidates, max_steps, n_jobs, architecture="XGBoost"):
    # architecture defaults to XGBoost — the only architecture for which n_jobs>1 is
    # permitted (the fleet path). fit_predict_loco is monkeypatched, so the string only
    # has to clear greedy_outer_loop's n_jobs>1 guard.
    return drv.greedy_outer_loop(
        samples=None, candidates_top_n=candidates, panels={},
        architecture=architecture, delta_step=drv.DELTA_STEP, max_steps=max_steps, seed=0,
        n_jobs=n_jobs,
        min_pos_survival=0.0, min_effective_npos=1, min_survive_countries=1,
        min_neg_survival=0.0,
    )


@pytest.mark.parametrize("n_jobs", [2, 4, 8])
def test_grid_parallel_bit_identical_to_serial(fake_inner, n_jobs):
    """THE core guarantee: parallel grid evaluation is bit-identical to serial."""
    fake_inner["values"] = {"a": 0.15, "b": 0.10, "c": 0.05, "d": 0.02}
    serial = _run(list("abcd"), max_steps=4, n_jobs=1)
    parallel = _run(list("abcd"), max_steps=4, n_jobs=n_jobs)

    assert parallel["selected_indicators"] == serial["selected_indicators"]
    assert parallel["chosen_window"] == serial["chosen_window"]
    assert parallel["final_global_auc"] == serial["final_global_auc"]  # EXACT, not approx
    assert (
        [(h["candidate"], h["window"], h["auc"]) for h in parallel["history"]]
        == [(h["candidate"], h["window"], h["auc"]) for h in serial["history"]]
    )


def test_grid_parallel_tiebreak_is_deterministic(fake_inner):
    """When two candidates tie on AUC, the first in candidate order must win — under
    BOTH serial and parallel (strict-`>` reduce over input-ordered results)."""
    fake_inner["values"] = {"a": 0.10, "b": 0.10}  # exact tie
    serial = _run(["a", "b"], max_steps=1, n_jobs=1)
    parallel = _run(["a", "b"], max_steps=1, n_jobs=4)
    assert serial["selected_indicators"] == ["a"]      # first-seen wins the tie
    assert parallel["selected_indicators"] == ["a"]     # identical under parallelism


def test_grid_parallel_default_is_serial(fake_inner):
    """Back-compat: the default n_jobs=1 path still selects best-first in order."""
    fake_inner["values"] = {"a": 0.15, "b": 0.10, "c": 0.05}
    res = _run(["c", "a", "b"], max_steps=3, n_jobs=1)
    assert res["selected_indicators"] == ["a", "b", "c"]
    assert res["chosen_window"] == 10  # max window tie-break bonus


@pytest.mark.parametrize("arch", ["LR", "MLP"])
def test_parallel_rejected_for_non_xgboost(fake_inner, arch):
    """The §2.5 guard: n_jobs>1 is refused for LR/MLP (BLAS thread state can make
    concurrent sklearn fits non-deterministic) — only XGBoost may parallelize. n_jobs=1
    stays allowed for all architectures."""
    fake_inner["values"] = {"a": 0.10}
    with pytest.raises(ValueError, match="bit-identical only for XGBoost"):
        _run(["a"], max_steps=1, n_jobs=4, architecture=arch)
    # n_jobs=1 is fine for any architecture (no parallelism → no BLAS race).
    assert _run(["a"], max_steps=1, n_jobs=1, architecture=arch)["selected_indicators"] == ["a"]
