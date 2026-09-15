/**
 * PatternAlignmentPanel — V4.1 §Pattern-level alignment (capability #3,
 * canonical movement shape). R&D Q3 ratified: N mini sparklines (N = recipe's
 * indicator count, 3-5) showing the canonical shape across the recipe's
 * window. Mean trajectory in bold + 25/75 percentile band in faint family
 * color (R&D: more honest than rendering individual country paths).
 *
 * — Daniyar Bekmurat, Comparative Historical Pattern Matching
 */
import Link from "next/link";
import type { Route } from "next";
import { getIndicatorLabel, stripProviderSuffix } from "@/lib/indicator-labels";

export interface AlignmentIndicator {
  code: string;
  name: string;
  provider: string;
}

export interface AlignmentShape {
  indicatorCode: string;
  mean: number[];
  p25: number[];
  p75: number[];
}

export interface PatternAlignmentPanelProps {
  familyColor: string;
  recipeId: string;
  windowYears: number;
  indicators: AlignmentIndicator[];
  shapeData: AlignmentShape[];
  /** When true, render the button to the full trajectory deep-dive (only
   *  recipes that ship a curated trajectory have a deep-dive page). */
  hasTrajectory?: boolean;
}

export function PatternAlignmentPanel({
  familyColor,
  recipeId,
  windowYears,
  indicators,
  shapeData,
  hasTrajectory = false,
}: PatternAlignmentPanelProps) {
  const shapeByCode = new Map(shapeData.map((s) => [s.indicatorCode, s]));

  return (
    <section
      data-tour="pattern-alignment-panel"
      style={{
        background: "var(--qgi-surface)",
        borderLeft: `3px solid ${familyColor}`,
        border: "1px solid var(--qgi-border)",
        borderRadius: "6px",
        padding: "16px 18px 18px",
        minWidth: "340px",
      }}
      aria-label="Trajectory alignment: canonical movement shape"
    >
      {/* 2026-05-29 (Naila #29): "Open the full trajectory" button moved
          from header to footer per founder direction. Header is now title
          + subtitle only, in a single clean line. */}
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "10px",
          marginBottom: "4px",
        }}
      >
        <h2
          style={{
            fontSize: "15px",
            fontWeight: 600,
            color: familyColor,
            letterSpacing: "0.1px",
            margin: 0,
          }}
        >
          Trajectory Alignment
        </h2>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            letterSpacing: "0.3px",
          }}
        >
          {indicators.length} signals · {windowYears}y window
        </span>
      </header>

      {/* 2026-05-29 (Naila #29): subtitle rewritten for plain-English
          comprehension. The old line ("what this recipe's trajectory
          LOOKS like") was already decent but front-loaded the methodology
          term. New line opens with the audience-facing question. */}
      <p
        style={{
          fontSize: "12px",
          color: "var(--qgi-text-muted)",
          margin: "2px 0 16px",
          lineHeight: 1.5,
          maxWidth: "65ch",
        }}
      >
        For a country to score high on this trend, its signals need to MOVE in this shape
        across the window. The <strong>bold line</strong> is the average path across every
        verified precedent; the shaded band is the range the middle 50% of precedents
        followed.
      </p>

      <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
        {indicators.map((ind) => {
          const shape = shapeByCode.get(ind.code);
          return (
            <IndicatorShape
              key={ind.code}
              indicator={ind}
              shape={shape}
              familyColor={familyColor}
              windowYears={windowYears}
            />
          );
        })}
      </div>

      {/* 2026-05-29 (Naila #29): legend + axis-hint row, with the
          "Open the full trajectory" button right-aligned at the bottom.
          Cleaner reading order: chart → legend → "go deeper". */}
      <footer
        style={{
          marginTop: "14px",
          paddingTop: "10px",
          borderTop: "1px dashed var(--qgi-border)",
          fontFamily: "ui-monospace, monospace",
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          letterSpacing: "0.3px",
          display: "flex",
          alignItems: "center",
          gap: "14px",
          flexWrap: "wrap",
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              width: "16px",
              height: "2px",
              background: familyColor,
              display: "inline-block",
            }}
          />
          mean trajectory
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              width: "16px",
              height: "8px",
              background: familyColor,
              opacity: 0.18,
              display: "inline-block",
              border: `1px solid ${familyColor}55`,
            }}
          />
          25th–75th percentile
        </span>
        <span>year-0 = event year</span>
        {hasTrajectory && (
          <Link
            href={`/trends/${recipeId}/trajectory` as Route}
            style={{
              marginLeft: "auto",
              fontFamily: "ui-monospace, monospace",
              fontSize: "10px",
              color: familyColor,
              textDecoration: "none",
              border: `1px solid ${familyColor}`,
              background: `${familyColor}14`,
              padding: "4px 10px",
              borderRadius: "4px",
              letterSpacing: "0.4px",
              whiteSpace: "nowrap",
            }}
          >
            Open the full trajectory →
          </Link>
        )}
      </footer>
    </section>
  );
}

