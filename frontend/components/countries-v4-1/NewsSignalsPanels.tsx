"use client";

/**
 * News-layer panels for the country page (HF merge step 2, 2026-06-10;
 * Trend Drift rebuilt for the Topics->Trends migration, founder 2026-07-04).
 *
 * NewsSignalsPanel: the country's live trends as selectable chips (verdict,
 * news pressure), with the selected trend's full pulse charted against its
 * verified event markers and the structural level.
 *
 * TopicDriftPanel ("Trend Drift"): the country's monthly news pressure per
 * trend, stacked to each month's 100% share of attention, full history,
 * horizontally zoomable (Phase 3 polish, 2026-07-05: the heatmap and
 * full-history line sub-views were dropped, the share-of-attention read
 * carried the panel on its own).
 *
 * Verdict labels are the canonical set (founder 2026-07-05): the HfVerdict
 * enum keys (ACTIVE/SIGNAL/LATENT/QUIET) are internal only, every surface
 * shows Both Firing / News-Only / Elevated & Quiet / Quiet.
 *
 * All ride PanelShell (V4.1 idiom) and the ECharts theme tokens. echarts
 * loads behind next/dynamic so country pages without a visitor opening
 * these panels stay light.
 */

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import type { Route } from "next";
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { InfoTooltip } from "@/components/design/InfoTooltip";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens } from "@/lib/echarts-theme";
import type { HfVerdict } from "@/lib/hf/topics-data";
import type { HfCountryDetail, HfTopicSeries } from "@/lib/hf/pulse-detail";
import { GLOBAL_PERCENTILE_NOTE } from "@/lib/hf/news-scale";
import { LIVE_NEWS_TRENDS } from "@/lib/hf/trend-taxonomy";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

/**
 * Trend Drift categorical palette: one hue per live trend, fixed order (never
 * cycled, color follows the trend's identity, not its rank in a given month),
 * separate dark/light steps. Retuned lower-chroma/muted (founder catch
 * 2026-07-05: the original Tailwind-500/600 set read too bright against the
 * stacked-area fills); same hue family per trend, OKLCH C ~0.11-0.12 instead
 * of ~0.14-0.25. Validated against this panel's own surfaces (#162032 dark,
 * #ffffff light) with the dataviz skill's six-check script: all four checks
 * PASS in both modes at the default adjacent-pair CVD check (worst adjacent
 * deltaE 14.6 dark / 20.3 light, past the >=12 target).
 */
const TREND_COLORS: Record<string, { dark: string; light: string }> = {
  currency_crisis: { dark: "#3590bf", light: "#077bab" },
  mass_protest: { dark: "#489a68", light: "#0b7643" },
  migration_and_refugees: { dark: "#b97340", light: "#964d09" },
  elections_and_voting: { dark: "#b7698f", light: "#94436d" },
  political_corruption: { dark: "#857ac4", light: "#6355a2" },
  labor_action: { dark: "#c06a64", light: "#9c433f" },
};

function trendColor(slug: string, isDark: boolean): string {
  const c = TREND_COLORS[slug];
  if (!c) return isDark ? "#8aa6be" : "#64748b"; // fallback, should not occur
  return isDark ? c.dark : c.light;
}

const TREND_ORDER_INDEX: Record<string, number> = Object.fromEntries(
  LIVE_NEWS_TRENDS.map((slug, i) => [slug, i])
);

/**
 * Trend Drift's 3 sub-views share ONE fixed trend order (LIVE_NEWS_TRENDS),
 * not detail.series' per-country "strongest reading first" sort: every
 * trend keeps the same row/line/stack slot, and the same categorical color,
 * across countries and across the 3 views, which is also the order the
 * palette above was CVD-validated against.
 */
function trendDriftOrder(series: HfTopicSeries[]): HfTopicSeries[] {
  return [...series].sort(
    (a, b) =>
      (TREND_ORDER_INDEX[a.topic.id] ?? 99) - (TREND_ORDER_INDEX[b.topic.id] ?? 99)
  );
}

const VERDICT_LABEL: Record<HfVerdict, string> = {
  ACTIVE: "Both Firing",
  SIGNAL: "News-Only",
  LATENT: "Elevated & Quiet",
  QUIET: "Quiet",
};

