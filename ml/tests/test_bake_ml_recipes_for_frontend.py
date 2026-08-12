"""Tests for `scripts.bake_ml_recipes_for_frontend` (master frontend bake).

Locks the contract:
1. The bake produces exactly 4 top-4 recipes (per Majles 2026-05-11 Topic 5).
2. `interpretation_hint` per recipe matches the Asas mini-Majles DECISION
   (#656). Currently: 1 `risk_elevation` (civil_war) + 3 `ambiguous` (others).
3. `dispatch_sha` matches `EXPECTED_DISPATCH_SHA` from verify_dispatch_sha
   (the F-H-1 item 4 deploy gate). Mismatch raises ValueError.
4. Required schema fields are present + correctly typed across all 4 recipes.
5. Derived fields are computed correctly:
   - `display_name` = title-case from recipe_id
   - `concentration_alert_level` = thresholded from share
   - `mechanism_narrative_excerpt` = sentence-boundary truncation
   - `paper_section_anchor` = `section-4-{recipe_id}`
   - `model_version` = `v1.0-{dispatch_sha[:7]} ({date})`
6. SHAP top-K indicators are embedded (10 per recipe).
7. Disclosures block is embedded verbatim from honest-disclosures.json.

This test exercises the bake against the live qgi-data inputs on main.
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
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import bake_ml_recipes_for_frontend as bake  # noqa: E402
from hybrid_dispatch import load_dispatch  # noqa: E402
from verify_dispatch_sha import EXPECTED_DISPATCH_SHA  # noqa: E402

# Sibling qgi-data + qgi-ml paths
DATA_ROOT = REPO_ROOT.parent / "qgi-data"
DISPATCH_JSON = REPO_ROOT / "config" / "hybrid_architecture_dispatch.json"
TEAR_SHEETS_JSON = DATA_ROOT / "reference" / "tear-sheets-2026-05.json"
HONEST_DISCLOSURES_JSON = DATA_ROOT / "reference" / "honest-disclosures-2026-05-11.json"
SHAP_JSON = DATA_ROOT / "reference" / "shap-fingerprint-2026-05.json"


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tear_sheets_doc() -> dict:
    if not TEAR_SHEETS_JSON.exists():
        pytest.skip(f"tear-sheets JSON not found at {TEAR_SHEETS_JSON}")
    return json.loads(TEAR_SHEETS_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def honest_disclosures_doc() -> dict:
    if not HONEST_DISCLOSURES_JSON.exists():
        pytest.skip(f"honest-disclosures JSON not found at {HONEST_DISCLOSURES_JSON}")
    return json.loads(HONEST_DISCLOSURES_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def shap_doc() -> dict:
    if not SHAP_JSON.exists():
        pytest.skip(f"SHAP fingerprint not found at {SHAP_JSON}")
    return json.loads(SHAP_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dispatch_sha() -> str:
    return load_dispatch(DISPATCH_JSON).sha256


@pytest.fixture(scope="module")
def stack(
    tear_sheets_doc: dict,
    honest_disclosures_doc: dict,
    shap_doc: dict,
    dispatch_sha: str,
) -> dict:
    return bake.build_stack(
        tear_sheets_doc=tear_sheets_doc,
        honest_disclosures_doc=honest_disclosures_doc,
        shap_doc=shap_doc,
        dispatch_sha=dispatch_sha,
        source_artifacts=[],
        generated_at="2026-05-11T16:00:00Z",
    )


@pytest.fixture(scope="module")
def by_recipe(stack: dict) -> dict[str, dict]:
    return {r["recipe_id"]: r for r in stack["recipes"]}


# ----------------------------------------------------------------------------
# Top-4 contract
# ----------------------------------------------------------------------------


def test_top_4_recipes_baked(stack: dict):
    assert stack["metadata"]["n_recipes"] == 4
    assert len(stack["recipes"]) == 4


def test_recipe_ids_match_top_4(by_recipe: dict[str, dict]):
    assert set(by_recipe.keys()) == set(bake.TOP_4_RECIPES)


def test_recipe_order_matches_top_4_canonical(stack: dict):
    """Order matters for deterministic byte-level output; TOP_4_RECIPES is the
    canonical order (civil_war, multilateral, elections, bilateral)."""
    actual = [r["recipe_id"] for r in stack["recipes"]]
    assert tuple(actual) == bake.TOP_4_RECIPES


# ----------------------------------------------------------------------------
# Asas mini-Majles (#656) interpretation_hint values
# ----------------------------------------------------------------------------


def test_interpretation_hint_per_recipe_matches_majles_decision(by_recipe: dict[str, dict]):
    """Per the #656 DECISION on 2026-05-11."""
    assert by_recipe["civil_war_and_insurgency"]["interpretation_hint"] == "risk_elevation"
    assert by_recipe["multilateral_agreement"]["interpretation_hint"] == "ambiguous"
    assert by_recipe["elections_and_voting"]["interpretation_hint"] == "ambiguous"
    assert by_recipe["bilateral_treaty"]["interpretation_hint"] == "ambiguous"


