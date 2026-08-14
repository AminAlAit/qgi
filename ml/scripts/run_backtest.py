#!/usr/bin/env python3
"""
QGI Backtesting Script V1.8 — Per-tier walk-forward validation.

Changes from V1.5.2:
- Per-tier (S/M/L/XL) Platt scaling and thresholds
- Per-tier metrics + weighted aggregate
- XL fallback to M-tier Platt params when <500 positive pairs
- Configurable S3 bucket + workgroup via CLI args (no hardcoding)
- Output: JSON results + console tables

Usage:
    # Full backtest (validate on 2015, test on 2020):
    python run_backtest.py --bucket qgi-data-lake-771606957899 --mode full

    # With explicit region + workgroup:
    python run_backtest.py --bucket qgi-data-lake-771606957899 --region eu-central-1 --workgroup QGI-Lambda-Workgroup --mode full

    # Validate only (tune thresholds):
    python run_backtest.py --bucket qgi-data-lake-771606957899 --mode validate --cutoff 2015

    # Test only (locked threshold per tier):
    python run_backtest.py --bucket qgi-data-lake-771606957899 --mode test --cutoff 2020
"""

import argparse
import time
import json
import sys
import math
import os
from collections import defaultdict

import boto3
import numpy as np

# ---------------------------------------------------------------------------
# Tier definitions (#128)
# ---------------------------------------------------------------------------
TIERS = {
    'S':  (3, 8),
    'M':  (9, 20),
    'L':  (21, 40),
    'XL': (41, 999),
}

XL_FALLBACK_MIN_POSITIVES = 500  # If XL has fewer, use M-tier Platt params

# ---------------------------------------------------------------------------
# Curated country IDs (55 countries with verified event histories)
# ---------------------------------------------------------------------------
CURATED_COUNTRY_IDS = [
    # Original 35
    1, 3, 10, 18, 31, 45, 63, 66, 69, 100, 101, 102, 103, 106, 112,
    117, 121, 124, 140, 147, 159, 167, 174, 182, 195, 206, 212, 217,
    227, 228, 233, 234, 242, 243, 248,
    # Batch 1 (2026-04-11): Colombia, Kenya, Myanmar, North Korea, Somalia
    48, 114, 149, 162, 205,
    # Batch 2 (2026-04-11): Cuba, Ecuador, Germany, Ghana, Kazakhstan,
    # Malaysia, Poland, South Korea, Thailand, United Kingdom
    54, 62, 81, 82, 113, 131, 176, 208, 221, 235,
    # Batch 3 (2026-04-11): Angola, Bosnia, Chile, France, Italy
    6, 28, 44, 74, 107,
]


# ---------------------------------------------------------------------------
# Athena helpers
# ---------------------------------------------------------------------------

def get_athena(args):
    """Build Athena client, optionally assuming a cross-account role."""
    if args.role_arn:
        sts = boto3.client('sts', region_name=args.region)
        creds = sts.assume_role(
            RoleArn=args.role_arn, RoleSessionName='backtest'
        )['Credentials']
        return boto3.client(
            'athena', region_name=args.region,
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
        )
    return boto3.client('athena', region_name=args.region)


