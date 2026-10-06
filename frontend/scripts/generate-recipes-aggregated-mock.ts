/**
 * Generate `data/recipes-aggregated-mock.json` — Week-2 mock data scaffold
 * for #464 (Frontend route restructure).
 *
 * Schema mirrors the future `qgi_data.recipes_aggregated` Glue table per
 * #462 ticket. When real data lands in Week 3, the loader in
 * `lib/recipes-aggregated.ts` swaps from this file to S3/Athena and the
 * route handlers don't change.
 *
 * Strategy: 5 high-salience recipes are hand-tuned with realistic
 * indicator names from `data/indexes.json`. The remaining 66 categories
 * (full L3 taxonomy from `lib/category-taxonomy.ts`) are generated with
 * deterministic random-ish numbers so the mock UI still has 71 rows
 * without 71 hours of authoring.
 *
 * Re-run:  npx tsx scripts/generate-recipes-aggregated-mock.ts
 *
 * THROWAWAY in spirit — the real pipeline (Phase 5b.6.5) will replace
 * this generator. Kept in the repo for reproducibility while the mock
 * is in service (one Week 2 → Week 3 cutover).
 */
import { writeFileSync, readFileSync } from "node:fs";
import { join } from "node:path";

// ---------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------

interface IndicatorIndex {
  id: string;
  numeric_id: number;
  name: string;
  sector: string;
}

const ROOT = join(__dirname, "..");
const indicators: IndicatorIndex[] = JSON.parse(
  readFileSync(join(ROOT, "data", "indexes.json"), "utf-8")
);

// Hard-coded L3 taxonomy (matches CATEGORY_L1_MAP keys in
// lib/category-taxonomy.ts; legacy slugs trimmed). Source: 2026-04
// canonical 71-code L3 taxonomy.
const L3_CATEGORIES: string[] = [
  // A — Political Power & Regime
  "elections_and_voting",
  "government_formation",
  "constitutional_change",
  "decentralization_and_federalism",
  "democratic_transition",
  "executive_power_consolidation",
  "military_coup",
  "coup_attempt_or_succession",
  "transitional_justice",
  "peacekeeping_and_peace_process",
  // B — Conflict & Political Violence
  "interstate_war",
  "civil_war_and_insurgency",
  "terrorist_attack",
  "foreign_intervention",
  "ethnic_and_communal_conflict",
  "political_violence",
  // C — State Authority & Governance
  "political_repression",
  "political_corruption",
  "human_rights_violation",
  "human_rights_reform",
  "military_policy_and_reform",
  // D — Economic & Financial Stress
  "currency_crisis",
  "banking_and_financial_crisis",
  "economic_recession",
  "fiscal_policy_change",
  "monetary_policy_change",
  "economic_liberalization",
  "economic_nationalization",
  "economic_recovery",
  "economic_growth_milestone",
  "trade_agreement",
  "trade_dispute",
  "foreign_direct_investment",
  "industrial_policy",
  "sanctions_and_arms_embargo",
  "foreign_aid_and_development",
  "sovereign_default",
  // E — Social Mobilization & Civil Society
  "mass_protest",
  "labor_action",
  "social_policy_reform",
  "public_health_reform",
  "poverty_and_inequality_crisis",
  "religious_and_social_movement",
  "migration_and_refugees",
  // F — Diplomatic & Geopolitical Relations
  "bilateral_treaty",
  "multilateral_agreement",
  "diplomatic_rupture",
  "territorial_disputes",
  "regional_integration",
  // G — Humanitarian & Environmental Crisis
  "earthquake",
  "flood_and_cyclone",
  "volcanic_eruption",
  "natural_disaster",
  "drought_and_famine",
  "epidemic_and_pandemic",
  "humanitarian_crisis",
  "water_crisis",
  // H — Structural & Development Context
  "energy_policy",
  "oil_and_gas",
  "renewable_energy",
  "environmental_policy",
  "climate_agreement",
  "resource_conflict",
  "infrastructure_project",
  "urban_development",
  "education_reform",
  "education_and_research",
  "digital_policy",
  "technology_breakthrough",
  "cyberattack",
  "cultural_and_heritage",
  "sport_and_international_event",
  "agricultural_policy",
];

