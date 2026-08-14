#!/usr/bin/env python3
"""
run_cointegration_phase_b.py — Phase B execution for #585 v1.

Per founder direction (2026-05-02): use VERIFIED events only. Verified events
are curated events whose corresponding verification record carries
verdict="TRUE" in qgi-data/events/verification/{country}.json.

Per Sebastien's plan §4.4, Phase B builds the event-occurrence panel and
runs Westerlund (2007) Gt on every (I(1) indicator x recipe category) cell,
producing qgi-data/reference/cointegration-map.json.

Founder greenlit Phase B (Greenlight 2a equivalent) on 2026-05-02.

Differences from the design doc §4.4:
- Reads verification + curated locally (qgi-data/events/{verification,curated}/)
  rather than via Athena. Saves ~$1-2 in Athena charges and surfaces verification
  as the gating step (founder requirement).
- No Athena calls in this script.

Usage:
  python scripts/run_cointegration_phase_b.py --dry-run   # describe what it would do
  python scripts/run_cointegration_phase_b.py             # execute (under founder greenlight)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Phase A machinery — already merged to qgi-ml main
sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_cointegration_map import (  # noqa: E402
    ACTION_NO_EXISTING_MAP,
    ACTION_OVERWRITE_REQUIRED,
    ACTION_RESUME,
    ACTION_SKIP,
    CELL_KEY_SEP,
    CHECKPOINT_EVERY,
    DEFAULT_BOOTSTRAP_REPS,
    DEFAULT_LAGS,
    DEFAULT_P_THRESHOLD,
    PERF_WARN_RATE_CELLS_PER_MIN,
    PIPELINE_VERSION,
    PROGRESS_LOG_EVERY,
    VERDICT_INSUFFICIENT_DATA,
    _check_existing_map,
    build_pipeline_config,
    classify_verdict,
    get_i1_indicators_from_regimes,
    load_regimes_file,
    westerlund_gt,
    write_cointegration_map,
)


# ===========================================================================
# Country-name normalization (verification filenames -> indicator-panel names)
# ===========================================================================

_LOWERCASE_WORDS: frozenset[str] = frozenset({"and", "of", "the", "la"})


def file_stem_to_country_name(stem: str) -> str:
    """Convert verification/curated filename stem to indicator-panel country name.
    Examples:
      'afghanistan'                  -> 'Afghanistan'
      'south_africa'                 -> 'South Africa'
      'bosnia_and_herzegovina'       -> 'Bosnia and Herzegovina'
      'democratic_republic_of_congo' -> 'Democratic Republic of Congo'
      'united_states'                -> 'United States'
    """
    words = stem.lower().replace("_", " ").split()
    out: list[str] = []
    for i, w in enumerate(words):
        if i > 0 and w in _LOWERCASE_WORDS:
            out.append(w)
        else:
            out.append(w.capitalize())
    return " ".join(out)


def _is_skip_filename(p: Path) -> bool:
    """Skip backup/audit files starting with underscore."""
    return p.name.startswith("_") or any(
        part.startswith("_") for part in p.parts
    )


# ===========================================================================
# Verified events ingestion (LOCAL ONLY — no Athena)
# ===========================================================================

def load_verified_events(curated_dir: Path, verification_dir: Path) -> pd.DataFrame:
    """
    Read curated events + verification verdicts; return verified events.

    A verified event = a curated event whose (year, title) appears in the
    corresponding country's verification file with verdict="TRUE".

    Returns DataFrame with columns: [country, year, category, title].
    """
    if not curated_dir.exists():
        raise FileNotFoundError(f"curated_dir not found: {curated_dir}")
    if not verification_dir.exists():
        raise FileNotFoundError(f"verification_dir not found: {verification_dir}")

    # Build verification index: {country_name: set of (year, title) with verdict TRUE}
    verified_keys: dict[str, set[tuple[int, str]]] = {}
    n_verification_files = 0
    for vfile in sorted(verification_dir.glob("*.json")):
        if _is_skip_filename(vfile):
            continue
        n_verification_files += 1
        country = file_stem_to_country_name(vfile.stem)
        try:
            data = json.loads(vfile.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            warnings.warn(f"verification file unreadable: {vfile} ({e})", UserWarning)
            continue
        s: set[tuple[int, str]] = set()
        for rec in data:
            verdict = (rec.get("verdict") or "").strip().upper()
            year = rec.get("year")
            title = rec.get("title")
            if verdict == "TRUE" and year is not None and title is not None:
                s.add((int(year), title))
        if s:
            verified_keys[country] = s

    # Walk curated, keep only events whose (year, title) is verified
    rows: list[dict] = []
    n_curated_files = 0
    n_curated_events = 0
    for cfile in sorted(curated_dir.glob("*.json")):
        if _is_skip_filename(cfile):
            continue
        n_curated_files += 1
        country = file_stem_to_country_name(cfile.stem)
        try:
            data = json.loads(cfile.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            warnings.warn(f"curated file unreadable: {cfile} ({e})", UserWarning)
            continue
        country_keys = verified_keys.get(country, set())
        for rec in data:
            n_curated_events += 1
            year = rec.get("year")
            title = rec.get("title")
            category = rec.get("category")
            if year is None or title is None or category is None:
                continue
            if (int(year), title) in country_keys:
                rows.append({
                    "country": country,
                    "year": int(year),
                    "category": category,
                    "title": title,
                })

    df = pd.DataFrame(rows)
    print(f"[phase-b] verification files: {n_verification_files}")
    print(f"[phase-b] curated files:      {n_curated_files}")
    print(f"[phase-b] curated events:     {n_curated_events:,}")
    print(f"[phase-b] verified events:    {len(df):,}")
    if len(df) > 0:
        print(f"[phase-b] verified countries: {df['country'].nunique()}")
        print(f"[phase-b] verified categories: {df['category'].nunique()}")
    return df


# ===========================================================================
# Event-occurrence panel construction per recipe category
# ===========================================================================

def build_event_occurrence_panel(
    verified_events: pd.DataFrame,
    recipe_category: str,
    countries: list[str],
    year_range: tuple[int, int],
) -> pd.DataFrame:
    """
    For a given recipe_category, build an event-occurrence panel covering
    `countries` x [year_range[0]..year_range[1]] with event_occ in {0, 1}.

    event_occ = 1 if any verified event of `recipe_category` exists for that
    (country, year), else 0.
    """
    cat_events = verified_events[verified_events["category"] == recipe_category]
    cat_set = set(zip(cat_events["country"].tolist(), cat_events["year"].tolist()))

    y_min, y_max = year_range
    rows: list[dict] = []
    for ctry in countries:
        for yr in range(y_min, y_max + 1):
            occ = 1.0 if (ctry, yr) in cat_set else 0.0
            rows.append({"country": ctry, "year": yr, "event_occ": occ})
    return pd.DataFrame(rows)


# ===========================================================================
# Recipe enumeration
# ===========================================================================

def load_recipe_categories(recipes_json: Path) -> list[str]:
    """Return the sorted list of L3 event categories from recipes-aggregated.json."""
    data = json.loads(recipes_json.read_text(encoding="utf-8"))
    cats = sorted({r["event_category"] for r in data["recipes"]
                   if r.get("event_category")})
    return cats


# ===========================================================================
# Driver
# ===========================================================================

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--regimes-path", type=Path,
                   default=Path("qgi-data/reference/indicator-regimes.json"))
    p.add_argument("--panels-path", type=Path,
                   default=Path("qgi-ml/data/i1_panels.parquet"))
    p.add_argument("--curated-dir", type=Path,
                   default=Path("qgi-data/events/curated"))
    p.add_argument("--verification-dir", type=Path,
                   default=Path("qgi-data/events/verification"))
    p.add_argument("--recipes-json", type=Path,
                   default=Path("qgi-frontend/data/recipes-aggregated.json"))
    p.add_argument("--output-path", type=Path,
                   default=Path("qgi-data/reference/cointegration-map.json"))
    p.add_argument("--lags", type=int, default=DEFAULT_LAGS)
    p.add_argument("--p-threshold", type=float, default=DEFAULT_P_THRESHOLD)
    p.add_argument("--overwrite", action="store_true",
                   help="Force-clobber existing cointegration-map.json with "
                        "different pipeline_config.")
    p.add_argument("--dry-run", action="store_true",
                   help="Describe what would run; do not compute the map.")
    p.add_argument("--limit-cells", type=int, default=None,
                   help="DEV: limit total cell tests to first N (debugging).")
    args = p.parse_args()

    audit_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Stage 0: pipeline_config + idempotency check
    pipeline_config = build_pipeline_config(
        regimes_path=args.regimes_path,
        panels_path=args.panels_path,
        qgi_data_repo_dir=Path("qgi-data"),
        lags=args.lags,
        bootstrap_reps=DEFAULT_BOOTSTRAP_REPS,
        p_threshold=args.p_threshold,
    )
    print(f"[phase-b] pipeline_config: {json.dumps(pipeline_config, indent=2)}")

    # Stage 1: load regimes, recipes, panels
    print(f"\n[phase-b] loading regimes from {args.regimes_path}")
    regimes_envelope = json.loads(args.regimes_path.read_text(encoding="utf-8"))
    i1_indicators = sorted(get_i1_indicators_from_regimes(regimes_envelope))
    print(f"[phase-b] I(1) indicators: {len(i1_indicators)}")

    print(f"[phase-b] loading recipes from {args.recipes_json}")
    recipe_categories = load_recipe_categories(args.recipes_json)
    print(f"[phase-b] recipe categories: {len(recipe_categories)}")

    expected_cells = len(i1_indicators) * len(recipe_categories)
    if args.limit_cells is not None:
        expected_cells = min(expected_cells, args.limit_cells)
    print(f"[phase-b] expected cells: {expected_cells} ({len(i1_indicators)} x {len(recipe_categories)})")

    # Stage 2: idempotency guard
    action = _check_existing_map(args.output_path, pipeline_config, expected_cells)
    print(f"[phase-b] idempotency-guard verdict: {action}")
    if action == ACTION_SKIP:
        print(f"[phase-b] cointegration-map.json already complete at "
              f"{args.output_path}. Exit 0.")
        return 0
    if action == ACTION_OVERWRITE_REQUIRED and not args.overwrite:
        print(f"[phase-b-ERROR] {args.output_path} exists with different "
              f"pipeline_config. Pass --overwrite to clobber.", file=sys.stderr)
        return 2

    # Stage 3: load i1_panels.parquet
    print(f"\n[phase-b] loading i1_panels from {args.panels_path}")
    panels = pd.read_parquet(args.panels_path)
    print(f"[phase-b] panel rows: {len(panels):,}")
    panel_countries = sorted(panels["country"].unique().tolist())
    print(f"[phase-b] panel countries: {len(panel_countries)}")
    panel_year_min = int(panels["year"].min())
    panel_year_max = int(panels["year"].max())
    print(f"[phase-b] panel year range: {panel_year_min}..{panel_year_max}")

    # Stage 4: load verified events (LOCAL — no Athena)
    print("\n[phase-b] loading VERIFIED events from local files")
    verified_events = load_verified_events(args.curated_dir, args.verification_dir)
    if len(verified_events) == 0:
        print("[phase-b-ERROR] no verified events found; aborting.", file=sys.stderr)
        return 3

    # Cross-check: how many recipe categories overlap with verified-event categories?
    verified_cats = set(verified_events["category"].unique())
    recipe_cats_with_events = [c for c in recipe_categories if c in verified_cats]
    print(f"[phase-b] recipe categories with verified events: "
          f"{len(recipe_cats_with_events)}/{len(recipe_categories)}")
    if len(recipe_cats_with_events) < len(recipe_categories):
        missing = [c for c in recipe_categories if c not in verified_cats]
        print(f"[phase-b]   recipes with NO verified events: "
              f"{len(missing)} (will all be insufficient_data)")
        for m in missing[:10]:
            print(f"[phase-b]     - {m}")
        if len(missing) > 10:
            print(f"[phase-b]     ... +{len(missing) - 10} more")

    if args.dry_run:
        print("\n[phase-b] DRY RUN — would proceed to per-cell Westerlund test.")
        print(f"[phase-b]   cells: {expected_cells}")
        print(f"[phase-b]   estimated wall time at 50 cells/min: "
              f"{expected_cells / 50.0:.1f} min")
        return 0

    # Stage 5: pre-build event panels per recipe category (cache for reuse across indicators)
    print("\n[phase-b] pre-building event panels per recipe category...")
    event_panels_cache: dict[str, pd.DataFrame] = {}
    for cat in recipe_categories:
        event_panels_cache[cat] = build_event_occurrence_panel(
            verified_events, cat, panel_countries, (panel_year_min, panel_year_max),
        )
    print(f"[phase-b] cached {len(event_panels_cache)} event panels")

    # Stage 6: Resume support — if action=RESUME, read completed cells
    completed_cells: dict[str, dict] = {}
    if action == ACTION_RESUME:
        try:
            existing = json.loads(args.output_path.read_text(encoding="utf-8"))
            completed_cells = existing.get("cells", {}) or {}
            print(f"[phase-b] resume: loaded {len(completed_cells)} completed cells")
        except Exception as e:
            print(f"[phase-b] resume failed: {e}; starting fresh", file=sys.stderr)
            completed_cells = {}

    # Stage 7: execute Westerlund per cell
    print(f"\n[phase-b] executing Westerlund Gt for {expected_cells} cells...")
    cells_out: dict[str, dict] = dict(completed_cells)
    n_converged = sum(1 for c in cells_out.values() if c.get("converged"))
    n_not_converged = sum(1 for c in cells_out.values() if c.get("verdict") == "not_converged")
    n_insufficient = sum(1 for c in cells_out.values() if c.get("verdict") == "insufficient_data")
    t_start = time.monotonic()
    cell_idx = len(cells_out)
    cells_total_planned = expected_cells

    for ind_id in i1_indicators:
        ind_panel = panels[panels["indicator_id"] == ind_id][["country", "year", "value"]]
        if len(ind_panel) == 0:
            # Indicator not in cached panel — record insufficient_data for all its recipes
            for cat in recipe_categories:
                key = f"{ind_id}{CELL_KEY_SEP}{cat}"
                if key in cells_out:
                    continue
                if args.limit_cells is not None and cell_idx >= args.limit_cells:
                    break
                cells_out[key] = {
                    "gt_statistic": None, "p_value": None,
                    "n_countries": 0, "mean_rho": None,
                    "converged": False, "verdict": VERDICT_INSUFFICIENT_DATA,
                }
                n_insufficient += 1
                cell_idx += 1
            continue

        for cat in recipe_categories:
            key = f"{ind_id}{CELL_KEY_SEP}{cat}"
            if key in cells_out:
                continue
            if args.limit_cells is not None and cell_idx >= args.limit_cells:
                break

            event_panel = event_panels_cache[cat]

            try:
                # Suppress per-country zero-overlap UserWarnings during the loop
                # (A5 still emits them; we collect counts but don't flood stdout).
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    result = westerlund_gt(
                        ind_panel, event_panel, lags=args.lags,
                        bootstrap_reps=DEFAULT_BOOTSTRAP_REPS,
                    )
            except Exception as e:
                result = {"gt_statistic": None, "p_value": None,
                          "n_countries": 0, "mean_rho": None, "converged": False}
                print(f"[phase-b-WARN] cell {key} raised {type(e).__name__}: {e}",
                      file=sys.stderr)

            verdict = classify_verdict(result, p_threshold=args.p_threshold)
            cells_out[key] = {
                "gt_statistic": result.get("gt_statistic"),
                "p_value": result.get("p_value"),
                "n_countries": result.get("n_countries", 0),
                "mean_rho": result.get("mean_rho"),
                "converged": result.get("converged", False),
                "verdict": verdict,
            }

            if verdict == VERDICT_INSUFFICIENT_DATA:
                n_insufficient += 1
            elif verdict == "not_converged":
                n_not_converged += 1
            elif verdict in ("cointegrated", "not_cointegrated"):
                n_converged += 1

            cell_idx += 1

            # A2: progress logging every PROGRESS_LOG_EVERY cells
            if cell_idx % PROGRESS_LOG_EVERY == 0:
                elapsed = time.monotonic() - t_start
                rate_per_min = (cell_idx / elapsed * 60.0) if elapsed > 0 else 0.0
                pct = (cell_idx / cells_total_planned * 100.0) if cells_total_planned else 0.0
                eta_min = ((cells_total_planned - cell_idx) / rate_per_min
                           if rate_per_min > 0 else float("nan"))
                print(f"[585] cell {cell_idx}/{cells_total_planned} ({pct:.1f}%) | "
                      f"converged: {n_converged} | not_converged: {n_not_converged} | "
                      f"insufficient_data: {n_insufficient} | "
                      f"elapsed: {int(elapsed//60)}m{int(elapsed%60):02d}s | "
                      f"rate: {rate_per_min:.0f} cells/min | "
                      f"eta: {eta_min:.0f}m" if np.isfinite(eta_min) else
                      f"[585] cell {cell_idx}/{cells_total_planned} (rate=0)")
                if rate_per_min > 0 and rate_per_min < PERF_WARN_RATE_CELLS_PER_MIN:
                    print(f"[585-PERF-WARN] bootstrap rate degraded below "
                          f"{PERF_WARN_RATE_CELLS_PER_MIN} cells/min — investigate "
                          f"degenerate OLS matrices or vectorize.",
                          file=sys.stderr)

            # A2: partial JSON checkpoint every CHECKPOINT_EVERY cells
            if cell_idx % CHECKPOINT_EVERY == 0:
                write_cointegration_map(
                    args.output_path, pipeline_config, cells_out,
                    finalized=False,
                    source_panels=str(args.panels_path),
                    source_events=f"{args.curated_dir}+{args.verification_dir} (verified-only)",
                )
                print(f"[585] checkpoint written ({len(cells_out)} cells in file)")
        else:
            continue
        break  # broken out by --limit-cells

    # Stage 8: finalize map
    print("\n[phase-b] finalizing cointegration-map.json")
    write_cointegration_map(
        args.output_path, pipeline_config, cells_out,
        finalized=True,
        source_panels=str(args.panels_path),
        source_events=f"{args.curated_dir}+{args.verification_dir} (verified-only)",
    )
    elapsed = time.monotonic() - t_start
    print(f"[phase-b] complete: {len(cells_out)} cells in "
          f"{int(elapsed//60)}m{int(elapsed%60):02d}s")

    # Stage 9: aggregate verdict
    n_cointegrated = sum(1 for c in cells_out.values() if c.get("verdict") == "cointegrated")
    n_not_cointegrated = sum(1 for c in cells_out.values() if c.get("verdict") == "not_cointegrated")
    n_insufficient = sum(1 for c in cells_out.values() if c.get("verdict") == VERDICT_INSUFFICIENT_DATA)
    n_not_converged = sum(1 for c in cells_out.values() if c.get("verdict") == "not_converged")

    print()
    print("=" * 70)
    print("PHASE B COMPLETE — cointegration-map.json written")
    print(f"  output: {args.output_path}")
    print(f"  cells: {len(cells_out)}")
    print(f"  cointegrated:        {n_cointegrated}")
    print(f"  not_cointegrated:    {n_not_cointegrated}")
    print(f"  insufficient_data:   {n_insufficient}")
    print(f"  not_converged:       {n_not_converged}")
    if (n_cointegrated + n_not_cointegrated) > 0:
        pct_coint = n_cointegrated / (n_cointegrated + n_not_cointegrated) * 100.0
        print(f"  cointegration rate (excl insufficient/not_converged): {pct_coint:.1f}%")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
