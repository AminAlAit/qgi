#!/usr/bin/env python3
"""
compute_indicator_category_weights.py — Per-(indicator × L3 category) posterior
weight matrix for QGI #577.

Design doc: docs/specs/internal/design/per-indicator-l3-weight-matrix.md

Status: SKELETON — awaiting founder + Asas Majles vote before landing on a branch.
        This script is a PROPOSAL, not production code.

Stand-in note
─────────────
Until a post-M1/M2/M3 audit run is available, `lift(i,c)` is approximated as
sigmoid(tfidf_score(i,c)) from recipes-aggregated.json. When --audit-json is
supplied, the script reads real permutation-importance lifts from the auditioner
output and substitutes them for the tfidf stand-in.

Posterior weight formula (from design doc §1):
  w(i,c) = σ( logit(prior(i,c)) + β·lift(i,c) − γ·ubiquity(i) + δ·specificity(i) )
  where σ is logistic sigmoid, logit(p) = log(p/(1-p)).
  β=1.5, γ=1.5, δ=0.8.

Ingredients:
  prior(i,c)    — per-(indicator sector, L1 cluster) causal-mechanism prior (0,1)
  lift(i,c)     — normalised predictive lift per (indicator, category) [0,1]
  ubiquity(i)   — fraction of L3 categories where indicator is in top-15 [0,1]
  specificity(i)— normalised CV of indicator's tfidf across categories [0,1]

Anti-patterns (inherited from audition_indicators.py):
  - BH/FDR multiple-testing correction is HARD VETOED (2026-04-26, founder).
  - Do not auto-promote/demote indicators — weights are inputs, not gates.
  - Do not impute missing tfidf — flag as cold-start.

Usage:
  # Dry run — prints summary stats, writes nothing
  python scripts/compute_indicator_category_weights.py --dry-run

  # Full run — writes JSON + causal-mechanism doc stub
  python scripts/compute_indicator_category_weights.py \\
      --recipes-json qgi-frontend/data/recipes-aggregated.json \\
      --indexes-json qgi-frontend/data/indexes.json \\
      --taxonomy-json qgi-data/events/taxonomy_hierarchy.json \\
      --output-json qgi-data/data/indicator-category-weights.json \\
      --output-doc docs/specs/internal/methodology/indicator-category-weight-justifications.md

  # With real auditioner lift data (post-M2 run)
  python scripts/compute_indicator_category_weights.py \\
      --audit-json results/audition_2026_XX_XX/audit_lift.json \\
      ...
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Constants — match design doc §1
# ---------------------------------------------------------------------------

PIPELINE_VERSION = "V2.0-dev"
SCHEMA_VERSION = 1
THRESHOLD_T = 0.50          # cells above this require causal-mechanism doc

# Linear combination coefficients (design doc §1)
# Prior enters as logit(prior) with an implicit coefficient of 1.0 (Bayesian anchor).
# BETA, GAMMA, DELTA shift the log-odds relative to the prior.
BETA = 1.5    # lift evidence weight
GAMMA = 1.5   # ubiquity penalty
DELTA = 0.8   # specificity reward

# Ubiquity threshold above which an indicator is "ubiquitous"
UBIQUITY_THRESHOLD = 0.80

# Demographic 3 indicator IDs (Population, Life Expectancy, Mortality under-5)
D3_IDS = {2, 4, 14}

# Per-L1 prior for Demographic 3 indicators (design doc §4)
# Keys are L1 letter codes A-H.
D3_L1_PRIOR: dict[str, float] = {
    "A": 0.05,   # Political Power & Regime  (POL) — no causal pathway
    "B": 0.05,   # Conflict & Political Violence (SEC) — no causal pathway
    "C": 0.08,   # State Authority & Governance (GOV/SEC)
    "D": 0.30,   # Economic & Financial Stress (DEV)
    "E": 0.35,   # Social Mobilization & Civil Society (SOC)
    "F": 0.10,   # Diplomatic & Geopolitical Relations (DIP)
    "G": 0.70,   # Humanitarian & Environmental Crisis (HEALTH)
    "H": 0.45,   # Structural & Development Context (STRUCT/DEV)
}

# Default prior for all non-D3 indicators (neutral/uninformative)
DEFAULT_NON_D3_PRIOR = 0.50


# ---------------------------------------------------------------------------
# Core formula — pure function, fully testable
# ---------------------------------------------------------------------------

def sigmoid(x: float) -> float:
    """Logistic sigmoid, numerically stable."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def compute_weight(
    indicator_id: int,
    l3_category: str,  # noqa: ARG001 — kept for audit trail
    l1_code: str,
    ubiquity: float,
    specificity: float,
    lift: float,
    prior: float,
) -> float:
    """
    Compute posterior weight for one (indicator, l3_category) cell.

    All inputs are in [0, 1].  Returns weight in [0, 1].

    Formula (design doc §1):
        w = σ( logit(prior) + β·lift − γ·ubiquity + δ·specificity )

    The logit(prior) term is the Bayesian anchor: it enters with coefficient 1.0
    so that a strong causal prior (e.g. prior=0.05 → logit=-2.94) cannot be
    overcome by lift alone on substrate-confounded indicators.

    Parameters
    ----------
    indicator_id  : numeric indicator ID (for dispatch only; not in formula)
    l3_category   : L3 event category (for audit trail; not in formula)
    l1_code       : L1 taxonomy code A-H (not in formula; used upstream for prior lookup)
    ubiquity      : fraction of L3 categories where indicator is in top-15
    specificity   : normalised CV of indicator's tfidf (per-indicator scalar)
    lift          : normalised predictive lift for this (indicator, category) pair
    prior         : causal-mechanism prior in (0,1) for this (indicator, L1) pair

    Returns
    -------
    float in [0, 1]
    """
    # Clamp prior away from 0/1 to keep logit finite
    p = max(0.001, min(0.999, prior))
    logit_prior = math.log(p / (1.0 - p))
    linear = logit_prior + BETA * lift - GAMMA * ubiquity + DELTA * specificity
    return sigmoid(linear)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_recipes(path: Path) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    return data["recipes"]


