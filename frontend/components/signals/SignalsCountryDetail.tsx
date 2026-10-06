"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { CountryFlag } from "@/components/design/CountryFlag";
import { L1_GROUPS } from "@/lib/category-taxonomy";
import { AUTO_NARRATIVE_LABEL } from "@/lib/labels";
import type { CountrySignalRow, SignalTier } from "@/lib/signals-types";

/**
 * Merged Signals per-country detail — Build PR #3 of 5 (A3 Family 3).
 *
 * Brief: docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-13.md
 *   (Family 3 — Signals / per-country composition)
 *
 * Scope of PR #3:
 *   - Breadcrumb (Home / Signals / {country})
 *   - Hero: eyebrow + h1 "What's firing on {country}" + country flag +
 *     country tier badge + tier-pill hover tooltip
 *   - Lloyd's-style methodology disclosure banner (sticky pattern)
 *   - Section 1 — "What's happening here" lede (Ingrid 75-95w 3-movement
 *     template for authored countries; preview-template fallback for ~140
 *     unauthored). Tagged `[Illustrative narrative]` or `[Preview
 *     template]` per Sipho's 4-label vocabulary.
 *   - Filter strip (search + tier radiogroup + domain chips)
 *   - Per-country sortable table (CATEGORY · TIER · L1 · ALIGNMENT)
 *   - Cross-family handoffs footer (Precedents + Countries + master list)
 *
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

const TIER_ORDER: Record<SignalTier, number> = { HIGH: 0, MODERATE: 1, INDICATIVE: 2 };

type SortColumn = "category" | "tier" | "salience";
type SortDir = "asc" | "desc";

function sortRows(
  rows: CountrySignalRow[],
  col: SortColumn,
  dir: SortDir
): CountrySignalRow[] {
  const arr = [...rows];
  const mul = dir === "asc" ? 1 : -1;
  switch (col) {
    case "category":
      arr.sort((a, b) => mul * a.category.localeCompare(b.category));
      break;
    case "tier":
      arr.sort((a, b) => mul * (TIER_ORDER[a.tier] - TIER_ORDER[b.tier]));
      break;
    case "salience":
      arr.sort((a, b) => mul * (a.salience - b.salience));
      break;
  }
  return arr;
}

export function SignalsCountryDetail({
  slug,
  countryName,
  alpha2,
  countryTier,
  rows,
  tierCounts,
  generatedDate,
  curated,
}: {
  slug: string;
  countryName: string;
  alpha2: string;
  /**
   * V1 overall_risk_tier — already in HIGH/MODERATE/INDICATIVE vocabulary
   * per country-risks.schema.ts RiskTierSchema. Brief 7th-vote unified
   * country + signal vocab, so indexes TIER_META directly.
   */
  countryTier: SignalTier;
  rows: CountrySignalRow[];
  tierCounts: Record<SignalTier, number>;
  generatedDate: string;
  /** True when the country has a curated event-history file (Ingrid lede). */
  curated: boolean;
}) {
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState<"ALL" | SignalTier>("ALL");
  const [activeDomains, setActiveDomains] = useState<Set<string>>(new Set());
  const [sortCol, setSortCol] = useState<SortColumn>("salience");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const domainCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of rows) {
      if (r.l1) c[r.l1.code] = (c[r.l1.code] ?? 0) + 1;
    }
    return c;
  }, [rows]);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (search) {
        const q = search.toLowerCase();
        if (
          !r.display_name.toLowerCase().includes(q) &&
          !r.category.toLowerCase().includes(q) &&
          !(r.l1?.label.toLowerCase().includes(q) ?? false)
        ) {
          return false;
        }
      }
      if (tierFilter !== "ALL" && r.tier !== tierFilter) return false;
      if (activeDomains.size > 0 && !(r.l1 && activeDomains.has(r.l1.code))) {
        return false;
      }
      return true;
    });
  }, [rows, search, tierFilter, activeDomains]);

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

  const heroTierMeta = TIER_META[countryTier];
  const firingTotal = tierCounts.HIGH + tierCounts.MODERATE;

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
          href={"/risk-board" as Route}
          className="hover:underline"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Signals
        </Link>
        <span className="mx-1.5">/</span>
        <span style={{ color: "var(--qgi-text-muted)" }}>{countryName}</span>
      </nav>

      {/* ============== Hero ============== */}
      <div className="mb-5">
        <div
          className="text-[10px] tracking-widest uppercase mb-1"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Signals — {countryName}
        </div>
        <div className="flex items-center gap-3 mb-2">
          <CountryFlag alpha2={alpha2} size={32} countryName={countryName} />
          <h1
            className="text-2xl font-semibold leading-snug"
            style={{ color: "var(--qgi-text)" }}
          >
            What&apos;s firing on {countryName}
          </h1>
          {/* #850 — explicit "Country composite tier" label distinguishes the
              statistical-layer tier from the ML-signal tier shown in the body.
              Three countries (Bahrain, Dominican Republic, Thailand) have a
              HIGH composite tier while all LOCKed ML signals are INDICATIVE. */}
          <span
            className="text-[10px] tracking-wider uppercase font-semibold font-data px-2 py-1 rounded"
            title={`Country composite tier: ${heroTierMeta.label}. ${heroTierMeta.tooltip} This tier reflects the full statistical-layer scoring across 71 categories. The ML-validated recipe signals below are tracked on a different scale — see /methodology#aggregate-vs-per-recipe.`}
            style={{
              backgroundColor: heroTierMeta.bg,
              color: heroTierMeta.color,
              border: `1px solid ${heroTierMeta.border}`,
            }}
          >
            Country composite tier: {heroTierMeta.label}
          </span>
        </div>
        <p
          className="text-xs font-data tabular-nums"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          {rows.length} categories tracked · {firingTotal} firing across all tier windows
          · v1.9.1 scoring · Updated {generatedDate}
        </p>
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
          Signals shown are output from QGI&apos;s pattern-matching pipeline, scored
          against historical precedent. Tier values (HIGH / MODERATE / INDICATIVE) reflect
          max-salience-z thresholds — relative position, not a probabilistic forecast.
          Hover any tier badge for the rubric. Methodology and known limitations:{" "}
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

      {/* ============== Section 1 — "What's happening here" lede ============== */}
      <section
        aria-labelledby="lede-heading"
        className="mb-6 rounded-lg border p-5"
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
            What&apos;s happening here
          </h2>
          <span
            className="text-[9px] tracking-widest uppercase font-semibold px-1.5 py-0.5 rounded"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              color: "var(--qgi-text-muted)",
              border: "1px solid var(--qgi-border)",
            }}
          >
            {AUTO_NARRATIVE_LABEL}
          </span>
        </div>
        <p
          className="text-sm leading-relaxed max-w-[68ch]"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {ledeText({ countryName, rows, tierCounts, curated, countryTier })}
        </p>
      </section>

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
        {/* Tier chip group */}
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
                        ? "var(--qgi-text-muted)"
                        : "var(--qgi-border)"
                  }`,
                }}
              >
                {t}
              </button>
            );
          })}
        </div>

        {/* Search — #741 (2026-05-16): sr-only <label htmlFor> per WCAG 1.3.1 */}
        <label htmlFor="signals-country-detail-search" className="sr-only">
          Search category or L1 domain
        </label>
        <input
          id="signals-country-detail-search"
          type="text"
          placeholder="Search category or L1..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-2 rounded-md border bg-transparent text-xs flex-1 min-w-0"
          style={{
            borderColor: "var(--qgi-border)",
            color: "var(--qgi-text)",
          }}
        />

        {/* Sort */}
        <div className="flex items-center gap-1">
          {/* #741: visible "Sort" span -> <label htmlFor> for click-to-focus */}
          <label
            htmlFor="signals-country-detail-sort"
            className="text-[9px] tracking-widest uppercase mr-1"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Sort
          </label>
          <select
            id="signals-country-detail-sort"
            value={sortCol}
            onChange={(e) => setSortCol(e.target.value as SortColumn)}
            className="px-2 py-1.5 rounded border bg-transparent text-[11px]"
            style={{
              backgroundColor: "var(--qgi-surface)",
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            <option value="salience">Alignment (salience-z proxy)</option>
            <option value="tier">Tier</option>
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
          Showing {sorted.length} of {rows.length}
        </span>
      </div>

      {/* ============== Per-country table ============== */}
      <div
        className="rounded-lg border overflow-hidden mb-6"
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderColor: "var(--qgi-border)",
        }}
      >
        <div
          className="hidden md:grid items-center px-4 py-2.5 text-[10px] tracking-widest uppercase gap-x-2"
          style={{
            gridTemplateColumns: "2fr 110px 90px 140px",
            color: "var(--qgi-text-dim)",
            borderBottom: "1px solid var(--qgi-border)",
            backgroundColor: "var(--qgi-surface-2)",
          }}
        >
          <span>Category</span>
          <span>Tier</span>
          <span>L1</span>
          <span className="text-right inline-flex items-center justify-end gap-1.5">
            Alignment
            <span
              className="text-[8px] font-normal normal-case tracking-normal px-1 py-0.5 rounded"
              title="Preview values — Q4 2026 bake will replace with per-country alignment scores."
              style={{
                backgroundColor: "var(--qgi-surface)",
                color: "var(--qgi-text-dim)",
                border: "1px solid var(--qgi-border)",
              }}
            >
              Preview
            </span>
          </span>
        </div>

        {sorted.length === 0 ? (
          <div
            className="text-center py-12 text-sm"
            role="status"
            aria-live="polite"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            <p className="mb-3">
              No active signals match your filters for {countryName}.
            </p>
            <div className="flex justify-center gap-3">
              {(search || tierFilter !== "ALL" || activeDomains.size > 0) && (
                <button
                  onClick={() => {
                    setSearch("");
                    setTierFilter("ALL");
                    setActiveDomains(new Set());
                  }}
                  className="text-[10px] tracking-widest uppercase px-3 py-1.5 rounded border"
                  style={{
                    borderColor: "var(--qgi-border)",
                    color: "var(--qgi-text-muted)",
                  }}
                >
                  Reset filters
                </button>
              )}
              <Link
                href={`/countries/${slug}` as Route}
                className="text-[10px] tracking-widest uppercase px-3 py-1.5 rounded border"
                style={{
                  borderColor: "var(--qgi-border)",
                  color: "var(--qgi-text-muted)",
                }}
              >
                View country profile →
              </Link>
            </div>
          </div>
        ) : (
          <ul className="divide-y" style={{ borderColor: "var(--qgi-border)" }}>
            {sorted.map((r) => (
              <CountrySignalRowComponent key={r.category} row={r} countrySlug={slug} />
            ))}
          </ul>
        )}
      </div>

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
          Continue exploring {countryName}
        </h2>
        <div className="flex flex-wrap gap-2">
          <Link
            href={`/countries/${slug}` as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            Country profile →
          </Link>
          {/* PR-4 (#752): the old `Historical precedents → /precedents?country={slug}`
              CTA was removed. The /precedents index no longer honours a
              `?country=` query (PR-1 collapsed the catalogue to the 4 LOCKed
              ML recipes), so the link landed on an unfiltered index. The
              `Country profile →` CTA above already covers country-scoped
              navigation. */}
          <Link
            href={"/risk-board" as Route}
            className="text-[11px] px-3 py-1.5 rounded border transition-colors hover:bg-[color:var(--qgi-surface-2)]"
            style={{
              borderColor: "var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            All firing signals →
          </Link>
        </div>
      </section>

      <p
        className="text-[10px] tracking-widest uppercase text-center"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Currently firing signals updated {generatedDate} · Country tier from V1.9.1
        scoring ·{" "}
        <Link href={"/methodology" as Route} className="underline underline-offset-2">
          Methodology →
        </Link>
      </p>
    </div>
  );
}

// ============================================================================
// Per-row component
// ============================================================================
function CountrySignalRowComponent({
  row,
  countrySlug,
}: {
  row: CountrySignalRow;
  countrySlug: string;
}) {
  const meta = TIER_META[row.tier];
  // PR #4 — leaf page lives at /signals/[country]/[slug] now.
  const detailHref = `/signals/${countrySlug}/${row.category}` as Route;

  return (
    <li>
      <Link
        href={detailHref}
        className="px-4 py-3 grid items-center gap-x-2 transition-colors hover:bg-[color:var(--qgi-surface-2)]"
        style={{
          gridTemplateColumns: "2fr 110px 90px 140px",
        }}
      >
        <div className="min-w-0">
          <div
            className="text-sm font-medium leading-tight truncate"
            style={{ color: "var(--qgi-text)" }}
            title={row.display_name}
          >
            {row.display_name}
          </div>
        </div>

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

        {row.l1 ? (
          <div
            className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] tracking-widest uppercase font-semibold w-fit"
            style={{
              backgroundColor: `${row.l1.color}14`,
              color: row.l1.color,
            }}
            title={row.l1.label}
          >
            {row.l1.shortLabel}
          </div>
        ) : (
          <span
            className="text-[9px] tracking-widest uppercase"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            —
          </span>
        )}

        <div
          className="text-right text-sm font-data tabular-nums"
          style={{ color: "var(--qgi-text)" }}
          title={`Max salience-z across all tier windows for this country: ${row.salience.toFixed(2)}`}
        >
          {row.salience.toFixed(2)}
        </div>
      </Link>
    </li>
  );
}

// ============================================================================
// Ingrid lede — 3-movement template
// ----------------------------------------------------------------------------
// 75-95w / 3 movements:
//   1. What pattern shape this country fires on today
//   2. What has shifted recently in the indicator set
//   3. Honest disclosure: model output, not forecast
//
// Authored countries → [Illustrative narrative] tag rendered by caller.
// Unauthored countries → [Preview template] tag rendered by caller; this
// function still returns a templated paragraph so the section never reads
// as empty.
// ============================================================================
function ledeText({
  countryName,
  rows,
  tierCounts,
  curated,
  countryTier,
}: {
  countryName: string;
  rows: CountrySignalRow[];
  tierCounts: Record<SignalTier, number>;
  curated: boolean;
  /** #850 — composite tier used to add a note when composite ≠ ML-signal tier. */
  countryTier: SignalTier;
}): string {
  const firing = tierCounts.HIGH + tierCounts.MODERATE;
  const top = rows[0];
  const topName = top?.display_name ?? "no firing category";
  const topL1 = top?.l1?.label ?? "an unmapped domain";
  const topScore = top?.salience.toFixed(2) ?? "—";

  if (firing === 0) {
    // #850 — when the composite tier is above INDICATIVE but no ML signals are
    // firing, add a clarifying sentence so readers understand the discrepancy.
    const compositeMismatchNote =
      countryTier !== "INDICATIVE"
        ? ` Note: the country composite tier (${countryTier}) reflects the full statistical-layer scoring across 71 categories. No ML-validated recipes are currently firing at MODERATE+ for this country.`
        : "";
    return curated
      ? `${countryName} shows no categories firing above the baseline rung this week. Background-level signals remain present across the indicator set, but none crossed the moderate threshold in the current bake. This page reports model output for editorial review, not forecasting judgement; absence of firing is not a guarantee of stability.${compositeMismatchNote}`
      : `${countryName} currently shows no signals at moderate or higher tier. The full category list below remains visible at background tier for reference. The page below reports model output, not editorial forecast; verify against the country profile and precedents pages before drawing conclusions.${compositeMismatchNote}`;
  }

  // Curated voice — Ingrid 3-movement
  //
  // #719 residual (persona-test, 2026-05-17): the prior sentence
  // claimed the signal "has held across S/M/L/XL tier windows in
  // this bake, indicating the signal is structural rather than
  // episode-bound." That assertion cannot be sourced from the
  // current SignalRow shape (no `by_window` field exists in the
  // bake). It rendered unconditionally regardless of whether the
  // top category actually fired across all four windows or just
  // one — same drift class as the deleted "1997-class precedents"
  // caption. Per Ingrid: when copy can't be data-bound, remove the
  // claim. Re-add when (and only when) the bake emits per-window
  // firing data and the conditional can verify it.
  if (curated) {
    return `${countryName} enters this week with ${firing} ${firing === 1 ? "category" : "categories"} firing above the baseline rung, the most pronounced being ${topName} at ${topScore}σ in the ${topL1} domain. None of these are predictions in isolation; this page reports model output reviewed for editorial release, not probabilistic forecasts of recurrence.`;
  }

  // Preview-template fallback
  return `${countryName} currently has ${firing} ${firing === 1 ? "category" : "categories"} firing above the baseline rung. The strongest aggregate alignment is ${topName} in the ${topL1} domain, scoring ${topScore}σ. The page below lists every active category by alignment strength; hover any tier badge for the rubric. Verify against the country profile and precedents pages before drawing conclusions.`;
}
