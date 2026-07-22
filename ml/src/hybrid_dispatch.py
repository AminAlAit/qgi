"""Hybrid D2/D5 architecture dispatch table loader (F-H-1 Orchestration Contract).

Per docs/specs/internal/ops/ml-track/stage-2-hybrid-d2-d5-walk-methodology-prereg.md
(commit 7db3596) F-H-1: production prediction pipelines MUST consult the
dispatch table at run-start and route predictions through the per-recipe
assigned architecture. Mid-walk re-assignment is forbidden per F-H-5.

Usage::

    from hybrid_dispatch import HybridDispatch, load_dispatch
    dispatch = load_dispatch()  # loads config/hybrid_architecture_dispatch.json
    arch = dispatch.architecture_for("mass_protest")  # "D5"
    backbone_dir = dispatch.backbone_dir_for("civil_war_and_insurgency")
    advisory = dispatch.is_advisory_only("terrorist_attack")  # True
    for r in dispatch.locked_recipes(): ...

Production walks MUST also call ``dispatch.log_to_run_artifact(...)`` at
run-start to satisfy F-H-1's runtime-logging requirement.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Canonical schema version this loader supports
SUPPORTED_SCHEMA_VERSION = 1

# Resolve the canonical dispatch JSON path relative to repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DISPATCH_PATH = REPO_ROOT / "config" / "hybrid_architecture_dispatch.json"


@dataclass(frozen=True)
class RecipeAssignment:
    """Per-recipe architecture assignment from the dispatch table.

    All fields are pre-registered in the hybrid pre-reg (commit 7db3596)
    Architecture assignment table.
    """

    recipe_id: str
    architecture: str  # "D2" | "D5"
    backbone_dir: str  # path (relative to qgi-ml repo root)
    predictions_canonical: str  # path to canonical predictions JSON
    loco_auc: float
    n_pos_loco: int
    tier: str  # "STRONG" | "MODERATE" | "MARGINAL"
    assignment_confidence: str  # "HIGH" | "MODERATE" | "LOW"
    advisory_only: bool  # F-H-3 ADVISORY-ONLY flag (n_pos_loco < 3)
    f_rule_anomaly: bool  # True if in-sample F2 fails under assigned arch
    notes: str


class HybridDispatch:
    """In-memory dispatch table for F-H-1 production orchestration.

    Loads the canonical hybrid_architecture_dispatch.json and exposes typed
    query methods. Computes a SHA-256 of the source JSON for runtime logging
    so production runs can pin which dispatch table they consumed.
    """

    def __init__(self, payload: dict[str, Any], source_path: Path | None = None) -> None:
        self._payload = payload
        self._source_path = source_path
        if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
            msg = (
                f"hybrid_architecture_dispatch.json schema_version "
                f"{payload.get('schema_version')!r} != supported "
                f"{SUPPORTED_SCHEMA_VERSION}; loader will not interpret unknown schemas"
            )
            raise ValueError(msg)
        if "assignments" not in payload:
            raise ValueError("dispatch table missing 'assignments' key")
        self._assignments = {
            rid: RecipeAssignment(
                recipe_id=rid,
                architecture=row["architecture"],
                backbone_dir=row["backbone_dir"],
                predictions_canonical=row["predictions_canonical"],
                loco_auc=float(row["loco_auc"]),
                n_pos_loco=int(row["n_pos_loco"]),
                tier=row["tier"],
                assignment_confidence=row["assignment_confidence"],
                advisory_only=bool(row["advisory_only"]),
                f_rule_anomaly=bool(row["f_rule_anomaly"]),
                notes=row.get("notes", ""),
            )
            for rid, row in payload["assignments"].items()
        }
        self._falsified = set(payload.get("falsified", []))

    # ---- Properties ---------------------------------------------------------

    @property
    def schema_version(self) -> int:
        return self._payload["schema_version"]

    @property
    def filed(self) -> str:
        return self._payload.get("filed", "")

    @property
    def pre_reg_lineage(self) -> dict[str, str]:
        return dict(self._payload.get("pre_reg_lineage", {}))

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    @property
    def sha256(self) -> str:
        """SHA-256 of the canonical JSON content for runtime logging.

        Computed on a canonical serialization (sorted keys) so the SHA is
        deterministic across loaders. This is what production walks log
        per F-H-1's deployment-time verification check.
        """
        canonical = json.dumps(self._payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ---- Query methods ------------------------------------------------------

    def locked_recipes(self) -> tuple[str, ...]:
        """All LOCKED recipe IDs in stable order."""
        return tuple(sorted(self._assignments.keys()))

    def falsified_recipes(self) -> tuple[str, ...]:
        """All FALSIFIED recipe IDs (not part of production set)."""
        return tuple(sorted(self._falsified))

    def assignment_for(self, recipe_id: str) -> RecipeAssignment:
        """Get the full RecipeAssignment for a LOCKED recipe.

        Raises KeyError if recipe is not LOCKED (e.g., FALSIFIED recipes
        do not have hybrid assignments).
        """
        if recipe_id not in self._assignments:
            if recipe_id in self._falsified:
                msg = (
                    f"recipe {recipe_id!r} is FALSIFIED; not part of hybrid LOCKED "
                    f"set. FALSIFIED recipes have no production architecture."
                )
            else:
                msg = (
                    f"recipe {recipe_id!r} not in hybrid dispatch table; "
                    f"valid LOCKED recipes: {self.locked_recipes()}"
                )
            raise KeyError(msg)
        return self._assignments[recipe_id]

    def architecture_for(self, recipe_id: str) -> str:
        """Return 'D2' or 'D5' for a LOCKED recipe."""
        return self.assignment_for(recipe_id).architecture

    def backbone_dir_for(self, recipe_id: str) -> str:
        return self.assignment_for(recipe_id).backbone_dir

    def predictions_canonical_for(self, recipe_id: str) -> str:
        return self.assignment_for(recipe_id).predictions_canonical

    def is_advisory_only(self, recipe_id: str) -> bool:
        """F-H-3 ADVISORY-ONLY flag (n_pos_loco < 3)."""
        return self.assignment_for(recipe_id).advisory_only

    def has_f_rule_anomaly(self, recipe_id: str) -> bool:
        """True if in-sample F2 fails under assigned architecture."""
        return self.assignment_for(recipe_id).f_rule_anomaly

    def recipes_by_architecture(self, architecture: str) -> tuple[str, ...]:
        """All LOCKED recipes assigned to the given architecture."""
        return tuple(sorted(
            rid for rid, a in self._assignments.items()
            if a.architecture == architecture
        ))

    def recipes_by_tier(self, tier: str) -> tuple[str, ...]:
        """All LOCKED recipes at the given tier."""
        return tuple(sorted(
            rid for rid, a in self._assignments.items() if a.tier == tier
        ))

    # ---- Runtime logging (F-H-1 production-walk requirement) -----------------

    @staticmethod
    def _hash_directory(dir_path: Path) -> str | None:
        """SHA-256 over the deterministic-sorted concatenation of file SHAs.

        For backbone_dir hashing (F-H-1 item 3 requirement). Returns None if
        the directory does not exist (e.g., backbone artifacts not yet built
        locally). Returns the hex digest as a string otherwise.

        Determinism: file paths are sorted before hashing; each file's bytes
        are hashed, then the per-file digests are concatenated in path order
        and hashed again. This yields a stable directory-content fingerprint
        regardless of filesystem traversal order.
        """
        if not dir_path.exists() or not dir_path.is_dir():
            return None
        file_digests = []
        for fp in sorted(dir_path.rglob("*")):
            if not fp.is_file():
                continue
            h = hashlib.sha256()
            h.update(str(fp.relative_to(dir_path)).encode("utf-8"))
            h.update(b"\x00")
            h.update(fp.read_bytes())
            file_digests.append(h.hexdigest())
        if not file_digests:
            return None
        combined = hashlib.sha256()
        for d in file_digests:
            combined.update(d.encode("ascii"))
        return combined.hexdigest()

    def backbone_dir_sha256(self, recipe_id: str, repo_root: Path | None = None) -> str | None:
        """SHA-256 of the backbone_dir contents for a LOCKED recipe.

        Returns None if the directory does not exist (typical when running
        outside the qgi-ml repo or before backbones have been trained
        locally). Production walks MUST verify this returns a real SHA
        before claiming F-H-1 compliance.

        Per F-H-1 item 3 (Orchestration Contract): backbone_dir SHA must be
        logged alongside dispatch-table SHA.
        """
        a = self.assignment_for(recipe_id)
        root = repo_root or REPO_ROOT
        return self._hash_directory(root / a.backbone_dir)

    def runtime_log_entry(self, repo_root: Path | None = None) -> dict[str, Any]:
        """Return the F-H-1 runtime-log record a production walk MUST emit.

        Per F-H-1's Orchestration Implementation Contract: every production
        walk MUST log the dispatch-table SHA + per-recipe architecture
        assignment + backbone_dir SHA to its run artifact.

        ``repo_root`` allows callers to point the backbone_dir hashing at a
        non-default location (e.g., when running from a packaged deployment).
        Per-recipe backbone_dir_sha256 is None if the directory is not
        present at hash time — production walks SHOULD assert this is not
        None at runtime (see ``runtime_log_assert_compliance`` for the
        production-walk callsite pattern).
        """
        return {
            "hybrid_dispatch_sha256": self.sha256,
            "hybrid_dispatch_source_path": (
                str(self._source_path) if self._source_path else None
            ),
            "hybrid_dispatch_schema_version": self.schema_version,
            "pre_reg_lineage": self.pre_reg_lineage,
            "per_recipe_assignment": {
                rid: {
                    "architecture": a.architecture,
                    "backbone_dir": a.backbone_dir,
                    "backbone_dir_sha256": self.backbone_dir_sha256(rid, repo_root),
                    "tier": a.tier,
                    "advisory_only": a.advisory_only,
                    "f_rule_anomaly": a.f_rule_anomaly,
                }
                for rid, a in self._assignments.items()
            },
        }


def load_dispatch(path: Path | None = None) -> HybridDispatch:
    """Load the canonical hybrid dispatch table.

    Defaults to ``qgi-ml/config/hybrid_architecture_dispatch.json``.
    """
    p = path or DEFAULT_DISPATCH_PATH
    payload = json.loads(p.read_text(encoding="utf-8"))
    return HybridDispatch(payload, source_path=p)


# F-H-1 item 4 — Deployment-time SHA verification
#
# The hybrid pre-reg specifies: "at production deploy, a verification script
# must compare the dispatch-table SHA against the latest pre-reg-merged
# commit's expected SHA. Mismatch blocks deploy."
#
# ACTIVE — implemented in scripts/verify_dispatch_sha.py and wired into CI
# via .github/workflows/verify-dispatch-sha.yml (ticket #648, 2026-05-11).
# The deploy script runs both the SHA pin check AND assert_dispatch_invariants
# below; either failing blocks deploy. Rotation procedure: every dispatch JSON
# amendment must update EXPECTED_DISPATCH_SHA in the deploy script in the same
# PR as a NEW F-H-4 pre-reg amendment.
#
# runtime_log_entry() still emits the SHA for forensic inspection.


def assert_dispatch_invariants(dispatch: HybridDispatch) -> None:
    """Assert the F-H-1 invariants that the dispatch table must satisfy.

    Production walk scripts SHOULD call this at run-start. Raises
    AssertionError on any violation; the runtime is expected to abort
    rather than silently proceed.
    """
    # Invariant 1: every LOCKED recipe has architecture in {D2, D5}
    for rid in dispatch.locked_recipes():
        a = dispatch.assignment_for(rid)
        assert a.architecture in ("D2", "D5"), (
            f"recipe {rid} has invalid architecture {a.architecture!r}"
        )

    # Invariant 2: tier is in canonical set
    for rid in dispatch.locked_recipes():
        a = dispatch.assignment_for(rid)
        assert a.tier in ("STRONG", "MODERATE", "MARGINAL"), (
            f"recipe {rid} has invalid tier {a.tier!r}"
        )

    # Invariant 3: ADVISORY-ONLY iff n_pos_loco == 1 (F-H-3 operative carveout,
    # bidirectional)
    #
    # PRE-REG WORDING INCONSISTENCY (flagged for next Majles clarification):
    # F-H-3's rule statement says "n_pos_total < 3" but its carveout paragraph
    # explicitly excludes n_pos=2 recipes ("Recipes with n_pos_LOCO = 2 ...
    # escape the strictest ADVISORY-ONLY pricing restriction"). The two
    # paragraphs are mathematically inconsistent because 2 < 3 is true.
    #
    # OPERATIVE RULE (what the dispatch table encodes, what the Stage 5 paper
    # and the pre-reg's enumeration of affected recipes both reflect):
    #   advisory_only == True  ↔  n_pos_loco == 1
    #   advisory_only == False ↔  n_pos_loco >= 2
    #
    # Affected n_pos_loco = 1 recipes (4): terrorist_attack, energy_policy,
    # epidemic_and_pandemic, human_rights_violation
    # Escaped n_pos_loco = 2 recipes (3): peacekeeping_and_peace_process,
    # territorial_disputes, mass_protest
    #
    # QA PR #41 review caught that the earlier single-direction invariant
    # silently allowed advisory_only=False with n_pos_loco<3. The fix went
    # bidirectional but then exposed this pre-reg wording inconsistency.
    # Encoding the operative rule here; the wording cleanup is a follow-up
    # Majles amendment.
    for rid in dispatch.locked_recipes():
        a = dispatch.assignment_for(rid)
        expected_advisory = a.n_pos_loco == 1
        assert a.advisory_only == expected_advisory, (
            f"recipe {rid}: advisory_only={a.advisory_only} inconsistent with "
            f"n_pos_loco={a.n_pos_loco}. F-H-3 operative carveout requires "
            f"advisory_only IFF n_pos_loco == 1 (pre-reg wording 'n < 3' has "
            f"a carveout that excludes n=2; see PR #41 review and source "
            f"comments for the inconsistency)."
        )

    # Invariant 4: Assignment confidence is canonical
    for rid in dispatch.locked_recipes():
        a = dispatch.assignment_for(rid)
        assert a.assignment_confidence in ("HIGH", "MODERATE", "LOW"), (
            f"recipe {rid} has invalid Assignment confidence {a.assignment_confidence!r}"
        )

    # Invariant 5: LOCKED + FALSIFIED partition is disjoint
    locked = set(dispatch.locked_recipes())
    falsified = set(dispatch.falsified_recipes())
    overlap = locked & falsified
    assert not overlap, (
        f"recipes appear in both LOCKED and FALSIFIED sets: {overlap}"
    )

    # Invariant 6: LOCKED count matches the metadata claim
    n_locked_meta = dispatch._payload.get("metadata", {}).get("n_locked")
    if n_locked_meta is not None:
        assert n_locked_meta == len(locked), (
            f"metadata.n_locked={n_locked_meta} != actual {len(locked)}"
        )
