"use client";

import ReactECharts from "echarts-for-react";
import { useRouter } from "next/navigation";
import type { PatternRow } from "@/lib/types";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens } from "@/lib/echarts-theme";

interface Props {
  patterns: PatternRow[];
}

export function PatternScatter({ patterns }: Props) {
  const router = useRouter();
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);

  const data = patterns.map((p) => [
    p.pattern_length,
    p.num_indexes,
    p.pattern_power_score,
    p.country_a,
    p.country_b,
    p.start_year_a,
    p.start_year_b,
    p.country_a_id ?? p.country_a,
    p.country_b_id ?? p.country_b,
  ]);

  const option = {
    backgroundColor: "transparent",
    title: {
      text: "The Strengths & Lengths of International Relationships",
      textStyle: {
        color: t.textMuted,
        fontSize: 11,
        fontWeight: 400,
        letterSpacing: 2,
      },
      top: 0,
      left: 0,
    },
    tooltip: {
      trigger: "item",
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (params: { value: (string | number)[] }) => {
        const [len, idx, pps, ca, cb, sya, syb] = params.value;
        return [
          `<b style="color:${t.countryA}">${ca}</b> → <b style="color:${t.countryB}">${cb}</b>`,
          `Duration: ${len} yrs &nbsp;|&nbsp; Indexes: ${idx}`,
          `Score: <span style="color:${t.amber}">${Number(pps).toFixed(3)}</span>`,
          `${sya}–${Number(sya) + Number(len) - 1} / ${syb}–${Number(syb) + Number(len) - 1}`,
        ].join("<br/>");
      },
    },
    grid: { top: 36, right: 16, bottom: 48, left: 56 },
    xAxis: {
      name: "PATTERN DURATION (YRS)",
      nameLocation: "middle",
      nameGap: 32,
      nameTextStyle: { color: t.textDim, fontSize: 9, letterSpacing: 1 },
      type: "value",
      axisLine: { lineStyle: { color: t.border } },
      splitLine: { lineStyle: { color: t.splitLine } },
      axisLabel: { color: t.textMuted, fontSize: 10 },
    },
    yAxis: {
      name: "INDICATOR MATCHES",
      nameLocation: "middle",
      nameGap: 40,
      nameTextStyle: { color: t.textDim, fontSize: 9, letterSpacing: 1 },
      type: "value",
      axisLine: { lineStyle: { color: t.border } },
      splitLine: { lineStyle: { color: t.splitLine } },
      axisLabel: { color: t.textMuted, fontSize: 10 },
    },
    series: [
      {
        type: "scatter",
        data,
        symbolSize: (val: number[]) => Math.max(4, Math.min(32, val[2] * 30)),
        itemStyle: {
          color: t.accent + "8c", // ~55% alpha
          borderColor: t.accent,
          borderWidth: 0.5,
        },
        emphasis: {
          itemStyle: {
            color: t.accent,
            borderColor: isDark ? "#fff" : t.text,
            borderWidth: 1.5,
          },
        },
      },
    ],
  };

  const onEvents = {
    click: (params: { value: (string | number)[] }) => {
      const [len, , , , , sya, syb, caId, cbId] = params.value;
      const qs = new URLSearchParams({
        country_a: String(caId),
        country_b: String(cbId),
        length: String(len),
        start_a: String(sya),
        start_b: String(syb),
      });
      router.push(`/patterns?${qs.toString()}`);
    },
  };

  return (
    <ReactECharts
      option={option}
      style={{ height: "100%", width: "100%" }}
      onEvents={onEvents}
    />
  );
}