def test_only_civil_war_is_risk_elevation(stack: dict):
    """Lone unambiguous-direction recipe in the top-4 ship list."""
    risk_elev = [r for r in stack["recipes"] if r["interpretation_hint"] == "risk_elevation"]
    assert len(risk_elev) == 1
    assert risk_elev[0]["recipe_id"] == "civil_war_and_insurgency"


def test_no_engagement_signal_in_default_bake(stack: dict):
    """The 2-2 tie-break default produces zero `engagement_signal` recipes.
    If founder overrides via DECISION option B or C, this test will need to
    update — and that update is the right place to surface the override."""
    eng = [r for r in stack["recipes"] if r["interpretation_hint"] == "engagement_signal"]
    assert eng == []


def test_all_hints_in_canonical_enum_set(stack: dict):
    for r in stack["recipes"]:
        assert r["interpretation_hint"] in bake.VALID_INTERPRETATION_HINTS, r["recipe_id"]


# ----------------------------------------------------------------------------
# F-H-1 item 4 deploy-gate alignment
# ----------------------------------------------------------------------------


def test_dispatch_sha_matches_expected_on_main(stack: dict, dispatch_sha: str):
    """The bake's dispatch_sha must equal EXPECTED_DISPATCH_SHA on main —
    the same gate the F-H-1 item 4 deploy-time verifier (#648) enforces."""
    assert stack["metadata"]["dispatch_sha"] == EXPECTED_DISPATCH_SHA
    assert stack["metadata"]["dispatch_sha"] == dispatch_sha


def test_sha_mismatch_raises_value_error(
    tear_sheets_doc: dict,
    honest_disclosures_doc: dict,
    shap_doc: dict,
):
    """Passing a wrong dispatch SHA must fail fast with the F-H-4 rotation
    guidance — same defensive posture as #648's verify_dispatch_sha."""
    with pytest.raises(ValueError) as exc_info:
        bake.build_stack(
            tear_sheets_doc=tear_sheets_doc,
            honest_disclosures_doc=honest_disclosures_doc,
            shap_doc=shap_doc,
            dispatch_sha="0" * 64,
            source_artifacts=[],
        )
    msg = str(exc_info.value)
    assert "dispatch_sha mismatch" in msg
    assert "F-H-4" in msg


# ----------------------------------------------------------------------------
# Schema completeness + derivation correctness
# ----------------------------------------------------------------------------

REQUIRED_RECIPE_FIELDS = [
    "recipe_id",
    "display_name",
    "tier",
    "architecture",
    "loco_auc",
    "n_pos_loco",
    "assignment_confidence",
    "in_sample_f1_ece",
    "in_sample_f2_auc",
    "in_sample_f2_ci_lower",
    "in_sample_f2_ci_upper",
    "ece_overall",
    "ece_high_cohort",
    "ece_mid_cohort",
    "ece_low_cohort",
    "zero_positive_cohort_flag",
    "anchor_ahi_value",
    "anchor_ahi_status",
    "anchor_ahi_n_evaluable",
    "anchor_ahi_reason",
    "advisory_only_flag",
    "f_rule_anomaly_flag",
    "top_1_training_country",
    "top_1_training_country_share",
    "concentration_alert_level",
    "interpretation_hint",
    "mechanism_narrative",
    "mechanism_narrative_excerpt",
    "buyer_disclosure_recommendation",
    "open_followups",
    "paper_section_anchor",
    "top_k_indicators",
    "model_version",
]


def test_every_recipe_has_all_required_fields(stack: dict):
    for r in stack["recipes"]:
        missing = [f for f in REQUIRED_RECIPE_FIELDS if f not in r]
        assert not missing, f"{r['recipe_id']} missing fields: {missing}"


def test_display_name_derivation(by_recipe: dict[str, dict]):
    """Spaces + sentence-case from recipe_id slug."""
    assert by_recipe["civil_war_and_insurgency"]["display_name"] == "Civil war and insurgency"
    assert by_recipe["multilateral_agreement"]["display_name"] == "Multilateral agreement"


