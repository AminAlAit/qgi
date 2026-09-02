/**
 * nearest-analog-data — current-country analog data for /analogues.
 *
 * V4.1 wire-up (2026-05-30 — full pipeline wire):
 *   - All 216-country entries come exclusively from loadAnalogs() (fleet-run-1
 *     current-state-analogs.json). No hand-authored seed overrides.
 *   - Pipeline emits match_score on 0–1 (cosine similarity). buildAllEntries()
 *     multiplies by 100 so AnalogCard thresholds (STRONG≥85, MODERATE≥70) work.
 *   - what_happened_next: null → rendered as "In training set." (honest gap).
 *   - indicator_trajectory: null → sparkline rendered as "Not yet curated"
 *     placeholder (no fake data).
 *   - secondary_recipe_ids: [] → "ALSO RESEMBLES" section simply absent.
 *
 * Implements Capability #12 (Nearest historical analog): SHAP-weighted cosine
 * similarity between a country's recent indicator trajectory and the pre-event
 * trajectories of all historical positives in the recipe's training set.
 * Self-excluded. Carries the regional-clustering caveat.
 *
 * HONESTY REGIME
 * - These are similarity matches, NOT forward predictions.
 * - Match scores < 70 are flagged as "weak analog" per ledger Feature 12.
 * - Regional-clustering caveat applies.
 */
import {
  loadAnalogs,
  loadAllScores,
  FLEET_RUN_1_RECIPE_IDS,
} from "@/lib/te-data-contract/load";
import type { NearestAnalogEntry } from "@/lib/te-data-contract/scores";
import { whnBlurb } from "@/lib/curation/what-happened-next";

/**
 * ISO 3166-1 alpha-2 → alpha-3 lookup for the 216-country TE fleet-run-1
 * analog corpus (2026-05-30). All entries have iso=null, iso2=<2-letter>.
 * Needed because getCurrentCountry() looks up by 3-letter code (matching URL
 * routing, e.g. /analogues?iso=SDN), but the bake only carries iso2.
 * This is the canonical standard mapping — no fallback truncation needed.
 */
