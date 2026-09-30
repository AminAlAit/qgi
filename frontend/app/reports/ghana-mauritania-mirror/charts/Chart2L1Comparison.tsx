"use client";

import { useState } from "react";

const L1_DIMENSIONS = [
  {
    id: "A",
    label: "Political",
    fullName: "Political Power & Regime",
    ghana: 1.66,
    mauritania: 1.05,
  },
  {
    id: "B",
    label: "Conflict",
    fullName: "Conflict & Insurgency",
    ghana: 0,
    mauritania: 0,
  },
  {
    id: "C",
    label: "Governance",
    fullName: "Governance & Rule of Law",
    ghana: 0,
    mauritania: 0,
  },
  {
    id: "D",
    label: "Economic",
    fullName: "Economic & Financial Stress",
    ghana: 1.01,
    mauritania: 0.64,
  },
  {
    id: "E",
    label: "Social",
    fullName: "Social & Civil Unrest",
    ghana: 0.24,
    mauritania: 0.18,
  },
  {
    id: "F",
    label: "Diplomatic",
    fullName: "Diplomatic & Geopolitical",
    ghana: 0.5,
    mauritania: 0.5,
  },
  {
    id: "G",
    label: "Humanitarian",
    fullName: "Humanitarian & Displacement",
    ghana: 0,
    mauritania: 0.32,
  },
  {
    id: "H",
    label: "Structural",
    fullName: "Structural Vulnerability",
    ghana: 0,
    mauritania: 0.03,
  },
] as const;

type HoverState = {
  dimId: string;
  country: "ghana" | "mauritania";
} | null;

/** Variant for hero display (larger, 900x400) */
export function Chart2L1ComparisonHero() {
  return <Chart2L1ComparisonInner isHero />;
}

/** Standard in-article variant */
export default function Chart2L1Comparison() {
  return <Chart2L1ComparisonInner isHero={false} />;
}

