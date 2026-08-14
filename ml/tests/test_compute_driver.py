"""Unit tests for compute_driver.py — per-country driver (TE capability #4).

No IO, no panels, no AWS. All tests operate on synthetic in-memory data.

Coverage:
  - compute_country_drivers: correct ranking by weighted_contribution descending
  - compute_country_drivers: signal_share_pct (abs-mass) sums to ~100 when all positive
  - compute_country_drivers: signal_share_pct bounded [-100,100] + sign-correct when S near-zero/negative
  - compute_country_drivers: output schema matches spec (indicator, indicator_label,
      weighted_contribution, signal_share_pct, cosine)
  - compute_country_drivers: handles negative contributions correctly
  - compute_country_drivers: handles single-indicator recipe
  - compute_all_drivers: keys match country names in scores dict
  - compute_all_drivers: every country has full entry list matching n_indicators
  - build_output: schema includes recipe_id, eval_year, computed_at_utc,
      binding_provenance, m8_r5_note
  - build_output: m8_r5_note uses attribution framing, not causal/probability
  - get_indicator_label: returns catalog label for known indicators
  - get_indicator_label: returns raw code + TODO for unknown indicators
  - CLI: parser accepts all documented flags + defaults
  - Integration: end-to-end with synthetic scores dict produces valid artifact

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

import compute_driver as drv  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

INDICATOR_LABELS = {
    "v2elintmon": "International Election Monitoring",
    "RQ.EST": "Regulatory Quality (WGI)",
    "v2pepwrgen": "Power Distributed by Gender",
    "v2stfisccap": "Fiscal Capacity",
}


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


def _make_simple_country_entry(contributions: list[float]) -> dict:
    """Build a minimal per_indicator dict from a list of weighted_contributions."""
    indicators = [f"IND_{i}" for i in range(len(contributions))]
    weights = [0.25] * len(contributions)
    cosines = [c / w if abs(w) > 1e-9 else 0.0 for c, w in zip(contributions, weights)]
    per_ind = {
        ind: {
            "cosine": cos,
            "weight": w,
            "weighted_contribution": wc,
        }
        for ind, cos, w, wc in zip(indicators, cosines, weights, contributions)
    }
    total_S = sum(contributions)
    return {
        "cosine_similarity_S": total_S,
        "risk_score": 100 * (total_S + 1) / 2,
        "zone": "HIGH",
        "per_indicator": per_ind,
    }


# ---------------------------------------------------------------------------
# Tests: get_indicator_label
# ---------------------------------------------------------------------------


def test_label_known_vdem():
    """v2elintmon must return 'International Election Monitoring' (catalog verbatim)."""
    label = drv.get_indicator_label("v2elintmon")
    assert label == "International Election Monitoring", (
        f"Expected 'International Election Monitoring', got '{label}'"
    )


def test_label_known_wb_wgi():
    """RQ.EST must return 'Regulatory Quality (WGI)'."""
    label = drv.get_indicator_label("RQ.EST")
    assert "Regulatory Quality" in label, (
        f"Expected label containing 'Regulatory Quality', got '{label}'"
    )


def test_label_known_v2pepwrgen():
    """v2pepwrgen must return a label containing 'Gender' per catalog."""
    label = drv.get_indicator_label("v2pepwrgen")
    assert "Gender" in label or "gender" in label, (
        f"Expected label containing 'Gender', got '{label}'"
    )


def test_label_known_v2stfisccap():
    """v2stfisccap must return a label containing 'Fiscal' or 'Capacity' per catalog."""
    label = drv.get_indicator_label("v2stfisccap")
    assert "Fiscal" in label or "Capacity" in label or "fiscal" in label, (
        f"Expected label containing 'Fiscal'/'Capacity', got '{label}'"
    )


def test_label_unknown_indicator_returns_raw_code_with_todo():
    """Unknown indicator code must return the raw code + 'TODO' note, not a confabulated label."""
    label = drv.get_indicator_label("TOTALLY_UNKNOWN_CODE_XYZ")
    assert "TOTALLY_UNKNOWN_CODE_XYZ" in label, (
        "Unknown indicator: raw code must appear in returned label"
    )
    assert "TODO" in label.upper(), (
        "Unknown indicator: label must include TODO note to prevent confabulation"
    )


# ---------------------------------------------------------------------------
# Tests: compute_country_drivers — ranking
# ---------------------------------------------------------------------------


def test_drivers_ranked_by_weighted_contribution_descending():
    """Indicators must be ranked by weighted_contribution descending."""
    contributions = [0.10, 0.40, 0.05, 0.20]
    entry = _make_simple_country_entry(contributions)
    result = drv.compute_country_drivers(entry)
    wcs = [r["weighted_contribution"] for r in result]
    assert wcs == sorted(wcs, reverse=True), (
        f"Not sorted descending: {wcs}"
    )


def test_drivers_count_matches_indicators():
    """Result must contain one entry per indicator."""
    contributions = [0.1, 0.3, 0.2, 0.05]
    entry = _make_simple_country_entry(contributions)
    result = drv.compute_country_drivers(entry)
    assert len(result) == 4, f"Expected 4 entries, got {len(result)}"


def test_drivers_single_indicator():
    """Single-indicator recipe produces a single-entry result."""
    entry = {
        "cosine_similarity_S": 0.5,
        "risk_score": 75.0,
        "zone": "HIGH",
        "per_indicator": {
            "IND_A": {"cosine": 0.5, "weight": 1.0, "weighted_contribution": 0.5}
        },
    }
    result = drv.compute_country_drivers(entry)
    assert len(result) == 1
    assert result[0]["indicator"] == "IND_A"
    assert abs(result[0]["signal_share_pct"] - 100.0) < 1e-6, (
        f"Single indicator signal_share_pct should be 100.0, got {result[0]['signal_share_pct']}"
    )


# ---------------------------------------------------------------------------
# Tests: compute_country_drivers — share_pct
# ---------------------------------------------------------------------------


def test_signal_share_pct_abs_sums_to_100_when_all_positive():
    """signal_share_pct values must sum to ~100 when all contributions are positive."""
    contributions = [0.10, 0.40, 0.05, 0.20]
    entry = _make_simple_country_entry(contributions)
    result = drv.compute_country_drivers(entry)
    total_share = sum(r["signal_share_pct"] for r in result)
    # All-positive: abs-mass == signed sum, so shares sum to 100%.
    assert abs(total_share - 100.0) < 1e-4, (
        f"signal_share_pct should sum to 100.0 for all-positive contributions, got {total_share:.4f}"
    )


def test_signal_share_pct_formula_is_absolute_mass():
    """signal_share_pct = weighted_contribution / sum(|weighted_contribution|) * 100."""
    contributions = [0.30, 0.10, 0.20]
    entry = _make_simple_country_entry(contributions)
    abs_mass = sum(abs(c) for c in contributions)
    result = drv.compute_country_drivers(entry)
    for r in result:
        expected = r["weighted_contribution"] / abs_mass * 100.0
        assert abs(r["signal_share_pct"] - expected) < 1e-6, (
            f"signal_share_pct mismatch for {r['indicator']}: "
            f"expected {expected:.6f}, got {r['signal_share_pct']:.6f}"
        )


def test_signal_share_pct_bounded_when_S_near_zero_or_negative():
    """HONESTY GUARD (review 2026-05-24): when the signed sum S is near-zero or
    negative (mixed contributions), the OLD share_pct = wc/S blew up past 100% /
    sign-inverted (e.g. Argentina 528%, Armenia -67% for a positive contribution).
    The abs-mass denominator must keep every signal_share_pct bounded in
    [-100, +100], magnitudes summing to 100%, and the SIGN must match the
    contribution's sign (a positive contribution can never get a negative share)."""
    # S = 0.50 - 0.45 + 0.04 - 0.05 = 0.04  (near-zero signed sum, the pathological case)
    contributions = [0.50, -0.45, 0.04, -0.05]
    entry = _make_simple_country_entry(contributions)
    result = drv.compute_country_drivers(entry)
    abs_total = sum(abs(r["signal_share_pct"]) for r in result)
    assert abs(abs_total - 100.0) < 1e-4, (
        f"|signal_share_pct| must sum to 100, got {abs_total:.4f}"
    )
    for r in result:
        assert -100.0 - 1e-9 <= r["signal_share_pct"] <= 100.0 + 1e-9, (
            f"{r['indicator']}: signal_share_pct {r['signal_share_pct']:.2f} out of [-100,100] "
            f"(this is the bug the fix closes)"
        )
        # Sign of the share must match the sign of the contribution.
        wc = r["weighted_contribution"]
        if wc > 0:
            assert r["signal_share_pct"] > 0, f"{r['indicator']}: positive wc got negative share"
        elif wc < 0:
            assert r["signal_share_pct"] < 0, f"{r['indicator']}: negative wc got positive share"


