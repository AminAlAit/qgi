/**
 * Buyer-View transform layer — the typed boundary between raw bake data
 * and what gets rendered to users.
 *
 * # Why this exists
 *
 * The bake script (`qgi-ml/scripts/bake_ml_recipes_for_frontend.py`) writes
 * technical content into JSON fields that flow directly into JSX via
 * `{x.field}` expressions: recipe slugs in `mechanism_narrative`, raw
 * indicator codes like `VC.BTL.DETH__diff` in `top_k_indicators[]`,
 * methodology jargon (LOCO/AHI/n_pos/F-H-N) scattered through prose.
 *
 * Founder feedback 2026-05-12: scattered render-time relabels are
 * whack-a-mole. We need a typed boundary that:
 *
 *   1. Forces components to consume `BuyerMlRecipe` instead of `MlRecipeEntry`
 *      (TypeScript rejects raw type at compile time)
 *   2. Centralizes ALL relabeling logic in one file
 *   3. Has a CI gate asserting the output passes the polish-scanner
 *
 * # Architecture
 *
 *   data/ml-recipe-stack.json (raw, ML-team-owned)
 *           │
 *           ▼
 *   loadMlRecipeStack() → MlRecipeStack (raw types)
 *           │
 *           ▼
 *   toBuyerView(raw, slugMap) → BuyerMlRecipe (CLEAN)
 *           │
 *           ▼
 *   <PrecedentsV2Detail recipe={buyer} /> (type-checked: only accepts BuyerMlRecipe)
 *
 * # When the bake fix (#683) lands
 *
 * Once `qgi-ml` ships buyer-clean prose + `indicator_label` fields, this
 * module shrinks to a near-pass-through. Components don't need to change;
 * `toBuyerView` just stops doing rewrites.
 */

import type {
  AnchorAhiStatus,
  ConcentrationAlertLevel,
  InterpretationHint,
  MlRecipeEntry,
} from "@/lib/recipes-ml";
import { getIndicatorLabel } from "@/lib/indicator-labels";
import {
  buildSlugMap as buildSlugMapFromNarrative,
  rewriteRecipeSlugsInProse,
} from "@/lib/recipe-narrative";
import { replaceJargonInProse } from "@/lib/jargon-replace";

// ---------------------------------------------------------------------------
// BuyerMlRecipe type — what components consume
// ---------------------------------------------------------------------------

/**
 * A single indicator entry shaped for buyer rendering. Replaces
 * `TopKIndicator` for components: friendly `label` is what shows,
 * `raw_id` is preserved for `title=` analyst-recovery hover, and the
 * fixed-effect boolean is pre-translated to a `country_bias_caveat`
 * string (or null if not flagged).
 */
export interface BuyerIndicator {
  rank: number;
  /** Friendly buyer-facing label, e.g. "Battle-related deaths (year-over-year change)". */
  label: string;
  /** Raw indicator ID (e.g. "VC.BTL.DETH__diff") — for analyst-recovery tooltip only. */
  raw_id: string;
  /** Numeric importance score (`mean_abs_shap` from raw). */
  importance: number;
  /**
   * Pre-translated caveat. When fixed-effect-suspect: "Possible country bias".
   * When clean: null (component renders empty cell).
   */
  country_bias_caveat: string | null;
}

/**
 * Buyer-shaped recipe. Mirrors `MlRecipeEntry` numeric fields verbatim;
 * prose fields are jargon-rewritten + slug-rewritten; `top_k_indicators`
 * is reshaped to `indicators` (BuyerIndicator[]).
 *
 * Identifiers (`recipe_id`, `paper_section_anchor`) are preserved for
 * URL/key construction — components MUST NOT render them as text. The
 * type system can't enforce that (any `string` field can be JSX-rendered),
 * but the polish-scanner CI gate catches violations at build time.
 */
export interface BuyerMlRecipe {
  // ---- Identifiers (keep for URLs / React keys; not for rendering) ----
  recipe_id: string;
  display_name: string;
  paper_section_anchor: string;
  model_version: string;

  // ---- Pre-translated enum / status fields (already buyer-facing) ----
  tier: MlRecipeEntry["tier"];
  /** Plain-English architecture name; replaces raw "D2"/"D5". */
  architecture_label: string;
  /** Raw architecture code preserved for tooltip. */
  architecture_raw: "D2" | "D5";
  assignment_confidence: MlRecipeEntry["assignment_confidence"];
  anchor_ahi_status: AnchorAhiStatus;
  concentration_alert_level: ConcentrationAlertLevel;
  interpretation_hint: InterpretationHint;
  advisory_only_flag: boolean;
  f_rule_anomaly_flag: boolean;

  // ---- Numeric metrics (unchanged) ----
  loco_auc: number;
  n_pos_loco: number;
  in_sample_f1_ece: number;
  in_sample_f2_auc: number;
  in_sample_f2_ci_lower: number;
  in_sample_f2_ci_upper: number;
  ece_overall: number;
  ece_high_cohort: number;
  ece_mid_cohort: number;
  ece_low_cohort: number;
  anchor_ahi_value: number | null;
  anchor_ahi_n_evaluable: number | null;
  top_1_training_country_share: number | null;

  // ---- Cleaned prose fields ----
  /** Jargon-replaced + slug-rewritten. Safe to render directly. */
  mechanism_narrative: string;
  /** Same shape, shorter. */
  mechanism_narrative_excerpt: string;
  /** Jargon-replaced + slug-rewritten. Preserves markdown bold. */
  buyer_disclosure_recommendation: string;
  /** Jargon-replaced. */
  zero_positive_cohort_flag: string | null;
  /** Jargon-replaced + markdown links unlinked. */
  anchor_ahi_reason: string | null;
  /** Per-item jargon + slug rewrite. */
  open_followups: string[];

