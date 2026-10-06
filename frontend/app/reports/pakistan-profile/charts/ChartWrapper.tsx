"use client";

/**
 * Client wrapper for Pakistan report charts.
 *
 * `ssr: false` must be placed inside a "use client" file (Next.js 16 requirement —
 * see node_modules/next/dist/docs/01-app/02-guides/lazy-loading.md).
 * This module re-exports dynamic() wrappers so the server-component page.tsx
 * can import them without violating the ssr:false placement rule.
 */

import dynamic from "next/dynamic";

export const ChartMultiRecipeConvergenceHero = dynamic(
  () =>
    import("./ChartMultiRecipeConvergence").then(
      (m) => m.ChartMultiRecipeConvergenceHero
    ),
  { ssr: false }
);

export const ChartMultiRecipeConvergence = dynamic(
  () => import("./ChartMultiRecipeConvergence"),
  { ssr: false }
);

export const ChartSelfAnalogueHero = dynamic(
  () => import("./ChartSelfAnalogue").then((m) => m.ChartSelfAnalogueHero),
  { ssr: false }
);

export const ChartSelfAnalogue = dynamic(() => import("./ChartSelfAnalogue"), {
  ssr: false,
});
