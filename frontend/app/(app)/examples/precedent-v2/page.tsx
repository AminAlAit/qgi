"use client";

/**
 * EXAMPLE / PROTOTYPE: Precedent Detail V2
 * Demonstrates the redesigned precedent detail page from
 * ux-consult-precedent-detail-2026-04-16.md
 *
 * Hardcoded sample: Iraq -- Civil War and Insurgency
 *
 * 2026-04-24: route marked noindex so Google doesn't surface stale
 * V1.8.1-era prototype content. Full disposition decision (keep / move
 * / delete) tracked on the QA follow-up ticket. See also: metadata
 * export below.
 */

import { CountryFlag } from "@/components/design/CountryFlag";
import { InfoTooltip } from "@/components/design/InfoTooltip";

/* ------------------------------------------------------------------ */
/*  Sample data                                                        */
/* ------------------------------------------------------------------ */

const COUNTRY = {
  name: "Iraq",
  alpha2: "IQ",
  category: "Civil War and Insurgency",
  l1Group: "L1-A",
  l1Label: "Conflict & Security",
  salience: 2.31,
  percentile: 97,
  tier: "HIGH RISK",
  totalAnalogues: 187,
};

const TWINS = [
  {
    name: "Afghanistan",
    alpha2: "AF",
    matchScore: 94,
    leadYears: 2,
    length: 14,
    indicatorCount: 7,
    eventYear: 2001,
    eventLabel: "US invasion & Taliban overthrow",
    pps: 0.94,
    windowStart: 1988,
    windowEnd: 2001,
  },
  {
    name: "Syria",
    alpha2: "SY",
    matchScore: 91,
    leadYears: 3,
    length: 11,
    indicatorCount: 6,
    eventYear: 2011,
    eventLabel: "Syrian civil war outbreak",
    pps: 0.91,
    windowStart: 2000,
    windowEnd: 2011,
  },
  {
    name: "Libya",
    alpha2: "LY",
    matchScore: 87,
    leadYears: 2,
    length: 9,
    indicatorCount: 5,
    eventYear: 2011,
    eventLabel: "First Libyan civil war",
    pps: 0.87,
    windowStart: 2002,
    windowEnd: 2011,
  },
  {
    name: "Yemen",
    alpha2: "YE",
    matchScore: 83,
    leadYears: 4,
    length: 12,
    indicatorCount: 5,
    eventYear: 2015,
    eventLabel: "Yemen civil war escalation",
    pps: 0.83,
    windowStart: 2003,
    windowEnd: 2015,
  },
  {
    name: "Lebanon",
    alpha2: "LB",
    matchScore: 78,
    leadYears: 3,
    length: 10,
    indicatorCount: 4,
    eventYear: 2019,
    eventLabel: "Economic collapse & protests",
    pps: 0.78,
    windowStart: 2009,
    windowEnd: 2019,
  },
];

const TIER_DATA = [
  { tier: "S", label: "Short (3-8yr)", count: 98, salience: 2.41, color: "#f87171" },
  { tier: "M", label: "Medium (9-20yr)", count: 62, salience: 2.08, color: "#fbbf24" },
  { tier: "L", label: "Long (21-40yr)", count: 21, salience: 1.67, color: "#38bdf8" },
  {
    tier: "XL",
    label: "Institutional (41+yr)",
    count: 6,
    salience: 1.23,
    color: "#a78bfa",
  },
];

const METRICS = [
  {
    label: "Precedent Windows",
    value: "187",
    tooltip:
      "Total number of historical analogue patterns linking Iraq to other countries in the Civil War category.",
  },
  {
    label: "Peak Salience",
    value: "2.31",
    tooltip:
      "Maximum salience score across all pattern tiers. Scores above 1.2 are considered high-signal.",
  },
  {
    label: "Active Tiers",
    value: "4 / 4",
    tooltip:
      "Number of pattern-length tiers (S/M/L/XL) with at least one active precedent window.",
  },
  {
    label: "Last Event Year",
    value: "2019",
    tooltip: "Most recent curated event year among the top analogues for this category.",
  },
];

