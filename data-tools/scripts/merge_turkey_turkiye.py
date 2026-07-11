#!/usr/bin/env python3
# THROWAWAY — one-off script, no tests per #373.
# Ran once to rename Turkey → Türkiye across curated event files after the
# UN formally recognized the Türkiye spelling. The merge is irreversible
# (curated files overwritten in-place); re-running this script would be
# a no-op or could corrupt unrelated files. Kept in the repo for audit
# trail only. Do not re-run.
"""
merge_turkey_turkiye.py — merge qgi-data/events/curated/turkey.json into
turkiye.json, then delete turkey.json.

T10 #303 + T20 #313: both files existed but the frontend slug lookup for
country_name "Türkiye" resolves to `turkiye`, so the 52 events in
turkey.json were silently dropped. Merge to consolidate and remove the
redundant file.

Dedup rule: events match if (year, normalized_title_prefix_40) match.
Keep the entry from turkiye.json (newer curation cycle) on conflict.
"""

import json
import sys
from pathlib import Path


def normalize(title: str) -> str:
    return (title or "").strip().lower()[:40]


def main() -> int:
    root = Path(__file__).parent.parent
    turkey = root / "events" / "curated" / "turkey.json"
    turkiye = root / "events" / "curated" / "turkiye.json"

    if not turkiye.exists():
        print(f"ERROR: {turkiye} missing — abort.")
        return 1
    if not turkey.exists():
        print(f"No {turkey} to merge — nothing to do.")
        return 0

    with open(turkey, encoding="utf-8") as f:
        turkey_events = json.load(f)
    with open(turkiye, encoding="utf-8") as f:
        turkiye_events = json.load(f)

    print(f"turkey.json:  {len(turkey_events)} events")
    print(f"turkiye.json: {len(turkiye_events)} events")

    # Index turkiye by (year, normalized_title).
    seen = {(e.get("year"), normalize(e.get("title", ""))) for e in turkiye_events}

    added = []
    for ev in turkey_events:
        key = (ev.get("year"), normalize(ev.get("title", "")))
        if key in seen:
            continue
        added.append(ev)
        seen.add(key)

    merged = turkiye_events + added
    # Stable sort by year (preserves curator intent within a year).
    merged.sort(key=lambda e: e.get("year", 0))

    with open(turkiye, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"\nMerged {len(added)} unique events from turkey.json into turkiye.json")
    print(f"turkiye.json: {len(turkiye_events)} -> {len(merged)} events")

    turkey.unlink()
    print(f"Deleted {turkey}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
