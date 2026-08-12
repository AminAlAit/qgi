"""Regression tests locking the in-sample F2 anomaly state for the hybrid
recipes flagged in `stage-2-hybrid-d2-d5-walk-methodology-prereg.md` and the
Stage 5 paper Section 4 (docs-specs PR #50).

**Current state (post-KI-2 amendment 2026-05-11):** ONE LOCKed recipe carries
the f_rule_anomaly flag:
  - `epidemic_and_pandemic` (STRONG tier via LOCO 0.8824; in-sample F2 fails;
    retained LOCKed with f_rule_anomaly via inherited ADVISORY-ONLY).

**Pre-amendment historical state (pre-KI-2):** TWO LOCKed recipes carried the
flag. `territorial_disputes` was the second (MODERATE tier via LOCO 0.6780;
predictions degenerated to near-zero under D5; AHI = 1.0000 was an artifact
not strength). **KI-2 Majles amendment 2026-05-11 (Option C carried 3-1;
Priya dissent for Option B logged) FALSIFIED `territorial_disputes` under
hybrid.** Hybrid LOCKed count dropped 14 → 13.

The empirical-state tests for `territorial_disputes` (test_territorial_-
disputes_in_sample_f2_fails_under_d5 + test_territorial_disputes_f1_-
uninformative_under_degenerate_predictions) are RETAINED in this module
as historical documentation of WHY the recipe was FALSIFIED — they
exercise the predictions JSON directly (not the dispatch table) and
should remain green as long as the D5 predictions artifact is unchanged.

The hybrid pre-reg F-H-1 places production predictions on the assigned
architecture. KI-2 resolved the hybrid F-rule applicability ambiguity for
the territorial_disputes case (FALSIFY); for epidemic_and_pandemic the
ambiguity is operatively resolved by the inherited ADVISORY-ONLY
restriction (n_pos_LOCO=1 per F-H-3 post-KI-1).

These tests lock the disclosed state so that a future model retrain or
pipeline change cannot accidentally "fix" the anomaly without explicit
Majles re-pre-registration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from cohort_calibration import compute_ece  # noqa: E402
from hybrid_dispatch import load_dispatch  # noqa: E402


# D5 canonical predictions path (qgi-data PR #32 commit e19da56; local mirror in qgi-ml)
D5_PREDICTIONS_LOCAL = REPO_ROOT / "results" / "d5_multitask_2026_05_07" / "predictions.json"
# qgi-data canonical mirror used by Stage 5 paper for buyer disclosure
D5_PREDICTIONS_QGI_DATA = REPO_ROOT.parent / "qgi-data" / "reference" / "d5-d7-beta-validation-results-2026-05-07.json"


def _load_d5_predictions() -> list[dict]:
    """Load D5 predictions from the qgi-data canonical mirror (preferred)
    or the qgi-ml local copy as fallback."""
    for p in (D5_PREDICTIONS_QGI_DATA, D5_PREDICTIONS_LOCAL):
        if p.exists():
            payload = json.loads(p.read_text(encoding="utf-8"))
            return payload.get("predictions", payload if isinstance(payload, list) else [])
    pytest.skip(f"D5 predictions JSON not found at {D5_PREDICTIONS_QGI_DATA} or {D5_PREDICTIONS_LOCAL}")


def _bootstrap_auc_ci(probs: np.ndarray, labels: np.ndarray, n_boot: int = 200, seed: int = 0) -> tuple[float, float, float]:
    """Bootstrap AUC + 95% CI; matches the convention used in the walk reports."""
    point = roc_auc_score(labels, probs)
    rng = np.random.default_rng(seed)
    aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(labels), size=len(labels))
        if labels[idx].sum() in (0, len(idx)):
            continue
        try:
            aucs.append(roc_auc_score(labels[idx], probs[idx]))
        except Exception:
            continue
    lo = float(np.percentile(aucs, 2.5)) if aucs else float("nan")
    hi = float(np.percentile(aucs, 97.5)) if aucs else float("nan")
    return point, lo, hi


# ---- Dispatch table: f_rule_anomaly flag is locked in ------------------------


def test_dispatch_marks_epidemic_and_pandemic_as_f_rule_anomaly():
    """The dispatch JSON marks epidemic_and_pandemic with f_rule_anomaly=true.

    Pending Majles clarification on hybrid F-rule applicability, this flag
    is the binding contract for downstream Stage 4 production-walk code.
    """
    dispatch = load_dispatch()
    a = dispatch.assignment_for("epidemic_and_pandemic")
    assert a.f_rule_anomaly is True, (
        "epidemic_and_pandemic must be flagged f_rule_anomaly=True in the "
        "dispatch table until Majles resolves the hybrid F-rule applicability "
        "ambiguity. If you're seeing this fail, a model update or dispatch "
        "edit may have removed the flag without re-pre-registration."
    )


def test_dispatch_marks_territorial_disputes_as_falsified():
    """Per KI-2 Majles amendment 2026-05-11 (Option C carried 3-1):
    territorial_disputes is FALSIFIED under hybrid due to degenerate D5
    predictions. It must appear in the falsified list, NOT in assignments.

    Replaces the prior test_dispatch_marks_territorial_disputes_as_f_rule_anomaly
    which assumed the recipe was LOCKED with anomaly flag.
    """
    dispatch = load_dispatch()
    falsified = dispatch.falsified_recipes()
    assert "territorial_disputes" in falsified, (
        "territorial_disputes must be in the falsified list per KI-2 "
        "Majles amendment 2026-05-11. If you're seeing this fail, a dispatch "
        "edit may have moved the recipe back to assignments without "
        "re-pre-registration."
    )
    locked = dispatch.locked_recipes()
    assert "territorial_disputes" not in locked, (
        "territorial_disputes must NOT be in the LOCKED set per KI-2 "
        "amendment. Recipe is FALSIFIED under hybrid."
    )


def test_dispatch_exactly_one_f_rule_anomaly():
    """Exactly 1 recipe (epidemic_and_pandemic) has f_rule_anomaly=True
    after KI-2 amendment 2026-05-11 dropped territorial_disputes from the
    LOCKED set via FALSIFICATION.

    Also asserts the locked_recipes() count is the expected 13 — this guards
    against a silent regression where a recipe is moved into/out of the
    LOCKED set, which would let an f_rule_anomaly count change pass
    undetected.
    """
    dispatch = load_dispatch()
    locked = dispatch.locked_recipes()
    assert len(locked) == 13, (
        f"Expected 13 LOCKED recipes per hybrid pre-reg (post-KI-2 amendment "
        f"2026-05-11 — territorial_disputes FALSIFIED); got {len(locked)}. "
        f"A recipe being moved into or out of the LOCKED set would let the "
        f"f_rule_anomaly count silently pass even if a new anomaly is "
        f"introduced. Any change to the LOCKED set requires Majles "
        f"re-pre-registration."
    )
    anomalies = [r for r in locked if dispatch.has_f_rule_anomaly(r)]
    assert sorted(anomalies) == ["epidemic_and_pandemic"], (
        f"Expected exactly 1 f_rule_anomaly recipe (epidemic_and_pandemic) "
        f"after KI-2 amendment; got {sorted(anomalies)}. Any change to this "
        f"set requires Majles re-pre-registration."
    )


def test_dispatch_negative_lock_human_rights_violation_no_anomaly():
    """Negative lock: human_rights_violation has n_pos_loco=1 + D5-assigned
    but f_rule_anomaly is False (in-sample F2 passes for this recipe under D5).

    Per QA PR #42 review N4: without this negative lock, a future JSON
    edit flipping human_rights_violation's f_rule_anomaly to True would not
    be caught by the count test alone (which expects 2 anomalies; 3 would
    fail loudly, but a 2-flip swap would not).
    """
    dispatch = load_dispatch()
    a = dispatch.assignment_for("human_rights_violation")
    # Confirm the structural setup that makes this a meaningful negative lock
    assert a.architecture == "D5"
    assert a.n_pos_loco == 1
    assert a.advisory_only is True  # n_pos=1 → ADVISORY-ONLY
    # The negative lock itself
    assert a.f_rule_anomaly is False, (
        "human_rights_violation must NOT be flagged f_rule_anomaly per "
        "Stage 5 paper finding (in-sample F2 passes under D5 with AUC 0.8378). "
        "If you're seeing this fail, a JSON edit may have incorrectly added "
        "the flag — requires Majles re-pre-registration."
    )


# ---- Empirical state: in-sample F2 fails for these 2 recipes ----------------


def test_epidemic_and_pandemic_in_sample_f2_fails_under_d5():
    """Documented Stage 5 finding: epidemic_and_pandemic in-sample F2 fails
    under D5 (AUC < 0.57; CI does not exclude 0.5). Locks this state until
    Majles resolves.
    """
    preds = _load_d5_predictions()
    rps = [p for p in preds if p["recipe_id"] == "epidemic_and_pandemic"]
    if not rps:
        pytest.skip("epidemic_and_pandemic not in D5 predictions")
    probs = np.array([p["predicted_probability"] for p in rps])
    labels = np.array([p["label"] for p in rps])
    n_pos = int(labels.sum())
    auc, ci_lo, ci_hi = _bootstrap_auc_ci(probs, labels)

    # Documented values from Stage 5 paper tear-sheet
    assert n_pos == 2, f"expected n_pos_test=2; got {n_pos}"
    # F2 fails on point estimate
    assert auc < 0.57, (
        f"epidemic_and_pandemic in-sample F2 AUC = {auc:.4f}; expected < 0.57. "
        f"If F2 now passes, the documented F-rule anomaly status is invalidated "
        f"and the Stage 5 paper + dispatch flag require update via Majles."
    )
    # F2 fails on CI lower bound (CI does not exclude 0.5)
    assert ci_lo <= 0.5, (
        f"epidemic_and_pandemic in-sample F2 CI lower = {ci_lo:.4f}; expected <= 0.5. "
        f"If CI now excludes 0.5, the F-rule anomaly is partially resolved; "
        f"Stage 5 disclosure needs Majles update."
    )


def test_territorial_disputes_in_sample_f2_fails_under_d5():
    """Documented Stage 5 finding: territorial_disputes in-sample F2 fails
    under D5 (AUC < 0.57; CI does not exclude 0.5). Predictions collapse
    to near-zero per Stage 5 paper Section 4.
    """
    preds = _load_d5_predictions()
    rps = [p for p in preds if p["recipe_id"] == "territorial_disputes"]
    if not rps:
        pytest.skip("territorial_disputes not in D5 predictions")
    probs = np.array([p["predicted_probability"] for p in rps])
    labels = np.array([p["label"] for p in rps])
    n_pos = int(labels.sum())
    auc, ci_lo, ci_hi = _bootstrap_auc_ci(probs, labels)

    assert n_pos == 2
    assert auc < 0.57, (
        f"territorial_disputes in-sample F2 AUC = {auc:.4f}; expected < 0.57."
    )
    assert ci_lo <= 0.5

    # Stage 5 paper explicitly documents that predictions collapse to near-zero
    # for this recipe under D5 (max ~1.91e-6; both positives at exactly 0.0).
    # Lock this state — a future change that produces meaningful probabilities
    # would partially resolve the anomaly and require Majles update.
    assert probs.max() < 1e-3, (
        f"territorial_disputes D5 predictions max = {probs.max():.2e}; expected "
        f"< 1e-3 per Stage 5 paper (predictions collapse to near-zero under D5). "
        f"If max prob is now >= 1e-3, the documented 'degenerate output' anomaly "
        f"is partially resolved; Stage 5 disclosure needs Majles update."
    )


def test_epidemic_and_pandemic_loco_strong_tier_via_dispatch():
    """The hybrid tier (STRONG) for epidemic_and_pandemic rests on LOCO,
    not in-sample F2. Confirm dispatch encodes this."""
    dispatch = load_dispatch()
    a = dispatch.assignment_for("epidemic_and_pandemic")
    assert a.tier == "STRONG"
    assert a.loco_auc >= 0.75  # STRONG tier threshold
    # Also confirm ADVISORY-ONLY (separate F-H-3 flag; this recipe carries both)
    assert a.advisory_only is True


def test_territorial_disputes_not_in_assignments_post_ki2():
    """Per KI-2 Majles amendment 2026-05-11 (Option C carried 3-1):
    territorial_disputes is FALSIFIED under hybrid; recipe MUST NOT appear
    in dispatch.assignments (would mean it's a LOCKed candidate again).

    Replaces test_territorial_disputes_loco_moderate_tier_via_dispatch which
    asserted MODERATE-tier-via-dispatch — that assertion is no longer
    operative because the recipe is no longer in production assignments.
    """
    dispatch = load_dispatch()
    locked = dispatch.locked_recipes()
    assert "territorial_disputes" not in locked, (
        "territorial_disputes must NOT be in dispatch.assignments / "
        "locked_recipes() post-KI-2 amendment. Recipe is FALSIFIED under "
        "hybrid."
    )
    # Defensive: also confirm calling assignment_for() raises (since the
    # recipe isn't in assignments). This locks the contract that consumer
    # code can't get a stale RecipeAssignment for territorial_disputes.
    with pytest.raises(KeyError):
        dispatch.assignment_for("territorial_disputes")


# ---- F1 (calibration) still passes — these are F2-only anomalies -------------


def test_epidemic_and_pandemic_f1_still_passes_under_d5():
    """The F-rule anomaly is F2-only (discrimination); F1 (calibration) still
    passes. Locks this state to ensure future model updates don't
    accidentally regress F1 calibration on these recipes."""
    preds = _load_d5_predictions()
    rps = [p for p in preds if p["recipe_id"] == "epidemic_and_pandemic"]
    if not rps:
        pytest.skip("epidemic_and_pandemic not in D5 predictions")
    probs = np.array([p["predicted_probability"] for p in rps])
    labels = np.array([p["label"] for p in rps])
    ece = compute_ece(probs, labels, n_bins=10)
    assert ece <= 0.08, (
        f"epidemic_and_pandemic in-sample F1 ECE = {ece:.4f}; expected <= 0.08. "
        f"F1 must continue to pass even though F2 fails (anomaly is F2-only)."
    )


def test_territorial_disputes_f1_uninformative_under_degenerate_predictions():
    """F1 ECE is UNINFORMATIVE for territorial_disputes under D5.

    Per QA PR #42 review B1: when predictions collapse to ~0 across all
    test cells (territorial_disputes D5: max prob 1.91e-6; both positives at
    exactly 0.0), the ECE statistic is vacuously low — every observation
    falls into the first bin (lo=0.0), so ECE ≈ |observed_rate − 0| =
    n_pos/n ≈ 0.003. This passes ECE ≤ 0.08 trivially but tells you nothing
    about calibration quality.

    A Stage 4 reader could misread "F1 passes" as a genuine calibration
    green light. To avoid that misleading framing, this test does NOT assert
    a numerical ECE bound. Instead it documents the degenerate state as the
    Stage 5 paper does: ECE is technically below threshold but the
    discrimination metric (test_territorial_disputes_in_sample_f2_fails_
    under_d5) is the operative falsification disclosure.

    The degenerate-predictions lock is in
    test_territorial_disputes_in_sample_f2_fails_under_d5 (asserts
    probs.max() < 1e-3). That test is the operative lock on the disclosed
    state.
    """
    preds = _load_d5_predictions()
    rps = [p for p in preds if p["recipe_id"] == "territorial_disputes"]
    if not rps:
        pytest.skip("territorial_disputes not in D5 predictions")
    probs = np.array([p["predicted_probability"] for p in rps])
    # Just confirm the degenerate state; do NOT assert on ECE
    assert probs.max() < 1e-3, (
        "territorial_disputes D5 predictions should be degenerate (near-zero); "
        "if max prob is meaningful, the disclosed state has changed."
    )