function Chart2L1ComparisonInner({ isHero }: { isHero: boolean }) {
  const [hovered, setHovered] = useState<HoverState>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 2.0;
  const barW = isHero ? 30 : 22;
  const barGap = isHero ? 4 : 3;
  const groupGap = isHero ? 22 : 16;
  const labelH = isHero ? 44 : 38;
  const chartH = isHero ? 280 : 200;
  const svgW = L1_DIMENSIONS.length * (barW * 2 + barGap + groupGap) + groupGap + 20;

  const getBarProps = (dimId: string, country: "ghana" | "mauritania") => {
    if (!hovered) return { opacity: 1, stroke: "none", strokeWidth: 0 };
    if (hovered.dimId === dimId && hovered.country === country) {
      return { opacity: 1, stroke: "none", strokeWidth: 0 };
    }
    if (hovered.dimId === dimId && hovered.country !== country) {
      // Paired bar: accent stroke, not dimmed
      return { opacity: 1, stroke: "var(--qgi-accent)", strokeWidth: 1.5 };
    }
    // Other groups dim
    return { opacity: 0.25, stroke: "none", strokeWidth: 0 };
  };

  const handleMouseEnter = (
    e: React.MouseEvent<SVGRectElement>,
    dimId: string,
    country: "ghana" | "mauritania"
  ) => {
    const svgEl = e.currentTarget.closest("svg") as SVGSVGElement;
    const rect = svgEl?.getBoundingClientRect();
    const barRect = e.currentTarget.getBoundingClientRect();
    if (rect) {
      setTooltipPos({
        x: barRect.left - rect.left + barRect.width / 2,
        y: barRect.top - rect.top - 8,
      });
    }
    setHovered({ dimId, country });
  };

  const handleMouseLeave = () => setHovered(null);

  return (
    <figure
      id={isHero ? "ghana-l1-vs-mauritania-hero" : "ghana-l1-vs-mauritania"}
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${svgW} ${chartH + labelH + 20}`}
        width="100%"
        aria-label="Grouped bar chart comparing per-dimension L1 salience for Ghana and Mauritania across 8 dimensions"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          Per-dimension L1 salience: Ghana vs Mauritania (April 2026 scoring run)
        </title>
        {L1_DIMENSIONS.map((dim, i) => {
          const x = groupGap + i * (barW * 2 + barGap + groupGap);
          const ghanaH = Math.round((dim.ghana / maxVal) * chartH);
          const mauH = Math.round((dim.mauritania / maxVal) * chartH);
          const isActive = dim.id === "A" || dim.id === "D" || dim.id === "F";
          const ghanaProps = getBarProps(dim.id, "ghana");
          const mauProps = getBarProps(dim.id, "mauritania");

          return (
            <g key={dim.id}>
              {/* Ghana bar */}
              <rect
                x={x}
                y={chartH - ghanaH}
                width={barW}
                height={ghanaH || 2}
                rx={2}
                fill={isActive ? "#a78bfa" : "rgba(167,139,250,0.35)"}
                opacity={ghanaProps.opacity}
                stroke={ghanaProps.stroke}
                strokeWidth={ghanaProps.strokeWidth}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, dim.id, "ghana")}
                onMouseLeave={handleMouseLeave}
                aria-label={`Ghana dimension ${dim.id} salience ${dim.ghana}`}
              />
              {dim.ghana > 0 && (
                <text
                  x={x + barW / 2}
                  y={chartH - ghanaH - 3}
                  textAnchor="middle"
                  fontSize="9"
                  fontFamily="var(--font-data, monospace)"
                  fill={isActive ? "#a78bfa" : "rgba(167,139,250,0.6)"}
                  style={{ pointerEvents: "none" }}
                >
                  {dim.ghana}
                </text>
              )}
              {/* Mauritania bar */}
              <rect
                x={x + barW + barGap}
                y={chartH - mauH}
                width={barW}
                height={mauH || 2}
                rx={2}
                fill={isActive ? "#fbbf24" : "rgba(251,191,36,0.3)"}
                opacity={mauProps.opacity}
                stroke={mauProps.stroke}
                strokeWidth={mauProps.strokeWidth}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, dim.id, "mauritania")}
                onMouseLeave={handleMouseLeave}
                aria-label={`Mauritania dimension ${dim.id} salience ${dim.mauritania}`}
              />
              {dim.mauritania > 0 && (
                <text
                  x={x + barW + barGap + barW / 2}
                  y={chartH - mauH - 3}
                  textAnchor="middle"
                  fontSize="9"
                  fontFamily="var(--font-data, monospace)"
                  fill={isActive ? "#fbbf24" : "rgba(251,191,36,0.55)"}
                  style={{ pointerEvents: "none" }}
                >
                  {dim.mauritania}
                </text>
              )}
              {/* Dimension label */}
              <text
                x={x + barW}
                y={chartH + 12}
                textAnchor="middle"
                fontSize="11"
                fontFamily="var(--font-data, monospace)"
                fontWeight={isActive ? "700" : "400"}
                fill={isActive ? "var(--qgi-text)" : "var(--qgi-text-dim)"}
              >
                {dim.id}
              </text>
              <text
                x={x + barW}
                y={chartH + 26}
                textAnchor="middle"
                fontSize="9"
                fontFamily="sans-serif"
                fill="var(--qgi-text-dim)"
              >
                {dim.label}
              </text>
            </g>
          );
        })}
        {/* Legend */}
        <g transform={`translate(${groupGap}, ${chartH + labelH + 6})`}>
          <rect x={0} y={0} width={10} height={10} rx={2} fill="#a78bfa" />
          <text
            x={14}
            y={9}
            fontSize="10"
            fill="var(--qgi-text-dim)"
            fontFamily="sans-serif"
          >
            Ghana
          </text>
          <rect x={64} y={0} width={10} height={10} rx={2} fill="#fbbf24" />
          <text
            x={78}
            y={9}
            fontSize="10"
            fill="var(--qgi-text-dim)"
            fontFamily="sans-serif"
          >
            Mauritania
          </text>
          <text
            x={160}
            y={9}
            fontSize="9"
            fill="var(--qgi-text-muted)"
            fontFamily="sans-serif"
          >
            Bold = shared active dims (A / D / F)
          </text>
        </g>
      </svg>

      {/* Tooltip */}
      {hovered &&
        (() => {
          const dim = L1_DIMENSIONS.find((d) => d.id === hovered.dimId);
          if (!dim) return null;
          const isActive = dim.id === "A" || dim.id === "D" || dim.id === "F";
          const value = hovered.country === "ghana" ? dim.ghana : dim.mauritania;
          const countryName = hovered.country === "ghana" ? "Ghana" : "Mauritania";
          return (
            <div
              style={{
                position: "absolute",
                left: tooltipPos.x,
                top: tooltipPos.y,
                transform: "translate(-50%, -100%)",
                minWidth: 160,
                maxWidth: 220,
                backgroundColor: "var(--qgi-surface)",
                border: "1px solid var(--qgi-border)",
                borderRadius: 4,
                padding: "8px 10px",
                pointerEvents: "none",
                zIndex: 10,
                fontSize: 11,
                lineHeight: 1.5,
              }}
            >
              <div style={{ color: "var(--qgi-text)", fontWeight: 600, marginBottom: 2 }}>
                {dim.id}: {dim.fullName}
              </div>
              <div style={{ color: "var(--qgi-text-muted)" }}>{countryName}</div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color: hovered.country === "ghana" ? "#a78bfa" : "#fbbf24",
                  fontSize: 13,
                  margin: "4px 0",
                }}
              >
                {value === 0 ? `Zero signal for ${countryName}` : value.toFixed(2)}
              </div>
              {isActive && (
                <div style={{ color: "var(--qgi-accent)", fontSize: 10, marginTop: 2 }}>
                  Shared active dimension
                </div>
              )}
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Per-dimension L1 salience: Ghana vs Mauritania. Shared active dimensions A
        (Political Power &amp; Regime), D (Economic &amp; Financial Stress), and F
        (Diplomatic &amp; Geopolitical Relations) account for 99% of the cosine match
        (Political 66%, Economic 24%, Diplomatic 9%). Source: country-risks.json, April
        2026 scoring run.
      </figcaption>
    </figure>
  );
}
