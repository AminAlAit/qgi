"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { CountryFlag } from "@/components/design/CountryFlag";
import { countrySlug } from "@/lib/slug";
import { L1_GROUPS } from "@/lib/category-taxonomy";
import type { SignalRow, SignalTier } from "@/lib/signals-types";

/**
 * Merged Signals list shell — Build PR #2 of 5 (A3 Family 3 merger brief).
 *
 * Brief: docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-13.md
 *   (Family 3 — Signals)
 *
 * Scope of PR #2 (incremental over PR #1):
 *   - "5 firing now" curated band pinned above the filter strip with
 *     Sipho's `[Editor's pick · week of {date}]` label
 *   - 8-domain activation strip rendered above the table — one chip per
 *     L1 with categories-firing + countries-firing counts
 *
 * Carried over from PR #1:
 *   - H1 "Signals" + eyebrow "Currently firing — {date}" + 1-line metric
 *     strip (live tier counts)
 *   - Lloyd's-style methodology disclosure banner
 *   - Filter strip: search + tier buttons + domain multi-select
 *   - 4-row main table (post-#815 graduation; pre-graduation was 71) with
 *     5 cols (CATEGORY · TIER · MAX SALIENCE · COUNTRIES FIRING · TOP COUNTRIES)
 *
 * Deferred to PR #3: per-country watchlist /signals/[country]
 * Deferred to PR #4: per-(country, recipe) leaf with split-render by lineage
 * Deferred to PR #5 (founder-gated): cutover
 */

const TIER_META: Record<
  SignalTier,
  { label: string; color: string; bg: string; border: string; tooltip: string }
> = {
  HIGH: {
    label: "HIGH",
    color: "#f87171",
    bg: "rgba(248,113,113,0.10)",
    border: "rgba(248,113,113,0.35)",
    tooltip:
      "Max-salience ≥ 2.5σ over baseline. Source: Signals engine V1 / quantity: max-salience-z. Threshold: max-salience-z ≥ 2.5.",
  },
  MODERATE: {
    label: "MODERATE",
    color: "#fbbf24",
    bg: "rgba(251,191,36,0.10)",
    border: "rgba(251,191,36,0.35)",
    tooltip:
      "Max-salience 1.0–2.5σ over baseline. Statistical aggregation, not ML-validated.",
  },
  INDICATIVE: {
    label: "INDICATIVE",
    color: "#38bdf8",
    bg: "rgba(56,189,248,0.10)",
    border: "rgba(56,189,248,0.35)",
    tooltip: "Max-salience below 1.0σ over baseline. Background-level firing.",
  },
};

const TIER_ORDER: Record<SignalTier, number> = {
  HIGH: 0,
  MODERATE: 1,
  INDICATIVE: 2,
};

type SortColumn = "tier" | "category" | "max_salience" | "firing_count";
type SortDir = "asc" | "desc";

function sortRows(rows: SignalRow[], col: SortColumn, dir: SortDir): SignalRow[] {
  const arr = [...rows];
  const mul = dir === "asc" ? 1 : -1;
  switch (col) {
    case "category":
      arr.sort((a, b) => mul * a.category.localeCompare(b.category));
      break;
    case "tier":
      arr.sort((a, b) => mul * (TIER_ORDER[a.tier] - TIER_ORDER[b.tier]));
      break;
    case "max_salience":
      arr.sort((a, b) => mul * (a.max_salience - b.max_salience));
      break;
    case "firing_count":
      arr.sort((a, b) => mul * (a.firing_count - b.firing_count));
      break;
  }
  return arr;
}

export interface DomainActivation {
  code: string;
  label: string;
  shortLabel: string;
  color: string;
  /** Count of categories with tier ≥ MODERATE mapped to this L1. */
  n_categories: number;
  /** Unique-country count across this L1's firing categories (top-3 per cat). */
  n_countries: number;
}

