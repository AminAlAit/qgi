"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { countrySlug } from "@/lib/slug";
import { formatDataThrough } from "@/lib/format-bake-date";
import type { PatternsMergedRow } from "@/lib/types";
import type {
  PatternWindowTier,
  PatternsInitialFilters,
} from "@/lib/patterns-initial-filters";
import { PatternTrajectoryCell } from "@/components/patterns/PatternTrajectoryCell";

/**
 * Merged Patterns list shell — Build PR #4 of 5 (A3 Family 4 merger brief).
 *
 * Brief: docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-13.md
 *   (Family 4 — Patterns)
 *
 * Scope of PR #4 (incremental over PR #1-3):
 *   - **Sparkline column** — 80×24px SVG per row, 7-point correlation
 *     trajectory deterministically seeded on row identity (preview data
 *     until ranking.json carries per-window trajectory series)
 *   - **Recipe-confidence dot** — small color-coded indicator per row
 *     (preview placeholder until ranking.json carries the column)
 *   - **Layout toggle** — rows ↔ grid switcher in the table header per
 *     brief lines 1116-1125. `rows` is the Yuki/Ingrid scan-optimised
 *     1100×90 default; `grid` is the Elif/Marcus 280×180 dense card.
 *
 * Carried over from PR #1-3:
 *   - Foreign Affairs hero + "What this doesn't mean" callout + Lloyd's
 *     banner + Preset chip strip + Facet rail + Tier-vocab strip + 5-col
 *     rows-layout table
 *
 * Deferred to PR #5 (founder-gated): cutover.
 * Deferred to follow-up PRs: ECharts trajectory chart on detail page,
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

const TIER_ORDER: Record<PatternWindowTier, number> = {
  "XL-win": 0,
  "L-win": 1,
  "M-win": 2,
  "S-win": 3,
};

type SortColumn =
  | "pattern_power_score"
  | "avg_correlation"
  | "pattern_length"
  | "window_tier";
type SortDir = "asc" | "desc";

function sortRows(
  rows: PatternsMergedRow[],
  col: SortColumn,
  dir: SortDir
): PatternsMergedRow[] {
  const arr = [...rows];
  const mul = dir === "asc" ? 1 : -1;
  switch (col) {
    case "pattern_power_score":
      arr.sort((a, b) => mul * (a.pattern_power_score - b.pattern_power_score));
      break;
    case "avg_correlation":
      arr.sort((a, b) => mul * (a.avg_correlation - b.avg_correlation));
      break;
    case "pattern_length":
      arr.sort((a, b) => mul * (a.pattern_length - b.pattern_length));
      break;
    case "window_tier":
      arr.sort((a, b) => mul * (TIER_ORDER[a.window_tier] - TIER_ORDER[b.window_tier]));
      break;
  }
  return arr;
}

const PRESET_CHIPS: ReadonlyArray<{
  id: string;
  label: string;
  tooltip: string;
}> = [
  {
    id: "currently-firing",
    label: "Currently firing",
    tooltip: "Patterns with a recent firing year (last 24 months).",
  },
  {
    id: "top-confidence",
    label: "Top confidence",
    tooltip:
      "Ranked by out-of-country discrimination score: the strictest validation gate.",
  },
  {
    id: "country-tier-shifts",
    label: "Country-tier shifts",
    tooltip:
      "Patterns associated with countries whose composite risk tier moved this quarter.",
  },
  {
    id: "recently-confirmed",
    label: "Recently confirmed",
    tooltip: "Patterns whose canonical analogue closed within the last 12 months.",
  },
];

export function PatternsMergedListClient({
  rows,
  tierCounts,
  uniquePairCount,
  yearRange,
  generatedDate,
  countryOptions,
  initialFilters,
  lockedRecipeSet,
}: {
  rows: PatternsMergedRow[];
  tierCounts: Record<PatternWindowTier, number>;
  uniquePairCount: number;
  yearRange: { first: number; last: number };
  generatedDate: string;
  /** Country names sorted by firing-frequency desc — PR #2 facet. */
  countryOptions: Array<{ name: string; count: number }>;
  /** #781 — URL-seeded initial filter state (server-resolved). Defaults
   *  to empty when the page is reached without query params. */
  initialFilters?: PatternsInitialFilters;
  /** #849 — LOCKed ML recipe set; forwarded to PatternTrajectoryCell to
   *  guard falsification anchor links. Non-LOCKed categories are plain text. */
  lockedRecipeSet?: ReadonlySet<string>;
}) {
  const [search, setSearch] = useState<string>(initialFilters?.search ?? "");
  const [tierFilter, setTierFilter] = useState<Set<PatternWindowTier>>(
    () => new Set(initialFilters?.tierFilter ?? [])
  );
  const [countryFilter, setCountryFilter] = useState<Set<string>>(
    () => new Set(initialFilters?.countryFilter ?? [])
  );
  const [activePreset, setActivePreset] = useState<string | null>(null);
  // #786(d) — initial sort state from URL `?sort=`/`?dir=`, falls back
  // to PPS-desc when the URL is silent.
  const [sortCol, setSortCol] = useState<SortColumn>(
    (initialFilters?.sortCol as SortColumn | undefined) ?? "pattern_power_score"
  );
  const [sortDir, setSortDir] = useState<SortDir>(
    (initialFilters?.sortDir as SortDir | undefined) ?? "desc"
  );
  const [vocabDismissed, setVocabDismissed] = useState(false);
  const [layout, setLayout] = useState<"rows" | "grid">("rows");

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (search) {
        const q = search.toLowerCase();
        if (
          !r.country_a.toLowerCase().includes(q) &&
          !r.country_b.toLowerCase().includes(q)
        ) {
          return false;
        }
      }
      if (tierFilter.size > 0 && !tierFilter.has(r.window_tier)) return false;
      if (countryFilter.size > 0) {
        // #786(a) — AND-intersect, not OR-union. A pair row matches only
        // when EVERY country in the filter is one of the row's two
        // countries. Editorial expectation per Karl (Eurasia R5), Helena
        // (Brookings R5), Mei-Lin (World Bank R5): selecting Turkiye +
        // Iran means "patterns where BOTH appear" — the analogue search,
        // not a country-browse fallback. Single-country degenerates to
        // OR (the lone country must appear on one side). 3+ countries
        // returns 0 rows by definition since each pair-row has 2 sides
        // — the empty state is the honest answer.
        for (const wanted of countryFilter) {
          if (r.country_a !== wanted && r.country_b !== wanted) {
            return false;
          }
        }
      }
      return true;
    });
  }, [rows, search, tierFilter, countryFilter]);

  const sorted = useMemo(
    () => sortRows(filtered, sortCol, sortDir),
    [filtered, sortCol, sortDir]
  );

  return (
    <div className="p-6 lg:p-8">
      {/* ============== Header ============== */}
      <div className="mb-5">
        <div
          className="text-[10px] tracking-widest uppercase mb-2"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          156 countries · 13 locked recipes · 60 years of data
        </div>
        <h1
          className="text-2xl font-semibold leading-snug max-w-[68ch]"
          style={{ color: "var(--qgi-text)" }}
        >
          Which economies walked the same path, and what happened next.
        </h1>
        <p
          className="text-xs mt-3 font-data tabular-nums"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          {rows.length} country pairs (best window per pair) · {uniquePairCount} total
          unique pairs in bake · windows covering {yearRange.first}–{yearRange.last}
        </p>
      </div>

      {/* ============== "What this doesn't mean" callout (REQUIRED) ============== */}
      <div
        role="note"
        aria-label="What this doesn't mean"
        className="mb-4 rounded-lg border p-4"
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
          <li>This is not a forecast for either country on its own.</li>
          <li>
            Shared trajectory is not causation — these economies walked similar paths, not
            the same one.
          </li>
        </ul>
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
          Patterns shown are output from QGI&apos;s pattern-matching pipeline. Pattern
          strength is a composite of correlation, persistence, and breadth — not a
          predictive probability. Window-tier labels (S-win / M-win / L-win / XL-win)
          reflect canonical pattern length only. Methodology and known limitations:{" "}
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

      {/* ============== Preset chip strip (V2-A tabs folded — URL-state stub) ============== */}
      <div
        role="group"
        aria-label="Quick presets"
        className="flex gap-2 flex-wrap mb-4 overflow-x-auto"
      >
        <span
          className="text-[9px] tracking-widest uppercase self-center"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Quick presets
        </span>
        {PRESET_CHIPS.map((c) => {
          const active = activePreset === c.id;
          return (
            <button
              key={c.id}
              onClick={() => setActivePreset(active ? null : c.id)}
              aria-pressed={active}
              title={c.tooltip}
              className="px-3 py-1.5 rounded-full text-[10px] tracking-wider uppercase font-data font-semibold border whitespace-nowrap transition-all"
              style={{
                backgroundColor: active ? "rgba(99, 102, 241, 0.15)" : "transparent",
                borderColor: active ? "rgba(99, 102, 241, 0.35)" : "var(--qgi-border)",
                color: active ? "#a5b4fc" : "var(--qgi-text-muted)",
              }}
            >
              {c.label}
            </button>
          );
        })}
        {activePreset && (
          <span
            className="text-[9px] tracking-widest uppercase self-center"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            (Preview — chip filter wire-up coming soon)
          </span>
        )}
      </div>

      {/* ============== Tier-vocabulary disclosure strip (PR #2) ============== */}
      {!vocabDismissed && (
        <TierVocabularyStrip onDismiss={() => setVocabDismissed(true)} />
      )}

      {/* ============== Body: 2-col layout (rail + main) — PR #2 ============== */}
      <div className="grid gap-x-5 grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)]">
        <FacetRail
          tierFilter={tierFilter}
          tierCounts={tierCounts}
          onToggleTier={(t) => {
            setTierFilter((prev) => {
              const next = new Set(prev);
              if (next.has(t)) next.delete(t);
              else next.add(t);
              return next;
            });
          }}
          countryOptions={countryOptions}
          countryFilter={countryFilter}
          onToggleCountry={(name) => {
            setCountryFilter((prev) => {
              const next = new Set(prev);
              if (next.has(name)) next.delete(name);
              else next.add(name);
              return next;
            });
          }}
          onClearAll={() => {
            setTierFilter(new Set());
            setCountryFilter(new Set());
          }}
        />

        <div className="min-w-0">
          {/* ============== Filter strip — PR #2 trimmed (rail owns the tier facet) ============== */}
          <div className="flex flex-col sm:flex-row gap-3 mb-4 items-stretch sm:items-center flex-wrap">
            {/* #741: replace aria-label with proper sr-only <label htmlFor>
                for WCAG 1.3.1 + 4.1.2. aria-label dropped to avoid
                double-announce per accname-1.2 §4.3. */}
            <label htmlFor="patterns-merged-search" className="sr-only">
              Search country pair
            </label>
            <input
              id="patterns-merged-search"
              type="text"
              placeholder="Search country pair..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="px-3 py-2 rounded-md border bg-transparent text-xs flex-1 min-w-0"
              style={{
                borderColor: "var(--qgi-border)",
                color: "var(--qgi-text)",
              }}
            />

            <div className="flex items-center gap-1">
              {/* #741: visible "Sort" span -> <label htmlFor> for click-to-focus.
                  aria-label removed from <select> to avoid double-announce. */}
              <label
                htmlFor="patterns-merged-sort"
                className="text-[9px] tracking-widest uppercase mr-1"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                Sort
              </label>
              <select
                id="patterns-merged-sort"
                value={sortCol}
                onChange={(e) => setSortCol(e.target.value as SortColumn)}
                className="px-2 py-1.5 rounded border bg-transparent text-[11px]"
                style={{
                  backgroundColor: "var(--qgi-surface)",
                  borderColor: "var(--qgi-border)",
                  color: "var(--qgi-text-muted)",
                }}
              >
                <option value="pattern_power_score">Pattern strength</option>
                <option value="avg_correlation">Correlation</option>
                <option value="pattern_length">Pattern length</option>
                <option value="window_tier">Window tier</option>
              </select>
              <button
                onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
                className="px-2 py-2 rounded border text-[10px] tracking-wider font-data"
                style={{
                  backgroundColor: "var(--qgi-surface)",
                  borderColor: "var(--qgi-border)",
                  color: "var(--qgi-text-muted)",
                  minWidth: 36,
                }}
                title={
                  sortDir === "asc"
                    ? "Ascending — click to flip to descending"
                    : "Descending — click to flip to ascending"
                }
                aria-label={
                  sortDir === "asc"
                    ? "Sort direction ascending; click to flip to descending"
                    : "Sort direction descending; click to flip to ascending"
                }
              >
                {sortDir === "asc" ? "↑" : "↓"}
              </button>
            </div>

            <span className="text-xs font-data" style={{ color: "var(--qgi-text-dim)" }}>
              Showing {sorted.length} of {rows.length}
            </span>
          </div>

          {/* ============== Table ============== */}
          {/* Layout toggle bar — PR #4 */}
          <div className="flex items-center justify-end mb-2 gap-1.5">
            <span
              className="text-[9px] tracking-widest uppercase mr-1"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Layout
            </span>
            <div
              role="radiogroup"
              aria-label="Layout"
              className="inline-flex rounded border overflow-hidden"
              style={{ borderColor: "var(--qgi-border)" }}
            >
              {(["rows", "grid"] as const).map((l) => {
                const active = layout === l;
                return (
                  <button
                    key={l}
                    role="radio"
                    aria-checked={active}
                    onClick={() => setLayout(l)}
                    className="px-2.5 py-1 text-[10px] tracking-wider uppercase font-data font-semibold transition-colors"
                    style={{
                      backgroundColor: active ? "var(--qgi-surface-2)" : "transparent",
                      color: active ? "var(--qgi-text)" : "var(--qgi-text-muted)",
                    }}
                  >
                    {l}
                  </button>
                );
              })}
            </div>
          </div>

          <div
            className="rounded-lg border overflow-hidden"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
            }}
          >
            {layout === "rows" && (
              <div
                className="hidden md:grid items-center px-4 py-2.5 text-[10px] tracking-widest uppercase gap-x-2"
                style={{
                  gridTemplateColumns: "2fr 80px 90px 100px 70px 240px 24px",
                  color: "var(--qgi-text-dim)",
                  borderBottom: "1px solid var(--qgi-border)",
                  backgroundColor: "var(--qgi-surface-2)",
                }}
              >
                <span>Country pair</span>
                <span>Window</span>
                <span className="text-right">Correlation</span>
                <span className="text-right">Strength</span>
                <span className="text-right">Length</span>
                <span>Trajectory</span>
                <span title="Recipe confidence indicator — preview">RC</span>
              </div>
            )}

            {sorted.length === 0 ? (
              <div
                className="text-center py-12 text-sm"
                role="status"
                aria-live="polite"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                <p className="mb-3">No patterns match these filters.</p>
                {(search || tierFilter.size > 0 || countryFilter.size > 0) && (
                  <button
                    onClick={() => {
                      setSearch("");
                      setTierFilter(new Set());
                      setCountryFilter(new Set());
                    }}
                    className="text-[10px] tracking-widest uppercase px-3 py-1.5 rounded border"
                    style={{
                      borderColor: "var(--qgi-border)",
                      color: "var(--qgi-text-muted)",
                    }}
                  >
                    Clear all filters →
                  </button>
                )}
              </div>
            ) : layout === "rows" ? (
              <ul className="divide-y" style={{ borderColor: "var(--qgi-border)" }}>
                {sorted.map((row, idx) => (
                  <PatternRowComponent
                    key={row.row_key}
                    row={row}
                    rank={idx + 1}
                    lockedRecipeSet={lockedRecipeSet}
                  />
                ))}
              </ul>
            ) : (
              <div
                className="p-3 grid gap-3"
                style={{
                  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                }}
              >
                {sorted.map((row, idx) => (
                  <PatternGridCard
                    key={row.row_key}
                    row={row}
                    rank={idx + 1}
                    lockedRecipeSet={lockedRecipeSet}
                  />
                ))}
              </div>
            )}
          </div>

          <p
            className="mt-3 text-[10px] tracking-widest uppercase text-center"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            V1.9.1 scoring · {formatDataThrough(generatedDate)} ·{" "}
            <Link href={"/methodology" as Route} className="underline underline-offset-2">
              Methodology →
            </Link>
          </p>
        </div>
        {/* /main column */}
      </div>
      {/* /2-col body */}
    </div>
  );
}

