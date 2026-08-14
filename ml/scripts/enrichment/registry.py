"""Candidate registry - indicator-enrichment pipeline stage 0.

A single, provider-agnostic source of truth for every indicator QGI tracks, with
a status lifecycle. The registry GENERATES the existing downstream artifacts
(control-surface.xlsx sheets, indicator-allow-list.json) - it does not replace
the sheet-fetcher / dispatcher contract, so the live ingestion keeps working.

Lifecycle:
    candidate   - catalogued, not yet vetted            (not in the pipeline)
    vetted      - passed the vet gate, cleared to ingest (-> control surface: process)
    active      - ingested, panel exists, in the pool    (-> control surface: process; in allow-list)
    held        - deliberately deprioritized             (-> control surface: hold)
    quarantined - failed the vet gate                    (not in the pipeline)

numeric_id is the cross-system join key and MUST be globally unique. Existing
allocations are preserved (WB 1-275, V-Dem 276-314); new providers get fresh,
non-colliding blocks. Adding indicators only ever allocates from a provider's
block - it never renumbers existing entries.

Design: docs/specs/internal/ops/ml-track/indicator-enrichment-cicd-design.md
Local, $0, no AWS.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

# Provider numeric_id blocks. Existing (WB/VDEM) preserved exactly; new providers
# get fresh ranges above 314; *_EXT blocks give WB/V-Dem room to grow without
# colliding with the legacy 1-314 assignments. GDELT reserved (bias-gated).
PROVIDER_BLOCKS: dict[str, tuple[int, int]] = {
    "WB": (1, 275),
    "VDEM": (276, 314),
    "FAOSTAT": (315, 399),
    "UCDP": (400, 449),
    "UNHCR": (450, 499),
    "IDMC": (500, 549),
    "ILOSTAT": (550, 699),
    "UNDP": (700, 749),
    "OECD": (750, 849),
    "OWID": (850, 899),
    "VDEM_EXT": (900, 1399),
    "WB_EXT": (1400, 2399),
    "GDELT": (9000, 9999),
}

ALLOWED_STATUS = frozenset({"candidate", "vetted", "active", "held", "quarantined"})

# Map registry status -> the control-surface 'status' the sheet-fetcher understands
# ({process, hold}). Statuses absent from this map are excluded from the control
# surface entirely (not yet ready to fetch).
STATUS_TO_PIPELINE: dict[str, str] = {"vetted": "process", "active": "process", "held": "hold"}

# Legal lifecycle transitions (anything else is rejected).
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = {
    "candidate": frozenset({"vetted", "quarantined", "held"}),
    "vetted": frozenset({"active", "held", "quarantined"}),
    "active": frozenset({"held", "quarantined"}),
    # held was already evaluated; recovery is held -> vetted -> active (NOT back to
    # candidate, which would falsely claim "not yet evaluated" + orphan the vetted date).
    "held": frozenset({"vetted", "active"}),
    "quarantined": frozenset({"candidate"}),
}

# Must stay in lockstep with qgi-data/tests/test_control_surface_schema.py
# ALLOWED_CATEGORIES (and qgi-frontend lib/design.ts SECTOR_COLORS).
ALLOWED_CATEGORIES = frozenset({
    "Economic", "Trade", "Finance", "Energy", "Military", "Governance", "Government",
    "Health", "Demographic", "Social", "Education", "Infrastructure", "Environment", "Other",
})

CANONICAL_HEADER = ("id_string", "numeric_id", "name", "status", "category", "description")


class RegistryError(Exception):
    """Registry validation / allocation failure."""


def _today() -> str:
    return date.today().isoformat()


def base_provider(provider: str) -> str:
    """Resolve an allocation-overflow block (e.g. 'WB_EXT') to its base provider
    ('WB'). Overflow blocks exist only to give WB / V-Dem numeric_id room beyond
    the legacy 1-314 range; they share the base provider's control-surface sheet
    and fetcher routing. A plain provider passes through unchanged."""
    return provider[:-4] if provider.endswith("_EXT") else provider


def provider_for_sheet(provider: str) -> str:
    """Control-surface sheet name for a provider (preserves legacy sheet names).
    Overflow (*_EXT) blocks resolve to their base provider's sheet so new WB /
    V-Dem indicators land in the existing phase_2 / vdem sheets the fetchers read."""
    p = base_provider(provider)
    if p == "WB":
        return "phase_2_indicators"
    if p == "VDEM":
        return "vdem_indicators"
    return f"{p.lower()}_indicators"


def empty_registry() -> dict[str, Any]:
    return {"schema_version": 1, "generated": _today(),
            "provider_blocks": {k: list(v) for k, v in PROVIDER_BLOCKS.items()},
            "indicators": []}


def load_registry(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_registry(reg: dict[str, Any], path: str | Path) -> None:
    reg["generated"] = _today()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def allocate_numeric_id(reg: dict[str, Any], provider: str) -> int:
    """Lowest free numeric_id inside the provider's block (errors if block full)."""
    if provider not in PROVIDER_BLOCKS:
        raise RegistryError(f"unknown provider {provider!r}; known: {sorted(PROVIDER_BLOCKS)}")
    lo, hi = PROVIDER_BLOCKS[provider]
    used = {e["numeric_id"] for e in reg["indicators"]}
    for i in range(lo, hi + 1):
        if i not in used:
            return i
    raise RegistryError(f"provider block {provider} ({lo}-{hi}) is full")


