/**
 * CompareRankHistory -- one chart panel, two overlaid lines (A and B).
 *
 * Y-axis: rank 0-100, X-axis: 12 quarters.
 * Each line uses the L1 family color of THAT COUNTRY'S TOP RECIPE.
 * Caption: "A's rank on [recipe], B's rank on [recipe]. Different recipes; same scale."
 * ~280px tall, NEUTRAL_SLATE grid.
 *
 * Rendered as inline SVG so there are no chart library dependencies.
 * Retrospective only: no forward extrapolation past the last data point.
 *
 * V4.1 bar: familyColor() per country, NEUTRAL_SLATE grid, no em-dashes.
 */
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { familyColor, NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";

// Build a rank-history series for a country's top recipe momentum entry.
function rankSeries(country: CountryV4): number[] {
  const top = country.momentum[0];
  if (top) return top.rank_history;
  // Fallback: flat at the top recipe score.
  const score = country.top_recipes[0]?.score ?? 50;
  return Array(12).fill(score);
}

function topRecipeLabel(country: CountryV4): string {
  return country.top_recipes[0]?.label ?? "top trend";
}

function topRecipeColor(country: CountryV4): string {
  const l1Id = country.top_recipes[0]?.l1_id ?? "";
  const fallback = country.top_recipes[0]?.l1_color;
  return familyColor(l1Id, fallback);
}

// Build SVG polyline points from a series of 12 values (0..100).
function buildPoints(values: number[], w: number, h: number, pad: number): string {
  const innerW = w - pad * 2;
  const innerH = h - pad * 2;
  const n = values.length;
  return values
    .map((v, i) => {
      const x = pad + (n === 1 ? 0 : (i / (n - 1)) * innerW);
      const y = pad + innerH - (Math.max(0, Math.min(100, v)) / 100) * innerH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

const GRID_TICKS = [0, 25, 50, 75, 100];

export function CompareRankHistory({
  countryA,
  countryB,
}: {
  countryA: CountryV4;
  countryB: CountryV4;
}) {
  const svgW = 680;
  const svgH = 200;
  const padTop = 12;
  const padBottom = 24;
  const padLeft = 32;
  const padRight = 12;
  const plotW = svgW - padLeft - padRight;
  const plotH = svgH - padTop - padBottom;

  const seriesA = rankSeries(countryA);
  const seriesB = rankSeries(countryB);
  const colorA = topRecipeColor(countryA);
  const colorB = topRecipeColor(countryB);
  const labelA = topRecipeLabel(countryA);
  const labelB = topRecipeLabel(countryB);

  function xCoord(i: number): number {
    return padLeft + (i / 11) * plotW;
  }
  function yCoord(v: number): number {
    return padTop + plotH - (Math.max(0, Math.min(100, v)) / 100) * plotH;
  }

  const pointsA = seriesA
    .map((v, i) => `${xCoord(i).toFixed(1)},${yCoord(v).toFixed(1)}`)
    .join(" ");
  const pointsB = seriesB
    .map((v, i) => `${xCoord(i).toFixed(1)},${yCoord(v).toFixed(1)}`)
    .join(" ");

  const lastA = { x: xCoord(11), y: yCoord(seriesA[11] ?? 50) };
  const lastB = { x: xCoord(11), y: yCoord(seriesB[11] ?? 50) };

  // Quarter labels (Q1 ... Q12 abbreviated)
  const quarterLabels = ["Q1", "", "", "Q4", "", "", "Q7", "", "", "Q10", "", "Q12"];

  return (
    <PanelShell
      title="Rank history (last 12 quarters)"
      accent={NEUTRAL_SLATE}
      dataTour="compare-rank-history"
      fullWidth
    >
      {/* Legend */}
      <div
        style={{ display: "flex", gap: "16px", marginBottom: "12px", flexWrap: "wrap" }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "7px" }}>
          <FlagImg emoji={countryA.flag_emoji} name={countryA.name} width={14} />
          <span
            style={{
              fontSize: "11px",
              color: colorA,
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {countryA.name}
          </span>
          <span
            style={{
              fontSize: "10px",
              color: "var(--qgi-text-dim)",
              fontStyle: "italic",
            }}
          >
            on {labelA}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "7px" }}>
          <FlagImg emoji={countryB.flag_emoji} name={countryB.name} width={14} />
          <span
            style={{
              fontSize: "11px",
              color: colorB,
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {countryB.name}
          </span>
          <span
            style={{
              fontSize: "10px",
              color: "var(--qgi-text-dim)",
              fontStyle: "italic",
            }}
          >
            on {labelB}
          </span>
        </div>
        <span
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
            marginLeft: "auto",
          }}
        >
          Different trends; same scale.
        </span>
      </div>

      {/* SVG chart */}
      <svg
        width="100%"
        viewBox={`0 0 ${svgW} ${svgH}`}
        role="img"
        aria-label={`Rank history comparison for ${countryA.name} and ${countryB.name} over 12 quarters`}
        style={{ display: "block", overflow: "visible" }}
      >
        {/* Grid lines */}
        {GRID_TICKS.map((tick) => {
          const y = yCoord(tick);
          return (
            <g key={tick}>
              <line
                x1={padLeft}
                y1={y}
                x2={svgW - padRight}
                y2={y}
                stroke={NEUTRAL_SLATE}
                strokeWidth={tick === 0 || tick === 100 ? 1 : 0.5}
                strokeOpacity={0.25}
                strokeDasharray={tick === 0 || tick === 100 ? undefined : "3,4"}
              />
              <text
                x={padLeft - 4}
                y={y + 4}
                textAnchor="end"
                fontSize={9}
                fill={NEUTRAL_SLATE}
                opacity={0.6}
                fontFamily="ui-monospace, monospace"
              >
                {tick}
              </text>
            </g>
          );
        })}

        {/* Quarter labels */}
        {quarterLabels.map((ql, i) =>
          ql ? (
            <text
              key={i}
              x={xCoord(i)}
              y={svgH - 5}
              textAnchor="middle"
              fontSize={9}
              fill={NEUTRAL_SLATE}
              opacity={0.6}
              fontFamily="ui-monospace, monospace"
            >
              {ql}
            </text>
          ) : null
        )}

        {/* Line A */}
        <polyline
          points={pointsA}
          fill="none"
          stroke={colorA}
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={lastA.x} cy={lastA.y} r={2.8} fill={colorA} />

        {/* Line B */}
        <polyline
          points={pointsB}
          fill="none"
          stroke={colorB}
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="5,3"
        />
        <circle cx={lastB.x} cy={lastB.y} r={2.8} fill={colorB} />
      </svg>
    </PanelShell>
  );
}
