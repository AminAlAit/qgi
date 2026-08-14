"""Unit tests for diff_walk_summaries.py — §2.5 BIT-IDENTITY canary diff harness.

Covers:
  - PASS case (identical summaries)
  - FAIL case (one scalar field differs)
  - Missing-field handling (key absent in one summary → FAIL, not crash)
  - S3 URI parsing (mocked boto3 — no real AWS calls)
  - Exit-code contract (0=PASS, 1=FAIL)
  - History length mismatch
  - Per-cohort divergence
  - List-field order sensitivity
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import diff_walk_summaries as dws


# ---------------------------------------------------------------------------
# Minimal realistic summary fixture
# ---------------------------------------------------------------------------

def _make_summary(
    verdict: str = "HARD_FAIL",
    chosen_window: int = 18,
    final_global_auc: float = 0.7123,
    selected_indicators: list[str] | None = None,
    ci95_lo: float = 0.6811,
    ci95_hi: float = 0.7435,
    n_pos_survive: int = 87,
    n_countries_survive: int = 22,
    pos_coverage: float = 0.832,
    neg_coverage: float = 0.941,
    top_n_indicators: list[str] | None = None,
    cohort_loco: dict[str, float | None] | None = None,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Build a minimal but structurally complete f-ml-1-poc-summary dict."""
    if selected_indicators is None:
        selected_indicators = ["RQ.EST", "v2pepwrgen", "v2stfisccap"]
    if top_n_indicators is None:
        top_n_indicators = ["RQ.EST", "v2pepwrgen", "v2stfisccap", "v2elintmon"]
    if cohort_loco is None:
        cohort_loco = {
            "fragile-state": 0.6912,
            "mid-tier": 0.7034,
            "stable-democracy": 0.6500,
        }
    if history is None:
        history = [
            {
                "step": 1,
                "candidate": "RQ.EST",
                "window": 18,
                "auc": 0.6800,
                "lift_over_previous": 0.1800,
                "selected_after": ["RQ.EST"],
            },
            {
                "step": 2,
                "candidate": "v2pepwrgen",
                "window": 18,
                "auc": 0.7123,
                "lift_over_previous": 0.0323,
                "selected_after": ["RQ.EST", "v2pepwrgen"],
            },
        ]
    return {
        "recipe_id": "technology_breakthrough",
        "verdict": verdict,
        # Top-level §2.5 invariants (QA PR review FU-F3): present in the real emit.
        "architecture": "XGBoost",
        "borderline_lock": False,
        "n_positives": 174,
        "n_negatives": 522,
        "temporal_confound_auc": 0.5123,
        "global_loco": {
            "auc": final_global_auc,
            "ci80_lo": 0.6950,
            "ci80_hi": 0.7290,
            "ci95_lo": ci95_lo,
            "ci95_hi": ci95_hi,
            "n_bootstrap": 2000,
            "method": "bca_bootstrap",
        },
        "coverage_audit": {
            "n_pos_total": 174,
            "n_pos_survive": n_pos_survive,
            "n_neg_total": 522,
            "n_neg_survive": 491,
            "pos_coverage": pos_coverage,
            "neg_coverage": neg_coverage,
            "n_countries_survive": n_countries_survive,
            "coverage_pass": True,
        },
        "per_cohort": {
            cohort: {
                "n": 40,
                "loco_auc": loco_auc,
                "ece": 0.07,
                "low_confidence": False,
            }
            for cohort, loco_auc in cohort_loco.items()
        },
        "greedy_outer_loop": {
            "selected_indicators": selected_indicators,
            "chosen_window": chosen_window,
            "final_global_auc": final_global_auc,
            "history": history,
            "early_abort_floor_unreachable": False,
        },
        "univariate_screen": {
            "method": "LR, 10y window, ranked by global LOCO-AUC",
            "n_candidates_evaluated": 120,
            "top_n_kept": 40,
            "top_n_indicators": top_n_indicators,
        },
    }


# ---------------------------------------------------------------------------
# PASS case
# ---------------------------------------------------------------------------

