/**
 * AlarmsColumn — silent alarms list for the intel rail right column.
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import type { SilentAlarm } from "@/lib/dashboard/briefing-insights";
import { AlarmRow } from "./AlarmRow";

interface Props {
  alarms: SilentAlarm[];
}

export function AlarmsColumn({ alarms }: Props) {
  if (alarms.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        padding: "16px",
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        height: "100%",
        boxSizing: "border-box",
      }}
    >
      {/* Panel header */}
      <div>
        <div
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "#5B7E99",
            marginBottom: "2px",
          }}
        >
          Structural pressure, no headlines
        </div>
        <div
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          LATENT cells ranked by structure score
        </div>
      </div>

      {/* Alarm rows */}
      <div style={{ display: "flex", flexDirection: "column", gap: "6px", flex: 1 }}>
        {alarms.slice(0, 6).map((alarm) => (
          <AlarmRow key={alarm.key} alarm={alarm} />
        ))}
      </div>

      {/* Footer link */}
      <Link
        href={"/risk-board" as Route}
        style={{
          fontSize: "11px",
          color: "var(--qgi-accent)",
          textDecoration: "none",
          fontFamily: "ui-monospace, monospace",
          marginTop: "auto",
        }}
      >
        Full board →
      </Link>
    </div>
  );
}
