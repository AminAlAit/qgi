/**
 * country-recipe-match — data join for the
 * /trends/[slug]/countries/[iso] "how is this country following this recipe"
 * page, sourced from the REAL fleet-run-1 per-country scores.
 *
 * Source: loadScores(recipeId) -> data/te-fleet-run-1/scores/{id}.scores.json
 *
 * IMPORTANT: the te-data-contract `CountryScoreEntry` type declares the nested
 * indicator arrays with `code`/`name`, but the real fleet-run-1 JSON uses
 * `indicator_code`/`indicator_name`/`provider`. We cast to a local interface
 * (`FleetEntry`) that matches the real on-disk shape and read those fields.
 *
 * What fleet-run-1 gives us per (country x recipe) — all real, no synthesis:
 *   - score / rank / eval_year / zone / zone_label / cosine_similarity_S
 *   - per recipe indicator: 12-quarter z-trajectory + signal share % + sensitivity
 *   - indicator_trajectory_composite_12q: the country's overall signal path
 *   - momentum_scores_by_year: the score climbing/easing across recent years
 *   - nearest_analogs: the historical cases it most resembles, each carrying
 *     its OWN 12-quarter composite trajectory (so we can overlay paths)
 *
 * Fleet-run-1 cards do NOT carry trajectory_alignment (no canonical shape
 * band), so the "follow the shape" story is told by overlaying the country's
 * composite path against the analogues' real paths instead.
 *
 * Returns null for any recipe not in the scored fleet, or any country not
 * scored on it — the page then renders an honest "coming soon" state.
 */
import {
  loadScores,
  loadVintage,
  SAMPLE_10_RECIPE_IDS,
} from "@/lib/te-data-contract/load";
import { getIndicatorLabel } from "@/lib/indicator-labels";
import { iso2For } from "@/lib/te-mock/country-flags";
import { getRecipeCanonical } from "@/lib/te-mock/recipe-canonical-shape";
import { findAnalogueEvent, type AnalogueEvent } from "@/lib/te-mock/analogue-events";
import { whnBlurb } from "@/lib/curation/what-happened-next";

/* ── Local interfaces matching the REAL fleet-run-1 JSON field names ── */
interface FleetShap {
  indicator_code: string;
  indicator_name?: string | null;
  signal_share_pct: number;
  provider?: string | null;
}
interface FleetMovement {
  indicator_code: string;
  indicator_name?: string | null;
  provider?: string | null;
  trajectory_12q: number[];
  z_score_change: number;
}
interface FleetSensitivity {
  indicator: string;
  marginal_points_per_unit: number;
  headroom_points: number;
}
interface FleetAnalog {
  country: string;
  country_iso2?: string | null;
  year: number;
  match_score: number;
  weak_analog: boolean;
  what_happened_next?: string | null;
  indicator_trajectory_12q?: number[];
}
interface FleetEntry {
  iso2?: string | null;
  flag_emoji?: string | null;
  name: string;
  score: number;
  rank: number;
  eval_year: number;
  in_evidence_base: boolean;
  zone?: string;
  zone_label?: string;
  cosine_similarity_S?: number;
  shap_attribution: FleetShap[];
  indicator_movement: FleetMovement[];
  sensitivity_per_indicator?: FleetSensitivity[];
  indicator_trajectory_composite_12q?: number[];
  momentum_scores_by_year?: Record<string, number>;
  momentum_label?: string | null;
  nearest_analogs?: FleetAnalog[];
}

export interface MatchIndicator {
  code: string;
  name: string;
  provider: string;
  /** Signal share %, 0..100 (sums to ~100 across the recipe's set). */
  weightPct: number;
  /** This country's recent path on this signal (z-scored), 12 quarters. */
  trajectory: number[];
  /** Observed standardized change across the window. */
  zChange: number;
  /** "rising" | "falling" | "flat" — direction of recent movement. */
  direction: "rising" | "falling" | "flat";
  /** Recipe's canonical movement shape for this signal across its window
   *  (z-scored). null when no canonical-shape bake exists for this recipe. */
  canonicalMean: number[] | null;
  canonicalP25: number[] | null;
  canonicalP75: number[] | null;
}