def load_indexes(path: Path) -> dict[int, dict]:
    """Returns numeric_id → indicator metadata dict."""
    with open(path) as f:
        raw = json.load(f)
    return {ind["numeric_id"]: ind for ind in raw if "numeric_id" in ind}


def load_taxonomy(path: Path) -> dict[str, str]:
    """Returns l3_category → L1 code (A-H)."""
    with open(path) as f:
        data = json.load(f)
    mapping: dict[str, str] = {}
    for l1 in data["layer1"]:
        l1_code = l1["id"]
        for l2 in l1["layer2"]:
            for l3 in l2["layer3"]:
                mapping[l3] = l1_code
    return mapping


def load_audit_lift(path: Path) -> dict[tuple[int, str], float]:
    """
    Load real permutation-importance lifts from an auditioner output JSON.
    Expected schema: list of {"indicator_id": int, "event_category": str, "lift": float}
    Returns {(indicator_id, l3_category): lift_normalised}
    """
    with open(path) as f:
        rows = json.load(f)
    raw: dict[tuple[int, str], float] = {}
    for row in rows:
        key = (int(row["indicator_id"]), row["event_category"])
        raw[key] = float(row["lift"])
    # Normalise per category to [0,1]
    from collections import defaultdict
    by_cat: dict[str, list[float]] = defaultdict(list)
    for (iid, cat), v in raw.items():
        by_cat[cat].append(v)
    out: dict[tuple[int, str], float] = {}
    for (iid, cat), v in raw.items():
        vmax = max(by_cat[cat]) or 1.0
        out[(iid, cat)] = v / vmax
    return out


# ---------------------------------------------------------------------------
# Per-indicator scalar computation
# ---------------------------------------------------------------------------

