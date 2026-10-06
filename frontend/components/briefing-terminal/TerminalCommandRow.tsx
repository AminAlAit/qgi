/**
 * TerminalCommandRow — compact pill-link nav row (§1).
 *
 * Six destinations in one flex row. COMPARE + SANCTIONS SIM are coming-soon
 * (dashed border, 50% opacity). LIVE TERMINAL has a pulsing green dot.
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";

export interface TerminalCommandRowProps {
  liveTerminalIso: string;
  inPlayCount: number;
}

const PILL_BASE: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "5px",
  fontFamily: "ui-monospace, monospace",
  fontSize: "11px",
  letterSpacing: "1.8px",
  textTransform: "uppercase",
  padding: "6px 12px",
  borderRadius: "4px",
  textDecoration: "none",
  whiteSpace: "nowrap",
  transition: "border-color 120ms ease, background 120ms ease",
};

export function TerminalCommandRow({
  liveTerminalIso,
  inPlayCount,
}: TerminalCommandRowProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        flexWrap: "wrap",
        padding: "8px 0",
        borderBottom: "1px solid var(--qgi-border)",
        marginBottom: "8px",
      }}
    >
      <style>{`
        .qgi-cmd-pill {
          background: var(--qgi-surface);
          border: 1px solid var(--qgi-border);
          color: var(--qgi-text-muted);
        }
        .qgi-cmd-pill:hover {
          border-color: var(--qgi-accent);
          color: var(--qgi-text);
          background: var(--qgi-surface-2, rgba(56,189,248,0.05));
        }
        .qgi-cmd-coming {
          background: transparent;
          border: 1px dashed var(--qgi-border);
          color: var(--qgi-text-dim);
          opacity: 0.55;
          cursor: not-allowed;
        }
        .qgi-cmd-live {
          background: rgba(63,191,143,0.08);
          border: 1px solid rgba(63,191,143,0.35);
          color: #3FBF8F;
          font-weight: 700;
        }
        .qgi-cmd-live:hover {
          background: rgba(63,191,143,0.14);
          border-color: #3FBF8F;
        }
        @keyframes qgi-cmd-dot {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.2; }
        }
        .qgi-live-pill-dot {
          animation: qgi-cmd-dot 1.6s ease-in-out infinite;
        }
      `}</style>

      {/* Left cluster */}
      <Link href={"/risk-board" as Route} className="qgi-cmd-pill" style={PILL_BASE}>
        Risk Board
      </Link>
      <Link href={"/trends" as Route} className="qgi-cmd-pill" style={PILL_BASE}>
        Trends · {inPlayCount} in play
      </Link>
      <Link href={"/countries" as Route} className="qgi-cmd-pill" style={PILL_BASE}>
        Countries
      </Link>
      <Link href={"/analogues" as Route} className="qgi-cmd-pill" style={PILL_BASE}>
        Analogues
      </Link>

      {/* Coming-soon cluster */}
      <span className="qgi-cmd-coming" style={PILL_BASE}>
        Compare
      </span>
      <span className="qgi-cmd-coming" style={PILL_BASE}>
        Sanctions Sim
      </span>

      {/* Live Terminal */}
      <Link
        href={`/countries/${liveTerminalIso}` as Route}
        className="qgi-cmd-live"
        style={PILL_BASE}
      >
        <span
          className="qgi-live-pill-dot"
          style={{
            display: "inline-block",
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: "#3FBF8F",
            flexShrink: 0,
          }}
        />
        Live Terminal →
      </Link>
    </div>
  );
}
