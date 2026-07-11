#!/usr/bin/env python3
"""CI validation for verification verdict files (events/verification/).

Closes the gate validate_events.py never covered: verification/ was unvalidated
while its schema is evolving to the v2 double-verify shape (2026-07-02 design).

Accepts BOTH generations per entry:
  - legacy flat: {year, title, verdict, reason, [source]} with verdict in
    TRUE/FALSE/PARTIAL/UNCERTAIN (CONTESTED is v2-only)
  - v2:          adds verify_count, consensus_verdict, consensus_status,
    needs_tiebreak, source_independence, verifications[] — checked for internal
    consistency: verify_count == len(verifications), and ALL derived consensus
    fields (verdict/consensus_verdict/consensus_status/needs_tiebreak/had_dissent)
    must match recompute_consensus(verifications) under at least one of the two
    B1 policies (entries carry no policy field; the stored consensus_status
    discriminates). recompute_consensus is the Python parity port of
    workflows/events/schemas.mjs::recomputeConsensus, locked together by
    tests/consensus_vectors.json.

Join coverage: every (year, norm_title) should match a curated entry in the same
country file (same normalization as build_verified_positives._norm_title). 11
known orphans exist today (iran/venezuela/south_sudan/ukraine), so orphans WARN
by default; --strict-join makes them errors once cleaned up.

Exit code 0 = valid, 1 = errors found.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EVENTS_ROOT = Path(__file__).resolve().parent.parent / "events"
VERIFICATION_DIR = EVENTS_ROOT / "verification"
CURATED_DIR = EVENTS_ROOT / "curated"
POLICY_PATH = EVENTS_ROOT / "_ledger" / "consensus_policy.json"

POLICIES = ("conservative_downgrade", "majority_overturn")


def load_active_policy(path: Path = POLICY_PATH) -> str | None:
    """The founder-ratified B1 policy (events/_ledger/consensus_policy.json).
    Returns None when the file is absent/unreadable — the consensus check then
    falls back to accepting either policy's recompute (pre-ratification behavior)."""
    try:
        p = json.loads(path.read_text(encoding="utf-8")).get("active_policy")
        return p if p in POLICIES else None
    except Exception:
        return None

VERDICTS = ("TRUE", "FALSE", "PARTIAL", "UNCERTAIN")
CONSENSUS_VERDICTS = VERDICTS + ("CONTESTED",)
CONSENSUS_STATUSES = ("single", "double_confirmed", "double_negative", "downgraded",
                      "contested_open", "contested_resolved", "soft_kept")
INDEPENDENCE_VALUES = ("independent", "same_domain", "weak", "n/a")

_NONALNUM = re.compile(r"[^a-z0-9]+")


def _norm_title(title: str | None) -> str:
    """MUST match qgi-ml/scripts/build_verified_positives.py::_norm_title byte-for-byte
    (and workflows/events/schemas.mjs::normTitle) — it defines the join identity."""
    return _NONALNUM.sub(" ", (title or "").lower()).strip()


def recompute_consensus(passes: list[dict], policy: str = "conservative_downgrade") -> dict:
    """Python parity port of workflows/events/schemas.mjs::recomputeConsensus (§3.3).

    Returns {consensus_verdict, verdict, consensus_status, needs_tiebreak[, had_dissent]}.
    Raises ValueError on empty passes or an invalid pass verdict.
    """
    if not passes:
        raise ValueError("recompute_consensus: passes must be a non-empty list")
    v = [str(p.get("verdict")).upper() for p in passes]
    for x in v:
        if x not in VERDICTS:
            raise ValueError(f"recompute_consensus: invalid pass verdict {x!r}")
    n = len(v)
    t = v.count("TRUE")
    f = v.count("FALSE")
    has_p = "PARTIAL" in v
    has_u = "UNCERTAIN" in v

    def st(cv, status, tb=False, **extra):
        return {"consensus_verdict": cv, "verdict": cv, "consensus_status": status,
                "needs_tiebreak": tb, **extra}

    if len(set(v)) == 1:                                       # rule 1: unanimous
        return st(v[0], ("double_confirmed" if v[0] == "TRUE" else "double_negative")
                  if n >= 2 else "single")
    if t >= 1 and f >= 1:                                      # rule 2: hard clash
        if n <= 2:
            return st("CONTESTED", "contested_open", True)
        if t > f:
            return st("TRUE", "contested_resolved", False, had_dissent=True)
        if f > t:
            return st("FALSE", "contested_resolved", False, had_dissent=True)
        return st("CONTESTED", "contested_open", True)         # t == f, n >= 3
    if f >= 1:                                                 # rule 3: soft, FALSE present
        return st("FALSE", "downgraded")
    if policy == "majority_overturn":
        cv = "TRUE" if t >= 1 else ("PARTIAL" if has_p else "UNCERTAIN")
        return st(cv, "soft_kept")
    # conservative_downgrade: least-confident present on TRUE > PARTIAL > UNCERTAIN
    return st("UNCERTAIN" if has_u else "PARTIAL", "downgraded")


