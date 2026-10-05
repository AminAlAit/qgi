"""Append a per-vintage rank-history file to the cross-vintage append-only
chain.

Called from `.github/workflows/sync-te-fleet-vintage.yml`. Extracted to a
standalone file (rather than inlined as a bash heredoc) so:
  - The Python indentation isn't entangled with YAML block-scalar handling.
  - It can be unit-tested.
  - The same logic is reusable if a founder runs it locally to inspect a
    sync diff.

Inputs (env-vars or CLI):
  VINTAGE_SLUG / --slug    Path slug (e.g. "fleet-run-2-2026-08-15")
  --per-vintage PATH       Per-vintage rank-history.json
                           (default: data/te-fleet-run-<slug>/countries/country-rank-history.json)
  --cross PATH             Cross-vintage rank-history.json
                           (default: data/te-fleet-rank-history.json)

Behaviour:
  - If the per-vintage file is missing, exits 0 with a warning (no-op).
  - If the per-vintage file has no `vintage` field, exits non-zero
    (the bake guarantees the field; a missing field is a contract break).
  - If the cross-vintage file doesn't exist yet, the per-vintage rows
    seed it.
  - If a re-run brings rows for an already-present vintage, that vintage's
    rows are dropped and re-appended (idempotent re-run support).
  - Other vintages' rows always survive (append-only contract).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys


def append_rank_history(slug: str, per_vintage_path: pathlib.Path,
                        cross_path: pathlib.Path) -> int:
    """Returns exit code (0 = success, 0 with warning = noop, 2 = contract break)."""
    if not per_vintage_path.exists():
        # Workflow handles this as a warning, not a failure. Bake may have
        # skipped the rank-history emit on a stub run.
        print(f"::warning::No per-vintage rank-history at {per_vintage_path}; nothing to append")
        return 0

    new_doc = json.loads(per_vintage_path.read_text(encoding="utf-8"))
    new_rows = new_doc.get("rows", [])
    new_vintage = new_doc.get("vintage")
    if not new_vintage:
        print(f"::error::Per-vintage rank-history at {per_vintage_path} has no `vintage` field — contract break")
        return 2

    if cross_path.exists():
        cross_doc = json.loads(cross_path.read_text(encoding="utf-8"))
        existing_rows = cross_doc.get("rows", [])
        # Idempotency: drop any existing rows whose `vintage` equals
        # new_vintage so a re-run of the same SFN execution overwrites
        # cleanly. Cross-vintage rows for OTHER vintages survive.
        kept = [r for r in existing_rows if r.get("vintage") != new_vintage]
        dropped = len(existing_rows) - len(kept)
        if dropped:
            print(f"Dropped {dropped} existing rows for vintage={new_vintage}")
        merged_rows = kept + new_rows
    else:
        merged_rows = list(new_rows)

    n_vintages = len({r.get("vintage") for r in merged_rows if r.get("vintage")})

    out_doc = {
        "schema_note": (
            "Cross-vintage append-only. Re-running an existing vintage "
            "replaces its rows; rows from other vintages survive."
        ),
        "n_rows": len(merged_rows),
        "n_vintages": n_vintages,
        "rows": merged_rows,
    }
    cross_path.parent.mkdir(parents=True, exist_ok=True)
    cross_path.write_text(json.dumps(out_doc, indent=2), encoding="utf-8")
    print(f"Cross-vintage file: {len(merged_rows)} rows across {n_vintages} vintages "
          f"(slug={slug}, vintage={new_vintage})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", default=os.environ.get("VINTAGE_SLUG", ""),
                    help="Vintage slug. Defaults to $VINTAGE_SLUG.")
    ap.add_argument("--per-vintage", type=pathlib.Path, default=None,
                    help="Path to per-vintage country-rank-history.json. "
                         "Default derived from --slug.")
    ap.add_argument("--cross", type=pathlib.Path,
                    default=pathlib.Path("data/te-fleet-rank-history.json"),
                    help="Cross-vintage output path.")
    args = ap.parse_args()

    if not args.slug:
        print("::error::Empty --slug (set VINTAGE_SLUG env or pass --slug)", file=sys.stderr)
        return 2

    per_vintage_path = (
        args.per_vintage
        or pathlib.Path(f"data/te-fleet-run-{args.slug}/countries/country-rank-history.json")
    )
    return append_rank_history(args.slug, per_vintage_path, args.cross)


if __name__ == "__main__":
    sys.exit(main())
