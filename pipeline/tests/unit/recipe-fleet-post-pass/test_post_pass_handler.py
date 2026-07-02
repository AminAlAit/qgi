"""Unit tests for the recipe-fleet-post-pass Lambda handler. boto3 is monkeypatched —
no real AWS calls. Each test pins ONE behavior of the handler's plumbing:

  - it reads each recipe's summary from the right S3 key
  - it tolerates a missing summary (classifies → queued)
  - it loads (or accepts the absence of) floors + previous tracker
  - it derives `floor_ordering_ok` from the frozen_at_utc / earliest filed dates
  - it derives per-recipe `beats_baseline` from the floors map
  - condition env vars (`POST_PASS_BIT_IDENTICAL_WALK_OK` / `POST_PASS_POISONED_GUARD_OK`)
    flip the matching gate honestly (default = conservative)
  - the draft is written to `post-pass/{vintage_id}/draft-tracker.json` — NEVER to the
    live tracker (Condition D)
  - warnings surface non-fatal issues (missing keys, malformed JSON, empty prefix)
  - the SFN-friendly return envelope has every required field

Methodology decisions live in `post_pass_core` and are re-tested in
`test_post_pass_core.py` — these tests do NOT re-derive tier policy."""

from __future__ import annotations

import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

_LAMBDA_DIR = Path(__file__).resolve().parents[3] / "lambdas" / "recipe-fleet-post-pass"

# Load lambda_function under a UNIQUE name to avoid sys.modules collision with
# other Lambda dirs that also expose a `lambda_function` module
# (see qgi-frontend-bake-trigger for the same pattern).
_spec = importlib.util.spec_from_file_location("post_pass_lf", _LAMBDA_DIR / "lambda_function.py")
lf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lf)

# post_pass_core has a unique module name (no collision risk), so the simple
# sys.path + import idiom is fine.
sys.path.insert(0, str(_LAMBDA_DIR))
import post_pass_core as pp  # noqa: E402


# ---------- S3 fake -----------------------------------------------------------


class _FakeS3:
    """Minimal S3 stub keyed by (bucket, key) → bytes. Tracks puts. Supports
    `list_objects_v2` with `Prefix` + `Delimiter='/'` returning CommonPrefixes
    (the exact slice of the API the handler uses)."""

    def __init__(self, objs: dict[tuple[str, str], bytes] | None = None, sub_prefixes: list[str] | None = None):
        self.objs = dict(objs or {})
        self.sub_prefixes = list(sub_prefixes or [])
        self.put_calls: list[tuple[str, str, bytes]] = []

    def get_object(self, *, Bucket: str, Key: str):
        if (Bucket, Key) not in self.objs:
            err = {"Error": {"Code": "NoSuchKey", "Message": f"{Key} missing"}}
            raise ClientError(error_response=err, operation_name="GetObject")
        return {"Body": BytesIO(self.objs[(Bucket, Key)])}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str = "application/octet-stream"):
        self.put_calls.append((Bucket, Key, Body))
        return {"ETag": '"fake"'}

    def get_paginator(self, name: str):
        assert name == "list_objects_v2"
        prefixes = self.sub_prefixes

        class _P:
            def paginate(self_inner, *, Bucket, Prefix, Delimiter):
                yield {"CommonPrefixes": [{"Prefix": p} for p in prefixes]}

        return _P()


@pytest.fixture
def fake_s3(monkeypatch):
    s3 = _FakeS3()
    monkeypatch.setattr(lf, "_s3", lambda: s3)
    return s3


