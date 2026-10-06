"use client";

/**
 * GprConfirmationPanel: the per-country geopolitical-risk reading.
 *
 * Shown only for the 44 countries with a published academic benchmark (the
 * caller passes null otherwise, so the panel is simply absent elsewhere).
 * Confidence-first + honest: it shows how QGI-GPR has MOVED for this country
 * and a signal-quality tier; it never claims to reproduce the published index,
 * and no statistical jargon reaches the copy. The line ends at "today" and
 * never points forward, same guardrail as MiniSparkline (client component:
 * the ECharts line needs the theme tokens; entry/tier arrive as serializable
 * props from the server page).
 */
import dynamic from "next/dynamic";
import Link from "next/link";
import type { Route } from "next";
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens, type EchartsTokens } from "@/lib/echarts-theme";
import type { GprCountryEntry, GprTier } from "@/lib/gpr/gpr-country-data";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

// Archival violet, distinct from the structural family palette on this page.
const GPR_ACCENT = "#8B7CF6";

const TIER_TINT: Record<GprTier, string> = {
  A: "#3FBF8F", // Strong signal, calm green
  B: "var(--qgi-accent)", // Confirmed signal, accent
  C: "var(--qgi-text-muted)", // Weak signal, muted
};

// ECharts renders to canvas at build time, it cannot resolve CSS custom
// properties, so the chart line uses the theme-token equivalent of the tier
// tint above (same tier -> color mapping, literal hex per mode).
function tierLineColor(tier: GprTier, t: EchartsTokens): string {
  return tier === "A" ? t.success : tier === "B" ? t.accent : t.textMuted;
}

function yearRange(window: string): string {
  // window is "YYYY-MM to YYYY-MM"
  const years = window.match(/\d{4}/g);
  return years && years.length >= 2
    ? `${years[0]} to ${years[years.length - 1]}`
    : window;
}

const MONTH_ABBREV = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/**
 * Which category indices get an x-axis tick/label, so a ~10-year monthly
 * series reads as a timeline (year boundaries) instead of one label per
 * point. Prefers "MMM -01" (January) boundaries; falls back to evenly
 * spaced sampling for series too short to have two of them.
 */
function xAxisLabelIndices(dates: string[]): Set<number> {
  const yearStarts = dates.reduce<number[]>((acc, d, i) => {
    if (d.endsWith("-01")) acc.push(i);
    return acc;
  }, []);
  if (yearStarts.length >= 2) return new Set(yearStarts);

  const target = 6;
  const step = Math.max(1, Math.round(dates.length / target));
  const idx = new Set<number>();
  for (let i = 0; i < dates.length; i += step) idx.add(i);
  idx.add(dates.length - 1);
  return idx;
}

// "2015-02" -> "2015" at a year boundary, "Mar '15" otherwise (only reached
// by the short-series fallback above, since the common case ticks only land
// on January).
function xAxisLabelText(date: string): string {
  const [y, m] = date.split("-");
  if (m === "01") return y;
  const monthIdx = Number(m) - 1;
  return `${MONTH_ABBREV[monthIdx] ?? m} '${y.slice(2)}`;
}

export function GprConfirmationPanel({ entry }: { entry: GprCountryEntry }) {
  if (!entry) return null;
  const tint = TIER_TINT[entry.tier];

  return (
    <PanelShell
      fullWidth
      title="Geopolitical Risk Signal"
      titleCase
      accent={GPR_ACCENT}
      tooltip="QGI builds its own geopolitical-risk reading for every country from the global news record, and checks it against the published academic benchmark where one exists. The line shows how that reading has moved here; the badge shows how well it checks against the benchmark."
      caption={
        <>
          How {entry.name}&rsquo;s geopolitical risk has moved, {yearRange(entry.window)}.
          QGI-GPR tracks the direction and spikes of risk, not an absolute level.
        </>
      }
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "12px",
          flexWrap: "wrap",
          marginBottom: "8px",
        }}
      >
        <span
          style={{
            fontSize: "11px",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.5px",
            color: tint,
            border: `1px solid ${tint}`,
            background: `color-mix(in srgb, ${tint} 10%, transparent)`,
            borderRadius: "10px",
            padding: "3px 10px",
            whiteSpace: "nowrap",
            flexShrink: 0,
          }}
        >
          {entry.tier_label}
        </span>
        <span
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {entry.n_months} months of QGI-GPR
        </span>
      </div>

      <GprLineChart entry={entry} tier={entry.tier} />

      <div
        style={{
          marginTop: "12px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          flexWrap: "wrap",
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        <span>Validated against the published benchmark, {entry.n_months} months</span>
        <Link
          href={"/methodology/gpr" as Route}
          style={{
            color: GPR_ACCENT,
            textDecoration: "none",
            borderBottom: `1px solid color-mix(in srgb, ${GPR_ACCENT} 50%, transparent)`,
          }}
        >
          How we validate this &rarr;
        </Link>
      </div>
    </PanelShell>
  );
}

