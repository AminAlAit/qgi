/**
 * patterns-v4-main-data — data layer for the /patterns main catalogue page.
 *
 * SEPARATE from lib/te-mock/patterns-v4-data.ts, which describes
 * recipe-internal shape data (canonical movement trajectories per recipe).
 * This file describes COUNTRY PAIRS: two countries whose indicator-composite
 * histories ran in close parallel over a shared multi-decade window.
 *
 * VOCABULARY RULES (binding, no exceptions)
 * ------------------------------------------
 * - No engine-distinction vocabulary: no "cascade", "Pearson", "PPS",
 *   "SCDI", "trajectory engine", "ML-2 TE".
 * - Pair strength is a 0-100 RANK, not a probability.
 * - featured_editorial MUST be HISTORICAL-VOICE ONLY: describe the two
 *   countries' histories during the shared window. MUST NOT describe either
 *   country's present-day recipe activations, current scores, or live signals.
 *   This constraint is enforced by code review convention; there is no
 *   runtime guard, so every editor of this file must check manually.
 *
 * METHODOLOGY INTEGRITY (Marcus, binding)
 * ----------------------------------------
 * - No statusLabel chip data on pair rows.
 * - No family-color border or family-letter glyph on pair rows.
 * - Family-overlap filter uses families as navigation aid only; the pair
 *   row itself carries no family identity.
 */

import { flagFor } from "@/lib/te-mock/country-flags";

export interface PairRow {
  pair_id: string;
  country_a_iso: string;
  country_a_name: string;
  country_b_iso: string;
  country_b_name: string;
  /** ISO 3166-1 alpha-2, lowercase, for flagcdn */
  start_year: number;
  end_year: number;
  window_years: number;
  /** 0..100 integer; rank, not probability */
  pair_strength: number;
}

export interface FeaturedPair extends PairRow {
  /**
   * HISTORICAL-VOICE ONLY constraint.
   * Describe the historical pair: the two countries, the years, what happened
   * in those years to each country. MUST NOT describe either country's
   * present-day recipe activations, current scores, or live signals.
   */
  featured_editorial: string;
}

export interface RecentlySurfacedPair extends PairRow {
  surfaced_reason: "new_this_vintage" | "rose_in_rank";
  prior_strength?: number;
}

export interface PatternsV4Catalogue {
  vintage: string;
  total_pairs: number;
  median_window_years: number;
  longest_pair: PairRow;
  /** Top 30 pairs by pair_strength desc; full list available from getFullCatalogue() */
  ranking_top_30: PairRow[];
  featured_pair: FeaturedPair;
  recently_surfaced: RecentlySurfacedPair[];
}

// ── L1 families present in the mock catalogue, for family-overlap filter ──
// Each entry lists the ISO codes of countries currently active on a recipe
// in that family. The family-browse filter keeps pairs where AT LEAST ONE
// country in the pair appears in this set.
// (Mock approximation: real implementation would query recipe activations.)

export const FAMILY_ACTIVE_ISOS: Record<string, string[]> = {
  A: ["dz", "by", "hn", "kz", "ru", "tr", "ve", "tz"],
  B: ["sd", "mm", "so", "sy", "ye", "ly", "af", "ml", "cf"],
  C: ["cn", "kp", "er", "tz", "by", "ru", "ni"],
  D: ["ar", "lb", "gr", "ve", "lk", "tr", "eg", "ng"],
  E: ["eg", "cl", "hk", "ir", "sd", "by", "hn", "br"],
  F: ["ma", "vn", "co", "kz", "cr", "ie"],
  G: ["sd", "so", "sy", "ye", "af", "mm", "ni"],
  H: ["de", "au", "ca", "nz", "kr", "jp"],
};

// ── Full pair catalogue ───────────────────────────────────────────────────

