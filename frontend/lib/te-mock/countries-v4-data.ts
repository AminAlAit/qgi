/**
 * countries-v4-data — country hub data for /countries-v4 pages.
 *
 * V4.1 wire-up (2026-05-29):
 *   - SEEDS remain the primary source of driver/trajectory/population data.
 *   - TE sample-10 scores are overlaid on top_recipes when a TE recipe row
 *     matches a seed's recipesLit entry by recipe_id. This keeps drivers
 *     honest (seed-authored, not fabricated from scores) while surfacing
 *     real discrimination ranks.
 *   - country-index.json (214 entries) backfills iso2/flag_emoji for any
 *     country that appears in scores but not in SEEDS.
 *   - vintage is sourced from the country-index for TE countries.
 *
 * Each country carries:
 *   - identity (iso, name, region, flag_emoji, population, vintage)
 *   - aggregate (compound_score, recipes_lit_count, recipes_lit_graduated)
 *   - top_recipes: list of {recipe_id, score, label, l1 metadata, status}
 *   - drivers: the top few (3-5) V-Dem/WB/WGI indicators currently moving for
 *     this country, each with a 12-quarter trajectory
 *   - momentum: per-top-recipe 12-quarter rank-history sparkline data
 *   - analogs: top-3 historical pre-event-shape matches (foreign keys to
 *     nearest-analog-data when available; plausible fabrications otherwise)
 *   - lit_families: derived list of distinct L1 families lit
 *
 * All scores are discrimination ranks, NOT probabilities.
 */
import recipeTracker from "@/data/recipe-tracker.json";
import { getRecipe, type TrackerRecipe, type RecipeStatus } from "@/lib/te-mock/recipes";
import {
  loadAllScores,
  loadAnalogs,
  loadCardV3,
  loadCountryIndex,
  FLEET_RUN_1_RECIPE_IDS,
} from "@/lib/te-data-contract/load";
import { NAME_TO_ISO2, flagFromIso2 } from "@/lib/te-mock/country-iso2";
import { getIndicatorLabel } from "@/lib/indicator-labels";
import { whnBlurb } from "@/lib/curation/what-happened-next";

export interface CountryTopRecipe {
  recipe_id: string;
  label: string;
  score: number;
  l1_id: string;
  l1_label: string;
  l1_color: string;
  status: RecipeStatus;
}

/**
 * R&D reply §Q4 (docs-specs #169): drivers are split into two distinct
 * concepts that must NEVER be conflated in copy.
 *
 *   - CountryDriverAttribution → "why this country scores high":
 *     SHAP signal_share_pct per indicator. Sums to ~100 across the
 *     recipe's indicators. Capability #14 in the ledger.
 *
 *   - CountryDriverMovement → "what's moving in the panels":
 *     Z-trajectory of an indicator + observed z_score_change. Capability
 *     #15 alignment (the observable-substrate side).
 */
export interface CountryDriverAttribution {
  indicator_code: string;
  indicator_name: string;
  provider: string;
  /** SHAP-derived signal share for THIS recipe; 0..100, sums to ~100 across the 4 indicators. */
  signal_share_pct: number;
  /** Which recipe this attribution belongs to — drivers_attribution is per-recipe. */
  recipe_id: string;
  /** Round-2: +1 = risk-increasing, -1 = risk-decreasing. null if not available. */
  direction_sign?: number | null;
}

export interface CountryDriverMovement {
  indicator_code: string;
  indicator_name: string;
  provider: string;
  direction: "rising" | "falling" | "volatile" | "flat";
  /** 12 quarterly values in the recipe-scoring scale (0..100). */
  trajectory: number[];
  /** Observed standardized change over the visible window. */
  z_score_change: number;
  /** Round-2: raw indicator value at eval_year. null if unavailable. */
  latest_raw_value?: number | null;
  /** Round-2: raw indicator value at the prior year. null if unavailable. */
  prior_raw_value?: number | null;
  /** Round-2: unit hint string (e.g. "%", "z-score (V-Dem)"). null if unavailable. */
  unit?: string | null;
}

/** @deprecated Use CountryDriverMovement. Kept as an alias for prior-callsite compat. */
export type CountryDriver = CountryDriverMovement;

export interface CountryMomentum {
  recipe_id: string;
  label: string;
  l1_color: string;
  /** 12 quarterly rank-position values in the 0..100 score scale. */
  rank_history: number[];
  /**
   * Round-2: multi-year score history from momentum_scores_by_year.
   * Keys are year strings ("2023".."2026"), values are scores 0..100.
   * Populated from the bake corpus; empty object = first vintage only.
   */
  year_scores: Record<string, number>;
  /** Round-2: momentum label (rising/falling/flat/suppressed). null if unavailable. */
  momentum_label: string | null;
}

export interface SensitivityItem {
  indicator_code: string;
  indicator_name: string;
  marginal_points_per_unit: number;
  current_cosine: number;
  headroom: number;
  headroom_points: number;
}

export interface CountryAnalog {
  country: string;
  year: number;
  match_score: number;
  primary_recipe_id: string;
  what_happened_next: string;
  weak_analog?: boolean;
}

export interface CountryLitFamily {
  l1_id: string;
  l1_label: string;
  l1_color: string;
}

export interface CountryV4 {
  iso: string;
  name: string;
  region: string;
  flag_emoji: string;
  population: number;
  compound_score: number;
  recipes_lit_count: number;
  recipes_lit_graduated: number;
  top_recipes: CountryTopRecipe[];
  /**
   * SHAP attribution: why this country scores high on its TOP-LIT recipe.
   * Per R&D reply §Q4 — distinct from movement. Sums to ~100.
   */
  drivers_attribution: CountryDriverAttribution[];
  /**
   * Indicator movement: what's currently moving in the input panels for
   * this country. Distinct from attribution; never conflate in copy.
   */
  drivers_movement: CountryDriverMovement[];
  /** @deprecated alias of drivers_movement during the schema-align cutover. */
  drivers: CountryDriverMovement[];
  momentum: CountryMomentum[];
  analogs: CountryAnalog[];
  lit_families: CountryLitFamily[];
  vintage: string;
  /**
   * Round-2: per-indicator sensitivity — "what would move the score".
   * Populated from sensitivity_per_indicator[] in the scores bake.
   * Empty array = not yet scored on any TE recipe.
   */
  sensitivity: SensitivityItem[];
  /**
   * Round-2: 12-pt composite indicator trajectory from the bake.
   * Mean of selected indicators z-scores. Empty array = not available.
   */
  indicator_trajectory_composite_12q: number[];
}

const VINTAGE = (recipeTracker as { generated: string }).generated;

export const REGION_ORDER = [
  "Africa",
  "Americas",
  "Asia-Pacific",
  "Europe",
  "MENA",
] as const;

// Country of the week — Kwame's curated mock pick. Iran is the densest
// single-state compound case currently on the board.
export const COUNTRY_OF_THE_WEEK_ISO = "IRN";

// ── Mini seed format ─────────────────────────────────────────────────────
// `recipesLit` carries (recipe_id, score) pairs the country fires on;
// every score is treated as a discrimination rank (0..100). We hydrate
// each pair against the tracker JSON to attach L1 metadata + current
// status, then derive everything else.

interface Seed {
  iso: string;
  name: string;
  region: string;
  flag: string;
  population: number;
  recipesLit: Array<[string, number]>;
  drivers: Array<{
    code: string;
    name: string;
    provider: string;
    shape: "rising" | "falling" | "flat";
    from: number;
    to: number;
  }>;
  analogs?: CountryAnalog[];
}

