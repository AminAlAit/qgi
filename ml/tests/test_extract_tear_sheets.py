"""Tests for `scripts.extract_tear_sheets` (Stage 5 paper → JSON for #643 bake).

Locks the contract:
1. The parser finds exactly the 13 LOCKED recipes post-KI-2 (no more, no less).
2. EXPECTED_LOCKED_RECIPES matches the actual Stage 5 paper Section 4 contents
   on this branch — guards against silent paper edits per F-H-4 discipline.
3. Per-recipe schema completeness (every required field is present + typed
   correctly across the 13-recipe set).
4. Boundary cases parse correctly:
   - `civil_war_and_insurgency` (canonical D2 STRONG with measured AHI)
   - `multilateral_agreement` (D5 STRONG architecture-rescue case;
     "not in concentration audit" country handling)
   - `epidemic_and_pandemic` (the lone f_rule_anomaly + ADVISORY-ONLY)
   - `mass_protest` (LEAK-rescue nested parenthetical in LOCO line)
   - `humanitarian_crisis` (fully bold-wrapped Top-1 country line)
   - `terrorist_attack` (measured AHI + ADVISORY-ONLY)
5. Per Nasrin's binding rule: when `per_recipe_anchor_ahi is None`, the
   `per_recipe_anchor_ahi_reason` field is non-null + contains "Not measured".

Failure modes:
- Paper recipe set drifts from EXPECTED_LOCKED_RECIPES → ValueError + clear
  message naming the missing + extra recipes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import extract_tear_sheets as ets  # noqa: E402

# Resolve the live Stage 5 paper path (sibling docs-specs repo).
PAPER_PATH = (
    REPO_ROOT / "docs" / "specs" / "methodology"
    / "stage-5-buyer-disclosure-methodology-paper.md"
)


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def paper_text() -> str:
    """Live Stage 5 paper text on the docs-specs main branch."""
    if not PAPER_PATH.exists():
        pytest.skip(f"Stage 5 paper not found at {PAPER_PATH}")
    return PAPER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed(paper_text: str) -> list[dict]:
    return ets.extract_tear_sheets(paper_text)


@pytest.fixture(scope="module")
def by_recipe(parsed: list[dict]) -> dict[str, dict]:
    return {r["recipe_id"]: r for r in parsed}


# ----------------------------------------------------------------------------
# Recipe-set contract
# ----------------------------------------------------------------------------


def test_parses_exactly_13_recipes(parsed: list[dict]):
    """Post-KI-2: 13 LOCKed recipes ship. territorial_disputes (FALSIFIED) is
    skipped even though its tear-sheet header is struck-through in the paper."""
    assert len(parsed) == 13


def test_recipe_set_matches_expected(by_recipe: dict[str, dict]):
    """The recipe IDs found in the paper must exactly equal
    EXPECTED_LOCKED_RECIPES — guards against silent paper edits."""
    assert set(by_recipe.keys()) == ets.EXPECTED_LOCKED_RECIPES


def test_territorial_disputes_skipped(by_recipe: dict[str, dict]):
    """The struck-through FALSIFIED recipe is not in the output."""
    assert "territorial_disputes" not in by_recipe


def test_mismatch_raises_clear_error():
    """A paper missing a recipe raises ValueError with diagnostic detail."""
    fake_paper = "#### `only_one_recipe` — D2 STRONG\n\n**Architecture:** D2\n"
    with pytest.raises(ValueError) as exc_info:
        ets.extract_tear_sheets(fake_paper)
    msg = str(exc_info.value)
    assert "Missing" in msg
    assert "Extra" in msg
    assert "F-H-4" in msg


# ----------------------------------------------------------------------------
# Per-recipe schema completeness
# ----------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "recipe_id",
    "tier",
    "architecture",
    "loco_auc",
    "n_pos_loco",
    "assignment_confidence",
    "in_sample_f1_ece",
    "in_sample_f2_auc",
    "in_sample_f2_ci_lower",
    "in_sample_f2_ci_upper",
    "top_1_training_country",
    "top_1_training_country_share",
    "cohort_ece",
    "zero_positive_cohort_flag",
    "per_recipe_anchor_ahi",
    "per_recipe_anchor_ahi_reason",
    "f_h_3_advisory_only",
    "f_rule_anomaly",
    "mechanism_narrative",
    "buyer_disclosure_recommendation",
    "open_followups",
]


def test_every_recipe_has_all_required_fields(parsed: list[dict]):
    for r in parsed:
        missing = [f for f in REQUIRED_FIELDS if f not in r]
        assert not missing, f"{r['recipe_id']} missing fields: {missing}"


def test_architecture_in_canonical_set(parsed: list[dict]):
    for r in parsed:
        assert r["architecture"] in ("D2", "D5"), r["recipe_id"]


def test_tier_in_canonical_set(parsed: list[dict]):
    for r in parsed:
        assert r["tier"] in ("STRONG", "MODERATE", "MARGINAL"), r["recipe_id"]


def test_assignment_confidence_in_canonical_set(parsed: list[dict]):
    for r in parsed:
        assert r["assignment_confidence"] in ("HIGH", "MODERATE", "LOW"), r["recipe_id"]


def test_cohort_ece_has_three_keys(parsed: list[dict]):
    for r in parsed:
        keys = set(r["cohort_ece"].keys())
        assert keys == {"high", "mid", "low"}, r["recipe_id"]
        for v in r["cohort_ece"].values():
            assert isinstance(v, float)


def test_open_followups_is_list(parsed: list[dict]):
    for r in parsed:
        assert isinstance(r["open_followups"], list), r["recipe_id"]


def test_mechanism_narrative_nonempty(parsed: list[dict]):
    for r in parsed:
        assert isinstance(r["mechanism_narrative"], str)
        assert len(r["mechanism_narrative"]) > 50, r["recipe_id"]


# ----------------------------------------------------------------------------
# Per Nasrin's binding rule: "Not measured" must be explicit text, not blank
# ----------------------------------------------------------------------------


def test_when_ahi_is_none_reason_is_set(parsed: list[dict]):
    """When per_recipe_anchor_ahi is None, the reason field MUST be a
    non-empty string per Nasrin's buyer-disclosure rule."""
    for r in parsed:
        if r["per_recipe_anchor_ahi"] is None:
            reason = r["per_recipe_anchor_ahi_reason"]
            assert isinstance(reason, str), r["recipe_id"]
            assert len(reason) > 0, r["recipe_id"]
            # Per Nasrin's rule, the explicit text "Not measured" appears
            assert "Not measured" in reason, (
                f"{r['recipe_id']}: AHI reason must contain 'Not measured' verbatim; "
                f"got {reason!r}"
            )


