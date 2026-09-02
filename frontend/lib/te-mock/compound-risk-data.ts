/**
 * compound-risk-data — /compound-risk view data.
 *
 * V4.1 wire-up (2026-05-29):
 *   - SEEDS (cascade-era hand-authored rows) remain for the main compound
 *     country list and all three case studies.
 *   - TE sample-10 countries are appended from loadCountryIndex():
 *     each country's top_recipes (already carrying l1_id/l1_label/l1_color
 *     from the pipeline) maps directly to CompoundLitRecipe. Countries
 *     appearing in both SEEDS and country-index use the SEEDS version.
 *
 * Compound score formula (Sard Ihsa consult 2026-05-29, ratified by
 *   Roshani/Kwame/Miriam/Tariq/Elif):
 *
 *   compound_score = sqrt(N / (N + 2)) * sqrt(mean(score_i^2))
 *
 * where N = number of lit recipes (score >= 50), score_i = recipe
 * discrimination rank in 0..100. Bounded in [0, 100]. The Hölder-mean
 * (α=2 / RMS) core rewards consistently high recipes without unbounded
 * stacking; the sqrt(N/(N+2)) prefactor is a Bayesian shrinkage toward
 * zero for thin coverage (one recipe at 100 ⇒ ~57.7; three at 80 ⇒ ~62;
 * eight at 80 ⇒ ~71). Pre-registered: see /methodology #compound-formula.
 *
 * Replaces the prior cumulative-unbounded sum(max(0, score - 50)) which
 * was not a probability, not a percentile, and grew without bound as the
 * recipe catalog expanded. Old field kept as `compound_score_legacy` for
 * methodology debugging and the `?` tooltip on the page.
 */
import recipeTracker from "@/data/recipe-tracker.json";
import { getAllRecipes, getRecipe, type TrackerRecipe } from "@/lib/te-mock/recipes";
import { loadCountryIndex, SAMPLE_10_RECIPE_IDS } from "@/lib/te-data-contract/load";
import { flagFromIso2, NAME_TO_ISO2 } from "@/lib/te-mock/country-iso2";
import { familyLabel } from "@/lib/te-mock/l1-families";

export interface CompoundLitRecipe {
  recipe_id: string;
  label: string;
  score: number;
  decile: number; // 8 - 10 surfaced on this page
  l1_id: string;
  l1_label: string;
  l1_color: string;
}

export interface CompoundCountry {
  country: string;
  iso: string;
  flag: string;
  region: string;
  /** Bounded RMS with coverage shrinkage in [0, 100]. Ihsa-ratified 2026-05-29. */
  compound_score: number;
  /** Legacy sum-of-margins kept for the methodology tooltip / debugging only. */
  compound_score_legacy: number;
  lit_recipes: CompoundLitRecipe[];
  lit_families: string[]; // unique L1 ids, in canonical A-H order
  vintage: string;
}

export interface CompoundCaseStudy {
  country: string;
  iso: string;
  flag: string;
  compound_score: number;
  compound_score_legacy: number;
  recipes: CompoundLitRecipe[];
  narrative: string;
  vintage: string;
}

export const COMPOUND_VINTAGE = (recipeTracker as { generated: string }).generated;

// Cheap O(1) lookup of recipe metadata.
// Round-3.8 (2026-05-30) — sourced from getAllRecipes() (the deduped
// catalog where TE walked rows override the cascade-era queued seeds)
// instead of the raw recipe-tracker.json. That fix stops the
// CompoundLeaderboard's RecipeChip from rendering "Coming soon" status
// labels on recipes the rest of the app already shows as in-play.
export const RECIPE_LOOKUP: Record<string, TrackerRecipe> = Object.fromEntries(
  getAllRecipes().map((r) => [r.recipe_id, r])
);

function lit(recipe_id: string, score: number, decile = 9): CompoundLitRecipe {
  const r = RECIPE_LOOKUP[recipe_id];
  if (!r) throw new Error(`compound-risk: unknown recipe_id ${recipe_id}`);
  return {
    recipe_id,
    label: r.label,
    score,
    decile,
    l1_id: r.l1_id,
    l1_label: r.l1_label,
    l1_color: r.l1_color,
  };
}

