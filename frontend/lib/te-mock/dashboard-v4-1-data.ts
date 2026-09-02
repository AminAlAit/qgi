/**
 * Data layer for /dashboard — V4.1 confidence-first rebuild.
 *
 * Replaces the original V4.1 hero/highlights/surfaces/activity composition
 * with a showroom-style stack:
 *
 *   - HERO_TILES_V41          5 confidence-building catalog metrics
 *                             (recipes in catalog, countries scored, indicators
 *                             tracked, country pairs surfaced, vintages logged)
 *   - INSIGHT_PLOTS           4 audience-facing summary plots
 *                             (coverage map family distribution, indicator-corpus
 *                             scale, top country pairs teaser, analog spotlight)
 *   - WORLD_ACTIVITY_ROWS     audience-facing "what's moving in the world"
 *                             rows aggregated from country-index + scores
 *                             + analogs. Replaces the R&D walk feed.
 *
 * The original walk_fired / vacate / methodology_amendment events ARE still
 * loadable via loadActivityFeed() but they no longer surface on the dashboard
 * — they belong on /recipe-tracker (internal) and on /methodology (escape valve).
 *
 * NOT production data. Local mockup only.
 */

import {
  ScrollText,
  Globe,
  Activity,
  Layers,
  CalendarClock,
  TrendingUp,
  ArrowUpRight,
  Crosshair,
  Sparkles,
} from "lucide-react";

import { getAllRecipes, vintageStamp, type TrackerRecipe } from "@/lib/te-mock/recipes";
import {
  loadCountryIndex,
  loadAllScores,
  loadAnalogs,
  loadActivityFeed,
  loadRunIndex,
  loadIndicatorCatalogSize,
  loadIndicatorCorpusBreakdown,
} from "@/lib/te-data-contract/load";
import type { CountryIndex } from "@/lib/te-data-contract/country-index";
import { iso2For } from "@/lib/te-mock/country-flags";
import { cleanProseCopy } from "@/lib/clean-text";
import { L1_FAMILIES, familyColor, familyLabel } from "@/lib/te-mock/l1-families";
import type { HeroTile } from "@/components/dashboard-v4-1/DashboardHero";

// ───────────────────────────────────────────────────────────────────────────────
// Hero counts — catalog-size metrics, never "0".
// ───────────────────────────────────────────────────────────────────────────────

export interface HeroCounts41 {
  countries_scored: number;
  recipes_total: number;
  indicators_tracked: number;
  pairs_surfaced: number;
  vintages_logged: number;
  vintage: string;
}

/**
 * Indicator corpus size: read directly from MANIFEST.indicator_catalog_size.
 * Round-2 (2026-05-30): field ships with value 63 (V-Dem×33 + World Bank×29,
 * no FAO in this fleet run). Falls back to 63 on load error.
 */
function computeIndicatorsTracked(): number {
  try {
    return loadIndicatorCatalogSize();
  } catch {
    return 63;
  }
}

/**
 * Country pairs surfaced: number of distinct ordered analog matches across
 * the full /analogs corpus. Each row in current-state-analogs contributes
 * up to 3 nearest analogs → roughly 3× country count when fully baked.
 */
function computePairsSurfaced(): number {
  try {
    const analogs = loadAnalogs();
    return analogs.entries.reduce((acc, e) => acc + (e.analogs?.length ?? 0), 0);
  } catch {
    return 0;
  }
}

/**
 * Vintages logged: read from MANIFEST.run_index.
 * Round-2 (2026-05-30): field ships with value 1 (first fleet run).
 * Increments with each quarterly run. Falls back to 1 on load error.
 */
function computeVintagesLogged(): number {
  try {
    return loadRunIndex();
  } catch {
    return 1;
  }
}

export function buildHeroCountsV41(recipes: TrackerRecipe[]): HeroCounts41 {
  let countriesScored = 214;
  try {
    countriesScored = loadCountryIndex().n_countries_scored;
  } catch {
    /* fall back to roster constant */
  }
  return {
    countries_scored: countriesScored,
    recipes_total: recipes.length,
    indicators_tracked: computeIndicatorsTracked(),
    pairs_surfaced: computePairsSurfaced(),
    vintages_logged: computeVintagesLogged(),
    vintage: vintageStamp(),
  };
}

