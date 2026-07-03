#!/usr/bin/env python3
"""
QGI Backtesting Script V2 — Walk-forward validation with improved scoring.

Changes from V1:
- Log-space confidence scoring (not raw product)
- Multiple threshold sweep to find optimal F1
- Validation (cutoff=2015) and Test (cutoff=2020) modes
- QA-only event filtering
- Per-category metrics
- Lift@K at K=10,50,100,200

Usage:
    # Validation run (tune threshold):
    python run_backtest.py --bucket qgi-data-lake-771606957899 --role-arn ... --cutoff 2015 --mode validate

    # Test run (locked threshold):
    python run_backtest.py --bucket qgi-data-lake-771606957899 --role-arn ... --cutoff 2020 --mode test --threshold 0.35

    # Full run (both):
    python run_backtest.py --bucket qgi-data-lake-771606957899 --role-arn ... --mode full
"""

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict

import boto3
import numpy as np


def get_athena(args):
    if args.role_arn:
        sts = boto3.client("sts", region_name=args.region)
        creds = sts.assume_role(RoleArn=args.role_arn, RoleSessionName="backtest")["Credentials"]
        return boto3.client(
            "athena",
            region_name=args.region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
    return boto3.client("athena", region_name=args.region)


def run_query(athena, sql, max_results=1000):
    account_id = os.environ.get("AWS_ACCOUNT_ID", "771606957899")
    r = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": "qgi_data"},
        WorkGroup="QGI-Lambda-Workgroup",
        ResultConfiguration={"OutputLocation": f"s3://qgi-data-lake-{account_id}/query_results/"},
    )
    qid = r["QueryExecutionId"]
    while True:
        time.sleep(3)
        s = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if s["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
    if s["State"] != "SUCCEEDED":
        print(f"FAILED: {s.get('StateChangeReason', '?')[:200]}", file=sys.stderr)
        return []

    rows = []
    result = athena.get_query_results(QueryExecutionId=qid, MaxResults=max_results)
    cols = [c["Name"] for c in result["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
    for row in result["ResultSet"]["Rows"][1:]:
        d = {cols[i]: row["Data"][i].get("VarCharValue") for i in range(len(cols))}
        rows.append(d)
    while "NextToken" in result:
        result = athena.get_query_results(QueryExecutionId=qid, NextToken=result["NextToken"], MaxResults=max_results)
        for row in result["ResultSet"]["Rows"]:
            d = {cols[i]: row["Data"][i].get("VarCharValue") for i in range(len(cols))}
            rows.append(d)
    return rows


def log_score(count, correlation, indicator_count):
    """Log-space confidence scoring — prevents extreme outliers."""
    return 0.4 * math.log(float(count) + 1) + 0.4 * float(correlation) + 0.2 * math.log(float(indicator_count) + 1)


def compute_metrics(y_true, y_scores, threshold):
    """Compute full metrics suite at a given threshold."""
    y_pred = (y_scores >= threshold).astype(int)
    tp = ((y_pred == 1) & (y_true == 1)).sum()
    fp = ((y_pred == 1) & (y_true == 0)).sum()
    fn = ((y_pred == 0) & (y_true == 1)).sum()

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
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
    auprc = 0
    prev_recall = 0
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

    return {
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "auprc": round(auprc, 4),
        "lift": round(lift, 2),
        "brier_skill_score": round(bss, 4),
        "precision_at_3": round(precision_at_k(3), 4),
        "precision_at_5": round(precision_at_k(5), 4),
        "precision_at_10": round(precision_at_k(10), 4),
        "precision_at_50": round(precision_at_k(50), 4),
        "precision_at_100": round(precision_at_k(100), 4),
        "lift_at_10": round(lift_at_k(10), 2),
        "lift_at_50": round(lift_at_k(50), 2),
        "lift_at_100": round(lift_at_k(100), 2),
        "lift_at_200": round(lift_at_k(200), 2),
        "coverage": round((y_scores > 0).mean(), 4),
        "base_rate": round(base_rate, 4),
        "n_predictions": int((y_pred == 1).sum()),
        "n_ground_truth": int(y_true.sum()),
        "n_total": len(y_true),
    }


def load_ground_truth(athena, cutoff, source_filter=""):
    """Load actual events after cutoff."""
    sf = f"AND source = '{source_filter}'" if source_filter else ""
    rows = run_query(
        athena,
        f"""
        SELECT country_id, category_normalized
        FROM qgi_data.events
        WHERE year > {cutoff} {sf}
        GROUP BY country_id, category_normalized
    """,
    )
    return {(r["country_id"], r["category_normalized"]) for r in rows}


def load_recipe_predictions(athena, table, cutoff):
    """Load aggregated recipe predictions with log-space scoring."""
    rows = run_query(
        athena,
        f"""
        SELECT country_a_id, event_category,
               count(*) as recipe_count,
               avg(avg_correlation) as avg_corr,
               avg(indicator_count) as avg_ind
        FROM qgi_data.{table}
        WHERE end_year_a <= {cutoff} AND end_year_b <= {cutoff}
        GROUP BY country_a_id, event_category
    """,
    )
    preds = {}
    for r in rows:
        score = log_score(r["recipe_count"], r["avg_corr"], r["avg_ind"])
        preds[(r["country_a_id"], r["event_category"])] = score

    # Normalize to 0-1 using min-max on log scores
    if preds:
        vals = list(preds.values())
        mn, mx = min(vals), max(vals)
        rng = mx - mn if mx > mn else 1
        preds = {k: (v - mn) / rng for k, v in preds.items()}

    return preds


def load_persistence(athena, cutoff):
    """Persistence baseline: events in [cutoff-2, cutoff] predict cutoff+1."""
    rows = run_query(
        athena,
        f"""
        SELECT country_id, category_normalized, count(*) as cnt
        FROM qgi_data.events
        WHERE year BETWEEN {cutoff - 2} AND {cutoff}
        GROUP BY country_id, category_normalized
    """,
    )
    return {(r["country_id"], r["category_normalized"]): float(r["cnt"]) / 3.0 for r in rows}


def load_recency(athena, cutoff):
    """Load most recent event year per (country, category) before cutoff."""
    rows = run_query(
        athena,
        f"""
        SELECT country_id, category_normalized, max(year) as last_year
        FROM qgi_data.events
        WHERE year <= {cutoff}
        GROUP BY country_id, category_normalized
    """,
    )
    return {(r["country_id"], r["category_normalized"]): int(r["last_year"]) for r in rows}


def apply_recency(preds, recency, cutoff, decay=0.85):
    """Boost predictions by recency: recent events = higher score."""
    boosted = {}
    for key, score in preds.items():
        last_year = recency.get(key)
        if last_year is not None:
            years_ago = cutoff - last_year
            boost = decay**years_ago  # 0.85^1=0.85, 0.85^5=0.44, 0.85^10=0.20
            boosted[key] = score + 0.3 * boost  # additive boost, weighted
        else:
            boosted[key] = score
    return boosted


def platt_scale(y_true_train, y_scores_train, y_scores_test):
    """Fit Platt scaling on train, apply to test. Returns calibrated probabilities."""
    # Fit: find a, b such that P = 1/(1+exp(-(a*score+b)))
    # Simple grid search for a and b
    best_loss = float("inf")
    best_a, best_b = 1.0, 0.0

    for a in np.arange(0.5, 20, 0.5):
        for b in np.arange(-10, 5, 0.5):
            probs = 1.0 / (1.0 + np.exp(-(a * y_scores_train + b)))
            probs = np.clip(probs, 1e-7, 1 - 1e-7)
            # Log loss
            loss = -np.mean(y_true_train * np.log(probs) + (1 - y_true_train) * np.log(1 - probs))
            if loss < best_loss:
                best_loss = loss
                best_a, best_b = a, b

    # Apply to test
    calibrated = 1.0 / (1.0 + np.exp(-(best_a * y_scores_test + best_b)))
    return calibrated, best_a, best_b


def find_best_threshold(y_true, y_scores, thresholds=None):
    """Sweep thresholds, return the one with best F1."""
    if thresholds is None:
        thresholds = np.arange(0.05, 0.95, 0.05)
    best_f1 = 0
    best_t = 0.5
    for t in thresholds:
        m = compute_metrics(y_true, y_scores, t)
        if m["f1"] > best_f1:
            best_f1 = m["f1"]
            best_t = t
    return round(best_t, 2), round(best_f1, 4)


def build_arrays(preds, ground_truth):
    """Convert prediction dict + ground truth set into aligned numpy arrays."""
    all_pairs = sorted(set(preds.keys()) | ground_truth)
    y_true = np.array([1 if p in ground_truth else 0 for p in all_pairs])
    y_scores = np.array([preds.get(p, 0.0) for p in all_pairs])
    return y_true, y_scores


def print_table(header, rows):
    """Print a formatted table."""
    widths = [max(len(str(r[i])) for r in [header] + rows) + 2 for i in range(len(header))]
    fmt = "".join(f"{{:<{w}s}}" for w in widths)
    print(fmt.format(*[str(h) for h in header]))
    print("-" * sum(widths))
    for row in rows:
        print(fmt.format(*[str(v) for v in row]))


def main():
    parser = argparse.ArgumentParser(description="QGI Backtesting V2")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default="eu-central-1")
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--cutoff", type=int, default=2020)
    parser.add_argument("--mode", choices=["validate", "test", "full"], default="full")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--recipe-table", default="recipes", help="Athena table for recipes")
    args = parser.parse_args()

    athena = get_athena(args)

    if args.mode == "full":
        # Phase 1: Validate (cutoff=2015, find threshold)
        print("=" * 70)
        print("PHASE 1: VALIDATION (cutoff=2015)")
        print("=" * 70)
        gt_val = load_ground_truth(athena, 2015)
        preds_val_raw = load_recipe_predictions(athena, args.recipe_table, 2015)
        recency_val = load_recency(athena, 2015)
        preds_val = apply_recency(preds_val_raw, recency_val, 2015)
        # Re-normalize after recency
        if preds_val:
            vals = list(preds_val.values())
            mn, mx = min(vals), max(vals)
            rng = mx - mn if mx > mn else 1
            preds_val = {k: (v - mn) / rng for k, v in preds_val.items()}
        persist_val = load_persistence(athena, 2015)
        print(f"Ground truth: {len(gt_val)} pairs | Predictions: {len(preds_val)} pairs")

        y_true_val, y_scores_val = build_arrays(preds_val, gt_val)

        # Platt scaling: fit on validation
        print("Fitting Platt scaling...")
        y_scores_cal, platt_a, platt_b = platt_scale(y_true_val, y_scores_val, y_scores_val)
        print(f"Platt params: a={platt_a:.2f}, b={platt_b:.2f}")

        # Find best threshold on calibrated scores
        best_threshold, best_f1 = find_best_threshold(y_true_val, y_scores_cal)
        print(f"Best threshold (calibrated): {best_threshold} (F1={best_f1})")

        # Show validation metrics
        m = compute_metrics(y_true_val, y_scores_cal, best_threshold)
        y_true_p, y_scores_p = build_arrays(persist_val, gt_val)
        mp = compute_metrics(y_true_p, y_scores_p, 0.3)

        print(f"\nValidation metrics at threshold={best_threshold}:")
        print_table(
            ["Metric", "Persistence", "V1.5.2"],
            [
                [k, mp.get(k, ""), m.get(k, "")]
                for k in [
                    "f1",
                    "precision",
                    "recall",
                    "auprc",
                    "lift",
                    "lift_at_50",
                    "lift_at_100",
                    "brier_skill_score",
                    "n_predictions",
                ]
            ],
        )

        # Phase 2: Test (cutoff=2020, locked threshold + Platt params)
        print()
        print("=" * 70)
        print(f"PHASE 2: TEST (cutoff=2020, threshold={best_threshold}, Platt a={platt_a:.2f} b={platt_b:.2f} LOCKED)")
        print("=" * 70)
        gt_test = load_ground_truth(athena, 2020)
        preds_test_raw = load_recipe_predictions(athena, args.recipe_table, 2020)
        recency_test = load_recency(athena, 2020)
        preds_test = apply_recency(preds_test_raw, recency_test, 2020)
        if preds_test:
            vals = list(preds_test.values())
            mn, mx = min(vals), max(vals)
            rng = mx - mn if mx > mn else 1
            preds_test = {k: (v - mn) / rng for k, v in preds_test.items()}
        persist_test = load_persistence(athena, 2020)
        random_preds = {k: np.random.random() for k in set(preds_test.keys()) | gt_test}
        print(f"Ground truth: {len(gt_test)} pairs | Predictions: {len(preds_test)} pairs")

        y_true_t, y_scores_t_raw = build_arrays(preds_test, gt_test)
        # Apply Platt scaling with locked params from validation
        y_scores_t = 1.0 / (1.0 + np.exp(-(platt_a * y_scores_t_raw + platt_b)))

        y_true_p2, y_scores_p2 = build_arrays(persist_test, gt_test)
        y_true_r, y_scores_r = build_arrays(random_preds, gt_test)

        mt = compute_metrics(y_true_t, y_scores_t, best_threshold)
        mp2 = compute_metrics(y_true_p2, y_scores_p2, 0.3)
        mr = compute_metrics(y_true_r, y_scores_r, 0.5)

        print(f"\nTest metrics (threshold={best_threshold}, Platt-calibrated):")
        print_table(
            ["Metric", "Persistence", "Random", "V1.5.2"],
            [
                [k, mp2.get(k, ""), mr.get(k, ""), mt.get(k, "")]
                for k in [
                    "f1",
                    "precision",
                    "recall",
                    "auprc",
                    "lift",
                    "lift_at_10",
                    "lift_at_50",
                    "lift_at_100",
                    "lift_at_200",
                    "precision_at_3",
                    "precision_at_5",
                    "precision_at_10",
                    "precision_at_50",
                    "brier_skill_score",
                    "coverage",
                    "n_predictions",
                    "n_ground_truth",
                ]
            ],
        )

        # Summary
        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Validation threshold: {best_threshold}")
        print(f"V1.5.2 beats persistence (F1)?  {'YES' if mt['f1'] > mp2['f1'] else 'NO'} ({mt['f1']} vs {mp2['f1']})")
        print(f"V1.5.2 beats random (F1)?       {'YES' if mt['f1'] > mr['f1'] else 'NO'} ({mt['f1']} vs {mr['f1']})")
        print(f"V1.5.2 Lift:                    {mt['lift']}x")
        print(f"V1.5.2 Lift@50:                 {mt['lift_at_50']}x")
        print(f"V1.5.2 Lift@100:                {mt['lift_at_100']}x")
        print(f"V1.5.2 AUPRC:                   {mt['auprc']} (random: {mr['auprc']})")

        # Save
        results = {
            "validation": {"cutoff": 2015, "best_threshold": best_threshold, "best_f1": best_f1, "metrics": m},
            "test": {"cutoff": 2020, "threshold": best_threshold, "persistence": mp2, "random": mr, "v1_5_1": mt},
        }
        with open("backtest_v151_results.json", "w") as f:
            json.dump(results, f, indent=2)
        print("\nResults saved to backtest_v151_results.json")

    else:
        cutoff = args.cutoff
        threshold = args.threshold or 0.5
        print(f"Mode: {args.mode} | Cutoff: {cutoff} | Threshold: {threshold}")
        gt = load_ground_truth(athena, cutoff)
        preds = load_recipe_predictions(athena, args.recipe_table, cutoff)
        print(f"Ground truth: {len(gt)} | Predictions: {len(preds)}")
        y_true, y_scores = build_arrays(preds, gt)

        if args.mode == "validate":
            bt, bf = find_best_threshold(y_true, y_scores)
            print(f"Best threshold: {bt} (F1={bf})")
        m = compute_metrics(y_true, y_scores, threshold)
        for k, v in m.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