def test_paper_section_anchor_derivation(by_recipe: dict[str, dict]):
    for rid, r in by_recipe.items():
        assert r["paper_section_anchor"] == f"section-4-{rid}"


def test_model_version_includes_short_sha(by_recipe: dict[str, dict]):
    short_sha = EXPECTED_DISPATCH_SHA[:7]
    for r in by_recipe.values():
        assert short_sha in r["model_version"]
        assert "2026-05-11" in r["model_version"]


def test_ece_overall_equals_in_sample_f1_ece(stack: dict):
    """Schema synonym — ece_overall is the same value as in_sample_f1_ece."""
    for r in stack["recipes"]:
        assert r["ece_overall"] == r["in_sample_f1_ece"], r["recipe_id"]


# ----------------------------------------------------------------------------
# Derivation: concentration_alert_level
# ----------------------------------------------------------------------------


def test_concentration_alert_civil_war_caution(by_recipe: dict[str, dict]):
    """Syria 22.2% → caution (between 20% and 30%)."""
    assert by_recipe["civil_war_and_insurgency"]["concentration_alert_level"] == "caution"


def test_concentration_alert_multilateral_none(by_recipe: dict[str, dict]):
    """multilateral_agreement has top_1=None ('not in concentration audit') → 'none'."""
    assert by_recipe["multilateral_agreement"]["top_1_training_country"] is None
    assert by_recipe["multilateral_agreement"]["concentration_alert_level"] == "none"


def test_concentration_alert_bilateral_caution(by_recipe: dict[str, dict]):
    """Colombia 25.0% → caution."""
    assert by_recipe["bilateral_treaty"]["concentration_alert_level"] == "caution"


def test_concentration_alert_thresholds_pure():
    """Unit-test the threshold function in isolation, independent of paper data."""
    assert bake._concentration_alert(None) == "none"
    assert bake._concentration_alert(0.15) == "low"
    assert bake._concentration_alert(0.20) == "caution"
    assert bake._concentration_alert(0.29) == "caution"
    assert bake._concentration_alert(0.30) == "HIGH"
    assert bake._concentration_alert(0.71) == "HIGH"


# ----------------------------------------------------------------------------
# Derivation: mechanism_narrative_excerpt
# ----------------------------------------------------------------------------


def test_excerpt_under_max_chars(by_recipe: dict[str, dict]):
    for r in by_recipe.values():
        # Excerpt must be no longer than the source narrative + 1 char
        # (the ellipsis appended in the no-sentence-boundary case)
        assert len(r["mechanism_narrative_excerpt"]) <= len(r["mechanism_narrative"]) + 1
        assert len(r["mechanism_narrative_excerpt"]) <= bake.MECHANISM_EXCERPT_MAX_CHARS + 1


def test_excerpt_short_narrative_unchanged():
    """If the narrative is already under the cap, excerpt is the full narrative."""
    short = "First sentence. Second one."
    assert bake._mechanism_excerpt(short) == short


def test_excerpt_cuts_at_sentence_boundary():
    """Excerpt prefers a period boundary near the cap to avoid orphan clauses."""
    long_text = ("Sentence one is here. " * 30).strip()  # ~660 chars
    excerpt = bake._mechanism_excerpt(long_text, max_chars=200)
    # Sentence boundaries are every ~21 chars, so the boundary cut should
    # appear within the first 200 chars and end with "."
    assert excerpt.endswith(".")
    assert len(excerpt) <= 200


def test_excerpt_falls_back_to_ellipsis():
    """When no sentence boundary near max_chars, fall back to truncate+ellipsis."""
    long_no_period = "a" * 600  # no period anywhere
    excerpt = bake._mechanism_excerpt(long_no_period, max_chars=300)
    assert excerpt.endswith("…")
    assert len(excerpt) == 301  # 300 chars + 1 ellipsis


# ----------------------------------------------------------------------------
# SHAP top-K embedding
# ----------------------------------------------------------------------------


def test_top_k_indicators_count(by_recipe: dict[str, dict]):
    for r in by_recipe.values():
        assert len(r["top_k_indicators"]) == 10, r["recipe_id"]


def test_top_k_indicators_have_required_fields(by_recipe: dict[str, dict]):
    expected_fields = {"rank", "indicator_id", "mean_abs_shap", "fixed_effect_suspect"}
    for r in by_recipe.values():
        for tk in r["top_k_indicators"]:
            assert set(tk.keys()) == expected_fields, r["recipe_id"]