const SEEDS: Seed[] = [
  // ── MENA ────────────────────────────────────────────────────────────────
  {
    iso: "IRN",
    name: "Iran",
    region: "MENA",
    flag: "🇮🇷",
    population: 89_172_767,
    recipesLit: [
      ["foreign_intervention", 98.1],
      ["political_repression", 81.4],
      ["sanctions_and_arms_embargo", 78.9],
      ["mass_protest", 72.4],
      ["human_rights_violation", 68.7],
      ["currency_crisis", 64.2],
    ],
    drivers: [
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 68,
        to: 38,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 52,
        to: 24,
      },
      {
        code: "v2elintmon",
        name: "International election monitoring",
        provider: "V-Dem",
        shape: "falling",
        from: 45,
        to: 18,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 84,
      },
      {
        code: "v2stfisccap",
        name: "State fiscal source",
        provider: "V-Dem",
        shape: "falling",
        from: 58,
        to: 32,
      },
    ],
  },
  {
    iso: "LBN",
    name: "Lebanon",
    region: "MENA",
    flag: "🇱🇧",
    population: 5_490_000,
    recipesLit: [
      ["currency_crisis", 71.8],
      ["banking_and_financial_crisis", 68.5],
      ["economic_recession", 65.4],
      ["mass_protest", 61.2],
    ],
    drivers: [
      {
        code: "FB.AST.NPER.ZS",
        name: "Bank NPL ratio",
        provider: "World Bank",
        shape: "rising",
        from: 32,
        to: 76,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 88,
      },
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "rising",
        from: 51,
        to: 82,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 48,
        to: 22,
      },
      {
        code: "v2x_civlib",
        name: "Civil liberties",
        provider: "V-Dem",
        shape: "falling",
        from: 62,
        to: 44,
      },
    ],
  },
  {
    iso: "TUR",
    name: "Türkiye",
    region: "MENA",
    flag: "🇹🇷",
    population: 85_341_241,
    recipesLit: [
      ["currency_crisis", 71.2],
      ["economic_recession", 68.5],
      ["executive_power_consolidation", 68.7],
      ["political_repression", 58.4],
      ["earthquake", 68.7],
    ],
    drivers: [
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 34,
        to: 78,
      },
      {
        code: "v2x_jucon",
        name: "Judicial Constraints on Executive",
        provider: "V-Dem",
        shape: "falling",
        from: 55,
        to: 29,
      },
      {
        code: "v2xlg_legcon",
        name: "Legislative Constraints on Executive",
        provider: "V-Dem",
        shape: "falling",
        from: 52,
        to: 31,
      },
      {
        code: "NE.RSB.GNFS.ZS",
        name: "External balance % GDP",
        provider: "World Bank",
        shape: "falling",
        from: 50,
        to: 26,
      },
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shape: "falling",
        from: 58,
        to: 38,
      },
    ],
  },
  {
    iso: "EGY",
    name: "Egypt",
    region: "MENA",
    flag: "🇪🇬",
    population: 110_990_000,
    recipesLit: [
      ["political_repression", 64.1],
      ["currency_crisis", 61.7],
      ["economic_recession", 56.3],
      ["water_crisis", 53.4],
    ],
    drivers: [
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 36,
        to: 72,
      },
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 48,
        to: 28,
      },
      {
        code: "v2cseeorgs",
        name: "CSO entry/exit",
        provider: "V-Dem",
        shape: "falling",
        from: 45,
        to: 24,
      },
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "rising",
        from: 58,
        to: 84,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 42,
        to: 28,
      },
    ],
  },
  {
    iso: "TUN",
    name: "Tunisia",
    region: "MENA",
    flag: "🇹🇳",
    population: 12_356_000,
    recipesLit: [
      ["constitutional_change", 58.3],
      ["democratic_transition", 54.2],
      ["currency_crisis", 51.4],
    ],
    drivers: [
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "falling",
        from: 72,
        to: 51,
      },
      {
        code: "v2juncind",
        name: "Judicial independence",
        provider: "V-Dem",
        shape: "falling",
        from: 65,
        to: 42,
      },
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "rising",
        from: 52,
        to: 78,
      },
      {
        code: "v2lginvstp",
        name: "Legislative investigates exec",
        provider: "V-Dem",
        shape: "falling",
        from: 62,
        to: 38,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 41,
        to: 64,
      },
    ],
  },
  {
    iso: "YEM",
    name: "Yemen",
    region: "MENA",
    flag: "🇾🇪",
    population: 33_697_000,
    recipesLit: [
      ["humanitarian_crisis", 81.2],
      ["foreign_intervention", 79.8],
      ["civil_war_and_insurgency", 74.5],
      ["drought_and_famine", 66.4],
      ["economic_recession", 58.9],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 48,
        to: 82,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 74,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 32,
        to: 14,
      },
      {
        code: "v2x_clphy",
        name: "Physical Violence Index",
        provider: "V-Dem",
        shape: "rising",
        from: 45,
        to: 81,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 35,
        to: 76,
      },
    ],
  },

  // ── Africa ──────────────────────────────────────────────────────────────
  {
    iso: "SDN",
    name: "Sudan",
    region: "Africa",
    flag: "🇸🇩",
    population: 47_958_856,
    recipesLit: [
      ["humanitarian_crisis", 78.4],
      ["civil_war_and_insurgency", 71.2],
      ["foreign_intervention", 65.8],
      ["drought_and_famine", 62.1],
      ["mass_protest", 58.7],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 35,
        to: 82,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 40,
        to: 84,
      },
      {
        code: "VC.IDP.NWDS",
        name: "New internal displacements",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 78,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 32,
        to: 12,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 30,
        to: 14,
      },
    ],
  },
  {
    iso: "ETH",
    name: "Ethiopia",
    region: "Africa",
    flag: "🇪🇹",
    population: 126_527_060,
    recipesLit: [
      ["ethnic_and_communal_conflict", 64.7],
      ["civil_war_and_insurgency", 61.2],
      ["drought_and_famine", 58.9],
    ],
    drivers: [
      {
        code: "v2pepwrses",
        name: "Power Distributed by Social Group",
        provider: "V-Dem",
        shape: "falling",
        from: 52,
        to: 28,
      },
      {
        code: "VC.IDP.NWDS",
        name: "New internal displacements",
        provider: "World Bank",
        shape: "rising",
        from: 32,
        to: 68,
      },
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 74,
      },
      {
        code: "v2xeg_eqprotec",
        name: "Equal Protection Index",
        provider: "V-Dem",
        shape: "falling",
        from: 48,
        to: 26,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 41,
        to: 22,
      },
    ],
  },
  {
    iso: "NGA",
    name: "Nigeria",
    region: "Africa",
    flag: "🇳🇬",
    population: 223_804_000,
    recipesLit: [
      ["ethnic_and_communal_conflict", 62.1],
      ["terrorist_attack", 58.5],
      ["political_violence", 56.3],
      ["poverty_and_inequality_crisis", 54.1],
    ],
    drivers: [
      {
        code: "v2x_corr",
        name: "Political Corruption Index",
        provider: "V-Dem",
        shape: "rising",
        from: 55,
        to: 78,
      },
      {
        code: "VC.IHR.PSRC.P5",
        name: "Intentional homicide rate",
        provider: "World Bank",
        shape: "rising",
        from: 48,
        to: 72,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 41,
        to: 76,
      },
      {
        code: "v2pepwrses",
        name: "Power Distributed by Social Group",
        provider: "V-Dem",
        shape: "falling",
        from: 52,
        to: 32,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 45,
        to: 28,
      },
    ],
  },
  {
    iso: "COD",
    name: "DR Congo",
    region: "Africa",
    flag: "🇨🇩",
    population: 102_262_000,
    recipesLit: [
      ["humanitarian_crisis", 71.5],
      ["civil_war_and_insurgency", 68.4],
      ["ethnic_and_communal_conflict", 64.2],
      ["resource_conflict", 58.7],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 71,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 68,
      },
      {
        code: "v2x_corr",
        name: "Political Corruption Index",
        provider: "V-Dem",
        shape: "rising",
        from: 64,
        to: 81,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 28,
        to: 14,
      },
      {
        code: "VC.IDP.NWDS",
        name: "New internal displacements",
        provider: "World Bank",
        shape: "rising",
        from: 35,
        to: 64,
      },
    ],
  },
  {
    iso: "GNQ",
    name: "Equatorial Guinea",
    region: "Africa",
    flag: "🇬🇶",
    population: 1_795_000,
    recipesLit: [
      ["foreign_intervention", 96.9],
      ["political_corruption", 71.4],
      ["political_repression", 65.2],
    ],
    drivers: [
      {
        code: "v2x_corr",
        name: "Political Corruption Index",
        provider: "V-Dem",
        shape: "rising",
        from: 74,
        to: 88,
      },
      {
        code: "v2x_neopat",
        name: "Neopatrimonialism Index",
        provider: "V-Dem",
        shape: "rising",
        from: 78,
        to: 91,
      },
      {
        code: "CC.EST",
        name: "Control of Corruption",
        provider: "World Bank WGI",
        shape: "falling",
        from: 22,
        to: 8,
      },
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 32,
        to: 18,
      },
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shape: "falling",
        from: 28,
        to: 14,
      },
    ],
  },
  {
    iso: "MLI",
    name: "Mali",
    region: "Africa",
    flag: "🇲🇱",
    population: 23_293_000,
    recipesLit: [
      ["military_coup", 76.4],
      ["foreign_intervention", 68.7],
      ["civil_war_and_insurgency", 64.5],
      ["terrorist_attack", 64.2],
    ],
    drivers: [
      {
        code: "v2x_jucon",
        name: "Judicial Constraints on Executive",
        provider: "V-Dem",
        shape: "falling",
        from: 48,
        to: 18,
      },
      {
        code: "v2xlg_legcon",
        name: "Legislative Constraints on Executive",
        provider: "V-Dem",
        shape: "falling",
        from: 42,
        to: 15,
      },
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 36,
        to: 71,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 31,
        to: 11,
      },
      {
        code: "v2exl_legitlead",
        name: "Legitimacy of Leadership",
        provider: "V-Dem",
        shape: "falling",
        from: 45,
        to: 22,
      },
    ],
  },
  {
    iso: "BFA",
    name: "Burkina Faso",
    region: "Africa",
    flag: "🇧🇫",
    population: 23_251_000,
    recipesLit: [
      ["military_coup", 64.8],
      ["terrorist_attack", 61.0],
      ["foreign_intervention", 58.4],
      ["drought_and_famine", 56.7],
    ],
    drivers: [
      {
        code: "v2x_jucon",
        name: "Judicial Constraints on Executive",
        provider: "V-Dem",
        shape: "falling",
        from: 44,
        to: 21,
      },
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 32,
        to: 68,
      },
      {
        code: "v2exl_legitlead",
        name: "Legitimacy of Leadership",
        provider: "V-Dem",
        shape: "falling",
        from: 42,
        to: 24,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 35,
        to: 14,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 28,
        to: 58,
      },
    ],
  },
  {
    iso: "ZAF",
    name: "South Africa",
    region: "Africa",
    flag: "🇿🇦",
    population: 60_414_000,
    recipesLit: [
      ["poverty_and_inequality_crisis", 71.4],
      ["energy_policy", 54.7],
      ["labor_action", 61.8],
    ],
    drivers: [
      {
        code: "SI.POV.GINI",
        name: "Gini index",
        provider: "World Bank",
        shape: "rising",
        from: 78,
        to: 84,
      },
      {
        code: "SL.UEM.1524.ZS",
        name: "Youth unemployment",
        provider: "World Bank",
        shape: "rising",
        from: 65,
        to: 78,
      },
      {
        code: "SL.EMP.VULN.ZS",
        name: "Vulnerable employment %",
        provider: "World Bank",
        shape: "rising",
        from: 52,
        to: 64,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 54,
        to: 38,
      },
      {
        code: "v2x_corr",
        name: "Political Corruption Index",
        provider: "V-Dem",
        shape: "rising",
        from: 51,
        to: 68,
      },
    ],
  },
  {
    iso: "KEN",
    name: "Kenya",
    region: "Africa",
    flag: "🇰🇪",
    population: 55_100_000,
    recipesLit: [
      ["infrastructure_project", 58.4],
      ["ethnic_and_communal_conflict", 52.1],
      ["constitutional_change", 49.7],
    ],
    drivers: [
      {
        code: "BX.KLT.DINV.WD.GD.ZS",
        name: "FDI net inflows",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 58,
      },
      {
        code: "v2pepwrses",
        name: "Power Distributed by Social Group",
        provider: "V-Dem",
        shape: "falling",
        from: 55,
        to: 41,
      },
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "rising",
        from: 52,
        to: 72,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "flat",
        from: 58,
        to: 55,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "flat",
        from: 48,
        to: 46,
      },
    ],
  },

  // ── Americas ────────────────────────────────────────────────────────────
  {
    iso: "ARG",
    name: "Argentina",
    region: "Americas",
    flag: "🇦🇷",
    population: 46_044_000,
    recipesLit: [
      ["currency_crisis", 82.4],
      ["economic_recession", 72.1],
      ["fiscal_policy_change", 68.3],
      ["mass_protest", 61.7],
      ["monetary_policy_change", 59.4],
    ],
    drivers: [
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 51,
        to: 92,
      },
      {
        code: "NE.RSB.GNFS.ZS",
        name: "External balance % GDP",
        provider: "World Bank",
        shape: "falling",
        from: 48,
        to: 22,
      },
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "rising",
        from: 58,
        to: 84,
      },
      {
        code: "v2stfisccap",
        name: "Fiscal Capacity",
        provider: "V-Dem",
        shape: "falling",
        from: 52,
        to: 32,
      },
      {
        code: "BX.KLT.DINV.WD.GD.ZS",
        name: "FDI net inflows",
        provider: "World Bank",
        shape: "falling",
        from: 42,
        to: 24,
      },
    ],
  },
  {
    iso: "VEN",
    name: "Venezuela",
    region: "Americas",
    flag: "🇻🇪",
    population: 28_838_000,
    recipesLit: [
      ["currency_crisis", 78.4],
      ["political_repression", 73.6],
      ["economic_recession", 72.1],
      ["sanctions_and_arms_embargo", 64.8],
      ["mass_protest", 54.5],
      ["oil_and_gas", 74.2],
    ],
    drivers: [
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 61,
        to: 96,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 35,
        to: 81,
      },
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 42,
        to: 14,
      },
      {
        code: "v2x_corr",
        name: "Political Corruption Index",
        provider: "V-Dem",
        shape: "rising",
        from: 68,
        to: 89,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 31,
        to: 9,
      },
    ],
  },
  {
    iso: "BOL",
    name: "Bolivia",
    region: "Americas",
    flag: "🇧🇴",
    population: 12_186_000,
    recipesLit: [
      ["mass_protest", 54.2],
      ["constitutional_change", 52.4],
    ],
    drivers: [
      {
        code: "v2juncind",
        name: "Judicial independence",
        provider: "V-Dem",
        shape: "falling",
        from: 54,
        to: 36,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "falling",
        from: 61,
        to: 48,
      },
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 58,
      },
      {
        code: "NE.RSB.GNFS.ZS",
        name: "External balance % GDP",
        provider: "World Bank",
        shape: "falling",
        from: 52,
        to: 32,
      },
      {
        code: "v2lginvstp",
        name: "Legislative investigates exec",
        provider: "V-Dem",
        shape: "falling",
        from: 55,
        to: 41,
      },
    ],
  },
  {
    iso: "NIC",
    name: "Nicaragua",
    region: "Americas",
    flag: "🇳🇮",
    population: 7_046_000,
    recipesLit: [
      ["political_repression", 71.4],
      ["mass_protest", 54.8],
      ["economic_recession", 51.3],
    ],
    drivers: [
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 48,
        to: 16,
      },
      {
        code: "v2cseeorgs",
        name: "CSO entry/exit",
        provider: "V-Dem",
        shape: "falling",
        from: 45,
        to: 14,
      },
      {
        code: "v2psoppaut",
        name: "Opposition autonomy",
        provider: "V-Dem",
        shape: "falling",
        from: 38,
        to: 12,
      },
      {
        code: "v2juncind",
        name: "Judicial independence",
        provider: "V-Dem",
        shape: "falling",
        from: 42,
        to: 18,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "falling",
        from: 51,
        to: 22,
      },
    ],
  },
  {
    iso: "COL",
    name: "Colombia",
    region: "Americas",
    flag: "🇨🇴",
    population: 51_874_000,
    recipesLit: [
      ["peacekeeping_and_peace_process", 61.5],
      ["transitional_justice", 64.2],
      ["political_violence", 61.4],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "falling",
        from: 64,
        to: 38,
      },
      {
        code: "v2juncind",
        name: "Judicial independence",
        provider: "V-Dem",
        shape: "rising",
        from: 48,
        to: 62,
      },
      {
        code: "v2x_rule",
        name: "Rule of Law Index",
        provider: "V-Dem",
        shape: "rising",
        from: 44,
        to: 58,
      },
      {
        code: "VC.IDP.NWDS",
        name: "New internal displacements",
        provider: "World Bank",
        shape: "falling",
        from: 58,
        to: 35,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 32,
        to: 51,
      },
    ],
  },
  {
    iso: "MEX",
    name: "Mexico",
    region: "Americas",
    flag: "🇲🇽",
    population: 128_455_000,
    recipesLit: [
      ["political_violence", 68.1],
      ["government_formation", 61.7],
      ["public_health_reform", 53.4],
    ],
    drivers: [
      {
        code: "VC.IHR.PSRC.P5",
        name: "Intentional homicide rate",
        provider: "World Bank",
        shape: "rising",
        from: 58,
        to: 76,
      },
      {
        code: "v2x_corr",
        name: "Political Corruption Index",
        provider: "V-Dem",
        shape: "rising",
        from: 54,
        to: 68,
      },
      {
        code: "v2clkill",
        name: "Freedom from Political Killings",
        provider: "V-Dem",
        shape: "falling",
        from: 52,
        to: 32,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "flat",
        from: 48,
        to: 45,
      },
      {
        code: "v2juncind",
        name: "Judicial independence",
        provider: "V-Dem",
        shape: "falling",
        from: 51,
        to: 38,
      },
    ],
  },
  {
    iso: "BRA",
    name: "Brazil",
    region: "Americas",
    flag: "🇧🇷",
    population: 216_422_000,
    recipesLit: [
      ["poverty_and_inequality_crisis", 64.8],
      ["religious_and_social_movement", 51.4],
      ["monetary_policy_change", 54.8],
    ],
    drivers: [
      {
        code: "SI.POV.GINI",
        name: "Gini index",
        provider: "World Bank",
        shape: "rising",
        from: 68,
        to: 75,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 61,
      },
      {
        code: "v2csprtcpt",
        name: "CSO Participatory Env.",
        provider: "V-Dem",
        shape: "rising",
        from: 51,
        to: 64,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "flat",
        from: 62,
        to: 60,
      },
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "rising",
        from: 58,
        to: 72,
      },
    ],
  },
  {
    iso: "CHL",
    name: "Chile",
    region: "Americas",
    flag: "🇨🇱",
    population: 19_605_000,
    recipesLit: [
      ["constitutional_change", 58.3],
      ["mass_protest", 51.8],
      ["multilateral_agreement", 54.4],
    ],
    drivers: [
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "rising",
        from: 68,
        to: 75,
      },
      {
        code: "SI.POV.GINI",
        name: "Gini index",
        provider: "World Bank",
        shape: "falling",
        from: 64,
        to: 51,
      },
      {
        code: "v2csprtcpt",
        name: "CSO Participatory Env.",
        provider: "V-Dem",
        shape: "rising",
        from: 58,
        to: 68,
      },
      {
        code: "NE.TRD.GNFS.ZS",
        name: "Trade % GDP",
        provider: "World Bank",
        shape: "rising",
        from: 52,
        to: 64,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 35,
        to: 51,
      },
    ],
  },

  // ── Asia-Pacific ────────────────────────────────────────────────────────
  {
    iso: "PAK",
    name: "Pakistan",
    region: "Asia-Pacific",
    flag: "🇵🇰",
    population: 240_485_000,
    recipesLit: [
      ["terrorist_attack", 71.5],
      ["civil_war_and_insurgency", 66.8],
      ["political_violence", 64.5],
      ["economic_recession", 58.2],
      ["currency_crisis", 57.2],
    ],
    drivers: [
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 35,
        to: 14,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 41,
        to: 78,
      },
      {
        code: "v2cseeorgs",
        name: "CSO entry/exit",
        provider: "V-Dem",
        shape: "falling",
        from: 48,
        to: 28,
      },
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 62,
      },
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "rising",
        from: 54,
        to: 78,
      },
    ],
  },
  {
    iso: "MMR",
    name: "Myanmar",
    region: "Asia-Pacific",
    flag: "🇲🇲",
    population: 54_578_000,
    recipesLit: [
      ["civil_war_and_insurgency", 77.8],
      ["political_repression", 74.5],
      ["foreign_intervention", 71.2],
      ["ethnic_and_communal_conflict", 68.7],
      ["human_rights_violation", 71.4],
    ],
    drivers: [
      {
        code: "v2x_clphy",
        name: "Physical Violence Index",
        provider: "V-Dem",
        shape: "rising",
        from: 45,
        to: 88,
      },
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 35,
        to: 78,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 81,
      },
      {
        code: "v2clkill",
        name: "Freedom from Political Killings",
        provider: "V-Dem",
        shape: "falling",
        from: 32,
        to: 8,
      },
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 28,
        to: 7,
      },
    ],
  },
  {
    iso: "LKA",
    name: "Sri Lanka",
    region: "Asia-Pacific",
    flag: "🇱🇰",
    population: 21_894_000,
    recipesLit: [
      ["currency_crisis", 64.7],
      ["economic_recession", 61.8],
      ["banking_and_financial_crisis", 59.4],
      ["mass_protest", 57.2],
    ],
    drivers: [
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "rising",
        from: 58,
        to: 92,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 81,
      },
      {
        code: "DT.DOD.DSTC.ZS",
        name: "Short-term debt %",
        provider: "World Bank",
        shape: "rising",
        from: 48,
        to: 74,
      },
      {
        code: "NE.RSB.GNFS.ZS",
        name: "External balance % GDP",
        provider: "World Bank",
        shape: "falling",
        from: 45,
        to: 18,
      },
      {
        code: "v2csprtcpt",
        name: "CSO Participatory Env.",
        provider: "V-Dem",
        shape: "rising",
        from: 51,
        to: 68,
      },
    ],
  },
  {
    iso: "AFG",
    name: "Afghanistan",
    region: "Asia-Pacific",
    flag: "🇦🇫",
    population: 42_239_000,
    recipesLit: [
      ["foreign_intervention", 84.2],
      ["civil_war_and_insurgency", 81.8],
      ["humanitarian_crisis", 78.4],
      ["migration_and_refugees", 74.3],
      ["human_rights_violation", 71.2],
    ],
    drivers: [
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 48,
        to: 88,
      },
      {
        code: "v2x_clphy",
        name: "Physical Violence Index",
        provider: "V-Dem",
        shape: "rising",
        from: 51,
        to: 84,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 22,
        to: 5,
      },
      {
        code: "VC.IDP.NWDS",
        name: "New internal displacements",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 76,
      },
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 31,
        to: 4,
      },
    ],
  },
  {
    iso: "TKM",
    name: "Turkmenistan",
    region: "Asia-Pacific",
    flag: "🇹🇲",
    population: 6_516_000,
    recipesLit: [
      ["foreign_intervention", 97.0],
      ["political_repression", 68.7],
      ["executive_power_consolidation", 64.3],
    ],
    drivers: [
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 18,
        to: 5,
      },
      {
        code: "v2cseeorgs",
        name: "CSO entry/exit",
        provider: "V-Dem",
        shape: "falling",
        from: 14,
        to: 3,
      },
      {
        code: "v2psoppaut",
        name: "Opposition autonomy",
        provider: "V-Dem",
        shape: "falling",
        from: 12,
        to: 2,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "falling",
        from: 14,
        to: 4,
      },
      {
        code: "v2x_neopat",
        name: "Neopatrimonialism Index",
        provider: "V-Dem",
        shape: "rising",
        from: 78,
        to: 92,
      },
    ],
  },
  {
    iso: "TJK",
    name: "Tajikistan",
    region: "Asia-Pacific",
    flag: "🇹🇯",
    population: 10_143_000,
    recipesLit: [
      ["foreign_intervention", 88.5],
      ["political_repression", 61.8],
      ["ethnic_and_communal_conflict", 56.4],
    ],
    drivers: [
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 32,
        to: 14,
      },
      {
        code: "v2cseeorgs",
        name: "CSO entry/exit",
        provider: "V-Dem",
        shape: "falling",
        from: 28,
        to: 11,
      },
      {
        code: "v2juncind",
        name: "Judicial independence",
        provider: "V-Dem",
        shape: "falling",
        from: 31,
        to: 18,
      },
      {
        code: "v2x_corr",
        name: "Political Corruption Index",
        provider: "V-Dem",
        shape: "rising",
        from: 62,
        to: 78,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 42,
        to: 28,
      },
    ],
  },
  {
    iso: "PHL",
    name: "Philippines",
    region: "Asia-Pacific",
    flag: "🇵🇭",
    population: 117_337_000,
    recipesLit: [
      ["political_violence", 64.8],
      ["territorial_disputes", 54.1],
      ["foreign_direct_investment", 51.2],
    ],
    drivers: [
      {
        code: "v2clkill",
        name: "Freedom from Political Killings",
        provider: "V-Dem",
        shape: "falling",
        from: 45,
        to: 28,
      },
      {
        code: "v2x_clphy",
        name: "Physical Violence Index",
        provider: "V-Dem",
        shape: "rising",
        from: 48,
        to: 64,
      },
      {
        code: "v2svdomaut",
        name: "Domestic Autonomy",
        provider: "V-Dem",
        shape: "falling",
        from: 58,
        to: 41,
      },
      {
        code: "VC.IHR.PSRC.P5",
        name: "Intentional homicide rate",
        provider: "World Bank",
        shape: "rising",
        from: 41,
        to: 58,
      },
      {
        code: "BX.KLT.DINV.WD.GD.ZS",
        name: "FDI net inflows",
        provider: "World Bank",
        shape: "flat",
        from: 45,
        to: 48,
      },
    ],
  },
  {
    iso: "IND",
    name: "India",
    region: "Asia-Pacific",
    flag: "🇮🇳",
    population: 1_428_628_000,
    recipesLit: [
      ["executive_power_consolidation", 58.1],
      ["ethnic_and_communal_conflict", 61.7],
      ["religious_and_social_movement", 61.5],
    ],
    drivers: [
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "falling",
        from: 62,
        to: 48,
      },
      {
        code: "v2juncind",
        name: "Judicial independence",
        provider: "V-Dem",
        shape: "falling",
        from: 58,
        to: 42,
      },
      {
        code: "v2cseeorgs",
        name: "CSO entry/exit",
        provider: "V-Dem",
        shape: "falling",
        from: 54,
        to: 38,
      },
      {
        code: "v2pepwrses",
        name: "Power Distributed by Social Group",
        provider: "V-Dem",
        shape: "falling",
        from: 52,
        to: 38,
      },
      {
        code: "v2lginvstp",
        name: "Legislative investigates exec",
        provider: "V-Dem",
        shape: "falling",
        from: 51,
        to: 35,
      },
    ],
  },
  {
    iso: "IDN",
    name: "Indonesia",
    region: "Asia-Pacific",
    flag: "🇮🇩",
    population: 277_534_000,
    recipesLit: [
      ["democratic_transition", 55.7],
      ["earthquake", 61.8],
      ["religious_and_social_movement", 51.7],
    ],
    drivers: [
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "flat",
        from: 62,
        to: 61,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 52,
      },
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shape: "rising",
        from: 48,
        to: 58,
      },
      {
        code: "BX.KLT.DINV.WD.GD.ZS",
        name: "FDI net inflows",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 58,
      },
      {
        code: "v2x_civlib",
        name: "Civil liberties",
        provider: "V-Dem",
        shape: "falling",
        from: 58,
        to: 48,
      },
    ],
  },

  // ── Europe ──────────────────────────────────────────────────────────────
  {
    iso: "BLR",
    name: "Belarus",
    region: "Europe",
    flag: "🇧🇾",
    population: 9_498_000,
    recipesLit: [
      ["foreign_intervention", 94.2],
      ["political_repression", 78.2],
      ["sanctions_and_arms_embargo", 73.6],
    ],
    drivers: [
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 38,
        to: 11,
      },
      {
        code: "v2cseeorgs",
        name: "CSO entry/exit",
        provider: "V-Dem",
        shape: "falling",
        from: 32,
        to: 8,
      },
      {
        code: "v2psoppaut",
        name: "Opposition autonomy",
        provider: "V-Dem",
        shape: "falling",
        from: 31,
        to: 6,
      },
      {
        code: "v2juncind",
        name: "Judicial independence",
        provider: "V-Dem",
        shape: "falling",
        from: 38,
        to: 14,
      },
      {
        code: "v2svdomaut",
        name: "Domestic Autonomy",
        provider: "V-Dem",
        shape: "falling",
        from: 42,
        to: 18,
      },
    ],
  },
  {
    iso: "UKR",
    name: "Ukraine",
    region: "Europe",
    flag: "🇺🇦",
    population: 38_000_000,
    recipesLit: [
      ["interstate_war", 84.7],
      ["foreign_intervention", 81.4],
      ["humanitarian_crisis", 71.2],
      ["migration_and_refugees", 68.4],
      ["cyberattack", 71.4],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 35,
        to: 92,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 22,
        to: 88,
      },
      {
        code: "VC.IDP.NWDS",
        name: "New internal displacements",
        provider: "World Bank",
        shape: "rising",
        from: 18,
        to: 78,
      },
      {
        code: "v2svdomaut",
        name: "Domestic Autonomy",
        provider: "V-Dem",
        shape: "falling",
        from: 58,
        to: 31,
      },
      {
        code: "v2x_clphy",
        name: "Physical Violence Index",
        provider: "V-Dem",
        shape: "rising",
        from: 32,
        to: 84,
      },
    ],
  },
  {
    iso: "HUN",
    name: "Hungary",
    region: "Europe",
    flag: "🇭🇺",
    population: 9_589_000,
    recipesLit: [
      ["executive_power_consolidation", 71.4],
      ["constitutional_change", 58.2],
    ],
    drivers: [
      {
        code: "v2x_jucon",
        name: "Judicial Constraints on Executive",
        provider: "V-Dem",
        shape: "falling",
        from: 58,
        to: 31,
      },
      {
        code: "v2xlg_legcon",
        name: "Legislative Constraints on Exec",
        provider: "V-Dem",
        shape: "falling",
        from: 54,
        to: 28,
      },
      {
        code: "v2lginvstp",
        name: "Legislative investigates exec",
        provider: "V-Dem",
        shape: "falling",
        from: 52,
        to: 32,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "falling",
        from: 62,
        to: 44,
      },
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shape: "falling",
        from: 58,
        to: 42,
      },
    ],
  },
  {
    iso: "GRC",
    name: "Greece",
    region: "Europe",
    flag: "🇬🇷",
    population: 10_394_000,
    recipesLit: [
      ["fiscal_policy_change", 64.1],
      ["banking_and_financial_crisis", 54.7],
      ["economic_recovery", 58.2],
    ],
    drivers: [
      {
        code: "GC.DOD.TOTL.GD.ZS",
        name: "Government debt-to-GDP",
        provider: "World Bank",
        shape: "falling",
        from: 82,
        to: 64,
      },
      {
        code: "NY.GDP.MKTP.KD.ZG",
        name: "GDP growth",
        provider: "World Bank",
        shape: "rising",
        from: 32,
        to: 58,
      },
      {
        code: "SL.UEM.TOTL.ZS",
        name: "Unemployment",
        provider: "World Bank",
        shape: "falling",
        from: 78,
        to: 51,
      },
      {
        code: "BX.KLT.DINV.WD.GD.ZS",
        name: "FDI net inflows",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 58,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "rising",
        from: 51,
        to: 62,
      },
    ],
  },
  {
    iso: "DEU",
    name: "Germany",
    region: "Europe",
    flag: "🇩🇪",
    population: 84_482_000,
    recipesLit: [
      ["energy_policy", 58.4],
      ["multilateral_agreement", 54.1],
    ],
    drivers: [
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "flat",
        from: 88,
        to: 85,
      },
      {
        code: "NE.TRD.GNFS.ZS",
        name: "Trade % GDP",
        provider: "World Bank",
        shape: "flat",
        from: 78,
        to: 75,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "flat",
        from: 82,
        to: 81,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 32,
        to: 48,
      },
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shape: "flat",
        from: 81,
        to: 78,
      },
    ],
  },
  {
    iso: "GBR",
    name: "United Kingdom",
    region: "Europe",
    flag: "🇬🇧",
    population: 67_736_000,
    recipesLit: [
      ["cyberattack", 51.2],
      ["multilateral_agreement", 49.4],
    ],
    drivers: [
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "flat",
        from: 78,
        to: 76,
      },
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shape: "flat",
        from: 82,
        to: 79,
      },
      {
        code: "NE.TRD.GNFS.ZS",
        name: "Trade % GDP",
        provider: "World Bank",
        shape: "falling",
        from: 65,
        to: 54,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 31,
        to: 52,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "flat",
        from: 78,
        to: 75,
      },
    ],
  },
  {
    iso: "POL",
    name: "Poland",
    region: "Europe",
    flag: "🇵🇱",
    population: 41_026_000,
    recipesLit: [
      ["religious_and_social_movement", 57.8],
      ["regional_integration", 48.5],
    ],
    drivers: [
      {
        code: "v2juncind",
        name: "Judicial independence",
        provider: "V-Dem",
        shape: "rising",
        from: 38,
        to: 51,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy",
        provider: "V-Dem",
        shape: "rising",
        from: 58,
        to: 68,
      },
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shape: "rising",
        from: 62,
        to: 71,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 51,
      },
      {
        code: "NE.TRD.GNFS.ZS",
        name: "Trade % GDP",
        provider: "World Bank",
        shape: "rising",
        from: 58,
        to: 71,
      },
    ],
  },
  {
    iso: "RUS",
    name: "Russia",
    region: "Europe",
    flag: "🇷🇺",
    population: 144_236_000,
    recipesLit: [
      ["sanctions_and_arms_embargo", 74.7],
      ["foreign_intervention", 71.8],
      ["diplomatic_rupture", 71.8],
      ["political_repression", 64.5],
    ],
    drivers: [
      {
        code: "v2x_civlib",
        name: "Civil liberties index",
        provider: "V-Dem",
        shape: "falling",
        from: 38,
        to: 12,
      },
      {
        code: "v2cseeorgs",
        name: "CSO entry/exit",
        provider: "V-Dem",
        shape: "falling",
        from: 31,
        to: 8,
      },
      {
        code: "v2svdomaut",
        name: "Domestic Autonomy",
        provider: "V-Dem",
        shape: "rising",
        from: 62,
        to: 81,
      },
      {
        code: "NE.RSB.GNFS.ZS",
        name: "External balance % GDP",
        provider: "World Bank",
        shape: "rising",
        from: 51,
        to: 68,
      },
      {
        code: "v2psoppaut",
        name: "Opposition autonomy",
        provider: "V-Dem",
        shape: "falling",
        from: 32,
        to: 8,
      },
    ],
  },
  {
    iso: "SYR",
    name: "Syria",
    region: "MENA",
    flag: "🇸🇾",
    population: 21_324_000,
    recipesLit: [
      ["civil_war_and_insurgency", 84.1],
      ["foreign_intervention", 79.6],
      ["humanitarian_crisis", 77.3],
      ["democratic_transition", 68.9],
      ["migration_and_refugees", 64.2],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 44,
        to: 88,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 52,
        to: 92,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 28,
        to: 8,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 22,
        to: 4,
      },
    ],
  },
  {
    iso: "IRQ",
    name: "Iraq",
    region: "MENA",
    flag: "🇮🇶",
    population: 42_550_000,
    recipesLit: [
      ["civil_war_and_insurgency", 76.4],
      ["terrorist_attack", 73.8],
      ["foreign_intervention", 70.1],
      ["political_corruption", 66.5],
      ["oil_and_gas", 61.2],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 45,
        to: 78,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 28,
        to: 10,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 35,
        to: 18,
      },
      {
        code: "NY.GDP.MKTP.KD.ZG",
        name: "GDP growth (annual %)",
        provider: "World Bank",
        shape: "falling",
        from: 52,
        to: 28,
      },
    ],
  },
  {
    iso: "LBY",
    name: "Libya",
    region: "MENA",
    flag: "🇱🇾",
    population: 6_931_000,
    recipesLit: [
      ["civil_war_and_insurgency", 78.9],
      ["foreign_intervention", 72.4],
      ["oil_and_gas", 67.8],
      ["political_violence", 64.1],
      ["migration_and_refugees", 60.7],
    ],
    drivers: [
      {
        code: "PV.EST",
        name: "Political Stability and Absence of Violence",
        provider: "World Bank WGI",
        shape: "falling",
        from: 24,
        to: 8,
      },
      {
        code: "GE.EST",
        name: "Government Effectiveness",
        provider: "World Bank WGI",
        shape: "falling",
        from: 28,
        to: 10,
      },
      {
        code: "RL.EST",
        name: "Rule of Law",
        provider: "World Bank WGI",
        shape: "falling",
        from: 30,
        to: 12,
      },
      {
        code: "NY.GDP.MKTP.KD.ZG",
        name: "GDP growth (annual %)",
        provider: "World Bank",
        shape: "falling",
        from: 45,
        to: 18,
      },
    ],
  },
  {
    iso: "ISR",
    name: "Israel",
    region: "MENA",
    flag: "🇮🇱",
    population: 9_800_000,
    recipesLit: [
      ["political_violence", 81.5],
      ["terrorist_attack", 78.9],
      ["foreign_intervention", 71.2],
      ["mass_protest", 66.4],
      ["diplomatic_rupture", 62.8],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 22,
        to: 78,
      },
      {
        code: "MS.MIL.XPND.GD.ZS",
        name: "Military expenditure (% of GDP)",
        provider: "World Bank",
        shape: "rising",
        from: 41,
        to: 69,
      },
      {
        code: "PV.EST",
        name: "Political Stability / Absence of Violence",
        provider: "World Bank WGI",
        shape: "falling",
        from: 28,
        to: 8,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, consumer prices",
        provider: "World Bank",
        shape: "rising",
        from: 35,
        to: 58,
      },
    ],
  },
  {
    iso: "SOM",
    name: "Somalia",
    region: "Africa",
    flag: "🇸🇴",
    population: 18_143_379,
    recipesLit: [
      ["civil_war_and_insurgency", 82.3],
      ["terrorist_attack", 79.1],
      ["drought_and_famine", 74.6],
      ["humanitarian_crisis", 71.8],
      ["ethnic_and_communal_conflict", 64.3],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 52,
        to: 88,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 18,
        to: 5,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 44,
        to: 79,
      },
      {
        code: "SN.ITK.DEFC.ZS",
        name: "Prevalence of undernourishment",
        provider: "World Bank",
        shape: "rising",
        from: 38,
        to: 72,
      },
    ],
  },
  {
    iso: "HTI",
    name: "Haiti",
    region: "Americas",
    flag: "🇭🇹",
    population: 11_470_000,
    recipesLit: [
      ["political_violence", 83.7],
      ["humanitarian_crisis", 76.2],
      ["economic_recession", 68.4],
      ["migration_and_refugees", 63.9],
      ["flood_and_cyclone", 59.1],
    ],
    drivers: [
      {
        code: "PV.EST",
        name: "Political Stability / No Violence",
        provider: "World Bank WGI",
        shape: "falling",
        from: 22,
        to: 4,
      },
      {
        code: "RL.EST",
        name: "Rule of Law",
        provider: "World Bank WGI",
        shape: "falling",
        from: 18,
        to: 5,
      },
      {
        code: "VC.IHR.PSRC.P5",
        name: "Intentional homicides per 100k",
        provider: "World Bank",
        shape: "rising",
        from: 35,
        to: 78,
      },
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, CPI",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 89,
      },
    ],
  },
  {
    iso: "CAF",
    name: "Central African Republic",
    region: "Africa",
    flag: "🇨🇫",
    population: 5_637_011,
    recipesLit: [
      ["civil_war_and_insurgency", 80.6],
      ["foreign_intervention", 74.2],
      ["ethnic_and_communal_conflict", 69.7],
      ["humanitarian_crisis", 66.1],
      ["resource_conflict", 60.4],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 44,
        to: 82,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 36,
        to: 72,
      },
      {
        code: "PV.EST",
        name: "Political Stability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 28,
        to: 8,
      },
      {
        code: "v2x_corr",
        name: "Political Corruption Index",
        provider: "V-Dem",
        shape: "rising",
        from: 52,
        to: 76,
      },
    ],
  },
  {
    iso: "MOZ",
    name: "Mozambique",
    region: "Africa",
    flag: "🇲🇿",
    population: 33_897_354,
    recipesLit: [
      ["terrorist_attack", 72.8],
      ["civil_war_and_insurgency", 70.3],
      ["humanitarian_crisis", 65.7],
      ["flood_and_cyclone", 62.4],
      ["foreign_direct_investment", 58.6],
    ],
    drivers: [
      {
        code: "VC.BTL.DETH",
        name: "Battle-related deaths",
        provider: "World Bank",
        shape: "rising",
        from: 22,
        to: 68,
      },
      {
        code: "SM.POP.REFG.OR",
        name: "Refugees by origin",
        provider: "World Bank",
        shape: "rising",
        from: 18,
        to: 55,
      },
      {
        code: "PV.EST",
        name: "Political Stability and Absence of Violence",
        provider: "World Bank WGI",
        shape: "falling",
        from: 28,
        to: 10,
      },
      {
        code: "NY.GDP.MKTP.KD.ZG",
        name: "GDP growth (annual %)",
        provider: "World Bank",
        shape: "falling",
        from: 45,
        to: 24,
      },
    ],
  },
  {
    iso: "ZWE",
    name: "Zimbabwe",
    region: "Africa",
    flag: "🇿🇼",
    population: 16_665_409,
    recipesLit: [
      ["currency_crisis", 81.9],
      ["economic_recession", 75.4],
      ["political_repression", 70.8],
      ["human_rights_violation", 65.2],
      ["mass_protest", 60.7],
    ],
    drivers: [
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, consumer prices (annual %)",
        provider: "World Bank",
        shape: "rising",
        from: 42,
        to: 88,
      },
      {
        code: "VA.EST",
        name: "Voice and Accountability",
        provider: "World Bank WGI",
        shape: "falling",
        from: 28,
        to: 9,
      },
      {
        code: "PV.EST",
        name: "Political Stability and Absence of Violence",
        provider: "World Bank WGI",
        shape: "falling",
        from: 22,
        to: 11,
      },
      {
        code: "NY.GDP.MKTP.KD.ZG",
        name: "GDP growth (annual %)",
        provider: "World Bank",
        shape: "falling",
        from: 35,
        to: 14,
      },
    ],
  },
];

