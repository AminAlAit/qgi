/**
 * InsightPlots — V4.1 confidence-first dashboard.
 *
 * 4 audience-facing summary visuals that answer "what is QGI?" in 30s:
 *   1. CoverageMapPlot          — countries scored, region breakdown
 *   2. FamilyDistributionPlot   — recipe catalog across the 8 L1 families
 *   3. IndicatorCorpusPlot      — signal sources stacked
 *   4. TopPairTeaserPlot        — top historical resemblances
 *
 * All four are server components rendering inline SVG / DOM. No client
 * state, no charting library — keeps bundle small and SSR-safe.
 *
 * Per V4.1 rules §7: the plots invoke curiosity. They are not the user's
 * methodology audit; they are the showroom signage.
 */

import Link from "next/link";
import type { Route } from "next";
import { PanelBase } from "./PanelBase";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import type {
  FamilyDistribSlice,
  CoverageSummary,
  IndicatorCorpusStat,
  CountryPairTeaser,
} from "@/lib/te-mock/dashboard-v4-1-data";

const CALM_SLATE_BLUE = "#5B7E99";
const NEUTRAL_SLATE = "#7A8FA0";

// ───────────────────────────────────────────────────────────────────────────────
// 1. Coverage summary
// ───────────────────────────────────────────────────────────────────────────────

