"use client";

/**
 * TrendNewsSignalPanel: the news layer on the trend report card
 * (HF merge step 3, 2026-06-11; rebuilt for the Topics->Trends migration,
 * founder 2026-07-04).
 *
 * Two render modes now reach this component (a third, coming-soon, is
 * handled upstream by TrendNewsComingSoonPanel below so a trend with no
 * native feed never mounts this file at all):
 *   - FULL live trend (struct + news pressure both exist): an XY quadrant,
 *     modeled on TrendConfirmRejectPanel's ECharts option, plotting every
 *     covered country as a dot colored by verdict. Click a dot to open that
 *     country's drilldown.
 *   - NEWS-ONLY live trend: reserved for a trend with no structural axis.
 *     NEWS_ONLY_TRENDS (trend-taxonomy.ts) is empty as of the 2026-07-04
 *     migration, so labor_action now renders the full two-layer
 *     QuadrantPanel like every other live trend. NewsOnlyPanel below stays
 *     wired through signal.pulseOnly so a future news-only trend falls into
 *     it automatically; nothing currently reaches it.
 *
 * Conventions carried from the earlier rounds: PanelShell frame,
 * ExplainTip/InfoTooltip (never title-only), thresholds stated inline,
 * theme tokens, appendToBody tooltips, no em-dashes. Verdict labels are the
 * canonical set (Both Firing / News-Only / Elevated & Quiet / Quiet), shared
 * with the dashboard InteractiveLandscape and the methodology docs.
 */

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { InfoTooltip } from "@/components/design/InfoTooltip";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens, type EchartsTokens } from "@/lib/echarts-theme";
import type { HfVerdict } from "@/lib/hf/topics-data";
import type { TrendNewsSignal } from "@/lib/hf/trend-signal";
import { GLOBAL_PERCENTILE_NOTE } from "@/lib/hf/news-scale";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

// Canonical verdict labels (standardized everywhere, 2026-07-05): the
// internal HfVerdict enum keys stay ACTIVE/SIGNAL/LATENT/QUIET, only the
// human-facing labels changed. Same mapping as dashboard InteractiveLandscape.
const VERDICT_LABEL: Record<HfVerdict, string> = {
  ACTIVE: "Both Firing",
  SIGNAL: "News-Only",
  LATENT: "Elevated & Quiet",
  QUIET: "Quiet",
};

const VERDICT_STYLE: Record<HfVerdict, { color: string; bg: string; border: string }> = {
  ACTIVE: {
    color: "var(--qgi-warning)",
    bg: "color-mix(in srgb, var(--qgi-warning) 13%, transparent)",
    border: "color-mix(in srgb, var(--qgi-warning) 50%, transparent)",
  },
  SIGNAL: {
    color: "var(--qgi-accent)",
    bg: "color-mix(in srgb, var(--qgi-accent) 12%, transparent)",
    border: "color-mix(in srgb, var(--qgi-accent) 50%, transparent)",
  },
  LATENT: {
    color: "var(--qgi-text-muted)",
    bg: "var(--qgi-surface-2)",
    border: "var(--qgi-border)",
  },
  QUIET: {
    color: "var(--qgi-text-dim)",
    bg: "transparent",
    border: "color-mix(in srgb, var(--qgi-border) 70%, transparent)",
  },
};

function verdictTok(v: HfVerdict, t: EchartsTokens): string {
  return v === "ACTIVE"
    ? t.warning
    : v === "SIGNAL"
      ? t.accent
      : v === "LATENT"
        ? t.textMuted
        : t.textDim;
}

/** `text` may contain `\n` to wrap onto a second line (ECharts text graphics
 *  don't auto-wrap); "Elevated & Quiet" needs it to fit the corner cleanly,
 *  so it also takes a smaller default fontSize than the other three. */
function cornerCaption(
  text: string,
  fill: string,
  x: "left" | "right",
  y: "top" | "bottom",
  fontSize = 10
) {
  return {
    type: "text" as const,
    [x]: x === "left" ? "13%" : "9%",
    [y]: y === "top" ? "9%" : "16%",
    style: {
      text,
      fill,
      fontSize,
      lineHeight: fontSize + 2,
      fontFamily: "ui-monospace, monospace",
      opacity: 0.8,
    },
    silent: true,
    z: 1,
  };
}

