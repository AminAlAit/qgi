"""# THROWAWAY -- one-off audit script (parallel to
run_structural_break_audit.py and run_loco_diagnosis.py). Phase D D1
ICC continuous shrinkage weight audit on the engineered feature panel.

Per docs/specs/internal/ops/ml-track/stage-2-amendment-2026-05-05.md
(commit `04fa5fb`) D1: replace the binary `fixed_effect_suspect`
flag with a continuous ICC + bootstrap CI per feature.

Reads the trainer's engineered feature panel (post-first-difference),
computes ICC for each feature on the training window 2014-2021, and
emits a JSON shrinkage-weights artifact for downstream head training
to consume as adaptive regularization.

Usage::

    python scripts/run_icc_audit.py \
        --panel data/panel_104_2026_05_04.parquet \
        --train-year-max 2021 \
        --n-bootstrap 200 \
        --out ../qgi-data/reference/icc-shrinkage-weights-2026-05.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SHARED_ROOT = REPO_ROOT / "shared"
for _p in (str(SRC_ROOT), str(SCRIPTS_ROOT), str(SHARED_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from icc.icc import (  # noqa: E402
    DEFAULT_BOOTSTRAP_N,
    DEFAULT_BOOTSTRAP_SEED,
    compute_icc_for_features,
    shrinkage_weight_from_icc,
)
from train_multitask_v0 import build_feature_panel  # noqa: E402

LABEL_WINDOW_LOWER = 2014
DEFAULT_TRAIN_YEAR_MAX = 2021


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", type=Path, required=True)
    p.add_argument("--train-year-max", type=int, default=DEFAULT_TRAIN_YEAR_MAX)
    p.add_argument("--n-bootstrap", type=int, default=DEFAULT_BOOTSTRAP_N)
    p.add_argument("--seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not args.panel.exists():
        print(f"ERROR: panel not found: {args.panel}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"[icc] building engineered feature panel from {args.panel}",
              file=sys.stderr)
    panel = build_feature_panel(args.panel, train_year_max=args.train_year_max)
    feature_columns = [c for c in panel.columns if c not in ("country", "year")]
    if not args.quiet:
        print(f"[icc] panel: {len(panel)} rows, {len(feature_columns)} features",
              file=sys.stderr)

    # Restrict to training window
    train_mask = (panel["year"] >= LABEL_WINDOW_LOWER) & (panel["year"] <= args.train_year_max)
    panel_train = panel[train_mask].reset_index(drop=True)
    if not args.quiet:
        print(f"[icc] training-window panel: {len(panel_train)} rows "
              f"(years {LABEL_WINDOW_LOWER}-{args.train_year_max})",
              file=sys.stderr)

    if not args.quiet:
        print(f"[icc] computing ICC for {len(feature_columns)} features "
              f"(B={args.n_bootstrap})...", file=sys.stderr)

    icc_results = compute_icc_for_features(
        panel_train,
        feature_columns,
        country_col="country",
        year_col="year",
        n_bootstrap=args.n_bootstrap,
        seed=args.seed,
    )

    # Build summary
    n_high_icc = sum(1 for r in icc_results.values() if r.soft_flag_high_icc)
    n_skipped = sum(1 for r in icc_results.values() if r.skip_reason is not None)
    valid_iccs = [r.icc for r in icc_results.values()
                  if r.skip_reason is None and not pd.isna(r.icc)]
    median_icc = float(pd.Series(valid_iccs).median()) if valid_iccs else float("nan")

    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Phase D D1 -- ICC (intraclass correlation coefficient) per "
            "engineered feature for the head-training shrinkage-weight "
            "computation. Per docs/specs/internal/ops/ml-track/"
            "stage-2-amendment-2026-05-05.md (commit 04fa5fb) D1: "
            "replaces the binary fixed_effect_suspect flag in "
            "shap-fingerprint-2026-05.json."
        ),
        "method": {
            "icc_definition": "ICC = sigma_between_country^2 / (sigma_between + sigma_within)",
            "estimator": "one-way variance partitioning (sample variance per country, then mean across countries)",
            "ci_method": "cluster-bootstrap percentile (resample COUNTRIES with replacement)",
            "n_bootstrap": args.n_bootstrap,
            "shrinkage_weight": "linear: weight = max(0, min(1, 1 - icc)); NaN -> 0",
            "training_window": [LABEL_WINDOW_LOWER, args.train_year_max],
            "engineered_feature_space": "post-first-difference (matches build_feature_panel output)",
        },
        "policy": {
            "soft_flag_threshold": "icc > 0.7 -> high country-identity-proxy concern",
            "diagnostic_only_not_a_gate": True,
            "no_bh_fdr_correction": True,
        },
        "panel": {
            "path": str(args.panel),
            "n_features": len(feature_columns),
            "n_countries_in_train_window": int(panel_train["country"].nunique()),
            "n_observations_in_train_window": int(len(panel_train)),
        },
        "summary": {
            "n_features_total": len(feature_columns),
            "n_features_with_valid_icc": len(valid_iccs),
            "n_features_skipped": n_skipped,
            "n_features_high_icc_soft_flag": n_high_icc,
            "median_icc_across_valid": median_icc,
        },
        "consult_attribution": (
            "Recommended by Priya Venkataraman-Szabo (Stats 6 / ML 2, "
            "Majles seat #22) at the post-PoC trio convening 2026-05-05. "
            "Replaces the binary fixed_effect_suspect annotation from "
            "Stage 2 Prereq D (qgi-data PR #18 MERGED 9711545) with a "
            "continuous shrinkage weight. Justified empirically by Phase "
            "C LOCO diagnosis (qgi-ml PR #29 MERGED 1422b2c): "
            "civil_war_and_insurgency LOCO-AUC=0.339 vs in-sample 0.876 "
            "and bilateral_treaty LOCO-AUC=0.009 vs 0.747 confirmed "
            "country-fixed-effect contamination on those recipes; ICC "
            "shrinkage is the foundation fix before walking them."
        ),
        "features": {
            feat: {
                **asdict(result),
                "shrinkage_weight": shrinkage_weight_from_icc(result.icc),
            }
            for feat, result in icc_results.items()
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"[icc] wrote {args.out}", file=sys.stderr)
        print(f"[icc] summary: {output['summary']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
