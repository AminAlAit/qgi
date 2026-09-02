/**
 * Numeric indicator-ID supplement.
 *
 * Background — root cause of "(unknown N)" labels on `/precedents/[slug]`:
 *
 * The Athena table `qgi_data.recipes_aggregated` was baked with legacy
 * `indicator_id` smallints (the WB/V-Dem indicator catalog numbering
 * scheme as it existed at recipe-mining time). Since then:
 *
 *   - `qgi-data/registries/` was deduplicated (see
 *     `qgi-data/scripts/remove_tfrt_duplicate.py`): the row that
 *     legacy bakes referenced as numeric_id=165 (SP.DYN.TFRT.IN /
 *     Fertility rate, total) was removed; its current canonical
 *     numeric_id in `data/indexes.json` is 15.
 *   - 20 V-Dem variables (numeric_ids 276–307) were added to the
 *     pipeline indicator catalog but never seeded into
 *     `data/indexes.json` (the curated 259-entry WB-centric catalog).
 *
 * Consequence: `scripts/bake-recipes-aggregated.ts:buildIndicatorMap()`
 * loads `indexes.json` only, fails to find these 21 legacy ids, and
 * writes `"(unknown ${id})"` as the human-readable name into the
 * baked JSON. The dossier renders that string verbatim.
 *
 * Fix: this supplement is consulted by BOTH the bake script
 * (so future bakes self-heal) AND the dossier component
 * (so the already-baked `data/recipes-aggregated.json` renders
 * correctly without a fresh Athena bake).
 *
 * Provenance of the 21 entries:
 *   - 165: `qgi-data/scripts/remove_tfrt_duplicate.py` documents
 *          numeric_id=165 as SP.DYN.TFRT.IN.
 *   - 276–307: cross-referenced from
 *          `qgi-data/reference/indicator-allow-list.json` (numeric_id
 *          → V-Dem api_code) plus display labels from
 *          `docs/specs/methodology/indicator-catalog-detailed.md`
 *          (VD-01..VD-32 rows).
 *
 * Adding a new entry: when a future bake emits another "(unknown N)",
 * resolve N via `qgi-data/reference/indicator-allow-list.json` and
 * append below. Tests in `lib/__tests__/indicator-numeric-supplement.test.ts`
 * will fail loudly if `data/recipes-aggregated.json` ever ships an
 * unknown id this map doesn't cover.
 */

/** Legacy numeric-id → human-readable name. */
export const INDICATOR_NUMERIC_SUPPLEMENT: Readonly<Record<number, string>> = {
  // Legacy WB rows missing from the deduped indexes.json
  165: "Fertility rate, total (births per woman)",

  // V-Dem variables (qgi-data/reference/indicator-allow-list.json +
  // docs/specs/methodology/indicator-catalog-detailed.md)
  276: "Electoral Democracy Index (V-Dem)", // VD-01 v2x_polyarchy
  277: "Liberal Democracy Index (V-Dem)", // VD-02 v2x_libdem
  278: "Judicial Constraints on Executive (V-Dem)", // VD-03 v2x_jucon
  279: "Legislative Constraints on Executive (V-Dem)", // VD-04 v2xlg_legcon
  283: "Freedom of Expression (V-Dem)", // VD-08 v2x_freexp_altinf
  284: "Political Participation (V-Dem)", // VD-09 v2x_partip
  285: "Regime Type (V-Dem)", // VD-10 v2x_regime
  287: "Physical Violence Index (V-Dem)", // VD-12 v2x_clphy
  289: "Freedom from Torture (V-Dem)", // VD-14 v2cltort
  290: "Political Civil Liberties Index (V-Dem)", // VD-15 v2x_clpol
  291: "Private Civil Liberties Index (V-Dem)", // VD-16 v2x_clpriv
  293: "Political Corruption Index (V-Dem)", // VD-18 v2x_corr
  298: "Equal Protection Index (V-Dem)", // VD-23 v2xeg_eqprotec
  300: "Civil Society Participatory Environment (V-Dem)", // VD-25 v2csprtcpt
  301: "Women's Political Empowerment Index (V-Dem)", // VD-26 v2x_gender
  302: "Power Distributed by Gender (V-Dem)", // VD-27 v2pepwrgen
  303: "Power Distributed by Socioeconomic Position (V-Dem)", // VD-28 v2pepwrsoc
  304: "Power Distributed by Sexual Orientation (V-Dem)", // VD-29 v2pepwrort
  306: "Neopatrimonialism Index (V-Dem)", // VD-31 v2x_neopat
  307: "Free and Fair Elections Index (V-Dem)", // VD-32 v2xel_frefair
};

/**
 * Build a Map<numeric_id, name> that overlays the supplement onto a
 * base catalog (typically `data/indexes.json`). The supplement only
 * fills gaps — entries already present in the base are NOT overwritten.
 * That keeps `indexes.json` as the source of truth for everything it
 * covers; the supplement is strictly additive.
 */
export function buildIndicatorNameLookup(
  baseEntries: Iterable<readonly [number, string]>
): Map<number, string> {
  const m = new Map<number, string>(baseEntries);
  for (const [id, name] of Object.entries(INDICATOR_NUMERIC_SUPPLEMENT)) {
    const numId = Number(id);
    if (!m.has(numId)) {
      m.set(numId, name);
    }
  }
  return m;
}

/**
 * Check whether a baked indicator_name is the bake script's
 * unknown-fallback (`"(unknown ${id})"`). Cheaper than re-parsing
 * the id — callers usually have the id already.
 */
export function isBakedUnknown(name: string | undefined): boolean {
  return typeof name === "string" && /^\(unknown \d+\)$/.test(name);
}
