/**
 * cleanEmDashes — strip the em-dash (—, U+2014) from rendered copy.
 *
 * House style (founder, 2026-06-04): no "AI em-dash" in user-facing text.
 * Most of our prose is bake-generated data — trend hero definitions, the 1,200+
 * precedent event labels, card descriptions — so we clean at RENDER time rather
 * than editing the data files. That way a re-bake can never reintroduce them.
 *
 * An em-dash (with any surrounding spaces) collapses to a comma + space, which
 * reads naturally whether it separated an appositive mid-sentence ("X — a shift
 * — Y" → "X, a shift, Y") or a title from a descriptor ("Crisis — Conflict" →
 * "Crisis, Conflict"). En-dashes (–) in numeric ranges are left untouched; they
 * are correct typography, not the thing the rule is about.
 */
export function cleanEmDashes(s: string): string {
  if (!s) return s;
  return (
    s
      .replace(/\s*—\s*/g, ", ")
      // Guard the rare cases where the dash sat next to existing punctuation.
      .replace(/,\s*,/g, ",")
      .replace(/^\s*,\s*/, "")
  );
}

/**
 * Replace the standalone product noun "recipe(s)" → "trend(s)" (case-preserving)
 * in bake-generated prose where the backend still emits the old word — e.g. the
 * activity-feed event notes. `\b` does not match before "_", so code-like tokens
 * (`recipe_id`, `recipe_label`) are left intact; only the English word changes.
 */
export function recipeWordToTrend(s: string): string {
  if (!s) return s;
  return s
    .replace(/\bRecipes\b/g, "Trends")
    .replace(/\bRecipe\b/g, "Trend")
    .replace(/\brecipes\b/g, "trends")
    .replace(/\brecipe\b/g, "trend");
}

/** Bake-prose cleaner: drop em-dashes AND rename the recipe→trend product noun. */
export function cleanProseCopy(s: string): string {
  return cleanEmDashes(recipeWordToTrend(s));
}
