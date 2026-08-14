"""Unit tests for compute_sensitivity.py — sensitivity analysis (TE capability #5).

No IO, no panels, no AWS. All tests operate on synthetic in-memory data.

Coverage:
  - compute_country_sensitivity: marginal_points_per_unit = weight * 50 (from score map)
  - compute_country_sensitivity: headroom = weight * (1 - cosine) per spec
  - compute_country_sensitivity: headroom_points = headroom * 50 per spec
  - compute_country_sensitivity: ranked by headroom descending
  - compute_country_sensitivity: current_cosine matches per_indicator entry
  - compute_country_sensitivity: output schema per spec
  - compute_country_sensitivity: cosine = 1 → headroom = 0
  - compute_country_sensitivity: cosine = -1 → headroom = weight * 2 (maximum)
  - compute_all_sensitivity: keys match countries
  - compute_all_sensitivity: each country has n_indicators entries
  - build_output: schema includes recipe_id, eval_year, computed_at_utc,
      binding_provenance, m8_r5_note
  - build_output: m8_r5_note carries the IRONCLAD anti-causal firewall verbatim
  - build_output: binding_provenance cites te-new-capabilities-spec.md
  - CLI: parser accepts all documented flags + defaults
  - Integration: end-to-end with synthetic scores dict produces valid artifact
  - Anti-causal firewall: m8_r5_note must contain the exact spec §5 verbatim text

Per test-first rule (#373, feedback_test_first_rule.md):
tests written before implementation is run.
Mirror style of tests/test_compute_venn_abers_odds.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import compute_sensitivity as sens  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic data helpers — reuse same pattern as test_compute_driver.py
# ---------------------------------------------------------------------------


def _make_scores_dict(n_countries: int = 3, seed: int = 0) -> dict:
    """Minimal synthetic scores dict matching recipe-similarity-scores schema."""
    import random
    random.seed(seed)
    indicators = ["v2elintmon", "RQ.EST", "v2pepwrgen", "v2stfisccap"]
    shap = {
        "v2elintmon": 0.047,
        "RQ.EST": 0.511,
        "v2pepwrgen": 0.273,
        "v2stfisccap": 0.168,
    }
    countries = [f"Country_{i}" for i in range(n_countries)]
    scores = {}
    for c in countries:
        per_ind = {}
        total = 0.0
        for ind in indicators:
            cos = random.uniform(-0.5, 1.0)
            wc = shap[ind] * cos
            per_ind[ind] = {"cosine": cos, "weight": shap[ind], "weighted_contribution": wc}
            total += wc
        scores[c] = {
            "cosine_similarity_S": total,
            "risk_score": 100 * (total + 1) / 2,
            "zone": "HIGH" if total > 0.5 else "MODERATE",
            "per_indicator": per_ind,
        }
    return {
        "schema_version": 1,
        "recipe_id": "test_recipe",
        "evaluation_year": 2021,
        "selected_indicators": indicators,
        "chosen_window": 18,
        "shap_importance_normalized": shap,
        "n_countries_scored": n_countries,
        "scores": scores,
    }


def _make_simple_entry(weights: list[float], cosines: list[float]) -> dict:
    """Build a per_indicator dict from explicit weights and cosines."""
    assert len(weights) == len(cosines)
    indicators = [f"IND_{i}" for i in range(len(weights))]
    per_ind = {}
    total = 0.0
    for ind, w, cos in zip(indicators, weights, cosines):
        wc = w * cos
        per_ind[ind] = {"cosine": cos, "weight": w, "weighted_contribution": wc}
        total += wc
    return {
        "cosine_similarity_S": total,
        "risk_score": 100 * (total + 1) / 2,
        "zone": "HIGH",
        "per_indicator": per_ind,
    }


# ---------------------------------------------------------------------------
# Tests: compute_country_sensitivity — marginal_points_per_unit
# ---------------------------------------------------------------------------


def test_marginal_points_per_unit_formula():
    """marginal_points_per_unit = weight * 50 per spec.

    Score S in [-1, 1]; risk_score = 100*(S+1)/2.
    dS/d(cos_i) = w_i, so d(risk_score)/d(cos_i) = w_i * 50.
    """
    weights = [0.047, 0.511, 0.273, 0.168]
    cosines = [0.5, 0.8, -0.3, 0.9]
    entry = _make_simple_entry(weights, cosines)
    result = sens.compute_country_sensitivity(entry)
    for r in result:
        ind = r["indicator"]
        # Find the weight for this indicator
        w = entry["per_indicator"][ind]["weight"]
        expected_marg = w * 50.0
        assert abs(r["marginal_points_per_unit"] - expected_marg) < 1e-9, (
            f"{ind}: marginal_points_per_unit={r['marginal_points_per_unit']:.6f} "
            f"!= w*50={expected_marg:.6f}"
        )


def test_marginal_points_always_positive_for_positive_weights():
    """For non-negative SHAP weights, marginal_points_per_unit must always be >= 0."""
    weights = [0.047, 0.511, 0.273, 0.168]
    cosines = [0.5, 0.8, -0.3, 0.9]
    entry = _make_simple_entry(weights, cosines)
    result = sens.compute_country_sensitivity(entry)
    for r in result:
        assert r["marginal_points_per_unit"] >= 0, (
            f"{r['indicator']}: marginal_points_per_unit should be >=0 for positive weights"
        )


# ---------------------------------------------------------------------------
# Tests: compute_country_sensitivity — headroom
# ---------------------------------------------------------------------------


def test_headroom_formula():
    """headroom = weight * (1 - cosine) per spec §5."""
    weights = [0.047, 0.511, 0.273, 0.168]
    cosines = [0.5, 0.8, -0.3, 0.9]
    entry = _make_simple_entry(weights, cosines)
    result = sens.compute_country_sensitivity(entry)
    for r in result:
        ind = r["indicator"]
        w = entry["per_indicator"][ind]["weight"]
        cos = entry["per_indicator"][ind]["cosine"]
        expected_hr = w * (1.0 - cos)
        assert abs(r["headroom"] - expected_hr) < 1e-9, (
            f"{ind}: headroom={r['headroom']:.6f} != w*(1-cos)={expected_hr:.6f}"
        )


def test_headroom_zero_when_cosine_is_one():
    """cosine = 1 → headroom = 0 (no room to improve alignment)."""
    entry = _make_simple_entry([0.5], [1.0])
    result = sens.compute_country_sensitivity(entry)
    assert abs(result[0]["headroom"]) < 1e-9, (
        f"cosine=1 should give headroom=0, got {result[0]['headroom']}"
    )
    assert abs(result[0]["headroom_points"]) < 1e-9, (
        f"cosine=1 should give headroom_points=0, got {result[0]['headroom_points']}"
    )


def test_headroom_maximum_when_cosine_is_minus_one():
    """cosine = -1 → headroom = weight * 2 (maximum; fully anti-aligned)."""
    w = 0.4
    entry = _make_simple_entry([w], [-1.0])
    result = sens.compute_country_sensitivity(entry)
    expected_hr = w * 2.0
    assert abs(result[0]["headroom"] - expected_hr) < 1e-9, (
        f"cosine=-1 should give headroom=w*2={expected_hr:.4f}, got {result[0]['headroom']:.6f}"
    )


def test_headroom_points_formula():
    """headroom_points = headroom * 50 per spec §5."""
    weights = [0.047, 0.511, 0.273, 0.168]
    cosines = [0.5, 0.8, -0.3, 0.9]
    entry = _make_simple_entry(weights, cosines)
    result = sens.compute_country_sensitivity(entry)
    for r in result:
        expected_hp = r["headroom"] * 50.0
        assert abs(r["headroom_points"] - expected_hp) < 1e-9, (
            f"{r['indicator']}: headroom_points={r['headroom_points']:.6f} "
            f"!= headroom*50={expected_hp:.6f}"
        )


# ---------------------------------------------------------------------------
# Tests: compute_country_sensitivity — ranking
# ---------------------------------------------------------------------------


def test_ranked_by_headroom_descending():
    """Result must be ranked by headroom descending per spec §5."""
    weights = [0.047, 0.511, 0.273, 0.168]
    cosines = [0.5, 0.8, -0.3, 0.9]
    entry = _make_simple_entry(weights, cosines)
    result = sens.compute_country_sensitivity(entry)
    headrooms = [r["headroom"] for r in result]
    assert headrooms == sorted(headrooms, reverse=True), (
        f"Not sorted by headroom descending: {headrooms}"
    )


def test_current_cosine_matches_input():
    """current_cosine in output must match the per_indicator cosine."""
    weights = [0.3, 0.3, 0.2, 0.2]
    cosines = [0.7, -0.2, 0.4, 0.95]
    entry = _make_simple_entry(weights, cosines)
    result = sens.compute_country_sensitivity(entry)
    cosine_map = {r["indicator"]: r["current_cosine"] for r in result}
    for ind, cos in zip(["IND_0", "IND_1", "IND_2", "IND_3"], cosines):
        assert abs(cosine_map[ind] - cos) < 1e-9, (
            f"{ind}: current_cosine={cosine_map[ind]} != input cosine={cos}"
        )


# ---------------------------------------------------------------------------
# Tests: compute_country_sensitivity — output schema
# ---------------------------------------------------------------------------


def test_sensitivity_output_schema():
    """Each entry must contain the required fields per spec §5."""
    weights = [0.047, 0.511, 0.273, 0.168]
    cosines = [0.5, 0.8, -0.3, 0.9]
    entry = _make_simple_entry(weights, cosines)
    result = sens.compute_country_sensitivity(entry)
    required = {
        "indicator", "marginal_points_per_unit",
        "current_cosine", "headroom", "headroom_points",
    }
    for i, r in enumerate(result):
        assert required.issubset(set(r.keys())), (
            f"Entry {i} missing fields: {required - set(r.keys())}"
        )


def test_sensitivity_count_matches_indicators():
    """Result must contain one entry per indicator."""
    weights = [0.3, 0.3, 0.2, 0.2]
    cosines = [0.7, -0.2, 0.4, 0.95]
    entry = _make_simple_entry(weights, cosines)
    result = sens.compute_country_sensitivity(entry)
    assert len(result) == 4, f"Expected 4 entries, got {len(result)}"


# ---------------------------------------------------------------------------
# Tests: compute_all_sensitivity
# ---------------------------------------------------------------------------


def test_compute_all_sensitivity_keys_match_countries():
    """Output dict must have exactly the same country keys as scores dict."""
    data = _make_scores_dict(n_countries=5)
    result = sens.compute_all_sensitivity(data)
    assert set(result.keys()) == set(data["scores"].keys()), (
        "Output country keys must match input scores keys"
    )


def test_compute_all_sensitivity_each_country_full():
    """Each country's sensitivity list must have one entry per indicator."""
    data = _make_scores_dict(n_countries=4)
    n_ind = len(data["selected_indicators"])
    result = sens.compute_all_sensitivity(data)
    for country, entries in result.items():
        assert len(entries) == n_ind, (
            f"{country}: expected {n_ind} sensitivity entries, got {len(entries)}"
        )


