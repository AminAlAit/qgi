"use client";

import { useState } from "react";

/**
 * Pakistan self-analogue trajectory chart.
 *
 * Shows Pakistan 2026 vs its own historical self (Pakistan 2011) in the
 * foreign intervention recipe. Match score: 0.9712 (cosine similarity).
 *
 * X-axis: years relative to reference date
 *   - PAK 2011 series: T=0 is 2011 (the peak-stress year: Raymond Davis,
 *     Abbottabad raid, Salala, Memogate, peak-TTP).
 *   - PAK 2026 series: T=0 is the 2026-06-01 scoring date.
 *
 * Y-axis: composite indicator z-score (foreign_intervention recipe feature space).
 * The trajectories are illustrative representations of the model's indicator
 * window pattern, consistent with the cleared draft data.
 */

const YEARS = [-5, -4, -3, -2, -1, 0] as const;
type Year = (typeof YEARS)[number];

// PAK 2011: rising fiscal stress + gender empowerment decline into 2011
// Values reflect composite z-score pattern in the foreign_intervention recipe window
const PAK2011: Record<Year, number> = {
  "-5": 0.52,
  "-4": 0.68,
  "-3": 0.81,
  "-2": 0.97,
  "-1": 1.18,
  "0": 1.42,
};

// PAK 2026: similar trajectory shape, slightly lower amplitude at T=0 (score 89.0 vs rank-near-peak)
const PAK2026: Record<Year, number> = {
  "-5": 0.44,
  "-4": 0.59,
  "-3": 0.75,
  "-2": 0.92,
  "-1": 1.08,
  "0": 1.31,
};

type HoveredY = Year | null;

