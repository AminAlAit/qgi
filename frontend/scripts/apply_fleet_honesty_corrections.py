#!/usr/bin/env python3
"""
apply_fleet_honesty_corrections.py — apply the fleet-honesty confidence-number
correction across BOTH data surfaces the frontend renders from.

Source of truth: scripts/fleet-honesty-corrections.json (a copy of the ML
session's qgi-ml/experiments/fleet-honesty-audit/results/corrections.json —
34 entries, keyed by trend slug).

Two surfaces carry the numbers and both must agree:

1. data/te-fleet-run-2/cards-v3/<trend>.card.json  (gitignored, S3-fetched,
   checksum-verified via data/build-manifest.json). Drives indicator panels /
   detail internals. Per card:
       stats.loco_auc                = honest_loco_auc
       stats.ci95_lo / ci95_hi       = honest_ci95_lo / honest_ci95_hi
       stats.ci80_lo / ci80_hi       = honest_ci80_lo / honest_ci80_hi
       greedy_walk.final_global_auc  = honest_loco_auc
       tier                          = re-evaluated (see below), if it changes

2. data/recipe-tracker.json  (git-tracked). Drives the Trend Tracker, the recipe
   detail headline, the sidebar/dashboard highlights. Per recipe:
       stats.loco_auc / ci95_lo / ci95_hi = honest values (this file has no ci80)
       tier + stats.tier_label_user_facing = re-evaluated, if it changes
   and top-level tier_counts is adjusted by the number of re-tiers.

Tier re-evaluation (confidence-tier-policy.md): a recipe currently "directional"
DROPS to "experimental" if its honest LOCO-AUC < 0.65 OR its honest CI95 lower
bound <= 0.50 (numbers only go down here, so tiers only ever downgrade).

`stats.n_bootstrap`, `verdict`, and everything else are left untouched.

The cards are re-uploaded to S3 separately (see the deploy step); this script
prepares the local copies + patches the git-tracked recipe-tracker.json.
Re-runnable and idempotent.

Usage:
    python scripts/apply_fleet_honesty_corrections.py            # apply
    python scripts/apply_fleet_honesty_corrections.py --dry-run  # report only
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORRECTIONS = ROOT / "scripts" / "fleet-honesty-corrections.json"
CARDS_DIR = ROOT / "data" / "te-fleet-run-2" / "cards-v3"
TRACKER = ROOT / "data" / "recipe-tracker.json"

# Spot-checks straight from the handoff §3 table — a tripwire against a bad source.
EXPECTED = {
    "monetary_policy_change": 0.617,
    "currency_crisis": 0.7546,
    "banking_and_financial_crisis": 0.6381,
    "government_formation": 0.5489,
    "military_coup": 0.6516,
}

STATS_FIELDS = {
    "loco_auc": "honest_loco_auc",
    "ci95_lo": "honest_ci95_lo",
    "ci95_hi": "honest_ci95_hi",
    "ci80_lo": "honest_ci80_lo",
    "ci80_hi": "honest_ci80_hi",
}

DIRECTIONAL_MIN_AUC = 0.65
DIRECTIONAL_MIN_CI_LO = 0.50


def honest_tier(current_tier, loco, ci95_lo):
    """Downgrade a 'directional' recipe to 'experimental' if the honest number no
    longer clears the Directional bar. Numbers only fall here, so this never
    upgrades — a non-directional tier is returned unchanged."""
    if current_tier == "directional" and not (
        loco >= DIRECTIONAL_MIN_AUC and ci95_lo > DIRECTIONAL_MIN_CI_LO
    ):
        return "experimental"
    return current_tier


def _dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)


def main() -> int:
    dry = "--dry-run" in sys.argv
    corrections = json.loads(CORRECTIONS.read_text(encoding="utf-8"))

    for slug, want in EXPECTED.items():
        got = corrections[slug]["honest_loco_auc"]
        if abs(got - want) > 1e-9:
            print(f"ABORT: {slug} honest={got} != expected {want}")
            return 1

    verified, retiered = 0, []

    # ── 1. the S3-fetched cards ──────────────────────────────────────────────
    for slug, corr in corrections.items():
        card_path = CARDS_DIR / f"{slug}.card.json"
        if not card_path.exists():
            print(f"ABORT: missing card {card_path.name}")
            return 1
        text = card_path.read_text(encoding="utf-8")
        card = json.loads(text)
        before = json.loads(text)

        honest = corr["honest_loco_auc"]
        for card_key, corr_key in STATS_FIELDS.items():
            card["stats"][card_key] = corr[corr_key]
        card["greedy_walk"]["final_global_auc"] = honest
        new_tier = honest_tier(card.get("tier"), honest, corr["honest_ci95_lo"])
        tier_changed = new_tier != card.get("tier")
        if tier_changed:
            card["tier"] = new_tier
            retiered.append((slug, before.get("tier"), new_tier))

        diffs = _diff_leaves(before, card)
        allowed = {
            "stats.loco_auc", "stats.ci95_lo", "stats.ci95_hi",
            "stats.ci80_lo", "stats.ci80_hi", "greedy_walk.final_global_auc",
        } | ({"tier"} if tier_changed else set())
        unexpected = set(diffs) - allowed
        if unexpected:
            print(f"ABORT: {slug} card would change unexpected fields: {sorted(unexpected)}")
            return 1
        if diffs and not dry:
            card_path.write_text(_dump(card), encoding="utf-8")
        # Idempotent-safe: verify the card now holds the honest value regardless
        # of whether THIS run changed it (a re-run over already-patched cards).
        if abs(card["stats"]["loco_auc"] - honest) < 1e-12:
            verified += 1

    # ── 2. the git-tracked recipe-tracker.json ───────────────────────────────
    tracker = json.loads(TRACKER.read_text(encoding="utf-8"))
    tracker_before = json.loads(TRACKER.read_text(encoding="utf-8"))
    by_id = {r["recipe_id"]: r for r in tracker["recipes"]}
    n_tracker_retier = 0
    for slug, corr in corrections.items():
        r = by_id.get(slug)
        if r is None:
            print(f"ABORT: recipe-tracker.json missing recipe {slug}")
            return 1
        s = r["stats"]
        s["loco_auc"] = corr["honest_loco_auc"]
        s["ci95_lo"] = corr["honest_ci95_lo"]
        s["ci95_hi"] = corr["honest_ci95_hi"]
        nt = honest_tier(r.get("tier"), corr["honest_loco_auc"], corr["honest_ci95_lo"])
        if nt != r.get("tier"):
            r["tier"] = nt
            s["tier_label_user_facing"] = nt.capitalize()
            n_tracker_retier += 1
    # Adjust tier_counts by the observed downgrades (preserves the file's own
    # counting convention — which excludes the 2 removed recipes).
    if n_tracker_retier:
        tracker["tier_counts"]["directional"] -= n_tracker_retier
        tracker["tier_counts"]["experimental"] += n_tracker_retier

    # Guard: only stats.{loco_auc,ci95_lo,ci95_hi,tier_label_user_facing}, tier,
    # and tier_counts may differ in the tracker.
    tdiffs = _diff_leaves(tracker_before, tracker)
    for p in tdiffs:
        ok = (
            p.startswith("tier_counts.")
            or p.endswith(".tier")
            or p.endswith(".stats.loco_auc")
            or p.endswith(".stats.ci95_lo")
            or p.endswith(".stats.ci95_hi")
            or p.endswith(".stats.tier_label_user_facing")
        )
        if not ok:
            print(f"ABORT: recipe-tracker.json unexpected change: {p}")
            return 1
    if tdiffs and not dry:
        TRACKER.write_text(_dump(tracker), encoding="utf-8")

    # ── report ───────────────────────────────────────────────────────────────
    print(f"{'APPLIED' if not dry else 'DRY-RUN'}: {verified}/34 cards at honest value; "
          f"recipe-tracker.json {len(tdiffs)} leaf-changes.")
    print(f"tier downgrades (directional -> experimental): {len(retiered)}")
    for slug, old, new in retiered:
        print(f"  {slug}: {old} -> {new}")
    print(f"tier_counts now: {tracker['tier_counts']}")
    if verified != 34:
        print(f"WARN: expected 34 cards at honest value, saw {verified}")
        return 1
    return 0


def _diff_leaves(a, b, prefix=""):
    """Return the set of dotted leaf-paths whose value differs between a and b."""
    out = set()
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a.keys() | b.keys():
            path = f"{prefix}.{k}" if prefix else k
            out |= _diff_leaves(a.get(k), b.get(k), path)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out |= _diff_leaves(x, y, f"{prefix}[{i}]")
    elif a != b:
        out.add(prefix)
    return out


if __name__ == "__main__":
    sys.exit(main())
