/**
 * T1 (#59) — Pattern trajectory enrichment.
 *
 * For each pattern pair on /patterns, compute:
 *   - the LEADER's terminating event (real-world event from
 *     verified-events.json closest to end_year_a)
 *   - the FOLLOWER's current position within its projected arc
 *
 * The "terminating event" is the 4th of the 5 recipe components per the
 * QGI Methodology Charter (`docs/specs/internal/methodology-charter.md`):
 *   "what the recipe leads to (the precedent's outcome)."
 *
 * R7 personas (all 5 independently) asked for this on /patterns. EIC's
 * estimate: shipping this moves 2 of 5 R7 stories from B-grade to A-grade.
 *
 * This is Phase B (algorithmic) of the founder-ratified B-then-C plan:
 *   B = derive from verified-events.json (this file)
 *   C = layer hand-authored editorial polish per pair (future, opt-in via
 *       the `data_editorial` flag reserved on TerminatingEvent)
 */
import type { PatternRow } from "@/lib/types";

/** Raw record shape in `data/verified-events.json`. */
export interface VerifiedEvent {
  country: string;
  year: number;
  title: string;
  category: string;
  source: string;
  sourceDomain?: string;
}

export interface TerminatingEvent {
  country: string;
  year: number;
  title: string;
  category: string;
  source: string;
  /** Reserved for Phase C — hand-authored gloss overrides `title`. */
  editorialTitle?: string;
  /** True when sourced from `qgi-data` editorial overrides instead of the
   *  algorithmic verified-events.json lookup. Default false (Phase B). */
  dataEditorial: boolean;
}

