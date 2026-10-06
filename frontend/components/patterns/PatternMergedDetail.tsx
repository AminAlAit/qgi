import Link from "next/link";
import type { Route } from "next";
import type { PatternRow } from "@/lib/types";
import type { PatternWindowTier } from "@/lib/patterns-initial-filters";
import type { PatternTrajectory } from "@/lib/pattern-trajectory";
import { PatternTrajectoryCell } from "@/components/patterns/PatternTrajectoryCell";
import { formatDataThrough } from "@/lib/format-bake-date";
import { PatternScdiPager } from "@/components/patterns/PatternScdiPager";

/**
 * Merged Patterns per-pattern detail — Build PR #3 of 5 (A3 Family 4).
 *
 * Brief: docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-13.md
 *   (Family 4 — Patterns / detail page composition)
 *
 * Server component — no client interactivity beyond `<Link>` navigation.
 * Sections rendered (Tufte-minimal — full 11-section spec deferred):
 *   - Breadcrumb (Home / Patterns / {pair})
 *   - Hero: eyebrow + h1 "{a} → {b}" + chip cluster
 *   - Lloyd's methodology disclosure banner
 *   - Section 1 "What's the claim" Ingrid 90-110w 3-movement lede
 *   - Section 2 "What this doesn't mean" 3-bullet callout (REQUIRED)
 *   - Section 3 — Signal summary 8-stat strip (REAL columns where data
 *     exists, Preview-chipped columns for ML lineage placeholders)
 *   - Cross-family handoffs footer
 *   - Page footer with V1.9.1 scoring tag
 *
 * Deferred to PR #4: ECharts trajectory chart, RCI prose dossier,
 * mechanism narrative band, historical analogues table, coverage bias
 * diagnostic, recipe-switcher, methodology cross-ref.
 */

const TIER_META: Record<
  PatternWindowTier,
  { label: string; color: string; bg: string; border: string; tooltip: string }
> = {
  "XL-win": {
    label: "XL-win",
    color: "#a78bfa",
    bg: "rgba(167, 139, 250, 0.10)",
    border: "rgba(167, 139, 250, 0.35)",
    tooltip:
      "XL window. Pattern canonical_length > 40 years; longest-horizon trajectory comparisons.",
  },
  "L-win": {
    label: "L-win",
    color: "#38bdf8",
    bg: "rgba(56, 189, 248, 0.10)",
    border: "rgba(56, 189, 248, 0.35)",
    tooltip:
      "L window. Pattern canonical_length 21–40 years; multi-decade structural comparisons.",
  },
  "M-win": {
    label: "M-win",
    color: "#22c55e",
    bg: "rgba(34, 197, 94, 0.10)",
    border: "rgba(34, 197, 94, 0.35)",
    tooltip:
      "M window. Pattern canonical_length 9–20 years; medium-horizon trajectory comparisons.",
  },
  "S-win": {
    label: "S-win",
    color: "#fbbf24",
    bg: "rgba(251, 191, 36, 0.10)",
    border: "rgba(251, 191, 36, 0.35)",
    tooltip:
      "S window. Pattern canonical_length ≤ 8 years; short-horizon trajectory comparisons.",
  },
};

