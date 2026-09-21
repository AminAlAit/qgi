"use client";
/**
 * LeadStory — the front-page PDB-style lead item.
 *
 * Two-column asymmetric layout: 65% narrative + 35% data sidebar.
 * The H1 is the largest text element on the page (clamp 36-56px).
 *
 * Client component — the ssr:false dynamic chart requires a Client Component
 * in Next.js 16. Receives serializable props from the server page.
 */
import dynamic from "next/dynamic";
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

const BriefingSparkbar = dynamic(
  () => import("./BriefingSparkbar").then((m) => ({ default: m.BriefingSparkbar })),
  { ssr: false }
);

export interface LeadStoryStat {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  accentColor: string;
}

export interface LeadStoryProps {
  countryName: string;
  topicLabel: string;
  iso3: string | null;
  headline: string;
  sentence: string;
  handoffSentence: string;
  verdictLabel: string;
  verdictBg: string;
  verdictColor: string;
  verdictBorder: string;
  stats: LeadStoryStat[];
  vintageQuarter: string;
  /** Struct value for BriefingSparkbar (0-100) */
  struct: number;
  /** Pulse value for BriefingSparkbar (0-100) */
  pulse: number;
  inPlayCount: number;
  liveTerminalIso: string;
}

export function LeadStory({
  countryName,
  topicLabel,
  iso3,
  headline,
  sentence,
  handoffSentence,
  verdictLabel,
  verdictBg,
  verdictColor,
  verdictBorder,
  stats,
  vintageQuarter,
  struct,
  pulse,
  inPlayCount,
  liveTerminalIso,
}: LeadStoryProps) {
  return (
    <section style={{ padding: "28px 0 0" }}>
      <style>{`
        .qgi-lead-grid {
          display: grid;
          grid-template-columns: 65% 35%;
          gap: 0;
        }
        .qgi-lead-right {
          padding-left: 28px;
          border-left: 1px solid var(--qgi-border);
        }
        @media (max-width: 899px) {
          .qgi-lead-grid {
            grid-template-columns: 1fr;
          }
          .qgi-lead-right {
            border-left: none;
            border-top: 1px solid var(--qgi-border);
            padding-left: 0;
            padding-top: 20px;
            margin-top: 20px;
          }
        }
      `}</style>

      <div className="qgi-lead-grid">
        {/* ── Left column: narrative ── */}
        <div style={{ paddingRight: "28px" }}>
          {/* Eyebrow: LEAD STORY + verdict chip */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "12px",
              flexWrap: "wrap",
            }}
          >
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "11px",
                fontWeight: 600,
                letterSpacing: "4px",
                textTransform: "uppercase",
                color: "var(--qgi-accent)",
              }}
            >
              LEAD STORY
            </span>
            <span
              style={{
                fontSize: "10px",
                fontWeight: 700,
                letterSpacing: "2px",
                textTransform: "uppercase",
                fontFamily: "ui-monospace, monospace",
                padding: "2px 8px",
                borderRadius: "3px",
                background: verdictBg,
                color: verdictColor,
                border: `1px solid ${verdictBorder}`,
              }}
            >
              {verdictLabel}
            </span>
          </div>

          {/* Flag + Country · Topic */}
          {iso3 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                marginBottom: "12px",
                fontFamily: "ui-monospace, monospace",
                fontSize: "13px",
                fontWeight: 600,
                color: verdictColor,
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
              <span style={{ color: "var(--qgi-text-muted)", fontWeight: 400 }}>
                {topicLabel}
              </span>
            </div>
          )}

          {/* H1 — the headline */}
          <h1
            style={{
              fontSize: "clamp(36px, 4.5vw, 56px)",
              fontWeight: 800,
              lineHeight: 1.04,
              letterSpacing: "-1.2px",
              margin: "0 0 18px",
              maxWidth: "560px",
              color: "var(--qgi-text)",
            }}
          >
            {headline}
          </h1>

          {/* Ruled dateline */}
          <div style={{ marginBottom: "16px" }}>
            <div
              style={{
                height: "1px",
                background: "var(--qgi-border)",
                opacity: 0.4,
                marginBottom: "6px",
              }}
            />
            <span
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px",
                color: "var(--qgi-text-dim)",
                letterSpacing: "0.5px",
              }}
            >
              {vintageQuarter} · QGI Structural Analysis
            </span>
          </div>

          {/* Lede paragraph */}
          <p
            style={{
              fontSize: "17px",
              lineHeight: 1.65,
              color: "var(--qgi-text-muted)",
              maxWidth: "520px",
              margin: "0 0 16px",
            }}
          >
            {sentence}
          </p>

          {/* Handoff footnote */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              flexWrap: "wrap",
              fontFamily: "ui-monospace, monospace",
              fontSize: "12px",
              color: "var(--qgi-text-dim)",
            }}
          >
            <span>{handoffSentence}</span>
            <span style={{ color: "var(--qgi-border)", padding: "0 3px" }}>·</span>
            <Link
              href={"/risk-board" as Route}
              style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
            >
              Full Board
            </Link>
            <span style={{ color: "var(--qgi-border)", padding: "0 3px" }}>·</span>
            <Link
              href={"/trends" as Route}
              style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
            >
              {inPlayCount} Trends
            </Link>
            <span style={{ color: "var(--qgi-border)", padding: "0 3px" }}>·</span>
            <Link
              href={`/countries/${liveTerminalIso}` as Route}
              style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
            >
              Terminal →
            </Link>
          </div>
        </div>

        {/* ── Right column: data sidebar ── */}
        <div className="qgi-lead-right">
          <div
            style={{
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderTop: `3px solid ${verdictColor}`,
              borderRadius: "6px",
              padding: "18px",
            }}
          >
            {/* DATA READ label */}
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10px",
                letterSpacing: "2px",
                color: "var(--qgi-text-dim)",
                textTransform: "uppercase",
                marginBottom: "14px",
              }}
            >
              DATA READ
            </div>

            {/* Stats */}
            {stats.map((stat, i) => (
              <div key={stat.label}>
                {i > 0 && (
                  <div
                    style={{
                      height: "1px",
                      background: "var(--qgi-border)",
                      margin: "12px 0",
                    }}
                  />
                )}
                <div
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "11px",
                    color: "var(--qgi-text-dim)",
                    letterSpacing: "1px",
                    textTransform: "uppercase",
                    marginBottom: "4px",
                  }}
                >
                  {stat.label}
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: "3px" }}>
                  <span
                    style={{
                      fontFamily: "ui-monospace, monospace",
                      fontSize: "28px",
                      fontWeight: 700,
                      fontVariantNumeric: "tabular-nums",
                      color: stat.accentColor,
                      lineHeight: 1,
                    }}
                  >
                    {stat.value}
                  </span>
                  {stat.unit && (
                    <span
                      style={{
                        fontFamily: "ui-monospace, monospace",
                        fontSize: "11px",
                        color: "var(--qgi-text-dim)",
                      }}
                    >
                      {stat.unit}
                    </span>
                  )}
                </div>
                {stat.sub && (
                  <div
                    style={{
                      fontFamily: "ui-monospace, monospace",
                      fontSize: "11px",
                      color: stat.accentColor,
                      marginTop: "2px",
                    }}
                  >
                    {stat.sub}
                  </div>
                )}
              </div>
            ))}

            {/* Sparkbar — struct vs pulse */}
            <div
              style={{
                marginTop: "16px",
                borderTop: "1px solid var(--qgi-border)",
                paddingTop: "12px",
              }}
            >
              <BriefingSparkbar
                struct={struct}
                pulse={pulse}
                verdictColor={verdictColor}
              />
            </div>

            {/* Bottom link */}
            <div style={{ marginTop: "8px" }}>
              <Link
                href={"/risk-board" as Route}
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "11px",
                  color: "var(--qgi-accent)",
                  textDecoration: "none",
                }}
              >
                → Open full board
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
