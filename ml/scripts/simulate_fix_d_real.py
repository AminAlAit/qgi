#!/usr/bin/env python3
# DEFERRED — no tests per #373.
# Athena-backed Fix D simulator. Fix D is shelved per #378 until event-
# curation coverage reaches 190 countries. When that trigger fires, this
# script is RE-RUN against fresh staging data and may be replaced by a
# cleaner implementation per Roshani's stats-council review (docs/specs/
# methodology/recipes/v1.9.2-design.md). Not worth testing in its
# current shape — the functional contract will likely change. When the
# stats council finalizes the design, promote the canonical form to
# production + add tests at that point.
"""
V1.9.2 Fix D REAL simulation (Athena-backed, read-only).

Unlike simulate_fix_d.py (the z-of-z proxy), this script:
1. Queries the staging recipes table for raw pre-z scores per
   (country, category, tier) across all countries.
2. Applies the same scoring formula as generate_country_risks.py
   (prevalence + correlation + indicator_count + recency baseline).
3. Computes per-category global z (real Fix D), including zeros from
   countries that don't appear in a given category.
4. Sweeps the single HIGH threshold.
5. Compares against V1.9.1 per-country z for the same inputs.

Read-only. No writes to S3. Results land in .tmp/.

Usage:
    source .tmp/aws-session.sh
    python simulate_fix_d_real.py \\
        --bucket qgi-data-lake-771606957899 \\
        --output ../../.tmp/fix_d_real_simulation.json
"""

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict

import boto3


TIERS = {'S': (3, 8), 'M': (9, 20), 'L': (21, 40), 'XL': (41, 999)}
WORKGROUP = 'QGI-Lambda-Workgroup'


# Face-validity canonical set — ALL 14 countries including those
# potentially absent from staging (proxy simulation flagged this).
FACE_VALIDITY = {
    "Syria": "HIGH",
    "Somalia": "HIGH",
    "Yemen": "HIGH",
    "Afghanistan": "HIGH",
    "Lebanon": "HIGH",
    "Ethiopia": "HIGH",
    "Pakistan": "HIGH",     # disputed; per V1.9.1 notes, actually MODERATE-expected
    "Iran": "HIGH",
    "Ukraine": "HIGH",
    "Venezuela": "HIGH",
    "Cape Verde": "NOT_HIGH",
    "Cabo Verde": "NOT_HIGH",  # alternate name
    "Denmark": "NOT_HIGH",
    "Germany": "NOT_HIGH",
    "Costa Rica": "NOT_HIGH",
}


def run_query(athena, sql, bucket):
    r = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={'Database': 'qgi_data'},
        WorkGroup=WORKGROUP,
        ResultConfiguration={'OutputLocation': f's3://{bucket}/query_results/'},
    )
    qid = r['QueryExecutionId']
    while True:
        time.sleep(2)
        s = athena.get_query_execution(QueryExecutionId=qid)['QueryExecution']['Status']
        if s['State'] in ('SUCCEEDED', 'FAILED', 'CANCELLED'):
            break
    if s['State'] != 'SUCCEEDED':
        print(f"  QUERY FAILED: {s.get('StateChangeReason', '?')[:300]}", file=sys.stderr)
        return []
    rows, result = [], athena.get_query_results(QueryExecutionId=qid, MaxResults=1000)
    cols = [c['Name'] for c in result['ResultSet']['ResultSetMetadata']['ColumnInfo']]
    for row in result['ResultSet']['Rows'][1:]:
        rows.append({cols[i]: row['Data'][i].get('VarCharValue') for i in range(len(cols))})
    while 'NextToken' in result:
        result = athena.get_query_results(
            QueryExecutionId=qid, NextToken=result['NextToken'], MaxResults=1000)
        for row in result['ResultSet']['Rows']:
            rows.append({cols[i]: row['Data'][i].get('VarCharValue') for i in range(len(cols))})
    return rows


def load_severity_tiers():
    path = os.path.join(
        os.path.dirname(__file__), '..', '..',
        'qgi-data', 'reference', 'category_severity_tiers.json',
    )
    with open(path) as f:
        data = json.load(f)
    lookup = {}
    for weight_str, tier_info in data["tiers"].items():
        weight = float(weight_str)
        for cat in tier_info["categories"]:
            lookup[cat] = weight
    return lookup


