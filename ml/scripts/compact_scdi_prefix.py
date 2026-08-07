"""
compact_scdi_prefix.py — copy-compact pipeline-B-scdi-finder/scdis/ into
scdis-compacted/.

# THROWAWAY — run once for #592. Not part of any pipeline.

For each `country_a_id={N}/` partition under the source prefix:
  - Read all parquet files via PyArrow ParquetDataset (parallel S3 reads
    handled by the s3fs filesystem).
  - Concatenate into a single Arrow Table.
  - Write one `data.parquet` per partition to the target prefix (Snappy).
  - Originals are NOT deleted, ever (founder override 2026-05-04: the
    original `pipeline-B-scdi-finder/scdis/` prefix is retained
    indefinitely as permanent rollback insurance). The companion
    delete_scdi_originals.py is DEPRECATED and must not be run.

Memory budget (verified by dry-run 2026-05-03 against staging):
  Largest country partition has ~150M rows. Each SCDI row is ~20 bytes
  decoded (6 smallint + 1 float + 1 bool). Peak memory per partition:
  ~3 GB uncompressed Arrow Table. Run on a machine with >= 8 GB RAM
  (16 GB comfortable). A single t3.xlarge or any modern laptop suffices.

Idempotency: if the target file already exists with matching row count,
skip the partition (re-runs are safe).

Failure handling: per-country errors are collected and reported at the
end. Script exits non-zero if any country failed, so a CI runner can
detect partial success.

Usage:
  # Smoke test on one country first
  python scripts/compact_scdi_prefix.py \\
      --bucket qgi-data-lake-771606957899 \\
      --country-id 10 \\
      --dry-run

  # After dry-run looks correct, run full compaction
  python scripts/compact_scdi_prefix.py \\
      --bucket qgi-data-lake-771606957899

Standing-rule callout: this script ONLY needs founder per-session
approval if --dry-run is OFF (per
`feedback_no_pipeline_runs_without_approval.md`). Dry-runs are read-
only and free.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from typing import Optional

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
import s3fs

DEFAULT_SOURCE_PREFIX = "pipeline-B-scdi-finder/scdis/"
DEFAULT_TARGET_PREFIX = "pipeline-B-scdi-finder/scdis-compacted/"
SNAPPY = "snappy"


def list_country_ids(s3: "boto3.client", bucket: str, source_prefix: str) -> list[int]:
    """Return sorted list of country_a_id integer values found under
    source_prefix.

    Skips any directory that doesn't match the `country_a_id={N}/` form
    (defensive against future stray subdirectories).
    """
    paginator = s3.get_paginator("list_objects_v2")
    prefixes = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=source_prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []) or []:
            part = cp["Prefix"].rstrip("/").split("/")[-1]
            if part.startswith("country_a_id="):
                try:
                    prefixes.add(int(part.split("=", 1)[1]))
                except ValueError:
                    pass
    return sorted(prefixes)


def count_rows_via_metadata(s3fs_: s3fs.S3FileSystem, bucket: str, prefix: str) -> int:
    """Count total rows across all parquet files under prefix using
    parquet metadata only (no full read).

    Returns -1 if any file's metadata can't be read — caller falls back
    to a full read for verification.
    """
    # Caller always passes `prefix` ending in `/`, so the path is
    # well-formed for the glob. (No fallback variant needed; that was
    # dead code per QA review 2026-05-03.)
    path = f"{bucket}/{prefix}"
    try:
        files = s3fs_.glob(f"{path}*.parquet")
        if not files:
            return 0
        total = 0
        for f in files:
            with s3fs_.open(f, "rb") as fh:
                total += pq.ParquetFile(fh).metadata.num_rows
        return total
    except Exception:
        return -1


def compact_one_country(
    s3fs_: s3fs.S3FileSystem,
    bucket: str,
    source_prefix: str,
    target_prefix: str,
    country_id: int,
    dry_run: bool,
) -> tuple[int, int, str]:
    """Compact one country partition.

    Returns (source_rows, written_rows, status) where status is one of:
        "skipped_idempotent"   — target exists, row count matches, skipped
        "dry_run"              — would have written, didn't
        "written"              — wrote successfully
        "error:<reason>"       — see reason
    """
    src_partition = f"{source_prefix}country_a_id={country_id}/"
    tgt_partition = f"{target_prefix}country_a_id={country_id}/"
    tgt_key = f"{tgt_partition}data.parquet"

    src_rows = count_rows_via_metadata(s3fs_, bucket, src_partition)
    if src_rows == 0:
        return 0, 0, "error:empty_source_partition"
    if src_rows < 0:
        return 0, 0, "error:source_metadata_unreadable"

    # Idempotency: if target exists with matching row count, skip.
    if s3fs_.exists(f"{bucket}/{tgt_key}"):
        with s3fs_.open(f"{bucket}/{tgt_key}", "rb") as fh:
            tgt_rows = pq.ParquetFile(fh).metadata.num_rows
        if tgt_rows == src_rows:
            return src_rows, src_rows, "skipped_idempotent"
        # Row mismatch — log and rewrite below
        print(
            f"  [country={country_id}] target exists but row mismatch "
            f"(src={src_rows} tgt={tgt_rows}); rewriting"
        )

    if dry_run:
        return src_rows, 0, "dry_run"

    try:
        dataset = pq.ParquetDataset(f"{bucket}/{src_partition}", filesystem=s3fs_)
        table: pa.Table = dataset.read()
    except Exception as exc:
        return src_rows, 0, f"error:read_failed:{type(exc).__name__}:{exc}"

    if table.num_rows != src_rows:
        # Concurrent Lambda write between metadata pass and full read is
        # the most common cause. Mitigation: run during off-hours when
        # no pipeline is firing. The error path is deterministic — the
        # caller's idempotency check on re-run will see no target file
        # and re-attempt cleanly.
        return src_rows, table.num_rows, (
            f"error:row_count_mismatch_after_read (concurrent write suspected): "
            f"meta={src_rows},actual={table.num_rows}"
        )

    try:
        with s3fs_.open(f"{bucket}/{tgt_key}", "wb") as fh:
            pq.write_table(table, fh, compression=SNAPPY)
    except Exception as exc:
        return src_rows, 0, f"error:write_failed:{type(exc).__name__}:{exc}"

    # Post-write verification — read back the file we just wrote and
    # confirm row count matches what we sent. Three failure modes:
    # (a) S3 returned success on a partial PUT (rare but real),
    # (b) parquet writer corrupted the table,
    # (c) concurrent process overwrote between our write and our read.
    with s3fs_.open(f"{bucket}/{tgt_key}", "rb") as fh:
        written_rows = pq.ParquetFile(fh).metadata.num_rows
    if written_rows != src_rows:
        # CRITICAL: delete the bad target so the next idempotency check
        # treats this partition as un-compacted. Without this, a re-run
        # would see tgt_rows != src_rows, log "rewriting", and proceed
        # — but a bad target file might mistakenly satisfy the idempotency
        # check if src_rows happens to shift to match. QA review
        # 2026-05-03 caught this orphan-file failure mode (MAJOR #1).
        try:
            s3fs_.rm(f"{bucket}/{tgt_key}")
        except Exception as cleanup_exc:
            # Cleanup failure is logged but doesn't mask the original
            # mismatch — the operator must investigate manually.
            print(f"  [country={country_id}] WARN: bad target cleanup failed: "
                  f"{type(cleanup_exc).__name__}: {cleanup_exc}")
        return src_rows, written_rows, (
            f"error:post_write_mismatch:expected={src_rows},got={written_rows} "
            f"(bad target file deleted to prevent next-run false-positive)"
        )
    return src_rows, written_rows, "written"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--source-prefix", default=DEFAULT_SOURCE_PREFIX)
    parser.add_argument("--target-prefix", default=DEFAULT_TARGET_PREFIX)
    parser.add_argument("--dry-run", action="store_true",
                        help="List partitions and report row counts; do NOT write.")
    parser.add_argument("--country-id", type=int, default=None,
                        help="Compact only this single country partition (smoke test).")
    args = parser.parse_args()

    s3 = boto3.client("s3")
    s3fs_ = s3fs.S3FileSystem()

    if args.country_id is not None:
        country_ids = [args.country_id]
        print(f"Single-country mode: country_a_id={args.country_id}")
    else:
        print(f"Listing country partitions under s3://{args.bucket}/{args.source_prefix}")
        country_ids = list_country_ids(s3, args.bucket, args.source_prefix)
        print(f"Found {len(country_ids)} country partitions")

    if args.dry_run:
        print("\n--- DRY RUN --- no data will be written\n")

    print(f"  {'country_a_id':>14}  {'src_rows':>10}  {'written':>10}  status")
    print("  " + "-" * 60)

    results: dict[str, list[int]] = defaultdict(list)
    t0 = time.monotonic()

    for cid in country_ids:
        src_rows, written_rows, status = compact_one_country(
            s3fs_, args.bucket, args.source_prefix, args.target_prefix,
            cid, args.dry_run,
        )
        results[status].append(cid)
        marker = "OK" if status in ("written", "skipped_idempotent", "dry_run") else "FAIL"
        print(f"  [{marker}] country={cid:>5d}  src={src_rows:>10,}  "
              f"written={written_rows:>10,}  {status}")

    elapsed = time.monotonic() - t0
    print(f"\n--- Summary ({elapsed:.1f}s) ---")
    for status, ids in sorted(results.items()):
        print(f"  {status}: {len(ids)} countries")

    failures = [s for s in results if s.startswith("error:")]
    if failures:
        print("\nFAILED countries:")
        for s in failures:
            print(f"  {s}: {results[s]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
