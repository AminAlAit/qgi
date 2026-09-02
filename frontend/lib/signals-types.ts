/**
 * Shared type definitions for the signals surface.
 *
 * 2026-05-28: extracted from `app/(app)/signals/page.tsx` and sibling
 * pages when those routes were deleted as part of the V4.1 canonical
 * promotion. The legacy components in `components/signals/` import from
 * this file instead of from the deleted page files.
 */

import type { L1Group } from "@/lib/category-taxonomy";
import type { BuyerMlRecipe } from "@/lib/buyer-view";

export type SignalTier = "HIGH" | "MODERATE" | "INDICATIVE";

/** One row in the top-level signals index — one category, panel-wide max. */
export interface SignalRow {
  category: string;
  display_name: string;
  tier: SignalTier;
  /** Per-category max salience across all firing countries. */
  max_salience: number;
  /** Mean salience across firing countries. */
  avg_salience: number;
  /** Number of countries with non-zero salience for this category. */
  firing_count: number;
  /** Top-3 countries by salience. */
  top_countries: Array<{ id: string; name: string; alpha_2: string; salience: number }>;
  /** L1 group metadata; null when category isn't in CATEGORY_L1_MAP. */
  l1: L1Group | null;
}

/** One row in the per-country signals drill-down. */
export interface CountrySignalRow {
  category: string;
  display_name: string;
  tier: SignalTier;
  /** Max salience for this category in this country across all tier windows. */
  salience: number;
  /** L1 group metadata; null when the category isn't in CATEGORY_L1_MAP. */
  l1: L1Group | null;
}

/** Stat panel from the per-category leaf detail page. */
export interface LeafStatPanel {
  /** Max salience-z across all tier windows for this country/category. */
  max_salience: number;
  /** Per-tier window breakdown ({S,M,L,XL} → salience-z, where present). */
  by_window: Array<{ window: string; salience: number }>;
}

/** ML panel from the per-category leaf detail page. */
export interface LeafMlPanel {
  recipe: BuyerMlRecipe;
  is_top_4: boolean;
}
