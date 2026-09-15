"use client";

import * as React from "react";
import { iso2For } from "@/lib/te-mock/country-flags";

/**
 * Score distribution panel — V4.1, Naila polish 2026-05-29.
 *
 * Replaces:
 *   - Strip plot (always rendered second, low value): scoring buckets
 *     just to look like a different chart didn't add insight.
 *   - "Alternate view: per-country dots" mystery section header.
 *
 * Adds:
 *   - 1-line caption explaining what the chart shows (founder #26).
 *   - Country lists per histogram bin, derived from `countriesFull` (the
 *     full scored roster) so the hover tooltip never says "country list
 *     not available" — the data exists, the histogram bin just didn't
 *     carry it baked-in (founder #26).
 *   - Replacement secondary view: top-12 countries by score, ranked. A
 *     genuinely useful supplement to the histogram (founder #26 explicit
 *     prompt: "Replace ... with something more useful").
 */
interface HistogramBin {
  bin_lo: number;
  bin_hi: number;
  count: number;
  countries?: string[];
}

interface CountryScore {
  name: string;
  score: number;
}

export function ScoreDistributionPanel({
  familyColor,
  histogram,
  median,
  p90,
  p99,
  max,
  countriesFull,
}: {
  familyColor: string;
  histogram: HistogramBin[];
  median: number;
  p90: number;
  p99: number;
  max: number;
  /** Full scored roster (descending by score). Used to populate per-bin
   *  country lists when the baked histogram bins don't carry them, and
   *  to render the secondary top-N view. */
  countriesFull?: CountryScore[];
}) {
  /** Enrich histogram bins with countries from `countriesFull` if the bin
   *  doesn't already carry them. This is the founder-flagged bug: real-data
   *  histograms ship without per-bin country lists, so the hover tooltip
   *  was silently saying "Country list not available". The country roster
   *  exists; we just bucket it ourselves. */
  const enrichedHistogram = React.useMemo(() => {
    return histogram.map((b) => {
      if (b.countries && b.countries.length > 0) return b;
      const inBin = (countriesFull ?? []).filter(
        (c) => c.score >= b.bin_lo && c.score < b.bin_hi
      );
      // For the topmost bin, include the max-score boundary too.
      const isLast = b.bin_hi >= max;
      const matched = isLast
        ? (countriesFull ?? []).filter((c) => c.score >= b.bin_lo && c.score <= b.bin_hi)
        : inBin;
      return { ...b, countries: matched.map((c) => c.name) };
    });
  }, [histogram, countriesFull, max]);

  const hasData = histogram.length > 0 && histogram.some((b) => b.count > 0);
  if (!hasData) {
    return (
      <section
        data-tour="score-distribution-panel"
        style={{
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderLeft: `3px solid ${familyColor}`,
          borderRadius: "6px",
          padding: "18px 20px 20px",
          minWidth: "340px",
          minHeight: "200px",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}
      >
        <h2 style={{ fontSize: "15px", fontWeight: 600, color: familyColor, margin: 0 }}>
          Score Distribution
        </h2>
        <div
          style={{
            marginTop: "auto",
            padding: "16px 14px",
            border: "1px dashed var(--qgi-border)",
            background: "rgba(255,255,255,0.015)",
            borderRadius: "5px",
            color: "var(--qgi-text-muted)",
            fontSize: "13px",
          }}
        >
          In active rotation. This view fills on the next validation pass.
        </div>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="score-distribution-panel-heading"
      data-tour="score-distribution-panel"
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${familyColor}`,
        borderRadius: "6px",
        padding: "18px 20px 20px",
        minWidth: "340px",
        display: "flex",
        flexDirection: "column",
        gap: "18px",
      }}
    >
      <header>
        <h2
          id="score-distribution-panel-heading"
          style={{
            fontSize: "15px",
            fontWeight: 600,
            color: familyColor,
            margin: 0,
            letterSpacing: "0.1px",
          }}
        >
          Score Distribution
        </h2>
        {/* V4.1 #26: explicit 1-line caption. The chart shows score spread;
            most readers don't intuit a histogram of recipe scores without
            being told what they're looking at. */}
        <p
          style={{
            fontSize: "12px",
            lineHeight: 1.5,
            color: "var(--qgi-text-muted)",
            margin: "6px 0 0",
            maxWidth: "60ch",
          }}
        >
          How the trend&apos;s scores spread across every country we evaluate. The right
          tail (the small set of high-scoring countries) is where the trend flags
          structural resemblance to past precedents. Hover any bar for the countries
          inside that score range.
        </p>
      </header>

      <Histogram
        histogram={enrichedHistogram}
        familyColor={familyColor}
        median={median}
        p90={p90}
        p99={p99}
        max={max}
      />

      {countriesFull && countriesFull.length > 0 && (
        <TopCountriesTable countries={countriesFull} familyColor={familyColor} />
      )}
    </section>
  );
}

function Histogram({
  histogram,
  familyColor,
  median,
  p90,
  p99,
  max,
}: {
  histogram: HistogramBin[];
  familyColor: string;
  median: number;
  p90: number;
  p99: number;
  max: number;
}) {
  const [hoverIdx, setHoverIdx] = React.useState<number | null>(null);
  const W = 560;
  const H = 192;
  const PAD_L = 30;
  const PAD_R = 16;
  const PAD_T = 24;
  const PAD_B = 30;
  const plotW = W - PAD_L - PAD_R;
  const plotH = H - PAD_T - PAD_B;
  const maxCount = Math.max(1, ...histogram.map((b) => b.count));
  const xForScore = (s: number) => PAD_L + (s / 100) * plotW;
  const barWidth = plotW / histogram.length - 1.5;
  const hoveredBin = hoverIdx !== null ? histogram[hoverIdx] : null;

  return (
    <div style={{ width: "100%", position: "relative" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height: "auto", display: "block" }}
        role="img"
        aria-label="Histogram of trend scores"
      >
        {[0.25, 0.5, 0.75, 1].map((t) => {
          const y = PAD_T + plotH - t * plotH;
          return (
            <line
              key={t}
              x1={PAD_L}
              x2={PAD_L + plotW}
              y1={y}
              y2={y}
              stroke="var(--qgi-border)"
              strokeWidth={0.5}
              strokeDasharray="2 3"
            />
          );
        })}
        {histogram.map((b, i) => {
          const x = xForScore(b.bin_lo) + 0.75;
          const h = (b.count / maxCount) * plotH;
          const y = PAD_T + plotH - h;
          const isHover = hoverIdx === i;
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width={barWidth}
              height={Math.max(1, h)}
              fill={familyColor}
              fillOpacity={isHover ? 0.95 : 0.6}
              stroke={familyColor}
              strokeWidth={isHover ? 1 : 0.5}
              onMouseEnter={() => setHoverIdx(i)}
              onMouseLeave={() => setHoverIdx(null)}
              style={{ cursor: "pointer" }}
            />
          );
        })}
        <line
          x1={PAD_L}
          x2={PAD_L + plotW}
          y1={PAD_T + plotH}
          y2={PAD_T + plotH}
          stroke="var(--qgi-border)"
          strokeWidth={1}
        />
        {Array.from({ length: 11 }).map((_, i) => {
          const s = i * 10;
          const x = xForScore(s);
          return (
            <g key={i}>
              <line
                x1={x}
                x2={x}
                y1={PAD_T + plotH}
                y2={PAD_T + plotH + 3}
                stroke="var(--qgi-border)"
                strokeWidth={0.75}
              />
              <text
                x={x}
                y={PAD_T + plotH + 13}
                fontSize={8.5}
                fill="var(--qgi-text-dim)"
                textAnchor="middle"
                fontFamily="ui-monospace, monospace"
              >
                {s}
              </text>
            </g>
          );
        })}
        <Annotation
          x={xForScore(median)}
          top={PAD_T - 6}
          label="median"
          value={median}
          color="var(--qgi-text-muted)"
        />
        <Annotation
          x={xForScore(p90)}
          top={PAD_T - 6}
          label="top 10%"
          value={p90}
          color="var(--qgi-text-muted)"
        />
        <Annotation
          x={xForScore(p99)}
          top={PAD_T - 6}
          label="top 1%"
          value={p99}
          color="var(--qgi-text-muted)"
        />
        <Annotation
          x={xForScore(max)}
          top={PAD_T - 6}
          label="max"
          value={max}
          color={familyColor}
        />
        {[median, p90, p99, max].map((q, i) => (
          <line
            key={i}
            x1={xForScore(q)}
            x2={xForScore(q)}
            y1={PAD_T}
            y2={PAD_T + plotH}
            stroke="var(--qgi-text-dim)"
            strokeDasharray="2 3"
            strokeWidth={0.5}
            opacity={0.6}
          />
        ))}
      </svg>
      {hoveredBin && (
        <div
          style={{
            position: "absolute",
            top: "4px",
            right: "4px",
            background: "var(--qgi-bg)",
            border: `1px solid ${familyColor}`,
            borderRadius: "4px",
            padding: "8px 10px",
            maxWidth: "240px",
            fontFamily: "ui-monospace, monospace",
            fontSize: "10.5px",
            color: "var(--qgi-text)",
            pointerEvents: "none",
            boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
          }}
        >
          <div style={{ color: familyColor, marginBottom: "4px", fontWeight: 600 }}>
            score {hoveredBin.bin_lo}–{hoveredBin.bin_hi} · {hoveredBin.count}{" "}
            {hoveredBin.count === 1 ? "country" : "countries"}
          </div>
          {hoveredBin.countries && hoveredBin.countries.length > 0 ? (
            <div style={{ color: "var(--qgi-text-muted)", lineHeight: 1.5 }}>
              {hoveredBin.countries.slice(0, 12).join(", ")}
              {hoveredBin.countries.length > 12
                ? `, +${hoveredBin.countries.length - 12} more`
                : ""}
            </div>
          ) : (
            <div style={{ color: "var(--qgi-text-dim)", fontStyle: "italic" }}>
              No scored countries in this band.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Annotation({
  x,
  top,
  label,
  value,
  color,
}: {
  x: number;
  top: number;
  label: string;
  value: number;
  color: string;
}) {
  return (
    <g>
      <text
        x={x}
        y={top - 9}
        fontSize={8.5}
        fill={color}
        textAnchor="middle"
        fontFamily="ui-monospace, monospace"
      >
        {label}
      </text>
      <text
        x={x}
        y={top - 1}
        fontSize={8.5}
        fill={color}
        textAnchor="middle"
        fontFamily="ui-monospace, monospace"
      >
        {value.toFixed(0)}
      </text>
      <line x1={x} x2={x} y1={top + 2} y2={top + 5} stroke={color} strokeWidth={0.75} />
    </g>
  );
}

/** Replacement for the strip plot: the top-12 countries by score, ranked.
 *  More useful than a second view of the same dots; surfaces the right-tail
 *  the histogram only summarizes. */
function TopCountriesTable({
  countries,
  familyColor,
}: {
  countries: CountryScore[];
  familyColor: string;
}) {
  const top = [...countries].sort((a, b) => b.score - a.score).slice(0, 12);
  return (
    <div>
      <div
        style={{
          fontSize: "10px",
          letterSpacing: "1.2px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "8px",
        }}
      >
        Right-tail · top 12 countries
      </div>
      <ol
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
          gap: "4px 16px",
        }}
      >
        {top.map((c, i) => {
          const iso = iso2For(c.name);
          return (
            <li
              key={c.name}
              style={{
                display: "grid",
                gridTemplateColumns: "16px 16px minmax(0, 1fr) auto",
                gap: "6px",
                alignItems: "center",
                padding: "4px 0",
                borderBottom: "1px dashed var(--qgi-border)",
              }}
            >
              <span
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "10px",
                  color: "var(--qgi-text-dim)",
                  textAlign: "right",
                }}
              >
                {i + 1}
              </span>
              {iso ? (
                <img
                  src={`https://flagcdn.com/16x12/${iso}.png`}
                  alt={`${c.name} flag`}
                  width={16}
                  height={12}
                  style={{ display: "inline-block", verticalAlign: "middle" }}
                />
              ) : (
                <span
                  style={{ width: 16, height: 12, display: "inline-block" }}
                  aria-hidden
                />
              )}
              <span
                style={{
                  fontSize: "12px",
                  color: "var(--qgi-text)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {c.name}
              </span>
              <span
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "11.5px",
                  color: familyColor,
                  fontWeight: 600,
                }}
              >
                {c.score.toFixed(1)}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
