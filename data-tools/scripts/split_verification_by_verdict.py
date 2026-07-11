#!/usr/bin/env python3
"""
Split verification/ files by verdict (#372).

Today `events/verification/` commingles three states:
  - VERIFIED / TRUE  — adjudicator confirmed the event
  - FALSE            — adjudicator rejected the event
  - UNVERIFIED / missing — event was never adjudicated

The pipeline's ingest step should only see TRUE/FALSE entries (it filters FALSE
out, keeps TRUE, falls back to curated/ for everything else). This script
rewrites each verification file to contain ONLY verdicted entries. Unverified
entries are dropped — they already exist in events/curated/X.json, which the
ingest script unions in as the "fallback" source.

Also NORMALISES the schema across the 9 dialect variants observed in April 2026
(status/verdict/verification_status × note/notes/reason/verification_note ×
raw-array vs. dict-wrapped-with-events/results key). Output schema, per event:
    {
      "year":    int,
      "title":   str,
      "verdict": "TRUE" | "FALSE",
      "reason":  str | None,
      "source":  str | None (URL, if any — preserved for audit)
    }

Files with zero verdicted entries are DELETED entirely, so filesystem presence
becomes the "has been adjudicated" signal. Future qgi-agent sessions scanning
verification/ see immediately which countries still need a verifier pass.

Idempotent: re-running after new verifications is safe.

Usage:
    python split_verification_by_verdict.py          # dry-run by default
    python split_verification_by_verdict.py --apply  # write changes + delete empties
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
VERIFICATION_DIR = REPO_ROOT / "events" / "verification"
CURATED_DIR = REPO_ROOT / "events" / "curated"

# Every field name we've seen that holds the adjudication label
ADJUDICATION_FIELDS = ("verdict", "status", "verification_status", "verification_verdict", "verified")
# Every field name we've seen that holds the justification text
REASON_FIELDS = ("reason", "note", "notes", "verification_note")
# Source-URL fields, in preference order
SOURCE_FIELDS = ("source", "sources", "url", "verification_url", "verification_source")
# Dict-wrapper keys that hold the main events list (in preference order)
EVENTS_KEYS = ("events", "results")

# Values we treat as "adjudicator confirmed this event is real"
TRUE_LABELS = {"TRUE", "VERIFIED"}
# Values we treat as "adjudicator rejected this event"
FALSE_LABELS = {"FALSE"}


def normalize_verdict(event: dict) -> str | None:
    """Return 'TRUE', 'FALSE', or None (unverdicted)."""
    for field in ADJUDICATION_FIELDS:
        if field in event and event[field] is not None:
            val = str(event[field]).strip().upper()
            if val in TRUE_LABELS:
                return "TRUE"
            if val in FALSE_LABELS:
                return "FALSE"
            # UNVERIFIED or any other value → treat as unverdicted
            return None
    return None


def normalize_reason(event: dict) -> str | None:
    """Pick the first non-empty reason-like field."""
    for field in REASON_FIELDS:
        val = event.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def extract_source(event: dict) -> str | None:
    """Preserve source URL if present (for audit)."""
    for field in SOURCE_FIELDS:
        val = event.get(field)
        if isinstance(val, str) and val.strip().startswith("http"):
            return val.strip()
        if isinstance(val, list) and val and isinstance(val[0], str) and val[0].strip().startswith("http"):
            return val[0].strip()
    return None


def _match_normalize(title) -> str:
    """Robust title normalization for cross-dir matching (strips punctuation + non-word chars)."""
    s = str(title or '').lower()
    s = re.sub(r'[^\w\s]', ' ', s, flags=re.UNICODE)
    return ' '.join(s.split())


def load_curated_titles(curated_dir: Path) -> dict:
    """Build {country_stem: {(year, match_normalized_title): original_title}} from curated/.

    Used to heal encoding corruption in verification files: if a verification entry
    fuzzy-matches a curated entry, we write the CURATED title into the split output
    so future runs of ingest_events.py match exactly. Also builds a per-country list
    of (year, original_title) tuples for difflib fallback when strict norm fails.
    """
    index = {}
    lists = {}
    if not curated_dir.exists():
        return index, lists
    for f in sorted(curated_dir.glob("*.json")):
        try:
            data = json.load(f.open(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, list):
            continue
        per_country = {}
        per_list = []
        for e in data:
            if not isinstance(e, dict):
                continue
            year = e.get("year")
            title = e.get("title")
            if year is None or not title:
                continue
            per_country[(int(year), _match_normalize(title))] = title
            per_list.append((int(year), title))
        index[f.stem] = per_country
        lists[f.stem] = per_list
    return index, lists


def heal_title(country_stem: str, year, verification_title: str,
               curated_index: dict, curated_lists: dict) -> str:
    """Try to swap in the curated title for a fuzzy-matched verification entry.

    Returns the curated title if a match is found; otherwise returns the input
    verification_title unchanged. Strategy:
      1. Exact match on (year, match-normalized title) -> curated title
      2. Fallback: difflib ratio >= 0.75 against same-year curated titles -> curated title
      3. Else: return verification_title as-is
    """
    per_country = curated_index.get(country_stem, {})
    per_list = curated_lists.get(country_stem, [])
    if year is None or not verification_title:
        return verification_title
    year = int(year)
    # Strategy 1
    key = (year, _match_normalize(verification_title))
    if key in per_country:
        return per_country[key]
    # Strategy 2 — fuzzy match against same-year curated titles
    same_year = [t for (y, t) in per_list if y == year]
    if same_year:
        norm_ver = _match_normalize(verification_title)
        best = max(same_year, key=lambda t: difflib.SequenceMatcher(None, norm_ver, _match_normalize(t)).ratio())
        if difflib.SequenceMatcher(None, norm_ver, _match_normalize(best)).ratio() >= 0.75:
            return best
    return verification_title


def extract_events_list(data) -> list:
    """Pull the main events list out of a file, regardless of wrapping."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in EVENTS_KEYS:
            if key in data and isinstance(data[key], list) and data[key]:
                # Ensure it's an events list (dicts with titles), not e.g. a summary
                if isinstance(data[key][0], dict) and "title" in data[key][0]:
                    return data[key]
    return []


