"""
run_stage_e_survival_fraction.py — Phase 5 v0.0b Stage E.

Runs the DSCDI methodology across all 109 ingested indicators on cached
parquet (no production write). Produces two artifacts:

1. **Pairwise diagnostic** (`qgi-data/reference/stage-e-pairwise-diagnostic.json`):
   The canonical Stage C exit-gate report (per Priya's spec), now at full
   scale instead of the 3-indicator smoke. Reports per-indicator
   `mean_abs_pairwise_corr` + `demeaning_insufficient` flag for every
   Class A indicator.

2. **Survival fraction** (`qgi-data/reference/stage-e-survival-fraction.json`):
   The headline methodology report. For each indicator, computes the
   "survival fraction" — what proportion of the SCDI substrate's
   correlation structure survives the DSCDI transformation. High survival
   = SCDI and DSCDI agree (low Granger-Newbold contamination); low
   survival = the original SCDI substrate was substantially driven by
   spurious common-factor correlations.

   Per Tariq's I5 RECONVENE Phase 5 v0.0b spec:
   - High survival (>80%): Granger-Newbold concern was overstated for QGI's panel
   - Mid survival (40-80%): substantial substrate cleanup happened
   - Low survival (<40%): Granger-Newbold was severe; Phase 4 v0.2 result was
     substantially driven by spurious structure

# THROWAWAY in spirit (one-shot Stage E run) but committed for re-runnability.

Cost: ~$0 (109 small S3 GETs + local Python).
Time: ~6-12 hours wall on developer laptop. Safe to run overnight.

Per founder direction 2026-05-04 / 2026-05-05: Stage E is local Python
on cached parquet. NO production write. NO pipeline-run trigger. NO
Glue table population. The Stage E artifacts are committed-to-git
methodology reports that drive the Phase 6 design + the eventual Stage F
authorization decision.

Usage:
  python qgi-ml/scripts/run_stage_e_survival_fraction.py \\
      --bucket qgi-data-lake-771606957899
"""
from __future__ import annotations

import argparse
import importlib.util
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


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
DSCDI_MODULE_PATH = (
    REPO_ROOT / "qgi-pipeline" / "batch" / "dscdi-finder" / "src" / "dscdi_finder.py"
)
INDICATOR_PREFIX = "pipeline-A-indicator-extractor/output/parquet-completed/"
DEFAULT_AUDIT_PATH = REPO_ROOT / "qgi-data" / "reference" / "indicator-stationarity-audit-v2.json"
DEFAULT_PAIRWISE_OUTPUT = REPO_ROOT / "qgi-data" / "reference" / "stage-e-pairwise-diagnostic.json"
DEFAULT_SURVIVAL_OUTPUT = REPO_ROOT / "qgi-data" / "reference" / "stage-e-survival-fraction.json"

# Load DSCDI module
_spec = importlib.util.spec_from_file_location("dscdi_finder", DSCDI_MODULE_PATH)
dscdi = importlib.util.module_from_spec(_spec)
sys.modules["dscdi_finder"] = dscdi
_spec.loader.exec_module(dscdi)


def load_indicator_panel(s3fs_, bucket: str, indicator_id: str) -> pd.DataFrame | None:
    """Load one indicator's parquet, pivot to wide panel."""
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


def compute_scdi_baseline_correlation(panel: pd.DataFrame, min_obs: int = 15) -> float:
    """Compute the SCDI-equivalent mean abs pairwise correlation: Pearson on
    raw level series (no transformation, no demeaning).

    This is the "what the original SCDI substrate would see" baseline. Used
    in the survival-fraction calculation to compare against the DSCDI
    primary output's mean abs correlation.

    Returns mean abs off-diagonal correlation (NaN if insufficient data).
    """
    obs_per_country = panel.notna().sum(axis=0)
    keep = obs_per_country[obs_per_country >= min_obs].index.tolist()
    if len(keep) < 2:
        return float("nan")
    corr = panel[keep].corr(method="pearson", min_periods=4)
    return dscdi._mean_abs_pairwise_off_diagonal(corr)


