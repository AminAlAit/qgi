"""F-ML-1 per-recipe ML loop PoC driver.

Per `docs/specs/internal/ops/ml-track/F-ML-1-pre-reg.md` (ratified 8/8 2026-05-21).

Parameterized for any recipe whose per-recipe pre-reg has been 3-seat
mechanics Majles ratified. Default values preserve civil_war_and_insurgency
backward compatibility. Override via CLI flags for other recipes.

Implements:
  §3.1  three-gate LOCK criterion (Global LOCO + per-cohort LOCO + per-cohort ECE)
  §4    architecture menu {LR, XGBoost, MLP} with mechanical fold-variance trigger
  §5    hybrid greedy outer + L1 inner; full LOCO no subsampling; window grid
  §6    descriptive emit with full-window per-tertile trajectory signature
  §10   DECISION-file-ready output JSON

Bindings honored:
  - Tariq T20-1/2: no same-walk-data amendments; positive provenance required
  - Ji-Hoon R1: DEPRECATED via F-ML-N §4.2 amendment 2026-05-22; XGBoost is now
    binding for N_pos>=60; fold-variance is informational diagnostic only (§4.2-SD)
  - Ji-Hoon R2: full LOCO across all 9 windows; no subsampling
  - Miriam M14-1: full-window per-tertile temporal profile in trajectory signature
  - Roshani R18-A/B: BCa bootstrap (B=2000); window_ci method explicit
  - Marcus M8-1/2: per-recipe floor provenance annotation; unified field-3 schema
  - Nasrin N-2: window_search_auxiliary_note in DECISION emit

F-ML-N §4.2 amendment 2026-05-22 (qgi-aws-tf#864, 8/8 ratified):
  - Original §4.2 fold-variance MLP trigger (threshold 0.05) REMOVED
  - XGBoost is binding for N_pos>=60; no automatic architecture swap
  - New §4.2-SD: mandatory stability diagnostic (LOW/MODERATE/HIGH labels);
    does NOT gate architecture; informational only
  - MLP not eliminated from menu; reintroduction requires F-ML-N+1 pre-reg
  - Amendment artifact: docs/specs/internal/decisions/artifacts/F-ML-N-§4.2-amendment-2026-05-22.md

Mechanical correctness fix (2026-05-22): country_id normalization replaces `_`
with ` ` before `.title()` to match parquet panel + cohort-assignments format.
Discovered pre-walk-2 during econ_recession pre-reg prep. Civil_war walk-1 ran
WITHOUT this fix; its DECISION stands as ratified (the bug did not alter
HARD_FAIL routing). See per-recipe-pre-reg/economic-recession-pre-reg.md §3.a.

Run-time: multi-hour laptop. Zero AWS spend.

Usage (civil_war defaults):
    python scripts/run_f_ml_1_poc.py \\
        --output-dir ../docs/specs/internal/ops/ml-track/results/f-ml-1-poc/

Usage (economic_recession, per-recipe pre-reg values):
    python scripts/run_f_ml_1_poc.py \\
        --recipe-id economic_recession \\
        --hybrid-baseline 0.4784 \\
        --lock-floor 0.65 \\
        --cohort-loco-floor 0.60 \\
        --output-dir ../docs/specs/internal/ops/ml-track/results/f-ml-1-econ-rec/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

# Pin BLAS/OpenMP to one thread *around each model fit* so the parallel grid (#961) does not
# oversubscribe the box: N joblib threads each spawning N BLAS threads = N² (e.g. 16×16=256 on
# a 16-core canary). Pinning to 1 is bit-identical for the fleet's XGBoost path (n_estimators
# fixed, exact tree method, seeded; thread count does not change the result) and removes the
# contention that made the parallel walk run *slower* than a single laptop core. threadpoolctl
# is an optional dep: if absent (older local env), fall back to a no-op so the walk still runs.
try:
    from threadpoolctl import threadpool_limits as _threadpool_limits
except ImportError:  # pragma: no cover - exercised only where the dep is missing
    from contextlib import contextmanager

    @contextmanager
    def _threadpool_limits(*_args, **_kwargs):
        yield

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for _p in (SCRIPTS_ROOT, SRC_ROOT, REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# #969: Beta calibration emit. Imported under an explicit `_beta_cal` alias so the
# call site at the summary dict (search for `_beta_cal.compute_calibration_block`)
# is unambiguous about the source module. Placed AFTER the SRC_ROOT path setup
# above so no second `sys.path.insert` is needed (QA PR#124 FU-1).
import beta_calibration as _beta_cal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("f-ml-1-poc")

# ---- F-ML-1 pre-reg binding constants ---------------------------------------

# Default values match civil_war_and_insurgency walk-1 (preserved for backward
# compatibility). For other recipes, override RECIPE_ID + HYBRID_BASELINE +
# LOCK_FLOOR + COHORT_LOCO_FLOOR via CLI flags. Each per-recipe pre-reg must
# be 3-seat mechanics Majles ratified before the corresponding walk fires
# (per F-ML-1 §2.5 + Marcus M8-1).
DEFAULT_RECIPE_ID = "civil_war_and_insurgency"

# §7 PoC scope (civil_war defaults)
DEFAULT_HYBRID_BASELINE = 0.7686  # per-recipe floor provenance: cascade-inherited (Marcus M8-1 path (a))
DEFAULT_LOCK_FLOOR = 0.7986       # HYBRID_BASELINE + 0.03

# §3.1 per-cohort floors (civil_war defaults)
DEFAULT_COHORT_LOCO_FLOOR = 0.68  # Kwame R1, civil_war-anchored
COHORT_ECE_GATE = 0.08            # F-H-7 inherited (not recipe-specific)

# Sample-truncation fix (bugfix amendment 2026-05-25; Majles 5/5, Miriam binding-veto).
# "No silent sample restriction": a walk must never graduate on a coverage-truncated
# subsample (the foreign_intervention 0.9147-on-10-of-174 defect). See the
# 2026-05-25 truncation-leak DECISION + per-recipe-pre-reg/fleet-floor-annex.md.
MIN_POS_SURVIVAL = 0.50        # ≥50% of raw positives must survive build_X_y (Miriam)
MIN_EFFECTIVE_NPOS = 30        # ≥30 surviving positives for a meaningful LOCO (Ji-Hoon/Kwame)
MIN_SURVIVE_COUNTRIES = 10     # ≥10 surviving countries (Miriam MR-14-A3 charter coherence)
MIN_NEG_SURVIVAL = 0.60  # ≥60% of NEGATIVES must survive build_X_y (Ji-Hoon/Kwame fix B;
                         # renamed from MIN_INDICATOR_COVERAGE per Kwame KA-1, Majles 2026-05-25:
                         # the name now states what it gates — negative-class survival fraction.
                         # At the univariate screen this is the single indicator's neg-coverage;
                         # in coverage_gate_ok it is the selected set's neg-class survival.)

# Chance-baseline gate (MR-14-A2, bugfix amendment 2026-05-25). A walk whose global
# LOCO 95% CI includes chance (0.50) is statistically indistinguishable from a coin
# flip — it must NOT graduate, regardless of point estimate. This is the gate that
# catches the foreign_intervention failure mode ONCE the coverage gate has forced the
# full untruncated sample: the inflated 0.9147 was on 10/174 positives; on the full
# history the AUC is ≈0.4967 with a CI straddling 0.50. Blocking; overrides LOCK.
CHANCE_FLOOR = 0.50

# §5 indicator selection
TOP_N_PREFILTER = 40
DELTA_STEP = 0.005  # greedy outer-loop stopping
THIN_RECIPE_CAP = 5  # N_pos < 60 → outer loop cap

# Floor-aware early-abort (FLEET-3, QGI-R&D | 002, 2026-05-27).
# A walk whose remaining greedy steps cannot reach lock_floor — even under the
# optimistic assumption that every future step gains the best single-step lift seen
# so far — is treated as HARD_FAIL-bound; we abort it to stop burning compute on the
# doomed deep tail (constitutional_change ground 32h+ this way: its per-step lifts
# stayed above delta_step so the natural halt never fired, yet the floor was already
# out of reach).
#
# HONESTY ON THE BOUND (PR #116 review, 2026-05-27): the optimistic ceiling is a
# CONSERVATIVE HEURISTIC, **not** a strict mathematical upper bound. With a non-linear
# model (XGBoost) a future single-step lift CAN exceed observed_max_lift via interaction
# effects (an indicator weak alone but strong once others are selected). So the abort is
# outcome-neutral *in the common case* (flat/declining lifts, floor far below the
# ceiling) but could, in a narrow near-floor case, wrongly abort a recipe an interaction
# burst would have rescued. Mitigated by: (1) the MIN_STEPS_BEFORE_ABORT grace period;
# (2) using the all-time MAX lift (full benefit of the doubt); (3) the abort fires
# hardest where the floor gap is LARGE — exactly where an interaction rescue is least
# plausible — and is most lenient where the gap is small. The §2.5 classification
# (amendment-free vs pre-registered vs route-to-INCOMPLETE-not-HARD_FAIL) is referred to
# a Ji-Hoon/Kwame ruling before this is relied on in the fan-out; see PR #116 / FLEET-3.
MIN_STEPS_BEFORE_ABORT = 3

# §5.4 window grid
WINDOW_GRID = [3, 5, 7, 10, 12, 15, 18, 21, 25]

# Per-indicator feature block size (run-3.1 banking wide-net fix #1, 2026-07-10).
# Extended 8->10: appended two EXPLICIT lag features (z-score at year-2 and year-3;
# year-1 was already covered by `last_z`) to the end of the existing 8-feature block
# so all pre-existing positional slots (0-7) are UNCHANGED — only two new slots (8,9)
# are added. `extract_features_for_indicator` / `build_X_y` / `emit_descriptive` all
# key off this single constant so the block size is never hard-coded in more than one
# place inside this module. NOTE: downstream production scripts outside this module
# (scripts/score_countries.py, scripts/extract_shap_importances.py) still hard-code a
# LOCAL "8 features per indicator" assumption for SHAP/importance aggregation on
# ALREADY-GRADUATED recipes (civil_war etc.) that were walked under the old 8-feature
# block — they are UNCHANGED here (out of scope for the banking wide-net run) but MUST
# be updated in lockstep before any future walk output produced under this 10-feature
# block is fed through them, or their per-indicator grouping will silently misalign.
N_FEATURES_PER_INDICATOR = 10

# §4.2 MLP fold-variance trigger — DEPRECATED 2026-05-22 per F-ML-N amendment
# (qgi-aws-tf#864). XGBoost is now binding for N_pos>=60; no automatic MLP swap.
# Constant retained as a historical record only (not referenced in active code).
# See docs/specs/internal/decisions/artifacts/F-ML-N-§4.2-amendment-2026-05-22.md
MLP_FOLD_VARIANCE_TRIGGER_DEPRECATED = 0.05  # noqa: F841 — kept for archival reference

# §3.1 Roshani R18-A bootstrap
BCA_BOOTSTRAP_B = 2000

# Country-name normalization overrides (2026-05-22).
# Naive `country_id.replace("_", " ").title()` fails for 4 country_ids whose
# canonical forms in the parquet panels + cohort-assignments.json use hyphens
# or lowercase conjunctions/articles. Verified by enumeration over all
# positives.csv country_ids vs panel_set × cohort_assignments_set. See
# `docs/specs/internal/ops/ml-track/per-recipe-pre-reg/economic-recession-pre-reg.md` §3.a.
COUNTRY_NAME_OVERRIDES: dict[str, str] = {
    "democratic_republic_of_congo": "The Democratic Republic of the Congo",
    "guinea_bissau": "Guinea-Bissau",
    "republic_of_congo": "Republic of the Congo",
    "timor_leste": "Timor-Leste",
}


def normalize_country_id(country_id: str) -> str:
    """Normalize a positives.csv `country_id` to canonical Title Case form
    matching parquet panels + cohort-assignments.json.

    For 12 of 16 multi-word country_ids the naive
    `country_id.replace("_", " ").title()` is correct (e.g., "costa_rica" →
    "Costa Rica"). For the remaining 4 it produces a mismatch — overridden
    by `COUNTRY_NAME_OVERRIDES`.
    """
    if country_id in COUNTRY_NAME_OVERRIDES:
        return COUNTRY_NAME_OVERRIDES[country_id]
    return country_id.replace("_", " ").title()

# ---- AUC + bootstrap CI -----------------------------------------------------


def compute_auc(probs: np.ndarray, labels: np.ndarray) -> float:
    """Mann-Whitney U AUC (no sklearn dep at hot path)."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    p_pos = probs[labels == 1]
    p_neg = probs[labels == 0]
    if len(p_pos) == 0 or len(p_neg) == 0:
        return float("nan")
    n_concordant = 0.0
    for p in p_pos:
        n_concordant += np.sum(p_neg < p) + 0.5 * np.sum(p_neg == p)
    return n_concordant / (len(p_pos) * len(p_neg))