/** Shared legend + methodology footer, used by both live-trend modes. */
function VerdictLegend({ signal }: { signal: TrendNewsSignal }) {
  return (
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
      {(Object.keys(VERDICT_STYLE) as HfVerdict[]).map((v) => (
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
              background: VERDICT_STYLE[v].color,
            }}
          />
          {VERDICT_LABEL[v]}
          <InfoTooltip text={signal.verdicts[v]} />
        </span>
      ))}
      <span style={{ flex: 1 }} />
      <Link
        href={"/methodology#news-layer" as Route}
        target="_blank"
        rel="noopener"
        style={{ color: "var(--qgi-accent)", textDecoration: "none", fontSize: "11px" }}
      >
        How verdicts are assigned &rarr;
      </Link>
    </div>
  );
}

export function TrendNewsSignalPanel({
  slug,
  trendLabel,
  signal,
}: {
  slug: string;
  trendLabel: string;
  signal: TrendNewsSignal;
}) {
  if (signal.pulseOnly) {
    return <NewsOnlyPanel slug={slug} trendLabel={trendLabel} signal={signal} />;
  }
  return <QuadrantPanel slug={slug} trendLabel={trendLabel} signal={signal} />;
}

/* ───────── Mode (a): FULL live trend, struct x news pressure quadrant ── */

