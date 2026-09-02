/**
 * recipe-v4-1-mock — supplementary per-recipe V4.1 panel data.
 *
 * V4.1 wire-up (2026-05-29):
 *   - TE sample-10 recipes source from real card-v3 data via lib/te-data-contract/load.ts
 *   - foreign_intervention keeps its hand-authored fallback (demo-graduated case;
 *     no real card exists for it in sample-10)
 *   - civil_war_and_insurgency and constitutional_change keep their hand-authored
 *     data (cascade-era recipes not in the TE sample)
 *
 * CALIBRATION NOTE (per constraint):
 *   calibration.computed is false on every TE recipe in sample-10.
 *   The panel renders: "Calibration not yet computed for this vintage."
 *
 * RANK HISTORY NOTE:
 *   rank_history is first-vintage-only (1 point per country).
 *   The RankHistoryPanel renders: "Rank history available from the next quarterly run."
 *
 * RELIABILITY NOTE:
 *   v1_separation_pp and v4_oot_recall_pct are null in sample-10 (walks_completed: 1).
 *   The reliability panel renders "first vintage" disclosure.
 */

import { loadAllCards, loadAllScores } from "@/lib/te-data-contract/load";
import { resolveIndicatorLabel } from "@/lib/indicator-labels";
import { getRecipe, type IndicatorMock } from "./recipes";

export interface IndicatorWithWeight extends IndicatorMock {
  /** Normalized signal share, 0-100. The recipe's selected set sums to ~100. */
  shapWeightPct: number;
  /** CV AUC drop if this indicator were removed. */
  aucDrop: number;
}

export interface HistogramBin {
  bin_lo: number;
  bin_hi: number;
  count: number;
  countries?: string[];
}

export interface ScoreDistribution {
  histogram: HistogramBin[];
  median: number;
  p90: number;
  p99: number;
  max: number;
}

export interface ReliabilityMetrics {
  /**
   * V1 separation in percentage points. Null = first vintage, no multi-pass yet.
   * UI renders "first vintage" disclosure when null.
   */
  v1SeparationPp: number | null;
  /**
   * V4 OOT recall percent. Null = first vintage.
   */
  v4OotRecallPct: number | null;
  walksCompleted: number;
  verdict: string;
}

export interface CountryScore {
  name: string;
  score: number;
}

