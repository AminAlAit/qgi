"use client";

import ReactECharts from "echarts-for-react";
import { sectorColor } from "@/lib/design";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens } from "@/lib/echarts-theme";

interface Props {
  data: { name: string; value: number }[];
  onSectorClick?: (sector: string | null) => void;
  activeSector?: string | null;
}

export function SectorRose({ data, onSectorClick, activeSector }: Props) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);

  const enriched = data.map((d) => ({
    ...d,
    itemStyle: {
      // Inactive sectors recede to a muted grey (themed); active keep their
      // categorical sector hue (data-ink, intentionally not themed).
      color: activeSector && activeSector !== d.name ? t.predicted : sectorColor(d.name),
    },
  }));

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: "{b}: {c} indicators",
    },
    series: [
      {
        type: "pie",
        radius: ["20%", "72%"],
        roseType: "area",
        center: ["50%", "52%"],
        data: enriched,
        label: {
          show: true,
          color: t.textMuted,
          fontSize: 9,
          formatter: "{b}",
        },
        emphasis: {
          label: { color: t.text, fontSize: 10, fontWeight: 600 },
        },
      },
    ],
  };

  const onEvents = {
    click: (params: { name: string }) => {
      if (onSectorClick) {
        onSectorClick(activeSector === params.name ? null : params.name);
      }
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