export function SignalsMergedListClient({
  signals,
  tierCounts,
  totalCountries,
  generatedDate,
  domainActivation,
}: {
  signals: SignalRow[];
  tierCounts: Record<SignalTier, number>;
  totalCountries: number;
  /** ISO yyyy-mm-dd, computed server-side for hydration stability. */
  generatedDate: string;
  /** Per-L1 activation counts — REAL data. PR #2. */
  domainActivation: DomainActivation[];
}) {
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState<"ALL" | SignalTier>("ALL");
  const [activeDomains, setActiveDomains] = useState<Set<string>>(new Set());
  const [sortCol, setSortCol] = useState<SortColumn>("max_salience");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const domainCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of signals) {
      if (s.l1) c[s.l1.code] = (c[s.l1.code] ?? 0) + 1;
    }
    return c;
  }, [signals]);

  const filtered = useMemo(() => {
    return signals.filter((s) => {
      if (search) {
        const q = search.toLowerCase();
        if (
          !s.display_name.toLowerCase().includes(q) &&
          !s.category.toLowerCase().includes(q) &&
          !(s.l1?.label.toLowerCase().includes(q) ?? false)
        ) {
          return false;
        }
      }
      if (tierFilter !== "ALL" && s.tier !== tierFilter) return false;
      if (activeDomains.size > 0 && !(s.l1 && activeDomains.has(s.l1.code))) {
        return false;
      }
      return true;
    });
  }, [signals, search, tierFilter, activeDomains]);

  const sorted = useMemo(
    () => sortRows(filtered, sortCol, sortDir),
    [filtered, sortCol, sortDir]
  );

  const toggleDomain = (code: string) => {
    setActiveDomains((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const firingTotal = tierCounts.HIGH + tierCounts.MODERATE; // categories above background

  return (
    <div className="p-6 lg:p-8">
      {/* ============== Header ============== */}
      <div className="mb-5">
        <div
          className="text-[10px] tracking-widest uppercase mb-1"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Currently firing — {generatedDate}
        </div>
        <h1
          className="text-2xl font-semibold leading-snug"
          style={{ color: "var(--qgi-text)" }}
        >
          Signals
        </h1>
        <p
          className="text-xs mt-2 font-data tabular-nums"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          {signals.length} ML-validated {signals.length === 1 ? "recipe" : "recipes"} ·{" "}
          {firingTotal} firing across {totalCountries} countries · v1.9.1 scoring
        </p>
      </div>

      {/* ============== "5 firing now" curated band — PR #2 ============== */}
      <FiringNowBand signals={signals} generatedDate={generatedDate} />

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
          Signals shown are output from QGI&apos;s pattern-matching pipeline. Tier values
          (HIGH / MODERATE / INDICATIVE) reflect max-salience-z thresholds across firing
          countries — relative position, not a probabilistic forecast. Hover any tier
          badge for the rubric. Methodology and known limitations:{" "}
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

      {/* ============== Filter strip ============== */}
      <div
        role="group"
        aria-label="Filter by domain"
        className="flex gap-2 flex-wrap mb-3"
      >
        {L1_GROUPS.map((g) => {
          const active = activeDomains.has(g.code);
          const count = domainCounts[g.code] ?? 0;
          if (count === 0) return null;
          return (
            <button
              key={g.code}
              onClick={() => toggleDomain(g.code)}
              aria-pressed={active}
              className="px-3 py-1.5 rounded text-[10px] tracking-wider uppercase border transition-all"
              style={{
                backgroundColor: active ? `${g.color}18` : "transparent",
                borderColor: active ? g.color : "var(--qgi-border)",
                color: active ? g.color : "var(--qgi-text-muted)",
              }}
            >
              {g.shortLabel} ({count})
            </button>
          );
        })}
        {activeDomains.size > 0 && (
          <button
            onClick={() => setActiveDomains(new Set())}
            className="px-3 py-1.5 rounded text-[10px] tracking-wider uppercase border transition-colors"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-dim)",
            }}
          >
            Clear
          </button>
        )}
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-4 items-stretch sm:items-center flex-wrap">
        {/* Tier chip group — single-select */}
        <div
          role="radiogroup"
          aria-label="Filter by tier"
          className="flex items-center gap-1.5"
        >
          <span
            className="text-[9px] tracking-widest uppercase mr-1"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Tier
          </span>
          {(["ALL", "HIGH", "MODERATE", "INDICATIVE"] as const).map((t) => {
            const active = tierFilter === t;
            const meta = t !== "ALL" ? TIER_META[t] : null;
            return (
              <button
                key={t}
                role="radio"
                aria-checked={active}
                onClick={() => setTierFilter(t)}
                className="px-2.5 py-1 rounded-full text-[10px] tracking-wider uppercase font-data font-semibold transition-all"
                style={{
                  backgroundColor: active && meta ? meta.bg : "transparent",
                  color: active && meta ? meta.color : "var(--qgi-text-muted)",
                  border: `1px solid ${
                    active && meta
                      ? meta.border
                      : active
                        ? "var(--qgi-accent)"
                        : "var(--qgi-border)"
                  }`,
                }}
              >
                {t}
              </button>
            );
          })}
        </div>

        {/* Search — #741 (2026-05-16): sr-only <label htmlFor> replaces
            aria-label per WCAG 1.3.1 + accname-1.2 §4.3 (no double-naming). */}
        <label htmlFor="signals-merged-search" className="sr-only">
          Search category or L1 domain
        </label>
        <input
          id="signals-merged-search"
          type="text"
          placeholder="Search category or domain..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-4 py-2 rounded border text-sm flex-1 max-w-md outline-none transition-colors focus:border-[var(--qgi-accent)]"
          style={{
            backgroundColor: "var(--qgi-surface)",
            borderColor: "var(--qgi-border)",
            color: "var(--qgi-text)",
          }}
        />

        {/* Sort */}
        <div className="flex items-center gap-1.5 ml-auto">
          {/* #741: visible "Sort" span -> <label htmlFor> for click-to-focus */}
          <label
            htmlFor="signals-merged-sort"
            className="text-[9px] tracking-widest uppercase"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Sort
          </label>
          <select
            id="signals-merged-sort"
            value={sortCol}
            onChange={(e) => setSortCol(e.target.value as SortColumn)}
            className="px-3 py-2 rounded border text-xs outline-none cursor-pointer"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            <option value="max_salience">Max salience</option>
            <option value="tier">Tier</option>
            <option value="firing_count">Firing count</option>
            <option value="category">Category (A→Z)</option>
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
          Showing {sorted.length} of {signals.length}
        </span>
      </div>

      {/* ============== Domain activation strip — PR #2 ============== */}
      <DomainActivationStrip domains={domainActivation} />

      {/* ============== Table ============== */}
      <div
        className="rounded-lg border overflow-hidden"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <div
          className="hidden md:grid items-center px-4 py-2.5 text-[10px] tracking-widest uppercase gap-x-2"
          style={{
            gridTemplateColumns: "2fr 110px 90px 90px 1.5fr",
            color: "var(--qgi-text-dim)",
            borderBottom: "1px solid var(--qgi-border)",
            backgroundColor: "var(--qgi-surface-2)",
          }}
        >
          <span>Category</span>
          <span>Tier</span>
          <span className="text-right">Max salience</span>
          <span className="text-right">Firing</span>
          <span>Top countries</span>
        </div>

        {sorted.length === 0 ? (
          <div
            className="text-center py-12 text-sm"
            role="status"
            aria-live="polite"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            No signals match these filters.
          </div>
        ) : (
          sorted.map((s, idx) => (
            <SignalRowComponent
              key={s.category}
              row={s}
              isLast={idx === sorted.length - 1}
            />
          ))
        )}
      </div>

      <p className="text-[10px] mt-4 font-data" style={{ color: "var(--qgi-text-dim)" }}>
        V1.9.1 scoring · Max-salience-z thresholds: HIGH ≥ 2.5, MODERATE ≥ 1.0, INDICATIVE
        &lt; 1.0 ·{" "}
        <Link
          href={"/methodology" as Route}
          className="underline underline-offset-2 hover:text-[var(--qgi-text-muted)]"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Methodology →
        </Link>
        {" · "}
        <span style={{ color: "var(--qgi-text-muted)" }}></span>
      </p>
    </div>
  );
}

