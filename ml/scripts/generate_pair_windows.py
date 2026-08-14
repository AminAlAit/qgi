#!/usr/bin/env python3
"""
generate_pair_windows.py  —  Tickets #352, #358

Runs THREE Athena queries against qgi_data.patterns and produces two artefacts:

1.  data/pair-windows/{country_a_id}.json   (one file per country_a_id)
      keyed by country_b_id, each value has
        - "top" : up to TOP_N_PER_PAIR PPS-ranked windows + up to
                  TOP_K_PER_END_YEAR windows per distinct end-year anchored
                  to analogue event years (deduplicated, sorted by PPS desc)
        - "hist": length-histogram (length -> count)
      Each window carries l/sa/sb/ic/ac/pps/cp plus (§H) "ind": the pattern's
      indicator_numeric_ids, consumed by bake_pattern_scdis.py to resolve
      per-indicator SCDI detail without re-querying the 2 B-row patterns table.
      Schema matches what /api/patterns/windows/route.ts expects as the baked
      fallback.

2.  data/analogues.json                     (in place)
    data/analogues-enriched.json            (in place)
      Each analogue entry gets these extra fields so the "View pattern" link
      on PrecedentDetailClient can deep-link to S3 pattern detail:
        - best_pattern_length
        - best_pattern_start_a
        - best_pattern_start_b

## #358 change (2026-04-19): event-year-anchored sampling

The #352 version fetched only the top-K PPS-ranked windows per (subject,
analogue) pair. For subjects like Bahrain, that top-K was dominated by
windows ending 2021-2027 (the subject's recent trajectory). Old-event
analogues (Russia/Helsinki 1987) had no window anywhere near their event
year in the top-K, so the downstream enrichment produced pair_start_b=null
and the frontend fell back to a 15-year event-anchored approximation.

The fix: add Query 3 which selects the top-K patterns per
(country_a_id, country_b_id, end_year) triple, across every end-year in
[1950, CURRENT_YEAR]. Python-side, we load curated-event years per
country (from qgi-data/events/curated/*.json), then keep only windows
whose end-year matches an actual event year for the analogue country.
Downstream consumers (enrich_analogues_common_length.py,
AnalogueMultiTimeline) pick up the event-aligned windows automatically
because they're in the same "top" array the script already produces.

Execution is GATED on #241 (FAOSTAT integration) landing — don't run
until the WB + FAOSTAT combined pattern table is ready, per 2026-04-19
directive. Code lands dormant until then.

One-shot script — run after any pipeline refresh that updates qgi_data.patterns.

Usage:

    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    export AWS_SESSION_TOKEN=...
    python qgi-ml/scripts/generate_pair_windows.py \
        --bucket qgi-data-lake-771606957899 \
        --region eu-central-1
"""
from __future__ import annotations
import argparse
import json
import re
import time
import sys
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import boto3

WORKGROUP = "QGI-Lambda-Workgroup"
DATABASE = "qgi_data"
TOP_N_PER_PAIR = 20

# #358: in addition to top-N by PPS per pair, also keep top-K windows per
# (country_a_id, country_b_id, end_year) triple. End-year is start_year_b +
# length. This ensures that every event year (from curated events) has at
# least K pattern candidates available for the enrichment script to
# choose from, eliminating the 15-year event-anchored fallback for rows
# where the enriched set used to be null.
TOP_K_PER_END_YEAR = 3

# Earliest event year worth indexing (QGI curated events rarely predate
# 1950 — pre-WWII coverage is sparse across most countries). Also caps
# the Athena scan volume.
EVENT_YEAR_FLOOR = 1950
# Upper bound: we refuse analogue bars extending past the subject's NOW
# marker anyway (see enrich_analogues_common_length.py CURRENT_YEAR
# guard). Keeping the query under this ceiling avoids wasted rows.
CURRENT_YEAR = datetime.now().year