def add_indicator(
    reg: dict[str, Any],
    *,
    indicator_id: str,
    provider: str,
    name: str,
    category: str,
    description: str = "",
    provider_meta: dict[str, Any] | None = None,
    status: str = "candidate",
    numeric_id: int | None = None,
) -> dict[str, Any]:
    """Append a new indicator (allocating a numeric_id if not given). Validates the
    single entry; call validate_registry() for whole-file invariants."""
    if any(e["indicator_id"] == indicator_id for e in reg["indicators"]):
        raise RegistryError(f"duplicate indicator_id {indicator_id!r}")
    if status not in ALLOWED_STATUS:
        raise RegistryError(f"bad status {status!r}")
    if category not in ALLOWED_CATEGORIES:
        raise RegistryError(f"bad category {category!r} for {indicator_id}")
    if numeric_id is None:
        numeric_id = allocate_numeric_id(reg, provider)
    entry = {
        "indicator_id": indicator_id,
        "provider": provider,
        "numeric_id": numeric_id,
        "name": name,
        "status": status,
        "category": category,
        "description": description,
        "provider_meta": provider_meta or {},
        "lifecycle": {"added": _today(), "vetted": None, "activated": None, "reason": None},
        "vet": None,
    }
    reg["indicators"].append(entry)
    return entry


def get_indicator(reg: dict[str, Any], indicator_id: str) -> dict[str, Any]:
    for e in reg["indicators"]:
        if e["indicator_id"] == indicator_id:
            return e
    raise RegistryError(f"no such indicator {indicator_id!r}")


def transition(reg: dict[str, Any], indicator_id: str, new_status: str,
               *, reason: str | None = None, when: str | None = None) -> dict[str, Any]:
    """Move an indicator to a new lifecycle status, enforcing legal transitions."""
    if new_status not in ALLOWED_STATUS:
        raise RegistryError(f"bad status {new_status!r}")
    e = get_indicator(reg, indicator_id)
    cur = e["status"]
    if new_status not in LEGAL_TRANSITIONS.get(cur, frozenset()):
        raise RegistryError(f"illegal transition {cur!r} -> {new_status!r} for {indicator_id}")
    when = when or _today()
    e["status"] = new_status
    if new_status == "vetted":
        e["lifecycle"]["vetted"] = when
    elif new_status == "active":
        e["lifecycle"]["activated"] = when
    if reason is not None:
        e["lifecycle"]["reason"] = reason
    return e


