/**
 * Loader + types for `data/recipes-aggregated-mock.json` (#464 Week 2).
 *
 * Mirror of the future `qgi_data.recipes_aggregated` Glue table per
 * #462. When real data lands in Week 3, swap `loadRecipesAggregated()`
 * to read from S3/Athena and the route handlers don't need to change.
 *
 * We intentionally don't go through Zod here — the file is hand-curated
 * for the mock, and once the pipeline produces it the validation layer
 * will be added in the same PR that wires up the Athena loader.
 */
import type { Route } from "next";

export interface LengthBucket {
  length: number;
  count: number;
}

export interface IndicatorFingerprintEntry {
  indicator_id: number;
  /** #470 item 2 (closed via option (c) per QA consult): the future
   * Glue table stores indicator_id only — names live in
   * `data/indexes.json` (260 curated entries, 1-to-1 with smallint IDs).
   * Optional here for back-compat with mock data that still populates it;
   * frontend always resolves via lookup at render time. See [#473](https://github.com/AminAlAit/qgi-aws-tf/issues/473)
   * for the FAOSTAT/ILOSTAT trigger that would change this. */
  indicator_name?: string;
  /** Share of recipes-in-category that include this indicator (0..1). */
  frequency: number;
  /** 95% CI lower bound for frequency. */
  ci_lower: number;
  /** 95% CI upper bound for frequency. */
  ci_upper: number;
  /** Average |Pearson| across the recipes that contain this indicator. */
  avg_corr_magnitude: number;
  /** #470 item 1: TF-IDF score that drives the top-K=15 ranking in the
   * Glue table. Mirrored here so the Week-3 Athena swap is a one-line
   * change to the loader rather than a schema fork. */
  tfidf_score: number;
}

export interface RegionShare {
  region: string;
  share: number;
}

export interface CoverageBiasDiagnostic {
  n_pairs: number;
  oecd_share: number;
  regional_concentration: RegionShare[];
}

export interface RecipeAggregated {
  /** L3 taxonomy slug — primary key for the table. */
  event_category: string;
  canonical_length: number;
  length_distribution: LengthBucket[];
  indicator_fingerprint: IndicatorFingerprintEntry[];
  coverage_bias_diagnostic: CoverageBiasDiagnostic;
  total_instances: number;
  n_distinct_country_pairs: number;
  last_recomputed_at: string;
  contains_predicted: boolean;
  /**
   * Top-PPS canonical recipe metadata (#624). Pre-baked at pipeline time
   * to avoid a per-page-load Athena query against the unpartitioned
   * `event_category` predicate of `qgi_data.recipes` (which scans all 154
   * country_a_id partitions).
   *
   * Optional (`?:`) because older `recipes-aggregated.json` files baked
   * before #624 don't have these keys at all — `JSON.parse` produces
   * `undefined`, not `null`, for absent keys. Required-but-nullable would
   * mislead consumers into thinking `null` is the only "missing" sentinel.
   * Strict consumers should use `??` or truthy checks (both handle
   * undefined and null).
   */
  canonical_country_b_id?: string | null;
  canonical_country_b_name?: string | null;
  canonical_start_year_b?: number | null;
}

export interface RecipesAggregatedFile {
  generated_at: string;
  schema_version: number;
  pipeline_version: string;
  recipes: RecipeAggregated[];
}

// ---------------------------------------------------------------------------
// Country-recipe scores (mock for #463) — same file as the recipe types so
// callers usually wanting both don't have to import twice.
// ---------------------------------------------------------------------------

export interface CountryRecipeScoresFile {
  generated_at: string;
  schema_version: number;
  pipeline_version: string;
  /** country slug → { event_category → similarity score [0..1] } */
  scores: Record<string, Record<string, number>>;
}

// Loader functions live in `./recipes-aggregated-loader.ts` — that module
// is poisoned with `import "server-only"` so client components can import
// the types + URL helpers below without bundling `fs/promises` (which
// Webpack / Turbopack can't resolve in the browser bundle and 500s the
// route). See #470 follow-up; bug introduced by the original #464 PR.

// ---------------------------------------------------------------------------
// URL helpers — keep typed-routes happy in callers.
// ---------------------------------------------------------------------------

/** Canonical /precedents/{slug} URL. */
export function precedentSlugUrl(slug: string): Route {
  return `/precedents/${slug}` as Route;
}

/** Canonical /signals/{country} URL. */
export function signalCountryUrl(countrySlug: string): Route {
  return `/signals/${countrySlug}` as Route;
}

/** Canonical /signals/{country}/{slug} URL. */
export function signalCountryRecipeUrl(countrySlug: string, recipeSlug: string): Route {
  return `/signals/${countrySlug}/${recipeSlug}` as Route;
}
