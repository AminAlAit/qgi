"""
run_v0_2_demeaned_spotcheck.py — Phase 5 v0.2 T6 spot-check audit (#670).

Tariq pre-condition #1 (charter §148, T5 DECISION §8.1). Re-audits 9
indicators on the DEMEANED substrate (Stage F transform_panel +
demean_cross_section chain) and compares each verdict to the v2 baseline
(`indicator-stationarity-audit-v2.json`) which was run on the
UN-DEMEANED panel.

If any indicator flips I(0) ↔ I(1) classification on the demeaned series,
T7's v0.2 disposition file must be surgically updated before any Path A
arm fires.

# THROWAWAY in spirit (one-shot per cascade-track convening) but committed
# for re-runnability. Re-run only if the Stage F transform chain or the
# v2 audit baseline changes.

Methodology mirrors `run_i5_substrate_audit.py` (the v2 baseline generator):
  - Per-country ADF (statsmodels.tsa.stattools.adfuller, autolag="AIC",
    regression="c") with majority-vote aggregation
  - min_obs_required = 15 per Stage B QA review
  - Classification thresholds: I(0) if >=70% reject at level; I(1) if
    >=70% reject at first-difference; I(2) if <30% at both; ambiguous otherwise.

Stage F transform chain mirrored verbatim from
`qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py`:
  - OUTLIER_NO_TRANSFORM = {"NY.GDP.MKTP.KD.ZG"} — pass_through, no demeaning
  - OUTLIER_LOG_DIFFERENCE = {"SP.POP.TOTL"} — log_diff, then demean
  - CLASS_A_SEVERE_CSD members get first_diff (if I(1)) then demean
  - V-Dem indicators are NOT in CLASS_A_SEVERE_CSD or CLASS_B_WGI, so they
    fall under Class C (per-classification transform; no demeaning).

Cost: ~$0 (cached parquet read from S3, local Python compute). No Athena.
No founder per-session approval needed.

Usage:
  python qgi-ml/scripts/run_v0_2_demeaned_spotcheck.py \\
      --bucket qgi-data-lake-771606957899 \\
      --v2-baseline qgi-data/reference/indicator-stationarity-audit-v2.json \\
      --output qgi-data/reference/audit-v2-demeaned-spotcheck.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import s3fs

# ---------------------------------------------------------------------------
# T6 target indicators (per T5 DECISION §8.1 / charter A6 spot-check spec)
# ---------------------------------------------------------------------------

T6_TARGETS = [
    # 4 demeaning-insufficient Class A flags (Stage E pairwise diagnostic scores)
    {"id": "FP.CPI.TOTL.ZG", "category": "class_a_severe_csd_demeaning_insufficient",
     "stage_e_pairwise_corr": 0.66},
    {"id": "NY.GDP.PCAP.CD", "category": "class_a_severe_csd_demeaning_insufficient",
     "stage_e_pairwise_corr": 0.54},
    {"id": "SH.DYN.MORT", "category": "class_a_severe_csd_demeaning_insufficient",
     "stage_e_pairwise_corr": 0.36},
    {"id": "SP.POP.TOTL", "category": "class_a_severe_csd_demeaning_insufficient",
     "stage_e_pairwise_corr": 0.31},
    # 5 random-draw V-Dem low-survival tail
    {"id": "v2elintmon", "category": "v_dem_low_survival_random_draw"},
    {"id": "v2x_regime", "category": "v_dem_low_survival_random_draw"},
    {"id": "v2x_gender", "category": "v_dem_low_survival_random_draw"},
    {"id": "v2pepwrgen", "category": "v_dem_low_survival_random_draw"},
    {"id": "v2x_partip", "category": "v_dem_low_survival_random_draw"},
]

# ---------------------------------------------------------------------------
# Stage F transform-chain constants (mirrored from qgi-pipeline dscdi_finder.py)
# ---------------------------------------------------------------------------

CLASS_A_SEVERE_CSD: frozenset[str] = frozenset({
    "v2x_libdem", "NY.GDP.PCAP.CD", "FP.CPI.TOTL.ZG", "SL.UEM.TOTL.ZS",
    "CC.EST",
    "v2x_polyarchy", "MS.MIL.XPND.GD.ZS", "NE.EXP.GNFS.ZS", "NE.IMP.GNFS.ZS",
    "SE.PRM.ENRR", "SH.DYN.MORT", "SP.DYN.LE00.IN", "SP.DYN.TFRT.IN",
    "IT.CEL.SETS.P2",
})
CLASS_B_WGI: frozenset[str] = frozenset({
    "RL.EST", "GE.EST", "RQ.EST", "PS.EST", "VA.EST",
})
OUTLIER_NO_TRANSFORM: frozenset[str] = frozenset({"NY.GDP.MKTP.KD.ZG"})
OUTLIER_LOG_DIFFERENCE: frozenset[str] = frozenset({"SP.POP.TOTL"})

INDICATOR_PREFIX = "pipeline-A-indicator-extractor/output/parquet-completed/"
STAGE_F_MANIFEST_PREFIX = "pipeline-B-dscdi-finder/manifest/"

# ADF / classification thresholds — verbatim from run_i5_substrate_audit.py
P_REJECT = 0.05
ADF_FRAC_THRESHOLDS = {
    "I(0)_strong": 0.70,
    "I(1)_strong": 0.30,
    "I(2)_strong": 0.30,
}
MIN_OBS_REQUIRED = 15


# ---------------------------------------------------------------------------
# Stage F transform helpers (mirrored verbatim from dscdi_finder.py)
# ---------------------------------------------------------------------------

def determine_transform_and_demean(
    indicator_id: str, audit_classification: str
) -> tuple[str, bool]:
    """Replicate qgi-pipeline's IndicatorDisposition logic, return:
        (transform, demean_applied)
    where transform ∈ {"pass_through", "first_diff", "log_diff"}.

    Per qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py.
    """
    if indicator_id in OUTLIER_NO_TRANSFORM:
        return "pass_through", False  # Class A but demeaning suppressed
    if indicator_id in OUTLIER_LOG_DIFFERENCE:
        return "log_diff", True  # Class A, log-difference + demean

    if indicator_id in CLASS_A_SEVERE_CSD:
        cls = "A"
    elif indicator_id in CLASS_B_WGI:
        cls = "B"
    else:
        cls = "C"

    # Transform driven by audit_classification
    if audit_classification == "I(0)":
        transform = "pass_through"
    elif audit_classification == "I(1)":
        transform = "first_diff"
    elif audit_classification == "I(2)_or_higher":
        # INTENTIONAL DIVERGENCE FROM PIPELINE — documented per T6 PR #57
        # review (NIT 1). qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py
        # raises ValueError here (forces Tariq consultation before any
        # I(2)_or_higher indicator outside OUTLIER_LOG_DIFFERENCE ships
        # to production Stage C correlation output). For a one-shot AUDIT
        # script we use the conservative `first_diff` fallback instead —
        # the audit's purpose is to RE-CLASSIFY on the demeaned substrate,
        # not to compute production correlations, so audit robustness
        # outweighs the consultation-gate forcing function.
        #
        # In the 9-target T6 set, the only I(2) indicator (SP.POP.TOTL)
        # is short-circuited by OUTLIER_LOG_DIFFERENCE before reaching
        # this branch, so this fallback IS NOT EXERCISED on T6. If a
        # future T-style audit adds I(2) indicators outside the outlier
        # set, this branch fires — the warning print below makes the
        # divergence visible at run time.
        transform = "first_diff"
        print(
            f"  [WARN] {indicator_id}: I(2)_or_higher classification reached "
            f"the conservative first_diff fallback. Pipeline would have raised "
            f"ValueError here; audit script uses fallback for robustness. "
            f"Tariq consultation required before any production use.",
            file=sys.stderr,
        )
    elif audit_classification == "ambiguous":
        transform = "first_diff"  # conservative default (matches pipeline)
    else:
        transform = "pass_through"

    demean = cls == "A"
    return transform, demean


def transform_panel(panel: pd.DataFrame, transform: str) -> pd.DataFrame:
    """Replicate qgi-pipeline transform_panel verbatim."""
    if transform == "pass_through":
        return panel.copy()
    if transform == "first_diff":
        return panel.diff()
    if transform == "log_diff":
        positive = panel.where(panel > 0)
        return np.log(positive).diff()
    raise ValueError(f"unknown transform: {transform}")


def demean_cross_section(transformed: pd.DataFrame) -> pd.DataFrame:
    """Replicate qgi-pipeline demean_cross_section verbatim."""
    cross_section_mean = transformed.mean(axis=1, skipna=True)
    return transformed.sub(cross_section_mean, axis=0)


# ---------------------------------------------------------------------------
# ADF classifier (mirrored verbatim from run_i5_substrate_audit.py)
# ---------------------------------------------------------------------------

def classify_indicator_adf_fallback(panel: pd.DataFrame) -> dict[str, Any]:
    """Per-country ADF fallback — VERBATIM from run_i5_substrate_audit.py
    so the demeaned spot-check is methodologically apples-to-apples with
    the v2 baseline.
    """
    from statsmodels.tsa.stattools import adfuller

    countries = list(panel.columns)
    n_countries = len(countries)
    rejected_at_level = 0
    rejected_at_diff = 0
    countries_tested_at_level = 0
    countries_tested_at_diff = 0

    for country in countries:
        series = panel[country].dropna()
        if len(series) < MIN_OBS_REQUIRED:
            continue
        countries_tested_at_level += 1
        try:
            p_level = adfuller(series, autolag="AIC", regression="c")[1]
        except Exception:
            p_level = 1.0
        if p_level < P_REJECT:
            rejected_at_level += 1
        diffed = series.diff().dropna()
        if len(diffed) < MIN_OBS_REQUIRED:
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


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_indicator_panel(s3fs_: s3fs.S3FileSystem, bucket: str,
                          indicator_id: str) -> pd.DataFrame | None:
    """Load one indicator's parquet, pivot to wide panel (rows=year, cols=country)."""
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
    df = df.dropna(subset=["value"])
    df = df.drop_duplicates(subset=["country", "year"], keep="last")
    panel = df.pivot(index="year", columns="country", values="value").sort_index()
    return panel