def compute_ubiquity(recipes: list[dict]) -> dict[int, float]:
    """
    ubiquity(i) = |{c : i ∈ top-15 fingerprint of c}| / N_categories
    Per-indicator scalar — same value for every category.
    """
    n_cats = len(recipes)
    from collections import defaultdict
    cats_per_indicator: dict[int, set] = defaultdict(set)
    for r in recipes:
        cat = r["event_category"]
        for fp in r.get("indicator_fingerprint", []):
            cats_per_indicator[fp["indicator_id"]].add(cat)
    return {iid: len(cats) / n_cats for iid, cats in cats_per_indicator.items()}


def compute_specificity(recipes: list[dict]) -> dict[int, float]:
    """
    specificity(i) = CV(tfidf_i) / CV_max  (per-indicator scalar, [0,1])
    High CV = indicator's tfidf varies widely across categories (concentrated).
    Low CV = indicator contributes uniformly (substrate effect).
    """
    from collections import defaultdict
    tfidf_by_ind: dict[int, list[float]] = defaultdict(list)
    for r in recipes:
        for fp in r.get("indicator_fingerprint", []):
            tfidf_by_ind[fp["indicator_id"]].append(fp["tfidf_score"])

    cvs: dict[int, float] = {}
    for iid, scores in tfidf_by_ind.items():
        if len(scores) < 2:
            cvs[iid] = 1.0  # single-category indicator is maximally specific
        else:
            arr = np.array(scores, dtype=float)
            mean = arr.mean()
            if mean < 1e-9:
                cvs[iid] = 0.0
            else:
                cvs[iid] = arr.std() / mean

    if not cvs:
        return {}
    cv_max = max(cvs.values()) or 1.0
    return {iid: cv / cv_max for iid, cv in cvs.items()}


def tfidf_to_lift(tfidf: float, cat_max_tfidf: float) -> float:
    """
    Stand-in: convert tfidf_score to a [0,1] lift proxy by normalising per
    category then applying sigmoid to compress extremes.
    """
    if cat_max_tfidf < 1e-9:
        return 0.5
    normalised = min(tfidf / cat_max_tfidf, 1.0)
    return sigmoid(4.0 * (normalised - 0.5))  # sigmoid centred at 0.5


# ---------------------------------------------------------------------------
# Prior assignment
# ---------------------------------------------------------------------------

def get_prior(indicator_id: int, l1_code: str) -> float:
    """
    Return the causal-mechanism prior for (indicator, L1 cluster).
    D3 indicators use the per-L1 table; all others use the neutral default.
    """
    if indicator_id in D3_IDS:
        return D3_L1_PRIOR.get(l1_code, DEFAULT_NON_D3_PRIOR)
    return DEFAULT_NON_D3_PRIOR


# ---------------------------------------------------------------------------
# Matrix computation
# ---------------------------------------------------------------------------

