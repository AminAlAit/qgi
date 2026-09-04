/**
 * sector-colors.ts — canonical sector color palette for cascade pattern
 * indicator cards and sector breakdown chips.
 *
 * Hues are muted to sit against dark QGI surface backgrounds without
 * fighting the page text. Each sector has a distinct hue; all share low
 * saturation so no sector dominates visually unless the card count earns it.
 *
 * Colour selection rule (Sara Ahmed UX rubric):
 *   - Economic   : steel blue  — most common sector; calm, non-alarming
 *   - Political  : dusty violet — political indicators carry governance weight
 *   - Social     : muted sage   — social indicators = population wellbeing
 *   - Governance : warm slate   — close to economic but colder
 *   - Health     : muted teal   — clinical, neutral
 *   - Military   : desaturated red-brown — conflict/force, but not alarming
 *   - Trade      : warm gold    — commerce associations
 *   - Finance    : muted cyan   — market/fiscal
 *   - Education  : soft lavender
 *   - Demographic: muted mauve
 *   - Infrastructure: warm olive
 *   - Environment: muted green
 *   - Opposite-direction accent: muted teal #4A8A7E (for inverse-direction card stripe)
 */

export const SECTOR_COLORS: Record<string, string> = {
  Economic: "#5B7E99",
  Political: "#8A6FA8",
  Social: "#7A9A6A",
  Governance: "#6C8899",
  Health: "#4A9A8E",
  Military: "#8A6B5A",
  Trade: "#9A8B5A",
  Finance: "#5A8A9A",
  Education: "#8A7AAA",
  Demographic: "#8A6A8A",
  Infrastructure: "#7A8A5A",
  Environment: "#5A8A6A",
};

/** Fallback for sectors not in the catalog. */
export const SECTOR_COLOR_FALLBACK = "#7A8FA0";

/** Color used for the 3px left stripe on opposite-direction indicator cards. */
export const OPPOSITE_DIRECTION_COLOR = "#4A8A7E";

/** Return the sector color, or the fallback if the sector is unknown. */
export function sectorColor(sector: string): string {
  return SECTOR_COLORS[sector] ?? SECTOR_COLOR_FALLBACK;
}
