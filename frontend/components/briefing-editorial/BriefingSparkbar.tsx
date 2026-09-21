"use client";
/**
 * BriefingSparkbar — horizontal dual-bar chart: struct vs pulse.
 *
 * "use client" — uses echarts-for-react, loaded via next/dynamic ssr:false
 * at the import site (LeadStory).
 *
 * Props: struct (0-100), pulse (0-100), verdictColor (hex/css-var string).
 */
import ReactEcharts from "echarts-for-react";

interface BriefingSparkbarProps {
  struct: number;
  pulse: number;
  verdictColor: string;
}

export function BriefingSparkbar({ struct, pulse, verdictColor }: BriefingSparkbarProps) {
  const option = {
    grid: { top: 4, bottom: 4, left: 52, right: 8 },
    xAxis: {
      type: "value" as const,
      min: 0,
      max: 100,
      show: false,
    },
    yAxis: {
      type: "category" as const,
      data: ["struct", "pulse"],
      axisLabel: {
        fontSize: 11,
        fontFamily: "ui-monospace, monospace",
        color: "#6b7280",
      },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    series: [
      {
        type: "bar",
        data: [
          { value: struct, itemStyle: { color: "#5B7E99" } },
          { value: pulse, itemStyle: { color: verdictColor } },
        ],
        barWidth: 10,
        barGap: "40%",
        label: { show: false },
      },
    ],
    tooltip: { show: false },
    animation: false,
  };

  return (
    <ReactEcharts
      option={option}
      style={{ height: "80px", width: "100%" }}
      opts={{ renderer: "svg" }}
    />
  );
}
