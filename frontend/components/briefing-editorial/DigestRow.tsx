/**
 * DigestRow — 3-column "above the fold" digest strip.
 *
 * Three equal columns separated by 1px border lines (The Economist broadsheet).
 * Each column: PULSE / STRUCTURE / RESEMBLANCE with a splash number and
 * one editorial sentence derived from the data.
 *
 * Server component — no "use client".
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import type { PulseMover, SilentAlarm } from "@/lib/dashboard/briefing-insights";
import type { ClosestMatch } from "@/lib/te-mock/dashboard-v4-1-data";

interface DigestRowProps {
  topRiser: PulseMover | null;
  topAlarm: SilentAlarm | null;
  topMatch: ClosestMatch | null;
}

export function DigestRow({ topRiser, topAlarm, topMatch }: DigestRowProps) {
  return (
    <section style={{ marginTop: "36px" }}>
      <style>{`
        .qgi-digest-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          background: var(--qgi-border);
          gap: 1px;
          border: 1px solid var(--qgi-border);
          border-radius: 6px;
          overflow: hidden;
        }
        .qgi-digest-col {
          background: var(--qgi-surface);
          padding: 20px 18px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        @media (max-width: 639px) {
          .qgi-digest-grid {
            grid-template-columns: 1fr;
          }
        }
        @media (min-width: 640px) and (max-width: 767px) {
          .qgi-digest-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }
      `}</style>

      <div className="qgi-digest-grid">
        {/* Column 1: PULSE — top riser */}
        <div className="qgi-digest-col">
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "11px",
              fontWeight: 600,
              letterSpacing: "3px",
              textTransform: "uppercase",
              color: "var(--qgi-text-dim)",
              marginBottom: "4px",
              borderBottom: "1px solid var(--qgi-border)",
              paddingBottom: "8px",
            }}
          >
            PULSE
          </div>
          {topRiser ? (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "14px",
                  fontWeight: 600,
                  color: "var(--qgi-text)",
                }}
              >
                <FlagImg
                  emoji={flagFor(topRiser.countryName)}
                  name={topRiser.countryName}
                  width={16}
                  radius={2}
                />
                <span>{topRiser.countryName}</span>
                <span
                  style={{
                    fontSize: "11px",
                    color: "var(--qgi-text-dim)",
                    fontWeight: 400,
                  }}
                >
                  · {topRiser.topicLabel}
                </span>
              </div>
              <div>
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "42px",
                    fontWeight: 800,
                    fontVariantNumeric: "tabular-nums",
                    color: "#E05C5C",
                    lineHeight: 1,
                  }}
                >
                  +{Math.round(topRiser.delta)}
                </span>
              </div>
              <div
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "10px",
                  color: "var(--qgi-text-dim)",
                }}
              >
                pts this month
              </div>
              <p
                style={{
                  fontSize: "12px",
                  color: "var(--qgi-text-muted)",
                  lineHeight: 1.5,
                  margin: "4px 0 0",
                  flex: 1,
                }}
              >
                {topRiser.delta >= 30
                  ? `The sharpest single-month coverage acceleration on the board. Structural confirmation is the key question.`
                  : topRiser.delta >= 15
                    ? `Coverage is surging. Structural read holds steady — the gap between signal and news is narrowing fast.`
                    : `The leading pulse mover this release. Coverage is building momentum across this country-topic pair.`}
              </p>
              <div style={{ marginTop: "auto", paddingTop: "8px", textAlign: "right" }}>
                <Link
                  href={"/risk-board" as Route}
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "10px",
                    color: "var(--qgi-accent)",
                    textDecoration: "none",
                  }}
                >
                  → risk-board
                </Link>
              </div>
            </>
          ) : (
            <div style={{ color: "var(--qgi-text-dim)", fontSize: "12px" }}>
              No pulse movers this release.
            </div>
          )}
        </div>

        {/* Column 2: STRUCTURE — top silent alarm */}
        <div className="qgi-digest-col">
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "11px",
              fontWeight: 600,
              letterSpacing: "3px",
              textTransform: "uppercase",
              color: "var(--qgi-text-dim)",
              marginBottom: "4px",
              borderBottom: "1px solid var(--qgi-border)",
              paddingBottom: "8px",
            }}
          >
            STRUCTURE
          </div>
          {topAlarm ? (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "14px",
                  fontWeight: 600,
                  color: "var(--qgi-text)",
                }}
              >
                <FlagImg
                  emoji={flagFor(topAlarm.countryName)}
                  name={topAlarm.countryName}
                  width={16}
                  radius={2}
                />
                <span>{topAlarm.countryName}</span>
                <span
                  style={{
                    fontSize: "11px",
                    color: "var(--qgi-text-dim)",
                    fontWeight: 400,
                  }}
                >
                  · {topAlarm.topicLabel}
                </span>
              </div>
              <div>
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "42px",
                    fontWeight: 800,
                    fontVariantNumeric: "tabular-nums",
                    color: "var(--qgi-amber)",
                    lineHeight: 1,
                  }}
                >
                  +{Math.round(topAlarm.gap)}
                </span>
              </div>
              <div
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "10px",
                  color: "var(--qgi-text-dim)",
                }}
              >
                pts ahead of news
              </div>
              <p
                style={{
                  fontSize: "12px",
                  color: "var(--qgi-text-muted)",
                  lineHeight: 1.5,
                  margin: "4px 0 0",
                  flex: 1,
                }}
              >
                {topAlarm.gap >= 40
                  ? `The widest structural-to-news divergence on the board. Structural resemblance is leading the headlines by a wide margin.`
                  : topAlarm.gap >= 20
                    ? `Structural pressure is building well ahead of any news confirmation. The board is watching this closely.`
                    : `Structure is running ahead of coverage. A signal worth tracking before the news cycle catches up.`}
              </p>
              <div style={{ marginTop: "auto", paddingTop: "8px", textAlign: "right" }}>
                <Link
                  href={"/risk-board" as Route}
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "10px",
                    color: "var(--qgi-accent)",
                    textDecoration: "none",
                  }}
                >
                  → risk-board
                </Link>
              </div>
            </>
          ) : (
            <div style={{ color: "var(--qgi-text-dim)", fontSize: "12px" }}>
              No structural pressure alarms this release.
            </div>
          )}
        </div>

        {/* Column 3: RESEMBLANCE — top analogue match */}
        <div className="qgi-digest-col">
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: "11px",
              fontWeight: 600,
              letterSpacing: "3px",
              textTransform: "uppercase",
              color: "var(--qgi-text-dim)",
              marginBottom: "4px",
              borderBottom: "1px solid var(--qgi-border)",
              paddingBottom: "8px",
            }}
          >
            RESEMBLANCE
          </div>
          {topMatch ? (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "14px",
                  fontWeight: 600,
                  color: "var(--qgi-text)",
                }}
              >
                <FlagImg
                  emoji={flagFor(topMatch.country)}
                  name={topMatch.country}
                  width={16}
                  radius={2}
                />
                <span>{topMatch.country}</span>
                <span
                  style={{
                    fontSize: "11px",
                    color: "var(--qgi-text-dim)",
                    fontWeight: 400,
                  }}
                >
                  · {topMatch.recipe_label}
                </span>
              </div>
              <div>
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "42px",
                    fontWeight: 800,
                    fontVariantNumeric: "tabular-nums",
                    color: "#C9A84C",
                    lineHeight: 1,
                  }}
                >
                  {Math.round(topMatch.score)}
                </span>
              </div>
              <div
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "10px",
                  color: "var(--qgi-text-dim)",
                }}
              >
                % structural match
              </div>
              <p
                style={{
                  fontSize: "12px",
                  color: "var(--qgi-text-muted)",
                  lineHeight: 1.5,
                  margin: "4px 0 0",
                  flex: 1,
                }}
              >
                {topMatch.score >= 95
                  ? `The top structural precedent match this release. A near-identical historical parallel — structural resemblance at this level is uncommon.`
                  : topMatch.score >= 90
                    ? `A strong precedent signal. The structural conditions today closely mirror a documented historical episode.`
                    : `A clear structural similarity to a past event. Not a forecast — a lens on what these conditions have meant before.`}
              </p>
              <div style={{ marginTop: "auto", paddingTop: "8px", textAlign: "right" }}>
                <Link
                  href={"/analogues" as Route}
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "10px",
                    color: "var(--qgi-accent)",
                    textDecoration: "none",
                  }}
                >
                  → analogues
                </Link>
              </div>
            </>
          ) : (
            <div style={{ color: "var(--qgi-text-dim)", fontSize: "12px" }}>
              No close analogue matches this release.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
