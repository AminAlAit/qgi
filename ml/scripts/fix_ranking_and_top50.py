#!/usr/bin/env python3
# THROWAWAY — one-off script, no tests per #373.
# Ran once (T20 #313 fixes, 2026-04-19). Not intended for re-run; the fixes
# were absorbed into the proper Lambda generation pipeline on the next run.
# If the same class of bug ever resurfaces, fix at source (pipeline-recipe-
# engine-finalize) rather than re-running this script.
"""
fix_ranking_and_top50.py — in-place fixes for ranking.json + recipes-top50.json.

T20 #313 fixes:

1. ranking.json dedup:
   QA found only 24 unique country pairs across 1000 rows — South Korea /
   Thailand alone was 563 of 1000. Frontend already does client-side dedup
   (BaseClient.tsx padKey) but the baked file is wasteful + the "1000 top
   patterns" claim is misleading. Dedup to one best-PPS window per pair
   and preserve the original row ordering by PPS.

2. recipes-top50.json lookahead filter:
   QA flagged 3 recipes with `event_year_b > end_year_b` (Estonia yb=2023 >
   eyb=2021; Qatar 2013 > 2007; South Africa 2022 > 2021) — event drawn
   from OUTSIDE the pattern window, violates precedent semantics. Filter
   them out of the live file until the next Lambda run regenerates
   properly.

3. recipes-top50.json name audit:
   File currently has 12 entries despite being called "top50". This
   script flags but does NOT rename — rename would break every frontend
   consumer reading the path literally. Lambda regen will correct the
   count.

Usage:
    python qgi-ml/scripts/fix_ranking_and_top50.py \\
        --frontend qgi-frontend/data
"""

import argparse
import json
from pathlib import Path


def dedup_ranking(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("results", [])
    print(f"ranking.json: {len(rows)} rows before dedup")

    # Dedup by pair — keep best PPS.
    best: dict[str, dict] = {}
    for row in rows:
        # Coerce ids to padded strings so lex-order matches numeric-order
        # (matches the T2 fix in qgi-frontend).
        a = row.get("country_a_id") or row.get("country_a")
        b = row.get("country_b_id") or row.get("country_b")
        try:
            a_key = str(int(a)).zfill(6)
        except (TypeError, ValueError):
            a_key = str(a or "")
        try:
            b_key = str(int(b)).zfill(6)
        except (TypeError, ValueError):
            b_key = str(b or "")
        pair_key = f"{a_key}|{b_key}" if a_key < b_key else f"{b_key}|{a_key}"
        pps = row.get("pattern_power_score", 0) or 0
        existing = best.get(pair_key)
        if existing is None or pps > (existing.get("pattern_power_score", 0) or 0):
            best[pair_key] = row

    deduped = sorted(
        best.values(),
        key=lambda r: -(r.get("pattern_power_score", 0) or 0),
    )
    print(f"ranking.json: {len(deduped)} unique pairs after dedup")

    data["results"] = deduped
    data["deduped_at"] = "2026-04-19"  # audit breadcrumb
    data["deduped_method"] = "one-best-PPS-per-pair (T20 #313 in-place fix)"
    return data


def filter_lookahead_top50(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    rows = data.get("results", [])
    print(f"\nrecipes-top50.json: {len(rows)} rows before lookahead filter")
    if len(rows) < 50:
        print(
            f"  NOTE: file is misnamed — {len(rows)} rows but name implies 50. "
            "Lambda regen will correct. Not renaming to avoid breaking frontend consumers."
        )

    filtered = []
    dropped = []
    for row in rows:
        eyb = row.get("event_year_b")
        end_b = row.get("end_year_b")
        syb = row.get("start_year_b")
        if eyb is None or end_b is None or syb is None:
            filtered.append(row)
            continue
        # Event must fall INSIDE or AT the end of the pattern window
        # (start_year_b <= event_year_b <= end_year_b).
        if syb <= eyb <= end_b:
            filtered.append(row)
        else:
            dropped.append(row)

    print(f"recipes-top50.json: {len(filtered)} rows after filter (dropped {len(dropped)})")
    if dropped:
        print("  Dropped (event outside window):")
        for r in dropped:
            print(
                f"    {r.get('country_a_name')}-{r.get('country_b_name')} "
                f"start_b={r.get('start_year_b')} end_b={r.get('end_year_b')} "
                f"event_b={r.get('event_year_b')}"
            )

    data["results"] = filtered
    data["lookahead_filtered_at"] = "2026-04-19"
    data["lookahead_filter_method"] = "drop rows where event_year_b outside [start_year_b, end_year_b]"
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, default=Path("qgi-frontend/data"))
    args = parser.parse_args()

    ranking_path = args.frontend / "ranking.json"
    top50_path = args.frontend / "recipes-top50.json"

    if not ranking_path.exists():
        print(f"ERROR: {ranking_path} not found")
        return 1
    if not top50_path.exists():
        print(f"ERROR: {top50_path} not found")
        return 1

    deduped = dedup_ranking(ranking_path)
    with open(ranking_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)
    print(f"Wrote {ranking_path}")

    filtered = filter_lookahead_top50(top50_path)
    with open(top50_path, "w", encoding="utf-8") as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)
    print(f"Wrote {top50_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
