"""F-H-1 item 4 — deploy-time dispatch SHA + invariants verification.

Per docs/specs/internal/ops/ml-track/stage-2-hybrid-d2-d5-walk-methodology-prereg.md
(commit 7db3596) F-H-1 item 4:

    "Deployment-time falsification check: at production deploy, a
    verification script must compare the dispatch-table SHA against
    the latest pre-reg-merged commit's expected SHA. Mismatch blocks
    deploy."

This script implements the deploy-time check. Two-step gate:

1. SHA pin check: runtime dispatch SHA must equal EXPECTED_DISPATCH_SHA
   (pinned below to the post-KI-2 amendment state).
2. Invariant assertions: dispatch table must satisfy the F-H-1 / F-H-3
   structural invariants (`assert_dispatch_invariants`).

Any amendment to the dispatch table requires:

1. A NEW pre-reg amendment per F-H-4 (Lakatosian guard);
2. Rotation of EXPECTED_DISPATCH_SHA below to match the new dispatch JSON;
3. The amendment commit chronologically PRECEDING any production walk
   under the new dispatch (per F-H-4 amendment constraint 1).

**Usage (CI + deploy pipeline):**

    # On every push to main, every PR, and every deploy:
    python scripts/verify_dispatch_sha.py

    # Exits 0 if both checks pass; exits 1 with a clear error message
    # if either fails (CI fails; deploy blocks).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from hybrid_dispatch import assert_dispatch_invariants, load_dispatch  # noqa: E402

# ============================================================================
# EXPECTED_DISPATCH_SHA — the SHA-256 of the canonical hybrid dispatch JSON
# at the most recent pre-reg-merged amendment commit.
#
# Pinned to the post-KI-2 amendment state:
#   - hybrid pre-reg base:  docs-specs commit 7db3596
#   - KI-2 amendment:       docs-specs commit d4c6c37 (#64; territorial_disputes
#                           FALSIFIED per Majles 2026-05-11 3-1 vote);
#                           qgi-ml commit c1379ce (#48; dispatch JSON change)
#
# This value MUST be rotated whenever the dispatch JSON content changes,
# and the rotation MUST be part of a NEW pre-reg amendment per F-H-4.
# A bare dispatch JSON edit without rotating this constant is a
# pre-reg integrity violation and should be blocked at PR review by the
# persona owning pre-reg discipline (Kwame Adjei or successor).
#
# To compute the current SHA for rotation:
#    python -c "from hybrid_dispatch import load_dispatch; print(load_dispatch().sha256)"
#
# NOTE: this is NOT `sha256sum config/hybrid_architecture_dispatch.json`. The
# canonical SHA is computed over the JSON re-serialized with sorted keys +
# compact separators (see HybridDispatch.sha256), so it is invariant to
# whitespace and key-order changes in the file on disk. The CI test
# `test_expected_sha_matches_current_dispatch_json` validates the round-trip.
# ============================================================================
EXPECTED_DISPATCH_SHA = "55de0c76914fea94cbecb99a1e80cefbc49bd3b61e5ca956dac4ceb2869c0f97"


def verify() -> tuple[bool, str]:
    """Compare runtime dispatch SHA against the pre-reg-pinned expected SHA
    AND assert F-H-1 / F-H-3 structural invariants on the dispatch table.

    Returns
    -------
    (ok, message) : tuple
        ok=True if BOTH the SHAs match AND the invariants hold; ok=False
        otherwise. The message is a human-readable description suitable
        for CI log + alert payload.
    """
    dispatch = load_dispatch()
    runtime_sha = dispatch.sha256
    if runtime_sha != EXPECTED_DISPATCH_SHA:
        return False, (
            f"FAIL: dispatch SHA mismatch.\n"
            f"  Expected (pre-reg pinned):  {EXPECTED_DISPATCH_SHA}\n"
            f"  Runtime (config/hybrid_architecture_dispatch.json): {runtime_sha}\n"
            f"\n"
            f"This deploy is BLOCKED per F-H-1 item 4. The dispatch JSON has "
            f"been modified since the last pre-reg amendment. Either:\n"
            f"  (a) Revert the dispatch JSON to the pre-reg-merged state, OR\n"
            f"  (b) File a new pre-reg amendment per F-H-4 + rotate "
            f"EXPECTED_DISPATCH_SHA in scripts/verify_dispatch_sha.py to "
            f"match the new dispatch SHA.\n"
            f"\n"
            f"A bare dispatch JSON edit without F-H-4 amendment is a pre-reg "
            f"integrity violation and should be blocked at PR review."
        )

    try:
        assert_dispatch_invariants(dispatch)
    except AssertionError as exc:
        return False, (
            f"FAIL: dispatch invariant violation.\n"
            f"  Runtime SHA matches EXPECTED ({runtime_sha[:16]}...), but the "
            f"dispatch table fails an F-H-1 / F-H-3 structural invariant:\n"
            f"\n"
            f"  {exc}\n"
            f"\n"
            f"This deploy is BLOCKED. The dispatch JSON encodes a state that "
            f"violates the pre-reg's structural contract — the SHA pin alone "
            f"would have let this through, but the runtime assertion caught "
            f"it. Fix the dispatch JSON to satisfy the invariant, OR file a "
            f"pre-reg amendment per F-H-4 if the invariant itself must change."
        )

    return True, (
        f"OK: dispatch SHA matches expected ({runtime_sha[:16]}...) AND all "
        f"F-H-1 / F-H-3 structural invariants hold. Deploy-time verification "
        f"passes."
    )


def main() -> int:
    ok, message = verify()
    if ok:
        print(message)
        return 0
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
