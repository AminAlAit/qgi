/**
 * lib/signals-trajectory-canonical.ts — Pure canonical-recipe lookup.
 *
 * Extracted from `lib/signals-trajectory.ts` (which is `server-only`)
 * so that vitest tests can import the actual production function instead
 * of an inlined copy that could drift (per #624 strict-review F1).
 *
 * This module has zero AWS/Athena/server-only dependencies — it's a
 * straightforward type-narrowing lookup against pre-baked JSON shape.
 */

export interface CanonicalRecipeRow {
  country_b_id: string;
  country_b_name: string;
  start_year_b: number;
  length: number;
}

export interface BakedCanonicalFields {
  canonical_length: number;
  canonical_country_b_id?: string | null;
  canonical_country_b_name?: string | null;
  canonical_start_year_b?: number | null;
}

/**
 * #624: Read the top-PPS canonical recipe from the pre-baked
 * RecipeAggregated record instead of running an Athena query.
 *
 * Original behaviour (deleted) ran:
 *   SELECT country_b_id, start_year_b, length FROM qgi_data.recipes
 *   WHERE event_category='X' ORDER BY pattern_power_score DESC LIMIT 1
 * The `recipes` table is partitioned by country_a_id (154 partitions); the
 * `event_category` predicate had no partition pushdown, so each call
 * scanned all 154 partitions (= ~444 S3 GETs per execution). With 72
 * categories × ~89 ISR pages, cache warm-up alone produced ~4.4M S3 GETs.
 *
 * Bake script (`scripts/bake-recipes-aggregated.ts`) now pre-computes the
 * canonical row at pipeline time and writes the three fields into
 * recipes-aggregated.json. Frontend reads from JSON; zero per-page-load
 * Athena cost.
 *
 * Returns null when:
 *   - The baked JSON pre-dates this addition (canonical_country_b_id is
 *     null/undefined), or
 *   - The bake script's canonical-fetch step failed silently.
 *
 * `countryById` defaults to an empty map when imported standalone.
 * The server-only `lib/signals-trajectory.ts` module passes its
 * pre-built COUNTRY_BY_ID map (built from `data/countries.json`) at
 * call time.
 */
export function getCanonicalRecipeFromBaked(
  recipe: BakedCanonicalFields,
  countryById: Map<string, string> = new Map()
): CanonicalRecipeRow | null {
  if (!recipe.canonical_country_b_id) return null;
  const startYear = recipe.canonical_start_year_b;
  if (startYear == null) return null;
  return {
    country_b_id: recipe.canonical_country_b_id,
    country_b_name:
      recipe.canonical_country_b_name ??
      countryById.get(recipe.canonical_country_b_id) ??
      `Country ${recipe.canonical_country_b_id}`,
    start_year_b: startYear,
    length: recipe.canonical_length,
  };
}
