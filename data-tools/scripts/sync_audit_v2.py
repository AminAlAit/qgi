#!/usr/bin/env python3
"""
sync_audit_v2.py — push reference/indicator-stationarity-audit-v2.json to S3.

The Stage A v2 stationarity audit JSON is read by the dscdi-finder Batch
job at startup (env var `AUDIT_JSON_S3_KEY = reference/indicator-stationarity-audit-v2.json`)
to determine each indicator's Class A/B/C disposition + transformation
(first_diff / log_diff / pass_through).

Without this sync the Batch job fails on the very first call to
`s3_client.get_object()` with NoSuchKey. This script closes #621.

## Filename "v2" vs JSON `schema_version: 1` (deliberate decoupling)

The "v2" in the filename refers to the **audit RUN version** — Stage A
v1 was the original audit; Stage A v2 was the re-run after the QA
strict review fixes (ct trend regression added, indicator-list flags,
+5 issues per qgi-ml/scripts/run_i5_substrate_audit.py changelog).

The internal `schema_version: 1` is the **JSON SHAPE version** of the
audit output. The shape did not change between audit run v1 and run v2;
only the underlying methodology fixes did. So the file legitimately
carries `schema_version: 1` while living at the v2 filename.

This script DOES NOT enforce `schema_version == 2`. It enforces
`schema_version == 1` — which is the actual current schema. If the
output schema is ever bumped, this script must be updated in lockstep
with the dscdi-finder consumer (`dscdi_finder.load_audit_classifications`).

Idempotent: skips upload when the remote MD5 already matches local. Re-runs
on the same JSON are free (1 HEAD call) and produce no S3 change.

Usage:
    python sync_audit_v2.py --bucket qgi-data-lake-771606957899
    python sync_audit_v2.py --bucket qgi-data-lake-771606957899 --dry-run

Exit codes (matches sync_indicator_allow_list.py convention):
    0 — success (uploaded or skipped)
    1 — precondition failure (file missing, malformed JSON, zero results,
        or unexpected schema_version)

Mirrors the established `sync_indicator_allow_list.py` pattern (same MD5
ETag comparison + atomic put_object semantics + flag set). When the v2
audit is regenerated (e.g., post-CIPS upgrade 2026-06-04 deadline), re-run
this script to keep the dscdi-finder pipeline reading the latest substrate
classifications.

S3 layout:
    s3://{bucket}/reference/indicator-stationarity-audit-v2.json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
LOCAL_PATH = REPO_ROOT / "reference" / "indicator-stationarity-audit-v2.json"

S3_KEY = "reference/indicator-stationarity-audit-v2.json"


EXPECTED_SCHEMA_VERSION = 1  # see top-of-file note on filename "v2" vs schema 1


def remote_etag(s3, bucket: str, key: str) -> str | None:
    try:
        resp = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise
    return resp["ETag"].strip('"')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", required=True, help="S3 bucket (e.g. qgi-data-lake-771606957899)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, do not upload")
    args = parser.parse_args()

    if not LOCAL_PATH.exists():
        print(f"ERROR: local file not found: {LOCAL_PATH}", file=sys.stderr)
        return 1

    # Read the file ONCE into memory. Use these same bytes for both the
    # MD5 hash and the put_object body, so the ETag computed locally
    # matches the bytes actually uploaded — even if the file is replaced
    # between checks (TOCTOU defense).
    raw = LOCAL_PATH.read_bytes()

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: local file is not valid JSON: {exc}", file=sys.stderr)
        return 1

    schema = payload.get("schema_version")
    if schema != EXPECTED_SCHEMA_VERSION:
        print(
            f"ERROR: expected schema_version={EXPECTED_SCHEMA_VERSION}, got {schema!r}. "
            f"If the audit output schema was bumped, update EXPECTED_SCHEMA_VERSION here "
            f"AND the dscdi-finder consumer (qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py "
            f"load_audit_classifications) in lockstep.",
            file=sys.stderr,
        )
        return 1

    n_results = len(payload.get("results", {}))
    if n_results == 0:
        print(f"ERROR: local audit JSON has zero results entries — refusing to sync", file=sys.stderr)
        return 1

    # S3 ETag for a non-multipart object (single PUT, < 5 MB) equals the
    # MD5 hex digest of the object body. The audit JSON is ~33 KB so the
    # single-PUT path is guaranteed.
    local_hash = hashlib.md5(raw).hexdigest()

    s3 = boto3.client("s3")
    remote_hash = remote_etag(s3, args.bucket, S3_KEY)

    print(f"local: {LOCAL_PATH} (schema={schema}, {n_results} indicators, md5={local_hash})")
    print(f"s3:    s3://{args.bucket}/{S3_KEY}")
    print(f"remote etag: {remote_hash or '(absent)'}")

    if remote_hash == local_hash:
        print("=> remote MD5 matches local; skipping upload (idempotent no-op)")
        return 0

    if args.dry_run:
        print("=> dry-run: would PUT (remote differs or absent)")
        return 0

    print("=> uploading...")
    s3.put_object(
        Bucket=args.bucket,
        Key=S3_KEY,
        Body=raw,
        ContentType="application/json",
    )
    print("=> done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
