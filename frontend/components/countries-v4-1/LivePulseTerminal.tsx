"use client";

/**
 * LivePulseTerminal — the per-country PRO TERMINAL (full-screen takeover).
 *
 * A QGI × TradingView terminal that matches the founder's `qgi-console/pulse.html`
 * (:8761) prototype: a single CSS grid filling the viewport —
 *   header (back · logo · live GDELT stamp · UTC clock)
 *   rail (country switcher + 14 topic chips)  |  stage (verdict + chart + timeframe
 *   + Topic→Trends crosswalk)  |  sidebar (LIVE NEWS flow)
 *   status (data-provenance honesty line)
 *
 * Density-first, no app chrome. Everything real: run-2 structural resemblance ×
 * the monthly news pulse (2015→present), with the live GDELT feed for the three
 * live topics (Conflict · Protest · Economic distress). The other eleven are
 * history-only today and say so.
 *
 * Mobile layout (<1024px): stacked vertical flow instead of the 3-column grid.
 * Desktop (>=1024px): original layout unchanged.
 */

import { useEffect, useMemo, useState } from "react";
import { useResponsiveLayout } from "@/lib/hooks/useMediaQuery";
import dynamic from "next/dynamic";
import Link from "next/link";
import type { Route } from "next";
import { useTheme } from "@/lib/hooks/useTheme";
import { getEchartsTokens } from "@/lib/echarts-theme";
import type { HfVerdict } from "@/lib/hf/topics-data";
import type { HfCountryDetail, HfTopicSeries } from "@/lib/hf/pulse-detail";
import type {
  LivePulseSeriesData,
  LiveArticle,
  Resolution,
} from "@/lib/hf/live-pulse-series";
import { LivePulseStamp } from "@/components/hf/LivePulseStamp";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { HowToReadButton } from "@/components/te-v4-shared/HowToReadButton";
import { ExplainTip } from "@/components/design/ExplainTip";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

/* ── identity ────────────────────────────────────────────────────────── */

interface RailCountry {
  name: string;
  iso3: string;
  param: string;
}

// The three topics with a real hourly GDELT feed today (founder 2026-06-13).
// The other eleven are validated 11-year history only.
const LIVE_TOPICS: ReadonlySet<string> = new Set(["T02", "T05", "T06"]);

const ALL_RES: Resolution[] = ["1H", "4H", "1D", "1W", "1M"];
const RES_LABEL: Record<Resolution, string> = {
  "1H": "1H",
  "4H": "4H",
  "1D": "1D",
  "1W": "1W",
  "1M": "1M",
};

type Mode = "history" | "live";

const VERDICT_LABEL: Record<HfVerdict, string> = {
  ACTIVE: "▲ ACTIVE",
  SIGNAL: "⚡ SIGNAL",
  LATENT: "◉ LATENT",
  QUIET: "· QUIET",
};

// No red (V4.1): negative news tone reads amber, not alarm-red.
function verdictVar(v: HfVerdict): string {
  return v === "ACTIVE"
    ? "var(--qgi-warning)"
    : v === "SIGNAL"
      ? "var(--qgi-accent)"
      : v === "LATENT"
        ? "var(--qgi-text-muted)"
        : "var(--qgi-text-dim)";
}

function pretty(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bAnd\b/g, "&");
}

/* ── news headline from a GKG url (ported from the prototype) ──────────── */

const GENERIC: ReadonlySet<string> = new Set([
  "news",
  "world",
  "international",
  "national",
  "article",
  "articles",
  "story",
  "stories",
  "amp",
  "live",
  "updates",
  "update",
  "index",
  "home",
  "category",
  "politics",
  "business",
  "opinion",
  "video",
  "photos",
  "gallery",
  "breaking",
  "latest",
  "en",
  "ar",
  "section",
  "content",
  "web",
  "wire",
  "node",
]);

function hasVowel(t: string): boolean {
  return /[aeiou]/i.test(t);
}
function junkTok(t: string): boolean {
  if (/^\d{1,4}$/.test(t)) return false;
  const digits = (t.match(/\d/g) || []).length;
  if (t.length >= 16) return true;
  if (digits && digits / t.length > 0.4) return true;
  if (t.length >= 7 && !hasVowel(t)) return true;
  if (/^[0-9a-f]{6,}$/i.test(t)) return true;
  return false;
}
function wordsFrom(slug: string): { kept: string[]; real: string[] } {
  const s = slug.replace(/\.(html?|php|aspx?|ece|cms|amp|stm)$/i, "");
  const kept = s
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .filter((t) => !junkTok(t));
  while (kept.length && /^\d+$/.test(kept[0])) kept.shift();
  while (kept.length && /^\d+$/.test(kept[kept.length - 1])) kept.pop();
  const real = kept.filter((t) => /[A-Za-z]/.test(t) && hasVowel(t) && t.length >= 2);
  return { kept, real };
}
function deriveTitle(url: string, domain: string, topicLabel: string): string {
  let path = (url || "").split("?")[0].split("#")[0];
  if (domain && path.indexOf(domain) >= 0) path = path.split(domain)[1] || "";
  const segs = path.split("/").filter((s) => s && !GENERIC.has(s.toLowerCase()));
  for (let i = segs.length - 1; i >= 0; i--) {
    const w = wordsFrom(segs[i]);
    if (w.real.length >= 3) {
      return w.kept
        .join(" ")
        .replace(/\b\w/g, (c) => c.toUpperCase())
        .slice(0, 96);
    }
  }
  const dom = (domain || "source").replace(/^www\./, "").split(".")[0];
  return dom.charAt(0).toUpperCase() + dom.slice(1) + " · " + (topicLabel || "report");
}