def test_signal_share_pct_zero_when_all_contributions_zero():
    """Degenerate all-zero contributions → signal_share_pct 0.0, no divide-by-zero."""
    entry = _make_simple_country_entry([0.0, 0.0, 0.0])
    result = drv.compute_country_drivers(entry)
    assert all(r["signal_share_pct"] == 0.0 for r in result)


# ---------------------------------------------------------------------------
# Tests: compute_country_drivers — output schema
# ---------------------------------------------------------------------------


def test_drivers_output_schema():
    """Each entry must contain the required fields per spec §4."""
    contributions = [0.20, 0.30, 0.10, 0.15]
    entry = _make_simple_country_entry(contributions)
    result = drv.compute_country_drivers(entry)
    required = {"indicator", "indicator_label", "weighted_contribution", "signal_share_pct", "cosine"}
    for i, r in enumerate(result):
        assert required.issubset(set(r.keys())), (
            f"Entry {i} missing fields: {required - set(r.keys())}"
        )


def test_drivers_indicator_label_is_string():
    """indicator_label must be a non-empty string."""
    contributions = [0.20, 0.30, 0.10, 0.15]
    entry = _make_simple_country_entry(contributions)
    result = drv.compute_country_drivers(entry)
    for r in result:
        assert isinstance(r["indicator_label"], str), (
            f"{r['indicator']}: indicator_label must be a string"
        )
        assert len(r["indicator_label"]) > 0, (
            f"{r['indicator']}: indicator_label must be non-empty"
        )


