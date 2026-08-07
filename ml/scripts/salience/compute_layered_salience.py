"""
Standalone layered-salience computation module.

Implements the validated formula from `docs/specs/methodology/event-taxonomy-layered-design.md`
with all 5 implementation guardrails from the QA validation pass.

Stage A of ticket #233 — runs locally on `qgi-data/events/curated/*.json` without
needing the pipeline. Used to validate the formula against the full event corpus
before porting into `pipeline-recipe-engine-finalize` Lambda.

USAGE:
    python compute_layered_salience.py            # process all curated/*.json
    python compute_layered_salience.py --country austria  # single country

Output: qgi-ml/output/salience/{country}.json with l1_scores + l2_scores dicts.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

# Repo-relative paths (assumes script is run from anywhere; uses absolute repo root)
REPO_ROOT = Path(__file__).resolve().parents[3]  # qgi-ml/scripts/salience/ -> qgi-6.0/
DATA_EVENTS = REPO_ROOT / "qgi-data" / "events" / "curated"
TAXONOMY_FILE = REPO_ROOT / "qgi-data" / "events" / "taxonomy_hierarchy.json"
CATEGORY_MAPPING = REPO_ROOT / "qgi-data" / "events" / "category_mapping.json"
OUTPUT_DIR = REPO_ROOT / "qgi-ml" / "output" / "salience"

# Per the design doc, λ=0.15 → half-life ≈ 4.6 years (acute signal decay)
DECAY_LAMBDA = 0.15

# Per Guardrail G-3 — events tagged in multiple L1 groups; recorded for future
# global-rollup deduplication
DUAL_LABELED_CATEGORIES = {"sanctions_and_arms_embargo"}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_taxonomy() -> dict[str, Any]:
    """Load the taxonomy_hierarchy.json and build a Layer3 → (L1_id, L2_id) lookup."""
    with TAXONOMY_FILE.open(encoding="utf-8-sig") as f:
        taxonomy = json.load(f)

    l3_to_paths: dict[str, list[tuple[str, str]]] = {}
    for l1 in taxonomy["layer1"]:
        for l2 in l1["layer2"]:
            for l3 in l2["layer3"]:
                l3_to_paths.setdefault(l3, []).append((l1["id"], l2["id"]))
    return {"taxonomy": taxonomy, "l3_to_paths": l3_to_paths}


def load_canonical_categories() -> set[str]:
    with CATEGORY_MAPPING.open(encoding="utf-8-sig") as f:
        return set(json.load(f)["taxonomy"])


# ---------------------------------------------------------------------------
# Salience computation
# ---------------------------------------------------------------------------


def compute_event_raw_salience(event: dict[str, Any]) -> float:
    """
    Raw salience for a single event. Stage A heuristic: severity-weighted with
    a default of 0.5 if no explicit severity. Will be replaced when the pipeline's
    actual salience score is wired up — for now this lets us validate the
    aggregation math.
    """
    # Look for explicit numeric severity, fall back to default
    sev = event.get("severity")
    if isinstance(sev, (int, float)):
        s = float(sev)
        # Normalize to [0, 1] if it looks like a 1-10 or 1-5 scale
        if s > 1.0:
            s = s / 10.0 if s <= 10.0 else 1.0
        s = max(0.0, min(1.0, s))
        return s
    # Default: neutral mid-salience for unrated events
    return 0.5


def decay_weight(event_year: int, current_year: int) -> float:
    """exp(-λ × years_since)"""
    years_since = max(0, current_year - event_year)
    return math.exp(-DECAY_LAMBDA * years_since)


def compute_layered_salience(
    events: list[dict[str, Any]],
    taxonomy_lookup: dict[str, Any],
    canonical_categories: set[str],
    current_year: int = 2026,
) -> dict[str, Any]:
    """
    Apply the validated formula:
      L2_salience = max(raw × decay for each L3 child event)
      L1_salience = max(L2_salience for each L2 child)

    Returns: {"l1_scores": {...}, "l2_scores": {...}, "stats": {...}}
    """
    l3_to_paths = taxonomy_lookup["l3_to_paths"]
    taxonomy = taxonomy_lookup["taxonomy"]

    # Per-(L1, L2, L3) scoring buckets
    l3_scores: dict[tuple[str, str, str], list[float]] = {}
    skipped_invalid_category = 0
    skipped_invalid_year = 0

    for event in events:
        category = event.get("category")

        # Guardrail: bounds check on raw salience (G-1)
        raw = compute_event_raw_salience(event)
        assert 0.0 <= raw <= 1.0, f"Raw salience {raw} out of [0,1] for event"

        # Validate category is canonical
        if category not in canonical_categories:
            skipped_invalid_category += 1
            continue

        year = event.get("year")
        if not isinstance(year, int):
            skipped_invalid_year += 1
            continue

        decayed = raw * decay_weight(year, current_year)

        # Map L3 → all (L1, L2) paths (handles dual-labels per G-3)
        paths = l3_to_paths.get(category, [])
        for l1_id, l2_id in paths:
            l3_scores.setdefault((l1_id, l2_id, category), []).append(decayed)

    # Aggregate L3 → L2 (max) → L1 (max). Guardrail G-2: default=0.0 on empty.
    l2_scores: dict[str, float] = {}
    for l1 in taxonomy["layer1"]:
        for l2 in l1["layer2"]:
            children_scores = [
                max(scores)
                for (l1_id, l2_id, _), scores in l3_scores.items()
                if l1_id == l1["id"] and l2_id == l2["id"]
            ]
            l2_scores[l2["id"]] = max(children_scores, default=0.0)

    l1_scores: dict[str, float] = {}
    for l1 in taxonomy["layer1"]:
        children_scores = [
            l2_scores[l2["id"]] for l2 in l1["layer2"]
        ]
        l1_scores[l1["id"]] = max(children_scores, default=0.0)

    return {
        "l1_scores": {k: round(v, 4) for k, v in l1_scores.items()},
        "l2_scores": {k: round(v, 4) for k, v in l2_scores.items()},
        "stats": {
            "total_events": len(events),
            "skipped_invalid_category": skipped_invalid_category,
            "skipped_invalid_year": skipped_invalid_year,
            "decay_lambda": DECAY_LAMBDA,
            "current_year": current_year,
            "dual_labeled_categories": sorted(DUAL_LABELED_CATEGORIES),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def process_country(country_file: Path, taxonomy_lookup, canonical, current_year):
    with country_file.open(encoding="utf-8-sig") as f:
        events = json.load(f)
    if not isinstance(events, list):
        return None
    result = compute_layered_salience(events, taxonomy_lookup, canonical, current_year)
    result["country"] = country_file.stem
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", help="Single country slug (e.g. austria)")
    parser.add_argument("--year", type=int, default=2026, help="Current year for decay anchor")
    parser.add_argument("--summary-only", action="store_true", help="Skip per-country file writes")
    args = parser.parse_args()

    print(f"Loading taxonomy from {TAXONOMY_FILE}")
    taxonomy_lookup = load_taxonomy()
    canonical = load_canonical_categories()
    print(
        f"  L1 groups: {taxonomy_lookup['taxonomy']['summary']['layer1_count']}, "
        f"L2 sub-categories: {taxonomy_lookup['taxonomy']['summary']['layer2_count']}, "
        f"L3 canonical: {len(canonical)}"
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = (
        [DATA_EVENTS / f"{args.country}.json"]
        if args.country
        else sorted(DATA_EVENTS.glob("*.json"))
    )

    if not files or (args.country and not files[0].exists()):
        print(f"No country files found for: {args.country or 'all'}")
        return

    print(f"\nProcessing {len(files)} countries...")
    print(f"{'Country':<32} {'Top L1 (id:score)':<35} {'Events':>8} {'SkipCat':>8}")
    print("-" * 88)

    summary = []
    for country_file in files:
        result = process_country(country_file, taxonomy_lookup, canonical, args.year)
        if result is None:
            continue
        summary.append(result)

        # Find top L1 score
        top_l1 = max(result["l1_scores"].items(), key=lambda x: x[1])
        print(
            f"{result['country']:<32} {top_l1[0]}: {top_l1[1]:>5.3f}{'':<26} "
            f"{result['stats']['total_events']:>8} {result['stats']['skipped_invalid_category']:>8}"
        )

        if not args.summary_only:
            out_path = OUTPUT_DIR / f"{result['country']}.json"
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)

    # Aggregate stats
    total_events = sum(r["stats"]["total_events"] for r in summary)
    total_skipped = sum(r["stats"]["skipped_invalid_category"] for r in summary)
    print(f"\nProcessed {len(summary)} countries / {total_events} events / {total_skipped} skipped (non-canonical)")

    if not args.summary_only:
        index_path = OUTPUT_DIR / "_index.json"
        with index_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated": "2026-04-16",
                    "country_count": len(summary),
                    "total_events": total_events,
                    "decay_lambda": DECAY_LAMBDA,
                    "guardrails_applied": [
                        "G-1 bounds assertion on raw salience",
                        "G-2 max(default=0.0) on empty L2/L1",
                        "G-3 dual-label note for sanctions_and_arms_embargo",
                        "G-4 half-life label fixed (4.6yr not ~5yr)",
                        "G-5 layered scores are NEW fields; existing salience_score untouched",
                    ],
                },
                f,
                indent=2,
            )
        print(f"\nWrote per-country JSONs to {OUTPUT_DIR}")
        print(f"Wrote index to {index_path}")


if __name__ == "__main__":
    main()
