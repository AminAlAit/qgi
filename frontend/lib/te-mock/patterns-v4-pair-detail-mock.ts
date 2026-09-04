/**
 * patterns-v4-pair-detail-mock — data layer for /patterns/[slug] detail pages.
 *
 * VOCABULARY RULES (binding, no exceptions)
 * ------------------------------------------
 * - No leaderCountry, phaseShiftYears, leadIndicatorCount, aggregateLagYears.
 * - No "leads", "follows", "ahead of", "behind", "phase shift" in any copy.
 * - Two timestamps per indicator (crossingYearA / crossingYearB) are FACTS,
 *   never aggregated into a directional claim.
 * - compositeSeriesA / compositeSeriesB are z-score per year (not probability).
 * - No engine vocabulary: no "cascade", "Pearson", "PPS", "SCDI".
 *
 * Slug shape: {country-a-slug}-{country-b-slug}-{start-year}
 * Country-a-slug is alphabetically first. (Marcus §6.4, binding.)
 */

import { flagFor } from "@/lib/te-mock/country-flags";

// ── Types ─────────────────────────────────────────────────────────────────

export interface PairIndicator {
  code: string;
  name: string;
  provider: string;
  /** 0..100 — how much this indicator loaded into the pair-strength score. */
  contributionPct: number;
  /** Historical year country A crossed a notable threshold on this indicator. */
  crossingYearA: number;
  /** Historical year country B crossed a notable threshold on this indicator. */
  crossingYearB: number;
  /** Plain-English description of the threshold definition. */
  thresholdDefinition: string;
}

export interface DecadeBucket {
  /** e.g. "1970s" */
  decade: string;
  archetype: "ramp" | "oscillation" | "step" | "recovery" | "collapse";
  /** Indicator-composite z-score per year in this decade for country A. */
  seriesA: number[];
  /** Indicator-composite z-score per year in this decade for country B. */
  seriesB: number[];
}

export interface TodaySummary {
  iso: string;
  countryName: string;
  topRecipeLabel: string;
  catalogueRank: number;
}

export interface PairDetail {
  pair_id: string;
  /** Alphabetically-first country name. */
  countryA: string;
  countryB: string;
  /** ISO 3166-1 alpha-2, lowercase. */
  iso2A: string;
  iso2B: string;
  startYear: number;
  endYear: number;
  windowLength: number;
  /** Rank in the catalogue (1-indexed, 1 = strongest). */
  catalogueRank: number;
  catalogueSize: number;
  /** Top 8 indicators by contribution. */
  sharedIndicators: PairIndicator[];
  /** Decade label, e.g. "1980s". */
  strongestDecade: string;
  dominantFamilyA: { l1_id: string; l1_color: string; l1_label: string };
  dominantFamilyB: { l1_id: string; l1_color: string; l1_label: string };
  /** Indicator-composite z-score per year, indexed from startYear. */
  compositeSeriesA: number[];
  compositeSeriesB: number[];
  decadeBuckets: DecadeBucket[];
  todaySummaryA: TodaySummary;
  todaySummaryB: TodaySummary;
}

// ── Helpers ───────────────────────────────────────────────────────────────

/** Decode a flag emoji to ISO 3166-1 alpha-2 (inline, no external dep). */
function flagEmojiToIso2(emoji: string): string {
  try {
    return [...emoji]
      .map((ch) => String.fromCharCode(ch.codePointAt(0)! - 0x1f1e6 + 65))
      .join("")
      .toLowerCase();
  } catch {
    return "";
  }
}

/** Build a simple sine-like z-score series of given length, seeded by offset. */
function mockSeries(len: number, offset: number, phase: number): number[] {
  return Array.from({ length: len }, (_, i) => {
    const t = i / Math.max(len - 1, 1);
    return (
      Math.round(
        (Math.sin(t * Math.PI * 2.2 + phase) * 0.85 +
          t * 1.1 * (offset > 0 ? 1 : -1) +
          Math.sin(t * Math.PI * 5 + offset) * 0.25) *
          100
      ) / 100
    );
  });
}