export interface MatchAnalogue {
  country: string;
  iso2: string;
  year: number;
  /** match_score scaled to 0..100. */
  matchPct: number;
  weak: boolean;
  whatHappenedNext: string | null;
  /**
   * The real verified event that happened to this analogue country around
   * its analogue year, under this recipe — joined from data/verified-events.json
   * (the same corpus /methodology/events lists). null when no event of that
   * kind sits near that year.
   */
  event: AnalogueEvent | null;
  /** The analogue's own 12-quarter composite path (z-scored), if present. */
  path: number[] | null;
}

export interface CountryRecipeMatch {
  recipeId: string;
  countryName: string;
  iso2: string;
  /** Resemblance rank, 0..100. NOT a probability. */
  score: number;
  rank: number;
  nScored: number;
  evalYear: number;
  /** Years the 12-quarter window spans (12q = 3y). */
  windowYears: number;
  inEvidenceBase: boolean;
  /** Canonical window the recipe's shape spans (years). null when no shape. */
  canonicalWindowYears: number | null;
  zone: string | null;
  zoneLabel: string | null;
  /** Cosine similarity to the recipe's canonical profile, 0..1. */
  cosineSimilarity: number | null;
  /** The country's overall signal path (z-scored), 12 quarters. */
  composite: number[];
  /** Year -> score, recent years (e.g. 2023..2026). */
  momentumByYear: Array<{ year: string; score: number }>;
  momentumLabel: string | null;
  vintage: string;
  indicators: MatchIndicator[];
  analogues: MatchAnalogue[];
}

/** Normalize a backend provider code to its audience-facing label. */
function prettyProvider(raw: string | null | undefined): string {
  if (!raw) return "";
  const k = raw
    .trim()
    .toUpperCase()
    .replace(/[\s_-]/g, "");
  if (k === "VDEM") return "V-Dem";
  if (k === "WGI") return "World Bank WGI";
  if (k === "WB" || k === "WORLDBANK") return "World Bank";
  if (k === "FAO" || k === "FAOSTAT") return "FAOSTAT";
  if (k === "ILO" || k === "ILOSTAT") return "ILOSTAT";
  return raw;
}

function directionOf(zChange: number): "rising" | "falling" | "flat" {
  if (zChange > 0.15) return "rising";
  if (zChange < -0.15) return "falling";
  return "flat";
}

/**
 * Build the full (country x recipe) match. Returns null when the recipe is
 * not in the scored fleet or the country is not scored on it.
 */
