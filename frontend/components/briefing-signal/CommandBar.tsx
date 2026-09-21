/**
 * CommandBar — sticky 44px top strip for the Signal Board.
 *
 * Contents: wordmark · vintage chip · in-play count · spacer · live status dot.
 * Server component — no "use client".
 */
import type { LiveStatus } from "@/lib/hf/live-pulse-core";

interface Props {
  vintage: string;
  inPlayCount: number;
  liveStatus: LiveStatus;
}

export function CommandBar({ vintage, inPlayCount, liveStatus }: Props) {
  const isLive = liveStatus !== "absent" && liveStatus !== "paused";
  return (
    <div
      style={{
        height: "44px",
        display: "flex",
        alignItems: "center",
        gap: "12px",
        padding: "0 20px",
        background: "var(--qgi-surface)",
        borderBottom: "1px solid var(--qgi-border)",
      }}
    >
      {/* Bar label */}
      <span
        style={{
          fontFamily:
            "'Century Gothic', 'CenturyGothic', 'URW Gothic', 'AppleGothic', 'ITC Avant Garde Gothic', var(--font-qg-brand), sans-serif",
          fontSize: "11px",
          fontWeight: 700,
          letterSpacing: "4px",
          textTransform: "uppercase",
          color: "var(--qgi-accent)",
          whiteSpace: "nowrap",
        }}
      >
        The Signal Board
      </span>

      {/* Vintage chip — date-only (first 10 chars of ISO stamp) */}
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          padding: "2px 7px",
          borderRadius: "3px",
          background: "rgba(91,126,153,0.12)",
          border: "1px solid rgba(91,126,153,0.25)",
          whiteSpace: "nowrap",
        }}
      >
        v{vintage.slice(0, 10)}
      </span>

      {/* In-play count pill */}
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          fontWeight: 700,
          color: "#f59e0b",
          padding: "2px 8px",
          borderRadius: "3px",
          background: "rgba(245,158,11,0.10)",
          border: "1px solid rgba(245,158,11,0.25)",
          whiteSpace: "nowrap",
        }}
      >
        {inPlayCount} trends in play
      </span>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Live status */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            color: isLive ? "var(--qgi-success)" : "var(--qgi-text-dim)",
            lineHeight: 1,
          }}
        >
          {isLive ? "●" : "○"}
        </span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            letterSpacing: "1.5px",
            textTransform: "uppercase",
            color: isLive ? "var(--qgi-success)" : "var(--qgi-text-dim)",
          }}
        >
          LIVE
        </span>
      </div>
    </div>
  );
}
