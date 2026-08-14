"""
Phase 5 v0.2 Path B — hierarchical-Bayes partial-pooling evaluator.

Bayesian sibling of `validate_weight_matrix.py` (Path A, v6.6 with
--emit-per-cell). Path A returned INERT 4/4 on Stage F substrate at T9
(#673, qgi-data `0f8aeed`); the falsification report (T11, docs-specs
`dfe2cd4`, ratified 5/5 at `3b9221c`) fired Path B per two pre-registered
triggers (Kwame T5 §2 first-execution affirmation + Priya T7 §3
anchor-battery auto-trigger).

The contract is the Path B implementation spec at
`docs/specs/internal/ops/cascade-track/phase-5-v0.2-path-b-architecture.md`.
The spec was ratified at T10 commit `ca77505` (2026-05-14, 3/3 trio
sign-off) and AMENDED at commit `0db64f9` (2026-05-15, 6-seat Majles
unanimous SIGN-OFF on the response-variable shift `auc` → `anomaly_score`
plus surgical re-derivations of §2.1, §2.4, §2.5, §3.1, and a new §5.2
Path-B-internal closure protocol).

Ratification trail:
  - 2026-05-14 3-seat: c:/tmp/v0.2-T12-ratification/signoff_{priya,kwame,jihoon}.md
  - 2026-05-15 5-seat: c:/tmp/v0.2-T12-convergence/signoff_*.md
  - 2026-05-15 6-seat: c:/tmp/v0.2-T12-6seat/signoff_*.md
  - Closure tickets: qgi-aws-tf #684, #691, #692

What this evaluator does:
  - Builds the PyMC partial-pooling model per spec §1 with priors per §2
  - Generates a synthetic cell-level anomaly_score panel for smoke-testing
  - Loads real per-cell anomaly_score tensors from Path A v6.6 sidecar JSONs
    (`phase4-validation-arm{A,B,C,D}-v6.json` at qgi-data `14ebded`)
  - Runs NUTS with the §3.1 sampling config and emits §3.1 diagnostics

What this evaluator does NOT do (deferred per Kwame K-§2.5 pre-registration
gate ordering on the trio's real-data feature branch):
  - Execute the §2.5 sensitivity sweep (3×3×4 = 36 configurations) — sweep
    config is pinned at qgi-data/reference/v0.2-bayes-sweep-config.json
    (qgi-data `b059cd6`); MCMC against real data runs that 36-cell sweep
    plus the smoke-test gate per Ji-Hoon Move 1 round-2
  - Emit a Path B falsification verdict. The verdict gate is the 94% HDI
    on `tau_arm[A] − tau_arm[D]`, read against spec §5.2 routing thresholds
    (Miriam Move 3 / `0db64f9`)

Model statement (amended spec §1, docs-specs `0db64f9`):
    anomaly_score[arm, country, category] ~ Normal(
        mu
        + tau_arm[arm]
        + alpha_sector[sector(category)]
        + beta_cat[category]
        + country_intercept[country],
        sigma
    )

Priors (amended spec §2, docs-specs `0db64f9`):
    tau_arm[arm]         ~ Normal(0, 0.30)                     # §2.1 (was 0.05 AUC; k=5.72)
    sigma_*              ~ HalfCauchy(0.05)                    # §2.2 INVARIANT
    beta_cat[c]          ~ Normal(0, sigma_cat[sector(c)])     # §2.3 INVARIANT nested
    mu                   ~ Normal(0.168, 0.263)                # §2.4 empirical-Bayes

Empirical anchors: qgi-data/reference/v0.2-anomaly-score-empirical-range.json
(qgi-data `1a4bff5`):
  - signed pooled (arms A/B): P5..P95 = [-0.610, +0.535]; k = 5.72
  - unsigned pooled (C/D): P5..P95 = [+0.045, +1.020]; k = 4.87
  - cross-arm pooled: mu_empirical=0.1676, sigma_empirical=0.5257

Sampling config (§3.1 ratified by Ji-Hoon #21; INVARIANT under amendment):
  4 chains × 2000 iter post-warmup, warmup 1000, target_accept=0.95,
  max_treedepth=12, per-chain seeds set explicitly.

Diagnostics (§3.1 ratified by Ji-Hoon #21):
  R-hat < 1.01, n_eff > 400, divergences < 0.1 %, E-BFMI > 0.3,
  trace-plot non-stationarity inspection on country block.

Usage:
    # Smoke test (synthetic data; no real-data dependency):
    python qgi-ml/scripts/validate_weight_matrix_bayes.py --smoke

    # Real-data prep helper (loads Path A v6.6 sidecars, returns cells array;
    # does NOT run MCMC — that's gated on the trio's final prior-justification
    # sign-off on the merged amendment):
    python qgi-ml/scripts/validate_weight_matrix_bayes.py --prep-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    import arviz as az
    import pymc as pm


ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data-tools" if (ROOT / "data-tools").is_dir() else ROOT / "qgi-data"

if not DATA_DIR.is_dir():
    raise RuntimeError(
        f"ROOT resolution failed: expected sibling 'data-tools/' under {ROOT}, "
        f"but it is missing. Run this script from the QGI monorepo root."
    )

# Path A v6.6 run artifacts (input to the prep helper). Sidecar variant
# `-v6.json` carries the per-cell `anomaly_score` tensor; the v5 originals
# at `phase4-validation-arm{A,B,C,D}.json` are T11
# falsification substrate and Protocol-5 against amendment.
ARM_JSON_PATHS = {
    arm: DATA_DIR / "reference" / f"phase4-validation-arm{arm}-v6.json"
    for arm in ("A", "B", "C", "D")
}

# Deterministic sector mapping from event_category. The L1 taxonomy lives
# under data-tools/reference/event-category-l1-mapping.json; spec §1 names
# this as the load-bearing covariate that turns 68 categories into 10
# sectors. The prep helper loads it on real data; the smoke test uses a
# synthetic toy mapping.
L1_MAPPING_JSON = DATA_DIR / "reference" / "event-category-l1-mapping.json"

# Schema version for the Path B evaluator JSON output. Distinct from the
# Path A SCHEMA_VERSION; Path B starts at v1 because the output structure
# is different (posterior HDIs, not rule v2 verdicts).
PATH_B_SCHEMA_VERSION = 1

# Priors — amended at docs-specs `0db64f9` per the 2026-05-15 6-seat Majles
# convening (qgi-aws-tf#691). Amending any of these constants requires a
# new Majles convening with Priya #22, Kwame #11, Ji-Hoon #21, plus
# Roshani #18 (§2.4 author) and Miriam #14 (§5.2 author) where their
# work is impacted, per the §2 line 66 binding clause as amended.
TAU_ARM_PRIOR_SCALE = 0.30         # §2.1 amended (was 0.05 AUC-calibrated); 0.05 × k=5.72 → 0.286 → 0.30
HALF_CAUCHY_SCALE = 0.05           # §2.2 INVARIANT (Ji-Hoon Move 1 round-2 scale-invariance ruling)
MU_PRIOR_CENTER = 0.168            # §2.4 amended (was 0.30 AUC-mixture); empirical-Bayes mu_empirical=0.1676
MU_PRIOR_SCALE = 0.263             # §2.4 amended (was 0.05); 0.5 × sigma_empirical=0.5257

# Sampling config — §3.1, ratified by Ji-Hoon #21.
# Geometry block (n_chains, n_tune, n_draws, max_treedepth, non-centered
# parameterization on country_intercept_raw + beta_cat_raw) is INVARIANT
# under amendment per the 2026-05-15 6-seat Majles response-variable shift
# (Ji-Hoon Move 1 round-2 ratification).
#
# 2026-05-16 sampler-hyperparameter amendment (3-seat trio at qgi-aws-tf#744):
# TARGET_ACCEPT raised 0.95 → 0.99 to clear the v6 baseline's triple-FAIL
# diagnostic (R-hat 1.02, n_eff 388, divergences 1.89%). Authority: 3-seat
# trio (Priya #22 + Kwame #11 + Ji-Hoon #21) per Ji-Hoon §3.1-author ruling
# that target_accept is sampler-hyperparameter, not geometry. Sign-offs at
# c:/tmp/v0.2-T12-sampler-amendment/signoff_{priya,kwame,jihoon}.md.
N_CHAINS = 4
N_TUNE = 1000
N_DRAWS = 2000
TARGET_ACCEPT = 0.99    # §3.1 amended 2026-05-16 (was 0.95); 3-seat ratified at #744
MAX_TREEDEPTH = 12

# Diagnostic thresholds — §3.1, ratified by Ji-Hoon #21.
R_HAT_THRESHOLD = 1.01
N_EFF_THRESHOLD = 400
DIVERGENCE_THRESHOLD_PCT = 0.001   # < 0.1 % of post-warmup samples
E_BFMI_THRESHOLD = 0.3
# J-§3.1 (Ji-Hoon round-2 non-blocking rec from 2026-05-14, ratified
# MANDATORY at 2026-05-15 6-seat Majles + pinned at qgi-data
# `b059cd6` (v0.2-bayes-sweep-config.json `treedepth_saturation_rate_max_threshold`)):
# treedepth saturation is a hidden failure mode at max_treedepth=12 — the
# sampler hits the depth ceiling rather than converging. Flag if > 1 %.
TREEDEPTH_SATURATION_THRESHOLD = 0.01

# F-1 (QA review of PR #60; Kwame round-2 reclassified from polish to
# pre-registration-discipline gap; Ji-Hoon real-data ratification MANDATORY):
# compute_diagnostics's R-hat / n_eff gate must cover ALL 9 sampled RVs,
# not just the 4 named in the day-1 scaffold. The 272-element
# country_intercept_raw block is the precise funnel-failure site that
# non-centered parameterisation prevents; excluding it from the gate
# means a chain breakdown there silently passes while the headline params
# look fine. Verbatim from Ji-Hoon round-2 §3.1 audit:
DIAGNOSTIC_VAR_NAMES = (
    "mu",
    "tau_arm",
    "sigma_sector",
    "alpha_sector",
    "sigma_cat",
    "beta_cat_raw",
    "sigma_country",
    "country_intercept_raw",
    "sigma",
)

# Per-chain seeds. Pinned so smoke-test results reproduce across runs;
# real-data run uses these same seeds unless the trio convenes to change.
CHAIN_SEEDS = (17, 42, 123, 271)


@dataclass
class CellsArray:
    """The (n_arms, n_countries, n_categories) input the model fits against.

    `anomaly_score` is the cell-level anomaly score per (arm, country, category)
    emitted by Path A v6.6's `--emit-per-cell` flag (see
    `qgi-ml/scripts/validate_weight_matrix.py` SCHEMA_VERSION=6); cells
    with undefined score (no indicators contributing, or below the Phase 4
    minimum-observation gate) are NaN — PyMC's Normal likelihood with
    explicit NaN masking handles missing observations natively (spec §1).

    **Naming history:** at T10 spec commit `ca77505` the field was named
    `auc` per the original Path B response-variable spec. The 2026-05-15
    6-seat Majles convening (qgi-aws-tf#691) renamed the response variable
    to `anomaly_score` because ROC-AUC is mathematically undefined at
    single-observation granularity (Path A emits one anomaly_score per
    cell; AUC requires a distribution). The amended T10 spec at docs-specs
    `0db64f9` §1 reflects the rename verbatim; this dataclass field
    follows.

    `arm_labels`, `country_labels`, `category_labels` preserve the
    ordering for downstream interpretation of posterior summaries.

    `sector_idx_for_category` is the deterministic L1 mapping: each
    category index maps to one sector index in [0, n_sectors).
    """

    anomaly_score: np.ndarray  # shape (n_arms, n_countries, n_categories)
    arm_labels: list[str]
    country_labels: list[str]
    category_labels: list[str]
    sector_labels: list[str]
    sector_idx_for_category: np.ndarray  # shape (n_categories,)

    @property
    def n_arms(self) -> int:
        return len(self.arm_labels)

    @property
    def n_countries(self) -> int:
        return len(self.country_labels)

    @property
    def n_categories(self) -> int:
        return len(self.category_labels)

    @property
    def n_sectors(self) -> int:
        return len(self.sector_labels)

    def sha256_provenance(self) -> str:
        """SHA-256 of the cells array per spec §3.4 reproducibility block.

        The full input contract is `anomaly_score` shape + values + label
        ordering + sector mapping. Reviewer verifies this hash matches the
        Path A v6.6 sidecars at qgi-data/reference/phase4-validation-arm
        {A,B,C,D}-v6.json (qgi-data `14ebded`) that the implementation
        claims to fit against.
        """
        hasher = hashlib.sha256()
        hasher.update(np.ascontiguousarray(self.anomaly_score, dtype=np.float64).tobytes())
        hasher.update("|".join(self.arm_labels).encode("utf-8"))
        hasher.update("|".join(self.country_labels).encode("utf-8"))
        hasher.update("|".join(self.category_labels).encode("utf-8"))
        hasher.update("|".join(self.sector_labels).encode("utf-8"))
        hasher.update(self.sector_idx_for_category.astype(np.int64).tobytes())
        return hasher.hexdigest()


def build_model(cells: CellsArray):
    """Build the PyMC partial-pooling model per amended spec §1.

    Country block uses NON-CENTERED parameterisation (spec §3.1):
        country_intercept_raw ~ Normal(0, 1)
        country_intercept     = sigma_country * country_intercept_raw

    This avoids funnel-geometry divergences on the K ≈ 272 country block.

    Sector effects use centered parameterisation (small enough count:
    ~10 sectors). Category effects use a non-centered idiom
    (`beta_cat_raw ~ Normal(0, 1)` scaled by `sigma_cat[sector]`)
    because of the nested-hyperprior structure — functionally equivalent
    to the centered form at M ≈ 68 categories and explicitly permitted
    by Ji-Hoon §3.1's divergence-escalation clause (spec line 88's
    "centered" nomination applies to the simple case; the nested
    structure naturally lands in the scaled-raw idiom).

    Missing observations (NaN in `cells.anomaly_score`) are masked via
    PyMC's `observed` masked-array support; the posterior on tau_arm,
    alpha_sector, beta_cat, country_intercept updates from observed cells
    only — exactly the property that lets the model borrow strength
    across the sparse high-coverage / low-coverage tail (Priya T5 POV).
    """
    import pymc as pm  # local import — heavy dependency, only needed when fitting

    # Flatten cells to long form: each row is one observed anomaly_score with
    # its (arm, country, category, sector) indices. PyMC handles the missing
    # cells via the mask in `observed`, so we flatten EVERY cell (including
    # NaNs) and let PyMC's automatic-imputation pathway absorb them.
    n_arms, n_countries, n_categories = cells.anomaly_score.shape
    arm_idx, country_idx, category_idx = np.indices(cells.anomaly_score.shape)
    arm_idx_flat = arm_idx.ravel()
    country_idx_flat = country_idx.ravel()
    category_idx_flat = category_idx.ravel()
    sector_idx_flat = cells.sector_idx_for_category[category_idx_flat]
    score_flat = cells.anomaly_score.ravel()
    observed = np.ma.masked_invalid(score_flat)

    coords = {
        "arm": cells.arm_labels,
        "country": cells.country_labels,
        "category": cells.category_labels,
        "sector": cells.sector_labels,
        "obs_id": np.arange(score_flat.size),
    }

    with pm.Model(coords=coords) as model:
        # §2.4 amended (Roshani Move 2): empirical-Bayes weakly-informative
        # prior on mu, anchored at cross-arm pooled mean from
        # qgi-data/reference/v0.2-anomaly-score-empirical-range.json. The
        # mis-centering identification gambit is retired under anomaly_score
        # response (no canonical null at 0.50); arm-D unsigned-floor pins mu
        # structurally instead.
        mu = pm.Normal("mu", mu=MU_PRIOR_CENTER, sigma=MU_PRIOR_SCALE)

        # §2.1 amended (Priya Move 1): tau_arm scale 0.30 in anomaly_score
        # units (was 0.05 AUC; k=5.72 signed pooled). The 94% HDI on
        # tau_arm[A] - tau_arm[D] is the Path B falsification metric (§5.2.1).
        tau_arm = pm.Normal("tau_arm", mu=0.0, sigma=TAU_ARM_PRIOR_SCALE, dims="arm")

        # §2.2 + §2.3 INVARIANT (Ji-Hoon Move 1 round-2 scale-invariance ruling):
        # sector and category hyperpriors. Sector-level alpha shared across
        # categories; sigma_cat sector-specific to allow civil_war (high
        # heterogeneity) vs monetary_policy (low) different shrinkage.
        sigma_sector = pm.HalfCauchy("sigma_sector", beta=HALF_CAUCHY_SCALE)
        alpha_sector = pm.Normal("alpha_sector", mu=0.0, sigma=sigma_sector, dims="sector")
        sigma_cat = pm.HalfCauchy("sigma_cat", beta=HALF_CAUCHY_SCALE, dims="sector")
        beta_cat_raw = pm.Normal("beta_cat_raw", mu=0.0, sigma=1.0, dims="category")
        # Nested: each category's beta scaled by its own sector's sigma_cat
        beta_cat = pm.Deterministic(
            "beta_cat",
            beta_cat_raw * sigma_cat[cells.sector_idx_for_category],
            dims="category",
        )

        # §3.1: non-centered country block — avoids funnel divergences
        # on the K ≈ 272 country block.
        sigma_country = pm.HalfCauchy("sigma_country", beta=HALF_CAUCHY_SCALE)
        country_intercept_raw = pm.Normal(
            "country_intercept_raw", mu=0.0, sigma=1.0, dims="country"
        )
        country_intercept = pm.Deterministic(
            "country_intercept",
            sigma_country * country_intercept_raw,
            dims="country",
        )

        # Likelihood. Cells with NaN observed are imputed by PyMC's
        # automatic-imputation pathway; posterior on the named params
        # updates from observed cells only.
        sigma = pm.HalfCauchy("sigma", beta=HALF_CAUCHY_SCALE)
        mean = (
            mu
            + tau_arm[arm_idx_flat]
            + alpha_sector[sector_idx_flat]
            + beta_cat[category_idx_flat]
            + country_intercept[country_idx_flat]
        )
        pm.Normal("anomaly_score_obs", mu=mean, sigma=sigma, observed=observed, dims="obs_id")

    return model


def sample_posterior(model, *, draws: int = N_DRAWS, tune: int = N_TUNE,
                     chains: int = N_CHAINS, seeds: tuple[int, ...] = CHAIN_SEEDS):
    """NUTS sampling with the §3.1 ratified config.

    Returns an arviz InferenceData object.
    """
    import pymc as pm  # local import

    if len(seeds) < chains:
        raise ValueError(f"Need at least {chains} per-chain seeds, got {len(seeds)}")

    with model:
        # PyMC 5.x routes step-method-scoped kwargs via the `nuts=` dict;
        # `target_accept` is a `pm.sample` top-level kwarg but
        # `max_treedepth` is NUTS-only. See:
        # https://www.pymc.io/projects/docs/en/v5.16.2/api/generated/pymc.sampling.mcmc.sample.html
        # progressbar=True forces per-iteration stdout so long Python-only
        # NUTS runs are diagnosable mid-flight; the §3.1 production run can
        # override this back to False if needed for log noise.
        idata = pm.sample(
            draws=draws,
            tune=tune,
            chains=chains,
            cores=1,  # one chain at a time so the progressbar isn't garbled
            random_seed=list(seeds[:chains]),
            target_accept=TARGET_ACCEPT,
            nuts={"max_treedepth": MAX_TREEDEPTH},
            progressbar=True,
            return_inferencedata=True,
        )
    return idata


def compute_diagnostics(idata, *, var_names: tuple[str, ...] | None = None) -> dict:
    """Extract the §3.1 diagnostic suite ratified by Ji-Hoon #21, with the
    F-1 (QA) + J-§3.1 (Ji-Hoon) extensions ratified MANDATORY by the
    2026-05-15 6-seat Majles (qgi-aws-tf#691).

    Returns a dict with the named thresholds and PASS/FAIL per diagnostic
    so the smoke-test output (and the eventual real-data run) can be
    grepped by the PR-description / reviewer / regression-fixture pipeline.

    Diagnostic suite covers ALL 9 sampled RVs by default (per F-1):
        mu, tau_arm, sigma_sector, alpha_sector, sigma_cat, beta_cat_raw,
        sigma_country, country_intercept_raw, sigma
    The country_intercept_raw block (272 params at K=272) is the precise
    funnel-failure site that non-centered parameterisation prevents;
    excluding it from the R-hat / n_eff gate silently passes a chain
    breakdown there. Override `var_names` only for diagnostic-mode runs
    where the trio explicitly accepts a narrower sweep.

    Treedepth saturation rate (J-§3.1) flags the hidden failure mode at
    max_treedepth=12 where the sampler hits the depth ceiling rather than
    converging. Threshold pinned at 1 % (Ji-Hoon round-2 ratified by the
    6-seat as MANDATORY; matches `treedepth_saturation_rate_max_threshold`
    at qgi-data `b059cd6`).
    """
    import arviz as az  # local import

    diag_vars = list(var_names) if var_names is not None else list(DIAGNOSTIC_VAR_NAMES)
    summary = az.summary(idata, var_names=diag_vars)
    max_r_hat = float(summary["r_hat"].max())
    min_n_eff = float(summary["ess_bulk"].min())

    sample_stats = idata.sample_stats
    n_post_warmup = sample_stats.draw.size * sample_stats.chain.size
    n_divergences = int(sample_stats.diverging.sum().item())
    divergence_pct = n_divergences / n_post_warmup if n_post_warmup else float("nan")

    # E-BFMI — energy-based fraction of missing information per chain.
    # Ji-Hoon §3.1: > 0.3 per chain is healthy.
    e_bfmi = az.bfmi(idata)
    min_e_bfmi = float(np.min(e_bfmi))

    # J-§3.1 treedepth saturation rate. PyMC emits the per-iteration tree
    # depth at `sample_stats.tree_depth` (xarray DataArray over chains x
    # draws). A draw "saturates" when tree_depth == max_treedepth (PyMC
    # internally clamps; saturation is a near-divergence signal).
    if "tree_depth" in sample_stats.data_vars:
        max_observed_treedepth = int(sample_stats.tree_depth.max().item())
        n_saturated = int((sample_stats.tree_depth >= MAX_TREEDEPTH).sum().item())
        treedepth_saturation_rate = (
            n_saturated / n_post_warmup if n_post_warmup else float("nan")
        )
    else:
        # Older PyMC versions or sampler backends may not emit tree_depth;
        # emit NaN and a FAIL verdict so the trio's PR review surfaces it.
        max_observed_treedepth = -1
        n_saturated = -1
        treedepth_saturation_rate = float("nan")

    return {
        "max_r_hat": max_r_hat,
        "min_n_eff": min_n_eff,
        "n_divergences": n_divergences,
        "divergence_pct": divergence_pct,
        "min_e_bfmi": min_e_bfmi,
        "n_post_warmup_samples": n_post_warmup,
        # J-§3.1 NEW (6-seat ratified MANDATORY):
        "max_observed_treedepth": max_observed_treedepth,
        "n_treedepth_saturated": n_saturated,
        "treedepth_saturation_rate": treedepth_saturation_rate,
        # F-1: report which variables were covered by the R-hat / n_eff gate
        "var_names_in_gate": diag_vars,
        "thresholds": {
            "r_hat_max": R_HAT_THRESHOLD,
            "n_eff_min": N_EFF_THRESHOLD,
            "divergence_pct_max": DIVERGENCE_THRESHOLD_PCT,
            "e_bfmi_min": E_BFMI_THRESHOLD,
            "treedepth_saturation_rate_max": TREEDEPTH_SATURATION_THRESHOLD,
        },
        "verdicts": {
            "r_hat": "PASS" if max_r_hat < R_HAT_THRESHOLD else "FAIL",
            "n_eff": "PASS" if min_n_eff > N_EFF_THRESHOLD else "FAIL",
            "divergences": "PASS" if divergence_pct < DIVERGENCE_THRESHOLD_PCT else "FAIL",
            "e_bfmi": "PASS" if min_e_bfmi > E_BFMI_THRESHOLD else "FAIL",
            # NaN comparisons return False; FAIL means we couldn't measure,
            # which is itself a fail per Ji-Hoon round-2 — better to halt
            # the run than fly blind.
            "treedepth_saturation": (
                "PASS" if (not np.isnan(treedepth_saturation_rate)
                           and treedepth_saturation_rate < TREEDEPTH_SATURATION_THRESHOLD)
                else "FAIL"
            ),
        },
    }


def make_synthetic_cells(*, n_countries: int = 30, n_categories: int = 12,
                         n_sectors: int = 4, missing_rate: float = 0.30,
                         seed: int = 42) -> CellsArray:
    """Generate a small synthetic panel for smoke-testing.

    Structure mirrors the real shape (4 arms, K countries, M categories,
    nested into S sectors) but at small enough size that NUTS converges
    in seconds rather than minutes. Smoke test verifies the model
    SCAFFOLD works end-to-end; the trio's eventual real-data run will
    exercise it at K ≈ 272, M ≈ 68, S = 10.

    The simulated DGP plants a known tau_arm = (+0.04, +0.02, -0.01, 0.0)
    so the smoke test's posterior recovers a recognizable arm-A-vs-arm-D
    swing — convenient for the reviewer to eyeball.
    """
    rng = np.random.default_rng(seed)
    arm_labels = ["A", "B", "C", "D"]
    country_labels = [f"C{i:03d}" for i in range(n_countries)]
    category_labels = [f"cat_{i:02d}" for i in range(n_categories)]
    sector_labels = [f"sec_{i}" for i in range(n_sectors)]

    # Round-robin category → sector mapping
    sector_idx_for_category = np.array(
        [i % n_sectors for i in range(n_categories)], dtype=np.int64
    )

    # Ground-truth DGP per spec §1 structure
    true_mu = 0.50
    true_tau_arm = np.array([0.04, 0.02, -0.01, 0.0])  # A−D ≈ 0.04
    true_alpha_sector = rng.normal(0, 0.05, size=n_sectors)
    true_beta_cat = rng.normal(0, 0.05, size=n_categories)
    true_country_intercept = rng.normal(0, 0.05, size=n_countries)
    true_sigma = 0.03

    scores = np.full((4, n_countries, n_categories), np.nan)
    for arm in range(4):
        for country in range(n_countries):
            for category in range(n_categories):
                sector = sector_idx_for_category[category]
                mean = (
                    true_mu
                    + true_tau_arm[arm]
                    + true_alpha_sector[sector]
                    + true_beta_cat[category]
                    + true_country_intercept[country]
                )
                scores[arm, country, category] = rng.normal(mean, true_sigma)

    # Drop `missing_rate` fraction to NaN, simulating the sparse panel
    mask = rng.random(scores.shape) < missing_rate
    scores[mask] = np.nan

    return CellsArray(
        anomaly_score=scores,
        arm_labels=arm_labels,
        country_labels=country_labels,
        category_labels=category_labels,
        sector_labels=sector_labels,
        sector_idx_for_category=sector_idx_for_category,
    )


def load_l1_mapping() -> dict[str, str]:
    """Load the deterministic event_category → sector L1 mapping.

    Real-data prep helper uses this. Falls back to an empty dict if the
    file doesn't exist yet (which is fine for smoke testing).
    """
    if not L1_MAPPING_JSON.exists():
        return {}
    with L1_MAPPING_JSON.open(encoding="utf-8") as fh:
        data = json.load(fh)
    # Expected shape: {"mapping": {category_name: sector_name, ...}}
    return data.get("mapping", data)


def _sector_for_category(category: str, l1_mapping: dict[str, str]) -> str:
    """Resolve a category to its sector via the L1 mapping.

    If the category is not in the mapping, the category itself is returned
    as a 1-category sector — degraded but well-formed (the partial-pooling
    model still runs; the sector hyperprior just has no peers to pool
    across for that category). The trio's PR review verifies the L1 mapping
    is complete before MCMC fires.
    """
    return l1_mapping.get(category, category)


def prep_cells_from_arm_jsons(
    arm_paths: dict[str, Path] | None = None,
    l1_mapping: dict[str, str] | None = None,
) -> CellsArray:
    """Convert the four Path A v6.6 sidecar JSONs into a CellsArray.

    Loads `per_cell.cells` lists from each per-arm v6 sidecar JSON
    (default: `qgi-data/reference/phase4-validation-arm{A,B,C,D}-v6.json`
    at qgi-data `14ebded`), pivots each arm's flat list to a (country,
    category) grid, stacks the 4 arm grids into a 3D tensor with shape
    (n_arms, n_countries, n_categories), and returns it as a CellsArray
    consumable by `build_model`.

    **Cell semantics** (post-amendment spec §1, docs-specs `0db64f9`):
    each cell is a per-(arm, country, event_category) `anomaly_score`
    emitted by Path A v6.6's `--emit-per-cell` flag. Cells missing for
    an arm (a (country, category) pair that didn't appear in that arm's
    cells list — typically because n_indicators_used was 0) are NaN;
    PyMC's automatic-imputation pathway absorbs them. Per Priya's T5 POV
    citation in spec §1: "a hierarchical-Bayes model does not need 30
    cells in a stratum because it borrows strength across cells."

    **Universe construction:** the (country, category) grid is the union
    of all four arms' cells. This guarantees a single consistent grid
    across arms (each arm's `per_cell.cells` list has the same length —
    12,250 at qgi-data `14ebded` — but the helper does not assume
    cross-arm cell-set equality; it constructs the union for robustness).

    **Sector derivation:** each category resolves to a sector via the L1
    mapping at `L1_MAPPING_JSON`. If `l1_mapping` is None, this helper
    loads the file via `load_l1_mapping()`. Categories not in the
    mapping become 1-category sectors (degraded but well-formed; the
    trio's PR review verifies the mapping is complete before MCMC fires).

    Args:
        arm_paths: dict mapping arm letter to JSON path. Default:
            ARM_JSON_PATHS pointing at qgi-data v6 sidecars.
        l1_mapping: dict mapping event_category to sector_name. Default:
            loaded via load_l1_mapping().

    Returns:
        A CellsArray with shape (4, n_countries, n_categories) where
        each cell carries the per-arm anomaly_score (or NaN for missing).

    Raises:
        FileNotFoundError: if any arm's JSON is missing.
        KeyError: if an arm JSON doesn't carry a `per_cell` block (i.e.,
            wasn't generated with --emit-per-cell).
    """
    paths = arm_paths if arm_paths is not None else ARM_JSON_PATHS
    missing = [arm for arm, p in paths.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing per-arm v6 sidecar JSONs for arms {missing}; expected at {paths}. "
            "Run Path A v6.6 first with --emit-per-cell, or use --smoke for synthetic data."
        )

    # Load each arm JSON + extract the per_cell.cells list.
    arm_letters = sorted(paths.keys())  # canonical order A, B, C, D
    arm_cells: dict[str, list[dict]] = {}
    for arm in arm_letters:
        with paths[arm].open(encoding="utf-8") as fh:
            data = json.load(fh)
        if "per_cell" not in data:
            raise KeyError(
                f"Arm {arm} JSON at {paths[arm]} has no 'per_cell' block. "
                "Re-run Path A v6.6 with --emit-per-cell flag."
            )
        arm_cells[arm] = data["per_cell"]["cells"]

    # Build the union universe of (country_id, event_category) pairs across
    # all 4 arms. OrderedDict preserves first-seen order which is stable
    # given canonical arm iteration.
    country_set: OrderedDict[int, None] = OrderedDict()
    category_set: OrderedDict[str, None] = OrderedDict()
    for arm in arm_letters:
        for cell in arm_cells[arm]:
            country_set[int(cell["country_id"])] = None
            category_set[str(cell["event_category"])] = None

    # Sort for deterministic ordering across runs.
    country_labels = [str(cid) for cid in sorted(country_set.keys())]
    country_id_to_idx = {int(c): i for i, c in enumerate(country_labels)}
    category_labels = sorted(category_set.keys())
    category_to_idx = {c: i for i, c in enumerate(category_labels)}

    n_countries = len(country_labels)
    n_categories = len(category_labels)

    # Pivot each arm to the (country, category) grid; stack into 3D.
    score_tensor = np.full((4, n_countries, n_categories), np.nan, dtype=np.float64)
    for arm_idx, arm in enumerate(arm_letters):
        for cell in arm_cells[arm]:
            cid = int(cell["country_id"])
            cat = str(cell["event_category"])
            score = cell["anomaly_score"]
            # Float-cast guards against numpy-typed JSON values; None becomes NaN.
            score_tensor[arm_idx, country_id_to_idx[cid], category_to_idx[cat]] = (
                float(score) if score is not None else np.nan
            )

    # Derive sector labels + sector_idx_for_category via the L1 mapping.
    if l1_mapping is None:
        l1_mapping = load_l1_mapping()
    sector_for_category = [_sector_for_category(cat, l1_mapping) for cat in category_labels]
    # Stable-ordered unique sector list (preserves first-seen order from category iteration).
    sector_seen: OrderedDict[str, None] = OrderedDict()
    for s in sector_for_category:
        sector_seen[s] = None
    sector_labels = list(sector_seen.keys())
    sector_to_idx = {s: i for i, s in enumerate(sector_labels)}
    sector_idx_for_category = np.array(
        [sector_to_idx[s] for s in sector_for_category], dtype=np.int64
    )

    return CellsArray(
        anomaly_score=score_tensor,
        arm_labels=arm_letters,
        country_labels=country_labels,
        category_labels=category_labels,
        sector_labels=sector_labels,
        sector_idx_for_category=sector_idx_for_category,
    )


def run_smoke_test() -> dict:
    """End-to-end smoke test: synthetic data → model → NUTS → diagnostics.

    Smaller N than the real run for speed (smoke target: < 5 min on a
    workstation CPU with C-compiled NUTS; ~10-30 min on Python-only NUTS).
    Verifies the scaffold's plumbing: model builds, chains run, diagnostics
    emit, recovered tau_arm[A] - tau_arm[D] is in the expected direction.

    Returns a dict suitable for piping into the PR description.

    Progress logging is verbose by design — Python-only NUTS (when
    pytensor cannot find g++) can take hours per chain, and silent
    long-running smoke tests are unobservable. Every phase prints with a
    wall-time delta so a stalled run is diagnosable at a glance.
    """
    import time as _time

    t0 = _time.time()

    def _log(msg: str) -> None:
        elapsed = _time.time() - t0
        print(f"[smoke t+{elapsed:6.1f}s] {msg}", flush=True)

    started_at = datetime.now(timezone.utc).isoformat()
    _log("generating synthetic cells (30 countries x 12 categories x 4 arms)...")
    cells = make_synthetic_cells(n_countries=30, n_categories=12, n_sectors=4)
    cells_hash = cells.sha256_provenance()

    _log(f"cells shape: {cells.anomaly_score.shape}")
    _log(f"non-NaN cells: {int(np.sum(~np.isnan(cells.anomaly_score)))}/{cells.anomaly_score.size}")
    _log(f"cells SHA-256: {cells_hash}")

    _log("building PyMC partial-pooling model (compiling pytensor graph)...")
    model = build_model(cells)
    _log("model built; entering sampling phase")

    # Smoke-test sampling config: deliberately tiny so Python-only NUTS
    # finishes in minutes, not hours. 2 chains is the minimum for R-hat
    # to be defined; 200 draws + 200 tune is enough for divergences and
    # E-BFMI to be meaningful as a "does the scaffold work" smoke. The
    # §3.1 ratified config (4 chains x 2000 + 1000 tune) is what the T12
    # trio's real-data run uses — those constants stay locked at the
    # module level.
    smoke_chains = 2
    smoke_draws = 200
    smoke_tune = 200
    _log(f"sampling {smoke_chains} chains x {smoke_draws} draws "
         f"(tune {smoke_tune}); progressbar enabled for visibility...")
    idata = sample_posterior(model, draws=smoke_draws, tune=smoke_tune,
                             chains=smoke_chains)
    _log("sampling complete")

    _log("computing diagnostics (R-hat, n_eff, divergences, E-BFMI)...")
    diagnostics = compute_diagnostics(idata)
    _log(f"diagnostics: max_r_hat={diagnostics['max_r_hat']:.4f}, "
         f"min_n_eff={diagnostics['min_n_eff']:.1f}, "
         f"divergences={diagnostics['n_divergences']}, "
         f"min_e_bfmi={diagnostics['min_e_bfmi']:.3f}, "
         f"treedepth_saturation_rate={diagnostics['treedepth_saturation_rate']:.4f} "
         f"({diagnostics['verdicts']['treedepth_saturation']})")

    # Headline posterior: tau_arm[A] - tau_arm[D] HDI
    import arviz as az  # local import

    _log("computing 94% HDI on tau_arm[A] - tau_arm[D] (the Path B headline metric)...")
    tau_arm_samples = idata.posterior["tau_arm"]
    # F-3 (QA review of PR #60; ratified MANDATORY at 2026-05-15 6-seat):
    # xarray subtraction does not reliably preserve the DataArray `.name`
    # attribute across versions. Without the explicit .rename, ArviZ ≥ 0.16
    # may key the returned Dataset under "x" or raise KeyError. Renaming
    # to "tau_arm_A_minus_D" makes the downstream lookup deterministic.
    a_minus_d = (
        tau_arm_samples.sel(arm="A") - tau_arm_samples.sel(arm="D")
    ).rename("tau_arm_A_minus_D")
    hdi_94 = az.hdi(a_minus_d, hdi_prob=0.94)
    # arviz's hdi returns a Dataset keyed by the input DataArray's name
    hdi_low = float(hdi_94["tau_arm_A_minus_D"].sel(hdi="lower").item())
    hdi_high = float(hdi_94["tau_arm_A_minus_D"].sel(hdi="higher").item())
    posterior_mean_a_minus_d = float(a_minus_d.mean().item())
    _log(f"posterior tau_arm[A]-tau_arm[D]: mean={posterior_mean_a_minus_d:+.4f}, "
         f"94% HDI=[{hdi_low:+.4f}, {hdi_high:+.4f}] (DGP planted +0.04)")

    finished_at = datetime.now(timezone.utc).isoformat()
    result = {
        "schema_version": PATH_B_SCHEMA_VERSION,
        "smoke_test": True,
        "started_at": started_at,
        "finished_at": finished_at,
        "cells": {
            "shape": list(cells.anomaly_score.shape),
            "n_non_nan": int(np.sum(~np.isnan(cells.anomaly_score))),
            "sha256": cells_hash,
        },
        "true_tau_a_minus_d_dgp": 0.04,  # planted ground truth from make_synthetic_cells
        "posterior_a_minus_d": {
            "mean": posterior_mean_a_minus_d,
            "hdi_94_low": hdi_low,
            "hdi_94_high": hdi_high,
        },
        "diagnostics": diagnostics,
        "config_under_test": {
            "n_chains_smoke": smoke_chains,
            "n_draws_smoke": smoke_draws,
            "n_tune_smoke": smoke_tune,
            "target_accept": TARGET_ACCEPT,
            "max_treedepth": MAX_TREEDEPTH,
            "chain_seeds": list(CHAIN_SEEDS[:smoke_chains]),
        },
        "production_config_ratified_at_t10_ca77505": {
            "n_chains": N_CHAINS,
            "n_draws": N_DRAWS,
            "n_tune": N_TUNE,
            "target_accept": TARGET_ACCEPT,
            "max_treedepth": MAX_TREEDEPTH,
        },
        "priors": {
            "tau_arm_scale": TAU_ARM_PRIOR_SCALE,
            "half_cauchy_scale": HALF_CAUCHY_SCALE,
            "mu_center": MU_PRIOR_CENTER,
            "mu_scale": MU_PRIOR_SCALE,
        },
        "spec_commit": "0db64f9 (docs-specs amended T10; was ca77505)",
        "ratification": "6/6 unanimous 2026-05-15 (Priya #22, Roshani #18, Ji-Hoon #21, Miriam #14, Tariq #20, Kwame #11)",
    }

    return result


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 5 v0.2 Path B partial-pooling evaluator"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--smoke", action="store_true",
                       help="Run end-to-end smoke test on synthetic data")
    group.add_argument("--prep-only", action="store_true",
                       help="Load real Path A v6.6 sidecar JSONs and print "
                            "cells-array shape; does NOT run MCMC (gated on "
                            "T12 trio's final prior-justification sign-off)")
    parser.add_argument("--output-json", type=Path, default=None,
                        help="Optional path to write the smoke-test result JSON")
    args = parser.parse_args(argv)

    if args.smoke:
        result = run_smoke_test()
        print(json.dumps(result, indent=2, default=str))
        if args.output_json is not None:
            args.output_json.write_text(json.dumps(result, indent=2, default=str),
                                        encoding="utf-8")
        all_pass = all(v == "PASS" for v in result["diagnostics"]["verdicts"].values())
        return 0 if all_pass else 1

    if args.prep_only:
        cells = prep_cells_from_arm_jsons()
        print(f"cells shape: {cells.anomaly_score.shape}")
        print(f"n_countries: {cells.n_countries}")
        print(f"n_categories: {cells.n_categories}")
        print(f"n_sectors: {cells.n_sectors}")
        print(f"non-NaN cells: {int(np.sum(~np.isnan(cells.anomaly_score)))}/{cells.anomaly_score.size}")
        print(f"SHA-256 provenance: {cells.sha256_provenance()}")
        return 0

    return 2  # unreachable due to required mutually-exclusive group


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