function fmtStamp(dt: string): string {
  if (!dt || dt.length < 12) return "";
  const mo = [
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
  const m = parseInt(dt.slice(4, 6), 10) - 1;
  return `${mo[m] ?? "?"} ${dt.slice(6, 8)} · ${dt.slice(8, 10)}:${dt.slice(10, 12)}`;
}

/* ── component ───────────────────────────────────────────────────────── */

export function LivePulseTerminal({
  detail,
  seriesData,
  articles: articlesProp,
  countries,
  backHref,
  backLabel,
}: {
  detail: HfCountryDetail;
  seriesData: LivePulseSeriesData | null;
  /** Live article feed fetched independently of the series shell. Falls back
   *  to seriesData.articles when absent, then to []. This decoupling ensures
   *  the news rail is always populated even on countries that have articles
   *  but no committed live-pulse series JSON yet. */
  articles?: LiveArticle[];
  countries: RailCountry[];
  backHref: string;
  backLabel: string;
}) {
  // Open on a live topic if this country carries one, else the strongest board
  // reading (validated first, weakest leg).
  const initial = useMemo(() => {
    const live = detail.series.find((s) => LIVE_TOPICS.has(s.topic.id) && s.cell);
    if (live) return live.topic.id;
    let best: HfTopicSeries | null = null;
    // Weakest leg of the two readings; a null structural shouldn't read as 0
    // (that would always sink a pulse-only topic below a structural one).
    const legs = (s: HfTopicSeries) =>
      s.cell
        ? s.cell.struct !== null
          ? Math.min(s.cell.struct, s.cell.pulse)
          : s.cell.pulse
        : -1;
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

  // Human labels for the topics that carry a real hourly GDELT feed today (the
  // three live topics; the rest are validated history). Derived from the
  // single source of truth, LIVE_TOPICS, so labels and counts can never drift.
  const liveLabels = useMemo(
    () =>
      detail.series.filter((s) => LIVE_TOPICS.has(s.topic.id)).map((s) => s.topic.label),
    [detail]
  );

  const [topicId, setTopicId] = useState(initial);
  const [mode, setMode] = useState<Mode>("history");
  const [res, setRes] = useState<Resolution>("1M");
  const [filter, setFilter] = useState("");
  // Mobile rail drawer open/closed state
  const [railOpen, setRailOpen] = useState(false);

  // Responsive: switch to the stacked layout below 1024px, gated behind a
  // neutral skeleton until mounted. This is a full-screen (terminal) route with
  // no overflow-x-hidden shell, so emitting the 1024px desktop grid during SSR
  // would clip to a blank on phones. `useResponsiveLayout` flips `mounted` and
  // `isMobile` in ONE commit, so there is no frame where the desktop grid shows
  // on a phone (mounted=true while isMobile is still stale).
  const { mounted, isMobile } = useResponsiveLayout("(max-width: 1023px)");

  const sel = detail.series.find((s) => s.topic.id === topicId) ?? detail.series[0];
  const cell = sel?.cell ?? null;
  const struct = cell?.struct ?? null;
  const pulse = cell?.pulse ?? null;
  const verdict: HfVerdict = cell?.verdict ?? "QUIET";
  const isLive = LIVE_TOPICS.has(topicId);

  const multi = seriesData?.series[topicId];
  const resAvail = (r: Resolution) => (r === "1M" ? true : Boolean(multi?.[r]));

  // Chart input: history shows the full series at the chosen grain; live shows
  // the recent tail for a live topic, or an honest "no live feed" message.
  const view = useMemo(() => {
    if (mode === "live") {
      if (!isLive) {
        return {
          kind: "message" as const,
          text: `Live GDELT feed runs for ${liveLabels.length} topics today\n(${liveLabels.join(", ")}).\nSwitch to History for this topic's full pulse.`,
        };
      }
      const r: Resolution | null = multi?.["1H"] ? "1H" : multi?.["4H"] ? "4H" : null;
      if (!multi || !r)
        return { kind: "message" as const, text: "Live window warming up." };
      const s = multi[r]!;
      const tail = 96;
      const start = Math.max(0, s.x.length - tail);
      return {
        kind: "chart" as const,
        x: s.x.slice(start),
        y: s.y.slice(start),
        events: [] as Array<{ date: string; label: string }>,
        reliable: s.reliable,
        res: r,
        slider: false,
      };
    }
    if (res !== "1M" && multi?.[res]) {
      const s = multi[res]!;
      return {
        kind: "chart" as const,
        x: s.x,
        y: s.y,
        events: [] as Array<{ date: string; label: string }>,
        reliable: s.reliable,
        res,
        slider: true,
      };
    }
    return {
      kind: "chart" as const,
      x: sel?.months ?? [],
      y: sel?.pulse ?? [],
      events: sel?.events ?? [],
      reliable: true,
      res: "1M" as Resolution,
      slider: true,
    };
  }, [mode, res, isLive, multi, sel, liveLabels]);

  // The desktop 3-pane grid, defined as a function so it can render BOTH
  // pre-mount (for real desktop, chosen by CSS) and post-mount with no desktop
  // flash — and is only evaluated when actually rendered (never on mobile).
  const desktopGrid = () => (
    <div
      style={{
        height: "100dvh",
        display: "grid",
        gridTemplateRows: "48px 1fr 26px",
        gridTemplateColumns: "212px 1fr 332px",
        gridTemplateAreas: `"header header header" "rail stage sidebar" "status status status"`,
        // Desktop-first pro terminal. Below the three columns' natural width the
        // page scrolls horizontally rather than collapsing the stage to nothing.
        minWidth: "1024px",
        background: "var(--qgi-bg)",
        color: "var(--qgi-text)",
        overflow: "hidden",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      }}
    >
      <Header backHref={backHref} backLabel={backLabel} />
      <Rail
        countries={countries}
        currentIso3={detail.iso3}
        series={detail.series}
        topicId={topicId}
        onTopic={setTopicId}
        filter={filter}
        onFilter={setFilter}
      />
      <Stage
        sel={sel}
        countryName={detail.name}
        verdict={verdict}
        struct={struct}
        pulse={pulse}
        isLive={isLive}
        mode={mode}
        onMode={setMode}
        res={res}
        onRes={setRes}
        resAvail={resAvail}
        view={view}
        thresholds={detail.thresholds}
      />
      <NewsSidebar
        articles={articlesProp ?? seriesData?.articles ?? []}
        countryName={detail.name}
      />
      <StatusBar
        built={detail.built}
        liveLabels={liveLabels}
        topicCount={detail.series.length}
      />
    </div>
  );

  // Pre-mount: render the REAL desktop grid for >=1024px (CSS lg:block) so the
  // desktop has no skeleton/CLS (SSR and post-mount output match), and a neutral
  // skeleton only for <1024px (CSS lg:hidden) so the 1024px grid never crushes a
  // phone before the matchMedia branch resolves. The media query picks the right
  // one at first paint with no JS.
  if (!mounted) {
    return (
      <>
        <div
          className="lg:hidden"
          role="status"
          aria-live="polite"
          style={{
            minHeight: "100dvh",
            width: "100%",
            background: "var(--qgi-bg)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "12px",
              letterSpacing: "1px",
              color: "var(--qgi-text-dim)",
            }}
          >
            Loading Live Pulse…
          </span>
        </div>
        <div className="hidden lg:block">{desktopGrid()}</div>
      </>
    );
  }

  // ── MOBILE layout (<1024px): stacked vertical flow ──────────────────────
  if (isMobile) {
    return (
      <div
        style={{
          minHeight: "100dvh",
          display: "flex",
          flexDirection: "column",
          background: "var(--qgi-bg)",
          color: "var(--qgi-text)",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          overflowX: "hidden",
        }}
      >
        {/* 1. Header */}
        <MobileHeader backHref={backHref} backLabel={backLabel} />

        {/* 2. Country / Topic selector — collapsible drawer */}
        <div
          style={{
            borderBottom: "1px solid var(--qgi-border)",
          }}
        >
          {/* Drawer toggle button — min 44px tap target, clear interactive affordance */}
          <button
            type="button"
            onClick={() => setRailOpen((o) => !o)}
            aria-expanded={railOpen}
            aria-label={`${railOpen ? "Close" : "Open"} country and topic selector`}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0 16px",
              minHeight: "48px",
              background: "var(--qgi-surface)",
              border: "none",
              borderBottom: railOpen ? "1px solid var(--qgi-border)" : "none",
              color: "var(--qgi-text-muted)",
              fontSize: "12px",
              letterSpacing: "0.5px",
              cursor: "pointer",
              fontFamily: "inherit",
              gap: "8px",
            }}
          >
            <span
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                flex: 1,
                minWidth: 0,
              }}
            >
              {/* "Filters" label makes it scannable as a control */}
              <span
                style={{
                  fontSize: "9px",
                  letterSpacing: "1.5px",
                  color: "var(--qgi-text-dim)",
                  flexShrink: 0,
                  textTransform: "uppercase",
                }}
              >
                COUNTRY / TOPIC
              </span>
              <span style={{ color: "var(--qgi-border)", flexShrink: 0 }}>·</span>
              <span
                style={{
                  color: "var(--qgi-accent)",
                  fontWeight: 700,
                  flexShrink: 0,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {detail.name}
              </span>
              <span style={{ color: "var(--qgi-border)", flexShrink: 0 }}>·</span>
              <span
                style={{
                  color: "var(--qgi-text-muted)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {sel?.topic.label}
              </span>
            </span>
            {/* Chevron with border pill so it reads as a button */}
            <span
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: "28px",
                height: "28px",
                border: "1px solid var(--qgi-border)",
                borderRadius: "14px",
                flexShrink: 0,
                fontSize: "12px",
                color: "var(--qgi-accent)",
                background: "var(--qgi-bg)",
              }}
            >
              {railOpen ? "▲" : "▼"}
            </span>
          </button>

          {/* Collapsible rail content */}
          {railOpen && (
            <div style={{ background: "var(--qgi-bg)", padding: "12px 16px 16px" }}>
              <Rail
                countries={countries}
                currentIso3={detail.iso3}
                series={detail.series}
                topicId={topicId}
                onTopic={(id) => {
                  setTopicId(id);
                  setRailOpen(false);
                }}
                filter={filter}
                onFilter={setFilter}
                mobile
              />
            </div>
          )}
        </div>

        {/* 3. Stage — chart + verdict + timeframe controls — full width */}
        <div style={{ flex: "none" }}>
          <Stage
            sel={sel}
            countryName={detail.name}
            verdict={verdict}
            struct={struct}
            pulse={pulse}
            isLive={isLive}
            mode={mode}
            onMode={setMode}
            res={res}
            onRes={setRes}
            resAvail={resAvail}
            view={view}
            thresholds={detail.thresholds}
            mobile
          />
        </div>

        {/* 4. LIVE NEWS list — full width, no fixed height */}
        <NewsSidebarMobile
          articles={articlesProp ?? seriesData?.articles ?? []}
          countryName={detail.name}
        />

        {/* 5. Status bar */}
        <StatusBar
          built={detail.built}
          liveLabels={liveLabels}
          topicCount={detail.series.length}
        />
      </div>
    );
  }

  // ── DESKTOP layout (>=1024px): original 3-column grid — UNCHANGED ────────
  // Post-mount desktop (>=1024px): the same grid, now without the CSS gate.
  return desktopGrid();
}

/* ── header ──────────────────────────────────────────────────────────── */

function Header({ backHref, backLabel }: { backHref: string; backLabel: string }) {
  const [backHover, setBackHover] = useState(false);
  return (
    <header
      style={{
        gridArea: "header",
        background: "var(--qgi-surface)",
        borderBottom: "2px solid var(--qgi-accent)",
        display: "flex",
        alignItems: "center",
        gap: "14px",
        padding: "0 18px",
      }}
    >
      <Link
        href={backHref as Route}
        onMouseEnter={() => setBackHover(true)}
        onMouseLeave={() => setBackHover(false)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          height: "28px",
          padding: "0 12px",
          border: `1px solid ${backHover ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
          borderRadius: "14px",
          background: "var(--qgi-bg)",
          color: backHover ? "var(--qgi-accent)" : "var(--qgi-text-muted)",
          fontSize: "10.5px",
          letterSpacing: "1px",
          textDecoration: "none",
        }}
      >
        ← {backLabel}
      </Link>
      <Sep />
      <div
        style={{
          fontFamily:
            "'Century Gothic', 'CenturyGothic', 'URW Gothic', 'AppleGothic', 'ITC Avant Garde Gothic', var(--font-qg-brand), sans-serif",
          display: "flex",
          alignItems: "baseline",
          gap: "8px",
        }}
      >
        <span
          style={{
            fontSize: "18px",
            fontWeight: 700,
            color: "var(--qgi-accent)",
            letterSpacing: "1px",
          }}
        >
          QG
        </span>
        <span
          style={{
            fontSize: "10px",
            fontWeight: 500,
            letterSpacing: "2px",
            color: "var(--qgi-text-muted)",
            textTransform: "uppercase",
          }}
        >
          Intelligence
        </span>
      </div>
      <Sep />
      <span
        style={{
          fontSize: "11px",
          color: "var(--qgi-accent)",
          fontWeight: 700,
          letterSpacing: "3px",
        }}
      >
        LIVE PULSE · PRO
      </span>
      <span style={{ flex: 1 }} />
      <LivePulseStamp compact />
      <Sep />
      <HowToReadButton routeKey="live-pulse" />
      <Sep />
      <Clock />
    </header>
  );
}

/* ── mobile header: compact single-row ──────────────────────────────── */

function MobileHeader({ backHref, backLabel }: { backHref: string; backLabel: string }) {
  return (
    <header
      style={{
        background: "var(--qgi-surface)",
        borderBottom: "2px solid var(--qgi-accent)",
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "0 14px",
        height: "48px",
        flexShrink: 0,
      }}
    >
      <Link
        href={backHref as Route}
        aria-label={backLabel || "Back"}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "4px",
          padding: "0 10px",
          border: "1px solid var(--qgi-border)",
          borderRadius: "16px",
          background: "var(--qgi-bg)",
          color: "var(--qgi-text-muted)",
          fontSize: "11px",
          letterSpacing: "0.5px",
          textDecoration: "none",
          flexShrink: 0,
          minHeight: "44px",
          minWidth: "44px",
          justifyContent: "center",
        }}
      >
        ←
      </Link>
      {/* 'QG' + 'LIVE PULSE' is a bespoke compact lockup for this 48px terminal
          header — the shared <Wordmark> renders the full "QG INTELLIGENCE" nav
          mark, which is too wide here and carries the wrong label. The Century
          Gothic stack matches Wordmark's brand font. */}
      <span
        style={{
          fontFamily:
            "'Century Gothic', 'CenturyGothic', 'URW Gothic', 'AppleGothic', var(--font-qg-brand), sans-serif",
          fontSize: "17px",
          fontWeight: 700,
          color: "var(--qgi-accent)",
          letterSpacing: "1px",
          flexShrink: 0,
        }}
      >
        QG
      </span>
      <span
        style={{
          fontSize: "11px",
          color: "var(--qgi-accent)",
          fontWeight: 700,
          letterSpacing: "2px",
          flexShrink: 0,
        }}
      >
        LIVE PULSE
      </span>
      <span style={{ flex: 1 }} />
      <LivePulseStamp compact />
    </header>
  );
}

function Sep() {
  return (
    <span style={{ width: "1px", height: "18px", background: "var(--qgi-border)" }} />
  );
}

function Clock() {
  // Client-only ticking UTC clock; renders a placeholder until mounted so SSR
  // and first paint match (no hydration mismatch).
  const [t, setT] = useState<string>("--:--:--");
  useEffect(() => {
    const tick = () => setT(new Date().toISOString().slice(11, 19));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span style={{ fontSize: "10px", color: "var(--qgi-text-muted)" }}>{t} UTC</span>
  );
}

/* ── left rail: country switcher + topic chips ───────────────────────── */

function Rail({
  countries,
  currentIso3,
  series,
  topicId,
  onTopic,
  filter,
  onFilter,
  mobile,
}: {
  countries: RailCountry[];
  currentIso3: string;
  series: HfTopicSeries[];
  topicId: string;
  onTopic: (id: string) => void;
  filter: string;
  onFilter: (v: string) => void;
  mobile?: boolean;
}) {
  const shown = countries.filter(
    (c) => !filter || c.name.toLowerCase().includes(filter.toLowerCase())
  );

  // Mobile: natural flow (no fixed heights, no overflow:hidden)
  if (mobile) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {/* Country list */}
        <div>
          <SecLabel left="COUNTRY" right={String(countries.length)} mobile />
          <input
            value={filter}
            onChange={(e) => onFilter(e.target.value)}
            placeholder="filter…"
            aria-label="Filter countries"
            style={{
              minHeight: "44px",
              width: "100%",
              background: "var(--qgi-bg)",
              border: "1px solid var(--qgi-border)",
              borderRadius: "4px",
              color: "var(--qgi-text-muted)",
              fontSize: "13px",
              padding: "0 10px",
              marginBottom: "8px",
              fontFamily: "inherit",
              boxSizing: "border-box",
            }}
          />
          <div
            style={{
              maxHeight: "200px",
              overflowY: "auto",
              border: "1px solid var(--qgi-border)",
              borderRadius: "4px",
            }}
          >
            {shown.map((c) => {
              const on = c.iso3 === currentIso3;
              return (
                <Link
                  key={c.iso3}
                  href={`/countries/${c.param}/live-pulse` as Route}
                  aria-current={on ? "page" : undefined}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    minHeight: "44px",
                    padding: "0 12px",
                    fontSize: "13px",
                    textDecoration: "none",
                    color: on ? "var(--qgi-text)" : "var(--qgi-text-muted)",
                    background: on ? "var(--qgi-surface-2)" : "transparent",
                    borderLeft: `3px solid ${on ? "var(--qgi-accent)" : "transparent"}`,
                    borderBottom: "1px solid var(--qgi-border)",
                  }}
                >
                  <FlagImg emoji="" name={c.name} width={20} radius={1} />
                  {c.name}
                </Link>
              );
            })}
          </div>
        </div>

        {/* Topic chips */}
        <div>
          <SecLabel left="TOPIC" right={String(series.length)} mobile />
          <div
            role="group"
            aria-label="News topics"
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "6px",
            }}
          >
            {series.map((s) => {
              const on = s.topic.id === topicId;
              const v = s.cell?.verdict ?? "QUIET";
              const live = LIVE_TOPICS.has(s.topic.id);
              return (
                <button
                  key={s.topic.id}
                  type="button"
                  onClick={() => onTopic(s.topic.id)}
                  aria-pressed={on}
                  title={`${s.topic.id} · ${s.topic.name}${live ? " (live feed)" : ""}. Verdict: ${v}. ${s.topic.scope}`}
                  style={{
                    minHeight: "44px",
                    border: `1px solid ${on ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
                    boxShadow: on ? "inset 0 0 0 1px var(--qgi-accent)" : "none",
                    borderRadius: "4px",
                    background: on ? "var(--qgi-surface-2)" : "var(--qgi-bg)",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    padding: "0 8px",
                    gap: "6px",
                    position: "relative",
                    overflow: "hidden",
                    fontSize: "11px",
                    letterSpacing: "0.3px",
                    fontFamily: "inherit",
                    color: on ? "var(--qgi-text)" : "var(--qgi-text-muted)",
                    textAlign: "left",
                  }}
                >
                  <span
                    aria-hidden
                    style={{
                      width: "3px",
                      height: "16px",
                      borderRadius: "2px",
                      flexShrink: 0,
                      background: verdictVar(v),
                    }}
                  />
                  <span
                    style={{
                      fontWeight: 700,
                      color: on ? "var(--qgi-accent)" : "var(--qgi-text-dim)",
                      fontSize: "10px",
                      flexShrink: 0,
                    }}
                  >
                    {s.topic.id}
                  </span>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>
                    {s.topic.label}
                  </span>
                  {live && (
                    <span
                      aria-hidden
                      className="animate-pulse"
                      style={{
                        flexShrink: 0,
                        width: "6px",
                        height: "6px",
                        borderRadius: "50%",
                        background: "var(--qgi-success)",
                      }}
                    />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // Desktop rail (original)
  return (
    <div
      style={{
        gridArea: "rail",
        borderRight: "1px solid var(--qgi-border)",
        padding: "12px 10px",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <SecLabel left="COUNTRY" right={String(countries.length)} />
      <input
        value={filter}
        onChange={(e) => onFilter(e.target.value)}
        placeholder="filter…"
        aria-label="Filter countries"
        style={{
          height: "28px",
          width: "100%",
          background: "var(--qgi-bg)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "3px",
          color: "var(--qgi-text-muted)",
          fontSize: "11px",
          padding: "0 8px",
          marginBottom: "6px",
          fontFamily: "inherit",
        }}
      />
      <div
        style={{
          overflowY: "auto",
          flex: "1 1 auto",
          maxHeight: "46%",
          minHeight: "90px",
          marginBottom: "10px",
        }}
      >
        {shown.map((c) => {
          const on = c.iso3 === currentIso3;
          return (
            <Link
              key={c.iso3}
              href={`/countries/${c.param}/live-pulse` as Route}
              aria-current={on ? "page" : undefined}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                height: "30px",
                padding: "0 8px",
                fontSize: "11.5px",
                textDecoration: "none",
                color: on ? "var(--qgi-text)" : "var(--qgi-text-muted)",
                background: on ? "var(--qgi-surface-2)" : "transparent",
                borderLeft: `2px solid ${on ? "var(--qgi-accent)" : "transparent"}`,
              }}
            >
              <FlagImg emoji="" name={c.name} width={18} radius={1} />
              {c.name}
            </Link>
          );
        })}
      </div>

      <SecLabel left="TOPIC" right={String(series.length)} />
      <div
        role="group"
        aria-label="News topics"
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "4px",
          // Take the rail's remaining height and scroll within it, so the 14
          // chips can never spill past the rail on a short viewport.
          flex: "1 1 auto",
          minHeight: 0,
          alignContent: "start",
          overflowY: "auto",
          paddingBottom: "2px",
        }}
      >
        {series.map((s) => {
          const on = s.topic.id === topicId;
          const v = s.cell?.verdict ?? "QUIET";
          const live = LIVE_TOPICS.has(s.topic.id);
          return (
            <button
              key={s.topic.id}
              type="button"
              onClick={() => onTopic(s.topic.id)}
              aria-pressed={on}
              title={`${s.topic.id} · ${s.topic.name}${live ? " (live feed)" : ""}. Verdict: ${v}. ${s.topic.scope}`}
              style={{
                height: "27px",
                border: `1px solid ${on ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
                boxShadow: on ? "inset 0 0 0 1px var(--qgi-accent)" : "none",
                borderRadius: "3px",
                background: on ? "var(--qgi-surface-2)" : "var(--qgi-bg)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                padding: "0 6px",
                gap: "5px",
                position: "relative",
                overflow: "hidden",
                whiteSpace: "nowrap",
                fontSize: "9px",
                letterSpacing: "0.4px",
                fontFamily: "inherit",
                color: on ? "var(--qgi-text)" : "var(--qgi-text-muted)",
              }}
            >
              <span
                aria-hidden
                style={{
                  width: "2px",
                  height: "14px",
                  borderRadius: "2px",
                  flexShrink: 0,
                  background: verdictVar(v),
                }}
              />
              <span
                style={{
                  fontWeight: 700,
                  color: on ? "var(--qgi-accent)" : "var(--qgi-text-dim)",
                  fontSize: "8.5px",
                  flexShrink: 0,
                }}
              >
                {s.topic.id}
              </span>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>
                {s.topic.label}
              </span>
              {live && (
                <span
                  aria-hidden
                  className="animate-pulse"
                  style={{
                    position: "absolute",
                    top: "3px",
                    right: "3px",
                    width: "5px",
                    height: "5px",
                    borderRadius: "50%",
                    background: "var(--qgi-success)",
                  }}
                />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SecLabel({
  left,
  right,
  mobile,
}: {
  left: string;
  right: string;
  mobile?: boolean;
}) {
  return (
    <div
      style={{
        // Mobile bumps to 10px / 1px tracking for legibility; desktop unchanged.
        fontSize: mobile ? "10px" : "9px",
        color: "var(--qgi-text-muted)",
        letterSpacing: mobile ? "1px" : "2px",
        margin: "0 0 6px",
        display: "flex",
        justifyContent: "space-between",
      }}
    >
      <span>{left}</span>
      <span style={{ color: "var(--qgi-text-dim)" }}>{right}</span>
    </div>
  );
}

/* ── center stage: verdict strip + chart + timeframe + crosswalk ─────── */

type ChartView =
  | { kind: "message"; text: string }
  | {
      kind: "chart";
      x: string[];
      y: number[];
      events: Array<{ date: string; label: string }>;
      reliable: boolean;
      res: Resolution;
      slider: boolean;
    };

function Stage({
  sel,
  countryName,
  verdict,
  struct,
  pulse,
  isLive,
  mode,
  onMode,
  res,
  onRes,
  resAvail,
  view,
  thresholds,
  mobile,
}: {
  sel: HfTopicSeries | undefined;
  countryName: string;
  verdict: HfVerdict;
  struct: number | null;
  pulse: number | null;
  isLive: boolean;
  mode: Mode;
  onMode: (m: Mode) => void;
  res: Resolution;
  onRes: (r: Resolution) => void;
  resAvail: (r: Resolution) => boolean;
  view: ChartView;
  thresholds: { struct: number; pulse: number };
  mobile?: boolean;
}) {
  const vcol = verdictVar(verdict);
  return (
    <div
      style={{
        gridArea: mobile ? undefined : "stage",
        display: "flex",
        flexDirection: "column",
        padding: mobile ? "12px 14px" : "12px",
        gap: "10px",
        minWidth: 0,
      }}
    >
      {/* verdict strip */}
      <div
        style={{
          minHeight: "54px",
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "4px",
          display: "flex",
          alignItems: "center",
          gap: "16px",
          padding: "8px 16px",
          flexWrap: "wrap",
        }}
      >
        <ExplainTip text="Active: structure and news pulse are both 60 or above. Signal: news pulse is 60 or above but structure is below, often short-lived noise. Latent: structure is 60 or above while news stays quiet, a pattern worth watching. Quiet: neither reading reaches 60.">
          <span
            style={{
              minWidth: "96px",
              minHeight: mobile ? "44px" : "36px",
              height: mobile ? undefined : "36px",
              borderRadius: "5px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "1.5px",
              border: `1px solid ${vcol}`,
              color: vcol,
              background: `color-mix(in srgb, ${vcol} 13%, transparent)`,
              padding: mobile ? "0 14px" : undefined,
            }}
          >
            {VERDICT_LABEL[verdict]}
          </span>
        </ExplainTip>
        <span
          style={{
            display: "flex",
            alignItems: "center",
            gap: "9px",
            fontSize: mobile ? "16px" : "14px",
            fontWeight: 700,
          }}
        >
          {countryName}
        </span>
        {sel && (
          <span
            style={{
              fontSize: mobile ? "12px" : "10px",
              letterSpacing: "1px",
              padding: mobile ? "0 12px" : "4px 9px",
              minHeight: mobile ? "44px" : undefined,
              display: "flex",
              alignItems: "center",
              borderRadius: "4px",
              border: "1px solid var(--qgi-accent)",
              color: "var(--qgi-accent)",
              background: "color-mix(in srgb, var(--qgi-accent) 9%, transparent)",
            }}
          >
            {sel.topic.id} · {sel.topic.label.toUpperCase()}
          </span>
        )}
        {/* HISTORY / LIVE mode toggle */}
        <div
          role="group"
          aria-label="Mode"
          style={{
            display: "flex",
            background: "var(--qgi-bg)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "18px",
            padding: "2px",
          }}
        >
          {(["history", "live"] as Mode[]).map((m) => {
            const on = m === mode;
            return (
              <button
                key={m}
                type="button"
                onClick={() => onMode(m)}
                aria-pressed={on}
                style={{
                  border: "none",
                  background: on ? "var(--qgi-surface)" : "transparent",
                  color: on ? "var(--qgi-accent)" : "var(--qgi-text-muted)",
                  boxShadow: on ? "inset 0 0 0 1px var(--qgi-accent)" : "none",
                  fontSize: mobile ? "13px" : "10.5px",
                  letterSpacing: "1px",
                  height: mobile ? "44px" : "26px",
                  padding: mobile ? "0 18px" : "0 15px",
                  borderRadius: "16px",
                  cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                {m === "history" ? "HISTORY · 11Y" : "LIVE"}
              </button>
            );
          })}
        </div>
        <span style={{ flex: 1 }} />
        <Readout
          label="STRUCTURAL"
          value={struct === null ? "n/a" : String(Math.round(struct))}
          tip="How closely this country's long-run signals resemble the shape that ran ahead of this kind of event in the past. Scored 0 to 100, where 60 and above is elevated."
        />
        <Readout
          label="PULSE"
          value={pulse === null ? "n/a" : String(Math.round(pulse))}
          color="var(--qgi-accent)"
          tip="How much of this country's news coverage is on this theme right now, measured against its own history. 50 is a normal month for this country; 60 and above is elevated."
        />
        {struct !== null && pulse !== null && (
          <p
            style={{
              width: "100%",
              margin: "4px 0 0",
              fontSize: "11px",
              lineHeight: 1.4,
              fontFamily: "ui-monospace, monospace",
              color: "var(--qgi-text-dim)",
            }}
          >
            <span style={{ color: "var(--qgi-accent)", fontWeight: 700 }}>
              News at {Math.round(pulse)}
            </span>
            {pulse >= struct ? " · above " : " · below "}
            <span style={{ color: "var(--qgi-warning)", fontWeight: 700 }}>
              structural fair value {Math.round(struct)}
            </span>
            {` for ${sel?.topic.label ?? "this topic"}.`}
          </p>
        )}
      </div>

      {/* chart */}
      <div
        style={{
          flex: mobile ? undefined : 1,
          height: mobile ? "280px" : undefined,
          background: "var(--qgi-surface)",
          border: "1px solid var(--qgi-border)",
          borderRadius: "4px",
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          position: "relative",
        }}
      >
        {view.kind === "message" ? (
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              whiteSpace: "pre-line",
              color: "var(--qgi-text-muted)",
              fontSize: "13px",
              lineHeight: 1.7,
              padding: "24px",
            }}
          >
            {view.text}
          </div>
        ) : (
          <StageChart
            key={`${mode}-${view.res}-${sel?.topic.id}`}
            view={view}
            struct={struct}
            thresholds={thresholds}
            mobile={mobile}
          />
        )}
        {/* timeframe row — larger tap targets on mobile */}
        <div
          role="group"
          aria-label="Timeframe"
          style={{
            display: "flex",
            justifyContent: "center",
            gap: mobile ? "8px" : "6px",
            padding: mobile ? "10px 0 12px" : "8px 0 10px",
          }}
        >
          {ALL_RES.map((r) => {
            const on = mode === "history" ? r === res : false;
            const disabled = mode === "live" || !resAvail(r);
            return (
              <button
                key={r}
                type="button"
                disabled={disabled}
                aria-pressed={on}
                title={
                  mode === "live"
                    ? "Timeframe applies in History mode"
                    : !resAvail(r)
                      ? "Not available at this grain for this topic"
                      : undefined
                }
                onClick={() => onRes(r)}
                style={{
                  width: mobile ? "54px" : "42px",
                  height: mobile ? "44px" : "24px",
                  border: `1px solid ${on ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
                  borderRadius: mobile ? "4px" : "3px",
                  background: on ? "var(--qgi-surface-2)" : "transparent",
                  color: on
                    ? "var(--qgi-accent)"
                    : disabled
                      ? "var(--qgi-text-dim)"
                      : "var(--qgi-text-muted)",
                  fontSize: mobile ? "13px" : "10px",
                  cursor: disabled ? "not-allowed" : "pointer",
                  opacity: disabled ? 0.4 : 1,
                  fontFamily: "inherit",
                }}
              >
                {RES_LABEL[r]}
              </button>
            );
          })}
        </div>
      </div>

      {/* Topic → Trends crosswalk */}
      {sel && <Crosswalk sel={sel} isLive={isLive} />}
    </div>
  );
}

function Readout({
  label,
  value,
  color,
  tip,
}: {
  label: string;
  value: string;
  color?: string;
  tip?: string;
}) {
  return (
    <div style={{ textAlign: "right" }}>
      <div
        style={{
          fontSize: "8.5px",
          color: "var(--qgi-text-muted)",
          letterSpacing: "1.5px",
        }}
      >
        {tip ? (
          <ExplainTip
            text={tip}
            style={{
              borderBottom: "1px dotted var(--qgi-text-dim)",
              letterSpacing: "1.5px",
              fontSize: "8.5px",
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            }}
          >
            {label}
          </ExplainTip>
        ) : (
          label
        )}
      </div>
      <div style={{ fontSize: "20px", color: color ?? "var(--qgi-text)" }}>{value}</div>
    </div>
  );
}

function Crosswalk({ sel, isLive }: { sel: HfTopicSeries; isLive: boolean }) {
  const feeds = (sel.topic.trends ?? []).map(pretty);
  return (
    <div
      style={{
        marginTop: "1px",
        fontSize: "11px",
        lineHeight: 1.65,
        color: "var(--qgi-text-muted)",
        borderTop: "1px solid var(--qgi-border)",
        paddingTop: "9px",
      }}
    >
      <b style={{ color: "var(--qgi-accent)" }}>
        {sel.topic.id} · {sel.topic.name.toUpperCase()}
      </b>{" "}
      <span style={{ color: "var(--qgi-text-dim)" }}>news Topic</span>{" "}
      {isLive ? (
        <span style={{ color: "var(--qgi-success)", fontSize: "9px" }}>
          ● live + structural{" "}
          <Link
            href={"/methodology" as Route}
            style={{
              color: "var(--qgi-text-dim)",
              textDecoration: "none",
              borderBottom: "1px dotted var(--qgi-text-dim)",
              fontSize: "9px",
            }}
          >
            validation ›
          </Link>
        </span>
      ) : (
        <span style={{ color: "var(--qgi-text-dim)", fontSize: "9px" }}>
          ○ validated history · live feed coming soon
        </span>
      )}
      <br />
      <span style={{ color: "var(--qgi-text-dim)" }}>feeds trends →</span>{" "}
      {feeds.length ? feeds.slice(0, 8).join(" · ") : "(none)"}
      {feeds.length > 8 && (
        <span style={{ color: "var(--qgi-text-dim)" }}> +{feeds.length - 8}</span>
      )}
    </div>
  );
}

/* ── chart ───────────────────────────────────────────────────────────── */

function StageChart({
  view,
  struct,
  thresholds,
  mobile,
}: {
  view: Extract<ChartView, { kind: "chart" }>;
  struct: number | null;
  thresholds: { struct: number; pulse: number };
  mobile?: boolean;
}) {
  const { isDark } = useTheme();
  const t = getEchartsTokens(isDark);

  const fmtLabel = (v: string) =>
    view.res === "1M"
      ? v.slice(0, 7)
      : view.res === "1H" || view.res === "4H"
        ? v.slice(5) // MM-DD HH:MM
        : v.slice(5, 10); // MM-DD

  const markers = view.events
    .map((e) => {
      const i = view.x.indexOf(e.date);
      return i < 0
        ? null
        : { coord: [e.date, view.y[i]] as [string, number], label: e.label };
    })
    .filter(Boolean) as Array<{ coord: [string, number]; label: string }>;

  const showStruct = struct !== null && view.res === "1M";

  const dz: Array<Record<string, unknown>> = [
    {
      type: "inside",
      zoomOnMouseWheel: true,
      moveOnMouseMove: true,
      moveOnMouseWheel: false,
    },
  ];
  if (view.slider) {
    dz.push({
      type: "slider",
      height: 18,
      bottom: 6,
      left: 50,
      right: 18,
      backgroundColor: t.surface,
      borderColor: t.border,
      fillerColor: "color-mix(in srgb, " + t.accent + " 10%, transparent)",
      handleStyle: { color: t.accent, borderColor: t.accent },
      moveHandleStyle: { color: t.border, borderColor: t.accent },
      dataBackground: {
        lineStyle: { color: t.border, width: 1 },
        areaStyle: { color: t.border, opacity: 0.5 },
      },
      selectedDataBackground: {
        lineStyle: { color: t.accent, width: 1.2 },
        areaStyle: { color: t.accent, opacity: 0.15 },
      },
      textStyle: { color: t.textDim, fontSize: 9 },
      brushSelect: false,
    });
  }
  // Open window: the most recent slice per grain (TradingView default).
  const n = view.x.length;
  const show: Record<Resolution, number> = {
    "1M": n,
    "1W": Math.min(n, 104),
    "1D": Math.min(n, 210),
    "4H": Math.min(n, 126),
    "1H": Math.min(n, 504),
  };
  const startPct = n ? Math.round((Math.max(0, n - show[view.res]) / n) * 100) : 0;
  dz.forEach((z) => {
    z.start = startPct;
    z.end = 100;
  });

  const option = {
    backgroundColor: "transparent",
    animation: false,
    tooltip: {
      trigger: "axis",
      appendToBody: true,
      confine: true,
      backgroundColor: t.surface2,
      borderColor: t.accent,
      textStyle: { color: t.text, fontSize: 11 },
      formatter: (ps: Array<{ axisValue: string; data: number }>) => {
        const p = ps[0];
        const ev = view.events.find((e) => e.date === p.axisValue);
        return (
          `${p.axisValue}<br/>pulse ${Math.round(p.data)}` +
          (showStruct ? `<br/>structural ${Math.round(struct as number)}` : "") +
          (ev ? `<br/><span style="color:${t.amber}">${ev.label}</span>` : "")
        );
      },
    },
    // Mobile: tighter left gutter so Y-axis labels (0–100) clear the edge.
    // 48px fits "100" at 10px monospace; desktop keeps 64 for the axis name.
    grid: { left: mobile ? 48 : 64, right: 18, top: 16, bottom: view.slider ? 34 : 18 },
    xAxis: {
      type: "category",
      data: view.x,
      boundaryGap: false,
      axisLine: { lineStyle: { color: t.border } },
      axisTick: { show: false },
      axisLabel: {
        color: t.textDim,
        fontSize: 10,
        hideOverlap: true,
        formatter: fmtLabel,
      },
    },
    yAxis: {
      min: 0,
      max: 100,
      // Hide rotated axis name on mobile — saves ~16px of left gutter and
      // keeps axis labels flush inside the chart area on 360px screens.
      name: mobile ? "" : "News Pressure (%)",
      nameLocation: "middle",
      nameGap: mobile ? 0 : 48,
      nameRotate: 90,
      nameTextStyle: { color: t.textDim, fontSize: 10, letterSpacing: 0.5 },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: t.splitLine, opacity: 0.4, type: "dashed" } },
      axisLabel: { color: t.textDim, fontSize: 10 },
    },
    dataZoom: dz,
    series: [
      {
        name: "Pulse",
        type: "line",
        data: view.y,
        symbol: "none",
        sampling: "lttb",
        lineStyle: { width: 1.6, color: view.reliable ? t.accent : t.textDim },
        areaStyle: { color: `${t.accent}1e` },
        markPoint: {
          symbol: "pin",
          symbolSize: 18,
          itemStyle: { color: t.surface2, borderColor: t.amber, borderWidth: 1.4 },
          label: { show: false },
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
            fontSize: 10,
            color: t.textDim,
            formatter: `elevated ${thresholds.pulse}`,
          },
          data: [
            { yAxis: thresholds.pulse },
            ...(showStruct
              ? [
                  {
                    yAxis: struct as number,
                    lineStyle: { color: t.amber, type: "dashed" as const, width: 1.4 },
                    label: {
                      show: true,
                      position: "insideEndTop" as const,
                      fontSize: 10,
                      color: t.amber,
                      formatter: `structural ${Math.round(struct as number)}`,
                    },
                  },
                ]
              : []),
          ],
        },
      },
    ],
  };

  // Absolute fill inside a relative flex child: guarantees a measurable pixel
  // box at echarts.init(), so the chart never renders at 0 height on first
  // paint before a window resize (the classic ECharts-in-flex trap).
  return (
    <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
      <ReactECharts
        option={option}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      />
    </div>
  );
}