/**
 * Bounded RMS with coverage shrinkage (Ihsa 2026-05-29).
 *
 *   compound_score = sqrt(N / (N + 2)) * sqrt(mean(score_i^2))
 *
 * "Lit" is defined as score >= 50 (the orthogonal anchor); a country with
 * recipes below 50 contributes 0 N to the shrinkage and 0 to the RMS.
 * Returns a value in [0, 100].
 */
function compound(recipes: CompoundLitRecipe[]): number {
  const lit = recipes.filter((r) => r.score >= 50);
  const N = lit.length;
  if (N === 0) return 0;
  const meanSq = lit.reduce((s, r) => s + r.score * r.score, 0) / N;
  const rms = Math.sqrt(meanSq);
  const shrink = Math.sqrt(N / (N + 2));
  return Math.min(100, rms * shrink);
}

/** Legacy unbounded sum-of-margins. Kept for the `?` tooltip explaining what changed. */
function compoundLegacy(recipes: CompoundLitRecipe[]): number {
  return recipes.reduce((s, r) => s + Math.max(0, r.score - 50), 0);
}

function families(recipes: CompoundLitRecipe[]): string[] {
  return Array.from(new Set(recipes.map((r) => r.l1_id))).sort();
}

/**
 * Round-3.8 (2026-05-30) — Compound Risk cleanup. Filter lit-recipe lists
 * down to recipes that are actually IN PLAY in the catalog (status:
 * graduated / walked_no_graduation / in_progress / live_legacy). Drops
 * queued + hold recipes whose hand-curated seed scores were leaking
 * through and showing "Coming soon" tooltips on the Compound Risk page.
 *
 * Founder verdict (2026-05-30): "how can you be using recipes you don't
 * have baked data from? wtf.. can you do a thorough cleanup please."
 *
 * After this filter, Compound Risk aggregates ONLY recipes the rest of
 * the catalog also considers in-play. A country that loses all of its
 * lit recipes after the filter falls off the page entirely.
 */
function inPlayOnly(recipes: CompoundLitRecipe[]): CompoundLitRecipe[] {
  return recipes.filter((r) => {
    const tr = getRecipe(r.recipe_id);
    if (!tr) return false;
    return tr.status !== "queued";
  });
}

interface Seed {
  country: string;
  iso: string;
  flag: string;
  region: string;
  recipes: CompoundLitRecipe[];
}

