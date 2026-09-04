/**
 * analogue-pair — resolver for the individual analogue comparison page
 * (`/analogues/[trio]`, trio = `${subjectIso2}-${analogueIso2}-${year}`).
 *
 * An analogue is: a SUBJECT country (today) matched by the Trajectory Engine to
 * a past country-year, under a primary trend. This page shows, for that trend's
 * DRIVER indicators, the two countries' trajectories over the trend's canonical
 * window — the subject's recent run-up vs the analogue's run-up to its event.
 *
 * Each indicator series is z-scored against that country's own full history, so
 * the overlay reads as SHAPE resemblance (the basis of the match), not raw-level
 * difference. Window length = the trend's canonical length (greedy_walk.chosen_window).
 *
 * Honesty: "what happened next" is dated history ABOUT THE ANALOGUE, never a
 * forecast about the subject.
 */
import { loadAnalogs, loadCardV3 } from "@/lib/te-data-contract/load";
import { getIndicatorSeries } from "@/lib/te-data-contract/indicator-panels";
import { getIndicatorLabel } from "@/lib/indicator-labels";
import { getWhatHappenedNextByIso } from "@/lib/curation/what-happened-next";
import { getRecipe } from "@/lib/te-mock/recipes";
import { familyColor } from "@/lib/te-mock/l1-families";
import { iso2For } from "@/lib/te-mock/country-flags";

const DEFAULT_WINDOW = 12;

export interface DriverOverlay {
  code: string;
  name: string;
  /** All series are 0..100 display (z-scored vs each country's own history, then
   *  mapped ±3σ → 0..100), POSITION-ALIGNED to the canonical window: index i is
   *  (windowYears - 1 - i) years before the end; the last index is the end
   *  (today for the subject, the event year for the analogue and the canonical).
   *  null = no value that year. */
  subject: (number | null)[];
  analogue: (number | null)[];
  /** The trend's canonical shape for this indicator (mean) plus its p25/p75
   *  band, on the same 0..100 scale and alignment. null when the card carries no
   *  alignment for this indicator. */
  canonical: number[] | null;
  canonicalLo: number[] | null;
  canonicalHi: number[] | null;
}

export interface AnaloguePair {
  subjectIso2: string;
  subjectName: string;
  analogueIso2: string;
  analogueName: string;
  analogueYear: number;
  recipeId: string;
  trendLabel: string;
  familyColor: string;
  matchScore: number; // 0..100
  weak: boolean;
  windowYears: number;
  whatHappenedNext: string | null;
  sources?: string[];
  drivers: DriverOverlay[];
}

/** Z-score a yearly series against its own full history. Returns {} if <2 points. */
function zscoreFull(series: Record<string, number> | null): Record<string, number> {
  if (!series) return {};
  const vals = Object.values(series);
  if (vals.length < 2) return {};
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  const variance = vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length;
  const std = Math.sqrt(variance) || 1;
  const out: Record<string, number> = {};
  for (const [y, v] of Object.entries(series)) out[y] = (v - mean) / std;
  return out;
}

/** Map a z-score to the 0..100 display scale (±3σ clamped) — mirrors the
 *  `zTrajToDisplay` mapping used for the 12-quarter analogue trajectories. */
function zToDisplay(z: number): number {
  return Math.max(0, Math.min(100, ((z + 3) / 6) * 100));
}

/** Position-aligned window of display values, length W, ending at endYear:
 *  index i maps to year (endYear - (W - 1) + i); null where the year is missing. */
function windowAligned(
  z: Record<string, number>,
  endYear: number,
  W: number
): (number | null)[] {
  const out: (number | null)[] = [];
  for (let i = 0; i < W; i++) {
    const v = z[String(endYear - (W - 1) + i)];
    out.push(typeof v === "number" ? zToDisplay(v) : null);
  }
  return out;
}

const countReal = (arr: (number | null)[]) =>
  arr.reduce((n: number, v) => n + (v === null ? 0 : 1), 0);

