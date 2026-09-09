/**
 * PulseMoversPanel — biggest month-on-month pulse shifts.
 *
 * Perpetual: receives pre-derived PulseMover arrays from deriveBriefingInsights().
 * No hardcoded country/number/sentence. Everything flows from real data.
 *
 * Server component. No "use client".
 */
import Link from "next/link";
import type { Route } from "next";
import { PanelBase } from "./PanelBase";
import type { PulseMover } from "@/lib/dashboard/briefing-insights";
import type { HfVerdict } from "@/lib/hf/topics-data";

const VERDICT_COLOR: Record<HfVerdict, string> = {
  ACTIVE: "#E05C5C",
  SIGNAL: "#f59e0b",
  LATENT: "#5B7E99",
  QUIET: "var(--qgi-text-dim)",
};

interface Props {
  risers: PulseMover[];
  fallers: PulseMover[];
  loudestTopicLabel: string;
  loudestTopicPulse: number;
}

export function PulseMoversPanel({
  risers,
  fallers,
  loudestTopicLabel,
  loudestTopicPulse,
}: Props) {
  if (risers.length === 0 && fallers.length === 0) return null;

  const rightSlot = (
    <span
      style={{
        fontSize: "10px",
        fontFamily: "ui-monospace, monospace",
        color: "var(--qgi-text-dim)",
        letterSpacing: "0.3px",
        whiteSpace: "nowrap",
      }}
    >
      Loudest topic: <span style={{ color: "var(--qgi-text)" }}>{loudestTopicLabel}</span>
      {" · "}
      <span style={{ color: "#E05C5C", fontWeight: 700 }}>{loudestTopicPulse}</span> total
      pulse
    </span>
  );

  return (
    <PanelBase
      title="Biggest pulse movers this month"
      caption="Month-on-month shifts in news coverage intensity. Not a forecast — structural context lives on the board."
      accent="#E05C5C"
      rightSlot={rightSlot}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "10px 24px",
        }}
      >
        {/* Rising column */}
        {risers.length > 0 && (
          <div>
            <div
              style={{
                fontSize: "10px",
                fontFamily: "ui-monospace, monospace",
                textTransform: "uppercase",
                letterSpacing: "1.5px",
                color: "#E05C5C",
                marginBottom: "8px",
              }}
            >
              Rising
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {risers.map((m) => (
                <MoverRow key={m.key} mover={m} />
              ))}
            </div>
          </div>
        )}

        {/* Falling column */}
        {fallers.length > 0 && (
          <div>
            <div
              style={{
                fontSize: "10px",
                fontFamily: "ui-monospace, monospace",
                textTransform: "uppercase",
                letterSpacing: "1.5px",
                color: "#5B7E99",
                marginBottom: "8px",
              }}
            >
              Falling
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {fallers.map((m) => (
                <MoverRow key={m.key} mover={m} />
              ))}
            </div>
          </div>
        )}
      </div>

      <div style={{ marginTop: "12px" }}>
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
          See full board →
        </Link>
      </div>
    </PanelBase>
  );
}

function MoverRow({ mover }: { mover: PulseMover }) {
  const isRising = mover.direction === "rising";
  const deltaColor = isRising ? "#E05C5C" : "#5B7E99";
  const verdictColor = VERDICT_COLOR[mover.verdict];

  // Inline mini-bar: 64px track, filled portion based on current pulse (0-100)
  const BAR_WIDTH = 64;
  const filledWidth = Math.round((mover.pulse / 100) * BAR_WIDTH);
  // Prev pulse tick position
  const prevTick = Math.round((mover.prevPulse / 100) * BAR_WIDTH);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "7px 10px",
        background: "var(--qgi-bg)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${deltaColor}`,
        borderRadius: "5px",
        minWidth: 0,
      }}
    >
      {/* Labels */}
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
          {mover.countryName}
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
          {mover.topicLabel}
        </div>
      </div>

      {/* Delta badge */}
      <div
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "13px",
          fontWeight: 700,
          color: deltaColor,
          letterSpacing: "-0.3px",
          whiteSpace: "nowrap",
          flexShrink: 0,
        }}
      >
        {isRising ? "+" : ""}
        {mover.delta}
        {isRising ? " ↑" : " ↓"}
      </div>

      {/* Mini bar */}
      <div
        style={{
          position: "relative",
          width: `${BAR_WIDTH}px`,
          height: "6px",
          background: "rgba(91,126,153,0.18)",
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
  );
}
