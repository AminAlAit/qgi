"""
DSCDI Finder — Phase 5 v0.0b Stage C primary deliverable.

Computes Detrended Similar-Country Dynamic Indicators (DSCDIs) per the
unanimous CSD reconvene DECISION 2026-05-05. Two-pass algorithm with
Class A/B/C indicator taxonomy and common-factor demeaning for severe-
CSD global-arc indicators.

Authoritative input spec:
  docs/specs/internal/ops/cascade-track/phase-5-v0.0b-stage-c-input-spec.md

The methodology is deliberately decoupled from the production execution
context. This module provides pure-function transformations and
correlation routines; the eventual Batch container at Stage F will
import these functions and orchestrate them at scale.

# NOT RUN AGAINST PRODUCTION at Stage C. Per founder direction
# 2026-05-04 / 2026-05-05: Stage F (TF apply + pipeline-B re-bake) is
# DEFERRED to end-of-cascade-mandate test-run. Stage C ships the code
# + unit tests + smoke test on a single indicator only.

Three indicator classes (per CSD reconvene DECISION):
  - Class A: severe-CSD global-arc (CD > 100). Two-pass: undemeaned
    baseline + common-factor demeaned primary.
  - Class B: WGI-pre-normalized. Standard ADF-DSCDI (no demeaning;
    common factor already absorbed by source-data normalization).
  - Class C: low-CSD idiosyncratic (default). Standard ADF-DSCDI.

Falsification trigger (Stage C exit gate, Priya's spec):
  Mean abs pairwise Pearson > 0.25 on Class A demeaned output flags the
  indicator for Phase 6 EB architecture note + Miriam consultation.

References:
  - Stage C input spec (above)
  - CSD reconvene DECISION (docs-specs#26)
  - Pesaran (2004) for CD test (which this module does NOT compute;
    that's run_csd_diagnostic.py's job)
  - Pesaran (2007) CIPS — pure-Python implementation deferred to the
    30-day commitment (deadline 2026-06-04) per Tariq + Kwame.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Class taxonomy + transformation rules (per Stage C input spec)
# ---------------------------------------------------------------------------

#: Severe-CSD global-arc indicators (Class A) per Step 5 CSD diagnostic.
#: These get the two-pass treatment: undemeaned baseline + demeaned primary.
CLASS_A_SEVERE_CSD: frozenset[str] = frozenset(
    {
        "v2x_libdem",
        "NY.GDP.PCAP.CD",
        "FP.CPI.TOTL.ZG",
        "SL.UEM.TOTL.ZS",
        "CC.EST",  # WGI but elevated CD; Class A overrides Class B
        "v2x_polyarchy",
        "MS.MIL.XPND.GD.ZS",
        "NE.EXP.GNFS.ZS",
        "NE.IMP.GNFS.ZS",
        "SE.PRM.ENRR",
        "SH.DYN.MORT",
        "SP.DYN.LE00.IN",
        "SP.DYN.TFRT.IN",
        "IT.CEL.SETS.P2",
    }
)

#: WGI-pre-normalized indicators (Class B) per Tariq Q4 ruling.
#: Annual cross-sectional normalization absorbs common factor at source.
#: NOTE: CC.EST is in CLASS_A_SEVERE_CSD (override); rest are Class B.
CLASS_B_WGI: frozenset[str] = frozenset(
    {
        "RL.EST",
        "GE.EST",
        "RQ.EST",
        "PS.EST",
        "VA.EST",
    }
)

# Outlier handling per Protocol 2:
#: NY.GDP.MKTP.KD.ZG: I(0) growth rate; no transformation; no demeaning
#: (it's already a differenced series; demeaning would over-process).
OUTLIER_NO_TRANSFORM: frozenset[str] = frozenset({"NY.GDP.MKTP.KD.ZG"})

#: SP.POP.TOTL: I(2) per audit, but founder direction = log-difference
#: (population growth rate), not double-difference. Treated as Class A
#: for demeaning purposes.
OUTLIER_LOG_DIFFERENCE: frozenset[str] = frozenset({"SP.POP.TOTL"})

# Stage C exit-gate threshold (Priya's spec)
PAIRWISE_CORR_DEMEANING_INSUFFICIENT_THRESHOLD = 0.25

IndicatorClass = Literal["A", "B", "C"]
TransformKind = Literal["first_diff", "log_diff", "pass_through"]


@dataclass(frozen=True)
class IndicatorDisposition:
    """Per-indicator Stage C disposition computed from inputs.

    `indicator_class` drives the demeaning decision; `transform` drives
    the per-country series transformation.
    """

    indicator_id: str
    classification: str  # from audit JSON: I(0)/I(1)/I(2)/ambiguous
    indicator_class: IndicatorClass
    transform: TransformKind


# ---------------------------------------------------------------------------
# Disposition resolution
# ---------------------------------------------------------------------------


def resolve_disposition(indicator_id: str, audit_classification: str) -> IndicatorDisposition:
    """Map (indicator_id, audit_classification) to a Stage C disposition.

    Resolution rules (Protocol 1 + Protocol 2 + CSD reconvene Step 1):
      1. NY.GDP.MKTP.KD.ZG: pass_through, Class A documentation but no
         demeaning at compute time (special case in run_dscdi_pass).
      2. SP.POP.TOTL: log_diff, Class A.
      3. CLASS_B_WGI members: first_diff if I(1), pass_through if I(0),
         Class B.
      4. CLASS_A_SEVERE_CSD members: per-classification transform, Class A.
      5. Else (Class C default): per-classification transform.

    Raises ValueError on unrecognized classification.
    """
    if indicator_id in OUTLIER_NO_TRANSFORM:
        return IndicatorDisposition(
            indicator_id=indicator_id,
            classification=audit_classification,
            indicator_class="A",  # documentation marker; demeaning suppressed
            transform="pass_through",
        )
    if indicator_id in OUTLIER_LOG_DIFFERENCE:
        return IndicatorDisposition(
            indicator_id=indicator_id,
            classification=audit_classification,
            indicator_class="A",
            transform="log_diff",
        )

    if indicator_id in CLASS_A_SEVERE_CSD:
        cls: IndicatorClass = "A"
    elif indicator_id in CLASS_B_WGI:
        cls = "B"
    else:
        cls = "C"

    transform = _transform_for_classification(audit_classification)
    return IndicatorDisposition(
        indicator_id=indicator_id,
        classification=audit_classification,
        indicator_class=cls,
        transform=transform,
    )


def _transform_for_classification(classification: str) -> TransformKind:
    """Map Stage A audit classification → Stage C transform.

    Per Protocol 1 default: ambiguous → first_diff.
    """
    if classification == "I(0)":
        return "pass_through"
    if classification in ("I(1)", "ambiguous"):
        return "first_diff"
    if classification == "I(2)_or_higher":
        # Special case: only SP.POP.TOTL in audit v2; handled by
        # OUTLIER_LOG_DIFFERENCE before reaching here. Any other
        # I(2)_or_higher must trigger Tariq consultation per Protocol 2.
        raise ValueError(
            "I(2)_or_higher classification reached default branch — "
            "this should be handled by an outlier rule. Tariq consultation "
            "required before Stage C ships for any I(2) indicator outside "
            "OUTLIER_LOG_DIFFERENCE."
        )
    raise ValueError(f"unknown classification: {classification!r}")


# ---------------------------------------------------------------------------
# Per-country transformation (Pass 1)
# ---------------------------------------------------------------------------


def transform_panel(panel: pd.DataFrame, transform: TransformKind) -> pd.DataFrame:
    """Apply per-country transformation to a wide panel.

    Args:
        panel: rows=year, cols=country, values=indicator. May contain NaN.
        transform: pass_through | first_diff | log_diff.

    Returns: a new DataFrame with the transformation applied. NaN-safe:
    `.diff()` produces NaN at t=0, which propagates to correlation
    computation as missing data.
    """
    if transform == "pass_through":
        return panel.copy()
    if transform == "first_diff":
        return panel.diff()
    if transform == "log_diff":
        # Log-difference: log(x_t / x_{t-1}). Requires positive values;
        # NaN-propagated for non-positive entries (defensive against
        # population zero-points or anomalies).
        log_panel = np.log(panel.where(panel > 0))
        return log_panel.diff()
    raise ValueError(f"unknown transform: {transform!r}")


# ---------------------------------------------------------------------------
# Common-factor demeaning (Pass 2)
# ---------------------------------------------------------------------------


def demean_cross_section(transformed: pd.DataFrame) -> pd.DataFrame:
    """Subtract the cross-sectional mean at each time step.

    For each row (year), compute the mean across countries (NaN-safe via
    nanmean), then subtract from each country's value at that year.

    Per Priya's spec:
      ΔI*_{c,t} = ΔI_{c,t} − (1/N_t) Σ_c ΔI_{c,t}
    where N_t is the number of countries with non-null observations at t.

    Args:
        transformed: panel post-transformation (e.g., output of transform_panel).

    Returns: demeaned panel, same shape, NaN-preserved. Years with all-NaN
    rows return all-NaN (no demeaning attempted).
    """
    # Use pandas mean(axis=1, skipna=True) — equivalent to nanmean across
    # countries at each time step. Subtraction broadcasts across columns.
    cross_section_mean = transformed.mean(axis=1, skipna=True)
    return transformed.sub(cross_section_mean, axis=0)


# ---------------------------------------------------------------------------
# DSCDI computation orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DSCDIResult:
    """Outputs of run_dscdi_pass for one indicator.

    `primary` is the substrate Stage C ships to Phase 6.
    `baseline_undemeaned` is stored for ablation when indicator is Class A
    AND demeaning was actually attempted; it is None for Class B/C
    indicators (no demeaning, so primary IS the undemeaned correlation)
    AND for the NY.GDP.MKTP.KD.ZG special case (Class A but demeaning
    suppressed because the indicator is already a growth rate).

    `mean_abs_pairwise_corr` is the diagnostic Priya specified: if > 0.25
    for Class A WITH demeaning attempted, demeaning is insufficient and
    Phase 6 EB needs an architecture note.

    `demeaning_applied` distinguishes "Class A but suppressed by special
    case" (False; Phase 6 must handle CSD risk via different mechanism)
    from "Class B/C — no demeaning expected" (also False but for different
    reason — see `disposition.indicator_class`). For Phase 6 ablation
    consumers: a True value means baseline_undemeaned is populated and
    demeaning_insufficient is meaningful.
    """

    indicator_id: str
    disposition: IndicatorDisposition
    primary: pd.DataFrame  # country×country Pearson correlation
    baseline_undemeaned: pd.DataFrame | None  # only for Class A with demeaning_applied
    mean_abs_pairwise_corr: float
    demeaning_insufficient: bool
    n_countries: int
    demeaning_applied: bool


def run_dscdi_pass(
    indicator_id: str,
    panel: pd.DataFrame,
    audit_classification: str,
    min_obs: int = 15,
) -> DSCDIResult:
    """End-to-end Stage C DSCDI computation for one indicator.

    Steps:
      1. Resolve disposition (class + transform).
      2. Apply transformation (Pass 1).
      3. For Class A (excluding NY.GDP.MKTP.KD.ZG): compute baseline
         pairwise correlation on transformed series; then apply demeaning;
         then compute primary pairwise correlation on demeaned series.
      4. For Class B/C and the NY.GDP.MKTP.KD.ZG special case: compute
         primary pairwise correlation on transformed series; baseline = None.
      5. Compute mean abs pairwise correlation (excluding diagonal) on primary.
      6. Flag demeaning_insufficient if Class A WITH demeaning applied AND
         primary mean_abs > threshold.

    Args:
        indicator_id: ingested indicator id_string (e.g., "v2x_libdem").
        panel: wide panel (rows=year, cols=country).
        audit_classification: from Stage A v2 audit JSON.
        min_obs: minimum number of POST-TRANSFORMATION observations a
            country must have to participate. For first_diff and log_diff,
            the transformation produces NaN at t=0, so a country with N
            raw observations contributes N-1 transformed observations. A
            country with exactly `min_obs` raw observations is therefore
            EXCLUDED for first_diff/log_diff indicators; you need
            `min_obs + 1` raw observations to pass the filter. This
            matches the Stage A audit's filtering convention
            (qgi-ml/scripts/run_i5_substrate_audit.py also filters on
            transformed-observation count for diff tests).

    Returns: DSCDIResult with `demeaning_applied` indicating whether the
        two-pass demeaning ran (True for Class A non-OUTLIER_NO_TRANSFORM).
    """
    disposition = resolve_disposition(indicator_id, audit_classification)
    transformed = transform_panel(panel, disposition.transform)

    # Filter countries with insufficient observations (matches audit
    # min_obs convention — QA review fix #2).
    obs_per_country = transformed.notna().sum(axis=0)
    keep = obs_per_country[obs_per_country >= min_obs].index.tolist()
    sub_transformed = transformed[keep]

    # Special case: NY.GDP.MKTP.KD.ZG is Class A by lineage but is an
    # I(0) growth rate; demeaning would over-process. Skip demeaning.
    apply_demeaning = disposition.indicator_class == "A" and indicator_id not in OUTLIER_NO_TRANSFORM

    if apply_demeaning:
        baseline_corr = _pairwise_pearson(sub_transformed)
        demeaned = demean_cross_section(sub_transformed)
        primary_corr = _pairwise_pearson(demeaned)
    else:
        baseline_corr = None
        primary_corr = _pairwise_pearson(sub_transformed)

    mean_abs = _mean_abs_pairwise_off_diagonal(primary_corr)
    demeaning_insufficient = (
        disposition.indicator_class == "A"
        and apply_demeaning
        and mean_abs > PAIRWISE_CORR_DEMEANING_INSUFFICIENT_THRESHOLD
    )

    return DSCDIResult(
        indicator_id=indicator_id,
        disposition=disposition,
        primary=primary_corr,
        baseline_undemeaned=baseline_corr,
        mean_abs_pairwise_corr=mean_abs,
        demeaning_insufficient=demeaning_insufficient,
        n_countries=len(keep),
        demeaning_applied=apply_demeaning,
    )


def _pairwise_pearson(panel: pd.DataFrame) -> pd.DataFrame:
    """Country×country Pearson correlation matrix.

    Uses pandas' .corr() which is NaN-pairwise-aware: each pair uses only
    overlapping non-null years. Diagonal is 1.0 by construction.

    `min_periods=4` matches the SCDI finder's pattern-length floor
    (qgi-pipeline/batch/scdi-finder/src/scdi_finder.py uses MIN_LENGTH=3
    raw → 4 paired observations after the dropna intersect). Pairs with
    fewer overlapping observations get NaN correlation, which the
    pairwise diagnostic ignores via _mean_abs_pairwise_off_diagonal.
    """
    return panel.corr(method="pearson", min_periods=4)


def _mean_abs_pairwise_off_diagonal(corr: pd.DataFrame) -> float:
    """Mean absolute correlation excluding the diagonal.

    Priya's diagnostic: mean abs |rho_{i,j}| for i ≠ j.

    NaN handling: country pairs without enough overlapping observations
    have NaN correlation. Exclude those from the mean.
    """
    if corr.empty or len(corr) < 2:
        return 0.0
    mat = corr.values.copy()
    np.fill_diagonal(mat, np.nan)  # exclude self-correlation
    abs_off = np.abs(mat)
    if np.all(np.isnan(abs_off)):
        return 0.0
    return float(np.nanmean(abs_off))


# ---------------------------------------------------------------------------
# Audit JSON loader
# ---------------------------------------------------------------------------


def load_audit_classifications(audit_json_path: str | Path) -> dict[str, str]:
    """Read v2 audit JSON and return {indicator_id: classification}.

    Skips entries with classification in {load_failed, test_failed,
    insufficient_data} — those don't have a defensible Stage C disposition.
    """
    payload = json.loads(Path(audit_json_path).read_text(encoding="utf-8"))
    skip = {"load_failed", "test_failed", "insufficient_data"}
    out: dict[str, str] = {}
    for ind_id, rec in payload.get("results", {}).items():
        cls = rec.get("classification")
        if cls and cls not in skip:
            out[ind_id] = cls
    return out


# ---------------------------------------------------------------------------
# Stage C exit-gate diagnostic report
# ---------------------------------------------------------------------------


def build_diagnostic_report(
    results: Iterable[DSCDIResult],
) -> dict:
    """Build the Stage C exit-gate JSON per Priya's spec.

    Schema:
      {
        "schema_version": 1,
        "generator": "qgi-pipeline/batch/dscdi-finder/dscdi_finder.py",
        "threshold_demeaning_insufficient": 0.25,
        "indicators": {
          "<id>": {
            "indicator_class": "A"|"B"|"C",
            "transform": "first_diff"|"log_diff"|"pass_through",
            "n_countries": int,
            "mean_abs_pairwise_corr": float,
            "demeaning_insufficient": bool
          }, ...
        },
        "summary": {
          "n_total": int,
          "n_class_A": int,
          "n_class_B": int,
          "n_class_C": int,
          "n_demeaning_insufficient": int  # Phase 6 architecture-note count
        }
      }
    """
    results_list = list(results)
    indicators: dict[str, dict] = {}
    counts = {"A": 0, "B": 0, "C": 0}
    n_insufficient = 0
    for r in results_list:
        cls = r.disposition.indicator_class
        counts[cls] += 1
        if r.demeaning_insufficient:
            n_insufficient += 1
        indicators[r.indicator_id] = {
            "indicator_class": cls,
            "transform": r.disposition.transform,
            "audit_classification": r.disposition.classification,
            "n_countries": r.n_countries,
            "mean_abs_pairwise_corr": round(r.mean_abs_pairwise_corr, 6),
            "demeaning_applied": r.demeaning_applied,
            "demeaning_insufficient": r.demeaning_insufficient,
        }
    return {
        "schema_version": 1,
        "generator": "qgi-pipeline/batch/dscdi-finder/dscdi_finder.py",
        "threshold_demeaning_insufficient": (PAIRWISE_CORR_DEMEANING_INSUFFICIENT_THRESHOLD),
        "indicators": indicators,
        "summary": {
            "n_total": len(results_list),
            "n_class_A": counts["A"],
            "n_class_B": counts["B"],
            "n_class_C": counts["C"],
            "n_demeaning_insufficient": n_insufficient,
        },
    }
