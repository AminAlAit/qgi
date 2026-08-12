"""Determinism regression test for `qgi_ml.src.shape_kernel` (§4.2 binding).

Per Stage 6 pre-reg (docs-specs commit e4f9e7a) §4.2 (binding):

    "Determinism guarantee. Given identical inputs, compute_shape_features
    must return bit-identical outputs across runs. Regression test at
    tests/test_shape_kernel_determinism.py asserts the kernel run twice
    on the same input yields identical bytes."

**Chunk B status (this commit):** ACTIVE. The kernel math lands in Chunk B
and this test runs the kernel twice on the same input and asserts
``ShapeFeatureTriple`` bit-equality (tuple equality plus explicit
float-bit comparison via ``struct.pack``).

The §4.2 guarantee is achievable without effort in Python because none of
the math operations (Mahalanobis distance, DTW, cosine-of-lag) consult
random state. Chunk B MUST avoid any operation that would break
determinism: no ``np.random``, no ``set`` ordering dependencies in
trajectory indexing, no float-summation order that varies by dict
iteration order under different Python builds.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _build_fixture_prototype():  # type: ignore[no-untyped-def]
    """Build a fixture prototype for the determinism regression test."""
    from shape_prototype_dispatch import ShapePrototype, SubstrateAudit

    T_r = 5
    indicators = ("IND_A", "IND_B")
    mu_by_iid = {
        "IND_A": [0.0, 0.25, 0.5, 0.75, 1.0],
        "IND_B": [1.0, 0.75, 0.5, 0.25, 0.0],
    }
    sig = {
        iid: {
            "fpca_component_scores": [0.0, 0.0, 0.0],
            "fpca_cumulative_variance_explained": 0.85,
            "fpca_basis": "cubic_spline_K8",
            "posterior_mean_trajectory": mu_by_iid[iid],
            "posterior_cov_diag": [0.04] * T_r,
        }
        for iid in indicators
    }
    audit = SubstrateAudit(True, True, True, True)
    return ShapePrototype(
        recipe_id="determinism_fixture",
        indicator_ids=indicators,
        canonical_length_T_point=T_r,
        canonical_length_T_iqr=(T_r, T_r),
        canonical_length_T_method="fixture",
        per_indicator_trajectory_signature=sig,
        fit_method="fpca",
        fit_method_commit_sha="0" * 40,
        n_training_positives=12,
        training_data_snapshot_s3_path="s3://fixture/",
        training_data_snapshot_sha256="a" * 64,
        substrate_audit=audit,
        cohort_calibration_ref="fixture-ref",
        schema_version=1,
    )


def _build_fixture_indicator_panel(prototype) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    """Build a deterministic indicator panel matching the fixture prototype."""
    end_year = 2020
    T_r = prototype.canonical_length_T_point
    baseline_mean, target_sd = 100.0, 5.0
    baseline_years = list(range(end_year - T_r - 20, end_year - T_r))
    N = len(baseline_years)
    d_offset = target_sd * np.sqrt((N - 1) / N)
    baseline_vals = [
        baseline_mean + (d_offset if i % 2 == 0 else -d_offset)
        for i in range(N)
    ]
    rows = []
    for iid in prototype.indicator_ids:
        mu_traj = prototype.per_indicator_trajectory_signature[iid][
            "posterior_mean_trajectory"
        ]
        for y, v in zip(baseline_years, baseline_vals):
            rows.append({"country_id": "AAA", "year": y, "indicator_id": iid, "value": float(v)})
        for y, z in zip(range(end_year - T_r, end_year), mu_traj):
            rows.append(
                {
                    "country_id": "AAA",
                    "year": y,
                    "indicator_id": iid,
                    "value": baseline_mean + target_sd * float(z),
                }
            )
    return pd.DataFrame(rows)


def test_compute_shape_features_is_bit_deterministic() -> None:
    """Two invocations on identical inputs produce bit-identical triples.

    Per §4.2 binding guarantee: float-bit equality on every field of the
    returned NamedTuple.
    """
    from shape_kernel import compute_shape_features

    prototype = _build_fixture_prototype()
    panel = _build_fixture_indicator_panel(prototype)

    triple_1 = compute_shape_features(
        "AAA", "determinism_fixture", 2020, prototype, panel
    )
    triple_2 = compute_shape_features(
        "AAA", "determinism_fixture", 2020, prototype, panel
    )
    # Tuple equality on the NamedTuple.
    assert triple_1 == triple_2
    # Bit-identical floats (defensive — Python float == can pass on
    # different bit patterns for some NaN/zero edge cases).
    for v1, v2 in zip(triple_1, triple_2):
        assert struct.pack(">d", v1) == struct.pack(">d", v2)


def test_compute_shape_features_deterministic_under_row_permutation() -> None:
    """Row permutation of the indicator panel does not change the result.

    Per §4.2: the kernel must not depend on row-iteration order in the
    panel. We construct two semantically-identical panels (same rows,
    permuted order) and assert bit-equality of outputs.
    """
    from shape_kernel import compute_shape_features

    prototype = _build_fixture_prototype()
    panel = _build_fixture_indicator_panel(prototype)
    # Permute by reverse ordering.
    panel_reversed = panel.iloc[::-1].reset_index(drop=True)

    triple_1 = compute_shape_features("AAA", "determinism_fixture", 2020, prototype, panel)
    triple_2 = compute_shape_features("AAA", "determinism_fixture", 2020, prototype, panel_reversed)
    for v1, v2 in zip(triple_1, triple_2):
        assert struct.pack(">d", v1) == struct.pack(">d", v2)


def test_determinism_contract_documented_in_kernel_docstring() -> None:
    """The determinism guarantee is reachable from the public API docstring.

    This test is NOT skipped — it locks the API-doc requirement now so
    that any Chunk B refactor that drops the guarantee from the
    docstring is caught immediately.
    """
    from shape_kernel import compute_shape_features

    doc = compute_shape_features.__doc__ or ""
    assert "Determinism guarantee" in doc
    assert "bit-identical" in doc
    # Whitespace-normalize before checking — the docstring may wrap the
    # phrase across newlines.
    normalized = " ".join(doc.lower().split())
    assert "no random state" in normalized or "no `np.random`" in normalized


def test_determinism_test_module_skip_marker_present() -> None:
    """Sentinel: confirms the skipped Chunk B test exists in this module.

    Without this sentinel a future PR could silently delete the skipped
    test and leave Chunk B unable to find the placeholder. This test
    locks the placeholder's presence by name.
    """
    import test_shape_kernel_determinism as mod

    assert hasattr(mod, "test_compute_shape_features_is_bit_deterministic")
