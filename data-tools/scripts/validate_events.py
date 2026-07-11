#!/usr/bin/env python3
"""
CI validation for curated event JSON files.

Runs on every push to qgi-data. Fails if any event file violates the
canonical schema (same rules as jordan.json, the reference file).

Exit code 0 = all valid, 1 = validation errors found.

#422 refactor (2026-04-24):
  - Bug 1: mutable module-level globals replaced with FileResult +
    AggregateResult dataclasses returned from validate_file() / main().
    Makes the validator re-runnable in the same process + eliminates
    test-fixture drift.
  - Bug 2: enforce that every event's `category` is one of the 71
    canonical layer-3 codes in `events/taxonomy_hierarchy.json`. Blocks
    the confabulation class that the curation template addressed
    prompt-side.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

EVENTS_DIR = Path(__file__).resolve().parent.parent / "events" / "curated"
TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "events" / "taxonomy_hierarchy.json"
ALLOWED_YEAR_RANGE = (1900, 2030)  # Events can predate WB indicator data (1960+)
MAX_TITLE_LENGTH = 120

# #434 Mojibake guard: a Ã / â followed by Latin-1-supplement or Unicode
# punctuation char is the canonical signature of UTF-8 → cp1252 → UTF-8
# double-encoding. Flagged here so a re-introduction (e.g. a curation
# tool that mishandles encoding on Windows) fails CI before merge.
import re as _re_mojibake_module  # noqa: E402  (placed near guard for locality)
MOJIBAKE_RE = _re_mojibake_module.compile(r"[\u00C3\u00E2][\u00A0-\u00BF\u2010-\u21FF]+")

# Count thresholds
MIN_EVENTS_PER_COUNTRY = 10
MAX_RECENCY_RATIO = 0.35  # max fraction of events in 2020-2030 window


# ─── dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class FileResult:
    """Outcome of validating a single event JSON file."""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    events_count: int = 0


@dataclass
class AggregateResult:
    """Aggregated outcome across a directory of event files."""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_files: int = 0
    total_events: int = 0

    def merge(self, file_result: FileResult) -> None:
        self.errors.extend(file_result.errors)
        self.warnings.extend(file_result.warnings)
        self.total_events += file_result.events_count
        self.total_files += 1


# ─── taxonomy ────────────────────────────────────────────────────────────────

def load_valid_categories(taxonomy_path: Path = TAXONOMY_PATH) -> set[str]:
    """Extract the 71 canonical layer-3 category codes from taxonomy_hierarchy.json.

    Returns an empty set if the taxonomy can't be loaded — callers decide
    whether to enforce. `validate_file()` falls back to type-only checks
    when the set is empty, matching the old behavior.
    """
    try:
        with open(taxonomy_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

    codes: set[str] = set()
    for l1 in data.get("layer1", []):
        for l2 in l1.get("layer2", []):
            for l3 in l2.get("layer3", []):
                if isinstance(l3, dict):
                    code = l3.get("code")
                    if code:
                        codes.add(code)
                elif isinstance(l3, str):
                    codes.add(l3)
    return codes


# ─── validation ──────────────────────────────────────────────────────────────

def validate_file(path: Path, valid_categories: set[str] | None = None) -> FileResult:
    """Validate one event JSON file.

    Args:
        path: event file (JSON array of event dicts)
        valid_categories: if provided + non-empty, every event's `category`
            must be in the set. If None or empty, only type-checks run
            (backwards-compatible with pre-#422 behavior).

    Returns a FileResult with accumulated errors, warnings, and
    events_count.
    """
    result = FileResult()

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            result.errors.append(f"{path.name}: invalid JSON — {e}")
            return result

    if not isinstance(data, list):
        result.errors.append(
            f"{path.name}: root must be a JSON array, got {type(data).__name__}"
        )
        return result

    if len(data) < MIN_EVENTS_PER_COUNTRY:
        result.warnings.append(
            f"{path.name}: only {len(data)} events (min recommended: {MIN_EVENTS_PER_COUNTRY})"
        )

    recent_count = 0
    for i, event in enumerate(data):
        prefix = f"{path.name}[{i}]"

        if not isinstance(event, dict):
            result.errors.append(f"{prefix}: event must be a dict")
            continue

        # Required fields
        for key in ("year", "title", "description", "category"):
            if key not in event:
                result.errors.append(f"{prefix}: missing required field '{key}'")

        # Year
        year = event.get("year")
        if year is not None:
            if not isinstance(year, int):
                result.errors.append(
                    f"{prefix}: 'year' must be int, got {type(year).__name__}"
                )
            elif not (ALLOWED_YEAR_RANGE[0] <= year <= ALLOWED_YEAR_RANGE[1]):
                result.errors.append(f"{prefix}: year {year} outside {ALLOWED_YEAR_RANGE}")
            if isinstance(year, int) and 2020 <= year <= 2030:
                recent_count += 1

        # Title
        title = event.get("title")
        if title is not None:
            if not isinstance(title, str) or len(title) == 0:
                result.errors.append(f"{prefix}: 'title' must be non-empty string")
            elif len(title) > MAX_TITLE_LENGTH:
                result.warnings.append(
                    f"{prefix}: title exceeds {MAX_TITLE_LENGTH} chars ({len(title)})"
                )
            # #434: reject mojibake titles. Hard error (not warning) — these
            # are user-visible on country profile pages and a recovery
            # script ran today against 38 countries to clear ~830 occurrences.
            if isinstance(title, str) and MOJIBAKE_RE.search(title):
                result.errors.append(
                    f"{prefix}: title contains mojibake (UTF-8 → cp1252 → UTF-8 "
                    f"double-encoding). Run scripts/recover_mojibake.py or fix "
                    f"the curation source. Sample: {title[:80]!r}"
                )

        # Category
        category = event.get("category")
        if category is not None:
            if not isinstance(category, str):
                result.errors.append(f"{prefix}: 'category' must be string")
            # #422 Bug 2: taxonomy enforcement. Only enforce when a non-empty
            # set is supplied so tests + standalone invocations without the
            # taxonomy file still work.
            elif valid_categories and category not in valid_categories:
                result.errors.append(
                    f"{prefix}: category '{category}' is not in the canonical "
                    f"71-code taxonomy (see events/taxonomy_hierarchy.json)"
                )

        # Sources (optional but recommended)
        sources = event.get("sources")
        if sources is not None:
            if not isinstance(sources, list):
                result.errors.append(f"{prefix}: 'sources' must be a list")
            elif len(sources) == 0:
                result.warnings.append(f"{prefix}: 'sources' is empty")

        result.events_count += 1

    # Recency bias check
    if len(data) > 0 and recent_count / len(data) > MAX_RECENCY_RATIO:
        result.warnings.append(
            f"{path.name}: {recent_count}/{len(data)} events ({recent_count/len(data)*100:.0f}%) "
            f"are 2020-2030 — possible recency bias (threshold: {MAX_RECENCY_RATIO*100:.0f}%)"
        )

    return result


def validate_directory(
    events_dir: Path | None = None,
    taxonomy_path: Path | None = None,
) -> AggregateResult:
    """Validate every *.json file in events_dir. Returns an AggregateResult.

    Missing directory OR zero JSON files is reported as an error on the
    aggregate — caller decides how to exit.

    Defaults to the module-level EVENTS_DIR / TAXONOMY_PATH at CALL time,
    not at definition time, so tests can monkeypatch the constants.
    """
    if events_dir is None:
        events_dir = EVENTS_DIR
    if taxonomy_path is None:
        taxonomy_path = TAXONOMY_PATH

    agg = AggregateResult()

    if not events_dir.exists():
        agg.errors.append(f"events directory not found: {events_dir}")
        return agg

    json_files = sorted(events_dir.glob("*.json"))
    if not json_files:
        agg.errors.append(f"no JSON files found in {events_dir}")
        return agg

    valid_categories = load_valid_categories(taxonomy_path)

    for path in json_files:
        agg.merge(validate_file(path, valid_categories))

    return agg


def main() -> int:
    """CLI entry point. Returns exit code (0 ok, 1 errors found)."""
    agg = validate_directory()

    print(f"Validated {agg.total_files} files, {agg.total_events} events total.")

    if agg.warnings:
        print(f"\n{len(agg.warnings)} warnings:")
        for w in agg.warnings:
            print(f"  WARNING: {w}")

    if agg.errors:
        print(f"\n{len(agg.errors)} ERRORS:")
        for e in agg.errors:
            print(f"  ERROR: {e}")
        return 1

    print("\nAll files valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
