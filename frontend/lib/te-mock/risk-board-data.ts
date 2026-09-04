/**
 * risk-board-data — board data for /risk-board.
 *
 * V4.1 wire-up (2026-05-29):
 *   - Cascade-era recipe rows (foreign_intervention, civil_war_and_insurgency,
 *     etc.) keep their hand-authored cells.
 *   - TE sample-10 recipe rows are generated at runtime from real scores
 *     files: top-10 countries by discrimination rank, sorted descending.
 *   - getBoardRecipeIds() now includes all 10 TE sample-10 recipes.
 *   - getTopPairs() now includes top-1 pair from each TE recipe row.
 *
 * Three feeds:
 *   1. getTopPairs()        — today's top {country × recipe} pairs, ranked.
 *   2. getRecipeRow(id)     — for a recipe row, the top-10 country/score cells.
 *   3. getRecentMovements() — empty at vintage-1 (no prior vintage to diff).
 *
 * All scores are discrimination ranks, NOT probabilities.
 */

import { getAllRecipes, getRecipe, type TrackerRecipe } from "@/lib/te-mock/recipes";
import {
  loadScores,
  loadCountryIndex,
  loadVintage,
  FLEET_RUN_1_RECIPE_IDS,
} from "@/lib/te-data-contract/load";

// V4.1 §I: read the live vintage from the MANIFEST (produced_at_utc, date part)
// so each fleet re-bake lifts the stamp automatically. Was hardcoded "2026-05-28".
export const BOARD_VINTAGE = loadVintage().slice(0, 10);

/* ────────────────────────────────────────────────────────────────────────── */
/* Types                                                                       */
/* ────────────────────────────────────────────────────────────────────────── */

export interface BoardPair {
  country: string;
  recipe_id: string;
  score: number;
  /**
   * Rank-shift vs the prior bake vintage (quarterly cadence per R&D reply
   * §Q3, docs-specs #169). Negative = moved up (lower rank #). NULL at
   * vintage 1 — no prior vintage to diff against.
   */
  rank_delta_q: number | null;
}

/**
 * Cell-state honesty (R&D reply docs-specs #169 §Q7):
 *   - "scored"        — country has indicator coverage AND a walk has run.
 *   - "not_scored"    — country lacks coverage for this recipe's indicators;
 *                       NEVER framed as "low score" (different thing).
 *   - "no_walk_yet"   — the recipe itself is queued; no scores exist for
 *                       anyone yet.
 */
export type CellState = "scored" | "not_scored" | "no_walk_yet";

export interface BoardCell {
  country: string;
  /**
   * Discrimination rank, 0–100. Per M8-R5 NOT a probability.
   * `null` when state ≠ "scored".
   */
  score: number | null;
  /**
   * Honesty contract per R&D reply §Q7. A country missing coverage for a
   * recipe is "not_scored," never rendered as a low score.
   */
  state: CellState;
}

export interface RecipeRow {
  recipe_id: string;
  cells: BoardCell[];
  /** "graduated" | "walked_no_graduation" | "live_legacy" | "queued". */
  display_state: "graduated" | "walked_no_graduation" | "live_legacy" | "queued";
  /**
   * R&D reply §Q7 — per-recipe country coverage. n_countries_scored is the
   * count of countries with sufficient indicator coverage for THIS recipe.
   * countries_not_scored_iso lists the platform-roster countries without
   * coverage (for honesty surfacing in the row footer).
   *
   * Both null on `no_walk_yet` rows.
   */
  n_countries_scored: number | null;
  countries_not_scored_iso: string[] | null;
  /**
   * Total platform-roster size at the current vintage — denominator for
   * the coverage caption ("X of Y platform countries scored").
   */
  platform_roster_size: number;
}