const SEEDS: Seed[] = [
  {
    country: "Iran",
    iso: "IRN",
    flag: "🇮🇷",
    region: "Middle East",
    recipes: [
      lit("foreign_intervention", 98.1, 10),
      lit("political_repression", 81.4, 10),
      lit("mass_protest", 72.4, 9),
      lit("sanctions_and_arms_embargo", 78.9, 10),
      lit("currency_crisis", 64.2, 9),
    ],
  },
  {
    country: "Pakistan",
    iso: "PAK",
    flag: "🇵🇰",
    region: "South Asia",
    recipes: [
      lit("terrorist_attack", 71.5, 10),
      lit("civil_war_and_insurgency", 66.8, 9),
      lit("economic_recession", 58.2, 8),
      lit("political_violence", 64.5, 9),
    ],
  },
  {
    country: "Argentina",
    iso: "ARG",
    flag: "🇦🇷",
    region: "Latin America",
    recipes: [
      lit("currency_crisis", 82.4, 10),
      lit("economic_recession", 72.1, 10),
      lit("mass_protest", 61.7, 9),
      lit("fiscal_policy_change", 68.3, 9),
    ],
  },
  {
    country: "Myanmar",
    iso: "MMR",
    flag: "🇲🇲",
    region: "Southeast Asia",
    recipes: [
      lit("civil_war_and_insurgency", 77.8, 10),
      lit("foreign_intervention", 71.2, 9),
      lit("political_repression", 74.5, 10),
      lit("ethnic_and_communal_conflict", 68.7, 9),
    ],
  },
  {
    country: "Sudan",
    iso: "SDN",
    flag: "🇸🇩",
    region: "East Africa",
    recipes: [
      lit("civil_war_and_insurgency", 71.2, 10),
      lit("humanitarian_crisis", 78.4, 10),
      lit("foreign_intervention", 65.8, 9),
      lit("drought_and_famine", 62.1, 9),
      lit("mass_protest", 58.7, 8),
    ],
  },
  {
    country: "Lebanon",
    iso: "LBN",
    flag: "🇱🇧",
    region: "Middle East",
    recipes: [
      lit("economic_recession", 65.4, 9),
      lit("currency_crisis", 71.8, 10),
      lit("mass_protest", 61.2, 9),
      lit("banking_and_financial_crisis", 68.5, 9),
    ],
  },
  {
    country: "Belarus",
    iso: "BLR",
    flag: "🇧🇾",
    region: "Eastern Europe",
    recipes: [
      lit("political_repression", 78.2, 10),
      lit("foreign_intervention", 94.2, 10),
      lit("sanctions_and_arms_embargo", 73.6, 10),
      lit("multilateral_agreement", 58.0, 8),
    ],
  },
  {
    country: "Turkmenistan",
    iso: "TKM",
    flag: "🇹🇲",
    region: "Central Asia",
    recipes: [
      lit("foreign_intervention", 97.0, 10),
      lit("political_repression", 68.7, 9),
      lit("executive_power_consolidation", 64.3, 9),
    ],
  },
  {
    country: "Tajikistan",
    iso: "TJK",
    flag: "🇹🇯",
    region: "Central Asia",
    recipes: [
      lit("foreign_intervention", 88.5, 10),
      lit("political_repression", 61.8, 9),
      lit("ethnic_and_communal_conflict", 56.4, 8),
    ],
  },
  {
    country: "Yemen",
    iso: "YEM",
    flag: "🇾🇪",
    region: "Middle East",
    recipes: [
      lit("civil_war_and_insurgency", 74.5, 10),
      lit("humanitarian_crisis", 81.2, 10),
      lit("foreign_intervention", 79.8, 10),
      lit("drought_and_famine", 66.4, 9),
      lit("economic_recession", 58.9, 8),
    ],
  },
  {
    country: "Mali",
    iso: "MLI",
    flag: "🇲🇱",
    region: "Sahel",
    recipes: [
      lit("civil_war_and_insurgency", 64.5, 9),
      lit("terrorist_attack", 64.2, 9),
      lit("foreign_intervention", 68.7, 9),
      lit("military_coup", 71.2, 10),
    ],
  },
  {
    country: "Burkina Faso",
    iso: "BFA",
    flag: "🇧🇫",
    region: "Sahel",
    recipes: [
      lit("terrorist_attack", 61.0, 9),
      lit("military_coup", 64.8, 9),
      lit("foreign_intervention", 58.4, 8),
      lit("drought_and_famine", 56.7, 8),
    ],
  },
  {
    country: "Equatorial Guinea",
    iso: "GNQ",
    flag: "🇬🇶",
    region: "West Africa",
    recipes: [
      lit("foreign_intervention", 96.9, 10),
      lit("political_repression", 65.2, 9),
      lit("political_corruption", 71.4, 10),
    ],
  },
  {
    country: "Nicaragua",
    iso: "NIC",
    flag: "🇳🇮",
    region: "Latin America",
    recipes: [
      lit("political_repression", 71.4, 10),
      lit("mass_protest", 54.8, 8),
      lit("economic_recession", 51.3, 8),
    ],
  },
  {
    country: "Sri Lanka",
    iso: "LKA",
    flag: "🇱🇰",
    region: "South Asia",
    recipes: [
      lit("economic_recession", 61.8, 9),
      lit("currency_crisis", 64.7, 9),
      lit("mass_protest", 57.2, 8),
      lit("banking_and_financial_crisis", 59.4, 8),
    ],
  },
  {
    country: "Turkey",
    iso: "TUR",
    flag: "🇹🇷",
    region: "Middle East",
    recipes: [
      lit("economic_recession", 68.5, 9),
      lit("currency_crisis", 71.2, 10),
      lit("political_repression", 58.4, 8),
    ],
  },
  {
    country: "Nigeria",
    iso: "NGA",
    flag: "🇳🇬",
    region: "West Africa",
    recipes: [
      lit("terrorist_attack", 58.5, 8),
      lit("ethnic_and_communal_conflict", 62.1, 9),
      lit("political_violence", 56.3, 8),
    ],
  },
  {
    country: "Venezuela",
    iso: "VEN",
    flag: "🇻🇪",
    region: "Latin America",
    recipes: [
      lit("currency_crisis", 78.4, 10),
      lit("economic_recession", 72.1, 10),
      lit("political_repression", 68.3, 9),
      lit("mass_protest", 54.5, 8),
      lit("sanctions_and_arms_embargo", 64.8, 9),
    ],
  },
  {
    country: "DRC",
    iso: "COD",
    flag: "🇨🇩",
    region: "Central Africa",
    recipes: [
      lit("civil_war_and_insurgency", 68.4, 9),
      lit("ethnic_and_communal_conflict", 64.2, 9),
      lit("humanitarian_crisis", 71.5, 10),
      lit("resource_conflict", 58.7, 8),
    ],
  },
  {
    country: "Egypt",
    iso: "EGY",
    flag: "🇪🇬",
    region: "North Africa",
    recipes: [
      lit("political_repression", 64.1, 9),
      lit("economic_recession", 56.3, 8),
      lit("water_crisis", 53.4, 8),
    ],
  },
  {
    country: "Ethiopia",
    iso: "ETH",
    flag: "🇪🇹",
    region: "East Africa",
    recipes: [
      lit("civil_war_and_insurgency", 61.2, 9),
      lit("ethnic_and_communal_conflict", 64.7, 9),
      lit("drought_and_famine", 58.9, 8),
    ],
  },
  {
    country: "Bolivia",
    iso: "BOL",
    flag: "🇧🇴",
    region: "Latin America",
    recipes: [lit("mass_protest", 54.2, 8), lit("constitutional_change", 52.4, 8)],
  },
];

