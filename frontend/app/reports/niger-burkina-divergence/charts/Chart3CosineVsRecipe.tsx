"use client";

import { useState } from "react";

type Bar = {
  key: string;
  label: string;
  value: number;
  color: string;
  description: string;
};

const COSINE_BAR: Bar = {
  key: "cosine",
  label: "Niger ↔ Burkina Faso cosine similarity (L1 composite)",
  value: 95,
  color: "rgba(167,139,250,0.55)",
  description:
    "Niger and Burkina Faso are each other's closest structural peer on the 8-dimension L1 risk vector. By every conventional composite-similarity metric, they are nearly identical.",
};

const RECIPE_BARS: ReadonlyArray<Bar> = [
  {
    key: "niger",
    label: "Niger, Multilateral Agreement Precedent Match",
    value: 94,
    color: "#a78bfa",
    description:
      "#4 of 58 globally on the Multilateral Agreement recipe. Trend features in tax revenue, female LFPR, and V&A are moving in directions historically associated with multilateral engagement.",
  },
  {
    key: "burkina",
    label: "Burkina Faso, Multilateral Agreement Precedent Match",
    value: 2,
    color: "rgba(251,191,36,0.7)",
    description:
      "#57 of 58 globally. Fiscal trajectory, demographic indicators, and governance trajectory are all moving in directions that historically precede multilateral disengagement.",
  },
];

export default function Chart3CosineVsRecipe() {
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const maxVal = 100;
  const chartW = 380;
  const labelW = 90;
  const barH = 22;
  const cosineY = 30;
  const dividerY = 70;
  const recipeRowY = 100;
  const recipeBarGap = 30;
  const svgH = recipeRowY + RECIPE_BARS.length * (barH + recipeBarGap) + 20;

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

  const allBars = [COSINE_BAR, ...RECIPE_BARS];

  return (
    <figure
      id="niger-cosine-vs-recipe"
      className="my-8 relative"
      style={{ maxWidth: "100%" }}
    >
      <svg
        viewBox={`0 0 ${labelW + chartW + 90} ${svgH}`}
        width="100%"
        aria-label="Two-panel chart contrasting Niger-Burkina cosine similarity at 95% against their divergent Multilateral Agreement recipe scores"
        style={{ display: "block", overflow: "visible" }}
      >
        <title>
          Cosine 95% at the L1 composite, recipe scores 94 vs 2: the structural paradox.
        </title>

        {/* Top section label */}
        <text
          x={labelW}
          y={cosineY - 12}
          fontSize="9"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
          letterSpacing="0.1em"
        >
          AT THE L1 COMPOSITE LEVEL
        </text>

        {/* Cosine row */}
        <text
          x={labelW - 8}
          y={cosineY + barH / 2 + 4}
          textAnchor="end"
          fontSize="11"
          fontFamily="sans-serif"
          fill="var(--qgi-text)"
        >
          Cosine peer
        </text>
        <rect
          x={labelW}
          y={cosineY}
          width={Math.round((COSINE_BAR.value / maxVal) * chartW)}
          height={barH}
          rx={3}
          fill={COSINE_BAR.color}
          stroke="var(--qgi-accent)"
          strokeWidth={1}
          style={{ cursor: "pointer", transition: "opacity 0.15s" }}
          opacity={hovered && hovered !== COSINE_BAR.key ? 0.3 : 1}
          onMouseEnter={(e) => handleMouseEnter(e, COSINE_BAR.key)}
          onMouseLeave={handleMouseLeave}
          aria-label={`Niger and Burkina Faso cosine similarity ${COSINE_BAR.value}%`}
        />
        <text
          x={labelW + Math.round((COSINE_BAR.value / maxVal) * chartW) + 6}
          y={cosineY + barH / 2 + 4}
          fontSize="13"
          fontFamily="var(--font-data, monospace)"
          fill="var(--qgi-accent)"
          fontWeight="600"
          style={{ pointerEvents: "none" }}
        >
          95%
        </text>

        {/* Divider */}
        <line
          x1={labelW - 20}
          x2={labelW + chartW + 70}
          y1={dividerY}
          y2={dividerY}
          stroke="var(--qgi-border)"
          strokeWidth={1}
        />
        <text
          x={labelW + chartW / 2}
          y={dividerY + 14}
          textAnchor="middle"
          fontSize="10"
          fontStyle="italic"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
        >
          but at the recipe-cohort level…
        </text>

        {/* Recipe bars */}
        <text
          x={labelW}
          y={recipeRowY + 12}
          fontSize="9"
          fill="var(--qgi-text-muted)"
          fontFamily="sans-serif"
          letterSpacing="0.1em"
        >
          AT THE MULTILATERAL AGREEMENT RECIPE
        </text>

        {RECIPE_BARS.map((bar, i) => {
          const y = recipeRowY + 28 + i * (barH + recipeBarGap);
          const w = Math.round((bar.value / maxVal) * chartW);
          const opacity = hovered && hovered !== bar.key ? 0.3 : 1;

          return (
            <g key={bar.key}>
              <text
                x={labelW - 8}
                y={y + barH / 2 + 4}
                textAnchor="end"
                fontSize="11"
                fontFamily="sans-serif"
                fill="var(--qgi-text)"
                fontWeight={bar.key === "niger" ? "600" : "400"}
                style={{ opacity }}
              >
                {bar.key === "niger" ? "Niger" : "Burkina Faso"}
              </text>
              <rect
                x={labelW}
                y={y}
                width={Math.max(w, 2)}
                height={barH}
                rx={3}
                fill={bar.color}
                opacity={opacity}
                style={{ cursor: "pointer", transition: "opacity 0.15s" }}
                onMouseEnter={(e) => handleMouseEnter(e, bar.key)}
                onMouseLeave={handleMouseLeave}
                aria-label={`${bar.label}: ${bar.value}/100`}
              />
              <text
                x={labelW + Math.max(w, 2) + 6}
                y={y + barH / 2 + 4}
                fontSize="13"
                fontFamily="var(--font-data, monospace)"
                fill={bar.color === "#a78bfa" ? "#a78bfa" : "rgba(251,191,36,0.9)"}
                fontWeight="600"
                style={{ pointerEvents: "none", opacity }}
              >
                {bar.value}/100
              </text>
            </g>
          );
        })}
      </svg>

      {hovered &&
        (() => {
          const bar = allBars.find((b) => b.key === hovered);
          if (!bar) return null;
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
                {bar.label}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data, monospace)",
                  color:
                    bar.key === "cosine"
                      ? "var(--qgi-accent)"
                      : bar.key === "niger"
                        ? "#a78bfa"
                        : "#fbbf24",
                  fontSize: 14,
                  margin: "4px 0",
                }}
              >
                {bar.key === "cosine" ? "95%" : `${bar.value}/100`}
              </div>
              <div style={{ color: "var(--qgi-text-dim)", fontSize: 10 }}>
                {bar.description}
              </div>
            </div>
          );
        })()}

      <figcaption
        className="mt-2 text-xs leading-relaxed"
        style={{ color: "var(--qgi-text-dim)" }}
      >
        The structural paradox in a single frame: Niger and Burkina Faso are each
        other&apos;s #1 cosine peer at the L1 composite (95% similarity), yet the
        Multilateral Agreement recipe places them at opposite ends of the same 58-country
        cohort (94/100 vs 2/100). The L1 composite captures regime, conflict, and
        governance co-presence; the recipe scores trend features, the direction of change.
        These read the same countries differently. Source: QGI April 2026 scoring run.
      </figcaption>
    </figure>
  );
}