/** Split a full window series into per-decade buckets. */
function splitIntoBuckets(
  startYear: number,
  seriesA: number[],
  seriesB: number[],
  archetypeMap: Record<string, DecadeBucket["archetype"]>
): DecadeBucket[] {
  const buckets: DecadeBucket[] = [];
  const firstDecade = Math.floor(startYear / 10) * 10;
  const lastYear = startYear + seriesA.length - 1;

  for (let decade = firstDecade; decade <= lastYear; decade += 10) {
    const decadeStart = Math.max(decade, startYear);
    const decadeEnd = Math.min(decade + 9, lastYear);
    const iStart = decadeStart - startYear;
    const iEnd = decadeEnd - startYear;
    const label = `${decade}s`;
    buckets.push({
      decade: label,
      archetype: archetypeMap[label] ?? "ramp",
      seriesA: seriesA.slice(iStart, iEnd + 1),
      seriesB: seriesB.slice(iStart, iEnd + 1),
    });
  }
  return buckets;
}

// ── Mock data ─────────────────────────────────────────────────────────────

const PAIRS: PairDetail[] = [
  // ── paraguay-south_korea-1963 (demo slug) ────────────────────────────
  {
    pair_id: "paraguay-south_korea-1963",
    countryA: "Paraguay",
    countryB: "South Korea",
    iso2A: "py",
    iso2B: "kr",
    startYear: 1963,
    endYear: 2027,
    windowLength: 64,
    catalogueRank: 1,
    catalogueSize: 39,
    sharedIndicators: [
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy index",
        provider: "V-Dem",
        contributionPct: 22,
        crossingYearA: 1989,
        crossingYearB: 1987,
        thresholdDefinition:
          "Crossed the 0.5 threshold on the V-Dem electoral democracy index, marking transition from closed or electoral authoritarian to genuine electoral competition.",
      },
      {
        code: "NY.GDP.PCAP.KD.ZG",
        name: "GDP per capita growth (annual %)",
        provider: "World Bank",
        contributionPct: 18,
        crossingYearA: 1977,
        crossingYearB: 1969,
        thresholdDefinition:
          "Sustained GDP per capita growth above 4% for three or more consecutive years, marking a step shift from stagnant to expanding living standards.",
      },
      {
        code: "v2pepwrgen",
        name: "Power distributed by gender",
        provider: "V-Dem",
        contributionPct: 14,
        crossingYearA: 1992,
        crossingYearB: 1993,
        thresholdDefinition:
          "Crossed the median for the regional peer cohort on V-Dem's gendered power distribution measure, indicating a meaningful shift in formal gender equity.",
      },
      {
        code: "SE.TER.ENRR",
        name: "School enrollment, tertiary (% gross)",
        provider: "World Bank",
        contributionPct: 12,
        crossingYearA: 1995,
        crossingYearB: 1975,
        thresholdDefinition:
          "Gross tertiary enrollment exceeded 10%, marking the start of mass higher-education participation.",
      },
      {
        code: "v2csprtcpt",
        name: "CSO participatory environment",
        provider: "V-Dem",
        contributionPct: 11,
        crossingYearA: 1990,
        crossingYearB: 1988,
        thresholdDefinition:
          "CSO participation index crossed 0.6, indicating a civil society capable of autonomous organisation and public engagement.",
      },
      {
        code: "SP.URB.TOTL.IN.ZS",
        name: "Urban population (% of total)",
        provider: "World Bank",
        contributionPct: 10,
        crossingYearA: 1993,
        crossingYearB: 1975,
        thresholdDefinition:
          "Urban population exceeded 50% of total, marking the majority-urban transition.",
      },
      {
        code: "v2stfisccap",
        name: "Fiscal capacity",
        provider: "V-Dem",
        contributionPct: 8,
        crossingYearA: 2000,
        crossingYearB: 1985,
        thresholdDefinition:
          "State fiscal capacity crossed the 0.5 midpoint of the V-Dem scale, indicating meaningful state revenue-collection and expenditure capacity.",
      },
      {
        code: "GE.EST",
        name: "Government effectiveness (estimate)",
        provider: "World Bank (WGI)",
        contributionPct: 5,
        crossingYearA: 2003,
        crossingYearB: 1996,
        thresholdDefinition:
          "WGI Government Effectiveness estimate crossed 0.0 (the global median), indicating above-median government effectiveness.",
      },
    ],
    strongestDecade: "1980s",
    dominantFamilyA: { l1_id: "A", l1_color: "#7B5EE6", l1_label: "Political Power" },
    dominantFamilyB: { l1_id: "A", l1_color: "#7B5EE6", l1_label: "Political Power" },
    compositeSeriesA: mockSeries(64, 0.4, 0.2),
    compositeSeriesB: mockSeries(64, 0.5, 0.7),
    decadeBuckets: splitIntoBuckets(
      1963,
      mockSeries(64, 0.4, 0.2),
      mockSeries(64, 0.5, 0.7),
      {
        "1960s": "ramp",
        "1970s": "ramp",
        "1980s": "step",
        "1990s": "recovery",
        "2000s": "oscillation",
        "2010s": "oscillation",
        "2020s": "oscillation",
      }
    ),
    todaySummaryA: {
      iso: "py",
      countryName: "Paraguay",
      topRecipeLabel: "elections_and_voting",
      catalogueRank: 12,
    },
    todaySummaryB: {
      iso: "kr",
      countryName: "South Korea",
      topRecipeLabel: "bilateral_treaty",
      catalogueRank: 31,
    },
  },

  // ── argentina-russia-1985 ─────────────────────────────────────────────
  {
    pair_id: "argentina-russia-1985",
    countryA: "Argentina",
    countryB: "Russia",
    iso2A: "ar",
    iso2B: "ru",
    startYear: 1985,
    endYear: 2024,
    windowLength: 39,
    catalogueRank: 2,
    catalogueSize: 39,
    sharedIndicators: [
      {
        code: "FP.CPI.TOTL.ZG",
        name: "Inflation, consumer prices (annual %)",
        provider: "World Bank",
        contributionPct: 26,
        crossingYearA: 1990,
        crossingYearB: 1992,
        thresholdDefinition:
          "Annual inflation exceeded 100%, marking the onset of hyperinflationary conditions.",
      },
      {
        code: "NY.GDP.MKTP.KD.ZG",
        name: "GDP growth (annual %)",
        provider: "World Bank",
        contributionPct: 20,
        crossingYearA: 2002,
        crossingYearB: 1998,
        thresholdDefinition:
          "GDP growth fell below -5% for two or more consecutive years, indicating a deep recessionary contraction.",
      },
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy index",
        provider: "V-Dem",
        contributionPct: 18,
        crossingYearA: 1985,
        crossingYearB: 1991,
        thresholdDefinition:
          "Crossed the 0.5 threshold on the V-Dem electoral democracy index.",
      },
      {
        code: "DT.TDS.DPPF.XP.ZS",
        name: "Debt service (% of exports)",
        provider: "World Bank",
        contributionPct: 15,
        crossingYearA: 2001,
        crossingYearB: 1998,
        thresholdDefinition:
          "External debt service exceeded 25% of goods and services exports, a conventional stress threshold.",
      },
      {
        code: "v2stfisccap",
        name: "Fiscal capacity",
        provider: "V-Dem",
        contributionPct: 12,
        crossingYearA: 2010,
        crossingYearB: 2005,
        thresholdDefinition:
          "State fiscal capacity crossed the 0.5 midpoint of the V-Dem scale.",
      },
      {
        code: "v2x_corr",
        name: "Political corruption index",
        provider: "V-Dem",
        contributionPct: 9,
        crossingYearA: 2015,
        crossingYearB: 2012,
        thresholdDefinition:
          "V-Dem political corruption index exceeded 0.6, indicating systemic corruption.",
      },
    ],
    strongestDecade: "1990s",
    dominantFamilyA: { l1_id: "D", l1_color: "#3FA9F5", l1_label: "Economic Stress" },
    dominantFamilyB: { l1_id: "D", l1_color: "#3FA9F5", l1_label: "Economic Stress" },
    compositeSeriesA: mockSeries(39, 0.3, 1.1),
    compositeSeriesB: mockSeries(39, 0.35, 0.4),
    decadeBuckets: splitIntoBuckets(
      1985,
      mockSeries(39, 0.3, 1.1),
      mockSeries(39, 0.35, 0.4),
      {
        "1980s": "ramp",
        "1990s": "collapse",
        "2000s": "recovery",
        "2010s": "oscillation",
        "2020s": "oscillation",
      }
    ),
    todaySummaryA: {
      iso: "ar",
      countryName: "Argentina",
      topRecipeLabel: "economic_crisis",
      catalogueRank: 8,
    },
    todaySummaryB: {
      iso: "ru",
      countryName: "Russia",
      topRecipeLabel: "multilateral_agreement",
      catalogueRank: 22,
    },
  },

  // ── egypt-tunisia-1975 ────────────────────────────────────────────────
  {
    pair_id: "egypt-tunisia-1975",
    countryA: "Egypt",
    countryB: "Tunisia",
    iso2A: "eg",
    iso2B: "tn",
    startYear: 1975,
    endYear: 2018,
    windowLength: 43,
    catalogueRank: 3,
    catalogueSize: 39,
    sharedIndicators: [
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy index",
        provider: "V-Dem",
        contributionPct: 24,
        crossingYearA: 2011,
        crossingYearB: 2011,
        thresholdDefinition:
          "Crossed the 0.5 threshold on the V-Dem electoral democracy index.",
      },
      {
        code: "SP.POP.GROW",
        name: "Population growth (annual %)",
        provider: "World Bank",
        contributionPct: 19,
        crossingYearA: 1985,
        crossingYearB: 1980,
        thresholdDefinition:
          "Population growth peaked and began a sustained multi-decade decline, marking the demographic transition inflection.",
      },
      {
        code: "SL.UEM.TOTL.ZS",
        name: "Unemployment, total (% of labor force)",
        provider: "World Bank",
        contributionPct: 17,
        crossingYearA: 2011,
        crossingYearB: 2012,
        thresholdDefinition:
          "Total unemployment exceeded 13%, a level historically associated with mass protest mobilization in the region.",
      },
      {
        code: "v2pepwrgen",
        name: "Power distributed by gender",
        provider: "V-Dem",
        contributionPct: 14,
        crossingYearA: 2014,
        crossingYearB: 2014,
        thresholdDefinition:
          "Crossed the median for the regional peer cohort on V-Dem's gendered power distribution measure.",
      },
      {
        code: "v2csprtcpt",
        name: "CSO participatory environment",
        provider: "V-Dem",
        contributionPct: 13,
        crossingYearA: 2012,
        crossingYearB: 2011,
        thresholdDefinition: "CSO participation index crossed 0.6.",
      },
      {
        code: "GE.EST",
        name: "Government effectiveness (estimate)",
        provider: "World Bank (WGI)",
        contributionPct: 13,
        crossingYearA: 2015,
        crossingYearB: 2013,
        thresholdDefinition:
          "WGI Government Effectiveness estimate crossed 0.0 (the global median).",
      },
    ],
    strongestDecade: "2010s",
    dominantFamilyA: { l1_id: "E", l1_color: "#3FBF8F", l1_label: "Social Mobilization" },
    dominantFamilyB: { l1_id: "A", l1_color: "#7B5EE6", l1_label: "Political Power" },
    compositeSeriesA: mockSeries(43, 0.6, 2.1),
    compositeSeriesB: mockSeries(43, 0.55, 1.8),
    decadeBuckets: splitIntoBuckets(
      1975,
      mockSeries(43, 0.6, 2.1),
      mockSeries(43, 0.55, 1.8),
      {
        "1970s": "oscillation",
        "1980s": "ramp",
        "1990s": "step",
        "2000s": "ramp",
        "2010s": "collapse",
      }
    ),
    todaySummaryA: {
      iso: "eg",
      countryName: "Egypt",
      topRecipeLabel: "civil_war",
      catalogueRank: 5,
    },
    todaySummaryB: {
      iso: "tn",
      countryName: "Tunisia",
      topRecipeLabel: "elections_and_voting",
      catalogueRank: 19,
    },
  },

  // ── ghana-senegal-1980 ────────────────────────────────────────────────
  {
    pair_id: "ghana-senegal-1980",
    countryA: "Ghana",
    countryB: "Senegal",
    iso2A: "gh",
    iso2B: "sn",
    startYear: 1980,
    endYear: 2024,
    windowLength: 44,
    catalogueRank: 4,
    catalogueSize: 39,
    sharedIndicators: [
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy index",
        provider: "V-Dem",
        contributionPct: 28,
        crossingYearA: 1993,
        crossingYearB: 1988,
        thresholdDefinition:
          "Crossed the 0.5 threshold on the V-Dem electoral democracy index.",
      },
      {
        code: "NY.GDP.PCAP.KD.ZG",
        name: "GDP per capita growth (annual %)",
        provider: "World Bank",
        contributionPct: 21,
        crossingYearA: 1984,
        crossingYearB: 1995,
        thresholdDefinition:
          "Sustained GDP per capita growth above 3% for three or more consecutive years.",
      },
      {
        code: "v2csprtcpt",
        name: "CSO participatory environment",
        provider: "V-Dem",
        contributionPct: 16,
        crossingYearA: 1992,
        crossingYearB: 1990,
        thresholdDefinition: "CSO participation index crossed 0.6.",
      },
      {
        code: "SE.PRM.ENRR",
        name: "School enrollment, primary (% gross)",
        provider: "World Bank",
        contributionPct: 14,
        crossingYearA: 1995,
        crossingYearB: 1998,
        thresholdDefinition:
          "Gross primary enrollment exceeded 90%, indicating near-universal primary access.",
      },
      {
        code: "GE.EST",
        name: "Government effectiveness (estimate)",
        provider: "World Bank (WGI)",
        contributionPct: 21,
        crossingYearA: 2000,
        crossingYearB: 2005,
        thresholdDefinition:
          "WGI Government Effectiveness estimate crossed 0.0 (the global median).",
      },
    ],
    strongestDecade: "1990s",
    dominantFamilyA: { l1_id: "C", l1_color: "#E68F29", l1_label: "Governance & Rights" },
    dominantFamilyB: { l1_id: "C", l1_color: "#E68F29", l1_label: "Governance & Rights" },
    compositeSeriesA: mockSeries(44, 0.2, 0.9),
    compositeSeriesB: mockSeries(44, 0.25, 0.3),
    decadeBuckets: splitIntoBuckets(
      1980,
      mockSeries(44, 0.2, 0.9),
      mockSeries(44, 0.25, 0.3),
      {
        "1980s": "step",
        "1990s": "ramp",
        "2000s": "recovery",
        "2010s": "oscillation",
        "2020s": "oscillation",
      }
    ),
    todaySummaryA: {
      iso: "gh",
      countryName: "Ghana",
      topRecipeLabel: "elections_and_voting",
      catalogueRank: 28,
    },
    todaySummaryB: {
      iso: "sn",
      countryName: "Senegal",
      topRecipeLabel: "elections_and_voting",
      catalogueRank: 34,
    },
  },

  // ── poland-czech_republic-1989 ────────────────────────────────────────
  {
    pair_id: "poland-czech_republic-1989",
    countryA: "Czech Republic",
    countryB: "Poland",
    iso2A: "cz",
    iso2B: "pl",
    startYear: 1989,
    endYear: 2024,
    windowLength: 35,
    catalogueRank: 5,
    catalogueSize: 39,
    sharedIndicators: [
      {
        code: "v2x_polyarchy",
        name: "Electoral democracy index",
        provider: "V-Dem",
        contributionPct: 30,
        crossingYearA: 1990,
        crossingYearB: 1991,
        thresholdDefinition:
          "Crossed the 0.5 threshold on the V-Dem electoral democracy index.",
      },
      {
        code: "NY.GDP.MKTP.KD.ZG",
        name: "GDP growth (annual %)",
        provider: "World Bank",
        contributionPct: 22,
        crossingYearA: 1993,
        crossingYearB: 1992,
        thresholdDefinition:
          "GDP growth recovered to positive territory after the post-transition contraction.",
      },
      {
        code: "v2stfisccap",
        name: "Fiscal capacity",
        provider: "V-Dem",
        contributionPct: 18,
        crossingYearA: 1995,
        crossingYearB: 1997,
        thresholdDefinition:
          "State fiscal capacity crossed the 0.5 midpoint of the V-Dem scale.",
      },
      {
        code: "GE.EST",
        name: "Government effectiveness (estimate)",
        provider: "World Bank (WGI)",
        contributionPct: 15,
        crossingYearA: 1996,
        crossingYearB: 1998,
        thresholdDefinition: "WGI Government Effectiveness estimate exceeded +0.5.",
      },
      {
        code: "v2csprtcpt",
        name: "CSO participatory environment",
        provider: "V-Dem",
        contributionPct: 15,
        crossingYearA: 1991,
        crossingYearB: 1990,
        thresholdDefinition: "CSO participation index crossed 0.6.",
      },
    ],
    strongestDecade: "1990s",
    dominantFamilyA: { l1_id: "A", l1_color: "#7B5EE6", l1_label: "Political Power" },
    dominantFamilyB: { l1_id: "A", l1_color: "#7B5EE6", l1_label: "Political Power" },
    compositeSeriesA: mockSeries(35, 0.45, 1.5),
    compositeSeriesB: mockSeries(35, 0.4, 1.9),
    decadeBuckets: splitIntoBuckets(
      1989,
      mockSeries(35, 0.45, 1.5),
      mockSeries(35, 0.4, 1.9),
      {
        "1980s": "collapse",
        "1990s": "ramp",
        "2000s": "step",
        "2010s": "oscillation",
        "2020s": "oscillation",
      }
    ),
    todaySummaryA: {
      iso: "cz",
      countryName: "Czech Republic",
      topRecipeLabel: "bilateral_treaty",
      catalogueRank: 45,
    },
    todaySummaryB: {
      iso: "pl",
      countryName: "Poland",
      topRecipeLabel: "bilateral_treaty",
      catalogueRank: 38,
    },
  },
];

