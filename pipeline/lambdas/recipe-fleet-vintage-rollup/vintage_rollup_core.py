"""vintage_rollup_core.py — pure logic for the recipe-fleet cross-vintage rollup
Lambda (qgi-aws-tf#968). Reads per-vintage f-ml-1-poc-summary dicts and produces the
denormalized per-recipe time-series that the Admin Dashboard's quarterly trend section
(#151 TE §B) renders.

Kept pure + dependency-free so it is exhaustively testable. Handler-side I/O lives in
`lambda_function.py`.

Methodology constraint: every vintage's row is extracted FROM that vintage's own walk
summary; no inherited values, no carry-forward, no implicit interpolation between
quarters. The no-grandfather rule (FLEET-6) applies at the rollup layer too — a tier
that was Validated in a prior vintage and Experimental in the current one shows BOTH
honestly; the dashboard renders the transition as a slip.
"""

from __future__ import annotations

from typing import Any


def extract_vintage_row(summary: dict, vintage_id: str) -> dict[str, Any]:
    """One denormalized row per (recipe, vintage) for the rollup. EVERY field comes
    directly from `summary`; the only added field is `vintage_id` (the rollup's key).
    No defaults that hide a missing emit — None propagates so the dashboard can render
    "data not available for this vintage" honestly.

    SCHEMA DISCIPLINE (QA PR#45 FU4): the field set below is a deliberate WHITELIST.
    New fields added to future walk emits are intentionally NOT auto-passed-through —
    bump this function with explicit additions so the dashboard's column set is a
    reviewable change, not a silent widening. The trade-off is forward-compatibility:
    a wave that emits a new field won't surface it in the rollup until this function
    is updated. That's the correct direction for a versioned schema."""
    g = summary.get("greedy_outer_loop") or {}
    gl = summary.get("global_loco") or {}
    cov = summary.get("coverage_audit") or {}
    pc = summary.get("per_cohort") or {}

    # Per-cohort median LOCO-AUC (handy for the trend strip on the dashboard).
    cohort_aucs = sorted(
        v.get("loco_auc") for v in pc.values() if isinstance(v, dict) and v.get("loco_auc") is not None
    )
    cohort_med = None
    if cohort_aucs:
        n = len(cohort_aucs)
        cohort_med = cohort_aucs[n // 2] if n % 2 else (cohort_aucs[n // 2 - 1] + cohort_aucs[n // 2]) / 2

    return {
        "vintage_id": vintage_id,
        "walked_at_utc": summary.get("filed"),
        "verdict": summary.get("verdict"),
        "loco_auc": gl.get("auc"),
        "ci95_lo": gl.get("ci95_lo"),
        "ci95_hi": gl.get("ci95_hi"),
        "ci80_lo": gl.get("ci80_lo"),
        "ci80_hi": gl.get("ci80_hi"),
        "selected_indicators": g.get("selected_indicators"),
        "chosen_window": g.get("chosen_window"),
        "final_global_auc": g.get("final_global_auc"),
        "early_abort_floor_unreachable": g.get("early_abort_floor_unreachable"),
        "n_pos_total": cov.get("n_pos_total"),
        "n_pos_survive": cov.get("n_pos_survive"),
        "n_neg_total": cov.get("n_neg_total"),
        "n_neg_survive": cov.get("n_neg_survive"),
        "n_countries_survive": cov.get("n_countries_survive"),
        "pos_coverage": cov.get("pos_coverage"),
        "coverage_pass": cov.get("coverage_pass"),
        "elapsed_seconds": summary.get("elapsed_seconds"),
        "architecture": summary.get("architecture"),
        "borderline_lock": summary.get("borderline_lock"),
        "temporal_confound_auc": summary.get("temporal_confound_auc"),
        "n_positives": summary.get("n_positives"),
        "n_negatives": summary.get("n_negatives"),
        "per_cohort_median_loco_auc": cohort_med,
        "per_cohort": {
            k: {
                "loco_auc": (v.get("loco_auc") if isinstance(v, dict) else None),
                "ece": (v.get("ece") if isinstance(v, dict) else None),
            }
            for k, v in pc.items()
        },
        "indicator_lifts": [
            {
                "step": h.get("step"),
                "candidate": h.get("candidate"),
                "window": h.get("window"),
                "auc": h.get("auc"),
                "lift_over_previous": h.get("lift_over_previous"),
                "selected_after": h.get("selected_after"),
            }
            for h in (g.get("history") or [])
        ],
        "panel_fingerprint": summary.get("panel_fingerprint"),
    }


def merge_into_per_recipe(per_recipe: dict[str, list[dict]], recipe_id: str, row: dict[str, Any]) -> None:
    """Append `row` to `per_recipe[recipe_id]`. Idempotent on (recipe_id, vintage_id)
    pairs: if a row with the same vintage_id already exists, the later one REPLACES
    the earlier (so a re-ingest of the same archive doesn't double-list). Pure mutator
    — caller owns the dict."""
    existing = per_recipe.setdefault(recipe_id, [])
    for i, r in enumerate(existing):
        if r.get("vintage_id") == row.get("vintage_id"):
            existing[i] = row
            return
    existing.append(row)


def build_rollup(per_recipe: dict[str, list[dict]], *, current_vintage_id: str, produced_at_utc: str) -> dict[str, Any]:
    """Compose the final rollup document. Per-recipe vintages are sorted chronologically
    by `walked_at_utc` (None sorts last). Adds a top-level `n_recipes` + per-recipe
    `n_vintages` for the dashboard's roster overview."""
    recipes: dict[str, Any] = {}
    for rid in sorted(per_recipe):
        rows = list(per_recipe[rid])
        rows.sort(key=lambda r: r.get("walked_at_utc") or "~")  # tilde sorts after digits
        # Most-recent row first for "what's the current state" reads.
        latest = rows[-1] if rows else None
        recipes[rid] = {
            "n_vintages": len(rows),
            "latest_vintage_id": (latest or {}).get("vintage_id"),
            "latest_walked_at_utc": (latest or {}).get("walked_at_utc"),
            "vintages": rows,
        }
    return {
        "produced_at_utc": produced_at_utc,
        "current_vintage_id": current_vintage_id,
        "n_recipes": len(recipes),
        "n_vintages_total": sum(r["n_vintages"] for r in recipes.values()),
        "recipes": recipes,
    }