function verdictColor(v: HfVerdict): string {
  return v === "ACTIVE"
    ? "var(--qgi-warning)"
    : v === "SIGNAL"
      ? "var(--qgi-accent)"
      : v === "LATENT"
        ? "var(--qgi-text-muted)"
        : "var(--qgi-text-dim)";
}

/* ── News signals: theme chips + pulse-vs-events chart ───────────────── */

export function NewsSignalsPanel({ detail }: { detail: HfCountryDetail }) {
  // Default to the strongest reading: validated topics first, weakest-leg.
  const initial = useMemo(() => {
    let best: HfTopicSeries | null = null;
    const legs = (s: HfTopicSeries) =>
      s.cell ? Math.min(s.cell.struct ?? 0, s.cell.pulse) : -1;
    for (const s of detail.series) {
      if (
        best === null ||
        (s.topic.validated && !best.topic.validated) ||
        (s.topic.validated === best.topic.validated && legs(s) > legs(best))
      ) {
        best = s;
      }
    }
    return best?.topic.id ?? detail.series[0]?.topic.id;
  }, [detail]);
  const [topicId, setTopicId] = useState(initial);
  // Monthly is the overview cadence here; weekly arrives with the live data
  // layer (the monthly series can't be honestly resampled to weeks).
  const [resolution, setResolution] = useState<"1M" | "1W">("1M");

  const sel = detail.series.find((s) => s.topic.id === topicId) ?? detail.series[0];

  return (
    <PanelShell
      title="News Pulse"
      titleCase
      accent="var(--qgi-accent)"
      tooltip="This trend's news pressure: how much of a country's news coverage runs on the trend each month, ranked across every covered country and month (50 is the global median for that trend, 60 and up counts as elevated). The verdict pairs that pressure with the trend's structural resemblance, where available."
      caption={
        <>
          What the news is amplifying for {detail.name} right now. Select a trend to see
          its news pressure against the verified events.
        </>
      }
      fullWidth
    >
      {/* Theme chips */}
      <div
        role="group"
        aria-label="News trends"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "6px",
          marginBottom: "12px",
        }}
      >
        {detail.series.map((s) => {
          const active = s.topic.id === topicId;
          const v = s.cell?.verdict ?? "QUIET";
          return (
            <button
              key={s.topic.id}
              type="button"
              onClick={() => setTopicId(s.topic.id)}
              aria-pressed={active}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-start",
                gap: "3px",
                padding: "8px 12px",
                minWidth: "108px",
                background: active ? "var(--qgi-surface-2)" : "var(--qgi-bg)",
                border: "1px solid var(--qgi-border)",
                borderRadius: "6px",
                cursor: "pointer",
                boxShadow: active ? "inset 0 0 0 1px var(--qgi-accent)" : "none",
              }}
            >
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 600,
                  color: active ? "var(--qgi-text)" : "var(--qgi-text-muted)",
                  whiteSpace: "nowrap",
                }}
              >
                {s.topic.label}
              </span>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "baseline",
                  gap: "6px",
                  fontSize: "10.5px",
                }}
              >
                <span style={{ color: verdictColor(v), fontWeight: 600 }}>
                  {VERDICT_LABEL[v]}
                </span>
                <span
                  className="font-data"
                  style={{ color: "var(--qgi-text-dim)", fontSize: "11px" }}
                >
                  {s.cell ? Math.round(s.cell.pulse) : "–"}
                  <span style={{ opacity: 0.55 }}>/100</span>
                </span>
              </span>
              {s.cell?.struct == null && (
                <span
                  style={{
                    fontSize: "9px",
                    color: "var(--qgi-text-dim)",
                    letterSpacing: "0.4px",
                    textTransform: "uppercase",
                  }}
                >
                  news only
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Resolution + window hint. Monthly is live; weekly unlocks with the
          live data layer. Last twelve months shown by default; drag to scroll
          into earlier years. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginBottom: "8px",
          fontFamily: "ui-monospace, monospace",
          fontSize: "10px",
        }}
      >
        {(["1M", "1W"] as const).map((r) => {
          const active = r === resolution;
          const gated = r === "1W";
          return (
            <button
              key={r}
              type="button"
              disabled={gated}
              onClick={() => !gated && setResolution(r)}
              aria-pressed={gated ? undefined : active}
              aria-disabled={gated || undefined}
              title={gated ? "Weekly view arrives with the live data layer" : undefined}
              style={{
                padding: "3px 9px",
                borderRadius: "4px",
                border: "1px solid var(--qgi-border)",
                background: active ? "var(--qgi-surface-2)" : "transparent",
                color: gated
                  ? "var(--qgi-text-dim)"
                  : active
                    ? "var(--qgi-text)"
                    : "var(--qgi-text-muted)",
                boxShadow: active ? "inset 0 0 0 1px var(--qgi-accent)" : "none",
                cursor: gated ? "not-allowed" : "pointer",
                opacity: gated ? 0.55 : 1,
                letterSpacing: "0.5px",
              }}
            >
              {r}
            </button>
          );
        })}
        <span style={{ color: "var(--qgi-text-dim)", marginLeft: "2px" }}>
          last 12 months · drag left for earlier years
        </span>
      </div>

      {sel && <PulseEventsChart series={sel} thresholds={detail.thresholds} />}

      {/* Verdict legend, the country page carries the explanatory arc, so
          the four states are defined here (the terminal may assume them). */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "14px",
          marginTop: "12px",
          fontSize: "11px",
          color: "var(--qgi-text-muted)",
        }}
      >
        {(Object.keys(detail.verdicts) as HfVerdict[]).map((v) => (
          <span
            key={v}
            style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}
          >
            <span
              aria-hidden="true"
              style={{
                width: "7px",
                height: "7px",
                borderRadius: "50%",
                background: verdictColor(v),
              }}
            />
            {VERDICT_LABEL[v]}
            <InfoTooltip text={detail.verdicts[v]} />
          </span>
        ))}
        <span style={{ flex: 1 }} />
        <Link
          href={"/methodology#news-layer" as Route}
          target="_blank"
          rel="noopener"
          style={{ color: "var(--qgi-accent)", textDecoration: "none", fontSize: "11px" }}
        >
          How verdicts are assigned →
        </Link>
      </div>

      <p
        style={{
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          margin: "10px 0 0",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        {GLOBAL_PERCENTILE_NOTE} Event markers come from the verified record.
      </p>
    </PanelShell>
  );
}

