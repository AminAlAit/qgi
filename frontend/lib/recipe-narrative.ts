/**
 * Recipe-slug → display-name rewriting for buyer-facing prose.
 *
 * Used by `lib/buyer-view.ts` to rewrite recipe slugs that the bake
 * script wrote into prose fields (e.g. `mechanism_narrative` opening
 * with `civil_war_and_insurgency predicts...` instead of the display
 * name "Civil war and insurgency").
 *
 * Sentence-case-aware: at sentence start, the display name is rendered
 * verbatim (already capitalized). Mid-sentence, the first letter is
 * lowercased so prose stays grammatical.
 *
 * Cross-recipe references: a recipe's prose can mention OTHER recipes
 * by slug ("under D5, elections_and_voting uses..."). Callers pass the
 * FULL slug map for the entire stack so all references rewrite.
 *
 * Long-term plan: bake script (`qgi-ml/#683`) writes display-name prose
 * directly; this module then becomes a no-op.
 *
 * Isolated test coverage: `lib/__tests__/recipe-narrative.test.ts`.
 */
import type { MlRecipeEntry } from "@/lib/recipes-ml";

/** Build a slug → display-name map from a recipe list. */
export function buildSlugMap(
  recipes: ReadonlyArray<MlRecipeEntry>
): Record<string, string> {
  const map: Record<string, string> = {};
  for (const r of recipes) {
    if (r.recipe_id && r.display_name) {
      map[r.recipe_id] = r.display_name;
    }
  }
  return map;
}

/**
 * Replace every occurrence of any known recipe slug with its display
 * name in `prose`. Word-boundary-aware: slug chars are `[a-z_]`, so we
 * look for slugs surrounded by non-slug-char boundaries (start of
 * string, punctuation, whitespace).
 *
 * Sentence-start handling: when a slug appears at position 0 (or after
 * a sentence-ending punctuation), the replacement uses the display name
 * verbatim. Mid-sentence, first letter of the display name is
 * lowercased to keep grammar.
 */
export function rewriteRecipeSlugsInProse(
  prose: string,
  slugMap: Record<string, string>
): string {
  if (!prose) return prose;
  let result = prose;
  for (const [slug, displayName] of Object.entries(slugMap)) {
    // Match slug as a whole "word" — surrounded by non-slug-char boundaries.
    const regex = new RegExp(`(^|[^a-z_])(${escapeRegex(slug)})(?=[^a-z_]|$)`, "g");
    result = result.replace(regex, (_match, before: string) => {
      // Sentence start = BOL or after .!? followed by optional whitespace.
      const isSentenceStart = before === "" || /[.!?]\s*$/.test(before);
      const replacement = isSentenceStart
        ? displayName
        : displayName.charAt(0).toLowerCase() + displayName.slice(1);
      return before + replacement;
    });
  }
  return result;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
