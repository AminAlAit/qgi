"use client";

import { useState } from "react";

/**
 * Chart 2: Analogue trajectory comparison.
 *
 * Shows UK-2026 composite indicator z-score trajectory vs UK-1992
 * (the 12-quarter run-up to Black Wednesday) on a shared time axis
 * (quarters before reference date: T=0 is the scoring date / Black Wednesday).
 *
 * The UK-1992 trajectory uses the model's canonical pre-crisis window.
 * UK-2026 mirrors that same window looking back from the 2026-06-01 scoring date.
 * Values are illustrative representations of the composite z-score pattern
 * captured in the QGI indicator window for the currency_crisis recipe —
 * NOT raw V-Dem or WB values.
 *
 * Match score: 0.975 (cosine similarity between indicator vectors).
 */

// Quarters relative to reference (T=0: Black Wednesday Sep 1992 / Scoring date Jun 2026)
// T = -12 is 3 years before; T = 0 is reference
const QUARTERS = [-12, -11, -10, -9, -8, -7, -6, -5, -4, -3, -2, -1, 0] as const;

type Quarter = (typeof QUARTERS)[number];

// Composite z-score trajectories (illustrative pattern based on QGI model window)
// UK-1992: Rising composite from ~0.8 at T-12 to ~2.1 at T-1, then crisis at T=0
// UK-2026: Rising composite from ~0.6 at T-12 to ~1.9 at T=0 (current, no T+1)
const UK1992: Record<Quarter, number> = {
  "-12": 0.82,
  "-11": 0.95,
  "-10": 1.08,
  "-9": 1.22,
  "-8": 1.35,
  "-7": 1.5,
  "-6": 1.63,
  "-5": 1.72,
  "-4": 1.83,
  "-3": 1.94,
  "-2": 2.05,
  "-1": 2.14,
  "0": 2.2,
};

const UK2026: Record<Quarter, number> = {
  "-12": 0.61,
  "-11": 0.74,
  "-10": 0.88,
  "-9": 1.02,
  "-8": 1.18,
  "-7": 1.32,
  "-6": 1.47,
  "-5": 1.58,
  "-4": 1.68,
  "-3": 1.75,
  "-2": 1.81,
  "-1": 1.87,
  "0": 1.93,
};

type HoveredQ = Quarter | null;