const FULL_CATALOGUE: PairRow[] = [
  // ── Top 30 by pair_strength ──────────────────────────────────────────
  {
    pair_id: "pry-kor",
    country_a_iso: "py",
    country_a_name: "Paraguay",
    country_b_iso: "kr",
    country_b_name: "South Korea",
    start_year: 1963,
    end_year: 2027,
    window_years: 64,
    pair_strength: 91,
  },
  {
    pair_id: "arg-rus",
    country_a_iso: "ar",
    country_a_name: "Argentina",
    country_b_iso: "ru",
    country_b_name: "Russia",
    start_year: 1985,
    end_year: 2024,
    window_years: 39,
    pair_strength: 88,
  },
  {
    pair_id: "tun-egy",
    country_a_iso: "tn",
    country_a_name: "Tunisia",
    country_b_iso: "eg",
    country_b_name: "Egypt",
    start_year: 1975,
    end_year: 2018,
    window_years: 43,
    pair_strength: 86,
  },
  {
    pair_id: "gha-sen",
    country_a_iso: "gh",
    country_a_name: "Ghana",
    country_b_iso: "sn",
    country_b_name: "Senegal",
    start_year: 1980,
    end_year: 2024,
    window_years: 44,
    pair_strength: 84,
  },
  {
    pair_id: "pol-cze",
    country_a_iso: "pl",
    country_a_name: "Poland",
    country_b_iso: "cz",
    country_b_name: "Czech Republic",
    start_year: 1989,
    end_year: 2024,
    window_years: 35,
    pair_strength: 83,
  },
  {
    pair_id: "chl-uru",
    country_a_iso: "cl",
    country_a_name: "Chile",
    country_b_iso: "uy",
    country_b_name: "Uruguay",
    start_year: 1990,
    end_year: 2024,
    window_years: 34,
    pair_strength: 82,
  },
  {
    pair_id: "idn-phl",
    country_a_iso: "id",
    country_a_name: "Indonesia",
    country_b_iso: "ph",
    country_b_name: "Philippines",
    start_year: 1970,
    end_year: 2015,
    window_years: 45,
    pair_strength: 81,
  },
  {
    pair_id: "mex-col",
    country_a_iso: "mx",
    country_a_name: "Mexico",
    country_b_iso: "co",
    country_b_name: "Colombia",
    start_year: 1985,
    end_year: 2024,
    window_years: 39,
    pair_strength: 80,
  },
  {
    pair_id: "nga-eth",
    country_a_iso: "ng",
    country_a_name: "Nigeria",
    country_b_iso: "et",
    country_b_name: "Ethiopia",
    start_year: 1993,
    end_year: 2024,
    window_years: 31,
    pair_strength: 79,
  },
  {
    pair_id: "ukr-geo",
    country_a_iso: "ua",
    country_a_name: "Ukraine",
    country_b_iso: "ge",
    country_b_name: "Georgia",
    start_year: 2000,
    end_year: 2024,
    window_years: 24,
    pair_strength: 78,
  },
  {
    pair_id: "irn-vnm",
    country_a_iso: "ir",
    country_a_name: "Iran",
    country_b_iso: "vn",
    country_b_name: "Vietnam",
    start_year: 1980,
    end_year: 2020,
    window_years: 40,
    pair_strength: 77,
  },
  {
    pair_id: "lbn-grc",
    country_a_iso: "lb",
    country_a_name: "Lebanon",
    country_b_iso: "gr",
    country_b_name: "Greece",
    start_year: 2000,
    end_year: 2022,
    window_years: 22,
    pair_strength: 76,
  },
  {
    pair_id: "per-bol",
    country_a_iso: "pe",
    country_a_name: "Peru",
    country_b_iso: "bo",
    country_b_name: "Bolivia",
    start_year: 1993,
    end_year: 2024,
    window_years: 31,
    pair_strength: 75,
  },
  {
    pair_id: "mys-tha",
    country_a_iso: "my",
    country_a_name: "Malaysia",
    country_b_iso: "th",
    country_b_name: "Thailand",
    start_year: 1970,
    end_year: 2020,
    window_years: 50,
    pair_strength: 74,
  },
  {
    pair_id: "mda-hrv",
    country_a_iso: "md",
    country_a_name: "Moldova",
    country_b_iso: "hr",
    country_b_name: "Croatia",
    start_year: 1996,
    end_year: 2024,
    window_years: 28,
    pair_strength: 73,
  },
  {
    pair_id: "ken-uga",
    country_a_iso: "ke",
    country_a_name: "Kenya",
    country_b_iso: "ug",
    country_b_name: "Uganda",
    start_year: 1990,
    end_year: 2024,
    window_years: 34,
    pair_strength: 72,
  },
  {
    pair_id: "pak-bgd",
    country_a_iso: "pk",
    country_a_name: "Pakistan",
    country_b_iso: "bd",
    country_b_name: "Bangladesh",
    start_year: 1978,
    end_year: 2022,
    window_years: 44,
    pair_strength: 71,
  },
  {
    pair_id: "arm-aze",
    country_a_iso: "am",
    country_a_name: "Armenia",
    country_b_iso: "az",
    country_b_name: "Azerbaijan",
    start_year: 1994,
    end_year: 2024,
    window_years: 30,
    pair_strength: 70,
  },
  {
    pair_id: "kaz-uzb",
    country_a_iso: "kz",
    country_a_name: "Kazakhstan",
    country_b_iso: "uz",
    country_b_name: "Uzbekistan",
    start_year: 1991,
    end_year: 2024,
    window_years: 33,
    pair_strength: 69,
  },
  {
    pair_id: "ven-ecu",
    country_a_iso: "ve",
    country_a_name: "Venezuela",
    country_b_iso: "ec",
    country_b_name: "Ecuador",
    start_year: 1999,
    end_year: 2024,
    window_years: 25,
    pair_strength: 68,
  },
  {
    pair_id: "dza-mar",
    country_a_iso: "dz",
    country_a_name: "Algeria",
    country_b_iso: "ma",
    country_b_name: "Morocco",
    start_year: 1970,
    end_year: 2022,
    window_years: 52,
    pair_strength: 67,
  },
  {
    pair_id: "zaf-bwa",
    country_a_iso: "za",
    country_a_name: "South Africa",
    country_b_iso: "bw",
    country_b_name: "Botswana",
    start_year: 1990,
    end_year: 2024,
    window_years: 34,
    pair_strength: 66,
  },
  {
    pair_id: "ind-lka",
    country_a_iso: "in",
    country_a_name: "India",
    country_b_iso: "lk",
    country_b_name: "Sri Lanka",
    start_year: 1980,
    end_year: 2024,
    window_years: 44,
    pair_strength: 65,
  },
  {
    pair_id: "irl-dnk",
    country_a_iso: "ie",
    country_a_name: "Ireland",
    country_b_iso: "dk",
    country_b_name: "Denmark",
    start_year: 1975,
    end_year: 2024,
    window_years: 49,
    pair_strength: 64,
  },
  {
    pair_id: "khm-mmr",
    country_a_iso: "kh",
    country_a_name: "Cambodia",
    country_b_iso: "mm",
    country_b_name: "Myanmar",
    start_year: 1998,
    end_year: 2024,
    window_years: 26,
    pair_strength: 63,
  },
  {
    pair_id: "bra-mex-2",
    country_a_iso: "br",
    country_a_name: "Brazil",
    country_b_iso: "mx",
    country_b_name: "Mexico",
    start_year: 1994,
    end_year: 2024,
    window_years: 30,
    pair_strength: 62,
  },
  {
    pair_id: "hnd-nic",
    country_a_iso: "hn",
    country_a_name: "Honduras",
    country_b_iso: "ni",
    country_b_name: "Nicaragua",
    start_year: 1990,
    end_year: 2024,
    window_years: 34,
    pair_strength: 61,
  },
  {
    pair_id: "tcd-caf",
    country_a_iso: "td",
    country_a_name: "Chad",
    country_b_iso: "cf",
    country_b_name: "Central African Republic",
    start_year: 2004,
    end_year: 2024,
    window_years: 20,
    pair_strength: 60,
  },
  {
    pair_id: "nga-civ",
    country_a_iso: "ng",
    country_a_name: "Nigeria",
    country_b_iso: "ci",
    country_b_name: "Cote d'Ivoire",
    start_year: 2000,
    end_year: 2024,
    window_years: 24,
    pair_strength: 59,
  },
  {
    pair_id: "svk-hun",
    country_a_iso: "sk",
    country_a_name: "Slovakia",
    country_b_iso: "hu",
    country_b_name: "Hungary",
    start_year: 1993,
    end_year: 2024,
    window_years: 31,
    pair_strength: 58,
  },
  // ── Additional pairs beyond top 30 (for "Show all N pairs" expand) ──
  {
    pair_id: "egy-jor",
    country_a_iso: "eg",
    country_a_name: "Egypt",
    country_b_iso: "jo",
    country_b_name: "Jordan",
    start_year: 1980,
    end_year: 2022,
    window_years: 42,
    pair_strength: 57,
  },
  {
    pair_id: "bel-mda",
    country_a_iso: "by",
    country_a_name: "Belarus",
    country_b_iso: "md",
    country_b_name: "Moldova",
    start_year: 1993,
    end_year: 2022,
    window_years: 29,
    pair_strength: 56,
  },
  {
    pair_id: "mlw-zmb",
    country_a_iso: "mw",
    country_a_name: "Malawi",
    country_b_iso: "zm",
    country_b_name: "Zambia",
    start_year: 1994,
    end_year: 2024,
    window_years: 30,
    pair_strength: 55,
  },
  {
    pair_id: "tur-egy",
    country_a_iso: "tr",
    country_a_name: "Turkey",
    country_b_iso: "eg",
    country_b_name: "Egypt",
    start_year: 2002,
    end_year: 2022,
    window_years: 20,
    pair_strength: 54,
  },
  {
    pair_id: "ago-moz",
    country_a_iso: "ao",
    country_a_name: "Angola",
    country_b_iso: "mz",
    country_b_name: "Mozambique",
    start_year: 1994,
    end_year: 2024,
    window_years: 30,
    pair_strength: 53,
  },
  {
    pair_id: "npl-btn",
    country_a_iso: "np",
    country_a_name: "Nepal",
    country_b_iso: "bt",
    country_b_name: "Bhutan",
    start_year: 1990,
    end_year: 2022,
    window_years: 32,
    pair_strength: 52,
  },
  {
    pair_id: "lva-est",
    country_a_iso: "lv",
    country_a_name: "Latvia",
    country_b_iso: "ee",
    country_b_name: "Estonia",
    start_year: 1991,
    end_year: 2024,
    window_years: 33,
    pair_strength: 51,
  },
  {
    pair_id: "mng-kgz",
    country_a_iso: "mn",
    country_a_name: "Mongolia",
    country_b_iso: "kg",
    country_b_name: "Kyrgyzstan",
    start_year: 1991,
    end_year: 2024,
    window_years: 33,
    pair_strength: 50,
  },
  {
    pair_id: "cri-pan",
    country_a_iso: "cr",
    country_a_name: "Costa Rica",
    country_b_iso: "pa",
    country_b_name: "Panama",
    start_year: 1975,
    end_year: 2024,
    window_years: 49,
    pair_strength: 49,
  },
  {
    pair_id: "irl-prt",
    country_a_iso: "ie",
    country_a_name: "Ireland",
    country_b_iso: "pt",
    country_b_name: "Portugal",
    start_year: 1986,
    end_year: 2024,
    window_years: 38,
    pair_strength: 48,
  },
];

