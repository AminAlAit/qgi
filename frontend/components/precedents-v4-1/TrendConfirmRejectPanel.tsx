"use client";

/**
 * TrendConfirmRejectPanel — the structure-vs-news quadrant for ONE country on
 * ONE trend (HF merge step 3, the trend-country drilldown's verdict view).
 *
 * The subject country is highlighted at (trend score x theme pulse) with
 * every other covered country ghosted for context; the dashed 60/60 lines
 * and corner captions make the verdict self-evident. Clicking a ghost dot
 * moves to that country's drilldown for the same trend.
 *
 * Conventions: appendToBody tooltips, ECharts behind next/dynamic, theme
 * tokens, derived axis floor, labeled thresholds, sentence-case verdicts.
 */

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens, type EchartsTokens } from "@/lib/echarts-theme";
import { iso2For } from "@/lib/te-mock/country-flags";
import type { HfVerdict } from "@/lib/hf/topics-data";
import type { TrendNewsSignal } from "@/lib/hf/trend-signal";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const VERDICT_LABEL: Record<HfVerdict, string> = {
  ACTIVE: "Both Firing",
  SIGNAL: "News-Only",
  LATENT: "Elevated & Quiet",
  QUIET: "Quiet",
};

function verdictVar(v: HfVerdict): string {
  return v === "ACTIVE"
    ? "var(--qgi-warning)"
    : v === "SIGNAL"
      ? "var(--qgi-accent)"
      : v === "LATENT"
        ? "var(--qgi-text-muted)"
        : "var(--qgi-text-dim)";
}

function verdictTok(v: HfVerdict, t: EchartsTokens): string {
  return v === "ACTIVE"
    ? t.warning
    : v === "SIGNAL"
      ? t.accent
      : v === "LATENT"
        ? t.textMuted
        : t.textDim;
}

function cornerCaption(
  text: string,
  fill: string,
  x: "left" | "right",
  y: "top" | "bottom"
) {
  return {
    type: "text" as const,
    [x]: x === "left" ? "13%" : "9%",
    [y]: y === "top" ? "9%" : "16%",
    style: {
      // The canonical labels run longer than the old Active/Signal/Latent
      // wording ("Elevated & Quiet"), so this corner text wraps to two lines
      // (a literal \n in the caller) at a smaller size instead of overrunning
      // the plot.
      text,
      fill,
      fontSize: 9,
      lineHeight: 11,
      align: x,
      fontFamily: "ui-monospace, monospace",
      opacity: 0.8,
    },
    silent: true,
    z: 1,
  };
}

