"""qgi-recipe-fleet-vintage-rollup — cross-vintage rollup Lambda (qgi-aws-tf#968).

Scans the recipe-fleet S3 layout for every walk-summary the platform has produced:
  - current vintage     : `ml-results/{recipe_id}/f-ml-1-poc-summary.json`
  - prior vintages      : `ml-results/_archive/{sub_prefix}/f-ml-1-poc-summary.json`
                          where `sub_prefix` is whatever was used at archive time
                          (e.g., "foreign_intervention-precanary-eval2021").

For each summary found, builds one denormalized row via `vintage_rollup_core` and
writes the joined-by-recipe time-series to:
  s3://{bucket}/dashboard/admin/te-vintage-rollup.json

Consumed by the Admin Dashboard (qgi-aws-tf#151 TE §B) — quarterly trend section.

SFN / event input:
    {
      "s3_bucket": "qgi-data-lake-771606957899",
      "current_vintage_id": "<sfn-execution-name>",  // optional; defaults to "current"
      "ml_results_prefix": "ml-results/"             // optional; defaults to "ml-results/"
    }

Returns:
    {
      "status": "ok",
      "rollup_s3_uri": "s3://...",
      "n_recipes": int,
      "n_vintages_total": int,
      "warnings": [str, ...]
    }
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

import vintage_rollup_core as core

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

_SUMMARY_FILENAME = "f-ml-1-poc-summary.json"
_ROLLUP_OUTPUT_KEY = "dashboard/admin/te-vintage-rollup.json"
_ARCHIVE_SUB = "_archive/"


def _s3() -> Any:
    return boto3.client("s3")


def _get_json(bucket: str, key: str, *, optional: bool = True) -> dict | None:
    try:
        resp = _s3().get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if optional and code in ("NoSuchKey", "404", "NoSuchBucket"):
            return None
        raise
    return json.loads(resp["Body"].read().decode("utf-8"))


def _put_json(bucket: str, key: str, body: dict) -> str:
    payload = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
    _s3().put_object(Bucket=bucket, Key=key, Body=payload, ContentType="application/json")
    return f"s3://{bucket}/{key}"


def _list_sub_prefixes(bucket: str, prefix: str) -> list[str]:
    """List CommonPrefixes under `prefix/` (one level). Returns the final path segment
    of each sub-prefix. Does NOT recurse."""
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    paginator = _s3().get_paginator("list_objects_v2")
    out: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes") or []:
            sub = cp["Prefix"]  # "ml-results/terrorist_attack/"
            seg = sub[len(prefix) :].rstrip("/")
            if seg:
                out.append(seg)
    return sorted(out)


def lambda_handler(event: dict, context: Any) -> dict[str, Any]:
    LOG.info("vintage-rollup start | event=%s", json.dumps(event)[:500])
    bucket = event.get("s3_bucket")
    if not bucket:
        raise ValueError("event.s3_bucket is required")
    prefix = event.get("ml_results_prefix", "ml-results/")
    current_vintage_id = event.get("current_vintage_id") or event.get("execution_name")
    if not current_vintage_id:
        # FU3 per QA PR#45: surface the default in CloudWatch so two invocations
        # without a current_vintage_id (manual re-run + scheduled run on the same day)
        # are observable — they'll collide on the same "current" key and the second
        # writer's archive walk silently displaces the first. Last-writer-wins is
        # fine for a dashboard-read artifact but should never be invisible.
        LOG.warning(
            "no current_vintage_id provided (no `current_vintage_id` event "
            "field and no `execution_name`); defaulting to 'current' — note "
            "any other invocation also using this default will collide on "
            "the same per-recipe vintage row."
        )
        current_vintage_id = "current"

    warnings: list[str] = []
    per_recipe: dict[str, list[dict]] = defaultdict(list)

    # 1. Current vintage — direct sub-prefixes under ml_results_prefix (skip _archive + system).
    current_subs = [s for s in _list_sub_prefixes(bucket, prefix) if not s.startswith("_")]
    LOG.info("current vintage sub-prefixes: %d", len(current_subs))
    for rid in current_subs:
        key = f"{prefix.rstrip('/')}/{rid}/{_SUMMARY_FILENAME}"
        try:
            summary = _get_json(bucket, key, optional=True)
        except (ClientError, json.JSONDecodeError) as exc:
            warnings.append(f"current {rid}: read error: {exc}")
            continue
        if not summary:
            continue
        row = core.extract_vintage_row(summary, vintage_id=current_vintage_id)
        core.merge_into_per_recipe(per_recipe, rid, row)

    # 2. Prior vintages — every sub-prefix under ml_results_prefix/_archive/.
    archive_prefix = f"{prefix.rstrip('/')}/{_ARCHIVE_SUB}"
    archive_subs = _list_sub_prefixes(bucket, archive_prefix)
    LOG.info("archived sub-prefixes: %d", len(archive_subs))
    for sub in archive_subs:
        key = f"{archive_prefix.rstrip('/')}/{sub}/{_SUMMARY_FILENAME}"
        try:
            summary = _get_json(bucket, key, optional=True)
        except (ClientError, json.JSONDecodeError) as exc:
            warnings.append(f"archive {sub}: read error: {exc}")
            continue
        if not summary:
            continue
        # Recipe_id MUST come from the summary's own field (authoritative). For a
        # legacy archive lacking it, fall back to the FULL sub-prefix string — never
        # to `sub.split("-")[0]` which silently produces wrong rids on sub-prefixes
        # like `bilateral_treaty-pre-canary` (it'd give "bilateral_treaty" by accident
        # but `economic_growth_milestone-2026Q1` would give an unrelated fragment by
        # accident). The full sub-prefix is unique and surfaces the gap honestly; a
        # warning makes the missing-recipe_id case observable. (QA PR#45 review.)
        rid = summary.get("recipe_id")
        if not rid:
            warnings.append(
                f"archive {sub}: summary missing recipe_id field; using full archive "
                f"sub-prefix as recipe_id (this is honest but means the rollup row "
                f"will appear under a non-canonical key — re-archive with recipe_id "
                f"populated to recover the canonical bucket)."
            )
            rid = sub
        # vintage_id = full archive sub-prefix (unique, traceable)
        row = core.extract_vintage_row(summary, vintage_id=sub)
        core.merge_into_per_recipe(per_recipe, rid, row)

    # 3. Build + write.
    rollup = core.build_rollup(
        per_recipe,
        current_vintage_id=current_vintage_id,
        produced_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    rollup_uri = _put_json(bucket, _ROLLUP_OUTPUT_KEY, rollup)
    LOG.info(
        "rollup written: %s (%d recipes, %d vintages)", rollup_uri, rollup["n_recipes"], rollup["n_vintages_total"]
    )

    return {
        "status": "ok",
        "rollup_s3_uri": rollup_uri,
        "current_vintage_id": current_vintage_id,
        "n_recipes": rollup["n_recipes"],
        "n_vintages_total": rollup["n_vintages_total"],
        "warnings": warnings,
    }