function QuadrantPanel({
  slug,
  trendLabel,
  signal,
}: {
  slug: string;
  trendLabel: string;
  signal: TrendNewsSignal;
}) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);
  const router = useRouter();
  const { rows, thresholds: th, notScored } = signal;

  const trendLower = trendLabel.toLowerCase();
  const panelTip = `This trend's news pressure: how much of each country's coverage runs on the trend each month, ranked across every covered country and month (50 is the median for this trend). The verdict pairs that pressure with the country's score on this trend; both count as elevated from 60 upward.`;

  const points = rows.map((r) => ({
    name: r.name,
    href: r.iso2 ? `/trends/${slug}/countries/${r.iso2}` : null,
    value: [r.struct ?? 0, r.pulse],
    verdict: r.verdict,
    itemStyle: { color: verdictTok(r.verdict, t), opacity: 0.82 },
  }));

  const structVals = rows.map((r) => r.struct ?? 0);
  const xMin = Math.min(
    30,
    Math.max(0, Math.floor((Math.min(...structVals) - 5) / 10) * 10)
  );

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      appendToBody: true,
      confine: true,
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (p: { data: { name: string; value: number[]; verdict: HfVerdict } }) =>
        `<b>${p.data.name}</b><br/>trend score ${Math.round(p.data.value[0])} · news pressure ${Math.round(
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
      name: "NEWS PRESSURE",
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
      // Longest label of the four: wrapped to 2 lines + a smaller fontSize
      // so it fits the corner without crowding the axis.
      cornerCaption("Elevated &\nQuiet", t.textMuted, "right", "bottom", 9),
      cornerCaption("Quiet", t.textDim, "left", "bottom"),
    ],
    series: [
      {
        type: "scatter",
        data: points,
        cursor: "pointer",
        symbolSize: 11,
        emphasis: { scale: 1.4, itemStyle: { opacity: 1 } },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: t.textDim, type: "dashed", width: 1.2 },
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
      title="News Pulse"
      titleCase
      accent="var(--qgi-accent)"
      tooltip={panelTip}
      caption={
        <>
          Where the news is running with the {trendLower} trend this month: every covered
          country&apos;s trend score against its news pressure
          <InfoTooltip text={GLOBAL_PERCENTILE_NOTE} />, strongest combined readings top
          right. Select a dot to open that country&apos;s drilldown.
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
        style={{ height: "360px", width: "100%" }}
      />

      <VerdictLegend signal={signal} />

      <p
        style={{
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          margin: "10px 0 0",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        The numbers read trend score, news pressure, both 0 to 100.{" "}
        {GLOBAL_PERCENTILE_NOTE} Pressure updates monthly.
        {notScored.length > 0 &&
          ` ${notScored.join(" and ")} ${notScored.length === 1 ? "is" : "are"} not scored on this trend (indicator coverage), so ${notScored.length === 1 ? "it does" : "they do"} not appear here.`}
      </p>
    </PanelShell>
  );
}

/* ───────── Mode (b): NEWS-ONLY live trend, compact ranked list ─────────── */

function NewsOnlyPanel({
  slug,
  trendLabel,
  signal,
}: {
  slug: string;
  trendLabel: string;
  signal: TrendNewsSignal;
}) {
  const { rows } = signal;
  const trendLower = trendLabel.toLowerCase();
  const panelTip = `This trend's news pressure: how much of each country's coverage runs on the trend each month, ranked across every covered country and month (50 is the median for this trend). This trend is shown news-only right now: the verdict reads the pressure alone, elevated from 60 upward.`;

  return (
    <PanelShell
      title="News Pulse"
      titleCase
      accent="var(--qgi-accent)"
      tooltip={panelTip}
      caption={
        <>
          Where the news is running with the {trendLower} trend this month, strongest
          readings first.
          <InfoTooltip text={GLOBAL_PERCENTILE_NOTE} />
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {rows.map((r) => {
          const vs = VERDICT_STYLE[r.verdict];
          const inner = (
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "9px",
                }}
              >
                <FlagImg emoji={flagFor(r.name)} name={r.name} width={16} radius={2} />
                <span
                  style={{
                    fontSize: "12.5px",
                    fontWeight: 600,
                    color: "var(--qgi-text)",
                    flex: 1,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {r.name}
                </span>
                <span
                  className="font-data"
                  style={{
                    fontSize: "11px",
                    color: "var(--qgi-text-muted)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {Math.round(r.pulse)}
                </span>
                <span
                  style={{
                    fontSize: "10.5px",
                    fontWeight: 600,
                    letterSpacing: "0.5px",
                    padding: "2px 8px",
                    borderRadius: "9px",
                    color: vs.color,
                    background: vs.bg,
                    border: `1px solid ${vs.border}`,
                    whiteSpace: "nowrap",
                  }}
                >
                  {VERDICT_LABEL[r.verdict]}
                </span>
              </div>
              <div
                style={{
                  height: "3px",
                  borderRadius: "2px",
                  background: "var(--qgi-border)",
                  marginTop: "5px",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${Math.max(2, Math.min(100, r.pulse))}%`,
                    height: "100%",
                    background: vs.color,
                    borderRadius: "2px",
                  }}
                />
              </div>
            </div>
          );
          return r.iso2 ? (
            <Link
              key={r.iso3}
              href={`/trends/${slug}/countries/${r.iso2}` as Route}
              style={{ textDecoration: "none", color: "inherit" }}
            >
              {inner}
            </Link>
          ) : (
            <div key={r.iso3}>{inner}</div>
          );
        })}
      </div>

      <div
        style={{
          marginTop: "14px",
          padding: "10px 12px",
          border: "1px dashed var(--qgi-border)",
          borderRadius: "5px",
          background: "rgba(255,255,255,0.015)",
          fontSize: "11.5px",
          lineHeight: 1.5,
          color: "var(--qgi-text-muted)",
        }}
      >
        Structural read coming soon for this trend. Right now, the verdict reads the news
        pressure alone.
      </div>

      <VerdictLegend signal={signal} />

      <p
        style={{
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          margin: "10px 0 0",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        The number is the news pressure, 0 to 100, this trend carries no structural axis.{" "}
        {GLOBAL_PERCENTILE_NOTE} Pressure updates monthly.
      </p>
    </PanelShell>
  );
}

/* ───────── Mode (c): COMING-SOON trend, no native feed yet ─────────────── */

