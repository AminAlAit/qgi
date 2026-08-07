"""
delete_scdi_originals.py — DEPRECATED 2026-05-04 (founder override).

DO NOT RUN. The original `pipeline-B-scdi-finder/scdis/` prefix is
retained indefinitely as permanent rollback insurance for the #592
compaction. The Glue table `qgi_data.scdis` is repointed to the
compacted prefix; the originals stay in S3 untouched.

This script's `main()` short-circuits with a refusal regardless of
flags. The implementation is preserved below for historical reference
and in case the override is reversed in a future founder decision.

Live spec: `docs/specs/internal/ops/cascade-track/phase-5-v0.0.md`
("Originals retention" section).

# THROWAWAY — DEPRECATED, do not run.

Hard prereqs (verify all before running with --confirm-delete):
  1. Compaction script ran successfully and verify_scdi_compaction.py
     reported PASS (all country partitions match).
  2. Glue table `qgi_data.scdis` location swapped to
     `pipeline-B-scdi-finder/scdis-compacted/` and at least 7 days have
     elapsed without query-result drift.
  3. The pipeline-B-scdi-finder Lambda's `S3_OUTPUT_PREFIX` env var has
     been updated to write to `scdis-compacted/` going forward AND a
     successful pipeline run has confirmed writes go to the new prefix.

If any of those is not yet true: do NOT run --confirm-delete. Use
--dry-run to preview the deletion scope without action.

Standing-rule callout: --confirm-delete is destructive. **Requires
explicit per-session founder approval** per
`feedback_no_pipeline_runs_without_approval.md`.

Safety gate: the script asserts row counts in scdis-compacted/ are
>= row counts in scdis/ before deleting a single key. If compacted has
fewer rows, abort.

Usage:
  # Preview only — what would be deleted:
  python scripts/delete_scdi_originals.py \\
      --bucket qgi-data-lake-771606957899 \\
      --dry-run

  # After dry-run AND founder greenlight:
  python scripts/delete_scdi_originals.py \\
      --bucket qgi-data-lake-771606957899 \\
      --confirm-delete
"""
from __future__ import annotations

import argparse
import sys

import boto3
import pyarrow.parquet as pq
import s3fs

DEFAULT_SOURCE_PREFIX = "pipeline-B-scdi-finder/scdis/"
DEFAULT_TARGET_PREFIX = "pipeline-B-scdi-finder/scdis-compacted/"
S3_DELETE_BATCH_SIZE = 1000  # AWS max per delete_objects call


def count_rows_in_prefix(s3fs_: s3fs.S3FileSystem, bucket: str, prefix: str) -> int:
    """Sum parquet metadata num_rows across all files under prefix
    (recursive)."""
    files = s3fs_.glob(f"{bucket}/{prefix}**/*.parquet")
    total = 0
    for f in files:
        with s3fs_.open(f, "rb") as fh:
            total += pq.ParquetFile(fh).metadata.num_rows
    return total


