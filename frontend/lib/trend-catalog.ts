/**
 * Client-safe trend catalog for the Trend-focus picker (settings).
 *
 * Derived from data/recipe-tracker.json (the canonical 71-trend roster). We map
 * it down to just {slug, label, l1Label} at module load so the picker has a
 * stable, sorted list without pulling the heavy per-recipe stats into logic.
 * The `slug` (recipe_id) is the same identity the Risk Board rows use, so a
 * focus selection filters the board directly.
 */
import tracker from "@/data/recipe-tracker.json";

export interface TrendCatalogEntry {
  slug: string;
  label: string;
  l1Label: string;
}

interface RawRecipe {
  recipe_id: string;
  label: string;
  l1_label: string;
}

export const TREND_CATALOG: TrendCatalogEntry[] = (
  (tracker as { recipes: RawRecipe[] }).recipes ?? []
)
  .map((r) => ({ slug: r.recipe_id, label: r.label, l1Label: r.l1_label }))
  .sort((a, b) => a.label.localeCompare(b.label));

export const TREND_LABEL: Map<string, string> = new Map(
  TREND_CATALOG.map((t) => [t.slug, t.label])
);
