/**
 * 2026-05-28 (V4.1 promo): Shared pattern + signal types that were previously
 * defined in the now-deleted V3 route pages. Moved here so legacy V3
 * components in `components/patterns/` and `components/signals/` can
 * continue to compile.
 */
import type { PatternWindowTier } from "@/lib/patterns-initial-filters";
import type { PatternTrajectory } from "@/lib/pattern-trajectory";

/**
 * PatternsMergedRow — enriched pattern row as used by the V3 patterns list.
 * Extracted 2026-05-28 from the deleted `app/(app)/patterns/page.tsx`.
 */
export interface PatternsMergedRow extends PatternRow {
  /** Brief-renamed Pattern-window vocab — S-win/M-win/L-win/XL-win. */
  window_tier: PatternWindowTier;
  /** Server-derived stable key for React lists. */
  row_key: string;
  /** T1 (#59) — leader terminating event + follower arc position. */
  trajectory: PatternTrajectory;
}

/**
 * PatternRow — single pattern window as produced by pipeline-recipe-engine
 * and consumed by the frontend.
 *
 * T2 #295 / T13 #306 type-drift fix (2026-04-19): `country_a_id` /
 * `country_b_id` now accept `string | number` to tolerate both the baked
 * JSON shape (stringified in `RankingPayload` per `lib/dashboard-cache.ts`)
 * and the Athena-path numeric shape. Callers must coerce with `String(x)` or
 * `Number(x)` at the usage site — do NOT rely on the type alone.
 */
export interface PatternRow {
  country_a: string;
  country_b: string;
  country_a_id?: string | number;
  country_b_id?: string | number;
  start_year_a: number;
  start_year_b: number;
  pattern_length: number;
  avg_correlation: number;
  pattern_power_score: number;
  num_indexes: number;
  predicted: boolean;
  /** Pattern window tier — raw S/M/L/XL classification from the pipeline. */
  pattern_tier?: "S" | "M" | "L" | "XL";
}

export interface IndexEntry {
  id: string;
  /**
   * T10 #303 fix (2026-04-19): previously typed `number | null`, but all
   * 260 entries in `indexes.json` have a non-null numeric_id. Tightened
   * to `number` so consumers don't need null guards the data never exercises.
   */
  numeric_id: number;
  name: string;
  sector: string;
  org: string;
  source: string;
  description: string;
  tips: string;
  citation: string;
}

export interface Country {
  id: string;
  name: string;
  alpha_2: string;
}

/** #128: Pattern length tier — from qgi_data.patterns.pattern_tier */
export type PatternTier = "S" | "M" | "L" | "XL";

/** #133: Convergence tier — from qgi_data.recipe_convergence.convergence_tier */
export type ConvergenceTier = "single" | "emerging" | "multilateral" | "high";

/**
 * A "signal" is the user-facing name for an active recipe match in QGI's
 * mental model (#121, 2026-04-07): a country currently following another
 * country's historical trajectory. The underlying database table is still
 * called `recipes` (Athena) — that's the data layer name. Everything the
 * user reads says "signal" or "precedent" instead.
 *
 * SignalRow is the canonical type name. RecipeRow is kept as an alias for
 * backwards compatibility with imports that haven't migrated yet.
 *
 * The V1.5.3 fields (#128 pattern_tier, #129 pps + instance_count, #133
 * convergence_*, #134 median_lead_time) are all optional so pre-V1.5.3
 * dashboard JSONs (before the next pipeline run lands the new CTAS)
 * still load without TypeScript errors.
 */
export interface SignalRow {
  recipe_id: string;
  event_category: string;
  country_a_id: number;
  country_b_id: number;
  country_a_name: string;
  country_b_name: string;
  start_year_a: number;
  start_year_b: number;
  length: number;
  avg_correlation: number;
  end_year_a: number;
  end_year_b: number;
  event_window: number;
  event_year_a: number;
  event_year_b: number;
  event_title_a: string;
  event_title_b: string;
  indicator_count: number;
  pattern_power_score: number;
  instance_count: number;

  // #129: new normalized 0-100 Pattern Strength
  pps?: number;

  // #128: pattern length tier
  pattern_tier?: PatternTier | null;

  // #134: forecast timing
  median_lead_time?: number | null;
  min_lead_time?: number | null;
  max_lead_time?: number | null;

  // #133: multi-pattern convergence
  convergence_score?: number;
  convergence_tier?: ConvergenceTier;
  n_predictors?: number;
  n_regions?: number;
  predictor_country_ids?: number[];
  composite_sort_key?: number;
}

/** @deprecated Use SignalRow. Kept as an alias during the #121 rename rollout. */
export type RecipeRow = SignalRow;

/**
 * #137: Wrapped API response shape for signal/precedent endpoints.
 *
 * `generated_at` is an ISO timestamp:
 *  - For S3-cached endpoints (top50, ranking, early-warning), it's the moment
 *    `pipeline-recipe-engine` last wrote the dashboard JSON. This means it
 *    reflects the last monthly pipeline run, not the request time.
 *  - For live endpoints (country profile), it's the request time.
 *
 * The frontend uses this for the data freshness UX (DataFreshness component)
 * so users can tell whether they're looking at month-old material or live data.
 */
export interface SignalsResponse {
  generated_at: string;
  /**
   * T10 #303 fix (2026-04-19): `recipes-top50.json` and `early-warning.json`
   * carry a top-level `as_of_year` that several callers reference via
   * `as unknown as` casts. Declared here so downstream consumers don't
   * drift out of type safety.
   */
  as_of_year?: number;
  results: SignalRow[];
}

