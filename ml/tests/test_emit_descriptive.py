"""Regression test for §F: emit_descriptive must emit the FULL positive corpus into
ranked_trajectory_signature (was capped at head(5)). The bake aggregates the canonical
shape over however many positives are present, so the cap is what bounded it to 5.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_f_ml_1_poc as walk  # noqa: E402


def _panel(countries, years, base=100.0):
    rows = []
    for c in countries:
        for i, y in enumerate(years):
            rows.append({"country": c, "year": y, "value": base + i})  # rising series
    return pd.DataFrame(rows)


def test_emit_descriptive_emits_all_positives_not_head5():
    # 6 positives — strictly more than the old head(5) cap. Each has a clean 25y
    # history so extract_trajectory_signature_full returns available=True.
    countries = ["A", "B", "C", "D", "E", "F"]
    years = list(range(1990, 2011))
    panels = {"ind1": _panel(countries + ["Z"], years)}
    samples = pd.DataFrame(
        [{"country": c, "year": 2010, "label": 1} for c in countries]
        + [{"country": "Z", "year": 2010, "label": 0}]
    )
    out = walk.emit_descriptive(
        selected=["ind1"], chosen_window=3, panels=panels, samples=samples,
        final_loco={}, architecture="XGBoost", feature_importances=[0.1] * 8,
        audit_chart_path=Path("/tmp/audit.png"),
    )
    sigs = out["ranked_trajectory_signature"]["per_indicator_signatures"][0]["samples"]
    assert len(sigs) == 6  # all 6 positives (head(5) would have given 5)
    # negatives are never used as canonical-shape samples
    assert all(s["country"] in countries for s in sigs)