// Fake preview rows for the coming-soon blur: plausible countries + verdict
// pills, never real data. Fixed set (not sourced from any trend) so the
// blur reads as "a preview of the shape of this panel", not a leaked score.
const COMING_SOON_PREVIEW_ROWS: { name: string; pulse: number; verdict: HfVerdict }[] = [
  { name: "Nigeria", pulse: 71, verdict: "ACTIVE" },
  { name: "Pakistan", pulse: 58, verdict: "SIGNAL" },
  { name: "Brazil", pulse: 46, verdict: "LATENT" },
  { name: "Indonesia", pulse: 39, verdict: "SIGNAL" },
  { name: "Turkey", pulse: 27, verdict: "QUIET" },
  { name: "Vietnam", pulse: 18, verdict: "QUIET" },
];

/**
 * TrendNewsComingSoonPanel: the placeholder page.tsx renders in place of
 * TrendNewsSignalPanel when getTrendNewsSignal().status is 'coming_soon'.
 * No struct, no pulse, no drilldown, and no naming of the data source: a
 * blurred preview of the row layout the real News Pulse list will use,
 * with a centered "coming soon" lockup over it. Single column (not
 * fullWidth), same PanelShell frame as every other panel on the page.
 */
export function TrendNewsComingSoonPanel({ trendLabel }: { trendLabel: string }) {
  const trendLower = trendLabel.toLowerCase();
  return (
    <PanelShell
      title="News Pulse"
      titleCase
      accent="#7A8FA0"
      tooltip={`We're building this trend's dedicated news feed. Until it ships, this trend has no news layer.`}
    >
      <div style={{ position: "relative" }}>
        {/* Blurred backdrop: same row shape as the live list (flag, name,
            pulse number, verdict pill, mini bar), fake data throughout. */}
        <div
          aria-hidden="true"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "8px",
            filter: "blur(4px)",
            opacity: 0.5,
            pointerEvents: "none",
            userSelect: "none",
          }}
        >
          {COMING_SOON_PREVIEW_ROWS.map((r) => {
            const vs = VERDICT_STYLE[r.verdict];
            return (
              <div key={r.name}>
                <div style={{ display: "flex", alignItems: "center", gap: "9px" }}>
                  <FlagImg emoji={flagFor(r.name)} name={r.name} width={16} radius={2} />
                  <span
                    style={{
                      fontSize: "12.5px",
                      fontWeight: 600,
                      color: "var(--qgi-text)",
                      flex: 1,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {r.name}
                  </span>
                  <span
                    className="font-data"
                    style={{
                      fontSize: "11px",
                      color: "var(--qgi-text-muted)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {r.pulse}
                  </span>
                  <span
                    style={{
                      fontSize: "10.5px",
                      fontWeight: 600,
                      letterSpacing: "0.5px",
                      padding: "2px 8px",
                      borderRadius: "9px",
                      color: vs.color,
                      background: vs.bg,
                      border: `1px solid ${vs.border}`,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {VERDICT_LABEL[r.verdict]}
                  </span>
                </div>
                <div
                  style={{
                    height: "3px",
                    borderRadius: "2px",
                    background: "var(--qgi-border)",
                    marginTop: "5px",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${Math.max(2, Math.min(100, r.pulse))}%`,
                      height: "100%",
                      background: vs.color,
                      borderRadius: "2px",
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Centered lockup, overlaid on the blur. */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "12px",
          }}
        >
          <div
            style={{
              textAlign: "center",
              maxWidth: "300px",
              padding: "14px 22px",
              border: "1px solid var(--qgi-border)",
              borderRadius: "8px",
              background: "var(--qgi-surface-2)",
              boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
            }}
          >
            <div
              style={{
                fontSize: "9.5px",
                letterSpacing: "2.5px",
                textTransform: "uppercase",
                color: "#7A8FA0",
                fontFamily: "ui-monospace, monospace",
                marginBottom: "6px",
              }}
            >
              Coming soon
            </div>
            <p
              style={{
                fontSize: "12px",
                lineHeight: 1.5,
                color: "var(--qgi-text-muted)",
                margin: 0,
              }}
            >
              We&apos;re working on the {trendLower} trend&apos;s news feed.
            </p>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}
