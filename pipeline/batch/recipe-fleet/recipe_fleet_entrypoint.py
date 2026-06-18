"""Recipe-fleet Batch entrypoint.

Runs the F-ML-1 walk (run_f_ml_1_poc.py) + extract_shap_importances.py +
compute_recipe_country_similarity.py + 5 in-walk capability scripts for a
batch of recipes sequentially inside a single Batch job. Designed for AWS
Batch EC2 Spot / Graviton (arm64, 2 vCPU / 4 GB).

Design doc: docs/specs/internal/ops/ml-track/aws-recipe-fleet-design.md §7

Per-recipe chain (FIX 1 — see inline comments):
  1. run_f_ml_1_poc.py        → f-ml-1-poc-summary.json + greedy-result.json
  2. extract_shap_importances.py → shap-importances-{recipe}.json
  3. compute_recipe_country_similarity.py → recipe-similarity-scores-{recipe}-{year}.json
  4. compute_track_record.py  → track-record-{recipe}-{year}.json
  5. compute_nearest_analog.py → nearest-analog-{recipe}-{year}.json
  6. compute_momentum.py      → momentum-{recipe}-{year}.json
  7. compute_driver.py        → driver-{recipe}-{year}.json
  8. compute_sensitivity.py   → sensitivity-{recipe}-{year}.json

Behaviour
---------
1. Sync indicator parquet panels from S3 ONCE (shared by all recipes in batch).
2. Download cohort-assignments.json from S3 ONCE (shared by all recipes in batch).
3. For each recipe_id in RECIPE_IDS (comma-separated env var):
   a. Skip if greedy-result.json already exists in S3 (resume-aware). See FIX 3.
   b. Sync any existing checkpoint blobs from S3 for this recipe.
   c. Run run_f_ml_1_poc.py with --output-dir pointing to a per-recipe local dir.
   d. Run extract_shap_importances.py + compute_recipe_country_similarity.py.
   e. Run the 5 in-walk capability scripts on the walk + similarity artifacts.
   f. Upload results + checkpoints to S3.
4. In canary mode (RUN_MODE=canary): emit cpu_utilization_pct_mean_walk +
   wall_clock_seconds + estimated_cost_usd to the result JSON. The SFN approval
   token is NOT written by this container (see FIX 4 comment below).

Environment variables (all have defaults for local testing)
------------------------------------------------------------
S3_BUCKET              : str  — data lake bucket name
PARQUET_DATA_PREFIX    : str  — S3 prefix for indicator parquet panels
ML_RESULTS_PREFIX      : str  — S3 prefix for per-recipe result JSONs
ML_CHECKPOINTS_PREFIX  : str  — S3 prefix for per-recipe checkpoint blobs
RECIPE_MANIFEST_S3_KEY : str  — S3 key for recipe-manifest.json
RECIPE_IDS             : str  — comma-separated list of recipe_ids to run
RUN_MODE               : str  — "canary" or "fleet" (default "fleet")
COHORT_SIDECAR_S3_KEY  : str  — S3 key for cohort-assignments.json (FIX 2)
EVALUATION_YEAR        : int  — OPTIONAL override of the scoring frontier. Unset
                                (default) → the entrypoint AUTO-resolves the frontier
                                per recipe from observed panel coverage (max observed
                                year + 1, D2). Set it only to pin a year (re-baseline
                                a graduate / historical canary).

S3 path conventions (trailing-slash prefixes):
  Parquet panels  : s3://{bucket}/{PARQUET_DATA_PREFIX}
  Results         : s3://{bucket}/{ML_RESULTS_PREFIX}{recipe_id}/
  Checkpoints     : s3://{bucket}/{ML_CHECKPOINTS_PREFIX}{recipe_id}/

NO Athena calls anywhere in this script — design §3 / §6 hard constraint.

FIX 4 — SFN task-token delivery:
  Approval-token delivery is via the qgi-recipe-fleet-approval SQS queue (the
  SFN approval state sends the token as the message body); the founder reads it
  from SQS and calls send-task-success. The container does NOT handle the token.
  The SFN $$.Task.Token only exists at the waitForTaskToken approval state
  (an SQS sendMessage state), NOT at the canary Batch job state. Writing it
  here would only ever write an empty string.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import psutil
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
LOG = logging.getLogger("recipe-fleet-entrypoint")

# ---------------------------------------------------------------------------
# Environment / configuration
# ---------------------------------------------------------------------------
S3_BUCKET = os.environ.get("S3_BUCKET", "")
PARQUET_DATA_PREFIX = os.environ.get(
    "PARQUET_DATA_PREFIX",
    "pipeline-A-indicator-extractor/output/parquet-completed/",
)
ML_RESULTS_PREFIX = os.environ.get("ML_RESULTS_PREFIX", "ml-results/")
ML_CHECKPOINTS_PREFIX = os.environ.get("ML_CHECKPOINTS_PREFIX", "ml-checkpoints/")
RECIPE_MANIFEST_S3_KEY = os.environ.get("RECIPE_MANIFEST_S3_KEY", "ml-results/recipe-manifest.json")
RECIPE_IDS_RAW = os.environ.get("RECIPE_IDS", "")
RUN_MODE = os.environ.get("RUN_MODE", "fleet")

# FIX 2: cohort sidecar S3 key — downloaded at startup, passed explicitly to
# every script that needs it (walk + similarity + track_record + nearest_analog).
COHORT_SIDECAR_S3_KEY = os.environ.get("COHORT_SIDECAR_S3_KEY", "reference/cohort-assignments.json")

# T20-R2: per-recipe pre-registered LOCK floors (recipe_id -> {lock_floor,
# cohort_loco_floor}). In fleet mode a recipe with no floor here is SKIPPED
# (never walked against the walk's civil_war-anchored default). See fleet-floor-annex.md.
RECIPE_FLOORS_S3_KEY = os.environ.get("RECIPE_FLOORS_S3_KEY", "reference/recipe-floors.json")


class FloorOrderingError(RuntimeError):
    """Raised when the per-recipe floors were not provably frozen BEFORE the walk."""


def assert_floor_ordering(floors_json: dict, walk_launch_utc: datetime) -> None:
    """FLEET-5 / trio Condition A (the highest-severity hole): a floor must be FROZEN
    BEFORE the walk that it judges — otherwise a floor re-derived from the same corpus
    the fleet is about to walk is a floor-shopping vector that re-creates the
    foreign_intervention failure class, 44 recipes at a time, with no one watching.

    Enforces (fleet mode only — canary falls back to the walk's default floor):
      1. The floors artifact carries frozen-before-walk PROVENANCE — top-level
         `frozen_at_utc`, `git_commit_sha`, `panel_fingerprint` all present + non-null.
         A floors file without provenance cannot be proven frozen-first → refuse.
      2. ORDERING: `frozen_at_utc` is strictly BEFORE the walk launch time. Floors
         frozen at/after launch were (or may have been) derived with knowledge of the
         walk corpus → refuse.

    NOTE the `panel_fingerprint` EQUALITY check (floors computed against the SAME corpus
    vintage being walked, not a stale one) lands with the floor-assembly step that records
    the fingerprint; this function already REQUIRES the field to be present so the schema
    is enforced from day one. Pure + testable."""
    missing = [k for k in ("frozen_at_utc", "git_commit_sha", "panel_fingerprint") if not floors_json.get(k)]
    if missing:
        raise FloorOrderingError(
            f"recipe-floors.json lacks frozen-before-walk provenance {missing}; cannot "
            f"prove floors were frozen before the walk (Condition A). Regenerate the "
            f"floors artifact with full provenance BEFORE launching the fleet."
        )
    try:
        frozen_at = datetime.fromisoformat(str(floors_json["frozen_at_utc"]))
    except ValueError as exc:
        raise FloorOrderingError(
            f"recipe-floors.json frozen_at_utc is not ISO-8601: {floors_json['frozen_at_utc']!r} ({exc})"
        ) from exc
    if frozen_at.tzinfo is None:
        frozen_at = frozen_at.replace(tzinfo=timezone.utc)
    if frozen_at >= walk_launch_utc:
        raise FloorOrderingError(
            f"FLOOR-SHOPPING GUARD: floors frozen at {frozen_at.isoformat()} are NOT "
            f"before the walk launch {walk_launch_utc.isoformat()} — a floor derived with "
            f"knowledge of the walk corpus is forbidden (Condition A). Freeze floors first."
        )


# Scoring frontier (D2). The hardcoded 2021 is GONE — leaving it made the LOCF
# nowcast fill inert on production data (Opus delivery-review finding #111). By
# default the entrypoint AUTO-resolves the frontier per recipe from observed panel
# coverage (resolve_frontier_year → max observed year + 1). Set EVALUATION_YEAR to
# an int only to PIN a year (e.g. re-baseline the graduate, or a historical canary).
_eval_env = os.environ.get("EVALUATION_YEAR", "").strip()
EVALUATION_YEAR_OVERRIDE: int | None = int(_eval_env) if _eval_env else None

# ---------------------------------------------------------------------------
# Path constants (container layout; see Dockerfile)
# ---------------------------------------------------------------------------
APP_DIR = Path("/app")
SCRIPTS_DIR = APP_DIR / "scripts"
# data/shape_inputs_v2/ is copied from qgi-ml at build time (FIX 2).
# extract_shap_importances.py resolves positives from REPO_ROOT/data/shape_inputs_v2/
# where REPO_ROOT = Path(__file__).parents[1] = /app. So /app/data/shape_inputs_v2/
# must exist — guaranteed by the COPY in the Dockerfile.
SHAPE_INPUTS_DIR = APP_DIR / "data" / "shape_inputs_v2"


_S3_CLIENT: Any = None


def _s3() -> Any:
    # Module-level singleton (#918): a fresh boto3.client per call wastes session +
    # credential-resolution work on every S3 op, and constructing one inside an
    # `except` clause (the old s3_object_exists) is what made the resume-guard fragile.
    # NB: the singleton is never reset on credential rotation — fine for a short-lived
    # Batch container; revisit if this entrypoint is ever run as a long-lived daemon.
    global _S3_CLIENT
    if _S3_CLIENT is None:
        _S3_CLIENT = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "eu-central-1"))
    return _S3_CLIENT


# ---------------------------------------------------------------------------
# S3 helpers (no Athena)
# ---------------------------------------------------------------------------


def s3_object_exists(bucket: str, key: str) -> bool:
    """True iff the object exists. A 404 → False; ANY other error (403/throttle/
    network) is RAISED, never swallowed (#918). The prior code caught a dynamically-
    constructed `_s3().exceptions.ClientError` and also had a bare `except Exception:
    return False`, so a permissions error read as 'object absent' — silently making
    the resume-guard re-run or mis-skip completed recipes on the fleet path."""
    try:
        _s3().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise  # 403 / throttle / etc. must surface — not be misread as "absent"


def resolve_canary_entry(job_summary: list[dict], canary_recipe: str) -> tuple[Any, str, bool]:
    """Find the canary recipe's OWN summary entry by id (#920) and decide whether it
    actually walked. Returns (entry|None, status, walked). `walked` is False for a
    missing entry or any 'skipped*' status — a skipped canary never ran a walk, so the
    SFN gate must not auto-approve the fan-out on it. Pure + unit-testable."""
    entry = next((e for e in job_summary if e.get("recipe_id") == canary_recipe), None)
    status = entry.get("status") if entry else "unknown"
    walked = bool(entry) and not str(status).startswith("skipped")
    return entry, status, walked


def _canary_message(walked: bool, status: str) -> str:
    """Human-facing canary-result message (#920 + review FU-1). Three honest cases:
    not-walked (skipped/missing) → DO NOT APPROVE; walked-but-failed (error/timeout)
    → review, do not approve on a failed walk; clean walk → review + approve."""
    if not walked:
        return (
            "DO NOT APPROVE: the canary recipe was SKIPPED (already in S3 or no floor "
            "on file) — no walk actually ran, so this result proves nothing about the "
            "fleet. Re-run the canary on a recipe that walks."
        )
    if str(status) in ("error", "timeout"):
        return (
            f"DO NOT APPROVE on a failed canary: the walk ran but ended status={status}. "
            "Investigate the failure before approving the fan-out."
        )
    return (
        "Canary complete. Review this file then use the SFN approval token from the "
        "qgi-recipe-fleet-approval SQS queue to call send-task-success and approve the fan-out."
    )


def s3_sync_prefix_down(bucket: str, prefix: str, local_dir: Path) -> int:
    """Download all objects under S3 prefix into local_dir. Returns count."""
    local_dir.mkdir(parents=True, exist_ok=True)
    s3 = _s3()
    paginator = s3.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Relative path within the prefix
            rel = key[len(prefix) :]
            if not rel:
                continue
            dest = local_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(dest))
            count += 1
    LOG.info("s3_sync_down: %d objects from s3://%s/%s → %s", count, bucket, prefix, local_dir)
    return count


def s3_download_file(bucket: str, key: str, local_path: Path) -> None:
    """Download a single S3 object to local_path."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    _s3().download_file(bucket, key, str(local_path))
    LOG.info("s3_download: s3://%s/%s → %s", bucket, key, local_path)


def s3_sync_dir_up(local_dir: Path, bucket: str, prefix: str) -> int:
    """Upload all files under local_dir to S3 prefix. Returns count of files
    actually uploaded (skipped-as-unchanged files are NOT counted).

    Content-aware: a file is skipped when an S3 object already exists at the
    target key AND its ContentLength matches the local file size AND its
    LastModified is ≥ the local file's mtime. Otherwise the local file is
    uploaded — covering new files, edits, and any case where we can't prove the
    S3 copy is fresh. Worth the head_object cost because the periodic-sync +
    multi-stage-emit pattern re-syncs the same dir 2-3 times per recipe, and
    most files (greedy-result.json, summary.json, country-scores.json) are
    written once and never rewritten within a recipe.

    QA follow-up #967 on PR #46 (2026-05-29 review)."""
    s3 = _s3()
    uploaded = 0
    skipped = 0
    for path in local_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(local_dir)
        key = f"{prefix}{rel.as_posix()}"
        local_size = path.stat().st_size
        local_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
            s3_size = head.get("ContentLength")
            s3_last = head.get("LastModified")  # tz-aware datetime
            if s3_size == local_size and s3_last is not None and s3_last >= local_mtime:
                skipped += 1
                continue
        except ClientError as exc:
            # 404 → upload (new key). Any other error → propagate; do NOT swallow
            # (mirrors the #918 fix on s3_object_exists).
            code = exc.response.get("Error", {}).get("Code")
            if code not in ("404", "NoSuchKey", "NotFound"):
                raise
        s3.upload_file(str(path), bucket, key)
        uploaded += 1
    LOG.info(
        "s3_sync_up: %d uploaded, %d skipped-unchanged from %s → s3://%s/%s",
        uploaded,
        skipped,
        local_dir,
        bucket,
        prefix,
    )
    return uploaded


def s3_upload_json(data: dict, bucket: str, key: str) -> None:
    _s3().put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2).encode(),
        ContentType="application/json",
    )
    LOG.info("Uploaded JSON → s3://%s/%s", bucket, key)


# ---------------------------------------------------------------------------
# CPU utilization sampler (canary metric — design §4 + §2a)
# ---------------------------------------------------------------------------


class CpuSampler:
    """Background CPU% sampler using psutil. Start before walk, stop after."""

    def __init__(self, interval: float = 5.0):
        self._interval = interval
        self._samples: list[float] = []
        self._running = False
        self._thread = None

    def start(self) -> None:
        import threading

        psutil.cpu_percent(interval=None)  # prime the counter
        self._running = True

        def _sample():
            while self._running:
                self._samples.append(psutil.cpu_percent(interval=self._interval))

        self._thread = threading.Thread(target=_sample, daemon=True)
        self._thread.start()

    def stop(self) -> float:
        """Stop sampling; return mean CPU% (0–100)."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._interval * 2)
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples)


class PeriodicCheckpointSync:
    """Sync the walk's output dir (which holds the #91 greedy-checkpoint.json +
    greedy-result.json) UP to S3 every `interval` seconds WHILE the walk runs.

    Why this matters (canary 2026-05-25): the walk writes its per-step checkpoint
    LOCALLY. Without this background sync the checkpoint only reached S3 after the
    walk finished — so a Spot reclaim mid-walk lost it and the retry restarted
    from greedy step 1. With it, the checkpoint is in S3 within `interval` of each
    step, so a reclaimed job's retry (or a fresh instance) downloads it and the
    walk's #91 resume picks up where it left off. Writes are atomic on the walk
    side (tmp+rename), so an in-flight sync at worst uploads a one-step-stale but
    valid checkpoint.
    """

    def __init__(self, local_dir: Path, bucket: str, prefix: str, interval: float = 90.0):
        self._local_dir = local_dir
        self._bucket = bucket
        self._prefix = prefix
        self._interval = interval
        self._running = False
        self._thread = None

    def start(self) -> None:
        import threading

        self._running = True

        def _loop():
            while self._running:
                # Sleep first so we don't double-sync at t=0 (the caller already
                # downloaded any prior checkpoint before launching the walk).
                for _ in range(int(self._interval)):
                    if not self._running:
                        return
                    time.sleep(1)
                try:
                    if self._local_dir.exists():
                        s3_sync_dir_up(self._local_dir, self._bucket, self._prefix)
                except Exception as exc:  # noqa: BLE001 — never let a sync error kill the walk
                    LOG.warning("checkpoint sync (periodic) failed, will retry: %s", exc)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=30)

    def flush(self) -> None:
        """One immediate synchronous checkpoint upload (used by the SIGTERM
        Spot-reclaim handler to capture the last <90s before the instance dies)."""
        try:
            if self._local_dir.exists():
                s3_sync_dir_up(self._local_dir, self._bucket, self._prefix)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("checkpoint flush on SIGTERM failed: %s", exc)


# ---------------------------------------------------------------------------
# Spot-reclaim (SIGTERM) handler
# ---------------------------------------------------------------------------
# AWS sends SIGTERM ~2 min before reclaiming a Spot instance, then SIGKILL.
# This handler writes a CLEAR marker to the log stream (so a watcher knows the
# run is handing off, rather than the stream just cutting off mid-line) and
# flushes the latest checkpoint to S3 so the retry resumes from the last step.
_ACTIVE_SYNC: PeriodicCheckpointSync | None = None


def _handle_sigterm(signum, frame):  # noqa: ANN001
    LOG.warning(
        "=== SIGTERM received (likely Spot reclaim) === flushing checkpoint to S3 "
        "and exiting; the Batch retry will resume from the last greedy step on a "
        "NEW log stream. This is the handoff marker — not a failure."
    )
    if _ACTIVE_SYNC is not None:
        _ACTIVE_SYNC.flush()
    LOG.warning("checkpoint flushed; exiting 1 for Batch retry/resume.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Script location helper
# ---------------------------------------------------------------------------


def _find_script(name: str) -> Path:
    """Return the Path to a named script, checking SCRIPTS_DIR then APP_DIR."""
    for candidate in (SCRIPTS_DIR / name, APP_DIR / name):
        if candidate.exists():
            return candidate
    # Return the SCRIPTS_DIR path even if absent — subprocess will surface the
    # error with a clear message rather than silently skipping.
    return SCRIPTS_DIR / name


# ---------------------------------------------------------------------------
# Walk runner
# ---------------------------------------------------------------------------


def run_walk(
    recipe_id: str,
    local_data_dir: Path,
    local_output_dir: Path,
    cohort_sidecar_path: Path,
    lock_floor: float | None = None,
    cohort_loco_floor: float | None = None,
) -> dict:
    """Invoke run_f_ml_1_poc.py as a subprocess.

    Returns a dict with at minimum {"status": "ok" | "error", ...}.

    The script writes its output JSON into local_output_dir.
    We pass --output-dir / --panel-dir / --positives-csv / --cohort-sidecar
    explicitly so the container never falls back to repo-relative defaults.

    FIX 1 — flags corrected vs original:
      BEFORE: --walk-output-dir (non-existent flag), --data-dir (non-existent flag)
              --checkpoint-dir (non-existent flag)
      AFTER:  --output-dir, --panel-dir, --positives-csv, --cohort-sidecar
              (all real flags from run_f_ml_1_poc._build_parser)
    """
    script = _find_script("run_f_ml_1_poc.py")
    local_output_dir.mkdir(parents=True, exist_ok=True)

    positives_csv = SHAPE_INPUTS_DIR / recipe_id / "positives.csv"

    cmd = [
        sys.executable,
        str(script),
        "--recipe-id",
        recipe_id,
        "--output-dir",
        str(local_output_dir),
        "--panel-dir",
        str(local_data_dir),
        "--positives-csv",
        str(positives_csv),
        "--cohort-sidecar",
        str(cohort_sidecar_path),
    ]
    # T20-R2: each recipe is judged against its pre-registered floor, NOT the
    # walk's civil_war-anchored default. The floor is resolved per recipe from
    # recipe-floors.json (see main); a recipe with no floor on file is SKIPPED
    # upstream, never run against the default.
    if lock_floor is not None:
        cmd += ["--lock-floor", str(lock_floor)]
    if cohort_loco_floor is not None:
        cmd += ["--cohort-loco-floor", str(cohort_loco_floor)]
    # FLEET-4c: the SFN Map sets N_JOBS = this job's per-recipe vCPU (#962); pass it to the
    # #961 parallel grid. Default 1 (serial, bit-identical) when unset or non-numeric. The
    # fleet runs only XGBoost (N_pos>=60) recipes, so n_jobs>1 is always the bit-identical path.
    n_jobs = os.environ.get("N_JOBS", "1")
    cmd += ["--n-jobs", n_jobs if n_jobs.isdigit() and int(n_jobs) >= 1 else "1"]

    LOG.info("Launching walk: %s", " ".join(cmd))
    t0 = time.monotonic()
    try:
        subprocess.run(
            cmd,
            capture_output=False,  # stdout/stderr stream to CloudWatch via awslogs
            check=True,
            timeout=32 * 3600,  # 32 h hard cap per recipe (below Batch 36 h limit)
        )
        elapsed = time.monotonic() - t0
        LOG.info("Walk complete for %s in %.0f s", recipe_id, elapsed)
        return {"status": "ok", "wall_clock_seconds": elapsed}
    except subprocess.CalledProcessError as exc:
        elapsed = time.monotonic() - t0
        LOG.error("Walk FAILED for %s after %.0f s: returncode=%d", recipe_id, elapsed, exc.returncode)
        return {"status": "error", "returncode": exc.returncode, "wall_clock_seconds": elapsed}
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        LOG.error("Walk TIMED OUT for %s after %.0f s", recipe_id, elapsed)
        return {"status": "timeout", "wall_clock_seconds": elapsed}


def run_score_countries(
    recipe_id: str,
    walk_output_dir: Path,
    local_data_dir: Path,
) -> dict:
    """[#967] Invoke score_countries.py as a subprocess AFTER the walk.

    Reads the walk's `f-ml-1-poc-summary.json` + positives.csv + the locked
    indicators' panels; refits XGBoost on the locked configuration; scores every
    country at its most-recent year of feature support; emits SHAP per country,
    indicator movement, top-3 nearest-analogs, score distribution, and 5-fold-CV
    LOO indicator-sensitivity into `country-scores.json` alongside the walk
    summary. The PeriodicCheckpointSync uploads it to S3 on the next tick.

    A non-zero return code DOES NOT fail the recipe — the walk summary is the
    primary artifact, and the post-pass Lambda + dashboard render honestly when
    `country-scores.json` is absent. The status is logged for the operator to
    surface in CloudWatch."""
    script = _find_script("score_countries.py")
    summary_path = walk_output_dir / "f-ml-1-poc-summary.json"
    if not summary_path.exists():
        LOG.warning("score_countries: walk summary missing at %s — skipping", summary_path)
        return {"status": "skipped", "reason": "summary_absent"}
    positives_csv = SHAPE_INPUTS_DIR / recipe_id / "positives.csv"
    if not positives_csv.exists():
        LOG.warning("score_countries: positives.csv missing at %s — skipping", positives_csv)
        return {"status": "skipped", "reason": "positives_absent"}

    cmd = [
        sys.executable,
        str(script),
        "--recipe-id",
        recipe_id,
        "--summary-path",
        str(summary_path),
        "--panel-dir",
        str(local_data_dir),
        "--positives-csv",
        str(positives_csv),
        "--output-dir",
        str(walk_output_dir),
    ]
    # Timeout default 1800 s (30 min) — local bake averaged ~3 min × 10 recipes.
    # Override via env var SCORE_COUNTRIES_TIMEOUT_SECONDS for fat recipes
    # (N_pos > 300) where the K × 5-fold LOO ablation dominates. QA
    # follow-up #967 on PR #46 (2026-05-29 review).
    try:
        timeout_s = int(os.environ.get("SCORE_COUNTRIES_TIMEOUT_SECONDS", "1800"))
        if timeout_s <= 0:
            raise ValueError("must be a positive integer (seconds)")
    except ValueError as exc:
        LOG.warning(
            "SCORE_COUNTRIES_TIMEOUT_SECONDS=%r is not a positive integer (%s) — falling back to the 1800 s default.",
            os.environ.get("SCORE_COUNTRIES_TIMEOUT_SECONDS"),
            exc,
        )
        timeout_s = 1800
    LOG.info("Launching score_countries (timeout=%ds): %s", timeout_s, " ".join(cmd))
    t0 = time.monotonic()
    try:
        subprocess.run(
            cmd,
            capture_output=False,  # awslogs picks up stdout/stderr
            check=True,
            timeout=timeout_s,
        )
        elapsed = time.monotonic() - t0
        LOG.info("score_countries complete for %s in %.0f s", recipe_id, elapsed)
        return {"status": "ok", "wall_clock_seconds": elapsed}
    except subprocess.CalledProcessError as exc:
        elapsed = time.monotonic() - t0
        LOG.warning(
            "score_countries FAILED for %s after %.0f s (rc=%d) — walk summary stands; country-scores.json absent.",
            recipe_id,
            elapsed,
            exc.returncode,
        )
        return {"status": "error", "returncode": exc.returncode, "wall_clock_seconds": elapsed}
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        LOG.warning("score_countries TIMED OUT for %s after %.0f s", recipe_id, elapsed)
        return {"status": "timeout", "wall_clock_seconds": elapsed}


# ---------------------------------------------------------------------------
# Scoring-frontier resolution (D2 — replaces the hardcoded 2021)
# ---------------------------------------------------------------------------


def resolve_frontier_year(selected_indicators: list[str], panel_dir: Path) -> int:
    """D2: scoring frontier = max OBSERVED year across the recipe's selected
    indicators + 1. Production panels carry `is_predicted` (ETS) rows which we
    DISCARD (D1) — only observed rows define the frontier. This mirrors the
    `--evaluation-year auto` logic in compute_recipe_country_similarity.py; the
    resolved int is then passed EXPLICITLY to every scoring/capability script so
    the whole chain agrees on one frontier (and the scores filename is
    deterministic). Raises if no observed rows are found."""
    import pandas as pd  # available in the container; local import keeps cold-start lean

    max_obs: int | None = None
    for ind in selected_indicators:
        path = panel_dir / ind / f"{ind}.parquet"
        if not path.exists():
            LOG.warning("Panel missing for indicator %s at %s — skipped in frontier calc", ind, path)
            continue
        df = pd.read_parquet(path)
        if "is_predicted" in df.columns:
            df = df[~df["is_predicted"].astype(bool)]
        if "value" in df.columns:
            df = df[df["value"].notna()]
        if len(df):
            yr = int(df["year"].max())
            max_obs = yr if max_obs is None else max(max_obs, yr)
    if max_obs is None:
        raise RuntimeError(
            f"Could not resolve scoring frontier — no observed rows for indicators {selected_indicators}"
        )
    return max_obs + 1


# ---------------------------------------------------------------------------
# Per-recipe capability chain (FIX 1)
# ---------------------------------------------------------------------------


def run_capability_chain(
    recipe_id: str,
    walk_output_dir: Path,
    local_data_dir: Path,
    cohort_sidecar_path: Path,
    evaluation_year: int,
) -> dict:
    """Run the full post-walk capability chain for one recipe.

    Chain (design §5 + te-new-capabilities-spec.md):
      Step A: extract_shap_importances.py  → shap-importances-{recipe}.json
      Step B: compute_recipe_country_similarity.py
                                           → recipe-similarity-scores-{recipe}-{year}.json
      Steps C–G: the 5 capability scripts

    FIX 1 — every subprocess call now uses the script's ACTUAL argparse flags.
    The original code used --walk-output-dir and --data-dir (both non-existent),
    which caused argparse exit 2 and silent zero output on every run. The
    similarity step was missing entirely, which caused a hard dependency crash
    for 4 of the 5 capability scripts (they all require --scores-file).

    Returns a dict of {step_name: "ok" | "error" | "not_found"}.
    """
    results: dict[str, str] = {}

    walk_summary_path = walk_output_dir / "f-ml-1-poc-summary.json"
    shap_path = walk_output_dir / f"shap-importances-{recipe_id}.json"
    scores_path = walk_output_dir / f"recipe-similarity-scores-{recipe_id}-{evaluation_year}.json"

    # -------------------------------------------------------------------------
    # Step A: extract_shap_importances.py
    # Produces: shap-importances-{recipe_id}.json in walk_output_dir.
    # Note: this script resolves positives via REPO_ROOT/data/shape_inputs_v2/
    # (REPO_ROOT = /app in container). The COPY in the Dockerfile ensures
    # /app/data/shape_inputs_v2/ is present. It also uses a hardcoded panel path
    # (REPO_ROOT/data/parquet_panels); we symlink local_data_dir there at
    # startup if the paths differ, OR rely on the fact that run_f_ml_1_poc.py
    # has already loaded all panels from local_data_dir and the summary JSON
    # carries all needed indicator metadata — extract_shap_importances only
    # needs the panels at REPO_ROOT/data/parquet_panels. See assumption note
    # in the canary report at the end of this file.
    #
    # FIX 1 — flags (extract_shap_importances._main argparse):
    #   --recipe-id (required)
    #   --walk-summary (required)
    #   --output-dir (required)
    #   --seed (optional, default 12345 — matches walk default)
    # -------------------------------------------------------------------------
    step_name = "extract_shap_importances.py"
    script = _find_script(step_name)
    if not script.exists():
        LOG.warning("Script not found: %s — skipping SHAP step", step_name)
        results[step_name] = "not_found"
    else:
        cmd = [
            sys.executable,
            str(script),
            "--recipe-id",
            recipe_id,
            "--walk-summary",
            str(walk_summary_path),
            "--output-dir",
            str(walk_output_dir),
        ]
        LOG.info("Running %s", step_name)
        try:
            subprocess.run(cmd, check=True, timeout=1800)
            results[step_name] = "ok"
        except Exception as exc:  # noqa: BLE001
            LOG.error("%s failed: %s", step_name, exc)
            results[step_name] = "error"

    # -------------------------------------------------------------------------
    # Step B: compute_recipe_country_similarity.py
    # Hard dependency of steps C, D, E, F, G (all read --scores-file).
    # Produces: recipe-similarity-scores-{recipe_id}-{evaluation_year}.json
    #
    # FIX 1 — flags (compute_recipe_country_similarity._main argparse):
    #   --recipe-id (required)
    #   --walk-summary (required)
    #   --shap-importances (required) ← was MISSING entirely in original code
    #   --output-dir (required)
    #   --panel-dir (optional, default REPO_ROOT/data/parquet_panels)
    #   --evaluation-year (we pass the entrypoint-resolved frontier int explicitly,
    #                       so the script does NOT use its 'auto' default here)
    #   --top-k-charts (optional)
    # BEFORE: step was missing entirely → argparse exit 2 on all 5 capability scripts
    # AFTER: step added; --shap-importances points to shap_path produced in Step A
    # -------------------------------------------------------------------------
    if results.get(step_name) != "ok":
        LOG.warning("Skipping similarity step — SHAP step did not complete successfully")
        results["compute_recipe_country_similarity.py"] = "skipped_shap_failed"
    else:
        step_name = "compute_recipe_country_similarity.py"
        script = _find_script(step_name)
        if not script.exists():
            LOG.warning("Script not found: %s — skipping", step_name)
            results[step_name] = "not_found"
        else:
            cmd = [
                sys.executable,
                str(script),
                "--recipe-id",
                recipe_id,
                "--walk-summary",
                str(walk_summary_path),
                "--shap-importances",
                str(shap_path),
                "--output-dir",
                str(walk_output_dir),
                "--panel-dir",
                str(local_data_dir),
                "--evaluation-year",
                str(evaluation_year),
            ]
            LOG.info("Running %s", step_name)
            try:
                subprocess.run(cmd, check=True, timeout=1800)
                results[step_name] = "ok"
            except Exception as exc:  # noqa: BLE001
                LOG.error("%s failed: %s", step_name, exc)
                results[step_name] = "error"

    # Remaining capability scripts all depend on the scores file produced in step B.
    similarity_ok = results.get("compute_recipe_country_similarity.py") == "ok"
    if not similarity_ok:
        LOG.warning("Similarity step did not complete — skipping capability scripts that require --scores-file")

    # -------------------------------------------------------------------------
    # Step C: compute_track_record.py
    # FIX 1 — flags (compute_track_record._build_parser argparse):
    #   --recipe-id (required)
    #   --walk-summary (required)
    #   --scores-file (required) ← was missing; hard dependency on similarity step
    #   --panel-dir (optional)
    #   --cohort-sidecar (optional, but must be a real path in container)
    #   --output-dir (required)
    #   --seed (optional)
    # BEFORE: --walk-output-dir (wrong), --data-dir (wrong)
    # AFTER: --walk-summary, --scores-file, --panel-dir, --cohort-sidecar, --output-dir
    # -------------------------------------------------------------------------
    step_name = "compute_track_record.py"
    if not similarity_ok:
        results[step_name] = "skipped_similarity_failed"
    else:
        script = _find_script(step_name)
        if not script.exists():
            LOG.warning("Script not found: %s — skipping", step_name)
            results[step_name] = "not_found"
        else:
            cmd = [
                sys.executable,
                str(script),
                "--recipe-id",
                recipe_id,
                "--walk-summary",
                str(walk_summary_path),
                "--scores-file",
                str(scores_path),
                "--panel-dir",
                str(local_data_dir),
                "--cohort-sidecar",
                str(cohort_sidecar_path),
                "--output-dir",
                str(walk_output_dir),
            ]
            LOG.info("Running %s", step_name)
            try:
                subprocess.run(cmd, check=True, timeout=1800)
                results[step_name] = "ok"
            except Exception as exc:  # noqa: BLE001
                LOG.error("%s failed: %s", step_name, exc)
                results[step_name] = "error"

    # -------------------------------------------------------------------------
    # Step D: compute_nearest_analog.py
    # FIX 1 — flags (compute_nearest_analog._build_parser argparse):
    #   --recipe-id (required)
    #   --scores-file (required)
    #   --walk-summary (required)
    #   --panel-dir (optional)
    #   --cohort-assignments (optional) ← note: flag name differs from track_record!
    #                                      compute_nearest_analog uses --cohort-assignments
    #                                      NOT --cohort-sidecar
    #   --output-dir (required)
    #   --top-k (optional)
    #   --analog-floor (optional)
    #   --evaluation-year (optional)
    # BEFORE: --walk-output-dir (wrong), --data-dir (wrong)
    # AFTER: --scores-file, --walk-summary, --panel-dir, --cohort-assignments, --output-dir
    # -------------------------------------------------------------------------
    step_name = "compute_nearest_analog.py"
    if not similarity_ok:
        results[step_name] = "skipped_similarity_failed"
    else:
        script = _find_script(step_name)
        if not script.exists():
            LOG.warning("Script not found: %s — skipping", step_name)
            results[step_name] = "not_found"
        else:
            cmd = [
                sys.executable,
                str(script),
                "--recipe-id",
                recipe_id,
                "--scores-file",
                str(scores_path),
                "--walk-summary",
                str(walk_summary_path),
                "--panel-dir",
                str(local_data_dir),
                "--cohort-assignments",
                str(cohort_sidecar_path),
                "--output-dir",
                str(walk_output_dir),
                "--evaluation-year",
                str(evaluation_year),
            ]
            LOG.info("Running %s", step_name)
            try:
                subprocess.run(cmd, check=True, timeout=1800)
                results[step_name] = "ok"
            except Exception as exc:  # noqa: BLE001
                LOG.error("%s failed: %s", step_name, exc)
                results[step_name] = "error"

    # -------------------------------------------------------------------------
    # Step E: compute_momentum.py
    # FIX 1 — flags (compute_momentum._build_parser argparse):
    #   --recipe-id (required)
    #   --scores-file (required)
    #   --walk-summary (required)
    #   --panel-dir (optional)
    #   --output-dir (required)
    #   --evaluation-year (optional)
    #   --n-offsets (optional)
    # No --cohort-sidecar or --cohort-assignments (this script doesn't use cohorts).
    # BEFORE: --walk-output-dir (wrong), --data-dir (wrong)
    # AFTER: --scores-file, --walk-summary, --panel-dir, --output-dir, --evaluation-year
    # -------------------------------------------------------------------------
    step_name = "compute_momentum.py"
    if not similarity_ok:
        results[step_name] = "skipped_similarity_failed"
    else:
        script = _find_script(step_name)
        if not script.exists():
            LOG.warning("Script not found: %s — skipping", step_name)
            results[step_name] = "not_found"
        else:
            cmd = [
                sys.executable,
                str(script),
                "--recipe-id",
                recipe_id,
                "--scores-file",
                str(scores_path),
                "--walk-summary",
                str(walk_summary_path),
                "--panel-dir",
                str(local_data_dir),
                "--output-dir",
                str(walk_output_dir),
                "--evaluation-year",
                str(evaluation_year),
            ]
            LOG.info("Running %s", step_name)
            try:
                subprocess.run(cmd, check=True, timeout=1800)
                results[step_name] = "ok"
            except Exception as exc:  # noqa: BLE001
                LOG.error("%s failed: %s", step_name, exc)
                results[step_name] = "error"

    # -------------------------------------------------------------------------
    # Step F: compute_driver.py
    # FIX 1 — flags (compute_driver._build_parser argparse):
    #   --scores-file (required)
    #   --output-dir (required)
    #   --catalog-file (optional, currently unused in script)
    # No --recipe-id (inferred from scores file). No --walk-summary. No --panel-dir.
    # BEFORE: --recipe-id (wrong for this script), --walk-output-dir (wrong), --data-dir (wrong)
    # AFTER: --scores-file, --output-dir only
    # -------------------------------------------------------------------------
    step_name = "compute_driver.py"
    if not similarity_ok:
        results[step_name] = "skipped_similarity_failed"
    else:
        script = _find_script(step_name)
        if not script.exists():
            LOG.warning("Script not found: %s — skipping", step_name)
            results[step_name] = "not_found"
        else:
            cmd = [
                sys.executable,
                str(script),
                "--scores-file",
                str(scores_path),
                "--output-dir",
                str(walk_output_dir),
            ]
            LOG.info("Running %s", step_name)
            try:
                subprocess.run(cmd, check=True, timeout=1800)
                results[step_name] = "ok"
            except Exception as exc:  # noqa: BLE001
                LOG.error("%s failed: %s", step_name, exc)
                results[step_name] = "error"

    # -------------------------------------------------------------------------
    # Step G: compute_sensitivity.py
    # FIX 1 — flags (compute_sensitivity._build_parser argparse):
    #   --scores-file (required)
    #   --output-dir (required)
    # No --recipe-id, no --walk-summary, no --panel-dir.
    # BEFORE: --recipe-id (wrong), --walk-output-dir (wrong), --data-dir (wrong)
    # AFTER: --scores-file, --output-dir only
    # -------------------------------------------------------------------------
    step_name = "compute_sensitivity.py"
    if not similarity_ok:
        results[step_name] = "skipped_similarity_failed"
    else:
        script = _find_script(step_name)
        if not script.exists():
            LOG.warning("Script not found: %s — skipping", step_name)
            results[step_name] = "not_found"
        else:
            cmd = [
                sys.executable,
                str(script),
                "--scores-file",
                str(scores_path),
                "--output-dir",
                str(walk_output_dir),
            ]
            LOG.info("Running %s", step_name)
            try:
                subprocess.run(cmd, check=True, timeout=1800)
                results[step_name] = "ok"
            except Exception as exc:  # noqa: BLE001
                LOG.error("%s failed: %s", step_name, exc)
                results[step_name] = "error"

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not S3_BUCKET:
        LOG.error("S3_BUCKET env var is required")
        sys.exit(1)

    # Catch Spot reclaim (SIGTERM ~2 min before kill): log a clean handoff
    # marker + flush the checkpoint to S3 so the retry resumes (see handler).
    signal.signal(signal.SIGTERM, _handle_sigterm)

    recipe_ids = [r.strip() for r in RECIPE_IDS_RAW.split(",") if r.strip()]
    if not recipe_ids:
        LOG.error("RECIPE_IDS env var is empty or not set")
        sys.exit(1)

    LOG.info(
        "recipe-fleet-entrypoint starting | mode=%s | recipes=%s | bucket=%s | eval_year=%s",
        RUN_MODE,
        recipe_ids,
        S3_BUCKET,
        EVALUATION_YEAR_OVERRIDE if EVALUATION_YEAR_OVERRIDE is not None else "auto (per-recipe observed frontier)",
    )

    with tempfile.TemporaryDirectory(prefix="qgi-fleet-") as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        # Sync panels to the HARDCODED default location REPO_ROOT/data/parquet_panels
        # (= /app/data/parquet_panels in-container). extract_shap_importances.py +
        # compute_recipe_country_similarity.py resolve panels from that fixed path,
        # while the walk + capabilities take --panel-dir; pointing both at the same
        # real directory makes the whole chain work without a symlink. Container fs
        # is ephemeral so writing under /app at runtime is fine.
        local_data_dir = APP_DIR / "data" / "parquet_panels"
        local_output_dir = tmpdir / "walk-output"
        local_checkpoints_root = tmpdir / "checkpoints"
        local_output_dir.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------
        # Step 1: sync indicator parquet panels ONCE for all recipes.
        # ------------------------------------------------------------------
        LOG.info("Syncing parquet panels from s3://%s/%s ...", S3_BUCKET, PARQUET_DATA_PREFIX)
        n_parquet = s3_sync_prefix_down(S3_BUCKET, PARQUET_DATA_PREFIX, local_data_dir)
        LOG.info("Parquet sync complete: %d objects", n_parquet)

        # ------------------------------------------------------------------
        # Step 1b: download cohort-assignments.json ONCE for all recipes.
        # FIX 2 — cohort sidecar is a qgi-data reference artifact (not in
        # qgi-ml). Download from S3 at startup; pass the local path explicitly
        # to every script that needs it (walk, track_record, nearest_analog).
        # ------------------------------------------------------------------
        local_cohort_sidecar = tmpdir / "cohort-assignments.json"
        LOG.info(
            "Downloading cohort sidecar from s3://%s/%s ...",
            S3_BUCKET,
            COHORT_SIDECAR_S3_KEY,
        )
        try:
            s3_download_file(S3_BUCKET, COHORT_SIDECAR_S3_KEY, local_cohort_sidecar)
            LOG.info("Cohort sidecar downloaded → %s", local_cohort_sidecar)
        except Exception as exc:  # noqa: BLE001
            LOG.error(
                "FATAL: failed to download cohort sidecar from s3://%s/%s: %s — "
                "cannot proceed without it (walk + LOCK gate + track_record require it)",
                S3_BUCKET,
                COHORT_SIDECAR_S3_KEY,
                exc,
            )
            sys.exit(1)

        # -- Per-recipe floors (T20-R2). Non-fatal if absent: fleet recipes then
        #    skip individually (never walked against a default floor); canary mode
        #    falls back to the walk's default floor. --
        # Captured BEFORE any recipe is walked: floors must be frozen before this.
        walk_launch_utc = datetime.now(timezone.utc)
        local_floors = tmpdir / "recipe-floors.json"
        recipe_floors: dict[str, dict] = {}
        floors_json: dict = {}
        try:
            s3_download_file(S3_BUCKET, RECIPE_FLOORS_S3_KEY, local_floors)
            floors_json = json.loads(local_floors.read_text(encoding="utf-8"))
            recipe_floors = floors_json.get("floors", {})
            LOG.info("Loaded %d per-recipe floors from s3://%s/%s", len(recipe_floors), S3_BUCKET, RECIPE_FLOORS_S3_KEY)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("No recipe-floors.json (s3://%s/%s): %s", S3_BUCKET, RECIPE_FLOORS_S3_KEY, exc)
        # Review followup: in FLEET mode a missing/empty/malformed floors file must
        # fail LOUDLY (like the cohort sidecar), not silently skip every recipe.
        if RUN_MODE == "fleet" and not recipe_floors:
            LOG.error(
                "FATAL: fleet mode but zero per-recipe floors loaded from s3://%s/%s — "
                "refusing to run a no-op fleet (T20-R2).",
                S3_BUCKET,
                RECIPE_FLOORS_S3_KEY,
            )
            sys.exit(1)
        # FLEET-5 / Condition A: refuse to walk unless the floors were provably FROZEN
        # BEFORE this run launched (kills the floor-shopping vector). Fail-loud in fleet.
        if RUN_MODE == "fleet":
            try:
                assert_floor_ordering(floors_json, walk_launch_utc)
                LOG.info(
                    "Floor-ordering OK (Condition A): floors frozen %s, launch %s.",
                    floors_json.get("frozen_at_utc"),
                    walk_launch_utc.isoformat(),
                )
            except FloorOrderingError as exc:
                LOG.error("FATAL (Condition A): %s", exc)
                sys.exit(1)

        # FIX 4 — SFN task-token write REMOVED.
        # The SFN $$.Task.Token only exists at the waitForTaskToken approval
        # state (an SQS sendMessage state), NOT at this Batch job state. Any
        # token present in the environment here is empty. Approval-token
        # delivery is via the qgi-recipe-fleet-approval SQS queue: the SFN
        # sends the token as the message body; the founder reads it from SQS
        # and calls send-task-success. This container does not handle the token.

        # ------------------------------------------------------------------
        # Step 2: process each recipe in the batch.
        # ------------------------------------------------------------------
        cpu_sampler = CpuSampler(interval=5.0)
        cpu_sampler.start()
        fleet_start = time.monotonic()

        job_summary: list[dict] = []

        for recipe_id in recipe_ids:
            # -- Resume guard: skip if greedy-result.json already in S3 --
            # FIX 3 — key was "{ML_RESULTS_PREFIX}{recipe_id}-greedy-result.json"
            # (a flat key). Corrected to "{ML_RESULTS_PREFIX}{recipe_id}/greedy-result.json"
            # because the entrypoint uploads the walk output dir with the prefix
            # "{ML_RESULTS_PREFIX}{recipe_id}/" — so the actual S3 key for the
            # greedy-result file is the per-recipe prefix + filename.
            # BEFORE: f"{ML_RESULTS_PREFIX}{recipe_id}-greedy-result.json"
            # AFTER:  f"{ML_RESULTS_PREFIX}{recipe_id}/greedy-result.json"
            greedy_result_key = f"{ML_RESULTS_PREFIX}{recipe_id}/greedy-result.json"
            if s3_object_exists(S3_BUCKET, greedy_result_key):
                LOG.info("SKIP %s — greedy-result.json already in S3 (%s)", recipe_id, greedy_result_key)
                job_summary.append({"recipe_id": recipe_id, "status": "skipped"})
                continue

            # T20-R2: resolve this recipe's pre-registered floor. In fleet mode a
            # recipe with no floor on file is SKIPPED — never walked against the default.
            floor_entry = recipe_floors.get(recipe_id)
            if floor_entry is None and RUN_MODE == "fleet":
                LOG.warning(
                    "SKIP %s — no floor in recipe-floors.json (T20-R2: no walk against the civil_war-anchored default)",
                    recipe_id,
                )
                job_summary.append({"recipe_id": recipe_id, "status": "skipped_no_floor"})
                continue
            if floor_entry is None:  # canary mode only (fleet already skipped above)
                LOG.warning(
                    "canary mode: %s runs against the walk DEFAULT floor (0.7986/0.68) — T20-R2 inapplicable in canary",
                    recipe_id,
                )
            elif floor_entry.get("lock_floor") is None or floor_entry.get("cohort_loco_floor") is None:
                # review followup (FU-B): a partial floor entry must fail LOUDLY, not fall to
                # a default. An `assert` was used here, but asserts are stripped under
                # `python -O`, which would silently let a partial floor through in an
                # optimized runtime. Use an explicit exit so the guard survives -O.
                LOG.error(
                    "FATAL: recipe-floors.json entry for %s is missing lock_floor "
                    "or cohort_loco_floor — refusing to walk against a partial floor",
                    recipe_id,
                )
                sys.exit(1)

            LOG.info("=== Processing recipe: %s ===", recipe_id)
            recipe_start = time.monotonic()

            # Per-recipe walk output dir and checkpoint dir
            walk_output_dir = local_output_dir / f"run_{recipe_id}"
            walk_output_dir.mkdir(parents=True, exist_ok=True)

            local_ckpt_dir = local_checkpoints_root / recipe_id
            local_ckpt_dir.mkdir(parents=True, exist_ok=True)
            ckpt_s3_prefix = f"{ML_CHECKPOINTS_PREFIX}{recipe_id}/"

            # Sync any existing checkpoints from S3 (resume from interruption)
            # run_f_ml_1_poc.py writes greedy-checkpoint.json + greedy-result.json
            # into --output-dir (= walk_output_dir). Sync from the results prefix
            # so a pre-existing greedy-result.json is picked up by the walk's own
            # checkpoint-resume logic.
            results_s3_prefix = f"{ML_RESULTS_PREFIX}{recipe_id}/"
            s3_sync_prefix_down(S3_BUCKET, results_s3_prefix, walk_output_dir)

            # -- Run walk, syncing the checkpoint to S3 every 90s so a Spot
            #    reclaim mid-walk is recoverable (the retry resumes from the last
            #    synced greedy step instead of restarting). Canary 2026-05-25. --
            global _ACTIVE_SYNC
            ckpt_sync = PeriodicCheckpointSync(walk_output_dir, S3_BUCKET, results_s3_prefix, interval=90.0)
            _ACTIVE_SYNC = ckpt_sync  # SIGTERM handler flushes this on Spot reclaim
            ckpt_sync.start()
            try:
                walk_result = run_walk(
                    recipe_id=recipe_id,
                    local_data_dir=local_data_dir,
                    local_output_dir=walk_output_dir,
                    cohort_sidecar_path=local_cohort_sidecar,
                    lock_floor=(floor_entry or {}).get("lock_floor"),
                    cohort_loco_floor=(floor_entry or {}).get("cohort_loco_floor"),
                )
            finally:
                ckpt_sync.stop()
                _ACTIVE_SYNC = None

            # -- Final upload of walk outputs to S3 (even on failure) --
            # greedy-checkpoint.json + greedy-result.json so a reclaimed Spot job
            # can resume from where it left off.
            if walk_output_dir.exists():
                s3_sync_dir_up(walk_output_dir, S3_BUCKET, results_s3_prefix)

            # [#967] Per-country scoring step — runs ONLY on a successful walk
            # (consumes the summary). Failure of this step is non-fatal: the
            # walk summary stands; country-scores.json is absent in S3; the
            # post-pass Lambda + dashboard render the gap honestly.
            score_result: dict = {"status": "skipped", "reason": "walk_not_ok"}
            if walk_result.get("status") == "ok":
                score_result = run_score_countries(
                    recipe_id=recipe_id,
                    walk_output_dir=walk_output_dir,
                    local_data_dir=local_data_dir,
                )
                # Re-sync so country-scores.json lands in S3 alongside the summary.
                if walk_output_dir.exists():
                    s3_sync_dir_up(walk_output_dir, S3_BUCKET, results_s3_prefix)

            cap_results: dict[str, str] = {}
            if walk_result.get("status") == "ok":
                # -- D2: resolve this recipe's scoring frontier from the walk's
                #    selected indicators' observed coverage (replaces hardcoded 2021).
                #    EVALUATION_YEAR env pins it; otherwise auto from panels. --
                if EVALUATION_YEAR_OVERRIDE is not None:
                    eval_year = EVALUATION_YEAR_OVERRIDE
                    LOG.info("Scoring frontier for %s PINNED to %d (EVALUATION_YEAR override)", recipe_id, eval_year)
                else:
                    with open(walk_output_dir / "f-ml-1-poc-summary.json", encoding="utf-8") as f:
                        _walk = json.load(f)
                    _selected = _walk["greedy_outer_loop"]["selected_indicators"]
                    eval_year = resolve_frontier_year(_selected, local_data_dir)
                    LOG.info(
                        "Scoring frontier for %s AUTO-resolved to %d (selected=%s)", recipe_id, eval_year, _selected
                    )

                # -- Run SHAP extraction + similarity + 5 capability scripts --
                cap_results = run_capability_chain(
                    recipe_id=recipe_id,
                    walk_output_dir=walk_output_dir,
                    local_data_dir=local_data_dir,
                    cohort_sidecar_path=local_cohort_sidecar,
                    evaluation_year=eval_year,
                )

                # -- Upload capability outputs to S3 --
                if walk_output_dir.exists():
                    s3_sync_dir_up(walk_output_dir, S3_BUCKET, results_s3_prefix)

            recipe_elapsed = time.monotonic() - recipe_start
            recipe_summary = {
                "recipe_id": recipe_id,
                "status": walk_result.get("status", "unknown"),
                "walk_wall_clock_seconds": walk_result.get("wall_clock_seconds"),
                "capability_results": cap_results,
                "score_countries": score_result,  # #967 — per-country scoring step result
            }
            job_summary.append(recipe_summary)
            LOG.info(
                "Recipe %s done in %.0f s | status=%s",
                recipe_id,
                recipe_elapsed,
                walk_result.get("status"),
            )

        # ------------------------------------------------------------------
        # Step 3: finalize canary metrics and upload summary.
        # ------------------------------------------------------------------
        fleet_elapsed = time.monotonic() - fleet_start
        cpu_mean = cpu_sampler.stop()

        # Rough cost estimate: c7g.large on-demand is ~$0.0725/hr in eu-central-1.
        # Spot is typically ~60-70% off → ~$0.025/hr. Use Spot estimate.
        _SPOT_HOURLY_USD = 0.025
        estimated_cost_usd = (_SPOT_HOURLY_USD * fleet_elapsed) / 3600

        summary = {
            "run_mode": RUN_MODE,
            "recipe_ids": recipe_ids,
            "job_summary": job_summary,
            "fleet_wall_clock_seconds": fleet_elapsed,
            "cpu_utilization_pct_mean_walk": round(cpu_mean, 1),
            "estimated_cost_usd": round(estimated_cost_usd, 4),
        }
        LOG.info("Fleet summary: %s", json.dumps(summary, indent=2))

        # Upload per-run fleet summary
        run_name = os.environ.get("AWS_BATCH_JOB_ID", "local")
        summary_key = f"{ML_RESULTS_PREFIX}fleet-summary-{run_name}.json"
        s3_upload_json(summary, S3_BUCKET, summary_key)

        # In canary mode: also write a canary-specific result for the SFN gate.
        if RUN_MODE == "canary" and recipe_ids:
            canary_recipe = recipe_ids[0]
            canary_result_key = f"{ML_RESULTS_PREFIX}canary-result-{canary_recipe}.json"
            # Look up the canary recipe's OWN summary entry by id (#920) — never the
            # positional job_summary[0], which can be a "skipped"/"skipped_no_floor"
            # entry. A skipped canary never actually ran a walk, so reporting it as a
            # $0 "success" would let the SFN gate auto-approve the whole fan-out on a
            # no-op. We surface canary_walked=false + a loud warning so the gate (and
            # the reviewer) refuse to approve.
            canary_entry, canary_status, canary_walked = resolve_canary_entry(job_summary, canary_recipe)
            if not canary_walked:
                LOG.warning(
                    "CANARY DID NOT WALK: %s status=%s — fan-out MUST NOT be "
                    "approved on this result; re-run the canary on a recipe that "
                    "will actually walk.",
                    canary_recipe,
                    canary_status,
                )
            s3_upload_json(
                {
                    "canary_recipe_id": canary_recipe,
                    "status": canary_status,
                    "canary_walked": canary_walked,
                    "walk_wall_clock_seconds": (canary_entry.get("walk_wall_clock_seconds") if canary_entry else None),
                    "cpu_utilization_pct_mean_walk": round(cpu_mean, 1),
                    "estimated_cost_usd": round(estimated_cost_usd, 4),
                    "message": _canary_message(canary_walked, canary_status),
                },
                S3_BUCKET,
                canary_result_key,
            )

    LOG.info(
        "recipe-fleet-entrypoint done | wall_clock=%.0f s | cpu_mean=%.1f%%",
        fleet_elapsed,
        cpu_mean,
    )


if __name__ == "__main__":
    main()
