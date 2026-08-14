"""
Unit tests for summarize_gamma_sensitivity.py (T2 / #666 / Phase 5 v0.2
charter γ-stage transparency artifact).

The script is a pure-function aggregator over per-arm validation JSONs
produced by validate_weight_matrix.py v5. Tests cover:
  - happy path (4 arms × 5 thresholds → table + N=30 breach flags)
  - hard-error on pre-v5 inputs (missing stratum_sensitivity)
  - A-D delta math
  - N=30 floor breach detection
  - missing-arm-threshold tolerance (None propagated, not crash)

Generated: 2026-05-12
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "summarize_gamma_sensitivity.py"
)
_spec = importlib.util.spec_from_file_location("summarize_gamma_sensitivity", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["summarize_gamma_sensitivity"] = mod
_spec.loader.exec_module(mod)


def _make_arm_json(tmp_path: Path, arm_label: str,
                   per_threshold: dict[int, dict]) -> Path:
    """Write a minimal per-arm validation JSON with the stratum_sensitivity
    block populated from `per_threshold`. Returns the path."""
    entries = [
        {
            "threshold": t,
            "n_cells": v["n_cells"],
            "n_categories": v["n_categories"],
            "mean_auc": v["mean_auc"],
            "median_auc": v["median_auc"],
        }
        for t, v in sorted(per_threshold.items())
    ]
    payload = {
        "schema_version": 4,
        "ablation_arm": arm_label,
        "stratum_sensitivity": {
            "thresholds_swept": [e["threshold"] for e in entries],
            "entries": entries,
        },
    }
    path = tmp_path / f"arm{arm_label}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_table_happy_path(tmp_path):
    """4 arms × 5 thresholds → table has 5 rows, one per threshold,
    each carrying arm_A/B/C/D blocks + a_minus_d_mean_auc delta."""
    def stub(mean_a):
        return {
            t: {"n_cells": 40 + t, "n_categories": 5,
                "mean_auc": mean_a, "median_auc": mean_a}
            for t in (3, 5, 7, 10, 15)
        }

    paths = {
        "A": _make_arm_json(tmp_path, "A", stub(0.610)),
        "B": _make_arm_json(tmp_path, "B", stub(0.600)),
        "C": _make_arm_json(tmp_path, "C", stub(0.605)),
        "D": _make_arm_json(tmp_path, "D", stub(0.603)),
    }
    arms = {label: mod._load_arm(p) for label, p in paths.items()}
    summary = mod.build_table(arms)

    assert summary["schema_version"] == 1
    assert summary["thresholds_swept"] == [3, 5, 7, 10, 15]
    assert len(summary["table"]) == 5
    for row in summary["table"]:
        for label in ("A", "B", "C", "D"):
            assert row[f"arm_{label}"] is not None
            assert row[f"arm_{label}"]["mean_auc"] == pytest.approx(
                {"A": 0.610, "B": 0.600, "C": 0.605, "D": 0.603}[label]
            )
        # A - D = 0.610 - 0.603 = 0.007
        assert row["a_minus_d_mean_auc"] == pytest.approx(0.007, abs=1e-9)


def test_load_arm_rejects_pre_v5_json(tmp_path):
    """A JSON missing `stratum_sensitivity` is from a pre-v5 run; the
    loader must raise rather than silently emit a half-populated table."""
    bad = tmp_path / "armD.json"
    bad.write_text(json.dumps({"schema_version": 4, "ablation_arm": "D"}),
                   encoding="utf-8")
    with pytest.raises(ValueError, match="stratum_sensitivity"):
        mod._load_arm(bad)


def test_n30_floor_breach_detection(tmp_path):
    """When an arm × threshold has n_cells < 30, the summary must flag
    it in `n30_floor_breach_by_threshold` and list the breaching arms."""
    # Arm A: n_cells = 25 at threshold=10 only → breach at t=10
    arm_a = {t: {"n_cells": 50, "n_categories": 5,
                 "mean_auc": 0.60, "median_auc": 0.60}
             for t in (3, 5, 7, 10, 15)}
    arm_a[10]["n_cells"] = 25
    arm_a[15]["n_cells"] = 12

    other = {t: {"n_cells": 50, "n_categories": 5,
                 "mean_auc": 0.60, "median_auc": 0.60}
             for t in (3, 5, 7, 10, 15)}

    paths = {
        "A": _make_arm_json(tmp_path, "A", arm_a),
        "B": _make_arm_json(tmp_path, "B", other),
        "C": _make_arm_json(tmp_path, "C", other),
        "D": _make_arm_json(tmp_path, "D", other),
    }
    arms = {label: mod._load_arm(p) for label, p in paths.items()}
    summary = mod.build_table(arms)
    breach = summary["n30_floor_breach_by_threshold"]
    assert breach["3"]["any_arm_below_n30"] is False
    assert breach["10"]["any_arm_below_n30"] is True
    assert breach["10"]["arms_below_n30"] == ["A"]
    assert breach["15"]["any_arm_below_n30"] is True
    assert breach["15"]["arms_below_n30"] == ["A"]
    # PR #56 review fix 2: data-missing must be disjoint from n30-below
    # at every threshold for this fixture (no rows are missing).
    for t_str, info in breach.items():
        assert info["any_arm_data_missing"] is False
        assert info["arms_data_missing"] == []
    # back-compat alias `arms_below` equals arms_below_n30 (NOT a union)
    assert breach["10"]["arms_below"] == breach["10"]["arms_below_n30"]


def test_data_missing_disjoint_from_n30_breach(tmp_path):
    """PR #56 review fix 2: when a per-arm JSON omits a threshold row
    (e.g. configuration error), it is flagged as `arms_data_missing` NOT
    as an N=30 breach. These two conditions must remain disjoint."""
    # Arm A is fine at every threshold except t=10 (row omitted entirely)
    arm_a_partial = {t: {"n_cells": 50, "n_categories": 5,
                         "mean_auc": 0.60, "median_auc": 0.60}
                     for t in (3, 5, 7, 15)}  # NOTE: 10 omitted

    other = {t: {"n_cells": 50, "n_categories": 5,
                 "mean_auc": 0.60, "median_auc": 0.60}
             for t in (3, 5, 7, 10, 15)}

    paths = {
        "A": _make_arm_json(tmp_path, "A", arm_a_partial),
        "B": _make_arm_json(tmp_path, "B", other),
        "C": _make_arm_json(tmp_path, "C", other),
        "D": _make_arm_json(tmp_path, "D", other),
    }
    arms = {label: mod._load_arm(p) for label, p in paths.items()}
    summary = mod.build_table(arms)
    breach_t10 = summary["n30_floor_breach_by_threshold"]["10"]
    assert breach_t10["any_arm_data_missing"] is True
    assert breach_t10["arms_data_missing"] == ["A"]
    # Crucially: arm A at t=10 is NOT a "below N=30" breach — its data
    # is simply absent. Conflating these would corrupt the Majles artifact.
    assert breach_t10["any_arm_below_n30"] is False
    assert breach_t10["arms_below_n30"] == []
    # Back-compat `arms_below` equals arms_below_n30 (NOT a union)
    assert breach_t10["arms_below"] == []


def test_a_minus_d_delta_none_when_endpoint_missing(tmp_path):
    """If arm A or arm D has a None mean_auc at a threshold, the A-D
    delta must be None rather than crashing or coercing to 0."""
    arm_a = {t: {"n_cells": 50, "n_categories": 5,
                 "mean_auc": 0.60, "median_auc": 0.60}
             for t in (3, 5, 7, 10, 15)}
    arm_a[3]["mean_auc"] = None
    arm_a[3]["median_auc"] = None

    other = {t: {"n_cells": 50, "n_categories": 5,
                 "mean_auc": 0.60, "median_auc": 0.60}
             for t in (3, 5, 7, 10, 15)}

    paths = {
        "A": _make_arm_json(tmp_path, "A", arm_a),
        "B": _make_arm_json(tmp_path, "B", other),
        "C": _make_arm_json(tmp_path, "C", other),
        "D": _make_arm_json(tmp_path, "D", other),
    }
    arms = {label: mod._load_arm(p) for label, p in paths.items()}
    summary = mod.build_table(arms)
    row_t3 = next(r for r in summary["table"] if r["threshold"] == 3)
    assert row_t3["a_minus_d_mean_auc"] is None
    row_t5 = next(r for r in summary["table"] if r["threshold"] == 5)
    assert row_t5["a_minus_d_mean_auc"] == pytest.approx(0.0, abs=1e-9)


def test_thresholds_constant_is_frozen():
    """The module exposes THRESHOLDS = (3, 5, 7, 10, 15). This is the
    Phase 5 v0.2 charter γ-sweep set — changing it requires an amendment."""
    assert mod.THRESHOLDS == (3, 5, 7, 10, 15)


def test_main_writes_output_file(tmp_path, monkeypatch, capsys):
    """End-to-end main() — 4 arm JSONs → 1 summary JSON, stdout has
    the breadcrumb table."""
    def stub(mean):
        return {
            t: {"n_cells": 40, "n_categories": 5,
                "mean_auc": mean, "median_auc": mean}
            for t in (3, 5, 7, 10, 15)
        }

    arm_paths = {
        "A": _make_arm_json(tmp_path, "A", stub(0.610)),
        "B": _make_arm_json(tmp_path, "B", stub(0.600)),
        "C": _make_arm_json(tmp_path, "C", stub(0.605)),
        "D": _make_arm_json(tmp_path, "D", stub(0.603)),
    }
    out_path = tmp_path / "out" / "gamma-summary.json"

    monkeypatch.setattr("sys.argv", [
        "summarize_gamma_sensitivity.py",
        "--arm-a", str(arm_paths["A"]),
        "--arm-b", str(arm_paths["B"]),
        "--arm-c", str(arm_paths["C"]),
        "--arm-d", str(arm_paths["D"]),
        "--out", str(out_path),
    ])
    mod.main()

    assert out_path.exists()
    summary = json.loads(out_path.read_text(encoding="utf-8"))
    assert summary["schema_version"] == 1
    assert len(summary["table"]) == 5
    assert summary["input_arm_files"]["A"] == str(arm_paths["A"])
    captured = capsys.readouterr()
    assert "γ sensitivity" in captured.out or "gamma" in captured.out.lower()