class TestPassCase:
    def test_identical_summaries_pass(self):
        s = _make_summary()
        result = dws.compare_summaries(s, copy.deepcopy(s))
        assert result["verdict"] == "BIT_IDENTICAL_PASS"
        assert result["fail_count"] == 0

    def test_pass_has_correct_pass_count(self):
        s = _make_summary()
        result = dws.compare_summaries(s, copy.deepcopy(s))
        # Every non-absent field should be PASS
        assert result["pass_count"] > 0
        fail_rows = [r for r in result["rows"] if r["status"] == "FAIL"]
        assert fail_rows == []


# ---------------------------------------------------------------------------
# FAIL cases — single field difference
# ---------------------------------------------------------------------------

class TestFailCases:
    def test_verdict_divergence_fails(self):
        baseline = _make_summary(verdict="HARD_FAIL")
        candidate = _make_summary(verdict="LOCK")
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fields = [r["field"] for r in result["divergences"]]
        assert "verdict" in fields

    def test_chosen_window_divergence_fails(self):
        baseline = _make_summary(chosen_window=18)
        candidate = _make_summary(chosen_window=21)
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fields = [r["field"] for r in result["divergences"]]
        assert "greedy_outer_loop.chosen_window" in fields

    def test_final_global_auc_divergence_fails(self):
        baseline = _make_summary(final_global_auc=0.7123)
        candidate = _make_summary(final_global_auc=0.7124)
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fields = [r["field"] for r in result["divergences"]]
        assert "greedy_outer_loop.final_global_auc" in fields

    def test_ci95_lo_divergence_fails(self):
        baseline = _make_summary(ci95_lo=0.6811)
        candidate = _make_summary(ci95_lo=0.6812)
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fields = [r["field"] for r in result["divergences"]]
        assert "global_loco.ci95_lo" in fields

    def test_pos_coverage_divergence_fails(self):
        baseline = _make_summary(pos_coverage=0.832)
        candidate = _make_summary(pos_coverage=0.830)
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fields = [r["field"] for r in result["divergences"]]
        assert "coverage_audit.pos_coverage" in fields

    def test_selected_indicators_order_divergence_fails(self):
        """List comparison is order-sensitive per §2.5."""
        baseline = _make_summary(selected_indicators=["RQ.EST", "v2pepwrgen"])
        candidate = _make_summary(selected_indicators=["v2pepwrgen", "RQ.EST"])
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fields = [r["field"] for r in result["divergences"]]
        assert "greedy_outer_loop.selected_indicators" in fields

    def test_history_auc_divergence_fails(self):
        h_baseline = [
            {"step": 1, "candidate": "RQ.EST", "window": 18, "auc": 0.6800, "lift_over_previous": 0.18},
        ]
        h_candidate = [
            {"step": 1, "candidate": "RQ.EST", "window": 18, "auc": 0.6801, "lift_over_previous": 0.18},
        ]
        baseline = _make_summary(history=h_baseline)
        candidate = _make_summary(history=h_candidate)
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        # The auc field at history[0] should be flagged
        fields = [r["field"] for r in result["divergences"]]
        assert any("history" in f and "auc" in f for f in fields)

    def test_history_length_divergence_fails(self):
        h_base = [{"step": 1, "candidate": "A", "window": 10, "auc": 0.6, "lift_over_previous": 0.1}]
        h_cand = [
            {"step": 1, "candidate": "A", "window": 10, "auc": 0.6, "lift_over_previous": 0.1},
            {"step": 2, "candidate": "B", "window": 10, "auc": 0.62, "lift_over_previous": 0.02},
        ]
        baseline = _make_summary(history=h_base)
        candidate = _make_summary(history=h_cand)
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"

    def test_per_cohort_divergence_fails(self):
        baseline = _make_summary(
            cohort_loco={"fragile-state": 0.69, "mid-tier": 0.70, "stable-democracy": 0.65}
        )
        candidate = _make_summary(
            cohort_loco={"fragile-state": 0.69, "mid-tier": 0.71, "stable-democracy": 0.65}
        )
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fields = [r["field"] for r in result["divergences"]]
        assert any("mid-tier" in f for f in fields)