function SignalRowComponent({ row, isLast }: { row: SignalRow; isLast: boolean }) {
  const meta = TIER_META[row.tier];
  // PR-vii (2026-05-15) — route to the highest-salience country's leaf
  // page for this signal. Falls back to the V1 master with recipe filter
  // when the row has no countries (defensive; shouldn't happen in current
  // data shape but the fallback keeps the row non-broken).
  const topCountry = row.top_countries[0];
  const topSlug = topCountry
    ? (countrySlug(topCountry.name) ?? topCountry.alpha_2.toLowerCase())
    : null;
  const detailHref = (
    topSlug ? `/signals/${topSlug}/${row.category}` : `/signals?recipe=${row.category}`
  ) as Route;
  return (
    <Link
      href={detailHref}
      className="block transition-colors hover:bg-[var(--qgi-surface-2)] group"
      style={{
        borderBottom: isLast ? "none" : "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${row.l1?.color ?? "var(--qgi-border)"}`,
      }}
    >
      {/* Mobile (compressed) */}
      <div className="md:hidden px-4 py-3 flex flex-col gap-1.5">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="text-sm font-medium group-hover:text-[var(--qgi-accent)] transition-colors"
            style={{ color: "var(--qgi-text)" }}
          >
            {row.display_name}
          </span>
          {row.l1 && (
            <span
              className="text-[9px] tracking-widest uppercase font-medium px-1.5 py-0.5 rounded"
              style={{ color: row.l1.color, backgroundColor: `${row.l1.color}18` }}
            >
              {row.l1.shortLabel}
            </span>
          )}
          <span
            className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-data font-semibold tracking-wider uppercase"
            style={{
              backgroundColor: meta.bg,
              color: meta.color,
              border: `1px solid ${meta.border}`,
            }}
            title={meta.tooltip}
          >
            {meta.label}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <span style={{ color: "var(--qgi-text-muted)" }}>
            <span className="font-data" style={{ color: "var(--qgi-text)" }}>
              {row.max_salience.toFixed(2)}σ
            </span>{" "}
            max
          </span>
          <span style={{ color: "var(--qgi-text-muted)" }}>
            <span className="font-data" style={{ color: "var(--qgi-text)" }}>
              {row.firing_count}
            </span>{" "}
            countries
          </span>
        </div>
      </div>

      {/* Desktop 5-col grid */}
      <div
        className="hidden md:grid items-center px-4 py-3 gap-x-2"
        style={{ gridTemplateColumns: "2fr 110px 90px 90px 1.5fr" }}
      >
        {/* CATEGORY */}
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="text-sm truncate group-hover:text-[var(--qgi-accent)] transition-colors font-medium"
            style={{ color: "var(--qgi-text)" }}
          >
            {row.display_name}
          </span>
          {row.l1 && (
            <span
              className="text-[9px] tracking-widest uppercase font-medium px-1 rounded shrink-0"
              style={{ color: row.l1.color, backgroundColor: `${row.l1.color}18` }}
              title={row.l1.label}
            >
              {row.l1.shortLabel}
            </span>
          )}
        </div>

        {/* TIER */}
        <span>
          <span
            className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-data font-semibold tracking-wider uppercase"
            style={{
              backgroundColor: meta.bg,
              color: meta.color,
              border: `1px solid ${meta.border}`,
            }}
            title={meta.tooltip}
          >
            {meta.label}
          </span>
        </span>

        {/* MAX SALIENCE */}
        <span
          className="text-right font-data text-[11px] tabular-nums"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {row.max_salience.toFixed(2)}σ
        </span>

        {/* FIRING COUNT */}
        <span
          className="text-right font-data text-[11px] tabular-nums"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {row.firing_count}
        </span>

        {/* TOP COUNTRIES */}
        <div className="flex items-center gap-2 min-w-0">
          {row.top_countries.slice(0, 3).map((c) => {
            const cslug = countrySlug(c.name) ?? c.alpha_2.toLowerCase();
            return (
              <span
                key={c.id}
                className="inline-flex items-center gap-1 shrink-0"
                title={`${c.name}: ${c.salience.toFixed(2)}σ`}
              >
                <CountryFlag alpha2={c.alpha_2} size={12} />
                <span
                  className="text-[10px] truncate"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  {cslug}
                </span>
              </span>
            );
          })}
        </div>
      </div>
    </Link>
  );
}

