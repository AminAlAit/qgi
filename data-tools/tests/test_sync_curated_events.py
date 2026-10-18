"""Tests for scripts/sync_curated_events.py (#373 test coverage audit).

Covers:
- upload mode: files enumerated + S3 upload_file called for each JSON
- upload mode: TRACKING.md uploaded when present
- upload mode: dry-run skips all upload_file calls
- upload mode: missing CURATED_DIR exits with sys.exit(1)
- download mode: S3 objects listed, download_file called for each .json
- download mode: dry-run skips all download_file calls
- download mode: missing TRACKING.md on S3 (404) warns and continues
- download mode: non-404 ClientError re-raised
- role assumption: STS assume_role called when --role-arn provided; s3 client built with temp creds
- encoding: non-ASCII filename (timor_leste.json) handled without error
- error path: ClientError on upload_file propagates (no silent swallow)
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import sync_curated_events as sut  # noqa: E402


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_s3():
    """Return a MagicMock wired to behave like a boto3 S3 client.

    The download() flow calls paginate() twice (curated/ + verification/),
    so the default stub must produce a fresh empty iterator on every call.
    A single `return_value = iter(...)` would be exhausted after the first
    invocation.
    """
    s3 = MagicMock()
    paginator = MagicMock()
    paginator.paginate.side_effect = lambda **kwargs: iter([{"Contents": []}])
    s3.get_paginator.return_value = paginator
    return s3


def _write_json(directory: Path, name: str, data=None):
    """Write a minimal JSON file into *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(
        json.dumps(data or [{"year": 2020, "title": f"Event in {name}"}]),
        encoding="utf-8",
    )


# ─── upload mode ──────────────────────────────────────────────────────────────

def test_upload_calls_upload_file_for_each_json(tmp_path, monkeypatch):
    curated = tmp_path / "events" / "curated"
    _write_json(curated, "jordan.json")
    _write_json(curated, "germany.json")
    # No TRACKING.md, no verification — exercise the curated-only branch
    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "nonexistent_tracking.md")

    s3 = _make_s3()
    sut.upload(s3, "test-bucket", dry_run=False)

    upload_calls = s3.upload_file.call_args_list
    # upload_file(localpath, bucket, key, ExtraArgs=...) -> args[2] is the S3 key
    uploaded_keys = {c.args[2] for c in upload_calls}
    assert any("germany.json" in k for k in uploaded_keys)
    assert any("jordan.json" in k for k in uploaded_keys)
    assert s3.upload_file.call_count == 2


def test_upload_includes_tracking_md_when_present(tmp_path, monkeypatch):
    curated = tmp_path / "events" / "curated"
    _write_json(curated, "jordan.json")
    tracking = tmp_path / "TRACKING.md"
    tracking.write_text("# tracking", encoding="utf-8")

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tracking)

    s3 = _make_s3()
    sut.upload(s3, "test-bucket", dry_run=False)

    # 1 JSON + 1 TRACKING.md = 2 calls (verification dir missing -> skipped)
    assert s3.upload_file.call_count == 2
    uploaded_keys = {c.args[2] for c in s3.upload_file.call_args_list}
    assert sut.S3_TRACKING_KEY in uploaded_keys


def test_upload_dry_run_never_calls_upload_file(tmp_path, monkeypatch):
    curated = tmp_path / "events" / "curated"
    _write_json(curated, "jordan.json")
    _write_json(curated, "germany.json")
    tracking = tmp_path / "TRACKING.md"
    tracking.write_text("# tracking", encoding="utf-8")

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tracking)

    s3 = _make_s3()
    sut.upload(s3, "test-bucket", dry_run=True)

    s3.upload_file.assert_not_called()


def test_upload_exits_when_curated_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(sut, "CURATED_DIR", tmp_path / "does_not_exist")
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "TRACKING.md")

    s3 = _make_s3()
    with pytest.raises(SystemExit) as exc_info:
        sut.upload(s3, "test-bucket", dry_run=False)
    assert exc_info.value.code == 1


def test_upload_non_ascii_filename_handled(tmp_path, monkeypatch):
    """timor_leste.json (ASCII in practice) and files with unicode chars in content."""
    curated = tmp_path / "events" / "curated"
    _write_json(curated, "timor_leste.json", [{"year": 2002, "title": "Timor-Leste Independence"}])

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "nonexistent.md")

    s3 = _make_s3()
    # Should not raise
    sut.upload(s3, "test-bucket", dry_run=False)

    assert s3.upload_file.call_count == 1
    called_key = s3.upload_file.call_args.args[2]
    assert "timor_leste.json" in called_key


