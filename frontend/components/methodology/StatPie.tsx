"use client";

/**
 * StatPie — a small interactive SVG donut + legend for the methodology stat
 * breakdowns (indicators per provider / per theme, events per master group /
 * per source). Hover a slice or a legend row to light it and dim the rest.
 * Stroke-dasharray donut technique, no chart dependency.
 */
import { useState } from "react";
import type { PieSlice } from "./pie-data";

const R = 54;
const STROKE = 18;
const STROKE_HOVER = 22;
const C = 2 * Math.PI * R;
const SIZE = 150;

export default function StatPie({
  title,
  slices,
  maxLegend = 14,
}: {
  title: string;
  slices: PieSlice[];
  maxLegend?: number;
}) {
  const [active, setActive] = useState<number | null>(null);

  const total = slices.reduce((n, s) => n + s.value, 0) || 1;
  const sorted = [...slices].sort((a, b) => b.value - a.value);
  let shown = sorted;
  if (sorted.length > maxLegend) {
    const head = sorted.slice(0, maxLegend - 1);
    const restVal = sorted.slice(maxLegend - 1).reduce((n, s) => n + s.value, 0);
    shown = [...head, { label: "Other", value: restVal, color: "#5a6270" }];
  }

  const arcs = shown.map((s, i) => {
    const dash = (s.value / total) * C;
    // Cumulative offset of all prior slices (no render-phase mutation).
    const offset = shown.slice(0, i).reduce((n, x) => n + (x.value / total) * C, 0);
    return { s, i, dash, offset };
  });

  return (
    <div
      className="rounded-lg border p-5"
      style={{ borderColor: "var(--qgi-border)", backgroundColor: "var(--qgi-surface)" }}
    >
      <h3
        className="text-[11px] tracking-[0.2em] uppercase mb-4"
        style={{ color: "var(--qgi-text-muted)" }}
      >
        {title}
      </h3>
      <div className="flex items-center gap-5 flex-wrap">
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="shrink-0"
        >
          <g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
            {arcs.map(({ s, i, dash, offset: off }) => {
              const dim = active !== null && active !== i;
              return (
                <circle
                  key={i}
                  cx={SIZE / 2}
                  cy={SIZE / 2}
                  r={R}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={active === i ? STROKE_HOVER : STROKE}
                  strokeDasharray={`${dash} ${C - dash}`}
                  strokeDashoffset={-off}
                  opacity={dim ? 0.25 : 1}
                  style={{
                    transition: "opacity 120ms ease, stroke-width 120ms ease",
                    cursor: "pointer",
                  }}
                  onMouseEnter={() => setActive(i)}
                  onMouseLeave={() => setActive(null)}
                />
              );
            })}
          </g>
          <text
            x={SIZE / 2}
            y={SIZE / 2 - 4}
            textAnchor="middle"
            fontSize="22"
            fontWeight="700"
            fill="var(--qgi-text)"
            fontFamily="ui-monospace, monospace"
          >
            {active !== null
              ? shown[active].value.toLocaleString()
              : total.toLocaleString()}
          </text>
          <text
            x={SIZE / 2}
            y={SIZE / 2 + 13}
            textAnchor="middle"
            fontSize="8.5"
            fill="var(--qgi-text-dim)"
            letterSpacing="1"
          >
            {active !== null
              ? `${Math.round((shown[active].value / total) * 100)}% · ${shown[active].label.toUpperCase()}`.slice(
                  0,
                  22
                )
              : "TOTAL"}
          </text>
        </svg>
        <ul
          className="flex-1 min-w-[160px] space-y-1.5"
          style={{ listStyle: "none", margin: 0, padding: 0 }}
        >
          {shown.map((s, i) => {
            const dim = active !== null && active !== i;
            return (
              <li
                key={i}
                className="flex items-center gap-2 text-[12px]"
                style={{
                  opacity: dim ? 0.4 : 1,
                  transition: "opacity 120ms ease",
                  cursor: "pointer",
                }}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
              >
                <span
                  style={{
                    width: 9,
                    height: 9,
                    borderRadius: 2,
                    backgroundColor: s.color,
                    flexShrink: 0,
                  }}
                />
                <span
                  className="flex-1 truncate"
                  style={{
                    color: active === i ? "var(--qgi-accent)" : "var(--qgi-text)",
                  }}
                >
                  {s.label}
                </span>
                <span
                  className="tabular-nums"
                  style={{
                    color: "var(--qgi-text-muted)",
                    fontFamily: "ui-monospace, monospace",
                  }}
                >
                  {s.value.toLocaleString()}
                </span>
                <span
                  className="tabular-nums text-[10px] w-9 text-right"
                  style={{
                    color: "var(--qgi-text-dim)",
                    fontFamily: "ui-monospace, monospace",
                  }}
                >
                  {Math.round((s.value / total) * 100)}%
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