def test_when_ahi_is_set_reason_is_null(parsed: list[dict]):
    """Symmetric check: measured AHI has no reason text."""
    for r in parsed:
        if r["per_recipe_anchor_ahi"] is not None:
            assert r["per_recipe_anchor_ahi_reason"] is None, r["recipe_id"]
            assert isinstance(r["per_recipe_anchor_ahi"], float)


# ----------------------------------------------------------------------------
# Boundary-case parses (the recipes that exercise the parser's weird paths)
# ----------------------------------------------------------------------------


def test_civil_war_and_insurgency_values(by_recipe: dict[str, dict]):
    """Canonical D2 STRONG, measured AHI, Syria top-1 22.2%."""
    r = by_recipe["civil_war_and_insurgency"]
    assert r["architecture"] == "D2"
    assert r["tier"] == "STRONG"
    assert r["loco_auc"] == pytest.approx(0.7686)
    assert r["n_pos_loco"] == 7
    assert r["assignment_confidence"] == "MODERATE"
    assert r["top_1_training_country"] == "syria"
    assert r["top_1_training_country_share"] == pytest.approx(0.222)
    # F2 CI bounds — the bracket regex is the field most likely to silently
    # regress if the paper's F2-line format changes (e.g. " — " vs " - ").
    assert r["in_sample_f2_auc"] == pytest.approx(0.8840)
    assert r["in_sample_f2_ci_lower"] == pytest.approx(0.794)
    assert r["in_sample_f2_ci_upper"] == pytest.approx(0.942)
    assert r["per_recipe_anchor_ahi"] == pytest.approx(0.1052)
    assert r["per_recipe_anchor_ahi_reason"] is None
    assert r["f_h_3_advisory_only"] is False
    assert r["f_rule_anomaly"] is False


