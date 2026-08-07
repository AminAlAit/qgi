"""Bake top-4 ML recipes into a frontend-consumable JSON.

Per qgi-aws-tf ticket #643 + 2026-05-11 Majles Topic 5 action item AI-5.1.

This is the **master bake script** that produces the single stack consumed by
the V2 frontend routes (`/precedents-v2-{a,b}` + `/signals-v2-{a,b}`). It
composes the post-KI-2 dispatch state, the Stage 5 tear-sheets, the Asas
mini-Majles `interpretation_hint` votes (#656), the SHAP per-recipe top-K
indicator fingerprint, the dispatch JSON SHA, and the Stage 5 Section 5
honest-disclosures artifact.

Inputs (all paths relative to the qgi monorepo layout):
- ``qgi-data/reference/tear-sheets-2026-05.json`` (#644 output; primary)
- ``qgi-data/reference/honest-disclosures-2026-05-11.json`` (Section 5 extract)
- ``qgi-data/reference/shap-fingerprint-2026-05.json`` (per-recipe top-K)
- ``qgi-ml/config/hybrid_architecture_dispatch.json`` (dispatch SHA pin)

Output schema (per `frontend-resurfacing-plan-2026-05-11.md` §schema):
- ``metadata`` block (schema_version, generated_at, dispatch_sha, source_artifacts)
- ``recipes`` array (top-4: civil_war_and_insurgency, multilateral_agreement,
  elections_and_voting, bilateral_treaty)
- ``disclosures`` block (verbatim from honest-disclosures.json)

Outputs written to:
- ``qgi-data/reference/ml-recipe-stack-2026-05.json`` (dated canonical reference)
- ``qgi-frontend/data/ml-recipe-stack.json`` (frontend-baked snapshot; no date
  in filename — replaced on each bake)

Usage:
    python scripts/bake_ml_recipes_for_frontend.py \\
        --tear-sheets ../qgi-data/reference/tear-sheets-2026-05.json \\
        --honest-disclosures ../qgi-data/reference/honest-disclosures-2026-05-11.json \\
        --shap-fingerprint ../qgi-data/reference/shap-fingerprint-2026-05.json \\
        --dispatch ../qgi-ml/config/hybrid_architecture_dispatch.json \\
        --output-canonical ../qgi-data/reference/ml-recipe-stack-2026-05.json \\
        --output-frontend ../qgi-frontend/data/ml-recipe-stack.json

Per resurfacing plan Q11 (default-fallback rule) + #656 DECISION (Section 2),
the `interpretation_hint` values are pinned to the Asas mini-Majles outcome.
Founder may override before public launch; re-run cost is <30 min.

Per #648 (F-H-1 item 4): the bake_ml_recipes step does NOT trigger the
deploy gate — that runs separately on push to main. But this bake's
metadata.dispatch_sha must match the EXPECTED_DISPATCH_SHA pinned in
scripts/verify_dispatch_sha.py at bake time. The bake fails fast if not.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from hybrid_dispatch import load_dispatch  # noqa: E402
from verify_dispatch_sha import EXPECTED_DISPATCH_SHA  # noqa: E402

# Top-4 recipes ship to V2 frontend per Majles 2026-05-11 Topic 5 vote (4-0).
TOP_4_RECIPES: tuple[str, ...] = (
    "civil_war_and_insurgency",
    "multilateral_agreement",
    "elections_and_voting",
    "bilateral_treaty",
)

# interpretation_hint enum values per #656 Asas mini-Majles DECISION
# (2 unanimous + 2 tied → tie-break to `ambiguous`). Founder may override
# before public launch via DECISION Section 3 options A/B/C/D.
INTERPRETATION_HINTS: dict[str, str] = {
    "civil_war_and_insurgency": "risk_elevation",  # 4-0 UNANIMOUS
    "multilateral_agreement": "ambiguous",          # 2-2 tie → tie-break
    "elections_and_voting": "ambiguous",            # 4-0 UNANIMOUS
    "bilateral_treaty": "ambiguous",                # 2-2 tie → tie-break
}

VALID_INTERPRETATION_HINTS = frozenset({"risk_elevation", "engagement_signal", "ambiguous"})

# Concentration-alert thresholds (per Stage 5 paper parentheticals: "low" / "caution-level" / "HIGH")
# Used to derive concentration_alert_level from top_1_training_country_share.
CONCENTRATION_HIGH_THRESHOLD = 0.30
CONCENTRATION_CAUTION_THRESHOLD = 0.20

# Mechanism narrative excerpt: first N chars at sentence boundary
MECHANISM_EXCERPT_MAX_CHARS = 280


def _sha256_file(path: Path) -> str:
    """SHA-256 over the raw file bytes (for source_artifacts metadata)."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _display_name(recipe_id: str) -> str:
    """`civil_war_and_insurgency` -> `Civil war and insurgency`."""
    return recipe_id.replace("_", " ").capitalize()


