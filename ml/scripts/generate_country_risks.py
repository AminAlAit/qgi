#!/usr/bin/env python3
"""
Generate country-risks.json for the QGI frontend.

Pre-computes V1.8.1 z-score + RRF scores per (country, category, tier)
so the Country Intelligence Browser reads from a static JSON instead of
live Athena queries. Cost: $0 per page view.

Usage:
    python generate_country_risks.py \
        --bucket qgi-data-lake-771606957899 \
        --region eu-central-1 \
        --output country-risks.json \
        --upload
"""

import argparse
import boto3
import json
import math
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TIERS = {'S': (3, 8), 'M': (9, 20), 'L': (21, 40), 'XL': (41, 999)}
WORKGROUP = 'QGI-Lambda-Workgroup'

# Curated country IDs (55 countries with verified event histories)
CURATED_IDS = {
    1, 3, 6, 10, 18, 28, 31, 44, 45, 48, 54, 62, 63, 66, 69, 74, 81,
    82, 100, 101, 102, 103, 106, 107, 112, 113, 114, 117, 121, 124,
    131, 140, 147, 149, 159, 162, 167, 174, 176, 182, 195, 205, 206,
    208, 212, 217, 221, 227, 228, 233, 234, 235, 242, 243, 248,
}


# ---------------------------------------------------------------------------
# Athena helper
# ---------------------------------------------------------------------------
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
        print(f"  QUERY FAILED: {s.get('StateChangeReason', '?')[:200]}")
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


# ---------------------------------------------------------------------------
# Scoring (V1.8.1 — matches run_backtest.py)
# ---------------------------------------------------------------------------
def zscore_per_country(preds):
    by_country = defaultdict(dict)
    for (cid, cat), s in preds.items():
        by_country[cid][(cid, cat)] = s
    result = {}
    for cid, cp in by_country.items():
        vals = list(cp.values())
        if len(vals) < 2:
            result.update(cp)
            continue
        mean = sum(vals) / len(vals)
        std = max((sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5, 1e-6)
        for key, score in cp.items():
            result[key] = (score - mean) / std
    return result


def rank_fusion(recipe_preds, persist_preds, k=60):
    rr = {key: i + 1 for i, (key, _) in enumerate(
        sorted(recipe_preds.items(), key=lambda x: -x[1]))}
    pr = {key: i + 1 for i, (key, _) in enumerate(
        sorted(persist_preds.items(), key=lambda x: -x[1]))}
    all_keys = set(recipe_preds.keys()) | set(persist_preds.keys())
    max_rank = len(all_keys) + 1
    return {
        key: 1 / (k + rr.get(key, max_rank)) + 1 / (k + pr.get(key, max_rank))
        for key in all_keys
    }


# ---------------------------------------------------------------------------
# Severity tiers (salience-finding: high-consequence events rank higher)
# ---------------------------------------------------------------------------
def load_severity_tiers(path=None):
    """Load category severity tier weights from `category_severity_tiers.json`.

    T17 #310 fix (2026-04-19): the cross-repo relative path
    `../../qgi-data/reference/category_severity_tiers.json` silently falls
    back to an empty dict if the script is run from a standalone qgi-ml
    checkout (CI, a single-repo clone, etc.) — collapsing all severity
    weights to 0.3 and wrecking the scoring without any obvious signal.

    Priority order:
      1. Explicit `path` argument.
      2. `QGI_SEVERITY_TIERS_PATH` environment variable.
      3. `../../qgi-data/reference/category_severity_tiers.json` (legacy).
    """
    import os

    candidates = []
    if path:
        candidates.append(path)
    env_path = os.environ.get("QGI_SEVERITY_TIERS_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.append(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "qgi-data",
            "reference",
            "category_severity_tiers.json",
        )
    )

    for p in candidates:
        try:
            with open(p) as f:
                data = json.load(f)
        except FileNotFoundError:
            continue
        lookup = {}
        for weight_str, tier_info in data["tiers"].items():
            weight = float(weight_str)
            for cat in tier_info["categories"]:
                lookup[cat] = weight
        return lookup

    # No file found on any candidate path. Loud warning — silent failure
    # would produce a wrong-but-plausible scoring output.
    import sys
    msg = (
        "  ERROR: category_severity_tiers.json not found on any candidate path. "
        "Tried: " + ", ".join(candidates) + ". "
        "Pass --severity-tiers-path or set QGI_SEVERITY_TIERS_PATH."
    )
    print(msg, file=sys.stderr)
    return {}


