/**
 * BriefingCommandBar — Command bar for the hybrid Briefing page.
 *
 * Same visual as briefing-signal/CommandBar but the wordmark reads "BRIEFING"
 * instead of "THE SIGNAL BOARD". Written as a separate component so
 * briefing-signal/CommandBar is not touched and its default label is preserved.
 *
 * Server component — no "use client".
 *
 * 2026-06-20: Stripped to wordmark only — removed vintage chip, trends badge,
 * and LIVE dot per founder revision. Props kept structurally but unused.
 */

// Props retained so the call-site in page.tsx doesn't need a simultaneous edit,
// but they are no longer rendered.
interface Props {
  vintage: string;
  inPlayCount: number;
  liveStatus: string;
}

export function BriefingCommandBar(_props: Props) {
  return (
    <div
      style={{
        height: "44px",
        display: "flex",
        alignItems: "center",
        padding: "0 20px",
        background: "var(--qgi-surface)",
        borderBottom: "1px solid var(--qgi-border)",
      }}
    >
      {/* Bar label — "BRIEFING" */}
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
        Briefing
      </span>
    </div>
  );
}
