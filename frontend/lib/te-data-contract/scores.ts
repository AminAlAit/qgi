/**
 * TE sample-10 scores file contract.
 *
 * Source: `data/te-sample-10/scores/{recipe_id}.scores.json`
 * Shape verified from real files at data/te-sample-10/scores/economic_nationalization.scores.json
 */

export interface ShapAttributionEntry {
  code: string;
  /** Resolved server-side; can be null — frontend backfills via lib/indicator-labels.ts. */
  name: string | null;
  signal_share_pct: number;
  /** Signed SHAP value (raw magnitude). null pending score_countries.py upgrade (#974). */
  shap_value?: number | null;
}

export interface IndicatorMovementEntry {
  code: string;
  /** Resolved server-side; can be null — frontend backfills via lib/indicator-labels.ts. */
  name: string | null;
  /** 12 quarterly z-scored values. */
  trajectory_12q: number[];
  z_score_change: number;
  /** Round-2: panel-explicit provider (replaces inferProvider() heuristic). */
  provider?: string | null;
  /** Round-2: raw indicator value at eval_year. */
  latest_raw_value?: number | null;
  /** Round-2: raw indicator value at the immediately-prior year. */
  prior_raw_value?: number | null;
  /** Round-2: unit hint string (e.g. "%", "z-score (V-Dem)"). */
  unit?: string | null;
}

export interface SensitivityEntry {
  indicator: string;
  marginal_points_per_unit: number;
  current_cosine: number;
  headroom: number;
  headroom_points: number;
}

export interface NearestAnalogEntry {
  country: string;
  year: number;
  match_score: number;
  weak_analog: boolean;
  /** Round-2: other recipes that also rate this analog highly. */
  secondary_recipe_ids?: string[];
  /** Round-2: 12-pt pre-event composite z-score trajectory. 100% coverage. */
  indicator_trajectory_12q?: number[];
  /** Round-2: curated narrative. null = research workstream in flight. */
  what_happened_next?: string | null;
}

export interface CountryScoreEntry {
  /** null in sample-10 — must be resolved via name-to-ISO map. */
  iso: string | null;
  /** ISO2 — present in fleet-run-1. */
  iso2?: string | null;
  /** Flag emoji — present in fleet-run-1. */
  flag_emoji?: string | null;
  name: string;
  score: number;
  rank: number;
  eval_year: number;
  in_evidence_base: boolean;
  delta_vs_prior_vintage: number | null;
  shap_attribution: ShapAttributionEntry[];
  indicator_movement: IndicatorMovementEntry[];
  nearest_analogs?: NearestAnalogEntry[];
  /** Round-2: 12-pt mean of selected indicators z-score trajectories. */
  indicator_trajectory_composite_12q?: number[];
  /** Round-2: fleet-canonical cosine similarity. */
  cosine_similarity_S?: number;
  /** Round-2: zone HIGH/MED/LOW. */
  zone?: string;
  /** Round-2: human-readable zone descriptor. */
  zone_label?: string;
  /** Round-2: per-indicator sensitivity entries. */
  sensitivity_per_indicator?: SensitivityEntry[];
  /** Round-2: multi-year momentum scores (year → score), 4 years 2023-2026. */
  momentum_scores_by_year?: Record<string, number>;
  /** Round-2: rising/falling/flat/suppressed. */
  momentum_label?: string | null;
}

export interface RecipeScoresFile {
  recipe_id: string;
  vintage: string;
  scored_at_utc: string;
  n_countries_scored: number;
  train_auc: number;
  scoring_method: string;
  scores: CountryScoreEntry[];
  /** Round-2: countries in the platform roster that were not scored. */
  countries_not_scored?: Array<{ name: string; iso2: string }>;
  /** Round-2: ISO2-only list for Risk Board footer tooltip. */
  countries_not_scored_iso?: string[];
  /** Round-2: count of unscored countries. */
  n_countries_not_scored?: number;
  /** Round-2: 5-fold cross-validated AUC. */
  cv_auc_full?: number;
}
