#!/usr/bin/env python3
"""
calibrate_recipe_similarity.py — #463 Part B Platt calibration training.

For each pattern-length tier (S/M/L/XL), fit a Platt sigmoid that maps
the V2.0 raw similarity score in `qgi_data.country_recipe_scores` to a
calibrated probability.

  similarity_calibrated = 1 / (1 + exp(-(a * similarity_raw + b)))

The (a, b) parameters per tier are written to S3 at
  `s3://{bucket}/calibration/recipe_similarity_v{N}/params.json`

The recipe-engine-finalize Lambda reads the latest version at runtime and
applies the sigmoid in the `country_recipe_scores` INSERT SQL. (Wiring
deferred to a follow-up; current Lambda has similarity_calibrated =
similarity_raw as a placeholder per the v0.1 ship.)

This script is algorithm-agnostic — works equally well against:
- v0.1 weighted-coverage raw scores (current)
- v0.2 Pearson trajectory raw scores (when Part A v0.2 lands)

Inputs:
  --pairs-jsonl        per-pair ground truth from `run_backtest.py
                       --dump-pairs-jsonl` (#463 Part C)
  --scores-jsonl       V2.0 raw scores per (country_id, event_category)
                       — JSONL with one record per row from
                       qgi_data.country_recipe_scores
  --recipes-aggregated path to recipes-aggregated JSON (mock or real)
                       — provides canonical_length per event_category
                       which determines the tier bucket

Output:
  --output-json   {S/M/L/XL: {a, b, n_pos, n_total}} written locally
  --upload + --bucket   also publish to S3 calibration prefix

Reuses qgi-ml/scripts/run_backtest.py:platt_scale (the brute-force
sigmoid grid search) so the algorithm matches the V1.9 backtest
discipline. Don't reinvent the wheel.

Usage:
  python scripts/calibrate_recipe_similarity.py \\
      --pairs-jsonl results/v2_eval_2026_04_27/pairs.jsonl \\
      --scores-jsonl results/v2_eval_2026_04_27/scores.jsonl \\
      --recipes-aggregated ../qgi-frontend/data/recipes-aggregated-mock.json \\
      --output-json results/v2_eval_2026_04_27/calibration_params.json \\
      --upload --bucket qgi-data-lake-771606957899 --version 1
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Re-use platt_scale from run_backtest (keeps the calibration discipline
# consistent across V1.x backtest + V2.0 scoring).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_backtest import TIERS, platt_scale  # noqa: E402


def tier_for_length(canonical_length: int) -> str:
    """Map canonical_length to its S/M/L/XL bucket."""
    for tier, (lo, hi) in TIERS.items():
        if lo <= canonical_length <= hi:
            return tier
    return "XL"


def load_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--pairs-jsonl", type=Path, required=True,
                   help="Per-pair fixture from run_backtest.py --dump-pairs-jsonl")
    p.add_argument("--scores-jsonl", type=Path, required=True,
                   help="V2.0 raw scores per (country_id, event_category) — one JSON per line")
    p.add_argument("--recipes-aggregated", type=Path, required=True,
                   help="Path to recipes-aggregated JSON (mock or real)")
    p.add_argument("--output-json", type=Path, required=True,
                   help="Where to write calibration_params.json locally")
    p.add_argument("--upload", action="store_true",
                   help="Also publish params to S3 at calibration/recipe_similarity_v{version}/")
    p.add_argument("--bucket", type=str, default=None,
                   help="S3 bucket (required when --upload)")
    p.add_argument("--region", type=str, default="eu-central-1")
    p.add_argument("--version", type=int, default=1,
                   help="Calibration version number — mapping_version stamp on every "
                        "row in country_recipe_scores")
    p.add_argument("--min-samples", type=int, default=30,
                   help="Skip per-tier fit when fewer than N pairs available "
                        "(falls back to identity sigmoid: a=1, b=0)")
    args = p.parse_args()

    if args.upload and not args.bucket:
        p.error("--upload requires --bucket")

    print(f"[load] {args.pairs_jsonl}")
    pairs = load_jsonl(args.pairs_jsonl)
    print(f"[load] {args.scores_jsonl}")
    scores = load_jsonl(args.scores_jsonl)
    print(f"[load] {args.recipes_aggregated}")
    recipes = json.loads(args.recipes_aggregated.read_text(encoding="utf-8"))

    # Build canonical_length lookup per L3 category.
    cl_by_cat = {r["event_category"]: r["canonical_length"] for r in recipes["recipes"]}
    print(f"[init] {len(cl_by_cat)} event_category → canonical_length entries")

    # Ground truth: max y_true across tier rows per (country, category). Use the
    # v1.9.1 rows specifically (not persistence) — those are the per-tier
    # predictions whose ground-truth label is what we want to calibrate against.
    gt: dict[tuple, int] = {}
    for r in pairs:
        if r.get("system") != "v1.9.1":
            continue
        key = (int(r["country_a_id"]), r["event_category"])
        gt[key] = max(gt.get(key, 0), int(r["y_true"]))
    print(f"[gt] {len(gt)} unique (country, category) ground-truth labels")

    # Bucket V2.0 raw scores by tier, JOIN to ground truth.
    by_tier: dict[str, dict[str, list]] = {
        t: {"y_true": [], "y_score": []} for t in TIERS
    }
    skipped_no_cl = 0
    skipped_no_gt = 0
    for s in scores:
        cat = s.get("event_category")
        cl = cl_by_cat.get(cat)
        if cl is None:
            skipped_no_cl += 1
            continue
        tier = tier_for_length(int(cl))
        key = (int(s["country_id"]), cat)
        if key not in gt:
            skipped_no_gt += 1
            continue
        by_tier[tier]["y_true"].append(gt[key])
        by_tier[tier]["y_score"].append(float(s["similarity_raw"]))

    if skipped_no_cl:
        print(f"[warn] {skipped_no_cl} score rows had no canonical_length match")
    if skipped_no_gt:
        print(f"[warn] {skipped_no_gt} score rows had no ground-truth pair")

    # Fit per tier.
    output: dict[str, dict] = {
        "version": args.version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "min_samples": args.min_samples,
        "tiers": {},
    }
    for tier in TIERS:
        bucket = by_tier[tier]
        n_total = len(bucket["y_true"])
        n_pos = int(sum(bucket["y_true"]))
        if n_total < args.min_samples or n_pos < 2:
            print(f"[fit] {tier}: SKIP (n_total={n_total}, n_pos={n_pos})")
            output["tiers"][tier] = {
                "a": 1.0, "b": 0.0,
                "n_total": n_total, "n_pos": n_pos,
                "note": f"insufficient data (need ≥{args.min_samples} total, ≥2 pos)",
            }
            continue
        y_true = np.array(bucket["y_true"])
        y_score = np.array(bucket["y_score"])
        _, a, b = platt_scale(y_true, y_score, y_score)
        print(f"[fit] {tier}: a={a:.3f}, b={b:.3f} (n_total={n_total}, n_pos={n_pos})")
        output["tiers"][tier] = {
            "a": float(a), "b": float(b),
            "n_total": n_total, "n_pos": n_pos,
        }

    # Write local.
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2))
    print(f"[write] {args.output_json}")

    # Optional S3 publish.
    if args.upload:
        import boto3
        s3 = boto3.client("s3", region_name=args.region)
        s3_key = f"calibration/recipe_similarity_v{args.version}/params.json"
        s3.put_object(
            Bucket=args.bucket, Key=s3_key,
            Body=json.dumps(output, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        print(f"[upload] s3://{args.bucket}/{s3_key}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