  // ---- Top-1 training country: keep as-is (it's a country name, clean) ----
  top_1_training_country: string | null;

  // ---- Indicator table (reshaped) ----
  /** Pre-labeled indicator rows. Replaces raw `top_k_indicators` from `MlRecipeEntry`. */
  indicators: BuyerIndicator[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ARCHITECTURE_LABELS: Record<"D2" | "D5", string> = {
  D2: "Level-features model",
  D5: "Trend-features model",
};

function cleanProse(
  text: string | null | undefined,
  slugMap: Record<string, string>
): string {
  if (!text) return "";
  // Order matters: rewrite slugs FIRST (sentence-case-aware), then
  // apply jargon replacements. If we did jargon first, "elections_and_voting"
  // could get its underscores mangled by a jargon pattern before the
  // slug rewriter sees it.
  const slugCleaned = rewriteRecipeSlugsInProse(text, slugMap);
  return replaceJargonInProse(slugCleaned);
}

function cleanProseNullable(
  text: string | null | undefined,
  slugMap: Record<string, string>
): string | null {
  if (text === null || text === undefined) return null;
  const cleaned = cleanProse(text, slugMap);
  return cleaned || null;
}

function shapeIndicator(raw: MlRecipeEntry["top_k_indicators"][number]): BuyerIndicator {
  return {
    rank: raw.rank,
    label: getIndicatorLabel(raw.indicator_id),
    raw_id: raw.indicator_id,
    importance: raw.mean_abs_shap,
    country_bias_caveat: raw.fixed_effect_suspect ? "Possible country bias" : null,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Build the slug → display-name map from a recipe stack. Pass to
 * `toBuyerView` so prose fields can rewrite cross-recipe references.
 *
 * Re-exported from `lib/recipe-narrative.ts` so page-level callers can
 * import everything they need from `lib/buyer-view.ts` (single import
 * boundary). Implementation lives next to its primary consumer
 * (`rewriteRecipeSlugsInProse`).
 */
export const buildSlugMap = buildSlugMapFromNarrative;

/**
 * Transform a raw `MlRecipeEntry` into a buyer-shaped `BuyerMlRecipe`.
 *
 * @param raw Raw recipe from `ml-recipe-stack.json`
 * @param slugMap Full recipe slug → display-name map for cross-references.
 *                If omitted, falls back to self-only `{[raw.recipe_id]: raw.display_name}`.
 *                Pages with access to the full stack SHOULD pass the map.
 */
export function toBuyerView(
  raw: MlRecipeEntry,
  slugMap?: Record<string, string>
): BuyerMlRecipe {
  const effectiveSlugMap: Record<string, string> = slugMap ?? {
    [raw.recipe_id]: raw.display_name,
  };
  return {
    // Identifiers (URL / React-key use only)
    recipe_id: raw.recipe_id,
    display_name: raw.display_name,
    paper_section_anchor: raw.paper_section_anchor,
    model_version: raw.model_version,

    // Pre-translated enum / status
    tier: raw.tier,
    architecture_label: ARCHITECTURE_LABELS[raw.architecture],
    architecture_raw: raw.architecture,
    assignment_confidence: raw.assignment_confidence,
    anchor_ahi_status: raw.anchor_ahi_status,
    concentration_alert_level: raw.concentration_alert_level,
    interpretation_hint: raw.interpretation_hint,
    advisory_only_flag: raw.advisory_only_flag,
    f_rule_anomaly_flag: raw.f_rule_anomaly_flag,

    // Numerics (verbatim)
    loco_auc: raw.loco_auc,
    n_pos_loco: raw.n_pos_loco,
    in_sample_f1_ece: raw.in_sample_f1_ece,
    in_sample_f2_auc: raw.in_sample_f2_auc,
    in_sample_f2_ci_lower: raw.in_sample_f2_ci_lower,
    in_sample_f2_ci_upper: raw.in_sample_f2_ci_upper,
    ece_overall: raw.ece_overall,
    ece_high_cohort: raw.ece_high_cohort,
    ece_mid_cohort: raw.ece_mid_cohort,
    ece_low_cohort: raw.ece_low_cohort,
    anchor_ahi_value: raw.anchor_ahi_value,
    anchor_ahi_n_evaluable: raw.anchor_ahi_n_evaluable,
    top_1_training_country_share: raw.top_1_training_country_share,

    // Cleaned prose
    mechanism_narrative: cleanProse(raw.mechanism_narrative, effectiveSlugMap),
    mechanism_narrative_excerpt: cleanProse(
      raw.mechanism_narrative_excerpt,
      effectiveSlugMap
    ),
    buyer_disclosure_recommendation: cleanProse(
      raw.buyer_disclosure_recommendation,
      effectiveSlugMap
    ),
    zero_positive_cohort_flag: cleanProseNullable(
      raw.zero_positive_cohort_flag,
      effectiveSlugMap
    ),
    anchor_ahi_reason: cleanProseNullable(raw.anchor_ahi_reason, effectiveSlugMap),
    open_followups: (raw.open_followups ?? []).map((f) =>
      cleanProse(f, effectiveSlugMap)
    ),

    // Country name (clean by construction)
    top_1_training_country: raw.top_1_training_country,

    // Indicators (reshaped)
    indicators: (raw.top_k_indicators ?? []).map(shapeIndicator),
  };
}

/**
 * Transform a list of recipes. Builds the slug map once and reuses it.
 */
export function toBuyerViewList(recipes: ReadonlyArray<MlRecipeEntry>): BuyerMlRecipe[] {
  const slugMap = buildSlugMap(recipes);
  return recipes.map((r) => toBuyerView(r, slugMap));
}
