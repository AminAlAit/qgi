#!/usr/bin/env python3
"""
detrending_experiment.py — #585 core experiment.

For each of the 29 confirmed I(1) indicators from #582 Phase 0c, compute the
empirical distribution of |Pearson r| on random country-pair × random-window-
start tuples, side by side for two methods:

  RAW: Z-score the level series within each window, then correlate
  DIFF: First-difference the series, Z-score the differences, then correlate

Output: side-by-side empirical curves for Tariq #20 + Miriam #19 to use as
input to their threshold-selection decision. The script DOES NOT pick a
threshold — that is the methodology council's call. The script provides the
data for the decision.

Pulls panels once via Athena and caches as parquet. Re-running uses cache.

Usage:
  python scripts/detrending_experiment.py \\
      --bucket qgi-data-lake-771606957899 \\
      --workgroup QGI-Lambda-Workgroup \\
      --output-dir results/detrending_experiment_2026_05_02/ \\
      --n-samples 2000

Cost: ~$1 Athena (one-time panel pull), $0 thereafter.
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

# 29 confirmed I(1) indicators from Phase 0c
I1_INDICATORS = [
    # WB economic
    "NY.GDP.MKTP.CD", "NY.GDP.MKTP.KD", "NY.GDP.PCAP.CD", "NY.GNP.PCAP.CD",
    # Trade
    "NE.EXP.GNFS.CD", "NE.IMP.GNFS.CD",
    # Demographic
    "SP.POP.TOTL", "SP.DYN.TFRT.IN",
    # Tech adoption
    "IT.CEL.SETS.P2", "IT.NET.USER.ZS",
    # Sectoral
    "NV.IND.TOTL.ZS", "EN.GHG.CO2.PC.CE.AR5", "EG.IMP.CONS.ZS",
    # Labor + education
    "SL.EMP.TOTL.SP.ZS", "SL.TLF.CACT.FE.ZS", "SL.UEM.1524.ZS",
    "SL.UEM.TOTL.ZS", "SE.PRM.ENRR",
    # Finance
    "FI.RES.TOTL.CD", "FM.LBL.BMNY.GD.ZS", "FB.AST.NPER.ZS",
    # Governance estimates
    "CC.EST", "RQ.EST",
    # V-Dem
    "v2cacamps", "v2excrptps", "v2exl_legitlead",
    "v2x_corr", "v2x_neopat", "v2x_rule",
]

SEGMENT_LENGTHS = [15, 25, 35]


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


def fetch_or_load_panels(ath, bucket, workgroup, indicator_ids, cache_path: Path):
    """Pull from Athena once; cache as parquet."""
    if cache_path.exists():
        print(f"[cache] loading panels from {cache_path}")
        return pd.read_parquet(cache_path)

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

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path)
    print(f"[cache] saved {len(df):,} rows to {cache_path}")
    return df


def zscore(arr):
    mu = np.mean(arr)
    sd = np.std(arr, ddof=0)
    if sd < 1e-9:
        return None
    return (arr - mu) / sd


def correlate_raw(window_a, window_b):
    """Z-score the level series within each window, return |Pearson r|."""
    za = zscore(window_a)
    zb = zscore(window_b)
    if za is None or zb is None:
        return None
    try:
        r = float(np.corrcoef(za, zb)[0, 1])
    except Exception:
        return None
    if np.isnan(r):
        return None
    return abs(r)


def correlate_diff(window_a, window_b):
    """First-difference, then Z-score, then correlate. Returns |Pearson r|."""
    da = np.diff(window_a)
    db = np.diff(window_b)
    if len(da) < 3 or len(db) < 3:
        return None
    za = zscore(da)
    zb = zscore(db)
    if za is None or zb is None:
        return None
    try:
        r = float(np.corrcoef(za, zb)[0, 1])
    except Exception:
        return None
    if np.isnan(r):
        return None
    return abs(r)


def sample_correlations(panel_wide, segment_length, n_samples, rng):
    """Sample n_samples random (country_a, country_b, window_start) tuples.
    For each: compute |r_raw| and |r_diff|. Return (r_raw_array, r_diff_array)."""
    countries = list(panel_wide.columns)
    years = panel_wide.index.values
    n_countries = len(countries)
    n_years = len(years)
    if n_countries < 2 or n_years < segment_length + 1:
        return np.array([]), np.array([])

    r_raw = []
    r_diff = []
    attempts = 0
    max_attempts = n_samples * 5

    while len(r_raw) < n_samples and attempts < max_attempts:
        attempts += 1
        ia, ib = rng.choice(n_countries, size=2, replace=False)
        ca, cb = countries[ia], countries[ib]
        max_start = n_years - segment_length
        start = rng.integers(0, max_start + 1)
        wa = panel_wide[ca].iloc[start:start + segment_length].to_numpy()
        wb = panel_wide[cb].iloc[start:start + segment_length].to_numpy()
        if np.any(np.isnan(wa)) or np.any(np.isnan(wb)):
            continue
        rr = correlate_raw(wa, wb)
        rd = correlate_diff(wa, wb)
        if rr is None or rd is None:
            continue
        r_raw.append(rr)
        r_diff.append(rd)

    return np.array(r_raw), np.array(r_diff)


def distribution_summary(arr, thresholds=(0.5, 0.6, 0.7, 0.75, 0.8, 0.9)):
    """Return mean, median, p95, and fraction above each threshold."""
    if len(arr) == 0:
        return {"n": 0}
    out = {
        "n": int(len(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
    }
    for t in thresholds:
        out[f"frac_above_{t}"] = float(np.mean(arr >= t))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", required=True)
    p.add_argument("--workgroup", default="QGI-Lambda-Workgroup")
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--cache-path", type=Path, default=Path("qgi-ml/data/i1_panels.parquet"))
    p.add_argument("--n-samples", type=int, default=2000)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rng = np.random.default_rng(args.seed)
    ath = boto3.client("athena", region_name=args.region)

    panel = fetch_or_load_panels(ath, args.bucket, args.workgroup,
                                  I1_INDICATORS, args.cache_path)
    print(f"[data] {len(panel):,} rows, {panel['indicator_id'].nunique()} indicators")

    results = []
    for ind_id in I1_INDICATORS:
        sub = panel[panel["indicator_id"] == ind_id]
        if sub.empty:
            print(f"  {ind_id:25s} -> SKIP (no data)")
            continue
        wide = sub.pivot_table(index="year", columns="country",
                               values="value", aggfunc="mean").sort_index()
        for L in SEGMENT_LENGTHS:
            r_raw, r_diff = sample_correlations(wide, L, args.n_samples, rng)
            if len(r_raw) == 0:
                continue
            raw_summary = distribution_summary(r_raw)
            diff_summary = distribution_summary(r_diff)
            results.append({
                "indicator_id": ind_id,
                "segment_length": L,
                "raw": raw_summary,
                "diff": diff_summary,
                "delta_mean": diff_summary["mean"] - raw_summary["mean"],
                "delta_frac_above_0.75": diff_summary["frac_above_0.75"] - raw_summary["frac_above_0.75"],
            })
            print(f"  {ind_id:25s} L={L:2d}  "
                  f"RAW mean={raw_summary['mean']:.3f} %>0.75={raw_summary['frac_above_0.75']*100:5.1f}%  ||  "
                  f"DIFF mean={diff_summary['mean']:.3f} %>0.75={diff_summary['frac_above_0.75']*100:5.1f}%")

    # Aggregate across all (indicator, segment_length)
    agg_raw_means = [r["raw"]["mean"] for r in results]
    agg_diff_means = [r["diff"]["mean"] for r in results]
    agg_raw_above_075 = [r["raw"]["frac_above_0.75"] for r in results]
    agg_diff_above_075 = [r["diff"]["frac_above_0.75"] for r in results]

    summary = {
        "audit_date": audit_date,
        "n_indicators": len(I1_INDICATORS),
        "n_indicator_length_combos": len(results),
        "n_samples_per_combo": args.n_samples,
        "segment_lengths": SEGMENT_LENGTHS,
        "aggregate": {
            "raw_mean_of_means": float(np.mean(agg_raw_means)),
            "diff_mean_of_means": float(np.mean(agg_diff_means)),
            "raw_mean_frac_above_0.75": float(np.mean(agg_raw_above_075)),
            "diff_mean_frac_above_0.75": float(np.mean(agg_diff_above_075)),
            "raw_max_frac_above_0.75": float(np.max(agg_raw_above_075)),
            "diff_max_frac_above_0.75": float(np.max(agg_diff_above_075)),
        },
        "per_combo": results,
    }

    json_path = args.output_dir / "detrending_experiment.json"
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # Markdown report
    md = []
    md.append(f"# Detrending Experiment — RAW vs FIRST-DIFF (#585) — {audit_date}\n")
    md.append(f"**Method:** For each of the {len(I1_INDICATORS)} I(1) indicators from #582 Phase 0c,")
    md.append(f"sample {args.n_samples} random (country_A, country_B, window_start) tuples")
    md.append(f"at segment lengths L ∈ {SEGMENT_LENGTHS}. Compute |Pearson r| under TWO methods:")
    md.append("")
    md.append("- **RAW:** Z-score the level series within each window")
    md.append("- **DIFF:** First-difference each window, then Z-score the differences")
    md.append("")
    md.append("This script does NOT pick a threshold — Tariq #20 + Miriam #19 pick from this data.")

    md.append("\n## Aggregate (mean across 29 indicators × 3 segment lengths = 87 combos)\n")
    md.append(f"- **Mean |r| under RAW:** {summary['aggregate']['raw_mean_of_means']:.3f}")
    md.append(f"- **Mean |r| under DIFF:** {summary['aggregate']['diff_mean_of_means']:.3f}")
    md.append(f"- **Mean fraction |r| ≥ 0.75 under RAW:** {summary['aggregate']['raw_mean_frac_above_0.75']*100:.1f}%")
    md.append(f"- **Mean fraction |r| ≥ 0.75 under DIFF:** {summary['aggregate']['diff_mean_frac_above_0.75']*100:.1f}%")
    md.append(f"- **Worst-case fraction |r| ≥ 0.75 under RAW:** {summary['aggregate']['raw_max_frac_above_0.75']*100:.1f}%")
    md.append(f"- **Worst-case fraction |r| ≥ 0.75 under DIFF:** {summary['aggregate']['diff_max_frac_above_0.75']*100:.1f}%")

    md.append("\n## Per-(indicator × segment-length) detail\n")
    md.append("| Indicator | L | RAW mean\\|r\\| | RAW p95 | RAW %>0.75 | DIFF mean\\|r\\| | DIFF p95 | DIFF %>0.75 | Δ%>0.75 |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        md.append(f"| {r['indicator_id']} | {r['segment_length']} | "
                  f"{r['raw']['mean']:.3f} | {r['raw']['p95']:.3f} | {r['raw']['frac_above_0.75']*100:.1f}% | "
                  f"{r['diff']['mean']:.3f} | {r['diff']['p95']:.3f} | {r['diff']['frac_above_0.75']*100:.1f}% | "
                  f"**{r['delta_frac_above_0.75']*100:+.1f}pp** |")

    md.append("\n## Empirical correlation distribution under DIFF, by threshold\n")
    md.append("Aggregate fraction of random pairs with |r| above each threshold,")
    md.append("after first-differencing. This is the curve Tariq + Miriam should use to pick the I(1)-regime threshold.\n")
    md.append("| Threshold | RAW mean fraction | DIFF mean fraction |")
    md.append("|---|---|---|")
    for t in (0.5, 0.6, 0.7, 0.75, 0.8, 0.9):
        raw_avg = float(np.mean([r["raw"][f"frac_above_{t}"] for r in results]))
        diff_avg = float(np.mean([r["diff"][f"frac_above_{t}"] for r in results]))
        md.append(f"| {t} | {raw_avg*100:.1f}% | **{diff_avg*100:.1f}%** |")

    md.append("\n## Interpretation guide for the methodology council\n")
    md.append("Tariq #20 + Miriam #19 must select a threshold for the I(1) (first-differenced)")
    md.append("regime that:")
    md.append("- (a) keeps the spurious-pass-through rate acceptably low — say ≤5%")
    md.append("- (b) does not over-filter genuine signal (which the auditioner lift comparison will measure)")
    md.append("")
    md.append("The DIFF columns above show the random-pair distribution after detrending.")
    md.append("Compare to the RAW columns to see how much the detrending shifts the distribution.")
    md.append("")
    md.append("Companion data needed before the council adjudicates:")
    md.append("- Lift values from auditioner under raw and diff (separate experiment)")
    md.append("- Genuine-signal retention test (selected country pairs known to share genuine relationships)")

    md_path = args.output_dir / "detrending_experiment.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(f"\n[output] {json_path}")
    print(f"[output] {md_path}")
    print()
    print("=" * 70)
    print(f"AGGREGATE: RAW mean |r| = {summary['aggregate']['raw_mean_of_means']:.3f}")
    print(f"           DIFF mean |r| = {summary['aggregate']['diff_mean_of_means']:.3f}")
    print(f"           RAW mean %>0.75  = {summary['aggregate']['raw_mean_frac_above_0.75']*100:.1f}%")
    print(f"           DIFF mean %>0.75 = {summary['aggregate']['diff_mean_frac_above_0.75']*100:.1f}%")
    print("=" * 70)
    print("Threshold selection deferred to Tariq #20 + Miriam #19 review.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