SQL_TOP_N = f"""
SELECT country_a_id, country_b_id, length, start_year_a, start_year_b,
       indicator_count, avg_correlation, pattern_power_score,
       -- §H cascade SCDI bake: carry the pattern's indicator id list (already a
       -- column on qgi_data.patterns) so bake_pattern_scdis can resolve per-indicator
       -- SCDI detail WITHOUT re-querying the 2B-row patterns table
       -- (cascade-patterns-scdi-reply-v2 §2).
       indicator_numeric_ids,
       -- #461: D7 plumbing carried forward into pair_windows.json so the
       -- frontend can render a "contains predicted values" badge per pair.
       COALESCE(contains_predicted, FALSE) AS contains_predicted
FROM (
  SELECT country_a_id, country_b_id, length, start_year_a, start_year_b,
         indicator_count, avg_correlation, pattern_power_score, contains_predicted,
         indicator_numeric_ids,
         ROW_NUMBER() OVER (
           PARTITION BY country_a_id, country_b_id
           ORDER BY pattern_power_score DESC
         ) AS rn
  FROM {DATABASE}.patterns
)
WHERE rn <= {TOP_N_PER_PAIR}
"""

SQL_HIST = f"""
SELECT country_a_id, country_b_id, length, COUNT(*) AS cnt
FROM {DATABASE}.patterns
GROUP BY country_a_id, country_b_id, length
"""

# #358: top-K windows per (a, b, end_year) triple. Restricted to
# [EVENT_YEAR_FLOOR, CURRENT_YEAR] so the scan stays bounded.
SQL_TOP_K_PER_END_YEAR = f"""
SELECT country_a_id, country_b_id, length, start_year_a, start_year_b,
       indicator_count, avg_correlation, pattern_power_score,
       -- §H: see SQL_TOP_N — carry the indicator id list for the SCDI baker.
       indicator_numeric_ids,
       -- #461: D7 plumbing — see SQL_TOP_N.
       COALESCE(contains_predicted, FALSE) AS contains_predicted
FROM (
  SELECT country_a_id, country_b_id, length, start_year_a, start_year_b,
         indicator_count, avg_correlation, pattern_power_score, contains_predicted,
         indicator_numeric_ids,
         ROW_NUMBER() OVER (
           PARTITION BY country_a_id, country_b_id, (start_year_b + length)
           ORDER BY pattern_power_score DESC
         ) AS rn_end
  FROM {DATABASE}.patterns
  WHERE (start_year_b + length) BETWEEN {EVENT_YEAR_FLOOR} AND {CURRENT_YEAR}
)
WHERE rn_end <= {TOP_K_PER_END_YEAR}
"""


def run_query(athena, sql: str, bucket: str, poll_seconds: float = 3.0) -> list[dict]:
    """Submit to Athena, poll, paginate results, return list of dicts."""
    print(f"[athena] submitting: {sql.strip().splitlines()[0][:80]}...")
    t0 = time.time()
    r = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": f"s3://{bucket}/query_results/"},
        WorkGroup=WORKGROUP,
    )
    qid = r["QueryExecutionId"]
    while True:
        st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = st["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Athena {state}: {st.get('StateChangeReason', '?')}")
        time.sleep(poll_seconds)
    t_exec = time.time() - t0
    print(f"[athena] succeeded in {t_exec:.1f}s; paginating results ...")

    rows: list[dict] = []
    header: list[str] | None = None
    paginator = athena.get_paginator("get_query_results")
    for page_i, page in enumerate(paginator.paginate(QueryExecutionId=qid, PaginationConfig={"PageSize": 1000})):
        for row in page["ResultSet"]["Rows"]:
            vals = [c.get("VarCharValue", "") for c in row["Data"]]
            if header is None:
                header = vals
            else:
                rows.append(dict(zip(header, vals)))
        if page_i and page_i % 50 == 0:
            print(f"[athena] ... {len(rows):,} rows so far")
    print(f"[athena] done: {len(rows):,} rows total")
    return rows


