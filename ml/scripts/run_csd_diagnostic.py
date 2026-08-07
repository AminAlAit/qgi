"""
run_csd_diagnostic.py — Phase 5 v0.0b Stage B Step 5.

Two diagnostics governed by Protocol 5:

1. **Pesaran (2004) CD test** on a pre-specified 15-indicator subsample.
   Tests the cross-section dependence of per-country residuals from a
   simple within-mean-removed model. Outputs: per-indicator CD statistic,
   p-value, and CSD-flag (p < 0.10) / severe-flag (p < 0.001).

2. **Geographic clustering diagnostic** on 25 contested indicators.
   Computes per-WB-region frac_rejected_at_diff. CSD-suspect flag when
   OECD frac_rejected exceeds non-OECD by > 0.20.

Both are non-outcome-conditional documentation-only outputs per Kwame's
Stage B pre-registration discipline. Reclassification only via Tariq
consultation, never autonomous.

Pesaran CD test reference: Pesaran, M. H. (2004). "General diagnostic
tests for cross section dependence in panels." Cambridge Working Papers
in Economics 0435. Statistic:

    CD = sqrt(2T / (N(N-1))) * sum_{i<j} rho_{ij}

where rho_{ij} is the sample correlation of residuals between countries
i and j over T periods. Under H0 (no CSD), CD ~ N(0,1) asymptotically.

Cost: ~$0 (local Python on cached parquet; ~30 S3 GETs total).
Time: ~30 seconds.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import boto3
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import s3fs
from scipy import stats

INDICATOR_PREFIX = "pipeline-A-indicator-extractor/output/parquet-completed/"
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]

# Pre-specified 15-indicator subsample per Protocol 5 (Tariq's Q5 spec).
# This list is FROZEN — committed to the protocol document before this
# script ran. Do NOT modify post-hoc to change CD diagnostic results.
CD_SUBSAMPLE_15 = [
    "v2x_libdem",
    "NY.GDP.PCAP.CD",
    "FP.CPI.TOTL.ZG",
    "SL.UEM.TOTL.ZS",
    "CC.EST",
    "v2x_polyarchy",
    "MS.MIL.XPND.GD.ZS",
    "NE.EXP.GNFS.ZS",
    "NE.IMP.GNFS.ZS",
    "SE.PRM.ENRR",
    "SH.DYN.MORT",
    "SP.DYN.LE00.IN",
    "SP.DYN.TFRT.IN",
    "IT.CEL.SETS.P2",
    "RL.EST",
]

# CD-flag thresholds per Protocol 5
CD_FLAG_P_THRESHOLD = 0.10
CD_SEVERE_P_THRESHOLD = 0.001

# Geographic clustering threshold per Protocol 5
GEO_CSD_SUSPECT_DELTA = 0.20

# OECD high-income membership (38 members as of 2026, ISO alpha-3).
# Hardcoded for the geographic diagnostic.
OECD_ALPHA3 = frozenset({
    "AUS", "AUT", "BEL", "CAN", "CHL", "COL", "CRI", "CZE", "DNK",
    "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL", "ISR",
    "ITA", "JPN", "KOR", "LVA", "LTU", "LUX", "MEX", "NLD", "NZL",
    "NOR", "POL", "PRT", "SVK", "SVN", "ESP", "SWE", "CHE", "TUR",
    "GBR", "USA",
})


def load_indicator_panel(s3fs_, bucket: str, indicator_id: str) -> pd.DataFrame | None:
    key = f"{INDICATOR_PREFIX}{indicator_id}/{indicator_id}.parquet"
    try:
        with s3fs_.open(f"{bucket}/{key}", "rb") as fh:
            df = pq.ParquetFile(fh).read().to_pandas()
    except Exception as exc:
        print(f"  [{indicator_id}] WARN: load failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return None
    needed = {"country", "year", "value"}
    if not needed.issubset(df.columns):
        return None
    df = df.dropna(subset=["value"])
    df = df.drop_duplicates(subset=["country", "year"], keep="last")
    return df.pivot(index="year", columns="country", values="value").sort_index()


def pesaran_cd_test(panel: pd.DataFrame, min_obs: int = 15) -> dict[str, Any]:
    """Pesaran (2004) CD statistic on residuals from country-level
    within-mean removal.

    Steps:
      1. Filter to countries with >= min_obs observations
      2. For each country: subtract its time-mean → residual series
      3. Compute pairwise sample correlations of residuals (T_ij = overlapping years)
      4. CD = sqrt(2T_ij / (N(N-1))) * sum_{i<j} sqrt(T_ij) * rho_{ij}
         (Pesaran 2004 form for unbalanced panels)
      5. CD ~ N(0,1) under H0; compute two-sided p-value

    Returns dict with cd_statistic, p_value, n_countries, mean_pairwise_T,
    n_pairs.
    """
    # Filter countries by observation count
    obs_per_country = panel.notna().sum(axis=0)
    keep = obs_per_country[obs_per_country >= min_obs].index.tolist()
    sub = panel[keep]

    if len(keep) < 2:
        return {
            "cd_statistic": None,
            "p_value": None,
            "n_countries": len(keep),
            "n_pairs": 0,
            "mean_pairwise_T": None,
            "error": "fewer than 2 countries with >= min_obs",
        }

    # Within-mean removal: subtract each country's time-mean
    residuals = sub.subtract(sub.mean(axis=0), axis=1)

    countries = list(residuals.columns)
    N = len(countries)
    cd_sum = 0.0
    n_pairs = 0
    T_sum = 0

    for i in range(N):
        for j in range(i + 1, N):
            r_i = residuals[countries[i]]
            r_j = residuals[countries[j]]
            both = r_i.notna() & r_j.notna()
            T_ij = int(both.sum())
            if T_ij < 4:
                continue
            x = r_i[both].values
            y = r_j[both].values
            sx = x.std(ddof=1)
            sy = y.std(ddof=1)
            if sx == 0 or sy == 0 or not np.isfinite(sx) or not np.isfinite(sy):
                continue
            rho = float(np.corrcoef(x, y)[0, 1])
            if not np.isfinite(rho):
                continue
            cd_sum += np.sqrt(T_ij) * rho
            n_pairs += 1
            T_sum += T_ij

    if n_pairs == 0:
        return {
            "cd_statistic": None,
            "p_value": None,
            "n_countries": N,
            "n_pairs": 0,
            "mean_pairwise_T": None,
            "error": "no valid country pairs",
        }

    # CD = sqrt(2 / (N(N-1))) * cd_sum (Pesaran 2004)
    cd = np.sqrt(2.0 / (N * (N - 1))) * cd_sum
    p_value = 2.0 * (1.0 - stats.norm.cdf(abs(cd)))

    return {
        "cd_statistic": round(float(cd), 4),
        "p_value": round(float(p_value), 6),
        "n_countries": N,
        "n_pairs": n_pairs,
        "mean_pairwise_T": round(T_sum / n_pairs, 1),
    }


def classify_cd_flag(p_value: float | None) -> str:
    """Per Protocol 5 thresholds."""
    if p_value is None:
        return "insufficient_data"
    if p_value < CD_SEVERE_P_THRESHOLD:
        return "severe_csd"
    if p_value < CD_FLAG_P_THRESHOLD:
        return "csd_flag"
    return "no_csd_flag"


def load_country_alpha3_map(s3, bucket: str) -> dict[str, str]:
    """Load countries.csv to map country name → alpha_3."""
    obj = s3.get_object(Bucket=bucket,
                        Key="pipeline-A-indicator-extractor/input/countries.csv")
    raw = obj["Body"].read().decode("utf-8")
    df = pd.read_csv(pd.io.common.StringIO(raw))
    # Build a map from each name column to alpha_3
    name_cols = [c for c in df.columns if c.startswith("name")]
    out = {}
    for _, row in df.iterrows():
        a3 = str(row.get("alpha_3", "")).strip()
        if not a3 or a3 == "nan":
            continue
        for col in name_cols:
            name = row.get(col)
            if isinstance(name, str) and name.strip():
                out[name.strip()] = a3
    return out


def geographic_clustering_diagnostic(panel: pd.DataFrame,
                                      country_to_alpha3: dict[str, str],
                                      ) -> dict[str, Any]:
    """Per Protocol 5: compute frac_rejected_at_diff for OECD countries vs
    non-OECD countries; flag CSD-suspect if delta > 0.20.

    Note: full per-WB-region breakdown requires a country→region map we
    don't have committed. OECD vs non-OECD is the core threshold check
    Protocol 5 specifies; we expose the 7-region breakdown as a future
    refinement (currently grouping non-OECD into one bucket).
    """
    from statsmodels.tsa.stattools import adfuller

    countries = list(panel.columns)
    oecd_rejected = 0
    oecd_tested = 0
    non_oecd_rejected = 0
    non_oecd_tested = 0

    for country in countries:
        series = panel[country].dropna()
        diffed = series.diff().dropna()
        if len(diffed) < 15:
            continue
        try:
            p_diff = adfuller(diffed, autolag="AIC", regression="c")[1]
        except Exception:
            p_diff = 1.0
        rejected = p_diff < 0.05
        a3 = country_to_alpha3.get(country, "")
        if a3 in OECD_ALPHA3:
            oecd_tested += 1
            if rejected:
                oecd_rejected += 1
        else:
            non_oecd_tested += 1
            if rejected:
                non_oecd_rejected += 1

    oecd_frac = oecd_rejected / oecd_tested if oecd_tested > 0 else None
    non_oecd_frac = (non_oecd_rejected / non_oecd_tested
                     if non_oecd_tested > 0 else None)

    if oecd_frac is None or non_oecd_frac is None:
        suspect = False
        delta = None
    else:
        delta = oecd_frac - non_oecd_frac
        suspect = delta > GEO_CSD_SUSPECT_DELTA

    return {
        "oecd_n_tested": oecd_tested,
        "oecd_frac_rejected_at_diff": (round(oecd_frac, 4)
                                        if oecd_frac is not None else None),
        "non_oecd_n_tested": non_oecd_tested,
        "non_oecd_frac_rejected_at_diff": (round(non_oecd_frac, 4)
                                            if non_oecd_frac is not None else None),
        "delta_oecd_minus_non_oecd": (round(delta, 4)
                                       if delta is not None else None),
        "csd_suspect": suspect,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--contested-list", required=True,
                        help="Path to text file with the 25 contested indicators")
    parser.add_argument("--output", required=True,
                        help="Path to write CSD diagnostic JSON")
    args = parser.parse_args()

    s3 = boto3.client("s3")
    s3fs_ = s3fs.S3FileSystem()

    # Load contested list for geographic diagnostic
    contested = sorted(set(line.strip() for line in
                            Path(args.contested_list).read_text(encoding="utf-8")
                            .splitlines() if line.strip()))
    print(f"Contested list: {len(contested)} indicators", file=sys.stderr)

    # Load country → alpha_3 map for geographic diagnostic
    print("Loading countries.csv for OECD membership lookup...", file=sys.stderr)
    country_to_alpha3 = load_country_alpha3_map(s3, args.bucket)
    print(f"  loaded {len(country_to_alpha3)} country-name → alpha_3 mappings",
          file=sys.stderr)

    # Diagnostic 1 — Pesaran CD on 15-indicator subsample
    print(f"\n=== Diagnostic 1: Pesaran (2004) CD test on {len(CD_SUBSAMPLE_15)}"
          " indicators ===", file=sys.stderr)
    cd_results: dict[str, dict[str, Any]] = {}
    t0 = time.monotonic()
    for i, ind in enumerate(CD_SUBSAMPLE_15, 1):
        print(f"[{i:2d}/{len(CD_SUBSAMPLE_15)}] {ind}", file=sys.stderr)
        panel = load_indicator_panel(s3fs_, args.bucket, ind)
        if panel is None:
            cd_results[ind] = {
                "cd_statistic": None, "p_value": None,
                "flag": "load_failed",
            }
            continue
        cd_stat = pesaran_cd_test(panel)
        cd_stat["flag"] = classify_cd_flag(cd_stat.get("p_value"))
        cd_results[ind] = cd_stat
    print(f"CD diagnostic complete in {time.monotonic() - t0:.1f}s",
          file=sys.stderr)

    # Diagnostic 2 — Geographic clustering on 25 contested
    print(f"\n=== Diagnostic 2: Geographic clustering (OECD vs non-OECD) on "
          f"{len(contested)} contested indicators ===", file=sys.stderr)
    geo_results: dict[str, dict[str, Any]] = {}
    t0 = time.monotonic()
    for i, ind in enumerate(contested, 1):
        print(f"[{i:2d}/{len(contested)}] {ind}", file=sys.stderr)
        panel = load_indicator_panel(s3fs_, args.bucket, ind)
        if panel is None:
            geo_results[ind] = {"csd_suspect": False, "error": "load_failed"}
            continue
        geo_results[ind] = geographic_clustering_diagnostic(panel, country_to_alpha3)
    print(f"Geographic diagnostic complete in {time.monotonic() - t0:.1f}s",
          file=sys.stderr)

    # Summarize
    cd_flags = {flag: 0 for flag in
                ["no_csd_flag", "csd_flag", "severe_csd", "insufficient_data",
                 "load_failed"]}
    for r in cd_results.values():
        f = r.get("flag", "load_failed")
        cd_flags[f] = cd_flags.get(f, 0) + 1

    geo_suspect_count = sum(1 for r in geo_results.values()
                             if r.get("csd_suspect") is True)

    payload = {
        "schema_version": 1,
        "generator": "qgi-ml/scripts/run_csd_diagnostic.py",
        "protocol_reference": (
            "docs/specs/internal/ops/cascade-track/phase-5-v0.0b-protocol-5-csd-protocol.md"
        ),
        "diagnostic_1_pesaran_cd": {
            "subsample": CD_SUBSAMPLE_15,
            "n_indicators": len(CD_SUBSAMPLE_15),
            "p_thresholds": {
                "csd_flag": CD_FLAG_P_THRESHOLD,
                "severe_csd": CD_SEVERE_P_THRESHOLD,
            },
            "summary_by_flag": cd_flags,
            "results": cd_results,
        },
        "diagnostic_2_geographic_clustering": {
            "scope": "25 contested indicators (per Decision 1)",
            "n_indicators": len(contested),
            "csd_suspect_threshold_delta": GEO_CSD_SUSPECT_DELTA,
            "n_csd_suspect": geo_suspect_count,
            "results": geo_results,
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n",
                            encoding="utf-8")

    print("\n=== Summary ===", file=sys.stderr)
    print("  CD test (15 indicators):", file=sys.stderr)
    for flag, n in sorted(cd_flags.items(), key=lambda x: -x[1]):
        if n > 0:
            print(f"    {flag}: {n}", file=sys.stderr)
    print(f"  Geographic CSD-suspect (25 contested): {geo_suspect_count}",
          file=sys.stderr)
    print(f"\nWrote {output_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