def test_drivers_cosine_matches_input():
    """cosine in output must match the per_indicator cosine from the input."""
    entry = {
        "cosine_similarity_S": 0.6,
        "risk_score": 80.0,
        "zone": "HIGH",
        "per_indicator": {
            "IND_A": {"cosine": 0.8, "weight": 0.5, "weighted_contribution": 0.4},
            "IND_B": {"cosine": 0.4, "weight": 0.5, "weighted_contribution": 0.2},
        },
    }
    result = drv.compute_country_drivers(entry)
    cosine_map = {r["indicator"]: r["cosine"] for r in result}
    assert abs(cosine_map["IND_A"] - 0.8) < 1e-9
    assert abs(cosine_map["IND_B"] - 0.4) < 1e-9


# ---------------------------------------------------------------------------
# Tests: compute_all_drivers
# ---------------------------------------------------------------------------


def test_compute_all_drivers_keys_match_countries():
    """Output dict must have exactly the same country keys as scores dict."""
    data = _make_scores_dict(n_countries=5)
    result = drv.compute_all_drivers(data)
    assert set(result.keys()) == set(data["scores"].keys()), (
        "Output country keys must match input scores keys"
    )


def test_compute_all_drivers_each_country_has_all_indicators():
    """Each country's driver list must have one entry per indicator."""
    data = _make_scores_dict(n_countries=4)
    n_ind = len(data["selected_indicators"])
    result = drv.compute_all_drivers(data)
    for country, drivers in result.items():
        assert len(drivers) == n_ind, (
            f"{country}: expected {n_ind} driver entries, got {len(drivers)}"
        )


