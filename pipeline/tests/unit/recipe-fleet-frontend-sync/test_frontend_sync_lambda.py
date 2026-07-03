"""Unit tests for qgi-recipe-fleet-frontend-sync Lambda (qgi-aws-tf#973 lane 2).

Mirrors the test layout of the sibling `qgi-frontend-bake-trigger` Lambda.

Covers:
  - _validate_event: required-field enforcement; trailing-slash normalization
  - _get_pat: reused from sibling pattern (Secrets Manager string secret)
  - _dispatch_workflow: 204 OK; non-204 raises; HTTPError raises with body
  - lambda_handler: missing fields raise; happy path end-to-end; dispatch
    failure propagates
"""

import importlib.util
import json
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
    / "recipe-fleet-frontend-sync"
    / "lambda_function.py"
)
_spec = importlib.util.spec_from_file_location("fe_sync", _MODULE_PATH)
fe_sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe_sync)


# ─── _validate_event ─────────────────────────────────────────────────────


class TestValidateEvent:
    def test_well_formed_event(self):
        event = {
            "vintage_s3_prefix": "frontend-data/te-fleet-run-2-abc/",
            "execution_name": "abc",
            "vintage": "fleet-run-2-2026-08-15",
        }
        prefix, exec_name, vintage = fe_sync._validate_event(event)
        assert prefix == "frontend-data/te-fleet-run-2-abc/"
        assert exec_name == "abc"
        assert vintage == "fleet-run-2-2026-08-15"

    def test_missing_prefix_raises(self):
        with pytest.raises(ValueError, match="vintage_s3_prefix"):
            fe_sync._validate_event({"execution_name": "x"})

    def test_missing_exec_name_raises(self):
        with pytest.raises(ValueError, match="execution_name"):
            fe_sync._validate_event({"vintage_s3_prefix": "x/"})

    def test_empty_prefix_raises(self):
        with pytest.raises(ValueError, match="vintage_s3_prefix"):
            fe_sync._validate_event({"vintage_s3_prefix": "", "execution_name": "x"})

    def test_empty_event_raises(self):
        with pytest.raises(ValueError):
            fe_sync._validate_event({})

    def test_none_event_raises(self):
        with pytest.raises(ValueError):
            fe_sync._validate_event(None)

    def test_trailing_slash_normalized(self):
        prefix, _, _ = fe_sync._validate_event(
            {
                "vintage_s3_prefix": "frontend-data/te-fleet-run-2-abc",
                "execution_name": "abc",
            }
        )
        assert prefix.endswith("/")

    def test_vintage_optional(self):
        prefix, exec_name, vintage = fe_sync._validate_event(
            {
                "vintage_s3_prefix": "x/",
                "execution_name": "abc",
            }
        )
        assert vintage is None


# ─── _get_pat ────────────────────────────────────────────────────────────


class TestGetPat:
    def test_returns_stripped_secret_string(self):
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": "  ghp_abc123  "}
        assert fe_sync._get_pat(client) == "ghp_abc123"

    def test_empty_secret_string_raises(self):
        client = MagicMock()
        client.get_secret_value.return_value = {"SecretString": ""}
        with pytest.raises(RuntimeError, match="no SecretString"):
            fe_sync._get_pat(client)

    def test_missing_secret_string_key_raises(self):
        """Defensive: Secrets Manager binary secrets return no `SecretString`
        key (binary content is under `SecretBinary` instead). Module rejects."""
        client = MagicMock()
        client.get_secret_value.return_value = {}
        with pytest.raises(RuntimeError, match="no SecretString"):
            fe_sync._get_pat(client)


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
        monkeypatch.setattr(fe_sync, "GITHUB_REF", "main")
        fake_opener = MagicMock(return_value=_FakeResponse(204))
        status = fe_sync._dispatch_workflow(
            "token",
            {"s3_bucket": "b", "vintage_s3_prefix": "p/", "execution_name": "x", "vintage": "v"},
            urlopen=fake_opener,
        )
        assert status == 204
        req = fake_opener.call_args[0][0]
        assert req.get_method() == "POST"
        assert req.full_url.endswith("/sync-te-fleet-vintage.yml/dispatches")
        assert req.headers["Authorization"] == "Bearer token"
        body = json.loads(req.data.decode("utf-8"))
        assert body["ref"] == "main"
        assert body["inputs"]["s3_bucket"] == "b"
        assert body["inputs"]["vintage_s3_prefix"] == "p/"
        assert body["inputs"]["execution_name"] == "x"

    def test_non_204_raises(self):
        fake_opener = MagicMock(return_value=_FakeResponse(201))
        with pytest.raises(RuntimeError, match="HTTP 201"):
            fe_sync._dispatch_workflow("token", {}, urlopen=fake_opener)

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
            fe_sync._dispatch_workflow("token", {}, urlopen=_opener)


# ─── lambda_handler ──────────────────────────────────────────────────────


class TestLambdaHandler:
    def test_missing_required_field_raises(self, monkeypatch):
        # _get_pat should NOT be called when validation fails
        monkeypatch.setattr(
            fe_sync,
            "_get_pat",
            lambda *a, **kw: (_ for _ in ()).throw(AssertionError("validation should fail first")),
        )
        with pytest.raises(ValueError, match="vintage_s3_prefix"):
            fe_sync.lambda_handler({"execution_name": "x"}, None)

    def test_happy_path_end_to_end(self, monkeypatch):
        monkeypatch.setattr(fe_sync, "_get_pat", lambda *a, **kw: "token")
        fake_opener = MagicMock(return_value=_FakeResponse(204))
        monkeypatch.setattr(fe_sync.urllib.request, "urlopen", fake_opener)

        event = {
            "vintage_s3_prefix": "frontend-data/te-fleet-run-2-abc/",
            "execution_name": "abc",
            "vintage": "fleet-run-2-2026-08-15",
        }
        result = fe_sync.lambda_handler(event, None)
        assert result["dispatched"] is True
        assert result["status"] == 204
        assert result["inputs"]["vintage_s3_prefix"] == "frontend-data/te-fleet-run-2-abc/"
        assert result["inputs"]["execution_name"] == "abc"
        assert result["inputs"]["vintage"] == "fleet-run-2-2026-08-15"
        assert result["inputs"]["s3_bucket"] == fe_sync.S3_BUCKET

    def test_vintage_defaults_to_execution_name(self, monkeypatch):
        """When the event doesn't supply `vintage`, the workflow input
        defaults to the execution_name so the PR branch name is still
        unique per SFN run."""
        monkeypatch.setattr(fe_sync, "_get_pat", lambda *a, **kw: "token")
        fake_opener = MagicMock(return_value=_FakeResponse(204))
        monkeypatch.setattr(fe_sync.urllib.request, "urlopen", fake_opener)

        event = {
            "vintage_s3_prefix": "frontend-data/te-fleet-run-2-abc/",
            "execution_name": "abc",
        }
        result = fe_sync.lambda_handler(event, None)
        assert result["inputs"]["vintage"] == "abc"

    def test_dispatch_failure_propagates(self, monkeypatch):
        monkeypatch.setattr(fe_sync, "_get_pat", lambda *a, **kw: "token")
        fake_opener = MagicMock(return_value=_FakeResponse(500))
        monkeypatch.setattr(fe_sync.urllib.request, "urlopen", fake_opener)
        with pytest.raises(RuntimeError, match="HTTP 500"):
            fe_sync.lambda_handler(
                {"vintage_s3_prefix": "p/", "execution_name": "x"},
                None,
            )
