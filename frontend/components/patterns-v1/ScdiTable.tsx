"use client";

import { useState } from "react";
import { pearsonPValue, formatPValue, significanceLabel } from "@/lib/stats";
import {
  sectorColor,
  sectorChipBg,
  correlationColor,
  significanceColor,
} from "@/lib/design";
import { InfoTooltip } from "@/components/design/InfoTooltip";

interface ScdiRow {
  index_name: string;
  sector: string;
  org: string;
  correlation: number;
  predicted: boolean;
  // #125: optional values arrays — when present we compute n + p-value
  values_a?: Array<number | null>;
  values_b?: Array<number | null>;
}

interface Props {
  scdis: ScdiRow[];
  activeSectors?: string[];
  onSectorFilter?: (sectors: string[]) => void;
  onRowSelect?: (indexName: string) => void;
  selectedIndex?: string | null;
}

// #126: SECTOR_COLORS moved to lib/design.ts — import from there.

export function ScdiTable({ scdis, onRowSelect, selectedIndex }: Props) {
  const [sortKey, setSortKey] = useState<"correlation" | "index_name" | "sector">(
    "correlation"
  );
  const [sortAsc, setSortAsc] = useState(false);
  const [sectorFilter, setSectorFilter] = useState<string[]>([]);

  const allSectors = Array.from(new Set(scdis.map((s) => s.sector))).sort();

  function toggleSort(key: typeof sortKey) {
    if (sortKey === key) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  function toggleSector(s: string) {
    setSectorFilter((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
  }

  const visible = scdis
    .filter((s) => sectorFilter.length === 0 || sectorFilter.includes(s.sector))
    .sort((a, b) => {
      const dir = sortAsc ? 1 : -1;
      if (sortKey === "correlation") return (a.correlation - b.correlation) * dir;
      return a[sortKey].localeCompare(b[sortKey]) * dir;
    });

  const SortIndicator = ({ col }: { col: typeof sortKey }) =>
    sortKey === col ? (sortAsc ? "↑" : "↓") : "";

  return (
    // T14 #307 HIGH fix (2026-04-19): table was a fixed 7-column grid
    // totalling ~500px wide. On mobile (375px viewport) columns either
    // crushed the Indicator name or pushed off-screen. Wrap in
    // overflow-x-auto with a min-width so users can swipe the table
    // horizontally on small screens until a full responsive redesign lands.
    <div className="flex flex-col overflow-x-auto">
      <div style={{ minWidth: 500 }}>
        {/* Sector filter chips */}
        <div
          className="flex flex-wrap gap-1.5 px-4 py-2 border-b"
          style={{ borderColor: "var(--qgi-border)" }}
        >
          {allSectors.map((s) => (
            <button
              key={s}
              onClick={() => toggleSector(s)}
              className="text-[9px] rounded px-2 py-0.5 transition-colors"
              style={{
                color: sectorFilter.includes(s) ? "var(--qgi-bg)" : sectorColor(s),
                backgroundColor: sectorFilter.includes(s)
                  ? sectorColor(s)
                  : sectorChipBg(s),
              }}
            >
              {s.toUpperCase()}
            </button>
          ))}
          {sectorFilter.length > 0 && (
            <button
              onClick={() => setSectorFilter([])}
              className="text-[9px] px-2 py-0.5"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              ✕ clear
            </button>
          )}
        </div>

        {/* Table header */}
        <div
          className="grid text-[9px] tracking-widest uppercase px-4 py-2 border-b"
          style={{
            gridTemplateColumns: "1fr 80px 80px 70px 50px 70px 40px",
            color: "var(--qgi-text-dim)",
            borderColor: "var(--qgi-border)",
          }}
        >
          <button onClick={() => toggleSort("index_name")} className="text-left">
            INDICATOR {SortIndicator({ col: "index_name" })}
          </button>
          {/*
           * #738 item 2 fix (2026-05-16, WCAG 4.1.2): InfoTooltip used to
           * be nested inside the sort <button>. Even though InfoTooltip
           * renders its trigger as `<span role="button">` (not a real
           * <button> element — pre-empting React's hydration error from
           * #567), nesting two interactive controls — one of them with
           * `role="button"` — fails 4.1.2's "no nested interactive
           * descendants" guidance and causes some screen readers to
           * double-announce the role on focus. Restructured into a
           * sibling flex container: <button> + <InfoTooltip> stand
           * side-by-side, each independently focusable + accessible.
           */}
          <span className="flex items-center gap-0.5">
            <button onClick={() => toggleSort("sector")} className="text-left">
              SECTOR {SortIndicator({ col: "sector" })}
            </button>
            <InfoTooltip text="The macro-sector this indicator measures (Economic, Demographic, Health, Governance, Infrastructure, etc.). Used for sector-coverage scoring and rose-chart filtering." />
          </span>
          <span className="flex items-center gap-0.5">
            SOURCE
            <InfoTooltip text="The data provider that publishes this indicator. Currently mostly World Bank; FAOSTAT, V-Dem, ILOSTAT being added." />
          </span>
          <span className="flex items-center justify-end gap-0.5">
            <button onClick={() => toggleSort("correlation")} className="text-right">
              R {SortIndicator({ col: "correlation" })}
            </button>
            <InfoTooltip text="Pearson correlation coefficient between Country A's and Country B's value series for this indicator across the pattern window. Ranges -1 to +1. Closer to +/-1 = tighter linear relationship." />
          </span>
          <span className="text-right flex items-center justify-end gap-0.5">
            N
            <InfoTooltip text="Number of matched data points (years) used to compute R. Patterns with low N are statistically weaker even at high R." />
          </span>
          <span className="text-right flex items-center justify-end gap-0.5">
            P-VALUE
            <InfoTooltip text="Probability that the observed correlation could occur by chance. p < 0.05 = statistically significant. *** = p < 0.001, ** = p < 0.01, * = p < 0.05, ns = not significant." />
          </span>
          <span></span>
        </div>

        {/* Rows */}
        {visible.map((row, i) => {
          // #125: compute n + p-value from the actual values arrays when present.
          // Falls back to "—" if the route didn't supply values (older routes).
          const va = row.values_a ?? [];
          const vb = row.values_b ?? [];
          let n = 0;
          for (let j = 0; j < Math.min(va.length, vb.length); j++) {
            if (
              va[j] != null &&
              vb[j] != null &&
              Number.isFinite(va[j]) &&
              Number.isFinite(vb[j])
            )
              n++;
          }
          const p = n >= 3 ? pearsonPValue(row.correlation, n) : NaN;
          const sig = significanceLabel(p);
          const sigCol = significanceColor(sig);

          return (
            <button
              key={i}
              onClick={() => onRowSelect?.(row.index_name)}
              className="grid items-center px-4 py-2.5 border-b text-xs transition-colors hover:bg-[var(--qgi-surface-2)] text-left"
              style={{
                gridTemplateColumns: "1fr 80px 80px 70px 50px 70px 40px",
                borderColor: "var(--qgi-border)",
                backgroundColor:
                  selectedIndex === row.index_name
                    ? "var(--qgi-surface-2)"
                    : "transparent",
              }}
            >
              <span className="truncate pr-2" style={{ color: "var(--qgi-text)" }}>
                {row.index_name}
                {row.predicted && (
                  <span
                    className="ml-2 text-[9px] rounded px-1.5 py-0.5"
                    style={{
                      color: "var(--qgi-predicted)",
                      backgroundColor: "rgba(107,127,150,0.15)",
                    }}
                  >
                    PREDICTED
                  </span>
                )}
              </span>
              <span
                className="text-[9px] truncate"
                style={{ color: sectorColor(row.sector) }}
              >
                {row.sector}
              </span>
              <span
                className="text-[9px] truncate"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                {row.org}
              </span>
              <span
                className="text-right font-data font-semibold"
                style={{ color: correlationColor(row.correlation) }}
              >
                {row.correlation.toFixed(3)}
              </span>
              <span
                className="text-right font-data text-[10px]"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                {n > 0 ? n : "–"}
              </span>
              <span
                className="text-right font-data text-[10px]"
                style={{ color: sigCol }}
              >
                {n >= 3 ? `${formatPValue(p)} ${sig}` : "–"}
              </span>
              <span
                className="text-center text-[10px]"
                style={{ color: "var(--qgi-text-dim)" }}
              >
                {selectedIndex === row.index_name ? "●" : "○"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
