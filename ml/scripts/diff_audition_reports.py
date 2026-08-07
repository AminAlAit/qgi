#!/usr/bin/env python3
"""
diff_audition_reports.py — compare two audition_indicators.py reports.

Surfaces what changed between two runs:
  - Per-recipe AUC delta (sorted by absolute change)
  - Per-recipe top-contributor reshuffle (which indicator replaced which)
  - Per-indicator audition_score delta (especially candidates that became
    fingerprint-eligible or vice versa)
  - V-Dem-vs-WB attribution shift (when provider data is available)

Usage:
  python scripts/diff_audition_reports.py \\
      --baseline results/audition_2026_04_26_vdem_candidates/audition_report.json \\
      --new      results/audition_2026_04_27_vdem39/audition_report.json \\
      --output   results/audition_2026_04_27_vdem39/diff_vs_baseline.md

Designed to be run automatically after every audit. The output file is the
human-readable changelog: "what does this audit say is different from last
time."
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def index_by(items: list[dict], key: str) -> dict:
    return {item[key]: item for item in items}


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--baseline", type=Path, required=True,
                   help="Earlier audition_report.json")
    p.add_argument("--new", type=Path, required=True,
                   help="Newer audition_report.json")
    p.add_argument("--output", type=Path, required=True,
                   help="Where to write the diff markdown")
    args = p.parse_args()

    base = load_report(args.baseline)
    new = load_report(args.new)

    # ---- Per-recipe AUC deltas ----
    base_recipes = index_by(base["per_recipe"], "event_category")
    new_recipes = index_by(new["per_recipe"], "event_category")
    common = sorted(set(base_recipes) & set(new_recipes))
    only_base = sorted(set(base_recipes) - set(new_recipes))
    only_new = sorted(set(new_recipes) - set(base_recipes))

    recipe_diffs = []
    for cat in common:
        b = base_recipes[cat]
        n = new_recipes[cat]
        delta_auc = n["test_auc"] - b["test_auc"]
        contributor_changed = b["top_indicator"] != n["top_indicator"]
        recipe_diffs.append({
            "event_category": cat,
            "tier": n.get("tier", "?"),
            "auc_baseline": b["test_auc"],
            "auc_new": n["test_auc"],
            "delta_auc": delta_auc,
            "top_baseline": b["top_indicator"],
            "top_new": n["top_indicator"],
            "contributor_changed": contributor_changed,
        })

    # ---- Per-indicator audition_score deltas ----
    base_inds = index_by(base["per_indicator"], "indicator_id_string")
    new_inds = index_by(new["per_indicator"], "indicator_id_string")
    common_inds = sorted(set(base_inds) & set(new_inds))
    only_base_inds = sorted(set(base_inds) - set(new_inds))
    only_new_inds = sorted(set(new_inds) - set(base_inds))

    ind_diffs = []
    for sid in common_inds:
        b = base_inds[sid]
        n = new_inds[sid]
        ind_diffs.append({
            "indicator": sid,
            "provider": n.get("provider", b.get("provider", "?")),
            "score_baseline": b["audition_score"],
            "score_new": n["audition_score"],
            "delta_score": n["audition_score"] - b["audition_score"],
            "is_candidate_now": n.get("is_candidate", False),
            "was_candidate": b.get("is_candidate", False),
        })

    # ---- Render markdown ----
    md = []
    md.append("# Audition Diff — baseline vs new\n")
    md.append(f"**Baseline:** `{args.baseline}` (audit_date: {base.get('audit_date', '?')})\n")
    md.append(f"**New:** `{args.new}` (audit_date: {new.get('audit_date', '?')})\n")

    md.append("\n## Headline\n")
    md.append(f"- Recipes covered: {len(base_recipes)} → {len(new_recipes)} (Δ={len(new_recipes)-len(base_recipes):+d})")
    md.append(f"- Indicators audited: {len(base_inds)} → {len(new_inds)} (Δ={len(new_inds)-len(base_inds):+d})")
    if "median_recipe_auc" in base and "median_recipe_auc" in new:
        md.append(f"- Median per-recipe AUC: {base['median_recipe_auc']:.3f} → {new['median_recipe_auc']:.3f} "
                  f"(Δ={new['median_recipe_auc']-base['median_recipe_auc']:+.3f})")
    n_changed_top = sum(1 for d in recipe_diffs if d["contributor_changed"])
    md.append(f"- Recipes with top-contributor reshuffle: **{n_changed_top}/{len(common)}**")

    # Top 10 biggest AUC swings (absolute)
    md.append("\n## Top 10 biggest AUC swings (absolute delta)\n")
    md.append("| Recipe | Tier | AUC baseline → new | Δ AUC | Top-contributor change |")
    md.append("|---|---|---|---|---|")
    for d in sorted(recipe_diffs, key=lambda r: -abs(r["delta_auc"]))[:10]:
        change = (
            f"{d['top_baseline']} → {d['top_new']}"
            if d["contributor_changed"]
            else "(no change)"
        )
        md.append(
            f"| {d['event_category']} | {d['tier']} | "
            f"{d['auc_baseline']:.3f} → {d['auc_new']:.3f} | "
            f"**{d['delta_auc']:+.3f}** | {change} |"
        )

    # Recipes with new top-contributor (especially V-Dem replacing WB)
    md.append("\n## Recipes where the top contributor changed\n")
    contributor_changes = [d for d in recipe_diffs if d["contributor_changed"]]
    if contributor_changes:
        md.append("| Recipe | Tier | AUC baseline → new | Old top → new top |")
        md.append("|---|---|---|---|")
        for d in sorted(contributor_changes, key=lambda r: -r["auc_new"]):
            md.append(
                f"| {d['event_category']} | {d['tier']} | "
                f"{d['auc_baseline']:.3f} → {d['auc_new']:.3f} | "
                f"{d['top_baseline']} → **{d['top_new']}** |"
            )
    else:
        md.append("(no top-contributor changes between the two runs)")

    # New / removed indicators
    if only_new_inds or only_base_inds:
        md.append("\n## Indicator universe changes\n")
        if only_new_inds:
            md.append(f"\n**New indicators ({len(only_new_inds)}):**")
            for sid in only_new_inds:
                ind = new_inds[sid]
                md.append(
                    f"- `{sid}` ({ind.get('provider', '?')}, "
                    f"score={ind['audition_score']:.4f}, "
                    f"candidate={ind.get('is_candidate', False)})"
                )
        if only_base_inds:
            md.append(f"\n**Removed indicators ({len(only_base_inds)}):**")
            for sid in only_base_inds:
                md.append(f"- `{sid}`")

    # Top 15 biggest audition_score moves
    md.append("\n## Top 15 biggest indicator audition_score moves\n")
    md.append("| Indicator | Provider | score baseline → new | Δ score | Status |")
    md.append("|---|---|---|---|---|")
    for d in sorted(ind_diffs, key=lambda r: -abs(r["delta_score"]))[:15]:
        status = "candidate" if d["is_candidate_now"] else "fingerprint"
        if d["was_candidate"] != d["is_candidate_now"]:
            status += " (status changed)"
        md.append(
            f"| {d['indicator']} | {d['provider']} | "
            f"{d['score_baseline']:.4f} → {d['score_new']:.4f} | "
            f"**{d['delta_score']:+.4f}** | {status} |"
        )

    # Provider rollup — only if provider data exists
    if any(d.get("provider") and d["provider"] != "?" for d in ind_diffs):
        md.append("\n## Per-provider rollup\n")
        from collections import defaultdict
        by_provider: dict[str, list[float]] = defaultdict(list)
        for d in ind_diffs:
            prov = d["provider"]
            if prov and prov != "?":
                by_provider[prov].append(d["score_new"])
        md.append("| Provider | n_indicators | mean audition_score | top indicator |")
        md.append("|---|---|---|---|")
        for prov in sorted(by_provider, key=lambda p: -sum(by_provider[p])/max(len(by_provider[p]), 1)):
            scores = by_provider[prov]
            top_ind = max(
                (d for d in ind_diffs if d["provider"] == prov),
                key=lambda d: d["score_new"]
            )
            md.append(
                f"| {prov} | {len(scores)} | {sum(scores)/len(scores):.4f} | "
                f"{top_ind['indicator']} ({top_ind['score_new']:.4f}) |"
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(md), encoding="utf-8")
    print(f"[write] {args.output}")
    print(f"  recipes: {len(common)} compared, {n_changed_top} top-contributor changes")
    print(f"  indicators: {len(common_inds)} compared, "
          f"{len(only_new_inds)} new, {len(only_base_inds)} removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
