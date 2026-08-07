#!/usr/bin/env python3
"""
produce_indicator_regimes.py — emit canonical indicator-regimes.json from
the Phase 0c CIPS audit report.

This is the source-of-truth file consumed by the auditioner (#585) and
eventually by the production SCDI scan pipeline (Ihsa I5 decision pending).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    src = repo_root / "qgi-ml" / "results" / "stationarity_audit_2026_05_02" / "stationarity_full_report.json"
    dst = repo_root / "qgi-data" / "reference" / "indicator-regimes.json"

    if not src.exists():
        print(f"ERROR: source not found: {src}", file=sys.stderr)
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))

    regimes = {"stationary": [], "marginal": [], "i1": []}
    indicators = []
    for ind in data["per_indicator"]:
        verdict = ind["verdict"]
        if verdict == "I(1)":
            regime_key = "i1"
            action = "first-diff"
        elif verdict == "MARGINAL":
            regime_key = "marginal"
            action = "keep"  # treated as stationary v1; revisit in v2
        elif verdict == "STATIONARY":
            regime_key = "stationary"
            action = "keep"
        else:
            continue
        regimes[regime_key].append(ind["indicator_id"])
        indicators.append({
            "id": ind["indicator_id"],
            "regime": regime_key,
            "action": action,
            "cips": ind["cips"],
            "n_countries": ind["n_countries"],
            "t_years": ind["t_years"],
        })

    out = {
        "schema_version": 1,
        "generated_at": data["audit_date"],
        "source": "qgi-ml/results/stationarity_audit_2026_05_02/stationarity_full_report.json",
        "audit_method": "CIPS (Pesaran 2007 Cross-sectionally Augmented IPS), case II (intercept, no trend)",
        "critical_value_5pct": -2.11,
        "critical_value_10pct": -2.03,
        "critical_value_1pct": -2.27,
        "aggregate_verdict": data.get("aggregate_verdict"),
        "pct_i1_or_marginal": data.get("pct_i1_or_marginal"),
        "regimes_summary": {
            "n_stationary": len(regimes["stationary"]),
            "n_marginal": len(regimes["marginal"]),
            "n_i1": len(regimes["i1"]),
            "n_total": len(indicators),
        },
        "regimes": {k: sorted(v) for k, v in regimes.items()},
        "indicators": sorted(indicators, key=lambda x: (x["regime"], x["id"])),
        "notes": [
            "Per Majles Al Ihsa I1 (2026-05-02), founder-greenlit Phase 0c full audit",
            "Action 'first-diff' = compute Pearson correlations on first-differenced Z-scored series",
            "Action 'keep' = compute Pearson correlations on raw Z-scored level series (current behavior)",
            "MARGINAL indicators treated as stationary (action=keep) in v1 per conservative call; revisit in v2",
            "Pipeline-side application gated on Ihsa I5 (production SCDI pipeline detrending decision)",
            "Auditioner-side application: ticket #585 (in flight)",
        ],
    }

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {dst}")
    print(f"  Stationary: {len(regimes['stationary'])}")
    print(f"  Marginal:   {len(regimes['marginal'])}")
    print(f"  I(1):       {len(regimes['i1'])}")
    print(f"  Total:      {len(indicators)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
