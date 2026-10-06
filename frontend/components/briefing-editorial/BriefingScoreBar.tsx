"use client";
/**
 * BriefingScoreBar — single horizontal gauge bar for the analogue match %.
 *
 * "use client" — uses echarts-for-react, loaded via next/dynamic ssr:false.
 *
 * Fills from left with amber gradient.
 * A vertical marker at 90% labels the minimum threshold.
 */
import ReactEcharts from "echarts-for-react";

interface BriefingScoreBarProps {
  matchPct: number;
}

export function BriefingScoreBar({ matchPct }: BriefingScoreBarProps) {
  const option = {
    grid: { top: 8, bottom: 28, left: 8, right: 8 },
    xAxis: {
      type: "value" as const,
      min: 0,
      max: 100,
      axisLabel: { show: false },
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: "category" as const,
      data: ["match"],
      axisLabel: { show: false },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    series: [
      {
        type: "bar",
        data: [matchPct],
        barWidth: 20,
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 1,
            y2: 0,
            colorStops: [
              { offset: 0, color: "#B6924A" },
              { offset: 1, color: "#C9A84C" },
            ],
          },
          borderRadius: [0, 3, 3, 0],
        },
        label: {
          show: true,
          position: "right" as const,
          formatter: `${Math.round(matchPct)}%`,
          color: "#C9A84C",
          fontFamily: "ui-monospace, monospace",
          fontSize: 13,
          fontWeight: 700,
        },
        markLine: {
          silent: true,
          symbol: "none",
          data: [{ xAxis: 90 }],
          lineStyle: { color: "rgba(201,168,76,0.5)", type: "dashed", width: 1 },
          label: {
            formatter: "90% threshold",
            position: "insideEndTop",
            fontSize: 11,
            color: "#C9A84C",
            fontFamily: "ui-monospace, monospace",
            rotate: 0,
          },
        },
      },
    ],
    tooltip: { show: false },
    animation: false,
  };

  return (
    <ReactEcharts
      option={option}
      style={{ height: "60px", width: "100%" }}
      opts={{ renderer: "svg" }}
    />
  );
}
