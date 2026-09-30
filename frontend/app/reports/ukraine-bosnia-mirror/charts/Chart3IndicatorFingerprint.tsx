"use client";

import { useState } from "react";

type Row = {
  key: string;
  label: string;
  shortLabel: string;
  weight: number;
  mechanism: string;
};

const INDICATORS: ReadonlyArray<Row> = [
  {
    key: "population",
    label: "Population (total), year-over-year change",
    shortLabel: "Population change",
    weight: 0.53,
    mechanism:
      "Top driver. For Ukraine, captures the displacement-and-return dynamics following the 2022 mobilisation. Demographic flux is the leading signal, not diplomatic posture.",
  },
  {
    key: "employment",
    label: "Employment ratio (% population), change",
    shortLabel: "Employment ratio change",
    weight: 0.42,
    mechanism:
      "Captures the labour-market post-mobilisation adjustment and the recovery curve. The model reads this trajectory shape as historically associated with bilateral treaty engagement.",
  },
  {
    key: "mobile",
    label: "Mobile cellular subscriptions, year-over-year change",
    shortLabel: "Mobile cellular subs change",
    weight: 0.38,
    mechanism:
      "Telecom infrastructure rebuild + restoration of normal civilian connectivity. A structural-economic-momentum indicator, not a diplomatic one.",
  },
];

export default function Chart3IndicatorFingerprint() {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 0.6;
  const barH = 26;
  const groupGap = 22;
  const labelW = 200;
  const chartW = 320;
  const svgH = INDICATORS.length * (barH + groupGap) + 30;

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
    <figure
      id="ukraine-bilateral-treaty-fingerprint"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${labelW + chartW + 80} ${svgH}`}
        width="100%"
        aria-label="Horizontal bar chart of the three Bilateral Treaty recipe indicators driving Ukraine's signal"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          Ukraine Bilateral Treaty fingerprint: population change (0.53), employment ratio
          change (0.42), mobile cellular subscriptions change (0.38). Not diplomatic
          variables.
        </title>
        {INDICATORS.map((row, i) => {
          const y = i * (barH + groupGap) + 12;
          const w = Math.round((row.weight / maxVal) * chartW);
          const opacity = hovered && hovered !== row.key ? 0.3 : 1;

          return (
            <g key={row.key}>
              <text
                x={labelW - 8}
                y={y + barH / 2 + 4}
                textAnchor="end"
                fontSize="12"
                fontFamily="sans-serif"
                fill="var(--qgi-text)"
                style={{ opacity }}
              >
                {row.shortLabel}
              </text>
              <rect
                x={labelW}
                y={y}
                width={w}
                height={barH}
                rx={3}
                fill="#a78bfa"
                opacity={opacity}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, row.key)}
                onMouseLeave={handleMouseLeave}
                aria-label={`${row.shortLabel}: importance ${row.weight}`}
              />
              <text
                x={labelW + w + 6}
                y={y + barH / 2 + 4}
                fontSize="13"
                fontFamily="var(--font-data, monospace)"
                fill="#a78bfa"
                fontWeight="600"
                style={{ pointerEvents: "none", opacity }}
              >
                {row.weight.toFixed(2)}
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
          Importance weight, Bilateral Treaty recipe
        </text>
      </svg>

      {hovered &&
        (() => {
          const row = INDICATORS.find((r) => r.key === hovered);
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
                padding: "10px 12px",
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
                  color: "#a78bfa",
                  fontSize: 13,
                  margin: "4px 0",
                }}
              >
                importance {row.weight.toFixed(2)}
              </div>
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                {row.mechanism}
              </div>
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Ukraine&apos;s Bilateral Treaty recipe indicator fingerprint: demographic and
        economic trajectory variables, not diplomatic variables. The model is reading
        structural-economic momentum (displacement-and-return, employment shock,
        infrastructure rebuild) as historically associated with bilateral treaty
        engagement. Source: QGI Bilateral Treaty recipe dossier (LOCO AUC 0.6681, MODERATE
        evidence grade), April 2026 scoring run.
      </figcaption>
    </figure>
  );
}
