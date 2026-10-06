"use client";

/**
 * AnalogClusterPanel — the analogue map (HF merge step 3; the founder-approved
 * "Analogues Cluster" plot, drawn from the page's own real match data).
 *
 * The subject country sits at the center; its nearest historical analogues
 * orbit it, closer means a stronger match. The two rings are the page's own
 * thresholds: strong (85) and moderate (70). Hover for the match and what
 * happened next; click to open the full comparison.
 *
 * Conventions: PanelShell (archival gold, same as the analogue cards),
 * appendToBody tooltip, ECharts behind next/dynamic, theme tokens.
 */

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens } from "@/lib/echarts-theme";
import { analogueHref } from "@/lib/te-mock/analogue-href";
import type { CurrentCountryEntry } from "@/lib/te-mock/nearest-analog-data";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const ARCHIVAL_GOLD = "#C9A66B";

export function AnalogClusterPanel({ entry }: { entry: CurrentCountryEntry }) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);
  const router = useRouter();

  const analogs = entry.analogs ?? [];
  if (analogs.length === 0) return null;

  // Spread the analogues evenly, starting from the top.
  const angles = analogs.map((_, i) => 90 + (360 / analogs.length) * i);

  // RELATIVE spread (review P0): top matches in the corpus saturate near
  // 100, so an absolute 100-minus-match radius piles every flag on the
  // center. Distance is relative WITHIN this country's matches: strongest
  // nearest the center, weakest on the outer guide. Exact ties fall back
  // to rank order so flags never overlap.
  const dists = analogs.map((a) => 100 - a.match_score);
  const maxDist = Math.max(...dists);
  const radii =
    maxDist < 0.05
      ? analogs.map((_, i) => 14 + i * 10)
      : analogs.map((a) => 10 + ((100 - a.match_score) / maxDist) * 20);

  const analogPoints = analogs.map((a, i) => {
    const iso2 = (a.country_iso2 ?? "").toLowerCase();
    return {
      name: `${a.country} ${a.year}`,
      value: [radii[i], angles[i]],
      match: Math.round(a.match_score),
      next: a.what_happened_next,
      href: analogueHref(entry.iso2, a.country_iso2, a.year),
      symbol:
        iso2 && /^[a-z]{2}$/.test(iso2)
          ? `image://https://flagcdn.com/28x21/${iso2}.png`
          : "circle",
      symbolSize: [24, 18] as [number, number],
      label: {
        show: true,
        position: "bottom" as const,
        color: t.textMuted,
        fontSize: 10.5,
        formatter: `${a.country} ${a.year} · ${Math.round(a.match_score)}%`,
      },
    };
  });

  const option = {
    backgroundColor: "transparent",
    polar: { radius: ["0%", "78%"] },
    angleAxis: { type: "value", min: 0, max: 360, show: false },
    radiusAxis: {
      type: "value",
      min: 0,
      max: 36,
      interval: 12,
      axisLine: { show: false },
      axisTick: { show: false },
      // Unlabeled orbit guides only: distance is RELATIVE within this
      // country's matches (each flag's label carries the absolute match),
      // so absolute-threshold rings would mislead (review finding).
      splitLine: { lineStyle: { color: t.border, type: "dashed", opacity: 0.6 } },
      axisLabel: { show: false },
    },
    tooltip: {
      // Body-level so the popup is never cut at the panel border.
      appendToBody: true,
      confine: true,
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (p: {
        data: { name: string; match?: number; next?: string; href?: string | null };
      }) => {
        if (typeof p.data.match !== "number") return `<b>${p.data.name}</b> · today`;
        // Pipeline placeholders ("In training set.") are not user copy.
        const rawNext =
          p.data.next && !/^In training set\.?$/i.test(p.data.next.trim())
            ? p.data.next
            : "";
        const next = rawNext.slice(0, 130);
        return (
          `<b>${p.data.name}</b> · ${p.data.match}% match` +
          (next
            ? `<br/><span style="color:${t.textMuted}">${next}${rawNext.length > 130 ? "…" : ""}</span>`
            : "") +
          (p.data.href
            ? `<br/><span style="color:${t.accent}">Open the comparison →</span>`
            : "")
        );
      },
    },
    series: [
      {
        type: "scatter",
        coordinateSystem: "polar",
        cursor: "pointer",
        data: analogPoints,
      },
      {
        type: "scatter",
        coordinateSystem: "polar",
        silent: false,
        data: [
          {
            name: entry.name,
            value: [0, 0],
            symbol:
              entry.iso2 && /^[a-z]{2}$/.test(entry.iso2)
                ? `image://https://flagcdn.com/36x27/${entry.iso2.toLowerCase()}.png`
                : "circle",
            symbolSize: [30, 23] as [number, number],
            label: {
              show: true,
              // Above the flag: bottom collided with right-side analogue
              // labels in the all-tied case.
              position: "top" as const,
              color: t.text,
              fontSize: 12,
              fontWeight: 600 as const,
              formatter: `${entry.name} today`,
            },
          },
        ],
      },
    ],
  };

  return (
    <PanelShell
      title="The analogue map"
      accent={ARCHIVAL_GOLD}
      tooltip="The subject country sits at the center; each orbiting flag is a historical case whose pre-event trajectory most resembles the subject's recent path. Distance is relative within these matches: the strongest sits nearest the center, and each flag's label carries the absolute match. Matches are similarity, not forecasts."
      caption={
        <>
          {entry.name}&apos;s nearest historical analogues at a glance; the strongest
          match orbits closest. Hover a flag for what happened next; select it to open the
          full comparison.
        </>
      }
      fullWidth
    >
      <ReactECharts
        option={option}
        onEvents={{
          click: (p: { data?: { href?: string | null } }) => {
            if (p.data?.href) router.push(p.data.href as Route);
          },
        }}
        style={{ height: "380px", width: "100%" }}
      />
    </PanelShell>
  );
}
