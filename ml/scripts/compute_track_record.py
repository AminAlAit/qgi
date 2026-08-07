"""Track-record at a score level — TE capability #1.

Per te-new-capabilities-spec.md §#1 (locked 2026-05-24, chat QGI-R&D | 002).

Answers: "When the model outputs a high score, how often was the event actually
realized, OUT OF FOLD?" — the honest stand-in for the calibrated probability QGI
cannot ship.

## Method

1. Reproduce the walk's LOCO out-of-fold predictions using the same function as
   compute_venn_abers_odds.py (reproduce_oof_predictions). Inputs: walk summary,
   scores file (for eval_year), panel dir, cohort sidecar, seed 12345.

2. Bin the OOF predicted scores into PRE-REGISTERED bins (fixed in spec before
   seeing results, §2.5 discipline):
       [0.0, 0.5), [0.5, 0.7), [0.7, 0.85), [0.85, 0.95), [0.95, 1.0]

3. Per bin: n, n_positive, ppv = n_positive/n, Wilson 95% CI (implemented below
   without heavy dependencies), flag, suppressed.

4. Report overall baseline rate = n_pos / n_total.

## Honesty gate (binding — enforced in code and artifact)

- STRICTLY out-of-fold (LOCO). No in-sample predictions.
- Suppress any bin with n < 5: set suppressed=True, flag=INSUFFICIENT_DATA.
  Still report ppv WITH its CI — never a bare point.
- NEVER label ppv as "probability". It is the "frequency of realized events among
  similarly-scoring country-years, out of fold." (M8-R5: discrimination layer
  track record, not calibration.)
- No FDR (single descriptive curve, not a multiple-comparison screen).

## Output

    track-record-{recipe_id}-{eval_year}.json

    Top-level keys: recipe_id, eval_year, computed_at_utc, seed_used,
    oof {n_samples, n_pos, n_neg, auc},
    bins [{score_range, n, n_positive, ppv, wilson_lo, wilson_hi, suppressed, flag}],
    baseline_rate, binding_provenance, m8_r5_note.

Usage:
    python scripts/compute_track_record.py \\
        --recipe-id foreign_intervention \\
        --walk-summary /c/tmp/.../f-ml-1-poc-summary.json \\
        --scores-file qgi-data/reference/recipe-similarity-scores-foreign_intervention-2021.json \\
        --panel-dir qgi-ml/data/parquet_panels \\
        --cohort-sidecar qgi-data/reference/cohort-assignments.json \\
        --output-dir qgi-data/reference/ \\
        --seed 12345
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
# Path setup — mirrors compute_venn_abers_odds.py
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import compute_venn_abers_odds as _vao  # noqa: E402 — for reproduce_oof_predictions

REPO_ROOT = SCRIPTS_DIR.parent

# ---------------------------------------------------------------------------
# Pre-registered bins (FIXED before seeing results — spec §2.5 discipline)
# These bins are locked in te-new-capabilities-spec.md §#1.
# DO NOT tune to results. Any change requires a new pre-registration.
# ---------------------------------------------------------------------------

BINS: list[tuple[float, float]] = [
    (0.0,  0.5),
    (0.5,  0.7),
    (0.7,  0.85),
    (0.85, 0.95),
    (0.95, 1.0),
]

# Minimum bin n to report without suppression flag
MIN_BIN_N = 5

# Wilson 95% z-score
_WILSON_Z_95 = 1.96

# ---------------------------------------------------------------------------
# Wilson 95% confidence interval — pure python, no heavy deps
# ---------------------------------------------------------------------------


def wilson_ci(n_pos: int, n: int, z: float = _WILSON_Z_95) -> tuple[float, float]:
    """Compute Wilson score 95% confidence interval for a proportion.

    The Wilson interval is preferred over the Wald interval for small n and
    extreme proportions (0/n, n/n) because it remains within [0, 1].

    Formula (Wilson 1927):
        center = (p_hat + z²/(2n)) / (1 + z²/n)
        half_width = (z / (1 + z²/n)) * sqrt(p_hat*(1-p_hat)/n + z²/(4n²))
        lo = center - half_width  (clipped to 0)
        hi = center + half_width  (clipped to 1)

    Parameters
    ----------
    n_pos : number of successes (positives)
    n     : total count
    z     : z-score for the desired confidence level (default 1.96 for 95%)

    Returns
    -------
    (lo, hi) : Wilson confidence interval, both in [0, 1], lo <= hi.
    Special case: n=0 → (0.0, 0.0).
    """
    if n == 0:
        return 0.0, 0.0

    p_hat = float(n_pos) / float(n)
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denominator
    half_width = (z / denominator) * math.sqrt(
        p_hat * (1.0 - p_hat) / n + z2 / (4.0 * n * n)
    )
    lo = max(0.0, center - half_width)
    hi = min(1.0, center + half_width)
    return float(lo), float(hi)


# ---------------------------------------------------------------------------
# Bin OOF predictions — core logic
# ---------------------------------------------------------------------------


def bin_oof_predictions(
    probs: np.ndarray,
    labels: np.ndarray,
) -> dict[str, Any]:
    """Bin OOF predicted scores into pre-registered bins and compute per-bin stats.

    STRICTLY out-of-fold predictions only. Never call with in-sample predictions.

    Parameters
    ----------
    probs  : (N,) array of OOF predicted probabilities/scores in [0, 1]
    labels : (N,) array of binary labels (0/1)

    Returns
    -------
    dict with:
        bins         : list of per-bin dicts (score_range, n, n_positive, ppv,
                       wilson_lo, wilson_hi, suppressed, flag)
        baseline_rate: overall n_pos / n_total
        n_total      : total number of OOF samples
        n_positive   : total number of positive OOF samples
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=int)
    n_total = int(len(probs))
    n_positive = int((labels == 1).sum())

    bins_out = []
    for (lo, hi) in BINS:
        # Assign: left-closed, right-open for all bins except the last.
        # The last bin [0.95, 1.0] is right-closed (includes 1.0).
        is_last = (hi == 1.0)
        if is_last:
            mask = (probs >= lo) & (probs <= hi)
        else:
            mask = (probs >= lo) & (probs < hi)

        bin_n = int(mask.sum())
        bin_n_pos = int(labels[mask].sum())
        ppv = float(bin_n_pos) / float(bin_n) if bin_n > 0 else float("nan")
        wilson_lo, wilson_hi = wilson_ci(bin_n_pos, bin_n, z=_WILSON_Z_95)

        suppressed = bin_n < MIN_BIN_N
        flag = "INSUFFICIENT_DATA" if suppressed else None

        bins_out.append({
            "score_range": f"[{lo}, {hi}{')'  if not is_last else ']'}",
            "n": bin_n,
            "n_positive": bin_n_pos,
            "ppv": round(ppv, 6) if not math.isnan(ppv) else None,
            "wilson_lo": round(wilson_lo, 6),
            "wilson_hi": round(wilson_hi, 6),
            "suppressed": suppressed,
            "flag": flag,
        })

    baseline_rate = float(n_positive) / float(n_total) if n_total > 0 else float("nan")

    return {
        "bins": bins_out,
        "baseline_rate": round(baseline_rate, 6),
        "n_total": n_total,
        "n_positive": n_positive,
    }