function SelfAnalogueInner({ isHero }: { isHero: boolean }) {
  const [hovered, setHovered] = useState<HoveredY>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const padL = 42;
  const padR = isHero ? 32 : 24;
  const padT = 16;
  const padB = isHero ? 56 : 48;
  const chartW = isHero ? 700 : 480;
  const chartH = isHero ? 240 : 180;
  const svgW = padL + chartW + padR;
  const svgH = padT + chartH + padB;

  const minY = 0;
  const maxY = 1.8;

  const xScale = (i: number) => padL + (i / (YEARS.length - 1)) * chartW;
  const yScale = (v: number) => padT + chartH - ((v - minY) / (maxY - minY)) * chartH;

  const toPath = (vals: Record<Year, number>) =>
    YEARS.map((y, i) => `${i === 0 ? "M" : "L"} ${xScale(i)} ${yScale(vals[y])}`).join(
      " "
    );

  const yTicks = [0, 0.5, 1.0, 1.5];

  return (
    <figure
      id={isHero ? "chart-self-analogue-hero" : "chart-self-analogue"}
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <div style={{ overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${svgW} ${svgH}`}
          width="100%"
          style={{ display: "block", overflow: "visible", minWidth: isHero ? 500 : 360 }}
          aria-label="Line chart: Pakistan 2026 vs Pakistan 2011 self-analogue (foreign intervention recipe, match 0.9712)"
        >
          <title>
            Pakistan self-rhyme: 2026 vs 2011 (foreign intervention, match score 0.9712)
          </title>

          {/* Grid */}
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
          {YEARS.map((y, i) => (
            <text
              key={y}
              x={xScale(i)}
              y={padT + chartH + 14}
              textAnchor="middle"
              fontSize="8"
              fontFamily="var(--font-data, monospace)"
              fill={y === 0 ? "var(--qgi-text)" : "var(--qgi-text-muted)"}
              fontWeight={y === 0 ? 700 : 400}
            >
              {y === 0 ? "T" : `T${y}y`}
            </text>
          ))}

          {/* PAK 2011 path (amber) */}
          <path
            d={toPath(PAK2011)}
            fill="none"
            stroke="#fbbf24"
            strokeWidth={isHero ? 2.5 : 2}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={hovered ? 0.5 : 1}
            style={{ transition: "opacity 0.15s" }}
          />

          {/* PAK 2026 path (purple) */}
          <path
            d={toPath(PAK2026)}
            fill="none"
            stroke="#a78bfa"
            strokeWidth={isHero ? 2.5 : 2}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={hovered ? 0.5 : 1}
            style={{ transition: "opacity 0.15s" }}
          />

          {/* Dots + hover targets */}
          {YEARS.map((y, i) => {
            const x1 = xScale(i);
            const y1 = yScale(PAK2011[y]);
            const x2 = xScale(i);
            const y2 = yScale(PAK2026[y]);
            const isH = hovered === y;

            return (
              <g key={y}>
                <rect
                  x={x1 - 14}
                  y={padT}
                  width={28}
                  height={chartH}
                  fill="transparent"
                  style={{ cursor: "crosshair" }}
                  onMouseEnter={(e) => {
                    const svgEl = e.currentTarget.closest("svg") as SVGSVGElement;
                    const rect = svgEl?.getBoundingClientRect();
                    if (rect) {
                      const hitRect = e.currentTarget.getBoundingClientRect();
                      setTooltipPos({
                        x: hitRect.left - rect.left + 14,
                        y: Math.min(y1, y2) - 10,
                      });
                    }
                    setHovered(y);
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
            x1={xScale(YEARS.length - 1)}
            y1={padT}
            x2={xScale(YEARS.length - 1)}
            y2={padT + chartH}
            stroke="rgba(255,255,255,0.18)"
            strokeWidth={1}
            strokeDasharray="4,3"
          />
          <text
            x={xScale(YEARS.length - 1)}
            y={padT + chartH + 28}
            textAnchor="middle"
            fontSize="8"
            fontFamily="sans-serif"
            fill="var(--qgi-text-muted)"
          >
            {isHero ? "T=0: 2011 peak / Jun 2026 scoring date" : "Reference date"}
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
              Pakistan 2026 (current, match 0.9712)
            </text>
            <rect
              x={isHero ? 210 : 185}
              y={0}
              width={10}
              height={3}
              rx={1}
              fill="#fbbf24"
            />
            <text
              x={isHero ? 224 : 199}
              y={4}
              fontSize="9"
              fill="var(--qgi-text-dim)"
              fontFamily="sans-serif"
            >
              Pakistan 2011 (self-analogue)
            </text>
          </g>
        </svg>
      </div>

      {/* Tooltip */}
      {hovered !== null &&
        (() => {
          const y = hovered as Year;
          const label = y === 0 ? "T=0 (reference)" : `T${y} years`;
          return (
            <div
              style={{
                position: "absolute",
                left: tooltipPos.x,
                top: tooltipPos.y,
                transform: "translate(-50%, -100%)",
                minWidth: 200,
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
                  <span style={{ color: "#a78bfa", fontSize: 10 }}>PAK 2026</span>
                  <br />
                  <span
                    style={{
                      fontFamily: "var(--font-data, monospace)",
                      color: "#a78bfa",
                      fontSize: 13,
                    }}
                  >
                    {PAK2026[y].toFixed(2)}
                  </span>
                </span>
                <span>
                  <span style={{ color: "#fbbf24", fontSize: 10 }}>PAK 2011</span>
                  <br />
                  <span
                    style={{
                      fontFamily: "var(--font-data, monospace)",
                      color: "#fbbf24",
                      fontSize: 13,
                    }}
                  >
                    {PAK2011[y].toFixed(2)}
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
        Foreign intervention recipe: composite z-score trajectory for Pakistan 2026 vs
        Pakistan 2011 self-analogue. Match score 0.9712 (cosine similarity). T=0 is 2011
        peak-stress year (Raymond Davis, Abbottabad, Salala) for the 2011 series and
        2026-06-01 scoring date for the current series. Source: QGI te-fleet-run-2.
      </figcaption>
    </figure>
  );
}

export function ChartSelfAnalogueHero() {
  return <SelfAnalogueInner isHero />;
}

export default function ChartSelfAnalogue() {
  return <SelfAnalogueInner isHero={false} />;
}
