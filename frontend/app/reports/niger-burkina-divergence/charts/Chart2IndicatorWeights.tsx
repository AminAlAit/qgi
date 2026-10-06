"use client";

import { useState } from "react";

type Row = {
  key: string;
  label: string;
  shortLabel: string;
  weight: number;
  mechanism: string;
  caveat?: string;
};

const INDICATORS: ReadonlyArray<Row> = [
  {
    key: "tax_revenue",
    label: "Tax revenue (% of GDP), year-over-year change",
    shortLabel: "Tax revenue (% GDP) Δ",
    weight: 0.6,
    mechanism:
      "Niger's fiscal trajectory has been improving since ECOWAS sanctions were lifted in February 2024; uranium export revenues resumed, producing a measurable improvement in tax-revenue-to-GDP trajectory.",
  },
  {
    key: "female_lfpr",
    label: "Female labour force participation rate, year-over-year change",
    shortLabel: "Female LFPR Δ",
    weight: 0.53,
    mechanism:
      "Niger has the world's highest fertility rate and one of the lowest female LFPRs. Marginal upward movement registers as a strong trend signal, because the model trained on historical patterns where demographic inclusion preceded multilateral engagement.",
  },
  {
    key: "voice_accountability",
    label: "Voice and Accountability (V-Dem), year-over-year change",
    shortLabel: "V&A (V-Dem) Δ",
    weight: 0.4,
    mechanism:
      "The rate of decline may have stabilised relative to the immediate post-coup period, which registers as a less-negative trend feature. V-Dem's coding may produce artefactual readings in post-coup environments where institutional continuity is disrupted.",
    caveat: "Possible country bias",
  },
];

export default function Chart2IndicatorWeights() {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 0.65;
  const barH = 22;
  const groupGap = 30;
  const labelW = 200;
  const chartW = 350;
  const svgH = INDICATORS.length * (barH + groupGap) + 20;

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
      id="niger-indicator-weights"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${labelW + chartW + 80} ${svgH}`}
        width="100%"
        aria-label="Horizontal bar chart of the three indicators driving Niger's Multilateral Agreement signal"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          Niger Multilateral Agreement indicator fingerprint: tax revenue Δ (0.60), Female
          LFPR Δ (0.53), V&amp;A Δ (0.40 with caveat).
        </title>
        {INDICATORS.map((row, i) => {
          const y = i * (barH + groupGap) + 10;
          const w = Math.round((row.weight / maxVal) * chartW);
          const opacity = hovered && hovered !== row.key ? 0.3 : 1;
          const isCaveat = !!row.caveat;

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
                fill={isCaveat ? "rgba(251,191,36,0.65)" : "#a78bfa"}
                opacity={opacity}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, row.key)}
                onMouseLeave={handleMouseLeave}
                aria-label={`${row.shortLabel}: importance ${row.weight}${row.caveat ? `, ${row.caveat}` : ""}`}
              />
              <text
                x={labelW + w + 6}
                y={y + barH / 2 + 4}
                fontSize="12"
                fontFamily="var(--font-data, monospace)"
                fill={isCaveat ? "rgba(251,191,36,0.9)" : "#a78bfa"}
                fontWeight="600"
                style={{ pointerEvents: "none", opacity }}
              >
                {row.weight.toFixed(2)}
              </text>
              {isCaveat && (
                <text
                  x={labelW + w + 50}
                  y={y + barH / 2 + 4}
                  fontSize="9"
                  fontFamily="sans-serif"
                  fontStyle="italic"
                  fill="rgba(251,191,36,0.85)"
                  style={{ pointerEvents: "none", opacity }}
                >
                  ⚠ caveat
                </text>
              )}
            </g>
          );
        })}
        <text
          x={labelW + chartW / 2}
          y={svgH - 4}
          textAnchor="middle"
          fontSize="10"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
        >
          Importance weight (trend-features model, recipe Multilateral Agreement)
        </text>
      </svg>

      {hovered &&
        (() => {
          const row = INDICATORS.find((r) => r.key === hovered);
          if (!row) return null;
          const isCaveat = !!row.caveat;
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
                  color: isCaveat ? "#fbbf24" : "#a78bfa",
                  fontSize: 13,
                  margin: "4px 0",
                }}
              >
                importance {row.weight.toFixed(2)}
              </div>
              <div
                style={{ color: "var(--qgi-text-dim)", fontSize: 10, marginBottom: 4 }}
              >
                {row.mechanism}
              </div>
              {row.caveat && (
                <div
                  style={{
                    color: "rgba(251,191,36,0.9)",
                    fontSize: 10,
                    fontStyle: "italic",
                    marginTop: 4,
                  }}
                >
                  ⚠ {row.caveat}
                </div>
              )}
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        Niger&apos;s top three Multilateral Agreement indicators: tax revenue change
        (0.60), female labour force participation change (0.53), Voice &amp;
        Accountability change (0.40, with V-Dem &ldquo;Possible Country Bias&rdquo;
        caveat). Trend features (direction of change), not absolute levels. Source: QGI
        Multilateral Agreement recipe dossier, April 2026 scoring run.
      </figcaption>
    </figure>
  );
}
