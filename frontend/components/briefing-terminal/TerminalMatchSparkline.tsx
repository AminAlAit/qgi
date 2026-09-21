"use client";

/**
 * TerminalMatchSparkline — 60×20px mini echarts line sparkline for match tiles.
 *
 * Loaded via next/dynamic with ssr:false from TerminalMatchTile.
 * No axes, no grid, area-fill at 15% opacity, line color = l1_color.
 */

import ReactECharts from "echarts-for-react";

export interface TerminalMatchSparklineProps {
  values: number[];
  color: string;
}

/** Safe hex→rgba conversion. Handles 3-digit + 6-digit hex. Falls back to the original hex string. */
function hexToRgba(hex: string, alpha: number): string {
  const raw = hex.replace(/^#/, "");
  if (raw.length === 3) {
    const r = parseInt(raw[0]! + raw[0]!, 16);
    const g = parseInt(raw[1]! + raw[1]!, 16);
    const b = parseInt(raw[2]! + raw[2]!, 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  if (raw.length === 6) {
    const r = parseInt(raw.slice(0, 2), 16);
    const g = parseInt(raw.slice(2, 4), 16);
    const b = parseInt(raw.slice(4, 6), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  // CSS var or rgb() passed — fall back to the input string
  return hex;
}

export function TerminalMatchSparkline({ values, color }: TerminalMatchSparklineProps) {
  if (!values || values.length < 2) return null;

  const areaTop = hexToRgba(color, 0.15);

  const option = {
    animation: false,
    grid: { top: 1, right: 1, bottom: 1, left: 1 },
    xAxis: { type: "category" as const, show: false, data: values.map((_, i) => i) },
    yAxis: { type: "value" as const, show: false },
    series: [
      {
        type: "line",
        data: values,
        smooth: true,
        symbol: "none",
        lineStyle: { color, width: 1.5 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: areaTop },
              { offset: 1, color: "rgba(0,0,0,0)" },
            ],
          },
        },
      },
    ],
  };

  return (
    <ReactECharts
      option={option}
      style={{ width: "60px", height: "20px" }}
      opts={{ renderer: "svg" }}
    />
  );
}
