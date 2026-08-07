#!/usr/bin/env python3
"""
generate_country_events_json.py — rebuild qgi-frontend/data/country-events.json
from the FULL qgi-data/events/curated/ directory.

T20 #313 fix (2026-04-19): previous writer missed 79 of 198 curated
countries (DRC, Belarus, Serbia, Rwanda, Uganda, Kosovo, Taiwan, Sweden,
Netherlands, Turkey-as-`turkey.json`, etc). Their profile pages rendered
empty event timelines despite curated data existing.

Root cause: slug-generation mismatch between the file names and the key
the frontend looks up with. The frontend does:

    key = name.lower()
             .replace(/^the\\s+/, "")
             .replace(/\\bof the\\b/g, "of")
             .replace(/[-\\s]+/g, "_")
             .replace(/[^a-z0-9_]/g, "")

Fix: for each curated file, use the FILENAME (without .json) as the key.
All 198 filenames already follow snake_case lowercase convention — they
are the canonical slug. No name-based mapping needed.

Also normalizes event categories to the 71-canonical taxonomy per
qgi-data/events/category_mapping.json so orphan slugs (327 of them at
31.8% of all events per T20) stop reaching the frontend.

Usage:
    python qgi-ml/scripts/generate_country_events_json.py \\
        --curated qgi-data/events/curated \\
        --mapping qgi-data/events/category_mapping.json \\
        --output qgi-frontend/data/country-events.json
"""

import argparse
import json
import os
from pathlib import Path


def load_mapping(mapping_path: Path) -> dict[str, str]:
    """Load the 71-canonical-category normalization map."""
    with open(mapping_path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mapping", {})


def normalize_category(raw: str, mapping: dict[str, str]) -> str:
    """Normalize a raw category label to one of the 71 canonical slugs.

    Fallback chain:
      1. Exact match in mapping.
      2. Stripped match.
      3. Leave raw string as-is — frontend will bucket it as 'Uncategorized'.
         We DON'T fall back to 'other' because that pollutes the taxonomy
         count downstream; better to surface the unmapped slug for audit.
    """
    if not raw or not isinstance(raw, str):
        return "uncategorized"
    if raw in mapping:
        return mapping[raw]
    stripped = raw.strip()
    if stripped in mapping:
        return mapping[stripped]
    return stripped.lower().replace(" ", "_")


def build_country_events(curated_dir: Path, mapping: dict[str, str]) -> dict:
    """Read every *.json in curated/ and return a {slug: [events]} mapping."""
    out: dict[str, list[dict]] = {}
    canonical_counts = {"canonical": 0, "fallback": 0}
    canonical_set = set(mapping.values())

    files = sorted(curated_dir.glob("*.json"))
    print(f"Reading {len(files)} curated country files from {curated_dir}")

    for f in files:
        slug = f.stem  # e.g. democratic_republic_of_congo
        if slug.startswith("_"):  # skip _backup_* directories / synthetic files
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                events = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARN: skipping {f.name}: {e}")
            continue

        if not isinstance(events, list):
            print(f"  WARN: {f.name} is not a JSON array, skipping")
            continue

        norm = []
        for ev in events:
            if not isinstance(ev, dict):
                continue
            year = ev.get("year")
            title = ev.get("title", "")
            raw_cat = ev.get("category", "")
            if not year or not isinstance(year, int):
                continue
            cat = normalize_category(raw_cat, mapping)
            if cat in canonical_set:
                canonical_counts["canonical"] += 1
            else:
                canonical_counts["fallback"] += 1
            norm.append({
                "year": year,
                "title": title,
                "category": cat,
            })

        # Sort by year ascending so the frontend doesn't need to re-sort.
        norm.sort(key=lambda e: e["year"])
        out[slug] = norm

    return out, canonical_counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--curated",
        type=Path,
        default=Path("qgi-data/events/curated"),
        help="Path to qgi-data/events/curated/ directory",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("qgi-data/events/category_mapping.json"),
        help="Path to category_mapping.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("qgi-frontend/data/country-events.json"),
        help="Output path for country-events.json",
    )
    args = parser.parse_args()

    if not args.curated.exists():
        print(f"ERROR: curated dir not found: {args.curated}")
        return 1
    if not args.mapping.exists():
        print(f"ERROR: mapping file not found: {args.mapping}")
        return 1

    mapping = load_mapping(args.mapping)
    print(f"Loaded {len(mapping)} category mappings -> {len(set(mapping.values()))} canonical targets")

    out, counts = build_country_events(args.curated, mapping)

    total_events = sum(len(v) for v in out.values())
    print(f"\nWrote {len(out)} countries, {total_events:,} events")
    print(f"  Canonical categories: {counts['canonical']:,} ({100*counts['canonical']/max(total_events,1):.1f}%)")
    print(f"  Fallback/unmapped:    {counts['fallback']:,} ({100*counts['fallback']/max(total_events,1):.1f}%)")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    size_kb = os.path.getsize(args.output) / 1024
    print(f"\n=> {args.output} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
