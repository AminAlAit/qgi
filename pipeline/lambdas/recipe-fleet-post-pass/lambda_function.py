"""qgi-recipe-fleet-post-pass — SFN Map-state successor Lambda.

Reads each recipe's `f-ml-1-poc-summary.json` from the recipe-fleet S3 prefix, joins each
to its frozen floor + the previously-published tracker tiers, calls the pure orchestrator
in `post_pass_core` to produce the DRAFT Recipe Tracker rows + tier transitions + the
integrity attestation that gates the tracker PR. Writes the draft as a single JSON to
S3 under `post-pass/{vintage_id}/draft-tracker.json` — NEVER to the live tracker (the
PR-Majles-merge path is the human-ratification gate per Condition D).

SFN Parameters (per `qgi-infra/modules/recipe-fleet/main.tf`):
    {
      "execution_name": "<sfn-execution-name>",  // becomes the vintage_id
      "ml_results_prefix": "ml-results/",
      "s3_bucket": "qgi-data-lake-771606957899"
    }

Returns:
    {
      "status": "ok" | "fail",
      "vintage_id": str,
      "draft_s3_uri": str,                       // s3://.../post-pass/{vintage_id}/draft-tracker.json
      "n_recipes_processed": int,
      "n_transitions": int,
      "attestation_summary": {
          "all_conditions_pass": bool,
          "tracker_pr_may_merge": bool,
          "pending_majles_signoff": int,
      },
      "warnings": [str, ...],                    // human-readable non-fatal issues
    }

The handler is INTENTIONALLY thin: every methodology decision lives in `post_pass_core`
(re-tested by `tests/unit/recipe-fleet-post-pass/test_post_pass_core.py`); the handler
only does S3 I/O + payload normalisation + error surfacing. That separation is what
makes `assemble_tracker_draft` testable without a network and the handler reviewable
purely as plumbing.

Conditions sourced for the integrity attestation:
    floor_ordering_ok           — TRUE iff `reference/recipe-floors.json` exists AND its
                                  `frozen_at_utc` is on or before the earliest walk's
                                  `filed` timestamp (FLEET-5 invariant in code form).
    no_grandfathered_tiers      — overridden TRUE by `assemble_tracker_draft` itself; we
                                  pass through whatever value we computed (kept honest).
    bit_identical_walk          — for now this is passed via the env var
                                  `POST_PASS_BIT_IDENTICAL_WALK_OK` (defaults True since
                                  the canary §2.5 gate is the production check; flip to
                                  False if a canary fails).
    no_poisoned_indicator_holds_bypassed — env var `POST_PASS_POISONED_GUARD_OK`
                                  (defaults False until FLEET-7 #124 lands). Honest FALSE
                                  blocks `tracker_pr_may_merge` — by design.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

import post_pass_core as pp

LOG = logging.getLogger()
LOG.setLevel(logging.INFO)

_FLOORS_KEY = "reference/recipe-floors.json"
_PUBLISHED_TRACKER_KEY = "post-pass/_latest/published-tracker.json"  # written by the
# post-Majles PR step
_DRAFT_KEY_TEMPLATE = "post-pass/{vintage_id}/draft-tracker.json"
_SUMMARY_FILENAME = "f-ml-1-poc-summary.json"


# ---------------------------------------------------------------------------
# S3 plumbing helpers (small, pure, mockable)
# ---------------------------------------------------------------------------


def _s3() -> Any:
    """Lazy client so tests can monkeypatch boto3 before any client is created."""
    return boto3.client("s3")


def _get_json(bucket: str, key: str, *, optional: bool = False) -> dict | None:
    """Read a JSON object. If `optional` and the key is missing (404/NoSuchKey), return
    None instead of raising — the caller decides what 'missing' means for that key."""
    try:
        resp = _s3().get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if optional and code in ("NoSuchKey", "404", "NoSuchBucket"):
            return None
        raise
    return json.loads(resp["Body"].read().decode("utf-8"))


def _put_json(bucket: str, key: str, body: dict) -> str:
    """Write JSON to S3 with utf-8 + Content-Type; return the s3:// URI."""
    payload = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
    _s3().put_object(Bucket=bucket, Key=key, Body=payload, ContentType="application/json")
    return f"s3://{bucket}/{key}"