def test_compute_all_sensitivity_is_sorted_by_headroom():
    """Each country's sensitivity list must be sorted by headroom descending."""
    data = _make_scores_dict(n_countries=3)
    result = sens.compute_all_sensitivity(data)
    for country, entries in result.items():
        headrooms = [e["headroom"] for e in entries]
        assert headrooms == sorted(headrooms, reverse=True), (
            f"{country}: sensitivity not sorted by headroom descending: {headrooms}"
        )


# ---------------------------------------------------------------------------
# Tests: build_output — artifact schema and honesty
# ---------------------------------------------------------------------------

# The IRONCLAD anti-causal m8_r5_note verbatim from spec §5:
REQUIRED_M8R5_NOTE = (
    "Describes how the similarity SCORE responds to changes in indicator ALIGNMENT. "
    "The model is discriminative, not causal — this is NOT a claim that changing "
    "the real-world indicator changes real-world risk."
)


def test_build_output_required_top_level_keys():
    """Artifact must have the required top-level keys per spec."""
    data = _make_scores_dict(n_countries=2)
    all_sens = sens.compute_all_sensitivity(data)
    artifact = sens.build_output(data, all_sens)
    required = {
        "recipe_id", "eval_year", "computed_at_utc",
        "binding_provenance", "m8_r5_note", "sensitivity",
    }
    assert required.issubset(set(artifact.keys())), (
        f"Missing top-level keys: {required - set(artifact.keys())}"
    )


