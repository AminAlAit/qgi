"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { CATEGORY_L1_MAP, L1_GROUPS } from "@/lib/category-taxonomy";
import type { RecipeAggregated } from "@/lib/recipes-aggregated";
import type { BuyerMlRecipe } from "@/lib/buyer-view";
import { getTierTooltip } from "@/components/precedents/TierPillTooltip";
import { formatPipelineVersion } from "@/lib/pipeline-version";

/**
 * Precedents index — #748 PR-1 (#749), 2026-05-17.
 *
 * Per the revised merger brief at
 * `docs/specs/internal/ops/cycle-resurfacing/merger-brief-2026-05-17-precedents-revised.md`
 * — supersedes the 2026-05-13 zoned-shell implementation that mismatched
 * the founder's L10525 directive.
 *
 * Scope (PR-1 of 4):
 *   - Drop the two-zone shell (was: 4 ML hero rows + 64-recipe stat catalogue)
 *   - Drop the LINEAGE column (single value, no information)
 *   - Drop the lineage filter chip (ML / Stat / All)
 *   - Drop the "Mix zones" toggle (no zones to mix)
 *   - Drop the methodology disclosure strip (no zone separation to disclose)
 *   - Drop the "What we're still testing" <details> (no catalogue to test)
 *   - Drop the DOMAIN column (folded into a small L1 chip in the recipe cell
 *     per Yuki's synthesis: cell-level chip beats a redundant column at 4 rows)
 *
 * What renders now: 4 rows, one per LOCKed ML recipe. 5 columns: RECIPE
 * (display name + 2-line mechanism excerpt + inline L1 chip) / TIER /
 * INSTANCES / COVERAGE / CTA (View dossier →).
 *
 * 2026-05-17 follow-up: LENGTH column dropped per founder directive
 * ("remove all canonical lengths from the 4 precedents; hide them
 * elegantly"). Removed: LENGTH <th>/<td>, the "length" sort case, and
 * `canonical_length` from the local HeroRow type (it was only used to
 * render the dropped column). The underlying RecipeAggregated and the
 * Athena/bake schemas are untouched — `substrate.canonical_length` is
 * still available to any future component that needs it.
 *
 * Filter strip is minimal: search input + domain chips (only L1 groups
 * actually represented in the 4 rows — synthesizer rule, no empty chips).
 *
 * Sequenced PRs that depend on this one (per ratified brief §6):
 *   - PR-2 (#750): merged dossier template at /precedents/[slug]
 *   - PR-3 (#751): retired-slug redirects + sitemap/robots
 *   - PR-4 (#752): internal-link sweep
 */

// ---------------------------------------------------------------------------
// Tier mapping (ML-only; STRONG > MODERATE > MARGINAL per buyer-view rubric)
// ---------------------------------------------------------------------------

const ML_TIER_RANK: Record<BuyerMlRecipe["tier"], number> = {
  STRONG: 0,
  MODERATE: 1,
  MARGINAL: 2,
};

const TIER_COLORS: Record<BuyerMlRecipe["tier"], string> = {
  STRONG: "#22c55e",
  MODERATE: "#fbbf24",
  MARGINAL: "#a3a3a3",
};

// ---------------------------------------------------------------------------
// Row shape
// ---------------------------------------------------------------------------

interface HeroRow {
  slug: string;
  display_name: string;
  l1_group: string;
  l1_short_label: string;
  l1_color: string;
  tier: BuyerMlRecipe["tier"];
  tier_rank: number;
  total_instances: number;
  oecd_share: number;
  /** First ~22 words of the buyer-cleaned mechanism narrative, for the
   *  2-line inline excerpt under the recipe name (Tomás synthesizer rule —
   *  mechanism preview is the primary affordance, not the Tier pill). */
  mechanism_excerpt: string;
  /** Cross-family pill: how many countries are currently flagged on this
   *  recipe in the latest score bake. Renders only when > 0. */
  firing_count: number;
  detail_href: Route;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMechanismExcerpt(text: string, maxWords = 22): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  const words = cleaned.split(" ");
  if (words.length <= maxWords) return cleaned;
  return words.slice(0, maxWords).join(" ") + "…";
}