// ── Featured pair ────────────────────────────────────────────────────────
// HISTORICAL-VOICE ONLY: describes what happened in Paraguay and South Korea
// during 1963-2027. MUST NOT describe either country's current recipe scores
// or live activations.

export const FEATURED_PAIR: FeaturedPair = {
  ...FULL_CATALOGUE[0],
  featured_editorial:
    "Paraguay and South Korea followed strikingly parallel arcs from the 1960s through the 2020s. Both started the period as agrarian, authoritarian states with thin institutional capacity and economies tied to a small number of export commodities. Both experienced prolonged single-party or military rule -- Paraguay under the Stroessner regime from 1954 to 1989, South Korea under Park Chung-hee and his successors from 1961 to 1987 -- before transitioning to contested multiparty elections within a few years of one another. In both countries, the transition period produced rapid expansion of a formal middle class, rising urbanization, and significant investment in public education. The two economies then diverged sharply in the 1990s as South Korea accelerated into a high-technology export model while Paraguay remained commodity-dependent, but the institutional trajectory -- democratic consolidation, expanding civil society, cyclical corruption crises -- continued to rhyme closely through the 2020s. The pair holds the longest continuous window in the current catalogue: sixty-four years of indicator co-movement across governance, economic structure, and social mobilization indices.",
};