// ---------------------------------------------------------------------------
// Output schema (mirror of qgi-aws-tf#462)
// ---------------------------------------------------------------------------

interface LengthBucket {
  length: number;
  count: number;
}

interface IndicatorFingerprintEntry {
  indicator_id: number;
  indicator_name: string;
  frequency: number;
  ci_lower: number;
  ci_upper: number;
  avg_corr_magnitude: number;
  /** #470 item 1: TF-IDF score that drives the top-K=15 ranking. Auto-
   * computed by `withTfidf()` below from frequency assuming N_total = 71
   * recipes. Absent from hand-curated entries — added during serialization. */
  tfidf_score?: number;
}

interface RegionShare {
  region: string;
  share: number;
}

interface CoverageBiasDiagnostic {
  n_pairs: number;
  oecd_share: number;
  regional_concentration: RegionShare[];
}

interface RecipeAggregated {
  event_category: string;
  canonical_length: number;
  length_distribution: LengthBucket[];
  indicator_fingerprint: IndicatorFingerprintEntry[];
  coverage_bias_diagnostic: CoverageBiasDiagnostic;
  total_instances: number;
  n_distinct_country_pairs: number;
  last_recomputed_at: string;
  contains_predicted: boolean;
}

interface RecipesAggregatedFile {
  generated_at: string;
  schema_version: number;
  pipeline_version: string;
  recipes: RecipeAggregated[];
}

// ---------------------------------------------------------------------------
// Hand-tuned high-salience recipes
// ---------------------------------------------------------------------------

const TIMESTAMP = "2026-04-26T12:00:00.000Z";

/** Pick an indicator by name — fail loud if the catalog drifts. */
function indicatorByName(name: string): IndicatorIndex {
  const hit = indicators.find((i) => i.name === name);
  if (!hit) throw new Error(`Indicator not found in catalog: ${name}`);
  return hit;
}

const CIVIL_WAR: RecipeAggregated = {
  event_category: "civil_war_and_insurgency",
  canonical_length: 18,
  length_distribution: [
    { length: 12, count: 4 },
    { length: 15, count: 9 },
    { length: 18, count: 23 },
    { length: 21, count: 8 },
    { length: 25, count: 3 },
  ],
  indicator_fingerprint: [
    {
      indicator_id: indicatorByName("GDP growth (annual %)").numeric_id,
      indicator_name: "GDP growth (annual %)",
      frequency: 0.78,
      ci_lower: 0.65,
      ci_upper: 0.89,
      avg_corr_magnitude: 0.84,
    },
    {
      indicator_id: indicatorByName(
        "Political Stability and Absence of Violence/Terrorism (estimate)"
      ).numeric_id,
      indicator_name: "Political Stability and Absence of Violence/Terrorism (estimate)",
      frequency: 0.72,
      ci_lower: 0.59,
      ci_upper: 0.83,
      avg_corr_magnitude: 0.81,
    },
    {
      indicator_id: indicatorByName("Military expenditure (% of GDP)").numeric_id,
      indicator_name: "Military expenditure (% of GDP)",
      frequency: 0.68,
      ci_lower: 0.55,
      ci_upper: 0.79,
      avg_corr_magnitude: 0.77,
    },
    {
      indicator_id: indicatorByName("Unemployment, total (% of total labor force)")
        .numeric_id,
      indicator_name: "Unemployment, total (% of total labor force)",
      frequency: 0.61,
      ci_lower: 0.47,
      ci_upper: 0.74,
      avg_corr_magnitude: 0.69,
    },
    {
      indicator_id: indicatorByName("Rule of Law (estimate)").numeric_id,
      indicator_name: "Rule of Law (estimate)",
      frequency: 0.55,
      ci_lower: 0.41,
      ci_upper: 0.68,
      avg_corr_magnitude: 0.71,
    },
    {
      indicator_id: indicatorByName("Inflation, consumer prices (annual %)").numeric_id,
      indicator_name: "Inflation, consumer prices (annual %)",
      frequency: 0.49,
      ci_lower: 0.35,
      ci_upper: 0.62,
      avg_corr_magnitude: 0.64,
    },
    {
      indicator_id: indicatorByName("Mortality rate, under-5 (per 1,000 live births)")
        .numeric_id,
      indicator_name: "Mortality rate, under-5 (per 1,000 live births)",
      frequency: 0.42,
      ci_lower: 0.28,
      ci_upper: 0.56,
      avg_corr_magnitude: 0.58,
    },
    {
      indicator_id: indicatorByName("Armed forces personnel (% of total labor force)")
        .numeric_id,
      indicator_name: "Armed forces personnel (% of total labor force)",
      frequency: 0.36,
      ci_lower: 0.23,
      ci_upper: 0.5,
      avg_corr_magnitude: 0.55,
    },
  ],
  coverage_bias_diagnostic: {
    n_pairs: 47,
    oecd_share: 0.13,
    regional_concentration: [
      { region: "Sub-Saharan Africa", share: 0.34 },
      { region: "Middle East", share: 0.21 },
      { region: "South Asia", share: 0.17 },
      { region: "Latin America", share: 0.13 },
      { region: "Europe", share: 0.09 },
    ],
  },
  total_instances: 47,
  n_distinct_country_pairs: 47,
  last_recomputed_at: TIMESTAMP,
  contains_predicted: false,
};