def bca_bootstrap_auc_ci(
    probs: np.ndarray, labels: np.ndarray, B: int = BCA_BOOTSTRAP_B, seed: int = 0
) -> dict[str, float]:
    """BCa bootstrap on AUC. Returns point + 80% + 95% CI bands.

    Per Roshani R18-A: B=2000 (default); BCa correction for bias + acceleration.
    """
    rng = np.random.default_rng(seed)
    n = len(probs)
    point = compute_auc(probs, labels)

    boot_aucs = np.empty(B)
    for b in range(B):
        idx = rng.integers(0, n, size=n)
        boot_aucs[b] = compute_auc(probs[idx], labels[idx])
    boot_aucs = boot_aucs[~np.isnan(boot_aucs)]

    # BCa bias correction
    z0 = _phi_inv(np.mean(boot_aucs < point))

    # BCa acceleration via jackknife
    jack = np.empty(n)
    for i in range(n):
        mask = np.arange(n) != i
        jack[i] = compute_auc(probs[mask], labels[mask])
    jack_mean = np.nanmean(jack)
    diffs = jack_mean - jack
    num = np.nansum(diffs ** 3)
    den = 6.0 * (np.nansum(diffs ** 2) ** 1.5 + 1e-12)
    a_hat = num / den

    def _bca_quantile(q: float) -> float:
        z_q = _phi_inv(q)
        adj = z0 + (z0 + z_q) / max(1.0 - a_hat * (z0 + z_q), 1e-9)
        return float(_phi(adj))

    return {
        "auc": float(point),
        "ci80_lo": float(np.percentile(boot_aucs, 100 * _bca_quantile(0.10))),
        "ci80_hi": float(np.percentile(boot_aucs, 100 * _bca_quantile(0.90))),
        "ci95_lo": float(np.percentile(boot_aucs, 100 * _bca_quantile(0.025))),
        "ci95_hi": float(np.percentile(boot_aucs, 100 * _bca_quantile(0.975))),
        "n_bootstrap": int(B),
        "method": "bca_bootstrap",
    }


def _phi(x: float) -> float:
    from scipy.stats import norm
    return float(norm.cdf(x))


def _phi_inv(p: float) -> float:
    from scipy.stats import norm
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return float(norm.ppf(p))


# ---- Indicator panel loading ------------------------------------------------


def list_candidate_indicators(panel_dir: Path) -> list[str]:
    """Return list of all candidate indicator IDs in the substrate."""
    return sorted([p.name for p in panel_dir.iterdir() if p.is_dir()])


def load_panel(indicator_id: str, panel_dir: Path) -> pd.DataFrame:
    """Load one indicator's parquet panel. Returns DataFrame with country, year, value."""
    path = panel_dir / indicator_id / f"{indicator_id}.parquet"
    df = pd.read_parquet(path)
    # Normalize country names to Title Case (parquet panels use Title Case;
    # positives.csv uses lowercase — caller normalizes positives instead)
    return df


# ---- Feature extraction -----------------------------------------------------


