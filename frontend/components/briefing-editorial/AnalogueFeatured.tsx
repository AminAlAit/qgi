"use client";
/**
 * AnalogueFeatured — full-width "this release's analogue" feature panel.
 *
 * Like The Economist's "Briefing" section: one historical comparison in
 * narrative form. Left: editorial narrative. Right: BriefingScoreBar chart.
 *
 * Client component — the ssr:false dynamic chart requires a Client Component
 * in Next.js 16. Receives serializable props from the server page.
 */
import dynamic from "next/dynamic";
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import type { CountryPairTeaser } from "@/lib/te-mock/dashboard-v4-1-data";

const BriefingScoreBar = dynamic(
  () => import("./BriefingScoreBar").then((m) => ({ default: m.BriefingScoreBar })),
  { ssr: false }
);

interface AnalogueFeaturedProps {
  pair: CountryPairTeaser | null;
}

export function AnalogueFeatured({ pair }: AnalogueFeaturedProps) {
  if (!pair) return null;

  return (
    <section style={{ marginBottom: "24px" }}>
      <style>{`
        .qgi-analogue-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 32px;
          align-items: start;
        }
        @media (max-width: 899px) {
          .qgi-analogue-grid {
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
        <div className="qgi-analogue-grid">
          {/* Left: narrative */}
          <div>
            {/* Eyebrow */}
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: "11px",
                fontWeight: 600,
                letterSpacing: "4px",
                textTransform: "uppercase",
                color: "var(--qgi-accent)",
                marginBottom: "12px",
              }}
            >
              ANALOGUE
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

            {/* Editorial body */}
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
              uncommon — the structural parallel is close enough to demand attention.
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
              Resemblance, not forecast — a structural lens on what these conditions have
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
              → Explore all analogues
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
            <BriefingScoreBar matchPct={pair.match_pct} />
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
