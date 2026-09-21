"use client";

/**
 * AdminTrendsCharts — client island for the /admin/trends page.
 *
 * Receives plain serialisable props (bucket counts) from the server page.
 * Uses echarts-for-react + getEchartsTokens(true) for the dark admin theme.
 *
 * Rule: never import from lib/admin/* or any server-only module here.
 */

import ReactECharts from "echarts-for-react";
import { getEchartsTokens } from "@/lib/echarts-theme";

export interface AucHistogramBuckets {
  /** walked recipes with locoAuc < 0.55 */
  under55: number;
  /** 0.55 <= locoAuc < 0.65 */
  b5565: number;
  /** 0.65 <= locoAuc < 0.75 */
  b6575: number;
  /** locoAuc >= 0.75 */
  over75: number;
}

interface Props {
  buckets: AucHistogramBuckets;
  walkedCount: number;
}

export function AdminTrendsAucHistogram({ buckets, walkedCount }: Props) {
  const t = getEchartsTokens(true);

  const categories = ["< 0.55", "0.55–0.65", "0.65–0.75", "≥ 0.75"];
  const counts = [buckets.under55, buckets.b5565, buckets.b6575, buckets.over75];

  // Per-bucket color: danger / warn / warn-to-good / success
  const barColors = [t.danger, t.warning, t.amber, t.success];

  const option = {
    backgroundColor: "transparent",
    grid: { top: 28, right: 16, bottom: 36, left: 36, containLabel: false },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "none" },
      backgroundColor: t.surface2,
      borderColor: t.border,
      borderWidth: 1,
      textStyle: { color: t.text, fontSize: 12 },
      formatter: (params: Array<{ name: string; value: number }>) => {
        const p = params[0];
        return `<span style="color:${t.textMuted};font-size:11px">cv-AUC ${p.name}</span><br/><b style="font-size:14px">${p.value}</b> <span style="color:${t.textDim};font-size:11px">Trends</span>`;
      },
    },
    xAxis: {
      type: "category",
      data: categories,
      axisLine: { lineStyle: { color: t.border } },
      axisTick: { show: false },
      axisLabel: {
        color: t.textMuted,
        fontSize: 11,
        fontFamily: "inherit",
      },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      splitLine: { lineStyle: { color: t.splitLine } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: t.textDim, fontSize: 10 },
    },
    series: [
      {
        type: "bar",
        data: counts.map((v, i) => ({
          value: v,
          itemStyle: { color: barColors[i], borderRadius: [3, 3, 0, 0] },
        })),
        barMaxWidth: 56,
        label: {
          show: true,
          position: "top",
          color: t.textMuted,
          fontSize: 11,
          fontWeight: 600,
          formatter: (p: { value: number }) => (p.value > 0 ? `${p.value}` : ""),
        },
      },
    ],
  };

  return (
    <div>
      <div
        style={{
          display: "flex",
          gap: "20px",
          alignItems: "baseline",
          marginBottom: "10px",
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: "11px", color: "var(--qgi-text-muted)" }}>
          {walkedCount} walked Trends — cv-AUC distribution
        </span>
        <span style={{ fontSize: "10px", color: "var(--qgi-text-dim)" }}>
          validated ≥ 0.78 &nbsp;·&nbsp; directional 0.70–0.78 &nbsp;·&nbsp; experimental
          &lt; 0.70
        </span>
      </div>
      <ReactECharts
        option={option}
        style={{ height: 180, width: "100%" }}
        opts={{ renderer: "canvas" }}
      />
    </div>
  );
}
