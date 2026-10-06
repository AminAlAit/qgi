/**
 * Verification process flow (#526, refactored 2026-04-29).
 *
 * Three stages: Fetch → Curate → Verify, each with a concrete worked example
 * so a reader can see exactly what changes step-to-step. Stats below follow
 * the metric-card theme.
 */
import stats from "@/data/methodology-stats.json";

const STEPS = [
  {
    n: 1,
    title: "Fetch",
    summary: "Pull the candidate event from a public source.",
    detail:
      "An LLM agent does a guided web search across Wikipedia, IMF, HRW, UN, government archives, and news of record. The raw text is captured along with the URL.",
    example: {
      stage: "Raw fetch from Wikipedia",
      lines: [
        "Country: Iceland",
        "Year: 2008",
        'Body: "In October 2008, the three major Icelandic banks ...',
        '       were placed in receivership ..."',
      ],
    },
  },
  {
    n: 2,
    title: "Curate",
    summary: "Reduce to a structured event matching QGI's schema.",
    detail:
      "The agent extracts a single canonical title, year, category from QGI's 71-category taxonomy, and a 1-2 sentence description. No web access during this stage; it is pure structural cleanup.",
    example: {
      stage: "After E1–E5 cleanup rules applied",
      lines: [
        '"year": 2008,',
        '"title": "Banking System Collapses in Three Days"',
        '"category": "banking_and_financial_crisis"',
        '"description": "Glitnir, Landsbanki, Kaupthing into receivership ..."',
      ],
    },
  },
  {
    n: 3,
    title: "Verify",
    summary: "Independent web-search pass confirms every event.",
    detail:
      "A separate LLM agent re-checks each curated event with 1–2 web queries. It records a verdict (TRUE / FALSE), a 1-2 sentence reason, and the cited source URL. Only TRUE-verdict events land in the data lake.",
    example: {
      stage: "Verdict written to events/verification/iceland.json",
      lines: [
        '"verdict": "TRUE",',
        '"reason": "Glitnir nationalized 2008-09-29; Landsbanki + Kaupthing 10-07/09 ...",',
        '"source": "https://en.wikipedia.org/wiki/2008–2011_Icelandic_financial_crisis"',
      ],
    },
  },
];

const PASS_RATE_PCT = 96.5;

const FLOW_CARDS = [
  {
    value: stats.total_verified_events.toLocaleString(),
    label: "Verified events",
    sublabel: "after the gate",
  },
  { value: `${PASS_RATE_PCT}%`, label: "Pass rate", sublabel: "TRUE / (TRUE + FALSE)" },
  {
    value: stats.unique_source_urls.toLocaleString(),
    label: "Distinct source URLs",
    sublabel: "no fabricated links",
  },
  {
    value: stats.unique_source_domains.toLocaleString(),
    label: "Source domains",
    sublabel: "wikipedia + ~785 others",
  },
];

export default function VerificationFlow() {
  return (
    <div>
      <p
        className="text-sm mb-10 leading-relaxed max-w-2xl"
        style={{ color: "var(--qgi-text)" }}
      >
        Three independent stages between finding an event on the web and adding it to the
        record. The same event, the 2008 Icelandic banking collapse, is shown at every
        stage.
      </p>

      {/* Three steps in a row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {STEPS.map((step, i) => (
          <div key={step.n} className="relative">
            <div
              className="rounded-lg border p-5 h-full"
              style={{
                borderColor: "var(--qgi-border)",
                backgroundColor: "var(--qgi-surface)",
              }}
            >
              {/* Stage marker */}
              <div className="flex items-baseline gap-3 mb-3">
                <span
                  className="font-data text-xs tracking-widest uppercase"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  Stage {step.n}
                </span>
                <span className="text-lg font-light" style={{ color: "var(--qgi-text)" }}>
                  {step.title}
                </span>
              </div>

              <div
                className="text-[12px] mb-3 leading-snug"
                style={{ color: "var(--qgi-text)" }}
              >
                {step.summary}
              </div>
              <div
                className="text-[11px] mb-4 leading-relaxed"
                style={{ color: "var(--qgi-text-muted)" }}
              >
                {step.detail}
              </div>

              {/* Worked example */}
              <div
                className="rounded p-3 text-[10px] font-data"
                style={{
                  backgroundColor: "var(--qgi-bg)",
                  border: "1px solid var(--qgi-border)",
                }}
              >
                <div
                  className="text-[9px] tracking-widest uppercase mb-2"
                  style={{ color: "var(--qgi-text-muted)" }}
                >
                  {step.example.stage}
                </div>
                {step.example.lines.map((line, j) => (
                  <div
                    key={j}
                    className="leading-relaxed"
                    style={{ color: "var(--qgi-text)" }}
                  >
                    {line}
                  </div>
                ))}
              </div>
            </div>

            {/* Arrow between cards (hidden on mobile) */}
            {i < STEPS.length - 1 && (
              <div
                className="hidden md:flex absolute top-1/2 -right-3 -translate-y-1/2 items-center justify-center w-6 h-6 rounded-full pointer-events-none z-10"
                style={{
                  backgroundColor: "var(--qgi-bg)",
                  color: "var(--qgi-text-muted)",
                  border: "1px solid var(--qgi-border)",
                }}
                aria-hidden
              >
                →
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Stats — metric-card theme */}
      <div className="mt-8 grid grid-cols-2 lg:grid-cols-4 gap-3">
        {FLOW_CARDS.map((c, i) => (
          <div
            key={i}
            className="rounded-lg border p-4"
            style={{
              borderColor: "var(--qgi-border)",
              backgroundColor: "var(--qgi-surface)",
            }}
          >
            <div
              className="font-data text-2xl tabular-nums tracking-tight"
              style={{ color: "var(--qgi-accent)" }}
            >
              {c.value}
            </div>
            <div
              className="text-[10px] tracking-widest uppercase mt-1"
              style={{ color: "var(--qgi-text-muted)" }}
            >
              {c.label}
            </div>
            <div className="text-[10px] mt-1" style={{ color: "var(--qgi-text-muted)" }}>
              {c.sublabel}
            </div>
          </div>
        ))}
      </div>

      <p
        className="mt-5 text-[11px] leading-relaxed max-w-3xl"
        style={{ color: "var(--qgi-text-muted)" }}
      >
        An event is only kept once it has passed verification with a true verdict and a
        cited public source. Events that fail, or that no source can confirm, are dropped.
      </p>
    </div>
  );
}