def compute_survival_fraction(
    indicator_id: str, panel: pd.DataFrame, dscdi_result, min_obs: int = 15
) -> dict[str, Any]:
    """Compute the SCDI→DSCDI survival fraction for one indicator.

    Definitions:
      - SCDI baseline correlation: mean abs pairwise Pearson on RAW level
        series. This is what the original SCDI methodology produces.
      - DSCDI primary correlation: mean abs pairwise Pearson on the
        per-class-transformed series, with demeaning if Class A.
      - Survival fraction: DSCDI primary / SCDI baseline. High = most of the
        SCDI signal survives detrending; low = much of SCDI was spurious
        common-factor correlation.

    The survival fraction is bounded in [0, 1] in expectation but can
    exceed 1 in edge cases (e.g., demeaning AMPLIFIES correlations on
    indicators where the cross-section variance was dominated by noise).
    Such cases are interesting and should be flagged.
    """
    scdi_baseline = compute_scdi_baseline_correlation(panel, min_obs)
    dscdi_primary = dscdi_result.mean_abs_pairwise_corr

    if scdi_baseline == 0 or pd.isna(scdi_baseline):
        survival = None
    else:
        survival = dscdi_primary / scdi_baseline

    return {
        "scdi_baseline_mean_abs_corr": (
            round(scdi_baseline, 6) if not pd.isna(scdi_baseline) else None
        ),
        "dscdi_primary_mean_abs_corr": round(dscdi_primary, 6),
        "survival_fraction": round(survival, 6) if survival is not None else None,
        "survival_amplifies_correlation": (
            survival is not None and survival > 1.0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--audit-path", default=str(DEFAULT_AUDIT_PATH),
                        help="Path to v2 audit JSON")
    parser.add_argument("--pairwise-output", default=str(DEFAULT_PAIRWISE_OUTPUT),
                        help="Where to write pairwise diagnostic JSON")
    parser.add_argument("--survival-output", default=str(DEFAULT_SURVIVAL_OUTPUT),
                        help="Where to write survival-fraction JSON")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process first N indicators (smoke)")
    args = parser.parse_args()

    # Load audit classifications
    print(f"Loading audit classifications from {args.audit_path}...",
          file=sys.stderr)
    classifications = dscdi.load_audit_classifications(args.audit_path)
    print(f"  loaded {len(classifications)} indicators with valid classifications",
          file=sys.stderr)

    s3fs_ = s3fs.S3FileSystem()

    indicator_ids = sorted(classifications.keys())
    if args.limit:
        indicator_ids = indicator_ids[:args.limit]
        print(f"  LIMITED to first {len(indicator_ids)} indicators", file=sys.stderr)

    print(f"\n=== Running DSCDI on {len(indicator_ids)} indicators ===\n",
          file=sys.stderr)

    dscdi_results = []
    survival_results: dict[str, dict[str, Any]] = {}
    failed_indicators: list[dict[str, str]] = []
    t0 = time.monotonic()

    for i, ind_id in enumerate(indicator_ids, 1):
        elapsed = time.monotonic() - t0
        eta = (elapsed / i) * (len(indicator_ids) - i) if i > 0 else 0
        print(f"[{i:3d}/{len(indicator_ids)}] {ind_id} "
              f"(elapsed {elapsed:.0f}s, ETA {eta:.0f}s)",
              file=sys.stderr)

        panel = load_indicator_panel(s3fs_, args.bucket, ind_id)
        if panel is None:
            failed_indicators.append({
                "indicator_id": ind_id,
                "reason": "panel_load_failed",
            })
            continue

        try:
            result = dscdi.run_dscdi_pass(
                ind_id, panel, classifications[ind_id]
            )
        except Exception as exc:
            failed_indicators.append({
                "indicator_id": ind_id,
                "reason": f"dscdi_pass_failed: {type(exc).__name__}: {exc}",
            })
            continue

        dscdi_results.append(result)
        survival_results[ind_id] = compute_survival_fraction(ind_id, panel, result)
        # Add disposition + class info for context
        survival_results[ind_id]["audit_classification"] = result.disposition.classification
        survival_results[ind_id]["indicator_class"] = result.disposition.indicator_class
        survival_results[ind_id]["transform"] = result.disposition.transform
        survival_results[ind_id]["demeaning_applied"] = result.demeaning_applied

    elapsed_total = time.monotonic() - t0
    print(f"\n=== Stage E complete in {elapsed_total:.0f}s "
          f"({elapsed_total/60:.1f} min) ===\n", file=sys.stderr)

    # Write pairwise diagnostic
    pairwise_report = dscdi.build_diagnostic_report(dscdi_results)
    pairwise_report["stage"] = "E"
    pairwise_report["wall_time_seconds"] = round(elapsed_total, 1)
    pairwise_report["failed_indicators"] = failed_indicators

    pairwise_path = Path(args.pairwise_output)
    pairwise_path.parent.mkdir(parents=True, exist_ok=True)
    pairwise_path.write_text(
        json.dumps(pairwise_report, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote pairwise diagnostic: {pairwise_path}", file=sys.stderr)

    # Write survival fraction report
    survival_values = [
        v["survival_fraction"] for v in survival_results.values()
        if v.get("survival_fraction") is not None
    ]
    n_survives_high = sum(1 for s in survival_values if s > 0.8)
    n_survives_mid = sum(1 for s in survival_values if 0.4 <= s <= 0.8)
    n_survives_low = sum(1 for s in survival_values if s < 0.4)
    n_amplifies = sum(
        1 for v in survival_results.values()
        if v.get("survival_amplifies_correlation")
    )

    survival_payload = {
        "schema_version": 1,
        "generator": "qgi-ml/scripts/run_stage_e_survival_fraction.py",
        "stage": "E",
        "n_indicators_attempted": len(indicator_ids),
        "n_indicators_succeeded": len(survival_results),
        "n_indicators_failed": len(failed_indicators),
        "wall_time_seconds": round(elapsed_total, 1),
        "summary_by_survival_band": {
            "high_>0.8": n_survives_high,
            "mid_0.4_to_0.8": n_survives_mid,
            "low_<0.4": n_survives_low,
            "amplifies_>1.0": n_amplifies,
        },
        "interpretation": (
            "Per Tariq's I5 RECONVENE: High survival (>80%) = Granger-Newbold "
            "concern was overstated for QGI's panel. Mid survival (40-80%) = "
            "substantial substrate cleanup. Low survival (<40%) = Granger-Newbold "
            "was severe; Phase 4 v0.2 sub-random AUC was substantially driven "
            "by spurious structure."
        ),
        "results": survival_results,
        "failed_indicators": failed_indicators,
    }

    survival_path = Path(args.survival_output)
    survival_path.parent.mkdir(parents=True, exist_ok=True)
    survival_path.write_text(
        json.dumps(survival_payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote survival-fraction report: {survival_path}", file=sys.stderr)

    print("\n=== Summary ===", file=sys.stderr)
    print(f"  Total: {len(indicator_ids)}", file=sys.stderr)
    print(f"  Succeeded: {len(survival_results)}", file=sys.stderr)
    print(f"  Failed: {len(failed_indicators)}", file=sys.stderr)
    print(f"  Pairwise demeaning_insufficient flags (Class A only): "
          f"{pairwise_report['summary']['n_demeaning_insufficient']}",
          file=sys.stderr)
    print("  Survival bands:", file=sys.stderr)
    print(f"    high (>0.8):     {n_survives_high}", file=sys.stderr)
    print(f"    mid (0.4-0.8):   {n_survives_mid}", file=sys.stderr)
    print(f"    low (<0.4):      {n_survives_low}", file=sys.stderr)
    print(f"    amplifies (>1):  {n_amplifies}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