// ── Trajectory + analog hydration ────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function buildTrajectory(
  shape: "rising" | "falling" | "flat",
  from: number,
  to: number,
  iso: string,
  code: string
): number[] {
  // Deterministic per-(iso, code) pseudo-noise so trajectories are stable
  // across renders. Simple LCG seeded on a hash of "iso:code".
  let h = 2166136261;
  const s = `${iso}:${code}`;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const rng = () => {
    h = Math.imul(48271, h) | 0;
    return ((h >>> 0) / 0xffffffff - 0.5) * 6;
  };
  const out: number[] = [];
  for (let q = 0; q < 12; q++) {
    const t = q / 11;
    let base: number;
    if (shape === "flat") {
      base = from + (to - from) * t;
    } else {
      // Slight S-curve so the line doesn't look mechanical.
      const eased = t * t * (3 - 2 * t);
      base = from + (to - from) * eased;
    }
    out.push(Math.max(0, Math.min(100, base + rng())));
  }
  // Pin endpoints so direction always reads true.
  out[0] = Math.max(0, Math.min(100, from));
  out[11] = Math.max(0, Math.min(100, to));
  return out;
}

/**
 * Build 4-year score history from momentum_scores_by_year.
 * Returns sorted year array (ascending) of scores as number[].
 * Returns [] when no momentum data is present (falls back to empty state
 * in RankHistoryPanel).
 */
