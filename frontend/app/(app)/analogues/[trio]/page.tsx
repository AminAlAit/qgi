/**
 * /analogues/[trio] — individual analogue comparison page.
 *
 * trio = `{subjectIso2}-{analogueIso2}-{year}` (e.g. "eg-sy-2011").
 *
 * Shows ONE analogue the Trajectory Engine surfaced for a subject country: the
 * subject (today) beside a past country-year, under a primary trend. For each
 * DRIVER indicator that defines that trend, the two countries' trajectories are
 * overlaid over the trend's canonical window — the subject's recent run-up vs
 * the analogue's run-up to its event. Series are standardized to each country's
 * own history, so the overlay reads as SHAPE resemblance, not raw level.
 *
 * Reuses the pattern-detail visual language (PanelCard / PanelHeading, dual-flag
 * header, "Not a forecast" footer) and the TrajectorySparkline overlay.
 *
 * Honesty: every claim here is a SIMILARITY statement. "What happened next" is
 * dated history about the ANALOGUE country, never a forecast about the subject.
 *
 * Zero mocks: all data from getAnaloguePair (real analogs + driver panels +
 * curated narratives). Trends with no panel-backed drivers for the pair show an
 * honest placeholder rather than a fabricated chart.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import type { Route } from "next";
import { notFound } from "next/navigation";
import { getAnaloguePair, allAnaloguePairKeys } from "@/lib/te-mock/analogue-pair";
import { AnalogueOverlayChart } from "@/components/analogue/AnalogueOverlayChart";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";

interface Params {
  params: Promise<{ trio: string }>;
}

/** Parse "{iso2}-{iso2}-{year}" → [si, ai, year] or null. */
function parseTrio(trio: string | undefined): [string, string, number] | null {
  const parts = (trio ?? "").split("-");
  if (parts.length !== 3) return null;
  const [si, ai, yearStr] = parts;
  const year = Number(yearStr);
  if (!/^[a-z]{2}$/i.test(si) || !/^[a-z]{2}$/i.test(ai)) return null;
  if (!Number.isInteger(year) || year < 1800 || year > 2100) return null;
  return [si, ai, year];
}

export function generateStaticParams() {
  return allAnaloguePairKeys();
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { trio } = await params;
  const parsed = parseTrio(trio);
  const pair = parsed ? getAnaloguePair(parsed[0], parsed[1], parsed[2]) : null;
  if (!pair) {
    return { title: "Analogue not found · QG Intelligence" };
  }
  return {
    title: `${pair.subjectName} ≈ ${pair.analogueName} ${pair.analogueYear} · Analogue · QG Intelligence`,
    description: `${pair.subjectName}'s recent trajectory resembles ${pair.analogueName} in the run-up to its ${pair.analogueYear} ${pair.trendLabel.toLowerCase()} (${Math.round(pair.matchScore)}% shape match). A similarity, not a forecast.`,
  };
}

/** Match-quality zone (mirrors AnalogCard thresholds). */
function zoneOf(score: number): { label: string; color: string } {
  if (score >= 85) return { label: "STRONG MATCH", color: "#3FBF8F" };
  if (score >= 70) return { label: "MODERATE MATCH", color: "#E6C45E" };
  return { label: "WEAK MATCH", color: "#E68F29" };
}

/** Card wrapper — matches /patterns/[slug] dark-surface visual system. */
function PanelCard({ children, dataTour }: { children: ReactNode; dataTour?: string }) {
  return (
    <div
      data-tour={dataTour}
      style={{
        background: "var(--qgi-surface)",
        border: "1px solid var(--qgi-border)",
        borderRadius: "10px",
        padding: "20px 22px",
        marginBottom: "20px",
      }}
    >
      {children}
    </div>
  );
}

function PanelHeading({ label, title }: { label: string; title: string }) {
  return (
    <div style={{ marginBottom: "14px" }}>
      <div
        style={{
          fontSize: "9px",
          letterSpacing: "1.6px",
          color: "var(--qgi-text-dim)",
          fontFamily: "ui-monospace, monospace",
          marginBottom: "4px",
          fontWeight: 600,
        }}
      >
        {label}
      </div>
      <h2
        style={{ fontSize: "15px", fontWeight: 700, margin: 0, color: "var(--qgi-text)" }}
      >
        {title}
      </h2>
    </div>
  );
}