const ISO2_TO_ISO3: Readonly<Record<string, string>> = {
  ad: "AND",
  ae: "ARE",
  af: "AFG",
  ag: "ATG",
  al: "ALB",
  am: "ARM",
  ao: "AGO",
  ar: "ARG",
  as: "ASM",
  at: "AUT",
  au: "AUS",
  aw: "ABW",
  az: "AZE",
  ba: "BIH",
  bb: "BRB",
  bd: "BGD",
  be: "BEL",
  bf: "BFA",
  bg: "BGR",
  bh: "BHR",
  bi: "BDI",
  bj: "BEN",
  bm: "BMU",
  bn: "BRN",
  bo: "BOL",
  br: "BRA",
  bs: "BHS",
  bt: "BTN",
  bw: "BWA",
  by: "BLR",
  bz: "BLZ",
  ca: "CAN",
  cd: "COD",
  cf: "CAF",
  cg: "COG",
  ch: "CHE",
  ci: "CIV",
  cl: "CHL",
  cm: "CMR",
  cn: "CHN",
  co: "COL",
  cr: "CRI",
  cu: "CUB",
  cv: "CPV",
  cw: "CUW",
  cy: "CYP",
  cz: "CZE",
  de: "DEU",
  dj: "DJI",
  dk: "DNK",
  dm: "DMA",
  do: "DOM",
  dz: "DZA",
  ec: "ECU",
  ee: "EST",
  eg: "EGY",
  er: "ERI",
  es: "ESP",
  et: "ETH",
  fi: "FIN",
  fj: "FJI",
  fm: "FSM",
  fo: "FRO",
  fr: "FRA",
  ga: "GAB",
  gb: "GBR",
  gd: "GRD",
  ge: "GEO",
  gh: "GHA",
  gi: "GIB",
  gl: "GRL",
  gm: "GMB",
  gn: "GIN",
  gq: "GNQ",
  gr: "GRC",
  gt: "GTM",
  gu: "GUM",
  gw: "GNB",
  gy: "GUY",
  hk: "HKG",
  hn: "HND",
  hr: "HRV",
  ht: "HTI",
  hu: "HUN",
  id: "IDN",
  ie: "IRL",
  il: "ISR",
  im: "IMN",
  in: "IND",
  iq: "IRQ",
  ir: "IRN",
  is: "ISL",
  it: "ITA",
  jm: "JAM",
  jo: "JOR",
  jp: "JPN",
  ke: "KEN",
  kg: "KGZ",
  kh: "KHM",
  ki: "KIR",
  km: "COM",
  kn: "KNA",
  kp: "PRK",
  kr: "KOR",
  kw: "KWT",
  ky: "CYM",
  kz: "KAZ",
  la: "LAO",
  lb: "LBN",
  lc: "LCA",
  li: "LIE",
  lk: "LKA",
  lr: "LBR",
  ls: "LSO",
  lt: "LTU",
  lu: "LUX",
  lv: "LVA",
  ly: "LBY",
  ma: "MAR",
  mc: "MCO",
  md: "MDA",
  me: "MNE",
  mf: "MAF",
  mg: "MDG",
  mh: "MHL",
  mk: "MKD",
  ml: "MLI",
  mm: "MMR",
  mn: "MNG",
  mo: "MAC",
  mp: "MNP",
  mr: "MRT",
  mt: "MLT",
  mu: "MUS",
  mv: "MDV",
  mw: "MWI",
  mx: "MEX",
  my: "MYS",
  mz: "MOZ",
  na: "NAM",
  nc: "NCL",
  ne: "NER",
  ng: "NGA",
  ni: "NIC",
  nl: "NLD",
  no: "NOR",
  np: "NPL",
  nr: "NRU",
  nz: "NZL",
  om: "OMN",
  pa: "PAN",
  pe: "PER",
  pf: "PYF",
  pg: "PNG",
  ph: "PHL",
  pk: "PAK",
  pl: "POL",
  pr: "PRI",
  ps: "PSE",
  pt: "PRT",
  pw: "PLW",
  py: "PRY",
  qa: "QAT",
  ro: "ROU",
  rs: "SRB",
  ru: "RUS",
  rw: "RWA",
  sa: "SAU",
  sb: "SLB",
  sc: "SYC",
  sd: "SDN",
  se: "SWE",
  sg: "SGP",
  si: "SVN",
  sk: "SVK",
  sl: "SLE",
  sm: "SMR",
  sn: "SEN",
  so: "SOM",
  sr: "SUR",
  ss: "SSD",
  st: "STP",
  sv: "SLV",
  sx: "SXM",
  sy: "SYR",
  sz: "SWZ",
  tc: "TCA",
  td: "TCD",
  tg: "TGO",
  th: "THA",
  tj: "TJK",
  tl: "TLS",
  tm: "TKM",
  tn: "TUN",
  to: "TON",
  tr: "TUR",
  tt: "TTO",
  tv: "TUV",
  tw: "TWN",
  tz: "TZA",
  ua: "UKR",
  ug: "UGA",
  us: "USA",
  uy: "URY",
  uz: "UZB",
  vc: "VCT",
  ve: "VEN",
  vg: "VGB",
  vi: "VIR",
  vn: "VNM",
  vu: "VUT",
  ws: "WSM",
  ye: "YEM",
  za: "ZAF",
  zm: "ZMB",
  zw: "ZWE",
};

export interface HistoricalAnalog {
  country: string;
  country_iso2: string | null; // ISO-2 (lowercase) from the bake; keys the analogue detail page
  year: number;
  match_score: number; // 0..100, cosine-similarity scaled
  primary_recipe_id: string; // recipe whose canonical shape drove the match
  secondary_recipe_ids: string[]; // other recipes that contributed
  indicator_trajectory: number[]; // 12 quarters pre-event, 0..100
  what_happened_next: string; // HISTORICAL FACT — what happened to the analog country after its event
  weak_analog?: boolean; // true if match_score < 70
}