def load_stage_f_manifest(s3fs_: s3fs.S3FileSystem, bucket: str,
                           indicator_id: str) -> dict | None:
    """Load the Stage F manifest entry for one indicator (or None if absent)."""
    key = f"{STAGE_F_MANIFEST_PREFIX}{indicator_id}.parquet"
    try:
        with s3fs_.open(f"{bucket}/{key}", "rb") as fh:
            df = pq.ParquetFile(fh).read().to_pandas()
    except Exception:
        return None
    if df.empty:
        return None
    row = df.iloc[0].to_dict()
    # Strip non-JSON-serializable types
    out = {}
    for k, v in row.items():
        if pd.isna(v):
            out[k] = None
        elif isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.floating,)):
            out[k] = float(v)
        elif isinstance(v, (np.bool_,)):
            out[k] = bool(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument(
        "--v2-baseline",
        type=Path,
        required=True,
        help="Path to indicator-stationarity-audit-v2.json (the un-demeaned baseline)",
    )
    parser.add_argument(
        "--creds",
        type=Path,
        default=Path(r"C:/Users/Amin/AppData/Local/Temp/qgi/staging_creds.json"),
        help="Path to staging AWS creds JSON (ak/sk/st)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write the spot-check JSON",
    )
    args = parser.parse_args()

    # Load creds for s3fs (cred file overrides ambient AWS env)
    creds = json.loads(args.creds.read_text())
    fs = s3fs.S3FileSystem(
        key=creds["ak"], secret=creds["sk"], token=creds["st"],
        client_kwargs={"region_name": "eu-central-1"},
    )

    # Load v2 baseline (un-demeaned panel verdicts)
    v2 = json.loads(args.v2_baseline.read_text(encoding="utf-8"))
    v2_results = v2["results"]
    v2_audit_method = v2.get("test_method", "?")

    audit_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    per_indicator: list[dict[str, Any]] = []

    for spec in T6_TARGETS:
        ind_id = spec["id"]
        v2_entry = v2_results.get(ind_id)
        if v2_entry is None:
            per_indicator.append({
                **spec,
                "v2_classification_undemeaned": None,
                "demeaned_classification": "v2_baseline_absent",
                "verdict_flipped": None,
                "error": "indicator not in v2 baseline JSON",
            })
            print(f"  [{ind_id}] NOT IN V2 BASELINE; skipping",
                  file=sys.stderr)
            continue
        v2_cls = v2_entry["classification"]

        # Load Stage F manifest to determine transform + demean_applied for this indicator
        manifest = load_stage_f_manifest(fs, args.bucket, ind_id)
        stage_f_transform = manifest.get("transform") if manifest else None
        stage_f_demean_applied = (
            manifest.get("demeaning_applied") if manifest else None
        )
        stage_f_demean_insufficient = (
            manifest.get("demeaning_insufficient") if manifest else None
        )

        # Derive transform locally (for cross-check + fallback if manifest absent)
        derived_transform, derived_demean = determine_transform_and_demean(
            ind_id, v2_cls
        )

        # Load raw panel from pipeline-A
        panel = load_indicator_panel(fs, args.bucket, ind_id)
        if panel is None:
            per_indicator.append({
                **spec,
                "v2_classification_undemeaned": v2_cls,
                "demeaned_classification": "load_failed",
                "verdict_flipped": None,
                "stage_f_manifest": manifest,
                "derived_transform": derived_transform,
                "derived_demean_applied": derived_demean,
                "error": "raw panel could not be loaded",
            })
            continue

        # Apply Stage F chain: transform → demean (only if Class A per dispatch)
        transform_used = (
            stage_f_transform if stage_f_transform else derived_transform
        )
        demean_used = (
            stage_f_demean_applied if stage_f_demean_applied is not None
            else derived_demean
        )

        transformed = transform_panel(panel, transform_used)
        substrate = (
            demean_cross_section(transformed) if demean_used else transformed
        )

        # Re-run per-country ADF on the demeaned series
        try:
            adf_result = classify_indicator_adf_fallback(substrate)
        except Exception as exc:
            per_indicator.append({
                **spec,
                "v2_classification_undemeaned": v2_cls,
                "demeaned_classification": "adf_failed",
                "verdict_flipped": None,
                "stage_f_manifest": manifest,
                "derived_transform": derived_transform,
                "derived_demean_applied": derived_demean,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        demeaned_cls = adf_result["classification"]

        # Flip detection: I(0) ↔ I(1) is the load-bearing flip per the T6
        # ticket; ambiguous transitions are also surfaced but not classed as
        # "load-bearing" flips.
        i01_pair = {"I(0)", "I(1)"}
        load_bearing_flip = (
            v2_cls in i01_pair and demeaned_cls in i01_pair and v2_cls != demeaned_cls
        )
        any_flip = v2_cls != demeaned_cls

        per_indicator.append({
            **spec,
            "v2_classification_undemeaned": v2_cls,
            "v2_frac_rejected_at_level": v2_entry.get("frac_rejected_at_level"),
            "v2_frac_rejected_at_diff": v2_entry.get("frac_rejected_at_diff"),
            "demeaned_classification": demeaned_cls,
            "demeaned_frac_rejected_at_level": adf_result["frac_rejected_at_level"],
            "demeaned_frac_rejected_at_diff": adf_result["frac_rejected_at_diff"],
            "demeaned_n_countries_tested_at_level": adf_result["n_countries_tested_at_level"],
            "demeaned_n_countries_tested_at_diff": adf_result["n_countries_tested_at_diff"],
            "demeaned_n_countries_total": adf_result["n_countries_total"],
            "any_flip": any_flip,
            "load_bearing_flip_i0_i1": load_bearing_flip,
            "stage_f_manifest": manifest,
            "transform_used": transform_used,
            "demean_applied": demean_used,
        })

        v2_str = v2_cls
        new_str = demeaned_cls
        flip_str = "FLIP" if load_bearing_flip else ("change" if any_flip else "stable")
        print(
            f"  [{ind_id:>20}] v2={v2_str:>14}  demeaned={new_str:>14}  "
            f"{flip_str}",
            file=sys.stderr,
        )

    # Aggregate
    n_load_bearing_flips = sum(
        1 for r in per_indicator if r.get("load_bearing_flip_i0_i1")
    )
    n_any_flips = sum(1 for r in per_indicator if r.get("any_flip"))

    if n_load_bearing_flips > 0:
        aggregate_verdict = "FLIPS_DETECTED"
        aggregate_action = (
            f"{n_load_bearing_flips} of 9 indicators flipped I(0) ↔ I(1) on the "
            f"demeaned substrate. v0.2 disposition file MUST be surgically updated "
            f"before any Path A arm fires; T7 phase doc must cite this audit's "
            f"commit SHA."
        )
    elif n_any_flips > 0:
        aggregate_verdict = "NON_LOAD_BEARING_CHANGES"
        aggregate_action = (
            f"{n_any_flips} of 9 indicators changed classification on the demeaned "
            f"substrate but no I(0) ↔ I(1) flip. v0.2 disposition file may be "
            f"updated (optional); Path A can proceed without modification."
        )
    else:
        aggregate_verdict = "NO_FLIPS"
        aggregate_action = (
            "All 9 audited indicators retain their v2 baseline classification on "
            "the demeaned substrate. v0.2 disposition file requires no update; "
            "Path A can proceed."
        )

    output = {
        "schema_version": 1,
        "generator": "qgi-ml/scripts/run_v0_2_demeaned_spotcheck.py",
        "audit_date": audit_date,
        "purpose": (
            "Phase 5 v0.2 T6 spot-check audit (#670). Tariq pre-condition #1 "
            "per charter §148 / T5 DECISION §8.1. Re-audits 9 indicators on the "
            "DEMEANED substrate (Stage F transform + demean chain) and compares "
            "to the un-demeaned v2 baseline. Detects I(0)/I(1) classification "
            "flips that would require a v0.2 disposition-file update before "
            "Path A arms fire."
        ),
        "provenance": {
            "charter_commit_sha": "bcf656c",
            "charter_path": "docs/specs/internal/ops/cascade-track/phase-5-v0.2-charter.md",
            "t5_decision_commit_sha": "a434cdf",
            "t5_decision_path": (
                "docs/specs/internal/majles/in-progress/"
                "2026-05-12_Ihsa_v0.2_gamma_gate_DECISION.md"
            ),
            "pre_reg_spec_commit_sha": "a2f5db4",
            "pre_reg_spec_path": (
                "docs/specs/internal/ops/cascade-track/phase-5-v0.2-spec.md"
            ),
            "v2_baseline_path": str(args.v2_baseline),
            "v2_baseline_generator": "qgi-ml/scripts/run_i5_substrate_audit.py",
            "stage_f_source_file": (
                "qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py "
                "(transform_panel + demean_cross_section + "
                "CLASS_A_SEVERE_CSD / CLASS_B_WGI / OUTLIER_NO_TRANSFORM / "
                "OUTLIER_LOG_DIFFERENCE)"
            ),
            "audit_script": "qgi-ml/scripts/run_v0_2_demeaned_spotcheck.py",
        },
        "v2_baseline_test_method": v2_audit_method,
        "test_method": "per_country_adf_fallback",
        "test_method_note": (
            "Verbatim mirror of run_i5_substrate_audit.py methodology — same ADF "
            "(autolag='AIC', regression='c'), same min_obs_required=15, same "
            "classification thresholds. Stage F transform chain mirrored verbatim "
            "from qgi-pipeline/batch/dscdi-finder/src/dscdi_finder.py "
            "(determine_transform_and_demean + transform_panel + "
            "demean_cross_section). One INTENTIONAL DIVERGENCE from the pipeline: "
            "the I(2)_or_higher branch uses a conservative first_diff fallback "
            "instead of raising ValueError, for audit robustness — see script "
            "docstring and inline comment at determine_transform_and_demean."
        ),
        "decision_rule": {
            "I(0)_threshold_frac_rejected_at_level": ADF_FRAC_THRESHOLDS["I(0)_strong"],
            "I(1)_threshold_frac_rejected_at_diff": ADF_FRAC_THRESHOLDS["I(0)_strong"],
            "I(2)_threshold_frac_rejected_at_diff": ADF_FRAC_THRESHOLDS["I(2)_strong"],
            "p_reject": P_REJECT,
            "min_obs_required": MIN_OBS_REQUIRED,
        },
        "indicators_audited": len(per_indicator),
        "n_load_bearing_flips_i0_i1": n_load_bearing_flips,
        "n_any_classification_changes": n_any_flips,
        "aggregate_verdict": aggregate_verdict,
        "aggregate_action": aggregate_action,
        "results": per_indicator,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    print("\n--- Summary ---", file=sys.stderr)
    print(f"  Indicators audited: {len(per_indicator)}", file=sys.stderr)
    print(f"  Load-bearing flips (I(0) ↔ I(1)): {n_load_bearing_flips}", file=sys.stderr)
    print(f"  Any-classification changes:        {n_any_flips}", file=sys.stderr)
    print(f"  Aggregate verdict: {aggregate_verdict}", file=sys.stderr)
    print(f"\nWrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
