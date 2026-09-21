/**
 * Top-of-page glossary (#527).
 *
 * 5 plain-English term definitions, each paired with a small inline visual
 * that conveys the concept at a glance. Anchored so the rest of the page
 * can deep-link back.
 *
 * SCDI = "Single Correlating Dyadic Index" (founder-correct as of 2026-04-29).
 */

import { TOTAL_INDICATORS, TOTAL_INDICATOR_PROVIDERS } from "@/lib/site-stats";

const TERMS: { id: string; short: string; long: string; visual: React.ReactNode }[] = [
  {
    id: "event",
    short: "Event",
    long: "A historical incident QGI tracks against a country's indicator trajectory: for example, Brazil's 2018 presidential election, the 2008 Icelandic banking collapse, the 2011 Bahraini uprising. Every event is verified against a public source.",
    visual: <CalendarDot />,
  },
  {
    id: "indicator",
    short: "Indicator",
    long: `A single time-series QGI ingests: GDP per capita, V-Dem polyarchy score, Gini coefficient, FAOSTAT food-price index. Currently ${TOTAL_INDICATORS} indicators across ${TOTAL_INDICATOR_PROVIDERS} sources.`,
    visual: <Sparkline />,
  },
  {
    id: "scdi",
    short: "SCDI",
    long: "Single Correlating Dyadic Index. The atomic unit of co-movement: when country A's trajectory on one indicator matches country B's, year-aligned at offset N, with Pearson correlation ≥ 0.5. Billions of these get computed per pipeline run.",
    visual: <CorrelatedLines />,
  },
  {
    id: "pattern",
    short: "Pattern",
    long: "A repeated co-movement across multiple indicators, when several SCDIs link the same country pair at the same time offset. Patterns are stronger evidence than any single SCDI.",
    visual: <Branching />,
  },
  {
    id: "recipe",
    short: "Trend",
    long: "The canonical shape distilled from multiple Patterns. A trend says: this country's current trajectory resembles the trajectory of a country that went on to experience a given kind of event. Trends are the basis for every country reading on the live site.",
    visual: <Fingerprint />,
  },
];

export default function Glossary() {
  return (
    <section
      id="glossary"
      className="py-10 border-b"
      style={{ borderColor: "var(--qgi-border)" }}
    >
      <h2
        className="text-xs tracking-[0.25em] uppercase mb-6"
        style={{ color: "var(--qgi-text-muted)" }}
      >
        Five terms used on this page
      </h2>
      <dl className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        {TERMS.map((t) => (
          <div key={t.id} id={t.id} className="scroll-mt-20">
            <div
              className="rounded-lg border p-3 mb-3 flex items-center justify-center h-20"
              style={{
                backgroundColor: "var(--qgi-surface)",
                borderColor: "var(--qgi-border)",
              }}
              aria-hidden
            >
              {t.visual}
            </div>
            <dt
              className="font-data text-sm tracking-wide mb-2"
              style={{ color: "var(--qgi-accent)" }}
            >
              {t.short}
            </dt>
            <dd
              className="text-[12px] leading-relaxed"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              {t.long}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// ─── Visual icons (inline SVG, no external deps) ──────────────────────────

function CalendarDot() {
  return (
    <svg viewBox="0 0 80 60" className="w-full h-full">
      {/* Calendar grid */}
      <rect
        x="10"
        y="14"
        width="60"
        height="38"
        rx="3"
        fill="none"
        stroke="#5a6270"
        strokeWidth="1"
      />
      <line x1="10" y1="22" x2="70" y2="22" stroke="#5a6270" strokeWidth="1" />
      <line x1="22" y1="10" x2="22" y2="18" stroke="#5a6270" strokeWidth="1" />
      <line x1="58" y1="10" x2="58" y2="18" stroke="#5a6270" strokeWidth="1" />
      {/* Grid dots */}
      {[28, 38, 48, 58].map((y) =>
        [20, 30, 40, 50, 60].map((x) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r="1.2" fill="#5a6270" />
        ))
      )}
      {/* Highlighted event */}
      <circle cx="40" cy="38" r="4" fill="#FF6B35" />
      <circle
        cx="40"
        cy="38"
        r="6"
        fill="none"
        stroke="#FF6B35"
        strokeWidth="1"
        opacity="0.4"
      />
    </svg>
  );
}

function Sparkline() {
  // Single time-series — meandering line
  const pts = [
    [4, 35],
    [12, 32],
    [20, 38],
    [28, 28],
    [36, 30],
    [44, 22],
    [52, 26],
    [60, 16],
    [68, 20],
    [76, 14],
  ];
  const d = "M " + pts.map((p) => p.join(" ")).join(" L ");
  return (
    <svg viewBox="0 0 80 50" className="w-full h-full">
      <path
        d={d}
        fill="none"
        stroke="#7B5EE6"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {pts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="1.4" fill="#7B5EE6" />
      ))}
    </svg>
  );
}

function CorrelatedLines() {
  // Two parallel-ish lines (correlated trajectories)
  const a = [
    [4, 30],
    [14, 26],
    [24, 32],
    [34, 22],
    [44, 26],
    [54, 18],
    [64, 22],
    [76, 14],
  ];
  const b = [
    [4, 40],
    [14, 36],
    [24, 42],
    [34, 32],
    [44, 36],
    [54, 28],
    [64, 32],
    [76, 24],
  ];
  const dA = "M " + a.map((p) => p.join(" ")).join(" L ");
  const dB = "M " + b.map((p) => p.join(" ")).join(" L ");
  return (
    <svg viewBox="0 0 80 50" className="w-full h-full">
      <path d={dA} fill="none" stroke="#FF6B35" strokeWidth="1.6" strokeLinecap="round" />
      <path d={dB} fill="none" stroke="#5BA8E8" strokeWidth="1.6" strokeLinecap="round" />
      {/* Ghost connector showing dyadic */}
      {a.map(([ax, ay], i) => {
        const [bx, by] = b[i];
        return (
          <line
            key={i}
            x1={ax}
            y1={ay}
            x2={bx}
            y2={by}
            stroke="#5a6270"
            strokeWidth="0.4"
            strokeDasharray="1,1.5"
          />
        );
      })}
    </svg>
  );
}

function Branching() {
  // Pattern = several SCDIs (multiple lines bundling at one point)
  return (
    <svg viewBox="0 0 80 50" className="w-full h-full">
      {/* Hub */}
      <circle cx="20" cy="25" r="3" fill="#7B5EE6" />
      {/* Spokes */}
      {[
        [60, 8],
        [70, 18],
        [70, 32],
        [60, 42],
      ].map(([x, y], i) => (
        <g key={i}>
          <line x1="22" y1="25" x2={x} y2={y} stroke="#7B5EE6" strokeWidth="1.2" />
          <circle cx={x} cy={y} r="2" fill="none" stroke="#7B5EE6" strokeWidth="1.2" />
        </g>
      ))}
      <text x="20" y="46" textAnchor="middle" fontSize="6" fill="#a1a8b3">
        A
      </text>
    </svg>
  );
}

function Fingerprint() {
  // Concentric arcs evoking a fingerprint
  return (
    <svg viewBox="0 0 80 50" className="w-full h-full">
      {[8, 12, 16, 20].map((r, i) => (
        <ellipse
          key={i}
          cx="40"
          cy="25"
          rx={r * 1.6}
          ry={r}
          fill="none"
          stroke="#FF6B35"
          strokeWidth="1.1"
          opacity={0.85 - i * 0.15}
        />
      ))}
      <circle cx="40" cy="25" r="2" fill="#FF6B35" />
    </svg>
  );
}
