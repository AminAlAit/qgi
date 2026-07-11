#!/usr/bin/env python3
"""
remove_tfrt_duplicate.py — # THROWAWAY (per #373) — one-shot fix for the
duplicate `SP.DYN.TFRT.IN` row in `phase_2_indicators` of
`indicators/control-surface.xlsx`.

The schema test added in #494 step 3 caught this pre-existing duplicate:
- Row at numeric_id=15  is `process` (active, ingested)
- Row at numeric_id=165 is `hold` (inactive, redundant)

Both rows share the same id_string and name. The held duplicate was
likely a copy-paste artifact from a batch import. id_string uniqueness
is the contract that makes the indicator catalog joinable; this script
restores it.

Verified (qgi-data/scripts/) before running:
- `qgi-frontend/data/indexes.json` mirrors the XLSX duplicate (has
  entries at numeric_id=15 AND 165). The 165 entry is removed in the
  same PR for consistency.
- `recipe-confidence.json` has zero numeric_id references — safe.
- Methodology docs reference SP.DYN.TFRT.IN by id_string only.
- No production parquet in this repo carries numeric_id=165.

Run from qgi-data root:
  python scripts/remove_tfrt_duplicate.py

# THROWAWAY — single-run data fix. After commit, this script's role is
# documentation. No consumer should re-import or call it at runtime.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl


SCRIPT_DIR = Path(__file__).parent
XLSX_PATH = SCRIPT_DIR.parent / "indicators" / "control-surface.xlsx"
INDEXES_JSON = (
    SCRIPT_DIR.parent.parent / "qgi-frontend" / "data" / "indexes.json"
)

DUPLICATE_ID_STRING = "SP.DYN.TFRT.IN"
KEEP_NUMERIC_ID = 15
REMOVE_NUMERIC_ID = 165


def fix_xlsx() -> bool:
    """Remove the row in phase_2_indicators where numeric_id == 165
    AND id_string == SP.DYN.TFRT.IN (defensive AND-match — won't touch
    a future row that happens to land on 165 with a different id)."""
    if not XLSX_PATH.exists():
        print(f"[error] XLSX not found at {XLSX_PATH}", file=sys.stderr)
        return False

    print(f"[xlsx] loading {XLSX_PATH}")
    wb = openpyxl.load_workbook(XLSX_PATH)
    ws = wb["phase_2_indicators"]

    # Find the row to delete. Defensive: only delete if the row matches
    # BOTH the id_string and numeric_id we expect.
    target_row_idx: int | None = None
    for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if (
            row
            and row[0] == DUPLICATE_ID_STRING
            and row[1] == REMOVE_NUMERIC_ID
        ):
            target_row_idx = idx
            break

    if target_row_idx is None:
        print(
            f"[xlsx] no matching duplicate row found "
            f"(id_string={DUPLICATE_ID_STRING}, numeric_id={REMOVE_NUMERIC_ID}). "
            "Either already removed or never existed. Skipping."
        )
        return True

    print(f"[xlsx] deleting row {target_row_idx} (numeric_id={REMOVE_NUMERIC_ID})")
    ws.delete_rows(target_row_idx, 1)

    # Sanity check after delete: only one SP.DYN.TFRT.IN row should
    # remain, with numeric_id=15.
    survivors = [
        row for row in ws.iter_rows(min_row=2, values_only=True)
        if row and row[0] == DUPLICATE_ID_STRING
    ]
    if len(survivors) != 1:
        print(
            f"[xlsx] post-delete sanity check failed: "
            f"{len(survivors)} SP.DYN.TFRT.IN rows remain "
            f"(expected exactly 1 with numeric_id={KEEP_NUMERIC_ID})",
            file=sys.stderr,
        )
        return False
    surviving_id = int(survivors[0][1])
    if surviving_id != KEEP_NUMERIC_ID:
        print(
            f"[xlsx] post-delete sanity check failed: "
            f"surviving row has numeric_id={surviving_id} "
            f"(expected {KEEP_NUMERIC_ID})",
            file=sys.stderr,
        )
        return False

    wb.save(XLSX_PATH)
    print(f"[xlsx] saved {XLSX_PATH}")
    return True


def fix_indexes_json() -> bool:
    """Remove the entry in qgi-frontend/data/indexes.json where
    numeric_id == 165 AND id == SP.DYN.TFRT.IN."""
    if not INDEXES_JSON.exists():
        print(
            f"[json] indexes.json not found at {INDEXES_JSON} "
            "— qgi-frontend may not be cloned alongside qgi-data; "
            "skipping. Apply the fix manually if/when it is.",
            file=sys.stderr,
        )
        return True  # not a hard failure; XLSX fix is the primary change

    print(f"[json] loading {INDEXES_JSON}")
    data = json.loads(INDEXES_JSON.read_text(encoding="utf-8"))

    target_indexes: list[int] = [
        i
        for i, entry in enumerate(data)
        if entry.get("id") == DUPLICATE_ID_STRING
        and entry.get("numeric_id") == REMOVE_NUMERIC_ID
    ]
    if not target_indexes:
        print(
            f"[json] no matching duplicate entry found "
            f"(id={DUPLICATE_ID_STRING}, numeric_id={REMOVE_NUMERIC_ID}). "
            "Either already removed or never existed. Skipping."
        )
        return True

    if len(target_indexes) > 1:
        print(
            f"[json] unexpected: found {len(target_indexes)} matching entries — "
            "aborting to avoid silent over-deletion. Investigate manually.",
            file=sys.stderr,
        )
        return False

    print(
        f"[json] deleting entry at index {target_indexes[0]} "
        f"(numeric_id={REMOVE_NUMERIC_ID})"
    )
    data.pop(target_indexes[0])

    # Sanity check: exactly one SP.DYN.TFRT.IN entry remains, with
    # numeric_id=15.
    survivors = [e for e in data if e.get("id") == DUPLICATE_ID_STRING]
    if len(survivors) != 1:
        print(
            f"[json] post-delete sanity check failed: "
            f"{len(survivors)} SP.DYN.TFRT.IN entries remain "
            f"(expected exactly 1 with numeric_id={KEEP_NUMERIC_ID})",
            file=sys.stderr,
        )
        return False
    if survivors[0].get("numeric_id") != KEEP_NUMERIC_ID:
        print(
            f"[json] post-delete sanity check failed: "
            f"surviving entry has numeric_id={survivors[0].get('numeric_id')} "
            f"(expected {KEEP_NUMERIC_ID})",
            file=sys.stderr,
        )
        return False

    # Write as LF-only bytes (newline="" + binary write). On Windows,
    # Path.write_text() defaults to writing CRLF which would whole-file
    # rewrite the diff against the LF-original — silently exploding
    # the PR diff to thousands of lines.
    body = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    INDEXES_JSON.write_bytes(body)
    print(f"[json] saved {INDEXES_JSON} (LF line endings)")
    return True


def main() -> int:
    print("=" * 64)
    print("Remove SP.DYN.TFRT.IN duplicate (numeric_id=165, status=hold)")
    print("=" * 64)
    if not fix_xlsx():
        return 1
    if not fix_indexes_json():
        return 1
    print()
    print("[done] duplicate removed. Run the schema test to confirm:")
    print("       cd qgi-data && python -m pytest tests/test_control_surface_schema.py -v")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
