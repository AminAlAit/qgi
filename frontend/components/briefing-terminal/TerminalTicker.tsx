"use client";

/**
 * TerminalTicker — CSS-keyframe scrolling ticker strip.
 *
 * Continuously scrolls left via @keyframes. No JS animation frame.
 * Receives pre-formatted pill strings to avoid React serialization issues
 * with complex objects in client components.
 */

export interface TickerPill {
  text: string;
  verdict: "ACTIVE" | "SIGNAL" | "LATENT" | "QUIET";
}

const VERDICT_COLOR: Record<string, string> = {
  ACTIVE: "#E05C5C",
  SIGNAL: "#F59E0B",
  LATENT: "#5B7E99",
  QUIET: "var(--qgi-text-dim, #6b7280)",
};

export function TerminalTicker({ pills }: { pills: TickerPill[] }) {
  if (pills.length === 0) return null;

  // Duplicate pills so the loop is seamless
  const doubled = [...pills, ...pills];

  return (
    <div
      style={{
        overflow: "hidden",
        flex: 1,
        display: "flex",
        alignItems: "center",
        height: "100%",
        position: "relative",
      }}
    >
      <style>{`
        @keyframes qgi-ticker-scroll {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .qgi-ticker-inner {
          display: flex;
          align-items: center;
          gap: 0;
          white-space: nowrap;
          animation: qgi-ticker-scroll ${Math.max(pills.length * 4, 20)}s linear infinite;
          will-change: transform;
        }
      `}</style>
      <div className="qgi-ticker-inner">
        {doubled.map((pill, i) => (
          <span key={i} style={{ display: "inline-flex", alignItems: "center" }}>
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10px",
                letterSpacing: "0.4px",
                color: VERDICT_COLOR[pill.verdict] ?? "var(--qgi-text-dim)",
                padding: "0 4px",
              }}
            >
              {pill.text}
            </span>
            <span style={{ color: "var(--qgi-border, #2a3a4a)", padding: "0 2px" }}>
              |
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
