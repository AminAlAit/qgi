"use client";

import { useState } from "react";

const RADAR_DATA = [
  {
    id: "A",
    label: "Political Power & Regime",
    value: 1.66,
    cosineContrib: "66% of cosine match",
  },
  { id: "B", label: "Conflict & Insurgency", value: 0 },
  { id: "C", label: "Governance & Rule of Law", value: 0 },
  {
    id: "D",
    label: "Economic & Financial Stress",
    value: 1.01,
    cosineContrib: "24% of cosine match",
  },
  { id: "E", label: "Social & Civil Unrest", value: 0.24 },
  {
    id: "F",
    label: "Diplomatic & Geopolitical",
    value: 0.5,
    cosineContrib: "9% of cosine match",
  },
  { id: "G", label: "Humanitarian & Displacement", value: 0 },
  { id: "H", label: "Structural Vulnerability", value: 0 },
] as const;

export default function Chart4L1Profile() {
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);

  const maxVal = 2.0;
  const barMaxW = 340;
  const labelW = 180;
  const rowH = 24;
  const rowGap = 6;
  const svgW = labelW + barMaxW + 160;
  const svgH = RADAR_DATA.length * (rowH + rowGap) + 50;
  const highRefX = labelW + Math.round((0.6 / maxVal) * barMaxW);

  const getContextLine = (value: number) => {
    if (value === 0) return "Zero signal: no precedent-match activity in this dimension.";
    if (value > 1.0) return "Elevated: above the HIGH-tier median";
    return "Active signal";
  };

  return (
    <figure
      id="ghana-l1-profile-radar"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <style>{`
        @keyframes pulse-ref-line {
          0%, 100% { opacity: 0.12; }
          50% { opacity: 0.35; }
        }
        .ref-line-pulsing {
          animation: pulse-ref-line 0.8s ease-in-out infinite;
        }
      `}</style>

      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        width="100%"
        aria-label="Horizontal bar chart showing Ghana 8-dimension L1 risk profile from the April 2026 scoring run"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>Ghana 8-dimension L1 risk profile, April 2026 scoring run</title>

        {/* Reference line at global HIGH-tier median ~0.6 */}
        <line
          x1={highRefX}
          y1={0}
          x2={highRefX}
          y2={svgH - 20}
          stroke="rgba(255,255,255,0.12)"
          strokeWidth="1"
          strokeDasharray="4 3"
          className={hoveredRow !== null ? "ref-line-pulsing" : ""}
        />
        <text
          x={highRefX + 3}
          y={10}
          fontSize="8"
          fontFamily="sans-serif"
          fill="rgba(255,255,255,0.3)"
        >
          HIGH-tier median
        </text>

        {RADAR_DATA.map((dim, i) => {
          const y = i * (rowH + rowGap) + 12;
          const barW = Math.round((dim.value / maxVal) * barMaxW);
          const isActive = dim.value > 0;
          const isHovered = hoveredRow === dim.id;
          const bgOpacity = isHovered ? 0.07 : 0.03;
          const barOpacity = isHovered ? 1 : isActive ? 0.85 : 1;

          return (
            <g
              key={dim.id}
              style={{ cursor: "pointer" }}
              onMouseEnter={() => setHoveredRow(dim.id)}
              onMouseLeave={() => setHoveredRow(null)}
            >
              {/* Background track (full row, hover target) */}
              <rect
                x={labelW}
                y={y}
                width={barMaxW}
                height={rowH}
                rx={3}
                fill={`rgba(255,255,255,${bgOpacity})`}
                style={{ transition: "fill 0.15s" }}
              />
              {/* Dimension label */}
              <text
                x={labelW - 6}
                y={y + rowH / 2 + 4}
                textAnchor="end"
                fontSize="10"
                fontFamily="sans-serif"
                fill={isActive ? "var(--qgi-text)" : "var(--qgi-text-dim)"}
              >
                {dim.id}. {dim.label}
              </text>
              {/* Value bar */}
              {isActive && (
                <rect
                  x={labelW}
                  y={y}
                  width={barW}
                  height={rowH}
                  rx={3}
                  opacity={barOpacity}
                  fill={
                    dim.id === "A"
                      ? "#a78bfa"
                      : dim.id === "D"
                        ? "rgba(167,139,250,0.7)"
                        : dim.id === "F"
                          ? "rgba(167,139,250,0.5)"
                          : "rgba(167,139,250,0.35)"
                  }
                  style={{ transition: "opacity 0.15s" }}
                  aria-label={`Dimension ${dim.id} value ${dim.value}`}
                />
              )}
              {/* Value text */}
              <text
                x={isActive ? labelW + barW + 5 : labelW + 5}
                y={y + rowH / 2 + 4}
                fontSize="10"
                fontFamily="var(--font-data, monospace)"
                fill={isActive ? "rgba(167,139,250,0.9)" : "var(--qgi-text-muted)"}
              >
                {isActive ? dim.value.toFixed(2) : "0 (zero signal)"}
              </text>
            </g>
          );
        })}

        {/* Footer annotation */}
        <text
          x={labelW}
          y={svgH - 6}
          fontSize="9"
          fontFamily="sans-serif"
          fill="rgba(167,139,250,0.55)"
          fontStyle="italic"
        >
          Political dominance + Economic stress, zero conflict signal. Mauritania 2008
          template, not Burkina Faso 2022.
        </text>
      </svg>

      {/* Tooltip */}
      {hoveredRow &&
        (() => {
          const dim = RADAR_DATA.find((d) => d.id === hoveredRow);
          if (!dim) return null;
          const idx = RADAR_DATA.findIndex((d) => d.id === hoveredRow);
          const y = idx * (rowH + rowGap) + 12;
          const barW = Math.round((dim.value / maxVal) * barMaxW);
          const tooltipX = labelW + (dim.value > 0 ? barW : 0) + 50;
          const tooltipY = y + rowH / 2;

          return (
            <div
              style={{
                position: "absolute",
                left: `calc(${(tooltipX / svgW) * 100}%)`,
                top: `calc(${(tooltipY / svgH) * 100}%)`,
                transform: "translateY(-50%)",
                minWidth: 200,
                maxWidth: 260,
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
                {dim.id}. {dim.label}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color: "rgba(167,139,250,0.9)",
                  fontSize: 13,
                  margin: "4px 0",
                }}
              >
                {dim.value.toFixed(2)}
              </div>
              <div
                style={{ color: "var(--qgi-text-dim)", fontSize: 10, marginBottom: 4 }}
              >
                {getContextLine(dim.value)}
              </div>
              {"cosineContrib" in dim && dim.cosineContrib && (
                <div style={{ color: "var(--qgi-accent)", fontSize: 10 }}>
                  Accounts for {dim.cosineContrib} of the Ghana-Mauritania cosine match.
                </div>
              )}
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Ghana 8-dimension L1 risk profile, April 2026 scoring run. Dimensions A (Political
        Power &amp; Regime, 1.66), D (Economic &amp; Financial Stress, 1.01), and F
        (Diplomatic &amp; Geopolitical Relations, 0.50) are the three active dimensions
        that drive the Mauritania cosine match. Dashed reference line is the illustrative
        global HIGH-tier median. Source: country-risks.json, QGI V1.9.1.
      </figcaption>
    </figure>
  );
}
