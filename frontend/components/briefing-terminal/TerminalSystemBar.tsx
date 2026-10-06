/**
 * TerminalSystemBar — sticky 32px system header bar.
 *
 * Left: QGI·INTELLIGENCE wordmark + TERMINAL v{vintage}.
 * Center: live scrolling ticker (TerminalTicker client component).
 * Right: vintageQuarter · live status dot · LIVE/OFFLINE chip.
 *
 * Server component. TerminalTicker is the client leaf.
 */
import type { TickerPill } from "./TerminalTicker";
import { TerminalTicker } from "./TerminalTicker";

export interface TerminalSystemBarProps {
  vintage: string;
  vintageQuarter: string;
  tickerPills: TickerPill[];
  isLive: boolean;
}

export function TerminalSystemBar({
  vintage,
  vintageQuarter,
  tickerPills,
  isLive,
}: TerminalSystemBarProps) {
  return (
    <div
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        height: "32px",
        background: "var(--qgi-surface)",
        borderBottom: "1px solid var(--qgi-border)",
        display: "flex",
        alignItems: "center",
        padding: "0 14px",
        gap: "10px",
      }}
    >
      {/* Left rail */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          flexShrink: 0,
          whiteSpace: "nowrap",
        }}
      >
        <span
          style={{
            fontFamily:
              "'Century Gothic', 'CenturyGothic', 'URW Gothic', 'AppleGothic', 'ITC Avant Garde Gothic', var(--font-qg-brand), sans-serif",
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "1px",
            textTransform: "uppercase",
            display: "inline-flex",
            alignItems: "baseline",
            gap: "0",
          }}
        >
          <span style={{ color: "var(--qgi-accent)" }}>QG</span>
          <span style={{ color: "var(--qgi-text-muted)" }}>·INTELLIGENCE</span>
        </span>
        <span style={{ color: "var(--qgi-border)", fontSize: "9px" }}>·</span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            letterSpacing: "0.4px",
            color: "var(--qgi-text-dim)",
          }}
          title={`TERMINAL v${vintage}`}
        >
          TERMINAL v{vintage.slice(0, 10)}
        </span>
      </div>

      {/* Center: scrolling ticker — expands to fill remaining space. Hidden on mobile via .qgi-sys-ticker CSS. */}
      <div
        className="qgi-sys-ticker"
        style={{
          flex: 1,
          overflow: "hidden",
          height: "100%",
          display: "flex",
          alignItems: "center",
        }}
      >
        <TerminalTicker pills={tickerPills} />
      </div>

      {/* Right rail */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          flexShrink: 0,
          whiteSpace: "nowrap",
          fontFamily: "ui-monospace, monospace",
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
        }}
      >
        <span>{vintageQuarter}</span>
        <span style={{ color: "var(--qgi-border)" }}>·</span>
        {/* Pulsing dot */}
        {isLive ? (
          <>
            <style>{`
              @keyframes qgi-pulse-dot {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.3; }
              }
              .qgi-live-dot {
                animation: qgi-pulse-dot 1.6s ease-in-out infinite;
              }
            `}</style>
            <span
              className="qgi-live-dot"
              style={{
                display: "inline-block",
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: "#3FBF8F",
                flexShrink: 0,
              }}
            />
            <span style={{ color: "#3FBF8F", fontWeight: 700 }}>LIVE</span>
          </>
        ) : (
          <>
            <span
              style={{
                display: "inline-block",
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                background: "var(--qgi-text-dim)",
                flexShrink: 0,
              }}
            />
            <span style={{ color: "var(--qgi-text-dim)" }}>OFFLINE</span>
          </>
        )}
      </div>
    </div>
  );
}