/**
 * Hero tiles — V4.1 confidence-first rebuild (founder review 2026-05-29).
 *
 * Slot decisions:
 * 1. Recipes in the catalog        (catalog size — never 0, big tile)
 * 2. Countries scored               (coverage — global signal)
 * 3. Signals tracked                (indicator corpus — depth signal)
 * 4. Country pairs surfaced         (analog network — comparison signal)
 * 5. Vintages logged                (cadence — recency signal)
 *
 * REMOVED from prior V4.1:
 *  - "Validated recipes 0" (founder #2 — never surface 0 in a hero metric)
 *  - "Tested, did not hold up" (banned vocab; R&D internal)
 *  - "Early method, under review" (banned vocab; R&D internal)
 *  - "In flight" (banned vocab; R&D internal)
 *  - "Tracker vintage" (vintage owned by the page-level chip per §2)
 */
export const HERO_TILES_V41 = (c: HeroCounts41): HeroTile[] => [
  {
    big: true,
    value: String(c.recipes_total),
    label: "Trends in the catalog",
    sublabel: "Country-risk event shapes drawn from the historical record",
    Icon: ScrollText,
    color: "#7B5EE6",
  },
  {
    value: String(c.countries_scored),
    label: "Countries scored",
    sublabel: "Every country in the global roster",
    Icon: Globe,
    color: "#38bdf8",
  },
  {
    value: String(c.indicators_tracked),
    label: "Signals tracked",
    sublabel: "World Bank, V-Dem, FAO inputs",
    Icon: Activity,
    color: "#3FBF8F",
  },
  {
    value: String(c.pairs_surfaced),
    label: "Country pairs surfaced",
    sublabel: "Historical resemblances across the corpus",
    Icon: Layers,
    color: "#E68F29",
  },
  {
    value: String(c.vintages_logged),
    label: "Vintages logged",
    sublabel: "Refreshed quarterly with every run",
    Icon: CalendarClock,
    color: "#5B7E99",
  },
];

// Convenience: pre-built tiles from the live recipe list.
export function getHeroTilesV41(): HeroTile[] {
  const recipes = getAllRecipes();
  return HERO_TILES_V41(buildHeroCountsV41(recipes));
}

// ───────────────────────────────────────────────────────────────────────────────
// Insight plots — 4 summary visuals that answer "what is QGI?" in 30 seconds.
// ───────────────────────────────────────────────────────────────────────────────

export interface FamilyDistribSlice {
  family_id: string;
  family_label: string;
  color: string;
  count: number;
  pct: number;
}

/**
 * Family distribution: how the recipe catalog spreads across the 8 L1
 * threat families. This is a confidence-building "we cover the map"
 * signal — the journalist sees breadth, the buyer sees portfolio scope.
 */
export function buildFamilyDistribution(): FamilyDistribSlice[] {
  const recipes = getAllRecipes();
  const counts = new Map<string, number>();
  for (const r of recipes) {
    counts.set(r.l1_id, (counts.get(r.l1_id) ?? 0) + 1);
  }
  const total = recipes.length;
  const slices: FamilyDistribSlice[] = [];
  // Iterate in canonical A-H order so the donut renders consistently.
  for (const id of Object.keys(L1_FAMILIES)) {
    const count = counts.get(id) ?? 0;
    if (count === 0) continue;
    slices.push({
      family_id: id,
      family_label: familyLabel(id),
      color: familyColor(id),
      count,
      pct: total > 0 ? (count / total) * 100 : 0,
    });
  }
  // Sort by count desc for visual hierarchy (largest slice first).
  return slices.sort((a, b) => b.count - a.count);
}

export interface CoverageSummary {
  countries_scored: number;
  roster: number;
  pct: number;
  /** Top regions by score density (placeholder for the map render). */
  region_breakdown: Array<{ region: string; pct: number }>;
}