def num(s):
    """Parse number string. Handles empty → None."""
    if s is None or s == "":
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def parse_ind(s):
    """Parse Athena's text rendering of an ``array<smallint>`` into ``list[int]``.

    ``indicator_numeric_ids`` comes back from ``get_query_results`` as a VarChar
    string like ``"[16, 165, 4, 14]"`` (brackets, comma-separated, possibly with
    spaces). Empty / null / ``"[]"`` → ``[]``. Non-integer tokens are skipped so a
    malformed cell degrades to a shorter list rather than crashing the bake. The
    SCDI baker (``bake_pattern_scdis.py``) reads this as the window's ``ind`` field.
    """
    if not s:
        return []
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    out: list[int] = []
    for tok in s.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(int(tok))
        except ValueError:
            continue
    return out


# #358: curated-events loader. Same conventions as
# .tmp/decisions-form/_enrich_analogues.py (sluggify, apply known
# overrides, strip leading "the_").

_SLUG_OVERRIDES = {
    "democratic_republic_of_the_congo": "democratic_republic_of_congo",
    "republic_of_the_congo": "republic_of_congo",
    "turkey": "turkiye",
}


def _slug(name: str | None) -> str | None:
    """Thin delegate to the canonical shared implementation (#422 Bug 6).

    The transform itself lives in `qgi-ml/shared/slug.py`; this wrapper
    stays for call-site compatibility (`generate_pair_windows._slug` is
    referenced by existing tests + `resolve_country_slug` below).
    """
    # Import lazily so the module still imports when the shared/ package
    # is not on sys.path (e.g. during tooling that scans this file in
    # isolation). The happy path resolves fine because scripts/ is a
    # sibling of shared/ under qgi-ml/ and tests add the repo root.
    import sys
    from pathlib import Path
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    from shared.slug import country_slug
    return country_slug(name)


