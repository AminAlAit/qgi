/**
 * TE analogs contract.
 *
 * Source: `data/te-fleet-run-1/analogs/current-state-analogs.json`
 * Shape verified from real files (fleet-run-1, 216 entries).
 *
 * Breaking change from sample-10: entries now carry `iso2` (ISO 3166-1 alpha-2)
 * as the primary country key; `iso` remains null for all 216 entries. The
 * `nearest-analog-data.ts` buildAllEntries() uses ISO2_TO_ISO3 to resolve the
 * 3-letter code needed by URL routing and getCurrentCountry() lookups.
 */

export interface AnalogEntry {
  country: string;
  /** ISO 3166-1 alpha-2 lowercase for this analogue country (present in the
   *  bake; used to join the curated what-happened-next narratives). */
  country_iso2?: string | null;
  year: number;
  match_score: number;
  primary_recipe_id: string;
  what_happened_next: string | null;
  weak_analog: boolean;
}

export interface AnalogContributionEntry {
  recipe_id: string;
  recipe_label: string;
  l1_color: string;
  contribution_pct: number;
  status: string;
}

export interface CurrentStateAnalogEntry {
  /** null in fleet-run-1 — resolve via iso2 + ISO2_TO_ISO3 map. */
  iso: string | null;
  /** ISO 3166-1 alpha-2 lowercase — present in fleet-run-1, null in sample-10. */
  iso2: string | null;
  name: string;
  region: string | null;
  /** null — per-indicator trajectory not yet emitted by the bake. */
  indicator_trajectory: unknown | null;
  analogs: AnalogEntry[];
  contributions: AnalogContributionEntry[];
}

export interface CurrentStateAnalogs {
  vintage: string;
  entries: CurrentStateAnalogEntry[];
}
