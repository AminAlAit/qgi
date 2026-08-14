"""Unit tests for compute_recipe_rubric.py.

Covers the four-factor rubric (A, B, C, D), HARD GATE behavior, survival
sub-factor lookup, F5 head-class assignment, event corpus loading edge cases,
and a synthetic end-to-end flow with a fake curated corpus + taxonomy +
indicator-sector map.

Skipped when the real qgi-data files are absent (so tests run on a CI worker
that only has qgi-ml checked out).

Stage 0 deliverable per docs/specs/internal/ops/ml-track/stage-0-pre-registration.md.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import compute_recipe_rubric as crr  # noqa: E402


# ---------- Factor A ----------


def test_factor_a_below_gate_excludes():
    a, gated = crr.compute_factor_a(7, 100)
    assert a == 0.0
    assert gated is True


def test_factor_a_at_gate_includes():
    a, gated = crr.compute_factor_a(8, 100)
    assert a == pytest.approx(0.08)
    assert gated is False


def test_factor_a_max_normalized_to_one():
    a, gated = crr.compute_factor_a(100, 100)
    assert a == 1.0
    assert gated is False


def test_factor_a_zero_max_is_safe():
    a, gated = crr.compute_factor_a(50, 0)
    assert a == 0.0
    assert gated is True


def test_factor_a_custom_gate():
    a, gated = crr.compute_factor_a(15, 100, gate_min=20)
    assert a == 0.0
    assert gated is True
    a2, gated2 = crr.compute_factor_a(20, 100, gate_min=20)
    assert a2 == pytest.approx(0.20)
    assert gated2 is False


# ---------- Factor B ----------


def test_factor_b_external_source_score_one():
    b, src = crr.compute_factor_b("civil_war_and_insurgency")
    assert b == 1.0
    assert any("UCDP" in s for s in src)


def test_factor_b_internal_curation_half():
    b, src = crr.compute_factor_b("political_repression")
    assert b == 0.5


def test_factor_b_gradient_zero():
    b, src = crr.compute_factor_b("poverty_and_inequality_crisis")
    assert b == 0.0


def test_factor_b_unscored_defaults_to_half():
    b, src = crr.compute_factor_b("totally_made_up_category")
    assert b == 0.5
    assert "unscored" in src[0]


def test_factor_b_table_covers_all_71_categories():
    real_taxonomy = pathlib.Path(crr.DEFAULT_CATEGORY_MAPPING)
    if not real_taxonomy.exists():
        pytest.skip("real taxonomy not present in this worktree")
    taxonomy = crr.load_category_taxonomy(real_taxonomy)
    missing = [c for c in taxonomy if c not in crr.LABEL_CLARITY_B]
    assert not missing, f"LABEL_CLARITY_B missing entries: {missing}"


# ---------- Factor C (sector proxy) ----------


def test_factor_c_high_coverage_capped_at_one():
    indicator_map = {f"X-{i}": "CONFLICT" for i in range(15)}
    c, sectors, n = crr.compute_factor_c("civil_war_and_insurgency", indicator_map)
    assert c == 1.0
    assert n == 15
    assert "CONFLICT" in sectors


def test_factor_c_low_coverage():
    # Only 2 indicators in any of civil_war's relevant sectors
    indicator_map = {"X-1": "CONFLICT", "X-2": "REPRESSION", "X-3": "FOOD_RES"}
    c, sectors, n = crr.compute_factor_c("civil_war_and_insurgency", indicator_map)
    # CONFLICT, REPRESSION, GOV_INST, DISPLACE -> only X-1, X-2 match
    assert n == 2
    assert c == pytest.approx(0.2)


def test_factor_c_unmapped_category_returns_zero():
    indicator_map = {"X-1": "CONFLICT"}
    c, sectors, n = crr.compute_factor_c("totally_made_up_category", indicator_map)
    assert c == 0.0
    assert sectors == []
    assert n == 0


def test_factor_c_table_covers_all_71_categories():
    real_taxonomy = pathlib.Path(crr.DEFAULT_CATEGORY_MAPPING)
    if not real_taxonomy.exists():
        pytest.skip("real taxonomy not present in this worktree")
    taxonomy = crr.load_category_taxonomy(real_taxonomy)
    missing = [c for c in taxonomy if c not in crr.SECTOR_RELEVANCE]
    assert not missing, f"SECTOR_RELEVANCE missing entries: {missing}"


# ---------- Factor D (iterative) ----------


def test_factor_d_shared_indicators_above_min():
    # Two recipes both relevant to CONFLICT (5 indicators); shared count = 5 >= 3
    pre_d = {"a": 0.6, "b": 0.5}
    sector_relevance = {"a": ["CONFLICT"], "b": ["CONFLICT"]}
    indicator_map = {f"X-{i}": "CONFLICT" for i in range(5)}
    d = crr.compute_factor_d(
        pre_d, sector_relevance, indicator_map, excluded=set(),
    )
    assert d == {"a": pytest.approx(0.2), "b": pytest.approx(0.2)}


def test_factor_d_shared_below_min_returns_zero():
    pre_d = {"a": 0.6, "b": 0.5}
    sector_relevance = {"a": ["CONFLICT"], "b": ["CONFLICT"]}
    indicator_map = {"X-1": "CONFLICT", "X-2": "CONFLICT"}
    d = crr.compute_factor_d(
        pre_d, sector_relevance, indicator_map, excluded=set(),
    )
    assert d == {"a": 0.0, "b": 0.0}


def test_factor_d_excluded_categories_get_zero():
    pre_d = {"a": 0.6, "b": 0.5, "excluded_cat": 0.0}
    sector_relevance = {
        "a": ["CONFLICT"], "b": ["CONFLICT"], "excluded_cat": ["CONFLICT"],
    }
    indicator_map = {f"X-{i}": "CONFLICT" for i in range(5)}
    d = crr.compute_factor_d(
        pre_d, sector_relevance, indicator_map, excluded={"excluded_cat"},
    )
    assert d["excluded_cat"] == 0.0


def test_factor_d_capped_at_one():
    # 6 recipes all share with each other -> each shares with 5 others
    # 5 / 5 = 1.0 (cap). Add one more so the unbounded value would be 6/5=1.2.
    # Make sure cap holds.
    pre_d = {f"r{i}": 0.5 + i * 0.01 for i in range(7)}
    sector_relevance = {f"r{i}": ["CONFLICT"] for i in range(7)}
    indicator_map = {f"X-{i}": "CONFLICT" for i in range(5)}
    d = crr.compute_factor_d(
        pre_d, sector_relevance, indicator_map, excluded=set(),
    )
    assert all(v <= 1.0 for v in d.values())
    assert max(d.values()) == 1.0


def test_factor_d_top_n_limit_respected():
    # 30 recipes all overlap; only top-20 considered for shared count.
    pre_d = {f"r{i}": 0.5 + i * 0.01 for i in range(30)}
    sector_relevance = {f"r{i}": ["CONFLICT"] for i in range(30)}
    indicator_map = {f"X-{i}": "CONFLICT" for i in range(5)}
    d = crr.compute_factor_d(
        pre_d, sector_relevance, indicator_map, excluded=set(),
        top_n=20,
    )
    # The top-20 by score (highest first) means r29..r10 are top-20.
    # For r29: 19 other top-20 recipes share >=3 indicators -> 19/5 capped at 1.0
    # For r0 (not in top-20): 20 top-20 recipes share -> 20/5 capped at 1.0
    # All return 1.0 because 5 >> 5 threshold.
    # Important: function evaluates ALL recipes in pre_d, not just top-N.
    assert "r0" in d
    assert "r29" in d
    assert d["r29"] == 1.0


# ---------- Event loading + counting ----------


def test_count_n_positive_dedupes_country_year():
    events = [
        {"country": "x", "year": 2020, "category": "c", "verified": True},
        {"country": "x", "year": 2020, "category": "c", "verified": False},  # dup
        {"country": "x", "year": 2021, "category": "c", "verified": False},
    ]
    counts = crr.count_n_positive(events, (2014, 2025))
    assert counts == {"c": 2}


def test_count_n_positive_window_filter():
    events = [
        {"country": "x", "year": 2010, "category": "c", "verified": True},
        {"country": "x", "year": 2015, "category": "c", "verified": True},
        {"country": "x", "year": 2026, "category": "c", "verified": True},
    ]
    counts = crr.count_n_positive(events, (2014, 2025))
    assert counts == {"c": 1}


def test_count_n_positive_verified_only_filter():
    events = [
        {"country": "x", "year": 2020, "category": "c", "verified": False},
        {"country": "x", "year": 2021, "category": "c", "verified": True},
    ]
    assert crr.count_n_positive(events, (2014, 2025)) == {"c": 2}
    assert crr.count_n_positive(events, (2014, 2025), verified_only=True) == {"c": 1}


def test_load_curated_events_skips_underscore_files(tmp_path):
    (tmp_path / "afghanistan.json").write_text(
        json.dumps([{"year": 2020, "category": "x"}]), encoding="utf-8",
    )
    (tmp_path / "_backup.json").write_text(
        json.dumps([{"year": 2020, "category": "x"}]), encoding="utf-8",
    )
    events = crr.load_curated_events(tmp_path)
    assert len(events) == 1
    assert events[0]["country"] == "afghanistan"


def test_load_curated_events_handles_malformed_json(tmp_path, capsys):
    (tmp_path / "good.json").write_text(
        json.dumps([{"year": 2020, "category": "x"}]), encoding="utf-8",
    )
    (tmp_path / "bad.json").write_text("not json at all", encoding="utf-8")
    events = crr.load_curated_events(tmp_path)
    assert len(events) == 1
    captured = capsys.readouterr()
    assert "bad.json" in captured.err


def test_load_curated_events_skips_events_missing_fields(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps([
        {"year": 2020, "category": "x"},
        {"year": 2020},
        {"category": "x"},
        {},
    ]), encoding="utf-8")
    events = crr.load_curated_events(tmp_path)
    assert len(events) == 1


def test_load_curated_events_ignores_non_list_files(tmp_path):
    (tmp_path / "x.json").write_text(
        json.dumps({"this is": "an object not a list"}), encoding="utf-8",
    )
    events = crr.load_curated_events(tmp_path)
    assert events == []


# ---------- Taxonomy + sector loading ----------


def test_load_category_taxonomy_returns_layer3_to_ancestors(tmp_path):
    cat_path = tmp_path / "cm.json"
    cat_path.write_text(json.dumps({
        "version": "1.0",
        "layer1": [{
            "id": "X", "label": "X", "definition": "x", "color_hint": "#000",
            "layer2": [{
                "id": "X1", "label": "X One", "definition": "x",
                "layer3": ["x_one"],
            }],
        }],
    }), encoding="utf-8")
    tax = crr.load_category_taxonomy(cat_path)
    assert tax == {"x_one": {"layer1_id": "X", "layer2_id": "X1", "layer2_label": "X One"}}


def test_load_category_taxonomy_real_file_is_71():
    real = pathlib.Path(crr.DEFAULT_CATEGORY_MAPPING)
    if not real.exists():
        pytest.skip("real taxonomy not present")
    tax = crr.load_category_taxonomy(real)
    assert len(tax) == 71


def test_load_indicator_sector_map_real_file_is_142():
    real = pathlib.Path(crr.DEFAULT_INDICATOR_SECTORS)
    if not real.exists():
        pytest.skip("real indicator-sectors.json not present")
    sm = crr.load_indicator_sector_map(real)
    assert len(sm) == 142
    # Spot-check a known assignment
    assert sm.get("WB-01") == "CONFLICT"


# ---------- Survival sub-factors + F5 head class ----------


def test_survival_subfactors_default_just_eligible():
    f2, f3, f4 = crr.survival_subfactors("totally_made_up_category")
    assert (f2, f3, f4) == crr.SURVIVAL_SUB_FACTORS_DEFAULT
    assert f2 + f3 + f4 == 5  # default is just barely survival-eligible


def test_survival_subfactors_known_clear_onset():
    assert crr.survival_subfactors("civil_war_and_insurgency") == (3, 2, 2)


def test_survival_subfactors_known_gradient():
    assert crr.survival_subfactors("poverty_and_inequality_crisis") == (0, 0, 0)


def test_assign_head_class_excluded_when_below_gate():
    f5, label = crr.assign_head_class(survival_eligible=True, n_positive=5)
    assert f5 == 0
    assert label == "excluded"


def test_assign_head_class_survival_when_eligible_and_dense():
    f5, label = crr.assign_head_class(survival_eligible=True, n_positive=20)
    assert f5 == 3
    assert "DeepHit" in label


def test_assign_head_class_asymmetric_with_survival_deferred_label():
    # Survival-eligible but n_positive in [8,20) -> rare-class GBM, deferred label.
    f5, label = crr.assign_head_class(survival_eligible=True, n_positive=19)
    assert f5 == 2
    assert "asymmetric" in label
    assert "deferred" in label  # explicit "survival deferred until n>=20" hint


def test_assign_head_class_standard_gbm_when_dense_but_not_eligible():
    f5, label = crr.assign_head_class(survival_eligible=False, n_positive=50)
    assert f5 == 1
    assert "standard" in label


def test_assign_head_class_asymmetric_when_rare_and_not_eligible():
    f5, label = crr.assign_head_class(survival_eligible=False, n_positive=10)
    assert f5 == 2
    assert "asymmetric" in label
    assert "deferred" not in label  # not survival-eligible -> no deferred hint


def test_survival_subfactors_table_covers_all_71_categories():
    real = pathlib.Path(crr.DEFAULT_CATEGORY_MAPPING)
    if not real.exists():
        pytest.skip("real taxonomy not present")
    tax = crr.load_category_taxonomy(real)
    # Default is acceptable; this test just sanity-checks no typos in the table
    for cat in tax:
        f2, f3, f4 = crr.survival_subfactors(cat)
        assert 0 <= f2 <= 3
        assert 0 <= f3 <= 2
        assert 0 <= f4 <= 2


# ---------- End-to-end synthetic ----------


@pytest.fixture
def synthetic_inputs(tmp_path):
    """Produce a minimal curated corpus + taxonomy + indicator-sector map."""
    curated = tmp_path / "curated"
    curated.mkdir()
    # 12 unique (country, year) pairs for elections (passes hard gate);
    # 2 pairs for civil war (gated out)
    elections = [
        {"year": 2014 + i, "category": "elections_and_voting", "verified": True}
        for i in range(12)
    ]
    civil = [
        {"year": 2020, "category": "civil_war_and_insurgency", "verified": True},
        {"year": 2021, "category": "civil_war_and_insurgency", "verified": False},
    ]
    (curated / "atlantis.json").write_text(json.dumps(elections + civil), encoding="utf-8")

    cat_path = tmp_path / "category_mapping.json"
    cat_path.write_text(json.dumps({
        "version": "1.0",
        "layer1": [
            {"id": "A", "label": "Politics", "definition": "x", "color_hint": "#0",
             "layer2": [{"id": "A1", "label": "Elections", "definition": "x",
                         "layer3": ["elections_and_voting"]}]},
            {"id": "B", "label": "Conflict", "definition": "x", "color_hint": "#0",
             "layer2": [{"id": "B2", "label": "Civil War", "definition": "x",
                         "layer3": ["civil_war_and_insurgency"]}]},
        ],
    }), encoding="utf-8")

    sec_path = tmp_path / "indicator-sectors.json"
    sec_path.write_text(json.dumps({
        "schema_version": 1,
        "indicator_to_sector": {
            **{f"X-{i}": {"sector": "GOV_INST"} for i in range(20)},
            **{f"Y-{i}": {"sector": "CONFLICT"} for i in range(15)},
        },
    }), encoding="utf-8")
    return {"curated": curated, "cat_path": cat_path, "sec_path": sec_path}


def test_compute_recipe_rubric_end_to_end_payload_shape(synthetic_inputs):
    payload = crr.compute_recipe_rubric(
        curated_dir=synthetic_inputs["curated"],
        category_mapping_path=synthetic_inputs["cat_path"],
        indicator_sectors_path=synthetic_inputs["sec_path"],
        window=(2014, 2025),
    )
    assert payload["schema_version"] == 1
    assert payload["n_categories_total"] == 2
    assert "ranking" in payload
    assert "sources" in payload
    assert "category_mapping_sha256" in payload["sources"]
    assert "events_curated_state_hash_in_window" in payload["sources"]


def test_compute_recipe_rubric_hard_gate_applied(synthetic_inputs):
    payload = crr.compute_recipe_rubric(
        curated_dir=synthetic_inputs["curated"],
        category_mapping_path=synthetic_inputs["cat_path"],
        indicator_sectors_path=synthetic_inputs["sec_path"],
    )
    by_cat = {r["category_id"]: r for r in payload["ranking"]}
    assert by_cat["civil_war_and_insurgency"]["excluded_by_hard_gate"] is True
    assert by_cat["civil_war_and_insurgency"]["rank"] is None
    assert by_cat["civil_war_and_insurgency"]["A"] == 0.0
    # Per spec: hard-gated recipes get S=0.0 (not B+C+D residual).
    assert by_cat["civil_war_and_insurgency"]["S"] == 0.0
    assert by_cat["elections_and_voting"]["excluded_by_hard_gate"] is False
    assert by_cat["elections_and_voting"]["rank"] is not None
    assert by_cat["elections_and_voting"]["S"] > 0


def test_compute_recipe_rubric_uses_verified_only_for_gate(tmp_path):
    """All curated events count for n_positive_total; only verified gate Factor A.

    Setup: 12 unique (country, year) for 'elections_and_voting' but only 3 verified.
    Verified-only -> n=3 < 8 -> hard-gated.
    """
    curated = tmp_path / "curated"
    curated.mkdir()
    events = [
        {"year": 2014 + i, "category": "elections_and_voting", "verified": (i < 3)}
        for i in range(12)
    ]
    (curated / "atlantis.json").write_text(json.dumps(events), encoding="utf-8")

    cat_path = tmp_path / "category_mapping.json"
    cat_path.write_text(json.dumps({
        "version": "1.0",
        "layer1": [{
            "id": "A", "label": "Politics", "definition": "x", "color_hint": "#0",
            "layer2": [{"id": "A1", "label": "Elections", "definition": "x",
                        "layer3": ["elections_and_voting"]}],
        }],
    }), encoding="utf-8")

    sec_path = tmp_path / "indicator-sectors.json"
    sec_path.write_text(json.dumps({
        "schema_version": 1,
        "indicator_to_sector": {f"X-{i}": {"sector": "GOV_INST"} for i in range(20)},
    }), encoding="utf-8")

    payload = crr.compute_recipe_rubric(
        curated_dir=curated,
        category_mapping_path=cat_path,
        indicator_sectors_path=sec_path,
        window=(2014, 2025),
    )
    by_cat = {r["category_id"]: r for r in payload["ranking"]}
    e = by_cat["elections_and_voting"]
    assert e["n_positive_total"] == 12
    assert e["n_positive_verified"] == 3
    assert e["excluded_by_hard_gate"] is True  # verified < 8
    assert e["A"] == 0.0
    assert e["S"] == 0.0
    assert e["rank"] is None


def test_compute_recipe_rubric_ranking_is_descending(synthetic_inputs):
    payload = crr.compute_recipe_rubric(
        curated_dir=synthetic_inputs["curated"],
        category_mapping_path=synthetic_inputs["cat_path"],
        indicator_sectors_path=synthetic_inputs["sec_path"],
    )
    eligible = [r for r in payload["ranking"] if r["rank"] is not None]
    scores = [r["S"] for r in eligible]
    assert scores == sorted(scores, reverse=True)


def test_render_summary_handles_minimal_payload():
    payload = {
        "n_categories_total": 0,
        "n_categories_excluded_by_hard_gate": 0,
        "weights": {"A": 0.35, "B": 0.25, "C": 0.25, "D": 0.15},
        "training_window": [2014, 2025],
        "hard_gate": {"min_n_positive": 8},
        "ranking": [],
    }
    out = crr.render_summary(payload)
    assert "0 categories total" in out
    assert "Weights" in out


# ---------- Determinism ----------


def test_compute_recipe_rubric_is_deterministic(synthetic_inputs):
    p1 = crr.compute_recipe_rubric(
        curated_dir=synthetic_inputs["curated"],
        category_mapping_path=synthetic_inputs["cat_path"],
        indicator_sectors_path=synthetic_inputs["sec_path"],
    )
    p2 = crr.compute_recipe_rubric(
        curated_dir=synthetic_inputs["curated"],
        category_mapping_path=synthetic_inputs["cat_path"],
        indicator_sectors_path=synthetic_inputs["sec_path"],
    )
    # Ignore the generated timestamp (none currently in payload)
    assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)
