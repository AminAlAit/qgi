/**
 * FeaturedPairPanel — Section 6: featured pair of the vintage.
 *
 * Single hero pair, 12-point sparkline of both countries' indicator-composite
 * movement overlaid, one-paragraph editorial gloss, "Open the pair" CTA into
 * /patterns/{slug}.
 *
 * METHODOLOGY GUARD (Marcus, binding):
 * The featured_editorial field MUST be HISTORICAL-VOICE ONLY. This component
 * renders it verbatim. The constraint is enforced at the data layer
 * (patterns-v4-main-data.ts). DO NOT add any "current score", "currently
 * resembles", or "recipe activation" text here or in the data file.
 */
import Link from "next/link";
import type { Route } from "next";
import type { FeaturedPair } from "@/lib/te-mock/patterns-v4-main-data";
import { pairFlagFor, pairSlug } from "@/lib/te-mock/patterns-v4-main-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";

// 12-point deterministic sparklines seeded from the pair data.
// Two overlaid series: country A (warm line) and country B (cool line).
// Values are illustrative indicator-composite movements, not real data.
function buildSparkPoints(seed: number, offset = 0): number[] {
  const TAU = Math.PI * 2;
  return Array.from({ length: 12 }, (_, i) => {
    const t = i / 11;
    const wave = Math.sin(t * TAU * 1.3 + seed) * 0.4;
    const trend = -0.6 + t * 1.4 + offset;
    return Math.round((trend + wave) * 10) / 10;
  });
}

function normalizeToPixels(points: number[], height: number): number[] {
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  return points.map((v) => height - ((v - min) / range) * height);
}

function SparklineSvg({
  seriesA,
  seriesB,
  width,
  height,
}: {
  seriesA: number[];
  seriesB: number[];
  width: number;
  height: number;
}) {
  const allValues = [...seriesA, ...seriesB];
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min || 1;

  const toY = (v: number) => height - ((v - min) / range) * (height - 8) - 4;
  const toX = (i: number) => (i / 11) * (width - 8) + 4;

  const buildPath = (pts: number[]) =>
    pts
      .map((v, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(v).toFixed(1)}`)
      .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      style={{ display: "block" }}
    >
      {/* Series B (cool, behind) */}
      <path
        d={buildPath(seriesB)}
        fill="none"
        stroke="#5B7E99"
        strokeWidth="2"
        strokeOpacity="0.7"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Series A (warm, front) */}
      <path
        d={buildPath(seriesA)}
        fill="none"
        stroke="#E68F29"
        strokeWidth="2"
        strokeOpacity="0.85"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

interface FeaturedPairPanelProps {
  pair: FeaturedPair;
}

export function FeaturedPairPanel({ pair }: FeaturedPairPanelProps) {
  const seed = pair.pair_id.split("").reduce((s, c) => s + c.charCodeAt(0), 0);
  const seriesA = buildSparkPoints(seed * 0.01, 0);
  const seriesB = buildSparkPoints(seed * 0.017, 0.1);

  return (
    <div
      data-tour="patterns-featured-pair"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginTop: "24px",
      }}
    >
      {/* Header */}
      <div
        style={{
          fontSize: "9px",
          letterSpacing: "1.6px",
          color: "var(--qgi-accent)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "4px",
          fontWeight: 600,
        }}
      >
        FEATURED PAIR OF THE RELEASE
      </div>

      {/* Pair identity */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          flexWrap: "wrap",
          marginBottom: "16px",
        }}
      >
        <FlagImg
          emoji={pairFlagFor(pair.country_a_name)}
          name={pair.country_a_name}
          width={22}
        />
        <span style={{ fontSize: "20px", fontWeight: 700, color: "var(--qgi-text)" }}>
          {pair.country_a_name}
        </span>
        <span
          style={{
            fontSize: "18px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          ↔
        </span>
        <FlagImg
          emoji={pairFlagFor(pair.country_b_name)}
          name={pair.country_b_name}
          width={22}
        />
        <span style={{ fontSize: "20px", fontWeight: 700, color: "var(--qgi-text)" }}>
          {pair.country_b_name}
        </span>
        <span
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-muted)",
            fontFamily: "ui-monospace, monospace",
            marginLeft: "4px",
          }}
        >
          {pair.start_year}
          {"–"}
          {pair.end_year} · {pair.window_years} years · strength {pair.pair_strength}
        </span>
      </div>

      {/* Overlaid sparkline + legend */}
      <div
        style={{
          background: "var(--qgi-bg)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "6px",
          padding: "14px 16px",
          marginBottom: "16px",
        }}
      >
        <div
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            marginBottom: "10px",
            letterSpacing: "0.4px",
          }}
        >
          INDICATOR-COMPOSITE MOVEMENT -- {pair.start_year} to {pair.end_year}
        </div>

        <SparklineSvg seriesA={seriesA} seriesB={seriesB} width={480} height={64} />

        <div
          style={{
            display: "flex",
            gap: "16px",
            marginTop: "10px",
          }}
        >
          <LegendItem color="#E68F29" label={pair.country_a_name} />
          <LegendItem color="#5B7E99" label={pair.country_b_name} />
        </div>

        <div
          style={{
            marginTop: "8px",
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            fontStyle: "italic",
          }}
        >
          Illustrative composite trajectory. Positive values indicate movement toward
          higher instability composite; negative toward lower. Both series indexed to the
          same baseline for comparison.
        </div>
      </div>

      {/* Editorial paragraph -- HISTORICAL-VOICE ONLY (constraint enforced at data layer) */}
      <p
        style={{
          fontSize: "13.5px",
          color: "var(--qgi-text-muted)",
          lineHeight: 1.65,
          margin: "0 0 18px",
          maxWidth: "700px",
        }}
      >
        {pair.featured_editorial}
      </p>

      {/* CTA */}
      <Link
        href={`/patterns/${pairSlug(pair.pair_id)}` as Route}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          padding: "9px 16px",
          background: "var(--qgi-accent)",
          color: "#000",
          borderRadius: "6px",
          fontSize: "13px",
          fontWeight: 600,
          textDecoration: "none",
          fontFamily: "inherit",
          transition: "opacity 0.12s",
        }}
      >
        Open the pair
        <span style={{ fontFamily: "ui-monospace, monospace" }}>→</span>
      </Link>
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
      <div
        style={{
          width: "20px",
          height: "2px",
          background: color,
          borderRadius: "1px",
          flexShrink: 0,
        }}
      />
      <span style={{ fontSize: "11px", color: "var(--qgi-text-muted)" }}>{label}</span>
    </div>
  );
}