def compute_matrix(
    recipes: list[dict],
    indexes: dict[int, dict],
    l3_to_l1: dict[str, str],
    audit_lift: dict[tuple[int, str], float] | None = None,
) -> list[dict[str, Any]]:
    """
    Compute the full (indicator × L3 category) weight matrix.
    Returns a flat list of cell dicts.
    """
    ubiquity_map = compute_ubiquity(recipes)
    specificity_map = compute_specificity(recipes)

    # Per-category max tfidf for normalisation (stand-in lift)
    cat_max_tfidf: dict[str, float] = {}
    cat_fingerprints: dict[str, list[dict]] = {}
    for r in recipes:
        cat = r["event_category"]
        fp = r.get("indicator_fingerprint", [])
        cat_fingerprints[cat] = fp
        if fp:
            cat_max_tfidf[cat] = max(x["tfidf_score"] for x in fp)
        else:
            cat_max_tfidf[cat] = 1.0

    rows: list[dict[str, Any]] = []
    # Collect all (indicator_id, category) pairs that appear in fingerprints
    for r in recipes:
        cat = r["event_category"]
        l1_code = l3_to_l1.get(cat, "H")  # default H if unknown category

        for fp in r.get("indicator_fingerprint", []):
            iid = fp["indicator_id"]

            ub = ubiquity_map.get(iid, 0.0)
            spec = specificity_map.get(iid, 0.0)
            prior = get_prior(iid, l1_code)

            # Lift: real if available, else tfidf stand-in
            cold_start = False
            if audit_lift and (iid, cat) in audit_lift:
                lift = audit_lift[(iid, cat)]
            elif audit_lift:
                # Indicator exists in recipe but not in audit — cold start
                lift = 0.5
                cold_start = True
            else:
                # No audit supplied — use tfidf stand-in
                lift = tfidf_to_lift(fp["tfidf_score"], cat_max_tfidf.get(cat, 1.0))

            w = compute_weight(
                indicator_id=iid,
                l3_category=cat,
                l1_code=l1_code,
                ubiquity=ub,
                specificity=spec,
                lift=lift,
                prior=prior,
            )

            ind_meta = indexes.get(iid, {})
            rows.append({
                "indicator_id": iid,
                "indicator_name": ind_meta.get("name", f"(unknown {iid})"),
                "indicator_sector": ind_meta.get("sector", "Unknown"),
                "l3_category": cat,
                "l1_code": l1_code,
                "weight": round(w, 6),
                "prior": round(prior, 4),
                "ubiquity": round(ub, 4),
                "specificity": round(spec, 4),
                "lift": round(lift, 4),
                "cold_start": cold_start,
                "above_threshold": w > THRESHOLD_T,
            })

    return rows


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_json(rows: list[dict], output_path: Path) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_T": THRESHOLD_T,
        "n_indicators": len({r["indicator_id"] for r in rows}),
        "n_categories": len({r["l3_category"] for r in rows}),
        "weights": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[write] JSON → {output_path} ({len(rows)} cells)")