function PulseEventsChart({
  series,
  thresholds,
}: {
  series: HfTopicSeries;
  thresholds: { struct: number; pulse: number };
}) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);
  const struct = series.cell?.struct ?? null;

  // Open on the last 12 months; the reader drags left to scroll into earlier
  // years (no double-range slider, TradingView idiom, founder 2026-06-13).
  const n = series.months.length;
  const defaultStart = n > 12 ? Math.round(((n - 12) / n) * 100) : 0;

  const markers = series.events
    .map((e) => {
      const i = series.months.indexOf(e.date);
      return i < 0 ? null : { coord: [e.date, series.pulse[i]], label: e.label };
    })
    .filter(Boolean) as Array<{ coord: [string, number]; label: string }>;

  const option = {
    backgroundColor: "transparent",
    animation: false,
    tooltip: {
      trigger: "axis",
      // Render on document.body so the popup can never be squeezed or cut
      // at a panel border (founder catch 2026-06-11; ECharts analog of the
      // #567 InfoTooltip position:fixed fix).
      appendToBody: true,
      confine: true,
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (ps: Array<{ axisValue: string; data: number; seriesName: string }>) => {
        const p = ps[0];
        const ev = series.events.find((e) => e.date === p.axisValue);
        return (
          `${p.axisValue}<br/>news pressure ${Math.round(p.data)}` +
          (struct !== null ? `<br/>structural ${Math.round(struct)}` : "") +
          (ev ? `<br/><span style="color:${t.amber}">${ev.label}</span>` : "")
        );
      },
    },
    legend: {
      top: 2,
      right: 6,
      textStyle: { color: t.textMuted, fontSize: 10 },
      data: struct !== null ? ["News pressure", "Structural"] : ["News pressure"],
    },
    grid: { left: 42, right: 16, top: 28, bottom: 26 },
    xAxis: {
      type: "category",
      data: series.months,
      boundaryGap: false,
      axisLine: { lineStyle: { color: t.border } },
      axisTick: { show: false },
      axisLabel: {
        color: t.textDim,
        fontSize: 10,
        hideOverlap: true,
        // Full year on January, month number otherwise, so year boundaries
        // stay legible as the reader scrolls back through history.
        formatter: (v: string) => (v.endsWith("-01") ? v.slice(0, 4) : v.slice(5)),
      },
    },
    yAxis: {
      min: 0,
      max: 100,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: t.splitLine, opacity: 0.5 } },
      axisLabel: { color: t.textDim, fontSize: 10 },
    },
    // Inside-only pan/zoom: drag to scroll through history, wheel to zoom. No
    // slider (founder: "TradingView doesn't have it, we don't need it").
    dataZoom: [
      {
        type: "inside",
        start: defaultStart,
        end: 100,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        moveOnMouseWheel: false,
      },
    ],
    series: [
      {
        name: "News pressure",
        type: "line",
        data: series.pulse,
        symbol: "none",
        lineStyle: { width: 1.8, color: t.accent },
        areaStyle: { color: `${t.accent}22` },
        markPoint: {
          symbol: "pin",
          symbolSize: 20,
          itemStyle: { color: t.surface2, borderColor: t.amber, borderWidth: 1.5 },
          label: { show: false },
          // No emphasis label: the axis tooltip names the event on a pinned
          // month; a second box duplicating it reads as a bug (founder catch).
          emphasis: { disabled: true },
          data: markers.map((m) => ({ coord: m.coord, value: m.label })),
        },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: t.textDim, type: "dashed", width: 1 },
          label: {
            show: true,
            position: "insideEndTop" as const,
            color: t.textDim,
            fontSize: 10,
            formatter: "elevated 60",
          },
          data: [{ yAxis: thresholds.pulse }],
        },
      },
      // News-only trends (migration, corruption; labor_action was promoted to
      // full two-layer 2026-07-05) have no structural resemblance to plot,
      // the line is dropped entirely.
      ...(struct !== null
        ? [
            {
              name: "Structural",
              type: "line" as const,
              data: series.months.map(() => struct),
              symbol: "none" as const,
              // Series-level color so the legend swatch matches the line
              // (without it ECharts paints the key from its default palette).
              color: t.amber,
              itemStyle: { color: t.amber },
              lineStyle: {
                width: 1.6,
                type: "dashed" as const,
                color: t.amber,
                opacity: 0.8,
              },
            },
          ]
        : []),
    ],
  };

  return <ReactECharts option={option} style={{ height: "260px", width: "100%" }} />;
}

