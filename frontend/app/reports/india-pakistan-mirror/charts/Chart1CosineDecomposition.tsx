"use client";

import { useState } from "react";

type Dim = {
  key: string;
  short: string;
  full: string;
  pct: number;
  description: string;
};

const DIMENSIONS: ReadonlyArray<Dim> = [
  {
    key: "conflict",
    short: "Conflict & Political Violence",
    full: "Conflict & Political Violence",
    pct: 45,
    description:
      "The largest single contributor: battle-related deaths, insurgency intensity, political-violence trajectories. India's J&K + Manipur + Naxalite footprint and Pakistan's TTP + Balochistan footprint map to the same indicator signatures.",
  },
  {
    key: "regime",
    short: "Political Power & Regime",
    full: "Political Power & Regime",
    pct: 17,
    description:
      "Indicators of regime concentration, executive durability, and political polarisation. India's recent V-Dem and WGI deteriorations have brought it into closer alignment with Pakistan's regime trajectory than its prior baseline.",
  },
  {
    key: "governance",
    short: "State Authority & Governance",
    full: "State Authority & Governance",
    pct: 11,
    description:
      "Government effectiveness, rule-of-law, and state-capacity indicators. The convergence here is driven by deterioration in both countries' WGI Governance subcomponents over the past decade.",
  },
  {
    key: "economic",
    short: "Economic & Financial Stress",
    full: "Economic & Financial Stress",
    pct: 11,
    description:
      "Inflation, sovereign-credit-stress proxies, growth volatility, energy-import dependency. Pakistan's 2022–2024 crisis is more acute, but India's structural trend on these indicators has not been benign.",
  },
  {
    key: "social",
    short: "Social Mobilisation & Civil Society",
    full: "Social Mobilisation & Civil Society",
    pct: 10,
    description:
      "Civic-protest intensity, communal-violence incidence, social-movement indicators. India's state-level communal episodes and Pakistan's Tehrik-e-Insaf cycle leave related signatures.",
  },
  {
    key: "diplomatic",
    short: "Diplomatic & Geopolitical",
    full: "Diplomatic & Geopolitical Relations",
    pct: 6,
    description:
      "Bilateral and multilateral engagement trajectories. The smallest dimensional contributor; not the locus of the match.",
  },
];

function ChartBody({ size }: { size: "hero" | "inline" }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 50;
  const barH = size === "hero" ? 26 : 20;
  const groupGap = size === "hero" ? 14 : 10;
  const labelW = size === "hero" ? 240 : 200;
  const chartW = size === "hero" ? 430 : 320;
  const svgH = DIMENSIONS.length * (barH + groupGap) + 24;

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
    <>
      <svg
        viewBox={`0 0 ${labelW + chartW + 80} ${svgH}`}
        width="100%"
        aria-label="Horizontal bar chart of India-Pakistan cosine similarity decomposition across 6 L1 dimensions"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>India-Pakistan 99% cosine similarity, decomposed by L1 dimension</title>
        {DIMENSIONS.map((dim, i) => {
          const y = i * (barH + groupGap) + 12;
          const w = Math.round((dim.pct / maxVal) * chartW);
          const opacity = hovered && hovered !== dim.key ? 0.3 : 1;
          const isPrimary = dim.pct >= 17;

          return (
            <g key={dim.key}>
              <text
                x={labelW - 8}
                y={y + barH / 2 + 4}
                textAnchor="end"
                fontSize={size === "hero" ? "12" : "11"}
                fontFamily="sans-serif"
                fill="var(--qgi-text)"
                fontWeight={isPrimary ? "600" : "400"}
                style={{ opacity }}
              >
                {dim.short}
              </text>
              <rect
                x={labelW}
                y={y}
                width={w}
                height={barH}
                rx={3}
                fill={isPrimary ? "#a78bfa" : "rgba(167,139,250,0.55)"}
                opacity={opacity}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, dim.key)}
                onMouseLeave={handleMouseLeave}
                aria-label={`${dim.full}: ${dim.pct}% of cosine match`}
              />
              <text
                x={labelW + w + 6}
                y={y + barH / 2 + 4}
                fontSize={size === "hero" ? "13" : "11"}
                fontFamily="var(--font-data, monospace)"
                fill="#a78bfa"
                fontWeight="600"
                style={{ pointerEvents: "none", opacity }}
              >
                {dim.pct}%
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
          Share of 99% India↔Pakistan cosine similarity, by L1 dimension
        </text>
      </svg>

      {hovered &&
        (() => {
          const dim = DIMENSIONS.find((d) => d.key === hovered);
          if (!dim) return null;
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
                padding: "8px 10px",
                pointerEvents: "none",
                zIndex: 10,
                fontSize: 11,
                lineHeight: 1.5,
              }}
            >
              <div style={{ color: "var(--qgi-text)", fontWeight: 600, marginBottom: 4 }}>
                {dim.full}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color: "#a78bfa",
                  fontSize: 14,
                  margin: "4px 0",
                }}
              >
                {dim.pct}% of the match
              </div>
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                {dim.description}
              </div>
            </div>
          );
        })()}
    </>
  );
}

export default function Chart1CosineDecomposition() {
  return (
    <figure
      id="india-pakistan-cosine-decomposition"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <ChartBody size="inline" />
      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        India and Pakistan 99% cosine similarity decomposed across 6 of 8 L1 dimensions.
        The match is structural-violence dominant (Conflict &amp; Political Violence 45%,
        Political Power &amp; Regime 17%), not a one-dimensional artefact. Source: QGI
        cosine decomposition, April 2026 scoring run.
      </figcaption>
    </figure>
  );
}

export function Chart1CosineDecompositionHero() {
  return (
    <figure
      id="india-pakistan-cosine-decomposition-hero"
      className="my-2 relative"
      style={{ maxWidth: "100%" }}
    >
      <ChartBody size="hero" />
    </figure>
  );
}