def test_compute_all_drivers_is_sorted():
    """Each country's drivers must be sorted by weighted_contribution descending."""
    data = _make_scores_dict(n_countries=3)
    result = drv.compute_all_drivers(data)
    for country, drivers in result.items():
        wcs = [d["weighted_contribution"] for d in drivers]
        assert wcs == sorted(wcs, reverse=True), (
            f"{country}: drivers not sorted descending: {wcs}"
        )


# ---------------------------------------------------------------------------
# Tests: build_output — artifact schema
# ---------------------------------------------------------------------------


def test_build_output_required_top_level_keys():
    """Artifact must have recipe_id, eval_year, computed_at_utc,
    binding_provenance, m8_r5_note, drivers per spec."""
    data = _make_scores_dict(n_countries=2)
    drivers = drv.compute_all_drivers(data)
    artifact = drv.build_output(data, drivers)
    required = {
        "recipe_id", "eval_year", "computed_at_utc",
        "binding_provenance", "m8_r5_note", "drivers",
    }
    assert required.issubset(set(artifact.keys())), (
        f"Missing top-level keys: {required - set(artifact.keys())}"
    )


def test_build_output_m8_r5_note_is_attribution_framing():
    """m8_r5_note must use attribution framing, not causal/probability language.

    The note must not CLAIM causality (i.e., must not positively assert X causes Y).
    It may DENY causality (e.g., "NOT causal" or "never interpret as causes").
    It must also not claim probability.
    """
    data = _make_scores_dict(n_countries=2)
    drivers = drv.compute_all_drivers(data)
    artifact = drv.build_output(data, drivers)
    note = artifact["m8_r5_note"]
    assert isinstance(note, str) and len(note) > 0, "m8_r5_note must be a non-empty string"
    # Must explicitly deny causality (the note may mention 'causes' in a negating context)
    note_lower = note.lower()
    has_causal_denial = (
        "not causal" in note_lower
        or "never" in note_lower
        or "not a claim" in note_lower
        or "discrimination" in note_lower
        or "discriminative" in note_lower
    )
    assert has_causal_denial, (
        f"m8_r5_note must explicitly deny causality (e.g. 'not causal', 'never'): {note!r}"
    )
    # Must not positively claim to give a probability — it may deny it (e.g., "not a probability")
    # Check: the note must not have standalone positive claim like "probability of" or "is X%"
    import re
    # If "probability" appears, it must be in a negating context
    if "probability" in note_lower:
        has_prob_denial = (
            "not a probability" in note_lower
            or "not probability" in note_lower
            or "no probability" in note_lower
        )
        assert has_prob_denial, (
            f"m8_r5_note may only mention 'probability' in a negating context: {note!r}"
        )
    # Must reference attribution to similarity score
    assert (
        "attribution" in note_lower
        or "contributes" in note_lower
        or "similarity" in note_lower
        or "score" in note_lower
    ), (
        "m8_r5_note must reference attribution to similarity score"
    )


def test_build_output_drivers_contains_all_countries():
    """artifact['drivers'] must contain an entry for every country in scores."""
    data = _make_scores_dict(n_countries=3)
    drivers = drv.compute_all_drivers(data)
    artifact = drv.build_output(data, drivers)
    assert set(artifact["drivers"].keys()) == set(data["scores"].keys())


def test_build_output_recipe_id_matches():
    """artifact['recipe_id'] must match the input scores recipe_id."""
    data = _make_scores_dict(n_countries=2)
    drivers = drv.compute_all_drivers(data)
    artifact = drv.build_output(data, drivers)
    assert artifact["recipe_id"] == data["recipe_id"]


