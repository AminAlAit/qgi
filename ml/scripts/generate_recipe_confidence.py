#!/usr/bin/env python3
"""
generate_recipe_confidence.py — compute Recipe Confidence Index (RCI) from
an audit_report.json and write the frontend-consumable JSON (#481).

RCI formula:
    RCI = max(0, 2*(AUC-0.5))
        × clamp(n_pos/30, 0, 1)
        × clamp(1 - n_mnar/15, 0, 1)

Tier banding:
    GREEN        rci >= 0.50
    YELLOW       rci  0.20–0.50
    RED          rci  < 0.20
    INSUFFICIENT n_pos < 5 OR n_total < 30 OR AUC undefined

Output schema mirrors the loader in qgi-frontend/lib/recipe-confidence.ts.

Usage:
    python scripts/generate_recipe_confidence.py \\
        --audit-report results/audition_2026_04_27_v0_5/audition_report.json \\
        --output ../qgi-frontend/data/recipe-confidence.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit-report", type=Path, required=True,
                   help="Path to an audition_report.json")
    p.add_argument("--output", type=Path, required=True,
                   help="Where to write recipe-confidence.json")
    p.add_argument("--pipeline-version", default="v0.5",
                   help="Stamped on every entry; advance when formula changes")
    args = p.parse_args()

    report = json.loads(args.audit_report.read_text(encoding="utf-8"))

    out = {
        "generated_at": report["audit_date"],
        "git_sha": report.get("git_sha", "?"),
        "pipeline_version": args.pipeline_version,
        "schema_version": 1,
        "audit_basis": str(args.audit_report),
        "formula_note": (
            "RCI = max(0, 2*(AUC-0.5)) × clamp(n_pos/30, 0, 1) "
            "× clamp(1 - n_mnar/15, 0, 1)"
        ),
        "tiers": {
            "GREEN": ">= 0.50 — high confidence",
            "YELLOW": "0.20-0.50 — moderate confidence",
            "RED": "< 0.20 — low confidence; treat results with skepticism",
            "INSUFFICIENT": "below sample threshold (n_pos < 5 or auc undefined)",
        },
        "recipes": {},
    }

    def safe(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return v

    for r in report["per_recipe"]:
        cat = r["event_category"]
        auc = r.get("test_auc")
        n_pos = r.get("n_pos") or 0
        n_total = r.get("n_total") or 0
        n_mnar = r.get("n_mnar_flagged", 0)

        if (auc is None or (isinstance(auc, float) and math.isnan(auc))
                or n_pos < 5 or n_total < 30):
            out["recipes"][cat] = {
                "rci": None, "tier": "INSUFFICIENT",
                "test_auc": safe(auc),
                "auc_ci_low": safe(r.get("auc_ci_low")),
                "auc_ci_high": safe(r.get("auc_ci_high")),
                "n_total": n_total, "n_pos": n_pos,
                "n_mnar_flagged": n_mnar,
                "top_indicator": r.get("top_indicator"),
            }
            continue

        auc_skill = max(0.0, 2 * (auc - 0.5))
        sample_factor = min(1.0, max(0.0, n_pos / 30.0))
        mnar_factor = min(1.0, max(0.0, 1.0 - n_mnar / 15.0))
        rci = auc_skill * sample_factor * mnar_factor

        if rci >= 0.50:
            tier = "GREEN"
        elif rci >= 0.20:
            tier = "YELLOW"
        else:
            tier = "RED"

        def round_or_none(v, n=3):
            return round(v, n) if isinstance(v, (int, float)) and not math.isnan(v) else None

        out["recipes"][cat] = {
            "rci": round(rci, 3),
            "tier": tier,
            "auc_skill": round(auc_skill, 3),
            "sample_factor": round(sample_factor, 3),
            "mnar_factor": round(mnar_factor, 3),
            "test_auc": round_or_none(auc),
            "auc_ci_low": round_or_none(r.get("auc_ci_low")),
            "auc_ci_high": round_or_none(r.get("auc_ci_high")),
            "n_total": n_total,
            "n_pos": n_pos,
            "n_mnar_flagged": n_mnar,
            "top_indicator": r.get("top_indicator"),
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2), encoding="utf-8")
    from collections import Counter
    tiers = Counter(v["tier"] for v in out["recipes"].values())
    print(f"[write] {args.output}")
    print(f"[stats] {len(out['recipes'])} recipes, tiers: {dict(tiers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
