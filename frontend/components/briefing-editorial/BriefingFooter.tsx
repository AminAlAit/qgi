/**
 * BriefingFooter — dateline scope strip.
 *
 * Simple two-line text footer — no box, no card.
 * Intentionally quiet.
 *
 * Server component — no "use client".
 */

interface BriefingFooterProps {
  recipesTotal: number;
  familyCount: number;
  indicatorsTracked: number;
  vintage: string;
}

export function BriefingFooter({
  recipesTotal,
  familyCount,
  indicatorsTracked,
  vintage,
}: BriefingFooterProps) {
  return (
    <footer
      style={{
        borderTop: "1px solid var(--qgi-border)",
        padding: "20px 0 48px",
      }}
    >
      <p
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "12px",
          color: "var(--qgi-text-dim)",
          margin: "0 0 4px",
          lineHeight: 1.6,
        }}
      >
        180+ countries <span style={{ opacity: 0.4 }}>·</span> {recipesTotal} event trends{" "}
        <span style={{ opacity: 0.4 }}>·</span> {familyCount} risk families{" "}
        <span style={{ opacity: 0.4 }}>·</span> {indicatorsTracked} signals tracked
      </p>
      <p
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          margin: 0,
          opacity: 0.6,
        }}
      >
        Structural analysis refreshed quarterly <span style={{ opacity: 0.4 }}>·</span>{" "}
        Resemblance, not forecast <span style={{ opacity: 0.4 }}>·</span> QGI V4.1{" "}
        <span style={{ opacity: 0.4 }}>·</span> v{vintage}
      </p>
    </footer>
  );
}
