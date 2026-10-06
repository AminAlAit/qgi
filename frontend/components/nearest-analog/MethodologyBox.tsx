/**
 * MethodologyBox — side panel explaining shape-matching in plain terms.
 * Calm slate-blue "How to read this" panel (V4.1). No internal acronyms
 * (LOCO, M8-R5) in rendered copy. Four numbered statements covering what
 * match scores mean, what analog outcomes represent, and what the indicators
 * are.
 *
 * V4.1 §2: vintage stamp removed from this panel — one stamp lives in the
 * global header. The "Data vintage" row now reads as a static statement.
 *
 * Server component.
 */
import { Telescope, Compass, History as HistoryIcon } from "lucide-react";

/** Accent hue for the panel: calm slate-blue. */
const PANEL_COLOR = "#5B7E99";

export function MethodologyBox() {
  return (
    <aside
      data-tour="analog-methodology-box"
      style={{
        background: "rgba(91,126,153,0.06)",
        border: `1px solid ${PANEL_COLOR}`,
        borderRadius: "8px",
        borderLeft: `3px solid ${PANEL_COLOR}`,
        padding: "18px",
        display: "flex",
        flexDirection: "column",
        gap: "14px",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          paddingBottom: "10px",
          borderBottom: `1px solid rgba(91,126,153,0.25)`,
        }}
      >
        <Telescope size={18} strokeWidth={1.6} color={PANEL_COLOR} />
        <div>
          <div
            style={{
              fontSize: "9px",
              letterSpacing: "1.5px",
              color: PANEL_COLOR,
              fontFamily: "ui-monospace, monospace",
              marginBottom: "1px",
              fontWeight: 600,
            }}
          >
            HOW TO READ THIS
          </div>
          <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--qgi-text)" }}>
            What these matches mean
          </div>
        </div>
      </header>

      <ol
        style={{
          margin: 0,
          padding: "0 0 0 18px",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}
      >
        <li style={{ fontSize: "12px", color: "var(--qgi-text-muted)", lineHeight: 1.6 }}>
          <strong style={{ color: "var(--qgi-text)" }}>
            Match scores are similarity ranks, not probabilities.
          </strong>{" "}
          A score of 87 means the indicator trajectories are highly similar to a
          historical case; it says nothing about the chance of any event occurring.
        </li>
        <li style={{ fontSize: "12px", color: "var(--qgi-text-muted)", lineHeight: 1.6 }}>
          <strong style={{ color: "var(--qgi-text)" }}>
            Analogue outcomes are completed history about the analogue country.
          </strong>{" "}
          &ldquo;In Tunisia, 2008, …&rdquo; describes what happened there. It is never
          joined to the current country by a predictive verb and does not imply the
          current country will follow the same path.
        </li>
        <li style={{ fontSize: "12px", color: "var(--qgi-text-muted)", lineHeight: 1.6 }}>
          <strong style={{ color: "var(--qgi-text)" }}>
            Indicators are statistical associations, not causes.
          </strong>{" "}
          The four composite indicators driving the match score co-varied with the labeled
          event in historical data. Co-variation is not causation; other factors may
          dominate in any specific case.
        </li>
        <li style={{ fontSize: "12px", color: "var(--qgi-text-muted)", lineHeight: 1.6 }}>
          <strong style={{ color: "var(--qgi-text)" }}>
            Cross-region matches carry additional uncertainty.
          </strong>{" "}
          The discrimination score was validated within each region. Matches across
          regions (for example, Lebanon compared with Argentina) inherit higher structural
          uncertainty and should be read with extra caution.
        </li>
      </ol>

      {/* Mechanic row */}
      <Row icon={Compass} title="How the match is computed">
        For each trajectory shape in the library, the engine computes a weighted cosine
        similarity between the current country&apos;s recent 12-quarter composite series
        and every historical case&apos;s pre-event series. The country is self-excluded.
        The top three cases across all trajectory shapes are surfaced.
      </Row>

      {/* V4.1 §2: vintage stamp removed — the global header carries it. */}
      <Row icon={HistoryIcon} title="Updates">
        The analogue corpus is updated on each data release. Rankings may shift as new
        events are catalogued.
      </Row>
    </aside>
  );
}

function Row({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof Telescope;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: "10px",
        borderTop: "1px solid rgba(91,126,153,0.15)",
        paddingTop: "10px",
      }}
    >
      <div style={{ flexShrink: 0, marginTop: "2px", color: "var(--qgi-text-muted)" }}>
        <Icon size={14} strokeWidth={1.6} />
      </div>
      <div>
        <div
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: "var(--qgi-text)",
            marginBottom: "3px",
            letterSpacing: "0.2px",
          }}
        >
          {title}
        </div>
        <p
          style={{
            fontSize: "12px",
            color: "var(--qgi-text-muted)",
            lineHeight: 1.55,
            margin: 0,
          }}
        >
          {children}
        </p>
      </div>
    </div>
  );
}
