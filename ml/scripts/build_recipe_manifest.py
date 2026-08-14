"""Build recipe-manifest.json for the recipe-fleet (design §2a / §7 step 3).

Reads qgi-ml/data/shape_inputs_v2/*/positives.csv, counts N_pos per recipe,
and emits a tiered manifest:

  - runnable : N_pos >= 60  → XGBoost walk proceeds (F-ML-1 §5 THIN_RECIPE_CAP gate)
  - thin     : 8 <= N_pos < 60 → walk runs under thin-recipe cap (5 greedy steps)
  - skip     : N_pos < 8    → insufficient data; job never submitted

The manifest is consumed by:
  1. The SFN pre-filter Pass state (reads runnable_recipes list for Map input).
  2. The Batch entrypoint (recipe_fleet_entrypoint.py) as a secondary guard.

Output: recipe-manifest.json (default: qgi-ml/data/recipe-manifest.json)
        Optionally upload to S3 via --bucket + --upload flags.

Usage:
    python qgi-ml/scripts/build_recipe_manifest.py
    python qgi-ml/scripts/build_recipe_manifest.py \
        --data-dir qgi-ml/data/shape_inputs_v2 \
        --output qgi-ml/data/recipe-manifest.json \
        --bucket qgi-data-lake-771606957899 \
        --upload

Update this manifest whenever qgi-data/events/curated/ changes (new positive
events added or removed). Commit the updated recipe-manifest.json alongside
the positives.csv changes.

Tested: tests/test_build_recipe_manifest.py (sizing tiers, country count, job batching).
The `vcpu` field on each runnable_job is consumed by the post-#962 SFN Map (VCPU override
+ --n-jobs); the legacy SFN ignores it and submits at the job-definition default.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("build-recipe-manifest")

# F-ML-1 thresholds (from run_f_ml_1_poc.py constants)
RUNNABLE_MIN_NPOS = 60    # XGBoost full walk
THIN_MIN_NPOS = 8         # thin walk (5-step greedy cap)
# N_pos < THIN_MIN_NPOS → skip (insufficient for any meaningful walk)

# Batch job grouping: ~5 recipes per Batch job (design §2a "batches of ~5")
RECIPES_PER_JOB = 5

# #962 per-recipe Spot sizing. The wall-clock / cost driver is the COUNTRY count
# (= LOCO folds), not n_pos, so jobs are sized + batched by it. vCPU = the --n-jobs the
# parallel walk (#961) uses; batch_size shrinks for fat recipes so each fat job stays
# small (it processes its batch SEQUENTIALLY, so we don't pile slow recipes into one job).
# vCPUs stay within the FLEET-9 cap: max_vcpus=48 ≥ MaxConcurrency throttles concurrent
# fat jobs. Tiers (consult 2026-05-27): <60 ctry→4 / 60-99→8 / ≥100→16 vCPU.
SIZE_TIERS = [
    # (max_countries_exclusive, tier, vcpu, batch_size)
    (60, "small", 4, 5),
    (100, "medium", 8, 3),
    (10**9, "fat", 16, 1),
]


def size_tier(n_countries: int) -> dict:
    """Pure: map a recipe's country count to its sizing tier (tier, vcpu, batch_size)."""
    for ceil, tier, vcpu, batch in SIZE_TIERS:
        if n_countries < ceil:
            return {"tier": tier, "vcpu": vcpu, "batch_size": batch}
    raise AssertionError("unreachable: SIZE_TIERS last bound is open")


def count_positives(positives_csv: Path) -> int:
    """Count data rows (non-header) in a positives.csv file."""
    try:
        with positives_csv.open() as f:
            lines = [ln for ln in f if ln.strip()]
        # Subtract 1 for header row
        return max(0, len(lines) - 1)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Could not read %s: %s", positives_csv, exc)
        return 0


def count_countries(positives_csv: Path) -> int:
    """Count DISTINCT country_id (LOCO folds) in a positives.csv — the sizing driver."""
    try:
        with positives_csv.open() as f:
            rows = [ln.strip() for ln in f if ln.strip()]
        if len(rows) < 2:
            return 0
        # header is "country_id,event_year"; country_id is column 0
        return len({r.split(",", 1)[0] for r in rows[1:]})
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Could not read countries from %s: %s", positives_csv, exc)
        return 0


