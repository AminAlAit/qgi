"""Unit tests for FLEET-7 / Condition C leakage-canary (check_new_indicator_leakage).

Covers the pure verdict logic (classify_leakage) and the per-recipe orchestration with
the expensive LOCO monkeypatched out. The contract: a new indicator that scores
implausibly high (univariate LOCO ≥ threshold) on a reference recipe it should not
predict is HELD for human review (the leak signature); NaN/None scores are ignored,
never treated as a pass.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import check_new_indicator_leakage as canary  # noqa: E402


# ---- pure verdict logic ----------------------------------------------------

def test_pass_when_all_below_threshold():
    out = canary.classify_leakage({"a": 0.61, "b": 0.55, "c": 0.70}, threshold=0.85)
    assert out["verdict"] == "PASS"
    assert out["flagged_recipes"] == {}


def test_hold_when_any_at_or_above_threshold():
    out = canary.classify_leakage({"a": 0.62, "b": 0.91, "c": 0.58}, threshold=0.85)
    assert out["verdict"] == "HOLD_SUSPECTED_LEAK"
    assert out["flagged_recipes"] == {"b": 0.91}


def test_boundary_is_inclusive():
    """AUC exactly == threshold must HOLD (implausible discrimination is suspicious)."""
    out = canary.classify_leakage({"a": 0.85}, threshold=0.85)
    assert out["verdict"] == "HOLD_SUSPECTED_LEAK"


def test_nan_and_none_ignored_not_passed():
    out = canary.classify_leakage({"a": float("nan"), "b": None, "c": 0.60}, threshold=0.85)
    assert out["verdict"] == "PASS"
    assert out["per_recipe_auc"]["a"] is None and out["per_recipe_auc"]["b"] is None


def test_nan_does_not_mask_a_real_leak():
    out = canary.classify_leakage({"a": float("nan"), "b": 0.97}, threshold=0.85)
    assert out["verdict"] == "HOLD_SUSPECTED_LEAK"
    assert out["flagged_recipes"] == {"b": 0.97}


# ---- orchestration (LOCO monkeypatched) ------------------------------------

@pytest.fixture
def fake_loco(monkeypatch, tmp_path):
    """Stub build_samples/build_X_y/fit_predict_loco so run_leakage_canary needs no
    panels or real solver; AUC per recipe is injected via `aucs`."""
    monkeypatch.setattr(canary.drv, "load_panel", lambda ind, d: object())
    monkeypatch.setattr(canary.drv, "normalize_country_id", lambda x: x)
    monkeypatch.setattr(canary.drv, "build_samples",
                        lambda pos, negatives_per_positive=3, seed=0: pos)
    aucs: dict[str, float] = {}

    # AUC keyed by the positives_csv parent dir name (the recipe id)
    def fake_uni(indicator, positives_csv, panels, window=10, negatives_per_positive=3, seed=0):
        return aucs.get(positives_csv.parent.name)

    monkeypatch.setattr(canary, "univariate_auc_for_recipe", fake_uni)
    return aucs, tmp_path


def _mk_recipe(root, rid):
    d = root / rid
    d.mkdir(parents=True, exist_ok=True)
    (d / "positives.csv").write_text("country_id,event_year\nx,2000\n", encoding="utf-8")
    return d


def test_run_canary_holds_on_high_unrelated_score(fake_loco):
    aucs, root = fake_loco
    for rid in ("currency_crisis", "natural_disaster"):
        _mk_recipe(root, rid)
    aucs.update({"currency_crisis": 0.60, "natural_disaster": 0.93})  # leak-like on one
    out = canary.run_leakage_canary("NEW.IND", ["currency_crisis", "natural_disaster"],
                                    shape_inputs_dir=root, panel_dir=root)
    assert out["verdict"] == "HOLD_SUSPECTED_LEAK"
    assert out["indicator"] == "NEW.IND"
    assert set(out["flagged_recipes"]) == {"natural_disaster"}


def test_run_canary_passes_clean_indicator(fake_loco):
    aucs, root = fake_loco
    for rid in ("currency_crisis", "natural_disaster"):
        _mk_recipe(root, rid)
    aucs.update({"currency_crisis": 0.58, "natural_disaster": 0.63})
    out = canary.run_leakage_canary("NEW.IND", ["currency_crisis", "natural_disaster"],
                                    shape_inputs_dir=root, panel_dir=root)
    assert out["verdict"] == "PASS"


def test_run_canary_missing_positives_is_none_not_pass(fake_loco):
    aucs, root = fake_loco
    _mk_recipe(root, "currency_crisis")
    aucs.update({"currency_crisis": 0.60})  # natural_disaster has no positives.csv → None
    out = canary.run_leakage_canary("NEW.IND", ["currency_crisis", "natural_disaster"],
                                    shape_inputs_dir=root, panel_dir=root)
    assert out["per_recipe_auc"]["natural_disaster"] is None
    assert out["verdict"] == "PASS"


def test_main_exit_code_gates_on_hold(fake_loco):
    """The CI/ingestion-gate contract: _main exits 1 on HOLD, 0 on PASS."""
    aucs, root = fake_loco
    _mk_recipe(root, "currency_crisis")
    args = ["--indicator", "X", "--reference-recipes", "currency_crisis",
            "--shape-inputs-dir", str(root), "--panel-dir", str(root)]
    aucs["currency_crisis"] = 0.95
    assert canary._main(args) == 1     # HOLD → non-zero (blocks admission)
    aucs["currency_crisis"] = 0.55
    assert canary._main(args) == 0     # PASS → zero