const MILITARY_COUP: RecipeAggregated = {
  event_category: "military_coup",
  canonical_length: 12,
  length_distribution: [
    { length: 8, count: 6 },
    { length: 10, count: 11 },
    { length: 12, count: 18 },
    { length: 15, count: 7 },
    { length: 20, count: 2 },
  ],
  indicator_fingerprint: [
    {
      indicator_id: indicatorByName("Military expenditure (% of GDP)").numeric_id,
      indicator_name: "Military expenditure (% of GDP)",
      frequency: 0.84,
      ci_lower: 0.72,
      ci_upper: 0.92,
      avg_corr_magnitude: 0.79,
    },
    {
      indicator_id: indicatorByName(
        "Political Stability and Absence of Violence/Terrorism (estimate)"
      ).numeric_id,
      indicator_name: "Political Stability and Absence of Violence/Terrorism (estimate)",
      frequency: 0.81,
      ci_lower: 0.69,
      ci_upper: 0.9,
      avg_corr_magnitude: 0.83,
    },
    {
      indicator_id: indicatorByName("Government Effectiveness (estimate)").numeric_id,
      indicator_name: "Government Effectiveness (estimate)",
      frequency: 0.7,
      ci_lower: 0.57,
      ci_upper: 0.81,
      avg_corr_magnitude: 0.74,
    },
    {
      indicator_id: indicatorByName("GDP growth (annual %)").numeric_id,
      indicator_name: "GDP growth (annual %)",
      frequency: 0.62,
      ci_lower: 0.48,
      ci_upper: 0.74,
      avg_corr_magnitude: 0.66,
    },
    {
      indicator_id: indicatorByName("Voice and Accountability (estimate)").numeric_id,
      indicator_name: "Voice and Accountability (estimate)",
      frequency: 0.58,
      ci_lower: 0.44,
      ci_upper: 0.71,
      avg_corr_magnitude: 0.7,
    },
    {
      indicator_id: indicatorByName("Control of Corruption (estimate)").numeric_id,
      indicator_name: "Control of Corruption (estimate)",
      frequency: 0.51,
      ci_lower: 0.37,
      ci_upper: 0.64,
      avg_corr_magnitude: 0.62,
    },
    {
      indicator_id: indicatorByName("Armed forces personnel (% of total labor force)")
        .numeric_id,
      indicator_name: "Armed forces personnel (% of total labor force)",
      frequency: 0.46,
      ci_lower: 0.32,
      ci_upper: 0.6,
      avg_corr_magnitude: 0.58,
    },
  ],
  coverage_bias_diagnostic: {
    n_pairs: 44,
    oecd_share: 0.07,
    regional_concentration: [
      { region: "Sub-Saharan Africa", share: 0.45 },
      { region: "Latin America", share: 0.23 },
      { region: "Middle East", share: 0.16 },
      { region: "South Asia", share: 0.09 },
    ],
  },
  total_instances: 44,
  n_distinct_country_pairs: 44,
  last_recomputed_at: TIMESTAMP,
  contains_predicted: false,
};