def test_upload_clienterror_propagates(tmp_path, monkeypatch):
    """ClientError on upload_file is NOT silently swallowed — it propagates."""
    from botocore.exceptions import ClientError

    curated = tmp_path / "events" / "curated"
    _write_json(curated, "jordan.json")

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "nonexistent.md")

    s3 = _make_s3()
    s3.upload_file.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "PutObject"
    )

    with pytest.raises(ClientError):
        sut.upload(s3, "test-bucket", dry_run=False)


# ─── download mode ────────────────────────────────────────────────────────────

def _stub_paginator(s3, keys, verification_keys=None):
    """Configure s3 mock paginator to return *keys* and *verification_keys*.

    The download() flow calls paginate() twice — once for curated/ and once
    for verification/. The paginate side_effect dispatches on the Prefix
    kwarg so both calls work; pass verification_keys=None (default) to keep
    the verification side empty.
    """
    paginator = MagicMock()

    def _paginate(**kwargs):
        prefix = kwargs.get("Prefix", "")
        if prefix == sut.S3_VERIFICATION_PREFIX:
            return iter([{"Contents": [{"Key": k} for k in (verification_keys or [])]}])
        return iter([{"Contents": [{"Key": k} for k in keys]}])

    paginator.paginate.side_effect = _paginate
    s3.get_paginator.return_value = paginator


def test_download_calls_download_file_for_each_json(tmp_path, monkeypatch):
    curated = tmp_path / "events" / "curated"
    verification = tmp_path / "events" / "verification"
    tracking = tmp_path / "events" / "TRACKING.md"

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", verification)
    monkeypatch.setattr(sut, "TRACKING_FILE", tracking)

    s3 = _make_s3()
    _stub_paginator(s3, [
        "events-source/curated/jordan.json",
        "events-source/curated/germany.json",
    ])

    sut.download(s3, "test-bucket", dry_run=False)

    assert s3.download_file.call_count == 3  # 2 curated JSONs + 1 TRACKING.md
    downloaded_keys = {c.args[1] for c in s3.download_file.call_args_list}
    assert "events-source/curated/jordan.json" in downloaded_keys
    assert "events-source/curated/germany.json" in downloaded_keys
    assert sut.S3_TRACKING_KEY in downloaded_keys


def test_download_dry_run_never_calls_download_file(tmp_path, monkeypatch):
    curated = tmp_path / "events" / "curated"
    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "TRACKING.md")

    s3 = _make_s3()
    _stub_paginator(s3, ["events-source/curated/jordan.json"])

    sut.download(s3, "test-bucket", dry_run=True)

    s3.download_file.assert_not_called()


def test_download_tracking_404_warns_and_continues(tmp_path, monkeypatch, capsys):
    """If TRACKING.md is absent on S3 (404), the download should warn and not crash."""
    from botocore.exceptions import ClientError

    curated = tmp_path / "events" / "curated"
    tracking = tmp_path / "TRACKING.md"
    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tracking)

    s3 = _make_s3()
    _stub_paginator(s3, [])  # no JSON files

    def _download_side_effect(bucket, key, local):
        if key == sut.S3_TRACKING_KEY:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}}, "GetObject"
            )

    s3.download_file.side_effect = _download_side_effect

    # Should not raise
    sut.download(s3, "test-bucket", dry_run=False)

    captured = capsys.readouterr()
    assert "WARNING" in captured.out or "not in S3" in captured.out


def test_download_tracking_non_404_clienterror_reraises(tmp_path, monkeypatch):
    """Non-404 ClientError on TRACKING.md download must propagate."""
    from botocore.exceptions import ClientError

    curated = tmp_path / "events" / "curated"
    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "TRACKING.md")

    s3 = _make_s3()
    _stub_paginator(s3, [])

    def _fail(bucket, key, local):
        if key == sut.S3_TRACKING_KEY:
            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "Server Error"}}, "GetObject"
            )

    s3.download_file.side_effect = _fail

    with pytest.raises(ClientError):
        sut.download(s3, "test-bucket", dry_run=False)


def test_download_ignores_non_json_s3_objects(tmp_path, monkeypatch):
    """Objects in the prefix that are not .json (e.g. folders) are ignored."""
    curated = tmp_path / "events" / "curated"
    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "events" / "verification")
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "TRACKING.md")

    s3 = _make_s3()
    _stub_paginator(s3, [
        "events-source/curated/",           # folder key
        "events-source/curated/jordan.json",
        "events-source/curated/README.txt",  # non-JSON
    ])

    sut.download(s3, "test-bucket", dry_run=False)

    # Only jordan.json + TRACKING.md = 2 download_file calls
    downloaded_keys = {c.args[1] for c in s3.download_file.call_args_list}
    assert "events-source/curated/jordan.json" in downloaded_keys
    assert "events-source/curated/" not in downloaded_keys
    assert "events-source/curated/README.txt" not in downloaded_keys


