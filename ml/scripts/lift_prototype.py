#!/usr/bin/env python3
"""
lift_prototype.py — Lean lift comparison for #585.

For 5 selected recipes, compute per-I(1)-indicator auditioner-style predictive
lift under two methods:
  RAW:  features (mean, std, slope, change) computed on Z-scored LEVELS
  DIFF: features computed on Z-scored FIRST-DIFFERENCES

If detrending preserves genuine signal, lift should be similar between methods.
If detrending kills signal, lift collapses to ~0 under DIFF.
If detrending was removing only spurious-trend lift, RAW lift > DIFF lift but
DIFF lift remains meaningfully positive.

This is a LEAN prototype — 5 recipes × ~5 I(1) indicators each = ~25 cells.
Informs whether the heavy version (full auditioner with --detrend-method) is
worth running.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import roc_auc_score


# Recipes selected to span L1 sectors + prominently feature I(1) indicators
SELECTED_RECIPES = [
    "military_coup",
    "government_formation",
    "economic_recession",
    "trade_agreement",
    "civil_war_and_insurgency",
]

CUTOFF_YEAR = 2020
END_YEAR = 2026
CANONICAL_LENGTH = 25  # use 25-yr window for all recipes in this lean test
RANDOM_SEED = 42


def run_athena(ath, sql, bucket, workgroup, db="qgi_data"):
    r = ath.start_query_execution(
        QueryString=sql, QueryExecutionContext={"Database": db},
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": f"s3://{bucket}/query_results/"},
    )
    qid = r["QueryExecutionId"]
    while True:
        time.sleep(1.5)
        s = ath.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if s["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
    if s["State"] != "SUCCEEDED":
        raise RuntimeError(f"Athena {s['State']}: {s.get('StateChangeReason', '?')}")
    return qid


def athena_fetch_all(ath, qid):
    rows, token, first = [], None, True
    while True:
        kw = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kw["NextToken"] = token
        page = ath.get_query_results(**kw)
        page_rows = page["ResultSet"]["Rows"]
        if first and page_rows:
            page_rows = page_rows[1:]
            first = False
        for r in page_rows:
            rows.append([c.get("VarCharValue") for c in r["Data"]])
        token = page.get("NextToken")
        if not token:
            break
    return rows


def fetch_ground_truth(ath, bucket, workgroup, categories):
    in_clause = ",".join(f"'{c}'" for c in categories)
    sql = f"""
    SELECT country_id, category_normalized AS event_category,
           cast(max(year) > {CUTOFF_YEAR} AS integer) AS y_post_cutoff
    FROM qgi_data.events
    WHERE category_normalized IN ({in_clause})
      AND year BETWEEN 1900 AND {END_YEAR}
    GROUP BY country_id, category_normalized
    """
    print(f"[athena] ground truth events for {len(categories)} categories...")
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    df = pd.DataFrame(rows, columns=["country_id", "event_category", "y_post_cutoff"])
    df["country_id"] = df["country_id"].astype(int)
    df["y_post_cutoff"] = df["y_post_cutoff"].astype(int)
    return df


def fetch_countries(ath, bucket, workgroup):
    sql = """
    SELECT id AS country_id, name_1 AS name
    FROM qgi_data.countries
    WHERE id IS NOT NULL AND id != ''
    """
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    df = pd.DataFrame(rows, columns=["country_id", "name"])
    df["country_id"] = df["country_id"].astype(int)
    return df


def load_indicator_map(s3, bucket):
    import csv
    import io
    obj = s3.get_object(
        Bucket=bucket, Key="pipeline-A-indicator-extractor/input/indicator_map.csv"
    )
    text = obj["Body"].read().decode("utf-8")
    rdr = csv.DictReader(io.StringIO(text))
    return {int(r["numeric_id"]): r["id_string"] for r in rdr}


def load_recipes_fingerprints(recipes_json_path: Path, selected: list[str]):
    """Read recipes-aggregated.json, return {category: [{indicator_id, ...}, ...]}."""
    data = json.loads(recipes_json_path.read_text(encoding="utf-8"))
    out = {}
    for r in data["recipes"]:
        if r["event_category"] in selected:
            out[r["event_category"]] = r["indicator_fingerprint"]
    return out


def stats_from_series(values, mode):
    """
    mode = 'raw': features from Z-scored levels
    mode = 'diff': features from Z-scored first-differences
    Returns [mean, std, slope, change] or [nan]*4 if insufficient.
    """
    arr = np.asarray(values, dtype=float)
    if mode == "diff":
        if len(arr) < 3:
            return [np.nan] * 4
        arr = np.diff(arr)
    if len(arr) < 3:
        return [np.nan] * 4
    # Z-score the (post-diff if applicable) series for scale invariance
    mu = float(np.mean(arr))
    sd = float(np.std(arr)) if len(arr) > 1 else 1.0
    if sd < 1e-9:
        return [np.nan] * 4
    z = (arr - mu) / sd
    # Stats on z
    mean = float(np.mean(z))   # always 0 by construction; keep as feature for the GBM to verify
    std = float(np.std(z))     # always 1 by construction; same
    if len(z) >= 2:
        slope = float(np.polyfit(np.arange(len(z)), z, 1)[0])
        change = float(z[-1] - z[0])
    else:
        slope = 0.0
        change = 0.0
    # Replace mean/std (which are constant under z) with raw mean and std
    return [mu, sd, slope, change]


def build_features(panel, fingerprint, num_to_str, country_to_id, mode, i1_set):
    """
    Build (country_id × feature) DataFrame.
    For each indicator in fingerprint:
      if it's I(1) and mode=='diff': use diff features
      else: use raw features
    """
    window_start = CUTOFF_YEAR - CANONICAL_LENGTH
    window_end = CUTOFF_YEAR
    feature_cols = []
    rows = {}

    for fp in fingerprint:
        nid = fp["indicator_id"]
        sid = num_to_str.get(nid)
        if sid is None:
            continue
        # Decide method per indicator
        if mode == "diff" and sid in i1_set:
            method = "diff"
        else:
            method = "raw"
        # Per-country features
        for stat in ["mean", "std", "slope", "change"]:
            feature_cols.append(f"ind{nid}__{stat}")
        sub = panel[(panel["indicator_id"] == sid) &
                    (panel["year"] >= window_start) &
                    (panel["year"] <= window_end)]
        for ctry in sub["country"].unique():
            cdata = sub[sub["country"] == ctry].sort_values("year")
            stats = stats_from_series(cdata["value"].to_numpy(), method)
            country_id = country_to_id.get(ctry)
            if country_id is None:
                continue
            if country_id not in rows:
                rows[country_id] = {"country_id": country_id, "country": ctry}
            for stat_name, v in zip(["mean", "std", "slope", "change"], stats):
                rows[country_id][f"ind{nid}__{stat_name}"] = v

    df = pd.DataFrame(list(rows.values()))
    return df, feature_cols


def fit_and_score(features, feature_cols, y_col="y"):
    X = features[feature_cols].fillna(0.0).to_numpy()
    y = features[y_col].to_numpy()
    if y.sum() < 2 or (1 - y).sum() < 2 or len(y) < 20:
        return None
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.20, random_state=RANDOM_SEED)
    train_idx, test_idx = next(sss.split(X, y))
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    if y_test.sum() < 1 or (1 - y_test).sum() < 1:
        return None
    model = GradientBoostingClassifier(
        n_estimators=80, max_depth=3, learning_rate=0.05,
        random_state=RANDOM_SEED, subsample=0.9,
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    if len(np.unique(y_test)) < 2:
        return None
    test_auc = float(roc_auc_score(y_test, proba))
    pi = permutation_importance(
        model, X_test, y_test, n_repeats=10,
        random_state=RANDOM_SEED, scoring="neg_log_loss",
    )
    importances = {col: float(imp) for col, imp in zip(feature_cols, pi.importances_mean)}
    # Aggregate per indicator (sum positive lifts across the 4 stat columns)
    from collections import defaultdict
    per_ind = defaultdict(float)
    for col, imp in importances.items():
        prefix = col.split("__", 1)[0]
        per_ind[prefix] += max(0.0, imp)
    return {"test_auc": test_auc, "n_train": len(X_train), "n_test": len(X_test),
            "per_indicator_lift": dict(per_ind)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True)
    p.add_argument("--workgroup", default="QGI-Lambda-Workgroup")
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--cache-path", type=Path, default=Path("qgi-ml/data/all_104_panels.parquet"))
    p.add_argument("--regimes-path", type=Path, default=Path("qgi-data/reference/indicator-regimes.json"))
    p.add_argument("--recipes-json", type=Path, default=Path("qgi-frontend/data/recipes-aggregated.json"))
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    s3 = boto3.client("s3", region_name=args.region)
    ath = boto3.client("athena", region_name=args.region)

    # Indicator map
    num_to_str = load_indicator_map(s3, args.bucket)
    print(f"[map] {len(num_to_str)} numeric -> string mappings")

    # Regimes
    regimes = json.loads(args.regimes_path.read_text(encoding="utf-8"))
    i1_set = set(regimes["regimes"]["i1"])
    print(f"[regimes] {len(i1_set)} I(1) indicators")

    # Fingerprints
    fingerprints = load_recipes_fingerprints(args.recipes_json, SELECTED_RECIPES)
    print(f"[recipes] {len(fingerprints)}/{len(SELECTED_RECIPES)} selected recipes found")

    # Identify all indicators we need (union of fingerprints)
    needed_nids = set()
    for cat, fp in fingerprints.items():
        for entry in fp:
            needed_nids.add(entry["indicator_id"])
    needed_sids = sorted({num_to_str[n] for n in needed_nids if n in num_to_str})
    print(f"[needed] {len(needed_sids)} unique indicator strings across fingerprints")

    # Load or fetch panel
    if args.cache_path.exists():
        print(f"[cache] loading from {args.cache_path}")
        panel = pd.read_parquet(args.cache_path)
    else:
        in_clause = ",".join(f"'{i}'" for i in needed_sids)
        sql = f"""
        SELECT country, year, indicator_id, value
        FROM qgi_data.indicators
        WHERE indicator_id IN ({in_clause})
          AND value IS NOT NULL
        """
        print(f"[athena] fetching panel for {len(needed_sids)} indicators...")
        qid = run_athena(ath, sql, args.bucket, args.workgroup)
        rows = athena_fetch_all(ath, qid)
        panel = pd.DataFrame(rows, columns=["country", "year", "indicator_id", "value"])
        panel["year"] = panel["year"].astype(int)
        panel["value"] = panel["value"].astype(float)
        args.cache_path.parent.mkdir(parents=True, exist_ok=True)
        panel.to_parquet(args.cache_path)
        print(f"[cache] saved {len(panel):,} rows")

    # Countries + ground truth
    countries = fetch_countries(ath, args.bucket, args.workgroup)
    country_to_id = dict(zip(countries["name"], countries["country_id"]))
    gt = fetch_ground_truth(ath, args.bucket, args.workgroup, list(fingerprints.keys()))

    # Per-recipe comparison
    results = []
    for cat, fp in fingerprints.items():
        cat_gt = gt[gt["event_category"] == cat][["country_id", "y_post_cutoff"]]
        i1_in_fp = sum(1 for entry in fp if num_to_str.get(entry["indicator_id"]) in i1_set)
        print(f"\n[recipe] {cat}  (fingerprint size {len(fp)}, I(1) in fp: {i1_in_fp})")

        # Build features + train under RAW
        feat_raw, cols_raw = build_features(panel, fp, num_to_str, country_to_id, "raw", i1_set)
        feat_raw = feat_raw.merge(cat_gt, on="country_id", how="left")
        feat_raw["y"] = feat_raw["y_post_cutoff"].fillna(0).astype(int)
        res_raw = fit_and_score(feat_raw, cols_raw)

        # Build features + train under DIFF (only I(1) indicators get diff'd)
        feat_diff, cols_diff = build_features(panel, fp, num_to_str, country_to_id, "diff", i1_set)
        feat_diff = feat_diff.merge(cat_gt, on="country_id", how="left")
        feat_diff["y"] = feat_diff["y_post_cutoff"].fillna(0).astype(int)
        res_diff = fit_and_score(feat_diff, cols_diff)

        if res_raw is None or res_diff is None:
            print("  -> skipped (insufficient data)")
            continue

        print(f"  RAW  AUC={res_raw['test_auc']:.3f}  (n_train={res_raw['n_train']}, n_test={res_raw['n_test']})")
        print(f"  DIFF AUC={res_diff['test_auc']:.3f}  (n_train={res_diff['n_train']}, n_test={res_diff['n_test']})")

        # Per-I(1)-indicator lift comparison
        per_ind_compare = []
        for entry in fp:
            nid = entry["indicator_id"]
            sid = num_to_str.get(nid)
            if sid not in i1_set:
                continue
            prefix = f"ind{nid}"
            lift_raw = res_raw["per_indicator_lift"].get(prefix, 0.0)
            lift_diff = res_diff["per_indicator_lift"].get(prefix, 0.0)
            per_ind_compare.append({
                "indicator_id_string": sid,
                "indicator_name": entry.get("indicator_name", "?"),
                "lift_raw": lift_raw,
                "lift_diff": lift_diff,
                "delta": lift_diff - lift_raw,
                "ratio": (lift_diff / lift_raw) if lift_raw > 1e-9 else None,
            })

        results.append({
            "event_category": cat,
            "n_total_features": len(cols_raw),
            "i1_in_fingerprint": i1_in_fp,
            "auc_raw": res_raw["test_auc"],
            "auc_diff": res_diff["test_auc"],
            "n_train": res_raw["n_train"],
            "n_test": res_raw["n_test"],
            "per_i1_indicator": per_ind_compare,
        })

    # Aggregate
    summary = {
        "audit_date": audit_date,
        "n_recipes_evaluated": len(results),
        "selected_recipes": SELECTED_RECIPES,
        "cutoff_year": CUTOFF_YEAR,
        "canonical_length": CANONICAL_LENGTH,
        "results": results,
    }

    json_path = args.output_dir / "lift_prototype.json"
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # Markdown
    md = []
    md.append(f"# Lean Lift Comparison: RAW vs DIFF (#585) — {audit_date}\n")
    md.append("**Question:** When we apply first-differencing to I(1) indicators in feature construction, does GENUINE predictive signal survive (lift preserved) or COLLAPSE (lift kills)?\n")
    md.append(f"**Setup:** {len(SELECTED_RECIPES)} recipes, cutoff year {CUTOFF_YEAR}, canonical length {CANONICAL_LENGTH}, GBM + permutation importance.\n")

    md.append("\n## Per-recipe AUC summary\n")
    md.append("| Recipe | I(1) in fp | n_total_feat | RAW AUC | DIFF AUC | Δ AUC |")
    md.append("|---|---|---|---|---|---|")
    for r in results:
        d = r["auc_diff"] - r["auc_raw"]
        md.append(f"| {r['event_category']} | {r['i1_in_fingerprint']} | {r['n_total_features']} | "
                  f"{r['auc_raw']:.3f} | {r['auc_diff']:.3f} | **{d:+.3f}** |")

    md.append("\n## Per-(recipe × I(1)-indicator) lift comparison\n")
    md.append("| Recipe | Indicator | Lift RAW | Lift DIFF | Δ | Ratio (DIFF/RAW) |")
    md.append("|---|---|---|---|---|---|")
    for r in results:
        for p in r["per_i1_indicator"]:
            ratio_str = f"{p['ratio']:.2f}" if p['ratio'] is not None else "—"
            md.append(f"| {r['event_category']} | {p['indicator_name']} ({p['indicator_id_string']}) | "
                      f"{p['lift_raw']:.4f} | {p['lift_diff']:.4f} | "
                      f"{p['delta']:+.4f} | {ratio_str} |")

    md.append("\n## Interpretation\n")
    md.append("- **AUC change near zero** = detrending preserves overall recipe predictiveness")
    md.append("- **Per-indicator lift collapsing to ~0 under DIFF** = that indicator's lift was substrate-driven; detrending correctly removes spurious contribution")
    md.append("- **Per-indicator lift preserved under DIFF** = genuine signal survives; detrending didn't kill the indicator's predictive value")
    md.append("- **Per-indicator lift INCREASED under DIFF** = surprising; possibly the trend was masking change-driven signal")
    md.append("\nThis is a 5-recipe lean prototype; full validation needs the heavy version (full auditioner with `--detrend-method first-diff` across the entire ~72-recipe corpus).")

    md_path = args.output_dir / "lift_prototype.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(f"\n[output] {json_path}")
    print(f"[output] {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