export function PatternMergedDetail({
  row,
  tier,
  aSlug,
  bSlug,
  generatedDate,
  trajectory,
  lockedRecipeSet,
}: {
  row: PatternRow;
  tier: PatternWindowTier;
  aSlug: string;
  bSlug: string;
  generatedDate: string;
  /** #840 — trajectory narrative (terminating event, arc position, falsification anchor). */
  trajectory?: PatternTrajectory;
  /** #849 — LOCKed ML recipe set; forwarded to PatternTrajectoryCell for
   *  falsification anchor link guard. */
  lockedRecipeSet?: ReadonlySet<string>;
}) {
  const meta = TIER_META[tier];
  const ledeText = buildLedeText({ row, tier });

  return (
    <div className="p-6 lg:p-8">
      {/* ============== Breadcrumb ============== */}
      <nav
        aria-label="Breadcrumb"
        className="text-[10px] tracking-widest uppercase mb-3"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        <Link
          href={"/" as Route}
          className="hover:underline"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Home
        </Link>
        <span className="mx-1.5">/</span>
        <Link
          href={"/patterns" as Route}
          className="hover:underline"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Patterns
        </Link>
        <span className="mx-1.5">/</span>
        <span style={{ color: "var(--qgi-text-muted)" }}>
          {row.country_a} → {row.country_b}
        </span>
      </nav>

      {/* ============== Hero ============== */}
      <div className="mb-5">
        <div
          className="text-[10px] tracking-widest uppercase mb-1"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Pattern · {row.pattern_length}-year window
        </div>
        <h1
          className="text-3xl font-semibold leading-snug mb-1"
          style={{ color: "var(--qgi-text)" }}
        >
          {row.country_a}{" "}
          <span style={{ color: "var(--qgi-text-dim)" }} aria-hidden="true">
            →
          </span>{" "}
          {row.country_b}
        </h1>
        {/* #839 — when country_b started before country_a, the arrow convention
            (country_a → country_b) conflicts with chronological precedence.
            Show a one-line annotation so readers aren't misled. */}
        {row.start_year_b < row.start_year_a && (
          <p className="text-[11px] mb-3 italic" style={{ color: "var(--qgi-text-dim)" }}>
            Follower: {row.country_a} (started {row.start_year_a},{" "}
            {row.start_year_a - row.start_year_b}{" "}
            {row.start_year_a - row.start_year_b === 1 ? "year" : "years"} after{" "}
            {row.country_b})
          </p>
        )}
        {row.start_year_b >= row.start_year_a && <div className="mb-3" />}
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            [Verified data]
          </span>
          <span
            className="text-[10px] tracking-wider uppercase font-semibold font-data px-2 py-1 rounded"
            title={meta.tooltip}
            style={{
              backgroundColor: meta.bg,
              color: meta.color,
              border: `1px solid ${meta.border}`,
            }}
          >
            {meta.label}
          </span>
          <span
            className="text-[10px] tracking-widest uppercase font-semibold font-data px-2 py-0.5 rounded"
            title="Architecture lineage: D2 (level features) / D5 (trend features) / V1-statistical. Wires up when ranking.json carries the lineage column."
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-dim)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            Architecture · Preview
          </span>
          <span
            className="text-[10px] tracking-widest uppercase font-semibold font-data px-2 py-0.5 rounded"
            title="Recipe confidence rung: GREEN, YELLOW, RED, or insufficient. Surfaces when the pipeline stack carries the column."
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-dim)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            Recipe Confidence · Preview
          </span>
          {row.predicted && (
            <span
              className="text-[10px] tracking-widest uppercase font-semibold font-data px-2 py-0.5 rounded"
              title="This pattern window's trailing segment includes predicted (not observed) data per Decision D4 (±15%)."
              style={{
                backgroundColor: "rgba(251, 191, 36, 0.10)",
                color: "#fbbf24",
                border: "1px solid rgba(251, 191, 36, 0.35)",
              }}
            >
              Contains predicted
            </span>
          )}
        </div>
      </div>

      {/* ============== Lloyd's methodology disclosure banner ============== */}
      <div
        role="note"
        aria-label="Methodology disclosure"
        className="mb-5 rounded-lg border p-4"
        style={{
          backgroundColor: "rgba(245, 158, 11, 0.06)",
          borderColor: "rgba(245, 158, 11, 0.25)",
          borderLeftWidth: 2,
          borderLeftStyle: "solid",
          borderLeftColor: "rgba(245, 158, 11, 0.6)",
          color: "var(--qgi-text-muted)",
        }}
      >
        <span
          className="font-semibold tracking-wide uppercase text-[10px] mr-2 block mb-1"
          style={{ color: "rgba(245, 158, 11, 0.95)" }}
        >
          Methodology disclosure
        </span>
        <p className="text-xs leading-relaxed max-w-[68ch]">
          This page reports output from QGI&apos;s pattern-matching pipeline. Pattern
          Power Score is a composite of correlation strength, persistence, and breadth,
          not a predictive probability. The pair&apos;s shared trajectory is a statistical
          comparison against historical precedent. Methodology and known limitations:{" "}
          <Link
            href={"/methodology" as Route}
            className="underline underline-offset-2"
            style={{ color: "var(--qgi-text)" }}
          >
            /methodology
          </Link>
          .
        </p>
      </div>

      {/* ============== Section 1 — "What's the claim" Ingrid lede ============== */}
      <section
        aria-labelledby="lede-heading"
        className="mb-5 rounded-lg border p-5"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <div className="flex items-center gap-2 mb-2">
          <h2
            id="lede-heading"
            className="text-xs tracking-widest uppercase font-semibold"
            style={{ color: "var(--qgi-text)" }}
          >
            What&apos;s the claim
          </h2>
          <span
            className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            [Preview template]
          </span>
        </div>
        <p
          className="text-sm leading-relaxed max-w-[68ch]"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {ledeText}
        </p>
      </section>

      {/* ============== Trajectory section (#840) ============== */}
      {trajectory && (
        <section className="mb-5">
          <h2
            className="text-sm font-semibold mb-3"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Trajectory
          </h2>
          <div
            className="rounded-lg border p-4"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            <PatternTrajectoryCell
              trajectory={trajectory}
              leaderCountry={row.country_a}
              lockedRecipeSet={lockedRecipeSet}
            />
          </div>
        </section>
      )}

      {/* ============== Section 2 — "What this doesn't mean" callout (REQUIRED) ============== */}
      <div
        role="note"
        aria-label="What this doesn't mean"
        className="mb-5 rounded-lg border p-4"
        style={{
          backgroundColor: "rgba(251, 191, 36, 0.06)",
          borderColor: "rgba(251, 191, 36, 0.25)",
          borderLeftWidth: 2,
          borderLeftStyle: "solid",
          borderLeftColor: "rgba(251, 191, 36, 0.6)",
          color: "var(--qgi-text-muted)",
        }}
      >
        <div className="flex items-center gap-2 mb-2">
          <span
            className="font-semibold tracking-wide uppercase text-[10px]"
            style={{ color: "rgba(251, 191, 36, 0.95)" }}
          >
            What this doesn&apos;t mean
          </span>
          <span
            className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            [Worked example]
          </span>
        </div>
        <ul
          className="text-xs leading-relaxed space-y-1 list-disc pl-5 max-w-[68ch]"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          <li>This is not a prediction of when the next case will occur.</li>
          <li>
            This is not a forecast for {row.country_a} or {row.country_b} on its own.
          </li>
          <li>
            Shared trajectory is not causation; these economies walked similar paths, not
            the same one.
          </li>
        </ul>
      </div>

      {/* ============== Section 3 — Signal summary 8-stat strip ============== */}
      <section
        aria-labelledby="stats-heading"
        className="mb-5 rounded-lg border p-5"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <div className="flex items-center gap-2 mb-3">
          <h2
            id="stats-heading"
            className="text-xs tracking-widest uppercase font-semibold"
            style={{ color: "var(--qgi-text)" }}
          >
            Signal summary
          </h2>
          <span
            className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            [Verified data]
          </span>
        </div>
        <div
          className="grid gap-x-6 gap-y-3"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}
        >
          <StatCell
            label="Correlation"
            value={`${(row.avg_correlation * 100).toFixed(1)}%`}
            tooltip={`Pearson |r| averaged across ${row.num_indexes} shared indicators.`}
          />
          <StatCell
            label="Pattern strength"
            value={row.pattern_power_score.toFixed(0)}
            tooltip="Pattern strength: composite of correlation, persistence, and breadth. Not a predictive probability."
          />
          <StatCell
            label="Length"
            value={`${row.pattern_length} y`}
            tooltip={`Pattern canonical_length: ${row.pattern_length}-year window.`}
          />
          <StatCell
            label="Shared indicators"
            value={String(row.num_indexes)}
            tooltip={`Number of indicators where ${row.country_a} and ${row.country_b} co-moved within window.`}
          />
          <StatCell
            label={`${row.country_a} start`}
            value={String(row.start_year_a)}
            tooltip={`First year of the window for ${row.country_a}.`}
          />
          <StatCell
            label={`${row.country_b} start`}
            value={String(row.start_year_b)}
            tooltip={`First year of the window for ${row.country_b}.`}
          />
          <StatCell
            label="Discrimination"
            value="—"
            preview
            tooltip="Out-of-country discrimination score (LOCO-style). Wires up when ranking.json carries the ML stack column."
          />
          <StatCell
            label="Calibration"
            value="—"
            preview
            tooltip="Calibration band (Well-calibrated / gap / drift). Wires up when ranking.json carries the calibration column."
          />
        </div>
      </section>

      {/* ============== Section 4 — SCDI panels (paginated, 4 per page) ============== */}
      {row.country_a_id != null && row.country_b_id != null && (
        <PatternScdiPager
          country_a_id={row.country_a_id}
          country_b_id={row.country_b_id}
          start_year_a={row.start_year_a}
          start_year_b={row.start_year_b}
          length={row.pattern_length}
          countryAName={row.country_a}
          countryBName={row.country_b}
        />
      )}

      {/* ============== Cross-family handoffs footer ============== */}
      <section
        aria-label="Related pages"
        className="rounded-lg border p-4 mb-3"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <h2
          className="text-[10px] tracking-widest uppercase font-semibold mb-2"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Continue exploring
        </h2>
        <div className="flex flex-wrap gap-2">
          <Link
            href={"/patterns" as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            ← All patterns
          </Link>
          <Link
            href={`/countries/${aSlug}` as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            {row.country_a} country profile →
          </Link>
          <Link
            href={`/countries/${bSlug}` as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            {row.country_b} country profile →
          </Link>
          <Link
            href={`/countries/aSlug}` as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            What&apos;s firing on {row.country_a} →
          </Link>
          <Link
            href={`/countries/bSlug}` as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            What&apos;s firing on {row.country_b} →
          </Link>
          <Link
            href={"/trends" as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            Historical precedents →
          </Link>
        </div>
      </section>

      <p
        className="text-[10px] tracking-widest uppercase text-center"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        V1.9.1 scoring · {formatDataThrough(generatedDate)} ·{" "}
        <Link href={"/methodology" as Route} className="underline underline-offset-2">
          Methodology →
        </Link>
      </p>
    </div>
  );
}

function StatCell({
  label,
  value,
  tooltip,
  preview,
}: {
  label: string;
  value: string;
  tooltip?: string;
  preview?: boolean;
}) {
  return (
    <div className="min-w-0" title={tooltip}>
      <div
        className="text-[9px] tracking-widest uppercase mb-0.5 flex items-center gap-1"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        <span>{label}</span>
        {preview && (
          <span
            className="text-[8px] font-normal normal-case tracking-normal px-1 py-0.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-dim)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            Preview
          </span>
        )}
      </div>
      <div
        className="text-base font-data tabular-nums font-semibold truncate"
        style={{ color: preview ? "var(--qgi-text-dim)" : "var(--qgi-text)" }}
      >
        {value}
      </div>
    </div>
  );
}

// ============================================================================
// Ingrid lede — 3-movement template
// ----------------------------------------------------------------------------
// Movement 1: the claim (window + indicators + correlation)
// Movement 2: status + caveat (window-tier + Architecture preview)
// Movement 3: what to read next (cross-family handoff teaser)
// ============================================================================
function buildLedeText({
  row,
  tier,
}: {
  row: PatternRow;
  tier: PatternWindowTier;
}): string {
  const corrPct = (row.avg_correlation * 100).toFixed(1);
  const yearGap = row.start_year_a - row.start_year_b;
  const orderingPhrase =
    yearGap > 0
      ? `${row.country_b} preceded ${row.country_a} by ${yearGap} ${yearGap === 1 ? "year" : "years"} on the shared trajectory`
      : yearGap < 0
        ? `${row.country_a} preceded ${row.country_b} by ${Math.abs(yearGap)} ${Math.abs(yearGap) === 1 ? "year" : "years"} on the shared trajectory`
        : `${row.country_a} and ${row.country_b} walked the same trajectory in the same start year`;

  // #851 — replace internal engineering phrase "ranking schema upgrade" with
  // user-facing copy. The phrase appeared on every one of the 9 pattern detail
  // pages and was flagged by two W3 personas as trust-breaking jargon.
  return `${orderingPhrase}, across a ${row.pattern_length}-year window covering ${row.num_indexes} shared indicators. Average correlation: ${corrPct}%. The pattern carries a ${tier} window-tier label; Architecture lineage data is not yet available in this bake and will populate when the pattern database is updated. Read the country profiles for either side of the pair below, or jump to historical precedents for the closest analogues. This page reports model output reviewed for editorial release, not a probabilistic forecast of recurrence.`;
}
