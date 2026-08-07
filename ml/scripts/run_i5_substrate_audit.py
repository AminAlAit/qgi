"""
run_i5_substrate_audit.py — Phase 5 v0.0b Stage A: panel unit-root audit.

# THROWAWAY in spirit (one-shot per catalog refresh) but committed for
# re-runnability. Re-run when new indicators ingest or the catalog grows.

For each ingested indicator with parquet output at
`pipeline-A-indicator-extractor/output/parquet-completed/{id}/{id}.parquet`,
runs panel unit-root tests and classifies the indicator as I(0)/I(1)/I(2)/
ambiguous. Output JSON at `qgi-data/reference/indicator-stationarity-audit.json`
is the input for Phase 5 v0.0b Stage C (DSCDI computation): I(1) indicators
get first-differenced before Pearson correlation; I(0) pass through unchanged.

Per Tariq Farouk-Lindgren's I5 RECONVENE spec
(docs/specs/internal/majles/in-progress/2026-05-03_Ihsa_post_phase4_tariq_RECONVENE.md):
  - Test: Pesaran (2007) CIPS heterogeneous-panel unit-root test, OR
    fallback to per-country ADF + majority-vote aggregation if CIPS
    library unavailable. QA methodology consult (Stage B) reviews
    the choice before Stage C kickoff.
  - Decision rule: I(0) if test rejects unit root at 5%; I(1) if test
    fails to reject at level but rejects at first-difference; I(2) if
    fails at both; ambiguous if borderline (4% < p < 6%).

Scope (per Phase 5 v0.0b spec amendment 2026-05-04):
  All 109 indicators with parquet output. Decomposes as:
  - 47 WB/VD-curated + 5 FA-curated (catalog-tracked)
  - 57 uncurated WB indicators (in indicator_map but not in catalog)
  All 109 audited; uncurated tagged separately so they can be promoted
  to catalog later if methodology team wants them.

Data flow:
  1. List parquet directories under pipeline-A-indicator-extractor/output/parquet-completed/
  2. For each indicator: download parquet, pivot to wide panel (rows=year,
     cols=country, values=indicator_value), apply unit-root test
  3. Write per-indicator classification + p-values to JSON
  4. Stage B QA consult reviews the JSON before Stage C reads it

Cost: ~$0.05 (109 small S3 GETs ~$0.0001 + Athena verify reads ~$0.04).
Time: ~5-10 min wall (parallelizable across indicators if needed).

Usage:
  python qgi-ml/scripts/run_i5_substrate_audit.py \\
      --bucket qgi-data-lake-771606957899 \\
      --output qgi-data/reference/indicator-stationarity-audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
import pyarrow.parquet as pq
import s3fs

INDICATOR_PREFIX = "pipeline-A-indicator-extractor/output/parquet-completed/"
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "qgi-data" / "reference" / "indicator-stationarity-audit.json"

# Decision thresholds (per Tariq spec; Stage B QA consult may revise).
# A test "rejects" the unit root if its p-value < 0.05.
P_REJECT = 0.05
P_AMBIGUOUS_LO = 0.04
P_AMBIGUOUS_HI = 0.06

# Per-country ADF fallback: classify the indicator by the FRACTION of
# countries whose level series rejects the unit root. The thresholds are
# conservative — most countries must agree for a strong I(0) call.
ADF_FRAC_THRESHOLDS = {
    "I(0)_strong": 0.70,   # >=70% of countries reject at level
    "I(1)_strong": 0.30,   # <30% reject at level (most don't), but >=70% reject at first-difference
    "I(2)_strong": 0.30,   # <30% reject at level AND <30% at first-difference
}


def list_indicators(s3: "boto3.client", bucket: str) -> list[str]:
    """List all indicator IDs (directory names) under INDICATOR_PREFIX."""
    paginator = s3.get_paginator("list_objects_v2")
    ids: set[str] = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=INDICATOR_PREFIX, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []) or []:
            part = cp["Prefix"].rstrip("/").split("/")[-1]
            if part:
                ids.add(part)
    return sorted(ids)


def load_indicator_panel(s3fs_: s3fs.S3FileSystem, bucket: str, indicator_id: str
                          ) -> pd.DataFrame | None:
    """Load one indicator's parquet, pivot to wide panel (rows=year, cols=country).

    Returns None if the parquet is missing or has unexpected schema.
    """
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
        print(f"  [{indicator_id}] WARN: missing columns; have {list(df.columns)}",
              file=sys.stderr)
        return None
    # Drop nulls, deduplicate, pivot
    df = df.dropna(subset=["value"])
    df = df.drop_duplicates(subset=["country", "year"], keep="last")
    panel = df.pivot(index="year", columns="country", values="value").sort_index()
    return panel


def classify_indicator_adf_fallback(panel: pd.DataFrame) -> dict[str, Any]:
    """Per-country ADF fallback: run ADF on each country's level + first-
    difference series; classify the indicator by the country-level vote.

    Returns dict with classification, fraction-rejecting metrics, and the
    minimum panel size used.
    """
    from statsmodels.tsa.stattools import adfuller

    countries = list(panel.columns)
    n_countries = len(countries)
    rejected_at_level = 0
    rejected_at_diff = 0
    countries_tested_at_level = 0
    countries_tested_at_diff = 0
    # Min obs raised from 8 to 15 per Stage B QA review: with autolag="AIC"
    # and regression="c", statsmodels at nobs=8 fits ~0 lags with negligible
    # degrees of freedom and returns near-meaningless p-values. 15 is a
    # standard practitioner floor for annual-data ADF.
    min_obs_required = 15

    for country in countries:
        series = panel[country].dropna()
        if len(series) < min_obs_required:
            continue
        countries_tested_at_level += 1
        # Level test
        try:
            p_level = adfuller(series, autolag="AIC", regression="c")[1]
        except Exception:
            p_level = 1.0
        if p_level < P_REJECT:
            rejected_at_level += 1
        # First-difference test (only counted in diff denominator if it actually runs)
        diffed = series.diff().dropna()
        if len(diffed) < min_obs_required:
            continue
        countries_tested_at_diff += 1
        try:
            p_diff = adfuller(diffed, autolag="AIC", regression="c")[1]
        except Exception:
            p_diff = 1.0
        if p_diff < P_REJECT:
            rejected_at_diff += 1

    if countries_tested_at_level == 0:
        return {
            "classification": "insufficient_data",
            "n_countries_tested_at_level": 0,
            "n_countries_tested_at_diff": 0,
            "n_countries_total": n_countries,
            "frac_rejected_at_level": None,
            "frac_rejected_at_diff": None,
            "test": "per_country_adf",
        }

    frac_level = rejected_at_level / countries_tested_at_level
    frac_diff = (
        rejected_at_diff / countries_tested_at_diff
        if countries_tested_at_diff > 0 else 0.0
    )

    # Classification logic — I(2)_or_higher branch now also requires that
    # frac_level is not high (i.e., the level series is also non-stationary).
    # Without this guard, a heterogeneous panel (40% reject at level, 25%
    # reject at diff) was misclassified as I(2). The ambiguous branch now
    # catches those cases.
    if frac_level >= ADF_FRAC_THRESHOLDS["I(0)_strong"]:
        cls = "I(0)"
    elif frac_diff >= ADF_FRAC_THRESHOLDS["I(0)_strong"]:
        cls = "I(1)"
    elif (frac_diff < ADF_FRAC_THRESHOLDS["I(2)_strong"]
          and frac_level < ADF_FRAC_THRESHOLDS["I(2)_strong"]):
        cls = "I(2)_or_higher"
    else:
        cls = "ambiguous"

    return {
        "classification": cls,
        "n_countries_tested_at_level": countries_tested_at_level,
        "n_countries_tested_at_diff": countries_tested_at_diff,
        "n_countries_total": n_countries,
        "frac_rejected_at_level": round(frac_level, 4),
        "frac_rejected_at_diff": round(frac_diff, 4),
        "test": "per_country_adf",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help="Path to write audit JSON")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only audit first N indicators (for smoke test)")
    args = parser.parse_args()

    s3 = boto3.client("s3")
    s3fs_ = s3fs.S3FileSystem()

    print(f"Listing indicators under s3://{args.bucket}/{INDICATOR_PREFIX}",
          file=sys.stderr)
    indicators = list_indicators(s3, args.bucket)
    print(f"Found {len(indicators)} indicators", file=sys.stderr)
    if args.limit:
        indicators = indicators[:args.limit]
        print(f"Limited to first {len(indicators)} for this run", file=sys.stderr)

    results: dict[str, dict[str, Any]] = {}
    t0 = time.monotonic()

    for i, ind_id in enumerate(indicators, 1):
        elapsed = time.monotonic() - t0
        eta = (elapsed / i) * (len(indicators) - i) if i > 0 else 0
        print(f"[{i:3d}/{len(indicators)}] {ind_id} (elapsed {elapsed:.0f}s, "
              f"ETA {eta:.0f}s)", file=sys.stderr)

        panel = load_indicator_panel(s3fs_, args.bucket, ind_id)
        if panel is None:
            results[ind_id] = {
                "classification": "load_failed",
                "n_countries_tested_at_level": 0,
                "n_countries_tested_at_diff": 0,
                "n_countries_total": 0,
                "test": None,
                "error": "panel could not be loaded",
            }
            continue

        try:
            result = classify_indicator_adf_fallback(panel)
        except Exception as exc:
            results[ind_id] = {
                "classification": "test_failed",
                "n_countries_tested_at_level": 0,
                "n_countries_tested_at_diff": 0,
                "n_countries_total": len(panel.columns),
                "test": "per_country_adf",
                "error": f"{type(exc).__name__}: {exc}",
            }
            continue
        results[ind_id] = result

    # Summary stats
    by_cls: dict[str, int] = {}
    for r in results.values():
        by_cls[r["classification"]] = by_cls.get(r["classification"], 0) + 1

    payload = {
        "schema_version": 1,
        "generator": "qgi-ml/scripts/run_i5_substrate_audit.py",
        "test_method": "per_country_adf_fallback",
        "test_method_note": (
            "Per-country ADF (statsmodels.tsa.stattools.adfuller) with "
            "majority-vote aggregation. Pesaran CIPS not used in this "
            "run; see Stage B QA consult for the methodology choice "
            "(panel test vs per-country aggregation)."
        ),
        "decision_rule": {
            "I(0)_threshold_frac_rejected_at_level": ADF_FRAC_THRESHOLDS["I(0)_strong"],
            "I(1)_threshold_frac_rejected_at_diff": ADF_FRAC_THRESHOLDS["I(0)_strong"],
            "I(2)_threshold_frac_rejected_at_diff": ADF_FRAC_THRESHOLDS["I(2)_strong"],
            "p_reject": P_REJECT,
        },
        "indicators_audited": len(results),
        "summary_by_classification": by_cls,
        "results": results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n",
                            encoding="utf-8")

    print(f"\n--- Summary ({time.monotonic() - t0:.1f}s wall) ---", file=sys.stderr)
    print(f"  Total audited: {len(results)}", file=sys.stderr)
    for cls, n in sorted(by_cls.items(), key=lambda x: -x[1]):
        print(f"  {cls:>20}: {n}", file=sys.stderr)
    print(f"\nWrote {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