// ── Index ─────────────────────────────────────────────────────────────────

const INDEX: Record<string, PairDetail> = {};
for (const p of PAIRS) {
  INDEX[p.pair_id] = p;
}

/**
 * Alias map: compact pair_ids used by the main-data catalogue
 * (lib/te-mock/patterns-v4-main-data.ts) → the long-form slugs this file's
 * hand-authored detail entries are keyed on.
 *
 * Pairs NOT in this map fall through to the deterministic synthesizer below,
 * so every row in the main-data catalogue navigates to a working detail page.
 */
const SLUG_ALIASES: Record<string, string> = {
  "pry-kor": "paraguay-south_korea-1963",
  "arg-rus": "argentina-russia-1985",
  "tun-egy": "egypt-tunisia-1975",
  "gha-sen": "ghana-senegal-1980",
  "pol-cze": "poland-czech_republic-1989",
};

// ── Synthesizer for catalog pairs without hand-authored detail ────────────
//
// Every PairRow in `lib/te-mock/patterns-v4-main-data.ts` deserves a working
// detail page. For the 5 with hand-authored entries above, INDEX/SLUG_ALIASES
// route directly. For the other ~35, we synthesize a deterministic PairDetail
// from the row's existing fields (countries, years, window). The synthesized
// content respects the symmetric framing rule: no leader/follower vocab,
// no aggregated timestamps, two crossing years per indicator as facts.