export function getCountryRecipeMatch(
  recipeId: string,
  iso2: string
): CountryRecipeMatch | null {
  if (!SAMPLE_10_RECIPE_IDS.includes(recipeId)) return null;

  let scoresFile;
  try {
    scoresFile = loadScores(recipeId);
  } catch {
    return null;
  }

  const target = iso2.toLowerCase();
  const entry = (scoresFile.scores as unknown as FleetEntry[]).find((e) => {
    const code = (e.iso2 ?? iso2For(e.name) ?? "").toLowerCase();
    return code === target;
  });
  if (!entry) return null;

  const weightByCode = new Map(
    entry.shap_attribution.map((s) => [s.indicator_code, s.signal_share_pct])
  );
  const canon = getRecipeCanonical(recipeId);

  const indicators: MatchIndicator[] = (entry.indicator_movement ?? [])
    .map((m): MatchIndicator | null => {
      if (!Array.isArray(m.trajectory_12q) || m.trajectory_12q.length === 0) return null;
      const shape = canon?.byCode.get(m.indicator_code) ?? null;
      return {
        code: m.indicator_code,
        name: m.indicator_name || getIndicatorLabel(m.indicator_code),
        provider: prettyProvider(m.provider),
        weightPct: weightByCode.get(m.indicator_code) ?? 0,
        trajectory: m.trajectory_12q,
        zChange: m.z_score_change,
        direction: directionOf(m.z_score_change),
        canonicalMean: shape ? shape.mean : null,
        canonicalP25: shape ? shape.p25 : null,
        canonicalP75: shape ? shape.p75 : null,
      };
    })
    .filter((x): x is MatchIndicator => x !== null)
    .sort((a, b) => b.weightPct - a.weightPct);

  if (indicators.length === 0) return null;

  const composite = entry.indicator_trajectory_composite_12q ?? [];

  const momentumByYear = entry.momentum_scores_by_year
    ? Object.keys(entry.momentum_scores_by_year)
        .sort()
        .map((year) => ({ year, score: entry.momentum_scores_by_year![year] }))
    : [];

  const analogues: MatchAnalogue[] = (entry.nearest_analogs ?? []).map((a) => ({
    country: a.country,
    iso2: (a.country_iso2 ?? iso2For(a.country) ?? "").toLowerCase(),
    year: a.year,
    matchPct: Math.round(a.match_score * 100),
    weak: a.weak_analog,
    whatHappenedNext:
      whnBlurb(a.country_iso2, a.country, a.year) ?? a.what_happened_next ?? null,
    // Join the analogue to the real verified event that hit that country
    // around that year under this recipe (title + public source).
    event: findAnalogueEvent(a.country, a.year, recipeId),
    path:
      Array.isArray(a.indicator_trajectory_12q) && a.indicator_trajectory_12q.length > 0
        ? a.indicator_trajectory_12q
        : null,
  }));

  return {
    recipeId,
    countryName: entry.name,
    iso2: (entry.iso2 ?? target).toLowerCase(),
    score: entry.score,
    rank: entry.rank,
    nScored: scoresFile.n_countries_scored,
    evalYear: entry.eval_year,
    windowYears: Math.max(1, Math.round((composite.length || 12) / 4)),
    inEvidenceBase: entry.in_evidence_base,
    canonicalWindowYears: canon?.windowYears ?? null,
    zone: entry.zone ?? null,
    zoneLabel: entry.zone_label ?? null,
    cosineSimilarity:
      typeof entry.cosine_similarity_S === "number" ? entry.cosine_similarity_S : null,
    composite,
    momentumByYear,
    momentumLabel: entry.momentum_label ?? null,
    vintage: loadVintage(),
    indicators,
    analogues,
  };
}

/**
 * Static params for the scored (fleet) match pages. Pre-renders only the top
 * match per recipe (~44 pages) to keep the build within CI's memory budget;
 * the long tail renders on demand when linked (pages are noindex).
 */
export function getMatchStaticParams(): Array<{ slug: string; iso: string }> {
  const out: Array<{ slug: string; iso: string }> = [];
  const seen = new Set<string>();
  for (const slug of SAMPLE_10_RECIPE_IDS) {
    let file;
    try {
      file = loadScores(slug);
    } catch {
      continue;
    }
    // Build-memory: pre-render only the top match per recipe (~44 pages total).
    // These pages are noindex and reached from in-app links, and dynamicParams
    // defaults to true, so the rest render on-demand. Pre-rendering the full
    // PER_RECIPE_CAP * 44 grid (~2,200 pages) OOMs CI's 2GB Node heap.
    const top = [...(file.scores as unknown as FleetEntry[])]
      .sort((a, b) => a.rank - b.rank)
      .slice(0, 1);
    for (const e of top) {
      const i2 = (e.iso2 ?? iso2For(e.name) ?? "").toLowerCase();
      if (!i2) continue;
      const key = `${slug}/${i2}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ slug, iso: i2 });
    }
  }
  return out;
}