/** snake_case → "Title Case With Spaces" for display. */
function displayifyCategory(slug: string): string {
  return slug.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * T2 (#826) — Forward-looking falsification anchor for the FOLLOWER.
 *
 * Founder template (2026-05-19): "If [follower] does not experience some
 * form of '[event category]' event by [followerEndYear ±1 year], this
 * pattern is falsified."
 *
 * Source of `eventCategory`: the LEADER's terminating event category from
 * the same verified-events lookup T1 already does. No new authored content,
 * no recipe-level static fields. Null when there's no terminating event
 * to anchor on — the cell omits the falsification line in that case
 * rather than fabricating a generic recipe-name placeholder.
 *
 * The "±1 year" tolerance + "some form of" framing intentionally avoids
 * hard thresholds (per founder direction). Whether a specific real-world
 * event qualifies as "some form of civil_war_and_insurgency" is left to
 * the reader / future evaluator — not encoded in this lib.
 *
 * #831 (R8-W1redo-Priya-1): `isWindowElapsed` is true when the
 * falsification window has already passed (windowEnd < currentYear).
 * PatternTrajectoryCell uses this to suppress the forward-looking
 * "Falsifies if ..." copy and show an honest elapsed-state message.
 */
export interface FalsificationAnchor {
  followerCountry: string;
  /** Raw event-category slug from the leader's terminating event. */
  eventCategory: string;
  /** snake_case → "Title Case With Spaces" for display. */
  eventCategoryDisplay: string;
  /** followerEndYear - 1. */
  windowStart: number;
  /** followerEndYear + 1. */
  windowEnd: number;
  /** #831 — true when windowEnd < currentYear (window is in the past). */
  isWindowElapsed: boolean;
}

export interface PatternTrajectory {
  /** Leader's projected window-close year (start_year_a + pattern_length). */
  leaderEndYear: number;
  /** Closest event to leaderEndYear for country_a, or null when none in tolerance. */
  terminatingEvent: TerminatingEvent | null;
  /** Follower's projected window-close year. */
  followerEndYear: number;
  /** Years elapsed in follower's arc (clamped 0..pattern_length). */
  followerYearsElapsed: number;
  /** Pattern length, surfaced for cell render convenience. */
  patternLength: number;
  /** T2 (#826) — forward falsification anchor for the follower. Null when
   *  no terminating event is available to anchor on. */
  falsificationAnchor: FalsificationAnchor | null;
}

/**
 * Tolerance in years for the leader-end event lookup. Wider than ±1 to
 * accommodate slightly-off bake timing and event-corpus year granularity;
 * narrower than ±5 to avoid claiming unrelated events as "terminating."
 * Ingrid's design recommendation: ±2.
 */
export const EVENT_LOOKUP_TOLERANCE_YEARS = 2;

/**
 * Find the most relevant event for `country` near `targetYear`.
 *
 * Selection rule:
 *   1. Filter to events on this country within ±EVENT_LOOKUP_TOLERANCE_YEARS
 *   2. Among those, prefer the one with the smallest |year - targetYear|
 *   3. Ties broken by lexicographic title (deterministic; events at the
 *      same year + same country should be rare).
 *
 * Returns null when nothing in tolerance. We do NOT fabricate "soft" matches
 * from outside the tolerance — Ingrid's missing-data state ("No verified
 * event on record") is the honest answer.
 */
export function findTerminatingEvent(
  country: string,
  targetYear: number,
  events: ReadonlyArray<VerifiedEvent>
): TerminatingEvent | null {
  const lowerCountry = country.toLowerCase();
  let best: VerifiedEvent | null = null;
  let bestDistance = Infinity;
  for (const ev of events) {
    if (ev.country.toLowerCase() !== lowerCountry) continue;
    const distance = Math.abs(ev.year - targetYear);
    if (distance > EVENT_LOOKUP_TOLERANCE_YEARS) continue;
    if (
      distance < bestDistance ||
      (distance === bestDistance &&
        best !== null &&
        ev.title.localeCompare(best.title) < 0)
    ) {
      best = ev;
      bestDistance = distance;
    }
  }
  if (!best) return null;
  return {
    country: best.country,
    year: best.year,
    title: best.title,
    category: best.category,
    source: best.source,
    dataEditorial: false,
  };
}

/**
 * Compute the full trajectory for a pattern row given the events corpus
 * and a reference "current year" (parameterized for test determinism).
 *
 * Direction convention: country_a = LEADER (analogue, completed arc),
 * country_b = FOLLOWER (live case). Confirmed by Ingrid 2026-05-19.
 *
 * Note: country_a is the 'leader' by ranking.json convention, but if
 * `start_year_b < start_year_a` the chronological leader is country_b.
 * See ticket #839 — UI may want to swap labels for that case; the data
 * convention here doesn't change.
 */
export function computePatternTrajectory(
  row: Pick<
    PatternRow,
    "country_a" | "country_b" | "start_year_a" | "start_year_b" | "pattern_length"
  >,
  events: ReadonlyArray<VerifiedEvent>,
  currentYear: number = new Date().getFullYear()
): PatternTrajectory {
  const leaderEndYear = row.start_year_a + row.pattern_length;
  const followerEndYear = row.start_year_b + row.pattern_length;
  const followerYearsElapsed = Math.max(
    0,
    Math.min(row.pattern_length, currentYear - row.start_year_b)
  );
  const terminatingEvent = findTerminatingEvent(row.country_a, leaderEndYear, events);
  // #831 (R8-W1redo-Priya-1): mark anchor as elapsed when its window is in the past.
  const falsificationAnchor: FalsificationAnchor | null = terminatingEvent
    ? {
        followerCountry: row.country_b,
        eventCategory: terminatingEvent.category,
        eventCategoryDisplay: displayifyCategory(terminatingEvent.category),
        windowStart: followerEndYear - 1,
        windowEnd: followerEndYear + 1,
        isWindowElapsed: followerEndYear + 1 < currentYear,
      }
    : null;
  return {
    leaderEndYear,
    terminatingEvent,
    followerEndYear,
    followerYearsElapsed,
    patternLength: row.pattern_length,
    falsificationAnchor,
  };
}