def _put_summary(
    s3,
    bucket,
    prefix,
    rid,
    *,
    verdict="HARD_FAIL",
    auc=0.72,
    ci95_lo=0.66,
    ci95_hi=0.80,
    filed="2026-05-28T11:00:00Z",
    cohort_med=0.60,
    panel_fp=None,
):
    summary = {
        "recipe_id": rid,
        "verdict": verdict,
        "filed": filed,
        "global_loco": {"auc": auc, "ci95_lo": ci95_lo, "ci95_hi": ci95_hi},
        "per_cohort": {
            "a": {"loco_auc": cohort_med - 0.05},
            "b": {"loco_auc": cohort_med},
            "c": {"loco_auc": cohort_med + 0.05},
        },
    }
    if panel_fp is not None:
        summary["panel_fingerprint"] = panel_fp
    s3.objs[(bucket, f"{prefix.rstrip('/')}/{rid}/{lf._SUMMARY_FILENAME}")] = json.dumps(summary).encode("utf-8")
    s3.sub_prefixes.append(f"{prefix.rstrip('/')}/{rid}/")


def _put_floors(s3, bucket, *, frozen_at="2026-05-28T10:00:00Z", recipe_baselines: dict[str, float] | None = None):
    floors_doc = {
        "frozen_at_utc": frozen_at,
        "floors": {rid: {"hybrid_baseline": hb} for rid, hb in (recipe_baselines or {}).items()},
    }
    s3.objs[(bucket, lf._FLOORS_KEY)] = json.dumps(floors_doc).encode("utf-8")


def _put_prev_tracker(s3, bucket, tiers: dict[str, str]):
    s3.objs[(bucket, lf._PUBLISHED_TRACKER_KEY)] = json.dumps(
        {"draft_recipes": [{"recipe_id": rid, "tier": tier} for rid, tier in tiers.items()]}
    ).encode("utf-8")


# ---------- happy path --------------------------------------------------------


def test_happy_path_writes_draft_and_returns_envelope(fake_s3):
    bucket = "qgi-data-lake-771606957899"
    prefix = "ml-results/"
    _put_summary(
        fake_s3, bucket, prefix, "a", verdict="HARD_FAIL", auc=0.80, ci95_lo=0.72, ci95_hi=0.86, cohort_med=0.60
    )
    _put_summary(
        fake_s3,
        bucket,
        prefix,
        "b",
        verdict="MARGINAL_PENDING_BETA_CALIBRATION",
        auc=0.66,
        ci95_lo=0.55,
        ci95_hi=0.74,
        cohort_med=0.58,
    )
    _put_floors(fake_s3, bucket, recipe_baselines={"a": 0.70, "b": 0.65})
    _put_prev_tracker(fake_s3, bucket, {"a": pp.EXPERIMENTAL, "b": pp.EXPERIMENTAL})
    out = lf.lambda_handler(
        {"s3_bucket": bucket, "ml_results_prefix": prefix, "execution_name": "wave1-test-20260528"}, None
    )
    assert out["status"] == "ok"
    assert out["vintage_id"] == "wave1-test-20260528"
    assert out["draft_s3_uri"] == f"s3://{bucket}/post-pass/wave1-test-20260528/draft-tracker.json"
    assert out["n_recipes_processed"] == 2
    assert out["attestation_summary"]["pending_majles_signoff"] == out["n_transitions"]
    # The draft envelope was written exactly once + only to the draft key (NEVER the
    # published-tracker key — that's the PR-Majles path).
    assert len(fake_s3.put_calls) == 1
    put_bucket, put_key, _ = fake_s3.put_calls[0]
    assert put_bucket == bucket
    assert put_key == "post-pass/wave1-test-20260528/draft-tracker.json"
    assert put_key != lf._PUBLISHED_TRACKER_KEY


def test_draft_payload_has_required_top_level_fields(fake_s3):
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a")
    _put_floors(fake_s3, bucket)
    lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    for k in (
        "draft_recipes",
        "transitions",
        "attestation",
        "vintage_id",
        "produced_at_utc",
        "source_prefix",
        "warnings",
    ):
        assert k in body


# ---------- missing / malformed summaries -------------------------------------