function buildYearScores(
  countryName: string,
  recipeId: string,
  allScores: Record<string, import("@/lib/te-data-contract/scores").RecipeScoresFile>
): Record<string, number> {
  const sf = allScores[recipeId];
  if (!sf) return {};
  const nameLower = countryName.toLowerCase();
  const entry = sf.scores.find((e) => e.name.toLowerCase() === nameLower);
  if (!entry?.momentum_scores_by_year) return {};
  return entry.momentum_scores_by_year;
}

/**
 * Build momentum_label for a country × recipe.
 */
function buildMomentumLabel(
  countryName: string,
  recipeId: string,
  allScores: Record<string, import("@/lib/te-data-contract/scores").RecipeScoresFile>
): string | null {
  const sf = allScores[recipeId];
  if (!sf) return null;
  const nameLower = countryName.toLowerCase();
  const entry = sf.scores.find((e) => e.name.toLowerCase() === nameLower);
  return entry?.momentum_label ?? null;
}

/**
 * Build sensitivity items for a country × recipe.
 * Returns [] when sensitivity_per_indicator is absent or empty.
 */
function buildSensitivity(
  countryName: string,
  recipeId: string,
  allScores: Record<string, import("@/lib/te-data-contract/scores").RecipeScoresFile>
): SensitivityItem[] {
  const sf = allScores[recipeId];
  if (!sf) return [];
  const nameLower = countryName.toLowerCase();
  const entry = sf.scores.find((e) => e.name.toLowerCase() === nameLower);
  if (!entry?.sensitivity_per_indicator) return [];
  return entry.sensitivity_per_indicator.map((s) => ({
    indicator_code: s.indicator,
    indicator_name: getIndicatorLabel(s.indicator),
    marginal_points_per_unit: s.marginal_points_per_unit,
    current_cosine: s.current_cosine,
    headroom: s.headroom,
    headroom_points: s.headroom_points,
  }));
}