interface RecipeV4Extras {
  /** Per-indicator signal share + CV AUC drop. */
  indicators: IndicatorWithWeight[];
  distribution: ScoreDistribution;
  reliability: ReliabilityMetrics;
  /** Bottom-5 by score. */
  countriesBottom: CountryScore[];
  /** Minimum positives required. */
  threshold: number;
  thresholdMet: boolean;
  nCohorts: number;
  walkId: string;
  walkNumber: number;
  ratifiedBy: string;
  walkDate: string;
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Hand-authored extras for cascade-era / demo recipes                         */
/* ────────────────────────────────────────────────────────────────────────── */

const HAND_AUTHORED_EXTRAS: Record<string, RecipeV4Extras> = {
  foreign_intervention: {
    // Demo-graduated case. Kept as-is per spec constraint.
    indicators: [
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shapWeightPct: 38,
        aucDrop: 0.083,
      },
      {
        code: "v2pepwrgen",
        name: "Power Distributed by Gender",
        provider: "V-Dem",
        shapWeightPct: 27,
        aucDrop: 0.052,
      },
      {
        code: "v2stfisccap",
        // 2026-05-29 Naila — catalog-canonical name (VD-11).
        name: "State fiscal capacity",
        provider: "V-Dem",
        shapWeightPct: 20,
        aucDrop: 0.038,
      },
      {
        code: "v2elintmon",
        name: "International Election Monitoring",
        provider: "V-Dem",
        shapWeightPct: 15,
        aucDrop: 0.027,
      },
    ],
    distribution: {
      histogram: [
        { bin_lo: 0, bin_hi: 10, count: 38 },
        { bin_lo: 10, bin_hi: 20, count: 31 },
        { bin_lo: 20, bin_hi: 30, count: 24 },
        { bin_lo: 30, bin_hi: 40, count: 18 },
        { bin_lo: 40, bin_hi: 50, count: 14 },
        { bin_lo: 50, bin_hi: 60, count: 12 },
        { bin_lo: 60, bin_hi: 70, count: 9 },
        { bin_lo: 70, bin_hi: 80, count: 7 },
        { bin_lo: 80, bin_hi: 90, count: 5 },
        { bin_lo: 90, bin_hi: 100, count: 3 },
      ],
      median: 24,
      p90: 68,
      p99: 96,
      max: 98,
    },
    reliability: {
      v1SeparationPp: 25.8,
      v4OotRecallPct: 86.7,
      walksCompleted: 4,
      // Demo graduated — shows a confident result.
      // The real vacate story is on /recipe-tracker; this detail page is the demo.
      verdict: "LOCK",
    },
    countriesBottom: [
      { name: "Switzerland", score: 5.2 },
      { name: "Iceland", score: 5.8 },
      { name: "Norway", score: 6.4 },
      { name: "New Zealand", score: 7.1 },
      { name: "Finland", score: 8.3 },
    ],
    threshold: 60,
    thresholdMet: true,
    nCohorts: 6,
    walkId: "fi_v4_2026-05-21",
    walkNumber: 4,
    ratifiedBy: "Advisory council · 2026-05-22",
    walkDate: "2026-05-21",
  },

  civil_war_and_insurgency: {
    indicators: [
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shapWeightPct: 45,
        aucDrop: 0.072,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral Democracy Index",
        provider: "V-Dem",
        shapWeightPct: 33,
        aucDrop: 0.054,
      },
      {
        code: "v2psoppaut",
        name: "Opposition Autonomy",
        provider: "V-Dem",
        shapWeightPct: 22,
        aucDrop: 0.034,
      },
    ],
    distribution: {
      histogram: [
        { bin_lo: 0, bin_hi: 10, count: 34 },
        { bin_lo: 10, bin_hi: 20, count: 28 },
        { bin_lo: 20, bin_hi: 30, count: 22 },
        { bin_lo: 30, bin_hi: 40, count: 18 },
        { bin_lo: 40, bin_hi: 50, count: 14 },
        { bin_lo: 50, bin_hi: 60, count: 11 },
        { bin_lo: 60, bin_hi: 70, count: 9 },
        { bin_lo: 70, bin_hi: 80, count: 8 },
        { bin_lo: 80, bin_hi: 90, count: 4 },
        { bin_lo: 90, bin_hi: 100, count: 2 },
      ],
      median: 21,
      p90: 64,
      p99: 88,
      max: 91,
    },
    reliability: {
      v1SeparationPp: 14.2,
      v4OotRecallPct: 48.5,
      walksCompleted: 3,
      verdict: "DID_NOT_HOLD",
    },
    countriesBottom: [
      { name: "Switzerland", score: 4.1 },
      { name: "Iceland", score: 5.0 },
      { name: "Norway", score: 5.8 },
      { name: "Singapore", score: 6.3 },
      { name: "Luxembourg", score: 7.0 },
    ],
    threshold: 60,
    thresholdMet: true,
    nCohorts: 6,
    walkId: "cw_v3_2026-05-08",
    walkNumber: 3,
    ratifiedBy: "Advisory council · 2026-05-09",
    walkDate: "2026-05-08",
  },

  constitutional_change: {
    indicators: [
      {
        code: "v2lginvstp",
        name: "Legislative Investigates Executive",
        provider: "V-Dem",
        shapWeightPct: 30,
        aucDrop: 0.058,
      },
      {
        code: "v2juncind",
        name: "Judicial Independence",
        provider: "V-Dem",
        shapWeightPct: 24,
        aucDrop: 0.044,
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral Democracy Index",
        provider: "V-Dem",
        shapWeightPct: 19,
        aucDrop: 0.033,
      },
      {
        code: "RQ.EST",
        name: "Regulatory Quality",
        provider: "World Bank WGI",
        shapWeightPct: 15,
        aucDrop: 0.026,
      },
      {
        code: "v2csprtcpt",
        name: "Civil Society Participatory Environment",
        provider: "V-Dem",
        shapWeightPct: 12,
        aucDrop: 0.019,
      },
    ],
    distribution: {
      histogram: [
        { bin_lo: 0, bin_hi: 10, count: 22 },
        { bin_lo: 10, bin_hi: 20, count: 26 },
        { bin_lo: 20, bin_hi: 30, count: 24 },
        { bin_lo: 30, bin_hi: 40, count: 21 },
        { bin_lo: 40, bin_hi: 50, count: 17 },
        { bin_lo: 50, bin_hi: 60, count: 14 },
        { bin_lo: 60, bin_hi: 70, count: 10 },
        { bin_lo: 70, bin_hi: 80, count: 6 },
        { bin_lo: 80, bin_hi: 90, count: 4 },
        { bin_lo: 90, bin_hi: 100, count: 2 },
      ],
      median: 28,
      p90: 62,
      p99: 88,
      max: 90,
    },
    reliability: {
      v1SeparationPp: 16.0,
      v4OotRecallPct: 52.0,
      walksCompleted: 2,
      verdict: "MARGINAL",
    },
    countriesBottom: [
      { name: "Switzerland", score: 6.2 },
      { name: "Norway", score: 7.5 },
      { name: "Sweden", score: 8.1 },
      { name: "Denmark", score: 9.0 },
      { name: "Finland", score: 9.4 },
    ],
    threshold: 60,
    thresholdMet: true,
    nCohorts: 6,
    walkId: "cc_v2_2026-04-15",
    walkNumber: 2,
    ratifiedBy: "Advisory council · 2026-04-16",
    walkDate: "2026-04-15",
  },
};