export function TrendConfirmRejectPanel({
  slug,
  trendLabel,
  countryName,
  signal,
}: {
  slug: string;
  trendLabel: string;
  countryName: string;
  signal: TrendNewsSignal;
}) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);
  const router = useRouter();
  const { topic, rows, thresholds: th, perTrend } = signal;

  const subject = rows.find((r) => r.name === countryName);
  if (!subject) return null;

  // Per-Trend pulse is a global cross-country percentile (50 = global median);
  // the legacy crosswalk pulse is a within-country index (50 = own normal).
  const pulseLabel = perTrend ? trendLabel : topic.label;
  // The perTrend surface calls the 0-100 metric "news pressure"; the legacy
  // within-country crosswalk (!perTrend) keeps the older "news pulse" wording.
  // Shared strings below (tooltip, axis, caption) aren't otherwise split on
  // perTrend, so they read off this word instead of a hardcoded literal.
  const pulseWord = perTrend ? "news pressure" : "news pulse";
  const tip = perTrend
    ? `The verdict pairs ${countryName}'s score on this trend with its ${trendLabel.toLowerCase()} news pressure: how much of the country's coverage runs on the trend, ranked across every covered country and month (50 is the global median). Both readings count as elevated from 60 upward; the four corners are the four verdicts.`
    : `The verdict pairs ${countryName}'s score on this specific trend with the ${topic.label} news pulse: how much of the country's news coverage runs on that theme, against its own normal of 50. Both readings count as elevated from 60 upward; the four corners are the four verdicts. The Risk Board reads the broader ${topic.label} composite across all its trends, so the two readings can differ.`;

  const points = rows.map((r) => {
    const isSub = r.name === countryName;
    const iso2 = iso2For(r.name);
    return {
      name: r.name,
      href: r.iso2 ? `/trends/${slug}/countries/${r.iso2}` : null,
      value: [r.struct ?? 0, r.pulse],
      verdict: r.verdict,
      symbol:
        isSub && iso2 && /^[a-z]{2}$/.test(iso2)
          ? `image://https://flagcdn.com/28x21/${iso2}.png`
          : "circle",
      symbolSize: isSub ? ([26, 20] as [number, number]) : 7,
      z: isSub ? 12 : 10,
      itemStyle: isSub
        ? { borderColor: t.text, borderWidth: 0 }
        : { color: verdictTok(r.verdict, t), opacity: 0.55 },
      label: {
        show: isSub,
        position: "bottom" as const,
        color: t.text,
        fontSize: 11.5,
        fontWeight: 600 as const,
        formatter: r.name,
      },
    };
  });

  const structVals = rows.map((r) => r.struct ?? 0);
  const xMin = Math.min(
    30,
    Math.max(0, Math.floor((Math.min(...structVals) - 5) / 10) * 10)
  );

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      // Body-level so it can never be cut at the panel border.
      appendToBody: true,
      confine: true,
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (p: { data: { name: string; value: number[]; verdict: HfVerdict } }) =>
        `<b>${p.data.name}</b><br/>trend score ${Math.round(p.data.value[0])} · ${pulseWord} ${Math.round(
          p.data.value[1]
        )}<br/>${VERDICT_LABEL[p.data.verdict]}`,
    },
    grid: { left: 52, right: 60, top: 24, bottom: 40 },
    xAxis: {
      min: xMin,
      max: 100,
      name: "TREND SCORE",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: t.textDim, fontSize: 10, letterSpacing: 1 },
      axisLine: { lineStyle: { color: t.border } },
      splitLine: { show: false },
      axisLabel: { color: t.textDim, fontSize: 10 },
    },
    yAxis: {
      min: 0,
      max: 100,
      name: pulseWord.toUpperCase(),
      nameLocation: "middle",
      nameGap: 32,
      nameTextStyle: { color: t.textDim, fontSize: 10, letterSpacing: 1 },
      axisLine: { lineStyle: { color: t.border } },
      splitLine: { show: false },
      axisLabel: { color: t.textDim, fontSize: 10 },
    },
    graphic: [
      cornerCaption("Both Firing", t.warning, "right", "top"),
      cornerCaption("News-Only", t.accent, "left", "top"),
      cornerCaption("Elevated &\nQuiet", t.textMuted, "right", "bottom"),
      cornerCaption("Quiet", t.textDim, "left", "bottom"),
    ],
    series: [
      {
        type: "scatter",
        data: points,
        cursor: "pointer",
        labelLayout: { moveOverlap: "shiftY" as const },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: t.textDim, type: "dashed", width: 1.2 },
          // Label only the horizontal line: the same text on the vertical
          // renders rotated and reads as a duplicate (smoke screenshot).
          label: { show: false },
          data: [
            { xAxis: th.struct },
            {
              yAxis: th.pulse,
              label: {
                show: true,
                position: "insideEndTop" as const,
                fontSize: 10,
                fontFamily: "ui-monospace, monospace",
                color: t.textDim,
                formatter: "elevated 60",
              },
            },
          ],
        },
      },
    ],
  };

  return (
    <PanelShell
      title="Structure vs News"
      accent="var(--qgi-accent)"
      tooltip={tip}
      caption={
        <>
          {countryName} reads{" "}
          <strong style={{ color: verdictVar(subject.verdict) }}>
            {VERDICT_LABEL[subject.verdict]}
          </strong>{" "}
          on the {trendLabel.toLowerCase()} trend right now: trend score{" "}
          {Math.round(subject.struct ?? 0)}, {pulseLabel} {pulseWord}{" "}
          {Math.round(subject.pulse)}
          {subject.verdict !== "ACTIVE" &&
          (((subject.struct ?? 0) < th.struct &&
            th.struct - (subject.struct ?? 0) <= 5) ||
            (subject.pulse < th.pulse && th.pulse - subject.pulse <= 5))
            ? ", just below the elevated threshold"
            : ""}
          . The other covered countries are ghosted for context; select a dot to switch.
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
        style={{ height: "340px", width: "100%" }}
      />
    </PanelShell>
  );
}