type SortCol = "tier" | "instances" | "coverage" | "alpha";
type SortDir = "asc" | "desc";

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function PrecedentsMergedListClient({
  heroRecipes,
  heroAggregatedBySlug,
  generatedAt,
  pipelineVersion,
  modelVersion,
  firingCountByMlSlug,
}: {
  heroRecipes: BuyerMlRecipe[];
  heroAggregatedBySlug: Record<string, RecipeAggregated>;
  generatedAt: string;
  pipelineVersion: string;
  modelVersion: string;
  firingCountByMlSlug: Record<string, number>;
}) {
  // Build the 4 rows. Recipes without an aggregated entry are skipped
  // (data-integrity invariant — every LOCKed ML recipe MUST have a stat
  // counterpart, since LOCK promotion is gated on the stat substrate).
  const rows = useMemo<HeroRow[]>(() => {
    return heroRecipes
      .map((r): HeroRow | null => {
        const agg = heroAggregatedBySlug[r.recipe_id];
        if (!agg) return null;
        const mapping = CATEGORY_L1_MAP[r.recipe_id];
        const l1 = mapping ? L1_GROUPS.find((g) => g.code === mapping.group) : undefined;
        return {
          slug: r.recipe_id,
          display_name: r.display_name,
          l1_group: mapping?.group ?? "?",
          l1_short_label: l1?.shortLabel ?? "Other",
          l1_color: l1?.color ?? "#8aa6be",
          tier: r.tier,
          tier_rank: ML_TIER_RANK[r.tier],
          total_instances: agg.total_instances,
          oecd_share: agg.coverage_bias_diagnostic.oecd_share,
          mechanism_excerpt: makeMechanismExcerpt(
            r.mechanism_narrative || r.mechanism_narrative_excerpt || ""
          ),
          firing_count: firingCountByMlSlug[r.recipe_id] ?? 0,
          detail_href: `/precedents/${r.recipe_id}` as Route,
        };
      })
      .filter((x): x is HeroRow => x !== null);
  }, [heroRecipes, heroAggregatedBySlug, firingCountByMlSlug]);

  const [search, setSearch] = useState("");
  const [activeDomains, setActiveDomains] = useState<Set<string>>(new Set());
  const [sortCol, setSortCol] = useState<SortCol>("tier");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Domain chips render only the L1 groups actually represented in the
  // four rows (synthesizer rule — never an empty chip).
  const representedDomains = useMemo(() => {
    const set = new Set<string>();
    rows.forEach((r) => set.add(r.l1_group));
    return L1_GROUPS.filter((g) => set.has(g.code));
  }, [rows]);

  const filtered = useMemo(() => {
    let result = rows;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (r) =>
          r.display_name.toLowerCase().includes(q) ||
          r.l1_short_label.toLowerCase().includes(q) ||
          r.mechanism_excerpt.toLowerCase().includes(q)
      );
    }
    if (activeDomains.size > 0) {
      result = result.filter((r) => activeDomains.has(r.l1_group));
    }
    return result;
  }, [rows, search, activeDomains]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    const sign = sortDir === "asc" ? 1 : -1;
    switch (sortCol) {
      case "tier":
        // Tier sort by rank — STRONG (0) → MARGINAL (2). Default direction
        // is desc (STRONG at top) per Marcus's "ML evidence underwrites
        // the dossier" principle. Secondary key: total_instances desc.
        arr.sort(
          (a, b) =>
            sign * (a.tier_rank - b.tier_rank) || -(a.total_instances - b.total_instances)
        );
        break;
      case "instances":
        arr.sort((a, b) => sign * (a.total_instances - b.total_instances));
        break;
      case "coverage":
        arr.sort((a, b) => sign * (a.oecd_share - b.oecd_share));
        break;
      case "alpha":
        arr.sort((a, b) => sign * a.display_name.localeCompare(b.display_name));
        break;
    }
    return arr;
  }, [filtered, sortCol, sortDir]);

  function toggleSort(col: SortCol) {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      // Defaults: alpha → asc, everything else → desc.
      setSortDir(col === "alpha" ? "asc" : "desc");
    }
  }

  function toggleDomain(code: string) {
    setActiveDomains((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  const bakeDate = new Date(generatedAt).toISOString().slice(0, 10);
  const sortIndicator = (col: SortCol) =>
    sortCol === col ? (sortDir === "asc" ? " ↑" : " ↓") : "";

  return (
    <div className="max-w-6xl mx-auto px-4 lg:px-6 py-8">
      {/* ─── Header ───────────────────────────────────────────────── */}
      <header className="mb-8">
        <div className="flex items-baseline justify-between gap-4 flex-wrap mb-3">
          <h1
            className="text-3xl font-semibold tracking-tight"
            style={{ color: "var(--qgi-text)" }}
          >
            Precedents
          </h1>
          <div
            className="text-[10px] font-data tracking-wider"
            style={{ color: "var(--qgi-text-dim)" }}
            title={`Generated ${generatedAt}`}
          >
            {/* #776 (persona-test R3): centralized formatter in
                `lib/pipeline-version.ts` strips engineer suffixes
                (`-dev`, `-baked`, `-rc`, `-beta`, `-alpha`) so the
                executive reader sees `v2.0`, not `vV2.0-dev`. See the
                lib file for behavior + the Marcus quote that motivated
                the rule. */}
            {formatPipelineVersion(pipelineVersion)} · {rows.length} currently validated ·
            model {modelVersion} · bake {bakeDate}
          </div>
        </div>
        <p
          className="text-sm leading-relaxed max-w-[68ch] mb-3"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          A precedent is a previous event that resembles a current one closely enough to
          inform a forecast. Four such recipes have completed adjudication: blind
          walk-forward backtest, calibration audit, four-pillar lock. They are below. Each
          one carries the statistical substrate it was promoted from, inside its dossier.
        </p>
        {/* Tour-design (2026-05-18): per Helena/Karl/Roberto R5 + universal
            5-persona observation, these two disclosures were collapsed-by-
            default behind `<details>` and universally missed. Now always-
            visible above-fold callouts. `role="note"` is intentional
            (overrides implicit `complementary` landmark with `note` —
            consistent with the site's existing pattern). */}
        <aside
          role="note"
          aria-label="How to read this"
          className="text-xs max-w-[68ch] mb-2"
        >
          <div
            className="font-semibold tracking-wide uppercase text-[10px] mb-1"
            style={{ color: "var(--qgi-amber)" }}
          >
            How to read this
          </div>
          <p
            className="mt-2 pl-3 border-l-2 leading-relaxed"
            style={{
              color: "var(--qgi-text-muted)",
              borderColor: "rgba(245, 158, 11, 0.4)",
            }}
          >
            The four cards below are the recipes the model can predict above chance,
            audited end-to-end. Each row opens onto a dossier that shows the ML evidence
            and the statistical fingerprint behind it — what&rsquo;s actually happening
            when these patterns appear, and which historical instances anchor the claim.
            The catalogue of unvalidated patterns has moved to the methodology page.
          </p>
        </aside>
        <aside
          role="note"
          aria-label="What this doesn't mean"
          className="text-xs max-w-[68ch]"
        >
          <div
            className="font-semibold tracking-wide uppercase text-[10px] mb-1"
            style={{ color: "var(--qgi-amber)" }}
          >
            What this doesn&apos;t mean
          </div>
          <p
            className="mt-2 pl-3 border-l-2 leading-relaxed"
            style={{
              color: "var(--qgi-text-muted)",
              borderColor: "rgba(245, 158, 11, 0.4)",
            }}
          >
            These four are not a global ranking. They are the recipes whose evidence has
            held up under every test in the lock rubric on this bake. Other patterns have
            been measured; many have not yet held. None of those appear here. The
            methodology page documents what was retired and why.
          </p>
        </aside>
      </header>

      {/* ─── Filter strip ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <label htmlFor="precedents-merged-search" className="sr-only">
          Search precedents
        </label>
        <input
          id="precedents-merged-search"
          type="text"
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-2 rounded border text-sm flex-1 min-w-[180px] max-w-sm outline-none transition-colors focus:border-[var(--qgi-accent)]"
          style={{
            backgroundColor: "var(--qgi-surface)",
            borderColor: "var(--qgi-border)",
            color: "var(--qgi-text)",
          }}
        />
        {representedDomains.length > 1 && (
          <>
            <span
              className="text-[9px] tracking-widest uppercase ml-2"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              Domain
            </span>
            {representedDomains.map((g) => {
              const active = activeDomains.has(g.code);
              return (
                <button
                  key={g.code}
                  onClick={() => toggleDomain(g.code)}
                  className="px-2 py-0.5 rounded text-[10px] font-medium tracking-wide transition-colors"
                  style={{
                    backgroundColor: active ? g.color : "transparent",
                    color: active ? "var(--qgi-bg)" : g.color,
                    border: `1px solid ${g.color}`,
                  }}
                  title={g.label}
                  aria-pressed={active}
                >
                  {g.shortLabel}
                </button>
              );
            })}
            {activeDomains.size > 0 && (
              <button
                onClick={() => setActiveDomains(new Set())}
                className="text-[10px] px-2 py-0.5 transition-colors"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                clear
              </button>
            )}
          </>
        )}
      </div>

      {/* ─── Table ────────────────────────────────────────────────── */}
      <div
        className="rounded-lg border overflow-hidden"
        style={{ borderColor: "var(--qgi-border)" }}
      >
        <table className="w-full">
          <thead style={{ backgroundColor: "var(--qgi-surface)" }}>
            <tr
              className="text-[10px] tracking-widest uppercase"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              <th
                className="text-left px-4 py-3 font-normal cursor-pointer hover:text-[var(--qgi-text)]"
                onClick={() => toggleSort("alpha")}
              >
                Recipe{sortIndicator("alpha")}
              </th>
              <th
                className="text-left px-4 py-3 font-normal cursor-pointer hover:text-[var(--qgi-text)] w-28"
                onClick={() => toggleSort("tier")}
              >
                Tier{sortIndicator("tier")}
              </th>
              <th
                className="text-right px-4 py-3 font-normal cursor-pointer hover:text-[var(--qgi-text)] w-28"
                onClick={() => toggleSort("instances")}
              >
                Instances{sortIndicator("instances")}
              </th>
              <th
                className="text-right px-4 py-3 font-normal cursor-pointer hover:text-[var(--qgi-text)] w-28"
                onClick={() => toggleSort("coverage")}
              >
                Coverage{sortIndicator("coverage")}
              </th>
              <th className="px-4 py-3 font-normal w-32"></th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-8 text-center text-xs"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  No precedents match these filters.
                </td>
              </tr>
            ) : (
              sorted.map((r) => (
                <tr
                  key={r.slug}
                  className="border-t hover:bg-white/5 transition-colors"
                  style={{ borderColor: "var(--qgi-border)" }}
                >
                  <td className="px-4 py-4 max-w-[460px]">
                    <Link href={r.detail_href} className="block group transition-colors">
                      <div className="flex items-baseline gap-2 mb-1 flex-wrap">
                        <span
                          className="font-medium text-[15px] group-hover:text-[var(--qgi-accent)] transition-colors"
                          style={{ color: "var(--qgi-text)" }}
                        >
                          {r.display_name}
                        </span>
                        <span
                          className="text-[10px] tracking-wide font-medium"
                          style={{ color: r.l1_color }}
                          title={r.l1_short_label}
                        >
                          {r.l1_short_label}
                        </span>
                        {r.firing_count > 0 && (
                          <span
                            className="text-[10px] tracking-wide font-data"
                            style={{ color: "var(--qgi-text-dim)" }}
                            title="Countries currently flagged on this recipe"
                          >
                            · {r.firing_count} firing
                          </span>
                        )}
                      </div>
                      {r.mechanism_excerpt && (
                        <p
                          className="text-xs leading-relaxed line-clamp-2"
                          style={{ color: "var(--qgi-text-muted)" }}
                        >
                          {r.mechanism_excerpt}
                        </p>
                      )}
                    </Link>
                  </td>
                  <td className="px-4 py-4 align-top">
                    <span
                      className="inline-block px-2 py-0.5 text-[10px] font-semibold rounded"
                      style={{
                        backgroundColor: `${TIER_COLORS[r.tier]}22`,
                        color: TIER_COLORS[r.tier],
                        border: `1px solid ${TIER_COLORS[r.tier]}55`,
                      }}
                      title={getTierTooltip(r.tier, "ML")}
                    >
                      {r.tier}
                    </span>
                  </td>
                  <td
                    className="px-4 py-4 text-right font-data tabular-nums align-top"
                    style={{ color: "var(--qgi-text)" }}
                  >
                    {r.total_instances.toLocaleString()}
                  </td>
                  <td
                    className="px-4 py-4 text-right font-data tabular-nums align-top"
                    style={{
                      color:
                        r.oecd_share > 0.5 ? "var(--qgi-amber)" : "var(--qgi-text-muted)",
                    }}
                    title={
                      r.oecd_share > 0.5
                        ? "Coverage skews OECD — non-OECD generalization caveat applies"
                        : "Globally representative coverage"
                    }
                  >
                    {(r.oecd_share * 100).toFixed(0)}% OECD
                  </td>
                  <td className="px-4 py-4 text-right align-top">
                    <Link
                      href={r.detail_href}
                      className="text-[11px] tracking-wider uppercase hover:text-[var(--qgi-accent)] transition-colors"
                      style={{ color: "var(--qgi-text-dim)" }}
                    >
                      View dossier →
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {sorted.length === 0 && (search || activeDomains.size > 0) && (
        <div className="mt-4 text-xs" style={{ color: "var(--qgi-text-dim)" }}>
          Clear filters to see all {rows.length} precedents.
        </div>
      )}
    </div>
  );
}
