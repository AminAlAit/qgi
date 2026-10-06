/**
 * CornerNavGrid — the hub's central utility panel.
 *
 * "Jump to any corner." One card per named destination, every route in the
 * platform in a single responsive grid. Server component — no client state.
 * Inline styles + var(--qgi-*) only (no Tailwind config changes).
 *
 * Routes with `comingSoon` render a muted chip. Routes with `isLive` render
 * a pulse-green "Live" chip. The grid adapts from 2 cols (mobile) to 5 cols
 * (desktop) via CSS auto-fill.
 */
import Link from "next/link";
import type { Route } from "next";
import type { ReactNode } from "react";
import { PanelBase } from "./PanelBase";

interface NavCorner {
  label: string;
  href: string;
  description: string;
  /** Lucide SVG path data (24-viewBox, stroke) rendered inline — avoids
   *  importing all of lucide-react into the server component. */
  iconPath: string;
  comingSoon?: boolean;
  isLive?: boolean;
}

const CORNERS: NavCorner[] = [
  {
    label: "Risk Board",
    href: "/risk-board",
    description: "Structural grid vs. news topics side by side",
    iconPath:
      "M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 4a1 1 0 1 1-1 1 1 1 0 0 1 1-1zm-4.24 11.07A7 7 0 0 1 5 12a7 7 0 0 1 7-7 7 7 0 0 1 7 7 7 7 0 0 1-2.76 5.57L15 16H9zM12 9a3 3 0 1 0 3 3 3 3 0 0 0-3-3z",
  },
  {
    label: "Trends",
    href: "/trends",
    description: "44 event shapes scored across 160+ countries",
    iconPath: "M3 3v18h18M7 16l4-4 4 4 4-4",
  },
  {
    label: "Countries",
    href: "/countries",
    description: "Country profiles, scores, and closest analogues",
    iconPath:
      "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z",
  },
  {
    label: "Analogues",
    href: "/analogues",
    description: "Historical precedents ranked by structural similarity",
    iconPath: "M21 21l-6-6m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0zM10 7v3m0 0v3m0-3h3m-3 0H7",
  },
  {
    label: "Compare",
    href: "/compare",
    description: "Side-by-side country comparison across the catalog",
    iconPath:
      "M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18",
    comingSoon: true,
  },
  {
    label: "Sanctions Simulator",
    href: "/sanctions-simulator",
    description: "Counterfactual impact model for sanctions analysis",
    iconPath:
      "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0 1 12 2.944a11.955 11.955 0 0 1-8.618 3.04A12.02 12.02 0 0 0 3 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
    comingSoon: true,
  },
  {
    label: "Live Terminal",
    href: "/countries/gbr",
    description: "Per-country intraday news pulse and live charts",
    iconPath:
      "M8.288 15.038a5.25 5.25 0 0 1 7.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12.53 18.22l-.53.53-.53-.53a.75.75 0 0 1 1.06 0z",
    isLive: true,
  },
];

/** SVG icon rendered from raw path data — keeps this component free of
 *  the lucide-react bundle. All icons use 24×24 viewBox, stroke style. */
function NavIcon({ d, color }: { d: string; color: string }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

function StatusChip({ comingSoon, isLive }: { comingSoon?: boolean; isLive?: boolean }) {
  if (isLive) {
    return (
      <span
        style={{
          fontSize: "8.5px",
          padding: "2px 6px",
          borderRadius: "3px",
          background: "rgba(34,197,94,0.12)",
          border: "1px solid rgba(34,197,94,0.45)",
          color: "#22c55e",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.5px",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        Live
      </span>
    );
  }
  if (comingSoon) {
    return (
      <span
        style={{
          fontSize: "8.5px",
          padding: "2px 6px",
          borderRadius: "3px",
          background: "rgba(148,163,184,0.10)",
          border: "1px dashed rgba(148,163,184,0.4)",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.5px",
          textTransform: "uppercase",
          whiteSpace: "nowrap",
        }}
      >
        Soon
      </span>
    );
  }
  return null;
}

export function CornerNavGrid({
  vintageChip,
  liveTerminalIso,
}: {
  vintageChip?: ReactNode;
  /** ISO3 (lowercase) for the Live Terminal card href. Defaults to "gbr". */
  liveTerminalIso?: string;
}) {
  const corners = liveTerminalIso
    ? CORNERS.map((c) =>
        c.label === "Live Terminal" ? { ...c, href: `/countries/${liveTerminalIso}` } : c
      )
    : CORNERS;

  return (
    <PanelBase title="Every surface, one click" accent="#5B7E99" rightSlot={vintageChip}>
      <style>{`
        .qgi-corner-card {
          transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
        }
        .qgi-corner-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 8px 24px rgba(0,0,0,0.32);
          border-color: var(--qgi-accent);
        }
      `}</style>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
          gap: "10px",
        }}
      >
        {corners.map((c) => (
          <CornerCard key={c.href} corner={c} />
        ))}
      </div>
    </PanelBase>
  );
}

function CornerCard({ corner }: { corner: NavCorner }) {
  const isMuted = corner.comingSoon;
  const iconColor = isMuted ? "var(--qgi-text-dim)" : "var(--qgi-accent)";

  return (
    <Link
      href={corner.href as Route}
      className="qgi-corner-card"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        textDecoration: "none",
        color: "inherit",
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "8px",
        padding: "14px 14px 12px",
        minHeight: "100px",
        opacity: isMuted ? 0.65 : 1,
      }}
    >
      {/* Icon box */}
      <div
        style={{
          width: "36px",
          height: "36px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${isMuted ? "rgba(148,163,184,0.08)" : "rgba(91,126,153,0.12)"}`,
          borderRadius: "6px",
          flexShrink: 0,
        }}
      >
        <NavIcon d={corner.iconPath} color={iconColor} />
      </div>

      {/* Label + chip */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--qgi-text)",
            lineHeight: 1.2,
          }}
        >
          {corner.label}
        </span>
        <StatusChip comingSoon={corner.comingSoon} isLive={corner.isLive} />
      </div>

      {/* Description */}
      <p
        style={{
          fontSize: "11px",
          color: "var(--qgi-text-muted)",
          lineHeight: 1.4,
          margin: 0,
        }}
      >
        {corner.description}
      </p>
    </Link>
  );
}
