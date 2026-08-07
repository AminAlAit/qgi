"""Stage 2 Prereq C — structural-break audit on the 104-indicator panel.

Implements Component 7 of `docs/specs/internal/ops/ml-track/07-validation-framework.md`.
Per Ji-Hoon + Kwame mini-consult (2026-05-04):

- Method: OLS-CUSUM on residuals of `value ~ year` (linear trend).
- Two windows per pair:
    - `narrow`: 2014-2021 (literal training window, low statistical power at n=8)
    - `extended`: max-available history through 2021 (better power)
- No binarization at single alpha; emits raw p + sup_b stat plus two
  descriptive flags (`soft_flag_p_lt_010`, `high_conf_break_p_lt_001`).
- Diagnostic only — Stage 2 falsification rules (F1/F2/F3) do NOT
  consume this output.
- Pre-registration: JSON committed to qgi-data BEFORE any Stage 2 walk.

Usage::

    python scripts/run_structural_break_audit.py \
        --panel data/panel_104_2026_05_04.parquet \
        --out ../qgi-data/reference/structural-break-audit-2026-05.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from tqdm import tqdm  # type: ignore[import-not-found]
except ImportError:
    def tqdm(iterable, **_kwargs):  # type: ignore[no-redef]
        # Minimal fallback: print every 500 iterations.
        for i, item in enumerate(iterable):
            if i and i % 500 == 0:
                print(f"  ... {i} pairs processed", file=sys.stderr)
            yield item

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SHARED_ROOT = REPO_ROOT / "shared"
for _p in (str(SRC_ROOT), str(SHARED_ROOT), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from structural_break import (  # noqa: E402
    DEFAULT_LOW_POWER_THRESHOLD,
    DEFAULT_MIN_N_OBSERVATIONS,
    EXTENDED_WINDOW_END,
    NARROW_WINDOW,
    audit_pair,
    compute_panel_snapshot_id,
)

try:
    from slug import country_slug  # type: ignore[import-not-found]
except ImportError:
    # Fallback if shared/slug.py not on path; replicate snake_case behavior.
    import re

    def country_slug(name: str) -> str:  # type: ignore[no-redef]
        return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--panel",
        type=Path,
        default=REPO_ROOT / "data" / "panel_104_2026_05_04.parquet",
        help="Path to the indicator panel parquet (long format: country,year,indicator_id,value).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSON path (canonical location: qgi-data/reference/structural-break-audit-2026-05.json).",
    )
    parser.add_argument(
        "--narrow-start",
        type=int,
        default=NARROW_WINDOW[0],
        help="Narrow-window start year (inclusive). Default: 2014.",
    )
    parser.add_argument(
        "--narrow-end",
        type=int,
        default=NARROW_WINDOW[1],
        help="Narrow-window end year (inclusive). Default: 2021.",
    )
    parser.add_argument(
        "--extended-end",
        type=int,
        default=EXTENDED_WINDOW_END,
        help="Extended-window end year (inclusive). Default: 2021.",
    )
    parser.add_argument(
        "--min-n",
        type=int,
        default=DEFAULT_MIN_N_OBSERVATIONS,
        help="Skip pairs with fewer than this many non-NaN observations. Default: 6.",
    )
    parser.add_argument(
        "--low-power-threshold",
        type=int,
        default=DEFAULT_LOW_POWER_THRESHOLD,
        help="Set low_power_warning when n_observations < threshold. Default: 15.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on (country, indicator) pairs (debug/dev runs).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress bar.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.panel.exists():
        print(f"ERROR: panel not found: {args.panel}", file=sys.stderr)
        return 2

    print(f"Reading panel: {args.panel}", file=sys.stderr)
    panel = pd.read_parquet(args.panel)
    required_cols = {"country", "year", "indicator_id", "value"}
    missing = required_cols - set(panel.columns)
    if missing:
        print(f"ERROR: panel missing columns: {missing}", file=sys.stderr)
        return 2

    panel_snapshot_id = compute_panel_snapshot_id(args.panel)
    print(f"Panel snapshot id (sha256): {panel_snapshot_id[:16]}...", file=sys.stderr)

    # Group once; iterate.
    panel = panel.dropna(subset=["country", "year", "indicator_id"])
    panel["year"] = panel["year"].astype(int)
    pairs = list(panel.groupby(["country", "indicator_id"], sort=True))
    if args.limit is not None:
        pairs = pairs[: args.limit]
    print(f"Auditing {len(pairs)} (country, indicator) pairs...", file=sys.stderr)

    cells: list[dict] = []
    iterator = pairs if args.quiet else tqdm(pairs, desc="cusum", unit="pair")
    for (country, indicator_id), grp in iterator:
        years = grp["year"].to_numpy()
        values = grp["value"].to_numpy(dtype=float)

        narrow = audit_pair(
            years,
            values,
            window_start=args.narrow_start,
            window_end=args.narrow_end,
            min_n_observations=args.min_n,
            low_power_threshold=args.low_power_threshold,
        )
        extended = audit_pair(
            years,
            values,
            window_start=None,
            window_end=args.extended_end,
            min_n_observations=args.min_n,
            low_power_threshold=args.low_power_threshold,
        )

        cells.append({
            "country": str(country),
            "country_slug": country_slug(str(country)),
            "indicator_id": str(indicator_id),
            "narrow": narrow,
            "extended": extended,
        })

    summary = _summarize(cells)

    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Stage 2 Prereq C: structural-break diagnostic per "
            "docs/specs/internal/ops/ml-track/07-validation-framework.md "
            "Component 7. Diagnostic only — does NOT feed into Stage 2 "
            "F-rules. Stage 2 walk consumes per-recipe to decide cell "
            "handling (exclusion / interaction / sub-model)."
        ),
        "method": {
            "test": "cusum_olsresid_linear_trend",
            "library": "statsmodels.stats.diagnostic.breaks_cusumolsresid",
            "ddof": 2,
            "regression": "value ~ year (intercept + linear trend)",
        },
        "policy": {
            "no_alpha_binarization": True,
            "soft_flag_threshold": 0.10,
            "high_conf_break_threshold": 0.01,
            "min_n_observations": args.min_n,
            "low_power_threshold": args.low_power_threshold,
            "no_bh_fdr_correction": True,
            "diagnostic_only_not_a_gate": True,
        },
        "windows": {
            "narrow": {"start": args.narrow_start, "end": args.narrow_end},
            "extended": {"start": None, "end": args.extended_end},
        },
        "panel": {
            "path_relative_to_qgi_ml": str(args.panel.relative_to(REPO_ROOT))
            if args.panel.is_absolute() and REPO_ROOT in args.panel.parents
            else str(args.panel),
            "panel_snapshot_id_sha256": panel_snapshot_id,
            "n_unique_countries": int(panel["country"].nunique()),
            "n_unique_indicators": int(panel["indicator_id"].nunique()),
            "n_pairs_audited": len(cells),
        },
        "consult_attribution": (
            "Methodology defaults set by Ji-Hoon Yamamoto-Costa + Kwame "
            "Adjei mini-consult (2026-05-04). Ji-Hoon: CUSUM only (drop "
            "Zivot-Andrews — wrong null + n=8 too small for reliable "
            "break-date estimation), no alpha binarization, low-power "
            "warning at n<15. Kwame: pre-registration via commit hash, "
            "diagnostic-only (F-rules stay clean), no BH/FDR (hard veto)."
        ),
        "summary": summary,
        "cells": cells,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}", file=sys.stderr)
    print(f"Summary: {summary}", file=sys.stderr)
    return 0


def _summarize(cells: list[dict]) -> dict:
    """Compute simple per-window counts for the JSON header."""

    def _window_summary(key: str) -> dict:
        n_total = len(cells)
        n_skipped = sum(1 for c in cells if c[key]["skip_reason"] is not None)
        n_tested = n_total - n_skipped
        n_soft_flagged = sum(
            1 for c in cells if c[key].get("soft_flag_p_lt_010") is True
        )
        n_high_conf = sum(
            1 for c in cells if c[key].get("high_conf_break_p_lt_001") is True
        )
        n_low_power = sum(
            1 for c in cells if c[key].get("low_power_warning") is True
        )
        return {
            "n_total_pairs": n_total,
            "n_tested": n_tested,
            "n_skipped": n_skipped,
            "n_soft_flagged_p_lt_010": n_soft_flagged,
            "n_high_conf_break_p_lt_001": n_high_conf,
            "n_low_power_warning": n_low_power,
            "soft_flag_rate_pct": round(100.0 * n_soft_flagged / n_tested, 2) if n_tested else 0.0,
            "high_conf_rate_pct": round(100.0 * n_high_conf / n_tested, 2) if n_tested else 0.0,
        }

    return {
        "narrow_2014_2021": _window_summary("narrow"),
        "extended_through_2021": _window_summary("extended"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
