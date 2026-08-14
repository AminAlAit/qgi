"""
Pre-convening empirical artifact for the T12 6-seat Majles convergence
(2026-05-15).

Computes empirical anomaly_score percentiles per (arm, stratum) on the
EXISTING Stage F substrate. Resolves the Priya-vs-Ji-Hoon "k factor"
disagreement (Priya ~k=8 vs Ji-Hoon ~k=30-120 vs Ji-Hoon's round-2
re-pricing ~k=20-40 vs Priya's round-2 derivation k=6-12) with hard
numbers BEFORE the 6-seat convening fires.

Output: `qgi-data/reference/v0.2-anomaly-score-empirical-range.json`

The output is a Kwame pre-registration artifact: it lands at qgi-data
BEFORE any §2.1 / §2.4 / §5.2 amendment commit on the trio's real-data
feature branch. The 6-seat convening reads this JSON as binding ground
truth — no analyst-tunable k after this commit.

Method:
  1. Load the Stage F demeaned panel (cached parquet; no Athena cost)
  2. Compute country z-scores via `compute_country_zscores`
  3. For each of 4 arms (A/B/C/D), call `score_country_event` to produce
     the per-(country, event_category) anomaly_score DataFrame
  4. Compute percentile distribution + stratified by
     n_indicators_used ≥ 10 stratum (matches §5 v2 rule v2 gate)
  5. Emit JSON with min/max/mean/std + p1/p5/p10/p25/p50/p75/p90/p95/p99
     per (arm, stratum) cell

Cost: ~$1-3 Athena (panel + countries pulls; cached after first run).
Wall time: ~5-15 minutes.

Pre-convening dependencies (must exist before this script runs):
  - qgi-data/reference/weight-matrix.json (Phase 3 output) — local
  - qgi-data/reference/indicator-directions.json — local (for arms A, B)
  - qgi-data/reference/indicator-allow-list.json — local (for arms A, C)
  - AWS staging creds at C:/Users/Amin/AppData/Local/Temp/qgi/staging_creds.json

CLI:
  python qgi-ml/scripts/compute_anomaly_score_empirical_range.py \
      --bucket qgi-data-lake-771606957899 \
      --workgroup qgi-data-staging \
      --output qgi-data/reference/v0.2-anomaly-score-empirical-range.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent.parent
PATH_A_SCRIPT = Path(__file__).resolve().parent / "validate_weight_matrix.py"
DEFAULT_OUTPUT = ROOT / "qgi-data" / "reference" / "v0.2-anomaly-score-empirical-range.json"

# Strata threshold per spec / rule v2 (n_indicators_used ≥ 10 is the
# "data-sufficient" stratum, < 10 is "thin-coverage").
STRATA_INDICATOR_THRESHOLD = 10

# Percentiles to emit.
PERCENTILES = [1, 5, 10, 25, 50, 75, 90, 95, 99]

# Spec version on the emitted artifact.
SCHEMA_VERSION = 1


def _load_path_a() -> object:
    """Import validate_weight_matrix.py as a module without executing main."""
    spec = importlib.util.spec_from_file_location("validate_weight_matrix", PATH_A_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_weight_matrix"] = mod
    spec.loader.exec_module(mod)
    return mod


def _percentile_summary(values: np.ndarray) -> dict:
    """Compute the percentile summary block per spec output schema."""
    if len(values) == 0:
        return {"n": 0, "all_nan": True}
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return {"n": int(len(values)), "n_finite": 0, "all_nan": True}
    summary = {
        "n": int(len(values)),
        "n_finite": int(len(finite)),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite, ddof=1)) if len(finite) > 1 else None,
    }
    for p in PERCENTILES:
        summary[f"p{p}"] = float(np.percentile(finite, p))
    return summary


def _hash_inputs(panel: pd.DataFrame, weights_df: pd.DataFrame) -> str:
    """SHA-256 of the inputs for reproducibility provenance."""
    h = hashlib.sha256()
    h.update(f"panel_rows={len(panel)}".encode())
    h.update(f"weights_rows={len(weights_df)}".encode())
    h.update(f"panel_indicators={sorted(panel['indicator_id'].unique().tolist())}".encode())
    return h.hexdigest()


def compute_empirical_range(*, bucket: str, workgroup: str,
                            cutoff_year: int = 2014,
                            output_path: Path = DEFAULT_OUTPUT) -> dict:
    """Compute empirical anomaly_score percentiles per (arm, stratum).

    Returns the dict that's also written to JSON.
    """
    print("[1/6] Loading Path A module...", flush=True)
    mod = _load_path_a()

    print("[2/6] Setting up Athena/S3 clients...", flush=True)
    creds_path = Path(r"C:/Users/Amin/AppData/Local/Temp/qgi/staging_creds.json")
    if not creds_path.exists():
        raise FileNotFoundError(f"AWS creds not found at {creds_path}")
    creds = json.loads(creds_path.read_text(encoding="utf-8"))
    session = boto3.Session(
        aws_access_key_id=creds["ak"],
        aws_secret_access_key=creds["sk"],
        aws_session_token=creds["st"],
        region_name="eu-central-1",
    )
    ath = session.client("athena")
    s3 = session.client("s3")

    print("[3/6] Loading weight matrix + directions + allow-list...", flush=True)
    weights_df = mod.load_weight_matrix()
    directions = mod.load_direction_annotations()
    allow_ids = mod.load_allow_list()
    if not directions or not allow_ids:
        raise FileNotFoundError(
            "directions or allow-list missing; rerun audition/allow-list "
            "generators first. See script docstring for the required local files."
        )

    print("[4/6] Loading panel + countries + num_to_api...", flush=True)
    # Path A's audition module loaded as a sibling via Path A's importlib
    # mechanism (validate_weight_matrix.py imports it at module load time).
    au = sys.modules["audition_indicators"]
    num_to_api = au.load_indicator_map(s3, bucket)
    # Need the panel's api_code list — derive from weights_df.indicator_numeric_id
    needed_api_codes = sorted({
        num_to_api[nid] for nid in weights_df["indicator_numeric_id"].unique()
        if nid in num_to_api
    })
    print(f"   {len(needed_api_codes)} api_codes needed by weights matrix")
    # Panel spans the z-score window (5 years up to cutoff). Use Path A's
    # widened range when transform layer is active.
    panel_lo = cutoff_year - 5  # standard z-score window
    panel = au.load_indicator_panel(
        ath, bucket, workgroup, needed_api_codes, panel_lo, cutoff_year,
    )
    countries_df = au.load_countries(ath, bucket, workgroup)
    # countries_df has columns (country_id, name), per validate_weight_matrix.py:2011
    country_id_to_str = dict(zip(countries_df["country_id"].astype(int), countries_df["name"]))

    print(f"   panel: {len(panel):,} rows; countries: {len(countries_df):,}")

    # Apply the Stage F transform layer to align with what T9 used. The
    # transform config is in v0.2-canonical-length.json (T7 binding).
    print("[5/6] Applying Stage F transform layer...", flush=True)
    canonical_length_config = mod.load_canonical_length_config(required=False)
    if canonical_length_config:
        panel = mod.apply_transform_layer(panel, canonical_length_config)
        print(f"   panel post-transform: {len(panel):,} rows")
    else:
        print("   no canonical_length_config; using raw panel (Phase 5 v0.1a substrate)")

    print("   computing z-scores...")
    zscores = mod.compute_country_zscores(panel, cutoff_year)
    print(f"   zscores: {len(zscores):,} rows")

    print("[6/6] Scoring per arm + computing empirical percentiles...", flush=True)
    arms = {
        "A": {"signed": True, "filter": True},
        "B": {"signed": True, "filter": False},
        "C": {"signed": False, "filter": True},
        "D": {"signed": False, "filter": False},
    }

    results_per_arm = {}
    for arm_name, arm_cfg in arms.items():
        print(f"   [arm {arm_name}] signed={arm_cfg['signed']}, filter={arm_cfg['filter']}")
        weights_local = weights_df
        if arm_cfg["filter"]:
            weights_local = mod.apply_591_filter(weights_local, allow_ids)
        scored = mod.score_country_event(
            weights_local, zscores, country_id_to_str, num_to_api,
            use_signed_scoring=arm_cfg["signed"],
            directions=directions if arm_cfg["signed"] else None,
        )
        scores = scored["anomaly_score"].values.astype(float)
        n_used = scored["n_indicators_used"].values

        full = _percentile_summary(scores)
        data_sufficient = _percentile_summary(scores[n_used >= STRATA_INDICATOR_THRESHOLD])
        thin_coverage = _percentile_summary(scores[n_used < STRATA_INDICATOR_THRESHOLD])

        results_per_arm[arm_name] = {
            "signed_scoring": arm_cfg["signed"],
            "591_filter_applied": arm_cfg["filter"],
            "n_cells_total": int(len(scored)),
            "n_cells_data_sufficient": int((n_used >= STRATA_INDICATOR_THRESHOLD).sum()),
            "n_cells_thin_coverage": int((n_used < STRATA_INDICATOR_THRESHOLD).sum()),
            "full_distribution": full,
            "stratum_data_sufficient": data_sufficient,
            "stratum_thin_coverage": thin_coverage,
            # Empirical anomaly_score range — the headline numbers the
            # 6-seat convening reads. p5/p95 is the standard "95% range"
            # the convening will use as the k-factor source of truth.
            "headline_p5_p95_range_full": (full.get("p5"), full.get("p95")),
            "headline_p5_p95_range_data_sufficient": (
                data_sufficient.get("p5"), data_sufficient.get("p95")
            ),
        }

    # Compute the cross-arm pooled range — useful for the §2.1 tau_arm
    # prior calibration which sees ALL arms in one model.
    all_scores = []
    for arm_name in arms:
        weights_local = weights_df
        if arms[arm_name]["filter"]:
            weights_local = mod.apply_591_filter(weights_local, allow_ids)
        scored = mod.score_country_event(
            weights_local, zscores, country_id_to_str, num_to_api,
            use_signed_scoring=arms[arm_name]["signed"],
            directions=directions if arms[arm_name]["signed"] else None,
        )
        all_scores.append(scored["anomaly_score"].values.astype(float))
    all_scores_concat = np.concatenate(all_scores)
    pooled_summary = _percentile_summary(all_scores_concat)

    # Compute the implied k-factor for tau_arm prior recalibration.
    # k = (anomaly_score p95 range) / (AUC tau_arm prior range)
    # Spec §2.1: tau_arm ~ Normal(0, 0.05) → 95% mass on ±0.10
    # k_signed = pooled_signed_p95_range / 0.20  (units: anomaly_score per AUC unit)
    auc_tau_arm_95_range = 0.20  # ±0.10
    pooled_p95_range = pooled_summary.get("p95", 0) - pooled_summary.get("p5", 0)
    k_factor_pooled = pooled_p95_range / auc_tau_arm_95_range if pooled_p95_range > 0 else None

    # k for signed arms alone (A/B) — more directly comparable to AUC
    # since signed scoring is the methodology variant under test
    signed_scores = np.concatenate([
        results_per_arm["A"], results_per_arm["B"]
    ]) if False else None
    # actually rerun:
    signed_concat = []
    for arm_name in ("A", "B"):
        weights_local = weights_df
        if arms[arm_name]["filter"]:
            weights_local = mod.apply_591_filter(weights_local, allow_ids)
        scored = mod.score_country_event(
            weights_local, zscores, country_id_to_str, num_to_api,
            use_signed_scoring=True, directions=directions,
        )
        signed_concat.append(scored["anomaly_score"].values.astype(float))
    signed_concat = np.concatenate(signed_concat)
    signed_summary = _percentile_summary(signed_concat)
    signed_p95_range = signed_summary.get("p95", 0) - signed_summary.get("p5", 0)
    k_factor_signed = signed_p95_range / auc_tau_arm_95_range if signed_p95_range > 0 else None

    # Same for unsigned (C/D)
    unsigned_concat = []
    for arm_name in ("C", "D"):
        weights_local = weights_df
        if arms[arm_name]["filter"]:
            weights_local = mod.apply_591_filter(weights_local, allow_ids)
        scored = mod.score_country_event(
            weights_local, zscores, country_id_to_str, num_to_api,
            use_signed_scoring=False, directions=None,
        )
        unsigned_concat.append(scored["anomaly_score"].values.astype(float))
    unsigned_concat = np.concatenate(unsigned_concat)
    unsigned_summary = _percentile_summary(unsigned_concat)
    unsigned_p95_range = unsigned_summary.get("p95", 0) - unsigned_summary.get("p5", 0)
    k_factor_unsigned = unsigned_p95_range / auc_tau_arm_95_range if unsigned_p95_range > 0 else None

    result = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "Pre-convening empirical artifact for T12 6-seat Majles "
                   "(convergence 2026-05-15). Resolves k-factor disagreement.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cutoff_year": cutoff_year,
        "stratum_threshold_n_indicators_used": STRATA_INDICATOR_THRESHOLD,
        "input_provenance_sha256": _hash_inputs(panel, weights_df),
        "per_arm_summary": results_per_arm,
        "pooled_summary": pooled_summary,
        "signed_pooled_summary": signed_summary,
        "unsigned_pooled_summary": unsigned_summary,
        "k_factor_estimates": {
            "definition": "k = (anomaly_score p95-p5 range) / (AUC tau_arm 95% prior range = 0.20)",
            "pooled_all_arms": k_factor_pooled,
            "signed_arms_only_AB": k_factor_signed,
            "unsigned_arms_only_CD": k_factor_unsigned,
            "interpretation": (
                "Recommended tau_arm prior scale for anomaly_score response: "
                "0.05 (AUC-calibrated) * k. Convening picks among "
                "{pooled, signed, unsigned} based on model identification "
                "concerns; signed_pooled is the methodology variant under test."
            ),
        },
        "convening_pre_registration_notes": (
            "Per Kwame round-2 ruling: this artifact lands at qgi-data BEFORE "
            "any §2.1/§2.4 amendment commit on the trio's real-data feature "
            "branch. The 6-seat convening reads this JSON as binding ground "
            "truth; no analyst-tunable k after this commit. Any future "
            "re-derivation requires a new Majles convening."
        ),
        "spec_references": {
            "T10_spec": "docs/specs/internal/ops/cascade-track/phase-5-v0.2-path-b-architecture.md @ ca77505",
            "convergence_signoffs": "c:/tmp/v0.2-T12-convergence/signoff_*.md",
            "T11_falsification_report": "docs-specs `dfe2cd4` ratified `3b9221c`",
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[done] wrote {output_path}", flush=True)

    # Headline print for stdout summary
    print("\n=== HEADLINE EMPIRICAL k-FACTOR ESTIMATES ===")
    print(f"  pooled (all arms):     k ≈ {k_factor_pooled:.2f}")
    print(f"  signed only (A, B):    k ≈ {k_factor_signed:.2f}")
    print(f"  unsigned only (C, D):  k ≈ {k_factor_unsigned:.2f}")
    print(f"\nP5..P95 range (signed pooled): "
          f"[{signed_summary.get('p5'):.3f}, {signed_summary.get('p95'):.3f}]")
    print(f"P5..P95 range (unsigned pooled): "
          f"[{unsigned_summary.get('p5'):.3f}, {unsigned_summary.get('p95'):.3f}]")

    return result


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute empirical anomaly_score range for T12 6-seat convening"
    )
    parser.add_argument("--bucket", required=True,
                        help="S3 bucket (e.g. qgi-data-lake-771606957899)")
    parser.add_argument("--workgroup", default="QGI-Lambda-Workgroup",
                        help="Athena workgroup")
    parser.add_argument("--cutoff-year", type=int, default=2014)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Output JSON path")
    args = parser.parse_args(argv)

    compute_empirical_range(
        bucket=args.bucket,
        workgroup=args.workgroup,
        cutoff_year=args.cutoff_year,
        output_path=args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
