/**
 * Types and loader for data/recipe-tracker.json — the trend status board
 * (rendered at /blog/trend-tracker; "Trends" is the user-facing name for
 * what the pipeline calls recipes — the file and ids keep the pipeline
 * vocabulary because the qgi-ml bake reads description_compelling from
 * this file by name).
 *
 * Schema: recipe-tracker-v1. 69 active trends across 8 L1 families
 * (2 deactivated 2026-06-20: natural_disaster, epidemic_and_pandemic —
 * exogenous-shock methodology category error per founder authorization).
 * Server-side only — reads the baked snapshot at SSR/build time.
 *
 * Tier ladder (confidence-tier-policy, ratified 2026-05-31), refreshed per
 * fleet-run vintage (current: te-fleet-run-2, walked 2026-06-01):
 *   validated     → cleared every validation gate (none yet; the bar is hard)
 *   directional   → in play on the dashboard; calibration pending (8)
 *   experimental  → walked, did not clear the gates (34)
 *   queued        → not yet walked (27)
 *
 * `status` is the legacy vocabulary kept for back-compat with older
 * consumers; new surfaces should read `tier`. `vintages[]` is append-only
 * per the run-separation rule — one row per fleet-run walk, never
 * overwritten.
 */
import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type RecipeStatus =
  | "graduated"
  | "in_progress"
  | "live_legacy"
  | "walked_no_graduation"
  | "queued";

export type RecipeTier = "validated" | "directional" | "experimental" | "queued";

export type RecipeAudience = "in_play" | "coming_soon" | "prior_version";

export interface RecipeStats {
  loco_auc?: number;
  ci95_lo?: number;
  ci95_hi?: number;
  window_y?: number;
  n_indicators?: number;
  n_countries_scored?: number;
  verdict?: string;
  tier_label_user_facing?: string;
}

export interface RecipeVintageRow extends RecipeStats {
  vintage: string;
  tier?: RecipeTier;
  v1_separation_pp?: number;
  v4_oot_recall?: number;
  blog_url?: string;
}

export interface Recipe {
  recipe_id: string;
  label: string;
  l1_id: string;
  l1_label: string;
  l1_color: string;
  l2_label: string;
  status: RecipeStatus;
  tier: RecipeTier;
  audience: RecipeAudience;
  stats?: RecipeStats | null;
  vintages?: RecipeVintageRow[];
  /**
   * When true, recipe is excluded from the trend catalog and all counts.
   * Set in recipe-tracker.json. The loader strips these from the returned
   * recipes array so no consumer needs to re-filter.
   */
  deactivated?: boolean;
  deactivation_reason?: string;
}

export interface RecipeTrackerData {
  generated: string;
  schema: string;
  vintage_current: string;
  n_recipes: number;
  status_counts: Record<string, number>;
  tier_counts: Record<RecipeTier, number>;
  recipes: Recipe[];
}

export interface RecipeFamily {
  l1_id: string;
  l1_label: string;
  l1_color: string;
  recipes: Recipe[];
}

// ---------------------------------------------------------------------------
// Loader
// ---------------------------------------------------------------------------

const TRACKER_FILE = path.join(process.cwd(), "data", "recipe-tracker.json");

let _cache: RecipeTrackerData | null = null;

/**
 * Load the trend tracker data. Throws if the file is missing or malformed.
 * Cached in-process after the first read.
 *
 * Deactivated recipes (deactivated: true) are stripped from the returned
 * recipes array. The n_recipes and tier_counts in recipe-tracker.json are
 * already updated to reflect the active-only count (69 as of 2026-06-20).
 */
export async function loadRecipeTracker(): Promise<RecipeTrackerData> {
  if (_cache !== null) return _cache;
  const raw = await fs.readFile(TRACKER_FILE, "utf-8");
  const parsed = JSON.parse(raw) as RecipeTrackerData;
  if (!parsed.recipes || !Array.isArray(parsed.recipes)) {
    throw new Error("recipe-tracker.json malformed: missing recipes array");
  }
  if (parsed.schema !== "recipe-tracker-v1") {
    throw new Error(
      `recipe-tracker.json schema '${parsed.schema}' unsupported; expected 'recipe-tracker-v1'`
    );
  }
  // Strip deactivated recipes from the public-facing data. Scores/events are
  // preserved on disk; they just do not appear in the trend catalog or counts.
  const active = { ...parsed, recipes: parsed.recipes.filter((r) => !r.deactivated) };
  _cache = active;
  return active;
}

/**
 * Group trends by L1 family, preserving the canonical L1 order (A–H).
 */
export function groupByFamily(recipes: Recipe[]): RecipeFamily[] {
  const map = new Map<string, RecipeFamily>();
  for (const recipe of recipes) {
    const existing = map.get(recipe.l1_id);
    if (existing) {
      existing.recipes.push(recipe);
    } else {
      map.set(recipe.l1_id, {
        l1_id: recipe.l1_id,
        l1_label: recipe.l1_label,
        l1_color: recipe.l1_color,
        recipes: [recipe],
      });
    }
  }
  // Sort by l1_id (A–H) to guarantee canonical order
  return Array.from(map.values()).sort((a, b) => a.l1_id.localeCompare(b.l1_id));
}

/**
 * User-facing label for a confidence tier. NOTE the vocabulary layering
 * (aligned with /trends, 2026-06-06): "in play" is the AUDIENCE word and it
 * covers every walked trend (all 44 this vintage) — the /trends gallery
 * chips all of them "in play". The tier ladder grades confidence WITHIN the
 * in-play set, so the board badges tiers by their own names and reserves
 * "Coming soon" (the /trends word) for the not-yet-walked.
 */
export function tierBadgeLabel(tier: RecipeTier): string {
  switch (tier) {
    case "validated":
      return "Validated";
    case "directional":
      return "Directional";
    case "experimental":
      return "Experimental";
    case "queued":
      return "Coming soon";
    default:
      // Exhaustiveness guard: a new RecipeTier member fails compilation here.
      return tier satisfies never;
  }
}