// Filter every seed's recipe list through inPlayOnly so queued/hold
// recipes from the cascade-era catalog never leak onto the Compound
// Risk page. Countries that lose all lit recipes after the filter are
// dropped (their score would be 0; the page is about countries with
// MULTIPLE in-play matches).
const SEED_COUNTRIES: CompoundCountry[] = SEEDS.map((s) => {
  const recipes = inPlayOnly(s.recipes);
  return {
    country: s.country,
    iso: s.iso,
    flag: s.flag,
    region: s.region,
    compound_score: compound(recipes),
    compound_score_legacy: compoundLegacy(recipes),
    lit_recipes: recipes,
    lit_families: families(recipes),
    vintage: COMPOUND_VINTAGE,
  };
}).filter((c) => c.lit_recipes.length > 0);

// ─── TE country-index supplement ─────────────────────────────────────────────
// Append countries from country-index that have ≥1 TE recipe lit at score ≥50
// and are NOT already in SEEDS. L1 metadata comes from country-index's
// top_recipes array (pipeline-emitted l1_id/l1_label/l1_color).

function buildTECompoundCountries(): CompoundCountry[] {
  try {
    const ci = loadCountryIndex();
    const seedNames = new Set(SEEDS.map((s) => s.country.toLowerCase()));
    const out: CompoundCountry[] = [];
    for (const c of ci.countries) {
      if (seedNames.has(c.name.toLowerCase())) continue;
      if (!c.top_recipes || c.top_recipes.length === 0) continue;
      // Only TE sample-10 recipe entries, lit at ≥50.
      const teRecipes = c.top_recipes.filter(
        (r) =>
          SAMPLE_10_RECIPE_IDS.includes(r.recipe_id) && r.score != null && r.score >= 50
      );
      if (teRecipes.length === 0) continue;

      const lit: CompoundLitRecipe[] = teRecipes.map((r) => ({
        recipe_id: r.recipe_id,
        label: r.label ?? r.recipe_id,
        score: r.score ?? 0,
        decile: Math.round((r.score ?? 0) / 10),
        l1_id: r.l1_id ?? "",
        // #997: country-index l1_label was bake-corrupted (a wrong taxonomy's
        // words on the correct A-H letter); l1_id stays correct, so resolve the
        // canonical label from l1-families rather than trusting the baked string.
        l1_label: familyLabel(r.l1_id ?? "", r.l1_label),
        l1_color: r.l1_color ?? "#7A8FA0",
      }));

      const iso2 = NAME_TO_ISO2.get(c.name.toLowerCase()) ?? "";
      const flag = iso2 ? flagFromIso2(iso2) : "";
      // Pseudo-3-letter iso from iso2 (no real iso3 in v3 contract).
      const iso = iso2 ? iso2.toUpperCase() + "_" : c.name.slice(0, 3).toUpperCase();

      out.push({
        country: c.name,
        iso,
        flag,
        region: c.region ?? "Unknown",
        compound_score: compound(lit),
        compound_score_legacy: compoundLegacy(lit),
        lit_recipes: lit,
        lit_families: families(lit),
        vintage: ci.vintage ?? COMPOUND_VINTAGE,
      });
    }
    return out;
  } catch {
    return [];
  }
}