/**
 * Enriched analogue — produced by `.tmp/decisions-form/_enrich_analogues.py`
 * (for base enrichment) + `qgi-ml/scripts/enrich_analogues_common_length.py`
 * (for #354 common-length fields). Reads `qgi-data/events/curated/*.json`
 * directly and picks the median-year event of the matching category as
 * the analogue's signature event, plus a length-L-aligned pattern window
 * per (subject, category) so every analogue row on a panel shares the
 * same pattern length (#354, Position C).
 *
 * Consumed by `components/countries/AnalogueMultiTimeline.tsx`
 * (tickets #293, #354).
 */
export interface AnalogueEnrichedEntry {
  country_b_id: number;
  country_b_name: string;
  alpha2: string;
  recipe_count: number;
  mean_corr: number;
  best_pps: number;
  avg_lead_years: number | null;
  /** Year of the median/signature event of the matching category for this analogue country. */
  event_year_b: number | null;
  /** Title of the signature event. */
  event_title_b: string | null;
  /** [earliest_event_year, latest_event_year] across all events of the category in this country. */
  event_range_b: [number, number] | null;
  /** All years with matching-category events for this analogue (reserved for richer timelines later). */
  event_all_years_b: number[] | null;
  /** 'qgi-data' = enriched from curated events; 'missing' = no match found. */
  event_data_source: "qgi-data" | "missing";

  /**
   * #354 common-length fields (preferred, populated by
   * `enrich_analogues_common_length.py` as of 2026-04-19):
   * every analogue in a (subject, category) block shares `pair_length ≈ canonical_length ± 2`
   * so the AnalogueMultiTimeline panel is structurally coherent.
   */
  /** #354: pattern length in years (all analogues in a panel ≈ canonical_length ± 2). */
  pair_length?: number;
  /** #354: subject's start year in the length-L pattern (varies per row, but all lengths are ≈ L). */
  pair_start_a?: number;
  /** #354: analogue's start year in the length-L pattern. */
  pair_start_b?: number;
  /** #354: PPS of the chosen length-L window. */
  pair_pps?: number;
  /** #354: average correlation of the chosen length-L window. */
  pair_avg_corr?: number;
  /**
   * #354: true iff event_year_b falls inside [pair_start_b, pair_start_b + pair_length].
   * When false, the widget renders a visual "event outside window" flag.
   */
  event_in_window?: boolean;

  /**
   * #461 (D7 plumbing): true when the underlying Pattern (and the SCDIs that
   * built it) included any predicted indicator-year via the indicator
   * completer. Surfaced as a "contains predicted values" badge on the
   * analogue card so users know the analogue was partly built on forecast
   * data rather than fully-real observations. False/undefined when absent
   * (pre-#461 enrichment runs, or pair_* not present at all).
   */
  contains_predicted?: boolean;

  /**
   * #465 Q2 (progressive disclosure): all top-N Pattern instances for this
   * (subject, analogue) pair, ordered by PPS desc. The first entry mirrors
   * the canonical `pair_*` fields above (selected as max-PPS per Q4).
   * AnalogueMultiTimeline renders only the canonical bar by default; on
   * row hover/click, expands to show all entries stacked.
   *
   * Optional + back-compat: when undefined, the component renders the
   * single canonical bar (pre-Q2 behaviour). New pipeline runs will
   * populate this; legacy `analogues-enriched.json` snapshots won't.
   */
  pair_instances?: PatternInstance[];

  /**
   * @deprecated #352: per-pair best-PPS length (independent across analogues).
   * Kept only for data-migration reading compatibility. Use the `pair_*`
   * fields above; they enforce the common-length invariant.
   */
  best_pattern_length?: number;
  /** @deprecated — see `pair_start_a`. */
  best_pattern_start_a?: number;
  /** @deprecated — see `pair_start_b`. */
  best_pattern_start_b?: number;
}

/** #465 Q2: a single Pattern instance backing one (subject, analogue) pair. */
export interface PatternInstance {
  /** Length in years. */
  l: number;
  /** Subject (country_a) start year. */
  sa: number;
  /** Analogue (country_b) start year. */
  sb: number;
  /** Pattern Power Score. */
  pps: number;
  /** Avg correlation magnitude across pattern indicators. */
  ac: number;
  /** Indicator count contributing to the pattern. */
  ic: number;
  /** #461 D7: any contributing SCDI built on predicted indicator-year? */
  cp?: boolean;
}

export interface AnalogueEnrichedSubject {
  country_id: string;
  country_name: string;
  subject_event_year_a: number | null;
  subject_event_title_a: string | null;
  subject_event_range_a: [number, number] | null;
  subject_event_all_years_a: number[] | null;
  subject_slug_resolved: string | null;
}

export interface AnaloguesEnrichedPayload {
  generated_at: string;
  source: string;
  enriched_count: number;
  total_analogues: number;
  /**
   * #354: `enrichment_algorithm` identifies the common-length-v1 pass.
   * Widget can assert on this before reading the new `pair_*` fields.
   */
  enrichment_algorithm?: string;
  enrichment_length_tolerance?: number;
  countries: {
    [countryId: string]: {
      [category: string]: {
        subject: AnalogueEnrichedSubject;
        analogues: AnalogueEnrichedEntry[];
        /**
         * #354: canonical pattern length L for this (subject, category).
         * All analogue rows on the panel have `pair_length ≈ L ± 2`.
         */
        canonical_length?: number;
      };
    };
  };
}
