"""Unit tests for vintage_rollup_core.py (#968 / FLEET-VINTAGE-ROLLUP).

The pure orchestrator that builds the cross-vintage rollup the Admin Dashboard's
trend section (#151 TE §B) renders. Tests pin: row extraction with full + partial
emit / cohort-median computation / merge idempotency on (recipe_id, vintage_id) /
chronological sort + tilde-after-digit tail behaviour."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lambdas" / "recipe-fleet-vintage-rollup"))
import vintage_rollup_core as core  # noqa: E402


# ---------- fixture helpers --------------------------------------------------


def _make_summary(
    *,
    verdict="HARD_FAIL",
    auc=0.72,
    filed="2026-05-28T11:00:00Z",
    selected=None,
    window=12,
    n_pos_total=174,
    n_pos_survive=120,
    history=None,
    cohort_aucs=None,
    panel_fp=None,
):
    if selected is None:
        selected = ["x", "y"]
    if history is None:
        history = [
            {"step": 1, "candidate": "x", "window": 12, "auc": 0.7, "lift_over_previous": 0.2, "selected_after": ["x"]}
        ]
    if cohort_aucs is None:
        cohort_aucs = [0.65, 0.70, 0.75]
    s = {
        "recipe_id": "demo_recipe",
        "verdict": verdict,
        "filed": filed,
        "n_positives": n_pos_total,
        "n_negatives": 522,
        "elapsed_seconds": 240.5,
        "architecture": "XGBoost",
        "borderline_lock": False,
        "temporal_confound_auc": 0.5,
        "global_loco": {
            "auc": auc,
            "ci95_lo": auc - 0.05,
            "ci95_hi": auc + 0.05,
            "ci80_lo": auc - 0.03,
            "ci80_hi": auc + 0.03,
        },
        "coverage_audit": {
            "n_pos_total": n_pos_total,
            "n_pos_survive": n_pos_survive,
            "n_neg_total": 522,
            "n_neg_survive": 491,
            "n_countries_survive": 22,
            "pos_coverage": n_pos_survive / n_pos_total,
            "coverage_pass": True,
        },
        "greedy_outer_loop": {
            "selected_indicators": selected,
            "chosen_window": window,
            "final_global_auc": auc,
            "early_abort_floor_unreachable": False,
            "history": history,
        },
        "per_cohort": {f"c{i}": {"loco_auc": a, "ece": 0.07} for i, a in enumerate(cohort_aucs)},
    }
    if panel_fp is not None:
        s["panel_fingerprint"] = panel_fp
    return s


# ---------- extract_vintage_row ----------------------------------------------


class TestExtractVintageRow:
    def test_full_emit_round_trips_every_field(self):
        s = _make_summary()
        row = core.extract_vintage_row(s, vintage_id="2026-Q2-W1")
        assert row["vintage_id"] == "2026-Q2-W1"
        assert row["walked_at_utc"] == "2026-05-28T11:00:00Z"
        assert row["verdict"] == "HARD_FAIL"
        assert row["loco_auc"] == 0.72
        assert row["ci95_lo"] == pytest.approx(0.67)
        assert row["ci95_hi"] == pytest.approx(0.77)
        assert row["selected_indicators"] == ["x", "y"]
        assert row["chosen_window"] == 12
        assert row["n_pos_total"] == 174
        assert row["n_pos_survive"] == 120
        assert row["elapsed_seconds"] == 240.5
        assert row["architecture"] == "XGBoost"
        assert row["per_cohort_median_loco_auc"] == 0.70  # middle of [0.65, 0.70, 0.75]
        assert len(row["indicator_lifts"]) == 1
        assert row["indicator_lifts"][0]["candidate"] == "x"

    def test_empty_summary_does_not_crash(self):
        row = core.extract_vintage_row({}, vintage_id="v0")
        assert row["vintage_id"] == "v0"
        assert row["walked_at_utc"] is None
        assert row["verdict"] is None
        assert row["loco_auc"] is None
        assert row["selected_indicators"] is None
        assert row["per_cohort_median_loco_auc"] is None
        assert row["indicator_lifts"] == []

    def test_cohort_median_even_count_averages_middle_two(self):
        s = _make_summary(cohort_aucs=[0.6, 0.7, 0.8, 0.9])
        row = core.extract_vintage_row(s, vintage_id="v")
        assert row["per_cohort_median_loco_auc"] == pytest.approx((0.7 + 0.8) / 2)

    def test_cohort_median_handles_none_loco_aucs_gracefully(self):
        s = _make_summary()
        s["per_cohort"] = {"a": {"loco_auc": None}, "b": {"loco_auc": 0.7}, "c": {"loco_auc": 0.8}}
        row = core.extract_vintage_row(s, vintage_id="v")
        assert row["per_cohort_median_loco_auc"] == pytest.approx(0.75)  # median of [0.7, 0.8]

    def test_cohort_median_all_none_yields_none(self):
        s = _make_summary()
        s["per_cohort"] = {"a": {"loco_auc": None}}
        row = core.extract_vintage_row(s, vintage_id="v")
        assert row["per_cohort_median_loco_auc"] is None

    def test_panel_fingerprint_round_trips_when_present(self):
        s = _make_summary(panel_fp="sha256:abcd")
        row = core.extract_vintage_row(s, vintage_id="v")
        assert row["panel_fingerprint"] == "sha256:abcd"

    def test_indicator_lifts_includes_selected_after_per_step(self):
        s = _make_summary(
            history=[
                {
                    "step": 1,
                    "candidate": "a",
                    "window": 12,
                    "auc": 0.7,
                    "lift_over_previous": 0.2,
                    "selected_after": ["a"],
                },
                {
                    "step": 2,
                    "candidate": "b",
                    "window": 12,
                    "auc": 0.75,
                    "lift_over_previous": 0.05,
                    "selected_after": ["a", "b"],
                },
            ]
        )
        row = core.extract_vintage_row(s, vintage_id="v")
        assert [h["selected_after"] for h in row["indicator_lifts"]] == [["a"], ["a", "b"]]


# ---------- merge_into_per_recipe (idempotency) ------------------------------


class TestMergeIntoPerRecipe:
    def test_appends_new_recipe(self):
        per = {}
        core.merge_into_per_recipe(per, "r1", {"vintage_id": "v1", "loco_auc": 0.7})
        assert "r1" in per and len(per["r1"]) == 1

    def test_appends_distinct_vintages_for_same_recipe(self):
        per = {}
        core.merge_into_per_recipe(per, "r1", {"vintage_id": "v1"})
        core.merge_into_per_recipe(per, "r1", {"vintage_id": "v2"})
        assert [r["vintage_id"] for r in per["r1"]] == ["v1", "v2"]

    def test_replaces_row_with_same_vintage_id(self):
        """Idempotency: a re-ingest of the same archive overwrites — never duplicates."""
        per = {}
        core.merge_into_per_recipe(per, "r1", {"vintage_id": "v1", "loco_auc": 0.7})
        core.merge_into_per_recipe(per, "r1", {"vintage_id": "v1", "loco_auc": 0.8})
        assert len(per["r1"]) == 1 and per["r1"][0]["loco_auc"] == 0.8


# ---------- build_rollup -----------------------------------------------------


class TestBuildRollup:
    def test_sorts_vintages_chronologically_by_walked_at(self):
        per = {
            "r1": [
                {"vintage_id": "v2", "walked_at_utc": "2026-05-28T12:00:00Z"},
                {"vintage_id": "v1", "walked_at_utc": "2026-05-27T10:00:00Z"},
            ]
        }
        out = core.build_rollup(per, current_vintage_id="v2", produced_at_utc="2026-05-29T00:00:00Z")
        assert [r["vintage_id"] for r in out["recipes"]["r1"]["vintages"]] == ["v1", "v2"]
        assert out["recipes"]["r1"]["latest_vintage_id"] == "v2"

    def test_missing_walked_at_sorts_last_via_tilde(self):
        """A vintage row without a walked_at_utc must NOT push above real timestamps —
        the tilde tail in the sort key keeps None at the end."""
        per = {
            "r1": [
                {"vintage_id": "v0", "walked_at_utc": None},
                {"vintage_id": "v1", "walked_at_utc": "2026-05-27T10:00:00Z"},
                {"vintage_id": "v2", "walked_at_utc": "2026-05-28T10:00:00Z"},
            ]
        }
        out = core.build_rollup(per, current_vintage_id="v2", produced_at_utc="...")
        assert [r["vintage_id"] for r in out["recipes"]["r1"]["vintages"]] == ["v1", "v2", "v0"]

    def test_top_level_counts_n_recipes_and_n_vintages_total(self):
        per = {"a": [{"vintage_id": "v1"}, {"vintage_id": "v2"}], "b": [{"vintage_id": "v1"}]}
        out = core.build_rollup(per, current_vintage_id="v2", produced_at_utc="...")
        assert out["n_recipes"] == 2
        assert out["n_vintages_total"] == 3

    def test_recipes_dict_is_sorted_by_recipe_id(self):
        per = {"zeta": [{"vintage_id": "v1"}], "alpha": [{"vintage_id": "v1"}]}
        out = core.build_rollup(per, current_vintage_id="v1", produced_at_utc="...")
        assert list(out["recipes"]) == ["alpha", "zeta"]

    def test_produced_at_and_current_vintage_round_trip(self):
        out = core.build_rollup({}, current_vintage_id="2026-Q2-W2", produced_at_utc="2026-05-29T01:00:00Z")
        assert out["produced_at_utc"] == "2026-05-29T01:00:00Z"
        assert out["current_vintage_id"] == "2026-Q2-W2"
        assert out["n_recipes"] == 0 and out["n_vintages_total"] == 0
