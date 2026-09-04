/**
 * TE sample-10 country-index contract.
 *
 * Source: `data/te-sample-10/countries/country-index.json`
 * Shape verified from real files.
 */

export interface CountryTopRecipeEntry {
  recipe_id: string;
  label: string;
  l1_id: string;
  l1_label: string;
  l1_color: string;
  score: number;
  status: string;
}

export interface RankHistoryPoint {
  quarter: string;
  rank_on_top_recipe: number;
}

export interface CountryIndexEntry {
  /** null in sample-10 — resolve via name-to-ISO3 map. */
  iso: string | null;
  /** null in sample-10 — resolve via name-to-ISO2 map. */
  iso2: string | null;
  /** null in sample-10 — derive from iso2 flag codepoints. */
  flag_emoji: string | null;
  name: string;
  /** null in sample-10 — backfill from static region seed. */
  region: string | null;
  /** null in sample-10. */
  population: number | null;
  vintage: string;
  recipes_lit_count: number;
  lit_families: string[];
  compound_score: number;
  top_recipes: CountryTopRecipeEntry[];
  /** null in sample-10 — sourced from recipe scores file per top recipe. */
  drivers_attribution: unknown | null;
  /** null in sample-10 — sourced from recipe scores file per top recipe. */
  drivers_movement: unknown | null;
  rank_history: RankHistoryPoint[];
  rank_history_notes: string;
  analogs_pointer: string | null;
  compound_score_rank: number;
}

export interface CountryIndex {
  vintage: string;
  platform_roster_size: number;
  n_countries_scored: number;
  compound_score_formula: string;
  countries: CountryIndexEntry[];
}
