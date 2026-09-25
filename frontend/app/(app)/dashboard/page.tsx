/**
 * Briefing — hybrid dashboard (Signal Board structure + Editorial analogue layer).
 *
 * Layout (top → bottom):
 *
 *   ZONE A  BriefingCommandBar (reads "BRIEFING"; same look as Signal's bar)
 *
 *   ZONE B  Three-column spatial grid (~260px / minmax(0,1fr) / ~230px):
 *     LEFT    Hot-signal hero (expanded, more generous spacing)
 *     CENTER  Interactive Signal landscape (scatter with country/topic filters)
 *     RIGHT   AlarmsColumnFixed only (MoversColumn removed from right rail)
 *
 *   ZONE C  MoversBand — "Biggest movers this month" as a full-width horizontal panel
 *
 *   ZONE D  Editorial ANALOGUE feature (AnalogueFeatured — top pair by match_pct)
 *
 *   ZONE E  On Radar — equalized TrendRailEqual (all cards same width + height)
 *
 *   ZONE F  Historical precedents (AnaloguesBand)
 *
 *   ZONE G  What's moving this vintage (WorldActivity)
 *
 * Route: /dashboard (the default Briefing page)
 * Async server component. revalidate = 300 — matches getLivePulse TTL.
 *
 * Candidate pages /briefing-signal, /briefing-editorial, /briefing-terminal
 * and ALL their component files are NOT touched.
 *
 * 2026-06-20 founder revisions:
 *   1. BriefingCommandBar stripped to wordmark only.
 *   2. Left-col nav-pill links removed.
 *   3. Left-col spotlight tiles removed.
 *   4. Hero card expanded with more generous spacing.
 *   5. Verdict color key moved to InteractiveLandscape controls row (HTML chips).
 *   6. Panel description replaced with plain-English copy (in InteractiveLandscape).
 *   7. Active count badge removed from landscape header (in InteractiveLandscape).
 *   8. Right rail contains AlarmsColumnFixed only (MoversColumn removed).
 *   9. MoversBand: horizontal full-width movers panel above AnalogueFeatured.
 *  10. ScopeFooter removed.
 *  11. Sidebar: "Sanctions Simulator" → "Sanctions Sim" (in Sidebar.tsx).
 * LAYOUT FIT: grid uses container-relative columns so right rail is visible at 1280px.
 */
import type { Metadata } from "next";
import type { Route } from "next";
import Link from "next/link";

import { getAllRecipes, vintageStamp } from "@/lib/te-mock/recipes";
import {
  buildHeroCountsV41,
  buildClosestMatches,
  buildTopPairTeasers,
  buildWorldActivityRows,
} from "@/lib/te-mock/dashboard-v4-1-data";
import { getTrendBoard } from "@/lib/hf/trend-board";
import { getLivePulse } from "@/lib/hf/live-pulse";
import { overlayCells } from "@/lib/hf/live-pulse-core";
import { getBucketArticles } from "@/lib/hf/live-pulse-buckets";
import type { LiveArticle } from "@/lib/hf/live-pulse-series";
import { deriveBriefingInsights } from "@/lib/dashboard/briefing-insights";
import { WorldActivity } from "@/components/dashboard-v4-1/WorldActivity";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

// Signal Board namespace — imported directly (read-only; untouched)
import type { HeroSignalData } from "@/components/briefing-signal/HeroSplit";
// AlarmsColumnFixed: hybrid copy with 11px gap-badge (QA fix — original frozen)
import { AlarmsColumnFixed } from "@/components/briefing-hybrid/AlarmsColumnFixed";
import type { ScatterPoint } from "@/components/briefing-signal/QuadrantSection";
import { AnaloguesBandHybrid } from "@/components/briefing-hybrid/AnaloguesBandHybrid";
import { SignalStatTile } from "@/components/briefing-signal/SignalStatTile";

// Editorial namespace — originals untouched; hybrid copy used on /dashboard
// import { AnalogueFeatured } from "@/components/briefing-editorial/AnalogueFeatured";

// Hybrid namespace — new components, no originals modified
import { AnalogueFeaturedHybrid } from "@/components/briefing-hybrid/AnalogueFeaturedHybrid";
import { BriefingCommandBar } from "@/components/briefing-hybrid/BriefingCommandBar";
import { InteractiveLandscapeWrapper } from "@/components/briefing-hybrid/InteractiveLandscapeWrapper";
import { TrendRailEqual } from "@/components/briefing-hybrid/TrendRailEqual";
import { MoversBand } from "@/components/briefing-hybrid/MoversBand";
import { HeroNewsPieces } from "@/components/briefing-hybrid/HeroNewsPieces";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Briefing · QG Intelligence",
  description:
    "Mission-control for geopolitical intelligence: signal landscape, hot signals, structural alarms, historical analogues, trend resemblances. One briefing.",
};

