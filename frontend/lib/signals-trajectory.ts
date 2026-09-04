/**
 * lib/signals-trajectory.ts — Server-only data fetcher for the
 * Indicator Trajectory Panel on /signals/[country]/[slug].
 *
 * Design (Yuki Takahashi-Rowe + Dr. Lena Hadid-Marchetti, 2026-05-01):
 *   - 4 Athena queries, all parallelized: fingerprint→indicator ids,
 *     canonical pattern (top-PPS recipe row), country trajectory,
 *     reference country_b trajectory.
 *   - X-axis: years-from-pattern-end (0 = last year of canonical window).
 *     Callers receive pre-aligned arrays so the chart doesn't need to
 *     re-normalize at render time.
 *   - Z-score normalization per series within the displayed window.
 *     Threshold: if a country has <5 non-null points in the window, the
 *     indicator slot is marked hasData=false and the chart shows a
 *     "Insufficient data" card instead.
 *   - Predicted flag: each data point carries {value, isPredicte} so the
 *     client component can split the series at the prediction boundary and
 *     render the predicted tail as a dashed line.
 *   - Graceful degradation: every async call catches and returns null, so
 *     the page never 500s — it renders the "unavailable" fallback.
 *
 * Why server-only? Uses AWS SDK (Athena), which must not be bundled into
 * the browser. The "server-only" import enforces this at build time.
 */
import "server-only";

import { runQuery } from "@/lib/athena";
import indexData from "@/data/indexes.json";
import countriesData from "@/data/countries.json";
import type { IndexEntry } from "@/lib/types";
import type {
  IndicatorFingerprintEntry,
  RecipeAggregated,
} from "@/lib/recipes-aggregated";
import {
  getCanonicalRecipeFromBaked,
  type CanonicalRecipeRow,
} from "@/lib/signals-trajectory-canonical";

// ---------------------------------------------------------------------------
// Country id → name lookup from baked countries.json
// ---------------------------------------------------------------------------

interface CountryEntry {
  id: string;
  name: string;
  alpha_2: string;
}

const COUNTRY_BY_ID: Map<string, string> = new Map(
  (countriesData as CountryEntry[]).map((c) => [c.id, c.name])
);

// ---------------------------------------------------------------------------
// Index lookup — numeric_id → string indicator_id (e.g. 1 → "NY.GDP.MKTP.KD.ZG")
// ---------------------------------------------------------------------------

const INDEX_BY_NUMERIC_ID: Map<number, IndexEntry> = new Map(
  (indexData as IndexEntry[]).map((e) => [e.numeric_id, e])
);

function resolveIndicatorId(numericId: number): string | null {
  return INDEX_BY_NUMERIC_ID.get(numericId)?.id ?? null;
}

