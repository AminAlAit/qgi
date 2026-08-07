#!/usr/bin/env python3
"""
stationarity_audit.py — Phase 0 SCDI panel stationarity audit (#582).

CIPS test (Pesaran 2007, Cross-sectionally Augmented IPS) on a 20-indicator
sample to determine whether the auditioner's predictive_lift terms are
contaminated by spurious correlations from non-stationary (I(1)) series.

Per Tariq Farouk-Lindgren (#20) protocol from Majles Al Ihsa I1 (2026-05-02):
  - Sample: 20 indicators spanning all sectors (founder-approved)
  - Test: CIPS (cross-sectionally augmented IPS) accounts for cross-sectional
    dependence which standard IPS does not — critical for cross-country panels
    sharing common factors (post-war development, globalisation, etc.)
  - Acceptance gate:
      <10% I(1) -> cheap path; proceed to #583 EB
      10-20% I(1) -> targeted lift recomputation per affected indicator
      >20% I(1) -> full audit on remaining 84 indicators before #577 ships

Decision file:
  docs/specs/internal/majles/2026-05-02_Ihsa_577_scope_broadening.md

Usage:
  python scripts/stationarity_audit.py \\
      --bucket qgi-data-lake-771606957899 \\
      --workgroup QGI-Lambda-Workgroup \\
      --output-dir results/stationarity_audit_2026_05_02/

Cost: ~$5 Athena (single panel scan + indicator_map fetch).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import numpy as np
import pandas as pd
import statsmodels.api as sm


# 20-indicator sample (founder-approved 2026-05-02)
# Maps display label -> indicator_id_string used in qgi_data.indicators
SAMPLE_INDICATORS = [
    # WB demographic — D3 substrate dominators (must include)
    {"label": "Population, total",                         "id": "SP.POP.TOTL",        "sector": "WB-demographic", "expected": "I(1)"},
    {"label": "Life expectancy at birth",                  "id": "SP.DYN.LE00.IN",     "sector": "WB-demographic", "expected": "I(1)"},
    {"label": "Mortality rate, under-5",                   "id": "SH.DYN.MORT",        "sector": "WB-demographic", "expected": "I(1)"},
    # WB economic
    {"label": "GDP per capita (current USD)",              "id": "NY.GDP.PCAP.CD",     "sector": "WB-economic",    "expected": "I(1)"},
    {"label": "GDP (constant 2015 USD)",                   "id": "NY.GDP.MKTP.KD",     "sector": "WB-economic",    "expected": "I(1)"},
    {"label": "GDP (current USD)",                         "id": "NY.GDP.MKTP.CD",     "sector": "WB-economic",    "expected": "I(1)"},
    {"label": "GNI per capita Atlas",                      "id": "NY.GNP.PCAP.CD",     "sector": "WB-economic",    "expected": "I(1)"},
    # WB infrastructure
    {"label": "Mobile cellular subscriptions (per 100)",   "id": "IT.CEL.SETS.P2",     "sector": "WB-infra",       "expected": "I(1) capped"},
    # V-Dem political (pre-screen #550)
    {"label": "V-Dem polyarchy",                           "id": "v2x_polyarchy",      "sector": "V-Dem",          "expected": "I(1)"},
    {"label": "V-Dem liberal democracy",                   "id": "v2x_libdem",         "sector": "V-Dem",          "expected": "I(1)"},
    {"label": "V-Dem state fiscal capacity",               "id": "v2stfisccap",        "sector": "V-Dem",          "expected": "?"},
    {"label": "V-Dem control of corruption",               "id": "v2x_corr",           "sector": "V-Dem",          "expected": "I(1)"},
    # WB trade
    {"label": "Exports of goods/services (current USD)",   "id": "NE.EXP.GNFS.CD",     "sector": "WB-trade",       "expected": "I(1)"},
    {"label": "Imports of goods/services (current USD)",   "id": "NE.IMP.GNFS.CD",     "sector": "WB-trade",       "expected": "I(1)"},
    # FAOSTAT
    {"label": "Food production index",                     "id": "AG.PRD.FOOD.XD",     "sector": "FAOSTAT",        "expected": "mixed"},
    # UCDP / conflict (stationary controls)
    {"label": "UCDP best-estimate battle deaths",          "id": "UCDP_BD_BEST",       "sector": "UCDP",           "expected": "stationary"},
    {"label": "UCDP onset of armed conflict (binary)",     "id": "UCDP_ONSET",         "sector": "UCDP",           "expected": "stationary"},
    # WB stationary controls
    {"label": "Inflation, consumer prices (annual %)",     "id": "FP.CPI.TOTL.ZG",     "sector": "WB-economic",    "expected": "stationary"},
    {"label": "Unemployment, total (% labor force)",       "id": "SL.UEM.TOTL.ZS",     "sector": "WB-economic",    "expected": "stationary"},
    {"label": "Tax revenue (% GDP)",                       "id": "GC.TAX.TOTL.GD.ZS",  "sector": "WB-fiscal",      "expected": "stationary"},
]

# Pesaran (2007) Table II.b — CIPS critical values (case II: intercept, no trend)
# Approximate truncated values for large N; we'll use these as the gate.
# Format: {alpha: critical_value}
# For T ≥ 30, N -> ∞: 5% ≈ -2.11; 10% ≈ -2.03; 1% ≈ -2.27
CIPS_CRIT_5PCT = -2.11
CIPS_CRIT_10PCT = -2.03
CIPS_CRIT_1PCT = -2.27


def run_athena(ath, sql, bucket, workgroup, db="qgi_data"):
    r = ath.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": db},
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


def fetch_panel(ath, bucket, workgroup, indicator_ids):
    """Long-format (country, year, indicator_id, value) for the sample."""
    in_clause = ",".join(f"'{i}'" for i in indicator_ids)
    sql = f"""
    SELECT country, year, indicator_id, value
    FROM qgi_data.indicators
    WHERE indicator_id IN ({in_clause})
      AND value IS NOT NULL
    """
    print(f"[athena] fetching panels for {len(indicator_ids)} indicators...")
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    df = pd.DataFrame(rows, columns=["country", "year", "indicator_id", "value"])
    df["year"] = df["year"].astype(int)
    df["value"] = df["value"].astype(float)
    return df


def compute_cadf(country_series, cs_mean_series, lags=0):
    """
    CADF regression for one country (Pesaran 2007):
        Δy_t = α + β·y_{t-1} + γ·ȳ_{t-1} + δ·Δȳ_t + Σψ_j Δy_{t-j} + ε_t
    Returns t-stat on β (the unit-root coefficient).

    NaN-safe; returns None if too few obs (< 6).
    """
    df = pd.DataFrame({"y": country_series, "cs_mean": cs_mean_series}).dropna()
    if len(df) < 6:
        return None

    df["dy"] = df["y"].diff()
    df["y_lag"] = df["y"].shift(1)
    df["cs_mean_lag"] = df["cs_mean"].shift(1)
    df["dcs_mean"] = df["cs_mean"].diff()

    # Optional lagged Δy_{t-j} terms
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
    """
    panel_wide: DataFrame, rows=year, columns=country, values=indicator value.
    Returns (CIPS, n_countries_used, t_used).
    """
    cs_means = panel_wide.mean(axis=1)
    cadfs = []
    for country in panel_wide.columns:
        cadf = compute_cadf(panel_wide[country], cs_means, lags=lags)
        if cadf is not None and not np.isnan(cadf):
            cadfs.append(cadf)
    if len(cadfs) < 5:
        return None, len(cadfs), len(panel_wide)
    return float(np.mean(cadfs)), len(cadfs), len(panel_wide)


def classify(cips, n, t):
    """Classify per-indicator stationarity verdict."""
    if cips is None:
        return "INSUFFICIENT_DATA", "Too few countries with usable series (N<5)"
    if cips < CIPS_CRIT_1PCT:
        return "STATIONARY", f"CIPS={cips:.3f} < 1% crit ({CIPS_CRIT_1PCT}); reject unit-root null at 1%"
    if cips < CIPS_CRIT_5PCT:
        return "STATIONARY", f"CIPS={cips:.3f} < 5% crit ({CIPS_CRIT_5PCT}); reject unit-root null at 5%"
    if cips < CIPS_CRIT_10PCT:
        return "MARGINAL", f"CIPS={cips:.3f} < 10% crit ({CIPS_CRIT_10PCT}); reject at 10% only — borderline"
    return "I(1)", f"CIPS={cips:.3f} ≥ 10% crit ({CIPS_CRIT_10PCT}); fail to reject unit-root null"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", required=True)
    p.add_argument("--workgroup", default="QGI-Lambda-Workgroup")
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--lags", type=int, default=0,
                   help="Lagged Δy terms in CADF regression (0 = pure CIPS)")
    args = p.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    ath = boto3.client("athena", region_name=args.region)

    indicator_ids = [s["id"] for s in SAMPLE_INDICATORS]
    panel = fetch_panel(ath, args.bucket, args.workgroup, indicator_ids)
    print(f"[data] {len(panel):,} rows, "
          f"{panel['indicator_id'].nunique()} distinct indicators returned, "
          f"{panel['country'].nunique()} countries")

    results = []
    for spec in SAMPLE_INDICATORS:
        ind_id = spec["id"]
        sub = panel[panel["indicator_id"] == ind_id]
        if sub.empty:
            results.append({
                **spec,
                "n_countries": 0,
                "t_years": 0,
                "cips": None,
                "verdict": "INSUFFICIENT_DATA",
                "rationale": "Indicator not present in qgi_data.indicators (likely not yet ingested)",
            })
            print(f"  {ind_id:25s} -> SKIP (not in data)")
            continue

        wide = sub.pivot_table(index="year", columns="country",
                               values="value", aggfunc="mean").sort_index()
        cips, n, t = compute_cips(wide, lags=args.lags)
        verdict, rationale = classify(cips, n, t)
        results.append({
            **spec,
            "n_countries": int(n),
            "t_years": int(t),
            "cips": cips,
            "verdict": verdict,
            "rationale": rationale,
        })
        cips_str = f"{cips:.3f}" if cips is not None else "—"
        print(f"  {ind_id:25s} CIPS={cips_str:>7s}  N={n:3d} T={t:3d}  -> {verdict}")

    # Aggregate verdict
    n_total = len(results)
    n_i1 = sum(1 for r in results if r["verdict"] == "I(1)")
    n_marginal = sum(1 for r in results if r["verdict"] == "MARGINAL")
    n_stationary = sum(1 for r in results if r["verdict"] == "STATIONARY")
    n_skip = sum(1 for r in results if r["verdict"] == "INSUFFICIENT_DATA")

    n_evaluable = n_total - n_skip
    pct_i1 = (n_i1 + n_marginal) / n_evaluable * 100 if n_evaluable else 0.0

    if pct_i1 < 10:
        agg_verdict = "CHEAP_PATH"
        agg_action = "Proceed to #583 EB hyperprior estimation. Lift validity acceptable."
    elif pct_i1 < 20:
        agg_verdict = "TARGETED_RECOMPUTATION"
        agg_action = (
            "Spawn #585: recompute lift on first-differenced/detrended residuals "
            "for the I(1) and MARGINAL indicators only. Then proceed to #583."
        )
    else:
        agg_verdict = "FULL_AUDIT"
        agg_action = (
            "Extend audit to remaining ~84 indicators before #577 production. "
            "#585 detrending engineering required for all I(1) confirmed."
        )

    report = {
        "audit_date": audit_date,
        "sample_size": n_total,
        "n_evaluable": n_evaluable,
        "n_i1": n_i1,
        "n_marginal": n_marginal,
        "n_stationary": n_stationary,
        "n_skip": n_skip,
        "pct_i1_or_marginal": round(pct_i1, 1),
        "aggregate_verdict": agg_verdict,
        "aggregate_action": agg_action,
        "cips_critical_5pct": CIPS_CRIT_5PCT,
        "cips_critical_10pct": CIPS_CRIT_10PCT,
        "per_indicator": results,
    }

    json_path = args.output_dir / "stationarity_report.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[output] wrote {json_path}")

    # Markdown report
    md = []
    md.append(f"# SCDI Panel Stationarity Audit — {audit_date}")
    md.append("\n**Test:** CIPS (Pesaran 2007 Cross-sectionally Augmented IPS), case II (intercept, no trend)")
    md.append(f"**Critical values:** 5% = {CIPS_CRIT_5PCT}, 10% = {CIPS_CRIT_10PCT}, 1% = {CIPS_CRIT_1PCT}")
    md.append(f"**CADF lags:** {args.lags}")
    md.append("\n## Aggregate verdict\n")
    md.append(f"- **Sample size:** {n_total} indicators ({n_evaluable} evaluable, {n_skip} not in data)")
    md.append(f"- **Stationary (PASS):** {n_stationary}")
    md.append(f"- **Marginal:** {n_marginal}")
    md.append(f"- **I(1) (FAIL):** {n_i1}")
    md.append(f"- **% I(1) or marginal:** {pct_i1:.1f}%")
    md.append(f"- **Verdict:** **{agg_verdict}**")
    md.append(f"- **Action:** {agg_action}")
    md.append("\n## Per-indicator results\n")
    md.append("| Indicator | Sector | A priori | N | T | CIPS | Verdict |")
    md.append("|---|---|---|---|---|---|---|")
    for r in results:
        cips_str = f"{r['cips']:.3f}" if r["cips"] is not None else "—"
        md.append(f"| {r['label']} | {r['sector']} | {r['expected']} | "
                  f"{r['n_countries']} | {r['t_years']} | {cips_str} | **{r['verdict']}** |")
    md.append("\n## Methodology notes\n")
    md.append("- **CIPS:** average of country-level CADF t-statistics on the lag-y coefficient")
    md.append("- **CADF:** Δy_{i,t} = α + β·y_{i,t-1} + γ·ȳ_{t-1} + δ·Δȳ_t + ε_{i,t}")
    md.append("- **Cross-sectional augmentation** absorbs the common factor that makes naive IPS oversized")
    md.append("- **Stationary** = reject unit-root null at 5%")
    md.append("- **Marginal** = reject only at 10% (treat as contamination risk)")
    md.append("- **I(1)** = fail to reject — series treated as non-stationary, lift contamination likely")
    md.append("- **Acceptance gate** (Tariq #20 protocol from Ihsa I1):")
    md.append("    - <10% I(1) -> CHEAP_PATH (proceed)")
    md.append("    - 10-20% -> TARGETED_RECOMPUTATION (spawn #585)")
    md.append("    - >20% -> FULL_AUDIT (extend to remaining 84 indicators)")
    md.append("\n## Per-indicator rationale\n")
    for r in results:
        md.append(f"- **{r['label']}** ({r['id']}): {r['rationale']}")

    md_path = args.output_dir / "stationarity_report.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(f"[output] wrote {md_path}")

    # Banner
    print("\n" + "=" * 60)
    print(f"AGGREGATE VERDICT: {agg_verdict}")
    print(f"% I(1) or marginal: {pct_i1:.1f}% (founder predicted ≥36%)")
    print(f"Action: {agg_action}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