export default async function BriefingHybridPage() {
  // ── Structural data (sync) ─────────────────────────────────────────────────
  const recipes = getAllRecipes();
  const counts = buildHeroCountsV41(recipes);
  const matches = buildClosestMatches(8);
  const resemblanceBand = buildTopPairTeasers(2000).filter(
    (p) => p.match_pct >= 90 && p.match_pct < 98.5
  );
  const resemblances =
    resemblanceBand.length <= 6
      ? resemblanceBand
      : Array.from(
          { length: 6 },
          (_, i) => resemblanceBand[Math.round((i * (resemblanceBand.length - 1)) / 5)]
        );
  const activity = buildWorldActivityRows();

  // ── Trend board + live overlay ─────────────────────────────────────────────
  const hfBoard = getTrendBoard();
  const live = await getLivePulse();
  const overlaid = overlayCells(hfBoard, live);
  const liveCells = overlaid.cells;

  // ── Vintage ────────────────────────────────────────────────────────────────
  const vintage = vintageStamp();

  // ── Trends in play ─────────────────────────────────────────────────────────
  const inPlayCount = recipes.filter(
    (r) => r.status === "walked_no_graduation" || r.status === "live_legacy"
  ).length;

  // ── Briefing insights ──────────────────────────────────────────────────────
  const insights = deriveBriefingInsights();

  // ── Hot cell: loudest ACTIVE board cell ────────────────────────────────────
  type HotCell = {
    iso3: string;
    topicId: string;
    countryName: string;
    topicLabel: string;
    struct: number;
    pulse: number;
  };
  let hotCell: HotCell | null = null;
  {
    let bestSum = -1;
    for (const [key, cell] of Object.entries(liveCells)) {
      if (cell.verdict !== "ACTIVE") continue;
      const sum = (cell.struct ?? 0) + cell.pulse;
      if (sum <= bestSum) continue;
      const [iso3, topicId] = key.split("|");
      if (!iso3 || !topicId) continue;
      const country = hfBoard.countries.find((c) => c.iso3 === iso3);
      const topic = hfBoard.topics.find((t) => t.id === topicId);
      if (!country || !topic) continue;
      bestSum = sum;
      hotCell = {
        iso3,
        topicId,
        countryName: country.name,
        topicLabel: topic.label,
        struct: cell.struct ?? 0,
        pulse: cell.pulse,
      };
    }
  }

  // ── Live terminal iso ──────────────────────────────────────────────────────
  const liveTerminalIso: string = hotCell
    ? hotCell.iso3.toLowerCase()
    : (hfBoard.countries.find((c) => c.linkable)?.iso3.toLowerCase() ?? "gbr");

  // ── Derived counts ─────────────────────────────────────────────────────────
  const topAlarm = insights.silentAlarms[0] ?? null;
  const topRiser = insights.topRisers[0] ?? null;

  const activeCount = Object.values(liveCells).filter(
    (c) => c.verdict === "ACTIVE"
  ).length;

  // ── Hero signal derivation (identical to /briefing-signal) ─────────────────
  const heroSignal: HeroSignalData = (() => {
    if (hotCell) {
      const riserMatch =
        topRiser?.countryName === hotCell.countryName &&
        topRiser?.topicLabel === hotCell.topicLabel;
      const pulseSub =
        riserMatch && topRiser
          ? `↑ ${Math.round(topRiser.delta)} pts this month`
          : undefined;
      return {
        countryName: hotCell.countryName,
        topicLabel: hotCell.topicLabel,
        iso3: hotCell.iso3,
        stats: [
          {
            label: "News Pressure",
            value: String(Math.round(hotCell.pulse)),
            unit: "/100",
            sub: pulseSub,
            accentColor: "#E05C5C",
          },
          {
            label: "Structure",
            value: String(Math.round(hotCell.struct)),
            unit: "/100",
            sub: "structural read",
            accentColor: "var(--qgi-text-dim)",
          },
        ],
        headline: "The loudest signal on the board.",
        sentence:
          "Structural pressure and live news coverage are both elevated. This is the confirmed signal this release.",
        verdictLabel: "Both Firing",
        verdictBg: "rgba(224,92,92,0.12)",
        verdictColor: "#E05C5C",
        verdictBorder: "rgba(224,92,92,0.35)",
      };
    }

    if (topAlarm && topAlarm.gap >= 30) {
      return {
        countryName: topAlarm.countryName,
        topicLabel: topAlarm.topicLabel,
        iso3: topAlarm.iso3,
        stats: [
          {
            label: "Structure",
            value: String(Math.round(topAlarm.struct)),
            unit: "/100",
            sub: "structural read",
            accentColor: "var(--qgi-amber)",
          },
          {
            label: "News Pressure",
            value: String(Math.round(topAlarm.pulse)),
            unit: "/100",
            sub: "coverage so far",
            accentColor: "var(--qgi-text-dim)",
          },
          {
            label: "News Gap",
            value: `+${Math.round(topAlarm.gap)}`,
            unit: " pts",
            sub: "above the news pressure",
            accentColor: "var(--qgi-warning)",
            bgTint: "rgba(245,158,11,0.08)",
          },
        ],
        headline: "Structural signal elevated, news quiet.",
        sentence:
          "Structural resemblance is elevated while this month's news coverage stays quiet — two timeframes in divergence.",
        verdictLabel: "Divergence",
        verdictBg: "rgba(245,158,11,0.10)",
        verdictColor: "var(--qgi-amber)",
        verdictBorder: "rgba(245,158,11,0.30)",
      };
    }

    if (topRiser) {
      return {
        countryName: topRiser.countryName,
        topicLabel: topRiser.topicLabel,
        iso3: topRiser.iso3,
        stats: [
          {
            label: "Pressure Move",
            value: `+${Math.round(topRiser.delta)}`,
            sub: "points this month",
            accentColor: "var(--qgi-accent)",
          },
          {
            label: "News Pressure",
            value: String(Math.round(topRiser.pulse)),
            unit: "/100",
            accentColor: "var(--qgi-text-dim)",
          },
          ...(topRiser.struct > 0
            ? [
                {
                  label: "Structure",
                  value: String(Math.round(topRiser.struct)),
                  unit: "/100",
                  sub: "structural read",
                  accentColor: "var(--qgi-text-dim)" as string,
                },
              ]
            : []),
        ],
        headline: "The sharpest coverage move this month.",
        sentence: "Coverage is accelerating. Structural confirmation pending.",
        verdictLabel: "RISING",
        verdictBg: "rgba(56,189,248,0.10)",
        verdictColor: "var(--qgi-accent)",
        verdictBorder: "rgba(56,189,248,0.25)",
      };
    }

    return {
      countryName: `${inPlayCount} Trends`,
      topicLabel: "In Play",
      iso3: null,
      stats: [
        {
          label: "Trends in Play",
          value: String(inPlayCount),
          accentColor: "var(--qgi-text-dim)",
        },
        {
          label: "Total Recipes",
          value: String(counts.recipes_total),
          accentColor: "var(--qgi-text-dim)",
        },
      ],
      headline: `${inPlayCount} trends in play this release.`,
      sentence: `Structural resemblance scoring across ${counts.countries_scored} countries. Open any trend for the full signal set.`,
      verdictLabel: "QUARTERLY",
      verdictBg: "rgba(91,126,153,0.10)",
      verdictColor: "var(--qgi-text-dim)",
      verdictBorder: "rgba(91,126,153,0.25)",
    };
  })();

  // ── Hero news pieces — up to 3 recent articles for heroSignal country×topic ──
  let heroArticles: LiveArticle[] = [];
  if (heroSignal.iso3) {
    const raw = await getBucketArticles(heroSignal.iso3);
    heroArticles = raw
      .filter((a) => a.topicLabel === heroSignal.topicLabel)
      .sort((a, b) => b.dt.localeCompare(a.dt))
      .slice(0, 3);
  }

  // ── Scatter points for the interactive landscape ───────────────────────────
  const scatterPoints: ScatterPoint[] = [];
  for (const [key, cell] of Object.entries(liveCells)) {
    if (cell.struct === null) continue;
    const [iso3, topicId] = key.split("|");
    if (!iso3 || !topicId) continue;
    const country = hfBoard.countries.find((c) => c.iso3 === iso3);
    const topic = hfBoard.topics.find((t) => t.id === topicId);
    if (!country || !topic) continue;
    scatterPoints.push({
      struct: cell.struct,
      pulse: cell.pulse,
      countryName: country.name,
      topicLabel: topic.label,
      verdict: cell.verdict,
    });
  }

  // ── Top analogue pair for Editorial feature ────────────────────────────────
  // Derive from buildTopPairTeasers — highest match_pct in the 85–98.5 range.
  const allPairs = buildTopPairTeasers(2000);
  const topAnalogue =
    allPairs
      .filter((p) => p.match_pct >= 85 && p.match_pct < 98.5)
      .sort((a, b) => b.match_pct - a.match_pct)[0] ??
    allPairs[0] ??
    null;

  return (
    <div
      style={{
        minHeight: "100%",
        background: "var(--qgi-bg)",
        color: "var(--qgi-text)",
      }}
    >
      {/* ── ZONE A: Briefing Command Bar ─────────────────────────────────── */}
      <BriefingCommandBar
        vintage={vintage}
        inPlayCount={inPlayCount}
        liveStatus={live.status}
      />

      <div
        style={{
          maxWidth: "1440px",
          margin: "0 auto",
          padding: "0 20px 64px",
        }}
      >
        <style>{`
          /*
           * ── ZONE B: Responsive three-column grid ──────────────────────────
           *
           * LAYOUT FIT STRATEGY (2026-06-20):
           * The app-sidebar is ~224px (expanded) or 56px (collapsed). At 1280px
           * total window width the content area available to the dashboard grid
           * is roughly 1280 - 224 - 40px padding = ~1016px. We use a
           * container-relative sizing: fixed left (~260px) + 1fr center +
           * fixed right (~230px) with a 12px gap on each side. Total =
           * 260 + 12 + [auto] + 12 + 230 = 514px taken; center gets the rest.
           * At 1016px content width this gives center ~502px which is healthy.
           * The right rail therefore ALWAYS appears on laptops at ≥1280px —
           * we never hide it.
           *
           * The old @media (max-width: 1439px) { display: none } rule is
           * replaced by a narrower breakpoint that only hides below 900px
           * (tablet portrait). At that point we drop to 2-col (left + center).
           * Below 768px mobile we drop to 1-col (center only).
           */
          .qgi-bh-main-grid {
            display: grid;
            grid-template-columns: 260px minmax(0, 1fr) 230px;
            gap: 12px;
            align-items: stretch;
            padding: 20px 0 0;
          }
          .qgi-bh-right-rail {
            display: flex;
          }
          @media (max-width: 900px) {
            .qgi-bh-main-grid {
              grid-template-columns: 240px minmax(0, 1fr);
            }
            .qgi-bh-right-rail {
              display: none !important;
            }
          }
          @media (max-width: 767px) {
            .qgi-bh-main-grid {
              grid-template-columns: 1fr;
            }
            .qgi-bh-left-col {
              display: none;
            }
          }
          /* ── Narrow viewport fallback: alarms below landscape ────────── */
          .qgi-bh-intel-mobile { display: none; }
          @media (max-width: 900px) {
            .qgi-bh-intel-mobile { display: block; }
          }
          /* ── Nav pill hover ──────────────────────────────────────────── */
          .qgi-bh-nav-pill:hover {
            background: rgba(91,126,153,0.22) !important;
            border-color: rgba(91,126,153,0.5) !important;
          }
        `}</style>

        {/* ── ZONE B: Main three-column spatial grid ─────────────────────── */}
        <div className="qgi-bh-main-grid">
          {/* LEFT: Hot-signal hero — expanded, more generous spacing */}
          <div
            className="qgi-bh-left-col"
            style={{ display: "flex", flexDirection: "column", gap: "0", height: "100%" }}
          >
            {/* Hot signal card — stretches to fill the full column height */}
            <div
              style={{
                padding: "24px",
                background: "var(--qgi-surface)",
                border: "1px solid var(--qgi-border)",
                borderLeft: `4px solid ${heroSignal.verdictColor}`,
                borderRadius: "10px",
                display: "flex",
                flexDirection: "column",
                gap: "0",
                flex: 1,
                minHeight: "320px",
                boxSizing: "border-box",
              }}
            >
              {/* Verdict chip */}
              <div style={{ marginBottom: "18px" }}>
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    letterSpacing: "1.5px",
                    textTransform: "uppercase",
                    fontFamily: "ui-monospace, monospace",
                    padding: "2px 8px",
                    borderRadius: "3px",
                    background: heroSignal.verdictBg,
                    color: heroSignal.verdictColor,
                    border: `1px solid ${heroSignal.verdictBorder}`,
                  }}
                >
                  {heroSignal.verdictLabel}
                </span>
              </div>

              {/* Country + topic row */}
              {heroSignal.iso3 && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "7px",
                    marginBottom: "14px",
                    flexWrap: "wrap",
                  }}
                >
                  <FlagImg
                    emoji={flagFor(heroSignal.countryName)}
                    name={heroSignal.countryName}
                    width={20}
                    radius={2}
                  />
                  <span
                    style={{
                      fontSize: "16px",
                      fontWeight: 600,
                      color: "var(--qgi-text)",
                    }}
                  >
                    {heroSignal.countryName}
                  </span>
                  <span style={{ color: "var(--qgi-border)", fontSize: "14px" }}>·</span>
                  <span style={{ fontSize: "13px", color: "var(--qgi-text-muted)" }}>
                    {heroSignal.topicLabel}
                  </span>
                </div>
              )}

              {/* H1 — larger, more prominent */}
              <h1
                style={{
                  fontSize: "clamp(24px, 2.4vw, 32px)",
                  fontWeight: 700,
                  lineHeight: 1.1,
                  letterSpacing: "-0.5px",
                  margin: "0 0 20px",
                  color: "var(--qgi-text)",
                }}
              >
                {heroSignal.headline}
              </h1>

              {/* Stat cluster — single connected row (News Pulse | Structure) */}
              {heroSignal.stats.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "stretch",
                    gap: "1px",
                    marginBottom: "18px",
                    flexWrap: "nowrap",
                  }}
                >
                  {heroSignal.stats.map((stat, i) => (
                    <SignalStatTile
                      key={stat.label}
                      label={stat.label}
                      value={stat.value}
                      unit={stat.unit}
                      sub={stat.sub}
                      accentColor={stat.accentColor}
                      bgTint={stat.bgTint}
                      isFirst={i === 0}
                      isLast={i === heroSignal.stats.length - 1}
                    />
                  ))}
                </div>
              )}

              {/* Editorial sentence */}
              <p
                style={{
                  fontSize: "14px",
                  color: "var(--qgi-text-muted)",
                  margin: "0 0 16px",
                  lineHeight: 1.6,
                }}
              >
                {heroSignal.sentence}
              </p>

              {/* In the news — up to 3 recent headlines for this country×topic */}
              <HeroNewsPieces articles={heroArticles} />

              {/* CTA links */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                  flexWrap: "wrap",
                  fontSize: "12px",
                  fontFamily: "ui-monospace, monospace",
                  marginTop: "24px",
                }}
              >
                <Link
                  href={"/risk-board" as Route}
                  style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
                >
                  Full board →
                </Link>
                <span style={{ color: "var(--qgi-border)", padding: "0 3px" }}>·</span>
                <Link
                  href={`/countries/${liveTerminalIso}` as Route}
                  style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
                >
                  Terminal →
                </Link>
              </div>
            </div>
          </div>

          {/* CENTER: Interactive Signal Landscape */}
          <div>
            <InteractiveLandscapeWrapper
              points={scatterPoints}
              activeCount={activeCount}
              inPlayCount={inPlayCount}
              silentAlarmCount={insights.silentAlarms.length}
            />
          </div>

          {/* RIGHT RAIL: Alarms only — MoversColumn removed */}
          <div
            className="qgi-bh-right-rail"
            style={{ flexDirection: "column", gap: "16px", height: "100%" }}
          >
            <AlarmsColumnFixed alarms={insights.silentAlarms} />
          </div>
        </div>

        {/* ── Narrow viewport: alarms visible when right rail hides ────────── */}
        <div className="qgi-bh-intel-mobile" style={{ marginTop: "20px" }}>
          <AlarmsColumnFixed alarms={insights.silentAlarms} />
        </div>

        {/* ── ZONE C: Biggest Movers — horizontal full-width band ───────────── */}
        <section style={{ marginTop: "28px" }}>
          <MoversBand
            risers={insights.topRisers}
            fallers={insights.topFallers}
            loudestTopicLabel={insights.loudestTopicLabel}
            loudestTopicPulse={insights.loudestTopicPulse}
          />
        </section>

        {/* ── ZONE D: Editorial ANALOGUE feature — hybrid copy (em-dash fix + chart clip fix) */}
        {topAnalogue && (
          <section style={{ marginTop: "32px" }}>
            <AnalogueFeaturedHybrid pair={topAnalogue} />
          </section>
        )}

        {/* ── ZONE E: On Radar — equalized card rail ───────────────────────── */}
        <section style={{ marginTop: "32px" }}>
          <TrendRailEqual matches={matches} inPlayCount={inPlayCount} />
        </section>

        {/* ── ZONE F: Historical precedents ─────────────────────────────────── */}
        <section style={{ marginTop: "32px" }}>
          <AnaloguesBandHybrid pairs={resemblances} />
        </section>

        {/* ── ZONE G: What's Moving This Release (WorldActivity has its own title) ── */}
        <section style={{ marginTop: "32px" }}>
          <WorldActivity rows={activity} />
        </section>

        {/* ScopeFooter removed (item 10). */}
      </div>
    </div>
  );
}