def load_country_event_years(curated_dir: Path) -> dict[str, set[int]]:
    """Map country slug → set of event years from qgi-data curated events.

    Returns a mapping like {"rwanda": {1959, 1962, 1994, ...}, ...} which
    the main() loop uses to filter the (a, b, end_year) result rows to
    only end-years that correspond to real events for country_b.

    Returns an empty dict (with a warning) if curated_dir is missing —
    the script still runs but the event-aligned Query 3 pass produces
    nothing beyond the top-N PPS pass. This keeps the script usable in
    contexts without the qgi-data sibling repo on disk.
    """
    if not curated_dir.is_dir():
        print(f"[events] curated dir not found: {curated_dir} — skipping event-year index")
        return {}

    out: dict[str, set[int]] = {}
    for p in sorted(curated_dir.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            with p.open("r", encoding="utf-8") as f:
                events = json.load(f)
        except Exception as exc:  # noqa: BLE001
            print(f"[events] skipping {p.name}: {exc}", file=sys.stderr)
            continue
        years = set()
        for e in events if isinstance(events, list) else []:
            if not isinstance(e, dict):
                continue
            y = e.get("year")
            if isinstance(y, int) and EVENT_YEAR_FLOOR <= y <= CURRENT_YEAR:
                years.add(y)
        if years:
            out[p.stem] = years
    print(f"[events] loaded event-year index for {len(out)} countries")
    return out


def resolve_country_slug(name: str | None, index: dict[str, set[int]]) -> str | None:
    """Match a country_b_name to a slug present in the event-year index.
    Uses the same overrides as the upstream enricher; returns None when
    no slug matches (script caller skips that row).
    """
    s = _slug(name)
    if not s:
        return None
    if s in index:
        return s
    if s in _SLUG_OVERRIDES and _SLUG_OVERRIDES[s] in index:
        return _SLUG_OVERRIDES[s]
    s2 = re.sub(r"^the_", "", s)
    if s2 in index:
        return s2
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bucket", required=True, help="S3 bucket for Athena query results (e.g. qgi-data-lake-771606957899)")
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--pair-windows-dir", default=None,
                   help="Output dir for per-country_a JSON files. Default: qgi-frontend/data/pair-windows/")
    p.add_argument("--analogues-path", default=None,
                   help="Path to analogues.json to enrich in-place. Default: qgi-frontend/data/analogues.json")
    p.add_argument("--analogues-enriched-path", default=None,
                   help="Path to analogues-enriched.json. Default: qgi-frontend/data/analogues-enriched.json")
    p.add_argument("--dry-run", action="store_true", help="Run queries + compute, but do not write files")
    p.add_argument(
        "--curated-events-dir",
        default=None,
        help="Dir containing qgi-data curated events JSONs (default: qgi-data/events/curated/ relative to repo root). "
        "Used by #358 event-year filter. If missing, the event-aligned Query 3 is skipped and the script "
        "falls back to the #352 top-N-by-PPS-only output.",
    )
    p.add_argument(
        "--skip-event-aligned",
        action="store_true",
        help="Skip Query 3 (event-aligned windows per #358). Useful for faster dev iterations "
        "or when you specifically want the old #352-shape output.",
    )
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    pair_windows_dir = Path(args.pair_windows_dir or (repo_root / "qgi-frontend" / "data" / "pair-windows"))
    analogues_path = Path(args.analogues_path or (repo_root / "qgi-frontend" / "data" / "analogues.json"))
    analogues_enriched_path = Path(args.analogues_enriched_path or (repo_root / "qgi-frontend" / "data" / "analogues-enriched.json"))
    curated_events_dir = Path(args.curated_events_dir or (repo_root / "qgi-data" / "events" / "curated"))

    print(f"repo_root             = {repo_root}")
    print(f"pair_windows_dir      = {pair_windows_dir}")
    print(f"analogues_path        = {analogues_path}")
    print(f"enriched analogues    = {analogues_enriched_path}")
    print(f"curated_events_dir    = {curated_events_dir}")
    print(f"skip_event_aligned    = {args.skip_event_aligned}  (#358)")
    print(f"dry_run               = {args.dry_run}")

    athena = boto3.client("athena", region_name=args.region)

    # ============================
    # Query 1: top-N windows per pair
    # ============================
    print("\n=== Query 1: top-N windows per pair ===")
    top_rows = run_query(athena, SQL_TOP_N, args.bucket)

    # Build per-country_a structure
    out: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"top": [], "hist": {}}))
    best_per_pair: dict[tuple[str, str], dict] = {}

    for r in top_rows:
        ca = str(r.get("country_a_id"))
        cb = str(r.get("country_b_id"))
        l = num(r.get("length"))
        sa = num(r.get("start_year_a"))
        sb = num(r.get("start_year_b"))
        ic = num(r.get("indicator_count"))
        ac = num(r.get("avg_correlation"))
        pps = num(r.get("pattern_power_score"))
        # #461: D7 plumbing — Athena returns "true"/"false" string for boolean.
        # Default to False on parse failure so legacy rows pre-#461 read as
        # "no predicted values" (the safer default for the user-facing badge).
        cp = str(r.get("contains_predicted", "")).lower() == "true"
        if None in (l, sa, sb, ic, ac, pps):
            continue
        entry = {"l": int(l), "sa": int(sa), "sb": int(sb), "ic": int(ic),
                 "ac": float(ac), "pps": float(pps), "cp": cp,
                 # §H: indicator id list for the SCDI baker (extra field; existing
                 # frontend readers ignore it, so this stays backward-compatible).
                 "ind": parse_ind(r.get("indicator_numeric_ids"))}
        out[ca][cb]["top"].append(entry)

    # Sort each top list DESC by pps (paranoia — should already be DESC from SQL)
    for ca, partners in out.items():
        for cb, data in partners.items():
            data["top"].sort(key=lambda x: -x["pps"])
            if data["top"]:
                best_per_pair[(ca, cb)] = data["top"][0]

    print(f"[agg] unique country_a values: {len(out)}")
    print(f"[agg] unique (a,b) pairs:     {len(best_per_pair)}")

    # ============================
    # Query 2: length histograms
    # ============================
    print("\n=== Query 2: length histograms ===")
    hist_rows = run_query(athena, SQL_HIST, args.bucket)
    for r in hist_rows:
        ca = str(r.get("country_a_id"))
        cb = str(r.get("country_b_id"))
        l = num(r.get("length"))
        cnt = num(r.get("cnt"))
        if None in (l, cnt):
            continue
        out[ca][cb]["hist"][str(int(l))] = int(cnt)

    # ============================
    # Query 3 (#358): top-K windows per (a, b, end_year) triple, filtered
    # to end-years matching real curated events for country_b. Merges
    # into out[ca][cb]["top"] (deduplicated on (l, sa, sb)).
    # ============================
    if args.skip_event_aligned:
        print("\n=== Query 3 skipped (--skip-event-aligned) ===")
    else:
        print("\n=== Query 3: event-aligned windows per (a, b, end_year) ===")
        event_years_by_slug = load_country_event_years(curated_events_dir)

        # Build reverse map: country_b_id → set of event years. Needs the
        # country_b_name → country_b_id mapping, which lives in the legacy
        # analogues.json (every country ever surfaced as an analogue has
        # a (country_b_id, country_b_name) there). Load it once.
        id_to_event_years: dict[str, set[int]] = {}
        if analogues_path.exists():
            with analogues_path.open("r", encoding="utf-8") as f:
                _legacy = json.load(f)
            seen_ids: set[str] = set()
            for _ca, _cats in _legacy.items():
                for _cat, _entries in _cats.items():
                    for _entry in _entries:
                        _cb_id = _entry.get("country_b_id")
                        _cb_name = _entry.get("country_b_name")
                        if _cb_id is None or str(_cb_id) in seen_ids:
                            continue
                        slug = resolve_country_slug(_cb_name, event_years_by_slug)
                        if slug is None:
                            continue
                        id_to_event_years[str(_cb_id)] = event_years_by_slug[slug]
                        seen_ids.add(str(_cb_id))
        print(f"[events] event-year index resolved for {len(id_to_event_years)} analogue country_b_ids")

        event_rows = run_query(athena, SQL_TOP_K_PER_END_YEAR, args.bucket)
        added = 0
        skipped_not_event_year = 0
        skipped_dupe = 0
        skipped_no_event_data = 0
        for r in event_rows:
            ca = str(r.get("country_a_id"))
            cb = str(r.get("country_b_id"))
            l = num(r.get("length"))
            sa = num(r.get("start_year_a"))
            sb = num(r.get("start_year_b"))
            ic = num(r.get("indicator_count"))
            ac = num(r.get("avg_correlation"))
            pps = num(r.get("pattern_power_score"))
            if None in (l, sa, sb, ic, ac, pps):
                continue
            end_year = int(sb) + int(l)
            cb_event_years = id_to_event_years.get(cb)
            if cb_event_years is None:
                # Country_b has no curated events. Skip — nothing to align to.
                skipped_no_event_data += 1
                continue
            # Keep windows whose end-year is within ±2 of any event year.
            # The ±2 tolerance matches the enrichment script's end_tolerance.
            if not any(abs(end_year - ey) <= 2 for ey in cb_event_years):
                skipped_not_event_year += 1
                continue
            # #461: D7 plumbing — same pattern as Query 1 above.
            cp = str(r.get("contains_predicted", "")).lower() == "true"
            entry = {
                "l": int(l), "sa": int(sa), "sb": int(sb),
                "ic": int(ic), "ac": float(ac), "pps": float(pps),
                "cp": cp,
                # §H: indicator id list for the SCDI baker (see Query 1).
                "ind": parse_ind(r.get("indicator_numeric_ids")),
            }
            # Deduplicate against existing top list (Query 1 may already
            # have this exact window if it's both PPS-top and event-aligned).
            existing = out[ca][cb]["top"]
            if any(
                e["l"] == entry["l"] and e["sa"] == entry["sa"] and e["sb"] == entry["sb"]
                for e in existing
            ):
                skipped_dupe += 1
                continue
            existing.append(entry)
            added += 1

        # Re-sort each pair's top list by PPS desc (new event-aligned
        # entries may have lower PPS than the top-N ones, so they go to
        # the end of the list — but order by PPS for consistency).
        for ca, partners in out.items():
            for cb, data in partners.items():
                data["top"].sort(key=lambda x: -x["pps"])

        print(f"[events] added {added} event-aligned windows to pair-windows output")
        print(f"[events]   rejected: {skipped_not_event_year} not near any event year")
        print(f"[events]   rejected: {skipped_dupe} already present (dupe of top-N)")
        print(f"[events]   rejected: {skipped_no_event_data} country_b has no curated events")

    # ============================
    # Write pair-windows files
    # ============================
    if args.dry_run:
        print("\n[DRY] would write", len(out), "pair-windows JSON files")
    else:
        pair_windows_dir.mkdir(parents=True, exist_ok=True)
        for ca, partners in out.items():
            path = pair_windows_dir / f"{ca}.json"
            with path.open("w", encoding="utf-8") as f:
                # compact encoding; these are data files, not meant for humans
                json.dump(dict(partners), f, separators=(",", ":"))
        print(f"\n[write] pair-windows: {len(out)} files -> {pair_windows_dir}")

    # ============================
    # Enrich analogues.json
    # ============================
    if analogues_path.exists():
        with analogues_path.open("r", encoding="utf-8") as f:
            analogues = json.load(f)
        enriched = 0
        total = 0
        for ca, cats in analogues.items():
            for cat, entries in cats.items():
                for entry in entries:
                    total += 1
                    key = (str(ca), str(entry.get("country_b_id")))
                    best = best_per_pair.get(key)
                    if best:
                        entry["best_pattern_length"] = best["l"]
                        entry["best_pattern_start_a"] = best["sa"]
                        entry["best_pattern_start_b"] = best["sb"]
                        enriched += 1
        print(f"\n[analogues] enriched {enriched}/{total} entries in {analogues_path}")
        if not args.dry_run:
            with analogues_path.open("w", encoding="utf-8") as f:
                json.dump(analogues, f, indent=2)
    else:
        print(f"[analogues] file not found: {analogues_path}")

    # ============================
    # Enrich analogues-enriched.json (has extra nested structure: .countries[ca][cat] = {subject, analogues[]})
    # ============================
    if analogues_enriched_path.exists():
        with analogues_enriched_path.open("r", encoding="utf-8") as f:
            enriched_doc = json.load(f)
        enriched2 = 0
        total2 = 0
        countries_map = enriched_doc.get("countries", {})
        for ca, cats in countries_map.items():
            for cat, section in cats.items():
                analogues_list = section.get("analogues", [])
                for entry in analogues_list:
                    total2 += 1
                    key = (str(ca), str(entry.get("country_b_id")))
                    best = best_per_pair.get(key)
                    if best:
                        entry["best_pattern_length"] = best["l"]
                        entry["best_pattern_start_a"] = best["sa"]
                        entry["best_pattern_start_b"] = best["sb"]
                        enriched2 += 1
        print(f"[analogues-enriched] enriched {enriched2}/{total2} entries in {analogues_enriched_path}")
        if not args.dry_run:
            with analogues_enriched_path.open("w", encoding="utf-8") as f:
                json.dump(enriched_doc, f, indent=2)
    else:
        print(f"[analogues-enriched] file not found: {analogues_enriched_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
