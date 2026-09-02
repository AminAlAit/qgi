/**
 * TE sample-10 card v3 contract.
 *
 * Source: `docs/specs/internal/ops/te-sample-10-frontend-reply-addendum-2026-05-28.md`
 * Shape verified from real files at `data/te-sample-10/cards-v3/*.card.json`.
 *
 * v3 is append-only over v2 over v1. Schema-validating v3 means validating
 * v2 (and v1) — strict subset preservation.
 */

export interface CardStats {
  loco_auc: number;
  ci95_lo: number;
  ci95_hi: number;
  ci80_lo: number;
  ci80_hi: number;
  n_bootstrap: number;
}

export interface GreedyWalkStep {
  step: number;
  candidate: string;
  window: number;
  auc: number;
  lift_over_previous: number;
  selected_after: string[];
}

export interface GreedyWalk {
  selected_indicators: string[];
  chosen_window: number;
  final_global_auc: number;
  early_abort_floor_unreachable: boolean;
  history: GreedyWalkStep[];
}

export interface CoverageAudit {
  n_pos_total: number;
  n_pos_survive: number;
  n_neg_total: number;
  n_neg_survive: number;
  n_countries_survive: number;
  pos_coverage: number;
  neg_coverage: number;
  coverage_pass: boolean;
}

export interface CohortMetric {
  loco_auc: number;
  ece: number;
  low_confidence: boolean;
}

export interface PerCohort {
  "fragile-state"?: CohortMetric;
  "mid-tier"?: CohortMetric;
  "stable-democracy"?: CohortMetric;
  [cohort: string]: CohortMetric | undefined;
}

export interface ScoreDistributionBin {
  bin_lo: number;
  bin_hi: number;
  count: number;
}

export interface ScoreDistribution {
  computed: boolean;
  histogram: ScoreDistributionBin[];
  median: number;
  p90: number;
  p99: number;
  max: number;
  n_countries_scored?: number;
  source?: string;
}

export interface IndicatorSensitivityEntry {
  code: string;
  /** Resolved server-side; can be null — frontend backfills via lib/indicator-labels.ts. */
  name: string | null;
  auc_with: number;
  auc_without: number;
  auc_drop: number;
}

export interface IndicatorSensitivity {
  computed: boolean;
  leave_one_out: IndicatorSensitivityEntry[];
  cv_auc_full?: number;
  method?: string;
}

export interface Calibration {
  computed: boolean;
  bins: Array<{
    predicted_lo: number;
    predicted_hi: number;
    observed_rate: number;
  }> | null;
  ece: number | null;
  notes?: string;
}

export interface ReliabilityMultipass {
  walks_completed: number;
  v1_separation_pp: number | null;
  v4_oot_recall_pct: number | null;
  verdict: string;
}

export type Tier = "validated" | "directional" | "experimental" | "queued" | "hold";

/**
 * Verdict from F-ML-1 §3.1. Open-ended (the pipeline may emit new
 * verdict labels in future vintages); render as-is.
 */
export type Verdict = string;

export interface CardV3 {
  recipe_id: string;
  tier: Tier;
  tier_provenance: string;
  verdict: Verdict;
  stats: CardStats;
  greedy_walk: GreedyWalk;
  coverage_audit: CoverageAudit | null;
  per_cohort: PerCohort;
  architecture: string;
  architecture_provenance: Record<string, unknown>;
  borderline_lock: boolean;
  temporal_confound_auc: number | null;
  stability_diagnostic: Record<string, unknown> | null;
  per_recipe_floor_provenance: Record<string, unknown>;
  n_positives: number;
  n_negatives: number;
  walked_at_utc: string;
  elapsed_seconds: number;
  raw_summary_s3: string;

  // v2 additions:
  score_distribution: ScoreDistribution;
  /** Optional: editorial precedent corpus pointer (may be empty in early vintages). */
  precedents_corpus?: {
    events: Array<{
      country_iso: string | null;
      country_name: string;
      year: number;
      label: string;
      brief_url?: string;
      in_training_set: boolean;
    }>;
    total_events_in_corpus: number;
  };
  /** Optional: trajectory alignment shape data (mean + p25 + p75 per indicator). */
  trajectory_alignment?: {
    window_years: number;
    indicators: Array<{
      code: string;
      name: string | null;
      provider: string;
      shape: { mean: number[]; p25: number[]; p75: number[] };
    }>;
  };
  indicator_sensitivity: IndicatorSensitivity;
  reliability_multipass: ReliabilityMultipass;
  calibration: Calibration;

  // v3 additions:
  engine: "trajectory-engine-v1";
  contract_version: string;
  per_country_scores_pointer: string;

  // round-2 (2026-05-30) additions:
  /** 12-float canonical trajectory composite built from per_feature_breakdown × shap_importance_normalized. */
  shape_points?: number[];
  /** Per-indicator raw SHAP values (unsigned magnitude). */
  shap_importance_raw?: Record<string, number>;
  /** Per-indicator normalized SHAP weights (sums to 1). */
  shap_importance_normalized?: Record<string, number>;
  /** Per-indicator direction signs: +1 (risk-increasing) / -1 (risk-decreasing). */
  shap_direction_signs?: Record<string, number>;
  /** Per-indicator last_z / mean_z / std_z / slope breakdown. */
  per_feature_breakdown?: Record<
    string,
    { last_z: number; mean_z: number; std_z: number; slope: number }
  >;
}
