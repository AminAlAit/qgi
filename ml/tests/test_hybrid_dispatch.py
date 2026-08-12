"""Tests for `qgi_ml.src.hybrid_dispatch` (F-H-1 Orchestration Contract loader).

Per F-H-1 of `docs/specs/internal/ops/ml-track/stage-2-hybrid-d2-d5-walk-methodology-prereg.md`
(commit 7db3596): "any implementation PR that adds or modifies the
production-prediction pipeline MUST include a test that loads the
dispatch table and asserts each recipe routes to the correct frozen
backbone artifact. Test names must include
`test_hybrid_dispatch_routes_<recipe_id>` at minimum for the boundary
cases (`terrorist_attack`, `energy_policy`, `mass_protest`,
`multilateral_agreement`)."

This test module satisfies that requirement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from hybrid_dispatch import (  # noqa: E402
    DEFAULT_DISPATCH_PATH,
    HybridDispatch,
    assert_dispatch_invariants,
    load_dispatch,
)


# ---- F-H-1 routing tests (boundary cases required by pre-reg) ----------------


@pytest.fixture(scope="module")
def dispatch() -> HybridDispatch:
    return load_dispatch()


def test_hybrid_dispatch_routes_terrorist_attack(dispatch: HybridDispatch) -> None:
    """Boundary case (per F-H-1): n_pos_loco=1 D2-assigned with ADVISORY-ONLY."""
    a = dispatch.assignment_for("terrorist_attack")
    assert a.architecture == "D2"
    assert a.backbone_dir == "results/d2_d7_canonical_2026_05/backbone"
    assert a.tier == "STRONG"
    assert a.advisory_only is True
    assert a.n_pos_loco == 1


def test_hybrid_dispatch_routes_energy_policy(dispatch: HybridDispatch) -> None:
    """Boundary case (per F-H-1): n_pos_loco=1 D2-assigned with ADVISORY-ONLY + curation-flagged."""
    a = dispatch.assignment_for("energy_policy")
    assert a.architecture == "D2"
    assert a.backbone_dir == "results/d2_d7_canonical_2026_05/backbone"
    assert a.tier == "STRONG"
    assert a.advisory_only is True
    assert a.n_pos_loco == 1


def test_hybrid_dispatch_routes_mass_protest(dispatch: HybridDispatch) -> None:
    """Boundary case (per F-H-1): the F-D5-1 LEAK rescue case; D5-assigned MARGINAL."""
    a = dispatch.assignment_for("mass_protest")
    assert a.architecture == "D5"
    assert a.backbone_dir == "results/d5_backbones_2026_05_07/backbone"
    assert a.tier == "MARGINAL"
    assert a.advisory_only is False
    assert a.n_pos_loco == 2
    # Confirm the LEAK rescue: D5 LOCO >= 0.5
    assert a.loco_auc >= 0.5


def test_hybrid_dispatch_routes_multilateral_agreement(dispatch: HybridDispatch) -> None:
    """Boundary case (per F-H-1): D5 architecture-rescue case (D2 FALSIFIED -> D5 STRONG)."""
    a = dispatch.assignment_for("multilateral_agreement")
    assert a.architecture == "D5"
    assert a.backbone_dir == "results/d5_backbones_2026_05_07/backbone"
    assert a.tier == "STRONG"
    assert a.advisory_only is False
    assert a.n_pos_loco == 7
    assert a.loco_auc >= 0.75  # STRONG tier threshold


# ---- F-H-1 invariants -------------------------------------------------------


def test_dispatch_invariants_pass(dispatch: HybridDispatch) -> None:
    """The dispatch table must satisfy all F-H-1 invariants."""
    assert_dispatch_invariants(dispatch)


def test_dispatch_has_13_locked_recipes(dispatch: HybridDispatch) -> None:
    """Per hybrid pre-reg post-KI-2 amendment 2026-05-11: 13 LOCKED recipes
    (6 STRONG + 5 MODERATE + 2 MARGINAL). territorial_disputes FALSIFIED.
    """
    locked = dispatch.locked_recipes()
    assert len(locked) == 13
    assert len(dispatch.recipes_by_tier("STRONG")) == 6
    assert len(dispatch.recipes_by_tier("MODERATE")) == 5
    assert len(dispatch.recipes_by_tier("MARGINAL")) == 2


def test_dispatch_architecture_split(dispatch: HybridDispatch) -> None:
    """Hybrid post-KI-2: 7 D2-assigned + 6 D5-assigned = 13 LOCKs
    (territorial_disputes was D5-assigned; FALSIFIED 2026-05-11)."""
    assert len(dispatch.recipes_by_architecture("D2")) == 7
    assert len(dispatch.recipes_by_architecture("D5")) == 6


def test_dispatch_advisory_only_count(dispatch: HybridDispatch) -> None:
    """Per F-H-3: exactly 4 recipes have ADVISORY-ONLY flag (terrorist_attack,
    energy_policy, epidemic_and_pandemic, human_rights_violation)."""
    advisory = [r for r in dispatch.locked_recipes() if dispatch.is_advisory_only(r)]
    assert sorted(advisory) == sorted([
        "terrorist_attack", "energy_policy",
        "epidemic_and_pandemic", "human_rights_violation",
    ])


def test_dispatch_f_rule_anomaly_count(dispatch: HybridDispatch) -> None:
    """Per Stage 5 paper finding post-KI-2 amendment 2026-05-11: exactly 1
    recipe has F-rule anomaly under D5 (epidemic_and_pandemic).
    territorial_disputes was previously flagged but is now FALSIFIED."""
    anomalies = [r for r in dispatch.locked_recipes() if dispatch.has_f_rule_anomaly(r)]
    assert sorted(anomalies) == ["epidemic_and_pandemic"]


def test_dispatch_falsified_count(dispatch: HybridDispatch) -> None:
    """10 D2-eligible recipes are FALSIFIED (not LOCKed) post-KI-2 amendment;
    13 LOCKed + 10 FALSIFIED = 23 total."""
    falsified = dispatch.falsified_recipes()
    assert len(falsified) == 10
    assert len(dispatch.locked_recipes()) + len(falsified) == 23


def test_dispatch_falsified_recipes_have_no_assignment(dispatch: HybridDispatch) -> None:
    """FALSIFIED recipes raise KeyError on assignment lookup."""
    for rid in dispatch.falsified_recipes():
        with pytest.raises(KeyError, match="FALSIFIED"):
            dispatch.assignment_for(rid)


def test_dispatch_unknown_recipe_raises(dispatch: HybridDispatch) -> None:
    """Unknown recipes raise KeyError with the LOCKED list in the message."""
    with pytest.raises(KeyError, match="not in hybrid dispatch table"):
        dispatch.assignment_for("nonexistent_recipe_id")


# ---- F-H-1 runtime logging ---------------------------------------------------


def test_dispatch_sha256_deterministic(dispatch: HybridDispatch) -> None:
    """SHA-256 must be deterministic for the same dispatch table content."""
    sha1 = dispatch.sha256
    dispatch2 = load_dispatch()
    sha2 = dispatch2.sha256
    assert sha1 == sha2
    # SHA-256 hex digest is 64 chars
    assert len(sha1) == 64


def test_dispatch_runtime_log_entry_complete(dispatch: HybridDispatch) -> None:
    """F-H-1 runtime log MUST include all required fields:
    dispatch SHA + per-recipe (architecture, backbone_dir, backbone_dir_sha256,
    tier, advisory_only, f_rule_anomaly)."""
    log = dispatch.runtime_log_entry()
    assert "hybrid_dispatch_sha256" in log
    assert "pre_reg_lineage" in log
    assert "per_recipe_assignment" in log
    assert len(log["per_recipe_assignment"]) == 13  # post-KI-2 (territorial_disputes FALSIFIED)
    # Spot-check one entry — verify F-H-1 item 3 fields all present
    mp = log["per_recipe_assignment"]["mass_protest"]
    assert mp["architecture"] == "D5"
    assert mp["tier"] == "MARGINAL"
    assert mp["advisory_only"] is False
    assert mp["f_rule_anomaly"] is False
    assert "backbone_dir" in mp
    # backbone_dir_sha256 is a field; value may be None if backbone artifacts
    # not present locally (e.g., test runner doesn't have the .lgbm files)
    assert "backbone_dir_sha256" in mp


def test_dispatch_invariant_3_catches_n1_violation(tmp_path: Path) -> None:
    """Invariant 3 must catch a misconfigured advisory_only=False + n_pos_loco=1.

    Earlier loader version had a one-directional check that silently passed
    this misconfiguration. Per QA PR #41 review B1, the fix is a
    bidirectional biconditional. This regression test confirms the fix.

    Note: per F-H-3 operative carveout, the bidirectional rule is
    `advisory_only IFF n_pos_loco == 1`. The pre-reg's `n < 3` wording is
    inconsistent with its own carveout paragraph (which excludes n=2);
    invariant follows the operative carveout.
    """
    import json
    bad = {
        "schema_version": 1,
        "assignments": {
            "test_recipe": {
                "architecture": "D2",
                "backbone_dir": "results/test/backbone",
                "predictions_canonical": "test.json",
                "loco_auc": 0.7,
                "n_pos_loco": 1,  # == 1, should require advisory_only=True
                "tier": "STRONG",
                "assignment_confidence": "LOW",
                "advisory_only": False,  # WRONG per operative carveout
                "f_rule_anomaly": False,
                "notes": "test"
            }
        },
        "falsified": [],
        "metadata": {"n_locked": 1}
    }
    p = tmp_path / "bad_dispatch.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    dispatch = load_dispatch(p)
    with pytest.raises(AssertionError, match="F-H-3 operative carveout requires"):
        assert_dispatch_invariants(dispatch)


def test_dispatch_invariant_3_catches_inverse_violation(tmp_path: Path) -> None:
    """Inverse: advisory_only=True with n_pos_loco>=2 must also fail."""
    import json
    bad = {
        "schema_version": 1,
        "assignments": {
            "test_recipe": {
                "architecture": "D2",
                "backbone_dir": "results/test/backbone",
                "predictions_canonical": "test.json",
                "loco_auc": 0.7,
                "n_pos_loco": 5,  # >= 2, should require advisory_only=False
                "tier": "STRONG",
                "assignment_confidence": "HIGH",
                "advisory_only": True,  # WRONG per operative carveout
                "f_rule_anomaly": False,
                "notes": "test"
            }
        },
        "falsified": [],
        "metadata": {"n_locked": 1}
    }
    p = tmp_path / "bad_dispatch.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    dispatch = load_dispatch(p)
    with pytest.raises(AssertionError, match="F-H-3 operative carveout requires"):
        assert_dispatch_invariants(dispatch)


def test_dispatch_invariant_3_accepts_n2_with_advisory_false(tmp_path: Path) -> None:
    """The operative carveout: n_pos_loco=2 with advisory_only=False is VALID.

    Per the F-H-3 carveout paragraph, n_pos_loco=2 recipes escape the
    ADVISORY-ONLY restriction (the gate is operationally n_pos=1).
    This test confirms the invariant does NOT reject n=2 + non-advisory.
    """
    import json
    valid = {
        "schema_version": 1,
        "assignments": {
            "test_recipe": {
                "architecture": "D5",
                "backbone_dir": "results/test/backbone",
                "predictions_canonical": "test.json",
                "loco_auc": 0.6,
                "n_pos_loco": 2,  # = 2, carveout-escape per F-H-3
                "tier": "MARGINAL",
                "assignment_confidence": "LOW",
                "advisory_only": False,  # CORRECT per operative carveout
                "f_rule_anomaly": False,
                "notes": "test"
            }
        },
        "falsified": [],
        "metadata": {"n_locked": 1}
    }
    p = tmp_path / "good_dispatch.json"
    p.write_text(json.dumps(valid), encoding="utf-8")
    dispatch = load_dispatch(p)
    # Should NOT raise
    assert_dispatch_invariants(dispatch)


def test_dispatch_backbone_dir_sha256_returns_none_when_absent(dispatch: HybridDispatch) -> None:
    """backbone_dir_sha256 returns None when the artifact directory is not present.

    Production walks SHOULD assert this is not None at runtime to ensure
    F-H-1 compliance; the None return is expected in test environments
    where the .lgbm artifacts are not built locally. The HybridDispatch
    contract is that None signals 'not hashed' rather than raising — the
    caller decides whether to error.
    """
    # Hash from a non-existent directory should return None gracefully
    sha = dispatch.backbone_dir_sha256("civil_war_and_insurgency", repo_root=Path("/nonexistent"))
    assert sha is None


def test_dispatch_backbone_dir_sha256_computes_when_present(tmp_path: Path) -> None:
    """When the directory exists, backbone_dir_sha256 returns a deterministic SHA."""
    import json
    # Build a tiny fake backbone dir
    backbone_subdir = tmp_path / "results" / "test" / "backbone"
    backbone_subdir.mkdir(parents=True)
    (backbone_subdir / "a.lgbm").write_bytes(b"tree_a")
    (backbone_subdir / "b.lgbm").write_bytes(b"tree_b")
    # Build a fake dispatch JSON pointing at it
    bad = {
        "schema_version": 1,
        "assignments": {
            "test_recipe": {
                "architecture": "D2",
                "backbone_dir": "results/test/backbone",
                "predictions_canonical": "test.json",
                "loco_auc": 0.7,
                "n_pos_loco": 5,
                "tier": "STRONG",
                "assignment_confidence": "HIGH",
                "advisory_only": False,
                "f_rule_anomaly": False,
                "notes": "test"
            }
        },
        "falsified": [],
        "metadata": {"n_locked": 1}
    }
    p = tmp_path / "dispatch.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    dispatch = load_dispatch(p)
    sha = dispatch.backbone_dir_sha256("test_recipe", repo_root=tmp_path)
    assert sha is not None
    assert len(sha) == 64  # hex digest
    # Deterministic across calls
    sha2 = dispatch.backbone_dir_sha256("test_recipe", repo_root=tmp_path)
    assert sha == sha2


def test_dispatch_pre_reg_lineage_includes_hybrid(dispatch: HybridDispatch) -> None:
    """Pre-reg lineage must include all 4 binding pre-regs."""
    lineage = dispatch.pre_reg_lineage
    assert "hybrid" in lineage
    assert lineage["hybrid"] == "7db3596"
    assert "d5_walk" in lineage
    assert "tier_threshold" in lineage
    assert "d2_walk" in lineage


# ---- Schema validation ------------------------------------------------------


def test_dispatch_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    """Loader must refuse unknown schema versions (forward-compat guard)."""
    import json
    bad = {"schema_version": 99, "assignments": {}}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_dispatch(p)


def test_dispatch_default_path_resolves(dispatch: HybridDispatch) -> None:
    """Default dispatch path resolves to the committed canonical config."""
    assert DEFAULT_DISPATCH_PATH.exists()
    assert DEFAULT_DISPATCH_PATH.name == "hybrid_architecture_dispatch.json"
    assert DEFAULT_DISPATCH_PATH.parent.name == "config"
