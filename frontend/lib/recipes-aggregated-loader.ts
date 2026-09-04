import "server-only";
import type {
  CountryRecipeScoresFile,
  RecipeAggregated,
  RecipesAggregatedFile,
} from "./recipes-aggregated";

/**
 * Server-only loaders for the recipes-aggregated dataset.
 *
 * Split from `lib/recipes-aggregated.ts` so client components can import
 * the types + URL helpers without bundling `fs/promises` (which Webpack /
 * Turbopack can't resolve in the browser bundle and 500s the route).
 *
 * The "server-only" import poisons this module for client use — any
 * accidental client import triggers a build-time error rather than a
 * runtime mystery.
 *
 * #547 (2026-05-01): switched from `*-mock.json` (Week-2 hand-curated
 * scaffold, pipeline_version=mock-v0) to the baked real JSONs produced
 * by `scripts/bake-recipes-aggregated.ts` + `scripts/bake-country-recipe-scores.ts`.
 * Those scripts query Athena `qgi_data.recipes_aggregated` (#462) and
 * `qgi_data.country_recipe_scores` (#463) directly. The mock files are
 * retained in the repo as fallback / test fixtures.
 */

export async function loadRecipesAggregated(): Promise<RecipesAggregatedFile> {
  const fs = await import("fs/promises");
  const path = await import("path");
  const filePath = path.join(process.cwd(), "data", "recipes-aggregated.json");
  const raw = await fs.readFile(filePath, "utf-8");
  return JSON.parse(raw) as RecipesAggregatedFile;
}

export async function loadRecipeBySlug(slug: string): Promise<RecipeAggregated | null> {
  const data = await loadRecipesAggregated();
  return data.recipes.find((r) => r.event_category === slug) ?? null;
}

export async function loadCountryRecipeScores(): Promise<CountryRecipeScoresFile> {
  const fs = await import("fs/promises");
  const path = await import("path");
  const filePath = path.join(process.cwd(), "data", "country-recipe-scores.json");
  const raw = await fs.readFile(filePath, "utf-8");
  return JSON.parse(raw) as CountryRecipeScoresFile;
}

export async function getCountrySignals(
  countrySlug: string
): Promise<Array<{ event_category: string; score: number }>> {
  const data = await loadCountryRecipeScores();
  const entry = data.scores[countrySlug];
  if (!entry) return [];
  return Object.entries(entry)
    .map(([event_category, score]) => ({ event_category, score }))
    .sort((a, b) => b.score - a.score);
}