def test_top_k_strips_diagnostic_fields(by_recipe: dict[str, dict]):
    """The bake intentionally drops diagnostic SHAP fields (variance_ratio,
    within_country_std_median, rationale) — frontend doesn't render them."""
    for r in by_recipe.values():
        for tk in r["top_k_indicators"]:
            assert "variance_ratio_vs_panel_median" not in tk, r["recipe_id"]
            assert "within_country_std_median" not in tk, r["recipe_id"]
            assert "rationale" not in tk, r["recipe_id"]


# ----------------------------------------------------------------------------
# Disclosures + metadata
# ----------------------------------------------------------------------------


def test_disclosures_block_embedded_verbatim(
    stack: dict,
    honest_disclosures_doc: dict,
):
    """The frontend renders the disclosures block; embedding verbatim avoids
    any silent re-encoding and lets the doc evolve in qgi-data without
    re-baking until the next pre-reg amendment."""
    assert stack["disclosures"] == honest_disclosures_doc


def test_metadata_schema_version(stack: dict):
    assert stack["metadata"]["schema_version"] == "1.0"


def test_metadata_top_4_listed(stack: dict):
    assert tuple(stack["metadata"]["top_4_recipes"]) == bake.TOP_4_RECIPES


def test_metadata_interpretation_hint_decision_path(stack: dict):
    """Forward-pointer to the Asas mini-Majles DECISION file in qgi-docs."""
    assert "DECISION" in stack["metadata"]["interpretation_hint_decision"]
    assert "2026-05-11_Asas_interpretation_hint" in stack["metadata"]["interpretation_hint_decision"]


# ----------------------------------------------------------------------------
# Missing-recipe guardrail
# ----------------------------------------------------------------------------


def test_missing_top_4_recipe_raises(
    honest_disclosures_doc: dict,
    shap_doc: dict,
    dispatch_sha: str,
):
    """If tear-sheets is missing a top-4 recipe (e.g. paper edit changed the
    recipe set), the bake fails with a clear error naming the missing ones."""
    incomplete_tear_sheets = {
        "schema_version": "1.0",
        "n_recipes": 1,
        "recipes": [
            r for r in [
                {"recipe_id": "civil_war_and_insurgency", "tier": "STRONG"},  # only one
            ]
        ],
    }
    with pytest.raises(ValueError) as exc_info:
        bake.build_stack(
            tear_sheets_doc=incomplete_tear_sheets,
            honest_disclosures_doc=honest_disclosures_doc,
            shap_doc=shap_doc,
            dispatch_sha=dispatch_sha,
            source_artifacts=[],
        )
    msg = str(exc_info.value)
    assert "missing top-4" in msg.lower()
    assert "multilateral_agreement" in msg or "elections_and_voting" in msg


def test_unknown_recipe_id_in_top_4_list_raises(
    honest_disclosures_doc: dict,
    shap_doc: dict,
    dispatch_sha: str,
):
    """If INTERPRETATION_HINTS is missing a recipe ID that's in TOP_4_RECIPES
    (e.g. a typo'd recipe was added to TOP_4 but not to the hints dict), the
    bake fails per-recipe with a clear error."""
    fake_tear = {
        "schema_version": "1.0",
        "n_recipes": 1,
        "recipes": [{
            "recipe_id": "fake_recipe_not_in_hints",
            "tier": "STRONG",
            "architecture": "D2",
            "loco_auc": 0.5,
            "n_pos_loco": 5,
            "assignment_confidence": "HIGH",
            "in_sample_f1_ece": 0.01,
            "in_sample_f2_auc": 0.7,
            "in_sample_f2_ci_lower": 0.6,
            "in_sample_f2_ci_upper": 0.8,
            "top_1_training_country": "x",
            "top_1_training_country_share": 0.1,
            "cohort_ece": {"high": 0.01, "mid": 0.02, "low": 0.03},
            "zero_positive_cohort_flag": None,
            "per_recipe_anchor_ahi": None,
            "per_recipe_anchor_ahi_reason": "Not measured",
            "f_h_3_advisory_only": False,
            "f_rule_anomaly": False,
            "mechanism_narrative": "test narrative",
            "buyer_disclosure_recommendation": "test",
            "open_followups": [],
        }],
    }
    with pytest.raises(ValueError) as exc_info:
        bake.build_recipe_entry(
            fake_tear["recipes"][0],
            shap_doc,
            "0" * 64,
            "2026-05-11T00:00:00Z",
        )
    assert "not in INTERPRETATION_HINTS" in str(exc_info.value)
