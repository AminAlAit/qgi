#!/usr/bin/env python3
"""
sync_indicator_allow_list.py — push reference/indicator-allow-list.json to S3.

Co-locates the JSON with indicator_map.csv so the
pipeline-recipe-engine-finalize Lambda can read both from the same prefix
on cold start.

Idempotent: skips upload when the remote MD5 already matches local. Re-runs
on the same JSON are free (1 HEAD call) and produce no S3 change.

Usage:
    python sync_indicator_allow_list.py --bucket qgi-data-lake-771606957899
    python sync_indicator_allow_list.py --bucket qgi-data-lake-771606957899 --dry-run

Pre-deploy of the lambda: this MUST run after every regeneration of
indicator-allow-list.json (e.g., when the catalog grows). The lambda reads
from S3 once at module load — without sync, the lambda sees stale data.

S3 layout:
    s3://{bucket}/pipeline-A-indicator-extractor/input/indicator-allow-list.json
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
LOCAL_PATH = REPO_ROOT / "reference" / "indicator-allow-list.json"

S3_KEY = "pipeline-A-indicator-extractor/input/indicator-allow-list.json"


def local_md5(path: Path) -> str:
    """S3 ETag for a non-multipart object equals the MD5 hex digest of the
    object body. We compute the same here for comparison."""
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def remote_etag(s3, bucket: str, key: str) -> str | None:
    try:
        resp = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise
    # ETag comes back wrapped in quotes; strip them.
    return resp["ETag"].strip('"')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="Compare local vs remote; do not upload.")
    args = parser.parse_args()

    if not LOCAL_PATH.exists():
        print(f"ERROR: {LOCAL_PATH} not found. Run "
              "qgi-ml/scripts/generate_indicator_allow_list.py first.",
              file=sys.stderr)
        return 1

    # Validate JSON shape minimally before uploading — refuse to push a
    # broken file to a path the production lambda will read on cold start.
    try:
        payload = json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
        if "allow_list_numeric_ids" not in payload:
            raise ValueError("missing 'allow_list_numeric_ids' field")
        if not isinstance(payload["allow_list_numeric_ids"], list):
            raise ValueError("'allow_list_numeric_ids' must be a list")
        if not all(isinstance(x, int) for x in payload["allow_list_numeric_ids"]):
            raise ValueError("'allow_list_numeric_ids' must contain ints only")
        n = len(payload["allow_list_numeric_ids"])
        if n == 0:
            raise ValueError("allow-list is empty — refuse to upload (would "
                             "make the lambda emit empty fingerprints)")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {LOCAL_PATH} failed validation: {exc}", file=sys.stderr)
        return 1

    s3 = boto3.client("s3")
    local_hash = local_md5(LOCAL_PATH)
    remote_hash = remote_etag(s3, args.bucket, S3_KEY)

    print(f"Local:  {LOCAL_PATH}")
    print(f"  size: {LOCAL_PATH.stat().st_size:,} bytes  MD5: {local_hash}")
    print(f"  allow-list size: {n} numeric_ids")
    print(f"Remote: s3://{args.bucket}/{S3_KEY}")
    if remote_hash is None:
        print(f"  (does not exist yet)")
    else:
        print(f"  ETag: {remote_hash}")

    if remote_hash == local_hash:
        print("\nLocal and remote match. Nothing to upload.")
        return 0

    if args.dry_run:
        action = "create" if remote_hash is None else "overwrite"
        print(f"\n[dry-run] Would {action} s3://{args.bucket}/{S3_KEY}")
        return 0

    print(f"\nUploading...")
    s3.upload_file(
        str(LOCAL_PATH), args.bucket, S3_KEY,
        ExtraArgs={"ContentType": "application/json"},
    )
    print(f"Done. Pushed {n} numeric_ids to s3://{args.bucket}/{S3_KEY}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
