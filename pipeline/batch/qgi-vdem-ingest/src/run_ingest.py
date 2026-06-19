#!/usr/bin/env python3
"""
run_ingest.py — V-Dem ingest Batch entry orchestrator (#494 step 4).

Sits between the Step Functions definition and the worker script
(`ingest_vdem.py` from qgi-data, bundled into this image at /app/).
The orchestrator's job is **environment-to-CLI translation**:

  1. Read the SF-provided env vars
  2. Download the unzipped V-Dem CSV from S3 to /tmp
  3. Invoke the bundled `ingest_vdem.py` with the right CLI args
  4. Surface the worker's exit code (0 on success, non-zero on failure)
  5. Clean up the /tmp CSV (best-effort)

The worker script has its own contract: it reads the indicator list
from `INDICATOR_CATALOG_XLSX_PATH` (set by the Dockerfile to
`/app/indicators/control-surface.xlsx`), applies the country map
from `/app/registries/vdem_country_map.yaml`, and writes per-indicator
parquets to `s3://{bucket}/pipeline-A-indicator-extractor/output/parquet/`.
This orchestrator does NOT re-implement any of that logic — it just
sets up the working directory and shells out.

## Env vars (all required)

  S3_BUCKET           — data lake bucket (e.g. qgi-data-lake-771606957899)
  VDEM_CSV_S3_KEY     — S3 key of the unzipped V-Dem CSV in the bucket
                        (the unzip Lambda's output location)
  AWS_REGION          — eu-central-1
  ATHENA_WORKGROUP    — Athena workgroup to use for MSCK REPAIR
                        (default: QGI-Lambda-Workgroup)

## Optional env vars

  DRY_RUN             — "true" to skip S3 writes (validate-only mode)
  SKIP_REPAIR         — "true" to skip MSCK REPAIR after upload
                        (default: run it)

## Exit codes

  0  — success
  1  — env var validation failure (missing required, etc.)
  2  — S3 download of the V-Dem CSV failed
  3+ — propagated from ingest_vdem.py

The Step Functions definition (#494 step 6) maps non-zero exits to a
Failed terminal state and emits SNS to qgi-vdem-ingest-status.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import boto3


# Paths inside the container (set by the Dockerfile).
WORKER_SCRIPT = Path("/app/ingest_vdem.py")
COUNTRY_MAP_PATH = Path("/app/registries/vdem_country_map.yaml")


def env_required(name: str) -> str:
    """Read a required env var; exit 1 with a clear message if missing."""
    val = os.environ.get(name)
    if not val:
        print(f"[error] missing required env var: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean-ish env var ('true'/'1'/'yes' = True)."""
    val = os.environ.get(name, "").strip().lower()
    if not val:
        return default
    return val in ("true", "1", "yes")


def download_csv_to_tmp(bucket: str, key: str, region: str) -> Path:
    """Download the V-Dem CSV from S3 to /tmp/. Returns the local path.

    Uses /tmp because Fargate gives every task at least 20 GiB of
    ephemeral storage by default — V-Dem v16 CSV is ~388 MB, no
    pressure on space. The file is best-effort cleaned up at the end
    of run_pipeline().
    """
    s3 = boto3.client("s3", region_name=region)
    local_path = Path(tempfile.gettempdir()) / Path(key).name
    print(f"[download] s3://{bucket}/{key} → {local_path}")
    try:
        s3.download_file(bucket, key, str(local_path))
    except Exception as e:
        print(f"[error] S3 download failed: {e}", file=sys.stderr)
        sys.exit(2)
    size_mb = local_path.stat().st_size / 1_000_000
    print(f"[download] OK ({size_mb:.1f} MB)")
    return local_path


def build_ingest_argv(
    csv_path: Path,
    bucket: str,
    workgroup: str,
    region: str,
    dry_run: bool,
    repair: bool,
) -> list[str]:
    """Compose argv for the ingest_vdem.py worker."""
    argv = [
        sys.executable,
        "-u",
        str(WORKER_SCRIPT),
        "--vdem-csv-path",
        str(csv_path),
        "--bucket",
        bucket,
        "--workgroup",
        workgroup,
        "--region",
        region,
        "--country-map",
        str(COUNTRY_MAP_PATH),
    ]
    if dry_run:
        argv.append("--dry-run")
    if repair:
        argv.append("--repair")
    return argv


def run_pipeline() -> int:
    bucket = env_required("S3_BUCKET")
    csv_key = env_required("VDEM_CSV_S3_KEY")
    region = env_required("AWS_REGION")
    workgroup = os.environ.get("ATHENA_WORKGROUP", "QGI-Lambda-Workgroup")

    dry_run = env_bool("DRY_RUN", default=False)
    skip_repair = env_bool("SKIP_REPAIR", default=False)

    print(f"[init] bucket={bucket}")
    print(f"[init] csv_key={csv_key}")
    print(f"[init] region={region}")
    print(f"[init] workgroup={workgroup}")
    print(f"[init] dry_run={dry_run} skip_repair={skip_repair}")
    print(f"[init] worker script: {WORKER_SCRIPT}")

    # Sanity check the bundled artifacts before starting work — this
    # catches a Dockerfile-build regression early instead of at the
    # ingest_vdem.py error path.
    for path in (WORKER_SCRIPT, COUNTRY_MAP_PATH):
        if not path.exists():
            print(f"[error] bundled artifact missing: {path}", file=sys.stderr)
            print("[error] check the Dockerfile + the CI staging step.", file=sys.stderr)
            sys.exit(1)

    csv_path = download_csv_to_tmp(bucket, csv_key, region)

    argv = build_ingest_argv(
        csv_path=csv_path,
        bucket=bucket,
        workgroup=workgroup,
        region=region,
        dry_run=dry_run,
        repair=not skip_repair,
    )
    print(f"[exec] {' '.join(argv)}")
    try:
        rc = subprocess.call(argv)
    finally:
        # Best-effort cleanup. Container exits anyway, but explicit
        # delete keeps logs honest about disk usage on long-running
        # spot instances that get re-used (rare in Fargate, but cheap
        # insurance).
        try:
            csv_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"[warn] csv cleanup failed: {e}", file=sys.stderr)

    if rc == 0:
        print("[done] V-Dem ingest succeeded.")
    else:
        print(f"[done] V-Dem ingest failed (exit code {rc}).", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(run_pipeline())