/**
 * Build indicator_trajectory_composite_12q for a country × recipe.
 * Returns [] when field is absent.
 */
function buildCompositeTrajectory(
  countryName: string,
  recipeId: string,
  allScores: Record<string, import("@/lib/te-data-contract/scores").RecipeScoresFile>
): number[] {
  const sf = allScores[recipeId];
  if (!sf) return [];
  const nameLower = countryName.toLowerCase();
  const entry = sf.scores.find((e) => e.name.toLowerCase() === nameLower);
  const raw = entry?.indicator_trajectory_composite_12q;
  if (!Array.isArray(raw) || raw.length === 0) return [];
  // Normalise from z-score range ±3 to 0..100 display scale.
  return raw.map((v) => Math.max(0, Math.min(100, ((v + 3) / 6) * 100)));
}

// Plausible mock analogs by country profile. Used as fallbacks when
// nearest-analog-data.ts doesn't carry an entry for the ISO. Each tuple
// is (country, year, match_score, primary_recipe_id, what_happened_next).
type AnalogTuple = [string, number, number, string, string];

// Per-family (L1) analog pools — keyed by L1 id (A..H).
// Self-exclusion is applied at call time.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const ANALOG_POOLS_BY_FAMILY: Record<string, AnalogTuple[]> = {
  // B — Conflict & Violence
  B: [
    [
      "Yemen",
      2014,
      74.8,
      "civil_war_and_insurgency",
      "The Houthi movement seized Sanaa in September 2014. Saudi-led coalition air strikes began in March 2015, triggering a multi-sided civil war that by 2023 had displaced over 4 million people and produced the world's largest humanitarian crisis.",
    ],
    [
      "Iraq",
      2014,
      71.2,
      "foreign_intervention",
      "ISIS seized Mosul and declared a caliphate in June 2014. A US-led coalition launched air strikes in August 2014; ground operations by Iraqi forces, Kurdish Peshmerga, and Iranian-backed militias followed. Mosul was retaken in July 2017.",
    ],
    [
      "Mali",
      2012,
      66.5,
      "civil_war_and_insurgency",
      "AQIM-linked MNLA rebels seized northern Mali in March–April 2012 following a military coup. French Operation Serval launched in January 2013; the UN MINUSMA mission deployed in July 2013. Insurgency persisted through subsequent coups in 2020 and 2021.",
    ],
  ],
  // D — Economic Stress
  D: [
    [
      "Argentina",
      2001,
      68.9,
      "currency_crisis",
      "Argentina defaulted on US$100bn of sovereign debt in December 2001, the largest default in history at the time. The peso lost ~75% of its value within months; the country cycled through five presidents in two weeks.",
    ],
    [
      "Lebanon",
      2019,
      66.3,
      "banking_and_financial_crisis",
      "Lebanon's banking system froze deposits in October 2019 as the government defaulted on US$1.2bn in Eurobonds in March 2020. The Beirut port explosion in August 2020 compounded the collapse; GDP contracted ~58% from 2018 to 2021.",
    ],
    [
      "Greece",
      2012,
      64.2,
      "banking_and_financial_crisis",
      "Greece executed the largest sovereign-debt restructuring in history in March 2012 (~€199bn PSI swap). Three EU/IMF bailout programmes ran from 2010 through 2018; unemployment exceeded 27%.",
    ],
  ],
  // E — Social Mobilization
  E: [
    [
      "Egypt",
      2011,
      72.1,
      "mass_protest",
      "Eighteen days of protests centred on Tahrir Square forced President Hosni Mubarak to resign on 11 February 2011. The Supreme Council of the Armed Forces ruled for 16 months; Mohamed Morsi won elections in June 2012 before being deposed in a military coup in July 2013.",
    ],
    [
      "Sudan",
      2019,
      68.4,
      "mass_protest",
      "Mass protests beginning December 2018 against Omar al-Bashir's government led to his removal by the military on 11 April 2019. A transitional Sovereignty Council formed in August 2019; a second coup in October 2021 by General al-Burhan dissolved civilian government.",
    ],
    [
      "Tunisia",
      2010,
      64.7,
      "mass_protest",
      "Mohamed Bouazizi's self-immolation in December 2010 sparked protests that ended Ben Ali's 23-year rule on 14 January 2011. A new constitution was ratified in January 2014. President Kais Saied subsequently suspended parliament in July 2021.",
    ],
  ],
  // G — Humanitarian Crisis
  G: [
    [
      "Yemen",
      2015,
      75.3,
      "humanitarian_crisis",
      "The Saudi-led military intervention in March 2015 triggered a blockade that, combined with active conflict, produced the world's largest humanitarian crisis by 2018: 21 million people food-insecure, over 4 million displaced, cholera outbreak exceeding 2 million cases.",
    ],
    [
      "DR Congo",
      1998,
      69.8,
      "humanitarian_crisis",
      "The Second Congo War (1998–2003) drew in eight African states. An estimated 5 million people died, mostly from disease and famine; 3.4 million were internally displaced by 2002. The conflict fragmented into dozens of armed groups that persist in eastern DRC today.",
    ],
    [
      "Afghanistan",
      2021,
      65.1,
      "humanitarian_crisis",
      "The Taliban's seizure of Kabul on 15 August 2021 triggered the rapid collapse of the US-backed government. Within months 97% of Afghans fell below the poverty line; 24 million faced acute food insecurity and over 3.5 million were internally displaced by early 2022.",
    ],
  ],
  // Default for other families (A, C, F, H)
  DEFAULT_CRISIS: [
    [
      "Tunisia",
      2010,
      71.4,
      "mass_protest",
      "Mohamed Bouazizi's self-immolation in December 2010 sparked protests that ended Ben Ali's 23-year rule on 14 January 2011. A new constitution was ratified in January 2014. President Kais Saied subsequently suspended parliament in July 2021.",
    ],
    [
      "Argentina",
      2001,
      68.9,
      "currency_crisis",
      "Argentina defaulted on US$100bn of sovereign debt in December 2001, the largest default in history at the time. The peso lost ~75% of its value within months; the country cycled through five presidents in two weeks.",
    ],
    [
      "Greece",
      2012,
      64.2,
      "banking_and_financial_crisis",
      "Greece executed the largest sovereign-debt restructuring in history in March 2012 (~€199bn PSI swap). Three EU/IMF bailout programmes ran from 2010 through 2018; unemployment exceeded 27%.",
    ],
  ],
};

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const ANALOG_FALLBACKS_STABLE: AnalogTuple[] = [
  [
    "Indonesia",
    2014,
    62.8,
    "democratic_transition",
    "Joko Widodo's July 2014 election as the first Indonesian president from outside the political-military elite consolidated the post-Reformasi democratic transition that began in 1998.",
  ],
  [
    "Brazil",
    2002,
    58.4,
    "government_formation",
    "Luiz Inácio Lula da Silva's October 2002 election victory completed Brazil's first peaceful left-right transfer of power since the 1985 return to democracy.",
  ],
  [
    "Chile",
    2017,
    54.6,
    "constitutional_change",
    "Chile's 2019-2022 constitutional process began after the October 2019 estallido social. The September 2022 plebiscite rejected the draft; a second process produced another rejected draft in December 2023.",
  ],
];

