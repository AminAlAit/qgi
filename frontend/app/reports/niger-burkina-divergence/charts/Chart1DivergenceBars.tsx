"use client";

import { useState } from "react";

type Row = {
  country: string;
  slug: string;
  score: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  rank: string;
  highlight?: boolean;
  note?: string;
};

const DIVERGENCE_DATA: ReadonlyArray<Row> = [
  {
    country: "Niger",
    slug: "niger",
    score: 94,
    ciLow: 84,
    ciHigh: 100,
    rank: "#4 of 58",
    highlight: true,
  },
  {
    country: "Burkina Faso",
    slug: "burkina_faso",
    score: 2,
    ciLow: 0,
    ciHigh: 5,
    rank: "#57 of 58",
  },
  {
    country: "Mali",
    slug: "mali",
    score: null,
    ciLow: null,
    ciHigh: null,
    rank: "no signal",
    note: "No Multilateral Agreement score in current run",
  },
];

type HoverState = string | null;

function ChartBody({ size }: { size: "hero" | "inline" }) {
  const [hovered, setHovered] = useState<HoverState>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 100;
  const barH = size === "hero" ? 30 : 22;
  const groupGap = size === "hero" ? 36 : 28;
  const labelW = size === "hero" ? 130 : 110;
  const chartW = size === "hero" ? 540 : 380;
  const valueW = 90;
  const svgH = DIVERGENCE_DATA.length * (barH + groupGap) + 20;

  const handleMouseEnter = (
    e: React.MouseEvent<SVGRectElement | SVGGElement>,
    country: string
  ) => {
    const svg = (
      e.currentTarget.closest("svg") as SVGSVGElement
    )?.getBoundingClientRect();
    const target = e.currentTarget.getBoundingClientRect();
    if (svg) {
      setTooltipPos({
        x: target.right - svg.left + 10,
        y: target.top - svg.top + target.height / 2,
      });
    }
    setHovered(country);
  };

  const handleMouseLeave = () => setHovered(null);

  return (
    <>
      <svg
        viewBox={`0 0 ${labelW + chartW + valueW + 8} ${svgH}`}
        width="100%"
        aria-label="Horizontal bar chart of Multilateral Agreement Precedent Match scores for Niger, Burkina Faso, and Mali"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          Niger #4 (94/100), Burkina Faso #57 (2/100), Mali no signal: Multilateral
          Agreement Precedent Match scores, April 2026 scoring run.
        </title>
        {DIVERGENCE_DATA.map((row, i) => {
          const y = i * (barH + groupGap) + 10;
          const w = row.score != null ? Math.round((row.score / maxVal) * chartW) : 0;
          const ciL = row.ciLow != null ? Math.round((row.ciLow / maxVal) * chartW) : 0;
          const ciH = row.ciHigh != null ? Math.round((row.ciHigh / maxVal) * chartW) : 0;
          const isMissing = row.score === null;
          const fill = row.highlight
            ? "#a78bfa"
            : isMissing
              ? "rgba(255,255,255,0.08)"
              : "rgba(251,191,36,0.7)";
          const opacity = hovered && hovered !== row.country ? 0.3 : 1;

          return (
            <g key={row.country}>
              {/* Country label */}
              <text
                x={labelW - 8}
                y={y + barH / 2 + 4}
                textAnchor="end"
                fontSize={size === "hero" ? "14" : "12"}
                fontFamily="sans-serif"
                fill={row.highlight ? "var(--qgi-text)" : "var(--qgi-text-dim)"}
                fontWeight={row.highlight ? "600" : "400"}
                style={{ opacity }}
              >
                {row.country}
              </text>
              <text
                x={labelW - 8}
                y={y + barH / 2 + (size === "hero" ? 19 : 17)}
                textAnchor="end"
                fontSize={size === "hero" ? "10" : "9"}
                fontFamily="var(--font-data, monospace)"
                fill="var(--qgi-text-muted)"
                style={{ opacity }}
              >
                {row.rank}
              </text>
              {/* CI bracket for non-missing rows */}
              {!isMissing && (
                <>
                  <line
                    x1={labelW + ciL}
                    x2={labelW + ciH}
                    y1={y + barH / 2}
                    y2={y + barH / 2}
                    stroke="var(--qgi-text-muted)"
                    strokeWidth={1}
                    strokeDasharray="2 2"
                    opacity={opacity * 0.6}
                  />
                  <line
                    x1={labelW + ciL}
                    x2={labelW + ciL}
                    y1={y + barH / 2 - 4}
                    y2={y + barH / 2 + 4}
                    stroke="var(--qgi-text-muted)"
                    strokeWidth={1}
                    opacity={opacity * 0.6}
                  />
                  <line
                    x1={labelW + ciH}
                    x2={labelW + ciH}
                    y1={y + barH / 2 - 4}
                    y2={y + barH / 2 + 4}
                    stroke="var(--qgi-text-muted)"
                    strokeWidth={1}
                    opacity={opacity * 0.6}
                  />
                </>
              )}
              {/* Main score bar */}
              <rect
                x={labelW}
                y={y}
                width={isMissing ? chartW : w}
                height={barH}
                rx={3}
                fill={fill}
                opacity={opacity}
                stroke={isMissing ? "var(--qgi-border)" : "none"}
                strokeDasharray={isMissing ? "4 3" : undefined}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, row.country)}
                onMouseLeave={handleMouseLeave}
                aria-label={
                  isMissing
                    ? `${row.country}: ${row.note}`
                    : `${row.country}: ${row.score}/100, ${row.rank}`
                }
              />
              {/* Value label */}
              {!isMissing ? (
                <text
                  x={labelW + w + 6}
                  y={y + barH / 2 + 4}
                  fontSize={size === "hero" ? "13" : "11"}
                  fontFamily="var(--font-data, monospace)"
                  fill={row.highlight ? "#a78bfa" : "rgba(251,191,36,0.9)"}
                  fontWeight="600"
                  style={{ pointerEvents: "none", opacity }}
                >
                  {row.score}/100
                </text>
              ) : (
                <text
                  x={labelW + chartW / 2}
                  y={y + barH / 2 + 4}
                  textAnchor="middle"
                  fontSize={size === "hero" ? "11" : "10"}
                  fontFamily="sans-serif"
                  fontStyle="italic"
                  fill="var(--qgi-text-muted)"
                  style={{ pointerEvents: "none", opacity }}
                >
                  no signal in current run
                </text>
              )}
            </g>
          );
        })}
        {/* Recipe label */}
        <text
          x={labelW + chartW / 2}
          y={svgH - 4}
          textAnchor="middle"
          fontSize="10"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
        >
          Multilateral Agreement recipe Precedent Match (0&ndash;100, with 95% CI bracket)
        </text>
      </svg>

      {/* Tooltip */}
      {hovered &&
        (() => {
          const row = DIVERGENCE_DATA.find((r) => r.country === hovered);
          if (!row) return null;
          return (
            <div
              style={{
                position: "absolute",
                left: tooltipPos.x,
                top: tooltipPos.y,
                transform: "translateY(-50%)",
                width: 220,
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
              <div style={{ color: "var(--qgi-text)", fontWeight: 600, marginBottom: 4 }}>
                {row.country}
              </div>
              <div style={{ color: "var(--qgi-text-muted)", marginBottom: 4 }}>
                Multilateral Agreement
              </div>
              {row.score != null ? (
                <>
                  <div
                    style={{
                      fontFamily: "var(--font-data, monospace)",
                      color: row.highlight ? "#a78bfa" : "#fbbf24",
                      fontSize: 14,
                      margin: "4px 0",
                    }}
                  >
                    {row.score}/100
                  </div>
                  <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                    95% CI {row.ciLow}&ndash;{row.ciHigh} &middot; {row.rank}
                  </div>
                </>
              ) : (
                <div
                  style={{
                    color: "var(--qgi-text-dim)",
                    fontSize: 10,
                    fontStyle: "italic",
                  }}
                >
                  {row.note}
                </div>
              )}
            </div>
          );
        })()}
    </>
  );
}

export default function Chart1DivergenceBars() {
  return (
    <figure
      id="niger-burkina-divergence-bars"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <ChartBody size="inline" />
      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Multilateral Agreement Precedent Match scores: Niger ranks #4 of 58 (94/100, 95%
        CI 84&ndash;100). Burkina Faso ranks #57 of 58 (2/100, CI 0&ndash;5). Mali has no
        Multilateral Agreement signal in the April 2026 scoring run. Source: QGI
        computation, April 2026 scoring run (QGI V1.9.1).
      </figcaption>
    </figure>
  );
}

export function Chart1DivergenceBarsHero() {
  return (
    <figure
      id="niger-burkina-divergence-hero"
      className="my-2 relative"
      style={{ maxWidth: "100%" }}
    >
      <ChartBody size="hero" />
    </figure>
  );
}
