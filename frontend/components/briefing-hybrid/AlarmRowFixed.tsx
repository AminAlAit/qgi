/**
 * AlarmRowFixed — hybrid-namespace copy of briefing-signal/AlarmRow.
 *
 * Two-line layout so the country·topic and the "+N pts" gap badge always sit
 * INSIDE the narrow right-rail card. The original single-line row crowded five
 * elements into a 230px rail, squeezing the country name to nothing and pushing
 * the gap badge past the card's right edge.
 *
 * The briefing-signal/AlarmRow is left 100% untouched per the candidate-pages
 * freeze rule. This copy lives in briefing-hybrid/ and is used only by
 * AlarmsColumnFixed (also in briefing-hybrid/).
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import type { SilentAlarm } from "@/lib/dashboard/briefing-insights";

export function AlarmRowFixed({ alarm }: { alarm: SilentAlarm }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "6px",
        padding: "8px 10px",
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderLeft: "3px solid #5B7E99",
        borderRadius: "5px",
        minWidth: 0,
      }}
    >
      {/* Row 1: flag + country · topic (full width, ellipsis safety) */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "7px",
          minWidth: 0,
        }}
      >
        <FlagImg
          emoji={flagFor(alarm.countryName)}
          name={alarm.countryName}
          width={16}
          radius={2}
        />
        <div
          style={{
            minWidth: 0,
            flex: 1,
            overflow: "hidden",
            whiteSpace: "nowrap",
            textOverflow: "ellipsis",
          }}
        >
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "var(--qgi-text)",
            }}
          >
            {alarm.countryName}
          </span>
          <span style={{ color: "var(--qgi-border)", padding: "0 4px" }}>·</span>
          <span style={{ fontSize: "11px", color: "var(--qgi-text-muted)" }}>
            {alarm.topicLabel}
          </span>
        </div>
      </div>

      {/* Row 2: struct · pulse · gap badge (badge has its own room here) */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <span style={{ fontFamily: "ui-monospace, monospace", fontSize: "12px" }}>
          <span style={{ color: "#f59e0b", fontWeight: 700 }}>
            {Math.round(alarm.struct)}
          </span>
          <span style={{ color: "var(--qgi-text-dim)", fontSize: "10px" }}> struct</span>
        </span>
        <span style={{ fontFamily: "ui-monospace, monospace", fontSize: "12px" }}>
          <span style={{ color: "var(--qgi-text-muted)", fontWeight: 600 }}>
            {Math.round(alarm.pulse)}
          </span>
          <span style={{ color: "var(--qgi-text-dim)", fontSize: "10px" }}> pulse</span>
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: "11px",
            fontWeight: 700,
            fontFamily: "ui-monospace, monospace",
            letterSpacing: "0.5px",
            padding: "2px 7px",
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
    </div>
  );
}