def run_query(athena, sql, bucket, workgroup, max_results=1000):
    """Execute Athena query synchronously. Returns list of row dicts."""
    r = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={'Database': 'qgi_data'},
        WorkGroup=workgroup,
        ResultConfiguration={
            'OutputLocation': f's3://{bucket}/query_results/',
        },
    )
    qid = r['QueryExecutionId']
    while True:
        time.sleep(2)
        s = athena.get_query_execution(
            QueryExecutionId=qid
        )['QueryExecution']['Status']
        if s['State'] in ('SUCCEEDED', 'FAILED', 'CANCELLED'):
            break
    if s['State'] != 'SUCCEEDED':
        print(
            f"FAILED: {s.get('StateChangeReason', '?')[:200]}",
            file=sys.stderr,
        )
        return []

    rows = []
    result = athena.get_query_results(
        QueryExecutionId=qid, MaxResults=max_results
    )
    cols = [
        c['Name']
        for c in result['ResultSet']['ResultSetMetadata']['ColumnInfo']
    ]
    for row in result['ResultSet']['Rows'][1:]:
        d = {
            cols[i]: row['Data'][i].get('VarCharValue')
            for i in range(len(cols))
        }
        rows.append(d)
    while 'NextToken' in result:
        result = athena.get_query_results(
            QueryExecutionId=qid,
            NextToken=result['NextToken'],
            MaxResults=max_results,
        )
        for row in result['ResultSet']['Rows']:
            d = {
                cols[i]: row['Data'][i].get('VarCharValue')
                for i in range(len(cols))
            }
            rows.append(d)
    return rows


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def log_score(count, correlation, indicator_count, eligible_countries=None):
    """V1.6 scoring with prevalence rate (#183).

    If eligible_countries is provided, uses prevalence rate instead of raw count.
    Falls back to V1.5.3 log-count scoring if not provided.
    """
    if eligible_countries and float(eligible_countries) > 0:
        prevalence = float(count) / max(float(eligible_countries), 5.0)
        return (
            0.30 * math.log(prevalence + 0.01)
            + 0.40 * float(correlation)
            + 0.15 * math.log(float(indicator_count) + 1)
            + 0.15  # category specificity bonus (placeholder — 1.0 for all v2 categories)
        )
    return (
        0.4 * math.log(float(count) + 1)
        + 0.4 * float(correlation)
        + 0.2 * math.log(float(indicator_count) + 1)
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(y_true, y_scores, threshold):
    """Compute full metrics suite at a given threshold."""
    y_pred = (y_scores >= threshold).astype(int)
    tp = ((y_pred == 1) & (y_true == 1)).sum()
    fp = ((y_pred == 1) & (y_true == 0)).sum()
    fn = ((y_pred == 0) & (y_true == 1)).sum()

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0
    )
    base_rate = y_true.mean() if len(y_true) > 0 else 0
    lift = precision / base_rate if base_rate > 0 and precision > 0 else 0

    # Brier Score
    brier = ((y_scores - y_true) ** 2).mean()
    brier_ref = ((base_rate - y_true) ** 2).mean()
    bss = 1 - (brier / brier_ref) if brier_ref > 0 else 0

    # AUPRC
    sorted_idx = np.argsort(-y_scores)
    y_sorted = y_true[sorted_idx]
    tp_cum = 0
    auprc = 0.0
    prev_recall = 0.0
    for i in range(len(y_sorted)):
        if y_sorted[i] == 1:
            tp_cum += 1
        p = tp_cum / (i + 1)
        r = tp_cum / max(y_true.sum(), 1)
        auprc += (r - prev_recall) * p
        prev_recall = r

    # Precision@K and Lift@K
    def precision_at_k(k):
        if len(sorted_idx) < k:
            k = len(sorted_idx)
        return y_true[sorted_idx[:k]].sum() / k if k > 0 else 0

    def lift_at_k(k):
        pak = precision_at_k(k)
        return pak / base_rate if base_rate > 0 else 0

    # F2 score (beta=2, weights recall 2x — standard for risk products)
    f2 = (
        5 * precision * recall / (4 * precision + recall)
        if (4 * precision + recall) > 0
        else 0
    )

    # NDCG@K (Normalized Discounted Cumulative Gain)
    def ndcg_at_k(k):
        top_k = sorted_idx[:min(k, len(sorted_idx))]
        dcg = sum(
            float(y_true[top_k[i]]) / math.log2(i + 2)
            for i in range(len(top_k))
        )
        ideal = np.sort(y_true)[::-1][:min(k, len(y_true))]
        idcg = sum(
            float(ideal[i]) / math.log2(i + 2)
            for i in range(len(ideal))
        )
        return dcg / idcg if idcg > 0 else 0

    return {
        'f1': round(f1, 4),
        'f2': round(f2, 4),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'auprc': round(auprc, 4),
        'ndcg_at_20': round(ndcg_at_k(20), 4),
        'ndcg_at_50': round(ndcg_at_k(50), 4),
        'lift': round(lift, 2),
        'brier_skill_score': round(bss, 4),
        'precision_at_10': round(precision_at_k(10), 4),
        'precision_at_50': round(precision_at_k(50), 4),
        'precision_at_100': round(precision_at_k(100), 4),
        'lift_at_10': round(lift_at_k(10), 2),
        'lift_at_50': round(lift_at_k(50), 2),
        'lift_at_100': round(lift_at_k(100), 2),
        'lift_at_200': round(lift_at_k(200), 2),
        'coverage': round((y_scores > 0).mean(), 4),
        'base_rate': round(base_rate, 4),
        'n_predictions': int((y_pred == 1).sum()),
        'n_ground_truth': int(y_true.sum()),
        'n_total': len(y_true),
    }


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_ground_truth(athena, cutoff, bucket, workgroup, country_ids=None):
    """Load actual events after cutoff, optionally filtered by country IDs."""
    country_filter = ''
    if country_ids:
        ids_str = ','.join(str(c) for c in country_ids)
        country_filter = f' AND country_id IN ({ids_str})'
    rows = run_query(
        athena,
        f"""
        SELECT country_id, category_normalized
        FROM qgi_data.events
        WHERE year > {cutoff}{country_filter}
        GROUP BY country_id, category_normalized
        """,
        bucket, workgroup,
    )
    return {(r['country_id'], r['category_normalized']) for r in rows}


def load_recipe_predictions_by_tier(athena, table, cutoff, bucket, workgroup, country_ids=None):
    """Load aggregated recipe predictions, stratified by tier (#130).

    Returns: dict[tier_name] -> dict[(country_a_id, event_category)] -> score
    """
    preds_by_tier = {t: {} for t in TIERS}
    country_filter = ''
    if country_ids:
        ids_str = ','.join(str(c) for c in country_ids)
        country_filter = f' AND country_a_id IN ({ids_str})'

    for tier_name, (lo, hi) in TIERS.items():
        # V1.7 P2: per-country partner-eligible count for prevalence rate
        partner_rows = run_query(
            athena,
            f"""
            SELECT country_a_id, count(DISTINCT country_b_id) as partners
            FROM qgi_data.scdis
            WHERE length BETWEEN {lo} AND {hi}
            GROUP BY country_a_id
            """,
            bucket, workgroup,
        )
        partner_eligible = {
            r['country_a_id']: int(r['partners'])
            for r in partner_rows
        }

        rows = run_query(
            athena,
            f"""
            SELECT country_a_id, event_category,
                   count(*) as recipe_count,
                   avg(avg_correlation) as avg_corr,
                   avg(indicator_count) as avg_ind
            FROM qgi_data.{table}
            WHERE end_year_a <= {cutoff} AND end_year_b <= {cutoff}
              AND length BETWEEN {lo} AND {hi}{country_filter}
            GROUP BY country_a_id, event_category
            """,
            bucket, workgroup,
        )

        tier_preds = {}
        for r in rows:
            # V1.7: per-country denominator instead of global
            country_partners = partner_eligible.get(r['country_a_id'], 5)
            score = log_score(
                r['recipe_count'], r['avg_corr'], r['avg_ind'],
                eligible_countries=country_partners,
            )
            tier_preds[(r['country_a_id'], r['event_category'])] = score

        # P2: NO per-tier normalization — feed raw scores through
        # (was: normalize to 0-1, which compressed Platt output)

        preds_by_tier[tier_name] = tier_preds
        print(f"  {tier_name} (length {lo}-{hi}): {len(tier_preds)} predictions, {len(partner_eligible)} countries with partners")

    return preds_by_tier