def write_doc_stub(
    rows: list[dict],
    output_path: Path,
    l3_to_l1: dict[str, str],
    taxonomy_meta: dict[str, dict],
) -> None:
    """
    Write a markdown stub for all cells above THRESHOLD_T.
    Human fills in the justification + citations.
    """
    above = [r for r in rows if r["above_threshold"]]
    above.sort(key=lambda r: (-r["weight"], r["l3_category"], r["indicator_id"]))

    lines = [
        "# Indicator-Category Weight Justifications",
        "",
        f"Auto-generated {datetime.now(timezone.utc).date()} for weights > T={THRESHOLD_T}.",
        f"**{len(above)} cells require human review.** Fill in each TODO before Phase 4 ships.",
        "Human review order: A/B political categories first (highest credibility risk).",
        "",
        "---",
        "",
    ]
    for r in above:
        l1_code = r["l1_code"]
        l1_label = taxonomy_meta.get(l1_code, {}).get("label", l1_code)
        cold_tag = " **[COLD-START — audit pending]**" if r["cold_start"] else ""
        lines += [
            f"### indicator_id={r['indicator_id']} × {r['l3_category']} "
            f"| weight={r['weight']:.3f}{cold_tag}",
            "",
            f"**Indicator:** {r['indicator_name']} "
            f"(id={r['indicator_id']}, sector={r['indicator_sector']})",
            f"**L3 Category:** {r['l3_category']} (L1: {l1_code} — {l1_label})",
            f"**Weight:** {r['weight']:.4f} | **Prior:** {r['prior']:.3f} "
            f"| **Lift:** {r['lift']:.3f} | **Ubiquity:** {r['ubiquity']:.3f}",
            "",
            "**Proposed causal mechanism:**",
            f"TODO: describe the causal pathway by which `{r['indicator_name']}` "
            f"is expected to change before or during `{r['l3_category']}` events. "
            "Cite at minimum one empirical source or theoretical model.",
            "",
            "**Sources / citations:**",
            "- [ ] TODO",
            "",
            "**Reviewer sign-off:** ___  **Review date:** ___",
            "",
            "---",
            "",
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[write] doc stub → {output_path} ({len(above)} entries)")


# ---------------------------------------------------------------------------
# Dry-run summary
# ---------------------------------------------------------------------------

def print_dry_run_summary(rows: list[dict], l3_to_l1: dict[str, str]) -> None:
    total = len(rows)
    n_above_t = sum(1 for r in rows if r["above_threshold"])
    n_cold = sum(1 for r in rows if r["cold_start"])
    n_indicators = len({r["indicator_id"] for r in rows})
    n_cats = len({r["l3_category"] for r in rows})

    # D3 stats on POL/SEC categories (L1 = A or B)
    d3_pol = [
        r for r in rows
        if r["indicator_id"] in D3_IDS and r["l1_code"] in ("A", "B")
    ]
    d3_health = [
        r for r in rows
        if r["indicator_id"] in D3_IDS and r["l1_code"] == "G"
    ]

    # Specific acceptance checks
    military_coup_d3 = [
        r for r in rows
        if r["indicator_id"] in D3_IDS and r["l3_category"] == "military_coup"
    ]
    exec_power_d3 = [
        r for r in rows
        if r["indicator_id"] in D3_IDS and r["l3_category"] == "executive_power_consolidation"
    ]
    fiscal_top = sorted(
        [r for r in rows if r["l3_category"] == "fiscal_policy_change"],
        key=lambda r: -r["weight"]
    )

    print("=" * 60)
    print("DRY-RUN SUMMARY — indicator-category weight matrix")
    print("=" * 60)
    print(f"  Matrix shape      : {n_indicators} indicators × {n_cats} L3 categories")
    print(f"  Total cells       : {total}")
    print(f"  Cells > T={THRESHOLD_T}      : {n_above_t} "
          f"({100*n_above_t/total:.1f}%)")
    print(f"  Cold-start cells  : {n_cold}")
    print()
    print("  --- Demographic 3 acceptance checks ---")
    print(f"  D3 cells on L1=A/B (POL/SEC): {len(d3_pol)}")
    if d3_pol:
        ws = [r["weight"] for r in d3_pol]
        print(f"    weight range: [{min(ws):.4f}, {max(ws):.4f}]  "
              f"(all should be < 0.10)")
        all_pass = all(w < 0.10 for w in ws)
        print(f"    ALL < 0.10?   {'PASS' if all_pass else 'FAIL'}")
    print()
    print("  D3 on military_coup:")
    for r in military_coup_d3:
        status = "OK (<0.10)" if r["weight"] < 0.10 else "FAIL (>=0.10)"
        print(f"    id={r['indicator_id']:3d} {r['indicator_name'][:35]:<35}"
              f"  w={r['weight']:.4f}  {status}")
    print()
    print("  D3 on executive_power_consolidation:")
    for r in exec_power_d3:
        status = "OK (<0.10)" if r["weight"] < 0.10 else "FAIL (>=0.10)"
        print(f"    id={r['indicator_id']:3d} {r['indicator_name'][:35]:<35}"
              f"  w={r['weight']:.4f}  {status}")
    print()
    print(f"  D3 cells on L1=G (HEALTH): {len(d3_health)}")
    if d3_health:
        ws = [r["weight"] for r in d3_health]
        print(f"    weight range: [{min(ws):.4f}, {max(ws):.4f}]  "
              f"(should be >= 0.50)")
        all_pass = all(w >= 0.50 for w in ws)
        print(f"    ALL >= 0.50?  {'PASS' if all_pass else 'FAIL'}")
    print()
    print("  --- Positive control: fiscal_policy_change top-5 ---")
    for r in fiscal_top[:5]:
        flag = " <-- target near 1.0" if "fisccap" in r["indicator_name"].lower() else ""
        print(f"    id={r['indicator_id']:3d} {r['indicator_name'][:40]:<40}"
              f"  w={r['weight']:.4f}{flag}")
    print()
    print("  --- Ubiquity-penalised indicators ---")
    ub_heavy = sorted(
        {(r["indicator_id"], r["indicator_name"], r["ubiquity"])
         for r in rows if r["ubiquity"] > UBIQUITY_THRESHOLD},
        key=lambda x: -x[2]
    )
    for iid, name, ub in ub_heavy[:8]:
        print(f"    id={iid:3d} {name[:40]:<40}  ubiquity={ub:.3f}")
    print("=" * 60)
    print("  Stand-in mode: lift = sigmoid(tfidf_normalised) — "
          "tfidf proxy used (no audit JSON).")
    print("  Run with --audit-json to use real permutation-importance lifts.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compute per-(indicator × L3 category) posterior weight matrix (#577)."
    )
    repo_root = Path(__file__).resolve().parents[2]
    p.add_argument(
        "--recipes-json",
        type=Path,
        default=repo_root / "qgi-frontend" / "data" / "recipes-aggregated.json",
    )
    p.add_argument(
        "--indexes-json",
        type=Path,
        default=repo_root / "qgi-frontend" / "data" / "indexes.json",
    )
    p.add_argument(
        "--taxonomy-json",
        type=Path,
        default=repo_root / "qgi-data" / "events" / "taxonomy_hierarchy.json",
    )
    p.add_argument(
        "--output-json",
        type=Path,
        default=repo_root / "qgi-data" / "data" / "indicator-category-weights.json",
    )
    p.add_argument(
        "--output-doc",
        type=Path,
        default=repo_root / "docs-specs" / "internal" / "methodology"
                / "indicator-category-weight-justifications.md",
    )
    p.add_argument(
        "--audit-json",
        type=Path,
        default=None,
        help="Path to auditioner output JSON with real lift values. "
             "If omitted, tfidf stand-in is used.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary stats only; do not write any files.",
    )
    p.add_argument(
        "--cold-start-knn",
        action="store_true",
        help="(Not yet implemented) Use KNN borrowing for cold-start indicators.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # --- Load inputs ---
    if not args.recipes_json.exists():
        print(f"ERROR: recipes JSON not found: {args.recipes_json}", file=sys.stderr)
        sys.exit(1)
    if not args.indexes_json.exists():
        print(f"ERROR: indexes JSON not found: {args.indexes_json}", file=sys.stderr)
        sys.exit(1)
    if not args.taxonomy_json.exists():
        print(f"ERROR: taxonomy JSON not found: {args.taxonomy_json}", file=sys.stderr)
        sys.exit(1)

    recipes = load_recipes(args.recipes_json)
    indexes = load_indexes(args.indexes_json)
    l3_to_l1 = load_taxonomy(args.taxonomy_json)

    # Taxonomy metadata for doc stub
    with open(args.taxonomy_json) as f:
        tax_raw = json.load(f)
    taxonomy_meta = {l1["id"]: l1 for l1 in tax_raw["layer1"]}

    audit_lift: dict[tuple[int, str], float] | None = None
    if args.audit_json:
        if not args.audit_json.exists():
            print(f"ERROR: audit JSON not found: {args.audit_json}", file=sys.stderr)
            sys.exit(1)
        audit_lift = load_audit_lift(args.audit_json)
        print(f"[load] audit lift: {len(audit_lift)} cells from {args.audit_json}")
    else:
        print("[info] No --audit-json supplied. Using tfidf stand-in for lift.")

    if args.cold_start_knn:
        print("[warn] --cold-start-knn is not yet implemented; ignoring flag.", file=sys.stderr)

    # --- Compute matrix ---
    rows = compute_matrix(recipes, indexes, l3_to_l1, audit_lift)

    # --- Output ---
    if args.dry_run:
        print_dry_run_summary(rows, l3_to_l1)
    else:
        write_json(rows, args.output_json)
        write_doc_stub(rows, args.output_doc, l3_to_l1, taxonomy_meta)
        print_dry_run_summary(rows, l3_to_l1)
        print(f"\n[done] Wrote {len(rows)} cells to {args.output_json}")


if __name__ == "__main__":
    main()