export function buildCoverageSummary(): CoverageSummary {
  let scored = 214;
  let roster = 248;
  let regionBreakdown: Array<{ region: string; pct: number }> = [];
  try {
    const idx = loadCountryIndex() as CountryIndex & {
      coverage_density_per_region?: Record<string, number>;
    };
    scored = idx.n_countries_scored;
    roster = idx.platform_roster_size;
    // Derive region breakdown from `coverage_density_per_region` (bucket-A
    // enrichment applied on every fleet run). Percentages are share-of-scored.
    const cdr = idx.coverage_density_per_region ?? {};
    const total = Object.values(cdr).reduce((a, b) => a + b, 0);
    regionBreakdown = Object.entries(cdr)
      // Drop the "Unknown" bucket — not meaningful for a coverage display.
      .filter(([region]) => region !== "Unknown" && region !== "null")
      .sort((a, b) => b[1] - a[1])
      .map(([region, count]) => ({
        region,
        pct: total > 0 ? (count / total) * 100 : 0,
      }));
  } catch {
    /* fall back to empty breakdown on load failure */
  }
  return {
    countries_scored: scored,
    roster,
    pct: roster > 0 ? (scored / roster) * 100 : 0,
    region_breakdown: regionBreakdown,
  };
}

export interface IndicatorCorpusStat {
  label: string;
  count: number;
  color: string;
}

/**
 * Indicator corpus stack: reads provider breakdown directly from
 * MANIFEST.indicator_corpus_breakdown.
 *
 * Round-2 (2026-05-30): breakdown = {"V-Dem": 33, "World Bank": 29}.
 * Falls back to the hardcoded round-2 totals if the manifest is unavailable.
 *
 * Provider → display color map mirrors the V4.1 brand palette.
 */
export function buildIndicatorCorpusStack(): IndicatorCorpusStat[] {
  const PROVIDER_COLORS: Record<string, string> = {
    "V-Dem": "#7B5EE6",
    "World Bank": "#38bdf8",
    FAO: "#E68F29",
  };
  const DEFAULT_COLOR = "#3FBF8F";
  try {
    const breakdown = loadIndicatorCorpusBreakdown();
    return Object.entries(breakdown)
      .sort((a, b) => b[1] - a[1])
      .map(([provider, count]) => ({
        label: provider,
        count,
        color: PROVIDER_COLORS[provider] ?? DEFAULT_COLOR,
      }));
  } catch {
    return [
      { label: "V-Dem", count: 33, color: "#7B5EE6" },
      { label: "World Bank", count: 29, color: "#38bdf8" },
    ];
  }
}

export interface CountryPairTeaser {
  country_a: string;
  country_a_iso2: string | null;
  country_b: string;
  country_b_year: number;
  country_b_iso2: string | null;
  recipe_id: string;
  recipe_label: string;
  match_pct: number;
}

/**
 * Country-pair similarity teaser: the strongest historical resemblance in
 * the corpus across all recipes. Drawn from `current-state-analogs` —
 * picks the highest-match pair where neither side is weak_analog.
 */
export function buildTopPairTeasers(n = 3): CountryPairTeaser[] {
  try {
    const analogs = loadAnalogs();
    const recipes = getAllRecipes();
    const activeIds = new Set(recipes.map((r) => r.recipe_id));
    const recipeLabel = (id: string) =>
      recipes.find((r) => r.recipe_id === id)?.label ?? id;
    const flat: CountryPairTeaser[] = [];
    for (const entry of analogs.entries) {
      for (const a of entry.analogs) {
        if (a.weak_analog) continue;
        // Skip deactivated recipes (natural_disaster, epidemic_and_pandemic).
        if (!activeIds.has(a.primary_recipe_id)) continue;
        flat.push({
          country_a: entry.name,
          country_a_iso2: iso2For(entry.name) ?? null,
          country_b: a.country,
          country_b_year: a.year,
          country_b_iso2: iso2For(a.country) ?? null,
          recipe_id: a.primary_recipe_id,
          recipe_label: recipeLabel(a.primary_recipe_id),
          match_pct: a.match_score * 100,
        });
      }
    }
    return flat.sort((a, b) => b.match_pct - a.match_pct).slice(0, n);
  } catch {
    return [];
  }
}

// ───────────────────────────────────────────────────────────────────────────────
// Closest matches now — the Briefing centerpiece.
// "How countries are following recipes", as a left-to-right row of rich cards.
// Real fleet data; the strong band (the 95%ers), not the saturated 100s; one
// per country for variety; each card opens the country×recipe match page.
// ───────────────────────────────────────────────────────────────────────────────

