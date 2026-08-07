#!/usr/bin/env python3
# THROWAWAY — one-off script, no tests per #373.
# Ran once (2026-04-19 tier recalibration). V1.9.1 Fix C superseded this
# logic with the 3-layer hybrid `risk_tier_label()` in generate_country_risks.py
# and country_risks.py (Lambda copy). Proper way to re-apply tier rules is a
# full pipeline re-run, not script-side JSON mutation.
"""
recalibrate_tiers_in_place.py — apply the 2026-04-19 category-stratified
tier logic to an EXISTING country-risks.json, without re-running Athena.

Why: generate_country_risks.py needs staging-account AWS creds to hit
qgi_data.recipes / qgi_data.events. But the existing baked JSON already
carries `salience_score` and `severity_tier` for every scored category — which
is everything the new risk_tier_label() needs. So we can recompute
overall_risk_tier offline.

Usage:
    python recalibrate_tiers_in_place.py \
        --input qgi-frontend/data/country-risks.json \
        --output qgi-frontend/data/country-risks.json   # in-place

Can also target a different output file for diffing first.
"""

import argparse
import json
from collections import Counter


# Keep this in sync with generate_country_risks.py :: risk_tier_label()
def risk_tier_label(top_salience: float, top_severity_weight: float) -> str:
    CRISIS_HIGH_THRESHOLD = 1.4
    REGULAR_HIGH_THRESHOLD = 1.625
    CRISIS_MODERATE_THRESHOLD = 1.0
    REGULAR_MODERATE_THRESHOLD = 1.3
    is_crisis = top_severity_weight >= 1.0
    high_cut = CRISIS_HIGH_THRESHOLD if is_crisis else REGULAR_HIGH_THRESHOLD
    moderate_cut = (
        CRISIS_MODERATE_THRESHOLD if is_crisis else REGULAR_MODERATE_THRESHOLD
    )
    if top_salience >= high_cut:
        return "HIGH"
    elif top_salience >= moderate_cut:
        return "MODERATE"
    else:
        return "INDICATIVE"


def compute_tier(country_entry: dict) -> tuple[str, float, float, str]:
    """Return (new_tier, max_salience, severity_weight, top_cat) for a country."""
    max_salience = -999.0
    top_severity = 0.3
    top_cat = "(none)"
    for _tier_name, tier_block in country_entry.get("tiers", {}).items():
        for c in (tier_block.get("top_categories") or [])[:5]:
            sal = c.get("salience_score")
            if sal is None:
                continue
            if sal > max_salience:
                max_salience = sal
                top_severity = c.get("severity_tier", 0.3)
                top_cat = c.get("category", "(unknown)")
    return (
        risk_tier_label(max_salience, top_severity),
        max_salience,
        top_severity,
        top_cat,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without writing output",
    )
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    before = Counter()
    after = Counter()
    flipped = []  # (country_name, old_tier, new_tier, salience, severity, cat)

    for cid, country in data["countries"].items():
        old_tier = country.get("overall_risk_tier", "INDICATIVE")
        new_tier, sal, severity, cat = compute_tier(country)
        before[old_tier] += 1
        after[new_tier] += 1
        if new_tier != old_tier:
            flipped.append(
                (country.get("name", cid), old_tier, new_tier, sal, severity, cat)
            )
        country["overall_risk_tier"] = new_tier

    # Flag the new tier algorithm in metadata so downstream caches/users see
    # the change and we preserve an audit trail.
    # Audit-trail metadata. QA reviewer P0-2 fix (2026-04-19): earlier
    # string omitted the crisis MODERATE floor of 1.0 and would have made
    # the next diff reader think Ukraine (sal=1.17, severity=1.0) was
    # mis-tiered. The logic is symmetric across both cuts.
    data["tier_algorithm"] = (
        "category-stratified-2026-04-19: "
        "HIGH>=1.4 if severity>=1.0 else 1.625; "
        "MODERATE>=1.0 if severity>=1.0 else 1.3"
    )

    print("\n== Tier distribution ==")
    print(f"{'tier':12} {'before':>7}  {'after':>7}  delta")
    all_tiers = sorted(set(before) | set(after), key=lambda t: {"HIGH": 0, "MODERATE": 1, "INDICATIVE": 2}.get(t, 3))
    for t in all_tiers:
        b = before[t]
        a = after[t]
        print(f"{t:12} {b:>7}  {a:>7}  {a - b:+d}")

    print(f"\n== {len(flipped)} countries changed tier ==")
    # Show biggest promotions and demotions separately
    promoted = [f for f in flipped if tier_rank(f[2]) < tier_rank(f[1])]
    demoted = [f for f in flipped if tier_rank(f[2]) > tier_rank(f[1])]
    print(f"  {len(promoted)} promoted (more severe), {len(demoted)} demoted (less severe)\n")

    if promoted:
        print("Promoted (most severe first):")
        for name, old, new, sal, severity, cat in sorted(
            promoted, key=lambda x: -x[3]
        )[:20]:
            print(
                f"  {old:>10} -> {new:<10}  {name:<32}  sal={sal:.2f} severity={severity:.1f} ({cat})"
            )
    if demoted:
        print("\nDemoted (least severe first):")
        for name, old, new, sal, severity, cat in sorted(
            demoted, key=lambda x: x[3]
        )[:20]:
            print(
                f"  {old:>10} -> {new:<10}  {name:<32}  sal={sal:.2f} severity={severity:.1f} ({cat})"
            )

    if args.dry_run:
        print("\nDry run — no file written.")
        return

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {args.output}")


def tier_rank(tier: str) -> int:
    return {"HIGH": 0, "MODERATE": 1, "INDICATIVE": 2}.get(tier, 3)


if __name__ == "__main__":
    main()