# ---------------------------------------------------------------------------
# Missing-field handling (should surface as FAIL, not raise)
# ---------------------------------------------------------------------------

class TestMissingFieldHandling:
    def test_missing_verdict_in_candidate_fails(self):
        baseline = _make_summary()
        candidate = copy.deepcopy(baseline)
        del candidate["verdict"]
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fail_fields = [r["field"] for r in result["divergences"]]
        assert "verdict" in fail_fields

    def test_missing_verdict_in_baseline_fails(self):
        baseline = _make_summary()
        del baseline["verdict"]
        candidate = _make_summary()
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fail_fields = [r["field"] for r in result["divergences"]]
        assert "verdict" in fail_fields

    def test_missing_in_both_is_both_absent_not_fail(self):
        """A key absent from BOTH summaries is BOTH_ABSENT, not a FAIL.

        This matters for optional fields like per_cohort when the recipe has
        too few cohort samples to populate the block.
        """
        baseline = _make_summary()
        candidate = _make_summary()
        # Remove a deep optional key from both
        del baseline["global_loco"]["ci95_lo"]
        del candidate["global_loco"]["ci95_lo"]
        result = dws.compare_summaries(baseline, candidate)
        both_absent = [r for r in result["rows"] if r["status"] == "BOTH_ABSENT"
                       and r["field"] == "global_loco.ci95_lo"]
        assert len(both_absent) == 1
        # Should not count as a FAIL
        fail_fields = [r["field"] for r in result["divergences"]]
        assert "global_loco.ci95_lo" not in fail_fields

    def test_missing_coverage_audit_in_candidate_fails(self):
        baseline = _make_summary()
        candidate = copy.deepcopy(baseline)
        del candidate["coverage_audit"]
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        # At least one coverage sub-field should be in divergences
        fail_fields = [r["field"] for r in result["divergences"]]
        assert any("coverage_audit" in f for f in fail_fields)

    def test_missing_history_in_one_summary_fails(self):
        baseline = _make_summary()
        candidate = copy.deepcopy(baseline)
        del candidate["greedy_outer_loop"]["history"]
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"

    def test_missing_per_cohort_in_one_summary_fails(self):
        baseline = _make_summary()
        candidate = copy.deepcopy(baseline)
        del candidate["per_cohort"]
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"


# ---------------------------------------------------------------------------
# S3 URI parsing (pure — no network)
# ---------------------------------------------------------------------------

class TestS3UriParsing:
    def test_parse_simple_uri(self):
        bucket, key = dws._parse_s3_uri("s3://my-bucket/path/to/file.json")
        assert bucket == "my-bucket"
        assert key == "path/to/file.json"

    def test_parse_deep_prefix(self):
        bucket, key = dws._parse_s3_uri(
            "s3://qgi-data-lake-771606957899/ml-results/technology_breakthrough/"
            "canary-techbreak-20260528-022429/f-ml-1-poc-summary.json"
        )
        assert bucket == "qgi-data-lake-771606957899"
        assert key == (
            "ml-results/technology_breakthrough/"
            "canary-techbreak-20260528-022429/f-ml-1-poc-summary.json"
        )

    def test_load_s3_json_calls_boto3(self, monkeypatch):
        """Monkeypatch boto3.client to verify S3 get_object is called correctly."""
        expected = {"verdict": "HARD_FAIL", "recipe_id": "test"}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(expected).encode("utf-8")
        mock_response = {"Body": mock_body}
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = mock_response
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            result = dws._load_s3_json(
                "s3://qgi-data-lake-771606957899/ml-results/technology_breakthrough/"
                "canary-techbreak-20260528-022429/f-ml-1-poc-summary.json"
            )

        mock_boto3.client.assert_called_once_with("s3")
        mock_s3.get_object.assert_called_once_with(
            Bucket="qgi-data-lake-771606957899",
            Key=(
                "ml-results/technology_breakthrough/"
                "canary-techbreak-20260528-022429/f-ml-1-poc-summary.json"
            ),
        )
        assert result == expected

    def test_load_json_local_path(self, tmp_path):
        payload = {"verdict": "LOCK", "recipe_id": "test"}
        f = tmp_path / "summary.json"
        f.write_text(json.dumps(payload), encoding="utf-8")
        result = dws._load_json(str(f))
        assert result == payload

    def test_load_json_dispatches_to_s3_for_s3_uri(self, monkeypatch):
        expected = {"verdict": "HARD_FAIL"}
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(expected).encode("utf-8")
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            result = dws._load_json("s3://bucket/key.json")

        assert result == expected
        mock_boto3.client.assert_called_once_with("s3")