export interface ClosestMatch {
  country: string;
  iso2: string;
  recipe_id: string;
  recipe_label: string;
  l1_color: string;
  score: number;
  zone_label: string | null;
  /** 12-quarter composite z-trajectory for the card spark (may be empty). */
  composite: number[];
  eval_year: number;
}

/**
 * The strongest current country×recipe matches across the whole fleet, in the
 * "95%er" band — strong resemblance without the saturated 100s. Diversified to
 * one country per card and at most two cards per recipe so the row reads as a
 * spread of distinct stories, not the same country five times.
 */
export function buildClosestMatches(n = 8): ClosestMatch[] {
  try {
    const byId = new Map(getAllRecipes().map((r) => [r.recipe_id, r]));
    const all = loadAllScores();
    const band: ClosestMatch[] = [];
    for (const [rid, file] of Object.entries(all)) {
      const rec = byId.get(rid);
      if (!rec) continue;
      const fc = familyColor(rec.l1_id, rec.l1_color);
      for (const e of file.scores as Array<{
        name: string;
        iso2?: string | null;
        score: number;
        zone_label?: string;
        eval_year: number;
        indicator_trajectory_composite_12q?: number[];
      }>) {
        // The "95%er" band: skip the saturated top (>=98, which clusters at
        // 99 and reads as a wall) and the long tail. Strong, varied, not maxed.
        if (e.score >= 98 || e.score < 92) continue;
        const iso2 = (e.iso2 ?? iso2For(e.name) ?? "").toLowerCase();
        if (!/^[a-z]{2}$/.test(iso2)) continue;
        band.push({
          country: e.name,
          iso2,
          recipe_id: rid,
          recipe_label: rec.label,
          l1_color: fc,
          score: e.score,
          zone_label: e.zone_label ?? null,
          composite: e.indicator_trajectory_composite_12q ?? [],
          eval_year: e.eval_year,
        });
      }
    }
    if (band.length <= n) return band.sort((a, b) => b.score - a.score);
    // Sample n picks evenly across the WHOLE band (ascending) so the row shows
    // a genuine range of strengths (e.g. 97 down to 92), not each country's
    // peak (which clusters at the top). Distinct country per card, <=2 per
    // recipe. We search outward from each evenly-spaced index for the first
    // entry that satisfies the variety constraints.
    band.sort((a, b) => a.score - b.score);
    const N = band.length;
    const usedCountry = new Set<string>();
    const usedRecipe = new Map<string, number>();
    const picked: ClosestMatch[] = [];
    for (let i = 0; i < n; i++) {
      const target = Math.round((i * (N - 1)) / (n - 1));
      let chosen: ClosestMatch | null = null;
      for (let off = 0; off < N && !chosen; off++) {
        for (const cand of [target + off, target - off]) {
          if (cand < 0 || cand >= N) continue;
          const m = band[cand];
          if (usedCountry.has(m.country)) continue;
          if ((usedRecipe.get(m.recipe_id) ?? 0) >= 2) continue;
          chosen = m;
          break;
        }
      }
      if (chosen) {
        picked.push(chosen);
        usedCountry.add(chosen.country);
        usedRecipe.set(chosen.recipe_id, (usedRecipe.get(chosen.recipe_id) ?? 0) + 1);
      }
    }
    picked.sort((a, b) => b.score - a.score);
    return picked;
  } catch {
    return [];
  }
}

// ───────────────────────────────────────────────────────────────────────────────
// World-facing activity — replaces the R&D walk feed.
// ───────────────────────────────────────────────────────────────────────────────

export interface WorldActivityRow {
  date: string;
  kind:
    | "country_movement"
    | "recipe_top10_shift"
    | "pair_emerged"
    | "analog_spotlight"
    | "corpus_growth";
  title: string;
  detail: string;
  href: string;
  color: string;
  iconKey: "trending" | "crosshair" | "layers" | "sparkles" | "activity";
}

/**
 * Map an iconKey enum to a LucideIcon. Done in the consumer (page.tsx) so
 * this data module stays a pure data layer — no React imports.
 */
export const ICON_FOR_ACTIVITY_KEY = {
  trending: TrendingUp,
  crosshair: Crosshair,
  layers: ArrowUpRight,
  sparkles: Sparkles,
  activity: Activity,
} as const;