import type { PairRow } from "./patterns-v4-main-data";
import { getFullCatalogue } from "./patterns-v4-main-data";
import { L1_FAMILIES, familyColor, NEUTRAL_SLATE } from "./l1-families";

/** Deterministic seeded PRNG in [0, 1) derived from a string. */
function seedFrom(s: string): () => number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  }
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    h = (h ^ (h >>> 16)) >>> 0;
    return h / 4294967296;
  };
}

const INDICATOR_POOL = [
  { code: "v2x_libdem", name: "Liberal democracy index", provider: "V-Dem" },
  { code: "v2x_polyarchy", name: "Electoral democracy index", provider: "V-Dem" },
  { code: "v2psprbrch", name: "Party branches", provider: "V-Dem" },
  { code: "v2eltrnout", name: "Voter turnout", provider: "V-Dem" },
  { code: "v2x_corr", name: "Political corruption index", provider: "V-Dem" },
  { code: "v2elffelr", name: "Election free and fair", provider: "V-Dem" },
  { code: "FP.CPI.TOTL.ZG", name: "Inflation, consumer prices", provider: "World Bank" },
  { code: "NY.GDP.MKTP.KD.ZG", name: "GDP growth", provider: "World Bank" },
  { code: "BN.CAB.XOKA.CD", name: "Current account balance", provider: "World Bank" },
  { code: "SI.POV.GINI", name: "Gini coefficient", provider: "World Bank" },
  {
    code: "FAOSTAT.GFCF.AGR",
    name: "Capital formation in agriculture",
    provider: "FAOSTAT",
  },
  { code: "ILO.UE.RATE", name: "Unemployment rate", provider: "ILOSTAT" },
];

