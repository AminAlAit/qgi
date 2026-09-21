"use client";
/**
 * InteractiveLandscape, the hybrid Briefing's centre-piece scatter chart.
 *
 * Based on briefing-signal/QuadrantChart but with two filter dropdowns:
 *   - Country selector (All + every distinct country present in the data)
 *   - Trend selector   (All + every distinct trend present in the data)
 *
 * Selection behaviour:
 *   - All/All        → every dot rendered at normal opacity
 *   - Country only   → that country's dots brightened / enlarged; rest dimmed
 *   - Trend only     → that trend's dots brightened / enlarged; rest dimmed
 *   - Both           → the matching country×trend intersection dot gets a ring
 *                      and label; rest dimmed proportionally
 *
 * 2026-06-20: Verdict color key moved OUT of the ECharts legend and rendered
 * as HTML swatch chips in the controls row. ECharts legend removed to avoid
 * duplication. Active count badge removed. Panel description replaced with
 * plain-English copy.
 *
 * Plots the 6 live news trends x countries (Topics->Trends migration,
 * 2026-07-04). Coming-soon trends carry no cells, so they are simply absent
 * from the scatter; a small note beneath the chart names them.
 *
 * Rendered with ssr:false via dynamic import in InteractiveLandscapeWrapper.
 */
import { useState, useMemo } from "react";
import { useResponsiveLayout } from "@/lib/hooks/useMediaQuery";
import ReactECharts from "echarts-for-react";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens } from "@/lib/echarts-theme";
import type { ScatterPoint } from "@/components/briefing-signal/QuadrantSection";
import { GLOBAL_PERCENTILE_NOTE } from "@/lib/hf/news-scale";
import { COMING_SOON_TREND_COLUMNS } from "@/lib/hf/trend-taxonomy";

const VERDICT_COLORS = {
  ACTIVE: "#E05C5C",
  SIGNAL: "#f59e0b",
  LATENT: "#5B7E99",
  QUIET: "#243347",
} as const;

// Verdict key entries shown in the controls row (human-readable label).
const VERDICT_KEY: { verdict: keyof typeof VERDICT_COLORS; label: string }[] = [
  { verdict: "ACTIVE", label: "Both Firing" },
  { verdict: "LATENT", label: "Elevated & Quiet" },
  { verdict: "SIGNAL", label: "News-Only" },
  { verdict: "QUIET", label: "Quiet" },
];

interface Props {
  points: ScatterPoint[];
  activeCount: number;
  inPlayCount: number;
  silentAlarmCount: number;
}

const ALL = "All";

// Elegant one-liner naming the curated columns that don't have a news feed
// yet. Handles 1, 2 or 3+ entries (the list is expandable).
function comingSoonNote(): string | null {
  const labels = COMING_SOON_TREND_COLUMNS.map((c) => c.label);
  if (labels.length === 0) return null;
  if (labels.length === 1) return `${labels[0]}: news feed coming soon.`;
  const head = labels.slice(0, -1).join(", ");
  const last = labels[labels.length - 1];
  return `${head} and ${last}: news feeds coming soon.`;
}