// ── Recently surfaced pairs ───────────────────────────────────────────────

export const RECENTLY_SURFACED: RecentlySurfacedPair[] = [
  {
    ...FULL_CATALOGUE.find((p) => p.pair_id === "ukr-geo")!,
    surfaced_reason: "rose_in_rank",
    prior_strength: 65,
  },
  {
    ...FULL_CATALOGUE.find((p) => p.pair_id === "lbn-grc")!,
    surfaced_reason: "rose_in_rank",
    prior_strength: 69,
  },
  {
    ...FULL_CATALOGUE.find((p) => p.pair_id === "tcd-caf")!,
    surfaced_reason: "new_this_vintage",
  },
  {
    ...FULL_CATALOGUE.find((p) => p.pair_id === "svk-hun")!,
    surfaced_reason: "new_this_vintage",
  },
  {
    ...FULL_CATALOGUE.find((p) => p.pair_id === "khm-mmr")!,
    surfaced_reason: "rose_in_rank",
    prior_strength: 58,
  },
  {
    ...FULL_CATALOGUE.find((p) => p.pair_id === "ven-ecu")!,
    surfaced_reason: "rose_in_rank",
    prior_strength: 62,
  },
];

// ── Catalogue accessor ───────────────────────────────────────────────────

let _cache: PatternsV4Catalogue | null = null;

