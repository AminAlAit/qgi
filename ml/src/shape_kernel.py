"""Shape-feature kernel module (Stage 6 §4.2 binding API).

Per `docs/specs/internal/ops/ml-track/stage-6-shape-feature-prereg.md`
(commit e4f9e7a) §4.2: this module exposes a deterministic public API
``compute_shape_features(country_id, recipe_id, year, shape_prototype,
indicator_panel)`` returning a `ShapeFeatureTriple` of three scalars per
``(country, recipe, year)``. The triple is fed **only** into the
per-recipe head as input features. It is NOT fed into the loss function,
NOT propagated through gradient reversal, NOT absorbed into the shared
backbone embedding, and NOT backpropagated into the prototype parameters
(prototypes are pinned artifacts, not learned weights at training time).

**Chunk B scope (this commit):** math implementation per §3.5.1 + §4.2.
Mahalanobis-derived similarity scalar against the posterior-mean prototype;
DTW distance against the posterior-mean trajectory; cosine-of-lag phase
alignment. Deterministic (no random state). The §4.2 binding contract
documented in the docstring below is honored verbatim.

Authority lineage:
    Methodology Charter (2026-05-17)
      -> DECISION §3 Layers 1-2 + Layer 7 (2026-05-17)
        -> modular architecture spec `06-modular-architecture.md` (2026-05-04)
          -> Stage 6 pre-reg §4 (commit e4f9e7a)
            -> this module.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import numpy as np
import pandas as pd

from shape_prototype_fit_utils import (
    dtw_distance,
    per_country_z_score,
    phase_alignment_cosine,
)

if TYPE_CHECKING:
    from shape_prototype_dispatch import ShapePrototype


# ---- Exceptions (binding API per §4.2) --------------------------------------


class ShapePrototypeMissingError(RuntimeError):
    """Raised when ``compute_shape_features`` is called for a recipe without a prototype.

    The orchestrator MUST check ``ShapePrototypeDispatch.has_prototype(recipe_id)``
    before calling the kernel and route to ingredient+length fallback when
    False. This exception is the kernel's defensive backstop.
    """


class SubstrateInsufficientError(RuntimeError):
    """Raised when the country's indicator panel cannot support the shape kernel.

    Triggered when either:
      (a) the country's available trajectory is shorter than the recipe's
          ``canonical_length_T_point`` (cannot align), OR
      (b) the country's panel fails the Tariq G1-G4 substrate gates for
          this `(country, recipe, year)` triple (per-query substrate check
          distinct from the per-recipe prototype-fit substrate audit in §4.3).

    Per §4.2 binding contract this routes to ingredient+length fallback at
    the head input layer (the head receives a sentinel "shape unavailable"
    marker rather than a triple).
    """


# ---- Output type (binding per §4.2) -----------------------------------------


class ShapeFeatureTriple(NamedTuple):
    """The deterministic shape-feature output per ``(country, recipe, year)``.

    All three outputs are **scalars** — not vectors, not posterior samples.
    Per §4.2 binding contract:

    - ``shape_similarity_scalar`` ∈ [0, 1]
        Mahalanobis-distance-derived posterior-mean similarity. 1 = perfect
        match against the prototype's posterior-mean trajectory. Computed
        from the posterior-mean prototype $\\bar{\\mu}_r = \\mathbb{E}_{\\pi_r}[\\mu_r]$;
        per-draw posterior samples are NOT propagated into the head as features.

    - ``shape_dtw_score`` ∈ [0, ∞)
        DTW (Dynamic Time Warping) distance between the country's z-scored
        trajectory and the prototype's posterior-mean trajectory. Lower =
        better alignment.

    - ``shape_phase_alignment`` ∈ [-1, 1]
        The cosine of the lag at which DTW achieves its minimum.
        Captures whether the country is "leading" or "lagging" the canonical
        movement.

    The §3↔§4 reconciliation contract (binding, verbatim from §4.2):

        "shape_similarity_scalar is computed from the posterior-mean
        prototype $\\bar{\\mu}_r = \\mathbb{E}_{\\pi_r}[\\mu_r]$ (per-draw
        posterior samples are NOT propagated into the head as features);
        uncertainty from prototype parameter variance ($\\Sigma_r$
        posterior + $\\bar{\\mu}_r$ posterior covariance) propagates
        downstream through the bootstrap-CI harness on head outputs per
        §4.6, which resamples training rows + (where prototype N is
        sufficient) prototype draws to produce 80% + 95% credible
        intervals on head probability outputs per R3. shape_dtw_score and
        shape_phase_alignment are likewise computed against the
        posterior-mean trajectory. The prototype carries the posterior
        uncertainty (§3); the kernel emits three scalars per (country,
        recipe, year); the head's CI captures the propagated uncertainty.
        This is the binding contract between §3 (Bayesian posterior shape
        object) and §4 (scalar kernel API) — no per-draw shape posteriors
        are ever exposed to the head's forward pass."

    This NamedTuple is intentionally not a frozen dataclass: pickling,
    JSON-serialization via ``._asdict()``, and tuple-unpacking are all
    first-class downstream consumer affordances (the bootstrap-CI harness
    in §4.6 unpacks the triple positionally; the prediction-JSON writer
    in §4.5 serializes via ``_asdict``).
    """

    shape_similarity_scalar: float
    shape_dtw_score: float
    shape_phase_alignment: float


# ---- Internal helpers -------------------------------------------------------


def _extract_indicator_trajectory(
    indicator_panel: pd.DataFrame,
    country_id: str,
    indicator_id: str,
    end_year: int,
    T_r: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract the alignment window and the pre-window baseline for one indicator.

    Per §3.2.1 end-alignment + §3.2.2 normalization:
      - alignment window: years in [end_year - T_r, end_year - 1] (t in {-T_r, ..., -1})
      - pre-window baseline: years in [end_year - T_r - 20, end_year - T_r - 1]

    Long-format expected panel columns: country_id, year, indicator_id, value.

    Raises:
        SubstrateInsufficientError: if the alignment window is incomplete
            (any of the T_r expected years is missing).
    """
    required_cols = {"country_id", "year", "indicator_id", "value"}
    missing = required_cols - set(indicator_panel.columns)
    if missing:
        raise SubstrateInsufficientError(
            f"indicator_panel missing required columns: {sorted(missing)}"
        )

    mask = (
        (indicator_panel["country_id"] == country_id)
        & (indicator_panel["indicator_id"] == indicator_id)
    )
    sub = indicator_panel.loc[mask, ["year", "value"]].sort_values("year")

    # Build a year -> value mapping for deterministic lookups.
    year_to_value = dict(zip(sub["year"].astype(int).tolist(), sub["value"].astype(float).tolist()))

    alignment_years = list(range(end_year - T_r, end_year))
    alignment_vals = []
    for y in alignment_years:
        if y not in year_to_value or not np.isfinite(year_to_value[y]):
            raise SubstrateInsufficientError(
                f"country={country_id!r} indicator={indicator_id!r}: alignment "
                f"window year {y} missing or non-finite. Required window: "
                f"{alignment_years[0]}..{alignment_years[-1]} (T_r={T_r})."
            )
        alignment_vals.append(year_to_value[y])

    baseline_years = list(range(end_year - T_r - 20, end_year - T_r))
    baseline_vals = [year_to_value[y] for y in baseline_years if y in year_to_value and np.isfinite(year_to_value[y])]
    # Per N6 (QA 2026-05-17): require at least 3 baseline years at kernel
    # time. With <3 points the sample SD is degenerate (n=1 -> 0; n=2 -> highly
    # unstable) and the per-country z-score floors to 1e-6, producing extreme
    # z-scores; this matches the training-time `<20` BASELINE_TOO_SHORT intent
    # at the kernel boundary (training drops the instance; kernel raises).
    if len(baseline_vals) < 3:
        raise SubstrateInsufficientError(
            f"country={country_id!r} indicator={indicator_id!r}: pre-window "
            f"baseline has only {len(baseline_vals)} finite year(s); kernel "
            f"requires >= 3 (training-time gate is BASELINE_TOO_SHORT at <20). "
            f"Per §3.2.2: at kernel time, BASELINE_TOO_SHORT raises."
        )

    return np.asarray(alignment_vals, dtype=float), np.asarray(baseline_vals, dtype=float)


