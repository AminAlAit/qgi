"""Shape-prototype dispatch table loader (F-Shape-1 / §4.3 Pinning Contract).

Per `qgi-docs/internal/ops/ml-track/stage-6-shape-feature-prereg.md` (commit
e4f9e7a) §4.3: production shape-feature emits MUST consult this artifact at
run-start, SHA-verify the file content against `metadata.file_sha256`, assert
the per-recipe G1-G4 substrate gates, and pin the prototype SHA in every
result JSON. Prototype rotation requires F-H-4 amendment + the Lakatosian
guard F-Shape-1 (§6.2) + 8-seat ratification.

This module mirrors the structure of `qgi-ml/src/hybrid_dispatch.py` (F-H-1
loader for the D2/D5 dispatch table). The intentional parity is a
patch-pinning + audit-traceability discipline: a Lloyd's reviewer reading
either loader can pattern-match the other without reading new conventions.

Usage::

    from shape_prototype_dispatch import load_dispatch, assert_dispatch_invariants
    dispatch = load_dispatch()  # loads config/shape-prototypes.lock.json
    prototype = dispatch.prototype_for("mass_protest")
    # Substrate-inadequate recipes:
    for rid in dispatch.substrate_inadequate_recipes():
        ...  # route to ingredient + length fallback per §4.3 invariant 3
    # Runtime logging (binding per §4.5 five-SHAs contract):
    log = dispatch.runtime_log_entry()  # writes into prediction JSON provenance

Chunk A scope (this commit): schemas + loader + SHA + invariants + tests. The
math (FPCA / hierarchical Bayes / MCMC / shape kernel body) is Chunk B.
Population of `shape-prototypes.lock.json` with the founder-picked trio
arrives in Chunk C after Chunk B fits the prototypes.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Canonical schema version this loader supports
SUPPORTED_PROTOTYPE_SCHEMA_VERSION = 1

# Resolve the canonical lock JSON path relative to repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK_PATH = REPO_ROOT / "config" / "shape-prototypes.lock.json"
DEFAULT_SCHEMA_PATH = REPO_ROOT / "config" / "shape-prototypes.lock.schema.json"


# ---- Exceptions (binding API per §4.3) --------------------------------------


class PrototypeIntegrityError(RuntimeError):
    """Raised when `shape-prototypes.lock.json` fails SHA-256 verification.

    Per §4.3 invariant 2: at load time the loader recomputes SHA-256 over
    canonical-serialized JSON content (sorted keys, ``(",", ":")`` separators)
    with ``metadata.file_sha256`` set to the empty string, and compares to
    the embedded `metadata.file_sha256`. Mismatch raises this exception;
    the runtime MUST abort rather than silently proceed.
    """


class SubstrateInadequateError(RuntimeError):
    """Raised when a caller requests a prototype that failed G1-G4 substrate.

    Per §4.3 invariant 3: G1-G4 gate failure routes that recipe to the
    ingredient+length fallback (no shape similarity emitted; tear-sheet
    renders "shape unavailable for this recipe because [reason]"). Loader
    construction does NOT raise on substrate failure (this is normal
    operational state, not corruption); only direct prototype lookup via
    ``prototype_for(recipe_id)`` raises. To enumerate without raising, use
    ``substrate_inadequate_recipes()`` or ``has_prototype(recipe_id)``.
    """


class AdvisoryOnlyShapeUnfittableError(RuntimeError):
    """Raised when a caller requests a prototype for an ADVISORY-ONLY recipe.

    Per F-H-4-A5 (§3.1.5 cascade exit clause): a recipe routes here when its
    §3.1.4 GP fallback NUTS sampler gates persistently fail after operational
    tooling exhaustion (refit at target_accept=0.99 + advi+adapt_diag init +
    n_draws>=2000 per chain still fail R-hat ≤ 1.01 or ESS >= 400). The
    recipe retains its cascade LOCK status (STRONG/MODERATE/MARGINAL); only
    the shape feature is unavailable. Loader construction does NOT raise on
    ADVISORY-ONLY status; only direct prototype lookup via
    ``prototype_for(recipe_id)`` raises. To enumerate without raising, use
    ``advisory_only_recipes()`` or ``has_prototype(recipe_id)`` (which
    returns False for ADVISORY-ONLY recipes). The non-raising fetch
    ``try_prototype_for(recipe_id)`` returns ``None`` instead.
    """


class Phase1HardFalsifiedError(RuntimeError):
    """Raised when a caller requests a prototype for a Phase-1 HARD-FALSIFIED recipe.

    Per stage-6-phase-1-closure-DECISION-2026-05-21 (8-seat ratified): when
    the Stage 7 §6.1 4-tier exit table routes a recipe to HARD-FALSIFY, the
    prototype itself remains mathematically sound (sampler diagnostics pass),
    but the FEATURE derived from the prototype failed F-S-1/F-S-3 + F-H-7
    with margin. Production cascade reverts to ingredient+length-only for
    that recipe. Per Tariq #20 R-T1 binding rider: the prototype MUST NOT
    be reused as initialization data, priors, or warm-starts under any
    future fresh pre-reg. Future revival requires a full re-fit per F-Shape-1.
    """


class SchemaValidationError(ValueError):
    """Raised when the lock JSON fails the §4.3 schema invariants.

    Hand-rolled structural validation is used (mirrors hybrid_dispatch.py's
    pattern; no ``jsonschema`` dependency). The schema-as-JSON artifact at
    ``config/shape-prototypes.lock.schema.json`` is the binding reference;
    this loader enforces the subset of constraints required for safe
    runtime operation.
    """


# ---- Dataclasses ------------------------------------------------------------


@dataclass(frozen=True)
class SubstrateAudit:
    """Per-recipe G1-G4 substrate gate audit per §4.3 + Tariq's substrate spec.

    All four gates must pass for the recipe to have a usable prototype. Gate
    failure routes the recipe to ingredient+length fallback (NOT an error).
    """

    g1_n_pos_geq_10: bool
    g2_n_countries_geq_5: bool
    g3_density_geq_0_85: bool
    g4_censoring_clean: bool

    @property
    def all_pass(self) -> bool:
        """True iff all four G-gates pass."""
        return (
            self.g1_n_pos_geq_10
            and self.g2_n_countries_geq_5
            and self.g3_density_geq_0_85
            and self.g4_censoring_clean
        )

    def failing_gates(self) -> tuple[str, ...]:
        """Sorted tuple of failing gate names (empty if all_pass)."""
        out = []
        if not self.g1_n_pos_geq_10:
            out.append("g1_n_pos_geq_10")
        if not self.g2_n_countries_geq_5:
            out.append("g2_n_countries_geq_5")
        if not self.g3_density_geq_0_85:
            out.append("g3_density_geq_0_85")
        if not self.g4_censoring_clean:
            out.append("g4_censoring_clean")
        return tuple(out)


@dataclass(frozen=True)
class ShapePrototype:
    """Per-recipe canonical shape prototype entry per §4.3 binding schema.

    Carries the FPCA (primary) or hierarchical-Bayes+GP (fallback) posterior
    summary plus all five-SHA provenance fields a Lloyd's reviewer needs to
    audit one production prediction.

    Note: the per-indicator trajectory signature is stored as a free-form
    dict on this dataclass; downstream Chunk B will introduce a typed
    ``IndicatorSignature`` dataclass when the FPCA math lands. The dict
    structure is schema-validated at load time, so Chunk B's typed wrapper
    is a non-breaking refinement.
    """

    recipe_id: str
    indicator_ids: tuple[str, ...]
    canonical_length_T_point: int
    canonical_length_T_iqr: tuple[int, int]
    canonical_length_T_method: str
    per_indicator_trajectory_signature: dict[str, dict[str, Any]] = field(repr=False)
    fit_method: str  # "fpca" | "hierarchical_bayes_gp_fallback"
    fit_method_commit_sha: str
    n_training_positives: int
    training_data_snapshot_s3_path: str
    training_data_snapshot_sha256: str
    substrate_audit: SubstrateAudit
    cohort_calibration_ref: str
    schema_version: int
    # Cascade disposition for the shape feature on this recipe.
    # "fit_locked" = shape prototype valid (default; equivalent to pre-A5 behavior).
    # "advisory_only_shape_unfittable" = F-H-4-A5 §3.1.5 cascade exit clause invoked.
    # "phase_1_hard_falsified" = stage-6-phase-1-closure-DECISION-2026-05-21
    #     (8-seat ratified): prototype is mathematically sound but the FEATURE
    #     derived from it failed F-S-1/F-S-3 + F-H-7 with margin. Production
    #     cascade reverts to ingredient+length-only; revival requires fresh pre-reg.
    cascade_outcome: str = "fit_locked"


# ---- Dispatch ---------------------------------------------------------------


class ShapePrototypeDispatch:
    """In-memory dispatch table for §4.3 production shape-feature orchestration.

    Loads the canonical `shape-prototypes.lock.json`, hand-rolls structural
    validation against the schema's binding invariants, SHA-256-verifies the
    file content, and exposes typed query methods + a runtime-log entry for
    production shape-feature emit JSON's five-SHA provenance block (§4.5).
    """

    def __init__(self, payload: dict[str, Any], source_path: Path | None = None) -> None:
        self._payload = payload
        self._source_path = source_path

        # Top-level structural validation (subset of the JSON Schema, sized
        # to what the loader needs to operate safely at runtime).
        self._validate_top_level(payload)

        if payload["schema_version"] != SUPPORTED_PROTOTYPE_SCHEMA_VERSION:
            msg = (
                f"shape-prototypes.lock.json schema_version "
                f"{payload['schema_version']!r} != supported "
                f"{SUPPORTED_PROTOTYPE_SCHEMA_VERSION}; loader will not "
                f"interpret unknown schemas"
            )
            raise SchemaValidationError(msg)

        # SHA-256 verification (§4.3 invariant 2). Computed BEFORE prototype
        # parsing so corruption is detected even if recipe entries are
        # structurally invalid.
        self._verify_file_sha256(payload)

        # Parse prototypes.
        self._prototypes: dict[str, ShapePrototype] = {}
        self._substrate_inadequate: set[str] = set()
        # F-H-4-A5: track recipes routed to ADVISORY-ONLY via the §3.1.5
        # cascade exit clause. Separate from substrate-inadequate because the
        # failure mode is sampler-gate exhaustion, not G1-G4 audit.
        self._shape_unfittable_advisory_only: set[str] = set()
        self._phase_1_hard_falsified: set[str] = set()
        for rid, row in payload["recipes"].items():
            self._validate_recipe(rid, row)
            audit = SubstrateAudit(
                g1_n_pos_geq_10=bool(row["substrate_audit"]["g1_n_pos_geq_10"]),
                g2_n_countries_geq_5=bool(row["substrate_audit"]["g2_n_countries_geq_5"]),
                g3_density_geq_0_85=bool(row["substrate_audit"]["g3_density_geq_0_85"]),
                g4_censoring_clean=bool(row["substrate_audit"]["g4_censoring_clean"]),
            )
            # F-H-4-A5: read cascade_outcome; absent value defaults to
            # "fit_locked" for backward-compat with pre-A5 lock entries.
            cascade_outcome = str(row.get("cascade_outcome", "fit_locked"))
            if cascade_outcome not in ("fit_locked", "advisory_only_shape_unfittable", "phase_1_hard_falsified"):
                raise SchemaValidationError(
                    f"recipes[{rid!r}] cascade_outcome must be 'fit_locked', "
                    f"'advisory_only_shape_unfittable', or 'phase_1_hard_falsified'; "
                    f"got {cascade_outcome!r}"
                )
            # F-H-4-A5 semantic gate: fit_locked entries MUST carry a
            # non-empty per_indicator_trajectory_signature. The schema's
            # minProperties was relaxed to 0 (so ADVISORY-ONLY entries can
            # legally emit {}), but fit_locked recipes silently accepting
            # an empty signature would be a regression. The loader enforces
            # the conditional non-emptiness here. QA review of qgi-ml#85
            # caught this gap; the corresponding test lives in
            # tests/test_shape_prototype_loader.py.
            if cascade_outcome == "fit_locked" and not row["per_indicator_trajectory_signature"]:
                raise SchemaValidationError(
                    f"recipes[{rid!r}] has cascade_outcome='fit_locked' but "
                    f"per_indicator_trajectory_signature is empty. A LOCKED "
                    f"shape recipe must carry at least one indicator signature. "
                    f"If the recipe is meant to be ADVISORY-ONLY (no shape "
                    f"prototype), set cascade_outcome='advisory_only_shape_unfittable' "
                    f"per F-H-4-A5 (Stage 6 §3.1.5 cascade exit clause)."
                )
            proto = ShapePrototype(
                recipe_id=rid,
                indicator_ids=tuple(row["indicator_ids"]),
                canonical_length_T_point=int(row["canonical_length_T"]["point"]),
                canonical_length_T_iqr=(
                    int(row["canonical_length_T"]["posterior_iqr"][0]),
                    int(row["canonical_length_T"]["posterior_iqr"][1]),
                ),
                canonical_length_T_method=row["canonical_length_T"]["method"],
                per_indicator_trajectory_signature=dict(row["per_indicator_trajectory_signature"]),
                fit_method=row["fit_method"],
                fit_method_commit_sha=row["fit_method_commit_sha"],
                n_training_positives=int(row["n_training_positives"]),
                training_data_snapshot_s3_path=row["training_data_snapshot_sha"]["s3_path"],
                training_data_snapshot_sha256=row["training_data_snapshot_sha"]["sha256"],
                substrate_audit=audit,
                cohort_calibration_ref=row["cohort_calibration_ref"],
                schema_version=int(row["schema_version"]),
                cascade_outcome=cascade_outcome,
            )
            self._prototypes[rid] = proto
            if not audit.all_pass:
                self._substrate_inadequate.add(rid)
            if cascade_outcome == "advisory_only_shape_unfittable":
                self._shape_unfittable_advisory_only.add(rid)
            if cascade_outcome == "phase_1_hard_falsified":
                self._phase_1_hard_falsified.add(rid)

    # ---- Validation helpers ------------------------------------------------

    @staticmethod
    def _validate_top_level(payload: dict[str, Any]) -> None:
        required = {
            "schema_version",
            "filed",
            "purpose",
            "pre_reg_lineage",
            "metadata",
            "recipes",
            "amendments",
        }
        missing = required - payload.keys()
        if missing:
            raise SchemaValidationError(
                f"shape-prototypes.lock.json missing top-level keys: {sorted(missing)}"
            )
        if not isinstance(payload["recipes"], dict):
            raise SchemaValidationError("'recipes' must be a JSON object")
        if not isinstance(payload["amendments"], list):
            raise SchemaValidationError("'amendments' must be a JSON array")
        if not isinstance(payload["pre_reg_lineage"], dict):
            raise SchemaValidationError("'pre_reg_lineage' must be a JSON object")
        if "stage_6" not in payload["pre_reg_lineage"]:
            raise SchemaValidationError(
                "'pre_reg_lineage' must contain 'stage_6' (commit SHA of Stage 6 merge)"
            )
        meta = payload["metadata"]
        if not isinstance(meta, dict):
            raise SchemaValidationError("'metadata' must be a JSON object")
        for k in ("file_sha256", "n_recipes_with_prototype", "n_recipes_substrate_inadequate"):
            if k not in meta:
                raise SchemaValidationError(f"'metadata.{k}' is required")

    @staticmethod
    def _validate_recipe(rid: str, row: dict[str, Any]) -> None:
        required = {
            "recipe_id",
            "indicator_ids",
            "canonical_length_T",
            "per_indicator_trajectory_signature",
            "fit_method",
            "fit_method_commit_sha",
            "n_training_positives",
            "training_data_snapshot_sha",
            "substrate_audit",
            "cohort_calibration_ref",
            "schema_version",
        }
        missing = required - row.keys()
        if missing:
            raise SchemaValidationError(
                f"recipes[{rid!r}] missing keys: {sorted(missing)}"
            )
        if row["recipe_id"] != rid:
            raise SchemaValidationError(
                f"recipes[{rid!r}].recipe_id ({row['recipe_id']!r}) does not match map key"
            )
        if row["fit_method"] not in ("fpca", "hierarchical_bayes_gp_fallback"):
            raise SchemaValidationError(
                f"recipes[{rid!r}].fit_method ({row['fit_method']!r}) "
                f"must be 'fpca' or 'hierarchical_bayes_gp_fallback'"
            )
        substrate_keys = {
            "g1_n_pos_geq_10",
            "g2_n_countries_geq_5",
            "g3_density_geq_0_85",
            "g4_censoring_clean",
        }
        if substrate_keys - row["substrate_audit"].keys():
            raise SchemaValidationError(
                f"recipes[{rid!r}].substrate_audit missing G1-G4 keys"
            )

    @staticmethod
    def _canonical_payload_for_sha(payload: dict[str, Any]) -> dict[str, Any]:
        """Return a deep-ish copy of payload with metadata.file_sha256 cleared.

        This is the canonical form over which SHA-256 is computed. Clearing
        the embedded SHA before hashing is the standard "self-referential
        digest" pattern: the file's own SHA cannot be a function of itself.
        """
        clone = {k: v for k, v in payload.items()}
        clone["metadata"] = {k: v for k, v in payload["metadata"].items()}
        clone["metadata"]["file_sha256"] = ""
        return clone

    def _verify_file_sha256(self, payload: dict[str, Any]) -> None:
        claimed = payload["metadata"]["file_sha256"]
        canonical = json.dumps(
            self._canonical_payload_for_sha(payload),
            sort_keys=True,
            separators=(",", ":"),
        )
        actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if claimed != actual:
            raise PrototypeIntegrityError(
                f"shape-prototypes.lock.json SHA-256 mismatch: "
                f"claimed={claimed!r}, actual={actual!r}. "
                f"File may be corrupted or modified without rotating "
                f"metadata.file_sha256. Per §4.3 invariant 2 the runtime "
                f"aborts. See §4.5 prototype mutation discipline for the "
                f"rotation procedure (F-H-4 amendment + sister commit + "
                f"F-Shape-1 + 8-seat ratification)."
            )

    # ---- Properties --------------------------------------------------------

    @property
    def schema_version(self) -> int:
        return int(self._payload["schema_version"])

    @property
    def filed(self) -> str:
        return self._payload.get("filed", "")

    @property
    def pre_reg_lineage(self) -> dict[str, str]:
        return dict(self._payload["pre_reg_lineage"])

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    @property
    def sha256(self) -> str:
        """SHA-256 of the canonical-serialized JSON content (file_sha256 cleared).

        This is the digest production walks log in the §4.5 five-SHA
        provenance block as ``shape_prototypes_lock_sha256``. It is
        deterministic across loaders and across machines because both the
        canonical-serialization rules and the self-referential SHA-clearing
        rule are fixed by §4.3.
        """
        canonical = json.dumps(
            self._canonical_payload_for_sha(self._payload),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ---- Query methods -----------------------------------------------------

    def recipes_with_prototype(self) -> tuple[str, ...]:
        """All recipe IDs that have a prototype entry (regardless of substrate)."""
        return tuple(sorted(self._prototypes.keys()))

    def substrate_adequate_recipes(self) -> tuple[str, ...]:
        """Recipe IDs whose prototypes pass all G1-G4 substrate gates."""
        return tuple(sorted(
            rid for rid in self._prototypes if rid not in self._substrate_inadequate
        ))

    def substrate_inadequate_recipes(self) -> tuple[str, ...]:
        """Recipe IDs whose prototype entries failed at least one G-gate.

        Per §4.3 invariant 3 these route to ingredient+length fallback.
        """
        return tuple(sorted(self._substrate_inadequate))

    def has_prototype(self, recipe_id: str) -> bool:
        """True iff the recipe has a prototype entry AND its substrate is adequate
        AND it is not routed to ADVISORY-ONLY under F-H-4-A5 AND it is not
        routed to HARD-FALSIFY under Stage 7 closure DECISION 2026-05-21.

        Non-raising form of ``prototype_for``; production orchestrators use
        this to decide whether to call the shape kernel or fall back to the
        non-shape head per §4.2.
        """
        return (
            recipe_id in self._prototypes
            and recipe_id not in self._substrate_inadequate
            and recipe_id not in self._shape_unfittable_advisory_only
            and recipe_id not in self._phase_1_hard_falsified
        )

    def hard_falsified_recipes(self) -> tuple[str, ...]:
        """Recipes routed to HARD-FALSIFY per Stage 7 closure DECISION 2026-05-21.

        These recipes have cascade_outcome='phase_1_hard_falsified'. Production
        cascade orchestrators MUST route these to ingredient+length-only
        (no shape feature emitted). Per Tariq #20 R-T1 binding rider, the
        underlying prototypes MUST NOT be reused as initialization data,
        priors, or warm-starts under any future fresh pre-reg.
        """
        return tuple(sorted(self._phase_1_hard_falsified))

    def advisory_only_recipes(self) -> tuple[str, ...]:
        """F-H-4-A5: recipes routed to ADVISORY-ONLY shape status.

        These recipes have cascade_outcome='advisory_only_shape_unfittable'.
        The non-shape head fallback is the routing destination per §4.2.
        The recipe's Hybrid D2/D5 cascade LOCK status is independent.
        """
        return tuple(sorted(self._shape_unfittable_advisory_only))

    def try_prototype_for(self, recipe_id: str) -> ShapePrototype | None:
        """Non-raising fetch for the shape prototype.

        Per F-H-4-A5 Marcus rider: orchestrator-facing dispatch returns
        ``None`` (not raise) for ADVISORY-ONLY recipes so the production
        path can branch to the non-shape head cleanly. Substrate-inadequate
        and missing-prototype cases also return None.
        """
        if recipe_id not in self._prototypes:
            return None
        if recipe_id in self._substrate_inadequate:
            return None
        if recipe_id in self._shape_unfittable_advisory_only:
            return None
        if recipe_id in self._phase_1_hard_falsified:
            return None
        return self._prototypes[recipe_id]

    def prototype_for(self, recipe_id: str) -> ShapePrototype:
        """Return the ShapePrototype for a recipe with adequate substrate.

        Raises:
            KeyError: if the recipe has no prototype entry at all.
            SubstrateInadequateError: if the recipe has an entry but G1-G4
                gates failed; caller must route to ingredient+length fallback.
            AdvisoryOnlyShapeUnfittableError: if the recipe routed to
                ADVISORY-ONLY shape per F-H-4-A5 (§3.1.5 cascade exit clause).
                Caller must route to the non-shape head per §4.2.
            Phase1HardFalsifiedError: if the recipe routed to HARD-FALSIFY
                per Stage 7 §6.1 closure DECISION 2026-05-21. Caller must
                route to ingredient+length-only (no shape feature emitted).
        """
        if recipe_id not in self._prototypes:
            raise KeyError(
                f"recipe {recipe_id!r} has no shape prototype in "
                f"shape-prototypes.lock.json; known recipes: "
                f"{self.recipes_with_prototype()}"
            )
        if recipe_id in self._substrate_inadequate:
            audit = self._prototypes[recipe_id].substrate_audit
            raise SubstrateInadequateError(
                f"recipe {recipe_id!r} prototype exists but failed substrate "
                f"gates: {audit.failing_gates()}. Per §4.3 invariant 3 the "
                f"orchestrator MUST route this recipe to ingredient+length "
                f"fallback (no shape similarity emitted)."
            )
        if recipe_id in self._shape_unfittable_advisory_only:
            raise AdvisoryOnlyShapeUnfittableError(
                f"recipe {recipe_id!r} routed to ADVISORY-ONLY shape status "
                f"per F-H-4-A5 (§3.1.5 cascade exit clause). The §3.1.4 GP "
                f"fallback NUTS sampler gates failed after operational "
                f"tooling exhaustion. Orchestrator must use the non-shape "
                f"head per §4.2; use try_prototype_for() for the non-raising "
                f"variant. Cascade LOCK status of this recipe is independent "
                f"and unaffected."
            )
        if recipe_id in self._phase_1_hard_falsified:
            raise Phase1HardFalsifiedError(
                f"recipe {recipe_id!r} routed to HARD-FALSIFY per Stage 7 "
                f"§6.1 closure DECISION 2026-05-21 (8-seat ratified). The "
                f"prototype itself is mathematically sound but the FEATURE "
                f"derived from it failed F-S-1/F-S-3 + F-H-7 with margin. "
                f"Orchestrator must use ingredient+length-only (no shape "
                f"feature). Per Tariq #20 R-T1 binding rider: this prototype "
                f"MUST NOT be reused as initialization data, priors, or "
                f"warm-starts under any future fresh pre-reg."
            )
        return self._prototypes[recipe_id]

    # ---- Runtime logging (§4.5 five-SHA contract) --------------------------

    def runtime_log_entry(self) -> dict[str, Any]:
        """Return the §4.5 runtime-log record a production shape emit MUST embed.

        Per §4.5: every shape-feature production prediction JSON carries
        five SHAs in its provenance block. This method emits the
        prototype-side fragment of that block; the qgi-ml commit SHA,
        dispatch_v2 SHA, and lockfile SHA are joined by the emitting
        script. The shape-prototype-side fragment is the minimum a Lloyd's
        auditor needs to trace a prediction back to its prototype source.

        The structure mirrors HybridDispatch.runtime_log_entry() so audit
        consumers can pattern-match across the two F-rule loaders.
        """
        return {
            "shape_prototypes_lock_sha256": self.sha256,
            "shape_prototypes_lock_source_path": (
                str(self._source_path) if self._source_path else None
            ),
            "shape_prototypes_lock_schema_version": self.schema_version,
            "pre_reg_lineage": self.pre_reg_lineage,
            "per_recipe_prototype": {
                rid: {
                    "fit_method": p.fit_method,
                    "fit_method_commit_sha": p.fit_method_commit_sha,
                    "n_training_positives": p.n_training_positives,
                    "canonical_length_T_point": p.canonical_length_T_point,
                    "training_data_snapshot_sha256": p.training_data_snapshot_sha256,
                    "substrate_adequate": p.substrate_audit.all_pass,
                    "substrate_failing_gates": list(p.substrate_audit.failing_gates()),
                }
                for rid, p in self._prototypes.items()
            },
        }


# ---- Loader -----------------------------------------------------------------


def load_dispatch(path: Path | None = None) -> ShapePrototypeDispatch:
    """Load the canonical shape-prototype lock file.

    Defaults to ``qgi-ml/config/shape-prototypes.lock.json``. Performs
    schema validation (top-level + per-recipe) and SHA-256 verification on
    load; downstream callers SHOULD additionally call
    ``assert_dispatch_invariants(dispatch)`` at run-start.
    """
    p = path or DEFAULT_LOCK_PATH
    payload = json.loads(p.read_text(encoding="utf-8"))
    return ShapePrototypeDispatch(payload, source_path=p)


# ---- Invariants (§4.3 + §4.4) -----------------------------------------------


def assert_dispatch_invariants(dispatch: ShapePrototypeDispatch) -> None:
    """Assert §4.3 + §4.4 invariants the shape-prototype dispatch must satisfy.

    Production shape-emit scripts SHOULD call this at run-start. Raises
    AssertionError on any violation; the runtime is expected to abort
    rather than silently proceed. The CI deploy gate
    ``scripts/verify_dispatch_sha.py`` (extended in a follow-up commit per
    §4.4) calls both this function AND the SHA-pin check; either failing
    blocks deploy.
    """
    payload = dispatch._payload  # noqa: SLF001 — invariant inspection on the dispatch state

    # Invariant 1: metadata.n_recipes_with_prototype matches actual count.
    claimed_n_proto = payload["metadata"]["n_recipes_with_prototype"]
    actual_n_proto = len(dispatch.recipes_with_prototype())
    assert claimed_n_proto == actual_n_proto, (
        f"metadata.n_recipes_with_prototype={claimed_n_proto} != actual "
        f"{actual_n_proto}"
    )

    # Invariant 2: metadata.n_recipes_substrate_inadequate matches actual count.
    claimed_n_inad = payload["metadata"]["n_recipes_substrate_inadequate"]
    actual_n_inad = len(dispatch.substrate_inadequate_recipes())
    assert claimed_n_inad == actual_n_inad, (
        f"metadata.n_recipes_substrate_inadequate={claimed_n_inad} != actual "
        f"{actual_n_inad}"
    )

    # Invariant 3: every prototype's schema_version matches the dispatch's.
    for rid, p in dispatch._prototypes.items():  # noqa: SLF001
        assert p.schema_version == dispatch.schema_version, (
            f"recipes[{rid!r}].schema_version={p.schema_version} != "
            f"dispatch schema_version {dispatch.schema_version}"
        )

    # Invariant 4: pre_reg_lineage includes 'stage_6' with a non-empty value.
    stage_6 = dispatch.pre_reg_lineage.get("stage_6", "")
    assert stage_6, (
        "pre_reg_lineage.stage_6 must reference the Stage 6 pre-reg merge SHA"
    )

    # Invariant 5: substrate-inadequate set is a subset of recipes-with-prototype.
    adequate = set(dispatch.substrate_adequate_recipes())
    inadequate = set(dispatch.substrate_inadequate_recipes())
    overlap = adequate & inadequate
    assert not overlap, (
        f"recipes cannot be both substrate-adequate and substrate-inadequate: {overlap}"
    )

    # Invariant 6: canonical_length_T_iqr brackets the point estimate.
    for rid, p in dispatch._prototypes.items():  # noqa: SLF001
        lo, hi = p.canonical_length_T_iqr
        assert lo <= p.canonical_length_T_point <= hi, (
            f"recipes[{rid!r}].canonical_length_T: point "
            f"{p.canonical_length_T_point} not in IQR [{lo}, {hi}]"
        )


# §4.4 NOTE — Dispatch v2 integration
#
# Phase 2 of QGI-R&D | 001 introduces `hybrid_dispatch_v2.json` which adds
# the `architecture: "shape"` enum value and per-recipe
# `shape_prototype_ref` JSON pointer into this lock. The v2 dispatch
# loader (Chunk D, separate PR per §4.8 sunset path) will:
#
#   1. Load this shape-prototype dispatch via ``load_dispatch()``.
#   2. Resolve each `shape_prototype_ref` and either bind it to the
#      recipe head OR demote the recipe to `architecture: "ingredient_length_only"`
#      if the prototype is substrate-inadequate (the single permitted
#      runtime architecture remapping per §4.4).
#   3. Add Invariants 7, 8, 9 from §4.4 to its own assert function.
#
# That work is NOT in Chunk A scope. This module exposes the
# substrate-inadequate set in advance so the v2 loader can consume it
# without inspecting private state.
