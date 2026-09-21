/**
 * AdminSignalsCharts — client component for the /admin/signals page.
 * Renders a horizontal bar chart of GPR tier counts (A / B / C).
 * Props are plain serialisable values, passed from the server page.
 */
"use client";

import ReactECharts from "echarts-for-react";
import { getEchartsTokens } from "@/lib/echarts-theme";

interface Props {
  tierA: number;
  tierB: number;
  tierC: number;
}

export function AdminSignalsCharts({ tierA, tierB, tierC }: Props) {
  const t = getEchartsTokens(true); // admin is always dark

  const option = {
    backgroundColor: "transparent",
    grid: { left: 56, right: 24, top: 12, bottom: 28 },
    xAxis: {
      type: "value",
      name: "countries",
      nameLocation: "end",
      nameTextStyle: { color: t.textDim, fontSize: 10 },
      axisLine: { lineStyle: { color: t.border } },
      axisTick: { show: false },
      axisLabel: { color: t.textMuted, fontSize: 10 },
      splitLine: { lineStyle: { color: t.splitLine } },
    },
    yAxis: {
      type: "category",
      data: ["C — Low signal", "B — Moderate", "A — Strong"],
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: t.textMuted, fontSize: 11 },
    },
    series: [
      {
        type: "bar",
        data: [
          { value: tierC, itemStyle: { color: t.textDim } },
          { value: tierB, itemStyle: { color: t.warning } },
          { value: tierA, itemStyle: { color: t.success } },
        ],
        barMaxWidth: 28,
        label: {
          show: true,
          position: "right",
          color: t.textMuted,
          fontSize: 11,
          fontFamily: "var(--font-geist-mono, ui-monospace, monospace)",
        },
      },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 12 },
    },
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: "140px", width: "100%" }}
      opts={{ renderer: "svg" }}
    />
  );
}
