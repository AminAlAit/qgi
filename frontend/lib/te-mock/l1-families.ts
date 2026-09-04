/**
 * l1-families — canonical L1 threat-family display palette for the V4.1
 * country pages.
 *
 * The recipe tracker JSON carries an l1_color per recipe, but two families
 * (A Political Power and F Diplomacy) ship nearly identical purples
 * (#7B5EE6 vs #9F7AEA) that are indistinguishable as small chips/accents on
 * dark navy. Per Talia (data-viz, 2026-05-28 color consult) we re-hue F to
 * an indigo (#6C77E8) and pair every family chip with its letter glyph, so
 * family identity survives both the residual proximity and color-blindness.
 *
 * `familyColor()` returns the DISPLAY color (F overridden); for every other
 * family it equals the tracker color, so the two stay consistent.
 *
 * 2026-05-28 (QA-6): H was identical to NEUTRAL_SLATE (#7A8FA0), so H-dominant
 * cards (Kenya, Germany, UK) rendered their left-border / ribbon / symbol in
 * the exact same hue as the magnitude bar and "+N more" overflow — breaking
 * the color-encodes-kind / length-encodes-magnitude rule. Re-hued H to warm
 * taupe (#8A7A6E) to free up slate as the neutral channel.
 */

export interface L1Family {
  id: string;
  label: string;
  color: string;
}

export const L1_FAMILIES: Record<string, L1Family> = {
  A: { id: "A", label: "Political Power", color: "#7B5EE6" },
  B: { id: "B", label: "Conflict & Violence", color: "#E64545" },
  C: { id: "C", label: "Governance & Rights", color: "#E68F29" },
  D: { id: "D", label: "Economic Stress", color: "#3FA9F5" },
  E: { id: "E", label: "Social Mobilization", color: "#3FBF8F" },
  // F re-hued from tracker #9F7AEA → #6C77E8 to break the A/F purple clash.
  F: { id: "F", label: "Diplomacy & Geopolitics", color: "#6C77E8" },
  G: { id: "G", label: "Humanitarian Crisis", color: "#E94989" },
  // H re-hued from #7A8FA0 → #8A7A6E (warm taupe) — see file header for why.
  H: { id: "H", label: "Structural Trends", color: "#8A7A6E" },
};

/** Neutral slate used for magnitude bars, structural panel accents, and
 *  the "+N more families" overflow segment — never a family hue. */
export const NEUTRAL_SLATE = "#7A8FA0";

/** Calm slate-blue used for the de-shouted anti-causal firewall panels
 *  ("How to read this …") across V4.1 surfaces. Single source so the
 *  hue stays consistent if it ever tunes. */
export const CALM_SLATE_BLUE = "#5B7E99";

/**
 * Display color for a family id. Falls back to the passed tracker color,
 * then to neutral slate, so an unknown id never throws.
 */
export function familyColor(l1Id: string, fallback?: string): string {
  return L1_FAMILIES[l1Id]?.color ?? fallback ?? NEUTRAL_SLATE;
}

/** Display label for a family id (falls back to the id itself). */
export function familyLabel(l1Id: string, fallback?: string): string {
  return L1_FAMILIES[l1Id]?.label ?? fallback ?? l1Id;
}