export const COMPOUND_COUNTRIES: CompoundCountry[] = [
  ...SEED_COUNTRIES,
  ...buildTECompoundCountries(),
];

export function countLitAtThreshold(
  countries: CompoundCountry[],
  threshold: number
): number {
  return countries.filter((c) => c.lit_recipes.length >= threshold).length;
}

// ── Case studies ─────────────────────────────────────────────────────────────
// 4-5 sentence analyst paragraphs. Vintage-stamped. MOCK-labeled.

const IRAN = COMPOUND_COUNTRIES.find((c) => c.iso === "IRN")!;
const SUDAN = COMPOUND_COUNTRIES.find((c) => c.iso === "SDN")!;
const ARGENTINA = COMPOUND_COUNTRIES.find((c) => c.iso === "ARG")!;

export const COMPOUND_CASE_STUDIES: CompoundCaseStudy[] = [
  {
    country: IRAN.country,
    iso: IRAN.iso,
    flag: IRAN.flag,
    compound_score: IRAN.compound_score,
    compound_score_legacy: IRAN.compound_score_legacy,
    recipes: IRAN.lit_recipes,
    vintage: IRAN.vintage,
    narrative:
      "Iran is the densest single-state compound case currently on the board, with high scores on five recipes " +
      "(Foreign Intervention, Political Repression, Sanctions and Arms Embargo, Mass Protest, and Currency Crisis), " +
      "spanning four threat families at once (Conflict & Violence, Governance & Rights, Economic Stress, Social Mobilization). " +
      "The structural read is that the same underlying signals — degraded regulatory quality, narrowing " +
      "civil-liberties space, and deteriorating fiscal-source diversity — sit behind the foreign-intervention trajectory " +
      "AND the protest-and-repression cycle. The compound score reflects shared substrate as much as independent crisis " +
      "paths. None of these recipes is yet deployed for real decisions, so this is best read as a positioning aggregate, " +
      "not a forecast of any single event firing, and certainly not of all five firing jointly.",
  },
  {
    country: SUDAN.country,
    iso: SUDAN.iso,
    flag: SUDAN.flag,
    compound_score: SUDAN.compound_score,
    compound_score_legacy: SUDAN.compound_score_legacy,
    recipes: SUDAN.lit_recipes,
    vintage: SUDAN.vintage,
    narrative:
      "Sudan registers across five recipes (Civil War and Insurgency, Humanitarian Crisis, Foreign Intervention, " +
      "Drought and Famine, Mass Protest), spanning three threat families (Conflict & Violence, Social Mobilization, " +
      "Humanitarian Crisis) with a meteorological drought-and-famine channel layered on top. Unlike the Iran case, " +
      "the Sudan stack reflects genuinely distinct structural pressures rather than a single bundle of correlated " +
      "signals; conflict-shape indicators (state-capacity collapse, ethnic-violence rates) sit alongside meteorological " +
      "and humanitarian-throughput signals that draw on a non-overlapping data substrate. This is the architecturally " +
      "cleanest compound case in the current snapshot, and the one most consistent with the original intuition of " +
      "the compound page: three independent lenses pointing at the same country.",
  },
  {
    country: ARGENTINA.country,
    iso: ARGENTINA.iso,
    flag: ARGENTINA.flag,
    compound_score: ARGENTINA.compound_score,
    compound_score_legacy: ARGENTINA.compound_score_legacy,
    recipes: ARGENTINA.lit_recipes,
    vintage: ARGENTINA.vintage,
    narrative:
      "Argentina shows the canonical economic-compound shape (Currency Crisis, Economic Recession, " +
      "Fiscal Policy Change, and Mass Protest), three Economic-Stress recipes plus a Social-Mobilization spillover. " +
      "The reading to be careful about here is that Currency Crisis and Economic Recession share substantial " +
      "underlying signals (inflation, GDP growth, fiscal-source diversity), so a tightly clustered compound score " +
      "is mathematically expected rather than independently informative; the Mass Protest reading is the one " +
      "independent confirmation that the economic stress is propagating into the social domain rather than being " +
      "absorbed at the policy layer. Until one of these recipes is deployed for real decisions, the Argentina case " +
      "is a worked example of why a single bounded score is more honest than a stacked sum.",
  },
];