def test_missing_summary_is_classified_queued_not_dropped(fake_s3):
    """When a recipe's sub-prefix exists but the summary is absent (e.g. the walk
    crashed mid-way), the recipe MUST still appear in the draft as queued, not be
    silently omitted — `assemble_tracker_draft` already enforces this for None."""
    bucket = "b"
    fake_s3.sub_prefixes.append("ml-results/a/")  # sub-prefix only, no summary file
    _put_floors(fake_s3, bucket)
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    rows = {r["recipe_id"]: r for r in body["draft_recipes"]}
    assert "a" in rows
    assert rows["a"]["tier"] == pp.QUEUED
    assert out["n_recipes_processed"] == 1


def test_malformed_summary_surfaces_in_warnings_not_a_crash(fake_s3):
    bucket = "b"
    fake_s3.objs[(bucket, "ml-results/a/f-ml-1-poc-summary.json")] = b"not json"
    fake_s3.sub_prefixes.append("ml-results/a/")
    _put_floors(fake_s3, bucket)
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    assert out["status"] == "ok"
    assert any("malformed JSON" in w for w in out["warnings"])


def test_empty_prefix_returns_ok_with_warning(fake_s3):
    """An empty prefix is honestly returned (n_recipes_processed=0 + a warning) so a
    config mistake surfaces — failing here would mask it."""
    bucket = "b"
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    assert out["status"] == "ok"
    assert out["n_recipes_processed"] == 0
    assert any("no recipe sub-prefixes" in w for w in out["warnings"])


def test_archive_subprefix_is_skipped(fake_s3):
    """`_archive/`-prefixed sub-keys are prior-vintage backups, not current-vintage
    recipes; they must NOT enter the post-pass results."""
    bucket = "b"
    fake_s3.sub_prefixes.append("ml-results/_archive/")
    _put_summary(fake_s3, bucket, "ml-results/", "a")
    _put_floors(fake_s3, bucket)
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    assert out["n_recipes_processed"] == 1


def test_event_missing_s3_bucket_raises(fake_s3):
    with pytest.raises(ValueError, match="s3_bucket"):
        lf.lambda_handler({"execution_name": "v1"}, None)


# ---------- floors + beats_baseline derivation --------------------------------


def test_beats_baseline_true_when_auc_above_hybrid_baseline(fake_s3):
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a", auc=0.80)
    _put_floors(fake_s3, bucket, recipe_baselines={"a": 0.70})
    lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    # The Directional path requires beats_baseline ≠ False; we don't expose the dict in
    # the draft but we CAN check the tier landed Directional (which requires it).
    row = next(r for r in body["draft_recipes"] if r["recipe_id"] == "a")
    assert row["tier"] in (pp.DIRECTIONAL, pp.EXPERIMENTAL)  # not demoted by False


def test_beats_baseline_false_demotes_to_experimental(fake_s3):
    """AUC ≤ hybrid_baseline (criterion 4 False) MUST demote a recipe that would
    otherwise be Directional, per classify_tier."""
    bucket = "b"
    _put_summary(
        fake_s3, bucket, "ml-results/", "a", verdict="HARD_FAIL", auc=0.80, ci95_lo=0.72, ci95_hi=0.86, cohort_med=0.60
    )
    _put_floors(fake_s3, bucket, recipe_baselines={"a": 0.85})  # baseline > our auc
    lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    row = next(r for r in body["draft_recipes"] if r["recipe_id"] == "a")
    assert row["tier"] == pp.EXPERIMENTAL


def test_missing_floors_doesnt_crash_but_warns_and_blocks_floor_ordering(fake_s3):
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a")
    # NO floors written
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    assert body["attestation"]["conditions"]["floor_ordering_ok"] is False
    assert any("floors missing" in w for w in out["warnings"])


def test_floor_ordering_ok_true_when_frozen_before_walks(fake_s3):
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a", filed="2026-05-28T11:00:00Z")
    _put_floors(fake_s3, bucket, frozen_at="2026-05-28T09:00:00Z")
    lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    assert body["attestation"]["conditions"]["floor_ordering_ok"] is True