// Lazy-built name→analog lookup over the real TE current-state-analogs corpus.
// Keyed by lowercased country name to match the v3 analogs contract (iso=null
// in sample-10). Built once, reused across every hydrate() call.
let _teAnalogByName: Map<string, CountryAnalog[]> | null = null;

function buildTEAnalogIndex(): Map<string, CountryAnalog[]> {
  const out = new Map<string, CountryAnalog[]>();
  try {
    const data = loadAnalogs();
    for (const entry of data.entries) {
      if (!entry.name || !entry.analogs || entry.analogs.length === 0) continue;
      const subjectName = entry.name.toLowerCase();
      // Self-exclusion + null what_happened_next handling. The real corpus
      // has what_happened_next=null today (back-end TODO); we surface an
      // honest "Outcome history pending" caption rather than fabricating.
      const list: CountryAnalog[] = entry.analogs
        .filter((a) => a.country && a.country.toLowerCase() !== subjectName)
        .map((a) => ({
          country: a.country,
          year: a.year,
          // Sample-10 stores match_score as 0..1; surface as 0..100 percent.
          match_score: a.match_score <= 1 ? a.match_score * 100 : a.match_score,
          primary_recipe_id: a.primary_recipe_id,
          what_happened_next:
            whnBlurb(a.country_iso2, a.country, a.year) ??
            a.what_happened_next ??
            "Outcome history is still being curated for this analog.",
          weak_analog: a.weak_analog ?? false,
        }));
      if (list.length > 0) out.set(subjectName, list);
    }
  } catch {
    // loadAnalogs unavailable — leave the index empty; every country falls
    // through to the honest "in development" empty state.
  }
  return out;
}

