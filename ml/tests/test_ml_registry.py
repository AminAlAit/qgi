"""Unit tests for src/ml_registry.py.

Exercises the LocalFilesystemBackend (S3Backend is integration-tested
manually with real STS creds; not covered here). Verifies path conventions,
ID validation, fingerprinting, run-id generation, metadata serialization,
and the public register_model / snapshot_training_data flows.

Stage 0 deliverable per docs/specs/internal/ops/ml-track/stage-0-pre-registration.md.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import sys

import pytest

SRC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import ml_registry as mr  # noqa: E402


# ---------- LocalFilesystemBackend ----------


def test_local_backend_write_then_read_round_trip(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    uri = backend.write_bytes("a/b/c.bin", b"hello")
    assert "file://" in uri
    assert backend.read_bytes("a/b/c.bin") == b"hello"


def test_local_backend_exists():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        backend = mr.LocalFilesystemBackend(td)
        assert backend.exists("nope.bin") is False
        backend.write_bytes("here.bin", b"x")
        assert backend.exists("here.bin") is True


def test_local_backend_list_keys_returns_relative_posix(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    backend.write_bytes("a/x.bin", b"1")
    backend.write_bytes("a/y.bin", b"2")
    backend.write_bytes("b/z.bin", b"3")
    a_keys = backend.list_keys("a")
    assert "a/x.bin" in a_keys
    assert "a/y.bin" in a_keys
    assert "b/z.bin" not in a_keys


def test_local_backend_list_keys_empty_on_missing_prefix(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    assert backend.list_keys("does/not/exist") == []


def test_local_backend_creates_parent_dirs(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    backend.write_bytes("very/deep/nested/path/x.bin", b"x")
    assert (tmp_path / "very" / "deep" / "nested" / "path" / "x.bin").is_file()


# ---------- Path builders ----------


def test_model_artifact_key_format():
    k = mr.model_artifact_key("civil_war_and_insurgency", "2026-05-04T120000Z")
    assert k == "ml-artifacts/v0/civil_war_and_insurgency/2026-05-04T120000Z/model.pkl"


def test_model_metadata_key_format():
    k = mr.model_metadata_key("civil_war_and_insurgency", "2026-05-04T120000Z")
    assert k.endswith("/metadata.json")


def test_training_data_snapshot_key_format():
    k = mr.training_data_snapshot_key("2026-05-04T120000Z", "WB-01")
    assert k == "ml-artifacts/training-data-snapshots/2026-05-04T120000Z/WB-01.parquet"


def test_ml_output_score_key_format():
    k = mr.ml_output_score_key("civil_war_and_insurgency", 2024)
    assert k == "ml-outputs/recipe-scores/civil_war_and_insurgency/2024/score.json"


def test_ml_output_score_key_rejects_implausible_year():
    with pytest.raises(ValueError):
        mr.ml_output_score_key("x", 1800)
    with pytest.raises(ValueError):
        mr.ml_output_score_key("x", 99999)


# ---------- _check_id ----------


@pytest.mark.parametrize("bad", [
    "../escape",
    "with space",
    "with/slash",
    "with\\backslash",
    "with\nnewline",
    "with\ttab",
    "",
    "C:windows_drive",  # Windows drive-letter colon must be blocked
    "C:\\absolute\\path",
    ":leading_colon",
    "trailing:",
])
def test_check_id_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        mr._check_id(bad, "x")


def test_check_id_accepts_normal_ids():
    mr._check_id("civil_war_and_insurgency", "x")
    mr._check_id("2026-05-04T120000Z", "x")
    mr._check_id("WB-01", "x")
    # No exception expected.


def test_path_builders_reject_traversal():
    with pytest.raises(ValueError):
        mr.model_artifact_key("../sneaky", "run")
    with pytest.raises(ValueError):
        mr.training_data_snapshot_key("run", "../../etc/passwd")


# ---------- generate_run_id ----------


def test_generate_run_id_format():
    fixed = _dt.datetime(2026, 5, 4, 12, 0, 0, tzinfo=_dt.timezone.utc)
    assert mr.generate_run_id(now=fixed) == "2026-05-04T120000Z"


def test_generate_run_id_with_suffix():
    fixed = _dt.datetime(2026, 5, 4, 12, 0, 0, tzinfo=_dt.timezone.utc)
    out = mr.generate_run_id(now=fixed, suffix="lightgbm_v0")
    assert out == "2026-05-04T120000Z_lightgbm_v0"


def test_generate_run_id_rejects_bad_suffix():
    fixed = _dt.datetime(2026, 5, 4, 12, 0, 0, tzinfo=_dt.timezone.utc)
    with pytest.raises(ValueError):
        mr.generate_run_id(now=fixed, suffix="bad suffix with spaces")


# ---------- Hashing + fingerprinting ----------


def test_sha256_of_file_matches_bytes(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world")
    assert mr.sha256_of_file(p) == hashlib.sha256(b"hello world").hexdigest()


def test_fingerprint_validation_script_returns_fields(tmp_path):
    s = tmp_path / "validator.py"
    s.write_bytes(b"# fake validator\n")  # write_bytes avoids Windows \r\n translation
    fp = mr.fingerprint_validation_script(s)
    assert fp.script_path == str(s)
    assert fp.file_sha256 == hashlib.sha256(b"# fake validator\n").hexdigest()
    # git_commit_sha + git_dirty depend on git env; just check shape
    assert fp.git_commit_sha is None or isinstance(fp.git_commit_sha, str)
    assert fp.git_dirty in (None, True, False)
    assert "T" in fp.fingerprinted_at_utc  # ISO 8601 with T separator


def test_fingerprint_validation_script_raises_on_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        mr.fingerprint_validation_script(tmp_path / "no_such_file.py")


# ---------- ModelMetadata ----------


def test_model_metadata_serializes_to_json(tmp_path):
    m = mr.ModelMetadata(
        recipe_id="civil_war_and_insurgency",
        run_id="2026-05-04T120000Z",
        model_class="LightGBM_v0_baseline",
        training_data_snapshot_run_id="2026-05-04T120000Z",
        training_data_hash="deadbeef",
        validation_script_fingerprint=None,
        hyperparameters={"num_leaves": 31, "learning_rate": 0.05},
        oos_by_time_auc={"point": 0.62, "ci": [0.55, 0.69]},
        ece_post_calibration=0.04,
        calibration_curve=None,
        created_at_utc="2026-05-04T12:00:00+00:00",
    )
    blob = m.to_json_bytes()
    parsed = json.loads(blob)
    assert parsed["recipe_id"] == "civil_war_and_insurgency"
    assert parsed["model_class"] == "LightGBM_v0_baseline"
    assert parsed["hyperparameters"]["num_leaves"] == 31


# ---------- register_model ----------


def test_register_model_writes_artifact_and_metadata(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    artifact = tmp_path / "model.pkl"
    artifact.write_bytes(b"\x80\x04...")  # dummy pickle bytes
    md = mr.ModelMetadata(
        recipe_id="r1", run_id="run1",
        model_class="LightGBM_v0_baseline",
        training_data_snapshot_run_id="run1",
        training_data_hash="h",
        validation_script_fingerprint=None,
        hyperparameters={},
        oos_by_time_auc=None,
        ece_post_calibration=None,
        calibration_curve=None,
        created_at_utc="2026-05-04T12:00:00+00:00",
    )
    out = mr.register_model("r1", "run1", artifact, md, backend)
    assert "model_uri" in out
    assert "metadata_uri" in out
    assert backend.exists("ml-artifacts/v0/r1/run1/model.pkl")
    assert backend.exists("ml-artifacts/v0/r1/run1/metadata.json")
    parsed = json.loads(backend.read_bytes("ml-artifacts/v0/r1/run1/metadata.json"))
    assert parsed["recipe_id"] == "r1"


def test_register_model_rejects_metadata_mismatch(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    artifact = tmp_path / "model.pkl"
    artifact.write_bytes(b"x")
    md = mr.ModelMetadata(
        recipe_id="r1", run_id="run1",
        model_class="x", training_data_snapshot_run_id="run1",
        training_data_hash="h", validation_script_fingerprint=None,
        hyperparameters={}, oos_by_time_auc=None, ece_post_calibration=None,
        calibration_curve=None, created_at_utc="2026-05-04T12:00:00+00:00",
    )
    with pytest.raises(ValueError):
        mr.register_model("r2", "run1", artifact, md, backend)
    with pytest.raises(ValueError):
        mr.register_model("r1", "DIFFERENT_run", artifact, md, backend)


def test_register_model_raises_if_artifact_missing(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    md = mr.ModelMetadata(
        recipe_id="r", run_id="run", model_class="x",
        training_data_snapshot_run_id="run", training_data_hash="h",
        validation_script_fingerprint=None, hyperparameters={},
        oos_by_time_auc=None, ece_post_calibration=None,
        calibration_curve=None, created_at_utc="2026-05-04T12:00:00+00:00",
    )
    with pytest.raises(FileNotFoundError):
        mr.register_model("r", "run", tmp_path / "no_such.pkl", md, backend)


# ---------- snapshot_training_data ----------


def test_snapshot_training_data_writes_all_indicators(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    p1 = tmp_path / "WB-01.parquet"
    p2 = tmp_path / "WB-02.parquet"
    p1.write_bytes(b"WB01_DATA")
    p2.write_bytes(b"WB02_DATA")
    out = mr.snapshot_training_data(
        run_id="run1",
        indicator_local_paths={"WB-01": p1, "WB-02": p2},
        backend=backend,
    )
    assert out["n_indicators"] == 2
    assert "WB-01" in out["snapshot_uris"]
    assert "WB-02" in out["snapshot_uris"]
    assert backend.exists("ml-artifacts/training-data-snapshots/run1/WB-01.parquet")
    assert backend.exists("ml-artifacts/training-data-snapshots/run1/WB-02.parquet")
    assert isinstance(out["snapshot_hash"], str) and len(out["snapshot_hash"]) == 64


def test_snapshot_training_data_hash_is_deterministic(tmp_path):
    """Same inputs (regardless of dict order) -> same snapshot_hash."""
    backend = mr.LocalFilesystemBackend(tmp_path)
    p1 = tmp_path / "a.parquet"
    p1.write_bytes(b"AAA")
    p2 = tmp_path / "b.parquet"
    p2.write_bytes(b"BBB")
    h1 = mr.snapshot_training_data("r", {"a": p1, "b": p2}, backend)["snapshot_hash"]
    # Re-run to a different prefix to avoid filesystem clobber
    backend2 = mr.LocalFilesystemBackend(tmp_path / "second")
    h2 = mr.snapshot_training_data("r", {"b": p2, "a": p1}, backend2)["snapshot_hash"]
    assert h1 == h2


def test_snapshot_training_data_hash_changes_when_content_changes(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    p = tmp_path / "x.parquet"
    p.write_bytes(b"v1")
    h1 = mr.snapshot_training_data("r1", {"x": p}, backend)["snapshot_hash"]
    p.write_bytes(b"v2")
    backend2 = mr.LocalFilesystemBackend(tmp_path / "second")
    h2 = mr.snapshot_training_data("r2", {"x": p}, backend2)["snapshot_hash"]
    assert h1 != h2


def test_snapshot_training_data_raises_on_empty():
    backend = mr.LocalFilesystemBackend(pathlib.Path("/tmp/nope"))  # never written
    with pytest.raises(ValueError):
        mr.snapshot_training_data("r", {}, backend)


def test_snapshot_training_data_raises_on_missing_indicator(tmp_path):
    backend = mr.LocalFilesystemBackend(tmp_path)
    with pytest.raises(FileNotFoundError):
        mr.snapshot_training_data("r", {"x": tmp_path / "missing.parquet"}, backend)


# ---------- S3Backend smoke tests (no real AWS calls) ----------


def test_s3_backend_lazy_imports_boto3(monkeypatch):
    """S3Backend imports boto3+botocore on init. Mock client construction so the
    test doesn't depend on AWS credentials in CI (NoCredentialsError + similar)."""
    try:
        import boto3  # noqa: F401
    except ImportError:
        pytest.skip("boto3 not installed in this env")
    import boto3 as _boto3
    monkeypatch.setattr(_boto3, "client", lambda *a, **kw: object())
    backend = mr.S3Backend(bucket="qgi-data-lake-test", region="eu-central-1")
    assert backend.bucket == "qgi-data-lake-test"
    assert backend.region == "eu-central-1"
    assert backend._client is not None


def test_s3_backend_uri_format(monkeypatch):
    try:
        import boto3 as _boto3
    except ImportError:
        pytest.skip("boto3 not installed in this env")
    monkeypatch.setattr(_boto3, "client", lambda *a, **kw: object())
    backend = mr.S3Backend(bucket="my-bucket")
    assert backend.uri("a/b.bin") == "s3://my-bucket/a/b.bin"
