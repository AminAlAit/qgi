"use client";

import { useState } from "react";

type WindowRow = {
  window: "S" | "M" | "L" | "XL";
  label: string;
  india: number;
  pakistan: number;
  tier: { india: "MODERATE" | "INDICATIVE"; pakistan: "MODERATE" | "INDICATIVE" };
  description: string;
};

const SIGMA_DATA: ReadonlyArray<WindowRow> = [
  {
    window: "S",
    label: "Short (3–8y)",
    india: 1.94,
    pakistan: 1.94,
    tier: { india: "MODERATE", pakistan: "MODERATE" },
    description:
      "Short-horizon policy-cycle window. Both countries score above 1.0σ MODERATE, with identical 1.94σ readings.",
  },
  {
    window: "M",
    label: "Medium (9–20y)",
    india: 1.74,
    pakistan: 1.74,
    tier: { india: "MODERATE", pakistan: "MODERATE" },
    description:
      "Medium-horizon leadership-era window. Both at 1.74σ MODERATE. Still identical.",
  },
  {
    window: "L",
    label: "Long (21–40y)",
    india: 1.47,
    pakistan: 1.47,
    tier: { india: "MODERATE", pakistan: "MODERATE" },
    description: "Long-horizon structural-shift window. Both at 1.47σ MODERATE.",
  },
  {
    window: "XL",
    label: "Extra-Long (41y+)",
    india: 0.83,
    pakistan: 1.06,
    tier: { india: "INDICATIVE", pakistan: "MODERATE" },
    description:
      "Extra-long window: structural-identity scale. India drops to INDICATIVE (0.83σ), below the MODERATE threshold. Pakistan holds MODERATE (1.06σ). The convergence is recent, not decades-embedded.",
  },
];