/**
 * Returns this country's historical analogs from the real TE corpus, or an
 * empty array when the corpus has no entry for this country.
 *
 * 2026-05-29 (V4.1 round 2): the prior implementation fell through to
 * hand-authored per-family analog pools when the real corpus was missing
 * an entry. That fabricated data masquerading as real on /countries/zaf
 * and /countries/sdn (and ~150 other countries not in the 60-entry sample
 * corpus). Per the founder ping ("Historical Analogs panel feels it still
 * uses mock data") we now return [] for missing countries and let the
 * AnalogsPanelV41 render an honest "Historical analogs in development for
 * this country" message.
 *
 * The hand-authored fallback pools are kept in the file as commented-out
 * documentation of what the prior behavior looked like, but no longer
 * called — they're a backend-ask, not a frontend fabrication.
 */
function analogsFor(name: string): CountryAnalog[] {
  if (!_teAnalogByName) _teAnalogByName = buildTEAnalogIndex();
  return _teAnalogByName.get(name.toLowerCase()) ?? [];
}

function compoundScore(litRecipes: Array<[string, number]>): number {
  // Bounded RMS with coverage shrinkage. Mirror of compound-risk-data.ts
  // ratified by the Ihsa consult 2026-05-29 (Roshani/Kwame/Miriam/Tariq/Elif).
  //   compound_score = sqrt(N / (N + 2)) * sqrt(mean(score_i^2))
  // where "lit" = score >= 50, and the result is bounded in [0, 100].
  const lit = litRecipes.filter(([, score]) => score >= 50);
  const N = lit.length;
  if (N === 0) return 0;
  const meanSq = lit.reduce((s, [, score]) => s + score * score, 0) / N;
  const rms = Math.sqrt(meanSq);
  const shrink = Math.sqrt(N / (N + 2));
  return Math.min(100, rms * shrink);
}

// Hydrate a seed into a full CountryV4 entry.
// allScores is passed in (loaded once by buildCountriesV4) for SHAP/movement reads.
function hydrate(
  seed: Seed,
  allScores: Record<string, import("@/lib/te-data-contract/scores").RecipeScoresFile> = {}
): CountryV4 {
  const topRecipesAll: CountryTopRecipe[] = [];
  for (const [recipeId, score] of seed.recipesLit) {
    const meta: TrackerRecipe | undefined = getRecipe(recipeId);
    if (!meta) continue;
    topRecipesAll.push({
      recipe_id: recipeId,
      label: meta.label,
      score,
      l1_id: meta.l1_id,
      l1_label: meta.l1_label,
      l1_color: meta.l1_color,
      status: meta.status,
    });
  }
  topRecipesAll.sort((a, b) => b.score - a.score);

  const recipesLitCount = topRecipesAll.length;
  const recipesLitGraduated = topRecipesAll.filter(
    (r) => r.status === "graduated"
  ).length;

  // Distinct lit families, A..H order.
  const litFamiliesMap = new Map<string, CountryLitFamily>();
  for (const r of topRecipesAll) {
    if (!litFamiliesMap.has(r.l1_id)) {
      litFamiliesMap.set(r.l1_id, {
        l1_id: r.l1_id,
        l1_label: r.l1_label,
        l1_color: r.l1_color,
      });
    }
  }
  const litFamilies = Array.from(litFamiliesMap.values()).sort((a, b) =>
    a.l1_id.localeCompare(b.l1_id)
  );

  // Attribution (SHAP): read from bake scores for the country's top-lit TE recipe.
  // Falls back to [] (honest empty state) when the country has no scored TE entry.
  // If the top recipe is not in fleet-run-1 (i.e. a seed-only recipe), cascade down
  // to the first fleet-run-1 recipe that has SHAP data for this country.
  const topRecipeTEId = topRecipesAll.find((r) =>
    FLEET_RUN_1_RECIPE_IDS.includes(r.recipe_id)
  )?.recipe_id;
  const drivers_attribution: CountryDriverAttribution[] = topRecipeTEId
    ? buildAttribution(seed.name, topRecipeTEId, allScores)
    : [];

  // Movement: read real indicator_movement[] from the bake scores for the same
  // top-lit TE recipe. Falls back to [] → WhatsMovingPanel honest empty state.
  // For seeds that have no scored TE recipe, we emit [] (not synthetic trajectories).
  const drivers_movement: CountryDriverMovement[] = topRecipeTEId
    ? buildMovementFromScores(seed.name, topRecipeTEId, allScores)
    : [];

  // Momentum: populate year_scores from momentum_scores_by_year (round-2).
  // rank_history remains empty at vintage-1 — the cross-vintage rollup file
  // (country-rank-history.json) now provides that data via loadRankHistory().
  const momentum: CountryMomentum[] = topRecipesAll.slice(0, 4).map((r) => {
    const yearScores = FLEET_RUN_1_RECIPE_IDS.includes(r.recipe_id)
      ? buildYearScores(seed.name, r.recipe_id, allScores)
      : {};
    const momentumLabel = FLEET_RUN_1_RECIPE_IDS.includes(r.recipe_id)
      ? buildMomentumLabel(seed.name, r.recipe_id, allScores)
      : null;
    return {
      recipe_id: r.recipe_id,
      label: r.label,
      l1_color: r.l1_color,
      rank_history: [],
      year_scores: yearScores,
      momentum_label: momentumLabel,
    };
  });

  // Round-2: sensitivity items from the top-lit TE recipe.
  const sensitivity: SensitivityItem[] = topRecipeTEId
    ? buildSensitivity(seed.name, topRecipeTEId, allScores)
    : [];

  // Round-2: composite indicator trajectory from the top-lit TE recipe.
  const indicator_trajectory_composite_12q: number[] = topRecipeTEId
    ? buildCompositeTrajectory(seed.name, topRecipeTEId, allScores)
    : [];

  return {
    iso: seed.iso,
    name: seed.name,
    region: seed.region,
    flag_emoji: seed.flag,
    population: seed.population,
    compound_score: compoundScore(seed.recipesLit),
    recipes_lit_count: recipesLitCount,
    recipes_lit_graduated: recipesLitGraduated,
    top_recipes: topRecipesAll,
    drivers_attribution,
    drivers_movement,
    drivers: drivers_movement, // back-compat alias
    momentum,
    analogs: analogsFor(seed.name),
    lit_families: litFamilies,
    vintage: VINTAGE,
    sensitivity,
    indicator_trajectory_composite_12q,
  };
}

/**
 * Infer a short provider label from a raw indicator code.
 *
 *   - V-Dem codes start with "v2" → "V-Dem"
 *   - WGI codes end with ".EST" → "World Bank WGI"
 *   - Everything else → "World Bank"
 *
 * Round-2 (2026-05-30): indicator_movement[] now carries an explicit
 * `provider` field. This heuristic is retained only for shap_attribution[]
 * which does not carry provider (pending score_countries.py upgrade #974).
 */
function inferProvider(code: string | null | undefined): string {
  // 2026-05-30: defensive — same hardening as resolveIndicatorLabel.
  // Fleet-run-1 shap_attribution[] occasionally has undefined codes;
  // crashing here would 500 every page that loads countries-v4-data.ts.
  if (!code) return "Unknown";
  const base = code.split("__")[0]; // strip any transform suffix
  if (base.startsWith("v2")) return "V-Dem";
  if (base.endsWith(".EST")) return "World Bank WGI";
  return "World Bank";
}

/**
 * Map a bake provider code to a display label.
 * Round-2: scores file emits "VDEM", "WB" etc. — normalise to display labels.
 */
function resolveProvider(bakeProvider: string | null | undefined, code: string): string {
  if (!bakeProvider) return inferProvider(code);
  switch (bakeProvider.toUpperCase()) {
    case "VDEM":
      return "V-Dem";
    case "WB":
      return "World Bank";
    case "WGI":
      return "World Bank WGI";
    default:
      return bakeProvider;
  }
}

/**
 * Real SHAP attribution for a country × recipe.
 *
 * Reads from the baked scores file (`scores/{recipeId}.scores.json`) for the
 * country name, extracts the `shap_attribution[]` array, and normalises into
 * CountryDriverAttribution[].
 *
 * Round-2: also reads `card.shap_direction_signs` to populate direction_sign
 * per indicator (used by WhyScoresPanel for +/- arrows).
 *
 * Indicator names that are null in the bake are backfilled via
 * `getIndicatorLabel()` (lib/indicator-labels.ts).
 *
 * Returns [] when:
 *   - the recipe ID is not in fleet-run-1;
 *   - the country is not found in that recipe's scores;
 *   - the shap_attribution array is empty.
 * In these cases WhyScoresPanel renders "Driver attribution available once
 * the country is scored on at least one recipe."
 */
