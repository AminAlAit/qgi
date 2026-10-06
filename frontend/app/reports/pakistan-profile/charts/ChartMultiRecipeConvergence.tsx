"use client";

import { useState } from "react";

/**
 * Pakistan multi-recipe convergence chart.
 *
 * Shows Pakistan's five top-20 endogenous recipe scores (score_pp) from
 * te-fleet-run-2 (scored 2026-06-01), with LOCO AUC and global rank annotated.
 * The horizontal bar chart doubles as the hero visual and an in-article reference.
 *
 * All values are from the cleared draft-article (committee-approved data):
 *   - Labor Action:             score_pp 96.0, rank 8/174,  LOCO AUC 0.8145
 *   - Religious/Social Mvmt:   score_pp 93.6, rank 12/171, LOCO AUC 0.8186
 *   - Political Repression:    score_pp 91.4, rank 16/174, LOCO AUC 0.6847
 *   - Foreign Intervention:    score_pp 89.0, rank 20/172, LOCO AUC 0.7227
 *   - Democratic Transition:   score_pp 79.9, rank 36/174, LOCO AUC 0.6967
 */

const RECIPES = [
  {
    label: "Labor Action",
    shortLabel: "Labor Action",
    scorePp: 96.0,
    rank: 8,
    total: 174,
    locoAuc: 0.8145,
    tier: "Directional" as const,
    hardFail: false,
  },
  {
    label: "Religious & Social Movement",
    shortLabel: "Religious/Social",
    scorePp: 93.6,
    rank: 12,
    total: 171,
    locoAuc: 0.8186,
    tier: "Directional" as const,
    hardFail: false,
  },
  {
    label: "Political Repression",
    shortLabel: "Political Repression",
    scorePp: 91.4,
    rank: 16,
    total: 174,
    locoAuc: 0.6847,
    tier: "Experimental" as const,
    hardFail: true,
  },
  {
    label: "Foreign Intervention",
    shortLabel: "Foreign Intervention",
    scorePp: 89.0,
    rank: 20,
    total: 172,
    locoAuc: 0.7227,
    tier: "Directional" as const,
    hardFail: false,
  },
  {
    label: "Democratic Transition",
    shortLabel: "Democratic Transition",
    scorePp: 79.9,
    rank: 36,
    total: 174,
    locoAuc: 0.6967,
    tier: "Experimental" as const,
    hardFail: true,
  },
] as const;

type HoveredIdx = number | null;

