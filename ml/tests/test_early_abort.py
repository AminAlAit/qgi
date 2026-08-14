"""Unit tests for the floor-aware early-abort in greedy_outer_loop (FLEET-3,
QGI-R&D | 002, 2026-05-27).

The abort stops a greedy walk that is HARD_FAIL-bound — when even the most
OPTIMISTIC remaining gain (every future step earning the best single-step lift
seen so far) cannot reach lock_floor. Ji-Hoon's §2.5-clean property is the
contract under test: the abort is OUTCOME-NEUTRAL — it only ever TRUNCATES a
walk that would have failed anyway, never changes which indicators get selected,
and never fires on a recipe that could reach the floor.

As in test_greedy_checkpoint.py, the expensive inner fns (build_X_y,
fit_predict_loco) are monkeypatched so AUC is a deterministic function of the
selected set. No IO, no panels, no AWS.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_f_ml_1_poc as drv  # noqa: E402


@pytest.fixture
def fake_inner(monkeypatch):
    """AUC = 0.5 + sum of per-indicator values in the trial set. Tests set
    `fake_inner['values']` to shape the lift trajectory. Single window → no
    tiebreak noise. Returns the mutable control dict."""
    monkeypatch.setattr(drv, "WINDOW_GRID", [10], raising=True)
    # `values` → additive AUC; or set `auc_fn` for non-additive (interaction) AUC.
    ctrl = {"values": {}, "auc_fn": None}
    last = {"auc": 0.5}

    def fake_build_X_y(samples, trial_set, win, panels, feat_cache=None):
        if ctrl["auc_fn"] is not None:
            last["auc"] = ctrl["auc_fn"](trial_set)
        else:
            last["auc"] = 0.5 + sum(ctrl["values"].get(i, 0.0) for i in trial_set)
        X = np.ones((40, max(1, len(trial_set))))
        y = np.array([0, 1] * 20)
        return X, y, ["cc"] * 40, [2000] * 40

    def fake_loco(X, y, c, yr, architecture="LR", seed=0):
        return {"global_auc": last["auc"], "per_country_auc": {"cc": last["auc"]},
                "probs": np.array([0.4, 0.6]), "labels": np.array([0, 1])}

    monkeypatch.setattr(drv, "build_X_y", fake_build_X_y, raising=True)
    monkeypatch.setattr(drv, "fit_predict_loco", fake_loco, raising=True)
    return ctrl


def _run(candidates, max_steps, lock_floor=None, min_steps=drv.MIN_STEPS_BEFORE_ABORT):
    return drv.greedy_outer_loop(
        samples=None, candidates_top_n=candidates, panels={},
        architecture="LR", delta_step=drv.DELTA_STEP, max_steps=max_steps, seed=0,
        lock_floor=lock_floor, min_steps_before_abort=min_steps,
        # Relax the coverage gate — these tests exercise the abort control flow,
        # not the coverage policy (covered in test_coverage_gate.py).
        min_pos_survival=0.0, min_effective_npos=1, min_survive_countries=1,
        min_neg_survival=0.0,
    )


def test_abort_fires_when_floor_unreachable(fake_inner):
    """Uniform tiny lifts (0.02 > delta_step, so the natural halt never fires —
    the constitutional_change pattern) against a high floor → must early-abort.
    Aborts the step AFTER the grace period (default min_steps=3)."""
    fake_inner["values"] = {k: 0.02 for k in "abcde"}
    res = _run(list("abcde"), max_steps=5, lock_floor=0.90)
    assert res["early_abort_floor_unreachable"] is True
    assert len(res["selected_indicators"]) == 3      # committed steps 1-3, aborted before 4
    assert res["final_global_auc"] == pytest.approx(0.56)  # 0.5 + 3×0.02


def test_no_abort_when_floor_reachable(fake_inner):
    """A recipe whose AUC clears the floor early must never abort, and runs to
    completion."""
    fake_inner["values"] = {"a": 0.15, "b": 0.10, "c": 0.05, "d": 0.02}
    res = _run(list("abcd"), max_steps=4, lock_floor=0.62)
    assert res["early_abort_floor_unreachable"] is False
    assert res["selected_indicators"] == ["a", "b", "c", "d"]


def test_no_premature_abort_when_floor_crossed_late(fake_inner):
    """Outcome-neutral guarantee #1: a recipe that only crosses the floor at a
    LATER step must not be killed early. Uniform 0.05 lifts, floor 0.70: at step
    3 (auc 0.65) the optimistic ceiling (0.65 + 2×0.05 = 0.75) still clears 0.70,
    so no abort — and the walk then actually reaches 0.70+."""
    fake_inner["values"] = {k: 0.05 for k in "abcde"}
    res = _run(list("abcde"), max_steps=5, lock_floor=0.70)
    assert res["early_abort_floor_unreachable"] is False
    assert res["final_global_auc"] >= 0.70


def test_abort_only_truncates_never_reorders(fake_inner):
    """Outcome-neutral guarantee #2: the SAME walk with lock_floor=None (no abort)
    selects the identical indicators in the identical order — the abort merely
    stops early. It can only convert a future-FAIL into an earlier-FAIL."""
    fake_inner["values"] = {k: 0.02 for k in "abcde"}
    aborted = _run(list("abcde"), max_steps=5, lock_floor=0.90)
    unbounded = _run(list("abcde"), max_steps=5, lock_floor=None)
    assert unbounded["early_abort_floor_unreachable"] is False
    assert len(unbounded["selected_indicators"]) == 5      # ran to the cap
    # The aborted selection is a strict PREFIX of the unbounded one.
    k = len(aborted["selected_indicators"])
    assert aborted["selected_indicators"] == unbounded["selected_indicators"][:k]


def test_grace_period_holds(fake_inner):
    """The walk never aborts before min_steps_before_abort, even when doomed —
    giving late/interaction indicators a chance. With min_steps=4 the doomed walk
    survives step 3 and aborts at step 4."""
    fake_inner["values"] = {k: 0.02 for k in "abcdef"}
    res = _run(list("abcdef"), max_steps=6, lock_floor=0.90, min_steps=4)
    assert res["early_abort_floor_unreachable"] is True
    assert len(res["selected_indicators"]) == 4   # survived step 3, aborted at step 4


def test_no_lock_floor_disables_abort(fake_inner):
    """Back-compat: lock_floor=None (the pre-FLEET-3 default) never aborts."""
    fake_inner["values"] = {k: 0.02 for k in "abc"}
    res = _run(list("abc"), max_steps=3, lock_floor=None)
    assert res["early_abort_floor_unreachable"] is False
    assert res["selected_indicators"] == ["a", "b", "c"]


def test_interaction_effect_can_cause_false_abort(fake_inner):
    """DOCUMENTS THE KNOWN LIMITATION (PR #116 review): the abort bound is a
    conservative HEURISTIC, not a strict upper bound. Under interaction effects a
    future single-step lift can exceed observed_max_lift, so the abort CAN wrongly
    terminate a recipe that would have reached the floor. Here 'z' is worthless
    alone but worth +0.30 once {a,b,c} are selected — greedy adds a,b,c first (tiny
    0.02 lifts), the abort then fires at the floor, and the recipe never gets to add
    'z'. An unbounded run reaches 0.86 ≥ floor. This test PINS the non-neutrality so
    the limitation is honest and visible, not a silent assumption. The §2.5 ruling
    (Ji-Hoon+Kwame 2026-05-27) routes this halt to INCOMPLETE, not HARD_FAIL — see
    test_early_abort_routes_to_incomplete_not_hard_fail."""
    def auc_fn(trial_set):
        s = set(trial_set)
        base = 0.5 + 0.02 * len(s & set("abc"))
        if "z" in s and {"a", "b", "c"} <= s:
            base += 0.30  # synergistic: z only pays off once a,b,c are present
        return base

    fake_inner["auc_fn"] = auc_fn
    aborted = _run(["a", "b", "c", "z"], max_steps=4, lock_floor=0.80)
    unbounded = _run(["a", "b", "c", "z"], max_steps=4, lock_floor=None)

    assert aborted["early_abort_floor_unreachable"] is True
    assert aborted["final_global_auc"] < 0.80          # wrongly judged HARD_FAIL-bound
    assert unbounded["selected_indicators"] == ["a", "b", "c", "z"]
    assert unbounded["final_global_auc"] >= 0.80        # would actually have passed


def test_early_abort_routes_to_incomplete_not_hard_fail():
    """§2.5 ruling (Ji-Hoon+Kwame 2026-05-27): because the abort bound is a heuristic
    (it can flip a would-be-PASS, per the test above), a floor-unreachable abort must
    route to INCOMPLETE_CEILING_BELOW_FLOOR for human/Majles adjudication — NEVER an
    auto-HARD_FAIL. The override is verdict-neutral → structurally §2.5-clean."""
    assert drv.early_abort_verdict_override(
        "HARD_FAIL", {"early_abort_floor_unreachable": True}
    ) == "INCOMPLETE_CEILING_BELOW_FLOOR"
    # No abort → the gate-derived verdict passes through untouched.
    assert drv.early_abort_verdict_override(
        "HARD_FAIL", {"early_abort_floor_unreachable": False}
    ) == "HARD_FAIL"
    assert drv.early_abort_verdict_override("LOCK", {}) == "LOCK"
    assert drv.early_abort_verdict_override(
        "MARGINAL_PENDING_BETA_CALIBRATION", {"early_abort_floor_unreachable": False}
    ) == "MARGINAL_PENDING_BETA_CALIBRATION"
