"""Build per-(country, year) Lloyd's actuarial cohort assignments.

Per `docs/specs/methodology/cohort-definitions.md` (8-seat ratified 2026-05-21).

Cohort cutoffs:
  fragile-state    FSI total >= 90    (V-Dem polyarchy <= 0.35 fallback)
  mid-tier         FSI total 60-90    (V-Dem polyarchy in (0.35, 0.65] fallback)
  stable-democracy FSI total < 60     (V-Dem polyarchy > 0.65 fallback)

This is the Ji-Hoon #21 R2 rider deliverable on the cohort-definitions
ratification: the F-Shape-1 single-veto block on the Stage 7 walk
requires this sidecar to be committed to `qgi-data/reference/`
BEFORE the walk fires.

Per Marcus #8 R4 rider on the same ratification: V-Dem polyarchy
fallbacks for positive instances use the EVENT-YEAR index value,
not the latest-year value. This script emits per-(country, year)
assignments so the consumer can do that lookup correctly.

FSI integration is deferred to a Phase 2 follow-up; this Phase 1
sidecar uses the V-Dem polyarchy fallback as the primary source
(documented in cohort-definitions.md as the >85%-agreement fallback).

Usage:
    python scripts/build_cohort_assignments.py \\
        --vdem-panel data/parquet_panels/v2x_polyarchy/v2x_polyarchy.parquet \\
        --output ../qgi-data/reference/cohort-assignments.json

Run from `qgi-ml/` directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Cohort cutoffs per docs/specs/methodology/cohort-definitions.md (8-seat
# ratified 2026-05-21). V-Dem polyarchy fallback thresholds, calibrated
# to agree with FSI ≥ 90 / 60-90 / < 60 on >85% of countries in 2018-2023.
FRAGILE_STATE_VDEM_UPPER = 0.35   # V-Dem ≤ 0.35  → fragile-state
MID_TIER_VDEM_UPPER = 0.65        # V-Dem in (0.35, 0.65] → mid-tier
# V-Dem > 0.65 → stable-democracy


def assign_cohort_vdem(polyarchy: float) -> str:
    """Map a V-Dem polyarchy index to one of three Lloyd's cohorts.

    Per cohort-definitions.md fallback rules.
    """
    if polyarchy <= FRAGILE_STATE_VDEM_UPPER:
        return "fragile-state"
    if polyarchy <= MID_TIER_VDEM_UPPER:
        return "mid-tier"
    return "stable-democracy"


def build_assignments(vdem_df: pd.DataFrame) -> dict:
    """Build the per-(country, year) cohort assignment payload.

    Returns a dict matching the expected sidecar schema:
        {
          "schema_version": 1,
          "filed": "<ISO date>",
          "lineage": {...},
          "cutoffs": {...},
          "assignments": {
            "country_name": {
              "<year>": "fragile-state" | "mid-tier" | "stable-democracy",
              ...
            },
            ...
          }
        }
    """
    assignments: dict[str, dict[str, str]] = {}
    for _, row in vdem_df.iterrows():
        country = str(row["country"])
        year = int(row["year"])
        value = float(row["value"])
        if not np.isfinite(value):
            continue
        cohort = assign_cohort_vdem(value)
        if country not in assignments:
            assignments[country] = {}
        assignments[country][str(year)] = cohort

    return {
        "schema_version": 1,
        "filed": datetime.now(timezone.utc).date().isoformat(),
        "purpose": (
            "Per-(country, year) Lloyd's actuarial cohort assignments "
            "for F-H-7 cohort-stratified calibration. Phase 1 uses "
            "V-Dem polyarchy fallback per cohort-definitions.md "
            "(8-seat ratified 2026-05-21); FSI integration deferred "
            "to Phase 2."
        ),
        "lineage": {
            "cohort_definitions": "docs/specs/methodology/cohort-definitions.md",
            "vdem_panel": "qgi-ml/data/parquet_panels/v2x_polyarchy/v2x_polyarchy.parquet",
            "ratification": (
                "8-seat ratified 2026-05-21 with R1+R2+R3+R4 operational riders"
            ),
        },
        "cutoffs": {
            "primary_source": "FSI 2024 (Fund for Peace Fragile States Index)",
            "fallback_source": "V-Dem polyarchy (v2x_polyarchy)",
            "fragile_state_vdem_upper": FRAGILE_STATE_VDEM_UPPER,
            "mid_tier_vdem_upper": MID_TIER_VDEM_UPPER,
            "source_primary_field": "FSI Total Score",  # R3 rider
            "marcus_r4_note": (
                "V-Dem fallback for positive instances uses the EVENT-YEAR "
                "index value, not latest-year. Per Marcus #8 R4 rider on "
                "cohort-definitions ratification."
            ),
        },
        "assignments": assignments,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vdem-panel",
        type=Path,
        required=True,
        help="Path to the V-Dem polyarchy parquet panel",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write the cohort-assignments.json sidecar",
    )
    args = parser.parse_args(argv)

    print(f"Loading V-Dem polyarchy panel from {args.vdem_panel} ...", file=sys.stderr)
    vdem_df = pd.read_parquet(args.vdem_panel)
    print(
        f"  rows: {len(vdem_df)}, countries: {vdem_df['country'].nunique()}, "
        f"years: {vdem_df['year'].min()}-{vdem_df['year'].max()}",
        file=sys.stderr,
    )

    payload = build_assignments(vdem_df)
    n_countries = len(payload["assignments"])
    n_country_years = sum(len(v) for v in payload["assignments"].values())
    print(
        f"  assignments: {n_countries} countries, {n_country_years} country-years",
        file=sys.stderr,
    )

    cohort_counts: dict[str, int] = {"fragile-state": 0, "mid-tier": 0, "stable-democracy": 0}
    for country_years in payload["assignments"].values():
        for cohort in country_years.values():
            cohort_counts[cohort] = cohort_counts.get(cohort, 0) + 1
    print("  cohort distribution (country-years):", file=sys.stderr)
    for cohort, count in cohort_counts.items():
        pct = 100.0 * count / max(n_country_years, 1)
        print(f"    {cohort:20s}  {count:>7d}  ({pct:.1f}%)", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
    print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
