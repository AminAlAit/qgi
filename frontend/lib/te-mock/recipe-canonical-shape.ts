/**
 * recipe-canonical-shape — the recipe's canonical per-indicator movement shape
 * (the path a country must trace to score high), sourced from the card's
 * `trajectory_alignment`.
 *
 * As of te-fleet-run-2 the full fleet bakes `trajectory_alignment` on all 44
 * cards (the run-1 0/44 gap is closed), so we read it straight from
 * `loadCardV3` — no more te-sample-10 borrow. Recipes without it (or unknown
 * ids) return null and the country-vs-canonical overlay falls back to the
 * country's own path.
 *
 * Note: WB indicator `name` is null inline in run-2 cards; consumers resolve the
 * human label by `code` via `lib/indicator-labels.ts`. This module only carries
 * the numeric shape keyed by `code`, so the null name does not affect it.
 */
import { loadCardV3 } from "@/lib/te-data-contract/load";

interface TrajectoryAlignment {
  window_years: number;
  indicators: Array<{
    code: string;
    shape: { mean: number[]; p25: number[]; p75: number[] };
  }>;
}

export interface CanonicalShape {
  /** mean trajectory across the canonical window (z-scored, length = window). */
  mean: number[];
  p25: number[];
  p75: number[];
}

export interface RecipeCanonical {
  windowYears: number;
  byCode: Map<string, CanonicalShape>;
}

/**
 * Canonical per-indicator shape for a recipe, or null when the card carries no
 * `trajectory_alignment` (or the recipe id is unknown).
 */
export function getRecipeCanonical(recipeId: string): RecipeCanonical | null {
  let card: { trajectory_alignment?: TrajectoryAlignment };
  try {
    card = loadCardV3(recipeId) as unknown as {
      trajectory_alignment?: TrajectoryAlignment;
    };
  } catch {
    return null;
  }
  const ta = card?.trajectory_alignment;
  if (!ta || !Array.isArray(ta.indicators) || ta.indicators.length === 0) return null;
  return {
    windowYears: ta.window_years,
    byCode: new Map(ta.indicators.map((i) => [i.code, i.shape])),
  };
}