/* ────────────────────────────────────────────────────────────────────────── */
/* TE recipe extras — built from real card-v3 data                             */
/* ────────────────────────────────────────────────────────────────────────── */

function resolveIndicatorName(code: string): string {
  const { label } = resolveIndicatorLabel(code);
  return label;
}

function inferProvider(code: string): string {
  if (code.startsWith("v2") || code.startsWith("v3")) return "V-Dem";
  if (code.includes(".")) return "World Bank";
  return "Other";
}

/**
 * Build RecipeV4Extras from a real card-v3 + scores file.
 * Returns null if the card is not available.
 */
function buildFromCard(recipeId: string): RecipeV4Extras | null {
  let card;
  try {
    const allCards = loadAllCards();
    card = allCards[recipeId];
  } catch {
    return null;
  }
  if (!card) return null;

  // LOO sensitivity map for AUC drop values
  const looEntries = card.indicator_sensitivity?.leave_one_out ?? [];
  const looMap = new Map(looEntries.map((e) => [e.code, e]));

  // Normalize LOO AUC drops to signal share %
  // Positive drops get proportional weight; negative/zero get a floor weight.
  const drops = card.greedy_walk.selected_indicators.map((code) => {
    const entry = looMap.get(code);
    return Math.max(0.001, entry?.auc_drop ?? 0.001);
  });
  const totalDrop = drops.reduce((a, b) => a + b, 0);

  const indicators: IndicatorWithWeight[] = card.greedy_walk.selected_indicators.map(
    (code, i) => {
      const entry = looMap.get(code);
      const rawName = entry?.name ?? null;
      const name = rawName ?? resolveIndicatorName(code);
      const provider = inferProvider(code);
      const shapWeightPct = Number(((drops[i] / totalDrop) * 100).toFixed(1));
      const aucDrop = Number((entry?.auc_drop ?? 0).toFixed(4));
      return { code, name, provider, shapWeightPct, aucDrop };
    }
  );

  // Adjust first entry so weights sum to 100 exactly
  const weightsSum = indicators.reduce((s, ind) => s + ind.shapWeightPct, 0);
  if (indicators.length > 0 && weightsSum !== 100) {
    const drift = 100 - weightsSum;
    indicators[0] = {
      ...indicators[0],
      shapWeightPct: Number((indicators[0].shapWeightPct + drift).toFixed(1)),
    };
  }

  // Score distribution from card.score_distribution
  const sd = card.score_distribution;
  const distribution: ScoreDistribution = {
    histogram: sd.histogram.map((b) => ({
      bin_lo: b.bin_lo,
      bin_hi: b.bin_hi,
      count: b.count,
    })),
    median: sd.median,
    p90: sd.p90,
    p99: sd.p99,
    max: sd.max,
  };

  // Reliability from card.reliability_multipass
  const rmp = card.reliability_multipass;
  const reliability: ReliabilityMetrics = {
    v1SeparationPp: rmp.v1_separation_pp, // null in sample-10 — UI renders "first vintage"
    v4OotRecallPct: rmp.v4_oot_recall_pct, // null in sample-10
    walksCompleted: rmp.walks_completed,
    verdict: rmp.verdict,
  };

  // Bottom 5 countries from scores file (lowest score, non-null names)
  let countriesBottom: CountryScore[] = [];
  try {
    const allScores = loadAllScores();
    const sf = allScores[recipeId];
    if (sf?.scores && sf.scores.length > 0) {
      countriesBottom = [...sf.scores]
        .filter((e) => e.name != null)
        .sort((a, b) => a.score - b.score)
        .slice(0, 5)
        .map((e) => ({ name: e.name, score: Number(e.score.toFixed(1)) }));
    }
  } catch {
    // scores unavailable — leave empty
  }

  // Coverage audit / cohort count
  const nPosTotal = card.coverage_audit?.n_pos_total ?? card.n_positives;
  const threshold = 60; // F-ML-1 §3 floor
  const thresholdMet = nPosTotal >= threshold;
  const nCohorts = Object.keys(card.per_cohort ?? {}).length;

  // Walk identity
  const walkDate = card.walked_at_utc ? card.walked_at_utc.split("T")[0] : TE_VINTAGE;

  return {
    indicators,
    distribution,
    reliability,
    countriesBottom,
    threshold,
    thresholdMet,
    nCohorts,
    walkId: `${recipeId}_v1_${walkDate}`,
    walkNumber: 1,
    ratifiedBy: "Wave-1+2 fan-out · 2026-05-28",
    walkDate,
  };
}

