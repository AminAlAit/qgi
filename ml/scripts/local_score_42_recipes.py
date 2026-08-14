"""Run score_countries.py LOCALLY on the 42 recipes that walked under the OLD
image (pre-2026-05-29 rebuild) and therefore lack country-scores.json in S3.

For each missing recipe:
  1. Pull f-ml-1-poc-summary.json from s3://qgi-data-lake-771606957899/ml-results/{rid}/
  2. Locate positives.csv at qgi-ml/data/shape_inputs_v2/{rid}/positives.csv
  3. Run scripts/score_countries.py against cached panels at data/parquet_panels/
  4. Upload the produced country-scores.json back to S3

Then trigger bake_te_fleet_run_1.py to regenerate the corpus with full scoring.

This closes the 42-recipe gap from the 2026-05-30 first-bake pass.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3

B = "qgi-data-lake-771606957899"
PANEL_DIR = Path("data/parquet_panels")
SHAPE_INPUTS = Path("data/shape_inputs_v2")
SCORE_SCRIPT = Path("scripts/score_countries.py")


def has_country_scores(s3, rid: str) -> bool:
    try:
        s3.head_object(Bucket=B, Key=f"ml-results/{rid}/country-scores.json")
        return True
    except Exception:
        return False


def enumerate_missing(s3) -> list[str]:
    dirs: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=B, Prefix="ml-results/", Delimiter="/"
    ):
        for p in page.get("CommonPrefixes", []) or []:
            sub = p["Prefix"].split("ml-results/")[1].rstrip("/")
            if sub and not sub.startswith("_"):
                dirs.append(sub)
    return sorted(rid for rid in dirs if not has_country_scores(s3, rid))


def process(rid: str) -> tuple[str, bool, str]:
    s3 = boto3.client("s3", region_name="eu-central-1")
    try:
        positives = SHAPE_INPUTS / rid / "positives.csv"
        if not positives.exists():
            return rid, False, f"positives.csv missing at {positives}"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # 1. Pull summary
            summary_path = tmp / "f-ml-1-poc-summary.json"
            body = s3.get_object(
                Bucket=B, Key=f"ml-results/{rid}/f-ml-1-poc-summary.json"
            )["Body"].read()
            summary_path.write_bytes(body)
            # 2. Run score_countries.py
            cmd = [
                sys.executable,
                str(SCORE_SCRIPT),
                "--recipe-id", rid,
                "--summary-path", str(summary_path),
                "--panel-dir", str(PANEL_DIR),
                "--positives-csv", str(positives),
                "--output-dir", str(tmp),
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if res.returncode != 0:
                return rid, False, f"score_countries failed rc={res.returncode}: {res.stderr[-500:]}"
            scores_path = tmp / "country-scores.json"
            if not scores_path.exists():
                return rid, False, "country-scores.json not produced"
            # 3. Upload to S3
            s3.upload_file(
                str(scores_path), B, f"ml-results/{rid}/country-scores.json",
                ExtraArgs={"ContentType": "application/json"},
            )
            n = len(json.loads(scores_path.read_text()).get("scores", []))
            return rid, True, f"OK n_scored={n}"
    except Exception as exc:
        return rid, False, f"exception: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-workers", type=int, default=3,
                    help="Concurrent score_countries runs (each uses ~1-2 GB RAM; "
                         "keep low on laptops).")
    ap.add_argument("--dry-run", action="store_true",
                    help="List missing recipes; do not run.")
    args = ap.parse_args()

    s3 = boto3.client("s3", region_name="eu-central-1")
    missing = enumerate_missing(s3)
    print(f"=== {len(missing)} recipes missing country-scores.json ===")
    if args.dry_run:
        for rid in missing:
            print(f"  {rid}")
        return 0

    print(f"Running with max-workers={args.max_workers} ...")
    n_ok = 0
    n_fail = 0
    fails: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = {ex.submit(process, rid): rid for rid in missing}
        for fut in as_completed(futures):
            rid = futures[fut]
            try:
                _, ok, msg = fut.result()
            except Exception as exc:
                ok, msg = False, f"future failed: {exc}"
            if ok:
                n_ok += 1
                print(f"  [{n_ok+n_fail:>2}/{len(missing)}] {rid:<40} {msg}")
            else:
                n_fail += 1
                fails.append((rid, msg))
                print(f"  [{n_ok+n_fail:>2}/{len(missing)}] {rid:<40} FAIL: {msg}")

    print()
    print(f"=== DONE: {n_ok}/{len(missing)} succeeded, {n_fail} failed ===")
    if fails:
        print("Failures:")
        for rid, msg in fails:
            print(f"  {rid}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
