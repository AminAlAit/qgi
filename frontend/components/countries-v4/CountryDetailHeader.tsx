/**
 * CountryDetailHeader — hero strip for /countries-v4/[iso].
 *
 * Mirrors `RecipeDetail.tsx`'s header idiom (96px tile + 28px title +
 * status chips). The 96px tile carries the country flag emoji; the
 * chips beneath the title carry tier identity (compound score,
 * recipes-lit count, ISO).
 */
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";

export function CountryDetailHeader({ country }: { country: CountryV4 }) {
  return (
    <div
      style={{ display: "flex", gap: "20px", alignItems: "flex-start", flexWrap: "wrap" }}
    >
      <div
        style={{
          width: "96px",
          height: "96px",
          background: "var(--qgi-bg)",
          border: "1px solid var(--qgi-accent)",
          borderRadius: "10px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
        aria-hidden
      >
        <FlagImg emoji={country.flag_emoji} name={country.name} width={64} radius={4} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            marginBottom: "10px",
            flexWrap: "wrap",
          }}
        >
          {/* Compound chip — amber accent (Sofia's metric-tile pattern) */}
          <span
            style={{
              fontSize: "11px",
              padding: "3px 9px",
              border: "1px solid var(--qgi-amber)",
              color: "var(--qgi-amber)",
              backgroundColor: "rgba(245,158,11,0.10)",
              borderRadius: "4px",
              letterSpacing: "0.3px",
              fontFamily: "ui-monospace, monospace",
              fontWeight: 600,
            }}
          >
            Compound {country.compound_score.toFixed(1)}
          </span>
          {/* Lit-count chip — honest tier disclosure */}
          <span
            style={{
              fontSize: "11px",
              padding: "3px 9px",
              border: `1px solid ${country.recipes_lit_graduated > 0 ? "#3FBF8F" : "var(--qgi-text-dim)"}`,
              color:
                country.recipes_lit_graduated > 0 ? "#3FBF8F" : "var(--qgi-text-muted)",
              backgroundColor:
                country.recipes_lit_graduated > 0
                  ? "rgba(63,191,143,0.10)"
                  : "rgba(122,143,160,0.06)",
              borderRadius: "4px",
              letterSpacing: "0.3px",
              fontFamily: "ui-monospace, monospace",
              fontWeight: 600,
            }}
            title={`${country.recipes_lit_count} recipes currently lit; ${country.recipes_lit_graduated} of those are 🟢 Validated. The rest are walked-failed or queued.`}
          >
            {country.recipes_lit_count} lit · {country.recipes_lit_graduated} graduated
          </span>
          {/* ISO chip */}
          <span
            style={{
              fontSize: "10px",
              padding: "3px 8px",
              border: "1px solid var(--qgi-border)",
              color: "var(--qgi-text-dim)",
              borderRadius: "3px",
              letterSpacing: "0.6px",
              fontFamily: "ui-monospace, monospace",
            }}
          >
            ISO · {country.iso}
          </span>
        </div>
        <h1
          style={{
            fontSize: "28px",
            fontWeight: 600,
            lineHeight: 1.15,
            margin: "0 0 6px",
          }}
        >
          {country.name}
        </h1>
        <p
          style={{
            color: "var(--qgi-text-muted)",
            fontSize: "13px",
            margin: 0,
          }}
        >
          {country.region} · population ~{fmt(country.population)} · release{" "}
          {country.vintage}
        </p>
      </div>
    </div>
  );
}

function fmt(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}
