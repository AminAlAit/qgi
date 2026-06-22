"""
V-Dem unzip Lambda (#494 step 5).

Step in the V-Dem annual-refresh Step Functions pipeline:

  [human drops V-Dem ZIP at s3://qgi-data-lake-*/vdem-staging/incoming/]
              │
              ▼
     S3 EventBridge trigger → SF execution
              │
        ┌─────┼─────┐
        ▼     ▼     ▼
   [THIS  [Batch [SNS
    Lambda] vdem  notify]
              ingest]

This Lambda's job:
  1. Receive the SF Task input describing the uploaded ZIP
  2. Stream the ZIP from S3 into memory (V-Dem v16 ~140MB compressed)
  3. Find the largest .csv file inside (V-Dem ZIPs typically include
     codebook PDFs and metadata alongside the data CSV; we want the data)
  4. Upload that CSV to a known S3 key under vdem-staging/unzipped/
  5. Return the unzipped key + size for downstream Step Functions states

## SF Task input contract

```json
{
  "bucket": "qgi-data-lake-771606957899",
  "incoming_key": "vdem-staging/incoming/V-Dem-CY-Full+Others-v15.zip"
}
```

Bucket + incoming_key are populated by the S3 EventBridge trigger.

## Return contract

```json
{
  "bucket": "qgi-data-lake-771606957899",
  "unzipped_key": "vdem-staging/unzipped/V-Dem-CY-Full+Others-v15.csv",
  "csv_size_bytes": 407123456,
  "csv_filename": "V-Dem-CY-Full+Others-v15.csv"
}
```

The Batch job (#494 step 4 `qgi-vdem-ingest`) reads
`unzipped_key` from the SF state and sets it as `VDEM_CSV_S3_KEY` on
the Batch task env.

## Cost discipline

- ARM64 (Graviton) — cheaper than x86. Configured at deploy time via
  the Lambda Architectures property in the Terraform module (#494
  step 6). Defaults to x86 if Terraform is wrong; this Lambda's code
  is architecture-agnostic.
- Memory: target 1024 MB (V-Dem v16 ZIP ~140MB compressed → ~388MB CSV
  in memory; 1024MB headroom is plenty). Memory and timeout are set
  in Terraform — out-of-scope for this file.
- Annual cadence — single-digit USD per V-Dem release total cost (this
  Lambda + the Batch container together).

## Idempotency

If the same ZIP is uploaded twice (e.g., human re-drops a corrected
copy), this Lambda overwrites the unzipped CSV at the same key. The
downstream Batch job is responsible for its own idempotency
(per #505, separate ticket). This Lambda is a pure transform —
running it twice on the same input produces the same output.
"""

from __future__ import annotations

import io
import logging
import os
import re
import zipfile
from typing import Any

import boto3


logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")

UNZIPPED_PREFIX = "vdem-staging/unzipped/"

# PR #9 review item 1 (uncompressed-size guard): if a future V-Dem
# release ships a much larger CSV than v16's ~388MB, the Lambda would
# silently OOM at 1024MB memory. Configurable cap raises an actionable
# UnzipError instead — operator can bump the cap (and the Lambda
# memory in the Terraform module) intentionally rather than triaging
# a SIGKILL post-mortem.
#
# Default 700MB gives ~75% headroom over v16; bump via env var without
# a code change if a release legitimately exceeds it.
MAX_CSV_BYTES = int(os.environ.get("MAX_CSV_BYTES", 700_000_000))

# PR #9 review item 2 (ZIP-slip / filename validation): the filename
# from inside the ZIP flows into UNZIPPED_PREFIX + csv_filename to
# build the upload key. S3 accepts any character, so a member named
# `../../evil.csv` or `..\evil.csv` could land at a surprising key.
# Defense-in-depth — only allow filenames that look like normal CSVs.
SAFE_CSV_FILENAME_REGEX = re.compile(r"^[A-Za-z0-9._+\-]+\.csv$", re.IGNORECASE)