def main() -> int:
    print(
        "DEPRECATED 2026-05-04 (founder override): the original "
        "pipeline-B-scdi-finder/scdis/ prefix is retained indefinitely. "
        "This script will not run. See "
        "docs/specs/internal/ops/cascade-track/phase-5-v0.0.md "
        "'Originals retention' for the live spec.",
        file=sys.stderr,
    )
    return 2

    parser = argparse.ArgumentParser(  # noqa: F841 — preserved historical impl below
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--source-prefix", default=DEFAULT_SOURCE_PREFIX)
    parser.add_argument("--target-prefix", default=DEFAULT_TARGET_PREFIX)
    parser.add_argument("--dry-run", action="store_true",
                        help="List + count keys; do NOT delete. "
                             "Mutually exclusive with --confirm-delete; "
                             "if both are passed, --dry-run wins.")
    parser.add_argument("--confirm-delete", action="store_true",
                        help="Required to actually delete. Pass exactly "
                             "ONE of --dry-run or --confirm-delete.")
    args = parser.parse_args()

    if not args.dry_run and not args.confirm_delete:
        print("ERROR: pass either --dry-run (preview) or --confirm-delete (execute).")
        return 2

    s3 = boto3.client("s3")
    s3fs_ = s3fs.S3FileSystem()

    # Safety gate: verify compacted has at least as many rows as source.
    print("Counting rows in compacted prefix (safety gate)...")
    tgt_rows = count_rows_in_prefix(s3fs_, args.bucket, args.target_prefix)
    print("Counting rows in original prefix...")
    src_rows = count_rows_in_prefix(s3fs_, args.bucket, args.source_prefix)
    print(f"  source rows:    {src_rows:,}")
    print(f"  compacted rows: {tgt_rows:,}")

    if tgt_rows < src_rows:
        print(f"\nABORT: compacted ({tgt_rows:,}) has FEWER rows than source ({src_rows:,}).")
        print("Do NOT delete. Re-run compact_scdi_prefix.py first; investigate the gap.")
        return 1

    # List keys to delete
    paginator = s3.get_paginator("list_objects_v2")
    keys: list[str] = []
    for page in paginator.paginate(Bucket=args.bucket, Prefix=args.source_prefix):
        for obj in page.get("Contents", []) or []:
            keys.append(obj["Key"])

    n_batches = (len(keys) + S3_DELETE_BATCH_SIZE - 1) // S3_DELETE_BATCH_SIZE
    print(f"\nObjects to delete: {len(keys):,} (~{n_batches} batches of "
          f"{S3_DELETE_BATCH_SIZE})")

    if args.dry_run:
        print("\n[DRY RUN complete.]")
        print("To execute deletion: re-run with --confirm-delete (NOT --dry-run).")
        print("Requires explicit per-session founder approval per the "
              "no-pipeline-runs rule.")
        return 0

    print(f"\nProceeding with deletion of {len(keys):,} objects...")
    deleted = 0
    failed: list[dict] = []
    for i in range(0, len(keys), S3_DELETE_BATCH_SIZE):
        batch = [{"Key": k} for k in keys[i : i + S3_DELETE_BATCH_SIZE]]
        # Quiet=True suppresses per-key success rows (saves response size
        # for 1.65M-key runs) but errors are STILL returned in the
        # `Errors` array. We MUST inspect that — silent partial failure
        # is the worst possible outcome for a destructive script.
        # QA review 2026-05-03 (MAJOR #2) caught this.
        resp = s3.delete_objects(
            Bucket=args.bucket,
            Delete={"Objects": batch, "Quiet": True},
        )
        batch_errors = resp.get("Errors", []) or []
        if batch_errors:
            failed.extend(batch_errors)
            for err in batch_errors[:5]:
                print(f"  [DELETE FAILED] {err.get('Key')}: "
                      f"{err.get('Code')} {err.get('Message')}")
            if len(batch_errors) > 5:
                print(f"  ... and {len(batch_errors) - 5} more in this batch")
        # Count successes only — failed keys remain on S3.
        deleted += len(batch) - len(batch_errors)
        if deleted % 50_000 == 0 or deleted == len(keys) - len(failed):
            print(f"  deleted {deleted:,}/{len(keys):,}")

    print(f"\nDone. Deleted {deleted:,} objects from "
          f"s3://{args.bucket}/{args.source_prefix}")

    if failed:
        # Persist the failure list so the operator can retry / investigate.
        # A 1.65M-key run could plausibly have a few hundred transient
        # failures (throttle, replication delay) — not catastrophic but
        # NOT silent.
        from datetime import datetime
        from pathlib import Path
        fail_log = Path(f"./scdi_delete_failures_{datetime.utcnow():%Y%m%dT%H%M%S}.txt")
        with fail_log.open("w") as fh:
            for err in failed:
                fh.write(f"{err.get('Key')}\t{err.get('Code')}\t{err.get('Message')}\n")
        print(f"\nWARNING: {len(failed)} keys failed to delete. "
              f"See {fail_log} for the list. Re-run after triaging "
              f"(or invoke s3 rm with the failed-keys file).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