def compute_raw_scores(athena, bucket, recency, persist):
    """
    Returns:
        raw_scores: dict[(cid, cat, tier)] -> raw_score (pre-z)
        recipe_counts: dict[(cid, cat, tier)] -> count
    Same scoring formula as generate_country_risks.py.
    """
    raw_scores = {}
    recipe_counts = {}

    for tier_name, (lo, hi) in TIERS.items():
        print(f"  Querying tier {tier_name} ({lo}-{hi})...")

        pe = {}
        for r in run_query(athena,
                f'SELECT country_a_id, count(DISTINCT country_b_id) as p '
                f'FROM qgi_data.scdis WHERE length BETWEEN {lo} AND {hi} '
                f'GROUP BY country_a_id', bucket):
            try:
                pe[r['country_a_id']] = int(r['p'])
            except Exception:
                pass

        recipes = run_query(athena,
            f"SELECT country_a_id, event_category, count(*) as c, "
            f"avg(avg_correlation) as a, avg(indicator_count) as i "
            f"FROM qgi_data.recipes WHERE event_category IS NOT NULL "
            f"AND length BETWEEN {lo} AND {hi} "
            f"GROUP BY country_a_id, event_category", bucket)

        for r in recipes:
            try:
                cid = int(float(r['country_a_id']))
                partners = pe.get(r['country_a_id'], pe.get(str(cid), 5))
                if isinstance(partners, str):
                    partners = int(partners)
                prevalence = float(r['c']) / max(partners, 5)
                score = (0.30 * math.log(prevalence + 0.01)
                         + 0.40 * float(r['a'])
                         + 0.15 * math.log(float(r['i']) + 1)
                         + 0.15)
                ly = recency.get((cid, r['event_category']))
                if ly:
                    score += 0.15 * (0.85 ** max(2025 - ly, 0))
                raw_scores[(cid, r['event_category'], tier_name)] = score
                recipe_counts[(cid, r['event_category'], tier_name)] = int(float(r['c']))
            except Exception:
                pass

    return raw_scores, recipe_counts