SEVERITY_TIERS = load_severity_tiers()


def severity_weight(category):
    """Get severity tier weight for a category. Default 0.3 for unmapped categories."""
    return SEVERITY_TIERS.get(category, 0.3)


# Embedded fallback scoring config (mirrors qgi-data/scoring/V1.9.1.json).
DEFAULT_SCORING_CONFIG = {
    "_meta": {"scoring_version": "V1.9.1", "schema_version": 1},
    "thresholds": {
        "CRISIS_HIGH": 1.4,
        "REGULAR_HIGH": 2.0,
        "CRISIS_MODERATE": 1.0,
        "REGULAR_MODERATE": 1.3,
    },
    "composite_rule": {
        "enabled": True,
        "min_categories_above_salience": 2,
        "min_salience_floor": 1.3,
        "min_severity_for_at_least_one": 0.8,
    },
    "default_severity": 0.3,
    # #201 refinements (2026-05-15) — see qgi-data/scoring/V1.9.1.json.
    # Refinement 1 (raise HIGH to 1.5) was SUPERSEDED by V1.9.1's
    # severity-stratified thresholds above. Refinement 2 (min recipe count
    # gate) + Refinement 3 (per-category cap) close the gap.
    "min_recipe_count": 5,
    "category_salience_cap_percentile": 0.95,
    "category_salience_cap_min_observations": 20,
}


def load_scoring_config(path=None):
    """Load scoring config from qgi-data/scoring/V1.9.1.json.

    Priority: explicit path -> QGI_SCORING_CONFIG_PATH env var ->
    qgi-ml/scripts/../../qgi-data/scoring/V1.9.1.json. Silent fallback to
    DEFAULT_SCORING_CONFIG. Same pattern as load_severity_tiers.
    """
    candidates = []
    if path:
        candidates.append(path)
    env_path = os.environ.get("QGI_SCORING_CONFIG_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.append(
        os.path.join(
            os.path.dirname(__file__),
            "..", "..",
            "qgi-data", "scoring", "V1.9.1.json",
        )
    )
    for p in candidates:
        try:
            with open(p) as f:
                return json.load(f)
        except (FileNotFoundError, OSError):
            continue
    return DEFAULT_SCORING_CONFIG


def compute_per_category_caps(countries_data, percentile=0.95, min_observations=20):
    """#201 Refinement 3: per-category salience cap from p95 of observed scores.

    For each L3 event_category, compute the Nth percentile salience_score
    across all (country, tier) observations. Categories with fewer than
    `min_observations` non-null entries are LEFT UNCAPPED — small-sample p95
    is dominated by the single outlier we'd want to clip, which is
    counterproductive.

    The cap dampens runaway categories (the original motivation in #201:
    "Prevents civil_war_and_insurgency from monopolizing the top-N across
    all countries"). It does NOT alter the underlying z-scores, only the
    salience contribution passed downstream to risk_tier_label and the
    display ranking.

    Args:
        countries_data: {cid: {tier_name: [{'category', 'salience_score',
                        ...}, ...], ...}, ...} from the tier loop.
        percentile: 0.95 by default (95th percentile).
        min_observations: minimum non-null salience values required before a
                        cap is computed. Default 20.

    Returns:
        dict {category: cap_value_or_None}. Categories with insufficient
        data map to None (uncapped).
    """
    cat_saliences = {}
    for cid, tiers in countries_data.items():
        for tier_name, cats in tiers.items():
            for c in cats:
                cat = c.get('category')
                if cat is None:
                    continue
                cat_saliences.setdefault(cat, []).append(c['salience_score'])

    caps = {}
    for cat, scores in cat_saliences.items():
        if len(scores) < min_observations:
            caps[cat] = None
            continue
        scores_sorted = sorted(scores)
        # Linear-interpolation-free percentile (good enough for clipping).
        idx = int(round(percentile * (len(scores_sorted) - 1)))
        caps[cat] = scores_sorted[idx]
    return caps


