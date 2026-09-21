/**
 * MoversBand — "Biggest movers this month" as a full-width horizontal panel.
 *
 * Risers and fallers are laid out in a horizontal row/grid so they read at a
 * glance without the vertical rail height. Placed full-width directly ABOVE the
 * AnalogueFeatured section in the Briefing page.
 *
 * Server component — no "use client".
 */
import type { PulseMover } from "@/lib/dashboard/briefing-insights";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

interface Props {
  risers: PulseMover[];
  fallers: PulseMover[];
  loudestTopicLabel: string;
  loudestTopicPulse: number;
}

export function MoversBand({
  risers,
  fallers,
  loudestTopicLabel,
  loudestTopicPulse,
}: Props) {
  if (risers.length === 0 && fallers.length === 0) return null;

  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "16px 20px",
      }}
    >
      <style>{`
        .qgi-mover-card {
          transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
        }
        .qgi-mover-card:hover {
          transform: translateY(-3px);
          box-shadow: 0 6px 20px rgba(0,0,0,0.30);
        }
        .qgi-mover-card.rising:hover { border-color: rgba(224,92,92,0.55); }
        .qgi-mover-card.falling:hover { border-color: rgba(91,126,153,0.55); }
      `}</style>
      {/* Panel header row */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "14px",
          marginBottom: "14px",
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--qgi-accent)",
          }}
        >
          Biggest Movers This Month
        </span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
          }}
        >
          Month-on-month news coverage shifts
        </span>
        {loudestTopicPulse > 0 && (
          <span
            style={{
              marginLeft: "auto",
              fontFamily: "ui-monospace, monospace",
              fontSize: "11px",
              color: "var(--qgi-text-dim)",
            }}
          >
            Loudest topic:{" "}
            <span style={{ color: "var(--qgi-text)" }}>{loudestTopicLabel}</span>
            {" · "}
            <span style={{ color: "#E05C5C", fontWeight: 700 }}>
              {loudestTopicPulse}
            </span>{" "}
            total pulse
          </span>
        )}
      </div>

      {/* Horizontal card band — risers then fallers, wrapped */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "10px",
        }}
      >
        {risers.map((m) => (
          <MoverCard key={m.key} mover={m} />
        ))}
        {fallers.map((m) => (
          <MoverCard key={m.key} mover={m} />
        ))}
      </div>
    </div>
  );
}

// ── Card component ─────────────────────────────────────────────────────────────

function MoverCard({ mover }: { mover: PulseMover }) {
  const isRising = mover.direction === "rising";
  const accentColor = isRising ? "#E05C5C" : "#5B7E99";
  const arrowColor = isRising ? "#E05C5C" : "#5B7E99";
  const deltaStr = isRising
    ? `+${Math.round(mover.delta)}`
    : String(Math.round(mover.delta));

  return (
    <div
      className={`qgi-mover-card ${isRising ? "rising" : "falling"}`}
      style={{
        flex: "1 1 180px",
        minWidth: "160px",
        maxWidth: "260px",
        padding: "10px 12px",
        background: "var(--qgi-bg)",
        border: `1px solid ${isRising ? "rgba(224,92,92,0.20)" : "rgba(91,126,153,0.20)"}`,
        borderRadius: "8px",
        display: "flex",
        flexDirection: "column",
        gap: "6px",
      }}
    >
      {/* Direction label */}
      <div
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "9px",
          letterSpacing: "1.5px",
          textTransform: "uppercase",
          color: arrowColor,
          fontWeight: 700,
        }}
      >
        {isRising ? "↑ Rising" : "↓ Falling"}
      </div>

      {/* Flag + country name — full, no truncation */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--qgi-text)",
          lineHeight: 1.2,
        }}
      >
        <FlagImg
          emoji={flagFor(mover.countryName)}
          name={mover.countryName}
          width={16}
          radius={2}
        />
        <span style={{ wordBreak: "break-word" }}>{mover.countryName}</span>
      </div>

      {/* Topic name — full, no truncation */}
      <div
        style={{
          fontSize: "11px",
          color: "var(--qgi-text-muted)",
          lineHeight: 1.3,
          wordBreak: "break-word",
        }}
      >
        {mover.topicLabel}
      </div>

      {/* Delta + current pulse */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "8px",
          marginTop: "2px",
        }}
      >
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "20px",
            fontWeight: 700,
            color: accentColor,
            lineHeight: 1,
            letterSpacing: "-0.5px",
          }}
        >
          {deltaStr}
        </span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            color: "var(--qgi-text-dim)",
          }}
        >
          pts
        </span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            color: "var(--qgi-text-muted)",
            marginLeft: "auto",
          }}
        >
          {Math.round(mover.pulse)}
          <span style={{ color: "var(--qgi-text-dim)" }}>/100</span>
        </span>
      </div>
    </div>
  );
}
