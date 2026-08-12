"""Tests for `scripts/compute_d5_per_recipe_ahi.py`.

Locks the per-recipe AHI partitioning contract:
  1. Aggregate AHI re-computed from D5 predictions matches the cited
     value in `d5-batch-walk-verdict.md` (0.3218) within 0.001 tolerance.
  2. Per-recipe partitioning preserves aggregate (sum of n_evaluable
     across recipes equals aggregate n_evaluable; mass-balance check).
  3. Each recipe present in the anchor battery surfaces in the partition
     (or has all cases excluded; never silently dropped).
  4. JSON output schema is stable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from compute_d5_per_recipe_ahi import (  # noqa: E402
    CITED_AGGREGATE_AHI,
    SANITY_TOLERANCE,
    compute_per_recipe_metrics,
    evaluate_d5_anchors,
    main,
    partition_anchor_results_by_recipe,
)
from validate_ml_model import compute_anchor_drift_metrics  # noqa: E402

QGI_DATA_REF = REPO_ROOT.parent / "qgi-data" / "reference"
D5_PREDICTIONS_PATH = QGI_DATA_REF / "d5-d7-beta-validation-results-2026-05-07.json"
ANCHORS_PATH = QGI_DATA_REF / "anchor-case-battery.json"


@pytest.fixture(scope="module")
def d5_anchor_results():
    """Module-scoped fixture: evaluate D5 predictions against the anchor
    battery once and reuse the result across tests."""
    if not D5_PREDICTIONS_PATH.exists():
        pytest.skip(f"D5 predictions JSON not found at {D5_PREDICTIONS_PATH}")
    if not ANCHORS_PATH.exists():
        pytest.skip(f"Anchor battery JSON not found at {ANCHORS_PATH}")
    with D5_PREDICTIONS_PATH.open("r", encoding="utf-8") as f:
        predictions_payload = json.load(f)
    with ANCHORS_PATH.open("r", encoding="utf-8") as f:
        anchor_battery = json.load(f)
    predictions = predictions_payload.get("predictions", [])
    return evaluate_d5_anchors(predictions, anchor_battery)


def test_aggregate_ahi_matches_cited_value(d5_anchor_results):
    """Re-computed aggregate AHI must match d5-batch-walk-verdict.md
    line 58 cited value (0.3218) within SANITY_TOLERANCE (0.001).

    This is the canary: any divergence here signals either
    (a) the anchor evaluation code changed semantics, or
    (b) the predictions JSON was regenerated, or
    (c) the cited value in d5-batch-walk-verdict.md is wrong.
    """
    aggregate = compute_anchor_drift_metrics(d5_anchor_results)
    delta = abs(aggregate["ahi"] - CITED_AGGREGATE_AHI)
    assert delta <= SANITY_TOLERANCE, (
        f"Aggregate AHI {aggregate['ahi']:.6f} diverges from cited "
        f"{CITED_AGGREGATE_AHI} by {delta:.6f} > {SANITY_TOLERANCE}. "
        f"Either the anchor evaluation semantics changed or the cited "
        f"value in d5-batch-walk-verdict.md is stale."
    )


def test_per_recipe_partition_mass_balance(d5_anchor_results):
    """Sum of n_evaluable across all recipe groups must equal the
    aggregate n_evaluable. Catches silent drops in the partitioning
    logic (e.g., a case being assigned to None recipe and discarded).
    """
    aggregate = compute_anchor_drift_metrics(d5_anchor_results)
    per_recipe = compute_per_recipe_metrics(d5_anchor_results)
    sum_evaluable = sum(m["n_evaluable"] for m in per_recipe.values())
    assert sum_evaluable == aggregate["n_evaluable"], (
        f"Mass-balance violated: sum of per-recipe n_evaluable = "
        f"{sum_evaluable}; aggregate n_evaluable = "
        f"{aggregate['n_evaluable']}. Some cases are being lost in "
        f"partitioning."
    )


def test_per_recipe_partition_includes_recipes_with_zero_evaluable(d5_anchor_results):
    """Recipes that appear in the anchor battery but whose cases are
    all SKIPPED/DEFERRED/NYI must still surface in the partition with
    n_evaluable=0, NOT silently dropped. This preserves Lloyd's-style
    transparency: a recipe's absence from the per-recipe table is
    informative only if it's truly never an anchor target.
    """
    per_recipe = compute_per_recipe_metrics(d5_anchor_results)
    # Every recipe in the active anchor list (with `recipe` field set
    # to a non-empty string) must appear in per_recipe. The partition
    # function uses `case.get("recipe") or "__unrecipe__"` (truthy
    # check) which routes BOTH None AND empty-string into the
    # synthetic key. To match that semantics here we use the same
    # truthy check so empty-string recipes (if any ever appear) don't
    # falsely trip the "silent drop bug" assertion.
    active = d5_anchor_results["active"]
    recipes_with_field = {
        c.get("recipe") for c in active if c.get("recipe")  # truthy
    }
    for r in recipes_with_field:
        assert r in per_recipe, (
            f"Recipe {r!r} appears in active anchors but is missing from "
            f"the per-recipe partition. Silent drop bug."
        )


def test_partition_groups_by_recipe_field(d5_anchor_results):
    """Each case in a recipe's group must have that recipe field
    (sanity check on partition correctness)."""
    partitioned = partition_anchor_results_by_recipe(d5_anchor_results)
    for recipe, subset in partitioned.items():
        if recipe == "__unrecipe__":
            # Synthetic key for cases without a recipe field (sentinels)
            for case in subset["active"]:
                assert case.get("recipe") is None or case.get("recipe") == "", (
                    f"Case in __unrecipe__ group has recipe={case.get('recipe')!r}"
                )
        else:
            for case in subset["active"]:
                assert case.get("recipe") == recipe, (
                    f"Case in {recipe!r} group has recipe="
                    f"{case.get('recipe')!r}"
                )


def test_per_recipe_metrics_schema(d5_anchor_results):
    """Each per-recipe entry has the required fields with expected
    types. Locks downstream consumer contract (Stage 5 tear-sheets,
    Majles agenda doc, future automated dashboards)."""
    per_recipe = compute_per_recipe_metrics(d5_anchor_results)
    assert len(per_recipe) >= 1, "Expected at least one recipe partition"
    for recipe, m in per_recipe.items():
        assert isinstance(recipe, str)
        assert "ads" in m
        assert "ahr" in m
        assert "ahi" in m
        assert "n_evaluable" in m
        assert "n_excluded_non_evaluable" in m
        assert "per_case_drifts" in m
        assert isinstance(m["n_evaluable"], int)
        assert isinstance(m["n_excluded_non_evaluable"], int)
        if m["n_evaluable"] > 0:
            # ads/ahr/ahi finite when evaluable
            for k in ("ads", "ahr", "ahi"):
                v = m[k]
                assert isinstance(v, float)
                # Range check: each is in [0, 1]
                assert 0.0 <= v <= 1.0, (
                    f"Recipe {recipe!r} {k}={v} out of [0, 1] range"
                )


def test_main_writes_json_and_md(tmp_path):
    """End-to-end CLI test: --output-json + --output-md produce
    well-formed files; aggregate sanity check passes (exit 0)."""
    if not D5_PREDICTIONS_PATH.exists() or not ANCHORS_PATH.exists():
        pytest.skip("Required input JSONs not available")
    out_json = tmp_path / "per_recipe_ahi.json"
    out_md = tmp_path / "per_recipe_ahi.md"
    exit_code = main([
        "--predictions", str(D5_PREDICTIONS_PATH),
        "--anchors", str(ANCHORS_PATH),
        "--output-json", str(out_json),
        "--output-md", str(out_md),
    ])
    assert exit_code == 0, (
        "Sanity check failed: aggregate AHI does not match cited value"
    )
    assert out_json.exists()
    assert out_md.exists()
    with out_json.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["schema_version"] == 1
    assert "aggregate" in payload
    assert "per_recipe" in payload
    assert "sanity_check" in payload
    assert payload["sanity_check"]["passes"] is True
    md_content = out_md.read_text(encoding="utf-8")
    assert "D5 walk — per-recipe anchor health metrics" in md_content
    assert "Aggregate AHI" in md_content
    assert "Sanity check" in md_content


def test_synthetic_partition_metrics():
    """Pure-Python fixture: build a small synthetic anchor_results dict
    with known per-recipe drift values; verify the partition computes
    each recipe's AHI correctly with no dependency on the real D5
    predictions."""
    synthetic = {
        "active": [
            # Recipe "a": 2 anchors, both PASS (drift=0) → AHI = 1.0
            {
                "case_id": 1, "recipe": "a", "status": "PASS",
                "observed_percentile": 0.5,
                "expected_rank_band": [0.4, 0.6],
            },
            {
                "case_id": 2, "recipe": "a", "status": "PASS",
                "observed_percentile": 0.5,
                "expected_rank_band": [0.4, 0.6],
            },
            # Recipe "b": 1 anchor PASS (drift=0), 1 anchor FAIL (drift=0.2)
            # → ADS = 0.1, AHR = 0.5, AHI = 0.5 × 0.9 = 0.45
            {
                "case_id": 3, "recipe": "b", "status": "PASS",
                "observed_percentile": 0.5,
                "expected_rank_band": [0.4, 0.6],
            },
            {
                "case_id": 4, "recipe": "b", "status": "FAIL",
                "observed_percentile": 0.8,
                "expected_rank_band": [0.4, 0.6],
            },
            # Recipe "c": 1 SKIPPED → n_evaluable = 0 → metrics undefined
            {
                "case_id": 5, "recipe": "c", "status": "SKIPPED",
                "reason": "no predictions",
            },
        ]
    }
    per_recipe = compute_per_recipe_metrics(synthetic)
    assert "a" in per_recipe
    assert "b" in per_recipe
    assert "c" in per_recipe
    # Recipe a: perfect
    assert per_recipe["a"]["n_evaluable"] == 2
    assert per_recipe["a"]["ahi"] == pytest.approx(1.0, abs=1e-9)
    assert per_recipe["a"]["ahr"] == pytest.approx(1.0, abs=1e-9)
    assert per_recipe["a"]["ads"] == pytest.approx(0.0, abs=1e-9)
    # Recipe b: AHR=0.5, ADS=0.1, AHI=0.45
    assert per_recipe["b"]["n_evaluable"] == 2
    assert per_recipe["b"]["ahr"] == pytest.approx(0.5, abs=1e-9)
    assert per_recipe["b"]["ads"] == pytest.approx(0.1, abs=1e-9)
    assert per_recipe["b"]["ahi"] == pytest.approx(0.45, abs=1e-9)
    # Recipe c: skipped → n_evaluable=0
    assert per_recipe["c"]["n_evaluable"] == 0
    assert per_recipe["c"]["n_excluded_non_evaluable"] == 1
