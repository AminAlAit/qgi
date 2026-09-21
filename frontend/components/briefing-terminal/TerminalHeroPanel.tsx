/**
 * TerminalHeroPanel — §2-B center column: the primary signal hero.
 *
 * Dominant panel. Full-bleed dark panel, 3px colored left-border.
 * Top strip → subject line → headline → stat mosaic → signal sentence → nav footer.
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { TerminalStatCell } from "./TerminalStatCell";

export interface HeroStat {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  accentColor: string;
  bgTint?: string;
}

export interface TerminalHeroPanelProps {
  countryName: string;
  topicLabel: string;
  iso3: string | null;
  headline: string;
  sentence: string;
  verdictLabel: string;
  verdictColor: string;
  verdictBg: string;
  verdictBorder: string;
  stats: HeroStat[];
  vintageQuarter: string;
  isLive: boolean;
  inPlayCount: number;
  liveTerminalIso: string;
}

export function TerminalHeroPanel({
  countryName,
  topicLabel,
  iso3,
  headline,
  sentence,
  verdictLabel,
  verdictColor,
  verdictBg,
  verdictBorder,
  stats,
  vintageQuarter,
  isLive,
  inPlayCount,
  liveTerminalIso,
}: TerminalHeroPanelProps) {
  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${verdictColor}`,
        borderRadius: "4px",
        padding: "16px 18px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      {/* Top strip: verdict badge · vintage · live status */}
      <div
        style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}
      >
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            fontWeight: 700,
            letterSpacing: "2px",
            textTransform: "uppercase",
            padding: "2px 7px",
            borderRadius: "3px",
            background: verdictBg,
            color: verdictColor,
            border: `1px solid ${verdictBorder}`,
          }}
        >
          {verdictLabel}
        </span>
        <span
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            color: "var(--qgi-text-dim)",
            letterSpacing: "0.4px",
          }}
        >
          {vintageQuarter}
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            fontFamily: "ui-monospace, monospace",
            fontSize: "9px",
            color: isLive ? "#3FBF8F" : "var(--qgi-text-dim)",
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: "5px",
              height: "5px",
              borderRadius: "50%",
              background: isLive ? "#3FBF8F" : "var(--qgi-text-dim)",
            }}
          />
          {isLive ? "LIVE" : "QUARTERLY"}
        </span>
      </div>

      {/* Subject line */}
      {iso3 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "7px",
            fontSize: "12px",
            fontWeight: 700,
            letterSpacing: "1.2px",
            textTransform: "uppercase",
            fontFamily: "ui-monospace, monospace",
            color: verdictColor,
            flexWrap: "wrap",
          }}
        >
          <FlagImg
            emoji={flagFor(countryName)}
            name={countryName}
            width={14}
            radius={2}
          />
          <span>{countryName}</span>
          <span style={{ color: "var(--qgi-border)", fontWeight: 400 }}>·</span>
          <span style={{ color: "var(--qgi-text-muted)" }}>{topicLabel}</span>
        </div>
      )}

      {/* Headline — the one editorial voice element, system sans */}
      <h2
        style={{
          fontSize: "clamp(22px, 2.8vw, 34px)",
          fontWeight: 700,
          lineHeight: 1.08,
          letterSpacing: "-0.6px",
          margin: 0,
          maxWidth: "520px",
          color: "var(--qgi-text)",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        {headline}
      </h2>

      {/* Stat mosaic */}
      {stats.length > 0 && (
        <div
          style={{ display: "flex", alignItems: "stretch", gap: "1px", flexWrap: "wrap" }}
        >
          {stats.map((stat, i) => (
            <TerminalStatCell
              key={stat.label}
              label={stat.label}
              value={stat.value}
              unit={stat.unit}
              sub={stat.sub}
              accentColor={stat.accentColor}
              bgTint={stat.bgTint}
              isFirst={i === 0}
              isLast={i === stats.length - 1}
            />
          ))}
        </div>
      )}

      {/* Signal sentence */}
      <p
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "12px",
          color: "var(--qgi-text-muted)",
          margin: 0,
          lineHeight: 1.5,
        }}
      >
        {sentence}
      </p>

      {/* Navigation footer */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          flexWrap: "wrap",
          fontFamily: "ui-monospace, monospace",
          fontSize: "10px",
          color: "var(--qgi-accent)",
          marginTop: "auto",
        }}
      >
        <Link
          href={"/risk-board" as Route}
          style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
        >
          Full board
        </Link>
        <span style={{ color: "var(--qgi-border)" }}>·</span>
        <Link
          href={"/trends" as Route}
          style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
        >
          {inPlayCount} trends
        </Link>
        <span style={{ color: "var(--qgi-border)" }}>·</span>
        <Link
          href={`/countries/${liveTerminalIso}` as Route}
          style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
        >
          Terminal →
        </Link>
      </div>
    </div>
  );
}
