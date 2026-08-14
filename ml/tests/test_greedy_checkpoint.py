"""Unit tests for greedy checkpoint/resume in run_f_ml_1_poc.py (#91).

Founder 2026-05-24: per-step checkpointing is mandatory for all recipes and a
hard prerequisite for the AWS Spot fleet (a reclaimed multi-hour walk must
RESUME, not restart from zero). These tests target the RESUME LOGIC, not the
model: the expensive inner functions (build_X_y, fit_predict_loco) are
monkeypatched with deterministic fakes so the greedy selection is exact and
fast. Key guarantee under test: a run resumed from a mid-greedy checkpoint
produces the IDENTICAL final result to an uninterrupted run.

No IO beyond a tmp dir, no panels, no AWS.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_f_ml_1_poc as drv  # noqa: E402


# Deterministic candidate "values": greedy should select in descending value,
# because AUC = 0.5 + sum(values in trial_set) + tiny window bonus → monotone.
_VALUES = {"a": 0.15, "b": 0.10, "c": 0.05, "d": 0.02}


@pytest.fixture
def fake_inner(monkeypatch):
    """Monkeypatch build_X_y + fit_predict_loco + WINDOW_GRID for a fast,
    deterministic greedy. AUC grows with the selected set; the largest window
    wins ties; so greedy selects [a, b, c, d] at the max window, in order."""
    monkeypatch.setattr(drv, "WINDOW_GRID", [5, 10], raising=True)

    def fake_build_X_y(samples, trial_set, win, panels):
        # 40 rows, 2 classes → passes the len>=30 and unique(y)>=2 guards.
        X = np.ones((40, max(1, len(trial_set))))
        y = np.array([0, 1] * 20)
        c = ["cc"] * 40
        yr = [2000] * 40
        return X, y, c, yr

    def fake_fit_predict_loco(X, y, c, yr, architecture="LR", seed=0):
        # AUC encoded back from the column count is not enough (build_X_y loses
        # the names), so we recover the set value from a closure on the caller.
        # Instead: stash the current trial_set value via X's column count is
        # ambiguous; use a module-level hook set by build_X_y.
        return {"global_auc": _LAST["auc"], "per_country_auc": {"cc": _LAST["auc"]},
                "probs": np.array([0.4, 0.6]), "labels": np.array([0, 1])}

    # We need fit_predict_loco's AUC to reflect the *specific* trial_set, so
    # compute it inside build_X_y (which sees trial_set) and stash it.
    _LAST = {"auc": 0.5}

    def fake_build_X_y_with_auc(samples, trial_set, win, panels, feat_cache=None):
        val = sum(_VALUES.get(ind, 0.0) for ind in trial_set)
        _LAST["auc"] = 0.5 + val + 1e-4 * win  # larger window → tiny tiebreak win
        return fake_build_X_y(samples, trial_set, win, panels)

    monkeypatch.setattr(drv, "build_X_y", fake_build_X_y_with_auc, raising=True)
    monkeypatch.setattr(drv, "fit_predict_loco", fake_fit_predict_loco, raising=True)
    return _LAST


def _run(candidates, max_steps, checkpoint_path=None, sig=None, samples=None):
    return drv.greedy_outer_loop(
        samples=samples, candidates_top_n=candidates, panels={},
        architecture="LR", delta_step=drv.DELTA_STEP, max_steps=max_steps, seed=0,
        checkpoint_path=checkpoint_path, config_signature=sig,
        # Relax the coverage gate: these tests exercise the resume MECHANIC on tiny
        # synthetic fixtures, not the coverage policy (covered in test_coverage_gate.py
        # with production thresholds).
        min_pos_survival=0.0, min_effective_npos=1, min_survive_countries=1,
        min_neg_survival=0.0,
    )


def test_greedy_deterministic_selection_order(fake_inner):
    """Sanity: with the fake inner fns greedy selects highest-value candidates
    in order, at the max window."""
    res = _run(["c", "a", "b"], max_steps=3)
    assert res["selected_indicators"] == ["a", "b", "c"]
    assert res["chosen_window"] == 10  # max of [5,10]


_SIG = lambda cands, steps=3, seed=0, fp="fp0": drv.greedy_config_signature(  # noqa: E731
    "r", cands, "LR", drv.DELTA_STEP, steps, seed, fp)


def test_no_checkpoint_writes_no_file(fake_inner, tmp_path):
    """With checkpoint_path given but sig None (half-configured), the write path
    must be suppressed — proving the no-op is the AND of both params, not just
    that we happened to pass None for the path."""
    ckpt = tmp_path / drv.GREEDY_CHECKPOINT_NAME
    _run(["a", "b", "c"], max_steps=3, checkpoint_path=ckpt, sig=None)
    assert not ckpt.exists(), "checkpoint must not be written when config_signature is None"


def test_checkpoint_written_after_each_step(fake_inner, tmp_path):
    """A checkpoint file is written and reflects the final committed state."""
    ckpt = tmp_path / drv.GREEDY_CHECKPOINT_NAME
    sig = _SIG(["a", "b", "c"])
    res = _run(["a", "b", "c"], max_steps=3, checkpoint_path=ckpt, sig=sig)
    assert ckpt.exists()
    env = json.loads(ckpt.read_text(encoding="utf-8"))
    assert env["config_signature"] == sig
    assert env["state"]["selected"] == res["selected_indicators"]
    assert env["state"]["step"] == len(res["selected_indicators"])


def _craft_checkpoint(path, sig, full, up_to_step, candidates):
    """Build a checkpoint as if the walk committed `up_to_step` steps."""
    hist = full["history"][:up_to_step]
    selected = [h["candidate"] for h in hist]
    last = hist[-1]
    drv._write_json_atomic(path, {
        "schema_version": drv.CHECKPOINT_SCHEMA_VERSION,
        "config_signature": sig,
        "state": {
            "selected": selected,
            "chosen_window": last["window"],
            "remaining": [x for x in candidates if x not in selected],
            "current_auc": last["auc"],
            "step": up_to_step,
            "history": hist,
        },
    })


@pytest.mark.parametrize("up_to_step", [1, 2, 3])
def test_resume_reproduces_uninterrupted_run(fake_inner, tmp_path, up_to_step):
    """THE core guarantee: a run resumed from a mid-greedy checkpoint (after
    step 1, 2, or 3) produces the identical final result to an uninterrupted run."""
    candidates = ["a", "b", "c", "d"]
    sig = _SIG(candidates, steps=4)
    full = _run(candidates, max_steps=4)  # uninterrupted reference

    ckpt = tmp_path / drv.GREEDY_CHECKPOINT_NAME
    _craft_checkpoint(ckpt, sig, full, up_to_step, candidates)
    resumed = _run(candidates, max_steps=4, checkpoint_path=ckpt, sig=sig)

    assert resumed["selected_indicators"] == full["selected_indicators"]
    assert resumed["chosen_window"] == full["chosen_window"]
    assert abs(resumed["final_global_auc"] - full["final_global_auc"]) < 1e-9
    assert [h["candidate"] for h in resumed["history"]] == [h["candidate"] for h in full["history"]]


def test_resume_from_fully_committed_checkpoint_is_noop(fake_inner, tmp_path):
    """Resuming from an all-steps-committed checkpoint returns immediately with
    the same result (the while-loop exits on empty `remaining` / step cap)."""
    candidates = ["a", "b", "c"]
    sig = _SIG(candidates, steps=3)
    full = _run(candidates, max_steps=3)
    ckpt = tmp_path / drv.GREEDY_CHECKPOINT_NAME
    _craft_checkpoint(ckpt, sig, full, up_to_step=3, candidates=candidates)
    resumed = _run(candidates, max_steps=3, checkpoint_path=ckpt, sig=sig)
    assert resumed["selected_indicators"] == full["selected_indicators"]


def test_resume_rejected_when_data_fingerprint_differs(fake_inner, tmp_path):
    """BLOCKER FIX (review 2026-05-24): a checkpoint from the SAME config but a
    DIFFERENT data fingerprint (panels/positives updated) must be REJECTED —
    never silently resumed onto new data. This is the 4x/year-cadence guard."""
    candidates = ["a", "b", "c"]
    old_sig = _SIG(candidates, steps=3, fp="DATA_VINTAGE_OLD")
    new_sig = _SIG(candidates, steps=3, fp="DATA_VINTAGE_NEW")
    assert old_sig != new_sig, "different data fingerprint must change the signature"
    full = _run(candidates, max_steps=3)
    ckpt = tmp_path / drv.GREEDY_CHECKPOINT_NAME
    _craft_checkpoint(ckpt, old_sig, full, up_to_step=1, candidates=candidates)
    # Run with the NEW data signature → old checkpoint ignored → fresh start.
    res = _run(candidates, max_steps=3, checkpoint_path=ckpt, sig=new_sig)
    assert res["selected_indicators"] == ["a", "b", "c"]  # fresh best-first, not seeded


def test_resume_ignores_mismatched_signature(fake_inner, tmp_path):
    """A checkpoint from a DIFFERENT config must be ignored → run starts fresh,
    never silently resumes the wrong walk."""
    candidates = ["a", "b", "c"]
    wrong_sig = drv.greedy_config_signature("OTHER", candidates, "LR", drv.DELTA_STEP, 3, 999, "fp0")
    ckpt = tmp_path / drv.GREEDY_CHECKPOINT_NAME
    drv._write_json_atomic(ckpt, {
        "schema_version": drv.CHECKPOINT_SCHEMA_VERSION,
        "config_signature": wrong_sig,
        "state": {"selected": ["c"], "chosen_window": 5, "remaining": ["a", "b"],
                  "current_auc": 0.55, "step": 1, "history": [{"step": 1, "candidate": "c",
                  "window": 5, "auc": 0.55, "lift_over_previous": 0.05, "selected_after": ["c"]}]},
    })
    right_sig = _SIG(candidates, steps=3)
    res = _run(candidates, max_steps=3, checkpoint_path=ckpt, sig=right_sig)
    # Started fresh → normal best-first order, NOT seeded with "c".
    assert res["selected_indicators"] == ["a", "b", "c"]


def test_resume_ignores_corrupt_checkpoint(fake_inner, tmp_path):
    """A corrupt checkpoint file must be ignored → run starts fresh."""
    ckpt = tmp_path / drv.GREEDY_CHECKPOINT_NAME
    ckpt.write_text("{ this is not valid json", encoding="utf-8")
    sig = _SIG(["a", "b", "c"], steps=3)
    res = _run(["a", "b", "c"], max_steps=3, checkpoint_path=ckpt, sig=sig)
    assert res["selected_indicators"] == ["a", "b", "c"]


def test_panel_data_fingerprint_changes_on_content_change(tmp_path):
    """The data fingerprint (stat-based) must change when a panel file's size
    changes — the mechanism behind the 4x/year resume-rejection guard."""
    pdir = tmp_path / "panels"
    pdir.mkdir()
    (pdir / "RQ.EST.parquet").write_bytes(b"x" * 100)
    (pdir / "v2pepwrgen.parquet").write_bytes(b"y" * 200)
    fp1 = drv.panel_data_fingerprint(pdir)
    fp2 = drv.panel_data_fingerprint(pdir)
    assert fp1 == fp2, "fingerprint must be stable for unchanged files"
    (pdir / "RQ.EST.parquet").write_bytes(b"x" * 999)  # data updated
    fp3 = drv.panel_data_fingerprint(pdir)
    assert fp3 != fp1, "fingerprint must change when panel content changes"