export interface RankMovement {
  country: string;
  recipe_id: string;
  prior_rank: number;
  new_rank: number;
  /**
   * Number of bake vintages back the prior reading is from. ≥1 (quarterly
   * cadence per R&D reply §Q3). At vintage 1, the entire feed is empty —
   * the frontend renders <HistoryAccumulatingGate /> instead.
   */
  delta_quarters: number;
  /**
   * The vintage tag of the prior reading — e.g. "2026-Q2". Lets the UI
   * render "since 2026-Q2" verbatim, more honest than a relative count.
   */
  vs_vintage: string;
  /** A one-line hint why the rank shifted. Illustrative — not causal. */
  blurb: string;
}

/* ────────────────────────────────────────────────────────────────────────── */
/* TOP PAIRS — today's headline strip                                          */
/* ────────────────────────────────────────────────────────────────────────── */

/**
 * Build top pairs from all 44 fleet-run-2 recipes: top-1 country per recipe,
 * collected across the whole catalog and then sorted descending by score.
 * rank_delta_q is null at vintage 1 — no prior vintage to diff against.
 */
function buildAllTopPairs(): BoardPair[] {
  const pairs: BoardPair[] = [];
  for (const recipeId of FLEET_RUN_1_RECIPE_IDS) {
    try {
      const row = getTERecipeRow(recipeId);
      const top = row?.cells.find((c) => c.state === "scored" && c.score != null);
      if (top && top.score != null) {
        pairs.push({
          country: top.country,
          recipe_id: recipeId,
          score: top.score,
          rank_delta_q: null, // vintage 1 — no prior
        });
      }
    } catch {
      // skip missing / malformed scores files
    }
  }
  return pairs.sort((a, b) => b.score - a.score);
}

export function getTopPairs(): BoardPair[] {
  // Derived entirely from real fleet-run-2 scores — no hand-authored data.
  return buildAllTopPairs();
}

/* ────────────────────────────────────────────────────────────────────────── */
/* CURATED TOP PAIRS — hand-curated 20-pair list for the dashboard right rail */
/* ────────────────────────────────────────────────────────────────────────── */

/**
 * Extends BoardPair with vectors + rationale produced by the curation pass.
 * `vectors` is the audience-facing list of risk vectors driving the score
 * (rendered as small inline glyphs); `rationale` is a one-sentence audience
 * caption. Both optional — the loader renders calmly when absent.
 */
export interface CuratedBoardPair extends BoardPair {
  rank: number;
  vectors?: string[];
  rationale?: string;
}

interface CuratedTopPairsFile {
  produced_at_utc: string;
  curated_by: string;
  rubric: string;
  pairs: Array<{
    rank: number;
    country: string;
    recipe_id: string;
    score: number;
    vectors?: string[];
    rationale?: string;
  }>;
}

/**
 * Loads the hand-curated 20-pair list at `data/curated-top-pairs.json` if it
 * exists. Falls through to an empty array when the file is absent — the
 * dashboard rail then back-fills from getTopPairs() so the surface never
 * renders empty.
 *
 * The JSON is produced by a parallel curation agent. Shape:
 *   { produced_at_utc, curated_by, rubric, pairs: [...] }
 *
 * `rank_delta_q` is set to null for curated pairs — the curation is a
 * vintage-1 hand-selection, not a quarterly diff. Future curated drops can
 * include rank_delta_q if they want to.
 */
export function getCuratedTopPairs(): CuratedBoardPair[] {
  try {
    // Lazy require so a missing file does not break SSR import resolution.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const data = require("@/data/curated-top-pairs.json") as CuratedTopPairsFile;
    if (!data || !Array.isArray(data.pairs)) return [];
    return data.pairs.map((p) => ({
      rank: p.rank,
      country: p.country,
      recipe_id: p.recipe_id,
      score: p.score,
      rank_delta_q: null,
      vectors: p.vectors,
      rationale: p.rationale,
    }));
  } catch {
    // File absent or malformed — graceful empty.
    return [];
  }
}

/* ────────────────────────────────────────────────────────────────────────── */
/* PER-RECIPE ROWS — the heatmap grid                                          */
/* ────────────────────────────────────────────────────────────────────────── */

