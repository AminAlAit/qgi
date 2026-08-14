#!/usr/bin/env python3
# THROWAWAY — no tests per #373.
# Pre-Athena proxy simulator for V1.9.2 Fix D (shelved per #378).
# Ran once on 2026-04-22 as a z-of-z approximation; superseded by
# simulate_fix_d_real.py (Athena-backed). Neither is re-runnable as
# Fix D itself is shelved until event-curation coverage >=190 per
# docs/specs/methodology/recipes/v1.9.2-design.md. Kept for paper trail
# in qgi-ml/results/fix_d_shelved_2026_04_22/ only.
"""
V1.9.2 Fix D proxy simulation.

PROXY CAVEAT: real Fix D re-z-normalizes the raw per-(country, category)
recipe scores against each category's global distribution. Those raw
scores live in the Athena recipes table and cannot be recovered from
country-risks.json alone. This simulator instead treats V1.9.1's
per-country z_score field as the input signal and applies Fix-D-style
cross-country per-category z-normalization on top of it ("z-of-z").

What the proxy captures:
- Directional validation: do the predicted tier flips (Iran/Ukraine HIGH,
  Cape Verde/Denmark not-HIGH) hold under a Fix-D-like transformation?
- Threshold sweep shape: where in the salience distribution does the
  HIGH-share band [25, 45] fall?

What the proxy does NOT capture:
- Exact Fix D tier assignments — the math is "within-country standout
  z, normalized across countries" not "raw signal z across countries".
- Venezuela recovery — Venezuela's V1.9.1 top category is elections
  (0.6 severity). Its civil_war z_score is likely near 0 or negative,
  so proxy Fix D cannot recover Venezuela through civil_war. Real Fix D
  might, because Venezuela's RAW civil_war signal may still exceed the
  global per-category mean.

Usage:
    python simulate_fix_d.py \\
        --input ../../.tmp/country-risks-v191.json \\
        --output ../../.tmp/fix_d_simulation.json
"""

import argparse
import json
import math
import statistics
from collections import defaultdict


# Face-validity canonical set — same as golden test set (#379) direction.
FACE_VALIDITY = {
    # Expected HIGH (V1.9.1 correct)
    "Syria": "HIGH",
    "Somalia": "HIGH",
    "Yemen": "HIGH",
    "Afghanistan": "HIGH",
    "Lebanon": "HIGH",
    "Ethiopia": "HIGH",
    "Pakistan": "HIGH",
    # Expected HIGH (V1.9.1 misses — Fix D targets)
    "Iran": "HIGH",
    "Ukraine": "HIGH",
    "Venezuela": "HIGH",
    # Expected NOT HIGH (V1.9.1 correct after Fix C)
    "Cape Verde": "NOT_HIGH",
    "Denmark": "NOT_HIGH",
    "Germany": "NOT_HIGH",
    "Costa Rica": "NOT_HIGH",
}


