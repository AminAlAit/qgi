/**
 * compare-data.ts — derivation helpers for /compare.
 *
 * All functions derive from COUNTRIES_V4 (no new seed data). The module
 * is a pure computation layer: given two ISO codes, it extracts the
 * structural comparison primitives the page needs.
 *
 * V4.1 bar: no em-dashes, no banned vocab, no persona credits.
 */
import { COUNTRIES_V4, getCountryByIso, type CountryV4 } from "./countries-v4-data";

// ── Re-exports for convenience at the call sites ──────────────────────────
export type { CountryV4 };

// ── Types ─────────────────────────────────────────────────────────────────

export interface CompareGapRow {
  recipe_id: string;
  label: string;
  l1_id: string;
  l1_label: string;
  l1_color: string;
  score_a: number | null;
  score_b: number | null;
  /** Signed gap: score_a - score_b. Null when only one country is in play. */
  gap: number | null;
  status_a: string | null;
  status_b: string | null;
  /** True when the recipe is in play for both countries. */
  shared: boolean;
}

export interface AtAGlance {
  recipes_a: number;
  recipes_b: number;
  lit_families_a: number;
  lit_families_b: number;
  top_rank_gap: number;
  top_rank_gap_recipe: string;
  overlap_count: number;
}

export interface SharedMoverBadge {
  indicator_code: string;
  indicator_name: string;
}

/**
 * Union of A's lit recipes and B's lit recipes, sorted by max score descending.
 * Each row carries both scores (null when only one country is in play) and
 * a signed gap.
 */
export function compareGapRows(a: CountryV4, b: CountryV4): CompareGapRow[] {
  const recipeMap = new Map<
    string,
    {
      recipe_id: string;
      label: string;
      l1_id: string;
      l1_label: string;
      l1_color: string;
      score_a: number | null;
      score_b: number | null;
      status_a: string | null;
      status_b: string | null;
    }
  >();

  for (const r of a.top_recipes) {
    recipeMap.set(r.recipe_id, {
      recipe_id: r.recipe_id,
      label: r.label,
      l1_id: r.l1_id,
      l1_label: r.l1_label,
      l1_color: r.l1_color,
      score_a: r.score,
      score_b: null,
      status_a: r.status,
      status_b: null,
    });
  }

  for (const r of b.top_recipes) {
    const existing = recipeMap.get(r.recipe_id);
    if (existing) {
      existing.score_b = r.score;
      existing.status_b = r.status;
    } else {
      recipeMap.set(r.recipe_id, {
        recipe_id: r.recipe_id,
        label: r.label,
        l1_id: r.l1_id,
        l1_label: r.l1_label,
        l1_color: r.l1_color,
        score_a: null,
        score_b: r.score,
        status_a: null,
        status_b: r.status,
      });
    }
  }

  const rows: CompareGapRow[] = Array.from(recipeMap.values()).map((row) => ({
    ...row,
    gap: row.score_a !== null && row.score_b !== null ? row.score_a - row.score_b : null,
    shared: row.score_a !== null && row.score_b !== null,
  }));

  // Sort by max(score_a, score_b) descending.
  rows.sort((x, y) => {
    const maxX = Math.max(x.score_a ?? 0, x.score_b ?? 0);
    const maxY = Math.max(y.score_a ?? 0, y.score_b ?? 0);
    return maxY - maxX;
  });

  return rows;
}

/**
 * Four neutral at-a-glance numbers for the comparison strip.
 */
export function atAGlance(a: CountryV4, b: CountryV4): AtAGlance {
  const rows = compareGapRows(a, b);
  const sharedRows = rows.filter((r) => r.shared);

  // Top rank gap: largest |gap| among shared recipes.
  let topGap = 0;
  let topGapRecipe = "";
  for (const r of sharedRows) {
    if (r.gap !== null && Math.abs(r.gap) > Math.abs(topGap)) {
      topGap = r.gap;
      topGapRecipe = r.label;
    }
  }

  return {
    recipes_a: a.recipes_lit_count,
    recipes_b: b.recipes_lit_count,
    lit_families_a: a.lit_families.length,
    lit_families_b: b.lit_families.length,
    top_rank_gap: Math.abs(topGap),
    top_rank_gap_recipe: topGapRecipe,
    overlap_count: sharedRows.length,
  };
}

/**
 * Intersection of A's and B's lit recipes by recipe_id.
 */
export function sharedRecipes(a: CountryV4, b: CountryV4): CompareGapRow[] {
  return compareGapRows(a, b).filter((r) => r.shared);
}

/**
 * Analogs that appear in both A's and B's top-3 analog lists (by country name).
 */
export function sharedAnalogs(
  a: CountryV4,
  b: CountryV4
): Array<{ country: string; year: number }> {
  const bNames = new Set(a.analogs.map((x) => x.country.toLowerCase()));
  const result: Array<{ country: string; year: number }> = [];
  for (const analog of b.analogs) {
    if (bNames.has(analog.country.toLowerCase())) {
      result.push({ country: analog.country, year: analog.year });
    }
  }
  return result;
}

/**
 * Indicator codes that appear in both A's and B's drivers_movement top-3
 * fastest-moving indicators.
 */
export function sharedMovers(a: CountryV4, b: CountryV4): SharedMoverBadge[] {
  const topA = [...a.drivers_movement]
    .sort((x, y) => Math.abs(y.z_score_change) - Math.abs(x.z_score_change))
    .slice(0, 3);
  const topB = [...b.drivers_movement]
    .sort((x, y) => Math.abs(y.z_score_change) - Math.abs(x.z_score_change))
    .slice(0, 3);

  const codesB = new Set(topB.map((d) => d.indicator_code));
  return topA
    .filter((d) => codesB.has(d.indicator_code))
    .map((d) => ({ indicator_code: d.indicator_code, indicator_name: d.indicator_name }));
}

/**
 * Top-3 fastest-moving drivers for a country, sorted by |z_score_change| desc.
 */
export function topMovers(country: CountryV4, n = 3) {
  return [...country.drivers_movement]
    .sort((a, b) => Math.abs(b.z_score_change) - Math.abs(a.z_score_change))
    .slice(0, n);
}

/**
 * Top shared recipe: highest-scoring row where both countries are in play.
 * Returns null when there is no overlap.
 */
export function topSharedRecipe(a: CountryV4, b: CountryV4): CompareGapRow | null {
  const shared = sharedRecipes(a, b);
  return shared[0] ?? null;
}

/**
 * All available COUNTRIES_V4 entries, for the picker dropdown.
 */
export function allCountries(): CountryV4[] {
  return COUNTRIES_V4;
}

export { getCountryByIso };
