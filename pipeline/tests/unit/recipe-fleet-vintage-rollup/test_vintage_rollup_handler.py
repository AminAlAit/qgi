"""Unit tests for the vintage-rollup handler (#968). boto3 is monkeypatched —
no real AWS calls. Tests pin: current + archive sub-prefix discovery / system-prefix
skip (no _archive in current pass) / read errors surface as warnings / rollup landing
at the right S3 key / handler returns the expected envelope."""

from __future__ import annotations

import importlib.util
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

# Load the lambda module under a UNIQUE name to avoid sys.modules collision
# with other Lambda dirs that also expose a `lambda_function` module
# (see qgi-frontend-bake-trigger for the same pattern).
_MODULE_PATH = Path(__file__).resolve().parents[3] / "lambdas" / "recipe-fleet-vintage-rollup" / "lambda_function.py"
_spec = importlib.util.spec_from_file_location("vintage_rollup_lf", _MODULE_PATH)
lf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lf)


class _FakeS3:
    def __init__(self):
        self.objs: dict[tuple[str, str], bytes] = {}
        self.sub_prefixes_by_prefix: dict[str, list[str]] = {}
        self.put_calls: list[tuple[str, str, bytes]] = []

    def get_object(self, *, Bucket, Key):
        if (Bucket, Key) not in self.objs:
            err = {"Error": {"Code": "NoSuchKey", "Message": "missing"}}
            raise ClientError(error_response=err, operation_name="GetObject")
        return {"Body": BytesIO(self.objs[(Bucket, Key)])}

    def put_object(self, *, Bucket, Key, Body, ContentType="application/octet-stream"):
        self.put_calls.append((Bucket, Key, Body))
        return {"ETag": '"fake"'}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        subs_by_prefix = self.sub_prefixes_by_prefix

        class _P:
            def paginate(self, *, Bucket, Prefix, Delimiter):
                yield {"CommonPrefixes": [{"Prefix": s} for s in subs_by_prefix.get(Prefix, [])]}

        return _P()


@pytest.fixture
def fake_s3(monkeypatch):
    s = _FakeS3()
    monkeypatch.setattr(lf, "_s3", lambda: s)
    return s


def _put_summary(s3, bucket, key, *, recipe_id="r", verdict="HARD_FAIL", filed="2026-05-28T11:00:00Z", auc=0.7):
    s3.objs[(bucket, key)] = json.dumps(
        {
            "recipe_id": recipe_id,
            "verdict": verdict,
            "filed": filed,
            "global_loco": {"auc": auc, "ci95_lo": auc - 0.05, "ci95_hi": auc + 0.05},
            "coverage_audit": {
                "n_pos_total": 100,
                "n_pos_survive": 80,
                "n_countries_survive": 20,
                "pos_coverage": 0.8,
                "coverage_pass": True,
            },
            "greedy_outer_loop": {
                "selected_indicators": ["x"],
                "chosen_window": 12,
                "final_global_auc": auc,
                "history": [],
            },
            "per_cohort": {"a": {"loco_auc": 0.6, "ece": 0.07}},
        }
    ).encode("utf-8")


# ---------- happy path -------------------------------------------------------


def test_happy_path_writes_rollup_to_dashboard_admin(fake_s3):
    bucket = "qgi-data-lake-771606957899"
    fake_s3.sub_prefixes_by_prefix["ml-results/"] = [
        "ml-results/recipe_a/",
        "ml-results/recipe_b/",
        "ml-results/_archive/",  # _archive must be skipped
    ]
    _put_summary(fake_s3, bucket, "ml-results/recipe_a/f-ml-1-poc-summary.json", recipe_id="recipe_a")
    _put_summary(fake_s3, bucket, "ml-results/recipe_b/f-ml-1-poc-summary.json", recipe_id="recipe_b")
    fake_s3.sub_prefixes_by_prefix["ml-results/_archive/"] = ["ml-results/_archive/recipe_a-2026-Q1-W1/"]
    _put_summary(
        fake_s3,
        bucket,
        "ml-results/_archive/recipe_a-2026-Q1-W1/f-ml-1-poc-summary.json",
        recipe_id="recipe_a",
        filed="2026-04-15T09:00:00Z",
    )
    out = lf.lambda_handler({"s3_bucket": bucket, "current_vintage_id": "2026-Q2-W2"}, None)
    assert out["status"] == "ok"
    assert out["rollup_s3_uri"] == f"s3://{bucket}/dashboard/admin/te-vintage-rollup.json"
    assert out["n_recipes"] == 2
    # recipe_a has BOTH a current and an archived row; recipe_b has only the current
    assert out["n_vintages_total"] == 3