const MASS_PROTEST: RecipeAggregated = {
  event_category: "mass_protest",
  canonical_length: 9,
  length_distribution: [
    { length: 5, count: 12 },
    { length: 7, count: 19 },
    { length: 9, count: 31 },
    { length: 12, count: 14 },
    { length: 18, count: 5 },
  ],
  indicator_fingerprint: [
    {
      indicator_id: indicatorByName("Unemployment, total (% of total labor force)")
        .numeric_id,
      indicator_name: "Unemployment, total (% of total labor force)",
      frequency: 0.81,
      ci_lower: 0.71,
      ci_upper: 0.89,
      avg_corr_magnitude: 0.74,
    },
    {
      indicator_id: indicatorByName("Inflation, consumer prices (annual %)").numeric_id,
      indicator_name: "Inflation, consumer prices (annual %)",
      frequency: 0.74,
      ci_lower: 0.63,
      ci_upper: 0.83,
      avg_corr_magnitude: 0.69,
    },
    {
      indicator_id: indicatorByName("GDP per capita (current US$)").numeric_id,
      indicator_name: "GDP per capita (current US$)",
      frequency: 0.68,
      ci_lower: 0.56,
      ci_upper: 0.79,
      avg_corr_magnitude: 0.66,
    },
    {
      indicator_id: indicatorByName("Voice and Accountability (estimate)").numeric_id,
      indicator_name: "Voice and Accountability (estimate)",
      frequency: 0.63,
      ci_lower: 0.5,
      ci_upper: 0.74,
      avg_corr_magnitude: 0.71,
    },
    {
      indicator_id: indicatorByName("Individuals using the Internet (% of population)")
        .numeric_id,
      indicator_name: "Individuals using the Internet (% of population)",
      frequency: 0.55,
      ci_lower: 0.42,
      ci_upper: 0.67,
      avg_corr_magnitude: 0.58,
    },
    {
      indicator_id: indicatorByName("Mobile cellular subscriptions (per 100 people)")
        .numeric_id,
      indicator_name: "Mobile cellular subscriptions (per 100 people)",
      frequency: 0.49,
      ci_lower: 0.36,
      ci_upper: 0.61,
      avg_corr_magnitude: 0.53,
    },
    {
      indicator_id: indicatorByName("Control of Corruption (estimate)").numeric_id,
      indicator_name: "Control of Corruption (estimate)",
      frequency: 0.43,
      ci_lower: 0.3,
      ci_upper: 0.56,
      avg_corr_magnitude: 0.6,
    },
  ],
  coverage_bias_diagnostic: {
    n_pairs: 81,
    oecd_share: 0.28,
    regional_concentration: [
      { region: "Latin America", share: 0.24 },
      { region: "Middle East", share: 0.21 },
      { region: "Europe", share: 0.18 },
      { region: "Sub-Saharan Africa", share: 0.16 },
      { region: "East Asia", share: 0.11 },
    ],
  },
  total_instances: 81,
  n_distinct_country_pairs: 81,
  last_recomputed_at: TIMESTAMP,
  contains_predicted: false,
};