/* ── Trend drift: stacked-to-100% share of attention ─────────────────── */

const DRIFT_HINT_STYLE = {
  fontFamily: "ui-monospace, monospace",
  fontSize: "10px",
  color: "var(--qgi-text-dim)",
  margin: "0 0 10px",
} as const;

export function TopicDriftPanel({
  detail,
  accent,
}: {
  detail: HfCountryDetail;
  accent: string;
}) {
  const { isDark } = useTheme();
  // One fixed trend order (see trendDriftOrder above), instead of
  // detail.series' per-country strength sort, so a trend keeps the same
  // stack slot and color across countries.
  const ordered: HfCountryDetail = { ...detail, series: trendDriftOrder(detail.series) };

  return (
    <PanelShell
      title="Trend Drift"
      titleCase
      accent={accent}
      tooltip="Each month's news pressure per trend, stacked to that month's 100% share of total attention, ranked across every covered country and month. Reads the shifting mix of what a country's news is amplifying, not the absolute level (see News Pulse for that)."
      caption={
        <>
          Share of {detail.name}&apos;s news attention across the six trends, over time.
        </>
      }
      fullWidth
    >
      {/* Legend: one chip per trend, its fixed color, HTML (not the ECharts
          internal legend) so it reads the same as the verdict key above and
          never gets squeezed by the chart's own grid. */}
      <div
        role="list"
        aria-label="Trends"
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "12px",
          marginBottom: "8px",
          fontSize: "11px",
          color: "var(--qgi-text-muted)",
        }}
      >
        {ordered.series.map((s) => (
          <span
            key={s.topic.id}
            role="listitem"
            style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}
          >
            <span
              aria-hidden="true"
              style={{
                width: "9px",
                height: "9px",
                borderRadius: "2px",
                background: trendColor(s.topic.id, isDark),
                flexShrink: 0,
              }}
            />
            {s.topic.label}
          </span>
        ))}
      </div>
      <p style={DRIFT_HINT_STYLE}>
        Each month&apos;s trends stacked to 100% of that month&apos;s combined news
        pressure. Full history, last 24 months shown by default, drag left for 2015.
      </p>
      <TrendDriftShare detail={ordered} />
    </PanelShell>
  );
}