def test_build_output_eval_year_matches():
    """artifact['eval_year'] must match the input scores evaluation_year."""
    data = _make_scores_dict(n_countries=2)
    drivers = drv.compute_all_drivers(data)
    artifact = drv.build_output(data, drivers)
    assert artifact["eval_year"] == data["evaluation_year"]


def test_build_output_binding_provenance_cites_spec():
    """binding_provenance must cite te-new-capabilities-spec.md."""
    data = _make_scores_dict(n_countries=2)
    drivers = drv.compute_all_drivers(data)
    artifact = drv.build_output(data, drivers)
    prov = artifact["binding_provenance"]
    assert "te-new-capabilities-spec" in prov or "te-new-capabilities-spec.md" in prov, (
        "binding_provenance must cite te-new-capabilities-spec.md"
    )


def test_build_output_computed_at_utc_is_iso():
    """computed_at_utc must be an ISO 8601 UTC timestamp string."""
    from datetime import datetime, timezone
    data = _make_scores_dict(n_countries=2)
    drivers = drv.compute_all_drivers(data)
    artifact = drv.build_output(data, drivers)
    ts = artifact["computed_at_utc"]
    assert isinstance(ts, str) and len(ts) > 0, "computed_at_utc must be a non-empty string"
    # Parseable as ISO 8601
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.tzinfo is not None, "Timestamp must be timezone-aware"
    except ValueError as e:
        pytest.fail(f"computed_at_utc is not ISO 8601: {ts!r} — {e}")


# ---------------------------------------------------------------------------
# Tests: CLI parser
# ---------------------------------------------------------------------------


def test_cli_parser_required_flags(tmp_path):
    """--scores-file and --output-dir are required."""
    parser = drv._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])  # missing required flags


def test_cli_parser_all_flags(tmp_path):
    """Parser must accept all documented flags without error."""
    parser = drv._build_parser()
    args = parser.parse_args([
        "--scores-file", str(tmp_path / "scores.json"),
        "--output-dir", str(tmp_path),
    ])
    assert args.scores_file == tmp_path / "scores.json"
    assert args.output_dir == tmp_path


def test_cli_parser_optional_catalog_flag(tmp_path):
    """--catalog-file is an optional flag."""
    parser = drv._build_parser()
    args = parser.parse_args([
        "--scores-file", str(tmp_path / "scores.json"),
        "--output-dir", str(tmp_path),
        "--catalog-file", str(tmp_path / "catalog.md"),
    ])
    assert args.catalog_file == tmp_path / "catalog.md"


# ---------------------------------------------------------------------------
# Tests: integration — real indicator labels on known codes
# ---------------------------------------------------------------------------


def test_real_indicator_labels_no_confabulation():
    """The 4 foreign_intervention indicators must map to catalog-exact labels."""
    # Spec explicitly names these 4 (te-new-capabilities-spec.md §4):
    #   v2elintmon = "International Election Monitoring"
    #   RQ.EST     = "Regulatory Quality (WGI)"
    #   v2pepwrgen = power distribution by gender
    #   v2stfisccap = state fiscal capacity
    assert "International Election Monitoring" in drv.get_indicator_label("v2elintmon")
    assert "Regulatory Quality" in drv.get_indicator_label("RQ.EST")
    # The spec says "v2pepwrgen = power distribution by gender"
    label_pwr = drv.get_indicator_label("v2pepwrgen")
    assert len(label_pwr) > 0 and "TODO" not in label_pwr.upper(), (
        f"v2pepwrgen should have a real label, got: {label_pwr!r}"
    )
    label_fis = drv.get_indicator_label("v2stfisccap")
    assert len(label_fis) > 0 and "TODO" not in label_fis.upper(), (
        f"v2stfisccap should have a real label, got: {label_fis!r}"
    )