export default function Chart3TimeWindowSigma() {
  const [hovered, setHovered] = useState<{
    window: string;
    country: "india" | "pakistan";
  } | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 2.2;
  const barH = 14;
  const barGap = 4;
  const groupGap = 28;
  const labelW = 100;
  const chartW = 380;
  const svgH = SIGMA_DATA.length * (barH * 2 + barGap + groupGap) + 50;

  const handleMouseEnter = (
    e: React.MouseEvent<SVGRectElement>,
    win: string,
    country: "india" | "pakistan"
  ) => {
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
    setHovered({ window: win, country });
  };
  const handleMouseLeave = () => setHovered(null);

  const thresholdX = labelW + Math.round((1.0 / maxVal) * chartW);

  return (
    <figure
      id="india-pakistan-sigma-tiers"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${labelW + chartW + 80} ${svgH}`}
        width="100%"
        aria-label="Grouped horizontal bar chart of India vs Pakistan salience sigma scores across S, M, L, and XL time windows"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          India vs Pakistan Civil War &amp; Insurgency salience σ across S/M/L/XL windows.
          Identical through L; India drops below MODERATE at XL.
        </title>

        {/* MODERATE threshold reference line */}
        <line
          x1={thresholdX}
          x2={thresholdX}
          y1={20}
          y2={svgH - 40}
          stroke="var(--qgi-text-muted)"
          strokeDasharray="3 3"
          strokeWidth={1}
        />
        <text
          x={thresholdX + 4}
          y={16}
          fontSize="9"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
          fontStyle="italic"
        >
          MODERATE ≥ 1.0σ
        </text>

        {SIGMA_DATA.map((row, i) => {
          const y = i * (barH * 2 + barGap + groupGap) + 30;
          const iW = Math.round((row.india / maxVal) * chartW);
          const pW = Math.round((row.pakistan / maxVal) * chartW);
          const iOp =
            hovered && !(hovered.window === row.window && hovered.country === "india")
              ? 0.3
              : 1;
          const pOp =
            hovered && !(hovered.window === row.window && hovered.country === "pakistan")
              ? 0.3
              : 1;
          const isXl = row.window === "XL";

          return (
            <g key={row.window}>
              <text
                x={labelW - 8}
                y={y + barH + 4}
                textAnchor="end"
                fontSize="11"
                fontFamily="sans-serif"
                fill={isXl ? "var(--qgi-accent)" : "var(--qgi-text-dim)"}
                fontWeight={isXl ? "600" : "400"}
              >
                {row.window}-tier
              </text>
              {/* India bar */}
              <rect
                x={labelW}
                y={y}
                width={iW}
                height={barH}
                rx={2}
                fill="rgba(167,139,250,0.8)"
                opacity={iOp}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, row.window, "india")}
                onMouseLeave={handleMouseLeave}
                aria-label={`India ${row.window} window ${row.india}σ ${row.tier.india}`}
              />
              <text
                x={labelW + iW + 4}
                y={y + barH - 2}
                fontSize="10"
                fontFamily="var(--font-data, monospace)"
                fill="rgba(167,139,250,0.9)"
                style={{ pointerEvents: "none", opacity: iOp }}
              >
                {row.india.toFixed(2)}σ
              </text>
              {/* Pakistan bar */}
              <rect
                x={labelW}
                y={y + barH + barGap}
                width={pW}
                height={barH}
                rx={2}
                fill="rgba(251,191,36,0.75)"
                opacity={pOp}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, row.window, "pakistan")}
                onMouseLeave={handleMouseLeave}
                aria-label={`Pakistan ${row.window} window ${row.pakistan}σ ${row.tier.pakistan}`}
              />
              <text
                x={labelW + pW + 4}
                y={y + barH + barGap + barH - 2}
                fontSize="10"
                fontFamily="var(--font-data, monospace)"
                fill="rgba(251,191,36,0.9)"
                style={{ pointerEvents: "none", opacity: pOp }}
              >
                {row.pakistan.toFixed(2)}σ
              </text>
              {/* XL annotation */}
              {isXl && (
                <text
                  x={labelW + Math.max(iW, pW) + 50}
                  y={y + barH + 4}
                  fontSize="10"
                  fontStyle="italic"
                  fill="var(--qgi-accent)"
                  fontFamily="sans-serif"
                  style={{ pointerEvents: "none" }}
                >
                  India drops below MODERATE
                </text>
              )}
            </g>
          );
        })}

        {/* Legend */}
        <g transform={`translate(${labelW}, ${svgH - 18})`}>
          <rect x={0} y={0} width={10} height={10} rx={2} fill="rgba(167,139,250,0.8)" />
          <text
            x={14}
            y={9}
            fontSize="10"
            fill="var(--qgi-text-dim)"
            fontFamily="sans-serif"
          >
            India
          </text>
          <rect x={70} y={0} width={10} height={10} rx={2} fill="rgba(251,191,36,0.75)" />
          <text
            x={84}
            y={9}
            fontSize="10"
            fill="var(--qgi-text-dim)"
            fontFamily="sans-serif"
          >
            Pakistan
          </text>
        </g>
      </svg>

      {hovered &&
        (() => {
          const row = SIGMA_DATA.find((r) => r.window === hovered.window);
          if (!row) return null;
          const val = hovered.country === "india" ? row.india : row.pakistan;
          const tier = hovered.country === "india" ? row.tier.india : row.tier.pakistan;
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
              <div style={{ color: "var(--qgi-text)", fontWeight: 600, marginBottom: 2 }}>
                {hovered.country === "india" ? "India" : "Pakistan"} &middot; {row.window}
                -tier {row.label}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color: hovered.country === "india" ? "#a78bfa" : "#fbbf24",
                  fontSize: 13,
                  margin: "4px 0",
                }}
              >
                {val.toFixed(2)}σ {tier}
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
        India and Pakistan are identical at S, M, and L windows (1.94 / 1.74 / 1.47 σ, all
        MODERATE). At the Extra-Long window, India drops to 0.83σ (INDICATIVE) while
        Pakistan holds at 1.06σ (MODERATE). The longer the time window, the more the
        structural similarity dissipates: the convergence is recent, not embedded. Source:
        QGI Civil War &amp; Insurgency salience tiers, April 2026 scoring run.
      </figcaption>
    </figure>
  );
}
