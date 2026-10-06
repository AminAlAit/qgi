/**
 * TerminalLivePulseStream — §2-C right column: live pulse stream rows.
 *
 * When live: sorted ACTIVE+SIGNAL cells as compact stream rows.
 * When absent: OFFLINE message.
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { TerminalPanelShell } from "./TerminalPanelShell";

export interface PulseStreamRow {
  key: string;
  iso3: string;
  countryName: string;
  topicLabel: string;
  pulse: number;
  verdict: "ACTIVE" | "SIGNAL" | "LATENT" | "QUIET";
}

export interface TerminalLivePulseStreamProps {
  rows: PulseStreamRow[];
  isLive: boolean;
  loudestTopicLabel: string;
  loudestTopicPulse: number;
}

const VERDICT_COLOR: Record<string, string> = {
  ACTIVE: "#E05C5C",
  SIGNAL: "#F59E0B",
  LATENT: "#5B7E99",
  QUIET: "var(--qgi-text-dim)",
};

export function TerminalLivePulseStream({
  rows,
  isLive,
  loudestTopicLabel,
  loudestTopicPulse,
}: TerminalLivePulseStreamProps) {
  const topRows = rows.slice(0, 8);

  return (
    <TerminalPanelShell
      title="Live Pulse"
      accent={isLive ? "#3FBF8F" : "#5B7E99"}
      topRight={
        isLive ? (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              fontFamily: "ui-monospace, monospace",
              fontSize: "9px",
              color: "#3FBF8F",
            }}
          >
            <span
              style={{
                display: "inline-block",
                width: "5px",
                height: "5px",
                borderRadius: "50%",
                background: "#3FBF8F",
              }}
            />
            LIVE
          </span>
        ) : null
      }
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
    >
      {!isLive ? (
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            padding: "8px 0",
            letterSpacing: "0.4px",
          }}
        >
          OFFLINE — quarterly data only
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {topRows.map((row, i) => {
            const vColor = VERDICT_COLOR[row.verdict] ?? "var(--qgi-text-dim)";
            const pulseBarWidth = Math.max(2, Math.round((row.pulse / 100) * 24));
            return (
              <div
                key={row.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "5px 6px",
                  background: i % 2 === 0 ? "rgba(22,32,50,0.5)" : "var(--qgi-bg)",
                  borderRadius: "2px",
                }}
              >
                {/* Flag */}
                <FlagImg
                  emoji={flagFor(row.countryName)}
                  name={row.countryName}
                  width={12}
                  radius={1}
                />
                {/* Country + topic */}
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "10px",
                    color: "var(--qgi-text-muted)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    flex: 1,
                  }}
                >
                  {row.iso3.toUpperCase()} · {row.topicLabel}
                </span>
                {/* Pulse bar */}
                <span
                  style={{
                    display: "inline-block",
                    width: "24px",
                    height: "4px",
                    background: "var(--qgi-border)",
                    borderRadius: "2px",
                    position: "relative",
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      position: "absolute",
                      left: 0,
                      top: 0,
                      height: "4px",
                      width: `${pulseBarWidth}px`,
                      background: vColor,
                      borderRadius: "2px",
                    }}
                  />
                </span>
                {/* Pulse number */}
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "10px",
                    fontWeight: 700,
                    color: vColor,
                    flexShrink: 0,
                    width: "22px",
                    textAlign: "right",
                  }}
                >
                  {Math.round(row.pulse)}
                </span>
                {/* Verdict chip */}
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "8px",
                    letterSpacing: "0.5px",
                    color: vColor,
                    flexShrink: 0,
                    width: "42px",
                    textAlign: "right",
                  }}
                >
                  {row.verdict}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Loudest topic sub-row */}
      {loudestTopicLabel && (
        <div
          style={{
            marginTop: "10px",
            padding: "6px 8px",
            background: "rgba(245,158,11,0.06)",
            border: "1px solid rgba(245,158,11,0.20)",
            borderRadius: "3px",
          }}
        >
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "9px",
              color: "var(--qgi-text-dim)",
              letterSpacing: "1px",
              textTransform: "uppercase",
            }}
          >
            Loudest Topic
          </span>
          <div
            style={{ display: "flex", justifyContent: "space-between", marginTop: "3px" }}
          >
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "11px",
                color: "var(--qgi-text)",
                fontWeight: 600,
              }}
            >
              {loudestTopicLabel}
            </span>
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "11px",
                fontWeight: 700,
                color: "#F59E0B",
              }}
            >
              {loudestTopicPulse}
            </span>
          </div>
        </div>
      )}

      {/* CTA */}
      <div style={{ marginTop: "auto", paddingTop: "10px" }}>
        <Link
          href={"/risk-board" as Route}
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            color: "var(--qgi-accent)",
            textDecoration: "none",
            letterSpacing: "0.6px",
          }}
        >
          Risk Board →
        </Link>
      </div>
    </TerminalPanelShell>
  );
}
