"""
Unit tests for the V-Dem Batch entry orchestrator (#494 step 4).

The orchestrator's job is small and well-defined:
  1. Read env vars (validate required, default optional)
  2. Download the V-Dem CSV from S3 to /tmp
  3. Compose the right CLI args for `ingest_vdem.py`
  4. Surface the worker's exit code
  5. Clean up the /tmp CSV

These tests exercise the env-var → CLI-arg translation, the error
paths (missing env, S3 download failure, missing bundled artifacts),
and confirm the cleanup runs even on worker failure. The worker
script (`ingest_vdem.py`) is imported as a subprocess in production —
here we mock `subprocess.call` so the tests run fast and don't
require the bundled artifacts to be present.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "batch" / "qgi-vdem-ingest" / "src" / "run_ingest.py"
)


@pytest.fixture(scope="module")
def run_ingest():
    """Load src/run_ingest.py as a module without invoking run_pipeline()."""
    spec = importlib.util.spec_from_file_location("run_ingest_under_test", str(_SCRIPT_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def clean_env(monkeypatch):
    """Strip all env vars this orchestrator reads so each test starts
    from a known empty state."""
    for var in (
        "S3_BUCKET",
        "VDEM_CSV_S3_KEY",
        "AWS_REGION",
        "ATHENA_WORKGROUP",
        "DRY_RUN",
        "SKIP_REPAIR",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------- #
# env_required + env_bool                                                #
# ---------------------------------------------------------------------- #


def test_env_required_returns_value_when_set(run_ingest, monkeypatch):
    monkeypatch.setenv("FOO", "bar")
    assert run_ingest.env_required("FOO") == "bar"


def test_env_required_exits_on_missing(run_ingest, monkeypatch, capsys):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(SystemExit) as excinfo:
        run_ingest.env_required("MISSING_VAR")
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "missing required env var: MISSING_VAR" in err


def test_env_required_exits_on_blank(run_ingest, monkeypatch, capsys):
    """Empty string is not a valid value — treat as missing."""
    monkeypatch.setenv("BLANK", "")
    with pytest.raises(SystemExit) as excinfo:
        run_ingest.env_required("BLANK")
    assert excinfo.value.code == 1


@pytest.mark.parametrize(
    "val,expected",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("YES", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("", False),
        ("anything-else", False),
    ],
)
def test_env_bool_recognises_truthy(run_ingest, monkeypatch, val, expected):
    monkeypatch.setenv("BOOL_VAR", val)
    assert run_ingest.env_bool("BOOL_VAR") is expected


def test_env_bool_default_when_unset(run_ingest, monkeypatch):
    monkeypatch.delenv("UNSET_VAR", raising=False)
    assert run_ingest.env_bool("UNSET_VAR", default=True) is True
    assert run_ingest.env_bool("UNSET_VAR", default=False) is False


# ---------------------------------------------------------------------- #
# build_ingest_argv                                                      #
# ---------------------------------------------------------------------- #


def test_build_ingest_argv_default_flags(run_ingest, tmp_path):
    """Without --dry-run / --repair flags, argv should be the minimal
    invocation (path + bucket + workgroup + region + country-map)."""
    csv = tmp_path / "vdem.csv"
    csv.touch()
    argv = run_ingest.build_ingest_argv(
        csv_path=csv,
        bucket="qgi-data-lake-x",
        workgroup="QGI-Lambda-Workgroup",
        region="eu-central-1",
        dry_run=False,
        repair=False,
    )
    # Required flags
    assert "--vdem-csv-path" in argv
    assert str(csv) in argv
    assert "--bucket" in argv
    assert "qgi-data-lake-x" in argv
    assert "--workgroup" in argv
    assert "QGI-Lambda-Workgroup" in argv
    assert "--region" in argv
    assert "eu-central-1" in argv
    assert "--country-map" in argv
    # Optional flags absent
    assert "--dry-run" not in argv
    assert "--repair" not in argv


def test_build_ingest_argv_dry_run_flag(run_ingest, tmp_path):
    csv = tmp_path / "vdem.csv"
    argv = run_ingest.build_ingest_argv(
        csv,
        "b",
        "w",
        "r",
        dry_run=True,
        repair=False,
    )
    assert "--dry-run" in argv
    assert "--repair" not in argv


def test_build_ingest_argv_repair_flag(run_ingest, tmp_path):
    csv = tmp_path / "vdem.csv"
    argv = run_ingest.build_ingest_argv(
        csv,
        "b",
        "w",
        "r",
        dry_run=False,
        repair=True,
    )
    assert "--repair" in argv
    assert "--dry-run" not in argv


def test_build_ingest_argv_uses_bundled_worker_path(run_ingest, tmp_path):
    """The orchestrator must invoke the bundled worker at /app/ingest_vdem.py
    (not some other path). Catches a Dockerfile drift that moved the
    bundle location."""
    csv = tmp_path / "vdem.csv"
    argv = run_ingest.build_ingest_argv(
        csv,
        "b",
        "w",
        "r",
        dry_run=False,
        repair=False,
    )
    assert str(run_ingest.WORKER_SCRIPT) in argv
    assert run_ingest.WORKER_SCRIPT == Path("/app/ingest_vdem.py")


# ---------------------------------------------------------------------- #
# download_csv_to_tmp — boto3 mocked                                     #
# ---------------------------------------------------------------------- #


def test_download_csv_to_tmp_success(run_ingest, tmp_path):
    """Happy path: boto3 download_file succeeds → returns the tmp path."""
    fake_s3 = MagicMock()

    # Mock the side effect: write a small file at the destination
    def fake_download(bucket, key, local):
        Path(local).write_bytes(b"x" * 1024)

    fake_s3.download_file.side_effect = fake_download

    with patch("boto3.client", return_value=fake_s3):
        result = run_ingest.download_csv_to_tmp(
            "qgi-data-lake-x",
            "vdem-staging/V-Dem-CY-Full+Others-v15.csv",
            "eu-central-1",
        )
    assert result.name == "V-Dem-CY-Full+Others-v15.csv"
    assert result.exists()
    fake_s3.download_file.assert_called_once()


def test_download_csv_to_tmp_failure_exits_2(run_ingest, capsys):
    """boto3 raise → orchestrator exits with code 2 (S3 download failed)."""
    fake_s3 = MagicMock()
    fake_s3.download_file.side_effect = RuntimeError("AccessDenied")

    with patch("boto3.client", return_value=fake_s3):
        with pytest.raises(SystemExit) as excinfo:
            run_ingest.download_csv_to_tmp("b", "k", "r")
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "S3 download failed" in err


# ---------------------------------------------------------------------- #
# run_pipeline integration                                               #
# ---------------------------------------------------------------------- #


def _setup_full_env(monkeypatch, **overrides):
    defaults = {
        "S3_BUCKET": "qgi-data-lake-x",
        "VDEM_CSV_S3_KEY": "vdem-staging/v15.csv",
        "AWS_REGION": "eu-central-1",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        monkeypatch.setenv(k, v)


def test_run_pipeline_missing_required_env(run_ingest, clean_env, capsys):
    """No env vars set → exits 1 with clear message."""
    with pytest.raises(SystemExit) as excinfo:
        run_ingest.run_pipeline()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "S3_BUCKET" in err


def test_run_pipeline_missing_bundled_artifact_exits_1(run_ingest, clean_env, monkeypatch, tmp_path, capsys):
    """If the Dockerfile didn't COPY ingest_vdem.py / vdem_country_map.yaml
    into /app/, exit early with a clear error pointing at the staging
    step.

    PR #8 review item 6: explicitly point WORKER_SCRIPT at a path we
    know does not exist (instead of relying on `/app/...` happening
    not to exist on the dev host). Intent is now self-documenting and
    the test is robust against a hypothetical case where someone has
    `/app/ingest_vdem.py` on their local machine for unrelated reasons.
    """
    _setup_full_env(monkeypatch)
    nonexistent = tmp_path / "definitely-not-here" / "ingest_vdem.py"
    monkeypatch.setattr(run_ingest, "WORKER_SCRIPT", nonexistent)
    with pytest.raises(SystemExit) as excinfo:
        run_ingest.run_pipeline()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "bundled artifact missing" in err
    assert "Dockerfile" in err and "staging" in err


def test_run_pipeline_propagates_worker_exit_code(run_ingest, clean_env, monkeypatch, tmp_path):
    """When the worker script exits non-zero, the orchestrator surfaces
    that code. Step Functions maps non-zero to a Failed state and
    triggers SNS notification."""
    _setup_full_env(monkeypatch)
    fake_csv = tmp_path / "csv-from-s3.csv"
    fake_csv.write_bytes(b"x" * 100)

    # Stub the bundled artifacts so run_pipeline gets past the
    # bundled-artifact existence check
    def fake_exists(self):
        return True

    monkeypatch.setattr(Path, "exists", fake_exists)

    with patch.object(run_ingest, "download_csv_to_tmp", return_value=fake_csv):
        with patch("subprocess.call", return_value=42):
            rc = run_ingest.run_pipeline()
    assert rc == 42


def test_run_pipeline_returns_zero_on_success(run_ingest, clean_env, monkeypatch, tmp_path):
    """Worker exits 0 → orchestrator returns 0."""
    _setup_full_env(monkeypatch)
    fake_csv = tmp_path / "csv-from-s3.csv"
    fake_csv.write_bytes(b"x" * 100)

    def fake_exists(self):
        return True

    monkeypatch.setattr(Path, "exists", fake_exists)

    with patch.object(run_ingest, "download_csv_to_tmp", return_value=fake_csv):
        with patch("subprocess.call", return_value=0):
            rc = run_ingest.run_pipeline()
    assert rc == 0


def test_run_pipeline_dry_run_passes_flag(run_ingest, clean_env, monkeypatch, tmp_path):
    """DRY_RUN=true env → --dry-run passed to worker."""
    _setup_full_env(monkeypatch, DRY_RUN="true")
    fake_csv = tmp_path / "csv-from-s3.csv"
    fake_csv.write_bytes(b"x" * 100)

    def fake_exists(self):
        return True

    monkeypatch.setattr(Path, "exists", fake_exists)

    captured_argv: list[list[str]] = []

    def capture_call(argv, *args, **kwargs):
        captured_argv.append(argv)
        return 0

    with patch.object(run_ingest, "download_csv_to_tmp", return_value=fake_csv):
        with patch("subprocess.call", side_effect=capture_call):
            run_ingest.run_pipeline()

    assert len(captured_argv) == 1
    assert "--dry-run" in captured_argv[0]


def test_run_pipeline_skip_repair_omits_flag(run_ingest, clean_env, monkeypatch, tmp_path):
    """SKIP_REPAIR=true env → --repair NOT passed (default is to pass it)."""
    _setup_full_env(monkeypatch, SKIP_REPAIR="true")
    fake_csv = tmp_path / "csv-from-s3.csv"
    fake_csv.write_bytes(b"x" * 100)

    def fake_exists(self):
        return True

    monkeypatch.setattr(Path, "exists", fake_exists)

    captured_argv: list[list[str]] = []

    def capture_call(argv, *args, **kwargs):
        captured_argv.append(argv)
        return 0

    with patch.object(run_ingest, "download_csv_to_tmp", return_value=fake_csv):
        with patch("subprocess.call", side_effect=capture_call):
            run_ingest.run_pipeline()

    assert "--repair" not in captured_argv[0]


def test_run_pipeline_default_passes_repair(run_ingest, clean_env, monkeypatch, tmp_path):
    """Default behavior (no SKIP_REPAIR) is --repair on."""
    _setup_full_env(monkeypatch)
    fake_csv = tmp_path / "csv-from-s3.csv"
    fake_csv.write_bytes(b"x" * 100)

    def fake_exists(self):
        return True

    monkeypatch.setattr(Path, "exists", fake_exists)

    captured_argv: list[list[str]] = []

    def capture_call(argv, *args, **kwargs):
        captured_argv.append(argv)
        return 0

    with patch.object(run_ingest, "download_csv_to_tmp", return_value=fake_csv):
        with patch("subprocess.call", side_effect=capture_call):
            run_ingest.run_pipeline()

    assert "--repair" in captured_argv[0]


def test_run_pipeline_custom_workgroup(run_ingest, clean_env, monkeypatch, tmp_path):
    """ATHENA_WORKGROUP env override is honored."""
    _setup_full_env(monkeypatch, ATHENA_WORKGROUP="custom-wg")
    fake_csv = tmp_path / "csv-from-s3.csv"
    fake_csv.write_bytes(b"x" * 100)

    def fake_exists(self):
        return True

    monkeypatch.setattr(Path, "exists", fake_exists)

    captured_argv: list[list[str]] = []

    def capture_call(argv, *args, **kwargs):
        captured_argv.append(argv)
        return 0

    with patch.object(run_ingest, "download_csv_to_tmp", return_value=fake_csv):
        with patch("subprocess.call", side_effect=capture_call):
            run_ingest.run_pipeline()

    assert "custom-wg" in captured_argv[0]


def test_run_pipeline_cleans_up_csv_on_worker_failure(run_ingest, clean_env, monkeypatch, tmp_path):
    """Worker exits non-zero → orchestrator still deletes the /tmp CSV."""
    _setup_full_env(monkeypatch)
    fake_csv = tmp_path / "csv-from-s3.csv"
    fake_csv.write_bytes(b"x" * 100)
    assert fake_csv.exists()

    def fake_exists(self):
        # Pretend bundled artifacts exist; let the test CSV check itself
        if str(self) in (
            str(run_ingest.WORKER_SCRIPT),
            str(run_ingest.COUNTRY_MAP_PATH),
        ):
            return True
        return Path.exists.__wrapped__(self) if hasattr(Path.exists, "__wrapped__") else os.path.exists(str(self))

    # Simpler: just patch the bundled-artifact paths to "exist"
    monkeypatch.setattr(run_ingest, "WORKER_SCRIPT", fake_csv)  # any extant file
    monkeypatch.setattr(run_ingest, "COUNTRY_MAP_PATH", fake_csv)

    with patch.object(run_ingest, "download_csv_to_tmp", return_value=fake_csv):
        with patch("subprocess.call", return_value=99):
            rc = run_ingest.run_pipeline()

    assert rc == 99
    # After run_pipeline, the CSV should have been unlinked
    assert not fake_csv.exists(), "csv cleanup did not run on worker failure"
