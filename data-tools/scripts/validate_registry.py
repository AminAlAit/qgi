#!/usr/bin/env python3
"""CI guard for registries/candidate-registry.json (indicator-enrichment stage 0).

Standalone (no qgi-ml import) so qgi-data CI can validate the registry on every PR
touching registries/**. Mirrors the invariants enforced by qgi-ml
scripts/enrichment/registry.py validate_registry(): unique indicator_id +
numeric_id, numeric_id within the entry's declared provider block, and
status/category in the allowed vocab. Exits 1 on any violation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REG = Path(__file__).resolve().parents[1] / "registries" / "candidate-registry.json"

ALLOWED_STATUS = {"candidate", "vetted", "active", "held", "quarantined"}
ALLOWED_CATEGORIES = {
    "Economic", "Trade", "Finance", "Energy", "Military", "Governance", "Government",
    "Health", "Demographic", "Social", "Education", "Infrastructure", "Environment", "Other",
}


def validate(reg: dict) -> list[str]:
    errors: list[str] = []
    blocks = {k: tuple(v) for k, v in reg.get("provider_blocks", {}).items()}
    seen_id: set[str] = set()
    seen_num: dict[int, str] = {}
    for e in reg.get("indicators", []):
        iid = e.get("indicator_id", "<missing>")
        for f in ("indicator_id", "provider", "numeric_id", "name", "status", "category"):
            if f not in e:
                errors.append(f"{iid}: missing field {f!r}")
        if e.get("status") not in ALLOWED_STATUS:
            errors.append(f"{iid}: bad status {e.get('status')!r}")
        if e.get("category") not in ALLOWED_CATEGORIES:
            errors.append(f"{iid}: bad category {e.get('category')!r}")
        if iid in seen_id:
            errors.append(f"duplicate indicator_id {iid!r}")
        seen_id.add(iid)
        num, prov = e.get("numeric_id"), e.get("provider")
        if isinstance(num, int):
            if num in seen_num:
                errors.append(f"duplicate numeric_id {num} ({seen_num[num]} & {iid})")
            seen_num[num] = iid
            if prov in blocks:
                lo, hi = blocks[prov]
                if not (lo <= num <= hi):
                    errors.append(f"{iid}: numeric_id {num} outside {prov} block {lo}-{hi}")
            else:
                errors.append(f"{iid}: provider {prov!r} not in provider_blocks")
    return errors


def main() -> int:
    if not REG.exists():
        print(f"OK - no registry at {REG.name} (nothing to validate)")
        return 0
    reg = json.loads(REG.read_text(encoding="utf-8"))
    errs = validate(reg)
    if errs:
        print(f"INVALID candidate-registry.json ({len(errs)} violations):", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"OK - {len(reg.get('indicators', []))} indicators, no violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