/* ── right sidebar: LIVE NEWS flow ───────────────────────────────────── */

const TOPIC_TINT: Record<string, string> = {
  T01: "var(--qgi-accent)",
  T02: "var(--qgi-warning)",
  T03: "var(--qgi-warning)",
  T05: "var(--qgi-accent)",
  T06: "var(--qgi-accent)",
  T07: "var(--qgi-text-muted)",
};

function NewsSidebar({
  articles,
  countryName,
}: {
  articles: LiveArticle[];
  countryName: string;
}) {
  const sorted = useMemo(
    () => [...articles].sort((a, b) => (a.dt < b.dt ? 1 : a.dt > b.dt ? -1 : 0)),
    [articles]
  );
  return (
    <div
      style={{
        gridArea: "sidebar",
        background: "var(--qgi-surface)",
        borderLeft: "1px solid var(--qgi-border)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: "36px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "0 14px",
          borderBottom: "1px solid var(--qgi-border)",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            color: "var(--qgi-text-muted)",
            letterSpacing: "2px",
          }}
        >
          LIVE NEWS
        </span>
        <span
          style={{
            fontSize: "9px",
            color: "var(--qgi-text-muted)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "10px",
            padding: "2px 8px",
          }}
        >
          {countryName}
        </span>
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {sorted.length === 0 ? (
          <div
            style={{
              padding: "40px 14px",
              textAlign: "center",
              color: "var(--qgi-text-dim)",
              fontSize: "12px",
            }}
          >
            Live headlines coming soon.
          </div>
        ) : (
          sorted.map((a, i) => {
            const tint = TOPIC_TINT[a.topic] ?? "var(--qgi-text-muted)";
            const tone = a.tone;
            const toneCol =
              tone === null
                ? "var(--qgi-text-dim)"
                : tone < -1
                  ? "var(--qgi-warning)"
                  : tone > 1
                    ? "var(--qgi-success)"
                    : "var(--qgi-text-muted)";
            const title = deriveTitle(a.url, a.domain, a.topicLabel);
            return (
              <a
                key={`${a.url}-${i}`}
                href={a.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: "block",
                  padding: "9px 14px",
                  borderBottom: "1px solid var(--qgi-border)",
                  borderLeft: `3px solid ${tint}`,
                  textDecoration: "none",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "8.5px",
                    letterSpacing: "0.5px",
                    color: "var(--qgi-text-muted)",
                  }}
                >
                  <span>
                    {a.domain
                      .replace(/^www\./, "")
                      .toUpperCase()
                      .slice(0, 20)}
                  </span>
                  <span>{fmtStamp(a.dt)}</span>
                </div>
                <div
                  style={{
                    fontSize: "11px",
                    color: "var(--qgi-text)",
                    lineHeight: 1.35,
                    margin: "4px 0 5px",
                  }}
                >
                  {title}
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    fontSize: "8.5px",
                  }}
                >
                  <span style={{ color: tint, fontWeight: 600 }}>{a.topicLabel}</span>
                  {tone !== null && (
                    <span
                      style={{ color: toneCol }}
                      title="Sentiment of the article's language from the GDELT feed: negative skews critical or alarming, positive favorable or neutral. Below -1 is flagged as notably critical."
                    >
                      tone {tone.toFixed(1)}
                    </span>
                  )}
                </div>
              </a>
            );
          })
        )}
      </div>
      <div
        style={{
          fontSize: "9px",
          color: "var(--qgi-text-dim)",
          padding: "7px 14px",
          borderTop: "1px solid var(--qgi-border)",
        }}
      >
        News attention across all topics from the global GDELT feed, not verified events.
        Click to open.
      </div>
    </div>
  );
}

