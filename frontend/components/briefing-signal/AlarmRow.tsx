/**
 * AlarmRow — single alarm row: flag + country + topic + struct + pulse + gap badge.
 * Server component.
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import type { SilentAlarm } from "@/lib/dashboard/briefing-insights";

export function AlarmRow({ alarm }: { alarm: SilentAlarm }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "8px 10px",
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderLeft: "3px solid #5B7E99",
        borderRadius: "5px",
        minWidth: 0,
      }}
    >
      {/* Flag */}
      <FlagImg
        emoji={flagFor(alarm.countryName)}
        name={alarm.countryName}
        width={16}
        radius={2}
      />

      {/* Country + Topic */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "12px",
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

      {/* Struct score (big, amber) */}
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "18px",
            fontWeight: 700,
            color: "#f59e0b",
            lineHeight: 1,
          }}
        >
          {Math.round(alarm.struct)}
        </div>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            letterSpacing: "0.5px",
          }}
        >
          struct
        </div>
      </div>

      {/* Pulse score (smaller, dim) */}
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--qgi-text-muted)",
            lineHeight: 1,
          }}
        >
          {Math.round(alarm.pulse)}
        </div>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            letterSpacing: "0.5px",
          }}
        >
          pulse
        </div>
      </div>

      {/* Gap badge */}
      <span
        style={{
          fontSize: "9px",
          fontWeight: 700,
          fontFamily: "ui-monospace, monospace",
          letterSpacing: "0.5px",
          padding: "3px 7px",
          borderRadius: "3px",
          background: "rgba(245,158,11,0.12)",
          color: "#f59e0b",
          border: "1px solid rgba(245,158,11,0.30)",
          whiteSpace: "nowrap",
          flexShrink: 0,
        }}
      >
        +{Math.round(alarm.gap)} pts
      </span>
    </div>
  );
}