// Module-level cache for built TE extras
const _teExtrasCache = new Map<string, RecipeV4Extras | null>();
const TE_VINTAGE = "2026-05-28";

function getTE(recipeId: string): RecipeV4Extras | null {
  if (_teExtrasCache.has(recipeId)) return _teExtrasCache.get(recipeId) ?? null;
  const result = buildFromCard(recipeId);
  _teExtrasCache.set(recipeId, result);
  return result;
}

/**
 * Get recipe V4 extras. Lookup order:
 *   1. Hand-authored (foreign_intervention, civil_war_and_insurgency, constitutional_change)
 *   2. TE card-derived (the 10 sample-10 recipes)
 *   3. null (no data available)
 */
export function getRecipeV4Extras(recipeId: string): RecipeV4Extras | null {
  if (HAND_AUTHORED_EXTRAS[recipeId]) return HAND_AUTHORED_EXTRAS[recipeId];
  return getTE(recipeId);
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Full country roster (capability §8/§9)                                      */
/* ────────────────────────────────────────────────────────────────────────── */

/**
 * Return the full scored-country roster for a recipe, descending by score.
 *
 * TE recipes source from the real scores file.
 * Cascade-era and un-walked recipes fall back to synthesized list.
 */
export function getCountriesFull(recipeId: string): CountryScore[] {
  // Try real scores first
  try {
    const allScores = loadAllScores();
    const sf = allScores[recipeId];
    if (sf?.scores && sf.scores.length > 0) {
      return [...sf.scores]
        .filter((e) => e.name != null)
        .map((e) => ({ name: e.name, score: Number(e.score.toFixed(1)) }))
        .sort((a, b) => b.score - a.score);
    }
  } catch {
    // fall through to synth
  }

  // Demo-graduated case — use the stored hand-authored list
  if (recipeId === "foreign_intervention") {
    return COUNTRIES_FULL_FOREIGN_INTERVENTION.sort((a, b) => b.score - a.score);
  }

  return synthesizeFullList(recipeId);
}

const COUNTRIES_FULL_FOREIGN_INTERVENTION: CountryScore[] = [
  { name: "Iran", score: 98.1 },
  { name: "Turkmenistan", score: 97.0 },
  { name: "Equatorial Guinea", score: 96.9 },
  { name: "Belarus", score: 94.2 },
  { name: "Tajikistan", score: 88.5 },
  { name: "Eritrea", score: 84.7 },
  { name: "Syria", score: 81.3 },
  { name: "North Korea", score: 78.2 },
  { name: "Venezuela", score: 75.8 },
  { name: "Cuba", score: 73.4 },
  { name: "Nicaragua", score: 71.6 },
  { name: "Saudi Arabia", score: 68.9 },
  { name: "Sudan", score: 64.5 },
  { name: "South Sudan", score: 62.7 },
  { name: "Libya", score: 60.8 },
  { name: "Yemen", score: 58.4 },
  { name: "Somalia", score: 55.7 },
  { name: "Central African Republic", score: 53.2 },
  { name: "DRC", score: 51.6 },
  { name: "Ethiopia", score: 48.9 },
  { name: "Honduras", score: 46.4 },
  { name: "Guatemala", score: 44.7 },
  { name: "El Salvador", score: 43.1 },
  { name: "Madagascar", score: 41.5 },
  { name: "Cambodia", score: 39.8 },
  { name: "Laos", score: 38.2 },
  { name: "Myanmar", score: 37.5 },
  { name: "Nigeria", score: 36.1 },
  { name: "Cameroon", score: 35.0 },
  { name: "Uganda", score: 33.7 },
  { name: "Mozambique", score: 32.4 },
  { name: "Burundi", score: 31.2 },
  { name: "Mali", score: 30.5 },
  { name: "Burkina Faso", score: 29.4 },
  { name: "Niger", score: 28.7 },
  { name: "Guinea", score: 28.0 },
  { name: "Afghanistan", score: 27.5 },
  { name: "Pakistan", score: 26.8 },
  { name: "Iraq", score: 26.1 },
  { name: "Egypt", score: 25.4 },
  { name: "Algeria", score: 24.8 },
  { name: "Russia", score: 24.2 },
  { name: "Azerbaijan", score: 23.5 },
  { name: "Kazakhstan", score: 22.7 },
  { name: "Kyrgyzstan", score: 22.0 },
  { name: "Armenia", score: 21.3 },
  { name: "Ukraine", score: 20.6 },
  { name: "Vietnam", score: 19.8 },
  { name: "Thailand", score: 19.2 },
  { name: "Malaysia", score: 18.6 },
  { name: "Bangladesh", score: 17.9 },
  { name: "Nepal", score: 17.3 },
  { name: "Lebanon", score: 16.8 },
  { name: "Jordan", score: 16.2 },
  { name: "Morocco", score: 15.6 },
  { name: "Tunisia", score: 14.9 },
  { name: "Turkey", score: 14.2 },
  { name: "Georgia", score: 13.6 },
  { name: "Moldova", score: 13.0 },
  { name: "Serbia", score: 12.4 },
  { name: "Albania", score: 11.8 },
  { name: "Bosnia and Herzegovina", score: 11.3 },
  { name: "Bulgaria", score: 10.8 },
  { name: "Romania", score: 10.4 },
  { name: "Hungary", score: 10.0 },
  { name: "Mexico", score: 14.5 },
  { name: "Brazil", score: 13.8 },
  { name: "Argentina", score: 12.6 },
  { name: "Colombia", score: 12.1 },
  { name: "India", score: 11.5 },
  { name: "Philippines", score: 11.0 },
  { name: "Indonesia", score: 10.6 },
  { name: "South Africa", score: 10.2 },
  { name: "Israel", score: 9.7 },
  { name: "United States", score: 9.3 },
  { name: "United Kingdom", score: 8.8 },
  { name: "France", score: 8.4 },
  { name: "Italy", score: 8.0 },
  { name: "Spain", score: 7.6 },
  { name: "Germany", score: 7.2 },
  { name: "Belgium", score: 6.9 },
  { name: "Austria", score: 6.6 },
  { name: "Netherlands", score: 6.3 },
  { name: "Portugal", score: 6.0 },
  { name: "Ireland", score: 5.7 },
  { name: "Japan", score: 5.5 },
  { name: "Finland", score: 8.3 },
  { name: "New Zealand", score: 7.1 },
  { name: "Norway", score: 6.4 },
  { name: "Iceland", score: 5.8 },
  { name: "Switzerland", score: 5.2 },
];

const FILLER_POOL = [
  "Russia",
  "Turkey",
  "Egypt",
  "Iraq",
  "Pakistan",
  "Algeria",
  "Mexico",
  "Brazil",
  "Argentina",
  "Colombia",
  "Vietnam",
  "Thailand",
  "Indonesia",
  "Philippines",
  "Nigeria",
  "Kenya",
  "Ghana",
  "Tunisia",
  "Morocco",
  "Jordan",
  "Lebanon",
  "Romania",
  "Hungary",
  "Bulgaria",
  "Serbia",
  "Albania",
  "Georgia",
  "Armenia",
  "Kazakhstan",
  "Uzbekistan",
];

function synthesizeFullList(recipeId: string): CountryScore[] {
  const extras = HAND_AUTHORED_EXTRAS[recipeId];
  const bottom = extras?.countriesBottom ?? [];
  const fillerCount = Math.min(FILLER_POOL.length, 25);
  const peakScore = 80;
  const floorScore = bottom.length > 0 ? bottom[0].score : 10;
  const list: CountryScore[] = [];
  for (let i = 0; i < fillerCount; i++) {
    const t = i / Math.max(1, fillerCount - 1);
    const score = peakScore - t * (peakScore - floorScore - 5);
    list.push({ name: FILLER_POOL[i], score: Math.round(score * 10) / 10 });
  }
  for (const b of bottom) list.push(b);
  return list.sort((a, b) => b.score - a.score);
}

/**
 * Fallback extras for recipes without any data. Returns sensible empty defaults
 * so the page renders without crashing.
 */
export function getFallbackExtras(recipeId: string): RecipeV4Extras {
  const recipe = getRecipe(recipeId);
  return {
    indicators: (recipe?.recipe_id ? [] : []) as IndicatorWithWeight[],
    distribution: { histogram: [], median: 0, p90: 0, p99: 0, max: 0 },
    reliability: {
      v1SeparationPp: null,
      v4OotRecallPct: null,
      walksCompleted: 0,
      verdict: "NO_DATA",
    },
    countriesBottom: [],
    threshold: 60,
    thresholdMet: false,
    nCohorts: 0,
    walkId: "",
    walkNumber: 0,
    ratifiedBy: "",
    walkDate: "",
  };
}