function buildDetailHref(row: PatternsMergedRow): Route {
  const aSlug = countrySlug(row.country_a) ?? row.country_a.toLowerCase();
  const bSlug = countrySlug(row.country_b) ?? row.country_b.toLowerCase();
  // PR #3 — /patterns/[slug] detail page is live. Slug shape
  // `{a-slug}-{b-slug}-{start_year_a}-{start_year_b}` matches
  // generateStaticParams. Both year fields are required to disambiguate
  // same-pair windows that share start_year_a — without start_year_b the
  // slug collides across 53 of 64 unique pairs in the current ranking.
  //
  // ⚠ Coupling note (Rank-4 dedupe, 2026-05-18): the list page now sends
  // only the highest-PPS window per pair to this href builder. Today's
  // generateStaticParams emits all windows so any one of them resolves;
  // after #718 ships the upstream bake fix, the "winning" window for a
  // pair may shift bake-to-bake — verify that change against
  // generateStaticParams to avoid silently rotating the slug to a non-
  // pre-rendered route. Follow-up tracked at qgi-aws-tf followup ticket.
  return `/patterns/${aSlug}-${bSlug}-${row.start_year_a}-${row.start_year_b}` as Route;
}

function PatternRowComponent({
  row,
  rank,
  lockedRecipeSet,
}: {
  row: PatternsMergedRow;
  rank: number;
  lockedRecipeSet?: ReadonlySet<string>;
}) {
  const meta = TIER_META[row.window_tier];
  const detailHref = buildDetailHref(row);
  return (
    <li>
      <Link
        href={detailHref}
        className="px-4 py-3 grid items-center gap-x-2 transition-colors hover:bg-[color:var(--qgi-surface-2)]"
        style={{
          gridTemplateColumns: "2fr 80px 90px 100px 70px 240px 24px",
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="text-[9px] tracking-widest uppercase font-data tabular-nums w-6"
            style={{
              color: rank <= 3 ? "rgba(245, 158, 11, 0.85)" : "var(--qgi-text-dim)",
            }}
          >
            #{rank}
          </span>
          <span
            className="text-xs font-medium truncate"
            style={{ color: "var(--qgi-text)" }}
            title={row.country_a}
          >
            {row.country_a}
          </span>
          <span
            className="text-[10px]"
            style={{ color: "var(--qgi-text-dim)" }}
            aria-hidden="true"
          >
            →
          </span>
          <span
            className="text-xs font-medium truncate"
            style={{ color: "var(--qgi-text)" }}
            title={row.country_b}
          >
            {row.country_b}
          </span>
          <span
            className="text-[10px] font-data tabular-nums whitespace-nowrap"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            {row.start_year_a}–{row.start_year_b}
          </span>
        </div>

        <div
          className="text-[10px] tracking-wider uppercase font-semibold font-data text-center px-2 py-1 rounded w-fit"
          title={meta.tooltip}
          style={{
            backgroundColor: meta.bg,
            color: meta.color,
            border: `1px solid ${meta.border}`,
          }}
        >
          {meta.label}
        </div>

        <div
          className="text-right text-sm font-data tabular-nums"
          style={{ color: "var(--qgi-text)" }}
          title={`Pearson correlation across ${row.num_indexes} shared indicators.`}
        >
          {(row.avg_correlation * 100).toFixed(1)}%
        </div>

        <div
          className="text-right text-sm font-data tabular-nums"
          style={{ color: "var(--qgi-text)" }}
          title="Pattern strength — composite ranking metric. Bake formula: average correlation × pattern length (years) × indicator count. NOT a probability, NOT a calibrated forecast — use as a sort key only. For sovereign-credit work, lean on the correlation coefficient and window length as the substantive inputs."
        >
          {row.pattern_power_score.toFixed(0)}
        </div>

        <div
          className="text-right text-sm font-data tabular-nums"
          style={{ color: "var(--qgi-text-muted)" }}
          title={`Pattern length in years (${row.pattern_length}-year window).`}
        >
          {row.pattern_length}y
        </div>

        {/* T1 (#59) — leader terminating event + follower arc position */}
        <PatternTrajectoryCell
          trajectory={row.trajectory}
          leaderCountry={row.country_a}
          lockedRecipeSet={lockedRecipeSet}
        />

        {/* Recipe-confidence dot — PR #4 preview placeholder */}
        <RciDot row={row} />
      </Link>
    </li>
  );
}

// ============================================================================
// PR #2 — Tier-vocabulary disclosure strip
// ----------------------------------------------------------------------------
// Per brief §1087-1098. The Patterns family carries 6 distinct tier
// systems; quick-reference here keeps the rest of the page from having
// to inline each rubric. Dismissible.
//
// TODO (cleanup PR before PR #5 cutover): brief §1089 calls for URL-state
// persistence on dismissal (`?vocab=0`). Currently dismissal is in-memory
// only — a page reload re-renders the strip. Wire `useSearchParams` /
// `useRouter` when the rail facets also migrate to URL-state.
// ============================================================================
function TierVocabularyStrip({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      role="note"
      aria-label="Tier vocabulary"
      className="mb-4 rounded-lg border p-3"
      style={{
        backgroundColor: "var(--qgi-surface)",
        borderColor: "var(--qgi-border)",
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <p
            className="text-[10px] tracking-widest uppercase font-semibold mb-2"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            This page uses 6 distinct tier systems · hover any badge for definition
          </p>
          <ul
            className="text-[11px] leading-relaxed grid gap-x-4 gap-y-1"
            style={{
              color: "var(--qgi-text-muted)",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            }}
          >
            <li>
              <span className="font-semibold">Pattern strength</span>: composite 0–2500
            </li>
            <li>
              <span className="font-semibold">Correlation tier</span>: Pearson |r|
              thresholds (S/A/B/C)
            </li>
            <li>
              <span className="font-semibold">Pattern window</span>: S-win / M-win / L-win
              / XL-win (canonical length)
            </li>
            <li>
              <span className="font-semibold">Evidence strength</span>: STRONG / MODERATE
              / MARGINAL (matches Precedents ML rung)
            </li>
            <li>
              <span className="font-semibold">Recipe Confidence Index</span>: GREEN /
              YELLOW / RED / INSUFFICIENT
            </li>
            <li>
              <span className="font-semibold">Country tier</span>: HIGH / MODERATE /
              INDICATIVE (matches Countries + Signals)
            </li>
          </ul>
        </div>
        <button
          onClick={onDismiss}
          aria-label="Dismiss tier vocabulary strip"
          className="text-[10px] tracking-widest uppercase px-2 py-1 rounded border whitespace-nowrap"
          style={{
            borderColor: "var(--qgi-border)",
            color: "var(--qgi-text-dim)",
          }}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

// ============================================================================
// PR #2 — Facet rail (220px persistent on lg+)
// ----------------------------------------------------------------------------
// Brief §1099-1114 lists 7 categorical facets + 1 slider group. PR #2
// surfaces 2 with REAL data (Window-tier + Country) and the remaining 5
// as preview-placeholder facets — chipped `Preview` until the ranking.json
// schema carries those columns.
// ============================================================================
function FacetRail({
  tierFilter,
  tierCounts,
  onToggleTier,
  countryOptions,
  countryFilter,
  onToggleCountry,
  onClearAll,
}: {
  tierFilter: Set<PatternWindowTier>;
  tierCounts: Record<PatternWindowTier, number>;
  onToggleTier: (t: PatternWindowTier) => void;
  countryOptions: Array<{ name: string; count: number }>;
  countryFilter: Set<string>;
  onToggleCountry: (name: string) => void;
  onClearAll: () => void;
}) {
  const [countrySearch, setCountrySearch] = useState("");
  const visibleCountries = useMemo(() => {
    const q = countrySearch.toLowerCase().trim();
    return q
      ? countryOptions.filter((c) => c.name.toLowerCase().includes(q))
      : countryOptions;
  }, [countryOptions, countrySearch]);
  const totalActive = tierFilter.size + countryFilter.size;

  return (
    <aside
      aria-label="Filter facets"
      className="rounded-lg border p-4 self-start lg:sticky lg:top-4"
      style={{
        backgroundColor: "var(--qgi-surface)",
        borderColor: "var(--qgi-border)",
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <h2
          className="text-[10px] tracking-widest uppercase font-semibold"
          style={{ color: "var(--qgi-text)" }}
        >
          Facets
        </h2>
        {totalActive > 0 && (
          <button
            onClick={onClearAll}
            className="text-[9px] tracking-widest uppercase px-2 py-0.5 rounded border"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-dim)",
            }}
          >
            Clear ({totalActive})
          </button>
        )}
      </div>

      {/* Architecture — preview placeholder per brief lineage-flagship position */}
      <FacetPlaceholder
        label="Architecture"
        tooltip="Lineage chip — D2 (level features) / D5 (trend features) / V1-statistical. Wires up when ranking.json schema carries the lineage column."
      />

      {/* Falsification status — NEW 5th-lineage per Marcus */}
      <FacetPlaceholder
        label="Falsification status"
        tooltip="Locked / Unlocked / Provisional — surfaces ML Stage 4 falsification rule status when bake lands."
      />

      {/* Window tier — REAL data, multi-select */}
      <FacetSection label="Window tier">
        <div role="group" aria-label="Window tier facet">
          {(["XL-win", "L-win", "M-win", "S-win"] as const).map((t) => {
            const active = tierFilter.has(t);
            const meta = TIER_META[t];
            return (
              <button
                key={t}
                onClick={() => onToggleTier(t)}
                aria-pressed={active}
                className="w-full flex items-center justify-between text-left px-2 py-1 mb-1 rounded text-[11px] transition-colors hover:bg-[color:var(--qgi-surface-2)]"
                style={{
                  backgroundColor: active ? meta.bg : "transparent",
                  border: `1px solid ${active ? meta.border : "transparent"}`,
                  color: active ? meta.color : "var(--qgi-text-muted)",
                }}
              >
                <span className="tracking-wider uppercase font-semibold font-data">
                  {meta.label}
                </span>
                <span className="text-[10px] opacity-70 font-data tabular-nums">
                  {tierCounts[t]}
                </span>
              </button>
            );
          })}
        </div>
      </FacetSection>

      {/* Country — REAL data, multi-select searchable */}
      <FacetSection label="Country">
        {/* #741: aria-label -> sr-only <label htmlFor> for WCAG 1.3.1 */}
        <label htmlFor="patterns-merged-country-search" className="sr-only">
          Search countries
        </label>
        <input
          id="patterns-merged-country-search"
          type="text"
          placeholder="Search…"
          value={countrySearch}
          onChange={(e) => setCountrySearch(e.target.value)}
          className="w-full mb-1.5 px-2 py-1 rounded border bg-transparent text-[11px]"
          style={{
            borderColor: "var(--qgi-border)",
            color: "var(--qgi-text)",
          }}
        />
        <div
          className="overflow-y-auto pr-1"
          style={{ maxHeight: 180 }}
          role="group"
          aria-label="Country facet"
        >
          {visibleCountries.slice(0, 50).map((c) => {
            const active = countryFilter.has(c.name);
            return (
              <button
                key={c.name}
                onClick={() => onToggleCountry(c.name)}
                aria-pressed={active}
                className="w-full flex items-center justify-between text-left px-2 py-1 rounded text-[11px] transition-colors hover:bg-[color:var(--qgi-surface-2)]"
                style={{
                  backgroundColor: active ? "rgba(99, 102, 241, 0.10)" : "transparent",
                  color: active ? "#a5b4fc" : "var(--qgi-text-muted)",
                }}
              >
                <span className="truncate" title={c.name}>
                  {c.name}
                </span>
                <span className="text-[10px] opacity-70 font-data tabular-nums">
                  {c.count}
                </span>
              </button>
            );
          })}
          {visibleCountries.length > 50 && (
            <p
              className="text-[10px] tracking-widest uppercase mt-1 px-2"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              + {visibleCountries.length - 50} more — refine search
            </p>
          )}
        </div>
      </FacetSection>

      {/* L1 / Region / RCI / Evidence-strength — preview placeholders */}
      <FacetPlaceholder
        label="L1 category"
        tooltip="Risk-domain group (governance / economy / security / trade / energy). Wires up when ranking.json carries the L1 column."
      />
      <FacetPlaceholder
        label="Evidence strength"
        tooltip="STRONG / MODERATE / MARGINAL — matches Precedents ML rung."
      />
      <FacetPlaceholder
        label="Recipe Confidence"
        tooltip="GREEN / YELLOW / RED / INSUFFICIENT — Recipe Confidence Index."
      />
      <FacetPlaceholder
        label="Region"
        tooltip="17 named regions. Wires up when ranking.json carries the region column."
      />
    </aside>
  );
}

function FacetSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3" style={{ borderTop: "1px solid var(--qgi-border)" }}>
      <h3
        className="text-[10px] tracking-widest uppercase font-semibold pt-2.5 pb-1.5"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        {label}
      </h3>
      {children}
    </div>
  );
}

function FacetPlaceholder({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <div
      className="mb-3 flex items-center justify-between"
      style={{ borderTop: "1px solid var(--qgi-border)" }}
      title={tooltip}
    >
      <h3
        className="text-[10px] tracking-widest uppercase font-semibold pt-2.5 pb-1.5"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        {label}
      </h3>
      <span
        className="text-[9px] tracking-widest uppercase px-1.5 py-0.5 rounded mt-1"
        style={{
          backgroundColor: "var(--qgi-surface-2)",
          color: "var(--qgi-text-dim)",
          border: "1px solid var(--qgi-border)",
        }}
      >
        Preview
      </span>
    </div>
  );
}

// ============================================================================
// Recipe-confidence dot placeholder — face-validity-debt cleanup (Dmitri R3)
// ----------------------------------------------------------------------------
// Same principle as the sparkline above: the prior dot was a seeded-color
// preview that read as "this row has a real RCI rung" to non-hovering users.
// Replaced with a neutral grey dot + clearer hover copy. Wires up to the
// real `rci` field when ranking.json carries it.
// ============================================================================
function RciDot({ row: _row }: { row: PatternsMergedRow }) {
  return (
    <span
      aria-label="Recipe confidence — bake pending"
      title="Recipe Confidence Index will populate when ranking.json carries the `rci` column. Held as a neutral placeholder rather than a seeded preview color, since colored dots read as real RCI rungs to non-hovering users."
      style={{
        display: "inline-block",
        width: 10,
        height: 10,
        borderRadius: 999,
        backgroundColor: "var(--qgi-surface-2)",
        border: "1px dashed var(--qgi-border)",
      }}
    />
  );
}

// ============================================================================
// PR #4 — Grid layout card
// ----------------------------------------------------------------------------
// V2-B-derived 5-zone density card (Elif/Marcus mode). Same data surfaces
// as the rows layout but compressed to ~280×180; sparkline mid-cell rather
// than as a separate column.
// ============================================================================
function PatternGridCard({
  row,
  rank,
  lockedRecipeSet,
}: {
  row: PatternsMergedRow;
  rank: number;
  lockedRecipeSet?: ReadonlySet<string>;
}) {
  const meta = TIER_META[row.window_tier];
  const detailHref = buildDetailHref(row);
  return (
    <Link
      href={detailHref}
      className="block rounded-lg border p-3 transition-colors hover:bg-[color:var(--qgi-surface-2)]"
      style={{
        backgroundColor: "var(--qgi-surface-2)",
        borderColor: "var(--qgi-border)",
      }}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0 flex-1">
          <div
            className="text-[9px] tracking-widest uppercase font-data tabular-nums mb-0.5"
            style={{
              color: rank <= 3 ? "rgba(245, 158, 11, 0.85)" : "var(--qgi-text-dim)",
            }}
          >
            #{rank}
          </div>
          <div
            className="text-sm font-medium leading-tight"
            style={{ color: "var(--qgi-text)" }}
          >
            {row.country_a}{" "}
            <span style={{ color: "var(--qgi-text-dim)" }} aria-hidden="true">
              →
            </span>{" "}
            {row.country_b}
          </div>
          <div
            className="text-[10px] font-data tabular-nums mt-0.5"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            {row.start_year_a}–{row.start_year_b} · {row.pattern_length}y
          </div>
        </div>
        <div className="flex items-start gap-1 shrink-0">
          <span
            className="text-[9px] tracking-wider uppercase font-semibold font-data text-center px-1.5 py-0.5 rounded"
            title={meta.tooltip}
            style={{
              backgroundColor: meta.bg,
              color: meta.color,
              border: `1px solid ${meta.border}`,
            }}
          >
            {meta.label}
          </span>
          <RciDot row={row} />
        </div>
      </div>

      {/* T1 (#59) — leader terminating event + follower arc position */}
      <div className="mb-2">
        <PatternTrajectoryCell
          trajectory={row.trajectory}
          leaderCountry={row.country_a}
          lockedRecipeSet={lockedRecipeSet}
        />
      </div>

      <div className="flex items-baseline justify-between gap-2 font-data tabular-nums">
        <div className="min-w-0">
          <div
            className="text-[9px] tracking-widest uppercase"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Correlation
          </div>
          <div className="text-sm font-semibold" style={{ color: "var(--qgi-text)" }}>
            {(row.avg_correlation * 100).toFixed(1)}%
          </div>
        </div>
        <div className="min-w-0 text-right">
          <div
            className="text-[9px] tracking-widest uppercase"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Power
          </div>
          <div className="text-sm font-semibold" style={{ color: "var(--qgi-text)" }}>
            {row.pattern_power_score.toFixed(0)}
          </div>
        </div>
      </div>
    </Link>
  );
}
