/**
 * IndicatorDonut — interactive donut of a recipe's signal weights.
 *
 * One family hue at stepped opacity (colour encodes one family, not a
 * rainbow). Hovering a slice OR its legend row lights that signal to full
 * strength and fades the others; the legend names stay fixed on the right.
 *
 * Client component (hover state). Rendered inside the server IndicatorSetPanel.
 */
"use client";

import { useState } from "react";
import { stripProviderSuffix } from "@/lib/indicator-labels";
import type { IndicatorWithWeight } from "@/lib/te-mock/recipe-v4-1-mock";

const SLICE_OPACITY = [1, 0.8, 0.62, 0.48, 0.37, 0.3, 0.26];
const FADED = 0.12;

function sliceOpacity(i: number): number {
  return SLICE_OPACITY[Math.min(i, SLICE_OPACITY.length - 1)];
}

function polar(cx: number, cy: number, r: number, angleDeg: number): [number, number] {
  const a = ((angleDeg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

function donutSlicePath(
  cx: number,
  cy: number,
  R: number,
  r: number,
  startDeg: number,
  endDeg: number
): string {
  const [ox0, oy0] = polar(cx, cy, R, startDeg);
  const [ox1, oy1] = polar(cx, cy, R, endDeg);
  const [ix1, iy1] = polar(cx, cy, r, endDeg);
  const [ix0, iy0] = polar(cx, cy, r, startDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return (
    `M ${ox0.toFixed(2)} ${oy0.toFixed(2)} ` +
    `A ${R} ${R} 0 ${large} 1 ${ox1.toFixed(2)} ${oy1.toFixed(2)} ` +
    `L ${ix1.toFixed(2)} ${iy1.toFixed(2)} ` +
    `A ${r} ${r} 0 ${large} 0 ${ix0.toFixed(2)} ${iy0.toFixed(2)} Z`
  );
}

export function IndicatorDonut({
  familyColor,
  indicators,
}: {
  familyColor: string;
  indicators: IndicatorWithWeight[];
}) {
  const [hovered, setHovered] = useState<string | null>(null);

  const sorted = [...indicators].sort((a, b) => b.shapWeightPct - a.shapWeightPct);
  const cx = 80;
  const cy = 80;
  const R = 70;
  const rInner = 44;

  const slices = sorted.reduce<
    Array<{ ind: IndicatorWithWeight; start: number; end: number; baseOpacity: number }>
  >((arr, ind, i) => {
    const prevEnd = i === 0 ? 0 : arr[i - 1].end;
    const frac = (ind.shapWeightPct ?? 0) / 100;
    arr.push({
      ind,
      start: prevEnd,
      end: prevEnd + frac * 360,
      baseOpacity: sliceOpacity(i),
    });
    return arr;
  }, []);

  const opacityFor = (code: string, base: number): number => {
    if (!hovered) return base;
    return hovered === code ? 1 : FADED;
  };

  return (
    <div style={{ display: "flex", gap: "24px", alignItems: "center", flexWrap: "wrap" }}>
      {/* Donut */}
      <svg
        width="160"
        height="160"
        viewBox="0 0 160 160"
        role="img"
        aria-label="Signal weights, summing to 100%"
        style={{ display: "block", flexShrink: 0 }}
      >
        {slices.length === 1 ? (
          <>
            <circle cx={cx} cy={cy} r={R} fill={familyColor} opacity={1} />
            <circle cx={cx} cy={cy} r={rInner} fill="var(--qgi-surface)" />
          </>
        ) : (
          slices.map((s) => (
            <path
              key={s.ind.code}
              d={donutSlicePath(cx, cy, R, rInner, s.start, s.end)}
              fill={familyColor}
              opacity={opacityFor(s.ind.code, s.baseOpacity)}
              stroke="var(--qgi-surface)"
              strokeWidth={1.5}
              style={{ transition: "opacity 140ms ease", cursor: "default" }}
              onMouseEnter={() => setHovered(s.ind.code)}
              onMouseLeave={() => setHovered(null)}
            />
          ))
        )}
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "26px",
            fontWeight: 700,
            fill: "var(--qgi-text)",
          }}
        >
          {indicators.length}
        </text>
        <text
          x={cx}
          y={cy + 14}
          textAnchor="middle"
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            letterSpacing: "1.5px",
            fill: "var(--qgi-text-dim)",
          }}
        >
          SIGNALS
        </text>
      </svg>

      {/* Legend (names fixed on the right) */}
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "10px",
          flex: 1,
          minWidth: "200px",
        }}
      >
        {slices.map((s) => {
          const dim = hovered !== null && hovered !== s.ind.code;
          return (
            <li
              key={s.ind.code}
              onMouseEnter={() => setHovered(s.ind.code)}
              onMouseLeave={() => setHovered(null)}
              style={{
                display: "grid",
                gridTemplateColumns: "12px minmax(0, 1fr) auto",
                gap: "10px",
                alignItems: "center",
                opacity: dim ? 0.4 : 1,
                transition: "opacity 140ms ease",
                cursor: "default",
              }}
            >
              <span
                aria-hidden
                style={{
                  width: "12px",
                  height: "12px",
                  borderRadius: "3px",
                  background: familyColor,
                  opacity: hovered === s.ind.code ? 1 : s.baseOpacity,
                  flexShrink: 0,
                  transition: "opacity 140ms ease",
                }}
              />
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: "9.5px",
                    letterSpacing: "0.6px",
                    color: "var(--qgi-text-dim)",
                    fontFamily: "ui-monospace, monospace",
                    textTransform: "uppercase",
                    marginBottom: "1px",
                  }}
                >
                  {s.ind.provider}
                </div>
                <div
                  style={{
                    fontSize: "12.5px",
                    color: "var(--qgi-text)",
                    fontWeight: 600,
                    lineHeight: 1.3,
                  }}
                  title={s.ind.code}
                >
                  {stripProviderSuffix(s.ind.name)}
                </div>
              </div>
              <span
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "14px",
                  fontWeight: 700,
                  color: familyColor,
                  letterSpacing: "-0.3px",
                }}
                title="How much this signal counts toward the score for this trend."
              >
                {s.ind.shapWeightPct.toFixed(0)}%
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
