"use client";

import { useState } from "react";

type Row = {
  key: string;
  label: string;
  shortLabel: string;
  weight: number;
  mechanism: string;
};

const INDICATORS: ReadonlyArray<Row> = [
  {
    key: "battle_deaths",
    label: "Battle-related deaths, year-on-year change",
    shortLabel: "Battle-related deaths Δ",
    weight: 0.55,
    mechanism:
      "Top driver. In India: J&K low-intensity conflict + Manipur (since 2023) + Naxalite-related violence. In Pakistan: TTP insurgency, Balochistan operations, post-Afghanistan deterioration. The model does not distinguish counter-insurgency from failing state, only the underlying data.",
  },
  {
    key: "political_stability",
    label: "Political Stability and Absence of Violence/Terrorism, change",
    shortLabel: "Political Stability Δ",
    weight: 0.4,
    mechanism:
      "V-Dem + WGI deterioration in both countries. India's path is driven by state-level communal-violence episodes, the Manipur crisis, and rising polarisation indices. Pakistan's is more acute, but the directions are converging.",
  },
  {
    key: "gov_consumption",
    label: "Government final consumption expenditure, change",
    shortLabel: "Gov consumption Δ",
    weight: 0.2,
    mechanism:
      "Fiscal-pressure proxy. Both countries show a state-spending trajectory consistent with security-cost absorption and short-horizon counter-cyclical responses.",
  },
  {
    key: "energy_imports",
    label: "Energy imports as % of energy use, change",
    shortLabel: "Energy import dependency Δ",
    weight: 0.18,
    mechanism:
      "Cross-cutting South Asian structural driver. India ≈ 44% energy imported; trajectory tightened with coal-import-dependency volatility. Pakistan's 2022–2024 crisis was acute; the model is reading the structural trend, not the episodic crisis.",
  },
  {
    key: "arms_imports",
    label: "Arms imports trajectory",
    shortLabel: "Arms imports Δ",
    weight: 0.12,
    mechanism:
      "Lowest weight of the five top drivers. Reflects the structural-armament backdrop across both countries; modest contribution to the overall recipe signal.",
  },
];

export default function Chart2RecipeIndicators() {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 0.6;
  const barH = 22;
  const groupGap = 18;
  const labelW = 200;
  const chartW = 320;
  const svgH = INDICATORS.length * (barH + groupGap) + 24;

  const handleMouseEnter = (e: React.MouseEvent<SVGRectElement>, key: string) => {
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
    setHovered(key);
  };
  const handleMouseLeave = () => setHovered(null);

  return (
    <figure
      id="india-pakistan-recipe-indicators"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${labelW + chartW + 80} ${svgH}`}
        width="100%"
        aria-label="Horizontal bar chart of shared Civil War and Insurgency recipe indicator weights for India and Pakistan"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          Civil War &amp; Insurgency recipe indicator fingerprint: shared between India
          and Pakistan, identical rank order and importance weights.
        </title>
        {INDICATORS.map((row, i) => {
          const y = i * (barH + groupGap) + 12;
          const w = Math.round((row.weight / maxVal) * chartW);
          const opacity = hovered && hovered !== row.key ? 0.3 : 1;
          const isTop = row.weight >= 0.4;

          return (
            <g key={row.key}>
              <text
                x={labelW - 8}
                y={y + barH / 2 + 4}
                textAnchor="end"
                fontSize="11"
                fontFamily="sans-serif"
                fill="var(--qgi-text)"
                fontWeight={isTop ? "600" : "400"}
                style={{ opacity }}
              >
                {row.shortLabel}
              </text>
              <rect
                x={labelW}
                y={y}
                width={w}
                height={barH}
                rx={3}
                fill={isTop ? "#a78bfa" : "rgba(167,139,250,0.55)"}
                opacity={opacity}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, row.key)}
                onMouseLeave={handleMouseLeave}
                aria-label={`${row.shortLabel}: importance ${row.weight}`}
              />
              <text
                x={labelW + w + 6}
                y={y + barH / 2 + 4}
                fontSize="12"
                fontFamily="var(--font-data, monospace)"
                fill="#a78bfa"
                fontWeight="600"
                style={{ pointerEvents: "none", opacity }}
              >
                {row.weight.toFixed(2)}
              </text>
            </g>
          );
        })}
        <text
          x={labelW + chartW / 2}
          y={svgH - 6}
          textAnchor="middle"
          fontSize="10"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
        >
          Importance weight, Civil War &amp; Insurgency recipe (same for India and
          Pakistan)
        </text>
      </svg>

      {hovered &&
        (() => {
          const row = INDICATORS.find((r) => r.key === hovered);
          if (!row) return null;
          return (
            <div
              style={{
                position: "absolute",
                left: tooltipPos.x,
                top: tooltipPos.y,
                transform: "translateY(-50%)",
                width: 280,
                backgroundColor: "var(--qgi-surface)",
                border: "1px solid var(--qgi-border)",
                borderRadius: 4,
                padding: "10px 12px",
                pointerEvents: "none",
                zIndex: 10,
                fontSize: 11,
                lineHeight: 1.5,
              }}
            >
              <div style={{ color: "var(--qgi-text)", fontWeight: 600, marginBottom: 4 }}>
                {row.label}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color: "#a78bfa",
                  fontSize: 13,
                  margin: "4px 0",
                }}
              >
                importance {row.weight.toFixed(2)}
              </div>
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                {row.mechanism}
              </div>
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Civil War &amp; Insurgency recipe indicator fingerprint: identical rank order and
        importance weights for India and Pakistan. Same five drivers, same weights, two
        countries. Source: QGI Civil War &amp; Insurgency recipe dossier (LOCO AUC 0.769,
        ECE 0.006), April 2026 scoring run.
      </figcaption>
    </figure>
  );
}
