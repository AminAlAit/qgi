#!/usr/bin/env python3
"""
Aggregate Event Verifications
=============================

Reads every ``qgi-data/events/verification/*.json`` file, computes
per-country + cross-country statistics, and emits both a plain-text
summary to stdout and (optionally) a Markdown report.

Input file shape (one object per curated event, written by the QA
verification agents):
    {"year": 1952, "title": "...", "status": "VERIFIED" | "UNVERIFIED" | "FALSE",
     "source": "https://...", "note": "..."}

Usage:
    python qgi-ml/scripts/aggregate_event_verifications.py
    python qgi-ml/scripts/aggregate_event_verifications.py --md docs/specs/internal/event-verification-report.md
    python qgi-ml/scripts/aggregate_event_verifications.py --sort-by false-rate --limit 20

Notes:
- Year-off errors are the dominant failure mode across the verified
  corpus (~90% of FALSE findings as of April 2026). The script surfaces
  these explicitly via a ``year_off`` classification heuristic on the
  ``note`` field.
- No external dependencies (stdlib only). Works on the Windows + Python
  3.13 environment Amin uses.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_VERIFICATION_DIR = REPO_ROOT / "qgi-data" / "events" / "verification"
DEFAULT_CURATED_DIR = REPO_ROOT / "qgi-data" / "events" / "curated"

# --------------------------------------------------------------------- #
# Heuristics                                                            #
# --------------------------------------------------------------------- #

# A FALSE note is a "year off" error if it contains any of these cues
# (case-insensitive). The QA agents are consistent in how they
# phrase these, so simple substring matching is good enough.
YEAR_OFF_CUES = [
    "year is wrong",
    "year error",
    "year off",
    "year-off",
    "off by",
    "wrong year",
    "incorrect year",
    "not 19",  # e.g. "not 1952, but 1956"
    "not 20",  # e.g. "not 2006, but 2007"
    "actually 19",
    "actually 20",
]

# --------------------------------------------------------------------- #
# Data classes                                                          #
# --------------------------------------------------------------------- #


@dataclass
class CountryStats:
    slug: str
    verified: int = 0
    unverified: int = 0
    false: int = 0
    year_off_false: int = 0
    false_events: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.verified + self.unverified + self.false

    @property
    def verified_pct(self) -> float:
        return (self.verified / self.total * 100) if self.total else 0.0

    @property
    def false_pct(self) -> float:
        return (self.false / self.total * 100) if self.total else 0.0

    @property
    def unverified_pct(self) -> float:
        return (self.unverified / self.total * 100) if self.total else 0.0


# --------------------------------------------------------------------- #
# Classification                                                        #
# --------------------------------------------------------------------- #


def is_year_off(note: str) -> bool:
    lower = (note or "").lower()
    return any(cue in lower for cue in YEAR_OFF_CUES)


def classify_file(path: Path) -> CountryStats:
    """Parse one verification JSON. Accepts two wire formats:

    1. Flat array of event verifications (used by the retry-wave agents):
       ``[{"year": ..., "status": "VERIFIED", ...}, ...]``

    2. Wrapped object with metadata + ``results`` array (used by the
       original 5-pair parallel agents):
       ``{"country": "X", "summary": {...}, "results": [ ... ]}``

    Both shapes yield the same ``CountryStats`` output.
    """
    slug = path.stem
    stats = CountryStats(slug=slug)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] cannot parse {path.name}: {exc}", file=sys.stderr)
        return stats

    # Normalize to a flat event list. Agents have used at least three
    # wrapper shapes; try the common keys in order.
    events = None
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        for key in ("results", "events", "verifications", "items"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                events = candidate
                break
    if events is None:
        print(f"[warn] {path.name} has unknown shape; skipping", file=sys.stderr)
        return stats

    for event in events:
        if not isinstance(event, dict):
            continue
        status = (event.get("status") or "").strip().upper()
        if status == "VERIFIED":
            stats.verified += 1
        elif status == "UNVERIFIED":
            stats.unverified += 1
        elif status == "FALSE":
            stats.false += 1
            note = event.get("note") or ""
            if is_year_off(note):
                stats.year_off_false += 1
            stats.false_events.append(
                {
                    "year": event.get("year"),
                    "title": event.get("title"),
                    "note": note,
                    "year_off": is_year_off(note),
                }
            )
    return stats


# --------------------------------------------------------------------- #
# Reporting                                                             #
# --------------------------------------------------------------------- #


def render_plain_table(rows: list[CountryStats]) -> str:
    headers = ("Country", "Total", "Verified", "Unverif.", "False", "False %", "Year-off")
    widths = [28, 6, 8, 8, 6, 8, 8]
    lines = []
    sep = "  ".join("-" * w for w in widths)
    lines.append(sep)
    lines.append("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    lines.append(sep)
    for s in rows:
        lines.append(
            "  ".join(
                [
                    s.slug.ljust(widths[0]),
                    str(s.total).rjust(widths[1]),
                    str(s.verified).rjust(widths[2]),
                    str(s.unverified).rjust(widths[3]),
                    str(s.false).rjust(widths[4]),
                    f"{s.false_pct:5.1f}%".rjust(widths[5]),
                    str(s.year_off_false).rjust(widths[6]),
                ]
            )
        )
    lines.append(sep)
    return "\n".join(lines)


def render_markdown(rows: list[CountryStats], totals: CountryStats, coverage: tuple[int, int]) -> str:
    verified_total = totals.verified
    unverified_total = totals.unverified
    false_total = totals.false
    grand_total = totals.total
    year_off_total = sum(r.year_off_false for r in rows)
    done_count, curated_count = coverage

    # Build the per-country table (sorted by false_pct descending).
    lines = []
    lines.append("# QGI Event Verification — Cross-Country Report")
    lines.append("")
    lines.append(
        f"Coverage: **{done_count} of {curated_count}** curated countries verified "
        f"({done_count / curated_count * 100:.1f}%)."
    )
    lines.append("")
    lines.append(
        f"Rolled up across {done_count} countries: **{verified_total} VERIFIED**, "
        f"**{unverified_total} UNVERIFIED**, **{false_total} FALSE** "
        f"({false_total / grand_total * 100:.2f}% error rate). "
        f"**{year_off_total}** of the {false_total} FALSE events "
        f"({year_off_total / false_total * 100:.1f}%) are year-off errors."
    )
    lines.append("")
    lines.append("## Per-country table (sorted by FALSE rate, desc)")
    lines.append("")
    lines.append("| Country | Total | Verified | Unverified | False | False % | Year-off |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for s in rows:
        lines.append(
            f"| {s.slug} | {s.total} | {s.verified} | {s.unverified} | {s.false} | "
            f"{s.false_pct:.1f}% | {s.year_off_false} |"
        )
    lines.append("")

    # FALSE events detail
    lines.append("## FALSE events (grouped by country)")
    lines.append("")
    for s in rows:
        if not s.false_events:
            continue
        lines.append(f"### {s.slug} ({s.false} FALSE)")
        lines.append("")
        for ev in s.false_events:
            marker = "[year-off]" if ev["year_off"] else "[fact-error]"
            lines.append(f"- **{ev['year']} — {ev['title']}** {marker}")
            if ev["note"]:
                lines.append(f"  - {ev['note']}")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------- #
# Main                                                                  #
# --------------------------------------------------------------------- #


def collect(verification_dir: Path) -> list[CountryStats]:
    files = sorted(verification_dir.glob("*.json"))
    return [classify_file(p) for p in files if p.is_file()]


def sum_totals(rows: Iterable[CountryStats]) -> CountryStats:
    total = CountryStats(slug="TOTAL")
    for r in rows:
        total.verified += r.verified
        total.unverified += r.unverified
        total.false += r.false
        total.year_off_false += r.year_off_false
    return total


def count_curated(curated_dir: Path) -> int:
    if not curated_dir.is_dir():
        return 0
    return len(list(curated_dir.glob("*.json")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--verification-dir",
        type=Path,
        default=DEFAULT_VERIFICATION_DIR,
        help="Directory containing verification JSONs (default: %(default)s)",
    )
    parser.add_argument(
        "--curated-dir",
        type=Path,
        default=DEFAULT_CURATED_DIR,
        help="Directory containing curated JSONs (default: %(default)s)",
    )
    parser.add_argument(
        "--sort-by",
        choices=["slug", "false-rate", "false-count", "total"],
        default="false-rate",
        help="Sort per-country table (default: %(default)s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Show only the top-N rows in the plain table (does not affect markdown)",
    )
    parser.add_argument(
        "--md",
        type=Path,
        default=None,
        help="If set, write a Markdown report to this path",
    )
    args = parser.parse_args()

    if not args.verification_dir.is_dir():
        print(f"[error] verification dir not found: {args.verification_dir}", file=sys.stderr)
        return 2

    rows = collect(args.verification_dir)
    if not rows:
        print("[error] no verification files found", file=sys.stderr)
        return 2

    # Sort
    sort_key = {
        "slug": lambda r: r.slug,
        "false-rate": lambda r: (-r.false_pct, -r.total),
        "false-count": lambda r: (-r.false, -r.total),
        "total": lambda r: -r.total,
    }[args.sort_by]
    rows.sort(key=sort_key)

    totals = sum_totals(rows)
    curated_count = count_curated(args.curated_dir)

    display = rows[: args.limit] if args.limit else rows

    # Plain-text output
    print(f"Verification coverage: {len(rows)} of {curated_count} curated countries")
    print(
        f"Grand totals: {totals.total} events | "
        f"{totals.verified} VERIFIED ({totals.verified / totals.total * 100:.1f}%) | "
        f"{totals.unverified} UNVERIFIED ({totals.unverified / totals.total * 100:.1f}%) | "
        f"{totals.false} FALSE ({totals.false / totals.total * 100:.1f}%) | "
        f"{totals.year_off_false} year-off "
        f"({totals.year_off_false / max(totals.false, 1) * 100:.1f}% of FALSE)"
    )
    print()
    print(render_plain_table(display))

    # Markdown output
    if args.md:
        # Markdown report always uses full, sorted-by-false-rate view.
        md_rows = sorted(rows, key=lambda r: (-r.false_pct, -r.total))
        md = render_markdown(md_rows, totals, (len(rows), curated_count))
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(md, encoding="utf-8")
        print(f"\n[ok] wrote Markdown report to {args.md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
