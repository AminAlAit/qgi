/**
 * MoverRow — single mover row: flag + country + topic + delta + mini-bar.
 * Server component.
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import type { PulseMover } from "@/lib/dashboard/briefing-insights";
import type { HfVerdict } from "@/lib/hf/topics-data";

const VERDICT_COLOR: Record<HfVerdict, string> = {
  ACTIVE: "#E05C5C",
  SIGNAL: "#f59e0b",
  LATENT: "#5B7E99",
  QUIET: "var(--qgi-text-dim)",
};

const BAR_WIDTH = 56;

export function MoverRow({ mover }: { mover: PulseMover }) {
  const isRising = mover.direction === "rising";
  const deltaColor = isRising ? "#E05C5C" : "#5B7E99";
  const verdictColor = VERDICT_COLOR[mover.verdict];
  const filledWidth = Math.round((mover.pulse / 100) * BAR_WIDTH);
  const prevTick = Math.round((mover.prevPulse / 100) * BAR_WIDTH);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "5px",
        padding: "8px 10px",
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${deltaColor}`,
        borderRadius: "5px",
        minWidth: 0,
      }}
    >
      {/* Row 1: flag + full country name */}
      <div style={{ display: "flex", alignItems: "center", gap: "7px", minWidth: 0 }}>
        <FlagImg
          emoji={flagFor(mover.countryName)}
          name={mover.countryName}
          width={16}
          radius={2}
        />
        <div
          style={{
            fontSize: "12px",
            fontWeight: 600,
            color: "var(--qgi-text)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            minWidth: 0,
            flex: 1,
          }}
        >
          {mover.countryName}
        </div>
      </div>

      {/* Row 2: topic label — full width, never competes for space */}
      <div
        style={{
          fontSize: "10.5px",
          color: "var(--qgi-text-muted)",
          minWidth: 0,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {mover.topicLabel}
      </div>

      {/* Row 3: delta + mini-bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          minWidth: 0,
        }}
      >
        {/* Delta — monospace */}
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "13px",
            fontWeight: 700,
            color: deltaColor,
            letterSpacing: "-0.5px",
            whiteSpace: "nowrap",
            flexShrink: 0,
            lineHeight: 1,
          }}
        >
          {isRising ? "+" : ""}
          {Math.round(mover.delta)}
          <span style={{ fontSize: "10px" }}>{isRising ? " ↑" : " ↓"}</span>
        </div>

        {/* Mini-bar */}
        <div
          style={{
            position: "relative",
            width: `${BAR_WIDTH}px`,
            height: "6px",
            background: "var(--qgi-border)",
            borderRadius: "3px",
            flexShrink: 0,
            overflow: "visible",
          }}
        >
          {/* Filled portion (current pulse) */}
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              height: "100%",
              width: `${filledWidth}px`,
              background: verdictColor,
              borderRadius: "3px",
              opacity: 0.85,
            }}
          />
          {/* Previous-pulse tick */}
          <div
            style={{
              position: "absolute",
              left: `${prevTick}px`,
              top: "-2px",
              width: "2px",
              height: "10px",
              background: "var(--qgi-text-dim)",
              borderRadius: "1px",
              opacity: 0.6,
            }}
          />
        </div>
      </div>
    </div>
  );
}
