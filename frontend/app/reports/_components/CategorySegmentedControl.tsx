"use client";

import { useState, useMemo } from "react";
import type { Report, ReportCategory } from "../_data/reports-manifest";
import { ReportCard } from "./ReportCard";

type Props = {
  reports: Report[];
};

const ALL_LABEL = "All" as const;
type Segment = typeof ALL_LABEL | ReportCategory;

export function CategoryFilteredGrid({ reports }: Props) {
  const categories = useMemo(() => {
    const set = new Set<ReportCategory>();
    for (const r of reports) set.add(r.category);
    return Array.from(set);
  }, [reports]);

  const [active, setActive] = useState<Segment>(ALL_LABEL);

  const filtered = useMemo(() => {
    if (active === ALL_LABEL) return reports;
    return reports.filter((r) => r.category === active);
  }, [reports, active]);

  const showSegmentedControl = categories.length >= 2;

  return (
    <div>
      {showSegmentedControl && (
        <div
          role="group"
          aria-label="Filter reports by category"
          className="flex flex-wrap items-center gap-1 mb-6 p-1 rounded-md w-fit"
          style={{
            backgroundColor: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          {[ALL_LABEL as Segment, ...categories].map((seg) => {
            const isActive = seg === active;
            return (
              <button
                key={seg}
                type="button"
                aria-pressed={isActive}
                onClick={() => setActive(seg)}
                className="text-[11px] tracking-wider uppercase font-data px-3 py-1.5 rounded transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--qgi-accent)]"
                style={{
                  backgroundColor: isActive ? "var(--qgi-accent)" : "transparent",
                  color: isActive ? "var(--qgi-bg)" : "var(--qgi-text-muted)",
                  fontWeight: isActive ? 600 : 400,
                }}
              >
                {seg}
              </button>
            );
          })}
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="text-sm py-8 text-center" style={{ color: "var(--qgi-text-dim)" }}>
          No reports in this category yet.
        </p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {filtered.map((report) => (
            <ReportCard key={report.slug} report={report} />
          ))}
        </div>
      )}
    </div>
  );
}
