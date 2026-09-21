"use client";
/**
 * QuadrantChart — ECharts scatter plot: struct vs pulse, one dot per board cell.
 * Color-coded by verdict (ACTIVE/SIGNAL/LATENT/QUIET).
 * Reference lines at x=60, y=60 define four quadrants.
 *
 * Dynamic import (ssr:false) from QuadrantSection to avoid SSR issues.
 */
import ReactECharts from "echarts-for-react";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens } from "@/lib/echarts-theme";

interface ScatterPoint {
  struct: number;
  pulse: number;
  countryName: string;
  topicLabel: string;
  verdict: "ACTIVE" | "SIGNAL" | "LATENT" | "QUIET";
}

interface Props {
  points: ScatterPoint[];
}

const VERDICT_COLORS = {
  ACTIVE: "#E05C5C",
  SIGNAL: "#f59e0b",
  LATENT: "#5B7E99",
  QUIET: "#243347",
};

export function QuadrantChart({ points }: Props) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);

  // Group by verdict
  const byVerdict: Record<string, ScatterPoint[]> = {
    ACTIVE: [],
    SIGNAL: [],
    LATENT: [],
    QUIET: [],
  };
  for (const p of points) {
    byVerdict[p.verdict].push(p);
  }

  const series = (["ACTIVE", "SIGNAL", "LATENT", "QUIET"] as const).map((v) => ({
    name: v,
    type: "scatter" as const,
    data: byVerdict[v].map((p) => [p.struct, p.pulse, p.countryName, p.topicLabel]),
    symbolSize: v === "QUIET" ? 5 : 8,
    itemStyle: {
      color: VERDICT_COLORS[v],
      opacity: v === "QUIET" ? 0.3 : 0.8,
    },
  }));

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item" as const,
      backgroundColor: t.surface,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (params: { value: (string | number)[]; seriesName: string }) => {
        const [struct, pulse, country, topic] = params.value;
        const verdictColor =
          VERDICT_COLORS[params.seriesName as keyof typeof VERDICT_COLORS] ?? t.textMuted;
        return [
          `<b style="color:${t.text}">${country}</b> · <span style="color:${t.textMuted}">${topic}</span>`,
          `Struct: <span style="color:${t.amber};font-weight:700">${Math.round(Number(struct))}</span> &nbsp; Pulse: <span style="color:${t.accent}">${Math.round(Number(pulse))}</span>`,
          `<span style="color:${verdictColor};font-weight:700;letter-spacing:1px;font-size:10px">${params.seriesName}</span>`,
        ].join("<br/>");
      },
    },
    legend: {
      top: 4,
      right: 4,
      data: ["ACTIVE", "SIGNAL", "LATENT", "QUIET"],
      textStyle: { color: t.textMuted, fontSize: 10 },
      itemWidth: 10,
      itemHeight: 10,
    },
    grid: { top: 36, right: 80, bottom: 48, left: 52 },
    xAxis: {
      name: "STRUCTURE",
      nameLocation: "middle" as const,
      nameGap: 28,
      nameTextStyle: {
        color: t.textDim,
        fontSize: 10,
        letterSpacing: 2,
      },
      min: 0,
      max: 100,
      axisLine: { lineStyle: { color: t.border } },
      axisLabel: { color: t.textMuted, fontSize: 10 },
      splitLine: { lineStyle: { color: t.splitLine } },
    },
    yAxis: {
      name: "PULSE",
      nameLocation: "middle" as const,
      nameGap: 36,
      nameTextStyle: {
        color: t.textDim,
        fontSize: 11,
        letterSpacing: 2,
      },
      min: 0,
      max: 100,
      axisLine: { lineStyle: { color: t.border } },
      axisLabel: { color: t.textMuted, fontSize: 10 },
      splitLine: { lineStyle: { color: t.splitLine } },
    },
    series: [
      ...series,
      // Reference lines (markLine via scatter dummy series)
      {
        name: "_ref",
        type: "scatter" as const,
        data: [],
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "rgba(91,126,153,0.40)", type: "dashed", width: 1 },
          label: { show: false },
          data: [{ xAxis: 60 }, { yAxis: 60 }],
        },
      },
    ],
    graphic: [
      {
        type: "text",
        left: "62%",
        top: "8%",
        style: {
          text: "ACTIVE / SIGNAL",
          fill: "var(--qgi-accent, #38bdf8)",
          fontSize: 11,
          fontFamily: "ui-monospace, monospace",
          fontWeight: 700,
          letterSpacing: 1,
        },
      },
      {
        // Shifted down 16px to clear the Y-axis "100" tick label
        type: "text",
        left: "5%",
        top: "14%",
        style: {
          text: "NEWS-ONLY",
          fill: t.textDim,
          fontSize: 11,
          fontFamily: "ui-monospace, monospace",
          letterSpacing: 1,
        },
      },
      {
        type: "text",
        left: "62%",
        top: "60%",
        style: {
          text: "LATENT",
          fill: "#f59e0b",
          fontSize: 11,
          fontFamily: "ui-monospace, monospace",
          fontWeight: 700,
          letterSpacing: 1,
        },
      },
      {
        type: "text",
        left: "5%",
        top: "60%",
        style: {
          text: "QUIET",
          fill: t.textDim,
          fontSize: 11,
          fontFamily: "ui-monospace, monospace",
          letterSpacing: 1,
        },
      },
    ],
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: "340px", width: "100%" }}
      opts={{ renderer: "svg" }}
    />
  );
}