# ---------------------------------------------------------------------------
# Top-level artifact builder
# ---------------------------------------------------------------------------


def compute_track_record_from_oof(
    probs: np.ndarray,
    labels: np.ndarray,
    recipe_id: str,
    eval_year: int,
    seed: int,
    auc: float,
) -> dict[str, Any]:
    """Build the full track-record artifact from OOF predictions.

    Parameters
    ----------
    probs      : (N,) OOF predicted probabilities/scores
    labels     : (N,) binary labels
    recipe_id  : recipe identifier
    eval_year  : evaluation year
    seed       : random seed used in OOF reproduction
    auc        : reproduced LOCO AUC (passed in to avoid recomputation)

    Returns
    -------
    Dict matching the artifact schema from the spec.
    """
    binned = bin_oof_predictions(probs, labels)
    n_neg = binned["n_total"] - binned["n_positive"]

    return {
        "recipe_id": recipe_id,
        "eval_year": eval_year,
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed_used": seed,
        "oof": {
            "n_samples": binned["n_total"],
            "n_pos": binned["n_positive"],
            "n_neg": n_neg,
            "auc": round(float(auc), 6),
        },
        "bins": binned["bins"],
        "baseline_rate": binned["baseline_rate"],
        "binding_provenance": (
            "te-new-capabilities-spec.md §#1 (locked 2026-05-24, chat QGI-R&D | 002). "
            "Bins pre-registered before results: [0,0.5), [0.5,0.7), [0.7,0.85), "
            "[0.85,0.95), [0.95,1.0]. Suppression at n<5. No FDR."
        ),
        "m8_r5_note": (
            "M8-R5 BINDING: frequency of realized events among similarly-scoring "
            "country-years, OUT OF FOLD. This is the discrimination layer's track record, "
            "NOT a calibrated probability. ppv = n_positive / n per bin (OOF only). "
            "Wilson 95% CI reported; suppressed bins (n<5) flagged INSUFFICIENT_DATA. "
            "Never label ppv as 'probability'."
        ),
        "sampling_disclosure": (
            "The OOF set is built by the walk's 1:3 positive:negative LOCO sampling, "
            "NOT a prevalence-matched cohort. Absolute PPV figures reflect this 1:3 "
            "construction and must NOT be read as a real-world hit rate. They are "
            "comparative (high bins vs low bins vs the in-sample baseline_rate, which "
            "is itself the 1:3 base). Prevalence-matched track-record is a Stage-B "
            "enrichment (score more negatives OOF) — deferred (#110)."
        ),
    }


