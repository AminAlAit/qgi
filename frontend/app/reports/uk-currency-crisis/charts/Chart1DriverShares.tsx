"use client";

import { useState } from "react";

const DRIVERS = [
  {
    rank: 1,
    label: "Judicial Reform Attempts",
    shortLabel: "Judicial Reform",
    code: "v2jureform",
    share: 34.5,
  },
  {
    rank: 2,
    label: "Current Account Balance (% GDP)",
    shortLabel: "Current Account",
    code: "BN.CAB.XOKA.GD.ZS",
    share: 27.2,
  },
  {
    rank: 3,
    label: "Imports of goods and services",
    shortLabel: "Imports",
    code: "NE.IMP.GNFS.CD",
    share: 20.8,
  },
  {
    rank: 4,
    label: "GDP (current USD)",
    shortLabel: "GDP nominal",
    code: "NY.GDP.MKTP.CD",
    share: 14.1,
  },
  {
    rank: 5,
    label: "GDP deflator (annual %)",
    shortLabel: "GDP deflator",
    code: "NY.GDP.DEFL.KD.ZG",
    share: 3.5,
  },
] as const;

type HoveredIdx = number | null;

export default function Chart1DriverShares() {
  const [hovered, setHovered] = useState<HoveredIdx>(null);
  const [tooltipY, setTooltipY] = useState(0);

  const rowH = 36;
  const barMaxW = 320;
  const leftPad = 110;
  const rightPad = 60;
  const svgW = leftPad + barMaxW + rightPad;
  const svgH = DRIVERS.length * rowH + 20;
  const maxShare = 40;

  return (
    <figure
      id="chart-driver-shares"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <div style={{ overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${svgW} ${svgH}`}
          width="100%"
          style={{ display: "block", overflow: "visible", minWidth: 400 }}
          aria-label="Horizontal bar chart: SHAP driver shares for UK currency-crisis score, te-fleet-run-2"
        >
          <title>UK currency-crisis: SHAP driver shares (te-fleet-run-2)</title>

          {DRIVERS.map((d, i) => {
            const y = 10 + i * rowH;
            const barW = Math.round((d.share / maxShare) * barMaxW);
            const isTop3 = i < 3;
            const isHov = hovered === i;
            const dimmed = hovered !== null && !isHov;
            const fill =
              i === 0 ? "#a78bfa" : isTop3 ? "#8b5cf6" : "rgba(167,139,250,0.45)";

            return (
              <g key={d.rank}>
                {/* Row label */}
                <text
                  x={leftPad - 8}
                  y={y + rowH / 2 + 4}
                  textAnchor="end"
                  fontSize="10"
                  fontFamily="sans-serif"
                  fill={dimmed ? "rgba(200,200,200,0.3)" : "var(--qgi-text-dim)"}
                  style={{ transition: "fill 0.15s" }}
                >
                  {d.shortLabel}
                </text>

                {/* Bar */}
                <rect
                  x={leftPad}
                  y={y + 6}
                  width={barW}
                  height={rowH - 14}
                  rx={3}
                  fill={fill}
                  opacity={dimmed ? 0.2 : 1}
                  style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                  onMouseEnter={(e) => {
                    const svgEl = e.currentTarget.closest("svg") as SVGSVGElement;
                    const rect = svgEl?.getBoundingClientRect();
                    const barRect = e.currentTarget.getBoundingClientRect();
                    if (rect) {
                      setTooltipY(barRect.top - rect.top);
                    }
                    setHovered(i);
                  }}
                  onMouseLeave={() => setHovered(null)}
                  aria-label={`${d.label}: ${d.share}% of signal`}
                />

                {/* Share label */}
                <text
                  x={leftPad + barW + 6}
                  y={y + rowH / 2 + 4}
                  fontSize="10"
                  fontFamily="var(--font-data, monospace)"
                  fill={
                    dimmed
                      ? "rgba(200,200,200,0.3)"
                      : i === 0
                        ? "#a78bfa"
                        : "var(--qgi-text-muted)"
                  }
                  style={{ transition: "fill 0.15s" }}
                >
                  {d.share}%
                </text>
              </g>
            );
          })}

          {/* Axis line */}
          <line
            x1={leftPad}
            y1={8}
            x2={leftPad}
            y2={svgH - 4}
            stroke="var(--qgi-border)"
            strokeWidth={1}
          />

          {/* Total label */}
          <text
            x={leftPad}
            y={svgH + 4}
            fontSize="9"
            fontFamily="sans-serif"
            fill="var(--qgi-text-muted)"
          >
            All five SHAP values positive. Top 3 = 82.5% of signal. Source: QGI
            te-fleet-run-2.
          </text>
        </svg>
      </div>

      {/* Tooltip */}
      {hovered !== null &&
        (() => {
          const d = DRIVERS[hovered];
          return (
            <div
              style={{
                position: "absolute",
                left:
                  leftPad +
                  Math.round((d.share / maxShare) * barMaxW) / 2 +
                  leftPad * 0.5,
                top: tooltipY,
                transform: "translate(-50%, -110%)",
                minWidth: 200,
                maxWidth: 280,
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
                Rank {d.rank}: {d.label}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color: "#a78bfa",
                  fontSize: 14,
                  margin: "4px 0",
                }}
              >
                {d.share}% of signal
              </div>
              <div style={{ color: "var(--qgi-text-muted)", fontSize: 10 }}>{d.code}</div>
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10, marginTop: 4 }}>
                SHAP value positive: pushes UK score toward crisis resemblance.
              </div>
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        SHAP driver decomposition for UK currency-crisis score, te-fleet-run-2 (scored
        2026-06-01). Judicial reform attempts (V-Dem v2jureform) leads at 34.5%,
        outweighing the current account deficit by 7.3 percentage points.
      </figcaption>
    </figure>
  );
}
