/**
 * HeroSplit — two-column hero for the Signal Board.
 *
 * Left (55%): Hot Signal Card — the loudest board signal with stat tiles.
 * Right (45%): Three compact SpotlightTiles (alarm, riser, match).
 *
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { SignalStatTile } from "./SignalStatTile";
import { SpotlightTileInner } from "./SpotlightTile";
import type { SpotlightData } from "./SpotlightTile";

export interface HeroStat {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  accentColor: string;
  bgTint?: string;
}

export interface HeroSignalData {
  countryName: string;
  topicLabel: string;
  iso3: string | null;
  stats: HeroStat[];
  headline: string;
  sentence: string;
  verdictLabel: string;
  verdictBg: string;
  verdictColor: string;
  verdictBorder: string;
}

interface Props {
  heroSignal: HeroSignalData;
  spotlights: SpotlightData[];
  inPlayCount: number;
  liveTerminalIso: string;
  vintage: string;
}

export function HeroSplit({
  heroSignal,
  spotlights,
  inPlayCount,
  liveTerminalIso,
  vintage,
}: Props) {
  return (
    <>
      <style>{`
        .qgi-sb-hero-grid {
          display: grid;
          grid-template-columns: 55% 45%;
          gap: 16px;
          align-items: stretch;
        }
        @media (max-width: 1099px) {
          .qgi-sb-hero-grid {
            grid-template-columns: 1fr;
          }
          .qgi-sb-spotlights {
            display: flex !important;
            flex-direction: row !important;
            gap: 10px !important;
          }
        }
        @media (max-width: 767px) {
          .qgi-sb-spotlights {
            flex-direction: column !important;
          }
        }
      `}</style>
      <div className="qgi-sb-hero-grid">
        {/* Left: Hot Signal Card */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "14px",
            padding: "20px",
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderLeft: `4px solid ${heroSignal.verdictColor}`,
            borderRadius: "10px",
            minHeight: "220px",
          }}
        >
          {/* Eyebrow row: verdict chip + vintage chip */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                fontSize: "9px",
                fontWeight: 700,
                letterSpacing: "2px",
                textTransform: "uppercase",
                fontFamily: "ui-monospace, monospace",
                padding: "2px 8px",
                borderRadius: "3px",
                background: heroSignal.verdictBg,
                color: heroSignal.verdictColor,
                border: `1px solid ${heroSignal.verdictBorder}`,
              }}
            >
              {heroSignal.verdictLabel}
            </span>
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "9px",
                color: "var(--qgi-text-dim)",
                padding: "2px 7px",
                borderRadius: "3px",
                background: "rgba(91,126,153,0.10)",
                border: "1px solid rgba(91,126,153,0.20)",
              }}
            >
              v{vintage}
            </span>
          </div>

          {/* Country + Topic row */}
          {heroSignal.iso3 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                flexWrap: "wrap",
              }}
            >
              <FlagImg
                emoji={flagFor(heroSignal.countryName)}
                name={heroSignal.countryName}
                width={20}
                radius={2}
              />
              <span
                style={{
                  fontSize: "18px",
                  fontWeight: 600,
                  color: "var(--qgi-text)",
                }}
              >
                {heroSignal.countryName}
              </span>
              <span style={{ color: "var(--qgi-border)" }}>·</span>
              <span style={{ fontSize: "16px", color: "var(--qgi-text-muted)" }}>
                {heroSignal.topicLabel}
              </span>
            </div>
          )}

          {/* H1 headline */}
          <h1
            style={{
              fontSize: "clamp(28px, 2.8vw, 40px)",
              fontWeight: 700,
              lineHeight: 1.07,
              letterSpacing: "-0.8px",
              margin: 0,
              maxWidth: "480px",
              color: "var(--qgi-text)",
            }}
          >
            {heroSignal.headline}
          </h1>

          {/* Stat cluster */}
          {heroSignal.stats.length > 0 && (
            <div
              style={{
                display: "flex",
                alignItems: "stretch",
                gap: "1px",
                flexWrap: "wrap",
              }}
            >
              {heroSignal.stats.map((stat, i) => (
                <SignalStatTile
                  key={stat.label}
                  label={stat.label}
                  value={stat.value}
                  unit={stat.unit}
                  sub={stat.sub}
                  accentColor={stat.accentColor}
                  bgTint={stat.bgTint}
                  isFirst={i === 0}
                  isLast={i === heroSignal.stats.length - 1}
                />
              ))}
            </div>
          )}

          {/* Editorial sentence */}
          <p
            style={{
              fontSize: "15px",
              color: "var(--qgi-text-muted)",
              margin: 0,
              maxWidth: "480px",
              lineHeight: 1.6,
            }}
          >
            {heroSignal.sentence}
          </p>

          {/* CTA links */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              flexWrap: "wrap",
              fontSize: "12px",
              fontFamily: "ui-monospace, monospace",
              marginTop: "auto",
            }}
          >
            <Link
              href={"/risk-board" as Route}
              style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
            >
              Full board →
            </Link>
            <span style={{ color: "var(--qgi-border)", padding: "0 4px" }}>·</span>
            <Link
              href={"/trends" as Route}
              style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
            >
              {inPlayCount} trends in play →
            </Link>
            <span style={{ color: "var(--qgi-border)", padding: "0 4px" }}>·</span>
            <Link
              href={`/countries/${liveTerminalIso}` as Route}
              style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
            >
              Terminal →
            </Link>
          </div>
        </div>

        {/* Right: Three spotlight tiles */}
        <div
          className="qgi-sb-spotlights"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "10px",
          }}
        >
          {spotlights.map((s, i) => (
            <div key={i} style={{ flex: 1 }}>
              <SpotlightTileInner data={s} />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
