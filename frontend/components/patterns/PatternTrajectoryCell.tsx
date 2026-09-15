/**
 * T1 (#59) + T2 (#826) — Pattern trajectory cell rendered on /patterns list view.
 *
 * Replaces the prior `Sparkline` + "Trajectory pending" chip placeholder.
 * Three stacked lines per row (~52px total):
 *
 *   Line 1 (narrative):     "{LeaderCountry} window closed {year} · {Event title}"
 *   Line 2 (position):      "[████░░░░] Year {n} of {N}"
 *   Line 3 (falsification): "Falsifies if {Follower} sees no '{event}' by {Y±1}"
 *
 * Design synthesis of Ingrid (Cairo / narrative) + Elif (Tufte / inline-
 * density) Majles consults, 2026-05-19. Position bar styling = Elif's
 * minimum-mark recommendation (single accent tick on a neutral track).
 * Narrative copy template = Ingrid's "Cairo principle: answer the question
 * the reader is already forming."
 *
 * Missing-event state ("No verified event on record") is Ingrid's
 * honest framing — never says "pending" because the lookup has resolved
 * (negatively). When the terminating event is null, the falsification
 * line is also omitted (no anchor to falsify against) — never replaced
 * with a generic placeholder.
 *
 * T2 (#826) — founder-ratified template 2026-05-19:
 *   "If [follower] does not experience some form of '[category]' event
 *    by [end year ±1], this pattern is falsified."
 * Source: leader's terminating event category (no new authored data, no
 * hard thresholds; "some form of" framing intentionally leaves
 * interpretation to the reader / future evaluator).
 *
 * Phase C (editorial polish) is enabled via the `dataEditorial` flag on
 * the trajectory's terminatingEvent; when true, this cell will render
 * a 4px left accent border to mark editorial provenance. The data flow
 * for that is reserved here; no Phase C entries exist in the corpus yet.
 */
import Link from "next/link";
import type { Route } from "next";
import { countrySlug } from "@/lib/slug";
import type { PatternTrajectory } from "@/lib/pattern-trajectory";

interface Props {
  trajectory: PatternTrajectory;
  leaderCountry: string;
  /** #849 — guard: only render the falsification category as a <Link> when the
   *  category is in the LOCKed ML recipe set. Non-LOCKed categories produce
   *  404s because the signals leaf calls notFound() for unfired categories.
   *  When this prop is omitted (or empty), all categories render as plain text
   *  (safe default matching pre-#841 behaviour). */
  lockedRecipeSet?: ReadonlySet<string>;
}

/** Trim long verified-event titles to a scannable length (Ingrid: ≤10 words). */
function truncateTitle(title: string, maxChars = 56): string {
  if (title.length <= maxChars) return title;
  return `${title.slice(0, maxChars - 1).trimEnd()}…`;
}

export function PatternTrajectoryCell({
  trajectory,
  leaderCountry,
  lockedRecipeSet,
}: Props) {
  const {
    terminatingEvent,
    leaderEndYear,
    followerYearsElapsed,
    patternLength,
    falsificationAnchor,
  } = trajectory;
  const progressPct = patternLength > 0 ? followerYearsElapsed / patternLength : 0;
  const isEditorial = terminatingEvent?.dataEditorial ?? false;

  const narrativeLine = terminatingEvent
    ? `${leaderCountry} window closed ${terminatingEvent.year} · ${truncateTitle(terminatingEvent.title)}`
    : `${leaderCountry} window closes ~${leaderEndYear} · No verified event on record`;

  const positionLabel = `Year ${followerYearsElapsed} of ${patternLength}`;

  return (
    <div
      className="flex flex-col gap-1 min-w-0"
      style={
        isEditorial
          ? { borderLeft: "4px solid var(--qgi-accent)", paddingLeft: 6 }
          : undefined
      }
      data-event-id={terminatingEvent?.source ?? ""}
      data-editorial={isEditorial ? "true" : "false"}
    >
      <div
        className="text-[11px] leading-tight truncate"
        style={{
          color: terminatingEvent ? "var(--qgi-text)" : "var(--qgi-text-dim)",
          fontStyle: terminatingEvent ? "normal" : "italic",
        }}
        title={
          terminatingEvent
            ? `${terminatingEvent.title}: ${terminatingEvent.country}, ${terminatingEvent.year}. Source: ${terminatingEvent.source}`
            : `No event found in verified-events.json for ${leaderCountry} within ±2 years of ${leaderEndYear}.`
        }
      >
        {narrativeLine}
      </div>
      <div
        className="flex items-center gap-1.5"
        aria-label={positionLabel}
        title={`Follower is ${followerYearsElapsed} years into a ${patternLength}-year pattern.`}
      >
        <div
          role="presentation"
          className="relative h-[3px] flex-1 rounded-full overflow-hidden"
          style={{ backgroundColor: "var(--qgi-surface-2)" }}
        >
          <div
            className="absolute inset-y-0 left-0 rounded-full"
            style={{
              width: `${Math.round(progressPct * 100)}%`,
              backgroundColor: "var(--qgi-accent)",
            }}
          />
        </div>
        <span
          className="text-[9px] tracking-wider font-data tabular-nums whitespace-nowrap"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {positionLabel}
        </span>
      </div>
      {/* #831 (R8-W1redo-Priya-1): elapsed windows show honest "outcome not yet
          determined" copy instead of the stale forward-looking "Falsifies if …". */}
      {falsificationAnchor &&
        (falsificationAnchor.isWindowElapsed ? (
          <div
            className="text-[10px] leading-tight truncate italic"
            style={{ color: "var(--qgi-text-dim)" }}
            title={`The falsification window (${falsificationAnchor.windowStart}–${falsificationAnchor.windowEnd}) has passed. QGI has not yet determined the outcome for ${falsificationAnchor.followerCountry}.`}
          >
            {`Window elapsed ${falsificationAnchor.windowEnd}: outcome not yet determined by QGI`}
          </div>
        ) : (
          <div
            className="text-[10px] leading-tight truncate"
            style={{ color: "var(--qgi-text-muted)" }}
            title={`Falsification anchor: if ${falsificationAnchor.followerCountry} does not experience some form of ‘${falsificationAnchor.eventCategoryDisplay}’ event by ${falsificationAnchor.windowStart}–${falsificationAnchor.windowEnd}, this pattern is falsified.`}
          >
            <span style={{ color: "var(--qgi-text-dim)" }}>Falsifies if</span>{" "}
            {`${falsificationAnchor.followerCountry} sees no `}
            {/* #849 — only hyperlink when the category is in the LOCKed ML recipe
                set. Non-LOCKed categories 404 on the signals leaf (notFound() fires
                when byWindow.length === 0). Regression from #841 which wired the
                link unconditionally; 227 dead links audited in current ranking.json. */}
            {lockedRecipeSet?.has(falsificationAnchor.eventCategory) ? (
              <Link
                href={
                  `/signals/${countrySlug(falsificationAnchor.followerCountry) ?? falsificationAnchor.followerCountry.toLowerCase()}/${falsificationAnchor.eventCategory}` as Route
                }
                className="underline underline-offset-2 hover:text-[var(--qgi-accent)]"
              >
                &apos;{falsificationAnchor.eventCategoryDisplay}&apos;
              </Link>
            ) : (
              <span>&apos;{falsificationAnchor.eventCategoryDisplay}&apos;</span>
            )}
            {` by `}
            <span className="font-data tabular-nums">
              {falsificationAnchor.windowStart}&ndash;{falsificationAnchor.windowEnd}
            </span>
          </div>
        ))}
    </div>
  );
}
