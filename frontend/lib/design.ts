/**
 * QGI design tokens — single source of truth for colors, thresholds, and
 * visual language across every component (#126).
 *
 * Before this file existed, SECTOR_COLORS was duplicated verbatim in four
 * separate components (SectorRose, ScdiTable, IndexCatalogue,
 * PatternSummaryCard), tier/convergence badges did not exist, and each chart
 * inlined its own 0.8/0.6 thresholds for coloring correlations. This module
 * centralizes all of that so future views (#122, #123, #124) consume stable
 * tokens instead of inventing their own.
 *
 * Design principles:
 * - One color per sector, stable across every view
 * - Three categorical tiers (tier, convergence, significance) each get a
 *   fixed palette; no ad-hoc ternaries at call sites
 * - PPS / correlation color bands are thresholds on a continuous scale,
 *   exposed as helper functions not lookup maps
 * - Tabular numeric formatting lives in the `.font-data` CSS class
 *   (defined in globals.css), not here
 */

import type { PatternTier, ConvergenceTier } from "@/lib/dashboard-cache";

// ---------------------------------------------------------------------------
// Sector colors
// ---------------------------------------------------------------------------

/**
 * Canonical sector color map. Every component that renders a sector badge,
 * rose chart slice, or category chip MUST consume this — never inline a hex
 * literal. Add new sectors here as the taxonomy expands.
 *
 * Color assignments are stable and carefully chosen:
 * - Neighboring sectors on the color wheel are avoided for adjacent UI rows
 * - Military/Danger sectors share the red family
 * - Econ/Trade/Finance share the cool blue family
 * - Governance/Social share the purple family
 */
export const SECTOR_COLORS: Record<string, string> = {
  Economic: "#38bdf8", // sky-400
  Trade: "#34d399", // emerald-400
  Finance: "#93c5fd", // blue-300
  Energy: "#fde68a", // amber-200
  Military: "#f87171", // red-400
  Governance: "#a78bfa", // violet-400
  Government: "#c4b5fd", // violet-300
  Health: "#fb923c", // orange-400
  Demographic: "#fbbf24", // amber-400
  Social: "#e879f9", // fuchsia-400
  Education: "#22d3ee", // cyan-400
  Infrastructure: "#4ade80", // green-400
  Environment: "#86efac", // green-300
  Other: "#7a90a8", // slate-muted
};

/** Safe sector color lookup with fallback to 'Other'. */
export function sectorColor(sector: string | null | undefined): string {
  if (!sector) return SECTOR_COLORS.Other;
  return SECTOR_COLORS[sector] ?? SECTOR_COLORS.Other;
}

/**
 * Faded background for a sector chip — 18 hex alpha (~9%) applied to the
 * sector color. Used for filter chips and inline badges.
 */
export function sectorChipBg(sector: string | null | undefined): string {
  return `${sectorColor(sector)}18`;
}

// ---------------------------------------------------------------------------
// Pattern tier (#128 — S/M/L/XL)
// ---------------------------------------------------------------------------

/**
 * Colors for each pattern length tier. Same hierarchy as the taxonomy:
 *   S  = single policy/commodity cycle  (crisis precedent)
 *   M  = leadership era / generational  (policy regime)
 *   L  = Cold War era / development     (structural era)
 *   XL = institutional similarity       (civilizational)
 * Reads from short=red/urgent to long=cool/structural.
 */
export const TIER_COLORS: Record<PatternTier, string> = {
  S: "#f87171", // red-400 — short, urgent, crisis-relevant
  M: "#fbbf24", // amber-400 — medium-term, actionable
  L: "#38bdf8", // sky-400 — long, structural
  XL: "#a78bfa", // violet-400 — institutional
};

export function tierColor(tier: PatternTier | null | undefined): string {
  if (!tier) return SECTOR_COLORS.Other;
  return TIER_COLORS[tier];
}