// RECIPE_ROW_CELLS intentionally removed — all 5 cascade-era hand-authored
// rows (foreign_intervention, civil_war_and_insurgency, terrorist_attack,
// economic_recession, elections_and_voting) are now in fleet-run-2 with real
// scores. getRecipeRow() falls through to getTERecipeRow() for them.
// Keeping this map non-empty would shadow the real pipeline data.
const RECIPE_ROW_CELLS: Record<string, BoardCell[]> = {};

/**
 * PLATFORM_ROSTER_SIZE: fallback denominator for coverage captions when the
 * scores file doesn't carry n_countries_scored (should not happen for
 * fleet-run-2, but kept as a safe floor).
 */
const PLATFORM_ROSTER_SIZE = 174;

// RECIPE_COVERAGE removed — all 44 fleet-run-2 recipes carry real
// n_countries_scored in their scores file (top-level field). The five
// previously hand-authored entries (foreign_intervention,
// civil_war_and_insurgency, terrorist_attack, economic_recession,
// elections_and_voting) are superseded by real pipeline counts.
// getRecipeRow() now reads coverage from loadScores() for every TE recipe.

/**
 * Recipes that are explicitly "queued" / no-walk on the board.
 * Each renders as a greyed row with "no walk yet" cells.
 */
const QUEUED_RECIPES_ON_BOARD = [
  "political_repression",
  "currency_crisis",
  "mass_protest",
  "human_rights_violation",
  "humanitarian_crisis",
  "drought_and_famine",
  "interstate_war",
  "military_coup",
  "democratic_transition",
  "constitutional_change",
];

const EMPTY_QUEUED_CELLS: BoardCell[] = Array.from({ length: 10 }, () => ({
  country: "—",
  score: null,
  state: "no_walk_yet" as const,
}));

// ─── TE fleet-run-2 row builder ───────────────────────────────────────────────

/**
 * Build a RecipeRow for a TE fleet-run-2 recipe using real scores.
 * Returns null if scores are unavailable (loader throws).
 */
function buildTERecipeRow(recipeId: string): RecipeRow | null {
  try {
    const recipe = getRecipe(recipeId);
    if (!recipe) return null;
    const sf = loadScores(recipeId);
    // Resolve n_countries_scored from real scores file.
    const n_countries_scored = sf.n_countries_scored ?? sf.scores.length;
    // Top-10 by score descending.
    const top10 = sf.scores
      .filter((e) => e.score != null)
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
      .slice(0, 10);
    const cells: BoardCell[] = top10.map((e) => ({
      country: e.name,
      score: e.score ?? null,
      state: "scored" as const,
    }));
    // Pad to 10 if fewer than 10 scored countries.
    while (cells.length < 10) {
      cells.push({ country: "—", score: null, state: "not_scored" as const });
    }
    // Round-2: countries_not_scored_iso now baked in scores file.
    const countries_not_scored_iso =
      Array.isArray(sf.countries_not_scored_iso) && sf.countries_not_scored_iso.length > 0
        ? sf.countries_not_scored_iso
        : null;
    return {
      recipe_id: recipeId,
      cells,
      display_state: "walked_no_graduation",
      n_countries_scored,
      countries_not_scored_iso,
      platform_roster_size: sf.n_countries_scored ?? PLATFORM_ROSTER_SIZE,
    };
  } catch {
    return null;
  }
}

// Module-level cache for TE rows (avoid re-loading on every call).
const _teRowCache = new Map<string, RecipeRow | null>();

function getTERecipeRow(recipeId: string): RecipeRow | null {
  if (!_teRowCache.has(recipeId)) {
    _teRowCache.set(recipeId, buildTERecipeRow(recipeId));
  }
  return _teRowCache.get(recipeId) ?? null;
}

