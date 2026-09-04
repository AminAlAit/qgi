/**
 * Types for `data/ml-recipe-stack.json` — the V2-shipped ML recipe stack
 * baked by `qgi-ml/scripts/bake_ml_recipes_for_frontend.py` (#643).
 *
 * Schema mirrors the bake script output. Keep in sync when bake schema
 * evolves; consumers should branch on `metadata.schema_version` if the
 * shape changes in a breaking way.
 *
 * Per #656 Asas DECISION + Ji-Hoon's binding rule, `interpretation_hint`
 * enum semantics carry buyer-disclosure weight beyond a label — rendering
 * MUST surface the parenthetical "does not imply premium reduction" for
 * `engagement_signal`. See `components/ml/Callouts.tsx` for the binding
 * rendering contract.
 */

/** Enum from #656 Asas mini-Majles DECISION. */
export type InterpretationHint = "risk_elevation" | "engagement_signal" | "ambiguous";

/**
 * Concentration alert level derived in the bake script from
 * `top_1_training_country_share` (HIGH ≥0.30, caution 0.20-0.30, low <0.20,
 * none for null).
 */
export type ConcentrationAlertLevel = "HIGH" | "caution" | "low" | "none";

/** Anchor AHI presence flag. */
export type AnchorAhiStatus = "measured" | "not_measured";

/** Per-recipe top-K SHAP indicator entry. */
export interface TopKIndicator {
  rank: number;
  indicator_id: string;
  mean_abs_shap: number;
  fixed_effect_suspect: boolean;
}

/** Per-recipe entry in `ml-recipe-stack.json` `recipes[]`. */
export interface MlRecipeEntry {
  recipe_id: string;
  display_name: string;
  tier: "STRONG" | "MODERATE" | "MARGINAL";
  architecture: "D2" | "D5";
  loco_auc: number;
  n_pos_loco: number;
  assignment_confidence: "HIGH" | "MODERATE" | "LOW";
  in_sample_f1_ece: number;
  in_sample_f2_auc: number;
  in_sample_f2_ci_lower: number;
  in_sample_f2_ci_upper: number;
  ece_overall: number;
  ece_high_cohort: number;
  ece_mid_cohort: number;
  ece_low_cohort: number;
  zero_positive_cohort_flag: string | null;
  anchor_ahi_value: number | null;
  anchor_ahi_status: AnchorAhiStatus;
  /** Always null today; #647 will populate when extract_tear_sheets captures
   *  `n_evaluable` from the Stage 5 paper. */
  anchor_ahi_n_evaluable: number | null;
  anchor_ahi_reason: string | null;
  advisory_only_flag: boolean;
  f_rule_anomaly_flag: boolean;
  top_1_training_country: string | null;
  top_1_training_country_share: number | null;
  concentration_alert_level: ConcentrationAlertLevel;
  interpretation_hint: InterpretationHint;
  mechanism_narrative: string;
  mechanism_narrative_excerpt: string;
  buyer_disclosure_recommendation: string;
  open_followups: string[];
  paper_section_anchor: string;
  top_k_indicators: TopKIndicator[];
  model_version: string;
}

/** Source-artifact provenance entry in metadata. */
export interface SourceArtifact {
  path: string;
  sha256: string;
}

/** Top-level metadata block in `ml-recipe-stack.json`. */
export interface MlRecipeStackMetadata {
  schema_version: string;
  generated_at: string;
  dispatch_sha: string;
  n_recipes: number;
  top_4_recipes: string[];
  source_artifacts: SourceArtifact[];
  /** Forward-pointer to the #656 Asas DECISION file. */
  interpretation_hint_decision: string;
}

/** Disclosures block — verbatim from honest-disclosures-2026-05-11.json. */
export interface MlRecipeStackDisclosures {
  schema_version: string;
  generated_at: string;
  purpose: string;
  source_paper: string;
  ml_opus_track_commit: string;
  // The disclosures block embeds many sub-objects (what_was_tested,
  // what_was_not_tested, falsified_under_hybrid, etc.). Frontend renders
  // selected ones at the §5-prominent + §4-collapsible + footer slots per
  // resurfacing plan §caveat presentation. Type loosely; consumers narrow.
  [key: string]: unknown;
}

/** Top-level shape of `data/ml-recipe-stack.json`. */
export interface MlRecipeStack {
  metadata: MlRecipeStackMetadata;
  recipes: MlRecipeEntry[];
  disclosures: MlRecipeStackDisclosures;
}
