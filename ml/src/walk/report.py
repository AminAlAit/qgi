"""Per-recipe markdown report writer for Stage 2 walks.

Format follows pre-reg §10 + `docs/specs/internal/ops/ml-track/
stage-2-per-recipe-optimization.md`.
"""
from __future__ import annotations

from typing import Any


def _fmt_float(value: float | None, ndigits: int = 4) -> str:
    if value is None:
        return "N/A"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not (-float("inf") < f < float("inf")):
        return "NaN" if f != f else f"{'inf' if f > 0 else '-inf'}"
    return f"{f:.{ndigits}f}"


def _fmt_pass(passed: bool | None) -> str:
    if passed is None:
        return "N/A"
    return "PASS" if passed else "FAIL"


def render_walk_report(
    *,
    recipe_id: str,
    rank: int | None,
    rubric_metadata: dict[str, Any],
    n_train: int,
    n_cal: int,
    n_test: int,
    n_pos_train: int,
    n_pos_cal: int,
    n_pos_test: int,
    f1_result: dict[str, Any],
    f2_result: dict[str, Any],
    f3_result: dict[str, Any] | None,
    baseline_comparison: dict[str, Any],
    verdict: dict[str, Any],
    pre_reg_commit_sha: str,
    backbone_dir: str,
    walk_run_id: str,
    notes: str = "",
) -> str:
    """Render the per-recipe walk report as a Markdown string."""
    lines: list[str] = []
    lines.append(f"# Recipe walk: `{recipe_id}`")
    lines.append("")
    rank_str = str(rank) if rank is not None else "N/A"
    lines.append(f"**Stage 2 sequence:** rank {rank_str}")
    lines.append(f"**Status:** {verdict['verdict']}")
    lines.append(f"**Walk run id:** `{walk_run_id}`")
    lines.append(f"**Pre-registration commit:** `{pre_reg_commit_sha}`")
    lines.append(f"**Backbone (frozen):** `{backbone_dir}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Rubric score
    lines.append("## Rubric score")
    lines.append("")
    lines.append(f"- A (density): {_fmt_float(rubric_metadata.get('A'), 3)} "
                 f"(n_positive_verified={rubric_metadata.get('n_positive_verified')}, "
                 f"n_positive_total={rubric_metadata.get('n_positive_total')})")
    lines.append(f"- B (label clarity): {_fmt_float(rubric_metadata.get('B'), 3)}")
    lines.append(f"- C (directional indicators): {_fmt_float(rubric_metadata.get('C'), 3)} "
                 f"(n_relevant_indicators={rubric_metadata.get('n_relevant_indicators')})")
    lines.append(f"- D (pooling utility): {_fmt_float(rubric_metadata.get('D'), 3)}")
    lines.append(f"- **S(r): {_fmt_float(rubric_metadata.get('S'), 4)}**")
    lines.append(f"- F2={rubric_metadata.get('F2')}, F3={rubric_metadata.get('F3')}, "
                 f"F4={rubric_metadata.get('F4')}, "
                 f"survival_eligible={rubric_metadata.get('survival_eligible')}")
    lines.append(f"- F5: {rubric_metadata.get('F5')} (head class: "
                 f"{rubric_metadata.get('head_class')})")
    lines.append("")

    # Sample sizes
    lines.append("## Sample sizes")
    lines.append("")
    lines.append("| Fold | n_total | n_positive |")
    lines.append("|---|---|---|")
    lines.append(f"| Train (80% of 2014-2021) | {n_train} | {n_pos_train} |")
    lines.append(f"| Cal (20% of 2014-2021) | {n_cal} | {n_pos_cal} |")
    lines.append(f"| Test (2022-2025 OOS) | {n_test} | {n_pos_test} |")
    lines.append("")

    # F-rule outcomes
    lines.append("## Falsification rule outcomes")
    lines.append("")
    lines.append("| Rule | Metric | Value | Threshold | Result |")
    lines.append("|---|---|---|---|---|")
    lines.append(f"| F1 (calibration) | ECE | {_fmt_float(f1_result['value'])} "
                 f"| ≤ {_fmt_float(f1_result['threshold'])} "
                 f"| {_fmt_pass(f1_result['passed'])} |")
    f2_ci = f"[{_fmt_float(f2_result.get('ci_lower'))}, {_fmt_float(f2_result.get('ci_upper'))}]"
    lines.append(f"| F2 (AUC vs chance) | AUC (95% CI) "
                 f"| {_fmt_float(f2_result['value'])} {f2_ci} "
                 f"| CI excludes {f2_result['baseline']} AND point ≥ {f2_result['point_threshold']} "
                 f"| {_fmt_pass(f2_result['passed'])} |")
    if f3_result is not None:
        f3_ci = f"[{_fmt_float(f3_result.get('ci_lower'))}, {_fmt_float(f3_result.get('ci_upper'))}]"
        lines.append(f"| F3 (hazard band) | CI width on mean P̂ "
                     f"| {_fmt_float(f3_result['value'])} {f3_ci} "
                     f"| ≤ {_fmt_float(f3_result['threshold'])} "
                     f"| {_fmt_pass(f3_result['passed'])} |")
    else:
        lines.append("| F3 (hazard band) | N/A | — | — | not applicable (non-survival head) |")
    lines.append("")

    # Verdict-gate baseline comparison
    lines.append("## Verdict-gate vs Stage 1 LR baseline")
    lines.append("")
    lines.append("| Metric | DeepHit-lite | Stage 1 LR | Δ | Threshold | Regression? |")
    lines.append("|---|---|---|---|---|---|")
    bc = baseline_comparison
    lines.append(f"| AUC (C-index) | {_fmt_float(bc['deephit_auc'])} "
                 f"| {_fmt_float(bc['baseline_auc'])} "
                 f"| {_fmt_float(bc['delta_auc'])} "
                 f"| ≤ {_fmt_float(bc['threshold'])} regression "
                 f"| {'YES' if bc['auc_regression'] else 'no'} |")
    lines.append(f"| Brier score | {_fmt_float(bc['deephit_brier'])} "
                 f"| {_fmt_float(bc['baseline_brier'])} "
                 f"| {_fmt_float(bc['delta_brier'])} "
                 f"| ≤ {_fmt_float(bc['threshold'])} regression "
                 f"| {'YES' if bc['brier_regression'] else 'no'} |")
    lines.append("")

    # Verdict
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"**{verdict['verdict']}** — {verdict['reason']}")
    lines.append("")
    lines.append(f"Next step: {verdict['next_step']}")
    lines.append("")

    # Required disclosures (from pre-reg §9)
    lines.append("## Required disclosures (pre-reg §9)")
    lines.append("")
    lines.append("- **Low-n F2 caveat:** F2 for `elections_and_voting` (n_pos_test="
                 f"{n_pos_test}) has reduced discriminative power; LOCK status carries "
                 "elevated uncertainty until a higher-n recipe is walked.")
    lines.append("- **Hazard interpretation:** QGI reports unconditional next-year "
                 "cumulative incidence (1 − survival), not conditional hazard. Stage 4 "
                 "user-facing surface inherits this contract.")
    lines.append("- **Cross-recipe calibration sharing:** NOT applied at Stage 2 per "
                 "pre-registration; deferred to post-LOCK research.")
    lines.append("- **Verdict-gate noise band:** the 0.03 regression threshold sits inside "
                 f"the bootstrap-CI noise band at n_pos_test={n_pos_test} (expected CI "
                 "width ≈ 0.12-0.15). Threshold is the locked commitment mechanism, not "
                 "a power-justified gate.")
    lines.append("")

    # Notes
    if notes:
        lines.append("## Notes")
        lines.append("")
        lines.append(notes)
        lines.append("")

    # Replication signature
    lines.append("---")
    lines.append("")
    lines.append("## Replication signature")
    lines.append("")
    lines.append(f"- Walk run id: `{walk_run_id}`")
    lines.append(f"- Pre-registration commit (docs-specs): `{pre_reg_commit_sha}`")
    lines.append(f"- Backbone artifact path: `{backbone_dir}`")
    lines.append("")

    return "\n".join(lines)
