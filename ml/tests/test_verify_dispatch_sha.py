"""Tests for `qgi_ml.scripts.verify_dispatch_sha` (F-H-1 item 4 deploy gate).

Locks the deploy-time verifier's contract:

1. EXPECTED_DISPATCH_SHA is pinned to the post-KI-2 amendment state.
2. verify() returns (True, ...) when runtime SHA matches AND invariants hold.
3. verify() returns (False, ...) with rotation guidance when SHA mismatches.
4. verify() returns (False, ...) with invariant detail when SHA matches but
   the dispatch table fails an F-H-1 / F-H-3 structural invariant.
5. CLI main() exits 0 on pass, 1 on fail.

Rotation of EXPECTED_DISPATCH_SHA is governed by F-H-4: every change to the
constant must accompany a new pre-reg amendment + the same-PR dispatch JSON
edit. See scripts/verify_dispatch_sha.py for the rotation playbook.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import verify_dispatch_sha  # noqa: E402
from hybrid_dispatch import load_dispatch  # noqa: E402


# ----------------------------------------------------------------------------
# EXPECTED_DISPATCH_SHA pin
# ----------------------------------------------------------------------------


def test_expected_sha_constant_is_pinned_hex():
    """EXPECTED_DISPATCH_SHA must be a 64-character lowercase hex SHA-256, not
    a placeholder. F-H-4 forbids leaving the constant in a deferred sentinel
    state on main after Stage 4."""
    sha = verify_dispatch_sha.EXPECTED_DISPATCH_SHA
    assert isinstance(sha, str)
    assert re.fullmatch(r"[0-9a-f]{64}", sha), (
        f"EXPECTED_DISPATCH_SHA must be 64 lowercase hex chars; got {sha!r}"
    )


def test_expected_sha_matches_current_dispatch_json():
    """The pinned SHA must equal the SHA computed from the canonical dispatch
    JSON currently on this branch. A bare JSON edit without rotating the
    constant is a pre-reg integrity violation per F-H-4 — this test surfaces
    such a violation in CI."""
    runtime_sha = load_dispatch().sha256
    assert verify_dispatch_sha.EXPECTED_DISPATCH_SHA == runtime_sha, (
        "Pinned EXPECTED_DISPATCH_SHA differs from the SHA of "
        "config/hybrid_architecture_dispatch.json on this branch. The "
        "dispatch JSON was changed without rotating the constant, OR the "
        "constant was rotated without matching the JSON content. F-H-4 "
        "requires both to move together in a pre-reg amendment PR."
    )


# ----------------------------------------------------------------------------
# verify() — passing path
# ----------------------------------------------------------------------------


def test_verify_passes_when_sha_matches_and_invariants_hold():
    """In the on-main pinned state, verify() returns (True, ok-message)."""
    ok, message = verify_dispatch_sha.verify()
    assert ok is True, f"verify() should pass on main; got message: {message}"
    assert "OK" in message
    assert "F-H-1" in message and "invariants" in message.lower()


def test_main_returns_zero_when_pinned():
    """CLI entry point exits with code 0 in the pinned state (CI green)."""
    exit_code = verify_dispatch_sha.main()
    assert exit_code == 0


# ----------------------------------------------------------------------------
# verify() — SHA mismatch failure path
# ----------------------------------------------------------------------------


def test_verify_fails_when_expected_sha_does_not_match_runtime(monkeypatch):
    """If EXPECTED_DISPATCH_SHA is rotated to a wrong value, verify() must
    fail with a SHA-mismatch message that includes both SHAs and rotation
    guidance.

    Simulates the case where the dispatch JSON has been edited but the
    constant has been wrong-rotated. This is what F-H-4 PR review catches.
    """
    fake_sha = "0" * 64
    monkeypatch.setattr(verify_dispatch_sha, "EXPECTED_DISPATCH_SHA", fake_sha)
    ok, message = verify_dispatch_sha.verify()
    assert ok is False
    assert "FAIL" in message
    assert "SHA mismatch" in message
    assert fake_sha in message  # cited as the expected value
    runtime_sha = load_dispatch().sha256
    assert runtime_sha in message  # actual runtime SHA also cited
    # Failure message must point to the F-H-4 rotation procedure
    assert "F-H-4" in message


def test_main_returns_nonzero_on_sha_mismatch(monkeypatch, capsys):
    """CLI exits 1 when SHA mismatches; failure goes to stderr per Unix
    convention so CI logs surface it."""
    monkeypatch.setattr(verify_dispatch_sha, "EXPECTED_DISPATCH_SHA", "0" * 64)
    exit_code = verify_dispatch_sha.main()
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.err


# ----------------------------------------------------------------------------
# verify() — invariant violation failure path
# ----------------------------------------------------------------------------


def test_verify_fails_when_dispatch_invariant_violated(monkeypatch):
    """If the SHA matches but the dispatch violates an F-H-1 / F-H-3
    structural invariant (e.g. an arch outside {D2, D5}), verify() must
    return False with an invariant-specific message.

    Simulates by monkeypatching `assert_dispatch_invariants` to raise.
    """
    def raising_invariants(_dispatch):
        raise AssertionError("synthetic-invariant-violation-for-test")

    monkeypatch.setattr(
        verify_dispatch_sha, "assert_dispatch_invariants", raising_invariants
    )
    ok, message = verify_dispatch_sha.verify()
    assert ok is False
    assert "invariant violation" in message.lower()
    assert "synthetic-invariant-violation-for-test" in message
    # SHA matched, so the message should make that clear before pivoting to
    # the invariant failure — distinguishes from a pure SHA mismatch
    assert "SHA matches" in message or "SHA matches EXPECTED" in message


def test_verify_invariants_actually_run(monkeypatch):
    """verify() must invoke assert_dispatch_invariants — guards against a
    future regression where someone removes the call. Counts invocations."""
    call_count = {"n": 0}
    real_assert = verify_dispatch_sha.assert_dispatch_invariants

    def counting_assert(dispatch):
        call_count["n"] += 1
        return real_assert(dispatch)

    monkeypatch.setattr(
        verify_dispatch_sha, "assert_dispatch_invariants", counting_assert
    )
    verify_dispatch_sha.verify()
    assert call_count["n"] == 1, (
        "verify() must call assert_dispatch_invariants exactly once per "
        "invocation; got "
        f"{call_count['n']} calls"
    )