const TERRORIST_ATTACK: RecipeAggregated = {
  event_category: "terrorist_attack",
  canonical_length: 14,
  length_distribution: [
    { length: 8, count: 7 },
    { length: 11, count: 14 },
    { length: 14, count: 24 },
    { length: 18, count: 11 },
    { length: 22, count: 4 },
  ],
  indicator_fingerprint: [
    {
      indicator_id: indicatorByName(
        "Political Stability and Absence of Violence/Terrorism (estimate)"
      ).numeric_id,
      indicator_name: "Political Stability and Absence of Violence/Terrorism (estimate)",
      frequency: 0.86,
      ci_lower: 0.76,
      ci_upper: 0.93,
      avg_corr_magnitude: 0.82,
    },
    {
      indicator_id: indicatorByName("Military expenditure (% of GDP)").numeric_id,
      indicator_name: "Military expenditure (% of GDP)",
      frequency: 0.69,
      ci_lower: 0.56,
      ci_upper: 0.8,
      avg_corr_magnitude: 0.71,
    },
    {
      indicator_id: indicatorByName("Rule of Law (estimate)").numeric_id,
      indicator_name: "Rule of Law (estimate)",
      frequency: 0.65,
      ci_lower: 0.52,
      ci_upper: 0.76,
      avg_corr_magnitude: 0.68,
    },
    {
      indicator_id: indicatorByName("Arms imports (SIPRI trend indicator values)")
        .numeric_id,
      indicator_name: "Arms imports (SIPRI trend indicator values)",
      frequency: 0.57,
      ci_lower: 0.43,
      ci_upper: 0.69,
      avg_corr_magnitude: 0.65,
    },
    {
      indicator_id: indicatorByName("Government Effectiveness (estimate)").numeric_id,
      indicator_name: "Government Effectiveness (estimate)",
      frequency: 0.51,
      ci_lower: 0.37,
      ci_upper: 0.64,
      avg_corr_magnitude: 0.62,
    },
    {
      indicator_id: indicatorByName("Unemployment, total (% of total labor force)")
        .numeric_id,
      indicator_name: "Unemployment, total (% of total labor force)",
      frequency: 0.45,
      ci_lower: 0.32,
      ci_upper: 0.58,
      avg_corr_magnitude: 0.55,
    },
  ],
  coverage_bias_diagnostic: {
    n_pairs: 60,
    oecd_share: 0.18,
    regional_concentration: [
      { region: "Middle East", share: 0.32 },
      { region: "South Asia", share: 0.22 },
      { region: "Sub-Saharan Africa", share: 0.18 },
      { region: "Europe", share: 0.13 },
    ],
  },
  total_instances: 60,
  n_distinct_country_pairs: 60,
  last_recomputed_at: TIMESTAMP,
  contains_predicted: false,
};

