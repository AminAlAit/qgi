"""Model registry + reproducibility infrastructure for ML-Opus.

Stage 0 deliverable per docs/specs/internal/ops/ml-track/stage-0-pre-registration.md.

Implements three of Ji-Hoon's four binding reproducibility components:
    1. Model registry          -- register_model()
    2. Training-data versioning -- snapshot_training_data()
    3. Validation-script fingerprinting -- fingerprint_validation_script()
The fourth (pre-registration log) is the pre-registration markdown document.

S3 path conventions (per 06-modular-architecture.md + 07-validation-framework.md):

    ml-artifacts/v0/<recipe-id>/<run-id>/model.pkl
    ml-artifacts/v0/<recipe-id>/<run-id>/metadata.json
    ml-artifacts/training-data-snapshots/<run-id>/<indicator-id>.parquet
    ml-outputs/recipe-scores/<recipe-id>/<year>/score.json

Backends:
    LocalFilesystemBackend(root: Path)              for tests + dev
    S3Backend(bucket: str, region: str)             for production runs

Both implement a small StorageBackend protocol (write_bytes / read_bytes /
exists / list_keys / uri). Production callers pass an S3Backend; tests pass a
LocalFilesystemBackend(tmp_path).

boto3 is lazy-imported inside S3Backend so this module is importable in
test environments without boto3 installed.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol


# Conventions
DEFAULT_BUCKET = "qgi-data-lake-771606957899"  # staging account; per README.md
DEFAULT_REGION = "eu-central-1"

ML_ARTIFACTS_PREFIX = "ml-artifacts/v0"
TRAINING_DATA_PREFIX = "ml-artifacts/training-data-snapshots"
ML_OUTPUTS_PREFIX = "ml-outputs/recipe-scores"

METADATA_FILENAME = "metadata.json"
MODEL_FILENAME = "model.pkl"


# ---------- Storage backends ----------


class StorageBackend(Protocol):
    """Minimal interface used by the registry. Swap S3 for filesystem in tests."""

    def write_bytes(self, key: str, content: bytes) -> str: ...
    def read_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def list_keys(self, prefix: str) -> list[str]: ...
    def uri(self, key: str) -> str: ...


class LocalFilesystemBackend:
    """Writes objects to a local directory tree. Used for tests and dev runs."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Treat key as a relative POSIX-style path (matches S3 key semantics).
        return self.root / key

    def write_bytes(self, key: str, content: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return self.uri(key)

    def read_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list_keys(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        out: list[str] = []
        for p in base.rglob("*"):
            if p.is_file():
                out.append(str(p.relative_to(self.root)).replace("\\", "/"))
        return sorted(out)

    def uri(self, key: str) -> str:
        return f"file://{self._path(key).as_posix()}"


class S3Backend:
    """Writes objects to an S3 bucket. boto3 is lazy-imported on init."""

    def __init__(self, bucket: str = DEFAULT_BUCKET, region: str = DEFAULT_REGION) -> None:
        try:
            import boto3
            import botocore.exceptions
        except ImportError as err:  # pragma: no cover - exercised manually
            raise RuntimeError(
                "boto3 + botocore are required for S3Backend; install with `pip install boto3`."
            ) from err
        self.bucket = bucket
        self.region = region
        self._client = boto3.client("s3", region_name=region)
        # Capture the canonical ClientError class so .exists() can catch it without
        # depending on `client.exceptions.ClientError` (which is unreliable across
        # boto3 versions).
        self._client_error_cls = botocore.exceptions.ClientError

    def write_bytes(self, key: str, content: bytes) -> str:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=content)
        return self.uri(key)

    def read_bytes(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self._client_error_cls as err:
            code = err.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise  # 403 / 500 / other -- bubble up

    def list_keys(self, prefix: str) -> list[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        out: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                out.append(obj["Key"])
        return out

    def uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"


# ---------- Path builders ----------


def model_artifact_key(recipe_id: str, run_id: str, filename: str = MODEL_FILENAME) -> str:
    """Return the S3 key for a model artifact under <recipe>/<run>/."""
    _check_id(recipe_id, "recipe_id")
    _check_id(run_id, "run_id")
    return f"{ML_ARTIFACTS_PREFIX}/{recipe_id}/{run_id}/{filename}"


def model_metadata_key(recipe_id: str, run_id: str) -> str:
    return model_artifact_key(recipe_id, run_id, filename=METADATA_FILENAME)


def training_data_snapshot_key(run_id: str, indicator_id: str) -> str:
    """Return the S3 key for a snapshot of one indicator panel for one run."""
    _check_id(run_id, "run_id")
    _check_id(indicator_id, "indicator_id")
    return f"{TRAINING_DATA_PREFIX}/{run_id}/{indicator_id}.parquet"


def ml_output_score_key(recipe_id: str, year: int) -> str:
    """Return the S3 key for a per-(recipe, year) score JSON for frontend consumption."""
    _check_id(recipe_id, "recipe_id")
    if not isinstance(year, int) or year < 1900 or year > 2200:
        raise ValueError(f"year out of plausible range: {year!r}")
    return f"{ML_OUTPUTS_PREFIX}/{recipe_id}/{year}/score.json"


def _check_id(value: str, label: str) -> None:
    """Reject path-traversal attempts and obviously-bad IDs.

    Forbidden tokens cover: directory traversal (..), POSIX/Windows path
    separators (/ \\), whitespace (space, newline, tab), and the Windows drive-
    letter colon (:) which would otherwise let "C:secret" through unchallenged
    on Windows hosts.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty str; got {value!r}")
    bad = ("..", "/", "\\", ":", " ", "\n", "\t")
    for tok in bad:
        if tok in value:
            raise ValueError(f"{label} contains forbidden token {tok!r}: {value!r}")


# ---------- Run ID generation ----------


def generate_run_id(now: _dt.datetime | None = None, suffix: str | None = None) -> str:
    """Return a deterministic-shape run_id like '2026-05-04T120000Z' or with suffix.

    Caller passes `now` for tests (otherwise wall-clock is used). `suffix` may
    name the experiment or model class to disambiguate same-second runs.
    """
    ts = (now or _dt.datetime.now(tz=_dt.timezone.utc)).strftime("%Y-%m-%dT%H%M%SZ")
    if suffix:
        _check_id(suffix, "suffix")
        return f"{ts}_{suffix}"
    return ts


# ---------- Fingerprinting + hashing ----------


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_of_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _git_commit_sha(repo_dir: Path) -> str | None:
    """Return short HEAD SHA for the repo at repo_dir, or None if not a git tree."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return None
        return out.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _git_dirty(repo_dir: Path) -> bool | None:
    """Return True if the repo has uncommitted changes; None if not a git tree."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return None
        return bool(out.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


@dataclass
class ScriptFingerprint:
    script_path: str
    file_sha256: str
    git_commit_sha: str | None
    git_dirty: bool | None
    fingerprinted_at_utc: str


def fingerprint_validation_script(script_path: Path) -> ScriptFingerprint:
    """Return the fingerprint info to embed in model metadata.

    Captures both the file content hash and the git commit SHA so a future
    audit can reproduce the exact validation logic that produced the metrics.
    git_dirty=True is a warning sign -- means the script has uncommitted edits
    relative to the recorded SHA.
    """
    script_path = Path(script_path)
    if not script_path.is_file():
        raise FileNotFoundError(f"validation script not found: {script_path}")
    return ScriptFingerprint(
        script_path=str(script_path),
        file_sha256=sha256_of_file(script_path),
        git_commit_sha=_git_commit_sha(script_path.parent),
        git_dirty=_git_dirty(script_path.parent),
        fingerprinted_at_utc=_dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
    )


# ---------- Metadata schema ----------


@dataclass
class ModelMetadata:
    """Minimum metadata required for an audit-defensible model artifact.

    Per Ji-Hoon: a model whose training-data snapshot can't be reproduced fails
    Lloyd's actuarial review on the spot. This struct is the audit trail.
    """
    recipe_id: str
    run_id: str
    model_class: str  # e.g., "LightGBM_v0_baseline" / "DeepHit_lite" / "asymmetric_GBM"
    training_data_snapshot_run_id: str  # cross-link to snapshot dir
    training_data_hash: str             # sha256 of concatenated input parquets
    validation_script_fingerprint: dict | None  # output of fingerprint_validation_script
    hyperparameters: dict
    oos_by_time_auc: dict | None       # {point: float, ci: [low, high]}
    ece_post_calibration: float | None
    calibration_curve: list[dict] | None  # [{decile, predicted_mean, observed_rate, count}]
    created_at_utc: str
    creator: str = "ml-opus"
    notes: list[str] = field(default_factory=list)

    def to_json_bytes(self) -> bytes:
        # sort_keys=True ensures byte-identical serialization regardless of how
        # the caller constructed nested dicts (e.g., hyperparameters insertion
        # order). Reproducibility-critical per Ji-Hoon.
        return (json.dumps(asdict(self), indent=2, sort_keys=True) + "\n").encode("utf-8")


# ---------- Public registry operations ----------


def register_model(
    recipe_id: str,
    run_id: str,
    model_artifact_local_path: Path,
    metadata: ModelMetadata,
    backend: StorageBackend,
) -> dict[str, str]:
    """Write a model artifact + its metadata to the registry.

    Returns dict with `model_uri`, `metadata_uri`, and `run_id`. Idempotent
    insofar as overwriting at the same key is permitted (caller controls
    run_id uniqueness via generate_run_id() suffix).
    """
    _check_id(recipe_id, "recipe_id")
    _check_id(run_id, "run_id")
    if metadata.recipe_id != recipe_id or metadata.run_id != run_id:
        raise ValueError(
            "metadata.recipe_id / metadata.run_id must match the registration call args"
        )
    # NOTE: metadata.training_data_snapshot_run_id is intentionally NOT cross-
    # checked against run_id -- a model can legitimately reference an earlier
    # snapshot's run_id (e.g., when re-training on the same training data with
    # a different model class). Caller is responsible for passing the right
    # snapshot reference.
    model_artifact_local_path = Path(model_artifact_local_path)
    if not model_artifact_local_path.is_file():
        raise FileNotFoundError(f"model artifact not found: {model_artifact_local_path}")
    artifact_key = model_artifact_key(recipe_id, run_id)
    metadata_key = model_metadata_key(recipe_id, run_id)
    model_uri = backend.write_bytes(artifact_key, model_artifact_local_path.read_bytes())
    metadata_uri = backend.write_bytes(metadata_key, metadata.to_json_bytes())
    return {
        "model_uri": model_uri,
        "metadata_uri": metadata_uri,
        "run_id": run_id,
        "recipe_id": recipe_id,
    }


def snapshot_training_data(
    run_id: str,
    indicator_local_paths: dict[str, Path],
    backend: StorageBackend,
) -> dict[str, Any]:
    """Snapshot indicator parquets to the training-data-snapshots/<run_id>/ prefix.

    indicator_local_paths is a dict of indicator_id -> local Path. Returns:
        {
            run_id, n_indicators,
            snapshot_uris: {indicator_id: uri},
            snapshot_hash: sha256 of sorted (indicator_id, file_sha256) pairs,
        }

    The snapshot_hash is the commit-id-equivalent for the training-data state;
    bake it into ModelMetadata.training_data_hash.
    """
    _check_id(run_id, "run_id")
    if not indicator_local_paths:
        raise ValueError("indicator_local_paths must contain at least one entry")
    snapshot_uris: dict[str, str] = {}
    pair_lines: list[str] = []
    for indicator_id, local_path in sorted(indicator_local_paths.items()):
        local_path = Path(local_path)
        if not local_path.is_file():
            raise FileNotFoundError(f"indicator parquet not found: {local_path}")
        key = training_data_snapshot_key(run_id, indicator_id)
        content = local_path.read_bytes()
        uri = backend.write_bytes(key, content)
        snapshot_uris[indicator_id] = uri
        pair_lines.append(f"{indicator_id}|{sha256_of_bytes(content)}")
    snapshot_hash = sha256_of_bytes("\n".join(pair_lines).encode("utf-8"))
    return {
        "run_id": run_id,
        "n_indicators": len(indicator_local_paths),
        "snapshot_uris": snapshot_uris,
        "snapshot_hash": snapshot_hash,
    }