def _signature_array(signature: dict, key: str) -> np.ndarray:
    """Extract a numeric array field from a per-indicator trajectory signature.

    Tolerates list, tuple, or numpy-array storage in the JSON-loaded
    signature.
    """
    val = signature.get(key)
    if val is None:
        raise ShapePrototypeMissingError(
            f"prototype signature missing required field: {key!r}"
        )
    return np.asarray(val, dtype=float)


# ---- Public API (binding per §4.2) ------------------------------------------


def compute_shape_features(
    country_id: str,
    recipe_id: str,
    year: int,
    shape_prototype: "ShapePrototype",
    indicator_panel: "pd.DataFrame",
) -> ShapeFeatureTriple:
    """Compute the deterministic shape-feature triple for one (country, recipe, year).

    **Determinism guarantee (binding per §4.2):** given identical inputs,
    this function MUST return bit-identical outputs across runs. No random
    state is consulted inside the function body: FPCA scoring, DTW, and
    cosine-of-lag are all deterministic given the pinned prototype and
    z-scoring rule. The regression test at
    ``tests/test_shape_kernel_determinism.py`` asserts the kernel run twice
    on the same input yields identical bytes.

    **§3↔§4 reconciliation (binding contract).** The shape prototype
    carries the full Bayesian posterior (≥1000 samples per §3.1.1); this
    kernel emits three scalars computed against the posterior-mean
    prototype $\\bar{\\mu}_r$. Per-draw posterior samples are NEVER
    propagated into the head's forward pass as features. Uncertainty from
    the prototype's posterior parameter variance propagates downstream
    through the §4.6 bootstrap-CI harness on head outputs (R3-binding
    80% + 95% credible intervals on head probability outputs).

    **R3 (Bayesian-only downstream).** The scalar API is consistent with
    R3 because the head returns calibrated probabilities + credible
    intervals; the kernel is one upstream of the Bayesian boundary.
    Beta calibration on head outputs (§4.6) is the single calibration
    step; there is NO isotonic-on-the-kernel layer.

    **R4 (laptop-scale only).** No AWS calls. ``indicator_panel`` is the
    caller's responsibility to load from the cached parquet snapshot
    pinned in the shape prototype's ``training_data_snapshot_sha256``;
    callers MUST verify panel provenance before invoking this kernel.

    Args:
        country_id: ISO-3 country code (e.g., "VEN").
        recipe_id: Recipe ID from the LOCKED set
            (e.g., "mass_protest"). Must match the recipe ID embedded in
            ``shape_prototype``.
        year: Query year ($\\hat{t}$). The aligned trajectory window is
            ``[year - canonical_length_T_point, year - 1]`` per §3.2.1
            end-alignment ($t=0$ lock).
        shape_prototype: The pinned canonical shape prototype loaded via
            ``ShapePrototypeDispatch.prototype_for(recipe_id)``. Carries
            the FPCA posterior summary + canonical length + G1-G4 audit.
            Orchestrator MUST verify ``substrate_audit.all_pass`` before
            calling (kernel raises ``SubstrateInsufficientError`` if not).
        indicator_panel: pandas DataFrame containing the country's
            indicator-level data for the recipe's ``indicator_ids``,
            covering at minimum the alignment window. Long-format
            ``(country_id, year, indicator_id, value)`` is the expected
            shape.

    Returns:
        ShapeFeatureTriple of three scalars per the binding §4.2 ranges.

    Raises:
        ShapePrototypeMissingError: if ``shape_prototype`` is None, its
            ``recipe_id`` does not match the ``recipe_id`` arg, or its
            per-indicator signature is missing required fields.
        SubstrateInsufficientError: if the country's available panel is
            shorter than ``canonical_length_T_point`` OR fails per-query
            G1-G4 substrate gates for this ``(country, recipe, year)``,
            OR the per-indicator panel is missing alignment-window years.

    Notes:
        Implementation per §3.5.1 + §4.2:
          - shape_similarity_scalar: Mahalanobis distance against the
            prototype's posterior-mean trajectory in z-score space,
            aggregated across the K_r indicators in quadrature; mapped
            to [0, 1] via 1 - tanh(d / d_scale) where d_scale is the
            prototype's average posterior trajectory SD
            (sqrt(mean(posterior_cov_diag))).
          - shape_dtw_score: pure-NumPy DTW between the concatenated
            z-scored country trajectory and the prototype's posterior-mean
            trajectory.
          - shape_phase_alignment: cos(pi * lag / T_r) of the median lag
            on the DTW warping path.
    """
    # --- Prototype guards -----------------------------------------------------
    if shape_prototype is None:
        raise ShapePrototypeMissingError(
            f"shape_prototype is None for recipe_id={recipe_id!r}. "
            f"Orchestrator MUST check ShapePrototypeDispatch.has_prototype "
            f"before calling the kernel."
        )
    if shape_prototype.recipe_id != recipe_id:
        raise ShapePrototypeMissingError(
            f"shape_prototype.recipe_id={shape_prototype.recipe_id!r} does "
            f"not match recipe_id arg {recipe_id!r}"
        )
    if not shape_prototype.substrate_audit.all_pass:
        raise SubstrateInsufficientError(
            f"recipe {recipe_id!r} prototype has failing substrate gates: "
            f"{shape_prototype.substrate_audit.failing_gates()}. Orchestrator "
            f"MUST route to ingredient+length fallback per §4.3 invariant 3."
        )

    T_r = int(shape_prototype.canonical_length_T_point)
    indicator_ids = list(shape_prototype.indicator_ids)
    signatures = shape_prototype.per_indicator_trajectory_signature

    if not indicator_ids:
        raise ShapePrototypeMissingError(
            f"recipe {recipe_id!r} has empty indicator_ids in prototype"
        )

    # Verify all indicator signatures are present (prototype contract).
    missing_signatures = [iid for iid in indicator_ids if iid not in signatures]
    if missing_signatures:
        raise ShapePrototypeMissingError(
            f"recipe {recipe_id!r}: per_indicator_trajectory_signature "
            f"missing entries for indicators: {missing_signatures}"
        )

    # --- Per-indicator normalization + distance accumulation ------------------
    # Accumulate squared distances across indicators in z-score space; this
    # is the diagonal-Mahalanobis form (matches the prototype's
    # posterior_cov_diag storage in the schema).
    sum_squared_distance = 0.0
    posterior_sd_sum_squared = 0.0
    concatenated_country: list[np.ndarray] = []
    concatenated_prototype: list[np.ndarray] = []

    for iid in indicator_ids:
        # Extract trajectory + baseline.
        alignment_vals, baseline_vals = _extract_indicator_trajectory(
            indicator_panel, country_id, iid, end_year=year, T_r=T_r
        )
        # Normalize per §3.2.2.
        norm = per_country_z_score(
            raw_trajectory=alignment_vals,
            pre_window_baseline=baseline_vals,
        )
        y_country = norm.y_normalized  # (T_r,)

        # Prototype posterior-mean trajectory + diagonal covariance.
        sig = signatures[iid]
        mu_trajectory = _signature_array(sig, "posterior_mean_trajectory")
        cov_diag = _signature_array(sig, "posterior_cov_diag")

        if mu_trajectory.shape[0] != T_r:
            raise ShapePrototypeMissingError(
                f"recipe {recipe_id!r} indicator {iid!r}: "
                f"posterior_mean_trajectory length {mu_trajectory.shape[0]} "
                f"!= canonical_length_T_point {T_r}"
            )
        if cov_diag.shape[0] != T_r:
            raise ShapePrototypeMissingError(
                f"recipe {recipe_id!r} indicator {iid!r}: "
                f"posterior_cov_diag length {cov_diag.shape[0]} != T_r {T_r}"
            )

        # Mahalanobis-style diagonal distance contribution. Floor cov_diag
        # to avoid division by zero on degenerate axes.
        floored_var = np.maximum(cov_diag, 1e-9)
        sq_dist = float(np.sum(((y_country - mu_trajectory) ** 2) / floored_var))
        sum_squared_distance += sq_dist

        # Distance-scale accumulator: sqrt(trace(Sigma_r)) per spec §4.2 doc.
        posterior_sd_sum_squared += float(np.sum(cov_diag))

        concatenated_country.append(y_country)
        concatenated_prototype.append(mu_trajectory)

    # --- shape_similarity_scalar ---------------------------------------------
    d_total = float(np.sqrt(sum_squared_distance))
    # Per spec doc: d_scale is the posterior-mean of sqrt(trace(Sigma_r)).
    # Floor at small epsilon for numerical stability on near-degenerate prototypes.
    d_scale = float(np.sqrt(max(posterior_sd_sum_squared, 1e-9)))
    # Map distance to [0, 1] similarity: 1 - tanh(d / d_scale).
    similarity = 1.0 - float(np.tanh(d_total / d_scale))
    # Clamp to [0, 1] defensively (tanh in [0,1) on positive input so this
    # is theoretically already in [0, 1]; clamp guards against fp noise).
    similarity = max(0.0, min(1.0, similarity))

    # --- shape_dtw_score + shape_phase_alignment -----------------------------
    country_concat = np.concatenate(concatenated_country)
    prototype_concat = np.concatenate(concatenated_prototype)
    dtw_score, optimal_lag = dtw_distance(country_concat, prototype_concat)
    phase_alignment = phase_alignment_cosine(optimal_lag, max_lag=T_r)

    return ShapeFeatureTriple(
        shape_similarity_scalar=similarity,
        shape_dtw_score=float(dtw_score),
        shape_phase_alignment=float(phase_alignment),
    )