def test_build_output_m8_r5_note_ironclad_verbatim():
    """m8_r5_note MUST carry the IRONCLAD anti-causal firewall text verbatim from spec §5.

    The spec says: 'Mandatory m8_r5_note: "Describes how the similarity SCORE
    responds to changes in indicator ALIGNMENT. The model is discriminative,
    not causal — this is NOT a claim that changing the real-world indicator
    changes real-world risk."'
    """
    data = _make_scores_dict(n_countries=2)
    all_sens = sens.compute_all_sensitivity(data)
    artifact = sens.build_output(data, all_sens)
    note = artifact["m8_r5_note"]
    # Check for the key discriminating phrases from the spec
    assert "discriminative, not causal" in note, (
        f"m8_r5_note must contain 'discriminative, not causal' (spec §5 verbatim). Got: {note!r}"
    )
    assert "NOT a claim" in note, (
        f"m8_r5_note must contain 'NOT a claim' (spec §5 verbatim). Got: {note!r}"
    )
    assert "SCORE" in note or "score" in note.lower(), (
        "m8_r5_note must reference the SCORE"
    )
    assert "ALIGNMENT" in note or "alignment" in note.lower(), (
        "m8_r5_note must reference indicator ALIGNMENT"
    )


def test_build_output_m8_r5_note_no_policy_advice():
    """HONESTY GUARD (review 2026-05-24): the anti-causal firewall note must
    (a) carry the explicit non-causal disclaimer, and (b) contain NO causal-
    directive phrasing. The previous form (`"should" not in note or "NOT" in note`)
    passed trivially because "NOT" is always present — it guarded nothing."""
    data = _make_scores_dict(n_countries=2)
    all_sens = sens.compute_all_sensitivity(data)
    artifact = sens.build_output(data, all_sens)
    note = artifact["m8_r5_note"].lower()
    # (a) the firewall disclaimer must be present (unconditional).
    assert "not causal" in note or "discriminative, not causal" in note, (
        "m8_r5_note must carry the explicit 'discriminative, not causal' disclaimer"
    )
    assert "not a claim" in note, (
        "m8_r5_note must explicitly state it is NOT a claim about real-world risk"
    )
    # (b) NO causal-directive phrasing, unconditionally (these must never appear).
    forbidden = [
        "should improve", "to lower risk", "to reduce risk", "to lower the risk",
        "to reduce the risk", "recommend", "in order to lower", "fix ", "improving",
    ]
    for phrase in forbidden:
        assert phrase not in note, (
            f"m8_r5_note contains causal-directive phrasing {phrase!r} — anti-causal firewall breached"
        )


