"""assemble_recipe_floors.py — FLEET-1b/#960 (seed of #952 atomic data-prep).

Combine the wave-1 path-(a/b) floors (prior-D2-walk provenance, hand-curated) with the
path-(c) greenfield naive-baseline floors (compute_naive_baselines output) into ONE
recipe-floors.json that the fleet entrypoint reads.

Stamps the artifact with frozen-before-walk PROVENANCE that FLEET-5 / Condition A
requires: `frozen_at_utc`, `panel_fingerprint` (the vintage the floors were computed
against — must match the panels the fleet walks), and `git_commit_sha`. A recipe absent
here is SKIPPED in fleet mode; the fleet refuses to run if this artifact lacks provenance
or was not frozen before launch.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import run_f_ml_1_poc as drv  # noqa: E402  (for the global panel_data_fingerprint)


def build_path_c_floor_rows(baselines: dict[str, dict], cohort_gap: float = 0.06) -> dict[str, dict]:
    """Pure: naive-baseline entries -> floor rows. cohort_loco_floor = lock_floor - gap.
    Carries provenance (path c, naive basis, winner, floor_basis). Testable."""
    rows: dict[str, dict] = {}
    for rid, e in baselines.items():
        if "error" in e or e.get("lock_floor") is None:
            continue  # a recipe that failed to compute gets NO floor → fleet skips it (loud)
        lf = round(float(e["lock_floor"]), 4)
        rows[rid] = {
            "lock_floor": lf,
            "cohort_loco_floor": round(lf - cohort_gap, 4),
            "path": "c",
            "basis_loco": e.get("naive_loco"),
            "naive_winner": e.get("naive_winner"),
            "floor_basis": e.get("floor_basis"),
            "source": "naive-baselines.json",
            "wave": "c",
        }
    return rows


def _merge_baselines(paths: list[Path]) -> dict[str, dict]:
    """Merge naive-baseline parts. (Each entry's own `panel_fingerprint` is a PER-RECIPE
    provenance hash — kept in naive-baselines.json, not used here; the floors file carries
    one GLOBAL panel-dir fingerprint computed in main() for the Condition-A vintage check.)"""
    merged: dict[str, dict] = {}
    for p in paths:
        d = json.loads(p.read_text(encoding="utf-8"))
        merged.update(d.get("baselines", {}))
    return merged


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline-files", nargs="+", type=Path, required=True,
                   help="naive-baselines JSON files to merge (banked + parallel parts)")
    p.add_argument("--wave1-floors", type=Path, required=True,
                   help="existing recipe-floors.json — its path-(a/b) wave-1 rows are preserved")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--panel-dir", type=Path, default=REPO_ROOT / "data" / "parquet_panels",
                   help="panel dir the floors were computed against — its global fingerprint is "
                        "stamped for the FLEET-5 / Condition-A vintage check")
    p.add_argument("--cohort-gap", type=float, default=0.06)
    p.add_argument("--abs-floor", type=float, default=0.70)
    p.add_argument("--floor-cap", type=float, default=0.90)
    p.add_argument("--delta-lift", type=float, default=0.03)
    args = p.parse_args(argv)

    merged = _merge_baselines(args.baseline_files)
    panel_fp = drv.panel_data_fingerprint(args.panel_dir)  # global vintage of the walked panels
    path_c = build_path_c_floor_rows(merged, cohort_gap=args.cohort_gap)

    wave1 = json.loads(args.wave1_floors.read_text(encoding="utf-8")).get("floors", {})
    wave1_ab = {k: v for k, v in wave1.items() if v.get("path") == "a/b"}  # preserve only a/b
    overlap = set(wave1_ab) & set(path_c)
    if overlap:
        raise SystemExit(f"a recipe appears in BOTH wave-1 (a/b) and path-c: {overlap}")

    floors = {**wave1_ab, **path_c}
    # sanity: no floor may exceed the cap
    bad = {k: v["lock_floor"] for k, v in floors.items() if v["lock_floor"] > args.floor_cap}
    if bad:
        raise SystemExit(f"floor(s) exceed cap {args.floor_cap}: {bad}")

    payload = {
        "schema_version": 1,
        "policy": "fleet-floor-annex.md (5-Opus-Majles + founder absolute floor 0.70, 2026-05-25); "
                  "path-c greenfield via compute_naive_baselines (FLEET-1b/#960).",
        "delta_lift": args.delta_lift, "abs_floor": args.abs_floor, "cohort_gap": args.cohort_gap,
        "floor_cap": args.floor_cap,
        # FLEET-5 / Condition A provenance — frozen BEFORE the fleet walks this vintage.
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "panel_fingerprint": panel_fp,
        "git_commit_sha": _git_sha(),
        "note": "cohort_loco_floor = lock_floor - cohort_gap. Wave-1 path-(a/b) preserved from "
                "prior D2 walks; path-(c) rows are naive-baseline floors. A recipe absent here "
                "is SKIPPED in fleet mode (and the fleet refuses to run without this provenance).",
        "floors": floors,
    }
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}: {len(floors)} floors "
          f"({len(wave1_ab)} wave-1 a/b + {len(path_c)} path-c) | panel_fingerprint={panel_fp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