def _concentration_alert(share: float | None) -> str:
    """Map top-1 share to concentration alert level for frontend rendering.

    Thresholds match the Stage 5 paper's prose labels in Section 4 parentheticals:
    - HIGH:    share >= 0.30
    - caution: 0.20 <= share < 0.30
    - low:     share < 0.20
    - none:    share is None (recipe not in concentration audit)
    """
    if share is None:
        return "none"
    if share >= CONCENTRATION_HIGH_THRESHOLD:
        return "HIGH"
    if share >= CONCENTRATION_CAUTION_THRESHOLD:
        return "caution"
    return "low"


def _mechanism_excerpt(narrative: str, max_chars: int = MECHANISM_EXCERPT_MAX_CHARS) -> str:
    """Truncate the mechanism narrative at a sentence boundary near max_chars.

    Frontend tear-sheets display the excerpt; full narrative is reachable via
    `paper_section_anchor` deep-link. The boundary heuristic: cut at the last
    `. ` at or before max_chars; if no such cut exists, return the first
    max_chars chars + ellipsis.
    """
    if len(narrative) <= max_chars:
        return narrative
    head = narrative[:max_chars]
    cut = head.rfind(". ")
    if cut >= max_chars // 2:  # only cut if we keep at least half the text
        return narrative[: cut + 1]
    return head.rstrip() + "…"


def _top_k_for_recipe(
    shap_doc: dict[str, Any],
    recipe_id: str,
    k: int = 10,
) -> list[dict[str, Any]]:
    """Pull the top-K SHAP indicators for a recipe; strip diagnostic fields
    that the frontend doesn't need to display (variance_ratio etc.)."""
    recipe_block = shap_doc.get("recipes", {}).get(recipe_id, {})
    raw_top_k = recipe_block.get("top_k", [])[:k]
    return [
        {
            "rank": entry["rank"],
            "indicator_id": entry["indicator_id"],
            "mean_abs_shap": entry["mean_abs_shap"],
            "fixed_effect_suspect": entry["fixed_effect_suspect"],
        }
        for entry in raw_top_k
    ]


def build_recipe_entry(
    tear_sheet: dict[str, Any],
    shap_doc: dict[str, Any],
    dispatch_sha: str,
    generated_at: str,
) -> dict[str, Any]:
    """Compose one frontend-shipped recipe entry from the per-source inputs."""
    recipe_id = tear_sheet["recipe_id"]
    if recipe_id not in INTERPRETATION_HINTS:
        raise ValueError(
            f"recipe_id {recipe_id!r} not in INTERPRETATION_HINTS — "
            f"top-4 ship list does not include this recipe. If shipping a "
            f"new recipe to V2, add the Asas-vote value first per #656."
        )
    hint = INTERPRETATION_HINTS[recipe_id]
    if hint not in VALID_INTERPRETATION_HINTS:
        raise ValueError(
            f"interpretation_hint {hint!r} for {recipe_id} not in "
            f"{sorted(VALID_INTERPRETATION_HINTS)}"
        )
    return {
        "recipe_id": recipe_id,
        "display_name": _display_name(recipe_id),
        "tier": tear_sheet["tier"],
        "architecture": tear_sheet["architecture"],
        "loco_auc": tear_sheet["loco_auc"],
        "n_pos_loco": tear_sheet["n_pos_loco"],
        "assignment_confidence": tear_sheet["assignment_confidence"],
        "in_sample_f1_ece": tear_sheet["in_sample_f1_ece"],
        "in_sample_f2_auc": tear_sheet["in_sample_f2_auc"],
        "in_sample_f2_ci_lower": tear_sheet["in_sample_f2_ci_lower"],
        "in_sample_f2_ci_upper": tear_sheet["in_sample_f2_ci_upper"],
        # ece_overall is currently a schema-level synonym for in_sample_f1_ece
        # (Stage 5 paper records one ECE per recipe). If Stage 6 ever splits
        # them (e.g. cohort-aggregated vs F1-cohort-stratified), the bake
        # must compute ece_overall separately rather than aliasing.
        "ece_overall": tear_sheet["in_sample_f1_ece"],
        "ece_high_cohort": tear_sheet["cohort_ece"]["high"],
        "ece_mid_cohort": tear_sheet["cohort_ece"]["mid"],
        "ece_low_cohort": tear_sheet["cohort_ece"]["low"],
        "zero_positive_cohort_flag": tear_sheet["zero_positive_cohort_flag"],
        "anchor_ahi_value": tear_sheet["per_recipe_anchor_ahi"],
        "anchor_ahi_status": (
            "measured" if tear_sheet["per_recipe_anchor_ahi"] is not None
            else "not_measured"
        ),
        # TODO(qgi-aws-tf#647): when extract_tear_sheets captures
        # n_evaluable from the Stage 5 paper, populate this field. Today the
        # tear-sheets schema doesn't carry it; null is the honest disclosure.
        "anchor_ahi_n_evaluable": None,
        "anchor_ahi_reason": tear_sheet["per_recipe_anchor_ahi_reason"],
        "advisory_only_flag": tear_sheet["f_h_3_advisory_only"],
        "f_rule_anomaly_flag": tear_sheet["f_rule_anomaly"],
        "top_1_training_country": tear_sheet["top_1_training_country"],
        "top_1_training_country_share": tear_sheet["top_1_training_country_share"],
        "concentration_alert_level": _concentration_alert(
            tear_sheet["top_1_training_country_share"]
        ),
        "interpretation_hint": hint,
        "mechanism_narrative": tear_sheet["mechanism_narrative"],
        "mechanism_narrative_excerpt": _mechanism_excerpt(
            tear_sheet["mechanism_narrative"]
        ),
        "buyer_disclosure_recommendation": tear_sheet["buyer_disclosure_recommendation"],
        "open_followups": tear_sheet["open_followups"],
        "paper_section_anchor": f"section-4-{recipe_id}",
        "top_k_indicators": _top_k_for_recipe(shap_doc, recipe_id),
        "model_version": f"v1.0-{dispatch_sha[:7]} ({generated_at[:10]})",
    }


