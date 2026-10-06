"use client";

/**
 * TopicBoard — the news-layer view of /risk-board (2026-06-10).
 *
 * The structural grid answers "which countries resemble which trends".
 * This view answers "which of those readings the news is confirming right
 * now". Each country x topic cell carries one of four verdicts:
 *   Both Firing     = structure primed AND news live   (act on it)
 *   News-Only       = news spike without structure     (often noise)
 *   Elevated & Quiet = structure primed, news quiet     (watch it)
 *   Quiet           = neither elevated
 *
 * Three reading lenses, one per audience (founder ask 2026-06-10):
 *   Scan    — the returning analyst's 10-second sweep (rank by active count)
 *   Surge   — the journalist's "what just changed" (rank by pulse jump)
 *   Primed & quiet — the risk professional's edge: structure says primed,
 *                    coverage has not arrived yet (rank by latent density)
 *
 * Plus a Map mode: the confirm/reject quadrant per topic, flags positioned
 * by structural resemblance x news pulse.
 *
 * Verdict colors ride the token system (no red, founder-ratified):
 * Both Firing=warning amber, News-Only=accent cyan, Elevated & Quiet=muted, Quiet=dim.
 */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { Route } from "next";
import dynamic from "next/dynamic";
import { ArrowUpRight } from "lucide-react";

// echarts only loads when the Map mode first mounts — keeps the ~300KB
// bundle off the default /risk-board path (review finding).
const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { InfoTooltip } from "@/components/design/InfoTooltip";
import { flagFor, iso2For } from "@/lib/te-mock/country-flags";
import { useTheme } from "@/lib/hooks/useTheme";
import { useMediaQuery } from "@/lib/hooks/useMediaQuery";
import { getEchartsTokens } from "@/lib/echarts-theme";
import type { HfBoard, HfCell, HfTopic, HfVerdict } from "@/lib/hf/topics-data";
import type { TrendBoard } from "@/lib/hf/trend-board";
import { GLOBAL_PERCENTILE_NOTE } from "@/lib/hf/news-scale";

/* ── Verdict presentation ────────────────────────────────────────────── */

const VERDICT_STYLE: Record<
  HfVerdict,
  { label: string; color: string; bg: string; border: string }
> = {
  ACTIVE: {
    label: "Both Firing",
    color: "var(--qgi-warning)",
    bg: "color-mix(in srgb, var(--qgi-warning) 13%, transparent)",
    border: "color-mix(in srgb, var(--qgi-warning) 50%, transparent)",
  },
  SIGNAL: {
    label: "News-Only",
    color: "var(--qgi-accent)",
    bg: "color-mix(in srgb, var(--qgi-accent) 12%, transparent)",
    border: "color-mix(in srgb, var(--qgi-accent) 50%, transparent)",
  },
  LATENT: {
    label: "Elevated & Quiet",
    color: "var(--qgi-text-muted)",
    bg: "var(--qgi-surface-2)",
    border: "var(--qgi-border)",
  },
  QUIET: {
    // Ghost pill, not bare text: keeps the four-state vocabulary structurally
    // identical while staying the visually quietest state (review finding).
    label: "Quiet",
    color: "var(--qgi-text-dim)",
    bg: "transparent",
    border: "color-mix(in srgb, var(--qgi-border) 70%, transparent)",
  },
};

type Lens = "scan" | "surge" | "primed";

const LENS_META: Record<Lens, { label: string; lede: string }> = {
  scan: {
    label: "Scan",
    lede: "Countries ranked by how many themes are active right now. The ten-second sweep.",
  },
  surge: {
    label: "Surge",
    lede: "Ranked by the biggest jump in news pulse since last month. What the world started talking about.",
  },
  primed: {
    label: "Primed & quiet",
    lede: "The Elevated & Quiet readings: structure elevated, news quiet. The conditions are in place while coverage stays light.",
  },
};

interface Props {
  data: TrendBoard;
}

