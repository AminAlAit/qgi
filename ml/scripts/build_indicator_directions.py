"""
build_indicator_directions.py — generator for indicator-directions.json.

Parses the two cross-Opus working drafts (cascade-side + ML-side) and
emits the canonical {api_code -> direction} JSON that
validate_weight_matrix.py v4 consumes in arms A and B (signed scoring).

Schema (matches load_direction_annotations contract):
  {"schema_version": N,
   "generated": "ISO 8601 UTC",
   "directions": [
     {"api_code": "v2x_libdem", "direction": +1, "tag": "[lit-only]",
      "justification": "first ~250 chars from working draft", "source": "cascade"},
     ...
   ]}

Inputs:
  - qgi-docs/internal/ops/cascade-track/catalog-direction-annotation-cascade-side.md
  - qgi-docs/internal/ops/ml-track/catalog-direction-annotation-ml-side.md

Output:
  - qgi-data/reference/indicator-directions.json

Conflict resolution policy (per Lane B sector split + R2):
  If the same api_code appears in both files with different directions,
  cascade wins by default (cascade owns macro/economic + governance per
  the 2026-05-10 sector split). If cascade has direction:0 and ML has a
  non-zero direction with the same api_code, the api_code is flagged as
  a Majles candidate and emitted with cascade's direction:0 — the
  literature default holds per R1.

Determinism (T3 from PR #47 strict review):
  Same input MDs → byte-identical output JSON when `--frozen-timestamp`
  or the SOURCE_DATE_EPOCH env var is set. Without those, only the
  top-level `generated` field varies between runs.
  Sorted by api_code throughout; no wall-clock fields in `directions[]`
  rows.

Usage:
  python qgi-ml/scripts/build_indicator_directions.py
  python qgi-ml/scripts/build_indicator_directions.py --dry-run
  python qgi-ml/scripts/build_indicator_directions.py --frozen-timestamp 2026-05-11T00:00:00Z
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parents[2]

CASCADE_DRAFT = (
    ROOT / "qgi-docs" / "internal" / "ops" / "cascade-track"
    / "catalog-direction-annotation-cascade-side.md"
)
ML_DRAFT = (
    ROOT / "qgi-docs" / "internal" / "ops" / "ml-track"
    / "catalog-direction-annotation-ml-side.md"
)
OUTPUT_JSON = ROOT / "qgi-data" / "reference" / "indicator-directions.json"

SCHEMA_VERSION = 1

# Indicator-cell regex (applied to column 1 of a Markdown table row).
# Three accepted shapes inside the `**...**` bold marker at the start
# of the cell:
#   1. `**WB-NN API.CODE** (Name, range)` — catalog code + space + api_code
#   2. `**API.CODE** (Name, range)`       — bare api_code (no catalog prefix)
#   3. `**FA-NN** (Name)`                 — catalog code IS the api_code (T5: bare-catalog shape)
# Cascade uses (1) for V-Dem; (2) for WGI (`**CC.EST** ...`).
# ML uses (1) for WB-NN coded (e.g. `**WB-03 SM.POP.REFG.OR**`); (2) for
# bare api codes (e.g. `**SE.ADT.LITR.ZS**`). Shape (3) is theoretical
# today but documented for forward-compat — if any draft ever uses `FA-01`
# as the api_code itself (no separate token), the second group falls back
# to the catalog_code's value.
#
# Catalog-code: [A-Z]{2,3}-[A-Z0-9P]+  (e.g., VD-01, WB-P5, FA-01)
# API code: any token of [A-Za-z0-9_.] characters
INDICATOR_CELL_RE = re.compile(
    r"^\s*\*\*"
    # optional catalog code + space (group 1; may be None for shape 2)
    r"(?:([A-Z]{2,3}-[A-Z0-9P]+)(?:\s+([A-Za-z0-9_.]+))?|([A-Za-z0-9_.]+))"
    r"\*\*"
)

# Direction-cell regex: `**±1/0**` inside column 2.
DIRECTION_CELL_RE = re.compile(r"\*\*([+\-]?[01])\*\*")


def _normalize_tag(raw_tag: str) -> str:
    """Strip bracket/backtick decoration from a tag column value.

    Three cases, all returning a plain-string tag safe to embed in JSON:
      1. Cascade backtick+bracket pattern (e.g. `` `[lit-only]` ``)
         → return `[lit-only]` (inner-bracketed string, no backticks)
      2. Bare-backtick pattern (e.g. `` `something` ``)
         → return `something` (T6: strip standalone backticks too)
      3. Bare free text (ML's tags like "High confidence (...)")
         → return unchanged

    T6 strict review (PR #47): previously only case 1 stripped
    decoration; case 2 silently returned the input with backticks
    preserved, contradicting the docstring. Now both cases strip.
    """
    t = raw_tag.strip().rstrip("|").strip()
    # Case 1: backtick + bracket
    m = re.match(r"^`\[([^\]]+)\]`$", t)
    if m:
        return f"[{m.group(1)}]"
    # Case 2: bare backticks (no brackets) — strip them, return inner text
    m = re.match(r"^`([^`]+)`$", t)
    if m:
        return m.group(1)
    # Case 3: free text — return unchanged
    return t


def _split_table_row(line: str) -> list[str] | None:
    """Split a Markdown table row into its column cells.

    Returns a list of column-text strings (leading + trailing empties
    stripped), OR None if the line is not a table row (no `|`, header
    separator line, etc.).

    T1 strict review (PR #47): replaces the previous single-regex
    column-pipe parser which silently truncated justifications that
    contained `|` characters. This split-based parser respects
    Markdown's `\\|` escape: an escaped pipe stays in its cell rather
    than splitting it.

    Note: simple `line.split("|")` would mis-handle `\\|` (backslash-
    escaped pipes). Markdown table syntax uses `\\|` to put a literal
    `|` inside a cell. We replace `\\|` with a sentinel before splitting,
    then restore.
    """
    if "|" not in line:
        return None
    SENTINEL = "\x00PIPE\x00"
    # Replace escaped pipes with sentinel, split, restore.
    parts = line.replace(r"\|", SENTINEL).split("|")
    parts = [p.replace(SENTINEL, "|") for p in parts]
    # Strip the leading + trailing empty cells produced by `|...|` framing
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return parts


def parse_draft(path: Path, source_label: str) -> list[dict]:
    """Extract direction-annotation rows from a working-draft markdown.

    Returns a list of {api_code, direction, tag, justification, source}.
    Rows that don't match the canonical pattern are skipped silently
    (e.g., header/divider/explanatory rows). Caller can compare count
    against the draft's claimed-indicator-count to detect drift.

    T1 fix (PR #47 strict review): switched from single-shot regex
    to column-split parsing so the justification cell can safely
    contain `|` characters (via Markdown's `\\|` escape).
    """
    if not path.exists():
        print(f"[WARN] working draft not found: {path}", file=sys.stderr)
        return []

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = _split_table_row(line)
        # Expect at least 4 columns: indicator | direction | justification | tag
        if parts is None or len(parts) < 4:
            continue
        # Column 0: indicator cell. Apply the regex, accept any of the 3 shapes.
        ind_match = INDICATOR_CELL_RE.match(parts[0])
        if not ind_match:
            continue
        # Three capture groups: (catalog_code_with_api, api_code_after_catalog, bare_api_code)
        # T5 forward-compat: if the catalog-only shape matched (catalog_code present
        # but no second token), use catalog_code as the api_code.
        g_catalog, g_api_after_catalog, g_bare_api = ind_match.groups()
        if g_api_after_catalog:
            catalog_code = g_catalog
            api_code = g_api_after_catalog
        elif g_catalog:  # catalog-only shape (T5 future-form)
            catalog_code = g_catalog
            api_code = g_catalog
        else:  # bare-api shape
            catalog_code = None
            api_code = g_bare_api
        # Column 1: direction
        dir_match = DIRECTION_CELL_RE.search(parts[1])
        if not dir_match:
            continue
        sign = dir_match.group(1)
        # Column 2: justification (anything inside the cell, pipes preserved)
        justification = parts[2]
        # Column 3: tag
        tag = parts[3]
        # Normalize "+1"/"−1"/"0" → int. Note: ROW_RE matches "1", "-1", "+1"
        # via the [+\-]?[01] pattern. Map to int directly.
        if sign == "0":
            direction = 0
        elif sign == "1" or sign == "+1":
            direction = 1
        elif sign == "-1":
            direction = -1
        else:
            # Should not reach here given the regex, but defensive.
            print(f"[WARN] unparseable sign {sign!r} for {api_code}; skipped",
                  file=sys.stderr)
            continue
        # Truncate justification to a manageable size (full prose lives in
        # the working drafts; the JSON is for machine consumption + audit
        # trail).
        just = justification.strip()
        if len(just) > 300:
            just = just[:297] + "..."
        rows.append({
            "api_code": api_code,
            "direction": direction,
            "tag": _normalize_tag(tag),
            "justification": just,
            "source": source_label,
            "catalog_code": catalog_code,  # may be None for bare-pattern rows
        })
    return rows


def merge_with_conflict_resolution(
    cascade_rows: list[dict], ml_rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Merge cascade + ML rows; cascade wins on conflict per Lane B R2.

    Returns (merged_rows, conflicts) where:
      - merged_rows: deduped + sorted by api_code; ready for JSON emit
      - conflicts: list of {api_code, cascade_direction, ml_direction,
                            resolved_to, reason} for the audit trail

    Conflict resolution:
      1. Same api_code in both files with same direction → emit once
         (source="cascade" wins, ML row dropped)
      2. Same api_code with DIFFERENT directions → cascade wins; emit
         cascade's direction; flag in conflicts list with reason
      3. Cascade has direction:0 + ML has non-zero (the v2cseeorgs
         pattern) → cascade's direction:0 wins per R1 mixed-lit
         fallback; flag in conflicts list as a Majles candidate
    """
    by_api: dict[str, dict] = {}
    conflicts: list[dict] = []

    # Insert cascade first (always wins on conflict)
    for row in cascade_rows:
        by_api[row["api_code"]] = row

    # Then ML — log appropriately if api_code already present from cascade.
    # T4 strict review fix: split overlaps into two semantic buckets:
    #  - sign_conflicts: cascade ±1 vs ML ∓1 (R2: cascade wins)
    #  - deferral_overrides: cascade 0 (Majles-deferred) vs ML ±1
    #    (R1: cascade's mixed-lit fallback wins; ML's non-zero is the
    #    unresolved evidence, not "wrong")
    # Conflating these in one `conflicts` list mislabeled R1 deferrals
    # as R2 conflicts and made the audit trail harder to read at Majles.
    for row in ml_rows:
        api = row["api_code"]
        if api in by_api:
            c_row = by_api[api]
            if c_row["direction"] == row["direction"]:
                # Same sign — cascade-source win is silent
                continue
            entry = {
                "api_code": api,
                "cascade_direction": c_row["direction"],
                "cascade_tag": c_row["tag"],
                "ml_direction": row["direction"],
                "ml_tag": row["tag"],
                "resolved_to": c_row["direction"],
                "resolved_source": "cascade",
            }
            if c_row["direction"] == 0 and row["direction"] != 0:
                # R1 deferral: cascade explicitly chose direction:0 because
                # the literature is mixed. ML's non-zero is not "wrong" —
                # it's the unresolved evidence cascade is deferring on.
                entry["conflict_type"] = "deferral"
                entry["reason"] = (
                    "Lane B R1 (mixed-lit fallback): cascade explicitly "
                    "marked direction:0 (Majles-deferred); ML's non-zero "
                    "sign is unresolved evidence, not a contradiction. "
                    "Majles re-decides when ML cites conflicting external "
                    "literature."
                )
            else:
                # R2 sign conflict: cascade ±1 vs ML ∓1 (genuine contradiction)
                entry["conflict_type"] = "sign"
                entry["reason"] = (
                    "Lane B R2: cascade's literature default wins on "
                    "cross-Opus sign conflicts. ML-Opus may escalate to "
                    "Majles with conflicting external evidence; until then, "
                    "cascade's sign holds."
                )
            conflicts.append(entry)
            continue
        by_api[api] = row

    merged = sorted(by_api.values(), key=lambda r: r["api_code"])
    return merged, conflicts


def _resolve_generated_timestamp(frozen: str | None = None) -> str:
    """Resolve the value to put in the output JSON's `generated` field.

    Precedence (T3 PR #47 strict review):
      1. Explicit --frozen-timestamp CLI arg (if set)
      2. SOURCE_DATE_EPOCH env var (Unix-timestamp seconds since epoch;
         standard reproducible-builds convention from reproducible-builds.org)
      3. Wall-clock UTC now (default, non-deterministic across runs)
    """
    if frozen:
        return frozen
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    if sde:
        try:
            return datetime.fromtimestamp(int(sde), tz=timezone.utc).isoformat()
        except (ValueError, OSError) as e:
            print(f"[WARN] SOURCE_DATE_EPOCH={sde!r} not parseable as int: {e}; "
                  f"falling back to wall clock", file=sys.stderr)
    return datetime.now(timezone.utc).isoformat()


def emit_json(
    rows: list[dict], conflicts: list[dict], cascade_n: int, ml_n: int,
    frozen_timestamp: str | None = None,
) -> dict:
    """Build the output JSON object matching load_direction_annotations()
    expected schema.

    T3 PR #47 strict review: the `generated` field uses --frozen-timestamp
    or SOURCE_DATE_EPOCH if available; otherwise wall-clock UTC.
    """
    # Strip the `catalog_code` field from emitted rows — it's a working
    # provenance breadcrumb but not part of the loader contract.
    directions = [
        {
            "api_code": r["api_code"],
            "direction": r["direction"],
            "tag": r["tag"],
            "justification": r["justification"],
            "source": r["source"],
        }
        for r in rows
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated": _resolve_generated_timestamp(frozen_timestamp),
        "method": (
            "Parses cascade-side + ML-side working drafts at "
            "qgi-docs/internal/ops/{cascade,ml}-track/"
            "catalog-direction-annotation-{cascade,ml}-side.md and emits "
            "{api_code -> direction} for the indicators with literature-"
            "defensible signs. Cascade wins on sign conflicts per "
            "Lane B R1+R2 (cross-opus-chat.md 2026-05-10)."
        ),
        "source_drafts": {
            # POSIX-forward-slash paths for cross-platform diff-stability:
            # without .as_posix() the JSON has Windows backslashes on
            # Windows runs and forward slashes on Linux CI, which produces
            # noisy diffs every regeneration (T2 strict review fix).
            "cascade": CASCADE_DRAFT.relative_to(ROOT).as_posix(),
            "ml": ML_DRAFT.relative_to(ROOT).as_posix(),
        },
        "row_counts": {
            "cascade_rows_parsed": cascade_n,
            "ml_rows_parsed": ml_n,
            "merged_rows": len(directions),
            "conflicts_resolved": len(conflicts),
        },
        "conflicts": conflicts,
        "directions": directions,
    }


AUDIT_JSON_PATH = ROOT / "qgi-data" / "reference" / "indicator-stationarity-audit-v2.json"


def _print_coverage_delta(merged: list[dict]) -> None:
    """T7 PR #47 strict review: print coverage delta vs the audited
    109-indicator set. Helps operators sanity-check that drift between
    the working drafts and the audit set is intentional before
    committing a regenerated artifact.
    """
    if not AUDIT_JSON_PATH.exists():
        print(f"    [coverage] audit JSON not found at {AUDIT_JSON_PATH.relative_to(ROOT)}; "
              f"coverage delta skipped")
        return
    audit = json.loads(AUDIT_JSON_PATH.read_text(encoding="utf-8"))
    audit_codes = set(audit.get("results", {}).keys())
    merged_codes = {r["api_code"] for r in merged}
    covered = audit_codes & merged_codes
    missing_in_directions = audit_codes - merged_codes
    extra_in_directions = merged_codes - audit_codes
    print(f"    [coverage] audited={len(audit_codes)} "
          f"in_directions={len(merged_codes)} "
          f"covered={len(covered)} "
          f"audited_but_missing={len(missing_in_directions)} "
          f"in_directions_but_not_audited={len(extra_in_directions)}")
    if missing_in_directions:
        ordered = sorted(missing_in_directions)
        sample = ", ".join(ordered[:5])
        if len(ordered) > 5:
            sample += f", ... +{len(ordered) - 5} more"
        print(f"    [coverage] audited_but_missing: {sample}")


def main(dry_run: bool = False, frozen_timestamp: str | None = None) -> int:
    print(f"[1] Parsing cascade draft: {CASCADE_DRAFT.relative_to(ROOT).as_posix()}")
    cascade_rows = parse_draft(CASCADE_DRAFT, source_label="cascade")
    print(f"    parsed {len(cascade_rows)} rows")

    print(f"[2] Parsing ML draft: {ML_DRAFT.relative_to(ROOT).as_posix()}")
    ml_rows = parse_draft(ML_DRAFT, source_label="ml-opus")
    print(f"    parsed {len(ml_rows)} rows")

    print("[3] Merging with Lane B conflict resolution (cascade wins)")
    merged, conflicts = merge_with_conflict_resolution(cascade_rows, ml_rows)
    print(f"    merged {len(merged)} rows ({len(conflicts)} conflicts resolved)")

    if conflicts:
        print("\n[!] Sign conflicts (cascade default wins):")
        for c in conflicts:
            print(f"    {c['api_code']}: cascade={c['cascade_direction']:+d} "
                  f"({c['cascade_tag']}); ml={c['ml_direction']:+d} "
                  f"({c['ml_tag']}) -> resolved {c['resolved_to']:+d}")

    # Sanity: every row has a direction in {-1, 0, +1}; non-empty api_code
    for r in merged:
        assert r["direction"] in (-1, 0, 1), f"bad direction in {r}"
        assert r["api_code"], f"empty api_code in {r}"

    # T7: coverage delta vs the 109-indicator audit set
    _print_coverage_delta(merged)

    payload = emit_json(
        merged, conflicts, len(cascade_rows), len(ml_rows),
        frozen_timestamp=frozen_timestamp,
    )

    if dry_run:
        print(f"\n[DRY-RUN] would write {len(merged)} directions to "
              f"{OUTPUT_JSON.relative_to(ROOT).as_posix()}")
        print(json.dumps(
            {"directions": payload["directions"][:3], "total": len(merged)},
            indent=2,
        ))
        return 0

    print(f"\n[4] Writing {OUTPUT_JSON.relative_to(ROOT).as_posix()}")
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"    wrote {len(merged)} directions "
          f"({sum(1 for r in merged if r['direction'] == 1)} +1, "
          f"{sum(1 for r in merged if r['direction'] == -1)} -1, "
          f"{sum(1 for r in merged if r['direction'] == 0)} direction:0)")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="parse + merge but do not write the JSON")
    p.add_argument("--frozen-timestamp", default=None, metavar="ISO_8601",
                   help="Pin the output `generated` field to this ISO-8601 "
                        "timestamp (T3 PR #47 strict review). For "
                        "reproducible builds. Overrides SOURCE_DATE_EPOCH.")
    args = p.parse_args()
    sys.exit(main(dry_run=args.dry_run, frozen_timestamp=args.frozen_timestamp))