# ---------------------------------------------------------------------------
# Exit-code contract
# ---------------------------------------------------------------------------

class TestExitCode:
    def test_main_pass_returns_0(self, tmp_path):
        summary = _make_summary()
        baseline_path = tmp_path / "baseline.json"
        candidate_path = tmp_path / "candidate.json"
        baseline_path.write_text(json.dumps(summary), encoding="utf-8")
        candidate_path.write_text(json.dumps(copy.deepcopy(summary)), encoding="utf-8")

        rc = dws._main([
            "--baseline", str(baseline_path),
            "--candidate", str(candidate_path),
        ])
        assert rc == 0

    def test_main_fail_returns_1(self, tmp_path):
        baseline = _make_summary(verdict="HARD_FAIL")
        candidate = _make_summary(verdict="LOCK")
        baseline_path = tmp_path / "baseline.json"
        candidate_path = tmp_path / "candidate.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

        rc = dws._main([
            "--baseline", str(baseline_path),
            "--candidate", str(candidate_path),
        ])
        assert rc == 1

    def test_main_writes_json_out_on_fail(self, tmp_path):
        baseline = _make_summary(verdict="HARD_FAIL")
        candidate = _make_summary(verdict="LOCK")
        baseline_path = tmp_path / "baseline.json"
        candidate_path = tmp_path / "candidate.json"
        out_path = tmp_path / "result.json"
        baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

        rc = dws._main([
            "--baseline", str(baseline_path),
            "--candidate", str(candidate_path),
            "--out", str(out_path),
        ])
        assert rc == 1
        out = json.loads(out_path.read_text(encoding="utf-8"))
        assert out["verdict"] == "BIT_IDENTICAL_FAIL"
        assert len(out["divergences"]) >= 1

    def test_main_writes_json_out_on_pass(self, tmp_path):
        summary = _make_summary()
        baseline_path = tmp_path / "baseline.json"
        candidate_path = tmp_path / "candidate.json"
        out_path = tmp_path / "result.json"
        baseline_path.write_text(json.dumps(summary), encoding="utf-8")
        candidate_path.write_text(json.dumps(copy.deepcopy(summary)), encoding="utf-8")

        rc = dws._main([
            "--baseline", str(baseline_path),
            "--candidate", str(candidate_path),
            "--out", str(out_path),
        ])
        assert rc == 0
        out = json.loads(out_path.read_text(encoding="utf-8"))
        assert out["verdict"] == "BIT_IDENTICAL_PASS"
        assert out["divergences"] == []


# ---------------------------------------------------------------------------
# Markdown renderer sanity
# ---------------------------------------------------------------------------

class TestMarkdownRenderer:
    def test_pass_message_in_output(self):
        s = _make_summary()
        result = dws.compare_summaries(s, copy.deepcopy(s))
        md = dws.render_markdown(result)
        assert "BIT_IDENTICAL_PASS" in md
        assert "PASS" in md

    def test_fail_message_in_output(self):
        baseline = _make_summary(verdict="HARD_FAIL")
        candidate = _make_summary(verdict="LOCK")
        result = dws.compare_summaries(baseline, candidate)
        md = dws.render_markdown(result)
        assert "BIT_IDENTICAL_FAIL" in md
        assert "BLOCKED" in md


