"use client";

/**
 * AdminTrendDetailShap — horizontal SHAP driver bars for the Trend detail page.
 *
 * Section-prefixed "AdminTrendDetail" so no collision with AdminTrendsCharts.
 * Direction: +1 = risk-increasing (danger/amber), -1 = risk-decreasing (success), 0 = neutral.
 */

import type { CSSProperties } from "react";

export interface ShapDriver {
  code: string;
  weight: number;
  direction: number; // +1 | -1 | 0
  label: string; // resolved indicator name
}

function barColor(direction: number): string {
  if (direction === 1) return "var(--qgi-danger)";
  if (direction === -1) return "var(--qgi-success)";
  return "var(--qgi-text-dim)";
}

function directionLabel(direction: number): string {
  if (direction === 1) return "risk ↑";
  if (direction === -1) return "risk ↓";
  return "neutral";
}

function directionColor(direction: number): string {
  if (direction === 1) return "var(--qgi-danger)";
  if (direction === -1) return "var(--qgi-success)";
  return "var(--qgi-text-dim)";
}

export function AdminTrendDetailShap({ drivers }: { drivers: ShapDriver[] }) {
  if (!drivers.length) {
    return (
      <p style={{ margin: 0, fontSize: "12px", color: "var(--qgi-text-dim)" }}>
        No SHAP data available for this Trend.
      </p>
    );
  }

  // Normalize bar width: largest driver = 100%
  const maxWeight = Math.max(...drivers.map((d) => d.weight), 0.001);

  const rowStyle: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "28px 1fr 56px 60px",
    alignItems: "center",
    gap: "8px",
    padding: "5px 0",
    borderBottom: "1px solid var(--qgi-border)",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {/* Column headers */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "28px 1fr 56px 60px",
          gap: "8px",
          padding: "0 0 6px",
          borderBottom: "2px solid var(--qgi-border)",
        }}
      >
        {["#", "Indicator", "Dir", "Weight"].map((h, i) => (
          <span
            key={h}
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "0.5px",
              textTransform: "uppercase",
              color: "var(--qgi-text-dim)",
              textAlign: i >= 2 ? "right" : "left",
            }}
          >
            {h}
          </span>
        ))}
      </div>

      {drivers.map((d, i) => {
        const barPct = (d.weight / maxWeight) * 100;
        return (
          <div key={`shap-${d.code}-${i}`} style={rowStyle}>
            {/* rank */}
            <span
              className="font-data"
              style={{
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                textAlign: "right",
              }}
            >
              {i + 1}
            </span>

            {/* Indicator name + bar */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "3px",
                minWidth: 0,
              }}
            >
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--qgi-text)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={`${d.label} [${d.code}]`}
              >
                {d.label}
              </span>
              <span
                style={{
                  fontSize: "9px",
                  color: "var(--qgi-text-dim)",
                  fontFamily: "monospace",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {d.code}
              </span>
              {/* bar */}
              <div
                style={{
                  height: "4px",
                  background: "var(--qgi-surface-2)",
                  borderRadius: "2px",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${barPct.toFixed(1)}%`,
                    background: barColor(d.direction),
                    borderRadius: "2px",
                    opacity: 0.85,
                    transition: "width 0.2s ease",
                  }}
                />
              </div>
            </div>

            {/* direction */}
            <span
              style={{
                fontSize: "10px",
                color: directionColor(d.direction),
                fontWeight: 600,
                textAlign: "right",
                whiteSpace: "nowrap",
              }}
            >
              {directionLabel(d.direction)}
            </span>

            {/* weight */}
            <span
              className="font-data"
              style={{
                fontSize: "11px",
                color: "var(--qgi-text-muted)",
                textAlign: "right",
                whiteSpace: "nowrap",
              }}
            >
              {d.weight.toFixed(3)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
