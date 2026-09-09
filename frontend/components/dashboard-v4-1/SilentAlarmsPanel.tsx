/**
 * SilentAlarmsPanel — structural pressure without news coverage.
 *
 * Shows LATENT cells ranked by struct score. The gap between structure and
 * pulse is the QGI differentiator: we see it structurally before the news
 * notices. V4.1 framing: structural signal, not imminent crisis.
 *
 * Server component. No "use client".
 */
import Link from "next/link";
import type { Route } from "next";
import { PanelBase } from "./PanelBase";
import type { SilentAlarm } from "@/lib/dashboard/briefing-insights";

interface Props {
  alarms: SilentAlarm[];
}

export function SilentAlarmsPanel({ alarms }: Props) {
  if (alarms.length === 0) return null;

  const rightSlot = (
    <Link
      href={"/risk-board" as Route}
      style={{
        fontSize: "11px",
        color: "var(--qgi-accent)",
        textDecoration: "none",
        fontFamily: "ui-monospace, monospace",
        letterSpacing: "0.3px",
        whiteSpace: "nowrap",
      }}
    >
      Full board →
    </Link>
  );

  return (
    <PanelBase
      title="Structural pressure without news coverage"
      caption="High resemblance score, low news pulse — the gap is where QGI leads. LATENT verdict means structure is present; news has not yet caught up."
      accent="#5B7E99"
      rightSlot={rightSlot}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
          gap: "10px",
        }}
      >
        {alarms.map((alarm) => (
          <AlarmCard key={alarm.key} alarm={alarm} />
        ))}
      </div>
    </PanelBase>
  );
}

function AlarmCard({ alarm }: { alarm: SilentAlarm }) {
  // Bar widths: struct and pulse expressed as % of 100
  const structPct = Math.min(100, Math.round(alarm.struct));
  const pulsePct = Math.min(100, Math.round(alarm.pulse));

  return (
    <div
      style={{
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderLeft: "3px solid #5B7E99",
        borderRadius: "5px",
        padding: "10px 12px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
      }}
    >
      {/* Header: country + topic + LATENT badge */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "6px",
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontSize: "12.5px",
              fontWeight: 600,
              color: "var(--qgi-text)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {alarm.countryName}
          </div>
          <div
            style={{
              fontSize: "10.5px",
              color: "var(--qgi-text-muted)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {alarm.topicLabel}
          </div>
        </div>
        <span
          style={{
            fontSize: "8.5px",
            padding: "2px 6px",
            borderRadius: "3px",
            background: "rgba(91,126,153,0.15)",
            border: "1px solid rgba(91,126,153,0.4)",
            color: "#5B7E99",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.5px",
            flexShrink: 0,
          }}
        >
          LATENT
        </span>
      </div>

      {/* Dual progress bars */}
      <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
        {/* Struct bar */}
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: "2px",
            }}
          >
            <span
              style={{
                fontSize: "9.5px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
                letterSpacing: "0.3px",
              }}
            >
              struct
            </span>
            <span
              style={{
                fontSize: "9.5px",
                fontWeight: 700,
                color: "#5B7E99",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {structPct}
            </span>
          </div>
          <div
            style={{
              height: "5px",
              background: "rgba(91,126,153,0.15)",
              borderRadius: "3px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${structPct}%`,
                background: "#5B7E99",
                borderRadius: "3px",
              }}
            />
          </div>
        </div>

        {/* Pulse bar */}
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: "2px",
            }}
          >
            <span
              style={{
                fontSize: "9.5px",
                color: "var(--qgi-text-dim)",
                fontFamily: "ui-monospace, monospace",
                letterSpacing: "0.3px",
              }}
            >
              pulse
            </span>
            <span
              style={{
                fontSize: "9.5px",
                fontWeight: 700,
                color: "var(--qgi-text-muted)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {pulsePct}
            </span>
          </div>
          <div
            style={{
              height: "5px",
              background: "rgba(91,126,153,0.10)",
              borderRadius: "3px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${pulsePct}%`,
                background: "rgba(91,126,153,0.45)",
                borderRadius: "3px",
              }}
            />
          </div>
        </div>
      </div>

      {/* Gap callout */}
      <div
        style={{
          fontSize: "10px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.2px",
        }}
      >
        gap:{" "}
        <span style={{ color: "#5B7E99", fontWeight: 700 }}>{Math.round(alarm.gap)}</span>{" "}
        pts
      </div>
    </div>
  );
}