const ARCHETYPE_POOL: DecadeBucket["archetype"][] = [
  "ramp",
  "oscillation",
  "step",
  "recovery",
  "collapse",
];

const FAMILY_IDS = ["A", "B", "C", "D", "E", "F", "G", "H"];

function synthesizePairDetail(
  row: PairRow,
  catalogueRank: number,
  catalogueSize: number
): PairDetail {
  const rand = seedFrom(row.pair_id);

  // 8 indicators picked deterministically from the pool with normalized contributions.
  const pool = [...INDICATOR_POOL].sort(() => rand() - 0.5).slice(0, 8);
  const rawContribs = pool.map(() => 5 + rand() * 20);
  const sumContribs = rawContribs.reduce((a, b) => a + b, 0);
  const sharedIndicators: PairIndicator[] = pool.map((ind, i) => ({
    code: ind.code,
    name: ind.name,
    provider: ind.provider,
    contributionPct: Number(((rawContribs[i] / sumContribs) * 100).toFixed(1)),
    crossingYearA: row.start_year + Math.floor(rand() * row.window_years * 0.7),
    crossingYearB: row.start_year + Math.floor(rand() * row.window_years * 0.7),
    thresholdDefinition: `${ind.name} z-score crossed +1.5 SD above its country baseline.`,
  }));

  // Composite z-score series, one entry per year of the shared window.
  const seriesLen = Math.max(2, row.window_years);
  const compositeSeriesA: number[] = [];
  const compositeSeriesB: number[] = [];
  for (let i = 0; i < seriesLen; i++) {
    const phase = i / seriesLen;
    const baseA = Math.sin(phase * Math.PI * 2 + rand() * 0.6) * 1.4;
    const baseB = Math.sin(phase * Math.PI * 2 + rand() * 0.6 + 0.3) * 1.4;
    compositeSeriesA.push(Number((baseA + (rand() - 0.5) * 0.5).toFixed(2)));
    compositeSeriesB.push(Number((baseB + (rand() - 0.5) * 0.5).toFixed(2)));
  }

  // Decade buckets covering the window.
  const startDecade = Math.floor(row.start_year / 10) * 10;
  const endDecade = Math.floor(row.end_year / 10) * 10;
  const decadeBuckets: DecadeBucket[] = [];
  for (let d = startDecade; d <= endDecade; d += 10) {
    const offset = Math.max(0, d - row.start_year);
    const sliceA = compositeSeriesA.slice(offset, offset + 10);
    const sliceB = compositeSeriesB.slice(offset, offset + 10);
    decadeBuckets.push({
      decade: `${d}s`,
      archetype: ARCHETYPE_POOL[Math.floor(rand() * ARCHETYPE_POOL.length)],
      seriesA:
        sliceA.length > 0
          ? sliceA
          : compositeSeriesA.slice(0, Math.min(10, compositeSeriesA.length)),
      seriesB:
        sliceB.length > 0
          ? sliceB
          : compositeSeriesB.slice(0, Math.min(10, compositeSeriesB.length)),
    });
  }
  const strongestDecade =
    decadeBuckets[Math.floor(decadeBuckets.length / 2)]?.decade ??
    decadeBuckets[0]?.decade ??
    `${startDecade}s`;

  // Family assignment per country — deterministic hash of country name.
  const famAIdx = Math.floor(seedFrom(row.country_a_name)() * FAMILY_IDS.length);
  const famBIdx = Math.floor(seedFrom(row.country_b_name)() * FAMILY_IDS.length);
  const familyMeta = (id: string) => ({
    l1_id: id,
    l1_color: familyColor(id, NEUTRAL_SLATE),
    l1_label: L1_FAMILIES[id]?.label ?? id,
  });

  return {
    pair_id: row.pair_id,
    countryA: row.country_a_name,
    countryB: row.country_b_name,
    iso2A: row.country_a_iso.toLowerCase(),
    iso2B: row.country_b_iso.toLowerCase(),
    startYear: row.start_year,
    endYear: row.end_year,
    windowLength: row.window_years,
    catalogueRank,
    catalogueSize,
    sharedIndicators,
    strongestDecade,
    dominantFamilyA: familyMeta(FAMILY_IDS[famAIdx]),
    dominantFamilyB: familyMeta(FAMILY_IDS[famBIdx]),
    compositeSeriesA,
    compositeSeriesB,
    decadeBuckets,
    todaySummaryA: {
      iso: row.country_a_iso.toLowerCase(),
      countryName: row.country_a_name,
      topRecipeLabel: "currently in play on multiple recipes",
      catalogueRank: Math.floor(rand() * 50) + 1,
    },
    todaySummaryB: {
      iso: row.country_b_iso.toLowerCase(),
      countryName: row.country_b_name,
      topRecipeLabel: "currently in play on multiple recipes",
      catalogueRank: Math.floor(rand() * 50) + 1,
    },
  };
}