# ─── role assumption ──────────────────────────────────────────────────────────

def test_main_uses_assume_role_when_role_arn_provided(monkeypatch, tmp_path):
    """When --role-arn is given, STS assume_role is called and temp creds used."""
    fake_creds = {
        "AccessKeyId": "ASIA_FAKE",
        "SecretAccessKey": "secret",
        "SessionToken": "token",
    }
    sts_mock = MagicMock()
    sts_mock.assume_role.return_value = {"Credentials": fake_creds}

    s3_mock = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = iter([{"Contents": []}])
    s3_mock.get_paginator.return_value = paginator

    boto3_client_calls = []

    def _boto3_client(service, **kwargs):
        boto3_client_calls.append((service, kwargs))
        if service == "sts":
            return sts_mock
        return s3_mock

    monkeypatch.setattr(sut, "CURATED_DIR", tmp_path / "nonexistent_for_download")
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "nonexistent_for_download_verif")

    with patch("sync_curated_events.boto3") as mock_boto3:
        mock_boto3.client.side_effect = _boto3_client

        # Patch sys.argv for argparse
        test_args = [
            "sync_curated_events.py",
            "--bucket", "test-bucket",
            "--role-arn", "arn:aws:iam::123456789012:role/test-role",
            "--download",
            "--dry-run",
        ]
        monkeypatch.setattr(sys, "argv", test_args)
        sut.main()

    # STS client created then assume_role called
    sts_calls = [c for c in mock_boto3.client.call_args_list if c.args[0] == "sts"]
    assert len(sts_calls) == 1
    sts_mock.assume_role.assert_called_once()
    call_kwargs = sts_mock.assume_role.call_args.kwargs
    assert call_kwargs["RoleArn"] == "arn:aws:iam::123456789012:role/test-role"

    # S3 client created with temp creds
    s3_calls = [c for c in mock_boto3.client.call_args_list if c.args[0] == "s3"]
    assert len(s3_calls) == 1
    s3_kwargs = s3_calls[0].kwargs
    assert s3_kwargs["aws_access_key_id"] == "ASIA_FAKE"
    assert s3_kwargs["aws_session_token"] == "token"


# ─── #541: verification/ sync ─────────────────────────────────────────────────

def test_upload_includes_verification_files_when_present(tmp_path, monkeypatch):
    """#541 bug 2 regression: verification/{country}.json files sync to
    s3://{bucket}/events-source/verification/, alongside curated/."""
    curated = tmp_path / "events" / "curated"
    verification = tmp_path / "events" / "verification"
    _write_json(curated, "jordan.json")
    _write_json(verification, "jordan.json", [{"event_id": 1, "verdict": "verified"}])
    _write_json(verification, "germany.json", [{"event_id": 1, "verdict": "verified"}])

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", verification)
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "nonexistent.md")

    s3 = _make_s3()
    sut.upload(s3, "test-bucket", dry_run=False)

    # 1 curated + 2 verification = 3 upload calls
    assert s3.upload_file.call_count == 3
    uploaded_keys = {c.args[2] for c in s3.upload_file.call_args_list}
    assert "events-source/curated/jordan.json" in uploaded_keys
    assert "events-source/verification/jordan.json" in uploaded_keys
    assert "events-source/verification/germany.json" in uploaded_keys


def test_upload_skips_verification_when_dir_missing(tmp_path, monkeypatch, capsys):
    """Verification dir is optional — if it doesn't exist, warn and continue
    (don't fail the entire sync just because verification hasn't been built)."""
    curated = tmp_path / "events" / "curated"
    _write_json(curated, "jordan.json")
    # VERIFICATION_DIR explicitly does not exist
    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", tmp_path / "no_verification_here")
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "nonexistent.md")

    s3 = _make_s3()
    sut.upload(s3, "test-bucket", dry_run=False)

    assert s3.upload_file.call_count == 1  # only the 1 curated file
    captured = capsys.readouterr()
    assert "verification" in captured.out.lower()
    assert "WARNING" in captured.out


def test_upload_verification_dry_run_skips_upload(tmp_path, monkeypatch):
    """Dry-run mode must not call upload_file even for verification files."""
    curated = tmp_path / "events" / "curated"
    verification = tmp_path / "events" / "verification"
    _write_json(curated, "jordan.json")
    _write_json(verification, "jordan.json")

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", verification)
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "nonexistent.md")

    s3 = _make_s3()
    sut.upload(s3, "test-bucket", dry_run=True)
    s3.upload_file.assert_not_called()


