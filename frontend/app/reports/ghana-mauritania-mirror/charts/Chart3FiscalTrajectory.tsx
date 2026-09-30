"use client";

import { useState } from "react";

const IMF_ECF_MARKERS: Array<{
  year: number;
  label: string;
  debtGdp: number;
  event?: boolean;
}> = [
  { year: 2018, label: "Pre-programme", debtGdp: 57.9 },
  { year: 2019, label: "", debtGdp: 62.4 },
  { year: 2020, label: "COVID shock", debtGdp: 76.7 },
  { year: 2021, label: "", debtGdp: 81.1 },
  { year: 2022, label: "Sovereign default (Dec 2022)", debtGdp: 93.5, event: true },
  { year: 2023, label: "ECF entry (May 2023)", debtGdp: 88.2, event: true },
  { year: 2024, label: "ECF 2nd review", debtGdp: 79.1, event: true },
  { year: 2025, label: "ECF 3rd review", debtGdp: 74.3, event: true },
];

type TooltipData =
  | { kind: "point"; year: number; debtGdp: number; label?: string; event?: boolean }
  | { kind: "window" };

export default function Chart3FiscalTrajectory() {
  const [tooltip, setTooltip] = useState<{
    data: TooltipData;
    x: number;
    y: number;
  } | null>(null);

  const paddingL = 44;
  const paddingR = 16;
  const paddingT = 16;
  const paddingB = 28;
  const svgW = 560;
  const svgH = 220;
  const chartW = svgW - paddingL - paddingR;
  const chartH = svgH - paddingT - paddingB;

  const years = IMF_ECF_MARKERS.map((d) => d.year);
  const minYear = years[0];
  const maxYear = 2026;
  const minDebt = 50;
  const maxDebt = 100;

  const xScale = (year: number) =>
    paddingL + ((year - minYear) / (maxYear - minYear)) * chartW;
  const yScale = (val: number) =>
    paddingT + chartH - ((val - minDebt) / (maxDebt - minDebt)) * chartH;

  const pathD = IMF_ECF_MARKERS.map((d, i) => {
    const px = xScale(d.year);
    const py = yScale(d.debtGdp);
    return `${i === 0 ? "M" : "L"} ${px} ${py}`;
  }).join(" ");

  const handlePointEnter = (
    e: React.MouseEvent<SVGCircleElement>,
    d: (typeof IMF_ECF_MARKERS)[0]
  ) => {
    const rect = (
      e.currentTarget.closest("svg") as SVGSVGElement
    )?.getBoundingClientRect();
    const cx = parseFloat(e.currentTarget.getAttribute("cx") || "0");
    const cy = parseFloat(e.currentTarget.getAttribute("cy") || "0");
    if (rect) {
      setTooltip({
        data: {
          kind: "point",
          year: d.year,
          debtGdp: d.debtGdp,
          label: d.label,
          event: d.event,
        },
        x: cx,
        y: cy - 12,
      });
    }
  };

  const handleWindowEnter = () => {
    setTooltip({
      data: { kind: "window" },
      x: xScale(2025.75),
      y: paddingT + 20,
    });
  };

  const handleLeave = () => setTooltip(null);

  return (
    <figure
      id="ghana-imf-fiscal-trajectory"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${svgW} ${svgH + 36}`}
        width="100%"
        aria-label="Line chart showing Ghana public debt as percentage of GDP from 2018 to 2025 with IMF ECF program event markers, plus the May-November 2026 trigger watch window shaded"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>Ghana public debt/GDP 2018–2025 + May–November 2026 watch window</title>

        {/* Y-axis gridlines */}
        {[60, 70, 80, 90, 100].map((v) => (
          <g key={v}>
            <line
              x1={paddingL}
              y1={yScale(v)}
              x2={paddingL + chartW}
              y2={yScale(v)}
              stroke="var(--qgi-border)"
              strokeWidth="0.5"
              strokeDasharray="3 3"
            />
            <text
              x={paddingL - 4}
              y={yScale(v) + 4}
              textAnchor="end"
              fontSize="9"
              fontFamily="var(--font-data, monospace)"
              fill="var(--qgi-text-dim)"
            >
              {v}%
            </text>
          </g>
        ))}

        {/* Trigger-watch window shading */}
        <rect
          x={xScale(2025.5)}
          y={paddingT}
          width={xScale(2026) - xScale(2025.5)}
          height={chartH}
          fill="rgba(167,139,250,0.08)"
          style={{ cursor: "pointer" }}
          onMouseEnter={handleWindowEnter}
          onMouseLeave={handleLeave}
        />
        <text
          x={xScale(2025.75)}
          y={paddingT + 10}
          textAnchor="middle"
          fontSize="8"
          fontFamily="sans-serif"
          fill="rgba(167,139,250,0.6)"
          style={{ pointerEvents: "none" }}
        >
          Watch window
        </text>

        {/* Line */}
        <path
          d={pathD}
          fill="none"
          stroke="#a78bfa"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* Event markers and year labels */}
        {IMF_ECF_MARKERS.map((d) => {
          const px = xScale(d.year);
          const py = yScale(d.debtGdp);
          const isHovered =
            tooltip?.data?.kind === "point" &&
            "year" in tooltip.data &&
            tooltip.data.year === d.year;
          const baseR = d.event ? 5 : 3;
          return (
            <g key={d.year}>
              {isHovered && (
                <circle
                  cx={px}
                  cy={py}
                  r={baseR + 4}
                  fill="none"
                  stroke={d.event ? "#fbbf24" : "#a78bfa"}
                  strokeWidth="1"
                  opacity={0.5}
                />
              )}
              <circle
                cx={px}
                cy={py}
                r={isHovered ? baseR + 3 : baseR}
                fill={d.event ? "#fbbf24" : "#a78bfa"}
                stroke="var(--qgi-bg)"
                strokeWidth="1.5"
                style={{ cursor: "pointer", transition: "r 0.15s" }}
                onMouseEnter={(e) => handlePointEnter(e, d)}
                onMouseLeave={handleLeave}
                aria-label={`${d.year}: debt/GDP ${d.debtGdp}%${d.event ? ". " + d.label : ""}`}
              />
              {d.event && d.label && (
                <text
                  x={px}
                  y={py - 9}
                  textAnchor="middle"
                  fontSize="8"
                  fontFamily="sans-serif"
                  fill="#fbbf24"
                  style={{ pointerEvents: "none" }}
                >
                  {d.label}
                </text>
              )}
              <text
                x={px}
                y={paddingT + chartH + 14}
                textAnchor="middle"
                fontSize="9"
                fontFamily="var(--font-data, monospace)"
                fill="var(--qgi-text-dim)"
              >
                {d.year}
              </text>
            </g>
          );
        })}

        {/* Y-axis label */}
        <text
          x={8}
          y={paddingT + chartH / 2}
          textAnchor="middle"
          fontSize="9"
          fontFamily="sans-serif"
          fill="var(--qgi-text-muted)"
          transform={`rotate(-90, 8, ${paddingT + chartH / 2})`}
        >
          Debt / GDP %
        </text>

        {/* Legend */}
        <g transform={`translate(${paddingL}, ${svgH + 16})`}>
          <circle cx={5} cy={5} r={5} fill="#fbbf24" />
          <text
            x={14}
            y={9}
            fontSize="9"
            fill="var(--qgi-text-dim)"
            fontFamily="sans-serif"
          >
            ECF milestone (IMF program docs, not QGI data)
          </text>
          <circle cx={240} cy={5} r={3} fill="#a78bfa" />
          <text
            x={250}
            y={9}
            fontSize="9"
            fill="var(--qgi-text-dim)"
            fontFamily="sans-serif"
          >
            Debt/GDP datapoint (IMF Article IV historical)
          </text>
        </g>
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div
          style={{
            position: "absolute",
            left: tooltip.x,
            top: tooltip.y,
            transform: "translate(-50%, -100%)",
            minWidth: tooltip.data.kind === "window" ? 260 : 180,
            backgroundColor: "var(--qgi-surface)",
            border:
              tooltip.data.kind === "window"
                ? "1px dashed var(--qgi-border)"
                : "1px solid var(--qgi-border)",
            borderRadius: 4,
            padding: "8px 10px",
            pointerEvents: "none",
            zIndex: 10,
            fontSize: 11,
            lineHeight: 1.5,
          }}
        >
          {tooltip.data.kind === "window" ? (
            <>
              <div style={{ color: "var(--qgi-text)", fontWeight: 600, marginBottom: 2 }}>
                Trigger Watch Window
              </div>
              <div style={{ color: "var(--qgi-text-muted)" }}>
                May–November 2026 trigger watch window, next ECF disbursement review cycle
              </div>
            </>
          ) : (
            <>
              <div style={{ color: "var(--qgi-text)", fontWeight: 600, marginBottom: 2 }}>
                {tooltip.data.year}: {tooltip.data.debtGdp}% debt/GDP
              </div>
              {tooltip.data.event && tooltip.data.label && (
                <div style={{ color: "#fbbf24", marginBottom: 4 }}>
                  {tooltip.data.label}
                </div>
              )}
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                IMF Article IV historical series, not QGI data
              </div>
            </>
          )}
        </div>
      )}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Ghana public debt/GDP 2018–2025 (historical, IMF Article IV consultation series)
        with ECF program event markers. No IMF forward projections are included. ECF event
        markers derive from IMF program documentation, not QGI-computed data. Six-month
        trigger watch window (May–November 2026) shaded.
      </figcaption>
    </figure>
  );
}
