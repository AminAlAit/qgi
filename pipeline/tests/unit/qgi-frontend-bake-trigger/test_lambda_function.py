"""Unit tests for qgi-frontend-bake-trigger Lambda (#417 Option C).

Covers:
  - _parse_s3_event: well-formed events, empty, malformed
  - _get_pat: SecretsManager stub returns PAT string; binary/empty raises
  - _dispatch_workflow: injectable urlopen; 204 ok, non-204 raises,
    HTTPError raises with body
  - lambda_handler: wrong-key skip, no-records skip, happy path end-to-end
"""

import importlib.util
import json
import os
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import HTTPError

import pytest

# Load the module directly from the Lambda dir (no package install).
_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "lambdas"
    / "qgi-frontend-bake-trigger"
    / "lambda_function.py"
)
_spec = importlib.util.spec_from_file_location("bake_trigger", _MODULE_PATH)
bake_trigger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bake_trigger)


# ─── _parse_s3_event ─────────────────────────────────────────────────────


class TestParseS3Event:
    def test_well_formed_event(self):
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "qgi-data-lake-771606957899"},
                        "object": {
                            "key": "dashboard/country-risks.json",
                            "eTag": "abc123def456",
                        },
                    },
                }
            ],
        }
        assert bake_trigger._parse_s3_event(event) == (
            "qgi-data-lake-771606957899",
            "dashboard/country-risks.json",
            "abc123def456",
        )

    def test_no_records_returns_none(self):
        assert bake_trigger._parse_s3_event({}) is None
        assert bake_trigger._parse_s3_event({"Records": []}) is None

    def test_missing_bucket_returns_none(self):
        event = {"Records": [{"s3": {"object": {"key": "x"}}}]}
        assert bake_trigger._parse_s3_event(event) is None

    def test_missing_key_returns_none(self):
        event = {"Records": [{"s3": {"bucket": {"name": "b"}}}]}
        assert bake_trigger._parse_s3_event(event) is None

    def test_missing_etag_defaults_empty(self):
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "k"},
                    },
                }
            ],
        }
        assert bake_trigger._parse_s3_event(event) == ("b", "k", "")


# ─── _get_pat ────────────────────────────────────────────────────────────


class TestGetPat:
    def test_returns_stripped_secret_string(self):
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": "  ghp_abc123  "}
        assert bake_trigger._get_pat(client) == "ghp_abc123"

    def test_empty_secret_string_raises(self):
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": ""}
        with pytest.raises(RuntimeError, match="no SecretString"):
            bake_trigger._get_pat(client)

    def test_missing_secret_string_raises(self):
        client = MagicMock()
        client.get_secret_value.return_value = {}
        with pytest.raises(RuntimeError, match="no SecretString"):
            bake_trigger._get_pat(client)


# ─── _dispatch_workflow ──────────────────────────────────────────────────


class _FakeResponse:
    """Minimal context-manager mock for urllib.request.urlopen responses."""

    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestDispatchWorkflow:
    def test_204_returns_status(self, monkeypatch):
        # GITHUB_REF is a runner-injected env var on GitHub Actions
        # (`refs/heads/main`); the Lambda's module-level default of "main"
        # gets shadowed there. Pin the attribute for deterministic asserts.
        monkeypatch.setattr(bake_trigger, "GITHUB_REF", "main")
        fake_opener = MagicMock(return_value=_FakeResponse(204))
        status = bake_trigger._dispatch_workflow(
            "token",
            {"bucket": "b", "key": "k"},
            urlopen=fake_opener,
        )
        assert status == 204
        # Verify the request was built correctly.
        req = fake_opener.call_args[0][0]
        assert req.get_method() == "POST"
        assert "api.github.com" in req.full_url
        assert "workflow_dispatch" not in req.full_url  # uses /dispatches path
        assert req.full_url.endswith("/dispatches")
        assert req.headers["Authorization"] == "Bearer token"
        body = json.loads(req.data.decode("utf-8"))
        assert body["ref"] == "main"
        assert body["inputs"] == {"bucket": "b", "key": "k"}

    def test_non_204_raises(self):
        fake_opener = MagicMock(return_value=_FakeResponse(201))
        with pytest.raises(RuntimeError, match="HTTP 201"):
            bake_trigger._dispatch_workflow(
                "token",
                {},
                urlopen=fake_opener,
            )

    def test_http_error_raises_with_body(self):
        def _opener(req, timeout=None):
            raise HTTPError(
                req.full_url,
                401,
                "Unauthorized",
                hdrs=None,
                fp=BytesIO(b'{"message": "Bad credentials"}'),
            )

        with pytest.raises(RuntimeError, match="HTTP 401.*Bad credentials"):
            bake_trigger._dispatch_workflow("token", {}, urlopen=_opener)


# ─── lambda_handler ──────────────────────────────────────────────────────


class TestLambdaHandler:
    def test_no_records_no_dispatch(self, monkeypatch):
        called = {"n": 0}
        monkeypatch.setattr(
            bake_trigger,
            "_get_pat",
            lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called")),
        )
        result = bake_trigger.lambda_handler({"Records": []}, None)
        assert result == {"dispatched": False, "reason": "no_s3_record"}

    def test_wrong_key_skipped(self, monkeypatch):
        monkeypatch.setattr(
            bake_trigger,
            "_get_pat",
            lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not be called")),
        )
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "dashboard/some-other-file.json", "eTag": "x"},
                    },
                }
            ],
        }
        result = bake_trigger.lambda_handler(event, None)
        assert result["dispatched"] is False
        assert result["reason"] == "wrong_key"

    def test_happy_path_end_to_end(self, monkeypatch):
        monkeypatch.setattr(bake_trigger, "_get_pat", lambda *a, **kw: "token")
        fake_opener = MagicMock(return_value=_FakeResponse(204))
        monkeypatch.setattr(
            bake_trigger.urllib.request,
            "urlopen",
            fake_opener,
        )
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "qgi-data-lake-771606957899"},
                        "object": {
                            "key": "dashboard/country-risks.json",
                            "eTag": "abc12345xyz",
                        },
                    },
                }
            ],
        }
        result = bake_trigger.lambda_handler(event, None)
        assert result["dispatched"] is True
        assert result["status"] == 204
        assert result["inputs"]["bucket"] == "qgi-data-lake-771606957899"
        assert result["inputs"]["key"] == "dashboard/country-risks.json"
        assert result["inputs"]["etag"] == "abc12345xyz"
        assert "abc12345" in result["inputs"]["message"]

    def test_dispatch_failure_propagates(self, monkeypatch):
        monkeypatch.setattr(bake_trigger, "_get_pat", lambda *a, **kw: "token")
        fake_opener = MagicMock(return_value=_FakeResponse(500))
        monkeypatch.setattr(
            bake_trigger.urllib.request,
            "urlopen",
            fake_opener,
        )
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "b"},
                        "object": {"key": "dashboard/country-risks.json", "eTag": "x"},
                    },
                }
            ],
        }
        with pytest.raises(RuntimeError, match="HTTP 500"):
            bake_trigger.lambda_handler(event, None)