const SOVEREIGN_DEFAULT: RecipeAggregated = {
  event_category: "sovereign_default",
  canonical_length: 22,
  length_distribution: [
    { length: 15, count: 3 },
    { length: 18, count: 7 },
    { length: 22, count: 14 },
    { length: 26, count: 6 },
    { length: 30, count: 2 },
  ],
  indicator_fingerprint: [
    {
      indicator_id: indicatorByName("Inflation, consumer prices (annual %)").numeric_id,
      indicator_name: "Inflation, consumer prices (annual %)",
      frequency: 0.91,
      ci_lower: 0.82,
      ci_upper: 0.96,
      avg_corr_magnitude: 0.88,
    },
    {
      indicator_id: indicatorByName("GDP growth (annual %)").numeric_id,
      indicator_name: "GDP growth (annual %)",
      frequency: 0.85,
      ci_lower: 0.74,
      ci_upper: 0.92,
      avg_corr_magnitude: 0.83,
    },
    {
      indicator_id: indicatorByName("GDP (current US$)").numeric_id,
      indicator_name: "GDP (current US$)",
      frequency: 0.79,
      ci_lower: 0.67,
      ci_upper: 0.88,
      avg_corr_magnitude: 0.77,
    },
    {
      indicator_id: indicatorByName("Exports of goods and services (% of GDP)")
        .numeric_id,
      indicator_name: "Exports of goods and services (% of GDP)",
      frequency: 0.71,
      ci_lower: 0.58,
      ci_upper: 0.82,
      avg_corr_magnitude: 0.74,
    },
    {
      indicator_id: indicatorByName("Imports of goods and services (% of GDP)")
        .numeric_id,
      indicator_name: "Imports of goods and services (% of GDP)",
      frequency: 0.66,
      ci_lower: 0.53,
      ci_upper: 0.77,
      avg_corr_magnitude: 0.7,
    },
    {
      indicator_id: indicatorByName("Regulatory Quality (estimate)").numeric_id,
      indicator_name: "Regulatory Quality (estimate)",
      frequency: 0.59,
      ci_lower: 0.45,
      ci_upper: 0.71,
      avg_corr_magnitude: 0.66,
    },
    {
      indicator_id: indicatorByName("GNI per capita, Atlas method (current US$)")
        .numeric_id,
      indicator_name: "GNI per capita, Atlas method (current US$)",
      frequency: 0.52,
      ci_lower: 0.39,
      ci_upper: 0.65,
      avg_corr_magnitude: 0.61,
    },
  ],
  coverage_bias_diagnostic: {
    n_pairs: 32,
    oecd_share: 0.22,
    regional_concentration: [
      { region: "Latin America", share: 0.41 },
      { region: "Sub-Saharan Africa", share: 0.22 },
      { region: "Europe", share: 0.19 },
      { region: "Middle East", share: 0.09 },
    ],
  },
  total_instances: 32,
  n_distinct_country_pairs: 32,
  last_recomputed_at: TIMESTAMP,
  contains_predicted: false,
};

const HAND_TUNED: RecipeAggregated[] = [
  CIVIL_WAR,
  MILITARY_COUP,
  MASS_PROTEST,
  TERRORIST_ATTACK,
  SOVEREIGN_DEFAULT,
];

// ---------------------------------------------------------------------------
// Generated (sketch) recipes for the rest of the 71 categories
// ---------------------------------------------------------------------------

/**
 * Deterministic pseudo-random based on a hash of the category slug — so
 * the mock numbers are stable across regenerations (no UI flicker
 * between developer machines).
 */
function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function pickIndicators(seed: number, k: number): IndicatorIndex[] {
  // Stable shuffle: pick k indicators using a linear-congruential
  // step over the catalog. Prevents the same indicator dominating
  // every sketch recipe.
  const result: IndicatorIndex[] = [];
  const seen = new Set<number>();
  let idx = seed % indicators.length;
  while (result.length < k && seen.size < indicators.length) {
    if (!seen.has(idx)) {
      result.push(indicators[idx]);
      seen.add(idx);
    }
    idx = (idx + 1103515245 + result.length * 12345) % indicators.length;
  }
  return result;
}

