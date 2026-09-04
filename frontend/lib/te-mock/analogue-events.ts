/**
 * analogue-events — joins a nearest-analogue (country, year, recipe) to the
 * real verified event that happened to that country, sourced from the same
 * `data/verified-events.json` corpus the /methodology/events table reads.
 *
 * Each verified event carries { country, year, title, category, source,
 * sourceDomain }. A recipe_id IS the event category (e.g. "terrorist_attack",
 * "civil_war_and_insurgency"), so the join is:
 *
 *   analogue(country, year) under recipe R
 *      -> the verified event where category === R, country matches, and the
 *         event year is closest to the analogue year (within a small window).
 *
 * The analogue year is the eval-year of that historical state — for a positive
 * case the 12-quarter window ends at the event, so the matching event sits at
 * (or within a year or two of) the analogue year. ~94% of fleet-run-1 analogues
 * resolve to a real event this way; the rest carry no event of that kind near
 * that year and honestly show nothing.
 */
import rawVerifiedEvents from "@/data/verified-events.json";

export interface AnalogueEvent {
  title: string;
  year: number;
  /** Public source URL, or null when the row has no source. */
  source: string | null;
  /** Display domain for the source (e.g. "wikipedia.org"), or null. */
  sourceDomain: string | null;
}

interface VerifiedEventRow {
  country: string;
  year: number;
  title: string;
  category: string;
  source: string | null;
  sourceDomain: string | null;
}

/** lowercase, strip diacritics, drop non-alphanumerics — robust name key. */
function norm(s: string): string {
  return (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "");
}

// Index built once at module load: `${normCountry}::${category}` -> rows.
let INDEX: Map<string, VerifiedEventRow[]> | null = null;

function getIndex(): Map<string, VerifiedEventRow[]> {
  if (INDEX) return INDEX;
  const idx = new Map<string, VerifiedEventRow[]>();
  for (const e of rawVerifiedEvents as unknown as VerifiedEventRow[]) {
    if (!e || !e.country || !e.category) continue;
    const key = `${norm(e.country)}::${e.category}`;
    const bucket = idx.get(key);
    if (bucket) bucket.push(e);
    else idx.set(key, [e]);
  }
  INDEX = idx;
  return idx;
}

/**
 * Find the verified event that happened to `country` around `year` under the
 * given recipe. Returns null when no event of that category sits within
 * `windowYears` of the analogue year.
 */
export function findAnalogueEvent(
  country: string,
  year: number,
  recipeId: string,
  windowYears = 2
): AnalogueEvent | null {
  const list = getIndex().get(`${norm(country)}::${recipeId}`);
  if (!list || list.length === 0) return null;

  let best: VerifiedEventRow | null = null;
  let bestDist = Infinity;
  for (const e of list) {
    const dist = Math.abs(e.year - year);
    // Closest year wins; ties break toward the event at or after the analogue
    // year (the one the analogue is genuinely "running up to").
    if (
      dist < bestDist ||
      (dist === bestDist && best != null && e.year >= year && best.year < year)
    ) {
      bestDist = dist;
      best = e;
    }
  }
  if (!best || bestDist > windowYears) return null;
  return {
    title: best.title,
    year: best.year,
    source: best.source ?? null,
    sourceDomain: best.sourceDomain ?? null,
  };
}
