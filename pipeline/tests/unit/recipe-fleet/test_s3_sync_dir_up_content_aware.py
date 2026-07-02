"""QA #967 follow-up C: s3_sync_dir_up must skip a file when the S3 object
already has matching ContentLength AND its LastModified is ≥ the local file's
mtime. Otherwise upload — covering new files, edits, larger-on-disk, smaller-
on-disk, and the case where the S3 copy is older than what we just wrote.

The periodic-sync + multi-stage-emit pattern in the entrypoint re-syncs the
same dir 2-3 times per recipe. Without this skip, each re-sync re-uploads ~5
small JSONs that haven't changed.

This file pins the safe-skip semantics and the error-propagation semantics
(non-404 ClientError must NOT be swallowed — mirrors the #918 fix on
s3_object_exists). No real S3 — boto3 fake.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

_ENTRYPOINT = Path(__file__).resolve().parents[3] / "batch" / "recipe-fleet" / "recipe_fleet_entrypoint.py"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location("recipe_fleet_entrypoint_sync_content", _ENTRYPOINT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeS3:
    def __init__(self):
        self.objects: dict[str, dict] = {}  # key → {ContentLength, LastModified}
        self.uploaded_keys: list[str] = []

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            err = {"Error": {"Code": "404", "Message": "Not Found"}}
            raise ClientError(error_response=err, operation_name="HeadObject")
        return self.objects[Key]

    def upload_file(self, path, bucket, key):
        # Record + simulate the upload by populating head_object's table.
        self.uploaded_keys.append(key)
        size = Path(path).stat().st_size
        self.objects[key] = {
            "ContentLength": size,
            "LastModified": datetime.now(timezone.utc),
        }


@pytest.fixture
def ep_and_s3(monkeypatch):
    ep = _load_entrypoint()
    fake = _FakeS3()
    monkeypatch.setattr(ep, "_s3", lambda: fake)
    return ep, fake


def test_skips_when_s3_has_matching_size_and_fresher_mtime(ep_and_s3, tmp_path):
    ep, fake = ep_and_s3
    f = tmp_path / "summary.json"
    f.write_text('{"k":"v"}')
    local_size = f.stat().st_size
    # Stage S3 with matching size AND LastModified strictly after local mtime.
    s3_modified = datetime.now(timezone.utc) + timedelta(seconds=5)
    fake.objects["recipes/civil_war/summary.json"] = {
        "ContentLength": local_size,
        "LastModified": s3_modified,
    }
    uploaded = ep.s3_sync_dir_up(tmp_path, "bucket", "recipes/civil_war/")
    assert uploaded == 0
    assert fake.uploaded_keys == []


def test_uploads_when_s3_size_mismatches_local(ep_and_s3, tmp_path):
    ep, fake = ep_and_s3
    f = tmp_path / "summary.json"
    f.write_text('{"a":1,"b":2}')
    fake.objects["recipes/civil_war/summary.json"] = {
        "ContentLength": 999,  # mismatched
        "LastModified": datetime.now(timezone.utc) + timedelta(seconds=5),
    }
    uploaded = ep.s3_sync_dir_up(tmp_path, "bucket", "recipes/civil_war/")
    assert uploaded == 1
    assert fake.uploaded_keys == ["recipes/civil_war/summary.json"]


def test_uploads_when_s3_object_is_older_than_local(ep_and_s3, tmp_path):
    """Even with matching size, an older S3 object must be re-uploaded — local
    was edited to coincidentally yield same byte count."""
    ep, fake = ep_and_s3
    f = tmp_path / "summary.json"
    f.write_text('{"k":"v"}')
    local_size = f.stat().st_size
    fake.objects["x/summary.json"] = {
        "ContentLength": local_size,
        "LastModified": datetime.now(timezone.utc) - timedelta(minutes=5),  # older
    }
    uploaded = ep.s3_sync_dir_up(tmp_path, "bucket", "x/")
    assert uploaded == 1


def test_uploads_when_s3_object_absent(ep_and_s3, tmp_path):
    ep, fake = ep_and_s3
    (tmp_path / "new.json").write_text("{}")
    # head_object → 404 raised → upload taken
    uploaded = ep.s3_sync_dir_up(tmp_path, "bucket", "y/")
    assert uploaded == 1
    assert fake.uploaded_keys == ["y/new.json"]


def test_mixed_uploaded_and_skipped(ep_and_s3, tmp_path):
    ep, fake = ep_and_s3
    a = tmp_path / "fresh.json"
    a.write_text('{"a":1}')
    b = tmp_path / "stale.json"
    b.write_text('{"b":2}')
    # fresh.json: S3 has matching size + fresher mtime → skip
    fake.objects["r/fresh.json"] = {
        "ContentLength": a.stat().st_size,
        "LastModified": datetime.now(timezone.utc) + timedelta(seconds=10),
    }
    # stale.json: S3 missing → upload
    uploaded = ep.s3_sync_dir_up(tmp_path, "bucket", "r/")
    assert uploaded == 1
    assert fake.uploaded_keys == ["r/stale.json"]


def test_propagates_non_404_client_error_does_NOT_swallow(ep_and_s3, tmp_path, monkeypatch):
    """403 / throttle / network → MUST raise (mirrors #918 on s3_object_exists).
    Swallowing here would silently double-upload or worse, mis-skip on a
    transient permission glitch."""
    ep, fake = ep_and_s3
    (tmp_path / "x.json").write_text("{}")

    def fake_head(*, Bucket, Key):
        err = {"Error": {"Code": "403", "Message": "Forbidden"}}
        raise ClientError(error_response=err, operation_name="HeadObject")

    monkeypatch.setattr(fake, "head_object", fake_head)
    with pytest.raises(ClientError) as exc_info:
        ep.s3_sync_dir_up(tmp_path, "bucket", "p/")
    assert exc_info.value.response["Error"]["Code"] == "403"
    assert fake.uploaded_keys == []  # nothing leaked through on error


def test_NoSuchKey_code_is_treated_as_404(ep_and_s3, tmp_path, monkeypatch):
    """boto3 occasionally returns Code='NoSuchKey' instead of '404' for absent
    objects depending on the API path — treat both as cache-miss."""
    ep, fake = ep_and_s3
    (tmp_path / "n.json").write_text("{}")

    def fake_head(*, Bucket, Key):
        err = {"Error": {"Code": "NoSuchKey", "Message": "missing"}}
        raise ClientError(error_response=err, operation_name="HeadObject")

    monkeypatch.setattr(fake, "head_object", fake_head)
    uploaded = ep.s3_sync_dir_up(tmp_path, "bucket", "q/")
    assert uploaded == 1
