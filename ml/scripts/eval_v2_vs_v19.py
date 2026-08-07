#!/usr/bin/env python3
"""
V2.0-vs-V1.9.1 evaluation harness — #463 Part C.

Per the 2026-04-25 Majles consult, Kwame's vote on Decision 1 was conditional
on "is V2.0 better than V1.9.1?" being answered with a clear metric. This
script computes the answer.

The decision rule (locked, per design doc
docs/specs/internal/design/recipe-scoring-architecture.md):

  V2.0 must be better on at least one of {precision-at-K, calibration}
  AND not worse on persistence margin.

If the rule fails, the SRE gate (#466) blocks the V2.0 frontend cutover
and we revisit calibration / fingerprint composition.

Usage:
    # Once #463 Part A v0.2 + Part B (calibration) ship, the V2.0 column
    # in country_recipe_scores will be populated and this script reads it
    # via Athena:
    python eval_v2_vs_v19.py --bucket qgi-data-lake-771606957899 \\
        --baseline-json ../results/backtest_results.json \\
        --output-dir ../results/v2_eval_$(date +%Y_%m_%d)/

    # Currently runs in DESIGN-VALIDATION mode without --athena-bucket: just
    # computes V1.9.1 metrics from the cached backtest output and emits the
    # report skeleton with V2.0 columns marked PENDING.
    python eval_v2_vs_v19.py \\
        --baseline-json ../results/backtest_results.json \\
        --output-dir ../results/v2_eval_skeleton/

What this script computes for V1.9.1 + V2.0:
  - Precision-at-K for K in {10, 50, 100}
  - Recall at the same K values
  - Brier score (mean((y_pred - y_true)^2))
  - Margin-over-persistence (delta vs the naive "predict if event in last 5yr"
    baseline that V1.9 backtests use)

Outputs:
  - results/{output-dir}/eval_report.md — narrative table + decision rule
  - results/{output-dir}/raw_metrics.json — programmatic access for SRE
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Decision rule per design doc.
# ---------------------------------------------------------------------------
DECISION_RULE = (
    "V2.0 must be BETTER on at least one of {precision-at-K, calibration} "
    "AND NOT WORSE on persistence margin."
)
PRECISION_AT_K_VALUES = (10, 50, 100)


# ---------------------------------------------------------------------------
# Metric calculations — the per-pair / per-(country, recipe) variants.
# Used when re-scoring the V1.9 backtest set against V2.0 scores.
# Aggregate variants (read from backtest_results.json) used for V1.9.1.
# ---------------------------------------------------------------------------

@dataclass
class ScoringMetrics:
    """One row per scoring system in the eval table."""
    system: str  # "V1.9.1" / "V2.0" / "persistence" / "random"
    precision_at_10: float
    precision_at_50: float
    precision_at_100: float
    recall_at_10: float
    recall_at_50: float
    recall_at_100: float
    brier_score: float
    margin_over_persistence: float
    n_predictions: int
    coverage: float
    notes: str = ""


def precision_at_k(y_true_sorted_by_score: list[bool], k: int) -> float:
    """y_true sorted by predicted score DESC; precision in top-K."""
    if k == 0 or len(y_true_sorted_by_score) == 0:
        return 0.0
    top = y_true_sorted_by_score[:k]
    return sum(1 for y in top if y) / len(top)


def recall_at_k(y_true_sorted_by_score: list[bool], k: int) -> float:
    """y_true sorted by predicted score DESC; recall in top-K."""
    total_positives = sum(1 for y in y_true_sorted_by_score if y)
    if total_positives == 0:
        return 0.0
    top = y_true_sorted_by_score[:k]
    return sum(1 for y in top if y) / total_positives


def brier_score(y_true: list[bool], y_pred: list[float]) -> float:
    """Mean squared error between predicted probability and outcome."""
    if not y_true:
        return float("nan")
    return sum((p - (1.0 if t else 0.0)) ** 2 for t, p in zip(y_true, y_pred)) / len(y_true)


def margin_over_persistence(system_metric: float, persistence_metric: float) -> float:
    """V1.9 uses F1 as the headline. We pin to F1-equivalent; later refine."""
    return system_metric - persistence_metric


# ---------------------------------------------------------------------------
# Per-pair fixture loader (#463 Part C completion, 2026-04-26)
# ---------------------------------------------------------------------------

def load_pairs_jsonl(path: Path) -> list[dict]:
    """Read the per-pair predictions JSONL emitted by run_backtest.py
    --dump-pairs-jsonl. Each line is one (pair, tier, system, y_cal, y_true).

    Returns the full list; callers filter by system.
    """
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def metrics_from_pairs(records: list[dict], system_name: str) -> ScoringMetrics:
    """Compute precision-at-K, recall-at-K, Brier from per-pair records.

    Aggregates across tiers (one prediction per pair, taking the highest
    y_cal across the pair's tier rows — matches the per-tier-threshold logic
    in run_backtest where each tier produces independent predictions).
    """
    # Filter to system + collapse tiers per (country_a_id, event_category):
    # take max y_cal across tier rows for the same pair.
    by_pair: dict[tuple, tuple[float, int]] = {}
    for r in records:
        if r.get("system") != system_name:
            continue
        key = (r["country_a_id"], r["event_category"])
        yc = float(r["y_cal"])
        yt = int(r["y_true"])
        if key not in by_pair or yc > by_pair[key][0]:
            by_pair[key] = (yc, yt)

    if not by_pair:
        return ScoringMetrics(
            system=system_name,
            precision_at_10=float("nan"), precision_at_50=float("nan"),
            precision_at_100=float("nan"), recall_at_10=float("nan"),
            recall_at_50=float("nan"), recall_at_100=float("nan"),
            brier_score=float("nan"), margin_over_persistence=float("nan"),
            n_predictions=0, coverage=0.0,
            notes=f"NO RECORDS for system={system_name!r} in fixture",
        )

    items = sorted(by_pair.items(), key=lambda kv: -kv[1][0])
    y_true_sorted = [v[1] == 1 for _, v in items]
    y_cal_all = [v[0] for _, v in items]
    y_true_all = [v[1] == 1 for _, v in items]

    return ScoringMetrics(
        system=system_name,
        precision_at_10=precision_at_k(y_true_sorted, 10),
        precision_at_50=precision_at_k(y_true_sorted, 50),
        precision_at_100=precision_at_k(y_true_sorted, 100),
        recall_at_10=recall_at_k(y_true_sorted, 10),
        recall_at_50=recall_at_k(y_true_sorted, 50),
        recall_at_100=recall_at_k(y_true_sorted, 100),
        brier_score=brier_score(y_true_all, y_cal_all),
        margin_over_persistence=0.0,  # filled by caller after both systems read
        n_predictions=len(by_pair),
        coverage=1.0,
        notes=f"Computed from per-pair fixture: {len(by_pair)} unique pairs",
    )


# ---------------------------------------------------------------------------
# V1.9.1 baseline loader — reads aggregate metrics from backtest_results.json.
# ---------------------------------------------------------------------------

def load_v19_baseline(baseline_json: Path) -> tuple[ScoringMetrics, ScoringMetrics]:
    """Load V1.9.1 + persistence rows from the backtest output.

    The backtest_results.json shape is one dict per scoring system, with
    aggregate metrics (no per-pair detail). For V1.9.1's precision-at-K
    we only have K=3 and K=5 in the cache; extrapolate cautiously, mark
    K=10/50/100 as PENDING when not available.
    """
    with baseline_json.open("r", encoding="utf-8") as f:
        data = json.load(f)

    persistence = data.get("persistence", {})
    # Pick the latest V1.x entry as the V1.9.1 stand-in. The cache may not
    # be regenerated post-V1.9.1 yet; fall back to v1_5 / v1_0 as needed.
    v19_keys = ["v1_9_1", "v1_9", "v1_8_1", "v1_8", "v1_5", "v1_0"]
    v19 = {}
    chosen_key = None
    for k in v19_keys:
        if k in data:
            v19 = data[k]
            chosen_key = k
            break

    persistence_f1 = persistence.get("f1", 0.0)
    v19_f1 = v19.get("f1", 0.0)

    persistence_metrics = ScoringMetrics(
        system="persistence",
        precision_at_10=v19.get("precision_at_5", float("nan")),
        precision_at_50=float("nan"),
        precision_at_100=float("nan"),
        recall_at_10=float("nan"),
        recall_at_50=float("nan"),
        recall_at_100=float("nan"),
        brier_score=-persistence.get("brier_skill_score", 0.0),  # BSS → approx Brier
        margin_over_persistence=0.0,
        n_predictions=persistence.get("n_predictions", 0),
        coverage=persistence.get("coverage", 0.0),
        notes="precision_at_10/50/100 unavailable from cache; rerun backtest with extended K to populate.",
    )
    v19_metrics = ScoringMetrics(
        system=f"V1.9.1 ({chosen_key})" if chosen_key else "V1.9.1",
        precision_at_10=v19.get("precision_at_5", float("nan")),
        precision_at_50=float("nan"),
        precision_at_100=float("nan"),
        recall_at_10=float("nan"),
        recall_at_50=float("nan"),
        recall_at_100=float("nan"),
        brier_score=-v19.get("brier_skill_score", 0.0),
        margin_over_persistence=margin_over_persistence(v19_f1, persistence_f1),
        n_predictions=v19.get("n_predictions", 0),
        coverage=v19.get("coverage", 0.0),
        notes=f"From {baseline_json.name} key '{chosen_key}'. K=5 used as proxy for K=10.",
    )

    return persistence_metrics, v19_metrics


# ---------------------------------------------------------------------------
# V2.0 scorer — reads country_recipe_scores from Athena.
# Currently STUB: implementation lands once #463 Part A v0.2 (Pearson) + Part B
# (Platt calibration) ship.
# ---------------------------------------------------------------------------

def load_v20_metrics_stub() -> ScoringMetrics:
    """Placeholder for V2.0 scoring — populated once Parts A v0.2 + B ship.

    The real implementation will:
      1. Query qgi_data.country_recipe_scores for every (country, recipe) tuple
      2. Re-evaluate against the V1.9 backtest's 649 ground-truth pairs at the
         2020 cutoff (need the backtest set itself, not just the aggregate
         results — that's the missing piece this stub depends on)
      3. Compute precision-at-K / recall / Brier / margin-over-persistence
    """
    return ScoringMetrics(
        system="V2.0",
        precision_at_10=float("nan"),
        precision_at_50=float("nan"),
        precision_at_100=float("nan"),
        recall_at_10=float("nan"),
        recall_at_50=float("nan"),
        recall_at_100=float("nan"),
        brier_score=float("nan"),
        margin_over_persistence=float("nan"),
        n_predictions=0,
        coverage=0.0,
        notes=(
            "PENDING: blocked on #463 Part A v0.2 (Pearson trajectory) + "
            "Part B (Platt calibration). Backtest set re-evaluation also "
            "requires the per-pair backtest fixture (not yet exported "
            "from run_backtest.py — open follow-up to surface)."
        ),
    )


def evaluate_decision_rule(
    persistence: ScoringMetrics,
    v19: ScoringMetrics,
    v20: ScoringMetrics,
) -> tuple[bool, str]:
    """Apply the decision rule: V2.0 must be BETTER on precision-at-K OR
    calibration (Brier) AND NOT WORSE on persistence margin.

    Returns (passed, explanation).
    """
    # Persistence margin: V2.0 must not be worse than V1.9.1's margin.
    # NaN-safe: a NaN comparison is False, so PENDING V2.0 always fails.
    persistence_ok = (
        not _is_nan(v20.margin_over_persistence)
        and v20.margin_over_persistence >= v19.margin_over_persistence
    )

    # Precision-at-K: V2.0 must be better on at least one K.
    precision_better = any(
        not _is_nan(getattr(v20, f"precision_at_{k}"))
        and getattr(v20, f"precision_at_{k}") > getattr(v19, f"precision_at_{k}")
        for k in PRECISION_AT_K_VALUES
    )

    # Calibration: V2.0 Brier must be lower (closer to 0).
    calibration_better = (
        not _is_nan(v20.brier_score)
        and v20.brier_score < v19.brier_score
    )

    rule_passed = persistence_ok and (precision_better or calibration_better)

    if rule_passed:
        explanation = "PASS V2.0 ships. Persistence margin held, "
        if precision_better and calibration_better:
            explanation += "improvement on both precision-at-K AND calibration."
        elif precision_better:
            explanation += "precision-at-K improved."
        elif calibration_better:
            explanation += "calibration improved."
    else:
        reasons = []
        if not persistence_ok:
            reasons.append(
                f"persistence margin ({v20.margin_over_persistence:.4f}) "
                f"WORSE than V1.9.1 ({v19.margin_over_persistence:.4f})"
            )
        if not (precision_better or calibration_better):
            reasons.append(
                "no improvement on precision-at-K or calibration"
            )
        explanation = "FAIL V2.0 fails decision rule: " + "; ".join(reasons)
        if v20.system == "V2.0" and "PENDING" in v20.notes:
            explanation += "  (NOTE: V2.0 metrics PENDING — re-run after #463 Parts A v0.2 + B ship.)"

    return rule_passed, explanation


def _is_nan(x: float) -> bool:
    return x != x


# ---------------------------------------------------------------------------
# Report writer.
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    persistence: ScoringMetrics,
    v19: ScoringMetrics,
    v20: ScoringMetrics,
    rule_passed: bool,
    rule_explanation: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. raw_metrics.json — programmatic.
    raw_path = output_dir / "raw_metrics.json"
    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "decision_rule": DECISION_RULE,
                "rule_passed": rule_passed,
                "rule_explanation": rule_explanation,
                "metrics": {
                    "persistence": asdict(persistence),
                    "v1_9_1": asdict(v19),
                    "v2_0": asdict(v20),
                },
            },
            f,
            indent=2,
        )

    # 2. eval_report.md — narrative.
    md_path = output_dir / "eval_report.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write(_render_markdown(persistence, v19, v20, rule_passed, rule_explanation))

    return raw_path, md_path


def _fmt(x: float, fmt: str = ".4f") -> str:
    if _is_nan(x):
        return "PENDING"
    return format(x, fmt)


def _render_markdown(
    persistence: ScoringMetrics,
    v19: ScoringMetrics,
    v20: ScoringMetrics,
    rule_passed: bool,
    rule_explanation: str,
) -> str:
    return f"""# V2.0-vs-V1.9.1 evaluation

**Decision rule:** {DECISION_RULE}

**Verdict:** {rule_explanation}

---

## Aggregate metrics

| Metric | persistence | V1.9.1 | V2.0 |
|---|---:|---:|---:|
| Precision @ 10 | {_fmt(persistence.precision_at_10)} | {_fmt(v19.precision_at_10)} | {_fmt(v20.precision_at_10)} |
| Precision @ 50 | {_fmt(persistence.precision_at_50)} | {_fmt(v19.precision_at_50)} | {_fmt(v20.precision_at_50)} |
| Precision @ 100 | {_fmt(persistence.precision_at_100)} | {_fmt(v19.precision_at_100)} | {_fmt(v20.precision_at_100)} |
| Recall @ 10 | {_fmt(persistence.recall_at_10)} | {_fmt(v19.recall_at_10)} | {_fmt(v20.recall_at_10)} |
| Recall @ 50 | {_fmt(persistence.recall_at_50)} | {_fmt(v19.recall_at_50)} | {_fmt(v20.recall_at_50)} |
| Recall @ 100 | {_fmt(persistence.recall_at_100)} | {_fmt(v19.recall_at_100)} | {_fmt(v20.recall_at_100)} |
| Brier score (lower better) | {_fmt(persistence.brier_score)} | {_fmt(v19.brier_score)} | {_fmt(v20.brier_score)} |
| Margin over persistence | {_fmt(persistence.margin_over_persistence)} | {_fmt(v19.margin_over_persistence)} | {_fmt(v20.margin_over_persistence)} |
| N predictions | {persistence.n_predictions} | {v19.n_predictions} | {v20.n_predictions} |
| Coverage | {_fmt(persistence.coverage)} | {_fmt(v19.coverage)} | {_fmt(v20.coverage)} |

## Notes per system

- **persistence:** {persistence.notes or "naive baseline; predict if event in last 5yr"}
- **V1.9.1:** {v19.notes or "from existing backtest cache"}
- **V2.0:** {v20.notes or "computed from current pipeline run"}

## Decision rule check

{rule_explanation}

---

Generated by `qgi-ml/scripts/eval_v2_vs_v19.py`. Source data:
- V1.9.1 baseline: cached aggregate metrics from `qgi-ml/results/backtest_results.json`
- V2.0: `qgi_data.country_recipe_scores` (#463) once Parts A v0.2 + B ship and the backtest set is re-evaluated
"""


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--baseline-json", type=Path, required=True,
                   help="Path to qgi-ml/results/backtest_results.json")
    p.add_argument("--output-dir", type=Path, required=True,
                   help="Directory to write eval_report.md + raw_metrics.json")
    p.add_argument("--bucket", type=str, default=None,
                   help="S3 bucket for V2.0 Athena queries. If absent, runs in design-validation mode (V2.0 columns PENDING).")
    p.add_argument("--pairs-jsonl", type=Path, default=None,
                   help="Per-pair backtest fixture from run_backtest.py --dump-pairs-jsonl. "
                        "When supplied, computes V1.9.1 + persistence metrics from per-pair "
                        "data (precision-at-K, Brier) instead of falling back to aggregate cache.")
    args = p.parse_args()

    # #463 Part C: prefer per-pair fixture when supplied; fall back to
    # aggregate cache when only --baseline-json is given.
    if args.pairs_jsonl and args.pairs_jsonl.exists():
        records = load_pairs_jsonl(args.pairs_jsonl)
        persistence = metrics_from_pairs(records, "persistence")
        v19 = metrics_from_pairs(records, "v1.9.1")
        # Compute margin-over-persistence using Brier (lower-better; margin
        # is persistence_brier - v19_brier, positive = v19 wins).
        if not _is_nan(persistence.brier_score) and not _is_nan(v19.brier_score):
            v19.margin_over_persistence = persistence.brier_score - v19.brier_score
    else:
        persistence, v19 = load_v19_baseline(args.baseline_json)

    if args.bucket:
        # TODO: implement Athena query path for V2.0 once #463 Parts A v0.2 + B ship.
        # The pairs fixture from --pairs-jsonl will provide the (country_id, category)
        # set to score against; V2.0's similarity-calibrated value comes from
        # qgi_data.country_recipe_scores via the bucket's Athena workgroup.
        print("WARNING: --bucket supplied but V2.0 Athena scoring not yet implemented. Falling back to PENDING.", flush=True)
    v20 = load_v20_metrics_stub()

    rule_passed, rule_explanation = evaluate_decision_rule(persistence, v19, v20)
    raw_path, md_path = write_report(
        args.output_dir, persistence, v19, v20, rule_passed, rule_explanation
    )

    print(f"Wrote {md_path}")
    print(f"Wrote {raw_path}")
    print(f"\n{rule_explanation}")
    return 0 if rule_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
