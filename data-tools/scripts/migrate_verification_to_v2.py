#!/usr/bin/env python3
"""Migrate flat single-verdict verification files to the v2 double-verify schema.

Wraps each legacy entry's verdict/reason/source into verifications[0] (pass_1,
verifier model "qgi-agent-verified-pre-migration") and adds the derived fields
(verify_count, consensus_verdict, consensus_status, needs_tiebreak,
source_independence). Loss-free: verdict/reason/source are preserved both at the
top level AND inside verifications[0], so legacy readers
(build_verified_positives.py, ingest_events.py — both key on top-level `verdict`)
see byte-identical semantics.

Idempotent (skips entries that already have `verifications`). Malformed entries
(verdict outside TRUE/FALSE/PARTIAL/UNCERTAIN) are left untouched for manual review.

Do NOT run scripts/split_verification_by_verdict.py after this migration — it
rebuilds entries to a flat {year,title,verdict,reason,source} dict and would strip
verifications[] and drop every PARTIAL/UNCERTAIN verdict.

Usage: python migrate_verification_to_v2.py [--apply] [--dir PATH]   # dry-run by default
"""
import argparse
import json
import sys
from pathlib import Path

VDIR = Path(__file__).resolve().parent.parent / "events" / "verification"
VALID = {"TRUE", "FALSE", "PARTIAL", "UNCERTAIN"}


def migrate_entry(e: dict) -> dict:
    if "verifications" in e:              # already v2 -> idempotent no-op
        return e
    v = str(e.get("verdict", "")).strip().upper()
    if v not in VALID:                    # leave malformed entries for manual review
        return e
    src = e.get("source")
    src = src.strip() if isinstance(src, str) and src.strip() else None
    p1 = {"pass_n": 1, "verdict": v, "reason": e.get("reason"), "source": src,
          "verifier": {"model": "qgi-agent-verified-pre-migration", "date": None, "method": "web_search"}}
    out = {"year": e.get("year"), "title": e.get("title"),
           "verdict": v, "reason": e.get("reason"),
           "verify_count": 1, "consensus_verdict": v, "consensus_status": "single",
           "needs_tiebreak": False, "source_independence": "n/a", "verifications": [p1]}
    if src:
        out["source"] = src
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dir", type=Path, default=VDIR,
                    help="verification directory (default: events/verification)")
    args = ap.parse_args(argv)
    files = sorted(args.dir.glob("*.json"))
    changed = already = 0
    for f in files:
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as ex:
            print(f"SKIP {f.name}: {ex}", file=sys.stderr); continue
        if not isinstance(data, list):
            print(f"SKIP {f.name}: not a flat array", file=sys.stderr); continue
        new = [migrate_entry(e) if isinstance(e, dict) else e for e in data]
        n_new = sum(1 for a, b in zip(data, new) if a is not b)
        if n_new == 0:
            already += 1; continue
        changed += 1
        print(f"{f.name}: {n_new}/{len(data)} entries wrapped")
        if args.apply:
            f.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: {changed} files to migrate, "
          f"{already} already v2 (idempotent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