export interface RecipeContribution {
  recipe_id: string;
  recipe_label: string;
  l1_color: string;
  contribution_pct: number; // 0..100
  // "in_progress" is the local-union name for the pipeline's "in_play"
  // value; statusLabel renders it as "In play".
  status: "graduated" | "walked_no_graduation" | "queued" | "live_legacy" | "in_progress";
}

export interface CurrentCountryEntry {
  iso: string;
  iso2: string; // ISO-2 (lowercase) — the subject half of the analogue detail key
  name: string;
  region: string;
  indicator_trajectory: number[]; // 12 quarters of "today" — drives the sparkline
  analogs: HistoricalAnalog[]; // top-3 nearest
  contributions: RecipeContribution[]; // which recipes contributed, ranked
}

// ─── Pipeline analog builder ──────────────────────────────────────────────────
// All 216-country entries come exclusively from loadAnalogs() (fleet-run-1
// current-state-analogs.json). No hand-authored seeds.
//
// Score-scale: the pipeline emits match_score on 0–1 (cosine similarity).
// AnalogCard thresholds (STRONG ≥ 85, MODERATE ≥ 70, WEAK < 70) expect 0–100.
// We multiply by 100 here; weak_analog is re-derived from the scaled score.
//
// Round-2 enrichment: scores files carry nearest_analogs[] with
// indicator_trajectory_12q and secondary_recipe_ids per subject-country ×
// recipe. We build a lookup keyed by
//   `${subject_name.lower}|${analog_country.lower}|${year}`
// across all 44 recipes and join it into the analogs array.

/** Map z-score trajectory from ±3 to 0–100 display scale. */
function zTrajToDisplay(zArr: number[]): number[] {
  return zArr.map((v) => Math.max(0, Math.min(100, ((v + 3) / 6) * 100)));
}

type ScoresAnalogKey = `${string}|${string}|${number}`;
type ScoresAnalogLookup = Map<ScoresAnalogKey, NearestAnalogEntry>;

let _scoresAnalogLookup: ScoresAnalogLookup | null = null;

/**
 * Build the round-2 enrichment lookup from all 44 scores files.
 * Key: `${subject_name.lower}|${analog_country.lower}|${year}`.
 * First match wins (recipes processed in FLEET_RUN_1_RECIPE_IDS order).
 * Only populates `indicator_trajectory_12q` and `secondary_recipe_ids`.
 */
function buildScoresAnalogLookup(): ScoresAnalogLookup {
  const out: ScoresAnalogLookup = new Map();
  try {
    const allScores = loadAllScores();
    for (const recipeId of FLEET_RUN_1_RECIPE_IDS) {
      const sf = allScores[recipeId];
      if (!sf) continue;
      for (const entry of sf.scores) {
        if (!entry.nearest_analogs || entry.nearest_analogs.length === 0) continue;
        const subjectKey = entry.name.toLowerCase();
        for (const a of entry.nearest_analogs) {
          if (!a.country || !a.year) continue;
          const key: ScoresAnalogKey = `${subjectKey}|${a.country.toLowerCase()}|${a.year}`;
          if (!out.has(key)) {
            out.set(key, a);
          }
        }
      }
    }
  } catch {
    // Scores unavailable — enrichment skipped.
  }
  return out;
}

let _allEntriesCache: CurrentCountryEntry[] | null = null;

