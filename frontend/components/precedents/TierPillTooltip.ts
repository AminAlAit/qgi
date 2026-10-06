/**
 * Tier-pill tooltip copy — 7 entries from the A3 brief Family 1 (Precedents).
 *
 * Brief: docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-13.md
 *   section: "Tier-pill tooltips (Sipho)"
 *
 * Used by:
 *   - components/precedents/PrecedentsMergedListClient.tsx (PR #1)
 *   - components/precedents/MergedDetailFooter.tsx (PR #2)
 *   - mechanism cell on detail page (PR #3, deferred)
 *
 * Shared so the wording stays canonical across surfaces. Hover-tooltip text
 * is verbatim per the brief — do not paraphrase without re-vote.
 */

export type TierMethod = "ML" | "Stat";

export const TIER_TOOLTIP_COPY: Record<string, string> = {
  // ML-adjudicated tiers
  STRONG:
    "Survived all 4 lock pillars: walk-forward AUC ≥0.65, calibration Brier ≤0.20, falsification rules clean, holdout reproduced. Highest evidentiary weight in this corpus.",
  "MODERATE (ML)":
    "Locked, but with one pillar at threshold (e.g. AUC 0.61–0.65 or two falsifications fired without flipping the sign). Use with the caveat.",
  MARGINAL:
    "Locked under amendment (KI-1/KI-2 sign or wording change applied post-pre-reg). Methodology honest; treat as provisional pending replication.",
  // Statistical (RCI-derived) tiers
  HIGH: "Correlation strength + event coverage in the top decile of the screen. Has not been backtested.",
  "MODERATE (Stat)":
    "Screen-positive across both countries; mid-decile strength. Not backtested.",
  LOW: "Crosses screen floor; included for audit completeness. Not backtested.",
  INSUFFICIENT:
    "Below the screen floor on at least one axis; shown only when explicitly filtered in. Not a finding.",
};

/**
 * Resolve a (tier, method) pair to its tooltip string. The "MODERATE" rung
 * collides across rubrics — disambiguate by method suffix.
 */
export function getTierTooltip(tier: string, method: TierMethod): string {
  if (tier === "MODERATE") {
    return method === "ML"
      ? TIER_TOOLTIP_COPY["MODERATE (ML)"]
      : TIER_TOOLTIP_COPY["MODERATE (Stat)"];
  }
  return TIER_TOOLTIP_COPY[tier] ?? "";
}
