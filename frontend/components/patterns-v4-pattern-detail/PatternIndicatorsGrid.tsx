"use client";

/**
 * PatternIndicatorsGrid — §4 Pattern Indicators grid.
 *
 * Kicker: INDICATOR DETAIL
 * Heading: "Each signal, side by side"
 * Body: 2-column desktop / 1-column mobile card grid.
 *
 * Each card:
 *   - 3px left accent stripe: sector color (same direction) or OPPOSITE_DIRECTION_COLOR
 *   - Indicator name + sector label (9px monospace chip)
 *   - Side-by-side 120×32 sparklines: country A left, B right
 *     with 10px monospace country names above
 *   - Pearson r with lerpHexToRgb gradient typography + confidenceGlow
 *   - Direction chip: "Same direction" (muted green) | "Opposite direction" (muted teal)
 *
 * Sort: r desc by default; also r_desc, sector, direction.
 * URL state: ?sort=r_desc (default), ?sort=sector, ?sort=direction.
 * Filter chips: "All" + one per sector present.
 * Show first 20 cards; "Show all {N} signals" expander at 21+.
 *
 * V4.1 rules (binding):
 *   - No engine vocabulary (no SCDI, no cascade, no Pearson r in user-facing label)
 *   - User copy: "Pattern Indicator", not "SCDI"
 *   - r shown as number (r = 0.87), no jargon labels
 *   - Confidence color via lerpHexToRgb + confidenceGlow (same as recipe cards)
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import type { PatternIndicator } from "@/lib/cascade-patterns/scdi-mock";
import { sectorColor, OPPOSITE_DIRECTION_COLOR } from "@/lib/cascade-patterns/sector-colors";
import { MUTED_GRAY, lerpHexToRgb, confidenceGlow } from "@/lib/color-lerp";

type SortKey = "r_desc" | "sector" | "direction";

const EXPAND_THRESHOLD = 20;

// ── Sparkline helpers ────────────────────────────────────────────────────

function Sparkline({
  series,
  color,
  width = 120,
  height = 32,
}: {
  series: number[];
  color: string;
  width?: number;
  height?: number;
}) {
  if (series.length < 2) return null;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max - min || 1;
  const pad = 3;

  const path = series
    .map((v, i) => {
      const x = pad + (i / (series.length - 1)) * (width - pad * 2);
      const y = pad + (1 - (v - min) / range) * (height - pad * 2);
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      style={{ display: "block" }}
    >
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// ── Direction chip ────────────────────────────────────────────────────────

function DirectionChip({ direction }: { direction: "same" | "opposite" }) {
  const isSame = direction === "same";
  const color = isSame ? "#7A9A6A" : OPPOSITE_DIRECTION_COLOR;
  const label = isSame ? "Same direction" : "Opposite direction";
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "2px 8px",
        borderRadius: "12px",
        border: `1px solid ${color}50`,
        background: `${color}15`,
        fontSize: "10px",
        color,
        fontFamily: "ui-monospace, monospace",
        fontWeight: 600,
        letterSpacing: "0.3px",
      }}
    >
      <span style={{ fontSize: "8px" }}>{isSame ? "↑↑" : "↑↓"}</span>
      {label}
    </div>
  );
}

// ── Single indicator card ─────────────────────────────────────────────────

function IndicatorCard({
  indicator,
  countryA,
  countryB,
}: {
  indicator: PatternIndicator;
  countryA: string;
  countryB: string;
}) {
  const stripeColor =
    indicator.direction === "same"
      ? sectorColor(indicator.sector)
      : OPPOSITE_DIRECTION_COLOR;

  // Map pearson_r (0-1) to confidence t: r=0.6 → t=0, r=1.0 → t=1.
  const t = Math.max(0, Math.min(1, (indicator.pearson_r - 0.6) / 0.4));
  const rColor = lerpHexToRgb(MUTED_GRAY, "#FFFFFF", t);
  const rGlow = confidenceGlow("#FFFFFF", t);

  const colorA = sectorColor(indicator.sector);
  const colorB = indicator.direction === "same" ? `${colorA}99` : OPPOSITE_DIRECTION_COLOR;

  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* 3px left accent stripe + content */}
      <div style={{ display: "flex", flex: 1 }}>
        {/* Accent stripe */}
        <div
          style={{
            width: "3px",
            background: stripeColor,
            flexShrink: 0,
          }}
        />

        <div style={{ flex: 1, padding: "12px 14px" }}>
          {/* Sector chip + indicator name */}
          <div style={{ marginBottom: "8px" }}>
            <span
              style={{
                fontSize: "9px",
                fontFamily: "ui-monospace, monospace",
                color: stripeColor,
                letterSpacing: "1px",
                fontWeight: 600,
                textTransform: "uppercase" as const,
              }}
            >
              {indicator.sector}
            </span>
            <div
              style={{
                fontSize: "12px",
                fontWeight: 600,
                color: "var(--qgi-text)",
                lineHeight: 1.35,
                marginTop: "2px",
              }}
            >
              {indicator.name}
            </div>
          </div>

          {/* Sparklines side-by-side */}
          <div
            style={{
              display: "flex",
              gap: "10px",
              marginBottom: "10px",
            }}
          >
            {/* Country A */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
              <span
                style={{
                  fontSize: "10px",
                  fontFamily: "ui-monospace, monospace",
                  color: "var(--qgi-text-dim)",
                  marginBottom: "2px",
                  letterSpacing: "0.3px",
                }}
              >
                {countryA.slice(0, 12)}
              </span>
              <Sparkline series={indicator.series_a} color={colorA} />
            </div>

            {/* Country B */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start" }}>
              <span
                style={{
                  fontSize: "10px",
                  fontFamily: "ui-monospace, monospace",
                  color: "var(--qgi-text-dim)",
                  marginBottom: "2px",
                  letterSpacing: "0.3px",
                }}
              >
                {countryB.slice(0, 12)}
              </span>
              <Sparkline series={indicator.series_b} color={colorB} />
            </div>
          </div>

          {/* Footer: r value + direction chip */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "6px",
            }}
          >
            <span
              style={{
                fontSize: "13px",
                fontFamily: "ui-monospace, monospace",
                fontWeight: 700,
                color: rColor,
                textShadow: rGlow || undefined,
                letterSpacing: "0.3px",
              }}
            >
              r = {indicator.pearson_r.toFixed(2)}
            </span>
            <DirectionChip direction={indicator.direction} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main grid component ───────────────────────────────────────────────────

interface PatternIndicatorsGridProps {
  indicators: PatternIndicator[];
  countryA: string;
  countryB: string;
  /** Initial sort key; can be overridden by URL params client-side. */
  initialSort?: SortKey;
}

export function PatternIndicatorsGrid({
  indicators,
  countryA,
  countryB,
  initialSort = "r_desc",
}: PatternIndicatorsGridProps) {
  const [sortKey, setSortKey] = useState<SortKey>(() => {
    if (typeof window !== "undefined") {
      try {
        const params = new URLSearchParams(window.location.search);
        const s = params.get("sort") as SortKey | null;
        if (s && ["r_desc", "sector", "direction"].includes(s)) {
          return s;
        }
      } catch {
        // SSR safety
      }
    }
    return initialSort;
  });
  const [activeFilter, setActiveFilter] = useState<string>("All");
  const [expanded, setExpanded] = useState(false);

  // Push sort to URL without navigation.
  const handleSort = useCallback((key: SortKey) => {
    setSortKey(key);
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("sort", key);
      window.history.replaceState(null, "", url.toString());
    } catch {
      // SSR safety
    }
  }, []);

  // Unique sectors for filter chips.
  const sectors = useMemo(() => {
    const s = new Set<string>();
    for (const ind of indicators) s.add(ind.sector);
    return Array.from(s).sort();
  }, [indicators]);

  // Filter.
  const filtered = useMemo(() => {
    if (activeFilter === "All") return indicators;
    return indicators.filter((i) => i.sector === activeFilter);
  }, [indicators, activeFilter]);

  // Sort.
  const sorted = useMemo(() => {
    const copy = [...filtered];
    switch (sortKey) {
      case "r_desc":
        return copy.sort((a, b) => b.pearson_r - a.pearson_r);
      case "sector":
        return copy.sort((a, b) => a.sector.localeCompare(b.sector) || b.pearson_r - a.pearson_r);
      case "direction":
        return copy.sort((a, b) => {
          if (a.direction === b.direction) return b.pearson_r - a.pearson_r;
          return a.direction === "same" ? -1 : 1;
        });
    }
  }, [filtered, sortKey]);

  const visible = expanded ? sorted : sorted.slice(0, EXPAND_THRESHOLD);
  const hasMore = sorted.length > EXPAND_THRESHOLD;

  const SORT_LABELS: Record<SortKey, string> = {
    r_desc: "Correlation",
    sector: "Sector",
    direction: "Direction",
  };

  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginBottom: "20px",
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: "16px" }}>
        <div
          style={{
            fontSize: "9px",
            letterSpacing: "1.6px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            marginBottom: "6px",
            fontWeight: 600,
          }}
        >
          INDICATOR DETAIL
        </div>
        <h2
          style={{
            fontSize: "15px",
            fontWeight: 700,
            margin: "0 0 12px",
            color: "var(--qgi-text)",
          }}
        >
          Each signal, side by side
        </h2>

        {/* Sort controls + filter chips row */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "8px",
            alignItems: "center",
          }}
        >
          {/* Sort by label */}
          <span
            style={{
              fontSize: "10px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
              letterSpacing: "0.3px",
              marginRight: "2px",
            }}
          >
            Sort:
          </span>
          {(["r_desc", "sector", "direction"] as SortKey[]).map((key) => (
            <button
              key={key}
              onClick={() => handleSort(key)}
              style={{
                padding: "3px 10px",
                borderRadius: "12px",
                border: `1px solid ${sortKey === key ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
                background: sortKey === key ? "var(--qgi-accent)15" : "transparent",
                color: sortKey === key ? "var(--qgi-accent)" : "var(--qgi-text-muted)",
                fontSize: "11px",
                fontFamily: "ui-monospace, monospace",
                cursor: "pointer",
                fontWeight: sortKey === key ? 600 : 400,
              }}
            >
              {SORT_LABELS[key]}
            </button>
          ))}

          {/* Separator */}
          <span style={{ color: "var(--qgi-border)", fontSize: "14px" }}>|</span>

          {/* Filter: All */}
          <button
            onClick={() => setActiveFilter("All")}
            style={{
              padding: "3px 10px",
              borderRadius: "12px",
              border: `1px solid ${activeFilter === "All" ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
              background: activeFilter === "All" ? "var(--qgi-accent)15" : "transparent",
              color: activeFilter === "All" ? "var(--qgi-accent)" : "var(--qgi-text-muted)",
              fontSize: "11px",
              fontFamily: "ui-monospace, monospace",
              cursor: "pointer",
              fontWeight: activeFilter === "All" ? 600 : 400,
            }}
          >
            All ({indicators.length})
          </button>

          {/* Filter: per sector */}
          {sectors.map((sector) => {
            const count = indicators.filter((i) => i.sector === sector).length;
            const isActive = activeFilter === sector;
            const color = sectorColor(sector);
            return (
              <button
                key={sector}
                onClick={() => setActiveFilter(sector)}
                style={{
                  padding: "3px 10px",
                  borderRadius: "12px",
                  border: `1px solid ${isActive ? color : "var(--qgi-border)"}`,
                  background: isActive ? `${color}20` : "transparent",
                  color: isActive ? color : "var(--qgi-text-muted)",
                  fontSize: "11px",
                  fontFamily: "ui-monospace, monospace",
                  cursor: "pointer",
                  fontWeight: isActive ? 600 : 400,
                }}
              >
                {sector} ({count})
              </button>
            );
          })}
        </div>
      </div>

      {/* Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "12px",
        }}
      >
        {visible.map((indicator) => (
          <IndicatorCard
            key={indicator.code}
            indicator={indicator}
            countryA={countryA}
            countryB={countryB}
          />
        ))}
      </div>

      {/* Show all expander */}
      {hasMore && !expanded && (
        <div style={{ marginTop: "16px", textAlign: "center" }}>
          <button
            onClick={() => setExpanded(true)}
            style={{
              padding: "8px 20px",
              borderRadius: "6px",
              border: "1px solid var(--qgi-border)",
              background: "transparent",
              color: "var(--qgi-text-muted)",
              fontSize: "12px",
              fontFamily: "ui-monospace, monospace",
              cursor: "pointer",
              letterSpacing: "0.3px",
            }}
          >
            Show all {sorted.length} indicators
          </button>
        </div>
      )}

      {expanded && hasMore && (
        <div style={{ marginTop: "16px", textAlign: "center" }}>
          <button
            onClick={() => setExpanded(false)}
            style={{
              padding: "8px 20px",
              borderRadius: "6px",
              border: "1px solid var(--qgi-border)",
              background: "transparent",
              color: "var(--qgi-text-muted)",
              fontSize: "12px",
              fontFamily: "ui-monospace, monospace",
              cursor: "pointer",
              letterSpacing: "0.3px",
            }}
          >
            Collapse
          </button>
        </div>
      )}
    </div>
  );
}