export default async function AnaloguePairPage({ params }: Params) {
  const { trio } = await params;
  const parsed = parseTrio(trio);
  if (!parsed) notFound();
  const pair = getAnaloguePair(parsed[0], parsed[1], parsed[2]);
  if (!pair) notFound();

  const zone = zoneOf(pair.matchScore);
  const fam = pair.familyColor;

  return (
    <div
      style={{ minHeight: "100%", background: "var(--qgi-bg)", color: "var(--qgi-text)" }}
    >
      <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "24px 24px 64px" }}>
        {/* ── Header band ── */}
        <div
          data-tour="analogue-header"
          style={{
            background: "var(--qgi-surface)",
            border: "1px solid var(--qgi-border)",
            borderRadius: "10px",
            padding: "20px 24px 24px",
            marginBottom: "20px",
          }}
        >
          {/* Breadcrumb */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "11px",
              color: "var(--qgi-text-muted)",
              fontFamily: "ui-monospace, monospace",
              marginBottom: "16px",
              flexWrap: "wrap",
            }}
          >
            <Link
              href={"/analogues" as Route}
              style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
            >
              Analogues
            </Link>
            <span style={{ color: "var(--qgi-text-dim)" }}>/</span>
            <span style={{ color: "var(--qgi-text)" }}>
              {pair.subjectName} ≈ {pair.analogueName} {pair.analogueYear}
            </span>
          </div>

          {/* Dual-flag + title */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              marginBottom: "14px",
            }}
          >
            <div
              style={{
                position: "relative",
                width: "88px",
                height: "66px",
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "60px",
                  height: "45px",
                  border: "2px solid var(--qgi-accent)",
                  borderRadius: "4px",
                  overflow: "hidden",
                  zIndex: 2,
                }}
              >
                <FlagImg
                  emoji={flagFor(pair.subjectName)}
                  name={pair.subjectName}
                  width={60}
                  radius={2}
                />
              </div>
              <div
                style={{
                  position: "absolute",
                  bottom: 0,
                  right: 0,
                  width: "60px",
                  height: "45px",
                  border: `2px solid ${fam}`,
                  borderRadius: "4px",
                  overflow: "hidden",
                  zIndex: 1,
                }}
              >
                <FlagImg
                  emoji={flagFor(pair.analogueName)}
                  name={pair.analogueName}
                  width={60}
                  radius={2}
                />
              </div>
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              {/* flag + name row */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  flexWrap: "wrap",
                  marginBottom: "6px",
                }}
              >
                <FlagImg
                  emoji={flagFor(pair.subjectName)}
                  name={pair.subjectName}
                  width={20}
                  radius={2}
                />
                <span
                  style={{
                    fontSize: "14px",
                    fontWeight: 600,
                    color: "var(--qgi-text-muted)",
                  }}
                >
                  {pair.subjectName}{" "}
                  <span style={{ color: "var(--qgi-text-dim)" }}>today</span>
                </span>
                <span
                  style={{
                    fontSize: "15px",
                    color: "var(--qgi-text-dim)",
                    fontFamily: "ui-monospace, monospace",
                    userSelect: "none",
                  }}
                >
                  ≈
                </span>
                <FlagImg
                  emoji={flagFor(pair.analogueName)}
                  name={pair.analogueName}
                  width={20}
                  radius={2}
                />
                <span
                  style={{
                    fontSize: "14px",
                    fontWeight: 600,
                    color: "var(--qgi-text-muted)",
                  }}
                >
                  {pair.analogueName} {pair.analogueYear}
                </span>
              </div>

              <h1
                style={{
                  fontSize: "clamp(20px, 3.5vw, 30px)",
                  fontWeight: 800,
                  margin: "0 0 8px",
                  color: "var(--qgi-text)",
                  lineHeight: 1.15,
                }}
              >
                {pair.subjectName} resembles {pair.analogueName}, {pair.analogueYear}
              </h1>

              {/* chips: trend + match + weak */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  flexWrap: "wrap",
                }}
              >
                <Link
                  href={`/trends/${pair.recipeId}` as Route}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "3px 10px",
                    borderRadius: "4px",
                    border: `1px solid ${fam}`,
                    background: `${fam}1A`,
                    color: fam,
                    fontSize: "12px",
                    fontWeight: 600,
                    textDecoration: "none",
                    fontFamily: "ui-monospace, monospace",
                  }}
                >
                  {pair.trendLabel}
                </Link>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "3px 10px",
                    borderRadius: "4px",
                    border: `1px solid ${zone.color}`,
                    color: zone.color,
                    fontSize: "12px",
                    fontWeight: 700,
                    fontFamily: "ui-monospace, monospace",
                  }}
                >
                  {Math.round(pair.matchScore)}% · {zone.label}
                </span>
                {pair.weak && (
                  <span
                    style={{
                      padding: "3px 10px",
                      borderRadius: "4px",
                      border: "1px solid rgba(230,143,41,0.5)",
                      background: "rgba(230,143,41,0.1)",
                      color: "#E68F29",
                      fontSize: "11px",
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    weak analogue
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Lede */}
          <p
            style={{
              fontSize: "15px",
              color: "var(--qgi-text)",
              maxWidth: "760px",
              lineHeight: 1.65,
              margin: 0,
            }}
          >
            {pair.subjectName}&apos;s recent indicator movement most resembles{" "}
            {pair.analogueName} in the {pair.windowYears}-year run-up to its{" "}
            {pair.analogueYear} {pair.trendLabel.toLowerCase()}. Below, each indicator
            that drives the {pair.trendLabel}
            {
              " trend is standardized to each country's own history, so the comparison is about "
            }
            <strong>shape</strong>, not levels. This is a <strong>resemblance</strong>,
            not a forecast.
          </p>
        </div>

        {/* ── Driver overlays ── */}
        <PanelCard dataTour="analogue-drivers">
          <PanelHeading
            label="WHAT IS DRIVING THIS RESEMBLANCE"
            title={`The ${pair.trendLabel} drivers, ${pair.windowYears}-year run-up`}
          />
          {pair.drivers.length > 0 ? (
            <>
              <p
                style={{
                  fontSize: "12px",
                  color: "var(--qgi-text-dim)",
                  margin: "0 0 12px",
                  lineHeight: 1.55,
                  maxWidth: "720px",
                }}
              >
                Each indicator is standardized to its own history, so the lines compare
                shape rather than absolute level. Every line runs left to right and ends
                at the right edge (today for {pair.subjectName}, the event year for{" "}
                {pair.analogueName} and the trend). The dashed line and its band are the{" "}
                {pair.trendLabel}
                {
                  " trend's own canonical shape for that indicator. Tap or hover any chart for the year-by-year values."
                }
              </p>
              {/* legend */}
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "16px",
                  margin: "0 0 16px",
                  fontSize: "11px",
                  fontFamily: "ui-monospace, monospace",
                  color: "var(--qgi-text-muted)",
                }}
              >
                {[
                  {
                    c: "var(--qgi-accent)",
                    dash: false,
                    t: `${pair.subjectName} (today)`,
                  },
                  {
                    c: "#C9A66B",
                    dash: false,
                    t: `${pair.analogueName} ${pair.analogueYear}`,
                  },
                  {
                    c: fam,
                    dash: true,
                    t: `${pair.trendLabel} canonical (p25 to p75 band)`,
                  },
                ].map((l) => (
                  <span
                    key={l.t}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                  >
                    <span
                      style={{
                        width: 16,
                        height: 0,
                        borderTop: `2px ${l.dash ? "dashed" : "solid"} ${l.c}`,
                        display: "inline-block",
                      }}
                    />
                    {l.t}
                  </span>
                ))}
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(min(320px, 100%), 1fr))",
                  gap: "16px",
                }}
              >
                {pair.drivers.map((d) => (
                  <div
                    key={d.code}
                    style={{
                      background: "var(--qgi-bg)",
                      border: "1px solid var(--qgi-border)",
                      borderRadius: "8px",
                      padding: "14px 14px 10px",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "baseline",
                        justifyContent: "space-between",
                        gap: 8,
                        marginBottom: "8px",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "12.5px",
                          fontWeight: 600,
                          color: "var(--qgi-text)",
                          lineHeight: 1.3,
                        }}
                      >
                        {d.name}
                      </span>
                      {!d.canonical && (
                        <span
                          style={{
                            fontSize: "9px",
                            color: "var(--qgi-text-dim)",
                            fontFamily: "ui-monospace, monospace",
                            whiteSpace: "nowrap",
                          }}
                          title="The trend card has no canonical shape for this indicator yet."
                        >
                          no canonical
                        </span>
                      )}
                    </div>
                    <AnalogueOverlayChart
                      subject={d.subject}
                      analogue={d.analogue}
                      canonical={d.canonical}
                      canonicalLo={d.canonicalLo}
                      canonicalHi={d.canonicalHi}
                      windowYears={pair.windowYears}
                      subjectName={pair.subjectName}
                      analogueName={pair.analogueName}
                      analogueYear={pair.analogueYear}
                      familyColor={fam}
                    />
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p
              style={{
                fontSize: "13px",
                color: "var(--qgi-text-muted)",
                margin: 0,
                lineHeight: 1.65,
                fontStyle: "italic",
                borderTop: "1px dashed var(--qgi-border)",
                paddingTop: "12px",
              }}
            >
              The driver indicators for the {pair.trendLabel} trend don&apos;t have enough
              panel history for both {pair.subjectName} and {pair.analogueName} over this
              window to draw a side-by-side overlay. The match itself stands on the
              engine&apos;s shape score; the per-indicator overlay arrives as panel
              coverage fills in.
            </p>
          )}
        </PanelCard>

        {/* ── What happened next (analogue history) ── */}
        <PanelCard dataTour="analogue-outcome">
          <PanelHeading
            label="WHAT HAPPENED NEXT"
            title={`${pair.analogueName} after ${pair.analogueYear}`}
          />
          {pair.whatHappenedNext ? (
            <>
              <p
                style={{
                  fontSize: "14px",
                  color: "var(--qgi-text)",
                  lineHeight: 1.65,
                  margin: 0,
                  maxWidth: "720px",
                }}
              >
                {pair.whatHappenedNext}
              </p>
              {pair.sources && pair.sources.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "8px 14px",
                    marginTop: "12px",
                    paddingTop: "10px",
                    borderTop: "1px solid var(--qgi-border)",
                  }}
                >
                  <span
                    style={{
                      fontSize: "10px",
                      letterSpacing: "1px",
                      color: "var(--qgi-text-dim)",
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    SOURCES:
                  </span>
                  {pair.sources.map((src, i) => (
                    <a
                      key={src}
                      href={src}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontSize: "11px",
                        color: "var(--qgi-accent)",
                        fontFamily: "ui-monospace, monospace",
                        textDecoration: "none",
                      }}
                    >
                      [{i + 1}]
                    </a>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p
              style={{
                fontSize: "13px",
                color: "var(--qgi-text-muted)",
                margin: 0,
                lineHeight: 1.65,
                fontStyle: "italic",
                borderTop: "1px dashed var(--qgi-border)",
                paddingTop: "12px",
              }}
            >
              The dated outcome history for {pair.analogueName} {pair.analogueYear} is
              still being curated. When it lands it appears here as fact about{" "}
              {pair.analogueName}, never as a prediction about {pair.subjectName}.
            </p>
          )}
        </PanelCard>

        {/* ── Handoffs footer ── */}
        <footer
          style={{
            marginTop: "8px",
            paddingTop: "16px",
            borderTop: "1px solid var(--qgi-border)",
            display: "flex",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "8px 14px",
          }}
        >
          {[
            { href: "/analogues", label: "← Back to Analogues" },
            {
              href: `/countries/${pair.subjectIso2}`,
              label: `${pair.subjectName} profile`,
            },
            {
              href: `/countries/${pair.analogueIso2}`,
              label: `${pair.analogueName} profile`,
            },
            { href: `/trends/${pair.recipeId}`, label: `${pair.trendLabel} trend` },
          ].map((l, i) => (
            <span
              key={l.href}
              style={{ display: "inline-flex", alignItems: "center", gap: "8px 14px" }}
            >
              {i > 0 && (
                <span
                  style={{
                    color: "var(--qgi-text-dim)",
                    fontFamily: "ui-monospace, monospace",
                    fontSize: "12px",
                  }}
                >
                  /
                </span>
              )}
              <Link
                href={l.href as Route}
                style={{
                  color: "var(--qgi-accent)",
                  textDecoration: "none",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "12px",
                  letterSpacing: "0.2px",
                }}
              >
                {l.label}
              </Link>
            </span>
          ))}
        </footer>

        <p
          style={{
            marginTop: "16px",
            fontSize: "11px",
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          Shape resemblance across the run-up window. A similarity statement, not a
          forecast.
        </p>
      </div>
    </div>
  );
}