// ============================================================================
// "Firing now" band — data-derived, top 5 by max_salience
// ----------------------------------------------------------------------------
// #719 (2026-05-16) — pre-fix this band read hand-authored entries from
// `./mockFiringSignals.ts`. All 5 captions had drifted from the current
// bake. Fix: derive entirely from the SignalRow[] the page already
// builds. See FiringNowBand docstring for full context.
// ============================================================================

/**
 * #719 (2026-05-16) — fully data-derived.
 *
 * Pre-fix this component read 5 hand-authored entries from
 * `./mockFiringSignals.ts`. Persona test 2026-05-15 (Marcus / CRO)
 * surfaced a credibility dealbreaker: every single one of the 5
 * captions diverged from the current bake. The most visible:
 *
 *   Caption claimed "Turkey, Egypt, and Pakistan now share a similar
 *   fiscal-distress signature to historical 1997-class precedents"
 *   alongside a MODERATE tier pill — while the live data showed
 *   Currency Crisis at 0.523σ INDICATIVE (4 firing countries, none
 *   of them Turkey / Egypt / Pakistan).
 *
 * Audit (2026-05-16): 5/5 mockFiringSignals entries diverged from
 * canonical. Root cause: hand-authored prose seeded against a
 * pre-V1.9.1 bake; never regenerated when the V1.9.1 bake landed.
 *
 * Fix: drop the mock array entirely. Derive the band live from the
 * SignalRow[] the page already builds: pick the 5 highest-salience
 * categories that fire above INDICATIVE; render display_name + live
 * tier + auto-prose ("Firing on N countries; leading: X") + the
 * top_countries chip strip from live data.
 *
 * Result: no drift surface remains. The band can never contradict
 * its adjacent table because both read the same SignalRow source.
 *
 * Deferred follow-up: a future hand-curated editorial layer
 * (qgi-data weekly JSON the original brief envisioned) can ride
 * ALONGSIDE this band as a separate "Editorial commentary" section,
 * with its own CI lint asserting cross-checked claims. Until that
 * exists, the data-derived band is the entire firing-now surface.
 */