class UnzipError(Exception):
    """Raised when the V-Dem ZIP can't be processed (no CSV inside,
    corrupted ZIP, S3 download fails, etc.). Step Functions maps this
    to a Failed terminal state and SNS notifies the operator."""


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Entry point. Validates input, downloads the ZIP, extracts the
    largest .csv, uploads to vdem-staging/unzipped/, returns the
    SF-consumable result.
    """
    bucket = event.get("bucket")
    incoming_key = event.get("incoming_key")
    if not bucket or not incoming_key:
        raise UnzipError(f"missing required event fields: bucket={bucket!r}, incoming_key={incoming_key!r}")

    logger.info("[unzip] start: s3://%s/%s", bucket, incoming_key)

    # 1. Download the ZIP from S3 into memory.
    zip_bytes = _download_zip(bucket, incoming_key)
    logger.info("[unzip] downloaded %d MB", len(zip_bytes) // 1_000_000)

    # 2. Extract the largest .csv from the ZIP.
    csv_filename, csv_bytes = _extract_largest_csv(zip_bytes, incoming_key)
    logger.info("[unzip] extracted %s (%d MB)", csv_filename, len(csv_bytes) // 1_000_000)

    # 3. Upload the CSV to vdem-staging/unzipped/ with the same base
    #    filename as the CSV inside the ZIP. This means re-uploads
    #    overwrite, and downstream Batch reads a stable key.
    unzipped_key = UNZIPPED_PREFIX + csv_filename
    _upload_csv(bucket, unzipped_key, csv_bytes)
    logger.info("[unzip] uploaded to s3://%s/%s", bucket, unzipped_key)

    return {
        "bucket": bucket,
        "unzipped_key": unzipped_key,
        "csv_size_bytes": len(csv_bytes),
        "csv_filename": csv_filename,
    }


def _download_zip(bucket: str, key: str) -> bytes:
    """Stream the ZIP body from S3 into memory."""
    try:
        resp = s3_client.get_object(Bucket=bucket, Key=key)
    except Exception as e:
        raise UnzipError(f"S3 GetObject failed for s3://{bucket}/{key}: {e}") from e
    return resp["Body"].read()


def _extract_largest_csv(zip_bytes: bytes, source_key: str) -> tuple[str, bytes]:
    """Find the largest .csv file in the ZIP, return (filename, bytes).

    V-Dem ZIPs typically contain:
      - V-Dem-CY-Full+Others-v15.csv  (the data — what we want)
      - Codebook.pdf                  (documentation)
      - README.txt                    (release notes)
      - Possibly metadata files

    "Largest .csv" is a robust heuristic: even if V-Dem starts shipping
    a small CSV alongside the data CSV, the data is always the dominant
    one. If the ZIP has zero .csv files we raise — that's a real
    upload error that needs human attention.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise UnzipError(f"invalid ZIP at {source_key}: {e}") from e

    # Filter: real .csv files (skip directory entries) AND non-empty
    # (PR #9 review item 3 — a 0-byte CSV would silently pass downstream
    # into a corrupt ingest. The "data is always the dominant CSV"
    # heuristic implicitly assumes non-empty; making it explicit).
    csv_members = [
        info
        for info in zf.infolist()
        if not info.is_dir() and info.filename.lower().endswith(".csv") and info.file_size > 0
    ]
    if not csv_members:
        all_filenames = [info.filename for info in zf.infolist()]
        raise UnzipError(
            f"no non-empty .csv files found in {source_key}. "
            f"ZIP contained {len(all_filenames)} member(s): {all_filenames}"
        )

    # Pick the largest by uncompressed size. Stable: equal-size CSVs
    # tie-broken by lexicographic filename (deterministic order).
    csv_members.sort(key=lambda i: (-i.file_size, i.filename))
    chosen = csv_members[0]
    logger.info(
        "[unzip] selected %s (%d MB) from %d candidate CSV(s)",
        chosen.filename,
        chosen.file_size // 1_000_000,
        len(csv_members),
    )

    # PR #9 review item 1 — uncompressed-size guard. Surface an
    # actionable error before we OOM trying to .read() a 1.5GB CSV at
    # 1024MB Lambda memory.
    if chosen.file_size > MAX_CSV_BYTES:
        raise UnzipError(
            f"selected CSV {chosen.filename!r} is {chosen.file_size:,} bytes, "
            f"above the cap of {MAX_CSV_BYTES:,} bytes. "
            f"Bump the MAX_CSV_BYTES env var (and Lambda memory in the "
            f"Terraform module) if this release legitimately needs more headroom."
        )

    # Strip any directory prefix from the filename in the ZIP — V-Dem
    # ZIPs sometimes include a top-level directory like
    # `V-Dem-CY-Full+Others-v15/V-Dem-CY-Full+Others-v15.csv`. After
    # stripping, validate the basename matches a safe pattern (PR #9
    # review item 2 — defense in depth against ZIP-slip filenames).
    csv_filename = chosen.filename.replace("\\", "/").split("/")[-1]
    if not SAFE_CSV_FILENAME_REGEX.match(csv_filename):
        raise UnzipError(
            f"unsafe CSV filename in ZIP: {chosen.filename!r} "
            f"(basename {csv_filename!r}). Expected ASCII letters, digits, "
            f"and . _ + - only."
        )

    with zf.open(chosen) as f:
        csv_bytes = f.read()
    return csv_filename, csv_bytes


def _upload_csv(bucket: str, key: str, csv_bytes: bytes) -> None:
    """Write the extracted CSV to S3. Overwrites existing key."""
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=csv_bytes,
            ContentType="text/csv",
        )
    except Exception as e:
        raise UnzipError(f"S3 PutObject failed for s3://{bucket}/{key}: {e}") from e
