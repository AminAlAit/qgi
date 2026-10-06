/**
 * AlarmsColumnFixed — hybrid-namespace wrapper around AlarmRowFixed.
 *
 * Identical to briefing-signal/AlarmsColumn except it imports AlarmRowFixed
 * (which has the 11px gap-badge) instead of the original 9px AlarmRow.
 * The original briefing-signal/AlarmsColumn is 100% untouched.
 */
import Link from "next/link";
import type { Route } from "next";
import type { SilentAlarm } from "@/lib/dashboard/briefing-insights";
import { AlarmRowFixed } from "./AlarmRowFixed";

interface Props {
  alarms: SilentAlarm[];
}

export function AlarmsColumnFixed({ alarms }: Props) {
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
          Structural Pressure, No Headlines
        </div>
        <div
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          Elevated &amp; quiet cells ranked by structure score
        </div>
      </div>

      {/* Alarm rows — show up to 10 to fill the stretched column height */}
      <div style={{ display: "flex", flexDirection: "column", gap: "6px", flex: 1 }}>
        {alarms.slice(0, 10).map((alarm) => (
          <AlarmRowFixed key={alarm.key} alarm={alarm} />
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
