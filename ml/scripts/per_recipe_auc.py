#!/usr/bin/env python3
"""
per_recipe_auc.py — Per-recipe AUC baseline diagnostic (#478).

Reads the V1.9.1 backtest pairs + V2.0 country_recipe_scores fixtures
and the L3 → L1 taxonomy, then emits a per-recipe AUC table grouped by
event family (Layer-1 taxonomy).

Output: markdown report at the path passed via --output, plus a CSV
companion for downstream analysis.

This is the seed work for the per-recipe metrics framework (#479) and
the pre-V-Dem baseline that the indicator-to-recipe auditioner (#480)
will be measured against post-V-Dem integration.

Usage:
  python scripts/per_recipe_auc.py \\
      --pairs-jsonl results/v2_eval_2026_04_26/pairs.jsonl \\
      --scores-jsonl results/v2_eval_2026_04_26/scores.jsonl \\
      --recipes-aggregated results/v2_eval_2026_04_26/recipes-aggregated.json \\
      --taxonomy ../qgi-data/events/taxonomy_hierarchy.json \\
      --output results/v2_eval_2026_04_26/per_recipe_auc.md
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

TIERS = {"S": (3, 8), "M": (9, 20), "L": (21, 40), "XL": (41, 999)}

MIN_TOTAL = 30
MIN_POS = 5


def tier_for_length(L: int) -> str:
    for t, (lo, hi) in TIERS.items():
        if lo <= L <= hi:
            return t
    return "XL"


def rank_auc(score_label_pairs: list[tuple[float, int]]) -> float | None:
    """AUC = P(score(positive) > score(negative)). Tie credit = 0.5."""
    pos = [s for s, y in score_label_pairs if y == 1]
    neg = [s for s, y in score_label_pairs if y == 0]
    if not pos or not neg:
        return None
    wins = ties = 0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1
            elif p == n:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def load_taxonomy(path: Path) -> dict[str, dict]:
    """Returns L3 → {l1_id, l1_label, l2_id, l2_label}."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for l1 in raw["layer1"]:
        for l2 in l1.get("layer2", []):
            for l3 in l2.get("layer3", []):
                out[l3] = {
                    "l1_id": l1["id"],
                    "l1_label": l1["display_label"],
                    "l2_id": l2["id"],
                    "l2_label": l2["label"],
                }
    return out


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--pairs-jsonl", type=Path, required=True)
    ap.add_argument("--scores-jsonl", type=Path, required=True)
    ap.add_argument("--recipes-aggregated", type=Path, required=True)
    ap.add_argument("--taxonomy", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    print(f"[load] {args.pairs_jsonl}")
    pairs = load_jsonl(args.pairs_jsonl)
    print(f"[load] {args.scores_jsonl}")
    scores = load_jsonl(args.scores_jsonl)
    print(f"[load] {args.recipes_aggregated}")
    ra = json.loads(args.recipes_aggregated.read_text(encoding="utf-8"))
    print(f"[load] {args.taxonomy}")
    tax = load_taxonomy(args.taxonomy)
    print(f"[init] {len(tax)} L3 → L1 mappings")

    cl_by_cat = {r["event_category"]: r["canonical_length"] for r in ra["recipes"]}

    # Ground truth: max y_true across tier rows per (country, category) — only
    # v1.9.1 pairs (not persistence baseline).
    gt: dict[tuple, int] = {}
    for r in pairs:
        if r.get("system") != "v1.9.1":
            continue
        key = (int(r["country_a_id"]), r["event_category"])
        gt[key] = max(gt.get(key, 0), int(r["y_true"]))
    print(f"[gt] {len(gt)} unique (country, category) ground-truth labels")

    # Per (event_category) bucket of (similarity_raw, y_true) where ground
    # truth exists. Filter out null-similarity rows defensively.
    by_cat: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for s in scores:
        cat = s["event_category"]
        sim = s.get("similarity_raw")
        if sim is None:
            continue
        key = (int(s["country_id"]), cat)
        if key not in gt:
            continue
        by_cat[cat].append((float(sim), gt[key]))

    print(f"[join] {sum(len(v) for v in by_cat.values())} score-rows-with-ground-truth across {len(by_cat)} categories")

    # Compute per-category metrics + bucket by L1 family.
    rows = []
    for cat, data in by_cat.items():
        n_total = len(data)
        n_pos = sum(y for _, y in data)
        if n_total < MIN_TOTAL or n_pos < MIN_POS:
            continue
        auc = rank_auc(data)
        if auc is None:
            continue
        cl = cl_by_cat.get(cat)
        tier = tier_for_length(int(cl)) if cl is not None else "?"
        tax_entry = tax.get(cat, {})
        family = tax_entry.get("l1_label", "Unmapped")
        family_id = tax_entry.get("l1_id", "?")
        pos_sims = [s for s, y in data if y == 1]
        neg_sims = [s for s, y in data if y == 0]
        mean_pos = sum(pos_sims) / len(pos_sims)
        mean_neg = sum(neg_sims) / len(neg_sims)
        rows.append({
            "event_category": cat,
            "family_id": family_id,
            "family": family,
            "canonical_length": cl,
            "tier": tier,
            "n_total": n_total,
            "n_pos": n_pos,
            "base_rate": n_pos / n_total,
            "auc": auc,
            "mean_sim_pos": mean_pos,
            "mean_sim_neg": mean_neg,
            "sim_gap": mean_pos - mean_neg,
        })

    # Sort: by family_id, then by AUC asc within family
    rows.sort(key=lambda r: (r["family_id"], r["auc"]))

    # CSV output
    csv_path = args.output.with_suffix(".csv")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[write] {csv_path}")

    # Markdown report
    md = []
    md.append("# Per-Recipe AUC Baseline Diagnostic (#478)\n")
    md.append("**Run date:** 2026-04-26 · **Pipeline:** V2.0 (Pearson trajectory similarity, tfidf weight)\n")
    md.append("**Ground truth:** V1.9.1 backtest pairs (test cutoff=2020) · "
              f"**Categories scored:** {len(rows)} of {len(by_cat)} qualifying (n≥{MIN_TOTAL}, n_pos≥{MIN_POS})\n")
    md.append("\n## Headline\n")

    aucs = [r["auc"] for r in rows]
    md.append(f"- Overall recipe AUC range: **{min(aucs):.3f} → {max(aucs):.3f}** (median {sorted(aucs)[len(aucs)//2]:.3f})")
    above_55 = sum(1 for a in aucs if a >= 0.55)
    md.append(f"- Recipes ≥ 0.55 AUC: **{above_55}/{len(rows)}** ({100*above_55/len(rows):.0f}%)")
    md.append(f"- Recipes ≤ 0.50 AUC (random or worse): **{sum(1 for a in aucs if a <= 0.50)}/{len(rows)}**")

    md.append("\n## Top 5 highest-AUC recipes\n")
    md.append("| Recipe | Family | Tier | AUC | n_total | n_pos | sim_gap |")
    md.append("|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: -r["auc"])[:5]:
        md.append(f"| {r['event_category']} | {r['family']} | {r['tier']} | "
                  f"**{r['auc']:.3f}** | {r['n_total']} | {r['n_pos']} | {r['sim_gap']:+.4f} |")

    md.append("\n## Bottom 5 lowest-AUC recipes\n")
    md.append("| Recipe | Family | Tier | AUC | n_total | n_pos | sim_gap |")
    md.append("|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: r["auc"])[:5]:
        md.append(f"| {r['event_category']} | {r['family']} | {r['tier']} | "
                  f"**{r['auc']:.3f}** | {r['n_total']} | {r['n_pos']} | {r['sim_gap']:+.4f} |")

    # Per-family aggregate
    md.append("\n## Per-family rollup\n")
    fam_data: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        fam_data[f"{r['family_id']}: {r['family']}"].append(r["auc"])
    md.append("| Family | n_recipes | mean AUC | median AUC | min | max |")
    md.append("|---|---|---|---|---|---|")
    for fam in sorted(fam_data):
        a = fam_data[fam]
        md.append(f"| {fam} | {len(a)} | {sum(a)/len(a):.3f} | "
                  f"{sorted(a)[len(a)//2]:.3f} | {min(a):.3f} | {max(a):.3f} |")

    # Full table sorted by family, then AUC asc
    md.append("\n## Full per-recipe table (sorted by family, then AUC asc)\n")
    md.append("| Family | Recipe | Tier | AUC | base_rate | n_total | n_pos | sim_gap |")
    md.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        md.append(f"| {r['family_id']} {r['family']} | {r['event_category']} | {r['tier']} | "
                  f"{r['auc']:.3f} | {r['base_rate']:.3f} | {r['n_total']} | {r['n_pos']} | {r['sim_gap']:+.4f} |")

    md.append("\n## Synthesis\n")
    # Auto-generate the synthesis paragraph from the per-family rollup.
    fam_means = {f: sum(a) / len(a) for f, a in fam_data.items()}
    fam_sorted = sorted(fam_means.items(), key=lambda x: -x[1])
    best_fam, best_auc = fam_sorted[0]
    worst_fam, worst_auc = fam_sorted[-1]
    md.append(f"- **Best-served family:** {best_fam} (mean AUC {best_auc:.3f}) — these recipes' substrate "
              "(World Bank + FAO indicators) is sufficient to discriminate ground-truth events.")
    md.append(f"- **Worst-served family:** {worst_fam} (mean AUC {worst_auc:.3f}) — these recipes are "
              "indicator-starved on the current substrate.")
    md.append(f"- **Family-AUC spread:** {best_auc - worst_auc:.3f} AUC points between best and worst family.\n")
    md.append("**Hypothesis confirmation:** if the family AUC spread > 0.10 AUC points, the global metric "
              "was masking real heterogeneity — per-recipe metrics (#479) become the right framework. "
              "Auditioner (#480) should prioritize provider acquisition for the worst-served families.\n")
    md.append("**Pre-V-Dem baseline:** these numbers are the comparison set. Post-V-Dem (#348) integration "
              "should lift the worst-served families more than the best-served (substrate-effect hypothesis).\n")

    args.output.write_text("\n".join(md), encoding="utf-8")
    print(f"[write] {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