/** Shared inside-only dataZoom: default to the last ~24 months, drag left to
 *  scroll back through the full history (no slider; TradingView idiom, same
 *  pattern as PulseEventsChart). */
function driftDataZoom(n: number) {
  const defaultStart = n > 24 ? Math.round(((n - 24) / n) * 100) : 0;
  return [
    {
      type: "inside" as const,
      start: defaultStart,
      end: 100,
      zoomOnMouseWheel: true,
      moveOnMouseMove: true,
      moveOnMouseWheel: false,
    },
  ];
}

/** Each month's trends stacked to 100% of that month's combined news
 *  pressure, so a reader can see the shifting share of attention. Months
 *  with zero recorded pressure across every trend split the share evenly
 *  rather than rendering as a NaN gap. The legend lives outside the chart
 *  (TopicDriftPanel above), so the ECharts internal legend stays off. */
function TrendDriftShare({ detail }: { detail: HfCountryDetail }) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);
  const months = detail.series[0]?.months ?? [];
  const n = months.length;

  const shares: number[][] = detail.series.map(() => []);
  for (let mi = 0; mi < n; mi++) {
    const raw = detail.series.map((s) => Math.max(0, s.pulse[mi] ?? 0));
    const total = raw.reduce((a, b) => a + b, 0);
    raw.forEach((v, si) => {
      shares[si].push(total > 0 ? (v / total) * 100 : 100 / raw.length);
    });
  }

  const option = {
    backgroundColor: "transparent",
    animation: false,
    tooltip: {
      trigger: "axis",
      appendToBody: true,
      confine: true,
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (
        ps: Array<{
          axisValue: string;
          data: number;
          seriesName: string;
          color: string;
          seriesIndex: number;
          dataIndex: number;
        }>
      ) => {
        const rows = ps
          .slice()
          .sort((a, b) => (b.data ?? 0) - (a.data ?? 0))
          .map((p) => {
            const rawPulse = detail.series[p.seriesIndex]?.pulse[p.dataIndex] ?? 0;
            return `<span style="color:${p.color}">${p.seriesName}</span> ${Math.round(p.data)}% (pressure ${Math.round(rawPulse)})`;
          })
          .join("<br/>");
        return `${ps[0]?.axisValue}<br/>${rows}`;
      },
    },
    // No ECharts legend: TopicDriftPanel renders the trend color key as HTML
    // above the chart (one legend, not a duplicate second one in-canvas).
    grid: { left: 42, right: 16, top: 16, bottom: 26 },
    xAxis: {
      type: "category",
      data: months,
      boundaryGap: false,
      axisLine: { lineStyle: { color: t.border } },
      axisTick: { show: false },
      axisLabel: {
        color: t.textDim,
        fontSize: 10,
        hideOverlap: true,
        formatter: (v: string) => (v.endsWith("-01") ? v.slice(0, 4) : v.slice(5)),
      },
    },
    yAxis: {
      min: 0,
      max: 100,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: t.splitLine, opacity: 0.5 } },
      axisLabel: { color: t.textDim, fontSize: 10, formatter: "{value}%" },
    },
    dataZoom: driftDataZoom(n),
    series: detail.series.map((s, si) => {
      const color = trendColor(s.topic.id, isDark);
      return {
        name: s.topic.label,
        type: "line" as const,
        stack: "share",
        data: shares[si],
        symbol: "none" as const,
        lineStyle: { width: 1, color },
        areaStyle: { color, opacity: 0.82 },
      };
    }),
  };

  return <ReactECharts option={option} style={{ height: "260px", width: "100%" }} />;
}