/**
 * Map a `fired_at` ISO string to a display date (YYYY-MM-DD).
 */
function firedAtToDate(firedAt: string): string {
  try {
    return firedAt.slice(0, 10);
  } catch {
    return firedAt;
  }
}

/**
 * Build world-facing activity rows from the baked program-feed.json.
 *
 * Source: `data/te-fleet-run-1/activity/program-feed.json` (46 events).
 * Consumes `loadActivityFeed()` from the data contract.
 *
 * Mapping:
 *   walk_fired              → recipe_top10_shift  (recipe run this vintage)
 *   vacate                  → corpus_growth       (catalog correction)
 *   methodology_amendment   → corpus_growth       (methodology update)
 *   <unknown kind>          → corpus_growth       (generic catalog event)
 *
 * Rows are sorted most-recent-first by `fired_at` (descending ISO string
 * sort is correct for the YYYY-MM-DDTHH:MM:SSZ format used in the feed).
 * The function returns ALL rows; the WorldActivity component collapses to 5
 * and expands on demand.
 */
export function buildWorldActivityRows(): WorldActivityRow[] {
  try {
    const feed = loadActivityFeed();
    // Drop activity events for deactivated recipes (natural_disaster,
    // epidemic_and_pandemic) so they don't surface on the Briefing.
    const activeIds = new Set(getAllRecipes().map((r) => r.recipe_id));
    const sorted = [...feed.events]
      .filter((evt) => {
        const rid = (evt as { recipe_id?: string }).recipe_id;
        return !rid || activeIds.has(rid);
      })
      .sort((a, b) => b.fired_at.localeCompare(a.fired_at));
    return sorted.map((evt): WorldActivityRow => {
      const date = firedAtToDate(evt.fired_at);
      if (evt.kind === "walk_fired") {
        const e = evt as {
          kind: "walk_fired";
          fired_at: string;
          recipe_id: string;
          recipe_label: string;
          tier: string;
          verdict: string;
          loco_auc: number;
          note: string;
        };
        const verdictLabel =
          e.verdict === "MARGINAL_PENDING_BETA_CALIBRATION"
            ? "directional, beta calibration pending"
            : "experimental, under review";
        return {
          date,
          kind: "recipe_top10_shift",
          title: `${e.recipe_label}: first release under the Trajectory Engine`,
          detail:
            `Walk completed ${date}. LOCO AUC ${e.loco_auc.toFixed(3)} · ` +
            `${verdictLabel}. ${cleanProseCopy(e.note)}`,
          href: `/trends/${e.recipe_id}`,
          color: "#7B5EE6",
          iconKey: "crosshair",
        };
      }
      if (evt.kind === "vacate") {
        const e = evt as {
          kind: "vacate";
          fired_at: string;
          recipe_id: string;
          recipe_label: string;
          prior_status: string;
          cause: string;
          note: string;
        };
        return {
          date,
          kind: "corpus_growth",
          title: `${e.recipe_label}: status correction applied`,
          detail: `${cleanProseCopy(e.cause)} ${cleanProseCopy(e.note)}`,
          href: `/trends/${e.recipe_id}`,
          color: "#E68F29",
          iconKey: "activity",
        };
      }
      if (evt.kind === "methodology_amendment") {
        const e = evt as {
          kind: "methodology_amendment";
          fired_at: string;
          title: string;
          detail: string;
        };
        return {
          date,
          kind: "corpus_growth",
          title: `Methodology update: ${e.title}`,
          detail: cleanProseCopy(e.detail),
          href: `/methodology`,
          color: "#5B7E99",
          iconKey: "activity",
        };
      }
      // Generic fallback for unknown future kinds
      return {
        date,
        kind: "corpus_growth",
        title: `Catalog event: ${evt.kind}`,
        detail: `Recorded ${date}.`,
        href: `/methodology`,
        color: "#5B7E99",
        iconKey: "activity",
      };
    });
  } catch {
    return [];
  }
}

// Legacy re-exports removed 2026-05-29 — `lib/te-mock/dashboard-v4-data.ts`
// was deleted with the V4.1 round-3 amendment. Grep confirmed no active
// callers of HIGHLIGHTS / SURFACE_CARDS / ACTIVITY_EVENTS outside this
// module, so the re-export shim is no longer load-bearing.