def build_stack(
    tear_sheets_doc: dict[str, Any],
    honest_disclosures_doc: dict[str, Any],
    shap_doc: dict[str, Any],
    dispatch_sha: str,
    source_artifacts: list[dict[str, str]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Compose the full frontend-shipped ML recipe stack.

    Validates: dispatch_sha matches EXPECTED_DISPATCH_SHA (else fail fast);
    all 4 top-4 recipe IDs found in tear_sheets_doc; interpretation_hint
    values are in the canonical enum set.
    """
    if dispatch_sha != EXPECTED_DISPATCH_SHA:
        raise ValueError(
            f"dispatch_sha mismatch at bake time:\n"
            f"  passed:    {dispatch_sha}\n"
            f"  expected:  {EXPECTED_DISPATCH_SHA}\n"
            f"This is the same gate the #648 deploy-time verifier enforces. "
            f"Either re-run with the on-main dispatch JSON, or rotate "
            f"EXPECTED_DISPATCH_SHA in scripts/verify_dispatch_sha.py per "
            f"F-H-4 amendment discipline."
        )
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_id = {r["recipe_id"]: r for r in tear_sheets_doc["recipes"]}
    missing = [rid for rid in TOP_4_RECIPES if rid not in by_id]
    if missing:
        raise ValueError(
            f"tear_sheets_doc missing top-4 recipes: {missing}. "
            f"Tear-sheets has {sorted(by_id)}."
        )
    recipes = [
        build_recipe_entry(by_id[rid], shap_doc, dispatch_sha, generated_at)
        for rid in TOP_4_RECIPES
    ]
    return {
        "metadata": {
            "schema_version": "1.0",
            "generated_at": generated_at,
            "dispatch_sha": dispatch_sha,
            "n_recipes": len(recipes),
            "top_4_recipes": list(TOP_4_RECIPES),
            "source_artifacts": source_artifacts,
            "interpretation_hint_decision": (
                "qgi-docs/internal/majles/"
                "2026-05-11_Asas_interpretation_hint_DECISION.md"
            ),
        },
        "recipes": recipes,
        "disclosures": honest_disclosures_doc,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tear-sheets", type=Path, required=True)
    parser.add_argument("--honest-disclosures", type=Path, required=True)
    parser.add_argument("--shap-fingerprint", type=Path, required=True)
    parser.add_argument("--dispatch", type=Path, required=True)
    parser.add_argument("--output-canonical", type=Path, required=True)
    parser.add_argument("--output-frontend", type=Path, required=True)
    parser.add_argument(
        "--generated-at",
        default=None,
        help="ISO8601 timestamp for the metadata.generated_at field; "
        "defaults to now() in UTC. Override for deterministic output in tests.",
    )
    args = parser.parse_args()

    tear_sheets_doc = json.loads(args.tear_sheets.read_text(encoding="utf-8"))
    honest_disclosures_doc = json.loads(
        args.honest_disclosures.read_text(encoding="utf-8")
    )
    shap_doc = json.loads(args.shap_fingerprint.read_text(encoding="utf-8"))
    dispatch = load_dispatch(args.dispatch)
    dispatch_sha = dispatch.sha256
    source_artifacts = [
        {
            "path": str(p.as_posix()),
            "sha256": _sha256_file(p),
        }
        for p in (
            args.tear_sheets,
            args.honest_disclosures,
            args.shap_fingerprint,
            args.dispatch,
        )
    ]
    stack = build_stack(
        tear_sheets_doc=tear_sheets_doc,
        honest_disclosures_doc=honest_disclosures_doc,
        shap_doc=shap_doc,
        dispatch_sha=dispatch_sha,
        source_artifacts=source_artifacts,
        generated_at=args.generated_at,
    )
    payload = json.dumps(stack, indent=2, ensure_ascii=False) + "\n"
    args.output_canonical.parent.mkdir(parents=True, exist_ok=True)
    args.output_canonical.write_text(payload, encoding="utf-8")
    args.output_frontend.parent.mkdir(parents=True, exist_ok=True)
    args.output_frontend.write_text(payload, encoding="utf-8")
    print(
        f"Wrote {len(stack['recipes'])} top-4 recipe entries to:\n"
        f"  canonical: {args.output_canonical}\n"
        f"  frontend:  {args.output_frontend}\n"
        f"dispatch_sha pinned: {dispatch_sha[:16]}..."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