function generateSketch(category: string): RecipeAggregated {
  const seed = hashString(category);
  // Length anchors near {6, 9, 12, 15, 18, 22, 30}
  const lengthAnchors = [6, 9, 12, 15, 18, 22, 30];
  const canonical = lengthAnchors[seed % lengthAnchors.length];

  // Length distribution: 5 buckets centered on canonical
  const length_distribution: LengthBucket[] = [
    { length: Math.max(3, canonical - 6), count: 2 + (seed % 4) },
    { length: Math.max(4, canonical - 3), count: 5 + ((seed >> 2) % 6) },
    { length: canonical, count: 8 + ((seed >> 4) % 12) },
    { length: canonical + 3, count: 3 + ((seed >> 6) % 5) },
    { length: canonical + 6, count: 1 + ((seed >> 8) % 3) },
  ];

  const total = length_distribution.reduce((a, b) => a + b.count, 0);

  const k = 6 + (seed % 5); // 6-10 indicators per recipe
  const picked = pickIndicators(seed, k);
  const indicator_fingerprint: IndicatorFingerprintEntry[] = picked.map((ind, i) => {
    // Frequency decays from ~0.75 down to ~0.25 across the K indicators
    // (top-K are the strongest). CI width is ~0.25.
    const freq = Math.max(0.18, 0.78 - i * 0.06 - ((seed >> (i + 3)) % 100) / 1000);
    const ciHalf = 0.08 + ((seed >> i) % 60) / 1000;
    return {
      indicator_id: ind.numeric_id,
      indicator_name: ind.name,
      frequency: round(freq, 2),
      ci_lower: round(Math.max(0.05, freq - ciHalf), 2),
      ci_upper: round(Math.min(0.98, freq + ciHalf), 2),
      avg_corr_magnitude: round(0.55 + ((seed >> (i * 2)) % 350) / 1000, 2),
    };
  });

  // Coverage diagnostic: 3-5 regions
  const REGIONS = [
    "Sub-Saharan Africa",
    "Latin America",
    "Middle East",
    "South Asia",
    "East Asia",
    "Europe",
    "North America",
    "Oceania",
  ];
  const numRegions = 3 + (seed % 3);
  const startRegion = seed % REGIONS.length;
  const regional_concentration: RegionShare[] = [];
  let remaining = 1.0;
  for (let i = 0; i < numRegions; i++) {
    const ix = (startRegion + i) % REGIONS.length;
    const share =
      i === numRegions - 1
        ? remaining
        : round(Math.min(remaining * 0.6, 0.15 + ((seed >> i) % 250) / 1000), 2);
    regional_concentration.push({ region: REGIONS[ix], share });
    remaining = round(Math.max(0.05, remaining - share), 2);
    if (remaining <= 0) break;
  }

  return {
    event_category: category,
    canonical_length: canonical,
    length_distribution,
    indicator_fingerprint,
    coverage_bias_diagnostic: {
      n_pairs: total,
      oecd_share: round(0.08 + ((seed >> 1) % 350) / 1000, 2),
      regional_concentration,
    },
    total_instances: total,
    n_distinct_country_pairs: total,
    last_recomputed_at: TIMESTAMP,
    contains_predicted: false,
  };
}

function round(n: number, decimals: number): number {
  const f = 10 ** decimals;
  return Math.round(n * f) / f;
}

// ---------------------------------------------------------------------------
// Compose + write
// ---------------------------------------------------------------------------

const handTunedSlugs = new Set(HAND_TUNED.map((r) => r.event_category));
const sketches = L3_CATEGORIES.filter((c) => !handTunedSlugs.has(c)).map(generateSketch);

const all: RecipeAggregated[] = [...HAND_TUNED, ...sketches].sort(
  (a, b) => b.total_instances - a.total_instances
);

const output: RecipesAggregatedFile = {
  generated_at: TIMESTAMP,
  schema_version: 1,
  pipeline_version: "mock-v0",
  recipes: all,
};

// #470 item 1: post-process every fingerprint entry to compute tfidf_score
// from its frequency. Real data ships tfidf from the Athena CTAS (#462);
// the mock approximates it as freq * log(N_total / freq*N_total) which
// preserves the descending-by-tfidf ranking the frontend expects.
const N_TOTAL = 71; // L3 categories
function withTfidf(e: IndicatorFingerprintEntry): IndicatorFingerprintEntry {
  if (e.tfidf_score !== undefined) return e;
  const freq = Math.max(0.001, Math.min(1, e.frequency));
  const idfDenom = Math.max(1, Math.round(freq * N_TOTAL));
  const tfidf = freq * Math.log(N_TOTAL / idfDenom);
  return { ...e, tfidf_score: Number(tfidf.toFixed(4)) };
}
for (const recipe of all) {
  recipe.indicator_fingerprint = recipe.indicator_fingerprint
    .map(withTfidf)
    // The Glue table orders by tfidf desc per #462; mirror here so
    // frontend doesn't need to re-sort on read.
    .sort((a, b) => (b.tfidf_score ?? 0) - (a.tfidf_score ?? 0));
}

const outPath = join(ROOT, "data", "recipes-aggregated-mock.json");
writeFileSync(outPath, JSON.stringify(output, null, 2));
console.log(`Wrote ${all.length} recipes to ${outPath}`);