def _load_curated_keys(curated_dir: Path) -> dict[str, set[tuple[int, str]]]:
    keys: dict[str, set[tuple[int, str]]] = {}
    if not curated_dir.exists():
        return keys
    for cf in sorted(curated_dir.glob("*.json")):
        if cf.stem.startswith("_") or "curation_report" in cf.name:
            continue
        try:
            events = json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            continue  # curated corruption is validate_events.py's job to report
        if not isinstance(events, list):
            continue
        # non-int years are validate_events.py's problem — don't let one crash this gate
        keys[cf.stem] = {(e["year"], _norm_title(e.get("title")))
                         for e in events
                         if isinstance(e, dict) and isinstance(e.get("year"), int)}
    return keys


def _validate_pass(prefix: str, i: int, p, errors: list[str]) -> None:
    if not isinstance(p, dict):
        errors.append(f"{prefix}: verifications[{i}] must be a dict")
        return
    if p.get("pass_n") != i + 1:
        errors.append(f"{prefix}: verifications[{i}].pass_n must be {i + 1}, got {p.get('pass_n')!r}")
    if str(p.get("verdict")).upper() not in VERDICTS:
        errors.append(f"{prefix}: verifications[{i}].verdict {p.get('verdict')!r} invalid "
                      f"(pass verdicts are TRUE/FALSE/PARTIAL/UNCERTAIN — never CONTESTED)")
    ver = p.get("verifier")
    if not isinstance(ver, dict) or not ver.get("model") or not ver.get("method"):
        errors.append(f"{prefix}: verifications[{i}].verifier must carry model + method")


def validate_entry(prefix: str, e, curated_keys: set[tuple[int, str]] | None,
                   errors: list[str], warnings: list[str], strict_join: bool,
                   active_policy: str | None = None) -> None:
    if not isinstance(e, dict):
        errors.append(f"{prefix}: entry must be a dict")
        return
    year, title = e.get("year"), e.get("title")
    if not isinstance(year, int):
        errors.append(f"{prefix}: 'year' must be int, got {type(year).__name__}")
    if not isinstance(title, str) or not title:
        errors.append(f"{prefix}: 'title' must be non-empty string")
    verdict = e.get("verdict")
    is_v2 = "verifications" in e

    if is_v2:
        if verdict not in CONSENSUS_VERDICTS:
            errors.append(f"{prefix}: v2 'verdict' {verdict!r} not in {CONSENSUS_VERDICTS}")
        passes = e.get("verifications")
        if not isinstance(passes, list) or not passes:
            errors.append(f"{prefix}: 'verifications' must be a non-empty array")
            passes = []
        for i, p in enumerate(passes):
            _validate_pass(prefix, i, p, errors)
        if e.get("verify_count") != len(passes):
            errors.append(f"{prefix}: verify_count {e.get('verify_count')!r} != "
                          f"len(verifications) {len(passes)}")
        if e.get("consensus_status") not in CONSENSUS_STATUSES:
            errors.append(f"{prefix}: consensus_status {e.get('consensus_status')!r} invalid")
        if not isinstance(e.get("needs_tiebreak"), bool):
            errors.append(f"{prefix}: needs_tiebreak must be bool")
        if e.get("source_independence") not in INDEPENDENCE_VALUES:
            errors.append(f"{prefix}: source_independence {e.get('source_independence')!r} invalid")
        if passes and all(isinstance(p, dict) and str(p.get("verdict")).upper() in VERDICTS
                          for p in passes):
            # B1 ratified (2026-07-02): when events/_ledger/consensus_policy.json
            # names the active policy, every entry's derived fields (verdict,
            # consensus_verdict, consensus_status, needs_tiebreak, had_dissent) must
            # match THAT policy's recompute — a hand-edit that promotes a downgraded
            # entry to soft_kept under the conservative regime fails CI. Only when
            # no policy file exists (pre-ratification checkouts) does the check fall
            # back to accepting either policy's recompute.
            recomputes = ([recompute_consensus(passes, active_policy)]
                          if active_policy
                          else [recompute_consensus(passes, p) for p in POLICIES])

            def _matches(c: dict) -> bool:
                return (verdict == c["consensus_verdict"]
                        and e.get("consensus_verdict") == c["consensus_verdict"]
                        and e.get("consensus_status") == c["consensus_status"]
                        and bool(e.get("needs_tiebreak")) == c["needs_tiebreak"]
                        and bool(e.get("had_dissent", False)) == bool(c.get("had_dissent", False)))

            if not any(_matches(c) for c in recomputes):
                expected = "; ".join(
                    f"{c['consensus_verdict']}/{c['consensus_status']}" for c in recomputes)
                regime = f"active policy {active_policy}" if active_policy else "either policy"
                errors.append(
                    f"{prefix}: consensus mismatch — stored (verdict={verdict!r}, "
                    f"consensus_verdict={e.get('consensus_verdict')!r}, "
                    f"consensus_status={e.get('consensus_status')!r}, "
                    f"needs_tiebreak={e.get('needs_tiebreak')!r}, "
                    f"had_dissent={e.get('had_dissent', False)!r}) does not match the "
                    f"recompute under {regime} (expected {expected})")
    else:
        if verdict not in VERDICTS:
            errors.append(f"{prefix}: legacy 'verdict' {verdict!r} not in {VERDICTS} "
                          f"(CONTESTED requires the v2 shape)")
        if not e.get("reason"):
            warnings.append(f"{prefix}: legacy entry has no 'reason'")

    # join coverage (the load-bearing contract)
    if isinstance(year, int) and isinstance(title, str) and curated_keys is not None:
        if (year, _norm_title(title)) not in curated_keys:
            msg = (f"{prefix}: no curated entry joins to (year={year}, "
                   f"norm_title={_norm_title(title)!r}) — orphan verdict")
            (errors if strict_join else warnings).append(msg)