function FiringNowBand({
  signals,
  generatedDate,
}: {
  signals: SignalRow[];
  generatedDate: string;
}) {
  const cards = useMemo(() => {
    // Take the top 5 by max_salience that ALSO fire above INDICATIVE.
    // INDICATIVE means "background-level firing" by tier definition;
    // it doesn't belong in a "firing now" curated band.
    return [...signals]
      .filter((s) => s.tier !== "INDICATIVE")
      .sort((a, b) => b.max_salience - a.max_salience)
      .slice(0, 5);
  }, [signals]);

  if (cards.length === 0) return null;

  return (
    <section
      aria-label="Firing now — top categories from current bake"
      className="mb-5 rounded-lg border overflow-hidden"
      style={{
        backgroundColor: "var(--qgi-surface)",
        borderColor: "var(--qgi-border)",
      }}
    >
      <div
        className="px-4 py-2 flex items-center justify-between"
        style={{
          backgroundColor: "var(--qgi-surface-2)",
          borderBottom: "1px solid var(--qgi-border)",
        }}
      >
        <span
          className="text-[9px] tracking-widest uppercase font-semibold"
          style={{ color: "var(--qgi-text-muted)" }}
          title="Computed live from the current bake. Top 5 categories by max-salience that fire above INDICATIVE. No editorial prose; data-derived only."
        >
          [Verified data · week of {generatedDate}]
        </span>
        <span
          className="text-[9px] tracking-widest uppercase"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          {cards.length} firing now
        </span>
      </div>
      <ul className="divide-y" style={{ borderColor: "var(--qgi-border)" }}>
        {cards.map((live) => {
          const meta = TIER_META[live.tier];
          // Route to the highest-salience country's leaf.
          const cardTopCountry = live.top_countries[0];
          const cardTopSlug = cardTopCountry
            ? (countrySlug(cardTopCountry.name) ?? cardTopCountry.alpha_2.toLowerCase())
            : null;
          const detailHref = (
            cardTopSlug
              ? `/signals/${cardTopSlug}/${live.category}`
              : `/signals?recipe=${live.category}`
          ) as Route;
          // Auto-derived prose — purely data-driven, no editorial license.
          // Format: "Firing on {N} countries; leading: {country1} at {salience}σ."
          const leadCountry = live.top_countries[0];
          const otherCount = Math.max(0, live.firing_count - 1);
          const derivedProse = leadCountry
            ? `Firing on ${live.firing_count} ${
                live.firing_count === 1 ? "country" : "countries"
              } in the current bake; ${leadCountry.name} leads at ${leadCountry.salience.toFixed(
                2
              )}σ${
                otherCount > 0
                  ? `, with ${otherCount} other ${otherCount === 1 ? "country" : "countries"} also above the firing threshold.`
                  : "."
              }`
            : `Firing on ${live.firing_count} ${
                live.firing_count === 1 ? "country" : "countries"
              } in the current bake.`;
          return (
            <li key={live.category} style={{ borderColor: "var(--qgi-border)" }}>
              {/* #754 (persona-test 2026-05-17, Fatima/UNDP iPhone 14 / 390px):
                  the prior fixed 4-column grid (1.4fr / 90px / 2.5fr / 140px)
                  consumed ~280px in fixed widths + gaps, leaving the
                  description column ~33px wide on mobile — the prose then
                  wrapped one-word-per-line for ~12 lines. Fix: render as a
                  flex column below `md` (so children stack vertically and
                  the prose has full width to flow); promote to the 4-column
                  grid at ≥md. The inline `gridTemplateColumns` is inert on
                  mobile because `display: flex` overrides `display: grid`. */}
              <Link
                href={detailHref}
                className="px-4 py-3 flex flex-col gap-2 md:grid md:items-start md:gap-x-3 md:gap-y-0 transition-colors hover:bg-[color:var(--qgi-surface-2)]"
                style={{
                  gridTemplateColumns: "minmax(0, 1.4fr) 90px minmax(0, 2.5fr) 140px",
                }}
              >
                {/* Category + L1 chip */}
                <div className="min-w-0">
                  <div
                    className="text-sm font-medium leading-tight truncate"
                    style={{ color: "var(--qgi-text)" }}
                    title={live.display_name}
                  >
                    {live.display_name}
                  </div>
                  {live.l1 && (
                    <div
                      className="inline-flex items-center mt-1 px-1.5 py-0.5 rounded text-[9px] tracking-widest uppercase font-semibold"
                      style={{
                        backgroundColor: `${live.l1.color}14`,
                        color: live.l1.color,
                      }}
                    >
                      {live.l1.shortLabel}
                    </div>
                  )}
                </div>

                {/* Tier pill */}
                <div
                  className="text-[10px] tracking-wider uppercase font-semibold font-data text-center px-2 py-1 rounded"
                  title={meta.tooltip}
                  style={{
                    backgroundColor: meta.bg,
                    color: meta.color,
                    border: `1px solid ${meta.border}`,
                  }}
                >
                  {meta.label}
                </div>

                {/* Auto-derived data prose */}
                <p
                  className="text-xs leading-relaxed"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  {derivedProse}
                </p>

                {/* Top countries chip strip — same data as the prose's "leading" claim. */}
                <div className="flex flex-wrap gap-1 justify-end">
                  {live.top_countries.map((c) => (
                    <span
                      key={c.alpha_2}
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]"
                      style={{
                        backgroundColor: "var(--qgi-surface-2)",
                        border: "1px solid var(--qgi-border)",
                        color: "var(--qgi-text-muted)",
                      }}
                    >
                      <CountryFlag alpha2={c.alpha_2} size={12} countryName={c.name} />
                      <span className="whitespace-nowrap">{c.name}</span>
                    </span>
                  ))}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ============================================================================
// PR #2 — Domain activation strip
// ----------------------------------------------------------------------------
// 8-cell L1-domain band rendered above the master list. Each cell shows
// (a) categories firing in this domain at tier ≥ MODERATE, (b) unique
// country count across those firing categories. REAL data — no preview chip.
// ============================================================================

function DomainActivationStrip({ domains }: { domains: DomainActivation[] }) {
  // #815 (2026-05-18) — after the 4-only graduation the LOCKed recipes
  // concentrate in 2 L1 domains (F-Conflict + B-Governance). Rendering all
  // 8 L1 cells with 6 stuck at 0 made the strip look broken. Filter to
  // non-zero domains for visual clarity; the post-graduation subtitle
  // tells the reader these are the activated subset.
  const activeDomains = domains.filter((d) => d.n_categories > 0);
  // Defensive fallback: if NOTHING is firing (edge case for future bakes),
  // fall back to the full list so the strip still renders.
  const shown = activeDomains.length > 0 ? activeDomains : domains;
  const maxN = Math.max(1, ...shown.map((d) => d.n_categories));
  return (
    <section
      aria-label="Domain activation"
      className="mb-3 rounded-lg border overflow-hidden"
      style={{
        backgroundColor: "var(--qgi-surface)",
        borderColor: "var(--qgi-border)",
      }}
    >
      <div
        className="px-3 py-1.5 flex items-center justify-between"
        style={{
          backgroundColor: "var(--qgi-surface-2)",
          borderBottom: "1px solid var(--qgi-border)",
        }}
      >
        <span
          className="text-[9px] tracking-widest uppercase font-semibold"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          Domain activation
        </span>
        <span
          className="text-[9px] tracking-widest uppercase"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          categories firing ≥ MODERATE · {shown.length} active{" "}
          {shown.length === 1 ? "L1 domain" : "L1 domains"}
        </span>
      </div>
      <div
        className="grid"
        style={{
          gridTemplateColumns: `repeat(${shown.length}, minmax(0, 1fr))`,
        }}
      >
        {shown.map((d, idx) => {
          const heightPct = (d.n_categories / maxN) * 100;
          const isLast = idx === shown.length - 1;
          return (
            <div
              key={d.code}
              className="px-3 py-2"
              style={{
                borderRight: isLast ? undefined : "1px solid var(--qgi-border)",
              }}
              title={`${d.label} — ${d.n_categories} ${d.n_categories === 1 ? "category" : "categories"} firing across ≥${d.n_countries} ${d.n_countries === 1 ? "country" : "countries"} (sampled from top-3 firing per category; true panel reach may be higher)`}
            >
              <div
                className="text-[9px] tracking-widest uppercase font-semibold mb-1.5"
                style={{ color: d.color }}
              >
                {d.shortLabel}
              </div>
              {/* Mini activation bar */}
              <div
                className="rounded-sm overflow-hidden mb-1.5"
                style={{
                  height: 4,
                  backgroundColor: "var(--qgi-surface-2)",
                }}
              >
                <div
                  style={{
                    width: `${heightPct}%`,
                    height: "100%",
                    backgroundColor: d.color,
                    transition: "width 220ms ease-out",
                  }}
                />
              </div>
              <div className="flex items-baseline gap-1 font-data tabular-nums">
                <span
                  className="text-sm font-semibold"
                  style={{ color: "var(--qgi-text)" }}
                >
                  {d.n_categories}
                </span>
                <span
                  className="text-[9px] tracking-widest uppercase"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  cat
                </span>
              </div>
              <div className="flex items-baseline gap-1 font-data tabular-nums">
                <span className="text-[11px]" style={{ color: "var(--qgi-text-muted)" }}>
                  ≥{d.n_countries}
                </span>
                <span
                  className="text-[9px] tracking-widest uppercase"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  cty
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