def zscore_per_country_v191(raw_scores):
    """V1.9.1 per-country z — same logic as generate_country_risks.py.
    Normalizes per (country, tier) — i.e. for each country, within each tier.
    """
    grouped = defaultdict(dict)
    for (cid, cat, tier), score in raw_scores.items():
        grouped[(cid, tier)][cat] = score
    result = {}
    for (cid, tier), cats in grouped.items():
        vals = list(cats.values())
        if len(vals) < 2:
            for cat, score in cats.items():
                result[(cid, cat, tier)] = 0.0
            continue
        mean = sum(vals) / len(vals)
        std = max((sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5, 1e-6)
        for cat, score in cats.items():
            result[(cid, cat, tier)] = (score - mean) / std
    return result


def zscore_per_category_fix_d(raw_scores, all_countries):
    """V1.9.2 Fix D — per-category global z across all countries.

    For each (category, tier), compute mean/std across ALL countries.
    Countries with no recipe in that (cat, tier) get score=0
    (score < 0 is impossible given formula, so 0 is natural baseline).
    """
    # Collect per-(category, tier) scores with zero-fill
    by_cat_tier = defaultdict(dict)  # (cat, tier) -> {cid: score}
    cat_tiers_seen = set()
    for (cid, cat, tier), score in raw_scores.items():
        by_cat_tier[(cat, tier)][cid] = score
        cat_tiers_seen.add((cat, tier))

    # For each (cat, tier), augment with zeros for countries not in raw_scores for this pair
    for (cat, tier) in cat_tiers_seen:
        for cid in all_countries:
            if cid not in by_cat_tier[(cat, tier)]:
                by_cat_tier[(cat, tier)][cid] = 0.0

    # Compute global stats per (cat, tier)
    stats = {}
    for (cat, tier), cid_scores in by_cat_tier.items():
        vals = list(cid_scores.values())
        if len(vals) < 2:
            continue
        mu = statistics.mean(vals)
        sigma = statistics.pstdev(vals)
        if sigma < 1e-6:
            sigma = 1e-6
        stats[(cat, tier)] = {
            'mu': mu,
            'sigma': sigma,
            'n_total': len(vals),
            'n_nonzero': sum(1 for v in vals if v > 0),
            'min': min(vals),
            'max': max(vals),
        }

    # Compute z_global for every (cid, cat, tier) where we had a score
    z_global = {}
    for (cid, cat, tier), score in raw_scores.items():
        key = (cat, tier)
        if key not in stats:
            continue
        z = (score - stats[key]['mu']) / stats[key]['sigma']
        z_global[(cid, cat, tier)] = z

    return z_global, stats


def label_tier_single_threshold(max_salience, high_threshold, moderate_ratio):
    """Fix D single-threshold tier labeling."""
    moderate_threshold = high_threshold * moderate_ratio
    if max_salience >= high_threshold:
        return "HIGH"
    if max_salience >= moderate_threshold:
        return "MODERATE"
    return "INDICATIVE"


def label_tier_v191(category_scores_for_country, config):
    """V1.9.1 3-layer hybrid (exact copy of generate_country_risks.py logic)."""
    if not category_scores_for_country:
        return "INDICATIVE"
    thresholds = config['thresholds']
    composite = config.get('composite_rule', {})
    if composite.get('enabled'):
        floor = composite['min_salience_floor']
        min_n = composite['min_categories_above_salience']
        min_sev = composite['min_severity_for_at_least_one']
        above = [c for c in category_scores_for_country if c['salience_score'] >= floor]
        if len(above) >= min_n and any(c['severity_tier'] >= min_sev for c in above):
            return "HIGH"
    top = max(category_scores_for_country, key=lambda c: c['salience_score'])
    is_crisis = top['severity_tier'] >= 1.0
    high_cut = thresholds['CRISIS_HIGH'] if is_crisis else thresholds['REGULAR_HIGH']
    moderate_cut = thresholds['CRISIS_MODERATE'] if is_crisis else thresholds['REGULAR_MODERATE']
    top_sal = top['salience_score']
    if top_sal >= high_cut:
        return "HIGH"
    if top_sal >= moderate_cut:
        return "MODERATE"
    return "INDICATIVE"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--region', default='eu-central-1')
    parser.add_argument('--output', default='../../.tmp/fix_d_real_simulation.json')
    parser.add_argument('--moderate-ratio', type=float, default=0.65,
                        help="MODERATE threshold = HIGH threshold × this ratio")
    args = parser.parse_args()

    athena = boto3.client('athena', region_name=args.region)

    print("Loading severity tiers...")
    severity = load_severity_tiers()
    print(f"  {len(severity)} categories with severity mapped")

    # Load V1.9.1 config (for V1.9.1 comparison)
    v191_config_path = os.path.join(
        os.path.dirname(__file__), '..', '..',
        'qgi-data', 'scoring', 'V1.9.1.json',
    )
    with open(v191_config_path) as f:
        v191_config = json.load(f)

    print("\nLoading countries...")
    cn = {}
    all_cids = set()
    for r in run_query(athena,
            'SELECT id, name_1, alpha_2 FROM qgi_data.countries WHERE name_1 IS NOT NULL',
            args.bucket):
        try:
            cid = int(float(r['id']))
            cn[cid] = {'name': r['name_1'], 'alpha_2': r.get('alpha_2', '')}
            all_cids.add(cid)
        except Exception:
            pass
    print(f"  {len(cn)} countries")

    print("\nLoading recency...")
    recency = {}
    for r in run_query(athena,
            'SELECT country_id, category_normalized, max(year) as y '
            'FROM qgi_data.events WHERE category_normalized IS NOT NULL '
            'GROUP BY country_id, category_normalized', args.bucket):
        try:
            recency[(int(float(r['country_id'])), r['category_normalized'])] = int(r['y'])
        except Exception:
            pass

    print("\nLoading persistence...")
    persist = {}
    for r in run_query(athena,
            'SELECT country_id, category_normalized, count(*) as c '
            'FROM qgi_data.events WHERE year BETWEEN 2023 AND 2025 '
            'AND category_normalized IS NOT NULL '
            'GROUP BY country_id, category_normalized', args.bucket):
        try:
            persist[(int(float(r['country_id'])), r['category_normalized'])] = float(r['c']) / 3.0
        except Exception:
            pass

    print("\nComputing raw scores (all tiers)...")
    raw_scores, recipe_counts = compute_raw_scores(athena, args.bucket, recency, persist)
    print(f"  {len(raw_scores)} (country, category, tier) raw scores")

    # Dedupe countries actually present in raw_scores
    countries_with_recipes = {c[0] for c in raw_scores.keys()}
    print(f"  {len(countries_with_recipes)} distinct countries with recipes")

    print("\nV1.9.1 per-country z...")
    z_v191 = zscore_per_country_v191(raw_scores)

    print("\nFix D per-category global z (with zero-fill)...")
    z_fix_d, stats_fix_d = zscore_per_category_fix_d(raw_scores, all_cids)
    print(f"  {len(stats_fix_d)} (category, tier) distributions")
    sigmas = sorted([s['sigma'] for s in stats_fix_d.values()])
    print(f"  sigma: min={sigmas[0]:.3f} "
          f"p25={sigmas[len(sigmas)//4]:.3f} "
          f"med={sigmas[len(sigmas)//2]:.3f} "
          f"p75={sigmas[3*len(sigmas)//4]:.3f} "
          f"max={sigmas[-1]:.3f}")

    # Per-country max salience and top category under each approach
    per_country = {}
    for cid in countries_with_recipes:
        entry = {
            'cid': cid,
            'name': cn.get(cid, {}).get('name', f'#{cid}'),
            'alpha_2': cn.get(cid, {}).get('alpha_2', ''),
            'v191_top_salience': -999.0,
            'v191_top_cat': None,
            'v191_top_tier': None,
            'v191_all_salience': [],
            'fix_d_top_salience': -999.0,
            'fix_d_top_cat': None,
            'fix_d_top_tier': None,
        }
        for (c, cat, tier), raw in raw_scores.items():
            if c != cid:
                continue
            sev = severity.get(cat, 0.3)
            # V1.9.1
            z1 = z_v191.get((cid, cat, tier), 0.0)
            sal1 = z1 * sev
            entry['v191_all_salience'].append({
                'salience_score': sal1,
                'severity_tier': sev,
                'category': cat,
                'tier': tier,
            })
            if sal1 > entry['v191_top_salience']:
                entry['v191_top_salience'] = sal1
                entry['v191_top_cat'] = cat
                entry['v191_top_tier'] = tier
            # Fix D
            z2 = z_fix_d.get((cid, cat, tier), 0.0)
            sal2 = z2 * sev
            if sal2 > entry['fix_d_top_salience']:
                entry['fix_d_top_salience'] = sal2
                entry['fix_d_top_cat'] = cat
                entry['fix_d_top_tier'] = tier
        entry['v191_tier'] = label_tier_v191(entry['v191_all_salience'], v191_config)
        per_country[cid] = entry

    # Also apply V1.9.1 tier distribution for comparison
    v191_dist = defaultdict(int)
    for e in per_country.values():
        v191_dist[e['v191_tier']] += 1

    # Fix D threshold sweep
    print("\nFix D threshold sweep...")
    sweep = []
    for th_int in range(0, 51):
        th = th_int * 0.1
        dist = defaultdict(int)
        by_name = {}
        for e in per_country.values():
            label = label_tier_single_threshold(e['fix_d_top_salience'], th, args.moderate_ratio)
            dist[label] += 1
            by_name[e['name']] = label

        fv_hits = 0
        fv_total = 0
        fv_misses = []
        for name, expected in FACE_VALIDITY.items():
            if name not in by_name:
                continue
            fv_total += 1
            actual = by_name[name]
            match = (
                (expected == "HIGH" and actual == "HIGH")
                or (expected == "NOT_HIGH" and actual != "HIGH")
            )
            if match:
                fv_hits += 1
            else:
                fv_misses.append(f"{name} exp={expected} got={actual}")

        total = sum(dist.values())
        high_share = dist['HIGH'] / total if total else 0
        sweep.append({
            'threshold': round(th, 2),
            'dist': dict(dist),
            'high_share_pct': round(high_share * 100, 1),
            'in_target_band': 0.25 <= high_share <= 0.45,
            'face_validity': f"{fv_hits}/{fv_total}",
            'fv_hits': fv_hits,
            'fv_total': fv_total,
            'fv_misses': fv_misses,
        })

    # Pick best threshold: max FV within target band, tiebreak by distance to 35% HIGH
    candidates = [s for s in sweep if s['in_target_band']]
    if not candidates:
        candidates = sweep
    candidates.sort(key=lambda r: (-r['fv_hits'], abs(r['high_share_pct'] - 35)))
    recommended = candidates[0]

    print(f"\nRecommended threshold: {recommended['threshold']}")
    print(f"  dist: {recommended['dist']}")
    print(f"  HIGH share: {recommended['high_share_pct']}%")
    print(f"  Face validity: {recommended['face_validity']}")
    for m in recommended['fv_misses']:
        print(f"    miss: {m}")

    # Face-validity comparison table
    print("\n" + "=" * 95)
    print(f"{'Country':<16} {'Expect':<9} {'V1.9.1':<13} {'FixD':<13} "
          f"{'salV191':>9} {'salFixD':>9}  topCatFixD")
    print("-" * 95)
    fv_table = []
    for name, expected in FACE_VALIDITY.items():
        matches = [e for e in per_country.values() if e['name'] == name]
        if not matches:
            continue
        e = matches[0]
        fd_tier = label_tier_single_threshold(
            e['fix_d_top_salience'], recommended['threshold'], args.moderate_ratio)
        v191_match = ((expected == "HIGH" and e['v191_tier'] == "HIGH")
                      or (expected == "NOT_HIGH" and e['v191_tier'] != "HIGH"))
        fd_match = ((expected == "HIGH" and fd_tier == "HIGH")
                    or (expected == "NOT_HIGH" and fd_tier != "HIGH"))
        fv_table.append({
            'name': name,
            'expected': expected,
            'v191_tier': e['v191_tier'],
            'fix_d_tier': fd_tier,
            'v191_top_salience': round(e['v191_top_salience'], 3),
            'fix_d_top_salience': round(e['fix_d_top_salience'], 3),
            'fix_d_top_cat': e['fix_d_top_cat'],
            'fix_d_top_tier': e['fix_d_top_tier'],
            'v191_match': v191_match,
            'fix_d_match': fd_match,
        })
        m1 = '+' if v191_match else '-'
        m2 = '+' if fd_match else '-'
        print(f"{name:<16} {expected:<9} "
              f"{m1}{e['v191_tier']:<12} "
              f"{m2}{fd_tier:<12} "
              f"{e['v191_top_salience']:>9.3f} "
              f"{e['fix_d_top_salience']:>9.3f}  "
              f"{e['fix_d_top_cat']} [{e['fix_d_top_tier']}]")

    # Save full output
    print("\n" + "=" * 95)
    print(f"V1.9.1 tier distribution: {dict(v191_dist)}")
    out = {
        'simulation_type': 'REAL Fix D (Athena-backed, full zero-fill)',
        'n_countries': len(cn),
        'n_countries_with_recipes': len(countries_with_recipes),
        'n_raw_scores': len(raw_scores),
        'n_category_tier_distributions': len(stats_fix_d),
        'sigma_distribution_fix_d': {
            'min': round(sigmas[0], 4),
            'p25': round(sigmas[len(sigmas)//4], 4),
            'median': round(sigmas[len(sigmas)//2], 4),
            'p75': round(sigmas[3*len(sigmas)//4], 4),
            'max': round(sigmas[-1], 4),
        },
        'v191_tier_distribution': dict(v191_dist),
        'fix_d_sweep': sweep,
        'fix_d_recommended_threshold': recommended,
        'fix_d_moderate_ratio': args.moderate_ratio,
        'face_validity_comparison': fv_table,
        # Top-15 categories by global mean score per tier (informative)
        'top_categories_by_global_mean': sorted(
            [{'cat': k[0], 'tier': k[1], 'mu': round(v['mu'], 4),
              'sigma': round(v['sigma'], 4), 'n_nonzero': v['n_nonzero'],
              'max': round(v['max'], 4)}
             for k, v in stats_fix_d.items()],
            key=lambda x: -x['max'],
        )[:15],
    }

    # Also dump per-country result summary for top categories investigation
    out['per_country_summary'] = sorted(
        [{'name': e['name'], 'v191_tier': e['v191_tier'],
          'v191_top_salience': round(e['v191_top_salience'], 3),
          'fix_d_top_salience': round(e['fix_d_top_salience'], 3),
          'fix_d_tier_at_rec': label_tier_single_threshold(
              e['fix_d_top_salience'], recommended['threshold'], args.moderate_ratio),
          'fix_d_top_cat': e['fix_d_top_cat'],
          'fix_d_top_tier': e['fix_d_top_tier']}
         for e in per_country.values()],
        key=lambda x: -x['fix_d_top_salience'],
    )

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {args.output}")


if __name__ == '__main__':
    main()