export function getPatternsCatalogue(): PatternsV4Catalogue {
  if (_cache) return _cache;

  const sorted = [...FULL_CATALOGUE].sort((a, b) => b.pair_strength - a.pair_strength);
  const windows = sorted.map((p) => p.window_years).sort((a, b) => a - b);
  const mid = Math.floor(windows.length / 2);
  const medianWindow =
    windows.length % 2 === 0
      ? Math.round((windows[mid - 1] + windows[mid]) / 2)
      : windows[mid];
  const longest = sorted.reduce((best, p) =>
    p.window_years > best.window_years ? p : best
  );

  _cache = {
    vintage: "2026-Q2",
    total_pairs: FULL_CATALOGUE.length,
    median_window_years: medianWindow,
    longest_pair: longest,
    ranking_top_30: sorted.slice(0, 30),
    featured_pair: FEATURED_PAIR,
    recently_surfaced: RECENTLY_SURFACED,
  };
  return _cache;
}

export function getFullCatalogue(): PairRow[] {
  return [...FULL_CATALOGUE].sort((a, b) => b.pair_strength - a.pair_strength);
}

/**
 * Returns flag emoji for a country name. Thin wrapper over country-flags.ts
 * so components can import from the data layer rather than spreading the
 * dependency.
 */
export function pairFlagFor(name: string): string {
  return flagFor(name);
}

/** Generate a URL-safe slug from a pair_id for /patterns/{slug} routes */
export function pairSlug(pairId: string): string {
  return pairId;
}
