/**
 * EditorialColumns — two-column editorial list panel.
 *
 * Left: Rising Coverage (top pulse risers, horizontal list rows).
 * Right: Structural Pressure (top silent alarms, horizontal list rows).
 *
 * Rows are hairline-separated, not cards. Reads faster at high density.
 *
 * Server component — no "use client".
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { PanelBase } from "@/components/dashboard-v4-1/PanelBase";
import type { PulseMover, SilentAlarm } from "@/lib/dashboard/briefing-insights";

interface EditorialColumnsProps {
  risers: PulseMover[];
  alarms: SilentAlarm[];
  loudestTopicLabel: string;
  loudestTopicPulse: number;
}

function MiniBarTrack({ fill, color }: { fill: number; color: string }) {
  return (
    <div
      style={{
        width: "56px",
        height: "4px",
        background: "var(--qgi-border)",
        borderRadius: "2px",
        overflow: "hidden",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          width: `${Math.min(100, fill)}%`,
          height: "100%",
          background: color,
          borderRadius: "2px",
        }}
      />
    </div>
  );
}

export function EditorialColumns({
  risers,
  alarms,
  loudestTopicLabel,
  loudestTopicPulse,
}: EditorialColumnsProps) {
  const displayRisers = risers.slice(0, 4);
  const displayAlarms = alarms.slice(0, 4);

  const avgGap =
    alarms.length > 0
      ? Math.round(
          alarms.slice(0, 4).reduce((sum, a) => sum + a.gap, 0) /
            Math.min(4, alarms.length)
        )
      : 0;

  return (
    <PanelBase
      title="Intelligence Digest"
      accent="#5B7E99"
      caption="Where coverage is accelerating and where structural pressure is building without news confirmation."
    >
      <style>{`
        .qgi-editorial-cols {
          display: grid;
          grid-template-columns: 1fr 1px 1fr;
          gap: 0;
        }
        .qgi-editorial-divider {
          background: var(--qgi-border);
          margin: 0 20px;
        }
        @media (max-width: 639px) {
          .qgi-editorial-cols {
            grid-template-columns: 1fr;
          }
          .qgi-editorial-divider {
            display: none;
          }
        }
      `}</style>

      <div className="qgi-editorial-cols">
        {/* Left: Rising Coverage */}
        <div>
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "3px",
              textTransform: "uppercase",
              color: "#E05C5C",
              marginBottom: "12px",
            }}
          >
            RISING COVERAGE
          </div>

          {displayRisers.length === 0 ? (
            <div style={{ color: "var(--qgi-text-dim)", fontSize: "12px" }}>
              No significant risers this release.
            </div>
          ) : (
            displayRisers.map((mover, i) => (
              <div
                key={mover.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "9px 0",
                  borderTop: i > 0 ? "1px solid var(--qgi-border)" : undefined,
                  flexWrap: "wrap",
                }}
              >
                <FlagImg
                  emoji={flagFor(mover.countryName)}
                  name={mover.countryName}
                  width={14}
                  radius={2}
                />
                <span
                  style={{ fontSize: "13px", fontWeight: 600, color: "var(--qgi-text)" }}
                >
                  {mover.countryName}
                </span>
                <span
                  style={{
                    fontSize: "11px",
                    color: "var(--qgi-text-dim)",
                  }}
                >
                  {mover.topicLabel}
                </span>
                <span
                  style={{
                    marginLeft: "auto",
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "13px",
                    fontWeight: 700,
                    color: "#E05C5C",
                    flexShrink: 0,
                  }}
                >
                  +{Math.round(mover.delta)} ↑
                </span>
                <MiniBarTrack fill={mover.pulse} color="#E05C5C" />
              </div>
            ))
          )}

          {/* Editorial summary sentence */}
          {loudestTopicLabel && (
            <p
              style={{
                fontSize: "11px",
                fontStyle: "italic",
                color: "var(--qgi-text-muted)",
                marginTop: "12px",
                lineHeight: 1.5,
              }}
            >
              {loudestTopicLabel} is the most-covered domain this release at{" "}
              {loudestTopicPulse} combined pulse.
            </p>
          )}
        </div>

        {/* Divider */}
        <div className="qgi-editorial-divider" />

        {/* Right: Structural Pressure */}
        <div>
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "3px",
              textTransform: "uppercase",
              color: "var(--qgi-amber)",
              marginBottom: "12px",
            }}
          >
            STRUCTURAL PRESSURE
          </div>

          {displayAlarms.length === 0 ? (
            <div style={{ color: "var(--qgi-text-dim)", fontSize: "12px" }}>
              No structural alarms this release.
            </div>
          ) : (
            displayAlarms.map((alarm, i) => (
              <div
                key={alarm.key}
                style={{
                  padding: "9px 0",
                  borderTop: i > 0 ? "1px solid var(--qgi-border)" : undefined,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    marginBottom: "4px",
                    flexWrap: "wrap",
                  }}
                >
                  <FlagImg
                    emoji={flagFor(alarm.countryName)}
                    name={alarm.countryName}
                    width={14}
                    radius={2}
                  />
                  <span
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--qgi-text)",
                    }}
                  >
                    {alarm.countryName}
                  </span>
                  <span style={{ fontSize: "11px", color: "var(--qgi-text-dim)" }}>
                    {alarm.topicLabel}
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "ui-monospace, monospace",
                      fontSize: "10px",
                      color: "var(--qgi-text-dim)",
                    }}
                  >
                    struct{" "}
                    <span style={{ color: "var(--qgi-amber)", fontWeight: 600 }}>
                      {Math.round(alarm.struct)}
                    </span>{" "}
                    · pulse{" "}
                    <span style={{ color: "var(--qgi-text)" }}>
                      {Math.round(alarm.pulse)}
                    </span>{" "}
                    · gap{" "}
                    <span style={{ color: "var(--qgi-amber)", fontWeight: 700 }}>
                      +{Math.round(alarm.gap)}
                    </span>
                  </span>
                  <MiniBarTrack fill={alarm.struct} color="var(--qgi-amber)" />
                </div>
              </div>
            ))
          )}

          {/* Editorial summary sentence */}
          {displayAlarms.length > 0 && avgGap > 0 && (
            <p
              style={{
                fontSize: "11px",
                fontStyle: "italic",
                color: "var(--qgi-text-muted)",
                marginTop: "12px",
                lineHeight: 1.5,
              }}
            >
              In these {displayAlarms.length} cases, structural resemblance is running{" "}
              {avgGap} points ahead of news confirmation.
            </p>
          )}
        </div>
      </div>
    </PanelBase>
  );
}
