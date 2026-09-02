/**
 * Demographic-3 frontend suppression — M5 phase 1 (Asas Majles 2026-05-01).
 *
 * The "Demographic 3" indicators (Population total, Life expectancy at birth,
 * Mortality rate under-5) appear in the top-15 fingerprint of 100% of recipes
 * (per investigation #573). Substrate-effect contamination — they correlate
 * because populations evolve smoothly over decades, NOT because they predict
 * coups / fiscal crises / etc.
 *
 * **Phase 1 (this file):** suppress them from frontend fingerprint
 * visualizations. Quick visual win; ships in hours; gives buyers a credible
 * fingerprint to look at while the proper fix bakes.
 *
 * **Phase 2 (#577 — pipeline):** replace with per-(indicator × L3 category)
 * posterior weighting matrix. The weights will produce mathematically-correct
 * fingerprints (D3 weight ≈ 0 for L1=POL/SEC, ≈ 1 for L1=HEALTH/DEV).
 *
 * **When phase 2 ships:** delete this file. Suppression becomes obsolete
 * because the weighted re-bake produces a correct fingerprint downstream.
 *
 * Numeric IDs verified via `qgi-frontend/data/indexes.json` and confirmed by
 * #573 investigation:
 *   - 2  = Population, total
 *   - 4  = Life expectancy at birth, total (years)
 *   - 14 = Mortality rate, under-5 (per 1,000 live births)
 */
export const DEMOGRAPHIC_3_IDS: ReadonlySet<number> = new Set([2, 4, 14]);

/**
 * Filter a fingerprint array to remove Demographic-3 entries.
 *
 * Use on EVERY fingerprint visualization that surfaces indicator names to
 * users. (Other fingerprint consumers — e.g. ML pipelines that compute on
 * raw scores — should NOT use this filter; they should use the upstream
 * weighted matrix once #577 lands.)
 */
export function filterDemographic3<T extends { indicator_id: number }>(
  fingerprint: T[]
): T[] {
  return fingerprint.filter((f) => !DEMOGRAPHIC_3_IDS.has(f.indicator_id));
}