def test_multilateral_agreement_not_in_audit(by_recipe: dict[str, dict]):
    """The 'not in concentration audit' variant → country fields are None."""
    r = by_recipe["multilateral_agreement"]
    assert r["architecture"] == "D5"
    assert r["tier"] == "STRONG"
    assert r["top_1_training_country"] is None
    assert r["top_1_training_country_share"] is None


def test_epidemic_and_pandemic_is_the_lone_f_rule_anomaly(parsed: list[dict]):
    """Post-KI-2, exactly one LOCKed recipe carries f_rule_anomaly: epidemic_and_pandemic."""
    flagged = [r for r in parsed if r["f_rule_anomaly"]]
    assert len(flagged) == 1
    assert flagged[0]["recipe_id"] == "epidemic_and_pandemic"


def test_epidemic_and_pandemic_values(by_recipe: dict[str, dict]):
    """The hybrid F2 anomaly recipe: STRONG via LOCO 0.8824, but in-sample F2 fails."""
    r = by_recipe["epidemic_and_pandemic"]
    assert r["architecture"] == "D5"
    assert r["tier"] == "STRONG"
    assert r["loco_auc"] == pytest.approx(0.8824)
    assert r["n_pos_loco"] == 1
    assert r["assignment_confidence"] == "LOW"
    assert r["f_h_3_advisory_only"] is True
    assert r["f_rule_anomaly"] is True
    # The F2 line says 0.5627 < 0.57 threshold (fails) — value still captured
    assert r["in_sample_f2_auc"] == pytest.approx(0.5627)


def test_mass_protest_leak_rescue_loco_extracted(by_recipe: dict[str, dict]):
    """LOCO line has an embedded `**0.5847 (rescued from D2 LEAK 0.4449)**`
    parenthetical inside bold. Parser must extract 0.5847 (not 0.4449)."""
    r = by_recipe["mass_protest"]
    assert r["loco_auc"] == pytest.approx(0.5847)
    assert r["n_pos_loco"] == 2
    assert r["assignment_confidence"] == "LOW"


def test_humanitarian_crisis_fully_bold_country_line(by_recipe: dict[str, dict]):
    """Top-1 line is fully bold-wrapped on humanitarian_crisis:
    `**Top-1 training country:** **venezuela 71.4% (HIGH concentration — flagged)**`"""
    r = by_recipe["humanitarian_crisis"]
    assert r["top_1_training_country"] == "venezuela"
    assert r["top_1_training_country_share"] == pytest.approx(0.714)


def test_terrorist_attack_measured_ahi_and_advisory(by_recipe: dict[str, dict]):
    r = by_recipe["terrorist_attack"]
    assert r["per_recipe_anchor_ahi"] == pytest.approx(0.4322)
    assert r["per_recipe_anchor_ahi_reason"] is None
    assert r["f_h_3_advisory_only"] is True
    assert r["n_pos_loco"] == 1


def test_advisory_only_count(parsed: list[dict]):
    """Post-KI-1: ADVISORY-ONLY iff n_pos_LOCO == 1. Four such recipes:
    terrorist_attack, energy_policy, epidemic_and_pandemic, human_rights_violation."""
    advisory = sorted(r["recipe_id"] for r in parsed if r["f_h_3_advisory_only"])
    assert advisory == [
        "energy_policy",
        "epidemic_and_pandemic",
        "human_rights_violation",
        "terrorist_attack",
    ]


def test_n_pos_loco_eq_1_iff_advisory_only(parsed: list[dict]):
    """F-H-3 invariant (post-KI-1): advisory_only IFF n_pos_loco == 1."""
    for r in parsed:
        assert r["f_h_3_advisory_only"] == (r["n_pos_loco"] == 1), r["recipe_id"]


# ----------------------------------------------------------------------------
# Deterministic output
# ----------------------------------------------------------------------------


def test_output_sorted_by_recipe_id(parsed: list[dict]):
    """Output is sorted alphabetically for deterministic byte-level diffs."""
    ids = [r["recipe_id"] for r in parsed]
    assert ids == sorted(ids)
