#!/usr/bin/env python3
"""
Augment country-risks.json with QGI Risk Score (0-100 percentile rank).

#721 / Majles 2026-05-16 STEP 1 (custom local bake; no pipeline run).

The Majles ratified a bounded buyer-facing score that lives ALONGSIDE
the existing unbounded salience. Spec:
    docs/specs/internal/ops/qgi-risk-score-majles-2026-05-16.md

Step 1 (this script): augment an existing country-risks.json without
re-running the scoring pipeline. Reads existing salience values,
computes the percentile rank across the bake's cohort, writes back the
augmented JSON.

Step 2 (deferred to one-shot pipeline run, see
docs/specs/internal/ops/one-shot-pipeline-checklist.md): fold the
percentile rank emission into `generate_country_risks.py` natively so
each bake produces the field directly.

USAGE
    python augment_country_risks_with_qgi_risk_score.py \\
        --input  qgi-frontend/data/country-risks.json \\
        --output qgi-frontend/data/country-risks.json   # in-place

OUTPUT FIELDS (added per country)
    qgi_risk_score_0_100      int|null   0..100 percentile rank
                                          (null if coverage insufficient)
    qgi_risk_score_ci_low     int|null   95% bootstrap CI lower bound
    qgi_risk_score_ci_high    int|null   95% bootstrap CI upper bound
    coverage_flag             str        "ok" | "insufficient"

OUTPUT FIELDS (added at top level)
    qgi_risk_score_version    str        "v1"
    qgi_risk_score_cohort_n   int        countries in the rank cohort
    qgi_risk_score_method     str        "percentile-rank-of-max-salience"
    qgi_risk_score_baked_at   str        ISO8601 UTC

MAJLES DECISIONS HONORED (verbatim from the synthesis spec)
1. Range: 0-100 integer (8/8 unanimous)
2. Computation: empirical percentile rank — NOT a closed-form Φ transform
   (Roshani + Dmitri argued for statistical honesty; founder ratified)
3. Strict ordinal interpretation — NOT a probability. Code docstrings
   forbid the "% chance" reading.
4. Floors at 0 (never negative). Bake-script writes negative-salience
   countries as 0, but coverage_flag stays "ok" if recipe_count
   threshold is met.
5. Insufficient-data: null (NEVER coerced to 0 or 50). Marcus's veto.
6. Reference distribution: countries in current bake's cohort (all
   156 in this run; founder may later restrict to curated_only via
   --cohort=curated).
7. Bootstrap CI: 1000 bootstrap iterations resampling the cohort
   salience distribution with replacement; 95% percentile interval.
   Step 1 uses country-level resampling (not recipe-level — recipe
   data would require Athena access; deferred to Step 2 native bake).

LIMITATIONS (documented; filed as #721 acceptance follow-ups)
- Step 1 CI is country-cohort-resampling. Step 2 (native bake) will
  switch to recipe-level resampling per the Majles spec.
- min_recipe_count threshold (Majles config-key 5) is INTERPRETED as
  max(recipe_count across top_categories) — country's strongest
  recipe-cohort sample. A country with all-tier-blocks empty or with
  every category's recipe_count < 5 gets coverage_flag="insufficient".
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import random
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_RECIPE_COUNT = 5  # Majles V1.9.1 config key; insufficient-data threshold
BOOTSTRAP_ITERATIONS = 1000
CI_LOWER_PCT = 2.5
CI_UPPER_PCT = 97.5
BOOTSTRAP_SEED = 17  # deterministic — same seed as T12 canary chain

# #728 (2026-05-16) — per-(country, recipe) Risk Score scope.
# Top-4 ML-LOCKed recipes per the 2026-05-15 ml-recipe-stack bake.
# Hardcoded here for Step 1; Step 2 reads from ml-recipe-stack.json
# metadata.top_4_recipes (deferred to keep the script Athena-free).
TOP_4_LOCKED_RECIPES = (
    "civil_war_and_insurgency",
    "multilateral_agreement",
    "elections_and_voting",
    "bilateral_treaty",
)

# #729 / Majles per-recipe Step 1.5 (2026-05-16) — Roshani's veto on small-N
# bootstrap: widen the 95% CI by 1.5× when cohort_n is below this threshold.
# Honest hedge against bootstrap-bias-at-small-N. multilateral_agreement
# (N=58) is the current cohort hitting this gate.
SMALL_COHORT_CI_THRESHOLD = 80
SMALL_COHORT_CI_WIDEN_FACTOR = 1.5

# #729 / Majles per-recipe Step 1.5 — Dmitri's hard gate: a quant treating
# 4 scores as iid signals when they're 0.7 correlated blows up a book.
# Spearman correlation requires ≥ this many countries with valid scores on
# BOTH recipes in a pair to publish a number (else null).
MIN_CORRELATION_PAIRS = 5


# ---------------------------------------------------------------------------
# Per-country max-salience extraction
# ---------------------------------------------------------------------------

def extract_max_salience(country: dict) -> tuple[float | None, int]:
    """Return (max_salience_score, max_recipe_count_across_categories).

    max_salience is the country's strongest signal across all tier windows
    (S/M/L/XL). max_recipe_count is the country's deepest recipe cohort
    (used for the coverage_flag threshold).

    Returns (None, 0) if no top_categories at all.
    """
    max_sal: float | None = None
    max_rc = 0
    tiers = country.get("tiers", {})
    for tier_block in tiers.values():
        for cat in tier_block.get("top_categories", []):
            sal = cat.get("salience_score")
            if sal is None:
                sal = cat.get("z_score")
            if sal is not None and (max_sal is None or sal > max_sal):
                max_sal = sal
            rc = cat.get("recipe_count", 0)
            if rc > max_rc:
                max_rc = rc
    return max_sal, max_rc


# ---------------------------------------------------------------------------
# Per-(country, recipe) salience extraction (#728)
# ---------------------------------------------------------------------------

def extract_per_recipe_salience(country: dict) -> dict[str, tuple[float, int] | None]:
    """Per-recipe salience + recipe_count for the top-4 LOCKed recipes.

    Walks the country's top_categories across all tier windows (S/M/L/XL)
    and picks the MAX salience_score for each top-4 recipe. If a recipe
    has multiple entries across tier blocks (rare but possible), keeps
    the strongest.

    Returns: {recipe_id: (salience, recipe_count)} for recipes the country
    has top_category data for; recipe_id missing if the country has no
    top_category match. Salience is clamped at 0 (Majles negative-clamp
    rule); recipe_count is the recipe-cohort depth for coverage gating.
    """
    out: dict[str, tuple[float, int] | None] = {r: None for r in TOP_4_LOCKED_RECIPES}
    tiers = country.get("tiers", {})
    for tier_block in tiers.values():
        for cat in tier_block.get("top_categories", []):
            recipe_id = cat.get("category")
            if recipe_id not in TOP_4_LOCKED_RECIPES:
                continue
            sal = cat.get("salience_score")
            if sal is None:
                sal = cat.get("z_score")
            if sal is None:
                continue
            sal = max(0.0, sal)  # Majles negative-clamp rule
            rc = cat.get("recipe_count", 0)
            existing = out[recipe_id]
            if existing is None or sal > existing[0]:
                out[recipe_id] = (sal, rc)
    return out


# ---------------------------------------------------------------------------
# Percentile rank + bootstrap CI
# ---------------------------------------------------------------------------

def percentile_rank(value: float, cohort: list[float]) -> int:
    """Empirical percentile rank of `value` in `cohort`.

    Uses the "fraction strictly below + half-tied" convention to handle
    duplicate salience values fairly. Result rounded to int in [0, 100].
    """
    if not cohort:
        return 0
    n_below = sum(1 for v in cohort if v < value)
    n_tied = sum(1 for v in cohort if v == value)
    rank = (n_below + 0.5 * n_tied) / len(cohort)
    pct = max(0, min(100, round(rank * 100)))
    return pct


def widen_ci_for_small_cohort(
    score: int,
    ci_low: int,
    ci_high: int,
    cohort_n: int,
    threshold: int = SMALL_COHORT_CI_THRESHOLD,
    factor: float = SMALL_COHORT_CI_WIDEN_FACTOR,
) -> tuple[int, int]:
    """#729 — Roshani's small-cohort CI widening (2026-05-16).

    Widens the bootstrap 95% CI by `factor` (default 1.5×) when the cohort
    is small (default N < 80). Bootstrap CI at small N tends to be over-
    confident (bias toward narrow intervals on resampling), so widening is
    the honest hedge documented in the Majles spec.

    Clamps to [0, 100] after widening to preserve the 0-100 contract.
    """
    if cohort_n >= threshold:
        return ci_low, ci_high
    new_low = max(0, round(score - factor * (score - ci_low)))
    new_high = min(100, round(score + factor * (ci_high - score)))
    return new_low, new_high


def compute_ranks(values: list[float]) -> list[float]:
    """Fractional ranks (mid-rank for ties), the standard Spearman convention."""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-indexed, mid-rank
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def spearman_correlation(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation. Returns None if degenerate.

    Computes Pearson correlation of the fractional ranks of x and y. Returns
    None for empty inputs, mismatched lengths, or zero-variance ranks.
    """
    if len(x) != len(y) or len(x) < 2:
        return None
    rx = compute_ranks(x)
    ry = compute_ranks(y)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def bootstrap_ci(
    value: float,
    cohort: list[float],
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[int, int]:
    """Bootstrap 95% CI on percentile rank.

    Resamples the cohort with replacement `iterations` times; for each
    bootstrap sample, recomputes the percentile rank of `value` against
    the resampled cohort; returns the 2.5th and 97.5th percentiles of
    the bootstrap rank distribution.

    Deterministic via fixed seed (BOOTSTRAP_SEED).
    """
    if len(cohort) < 2:
        return 0, 100
    rng = random.Random(seed)
    n = len(cohort)
    ranks: list[int] = []
    for _ in range(iterations):
        resample = [cohort[rng.randint(0, n - 1)] for _ in range(n)]
        ranks.append(percentile_rank(value, resample))
    ranks.sort()
    lower_idx = max(0, int(math.floor(iterations * CI_LOWER_PCT / 100)))
    upper_idx = min(iterations - 1, int(math.ceil(iterations * CI_UPPER_PCT / 100)))
    return ranks[lower_idx], ranks[upper_idx]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Path to existing country-risks.json")
    ap.add_argument("--output", required=True, help="Path to write augmented JSON")
    ap.add_argument(
        "--cohort",
        choices=["all", "curated"],
        default="all",
        help="Rank cohort: 'all' (default) or 'curated' (curated=True only)",
    )
    ap.add_argument(
        "--ml-recipe-stack",
        default=None,
        help="Path to ml-recipe-stack.json (for Step 1.5 calibration carry — recipe ECE, LOCO AUC, advisory flag). Optional; per-recipe entries omit calibration fields when absent.",
    )
    args = ap.parse_args()

    # #729 Step 1.5 — load ML recipe-stack for calibration carry per Kwame's veto.
    ml_recipe_calibration: dict[str, dict] = {}
    if args.ml_recipe_stack:
        stack_path = pathlib.Path(args.ml_recipe_stack)
        if stack_path.exists():
            with open(stack_path, "r", encoding="utf-8") as f:
                ml_stack = json.load(f)
            for r in ml_stack.get("recipes", []):
                rid = r.get("recipe_id")
                if rid in TOP_4_LOCKED_RECIPES:
                    ml_recipe_calibration[rid] = {
                        "recipe_ece": r.get("ece_overall"),
                        "recipe_loco_auc": r.get("loco_auc"),
                        "recipe_f_rule_advisory_flag": bool(r.get("advisory_only_flag", False)),
                        "recipe_f_rule_anomaly_flag": bool(r.get("f_rule_anomaly_flag", False)),
                    }
            print(f"Loaded ML calibration for {len(ml_recipe_calibration)} recipes from {stack_path}")
        else:
            print(f"WARNING: --ml-recipe-stack path not found: {stack_path}; calibration carry skipped", file=sys.stderr)

    in_path = pathlib.Path(args.input)
    out_path = pathlib.Path(args.output)
    if not in_path.exists():
        print(f"ERROR: input file not found: {in_path}", file=sys.stderr)
        return 1

    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    countries: dict[str, dict] = data["countries"]
    print(f"Loaded {len(countries)} countries from {in_path}")
    print(f"Bake version: {data.get('version', 'n/a')} · generated_at: {data.get('generated_at', 'n/a')}")

    # ---------- Pass 1: extract max salience + coverage flag per country -----
    salience_by_id: dict[str, float] = {}
    coverage_flag_by_id: dict[str, str] = {}
    for cid, c in countries.items():
        max_sal, max_rc = extract_max_salience(c)
        if max_sal is None or max_rc < MIN_RECIPE_COUNT:
            coverage_flag_by_id[cid] = "insufficient"
            continue
        # Apply the Majles "negative salience clamps to 0" rule.
        salience_by_id[cid] = max(0.0, max_sal)
        coverage_flag_by_id[cid] = "ok"

    # ---------- Pass 2: build the rank cohort -------------------------------
    if args.cohort == "curated":
        cohort_ids = [cid for cid in salience_by_id if countries[cid].get("curated")]
    else:
        cohort_ids = list(salience_by_id.keys())
    cohort_salience = [salience_by_id[cid] for cid in cohort_ids]
    cohort_n = len(cohort_salience)
    print(f"Cohort: {args.cohort} (N={cohort_n}); insufficient: {sum(1 for v in coverage_flag_by_id.values() if v == 'insufficient')}")

    # ---------- Pass 3: compute country-level risk score + CI ---------------
    for cid, c in countries.items():
        flag = coverage_flag_by_id[cid]
        if flag == "insufficient":
            c["qgi_risk_score_0_100"] = None
            c["qgi_risk_score_ci_low"] = None
            c["qgi_risk_score_ci_high"] = None
            c["coverage_flag"] = "insufficient"
            continue
        sal = salience_by_id[cid]
        score = percentile_rank(sal, cohort_salience)
        ci_low, ci_high = bootstrap_ci(sal, cohort_salience)
        c["qgi_risk_score_0_100"] = score
        c["qgi_risk_score_ci_low"] = ci_low
        c["qgi_risk_score_ci_high"] = ci_high
        c["coverage_flag"] = "ok"

    # ---------- Pass 3.5: per-(country, recipe) Risk Score (#728) -----------
    # For each top-4 LOCKed recipe, build a cohort of countries that have
    # the recipe in their top_categories with recipe_count >= MIN_RECIPE_COUNT,
    # then percentile-rank each country's salience against that recipe-specific
    # cohort. Countries without the recipe in top_categories get null entries.
    per_recipe_salience: dict[str, dict[str, tuple[float, int]]] = {
        r: {} for r in TOP_4_LOCKED_RECIPES
    }
    for cid, c in countries.items():
        per_recipe = extract_per_recipe_salience(c)
        for recipe_id, entry in per_recipe.items():
            if entry is None:
                continue
            sal, rc = entry
            if rc < MIN_RECIPE_COUNT:
                continue  # insufficient recipe-cohort depth for this country
            per_recipe_salience[recipe_id][cid] = (sal, rc)

    # Per-recipe cohort = countries with sufficient coverage on THAT recipe,
    # filtered by the same --cohort arg as the country-level pass.
    per_recipe_cohort_n: dict[str, int] = {}
    for recipe_id in TOP_4_LOCKED_RECIPES:
        recipe_cohort_ids = list(per_recipe_salience[recipe_id].keys())
        if args.cohort == "curated":
            recipe_cohort_ids = [
                cid for cid in recipe_cohort_ids if countries[cid].get("curated")
            ]
        recipe_cohort = [per_recipe_salience[recipe_id][cid][0] for cid in recipe_cohort_ids]
        per_recipe_cohort_n[recipe_id] = len(recipe_cohort)
        # Persist the cohort itself for the ranking step
        per_recipe_salience[recipe_id]["__cohort__"] = recipe_cohort  # type: ignore[assignment]

    # Per-country emit: a `qgi_risk_score_by_recipe` block keyed by recipe_id
    # with score/ci_low/ci_high/coverage_flag per Majles spec parity.
    # #729 Step 1.5 enrichments applied per-entry:
    #   - Roshani's small-N CI widening (1.5× when cohort < 80)
    #   - Kwame's calibration carry (recipe_ece, recipe_loco_auc, advisory flag)
    #   - cohort_n_recipe surfaced per-entry (Roshani's veto — must be glanceable
    #     beside the score, not just hover-only)
    per_recipe_score_by_country: dict[str, dict[str, int]] = {
        r: {} for r in TOP_4_LOCKED_RECIPES
    }
    for cid, c in countries.items():
        by_recipe: dict[str, dict | None] = {}
        for recipe_id in TOP_4_LOCKED_RECIPES:
            cohort_for_recipe = per_recipe_salience[recipe_id].get("__cohort__", [])
            entry = per_recipe_salience[recipe_id].get(cid)
            if entry is None or not cohort_for_recipe:
                by_recipe[recipe_id] = None
                continue
            sal, _rc = entry
            r_score = percentile_rank(sal, cohort_for_recipe)
            r_ci_low, r_ci_high = bootstrap_ci(sal, cohort_for_recipe)
            # #729 Step 1.5 — Roshani's small-N CI widening
            r_ci_low, r_ci_high = widen_ci_for_small_cohort(
                r_score, r_ci_low, r_ci_high, per_recipe_cohort_n[recipe_id]
            )
            entry_emit: dict = {
                "score": r_score,
                "ci_low": r_ci_low,
                "ci_high": r_ci_high,
                "coverage_flag": "ok",
                # #729 Step 1.5 — Roshani's per-tile cohort_n surfacing
                "cohort_n_recipe": per_recipe_cohort_n[recipe_id],
            }
            # #729 Step 1.5 — Kwame's calibration carry (only if loaded)
            calibration = ml_recipe_calibration.get(recipe_id)
            if calibration is not None:
                entry_emit.update(calibration)
            by_recipe[recipe_id] = entry_emit
            # Stash for the correlation matrix pass below
            per_recipe_score_by_country[recipe_id][cid] = r_score
        c["qgi_risk_score_by_recipe"] = by_recipe

    # ---------- Pass 3.6: recipe-recipe Spearman correlation matrix (#729) --
    # Dmitri's hard gate: a quant treating 4 scores as iid signals when they
    # share regime-stress factors blows up a book. Publish the 4×4 Spearman
    # matrix so portfolio decisions can residualize correctly.
    #
    # Computed over countries with VALID scores on BOTH recipes in each pair
    # (pairwise complete observations). Self-correlation = 1.0; cell = null
    # when fewer than MIN_CORRELATION_PAIRS shared countries.
    correlation_matrix: dict[str, dict[str, float | None]] = {}
    for ra in TOP_4_LOCKED_RECIPES:
        correlation_matrix[ra] = {}
        for rb in TOP_4_LOCKED_RECIPES:
            if ra == rb:
                correlation_matrix[ra][rb] = 1.0
                continue
            shared = set(per_recipe_score_by_country[ra].keys()) & set(
                per_recipe_score_by_country[rb].keys()
            )
            if len(shared) < MIN_CORRELATION_PAIRS:
                correlation_matrix[ra][rb] = None
                continue
            xs = [per_recipe_score_by_country[ra][cid] for cid in shared]
            ys = [per_recipe_score_by_country[rb][cid] for cid in shared]
            corr = spearman_correlation(xs, ys)
            correlation_matrix[ra][rb] = round(corr, 3) if corr is not None else None

    # ---------- Pass 4: top-level metadata ----------------------------------
    data["qgi_risk_score_version"] = "v3"  # #729 bump: Step 1.5 enrichments
    data["qgi_risk_score_cohort_n"] = cohort_n
    data["qgi_risk_score_method"] = "percentile-rank-of-max-salience"
    data["qgi_risk_score_baked_at"] = datetime.now(timezone.utc).isoformat()
    # #728: per-recipe cohort sizes (one entry per top-4 LOCKed recipe).
    data["qgi_risk_score_per_recipe_cohort_n"] = per_recipe_cohort_n
    data["qgi_risk_score_per_recipe_recipes"] = list(TOP_4_LOCKED_RECIPES)
    # #729 Step 1.5 — Dmitri's correlation matrix
    data["qgi_risk_score_per_recipe_correlation_matrix"] = correlation_matrix
    data["qgi_risk_score_per_recipe_min_pairs"] = MIN_CORRELATION_PAIRS
    data["qgi_risk_score_small_cohort_ci_threshold"] = SMALL_COHORT_CI_THRESHOLD
    data["qgi_risk_score_small_cohort_ci_widen_factor"] = SMALL_COHORT_CI_WIDEN_FACTOR

    # ---------- Pass 5: write back ------------------------------------------
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2 if os.environ.get("QGI_PRETTY") else None)
    print(f"Augmented JSON written to {out_path}")

    # ---------- Sanity report ------------------------------------------------
    scores = [c.get("qgi_risk_score_0_100") for c in countries.values()]
    scored = [s for s in scores if s is not None]
    if scored:
        print(f"Country-level score distribution (n={len(scored)}):")
        print(f"  min: {min(scored)} · max: {max(scored)} · median: {sorted(scored)[len(scored)//2]}")
        print(f"  >= 80: {sum(1 for s in scored if s >= 80)} countries")
        print(f"  50-79: {sum(1 for s in scored if 50 <= s < 80)} countries")
        print(f"  20-49: {sum(1 for s in scored if 20 <= s < 50)} countries")
        print(f"  <  20: {sum(1 for s in scored if s < 20)} countries")
    # #728: per-recipe sanity report
    print()
    print("Per-recipe cohort sizes:")
    for recipe_id, n in per_recipe_cohort_n.items():
        widened = "(CI widened 1.5×)" if n < SMALL_COHORT_CI_THRESHOLD else ""
        print(f"  {recipe_id}: N={n} {widened}")
    # #729 Step 1.5 sanity report
    print()
    print("Recipe-recipe Spearman correlation matrix:")
    print(f"  {'':<28}" + " ".join(f"{r[:8]:>8}" for r in TOP_4_LOCKED_RECIPES))
    for ra in TOP_4_LOCKED_RECIPES:
        row = "  " + f"{ra[:28]:<28}"
        for rb in TOP_4_LOCKED_RECIPES:
            cell = correlation_matrix[ra][rb]
            row += f" {cell:>8.3f}" if cell is not None else f" {'—':>8}"
        print(row)
    if ml_recipe_calibration:
        print()
        print(f"Calibration metrics carried for {len(ml_recipe_calibration)} recipes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