def test_build_output_binding_provenance_cites_spec():
    """binding_provenance must cite te-new-capabilities-spec.md."""
    data = _make_scores_dict(n_countries=2)
    all_sens = sens.compute_all_sensitivity(data)
    artifact = sens.build_output(data, all_sens)
    prov = artifact["binding_provenance"]
    assert "te-new-capabilities-spec" in prov, (
        f"binding_provenance must cite te-new-capabilities-spec.md, got: {prov!r}"
    )


def test_build_output_recipe_id_and_eval_year():
    """recipe_id and eval_year must match input."""
    data = _make_scores_dict(n_countries=2)
    all_sens = sens.compute_all_sensitivity(data)
    artifact = sens.build_output(data, all_sens)
    assert artifact["recipe_id"] == data["recipe_id"]
    assert artifact["eval_year"] == data["evaluation_year"]


def test_build_output_computed_at_utc_parseable():
    """computed_at_utc must be a parseable ISO 8601 UTC timestamp."""
    from datetime import datetime
    data = _make_scores_dict(n_countries=2)
    all_sens = sens.compute_all_sensitivity(data)
    artifact = sens.build_output(data, all_sens)
    ts = artifact["computed_at_utc"]
    assert isinstance(ts, str) and len(ts) > 0
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.tzinfo is not None
    except ValueError as e:
        pytest.fail(f"computed_at_utc not ISO 8601: {ts!r} — {e}")


def test_build_output_sensitivity_contains_all_countries():
    """artifact['sensitivity'] must contain all countries."""
    data = _make_scores_dict(n_countries=3)
    all_sens = sens.compute_all_sensitivity(data)
    artifact = sens.build_output(data, all_sens)
    assert set(artifact["sensitivity"].keys()) == set(data["scores"].keys())


# ---------------------------------------------------------------------------
# Tests: CLI parser
# ---------------------------------------------------------------------------


def test_cli_parser_required_flags(tmp_path):
    """--scores-file and --output-dir are required."""
    parser = sens._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])  # missing required flags


def test_cli_parser_all_flags(tmp_path):
    """Parser must accept all documented flags without error."""
    parser = sens._build_parser()
    args = parser.parse_args([
        "--scores-file", str(tmp_path / "scores.json"),
        "--output-dir", str(tmp_path),
    ])
    assert args.scores_file == tmp_path / "scores.json"
    assert args.output_dir == tmp_path


# ---------------------------------------------------------------------------
# Tests: integration — end-to-end with synthetic real-recipe data
# ---------------------------------------------------------------------------


