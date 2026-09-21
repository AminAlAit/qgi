/**
 * CompareDriversFaceOff — SHAP attribution side by side for the top shared
 * recipe.
 *
 * If both countries are in play on at least one shared recipe, renders the
 * top shared recipe's attribution for both countries. Fallback: each
 * country's top individual recipe when there is no overlap.
 *
 * Two columns of drivers_attribution (signal_share_pct per indicator).
 * Shared indicators list at the bottom.
 * Panel tinted in the family color of the top shared recipe.
 *
 * V4.1 bar: familyColor() tint, no em-dashes, no banned vocab.
 */
import { FlagImg } from "@/components/countries-v4-1/FlagImg";
import { familyColor } from "@/lib/te-mock/l1-families";
import { NEUTRAL_SLATE } from "@/lib/te-mock/l1-families";
import type { CountryV4 } from "@/lib/te-mock/countries-v4-data";
import type { CompareGapRow } from "@/lib/te-mock/compare-data";

function AttributionRow({ name, share }: { name: string; share: number }) {
  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}
    >
      <span
        style={{
          flex: 1,
          fontSize: "12px",
          color: "var(--qgi-text)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={name}
      >
        {name}
      </span>
      <span
        style={{
          fontFamily: "ui-monospace, monospace",
          fontSize: "11px",
          fontWeight: 700,
          color: "var(--qgi-text)",
          width: "36px",
          textAlign: "right",
          flexShrink: 0,
        }}
      >
        {share.toFixed(0)}%
      </span>
      <div
        style={{
          width: "60px",
          height: "5px",
          background: "var(--qgi-border)",
          borderRadius: "3px",
          overflow: "hidden",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: `${share}%`,
            height: "100%",
            background: NEUTRAL_SLATE,
            borderRadius: "3px",
          }}
        />
      </div>
    </div>
  );
}

export function CompareDriversFaceOff({
  countryA,
  countryB,
  topRow,
}: {
  countryA: CountryV4;
  countryB: CountryV4;
  topRow: CompareGapRow | null;
}) {
  // Determine which recipe to show and what color to use.
  const recipeLabel = topRow?.label ?? countryA.top_recipes[0]?.label ?? "Top trend";
  const scoreA = topRow?.score_a ?? countryA.top_recipes[0]?.score ?? null;
  const scoreB = topRow?.score_b ?? countryB.top_recipes[0]?.score ?? null;
  const l1Id = topRow?.l1_id ?? countryA.top_recipes[0]?.l1_id ?? "";
  const l1Color = topRow?.l1_color ?? countryA.top_recipes[0]?.l1_color;
  const color = familyColor(l1Id, l1Color);
  const tint = `${color}14`;
  const borderColor = `${color}40`;

  const attribA = countryA.drivers_attribution;
  const attribB = countryB.drivers_attribution;

  const codesA = new Set(attribA.map((d) => d.indicator_code));
  const codesB = new Set(attribB.map((d) => d.indicator_code));
  const sharedCodes = attribA
    .filter((d) => codesB.has(d.indicator_code))
    .map((d) => d.indicator_name);

  const scoreStr = [
    scoreA !== null ? `${countryA.name} ${scoreA.toFixed(0)}` : null,
    scoreB !== null ? `${countryB.name} ${scoreB.toFixed(0)}` : null,
  ]
    .filter(Boolean)
    .join(" | ");

  return (
    <section
      data-tour="compare-drivers"
      style={{
        background: tint,
        border: "1px solid var(--qgi-border)",
        borderLeft: `3px solid ${color}`,
        borderRadius: "6px",
        padding: "16px 18px",
      }}
    >
      {/* Recipe label + scores */}
      <div style={{ marginBottom: "14px" }}>
        <h2
          style={{
            fontSize: "13px",
            letterSpacing: "0.5px",
            textTransform: "uppercase",
            color,
            fontFamily: "ui-monospace, monospace",
            fontWeight: 600,
            margin: "0 0 4px",
          }}
        >
          Drivers face-off
        </h2>
        <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
          <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--qgi-text)" }}>
            {recipeLabel}
          </span>
          {scoreStr && (
            <span
              style={{
                fontSize: "11px",
                fontFamily: "ui-monospace, monospace",
                color: "var(--qgi-text-muted)",
              }}
            >
              {scoreStr}
            </span>
          )}
        </div>
      </div>

      {/* Two attribution columns */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "16px",
        }}
      >
        {/* Country A */}
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              marginBottom: "10px",
            }}
          >
            <FlagImg emoji={countryA.flag_emoji} name={countryA.name} width={16} />
            <span
              style={{
                fontSize: "12px",
                fontWeight: 600,
                color: "var(--qgi-text)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {countryA.name}
            </span>
          </div>
          {attribA.length === 0 ? (
            <span
              style={{
                fontSize: "11px",
                color: "var(--qgi-text-dim)",
                fontStyle: "italic",
              }}
            >
              No attribution data
            </span>
          ) : (
            attribA.map((d) => (
              <AttributionRow
                key={d.indicator_code}
                name={d.indicator_name}
                share={d.signal_share_pct}
              />
            ))
          )}
        </div>

        {/* Country B */}
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              marginBottom: "10px",
            }}
          >
            <FlagImg emoji={countryB.flag_emoji} name={countryB.name} width={16} />
            <span
              style={{
                fontSize: "12px",
                fontWeight: 600,
                color: "var(--qgi-text)",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {countryB.name}
            </span>
          </div>
          {attribB.length === 0 ? (
            <span
              style={{
                fontSize: "11px",
                color: "var(--qgi-text-dim)",
                fontStyle: "italic",
              }}
            >
              No attribution data
            </span>
          ) : (
            attribB.map((d) => (
              <AttributionRow
                key={d.indicator_code}
                name={d.indicator_name}
                share={d.signal_share_pct}
              />
            ))
          )}
        </div>
      </div>

      {/* Shared indicators */}
      {sharedCodes.length > 0 && (
        <div
          style={{
            marginTop: "14px",
            paddingTop: "12px",
            borderTop: `1px solid ${borderColor}`,
          }}
        >
          <div
            style={{
              fontSize: "10px",
              letterSpacing: "0.6px",
              textTransform: "uppercase",
              color,
              fontFamily: "ui-monospace, monospace",
              fontWeight: 600,
              marginBottom: "6px",
            }}
          >
            Shared indicators
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
            {sharedCodes.map((name) => (
              <span
                key={name}
                style={{
                  fontSize: "10px",
                  fontFamily: "ui-monospace, monospace",
                  padding: "2px 8px",
                  border: `1px solid ${color}44`,
                  borderRadius: "3px",
                  color,
                  background: `${color}12`,
                }}
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