def load_persistence(athena, cutoff, bucket, workgroup, country_ids=None):
    """Persistence baseline: events in [cutoff-2, cutoff] predict cutoff+1."""
    country_filter = ''
    if country_ids:
        ids_str = ','.join(str(c) for c in country_ids)
        country_filter = f' AND country_id IN ({ids_str})'
    rows = run_query(
        athena,
        f"""
        SELECT country_id, category_normalized, count(*) as cnt
        FROM qgi_data.events
        WHERE year BETWEEN {cutoff - 2} AND {cutoff}{country_filter}
        GROUP BY country_id, category_normalized
        """,
        bucket, workgroup,
    )
    return {
        (r['country_id'], r['category_normalized']): float(r['cnt']) / 3.0
        for r in rows
    }


def load_recency(athena, cutoff, bucket, workgroup, country_ids=None):
    """Load most recent event year per (country, category) before cutoff."""
    country_filter = ''
    if country_ids:
        ids_str = ','.join(str(c) for c in country_ids)
        country_filter = f' AND country_id IN ({ids_str})'
    rows = run_query(
        athena,
        f"""
        SELECT country_id, category_normalized, max(year) as last_year
        FROM qgi_data.events
        WHERE year <= {cutoff}{country_filter}
        GROUP BY country_id, category_normalized
        """,
        bucket, workgroup,
    )
    return {
        (r['country_id'], r['category_normalized']): int(r['last_year'])
        for r in rows
    }


def apply_recency(preds, recency, cutoff, decay=0.85, weight=0.15):
    """Boost predictions by recency: recent events = higher score.

    V1.6: weight halved from 0.30 to 0.15 (#184 P3).
    """
    boosted = {}
    for key, score in preds.items():
        last_year = recency.get(key)
        if last_year is not None:
            years_ago = cutoff - last_year
            boost = decay ** years_ago
            boosted[key] = score + weight * boost
        else:
            boosted[key] = score
    return boosted


def renormalize(preds):
    """Re-normalize scores to 0-1 after recency boost."""
    if not preds:
        return preds
    vals = list(preds.values())
    mn, mx = min(vals), max(vals)
    rng = mx - mn if mx > mn else 1
    return {k: (v - mn) / rng for k, v in preds.items()}


def zscore_per_country(preds):
    """V1.8: Within-country z-score normalization.

    For each country, center its category scores around the country's mean
    and scale by country's std. This removes data-volume bias by asking
    "which category is anomalously elevated for THIS country?" instead of
    "which country has the most recipes globally?"
    """
    if not preds:
        return preds

    # Group scores by country
    by_country = defaultdict(dict)
    for (cid, cat), score in preds.items():
        by_country[cid][(cid, cat)] = score

    result = {}
    for cid, country_preds in by_country.items():
        vals = list(country_preds.values())
        if len(vals) < 2:
            # Single category for this country — can't z-score, keep raw
            result.update(country_preds)
            continue
        mean = sum(vals) / len(vals)
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        std = max(std, 1e-6)  # prevent division by zero
        for key, score in country_preds.items():
            result[key] = (score - mean) / std

    return result


def rank_fusion_ensemble(recipe_preds, persistence_preds, k=60):
    """V1.8: Reciprocal Rank Fusion of recipe + persistence signals.

    Combines two complementary signals:
    - Recipes: structural economic pattern match (what COULD happen)
    - Persistence: recent event history (what IS happening)

    RRF is robust to score scale mismatches — uses ranks only.
    """
    # Compute ranks for each signal
    recipe_ranked = sorted(recipe_preds.items(), key=lambda x: -x[1])
    recipe_rank = {key: i + 1 for i, (key, _) in enumerate(recipe_ranked)}

    persist_ranked = sorted(persistence_preds.items(), key=lambda x: -x[1])
    persist_rank = {key: i + 1 for i, (key, _) in enumerate(persist_ranked)}

    # All keys from both signals
    all_keys = set(recipe_preds.keys()) | set(persistence_preds.keys())
    max_rank = len(all_keys) + 1  # default rank for missing keys

    # RRF score
    fused = {}
    for key in all_keys:
        r_rank = recipe_rank.get(key, max_rank)
        p_rank = persist_rank.get(key, max_rank)
        fused[key] = 1.0 / (k + r_rank) + 1.0 / (k + p_rank)

    return fused


# ---------------------------------------------------------------------------
# Platt scaling + threshold search
# ---------------------------------------------------------------------------

def platt_scale(y_true_train, y_scores_train, y_scores_apply):
    """Fit Platt scaling on train, apply to given scores."""
    best_loss = float('inf')
    best_a, best_b = 1.0, 0.0

    for a in np.arange(0.5, 20, 0.5):
        for b in np.arange(-10, 5, 0.5):
            probs = 1.0 / (1.0 + np.exp(-(a * y_scores_train + b)))
            probs = np.clip(probs, 1e-7, 1 - 1e-7)
            loss = -np.mean(
                y_true_train * np.log(probs)
                + (1 - y_true_train) * np.log(1 - probs)
            )
            if loss < best_loss:
                best_loss = loss
                best_a, best_b = a, b

    calibrated = 1.0 / (1.0 + np.exp(-(best_a * y_scores_apply + best_b)))
    return calibrated, best_a, best_b