export function CoverageMapPlot({ data }: { data: CoverageSummary }) {
  return (
    <PanelBase
      title="Global coverage"
      caption="Every country in the roster gets scored on every trend in the catalog, every release."
      accent={CALM_SLATE_BLUE}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: "20px",
          alignItems: "center",
        }}
      >
        {/* Big number */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-start",
            padding: "12px 16px 12px 0",
            borderRight: "1px solid var(--qgi-border)",
            paddingRight: "20px",
          }}
        >
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontWeight: 700,
              fontSize: "44px",
              color: "#38bdf8",
              lineHeight: 1,
              letterSpacing: "-1px",
            }}
          >
            {data.countries_scored}
          </div>
          <div
            style={{
              fontSize: "10.5px",
              letterSpacing: "1px",
              textTransform: "uppercase",
              color: "var(--qgi-text-muted)",
              marginTop: "6px",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            countries scored
          </div>
          <div
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              marginTop: "6px",
            }}
          >
            of {data.roster} in the global roster
          </div>
        </div>

        {/* Region bars */}
        <div style={{ display: "flex", flexDirection: "column", gap: "7px" }}>
          {data.region_breakdown.map((r) => (
            <div key={r.region}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "11px",
                  marginBottom: "3px",
                  color: "var(--qgi-text)",
                }}
              >
                <span>{r.region}</span>
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    color: "var(--qgi-text-dim)",
                  }}
                >
                  {Math.round(r.pct)}%
                </span>
              </div>
              <div
                style={{
                  height: "6px",
                  background: "var(--qgi-bg)",
                  borderRadius: "3px",
                  overflow: "hidden",
                  border: "1px solid var(--qgi-border)",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${r.pct}%`,
                    background: "#38bdf8",
                    opacity: 0.85,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </PanelBase>
  );
}

// ───────────────────────────────────────────────────────────────────────────────
// 2. Family distribution donut
// ───────────────────────────────────────────────────────────────────────────────

export function FamilyDistributionPlot({ slices }: { slices: FamilyDistribSlice[] }) {
  const total = slices.reduce((acc, s) => acc + s.count, 0);
  // Donut radius/stroke setup.
  const size = 140;
  const strokeWidth = 22;
  const radius = size / 2 - strokeWidth / 2;
  const circumference = 2 * Math.PI * radius;

  // Precompute per-slice (dash, gap, offset) in a single pass. The earlier
  // pattern accumulated `offset` inside the .map() callback, which trips
  // react-hooks/no-mutating-rendered-state — pure functional reduce avoids
  // the lint and is the same shape at runtime.
  const segments = slices.reduce<
    Array<{
      family_id: string;
      color: string;
      dash: number;
      gap: number;
      offset: number;
    }>
  >((acc, s) => {
    const last = acc[acc.length - 1];
    const cumulativeOffset = last ? last.offset + last.dash : 0;
    const slicePct = total > 0 ? s.count / total : 0;
    const dash = slicePct * circumference;
    const gap = circumference - dash;
    acc.push({
      family_id: s.family_id,
      color: s.color,
      dash,
      gap,
      offset: cumulativeOffset,
    });
    return acc;
  }, []);

  return (
    <PanelBase
      title="What the catalog covers"
      caption="Trends span eight risk families, from political power to humanitarian crisis."
      accent={CALM_SLATE_BLUE}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `${size + 24}px 1fr`,
          gap: "20px",
          alignItems: "center",
        }}
      >
        {/* Donut */}
        <div style={{ position: "relative", width: size, height: size }}>
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke="var(--qgi-bg)"
              strokeWidth={strokeWidth}
            />
            {segments.map((seg) => (
              <circle
                key={seg.family_id}
                cx={size / 2}
                cy={size / 2}
                r={radius}
                fill="none"
                stroke={seg.color}
                strokeWidth={strokeWidth}
                strokeDasharray={`${seg.dash} ${seg.gap}`}
                strokeDashoffset={-seg.offset}
                transform={`rotate(-90 ${size / 2} ${size / 2})`}
              />
            ))}
          </svg>
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "28px",
                fontWeight: 700,
                color: "var(--qgi-text)",
                lineHeight: 1,
              }}
            >
              {total}
            </div>
            <div
              style={{
                fontSize: "9.5px",
                letterSpacing: "1px",
                textTransform: "uppercase",
                color: "var(--qgi-text-dim)",
                marginTop: "4px",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              trends
            </div>
          </div>
        </div>

        {/* Legend */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            columnGap: "14px",
            rowGap: "6px",
          }}
        >
          {slices.map((s) => (
            <div
              key={s.family_id}
              style={{ display: "flex", alignItems: "center", gap: "8px" }}
            >
              <span
                aria-hidden="true"
                style={{
                  display: "inline-block",
                  width: "10px",
                  height: "10px",
                  borderRadius: "2px",
                  background: s.color,
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--qgi-text)",
                  flex: 1,
                  minWidth: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {s.family_label}
              </span>
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--qgi-text-dim)",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                {s.count}
              </span>
            </div>
          ))}
        </div>
      </div>
    </PanelBase>
  );
}

// ───────────────────────────────────────────────────────────────────────────────
// 3. Indicator corpus stack
// ───────────────────────────────────────────────────────────────────────────────

export function IndicatorCorpusPlot({ stats }: { stats: IndicatorCorpusStat[] }) {
  const total = stats.reduce((acc, s) => acc + s.count, 0);
  return (
    <PanelBase
      title="Signal sources"
      caption="Every trend is built from a curated mix of institutional, governance, and economic series."
      accent={CALM_SLATE_BLUE}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        {/* Stacked bar */}
        <div
          style={{
            display: "flex",
            height: "16px",
            borderRadius: "4px",
            overflow: "hidden",
            border: "1px solid var(--qgi-border)",
          }}
        >
          {stats.map((s) => (
            <div
              key={s.label}
              style={{
                width: `${(s.count / total) * 100}%`,
                background: s.color,
                opacity: 0.9,
              }}
              title={`${s.label} · ${s.count}`}
            />
          ))}
        </div>

        {/* Legend */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            columnGap: "14px",
            rowGap: "5px",
          }}
        >
          {stats.map((s) => (
            <div
              key={s.label}
              style={{ display: "flex", alignItems: "center", gap: "8px" }}
            >
              <span
                aria-hidden="true"
                style={{
                  display: "inline-block",
                  width: "10px",
                  height: "10px",
                  borderRadius: "2px",
                  background: s.color,
                  flexShrink: 0,
                }}
              />
              <span style={{ fontSize: "11px", color: "var(--qgi-text)", flex: 1 }}>
                {s.label}
              </span>
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--qgi-text-dim)",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                {s.count}
              </span>
            </div>
          ))}
        </div>

        <div
          style={{
            fontSize: "10.5px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            paddingTop: "4px",
            borderTop: "1px solid var(--qgi-border)",
          }}
        >
          {total} signals tracked across {stats.length} providers.
        </div>
      </div>
    </PanelBase>
  );
}

// ───────────────────────────────────────────────────────────────────────────────
// 4. Top pair teasers — historical resemblances
// ───────────────────────────────────────────────────────────────────────────────

export function TopPairTeaserPlot({ pairs }: { pairs: CountryPairTeaser[] }) {
  if (pairs.length === 0) {
    return null;
  }
  return (
    <PanelBase
      title="Historical resemblances"
      caption="The closest matches between today's countries and the historical record."
      accent={CALM_SLATE_BLUE}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {pairs.map((p, i) => (
          <Link
            key={`${p.country_a}-${p.country_b}-${i}`}
            href={"/analogues" as Route}
            style={{
              textDecoration: "none",
              color: "inherit",
              display: "block",
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) auto",
                gap: "12px",
                alignItems: "center",
                padding: "10px 12px",
                background: "var(--qgi-bg)",
                border: "1px solid var(--qgi-border)",
                borderLeft: `3px solid ${NEUTRAL_SLATE}`,
                borderRadius: "6px",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: "13px",
                    fontWeight: 600,
                    color: "var(--qgi-text)",
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    flexWrap: "wrap",
                    lineHeight: 1.3,
                  }}
                >
                  <FlagImg emoji={flagFor(p.country_a)} name={p.country_a} width={18} />
                  <span>{p.country_a}</span>
                  <span style={{ color: "var(--qgi-text-dim)" }}>resembles</span>
                  <FlagImg emoji={flagFor(p.country_b)} name={p.country_b} width={18} />
                  <span>
                    {p.country_b} {p.country_b_year}
                  </span>
                </div>
                <div
                  style={{
                    fontSize: "11px",
                    color: "var(--qgi-text-muted)",
                    marginTop: "4px",
                  }}
                >
                  on the {p.recipe_label} trend shape
                </div>
              </div>
              <div
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontWeight: 700,
                  fontSize: "18px",
                  color: "#38bdf8",
                  letterSpacing: "-0.3px",
                  whiteSpace: "nowrap",
                }}
              >
                {Math.round(p.match_pct)}%
              </div>
            </div>
          </Link>
        ))}
      </div>
    </PanelBase>
  );
}