export function TopicBoard({ data }: Props) {
  const [lens, setLensState] = useState<Lens>("scan");
  const [mode, setModeState] = useState<"grid" | "map">("grid");
  // Empty default: QuadrantMap falls back to its first (live) topic, so this
  // never needs to know a live trend's id up front.
  const [mapTopic, setMapTopic] = useState<string>("");

  // Remember the last lens + view between sessions (persona ask). The rAF
  // defer follows the Sidebar's localStorage-sync idiom.
  useEffect(() => {
    const raf = requestAnimationFrame(() => {
      try {
        const l = localStorage.getItem("qgi-topics-lens");
        if (l === "scan" || l === "surge" || l === "primed") setLensState(l);
        if (localStorage.getItem("qgi-topics-mode") === "map") setModeState("map");
      } catch {
        // localStorage blocked; defaults stand.
      }
    });
    return () => cancelAnimationFrame(raf);
  }, []);
  const setLens = (l: Lens) => {
    setLensState(l);
    try {
      localStorage.setItem("qgi-topics-lens", l);
    } catch {}
  };
  const setMode = (m: "grid" | "map") => {
    setModeState(m);
    try {
      localStorage.setItem("qgi-topics-mode", m);
    } catch {}
  };

  const topics = data.boardTopics;
  // The 3 curated "coming soon" columns (no cells yet); the rest render live.
  const comingSoon = new Set(data.comingSoon);
  const liveTopics = topics.filter((t) => !comingSoon.has(t.id));
  // The Quadrant map needs a structural (y) axis, so it further drops any
  // news-only live trend (e.g. labor_action) whose struct reads null for
  // every country. A data-driven check, not a hardcoded slug list, so it
  // keeps working if the news-only set changes.
  const mapTopics = liveTopics.filter((t) =>
    data.countries.some((c) => (data.cells[`${c.iso3}|${t.id}`]?.struct ?? null) !== null)
  );

  // One row per country: cells in topic order + per-lens rank metrics.
  const rows = useMemo(() => {
    return data.countries.map((country) => {
      const cells = topics.map((t) => data.cells[`${country.iso3}|${t.id}`] ?? null);
      const activeCount = cells.filter((c) => c?.verdict === "ACTIVE").length;
      const latentCount = cells.filter((c) => c?.verdict === "LATENT").length;
      const pulseSum = cells.reduce((s, c) => s + (c?.pulse ?? 0), 0);
      const structSum = cells.reduce((s, c) => s + (c?.struct ?? 0), 0);
      // Finite sentinel, not -Infinity: a country whose every cell lacks a
      // prior month (a new entrant) would otherwise make the Surge comparator
      // return NaN ((-Inf)-(-Inf)) and scramble the sort.
      const deltas = cells.flatMap((c) =>
        c && c.prevPulse !== null ? [c.pulse - c.prevPulse] : []
      );
      const maxDelta = deltas.length ? Math.max(...deltas) : Number.MIN_SAFE_INTEGER;
      return { country, cells, activeCount, latentCount, pulseSum, structSum, maxDelta };
    });
  }, [data, topics]);

  const sortedRows = useMemo(() => {
    const r = [...rows];
    if (lens === "surge")
      r.sort((a, b) => b.maxDelta - a.maxDelta || b.pulseSum - a.pulseSum);
    else if (lens === "primed")
      r.sort(
        (a, b) =>
          b.latentCount - a.latentCount ||
          b.structSum - a.structSum ||
          b.pulseSum - a.pulseSum
      );
    // Third tiebreak (structSum / pulseSum) keeps the long cold tail meaningfully
    // ordered at 30 rows instead of falling back to insertion order.
    else
      r.sort(
        (a, b) =>
          b.activeCount - a.activeCount ||
          b.pulseSum - a.pulseSum ||
          b.structSum - a.structSum
      );
    return r;
  }, [rows, lens]);

  // Hero: the strongest combined reading this month. Validated topics first;
  // tiebreak on the WEAKEST leg (min of struct/pulse) so "combined" means
  // combined, not just loudest news (review finding).
  const hero = useMemo(() => {
    type Hero = { country: HfBoard["countries"][number]; topic: HfTopic; cell: HfCell };
    const legs = (c: HfCell) => Math.min(c.struct ?? 0, c.pulse);
    let best: Hero | null = null;
    for (const row of rows) {
      for (let i = 0; i < topics.length; i++) {
        const t = topics[i];
        const c = row.cells[i];
        if (!c || c.verdict !== "ACTIVE") continue;
        const beats =
          best === null ||
          (t.validated && !best.topic.validated) ||
          (t.validated === best.topic.validated && legs(c) > legs(best.cell));
        if (beats) best = { country: row.country, topic: t, cell: c };
      }
    }
    return best;
  }, [rows, topics]);

  const gridTemplate = `200px repeat(${topics.length}, minmax(0, 1fr)) 72px`;

  return (
    <div>
      {/* Intro — the one tab-appropriate sentence under the page h1 (the
          review's P0: the old static page copy described trend rows while
          this view shows country rows). No second heading. */}
      <div
        style={{
          color: "var(--qgi-text-muted)",
          fontSize: "15px",
          lineHeight: 1.6,
          maxWidth: "820px",
          margin: "0 0 16px",
        }}
      >
        Each cell combines a country&apos;s structural resemblance
        <InfoTooltip text="How closely the country's long-run indicators resemble the shape that ran ahead of this kind of event in the past, from 0 to 100. 60 and above counts as elevated." />{" "}
        with its monthly news pulse
        <InfoTooltip text="How much of this country's news coverage is on this theme, from 0 to 100, ranked across every covered country and month. 60 and above counts as elevated." />{" "}
        into a single reading. Scan a row for which themes are running hot, or a column
        for which countries are drawing attention on one theme.
      </div>

      {/* Hero: strongest combined reading */}
      {hero && mode === "grid" && (
        <HeroStrip hero={hero} linkable={hero.country.linkable} />
      )}

      {/* Controls: lenses + grid/map switch */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "10px",
          marginBottom: "8px",
        }}
      >
        {/* Lenses only apply to the grid; hiding them in Map mode avoids a
            selected-but-inert control (review finding). */}
        <div
          style={{
            display: "flex",
            gap: "5px",
            visibility: mode === "grid" ? "visible" : "hidden",
          }}
        >
          {(Object.keys(LENS_META) as Lens[]).map((l) => {
            const active = lens === l;
            return (
              <button
                key={l}
                type="button"
                onClick={() => setLens(l)}
                style={{
                  fontSize: "10.5px",
                  padding: "5px 11px",
                  background: active ? "var(--qgi-accent)" : "transparent",
                  color: active ? "var(--qgi-bg)" : "var(--qgi-text-muted)",
                  border: `1px solid ${active ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
                  borderRadius: "4px",
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: "0.4px",
                  cursor: "pointer",
                }}
              >
                {LENS_META[l].label}
              </button>
            );
          })}
        </div>
        <span style={{ flex: 1 }} />
        <div style={{ display: "flex", gap: "5px" }}>
          {(["grid", "map"] as const).map((m) => {
            const active = mode === m;
            return (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                style={{
                  fontSize: "10.5px",
                  padding: "5px 11px",
                  background: active ? "var(--qgi-surface-2)" : "transparent",
                  color: active ? "var(--qgi-text)" : "var(--qgi-text-dim)",
                  border: `1px solid ${active ? "var(--qgi-text-dim)" : "var(--qgi-border)"}`,
                  borderRadius: "4px",
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: "0.4px",
                  cursor: "pointer",
                  textTransform: "capitalize",
                }}
              >
                {m === "grid" ? "Grid" : "Quadrant"}
              </button>
            );
          })}
        </div>
      </div>

      {/* Lens lede */}
      {mode === "grid" && (
        <p
          style={{
            color: "var(--qgi-text-dim)",
            fontSize: "12.5px",
            margin: "0 0 12px",
            lineHeight: 1.5,
          }}
        >
          {LENS_META[lens].lede}{" "}
          <span style={{ color: "var(--qgi-text-muted)" }}>{GLOBAL_PERCENTILE_NOTE}</span>
        </p>
      )}

      {mode === "grid" ? (
        <VerdictGrid
          topics={topics}
          comingSoon={comingSoon}
          rows={sortedRows}
          lens={lens}
          gridTemplate={gridTemplate}
          history={data.history}
        />
      ) : (
        <QuadrantMap
          data={data}
          topics={mapTopics}
          mapTopic={mapTopic}
          onTopic={setMapTopic}
        />
      )}

      {/* Verdict labels already render on every cell, so the legend row that
          used to repeat them below the board was dropped (Topics->Trends
          migration cleanup, 2026-07-04); the methodology link stands alone. */}
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "14px" }}>
        <Link
          href={"/methodology#news-layer" as Route}
          target="_blank"
          rel="noopener"
          style={{
            color: "var(--qgi-accent)",
            textDecoration: "none",
            fontSize: "11.5px",
          }}
        >
          How verdicts are assigned →
        </Link>
      </div>

      {/* Footer note (matches the structural footer idiom) */}
      <div
        style={{
          marginTop: "12px",
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.3px",
        }}
      >
        Covering {data.countries.length} countries across {liveTopics.length} live trends
        today; {comingSoon.size} more are tracked with feeds pending. Pulse updates
        monthly; structural scores refresh each release.
      </div>
    </div>
  );
}

/* ── Hero strip ──────────────────────────────────────────────────────── */

function HeroStrip({
  hero,
  linkable,
}: {
  hero: {
    country: { name: string; iso3: string };
    topic: HfTopic;
    cell: HfCell;
  };
  linkable: boolean;
}) {
  const body = (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "12px",
        padding: "12px 16px",
        marginBottom: "14px",
        border: "1px solid color-mix(in srgb, var(--qgi-warning) 40%, transparent)",
        background: "color-mix(in srgb, var(--qgi-warning) 6%, transparent)",
        borderRadius: "8px",
        flexWrap: "wrap",
      }}
    >
      <span
        style={{
          fontSize: "10px",
          letterSpacing: "2px",
          textTransform: "uppercase",
          color: "var(--qgi-warning)",
          fontFamily: "ui-monospace, monospace",
          flexShrink: 0,
        }}
      >
        This month
      </span>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "7px",
          fontSize: "13.5px",
          color: "var(--qgi-text)",
          fontWeight: 600,
        }}
      >
        <FlagImg
          emoji={flagFor(hero.country.name)}
          name={hero.country.name}
          width={16}
          radius={2}
        />
        {hero.country.name} · {hero.topic.label}
      </span>
      <span style={{ fontSize: "12.5px", color: "var(--qgi-text-muted)" }}>
        is the strongest combined reading: structural {Math.round(hero.cell.struct ?? 0)},
        news pulse {Math.round(hero.cell.pulse)}.
      </span>
      {linkable && (
        <span
          style={{
            marginLeft: "auto",
            color: "var(--qgi-warning)",
            display: "inline-flex",
            alignItems: "center",
            gap: "3px",
            fontSize: "11.5px",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          Open {hero.country.name}
          <ArrowUpRight size={12} strokeWidth={2} />
        </span>
      )}
    </div>
  );
  return linkable ? (
    <Link
      href={`/countries/${hero.country.iso3.toLowerCase()}` as Route}
      style={{ textDecoration: "none", color: "inherit", display: "block" }}
    >
      {body}
    </Link>
  ) : (
    body
  );
}

/* ── Verdict grid ────────────────────────────────────────────────────── */

/** Per-lens summary column: header label + the row figure that explains the
 *  ranking, so the rightmost column always answers the active lens's
 *  question (review finding). */
const SUMMARY_HEADER: Record<Lens, string> = {
  scan: "Both Firing",
  surge: "Jump",
  primed: "Primed",
};

const SUMMARY_TOOLTIP: Record<Lens, string> = {
  scan: "How many of this country's themes read Both Firing right now: structure primed and news running together.",
  surge:
    "This country's biggest single-theme rise in news pulse versus last month, in points on the 0 to 100 pulse scale.",
  primed:
    "How many themes read Elevated & Quiet: structure elevated while the news stays quiet.",
};

function VerdictGrid({
  topics,
  comingSoon,
  rows,
  lens,
  gridTemplate,
  history,
}: {
  topics: HfTopic[];
  /** Ids of the curated "coming soon" columns (no cells yet). */
  comingSoon: Set<string>;
  rows: Array<{
    country: { name: string; iso3: string; linkable: boolean };
    cells: Array<HfCell | null>;
    activeCount: number;
    latentCount: number;
    maxDelta: number;
  }>;
  lens: Lens;
  gridTemplate: string;
  history: HfBoard["history"];
}) {
  // Below 1024px the trend matrix can't fit a phone, so it scrolls
  // horizontally inside a clip frame; the header can't be page-sticky there
  // (an overflow-x:auto ancestor breaks sticky-to-page). On desktop we keep
  // main's design: overflow:visible container + a page-sticky header so the
  // trend columns stay labelled while scrolling 30 country rows.
  const isMobile = useMediaQuery("(max-width: 1023px)");
  const headerSticky: React.CSSProperties = isMobile
    ? {}
    : {
        position: "sticky",
        top: 0, // visual QA: bump to the sticky-nav height if one is added
        zIndex: 10,
        // The container's overflow is "visible" (for sticky), so the header
        // rounds its own top corners to match the 8px card.
        borderRadius: "8px 8px 0 0",
      };

  const matrix = (
    <>
      {/* Header — page-sticky on desktop so topic columns stay labelled. */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: gridTemplate,
          background: "var(--qgi-bg)",
          borderBottom: "1px solid var(--qgi-border)",
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          letterSpacing: "1px",
          color: "var(--qgi-text-dim)",
          ...headerSticky,
        }}
      >
        <div style={{ padding: "10px 14px", borderRight: "1px solid var(--qgi-border)" }}>
          Country ↓ · Trend →
        </div>
        {topics.map((t) => {
          const soon = comingSoon.has(t.id);
          return (
            <div
              key={t.id}
              style={{
                padding: "8px 6px",
                textAlign: "center",
                borderRight: "1px solid var(--qgi-border)",
                lineHeight: 1.4,
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  flexWrap: "wrap",
                  justifyContent: "center",
                  alignItems: "center",
                  gap: "2px 5px",
                  color: soon ? "var(--qgi-text-dim)" : "var(--qgi-text-muted)",
                }}
              >
                {/* No whiteSpace: nowrap here: 9 narrower columns + multi-word
                    trend names (e.g. "Migration & Refugees") need to wrap
                    instead of overrunning the next column (QA finding,
                    Topics->Trends migration). */}
                {t.label}
                {soon ? (
                  <>
                    <SoonPill />
                    <InfoTooltip text={`${t.name}: tracked, feed pending.`} />
                  </>
                ) : (
                  <InfoTooltip
                    text={`${t.name}. Tracked and scored; validation against the event record is ongoing.`}
                  />
                )}
              </span>
            </div>
          );
        })}
        <div style={{ padding: "10px 6px", textAlign: "center" }}>
          {SUMMARY_HEADER[lens]}
          <InfoTooltip text={SUMMARY_TOOLTIP[lens]} />
        </div>
      </div>

      {/* Rows */}
      {rows.map((row, ri) => (
        <div
          key={row.country.iso3}
          style={{
            display: "grid",
            gridTemplateColumns: gridTemplate,
            borderBottom: ri === rows.length - 1 ? "none" : "1px solid var(--qgi-border)",
          }}
        >
          <CountryNameCell country={row.country} />
          {row.cells.map((cell, ci) => (
            <TopicCell
              key={topics[ci].id}
              cell={cell}
              lens={lens}
              country={row.country}
              topic={topics[ci]}
              comingSoon={comingSoon.has(topics[ci].id)}
              spark={history[`${row.country.iso3}|${topics[ci].id}`]?.pulse}
            />
          ))}
          <SummaryCell lens={lens} row={row} />
        </div>
      ))}
    </>
  );

  if (isMobile) {
    // Mobile (<1024px): horizontal-scroll the matrix inside a rounded clip
    // frame (the trend columns don't fit a phone). Header is not page-sticky
    // here.
    return (
      <>
        <div
          style={{
            border: "1px solid var(--qgi-border)",
            borderRadius: "8px",
            background: "var(--qgi-surface)",
            overflow: "hidden",
          }}
        >
          <div style={{ overflowX: "auto" }}>
            {/* min-width so the scroller always has content wider than a phone.
                200px label + trends × 44px + 72px summary. */}
            <div style={{ minWidth: `${200 + topics.length * 44 + 72}px` }}>{matrix}</div>
          </div>
        </div>
        <p
          className="lg:hidden"
          style={{
            margin: "8px 2px 0",
            fontSize: "11px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text-dim)",
            textAlign: "center",
          }}
        >
          ← scroll sideways to see all trends →
        </p>
      </>
    );
  }

  // Desktop (>=1024px): main's design — overflow:visible so the header can be
  // page-sticky while scrolling 30 country rows. The trend columns fit; no
  // h-scroll.
  return (
    <div
      style={{
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        background: "var(--qgi-surface)",
        overflow: "visible",
      }}
    >
      {matrix}
    </div>
  );
}

function SummaryCell({
  lens,
  row,
}: {
  lens: Lens;
  row: { activeCount: number; latentCount: number; maxDelta: number };
}) {
  let text: string;
  let color: string;
  if (lens === "surge") {
    const hasDelta = row.maxDelta > Number.MIN_SAFE_INTEGER;
    text = hasDelta ? `${row.maxDelta >= 0 ? "+" : ""}${Math.round(row.maxDelta)}` : "·";
    color =
      hasDelta && row.maxDelta >= 5
        ? "var(--qgi-warning)"
        : hasDelta && row.maxDelta <= -5
          ? "var(--qgi-success)"
          : "var(--qgi-text-dim)";
  } else if (lens === "primed") {
    text = row.latentCount ? String(row.latentCount) : "·";
    color = row.latentCount > 0 ? "var(--qgi-text-muted)" : "var(--qgi-text-dim)";
  } else {
    text = row.activeCount ? String(row.activeCount) : "·";
    color = row.activeCount > 0 ? "var(--qgi-warning)" : "var(--qgi-text-dim)";
  }
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "ui-monospace, monospace",
        fontSize: "13px",
        fontWeight: 700,
        color,
      }}
    >
      {text}
    </div>
  );
}

function CountryNameCell({
  country,
}: {
  country: { name: string; iso3: string; linkable: boolean };
}) {
  const inner = (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "10px 14px",
        borderRight: "1px solid var(--qgi-border)",
        height: "100%",
        fontSize: "12.5px",
        fontWeight: 600,
        color: "var(--qgi-text)",
      }}
    >
      <FlagImg emoji={flagFor(country.name)} name={country.name} width={16} radius={2} />
      <span
        style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
      >
        {country.name}
      </span>
    </div>
  );
  return country.linkable ? (
    <Link
      href={`/countries/${country.iso3.toLowerCase()}` as Route}
      style={{ textDecoration: "none", color: "inherit" }}
    >
      {inner}
    </Link>
  ) : (
    // Visually distinct from linked peers + says why (QA finding: identical
    // styling with no affordance difference read as broken links).
    <span
      title={`${country.name}: country profile coming soon. The news readings are live.`}
      style={{ opacity: 0.75, cursor: "help" }}
    >
      {inner}
    </span>
  );
}

/** Small, quiet chip for the 3 curated "coming soon" trend columns. */
function SoonPill() {
  return (
    <span
      aria-hidden="true"
      style={{
        fontSize: "8.5px",
        padding: "1px 6px",
        borderRadius: "3px",
        background: "color-mix(in srgb, var(--qgi-accent-dim) 10%, transparent)",
        border: "1px dashed var(--qgi-text-dim)",
        color: "var(--qgi-text-dim)",
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.5px",
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      Soon
    </span>
  );
}

function TopicCell({
  cell,
  lens,
  country,
  topic,
  spark,
  comingSoon = false,
}: {
  cell: HfCell | null;
  lens: Lens;
  country: { name: string; iso3: string; linkable: boolean };
  topic: HfTopic;
  spark?: number[];
  /** Curated "coming soon" column: no cell will ever arrive here yet. */
  comingSoon?: boolean;
}) {
  if (comingSoon) {
    // Quiet placeholder, not a dash: reads as "tracked, feed pending" rather
    // than "missing data" (review finding, Topics->Trends migration).
    const label = `${topic.label}: tracked, feed pending.`;
    return (
      <div
        title={label}
        role="note"
        aria-label={label}
        style={{
          padding: "7px 8px",
          borderRight: "1px solid var(--qgi-border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "56px",
          opacity: 0.4,
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: "5px",
            height: "5px",
            borderRadius: "50%",
            background: "var(--qgi-text-dim)",
          }}
        />
      </div>
    );
  }
  if (!cell) {
    return (
      <div
        style={{
          padding: "8px",
          borderRight: "1px solid var(--qgi-border)",
          color: "var(--qgi-text-dim)",
          fontSize: "11px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        –
      </div>
    );
  }
  const vs = VERDICT_STYLE[cell.verdict];
  const delta = cell.prevPulse !== null ? cell.pulse - cell.prevPulse : null;
  // Lens emphasis lives on the CELL BACKGROUND, never the pill: verdict
  // pills keep constant weight and color in every lens so the legend's
  // promise holds (review finding). Primed & quiet highlights its
  // Elevated & Quiet cells with a soft surface tint.
  const emphasized = lens === "primed" && cell.verdict === "LATENT";

  const title = `${country.name} · ${topic.label}: structural ${Math.round(cell.struct ?? 0)}, news pulse ${Math.round(cell.pulse)}${
    delta !== null ? ` (${delta >= 0 ? "+" : ""}${Math.round(delta)} vs last month)` : ""
  }. ${vs.label}.`;

  return (
    // Focusable with an accessible name so the numbers behind the verdict
    // reach keyboard and screen-reader users, not just mouse hover (title).
    <div
      title={title}
      role="note"
      aria-label={title}
      tabIndex={0}
      style={{
        padding: "7px 8px",
        borderRight: "1px solid var(--qgi-border)",
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        alignItems: "center",
        justifyContent: "center",
        background: emphasized ? "var(--qgi-surface-2)" : "transparent",
        transition: "background 140ms ease-out",
        minHeight: "56px",
      }}
    >
      <span
        style={{
          fontSize: "11px",
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
        {vs.label}
      </span>
      {lens === "surge" && delta !== null ? (
        <span
          style={{
            fontSize: "11px",
            fontFamily: "ui-monospace, monospace",
            color:
              delta >= 5
                ? "var(--qgi-warning)"
                : delta <= -5
                  ? "var(--qgi-success)"
                  : "var(--qgi-text-dim)",
          }}
        >
          {delta >= 0 ? "+" : ""}
          {Math.round(delta)}
        </span>
      ) : (
        spark && <Sparkline points={spark.slice(-12)} color={vs.color} />
      )}
    </div>
  );
}

/** Tiny inline pulse sparkline (last 12 months, 0-100 scale). */
function Sparkline({ points, color }: { points: number[]; color: string }) {
  if (points.length < 2) return null;
  const w = 44;
  const h = 12;
  const step = w / (points.length - 1);
  const path = points
    .map((p, i) => `${(i * step).toFixed(1)},${(h - (p / 100) * h).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={w} height={h} aria-hidden="true" style={{ opacity: 0.65 }}>
      <polyline
        points={path}
        fill="none"
        stroke={color}
        strokeWidth="1.2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/* ── Quadrant map (per-topic scatter) ────────────────────────────────── */

function QuadrantMap({
  data,
  topics,
  mapTopic,
  onTopic,
}: {
  data: HfBoard;
  topics: HfTopic[];
  mapTopic: string;
  onTopic: (id: string) => void;
}) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);
  const router = useRouter();
  const topic = topics.find((x) => x.id === mapTopic) ?? topics[0];

  const points = data.countries
    .map((c) => {
      const cell = data.cells[`${c.iso3}|${topic.id}`];
      if (!cell || cell.struct === null) return null;
      const iso2 = iso2For(c.name);
      const verdictColor =
        cell.verdict === "ACTIVE"
          ? t.warning
          : cell.verdict === "SIGNAL"
            ? t.accent
            : cell.verdict === "LATENT"
              ? t.textMuted
              : t.textDim;
      return {
        name: c.name,
        href: c.linkable ? `/countries/${c.iso3.toLowerCase()}` : null,
        // x = news pulse, y = structural resemblance (matches the X-card orientation).
        value: [cell.pulse, cell.struct],
        verdict: cell.verdict,
        symbol:
          iso2 && /^[a-z]{2}$/.test(iso2)
            ? `image://https://flagcdn.com/28x21/${iso2}.png`
            : "circle",
        symbolSize: [24, 18],
        label: {
          show: true,
          position: "bottom" as const,
          color: verdictColor,
          fontSize: 10.5,
          formatter: c.name,
        },
      };
    })
    .filter(Boolean);

  const th = data.thresholds;
  // Derive the structural (y) floor from the data (10-step, capped at 30) so a
  // future low-structure country can never be silently clipped off the canvas.
  const structVals = points.map((p) => p!.value[1] as number);
  const structMin = Math.min(
    30,
    Math.max(0, Math.floor((Math.min(...structVals) - 5) / 10) * 10)
  );

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      // Render on document.body so the popup can never be squeezed or cut
      // at a panel border (founder catch 2026-06-11; ECharts analog of the
      // #567 InfoTooltip position:fixed fix).
      appendToBody: true,
      confine: true,
      backgroundColor: t.surface2,
      borderColor: t.border,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (p: { data: { name: string; value: number[]; verdict: HfVerdict } }) =>
        `<b>${p.data.name}</b><br/>structural ${Math.round(p.data.value[1])} · news pulse ${Math.round(
          p.data.value[0]
        )}<br/>${VERDICT_STYLE[p.data.verdict].label}`,
    },
    grid: { left: 56, right: 28, top: 30, bottom: 46 },
    xAxis: {
      min: 0,
      max: 100,
      name: "How Loud The News Is",
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: { color: t.textDim, fontSize: 10, letterSpacing: 1.5 },
      axisLine: { lineStyle: { color: t.border } },
      // Minor gridlines off: the 60/60 threshold lines ARE the read of this
      // chart and must be the only interior lines (review finding).
      splitLine: { show: false },
      axisLabel: { color: t.textMuted, fontSize: 10.5 },
    },
    yAxis: {
      min: structMin,
      max: 100,
      name: "Resemblance To Historical Cases",
      nameLocation: "middle",
      nameGap: 36,
      nameTextStyle: { color: t.textDim, fontSize: 10, letterSpacing: 1.5 },
      axisLine: { lineStyle: { color: t.border } },
      splitLine: { show: false },
      axisLabel: { color: t.textMuted, fontSize: 10.5 },
    },
    graphic: [
      quadLabel(0.97, 0.06, "Both Firing", t.warning, "right"),
      quadLabel(0.08, 0.06, "Elevated & Quiet", t.textMuted, "left"),
      quadLabel(0.97, 0.84, "News-Only", t.accent, "right"),
      quadLabel(0.08, 0.84, "Quiet", t.textDim, "left"),
    ],
    series: [
      {
        type: "scatter",
        data: points,
        // Persona panel: the flags begged to be clicked. Pointer cursor +
        // click-through to the country profile (linkable countries only).
        cursor: "pointer",
        // Shift colliding country labels apart instead of letting them
        // overprint (review finding: NigeriaThailand ran together). shiftXY
        // (not shiftY) so 30 flags clustering in the Both Firing corner can
        // spread on both axes.
        labelLayout: { moveOverlap: "shiftXY" as const },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: t.textDim, type: "dashed", width: 1.2 },
          label: { show: false },
          data: [{ xAxis: th.pulse }, { yAxis: th.struct }],
        },
      },
    ],
  };

  return (
    <div
      style={{
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        background: "var(--qgi-surface)",
        padding: "14px",
      }}
    >
      {/* Topic chips */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "5px", marginBottom: "8px" }}>
        {topics.map((x) => {
          const active = x.id === topic.id;
          return (
            <button
              key={x.id}
              type="button"
              onClick={() => onTopic(x.id)}
              style={{
                fontSize: "11px",
                padding: "4px 10px",
                background: active ? "var(--qgi-surface-2)" : "transparent",
                color: active ? "var(--qgi-text)" : "var(--qgi-text-muted)",
                border: `1px solid ${active ? "var(--qgi-text-dim)" : "var(--qgi-border)"}`,
                borderRadius: "12px",
                fontFamily: "ui-monospace, monospace",
                cursor: "pointer",
              }}
            >
              {x.label}
            </button>
          );
        })}
      </div>
      <p
        style={{
          color: "var(--qgi-text-dim)",
          fontSize: "12px",
          margin: "0 0 4px",
          lineHeight: 1.5,
        }}
      >
        <span style={{ color: "var(--qgi-warning)" }}>Both Firing</span>
        {" = both elevated · "}
        <span style={{ color: "var(--qgi-accent)" }}>News-Only</span>
        {" = news without structure · "}
        <span style={{ color: "var(--qgi-text-muted)" }}>Elevated & Quiet</span>
        {" = structure without news · "}
        <span style={{ color: "var(--qgi-text-dim)" }}>Quiet</span>
        {" = neither."}
      </p>
      <ReactECharts
        option={option}
        onEvents={{
          click: (p: { data?: { href?: string | null } }) => {
            if (p.data?.href) router.push(p.data.href as Route);
          },
        }}
        style={{ height: "520px", width: "100%" }}
      />
    </div>
  );
}

function quadLabel(
  xr: number,
  yr: number,
  text: string,
  fill: string,
  align: "left" | "right"
) {
  return {
    type: "text" as const,
    left: align === "left" ? `${xr * 100}%` : undefined,
    right: align === "right" ? `${(1 - xr) * 100}%` : undefined,
    top: `${yr * 100}%`,
    // fontSize trimmed from 12 to 11 (was sized for "Active"/"Signal"; the
    // canonical labels run longer, e.g. "Elevated & Quiet").
    style: { text, fill, fontSize: 11, fontWeight: "bold" as const },
    z: 1,
  };
}
