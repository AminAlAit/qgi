/**
 * CompareAnalogsPair -- two-column list, each country's top 3 historical analogs.
 *
 * Each row: FlagImg + year + match score + one-line "what happened next".
 * Shared analogs (same country+year in both lists) marked with a chip in both
 * columns.
 *
 * Honesty rule (Kwame): "what happened next" is attributed to the analog,
 * never joined to the subject country by a predictive verb.
 *
 * V4.1 bar: archival gold accent, no em-dashes, no banned vocab.
 */
import { PanelShell } from "@/components/countries-v4-1/PanelShell";
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { flagFor } from "@/lib/te-mock/country-flags";
import { sharedAnalogs } from "@/lib/te-mock/compare-data";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";

const ARCHIVAL_GOLD = "#C9A66B";

// Hoisted out of CompareAnalogsPair so React doesn't recreate the
// component on every parent render (eslint react-hooks/static-components).
function AnalogColumn({
  country,
  sharedKeys,
}: {
  country: CountryV4;
  sharedKeys: Set<string>;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: "11px",
          fontFamily: "ui-monospace, monospace",
          fontWeight: 600,
          color: "var(--qgi-text-muted)",
          marginBottom: "10px",
          letterSpacing: "0.4px",
        }}
      >
        {country.name} ({country.iso})
      </div>
      {country.analogs.slice(0, 3).map((a, i) => {
        const key = `${a.country.toLowerCase()}:${a.year}`;
        const isShared = sharedKeys.has(key);
        return (
          <div
            key={`${a.country}-${a.year}-${i}`}
            style={{
              borderBottom: i < 2 ? "1px solid var(--qgi-border)" : undefined,
              paddingBottom: "10px",
              marginBottom: "10px",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "7px",
                marginBottom: "5px",
                flexWrap: "wrap",
              }}
            >
              <FlagImg emoji={flagFor(a.country)} name={a.country} width={16} />
              <span
                style={{
                  fontSize: "12.5px",
                  fontWeight: 600,
                  color: "var(--qgi-text)",
                }}
              >
                {a.country}, {a.year}
              </span>
              <span
                style={{
                  fontSize: "9.5px",
                  fontFamily: "ui-monospace, monospace",
                  padding: "1px 6px",
                  borderRadius: "10px",
                  color: ARCHIVAL_GOLD,
                  border: `1px solid ${ARCHIVAL_GOLD}55`,
                  background: `${ARCHIVAL_GOLD}12`,
                  letterSpacing: "0.2px",
                }}
                title="Structural similarity score between this analogue and the subject country."
              >
                {a.match_score.toFixed(0)}% match
              </span>
              {isShared && (
                <span
                  style={{
                    fontSize: "9px",
                    fontFamily: "ui-monospace, monospace",
                    padding: "1px 5px",
                    borderRadius: "3px",
                    color: "#E68F29",
                    border: "1px solid #E68F2955",
                    background: "#E68F2914",
                    letterSpacing: "0.3px",
                  }}
                >
                  Shared
                </span>
              )}
              {a.weak_analog && (
                <span
                  style={{
                    fontSize: "9.5px",
                    color: "var(--qgi-text-dim)",
                    fontStyle: "italic",
                  }}
                >
                  weaker match
                </span>
              )}
            </div>
            <p
              style={{
                fontSize: "11.5px",
                lineHeight: 1.5,
                color: "var(--qgi-text-muted)",
                margin: 0,
              }}
            >
              {a.what_happened_next}
            </p>
          </div>
        );
      })}
    </div>
  );
}

export function CompareAnalogsPair({
  countryA,
  countryB,
}: {
  countryA: CountryV4;
  countryB: CountryV4;
}) {
  const shared = sharedAnalogs(countryA, countryB);
  const sharedKeys = new Set(shared.map((s) => `${s.country.toLowerCase()}:${s.year}`));

  return (
    <PanelShell
      title="Historical analogues"
      accent={ARCHIVAL_GOLD}
      dataTour="compare-analogs"
      fullWidth
      caption={`Past situations whose shape most resembles each country now. Similarity is not prediction; the outcomes below are history about each analogue, not a forecast.`}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "24px",
        }}
      >
        <AnalogColumn country={countryA} sharedKeys={sharedKeys} />
        <AnalogColumn country={countryB} sharedKeys={sharedKeys} />
      </div>
    </PanelShell>
  );
}