// ── Accessors ─────────────────────────────────────────────────────────────

export function getPair(slug: string): PairDetail | undefined {
  // 1. Long-form hand-authored slug, exact match.
  if (INDEX[slug]) return INDEX[slug];

  // 2. Compact slug aliased to a hand-authored long-form entry.
  const aliased = SLUG_ALIASES[slug];
  if (aliased && INDEX[aliased]) return INDEX[aliased];

  // 3. Synthesize from main-data catalogue for any other catalog row.
  const catalogue = getFullCatalogue();
  const idx = catalogue.findIndex((r) => r.pair_id === slug);
  if (idx >= 0) {
    return synthesizePairDetail(catalogue[idx], idx + 1, catalogue.length);
  }

  return undefined;
}

export function getAllPairSlugs(): string[] {
  // Every long-form hand-authored slug + every compact alias + every
  // catalogue pair_id. generateStaticParams pre-renders all forms; the
  // synthesizer covers any catalog row not in the alias map.
  const catalogue = getFullCatalogue();
  const all = new Set<string>([
    ...Object.keys(INDEX),
    ...Object.keys(SLUG_ALIASES),
    ...catalogue.map((r) => r.pair_id),
  ]);
  return Array.from(all);
}

/** Emoji flag for a country name -- thin wrapper for components. */
export function pairDetailFlagFor(name: string): string {
  return flagFor(name);
}