def _list_recipe_ids(bucket: str, prefix: str) -> list[str]:
    """List the recipe sub-prefixes under `prefix/`, returning their final path segment
    (the recipe_id). Uses Delimiter='/' + CommonPrefixes — same pattern other QGI Lambdas
    use to enumerate per-recipe directories without paginating every object."""
    if not prefix.endswith("/"):
        prefix = prefix + "/"
    paginator = _s3().get_paginator("list_objects_v2")
    recipe_ids: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes") or []:
            sub = cp["Prefix"]  # e.g. "ml-results/terrorist_attack/"
            rid = sub[len(prefix) :].rstrip("/")
            if rid and not rid.startswith("_"):  # skip "_archive/" etc.
                recipe_ids.append(rid)
    return sorted(recipe_ids)


# ---------------------------------------------------------------------------
# Condition extractors (each is a tiny pure function from disk-state to a bool)
# ---------------------------------------------------------------------------


def _parse_utc(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 UTC timestamp, returning None if absent/unparseable.
    Accepts both trailing-Z and ±HH:MM offset forms. Consolidates the three
    repetitions of `datetime.fromisoformat(ts.replace("Z","+00:00"))` that
    otherwise drift independently in this module (QA PR #44 nit N1)."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _derive_floor_ordering_ok(floors_doc: dict | None, results: dict[str, dict | None]) -> bool:
    """FLEET-5 in code: floors must be frozen BEFORE the earliest walk fires. If we can't
    read either side of the comparison, fail CLOSED (return False) — never silently True.
    """
    if not floors_doc:
        return False
    frozen_dt = _parse_utc(floors_doc.get("frozen_at_utc"))
    if frozen_dt is None:
        return False
    walk_times: list[datetime] = []
    for summary in results.values():
        if not summary:
            continue
        walk_dt = _parse_utc(summary.get("filed"))
        if walk_dt is not None:
            walk_times.append(walk_dt)
    if not walk_times:
        # Can't verify — fail closed
        return False
    return frozen_dt <= min(walk_times)


def _derive_beats_baseline(floors_doc: dict | None, results: dict[str, dict | None]) -> dict[str, bool | None]:
    """Per-recipe `beats_baseline` (Directional criterion 4). Returns:
    - True  iff this run's AUC > the recipe's frozen hybrid_baseline
    - False iff AUC ≤ hybrid_baseline
    - None  iff we cannot compare (missing AUC or missing baseline) — the policy
            treats None as 'not asserted', not as a demotion.
    """
    out: dict[str, bool | None] = {}
    floors_map = (floors_doc or {}).get("floors") or {}
    for rid, summary in results.items():
        gl = (summary or {}).get("global_loco", {}) or {}
        auc = gl.get("auc")
        recipe_floor = floors_map.get(rid) or {}
        hb = recipe_floor.get("hybrid_baseline")
        if auc is None or hb is None:
            out[rid] = None
        else:
            out[rid] = bool(auc > hb)
    return out


def _reject_stale_walks(results: dict[str, dict | None], floors_doc: dict | None, warnings: list[str]) -> int:
    """Per-recipe filter (#966): set `results[rid] = None` for any summary whose
    `filed` timestamp predates `floors.frozen_at_utc`. The FLEET-5 invariant says
    floors must be frozen BEFORE every walk fires; a summary that violates that
    ordering is a stale leftover from a prior pipeline version (e.g., the
    foreign_intervention 2026-05-25 leaked walk that surfaced on 2026-05-28).
    Treating it as None routes the recipe to QUEUED via `assemble_tracker_draft`
    — never silently classified — and the warning surfaces the reason. Returns
    the count of recipes filtered. No-op when floors_doc or its `frozen_at_utc`
    is missing (the global `floor_ordering_ok` derivation already fails closed
    in that case)."""
    if not floors_doc:
        return 0
    frozen_at = floors_doc.get("frozen_at_utc")
    frozen_dt = _parse_utc(frozen_at)
    if frozen_dt is None:
        return 0
    rejected = 0
    for rid in sorted(results):
        summary = results[rid]
        if not summary:
            continue
        filed = summary.get("filed")
        walk_dt = _parse_utc(filed)
        if walk_dt is None:
            continue
        if walk_dt < frozen_dt:
            warnings.append(
                f"{rid}: stale walk (filed={filed} predates floors.frozen_at_utc="
                f"{frozen_at}); excluded from draft pending re-walk under the "
                f"corrected pipeline (FLEET-5 invariant)."
            )
            results[rid] = None
            rejected += 1
    return rejected


def _env_bool(name: str, default: bool) -> bool:
    """Parse a methodology-gate env var conservatively. Semantics:
    - UNSET → return `default` (no operator opinion expressed).
    - SET to a clear truthy string ('1','true','yes','on', case-insensitive) → True.
    - SET to anything else (typo'd, empty, "0", "false", "off", "ok", …) → FALSE,
      regardless of `default`. A methodology gate must fail closed on ambiguity:
      an operator who tried to express an opinion and mis-spelled it is safer held
      closed than silently treated as "use the default" (which would mask the typo).
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def lambda_handler(event: dict, context: Any) -> dict[str, Any]:
    """Entry point — see the module docstring for the input/output contract."""
    LOG.info("post-pass start | event=%s", json.dumps(event)[:1000])

    bucket = event.get("s3_bucket")
    prefix = event.get("ml_results_prefix", "ml-results/")
    execution_name = event.get("execution_name") or "ad-hoc"
    if not bucket:
        raise ValueError("event.s3_bucket is required")
    # 1:1 with the SFN execution — traceability + uniqueness (the SFN API enforces unique
    # execution names within a 90-day window, so two concurrent SFN runs cannot collide).
    # The "ad-hoc" fallback (direct invoke without an execution_name) is suffixed with a
    # second-precision UTC timestamp so manual sanity-invokes don't clobber each other.
    if execution_name == "ad-hoc":
        execution_name = f"ad-hoc-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    vintage_id = execution_name

    warnings: list[str] = []

    # 1. Enumerate recipes that have output in the prefix this vintage.
    recipe_ids = _list_recipe_ids(bucket, prefix)
    LOG.info("found %d recipe sub-prefixes under s3://%s/%s", len(recipe_ids), bucket, prefix)
    if not recipe_ids:
        # NOT an error — surface honestly. The caller (SFN) may have routed here with an
        # empty prefix (e.g. a config mistake); failing here would mask that.
        warnings.append(f"no recipe sub-prefixes under s3://{bucket}/{prefix}")

    # 2. Load each recipe's walk summary. A missing summary becomes None — classified
    #    as QUEUED downstream (not silently dropped).
    results: dict[str, dict | None] = {}
    for rid in recipe_ids:
        key = f"{prefix.rstrip('/')}/{rid}/{_SUMMARY_FILENAME}"
        try:
            summary = _get_json(bucket, key, optional=True)
        except ClientError as exc:
            warnings.append(f"{rid}: s3 ClientError reading {key}: {exc.response.get('Error', {}).get('Code')}")
            summary = None
        except json.JSONDecodeError as exc:
            warnings.append(f"{rid}: malformed JSON in {key}: {exc}")
            summary = None
        results[rid] = summary

    # 3. Load floors + previous-vintage tracker (both optional — first-ever run has no prior).
    floors_doc = _get_json(bucket, _FLOORS_KEY, optional=True)
    if floors_doc is None:
        warnings.append(
            f"floors missing at s3://{bucket}/{_FLOORS_KEY} — beats_baseline "
            f"will be None for every recipe and floor_ordering_ok will FAIL"
        )
    prev_tracker = _get_json(bucket, _PUBLISHED_TRACKER_KEY, optional=True)
    prev_tiers: dict[str, str] = {}
    if prev_tracker:
        for row in prev_tracker.get("draft_recipes") or prev_tracker.get("recipes") or []:
            rid = row.get("recipe_id")
            tier = row.get("tier")
            if rid and tier:
                prev_tiers[rid] = tier
    else:
        warnings.append(
            f"no previous tracker at s3://{bucket}/{_PUBLISHED_TRACKER_KEY} "
            f"— all transitions will read as 'queued → <tier>'"
        )

    # 3b. Reject any summary filed before the floors were frozen (#966). A walk that
    # predates floors.frozen_at_utc is a stale leftover from a prior pipeline version
    # (FLEET-5 invariant violation) — the foreign_intervention 2026-05-25 leaked walk
    # is the class of regression this filter closes. Filtered recipes are routed to
    # QUEUED via assemble_tracker_draft + the warning is surfaced for operator review.
    n_stale_rejected = _reject_stale_walks(results, floors_doc, warnings)
    if n_stale_rejected:
        LOG.warning("rejected %d stale-walk summaries (filed before floors.frozen_at_utc)", n_stale_rejected)

    # 4. Derive condition booleans + per-recipe baseline-beat.
    beats_baseline = _derive_beats_baseline(floors_doc, results)
    conditions = {
        "floor_ordering_ok": _derive_floor_ordering_ok(floors_doc, results),
        "bit_identical_walk": _env_bool("POST_PASS_BIT_IDENTICAL_WALK_OK", True),
        "no_poisoned_indicator_holds_bypassed": _env_bool("POST_PASS_POISONED_GUARD_OK", False),
        # no_grandfathered_tiers is OVERRIDDEN True by assemble_tracker_draft — passing
        # whatever we believe lets a stale caller's wrong value get corrected, never
        # silently smuggled in.
    }

    # 5. Run the pure orchestrator — every methodology decision lives here.
    # All walks in one vintage MUST share the same panel fingerprint (they read the same
    # parquet snapshot); a divergence here is a real signal — a panel mid-revision raced
    # with the fan-out, or two walks loaded different snapshots. Don't silently first-wins;
    # surface the divergence in `warnings` so the operator can investigate.  Per F2 (QA
    # PR review): the attestation still records ONE fingerprint (first non-None) so the
    # downstream draft stays well-formed; the warning is the audit trail.
    fps = sorted({s["panel_fingerprint"] for s in results.values() if s and s.get("panel_fingerprint")})
    panel_fp = fps[0] if fps else None
    if len(fps) > 1:
        warnings.append(
            f"panel_fingerprint divergence across walks ({len(fps)} distinct fingerprints): "
            f"{fps} — using {panel_fp!r} for the attestation; investigate a mid-vintage "
            f"panel revision or a stale walk-driver image"
        )

    draft = pp.assemble_tracker_draft(
        results=results,
        prev_tiers=prev_tiers,
        beats_baseline=beats_baseline,
        conditions=conditions,
        run_id=vintage_id,
        panel_fingerprint=panel_fp,
        # Condition I: record WHEN floors were frozen alongside the boolean, so the
        # attestation carries the `floor_ordering_ok` evidence (the frozen-at anchor),
        # not just its pass/fail verdict.
        floors_frozen_at_utc=(floors_doc or {}).get("frozen_at_utc"),
    )

    # 6. Write the draft (NEVER to the live tracker — that's the PR/Majles path).
    draft_key = _DRAFT_KEY_TEMPLATE.format(vintage_id=vintage_id)
    envelope = {
        **draft,
        "vintage_id": vintage_id,
        "produced_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_prefix": f"s3://{bucket}/{prefix}",
        "warnings": warnings,
    }
    draft_uri = _put_json(bucket, draft_key, envelope)
    LOG.info("draft written: %s", draft_uri)

    return {
        "status": "ok",
        "vintage_id": vintage_id,
        "draft_s3_uri": draft_uri,
        "n_recipes_processed": len(recipe_ids),
        "n_stale_rejected": n_stale_rejected,  # FU2 per QA PR review — self-describing audit signal
        "n_transitions": len(draft["transitions"]),
        "attestation_summary": {
            "all_conditions_pass": draft["attestation"]["all_conditions_pass"],
            "tracker_pr_may_merge": draft["attestation"]["tracker_pr_may_merge"],
            "pending_majles_signoff": len(draft["attestation"]["transitions_pending_majles"]),
        },
        "warnings": warnings,
    }
