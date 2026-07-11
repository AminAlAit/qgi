"""Tests for scripts/sync_audit_v2.py — closes #621.

Covers:
- Idempotent skip when remote ETag matches local MD5
- Upload happens when remote is absent (NoSuchKey / 404)
- Upload happens when remote ETag differs from local MD5
- --dry-run prevents any put_object call (when remote differs)
- --dry-run prevents any put_object call (when remote absent)
- Refuses to sync if local file missing
- Refuses to sync if local JSON is malformed
- Refuses to sync if local JSON has zero results entries
- Refuses to sync if schema_version != EXPECTED_SCHEMA_VERSION
- Non-404 ClientError on head_object re-raises
- ContentType is set to application/json on upload
- Single-read invariant: file read into memory once, same bytes used for
  hash and upload body
"""
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import sync_audit_v2 as sut  # noqa: E402


VALID_AUDIT = {
    "schema_version": 1,  # matches EXPECTED_SCHEMA_VERSION; see script docstring
    "results": {
        "v2x_libdem": {"classification": "I(1)"},
        "RL.EST": {"classification": "I(0)"},
    },
}


def _write_audit(tmp_path: Path, payload=VALID_AUDIT) -> Path:
    p = tmp_path / "indicator-stationarity-audit-v2.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _md5(p: Path) -> str:
    h = hashlib.md5()
    h.update(p.read_bytes())
    return h.hexdigest()


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "HeadObject")


# ─── core idempotency ────────────────────────────────────────────────────────

def test_skip_when_remote_md5_matches(tmp_path, monkeypatch, capsys):
    audit = _write_audit(tmp_path)
    monkeypatch.setattr(sut, "LOCAL_PATH", audit)

    s3 = MagicMock()
    s3.head_object.return_value = {"ETag": f'"{_md5(audit)}"'}
    monkeypatch.setattr(sut.boto3, "client", lambda *_: s3)

    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    rc = sut.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "skipping upload" in out
    s3.put_object.assert_not_called()


def test_upload_when_remote_absent(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path)
    monkeypatch.setattr(sut, "LOCAL_PATH", audit)

    s3 = MagicMock()
    s3.head_object.side_effect = _client_error("404")
    monkeypatch.setattr(sut.boto3, "client", lambda *_: s3)

    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    rc = sut.main()
    assert rc == 0
    s3.put_object.assert_called_once()
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "test"
    assert kwargs["Key"] == "reference/indicator-stationarity-audit-v2.json"
    assert kwargs["ContentType"] == "application/json"


def test_upload_when_remote_md5_differs(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path)
    monkeypatch.setattr(sut, "LOCAL_PATH", audit)

    s3 = MagicMock()
    s3.head_object.return_value = {"ETag": '"differenthash00000000000000000000"'}
    monkeypatch.setattr(sut.boto3, "client", lambda *_: s3)

    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    rc = sut.main()
    assert rc == 0
    s3.put_object.assert_called_once()


def test_dry_run_skips_upload_even_when_remote_differs(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path)
    monkeypatch.setattr(sut, "LOCAL_PATH", audit)

    s3 = MagicMock()
    s3.head_object.return_value = {"ETag": '"differenthash00000000000000000000"'}
    monkeypatch.setattr(sut.boto3, "client", lambda *_: s3)

    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test", "--dry-run"])
    rc = sut.main()
    assert rc == 0
    s3.put_object.assert_not_called()


# ─── precondition checks ─────────────────────────────────────────────────────

def test_refuses_when_local_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sut, "LOCAL_PATH", tmp_path / "does-not-exist.json")
    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    rc = sut.main()
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_refuses_when_local_invalid_json(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "indicator-stationarity-audit-v2.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(sut, "LOCAL_PATH", bad)
    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    rc = sut.main()
    assert rc == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_refuses_when_local_has_zero_results(tmp_path, monkeypatch, capsys):
    empty = _write_audit(tmp_path, payload={"schema_version": 1, "results": {}})
    monkeypatch.setattr(sut, "LOCAL_PATH", empty)
    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    rc = sut.main()
    assert rc == 1
    assert "zero results" in capsys.readouterr().err


def test_refuses_when_schema_version_unexpected(tmp_path, monkeypatch, capsys):
    # Reviewer F1: hard fail if the JSON schema is bumped without updating the
    # script + dscdi-finder consumer in lockstep.
    wrong = _write_audit(tmp_path, payload={"schema_version": 99, "results": {"x": {"classification": "I(0)"}}})
    monkeypatch.setattr(sut, "LOCAL_PATH", wrong)
    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    rc = sut.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "schema_version" in err
    assert "99" in err


def test_refuses_when_schema_version_missing(tmp_path, monkeypatch, capsys):
    no_schema = _write_audit(tmp_path, payload={"results": {"x": {"classification": "I(0)"}}})
    monkeypatch.setattr(sut, "LOCAL_PATH", no_schema)
    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    rc = sut.main()
    assert rc == 1
    assert "schema_version" in capsys.readouterr().err


def test_dry_run_skips_upload_when_remote_absent(tmp_path, monkeypatch, capsys):
    audit = _write_audit(tmp_path)
    monkeypatch.setattr(sut, "LOCAL_PATH", audit)

    s3 = MagicMock()
    s3.head_object.side_effect = _client_error("404")
    monkeypatch.setattr(sut.boto3, "client", lambda *_: s3)

    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test", "--dry-run"])
    rc = sut.main()
    assert rc == 0
    s3.put_object.assert_not_called()
    assert "would PUT" in capsys.readouterr().out


# ─── error handling ──────────────────────────────────────────────────────────

def test_non_404_client_error_reraises(tmp_path, monkeypatch):
    audit = _write_audit(tmp_path)
    monkeypatch.setattr(sut, "LOCAL_PATH", audit)

    s3 = MagicMock()
    s3.head_object.side_effect = _client_error("AccessDenied")
    monkeypatch.setattr(sut.boto3, "client", lambda *_: s3)

    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    with pytest.raises(ClientError):
        sut.main()


def test_uploaded_body_matches_local_md5(tmp_path, monkeypatch):
    """Reviewer F3: verify the bytes uploaded match the bytes that were
    hashed (single-read invariant — no TOCTOU gap)."""
    audit = _write_audit(tmp_path)
    monkeypatch.setattr(sut, "LOCAL_PATH", audit)

    expected_bytes = audit.read_bytes()
    expected_md5 = hashlib.md5(expected_bytes).hexdigest()

    s3 = MagicMock()
    s3.head_object.side_effect = _client_error("404")  # force upload path
    monkeypatch.setattr(sut.boto3, "client", lambda *_: s3)

    monkeypatch.setattr(sys, "argv", ["sync_audit_v2.py", "--bucket", "test"])
    rc = sut.main()
    assert rc == 0

    s3.put_object.assert_called_once()
    uploaded_body = s3.put_object.call_args.kwargs["Body"]
    assert uploaded_body == expected_bytes
    assert hashlib.md5(uploaded_body).hexdigest() == expected_md5