def find_threshold_at_precision(y_true, y_scores, target_precision=0.50):
    """V1.7: Find threshold optimizing F2 (recall-weighted) at >= target precision.

    Changes from V1.6:
    - Precision target lowered from 70% to 50% (#184 P3)
    - Optimizes F2 (beta=2) instead of F1 — appropriate for risk products
    - Dynamically adapts search range to actual score distribution
    """
    # Adapt search range to actual score distribution
    score_min = float(np.percentile(y_scores[y_scores > 0], 10)) if (y_scores > 0).any() else 0.3
    score_max = float(np.percentile(y_scores, 95))
    floor = max(score_min, 0.10)

    best_threshold = round((floor + score_max) / 2, 2)
    best_f2 = 0
    precision_met = False

    for t in np.arange(floor, min(score_max + 0.05, 0.99), 0.005):
        m = compute_metrics(y_true, y_scores, t)
        if m['n_predictions'] == 0:
            continue
        f2 = m['f2']
        if m['precision'] >= target_precision and not precision_met:
            best_threshold = t
            precision_met = True
        if precision_met and m['precision'] >= target_precision and f2 > best_f2:
            best_f2 = f2
            best_threshold = t
        if not precision_met and f2 > best_f2:
            best_f2 = f2
            best_threshold = t

    return round(best_threshold, 3), round(best_f2, 4), precision_met


def build_arrays(preds, ground_truth):
    """Convert prediction dict + ground truth set into aligned numpy arrays."""
    all_pairs = sorted(set(preds.keys()) | ground_truth)
    y_true = np.array([1 if p in ground_truth else 0 for p in all_pairs])
    y_scores = np.array([preds.get(p, 0.0) for p in all_pairs])
    return y_true, y_scores


def build_arrays_with_pairs(preds, ground_truth):
    """Like build_arrays but also returns the ordered (country_id, category)
    pair list so callers can compute stratified metrics (#400 per-category,
    #401 per-country)."""
    all_pairs = sorted(set(preds.keys()) | ground_truth)
    y_true = np.array([1 if p in ground_truth else 0 for p in all_pairs])
    y_scores = np.array([preds.get(p, 0.0) for p in all_pairs])
    return y_true, y_scores, all_pairs


def stratified_metrics(pairs, y_true, y_pred, group_fn, min_samples=5):
    """Compute per-group F1/precision/recall for any grouping function (#400, #401).

    Takes pre-thresholded `y_pred` (binary 0/1) rather than scores + threshold,
    so callers that apply per-tier thresholds (the V1.8 backtest does) can
    accumulate across tiers and still get correct per-group F1.

    Args:
        pairs:     list of (country_id, category) tuples, aligned with y_true/y_pred
        y_true:    array-like of 0/1 ground truth labels
        y_pred:    array-like of 0/1 predictions (already thresholded)
        group_fn:  callable pair → group key (e.g. lambda p: p[0] for country,
                   lambda p: p[1] for category)
        min_samples: groups with fewer total samples than this are dropped from
                   the output (avoids one-event categories producing noise)

    Returns: dict[group_key] → {f1, precision, recall, n_gt, n_total}.
    """
    buckets = defaultdict(lambda: {'y_true': [], 'y_pred': []})
    for pair, t, p in zip(pairs, y_true, y_pred):
        key = group_fn(pair)
        buckets[key]['y_true'].append(int(t))
        buckets[key]['y_pred'].append(int(p))

    result = {}
    for key, data in buckets.items():
        n = len(data['y_true'])
        if n < min_samples:
            continue
        yt = np.array(data['y_true'])
        yp = np.array(data['y_pred'])
        tp = int(((yp == 1) & (yt == 1)).sum())
        fp = int(((yp == 1) & (yt == 0)).sum())
        fn = int(((yp == 0) & (yt == 1)).sum())
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0 else 0.0
        )
        result[key] = {
            'f1': round(f1, 4),
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'n_gt': int(yt.sum()),
            'n_total': n,
        }
    return result