function buildAttribution(
  countryName: string,
  recipeId: string,
  allScores: Record<string, import("@/lib/te-data-contract/scores").RecipeScoresFile>
): CountryDriverAttribution[] {
  const sf = allScores[recipeId];
  if (!sf) return [];

  const nameLower = countryName.toLowerCase();
  const entry = sf.scores.find((e) => e.name.toLowerCase() === nameLower);
  if (!entry || !entry.shap_attribution || entry.shap_attribution.length === 0) return [];

  // Round-2: load shap_direction_signs from the card if available.
  let directionSigns: Record<string, number> = {};
  try {
    const card = loadCardV3(recipeId);
    directionSigns = card.shap_direction_signs ?? {};
  } catch {
    // Card unavailable or no direction signs — direction_sign stays null.
  }

  // NOTE: the contract type names these `code`/`name`, but the real fleet-run-1
  // JSON uses `indicator_code`/`indicator_name`/`provider`. Read the real
  // fields (falling back to the contract names) so we don't emit
  // "(indicator code missing)" placeholders.
  return entry.shap_attribution.map((s) => {
    const code = (s as { indicator_code?: string }).indicator_code ?? s.code ?? "";
    const name =
      (s as { indicator_name?: string | null }).indicator_name ??
      s.name ??
      getIndicatorLabel(code);
    const provider = resolveProvider((s as { provider?: string | null }).provider, code);
    return {
      indicator_code: code,
      indicator_name: name,
      provider,
      signal_share_pct: s.signal_share_pct,
      recipe_id: recipeId,
      direction_sign: directionSigns[code] ?? null,
    };
  });
}

/**
 * Real indicator movement for a country × recipe.
 *
 * Reads `indicator_movement[]` from the baked scores file and maps into
 * CountryDriverMovement[]. Trajectory values are z-scores (±3 range);
 * they are normalised to a 0–100 display scale for the MiniSparkline which
 * defaults to [0, 100]:
 *   display = clamp((z + 3) / 6 * 100, 0, 100)
 *
 * Direction is derived from z_score_change:
 *   > +0.3 → "rising", < -0.3 → "falling", otherwise "flat".
 *
 * Returns [] when the country has no scored entry for the recipe, or when
 * indicator_movement is empty. WhatsMovingPanel renders honest empty state.
 */
function buildMovementFromScores(
  countryName: string,
  recipeId: string,
  allScores: Record<string, import("@/lib/te-data-contract/scores").RecipeScoresFile>
): CountryDriverMovement[] {
  const sf = allScores[recipeId];
  if (!sf) return [];

  const nameLower = countryName.toLowerCase();
  const entry = sf.scores.find((e) => e.name.toLowerCase() === nameLower);
  if (!entry || !entry.indicator_movement || entry.indicator_movement.length === 0)
    return [];

  return entry.indicator_movement.map((m) => {
    // Real fleet-run-1 JSON uses `indicator_code`/`indicator_name` (the
    // contract type names them `code`/`name`); read the real fields first so
    // we don't emit "(indicator code missing)".
    const code = (m as { indicator_code?: string }).indicator_code ?? m.code ?? "";
    const name =
      (m as { indicator_name?: string | null }).indicator_name ??
      m.name ??
      getIndicatorLabel(code);
    const z = m.z_score_change;
    const direction: CountryDriverMovement["direction"] =
      z > 0.3 ? "rising" : z < -0.3 ? "falling" : "flat";
    // Normalise z-trajectory from ±3 range to 0–100 display scale.
    const trajectory = m.trajectory_12q.map((v) =>
      Math.max(0, Math.min(100, ((v + 3) / 6) * 100))
    );
    // Round-2: use explicit provider from bake; fall back to heuristic.
    const provider = resolveProvider(m.provider, code);
    return {
      indicator_code: code,
      indicator_name: name,
      provider,
      direction,
      trajectory,
      z_score_change: Number(z.toFixed(2)),
      // Round-2: raw values and unit from bake.
      latest_raw_value: m.latest_raw_value ?? null,
      prior_raw_value: m.prior_raw_value ?? null,
      unit: m.unit ?? null,
    };
  });
}

// ─── TE sample-10 scores overlay ─────────────────────────────────────────────
//
// For each country in SEEDS, check if any of its recipesLit entries map to a
// TE sample-10 recipe. If so, replace the seed-authored score with the real
// discrimination rank from the scores file. This keeps drivers honest
// (seed-authored) while showing real ranks in top_recipes.
//
// Countries that appear in TE scores but NOT in SEEDS are appended below as
// TE-only entries (iso/flag resolved from country-iso2.ts; drivers are empty
// since we have no seed-authored indicators for them).

let _countriesV4Cache: CountryV4[] | null = null;

function buildCountriesV4(): CountryV4[] {
  // Build a map of recipe_id → name → real score from TE scores files.
  // Keys are normalized: recipe_id (string), country name lowercase → score.
  const teScoreMap = new Map<string, Map<string, number>>();
  // Also track top_recipes from country-index for L1 metadata.
  const ciTopRecipesMap = new Map<
    string,
    {
      recipe_id: string;
      score: number;
      l1_id: string;
      l1_label: string;
      l1_color: string;
    }[]
  >();
  // allScores loaded once, passed to every hydrate() call for SHAP/movement reads.
  let allScores: Record<
    string,
    import("@/lib/te-data-contract/scores").RecipeScoresFile
  > = {};
  try {
    allScores = loadAllScores();
    for (const recipeId of FLEET_RUN_1_RECIPE_IDS) {
      const sf = allScores[recipeId];
      if (!sf) continue;
      const byName = new Map<string, number>();
      for (const entry of sf.scores) {
        byName.set(entry.name.toLowerCase(), entry.score);
      }
      teScoreMap.set(recipeId, byName);
    }
    const ci = loadCountryIndex();
    for (const c of ci.countries) {
      if (!c.top_recipes) continue;
      ciTopRecipesMap.set(
        c.name.toLowerCase(),
        c.top_recipes.map((r) => ({
          recipe_id: r.recipe_id,
          score: r.score ?? 0,
          l1_id: r.l1_id ?? "",
          l1_label: r.l1_label ?? "",
          l1_color: r.l1_color ?? "#7A8FA0",
        }))
      );
    }
  } catch {
    // Loaders unavailable at this point — fall through to seed-only.
  }

  // Hydrate every seed, overlaying real TE scores where available.
  const seedIsos = new Set(SEEDS.map((s) => s.iso.toUpperCase()));
  // iso2 set of the hand-authored seeds, decoded from each seed's flag emoji,
  // so a country-index entry for a country we already seed is skipped by iso2
  // even when the names differ ("DR Congo" seed vs the index's "The Democratic
  // Republic of the Congo"). Prevents the duplicate card + the bad /countries/the.
  const iso2FromEmoji = (e: string): string => {
    if (!e) return "";
    const cps = Array.from(e).map((ch) => ch.codePointAt(0) ?? 0);
    if (cps.length < 2 || cps[0] < 0x1f1e6) return "";
    return cps
      .slice(0, 2)
      .map((cp) => String.fromCharCode(97 + (cp - 0x1f1e6)))
      .join("");
  };
  const seedIso2s = new Set(
    SEEDS.map((s) => iso2FromEmoji((s as { flag?: string }).flag ?? "")).filter(Boolean)
  );
  const base = SEEDS.map((seed) => {
    // For each (recipeId, seedScore) pair, check if TE has a real score.
    const updatedRecipesLit: Array<[string, number]> = seed.recipesLit.map(
      ([rid, seedScore]) => {
        if (!FLEET_RUN_1_RECIPE_IDS.includes(rid)) return [rid, seedScore];
        const byName = teScoreMap.get(rid);
        if (!byName) return [rid, seedScore];
        const real = byName.get(seed.name.toLowerCase());
        return [rid, real !== undefined ? real : seedScore];
      }
    );
    return hydrate({ ...seed, recipesLit: updatedRecipesLit }, allScores);
  });

  // Append TE-only countries: countries that appear in TE scores (top_recipes
  // from country-index) but have no SEEDS entry (iso not in seedIsos).
  // We only add a country if it has at least one TE recipe score ≥ 50
  // (i.e., it's meaningfully "lit" on at least one recipe).
  const ci_extra: CountryV4[] = [];
  try {
    const ci = loadCountryIndex();
    const ciVintage = ci.vintage ?? "2026-05-28";
    for (const c of ci.countries) {
      // Prefer the country-index's OWN iso2 (always correct: DRC "cd", The
      // Gambia "gm"); only fall back to the name map. The old name-map-only
      // lookup missed "The ..." names -> iso2 "" -> iso3 = name.slice(0,3) =
      // "THE", giving "/countries/the" with no flag (founder 2026-06-04).
      const iso2 =
        ((c as { iso2?: string }).iso2 ?? "").toLowerCase() ||
        NAME_TO_ISO2.get(c.name.toLowerCase()) ||
        "";
      const iso3 = iso2 ? iso2.toUpperCase() : c.name.slice(0, 3).toUpperCase();
      // Skip if we already have a seed for this country (by iso3, by iso2, or
      // by name) so the index entry never duplicates a seed.
      if (
        seedIsos.has(iso3) ||
        (iso2 && seedIso2s.has(iso2)) ||
        base.some((b) => b.name.toLowerCase() === c.name.toLowerCase())
      )
        continue;
      if (!c.top_recipes || c.top_recipes.length === 0) continue;
      const topScore = c.top_recipes[0]?.score ?? 0;
      if ((topScore ?? 0) < 50) continue;

      const recipesLit: Array<[string, number]> = c.top_recipes
        .filter((r) => r.score != null)
        .map((r) => [r.recipe_id, r.score ?? 0]);
      if (recipesLit.length === 0) continue;

      const flag = iso2 ? flagFromIso2(iso2) : "";
      const entry = hydrate(
        {
          iso: iso3,
          name: c.name,
          region: c.region ?? "Unknown",
          flag,
          population: 0,
          recipesLit,
          drivers: [],
          analogs: [],
        },
        allScores
      );
      ci_extra.push({ ...entry, vintage: ciVintage });
    }
  } catch {
    // country-index unavailable — TE-only entries omitted
  }

  return [...base, ...ci_extra];
}

export const COUNTRIES_V4: CountryV4[] = (() => {
  if (!_countriesV4Cache) _countriesV4Cache = buildCountriesV4();
  return _countriesV4Cache;
})();

export function getCountryByIso(iso: string): CountryV4 | undefined {
  const upper = iso.toUpperCase();
  return COUNTRIES_V4.find((c) => c.iso === upper);
}

export function countriesByRegion(
  input?: readonly CountryV4[]
): Record<string, CountryV4[]> {
  const src = input ?? COUNTRIES_V4;
  const out: Record<string, CountryV4[]> = {};
  for (const c of src) {
    if (!out[c.region]) out[c.region] = [];
    out[c.region].push(c);
  }
  return out;
}