def extract_features_for_indicator(
    panel: pd.DataFrame, country: str, year: int, window: int
) -> np.ndarray | None:
    """Per-indicator per-window feature vector.

    Returns N_FEATURES_PER_INDICATOR (10) features:
        [last_z, mean_z, std_z, slope, accel, tertile1_mean, tertile2_mean, tertile3_mean,
         lag_z2, lag_z3]
    All z-scored vs panel-wide (cross-country) distribution at year-1.

    `lag_z2`/`lag_z3` (run-3.1 banking wide-net fix #1, 2026-07-10): explicit z-score
    at year-2 / year-3, appended after the original 8-feature block (positional slots
    0-7 unchanged; new slots are 8 and 9). LEAKAGE-SAFE BY CONSTRUCTION: both are read
    from `window_data`/`z`, which are already restricted to `series.loc[year - window
    : year - 1]` — strictly PAST data only, identical provenance to every other feature
    in this function (including `last_z` = z at year-1). Falls back to 0.0 (neutral,
    matching the existing tertile-mean fallback convention below) when the exact lag
    year has no observation in the panel — never imputed from a later year.

    Returns None if insufficient data in window.
    """
    cdf = panel[panel["country"] == country]
    series = cdf.set_index("year")["value"]
    window_data = series.loc[year - window:year - 1].dropna()
    if len(window_data) < max(3, window // 3):
        return None

    # Panel-wide z-score normalization
    panel_at_year = panel[panel["year"] == year - 1]["value"].dropna()
    if len(panel_at_year) < 10:
        # Fallback: use country's own recent baseline if cross-country reference unavailable
        baseline = series.loc[max(year - 25, series.index.min()):year - 1].dropna()
        mu = float(baseline.mean())
        sd = float(baseline.std())
    else:
        mu = float(panel_at_year.mean())
        sd = float(panel_at_year.std())
    if sd < 1e-9:
        sd = 1.0
    z = (window_data.values - mu) / sd

    # Tertiles (per Miriam M14-1)
    t1, t2, t3 = np.array_split(z, 3)
    t1m = float(t1.mean()) if len(t1) > 0 else 0.0
    t2m = float(t2.mean()) if len(t2) > 0 else 0.0
    t3m = float(t3.mean()) if len(t3) > 0 else 0.0

    # Linear slope
    x = np.arange(len(z), dtype=float)
    if len(z) >= 2:
        slope = float(np.polyfit(x, z, 1)[0])
    else:
        slope = 0.0

    # Quadratic acceleration coefficient
    if len(z) >= 3:
        coefs = np.polyfit(x, z, 2)
        accel = float(2.0 * coefs[0])
    else:
        accel = 0.0

    # Explicit lag features (year-2, year-3): exact-year lookup into the past-only
    # window_data/z index. 0.0 fallback when that specific calendar year is absent
    # from the panel (a real gap, not a leak — we never substitute a later year's value).
    lag_lookup = dict(zip(window_data.index.tolist(), z.tolist()))
    lag_z2 = float(lag_lookup.get(year - 2, 0.0))
    lag_z3 = float(lag_lookup.get(year - 3, 0.0))

    return np.array(
        [float(z[-1]), float(z.mean()), float(z.std()), slope, accel, t1m, t2m, t3m,
         lag_z2, lag_z3],
        dtype=float,
    )


def build_X_y(
    samples: pd.DataFrame,
    selected_indicators: list[str],
    window: int,
    panels: dict[str, pd.DataFrame],
    feat_cache: dict | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build feature matrix for one (selected_set, window) configuration.

    Returns:
        X: (n_valid, N_FEATURES_PER_INDICATOR * n_indicators) feature matrix
        y: (n_valid,) labels
        countries: (n_valid,) per-row country
        years: (n_valid,) per-row year

    `feat_cache` (optional): a memo dict keyed by ``(indicator, country, year, window)``
    → the N_FEATURES_PER_INDICATOR-feature vector (or None for insufficient data). BIT-IDENTICAL by construction:
    ``extract_features_for_indicator`` is a pure deterministic function of exactly those four
    keys (independent of the selected set), so a cached value equals a freshly-computed one.
    The greedy loop shares ONE cache across all (candidate × window) cells + steps, which kills
    the dominant redundancy — today the selected set's features are re-extracted for every
    candidate and every cell. The cache is a plain dict; under the thread backend (#961) its
    set/get are GIL-atomic and the cached value is deterministic, so a write race can at worst
    recompute the same value — never alter the result. `None` disables the cache (back-compat
    + the serial test arms)."""
    X_rows = []
    y_rows = []
    c_rows = []
    yr_rows = []
    for _, row in samples.iterrows():
        country = str(row["country"])
        year = int(row["year"])
        feat_parts = []
        skip = False
        for ind in selected_indicators:
            if feat_cache is not None:
                key = (ind, country, year, window)
                if key in feat_cache:
                    f = feat_cache[key]
                else:
                    f = extract_features_for_indicator(panels[ind], country, year, window)
                    feat_cache[key] = f
            else:
                f = extract_features_for_indicator(panels[ind], country, year, window)
            if f is None:
                skip = True
                break
            feat_parts.append(f)
        if skip:
            continue
        X_rows.append(np.concatenate(feat_parts))
        y_rows.append(int(row["label"]))
        c_rows.append(country)
        yr_rows.append(year)
    if not X_rows:
        return np.zeros((0, 0)), np.zeros(0), np.array([]), np.array([])
    return (
        np.vstack(X_rows),
        np.array(y_rows),
        np.array(c_rows),
        np.array(yr_rows),
    )


def coverage_report(samples: pd.DataFrame, selected_indicators: list[str],
                    window: int, panels: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Anti-silent-truncation coverage audit (Majles MR-14-A1, 2026-05-25). Surfaces
    how many positives/negatives SURVIVE build_X_y for a candidate set — the sample
    restriction the row-drop would otherwise hide (the foreign_intervention defect)."""
    _, y, c, _ = build_X_y(samples, selected_indicators, window, panels)
    n_pos_total = int((samples["label"] == 1).sum())
    n_neg_total = int((samples["label"] == 0).sum())
    n_pos_surv = int((y == 1).sum()) if len(y) else 0
    n_neg_surv = int((y == 0).sum()) if len(y) else 0
    n_countries = int(len({str(x) for x in c.tolist()})) if len(c) else 0
    return {
        "n_pos_total": n_pos_total, "n_pos_survive": n_pos_surv,
        "n_neg_total": n_neg_total, "n_neg_survive": n_neg_surv,
        "pos_coverage": (n_pos_surv / n_pos_total) if n_pos_total else 0.0,
        "neg_coverage": (n_neg_surv / n_neg_total) if n_neg_total else 0.0,
        "n_countries_survive": n_countries,
    }


def classify_verdict(coverage_pass: bool, chance_pass: bool, global_pass: bool,
                     cohort_loco_pass: bool, cohort_ece_pass: bool) -> str:
    """Map the gate booleans to the final walk verdict. Blocking gates override
    everything (Majles MR-14-A1/A2 / Miriam binding-veto): no graduation — not even
    MARGINAL — on a truncated subsample (coverage) or a chance-level CI. Coverage is
    checked first as it is the upstream cause of the chance failure. Pure + testable."""
    if not coverage_pass:
        return "COVERAGE_FAIL"
    if not chance_pass:
        return "CHANCE_FAIL"
    if global_pass and cohort_loco_pass and cohort_ece_pass:
        return "LOCK"
    if global_pass and cohort_loco_pass and not cohort_ece_pass:
        return "MARGINAL_PENDING_BETA_CALIBRATION"
    return "HARD_FAIL"


def early_abort_verdict_override(verdict: str, greedy_result: dict[str, Any]) -> str:
    """A floor-aware early-abort is a COMPUTE-bound halt, not a verdict (PR #116 /
    Ji-Hoon+Kwame ruling 2026-05-27). Its optimistic ceiling is a conservative HEURISTIC,
    not a strict upper bound under XGBoost interaction effects — so auto-declaring
    HARD_FAIL on an abort could flip a would-be-PASS and is therefore NOT §2.5-clean.
    When the greedy aborted on floor-unreachable we override the verdict to
    INCOMPLETE_CEILING_BELOW_FLOOR and route the partial walk to human/Majles
    adjudication (re-run unbounded / accept HARD_FAIL on the evidence / defer). This is
    verdict-neutral → structurally §2.5-clean; the compute saving is preserved (the walk
    still halted early), only the label changes. Pure + testable."""
    if greedy_result.get("early_abort_floor_unreachable"):
        return "INCOMPLETE_CEILING_BELOW_FLOOR"
    return verdict


def coverage_gate_ok(cov: dict[str, Any],
                     min_pos_survival: float = MIN_POS_SURVIVAL,
                     min_effective_npos: int = MIN_EFFECTIVE_NPOS,
                     min_survive_countries: int = MIN_SURVIVE_COUNTRIES,
                     min_neg_survival: float = MIN_NEG_SURVIVAL) -> bool:
    """Blocking gate: ≥min_pos_survival of positives survive, balanced class coverage,
    and ≥min_effective_npos positives across ≥min_survive_countries countries. A
    candidate set / walk failing this is COVERAGE_FAIL — never graded on a truncated
    subsample (the 2026-05-25 bugfix). Thresholds default to the module constants;
    they are injectable so mechanic-tests can exercise the greedy on tiny fixtures.

    Note (FU-2, QA review #112): the two class-survival thresholds are deliberately
    ASYMMETRIC — positives must clear MIN_POS_SURVIVAL (0.50) and negatives must clear
    MIN_NEG_SURVIVAL (0.60). Positives are the scarce, decisive class (the leak
    dropped 94% of them), so the binding floor sits on the positive side; the
    negative-survival check guards against an indicator that is sparse in the negative
    pool too. `min_neg_survival` thus names the minimum NEGATIVE-class survival."""
    return (cov["pos_coverage"] >= min_pos_survival
            and cov["neg_coverage"] >= min_neg_survival  # neg-class survival fraction
            and cov["n_pos_survive"] >= min_effective_npos
            and cov["n_countries_survive"] >= min_survive_countries)


def build_samples(pos: pd.DataFrame, negatives_per_positive: int = 3, seed: int = 0,
                  valid_years: range = range(1980, 2023),
                  time_matched: bool = True) -> pd.DataFrame:
    """Build the LOCO candidate set: all positives (label=1) + sampled negatives
    (label=0). Negatives are random (country, year) pairs drawn from the positive
    countries, excluding any positive pair.

    Extracted from the walk's main (2026-05-25) so the F-ML-1 walk AND the
    naive-baseline floor computation (compute_naive_baselines.py) build the
    IDENTICAL candidate set — Ji-Hoon's LOCO-parity requirement for greenfield
    floor provenance. ``pos`` must carry columns country, year, label(=1).

    ``time_matched`` (default ON, truncation-leak bugfix facet 3, Majles 2026-05-25):
    draw negative YEARS from the positives' empirical year distribution rather than
    uniformly over ``valid_years``. This neutralises the temporal confound — when
    positives cluster in older years but negatives are uniform-recent, calendar time
    alone separates the classes (AUC(year→label) was ~0.28 for foreign_intervention),
    and any indicator that merely trends over time can ride that confound to an
    inflated AUC. Time-matched negatives force the year marginals to coincide, so the
    model must use the indicator SHAPE, not the era. ``time_matched=False`` preserves
    the legacy uniform-year sampling (kept only for back-compat / mechanic tests)."""
    rng = np.random.default_rng(seed)
    pos_set = set(zip(pos["country"], pos["year"]))
    pos_countries = list(pos["country"].unique())
    # Year pool: positives' own years (time-matched) or the full valid range (legacy).
    year_pool = list(pos["year"].astype(int)) if time_matched else list(valid_years)
    n_neg_target = len(pos) * negatives_per_positive
    negs: list[dict] = []
    attempts = 0
    while len(negs) < n_neg_target and attempts < n_neg_target * 50:
        attempts += 1
        c = pos_countries[rng.integers(0, len(pos_countries))]
        y = int(year_pool[rng.integers(0, len(year_pool))])
        if (c, y) in pos_set:
            continue
        negs.append({"country": c, "year": y, "label": 0})
    return pd.concat([pos[["country", "year", "label"]], pd.DataFrame(negs)], ignore_index=True)


def temporal_confound_auc(samples: pd.DataFrame) -> float:
    """Diagnostic: AUC of YEAR alone as a label predictor. ~0.50 means the negative
    sampling is time-matched (no calendar-time confound); far from 0.50 means the
    era trivially separates the classes (the truncation-leak failure mode). Reported
    in the §10 summary; non-gating. Returns nan if labels are single-class."""
    y = samples["label"].to_numpy().astype(int)
    yr = samples["year"].to_numpy().astype(float)
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(compute_auc(yr, y))


def era_stratified_loco(probs: np.ndarray, labels: np.ndarray, years: np.ndarray,
                        boundary: int = 2000, min_n: int = 20) -> dict[str, Any]:
    """Diagnostic (bugfix facet 4, non-gating): split the pooled LOCO predictions by
    era and report per-era AUC + counts. The truncation leak concentrated all signal
    in a recent subsample; a healthy recipe should hold up across eras, while a wildly
    era-dependent AUC (e.g. strong post-2000, chance pre-2000) is a red flag that the
    evidence base is effectively era-restricted. Reports a coarse pre/post split at
    ``boundary`` plus per-decade buckets. Cells with <``min_n`` rows or single-class
    labels report auc=None (n still shown)."""
    probs = np.asarray(probs, float)
    labels = np.asarray(labels, int)
    years = np.asarray(years, int)

    def _cell(mask: np.ndarray) -> dict[str, Any]:
        n = int(mask.sum())
        n_pos = int((labels[mask] == 1).sum()) if n else 0
        if n < min_n or len(np.unique(labels[mask])) < 2:
            return {"n": n, "n_pos": n_pos, "auc": None}
        return {"n": n, "n_pos": n_pos, "auc": round(float(compute_auc(probs[mask], labels[mask])), 4)}

    out: dict[str, Any] = {
        "boundary": boundary,
        "pre_boundary": _cell(years < boundary),
        "post_boundary": _cell(years >= boundary),
        "by_decade": {},
    }
    if len(years):
        for dec in range(int(years.min()) // 10 * 10, int(years.max()) // 10 * 10 + 10, 10):
            cell = _cell((years >= dec) & (years < dec + 10))
            if cell["n"] > 0:
                out["by_decade"][f"{dec}s"] = cell
    aucs = [c["auc"] for c in (out["pre_boundary"], out["post_boundary"]) if c["auc"] is not None]
    out["pre_post_spread"] = round(abs(aucs[0] - aucs[1]), 4) if len(aucs) == 2 else None
    return out


# ---- LOCO + architecture ----------------------------------------------------


def _fit_predict_one_fold(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    architecture: str,
    seed: int = 0,
) -> np.ndarray:
    """Fit ONE model of `architecture` on (X_train, y_train) and return
    predict_proba(X_test)[:, 1].

    Extracted verbatim from `fit_predict_loco`'s per-country fold body (run-3.1 banking
    wide-net fix #6, 2026-07-10) so a genuine train-once/predict-once evaluation — e.g. a
    LOCKED TEMPORAL HOLD-OUT (train on screening-side rows, predict ONCE on frozen hold-out
    rows, no re-selection) — reuses the IDENTICAL model-fitting code every LOCO fold already
    uses, rather than a parallel reimplementation that could silently drift from it.
    `fit_predict_loco` below calls this exact function once per held-out country; this
    extraction is a pure refactor (same statements, same order, same `random_state=seed`) —
    bit-identical to the pre-refactor inline code, confirmed by the existing LOCO unit tests
    (which exercise `fit_predict_loco`'s public contract, unchanged by this extraction).

    NaN/inf replacement + `scale_pos_weight` (XGBoost class-imbalance) are handled INSIDE
    this helper (both are pure functions of `X_train`/`y_train`/`X_test`, so encapsulating
    them here removes a duplication point rather than creating one) — a caller only needs to
    hand in raw (post-`build_X_y`) train/test arrays.
    """
    from sklearn.preprocessing import StandardScaler

    n_pos = int((y_train == 1).sum())
    n_neg = int((y_train == 0).sum())
    spw = (n_neg / max(n_pos, 1)) if n_pos > 0 else 1.0

    # Replace residual NaN/inf with 0. NOTE (Ji-Hoon JH-2, 2026-05-25): this is
    # POST-row-selection numeric stabilization for rare non-finite values produced
    # by the z-score feature computation (e.g. a zero-variance window → 0/0). It is
    # NOT imputation of missing indicator windows — rows lacking a selected
    # indicator's window are already DROPPED in build_X_y (the coverage gate, not
    # fill, is the remedy). The JH-R1 firewall (no filled row in any fold) holds.
    X_train = np.where(np.isfinite(X_train), X_train, 0.0)
    X_test = np.where(np.isfinite(X_test), X_test, 0.0)

    if architecture == "LR":
        from sklearn.linear_model import LogisticRegression
        scaler = StandardScaler()
        Xt = scaler.fit_transform(X_train)
        Xte = scaler.transform(X_test)
        # Per F-ML-1 §5.2: L1-regularized inner model (QA PR#90 B1).
        clf = LogisticRegression(
            C=1.0, penalty="l1", solver="saga", class_weight="balanced",
            max_iter=2000, random_state=seed,
        )
        clf.fit(Xt, y_train)
        probs = clf.predict_proba(Xte)[:, 1]
    elif architecture == "XGBoost":
        from xgboost import XGBClassifier
        # Per F-ML-1 §5.2: L1-regularized inner model (QA PR#90 B1).
        # reg_alpha=0.1 inside XGBoost provides L1 regularization handling
        # collinearity at each greedy step.
        clf = XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            reg_alpha=0.1,
            scale_pos_weight=spw, eval_metric="logloss",
            random_state=seed, verbosity=0, n_jobs=1,
        )
        clf.fit(X_train, y_train)
        probs = clf.predict_proba(X_test)[:, 1]
    elif architecture == "MLP":
        from sklearn.neural_network import MLPClassifier
        scaler = StandardScaler()
        Xt = scaler.fit_transform(X_train)
        Xte = scaler.transform(X_test)
        clf = MLPClassifier(
            hidden_layer_sizes=(16,), activation="relu",
            solver="adam", learning_rate_init=1e-3, max_iter=200,
            early_stopping=True, random_state=seed,
        )
        clf.fit(Xt, y_train)
        probs = clf.predict_proba(Xte)[:, 1]
    else:
        raise ValueError(f"Unknown architecture {architecture!r}")

    return probs


def fit_predict_loco(
    X: np.ndarray,
    y: np.ndarray,
    countries: np.ndarray,
    years: np.ndarray,
    architecture: str,
    seed: int = 0,
) -> dict[str, Any]:
    """Run full LOCO with the specified architecture.

    Returns pooled predictions + per-country AUC for fold-variance computation.
    Per Ji-Hoon R2: no subsampling. Full country fold.
    """
    unique_countries = sorted(set(countries.tolist()))
    pooled_probs: list[float] = []
    pooled_labels: list[int] = []
    pooled_countries: list[str] = []
    pooled_years: list[int] = []
    per_country_auc: dict[str, float] = {}

    # NOTE: BLAS/OpenMP thread pinning lives at the greedy_outer_loop level now — wrapping
    # it here per-fold (or worse, per-cell when this fn is called inside Parallel) caused
    # the 2026-05-28 canary to be ~13× slower than the prior. threadpool_limits mutates
    # process-global library state under a lock; 16 joblib worker threads entering+exiting
    # the context per cell serialized hard. The fix is one enter per WALK in the greedy
    # outer loop (below), inherited by all joblib workers. The Dockerfile also sets
    # OMP_NUM_THREADS=1 et al. process-wide, so in production the in-code wrap is the
    # belt-and-suspenders for local runs without those env vars.
    for held in unique_countries:
        train_mask = countries != held
        test_mask = countries == held
        if test_mask.sum() == 0 or train_mask.sum() == 0:
            continue
        y_train = y[train_mask]
        if len(np.unique(y_train)) < 2:
            continue
        X_train = X[train_mask]
        X_test = X[test_mask]
        y_test = y[test_mask]

        probs = _fit_predict_one_fold(X_train, y_train, X_test, architecture, seed)

        pooled_probs.extend(probs.tolist())
        pooled_labels.extend(y_test.tolist())
        pooled_countries.extend([held] * test_mask.sum())
        pooled_years.extend(years[test_mask].tolist())
        if len(np.unique(y_test)) >= 2:
            per_country_auc[held] = compute_auc(probs, y_test)

    return {
        "probs": np.array(pooled_probs),
        "labels": np.array(pooled_labels),
        "countries": np.array(pooled_countries),
        "years": np.array(pooled_years),
        "per_country_auc": per_country_auc,
        "global_auc": compute_auc(np.array(pooled_probs), np.array(pooled_labels)),
    }


def _stability_label(fv: float) -> str:
    """Per F-ML-1 §4.2-SD: LOW (σ² < 0.04), MODERATE (0.04 ≤ σ² ≤ 0.10),
    HIGH (σ² > 0.10). Extracted as a named helper so tests can verify the
    driver's own thresholding logic directly (per QA PR#92 FU-3)."""
    if fv < 0.04:
        return "LOW"
    elif fv <= 0.10:
        return "MODERATE"
    else:
        return "HIGH"


def _build_stability_diagnostic(per_country_auc: dict[str, float]) -> dict[str, Any]:
    """Per F-ML-1 §4.2-SD: compute the informational stability diagnostic
    emitted on every walk under the F-ML-N amendment.

    §4.2-SD requires logging: (1) per-fold AUC values, (2) fold-AUC mean,
    (3) fold-AUC variance, (4) qualitative label. Extracted as a helper so
    tests can verify it directly (per QA PR#92 FU-2 + FU-3).
    """
    aucs = np.array(list(per_country_auc.values()))
    aucs = aucs[~np.isnan(aucs)]
    fv = float(np.var(aucs)) if len(aucs) >= 2 else 0.0
    fold_auc_mean = float(np.mean(aucs)) if len(aucs) >= 1 else float("nan")
    return {
        "fold_variance": fv,
        "fold_auc_mean": fold_auc_mean,
        "label": _stability_label(fv),
        "per_country_loco_auc": {k: float(v) for k, v in per_country_auc.items()},
        "thresholds": {"LOW_upper": 0.04, "MODERATE_upper": 0.10},
        "informational_only": True,
        "amendment_reference": (
            "F-ML-N §4.2 amendment 2026-05-22 (qgi-aws-tf#864); see "
            "docs/specs/internal/decisions/artifacts/F-ML-N-§4.2-amendment-2026-05-22.md"
        ),
    }


def fold_variance(per_country_auc: dict[str, float]) -> float:
    """Per Ji-Hoon R1: variance of per-country LOCO-AUC."""
    aucs = np.array(list(per_country_auc.values()))
    aucs = aucs[~np.isnan(aucs)]
    if len(aucs) < 2:
        return 0.0
    return float(np.var(aucs))


def window_ci_via_bootstrap_argmax(
    per_window_predictions: dict[int, tuple[np.ndarray, np.ndarray]],
    B: int = BCA_BOOTSTRAP_B,
    seed: int = 0,
) -> tuple[int, int]:
    """Per Roshani R18-B: window_ci via bootstrap argmax-window distribution.

    For each of B bootstrap iterations:
      1. Resample with replacement (same indices across all windows for paired comparison)
      2. Compute AUC at each window on the bootstrap sample
      3. Record argmax_window
    Return [2.5, 97.5] percentile range of argmax_windows.
    """
    if not per_window_predictions:
        return (0, 0)
    windows = sorted(per_window_predictions.keys())
    # Ensure all windows have same N (some may differ due to data availability)
    common_n = min(len(per_window_predictions[w][0]) for w in windows)
    if common_n < 10:
        return (windows[0], windows[-1])
    rng = np.random.default_rng(seed)
    argmax_windows: list[int] = []
    for _ in range(B):
        idx = rng.integers(0, common_n, size=common_n)
        best_auc = -1.0
        best_window = windows[0]
        for w in windows:
            probs, labels = per_window_predictions[w]
            probs_b = probs[:common_n][idx]
            labels_b = labels[:common_n][idx]
            auc = compute_auc(probs_b, labels_b)
            if not np.isnan(auc) and auc > best_auc:
                best_auc = auc
                best_window = w
        argmax_windows.append(best_window)
    return (
        int(np.percentile(argmax_windows, 2.5)),
        int(np.percentile(argmax_windows, 97.5)),
    )


# ---- Univariate screen ------------------------------------------------------


def univariate_loco_screen(
    samples: pd.DataFrame,
    candidates: list[str],
    panels: dict[str, pd.DataFrame],
    default_window: int = 10,
    top_n: int = TOP_N_PREFILTER,
) -> tuple[list[str], dict[str, dict]]:
    """Per §5.1: univariate LOCO-AUC screen → top-N.

    Uses LR (fast) at default 10y window. Per F-ML-1 §5.1 the screen is
    architecture-agnostic and pre-filter only.
    """
    LOG.info("Univariate screen: %d candidates × default %d-y window", len(candidates), default_window)
    n_pos_total = int((samples["label"] == 1).sum())
    n_neg_total = int((samples["label"] == 0).sum())
    scores: dict[str, dict] = {}
    n_coverage_rejected = 0
    for i, ind in enumerate(candidates):
        if i % 20 == 0:
            LOG.info("  ...%d/%d", i, len(candidates))
        X, y, c, yr = build_X_y(samples, [ind], default_window, panels)
        # Coverage gate (truncation fix, 2026-05-25): an indicator that drops too
        # many positives / too few countries cannot RANK — it can only worsen
        # coverage in combination and would steer the greedy onto a truncated
        # subsample (the foreign_intervention defect). Computed inline from this
        # screen's own build_X_y output (no second build).
        n_pos_s = int((y == 1).sum()) if len(y) else 0
        n_neg_s = int((y == 0).sum()) if len(y) else 0
        cov = {
            "pos_coverage": (n_pos_s / n_pos_total) if n_pos_total else 0.0,
            "neg_coverage": (n_neg_s / n_neg_total) if n_neg_total else 0.0,
            "n_pos_survive": n_pos_s,
            "n_countries_survive": int(len({str(x) for x in c.tolist()})) if len(c) else 0,
        }
        if not coverage_gate_ok(cov):
            scores[ind] = {"univariate_loco_auc": float("nan"), "n_valid": int(len(X)),
                           "coverage_fail": True, "pos_coverage": round(cov["pos_coverage"], 3)}
            n_coverage_rejected += 1
            continue
        if len(X) < 30:
            scores[ind] = {"univariate_loco_auc": float("nan"), "n_valid": int(len(X))}
            continue
        res = fit_predict_loco(X, y, c, yr, architecture="LR", seed=0)
        scores[ind] = {
            "univariate_loco_auc": float(res["global_auc"]),
            "n_valid": int(len(X)),
            "pos_coverage": round(cov["pos_coverage"], 3),
        }
    if n_coverage_rejected:
        LOG.info("Coverage gate rejected %d/%d candidate indicators (insufficient "
                 "positive/country coverage) before ranking.", n_coverage_rejected, len(candidates))
    ranked = sorted(
        candidates,
        key=lambda i: scores[i]["univariate_loco_auc"] if not np.isnan(scores[i]["univariate_loco_auc"]) else -1.0,
        reverse=True,
    )
    return ranked[:top_n], scores


# ---- Greedy outer + window search -------------------------------------------


# ---- Checkpoint / resume (#91) ---------------------------------------------
# Per-step greedy checkpointing so a long walk can RESUME instead of restart.
# Founder 2026-05-24: mandatory for all recipes; hard prerequisite for the AWS
# Spot fleet (a reclaimed multi-hour walk must resume, not restart from zero).
# Granularity: at most ONE greedy step is lost on interruption. A config
# signature guards every resume — a checkpoint is only honoured if it was
# produced by an identical walk configuration (recipe/candidates/arch/grid/
# seed/steps); a mismatch or a corrupt file is ignored and the walk starts
# fresh (never silently resume a different walk).
#
# NOTE (AWS): the checkpoint is a plain JSON file in output_dir. On the Spot
# fleet, output_dir must be backed by S3 (sync the checkpoint out after each
# step / in at startup) — wired in the AWS-fleet task, not here. S3, not
# DynamoDB: a cold, infrequent "where was I" blob, written once per greedy step.

GREEDY_CHECKPOINT_NAME = "greedy-checkpoint.json"
GREEDY_RESULT_NAME = "greedy-result.json"
CHECKPOINT_SCHEMA_VERSION = 1


def panel_data_fingerprint(panel_dir: Path, positives_csv: Path | None = None) -> str:
    """Fingerprint the TRAINING DATA a walk runs on: every parquet under
    panel_dir (RECURSIVE — panels may be partitioned into per-indicator subdirs)
    plus the positives CSV, by (relative_name, size). Cheap (stat only, no read).

    This is the 2-4x/year re-run safety guard: updated panels/positives change
    total size → the fingerprint changes → the config signature changes → a
    stale checkpoint from the prior data vintage is REJECTED (fresh start)
    rather than silently resumed onto new data.

    Deliberately uses SIZE, NOT mtime: on the AWS Spot fleet the panels are
    re-synced from S3 onto a fresh instance after every reclaim, which bumps
    mtime but not content — using mtime would reject the checkpoint on every
    reclaim (defeating #91 resume). Size is stable across re-syncs and changes
    on a real data update (parquet sizes virtually always differ between
    vintages). Recursion (** ) is required because the S3 layout stores each
    indicator under its own prefix; a top-level glob would see zero panels and
    silently fingerprint nothing. (Review/canary 2026-05-25.)"""
    parts: list[tuple] = []
    try:
        files = sorted(Path(panel_dir).rglob("*.parquet"), key=lambda p: str(p))
    except OSError:
        files = []
    for f in files:
        try:
            rel = f.relative_to(panel_dir).as_posix()
        except ValueError:
            rel = f.name
        try:
            parts.append((rel, f.stat().st_size))
        except OSError:
            parts.append((rel, -1))
    if positives_csv is not None and Path(positives_csv).exists():
        parts.append((Path(positives_csv).name, Path(positives_csv).stat().st_size))
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def greedy_config_signature(
    recipe_id: str,
    candidates_top_n: list[str],
    architecture: str,
    delta_step: float,
    max_steps: int,
    seed: int,
    data_fingerprint: str,
) -> str:
    """Stable hash of the inputs that define a greedy walk. A checkpoint may
    only be resumed when this signature matches exactly — otherwise the on-disk
    state belongs to a different walk and resuming would corrupt the result.

    `data_fingerprint` (from `panel_data_fingerprint`) is REQUIRED so that a
    re-run on updated training data does NOT resume a stale checkpoint (the
    4x/year cadence safety guard — see review 2026-05-24, blocker #2)."""
    payload = json.dumps({
        "schema": CHECKPOINT_SCHEMA_VERSION,
        "recipe_id": recipe_id,
        "candidates_top_n": list(candidates_top_n),  # order matters (greedy order)
        "architecture": architecture,
        "delta_step": round(float(delta_step), 8),
        "max_steps": int(max_steps),
        "seed": int(seed),
        "window_grid": list(WINDOW_GRID),
        "data_fingerprint": data_fingerprint,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, obj: dict[str, Any]) -> None:
    """Write JSON via a temp file + rename so a crash mid-write can't leave a
    truncated/corrupt checkpoint."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_greedy_checkpoint(path: Path, expected_signature: str) -> dict[str, Any] | None:
    """Return the validated checkpoint ENVELOPE if a signature-matching one
    exists; else None (corrupt / mismatched / absent → start fresh, with a log).
    The envelope carries `state` (per-step resume fields) and, for a completed
    greedy-result file, also `result` (the full greedy output)."""
    if not path.exists():
        return None
    try:
        ckpt = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        LOG.warning("Ignoring unreadable greedy checkpoint at %s (%s); starting fresh", path, exc)
        return None
    if not isinstance(ckpt, dict) or ckpt.get("config_signature") != expected_signature:
        LOG.warning("Greedy checkpoint config_signature mismatch/absent at %s; ignoring (different walk config)", path)
        return None
    state = ckpt.get("state")
    if not isinstance(state, dict) or "selected" not in state or "step" not in state:
        LOG.warning("Greedy checkpoint at %s missing required state fields; ignoring", path)
        return None
    return ckpt


def _eval_grid_cell(samples, selected, cand, win, panels, architecture, seed,
                    n_pos_tot, n_neg_tot, min_pos_survival, min_effective_npos,
                    min_survive_countries, min_neg_survival, feat_cache=None):
    """Evaluate ONE (candidate, window) grid cell: build the trial set, apply the
    len/class guards + coverage gate, run full LOCO. Returns the result dict, or None
    if the cell is skipped. Pure + deterministic (fixed seed, XGBoost n_jobs=1 inside)
    and reads `panels`/`samples` read-only → safe to run concurrently (#961). The caller
    reduces results in input order, so parallel evaluation is BIT-IDENTICAL to serial.
    `feat_cache` is the shared per-(indicator,country,year,window) feature memo (read-mostly,
    GIL-atomic under the thread backend); it changes only speed, never the result."""
    trial_set = selected + [cand]
    X, y, c, yr = build_X_y(samples, trial_set, win, panels, feat_cache=feat_cache)
    if len(X) < 30 or len(np.unique(y)) < 2:
        return None
    # Coverage gate (truncation fix, 2026-05-25): reject a candidate SET that drops too
    # many positives / countries — the greedy must not chase AUC on a truncated subsample.
    cov = {
        "pos_coverage": (int((y == 1).sum()) / n_pos_tot) if n_pos_tot else 0.0,
        "neg_coverage": (int((y == 0).sum()) / n_neg_tot) if n_neg_tot else 0.0,
        "n_pos_survive": int((y == 1).sum()),
        "n_countries_survive": int(len({str(x) for x in c})),
    }
    if not coverage_gate_ok(cov, min_pos_survival, min_effective_npos,
                            min_survive_countries, min_neg_survival):
        return None
    res = fit_predict_loco(X, y, c, yr, architecture=architecture, seed=seed)
    return {"candidate": cand, "window": win, "auc": res["global_auc"], "n_valid": len(X)}


def greedy_outer_loop(
    samples: pd.DataFrame,
    candidates_top_n: list[str],
    panels: dict[str, pd.DataFrame],
    architecture: str,
    delta_step: float = DELTA_STEP,
    max_steps: int | None = None,
    seed: int = 0,
    checkpoint_path: Path | None = None,
    config_signature: str | None = None,
    min_pos_survival: float = MIN_POS_SURVIVAL,
    min_effective_npos: int = MIN_EFFECTIVE_NPOS,
    min_survive_countries: int = MIN_SURVIVE_COUNTRIES,
    min_neg_survival: float = MIN_NEG_SURVIVAL,
    lock_floor: float | None = None,
    min_steps_before_abort: int = MIN_STEPS_BEFORE_ABORT,
    n_jobs: int = 1,
) -> dict[str, Any]:
    """Per §5.2/§5.3/§5.4: greedy outer loop with concurrent window search.

    At each step, evaluate (each remaining candidate × each window) via full LOCO.
    Pick the best (candidate, window) pair; add if lift ≥ delta_step.
    Per Ji-Hoon R2: full LOCO, no subsampling.
    """
    # #961 bit-identical contract: n_jobs>1 is guaranteed identical-to-serial only for
    # XGBoost (the fleet architecture — each cell trains one n_jobs=1 booster, fully
    # deterministic). Concurrent sklearn LR/MLP fits under the thread backend can differ
    # via BLAS/OpenMP thread state, which would violate §2.5. So we refuse to parallelize
    # those rather than silently risk a non-reproducible walk (PR #117 review).
    if n_jobs != 1 and architecture != "XGBoost":
        raise ValueError(
            f"n_jobs>1 is bit-identical only for XGBoost (the fleet architecture); got "
            f"architecture={architecture!r}. Run LR/MLP with n_jobs=1 (BLAS thread state "
            f"can make concurrent sklearn fits non-deterministic)."
        )
    selected: list[str] = []
    chosen_window: int | None = None
    remaining = list(candidates_top_n)
    history: list[dict] = []
    # Shared per-(indicator,country,year,window) feature memo for the whole walk. The dominant
    # cost is re-extracting the SAME features for the SAME (indicator,window) across every
    # candidate cell and every greedy step; this memo computes each exactly once. Bit-identical
    # (see build_X_y) — the canary re-run is the §2.5 confirmation that selection+AUC are
    # unchanged. One dict per walk (one process), GC'd at process exit; no cross-walk leak.
    # NOTE (QA PR#121 FU-2): on a checkpoint RESUME the cache starts cold, so the first
    # post-resume step pays the full extraction cost again. Speed-only — no correctness impact.
    feat_cache: dict = {}
    n_pos_tot = int((samples["label"] == 1).sum()) if samples is not None else 0
    n_neg_tot = int((samples["label"] == 0).sum()) if samples is not None else 0

    # Current LOCO-AUC with empty set = baseline (random)
    current_auc = 0.5
    observed_max_lift = 0.0  # largest single-step gain seen (optimistic abort bound)
    early_abort = False       # set True iff floor-aware early-abort fires

    step = 0
    if max_steps is None:
        max_steps = len(candidates_top_n)

    # --- Resume from a per-step checkpoint if one matches this config (#91) ---
    if checkpoint_path is not None and config_signature is not None:
        env = load_greedy_checkpoint(checkpoint_path, config_signature)
        if env is not None:
            state = env["state"]
            selected = list(state["selected"])
            chosen_window = state.get("chosen_window")
            remaining = list(state["remaining"])
            current_auc = float(state["current_auc"])
            history = list(state["history"])
            step = int(state["step"])
            # Reconstruct the optimistic abort bound from resumed history so the
            # early-abort decision is identical whether or not we resumed (#91).
            observed_max_lift = max(
                (float(h["lift_over_previous"]) for h in history), default=0.0
            )
            LOG.info(
                "RESUMING greedy from checkpoint: step=%d, selected=%s, current_auc=%.4f",
                step, selected, current_auc,
            )

    while remaining and step < max_steps:
        step += 1
        LOG.info("Greedy step %d/%d (selected=%d, remaining=%d)", step, max_steps, len(selected), len(remaining))
        # #961: the (candidate × window) grid is embarrassingly parallel — each cell is
        # an independent, deterministic LOCO eval. Evaluate cells via joblib (THREAD
        # backend: XGBoost fit releases the GIL and panels stay shared read-only, so we
        # avoid pickling the multi-MB panels dict per task, and test monkeypatches still
        # apply). joblib.Parallel preserves INPUT ORDER, so we reduce in the same
        # cand-major/window-minor order with the same strict-`>` tie-break as the serial
        # loop → BIT-IDENTICAL to n_jobs=1. n_jobs defaults to 1 (serial; tests + back-compat).
        cells = [(cand, win) for cand in remaining for win in WINDOW_GRID]
        # BLAS/OpenMP pin: ONE enter per greedy step, set-once on the main thread, inherited
        # by every joblib worker thread. The 2026-05-28 canary showed that putting this
        # wrap per-fold (inside fit_predict_loco) caused 16 workers to serialize on
        # threadpoolctl's process-global state lock — step 1 went from ~5 min to >74 min
        # (~13× slower). Per-step (~12 enter/exits per walk) avoids the contention while
        # preserving the BLAS-pin guarantee. The Dockerfile env vars OMP_NUM_THREADS=1
        # etc. are the production primary; this is the local belt-and-suspenders.
        with _threadpool_limits(1):
            results = Parallel(n_jobs=n_jobs, prefer="threads")(
                delayed(_eval_grid_cell)(
                    samples, selected, cand, win, panels, architecture, seed,
                    n_pos_tot, n_neg_tot, min_pos_survival, min_effective_npos,
                    min_survive_countries, min_neg_survival, feat_cache,
                )
                for (cand, win) in cells
            )
        best = None
        for res in results:  # input order preserved → identical tie-break to serial
            if res is None:
                continue
            if best is None or res["auc"] > best["auc"]:
                best = res
        LOG.info("  evaluated %d grid cells (%d candidates × %d windows) at step %d",
                 len(cells), len(remaining), len(WINDOW_GRID), step)
        if best is None:
            LOG.info("  no candidate produced a valid LOCO; halting greedy")
            break
        lift = best["auc"] - current_auc
        LOG.info("  step %d best: %s at %d-y window, AUC=%.4f, lift=%+.4f",
                 step, best["candidate"], best["window"], best["auc"], lift)
        history.append({
            "step": step,
            "candidate": best["candidate"],
            "window": best["window"],
            "auc": float(best["auc"]),
            "lift_over_previous": float(lift),
            "selected_after": selected + [best["candidate"]],
        })
        observed_max_lift = max(observed_max_lift, lift)
        if lift < delta_step:
            LOG.info("  lift below delta_step=%.4f; greedy halts (greedy-stopping invariant)", delta_step)
            break
        selected.append(best["candidate"])
        chosen_window = best["window"]
        remaining.remove(best["candidate"])
        current_auc = best["auc"]

        # Checkpoint AFTER the step commits (#91): at most one step is lost on
        # interruption. Atomic write so a crash mid-write can't corrupt it.
        if checkpoint_path is not None and config_signature is not None:
            _write_json_atomic(checkpoint_path, {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "config_signature": config_signature,
                "written_at_utc": datetime.now(timezone.utc).isoformat(),
                "state": {
                    "selected": selected,
                    "chosen_window": chosen_window,
                    "remaining": remaining,
                    "current_auc": float(current_auc),
                    "step": step,
                    "history": history,
                },
            })

        # Floor-aware early-abort (outcome-neutral; see MIN_STEPS_BEFORE_ABORT note).
        # The best AUC any number of remaining steps could reach is bounded above by
        # current_auc + (#steps left) × (best single-step lift ever seen). If even that
        # optimistic ceiling falls short of the floor, the walk is HARD_FAIL-bound — stop.
        if lock_floor is not None and step >= min_steps_before_abort:
            remaining_allowed = min(len(remaining), max_steps - step)
            optimistic_ceiling = current_auc + remaining_allowed * observed_max_lift
            if remaining_allowed > 0 and optimistic_ceiling < lock_floor:
                LOG.info(
                    "  EARLY-ABORT (floor unreachable): current_auc=%.4f + %d steps × "
                    "max-lift %.4f = optimistic ceiling %.4f < lock_floor %.4f. "
                    "Walk is HARD_FAIL-bound; aborting greedy to save compute (outcome-neutral).",
                    current_auc, remaining_allowed, observed_max_lift,
                    optimistic_ceiling, lock_floor,
                )
                early_abort = True
                break
    return {
        "selected_indicators": selected,
        "chosen_window": chosen_window,
        "final_global_auc": float(current_auc),
        "history": history,
        "early_abort_floor_unreachable": early_abort,
    }


# ---- Per-cohort ECE ---------------------------------------------------------


def compute_ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    if len(probs) == 0:
        return float("nan")
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(probs, bins) - 1, 0, n_bins - 1)
    n = len(probs)
    ece = 0.0
    for b in range(n_bins):
        mask = idx == b
        if mask.sum() == 0:
            continue
        ece += (mask.sum() / n) * abs(probs[mask].mean() - labels[mask].mean())
    return float(ece)


def per_cohort_loco_and_ece(
    probs: np.ndarray,
    labels: np.ndarray,
    countries: np.ndarray,
    years: np.ndarray,
    cohort_assignments: dict,
) -> dict[str, dict[str, Any]]:
    cohorts = {"fragile-state": [], "mid-tier": [], "stable-democracy": []}
    for i in range(len(probs)):
        c = str(countries[i]).title()  # Title Case for cohort lookup
        yr = str(int(years[i]))
        cohort = cohort_assignments.get(c, {}).get(yr)
        if cohort in cohorts:
            cohorts[cohort].append((float(probs[i]), int(labels[i])))
    out: dict[str, dict[str, Any]] = {}
    rng = np.random.default_rng(0)
    for cohort, data in cohorts.items():
        if len(data) < 5:
            out[cohort] = {"n": len(data), "loco_auc": None, "ece": None, "low_confidence": True}
            continue
        p = np.array([x[0] for x in data])
        y = np.array([x[1] for x in data])
        if len(np.unique(y)) < 2:
            cohort_auc = float("nan")
        else:
            cohort_auc = compute_auc(p, y)
        ece = compute_ece(p, y)
        # Bootstrap ECE 95% CI
        boots = []
        for _ in range(500):
            ix = rng.integers(0, len(p), len(p))
            boots.append(compute_ece(p[ix], y[ix]))
        # Reliability diagram bins (per QA PR#90 B2 residual: was None;
        # F-ML-1 §6 field 4 requires `reliability_diagram_bins` to be populated)
        n_bins = 10
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
        bin_idx = np.clip(np.digitize(p, bin_edges) - 1, 0, n_bins - 1)
        reliability_bins = []
        for b in range(n_bins):
            mask = bin_idx == b
            if mask.sum() == 0:
                reliability_bins.append({
                    "bin_lower": float(bin_edges[b]),
                    "bin_upper": float(bin_edges[b + 1]),
                    "n_in_bin": 0,
                    "mean_predicted": None,
                    "mean_actual": None,
                })
            else:
                reliability_bins.append({
                    "bin_lower": float(bin_edges[b]),
                    "bin_upper": float(bin_edges[b + 1]),
                    "n_in_bin": int(mask.sum()),
                    "mean_predicted": float(p[mask].mean()),
                    "mean_actual": float(y[mask].mean()),
                })
        out[cohort] = {
            "n": int(len(p)),
            "loco_auc": float(cohort_auc) if not np.isnan(cohort_auc) else None,
            "ece": float(ece),
            "ece_ci95_lo": float(np.percentile(boots, 2.5)),
            "ece_ci95_hi": float(np.percentile(boots, 97.5)),
            "low_confidence": len(p) < 30,
            "reliability_diagram_bins": reliability_bins,
        }
    return out


# ---- Descriptive emit per §6 + Miriam M14-1 ---------------------------------


def extract_trajectory_signature_full(
    panel: pd.DataFrame, country: str, year: int, window: int
) -> dict[str, Any]:
    """Per Miriam M14-1: full-window per-tertile + per-year temporal profile."""
    cdf = panel[panel["country"] == country]
    series = cdf.set_index("year")["value"]
    window_data = series.loc[year - window:year - 1].dropna()
    if len(window_data) < 3:
        return {"available": False}

    # Z-score
    baseline = series.loc[max(year - 25, series.index.min()):year - 1].dropna()
    mu = float(baseline.mean())
    sd = float(baseline.std()) or 1.0
    z = (window_data.values - mu) / sd

    t1, t2, t3 = np.array_split(z, 3)
    return {
        "available": True,
        "per_tertile_z_score": [
            float(t1.mean()) if len(t1) else 0.0,
            float(t2.mean()) if len(t2) else 0.0,
            float(t3.mean()) if len(t3) else 0.0,
        ],
        "per_tertile_direction_sign": [
            int(np.sign(t1.mean())) if len(t1) else 0,
            int(np.sign(t2.mean())) if len(t2) else 0,
            int(np.sign(t3.mean())) if len(t3) else 0,
        ],
        "temporal_profile": [float(v) for v in z.tolist()],
        "years_covered": [int(y) for y in window_data.index.tolist()],
    }


def emit_descriptive(
    selected: list[str],
    chosen_window: int,
    panels: dict[str, pd.DataFrame],
    samples: pd.DataFrame,
    final_loco: dict,
    architecture: str,
    feature_importances: list[float] | None,
    audit_chart_path: Path,
    per_cohort_profile: dict[str, dict[str, Any]] | None = None,
    window_ci: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Per F-ML-1 §6: 5 descriptive emit fields."""

    # Field 1: learned_canonical_length
    field_1 = {
        "best_window": int(chosen_window),
        "window_ci": [int(window_ci[0]), int(window_ci[1])] if window_ci else [int(chosen_window), int(chosen_window)],
        "window_search_grid": WINDOW_GRID,
        "window_ci_method": "bca_bootstrap_b2000",
    }

    # Field 2: indicator_importance_profile (SHAP-ranked)
    # For XGBoost, use feature_importances_; for LR, use abs coefficients
    # SHAP would be ideal but we'll use built-in importances for the PoC; flag as approximation
    field_2 = []
    if feature_importances is not None:
        n_feat_per_ind = N_FEATURES_PER_INDICATOR
        for k, ind in enumerate(selected):
            block = feature_importances[k * n_feat_per_ind:(k + 1) * n_feat_per_ind]
            field_2.append({
                "indicator_id": ind,
                "importance_mean_abs": float(np.mean(np.abs(block))),
                "direction_sign": 1 if np.mean(block) > 0 else -1,
            })
        field_2 = sorted(field_2, key=lambda r: -r["importance_mean_abs"])

    # Field 3: learned_aggregation_weights (Marcus M8-2 unified schema)
    field_3 = {
        "type": "tree_importance" if architecture == "XGBoost" else "linear_coef",
        "values": [
            {"indicator_id": ind, "weight": float(np.mean(np.abs(
                feature_importances[k * N_FEATURES_PER_INDICATOR:(k + 1) * N_FEATURES_PER_INDICATOR]
                if feature_importances is not None else [0.0]
            )))}
            for k, ind in enumerate(selected)
        ],
    }

    # Field 5: ranked_trajectory_signature (Miriam M14-1, FULL window)
    # frontend §B.1/§F: emit ALL positives (was head(5), a 5-sample interim) so the
    # bake aggregates the canonical movement shape (mean/p25/p75, lead-year aligned)
    # over the FULL positive corpus. The bake reads whatever `samples` are present and
    # records `samples_used`. Cost is ~O(n_positives x n_indicators) cheap DataFrame
    # slices — acceptable at walk scale. The Saudi-Azeri audit plot uses only
    # `samples[:3]`, so it is unaffected.
    positives = samples[samples["label"] == 1]
    field_5 = {"saudi_azeri_audit_url": str(audit_chart_path), "per_indicator_signatures": []}
    for ind in selected:
        sigs = []
        for _, row in positives.iterrows():
            sig = extract_trajectory_signature_full(
                panels[ind], str(row["country"]), int(row["year"]), chosen_window
            )
            if sig["available"]:
                sigs.append({
                    "country": str(row["country"]),
                    "year": int(row["year"]),
                    **sig,
                })
        field_5["per_indicator_signatures"].append({
            "indicator_id": ind,
            "samples": sigs,
        })

    # Field 4: per_cohort_calibration_profile (QA PR#90 B2 — was missing from emit)
    # Per F-ML-1 §6: required field mapping per-cohort calibration into the descriptive emit
    # (distinct from the summary root's `per_cohort` block; this is the
    # methodology-archive-grade artifact for Lloyd's audit).
    field_4 = {}
    if per_cohort_profile is not None:
        for cohort, info in per_cohort_profile.items():
            field_4[cohort] = {
                "ece": info.get("ece"),
                "ci95_lo": info.get("ece_ci95_lo"),
                "ci95_hi": info.get("ece_ci95_hi"),
                "n_test": info.get("n"),
                "reliability_diagram_bins": info.get("reliability_diagram_bins"),
            }

    return {
        "learned_canonical_length": field_1,
        "indicator_importance_profile": field_2,
        "learned_aggregation_weights": field_3,
        "per_cohort_calibration_profile": field_4,
        "ranked_trajectory_signature": field_5,
    }


# ---- Saudi-Azeri visual audit chart ----------------------------------------


def plot_saudi_azeri_audit(
    descriptive: dict, panels: dict[str, pd.DataFrame], chosen_window: int, save_path: Path
) -> str:
    """Per Miriam M14-1: visual auditability vs Saudi-Azeri canonical example."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        n_inds = len(descriptive["ranked_trajectory_signature"]["per_indicator_signatures"])
        if n_inds == 0:
            return ""
        fig, axes = plt.subplots(n_inds, 1, figsize=(10, 3 * n_inds), squeeze=False)
        for k, ind_sig in enumerate(descriptive["ranked_trajectory_signature"]["per_indicator_signatures"]):
            ax = axes[k, 0]
            for sample in ind_sig["samples"][:3]:
                profile = sample.get("temporal_profile", [])
                if profile:
                    ax.plot(profile, alpha=0.7, label=f"{sample['country']} {sample['year']}")
            ax.set_title(f"{ind_sig['indicator_id']} — {chosen_window}y trajectory (z-score)")
            ax.axhline(0, color="grey", linewidth=0.5)
            ax.legend(fontsize=8)
        plt.tight_layout()
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=80)
        plt.close()
        LOG.info("Saudi-Azeri audit chart saved → %s", save_path)
        return str(save_path)
    except Exception as e:
        LOG.warning("Audit chart generation failed: %s", e)
        return "chart_generation_failed"  # sentinel per QA PR#90 F4


# ---- Main orchestrator ------------------------------------------------------


def _to_strict_json(obj: Any) -> str:
    def _w(o):
        if isinstance(o, dict):
            return {k: _w(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_w(v) for v in o]
        if isinstance(o, float):
            if np.isnan(o) or np.isinf(o):
                return None
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            v = float(o)
            return None if (np.isnan(v) or np.isinf(v)) else v
        if isinstance(o, np.ndarray):
            return [_w(x) for x in o.tolist()]
        return o
    return json.dumps(_w(obj), indent=2, ensure_ascii=False)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser. Extracted from `_main` so tests can exercise
    the SAME parser construction code path (avoiding shadow-parser drift)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--recipe-id", default=DEFAULT_RECIPE_ID,
                        help="Recipe ID (e.g., civil_war_and_insurgency, economic_recession).")
    parser.add_argument("--hybrid-baseline", type=float, default=DEFAULT_HYBRID_BASELINE,
                        help="Per-recipe cascade-side baseline (Marcus M8-1 provenance). "
                             "Default 0.7686 = civil_war Hybrid LOCK; per-recipe pre-reg overrides.")
    parser.add_argument("--lock-floor", type=float, default=DEFAULT_LOCK_FLOOR,
                        help="Per-recipe global LOCO-AUC LOCK floor (§3.1 Gate 1). "
                             "Default 0.7986 = civil_war (Hybrid + 0.03); per-recipe pre-reg overrides.")
    parser.add_argument("--cohort-loco-floor", type=float, default=DEFAULT_COHORT_LOCO_FLOOR,
                        help="Per-cohort LOCO-AUC LOCK floor (§3.1 Gate 2). "
                             "Default 0.68 = civil_war Kwame R1 anchor; per-recipe pre-reg overrides.")
    parser.add_argument("--panel-dir", type=Path,
                        default=REPO_ROOT / "data" / "parquet_panels")
    parser.add_argument("--positives-csv", type=Path, default=None,
                        help="Positives CSV path. Defaults to "
                             "data/shape_inputs_v2/{recipe-id}/positives.csv.")
    parser.add_argument("--cohort-sidecar", type=Path,
                        default=REPO_ROOT.parent / "qgi-data" / "reference" / "cohort-assignments.json")
    parser.add_argument("--no-checkpoint", action="store_true",
                        help="Disable greedy checkpoint/resume (#91). Checkpointing is ON by "
                             "default (founder 2026-05-24: mandatory for all recipes). The data "
                             "fingerprint in the config signature already forces a fresh start "
                             "when panels/positives change, so this is rarely needed — use only "
                             "to force a clean from-scratch run on UNCHANGED data, or in tests.")
    parser.add_argument("--max-greedy-steps", type=int, default=12)
    parser.add_argument("--negatives-per-positive", type=int, default=3)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--n-jobs", type=int, default=1,
                        help="#961: parallel workers for the (candidate × window) grid "
                             "within each greedy step. Default 1 (serial). Bit-identical "
                             "to serial at any n_jobs (thread backend, ordered reduce). "
                             "The fleet sets this per-recipe by vCPU count (#962).")
    parser.add_argument("--max-candidates-debug", type=int, default=None,
                        help="Debug mode: cap candidates at N (NOT for production walks).")
    return parser


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    recipe_id = args.recipe_id
    hybrid_baseline = float(args.hybrid_baseline)
    lock_floor = float(args.lock_floor)
    cohort_loco_floor = float(args.cohort_loco_floor)
    if args.positives_csv is None:
        args.positives_csv = REPO_ROOT / "data" / "shape_inputs_v2" / recipe_id / "positives.csv"

    LOG.info("F-ML-1 PoC starting — recipe=%s", recipe_id)
    LOG.info("Per-recipe LOCK params: hybrid_baseline=%.4f, lock_floor=%.4f, cohort_loco_floor=%.4f",
             hybrid_baseline, lock_floor, cohort_loco_floor)
    t0 = time.time()

    # Load positives + build negatives.
    # Country-name normalization (2026-05-22 mechanical correctness fix):
    # parquet panels + cohort-assignments.json use space-separated names
    # ("Costa Rica", "Bosnia and Herzegovina") AND hyphenated forms for some
    # cases ("Guinea-Bissau", "Timor-Leste") AND lowercase conjunctions/articles
    # ("Republic of the Congo"). The naive `.title()` was incorrect for ALL
    # multi-word names. `normalize_country_id` handles all 16 observed
    # positives.csv multi-word country_ids: 12 via simple replace+title, 4 via
    # COUNTRY_NAME_OVERRIDES. Pre-fix civil_war walk silently dropped 41
    # multi-word events at panel lookup (256 → 192 effective N_pos).
    # Civil_war DECISION stands as-ratified; this fix applies to walks from
    # 2026-05-22 forward. See per-recipe-pre-reg/economic-recession-pre-reg.md §3.a.
    pos = pd.read_csv(args.positives_csv)
    pos["country"] = pos["country_id"].apply(normalize_country_id)
    pos = pos.rename(columns={"event_year": "year"})
    pos["label"] = 1
    LOG.info("Positives: %d rows, %d unique countries", len(pos), pos["country"].nunique())

    # Startup validation: surface any normalized country name that is missing
    # from the parquet panels or cohort-assignments.json. Fail fast rather
    # than silently dropping samples at feature-extraction time (the bug class
    # discovered pre-walk-2 on 2026-05-22). At least one panel must contain
    # the country for it to participate in LOCO; missing from cohort-assignments
    # is non-fatal (the cohort gate excludes the sample but global LOCO still
    # counts it).
    pos_countries_for_check = set(pos["country"].unique())
    sample_panel_path = next(args.panel_dir.iterdir())
    sample_panel = pd.read_parquet(sample_panel_path / f"{sample_panel_path.name}.parquet")
    panel_countries_in_sample = set(sample_panel["country"].dropna().unique())
    missing_in_panel = pos_countries_for_check - panel_countries_in_sample
    if missing_in_panel:
        LOG.warning(
            "Countries in positives.csv not found in sample panel %s — "
            "feature extraction will fail for these and they will be "
            "silently dropped (verify normalize_country_id covers them): %s",
            sample_panel_path.name, sorted(missing_in_panel),
        )
    # Load cohort-assignments.json ONCE at startup and retain in memory
    # for the LOCK GATE EVAL phase. Reading the file a second time at LOCK
    # GATE EVAL (~4-5h later) was the failure mode on the original walk-4
    # attempt 2026-05-22 — a git checkout in qgi-data between startup and
    # eval swapped the working-tree file out, crashing the eval after the
    # full greedy outer loop had already run.
    with open(args.cohort_sidecar, encoding="utf-8") as _f:
        _cohort_payload = json.load(_f)
    cohort_assignments_cached = _cohort_payload["assignments"]
    missing_in_cohorts = pos_countries_for_check - set(cohort_assignments_cached.keys())
    if missing_in_cohorts:
        LOG.warning(
            "Countries in positives.csv not in cohort-assignments.json — "
            "samples will count toward global LOCO but be excluded from "
            "per-cohort gate evaluation: %s",
            sorted(missing_in_cohorts),
        )

    samples = build_samples(pos, negatives_per_positive=args.negatives_per_positive, seed=args.seed)
    LOG.info("Samples built: %d positives + %d negatives", (samples["label"] == 1).sum(), (samples["label"] == 0).sum())

    # Load all candidate panels
    all_candidates = list_candidate_indicators(args.panel_dir)
    if args.max_candidates_debug:
        all_candidates = all_candidates[:args.max_candidates_debug]
        LOG.warning("DEBUG: capping candidates at %d (NOT production-walk)", args.max_candidates_debug)
    LOG.info("Loading %d candidate panels...", len(all_candidates))
    panels = {ind: load_panel(ind, args.panel_dir) for ind in all_candidates}

    # Univariate screen (per §5.1)
    LOG.info("=== UNIVARIATE SCREEN ===")
    top_n_inds, univariate_scores = univariate_loco_screen(samples, all_candidates, panels)
    LOG.info("Top-%d indicators selected by univariate LOCO-AUC", len(top_n_inds))

    # Architecture per §4.2 — civil_war N_pos = 192 ≥ 60 → XGBoost default
    n_pos = int((samples["label"] == 1).sum())
    architecture = "LR" if n_pos < 60 else "XGBoost"
    LOG.info("Architecture (pre-walk per §4.2): %s (N_pos=%d)", architecture, n_pos)

    # Greedy outer loop + concurrent window search (per §5.2-§5.4)
    LOG.info("=== GREEDY OUTER LOOP + WINDOW SEARCH ===")
    cap = THIN_RECIPE_CAP if n_pos < 60 else args.max_greedy_steps

    # Checkpoint/resume (#91). Two levels: (1) greedy-result.json lets a crash
    # AFTER greedy (e.g. the walk-4 LOCK-gate crash) skip the whole greedy loop;
    # (2) greedy-checkpoint.json lets a crash DURING greedy resume mid-loop. Both
    # are guarded by a config signature so only an identical walk config resumes.
    data_fp = panel_data_fingerprint(args.panel_dir, args.positives_csv)
    sig = greedy_config_signature(
        args.recipe_id, top_n_inds, architecture, DELTA_STEP, cap, args.seed, data_fp,
    )
    LOG.info("Greedy config signature %s (data fingerprint %s) — checkpoint resume guarded by this",
             sig[:12], data_fp)
    greedy_ckpt_path = args.output_dir / GREEDY_CHECKPOINT_NAME
    greedy_result_path = args.output_dir / GREEDY_RESULT_NAME

    greedy = None
    if not args.no_checkpoint:
        cached = load_greedy_checkpoint(greedy_result_path, sig)
        if cached is not None and "result" in cached:
            greedy = cached["result"]
            LOG.info("SKIPPING greedy loop — resuming from completed greedy-result.json "
                     "(%d selected, window=%s)", len(greedy["selected_indicators"]), greedy["chosen_window"])

    if greedy is None:
        greedy = greedy_outer_loop(
            samples, top_n_inds, panels, architecture,
            delta_step=DELTA_STEP, max_steps=cap, seed=args.seed,
            checkpoint_path=None if args.no_checkpoint else greedy_ckpt_path,
            config_signature=None if args.no_checkpoint else sig,
            lock_floor=lock_floor,
            n_jobs=args.n_jobs,
        )
        # Persist the completed greedy result BEFORE LOCK GATE EVAL so a crash
        # in the (cheaper but historically fragile) LOCK phase never re-runs the
        # expensive greedy search. Reuses the checkpoint envelope + signature.
        if not args.no_checkpoint:
            _write_json_atomic(greedy_result_path, {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "config_signature": sig,
                "written_at_utc": datetime.now(timezone.utc).isoformat(),
                "state": {"selected": greedy["selected_indicators"], "step": len(greedy["selected_indicators"])},
                "result": greedy,
            })
    LOG.info("Greedy result: %d selected, window=%s, final_AUC=%.4f",
             len(greedy["selected_indicators"]), greedy["chosen_window"], greedy["final_global_auc"])

    # Final fit with selected set + chosen window.
    # Per F-ML-N §4.2 amendment 2026-05-22: XGBoost is BINDING for N_pos >= 60.
    # The prior §4.2 fold-variance MLP trigger is removed entirely (cross-recipe
    # empirical evidence: civil_war + econ_recession both showed MLP collapse
    # by ~0.20 AUC). MLP is preserved in §4.1 menu but cannot be auto-swapped
    # without a fresh F-ML-N+1 pre-registration. See:
    # docs/specs/internal/decisions/artifacts/F-ML-N-§4.2-amendment-2026-05-22.md
    LOG.info("=== FINAL LOCO ===")
    X, y, c, yr = build_X_y(samples, greedy["selected_indicators"], greedy["chosen_window"], panels)
    final = fit_predict_loco(X, y, c, yr, architecture=architecture, seed=args.seed)
    chosen_arch = architecture
    LOG.info("%s final LOCO-AUC=%.4f", chosen_arch, final["global_auc"])

    # §4.2-SD informational stability diagnostic (per Kwame BLOCKING rider:
    # MANDATORY logging per walk; non-optional). Records fold-variance + label
    # but does NOT gate architecture. Per Miriam M14-R5 BLOCKING: persistent
    # HIGH variance MAY be cited as contextual evidence in support of a future
    # F-ML-N+1 amendment, which requires its own prior-walk provenance + 8/8
    # ratification INDEPENDENT of this §4.2-SD signal.
    stability_diagnostic = _build_stability_diagnostic(final["per_country_auc"])
    fv = stability_diagnostic["fold_variance"]
    LOG.info("§4.2-SD diagnostic: fold-variance=%.4f, fold-AUC mean=%.4f, label=%s "
             "(informational only; does NOT gate architecture)",
             fv, stability_diagnostic["fold_auc_mean"], stability_diagnostic["label"])

    # === Coverage audit (sample-truncation fix; Majles MR-14-A1, 2026-05-25) ===
    # "No silent sample restriction": surface how much of the evidence the selected
    # set actually evaluates. The foreign_intervention defect (0.9147 on 10/174
    # positives) hid here. A walk that keeps too little of the evidence is
    # COVERAGE_FAIL — it does NOT graduate on a truncated subsample.
    coverage = coverage_report(samples, greedy["selected_indicators"], greedy["chosen_window"], panels)
    LOG.info("COVERAGE AUDIT: %d/%d positives survive (%.1f%%) across %d countries; "
             "negatives %.1f%%",
             coverage["n_pos_survive"], coverage["n_pos_total"], 100 * coverage["pos_coverage"],
             coverage["n_countries_survive"], 100 * coverage["neg_coverage"])
    coverage_pass = coverage_gate_ok(coverage)
    if not coverage_pass:
        LOG.warning("COVERAGE_FAIL: selected set keeps too little of the evidence base "
                    "(positives %.1f%%, %d countries, n=%d) — refusing to grade on a "
                    "truncated subsample.", 100 * coverage["pos_coverage"],
                    coverage["n_countries_survive"], coverage["n_pos_survive"])

    # === Temporal-confound + era-stratified diagnostics (bugfix facets 3+4) ===
    # Non-gating. confound_auc≈0.50 confirms time-matched negatives neutralised the
    # calendar-time confound; era_loco surfaces signal concentrated in one era.
    confound_auc = temporal_confound_auc(samples)
    era_loco = era_stratified_loco(final["probs"], final["labels"], final["years"])
    # FU-1 (QA review #112): on a COVERAGE_FAIL walk these AUCs are computed on
    # the SAME truncated subsample the gate rejected — tag them so a DECISION reader
    # never mistakes inflated per-era/per-window numbers for real signal.
    era_loco["coverage_truncated"] = bool(not coverage_pass)
    LOG.info("DIAGNOSTIC temporal-confound AUC(year->label)=%.4f (≈0.50 = time-matched); "
             "era pre/post-%d spread=%s%s", confound_auc, era_loco["boundary"],
             era_loco["pre_post_spread"],
             "  [TRUNCATED — coverage_fail]" if not coverage_pass else "")

    # LOCK gate eval
    lock_gate_eval_ts = datetime.now(timezone.utc).isoformat()
    LOG.info("=== LOCK GATE EVAL ===")

    # Bootstrap CI on AUC
    LOG.info("BCa bootstrap on Global LOCO-AUC (B=%d)...", BCA_BOOTSTRAP_B)
    auc_ci = bca_bootstrap_auc_ci(final["probs"], final["labels"], B=BCA_BOOTSTRAP_B, seed=args.seed)

    # Per-cohort LOCO + ECE — reuses the cohort_assignments dict loaded
    # at startup (cohort_assignments_cached) rather than re-reading from
    # disk. See startup-load rationale comment for the failure mode.
    LOG.info("Per-cohort LOCO + ECE...")
    cohort_assignments = cohort_assignments_cached
    per_cohort = per_cohort_loco_and_ece(
        final["probs"], final["labels"], final["countries"], final["years"], cohort_assignments
    )

    # Per-cohort BCa CI
    for cohort, info in per_cohort.items():
        if info["n"] >= 30 and info["loco_auc"] is not None:
            mask = np.array([
                cohort_assignments.get(str(co).title(), {}).get(str(int(yr_)), None) == cohort
                for co, yr_ in zip(final["countries"], final["years"])
            ])
            if mask.sum() >= 30:
                ci = bca_bootstrap_auc_ci(
                    final["probs"][mask], final["labels"][mask], B=BCA_BOOTSTRAP_B, seed=args.seed
                )
                info["loco_auc_ci95_lo"] = ci["ci95_lo"]
                info["loco_auc_ci95_hi"] = ci["ci95_hi"]

    # §3.1 three-gate evaluation (per-recipe floor parameters)
    global_pass = final["global_auc"] >= lock_floor
    cohort_loco_pass = all(
        (info["n"] < 5) or (info["loco_auc"] is not None and info["loco_auc"] >= cohort_loco_floor)
        for info in per_cohort.values()
    )
    cohort_ece_pass = all(
        (info["n"] < 5) or (info["ece"] is not None and info["ece"] <= COHORT_ECE_GATE)
        for info in per_cohort.values()
    )

    # Chance-baseline gate (MR-14-A2): the global LOCO CI must clear chance. If the
    # 95% lower bound is at/below 0.50, the recipe is statistically a coin flip and
    # cannot graduate regardless of the point estimate.
    chance_pass = bool(auc_ci["ci95_lo"] > CHANCE_FLOOR)
    if not chance_pass:
        LOG.warning("CHANCE_FAIL: global LOCO 95%% CI lower bound %.4f <= chance floor %.2f "
                    "— indistinguishable from a coin flip; refusing to grade as signal.",
                    auc_ci["ci95_lo"], CHANCE_FLOOR)

    verdict = classify_verdict(coverage_pass, chance_pass, global_pass,
                               cohort_loco_pass, cohort_ece_pass)
    # A floor-unreachable early-abort routes to INCOMPLETE (not auto-HARD_FAIL) — the
    # heuristic abort bound cannot justify a verdict (PR #116 / Ji-Hoon+Kwame 2026-05-27).
    verdict = early_abort_verdict_override(verdict, greedy)
    if verdict == "INCOMPLETE_CEILING_BELOW_FLOOR":
        LOG.warning("EARLY-ABORT halt → verdict INCOMPLETE_CEILING_BELOW_FLOOR (NOT graded "
                    "as HARD_FAIL): partial walk surfaced for human/Majles adjudication.")

    borderline = bool(auc_ci["ci95_lo"] < lock_floor) if verdict == "LOCK" else False

    # Descriptive emit (per §6 + Miriam M14-1)
    LOG.info("=== DESCRIPTIVE EMIT ===")
    if chosen_arch == "XGBoost":
        # Re-fit one final XGBoost on full data to extract feature_importances_
        from xgboost import XGBClassifier
        X_all = np.where(np.isfinite(X), X, 0.0)
        full_xgb = XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            scale_pos_weight=(y==0).sum()/max((y==1).sum(),1),
            eval_metric="logloss", random_state=args.seed, verbosity=0, n_jobs=1,
        )
        full_xgb.fit(X_all, y)
        feature_importances = list(full_xgb.feature_importances_)
    else:
        feature_importances = None  # MLP: would need SHAP; skip for now

    audit_chart_path = args.output_dir / "saudi_azeri_audit.png"

    # window_search_auxiliary_note (per Nasrin N-2) + window_ci bootstrap (per Roshani R18-B)
    LOG.info("=== WINDOW-SEARCH AUXILIARY + WINDOW_CI BOOTSTRAP ===")
    final_step_history = greedy["history"][-1] if greedy["history"] else {}
    loco_auc_per_window: dict[int, float] = {}
    per_window_predictions: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    if greedy["selected_indicators"]:
        for w in WINDOW_GRID:
            Xw, yw, cw, yrw = build_X_y(samples, greedy["selected_indicators"], w, panels)
            if len(Xw) < 30 or len(np.unique(yw)) < 2:
                continue
            r = fit_predict_loco(Xw, yw, cw, yrw, architecture=chosen_arch, seed=args.seed)
            loco_auc_per_window[w] = float(r["global_auc"])
            per_window_predictions[w] = (r["probs"], r["labels"])
    LOG.info("BCa argmax-window bootstrap (B=%d) for window_ci...", BCA_BOOTSTRAP_B)
    window_ci_pair = window_ci_via_bootstrap_argmax(per_window_predictions, B=BCA_BOOTSTRAP_B, seed=args.seed)
    LOG.info("window_ci=[%d, %d] (best=%s)", window_ci_pair[0], window_ci_pair[1], greedy["chosen_window"])
    window_aux = {
        "n_combinations_evaluated_final_step": int(len(WINDOW_GRID) * max(1, len(greedy["history"]))),
        "loco_auc_spread_across_windows": loco_auc_per_window,
        # FU-1 (QA review #112): these per-window AUCs use the selected (possibly
        # sparse) set, so on a COVERAGE_FAIL walk they are computed on the truncated
        # subsample — flag so they are never read as signal.
        "coverage_truncated": bool(not coverage_pass),
    }

    # Now build the descriptive emit (depends on per_cohort + window_ci, computed above)
    descriptive = emit_descriptive(
        greedy["selected_indicators"], greedy["chosen_window"], panels, samples,
        final, chosen_arch, feature_importances, audit_chart_path,
        per_cohort_profile=per_cohort,
        window_ci=window_ci_pair,
    )
    chart_path = plot_saudi_azeri_audit(descriptive, panels, greedy["chosen_window"], audit_chart_path)
    descriptive["ranked_trajectory_signature"]["saudi_azeri_audit_url"] = chart_path

    # Compose DECISION-ready summary (per §10)
    elapsed = time.time() - t0
    summary = {
        "f_ml_1_pre_reg": "docs/specs/internal/ops/ml-track/F-ML-1-pre-reg.md",
        "filed": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "recipe_id": recipe_id,
        "verdict": verdict,
        "borderline_lock": borderline,
        "n_positives": n_pos,
        "n_negatives": int((samples["label"] == 0).sum()),
        "architecture": chosen_arch,
        "architecture_provenance": {
            "default_per_n_pos_rule": "LR (<60) | XGBoost (>=60)",
            "amendment_reference": "F-ML-N §4.2 amendment 2026-05-22 (qgi-aws-tf#864): XGBoost binding for N_pos>=60; §4.2 fold-variance MLP trigger removed entirely",
            "amendment_artifact": "docs/specs/internal/decisions/artifacts/F-ML-N-§4.2-amendment-2026-05-22.md",
            "lock_gate_eval_ts": lock_gate_eval_ts,
        },
        "stability_diagnostic": stability_diagnostic,
        "coverage_audit": {
            **coverage,
            "coverage_pass": bool(coverage_pass),
            "thresholds": {
                "min_pos_survival": MIN_POS_SURVIVAL,
                "min_effective_npos": MIN_EFFECTIVE_NPOS,
                "min_survive_countries": MIN_SURVIVE_COUNTRIES,
                "min_neg_survival": MIN_NEG_SURVIVAL,
            },
            "note": "Sample-truncation audit (Majles MR-14-A1, 2026-05-25). coverage_pass=false → COVERAGE_FAIL verdict; never graded on a truncated subsample.",
        },
        "per_recipe_floor_provenance": {
            "hybrid_baseline": hybrid_baseline,
            "lock_floor": lock_floor,
            "cohort_loco_floor": cohort_loco_floor,
            "note": (
                "Marcus M8-1 path-(a)/(b)/(c) provenance: see F-ML-1 §7 "
                "(civil_war_and_insurgency / cascade-inherited) or "
                "docs/specs/internal/ops/ml-track/per-recipe-pre-reg/ "
                "(other recipes; recipe_id with `_` -> `-` is the markdown filename stem)."
            ),
        },
        "global_loco": auc_ci,
        "per_cohort": per_cohort,
        "gates_eval": {
            "global_loco_pass": bool(global_pass),
            "per_cohort_loco_pass": bool(cohort_loco_pass),
            "per_cohort_ece_pass": bool(cohort_ece_pass),
            "chance_baseline_pass": bool(chance_pass),
            "global_floor": lock_floor,
            "cohort_loco_floor": cohort_loco_floor,
            "cohort_ece_gate": COHORT_ECE_GATE,
            "chance_floor": CHANCE_FLOOR,
        },
        "chance_baseline_gate": {
            "ci95_lo": auc_ci["ci95_lo"],
            "chance_floor": CHANCE_FLOOR,
            "chance_baseline_pass": bool(chance_pass),
            "bootstrap_seed": args.seed,  # RPM-2: record seed so a borderline CI is reproducible
            "bootstrap_B": BCA_BOOTSTRAP_B,
            "scope": "global_loco_only",  # RPM-1: per-cohort CI does not trigger CHANCE_FAIL
            "note": "MR-14-A2 (2026-05-25). chance_baseline_pass=false → CHANCE_FAIL verdict; the global LOCO CI straddles a coin flip. Global CI only (RPM-1).",
        },
        "temporal_confound_auc": (None if (isinstance(confound_auc, float) and confound_auc != confound_auc) else round(confound_auc, 4)),
        "era_stratified_loco": era_loco,
        "univariate_screen": {
            "method": "LR, 10y window, ranked by global LOCO-AUC",
            "n_candidates_evaluated": len(all_candidates),
            "top_n_kept": TOP_N_PREFILTER,
            "top_n_indicators": top_n_inds,
        },
        "greedy_outer_loop": greedy,
        # Note: top-level "fold_variance" removed per QA PR#92 FU-1.
        # Canonical location is `stability_diagnostic.fold_variance` (§4.2-SD).
        "descriptive_emit": descriptive,
        "window_search_auxiliary_note": window_aux,
        # #969: Beta calibration emit (Kull et al. 2017) on the pooled LOCO predictions.
        # APPEND-ONLY — does not change selected_indicators, chosen_window, AUC, the
        # gates_eval, or the verdict. The verdict policy (whether LOCK requires
        # ECE <= floor in addition to discrimination) is a Majles methodology gate
        # handled separately; this emit is the data the policy will consume.
        # Bit-identity is preserved because the calibration computation only READS
        # `final["probs"]` and `final["labels"]` (already-computed pooled LOCO arrays)
        # and writes a NEW top-level field. No upstream value is changed.
        "calibration": _beta_cal.compute_calibration_block(final["probs"], final["labels"]),
    }
    out_path = args.output_dir / "f-ml-1-poc-summary.json"
    out_path.write_text(_to_strict_json(summary), encoding="utf-8")
    LOG.info("Wrote %s", out_path)
    LOG.info("=== F-ML-1 PoC VERDICT: %s (borderline=%s) ===", verdict, borderline)
    LOG.info("Elapsed: %.1f minutes", elapsed / 60)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
