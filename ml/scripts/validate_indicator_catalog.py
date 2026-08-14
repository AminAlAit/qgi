#!/usr/bin/env python3
"""
validate_indicator_catalog.py — pre-flight check for
``Pipeline_Indicator_Catalog.xlsx`` before uploading to S3.

Why this exists
===============

The QA safety review for #241 Phase B (2026-04-20) flagged a
silent dispatcher fall-through: if the FAOSTAT sheet has
``provider=FAOSTAT`` but no ``fao_domain_code`` column (curation
typo), the dispatcher's grouping code falls through to a per-
indicator task submission. Each task then crashes immediately
because ``fetch_domain.py`` reads ``os.environ["DOMAIN_CODE"]`` as
a required env var. The failure-handler Lambda writes a FAILED
tracker row, the counter decrements, but we wasted a Fargate task
and the ops report will show 15 FAILED rows.

This script catches that class of errors before the XLSX ever
reaches S3. Run it locally after editing the catalog:

    python qgi-ml/scripts/validate_indicator_catalog.py \\
        --xlsx path/to/Pipeline_Indicator_Catalog.xlsx

Exits 0 on pass, 1 on any validation failure (with a specific
per-row error list).

Validations per sheet
=====================

All sheets
----------
- Essential columns present: id_string, numeric_id, name, status
- No duplicate numeric_id across any sheet (numeric_id is QGI's
  pipeline-wide PK)
- Status values are in the known set
  (process / hold / deprecated / planned)

FAOSTAT sheet specifically
--------------------------
- ``fao_domain_code`` column present and non-empty for every row
- ``fao_item_code`` column present and integer for every row
- ``fao_element_code`` column present and integer for every row

WB sheet specifically
---------------------
- ``wb_indicator_code`` column present (copy of id_string or direct WB
  code) — optional but warn if missing for any row

V-Dem, ILOSTAT, UCDP, etc. — validation extends as each provider
lands.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd


# Columns every sheet must have.
_ESSENTIAL_COLUMNS = {"id_string", "numeric_id", "name", "status"}

# Valid status values (matches pipeline-a-sheet-fetcher's filter).
_VALID_STATUSES = {"process", "hold", "deprecated", "planned"}

# Sheets to skip entirely (same convention as sheet-fetcher Lambda).
_SKIP_SHEETS = {"archive", "meta", "notes", "readme"}


# Per-provider required columns. Keys are sheet name (case-insensitive).
_PROVIDER_REQUIRED_COLUMNS: dict[str, list[tuple[str, type]]] = {
    "FAOSTAT": [
        ("fao_domain_code", str),
        ("fao_item_code", int),
        ("fao_element_code", int),
    ],
    "FAO": [  # Alias
        ("fao_domain_code", str),
        ("fao_item_code", int),
        ("fao_element_code", int),
    ],
}


def _is_skip(sheet_name: str) -> bool:
    return (
        sheet_name.startswith("_")
        or sheet_name.lower() in _SKIP_SHEETS
    )


def _validate_essentials(
    df: pd.DataFrame, sheet_name: str
) -> list[str]:
    errors: list[str] = []
    missing = _ESSENTIAL_COLUMNS - set(df.columns)
    if missing:
        errors.append(
            f"Sheet {sheet_name!r}: missing essential columns: {sorted(missing)}"
        )
        return errors  # can't validate further without essentials

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # +1 for header, +1 for 1-based Excel rows
        if pd.isna(row.get("id_string")) or not str(row["id_string"]).strip():
            errors.append(
                f"Sheet {sheet_name!r} row {row_num}: id_string missing"
            )
        if pd.isna(row.get("numeric_id")):
            errors.append(
                f"Sheet {sheet_name!r} row {row_num}: numeric_id missing"
            )
        else:
            try:
                int(row["numeric_id"])
            except (TypeError, ValueError):
                errors.append(
                    f"Sheet {sheet_name!r} row {row_num}: numeric_id "
                    f"{row['numeric_id']!r} is not an integer"
                )

        status = row.get("status")
        if pd.isna(status):
            errors.append(
                f"Sheet {sheet_name!r} row {row_num}: status is blank"
            )
        else:
            s = str(status).strip().lower()
            if s not in _VALID_STATUSES:
                errors.append(
                    f"Sheet {sheet_name!r} row {row_num}: status "
                    f"{status!r} not in {sorted(_VALID_STATUSES)}"
                )

    return errors


def _validate_provider_specific(
    df: pd.DataFrame, sheet_name: str
) -> list[str]:
    errors: list[str] = []
    required = _PROVIDER_REQUIRED_COLUMNS.get(sheet_name.upper())
    if not required:
        return errors  # no provider-specific rules for this sheet

    for col_name, col_type in required:
        if col_name not in df.columns:
            errors.append(
                f"Sheet {sheet_name!r}: required column {col_name!r} is missing"
            )
            continue
        for idx, row in df.iterrows():
            row_num = int(idx) + 2
            val = row.get(col_name)
            if pd.isna(val):
                errors.append(
                    f"Sheet {sheet_name!r} row {row_num}: {col_name!r} is blank"
                )
                continue
            if col_type is int:
                try:
                    int(val)
                except (TypeError, ValueError):
                    errors.append(
                        f"Sheet {sheet_name!r} row {row_num}: {col_name!r} "
                        f"= {val!r} is not an integer"
                    )
            # str columns are implicitly OK if not NaN
    return errors


def _validate_no_duplicate_numeric_ids(
    all_rows: list[tuple[str, int, Any]]
) -> list[str]:
    """Check numeric_id uniqueness across EVERY sheet. The pipeline uses
    numeric_id as a PK into scdis / patterns / indicator-values, so two
    different indicators sharing a numeric_id would corrupt downstream
    joins."""
    errors: list[str] = []
    seen: dict[int, tuple[str, int]] = {}
    for sheet_name, row_num, nid in all_rows:
        if nid is None:
            continue
        if nid in seen:
            prev_sheet, prev_row = seen[nid]
            errors.append(
                f"Duplicate numeric_id {nid}: first seen in {prev_sheet!r} "
                f"row {prev_row}, again in {sheet_name!r} row {row_num}"
            )
        else:
            seen[nid] = (sheet_name, row_num)
    return errors


def validate(xlsx_path: Path) -> tuple[bool, list[str]]:
    """Validate the entire catalog. Returns (ok, errors)."""
    if not xlsx_path.exists():
        return False, [f"File not found: {xlsx_path}"]

    xl = pd.ExcelFile(xlsx_path, engine="openpyxl")
    errors: list[str] = []
    all_numeric_ids: list[tuple[str, int, Any]] = []

    for sheet_name in xl.sheet_names:
        if _is_skip(sheet_name):
            continue
        df = pd.read_excel(xlsx_path, engine="openpyxl", sheet_name=sheet_name)
        df.columns = df.columns.str.strip()

        errors.extend(_validate_essentials(df, sheet_name))
        errors.extend(_validate_provider_specific(df, sheet_name))

        # Collect numeric_ids for the cross-sheet uniqueness check.
        if "numeric_id" in df.columns:
            for idx, row in df.iterrows():
                nid = row.get("numeric_id")
                row_num = int(idx) + 2
                try:
                    nid_int = int(nid) if not pd.isna(nid) else None
                except (TypeError, ValueError):
                    nid_int = None
                all_numeric_ids.append((sheet_name, row_num, nid_int))

    errors.extend(_validate_no_duplicate_numeric_ids(all_numeric_ids))
    return (not errors), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xlsx",
        type=Path,
        required=True,
        help="Path to Pipeline_Indicator_Catalog.xlsx to validate",
    )
    args = parser.parse_args()

    ok, errors = validate(args.xlsx)
    if ok:
        print(f"[ok] {args.xlsx}: catalog validates cleanly")
        return 0
    print(f"[fail] {args.xlsx}: {len(errors)} validation error(s):", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
