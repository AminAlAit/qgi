/**
 * Shared UI label constants.
 *
 * Centralised here so every auto-generated narrative block carries the
 * identical disclosure string — avoids the per-component label drift that
 * produced "[PREVIEW TEMPLATE]" / "[Illustrative narrative]" / (no label)
 * across three surfaces (R8 Daniel Mensah BUG-4 2026-05-20).
 */

/**
 * Standard disclosure label for every auto-generated narrative section.
 * Used by SignalsLeafDetail, SignalsCountryDetail, and CountryMergedDetail.
 */
export const AUTO_NARRATIVE_LABEL =
  "[Auto-generated from data — not editorially authored]";