function IndicatorShape({
  indicator,
  shape,
  familyColor,
  windowYears,
}: {
  indicator: AlignmentIndicator;
  shape: AlignmentShape | undefined;
  familyColor: string;
  windowYears: number;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "140px 1fr",
        gap: "12px",
        alignItems: "center",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontSize: "9px",
            letterSpacing: "0.8px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            marginBottom: "2px",
            textTransform: "uppercase",
          }}
        >
          {indicator.provider}
        </div>
        <div
          style={{
            fontSize: "12px",
            color: "var(--qgi-text)",
            fontWeight: 600,
            lineHeight: 1.3,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={`${indicator.name || getIndicatorLabel(indicator.code)} (${indicator.code})`}
        >
          {stripProviderSuffix(indicator.name || getIndicatorLabel(indicator.code))}
        </div>
        {/* 2026-05-27 (#159): raw indicator code hidden from visible row;
            available on hover via the title attribute. */}
      </div>
      <ShapeSparkline shape={shape} familyColor={familyColor} windowYears={windowYears} />
    </div>
  );
}

function ShapeSparkline({
  shape,
  familyColor,
  windowYears,
}: {
  shape: AlignmentShape | undefined;
  familyColor: string;
  windowYears: number;
}) {
  if (!shape || shape.mean.length === 0) {
    return (
      <div
        style={{
          height: "52px",
          border: "1px dashed var(--qgi-border)",
          borderRadius: "4px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "ui-monospace, monospace",
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          fontStyle: "italic",
        }}
      >
        shape not yet computed
      </div>
    );
  }

  const W = 360;
  const H = 56;
  const padT = 6;
  const padB = 14;
  const padL = 4;
  const padR = 4;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const N = shape.mean.length;
  const all = [...shape.mean, ...shape.p25, ...shape.p75];
  const rawMax = Math.max(...all);
  const rawMin = Math.min(...all);
  const absMax = Math.max(Math.abs(rawMax), Math.abs(rawMin), 1.0);
  const maxY = absMax + 0.2;
  const minY = -absMax - 0.2;

  const xFor = (i: number) => padL + (i / Math.max(1, N - 1)) * innerW;
  const yFor = (v: number) => padT + innerH - ((v - minY) / (maxY - minY)) * innerH;

  const bandTop = shape.p75
    .map((v, i) => `${xFor(i).toFixed(1)},${yFor(v).toFixed(1)}`)
    .join(" ");
  const bandBottom = shape.p25
    .map((v, i) => `${xFor(i).toFixed(1)},${yFor(v).toFixed(1)}`)
    .reverse()
    .join(" ");
  const bandPolyPoints = `${bandTop} ${bandBottom}`;

  const meanPath = shape.mean
    .map((v, i) => `${i === 0 ? "M" : "L"} ${xFor(i).toFixed(1)} ${yFor(v).toFixed(1)}`)
    .join(" ");

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Canonical movement shape sparkline"
      style={{ display: "block" }}
    >
      <line
        x1={padL}
        x2={padL + innerW}
        y1={yFor(0)}
        y2={yFor(0)}
        stroke="var(--qgi-border)"
        strokeDasharray="2 3"
        strokeWidth={0.5}
      />
      <polygon points={bandPolyPoints} fill={familyColor} opacity={0.16} />
      <polyline
        points={shape.p75
          .map((v, i) => `${xFor(i).toFixed(1)},${yFor(v).toFixed(1)}`)
          .join(" ")}
        fill="none"
        stroke={familyColor}
        opacity={0.35}
        strokeWidth={0.8}
      />
      <polyline
        points={shape.p25
          .map((v, i) => `${xFor(i).toFixed(1)},${yFor(v).toFixed(1)}`)
          .join(" ")}
        fill="none"
        stroke={familyColor}
        opacity={0.35}
        strokeWidth={0.8}
      />
      <path
        d={meanPath}
        fill="none"
        stroke={familyColor}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <line
        x1={padL + innerW}
        x2={padL + innerW}
        y1={padT}
        y2={padT + innerH}
        stroke="var(--qgi-text-dim)"
        strokeDasharray="1 2"
        strokeWidth={0.6}
      />
      <text
        x={padL}
        y={H - 3}
        fontSize="8"
        fill="var(--qgi-text-dim)"
        fontFamily="ui-monospace, monospace"
      >
        {windowYears} yrs before event
      </text>
      <text
        x={padL + innerW}
        y={H - 3}
        fontSize="8"
        fill="var(--qgi-text-dim)"
        fontFamily="ui-monospace, monospace"
        textAnchor="end"
      >
        event year
      </text>
    </svg>
  );
}