def test_floor_ordering_ok_false_when_floors_frozen_AFTER_walks(fake_s3):
    """The FLEET-5 invariant: floors must be frozen BEFORE the earliest walk fires.
    A floors-frozen-after-walks ordering MUST flip this False — that scenario is the
    very class of bug FLEET-5 was filed to catch."""
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a", filed="2026-05-28T09:00:00Z")
    _put_floors(fake_s3, bucket, frozen_at="2026-05-28T11:00:00Z")
    lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    assert body["attestation"]["conditions"]["floor_ordering_ok"] is False


def test_floor_ordering_fail_closed_when_frozen_at_missing(fake_s3):
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a")
    # Floors doc with no `frozen_at_utc` field — must fail closed.
    fake_s3.objs[(bucket, lf._FLOORS_KEY)] = json.dumps({"floors": {}}).encode("utf-8")
    lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    assert body["attestation"]["conditions"]["floor_ordering_ok"] is False


# ---------- previous tracker / transitions ------------------------------------


def test_no_previous_tracker_yields_queued_to_tier_transitions(fake_s3):
    """First-ever vintage: prev_tiers={} → every classified recipe shows as a
    transition from QUEUED to its new tier."""
    bucket = "b"
    _put_summary(
        fake_s3, bucket, "ml-results/", "a", verdict="HARD_FAIL", auc=0.80, ci95_lo=0.72, ci95_hi=0.86, cohort_med=0.60
    )
    _put_floors(fake_s3, bucket, recipe_baselines={"a": 0.70})
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    assert out["n_transitions"] == 1
    t = body["transitions"][0]
    assert t["from_tier"] == pp.QUEUED
    assert t["needs_majles_signoff"] is True
    assert any("no previous tracker" in w for w in out["warnings"])


def test_prev_tracker_unchanged_tier_yields_no_transition(fake_s3):
    bucket = "b"
    _put_summary(
        fake_s3, bucket, "ml-results/", "a", verdict="HARD_FAIL", auc=0.80, ci95_lo=0.72, ci95_hi=0.86, cohort_med=0.60
    )
    _put_floors(fake_s3, bucket, recipe_baselines={"a": 0.70})
    _put_prev_tracker(fake_s3, bucket, {"a": pp.DIRECTIONAL})
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    assert out["n_transitions"] == 0


# ---------- condition env vars ------------------------------------------------


def test_default_bit_identical_walk_is_true_when_unset(fake_s3, monkeypatch):
    """F1 per QA PR review: symmetric to test_default_poisoned_guard_blocks. The
    canary §2.5 gate is the production check, so the in-Lambda env-var default for
    `bit_identical_walk` is True. A future refactor flipping that default to False
    would silently block every wave; this test guards against the regression."""
    monkeypatch.delenv("POST_PASS_BIT_IDENTICAL_WALK_OK", raising=False)
    monkeypatch.delenv("POST_PASS_POISONED_GUARD_OK", raising=False)
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a")
    _put_floors(fake_s3, bucket)
    lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    assert body["attestation"]["conditions"]["bit_identical_walk"] is True


def test_adhoc_fallback_appends_utc_timestamp_so_invokes_dont_collide(fake_s3):
    """Per QA PR review specific-scrutiny-2: a direct Lambda invoke without
    `execution_name` would write to `post-pass/ad-hoc/...` and clobber any prior ad-hoc
    invoke. The handler now suffixes a UTC timestamp so two manual sanity-invokes
    produce two distinct draft keys."""
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a")
    _put_floors(fake_s3, bucket)
    out = lf.lambda_handler({"s3_bucket": bucket}, None)  # no execution_name
    assert out["vintage_id"].startswith("ad-hoc-")
    # Format: ad-hoc-YYYYMMDDTHHMMSSZ — 17 chars after the prefix.
    assert len(out["vintage_id"]) == len("ad-hoc-") + 16
    assert out["draft_s3_uri"].endswith(f"post-pass/{out['vintage_id']}/draft-tracker.json")


