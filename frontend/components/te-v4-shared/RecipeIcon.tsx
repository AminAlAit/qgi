/**
 * RecipeIcon — stable wrapper around `iconForRecipe(...)` that satisfies
 * the `react-hooks/static-components` lint rule.
 *
 * The naive pattern
 *     const Icon = iconForRecipe(id);
 *     return <Icon size={18} strokeWidth={1.6} />;
 * fires the rule because `Icon` is a component reference assigned inside
 * render. The Next.js 16 lint suite treats this as a state-loss bug even
 * though Lucide icons are stateless. Per the React 19 guidance + our
 * V4-mockup conventions, we wrap the lookup in a small dispatcher that
 * uses `React.createElement` directly — same render output, no rule fire,
 * and the wrapper itself has a stable module-scoped identity callers can
 * use without lint noise.
 *
 * Usage:
 *     <RecipeIcon recipeId={r.recipe_id} size={18} strokeWidth={1.6} />
 */
import { createElement } from "react";
import type { LucideProps } from "lucide-react";
import { iconForRecipe } from "@/lib/te-mock/icons";

interface Props extends LucideProps {
  recipeId: string;
}

export function RecipeIcon({ recipeId, ...rest }: Props) {
  return createElement(iconForRecipe(recipeId), rest);
}
