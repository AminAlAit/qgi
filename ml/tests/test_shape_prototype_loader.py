"""Tests for `qgi_ml.src.shape_prototype_dispatch` (§4.3 Pinning Contract loader).

Per Stage 6 pre-reg (qgi-docs commit e4f9e7a) §4.3: any implementation PR
that adds or modifies the production shape-feature pipeline MUST include
a test that loads the prototype lock, asserts SHA-256 verification,
asserts G1-G4 substrate gate handling, and asserts idempotence. This
module satisfies that requirement for Chunk A (loader skeleton).

Chunk B will extend with prototype-content tests once the FPCA math
lands and `shape-prototypes.lock.json` is populated.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from shape_prototype_dispatch import (  # noqa: E402
    DEFAULT_LOCK_PATH,
    AdvisoryOnlyShapeUnfittableError,
    PrototypeIntegrityError,
    SchemaValidationError,
    ShapePrototypeDispatch,
    SubstrateInadequateError,
    assert_dispatch_invariants,
    load_dispatch,
)


# ---- Helpers ----------------------------------------------------------------


def _canonical_sha(payload: dict[str, Any]) -> str:
    """Compute the canonical SHA-256 the loader expects in metadata.file_sha256."""
    clone = {k: v for k, v in payload.items()}
    clone["metadata"] = {k: v for k, v in payload["metadata"].items()}
    clone["metadata"]["file_sha256"] = ""
    canonical = json.dumps(clone, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_lock(path: Path, payload: dict[str, Any], *, fix_sha: bool = True) -> Path:
    """Write a lock JSON, optionally fixing metadata.file_sha256 to canonical."""
    if fix_sha:
        payload = copy.deepcopy(payload)
        payload["metadata"]["file_sha256"] = _canonical_sha(payload)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _adequate_recipe_payload(recipe_id: str = "mass_protest") -> dict[str, Any]:
    """Minimal valid recipe entry with all G1-G4 gates passing.

    Note: this is a SYNTHETIC test fixture only. The real prototype
    population (Chunk C) consumes the founder-picked trio after Chunk B
    lands the fitting math.
    """
    return {
        "recipe_id": recipe_id,
        "indicator_ids": ["VDEM_v2x_polyarchy", "VDEM_v2x_libdem"],
        "canonical_length_T": {
            "point": 5,
            "posterior_iqr": [4, 6],
            "method": "bayesian_acf_panel",
        },
        "per_indicator_trajectory_signature": {
            "VDEM_v2x_polyarchy": {
                "fpca_component_scores": [0.12, -0.34, 0.05],
                "fpca_cumulative_variance_explained": 0.82,
                "fpca_basis": "cubic_spline_K8",
                "posterior_mean_trajectory": [0.0, 0.1, 0.2, 0.15, 0.05],
                "posterior_cov_diag": [0.01, 0.01, 0.02, 0.02, 0.03],
            },
        },
        "fit_method": "fpca",
        "fit_method_commit_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "n_training_positives": 12,
        "training_data_snapshot_sha": {
            "s3_path": "s3://qgi-data-lake-771606957899/ml-artifacts/training-data-snapshots/test/",
            "sha256": "a" * 64,
        },
        "substrate_audit": {
            "g1_n_pos_geq_10": True,
            "g2_n_countries_geq_5": True,
            "g3_density_geq_0_85": True,
            "g4_censoring_clean": True,
        },
        "cohort_calibration_ref": (
            f"qgi-docs/methodology/ml-validation/{recipe_id}/shape-calibration-table.md"
        ),
        "schema_version": 1,
    }


def _empty_stub_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "filed": "2026-05-17",
        "purpose": "Test stub.",
        "pre_reg_lineage": {"stage_6": "e4f9e7a"},
        "metadata": {
            "file_sha256": "",
            "n_recipes_with_prototype": 0,
            "n_recipes_substrate_inadequate": 0,
        },
        "recipes": {},
        "amendments": [],
    }


# ---- Default-path loading ---------------------------------------------------


def test_default_lock_path_resolves() -> None:
    """The default lock path points at the committed canonical config."""
    assert DEFAULT_LOCK_PATH.exists(), (
        f"Default lock path {DEFAULT_LOCK_PATH} must exist (Chunk A stub)"
    )
    assert DEFAULT_LOCK_PATH.name == "shape-prototypes.lock.json"
    assert DEFAULT_LOCK_PATH.parent.name == "config"


def test_empty_stub_loads_cleanly(tmp_path: Path) -> None:
    """The empty stub payload must load without error (Chunk A acceptance)."""
    p = _write_lock(tmp_path / "empty.lock.json", _empty_stub_payload())
    dispatch = load_dispatch(p)
    assert dispatch.schema_version == 1
    assert dispatch.recipes_with_prototype() == ()
    assert dispatch.substrate_inadequate_recipes() == ()
    assert dispatch.substrate_adequate_recipes() == ()
    assert dispatch.pre_reg_lineage["stage_6"] == "e4f9e7a"


def test_empty_stub_passes_invariants() -> None:
    dispatch = load_dispatch()
    assert_dispatch_invariants(dispatch)  # MUST NOT raise


def test_runtime_log_entry_shape_on_empty_stub(tmp_path: Path) -> None:
    """Runtime log emits the five-SHA fragment even with zero recipes."""
    p = _write_lock(tmp_path / "empty.lock.json", _empty_stub_payload())
    dispatch = load_dispatch(p)
    log = dispatch.runtime_log_entry()
    assert "shape_prototypes_lock_sha256" in log
    assert len(log["shape_prototypes_lock_sha256"]) == 64
    assert log["shape_prototypes_lock_schema_version"] == 1
    assert log["per_recipe_prototype"] == {}
    assert log["pre_reg_lineage"]["stage_6"] == "e4f9e7a"


# ---- SHA-256 verification ---------------------------------------------------


def test_sha256_mismatch_raises(tmp_path: Path) -> None:
    """A tampered file_sha256 must raise PrototypeIntegrityError."""
    payload = _empty_stub_payload()
    # Set a wrong SHA explicitly.
    payload["metadata"]["file_sha256"] = "0" * 64
    p = tmp_path / "lock.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PrototypeIntegrityError, match="SHA-256 mismatch"):
        load_dispatch(p)


def test_sha256_idempotent_across_reloads(tmp_path: Path) -> None:
    """Loading the same content twice yields the same SHA."""
    payload = _empty_stub_payload()
    p = _write_lock(tmp_path / "lock.json", payload)
    d1 = load_dispatch(p)
    d2 = load_dispatch(p)
    assert d1.sha256 == d2.sha256
    assert len(d1.sha256) == 64


def test_canonical_sha_matches_committed_stub() -> None:
    """The committed empty stub's embedded SHA must match canonical recomputation."""
    payload = json.loads(DEFAULT_LOCK_PATH.read_text(encoding="utf-8"))
    expected = _canonical_sha(payload)
    assert payload["metadata"]["file_sha256"] == expected, (
        "The empty-stub SHA in shape-prototypes.lock.json does not match "
        "canonical recomputation. Recompute via _canonical_sha and update."
    )


