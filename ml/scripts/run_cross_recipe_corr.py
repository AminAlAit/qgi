"""# THROWAWAY -- one-off audit script. Phase D D6 cross-recipe correlation
tensor over time.

Per docs/specs/internal/ops/ml-track/stage-2-amendment-2026-05-05.md
(commit `04fa5fb`) D6 — Ji-Hoon's "free inference" proposal.

Loads existing predictions JSON (Stage 1 v0 tuned), computes the
recipe-recipe correlation matrix per test year, tracks stability
over time, and identifies persistent high-correlation recipe pairs.

Usage::

    python scripts/run_cross_recipe_corr.py \\
        --predictions results/hp_sweep_5_30_2/predictions.json \\
        --out ../qgi-data/reference/cross-recipe-corr-2026-05.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SHARED_ROOT = REPO_ROOT / "shared"
for _p in (str(SRC_ROOT), str(SCRIPTS_ROOT), str(SHARED_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cross_recipe_corr import (  # noqa: E402
    compute_per_year_snapshots,
    find_persistent_high_corrs,
    matrix_stability_over_time,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--predictions", type=Path, required=True)
    p.add_argument("--method", choices=["pearson", "spearman"], default="pearson")
    p.add_argument("--min-countries-per-year", type=int, default=30)
    p.add_argument("--persistent-threshold", type=float, default=0.7)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not args.predictions.exists():
        print(f"ERROR: predictions not found: {args.predictions}", file=sys.stderr)
        return 2

    print(f"[corr] reading {args.predictions}", file=sys.stderr)
    with args.predictions.open(encoding="utf-8") as f:
        payload = json.load(f)
    predictions = payload.get("predictions", payload if isinstance(payload, list) else [])
    if not predictions:
        print("ERROR: empty predictions list", file=sys.stderr)
        return 2
    print(f"[corr] loaded {len(predictions)} prediction rows", file=sys.stderr)

    print("[corr] computing per-year snapshots...", file=sys.stderr)
    snapshots = compute_per_year_snapshots(
        predictions, method=args.method,
        min_countries_per_year=args.min_countries_per_year,
    )
    n_valid = sum(1 for s in snapshots if s.skip_reason is None)
    print(f"[corr] snapshots: {len(snapshots)} years, {n_valid} valid",
          file=sys.stderr)

    stability = matrix_stability_over_time(snapshots)
    persistent = find_persistent_high_corrs(snapshots, threshold=args.persistent_threshold)

    print("[corr] stability:", stability.get("mean_distance"), file=sys.stderr)
    print(f"[corr] persistent high-corr pairs: {len(persistent)}", file=sys.stderr)

    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Phase D D6 cross-recipe correlation tensor over time. "
            "Free-inference diagnostic per Ji-Hoon Yamamoto-Costa's "
            "post-PoC trio recommendation 2026-05-05. Stable matrix = "
            "recipes measure distinct phenomena. Shifting matrix = "
            "regime change signal. Persistent high-corr pairs = "
            "informationally redundant recipes (consider consolidation)."
        ),
        "method": {
            "correlation": args.method,
            "min_countries_per_year": args.min_countries_per_year,
            "persistent_threshold": args.persistent_threshold,
            "stability_metric": "frobenius_norm_distance_between_consecutive_year_matrices",
            "scope": "per_year_recipe_recipe_correlation_matrices",
        },
        "predictions_source": str(args.predictions),
        "n_predictions": len(predictions),
        "stability": stability,
        "persistent_high_corrs": persistent,
        "snapshots": [asdict(s) for s in snapshots],
        "consult_attribution": (
            "Recommended by Ji-Hoon Yamamoto-Costa (Stats 5 / ML 1) at "
            "post-PoC trio convening 2026-05-05 (Topic 5). 'Free "
            "inference' -- no new model training, no new data; pure "
            "post-hoc analysis of existing predictions tensor."
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"[corr] wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