export function InteractiveLandscape({ points }: Props) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);

  // ── Derived option lists (sorted, deduplicated) ───────────────────────────
  const countries = useMemo(() => {
    const names = Array.from(new Set(points.map((p) => p.countryName))).sort();
    return [ALL, ...names];
  }, [points]);

  const topics = useMemo(() => {
    const labels = Array.from(new Set(points.map((p) => p.topicLabel))).sort();
    return [ALL, ...labels];
  }, [points]);

  // ── Filter state ──────────────────────────────────────────────────────────
  const [selectedCountry, setSelectedCountry] = useState<string>(ALL);
  const [selectedTopic, setSelectedTopic] = useState<string>(ALL);
  const [selectedVerdict, setSelectedVerdict] = useState<
    keyof typeof VERDICT_COLORS | null
  >(null);

  // Phone-width (<=480px) chart adjustments. The combined hook flips `mounted`
  // and `isNarrow` in one commit; the chart is gated on `mounted` below so it
  // renders ONCE with the correct margins instead of flashing desktop→narrow.
  const { mounted, isMobile: isNarrow } = useResponsiveLayout("(max-width: 480px)");

  const isFiltered =
    selectedCountry !== ALL || selectedTopic !== ALL || selectedVerdict !== null;

  function reset() {
    setSelectedCountry(ALL);
    setSelectedTopic(ALL);
    setSelectedVerdict(null);
  }

  // ── Per-quadrant counts (split at 60/60) for the guide cards ───────────────
  const quadCounts = useMemo(() => {
    let bothFiring = 0;
    let silentAlarm = 0;
    let newsOnly = 0;
    let quiet = 0;
    for (const p of points) {
      const hiStruct = p.struct >= 60;
      const hiPulse = p.pulse >= 60;
      if (hiStruct && hiPulse) bothFiring++;
      else if (hiStruct && !hiPulse) silentAlarm++;
      else if (!hiStruct && hiPulse) newsOnly++;
      else quiet++;
    }
    return { bothFiring, silentAlarm, newsOnly, quiet };
  }, [points]);

  // ── ECharts option derived from filter state ───────────────────────────────
  const option = useMemo(() => {
    const byVerdict: Record<string, ScatterPoint[]> = {
      ACTIVE: [],
      SIGNAL: [],
      LATENT: [],
      QUIET: [],
    };

    for (const p of points) {
      byVerdict[p.verdict]?.push(p);
    }

    // Determine which dot matches the active filters (the intersection)
    const hasCountryFilter = selectedCountry !== ALL;
    const hasTopicFilter = selectedTopic !== ALL;
    const hasVerdictFilter = selectedVerdict !== null;
    const hasBothFilters = hasCountryFilter && hasTopicFilter;

    // Build series: one per verdict
    const series = (["ACTIVE", "SIGNAL", "LATENT", "QUIET"] as const).map((v) => {
      const pts = byVerdict[v];

      return {
        name: v,
        type: "scatter" as const,
        data: pts.map((p) => {
          // Determine highlight state
          const countryMatch = !hasCountryFilter || p.countryName === selectedCountry;
          const topicMatch = !hasTopicFilter || p.topicLabel === selectedTopic;
          const verdictMatch = !hasVerdictFilter || v === selectedVerdict;
          const isHighlighted = countryMatch && topicMatch && verdictMatch;
          const isIntersection =
            hasBothFilters && countryMatch && topicMatch && verdictMatch;

          const baseOpacity = v === "QUIET" ? 0.3 : 0.8;
          const dimmedOpacity = 0.08;
          const opacity = !isFiltered
            ? baseOpacity
            : isHighlighted
              ? v === "QUIET"
                ? 0.5
                : 0.95
              : dimmedOpacity;

          const baseSize = v === "QUIET" ? 5 : 8;
          const size = !isFiltered
            ? baseSize
            : isHighlighted
              ? isIntersection
                ? 16
                : 12
              : baseSize * 0.8;

          return {
            // value = [x, y, ...] with x = news pulse, y = structure
            value: [p.pulse, p.struct, p.countryName, p.topicLabel],
            itemStyle: {
              color: VERDICT_COLORS[v],
              opacity,
              // Intersection dot gets a border ring
              borderColor: isIntersection ? "#fff" : "transparent",
              borderWidth: isIntersection ? 2 : 0,
            },
            symbolSize: size,
            // Label shown on intersection dot only
            label: isIntersection
              ? {
                  show: true,
                  position: "top" as const,
                  formatter: `${p.countryName}`,
                  fontSize: 10,
                  color: t.text,
                  backgroundColor: t.surface,
                  padding: [2, 5],
                  borderRadius: 3,
                }
              : { show: false },
          };
        }),
        symbolSize: (data: unknown) =>
          (data as { symbolSize?: number })?.symbolSize ?? (v === "QUIET" ? 5 : 8),
        itemStyle: { color: VERDICT_COLORS[v] },
        // label config at series level (per-item overrides above take precedence)
        label: { show: false },
      };
    });

    return {
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item" as const,
        backgroundColor: t.surface,
        borderColor: t.border,
        textStyle: { color: t.text, fontSize: 11 },
        formatter: (params: { value: (string | number)[]; seriesName: string }) => {
          const [pulse, struct, country, topic] = params.value;
          const verdictColor =
            VERDICT_COLORS[params.seriesName as keyof typeof VERDICT_COLORS] ??
            t.textMuted;
          return [
            `<b style="color:${t.text}">${country}</b> · <span style="color:${t.textMuted}">${topic}</span>`,
            `Struct: <span style="color:${t.amber};font-weight:700">${Math.round(Number(struct))}</span> &nbsp; Pulse: <span style="color:${t.accent}">${Math.round(Number(pulse))}</span>`,
            `<span style="color:${verdictColor};font-weight:700;letter-spacing:1px;font-size:10px">${params.seriesName}</span>`,
          ].join("<br/>");
        },
      },
      // No ECharts legend — color key is rendered as HTML chips in the controls row.
      // On narrow phones: tighten left margin (y-axis name hidden → shown as caption),
      // reduce font sizes to reclaim plot area.
      grid: {
        top: 16,
        right: 16,
        bottom: isNarrow ? 44 : 52,
        left: isNarrow ? 36 : 60,
      },
      xAxis: {
        name: "News Pressure (%)",
        nameLocation: "middle" as const,
        nameGap: isNarrow ? 26 : 30,
        nameTextStyle: {
          color: t.textDim,
          fontSize: isNarrow ? 10 : 11.5,
          fontWeight: 600,
        },
        min: 0,
        max: 100,
        axisLine: { lineStyle: { color: t.border } },
        axisLabel: { color: t.textMuted, fontSize: isNarrow ? 10 : 11 },
        splitLine: { lineStyle: { color: t.splitLine } },
      },
      yAxis: {
        // On phone the long y-axis name overlaps the plot; hide it and show a
        // plain-text caption below the chart instead.
        name: isNarrow ? "" : `Structural Fair Value for ${new Date().getFullYear()} (%)`,
        nameLocation: "middle" as const,
        nameGap: 40,
        nameTextStyle: { color: t.textDim, fontSize: 11.5, fontWeight: 600 },
        min: 0,
        max: 100,
        axisLine: { lineStyle: { color: t.border } },
        axisLabel: { color: t.textMuted, fontSize: isNarrow ? 10 : 11 },
        splitLine: { lineStyle: { color: t.splitLine } },
      },
      series: [
        ...series,
        // Reference lines at struct=60, pulse=60
        {
          name: "_ref",
          type: "scatter" as const,
          data: [],
          // Quadrant background tints (split at 60/60) — replaces the text labels
          markArea: {
            silent: true,
            data: [
              // top-right: high news + high structure → Active (red)
              [
                { coord: [60, 60], itemStyle: { color: "rgba(224,92,92,0.07)" } },
                { coord: [100, 100] },
              ],
              // top-left: quiet news + high structure → Latent (slate)
              [
                { coord: [0, 60], itemStyle: { color: "rgba(91,126,153,0.07)" } },
                { coord: [60, 100] },
              ],
              // bottom-right: high news + thin structure → Signal (amber)
              [
                { coord: [60, 0], itemStyle: { color: "rgba(245,158,11,0.06)" } },
                { coord: [100, 60] },
              ],
              // bottom-left: low on both → Quiet (dim)
              [
                { coord: [0, 0], itemStyle: { color: "rgba(91,126,153,0.022)" } },
                { coord: [60, 60] },
              ],
            ],
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: {
              color: "rgba(91,126,153,0.40)",
              type: "dashed",
              width: 1,
            },
            label: { show: false },
            data: [{ xAxis: 60 }, { yAxis: 60 }],
          },
        },
      ],
    };
  }, [points, selectedCountry, selectedTopic, selectedVerdict, t, isFiltered, isNarrow]);

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "16px",
      }}
    >
      {/* Section header — no active count badge */}
      <div style={{ marginBottom: "12px" }}>
        <h2
          style={{
            fontSize: "18px",
            fontWeight: 700,
            margin: "0 0 4px",
            letterSpacing: "-0.3px",
            color: "var(--qgi-text)",
          }}
        >
          Signal Landscape
        </h2>
        <p
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-muted)",
            margin: 0,
            lineHeight: 1.4,
          }}
        >
          One dot per country-trend. Further right = louder in the news right now, higher
          = structure more like past crises. Use the menus or the status keys to spotlight
          what matters. {GLOBAL_PERCENTILE_NOTE}
        </p>
      </div>

      {/* Controls row: dropdowns + verdict color key chips */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          marginBottom: "12px",
          flexWrap: "wrap",
        }}
      >
        {/* Country dropdown */}
        <select
          value={selectedCountry}
          onChange={(e) => setSelectedCountry(e.target.value)}
          aria-label="Filter by country"
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            color: "var(--qgi-text)",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "4px",
            padding: "4px 8px",
            cursor: "pointer",
            outline: "none",
            minWidth: "130px",
          }}
        >
          {countries.map((c) => (
            <option key={c} value={c}>
              {c === ALL ? "All countries" : c}
            </option>
          ))}
        </select>

        {/* Trend dropdown */}
        <select
          value={selectedTopic}
          onChange={(e) => setSelectedTopic(e.target.value)}
          aria-label="Filter by trend"
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            color: "var(--qgi-text)",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "4px",
            padding: "4px 8px",
            cursor: "pointer",
            outline: "none",
            minWidth: "130px",
          }}
        >
          {topics.map((tp) => (
            <option key={tp} value={tp}>
              {tp === ALL ? "All trends" : tp}
            </option>
          ))}
        </select>

        {/* Clear / reset */}
        {isFiltered && (
          <button
            onClick={reset}
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "11px",
              color: "var(--qgi-accent)",
              background: "transparent",
              border: "1px solid rgba(56,189,248,0.35)",
              borderRadius: "4px",
              padding: "4px 10px",
              cursor: "pointer",
            }}
          >
            Clear ×
          </button>
        )}

        {/* Active filter context pill */}
        {isFiltered && (
          <span
            style={{
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            {selectedCountry !== ALL && selectedTopic !== ALL
              ? `${selectedCountry} · ${selectedTopic}`
              : selectedCountry !== ALL
                ? selectedCountry
                : selectedTopic}
          </span>
        )}

        {/* Spacer pushes verdict key to the right */}
        <div style={{ flex: 1, minWidth: "8px" }} />

        {/* Verdict color key chips */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            flexWrap: "wrap",
          }}
        >
          {VERDICT_KEY.map(({ verdict, label }) => {
            const active = selectedVerdict === verdict;
            const anySelected = selectedVerdict !== null;
            return (
              <button
                key={verdict}
                type="button"
                onClick={() => setSelectedVerdict(active ? null : verdict)}
                aria-pressed={active}
                title={active ? "Show all verdicts" : `Show only ${label} cells`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "5px",
                  fontSize: "11px",
                  fontFamily: "ui-monospace, monospace",
                  color: active ? "var(--qgi-text)" : "var(--qgi-text-muted)",
                  background: active ? "rgba(91,126,153,0.15)" : "transparent",
                  border: active
                    ? `1px solid ${VERDICT_COLORS[verdict]}`
                    : "1px solid transparent",
                  borderRadius: "5px",
                  padding: "3px 8px",
                  cursor: "pointer",
                  opacity: anySelected && !active ? 0.45 : 1,
                  transition: "opacity 120ms ease, background 120ms ease",
                }}
              >
                <span
                  style={{
                    display: "inline-block",
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    background: VERDICT_COLORS[verdict],
                    flexShrink: 0,
                    opacity: verdict === "QUIET" ? 0.6 : 1,
                  }}
                />
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* The plot itself (header + controls above, quadrant guide below all
          share this same panel) */}
      <div
        role="img"
        aria-label="Signal landscape scatter: News Pressure (x) versus Structural Fair Value (y), one dot per country-trend."
        aria-describedby={isNarrow ? "landscape-yaxis-caption" : undefined}
      >
        {mounted ? (
          <ReactECharts
            option={option}
            style={{ height: isNarrow ? "400px" : "440px", width: "100%" }}
            opts={{ renderer: "svg" }}
          />
        ) : (
          // Reserve the chart's height before mount so the breakpoint-dependent
          // ECharts renders exactly once (no desktop to narrow margin flash / CLS).
          <div style={{ height: "440px", width: "100%" }} aria-hidden="true" />
        )}
      </div>
      {/* On narrow phones the y-axis name is suppressed to save space, so it is
          shown as a plain caption beneath the chart instead. */}
      {isNarrow && (
        <div
          id="landscape-yaxis-caption"
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
            textAlign: "center",
            marginTop: "2px",
            fontWeight: 600,
            letterSpacing: "0.2px",
          }}
        >
          ↑ Structural Fair Value for {new Date().getFullYear()} (%)
        </div>
      )}

      {/* Coming-soon trends: no cells to plot yet, so name them once, plainly. */}
      {comingSoonNote() && (
        <p
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            margin: "8px 0 0",
            lineHeight: 1.5,
          }}
        >
          {comingSoonNote()}
        </p>
      )}

      {/* Quadrant guide — what each corner means, in plain English. Laid out
            2x2 to mirror the plot (top = more structure, right = louder news). */}
      <div style={{ marginTop: "16px" }}>
        <div
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            marginBottom: "8px",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.5px",
          }}
        >
          What each Quadrant means
        </div>
        <div
          style={{
            display: "grid",
            // On phones <~320px two 1fr columns collapse gracefully;
            // minmax(150px,1fr) keeps 2 columns at ≥300px and stacks to 1 below that.
            gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
            gap: "10px",
          }}
        >
          <QuadCard
            tint="rgba(91,126,153,0.07)"
            accent="#5B7E99"
            title="Elevated & Quiet"
            count={quadCounts.silentAlarm}
            body="Structure high, news quiet — the two timeframes diverge."
          />
          <QuadCard
            tint="rgba(224,92,92,0.07)"
            accent="#E05C5C"
            title="Both Firing"
            count={quadCounts.bothFiring}
            body="Structure and news both high. The confirmed, active signals."
          />
          <QuadCard
            tint="rgba(91,126,153,0.03)"
            accent="var(--qgi-text-dim)"
            title="Quiet"
            count={quadCounts.quiet}
            body="Low on both. Off the radar this release."
          />
          <QuadCard
            tint="rgba(245,158,11,0.07)"
            accent="#f59e0b"
            title="News-Only"
            count={quadCounts.newsOnly}
            body="Loud news, thin structure. Coverage without a deep base yet."
          />
        </div>
      </div>
    </div>
  );
}

// ── QuadCard — a plain-English explainer for one plot quadrant ────────────────

function QuadCard({
  tint,
  accent,
  title,
  count,
  body,
}: {
  tint: string;
  accent: string;
  title: string;
  count: number;
  body: string;
}) {
  return (
    <div
      style={{
        background: tint,
        borderLeft: `3px solid ${accent}`,
        borderRadius: "4px",
        padding: "9px 11px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "7px",
          marginBottom: "3px",
        }}
      >
        <span
          style={{
            fontSize: "12px",
            fontWeight: 700,
            color: "var(--qgi-text)",
            whiteSpace: "nowrap",
          }}
        >
          {title}
        </span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            fontWeight: 700,
            color: accent,
          }}
        >
          {count}
        </span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            color: "var(--qgi-text-dim)",
            letterSpacing: "0.5px",
          }}
        >
          cells
        </span>
      </div>
      <div
        style={{
          fontSize: "11px",
          color: "var(--qgi-text-muted)",
          lineHeight: 1.4,
        }}
      >
        {body}
      </div>
    </div>
  );
}