def apply_per_category_caps(countries_data, caps):
    """Clip each (country, tier, category) salience_score at its category cap.

    In-place mutation of countries_data. None caps are no-ops.

    Returns:
        int: total number of salience_score values that were clipped.
    """
    clipped = 0
    for cid, tiers in countries_data.items():
        for tier_name, cats in tiers.items():
            for c in cats:
                cat = c.get('category')
                cap = caps.get(cat)
                if cap is None:
                    continue
                if c['salience_score'] > cap:
                    c['salience_score'] = round(cap, 4)
                    clipped += 1
    return clipped


def risk_tier_label(category_scores, config=None):
    """V1.9.1 Fix C — 3-layer hybrid calibration (#377).

    Layer 1: REGULAR_HIGH (severity_weight < 1.0) at 2.0 (raised from 1.625)
    Layer 2: CRISIS_HIGH (severity_weight >= 1.0) at 1.4
    Layer 3: Composite promotion — >=2 categories at salience >= 1.3 AND at
             least one has severity_weight >= 0.8 -> HIGH regardless of L1/L2.

    Args:
        category_scores: list of {'salience_score', 'severity_tier'} dicts
                         across ALL tier-lengths (S/M/L/XL). Layer 3 needs the
                         full list, not just the top-1.
        config: scoring config dict (mirrors qgi-data/scoring/V1.9.1.json).
                Falls back to DEFAULT_SCORING_CONFIG if None.

    Prior versions:
      - V1.8.1 (2026-04-19): 1.625 regular / 1.4 crisis HIGH — still 68% HIGH
        on some runs (Cape Verde #376 face-validity failure).
      - V1.9.1 (2026-04-22): this function — expected HIGH share 15-23%.
    """
    if config is None:
        config = DEFAULT_SCORING_CONFIG
    thresholds = config['thresholds']
    composite = config.get('composite_rule', {})

    if not category_scores:
        return "INDICATIVE"

    # Layer 3: composite promotion (check first — overrides Layer 1/2).
    if composite.get('enabled'):
        floor = composite['min_salience_floor']
        min_n = composite['min_categories_above_salience']
        min_sev = composite['min_severity_for_at_least_one']
        above = [c for c in category_scores if c['salience_score'] >= floor]
        if len(above) >= min_n and any(c['severity_tier'] >= min_sev for c in above):
            return "HIGH"

    # Layer 1/2: stratified thresholds on top (max-salience) category.
    top = max(category_scores, key=lambda c: c['salience_score'])
    top_salience = top['salience_score']
    top_severity_weight = top['severity_tier']

    is_crisis = top_severity_weight >= 1.0
    high_cut = thresholds['CRISIS_HIGH'] if is_crisis else thresholds['REGULAR_HIGH']
    moderate_cut = (
        thresholds['CRISIS_MODERATE'] if is_crisis else thresholds['REGULAR_MODERATE']
    )

    if top_salience >= high_cut:
        return "HIGH"
    elif top_salience >= moderate_cut:
        return "MODERATE"
    else:
        return "INDICATIVE"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Generate country-risks.json')
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--region', default='eu-central-1')
    parser.add_argument('--output', default='country-risks.json')
    parser.add_argument('--upload', action='store_true', help='Upload to S3 dashboard/')
    args = parser.parse_args()

    # #422 Bug 3: refuse to score with empty severity weights. Without this
    # guard, every category falls through to severity_weight()'s default 0.3
    # and the Lambda silently produces a uniform-salience country-risks.json.
    if not SEVERITY_TIERS:
        raise RuntimeError(
            "category_severity_tiers.json could not be loaded; refusing to score "
            "with empty severity weights (see T17 #310)."
        )

    athena = boto3.client('athena', region_name=args.region)
    s3 = boto3.client('s3', region_name=args.region)

    # 1. Load country names
    print("Loading countries...")
    cn = {}
    alpha2 = {}
    for r in run_query(athena, 'SELECT id, name_1, alpha_2 FROM qgi_data.countries WHERE name_1 IS NOT NULL', args.bucket):
        try:
            cid = int(float(r['id']))
            cn[cid] = r['name_1']
            alpha2[cid] = r.get('alpha_2', '')
        except:
            pass
    print(f"  {len(cn)} countries")

    # 2. Load recency
    print("Loading recency...")
    recency = {}
    for r in run_query(athena,
            'SELECT country_id, category_normalized, max(year) as y '
            'FROM qgi_data.events WHERE category_normalized IS NOT NULL '
            'GROUP BY country_id, category_normalized', args.bucket):
        try:
            recency[(int(float(r['country_id'])), r['category_normalized'])] = int(r['y'])
        except:
            pass

    # 3. Load persistence
    print("Loading persistence...")
    persist = {}
    for r in run_query(athena,
            'SELECT country_id, category_normalized, count(*) as c '
            'FROM qgi_data.events WHERE year BETWEEN 2023 AND 2025 '
            'AND category_normalized IS NOT NULL '
            'GROUP BY country_id, category_normalized', args.bucket):
        try:
            persist[(int(float(r['country_id'])), r['category_normalized'])] = float(r['c']) / 3.0
        except:
            pass

    # 4. Per-tier scoring
    countries_data = {}  # cid -> tier -> [(cat, z_score, rrf_rank, recipe_count, last_event_year)]

    for tier_name, (lo, hi) in TIERS.items():
        print(f"\nProcessing tier {tier_name} ({lo}-{hi} years)...")

        # Partner eligible counts
        pe = {}
        for r in run_query(athena,
                f'SELECT country_a_id, count(DISTINCT country_b_id) as p '
                f'FROM qgi_data.scdis WHERE length BETWEEN {lo} AND {hi} '
                f'GROUP BY country_a_id', args.bucket):
            try:
                pe[r['country_a_id']] = int(r['p'])
            except:
                pass

        # Recipe aggregates
        # #458: read from recipes_deduped (bullet-6 longest-pattern collapse)
        # so count(*) reflects unique (pair, event_year) instead of nested-
        # length pattern instances of the same event. Mirrors the in-pipeline
        # change in country_risks.py:374-381.
        recipes = run_query(athena,
            f"SELECT country_a_id, event_category, count(*) as c, "
            f"avg(avg_correlation) as a, avg(indicator_count) as i "
            f"FROM qgi_data.recipes_deduped WHERE event_category IS NOT NULL "
            f"AND length BETWEEN {lo} AND {hi} "
            f"GROUP BY country_a_id, event_category", args.bucket)

        scored = {}
        recipe_counts = {}
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
                scored[(cid, r['event_category'])] = score
                recipe_counts[(cid, r['event_category'])] = int(float(r['c']))
            except:
                pass

        # Z-score + RRF
        zscored = zscore_per_country(scored)
        fused = rank_fusion(zscored, persist)
        ranked = sorted(fused.items(), key=lambda x: -x[1])

        # Build rank map
        rank_map = {key: i + 1 for i, (key, _) in enumerate(ranked)}

        # Populate per-country data
        for (cid, cat), rrf_score in fused.items():
            if cid not in countries_data:
                countries_data[cid] = {}
            if tier_name not in countries_data[cid]:
                countries_data[cid][tier_name] = []

            z = zscored.get((cid, cat), 0)
            dw = severity_weight(cat)
            # salience_score: z-score amplified by severity weight
            salience = round(z * dw, 4)

            countries_data[cid][tier_name].append({
                'category': cat,
                'z_score': round(z, 3),
                'salience_score': salience,
                'severity_tier': dw,
                'rrf_rank': rank_map.get((cid, cat), 9999),
                'rrf_score': round(rrf_score, 6),
                'recipe_count': recipe_counts.get((cid, cat), 0),
                'last_event_year': recency.get((cid, cat)),
            })

        print(f"  {tier_name}: {len(scored)} scored pairs, {len(fused)} after fusion")

    # 5. Build output JSON
    print("\nBuilding output JSON...")
    output = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'version': 'V1.9.1',
        'scoring': 'z-score per country + RRF ensemble with persistence',
        'tiers': {k: {'min_length': v[0], 'max_length': v[1]} for k, v in TIERS.items()},
        'curated_country_count': len(CURATED_IDS),
        'total_countries': 0,
        'countries': {},
    }

    scoring_config = load_scoring_config()

    # #201 Refinement 3: per-category salience cap (p95 across countries).
    # Applied BEFORE the country loop so the capped salience_scores feed
    # both the top_categories display and the risk_tier_label tier promotion.
    cap_pct = scoring_config.get('category_salience_cap_percentile', 0.95)
    cap_min_obs = scoring_config.get('category_salience_cap_min_observations', 20)
    if cap_pct and cap_pct < 1.0:
        caps = compute_per_category_caps(
            countries_data,
            percentile=cap_pct,
            min_observations=cap_min_obs,
        )
        clipped = apply_per_category_caps(countries_data, caps)
        capped_cats = [c for c, v in caps.items() if v is not None]
        print(
            f"\nPer-category cap (#201 R3): clipped {clipped} salience values "
            f"across {len(capped_cats)} categories at p{int(cap_pct * 100)} "
            f"({len(caps) - len(capped_cats)} categories left uncapped due to <{cap_min_obs} obs)"
        )

    # #201 Refinement 2: minimum recipe count gate for cross_tier_categories.
    # Thin categories (recipe_count < min_recipe_count) don't promote a
    # country to HIGH/MODERATE via the risk_tier_label decision, but they
    # still appear in the display top_categories so users see the raw data.
    min_recipe_count = scoring_config.get('min_recipe_count', 5)

    for cid, tiers in countries_data.items():
        # Sort each tier's categories by RRF score descending, keep top 10
        country_entry = {
            'name': cn.get(cid, f'#{cid}'),
            'alpha_2': alpha2.get(cid, ''),
            'curated': cid in CURATED_IDS,
            'tiers': {},
            'overall_risk_tier': 'INDICATIVE',
        }

        # V1.9.1 Fix C: pass the full cross-tier category list to
        # risk_tier_label so Layer 3 composite promotion can see all
        # categories, not just the top-1. Top-5 per tier mirrors the prior
        # scan; flat list is re-sorted desc for stable behavior.
        #
        # #201 Refinement 2 (2026-05-15): skip categories with recipe_count
        # below min_recipe_count from cross_tier_categories. Thin categories
        # still appear in the display top_categories — only the risk-tier
        # promotion decision filters them out. Prevents a 2-recipe outlier
        # in demographic_pressure from pushing a country to HIGH.
        cross_tier_categories = []
        for tier_name in TIERS:
            cats = tiers.get(tier_name, [])
            # Sort by salience_score (z_score × severity_weight) — surfaces interesting predictions
            cats.sort(key=lambda x: -x['salience_score'])
            country_entry['tiers'][tier_name] = {
                'top_categories': cats[:10],
            }
            for c in cats[:5]:
                if c.get('recipe_count', 0) < min_recipe_count:
                    continue
                cross_tier_categories.append({
                    'salience_score': c['salience_score'],
                    'severity_tier': c['severity_tier'],
                })
        cross_tier_categories.sort(key=lambda x: -x['salience_score'])
        country_entry['overall_risk_tier'] = risk_tier_label(
            cross_tier_categories, scoring_config
        )
        output['countries'][str(cid)] = country_entry

    output['total_countries'] = len(output['countries'])

    # 6. Write local file
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {args.output} ({os.path.getsize(args.output) / 1024:.0f} KB)")
    print(f"  {output['total_countries']} countries, {output['curated_country_count']} curated")

    # Count risk tiers
    tiers_count = Counter(c['overall_risk_tier'] for c in output['countries'].values())
    for tier, count in tiers_count.most_common():
        print(f"  {tier}: {count} countries")

    # 7. Upload to S3
    if args.upload:
        key = 'dashboard/country-risks.json'
        s3.put_object(
            Bucket=args.bucket,
            Key=key,
            Body=json.dumps(output, ensure_ascii=False),
            ContentType='application/json',
        )
        print(f"\nUploaded to s3://{args.bucket}/{key}")


if __name__ == '__main__':
    main()