/**
 * Round-3.5 (2026-05-29) — full per-recipe country score map.
 *
 * Drives the Risk Board "select up to 10 countries" custom-grid mode.
 * Returns every country with a score in the recipe, regardless of top-10
 * rank. The user can then select arbitrary countries (e.g. Russia) and
 * the grid will resolve a real cell for them in every recipe row.
 *
 * - Cascade-era recipes (hand-authored): only the top-10 entries in
 *   RECIPE_ROW_CELLS contribute. Countries outside that set resolve to
 *   "not scored" — honest, matches the data we actually have.
 * - TE sample-10 recipes: full loadScores() corpus is used, which is
 *   the platform roster (~150 countries with scores per recipe).
 * - Queued recipes: empty map. The grid renders the "Coming soon" cell.
 *
 * The map is keyed by the same country `name` strings that appear in
 * BoardCell.country, so the client component looks countries up by
 * the same key it already renders.
 */
export function getRecipeFullScoreMap(recipeId: string): Record<string, number> {
  // TE fleet-run-2 rows (real data — all 44 walked recipes).
  if (FLEET_RUN_1_RECIPE_IDS.includes(recipeId)) {
    try {
      const sf = loadScores(recipeId);
      const map: Record<string, number> = {};
      for (const e of sf.scores) {
        if (typeof e.score === "number") {
          map[e.name] = e.score;
        }
      }
      return map;
    } catch {
      return {};
    }
  }
  // Queued / no walk
  return {};
}

export function getRecipeRow(recipeId: string): RecipeRow | null {
  const recipe = getRecipe(recipeId);
  if (!recipe) return null;
  // 1. TE fleet-run-2 rows (real data — all 44 walked recipes including the
  //    former cascade-era hand-authored group).
  if (FLEET_RUN_1_RECIPE_IDS.includes(recipeId)) {
    const teRow = getTERecipeRow(recipeId);
    if (teRow) return teRow;
  }
  // 2. Queued / no walk.
  return {
    recipe_id: recipeId,
    cells: EMPTY_QUEUED_CELLS,
    display_state: "queued",
    n_countries_scored: null,
    countries_not_scored_iso: null,
    platform_roster_size: PLATFORM_ROSTER_SIZE,
  };
}

/**
 * Recipes shown on the board, in order. Fleet-run-1 walked recipes first
 * (all 44, real data — including the former cascade-era group), then queued
 * recipes that didn't make the fleet-run-2 set but are in the cascade catalog.
 */
export function getBoardRecipeIds(): string[] {
  const fleetSet = new Set(FLEET_RUN_1_RECIPE_IDS);
  // Queued-only entries: board recipes not in fleet-run-2
  const queuedOnly = QUEUED_RECIPES_ON_BOARD.filter((id) => !fleetSet.has(id));
  return [...FLEET_RUN_1_RECIPE_IDS, ...queuedOnly];
}

export function getBoardRecipes(): TrackerRecipe[] {
  const ids = getBoardRecipeIds();
  const lookup = new Map(getAllRecipes().map((r) => [r.recipe_id, r]));
  return ids.map((id) => lookup.get(id)).filter((r): r is TrackerRecipe => Boolean(r));
}

/* ────────────────────────────────────────────────────────────────────────── */
/* RECENT MOVEMENTS — "what just changed"                                      */
/* ────────────────────────────────────────────────────────────────────────── */

/**
 * Recent movements feed.
 *
 * Per R&D pipeline reply §3 (docs-specs #169): rank-shift fields are EMPTY at
 * vintage 1 — scores only change when a recipe is re-walked/re-scored
 * (quarterly), so there's no prior bake to diff against. The frontend
 * renders <HistoryAccumulatingGate /> instead.
 *
 * The illustrative array below shows the SHAPE of the eventual data feed
 * (rank shifts vs prior quarterly vintage). Kept for component-shape
 * verification + the future post-vintage-2 state; getRecentMovements()
 * returns [] at current vintage 1.
 */