/* ── mobile news list: full-width, no fixed height ───────────────────── */

function NewsSidebarMobile({
  articles,
  countryName,
}: {
  articles: LiveArticle[];
  countryName: string;
}) {
  const sorted = useMemo(
    () => [...articles].sort((a, b) => (a.dt < b.dt ? 1 : a.dt > b.dt ? -1 : 0)),
    [articles]
  );
  return (
    <div
      style={{
        borderTop: "1px solid var(--qgi-border)",
        background: "var(--qgi-surface)",
      }}
    >
      {/* Section header */}
      <div
        style={{
          height: "44px",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          padding: "0 16px",
          borderBottom: "1px solid var(--qgi-border)",
        }}
      >
        <span
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-muted)",
            letterSpacing: "2px",
          }}
        >
          LIVE NEWS
        </span>
        <span
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-muted)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "10px",
            padding: "3px 10px",
          }}
        >
          {countryName}
        </span>
      </div>

      {/* Article list — no max-height, scrolls with the page */}
      {sorted.length === 0 ? (
        <div
          style={{
            padding: "32px 16px",
            textAlign: "center",
            color: "var(--qgi-text-dim)",
            fontSize: "13px",
          }}
        >
          Live headlines coming soon.
        </div>
      ) : (
        sorted.map((a, i) => {
          const tint = TOPIC_TINT[a.topic] ?? "var(--qgi-text-muted)";
          const tone = a.tone;
          const toneCol =
            tone === null
              ? "var(--qgi-text-dim)"
              : tone < -1
                ? "var(--qgi-warning)"
                : tone > 1
                  ? "var(--qgi-success)"
                  : "var(--qgi-text-muted)";
          const title = deriveTitle(a.url, a.domain, a.topicLabel);
          return (
            <a
              key={`${a.url}-${i}`}
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "block",
                padding: "12px 16px",
                borderBottom: "1px solid var(--qgi-border)",
                borderLeft: `3px solid ${tint}`,
                textDecoration: "none",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "10px",
                  letterSpacing: "0.5px",
                  color: "var(--qgi-text-muted)",
                  marginBottom: "4px",
                }}
              >
                <span>
                  {a.domain
                    .replace(/^www\./, "")
                    .toUpperCase()
                    .slice(0, 24)}
                </span>
                <span>{fmtStamp(a.dt)}</span>
              </div>
              <div
                style={{
                  fontSize: "13px",
                  color: "var(--qgi-text)",
                  lineHeight: 1.4,
                  marginBottom: "6px",
                }}
              >
                {title}
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  fontSize: "10px",
                }}
              >
                <span style={{ color: tint, fontWeight: 600 }}>{a.topicLabel}</span>
                {tone !== null && (
                  <span style={{ color: toneCol }}>tone {tone.toFixed(1)}</span>
                )}
              </div>
            </a>
          );
        })
      )}
      <div
        style={{
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          padding: "10px 16px",
          borderTop: "1px solid var(--qgi-border)",
        }}
      >
        News attention from the global GDELT feed, not verified events. Tap to open.
      </div>
    </div>
  );
}