# ---------------------------------------------------------------------------
# QA PR review additions (BLOCKERS + FU coverage)
# ---------------------------------------------------------------------------

class TestEarlyAbortFlagDivergence:
    """BLOCKER-1: greedy_outer_loop.early_abort_floor_unreachable must be diffed —
    a walk that switches from greedy-completed to early-aborted (or vice-versa) on
    the same recipe is taking a STRUCTURALLY DIFFERENT path; selected_indicators
    and AUC are only meaningful in-context, and would not, on their own, catch
    this divergence reliably (e.g. an early-abort can leave a shorter selection
    that happens to match a tied tie-break)."""

    def test_early_abort_flag_flip_is_a_fail(self):
        baseline = _make_summary()
        baseline["greedy_outer_loop"]["early_abort_floor_unreachable"] = False
        candidate = copy.deepcopy(baseline)
        candidate["greedy_outer_loop"]["early_abort_floor_unreachable"] = True
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fails = [r["field"] for r in result["divergences"]]
        assert "greedy_outer_loop.early_abort_floor_unreachable" in fails

    def test_early_abort_flag_unchanged_is_pass(self):
        s = _make_summary()
        result = dws.compare_summaries(s, copy.deepcopy(s))
        assert result["verdict"] == "BIT_IDENTICAL_PASS"


class TestBothAbsentSurfacing:
    """BLOCKER-2: when both summaries lack a SCALAR_FIELDS key, the verdict is still
    PASS (no divergence to compare) BUT the operator MUST see the absent fields in
    the PASS banner — a silent skip would let waves fire when both runs stopped
    emitting a required key (driver regression masked by symmetric absence)."""

    def test_both_absent_appears_in_pass_banner(self):
        # Strip architecture from BOTH — it's in SCALAR_FIELDS now per FU-F3.
        baseline = _make_summary()
        del baseline["architecture"]
        candidate = copy.deepcopy(baseline)
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_PASS"
        assert result["both_absent_count"] >= 1
        md = dws.render_markdown(result)
        # The banner must explicitly list the absent fields for human acknowledgement.
        assert "absent in BOTH" in md
        assert "architecture" in md

    def test_no_both_absent_no_note_in_banner(self):
        # The default fixture provides ALL SCALAR_FIELDS — no BOTH_ABSENT, no NOTE.
        s = _make_summary()
        result = dws.compare_summaries(s, copy.deepcopy(s))
        assert result["both_absent_count"] == 0
        md = dws.render_markdown(result)
        assert "absent in BOTH" not in md


class TestSelectedAfterHistoryComparison:
    """F1 per QA PR review: history[i].selected_after must be diffed so a
    greedy-reduce-order regression that happens to land on the same terminal
    selection still surfaces as a per-step divergence."""

    def test_selected_after_divergence_at_step_fails(self):
        baseline = _make_summary()
        candidate = copy.deepcopy(baseline)
        # Same terminal selection but a swapped step-1 selected_after — caught only by F1.
        candidate["greedy_outer_loop"]["history"][0]["selected_after"] = ["DIFFERENT_PICK"]
        result = dws.compare_summaries(baseline, candidate)
        assert result["verdict"] == "BIT_IDENTICAL_FAIL"
        fails = [r["field"] for r in result["divergences"]]
        assert any("history[0].selected_after" in f for f in fails)


class TestS3ErrorClearMessage:
    """F2 per QA PR review: an S3 ClientError raised by get_object must surface
    as a clear SystemExit with the error code and a helpful message — NOT a raw
    botocore traceback. The exit code still must be non-zero (waves stay blocked).
    """

    def test_s3_no_such_key_raises_systemexit_with_clear_message(self):
        from botocore.exceptions import ClientError
        err = ClientError(
            error_response={"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
            operation_name="GetObject",
        )
        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = err
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_s3
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            with pytest.raises(SystemExit) as excinfo:
                dws._load_s3_json("s3://bucket/key/missing.json")
        msg = str(excinfo.value)
        assert "NoSuchKey" in msg
        assert "s3://bucket/key/missing.json" in msg
