"use client";

import { useState } from "react";

type Row = {
  key: string;
  label: string;
  score: number;
  ciLow: number;
  ciHigh: number;
  rank: string;
  color: string;
  description: string;
};

const SEQUENCE: ReadonlyArray<Row> = [
  {
    key: "ukraine_bilateral",
    label: "Ukraine, Bilateral Treaty recipe (firing now)",
    score: 95,
    ciLow: 91,
    ciHigh: 98,
    rank: "#7 of 127",
    color: "#a78bfa",
    description:
      "The bilateral phase is active. Demographic and economic indicators (population change 0.53, employment ratio 0.42, mobile cellular 0.38) are the drivers. The war is part of the signal, not a block.",
  },
  {
    key: "ukraine_multilateral",
    label: "Ukraine, Multilateral Agreement recipe (uncertain)",
    score: 51,
    ciLow: 33,
    ciHigh: 70,
    rank: "#29 of 58",
    color: "rgba(167,139,250,0.45)",
    description:
      "Currently flat with a 37-point confidence interval. The model is genuinely uncertain. The 70/100 trigger threshold and the 60/100 exit floor define the trade window.",
  },
  {
    key: "bosnia_multilateral",
    label: "Bosnia, Multilateral Agreement (template, fully resolved)",
    score: 99,
    ciLow: 96,
    ciHigh: 100,
    rank: "#1 of 58",
    color: "rgba(251,191,36,0.7)",
    description:
      "The structural endpoint. Bosnia's post-Dayton institutionalisation locked in over the subsequent decade. The model has finished its read here.",
  },
];

const TRIGGER = 70;
const EXIT = 60;

export default function Chart2BilateralMultilateralSequence() {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 100;
  const barH = 26;
  const groupGap = 32;
  const labelW = 220;
  const chartW = 360;
  const svgH = SEQUENCE.length * (barH + groupGap) + 50;

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

  const triggerX = labelW + Math.round((TRIGGER / maxVal) * chartW);
  const exitX = labelW + Math.round((EXIT / maxVal) * chartW);

  return (
    <figure
      id="ukraine-bilateral-multilateral-sequence"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${labelW + chartW + 90} ${svgH}`}
        width="100%"
        aria-label="Bar chart showing Ukraine Bilateral Treaty 95, Ukraine Multilateral Agreement 51, Bosnia Multilateral Agreement 99 with trigger and exit thresholds"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          The Bilateral → Multilateral sequence: Ukraine firing on Bilateral, uncertain on
          Multilateral, with Bosnia as the resolved endpoint.
        </title>

        {/* Trigger (70) and exit (60) reference lines */}
        <line
          x1={triggerX}
          x2={triggerX}
          y1={10}
          y2={svgH - 30}
          stroke="var(--qgi-accent)"
          strokeDasharray="4 3"
          strokeWidth={1}
        />
        <text
          x={triggerX + 4}
          y={16}
          fontSize="9"
          fontFamily="var(--font-data, monospace)"
          fill="var(--qgi-accent)"
          fontWeight="600"
        >
          70/100 trigger
        </text>
        <line
          x1={exitX}
          x2={exitX}
          y1={10}
          y2={svgH - 30}
          stroke="rgba(251,191,36,0.85)"
          strokeDasharray="2 3"
          strokeWidth={1}
        />
        <text
          x={exitX - 4}
          y={16}
          textAnchor="end"
          fontSize="9"
          fontFamily="var(--font-data, monospace)"
          fill="rgba(251,191,36,0.9)"
          fontWeight="600"
        >
          60/100 exit
        </text>

        {SEQUENCE.map((row, i) => {
          const y = i * (barH + groupGap) + 36;
          const w = Math.round((row.score / maxVal) * chartW);
          const ciL = Math.round((row.ciLow / maxVal) * chartW);
          const ciH = Math.round((row.ciHigh / maxVal) * chartW);
          const opacity = hovered && hovered !== row.key ? 0.3 : 1;

          return (
            <g key={row.key}>
              <text
                x={labelW - 8}
                y={y + barH / 2 - 2}
                textAnchor="end"
                fontSize="11"
                fontFamily="sans-serif"
                fill="var(--qgi-text)"
                style={{ opacity }}
              >
                {row.key === "ukraine_bilateral"
                  ? "Ukraine · Bilateral Treaty"
                  : row.key === "ukraine_multilateral"
                    ? "Ukraine · Multilateral Agt."
                    : "Bosnia · Multilateral Agt."}
              </text>
              <text
                x={labelW - 8}
                y={y + barH / 2 + 13}
                textAnchor="end"
                fontSize="9"
                fontFamily="var(--font-data, monospace)"
                fill="var(--qgi-text-muted)"
                style={{ opacity }}
              >
                {row.rank}
              </text>
              {/* CI bracket */}
              <line
                x1={labelW + ciL}
                x2={labelW + ciH}
                y1={y + barH / 2}
                y2={y + barH / 2}
                stroke="var(--qgi-text-muted)"
                strokeDasharray="2 2"
                strokeWidth={1}
                opacity={opacity * 0.6}
              />
              <line
                x1={labelW + ciL}
                x2={labelW + ciL}
                y1={y + barH / 2 - 5}
                y2={y + barH / 2 + 5}
                stroke="var(--qgi-text-muted)"
                strokeWidth={1}
                opacity={opacity * 0.6}
              />
              <line
                x1={labelW + ciH}
                x2={labelW + ciH}
                y1={y + barH / 2 - 5}
                y2={y + barH / 2 + 5}
                stroke="var(--qgi-text-muted)"
                strokeWidth={1}
                opacity={opacity * 0.6}
              />
              <rect
                x={labelW}
                y={y}
                width={w}
                height={barH}
                rx={3}
                fill={row.color}
                opacity={opacity}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, row.key)}
                onMouseLeave={handleMouseLeave}
                aria-label={`${row.label}: ${row.score}/100`}
              />
              <text
                x={labelW + w + 6}
                y={y + barH / 2 + 4}
                fontSize="13"
                fontFamily="var(--font-data, monospace)"
                fill={
                  row.key === "ukraine_bilateral"
                    ? "#a78bfa"
                    : row.key === "bosnia_multilateral"
                      ? "rgba(251,191,36,0.95)"
                      : "rgba(167,139,250,0.85)"
                }
                fontWeight="600"
                style={{ pointerEvents: "none", opacity }}
              >
                {row.score}/100
              </text>
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
          Precedent Match score (0&ndash;100, 95% CI bracket)
        </text>
      </svg>

      {hovered &&
        (() => {
          const row = SEQUENCE.find((r) => r.key === hovered);
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
                padding: "8px 10px",
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
                  color:
                    row.color === "#a78bfa"
                      ? "#a78bfa"
                      : row.color === "rgba(251,191,36,0.7)"
                        ? "#fbbf24"
                        : "rgba(167,139,250,0.85)",
                  fontSize: 14,
                  margin: "4px 0",
                }}
              >
                {row.score}/100 · CI {row.ciLow}&ndash;{row.ciHigh} · {row.rank}
              </div>
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                {row.description}
              </div>
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        The structural sequence: Ukraine is firing on Bilateral Treaty at 95/100 (#7 of
        127). Multilateral Agreement is currently flat at 51/100 with a wide 37-point
        confidence interval. Bosnia (#1 at 99/100) is the resolved endpoint. The 70/100
        trigger and 60/100 exit lines define the trade window. Source: QGI Bilateral
        Treaty + Multilateral Agreement signals, April 2026 scoring run.
      </figcaption>
    </figure>
  );
}