def load_input(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_global_zscore_per_category(countries):
    """
    For each (tier, category), collect z_scores across all countries,
    compute μ_k and σ_k, return a lookup {(tier, category): (μ, σ)}.
    """
    collected = defaultdict(list)
    for cid, country in countries.items():
        for tier_name, tier_data in country.get("tiers", {}).items():
            for cat in tier_data.get("top_categories", []):
                key = (tier_name, cat["category"])
                collected[key].append(cat["z_score"])

    stats = {}
    for key, values in collected.items():
        if len(values) < 2:
            continue
        mu = statistics.mean(values)
        sigma = statistics.pstdev(values)
        if sigma < 1e-6:
            sigma = 1e-6
        stats[key] = (mu, sigma, len(values))
    return stats


def apply_fix_d(countries, stats):
    """
    Recompute salience_global per (country, tier, category) as:
        z_global = (z_score_V191 - μ_k) / σ_k
        salience_global = z_global × severity_tier

    Returns a new dict of countries with added global_salience fields
    and a new max_global_salience per country.
    """
    out = {}
    for cid, country in countries.items():
        new_country = {
            "name": country["name"],
            "alpha_2": country.get("alpha_2", ""),
            "curated": country.get("curated", False),
            "v191_overall_risk_tier": country.get("overall_risk_tier", "INDICATIVE"),
            "tiers": {},
            "max_global_salience": -999.0,
            "top_global_category": None,
            "top_global_tier": None,
        }
        for tier_name, tier_data in country.get("tiers", {}).items():
            new_cats = []
            for cat in tier_data.get("top_categories", []):
                key = (tier_name, cat["category"])
                if key not in stats:
                    continue
                mu, sigma, _ = stats[key]
                z_global = (cat["z_score"] - mu) / sigma
                salience_global = z_global * cat["severity_tier"]
                new_cats.append({
                    "category": cat["category"],
                    "z_v191": cat["z_score"],
                    "z_global": round(z_global, 3),
                    "severity_tier": cat["severity_tier"],
                    "salience_v191": cat["salience_score"],
                    "salience_global": round(salience_global, 4),
                })
                if salience_global > new_country["max_global_salience"]:
                    new_country["max_global_salience"] = salience_global
                    new_country["top_global_category"] = cat["category"]
                    new_country["top_global_tier"] = tier_name
            new_cats.sort(key=lambda c: -c["salience_global"])
            new_country["tiers"][tier_name] = new_cats
        out[cid] = new_country
    return out


def label_tier(max_salience, high_threshold, moderate_ratio=0.65):
    """
    Single-threshold labeling (Fix D simplified):
      HIGH if max_salience >= high_threshold
      MODERATE if max_salience >= high_threshold × moderate_ratio
      else INDICATIVE
    """
    moderate_threshold = high_threshold * moderate_ratio
    if max_salience >= high_threshold:
        return "HIGH"
    if max_salience >= moderate_threshold:
        return "MODERATE"
    return "INDICATIVE"


def threshold_sweep(countries, start=0.0, stop=3.0, step=0.1):
    """
    Sweep high_threshold from start to stop in step increments.
    Return a list of sweep results with distribution + face validity.
    """
    results = []
    thresholds = [round(start + i * step, 2) for i in range(int((stop - start) / step) + 1)]
    for th in thresholds:
        dist = {"HIGH": 0, "MODERATE": 0, "INDICATIVE": 0}
        by_country = {}
        for cid, c in countries.items():
            tier = label_tier(c["max_global_salience"], th)
            dist[tier] += 1
            by_country[c["name"]] = tier

        fv_hits = 0
        fv_total = 0
        fv_misses = []
        for name, expected in FACE_VALIDITY.items():
            if name not in by_country:
                continue
            fv_total += 1
            actual = by_country[name]
            match = (
                (expected == "HIGH" and actual == "HIGH")
                or (expected == "NOT_HIGH" and actual != "HIGH")
            )
            if match:
                fv_hits += 1
            else:
                fv_misses.append(f"{name} expected={expected} actual={actual}")

        total = sum(dist.values())
        high_share = dist["HIGH"] / total if total else 0
        results.append({
            "threshold": th,
            "dist": dist,
            "high_share_pct": round(high_share * 100, 1),
            "face_validity": f"{fv_hits}/{fv_total}",
            "fv_hits": fv_hits,
            "fv_total": fv_total,
            "fv_misses": fv_misses,
            "in_target_band": 0.25 <= high_share <= 0.45,
        })
    return results


def pick_recommended_threshold(sweep):
    """
    Pick the threshold that maximizes face-validity within the
    target [25, 45]% HIGH band. Tiebreak: threshold closest to
    HIGH share of 35% (middle of band).
    """
    candidates = [r for r in sweep if r["in_target_band"]]
    if not candidates:
        candidates = sweep
    candidates.sort(key=lambda r: (-r["fv_hits"], abs(r["high_share_pct"] - 35)))
    return candidates[0] if candidates else None


def compare_v191_vs_fix_d(countries_v191, countries_fix_d, recommended_threshold):
    """
    Build a side-by-side tier comparison for face-validity countries +
    distribution summary.
    """
    th = recommended_threshold["threshold"]
    rows = []
    for name in FACE_VALIDITY.keys():
        cid = next(
            (c for c, v in countries_v191.items() if v["name"] == name),
            None,
        )
        if not cid:
            continue
        v191_tier = countries_v191[cid].get("overall_risk_tier", "?")
        fix_d_tier = label_tier(countries_fix_d[cid]["max_global_salience"], th)
        expected = FACE_VALIDITY[name]
        rows.append({
            "country": name,
            "expected": expected,
            "v191_tier": v191_tier,
            "fix_d_tier": fix_d_tier,
            "max_salience_v191": max(
                (cat["salience_score"]
                 for tier in countries_v191[cid].get("tiers", {}).values()
                 for cat in tier.get("top_categories", [])),
                default=0.0,
            ),
            "max_salience_fix_d": round(countries_fix_d[cid]["max_global_salience"], 3),
            "top_cat_fix_d": countries_fix_d[cid]["top_global_category"],
            "v191_match": (
                (expected == "HIGH" and v191_tier == "HIGH")
                or (expected == "NOT_HIGH" and v191_tier != "HIGH")
            ),
            "fix_d_match": (
                (expected == "HIGH" and fix_d_tier == "HIGH")
                or (expected == "NOT_HIGH" and fix_d_tier != "HIGH")
            ),
        })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="../../.tmp/country-risks-v191.json")
    parser.add_argument("--output", default="../../.tmp/fix_d_simulation.json")
    args = parser.parse_args()

    print("Loading V1.9.1 output...")
    data = load_input(args.input)
    countries = data["countries"]
    print(f"  {len(countries)} countries loaded")

    print("\nComputing per-category global statistics...")
    stats = compute_global_zscore_per_category(countries)
    print(f"  {len(stats)} (tier, category) distributions")

    # Stats summary (distribution of sigmas for transparency)
    sigmas = sorted([s[1] for s in stats.values()])
    print(f"  sigma_k distribution: min={sigmas[0]:.3f} "
          f"p25={sigmas[len(sigmas)//4]:.3f} "
          f"med={sigmas[len(sigmas)//2]:.3f} "
          f"p75={sigmas[3*len(sigmas)//4]:.3f} "
          f"max={sigmas[-1]:.3f}")

    print("\nApplying Fix D proxy...")
    countries_fix_d = apply_fix_d(countries, stats)

    print("\nThreshold sweep...")
    sweep = threshold_sweep(countries_fix_d)
    print(f"  {len(sweep)} thresholds evaluated")

    recommended = pick_recommended_threshold(sweep)
    print(f"\nRecommended threshold: {recommended['threshold']}")
    print(f"  HIGH={recommended['dist']['HIGH']} "
          f"MODERATE={recommended['dist']['MODERATE']} "
          f"INDICATIVE={recommended['dist']['INDICATIVE']} "
          f"(HIGH share {recommended['high_share_pct']}%)")
    print(f"  Face validity: {recommended['face_validity']}")
    if recommended["fv_misses"]:
        print("  Misses:")
        for m in recommended["fv_misses"]:
            print(f"    - {m}")

    comparison = compare_v191_vs_fix_d(countries, countries_fix_d, recommended)

    print("\nFace-validity country comparison (V1.9.1 vs Fix D proxy):")
    print(f"{'Country':<15} {'Expect':<8} {'V1.9.1':<12} {'FixD':<12} "
          f"{'salV191':>8} {'salFixD':>8}  topCat")
    print("-" * 95)
    for row in comparison:
        mark_v = "+" if row["v191_match"] else "-"
        mark_d = "+" if row["fix_d_match"] else "-"
        print(f"{row['country']:<15} "
              f"{row['expected']:<8} "
              f"{mark_v}{row['v191_tier']:<11} "
              f"{mark_d}{row['fix_d_tier']:<11} "
              f"{row['max_salience_v191']:>8.3f} "
              f"{row['max_salience_fix_d']:>8.3f}  "
              f"{row['top_cat_fix_d']}")

    print("\nFull sweep (target band [25, 45]% HIGH):")
    print(f"{'Thr':>5} {'HIGH':>5} {'MOD':>5} {'IND':>5} {'H%':>6} "
          f"{'FV':>6} band?")
    for r in sweep:
        if r["high_share_pct"] > 0:
            mark = "*" if r["in_target_band"] else " "
            print(f"{r['threshold']:>5.1f} {r['dist']['HIGH']:>5} "
                  f"{r['dist']['MODERATE']:>5} {r['dist']['INDICATIVE']:>5} "
                  f"{r['high_share_pct']:>5.1f}% "
                  f"{r['face_validity']:>6} {mark}")

    out = {
        "proxy_caveat": (
            "This simulation applies Fix-D-style per-category global "
            "z-normalization to V1.9.1's per-country z_score field, not "
            "to the raw recipe scores. It tests directional validity of "
            "Fix D predictions but is NOT a substitute for the real Fix D "
            "simulation which requires Athena-level raw-score access."
        ),
        "input_file": args.input,
        "input_version": data.get("version"),
        "n_countries": len(countries),
        "n_tier_category_distributions": len(stats),
        "sigma_distribution": {
            "min": round(sigmas[0], 4),
            "p25": round(sigmas[len(sigmas)//4], 4),
            "median": round(sigmas[len(sigmas)//2], 4),
            "p75": round(sigmas[3*len(sigmas)//4], 4),
            "max": round(sigmas[-1], 4),
        },
        "sweep": sweep,
        "recommended_threshold": recommended,
        "face_validity_comparison": comparison,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