def chunk_list(items: list, size: int) -> list[list]:
    """Split list into sublists of up to `size` items each."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def build_runnable_jobs(runnable: list[dict]) -> list[dict]:
    """Pure: group runnable recipes into sized Batch jobs (#962). Recipes are bucketed by
    sizing tier, sorted densest-first within a tier, then chunked at the tier's batch_size.
    Each job carries the vCPU the SFN Map sets (resourceRequirements + --n-jobs). Returns a
    list of {recipe_ids: 'a,b', vcpu, tier, n_recipes, max_countries}."""
    by_tier: dict[str, list[dict]] = {}
    for r in runnable:
        by_tier.setdefault(r["size"]["tier"], []).append(r)
    jobs: list[dict] = []
    for _, tier, vcpu, batch in SIZE_TIERS:
        members = sorted(by_tier.get(tier, []), key=lambda x: x["n_pos"], reverse=True)
        for chunk in chunk_list(members, batch):
            jobs.append({
                "recipe_ids": ",".join(c["recipe_id"] for c in chunk),
                "vcpu": vcpu,
                "tier": tier,
                "n_recipes": len(chunk),
                "max_countries": max(c["n_countries"] for c in chunk),
            })
    return jobs


def build_manifest(data_dir: Path) -> dict:
    """Scan data_dir/*/positives.csv and build the manifest dict."""
    if not data_dir.is_dir():
        LOG.error("data-dir not found: %s", data_dir)
        sys.exit(1)

    runnable: list[dict] = []
    thin: list[dict] = []
    skip: list[dict] = []

    for recipe_dir in sorted(data_dir.iterdir()):
        if not recipe_dir.is_dir():
            continue
        recipe_id = recipe_dir.name
        positives_csv = recipe_dir / "positives.csv"
        if not positives_csv.exists():
            LOG.warning("No positives.csv for %s — skipping", recipe_id)
            continue
        n_pos = count_positives(positives_csv)
        n_countries = count_countries(positives_csv)
        entry = {"recipe_id": recipe_id, "n_pos": n_pos, "n_countries": n_countries}
        if n_pos >= RUNNABLE_MIN_NPOS:
            entry["size"] = size_tier(n_countries)  # #962 vCPU sizing for the fan-out
            runnable.append(entry)
        elif n_pos >= THIN_MIN_NPOS:
            thin.append(entry)
        else:
            skip.append(entry)

    # Sort each tier by n_pos descending (densest first → prioritize)
    runnable.sort(key=lambda x: x["n_pos"], reverse=True)
    thin.sort(key=lambda x: x["n_pos"], reverse=True)
    skip.sort(key=lambda x: x["n_pos"], reverse=True)

    # #962 sized jobs: batch runnable recipes by sizing tier, each job carrying its vCPU.
    # The SFN Map adopts `runnable_jobs` (per-job VCPU override + --n-jobs). `runnable_recipes`
    # is kept (DERIVED from the same jobs → consistent) so the current SFN keeps working until
    # it adopts the sized form. thin recipes stay on the legacy ~5-chunk (all small/2-vCPU).
    runnable_jobs = build_runnable_jobs(runnable)
    thin_ids = [r["recipe_id"] for r in thin]
    job_batches = [j["recipe_ids"].split(",") for j in runnable_jobs]
    thin_batches = chunk_list(thin_ids, RECIPES_PER_JOB)

    manifest = {
        "schema_version": "1",
        "thresholds": {
            "runnable_min_npos": RUNNABLE_MIN_NPOS,
            "thin_min_npos": THIN_MIN_NPOS,
        },
        "counts": {
            "runnable": len(runnable),
            "thin": len(thin),
            "skip": len(skip),
            "total": len(runnable) + len(thin) + len(skip),
        },
        # runnable_jobs (#962): the SIZED form the SFN Map adopts — one object per Batch
        # job: {recipe_ids, vcpu, tier, n_recipes, max_countries}. The Map sets the job's
        # resourceRequirements VCPU + passes --n-jobs = vcpu to the parallel walk (#961).
        "runnable_jobs": runnable_jobs,
        # runnable_recipes: legacy comma-string form, DERIVED from runnable_jobs (same
        # batching) so the pre-#962 SFN keeps working until it reads runnable_jobs.
        "runnable_recipes": [",".join(batch) for batch in job_batches],
        # thin_recipes: same structure. Can be added to SFN Map if desired.
        "thin_recipes": [",".join(batch) for batch in thin_batches],
        # Full per-recipe detail for debugging / audit trail.
        "detail": {
            "runnable": runnable,
            "thin": thin,
            "skip": skip,
        },
    }
    return manifest


def upload_to_s3(manifest: dict, bucket: str, key: str) -> None:
    import boto3
    s3 = boto3.client("s3")
    body = json.dumps(manifest, indent=2).encode()
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    LOG.info("Uploaded manifest → s3://%s/%s", bucket, key)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "shape_inputs_v2",
        help="Directory containing recipe subdirectories with positives.csv files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "recipe-manifest.json",
        help="Path for the output recipe-manifest.json",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default="",
        help="S3 bucket name (required with --upload)",
    )
    parser.add_argument(
        "--s3-key",
        type=str,
        default="ml-results/recipe-manifest.json",
        help="S3 key for the manifest (default: ml-results/recipe-manifest.json)",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        default=False,
        help="Upload the manifest to S3 after writing locally (requires --bucket)",
    )
    args = parser.parse_args()

    LOG.info("Scanning positives.csv files under: %s", args.data_dir)
    manifest = build_manifest(args.data_dir)

    # Pretty-print summary
    LOG.info(
        "Manifest: runnable=%d (%d jobs) | thin=%d (%d jobs) | skip=%d | total=%d",
        manifest["counts"]["runnable"],
        len(manifest["runnable_recipes"]),
        manifest["counts"]["thin"],
        len(manifest["thin_recipes"]),
        manifest["counts"]["skip"],
        manifest["counts"]["total"],
    )
    for entry in manifest["detail"]["runnable"]:
        LOG.info("  RUNNABLE  %s  (N_pos=%d)", entry["recipe_id"], entry["n_pos"])
    for entry in manifest["detail"]["thin"]:
        LOG.info("  THIN      %s  (N_pos=%d)", entry["recipe_id"], entry["n_pos"])
    for entry in manifest["detail"]["skip"]:
        LOG.info("  SKIP      %s  (N_pos=%d)", entry["recipe_id"], entry["n_pos"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(manifest, f, indent=2)
    LOG.info("Manifest written to %s", args.output)

    if args.upload:
        if not args.bucket:
            LOG.error("--bucket is required when --upload is set")
            sys.exit(1)
        upload_to_s3(manifest, args.bucket, args.s3_key)


if __name__ == "__main__":
    main()
