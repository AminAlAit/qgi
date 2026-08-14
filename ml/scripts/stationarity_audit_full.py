#!/usr/bin/env python3
"""
stationarity_audit_full.py — Phase 0c: extend audit to ALL indicators.

Same CIPS protocol as stationarity_audit.py (#582 Phase 0a) but discovers
indicators dynamically from qgi_data.indicators with N >= MIN_COUNTRIES
and T >= MIN_YEARS. Outputs combined report.

Cost: ~$1-5 Athena.
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
import statsmodels.api as sm

CIPS_CRIT_5PCT = -2.11
CIPS_CRIT_10PCT = -2.03
CIPS_CRIT_1PCT = -2.27

MIN_COUNTRIES = 20
MIN_YEARS = 15


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


def discover_indicators(ath, bucket, workgroup):
    """Return list of {id, n_countries, n_years} for indicators with sufficient data."""
    sql = f"""
    SELECT indicator_id,
           COUNT(DISTINCT country) AS n_countries,
           MAX(year) - MIN(year) + 1 AS t_span,
           COUNT(*) AS n_obs
    FROM qgi_data.indicators
    WHERE value IS NOT NULL
    GROUP BY indicator_id
    HAVING COUNT(DISTINCT country) >= {MIN_COUNTRIES}
       AND MAX(year) - MIN(year) + 1 >= {MIN_YEARS}
    ORDER BY indicator_id
    """
    print("[athena] discovering indicators with sufficient panel coverage...")
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    out = []
    for r in rows:
        out.append({
            "id": r[0], "n_countries": int(r[1]), "t_span": int(r[2]), "n_obs": int(r[3]),
        })
    return out


def fetch_panel(ath, bucket, workgroup, indicator_ids, batch_size=50):
    """Fetch all panels in batches to keep individual queries manageable."""
    all_dfs = []
    for i in range(0, len(indicator_ids), batch_size):
        batch = indicator_ids[i:i + batch_size]
        in_clause = ",".join(f"'{i}'" for i in batch)
        sql = f"""
        SELECT country, year, indicator_id, value
        FROM qgi_data.indicators
        WHERE indicator_id IN ({in_clause})
          AND value IS NOT NULL
        """
        print(f"[athena] batch {i//batch_size + 1}: fetching {len(batch)} indicators...")
        qid = run_athena(ath, sql, bucket, workgroup)
        rows = athena_fetch_all(ath, qid)
        if not rows:
            continue
        df = pd.DataFrame(rows, columns=["country", "year", "indicator_id", "value"])
        df["year"] = df["year"].astype(int)
        df["value"] = df["value"].astype(float)
        all_dfs.append(df)
    return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()


def compute_cadf(country_series, cs_mean_series, lags=0):
    df = pd.DataFrame({"y": country_series, "cs_mean": cs_mean_series}).dropna()
    if len(df) < 6:
        return None
    df["dy"] = df["y"].diff()
    df["y_lag"] = df["y"].shift(1)
    df["cs_mean_lag"] = df["cs_mean"].shift(1)
    df["dcs_mean"] = df["cs_mean"].diff()
    for j in range(1, lags + 1):
        df[f"dy_lag{j}"] = df["dy"].shift(j)
    df = df.dropna()
    if len(df) < 5:
        return None
    cols = ["y_lag", "cs_mean_lag", "dcs_mean"] + [f"dy_lag{j}" for j in range(1, lags + 1)]
    X = sm.add_constant(df[cols])
    y = df["dy"]
    try:
        model = sm.OLS(y, X).fit()
        return float(model.tvalues["y_lag"])
    except Exception:
        return None


def compute_cips(panel_wide, lags=0):
    cs_means = panel_wide.mean(axis=1)
    cadfs = []
    for country in panel_wide.columns:
        cadf = compute_cadf(panel_wide[country], cs_means, lags=lags)
        if cadf is not None and not np.isnan(cadf):
            cadfs.append(cadf)
    if len(cadfs) < 5:
        return None, len(cadfs), len(panel_wide)
    return float(np.mean(cadfs)), len(cadfs), len(panel_wide)


def classify(cips):
    if cips is None:
        return "INSUFFICIENT_DATA"
    if cips < CIPS_CRIT_1PCT:
        return "STATIONARY"  # at 1%
    if cips < CIPS_CRIT_5PCT:
        return "STATIONARY"  # at 5%
    if cips < CIPS_CRIT_10PCT:
        return "MARGINAL"
    return "I(1)"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bucket", required=True)
    p.add_argument("--workgroup", default="QGI-Lambda-Workgroup")
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ath = boto3.client("athena", region_name=args.region)

    # Discovery
    indicators = discover_indicators(ath, args.bucket, args.workgroup)
    print(f"[discovery] {len(indicators)} indicators with N >= {MIN_COUNTRIES}, T >= {MIN_YEARS}")

    # Fetch panels
    indicator_ids = [d["id"] for d in indicators]
    panel = fetch_panel(ath, args.bucket, args.workgroup, indicator_ids)
    print(f"[data] {len(panel):,} rows total")

    # Run CIPS per indicator
    results = []
    for i, spec in enumerate(indicators, 1):
        ind_id = spec["id"]
        sub = panel[panel["indicator_id"] == ind_id]
        if sub.empty:
            continue
        wide = sub.pivot_table(index="year", columns="country",
                               values="value", aggfunc="mean").sort_index()
        cips, n, t = compute_cips(wide)
        verdict = classify(cips)
        cips_str = f"{cips:.3f}" if cips is not None else "NA"
        print(f"  [{i:3d}/{len(indicators)}] {ind_id:25s} CIPS={cips_str:>7s}  N={n:3d} T={t:3d}  -> {verdict}")
        results.append({
            "indicator_id": ind_id,
            "n_countries": int(n),
            "t_years": int(t),
            "n_obs_total": spec["n_obs"],
            "cips": cips,
            "verdict": verdict,
        })

    # Aggregate
    n_total = len(results)
    n_i1 = sum(1 for r in results if r["verdict"] == "I(1)")
    n_marginal = sum(1 for r in results if r["verdict"] == "MARGINAL")
    n_stationary = sum(1 for r in results if r["verdict"] == "STATIONARY")
    n_insuff = sum(1 for r in results if r["verdict"] == "INSUFFICIENT_DATA")
    n_evaluable = n_total - n_insuff
    pct_i1 = (n_i1 + n_marginal) / n_evaluable * 100 if n_evaluable else 0.0

    if pct_i1 < 10:
        agg_verdict = "CHEAP_PATH"
    elif pct_i1 < 20:
        agg_verdict = "TARGETED_RECOMPUTATION"
    else:
        agg_verdict = "FULL_AUDIT_CONFIRMED"

    report = {
        "audit_date": audit_date,
        "phase": "0c (full)",
        "n_indicators_total": n_total,
        "n_evaluable": n_evaluable,
        "n_i1": n_i1,
        "n_marginal": n_marginal,
        "n_stationary": n_stationary,
        "n_insufficient": n_insuff,
        "pct_i1_or_marginal": round(pct_i1, 1),
        "aggregate_verdict": agg_verdict,
        "per_indicator": results,
    }
    json_path = args.output_dir / "stationarity_full_report.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    md = []
    md.append(f"# SCDI Stationarity Audit — FULL (Phase 0c) — {audit_date}\n")
    md.append("**Test:** CIPS (Pesaran 2007), case II (intercept, no trend)")
    md.append(f"**Indicators audited:** {n_total} (N >= {MIN_COUNTRIES} countries, T >= {MIN_YEARS} years)")
    md.append("\n## Aggregate verdict\n")
    md.append(f"- **Stationary:** {n_stationary}")
    md.append(f"- **Marginal:** {n_marginal}")
    md.append(f"- **I(1):** {n_i1}")
    md.append(f"- **Insufficient data:** {n_insuff}")
    md.append(f"- **% I(1) or marginal:** {pct_i1:.1f}%")
    md.append(f"- **Verdict:** **{agg_verdict}**")
    md.append("\n## I(1) indicators (need detrending in #585)\n")
    md.append("| Indicator | CIPS | N | T |")
    md.append("|---|---|---|---|")
    for r in sorted(results, key=lambda x: (x["verdict"], x["cips"] or 999)):
        if r["verdict"] != "I(1)":
            continue
        cips_str = f"{r['cips']:.3f}" if r["cips"] is not None else "—"
        md.append(f"| {r['indicator_id']} | {cips_str} | {r['n_countries']} | {r['t_years']} |")

    md.append("\n## MARGINAL indicators\n")
    md.append("| Indicator | CIPS | N | T |")
    md.append("|---|---|---|---|")
    for r in sorted(results, key=lambda x: x["cips"] or 999):
        if r["verdict"] != "MARGINAL":
            continue
        cips_str = f"{r['cips']:.3f}" if r["cips"] is not None else "—"
        md.append(f"| {r['indicator_id']} | {cips_str} | {r['n_countries']} | {r['t_years']} |")

    md.append("\n## STATIONARY indicators (no detrending needed)\n")
    md.append("| Indicator | CIPS | N | T |")
    md.append("|---|---|---|---|")
    for r in sorted(results, key=lambda x: x["cips"] or 999):
        if r["verdict"] != "STATIONARY":
            continue
        cips_str = f"{r['cips']:.3f}" if r["cips"] is not None else "—"
        md.append(f"| {r['indicator_id']} | {cips_str} | {r['n_countries']} | {r['t_years']} |")

    md_path = args.output_dir / "stationarity_full_report.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(f"\n[output] {json_path}")
    print(f"[output] {md_path}")
    print()
    print("=" * 70)
    print(f"AGGREGATE VERDICT: {agg_verdict}")
    print(f"% I(1) or marginal: {pct_i1:.1f}%  ({n_i1 + n_marginal} of {n_evaluable})")
    print(f"Confirmed I(1): {n_i1}  -- this is the #585 detrending scope")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
