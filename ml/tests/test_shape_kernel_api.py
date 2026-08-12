"""API contract tests for `qgi_ml.src.shape_kernel` (Stage 6 §4.2 binding).

Chunk A asserts the public surface: `ShapeFeatureTriple` is a NamedTuple
with the three pre-registered scalar fields, `compute_shape_features` has
the binding signature, and the function currently raises `NotImplementedError`
(pending Chunk B math). Chunk B updates this module to assert the math
behavior; the API-shape tests remain valid across both chunks.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import shape_kernel  # noqa: E402
from shape_kernel import (  # noqa: E402
    ShapeFeatureTriple,
    ShapePrototypeMissingError,
    SubstrateInsufficientError,
    compute_shape_features,
)


# ---- ShapeFeatureTriple structure -------------------------------------------


def test_shape_feature_triple_is_named_tuple() -> None:
    """ShapeFeatureTriple is a NamedTuple per §4.2 binding API."""
    assert issubclass(ShapeFeatureTriple, tuple)
    # NamedTuple marker:
    assert hasattr(ShapeFeatureTriple, "_fields")
    assert hasattr(ShapeFeatureTriple, "_asdict")


def test_shape_feature_triple_has_three_fields() -> None:
    """Per §4.2: exactly three scalar fields in pre-registered order."""
    assert ShapeFeatureTriple._fields == (
        "shape_similarity_scalar",
        "shape_dtw_score",
        "shape_phase_alignment",
    )


def test_shape_feature_triple_construction() -> None:
    """The NamedTuple constructs by position and by keyword."""
    by_position = ShapeFeatureTriple(0.5, 1.2, 0.0)
    by_keyword = ShapeFeatureTriple(
        shape_similarity_scalar=0.5,
        shape_dtw_score=1.2,
        shape_phase_alignment=0.0,
    )
    assert by_position == by_keyword
    assert by_position.shape_similarity_scalar == 0.5
    assert by_position.shape_dtw_score == 1.2
    assert by_position.shape_phase_alignment == 0.0


def test_shape_feature_triple_unpacks_positionally() -> None:
    """Downstream consumers unpack the triple positionally (§4.2 doc)."""
    triple = ShapeFeatureTriple(0.5, 1.2, -0.3)
    sim, dtw, phase = triple
    assert sim == 0.5
    assert dtw == 1.2
    assert phase == -0.3


def test_shape_feature_triple_asdict_keys() -> None:
    """_asdict() yields a stable mapping for JSON serialization (§4.5)."""
    triple = ShapeFeatureTriple(0.5, 1.2, -0.3)
    d = triple._asdict()
    assert set(d.keys()) == {
        "shape_similarity_scalar",
        "shape_dtw_score",
        "shape_phase_alignment",
    }


# ---- compute_shape_features signature ---------------------------------------


def test_compute_shape_features_exists() -> None:
    """The binding public API function exists in the module."""
    assert callable(compute_shape_features)
    assert hasattr(shape_kernel, "compute_shape_features")


def test_compute_shape_features_signature_matches_prereg() -> None:
    """Signature matches §4.2 binding API verbatim."""
    sig = inspect.signature(compute_shape_features)
    params = list(sig.parameters)
    assert params == [
        "country_id",
        "recipe_id",
        "year",
        "shape_prototype",
        "indicator_panel",
    ]


def test_compute_shape_features_rejects_none_prototype_in_chunk_b() -> None:
    """Chunk B: the math is landed; ``None`` prototype raises the binding error.

    Replaces Chunk A's ``NotImplementedError`` assertion. The API-signature
    tests above survive both chunks; the math + behavior tests live in
    `tests/test_shape_kernel_math.py`.
    """
    with pytest.raises(ShapePrototypeMissingError, match="None"):
        compute_shape_features(
            country_id="VEN",
            recipe_id="mass_protest",
            year=2024,
            shape_prototype=None,  # type: ignore[arg-type]
            indicator_panel=None,  # type: ignore[arg-type]
        )


# ---- Exception classes ------------------------------------------------------


def test_shape_prototype_missing_error_is_runtime_error() -> None:
    """The exception class is a RuntimeError subclass per §4.2 binding."""
    assert issubclass(ShapePrototypeMissingError, RuntimeError)


def test_substrate_insufficient_error_is_runtime_error() -> None:
    """The exception class is a RuntimeError subclass per §4.2 binding."""
    assert issubclass(SubstrateInsufficientError, RuntimeError)


def test_exception_classes_exposed_on_module() -> None:
    """Per §4.2 binding API: both exception classes are public."""
    assert hasattr(shape_kernel, "ShapePrototypeMissingError")
    assert hasattr(shape_kernel, "SubstrateInsufficientError")


# ---- Docstring carries the §3↔§4 reconciliation contract --------------------


def test_compute_shape_features_docstring_pins_reconciliation_contract() -> None:
    """The §3↔§4 reconciliation contract is documented on the public API.

    A Lloyd's reviewer reading the docstring alone (no Stage 6 PDF) must
    see: posterior-mean prototype (not per-draw samples) drives the
    scalar emit; uncertainty propagates through the head's bootstrap CI.
    """
    doc = compute_shape_features.__doc__ or ""
    assert "posterior-mean" in doc
    assert "Determinism guarantee" in doc
    assert "bootstrap" in doc.lower()
    # R3 and R4 named explicitly:
    assert "R3" in doc
    assert "R4" in doc


def test_shape_feature_triple_docstring_pins_value_ranges() -> None:
    """Per §4.2 binding: each scalar's range is documented on the NamedTuple."""
    doc = ShapeFeatureTriple.__doc__ or ""
    assert "[0, 1]" in doc
    assert "[-1, 1]" in doc
    assert "[0, ∞)" in doc or "[0, infinity)" in doc or "Lower" in doc