/** Human-readable tier label for tooltips and legends. */
export const TIER_LABELS: Record<PatternTier, string> = {
  S: "Short (3–8 yr)",
  M: "Medium (9–20 yr)",
  L: "Long (21–40 yr)",
  XL: "Institutional (41+ yr)",
};

// ---------------------------------------------------------------------------
// Convergence tier (#133 — single/emerging/multilateral/high)
// ---------------------------------------------------------------------------

/**
 * Colors for multi-pattern convergence tiers. Escalates from gray (weak
 * single signal) through amber (emerging) to red (high convergence). These
 * match the "dot circles" visual the #133 spec describes.
 */
export const CONVERGENCE_COLORS: Record<ConvergenceTier, string> = {
  // #740 (2026-05-18): swapped from slate-dim (#8aa6be) to neutral gray
  // (Tailwind gray-400). PR #82's a11y bump made the single tier visually
  // competitive with the warm tiers 2-4; gray-400 keeps AA (≥ 4.5:1 on all
  // three dark surfaces) while restoring the "barely-there weak signal"
  // semantic — less chroma = less attention-pull at equivalent luminance.
  single: "#9ca3af", // gray-400 — barely-there weak signal
  emerging: "#fbbf24", // amber-400 — watching
  multilateral: "#fb923c", // orange-400 — serious
  high: "#f87171", // red-400 — urgent
};

export function convergenceColor(tier: ConvergenceTier | null | undefined): string {
  if (!tier) return SECTOR_COLORS.Other;
  return CONVERGENCE_COLORS[tier];
}

export const CONVERGENCE_LABELS: Record<ConvergenceTier, string> = {
  single: "Single signal",
  emerging: "Emerging consensus",
  multilateral: "Multi-lateral convergence",
  high: "High convergence",
};

/**
 * Dot-circle count for convergence tier visualization — matches the #133
 * spec's "dot circles for convergence tier (visual badge)".
 */
export const CONVERGENCE_DOTS: Record<ConvergenceTier, number> = {
  single: 1,
  emerging: 2,
  multilateral: 3,
  high: 4,
};

// ---------------------------------------------------------------------------
// Pattern Power Score (#129 — 0-100 normalized)
// ---------------------------------------------------------------------------

/**
 * Color band for a 0-100 PPS value. Used on every signal card, detail
 * page, and ranking table.
 *
 * Bands are tuned to the V1.5.3 distribution — the long tail of low-PPS
 * signals gets a muted color so the eye is drawn to the rare high-PPS ones.
 */
export function ppsColor(pps: number | null | undefined): string {
  if (pps == null || !Number.isFinite(pps)) return SECTOR_COLORS.Other;
  if (pps >= 80) return "#f87171"; // red — very strong
  if (pps >= 60) return "#fb923c"; // orange — strong
  if (pps >= 40) return "#fbbf24"; // amber — moderate
  return "#7a90a8"; // slate — weak / background
}

// ---------------------------------------------------------------------------
// Correlation color band (legacy — kept for the indicator chart subtext)
// ---------------------------------------------------------------------------

/**
 * Color band for a Pearson r value (0..1 magnitude). Used by chart
 * subtitles in IndexChart. Matches what the code was inlining before.
 */
export function correlationColor(r: number | null | undefined): string {
  if (r == null || !Number.isFinite(r)) return SECTOR_COLORS.Other;
  if (r >= 0.8) return "#34d399"; // emerald-400 — strong
  if (r >= 0.6) return "#f59e0b"; // amber-500 — moderate
  return "#7a90a8"; // slate — weak
}

// ---------------------------------------------------------------------------
// Statistical significance (from lib/stats.ts pearsonPValue)
// ---------------------------------------------------------------------------

/** Color for a Pearson significance label: ***, **, *, ns, — */
export function significanceColor(sig: "***" | "**" | "*" | "ns" | "—"): string {
  switch (sig) {
    case "***":
    case "**":
      return "#34d399"; // success — p < 0.01
    case "*":
      return "#fbbf24"; // amber — p < 0.05
    case "ns":
    case "—":
    default:
      return "#7a90a8"; // dim — not significant
  }
}
