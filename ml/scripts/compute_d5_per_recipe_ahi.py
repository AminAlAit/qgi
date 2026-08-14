#!/usr/bin/env python3
"""
Per-recipe AHI partitioning for the D5 walk anchor regression suite.
====================================================================

Computes Anchor Health Index (AHI), Anchor Hit Rate (AHR), and Anchor
Drift Score (ADS) **partitioned by recipe** from the D5 walk predictions
JSON + the anchor case battery JSON.

Rationale (per `docs/specs/internal/ops/ml-track/results/stage-5-self-audit-and-majles-agenda-2026-05-11.md` "Scope NOT covered"):
the canonical D5 walk verdict (`d5-batch-walk-verdict.md` line 60-65)
reports a single aggregate AHI = 0.3218 across 92 of 100 evaluable
anchors. Nasrin (buyer-disclosure persona) requested per-recipe AHI
partitioning so each tear-sheet in the Stage 5 paper can carry its own
anchor-health metric.

This script is **read-only** on cached predictions JSON + anchor battery
JSON. No model training, no pipeline run, no AWS calls. Local Python on
cached parquet/JSON is permitted under the standing-rule "no pipeline
runs without approval" carve-out.

Sanity check: the aggregate AHI computed by this script (across all
recipes) MUST match the cited 0.3218 from `d5-batch-walk-verdict.md`
within floating-point tolerance, otherwise an anchor-evaluation
divergence has snuck in. A test enforces this invariant.

Inputs:
    --predictions  D5 predictions JSON (default: qgi-data/reference/d5-d7-beta-validation-results-2026-05-07.json)
    --anchors      anchor case battery JSON (default: qgi-data/reference/anchor-case-battery.json)
    --output-json  output per-recipe AHI JSON (default: stdout-only)
    --output-md    output per-recipe AHI markdown table (default: stdout-only)

Output JSON schema:
    {
      "schema_version": 1,
      "generated_at_utc": "...",
      "source_predictions": "<path>",
      "source_anchors": "<path>",
      "n_active_anchors": ...,
      "n_evaluable_anchors": ...,
      "aggregate": {ads, ahr, ahi, n_evaluable, ...},
      "per_recipe": {
        "<recipe>": {ads, ahr, ahi, n_evaluable, n_excluded_non_evaluable, per_case_drifts: [...]},
        ...
      },
      "sanity_check": {
        "cited_aggregate_ahi": 0.3218,
        "computed_aggregate_ahi": ...,
        "delta_abs": ...,
        "tolerance": 0.001,
        "passes": true/false,
      }
    }
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Import the canonical anchor-evaluation primitives. They live in
# `validate_ml_model.py` which is the single source of truth for the
# anchor methodology.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_ml_model import (  # noqa: E402
    compute_anchor_drift_metrics,
    evaluate_anchor_case,
)

DEFAULT_PREDICTIONS = (
    Path(__file__).resolve().parents[2]
    / "qgi-data"
    / "reference"
    / "d5-d7-beta-validation-results-2026-05-07.json"
)
DEFAULT_ANCHORS = (
    Path(__file__).resolve().parents[2]
    / "qgi-data"
    / "reference"
    / "anchor-case-battery.json"
)

# Sanity-check threshold: re-computed aggregate AHI must match the cited
# value from d5-batch-walk-verdict.md within this absolute tolerance.
CITED_AGGREGATE_AHI = 0.3218
SANITY_TOLERANCE = 0.001


def partition_anchor_results_by_recipe(
    anchor_results: dict,
) -> dict[str, dict]:
    """Group anchor-battery evaluation results by recipe.

    Cases without a `recipe` field (sentinels resolving to layer1, etc.)
    are aggregated under the synthetic key ``__unrecipe__`` so they're
    surfaced rather than silently dropped.

    Parameters
    ----------
    anchor_results : dict
        Output of `evaluate_anchor_battery(...)`. Expected to contain an
        `active` key.

    Returns
    -------
    dict[recipe, anchor_results_subset] — subset has the same `active`
    list shape as the input, filtered to that recipe.
    """
    if not isinstance(anchor_results, dict):
        return {}
    active = anchor_results.get("active") or []
    by_recipe: dict[str, list[dict]] = defaultdict(list)
    for case in active:
        recipe = case.get("recipe") or "__unrecipe__"
        by_recipe[recipe].append(case)
    return {
        recipe: {"active": cases}
        for recipe, cases in by_recipe.items()
    }


def compute_per_recipe_metrics(
    anchor_results: dict,
) -> dict[str, dict]:
    """Compute ADS/AHR/AHI per recipe by partitioning + reusing the
    canonical `compute_anchor_drift_metrics(...)` per group.
    """
    partitioned = partition_anchor_results_by_recipe(anchor_results)
    out: dict[str, dict] = {}
    for recipe, subset in sorted(partitioned.items()):
        metrics = compute_anchor_drift_metrics(subset)
        out[recipe] = {
            "ads": metrics["ads"],
            "ahr": metrics["ahr"],
            "ahi": metrics["ahi"],
            "n_evaluable": metrics["n_evaluable"],
            "n_excluded_non_evaluable": metrics["n_excluded_non_evaluable"],
            "per_case_drifts": metrics["per_case_drifts"],
        }
    return out


def evaluate_d5_anchors(
    predictions: list[dict],
    anchor_battery: dict,
) -> dict:
    """Evaluate every active anchor case against D5 predictions.

    Mirrors `evaluate_anchor_battery` from validate_ml_model but is
    inlined here to avoid coupling — that function's contract is
    "active + deferred"; we only need "active" for partitioning.
    """
    active_results = [
        evaluate_anchor_case(c, predictions)
        for c in anchor_battery.get("active_cases", [])
    ]
    return {"active": active_results}


def format_per_recipe_markdown(
    aggregate: dict,
    per_recipe: dict[str, dict],
    sanity_check: dict,
) -> str:
    """Format per-recipe AHI as a markdown table for inclusion in
    Stage 5 tear-sheets + the audit doc.

    Sorts recipes by AHI descending (healthiest first); recipes with
    n_evaluable=0 are sorted last alphabetically.
    """
    lines: list[str] = []
    lines.append("# D5 walk — per-recipe anchor health metrics")
    lines.append("")
    lines.append(
        f"**Aggregate AHI** = {aggregate['ahi']:.4f} "
        f"(AHR = {aggregate['ahr']:.4f}, ADS = {aggregate['ads']:.4f}, "
        f"n_evaluable = {aggregate['n_evaluable']})"
    )
    lines.append("")
    lines.append(
        f"**Sanity check vs `d5-batch-walk-verdict.md` cited AHI {CITED_AGGREGATE_AHI}**: "
        f"computed = {sanity_check['computed_aggregate_ahi']:.4f}, "
        f"delta = {sanity_check['delta_abs']:.6f}, "
        f"tolerance = {SANITY_TOLERANCE}, "
        f"**{'PASS' if sanity_check['passes'] else 'FAIL'}**."
    )
    lines.append("")
    lines.append("## Per-recipe partitioning")
    lines.append("")
    lines.append(
        "| Recipe | AHI | AHR | ADS | n_evaluable | n_excluded "
        "(SKIPPED/DEFERRED/NYI) |"
    )
    lines.append(
        "|---|---|---|---|---|---|"
    )
    # Sort: recipes with n_evaluable > 0 first by AHI desc, ties broken
    # by recipe name ascending (deterministic across Python releases);
    # then n_evaluable=0 alphabetically.
    def _sort_key(item):
        recipe, m = item
        n = m["n_evaluable"]
        if n == 0:
            return (1, recipe, 0.0)
        # negate ahi so descending order falls out of ascending sort;
        # recipe name is the deterministic tie-break on equal AHI.
        return (0, -float(m["ahi"]), recipe)
    for recipe, m in sorted(per_recipe.items(), key=_sort_key):
        if m["n_evaluable"] == 0:
            ahi_str = ahr_str = ads_str = "—"
        else:
            ahi_str = f"{m['ahi']:.4f}"
            ahr_str = f"{m['ahr']:.4f}"
            ads_str = f"{m['ads']:.4f}"
        lines.append(
            f"| {recipe} | {ahi_str} | {ahr_str} | {ads_str} | "
            f"{m['n_evaluable']} | {m['n_excluded_non_evaluable']} |"
        )
    lines.append("")
    lines.append(
        "Methodology: ADS = mean(|drift|) across evaluable anchors "
        "(PASS/FAIL only); AHR = fraction in-band; AHI = AHR × (1 − ADS) "
        "composite. Per-recipe partitioning groups by the `recipe` field "
        "in each anchor case. Recipes with n_evaluable=0 (only "
        "SKIPPED/DEFERRED/NOT_YET_IMPLEMENTED cases) have undefined "
        "metrics. Founder ratification of the ADS/AHR/AHI formula: "
        "2026-05-05."
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute per-recipe AHI partitioning for D5 walk.",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=DEFAULT_PREDICTIONS,
        help="Path to D5 predictions JSON (default: D5 walk canonical).",
    )
    parser.add_argument(
        "--anchors",
        type=Path,
        default=DEFAULT_ANCHORS,
        help="Path to anchor case battery JSON (default: canonical).",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write per-recipe AHI JSON.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Optional path to write per-recipe AHI markdown table.",
    )
    args = parser.parse_args(argv)

    with args.predictions.open("r", encoding="utf-8") as f:
        predictions_payload = json.load(f)
    predictions = predictions_payload.get("predictions", [])

    with args.anchors.open("r", encoding="utf-8") as f:
        anchor_battery = json.load(f)

    anchor_results = evaluate_d5_anchors(predictions, anchor_battery)
    aggregate = compute_anchor_drift_metrics(anchor_results)
    per_recipe = compute_per_recipe_metrics(anchor_results)

    delta_abs = abs(aggregate["ahi"] - CITED_AGGREGATE_AHI)
    sanity_check = {
        "cited_aggregate_ahi": CITED_AGGREGATE_AHI,
        "computed_aggregate_ahi": aggregate["ahi"],
        "delta_abs": delta_abs,
        "tolerance": SANITY_TOLERANCE,
        "passes": delta_abs <= SANITY_TOLERANCE,
    }

    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_predictions": str(args.predictions),
        "source_anchors": str(args.anchors),
        "n_active_anchors": len(anchor_results["active"]),
        "n_evaluable_anchors": aggregate["n_evaluable"],
        "aggregate": {
            "ads": aggregate["ads"],
            "ahr": aggregate["ahr"],
            "ahi": aggregate["ahi"],
            "n_evaluable": aggregate["n_evaluable"],
            "n_excluded_non_evaluable": aggregate["n_excluded_non_evaluable"],
        },
        "per_recipe": per_recipe,
        "sanity_check": sanity_check,
    }

    md = format_per_recipe_markdown(aggregate, per_recipe, sanity_check)

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with args.output_json.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        with args.output_md.open("w", encoding="utf-8") as f:
            f.write(md)

    # Stdout: write the markdown table (human-readable summary) using
    # UTF-8 explicitly, so non-ASCII characters (× minus signs, etc.)
    # don't break on Windows consoles configured for cp1252.
    try:
        sys.stdout.buffer.write(md.encode("utf-8"))
    except AttributeError:  # pragma: no cover — non-binary stream
        sys.stdout.write(md)

    # Non-zero exit code on sanity-check failure surfaces the divergence
    # to the caller (CI, etc.) — but the JSON + markdown are still
    # written. Defensive: only exit 1 when the sanity check is wired
    # against a real cited value; in fixture/test scenarios where
    # CITED_AGGREGATE_AHI is moot, the test patches this constant or
    # invokes the lower-level functions directly.
    return 0 if sanity_check["passes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