/**
 * GprLineChart: a proper ECharts line over the full QGI-GPR monthly series
 * (the tiny inline-SVG MiniSparkline this replaces). A dashed reference line
 * marks the series' own average so a reader can see above/below at a glance
 * (the benchmark has no published threshold to borrow). The line shows a
 * small end dot at the latest month and nowhere else, so it reads as ending
 * "today" rather than pointing forward (Kwame's no-forecast guardrail).
 */
function GprLineChart({ entry, tier }: { entry: GprCountryEntry; tier: GprTier }) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);
  const { dates, values } = entry.series;
  const n = values.length;
  const lo = n ? Math.min(...values) : 0;
  const hi = n ? Math.max(...values) : 1;
  const pad = (hi - lo) * 0.1 || 0.05;
  const mean = n ? values.reduce((a, b) => a + b, 0) / n : 0;
  const color = tierLineColor(tier, t);
  const labelIdx = xAxisLabelIndices(dates);

  const option = {
    backgroundColor: "transparent",
    animation: false,
    tooltip: {
      trigger: "axis",
      // Render on document.body so the popup can never be squeezed or cut at
      // a panel border (founder catch 2026-06-11).
      appendToBody: true,
      confine: true,
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (ps: Array<{ axisValue: string; data: number }>) =>
        `${ps[0]?.axisValue}<br/>QGI-GPR ${ps[0]?.data.toFixed(3)}`,
    },
    grid: { left: 46, right: 16, top: 16, bottom: 26 },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: t.border } },
      // Ticks only at the same sparse points as the labels below, so the
      // axis reads as year markers on a timeline, not a comb of 100+ points.
      axisTick: {
        show: true,
        interval: (index: number) => labelIdx.has(index),
        lineStyle: { color: t.border },
      },
      axisLabel: {
        color: t.textDim,
        fontSize: 10,
        interval: (index: number) => labelIdx.has(index),
        hideOverlap: true,
        formatter: (v: string) => xAxisLabelText(v),
      },
    },
    yAxis: {
      min: lo - pad,
      max: hi + pad,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: t.splitLine, opacity: 0.5 } },
      axisLabel: {
        color: t.textDim,
        fontSize: 10,
        formatter: (v: number) => v.toFixed(2),
      },
    },
    series: [
      {
        type: "line",
        data: values,
        // Symbol only at the last point: the visual "today" cutoff, never a
        // forecast-looking dotted continuation or arrowhead.
        symbol: (_v: number, params: { dataIndex: number }) =>
          params.dataIndex === n - 1 ? "circle" : "none",
        symbolSize: (_v: number, params: { dataIndex: number }) =>
          params.dataIndex === n - 1 ? 6 : 0,
        itemStyle: { color },
        lineStyle: { width: 1.8, color },
        areaStyle: { color: `${color}1c` },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: t.textDim, type: "dashed", width: 1 },
          label: {
            show: true,
            position: "insideEndTop" as const,
            color: t.textDim,
            fontSize: 10,
            formatter: "average",
          },
          data: [{ yAxis: mean }],
        },
      },
    ],
  };

  return <ReactECharts option={option} style={{ height: "220px", width: "100%" }} />;
}