# ---------------------------------------------------------------------------
# Main + CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe-id", required=True,
                        help="Recipe ID (e.g., foreign_intervention).")
    parser.add_argument("--walk-summary", type=Path, required=True,
                        help="Path to walk's f-ml-1-poc-summary.json.")
    parser.add_argument("--scores-file", type=Path, required=True,
                        help="Path to recipe-similarity-scores-{recipe}-{year}.json.")
    parser.add_argument("--panel-dir", type=Path,
                        default=REPO_ROOT / "data" / "parquet_panels",
                        help="Directory containing per-indicator parquet panels.")
    parser.add_argument("--cohort-sidecar", type=Path,
                        default=REPO_ROOT.parent / "qgi-data" / "reference" / "cohort-assignments.json",
                        help="Path to cohort-assignments.json.")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Output directory for track-record-*.json.")
    parser.add_argument("--seed", type=int, default=12345,
                        help="Random seed. Must match walk seed for OOF reproduction.")
    return parser


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load walk summary
    with open(args.walk_summary, encoding="utf-8") as f:
        walk_summary = json.load(f)
    assert walk_summary["recipe_id"] == args.recipe_id, (
        f"Walk summary recipe_id {walk_summary['recipe_id']!r} != requested {args.recipe_id!r}"
    )

    # Load scores file to extract eval_year
    with open(args.scores_file, encoding="utf-8") as f:
        scores_data = json.load(f)
    eval_year = int(scores_data["evaluation_year"])

    # Load cohort assignments
    with open(args.cohort_sidecar, encoding="utf-8") as f:
        cohort_payload = json.load(f)
    cohort_assignments = cohort_payload["assignments"]

    print(f"Recipe: {args.recipe_id}, eval_year: {eval_year}")
    print(f"Reproducing OOF predictions (seed={args.seed})...")

    # Reproduce OOF predictions (reuses compute_venn_abers_odds logic)
    oof = _vao.reproduce_oof_predictions(
        walk_summary=walk_summary,
        cohort_assignments=cohort_assignments,
        panel_dir=args.panel_dir,
        seed=args.seed,
    )

    print(
        f"  OOF: n={oof['n_samples']}, n_pos={oof['n_positives']}, "
        f"n_neg={oof['n_negatives']}, global_auc={oof['global_auc']:.4f}"
    )

    # OOF-fidelity self-check (mirrors compute_venn_abers_odds.py)
    stored_auc = walk_summary.get("global_loco", {}).get("auc")
    if stored_auc is not None:
        auc_delta = abs(float(oof["global_auc"]) - float(stored_auc))
        if auc_delta > 0.005:
            print(
                f"  WARNING: reproduced global_auc={oof['global_auc']:.4f} deviates "
                f"{auc_delta:.4f} from walk's stored {float(stored_auc):.4f} (> 0.005). "
                f"OOF reproduction may be unfaithful."
            )
        else:
            print(f"  OOF-fidelity self-check PASSED (|delta|={auc_delta:.5f} <= 0.005).")

    # Build artifact
    artifact = compute_track_record_from_oof(
        probs=oof["probs"],
        labels=oof["labels"],
        recipe_id=args.recipe_id,
        eval_year=eval_year,
        seed=args.seed,
        auc=oof["global_auc"],
    )

    # Write output
    out_path = args.output_dir / f"track-record-{args.recipe_id}-{eval_year}.json"
    out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_path}")

    # Print per-bin summary table
    print("\n=== TRACK RECORD PER BIN ===")
    print(f"{'Score range':<18} {'n':>6} {'n_pos':>6} {'ppv':>8} {'CI 95%':>20} {'suppressed':>10}")
    print("-" * 80)
    for b in artifact["bins"]:
        ppv_str = f"{b['ppv']:.3f}" if b["ppv"] is not None else "N/A"
        ci_str = f"[{b['wilson_lo']:.3f}, {b['wilson_hi']:.3f}]"
        sup_str = f"{'YES ('+b['flag']+')' if b['suppressed'] else 'no'}"
        print(
            f"{b['score_range']:<18} {b['n']:>6} {b['n_positive']:>6} "
            f"{ppv_str:>8} {ci_str:>20} {sup_str:>10}"
        )
    print(f"\nBaseline rate (overall): {artifact['baseline_rate']:.4f}")
    print(f"Reproduced OOF AUC: {artifact['oof']['auc']:.4f}")
    print(f"(Stored walk AUC: {stored_auc:.4f})" if stored_auc else "")

    return 0


if __name__ == "__main__":
    sys.exit(_main())