def test_integration_highest_headroom_country():
    """The most anti-aligned indicator must have the highest headroom."""
    # IND_1 has cosine = -0.8 and weight = 0.5 → headroom = 0.5 * 1.8 = 0.9 (largest)
    # IND_0 has cosine = 0.9 and weight = 0.3 → headroom = 0.3 * 0.1 = 0.03
    weights = [0.3, 0.5, 0.2]
    cosines = [0.9, -0.8, 0.5]
    entry = _make_simple_entry(weights, cosines)
    result = sens.compute_country_sensitivity(entry)
    # IND_1 should be first (highest headroom = 0.9)
    assert result[0]["indicator"] == "IND_1", (
        f"IND_1 should have highest headroom, got {result[0]['indicator']}"
    )
    expected_hr = 0.5 * (1 - (-0.8))
    assert abs(result[0]["headroom"] - expected_hr) < 1e-9


def test_integration_headroom_points_relationship():
    """headroom_points must be exactly 50 * headroom for all entries."""
    data = _make_scores_dict(n_countries=5, seed=42)
    all_sens = sens.compute_all_sensitivity(data)
    for country, entries in all_sens.items():
        for e in entries:
            expected_hp = e["headroom"] * 50.0
            assert abs(e["headroom_points"] - expected_hp) < 1e-9, (
                f"{country}/{e['indicator']}: headroom_points={e['headroom_points']} "
                f"!= headroom*50={expected_hp}"
            )


def test_integration_foreign_intervention_artifact(tmp_path):
    """End-to-end: simulate foreign_intervention scores and verify artifact."""
    data = {
        "schema_version": 1,
        "recipe_id": "foreign_intervention",
        "evaluation_year": 2021,
        "selected_indicators": ["v2elintmon", "RQ.EST", "v2pepwrgen", "v2stfisccap"],
        "chosen_window": 18,
        "shap_importance_normalized": {
            "v2elintmon": 0.047,
            "RQ.EST": 0.511,
            "v2pepwrgen": 0.273,
            "v2stfisccap": 0.168,
        },
        "n_countries_scored": 2,
        "scores": {
            "Iran": {
                "cosine_similarity_S": 0.85,
                "risk_score": 92.5,
                "zone": "HIGH",
                "per_indicator": {
                    "v2elintmon": {"cosine": 0.72, "weight": 0.047, "weighted_contribution": 0.0338},
                    "RQ.EST": {"cosine": 0.93, "weight": 0.511, "weighted_contribution": 0.4752},
                    "v2pepwrgen": {"cosine": 0.81, "weight": 0.273, "weighted_contribution": 0.2211},
                    "v2stfisccap": {"cosine": 0.74, "weight": 0.168, "weighted_contribution": 0.1243},
                },
            },
            "Norway": {
                "cosine_similarity_S": -0.05,
                "risk_score": 47.5,
                "zone": "LOW",
                "per_indicator": {
                    "v2elintmon": {"cosine": 0.80, "weight": 0.047, "weighted_contribution": 0.0376},
                    "RQ.EST": {"cosine": -0.50, "weight": 0.511, "weighted_contribution": -0.2555},
                    "v2pepwrgen": {"cosine": 0.95, "weight": 0.273, "weighted_contribution": 0.2594},
                    "v2stfisccap": {"cosine": 0.85, "weight": 0.168, "weighted_contribution": 0.1428},
                },
            },
        },
    }

    all_sens = sens.compute_all_sensitivity(data)
    artifact = sens.build_output(data, all_sens)

    # Iran: all cosines ≥ 0.72 → headroom = w*(1-cos); lowest headroom for RQ.EST (cos=0.93)
    iran_sens = all_sens["Iran"]
    # RQ.EST headroom = 0.511 * (1 - 0.93) = 0.03577; v2elintmon = 0.047*(1-0.72)=0.01316
    # v2pepwrgen = 0.273*(1-0.81)=0.05187; v2stfisccap = 0.168*(1-0.74)=0.04368
    # Sorted desc: v2pepwrgen > v2stfisccap > RQ.EST > v2elintmon
    assert iran_sens[0]["indicator"] == "v2pepwrgen", (
        f"Iran top headroom should be v2pepwrgen, got {iran_sens[0]['indicator']}"
    )

    # Norway: RQ.EST has cosine=-0.5 → headroom = 0.511*(1-(-0.5)) = 0.7665 (largest)
    norway_sens = all_sens["Norway"]
    assert norway_sens[0]["indicator"] == "RQ.EST", (
        f"Norway top headroom should be RQ.EST (cosine=-0.5), got {norway_sens[0]['indicator']}"
    )
    expected_hr_norway_rq = 0.511 * (1.0 - (-0.5))
    assert abs(norway_sens[0]["headroom"] - expected_hr_norway_rq) < 1e-6

    # m8_r5_note must have the anti-causal firewall
    note = artifact["m8_r5_note"]
    assert "discriminative, not causal" in note
    assert "NOT a claim" in note
