/**
 * AnaloguesBandHybrid — hybrid copy of briefing-signal/AnaloguesBand.tsx.
 *
 * Change from frozen original (briefing-signal/AnaloguesBand.tsx):
 *   - Subtitle em-dash replaced with a colon:
 *     "Structural similarity to a real historical moment — a lens, not a forecast."
 *     → "Structural similarity to a real historical moment: a lens, not a forecast."
 *
 * The original component is frozen (briefing-signal/) and must NOT be modified.
 * Server component.
 */
import Link from "next/link";
import type { Route } from "next";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import type { CountryPairTeaser } from "@/lib/te-mock/dashboard-v4-1-data";

interface Props {
  pairs: CountryPairTeaser[];
}

export function AnaloguesBandHybrid({ pairs }: Props) {
  if (pairs.length === 0) return null;

  return (
    <section>
      <style>{`
        .qgi-analogue-card { transition: transform 140ms ease, box-shadow 140ms ease; }
        .qgi-analogue-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.35); }
      `}</style>

      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: "14px",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2
            style={{
              fontSize: "18px",
              fontWeight: 600,
              margin: "0 0 4px",
              letterSpacing: "-0.2px",
            }}
          >
            Historical Precedents
          </h2>
          <p
            style={{
              fontSize: "13px",
              color: "var(--qgi-text-muted)",
              margin: 0,
              lineHeight: 1.5,
              maxWidth: "680px",
            }}
          >
            Structural similarity to a real historical moment: a lens, not a forecast.
          </p>
        </div>
        <Link
          href={"/analogues" as Route}
          style={{
            fontSize: "12px",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-accent)",
            textDecoration: "none",
            whiteSpace: "nowrap",
            alignSelf: "center",
          }}
        >
          → Analogues
        </Link>
      </div>

      {/* Card grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "12px",
        }}
      >
        {pairs.map((p, i) => (
          <Link
            key={`${p.country_a}-${p.country_b}-${p.country_b_year}-${p.recipe_id}-${i}`}
            href={"/analogues" as Route}
            className="qgi-analogue-card"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "8px",
              textDecoration: "none",
              color: "inherit",
              background: "var(--qgi-surface)",
              border: "1px solid var(--qgi-border)",
              borderLeft: "3px solid #B6924A",
              borderRadius: "8px",
              padding: "14px",
              minWidth: 0,
            }}
          >
            {/* Country A → resembles → Country B */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                flexWrap: "wrap",
              }}
            >
              <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                <FlagImg
                  emoji={flagFor(p.country_a)}
                  name={p.country_a}
                  width={18}
                  radius={2}
                />
                <span
                  style={{ fontSize: "13px", fontWeight: 600, color: "var(--qgi-text)" }}
                >
                  {p.country_a}
                </span>
              </span>
              <span
                style={{
                  fontSize: "11px",
                  color: "var(--qgi-text-dim)",
                  fontStyle: "italic",
                }}
              >
                resembles
              </span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                <FlagImg
                  emoji={flagFor(p.country_b)}
                  name={p.country_b}
                  width={18}
                  radius={2}
                />
                <span
                  style={{ fontSize: "13px", fontWeight: 600, color: "var(--qgi-text)" }}
                >
                  {p.country_b}, {p.country_b_year}
                </span>
              </span>
            </div>

            {/* Recipe label + match % */}
            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                justifyContent: "space-between",
                gap: "8px",
              }}
            >
              <span style={{ fontSize: "12px", color: "var(--qgi-text-muted)" }}>
                {p.recipe_label}
              </span>
              <span
                style={{
                  fontFamily: "ui-monospace, monospace",
                  fontSize: "14px",
                  fontWeight: 700,
                  color: "#C9A84C",
                }}
              >
                {Math.round(p.match_pct)}% match
              </span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
