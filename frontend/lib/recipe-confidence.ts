/**
 * Recipe Confidence Index (RCI) — per-recipe credibility metric (#481).
 *
 * Source: `data/recipe-confidence.json`, generated from the latest
 * indicator-to-recipe audit report (qgi-ml/scripts/audition_indicators.py
 * v0.5 output). The auditioner runs informationally, not as a gate per
 * founder direction (#480).
 *
 * RCI formula (internal — do NOT expose on the public methodology page):
 *   RCI = max(0, 2*(AUC-0.5)) × clamp(n_pos/30, 0, 1) × clamp(1 - n_mnar/15, 0, 1)
 *
 * Where:
 *   - AUC is the per-recipe holdout AUC from the auditioner
 *   - n_pos is the number of positive ground-truth events for the recipe
 *   - n_mnar is how many indicators are flagged for missingness-correlates-with-outcome
 *
 * Tier banding:
 *   GREEN        rci >= 0.50  (high confidence)
 *   YELLOW       rci  0.20–0.50 (moderate)
 *   RED          rci  < 0.20  (low confidence; show with caveat)
 *   INSUFFICIENT n_pos < 5 OR n_total < 30 OR AUC undefined
 *
 * Per founder direction (#482):
 *   - The badge is shown on /precedents/[slug] and /signals/[country]/[slug]
 *   - The /methodology page references RCI as a concept but does NOT expose
 *     the formula or thresholds verbatim.
 */
import recipeConfidenceData from "@/data/recipe-confidence.json";

export type RciTier = "GREEN" | "YELLOW" | "RED" | "INSUFFICIENT";

export interface RecipeConfidenceEntry {
  /** RCI value in [0, 1]. null when tier === "INSUFFICIENT". */
  rci: number | null;
  tier: RciTier;
  /** Subcomponents — present only for tiers other than INSUFFICIENT. */
  auc_skill?: number;
  sample_factor?: number;
  mnar_factor?: number;
  /** Diagnostic fields (always present when known). */
  test_auc: number | null;
  auc_ci_low: number | null;
  auc_ci_high: number | null;
  n_total: number;
  n_pos: number;
  n_mnar_flagged: number;
  /** Top-contributing indicator from the audit run. */
  top_indicator: string | null;
}

export interface RecipeConfidenceFile {
  generated_at: string;
  git_sha: string;
  pipeline_version: string;
  schema_version: number;
  audit_basis: string;
  formula_note: string;
  tiers: Record<RciTier, string>;
  recipes: Record<string, RecipeConfidenceEntry>;
}

const data = recipeConfidenceData as RecipeConfidenceFile;

/**
 * Lookup the RCI entry for a given event_category. Returns the
 * INSUFFICIENT placeholder when the recipe is unknown to the audit
 * (e.g. newly added category not yet in any audit run).
 */
export function getRecipeConfidence(eventCategory: string): RecipeConfidenceEntry {
  const hit = data.recipes[eventCategory];
  if (hit) return hit;
  return {
    rci: null,
    tier: "INSUFFICIENT",
    test_auc: null,
    auc_ci_low: null,
    auc_ci_high: null,
    n_total: 0,
    n_pos: 0,
    n_mnar_flagged: 0,
    top_indicator: null,
  };
}

/**
 * Tier-to-label mapping for UI rendering. Keep these strings short and
 * NOT methodology-specific — the /methodology page revamp (#482) frames
 * the same concept in vague-public language to avoid revealing the formula.
 */
export const TIER_LABEL: Record<RciTier, string> = {
  GREEN: "High confidence",
  YELLOW: "Moderate confidence",
  RED: "Low confidence",
  INSUFFICIENT: "Insufficient data",
};

/**
 * Tier-to-color mapping. Caller is free to use Tailwind class names,
 * CSS variables, or hex; this returns semantic-only category strings.
 */
export const TIER_SEMANTIC: Record<RciTier, "ok" | "warn" | "danger" | "muted"> = {
  GREEN: "ok",
  YELLOW: "warn",
  RED: "danger",
  INSUFFICIENT: "muted",
};

/**
 * Aggregate stats for the headline section of the methodology page (#482).
 * Counts per tier across the audited recipe corpus.
 */
export function getRciAggregate(): {
  total: number;
  byTier: Record<RciTier, number>;
  generated_at: string;
} {
  const byTier: Record<RciTier, number> = {
    GREEN: 0,
    YELLOW: 0,
    RED: 0,
    INSUFFICIENT: 0,
  };
  let total = 0;
  for (const entry of Object.values(data.recipes)) {
    total += 1;
    byTier[entry.tier] += 1;
  }
  return {
    total,
    byTier,
    generated_at: data.generated_at,
  };
}