function buildAllEntries(): CurrentCountryEntry[] {
  const base: CurrentCountryEntry[] = [];
  if (!_scoresAnalogLookup) _scoresAnalogLookup = buildScoresAnalogLookup();
  const scoresLookup = _scoresAnalogLookup;

  try {
    const data = loadAnalogs();
    for (const te of data.entries) {
      if (!te.name) continue;
      // iso: fleet-run-1 entries have iso=null + iso2=<2-letter>.
      // Use ISO2_TO_ISO3 for the canonical 3-letter code. Territory codes
      // not in the map fall back to name truncation and will be unreachable
      // via URL routing — harmless.
      const iso3 =
        te.iso ??
        (te.iso2 ? ISO2_TO_ISO3[te.iso2] : undefined) ??
        te.name.slice(0, 3).toUpperCase();
      if (!te.analogs || te.analogs.length === 0) continue;

      // Build HistoricalAnalog[] — multiply match_score × 100 (0–1 → 0–100).
      const subjectKey = te.name.toLowerCase();
      const analogs: HistoricalAnalog[] = te.analogs
        .filter((a) => a.country && a.year && a.match_score != null)
        .slice(0, 3)
        .map((a) => {
          const scaledScore = (a.match_score ?? 0) * 100;

          // Round-2: look up enrichment from the scores files.
          const enrichKey: ScoresAnalogKey = `${subjectKey}|${(a.country ?? "").toLowerCase()}|${a.year ?? 0}`;
          const enriched = scoresLookup.get(enrichKey);

          const secondaryRecipeIds: string[] = enriched?.secondary_recipe_ids ?? [];
          const indicatorTrajectory: number[] =
            enriched?.indicator_trajectory_12q &&
            enriched.indicator_trajectory_12q.length > 0
              ? zTrajToDisplay(enriched.indicator_trajectory_12q)
              : [];
          // Round-2: what_happened_next is still null from the bake.
          // Use enriched value if non-null; fall back to honest placeholder.
          const whatHappenedNext: string =
            whnBlurb(a.country_iso2, a.country, a.year) ??
            enriched?.what_happened_next ??
            a.what_happened_next ??
            "In training set.";

          return {
            country: a.country ?? "",
            country_iso2: a.country_iso2 ? a.country_iso2.toLowerCase() : null,
            year: a.year ?? 0,
            match_score: scaledScore,
            primary_recipe_id: a.primary_recipe_id ?? "",
            secondary_recipe_ids: secondaryRecipeIds,
            indicator_trajectory: indicatorTrajectory,
            what_happened_next: whatHappenedNext,
            weak_analog: scaledScore < 70,
          };
        });
      if (analogs.length === 0) continue;

      // Build RecipeContribution[].
      const contributions: RecipeContribution[] = (te.contributions ?? [])
        .filter((c) => c.recipe_id)
        .map((c) => ({
          recipe_id: c.recipe_id ?? "",
          recipe_label: c.recipe_label ?? c.recipe_id ?? "",
          l1_color: c.l1_color ?? "#7A8FA0",
          contribution_pct: c.contribution_pct ?? 0,
          // Pipeline emits status strings like "in_play" (V4.1 audience-
          // facing label) which maps to the local union value "in_progress"
          // (statusLabel renders both as "In play"). Anything else falls
          // back to "queued" → "Coming soon". 2026-05-30 bug fix: prior
          // version coerced "in_play" → "queued" so every contribution
          // chip on the analog page displayed "Coming soon".
          status: ((): RecipeContribution["status"] => {
            const raw = c.status ?? "";
            if (raw === "in_play") return "in_progress";
            if (
              raw === "graduated" ||
              raw === "walked_no_graduation" ||
              raw === "queued" ||
              raw === "live_legacy" ||
              raw === "in_progress"
            ) {
              return raw as RecipeContribution["status"];
            }
            return "queued";
          })(),
        }));

      base.push({
        iso: iso3,
        iso2: (te.iso2 ?? "").toLowerCase(),
        name: te.name,
        region: te.region ?? "Unknown",
        // Pipeline does not emit per-country indicator_trajectory — honest empty array.
        indicator_trajectory: Array.isArray(te.indicator_trajectory)
          ? (te.indicator_trajectory as number[])
          : [],
        analogs,
        contributions,
      });
    }
  } catch {
    // loadAnalogs unavailable — return empty; page will show "no data" state.
  }

  return base;
}

export function getCurrentCountries(): CurrentCountryEntry[] {
  if (!_allEntriesCache) _allEntriesCache = buildAllEntries();
  return _allEntriesCache;
}

export function getCurrentCountry(iso: string): CurrentCountryEntry | undefined {
  return getCurrentCountries().find((e) => e.iso === iso.toUpperCase());
}

export function defaultCurrentCountry(): CurrentCountryEntry {
  // Default to Egypt — the spec's example.
  return getCurrentCountries()[0];
}