def test_archive_subprefix_is_NOT_treated_as_current_recipe(fake_s3):
    """A common failure: the _archive sub-prefix would be enumerated as if it were a
    recipe directory. The handler must filter it out before reading."""
    bucket = "b"
    fake_s3.sub_prefixes_by_prefix["ml-results/"] = ["ml-results/_archive/"]
    out = lf.lambda_handler({"s3_bucket": bucket}, None)
    assert out["n_recipes"] == 0  # _archive correctly skipped from the current pass


def test_archive_subprefix_recipe_id_resolves_from_summary_field(fake_s3):
    """Archive sub-prefix name is the vintage_id; the recipe_id comes from the summary
    file's own `recipe_id` field — NOT from parsing the sub-prefix string."""
    bucket = "b"
    fake_s3.sub_prefixes_by_prefix["ml-results/"] = []
    fake_s3.sub_prefixes_by_prefix["ml-results/_archive/"] = [
        "ml-results/_archive/foreign_intervention-precanary-eval2021/"
    ]
    _put_summary(
        fake_s3,
        bucket,
        "ml-results/_archive/foreign_intervention-precanary-eval2021/f-ml-1-poc-summary.json",
        recipe_id="foreign_intervention",
        filed="2021-06-01T00:00:00Z",
    )
    lf.lambda_handler({"s3_bucket": bucket}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    # recipe_id is "foreign_intervention" (from summary), NOT "foreign_intervention-precanary-eval2021"
    assert "foreign_intervention" in body["recipes"]
    # vintage_id is the FULL archive sub-prefix string
    assert (
        body["recipes"]["foreign_intervention"]["vintages"][0]["vintage_id"]
        == "foreign_intervention-precanary-eval2021"
    )


def test_missing_summary_in_subprefix_is_skipped_no_crash(fake_s3):
    bucket = "b"
    fake_s3.sub_prefixes_by_prefix["ml-results/"] = ["ml-results/recipe_a/"]
    # NO summary file under recipe_a/
    out = lf.lambda_handler({"s3_bucket": bucket}, None)
    assert out["status"] == "ok" and out["n_recipes"] == 0


def test_malformed_summary_surfaces_in_warnings(fake_s3):
    bucket = "b"
    fake_s3.sub_prefixes_by_prefix["ml-results/"] = ["ml-results/recipe_a/"]
    fake_s3.objs[(bucket, "ml-results/recipe_a/f-ml-1-poc-summary.json")] = b"not json"
    out = lf.lambda_handler({"s3_bucket": bucket}, None)
    assert out["status"] == "ok"
    assert any("recipe_a" in w and "read error" in w for w in out["warnings"])


def test_empty_prefix_returns_empty_rollup(fake_s3):
    bucket = "b"
    out = lf.lambda_handler({"s3_bucket": bucket}, None)
    assert out["status"] == "ok"
    assert out["n_recipes"] == 0 and out["n_vintages_total"] == 0
    # An empty rollup was STILL written so the dashboard always has a file to read
    assert len(fake_s3.put_calls) == 1


def test_event_missing_s3_bucket_raises(fake_s3):
    with pytest.raises(ValueError, match="s3_bucket"):
        lf.lambda_handler({}, None)


def test_current_vintage_id_falls_back_to_execution_name_then_current(fake_s3):
    bucket = "b"
    out1 = lf.lambda_handler({"s3_bucket": bucket, "execution_name": "wave3-foo"}, None)
    assert out1["current_vintage_id"] == "wave3-foo"
    out2 = lf.lambda_handler({"s3_bucket": bucket}, None)
    assert out2["current_vintage_id"] == "current"


def test_idempotent_on_same_vintage_id_no_duplicate_rows(fake_s3):
    """If a current-vintage recipe and an archived row share the same vintage_id,
    the merge replaces — never duplicates. (Defensive — wouldn't usually occur in
    production since archive vintage_ids include their archive-prefix names.)"""
    bucket = "b"
    # Stage: current vintage uses "v1"; an archived sub with name "v1" too.
    fake_s3.sub_prefixes_by_prefix["ml-results/"] = ["ml-results/recipe_a/"]
    _put_summary(fake_s3, bucket, "ml-results/recipe_a/f-ml-1-poc-summary.json", recipe_id="recipe_a", auc=0.7)
    fake_s3.sub_prefixes_by_prefix["ml-results/_archive/"] = ["ml-results/_archive/v1/"]
    _put_summary(fake_s3, bucket, "ml-results/_archive/v1/f-ml-1-poc-summary.json", recipe_id="recipe_a", auc=0.8)
    out = lf.lambda_handler({"s3_bucket": bucket, "current_vintage_id": "v1"}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    assert out["n_vintages_total"] == 1  # one vintage_id v1, archive replaced current
    assert body["recipes"]["recipe_a"]["vintages"][0]["loco_auc"] == 0.8  # archive won (last write)


def test_archive_summary_without_recipe_id_falls_back_to_full_subprefix_NOT_split(fake_s3):
    """QA PR#45 BLOCKER fix: a legacy archive summary lacking `recipe_id` must
    fall back to the FULL archive sub-prefix (unique, auditable), NEVER to
    `sub.split('-')[0]` which silently mis-classifies on sub-prefixes that contain
    a hyphen not at the recipe-id boundary. The warning must surface the gap."""
    bucket = "b"
    fake_s3.sub_prefixes_by_prefix["ml-results/"] = []
    fake_s3.sub_prefixes_by_prefix["ml-results/_archive/"] = ["ml-results/_archive/bilateral_treaty-pre-canary-2025Q4/"]
    # Summary without recipe_id field
    fake_s3.objs[(bucket, "ml-results/_archive/bilateral_treaty-pre-canary-2025Q4/f-ml-1-poc-summary.json")] = (
        json.dumps(
            {
                "verdict": "HARD_FAIL",
                "filed": "2025-12-15T00:00:00Z",
                "global_loco": {"auc": 0.65, "ci95_lo": 0.6, "ci95_hi": 0.7},
                "coverage_audit": {
                    "n_pos_total": 100,
                    "n_pos_survive": 80,
                    "n_countries_survive": 20,
                    "pos_coverage": 0.8,
                    "coverage_pass": True,
                },
                "greedy_outer_loop": {
                    "selected_indicators": ["x"],
                    "chosen_window": 12,
                    "final_global_auc": 0.65,
                    "history": [],
                },
                "per_cohort": {},
            }
        ).encode("utf-8")
    )
    out = lf.lambda_handler({"s3_bucket": bucket}, None)
    body = json.loads(fake_s3.put_calls[-1][2].decode("utf-8"))
    # rid is the FULL sub-prefix (not "bilateral_treaty" — that would be the buggy
    # split fragment for a recipe that's actually labeled differently in production)
    assert "bilateral_treaty-pre-canary-2025Q4" in body["recipes"]
    assert "bilateral_treaty" not in body["recipes"]
    assert any("missing recipe_id" in w for w in out["warnings"])


def test_paginator_aggregates_across_multiple_pages(monkeypatch):
    """FU2 per QA PR#45: protect multi-page paginator correctness. The
    production paginator yields N pages; a regression that takes only the first
    page would silently miss late-alphabet recipes. Build a 2-page fake."""
    bucket = "b"

    class _MultiPageS3:
        def __init__(self):
            self.objs = {}
            self.put_calls = []

        def get_object(self, *, Bucket, Key):
            if (Bucket, Key) not in self.objs:
                raise ClientError({"Error": {"Code": "NoSuchKey", "Message": ""}}, "GetObject")
            return {"Body": BytesIO(self.objs[(Bucket, Key)])}

        def put_object(self, *, Bucket, Key, Body, ContentType="application/octet-stream"):
            self.put_calls.append((Bucket, Key, Body))
            return {"ETag": '"fake"'}

        def get_paginator(self, name):
            class _P:
                def paginate(self, *, Bucket, Prefix, Delimiter):
                    if Prefix == "ml-results/":
                        yield {"CommonPrefixes": [{"Prefix": "ml-results/alpha/"}]}
                        yield {"CommonPrefixes": [{"Prefix": "ml-results/zeta/"}]}
                    else:
                        yield {"CommonPrefixes": []}

            return _P()

    s = _MultiPageS3()
    monkeypatch.setattr(lf, "_s3", lambda: s)
    _put_summary(s, bucket, "ml-results/alpha/f-ml-1-poc-summary.json", recipe_id="alpha")
    _put_summary(s, bucket, "ml-results/zeta/f-ml-1-poc-summary.json", recipe_id="zeta")
    out = lf.lambda_handler({"s3_bucket": bucket}, None)
    # Both recipes must surface — a buggy `pages[0]` would drop zeta
    assert out["n_recipes"] == 2
    body = json.loads(s.put_calls[-1][2].decode("utf-8"))
    assert {"alpha", "zeta"} <= set(body["recipes"])


def test_writes_to_dashboard_admin_NEVER_to_ml_results(fake_s3):
    """Condition: the rollup is a derived dashboard artifact — never written into the
    ml-results prefix where it could be mistaken for a walk output."""
    bucket = "b"
    out = lf.lambda_handler({"s3_bucket": bucket}, None)
    written_keys = [k for _, k, _ in fake_s3.put_calls]
    assert written_keys == [lf._ROLLUP_OUTPUT_KEY]
    assert not any(k.startswith("ml-results/") for k in written_keys)