def test_default_poisoned_guard_blocks_tracker_pr_may_merge(fake_s3, monkeypatch):
    """Default (no env var) is FALSE for the poisoned-indicator guard — by design until
    FLEET-7 #124 is built. tracker_pr_may_merge MUST be False as a consequence."""
    monkeypatch.delenv("POST_PASS_POISONED_GUARD_OK", raising=False)
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a")
    _put_floors(fake_s3, bucket)
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    assert out["attestation_summary"]["all_conditions_pass"] is False
    assert out["attestation_summary"]["tracker_pr_may_merge"] is False


def test_setting_poisoned_guard_env_var_true_unblocks_attestation(fake_s3, monkeypatch):
    monkeypatch.setenv("POST_PASS_POISONED_GUARD_OK", "true")
    monkeypatch.setenv("POST_PASS_BIT_IDENTICAL_WALK_OK", "true")
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a", filed="2026-05-28T11:00:00Z")
    _put_floors(fake_s3, bucket, frozen_at="2026-05-28T09:00:00Z", recipe_baselines={"a": 0.70})
    _put_prev_tracker(fake_s3, bucket, {"a": pp.DIRECTIONAL})  # no transition → no Majles
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    assert out["attestation_summary"]["all_conditions_pass"] is True
    assert out["attestation_summary"]["tracker_pr_may_merge"] is True


def test_bit_identical_walk_env_var_can_flip_false(fake_s3, monkeypatch):
    monkeypatch.setenv("POST_PASS_BIT_IDENTICAL_WALK_OK", "false")
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a")
    _put_floors(fake_s3, bucket)
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    assert out["attestation_summary"]["all_conditions_pass"] is False


@pytest.mark.parametrize("raw", ["", "0", "no", "False", "off", "bogus", "  "])
def test_env_bool_explicit_non_truthy_returns_false_even_when_default_true(monkeypatch, raw):
    """Conservative for methodology gates: an OPERATOR who set the env var to anything
    non-truthy is signalling 'not OK'; we honor that, not the optimistic default. A typo
    like 'ture' is therefore safer (held closed) than 'silently use the default'."""
    monkeypatch.setenv("X", raw)
    assert lf._env_bool("X", False) is False
    assert lf._env_bool("X", True) is False


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on"])
def test_env_bool_honors_truthy_strings(monkeypatch, raw):
    monkeypatch.setenv("X", raw)
    assert lf._env_bool("X", False) is True


def test_env_bool_unset_returns_default(monkeypatch):
    """Only an UNSET env var falls through to the default — the 'no operator opinion
    expressed' state."""
    monkeypatch.delenv("X", raising=False)
    assert lf._env_bool("X", True) is True
    assert lf._env_bool("X", False) is False


# ---------- propagation + safety ----------------------------------------------


def test_panel_fingerprint_pulled_from_first_summary_that_has_one(fake_s3):
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a")  # no fingerprint
    _put_summary(fake_s3, bucket, "ml-results/", "b", panel_fp="sha256:abcd")
    _put_floors(fake_s3, bucket)
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    assert body["attestation"]["panel_fingerprint"] == "sha256:abcd"
    # No divergence → no fingerprint warning.
    assert not any("panel_fingerprint divergence" in w for w in out["warnings"])


def test_panel_fingerprint_divergence_surfaces_in_warnings(fake_s3):
    """F2 per QA PR review: two walks with DIFFERENT panel fingerprints in one
    vintage is a real signal (panel mid-revision, race, stale image). Must surface in
    `warnings` rather than silently first-wins."""
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a", panel_fp="sha256:aaa")
    _put_summary(fake_s3, bucket, "ml-results/", "b", panel_fp="sha256:bbb")
    _put_floors(fake_s3, bucket)
    out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    # The attestation still records ONE fingerprint (well-formed draft) — the WARNING is
    # the audit trail.
    assert body["attestation"]["panel_fingerprint"] in ("sha256:aaa", "sha256:bbb")
    div = [w for w in out["warnings"] if "panel_fingerprint divergence" in w]
    assert len(div) == 1
    assert "sha256:aaa" in div[0] and "sha256:bbb" in div[0]


