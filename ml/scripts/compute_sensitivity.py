"""Sensitivity analysis for QGI Trajectory Engine (TE capability #5).

TE add-on #5: sensitivity ("what moves the score") — anti-causal firewall.
Per te-new-capabilities-spec.md §5 (locked 2026-05-24, chat QGI-R&D | 002).

Answers: "Which indicator is the score most responsive to, for this country?"
— a pure transform of the existing recipe-similarity-scores artifact.
No model re-fit, no panels needed.

## Method

The score is linear in per-indicator cosine:

    S = Σ wᵢ · cosᵢ     (SHAP-weighted arithmetic mean cosine)

so  ∂S / ∂cosᵢ = wᵢ.

Per indicator, report:

    marginal_points_per_unit  = wᵢ * 50
        (risk_score = 100*(S+1)/2; d(risk_score)/d(cosᵢ) = wᵢ * 50)

    headroom                  = wᵢ * (1 − cosᵢ)
        (how much the indicator currently drags the score below its ceiling)

    headroom_points           = headroom * 50
        (headroom expressed in 0–100 risk-score points)

Rank by headroom descending (most room to improve alignment first).

## Honesty gate — IRONCLAD anti-causal firewall (spec §5, binding)

Every artifact field + any UI copy MUST frame this as a property of the
scoring metric's structure, NEVER as policy advice.

Mandatory m8_r5_note (verbatim from spec §5):
    "Describes how the similarity SCORE responds to changes in indicator
    ALIGNMENT. The model is discriminative, not causal — this is NOT a claim
    that changing the real-world indicator changes real-world risk."

## Usage

    python scripts/compute_sensitivity.py \\
        --scores-file ../qgi-data/reference/recipe-similarity-scores-foreign_intervention-2021.json \\
        --output-dir ../qgi-data/reference/

Output:
    sensitivity-{recipe_id}-{eval_year}.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_country_sensitivity(
    country_entry: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compute per-indicator sensitivity for one country.

    Per spec §5: S = Σ wᵢ·cosᵢ, so ∂S/∂cosᵢ = wᵢ.

    marginal_points_per_unit = wᵢ * 50
    headroom                 = wᵢ * (1 − cosᵢ)
    headroom_points          = headroom * 50

    Ranked by headroom descending.

    Parameters
    ----------
    country_entry : dict — one entry from scores[country], with keys:
        cosine_similarity_S, risk_score, zone, per_indicator

    Returns
    -------
    List of dicts, one per indicator, sorted by headroom descending.
    Each dict: {indicator, marginal_points_per_unit, current_cosine,
                headroom, headroom_points}
    """
    per_ind = country_entry["per_indicator"]

    rows: list[dict[str, Any]] = []
    for ind, ind_data in per_ind.items():
        w = float(ind_data["weight"])
        cos = float(ind_data["cosine"])

        marginal_points_per_unit = w * 50.0
        headroom = w * (1.0 - cos)
        headroom_points = headroom * 50.0

        rows.append({
            "indicator": ind,
            "marginal_points_per_unit": marginal_points_per_unit,
            "current_cosine": cos,
            "headroom": headroom,
            "headroom_points": headroom_points,
        })

    # Rank by headroom descending (most room to improve alignment first)
    rows.sort(key=lambda r: r["headroom"], reverse=True)
    return rows


def compute_all_sensitivity(
    scores_data: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Compute per-country sensitivity for all countries in the scores artifact.

    Parameters
    ----------
    scores_data : dict — parsed recipe-similarity-scores-{recipe}-{year}.json

    Returns
    -------
    Dict mapping country name → sorted list of sensitivity dicts
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for country, entry in scores_data["scores"].items():
        result[country] = compute_country_sensitivity(entry)
    return result


# ---------------------------------------------------------------------------
# Artifact builder
# ---------------------------------------------------------------------------

# The IRONCLAD anti-causal m8_r5_note — verbatim from spec §5.
# This exact text is required; do not paraphrase.
_M8_R5_NOTE = (
    "Describes how the similarity SCORE responds to changes in indicator ALIGNMENT. "
    "The model is discriminative, not causal — this is NOT a claim that changing "
    "the real-world indicator changes real-world risk."
)


def build_output(
    scores_data: dict[str, Any],
    sensitivity: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Build the full sensitivity artifact dict.

    Parameters
    ----------
    scores_data : dict — parsed recipe-similarity-scores artifact
    sensitivity : dict — output of compute_all_sensitivity()

    Returns
    -------
    dict — the full artifact, ready for json.dumps
    """
    return {
        "recipe_id": scores_data["recipe_id"],
        "eval_year": int(scores_data["evaluation_year"]),
        "capability": "sensitivity",
        "capability_spec_section": "#5",
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "binding_provenance": (
            "docs/specs/internal/ops/ml-track/te-new-capabilities-spec.md §5 "
            "(locked 2026-05-24, chat QGI-R&D | 002). "
            "Pure transform of recipe-similarity-scores artifact; no model re-fit."
        ),
        "m8_r5_note": _M8_R5_NOTE,
        "headroom_interpretation": (
            "Headroom is measured from a country's CURRENT cosine to +1.0 (maximum "
            "alignment with the crisis profile). For a LOW-zone country (trajectory "
            "DIVERGING from the crisis profile, often anti-aligned cosine<0), large "
            "headroom therefore reflects PROTECTIVE DISTANCE from the profile — NOT "
            "vulnerability. Read headroom together with each country's score zone "
            "(see country_zone)."
        ),
        "method": (
            "Score S = Σ wᵢ·cosᵢ, so ∂S/∂cosᵢ = wᵢ. "
            "marginal_points_per_unit = wᵢ * 50 (risk_score = 100*(S+1)/2). "
            "headroom = wᵢ*(1−cosᵢ); headroom_points = headroom*50. "
            "Ranked by headroom descending."
        ),
        "selected_indicators": scores_data.get("selected_indicators", []),
        "shap_importance_normalized": scores_data.get("shap_importance_normalized", {}),
        "chosen_window": scores_data.get("chosen_window"),
        "n_countries": len(sensitivity),
        # Per-country score zone (LOW/MODERATE/HIGH), so a consumer can interpret
        # high headroom correctly (protective distance for LOW-zone countries).
        "country_zone": {c: scores_data["scores"][c].get("zone") for c in sensitivity},
        "sensitivity": sensitivity,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scores-file", type=Path, required=True,
        help="Path to recipe-similarity-scores-{recipe}-{year}.json.",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Output directory for sensitivity-{recipe}-{year}.json.",
    )
    return parser


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.scores_file, encoding="utf-8") as f:
        scores_data = json.load(f)

    recipe_id = scores_data["recipe_id"]
    eval_year = int(scores_data["evaluation_year"])
    n_countries = len(scores_data.get("scores", {}))

    print(f"Recipe: {recipe_id}, eval_year: {eval_year}, n_countries: {n_countries}")

    all_sens = compute_all_sensitivity(scores_data)
    artifact = build_output(scores_data, all_sens)

    out_path = args.output_dir / f"sensitivity-{recipe_id}-{eval_year}.json"
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")

    # Sanity print: highest-headroom indicator for first 5 countries
    print("\n=== HIGHEST HEADROOM SANITY CHECK ===")
    for i, (country, sens_list) in enumerate(all_sens.items()):
        if i >= 5:
            break
        top = sens_list[0]
        print(
            f"  {country}: highest headroom = {top['indicator']} "
            f"(cos={top['current_cosine']:.3f}, "
            f"headroom={top['headroom']:.4f}, "
            f"headroom_pts={top['headroom_points']:.2f})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