export function getAnaloguePair(
  subjectIso2: string,
  analogueIso2: string,
  year: number
): AnaloguePair | null {
  let entries;
  try {
    entries = loadAnalogs().entries;
  } catch {
    return null;
  }
  const si = subjectIso2.toLowerCase();
  const ai = analogueIso2.toLowerCase();
  // Tolerant match: prefer the stored ISO-2, fall back to name→ISO-2. Lets links
  // built from country names (e.g. the country-profile panel) resolve even when
  // the stored code and iso2For(name) disagree on a long-tail country.
  const subj = entries.find(
    (e) =>
      (e.iso2 ?? "").toLowerCase() === si || (iso2For(e.name) ?? "").toLowerCase() === si
  );
  if (!subj) return null;
  const a = (subj.analogs ?? []).find(
    (x) =>
      x.year === year &&
      ((x.country_iso2 ?? "").toLowerCase() === ai ||
        (iso2For(x.country) ?? "").toLowerCase() === ai)
  );
  if (!a) return null;

  const recipe = getRecipe(a.primary_recipe_id);
  let drivers: string[] = [];
  let windowYears = DEFAULT_WINDOW;
  const alignment = new Map<string, { mean: number[]; p25: number[]; p75: number[] }>();
  try {
    const card = loadCardV3(a.primary_recipe_id);
    drivers = card.greedy_walk?.selected_indicators ?? [];
    const cw = card.greedy_walk?.chosen_window;
    if (typeof cw === "number" && cw > 0) windowYears = cw;
    // The card's canonical per-indicator shape (mean + p25/p75) over its
    // alignment window. When present it sets the window length so the subject,
    // analogue, and canonical lines all share one x-axis.
    const ta = card.trajectory_alignment;
    if (ta) {
      if (typeof ta.window_years === "number" && ta.window_years > 0) {
        windowYears = ta.window_years;
      }
      for (const ind of ta.indicators ?? []) {
        if (ind?.code && ind.shape) alignment.set(ind.code, ind.shape);
      }
    }
  } catch {
    /* no card → header + whn only */
  }
  const fam = familyColor(recipe?.l1_id ?? "", recipe?.l1_color ?? "#9ab0c4");

  const overlays: DriverOverlay[] = [];
  for (const code of drivers) {
    const subjZ = zscoreFull(getIndicatorSeries(si, code));
    const analZ = zscoreFull(getIndicatorSeries(ai, code));
    const subjYears = Object.keys(subjZ).map(Number);
    const analYears = Object.keys(analZ).map(Number);
    if (subjYears.length === 0 || analYears.length === 0) continue;
    const subjEnd = Math.max(...subjYears); // subject's "today" = latest year present
    const sW = windowAligned(subjZ, subjEnd, windowYears);
    const aW = windowAligned(analZ, year, windowYears);
    if (countReal(sW) < 2 || countReal(aW) < 2) continue;
    const shape = alignment.get(code);
    const canon = (arr: number[] | undefined): number[] | null =>
      arr && arr.length === windowYears ? arr.map(zToDisplay) : null;
    overlays.push({
      code,
      name: getIndicatorLabel(code),
      subject: sW,
      analogue: aW,
      canonical: canon(shape?.mean),
      canonicalLo: canon(shape?.p25),
      canonicalHi: canon(shape?.p75),
    });
  }

  const whn = getWhatHappenedNextByIso(ai, year);
  return {
    subjectIso2: si,
    subjectName: subj.name,
    analogueIso2: ai,
    analogueName: a.country,
    analogueYear: year,
    recipeId: a.primary_recipe_id,
    trendLabel: recipe?.label ?? a.primary_recipe_id,
    familyColor: fam,
    matchScore: a.match_score <= 1 ? a.match_score * 100 : a.match_score,
    weak: !!a.weak_analog,
    windowYears,
    whatHappenedNext: whn?.blurb ?? null,
    sources: whn?.sources,
    drivers: overlays,
  };
}

/** All `{trio}` params for generateStaticParams (one per surfaced analogue). */
export function allAnaloguePairKeys(): { trio: string }[] {
  let entries;
  try {
    entries = loadAnalogs().entries;
  } catch {
    return [];
  }
  const keys: { trio: string }[] = [];
  for (const e of entries) {
    const si = (e.iso2 ?? "").toLowerCase();
    if (!si) continue;
    for (const a of (e.analogs ?? []).slice(0, 3)) {
      const ai = (a.country_iso2 ?? "").toLowerCase();
      if (!ai || !a.year) continue;
      keys.push({ trio: `${si}-${ai}-${a.year}` });
    }
  }
  return keys;
}

// analogueHref lives in the standalone `analogue-href` module (client-safe);
// re-exported here for server-side callers that already import this resolver.
export { analogueHref } from "@/lib/te-mock/analogue-href";
