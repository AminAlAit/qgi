"""
Phase 4 / Phase 5 v0.1a — validation gate for the EB-shrunken weight matrix.

Hypothesis: countries whose indicator profile, weighted by Phase 3's
per-event-category weights, looks more anomalous should have HIGHER
rates of those event categories in held-out years.

Test:
  For each (country, event_category) in the weight matrix's coverage:
    1. Compute country's z-score per indicator (across all countries
       at the cutoff year)
    2. anomaly_score = sum over (indicator in event_category) of
         f(z_score, direction) * weight
       where f() depends on the ablation arm — see Ablation arms below.
    3. Compare ranking of anomaly_scores vs ground-truth events that
       happened post-cutoff (binary: did the country experience this
       event_category in [cutoff+1, end_year]?)

Ablation arms (Phase 5 v0.1a, 4-arm design — see
docs/specs/internal/ops/cascade-track/phase-5-v0.1a.md):

  | Arm | Formula                          | #591 filter? | Output captures              |
  |-----|----------------------------------|--------------|------------------------------|
  | A   | direction × z_score              | applied      | Both fixes simultaneously    |
  | B   | direction × z_score              | NOT applied  | Formula fix only             |
  | C   | |z_score|                        | applied      | Filter fix only              |
  | D   | |z_score|                        | NOT applied  | Phase 4 v0.2 equivalent      |

  D is the Phase 4 baseline; A is the treatment; B and C are the
  disaggregation arms that isolate the contribution of each fix.

Metrics:
  - Per-event-category AUC (treat anomaly_score as predictor; binary
    y_post_cutoff as label).
  - Bootstrap 95% CI on AUC per event_category (1000 resamples,
    bias-corrected percentile).
  - Stratified AUC: cells where n_indicators_used ≥ 10 vs < 10 (the
    "data-sufficient" stratum vs the "thin-coverage" stratum).
  - Per-event-category ECE (Expected Calibration Error) + reliability
    diagram. v3 had a single cross-category ECE; v4 adds per-category.
  - Cross-cell ECE retained for backward compatibility.

Decision (v4 — applies to whichever arm is active):
  - mean_auc > 0.55 = the weights carry SOME signal (better than random)
  - mean_auc > 0.65 = useful for ranking
  - ECE < 0.10 = well-calibrated
  - Arm-A-vs-Arm-D delta > 0.03 = signed-scoring + filter together
    produce meaningful AUC improvement (the Miriam <0.03 swing rule
    from DECISION v2)

Inputs (all local / cached, no Athena $ beyond a small panel pull):
  - qgi-data/reference/weight-matrix.json (Phase 3 output)
  - qgi-data/reference/indicator-directions.json (v4 NEW — per-indicator
    direction-of-effect annotations, +1/-1/0; see
    docs/specs/internal/ops/cascade-track/catalog-direction-annotation-cascade-side.md
    + docs/specs/internal/ops/ml-track/catalog-direction-annotation-ml-side.md
    for the source-of-truth working drafts. The JSON is built by a
    separate generator that consumes the two working drafts.)

    ⚠️ Arms A and B HARD-ERROR if this file is missing — they are not
    meaningfully runnable without per-indicator direction annotations.
    Until the generator ships, only arms C and D are operational.

  - qgi-data/reference/indicator-allow-list.json (#591 Option D; used
    when --ablation-arm in {A, C})

    ⚠️ Arms A and C HARD-ERROR if this file is missing. Generate it via
    `python qgi-ml/scripts/generate_indicator_allow_list.py --bucket ...`
    before running A/C.
  - qgi-data/events/taxonomy_hierarchy.json
  - docs/specs/methodology/indicator-catalog-detailed.md
  - indicator_map.csv (cached from S3)
  - qgi_data.indicators (Athena, ~$0.01)
  - qgi_data.events (Athena, ~$0.001)
  - qgi_data.countries (Athena, trivial)

Output:
  - qgi-data/reference/phase4-validation-arm{A,B,C,D}.json
    (one file per arm; legacy `phase4-validation.json` is the alias
    for the D-arm output for backward compatibility with v3 consumers)
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score


def _derive_category_seed(master_seed: int, event_category: str) -> int:
    """Deterministic per-category seed for bootstrap CIs.

    Python's built-in `hash()` is randomized across processes by default
    (PYTHONHASHSEED) — using it would mean bootstrap CIs drift between
    re-runs even with a fixed `--bootstrap-seed`. SHA-256 over a stable
    string encoding gives the same 4-byte int every time, cross-process.

    Strict review 2026-05-11 M1: replaces an earlier `hash((seed, str(ec)))`
    construction with a deterministic equivalent.
    """
    key = f"{master_seed}:{event_category}".encode("utf-8")
    digest = hashlib.sha256(key).digest()[:4]
    return int.from_bytes(digest, byteorder="big", signed=False)


# Sibling-imports for data loaders. Same pattern bake_weight_matrix.py
# uses. Both modules are pure-Python; their imports are side-effect-free
# (boto3 clients are created lazily inside the loader functions, not at
# module load time).
_AUDITION = Path(__file__).resolve().parent / "audition_indicators.py"
_spec_a = importlib.util.spec_from_file_location("audition_indicators", _AUDITION)
au = importlib.util.module_from_spec(_spec_a)
sys.modules["audition_indicators"] = au
_spec_a.loader.exec_module(au)

_EB = Path(__file__).resolve().parent / "estimate_eb_hyperpriors.py"
_spec_eb = importlib.util.spec_from_file_location("eb_hyperpriors", _EB)
eb = importlib.util.module_from_spec(_spec_eb)
sys.modules["eb_hyperpriors"] = eb
_spec_eb.loader.exec_module(eb)


ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data-tools" if (ROOT / "data-tools").is_dir() else ROOT / "qgi-data"
WEIGHT_MATRIX_JSON = DATA_DIR / "reference" / "weight-matrix.json"
DIRECTIONS_JSON = DATA_DIR / "reference" / "indicator-directions.json"
ALLOW_LIST_JSON = DATA_DIR / "reference" / "indicator-allow-list.json"
ANCHOR_BATTERY_JSON = DATA_DIR / "reference" / "cascade-anchor-case-battery.json"
# v6 NEW (T7 §4 + §5 binding):
CANONICAL_LENGTH_CONFIG_JSON_DEFAULT = DATA_DIR / "reference" / "v0.2-canonical-length.json"
EXCLUSION_LIST_CONFIG_JSON_DEFAULT = DATA_DIR / "reference" / "v0.2-demeaning-insufficient-exclusion.json"
V0_2_FALSIFICATION_CONFIG_JSON = DATA_DIR / "reference" / "v0.2-falsification-config.json"
OUTPUT_JSON_LEGACY = DATA_DIR / "reference" / "phase4-validation.json"
OUTPUT_JSON_TEMPLATE = "phase4-validation-arm{arm}.json"

# Schema version. v6 = T12 #692 — Phase 5 v0.2 Path B input substrate:
#   - optional `per_cell` block (under --emit-per-cell flag) carrying the
#     per-(country_id, event_category) anomaly_score tensor that Path B's
#     partial-pooling evaluator (validate_weight_matrix_bayes.py) consumes.
#     Per docs-specs `ca77505` §3.1 (post-6-seat-Majles amendment 2026-05-15):
#     response variable is anomaly_score, not AUC (AUC undefined at
#     single-observation granularity).
#   - Backward-compatible additive: every v5 field preserved verbatim;
#     `per_cell` is omitted (or None) when --emit-per-cell is not set.
#
# v5 = T8 (#672) — Phase 5 v0.2 Path A:
#   - rule v2 verdict (INERT / HARD-FALSIFY / SOFT-FALSIFY / PARTIAL / PASS)
#     emitted as the top-level `decision` field, replacing the v4 legacy
#     PROCEED / PROCEED_WITH_CAUTION / REVISIT / INSUFFICIENT_DATA scheme
#   - multi-seed random baseline (5 seeds per Roshani A3 + Kwame bright-line)
#   - posterior-update protocol block emitted alongside the verdict
#   - canonical_length config + demeaning-insufficient exclusion-list
#     consumption (T7 phase doc §4 + §5 binding)
#   - pre-CIPS-validation label (T7 §9 / charter A8)
#
# v2 = baselines added (#598); v3 was an internal-only iteration that
# never shipped; v4 = the v0.1a release; v5 = T8 / #672; v6 = THIS (T12 #692).
SCHEMA_VERSION = 6

# Default cutoff: 2014. Choice rationale: gives 11 years (2015-2025) of
# post-cutoff observation window for ground-truth events. Earlier cutoffs
# would extend the window but have sparser indicator coverage.
DEFAULT_CUTOFF_YEAR = 2014
DEFAULT_END_YEAR = 2025

# Z-score window: take the most recent N years before cutoff to compute
# country-level indicator stats (mean, std). 5 years balances recency
# with stability against single-year shocks.
ZSCORE_WINDOW_YEARS = 5

# ECE binning: 10 equal-width bins on [0, 1] after min-max scaling.
N_ECE_BINS = 10

# Default seed for the random-weight baseline (#598). Fixed so re-runs
# of the same validation report reproduce identical baseline AUCs.
DEFAULT_BASELINE_SEED = 42

# v6 NEW (T8 / #672 — Roshani A3 + Kwame bright-line). The single-seed
# baseline of v4/v5 is replaced with a 5-seed sweep so the random-
# baseline delta carries a CI rather than a point estimate. The 5 seeds
# are fixed for reproducibility per Protocol 5; do not reseed without
# convening Roshani + Kwame.
DEFAULT_BASELINE_SEEDS = (17, 42, 123, 271, 314)

# v6 NEW (T7 §1 / spec §1 / charter A2). Rule v2 stratum threshold +
# cardinality precondition. NON-AMENDABLE — bound to the pre-reg spec
# at docs-specs `a2f5db4`. The v6 evaluator reads these from the JSON
# config when present (V0_2_FALSIFICATION_CONFIG_JSON above); the
# constants here are fallback defaults matching the spec verbatim.
RULE_V2_STRATUM_THRESHOLD = 10
RULE_V2_CARDINALITY_FLOOR_N = 30
RULE_V2_FALSIFY_BELOW_SWING = 0.03
RULE_V2_INERT_TRIGGER_BYTE_IDENTICAL = "all_4_arms_byte_identical"
RULE_V2_INERT_TRIGGER_CARDINALITY = "stratum_cardinality_below_N"
RULE_V2_INERT_TRIGGER_BOOTSTRAP = "bootstrap_nonconvergence_above_10pct_categories"

# v6 NEW (T7 §3 / Roshani A3). Bayesian posterior-update protocol.
# Prior is the post-v0.1a anchor (0.30 ± 0.05); material-update
# threshold is ≥ 0.15 movement in either direction. Verbatim from
# pre-reg spec §3 and JSON config (V0_2_FALSIFICATION_CONFIG_JSON).
POSTERIOR_PRIOR_MEAN = 0.30
POSTERIOR_PRIOR_UNCERTAINTY = 0.05
POSTERIOR_MATERIAL_UPDATE_THRESHOLD = 0.15

# v6 NEW (T7 §8 / spec §5 / charter A9). 4-tier exit-criterion table.
# Tier conditions match the table verbatim; the verdict-computation
# helper reads them in the order HARD-FALSIFY → PASS → PARTIAL →
# SOFT-FALSIFY (longest match wins; matches the actual code path in
# compute_rule_v2_verdict), with INERT pre-checked.
TIER_HARD_FALSIFY_MEAN_AUC_BELOW = 0.50
TIER_HARD_FALSIFY_CI_LOWER_BELOW = 0.48
TIER_HARD_FALSIFY_ANCHOR_BELOW = 4  # out of 8 evaluable
TIER_SOFT_FALSIFY_SWING_BELOW = 0.03
TIER_PARTIAL_SWING_RANGE = (0.02, 0.05)
TIER_PARTIAL_MEAN_AUC_RANGE = (0.50, 0.55)
TIER_PASS_SWING_AT_LEAST = 0.05
TIER_PASS_MEAN_AUC_AT_LEAST = 0.55
TIER_PASS_ANCHOR_AT_LEAST = 6  # out of 8 evaluable

# v6 NEW (T7 §9 / charter A8). pre-CIPS-validation label, non-strippable
# until 2026-06-04. Every per-arm JSON carries this label.
PRE_CIPS_VALIDATION_LABEL_UNTIL = "2026-06-04"


# v6 NEW (#679 root-cause fix): replace NaN with None so the emitted JSON
# is RFC 8259 compliant (jq + JS JSON.parse accept it). Python's permissive
# json.dumps allows allow_nan=True which emits the bare token `NaN`,
# rejected by strict parsers. Used in main()'s output write path.

def _nan_to_none(o):
    """Recursively replace NaN floats with None for RFC 8259 compliance.
    Idempotent on values that are already JSON-safe."""
    import math
    if isinstance(o, float) and math.isnan(o):
        return None
    if isinstance(o, list):
        return [_nan_to_none(x) for x in o]
    if isinstance(o, dict):
        return {k: _nan_to_none(v) for k, v in o.items()}
    return o

# Bootstrap parameters for per-category AUC CIs (v4 NEW).
# 1000 resamples gives stable percentile-CI estimates without making
# the validation run prohibitively expensive (~109 categories × 1000 ≈
# 109k roc_auc_score calls — under a minute on a modern machine).
DEFAULT_BOOTSTRAP_RESAMPLES = 1000
DEFAULT_BOOTSTRAP_SEED = 42
BOOTSTRAP_CI_ALPHA = 0.05  # 95% CI = [2.5th, 97.5th] percentile

# Stratified-AUC split threshold (v4 NEW). Cells with n_indicators_used
# >= 10 are "data-sufficient"; < 10 is "thin-coverage". The split
# isolates whether the weight-matrix signal is concentrated in
# well-covered categories (Miriam's RECONVENE concern).
STRATA_INDICATOR_COUNT_THRESHOLD = 10

# Valid ablation arms (Phase 5 v0.1a).
ABLATION_ARMS = ("A", "B", "C", "D")
DEFAULT_ABLATION_ARM = "D"  # default = Phase 4 v0.2 baseline behavior

# Per-arm config: (use_signed_scoring, apply_591_filter)
ARM_CONFIG = {
    "A": (True, True),   # signed × filter — treatment
    "B": (True, False),  # signed × NO filter
    "C": (False, True),  # unsigned × filter
    "D": (False, False), # unsigned × NO filter — baseline
}


# ---------------------------------------------------------------------------
# Load the weight matrix
# ---------------------------------------------------------------------------

def load_weight_matrix() -> pd.DataFrame:
    """Returns a DataFrame with columns:
    indicator_numeric_id, indicator_catalog_id, event_category, sector,
    L1, weight, used_fallback.
    """
    d = json.loads(WEIGHT_MATRIX_JSON.read_text(encoding="utf-8"))
    df = pd.DataFrame(d["weights"])
    print(f"  weight-matrix: {len(df)} rows ({d['n_full_eb_prior']} full EB, "
          f"{sum(df['used_fallback'])} fallback)")
    return df


def load_direction_annotations(path: Path = DIRECTIONS_JSON) -> dict[str, int]:
    """Read indicator-directions.json (v4 NEW) and return {api_code: direction}.

    Schema:
      {"schema_version": N,
       "generated": "...",
       "directions": [{"api_code": "...", "direction": +1|-1|0,
                       "tag": "[lit-only]|...", "justification": "..."}, ...]}

    Returns: dict mapping api_code -> int in {-1, 0, +1}. Unknown codes
    are treated as direction 0 (no signal) by the scoring function; this
    loader does NOT pre-populate unknowns — that's the caller's job.

    If the file doesn't exist, returns an empty dict and the caller's
    score function will treat all indicators as direction 0. This makes
    the script runnable even before the directions JSON has been built
    (useful for the D-arm baseline which doesn't need directions).
    """
    if not path.exists():
        print(f"  [WARN] {path.name} not found — direction annotations skipped "
              f"(all indicators treated as direction 0). Arms A and B will be "
              f"equivalent to the D-arm in this run; use --ablation-arm D "
              f"explicitly to suppress this warning.")
        return {}
    d = json.loads(path.read_text(encoding="utf-8"))
    out = {row["api_code"]: int(row["direction"]) for row in d.get("directions", [])}
    nz = sum(1 for v in out.values() if v != 0)
    print(f"  indicator-directions: {len(out)} annotations "
          f"({nz} non-zero signs, {len(out) - nz} direction:0)")
    return out


def load_allow_list(path: Path = ALLOW_LIST_JSON) -> set[int]:
    """Read indicator-allow-list.json (#591 Option D) and return the set
    of allowed indicator_numeric_id values. Used when --ablation-arm in
    {A, C} to restrict the weight matrix to the curated indicator set.

    If the file doesn't exist, returns None (sentinel for "no filter
    available"). The caller decides whether that's an error (in filter
    mode) or fine (in non-filter mode).
    """
    if not path.exists():
        print(f"  [WARN] {path.name} not found — #591 filter unavailable. "
              f"Arms A and C will fall back to unfiltered behavior in this run.")
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    ids = set(int(x) for x in d.get("allow_list_numeric_ids", []))
    print(f"  indicator-allow-list (#591): {len(ids)} numeric IDs in filter")
    return ids


# ---------------------------------------------------------------------------
# v6 NEW (T8 / #672): T7 phase doc config loaders.
# These read the JSON contracts T7 §4 + §5 require to be in git before T9
# fires. Hard-error when missing IF rule v2 is being evaluated; pass
# through silently when ablation_arm == "D" + with_baselines=False (the
# legacy v4/v5 D-arm sanity-check use case).
# ---------------------------------------------------------------------------


def load_canonical_length_config(path: Path = CANONICAL_LENGTH_CONFIG_JSON_DEFAULT,
                                  *, required: bool = False) -> dict | None:
    """Load `qgi-data/reference/v0.2-canonical-length.json` (T7 §4 binding).

    Per T7 §4 + spec §8.2, this JSON encodes per-indicator canonical_length
    computed on the TRANSFORMED series (first_diff for I(1), log_diff for
    SP.POP.TOTL, pass_through for I(0) and NY.GDP.MKTP.KD.ZG). The v6
    evaluator MUST read from this file rather than recomputing from the
    raw panel — recomputation would silently mean a different statistical
    object than what v0.2 ratified.

    `required=True` is set by main() when ablation_arm is non-D OR
    with_baselines=True (i.e. whenever rule v2 is being evaluated).
    `required=False` preserves the v4/v5 D-arm sanity-check path.
    """
    if not path.exists():
        if required:
            raise FileNotFoundError(
                f"v6 evaluator requires {path} (T7 §4 binding). "
                f"This file is computed by T8's canonical-length re-derivation "
                f"step BEFORE T9 (Stage α) fires. Re-derive on the transformed "
                f"series (first_diff for I(1), log_diff for SP.POP.TOTL, "
                f"pass_through for I(0) and NY.GDP.MKTP.KD.ZG) and commit to "
                f"qgi-data; do NOT fall back to a raw-panel computation."
            )
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_exclusion_list_config(path: Path = EXCLUSION_LIST_CONFIG_JSON_DEFAULT,
                                *, required: bool = False) -> set[str] | None:
    """Load `qgi-data/reference/v0.2-demeaning-insufficient-exclusion.json`
    (T7 §5 (b) binding).

    Per T7 §5 decision (b), the 4 demeaning-insufficient Class A indicators
    (FP.CPI.TOTL.ZG, NY.GDP.PCAP.CD, SH.DYN.MORT, SP.POP.TOTL) are excluded
    from the headline AUC stratum so the rule v2 swing gate is a clean test
    on the 105 non-demeaning-insufficient indicators in the Stage F panel.

    Returns the set of excluded indicator id_strings (NOT numeric IDs;
    matched at the api_code/id_string layer because the catalog uses
    id_strings as canonical keys).
    """
    if not path.exists():
        if required:
            raise FileNotFoundError(
                f"v6 evaluator requires {path} (T7 §5 binding). "
                f"This file encodes the 4-Class-A demeaning-insufficient "
                f"exclusion list ratified in T7 §5 decision (b). Generate it "
                f"with the 4 verbatim indicator IDs (FP.CPI.TOTL.ZG, "
                f"NY.GDP.PCAP.CD, SH.DYN.MORT, SP.POP.TOTL) and Stage E "
                f"pairwise scores (0.66/0.54/0.36/0.31) — see T7 §5 inline."
            )
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    ids = {ind["id"] for ind in d.get("indicators", [])}
    print(f"  exclusion-list (T7 §5 (b)): {len(ids)} demeaning-insufficient indicators excluded")
    return ids


def load_v0_2_falsification_config(
    path: Path = V0_2_FALSIFICATION_CONFIG_JSON,
    *, required: bool = False,
) -> dict | None:
    """Load `qgi-data/reference/v0.2-falsification-config.json` (T3 pre-reg
    JSON config) for the rule v2 thresholds + posterior protocol priors.

    When this file is present, the v6 evaluator reads RULE_V2_* and
    POSTERIOR_* values from it (over-ride of the module-level constants).
    This is the source-of-truth contract per T7 §1; the module constants
    above are fallback defaults for tests / out-of-tree runs.
    """
    if not path.exists():
        if required:
            raise FileNotFoundError(
                f"v6 evaluator requires {path} (T3 pre-reg JSON config). "
                f"This is the machine-readable source-of-truth for rule v2 "
                f"thresholds, N=30 floor, INERT triggers, and posterior "
                f"protocol priors. Commit it (qgi-data PR #43 + #44) before "
                f"any v6 evaluation can fire under rule v2."
            )
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# v6 NEW (T8 / #672): rule v2 verdict + posterior-update protocol.
# ---------------------------------------------------------------------------


def compute_rule_v2_verdict(
    *,
    stratum_n_cells: int,
    stratum_mean_auc: float,
    stratum_ci_lower: float | None,
    a_minus_d_swing: float | None,
    anchor_pass_evaluable: int | None,
    anchor_evaluable_total: int | None,
    inert_triggers: list[str] | None = None,
    cardinality_floor_N: int = RULE_V2_CARDINALITY_FLOOR_N,
    # v6 review fix (MINOR #2): T11 aggregator owns the multi-seed
    # random-baseline-delta-negative signal + the anchor-battery-mixed
    # signal. Per-arm script passes None for both; aggregator computes
    # them across arms and calls this helper with the full set. When
    # None, the verdict applies the 2-of-3 condition fallback documented
    # in the per-tier branches below.
    random_baseline_delta_negative_at_multi_seed: bool | None = None,
    anchor_battery_is_mixed: bool | None = None,
) -> dict:
    """v6 NEW (T8 / #672). Compute the rule v2 verdict per pre-reg spec §1 +
    4-tier exit table §5 (charter A4 + A9). Returns:
      {
        "decision": "INERT" | "HARD-FALSIFY" | "SOFT-FALSIFY" | "PARTIAL" | "PASS",
        "rationale": str,
        "inert_reason": str | None,
        "tier_conditions_evaluated": dict,
      }

    Order of evaluation (per-arm context — final cross-arm verdict
    belongs to T11 aggregator):
      1. INERT pre-check — cardinality floor, byte-identical arms, bootstrap
         non-convergence (caller passes any/all triggers in `inert_triggers`).
      2. If not INERT: classify into HARD-FALSIFY / PASS / PARTIAL /
         SOFT-FALSIFY using the 4-tier conditions table from spec §5.

    Cross-arm conditions per spec §5 (passed by T11 aggregator only):
      - `random_baseline_delta_negative_at_multi_seed`: SOFT-FALSIFY's 3rd
        condition. When None, this helper applies the 2-of-3 fallback
        (swing < 0.03 + cardinality ≥ N) and marks the verdict with a
        `requires_t11_confirmation` flag.
      - `anchor_battery_is_mixed`: PARTIAL's 3rd condition. When None,
        the helper applies the 2-of-3 fallback (swing in range + mean AUC
        in range).

    Inputs are the registered stratum's evaluable AUC + CI + swing + anchor
    battery results. Caller is responsible for computing them on the
    `n_indicators_used >= 10` stratum AFTER applying T7 §5 (b) exclusion of
    the 4 demeaning-insufficient indicators.

    Raises ValueError if any input is structurally invalid (e.g. anchor
    pass count > evaluable total). Defaults to INERT on missing/None inputs
    rather than silently classifying — Protocol 5 demands the verdict be
    INERT when the test cannot execute, not an arbitrary tier.
    """
    inert_triggers = inert_triggers or []

    # ---- INERT pre-checks ----
    if stratum_n_cells < cardinality_floor_N:
        inert_triggers = list(inert_triggers) + [RULE_V2_INERT_TRIGGER_CARDINALITY]

    if inert_triggers:
        return {
            "decision": "INERT",
            "rationale": (
                f"Rule v2 returns INERT under triggers: {inert_triggers}. "
                f"Stratum n_cells={stratum_n_cells} vs N_floor={cardinality_floor_N}. "
                f"INERT is NOT a methodology halt; cascade does not "
                f"re-deliberate methodology on an INERT result; cascade "
                f"fixes the instrumentation and re-runs (spec §4)."
            ),
            "inert_reason": "; ".join(inert_triggers),
            "tier_conditions_evaluated": None,
        }

    # ---- Inputs must be non-None to evaluate tiers ----
    if (stratum_mean_auc is None or not np.isfinite(stratum_mean_auc)
            or a_minus_d_swing is None or not np.isfinite(a_minus_d_swing)):
        return {
            "decision": "INERT",
            "rationale": (
                "Rule v2 returns INERT — stratum mean_auc or A-D swing is "
                "NaN/None, which means the test did not produce a usable "
                "statistic on the registered stratum. Treat as data-readiness "
                "halt per spec §4."
            ),
            "inert_reason": "stratum_statistic_undefined",
            "tier_conditions_evaluated": None,
        }

    # ---- Anchor battery sanity ----
    anchor_pass = anchor_pass_evaluable if anchor_pass_evaluable is not None else 0
    anchor_total = anchor_evaluable_total if anchor_evaluable_total is not None else 8
    if anchor_total > 0 and anchor_pass > anchor_total:
        raise ValueError(
            f"anchor_pass_evaluable ({anchor_pass}) > anchor_evaluable_total "
            f"({anchor_total}) — invalid input"
        )

    # ---- 4-tier evaluation (spec §5) ----
    # CI lower defaults to mean_auc when not provided (conservative; treats
    # missing CI as if the point estimate IS the lower bound, which can only
    # delay HARD-FALSIFY, never trigger it spuriously).
    ci_lower = stratum_ci_lower if stratum_ci_lower is not None else stratum_mean_auc

    conditions = {
        "stratum_n_cells": int(stratum_n_cells),
        "stratum_mean_auc": float(stratum_mean_auc),
        "stratum_ci_lower": float(ci_lower),
        "a_minus_d_swing": float(a_minus_d_swing),
        "anchor_pass_evaluable": int(anchor_pass),
        "anchor_evaluable_total": int(anchor_total),
    }

    # HARD-FALSIFY: mean AUC < 0.50 AND CI lower < 0.48 AND anchors < 4/8
    if (stratum_mean_auc < TIER_HARD_FALSIFY_MEAN_AUC_BELOW
            and ci_lower < TIER_HARD_FALSIFY_CI_LOWER_BELOW
            and anchor_pass < TIER_HARD_FALSIFY_ANCHOR_BELOW):
        return {
            "decision": "HARD-FALSIFY",
            "rationale": (
                f"All 3 HARD-FALSIFY conditions fire: "
                f"mean_auc {stratum_mean_auc:.4f} < {TIER_HARD_FALSIFY_MEAN_AUC_BELOW} "
                f"AND CI_lower {ci_lower:.4f} < {TIER_HARD_FALSIFY_CI_LOWER_BELOW} "
                f"AND anchor_pass {anchor_pass}/8 < {TIER_HARD_FALSIFY_ANCHOR_BELOW}. "
                f"Cascade methodology direction closes permanently per spec §5 "
                f"+ T5 DECISION §5. NO v0.3 path on Path A."
            ),
            "inert_reason": None,
            "tier_conditions_evaluated": conditions,
        }

    # PASS: swing ≥ 0.05 AND mean AUC ≥ 0.55 AND anchors ≥ 6/8
    if (a_minus_d_swing >= TIER_PASS_SWING_AT_LEAST
            and stratum_mean_auc >= TIER_PASS_MEAN_AUC_AT_LEAST
            and anchor_pass >= TIER_PASS_ANCHOR_AT_LEAST):
        return {
            "decision": "PASS",
            "rationale": (
                f"All 3 PASS conditions fire: "
                f"swing {a_minus_d_swing:.4f} >= {TIER_PASS_SWING_AT_LEAST} "
                f"AND mean_auc {stratum_mean_auc:.4f} >= {TIER_PASS_MEAN_AUC_AT_LEAST} "
                f"AND anchor_pass {anchor_pass}/8 >= {TIER_PASS_ANCHOR_AT_LEAST}. "
                f"Methodology vindicated; Phase 6 (T13) begins on the now-"
                f"validated EB framework."
            ),
            "inert_reason": None,
            "tier_conditions_evaluated": conditions,
        }

    # PARTIAL: swing in [0.02, 0.05] AND mean AUC in [0.50, 0.55] AND anchors mixed
    # (3rd condition `anchor_battery_is_mixed` is cross-arm; per-arm context
    # uses 2-of-3 fallback when None per spec §5 review fix MINOR #2.)
    swing_in_partial = (
        TIER_PARTIAL_SWING_RANGE[0] <= a_minus_d_swing < TIER_PARTIAL_SWING_RANGE[1]
    )
    auc_in_partial = (
        TIER_PARTIAL_MEAN_AUC_RANGE[0] <= stratum_mean_auc < TIER_PARTIAL_MEAN_AUC_RANGE[1]
    )
    if swing_in_partial and auc_in_partial:
        # 3rd condition check: anchor_battery_is_mixed (T11 aggregator-supplied)
        third_condition_met = (
            anchor_battery_is_mixed if anchor_battery_is_mixed is not None
            else True  # 2-of-3 fallback when caller hasn't supplied it
        )
        requires_t11 = anchor_battery_is_mixed is None
        if third_condition_met:
            return {
                "decision": "PARTIAL",
                "rationale": (
                    f"PARTIAL conditions: swing {a_minus_d_swing:.4f} in "
                    f"{TIER_PARTIAL_SWING_RANGE} AND mean_auc "
                    f"{stratum_mean_auc:.4f} in {TIER_PARTIAL_MEAN_AUC_RANGE}"
                    + (" AND anchor_battery_is_mixed=True"
                       if anchor_battery_is_mixed is True else "")
                    + (" (2-of-3 fallback — T11 aggregator must confirm "
                       "the anchor-battery-mixed 3rd condition before "
                       "the verdict is binding)" if requires_t11 else "")
                    + ". Methodology has weaknesses; Path B (T12) becomes "
                    "next phase, not v0.3 of the same Path A design."
                ),
                "inert_reason": None,
                "tier_conditions_evaluated": conditions,
                "requires_t11_confirmation": requires_t11,
            }

    # SOFT-FALSIFY: swing < 0.03 AND stratum has >= N cells AND
    # random-baseline delta still negative at multi-seed bootstrap.
    # (3rd condition `random_baseline_delta_negative_at_multi_seed` is cross-arm.)
    if a_minus_d_swing < TIER_SOFT_FALSIFY_SWING_BELOW:
        third_condition_met = (
            random_baseline_delta_negative_at_multi_seed
            if random_baseline_delta_negative_at_multi_seed is not None
            else True  # 2-of-3 fallback per spec §5 review fix MINOR #2
        )
        requires_t11 = random_baseline_delta_negative_at_multi_seed is None
        if third_condition_met:
            return {
                "decision": "SOFT-FALSIFY",
                "rationale": (
                    f"SOFT-FALSIFY: swing {a_minus_d_swing:.4f} < "
                    f"{TIER_SOFT_FALSIFY_SWING_BELOW} on a non-INERT stratum "
                    f"(n_cells={stratum_n_cells} >= N={cardinality_floor_N})"
                    + (" AND random_baseline_delta_negative_at_multi_seed=True"
                       if random_baseline_delta_negative_at_multi_seed is True
                       else "")
                    + (" (2-of-3 fallback — T11 aggregator must confirm the "
                       "random-baseline-negative 3rd condition across the "
                       "multi-seed sweep before the verdict is binding)"
                       if requires_t11 else "")
                    + ". Default next phase: Path B (T12). NO v0.3 on Path A."
                ),
                "inert_reason": None,
                "tier_conditions_evaluated": conditions,
                "requires_t11_confirmation": requires_t11,
            }

    # Fallthrough — should be rare. Return PARTIAL as the most-conservative
    # "neither HARD-FALSIFY nor PASS" verdict.
    return {
        "decision": "PARTIAL",
        "rationale": (
            f"PARTIAL (fallthrough): swing {a_minus_d_swing:.4f} and "
            f"mean_auc {stratum_mean_auc:.4f} fall outside the cleanly-"
            f"defined HARD-FALSIFY / SOFT-FALSIFY / PASS regions. Treat as "
            f"PARTIAL per the most-conservative reading of spec §5."
        ),
        "inert_reason": None,
        "tier_conditions_evaluated": conditions,
    }


def compute_posterior_update(
    *,
    rule_v2_decision: str,
    a_minus_d_swing: float | None,
    prior_mean: float = POSTERIOR_PRIOR_MEAN,
    prior_uncertainty: float = POSTERIOR_PRIOR_UNCERTAINTY,
    material_update_threshold: float = POSTERIOR_MATERIAL_UPDATE_THRESHOLD,
) -> dict:
    """v6 NEW (T8 / #672). Compute the Bayesian posterior update per
    Roshani A3 (spec §3 + JSON config). Returns:
      {
        "prior_mean": float,
        "prior_uncertainty": float,
        "posterior_mean": float,
        "posterior_movement": float,
        "material_update_threshold": float,
        "is_material": bool,
        "rationale": str,
      }

    Update logic (heuristic; the protocol does NOT specify a likelihood
    function, only the material-update threshold and direction):
      - INERT verdict → posterior == prior (no update; the test did not
        execute on its intended target)
      - HARD-FALSIFY → posterior moves DOWN by ≥ 0.15 (material; clamp to
        [0, 1])
      - SOFT-FALSIFY → posterior moves down by 0.08 (immaterial, signals
        weakening evidence without falsifying the methodology)
      - PARTIAL → posterior moves up by 0.05 (immaterial; partial signal)
      - PASS → posterior moves UP by ≥ 0.15 (material; clamp)

    The spec-anchored quantities are:
      - 0.15 IS the material-update threshold (verbatim from spec §3 /
        Roshani A3 protocol);
      - direction of each verdict's update (HARD-FALSIFY downward,
        PASS upward, etc.) follows directly from the spec.

    The exact per-verdict magnitudes (-0.20, +0.20, +0.05, -0.08) are
    AUTHOR-CHOSEN heuristics satisfying the spec constraints, NOT
    verbatim spec values. They were chosen so HARD-FALSIFY and PASS
    just clear the 0.15 material threshold (with -0.05 margin for
    posterior clamping headroom), and PARTIAL/SOFT-FALSIFY produce
    sub-material nudges that document directional change without
    claiming falsification has fired. T11's aggregator may override
    these per-verdict magnitudes if the v0.2 falsification report's
    Bayesian section warrants more sophisticated update logic.
    """
    update_map = {
        "INERT":         (0.00, "no update; test did not execute on its intended target"),
        "HARD-FALSIFY":  (-0.20, "material downward update (methodology fails)"),
        "SOFT-FALSIFY":  (-0.08, "sub-material downward nudge (weakening evidence)"),
        "PARTIAL":       (+0.05, "sub-material upward nudge (partial signal)"),
        "PASS":          (+0.20, "material upward update (methodology vindicated)"),
    }
    delta, descr = update_map.get(rule_v2_decision, (0.00, "unknown verdict; no update"))
    posterior = max(0.0, min(1.0, prior_mean + delta))
    movement = posterior - prior_mean
    is_material = abs(movement) >= material_update_threshold

    return {
        "prior_mean": float(prior_mean),
        "prior_uncertainty": float(prior_uncertainty),
        "posterior_mean": float(posterior),
        "posterior_movement": float(movement),
        "material_update_threshold": float(material_update_threshold),
        "is_material": bool(is_material),
        "rationale": (
            f"Prior {prior_mean:.2f} ± {prior_uncertainty:.2f} (post-v0.1a anchor). "
            f"Rule v2 verdict: {rule_v2_decision}. {descr}. "
            f"Posterior {posterior:.2f}; movement {movement:+.2f} vs "
            f"threshold {material_update_threshold:.2f} → "
            f"{'MATERIAL' if is_material else 'IMMATERIAL'}."
        ),
    }


# ---------------------------------------------------------------------------
# v5 + v6: existing helper kept for backward-compat (v4 D-arm sanity check)
# ---------------------------------------------------------------------------


def apply_591_filter(weights_df: pd.DataFrame, allow_ids: set[int]) -> pd.DataFrame:
    """Restrict the weight matrix to indicators in the #591 allow list.

    Used by arms A and C. If allow_ids is None (allow-list file missing),
    returns the input unchanged with a warning — the caller's --ablation-arm
    choice may be silently mis-specified in that case.
    """
    if allow_ids is None:
        print("  [WARN] #591 filter requested but allow_ids is None — "
              "falling back to unfiltered weight matrix")
        return weights_df
    n_before = len(weights_df)
    out = weights_df[weights_df["indicator_numeric_id"].isin(allow_ids)].copy()
    n_after = len(out)
    print(f"  #591 filter: {n_before} → {n_after} rows "
          f"({n_before - n_after} dropped, {100 * n_after / n_before:.1f}% retained)")
    return out


def build_uniform_baseline(weights_df: pd.DataFrame) -> pd.DataFrame:
    """Replace every row's weight with 1.0, keeping the same (event_category,
    indicator_numeric_id) coverage.

    Tests the scoring formula in isolation. If uniform_AUC ≈ treatment_AUC,
    the |z_score| × weight formula is doing all the work and the EB priors
    contribute nothing. If uniform_AUC < treatment_AUC, the priors carry
    real signal. Filed as #598.
    """
    out = weights_df.copy()
    out["weight"] = 1.0
    return out


def build_random_baseline(weights_df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Replace every row's weight with a uniform random sample from [0, 1].

    Tests against pure noise. Random_AUC near 0.5 (and treatment_AUC also
    near 0.5) is the worst-case signal — the methodology produces no
    discrimination above chance.

    Seed is fixed (default 42) so re-runs reproduce identical baseline
    AUCs. Caller can override via --baseline-seed.
    """
    rng = np.random.default_rng(seed)
    out = weights_df.copy()
    out["weight"] = rng.uniform(0.0, 1.0, size=len(out))
    return out


def _build_per_cell_block(scored: pd.DataFrame) -> dict:
    """v6 NEW (T12 #692 / Path B input substrate).

    Emit the per-(country_id, event_category) anomaly_score tensor as a
    JSON-serialisable block. The Path B partial-pooling evaluator
    (`validate_weight_matrix_bayes.py`) consumes this via the
    `prep_cells_from_arm_jsons` helper and pivots to
    (n_arms, n_countries, n_categories) shape.

    Schema:
      {
        "schema_version": 1,
        "n_cells": <int>,
        "n_indicators_used_min": <int>,
        "n_indicators_used_max": <int>,
        "n_indicators_used_median": <float>,
        "cells": [
          {"country_id": <int>, "event_category": <str>,
           "anomaly_score": <float>, "n_indicators_used": <int>}, ...
        ]
      }

    Per spec `ca77505` §3.1 (post-6-seat-Majles amendment 2026-05-15): this
    is the per-cell `anomaly_score` (NOT AUC; AUC undefined at single-
    observation granularity). Cells are emitted directly from
    `score_country_event`'s aggregated DataFrame; no further transformation.
    """
    cells = []
    for _, row in scored.iterrows():
        cells.append({
            "country_id": int(row["country_id"]),
            "event_category": str(row["event_category"]),
            "anomaly_score": float(row["anomaly_score"]),
            "n_indicators_used": int(row["n_indicators_used"]),
        })
    n_used = scored["n_indicators_used"].values
    return {
        "schema_version": 1,
        "n_cells": int(len(scored)),
        "n_indicators_used_min": int(n_used.min()) if len(n_used) else 0,
        "n_indicators_used_max": int(n_used.max()) if len(n_used) else 0,
        "n_indicators_used_median": float(np.median(n_used)) if len(n_used) else float("nan"),
        "cells": cells,
    }


def evaluate_weights(
    weights_df: pd.DataFrame, zscores: pd.DataFrame,
    country_id_to_str: dict, num_to_api: dict, gt: pd.DataFrame,
    label: str,
    use_signed_scoring: bool = False,
    directions: dict[str, int] | None = None,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    anchor_battery: dict | None = None,
    strata_threshold: int = STRATA_INDICATOR_COUNT_THRESHOLD,
    emit_per_cell: bool = False,
) -> dict:
    """Run the full evaluation pipeline (score → per-category AUC + CI →
    stratified-by-coverage AUC → per-category ECE + reliability +
    cross-category ECE) on a weights DataFrame and return the summary
    dict.

    Used for both the regular weight matrix and the baseline (uniform /
    random) variants. The same scoring formula is used in all cases —
    only the weights differ — which means any AUC delta is attributable
    to the weights, not the formula.

    v4 NEW: use_signed_scoring + directions arguments propagate the
    ablation-arm decision through to score_country_event. Bootstrap CI
    and stratified AUC are computed unconditionally (cheap relative to
    the Athena pull that already happened).
    """
    print(f"\n[evaluate: {label}]")
    scored = score_country_event(
        weights_df, zscores, country_id_to_str, num_to_api,
        use_signed_scoring=use_signed_scoring, directions=directions,
    )
    # v4: per-category AUC now carries bootstrap CI inline.
    per_cat = compute_per_category_auc_with_ci(
        scored, gt,
        n_resamples=bootstrap_resamples, seed=bootstrap_seed,
    )
    aucs_real = [c["auc"] for c in per_cat if c["auc"] is not None]
    if aucs_real:
        mean_auc = float(np.mean(aucs_real))
        median_auc = float(np.median(aucs_real))
        n_above_0_55 = sum(1 for a in aucs_real if a > 0.55)
        n_above_0_65 = sum(1 for a in aucs_real if a > 0.65)
    else:
        mean_auc = median_auc = float("nan")
        n_above_0_55 = n_above_0_65 = 0
    # v4: stratified AUC by n_indicators_used.
    # v5 (T2 / #666): strata_threshold is configurable for the γ-stage
    # sensitivity sweep.
    stratified = compute_stratified_auc(scored, gt, strata_threshold=strata_threshold)
    # v5 (T2 / #666): per-threshold stratum sensitivity table at {3, 5, 7, 10, 15}.
    # Transparency artifact for the γ-stage Majles deliberation; not a decision
    # artifact (Miriam's N=30 hard floor is the gate).
    stratum_sensitivity = compute_stratum_sensitivity(scored, gt)
    # v4: per-category ECE.
    per_cat_ece = compute_per_category_ece(scored, gt)
    # Legacy v3 cross-category ECE retained for backward-compat consumers.
    ece, reliability = compute_ece_and_reliability(scored, gt)
    # v4 Step 3: anchor-case battery (regression suite, not validation).
    anchor_results = evaluate_anchor_cases(scored, anchor_battery)
    n_anchor_pass = sum(1 for r in anchor_results if r["passed"] is True)
    n_anchor_fail = sum(1 for r in anchor_results if r["passed"] is False)
    n_anchor_skip = sum(1 for r in anchor_results if r["passed"] is None)
    print(f"  {label}: mean_auc={mean_auc:.4f}  median_auc={median_auc:.4f}  "
          f"ece={ece:.4f}  n_categories_with_auc={len(aucs_real)}/{len(per_cat)}  "
          f"stratified[ds={stratified['data_sufficient']['mean_auc']:.4f}/tc="
          f"{stratified['thin_coverage']['mean_auc']:.4f}]  "
          f"anchors[pass={n_anchor_pass}/fail={n_anchor_fail}/skip={n_anchor_skip}]")
    return {
        "label": label,
        "n_event_categories": len(per_cat),
        "n_event_categories_with_auc": len(aucs_real),
        "n_predictions": len(scored),
        "mean_auc": mean_auc,
        "median_auc": median_auc,
        "n_auc_above_0_55": n_above_0_55,
        "n_auc_above_0_65": n_above_0_65,
        "ece": ece,
        "per_event_category_auc": per_cat,
        "reliability_diagram": reliability,
        # v4 NEW additions
        "stratified_auc": stratified,
        "per_event_category_ece": per_cat_ece,
        # v5 NEW (T2 / #666): γ-stage transparency artifact.
        "stratum_sensitivity": stratum_sensitivity,
        # v4 Step 3 anchor battery (None-tolerant — empty list if no battery loaded)
        "anchor_case_battery": {
            "n_pass": n_anchor_pass,
            "n_fail": n_anchor_fail,
            "n_skip": n_anchor_skip,
            "cases": anchor_results,
        },
        # v6 NEW (T12 #692 / Path B input substrate): per-cell anomaly_score
        # tensor for the partial-pooling model at qgi-ml/scripts/
        # validate_weight_matrix_bayes.py. Emitted as a list of records so
        # the JSON is human-readable and the downstream prep_cells_from_arm_jsons
        # helper can pivot to (n_arms, n_countries, n_categories) shape.
        # Spec: docs-specs `ca77505` §3.1 (post-6-seat amendment 2026-05-15).
        "per_cell": _build_per_cell_block(scored) if emit_per_cell else None,
    }


# ---------------------------------------------------------------------------
# v6.5 NEW (T8.5 / Tariq adjudication 2026-05-12):
#   apply_transform_layer — consume the canonical_length_config dispatch
#   table to transform the raw panel BEFORE z-scoring. Without this, the v6
#   evaluator runs against the v0.1a raw substrate even though T5 ratified
#   Path A on the Stage F transformed substrate (Protocol-5 breach against
#   charter A6). Tariq §5.2 implementation-grade scope.
# ---------------------------------------------------------------------------


def apply_transform_layer(panel: pd.DataFrame,
                           canonical_length_config: dict) -> pd.DataFrame:
    """Apply the v0.2 transform chain to the raw indicator panel.

    Per the v0.2-canonical-length.json dispatch table (T7 §4 + charter A6):
      - first_diff for I(1) / ambiguous / I(2)_or_higher indicators
      - log_diff for SP.POP.TOTL (OUTLIER_LOG_DIFFERENCE)
      - pass_through for I(0) + NY.GDP.MKTP.KD.ZG + the 2 T7 §6 surgical-
        override indicators (FP.CPI.TOTL.ZG, NY.GDP.PCAP.CD as I(0) on
        the demeaned substrate)
      - cross-section demean (subtract per-year cross-country mean) for
        Class A indicators (demean_applied=True in dispatch)

    Args:
      panel: long-format DataFrame with columns (country, year,
        indicator_id, value) from au.load_indicator_panel
      canonical_length_config: parsed v0.2-canonical-length.json dict
        with "indicators" map keyed by api_code (indicator_id)

    Returns: long-format DataFrame, same columns. Rows lost to first_diff
    (the earliest year per (country, indicator) pair) are dropped.
    Indicators NOT in the dispatch table are passed through unchanged
    with a warning (defensive: should not happen if the dispatch table
    covers the 109 Stage F indicators and the panel only queries those).
    """
    dispatch = canonical_length_config["indicators"]

    transformed_parts: list[pd.DataFrame] = []
    n_dropped_unknown = 0
    n_dropped_diff = 0
    by_transform: dict[str, int] = {}

    for ind_id, ind_panel in panel.groupby("indicator_id"):
        ind_panel = ind_panel.sort_values(["country", "year"]).reset_index(drop=True)
        spec = dispatch.get(ind_id)
        if spec is None:
            # Indicator not in dispatch table — pass through with warning.
            # Shouldn't happen in production (T9 queries Stage F indicators
            # the dispatch covers), but defensive against weight-matrix
            # indicators outside the audit set.
            print(f"  [WARN] {ind_id} not in canonical_length_config dispatch; "
                  f"passing through unchanged")
            n_dropped_unknown += 1
            transformed_parts.append(ind_panel)
            continue

        transform = spec["transform"]
        demean = spec["demean_applied"]
        by_transform[transform] = by_transform.get(transform, 0) + 1

        if transform == "pass_through":
            out = ind_panel.copy()
        elif transform == "first_diff":
            out = ind_panel.copy()
            out["value"] = out.groupby("country")["value"].diff()
            before = len(out)
            out = out.dropna(subset=["value"]).reset_index(drop=True)
            n_dropped_diff += before - len(out)
        elif transform == "log_diff":
            out = ind_panel.copy()
            # log of non-positive values produces NaN; .diff() handles
            # the row-1-NaN naturally.
            positive = out.where(out["value"] > 0)
            out["value"] = np.log(positive["value"]).groupby(out["country"]).diff()
            before = len(out)
            out = out.dropna(subset=["value"]).reset_index(drop=True)
            n_dropped_diff += before - len(out)
        else:
            raise ValueError(
                f"unknown transform {transform!r} in dispatch table for "
                f"indicator {ind_id}"
            )

        if demean:
            # Subtract per-year cross-country mean. NaN-safe via groupby-transform.
            out["value"] = out["value"] - out.groupby("year")["value"].transform("mean")

        transformed_parts.append(out)

    if not transformed_parts:
        return panel.iloc[0:0].copy()

    result = pd.concat(transformed_parts, ignore_index=True)
    print(f"  transform layer applied: {len(panel):,} -> {len(result):,} rows")
    print(f"    by transform: {by_transform}")
    if n_dropped_diff:
        print(f"    rows lost to first/log-differencing: {n_dropped_diff:,} "
              f"(expected; first year per (country, indicator) drops)")
    if n_dropped_unknown:
        print(f"    indicators not in dispatch (passed through): "
              f"{n_dropped_unknown}")
    return result


# ---------------------------------------------------------------------------
# Compute z-scored indicator panel
# ---------------------------------------------------------------------------

def compute_country_zscores(panel: pd.DataFrame, cutoff_year: int) -> pd.DataFrame:
    """For each (country, indicator_id) pair compute the z-score of the
    country's value at cutoff_year against the cross-country distribution
    at cutoff_year (or median over the recent ZSCORE_WINDOW_YEARS for
    countries missing the cutoff_year value).

    Returns long-format DataFrame: (country, indicator_id, value, z_score)
    """
    # Use median over the ZSCORE_WINDOW_YEARS ending at cutoff_year (inclusive)
    # so a missing single-year value doesn't drop a country.
    win_lo = cutoff_year - ZSCORE_WINDOW_YEARS + 1
    win = panel[(panel["year"] >= win_lo) & (panel["year"] <= cutoff_year)].copy()
    country_vals = win.groupby(["country", "indicator_id"])["value"].median().reset_index()

    # Cross-country z-score per indicator (vectorized via transform — avoids
    # the pandas groupby.apply include_groups deprecation warning).
    grp = country_vals.groupby("indicator_id")["value"]
    mu = grp.transform("mean")
    # Use string-form transform for consistency with the surrounding "mean"
    # / "min" / "max" calls; faster than a lambda (avoids per-group Python
    # dispatch). QA review 2026-05-03 caught the inconsistency.
    sd = grp.transform("std", ddof=0)
    # Where sd is 0/NaN: z-score is 0 (no information from that indicator)
    safe_sd = sd.where((sd > 0) & sd.notna(), other=np.nan)
    z = (country_vals["value"] - mu) / safe_sd
    country_vals = country_vals.copy()
    country_vals["z_score"] = z.fillna(0.0)
    return country_vals[["country", "indicator_id", "value", "z_score"]]


# ---------------------------------------------------------------------------
# Score per (country, event_category)
# ---------------------------------------------------------------------------

def score_country_event(weights_df: pd.DataFrame, zscores: pd.DataFrame,
                         country_id_to_str: dict, num_to_api: dict,
                         use_signed_scoring: bool = False,
                         directions: dict[str, int] | None = None) -> pd.DataFrame:
    """For each (country_id, event_category) pair: compute
        anomaly_score = sum over indicators in the event_category of
            f(z_score, direction) * weight
    where f() is:
        - |z_score|                   when use_signed_scoring=False (arms C, D)
        - direction × z_score         when use_signed_scoring=True (arms A, B)

    v4 NEW (Phase 5 v0.1a): the use_signed_scoring + directions arguments.
    Signed mode requires a directions map ({api_code: int in {-1, 0, +1}}).
    Indicators not in the directions map (or with direction=0) contribute
    zero in signed mode (matches the catalog convention that direction:0 =
    "model learns from the absolute z_score is meaningless without a
    literature-defensible sign"). The previous unsigned behavior is
    preserved exactly when use_signed_scoring=False.

    Args:
      weights_df: from weight-matrix.json (has indicator_numeric_id column)
      zscores: from compute_country_zscores (has country, indicator_id, z_score)
      country_id_to_str: {country_id: name} from qgi_data.countries
      num_to_api: {numeric_id: api_code} from indicator_map.csv
      use_signed_scoring: if True, use direction × z_score; else |z_score|
      directions: required when use_signed_scoring=True; ignored otherwise

    Returns DataFrame: (country_id, country_str, event_category,
                       anomaly_score, n_indicators_used)

    The weights table is keyed by indicator_numeric_id; the indicator
    panel is keyed by api_code. We bridge via num_to_api passed in by
    the caller.
    """
    if use_signed_scoring and directions is None:
        raise ValueError(
            "score_country_event(use_signed_scoring=True) requires a "
            "directions map. Pass directions=load_direction_annotations()."
        )

    # Add api_code column to weights_df via the shared num_to_api
    weights_df = weights_df.copy()
    weights_df["api_code"] = weights_df["indicator_numeric_id"].map(num_to_api)
    n_unmapped = weights_df["api_code"].isna().sum()
    if n_unmapped:
        print(f"  [WARN] {n_unmapped} weight rows have no api_code mapping — dropped")
        weights_df = weights_df.dropna(subset=["api_code"])

    # zscores has country (string) and indicator_id (api_code) — rename for join
    z = zscores.rename(columns={"indicator_id": "api_code"})

    # Join weights with zscores on api_code, compute per (country, event_category)
    merged = weights_df.merge(z, on="api_code", how="inner")

    if use_signed_scoring:
        # signed: direction × z_score × weight. Indicators not in the
        # directions map get direction 0 (no contribution). Indicators
        # with direction:0 in the catalog also get zero contribution — this
        # is the catalog convention for "no defensible literature sign;
        # defer to Majles."
        #
        # SIGN INVERSION (Phase 5 v0.1a strict review B1, 2026-05-11):
        # Catalog convention is `+1 = protective / risk-reducing`. So:
        #   weight × (+1) × HIGH z_score → LARGE POSITIVE partial → "more
        #     protective" condition → LOWER event probability.
        # But downstream AUC computes roc_auc_score(y_post_cutoff,
        # anomaly_score), which assumes HIGH score predicts y=1. To keep
        # that contract, we NEGATE the per-row partial_score so the
        # aggregated `anomaly_score` is a RISK score:
        #   HIGH anomaly_score → HIGH event probability  (signed AND unsigned)
        # This makes signed and unsigned arms directly comparable on AUC
        # without per-arm interpretation gymnastics. It also makes
        # Miriam's <0.03 swing rule (A vs D delta) meaningful as a
        # directional improvement check.
        merged["direction"] = merged["api_code"].map(directions).fillna(0).astype(int)
        merged["partial_score"] = -(
            merged["weight"] * merged["direction"] * merged["z_score"]
        )
    else:
        # unsigned legacy: |z_score| × weight (Phase 4 v0.2 behavior).
        # Already a risk score by construction (HIGH |z| = more anomalous =
        # higher predicted risk), so no negation needed.
        merged["partial_score"] = merged["weight"] * merged["z_score"].abs()
        merged["direction"] = 0  # kept for downstream uniformity; unused

    # n_indicators_used counts partial_score values — for signed mode,
    # this counts ALL joined rows (including direction:0 zero-contributors)
    # so the stratified-AUC split (≥10 cells vs <10 cells) measures
    # candidate-pool size, not effective-signal-pool size. That's the
    # right semantics: the stratification asks "did we have enough
    # indicators to compute a meaningful score" — direction:0 indicators
    # were SEEN, just not USED in signed mode.
    agg = merged.groupby(["country", "event_category"]).agg(
        anomaly_score=("partial_score", "sum"),
        n_indicators_used=("partial_score", "count"),
    ).reset_index()

    # Map country (str) -> country_id (int) via inverse of country_id_to_str
    str_to_id = {v: k for k, v in country_id_to_str.items()}
    agg["country_id"] = agg["country"].map(str_to_id)
    n_unmapped = agg["country_id"].isna().sum()
    if n_unmapped:
        print(f"  [WARN] {n_unmapped} aggregation rows had no country_id mapping — dropped")
        agg = agg.dropna(subset=["country_id"])
    agg["country_id"] = agg["country_id"].astype(int)

    return agg.rename(columns={"country": "country_str"})[
        ["country_id", "country_str", "event_category", "anomaly_score", "n_indicators_used"]
    ]


# ---------------------------------------------------------------------------
# Compute AUC + ECE + reliability
# ---------------------------------------------------------------------------

def compute_per_category_auc(scored: pd.DataFrame, gt: pd.DataFrame) -> list[dict]:
    """For each event_category in scored, compute AUC of anomaly_score
    vs y_post_cutoff."""
    merged = scored.merge(gt, on=["country_id", "event_category"], how="inner")
    out = []
    for ec, grp in merged.groupby("event_category"):
        y = grp["y_post_cutoff"].values
        pred = grp["anomaly_score"].values
        # Order checks: n-floor BEFORE all-same-label so the floor's
        # intent is unambiguous. Both produce auc=None per the gate's
        # contract; the order is purely for clarity.
        if len(grp) < 5:
            auc = None
        elif y.sum() == 0 or y.sum() == len(y):
            # All same label — AUC undefined
            auc = None
        else:
            try:
                auc = float(roc_auc_score(y, pred))
            except Exception:
                auc = None
        out.append({
            "event_category": ec,
            "n_countries": len(grp),
            "n_positive": int(y.sum()),
            "n_negative": int(len(y) - y.sum()),
            "auc": auc,
        })
    return out


def _auc_bootstrap_ci(
    y: np.ndarray, pred: np.ndarray, n_resamples: int, seed: int, alpha: float,
) -> tuple[float | None, float | None, list[float]]:
    """Compute bootstrap percentile CI for ROC AUC.

    Returns (lo, hi, point_estimates) where:
      - lo, hi = alpha/2 and 1-alpha/2 percentiles of the resample AUCs
      - point_estimates = the resample AUCs (length n_resamples; resamples
        that produced AUC-undefined cases are excluded)

    If fewer than 10 valid resamples can be computed, returns (None, None, [])
    — the CI is meaningless on a thin support.

    v4 NEW (Phase 5 v0.1a Step 2 spec): 1000 resamples per recipe.
    """
    n = len(y)
    if n < 5:
        return None, None, []
    rng = np.random.default_rng(seed)
    aucs = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        y_b = y[idx]
        p_b = pred[idx]
        # Same all-same-label guard as compute_per_category_auc
        if y_b.sum() == 0 or y_b.sum() == n:
            continue
        try:
            aucs.append(float(roc_auc_score(y_b, p_b)))
        except Exception:
            continue
    if len(aucs) < 10:
        return None, None, aucs
    lo = float(np.percentile(aucs, 100 * (alpha / 2)))
    hi = float(np.percentile(aucs, 100 * (1 - alpha / 2)))
    return lo, hi, aucs


def compute_per_category_auc_with_ci(
    scored: pd.DataFrame, gt: pd.DataFrame,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    alpha: float = BOOTSTRAP_CI_ALPHA,
) -> list[dict]:
    """v4 NEW. Per-category AUC plus bootstrap percentile CI.

    Same shape as compute_per_category_auc but each row also carries:
      - auc_ci_lo, auc_ci_hi: alpha/2 and 1-alpha/2 percentile of
        n_resamples bootstrap resamples
      - auc_ci_alpha: the CI level (for downstream display)

    Use deterministic seeds derived from (seed, event_category) so that
    re-runs produce identical CIs and individual category CIs are
    reproducible standalone. Falls back to None CIs when the resample
    distribution is too thin (< 10 valid resamples).
    """
    merged = scored.merge(gt, on=["country_id", "event_category"], how="inner")
    out = []
    for ec, grp in merged.groupby("event_category"):
        y = grp["y_post_cutoff"].values
        pred = grp["anomaly_score"].values

        if len(grp) < 5:
            auc = None
            ci_lo = ci_hi = None
        elif y.sum() == 0 or y.sum() == len(y):
            auc = None
            ci_lo = ci_hi = None
        else:
            try:
                auc = float(roc_auc_score(y, pred))
            except Exception:
                auc = None
            # Per-category seed: ensures CI for category X is reproducible
            # independently of other categories' presence. Uses SHA-256
            # (NOT Python `hash()`) for cross-process determinism — see
            # _derive_category_seed docstring + strict review 2026-05-11 M1.
            cat_seed = _derive_category_seed(seed, str(ec))
            ci_lo, ci_hi, _ = _auc_bootstrap_ci(
                y, pred, n_resamples=n_resamples,
                seed=cat_seed, alpha=alpha,
            )
        out.append({
            "event_category": ec,
            "n_countries": len(grp),
            "n_positive": int(y.sum()),
            "n_negative": int(len(y) - y.sum()),
            "auc": auc,
            "auc_ci_lo": ci_lo,
            "auc_ci_hi": ci_hi,
            "auc_ci_alpha": alpha,
        })
    return out


def compute_stratified_auc(
    scored: pd.DataFrame, gt: pd.DataFrame,
    strata_threshold: int = STRATA_INDICATOR_COUNT_THRESHOLD,
) -> dict:
    """v4 NEW (v5 amended for v0.2 γ-stage). Stratified AUC by n_indicators_used.

    Splits cells into:
      - "data-sufficient" stratum: n_indicators_used >= strata_threshold
      - "thin-coverage" stratum:   n_indicators_used <  strata_threshold

    Within each stratum, compute per-category AUC the same way as
    compute_per_category_auc, then summarize. This isolates whether the
    weight-matrix signal is concentrated in well-covered categories
    (Miriam's RECONVENE concern from the post-Phase-4 DECISION v2).

    v5 (T2 / #666): `strata_threshold` is now a parameter (was a module-
    level constant). Phase 5 v0.2 charter requires this to be configurable
    via the --strata-threshold CLI flag so γ-stage can run a sensitivity
    sweep at thresholds {3, 5, 7, 10, 15}. The module-level constant
    STRATA_INDICATOR_COUNT_THRESHOLD remains as the default for v3/v4-era
    callers; new code passes `strata_threshold` explicitly.

    Returns:
      {"threshold": int,
       "data_sufficient": {"n_cells": int, "n_categories": int,
                           "mean_auc": float, "median_auc": float,
                           "per_event_category_auc": [...]},
       "thin_coverage":   {... same shape ...}}
    """
    merged = scored.merge(gt, on=["country_id", "event_category"], how="inner")
    if merged.empty:
        return {
            "threshold": strata_threshold,
            "data_sufficient": {"n_cells": 0, "n_categories": 0,
                                "mean_auc": float("nan"),
                                "median_auc": float("nan"),
                                "per_event_category_auc": []},
            "thin_coverage": {"n_cells": 0, "n_categories": 0,
                              "mean_auc": float("nan"),
                              "median_auc": float("nan"),
                              "per_event_category_auc": []},
        }

    out = {"threshold": strata_threshold}
    for label, mask in [
        ("data_sufficient", merged["n_indicators_used"] >= strata_threshold),
        ("thin_coverage",   merged["n_indicators_used"] <  strata_threshold),
    ]:
        sub = merged.loc[mask]
        per_cat = []
        for ec, grp in sub.groupby("event_category"):
            y = grp["y_post_cutoff"].values
            pred = grp["anomaly_score"].values
            if len(grp) < 5 or y.sum() == 0 or y.sum() == len(y):
                auc = None
            else:
                try:
                    auc = float(roc_auc_score(y, pred))
                except Exception:
                    auc = None
            per_cat.append({
                "event_category": ec, "n_countries": len(grp),
                "n_positive": int(y.sum()), "auc": auc,
            })
        aucs = [c["auc"] for c in per_cat if c["auc"] is not None]
        out[label] = {
            "n_cells": int(mask.sum()),
            "n_categories": len(per_cat),
            "mean_auc": float(np.mean(aucs)) if aucs else float("nan"),
            "median_auc": float(np.median(aucs)) if aucs else float("nan"),
            "per_event_category_auc": per_cat,
        }
    return out


# Pre-registered γ-stage sensitivity sweep thresholds. Phase 5 v0.2 charter
# (Roshani A3 + Miriam A2): emit cell counts + mean AUC at each of these
# thresholds so the convening can see what rule v2 WOULD HAVE said at
# alternative cuts. This is a TRANSPARENCY artifact, not a decision artifact —
# the falsification gate uses Miriam's N=30 hard floor regardless. The sweep
# exists so post-hoc-rationalization risk is visible.
STRATUM_SENSITIVITY_THRESHOLDS = (3, 5, 7, 10, 15)


def compute_stratum_sensitivity(
    scored: pd.DataFrame, gt: pd.DataFrame,
    thresholds: tuple[int, ...] = STRATUM_SENSITIVITY_THRESHOLDS,
) -> dict:
    """v5 NEW (T2 / #666). Per-threshold stratum cardinality + mean AUC.

    For each threshold N in `thresholds`, count cells where n_indicators_used
    >= N and compute the mean per-category AUC restricted to those cells.
    Output structure mirrors compute_stratified_auc's "data_sufficient"
    branch, one entry per threshold.

    Phase 5 v0.2 charter (γ-stage / T4): runs at thresholds {3, 5, 7, 10, 15}
    to produce the sensitivity table the Majles inspects at the γ decision
    gate (T5). The sensitivity table is a transparency artifact only — the
    falsification rule v2 evaluates at Miriam's N=30 hard floor regardless
    of what the table shows.

    Returns:
      {"thresholds_swept": [3, 5, 7, 10, 15],
       "entries": [
         {"threshold": 3, "n_cells": int, "n_categories": int,
          "mean_auc": float, "median_auc": float},
         ...
       ]}

    Semantics note (PR #56 review fix 1):
      `n_categories` counts event_category groups PRESENT in the stratum
      (i.e. groups with at least one cell at n_indicators_used >= N).
      It is NOT the count of categories that contribute to `mean_auc` —
      categories with < 5 cells, all-same-label, or AUC-undefined are
      counted in `n_categories` but skipped in the mean. This matches
      compute_stratified_auc's `n_categories` convention; do not change
      one without changing the other.
    """
    merged = scored.merge(gt, on=["country_id", "event_category"], how="inner")
    entries: list[dict] = []

    for N in thresholds:
        if merged.empty:
            entries.append({
                "threshold": int(N),
                "n_cells": 0, "n_categories": 0,
                "mean_auc": float("nan"), "median_auc": float("nan"),
            })
            continue

        mask = merged["n_indicators_used"] >= N
        sub = merged.loc[mask]
        per_cat_aucs: list[float] = []
        n_categories = 0
        for ec, grp in sub.groupby("event_category"):
            n_categories += 1
            y = grp["y_post_cutoff"].values
            pred = grp["anomaly_score"].values
            if len(grp) < 5 or y.sum() == 0 or y.sum() == len(y):
                continue
            try:
                per_cat_aucs.append(float(roc_auc_score(y, pred)))
            except Exception:
                continue

        entries.append({
            "threshold": int(N),
            "n_cells": int(mask.sum()),
            "n_categories": n_categories,
            "mean_auc": float(np.mean(per_cat_aucs)) if per_cat_aucs else float("nan"),
            "median_auc": float(np.median(per_cat_aucs)) if per_cat_aucs else float("nan"),
        })

    return {
        "thresholds_swept": list(thresholds),
        "entries": entries,
    }


def compute_per_category_ece(
    scored: pd.DataFrame, gt: pd.DataFrame, n_bins: int = N_ECE_BINS,
) -> list[dict]:
    """v4 NEW. Per-event-category ECE + reliability diagram.

    v3 had a single cross-category ECE (which mixes base rates and is
    misleading — see method_caveats[1]). v4 adds per-category ECE so
    each event_category gets its own calibration estimate against its
    own base rate.

    Each category's predictions are min-max-scaled to [0, 1] *within the
    category*, then binned the same way as the cross-category ECE.
    """
    merged = scored.merge(gt, on=["country_id", "event_category"], how="inner")
    out = []
    for ec, grp in merged.groupby("event_category"):
        if len(grp) < 5:
            out.append({
                "event_category": ec, "n_cells": len(grp),
                "ece": None, "reliability_diagram": [],
            })
            continue
        scores = grp["anomaly_score"].values
        s_min, s_max = scores.min(), scores.max()
        span = s_max - s_min
        if span == 0:
            pred_scaled = np.full(len(grp), 0.5)
        else:
            pred_scaled = (scores - s_min) / span
        y = grp["y_post_cutoff"].values
        bins = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        rel = []
        for i in range(n_bins):
            lo, hi = bins[i], bins[i + 1]
            if i < n_bins - 1:
                mask = (pred_scaled >= lo) & (pred_scaled < hi)
            else:
                mask = (pred_scaled >= lo) & (pred_scaled <= hi)
            n_in = int(mask.sum())
            if n_in == 0:
                rel.append({"bin_lo": float(lo), "bin_hi": float(hi),
                            "n": 0, "mean_prediction": None,
                            "event_rate": None, "abs_calibration_gap": None})
                continue
            bin_pred = float(pred_scaled[mask].mean())
            bin_event_rate = float(y[mask].mean())
            gap = abs(bin_pred - bin_event_rate)
            ece += (n_in / len(grp)) * gap
            rel.append({"bin_lo": float(lo), "bin_hi": float(hi),
                        "n": n_in, "mean_prediction": bin_pred,
                        "event_rate": bin_event_rate,
                        "abs_calibration_gap": gap})
        out.append({
            "event_category": ec, "n_cells": len(grp),
            "ece": float(ece), "reliability_diagram": rel,
        })
    return out


def load_anchor_battery(path: Path = ANCHOR_BATTERY_JSON) -> dict:
    """v4 NEW (Phase 5 v0.1a Step 3). Load cascade-anchor-case-battery.json.

    Returns the full parsed JSON object so callers have access to the
    schema metadata + cases. Missing-file behavior: returns None and
    warns; the per-arm evaluation continues without anchor-case results
    (anchor cases are a regression suite, not a hard-blocker).
    """
    if not path.exists():
        print(f"  [WARN] {path.name} not found — anchor-case battery skipped. "
              f"Anchor results will be absent from the per-arm output JSON.")
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    print(f"  anchor-case-battery: {len(d.get('cases', []))} cases "
          f"(schema_v{d.get('schema_version')})")
    return d


def _compute_percentile_per_category(scored: pd.DataFrame) -> pd.DataFrame:
    """Compute predicted-risk percentile per (country, event_category).

    Per the anchor-battery `rank_basis` convention (cascade-anchor-case-
    battery.json `evaluation_semantics.rank_basis`): ASCENDING by
    anomaly_score, so:
      - percentile = rank / n_countries  (rank starts at 1)
      - percentile = 0.05 = bottom 5% (least predicted-risk)
      - percentile = 0.95 = top 5%    (most predicted-risk)

    Under the v4 risk-direction convention (PR #43 B1 fix), HIGH
    anomaly_score = HIGH event probability. So HIGH percentile = HIGH
    predicted risk. All anchor predicates assume this convention.
    """
    out = scored.copy()
    # Rank ascending: lowest anomaly_score → rank 1 → low percentile.
    out["risk_rank"] = out.groupby("event_category")["anomaly_score"].rank(
        method="average", ascending=True,
    )
    out["n_in_category"] = out.groupby("event_category")["country_str"].transform("count")
    out["risk_percentile"] = out["risk_rank"] / out["n_in_category"]
    return out


def _eval_predicate(case: dict, percentile_df: pd.DataFrame) -> dict:
    """Evaluate a single anchor case against the percentile_df.

    Returns: {case_id, country, country_resolved_to, event_categories,
              test_type, evaluation_scope, phase_gate, predicate_type,
              actual_values, passed, reason}

    `passed` semantics:
      - True  : case passes the predicate
      - False : case fails the predicate
      - None  : case cannot be evaluated (universe gap, cross-arm
                scope, or primary+fallback both insufficient)
    """
    case_id = case["case_id"]
    country = case["country"]
    test_type = case["test_type"]
    scope = case.get("evaluation_scope", "per_arm")
    phase_gate = case["phase_gate"]
    pred = case["predicate"]
    pred_type = pred["type"]
    base = {
        "case_id": case_id,
        "country": country,
        "country_resolved_to": None,
        "event_categories": case["event_categories"],
        "test_type": test_type,
        "evaluation_scope": scope,
        "phase_gate": phase_gate,
        "predicate_type": pred_type,
        "actual_values": None,
        "passed": None,
        "reason": "",
    }

    # Universe-gap guard (T3 from strict review).
    if case.get("in_evaluation_universe") is False:
        base["reason"] = (
            "country_outside_evaluation_universe (in_evaluation_universe=false; "
            "see case.universe_note)"
        )
        return base

    # Cross-arm scope guard (T4 from strict review).
    if scope == "cross_arm":
        base["reason"] = (
            "evaluation_scope=cross_arm; computed in step 5 cross-arm comparison, "
            "not per-arm evaluation"
        )
        return base

    # Per-arm evaluation.
    cats = case["event_categories"]
    sub = percentile_df[
        (percentile_df["country_str"] == country)
        & (percentile_df["event_category"].isin(cats))
    ]

    # Country-fallback rule for case 8 (Yemen → Somalia).
    if case.get("country_alternatives") and not _country_has_sufficient_data(
        sub, cats, case.get("country_fallback_rule", {})
    ):
        # Primary insufficient; try alternatives in order.
        for alt in case["country_alternatives"]:
            alt_sub = percentile_df[
                (percentile_df["country_str"] == alt)
                & (percentile_df["event_category"].isin(cats))
            ]
            if not alt_sub.empty and _country_has_sufficient_data(
                alt_sub, cats, case.get("country_fallback_rule", {})
            ):
                sub = alt_sub
                base["country_resolved_to"] = alt
                break
        else:
            base["reason"] = (
                "primary country has insufficient data on >=3 categories "
                "(n_countries < 5 per category) AND fallback alternative(s) "
                "either insufficient or outside evaluation universe"
            )
            return base
    else:
        base["country_resolved_to"] = country

    if sub.empty:
        base["reason"] = (
            f"no rows in scored data for country={country} on any of "
            f"event_categories={cats}. Country may be missing from the "
            f"weight-matrix coverage or event ground truth."
        )
        return base

    # Collect per-category percentiles (the actual_values payload).
    actual_values = {
        row["event_category"]: float(row["risk_percentile"])
        for _, row in sub.iterrows()
    }
    base["actual_values"] = actual_values

    # Dispatch by predicate type.
    if pred_type == "percentile_below":
        threshold = pred["threshold"]
        # Single-category test (cases 1, 2 use this with one category)
        cat = cats[0]
        if cat not in actual_values:
            base["reason"] = f"event_category {cat} not in scored data for {country}"
            return base
        actual = actual_values[cat]
        passed = actual < threshold
        base["passed"] = bool(passed)
        base["reason"] = (
            f"{country} percentile on {cat} = {actual:.4f}; "
            f"threshold = below {threshold:.2f} → {'PASS' if passed else 'FAIL'}"
        )

    elif pred_type == "percentile_above":
        threshold = pred["threshold"]
        # Cases 4, 5: case 5 uses predicate_satisfies_any=True (any of
        # the 3 economic categories above threshold passes); case 4 has
        # a single category.
        # T1 strict-review fix: use strict `>` for "above" predicates to
        # match the strict `<` used by "below" predicates. The boundary
        # itself is on the FAIL side for both directions — matching the
        # JSON spec text "above the 50th percentile" (strict) and the
        # "below the 30th percentile" (strict).
        any_pass = case.get("predicate_satisfies_any", False)
        if any_pass:
            passes = [v > threshold for v in actual_values.values()]
            passed = any(passes)
            base["passed"] = bool(passed)
            base["reason"] = (
                f"{country} percentiles = {actual_values}; "
                f"threshold = above {threshold:.2f} (satisfies_any) → "
                f"{'PASS' if passed else 'FAIL'} "
                f"({sum(passes)}/{len(passes)} categories above threshold)"
            )
        else:
            cat = cats[0]
            if cat not in actual_values:
                base["reason"] = f"event_category {cat} not in scored data for {country}"
                return base
            actual = actual_values[cat]
            passed = actual > threshold
            base["passed"] = bool(passed)
            base["reason"] = (
                f"{country} percentile on {cat} = {actual:.4f}; "
                f"threshold = above {threshold:.2f} → {'PASS' if passed else 'FAIL'}"
            )

    elif pred_type == "rank_floor_all_categories":
        threshold = pred["threshold"]
        # ALL categories must be below threshold
        breaches = {c: v for c, v in actual_values.items() if v >= threshold}
        passed = len(breaches) == 0
        base["passed"] = bool(passed)
        if passed:
            max_p = max(actual_values.values()) if actual_values else 0.0
            base["reason"] = (
                f"{country} max percentile across {len(actual_values)} categories "
                f"= {max_p:.4f}; threshold = floor below {threshold:.2f} on ALL → PASS"
            )
        else:
            base["reason"] = (
                f"{country} BREACHES floor on {len(breaches)} categories: "
                f"{breaches}; threshold = below {threshold:.2f} on ALL → FAIL"
            )

    elif pred_type == "multi_category_count_above":
        threshold = pred["threshold"]
        min_categories = pred["min_categories"]
        # T1: strict `>` per the JSON spec text "above the 75th percentile"
        above = [c for c, v in actual_values.items() if v > threshold]
        passed = len(above) >= min_categories
        base["passed"] = bool(passed)
        base["reason"] = (
            f"{country} above {threshold:.2f} on {len(above)} of "
            f"{len(actual_values)} categories ({above}); "
            f"threshold = at least {min_categories} → {'PASS' if passed else 'FAIL'}"
        )

    elif pred_type == "rank_stability_across_versions":
        # Cross-arm scope; should have been caught above. Defensive.
        base["reason"] = (
            "rank_stability_across_versions is cross-arm; should not reach "
            "per-arm evaluation. This is a bug — case was missing "
            "evaluation_scope=cross_arm in the JSON."
        )
        return base

    else:
        base["reason"] = f"unknown predicate type: {pred_type}"
        return base

    return base


def _country_has_sufficient_data(
    sub: pd.DataFrame, cats: list, fallback_rule: dict,
) -> bool:
    """Yemen→Somalia fallback rule: country must have at least
    `min_categories_with_data` categories with `n_in_category >=
    min_n_countries_per_category` (T5 from strict review — threshold
    lifted from prose to structured data).
    """
    if not fallback_rule:
        return not sub.empty
    min_cats = fallback_rule.get("min_categories_with_data", 1)
    min_n = fallback_rule.get("min_n_countries_per_category", 1)
    qualifying = sub[sub["n_in_category"] >= min_n]
    return qualifying["event_category"].nunique() >= min_cats


def evaluate_anchor_cases(scored: pd.DataFrame, battery: dict | None) -> list[dict]:
    """v4 NEW (Phase 5 v0.1a Step 3). Evaluate the 8-case anchor battery
    against the per-arm scored output.

    Returns a list of per-case result dicts (see _eval_predicate for the
    schema). When battery is None (file missing), returns empty list +
    a warning was already printed by load_anchor_battery.
    """
    if battery is None:
        return []
    if scored.empty:
        return [
            {**{k: None for k in ("actual_values", "passed")},
             "case_id": c["case_id"], "country": c["country"],
             "reason": "scored DataFrame is empty"}
            for c in battery.get("cases", [])
        ]
    percentile_df = _compute_percentile_per_category(scored)
    return [_eval_predicate(case, percentile_df) for case in battery.get("cases", [])]


def compute_ece_and_reliability(scored: pd.DataFrame, gt: pd.DataFrame,
                                 n_bins: int = N_ECE_BINS) -> tuple[float, list[dict]]:
    """Min-max-scale anomaly_score to [0, 1] WITHIN EACH event_category
    (otherwise events with very different score scales would dominate),
    then compute ECE across all (country, event_category) cells.
    """
    merged = scored.merge(gt, on=["country_id", "event_category"], how="inner")
    if merged.empty:
        return float("nan"), []

    # Per-category min-max scale (vectorized via transform — avoids the
    # pandas groupby.apply include_groups deprecation warning).
    grp = merged.groupby("event_category")["anomaly_score"]
    s_min = grp.transform("min")
    s_max = grp.transform("max")
    span = s_max - s_min
    # When span == 0 (all scores equal in the category), pred_scaled=0.5
    merged = merged.copy()
    merged["pred_scaled"] = np.where(
        span == 0, 0.5, (merged["anomaly_score"] - s_min) / span.replace(0, np.nan),
    )
    merged["pred_scaled"] = merged["pred_scaled"].fillna(0.5)

    # Bin
    bins = np.linspace(0, 1, n_bins + 1)
    rel = []
    ece = 0.0
    n_total = len(merged)
    for i in range(n_bins):
        lo = bins[i]
        hi = bins[i + 1]
        mask = (merged["pred_scaled"] >= lo) & (merged["pred_scaled"] < hi if i < n_bins - 1
                                                else merged["pred_scaled"] <= hi)
        n_in = int(mask.sum())
        if n_in == 0:
            rel.append({"bin_lo": float(lo), "bin_hi": float(hi),
                        "n": 0, "mean_prediction": None, "event_rate": None,
                        "abs_calibration_gap": None})
            continue
        bin_pred = float(merged.loc[mask, "pred_scaled"].mean())
        bin_event_rate = float(merged.loc[mask, "y_post_cutoff"].mean())
        gap = abs(bin_pred - bin_event_rate)
        ece += (n_in / n_total) * gap
        rel.append({"bin_lo": float(lo), "bin_hi": float(hi),
                    "n": n_in, "mean_prediction": bin_pred,
                    "event_rate": bin_event_rate,
                    "abs_calibration_gap": gap})
    return float(ece), rel


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(
    cutoff_year: int = DEFAULT_CUTOFF_YEAR,
    end_year: int = DEFAULT_END_YEAR,
    with_baselines: bool = False,
    baseline_seed: int = DEFAULT_BASELINE_SEED,
    ablation_arm: str = DEFAULT_ABLATION_ARM,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    strata_threshold: int = STRATA_INDICATOR_COUNT_THRESHOLD,
    # v6 NEW (T8 / #672 / T7 binding):
    baseline_seeds: tuple[int, ...] | None = None,
    rule_v2_evaluation: bool = False,
    canonical_length_config_path: Path = CANONICAL_LENGTH_CONFIG_JSON_DEFAULT,
    exclusion_list_config_path: Path = EXCLUSION_LIST_CONFIG_JSON_DEFAULT,
    # v6 NEW (T12 #692): emit per-(country_id, event_category) anomaly_score
    # tensor for Path B's partial-pooling evaluator. When True, the output
    # JSON gains a top-level `per_cell` block. Default False preserves
    # backward-compat with v5 consumers.
    emit_per_cell: bool = False,
) -> None:
    if ablation_arm not in ABLATION_ARMS:
        raise ValueError(
            f"ablation_arm must be one of {ABLATION_ARMS}; got {ablation_arm!r}"
        )
    use_signed_scoring, apply_filter = ARM_CONFIG[ablation_arm]
    print(f"[0] Ablation arm: {ablation_arm} "
          f"(signed_scoring={use_signed_scoring}, apply_591_filter={apply_filter})")

    # v6 NEW (T8 / #672): T7 phase doc binding — when rule_v2_evaluation
    # is True, the canonical_length config + exclusion-list config + JSON
    # config (V0_2_FALSIFICATION_CONFIG_JSON) MUST exist. T9 (Stage α)
    # fires with rule_v2_evaluation=True; earlier sanity-check D-arm runs
    # leave it False.
    canonical_length_config = load_canonical_length_config(
        path=canonical_length_config_path, required=rule_v2_evaluation,
    )
    # v6.5 (T8.5 / Tariq §5.2 step iii): under rule_v2_evaluation, reject
    # a half-populated dispatch table. The recipe-aggregator pass must
    # have filled canonical_length_value for every indicator before T9
    # fires; without this assertion, the failure mode is silent (the
    # transform-layer code happily uses transform + demean fields and
    # never reads canonical_length_value, so a null value would not
    # trigger any other error — but the absence of values means the
    # recipe-aggregator pass did not run, which means the values used
    # downstream are stale or missing).
    if rule_v2_evaluation and canonical_length_config:
        null_values = [
            ind for ind, cfg in canonical_length_config["indicators"].items()
            if cfg.get("canonical_length_value") is None
        ]
        if null_values:
            raise ValueError(
                f"v0.2-canonical-length.json has {len(null_values)} indicators "
                f"with null canonical_length_value (sample: {null_values[:5]}). "
                f"T8.5 requires the recipe-aggregator pipeline pass to populate "
                f"these BEFORE T9 fires. See JSON `binding_clause` field for "
                f"context."
            )
    exclusion_list = load_exclusion_list_config(
        path=exclusion_list_config_path, required=rule_v2_evaluation,
    )
    falsification_config = load_v0_2_falsification_config(
        required=rule_v2_evaluation,
    )

    # v6 NEW: multi-seed baseline default (Roshani A3 + Kwame bright-line).
    # When `baseline_seeds` is None and `with_baselines=True`, use the
    # 5-seed default. When the caller explicitly passes a non-None tuple,
    # honor it. When `with_baselines=False`, no baselines run regardless.
    if baseline_seeds is None and with_baselines:
        baseline_seeds = DEFAULT_BASELINE_SEEDS

    print(f"[1] Loading weight matrix ({WEIGHT_MATRIX_JSON.name})")
    weights_df = load_weight_matrix()

    # v4 NEW: direction annotations + #591 filter per arm. Hard-error
    # (NOT silent fallback) when a required input is missing in the
    # arm that requires it — per strict review 2026-05-11 m4. Silent
    # degradation in arm A would make it indistinguishable from arm B,
    # defeating the 4-arm ablation's whole purpose.
    directions: dict[str, int] = {}
    if use_signed_scoring:
        print(f"  Loading direction annotations ({DIRECTIONS_JSON.name})")
        directions = load_direction_annotations()
        if not directions:
            raise FileNotFoundError(
                f"Arm {ablation_arm} requires direction annotations at "
                f"{DIRECTIONS_JSON} but the file is missing or empty. "
                f"Either generate it (see docs/specs/internal/ops/cascade-track/"
                f"catalog-direction-annotation-cascade-side.md for the source-of-"
                f"truth working draft + a generator-spec TODO), or rerun with "
                f"--ablation-arm D (the unsigned-no-filter baseline that does "
                f"not need directions)."
            )
    if apply_filter:
        print(f"  Loading #591 allow-list ({ALLOW_LIST_JSON.name})")
        allow_ids = load_allow_list()
        if allow_ids is None:
            raise FileNotFoundError(
                f"Arm {ablation_arm} requires the #591 allow-list at "
                f"{ALLOW_LIST_JSON} but the file is missing. Generate it "
                f"via `python qgi-ml/scripts/generate_indicator_allow_list.py "
                f"--bucket qgi-data-lake-771606957899`, or rerun with "
                f"--ablation-arm B or D (no-filter arms)."
            )
        weights_df = apply_591_filter(weights_df, allow_ids)

    # v4 Step 3: anchor-case battery (regression suite). Optional — if
    # missing, anchor results are absent from the output (NOT a fatal
    # error; anchor cases are documentation/regression, not gating).
    print(f"  Loading anchor-case battery ({ANCHOR_BATTERY_JSON.name})")
    anchor_battery = load_anchor_battery()

    needed_num_ids = sorted(weights_df["indicator_numeric_id"].unique().tolist())
    print(f"  indicators in weight matrix (post-filter): {len(needed_num_ids)}")

    print("\n[2] Building num_id -> api_code chain")
    num_to_api = eb.load_numeric_to_api()
    needed_api_codes = [num_to_api[nid] for nid in needed_num_ids if nid in num_to_api]
    print(f"  api_codes: {len(needed_api_codes)}")

    # v6 NEW (T8 / #672 — review fix MAJOR #4): apply T7 §5 (b)
    # demeaning-insufficient exclusion. The exclusion list contains
    # api_code id_strings; map back to numeric_ids via num_to_api and
    # filter the weight matrix. Only applied when rule_v2_evaluation
    # is True (Stage α / Path A); D-arm sanity-check runs are unchanged.
    if rule_v2_evaluation and exclusion_list:
        api_to_num = {v: k for k, v in num_to_api.items()}
        excluded_num_ids = {
            api_to_num[code] for code in exclusion_list
            if code in api_to_num
        }
        missing = exclusion_list - {num_to_api.get(nid) for nid in excluded_num_ids}
        if missing:
            print(
                f"  [WARN] T7 §5 (b) exclusion list contains {len(missing)} "
                f"indicators not in num_to_api: {sorted(missing)}. They cannot "
                f"be excluded — verify the exclusion list against the indicator "
                f"map before T9 fires."
            )
        before = len(weights_df)
        weights_df = weights_df[
            ~weights_df["indicator_numeric_id"].isin(excluded_num_ids)
        ].copy()
        after = len(weights_df)
        print(
            f"  T7 §5 (b) exclusion applied: dropped {before - after} weight "
            f"matrix rows for {len(excluded_num_ids)} demeaning-insufficient "
            f"indicators (FP.CPI.TOTL.ZG, NY.GDP.PCAP.CD, SH.DYN.MORT, "
            f"SP.POP.TOTL); {after} rows remain"
        )
        # Refresh derived lists since the matrix changed.
        needed_num_ids = sorted(weights_df["indicator_numeric_id"].unique().tolist())
        needed_api_codes = [num_to_api[nid] for nid in needed_num_ids if nid in num_to_api]

    print("\n[3] Pulling Athena data (panel + ground truth + countries)")
    creds_path = Path(r"C:/Users/Amin/AppData/Local/Temp/qgi/staging_creds.json")
    creds = json.loads(creds_path.read_text())
    sess = boto3.Session(
        aws_access_key_id=creds["ak"],
        aws_secret_access_key=creds["sk"],
        aws_session_token=creds["st"],
        region_name="eu-central-1",
    )
    ath = sess.client("athena")

    # v6.5 (T8.5 / Tariq §5.2): under rule_v2_evaluation we'll apply
    # the transform layer post-pull. first_diff / log_diff drop the
    # earliest year per (country, indicator), so widen the panel window
    # by 1 year to preserve ZSCORE_WINDOW_YEARS observations after the
    # differencing operation.
    if rule_v2_evaluation and canonical_length_config:
        panel_lo = cutoff_year - ZSCORE_WINDOW_YEARS  # widened: drop 1 year via diff
    else:
        panel_lo = cutoff_year - ZSCORE_WINDOW_YEARS + 1
    panel = au.load_indicator_panel(
        ath, "qgi-data-lake-771606957899", "QGI-Lambda-Workgroup",
        needed_api_codes, panel_lo, cutoff_year,
    )
    print(f"  indicator panel: {len(panel):,} rows ({panel_lo}..{cutoff_year})")

    # v6.5 (T8.5 / Tariq §5.2 step ii): apply transform layer BEFORE
    # z-scoring. This brings the v6 evaluator into conformance with
    # charter A6 (canonical_length re-derivation on transformed series)
    # and T5 Bridge B5+'s ratified routing to Path A on Stage F.
    # Gated on rule_v2_evaluation so the v4/v5 D-arm sanity-check path
    # is unchanged.
    if rule_v2_evaluation and canonical_length_config:
        print("\n[3b] Applying v0.2 transform layer (T8.5 / Tariq §5.2)")
        panel = apply_transform_layer(panel, canonical_length_config)

    gt = au.load_event_ground_truth(
        ath, "qgi-data-lake-771606957899", "QGI-Lambda-Workgroup",
        cutoff_year, end_year,
    )
    print(f"  ground truth: {len(gt):,} (country_id, event_category) cells")

    countries = au.load_countries(
        ath, "qgi-data-lake-771606957899", "QGI-Lambda-Workgroup",
    )
    country_id_to_str = dict(zip(countries["country_id"].astype(int), countries["name"]))
    print(f"  countries: {len(country_id_to_str)}")

    print(f"\n[4] Computing country z-scores @ cutoff {cutoff_year}")
    zscores = compute_country_zscores(panel, cutoff_year)
    print(f"  z-scored cells: {len(zscores):,}")

    print(f"\n[5] Evaluating weight matrices (arm={ablation_arm})")
    treatment = evaluate_weights(
        weights_df, zscores, country_id_to_str, num_to_api, gt,
        label=f"treatment_arm{ablation_arm}",
        use_signed_scoring=use_signed_scoring, directions=directions,
        bootstrap_resamples=bootstrap_resamples, bootstrap_seed=bootstrap_seed,
        anchor_battery=anchor_battery,
        strata_threshold=strata_threshold,
        emit_per_cell=emit_per_cell,
    )
    mean_auc = treatment["mean_auc"]
    n_above_0_55 = treatment["n_auc_above_0_55"]
    n_above_0_65 = treatment["n_auc_above_0_65"]
    median_auc = treatment["median_auc"]
    aucs_real = [c["auc"] for c in treatment["per_event_category_auc"] if c["auc"] is not None]
    ece = treatment["ece"]
    reliability = treatment["reliability_diagram"]
    per_cat = treatment["per_event_category_auc"]

    baseline_uniform = None
    baseline_random = None  # v5 single-seed baseline (kept for backward-compat)
    baseline_random_multi_seed: list[dict] = []  # v6 NEW (T8 / #672)
    if with_baselines:
        # T5 strict-review fix: anchor battery is about treatment
        # methodology (does the formula correctly handle Malta, Norway,
        # etc.) — "Norway fails the floor under uniform weights" is
        # uninformative because the formula is what we're ablating.
        # Skip anchor evaluation for baselines.
        baseline_uniform = evaluate_weights(
            build_uniform_baseline(weights_df), zscores,
            country_id_to_str, num_to_api, gt,
            label="baseline_uniform",
            use_signed_scoring=use_signed_scoring, directions=directions,
            bootstrap_resamples=bootstrap_resamples, bootstrap_seed=bootstrap_seed,
            anchor_battery=None,
            strata_threshold=strata_threshold,
        )
        # v5 single-seed baseline (legacy field for backward-compat consumers).
        baseline_random = evaluate_weights(
            build_random_baseline(weights_df, seed=baseline_seed), zscores,
            country_id_to_str, num_to_api, gt,
            label=f"baseline_random_seed{baseline_seed}",
            use_signed_scoring=use_signed_scoring, directions=directions,
            bootstrap_resamples=bootstrap_resamples, bootstrap_seed=bootstrap_seed,
            anchor_battery=None,
            strata_threshold=strata_threshold,
        )
        # v6 NEW (T8 / #672): multi-seed baseline. The 5-seed default sweep
        # gives the random-baseline delta a CI rather than a point estimate,
        # closing Roshani A3 + Kwame bright-line + Priya's heterogeneity
        # demand for falsification gates that survive seed variance.
        if baseline_seeds:
            print(f"\n[5b] Multi-seed random baseline ({len(baseline_seeds)} seeds: {list(baseline_seeds)})")
            for s in baseline_seeds:
                b = evaluate_weights(
                    build_random_baseline(weights_df, seed=s), zscores,
                    country_id_to_str, num_to_api, gt,
                    label=f"baseline_random_seed{s}",
                    use_signed_scoring=use_signed_scoring, directions=directions,
                    bootstrap_resamples=bootstrap_resamples, bootstrap_seed=bootstrap_seed,
                    anchor_battery=None,
                    strata_threshold=strata_threshold,
                )
                baseline_random_multi_seed.append({
                    "seed": int(s),
                    "mean_auc": float(b["mean_auc"]),
                    "median_auc": float(b["median_auc"]),
                    "stratified_data_sufficient_mean_auc": float(
                        b["stratified_auc"]["data_sufficient"]["mean_auc"]
                    ) if np.isfinite(b["stratified_auc"]["data_sufficient"]["mean_auc"]) else None,
                })

    # Reliability diagram log (treatment only — baselines' reliability is
    # in the JSON but printing all 3 to stdout is noisy.)
    print("\n[6] Treatment reliability bins (non-empty):")
    for b in reliability:
        if b["n"] > 0:
            print(f"    [{b['bin_lo']:.2f}, {b['bin_hi']:.2f}]  n={b['n']:>4d}  "
                  f"pred={b['mean_prediction']:.3f}  event_rate={b['event_rate']:.3f}  "
                  f"gap={b['abs_calibration_gap']:.3f}")

    # v4: per-arm output path. Legacy phase4-validation.json is also
    # written as a symlink-alias for the D-arm to preserve v3 consumers.
    output_path = ROOT / "qgi-data" / "reference" / OUTPUT_JSON_TEMPLATE.format(arm=ablation_arm)
    print(f"\n[7] Writing {output_path}")
    # v6 NEW (T8 / #672): rule v2 verdict + posterior protocol. The
    # legacy v4 PROCEED / PROCEED_WITH_CAUTION / REVISIT / INSUFFICIENT_DATA
    # scheme is REPLACED with rule v2's INERT / HARD-FALSIFY / SOFT-FALSIFY /
    # PARTIAL / PASS verdict per pre-reg spec §1 + 4-tier exit table §5.
    #
    # Backward-compat: D-arm-only sanity-check runs (rule_v2_evaluation=False)
    # still emit a `decision` field, but it's the rule v2 verdict computed
    # on the full-set stratum (not the registered ≥10 stratum), which will
    # almost always return INERT because the cardinality floor binds.
    # Consumers that need the legacy PROCEED/REVISIT scheme should pin to
    # pre-v6 schema_version (= 4) and load the per-arm JSON accordingly.
    stratum_block = treatment["stratified_auc"]["data_sufficient"]
    stratum_n_cells = int(stratum_block.get("n_cells", 0))
    stratum_mean_auc = stratum_block.get("mean_auc", float("nan"))

    # A-D swing: when this arm is A and we have a D-arm baseline in scope,
    # compute it; otherwise the swing is None (and rule v2 returns INERT).
    # In production Path A (T9), the cascade runs the 4 arms separately
    # then aggregates via summarize_gamma_sensitivity.py; the per-arm JSON
    # carries enough info for the aggregator to compute A-D itself.
    # Here we emit None for swing on the per-arm JSON; the aggregator
    # owns the final rule v2 verdict on the cross-arm artifact.
    inert_triggers_local: list[str] = []
    # Optional placeholder: if a non-finite full-set mean_auc appears,
    # surface it as a rule v2 INERT trigger candidate (caller may add
    # cross-arm byte-identical triggers in the aggregator).
    if not np.isfinite(mean_auc):
        inert_triggers_local.append("treatment_mean_auc_undefined")

    anchor_pass_evaluable = sum(
        1 for r in treatment["anchor_case_battery"]["cases"]
        if r.get("passed") is True
    )
    anchor_total_evaluable = sum(
        1 for r in treatment["anchor_case_battery"]["cases"]
        if r.get("passed") is not None
    )

    verdict = compute_rule_v2_verdict(
        stratum_n_cells=stratum_n_cells,
        stratum_mean_auc=stratum_mean_auc if np.isfinite(stratum_mean_auc) else None,
        stratum_ci_lower=None,  # per-arm JSON does not compute the bootstrap CI for the stratum AUC; T11 aggregator does.
        a_minus_d_swing=None,  # cross-arm; computed by T11 aggregator
        anchor_pass_evaluable=anchor_pass_evaluable,
        anchor_evaluable_total=anchor_total_evaluable,
        inert_triggers=inert_triggers_local,
    )
    decision = verdict["decision"]
    decision_rationale = verdict["rationale"]

    posterior = compute_posterior_update(
        rule_v2_decision=decision, a_minus_d_swing=None,
    )

    # Legacy compatibility annotation: when baselines are computed AND
    # treatment is below the random baseline, append a note (preserved
    # from v4/v5 for cascade-Opus consumers reading the legacy alias).
    if (baseline_random is not None
            and np.isfinite(mean_auc)
            and np.isfinite(baseline_random["mean_auc"])
            and mean_auc < baseline_random["mean_auc"]):
        decision_rationale += (
            f" [Legacy v4 annotation: full-set treatment AUC ({mean_auc:.3f}) "
            f"is BELOW the random-weight baseline "
            f"({baseline_random['mean_auc']:.3f}); under the v4 scheme this "
            f"was a strong REVISIT signal. Under v6 rule v2, this annotation "
            f"is informational only — the verdict above is the binding one.]"
        )

    output = {
        "schema_version": SCHEMA_VERSION,
        "generated": datetime.now(timezone.utc).isoformat(),
        "ablation_arm": ablation_arm,
        "ablation_arm_config": {
            "use_signed_scoring": use_signed_scoring,
            "apply_591_filter": apply_filter,
        },
        "method": (
            f"anomaly_score = sum over (indicator in event_category) of "
            f"{'direction × z_score' if use_signed_scoring else '|z_score|'}"
            f" × weight"
            f"{' (post-#591 filter)' if apply_filter else ''}. "
            "AUC computed per event_category against y_post_cutoff with "
            f"bootstrap 95% CI ({DEFAULT_BOOTSTRAP_RESAMPLES} resamples). "
            "Stratified AUC by n_indicators_used (threshold "
            f"{strata_threshold}). ECE computed per category "
            f"and cross-category ({N_ECE_BINS} bins, min-max-scaled)."
        ),
        "method_caveats": [
            # Documented per QA review 2026-05-03 (MAJOR #1 + MINOR #4).
            "Imbalanced ground truth bias: ground truth excludes (country, "
            "event_category) cells where the country never had ANY event of "
            "that category (pre or post cutoff). High-base-rate categories "
            "(e.g. bilateral_treaty ~0.72) suppress discrimination signal. "
            "Mean AUC is therefore a LOWER bound on per-cell predictive power.",
            "Cross-category ECE (`ece` field, `reliability_diagram`) reflects "
            "category-base-rate mixing, NOT per-category calibration. Use "
            "`per_event_category_ece` for per-category calibration instead. "
            "Both retained: cross-category for v3 backward-compat, "
            "per-category for Phase 5+ analysis.",
            "Bootstrap CI on per-category AUC uses percentile method "
            "(non-bias-corrected). For categories with n < 10 valid resamples "
            "the CI is reported as None — typically driven by all-same-label "
            "in many bootstrap draws when the ground-truth positive count is "
            "small, or when the underlying cell count is below the data-"
            "sufficiency floor of 5 (in which case the point-AUC is also None).",
            "In signed-scoring mode (arms A, B), indicators with direction:0 "
            "in the catalog contribute zero to the anomaly_score. The "
            "stratified-AUC `n_indicators_used` threshold counts ALL joined "
            "indicators (including direction:0 zero-contributors), so the "
            "stratification reflects candidate-pool size, not "
            "effective-signal-pool size.",
            "Risk-direction inversion (signed arms A, B): catalog convention "
            "is `+1 = protective`. To keep `anomaly_score` interpretable as a "
            "RISK score (HIGH → HIGH event probability — required for AUC "
            "vs y_post_cutoff comparability with the unsigned arms C, D), "
            "per-row partial scores in signed mode are negated: "
            "risk_partial = -(weight × direction × z_score). This makes "
            "signed and unsigned arm AUCs directly comparable, and makes "
            "the A-vs-D delta a directional improvement measure. See "
            "_derive_category_seed sibling for the related determinism fix.",
        ],
        "config": {
            "cutoff_year": cutoff_year,
            "end_year": end_year,
            "zscore_window_years": ZSCORE_WINDOW_YEARS,
            "n_ece_bins": N_ECE_BINS,
            "with_baselines": with_baselines,
            "baseline_seed": baseline_seed if with_baselines else None,
            "ablation_arm": ablation_arm,
            "use_signed_scoring": use_signed_scoring,
            "apply_591_filter": apply_filter,
            "bootstrap_resamples": bootstrap_resamples,
            "bootstrap_seed": bootstrap_seed,
            "strata_indicator_count_threshold": strata_threshold,
        },
        "summary": {
            "n_event_categories": len(per_cat),
            "n_event_categories_with_auc": len(aucs_real),
            "n_predictions": treatment["n_predictions"],
            "mean_auc": mean_auc,
            "median_auc": median_auc,
            "n_auc_above_0_55": n_above_0_55,
            "n_auc_above_0_65": n_above_0_65,
            "ece": ece,
            "decision": decision,
            "decision_rationale": decision_rationale,
        },
        "per_event_category_auc": per_cat,
        "reliability_diagram": reliability,
        # v4 NEW top-level keys
        "stratified_auc": treatment["stratified_auc"],
        "per_event_category_ece": treatment["per_event_category_ece"],
        # v5 NEW (T2 / #666 / Phase 5 v0.2 charter A2): γ-stage transparency
        # artifact — per-threshold cardinality + mean AUC across {3,5,7,10,15}.
        # NOT a decision artifact (the falsification rule v2 evaluates at the
        # N=30 hard floor regardless of which thresholds the table populates).
        "stratum_sensitivity": treatment["stratum_sensitivity"],
        # v4 Step 3 anchor-case battery (regression suite per
        # cascade-anchor-case-battery.json; Kwame's warning: passing != validation)
        "anchor_case_battery": treatment["anchor_case_battery"],
    }

    # v6 NEW (T12 #692): per-cell anomaly_score tensor for Path B's
    # partial-pooling evaluator. Only emitted when --emit-per-cell is set;
    # backward-compat with v5 consumers preserved (key absent in v5-style
    # output). Per docs-specs `ca77505` §3.1 (post-6-seat-Majles amendment
    # 2026-05-15): the response variable for Path B is anomaly_score, not
    # AUC, because ROC-AUC is undefined at single-observation granularity.
    if emit_per_cell and treatment.get("per_cell") is not None:
        output["per_cell"] = treatment["per_cell"]

    # Baselines (#598): when --with-baselines fires, attach the uniform and
    # random-weight evaluation summaries as top-level keys. The treatment-vs-
    # baseline comparison is what tells us whether the EB priors carry signal.
    # Both baseline blocks include n_predictions so the Ihsa-convening
    # sanity check (same pipeline, different weights → same n_predictions)
    # is mechanical, not manual. QA review (MINOR #3, Phase 4 v0.2).
    if baseline_uniform is not None:
        output["baseline_uniform"] = {
            "mean_auc": baseline_uniform["mean_auc"],
            "median_auc": baseline_uniform["median_auc"],
            "ece": baseline_uniform["ece"],
            "n_predictions": baseline_uniform["n_predictions"],
            "n_event_categories_with_auc": baseline_uniform["n_event_categories_with_auc"],
            "n_auc_above_0_55": baseline_uniform["n_auc_above_0_55"],
            "n_auc_above_0_65": baseline_uniform["n_auc_above_0_65"],
            "per_event_category_auc": baseline_uniform["per_event_category_auc"],
            "reliability_diagram": baseline_uniform["reliability_diagram"],
        }
    if baseline_random is not None:
        output["baseline_random"] = {
            "seed": baseline_seed,
            "mean_auc": baseline_random["mean_auc"],
            "median_auc": baseline_random["median_auc"],
            "ece": baseline_random["ece"],
            "n_predictions": baseline_random["n_predictions"],
            "n_event_categories_with_auc": baseline_random["n_event_categories_with_auc"],
            "n_auc_above_0_55": baseline_random["n_auc_above_0_55"],
            "n_auc_above_0_65": baseline_random["n_auc_above_0_65"],
            "per_event_category_auc": baseline_random["per_event_category_auc"],
            "reliability_diagram": baseline_random["reliability_diagram"],
        }

    # v6 NEW (T8 / #672): top-level rule v2 verdict + posterior block +
    # multi-seed baseline + T7 config provenance + pre-CIPS-validation label.
    output["rule_v2_verdict"] = verdict
    output["posterior_update"] = posterior
    if baseline_random_multi_seed:
        output["baseline_random_multi_seed"] = {
            "seeds": list(baseline_seeds) if baseline_seeds else [],
            "per_seed": baseline_random_multi_seed,
            "n_seeds": len(baseline_random_multi_seed),
            "treatment_minus_random_full_set": (
                [
                    float(mean_auc) - float(b["mean_auc"])
                    for b in baseline_random_multi_seed
                    if np.isfinite(b["mean_auc"]) and np.isfinite(mean_auc)
                ] if np.isfinite(mean_auc) else []
            ),
        }
    # v6 NEW (T8 review fix MAJOR #4 polish): emit SHA-256 hashes of the
    # loaded T7 binding configs so the T11 falsification report can audit
    # WHICH config files were in scope. Hashes are computed on the
    # canonical-serialised JSON content (sorted keys) for reproducibility.
    import hashlib
    def _hash_config(cfg: dict | None) -> str | None:
        if cfg is None:
            return None
        return hashlib.sha256(
            json.dumps(cfg, sort_keys=True, allow_nan=False).encode("utf-8")
        ).hexdigest()

    output["t7_config_provenance"] = {
        "canonical_length_config_loaded": canonical_length_config is not None,
        "canonical_length_config_path": str(canonical_length_config_path),
        "canonical_length_config_sha256": _hash_config(canonical_length_config),
        "exclusion_list_loaded": exclusion_list is not None,
        "exclusion_list_size": len(exclusion_list) if exclusion_list else 0,
        "exclusion_list_config_path": str(exclusion_list_config_path),
        "exclusion_list_applied_to_weights_df": (
            rule_v2_evaluation and exclusion_list is not None
        ),
        "falsification_config_loaded": falsification_config is not None,
        "falsification_config_sha256": _hash_config(falsification_config),
        "rule_v2_evaluation_mode": rule_v2_evaluation,
        # v6.5 NEW (T8.5 / Tariq §5.4): transform layer provenance.
        # Records whether the panel was transformed (first_diff / log_diff /
        # pass_through + optional demean) per the canonical_length_config
        # dispatch BEFORE z-scoring. False under D-arm sanity-check mode;
        # True under rule_v2_evaluation. T11 falsification report MUST
        # cite this field to disambiguate raw-panel vs transformed-panel runs.
        "transform_layer_applied": (
            rule_v2_evaluation and canonical_length_config is not None
        ),
    }
    # v6 NEW (T7 §9 / charter A8): pre-CIPS-validation label.
    # Non-strippable until the 2026-06-04 CIPS run completes.
    output["pre_cips_validation_label"] = True
    output["cips_validation_expected_after"] = PRE_CIPS_VALIDATION_LABEL_UNTIL

    # v6 NEW (#679): RFC 8259 compliance — emit `null` instead of `NaN`.
    # Python's json defaults are permissive but jq + JS JSON.parse reject NaN.
    output_path.write_text(
        json.dumps(_nan_to_none(output), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"    wrote validation report → {output_path.name}")

    # Legacy alias: keep phase4-validation.json pointing at the D-arm
    # output so v3 consumers (no --ablation-arm awareness) keep working.
    # For non-D arms, no legacy alias is written.
    if ablation_arm == "D":
        OUTPUT_JSON_LEGACY.write_text(
            json.dumps(_nan_to_none(output), indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        print(f"    wrote legacy alias → {OUTPUT_JSON_LEGACY.name} (D-arm)")

    print("\n=== DECISION ===")
    print(f"  {decision}: {decision_rationale}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--cutoff-year", type=int, default=DEFAULT_CUTOFF_YEAR)
    p.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    p.add_argument("--with-baselines", action="store_true",
                   help="Run uniform-weight and random-weight baselines alongside "
                        "the regular Phase 3 weights. Output JSON gets top-level "
                        "`baseline_uniform` and `baseline_random` keys with the "
                        "same shape as `summary`. This is the comparison the "
                        "post-Phase-4 Ihsa convening uses to decide whether the "
                        "weights carry signal vs the scoring formula being the "
                        "bottleneck (#598). To force a refresh of the baselines, "
                        "delete or rename `weight-matrix.json` and re-bake.")
    p.add_argument("--baseline-seed", type=int, default=DEFAULT_BASELINE_SEED,
                   help=f"Seed for the random-weight baseline (default {DEFAULT_BASELINE_SEED}). "
                        "Fixed for reproducibility.")
    p.add_argument("--ablation-arm", choices=ABLATION_ARMS, default=DEFAULT_ABLATION_ARM,
                   help="Phase 5 v0.1a 4-arm ablation arm. "
                        "A = signed × #591 filter (treatment), "
                        "B = signed × no filter (formula-only), "
                        "C = unsigned × #591 filter (filter-only), "
                        "D = unsigned × no filter (Phase 4 v0.2 baseline, default).")
    p.add_argument("--bootstrap-resamples", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES,
                   help=f"Bootstrap resamples for per-category AUC CI "
                        f"(default {DEFAULT_BOOTSTRAP_RESAMPLES}).")
    p.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED,
                   help=f"Seed for bootstrap resampling (default {DEFAULT_BOOTSTRAP_SEED}). "
                        "Fixed for reproducibility.")
    p.add_argument("--strata-threshold", type=int,
                   default=STRATA_INDICATOR_COUNT_THRESHOLD,
                   help=f"v5 (T2 / #666 / Phase 5 v0.2 charter A2). "
                        f"n_indicators_used cutoff that splits a (country, "
                        f"event_category) cell into the `data_sufficient` vs "
                        f"`thin_coverage` stratum for the `stratified_auc` "
                        f"block (default {STRATA_INDICATOR_COUNT_THRESHOLD}). "
                        f"Used by the γ-stage sensitivity sweep — re-run the "
                        f"script once per threshold in {{3, 5, 7, 10, 15}} to "
                        f"populate the per-threshold table. The `stratum_"
                        f"sensitivity` top-level output (which lists ALL "
                        f"thresholds in {{3, 5, 7, 10, 15}}) is computed in a "
                        f"single pass regardless of this flag — the flag only "
                        f"controls which threshold the *stratified_auc* and "
                        f"*config.strata_indicator_count_threshold* fields "
                        f"reflect.")
    # v6 NEW (T8 / #672): rule v2 evaluation mode + T7 config paths.
    p.add_argument("--rule-v2-evaluation", action="store_true",
                   help="v6 (T8 / #672). When set, the script evaluates "
                        "rule v2 (pre-reg spec §1) and REQUIRES the T7 "
                        "canonical_length + exclusion-list + falsification "
                        "JSON configs to exist. Use when firing T9 (Stage α) "
                        "or any rule-v2-binding run. Leave unset for D-arm "
                        "sanity-check / γ-stage transparency runs.")
    p.add_argument("--canonical-length-config", type=Path,
                   default=CANONICAL_LENGTH_CONFIG_JSON_DEFAULT,
                   help=f"v6 (T7 §4 binding). Path to v0.2-canonical-"
                        f"length.json. Required when --rule-v2-evaluation "
                        f"is set. Default: {CANONICAL_LENGTH_CONFIG_JSON_DEFAULT}.")
    p.add_argument("--exclusion-list-config", type=Path,
                   default=EXCLUSION_LIST_CONFIG_JSON_DEFAULT,
                   help=f"v6 (T7 §5 (b) binding). Path to v0.2-demeaning-"
                        f"insufficient-exclusion.json. Required when "
                        f"--rule-v2-evaluation is set. Default: "
                        f"{EXCLUSION_LIST_CONFIG_JSON_DEFAULT}.")
    p.add_argument("--baseline-seeds", type=int, nargs="+", default=None,
                   help=f"v6 (T8 / #672, Roshani A3 + Kwame bright-line). "
                        f"Multi-seed random-baseline sweep. Default when "
                        f"--with-baselines is set and this flag is not "
                        f"passed: {list(DEFAULT_BASELINE_SEEDS)}. Override "
                        f"only when testing seed-sensitivity in CI.")
    p.add_argument("--emit-per-cell", action="store_true",
                   help="v6 NEW (T12 #692). Emit the per-(country_id, "
                        "event_category) anomaly_score tensor under a "
                        "top-level `per_cell` block in the output JSON. "
                        "Required for Path B's partial-pooling evaluator "
                        "(validate_weight_matrix_bayes.py). Schema "
                        "version bumps to 6 when this flag is set. "
                        "Backward-compatible: omitted → v5-equivalent output.")
    args = p.parse_args()
    main(
        cutoff_year=args.cutoff_year,
        end_year=args.end_year,
        with_baselines=args.with_baselines,
        baseline_seed=args.baseline_seed,
        ablation_arm=args.ablation_arm,
        bootstrap_resamples=args.bootstrap_resamples,
        bootstrap_seed=args.bootstrap_seed,
        strata_threshold=args.strata_threshold,
        # v6 NEW
        baseline_seeds=tuple(args.baseline_seeds) if args.baseline_seeds else None,
        rule_v2_evaluation=args.rule_v2_evaluation,
        canonical_length_config_path=args.canonical_length_config,
        exclusion_list_config_path=args.exclusion_list_config,
        emit_per_cell=args.emit_per_cell,
    )
