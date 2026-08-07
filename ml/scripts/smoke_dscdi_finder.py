"""
smoke_dscdi_finder.py — Phase 5 v0.0b Stage C smoke verification.

# THROWAWAY in spirit (one-shot verification) but committed for re-runnability.

Pulls ONE indicator's parquet from S3, applies the DSCDI two-pass algorithm
from `qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py`, and prints the
diagnostic (Class assignment, transformation, baseline-vs-primary mean abs
correlation, demeaning-insufficient flag).

Cost: ~$0 (1 S3 GET).
Time: ~5 seconds.

Per founder direction 2026-05-04 / 2026-05-05: cascade-Opus does NOT run
the full 109-indicator DSCDI computation. That's Stage F (deferred to end-
of-mandate test-run). This smoke is a single-indicator sanity check on
the methodology code, not a production execution.

Usage:
  # Smoke on the most CSD-extreme Class A indicator:
  python qgi-ml/scripts/smoke_dscdi_finder.py \\
      --bucket qgi-data-lake-771606957899 \\
      --indicator-id v2x_libdem \\
      --classification I(1)

  # Smoke on a Class B (WGI) indicator — should NOT demean:
  python qgi-ml/scripts/smoke_dscdi_finder.py \\
      --bucket qgi-data-lake-771606957899 \\
      --indicator-id RL.EST \\
      --classification I(1)

  # Smoke on the SP.POP.TOTL outlier (log-difference path):
  python qgi-ml/scripts/smoke_dscdi_finder.py \\
      --bucket qgi-data-lake-771606957899 \\
      --indicator-id SP.POP.TOTL \\
      --classification I(2)_or_higher
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import boto3
import pandas as pd
import pyarrow.parquet as pq
import s3fs

# Load the DSCDI module from qgi-pipeline (next to qgi-ml in the monorepo)
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
DSCDI_MODULE_PATH = (
    REPO_ROOT / "qgi-pipeline" / "batch" / "dscdi-finder" / "src" / "dscdi_finder.py"
)

_spec = importlib.util.spec_from_file_location("dscdi_finder", DSCDI_MODULE_PATH)
dscdi = importlib.util.module_from_spec(_spec)
sys.modules["dscdi_finder"] = dscdi  # required for Python 3.14 dataclass introspection
_spec.loader.exec_module(dscdi)


INDICATOR_PREFIX = "pipeline-A-indicator-extractor/output/parquet-completed/"


def load_indicator_panel(s3fs_, bucket: str, indicator_id: str) -> pd.DataFrame:
    key = f"{INDICATOR_PREFIX}{indicator_id}/{indicator_id}.parquet"
    with s3fs_.open(f"{bucket}/{key}", "rb") as fh:
        df = pq.ParquetFile(fh).read().to_pandas()
    df = df.dropna(subset=["value"])
    df = df.drop_duplicates(subset=["country", "year"], keep="last")
    return df.pivot(index="year", columns="country", values="value").sort_index()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--indicator-id", required=True,
                        help="e.g. v2x_libdem, RL.EST, SP.POP.TOTL")
    parser.add_argument("--classification", required=True,
                        choices=["I(0)", "I(1)", "I(2)_or_higher", "ambiguous"],
                        help="Stage A v2 audit classification for this indicator")
    args = parser.parse_args()

    print(f"=== Stage C DSCDI smoke: {args.indicator_id} ({args.classification}) ===",
          file=sys.stderr)

    s3fs_ = s3fs.S3FileSystem()
    print(f"Loading panel from s3://{args.bucket}/{INDICATOR_PREFIX}{args.indicator_id}/...",
          file=sys.stderr)
    panel = load_indicator_panel(s3fs_, args.bucket, args.indicator_id)
    print(f"  panel shape: {panel.shape} (years x countries)", file=sys.stderr)

    # Resolve disposition first (no compute)
    disposition = dscdi.resolve_disposition(args.indicator_id, args.classification)
    print("\n--- Disposition ---", file=sys.stderr)
    print(f"  indicator_class: {disposition.indicator_class}", file=sys.stderr)
    print(f"  transform: {disposition.transform}", file=sys.stderr)

    # Run the full pass
    result = dscdi.run_dscdi_pass(
        args.indicator_id, panel, args.classification
    )

    print("\n--- DSCDI Pass Result ---", file=sys.stderr)
    print(f"  n_countries (after min_obs filter): {result.n_countries}",
          file=sys.stderr)
    if result.baseline_undemeaned is not None:
        baseline_mean_abs = dscdi._mean_abs_pairwise_off_diagonal(
            result.baseline_undemeaned
        )
        print(f"  baseline (undemeaned) mean abs pairwise corr: "
              f"{baseline_mean_abs:.4f}", file=sys.stderr)
    print(f"  primary mean abs pairwise corr: "
          f"{result.mean_abs_pairwise_corr:.4f}", file=sys.stderr)
    print(f"  demeaning_insufficient flag (>0.25): "
          f"{result.demeaning_insufficient}", file=sys.stderr)

    if result.demeaning_insufficient:
        print(f"\n[FLAG] {args.indicator_id}: demeaning insufficient. "
              f"Phase 6 EB framework receives architecture note. "
              f"Miriam consultation required before EB code ships.",
              file=sys.stderr)
    else:
        print(f"\n[OK] {args.indicator_id}: demeaning sufficient. "
              f"Pass-through to Phase 6.", file=sys.stderr)

    # Print first few rows of the primary correlation matrix as visual sanity
    print("\n--- Primary correlation matrix (first 5x5) ---", file=sys.stderr)
    if result.primary.shape[0] >= 5:
        sample = result.primary.iloc[:5, :5].round(3)
        print(sample.to_string(), file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
