/**
 * Loader for `data/ml-recipe-stack.json` — the V2-shipped ML recipe stack.
 *
 * Used by `/trends{a,b}` + `/signals-v2{a,b}` route handlers (#645
 * + #655). Server-side only; reads the baked snapshot at SSR time.
 *
 * Per #643's bake-script contract, this file is committed alongside the
 * canonical `qgi-data/reference/ml-recipe-stack-2026-05.json` but never
 * fetched at runtime — it's a build-time artifact baked into the deploy.
 *
 * Schema version: 1.0. Consumers must check `metadata.schema_version` if
 * they need to handle breaking changes; today there's only one version.
 */
import "server-only";

import { promises as fs } from "node:fs";
import path from "node:path";
import type { MlRecipeEntry, MlRecipeStack } from "./recipes-ml";

const STACK_FILE = path.join(process.cwd(), "data", "ml-recipe-stack.json");

/** Cached singleton — read once per Lambda cold start. */
let _stackCache: MlRecipeStack | null = null;

/**
 * Load the full ML recipe stack. Throws if the file is missing or malformed.
 * Server-only — do not call from client components.
 */
export async function loadMlRecipeStack(): Promise<MlRecipeStack> {
  if (_stackCache !== null) return _stackCache;
  const raw = await fs.readFile(STACK_FILE, "utf-8");
  const parsed = JSON.parse(raw) as MlRecipeStack;
  if (!parsed.metadata || !Array.isArray(parsed.recipes)) {
    throw new Error(`ml-recipe-stack.json malformed: missing metadata or recipes array`);
  }
  if (parsed.metadata.schema_version !== "1.0") {
    throw new Error(
      `ml-recipe-stack.json schema_version ${parsed.metadata.schema_version} ` +
        `unsupported; expected '1.0'`
    );
  }
  _stackCache = parsed;
  return parsed;
}

/**
 * Look up a single recipe by slug (== `recipe_id`). Returns null if the
 * recipe isn't in the top-4 ship list — this enforces the SEO/metadata
 * invariant so future bakes with `n_recipes > 4` cannot leak metadata for
 * non-ship recipes via `generateMetadata`.
 */
export async function loadMlRecipeBySlug(slug: string): Promise<MlRecipeEntry | null> {
  const stack = await loadMlRecipeStack();
  const recipe = stack.recipes.find((r) => r.recipe_id === slug);
  if (!recipe) return null;
  if (!stack.metadata.top_4_recipes.includes(recipe.recipe_id)) return null;
  return recipe;
}

/**
 * Test-only: clear the singleton cache between tests so changes to the
 * underlying file or to mocks take effect.
 */
export function _resetMlRecipeStackCache(): void {
  _stackCache = null;
}
