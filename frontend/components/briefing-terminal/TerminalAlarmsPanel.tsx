/**
 * TerminalAlarmsPanel — §3-right: silent alarms + caught-up stacked.
 *
 * Two sub-panels inside one column, divided by a 1px border.
 * Server component.
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

export interface AlarmRow {
  countryName: string;
  topicLabel: string;
  struct: number;
  gap: number;
}

export interface CaughtUpRow {
  countryName: string;
  topicLabel: string;
  pulse: number;
  struct: number;
  crossoverPct: number;
}

export interface HistoricHighRow {
  countryName: string;
  topicLabel: string;
  currentPulse: number;
  pct: number;
}

export interface TerminalAlarmsPanelProps {
  silentAlarms: AlarmRow[];
  caughtUp: CaughtUpRow[];
  atHistoricHigh: HistoricHighRow[];
}

export function TerminalAlarmsPanel({
  silentAlarms,
  caughtUp,
  atHistoricHigh,
}: TerminalAlarmsPanelProps) {
  const topAlarms = silentAlarms.slice(0, 3);
  const topCaughtUp = caughtUp.slice(0, 2);
  const topHighs = atHistoricHigh.slice(0, 2);
  const showBottomHalf = topCaughtUp.length > 0 || topHighs.length > 0;

  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderTop: "2px solid #F59E0B",
        borderRadius: "4px",
        padding: "12px 14px",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Top half: Silent Alarms */}
      <div>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            fontWeight: 700,
            letterSpacing: "1.8px",
            textTransform: "uppercase",
            color: "#F59E0B",
            display: "block",
            marginBottom: "8px",
          }}
        >
          Silent Alarms
        </span>
        <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
          {topAlarms.map((alarm, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "7px",
                padding: "5px 8px",
                background: "rgba(245,158,11,0.05)",
                border: "1px solid rgba(245,158,11,0.18)",
                borderLeft: "2px solid #F59E0B",
                borderRadius: "3px",
              }}
            >
              <FlagImg
                emoji={flagFor(alarm.countryName)}
                name={alarm.countryName}
                width={12}
                radius={1}
              />
              <span
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "10px",
                  color: "var(--qgi-text-muted)",
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {alarm.countryName} · {alarm.topicLabel}
              </span>
              <span
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "10px",
                  fontWeight: 700,
                  color: "#F59E0B",
                  flexShrink: 0,
                }}
              >
                struct {Math.round(alarm.struct)} | +{Math.round(alarm.gap)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Divider + Bottom half: Caught Up / Historic Highs */}
      {showBottomHalf && (
        <div
          style={{
            marginTop: "12px",
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
              color: "var(--qgi-text-dim)",
              display: "block",
              marginBottom: "8px",
            }}
          >
            Caught Up / Historic Highs
          </span>
          <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
            {topCaughtUp.map((cell, i) => (
              <div
                key={`cu-${i}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "7px",
                  padding: "5px 8px",
                  background: "rgba(63,191,143,0.05)",
                  border: "1px solid rgba(63,191,143,0.18)",
                  borderLeft: "2px solid #3FBF8F",
                  borderRadius: "3px",
                }}
              >
                <FlagImg
                  emoji={flagFor(cell.countryName)}
                  name={cell.countryName}
                  width={12}
                  radius={1}
                />
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "10px",
                    color: "var(--qgi-text-muted)",
                    flex: 1,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {cell.countryName} · {cell.topicLabel}
                </span>
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "9px",
                    fontWeight: 700,
                    color: "#3FBF8F",
                    padding: "1px 5px",
                    background: "rgba(63,191,143,0.12)",
                    borderRadius: "3px",
                    flexShrink: 0,
                  }}
                >
                  CAUGHT UP
                </span>
              </div>
            ))}
            {topHighs.map((cell, i) => (
              <div
                key={`hh-${i}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "7px",
                  padding: "5px 8px",
                  background: "rgba(198,160,60,0.05)",
                  border: "1px solid rgba(198,160,60,0.18)",
                  borderLeft: "2px solid #C6A03C",
                  borderRadius: "3px",
                }}
              >
                <FlagImg
                  emoji={flagFor(cell.countryName)}
                  name={cell.countryName}
                  width={12}
                  radius={1}
                />
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "10px",
                    color: "var(--qgi-text-muted)",
                    flex: 1,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {cell.countryName} · {cell.topicLabel}
                </span>
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "9px",
                    fontWeight: 700,
                    color: "#C6A03C",
                    padding: "1px 5px",
                    background: "rgba(198,160,60,0.12)",
                    borderRadius: "3px",
                    flexShrink: 0,
                  }}
                >
                  DECADE HIGH
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