const LEAD_TIME_BINS = [
  { years: "1y", count: 42, pct: 22 },
  { years: "2y", count: 58, pct: 31 },
  { years: "3y", count: 39, pct: 21 },
  { years: "4y", count: 27, pct: 14 },
  { years: "5y", count: 14, pct: 8 },
  { years: "6+", count: 7, pct: 4 },
];

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function PrecedentV2Page() {
  const maxCount = Math.max(...TIER_DATA.map((t) => t.count));

  return (
    <div
      className="min-h-screen p-6 lg:p-10"
      style={{ backgroundColor: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <div className="max-w-7xl mx-auto space-y-8">
        {/* ---- Prototype badge ---- */}
        <div
          className="inline-block px-3 py-1 rounded text-[10px] tracking-widest uppercase"
          style={{
            backgroundColor: "rgba(251, 191, 36, 0.15)",
            color: "#fbbf24",
            border: "1px solid rgba(251, 191, 36, 0.3)",
          }}
        >
          UX PROTOTYPE -- NOT LIVE DATA
        </div>

        {/* ---- Breadcrumb ---- */}
        <div
          className="text-[11px] tracking-wider"
          style={{ color: "var(--qgi-text-dim)" }}
        >
          Countries / Iraq / {COUNTRY.l1Label} / {COUNTRY.category}
        </div>

        {/* ============================================================ */}
        {/*  HERO HEADER                                                 */}
        {/* ============================================================ */}
        <section
          className="rounded-xl p-6 lg:p-8"
          style={{
            backgroundColor: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          <div className="flex flex-wrap items-start justify-between gap-6">
            {/* Left: identity */}
            <div className="flex items-center gap-4">
              <CountryFlag alpha2={COUNTRY.alpha2} size={40} />
              <div>
                <div
                  className="text-[10px] tracking-widest uppercase mb-1"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  {COUNTRY.l1Group} {COUNTRY.l1Label}
                </div>
                <h1 className="text-2xl font-semibold tracking-wide">
                  {COUNTRY.name.toUpperCase()}
                </h1>
                <div className="text-sm mt-1" style={{ color: "var(--qgi-text-muted)" }}>
                  {COUNTRY.category}
                </div>
              </div>
            </div>

            {/* Right: tier + salience */}
            <div className="flex items-center gap-6">
              <span
                className="px-3 py-1.5 rounded text-[11px] tracking-widest font-semibold"
                style={{
                  backgroundColor: "rgba(248, 113, 113, 0.15)",
                  color: "#f87171",
                  border: "1px solid rgba(248, 113, 113, 0.3)",
                }}
              >
                {COUNTRY.tier}
              </span>
              <div className="text-right">
                <div
                  className="font-data text-3xl font-bold"
                  style={{ color: "#f87171" }}
                >
                  {COUNTRY.salience.toFixed(2)}
                </div>
                <div
                  className="text-[10px] tracking-wider"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  SALIENCE -- p{COUNTRY.percentile}
                </div>
              </div>
            </div>
          </div>

          {/* ---- Narrative lede ---- */}
          <div
            className="mt-6 p-5 rounded-lg text-sm leading-relaxed"
            style={{
              backgroundColor: "var(--qgi-surface-2)",
              borderLeft: "3px solid var(--qgi-accent)",
              color: "var(--qgi-text)",
            }}
          >
            Iraq&apos;s conflict indicators since 2003 most strongly mirror Afghanistan
            (1988-2001), which culminated in a full-scale foreign military intervention in
            2001. Four of the five strongest analogues experienced a civil-war-class event
            within 3 years of pattern end. QGI flags this as a{" "}
            <strong style={{ color: "#f87171" }}>high-density</strong> signal.
          </div>

          {/* ---- Actions rail ---- */}
          <div className="mt-5 flex flex-wrap gap-3">
            {["Download CSV", "Share card", "Open patterns view"].map((action) => (
              <button
                key={action}
                className="px-4 py-2 rounded text-[11px] tracking-wider transition-colors"
                style={{
                  backgroundColor: "var(--qgi-surface-2)",
                  color: "var(--qgi-text-muted)",
                  border: "1px solid var(--qgi-border)",
                }}
              >
                {action}
              </button>
            ))}
          </div>
        </section>

        {/* ============================================================ */}
        {/*  KEY METRICS ROW                                              */}
        {/* ============================================================ */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {METRICS.map((m) => (
            <div
              key={m.label}
              className="rounded-lg p-4"
              style={{
                backgroundColor: "var(--qgi-surface)",
                border: "1px solid var(--qgi-border)",
              }}
            >
              <div className="flex items-center gap-1 mb-2">
                <span
                  className="text-[10px] tracking-widest uppercase"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  {m.label}
                </span>
                <InfoTooltip text={m.tooltip} />
              </div>
              <div
                className="font-data text-2xl font-bold"
                style={{ color: "var(--qgi-text)" }}
              >
                {m.value}
              </div>
            </div>
          ))}
        </section>

        {/* ============================================================ */}
        {/*  TWINS PANEL                                                  */}
        {/* ============================================================ */}
        <section>
          <div className="flex items-baseline justify-between mb-4">
            <h2
              className="text-[11px] tracking-widest uppercase font-semibold"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              TOP 5 HISTORICAL ANALOGUES
            </h2>
            <span
              className="text-[11px] font-data"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              5 of {COUNTRY.totalAnalogues}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {TWINS.map((twin, i) => (
              <div
                key={twin.alpha2}
                className="rounded-xl p-4 flex flex-col gap-3 transition-colors hover:border-[var(--qgi-accent)]"
                style={{
                  backgroundColor: "var(--qgi-surface)",
                  border: `1px solid ${i === 0 ? "var(--qgi-accent)" : "var(--qgi-border)"}`,
                }}
              >
                {/* Country identity */}
                <div className="flex items-center gap-2">
                  <CountryFlag alpha2={twin.alpha2} size={20} />
                  <div>
                    <div className="text-xs font-semibold">{twin.name}</div>
                    <div
                      className="text-[10px] font-data"
                      style={{ color: "var(--qgi-text-dim)" }}
                    >
                      {twin.windowStart}-{twin.windowEnd}
                    </div>
                  </div>
                </div>

                {/* Mini sparkline placeholder */}
                <div
                  className="h-10 rounded flex items-end gap-px px-1"
                  style={{ backgroundColor: "var(--qgi-surface-2)" }}
                >
                  {Array.from({ length: twin.length }, (_, j) => {
                    const h = 8 + Math.sin((j * 1.3 + i) * 0.7) * 12 + Math.random() * 6;
                    return (
                      <div
                        key={j}
                        className="flex-1 rounded-t"
                        style={{
                          height: `${Math.max(4, h)}px`,
                          backgroundColor:
                            j === twin.length - 1 ? "#f87171" : "var(--qgi-accent)",
                          opacity: j === twin.length - 1 ? 1 : 0.4,
                        }}
                      />
                    );
                  })}
                </div>

                {/* Event marker */}
                <div
                  className="text-[10px] text-center tracking-wider"
                  style={{ color: "#f87171" }}
                >
                  EVENT {twin.eventYear}
                </div>

                {/* Stats */}
                <div
                  className="space-y-1 text-[11px] font-data"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  <div className="flex justify-between">
                    <span>Match</span>
                    <span className="font-semibold" style={{ color: "var(--qgi-text)" }}>
                      {twin.matchScore}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Lead</span>
                    <span>{twin.leadYears}y</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Length</span>
                    <span>{twin.length}y</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Indic.</span>
                    <span>{twin.indicatorCount}</span>
                  </div>
                </div>

                {/* Divider + view link */}
                <div
                  className="pt-2 mt-auto border-t text-center"
                  style={{ borderColor: "var(--qgi-border)" }}
                >
                  <span
                    className="text-[10px] tracking-widest cursor-pointer"
                    style={{ color: "var(--qgi-accent)" }}
                  >
                    View pattern &rarr;
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 text-right">
            <span
              className="text-[11px] tracking-wider cursor-pointer"
              style={{ color: "var(--qgi-accent)" }}
            >
              Show all {COUNTRY.totalAnalogues} analogues &rarr;
            </span>
          </div>
        </section>

        {/* ============================================================ */}
        {/*  TIER BREAKDOWN BARS                                          */}
        {/* ============================================================ */}
        <section
          className="rounded-xl p-6"
          style={{
            backgroundColor: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          <h2
            className="text-[11px] tracking-widest uppercase font-semibold mb-5"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            PATTERN LENGTH DISTRIBUTION
            <InfoTooltip text="Distribution of pattern lengths (in years) across all precedent windows for this country/category. Short patterns (3-8yr) detect policy cycles; long patterns (21+yr) detect structural trajectories. A wide spread means the signal is robust across time horizons." />
          </h2>

          <div className="space-y-3">
            {TIER_DATA.map((t) => (
              <div key={t.tier} className="flex items-center gap-4">
                <span
                  className="w-6 text-center font-data text-xs font-bold"
                  style={{ color: t.color }}
                >
                  {t.tier}
                </span>
                <span
                  className="w-32 text-[10px] tracking-wider"
                  style={{ color: "var(--qgi-text-dim)" }}
                >
                  {t.label}
                </span>
                <div
                  className="flex-1 h-5 rounded relative"
                  style={{ backgroundColor: "var(--qgi-surface-2)" }}
                >
                  <div
                    className="h-full rounded"
                    style={{
                      width: `${(t.count / maxCount) * 100}%`,
                      backgroundColor: t.color,
                      opacity: 0.7,
                    }}
                  />
                </div>
                <span
                  className="font-data text-xs w-16 text-right"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  {t.count} prec.
                </span>
                <span
                  className="font-data text-xs w-14 text-right"
                  style={{ color: t.color }}
                >
                  {t.salience.toFixed(2)}
                </span>
              </div>
            ))}
          </div>

          <div
            className="mt-4 text-[10px] tracking-wider"
            style={{ color: "var(--qgi-text-dim)" }}
          >
            Click a tier to filter the analogues panel above
          </div>
        </section>

        {/* ============================================================ */}
        {/*  LEAD-TIME DISTRIBUTION                                       */}
        {/* ============================================================ */}
        <section
          className="rounded-xl p-6"
          style={{
            backgroundColor: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          <div className="flex items-baseline justify-between mb-5">
            <h2
              className="text-[11px] tracking-widest uppercase font-semibold"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              LEAD-TIME DISTRIBUTION
              <InfoTooltip text="How many years before the actual event did the analogue pattern start flagging? A 3-year lead time means QGI's pattern match began 3 years before Country B's known event. Longer lead times = more advance warning, but also more false-positive risk." />
            </h2>
            <span
              className="text-[11px] tracking-wider italic"
              style={{ color: "var(--qgi-text-dim)" }}
            >
              &ldquo;How early did QGI flag?&rdquo;
            </span>
          </div>

          <div className="space-y-2">
            {LEAD_TIME_BINS.map((b) => (
              <div key={b.years} className="flex items-center gap-3">
                <span
                  className="font-data text-xs w-8 text-right"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  {b.years}
                </span>
                <div
                  className="flex-1 h-5 rounded relative"
                  style={{ backgroundColor: "var(--qgi-surface-2)" }}
                >
                  <div
                    className="h-full rounded"
                    style={{
                      width: `${b.pct * 3.2}%`,
                      backgroundColor: "var(--qgi-accent)",
                      opacity: 0.7,
                    }}
                  />
                </div>
                <span
                  className="font-data text-xs w-8 text-right"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  {b.count}
                </span>
              </div>
            ))}
          </div>

          <div
            className="mt-5 text-sm leading-relaxed"
            style={{ color: "var(--qgi-text-muted)" }}
          >
            Median lead: <strong style={{ color: "var(--qgi-text)" }}>2 years</strong>. Of
            the {COUNTRY.totalAnalogues} analogue patterns,{" "}
            <strong style={{ color: "var(--qgi-text)" }}>74%</strong> led the event by 3
            years or less.
          </div>
        </section>

        {/* ============================================================ */}
        {/*  METHODOLOGY FOOTER                                           */}
        {/* ============================================================ */}
        <footer
          className="rounded-lg p-4 text-[10px] tracking-wider leading-relaxed"
          style={{
            backgroundColor: "var(--qgi-surface)",
            color: "var(--qgi-text-dim)",
            border: "1px solid var(--qgi-border)",
          }}
        >
          V1.8.1 z-score + RRF &middot; Pattern correlation Pearson r &ge; 0.65 &middot;
          &plusmn;15% event window &middot; Salience &gt; 1.2 considered
          &ldquo;high-signal&rdquo; &middot; Event source: qgi-data/curated &middot; 88
          countries curated &middot; Last updated 2026-04-13
        </footer>
      </div>
    </div>
  );
}
