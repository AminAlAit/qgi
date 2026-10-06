"use client";

import { useState } from "react";

const SALIENCE_BARS_DATA = [
  { window: "S", label: "Short", elections: 1.56, coup: 1.39 },
  { window: "M", label: "Medium", elections: 1.9, coup: 1.42 },
  { window: "L", label: "Long", elections: 2.76, coup: 0.8, highlight: true },
  { window: "XL", label: "Extra-Long", elections: 2.38, coup: null },
] as const;

type HoverState = {
  window: string;
  type: "elections" | "coup";
} | null;

export default function Chart1SalienceBars() {
  const [hovered, setHovered] = useState<HoverState>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 3;
  const barH = 14;
  const groupGap = 32;
  const barGap = 4;
  const labelW = 52;
  const chartW = 400;
  const svgH = SALIENCE_BARS_DATA.length * (barH * 2 + barGap + groupGap) + 20;

  const getBarOpacity = (window: string, type: "elections" | "coup") => {
    if (!hovered) return 1;
    if (hovered.window === window && hovered.type === type) return 1; // hovered bar
    if (hovered.window === window && hovered.type !== type) return 0.3; // sibling bar
    return 0.25; // other groups
  };

  const handleMouseEnter = (
    e: React.MouseEvent<SVGRectElement>,
    window: string,
    type: "elections" | "coup"
  ) => {
    const rect = (
      e.currentTarget.closest("svg") as SVGSVGElement
    )?.getBoundingClientRect();
    const barRect = e.currentTarget.getBoundingClientRect();
    if (rect) {
      setTooltipPos({
        x: barRect.right - rect.left + 8,
        y: barRect.top - rect.top + barRect.height / 2,
      });
    }
    setHovered({ window, type });
  };

  const handleMouseLeave = () => setHovered(null);

  return (
    <figure
      id="ghana-election-coup-salience-bars"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${labelW + chartW + 8} ${svgH}`}
        width="100%"
        aria-label="Grouped horizontal bar chart showing Ghana salience z-scores for Elections and Voting and Military Coup across S M L and XL tier windows"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          Ghana: Elections &amp; Voting vs Military Coup salience z-scores by tier window
        </title>
        {SALIENCE_BARS_DATA.map((row, i) => {
          const y = i * (barH * 2 + barGap + groupGap) + 10;
          const electW = Math.round((row.elections / maxVal) * chartW);
          const coupW = row.coup != null ? Math.round((row.coup / maxVal) * chartW) : 0;
          const isHighlight = "highlight" in row && row.highlight;
          const electOpacity = getBarOpacity(row.window, "elections");
          const coupOpacity = getBarOpacity(row.window, "coup");

          return (
            <g key={row.window}>
              <text
                x={labelW - 6}
                y={y + barH - 2}
                textAnchor="end"
                fontSize="11"
                fontFamily="var(--font-data, monospace)"
                fill="var(--qgi-text-dim)"
              >
                {row.window}-tier
              </text>
              {/* Elections & Voting bar */}
              <rect
                x={labelW}
                y={y}
                width={electW}
                height={barH}
                rx={2}
                fill={isHighlight ? "#a78bfa" : "rgba(167,139,250,0.65)"}
                opacity={electOpacity}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, row.window, "elections")}
                onMouseLeave={handleMouseLeave}
                aria-label={`Elections and Voting ${row.window} window z-score ${row.elections}`}
              />
              {isHighlight && (
                <text
                  x={labelW + electW + 4}
                  y={y + barH - 3}
                  fontSize="10"
                  fontFamily="var(--font-data, monospace)"
                  fill="#a78bfa"
                  fontWeight="600"
                  style={{ pointerEvents: "none" }}
                >
                  {row.elections}σ ▲ peak
                </text>
              )}
              {!isHighlight && (
                <text
                  x={labelW + electW + 4}
                  y={y + barH - 3}
                  fontSize="10"
                  fontFamily="var(--font-data, monospace)"
                  fill="rgba(167,139,250,0.85)"
                  style={{ pointerEvents: "none" }}
                >
                  {row.elections}σ
                </text>
              )}
              {/* Military Coup bar */}
              {row.coup != null ? (
                <>
                  <rect
                    x={labelW}
                    y={y + barH + barGap}
                    width={coupW}
                    height={barH}
                    rx={2}
                    fill="rgba(251,191,36,0.7)"
                    opacity={coupOpacity}
                    style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                    onMouseEnter={(e) => handleMouseEnter(e, row.window, "coup")}
                    onMouseLeave={handleMouseLeave}
                    aria-label={`Military Coup ${row.window} window z-score ${row.coup}`}
                  />
                  <text
                    x={labelW + coupW + 4}
                    y={y + barH + barGap + barH - 3}
                    fontSize="10"
                    fontFamily="var(--font-data, monospace)"
                    fill="rgba(251,191,36,0.9)"
                    style={{ pointerEvents: "none" }}
                  >
                    {row.coup}σ
                  </text>
                </>
              ) : (
                <text
                  x={labelW + 4}
                  y={y + barH + barGap + barH - 3}
                  fontSize="10"
                  fontFamily="var(--font-data, monospace)"
                  fill="var(--qgi-text-muted)"
                >
                  (not in top tier)
                </text>
              )}
            </g>
          );
        })}
        {/* Legend */}
        <g transform={`translate(${labelW}, ${svgH - 14})`}>
          <rect x={0} y={0} width={10} height={10} rx={2} fill="rgba(167,139,250,0.85)" />
          <text
            x={14}
            y={9}
            fontSize="10"
            fill="var(--qgi-text-dim)"
            fontFamily="sans-serif"
          >
            Elections &amp; Voting
          </text>
          <rect x={130} y={0} width={10} height={10} rx={2} fill="rgba(251,191,36,0.7)" />
          <text
            x={144}
            y={9}
            fontSize="10"
            fill="var(--qgi-text-dim)"
            fontFamily="sans-serif"
          >
            Military Coup
          </text>
        </g>
      </svg>

      {/* Tooltip */}
      {hovered &&
        (() => {
          const row = SALIENCE_BARS_DATA.find((r) => r.window === hovered.window);
          if (!row) return null;
          const isElections = hovered.type === "elections";
          const value = isElections ? row.elections : row.coup;
          const isHighlight = "highlight" in row && row.highlight;
          const windowNames: Record<string, string> = {
            S: "Short window (S-tier)",
            M: "Medium window (M-tier)",
            L: "Long window (L-tier)",
            XL: "Extra-Long window (XL-tier)",
          };
          return (
            <div
              style={{
                position: "absolute",
                left: tooltipPos.x,
                top: tooltipPos.y,
                transform: "translateY(-50%)",
                width: 180,
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
                {windowNames[row.window]}
              </div>
              <div style={{ color: "var(--qgi-text-muted)" }}>
                {isElections ? "Elections & Voting" : "Military Coup"}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color: isElections ? "#a78bfa" : "#fbbf24",
                  fontSize: 13,
                  margin: "4px 0",
                }}
              >
                {value}σ
              </div>
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                Above Ghana&apos;s own historical average.
              </div>
              {isHighlight && isElections && (
                <div style={{ color: "var(--qgi-accent)", fontSize: 10, marginTop: 2 }}>
                  (peak window)
                </div>
              )}
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Ghana salience z-scores: Elections &amp; Voting vs Military Coup across tier
        windows. L-tier peak (2.76σ) highlighted. Military Coup absent from XL top tier.
        Source: country-risks.json, April 2026 scoring run (QGI V1.9.1).
      </figcaption>
    </figure>
  );
}