def validate_registry(reg: dict[str, Any]) -> list[str]:
    """Return a list of human-readable invariant violations ([] == valid)."""
    errors: list[str] = []
    seen_ids: dict[str, int] = {}
    seen_nums: dict[int, str] = {}
    for e in reg["indicators"]:
        iid = e.get("indicator_id", "<missing>")
        for field in ("indicator_id", "provider", "numeric_id", "name", "status", "category"):
            if field not in e:
                errors.append(f"{iid}: missing field {field!r}")
        prov = e.get("provider")
        if prov not in PROVIDER_BLOCKS:
            errors.append(f"{iid}: unknown provider {prov!r}")
        if e.get("status") not in ALLOWED_STATUS:
            errors.append(f"{iid}: bad status {e.get('status')!r}")
        if e.get("category") not in ALLOWED_CATEGORIES:
            errors.append(f"{iid}: bad category {e.get('category')!r}")
        if iid in seen_ids:
            errors.append(f"duplicate indicator_id {iid!r}")
        seen_ids[iid] = seen_ids.get(iid, 0) + 1
        num = e.get("numeric_id")
        if isinstance(num, int):
            if num in seen_nums:
                errors.append(f"duplicate numeric_id {num} ({seen_nums[num]} & {iid})")
            seen_nums[num] = iid
            if prov in PROVIDER_BLOCKS:
                lo, hi = PROVIDER_BLOCKS[prov]
                if not (lo <= num <= hi):
                    errors.append(f"{iid}: numeric_id {num} outside {prov} block {lo}-{hi}")
    return errors


def to_control_surface(reg: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Generate per-sheet control-surface rows from the registry.

    Only statuses in STATUS_TO_PIPELINE (vetted/active/held) reach the sheets.
    Rows carry CANONICAL_HEADER columns first, then any provider_meta columns
    (the sheet-fetcher passes non-essential columns through verbatim).
    Sorted by numeric_id for deterministic output.
    """
    sheets: dict[str, list[dict[str, Any]]] = {}
    for e in sorted(reg["indicators"], key=lambda x: x["numeric_id"]):
        pipe_status = STATUS_TO_PIPELINE.get(e["status"])
        if pipe_status is None:
            continue
        sheet = provider_for_sheet(e["provider"])
        row = {
            "id_string": e["indicator_id"],
            "numeric_id": e["numeric_id"],
            "name": e["name"],
            "status": pipe_status,
            "category": e["category"],
            "description": e.get("description", ""),
        }
        # provider_meta is passthrough, but must never clobber a canonical column.
        row.update({k: v for k, v in (e.get("provider_meta") or {}).items()
                    if k not in CANONICAL_HEADER})
        sheets.setdefault(sheet, []).append(row)
    return sheets


def to_allow_list(reg: dict[str, Any]) -> dict[str, Any]:
    """Generate the indicator-allow-list.json payload (active indicators only)."""
    active = sorted(e["numeric_id"] for e in reg["indicators"] if e["status"] == "active")
    return {
        "schema_version": 1,
        "generator": "scripts/enrichment/registry.py:to_allow_list",
        "purpose": "numeric_id allow-list for recipe-engine fingerprint filter (active pool)",
        "generated": _today(),
        "counts": {"active_indicators": len(active), "total_registry_entries": len(reg["indicators"])},
        "allow_list_numeric_ids": active,
    }


def status_summary(reg: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in reg["indicators"]:
        out[e["status"]] = out.get(e["status"], 0) + 1
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Candidate registry tooling (stage 0).")
    ap.add_argument("registry", type=Path, help="Path to candidate-registry.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="Validate invariants (exit 1 if violations)")
    sub.add_parser("summary", help="Print status counts")
    cs = sub.add_parser("control-surface", help="Emit control-surface rows as JSON")
    cs.add_argument("--output", type=Path, default=None)
    al = sub.add_parser("allow-list", help="Emit indicator-allow-list.json")
    al.add_argument("--output", type=Path, default=None)
    args = ap.parse_args(argv)

    reg = load_registry(args.registry)

    if args.cmd == "validate":
        errs = validate_registry(reg)
        if errs:
            print(f"INVALID ({len(errs)} violations):")
            for e in errs:
                print(f"  - {e}")
            return 1
        print(f"OK - {len(reg['indicators'])} indicators, no violations.")
        return 0
    if args.cmd == "summary":
        print(json.dumps(status_summary(reg), indent=2))
        return 0
    if args.cmd == "control-surface":
        payload = to_control_surface(reg)
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
            print(f"Wrote control-surface rows -> {args.output}")
        else:
            print(text)
        return 0
    if args.cmd == "allow-list":
        payload = to_allow_list(reg)
        text = json.dumps(payload, indent=2)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
            print(f"Wrote allow-list -> {args.output}")
        else:
            print(text)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