def load_country_id_to_region(athena, bucket, workgroup, regions_yaml_path=None):
    """Build a {country_id (int) → region (str)} map for #396 per-region F1.

    Steps:
      1. Query `qgi_data.countries` for (id, alpha_2).
      2. Load `qgi-data/registries/country_regions.yaml` (YAML structured as
         REGION: [alpha_2, alpha_2, ...]).
      3. Invert to alpha_2 → REGION and compose with step 1.

    Returns an empty dict on any failure so callers can no-op the per-region
    output block (keeping the backtest runnable without the YAML).
    """
    from pathlib import Path

    # Locate the YAML: explicit arg → env var → default qgi-data path.
    candidates = []
    if regions_yaml_path:
        candidates.append(Path(regions_yaml_path))
    env_path = os.environ.get("QGI_COUNTRY_REGIONS_PATH")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(
        Path(__file__).resolve().parent.parent.parent
        / "qgi-data" / "registries" / "country_regions.yaml"
    )

    yaml_path = next((p for p in candidates if p.exists()), None)
    if yaml_path is None:
        print("  [per-region] country_regions.yaml not found; skipping", file=sys.stderr)
        return {}

    # Simple YAML parse — file shape is `REGION:\n  - XX\n  - YY\n`. Avoids
    # adding a PyYAML dependency (same pattern as the finalize Lambda).
    alpha2_to_region: dict[str, str] = {}
    current_region = None
    with open(yaml_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            if not line.startswith(" ") and line.endswith(":"):
                key = line[:-1].strip()
                # Region codes are 3-letter uppercase (AFR, MEA, EUR, ASI, AMR, OCE).
                if len(key) == 3 and key.isupper():
                    current_region = key
                else:
                    current_region = None  # skip "version:" etc.
            elif line.lstrip().startswith("- ") and current_region:
                code = line.lstrip()[2:].strip()
                if code:
                    alpha2_to_region[code.upper()] = current_region

    if not alpha2_to_region:
        return {}

    # Pull id → alpha_2 from the countries Glue table.
    rows = run_query(
        athena,
        "SELECT id, alpha_2 FROM qgi_data.countries WHERE alpha_2 IS NOT NULL",
        bucket, workgroup,
    )
    id_to_region: dict[int, str] = {}
    for r in rows:
        try:
            cid = int(float(r["id"]))
        except (ValueError, TypeError):
            continue
        alpha2 = (r.get("alpha_2") or "").upper()
        region = alpha2_to_region.get(alpha2)
        if region:
            id_to_region[cid] = region
    return id_to_region


def summarize_per_country_distribution(per_country_metrics, top_k=5):
    """Build the p10/p25/p50/p75/p90 + worst/best summary for #401.

    Args:
        per_country_metrics: dict[country_id] → {f1, precision, recall, n_gt, n_total}
                             as returned by stratified_metrics() grouped by country.
        top_k: number of worst/best countries to surface by F1.

    Returns: dict with distribution stats + worst_k/best_k lists, or None if
             the input is empty.
    """
    if not per_country_metrics:
        return None

    # Sort ascending by F1 so worst is first, best is last.
    ordered = sorted(per_country_metrics.items(), key=lambda kv: kv[1]['f1'])
    f1s = [m['f1'] for _, m in ordered]
    n = len(f1s)

    def pct(p):
        k = max(0, min(n - 1, int(round(p * (n - 1)))))
        return f1s[k]

    return {
        'n_countries': n,
        'distribution': {
            'p10': pct(0.10),
            'p25': pct(0.25),
            'median': pct(0.50),
            'p75': pct(0.75),
            'p90': pct(0.90),
        },
        'worst_k': [{'country_id': cid, **m} for cid, m in ordered[:top_k]],
        'best_k': [{'country_id': cid, **m} for cid, m in ordered[-top_k:][::-1]],
    }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_table(header, rows):
    widths = [
        max(len(str(r[i])) for r in [header] + rows) + 2
        for i in range(len(header))
    ]
    fmt = "".join(f"{{:<{w}s}}" for w in widths)
    print(fmt.format(*[str(h) for h in header]))
    print("-" * sum(widths))
    for row in rows:
        print(fmt.format(*[str(v) for v in row]))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='QGI Backtesting V1.5.3')
    parser.add_argument('--bucket', required=True, help='S3 data lake bucket')
    parser.add_argument('--region', default='eu-central-1')
    parser.add_argument('--workgroup', default='QGI-Lambda-Workgroup')
    parser.add_argument('--role-arn', default=None, help='Cross-account role ARN (optional)')
    parser.add_argument('--cutoff', type=int, default=2020)
    parser.add_argument('--mode', choices=['validate', 'test', 'full'], default='full')
    parser.add_argument('--threshold', type=float, default=None)
    parser.add_argument('--recipe-table', default='recipes')
    parser.add_argument('--target-precision', type=float, default=0.50, help='Min precision for threshold (V1.7: 50%%)')
    parser.add_argument('--curated-only', action='store_true', help='Filter to 35 curated countries only')
    parser.add_argument('--output', default='backtest_v18_results.json')
    # #463 Part C completion: export per-pair predictions as JSONL so the
    # V2.0-vs-V1.9.1 eval (qgi-ml/scripts/eval_v2_vs_v19.py) has a fixture
    # to score V2.0 against without re-running the full backtest. One JSON
    # per line: {country_a_id, event_category, tier, system, y_cal, y_true,
    # cutoff_year}. systems: "v1.9.1" (per-tier rows), "persistence".
    parser.add_argument('--dump-pairs-jsonl', default=None,
                        help='Path to write per-pair predictions JSONL (#463 Part C eval fixture)')
    parser.add_argument('--dump-raw-scores', action='store_true',
                        help='Also write per-tier (prob, label) pairs to '
                             '{basename}_raw.json for diagnostic post-hoc '
                             'analysis (e.g. full PR curves, calibration plots).')
    args = parser.parse_args()

    # V1.9.2 Fix D enabler: capture raw (calibrated prob, label) per tier/phase
    # when --dump-raw-scores is set. Populated inside the val+test loops below.
    raw_scores = {t: {'validation': None, 'test': None} for t in TIERS}

    athena = get_athena(args)

    # Resolve country filter
    country_ids = CURATED_COUNTRY_IDS if args.curated_only else None
    if country_ids:
        print(f"CURATED-ONLY MODE: filtering to {len(country_ids)} countries")

    if args.mode in ('full', 'validate'):
        # =================================================================
        # PHASE 1: VALIDATION (cutoff=2015) — fit per-tier Platt + thresholds
        # =================================================================
        print("=" * 70)
        print("PHASE 1: VALIDATION (cutoff=2015) — PER-TIER (#130)")
        print("=" * 70)

        gt_val = load_ground_truth(athena, 2015, args.bucket, args.workgroup, country_ids)
        print(f"Ground truth: {len(gt_val)} (country, category) pairs post-2015")

        print("\nLoading per-tier predictions...")
        preds_by_tier_val = load_recipe_predictions_by_tier(
            athena, args.recipe_table, 2015, args.bucket, args.workgroup, country_ids,
        )
        recency_val = load_recency(athena, 2015, args.bucket, args.workgroup, country_ids)

        # Per-tier: apply recency, Platt scale, find threshold
        platt_params = {}
        tier_thresholds = {}
        tier_metrics_val = {}

        for tier_name in TIERS:
            preds = preds_by_tier_val[tier_name]
            if not preds:
                print(f"\n  {tier_name}: no predictions — skipping")
                tier_metrics_val[tier_name] = None
                continue

            # V1.8: recency → z-score per country → Platt
            preds_boosted = apply_recency(preds, recency_val, 2015)
            preds_boosted = zscore_per_country(preds_boosted)
            y_true, y_scores = build_arrays(preds_boosted, gt_val)
            n_positives = int(y_true.sum())

            # Platt scaling
            if tier_name == 'XL' and n_positives < XL_FALLBACK_MIN_POSITIVES:
                if 'M' in platt_params:
                    a, b = platt_params['M']
                    print(f"\n  {tier_name}: <{XL_FALLBACK_MIN_POSITIVES} positives ({n_positives}), using M-tier Platt params (a={a:.2f}, b={b:.2f})")
                    y_cal = 1.0 / (1.0 + np.exp(-(a * y_scores + b)))
                    platt_params[tier_name] = (a, b)
                else:
                    y_cal, a, b = platt_scale(y_true, y_scores, y_scores)
                    platt_params[tier_name] = (a, b)
            else:
                y_cal, a, b = platt_scale(y_true, y_scores, y_scores)
                platt_params[tier_name] = (a, b)

            # Threshold at target precision (#119)
            threshold, f1, precision_met = find_threshold_at_precision(
                y_true, y_cal, args.target_precision,
            )
            tier_thresholds[tier_name] = threshold

            m = compute_metrics(y_true, y_cal, threshold)
            tier_metrics_val[tier_name] = m

            if args.dump_raw_scores:
                raw_scores[tier_name]['validation'] = [
                    [float(p), int(l)] for p, l in zip(y_cal, y_true)
                ]

            status = "OK" if precision_met else "WARN precision not met"
            base_rate = n_positives / m['n_total'] if m['n_total'] > 0 else 0
            print(
                f"\n  {tier_name}: Platt a={a:.2f} b={b:.2f} | "
                f"cal_range=[{y_cal.min():.3f}, {y_cal.max():.3f}] | "
                f"threshold={threshold} | F1={m['f1']} | "
                f"Precision={m['precision']} | Recall={m['recall']} | AUPRC={m['auprc']} | "
                f"n={m['n_total']} ({n_positives} pos, base_rate={base_rate:.1%}) | {status}"
            )

        # Aggregate
        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY (per-tier)")
        print("=" * 70)
        header = ['Tier', 'F1', 'F2', 'Precision', 'Recall', 'AUPRC', 'NDCG@20', 'Threshold', 'N_pred', 'N_gt']
        rows = []
        total_preds = 0
        weighted_f1 = 0
        for tier_name in TIERS:
            m = tier_metrics_val.get(tier_name)
            if m is None:
                rows.append([tier_name, '-', '-', '-', '-', '-', '-', '-', 0, 0])
                continue
            rows.append([
                tier_name, m['f1'], m['f2'], m['precision'], m['recall'], m['auprc'],
                m['ndcg_at_20'], tier_thresholds.get(tier_name, '-'),
                m['n_predictions'], m['n_ground_truth'],
            ])
            total_preds += m['n_total']
            weighted_f1 += m['f1'] * m['n_total']

        agg_f1 = round(weighted_f1 / total_preds, 4) if total_preds > 0 else 0
        rows.append(['AGG', agg_f1, '', '', '', '', '', '', total_preds, ''])
        print_table(header, rows)

    if args.mode in ('full', 'test'):
        # =================================================================
        # PHASE 2: TEST (cutoff=2020) — locked Platt params + thresholds
        # =================================================================
        print()
        print("=" * 70)
        print("PHASE 2: TEST (cutoff=2020) — LOCKED PARAMS")
        print("=" * 70)

        if args.mode == 'test' and args.threshold:
            # Single threshold mode (backward compat)
            tier_thresholds = {t: args.threshold for t in TIERS}
            platt_params = {t: (5.0, -2.5) for t in TIERS}  # default Platt
            print(f"Using supplied threshold={args.threshold} for all tiers")

        gt_test = load_ground_truth(athena, 2020, args.bucket, args.workgroup, country_ids)
        print(f"Ground truth: {len(gt_test)} (country, category) pairs post-2020")

        print("\nLoading per-tier predictions...")
        preds_by_tier_test = load_recipe_predictions_by_tier(
            athena, args.recipe_table, 2020, args.bucket, args.workgroup, country_ids,
        )
        recency_test = load_recency(athena, 2020, args.bucket, args.workgroup, country_ids)
        persist_test = load_persistence(athena, 2020, args.bucket, args.workgroup, country_ids)

        tier_metrics_test = {}
        # Accumulate (pair, y_true, y_pred) across tiers for per-category /
        # per-country stratified metrics (#400, #401). y_pred is already
        # thresholded per-tier so cross-tier aggregation is correct even when
        # thresholds differ across tiers.
        all_pairs_test: list = []
        all_y_true_test: list = []
        all_y_pred_test: list = []
        # #463 Part C: per-pair predictions for V2.0-vs-V1.9.1 eval fixture.
        # One record per (pair, tier, system) so eval_v2_vs_v19.py can compare
        # V1.9.1's salience-derived calibrated score against V2.0's recipe
        # similarity for the same 649 pairs at 2020 cutoff.
        pair_records: list[dict] = []
        for tier_name in TIERS:
            preds = preds_by_tier_test[tier_name]
            if not preds:
                tier_metrics_test[tier_name] = None
                continue

            # V1.8: recency → z-score per country → rank fusion with persistence
            preds_boosted = apply_recency(preds, recency_test, 2020)
            preds_zscored = zscore_per_country(preds_boosted)

            # V1.8: Rank fusion ensemble with persistence
            preds_fused = rank_fusion_ensemble(preds_zscored, persist_test)
            y_true, y_scores, pairs = build_arrays_with_pairs(preds_fused, gt_test)

            # Apply LOCKED Platt params from validation
            a, b = platt_params.get(tier_name, (5.0, -2.5))
            y_cal = 1.0 / (1.0 + np.exp(-(a * y_scores + b)))

            threshold = tier_thresholds.get(tier_name, 0.5)
            m = compute_metrics(y_true, y_cal, threshold)
            tier_metrics_test[tier_name] = m

            # #400 + #401: accumulate for stratified metrics post-loop.
            # y_pred is binary (already thresholded at this tier's threshold).
            y_pred_tier = (y_cal >= threshold).astype(int)
            all_pairs_test.extend(pairs)
            all_y_true_test.extend(y_true.tolist())
            all_y_pred_test.extend(y_pred_tier.tolist())

            # #463 Part C: collect per-pair records for the eval fixture.
            for (country_id, category), yc, yt in zip(pairs, y_cal, y_true):
                pair_records.append({
                    "country_a_id": country_id,
                    "event_category": category,
                    "tier": tier_name,
                    "system": "v1.9.1",
                    "y_cal": float(yc),
                    "y_true": int(yt),
                    "cutoff_year": args.cutoff,
                })

            if args.dump_raw_scores:
                raw_scores[tier_name]['test'] = [
                    [float(p), int(l)] for p, l in zip(y_cal, y_true)
                ]

            print(
                f"\n  {tier_name}: threshold={threshold} (locked) | "
                f"F1={m['f1']} | Precision={m['precision']} | "
                f"AUPRC={m['auprc']} | Lift@50={m['lift_at_50']}"
            )

        # Persistence baseline
        y_true_p, y_scores_p = build_arrays(persist_test, gt_test)
        mp = compute_metrics(y_true_p, y_scores_p, 0.3)

        # #463 Part C: persistence baseline rows for the eval fixture.
        # Build a parallel pair list since build_arrays doesn't return one;
        # mirror its sort order.
        all_pairs_persist = sorted(set(persist_test.keys()) | gt_test)
        for (country_id, category), yp, yt in zip(all_pairs_persist, y_scores_p, y_true_p):
            pair_records.append({
                "country_a_id": country_id,
                "event_category": category,
                "tier": "all",  # persistence is single-pass, not tiered
                "system": "persistence",
                "y_cal": float(yp),
                "y_true": int(yt),
                "cutoff_year": args.cutoff,
            })

        # #463 Part C: write the per-pair fixture JSONL when --dump-pairs-jsonl
        # is supplied. One JSON per line (canonical JSONL format) so the
        # eval reader can stream-parse instead of loading the whole file.
        if args.dump_pairs_jsonl:
            with open(args.dump_pairs_jsonl, 'w', encoding='utf-8') as jf:
                for rec in pair_records:
                    jf.write(json.dumps(rec) + "\n")
            print(f"\n  Wrote {len(pair_records)} per-pair records to {args.dump_pairs_jsonl}")

        # Aggregate
        print("\n" + "=" * 70)
        print("TEST SUMMARY (per-tier, locked params)")
        print("=" * 70)
        header = ['Tier', 'F1', 'F2', 'Precision', 'Recall', 'AUPRC', 'NDCG@20', 'Lift@50', 'N_pred', 'N_gt']
        rows = []
        total_preds = 0
        weighted_f1 = 0
        for tier_name in TIERS:
            m = tier_metrics_test.get(tier_name)
            if m is None:
                rows.append([tier_name, '-', '-', '-', '-', '-', '-', '-', 0, 0])
                continue
            rows.append([
                tier_name, m['f1'], m['f2'], m['precision'], m['recall'], m['auprc'],
                m['ndcg_at_20'], m['lift_at_50'], m['n_predictions'], m['n_ground_truth'],
            ])
            total_preds += m['n_total']
            weighted_f1 += m['f1'] * m['n_total']

        agg_f1 = round(weighted_f1 / total_preds, 4) if total_preds > 0 else 0
        rows.append(['AGG', agg_f1, '', '', '', '', '', '', total_preds, ''])
        rows.append(['Persist', mp['f1'], mp['f2'], mp['precision'], mp['recall'], mp['auprc'], mp['ndcg_at_20'], mp['lift_at_50'], mp['n_predictions'], mp['n_ground_truth']])
        print_table(header, rows)

        beats_persist = agg_f1 > mp['f1']
        print(f"\nV1.8 beats persistence? {'YES' if beats_persist else 'NO'} (AGG F1={agg_f1} vs {mp['f1']})")

        # #400 + #401 + #396: per-category / per-country / per-region
        # stratified metrics across the full test set (all tiers combined,
        # each tier contributing its own thresholded y_pred).
        metrics_by_category = {}
        per_country_metrics = {}
        per_country_summary = None
        metrics_by_region = {}
        if all_pairs_test:
            metrics_by_category = stratified_metrics(
                all_pairs_test, all_y_true_test, all_y_pred_test,
                group_fn=lambda p: p[1],  # category is the second element
                min_samples=5,
            )
            per_country_metrics = stratified_metrics(
                all_pairs_test, all_y_true_test, all_y_pred_test,
                group_fn=lambda p: p[0],  # country_id is the first element
                min_samples=5,
            )
            per_country_summary = summarize_per_country_distribution(per_country_metrics)

            # #396: per-region F1 (AFR/MEA/EUR/ASI/AMR/OCE). Graceful no-op
            # when the regions map can't be loaded (empty id_to_region dict).
            id_to_region = load_country_id_to_region(
                athena, args.bucket, args.workgroup,
            )
            if id_to_region:
                metrics_by_region = stratified_metrics(
                    all_pairs_test, all_y_true_test, all_y_pred_test,
                    group_fn=lambda p: id_to_region.get(
                        int(float(p[0])) if str(p[0]).replace('.', '', 1).isdigit() else p[0],
                        "UNKNOWN",
                    ),
                    min_samples=5,
                )

            if metrics_by_category:
                # Print top 10 categories by n_gt — surfaces the ones that matter.
                top_cats = sorted(
                    metrics_by_category.items(),
                    key=lambda kv: kv[1]['n_gt'], reverse=True,
                )[:10]
                print("\n" + "=" * 70)
                print("TEST — PER-CATEGORY F1 (top 10 by ground-truth count) — #400")
                print("=" * 70)
                print_table(
                    ['Category', 'F1', 'Precision', 'Recall', 'n_gt', 'n_total'],
                    [[c, m['f1'], m['precision'], m['recall'], m['n_gt'], m['n_total']]
                     for c, m in top_cats],
                )

            if per_country_summary:
                print("\n" + "=" * 70)
                print("TEST — PER-COUNTRY F1 DISTRIBUTION — #401")
                print("=" * 70)
                d = per_country_summary['distribution']
                print(
                    f"  n={per_country_summary['n_countries']}  "
                    f"p10={d['p10']}  p25={d['p25']}  median={d['median']}  "
                    f"p75={d['p75']}  p90={d['p90']}"
                )
                worst_str = ", ".join(
                    f"{r['country_id']}:{r['f1']}" for r in per_country_summary['worst_k']
                )
                best_str = ", ".join(
                    f"{r['country_id']}:{r['f1']}" for r in per_country_summary['best_k']
                )
                print(f"  worst 5: {worst_str}")
                print(f"  best  5: {best_str}")

            # #396: per-region F1 summary
            if metrics_by_region:
                print("\n" + "=" * 70)
                print("TEST — PER-REGION F1 (AFR/MEA/EUR/ASI/AMR/OCE) — #396")
                print("=" * 70)
                # Sort by n_gt descending so the rows with most data come first.
                rows_by_region = sorted(
                    metrics_by_region.items(),
                    key=lambda kv: kv[1]['n_gt'], reverse=True,
                )
                print_table(
                    ['Region', 'F1', 'Precision', 'Recall', 'n_gt', 'n_total'],
                    [[r, m['f1'], m['precision'], m['recall'], m['n_gt'], m['n_total']]
                     for r, m in rows_by_region],
                )

    # Save results
    if args.mode == 'full':
        results = {
            'version': 'V1.8',
            'curated_only': args.curated_only,
            'n_countries': len(country_ids) if country_ids else 'all',
            'tiers': list(TIERS.keys()),
            'tier_ranges': TIERS,
            'validation': {
                'cutoff': 2015,
                'platt_params': {t: list(v) for t, v in platt_params.items()},
                'thresholds': tier_thresholds,
                'metrics': {
                    t: m for t, m in tier_metrics_val.items() if m is not None
                },
            },
            'test': {
                'cutoff': 2020,
                'metrics': {
                    t: m for t, m in tier_metrics_test.items() if m is not None
                },
                'persistence': mp,
                'aggregate_f1': agg_f1,
                'beats_persistence': bool(beats_persist),
                # #400: F1/precision/recall/n_gt per event category, pooled
                # across all tiers with each tier's own threshold.
                'metrics_by_category': metrics_by_category,
                # #401: distribution stats + worst/best 5 countries by F1.
                # Full per-country map under `per_country_full` for drill-in.
                'per_country_f1': per_country_summary,
                'per_country_full': per_country_metrics,
                # #396: per-region F1 (AFR/MEA/EUR/ASI/AMR/OCE). Empty dict if
                # country_regions.yaml wasn't resolvable.
                'aggregate_by_region': metrics_by_region,
            },
        }
        out_path = args.output
        with open(out_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {out_path}")

        if args.dump_raw_scores:
            base, ext = os.path.splitext(out_path)
            raw_path = f"{base}_raw{ext or '.json'}"
            raw_payload = {
                'version': results['version'],
                'tiers': raw_scores,
            }
            with open(raw_path, 'w') as f:
                json.dump(raw_payload, f)
            print(f"Raw (prob, label) scores saved to {raw_path}")


if __name__ == '__main__':
    main()