def test_no_confabulated_government_internet_monitoring():
    """v2elintmon must NOT return any confabulation like 'Government internet monitoring'.

    This is the exact error documented in feedback_indicator_labels_canonical_catalog.md:
    the confabulated label 'Government internet monitoring' must never appear.
    """
    label = drv.get_indicator_label("v2elintmon")
    assert "internet" not in label.lower(), (
        f"CONFABULATION DETECTED: v2elintmon returned '{label}' — "
        "must be 'International Election Monitoring' per catalog."
    )
    assert "government internet" not in label.lower(), (
        "CONFABULATION DETECTED: must not return 'Government internet monitoring'"
    )


# ---------------------------------------------------------------------------
# Tests: integration — end-to-end with synthetic real-recipe data
# ---------------------------------------------------------------------------


def test_integration_foreign_intervention_structure(tmp_path):
    """End-to-end: simulate a foreign_intervention-like scores dict and verify
    the full artifact schema is valid."""
    # Simulate 3-country, 4-indicator recipe
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
        "n_countries_scored": 3,
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
                "cosine_similarity_S": 0.10,
                "risk_score": 55.0,
                "zone": "MODERATE",
                "per_indicator": {
                    "v2elintmon": {"cosine": 0.50, "weight": 0.047, "weighted_contribution": 0.0235},
                    "RQ.EST": {"cosine": -0.50, "weight": 0.511, "weighted_contribution": -0.2555},
                    "v2pepwrgen": {"cosine": 0.90, "weight": 0.273, "weighted_contribution": 0.2457},
                    "v2stfisccap": {"cosine": 0.54, "weight": 0.168, "weighted_contribution": 0.0907},
                },
            },
            "Syria": {
                "cosine_similarity_S": 0.78,
                "risk_score": 89.0,
                "zone": "HIGH",
                "per_indicator": {
                    "v2elintmon": {"cosine": 0.10, "weight": 0.047, "weighted_contribution": 0.0047},
                    "RQ.EST": {"cosine": 0.88, "weight": 0.511, "weighted_contribution": 0.4497},
                    "v2pepwrgen": {"cosine": 0.79, "weight": 0.273, "weighted_contribution": 0.2157},
                    "v2stfisccap": {"cosine": 0.68, "weight": 0.168, "weighted_contribution": 0.1142},
                },
            },
        },
    }

    drivers = drv.compute_all_drivers(data)
    artifact = drv.build_output(data, drivers)

    # Top driver for Iran must be RQ.EST (largest weighted_contribution = 0.4752)
    iran_top = drivers["Iran"][0]
    assert iran_top["indicator"] == "RQ.EST", (
        f"Iran top driver should be RQ.EST, got {iran_top['indicator']}"
    )
    assert "Regulatory Quality" in iran_top["indicator_label"], (
        f"Iran top driver label should contain 'Regulatory Quality', got {iran_top['indicator_label']!r}"
    )

    # Norway: last driver should be the most negative (RQ.EST = -0.2555)
    norway_drivers = drivers["Norway"]
    # sorted descending: negative ones at the end
    assert norway_drivers[-1]["weighted_contribution"] < 0, (
        "Norway's last entry should be the most negative contribution"
    )

    # Artifact top-level keys present
    required = {"recipe_id", "eval_year", "computed_at_utc", "binding_provenance", "m8_r5_note", "drivers"}
    assert required.issubset(set(artifact.keys()))

    # All countries present
    assert set(artifact["drivers"].keys()) == {"Iran", "Norway", "Syria"}

    # signal_share_pct uses the absolute-mass denominator, so the MAGNITUDES
    # always sum to 100% exactly (independent of the signed sum S). This is the
    # invariant the abs-mass fix guarantees for every country.
    iran_abs_share_sum = sum(abs(d["signal_share_pct"]) for d in artifact["drivers"]["Iran"])
    assert abs(iran_abs_share_sum - 100.0) < 1e-4, (
        f"Iran |signal_share_pct| should sum to 100, got {iran_abs_share_sum:.4f}"
    )
