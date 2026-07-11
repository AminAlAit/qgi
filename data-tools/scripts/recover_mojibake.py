#!/usr/bin/env python3
"""
Recover mojibake (UTF-8 → cp1252 → UTF-8 double-encoding) in curated event
JSONs. #434 (2026-04-25).

The bug class: a Windows tool wrote UTF-8 bytes, something downstream
re-decoded those bytes as cp1252 (Windows-1252), and then re-encoded the
resulting string as UTF-8. Net result: characters like 'é' get rendered
as 'Ã©' on country profile pages.

Recovery: encode the mojibake string back to cp1252 (which produces the
original UTF-8 bytes), then decode as UTF-8 (which produces the original
character). When cp1252 fails, fall back to latin-1 — covers the small
fraction of cases where the producer wasn't on Windows.

Idempotent: running twice on a clean file is a no-op.

Usage:
    python qgi-data/scripts/recover_mojibake.py
    python qgi-data/scripts/recover_mojibake.py --dry-run

CI integration: scripts/validate_events.py rejects any title containing
the mojibake signature, so a re-introduction fails the validate workflow
before merge.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CURATED_DIR = Path(__file__).resolve().parent.parent / "events" / "curated"

# A Ã (U+00C3) followed by Latin-1 supplement, OR an â (U+00E2) followed
# by Unicode general-punctuation / Letterlike Symbols, is the canonical
# mojibake signature for double-encoded UTF-8.
MOJIBAKE_RE = re.compile(r"[\u00C3\u00E2][\u00A0-\u00BF\u2010-\u21FF]+")


def recover(s: str) -> tuple[str, bool]:
    """Return (recovered_string, did_recover).

    Tries cp1252 first (the Windows tool case which covers ~95%
    of observed mojibake), then latin-1 (POSIX fallback). Refuses to
    write back if the result still contains mojibake (defends against
    multi-pass re-encoding which would need more than two roundtrips
    and likely indicates a non-recoverable edge case).
    """
    if not MOJIBAKE_RE.search(s):
        return s, False
    for codec in ("cp1252", "latin-1"):
        try:
            recovered = s.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if not MOJIBAKE_RE.search(recovered):
            return recovered, True
    return s, False


def fix_file(path: Path, dry_run: bool) -> tuple[int, int]:
    """Returns (changes_in_this_file, total_events_in_file)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return 0, 0
    changes = 0
    for ev in data:
        if not isinstance(ev, dict):
            continue
        for key in ("title", "description", "category"):
            v = ev.get(key)
            if isinstance(v, str):
                new, did = recover(v)
                if did:
                    ev[key] = new
                    changes += 1
    if changes and not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return changes, len(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be recovered without writing files",
    )
    parser.add_argument(
        "--curated",
        type=Path,
        default=CURATED_DIR,
        help="Path to events/curated/",
    )
    args = parser.parse_args()

    if not args.curated.exists():
        print(f"ERROR: curated dir not found: {args.curated}")
        return 1

    files = sorted(args.curated.glob("*.json"))
    total_files = total_changes = total_files_changed = 0
    for f in files:
        if f.stem.startswith("_"):  # skip _backup_ etc.
            continue
        total_files += 1
        changes, _ = fix_file(f, args.dry_run)
        if changes:
            verb = "would recover" if args.dry_run else "recovered"
            print(f"{f.name}: {verb} {changes} fields")
            total_files_changed += 1
            total_changes += changes
    suffix = " (dry run, no files written)" if args.dry_run else ""
    print(
        f"\nProcessed {total_files} files; {total_changes} fields across "
        f"{total_files_changed} files{suffix}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