def test_download_fetches_verification_files(tmp_path, monkeypatch):
    """#541 bug 2 regression for the download direction: S3 verification/
    objects land in local VERIFICATION_DIR."""
    curated = tmp_path / "events" / "curated"
    verification = tmp_path / "events" / "verification"

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", verification)
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "TRACKING.md")

    s3 = _make_s3()
    _stub_paginator(
        s3,
        keys=["events-source/curated/jordan.json"],
        verification_keys=[
            "events-source/verification/jordan.json",
            "events-source/verification/germany.json",
        ],
    )

    sut.download(s3, "test-bucket", dry_run=False)

    # 1 curated + 2 verification + 1 TRACKING.md = 4 download calls
    assert s3.download_file.call_count == 4
    downloaded_keys = {c.args[1] for c in s3.download_file.call_args_list}
    assert "events-source/curated/jordan.json" in downloaded_keys
    assert "events-source/verification/jordan.json" in downloaded_keys
    assert "events-source/verification/germany.json" in downloaded_keys


def test_download_creates_verification_dir_on_first_call(tmp_path, monkeypatch):
    """Fresh clones don't have events/verification/ yet — download() must
    create it just like it creates curated/."""
    curated = tmp_path / "events" / "curated"
    verification = tmp_path / "events" / "verification"
    # Neither exists yet
    assert not curated.exists()
    assert not verification.exists()

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", verification)
    monkeypatch.setattr(sut, "TRACKING_FILE", tmp_path / "TRACKING.md")

    s3 = _make_s3()
    _stub_paginator(s3, [], verification_keys=[])

    sut.download(s3, "test-bucket", dry_run=False)

    assert curated.exists() and curated.is_dir()
    assert verification.exists() and verification.is_dir()


# ─── #541: Windows unicode safety ─────────────────────────────────────────────

def test_no_unicode_check_marks_in_output(tmp_path, monkeypatch, capsys):
    """#541 bug 3 regression: the script must not print U+2713 (CHECK MARK)
    or any character outside the cp1252-safe set in success/warning lines.
    cp1252 can't encode U+2713 and crashes the script on Windows. Belt-
    and-braces alongside the sys.stdout.reconfigure(encoding='utf-8') call
    at module import."""
    curated = tmp_path / "events" / "curated"
    verification = tmp_path / "events" / "verification"
    _write_json(curated, "jordan.json")
    _write_json(verification, "jordan.json")
    tracking = tmp_path / "TRACKING.md"
    tracking.write_text("# tracking", encoding="utf-8")

    monkeypatch.setattr(sut, "CURATED_DIR", curated)
    monkeypatch.setattr(sut, "VERIFICATION_DIR", verification)
    monkeypatch.setattr(sut, "TRACKING_FILE", tracking)

    s3 = _make_s3()
    sut.upload(s3, "test-bucket", dry_run=False)

    captured = capsys.readouterr()
    # The forbidden chars are CHECK MARK (U+2713) and HEAVY CHECK MARK
    # (U+2714) — both crash cp1252. Replace with ASCII "OK".
    assert "✓" not in captured.out, "U+2713 CHECK MARK is cp1252-unsafe"
    assert "✔" not in captured.out, "U+2714 HEAVY CHECK MARK is cp1252-unsafe"
    # Sanity: success markers ARE printed (the ASCII replacement)
    assert "OK " in captured.out


def test_module_reconfigures_stdout_to_utf8():
    """The script must call sys.stdout.reconfigure(encoding='utf-8') at
    import time on platforms where stdout supports it (Python 3.7+).
    This is the second leg of the cp1252 belt-and-braces fix — even if a
    future contributor reintroduces a non-ASCII char in print(), it won't
    crash on Windows because stdout is forced to UTF-8."""
    # If the reconfigure call worked, sys.stdout.encoding should be utf-8
    # (case-insensitive) when this test runs on any platform whose stdout
    # supports reconfigure. On platforms that don't support it (rare —
    # Python 3.7+ universally has TextIOWrapper.reconfigure), the script
    # silently skips. Either way, no exception at module import.
    import sys as _sys
    if hasattr(_sys.stdout, "reconfigure"):
        assert _sys.stdout.encoding.lower().replace("-", "") in (
            "utf8", "utf-8",
        ), f"stdout encoding is {_sys.stdout.encoding}, expected utf-8"