/* ── bottom status bar: data provenance honesty line ─────────────────── */

function StatusBar({
  built,
  liveLabels,
  topicCount,
}: {
  built: string;
  liveLabels: string[];
  topicCount: number;
}) {
  return (
    <div
      style={{
        gridArea: "status",
        background: "var(--qgi-surface)",
        borderTop: "1px solid var(--qgi-border)",
        display: "flex",
        alignItems: "center",
        gap: "18px",
        padding: "0 16px",
        fontSize: "9px",
        color: "var(--qgi-text-muted)",
        letterSpacing: "0.5px",
        overflow: "hidden",
        whiteSpace: "nowrap",
      }}
    >
      <span>
        <GDot /> STRUCTURE: REAL
      </span>
      <span>EVENTS: REAL (verified corpus)</span>
      <span style={{ color: "var(--qgi-success)" }}>
        LIVE PULSE + NEWS: REAL GDELT · {liveLabels.length} of {topicCount} topics live (
        {liveLabels.join(" · ")})
      </span>
      <ExplainTip text="Each country's monthly pulse is scored against its own 11-year history, so a reading of 60 means 60th percentile for that country, not a global comparison. This keeps smaller countries comparable to larger ones.">
        <span
          style={{
            color: "var(--qgi-success)",
            borderBottom: "1px dotted var(--qgi-success)",
          }}
        >
          VALIDATION: REAL GDELT · 11-year monthly pulse · scored against each
          country&apos;s own history
        </span>
      </ExplainTip>
      <span style={{ flex: 1 }} />
      <span style={{ color: "var(--qgi-text-dim)" }}>built {built}</span>
      <ExplainTip
        text={`Two layers: Trends are QGI's structural resemblance scores built from long-run signals. Topics are ${topicCount} news themes scored from the GDELT feed; ${liveLabels.length} carry an hourly live feed today, the rest show their full validated history. Together they form the Active/Signal/Latent/Quiet verdict.`}
      >
        <span
          style={{
            color: "var(--qgi-text-dim)",
            borderBottom: "1px dotted var(--qgi-text-dim)",
          }}
        >
          QGI · Trends ✕ Topics
        </span>
      </ExplainTip>
    </div>
  );
}

function GDot() {
  return (
    <span
      style={{
        width: "5px",
        height: "5px",
        borderRadius: "50%",
        background: "var(--qgi-success)",
        display: "inline-block",
        marginRight: "5px",
      }}
    />
  );
}
