"""check_new_indicator_leakage.py — FLEET-7 / trio Condition C leakage-canary.

Static checks (stationarity / allow-list / units / no-future-leak) are NECESSARY but
NOT SUFFICIENT: the foreign_intervention truncation leak passed every static check and
only died on a coverage audit. Before a NEW indicator joins the shared ~104-indicator
pool (where it could inflate selection across many recipes at once), run it as a
*univariate* LOCO across a few diverse REFERENCE recipes it has no mechanistic business
predicting. An indicator that scores implausibly high (≥ threshold) across unrelated
recipes is exhibiting the leak signature (it encodes the outcome/time, not the substrate)
→ HOLD for human review rather than auto-admit to the pool.

This is a GATE, not a narration (Ji-Hoon: make #957 a hard blocker). Verdict HOLD must
block pool admission until a human clears it. Cheap: loads only the one new panel.

Usage:
  python scripts/check_new_indicator_leakage.py --indicator NEW.IND.CODE \
      [--reference-recipes a b c] [--threshold 0.85] [--window 10]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import run_f_ml_1_poc as drv  # noqa: E402

# Diverse, substantively unrelated reference recipes — a single new indicator should NOT
# discriminate all of these well on its own. Overridable via --reference-recipes.
DEFAULT_REFERENCE_RECIPES = ["currency_crisis", "natural_disaster", "elections_and_voting"]
LEAK_THRESHOLD = 0.85   # univariate LOCO-AUC at/above this on an unrelated recipe = suspicious
SCREEN_WINDOW = 10


def classify_leakage(per_recipe_auc: dict[str, float | None],
                     threshold: float = LEAK_THRESHOLD) -> dict[str, Any]:
    """Pure verdict: HOLD if the indicator scores ≥ threshold (univariate LOCO) on ANY
    reference recipe it should not predict; else PASS. NaN/None AUCs (coverage-failed or
    unbuildable) are ignored, not treated as passes. Testable."""
    flagged = {
        r: round(float(a), 4)
        for r, a in per_recipe_auc.items()
        if a is not None and not math.isnan(float(a)) and float(a) >= threshold
    }
    return {
        "verdict": "HOLD_SUSPECTED_LEAK" if flagged else "PASS",
        "threshold": threshold,
        "flagged_recipes": flagged,
        "per_recipe_auc": {r: (None if a is None or math.isnan(float(a)) else round(float(a), 4))
                           for r, a in per_recipe_auc.items()},
    }


def univariate_auc_for_recipe(indicator: str, positives_csv: Path,
                              panels: dict[str, pd.DataFrame], window: int = SCREEN_WINDOW,
                              negatives_per_positive: int = 3, seed: int = 0) -> float | None:
    """Univariate LOCO-AUC of `indicator` alone on one recipe (mirrors the NB2 path in
    compute_naive_baselines: same build_samples + build_X_y + fit_predict_loco). Returns
    None if the cell is unbuildable (too few rows / one class)."""
    pos = pd.read_csv(positives_csv)
    pos["country"] = pos["country_id"].apply(drv.normalize_country_id)
    pos = pos.rename(columns={"event_year": "year"})
    pos["label"] = 1
    samples = drv.build_samples(pos, negatives_per_positive=negatives_per_positive, seed=seed)
    X, y, c, yr = drv.build_X_y(samples, [indicator], window, panels)
    if len(X) < 30 or len(np.unique(y)) < 2:
        return None
    return float(drv.fit_predict_loco(X, y, c, yr, architecture="LR", seed=seed)["global_auc"])


def run_leakage_canary(indicator: str, reference_recipes: list[str], shape_inputs_dir: Path,
                       panel_dir: Path, window: int = SCREEN_WINDOW,
                       threshold: float = LEAK_THRESHOLD, seed: int = 0) -> dict[str, Any]:
    panels = {indicator: drv.load_panel(indicator, panel_dir)}  # only the new panel — cheap
    per_recipe_auc: dict[str, float | None] = {}
    for rid in reference_recipes:
        pcsv = shape_inputs_dir / rid / "positives.csv"
        if not pcsv.exists():
            per_recipe_auc[rid] = None
            continue
        per_recipe_auc[rid] = univariate_auc_for_recipe(
            indicator, pcsv, panels, window=window, seed=seed)
    out = classify_leakage(per_recipe_auc, threshold)
    out["indicator"] = indicator
    out["window"] = window
    return out


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--indicator", required=True, help="new indicator id to vet")
    p.add_argument("--reference-recipes", nargs="+", default=DEFAULT_REFERENCE_RECIPES)
    p.add_argument("--shape-inputs-dir", type=Path, default=REPO_ROOT / "data" / "shape_inputs_v2")
    p.add_argument("--panel-dir", type=Path, default=REPO_ROOT / "data" / "parquet_panels")
    p.add_argument("--threshold", type=float, default=LEAK_THRESHOLD)
    p.add_argument("--window", type=int, default=SCREEN_WINDOW)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)

    result = run_leakage_canary(args.indicator, args.reference_recipes, args.shape_inputs_dir,
                                args.panel_dir, window=args.window, threshold=args.threshold,
                                seed=args.seed)
    txt = json.dumps(result, indent=2)
    print(txt)
    if args.out:
        args.out.write_text(txt, encoding="utf-8")
    # Non-zero exit on HOLD so a CI / ingestion gate blocks pool admission (hard blocker).
    return 1 if result["verdict"] == "HOLD_SUSPECTED_LEAK" else 0


if __name__ == "__main__":
    raise SystemExit(_main())
