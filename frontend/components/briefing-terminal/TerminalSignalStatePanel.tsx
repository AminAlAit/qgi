/**
 * TerminalSignalStatePanel — §2-A left column: top ACTIVE/SIGNAL cells + silent alarms.
 *
 * Shows top 5 cells by (struct + pulse) descending, then a SILENT ALARMS sub-section
 * with top 3 alarms. Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import { TerminalMiniCard } from "./TerminalMiniCard";
import { TerminalPanelShell } from "./TerminalPanelShell";

export interface SignalCell {
  key: string;
  countryName: string;
  topicLabel: string;
  pulse: number;
  struct: number;
  verdict: "ACTIVE" | "SIGNAL" | "LATENT" | "QUIET";
}

export interface SignalAlarm {
  countryName: string;
  topicLabel: string;
  struct: number;
  gap: number;
}

export interface TerminalSignalStatePanelProps {
  topCells: SignalCell[];
  silentAlarms: SignalAlarm[];
}

export function TerminalSignalStatePanel({
  topCells,
  silentAlarms,
}: TerminalSignalStatePanelProps) {
  const topThreeAlarms = silentAlarms.slice(0, 3);

  return (
    <TerminalPanelShell
      title="Signal State"
      accent="#E05C5C"
      style={{ height: "100%", display: "flex", flexDirection: "column" }}
    >
      {/* Top cells */}
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {topCells.slice(0, 5).map((cell) => (
          <TerminalMiniCard
            key={cell.key}
            countryName={cell.countryName}
            topicLabel={cell.topicLabel}
            pulse={cell.pulse}
            struct={cell.struct}
            verdict={cell.verdict}
          />
        ))}
      </div>

      {/* CTA */}
      <div style={{ marginTop: "10px" }}>
        <Link
          href={"/risk-board" as Route}
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "10px",
            color: "var(--qgi-accent)",
            letterSpacing: "0.6px",
            textDecoration: "none",
          }}
        >
          Full board →
        </Link>
      </div>

      {/* Silent alarms sub-section */}
      {topThreeAlarms.length > 0 && (
        <div
          style={{
            marginTop: "14px",
            borderTop: "1px solid var(--qgi-border)",
            paddingTop: "10px",
          }}
        >
          <span
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "9px",
              fontWeight: 700,
              letterSpacing: "1.8px",
              textTransform: "uppercase",
              color: "var(--qgi-amber, #F59E0B)",
              display: "block",
              marginBottom: "8px",
            }}
          >
            Silent Alarms
          </span>
          <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
            {topThreeAlarms.map((alarm, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "5px 8px",
                  background: "rgba(245,158,11,0.06)",
                  border: "1px solid rgba(245,158,11,0.20)",
                  borderLeft: "2px solid var(--qgi-amber, #F59E0B)",
                  borderRadius: "3px",
                  gap: "6px",
                }}
              >
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
                  {alarm.countryName} · {alarm.topicLabel}
                </span>
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "10px",
                    fontWeight: 700,
                    color: "var(--qgi-amber, #F59E0B)",
                    flexShrink: 0,
                  }}
                >
                  +{Math.round(alarm.gap)} pts
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </TerminalPanelShell>
  );
}
