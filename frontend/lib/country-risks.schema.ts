/**
 * Zod schema for `country-risks.json` (#440 Part B).
 *
 * The frontend used to trust the structure of pipeline JSON outputs;
 * when the pipeline shipped V1.9.1 with renamed fields (#428 fallout),
 * the UI silently rendered stale values because the shape mismatch
 * never threw. Zod-parsing the file at load time means a regen with a
 * drifted schema fails LOUD instead of softly painting `undefined`.
 *
 * The TypeScript interfaces in `country-risks.ts` are re-derived from
 * these schemas (via `z.infer`) so the two stay in lock-step
 * automatically — there's only ONE source of truth for the shape.
 *
 * If the pipeline adds a field, adding it here (with a sensible
 * default or `.optional()`) is the only place the frontend needs to
 * change. If the pipeline removes/renames a field, the next deploy's
 * load-time parse fails — which is exactly when you want to know.
 */

import { z } from "zod";

export const RiskTierSchema = z.enum(["HIGH", "MODERATE", "INDICATIVE"]);

export const CategoryScoreSchema = z.object({
  category: z.string(),
  z_score: z.number(),
  salience_score: z.number(),
  severity_tier: z.number(),
  rrf_rank: z.number(),
  rrf_score: z.number(),
  recipe_count: z.number(),
  last_event_year: z.number().nullable(),
});

export const TierDataSchema = z.object({
  top_categories: z.array(CategoryScoreSchema),
});

// #721 (2026-05-16) — QGI Risk Score: 0-100 percentile rank of the
// country's max salience across the bake's cohort. Lives ALONGSIDE
// salience (does NOT replace it). Strict ordinal interpretation —
// NOT a probability. See `docs/specs/internal/ops/qgi-risk-score-majles-
// 2026-05-16.md` for full spec.
//
// All four fields are `.nullable()` because insufficient-coverage
// countries get `null` rather than coerced to 0/50. Existing JSONs
// baked before this field landed parse cleanly via `.optional()`.
export const QgiRiskScoreCoverageFlagSchema = z.enum(["ok", "insufficient"]);
export type QgiRiskScoreCoverageFlag = z.infer<typeof QgiRiskScoreCoverageFlagSchema>;

// #728 (2026-05-16) — per-recipe Risk Score bundle. Mirrors the country-
// level score shape; emitted per top-4 LOCKed recipe. Null when the
// country has no top_category match for that recipe (i.e., the recipe
// is not in the country's signal profile).
//
// #729 Step 1.5 — Majles enrichments (all optional for back-compat with
// v2 bakes):
//   - `cohort_n_recipe`: Roshani's veto — must be glanceable beside score
//   - `recipe_ece` / `recipe_loco_auc` / advisory flags: Kwame's veto —
//     calibration metrics carried alongside score so buyers know reliability
export const QgiRiskScorePerRecipeEntrySchema = z.object({
  score: z.number().int().min(0).max(100),
  ci_low: z.number().int().min(0).max(100),
  ci_high: z.number().int().min(0).max(100),
  coverage_flag: QgiRiskScoreCoverageFlagSchema,
  // #729 Step 1.5 enrichments — optional for back-compat
  cohort_n_recipe: z.number().int().min(0).optional(),
  recipe_ece: z.number().nullable().optional(),
  recipe_loco_auc: z.number().nullable().optional(),
  recipe_f_rule_advisory_flag: z.boolean().optional(),
  recipe_f_rule_anomaly_flag: z.boolean().optional(),
});
export type QgiRiskScorePerRecipeEntry = z.infer<typeof QgiRiskScorePerRecipeEntrySchema>;

export const CountryRiskSchema = z.object({
  name: z.string(),
  alpha_2: z.string(),
  curated: z.boolean(),
  overall_risk_tier: RiskTierSchema,
  // Tiers are S/M/L/XL but the file may add new keys; Record<string, ...>
  // keeps the schema forward-compatible.
  tiers: z.record(z.string(), TierDataSchema),
  // #721 — QGI Risk Score per country. Optional because earlier bakes
  // pre-#721 don't carry them; nullable because insufficient-data
  // countries hold `null`.
  qgi_risk_score_0_100: z.number().int().min(0).max(100).nullable().optional(),
  qgi_risk_score_ci_low: z.number().int().min(0).max(100).nullable().optional(),
  qgi_risk_score_ci_high: z.number().int().min(0).max(100).nullable().optional(),
  coverage_flag: QgiRiskScoreCoverageFlagSchema.optional(),
  // #728 — per-recipe Risk Score. Record keyed by recipe_id (top-4
  // LOCKed). Null per recipe when the country has no top_category for it.
  qgi_risk_score_by_recipe: z
    .record(z.string(), QgiRiskScorePerRecipeEntrySchema.nullable())
    .optional(),
});

export const CountryRisksDataSchema = z.object({
  generated_at: z.string(),
  version: z.string(),
  scoring: z.string(),
  // The pipeline writes per-tier-length config under top-level `tiers`
  // alongside per-country tier data. Two distinct concepts unfortunately
  // sharing a key. Keep the shape mirror.
  tiers: z.record(
    z.string(),
    z.object({
      min_length: z.number(),
      max_length: z.number(),
    })
  ),
  curated_country_count: z.number(),
  total_countries: z.number(),
  countries: z.record(z.string(), CountryRiskSchema),
  // #721 — QGI Risk Score metadata. All optional because pre-#721 bakes
  // didn't carry them.
  qgi_risk_score_version: z.string().optional(),
  qgi_risk_score_cohort_n: z.number().int().min(0).optional(),
  qgi_risk_score_method: z.string().optional(),
  qgi_risk_score_baked_at: z.string().optional(),
  // #728 — per-recipe Risk Score metadata. Cohort N per recipe (cohorts
  // are recipe-specific subsets); recipe list (the top-4 LOCKed).
  qgi_risk_score_per_recipe_cohort_n: z
    .record(z.string(), z.number().int().min(0))
    .optional(),
  qgi_risk_score_per_recipe_recipes: z.array(z.string()).optional(),
  // #729 Step 1.5 — Dmitri's recipe-recipe Spearman correlation matrix,
  // surfaced so quants can residualize properly. 4×4 record-of-records;
  // self-correlation = 1.0; cells where shared-country count < min_pairs
  // are null. Spearman ∈ [-1, 1].
  qgi_risk_score_per_recipe_correlation_matrix: z
    .record(z.string(), z.record(z.string(), z.number().min(-1).max(1).nullable()))
    .optional(),
  qgi_risk_score_per_recipe_min_pairs: z.number().int().min(2).optional(),
  // #729 Step 1.5 — Roshani's small-N CI widening parameters (audit trail)
  qgi_risk_score_small_cohort_ci_threshold: z.number().int().min(0).optional(),
  qgi_risk_score_small_cohort_ci_widen_factor: z.number().min(1).optional(),
});

// Re-derive the TS types from the schemas so the two never drift.
export type RiskTier = z.infer<typeof RiskTierSchema>;
export type CategoryScore = z.infer<typeof CategoryScoreSchema>;
export type TierData = z.infer<typeof TierDataSchema>;
export type CountryRisk = z.infer<typeof CountryRiskSchema>;
export type CountryRisksData = z.infer<typeof CountryRisksDataSchema>;
