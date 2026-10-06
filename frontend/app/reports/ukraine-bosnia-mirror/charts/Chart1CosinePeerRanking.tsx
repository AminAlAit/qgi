"use client";

import { useState } from "react";

type Peer = {
  key: string;
  country: string;
  pct: number;
  description: string;
  highlight?: boolean;
};

const PEERS: ReadonlyArray<Peer> = [
  {
    key: "bosnia",
    country: "Bosnia and Herzegovina",
    pct: 81,
    description:
      "#1 structural twin, 81% cosine. Bidirectional: Bosnia's profile also lists Ukraine as #1. The Dayton-template structural endpoint.",
    highlight: true,
  },
  {
    key: "oman",
    country: "Oman",
    pct: 65,
    description: "Cluster of next-closest peers at 65%.",
  },
  {
    key: "sri_lanka",
    country: "Sri Lanka",
    pct: 65,
    description: "Cluster of next-closest peers at 65%.",
  },
  {
    key: "turkiye",
    country: "Türkiye",
    pct: 65,
    description: "Cluster of next-closest peers at 65%.",
  },
  {
    key: "uzbekistan",
    country: "Uzbekistan",
    pct: 65,
    description: "Cluster of next-closest peers at 65%.",
  },
];

function ChartBody({ size }: { size: "hero" | "inline" }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 100;
  const barH = size === "hero" ? 30 : 22;
  const groupGap = size === "hero" ? 18 : 14;
  const labelW = size === "hero" ? 220 : 180;
  const chartW = size === "hero" ? 470 : 360;
  const svgH = PEERS.length * (barH + groupGap) + 36;

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

  // Dotted reference line at 65% (the cluster threshold)
  const clusterX = labelW + Math.round((65 / maxVal) * chartW);

  return (
    <>
      <svg
        viewBox={`0 0 ${labelW + chartW + 80} ${svgH}`}
        width="100%"
        aria-label="Horizontal bar chart of Ukraine's top-5 cosine peers showing Bosnia at 81 percent categorically ahead of next-closest peer cluster at 65 percent"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          Ukraine cosine peer ranking, top-5. Bosnia 81%, then Oman / Sri Lanka /
          T&uuml;rkiye / Uzbekistan all at 65%.
        </title>

        {/* Cluster reference dotted line */}
        <line
          x1={clusterX}
          x2={clusterX}
          y1={4}
          y2={svgH - 26}
          stroke="var(--qgi-text-muted)"
          strokeDasharray="3 3"
          strokeWidth={1}
        />
        <text
          x={clusterX + 4}
          y={14}
          fontSize="9"
          fontStyle="italic"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
        >
          next-closest cluster
        </text>

        {PEERS.map((p, i) => {
          const y = i * (barH + groupGap) + 24;
          const w = Math.round((p.pct / maxVal) * chartW);
          const opacity = hovered && hovered !== p.key ? 0.3 : 1;
          const fill = p.highlight ? "#a78bfa" : "rgba(167,139,250,0.45)";

          return (
            <g key={p.key}>
              <text
                x={labelW - 8}
                y={y + barH / 2 + 4}
                textAnchor="end"
                fontSize={size === "hero" ? "13" : "12"}
                fontFamily="sans-serif"
                fill={p.highlight ? "var(--qgi-text)" : "var(--qgi-text-dim)"}
                fontWeight={p.highlight ? "600" : "400"}
                style={{ opacity }}
              >
                {p.country}
              </text>
              <rect
                x={labelW}
                y={y}
                width={w}
                height={barH}
                rx={3}
                fill={fill}
                opacity={opacity}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, p.key)}
                onMouseLeave={handleMouseLeave}
                aria-label={`${p.country}: ${p.pct}% cosine similarity to Ukraine`}
              />
              <text
                x={labelW + w + 6}
                y={y + barH / 2 + 4}
                fontSize={size === "hero" ? "14" : "12"}
                fontFamily="var(--font-data, monospace)"
                fill={p.highlight ? "#a78bfa" : "rgba(167,139,250,0.75)"}
                fontWeight="600"
                style={{ pointerEvents: "none", opacity }}
              >
                {p.pct}%
              </text>
              {p.highlight && (
                <text
                  x={labelW + w + 55}
                  y={y + barH / 2 + 4}
                  fontSize="10"
                  fontStyle="italic"
                  fill="var(--qgi-accent)"
                  fontFamily="sans-serif"
                  style={{ pointerEvents: "none", opacity }}
                >
                  +16pp gap ▲
                </text>
              )}
            </g>
          );
        })}

        <text
          x={labelW + chartW / 2}
          y={svgH - 8}
          textAnchor="middle"
          fontSize="10"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
        >
          Cosine similarity to Ukraine&apos;s L1 risk profile (8-dimension)
        </text>
      </svg>

      {hovered &&
        (() => {
          const p = PEERS.find((x) => x.key === hovered);
          if (!p) return null;
          return (
            <div
              style={{
                position: "absolute",
                left: tooltipPos.x,
                top: tooltipPos.y,
                transform: "translateY(-50%)",
                width: 240,
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
                {p.country}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color: p.highlight ? "#a78bfa" : "rgba(167,139,250,0.8)",
                  fontSize: 13,
                  margin: "4px 0",
                }}
              >
                {p.pct}% cosine
              </div>
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                {p.description}
              </div>
            </div>
          );
        })()}
    </>
  );
}

export default function Chart1CosinePeerRanking() {
  return (
    <figure
      id="ukraine-cosine-peer-ranking"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <ChartBody size="inline" />
      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Ukraine&apos;s top-5 cosine peers, April 2026 scoring run. Bosnia and Herzegovina
        is categorically ahead at 81%; the next-closest cluster (Oman, Sri Lanka,
        T&uuml;rkiye, Uzbekistan) sits at 65%. Source: QGI cosine similarity computation
        on the 8-dimension L1 risk profile.
      </figcaption>
    </figure>
  );
}

export function Chart1CosinePeerRankingHero() {
  return (
    <figure
      id="ukraine-cosine-peer-ranking-hero"
      className="my-2 relative"
      style={{ maxWidth: "100%" }}
    >
      <ChartBody size="hero" />
    </figure>
  );
}
