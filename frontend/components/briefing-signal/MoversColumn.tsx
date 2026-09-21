/**
 * MoversColumn — pulse movers list (risers + fallers) for the intel rail.
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import type { PulseMover } from "@/lib/dashboard/briefing-insights";
import { MoverRow } from "./MoverRow";

interface Props {
  risers: PulseMover[];
  fallers: PulseMover[];
  loudestTopicLabel: string;
  loudestTopicPulse: number;
}

export function MoversColumn({
  risers,
  fallers,
  loudestTopicLabel,
  loudestTopicPulse,
}: Props) {
  if (risers.length === 0 && fallers.length === 0) return null;

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
            color: "var(--qgi-accent)",
            marginBottom: "2px",
          }}
        >
          Biggest movers this month
        </div>
        <div
          style={{
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          Month-on-month news coverage shifts
        </div>
      </div>

      {/* Risers */}
      {risers.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "10px",
              fontFamily: "ui-monospace, monospace",
              textTransform: "uppercase",
              letterSpacing: "1.5px",
              color: "#E05C5C",
              marginBottom: "6px",
            }}
          >
            Rising
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {risers.map((m) => (
              <MoverRow key={m.key} mover={m} />
            ))}
          </div>
        </div>
      )}

      {/* Fallers */}
      {fallers.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "10px",
              fontFamily: "ui-monospace, monospace",
              textTransform: "uppercase",
              letterSpacing: "1.5px",
              color: "#5B7E99",
              marginBottom: "6px",
            }}
          >
            Falling
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {fallers.map((m) => (
              <MoverRow key={m.key} mover={m} />
            ))}
          </div>
        </div>
      )}

      {/* Loudest topic callout */}
      <div
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          color: "var(--qgi-text-dim)",
          padding: "8px 0 0",
          borderTop: "1px solid var(--qgi-border)",
          marginTop: "auto",
        }}
      >
        Loudest topic:{" "}
        <span style={{ color: "var(--qgi-text)" }}>{loudestTopicLabel}</span>
        {" · "}
        <span style={{ color: "#E05C5C", fontWeight: 700 }}>{loudestTopicPulse}</span>
        {" total pulse"}
      </div>

      {/* Footer link */}
      <Link
        href={"/risk-board" as Route}
        style={{
          fontSize: "11px",
          color: "var(--qgi-accent)",
          textDecoration: "none",
          fontFamily: "ui-monospace, monospace",
        }}
      >
        See full board →
      </Link>
    </div>
  );
}
