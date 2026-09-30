"use client";

import { useState, useMemo } from "react";
import type { Report, ReportCategory } from "../_data/reports-manifest";
import { ReportCard } from "./ReportCard";

type FormatTier = "ALL" | "BRIEF" | "DEEP DIVE";

type Props = {
  reports: Report[];
};

export function TierFilteredGrid({ reports }: Props) {
  const [activeTier, setActiveTier] = useState<FormatTier>("ALL");
  const [activeCategory, setActiveCategory] = useState<ReportCategory | "ALL">("ALL");

  // Tier-filtered set first
  const tierFiltered = useMemo(() => {
    if (activeTier === "ALL") return reports;
    if (activeTier === "BRIEF") return reports.filter((r) => r.format === "brief");
    return reports.filter((r) => r.format === "deep-dive");
  }, [reports, activeTier]);

  // Categories present after tier filter
  const categories = useMemo(() => {
    const set = new Set<ReportCategory>();
    for (const r of tierFiltered) set.add(r.category);
    return Array.from(set);
  }, [tierFiltered]);

  // Reset category when tier changes (if current category no longer present)
  const resolvedCategory: ReportCategory | "ALL" = useMemo(() => {
    if (activeCategory === "ALL") return "ALL";
    return categories.includes(activeCategory as ReportCategory) ? activeCategory : "ALL";
  }, [activeCategory, categories]);

  const filtered = useMemo(() => {
    if (resolvedCategory === "ALL") return tierFiltered;
    return tierFiltered.filter((r) => r.category === resolvedCategory);
  }, [tierFiltered, resolvedCategory]);

  const tiers: FormatTier[] = ["ALL", "BRIEF", "DEEP DIVE"];
  const showCategorySelect = categories.length >= 2;

  return (
    <div>
      {/* Tier chips */}
      <div
        role="group"
        aria-label="Filter reports by format"
        className="flex flex-wrap items-center gap-1 mb-4 p-1 rounded-md w-fit"
        style={{
          backgroundColor: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
        }}
      >
        {tiers.map((tier) => {
          const isActive = tier === activeTier;
          return (
            <button
              key={tier}
              type="button"
              aria-pressed={isActive}
              onClick={() => setActiveTier(tier)}
              className="text-[11px] tracking-wider uppercase font-data px-3 py-1.5 rounded transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)]"
              style={{
                backgroundColor: isActive ? "var(--qgi-accent)" : "transparent",
                color: isActive ? "var(--qgi-bg)" : "var(--qgi-text-muted)",
                fontWeight: isActive ? 600 : 400,
              }}
            >
              {tier}
            </button>
          );
        })}
      </div>

      {/* Optional category select */}
      {showCategorySelect && (
        <div className="mb-6">
          <label
            htmlFor="report-category-select"
            className="text-[10px] tracking-widest uppercase font-data mr-2"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Category
          </label>
          <select
            id="report-category-select"
            value={resolvedCategory}
            onChange={(e) => setActiveCategory(e.target.value as ReportCategory | "ALL")}
            className="text-[11px] tracking-wide font-data px-2 py-1 rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)]"
            style={{
              backgroundColor: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              color: "var(--qgi-text-muted)",
            }}
          >
            <option value="ALL">All categories</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Grid */}
      {filtered.length === 0 ? (
        <p className="text-sm py-8 text-center" style={{ color: "var(--qgi-text-dim)" }}>
          No reports in this category yet.
        </p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {filtered.map((report) => (
            <ReportCard key={report.slug} report={report} />
          ))}
        </div>
      )}
    </div>
  );
}