function resolveIndicatorName(numericId: number): string {
  return INDEX_BY_NUMERIC_ID.get(numericId)?.name ?? `Indicator #${numericId}`;
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface TrajectoryPoint {
  /** Years from pattern-end (0 = pattern end year, negative = before, positive = after). */
  yearsFromEnd: number;
  /** Calendar year of the subject country. Null for reference-only padding. */
  calendarYear: number | null;
  /** Z-scored value. Null means missing / insufficient for z-score. */
  value: number | null;
  /** Whether this value was predicted by the pipeline (vs observed). */
  isPredicted: boolean;
}

export interface CanonicalPoint {
  /** Same yearsFromEnd index as the subject series. */
  yearsFromEnd: number;
  /** Z-scored reference value. Null = missing. */
  value: number | null;
}

export interface IndicatorTrajectory {
  numericId: number;
  indicatorId: string; // string form e.g. "NY.GDP.MKTP.KD.ZG"
  indicatorName: string;
  /** False when <5 observed points in window → render placeholder. */
  hasData: boolean;
  /** True when no reference data available either — show "canonical only" empty. */
  hasCanonical: boolean;
  /** Subject country trajectory (z-scored, years-from-end axis). */
  subject: TrajectoryPoint[];
  /** Canonical reference trajectory (z-scored to its own window). */
  canonical: CanonicalPoint[];
  /** Pearson r between subject and canonical on overlapping non-null years. */
  pearsonR: number | null;
  /** Reference country name + years for the chart label. */
  referenceLabel: string;
}

export interface TrajectoryPanelData {
  /** Country B (reference) from the top-PPS recipe instance. */
  referenceCountryId: string | null;
  referenceCountryName: string | null;
  referenceStartYear: number | null;
  referenceEndYear: number | null;
  patternLength: number | null;
  trajectories: IndicatorTrajectory[];
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

/**
 * Load all data needed for the trajectory panel.
 * Returns null on any fatal error — component renders graceful fallback.
 *
 * #624: Signature changed from `(country, slug, fingerprint, canonicalLength)`
 * to `(country, recipe)`. The full RecipeAggregated record is required so
 * that the canonical recipe metadata (country_b, start_year_b) can be
 * read from the pre-baked JSON instead of via a per-page-load Athena
 * query. Callers already have the RecipeAggregated in scope when they
 * invoke this function.
 */
export async function loadTrajectoryPanelData(
  countryName: string,
  recipe: RecipeAggregated
): Promise<TrajectoryPanelData | null> {
  try {
    // Step 1: Pick top-N=4 fingerprint indicators that we can actually query
    // for. Critical: filter THEN slice (not slice-then-filter), otherwise
    // unmapped indicators (e.g. V-Dem additions not yet in indexes.json
    // per #550) consume slots and leave the panel with fewer than 4 cards.
    // We need the string indicator_id to query qgi_data.indicators_completed
    // (Athena table is partitioned by indicator_id), so unmapped numeric_ids
    // genuinely cannot fetch trajectory data — but we should backfill from
    // lower-ranked indicators that DO resolve so the 2x2 panel stays full.
    const resolved = [...recipe.indicator_fingerprint]
      .sort((a, b) => b.tfidf_score - a.tfidf_score)
      .map((fp) => ({
        numericId: fp.indicator_id,
        indicatorId: resolveIndicatorId(fp.indicator_id),
        indicatorName: resolveIndicatorName(fp.indicator_id),
      }))
      .filter((r) => r.indicatorId !== null)
      .slice(0, 4) as Array<{
      numericId: number;
      indicatorId: string;
      indicatorName: string;
    }>;

    if (resolved.length === 0) return null;

    // Step 2 (#624): Read the canonical recipe metadata from the pre-baked
    // RecipeAggregated record. This replaces the previous unpartitioned
    // Athena scan of qgi_data.recipes WHERE event_category='X' (which
    // touched all 154 country_a_id partitions per call). Pass the module-
    // level COUNTRY_BY_ID so the country_b_name fallback works.
    const canonicalRecipe = getCanonicalRecipeFromBaked(recipe, COUNTRY_BY_ID);

    // Step 3: Fetch subject country trajectory for all resolved indicators.
    // #626 (QA audit 2026-05-07): SORT before joining to make the SQL
    // string deterministic. Without sorting, two Vercel serverless instances
    // can build slightly different SQL strings for the same indicator set
    // (because `resolved` ordering depends on the fingerprint's tfidf
    // ordering, which can permute between instances). Different SQL string
    // = different unstable_cache key = independent Athena execution per
    // instance. Direct evidence (2026-05-07): 8 consecutive Vietnam queries
    // with the same 4 indicator IDs in 8 different orders, all
    // `Reused: false`. Sorting restores cache effectiveness — the SQL
    // result is order-independent (rows returned regardless of IN() order;
    // ORDER BY indicator_id, year already re-sorts the output).
    const indicatorIdList = resolved
      .map((r) => `'${r.indicatorId}'`)
      .sort()
      .join(",");
    const subjectRows = await fetchCountryTrajectory(countryName, indicatorIdList);

    // Step 4: If we have a canonical recipe, fetch its country_b trajectory.
    let referenceRows: RawIndicatorRow[] = [];
    if (canonicalRecipe) {
      referenceRows = await fetchCountryTrajectory(
        canonicalRecipe.country_b_name,
        indicatorIdList
      );
    }

    // Step 5: Build per-indicator aligned series.
    const patternLength = canonicalRecipe?.length ?? recipe.canonical_length;
    const refEndYear = canonicalRecipe
      ? canonicalRecipe.start_year_b + canonicalRecipe.length - 1
      : null;

    // Subject end year: use the most recent year with any data across all
    // subject indicators, capped at the current year. We use this as the
    // "now" anchor so the subject line extends right up to the latest available
    // data point (observed or predicted).
    const allSubjectYears = subjectRows.map((r) => r.year).filter((y) => !isNaN(y));
    const subjectEndYear =
      allSubjectYears.length > 0 ? Math.max(...allSubjectYears) : refEndYear; // fall back to ref end year if subject has no data at all

    // Window to display: patternLength years plus 2-year forecast buffer.
    const displayLength = patternLength + 2;
    const refStartYear = refEndYear !== null ? refEndYear - patternLength + 1 : null;

    const trajectories: IndicatorTrajectory[] = resolved.map((r) => {
      const subjRows = subjectRows.filter((row) => row.indicator_id === r.indicatorId);
      const refRowsForIndicator = referenceRows.filter(
        (row) => row.indicator_id === r.indicatorId
      );

      return buildTrajectory({
        numericId: r.numericId,
        indicatorId: r.indicatorId,
        indicatorName: r.indicatorName,
        subjectRows: subjRows,
        referenceRows: refRowsForIndicator,
        patternLength,
        displayLength,
        refStartYear,
        refEndYear,
        subjectEndYear,
        referenceLabel: canonicalRecipe
          ? `${canonicalRecipe.country_b_name} ${canonicalRecipe.start_year_b}–${refEndYear}`
          : "Canonical reference",
      });
    });

    return {
      referenceCountryId: canonicalRecipe?.country_b_id ?? null,
      referenceCountryName: canonicalRecipe?.country_b_name ?? null,
      referenceStartYear: refStartYear,
      referenceEndYear: refEndYear,
      patternLength,
      trajectories,
    };
  } catch (err) {
    console.error("[signals-trajectory] Fatal error loading panel data:", err);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

interface RawIndicatorRow {
  indicator_id: string;
  year: number;
  value: number;
  is_predicted: boolean;
}

// #624 strict-review F1: getCanonicalRecipeFromBaked + CanonicalRecipeRow
// were extracted to `lib/signals-trajectory-canonical.ts` so vitest tests
// import the real production function instead of an inlined copy that
// could drift. The pure logic has zero AWS/server dependency.

async function fetchCountryTrajectory(
  countryName: string,
  indicatorIdList: string
): Promise<RawIndicatorRow[]> {
  try {
    const safe = countryName.replace(/'/g, "''");
    const rows = await runQuery(
      `SELECT indicator_id, year, value, is_predicted
       FROM qgi_data.indicators_completed
       WHERE country = '${safe}'
         AND indicator_id IN (${indicatorIdList})
       ORDER BY indicator_id, year`
    );
    return rows
      .map((row) => ({
        indicator_id: row.indicator_id ?? "",
        year: parseInt(row.year, 10),
        value: parseFloat(row.value),
        is_predicted: row.is_predicted === "true",
      }))
      .filter((r) => !isNaN(r.year) && !isNaN(r.value));
  } catch (err) {
    console.warn(
      "[signals-trajectory] fetchCountryTrajectory failed for",
      countryName,
      err
    );
    return [];
  }
}

/** Compute mean and std of a finite number array. */
function meanStd(arr: number[]): { mean: number; std: number } {
  if (arr.length === 0) return { mean: 0, std: 1 };
  const mean = arr.reduce((s, v) => s + v, 0) / arr.length;
  const variance = arr.reduce((s, v) => s + (v - mean) ** 2, 0) / arr.length;
  return { mean, std: Math.sqrt(variance) || 1 };
}

/** Pearson correlation between two equal-length arrays (null = missing). */
function pearsonR(a: (number | null)[], b: (number | null)[]): number | null {
  const pairs: [number, number][] = [];
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] != null && b[i] != null) pairs.push([a[i]!, b[i]!]);
  }
  if (pairs.length < 3) return null;
  const n = pairs.length;
  const mx = pairs.reduce((s, [x]) => s + x, 0) / n;
  const my = pairs.reduce((s, [, y]) => s + y, 0) / n;
  let sxy = 0,
    sxx = 0,
    syy = 0;
  for (const [x, y] of pairs) {
    sxy += (x - mx) * (y - my);
    sxx += (x - mx) ** 2;
    syy += (y - my) ** 2;
  }
  const denom = Math.sqrt(sxx * syy);
  return denom === 0 ? null : sxy / denom;
}

interface BuildArgs {
  numericId: number;
  indicatorId: string;
  indicatorName: string;
  subjectRows: RawIndicatorRow[];
  referenceRows: RawIndicatorRow[];
  patternLength: number;
  displayLength: number;
  refStartYear: number | null;
  refEndYear: number | null;
  subjectEndYear: number | null;
  referenceLabel: string;
}

function buildTrajectory(args: BuildArgs): IndicatorTrajectory {
  const {
    numericId,
    indicatorId,
    indicatorName,
    subjectRows,
    referenceRows,
    patternLength,
    displayLength,
    refStartYear,
    refEndYear,
    subjectEndYear,
    referenceLabel,
  } = args;

  // --- Reference series (country_b) ---
  // Build a year → {value, isPredicted} map for the reference, covering
  // the canonical window [refStartYear, refEndYear + 2].
  const refMap = new Map<number, { value: number; isPredicted: boolean }>();
  for (const row of referenceRows) {
    refMap.set(row.year, { value: row.value, isPredicted: row.is_predicted });
  }

  // Collect reference values in window to z-score them.
  const refWindowValues: number[] = [];
  if (refStartYear !== null && refEndYear !== null) {
    for (let y = refStartYear; y <= refEndYear + 2; y++) {
      const r = refMap.get(y);
      if (r != null && Number.isFinite(r.value)) refWindowValues.push(r.value);
    }
  }
  const refStats = meanStd(refWindowValues);

  // Build canonical series aligned to yearsFromEnd.
  const canonical: CanonicalPoint[] = [];
  if (refStartYear !== null && refEndYear !== null) {
    for (let i = 0; i < displayLength; i++) {
      const yre = i - (patternLength - 1); // yearsFromEnd
      const calYear = refEndYear - (patternLength - 1) + i;
      const raw = refMap.get(calYear);
      canonical.push({
        yearsFromEnd: yre,
        value:
          raw != null && Number.isFinite(raw.value)
            ? (raw.value - refStats.mean) / refStats.std
            : null,
      });
    }
  }

  // --- Subject series ---
  // Build year → {value, isPredicted} map.
  const subjMap = new Map<number, { value: number; isPredicted: boolean }>();
  for (const row of subjectRows) {
    subjMap.set(row.year, { value: row.value, isPredicted: row.is_predicted });
  }

  // We display displayLength years ending at (subjectEndYear + 2).
  // If we don't have subjectEndYear (no canonical recipe), use the most
  // recent observed year as the anchor.
  const subjEndYear =
    subjectEndYear ??
    (subjectRows.length > 0 ? Math.max(...subjectRows.map((r) => r.year)) : null);

  // Check data sufficiency: count non-null observed points in the canonical window.
  const observedInWindow = subjectRows.filter(
    (r) =>
      !r.is_predicted &&
      (subjEndYear === null ||
        (r.year >= subjEndYear - patternLength + 1 && r.year <= subjEndYear + 2))
  );
  const hasData = observedInWindow.length >= 5;

  // Collect subject values in window to z-score them.
  const subjWindowValues: number[] = [];
  if (subjEndYear !== null) {
    for (let i = 0; i < displayLength; i++) {
      const calYear = subjEndYear - (patternLength - 1) + i;
      const r = subjMap.get(calYear);
      if (r != null && Number.isFinite(r.value)) subjWindowValues.push(r.value);
    }
  }
  const subjStats = meanStd(subjWindowValues);

  // Build subject trajectory.
  const subject: TrajectoryPoint[] = [];
  if (subjEndYear !== null) {
    for (let i = 0; i < displayLength; i++) {
      const yre = i - (patternLength - 1);
      const calYear = subjEndYear - (patternLength - 1) + i;
      const raw = subjMap.get(calYear);
      subject.push({
        yearsFromEnd: yre,
        calendarYear: calYear,
        value:
          hasData && raw != null && Number.isFinite(raw.value)
            ? (raw.value - subjStats.mean) / subjStats.std
            : null,
        isPredicted: raw?.isPredicted ?? false,
      });
    }
  }

  // Pearson r between subject z-scores and canonical z-scores.
  const r = pearsonR(
    subject.map((p) => p.value),
    canonical.map((p) => p.value)
  );

  return {
    numericId,
    indicatorId,
    indicatorName,
    hasData,
    hasCanonical: canonical.some((p) => p.value !== null),
    subject,
    canonical,
    pearsonR: r,
    referenceLabel,
  };
}