_UNSET = object()  # sentinel: "load the ratified policy from disk"


def validate_directory(verification_dir: Path = VERIFICATION_DIR,
                       curated_dir: Path = CURATED_DIR,
                       strict_join: bool = False,
                       active_policy=_UNSET) -> tuple[list[str], list[str], int, int]:
    if active_policy is _UNSET:
        active_policy = load_active_policy()
    errors: list[str] = []
    warnings: list[str] = []
    n_files = n_entries = 0
    if not verification_dir.exists():
        return [f"verification directory not found: {verification_dir}"], [], 0, 0
    curated_keys = _load_curated_keys(curated_dir)

    for vf in sorted(verification_dir.glob("*.json")):
        if vf.stem.startswith("_") or "curation_report" in vf.name:
            continue
        n_files += 1
        raw = vf.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            errors.append(f"{vf.name}: file has a UTF-8 BOM (breaks strict json.load consumers)")
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except Exception as ex:
            errors.append(f"{vf.name}: invalid JSON — {ex}")
            continue
        if not isinstance(data, list):
            errors.append(f"{vf.name}: root must be a JSON array, got {type(data).__name__}")
            continue
        ck = curated_keys.get(vf.stem)
        if ck is None:
            errors.append(f"{vf.name}: no curated file '{vf.stem}.json' — verification "
                          f"files must shadow a curated country file")
            ck = set()
        for i, e in enumerate(data):
            n_entries += 1
            validate_entry(f"{vf.name}[{i}]", e, ck, errors, warnings, strict_join,
                           active_policy)

    return errors, warnings, n_files, n_entries


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verification-dir", type=Path, default=VERIFICATION_DIR)
    ap.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    ap.add_argument("--strict-join", action="store_true",
                    help="treat orphan verdicts (no curated join) as errors, not warnings")
    ap.add_argument("--max-warnings", type=int, default=25,
                    help="print at most this many warnings (all are counted)")
    args = ap.parse_args(argv)

    active = load_active_policy()
    errors, warnings, n_files, n_entries = validate_directory(
        args.verification_dir, args.curated_dir, strict_join=args.strict_join,
        active_policy=active)

    print(f"Validated {n_files} verification files, {n_entries} entries total "
          f"(consensus regime: {active or 'either-policy fallback — no policy file'}).")
    if warnings:
        print(f"\n{len(warnings)} warnings:")
        for w in warnings[:args.max_warnings]:
            print(f"  WARNING: {w}")
        if len(warnings) > args.max_warnings:
            print(f"  ... and {len(warnings) - args.max_warnings} more")
    if errors:
        print(f"\n{len(errors)} ERRORS:")
        for e in errors:
            print(f"  ERROR: {e}")
        return 1
    print("\nAll verification files valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
