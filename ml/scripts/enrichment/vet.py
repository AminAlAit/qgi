"""Vet gate - indicator-enrichment pipeline stage 1.

Automated quality firewall for a candidate indicator BEFORE it enters the pool.
Runs five checks on the candidate's panel + metadata and emits a PASS /
QUARANTINE verdict with reasons. Quarantined indicators never reach the
challenger gate or a re-walk.

Checks:
  (a) history depth   - enough distinct years to be useful (hard)
  (b) country coverage - present for enough countries (hard)
  (c) variance floor   - not flat/degenerate across countries (hard)
  (d) stationarity     - not I(2)+/non-integrable (hard); I(1) passes -> first-diff
  (e) license          - not commercial/restricted (hard)
  (+) per-recipe coverage - informational; flags only if usable on ZERO recipes.
      (Real per-recipe filtering is the challenger gate's job, via the same
      coverage gate; this is an early "globally unusable" tripwire, not a
      per-recipe veto - a candidate need not cover every recipe.)

Reuses run_f_ml_1_poc's coverage gate verbatim for the per-recipe tripwire so
the truncation-leak guard (the foreign_intervention defect class) is identical
to the walk's. Local, $0, no AWS.

Design: docs/specs/internal/ops/ml-track/indicator-enrichment-cicd-design.md SS1.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ENRICH_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = ENRICH_DIR.parent  # qgi-ml/scripts
for _p in (str(ENRICH_DIR), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---- thresholds (calibrated so deliberately-added recent providers are not
# nuked; the per-recipe coverage gate + challenger gate do the fine filtering) --
MIN_YEARS = 10                  # a series needs >= a decade of distinct years
SHORT_HISTORY_FLAG_YEAR = 2008  # start_year after this -> informational "short" flag (not a fail)
MIN_COUNTRIES = 20              # present (>=1 non-null) for >= 20 countries
TOTAL_COUNTRIES = 261           # denominator for coverage_share (matches auditioner)
MAX_ZERO_VAR_FRAC = 0.20        # <= 20% of covered countries may be flat
VAR_EPS = 1e-9
STATIONARITY_QUARANTINE = frozenset({"I(2)_or_higher", "insufficient_data"})


def check_history_depth(panel: pd.DataFrame, *, min_years: int = MIN_YEARS,
                        short_flag_year: int = SHORT_HISTORY_FLAG_YEAR) -> dict[str, Any]:
    years = panel["year"].dropna().astype(int)
    if years.empty:
        return {"start_year": None, "n_years": 0, "short_history": True, "pass": False}
    start_year = int(years.min())
    n_years = int(years.nunique())
    return {"start_year": start_year, "n_years": n_years,
            "short_history": start_year > short_flag_year, "pass": n_years >= min_years}


def check_country_coverage(panel: pd.DataFrame, *, min_countries: int = MIN_COUNTRIES,
                           total_countries: int = TOTAL_COUNTRIES) -> dict[str, Any]:
    covered = panel.dropna(subset=["value"])["country"].nunique()
    return {"n_countries": int(covered),
            "coverage_share": round(covered / total_countries, 4),
            "pass": int(covered) >= min_countries}


def check_variance_floor(panel: pd.DataFrame, *, max_zero_var_frac: float = MAX_ZERO_VAR_FRAC,
                         eps: float = VAR_EPS) -> dict[str, Any]:
    # Per-country population std; single-obs / all-equal series -> ~0 (flat, uninformative).
    stds = panel.dropna(subset=["value"]).groupby("country")["value"].std(ddof=0).fillna(0.0)
    n = int(len(stds))
    if n == 0:
        return {"n_countries": 0, "frac_zero_variance": 1.0, "pass": False}
    flat = int((stds < eps).sum())
    frac = flat / n
    return {"n_countries": n, "frac_zero_variance": round(frac, 4),
            "pass": frac <= max_zero_var_frac}


def check_stationarity(indicator_id: str, audit: dict[str, Any] | None) -> dict[str, Any]:
    if not audit or indicator_id not in audit.get("results", {}):
        return {"classification": "unknown", "action": "audit-pending", "ambiguous": False, "pass": True}
    cls = audit["results"][indicator_id].get("classification", "unknown")
    blocked = cls in STATIONARITY_QUARANTINE
    if blocked:
        action = "quarantine"
    elif cls == "I(1)":
        action = "first-diff"      # difference once before use
    else:
        action = "keep"            # I(0) / ambiguous: use as-is
    # 'ambiguous' passes but is surfaced so downstream first-diff-vs-keep isn't silent.
    return {"classification": cls, "action": action, "ambiguous": cls == "ambiguous", "pass": not blocked}


def classify_license(license_str: str | None) -> str:
    s = (license_str or "").lower()
    if not s:
        return "unknown"
    if "commercial" in s or "restricted" in s or "proprietary" in s:
        return "restricted"
    if "cc0" in s:
        return "cc0"
    if "igo" in s:
        return "cc-igo"
    if "cc by" in s or "public domain" in s or "open" in s:
        return "open"
    return "unknown"


def check_license(provider: str, license_str: str | None) -> dict[str, Any]:
    tier = classify_license(license_str)
    # Open / CC0 / CC-IGO pass; restricted fails; unknown passes WITH a flag
    # (forward-looking - all current catalog providers are open).
    return {"tier": tier, "license": license_str, "pass": tier != "restricted"}


def check_recipe_coverage(panel: pd.DataFrame, indicator_id: str,
                          recipe_samples: dict[str, pd.DataFrame], *, window: int = 10) -> dict[str, Any]:
    """Per-recipe coverage tripwire using the walk's OWN coverage gate. Informational
    (records ok/total); contributes a quarantine reason only if usable on zero recipes."""
    import run_f_ml_1_poc as drv  # lazy: keeps pure checks importable without the driver
    per: dict[str, bool] = {}
    for rid, samples in recipe_samples.items():
        cov = drv.coverage_report(samples, [indicator_id], window, {indicator_id: panel})
        per[rid] = bool(drv.coverage_gate_ok(cov))
    n_ok = sum(per.values())
    return {"n_recipes_ok": n_ok, "n_recipes": len(per), "per_recipe_ok": per,
            "pass": (len(per) == 0) or (n_ok > 0)}


def vet_indicator(panel: pd.DataFrame, *, indicator_id: str, provider: str,
                  license_str: str | None = None, stationarity_audit: dict[str, Any] | None = None,
                  recipe_samples: dict[str, pd.DataFrame] | None = None,
                  window: int = 10) -> dict[str, Any]:
    """Run all checks on a candidate panel and return a verdict record."""
    checks: dict[str, Any] = {
        "history_depth": check_history_depth(panel),
        "country_coverage": check_country_coverage(panel),
        "variance_floor": check_variance_floor(panel),
        "stationarity": check_stationarity(indicator_id, stationarity_audit),
        "license": check_license(provider, license_str),
    }
    if recipe_samples is not None:
        checks["recipe_coverage"] = check_recipe_coverage(panel, indicator_id, recipe_samples, window=window)

    reasons: list[str] = []
    if not checks["history_depth"]["pass"]:
        reasons.append(f"history_depth:{checks['history_depth']['n_years']}y")
    if not checks["country_coverage"]["pass"]:
        reasons.append(f"country_coverage:{checks['country_coverage']['n_countries']}")
    if not checks["variance_floor"]["pass"]:
        reasons.append(f"variance_floor:{checks['variance_floor']['frac_zero_variance']}")
    if not checks["stationarity"]["pass"]:
        reasons.append(f"stationarity:{checks['stationarity']['classification']}")
    if not checks["license"]["pass"]:
        reasons.append(f"license:{checks['license']['tier']}")
    if "recipe_coverage" in checks and not checks["recipe_coverage"]["pass"]:
        reasons.append("recipe_coverage:usable_on_zero_recipes")

    return {"indicator_id": indicator_id, "provider": provider,
            "verdict": "QUARANTINE" if reasons else "PASS",
            "quarantine_reasons": reasons, "checks": checks}


def load_panel_for(indicator_id: str, panel_dir: Path) -> pd.DataFrame:
    return pd.read_parquet(panel_dir / indicator_id / f"{indicator_id}.parquet")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vet gate (stage 1): quality firewall for candidate indicators.")
    ap.add_argument("--panel-dir", type=Path, required=True, help="Dir of candidate panels {id}/{id}.parquet")
    ap.add_argument("--candidates", nargs="+", required=True, help="Candidate indicator ids to vet")
    ap.add_argument("--provider", default="UNKNOWN", help="Provider tag for license check")
    ap.add_argument("--license", dest="license_str", default=None, help="License string for the candidates")
    ap.add_argument("--stationarity-audit", type=Path, default=None,
                    help="indicator-stationarity-audit-v2.json (optional)")
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args(argv)

    audit = json.loads(args.stationarity_audit.read_text(encoding="utf-8")) if args.stationarity_audit else None
    results = []
    for cid in args.candidates:
        panel = load_panel_for(cid, args.panel_dir)
        results.append(vet_indicator(panel, indicator_id=cid, provider=args.provider,
                                     license_str=args.license_str, stationarity_audit=audit))
    n_pass = sum(r["verdict"] == "PASS" for r in results)
    report = {"schema_version": 1, "n_candidates": len(results),
              "n_pass": n_pass, "n_quarantine": len(results) - n_pass, "results": results}
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote vet report -> {args.output}")
    print(f"PASS {n_pass}/{len(results)}; QUARANTINE {len(results) - n_pass}.")
    for r in results:
        if r["verdict"] == "QUARANTINE":
            print(f"  - {r['indicator_id']}: {', '.join(r['quarantine_reasons'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
