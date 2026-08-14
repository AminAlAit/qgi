"""Behavior tests for `qgi_ml.src.shape_kernel` math (Chunk B).

Per Stage 6 pre-reg §3.5.1 + §4.2: these tests assert the deterministic
math contract. Edge cases: too-short trajectory raises
``SubstrateInsufficientError``; missing prototype field raises
``ShapePrototypeMissingError``; numerical sanity tests confirm perfect-
match input yields similarity ≈ 1.0, DTW ≈ 0.0, phase ≈ 1.0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from shape_kernel import (  # noqa: E402
    ShapeFeatureTriple,
    ShapePrototypeMissingError,
    SubstrateInsufficientError,
    compute_shape_features,
)
from shape_prototype_dispatch import ShapePrototype, SubstrateAudit  # noqa: E402


# ---- Fixtures ---------------------------------------------------------------


def _build_fixture_prototype(
    *,
    recipe_id: str = "fixture_recipe",
    indicators: tuple[str, ...] = ("IND_A", "IND_B"),
    T_r: int = 5,
    mu_trajectory_by_indicator: dict[str, list[float]] | None = None,
    cov_diag_by_indicator: dict[str, list[float]] | None = None,
    substrate_pass: bool = True,
) -> ShapePrototype:
    """Build a synthetic ShapePrototype dataclass for kernel tests."""
    if mu_trajectory_by_indicator is None:
        # Default: ascending ramp for IND_A, descending ramp for IND_B.
        mu_trajectory_by_indicator = {
            "IND_A": [0.0, 0.25, 0.5, 0.75, 1.0],
            "IND_B": [1.0, 0.75, 0.5, 0.25, 0.0],
        }
    if cov_diag_by_indicator is None:
        cov_diag_by_indicator = {iid: [0.04] * T_r for iid in indicators}

    sig: dict[str, dict] = {}
    for iid in indicators:
        sig[iid] = {
            "fpca_component_scores": [0.0, 0.0, 0.0],
            "fpca_cumulative_variance_explained": 0.85,
            "fpca_basis": "cubic_spline_K8",
            "posterior_mean_trajectory": mu_trajectory_by_indicator[iid],
            "posterior_cov_diag": cov_diag_by_indicator[iid],
        }

    audit = SubstrateAudit(
        g1_n_pos_geq_10=substrate_pass,
        g2_n_countries_geq_5=substrate_pass,
        g3_density_geq_0_85=substrate_pass,
        g4_censoring_clean=substrate_pass,
    )
    return ShapePrototype(
        recipe_id=recipe_id,
        indicator_ids=tuple(indicators),
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


def _build_fixture_panel_perfect_match(
    *,
    country_id: str = "AAA",
    indicators: tuple[str, ...] = ("IND_A", "IND_B"),
    T_r: int = 5,
    end_year: int = 2020,
    prototype: ShapePrototype | None = None,
) -> pd.DataFrame:
    """Build a country panel that, after z-scoring, matches the prototype mean.

    Strategy: the prototype's posterior_mean_trajectory is already in z-score
    space (per §3.1.1 the canonical shape object lives in normalized-trajectory
    space). To make the country's z-scored trajectory equal the prototype mean,
    we set the country's raw alignment-window values to `mu_trajectory * sigma
    + mu_baseline`, with the pre-window baseline chosen so that the baseline
    statistics (mean, SD) are (mu_baseline, sigma).
    """
    assert prototype is not None
    baseline_mean = 100.0
    target_sd = 5.0
    # Construct a 20-year pre-window baseline with EXACT (mean, sample-SD).
    # Sample SD with ddof=1 over [m-d, m+d, m-d, m+d, ...] of length N is
    #   sqrt(N*d^2 / (N-1)),
    # so to land exact target_sd we set d = target_sd * sqrt((N-1)/N).
    baseline_years = list(range(end_year - T_r - 20, end_year - T_r))
    N = len(baseline_years)
    d_offset = target_sd * np.sqrt((N - 1) / N)
    baseline_vals = [
        baseline_mean + (d_offset if i % 2 == 0 else -d_offset)
        for i in range(N)
    ]
    baseline_sd = target_sd

    rows = []
    for iid in indicators:
        mu_traj = prototype.per_indicator_trajectory_signature[iid][
            "posterior_mean_trajectory"
        ]
        # Add baseline values for this indicator.
        for y, v in zip(baseline_years, baseline_vals):
            rows.append({"country_id": country_id, "year": y, "indicator_id": iid, "value": float(v)})
        # Add alignment-window values: target_z * sd + mean.
        # Pad mu_traj with 0.0 if shorter than T_r so the panel always has
        # a complete alignment window (length-mismatch errors are tested
        # against the prototype, not the panel).
        alignment_years = list(range(end_year - T_r, end_year))
        mu_traj_padded = list(mu_traj) + [0.0] * (T_r - len(mu_traj))
        for y, z in zip(alignment_years, mu_traj_padded):
            rows.append(
                {
                    "country_id": country_id,
                    "year": y,
                    "indicator_id": iid,
                    "value": baseline_mean + baseline_sd * float(z),
                }
            )
    return pd.DataFrame(rows)


# ---- Determinism ------------------------------------------------------------


def test_compute_shape_features_is_deterministic() -> None:
    """Two invocations on identical inputs yield identical triples (§4.2)."""
    proto = _build_fixture_prototype()
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    t1 = compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)
    t2 = compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)
    assert t1 == t2
    # Float-bit equality (defensive, per the §4.2 determinism guarantee).
    import struct

    for v1, v2 in zip(t1, t2):
        assert struct.pack(">d", v1) == struct.pack(">d", v2)


# ---- Numerical sanity (perfect-match case) ----------------------------------


def test_perfect_match_yields_max_similarity() -> None:
    """A country whose z-scored trajectory equals the prototype's mean
    should yield similarity ≈ 1.0, DTW ≈ 0.0, phase ≈ 1.0."""
    proto = _build_fixture_prototype()
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    triple = compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)
    assert isinstance(triple, ShapeFeatureTriple)
    # tanh(0) = 0, so 1 - tanh(0) = 1.0 exactly.
    assert triple.shape_similarity_scalar == pytest.approx(1.0, abs=1e-9)
    assert triple.shape_dtw_score == pytest.approx(0.0, abs=1e-9)
    assert triple.shape_phase_alignment == pytest.approx(1.0, abs=1e-9)


def test_offset_trajectory_yields_lower_similarity() -> None:
    """A country whose trajectory is offset from the prototype's mean
    yields similarity < 1.0 and DTW > 0."""
    proto = _build_fixture_prototype()
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    # Add a +1.0 z-shift to the alignment window for IND_A.
    mask = (panel["indicator_id"] == "IND_A") & (panel["year"] >= 2015)
    panel.loc[mask, "value"] = panel.loc[mask, "value"] + 5.0  # +1 SD
    triple = compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)
    assert triple.shape_similarity_scalar < 1.0
    assert triple.shape_similarity_scalar > 0.0  # not at floor
    assert triple.shape_dtw_score > 0.0


def test_output_ranges_bind() -> None:
    """All three scalars satisfy their §4.2 binding ranges across fixtures."""
    proto = _build_fixture_prototype()
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    triple = compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)
    assert 0.0 <= triple.shape_similarity_scalar <= 1.0
    assert triple.shape_dtw_score >= 0.0
    assert -1.0 <= triple.shape_phase_alignment <= 1.0


# ---- Edge cases: prototype guards -------------------------------------------


def test_none_prototype_raises() -> None:
    with pytest.raises(ShapePrototypeMissingError, match="None"):
        compute_shape_features("AAA", "fixture_recipe", 2020, None, pd.DataFrame())  # type: ignore[arg-type]


def test_mismatched_recipe_id_raises() -> None:
    proto = _build_fixture_prototype(recipe_id="recipe_a")
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    with pytest.raises(ShapePrototypeMissingError, match="does not match"):
        compute_shape_features("AAA", "recipe_b", 2020, proto, panel)


def test_substrate_inadequate_prototype_raises() -> None:
    proto = _build_fixture_prototype(substrate_pass=False)
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    with pytest.raises(SubstrateInsufficientError, match="failing substrate"):
        compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)


def test_empty_indicator_ids_raises() -> None:
    # Build a prototype with no indicators (degenerate case).
    audit = SubstrateAudit(True, True, True, True)
    proto = ShapePrototype(
        recipe_id="r",
        indicator_ids=(),
        canonical_length_T_point=5,
        canonical_length_T_iqr=(5, 5),
        canonical_length_T_method="fixture",
        per_indicator_trajectory_signature={},
        fit_method="fpca",
        fit_method_commit_sha="0" * 40,
        n_training_positives=12,
        training_data_snapshot_s3_path="s3://fixture/",
        training_data_snapshot_sha256="a" * 64,
        substrate_audit=audit,
        cohort_calibration_ref="ref",
        schema_version=1,
    )
    with pytest.raises(ShapePrototypeMissingError, match="empty indicator_ids"):
        compute_shape_features("AAA", "r", 2020, proto, pd.DataFrame())


def test_prototype_mu_length_mismatch_raises() -> None:
    """A prototype with posterior_mean_trajectory length != T_r raises."""
    proto = _build_fixture_prototype(
        T_r=5,
        mu_trajectory_by_indicator={
            "IND_A": [0.0, 1.0, 2.0],  # length 3, not 5
            "IND_B": [0.0] * 5,
        },
    )
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    with pytest.raises(ShapePrototypeMissingError, match="length"):
        compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)


# ---- Edge cases: panel substrate --------------------------------------------


def test_missing_alignment_year_raises() -> None:
    """A country with a missing alignment-window year raises substrate error."""
    proto = _build_fixture_prototype()
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    # Drop year 2018 from the alignment window for IND_A.
    drop_mask = ~((panel["indicator_id"] == "IND_A") & (panel["year"] == 2018))
    panel = panel.loc[drop_mask].copy()
    with pytest.raises(SubstrateInsufficientError, match="2018"):
        compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)


def test_empty_baseline_raises() -> None:
    """A country with zero pre-window baseline years raises substrate error."""
    proto = _build_fixture_prototype()
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    # Drop all baseline years (years < 2015).
    panel = panel.loc[panel["year"] >= 2015].copy()
    with pytest.raises(SubstrateInsufficientError, match="baseline"):
        compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)


def test_missing_panel_column_raises() -> None:
    """A panel missing required columns raises substrate error."""
    proto = _build_fixture_prototype()
    panel = pd.DataFrame({"country_id": ["AAA"], "year": [2020]})  # missing indicator_id, value
    with pytest.raises(SubstrateInsufficientError, match="missing required columns"):
        compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)


def test_unknown_country_raises() -> None:
    """A country not present in the panel raises substrate error."""
    proto = _build_fixture_prototype()
    panel = _build_fixture_panel_perfect_match(prototype=proto, country_id="BBB")
    with pytest.raises(SubstrateInsufficientError):
        compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)


# ---- Triple is JSON-serializable per §4.5 -----------------------------------


def test_triple_asdict_yields_native_floats() -> None:
    proto = _build_fixture_prototype()
    panel = _build_fixture_panel_perfect_match(prototype=proto)
    triple = compute_shape_features("AAA", "fixture_recipe", 2020, proto, panel)
    d = triple._asdict()
    for v in d.values():
        assert isinstance(v, float)