function MultiRecipeInner({ isHero }: { isHero: boolean }) {
  const [hovered, setHovered] = useState<HoveredIdx>(null);
  const [tooltipY, setTooltipY] = useState(0);

  const rowH = isHero ? 44 : 38;
  const barMaxW = isHero ? 380 : 300;
  const leftPad = isHero ? 150 : 140;
  const rightPad = 80;
  const svgW = leftPad + barMaxW + rightPad;
  const svgH = RECIPES.length * rowH + (isHero ? 36 : 28);
  const maxScore = 100;

  return (
    <figure
      id={isHero ? "chart-convergence-hero" : "chart-convergence"}
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <div style={{ overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${svgW} ${svgH}`}
          width="100%"
          style={{ display: "block", overflow: "visible", minWidth: isHero ? 560 : 420 }}
          aria-label="Horizontal bar chart: Pakistan multi-recipe convergence scores from te-fleet-run-2"
        >
          <title>
            Pakistan 2026: Five top-20 structural recipe scores (QGI te-fleet-run-2)
          </title>

          {/* 90th percentile reference line */}
          {(() => {
            const x90 = leftPad + (90 / maxScore) * barMaxW;
            return (
              <g>
                <line
                  x1={x90}
                  y1={4}
                  x2={x90}
                  y2={svgH - (isHero ? 28 : 20)}
                  stroke="rgba(167,139,250,0.25)"
                  strokeWidth={1}
                  strokeDasharray="4,3"
                />
                <text
                  x={x90}
                  y={0}
                  textAnchor="middle"
                  fontSize="8"
                  fontFamily="sans-serif"
                  fill="rgba(167,139,250,0.55)"
                >
                  90th pct
                </text>
              </g>
            );
          })()}

          {RECIPES.map((r, i) => {
            const y = 8 + i * rowH;
            const barW = Math.round((r.scorePp / maxScore) * barMaxW);
            const isTop2 = i < 2;
            const isHov = hovered === i;
            const dimmed = hovered !== null && !isHov;

            // Color: Directional = purple, Experimental = amber
            const fill =
              r.tier === "Directional"
                ? i === 0
                  ? "#a78bfa"
                  : "#8b5cf6"
                : "rgba(251,191,36,0.65)";

            return (
              <g key={r.label}>
                {/* Row label */}
                <text
                  x={leftPad - 8}
                  y={y + rowH / 2 + 4}
                  textAnchor="end"
                  fontSize={isHero ? 10 : 9}
                  fontFamily="sans-serif"
                  fill={dimmed ? "rgba(200,200,200,0.25)" : "var(--qgi-text-dim)"}
                  style={{ transition: "fill 0.15s" }}
                >
                  {r.shortLabel}
                </text>

                {/* Bar */}
                <rect
                  x={leftPad}
                  y={y + 6}
                  width={barW}
                  height={rowH - 14}
                  rx={3}
                  fill={fill}
                  opacity={dimmed ? 0.18 : 1}
                  style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                  onMouseEnter={(e) => {
                    const svgEl = e.currentTarget.closest("svg") as SVGSVGElement;
                    const rect = svgEl?.getBoundingClientRect();
                    const barRect = e.currentTarget.getBoundingClientRect();
                    if (rect) setTooltipY(barRect.top - rect.top);
                    setHovered(i);
                  }}
                  onMouseLeave={() => setHovered(null)}
                  aria-label={`${r.label}: ${r.scorePp} (rank ${r.rank} of ${r.total})`}
                />

                {/* Score label */}
                <text
                  x={leftPad + barW + 6}
                  y={y + rowH / 2 + 4}
                  fontSize={isHero ? 11 : 10}
                  fontFamily="var(--font-data, monospace)"
                  fill={
                    dimmed
                      ? "rgba(200,200,200,0.25)"
                      : r.tier === "Directional"
                        ? i === 0
                          ? "#a78bfa"
                          : "#8b5cf6"
                        : "#fbbf24"
                  }
                  style={{ transition: "fill 0.15s" }}
                >
                  {r.scorePp.toFixed(1)}
                </text>

                {/* Rank badge */}
                <text
                  x={leftPad + barW + (isHero ? 42 : 38)}
                  y={y + rowH / 2 + 4}
                  fontSize="8"
                  fontFamily="sans-serif"
                  fill={dimmed ? "rgba(200,200,200,0.2)" : "var(--qgi-text-muted)"}
                  style={{ transition: "fill 0.15s" }}
                >
                  #{r.rank}
                </text>

                {/* HARD_FAIL marker */}
                {r.hardFail && (
                  <text
                    x={leftPad + barW + (isHero ? 58 : 52)}
                    y={y + rowH / 2 + 4}
                    fontSize="7"
                    fontFamily="sans-serif"
                    fill={dimmed ? "rgba(251,113,133,0.2)" : "rgba(251,113,133,0.7)"}
                    style={{ transition: "fill 0.15s" }}
                  >
                    *
                  </text>
                )}
              </g>
            );
          })}

          {/* Axis line */}
          <line
            x1={leftPad}
            y1={6}
            x2={leftPad}
            y2={svgH - (isHero ? 28 : 20)}
            stroke="var(--qgi-border)"
            strokeWidth={1}
          />

          {/* Legend */}
          <g transform={`translate(${leftPad}, ${svgH - (isHero ? 22 : 14)})`}>
            <rect x={0} y={0} width={8} height={3} rx={1} fill="#a78bfa" />
            <text
              x={12}
              y={4}
              fontSize="8"
              fill="var(--qgi-text-dim)"
              fontFamily="sans-serif"
            >
              Directional tier
            </text>
            <rect x={90} y={0} width={8} height={3} rx={1} fill="rgba(251,191,36,0.65)" />
            <text
              x={102}
              y={4}
              fontSize="8"
              fill="var(--qgi-text-dim)"
              fontFamily="sans-serif"
            >
              Experimental tier
            </text>
            <text
              x={190}
              y={4}
              fontSize="8"
              fill="rgba(251,113,133,0.7)"
              fontFamily="sans-serif"
            >
              * HARD_FAIL (orientation only)
            </text>
          </g>
        </svg>
      </div>

      {/* Tooltip */}
      {hovered !== null &&
        (() => {
          const r = RECIPES[hovered];
          return (
            <div
              style={{
                position: "absolute",
                left: leftPad + Math.round((r.scorePp / maxScore) * barMaxW) / 2,
                top: tooltipY,
                transform: "translate(-50%, -115%)",
                minWidth: 210,
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
              <div
                style={{
                  color: "var(--qgi-text)",
                  fontWeight: 600,
                  marginBottom: 4,
                }}
              >
                {r.label}
              </div>
              <div style={{ display: "flex", gap: 14 }}>
                <span>
                  <span style={{ color: "var(--qgi-text-muted)", fontSize: 10 }}>
                    Score
                  </span>
                  <br />
                  <span
                    style={{
                      fontFamily: "var(--font-data, monospace)",
                      color: r.tier === "Directional" ? "#a78bfa" : "#fbbf24",
                      fontSize: 14,
                    }}
                  >
                    {r.scorePp.toFixed(1)}
                  </span>
                </span>
                <span>
                  <span style={{ color: "var(--qgi-text-muted)", fontSize: 10 }}>
                    Global rank
                  </span>
                  <br />
                  <span
                    style={{
                      fontFamily: "var(--font-data, monospace)",
                      color: "var(--qgi-text)",
                      fontSize: 14,
                    }}
                  >
                    #{r.rank}/{r.total}
                  </span>
                </span>
                <span>
                  <span style={{ color: "var(--qgi-text-muted)", fontSize: 10 }}>
                    LOCO AUC
                  </span>
                  <br />
                  <span
                    style={{
                      fontFamily: "var(--font-data, monospace)",
                      color: "var(--qgi-text)",
                      fontSize: 14,
                    }}
                  >
                    {r.locoAuc.toFixed(4)}
                  </span>
                </span>
              </div>
              {r.hardFail && (
                <div
                  style={{
                    color: "rgba(251,113,133,0.85)",
                    fontSize: 10,
                    marginTop: 6,
                  }}
                >
                  HARD_FAIL: treat as orientation signal only.
                </div>
              )}
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Pakistan scores across five endogenous structural recipes, te-fleet-run-2 (scored
        2026-06-01). Purple = Directional tier (LOCO AUC 0.72+); amber = Experimental
        tier. Asterisk = HARD_FAIL verdict (Political Repression, Democratic Transition):
        treat those two scores as contextual orientation only. Source: QGI te-fleet-run-2.
      </figcaption>
    </figure>
  );
}

/** Hero variant (larger, displayed above the fold) */
export function ChartMultiRecipeConvergenceHero() {
  return <MultiRecipeInner isHero />;
}

/** Standard in-article variant */
export default function ChartMultiRecipeConvergence() {
  return <MultiRecipeInner isHero={false} />;
}
