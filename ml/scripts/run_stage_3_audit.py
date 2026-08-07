"""# THROWAWAY -- one-shot Stage 3 validation audit.

Per docs/specs/internal/ops/ml-track/stage-3-validation-audit.md:
runs the comprehensive validation on D2+D7-Beta LOCKED recipes and
emits Stage 3's portfolio-level + per-recipe-cohort calibration data.

Outputs (this PoC subset):
1. ml-validation-results-stage-3.json -- schema v3 with Component 5
   stratified calibration added on top of existing v2 fields
2. Per-recipe per-cohort calibration tables (Markdown) under
   docs/specs/methodology/ml-validation/<recipe>/calibration-table.md

Usage::

    python scripts/run_stage_3_audit.py \\
        --predictions results/d2_d7_canonical_2026_05/predictions.json \\
        --panel data/panel_104_2026_05_04.parquet \\
        --anchors ../qgi-data/reference/anchor-case-battery.json \\
        --locked-recipes civil_war_and_insurgency,bilateral_treaty,mass_protest,elections_and_voting,government_formation \\
        --output-json ../qgi-data/reference/ml-validation-results-stage-3.json \\
        --output-md-dir ../docs/specs/methodology/ml-validation
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SHARED_ROOT = REPO_ROOT / "shared"
for _p in (str(SRC_ROOT), str(SCRIPTS_ROOT), str(SHARED_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cohort_calibration import (  # noqa: E402
    assign_coverage_cohorts,
    stratified_calibration_per_recipe,
)
from train_multitask_v0 import build_feature_panel  # noqa: E402
from validate_ml_model import run_validation  # noqa: E402

LABEL_WINDOW_LOWER = 2014
TRAIN_YEAR_MAX = 2021


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--predictions", type=Path, required=True)
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--anchors", type=Path, required=True)
    p.add_argument("--locked-recipes", type=str, required=True,
                   help="Comma-separated list of LOCKED recipe IDs")
    p.add_argument("--output-json", type=Path, required=True)
    p.add_argument("--output-md-dir", type=Path, required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-bootstrap", type=int, default=200)
    return p.parse_args()


def render_calibration_table_md(reports_per_cohort: dict, recipe_id: str) -> str:
    """Render a Markdown calibration table per cohort for one recipe."""
    lines = [f"# Calibration tables: `{recipe_id}` (D2+D7-Beta)\n"]
    lines.append("**Filed:** Stage 3 validation audit, 2026-05-06\n")
    lines.append("**Architecture:** D2+D7-Beta multi-task with shared embedding + Beta calibration\n")
    lines.append("**Per Nasrin's binding requirement** (post-PoC trio, 2026-05-03): calibration tables are how Lloyd's actuaries price; AUC charts are NOT used in methodology disclosure.\n")
    lines.append("---\n")

    for cohort in ("high", "mid", "low", "unknown"):
        if cohort not in reports_per_cohort:
            continue
        report = reports_per_cohort[cohort]
        if report.skip_reason is not None:
            lines.append(f"## Cohort: **{cohort}** — SKIPPED ({report.skip_reason})\n")
            continue
        lines.append(f"## Cohort: **{cohort}**\n")
        lines.append(f"- N countries: **{report.n_countries}**")
        lines.append(f"- N observations: **{report.n_observations}**")
        lines.append(f"- N positives: **{report.n_positives}**")
        lines.append(f"- ECE: **{report.ece:.4f}** (cohort-specific)")
        lines.append("")
        lines.append("| Bin (predicted prob) | N obs | Mean predicted | Observed event rate | 95% CI |")
        lines.append("|---|---|---|---|---|")
        for row in report.table:
            if row.n_observations == 0:
                continue
            ci_str = f"[{row.observed_rate_ci_lower:.3f}, {row.observed_rate_ci_upper:.3f}]"
            lines.append(
                f"| [{row.bin_low:.2f}, {row.bin_high:.2f}] "
                f"| {row.n_observations} "
                f"| {row.mean_predicted_prob:.4f} "
                f"| {row.observed_event_rate:.4f} "
                f"| {ci_str} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()

    print(f"[stage3] reading predictions from {args.predictions}", file=sys.stderr)
    pred_payload = json.loads(args.predictions.read_text(encoding="utf-8"))
    predictions = pred_payload.get("predictions", pred_payload if isinstance(pred_payload, list) else [])
    print(f"[stage3] loaded {len(predictions)} predictions", file=sys.stderr)

    locked_recipes = [r.strip() for r in args.locked_recipes.split(",") if r.strip()]
    print(f"[stage3] LOCKED recipes: {locked_recipes}", file=sys.stderr)
    # Filter predictions to LOCKED recipes only
    locked_preds = [p for p in predictions if p["recipe_id"] in locked_recipes]
    print(f"[stage3] filtered predictions for LOCKED recipes: {len(locked_preds)}", file=sys.stderr)

    print("[stage3] building engineered feature panel for cohort assignment...", file=sys.stderr)
    panel = build_feature_panel(args.panel, train_year_max=TRAIN_YEAR_MAX)
    panel_train = panel[(panel["year"] >= LABEL_WINDOW_LOWER) & (panel["year"] <= TRAIN_YEAR_MAX)]
    print(f"[stage3] panel shape (train window): {panel_train.shape}", file=sys.stderr)

    coverage = assign_coverage_cohorts(panel_train)
    cohort_map = dict(zip(coverage["country"], coverage["cohort"]))
    print("[stage3] cohort distribution:", file=sys.stderr)
    print(coverage["cohort"].value_counts().to_string(), file=sys.stderr)

    print("[stage3] computing Component 5 stratified calibration...", file=sys.stderr)
    cohort_reports = stratified_calibration_per_recipe(
        locked_preds, cohort_map,
        n_bootstrap=args.n_bootstrap, seed=args.seed,
    )

    # Run base validation (Components 1, 3, 4, 6, plus AHI metrics)
    print("[stage3] running base validation (Components 1+3+4+6)...", file=sys.stderr)
    anchors = json.loads(args.anchors.read_text(encoding="utf-8"))
    base_validation = run_validation(
        predictions=locked_preds,
        anchor_battery=anchors,
        n_bootstrap=args.n_bootstrap,
        seed=args.seed,
    )

    # Compose Stage 3 v3 schema: extends base validation with Component 5
    output = {
        "schema_version": 3,
        "stage": "stage_3_validation_audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Stage 3 validation audit on the 5 LOCKED recipes from Stage 2 walks "
            "under D2+D7-Beta architecture. Adds Component 5 (cohort-stratified "
            "calibration) per Nasrin's binding requirement on top of existing "
            "Components 1+3+4+6 (AUC, ECE, Brier, anchors)."
        ),
        "locked_recipes": locked_recipes,
        "n_predictions_locked": len(locked_preds),
        "cohort_assignment": {
            "method": "country-level mean non-null fraction across engineered features in train window",
            "n_countries_per_cohort": coverage["cohort"].value_counts().to_dict(),
            "thresholds": {
                "high_pctile": 67,
                "low_pctile": 33,
            },
            "consult_attribution": (
                "Nasrin Farrokhzad's binding requirement (post-PoC trio "
                "2026-05-03): 'a model that is well-calibrated only on data-rich "
                "countries is commercially useless for political risk insurance, "
                "where the actual coverage targets are fragile states.'"
            ),
        },
        "components_v3_added": [5],
        "components_v3_inherited_from_base": [1, 3, 4, 6],
        "components_v3_deferred_to_followup": {
            "components": [2, 7, 8, 9],
            "rationale": (
                "Component 2 (fragile-state cohort): merged conceptually with "
                "Component 5 cohort calibration. "
                "Component 7 (structural-break flags): output already in "
                "qgi-data/reference/structural-break-audit-2026-05.json (Phase C). "
                "Component 8 (SHAP attribution): output already in "
                "qgi-data/reference/shap-fingerprint-2026-05.json (Stage 2 Prereq D). "
                "Component 9 (BH/FDR vs multi-task baseline): D2 IS the multi-task "
                "model -- comparison would be against itself. Defer to Stage 5 "
                "post-buyer-disclosure when alternative model classes are explored."
            ),
        },
        "components": {
            **base_validation["components"],
            "component_5_cohort_calibration": {
                "per_recipe": {
                    rid: {
                        cohort: {
                            **{k: v for k, v in asdict(report).items() if k != "table"},
                            "table": [asdict(row) for row in report.table],
                        }
                        for cohort, report in cohort_reports.get(rid, {}).items()
                    }
                    for rid in locked_recipes
                },
            },
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(output, indent=2, default=_json_default), encoding="utf-8")
    print(f"[stage3] wrote {args.output_json}", file=sys.stderr)

    # Render per-recipe calibration tables to Markdown
    args.output_md_dir.mkdir(parents=True, exist_ok=True)
    for rid in locked_recipes:
        if rid not in cohort_reports:
            continue
        recipe_dir = args.output_md_dir / rid
        recipe_dir.mkdir(parents=True, exist_ok=True)
        md = render_calibration_table_md(cohort_reports[rid], rid)
        out_path = recipe_dir / "calibration-table.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"[stage3] wrote {out_path}", file=sys.stderr)

    # Brief stdout summary
    print("\n=== Stage 3 cohort-stratified ECE per LOCKED recipe ===", file=sys.stderr)
    print(f"{'recipe':<35} {'high':>10} {'mid':>10} {'low':>10}", file=sys.stderr)
    for rid in locked_recipes:
        line = f"{rid:<35}"
        for cohort in ("high", "mid", "low"):
            r = cohort_reports.get(rid, {}).get(cohort)
            ece_str = f"{r.ece:.4f}" if (r and not np.isnan(r.ece)) else "N/A"
            line += f" {ece_str:>10}"
        print(line, file=sys.stderr)
    return 0


def _json_default(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        f = float(obj)
        return f if np.isfinite(f) else None
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.bool_):
        return bool(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
