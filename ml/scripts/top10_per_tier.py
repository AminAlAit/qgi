#!/usr/bin/env python3
"""Generate V1.8.1 top-10 predictions per tier with z-score + rank fusion.

#422 Bug 5 (2026-04-24): the main body was previously at module scope,
which meant `import top10_per_tier` triggered Athena queries at import
time — making the module untestable offline. Wrapped in main() + guarded
by `if __name__ == '__main__':` so the pure functions `zscore_per_country`
and `rank_fusion` can be imported cleanly.
"""

import os
import time
import math
from collections import Counter, defaultdict

import boto3

W = 'QGI-Lambda-Workgroup'
TIERS = {'S': (3, 8), 'M': (9, 20), 'L': (21, 40), 'XL': (41, 999)}


def make_athena_client(region=None):
    return boto3.client(
        'athena',
        region_name=region or os.environ.get('AWS_DEFAULT_REGION', 'eu-central-1'),
    )


def rq(athena, sql, bucket):
    r = athena.start_query_execution(
        QueryString=sql, QueryExecutionContext={'Database': 'qgi_data'},
        WorkGroup=W, ResultConfiguration={'OutputLocation': f's3://{bucket}/query_results/'})
    q = r['QueryExecutionId']
    while True:
        time.sleep(2)
        s = athena.get_query_execution(QueryExecutionId=q)['QueryExecution']['Status']
        if s['State'] in ('SUCCEEDED', 'FAILED', 'CANCELLED'):
            break
    if s['State'] != 'SUCCEEDED':
        return []
    rows, res = [], athena.get_query_results(QueryExecutionId=q, MaxResults=1000)
    cols = [c['Name'] for c in res['ResultSet']['ResultSetMetadata']['ColumnInfo']]
    for row in res['ResultSet']['Rows'][1:]:
        rows.append({cols[i]: row['Data'][i].get('VarCharValue') for i in range(len(cols))})
    while 'NextToken' in res:
        res = athena.get_query_results(
            QueryExecutionId=q, NextToken=res['NextToken'], MaxResults=1000)
        for row in res['ResultSet']['Rows']:
            rows.append({cols[i]: row['Data'][i].get('VarCharValue') for i in range(len(cols))})
    return rows


def zscore_per_country(preds):
    bc = defaultdict(dict)
    for (c, cat), s in preds.items():
        bc[c][(c, cat)] = s
    r = {}
    for c, cp in bc.items():
        v = list(cp.values())
        if len(v) < 2:
            r.update(cp)
            continue
        m = sum(v) / len(v)
        sd = max((sum((x - m) ** 2 for x in v) / len(v)) ** 0.5, 1e-6)
        for k, s in cp.items():
            r[k] = (s - m) / sd
    return r


def rank_fusion(rp, pp, k=60):
    rr = {key: i + 1 for i, (key, _) in enumerate(sorted(rp.items(), key=lambda x: -x[1]))}
    pr = {key: i + 1 for i, (key, _) in enumerate(sorted(pp.items(), key=lambda x: -x[1]))}
    ak = set(rp) | set(pp)
    mx = len(ak) + 1
    return {key: 1 / (k + rr.get(key, mx)) + 1 / (k + pr.get(key, mx)) for key in ak}


def main():
    athena = make_athena_client()
    bucket = os.environ.get('S3_BUCKET', 'qgi-data-lake-771606957899')

    print("Loading country names...")
    cn = {}
    for r in rq(athena, 'SELECT id, name_1 FROM qgi_data.countries WHERE name_1 IS NOT NULL', bucket):
        try:
            cn[int(float(r['id']))] = r['name_1']
        except Exception:
            pass

    print("Loading recency...")
    rm = {}
    for r in rq(athena,
                'SELECT country_id, category_normalized, max(year) as y '
                'FROM qgi_data.events WHERE category_normalized IS NOT NULL '
                'GROUP BY country_id, category_normalized', bucket):
        try:
            rm[(int(float(r['country_id'])), r['category_normalized'])] = int(r['y'])
        except Exception:
            pass

    print("Loading persistence...")
    persist = {}
    for r in rq(athena,
                'SELECT country_id, category_normalized, count(*) as c '
                'FROM qgi_data.events WHERE year BETWEEN 2023 AND 2025 '
                'AND category_normalized IS NOT NULL '
                'GROUP BY country_id, category_normalized', bucket):
        try:
            persist[(int(float(r['country_id'])), r['category_normalized'])] = float(r['c']) / 3.0
        except Exception:
            pass

    print("Loading per-country partner eligible counts...")
    pe_all = {}
    for tn, (lo, hi) in TIERS.items():
        pe = {}
        for r in rq(athena,
                    f'SELECT country_a_id, count(DISTINCT country_b_id) as p '
                    f'FROM qgi_data.scdis WHERE length BETWEEN {lo} AND {hi} '
                    f'GROUP BY country_a_id', bucket):
            try:
                pe[r['country_a_id']] = int(r['p'])
            except Exception:
                pass
        pe_all[tn] = pe

    for tn, (lo, hi) in TIERS.items():
        pe = pe_all[tn]
        print(f"\nLoading recipes for tier {tn}...")
        recipes = rq(athena,
                     f"SELECT country_a_id, event_category, count(*) as c, "
                     f"avg(avg_correlation) as a, avg(indicator_count) as i "
                     f"FROM qgi_data.recipes WHERE event_category IS NOT NULL "
                     f"AND length BETWEEN {lo} AND {hi} "
                     f"GROUP BY country_a_id, event_category", bucket)

        scored = {}
        for r in recipes:
            try:
                cid = int(float(r['country_a_id']))
                p = pe.get(r['country_a_id'], pe.get(str(cid), 5))
                if isinstance(p, str):
                    p = int(p)
                prev = float(r['c']) / max(p, 5)
                s = (0.30 * math.log(prev + 0.01)
                     + 0.40 * float(r['a'])
                     + 0.15 * math.log(float(r['i']) + 1)
                     + 0.15)
                ly = rm.get((cid, r['event_category']))
                if ly:
                    s += 0.15 * (0.85 ** max(2025 - ly, 0))
                scored[(cid, r['event_category'])] = s
            except Exception:
                pass

        fused = rank_fusion(zscore_per_country(scored), persist)
        ranked = sorted(fused.items(), key=lambda x: -x[1])

        print(f"\n{'=' * 95}")
        print(f"V1.8.1 TOP 10 -- TIER {tn} (length {lo}-{hi} years)")
        print(f"{'=' * 95}")
        print(f"{'#':<4} {'Country':<24} {'Event Category':<40} {'RRF':>8}")
        print(f"{'-' * 95}")
        for i, ((cid, cat), sc) in enumerate(ranked[:10], 1):
            print(f"{i:<4} {cn.get(cid, str(cid)):<24} {cat:<40} {sc:.6f}")

        cats = Counter(cat for (_, cat), _ in ranked[:50])
        cntrs = Counter(cn.get(c, str(c)) for (c, _), _ in ranked[:50])
        print(f"\n  Top-50: {len(cats)} categories, {len(cntrs)} countries")
        print(f"  Categories: {', '.join(f'{c}:{n}' for c, n in cats.most_common(10))}")
        print(f"  Countries: {', '.join(f'{c}:{n}' for c, n in cntrs.most_common(10))}")


if __name__ == '__main__':
    main()
