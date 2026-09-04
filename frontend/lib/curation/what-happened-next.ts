/**
 * what-happened-next — curated analogue outcome narratives.
 *
 * The backend (qgi-ml / curation) publishes `data/curation/what-happened-next.json`
 * as a growing flat map keyed by "<iso2>-<year>" (lowercase iso2, integer year),
 * each value a short, two-web-fact-checker-verified "what happened next" blurb
 * for that historical analogue.
 *
 * Key properties (see docs/specs/internal/ops/what-happened-next-frontend-ingest-2026-06-04.md):
 *   - RECIPE-AGNOSTIC: keyed by (country, year) only, so one lookup serves every
 *     surface (match page, country profile, Analogues). The same "cl-1973" blurb
 *     is correct for every analog that cites Chile-1973.
 *   - BATCHED: the file grows ~20% -> 100% over waves; a miss is normal mid-rollout
 *     and must render as the existing "coming soon" state, NEVER an error.
 *   - SERVER-ONLY: we join in the server data layer (countries / analogs / match
 *     builders) so the ~400KB map never ships to the client.
 *
 * No re-bake or schema change: the `what_happened_next` field stays null in the
 * scores/analogs files; we resolve from this join instead.
 */
import whnRaw from "@/data/curation/what-happened-next.json";
import { iso2For } from "@/lib/te-mock/country-flags";

export interface WhatHappenedNext {
  /** 1-2 sentence, ~25-55 word neutral narrative. */
  blurb: string;
  /** URLs the fact-checkers retrieved; safe to surface as citation links. */
  sources?: string[];
  /** "high" | "medium" — treat medium the same as high. */
  confidence?: string;
}

const WHN = whnRaw as Record<string, WhatHappenedNext>;

/** Look up by lowercase ISO-2 + year — the canonical join. */
export function getWhatHappenedNextByIso(
  iso2: string | null | undefined,
  year: number | null | undefined
): WhatHappenedNext | null {
  if (!iso2 || year == null) return null;
  return WHN[`${iso2.toLowerCase()}-${year}`] ?? null;
}

/** Look up by country name (resolves ISO-2 first) + year. */
export function getWhatHappenedNext(
  country: string | null | undefined,
  year: number | null | undefined
): WhatHappenedNext | null {
  if (!country || year == null) return null;
  return getWhatHappenedNextByIso(iso2For(country), year);
}

/**
 * Convenience used by the data layer: resolve the curated blurb for an analogue,
 * trying its ISO-2 first (present in the bake) and falling back to its name.
 * Returns null when not yet curated (caller keeps its existing "coming soon" UX).
 */
export function whnBlurb(
  iso2: string | null | undefined,
  country: string | null | undefined,
  year: number | null | undefined
): string | null {
  return (
    (getWhatHappenedNextByIso(iso2, year) ?? getWhatHappenedNext(country, year))?.blurb ??
    null
  );
}