const RECENT_MOVEMENTS_FUTURE_SHAPE: RankMovement[] = [
  {
    country: "Argentina",
    recipe_id: "economic_recession",
    prior_rank: 4,
    new_rank: 1,
    delta_quarters: 1,
    vs_vintage: "2026-Q2",
    blurb:
      "Inflation re-acceleration + FX-reserve drawdown pulled the country's similarity higher.",
  },
  {
    country: "Tajikistan",
    recipe_id: "foreign_intervention",
    prior_rank: 7,
    new_rank: 5,
    delta_quarters: 1,
    vs_vintage: "2026-Q2",
    blurb:
      "State-capacity indicators drifted further from the canonical shape's recovery arm.",
  },
  {
    country: "Pakistan",
    recipe_id: "terrorist_attack",
    prior_rank: 2,
    new_rank: 1,
    delta_quarters: 1,
    vs_vintage: "2026-Q2",
    blurb: "CSO restriction index moved further inside the historical pre-event band.",
  },
  {
    country: "Sudan",
    recipe_id: "civil_war_and_insurgency",
    prior_rank: 1,
    new_rank: 3,
    delta_quarters: 1,
    vs_vintage: "2026-Q2",
    blurb: "Trajectory smoothing pushed the country one decile down: still HIGH-zone.",
  },
  {
    country: "Equatorial Guinea",
    recipe_id: "foreign_intervention",
    prior_rank: 2,
    new_rank: 3,
    delta_quarters: 1,
    vs_vintage: "2026-Q2",
    blurb: "Reshuffle within the top-band; absolute score nearly unchanged.",
  },
  {
    country: "Turkey",
    recipe_id: "economic_recession",
    prior_rank: 1,
    new_rank: 2,
    delta_quarters: 1,
    vs_vintage: "2026-Q2",
    blurb: "Unemployment series revision narrowed alignment by half a decile.",
  },
  {
    country: "Lebanon",
    recipe_id: "economic_recession",
    prior_rank: 5,
    new_rank: 3,
    delta_quarters: 1,
    vs_vintage: "2026-Q2",
    blurb:
      "Renewed currency depreciation moved the trajectory further into the danger band.",
  },
  {
    country: "Niger",
    recipe_id: "civil_war_and_insurgency",
    prior_rank: 12,
    new_rank: 10,
    delta_quarters: 1,
    vs_vintage: "2026-Q2",
    blurb: "Crossed the row's top-10 threshold; rural governance index slipped further.",
  },
  {
    country: "Ecuador",
    recipe_id: "economic_recession",
    prior_rank: 11,
    new_rank: 10,
    delta_quarters: 1,
    vs_vintage: "2026-Q2",
    blurb: "First appearance inside this row's top-10 since the prior release.",
  },
];

/**
 * Returns recent rank movements at the current vintage.
 *
 * Vintage-1 reality: empty array. The pipeline emits an empty feed at the
 * first bake because there's no prior vintage to diff against (R&D reply
 * §3, docs-specs #169). RecentMovements component renders the
 * HistoryAccumulatingGate when this is empty.
 *
 * The vintage-2+ feed will be quarterly diffs against the prior bake.
 */
export function getRecentMovements(): RankMovement[] {
  // Vintage 1 — empty. The future shape lives in RECENT_MOVEMENTS_FUTURE_SHAPE
  // and will become live data starting at vintage 2.
  void RECENT_MOVEMENTS_FUTURE_SHAPE;
  return [];
}

/**
 * The post-vintage-2 feed. Exposed for component-shape testing + the
 * eventual state. Component reads via getRecentMovements() which returns
 * empty at vintage 1.
 */
export function getRecentMovementsFutureShape(): RankMovement[] {
  return RECENT_MOVEMENTS_FUTURE_SHAPE.slice().sort(
    (a, b) => a.delta_quarters - b.delta_quarters
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/* Helpers                                                                     */
/* ────────────────────────────────────────────────────────────────────────── */

/** Zone label for a discrimination score (mirrors capability §6 in the guide). */
export function zoneFor(score: number | null): "LOW" | "MODERATE" | "HIGH" | "—" {
  if (score === null) return "—";
  if (score < 40) return "LOW";
  if (score < 65) return "MODERATE";
  return "HIGH";
}
