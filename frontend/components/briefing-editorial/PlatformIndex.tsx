/**
 * PlatformIndex — editorial "contents page" navigation.
 *
 * Every platform surface as a horizontal row list (not card grid).
 * Rows are separated by hairlines. Each row links to the surface.
 *
 * recipesTotal is now a prop (from getAllRecipes length) so the Trends
 * description reflects the current data bake — nothing hardcoded.
 *
 * Server component — no "use client".
 */
import Link from "next/link";
import type { Route } from "next";
import type { ReactNode } from "react";
import { PanelBase } from "@/components/dashboard-v4-1/PanelBase";

interface IndexEntry {
  label: string;
  href: string;
  description: string;
  iconPath: string;
  comingSoon?: boolean;
  isLive?: boolean;
}

function buildCorners(recipesTotal: number, liveTerminalIso: string): IndexEntry[] {
  return [
    {
      label: "Risk Board",
      href: "/risk-board",
      description: "Structural grid vs. live news topics across every country",
      iconPath: "M3 3v18h18M7 16l4-4 4 4 4-4",
    },
    {
      label: "Trends",
      href: "/trends",
      description: `${recipesTotal} event shapes scored across 160+ countries this release`,
      iconPath: "M3 3v18h18M7 16l4-4 4 4 4-4",
    },
    {
      label: "Countries",
      href: "/countries",
      description: "Country profiles, scores, and closest historical analogues",
      iconPath:
        "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z",
    },
    {
      label: "Analogues",
      href: "/analogues",
      description: "Historical precedents ranked by structural similarity",
      iconPath: "M21 21l-6-6m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0z",
    },
    {
      label: "Live Terminal",
      href: `/countries/${liveTerminalIso}`,
      description: "Per-country intraday news pulse and live charts",
      iconPath:
        "M8.288 15.038a5.25 5.25 0 0 1 7.424 0M5.106 11.856c3.807-3.808 9.98-3.808 13.788 0M1.924 8.674c5.565-5.565 14.587-5.565 20.152 0M12.53 18.22l-.53.53-.53-.53a.75.75 0 0 1 1.06 0z",
      isLive: true,
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
  ];
}

function NavIconInline({ d }: { d: string }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="var(--qgi-accent)"
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
          fontSize: "10px",
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
          fontSize: "10px",
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

interface PlatformIndexProps {
  vintageChip: ReactNode;
  liveTerminalIso: string;
  /** Number of active trend recipes — drives Trends row description. */
  recipesTotal: number;
}

export function PlatformIndex({
  vintageChip,
  liveTerminalIso,
  recipesTotal,
}: PlatformIndexProps) {
  const corners = buildCorners(recipesTotal, liveTerminalIso);

  return (
    <PanelBase title="Platform Index" accent="#5B7E99" rightSlot={vintageChip}>
      <style>{`
        .qgi-pi-row {
          transition: background 120ms ease;
        }
        .qgi-pi-row:hover {
          background: rgba(91,126,153,0.06);
        }
        .qgi-pi-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0;
        }
        @media (max-width: 767px) {
          .qgi-pi-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>

      <div className="qgi-pi-grid">
        {corners.map((corner, i) => (
          <Link
            key={corner.href}
            href={corner.href as Route}
            className="qgi-pi-row"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "12px 6px",
              borderTop: i >= 2 ? "1px solid var(--qgi-border)" : undefined,
              borderBottom: "1px solid var(--qgi-border)",
              textDecoration: "none",
              color: "inherit",
              opacity: corner.comingSoon ? 0.6 : 1,
              borderRadius: "2px",
            }}
          >
            {/* Icon */}
            <div
              style={{
                width: "28px",
                height: "28px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "var(--qgi-surface)",
                borderRadius: "5px",
                flexShrink: 0,
              }}
            >
              <NavIconInline d={corner.iconPath} />
            </div>

            {/* Label + chip */}
            <div
              style={{ display: "flex", alignItems: "center", gap: "6px", flexShrink: 0 }}
            >
              <span
                style={{
                  fontSize: "13px",
                  fontWeight: 600,
                  color: "var(--qgi-text)",
                }}
              >
                {corner.label}
              </span>
              <StatusChip comingSoon={corner.comingSoon} isLive={corner.isLive} />
            </div>

            {/* Description */}
            <span
              style={{
                fontSize: "11px",
                color: "var(--qgi-text-dim)",
                flex: 1,
                minWidth: 0,
              }}
            >
              {corner.description}
            </span>

            {/* Arrow */}
            <span
              style={{
                color: "var(--qgi-text-dim)",
                fontSize: "13px",
                flexShrink: 0,
              }}
            >
              →
            </span>
          </Link>
        ))}
      </div>
    </PanelBase>
  );
}
