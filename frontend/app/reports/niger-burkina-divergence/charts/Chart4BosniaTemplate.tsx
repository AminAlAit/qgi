"use client";

import { useState } from "react";

type Marker = {
  key: string;
  label: string;
  country: string;
  score: number;
  description: string;
  isTemplate?: boolean;
};

const MARKERS: ReadonlyArray<Marker> = [
  {
    key: "bosnia",
    label: "Bosnia and Herzegovina",
    country: "Bosnia and Herzegovina",
    score: 99,
    description:
      "#1 of 58 globally. Highest convergence scores fired at -4 to +1 year relative to the Dayton-era multilateral event. The structural template the model learned from.",
    isTemplate: true,
  },
  {
    key: "niger",
    label: "Niger (current position)",
    country: "Niger",
    score: 94,
    description:
      "#4 of 58. Structurally analogous to Bosnia's pre-negotiation phase: indicator trajectory is building the structural case for multilateral re-engagement while the political surface maintains an isolation posture.",
  },
];

const LEAD_TIMES = [
  { y: -4, label: "-4y" },
  { y: -3, label: "-3y" },
  { y: -2, label: "-2y" },
  { y: -1, label: "-1y" },
  { y: 0, label: "event" },
  { y: 1, label: "+1y" },
];

export default function Chart4BosniaTemplate() {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 100;
  const chartW = 380;
  const labelW = 130;
  const barH = 22;
  const groupGap = 30;
  const barsTop = 20;
  const timelineY = MARKERS.length * (barH + groupGap) + 50;
  const svgH = timelineY + 60;

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

  const timelineLeft = labelW;
  const timelineRight = labelW + chartW;
  const timelineSpan = timelineRight - timelineLeft;

  return (
    <figure
      id="niger-bosnia-template"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${labelW + chartW + 60} ${svgH}`}
        width="100%"
        aria-label="Bar chart comparing Bosnia at 99 and Niger at 94 on the Multilateral Agreement recipe, with a lead-time timeline showing -4 to +1 year structural-signal window"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          Bosnia at 99/100 is the multilateral re-engagement template; Niger at 94/100 may
          be at the same structural-readiness point.
        </title>

        {MARKERS.map((m, i) => {
          const y = barsTop + i * (barH + groupGap);
          const w = Math.round((m.score / maxVal) * chartW);
          const opacity = hovered && hovered !== m.key ? 0.3 : 1;
          const color = m.isTemplate ? "#a78bfa" : "rgba(167,139,250,0.65)";

          return (
            <g key={m.key}>
              <text
                x={labelW - 8}
                y={y + barH / 2 + 4}
                textAnchor="end"
                fontSize="12"
                fontFamily="sans-serif"
                fill="var(--qgi-text)"
                fontWeight={m.isTemplate ? "600" : "400"}
                style={{ opacity }}
              >
                {m.country}
              </text>
              <rect
                x={labelW}
                y={y}
                width={w}
                height={barH}
                rx={3}
                fill={color}
                opacity={opacity}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, m.key)}
                onMouseLeave={handleMouseLeave}
                aria-label={`${m.country}: ${m.score}/100 on Multilateral Agreement`}
              />
              <text
                x={labelW + w + 6}
                y={y + barH / 2 + 4}
                fontSize="13"
                fontFamily="var(--font-data, monospace)"
                fill={color}
                fontWeight="600"
                style={{ pointerEvents: "none", opacity }}
              >
                {m.score}/100
              </text>
              {m.isTemplate && (
                <text
                  x={labelW + w + 60}
                  y={y + barH / 2 + 4}
                  fontSize="9"
                  fontStyle="italic"
                  fill="var(--qgi-accent)"
                  fontFamily="sans-serif"
                  style={{ pointerEvents: "none", opacity }}
                >
                  ▲ template
                </text>
              )}
            </g>
          );
        })}

        {/* Lead-time timeline */}
        <text
          x={labelW}
          y={timelineY - 16}
          fontSize="9"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
          letterSpacing="0.1em"
        >
          BOSNIA STRUCTURAL-SIGNAL LEAD TIME (PER DASHBOARD)
        </text>
        <line
          x1={timelineLeft}
          x2={timelineRight}
          y1={timelineY}
          y2={timelineY}
          stroke="var(--qgi-border)"
          strokeWidth={1}
        />
        {LEAD_TIMES.map((t, i) => {
          const x = timelineLeft + (i / (LEAD_TIMES.length - 1)) * timelineSpan;
          const isEvent = t.y === 0;
          return (
            <g key={t.label}>
              <line
                x1={x}
                x2={x}
                y1={timelineY - 4}
                y2={timelineY + 4}
                stroke={isEvent ? "var(--qgi-accent)" : "var(--qgi-text-muted)"}
                strokeWidth={isEvent ? 2 : 1}
              />
              <text
                x={x}
                y={timelineY + 16}
                textAnchor="middle"
                fontSize="10"
                fill={isEvent ? "var(--qgi-accent)" : "var(--qgi-text-dim)"}
                fontFamily="var(--font-data, monospace)"
                fontWeight={isEvent ? "600" : "400"}
              >
                {t.label}
              </text>
            </g>
          );
        })}
        {/* Signal window shading -4 to +1 */}
        <rect
          x={timelineLeft}
          y={timelineY - 8}
          width={timelineSpan}
          height={16}
          fill="rgba(167,139,250,0.08)"
        />
        <text
          x={timelineLeft + timelineSpan / 2}
          y={timelineY + 34}
          textAnchor="middle"
          fontSize="10"
          fontStyle="italic"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
        >
          Niger may currently be 1-3 years to the left of the &ldquo;event&rdquo;
        </text>
      </svg>

      {hovered &&
        (() => {
          const m = MARKERS.find((x) => x.key === hovered);
          if (!m) return null;
          return (
            <div
              style={{
                position: "absolute",
                left: tooltipPos.x,
                top: tooltipPos.y,
                transform: "translateY(-50%)",
                width: 260,
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
                {m.country}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color: "#a78bfa",
                  fontSize: 14,
                  margin: "4px 0",
                }}
              >
                {m.score}/100
              </div>
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                {m.description}
              </div>
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Bosnia and Herzegovina is the global #1 on the Multilateral Agreement recipe at
        99/100, with structural signals firing -4 to +1 year relative to the Dayton-era
        multilateral event. Niger&apos;s current 94/100 is the closest match to that
        template in the 2026 cohort, suggesting a structural pre-negotiation phase.
        Source: QGI Multilateral Agreement recipe dashboard, April 2026 scoring run.
      </figcaption>
    </figure>
  );
}
