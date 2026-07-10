#!/usr/bin/env python3
"""
Sync curated events JSONs, verification JSONs, and TRACKING.md to S3 (#141 / #541).

This is the SOURCE-OF-TRUTH sync — fast, no Athena, no Parquet rebuild.
Use this after every `clean and verify the events of [country]` pass to push
the local curated/{country}.json + verification/{country}.json up to S3 so
other machines / CI / Lambdas can read it.

Bidirectional:
  --upload   (default) push local -> S3
  --download         pull S3 -> local (for fresh clones / new dev machines)

The pipeline's heavy ingest_events.py reads the SAME local curated/ directory
on its next run and rebuilds Parquet from there. Run that separately when you
want the Athena `qgi_data.events` table updated.

Usage:
    python sync_curated_events.py --bucket qgi-data-lake-771606957899
    python sync_curated_events.py --bucket qgi-data-lake-771606957899 --download
    python sync_curated_events.py --bucket qgi-data-lake-771606957899 --dry-run

S3 layout:
    s3://{bucket}/events-source/curated/{country}.json
    s3://{bucket}/events-source/verification/{country}.json
    s3://{bucket}/events-source/TRACKING.md
"""
import argparse
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Force UTF-8 stdout on Windows so OK/ERROR markers and country names with
# non-ASCII characters render without UnicodeEncodeError under cp1252.
# Belt-and-braces alongside the ASCII-only marker change below (#541 bug 3).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
CURATED_DIR = REPO_ROOT / "events" / "curated"
VERIFICATION_DIR = REPO_ROOT / "events" / "verification"
# TRACKING.md sits next to the events/ subdir, not under it (see README.md +
# the qgi-data repo layout). The previous `REPO_ROOT / "data" / "events" /
# "TRACKING.md"` path is a holdover from the qgi-pipeline-era layout and was
# the silent reason TRACKING.md never reached S3 from this script (#541 bug 1).
TRACKING_FILE = REPO_ROOT / "events" / "TRACKING.md"

S3_PREFIX = "events-source/curated/"
S3_VERIFICATION_PREFIX = "events-source/verification/"
S3_TRACKING_KEY = "events-source/TRACKING.md"


def upload(s3, bucket: str, dry_run: bool) -> None:
    """Push local curated/ + verification/ + TRACKING.md to S3."""
    if not CURATED_DIR.exists():
        print(f"ERROR: {CURATED_DIR} does not exist")
        sys.exit(1)

    files = sorted(CURATED_DIR.glob("*.json"))
    print(f"Uploading {len(files)} curated event files to s3://{bucket}/{S3_PREFIX}")

    for f in files:
        key = f"{S3_PREFIX}{f.name}"
        if dry_run:
            print(f"  [dry-run] {f.name} -> s3://{bucket}/{key}")
            continue
        s3.upload_file(
            str(f), bucket, key,
            ExtraArgs={'ContentType': 'application/json'},
        )
        print(f"  OK {f.name}")

    # verification/ — canonical schema introduced in #372; the previous
    # version of this script silently skipped it, forcing every after-
    # curation flow to `aws s3 sync` directly (#541 bug 2).
    if VERIFICATION_DIR.exists():
        verif_files = sorted(VERIFICATION_DIR.glob("*.json"))
        print(f"Uploading {len(verif_files)} verification files to s3://{bucket}/{S3_VERIFICATION_PREFIX}")
        for f in verif_files:
            key = f"{S3_VERIFICATION_PREFIX}{f.name}"
            if dry_run:
                print(f"  [dry-run] {f.name} -> s3://{bucket}/{key}")
                continue
            s3.upload_file(
                str(f), bucket, key,
                ExtraArgs={'ContentType': 'application/json'},
            )
            print(f"  OK {f.name}")
    else:
        verif_files = []
        print(f"  WARNING: {VERIFICATION_DIR} not found, skipping verification sync")

    if TRACKING_FILE.exists():
        if dry_run:
            print(f"  [dry-run] TRACKING.md -> s3://{bucket}/{S3_TRACKING_KEY}")
        else:
            s3.upload_file(
                str(TRACKING_FILE), bucket, S3_TRACKING_KEY,
                ExtraArgs={'ContentType': 'text/markdown'},
            )
            print(f"  OK TRACKING.md")
    else:
        print(f"  WARNING: {TRACKING_FILE} not found, skipping")

    print(f"Done. Uploaded {len(files)} curated + {len(verif_files)} verification files"
          f"{' (dry-run)' if dry_run else ''}.")


def download(s3, bucket: str, dry_run: bool) -> None:
    """Pull S3 -> local curated/ + verification/ + TRACKING.md (for fresh clones)."""
    CURATED_DIR.mkdir(parents=True, exist_ok=True)
    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)

    paginator = s3.get_paginator('list_objects_v2')

    curated_keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=S3_PREFIX):
        for obj in page.get('Contents', []):
            if obj['Key'].endswith('.json'):
                curated_keys.append(obj['Key'])

    print(f"Downloading {len(curated_keys)} curated files from s3://{bucket}/{S3_PREFIX}")
    for key in curated_keys:
        filename = key.rsplit('/', 1)[-1]
        local = CURATED_DIR / filename
        if dry_run:
            print(f"  [dry-run] s3://{bucket}/{key} -> {local}")
            continue
        s3.download_file(bucket, key, str(local))
        print(f"  OK {filename}")

    verification_keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=S3_VERIFICATION_PREFIX):
        for obj in page.get('Contents', []):
            if obj['Key'].endswith('.json'):
                verification_keys.append(obj['Key'])

    print(f"Downloading {len(verification_keys)} verification files from "
          f"s3://{bucket}/{S3_VERIFICATION_PREFIX}")
    for key in verification_keys:
        filename = key.rsplit('/', 1)[-1]
        local = VERIFICATION_DIR / filename
        if dry_run:
            print(f"  [dry-run] s3://{bucket}/{key} -> {local}")
            continue
        s3.download_file(bucket, key, str(local))
        print(f"  OK {filename}")

    # Tracking file
    if dry_run:
        print(f"  [dry-run] s3://{bucket}/{S3_TRACKING_KEY} -> {TRACKING_FILE}")
    else:
        try:
            s3.download_file(bucket, S3_TRACKING_KEY, str(TRACKING_FILE))
            print(f"  OK TRACKING.md")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                print(f"  WARNING: TRACKING.md not in S3 yet, skipping")
            else:
                raise

    print(f"Done. Downloaded {len(curated_keys)} curated + {len(verification_keys)} "
          f"verification files{' (dry-run)' if dry_run else ''}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--bucket', required=True, help='S3 bucket name (e.g. qgi-data-lake-771606957899)')
    parser.add_argument('--region', default='eu-central-1')
    parser.add_argument('--role-arn', help='Optional cross-account role to assume')
    parser.add_argument('--download', action='store_true', help='Pull S3 -> local instead of pushing')
    parser.add_argument('--dry-run', action='store_true', help='Show what would happen without doing it')
    args = parser.parse_args()

    if args.role_arn:
        sts = boto3.client('sts', region_name=args.region)
        creds = sts.assume_role(RoleArn=args.role_arn, RoleSessionName='curated-events-sync')['Credentials']
        s3 = boto3.client(
            's3', region_name=args.region,
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
        )
    else:
        s3 = boto3.client('s3', region_name=args.region)

    if args.download:
        download(s3, args.bucket, args.dry_run)
    else:
        upload(s3, args.bucket, args.dry_run)


if __name__ == '__main__':
    main()
