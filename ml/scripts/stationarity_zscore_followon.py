#!/usr/bin/env python3
"""
stationarity_zscore_followon.py — Phase 0b follow-on for #582.

Question: Does QGI's within-segment Z-scoring + the M2=0.75 SCDI cut effectively
mitigate the spurious-correlation problem from I(1) indicators?

Approach: For each confirmed I(1) indicator from #582, simulate the empirical
distribution of |Pearson r| on random country-pair × random-window-start tuples
with QGI's typical segment lengths (15, 25, 35 years). Z-score each window
the way the SCDI framework does. Report the fraction with |r| ≥ 0.75 — that's
the spurious-pass-through rate of the M2 cut for this indicator.

Interpretation:
  - HIGH (>30%): M2=0.75 doesn't meaningfully filter spurious I(1) correlations.
    #585 detrending engineering required.
  - MEDIUM (10-30%): Partial filtering. Targeted detrending recommended for
    the worst offenders.
  - LOW (<10%): Z-scoring + M2 substantially fixes the issue empirically.
    #585 may be unnecessary; lift validity acceptable as-is.

Usage:
  python scripts/stationarity_zscore_followon.py \\
      --bucket qgi-data-lake-771606957899 \\
      --workgroup QGI-Lambda-Workgroup \\
      --output-dir results/stationarity_audit_2026_05_02/ \\
      --n-samples 2000

Cost: ~$1-2 Athena (single panel scan for the ~10 I(1) indicators).
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


# Confirmed I(1) and MARGINAL indicators from #582 (2026-05-02)
I1_INDICATORS = [
    {"id": "SP.POP.TOTL",        "label": "Population, total",         "verdict": "I(1)"},
    {"id": "NY.GDP.PCAP.CD",     "label": "GDP per capita",            "verdict": "I(1)"},
    {"id": "NY.GDP.MKTP.KD",     "label": "GDP (constant USD)",        "verdict": "I(1)"},
    {"id": "NY.GDP.MKTP.CD",     "label": "GDP (current USD)",         "verdict": "I(1)"},
    {"id": "NY.GNP.PCAP.CD",     "label": "GNI per capita",            "verdict": "I(1)"},
    {"id": "IT.CEL.SETS.P2",     "label": "Mobile subscriptions /100", "verdict": "I(1)"},
    {"id": "v2x_corr",           "label": "V-Dem control of corruption","verdict": "I(1)"},
    {"id": "NE.EXP.GNFS.CD",     "label": "Exports",                   "verdict": "I(1)"},
    {"id": "NE.IMP.GNFS.CD",     "label": "Imports",                   "verdict": "I(1)"},
    {"id": "SL.UEM.TOTL.ZS",     "label": "Unemployment %",            "verdict": "I(1)"},
    {"id": "GC.TAX.TOTL.GD.ZS",  "label": "Tax revenue %GDP",          "verdict": "MARGINAL"},
]

# Segment lengths to test — span QGI's typical SCDI window range (per README.md TIERS)
SEGMENT_LENGTHS = [15, 25, 35]

# M2 cut threshold (the founder's chosen SCDI hard cut)
M2_THRESHOLD = 0.75


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


def fetch_panel(ath, bucket, workgroup, indicator_ids):
    in_clause = ",".join(f"'{i}'" for i in indicator_ids)
    sql = f"""
    SELECT country, year, indicator_id, value
    FROM qgi_data.indicators
    WHERE indicator_id IN ({in_clause})
      AND value IS NOT NULL
    """
    print(f"[athena] fetching panels for {len(indicator_ids)} I(1) indicators...")
    qid = run_athena(ath, sql, bucket, workgroup)
    rows = athena_fetch_all(ath, qid)
    df = pd.DataFrame(rows, columns=["country", "year", "indicator_id", "value"])
    df["year"] = df["year"].astype(int)
    df["value"] = df["value"].astype(float)
    return df


def zscore_segment(arr):
    """Z-score a fixed-length window (this is what QGI's SCDI pipeline does)."""
    mu = np.mean(arr)
    sd = np.std(arr, ddof=0)
    if sd < 1e-9:
        return None
    return (arr - mu) / sd


def sample_correlations(panel_wide, segment_length, n_samples, rng):
    """
    For one indicator's wide panel (rows=year, cols=country):
    sample n_samples random (country_a, country_b, window_start) tuples,
    Z-score each window, compute |Pearson r|.

    Returns array of |r| values.
    """
    countries = list(panel_wide.columns)
    years = panel_wide.index.values
    n_countries = len(countries)
    n_years = len(years)
    if n_countries < 2 or n_years < segment_length + 1:
        return np.array([])

    rs = []
    attempts = 0
    max_attempts = n_samples * 5  # allow up to 5x attempts to find valid pairs

    while len(rs) < n_samples and attempts < max_attempts:
        attempts += 1
        # Pick two distinct countries
        ia, ib = rng.choice(n_countries, size=2, replace=False)
        ca, cb = countries[ia], countries[ib]
        # Pick a window start
        max_start = n_years - segment_length
        start = rng.integers(0, max_start + 1)
        # Extract windows
        wa = panel_wide[ca].iloc[start:start + segment_length].to_numpy()
        wb = panel_wide[cb].iloc[start:start + segment_length].to_numpy()
        # Need both windows fully populated (no NaN)
        if np.any(np.isnan(wa)) or np.any(np.isnan(wb)):
            continue
        # Z-score each window
        za = zscore_segment(wa)
        zb = zscore_segment(wb)
        if za is None or zb is None:
            continue
        # Pearson r between Z-scored windows
        try:
            r = float(np.corrcoef(za, zb)[0, 1])
        except Exception:
            continue
        if np.isnan(r):
            continue
        rs.append(abs(r))

    return np.array(rs)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", required=True)
    p.add_argument("--workgroup", default="QGI-Lambda-Workgroup")
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--n-samples", type=int, default=2000,
                   help="Number of random country-pair × window-start samples per (indicator, length)")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rng = np.random.default_rng(args.seed)
    ath = boto3.client("athena", region_name=args.region)

    indicator_ids = [s["id"] for s in I1_INDICATORS]
    panel = fetch_panel(ath, args.bucket, args.workgroup, indicator_ids)
    print(f"[data] {len(panel):,} rows across {panel['indicator_id'].nunique()} indicators")

    results = []
    for spec in I1_INDICATORS:
        ind_id = spec["id"]
        sub = panel[panel["indicator_id"] == ind_id]
        if sub.empty:
            print(f"  {ind_id:25s} -> SKIP (no data)")
            continue
        wide = sub.pivot_table(index="year", columns="country",
                               values="value", aggfunc="mean").sort_index()
        for L in SEGMENT_LENGTHS:
            rs = sample_correlations(wide, L, args.n_samples, rng)
            if len(rs) == 0:
                continue
            frac_above_05 = float(np.mean(rs >= 0.5))
            frac_above_075 = float(np.mean(rs >= M2_THRESHOLD))
            frac_above_09 = float(np.mean(rs >= 0.9))
            mean_r = float(np.mean(rs))
            median_r = float(np.median(rs))
            p95_r = float(np.percentile(rs, 95))
            results.append({
                "indicator_id": ind_id,
                "label": spec["label"],
                "verdict": spec["verdict"],
                "segment_length": L,
                "n_valid_samples": int(len(rs)),
                "mean_abs_r": mean_r,
                "median_abs_r": median_r,
                "p95_abs_r": p95_r,
                "frac_above_0.5": frac_above_05,
                "frac_above_0.75": frac_above_075,  # the M2 threshold
                "frac_above_0.9": frac_above_09,
            })
            print(f"  {ind_id:25s} L={L:2d}  n={len(rs)}  "
                  f"mean|r|={mean_r:.3f}  p95={p95_r:.3f}  "
                  f"%>0.75={frac_above_075*100:5.1f}%")

    # Aggregate verdict per indicator (worst case across segment lengths)
    print()
    print("=" * 70)
    print("Aggregate per-indicator (worst-case across L=15/25/35):")
    print("=" * 70)
    by_indicator = {}
    for r in results:
        ind_id = r["indicator_id"]
        if ind_id not in by_indicator:
            by_indicator[ind_id] = []
        by_indicator[ind_id].append(r)

    indicator_verdicts = []
    for ind_id, rows in by_indicator.items():
        worst_above_075 = max(r["frac_above_0.75"] for r in rows)
        spec = next(s for s in I1_INDICATORS if s["id"] == ind_id)
        if worst_above_075 < 0.10:
            verdict_local = "M2_FILTERS_EFFECTIVELY"
        elif worst_above_075 < 0.30:
            verdict_local = "PARTIAL"
        else:
            verdict_local = "M2_DOES_NOT_FILTER"
        indicator_verdicts.append({
            "indicator_id": ind_id,
            "label": spec["label"],
            "worst_frac_above_0.75": worst_above_075,
            "verdict": verdict_local,
        })
        print(f"  {ind_id:25s} worst %>0.75 = {worst_above_075*100:5.1f}%  -> {verdict_local}")

    # Aggregate across all indicators
    overall_worst = max(v["worst_frac_above_0.75"] for v in indicator_verdicts)
    overall_mean = float(np.mean([v["worst_frac_above_0.75"] for v in indicator_verdicts]))
    n_indicators_failing = sum(1 for v in indicator_verdicts if v["verdict"] == "M2_DOES_NOT_FILTER")
    n_indicators_partial = sum(1 for v in indicator_verdicts if v["verdict"] == "PARTIAL")
    n_indicators_filtered = sum(1 for v in indicator_verdicts if v["verdict"] == "M2_FILTERS_EFFECTIVELY")

    if overall_worst < 0.10:
        overall_verdict = "M2_FILTERS_EFFECTIVELY"
        action = "Z-scoring + 0.75 cut substantially fix the unit-root contamination empirically. #585 detrending may be unnecessary."
    elif overall_worst < 0.30:
        overall_verdict = "PARTIAL"
        action = "Z-scoring + 0.75 cut partially mitigate. #585 detrending recommended for the worst offenders only."
    else:
        overall_verdict = "M2_DOES_NOT_FILTER"
        action = "Z-scoring + 0.75 cut do NOT effectively filter spurious I(1) correlations. #585 detrending engineering required for confirmed I(1) indicators."

    report = {
        "audit_date": audit_date,
        "n_samples_per_combo": args.n_samples,
        "segment_lengths": SEGMENT_LENGTHS,
        "m2_threshold": M2_THRESHOLD,
        "per_indicator_per_length": results,
        "indicator_verdicts": indicator_verdicts,
        "overall_worst_frac_above_0.75": overall_worst,
        "overall_mean_frac_above_0.75": overall_mean,
        "overall_verdict": overall_verdict,
        "overall_action": action,
        "n_indicators_filtered": n_indicators_filtered,
        "n_indicators_partial": n_indicators_partial,
        "n_indicators_failing": n_indicators_failing,
    }

    json_path = args.output_dir / "zscore_followon_report.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    md = []
    md.append(f"# SCDI Z-score + 0.75 Filter Empirical Test — {audit_date}")
    md.append("\n**Question:** Does QGI's within-segment Z-scoring + the M2=0.75 SCDI cut")
    md.append("effectively filter out spurious correlations from confirmed I(1) indicators?")
    md.append(f"\n**Method:** For each I(1) indicator, sample {args.n_samples} random")
    md.append(f"(country_A, country_B, window_start) tuples with segment lengths L ∈ {SEGMENT_LENGTHS}.")
    md.append("Z-score each window. Compute |Pearson r|. Report fraction with |r| ≥ 0.75.")
    md.append("\n## Aggregate verdict\n")
    md.append(f"- **Overall worst fraction above 0.75:** {overall_worst*100:.1f}%")
    md.append(f"- **Overall mean fraction above 0.75:** {overall_mean*100:.1f}%")
    md.append(f"- **Indicators where M2 filters effectively (<10%):** {n_indicators_filtered}")
    md.append(f"- **Indicators with partial filtering (10-30%):** {n_indicators_partial}")
    md.append(f"- **Indicators where M2 does NOT filter (≥30%):** {n_indicators_failing}")
    md.append(f"- **Verdict:** **{overall_verdict}**")
    md.append(f"- **Action:** {action}")

    md.append("\n## Per-indicator verdicts (worst-case across L=15/25/35)\n")
    md.append("| Indicator | Worst %>0.75 | Verdict |")
    md.append("|---|---|---|")
    for v in sorted(indicator_verdicts, key=lambda x: -x["worst_frac_above_0.75"]):
        md.append(f"| {v['label']} | {v['worst_frac_above_0.75']*100:.1f}% | **{v['verdict']}** |")

    md.append("\n## Detail — per (indicator, segment length)\n")
    md.append("| Indicator | L | n | mean\\|r\\| | median\\|r\\| | p95\\|r\\| | %>0.5 | %>0.75 | %>0.9 |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        md.append(f"| {r['label']} | {r['segment_length']} | {r['n_valid_samples']} | "
                  f"{r['mean_abs_r']:.3f} | {r['median_abs_r']:.3f} | {r['p95_abs_r']:.3f} | "
                  f"{r['frac_above_0.5']*100:.1f}% | "
                  f"**{r['frac_above_0.75']*100:.1f}%** | "
                  f"{r['frac_above_0.9']*100:.1f}% |")

    md.append("\n## Interpretation\n")
    md.append("If the M2=0.75 SCDI cut filters spurious correlations from I(1) indicators")
    md.append("effectively, the fraction of random country-pair × random-window samples")
    md.append("with |r| ≥ 0.75 should be small. If it is large, then random walks correlated")
    md.append("by virtue of shared integration order routinely pass the 0.75 cut, contaminating")
    md.append("the lift values used by #577.")
    md.append("\nThis is a direct empirical answer to the founder's question: *does the 0.75 cut")
    md.append("save us from the unit-root problem?* It bypasses theoretical debate (Roshani vs.")
    md.append("Tariq on Z-scoring's effect on integrated series) and measures the actual")
    md.append("filtering rate on QGI's actual data.")

    md_path = args.output_dir / "zscore_followon_report.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(f"\n[output] wrote {json_path}")
    print(f"[output] wrote {md_path}")
    print()
    print("=" * 70)
    print(f"OVERALL VERDICT: {overall_verdict}")
    print(f"Worst per-indicator %>0.75: {overall_worst*100:.1f}%")
    print(f"Action: {action}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
