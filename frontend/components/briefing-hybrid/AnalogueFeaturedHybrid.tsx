"use client";
/**
 * AnalogueFeaturedHybrid — hybrid copy of briefing-editorial/AnalogueFeatured.
 *
 * Fixes vs original:
 *   1. Chart label clipping: imports BriefingScoreBarHybrid (increased grid.top
 *      + taller container) so the "90% threshold" markLine label is never clipped.
 *   2. Em-dashes banned on /dashboard: replaced with clean punctuation:
 *      "is uncommon — the structural..." → "is uncommon. The structural..."
 *      "Resemblance, not forecast — a structural lens..." →
 *      "Resemblance, not forecast: a structural lens..."
 *
 * The original briefing-editorial/AnalogueFeatured is 100% untouched.
 */
import dynamic from "next/dynamic";
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import type { CountryPairTeaser } from "@/lib/te-mock/dashboard-v4-1-data";

const BriefingScoreBarHybrid = dynamic(
  () =>
    import("./BriefingScoreBarHybrid").then((m) => ({
      default: m.BriefingScoreBarHybrid,
    })),
  { ssr: false }
);

interface AnalogueFeaturedHybridProps {
  pair: CountryPairTeaser | null;
}

export function AnalogueFeaturedHybrid({ pair }: AnalogueFeaturedHybridProps) {
  if (!pair) return null;

  return (
    <section style={{ marginBottom: "24px" }}>
      <style>{`
        .qgi-analogue-grid-h {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 32px;
          align-items: start;
        }
        @media (max-width: 899px) {
          .qgi-analogue-grid-h {
            grid-template-columns: 1fr;
            gap: 20px;
          }
        }
      `}</style>

      <div
        style={{
          background: "var(--qgi-surface)",
          borderLeft: "4px solid #B6924A",
          borderRadius: "8px",
          padding: "28px 32px",
          border: "1px solid var(--qgi-border)",
        }}
      >
        <div className="qgi-analogue-grid-h">
          {/* Left: narrative */}
          <div>
            {/* Eyebrow */}
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "11px",
                fontWeight: 600,
                letterSpacing: "1.5px",
                color: "var(--qgi-accent)",
                marginBottom: "12px",
              }}
            >
              Analogue
            </div>

            {/* Headline */}
            <h2
              style={{
                fontSize: "24px",
                fontWeight: 700,
                color: "var(--qgi-text)",
                lineHeight: 1.2,
                margin: "0 0 14px",
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                <FlagImg
                  emoji={flagFor(pair.country_a)}
                  name={pair.country_a}
                  width={20}
                  radius={2}
                />
                {pair.country_a}
              </span>{" "}
              today resembles{" "}
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                <FlagImg
                  emoji={flagFor(pair.country_b)}
                  name={pair.country_b}
                  width={20}
                  radius={2}
                />
                {pair.country_b}
              </span>{" "}
              in {pair.country_b_year}
            </h2>

            {/* Score badge */}
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "18px",
                fontWeight: 700,
                color: "#C9A84C",
                marginBottom: "16px",
              }}
            >
              {Math.round(pair.match_pct)}% structural match
            </div>

            {/* Editorial body — em-dashes replaced with clean punctuation */}
            <p
              style={{
                fontSize: "14px",
                lineHeight: 1.65,
                color: "var(--qgi-text-muted)",
                margin: "0 0 8px",
              }}
            >
              The structural conditions for {pair.recipe_label} are present in{" "}
              {pair.country_a} at a level last seen in {pair.country_b} in{" "}
              {pair.country_b_year}. Historical precedent at this confidence level is
              uncommon. The structural parallel is close enough to demand attention.
            </p>
            <p
              style={{
                fontSize: "13px",
                lineHeight: 1.6,
                color: "var(--qgi-text-dim)",
                margin: "0 0 16px",
                fontStyle: "italic",
              }}
            >
              Resemblance, not forecast: a structural lens on what these conditions have
              meant before.
            </p>

            {/* Link */}
            <Link
              href={"/analogues" as Route}
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px",
                color: "var(--qgi-accent)",
                textDecoration: "none",
              }}
            >
              &rarr; Explore all analogues
            </Link>
          </div>

          {/* Right: chart */}
          <div>
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "11px",
                color: "var(--qgi-text-dim)",
                letterSpacing: "2px",
                textTransform: "uppercase",
                marginBottom: "8px",
              }}
            >
              STRUCTURAL MATCH
            </div>
            <BriefingScoreBarHybrid matchPct={pair.match_pct} />
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "10px",
                color: "var(--qgi-text-dim)",
                marginTop: "8px",
              }}
            >
              {pair.recipe_label}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
