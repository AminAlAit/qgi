"""Unit tests for the BAKE_MODE=aws routing in bake_te_fleet_run_1.

Covers:
  - _BakeOutput local mode → writes hit the FS at the expected paths
  - _BakeOutput aws mode → writes hit s3.put_object with the right Key+Body
  - mkdir() is a no-op in aws mode
  - Invalid mode raises ValueError at construction
  - Absolute rel_path is rejected
  - _refuse_overwrite_if_baked raises when MANIFEST.json already exists
  - _refuse_overwrite_if_baked is silent when prefix is empty / no existing key

These tests do NOT exercise the full bake pipeline — that requires real walk
artifacts. They lock the writer contract so the AWS-mode rewrite stays
behaviour-equivalent to the local mode.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Import the bake module by path (it is a script, not a package member)
_BAKE = Path(__file__).resolve().parents[1] / "scripts" / "bake_te_fleet_run_1.py"
spec = importlib.util.spec_from_file_location("bake_te_fleet_run_1", _BAKE)
bake_mod = importlib.util.module_from_spec(spec)
sys.modules["bake_te_fleet_run_1"] = bake_mod
spec.loader.exec_module(bake_mod)

_BakeOutput = bake_mod._BakeOutput
_refuse_overwrite_if_baked = bake_mod._refuse_overwrite_if_baked
_resolve_reference_input = bake_mod._resolve_reference_input
_resolve_audience_status = bake_mod._resolve_audience_status


class TestBakeOutputLocal:
    def test_write_text_creates_file_under_output_dir(self, tmp_path: Path):
        s3 = MagicMock()
        w = _BakeOutput(
            mode="local", output_dir=tmp_path, s3_client=s3,
            bucket="ignored", prefix="",
        )
        w.write_text("scores/x.scores.json", '{"k":1}')
        target = tmp_path / "scores" / "x.scores.json"
        assert target.read_text() == '{"k":1}'
        s3.put_object.assert_not_called()

    def test_mkdir_creates_subdir(self, tmp_path: Path):
        w = _BakeOutput(
            mode="local", output_dir=tmp_path, s3_client=MagicMock(),
            bucket="ignored", prefix="",
        )
        w.mkdir("cards-v3")
        assert (tmp_path / "cards-v3").is_dir()

    def test_describe_root_returns_path(self, tmp_path: Path):
        w = _BakeOutput(
            mode="local", output_dir=tmp_path, s3_client=MagicMock(),
            bucket="ignored", prefix="",
        )
        assert w.describe_root() == str(tmp_path)

    def test_unicode_payload_roundtrip_utf8(self, tmp_path: Path):
        """QA F1/F2: local writes must use UTF-8 to match the S3 path's
        .encode('utf-8'); without it, flag emoji + non-ASCII indicator names
        would silently mangle on Windows (cp1252 default locale)."""
        w = _BakeOutput(
            mode="local", output_dir=tmp_path, s3_client=MagicMock(),
            bucket="ignored", prefix="",
        )
        payload = '{"country": "Côte d\'Ivoire", "flag": "🇨🇮", "indicator": "v2x_polyarchy"}'
        w.write_text("scores/x.scores.json", payload)
        target = tmp_path / "scores" / "x.scores.json"
        # Read back as UTF-8 explicitly — bit-identical
        assert target.read_text(encoding="utf-8") == payload
        # Raw bytes must round-trip through UTF-8 encoding
        assert target.read_bytes() == payload.encode("utf-8")


class TestBakeOutputAws:
    def test_write_text_calls_put_object_with_normalized_key(self, tmp_path: Path):
        s3 = MagicMock()
        w = _BakeOutput(
            mode="aws", output_dir=tmp_path, s3_client=s3,
            bucket="qgi-data-lake-771606957899",
            prefix="frontend-data/te-fleet-run-1-2026-05-30",
        )
        w.write_text("scores/foreign_intervention.scores.json", '{"k":1}')
        s3.put_object.assert_called_once_with(
            Bucket="qgi-data-lake-771606957899",
            Key="frontend-data/te-fleet-run-1-2026-05-30/scores/foreign_intervention.scores.json",
            Body=b'{"k":1}',
            ContentType="application/json",
        )

    def test_write_text_handles_trailing_slash_on_prefix(self, tmp_path: Path):
        s3 = MagicMock()
        w = _BakeOutput(
            mode="aws", output_dir=tmp_path, s3_client=s3,
            bucket="b", prefix="prefix/with/slash/",
        )
        w.write_text("MANIFEST.json", "{}")
        s3.put_object.assert_called_once()
        assert s3.put_object.call_args.kwargs["Key"] == "prefix/with/slash/MANIFEST.json"

    def test_mkdir_is_noop_in_aws_mode(self, tmp_path: Path):
        s3 = MagicMock()
        w = _BakeOutput(
            mode="aws", output_dir=tmp_path, s3_client=s3,
            bucket="b", prefix="p/",
        )
        w.mkdir()
        w.mkdir("cards-v3")
        # No FS touch (output_dir was a tmp_path; mkdir on it would have succeeded
        # but we want to assert no SUBDIR was created)
        assert not (tmp_path / "cards-v3").exists()
        s3.put_object.assert_not_called()

    def test_describe_root_returns_s3_uri(self, tmp_path: Path):
        w = _BakeOutput(
            mode="aws", output_dir=tmp_path, s3_client=MagicMock(),
            bucket="bkt", prefix="vintage-1",
        )
        assert w.describe_root() == "s3://bkt/vintage-1/"


class TestBakeOutputValidation:
    def test_invalid_mode_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Invalid BAKE_MODE"):
            _BakeOutput(
                mode="cloud", output_dir=tmp_path, s3_client=MagicMock(),
                bucket="b", prefix="",
            )

    def test_absolute_rel_path_rejected(self, tmp_path: Path):
        w = _BakeOutput(
            mode="aws", output_dir=tmp_path, s3_client=MagicMock(),
            bucket="b", prefix="p/",
        )
        with pytest.raises(ValueError, match="must be relative"):
            w.write_text("/absolute/path.json", "{}")


class TestRefuseOverwrite:
    def test_raises_when_manifest_exists(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {"KeyCount": 1, "Contents": [{"Key": "p/MANIFEST.json"}]}
        with pytest.raises(RuntimeError, match="Refusing to overwrite"):
            _refuse_overwrite_if_baked(s3, "bkt", "p")

    def test_silent_when_no_manifest(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {"KeyCount": 0}
        # Should not raise
        _refuse_overwrite_if_baked(s3, "bkt", "p/")

    def test_silent_when_prefix_empty(self):
        s3 = MagicMock()
        # When prefix is "", we should not even hit S3 — local mode
        _refuse_overwrite_if_baked(s3, "bkt", "")
        s3.list_objects_v2.assert_not_called()

    def test_list_objects_uses_manifest_key_not_just_prefix(self):
        """Lock the lookup key shape: it must be `{prefix}/MANIFEST.json`, not
        just `{prefix}`, so we don't false-positive on a prefix that exists for
        other reasons (e.g. an in-flight bake that hasn't written MANIFEST yet)."""
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {"KeyCount": 0}
        _refuse_overwrite_if_baked(s3, "bkt", "vintage-1/")
        s3.list_objects_v2.assert_called_once_with(
            Bucket="bkt",
            Prefix="vintage-1/MANIFEST.json",
            MaxKeys=1,
        )


class TestResolveReferenceInput:
    """QA #36 F1 follow-up: bake JobDef passes s3:// URIs for the 3
    reference files because they aren't vendored in the image. The resolver
    downloads to a temp file in that case; local paths pass through."""

    def test_local_path_pass_through(self, tmp_path: Path):
        local = tmp_path / "countries.json"
        local.write_text("{}")
        s3 = MagicMock()
        result = _resolve_reference_input(str(local), s3)
        assert result == Path(str(local))
        s3.download_file.assert_not_called()

    def test_path_object_pass_through(self, tmp_path: Path):
        local = tmp_path / "countries.json"
        s3 = MagicMock()
        result = _resolve_reference_input(local, s3)
        assert result == local
        s3.download_file.assert_not_called()

    def test_s3_uri_downloads(self):
        s3 = MagicMock()
        # Successful download_file is a no-op (returns None); the resolver
        # returns the local path it told boto3 to download into.
        result = _resolve_reference_input(
            "s3://qgi-data-lake-771606957899/reference/countries.json", s3,
        )
        assert isinstance(result, Path)
        assert result.suffix == ".json"
        s3.download_file.assert_called_once()
        call_args = s3.download_file.call_args[0]
        assert call_args[0] == "qgi-data-lake-771606957899"
        assert call_args[1] == "reference/countries.json"
        # Third arg is the tmp_path string
        assert str(result) == call_args[2]

    def test_s3_uri_with_nested_key(self):
        s3 = MagicMock()
        result = _resolve_reference_input(
            "s3://bucket/deeply/nested/path/file.md", s3,
        )
        assert isinstance(result, Path)
        assert result.suffix == ".md"
        call_args = s3.download_file.call_args[0]
        assert call_args[0] == "bucket"
        assert call_args[1] == "deeply/nested/path/file.md"

    def test_s3_uri_no_key_raises(self):
        s3 = MagicMock()
        with pytest.raises(ValueError, match="Malformed S3 URI"):
            _resolve_reference_input("s3://bucket-only", s3)

    def test_s3_uri_empty_key_raises(self):
        """QA #133 BLOCK: `s3://bucket/` passes the slash check but yields
        an empty key. Fail pre-flight here, not as an opaque boto3 error."""
        s3 = MagicMock()
        with pytest.raises(ValueError, match="key is empty"):
            _resolve_reference_input("s3://bucket/", s3)
        s3.download_file.assert_not_called()


class TestResolveAudienceStatus:
    """M8-R7 (BINDING, 2026-05-30 DECISION §10): 'prior_version' chip only for
    recipes with prior validated/graduated public footprint."""

    def test_lock_returns_validated(self):
        assert _resolve_audience_status("LOCK", {"status": "queued"}) == "validated"

    def test_hard_fail_greenfield_returns_coming_soon(self):
        """The most common fleet-run-1 case: HARD_FAIL on a recipe whose
        tracker status is 'queued' (greenfield). 'prior_version' is FORBIDDEN."""
        assert _resolve_audience_status("HARD_FAIL", {"status": "queued"}) == "coming_soon"

    def test_hard_fail_walked_no_graduation_returns_coming_soon(self):
        """`walked_no_graduation` is NOT 'validated or graduated' — recipe
        was walked but never shipped as validated. Still greenfield by M8-R7."""
        assert _resolve_audience_status("HARD_FAIL", {"status": "walked_no_graduation"}) == "coming_soon"

    def test_hard_fail_live_legacy_returns_prior_version(self):
        """Cascade-era live recipe re-walked and HARD_FAILed under F-ML-1:
        prior public footprint exists, so 'prior_version' is honest."""
        assert _resolve_audience_status("HARD_FAIL", {"status": "live_legacy"}) == "prior_version"

    def test_hard_fail_graduated_returns_prior_version(self):
        """A previously-graduated recipe HARD_FAILing under a re-walk:
        legitimate 'prior_version' — the public has seen it as validated."""
        assert _resolve_audience_status("HARD_FAIL", {"status": "graduated"}) == "prior_version"

    def test_hard_fail_no_tracker_row_returns_coming_soon(self):
        """Recipe missing from tracker entirely (rarest greenfield): no
        public footprint → coming_soon."""
        assert _resolve_audience_status("HARD_FAIL", None) == "coming_soon"

    def test_chance_fail_greenfield_returns_coming_soon(self):
        """CHANCE_FAIL also maps to 'prior_version' in the base dict; same
        M8-R7 gate applies."""
        assert _resolve_audience_status("CHANCE_FAIL", {"status": "queued"}) == "coming_soon"

    def test_marginal_pending_unaffected(self):
        """The gate only fires on base='prior_version'. MARGINAL_PENDING maps
        to 'in_play' regardless of tracker status. Both the short alias and
        the production canonical form (from run_f_ml_1_poc.py) are exercised
        per QA F2 (round 1 of #134)."""
        # Short alias (used in some test fixtures)
        assert _resolve_audience_status("MARGINAL_PENDING_BETA_CAL", {"status": "queued"}) == "in_play"
        assert _resolve_audience_status("MARGINAL_PENDING_BETA_CAL", {"status": "live_legacy"}) == "in_play"
        # Production canonical form emitted by run_f_ml_1_poc.py
        assert _resolve_audience_status("MARGINAL_PENDING_BETA_CALIBRATION", {"status": "queued"}) == "in_play"
        assert _resolve_audience_status("MARGINAL_PENDING_BETA_CALIBRATION", {"status": "live_legacy"}) == "in_play"

    def test_chance_fail_live_legacy_returns_prior_version(self):
        """QA F3: gate-opens path for CHANCE_FAIL on a cascade-era recipe.
        Mirrors the HARD_FAIL+live_legacy case for the second 'prior_version'
        verdict."""
        assert _resolve_audience_status("CHANCE_FAIL", {"status": "live_legacy"}) == "prior_version"

    def test_unknown_verdict_falls_to_coming_soon(self):
        """Unknown verdict (defensive): fall to coming_soon, never to a
        misleading prior_version."""
        assert _resolve_audience_status("UNKNOWN_VERDICT", {"status": "queued"}) == "coming_soon"

    def test_coverage_fail_unaffected(self):
        """COVERAGE_FAIL maps to 'coming_soon' in the base; gate doesn't fire."""
        assert _resolve_audience_status("COVERAGE_FAIL", {"status": "live_legacy"}) == "coming_soon"
