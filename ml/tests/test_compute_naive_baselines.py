"""Unit tests for compute_naive_baselines.py (#113 greenfield floor provenance)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import compute_naive_baselines as nb  # noqa: E402


def test_build_samples_refactor_deterministic_and_counts():
    """build_samples (extracted from the walk for LOCO parity) is seed-deterministic
    and yields negatives_per_positive negatives per positive."""
    import run_f_ml_1_poc as drv
    pos = pd.DataFrame({"country": ["Iran", "Iran", "Syria", "Iraq"],
                        "year": [1990, 1995, 2001, 2003], "label": [1, 1, 1, 1]})
    s1 = drv.build_samples(pos, negatives_per_positive=3, seed=7)
    s2 = drv.build_samples(pos, negatives_per_positive=3, seed=7)
    assert (s1["label"] == 1).sum() == 4 and (s1["label"] == 0).sum() == 12
    pd.testing.assert_frame_equal(s1, s2)               # seed-deterministic
    # negatives never collide with positives
    pos_set = set(zip(pos["country"], pos["year"]))
    negs = s1[s1["label"] == 0]
    assert not any((c, y) in pos_set for c, y in zip(negs["country"], negs["year"]))


def test_persistence_feature_causal_and_recency():
    pos = pd.DataFrame({"country": ["Iran", "Iran", "Syria"], "year": [1990, 1995, 2001],
                        "label": [1, 1, 1]})
    samples = pd.DataFrame({
        "country": ["Iran", "Iran", "Iran", "Syria", "Syria"],
        "year":    [1990,   1991,   1996,   2000,    2002],
        "label":   [1,      0,      0,      0,       1],
    })
    s = nb.persistence_feature(samples, pos).ravel()
    # Iran 1990: no prior (<1990) -> 0
    assert s[0] == 0.0
    # Iran 1991: prior {1990} -> 1/(1+1)=0.5
    assert abs(s[1] - 0.5) < 1e-9
    # Iran 1996: priors {1990,1995}, most recent 1995 -> 1/(1+1)=0.5
    assert abs(s[2] - 0.5) < 1e-9
    # Syria 2000: Syria's only positive is 2001 (not < 2000) -> 0 (causal: no future leak)
    assert s[3] == 0.0
    # Syria 2002: prior {2001} -> 1/(1+1)=0.5
    assert abs(s[4] - 0.5) < 1e-9


def test_bootstrap_auc_ci_ordering_and_determinism():
    rng = np.random.default_rng(0)
    # well-separated probs vs labels -> high AUC
    labels = np.array([0] * 50 + [1] * 50)
    probs = np.concatenate([rng.uniform(0, 0.5, 50), rng.uniform(0.5, 1.0, 50)])
    point, lo, hi = nb._bootstrap_auc_ci(probs, labels, n_boot=500, seed=42)
    assert lo <= point <= hi
    assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0
    # determinism
    p2, lo2, hi2 = nb._bootstrap_auc_ci(probs, labels, n_boot=500, seed=42)
    assert (point, lo, hi) == (p2, lo2, hi2)


def _synth_panel(countries, years, slope):
    rows = []
    for ci, c in enumerate(countries):
        for y in years:
            rows.append({"country": c, "year": y, "value": slope * ci + 0.1 * (y - years[0])})
    return pd.DataFrame(rows)


def test_compute_naive_baseline_smoke_and_floor(tmp_path):
    countries = [f"C{i:02d}" for i in range(14)]
    years = list(range(1985, 2016))
    panels = {"IND_A": _synth_panel(countries, years, 1.0),
              "IND_B": _synth_panel(countries, years, 0.3)}
    # positives: a handful (thin recipe, N_pos < 150)
    pos_rows = [("c00", 2000), ("c01", 2002), ("c02", 2004), ("c03", 2006),
                ("c04", 2008), ("c05", 2010), ("c06", 2012), ("c07", 2014)]
    pdir = tmp_path / "shape" / "smoke"
    pdir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(pos_rows, columns=["country_id", "event_year"]).to_csv(pdir / "positives.csv", index=False)

    r = nb.compute_naive_baseline("smoke", pdir / "positives.csv", tmp_path, ["IND_A", "IND_B"],
                                  panels, negatives_per_positive=3, seed=0, n_bootstrap=200)
    # schema
    for k in ("naive_loco", "lock_floor", "floor_basis", "naive_ci95", "nb1_persistence_loco",
              "nb2_single_indicator_loco", "thin", "panel_fingerprint"):
        assert k in r
    # floor obeys the absolute backstop + the formula
    assert r["lock_floor"] >= nb.ABS_FLOOR - 1e-9
    assert abs(r["lock_floor"] - max(r["relative_floor"], nb.ABS_FLOOR)) < 1e-9
    assert r["thin"] is True  # N_pos = 8 < 150
    # thin recipe anchors the basis to the upper CI
    assert abs(r["naive_basis_for_floor"] - r["naive_ci95"][1]) < 1e-9
    assert 0.0 <= r["naive_loco"] <= 1.0
    assert r["naive_winner"] in ("NB1_persistence", "NB2_single_indicator")


def test_floor_basis_label_matches_value(tmp_path):
    """floor_basis tracks the value: 'absolute_0.70' below the backstop, 'capped_0.90'
    when the relative floor would exceed the cap, else 'relative'."""
    countries = [f"C{i:02d}" for i in range(12)]
    years = list(range(1990, 2016))
    panels = {"IND_A": _synth_panel(countries, years, 0.05)}  # weak signal
    pos_rows = [(f"c{i:02d}", 2000 + i) for i in range(6)]
    pdir = tmp_path / "shape" / "weak"
    pdir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(pos_rows, columns=["country_id", "event_year"]).to_csv(pdir / "positives.csv", index=False)
    r = nb.compute_naive_baseline("weak", pdir / "positives.csv", tmp_path, ["IND_A"],
                                  panels, n_bootstrap=200, seed=0)
    if r["relative_floor"] < nb.ABS_FLOOR:
        assert r["floor_basis"] == "absolute_0.70"
        assert abs(r["lock_floor"] - nb.ABS_FLOOR) < 1e-9
    elif r["relative_floor"] > nb.FLOOR_CAP:
        assert r["floor_basis"] == "capped_0.90"
        assert abs(r["lock_floor"] - nb.FLOOR_CAP) < 1e-9
    else:
        assert r["floor_basis"] == "relative"
    # lock_floor never exceeds the cap, whatever the basis
    assert r["lock_floor"] <= nb.FLOOR_CAP + 1e-9