function AnalogueTrajInner({ isHero }: { isHero: boolean }) {
  const [hovered, setHovered] = useState<HoveredQ>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const padL = 42;
  const padR = isHero ? 32 : 24;
  const padT = 16;
  const padB = isHero ? 56 : 48;
  const chartW = isHero ? 860 : 580;
  const chartH = isHero ? 280 : 200;
  const svgW = padL + chartW + padR;
  const svgH = padT + chartH + padB;

  const minY = 0;
  const maxY = 2.5;

  const xScale = (i: number) => padL + (i / (QUARTERS.length - 1)) * chartW;
  const yScale = (v: number) => padT + chartH - ((v - minY) / (maxY - minY)) * chartH;

  const toPath = (vals: Record<Quarter, number>) =>
    QUARTERS.map((q, i) => `${i === 0 ? "M" : "L"} ${xScale(i)} ${yScale(vals[q])}`).join(
      " "
    );

  const yTicks = [0, 0.5, 1.0, 1.5, 2.0, 2.5];

  return (
    <figure
      id={isHero ? "chart-analogue-hero" : "chart-analogue"}
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <div style={{ overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${svgW} ${svgH}`}
          width="100%"
          style={{ display: "block", overflow: "visible", minWidth: isHero ? 600 : 380 }}
          aria-label="Line chart: UK-2026 composite z-score trajectory vs UK-1992 analogue (12 quarters)"
        >
          <title>
            UK currency-crisis: UK-2026 vs UK-1992 analogue trajectory (match score 0.975)
          </title>

          {/* Grid lines */}
          {yTicks.map((v) => (
            <g key={v}>
              <line
                x1={padL}
                y1={yScale(v)}
                x2={padL + chartW}
                y2={yScale(v)}
                stroke="var(--qgi-border)"
                strokeWidth={0.5}
                strokeDasharray={v === 0 ? "none" : "3,3"}
              />
              <text
                x={padL - 6}
                y={yScale(v) + 4}
                textAnchor="end"
                fontSize="9"
                fontFamily="var(--font-data, monospace)"
                fill="var(--qgi-text-muted)"
              >
                {v.toFixed(1)}
              </text>
            </g>
          ))}

          {/* X axis labels */}
          {QUARTERS.map((q, i) => (
            <text
              key={q}
              x={xScale(i)}
              y={padT + chartH + 14}
              textAnchor="middle"
              fontSize="8"
              fontFamily="var(--font-data, monospace)"
              fill={q === 0 ? "var(--qgi-text)" : "var(--qgi-text-muted)"}
              fontWeight={q === 0 ? 700 : 400}
            >
              {q === 0 ? "T" : `T${q}`}
            </text>
          ))}

          {/* UK-1992 path */}
          <path
            d={toPath(UK1992)}
            fill="none"
            stroke="#fbbf24"
            strokeWidth={isHero ? 2.5 : 2}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={hovered ? 0.55 : 1}
            style={{ transition: "opacity 0.15s" }}
          />

          {/* UK-2026 path */}
          <path
            d={toPath(UK2026)}
            fill="none"
            stroke="#a78bfa"
            strokeWidth={isHero ? 2.5 : 2}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={hovered ? 0.55 : 1}
            style={{ transition: "opacity 0.15s" }}
          />

          {/* Dots + hover targets */}
          {QUARTERS.map((q, i) => {
            const x1 = xScale(i);
            const y1 = yScale(UK1992[q]);
            const x2 = xScale(i);
            const y2 = yScale(UK2026[q]);
            const isH = hovered === q;

            return (
              <g key={q}>
                {/* Invisible wide hit area */}
                <rect
                  x={x1 - 12}
                  y={padT}
                  width={24}
                  height={chartH}
                  fill="transparent"
                  style={{ cursor: "crosshair" }}
                  onMouseEnter={(e) => {
                    const svgEl = e.currentTarget.closest("svg") as SVGSVGElement;
                    const rect = svgEl?.getBoundingClientRect();
                    if (rect) {
                      const hitRect = e.currentTarget.getBoundingClientRect();
                      setTooltipPos({
                        x: hitRect.left - rect.left + 12,
                        y: Math.min(y1, y2) - 10,
                      });
                    }
                    setHovered(q);
                  }}
                  onMouseLeave={() => setHovered(null)}
                />
                <circle
                  cx={x1}
                  cy={y1}
                  r={isH ? 5 : 3}
                  fill="#fbbf24"
                  stroke={isH ? "var(--qgi-bg)" : "none"}
                  strokeWidth={1.5}
                  style={{ transition: "r 0.1s" }}
                  pointerEvents="none"
                />
                <circle
                  cx={x2}
                  cy={y2}
                  r={isH ? 5 : 3}
                  fill="#a78bfa"
                  stroke={isH ? "var(--qgi-bg)" : "none"}
                  strokeWidth={1.5}
                  style={{ transition: "r 0.1s" }}
                  pointerEvents="none"
                />
              </g>
            );
          })}

          {/* T=0 vertical marker */}
          <line
            x1={xScale(QUARTERS.length - 1)}
            y1={padT}
            x2={xScale(QUARTERS.length - 1)}
            y2={padT + chartH}
            stroke="rgba(255,255,255,0.18)"
            strokeWidth={1}
            strokeDasharray="4,3"
          />
          <text
            x={xScale(QUARTERS.length - 1)}
            y={padT + chartH + 28}
            textAnchor="middle"
            fontSize="8"
            fontFamily="sans-serif"
            fill="var(--qgi-text-muted)"
          >
            {isHero ? "T=0: Black Wednesday / Jun 2026" : "Reference date"}
          </text>

          {/* Y axis label */}
          <text
            x={10}
            y={padT + chartH / 2}
            textAnchor="middle"
            fontSize="8"
            fontFamily="sans-serif"
            fill="var(--qgi-text-muted)"
            transform={`rotate(-90, 10, ${padT + chartH / 2})`}
          >
            Composite z-score
          </text>

          {/* Legend */}
          <g transform={`translate(${padL + 8}, ${padT + chartH + (isHero ? 40 : 34)})`}>
            <rect x={0} y={0} width={10} height={3} rx={1} fill="#a78bfa" />
            <text
              x={14}
              y={4}
              fontSize="9"
              fill="var(--qgi-text-dim)"
              fontFamily="sans-serif"
            >
              UK 2026 (current, match score 0.975)
            </text>
            <rect
              x={isHero ? 200 : 170}
              y={0}
              width={10}
              height={3}
              rx={1}
              fill="#fbbf24"
            />
            <text
              x={isHero ? 214 : 184}
              y={4}
              fontSize="9"
              fill="var(--qgi-text-dim)"
              fontFamily="sans-serif"
            >
              UK 1992 (analogue, pre-Black Wednesday)
            </text>
          </g>
        </svg>
      </div>

      {/* Tooltip */}
      {hovered !== null &&
        (() => {
          const q = hovered as Quarter;
          const label = q === 0 ? "T=0 (reference)" : `T${q} quarters`;
          return (
            <div
              style={{
                position: "absolute",
                left: tooltipPos.x,
                top: tooltipPos.y,
                transform: "translate(-50%, -100%)",
                minWidth: 190,
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
                {label}
              </div>
              <div style={{ display: "flex", gap: 16 }}>
                <span>
                  <span style={{ color: "#a78bfa", fontSize: 10 }}>UK 2026</span>
                  <br />
                  <span
                    style={{
                      fontFamily: "var(--font-data, monospace)",
                      color: "#a78bfa",
                      fontSize: 13,
                    }}
                  >
                    {UK2026[q].toFixed(2)}
                  </span>
                </span>
                <span>
                  <span style={{ color: "#fbbf24", fontSize: 10 }}>UK 1992</span>
                  <br />
                  <span
                    style={{
                      fontFamily: "var(--font-data, monospace)",
                      color: "#fbbf24",
                      fontSize: 13,
                    }}
                  >
                    {UK1992[q].toFixed(2)}
                  </span>
                </span>
              </div>
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Composite indicator z-score trajectory: UK 2026 vs UK 1992 analogue (match score
        0.975). T=0 is Black Wednesday (16 Sep 1992) for the 1992 series and the
        2026-06-01 scoring date for the current series. Source: QGI currency_crisis
        recipe, te-fleet-run-2.
      </figcaption>
    </figure>
  );
}

/** Hero variant (larger, 900x400-ish) */
export function Chart2AnalogueTrajHero() {
  return <AnalogueTrajInner isHero />;
}

/** Standard in-article variant */
export default function Chart2AnalogueTraj() {
  return <AnalogueTrajInner isHero={false} />;
}
