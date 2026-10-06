/**
 * LivePulseGlance — a slim strip of live news signals for the Briefing hub.
 *
 * Shows the top-N loudest country×topic cells by live pulse score, as compact
 * pills. Renders nothing (null) when the pulse is absent or no ACTIVE/SIGNAL
 * cells are available, so the Briefing page looks exactly as before until the
 * live poller is deployed.
 *
 * Server component. No "use client". Data is passed from the parent
 * (dashboard/page.tsx) which has already awaited getLivePulse().
 */
import Link from "next/link";
import type { Route } from "next";
import type { HfVerdict } from "@/lib/hf/topics-data";
import { PanelBase } from "./PanelBase";

export interface PulseGlancePill {
  iso3: string;
  countryName: string;
  topicLabel: string;
  pulse: number;
  verdict: HfVerdict;
}

const VERDICT_COLOR: Record<HfVerdict, string> = {
  ACTIVE: "#E05C5C",
  SIGNAL: "#f59e0b",
  LATENT: "#5B7E99",
  QUIET: "var(--qgi-text-dim)",
};

export function LivePulseGlance({ pills }: { pills: PulseGlancePill[] }) {
  if (pills.length === 0) return null;

  const rightSlot = (
    <Link
      href={"/risk-board" as Route}
      style={{
        fontSize: "11px",
        color: "var(--qgi-accent)",
        textDecoration: "none",
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.3px",
      }}
    >
      Full board →
    </Link>
  );

  return (
    <PanelBase title="Live news pulse" accent="#E05C5C" rightSlot={rightSlot}>
      <div
        style={{
          display: "flex",
          gap: "10px",
          overflowX: "auto",
          paddingBottom: "4px",
          // Hide scrollbar in most browsers; keep it accessible
          scrollbarWidth: "thin",
        }}
      >
        {pills.map((pill) => (
          <PulsePill key={`${pill.iso3}-${pill.topicLabel}`} pill={pill} />
        ))}
      </div>
    </PanelBase>
  );
}

function PulsePill({ pill }: { pill: PulseGlancePill }) {
  const color = VERDICT_COLOR[pill.verdict];
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        padding: "8px 12px",
        background: "var(--qgi-bg)",
        border: `1px solid ${color}55`,
        borderLeft: `3px solid ${color}`,
        borderRadius: "6px",
        minWidth: "120px",
        flexShrink: 0,
      }}
    >
      {/* Country · Topic */}
      <div
        style={{
          fontSize: "11px",
          fontWeight: 600,
          color: "var(--qgi-text)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {pill.countryName}
      </div>
      <div
        style={{
          fontSize: "10px",
          color: "var(--qgi-text-muted)",
          whiteSpace: "nowrap",
        }}
      >
        {pill.topicLabel}
      </div>
      {/* Pulse score */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "4px",
          marginTop: "2px",
        }}
      >
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "16px",
            fontWeight: 700,
            color,
            letterSpacing: "-0.5px",
            lineHeight: 1,
          }}
        >
          {Math.round(pill.pulse)}
        </span>
        <span
          style={{
            fontSize: "9px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
            textTransform: "uppercase",
            letterSpacing: "0.4px",
          }}
        >
          pulse
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: "8.5px",
            padding: "1px 5px",
            borderRadius: "3px",
            background: `${color}18`,
            border: `1px solid ${color}55`,
            color,
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.3px",
            whiteSpace: "nowrap",
          }}
        >
          {pill.verdict}
        </span>
      </div>
    </div>
  );
}