def process_file(path: Path, curated_index: dict, curated_lists: dict) -> dict:
    """Return a stats dict; do NOT write unless called from apply path."""
    try:
        raw = json.load(path.open(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"file": path.name, "error": f"JSON parse error: {e}"}

    events = extract_events_list(raw)
    if not events:
        return {"file": path.name, "error": "no events list found"}

    # v2 double-verify guard (2026-07-02): once migrate_verification_to_v2.py has
    # run, entries carry verifications[]/verify_count/consensus_* fields. This
    # script rebuilds flat {year,title,verdict,reason,source} dicts and only knows
    # TRUE/FALSE — running it on v2 data would strip the audit trail and silently
    # drop every PARTIAL/UNCERTAIN/CONTESTED verdict. Refuse loudly.
    if any(isinstance(e, dict) and "verifications" in e for e in events):
        raise SystemExit(
            f"REFUSING to process {path.name}: it contains v2 double-verify entries "
            f"(verifications[]). This script predates the v2 schema and would destroy "
            f"it. Use scripts/validate_verification.py + the Mode B workflow instead."
        )

    n_before = len(events)
    kept = []
    dropped_unverified = 0
    healed_titles = 0
    true_count = 0
    false_count = 0

    for e in events:
        if not isinstance(e, dict):
            continue
        verdict = normalize_verdict(e)
        if verdict is None:
            dropped_unverified += 1
            continue
        original_title = e.get("title")
        healed = heal_title(path.stem, e.get("year"), original_title,
                            curated_index, curated_lists)
        if healed != original_title:
            healed_titles += 1
        normalized = {
            "year": e.get("year"),
            "title": healed,
            "verdict": verdict,
            "reason": normalize_reason(e),
        }
        source = extract_source(e)
        if source:
            normalized["source"] = source
        kept.append(normalized)
        if verdict == "TRUE":
            true_count += 1
        else:
            false_count += 1

    return {
        "file": path.name,
        "n_before": n_before,
        "n_kept": len(kept),
        "n_true": true_count,
        "n_false": false_count,
        "n_dropped": dropped_unverified,
        "n_healed": healed_titles,
        "kept_events": kept,
        "delete": len(kept) == 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write changes + delete empty files (default: dry-run)")
    args = parser.parse_args()

    if not VERIFICATION_DIR.exists():
        print(f"ERROR: {VERIFICATION_DIR} does not exist", file=sys.stderr)
        sys.exit(1)

    files = sorted(VERIFICATION_DIR.glob("*.json"))
    print(f"Scanning {len(files)} verification files in {VERIFICATION_DIR}")
    print(f"Loading curated titles from {CURATED_DIR} for encoding-corruption healing...")
    curated_index, curated_lists = load_curated_titles(CURATED_DIR)
    print(f"Loaded curated index for {len(curated_index)} countries")
    print(f"Mode: {'APPLY (writing + deleting)' if args.apply else 'DRY-RUN (no changes)'}")
    print()

    totals = {"files_rewritten": 0, "files_deleted": 0, "events_before": 0,
              "events_kept": 0, "events_dropped": 0, "events_healed": 0,
              "true": 0, "false": 0, "errors": 0}
    error_files = []

    for path in files:
        stats = process_file(path, curated_index, curated_lists)
        if "error" in stats:
            print(f"  ERROR {stats['file']}: {stats['error']}")
            totals["errors"] += 1
            error_files.append(stats["file"])
            continue

        totals["events_before"] += stats["n_before"]
        totals["events_kept"] += stats["n_kept"]
        totals["events_dropped"] += stats["n_dropped"]
        totals["events_healed"] += stats["n_healed"]
        totals["true"] += stats["n_true"]
        totals["false"] += stats["n_false"]

        action = "DELETE" if stats["delete"] else "REWRITE"

        print(f"  {stats['file']}: {stats['n_before']} -> {stats['n_kept']} "
              f"(T={stats['n_true']}, F={stats['n_false']}, dropped={stats['n_dropped']}, "
              f"healed={stats['n_healed']}) [{action}]")

        if args.apply:
            if stats["delete"]:
                path.unlink()
                totals["files_deleted"] += 1
            else:
                with path.open("w", encoding="utf-8") as f:
                    json.dump(stats["kept_events"], f, indent=2, ensure_ascii=False)
                    f.write("\n")
                totals["files_rewritten"] += 1

    print()
    print("=" * 70)
    print(f"Events before:   {totals['events_before']}")
    print(f"Events kept:     {totals['events_kept']}  (TRUE={totals['true']}, FALSE={totals['false']})")
    print(f"Events dropped:  {totals['events_dropped']}  (unverdicted -- already in curated/)")
    print(f"Events healed:   {totals['events_healed']}  (title swapped to curated canonical for matching)")
    print(f"Files rewritten: {totals['files_rewritten']}")
    print(f"Files deleted:   {totals['files_deleted']}  (no verdicted entries remained)")
    if totals["errors"]:
        print(f"Files skipped (errors): {totals['errors']}  — {error_files}")
    if not args.apply:
        print("\n[DRY-RUN] Re-run with --apply to write changes.")


if __name__ == "__main__":
    main()