def test_modifying_content_without_rotating_sha_raises(tmp_path: Path) -> None:
    """Modifying content without rotating the embedded SHA must raise.

    This is the F-Shape-1 / §4.5 'no silent rotation' guard at runtime."""
    payload = _empty_stub_payload()
    p = _write_lock(tmp_path / "lock.json", payload)
    # Mutate purpose string without rotating SHA.
    raw = json.loads(p.read_text(encoding="utf-8"))
    raw["purpose"] = "TAMPERED"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(PrototypeIntegrityError):
        load_dispatch(p)


# ---- Schema validation ------------------------------------------------------


def test_unsupported_schema_version_raises(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    payload["schema_version"] = 99
    p = _write_lock(tmp_path / "lock.json", payload)
    with pytest.raises(SchemaValidationError, match="schema_version"):
        load_dispatch(p)


def test_missing_top_level_key_raises(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    del payload["pre_reg_lineage"]
    p = tmp_path / "lock.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SchemaValidationError, match="missing top-level keys"):
        load_dispatch(p)


def test_missing_stage_6_lineage_raises(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    payload["pre_reg_lineage"] = {}
    p = tmp_path / "lock.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SchemaValidationError, match="stage_6"):
        load_dispatch(p)


def test_malformed_json_raises(tmp_path: Path) -> None:
    p = tmp_path / "lock.json"
    p.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_dispatch(p)


def test_recipe_with_missing_field_raises(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    bad_recipe = _adequate_recipe_payload()
    del bad_recipe["fit_method"]
    payload["recipes"]["mass_protest"] = bad_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    with pytest.raises(SchemaValidationError, match="missing keys"):
        load_dispatch(p)


def test_recipe_with_bad_fit_method_raises(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    bad_recipe = _adequate_recipe_payload()
    bad_recipe["fit_method"] = "made_up_method"
    payload["recipes"]["mass_protest"] = bad_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    with pytest.raises(SchemaValidationError, match="fit_method"):
        load_dispatch(p)


def test_recipe_key_mismatch_raises(tmp_path: Path) -> None:
    """recipe_id in the entry must match the map key."""
    payload = _empty_stub_payload()
    bad_recipe = _adequate_recipe_payload(recipe_id="something_else")
    payload["recipes"]["mass_protest"] = bad_recipe  # mismatched key
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    with pytest.raises(SchemaValidationError, match="does not match map key"):
        load_dispatch(p)


# ---- Substrate gate handling ------------------------------------------------


def test_g1_fail_marks_recipe_substrate_inadequate(tmp_path: Path) -> None:
    """G1 failure routes recipe to substrate-inadequate set, does NOT raise on load."""
    payload = _empty_stub_payload()
    bad_recipe = _adequate_recipe_payload()
    bad_recipe["substrate_audit"]["g1_n_pos_geq_10"] = False
    payload["recipes"]["mass_protest"] = bad_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    payload["metadata"]["n_recipes_substrate_inadequate"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)

    dispatch = load_dispatch(p)  # MUST NOT raise
    assert "mass_protest" in dispatch.substrate_inadequate_recipes()
    assert "mass_protest" not in dispatch.substrate_adequate_recipes()
    assert dispatch.has_prototype("mass_protest") is False


def test_substrate_inadequate_lookup_raises_subclass(tmp_path: Path) -> None:
    """Direct prototype_for() on a substrate-inadequate recipe raises."""
    payload = _empty_stub_payload()
    bad_recipe = _adequate_recipe_payload()
    bad_recipe["substrate_audit"]["g3_density_geq_0_85"] = False
    payload["recipes"]["mass_protest"] = bad_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    payload["metadata"]["n_recipes_substrate_inadequate"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    with pytest.raises(SubstrateInadequateError, match="g3_density_geq_0_85"):
        dispatch.prototype_for("mass_protest")


def test_unknown_recipe_raises_key_error(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    with pytest.raises(KeyError, match="no shape prototype"):
        dispatch.prototype_for("nonexistent_recipe_id")


def test_all_g_gates_pass_yields_adequate_recipe(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    good_recipe = _adequate_recipe_payload()
    payload["recipes"]["mass_protest"] = good_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)

    assert dispatch.has_prototype("mass_protest") is True
    proto = dispatch.prototype_for("mass_protest")
    assert proto.recipe_id == "mass_protest"
    assert proto.fit_method == "fpca"
    assert proto.substrate_audit.all_pass is True
    assert proto.substrate_audit.failing_gates() == ()
    assert proto.canonical_length_T_point == 5
    assert proto.canonical_length_T_iqr == (4, 6)


# ---- Invariants -------------------------------------------------------------


def test_invariant_catches_metadata_count_mismatch(tmp_path: Path) -> None:
    """metadata.n_recipes_with_prototype != actual must fail invariants."""
    payload = _empty_stub_payload()
    good_recipe = _adequate_recipe_payload()
    payload["recipes"]["mass_protest"] = good_recipe
    # Wrong count:
    payload["metadata"]["n_recipes_with_prototype"] = 99
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    with pytest.raises(AssertionError, match="n_recipes_with_prototype"):
        assert_dispatch_invariants(dispatch)


def test_invariant_catches_substrate_count_mismatch(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    bad_recipe = _adequate_recipe_payload()
    bad_recipe["substrate_audit"]["g2_n_countries_geq_5"] = False
    payload["recipes"]["mass_protest"] = bad_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    # Wrong substrate count:
    payload["metadata"]["n_recipes_substrate_inadequate"] = 0
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    with pytest.raises(AssertionError, match="n_recipes_substrate_inadequate"):
        assert_dispatch_invariants(dispatch)


def test_invariant_catches_iqr_not_bracketing_point(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    bad_recipe = _adequate_recipe_payload()
    bad_recipe["canonical_length_T"]["point"] = 99  # outside [4, 6]
    payload["recipes"]["mass_protest"] = bad_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    with pytest.raises(AssertionError, match="canonical_length_T"):
        assert_dispatch_invariants(dispatch)


def test_runtime_log_includes_per_recipe_provenance(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    good_recipe = _adequate_recipe_payload()
    payload["recipes"]["mass_protest"] = good_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    log = dispatch.runtime_log_entry()
    assert "mass_protest" in log["per_recipe_prototype"]
    entry = log["per_recipe_prototype"]["mass_protest"]
    assert entry["fit_method"] == "fpca"
    assert entry["n_training_positives"] == 12
    assert entry["substrate_adequate"] is True
    assert entry["substrate_failing_gates"] == []


def test_substrate_inadequate_appears_in_runtime_log(tmp_path: Path) -> None:
    payload = _empty_stub_payload()
    bad_recipe = _adequate_recipe_payload()
    bad_recipe["substrate_audit"]["g4_censoring_clean"] = False
    payload["recipes"]["mass_protest"] = bad_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    payload["metadata"]["n_recipes_substrate_inadequate"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    log = dispatch.runtime_log_entry()
    entry = log["per_recipe_prototype"]["mass_protest"]
    assert entry["substrate_adequate"] is False
    assert "g4_censoring_clean" in entry["substrate_failing_gates"]


# ---- Type sanity ------------------------------------------------------------


def test_load_dispatch_returns_dispatch_type() -> None:
    dispatch = load_dispatch()
    assert isinstance(dispatch, ShapePrototypeDispatch)


def test_default_schema_path_exists() -> None:
    """The JSON-schema artifact must ship alongside the lock."""
    from shape_prototype_dispatch import DEFAULT_SCHEMA_PATH

    assert DEFAULT_SCHEMA_PATH.exists()
    # And be readable as JSON.
    schema = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["title"].startswith("QGI Stage 6 Shape Prototype Lock")


# ---- F-H-4-A5 ADVISORY-ONLY cascade exit clause -----------------------------
#
# Five tests for the §3.1.5 cascade exit clause (F-H-4-A5, 8-seat ratified
# 2026-05-20 with Tariq + Marcus operational riders). The cascade-exit-clause
# code path covers: schema acceptance of cascade_outcome="advisory_only_shape_
# unfittable" entries with empty per_indicator_trajectory_signature, dispatch
# loader tracking via _shape_unfittable_advisory_only, has_prototype/
# try_prototype_for/prototype_for behavior, and the loader's semantic gate
# preventing empty signature on fit_locked recipes.


def _advisory_only_recipe_payload(recipe_id: str = "foreign_intervention") -> dict[str, Any]:
    """Synthetic ADVISORY-ONLY recipe entry for F-H-4-A5 tests.

    Mirrors the production foreign_intervention lock entry structure: empty
    per_indicator_trajectory_signature, cascade_outcome set, Marcus rider
    diagnostic fields present, substrate_audit all-pass (because this is
    a sampler-gate failure, NOT a G1-G4 substrate failure).
    """
    return {
        "recipe_id": recipe_id,
        "cascade_outcome": "advisory_only_shape_unfittable",
        "indicator_ids": ["IND_A", "IND_B"],
        "canonical_length_T": {
            "point": 5,
            "posterior_iqr": [4, 6],
            "method": "advisory_only_not_emitted",
        },
        "per_indicator_trajectory_signature": {},
        "fit_method": "hierarchical_bayes_gp_fallback",
        "fit_method_commit_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        "n_training_positives": 110,
        "training_data_snapshot_sha": {
            "s3_path": "local-laptop-scale",
            "sha256": "0" * 64,
        },
        "substrate_audit": {
            "g1_n_pos_geq_10": True,
            "g2_n_countries_geq_5": True,
            "g3_density_geq_0_85": True,
            "g4_censoring_clean": True,
        },
        "cohort_calibration_ref": "advisory_only_not_applicable",
        "schema_version": 1,
    }


def test_advisory_only_recipe_loads_without_raising(tmp_path: Path) -> None:
    """F-H-4-A5: loader must accept a cascade_outcome='advisory_only_shape_unfittable'
    entry with empty per_indicator_trajectory_signature."""
    payload = _empty_stub_payload()
    payload["recipes"]["foreign_intervention"] = _advisory_only_recipe_payload()
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)

    dispatch = load_dispatch(p)  # MUST NOT raise
    assert "foreign_intervention" in dispatch.recipes_with_prototype()
    assert "foreign_intervention" in dispatch.advisory_only_recipes()


def test_advisory_only_has_prototype_returns_false(tmp_path: Path) -> None:
    """F-H-4-A5: has_prototype() returns False for ADVISORY-ONLY recipes so the
    production orchestrator routes to the non-shape head per §4.2."""
    payload = _empty_stub_payload()
    payload["recipes"]["foreign_intervention"] = _advisory_only_recipe_payload()
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    assert dispatch.has_prototype("foreign_intervention") is False


def test_advisory_only_prototype_for_raises_advisory_only_error(tmp_path: Path) -> None:
    """F-H-4-A5: prototype_for() on an ADVISORY-ONLY recipe raises
    AdvisoryOnlyShapeUnfittableError (NOT SubstrateInadequateError).
    Distinguishing the two failure modes lets the orchestrator emit
    different diagnostic messages to Lloyd's audit."""
    payload = _empty_stub_payload()
    payload["recipes"]["foreign_intervention"] = _advisory_only_recipe_payload()
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    with pytest.raises(AdvisoryOnlyShapeUnfittableError, match="F-H-4-A5"):
        dispatch.prototype_for("foreign_intervention")


def test_advisory_only_try_prototype_for_returns_none(tmp_path: Path) -> None:
    """F-H-4-A5 Marcus rider: try_prototype_for() returns None (non-raising)
    for ADVISORY-ONLY recipes so the production path branches cleanly."""
    payload = _empty_stub_payload()
    payload["recipes"]["foreign_intervention"] = _advisory_only_recipe_payload()
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    assert dispatch.try_prototype_for("foreign_intervention") is None
    # Sanity: try_prototype_for also returns None for unknown / substrate-
    # inadequate recipes so the production caller has one non-raising entry.
    assert dispatch.try_prototype_for("nonexistent_recipe") is None


def test_advisory_only_recipes_enumeration(tmp_path: Path) -> None:
    """F-H-4-A5: advisory_only_recipes() enumerates exactly the recipes with
    cascade_outcome='advisory_only_shape_unfittable'. Mixed-cohort test:
    one fit_locked + one ADVISORY-ONLY."""
    payload = _empty_stub_payload()
    payload["recipes"]["mass_protest"] = _adequate_recipe_payload(recipe_id="mass_protest")
    payload["recipes"]["foreign_intervention"] = _advisory_only_recipe_payload()
    payload["metadata"]["n_recipes_with_prototype"] = 2
    p = _write_lock(tmp_path / "lock.json", payload)
    dispatch = load_dispatch(p)
    assert dispatch.advisory_only_recipes() == ("foreign_intervention",)
    # mass_protest is fit_locked (default cascade_outcome) → has_prototype True
    assert dispatch.has_prototype("mass_protest") is True
    # foreign_intervention is ADVISORY-ONLY → has_prototype False
    assert dispatch.has_prototype("foreign_intervention") is False


def test_fit_locked_with_empty_signature_raises(tmp_path: Path) -> None:
    """F-H-4-A5 semantic gate (QA review of qgi-ml#85 blocker): the schema
    relaxed per_indicator_trajectory_signature minProperties to 0 so ADVISORY-
    ONLY entries can emit {}, but a fit_locked recipe with empty signature is
    a semantic regression. The loader catches it with a SchemaValidationError
    that hints at the correct cascade_outcome to use."""
    payload = _empty_stub_payload()
    bad_recipe = _adequate_recipe_payload()
    bad_recipe["cascade_outcome"] = "fit_locked"
    bad_recipe["per_indicator_trajectory_signature"] = {}
    payload["recipes"]["mass_protest"] = bad_recipe
    payload["metadata"]["n_recipes_with_prototype"] = 1
    p = _write_lock(tmp_path / "lock.json", payload)
    with pytest.raises(SchemaValidationError, match="cascade_outcome='fit_locked'"):
        load_dispatch(p)