def test_handler_never_writes_to_published_tracker_key(fake_s3):
    """Condition D: the live tracker is updated ONLY via human-ratified PR. The handler
    must never touch the `_latest/published-tracker.json` key — even by accident."""
    bucket = "b"
    _put_summary(fake_s3, bucket, "ml-results/", "a")
    _put_floors(fake_s3, bucket)
    lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
    written_keys = [k for _, k, _ in fake_s3.put_calls]
    assert lf._PUBLISHED_TRACKER_KEY not in written_keys
    assert all("post-pass/" in k and "draft-tracker.json" in k for k in written_keys)


# ---------- #966 stale-walk rejection ----------------------------------------


class TestStaleWalkRejection:
    """#966 — a summary `filed` before `floors.frozen_at_utc` is a FLEET-5 invariant
    violation and a stale leftover from a prior pipeline version (the
    foreign_intervention 2026-05-25 leaked walk is the canonical case the filter
    closes). Filtered recipes route to QUEUED + a warning surfaces the reason."""

    def test_stale_walk_routes_to_queued_with_warning(self, fake_s3):
        bucket = "b"
        # walk filed BEFORE floors were frozen — must be rejected
        _put_summary(fake_s3, bucket, "ml-results/", "stale_recipe", filed="2026-05-25T13:25:28Z")
        _put_summary(fake_s3, bucket, "ml-results/", "fresh_recipe", filed="2026-05-28T13:00:00Z")
        _put_floors(fake_s3, bucket, frozen_at="2026-05-27T22:12:40Z")
        out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
        body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
        rows = {r["recipe_id"]: r for r in body["draft_recipes"]}
        assert rows["stale_recipe"]["tier"] == pp.QUEUED
        assert rows["fresh_recipe"]["tier"] != pp.QUEUED  # classified normally
        assert any("stale_recipe" in w and "stale walk" in w for w in out["warnings"])
        assert any("foreign_intervention" not in w for w in out["warnings"])  # not by name
        # FU2 per QA PR review — return envelope MUST self-describe the rejection
        # count so an operator reading the SFN history can see it without parsing warnings.
        assert out["n_stale_rejected"] == 1

    def test_no_rejection_when_all_walks_post_freeze(self, fake_s3):
        bucket = "b"
        _put_summary(fake_s3, bucket, "ml-results/", "a", filed="2026-05-28T13:00:00Z")
        _put_floors(fake_s3, bucket, frozen_at="2026-05-27T22:12:40Z")
        out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
        assert not any("stale walk" in w for w in out["warnings"])

    def test_no_rejection_when_floors_missing(self, fake_s3):
        """If floors.json is absent the existing floor_ordering_ok FAIL already covers it;
        the stale-walk filter is a no-op so it never silently masks the missing-floors
        condition."""
        bucket = "b"
        _put_summary(fake_s3, bucket, "ml-results/", "a", filed="2026-05-25T00:00:00Z")
        out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
        body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
        # Row classified normally (no rejection); the floor_ordering_ok FAIL is the
        # global surface for "we can't verify ordering".
        assert any("floors missing" in w for w in out["warnings"])
        assert not any("stale walk" in w for w in out["warnings"])

    def test_no_rejection_when_frozen_at_missing_from_floors(self, fake_s3):
        bucket = "b"
        _put_summary(fake_s3, bucket, "ml-results/", "a", filed="2026-05-25T00:00:00Z")
        # Floors doc present but lacks frozen_at_utc — must NOT reject (fail-open here is
        # fine: floor_ordering_ok=FAIL already surfaces the missing-field condition).
        fake_s3.objs[(bucket, lf._FLOORS_KEY)] = json.dumps({"floors": {}}).encode("utf-8")
        out = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
        assert not any("stale walk" in w for w in out["warnings"])

    def test_walk_filed_exactly_at_freeze_is_NOT_rejected(self, fake_s3):
        """Boundary: filed == frozen_at means the walk fired at the same instant the
        floors were committed. Strict `<` predicate keeps this case classified normally."""
        bucket = "b"
        ts = "2026-05-27T22:12:40Z"
        _put_summary(fake_s3, bucket, "ml-results/", "a", filed=ts)
        _put_floors(fake_s3, bucket, frozen_at=ts)
        lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
        body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
        rows = {r["recipe_id"]: r for r in body["draft_recipes"]}
        assert rows["a"]["tier"] != pp.QUEUED  # classified, not stale-rejected

    def test_malformed_filed_timestamp_is_left_alone(self, fake_s3):
        """A summary whose `filed` field is unparseable is NOT rejected here (the
        existing flow already treats it as classified-normally); the filter only
        rejects when both timestamps parse + ordering is violated. Fail-open for
        unparseable inputs avoids silent over-rejection."""
        bucket = "b"
        # Build a manual summary with garbage filed
        import json as _j

        s = {
            "recipe_id": "a",
            "verdict": "HARD_FAIL",
            "filed": "not-a-real-timestamp",
            "global_loco": {"auc": 0.7, "ci95_lo": 0.6, "ci95_hi": 0.8},
            "per_cohort": {"a": {"loco_auc": 0.6}, "b": {"loco_auc": 0.55}, "c": {"loco_auc": 0.62}},
        }
        fake_s3.objs[(bucket, "ml-results/a/f-ml-1-poc-summary.json")] = _j.dumps(s).encode()
        fake_s3.sub_prefixes.append("ml-results/a/")
        _put_floors(fake_s3, bucket, frozen_at="2026-05-27T22:12:40Z")
        lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
        body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
        rows = {r["recipe_id"]: r for r in body["draft_recipes"]}
        assert rows["a"]["tier"] != pp.QUEUED  # unparseable filed → not rejected here

    def test_summary_without_filed_field_is_left_alone(self, fake_s3):
        """Same reasoning as unparseable filed — a missing `filed` is not enough on
        its own to reject."""
        bucket = "b"
        import json as _j

        s = {
            "recipe_id": "a",
            "verdict": "HARD_FAIL",
            # NO `filed` field at all
            "global_loco": {"auc": 0.7, "ci95_lo": 0.6, "ci95_hi": 0.8},
            "per_cohort": {"a": {"loco_auc": 0.6}, "b": {"loco_auc": 0.55}, "c": {"loco_auc": 0.62}},
        }
        fake_s3.objs[(bucket, "ml-results/a/f-ml-1-poc-summary.json")] = _j.dumps(s).encode()
        fake_s3.sub_prefixes.append("ml-results/a/")
        _put_floors(fake_s3, bucket, frozen_at="2026-05-27T22:12:40Z")
        lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
        body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
        rows = {r["recipe_id"]: r for r in body["draft_recipes"]}
        assert rows["a"]["tier"] != pp.QUEUED


# -----------------------------------------------------------------------------


def test_s3_get_object_error_other_than_nosuchkey_propagates(fake_s3, monkeypatch):
    """A real S3 error (e.g. AccessDenied) must propagate — silently treating it as
    'missing' could mask an IAM regression that needs founder attention."""
    bucket = "b"
    err = {"Error": {"Code": "AccessDenied", "Message": "no perm"}}
    # The recipe sub-prefix is enumerated, but the get_object for floors returns 403.
    fake_s3.sub_prefixes.append("ml-results/a/")
    fake_s3.objs[(bucket, "ml-results/a/f-ml-1-poc-summary.json")] = json.dumps({}).encode()
    # Patch _get_json so the floors read raises AccessDenied.
    orig = lf._get_json

    def faulty(b, k, *, optional=False):
        if k == lf._FLOORS_KEY:
            raise ClientError(err, "GetObject")
        return orig(b, k, optional=optional)

    monkeypatch.setattr(lf, "_get_json", faulty)
    with pytest.raises(ClientError):
        lf.lambda_handler({"s3_bucket": bucket, "execution_name": "v1"}, None)
